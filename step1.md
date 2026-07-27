需要先处理一次，而且建议把“第一次处理”设计成确定性预清洗，不要直接让 Coding Agent 一次读取 200 多条原始 HTML 数据。

200 多条本身不算大，但每行可能包含 HTML、重复模板、中英文结案话术和长链接。一次性加载会带来几个问题：

* 原始噪声大量占用上下文
* Agent 容易跨行串数据
* 中途失败后难以断点续跑
* 同一条数据重复处理时结果可能不一致
* 很难定位哪一行失败
* 输出稍长就可能超过上下文或输出限制

更稳妥的方式是分成两阶段。

推荐流程

原始 CSV
  ↓
第一阶段：本地确定性预清洗
  ↓
预清洗 CSV / JSONL
  ↓
第二阶段：Coding Agent 分批语义处理
  ↓
逐条保存结果 + 失败记录 + 处理日志
  ↓
最终 CSV

第一阶段需要处理什么

这一阶段不需要大模型，只做不会引入业务判断的操作：

1. 删除 HTML 注释，例如：

<!-- for WeLink copy-->

2. 将 <p>、<br>、<div> 转成换行。
3. 删除样式、空标签、图片标签。
4. 解码：

&nbsp;
&amp;
&lt;

5. 提取 URL，但不要删除业务 URL。
6. 压缩重复空格和空行。
7. 给每行生成唯一 ID。
8. 保留原始文本和预清洗文本。

建议第一阶段输出至少这些列：

record_id
raw_text
preclean_text
preclean_status
preclean_error

不要只覆盖原始列。

为什么建议转成 JSONL

虽然 CSV 可以继续用，但 Coding Agent 批处理时，JSONL 通常比单列 CSV 更稳。

每一行是独立 JSON：

{"record_id":"CASE_0001","preclean_text":"问题原因：用户咨询……"}
{"record_id":"CASE_0002","preclean_text":"问题原因：页面查询权限……"}

优点是：

* 一行对应一条记录
* 容易逐行读取
* 可以分批处理
* 中途失败不影响其他行
* 方便追加结果
* 不容易因为正文内有逗号、换行、引号而破坏格式

CSV 仍然可以作为最终交付格式，处理中间格式推荐 JSONL。

Coding Agent 不应一次性加载全量文件

正确做法是让程序负责读取数据，Agent 只处理当前批次。

例如：

每批 10 条

或者：

每批 5～20 条，根据单条长度动态调整

不要把完整 CSV 内容直接塞进 prompt。

理想执行方式是：

for batch in read_batches("preclean.jsonl", batch_size=10):
    results = process_batch(batch)
    append_results(results, "results.jsonl")

Agent 每次只看到当前批次。

推荐按字符数动态分批

单纯固定 10 条并不一定稳定，因为有的行可能只有 100 字，有的可能超过 5000 字。

可以同时限制：

最多 10 条
最多 20,000～30,000 个字符

例如：

def make_batches(records, max_items=10, max_chars=20000):
    batch = []
    total_chars = 0
    for record in records:
        text_length = len(record["preclean_text"])
        if batch and (
            len(batch) >= max_items
            or total_chars + text_length > max_chars
        ):
            yield batch
            batch = []
            total_chars = 0
        batch.append(record)
        total_chars += text_length
    if batch:
        yield batch

每条记录要独立返回

不要让 Agent 返回一大段自然语言。要求它严格返回结构化结果。

例如：

{
  "record_id": "CASE_0001",
  "user_intent": "咨询履行销售订单页面所需权限",
  "cause_normalized": "页面已切换到新系统，需要申请对应角色",
  "solution_normalized": "申请订单处理专员角色",
  "required_roles": [
    "订单处理专员"
  ],
  "related_menus": [
    "销售订单发运",
    "销售订单退货"
  ],
  "urls": [
    "https://..."
  ],
  "resolution_status": "resolved",
  "removed_noise": [
    "closing_template",
    "html_comment"
  ],
  "quality_flags": []
}

每条输入必须对应一条输出，且必须带回 record_id。

应该让 Skill 逐行处理，还是逐批处理

建议 Skill 的逻辑定义为：

对每条记录独立处理。

但实际调用方式使用：

一次传入一个小批次。

也就是说：

Skill 语义：逐条独立
运行机制：小批量调用

这样既能提高效率，也能避免跨记录污染。

在 Skill 里增加以下约束：

- 每条记录必须独立分析。
- 不得引用其他记录的信息。
- 不得合并不同 record_id 的内容。
- 输入多少条，输出必须多少条。
- 输出顺序必须与输入顺序一致。
- 每条输出必须保留 record_id。
- 单条失败时返回 error，不得终止整批。

需要设置断点续跑

不要处理完 200 条后再一次性保存。

应当每批处理后立即追加到：

results.jsonl

并维护：

processed_ids.txt

重新执行时跳过已经完成的 ID。

示例：

processed_ids = load_processed_ids("results.jsonl")
for batch in make_batches(records):
    pending_batch = [
        item for item in batch
        if item["record_id"] not in processed_ids
    ]
    if not pending_batch:
        continue
    results = process_batch(pending_batch)
    append_jsonl(results, "results.jsonl")

