# ITSM Case Noise Reduction Skill

## 1. Skill 名称

`itsm-case-noise-reduction`

## 2. Skill 目标

对 ITSM、客服工单、权限咨询、问题解决案例等半结构化 HTML 文本进行批量降噪、字段提取、内容标准化和质量校验。

该 Skill 重点处理以下类型的输入：

- HTML 标签和内联样式
- `<!-- for WeLink copy-->` 等系统注释
- 重复的结案话术
- 中英文重复话术
- 无意义状态词，如 `OK`、`Resolved`、`###`
- 图片、空白节点和无意义容器
- URL 与正文粘连
- 字段名称不一致
- 多段 Solution 内容拆散
- 权限角色、菜单、系统链接等关键信息混杂
- “问题原因”实际填写成“用户诉求”的情况

最终输出统一的结构化数据，可用于：

- 知识库建设
- FAQ 生成
- 工单聚类
- 搜索召回
- 大模型训练数据
- RAG 数据源
- 权限咨询知识图谱
- 数据分析和报表

---

## 3. 输入格式

输入可以是：

1. 单条 HTML 字符串
2. 多条案例组成的数组
3. CSV、Excel 或数据库记录中的文本字段
4. 已经去除部分 HTML 的纯文本
5. 混合中文、英文、URL 和系统模板话术的文本

示例输入：

```html
<p> 问题原因 (Cause)：咨询导入非标任务令按钮的权限</p>
<p> 解决方案 (Solution)：<!-- for WeLink copy-->WOM 创建非标任务令_计划员</p>
<p>
  <img src="example.png" alt="" />
  https://w3.huawei.com/iauth/#/selectPrivilege?onlyRole=true
</p>
<p> 处理结果 (Resolved or not)：<span>Resolved&nbsp;</span></p>
<p> ###</p>
<div style="background-color:pink;">
  您好！您的问题已解决，系统已提供7*24小时在线服务……
</div>
```

---

## 4. 推荐输出结构

每条案例建议输出以下字段：

```json
{
  "case_id": null,
  "user_intent": "",
  "cause_raw": "",
  "cause_normalized": "",
  "solution_raw": "",
  "solution_normalized": "",
  "required_roles": [],
  "related_menus": [],
  "related_systems": [],
  "urls": [],
  "resolution_status": "",
  "resolution_status_normalized": "",
  "business_keywords": [],
  "removed_noise": [],
  "quality_flags": [],
  "clean_text": "",
  "summary": ""
}
```

字段说明：

| 字段 | 含义 |
|---|---|
| `user_intent` | 用户实际咨询内容 |
| `cause_raw` | 原始“问题原因”字段 |
| `cause_normalized` | 标准化后的问题原因 |
| `solution_raw` | 原始解决方案内容 |
| `solution_normalized` | 清理和整合后的解决方案 |
| `required_roles` | 需要申请的角色或权限 |
| `related_menus` | 对应页面、菜单或功能入口 |
| `related_systems` | 涉及的系统名称 |
| `urls` | 有业务价值的链接 |
| `resolution_status` | 原始处理结果 |
| `resolution_status_normalized` | 标准化状态 |
| `business_keywords` | WOM、销售订单、任务令等关键词 |
| `removed_noise` | 被删除的噪声类别 |
| `quality_flags` | 数据质量风险 |
| `clean_text` | 最终清洗后的完整文本 |
| `summary` | 一句话知识摘要 |

---

## 5. 处理原则

### 5.1 业务信息优先

以下内容默认为高价值信息，不应误删：

- 权限名称
- 角色名称
- 菜单名称
- 页面名称
- 功能按钮名称
- 系统名称
- 产品名称
- 错误码
- 业务对象
- URL
- 申请路径
- 操作步骤
- 限制条件
- 处理状态

例如：

```text
订单处理专员
WOM 变更任务令_计划员
WOM 创建非标任务令_计划员
销售订单发运
销售订单退货
CBG订单信息查询
```

即使这些内容只有一行，也必须保留。

### 5.2 可解释删除

所有删除操作应当可以归类和追踪。

例如：

```json
{
  "removed_noise": [
    "html_comment",
    "closing_template",
    "duplicate_english_template",
    "empty_marker"
  ]
}
```

