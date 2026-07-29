---
name: metaerp-user-event-analysis
description: "对 MetaERP 用户事件工单（Excel）做三维度归类：专题、问题表象 L1/L2、解决方案分类（S1-S7 含 S4c），并生成专题→L1→解决方案桑基图。分类由后台进程逐条调 LLM 判定（单条独立上下文、断点续跑、并发），判据唯一事实源为 references/spec.md，配套评测脚本用人工审核金标算准确率与混淆矩阵、驱动判据迭代。凡涉及 MetaERP 工单归类/打标/分类统计/分类桑基图/分类准确率评测/判据修订的请求都必须使用本技能，包括用户只说'跑一下工单分类''补跑失败的''看下分类效果''改判据'等简略表述。"
version: 3.0.0
compatibility: "Python 3.10+；依赖 pandas、openpyxl、pyyaml、anthropic、httpx。LLM 走内部 MAAS 网关（Anthropic Messages 格式），.env 配置 LLM_BASE_URL / LLM_MODEL / ANTHROPIC_AUTH_TOKEN，内网直连不走代理。桑基图 ECharts CDN 渲染。Windows/PowerShell 下直接 python 调脚本，禁止 shell 内联 Python 代码。"
metadata:
  author: MetaERP-OPS
  version: 3.0.0
  category: data-analysis
  tags: [metaerp, ticket-classification, llm-batch, eval-driven]
---

# MetaERP 用户事件工单归类分析 v3

## 架构约定（先读，这决定了每个文件的职责边界）

1. **`references/spec.md` 是分类判据的唯一事实源**。classify.py 运行时读取其全文拼入 system prompt；人工复核也以它为标准。**修改判据只改 spec.md**——本文件（SKILL.md）不含任何判据，也永远不要往这里加判据。
2. **本文件只管编排**：怎么跑脚本、参数在哪配、出错怎么办。
3. **分类执行方式**：单条工单一次 LLM 调用、独立上下文、temperature=0、线程池并发。不做多条一批（批内交叉污染损失效果），不用正则匹配，不在对话里现场编写分类代码。
4. **评测驱动迭代**：改 spec 前先有基线数字；改 spec 后跑开发集回归。改进方向由混淆矩阵指出，不靠感觉。

## 文件清单

| 文件 | 职责 |
|------|------|
| `references/spec.md` | 三维度判定规范（机器优先、自包含），唯一事实源 |
| `scripts/classify.py` | ping / run（分类+断点续跑+写回）/ finalize（仅写回） |
| `scripts/eval.py` | sample（抽评测集）/ score（准确率+混淆矩阵+边界统计）/ agree（一致性） |
| `scripts/sankey.py` | 从已分类 Excel 生成桑基图 HTML |
| `scripts/config.yaml` | 运行参数、Excel 列名映射、金标列名、桑基图参数 |
| `.env` | LLM 凭证（不入 git，按 .env.example 自建） |

## 标准流程

### 首次使用（一次性）

```bash
# 1. 配置凭证：复制 .env.example 为 .env，填入网关地址/模型/key
# 2. 连通性诊断：确认网关可达、key 有效、模型能按 schema 输出
python scripts/classify.py ping
# 3. 确认列名：config.yaml 的 excel.columns 候选名覆盖不到实际表头时，
#    脚本会报错并打印实际表头，按提示填 name_override
```

### 建立评测基线（有人工审核金标数据时，强烈建议先做）

```bash
# 从人工审核过的 Excel 分层抽样出开发集/测试集（测试集封存，仅大版本时用）
python scripts/eval.py sample --gold data/raw/已审核工单.xlsx
# 在开发集上跑分类
python scripts/classify.py run --input data/interim/dev.xlsx --results-dir data/interim/dev_results --output data/interim/dev_已分类.xlsx
# 算基线：三维度准确率 + 混淆矩阵 + 边界字段有效性
python scripts/eval.py score --gold data/interim/dev.xlsx --results data/interim/dev_results/results.jsonl
```

金标列名默认为 `专题-人工`/`L1-人工`/`L2-人工`/`解决方案-人工`，与实际不符时改 config.yaml 的 `eval.gold_columns`。

### 全量分类

```bash
# 长任务：数千条 × LLM 调用，放后台进程跑，不阻塞对话
python scripts/classify.py run \
    --input data/raw/用户事件工单.xlsx \
    --results-dir data/interim/results \
    --output data/processed/工单_已分类.xlsx

# 网关波动导致部分失败 → 补跑（已成功条目自动跳过）
python scripts/classify.py run --input ... --results-dir ... --output ... --retry-errors

# 只重新写回（不调 LLM，例如改了输出列名后）
python scripts/classify.py finalize --input ... --results-dir ... --output ...
```

断点续跑机制：`results.jsonl` 逐条记录，重跑自动跳过已成功工单；失败条目带 error 字段，`--retry-errors` 补跑。

### 人工复核（定向，不全量）

输出 Excel 含两个复核辅助列：
- **分类依据**：LLM 引用的判据要点，复核时先看这个判断是否引对了判据
- **边界工单**：值为"是"的条目命中易混淆场景或信息不足——**按此列筛选做定向复核**，通常只占全量的一小部分

### 判据迭代循环

```
score 看混淆矩阵 → 找错误最集中的类别对 → 打开 spec.md 修订对应边界段落
→ 重跑开发集 → score 对比 → 满意后跑全量
```

两条铁律：
- **不一致 ≠ 模型差**：`eval.py agree` 对比 temperature=0 的两次结果，不一致条目意味着 spec 判据本身有歧义，修 spec 而不是调 prompt 技巧
- **测试集只在大版本动**：日常迭代只用开发集，防止对评测集过拟合

### 生成桑基图

```bash
python scripts/sankey.py --input data/processed/工单_已分类.xlsx --output data/processed/桑基图.html
```

节点去重、自环过滤、link 对齐均已在脚本内处理；显示参数在 config.yaml 的 `sankey` 段。

## 故障排查

| 现象 | 处理 |
|------|------|
| ping 失败 | 依次查：.env 三个变量、网关地址是否含 /anthropic 路径、内网连通性（脚本已 trust_env=False 不走代理） |
| 大量 429/5xx | 下调 config.yaml 的 run.concurrency |
| 报"未找到字段" | 按报错打印的实际表头，在 config.yaml 填 name_override |
| 输出枚举校验失败率高 | 检查 spec.md 第〇章 0.2 词表与 classify.py 顶部常量是否同步（两处必须一致） |
| Excel 保存报占用 | 脚本自动换名输出 `_分类结果.xlsx`；或关闭 Excel 后 finalize 重写 |
| PowerShell 解析错误 | 只用 `python scripts/xxx.py` 形式调用，禁止内联 Python 代码 |

## 修改本 skill 时的约束

- 往 spec.md 加判据：保持"定义→正向线索→负向线索→边界对比"的结构；新增类别时同步更新 spec 第〇章 0.2 词表 **和** classify.py 顶部的枚举常量（唯一需要双处同步的地方，改完跑一次 ping 验证）
- 不要把统计数字（各类工单量）写进 spec——那是数据集属性不是判据，会成为隐性先验
- 不要在 SKILL.md 复述判据摘要——历史教训：双份维护必然漂移