推荐保存三份结果

results_success.jsonl
results_review.jsonl
results_error.jsonl

分类建议：

success

* 权限角色明确
* Solution 有效
* 无明显字段冲突
* 模板已清除

review

* 角色是推断出来的
* Solution 太短
* Cause 和 Solution 混合
* 只有 URL
* 多个权限无法确认
* 状态冲突

error

* JSON 解析失败
* 输入为空
* 程序异常
* 输出缺少 record_id

第一次预处理不要做什么

第一阶段不要过度清理：

* 不要删除所有短句
* 不要删除所有英文
* 不要删除所有 URL
* 不要尝试重写 Solution
* 不要自动猜测权限名称
* 不要把 OK 直接删除而不记录状态
* 不要把原始数据覆盖掉

第一阶段只负责减少明显噪声；业务理解留给 Skill。

适合你的最终文件结构

原始文件：

cases_raw.csv

第一阶段结果：

cases_preclean.jsonl

Agent 输出：

cases_result.jsonl

人工复核：

cases_review.csv

最终结果：

cases_cleaned.csv

一个实用的预处理脚本

from __future__ import annotations
import csv
import html
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup, Comment
def preclean_html(raw_text: str) -> dict:
    raw_text = raw_text or ""
    try:
        soup = BeautifulSoup(raw_text, "html.parser")
        # 删除 HTML 注释
        for comment in soup.find_all(
            string=lambda text: isinstance(text, Comment)
        ):
            comment.extract()
        # 删除脚本和样式
        for tag in soup(["script", "style"]):
            tag.decompose()
        # 提取图片地址，之后删除图片标签
        image_urls = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                image_urls.append(src.strip())
            img.decompose()
        # 给块级标签补换行
        for tag_name in ["p", "div", "br", "li"]:
            for tag in soup.find_all(tag_name):
                tag.append("\n")
        text = soup.get_text("\n")
        text = html.unescape(text)
        # 提取 URL
        urls = re.findall(r"https?://[^\s<>'\"]+", text)
        urls = [
            url.rstrip("。，；;、)]}》")
            for url in urls
        ]
        # 标准化空格与换行
        text = text.replace("\u00a0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        return {
            "preclean_text": text,
            "urls": list(dict.fromkeys(urls)),
            "image_urls": list(dict.fromkeys(image_urls)),
            "preclean_status": "success",
            "preclean_error": "",
        }
    except Exception as exc:
        # HTML 解析异常时，降级为简单纯文本处理
        fallback = html.unescape(raw_text)
        fallback = re.sub(r"<!--.*?-->", "", fallback, flags=re.S)
        fallback = re.sub(r"<[^>]+>", "\n", fallback)
        fallback = re.sub(r"\n{3,}", "\n\n", fallback).strip()
        return {
            "preclean_text": fallback,
            "urls": [],
            "image_urls": [],
            "preclean_status": "fallback",
            "preclean_error": str(exc),
        }
def csv_to_jsonl(
    input_csv: str,
    output_jsonl: str,
    text_column: str,
) -> None:
    input_path = Path(input_csv)
    output_path = Path(output_jsonl)
    with input_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as source, output_path.open(
        "w",
        encoding="utf-8",
    ) as target:
        reader = csv.DictReader(source)
        if text_column not in (reader.fieldnames or []):
            raise ValueError(
                f"找不到列 {text_column!r}，"
                f"现有列：{reader.fieldnames}"
            )
        for index, row in enumerate(reader, start=1):
            raw_text = row.get(text_column, "")
            cleaned = preclean_html(raw_text)
            record = {
                "record_id": f"CASE_{index:05d}",
                "raw_text": raw_text,
                **cleaned,
            }
            target.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )
if __name__ == "__main__":
    csv_to_jsonl(
        input_csv="cases_raw.csv",
        output_jsonl="cases_preclean.jsonl",
        text_column="content",
    )

需要安装：

pip install beautifulsoup4

对 Coding Agent 的执行指令

可以给 Agent 类似这样的任务：

读取 cases_preclean.jsonl，但不要一次加载全部内容。
要求：
1. 使用流式方式逐行读取。
2. 每批最多 10 条，且总字符数不超过 20000。
3. 对每条记录独立调用 itsm-case-noise-reduction Skill。
4. 输入和输出均保留 record_id。
5. 每处理完一批，立即追加写入 cases_result.jsonl。
6. 已存在于结果文件中的 record_id 自动跳过。
7. 单条失败时记录 error 字段，不终止整批。
8. 不修改 raw_text。
9. 将需要人工复核的数据写入 cases_review.jsonl。
10. 全部完成后，再将 JSONL 转换为最终 CSV。

结论是：**你的单列 CSV 可以使用，但不建议直接交给 Coding Agent 全量读取。先做一次本地、确定性的 HTML 预清洗，再转换为带 ID 的 JSONL，之后让 Agent 分批、逐条、可断点地调用 Skill。**这样最稳健，也最容易追踪和复核。