不建议直接覆盖原始数据。应保留：

- 原始文本
- 清洗后文本
- 删除噪声类型
- 清洗规则版本

### 5.3 规则优先，模型辅助

优先使用确定性规则处理：

- HTML 标签
- 系统注释
- 固定模板话术
- URL
- 字段标题
- 状态映射
- 空白字符

模型或语义判断只应用于：

- 判断一段话属于 Cause 还是 Solution
- 从 Solution 中识别角色名称
- 判断“问题原因”实际是否为用户诉求
- 生成摘要
- 判断内容是否信息不足

---

## 6. 降噪处理流程

### Step 1：保存原始数据

为每条记录保留：

```json
{
  "raw_html": "...",
  "source": "itsm",
  "rule_version": "1.0.0"
}
```

严禁只保存清洗结果。

---

### Step 2：HTML 预处理

处理以下 HTML 内容：

#### 删除

- HTML 注释
- `script`
- `style`
- 无业务意义的 `div`
- 图片标签本身
- 空标签
- 纯样式属性
- `font-size`
- `background-color`
- `padding`
- `margin`

删除示例：

```html
<!-- for WeLink copy-->
<img src="..." alt="" />
<div style="margin:5px;padding:5px;">
```

#### 转换

将结构标签转换为换行：

```text
<p>      → 段落
<br>     → 换行
<div>    → 段落边界
<li>     → 列表项
```

#### 实体解码

统一处理：

```text
&nbsp;  → 空格
&amp;   → &
&lt;    → <
&gt;    → >
```

#### 注意事项

图片标签可以删除，但以下情况要保留图片相关信息：

- 图片具有有意义的 `alt`
- 图片是操作截图
- 图片 URL 本身需要用于追溯

推荐转换为：

```json
{
  "attachment_present": true,
  "attachment_urls": ["..."]
}
```

不要把长图片 URL 混入最终知识正文。

---

### Step 3：文本标准化

统一以下字符：

#### 空格

- 连续多个空格合并为一个
- 中文与标点之间无意义空格删除
- 行首和行尾空格删除
- `\r\n`、`\r` 统一为 `\n`
- 连续三行以上空行压缩为一行

#### 标点

建议统一：

```text
： :  → ：
； ;  → ；
， ,  → ，
```

URL 内部标点不得替换。

#### 大小写

状态词可以转为小写后匹配，但业务字段保留原始大小写：

```text
Resolved
resolved
RESOLVED
```

统一识别为：

```text
resolved
```

但角色名：

```text
WOM 创建非标任务令_计划员
```

必须保留原始大小写。

---

### Step 4：字段分段

识别以下字段标题：

#### 问题原因

```regex
问题原因\s*(?:\(Cause\))?\s*[：:]
原因\s*[：:]
Cause\s*[：:]
```

#### 解决方案

```regex
解决方案\s*(?:\(Solution\))?\s*[：:]
处理方案\s*[：:]
Solution\s*[：:]
```

#### 处理结果

```regex
处理结果\s*(?:\(Resolved\s*or\s*not\))?\s*[：:]
解决结果\s*[：:]
Resolved\s*or\s*not\s*[：:]
```

字段提取规则：

1. 从字段标题后开始提取
2. 到下一个字段标题前结束
3. 同一字段出现多次时，不直接覆盖
4. 多个片段按原顺序合并
5. URL 单独提取，但保留其字段归属

例如：

```text
解决方案：
履行销售订单页面已切换到新系统
对应的菜单是：
销售订单发运、销售订单退货
https://...
权限要申请：
订单处理专员
```

应整体归入 Solution，而不是只取第一行。

---

### Step 5：固定模板降噪

以下属于典型结案模板，应从知识正文中删除：

```text
您好！您的问题已解决，系统已提供7*24小时在线服务……
如果您后续遇到问题，可以点击系统右侧“客服”按钮……
谢谢！
```

英文版本同样删除：

```text
Hello! Your problem has been solved.
The system has provided 24/7 online service.
If you encounter a problem, click the Customer Service button...
Thank you!
```

以及：

```text
Dear user, the system has provided 24*7h online Customer-Service...
```

#### 模板删除策略

不要只依赖完全匹配。使用三层规则：

##### 第一层：精确模板哈希

对已知模板标准化后计算哈希，完全一致则删除。

##### 第二层：关键词组合匹配

当一段同时包含以下多个关键词时，可判定为结案模板：

中文关键词：

```text
问题已解决
7*24小时
在线服务
客服按钮
智能机器人
人工客服
后续遇到问题
谢谢
```

英文关键词：

```text
problem has been solved
24/7 online service
Customer Service button
intelligent robot
manual customer service
Thank you
```

建议至少命中三个关键短语。

##### 第三层：相似度匹配

对模板做字符或语义相似度计算。

建议阈值：

```text
字符相似度 >= 0.82
或
语义相似度 >= 0.90
```

当相似度处于灰区时，不删除，添加质量标记：

```json
{
  "quality_flags": [
    "suspected_closing_template"
  ]
}
```

#### 防止误删

以下内容即使包含“客服”也不能删除：

```text
需要申请客服管理员角色
客服按钮无法显示
人工客服工作台权限不足
```

模板识别必须针对完整句群，而不是仅匹配单个词。

---

### Step 6：无意义内容清理

删除单独出现且不提供业务信息的内容：

```text
###
#
OK
ok
Resolved
resolved
已解决
完成
-
--
无
N/A
```

但要区分字段语境。

例如：

```text
处理结果：Resolved
```

不能完全丢弃，应转换为结构化状态：

```json
{
  "resolution_status": "Resolved",
  "resolution_status_normalized": "resolved"
}
```

然后从 `clean_text` 正文中省略或规范化为：

```text
处理状态：已解决
```

#### 单字符和占位符规则

可删除：

```regex
^[#\-_*.\s]+$
```

可标记为空值：

```regex
^(无|暂无|未知|NA|N/A|null|none)$
```

---

### Step 7：处理状态标准化

建议统一为以下枚举：

```text
resolved
unresolved
partially_resolved
pending_user
pending_system
unknown
```

映射规则：

| 原始值 | 标准值 |
|---|---|
| Resolved | resolved |
| OK | resolved |
| 已解决 | resolved |
| 完成 | resolved |
| 未解决 | unresolved |
| 处理中 | pending_system |
| 等待用户反馈 | pending_user |
| 部分解决 | partially_resolved |
| 空值 | unknown |

注意：

`OK` 单独作为正文时属于低价值信息，但位于“处理结果”字段中可以映射为 `resolved`。

---

### Step 8：权限和角色提取

重点识别以下表达：

```text
权限要申请：订单处理专员
可以申请此权限：CBG订单信息查询
可申请角色：WOM 变更任务令_计划员
需要这个权限：WOM 变更任务令_计划员
解决方案：WOM 创建非标任务令_计划员
```

触发词包括：

```text
申请权限
申请角色
需要权限
需要角色
对应权限
对应角色
可申请
权限要申请
角色为
权限为
```

#### 角色提取规则

优先级：

1. 触发词后的同一行文本
2. Solution 中独立成行的业务名称
3. 含固定角色格式的文本
4. 词典匹配
5. 模型辅助识别

可识别的角色格式示例：

```regex
(?:WOM|CBG|ERP|OMS|SO)\s*[^\n，。；:：]{2,50}
```

但不能只依赖正则，因为：

```text
订单处理专员
```

不含系统前缀。

推荐维护角色词典：

```json
[
  "订单处理专员",
  "CBG订单信息查询",
  "WOM 变更任务令_计划员",
  "WOM 创建非标任务令_计划员"
]
```

#### 去重

角色名称去除：

- 首尾空格
- 多余冒号
- 尾部句号
- 重复出现

保留角色原始名称，不随意改写下划线和空格。

---

### Step 9：菜单和功能提取

识别触发词：

```text
菜单是
对应菜单
页面是
功能入口
按钮
进入
打开
切换到
```

示例：

```text
对应的菜单是：销售订单发运、销售订单退货
```

输出：

```json
{
  "related_menus": [
    "销售订单发运",
    "销售订单退货"
  ]
}
```

分隔符支持：

```text
、
，
,
；
;
/
换行
```

但包含 `/` 的 URL 不参与菜单拆分。

---

### Step 10：URL 提取和标准化

使用 URL 正则单独提取：

```regex
https?://[^\s<>"']+
```

清理 URL 尾部：

```text
。
，
；
)
]
&nbsp;
```

URL 分类建议：

```text
system_page
permission_application
attachment
documentation
unknown
```

示例：

```json
{
  "urls": [
    {
      "url": "https://erp-pro.saas.huawei.com/#/externalApp@SS_SO/saas/hso/so/searchSO",
      "type": "system_page"
    },
    {
      "url": "https://w3.huawei.com/iauth/#/selectPrivilege?onlyRole=true",
      "type": "permission_application"
    }
  ]
}
```

#### URL 去重

规范化时：

- 保留协议
- 保留 URL fragment，因为单页系统路由可能依赖 `#`
- 删除尾部无意义空格和标点
- 不要擅自删除查询参数
- 图片附件 URL 与业务入口 URL 分开存储

---

### Step 11：Cause 字段语义校正

很多工单中的“问题原因”实际上不是根因，而是用户诉求。

例如：

```text
咨询导入非标任务令按钮的权限
```

它属于：

```text
user_intent：咨询导入非标任务令按钮所需权限
```

并不是真正的系统原因。

因此建议将 Cause 拆成：

```json
{
  "user_intent": "咨询导入非标任务令按钮所需权限",
  "cause_normalized": "用户当前缺少导入非标任务令所需权限",
  "cause_type": "permission_missing"
}
```

推荐原因分类：

```text
permission_missing
permission_inquiry
role_missing
menu_migrated
page_access_denied
function_not_visible
data_query_permission
unknown
```

分类示例：

| 原始内容 | 类型 |
|---|---|
| 页面需要什么权限 | permission_inquiry |
| 当前没有提交权限 | permission_missing |
| 创建变更单权限咨询 | permission_inquiry |
| 页面已切换到新系统 | menu_migrated |
| 页面信息查询权限 | data_query_permission |

若无法确定，不得编造根因，使用：

```text
unknown
```

---

### Step 12：Solution 重写规则

Solution 的标准化应做到：

- 保留事实
- 删除口语重复
- 合并分散句子
- 明确权限、菜单和入口
- 不新增原文不存在的信息
- 不将推测写成事实

推荐输出句式：

```text
申请角色“订单处理专员”，并通过“销售订单发运”或“销售订单退货”菜单进入新系统页面。
```

或者结构化表达：

```text
所需权限：订单处理专员
相关菜单：销售订单发运、销售订单退货
系统入口：https://...
```

对于训练数据或知识库，推荐结构化表达，避免过度润色。

---

## 7. 规则优先级

规则执行顺序必须固定：

```text
1. 原始数据留存
2. HTML 解析
3. 注释和样式移除
4. HTML 实体解码
5. 段落和换行恢复
6. 字段标题识别
7. URL 提取
8. 固定模板识别
9. 无意义占位符删除
10. Cause、Solution、Result 分段
11. 权限、角色、菜单提取
12. 状态标准化
13. 文本合并和去重
14. 摘要生成
15. 质量校验
```

以下顺序是错误的：

```text
先删除所有短句
再识别权限
```

因为角色名称通常很短，容易被误删。

同样，不能先删除所有 URL，再判断其是否为系统入口。

---

## 8. 去重规则

### 8.1 完全重复

标准化空格和标点后完全一致则去重。

### 8.2 包含重复

例如：

```text
WOM 变更任务令_计划员
需要这个权限
WOM 变更任务令_计划员
```

保留一次角色名称。

### 8.3 中英文模板重复

中文和英文结案模板同时存在时，全部删除。

### 8.4 字段间重复

如果角色名同时存在于：

- Solution
- required_roles

结构化字段中保留，在 `clean_text` 中只保留一次。

---

## 9. 质量校验规则

每条记录清洗后执行校验。

### 9.1 必填信息校验

权限咨询案例建议至少包含：

```text
user_intent
required_roles 或 solution_normalized
```

缺失时标记：

```json
{
  "quality_flags": [
    "missing_permission_answer"
  ]
}
```

### 9.2 Cause 和 Solution 混淆

如果 Cause 中出现：

```text
申请角色
解决方法
对应权限
```

可能是字段填写错误，标记：

```text
cause_solution_mixed
```

### 9.3 Solution 过短

如果 Solution 清洗后只有：

```text
OK
Resolved
需要这个权限
```

标记：

```text
solution_too_short
```

### 9.4 只有 URL

如果 Solution 只有 URL，没有说明：

```text
solution_url_without_instruction
```

### 9.5 角色名称不确定

模型推断的角色但原文没有明确触发词时：

```text
inferred_role_requires_review
```

### 9.6 模板残留

清洗后仍包含：

```text
7*24小时
智能机器人
manual customer service
Customer Service button
```

标记：

```text
closing_template_remaining
```

### 9.7 状态冲突

例如：

```text
处理结果：未解决
正文：您的问题已解决
```

应标记：

```text
resolution_status_conflict
```

固定结案模板不能作为实际状态判断的唯一证据。

---

## 10. 输出文本模板

推荐最终 `clean_text` 格式：

```text
问题：{user_intent}
原因：{cause_normalized}
解决方案：{solution_normalized}
所需权限：{required_roles}
相关菜单：{related_menus}
相关链接：{urls}
处理状态：{resolution_status_normalized}
```

空字段不输出。

例如：

```text
问题：咨询履行销售订单页面所需权限。
原因：履行销售订单页面已切换到新系统，用户需申请对应角色。
解决方案：申请“订单处理专员”角色，通过“销售订单发运”或“销售订单退货”菜单进入。
所需权限：订单处理专员
相关菜单：销售订单发运、销售订单退货
相关链接：https://erp-pro.saas.huawei.com/#/externalApp@SS_SO/saas/hso/so/searchSO
处理状态：已解决
```

---

## 11. 五个案例的预期清洗结果

### 案例一

```json
{
  "user_intent": "咨询履行销售订单页面所需权限",
  "cause_normalized": "履行销售订单页面已切换到新系统，需要申请对应角色",
  "solution_normalized": "申请“订单处理专员”角色，通过“销售订单发运”或“销售订单退货”菜单进入新系统页面",
  "required_roles": [
    "订单处理专员"
  ],
  "related_menus": [
    "销售订单发运",
    "销售订单退货"
  ],
  "urls": [
    "https://erp-pro.saas.huawei.com/#/externalApp@SS_SO/saas/hso/so/searchSO"
  ],
  "resolution_status_normalized": "resolved",
  "removed_noise": [
    "html_comment",
    "closing_template"
  ]
}
```

### 案例二

```json
{
  "user_intent": "咨询页面订单信息查询权限",
  "cause_normalized": "用户需要订单信息查询权限",
  "solution_normalized": "申请“CBG订单信息查询”权限",
  "required_roles": [
    "CBG订单信息查询"
  ],
  "resolution_status_normalized": "resolved",
  "removed_noise": [
    "html_comment",
    "closing_template",
    "duplicate_english_template"
  ]
}
```

### 案例三

```json
{
  "user_intent": "申请提交任务令变更所需权限",
  "cause_normalized": "用户当前没有提交任务令变更的权限",
  "solution_normalized": "申请角色“WOM 变更任务令_计划员”",
  "required_roles": [
    "WOM 变更任务令_计划员"
  ],
  "resolution_status_normalized": "resolved",
  "removed_noise": [
    "html_comment",
    "closing_template",
    "low_information_status"
  ]
}
```

### 案例四

```json
{
  "user_intent": "咨询创建变更单所需权限",
  "cause_normalized": "用户需要创建变更单的权限",
  "solution_normalized": "申请角色“WOM 变更任务令_计划员”",
  "required_roles": [
    "WOM 变更任务令_计划员"
  ],
  "resolution_status_normalized": "resolved",
  "removed_noise": [
    "html_comment",
    "closing_template",
    "duplicate_english_template",
    "empty_html_container"
  ]
}
```

### 案例五

```json
{
  "user_intent": "咨询导入非标任务令按钮所需权限",
  "cause_normalized": "用户需要导入非标任务令功能的权限",
  "solution_normalized": "申请角色“WOM 创建非标任务令_计划员”",
  "required_roles": [
    "WOM 创建非标任务令_计划员"
  ],
  "urls": [
    "https://w3.huawei.com/iauth/#/selectPrivilege?onlyRole=true"
  ],
  "resolution_status_normalized": "resolved",
  "removed_noise": [
    "html_comment",
    "image_tag",
    "inline_style",
    "empty_marker",
    "closing_template"
  ]
}
```

---

## 12. 伪代码

```python
def clean_itsm_case(raw_html: str) -> dict:
    result = initialize_result(raw_html)

    # 1. HTML 层清理
    html = remove_script_and_style(raw_html)
    html = remove_html_comments(html)
    html = extract_attachment_metadata(html)
    text = html_to_text_with_linebreaks(html)
    text = decode_html_entities(text)

    # 2. 文本标准化
    text = normalize_unicode(text)
    text = normalize_spaces(text)
    text = normalize_linebreaks(text)

    # 3. 先提取 URL，防止后续清理误伤
    urls = extract_urls(text)
    result["urls"] = classify_urls(urls)

    # 4. 字段切分
    sections = split_sections(
        text,
        headings={
            "cause": CAUSE_PATTERNS,
            "solution": SOLUTION_PATTERNS,
            "result": RESULT_PATTERNS,
        },
    )

    # 5. 模板和噪声清理
    sections = remove_closing_templates(sections)
    sections = remove_empty_markers(sections)
    sections = remove_duplicate_sentences(sections)

    # 6. 业务信息提取
    result["cause_raw"] = sections.get("cause", "")
    result["solution_raw"] = sections.get("solution", "")
    result["resolution_status"] = sections.get("result", "")

    result["user_intent"] = extract_user_intent(result["cause_raw"])
    result["cause_normalized"] = normalize_cause(result["cause_raw"])
    result["required_roles"] = extract_roles(
        result["solution_raw"],
        role_dictionary=ROLE_DICTIONARY,
    )
    result["related_menus"] = extract_menus(result["solution_raw"])
    result["related_systems"] = extract_systems(text)

    result["solution_normalized"] = normalize_solution(
        solution=result["solution_raw"],
        roles=result["required_roles"],
        menus=result["related_menus"],
        urls=result["urls"],
    )

    result["resolution_status_normalized"] = normalize_status(
        result["resolution_status"]
    )

    # 7. 构建最终文本
    result["clean_text"] = build_clean_text(result)
    result["summary"] = build_summary(result)

    # 8. 质量校验
    result["quality_flags"] = validate_result(result)

    return result
```

---

## 13. 批处理流程

```text
读取数据
  ↓
生成唯一记录 ID
  ↓
保存原始 HTML
  ↓
HTML 清理
  ↓
字段识别
  ↓
模板降噪
  ↓
权限、角色、菜单、URL 提取
  ↓
状态标准化
  ↓
文本重组
  ↓
质量校验
  ↓
低置信度记录进入人工复核
  ↓
输出 JSON / CSV / Excel / 数据库
```

批处理时建议分为三个结果集：

```text
accepted
review_required
rejected
```

### accepted

满足以下条件：

- Cause 或用户诉求明确
- Solution 有有效信息
- 权限或角色可明确识别
- 没有状态冲突
- 没有严重模板残留

### review_required

出现以下情况之一：

- 只有链接，没有操作说明
- 角色通过模型推断得到
- 字段严重混乱
- 处理结果相互冲突
- 模板相似度处于灰区
- Solution 信息不足
- 一个案例包含多个无关问题

### rejected

仅在以下情况下使用：

- 空记录
- 纯模板内容
- 纯乱码
- 无任何业务信息
- HTML 解析失败且无法恢复

不要因为字段缺失就直接丢弃，优先进入人工复核。

---

## 14. 配置项

建议将可变化规则放在配置文件中：

```yaml
skill:
  name: itsm-case-noise-reduction
  version: 1.0.0

templates:
  closing_template_similarity_threshold: 0.90
  closing_template_keyword_min_hits: 3

text:
  max_blank_lines: 1
  normalize_punctuation: true
  preserve_role_case: true
  preserve_url_fragment: true

status_mapping:
  resolved:
    - Resolved
    - resolved
    - OK
    - 已解决
    - 完成
  unresolved:
    - Unresolved
    - 未解决
  pending_user:
    - 等待用户
    - 等待用户反馈

quality:
  require_intent: true
  require_solution: true
  flag_solution_shorter_than: 4
  send_inferred_roles_to_review: true
```

---

## 15. 词典设计

至少维护四类词典：

### 角色词典

```json
[
  "订单处理专员",
  "CBG订单信息查询",
  "WOM 变更任务令_计划员",
  "WOM 创建非标任务令_计划员"
]
```

### 菜单词典

```json
[
  "销售订单发运",
  "销售订单退货"
]
```

### 系统词典

```json
[
  "WOM",
  "CBG",
  "ERP",
  "ERP Pro",
  "iAuth"
]
```

### 模板词典

```json
[
  "您好！您的问题已解决，系统已提供7*24小时在线服务",
  "Hello! Your problem has been solved",
  "Dear user, the system has provided 24*7h online Customer-Service"
]
```

词典应支持版本管理和增量更新。

---

## 16. 健壮性要求

实现时必须遵循：

1. HTML 解析失败时降级为正则和纯文本处理。
2. 任意规则异常不得导致整批任务失败。
3. 每条记录单独捕获异常。
4. 原始文本永远保留。
5. URL 提取先于标点标准化。
6. 角色提取先于短文本删除。
7. 固定模板不能只通过单关键词删除。
8. 模型提取结果必须带置信度。
9. 低置信度结果进入人工复核。
10. 每次规则升级记录版本。
11. 支持重新处理历史数据。
12. 输出需要具有幂等性，同一输入和同一规则版本应产生相同结果。
13. 不得根据常识补充原文没有出现的权限名称。
14. 不得把结案模板中的“问题已解决”作为唯一状态证据。
15. 多问题工单应拆分或标记，不得强行合并为一个知识点。

---

## 17. 推荐置信度机制

```json
{
  "confidence": {
    "field_segmentation": 0.99,
    "role_extraction": 0.98,
    "template_removal": 0.97,
    "status_normalization": 0.95,
    "overall": 0.97
  }
}
```

建议规则：

```text
overall >= 0.90        → accepted
0.70 <= overall < 0.90 → review_required
overall < 0.70         → rejected 或人工复核
```

业务关键字段缺失时，即使总体分数高，也必须进入人工复核。

---

## 18. Skill 执行指令

当收到一条或多条 ITSM 案例时：

1. 不直接删除原始内容。
2. 解析 HTML 并保留段落边界。
3. 删除系统注释、样式和无意义标签。
4. 提取 Cause、Solution 和 Resolved 字段。
5. 删除固定结案模板及其中英文重复内容。
6. 删除 `###`、空节点等无业务价值内容。
7. 提取权限、角色、菜单、系统和 URL。
8. 将处理状态映射为统一枚举。
9. 将“问题原因”区分为用户诉求和实际原因。
10. 重组为结构化结果。
11. 对不确定字段添加质量标记，不得猜测。
12. 输出清洗结果、删除噪声类型和质量校验结果。

---

## 19. 禁止事项

禁止执行以下操作：

- 直接使用正则删除全部 HTML 后不恢复段落
- 删除全部短文本
- 删除全部英文
- 删除全部 URL
- 把所有 `Resolved` 字样当作正文
- 根据关键词随意生成不存在的角色
- 把图片 URL 当作业务入口 URL
- 因为存在结案模板就判断问题一定解决
- 将 Cause 和 Solution 简单拼接而不做字段校验
- 清洗后不保留原始记录
- 未记录规则版本
- 对低置信度数据静默输出

---

## 20. 最终验收标准

一条合格的清洗结果应满足：

- HTML 标签和系统样式已清除
- 结案模板已清除
- 中英文重复话术已清除
- 用户诉求清晰
- 权限或角色名称准确
- 菜单和链接被正确提取
- 处理状态已标准化
- 原始信息未被错误补充
- 删除内容可追踪
- 低质量数据被明确标记
- 同一输入重复执行结果一致