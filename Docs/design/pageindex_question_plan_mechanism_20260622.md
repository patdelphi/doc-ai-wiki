# PageIndex Question Plan 机制设计

> 时间：2026-06-22
> 范围：`src/pageindex`、`templates/pageindex`、`tests/unit`
> 目标：让 PageIndex 先理解用户到底要“判断、列举、定位、总结还是比较”，再生成答案，避免把所有问题都当成命题真假判断。

## 背景问题

当前 PageIndex 已能定位证据，但回答层容易混淆两类需求：

- 用户问“心脏病吃阿胶有好处吗”：需要判断证据是否支持命题。
- 用户问“阿胶有哪些质量检测方法”：需要从证据中提炼方法清单，不应判断问题真假。

如果用 Python 关键词写死路由，会快速变成脆弱规则库：医学问题、质量检测问题、工艺问题、对比问题都会不断追加特例。既然 Web 版本已经会调用 LLM，正确方向是让 LLM 生成结构化 Question Plan，Python 负责校验和执行约束。

## 核心机制

新增 `QuestionPlan` 作为回答前的结构化决策层。它不是最终答案，也不是模板；它决定“这道题应该怎么答”。

建议 JSON 结构：

```json
{
  "question_type": "information_extraction",
  "answer_strategy": "从证据中列举质量检测方法，按类别归纳。",
  "target": "阿胶质量检测方法",
  "claim": "",
  "required_output": ["结论", "方法清单", "依据", "来源", "不确定点"],
  "needs_evidence_relation": false,
  "insufficient_evidence_policy": "如果证据只覆盖部分方法，明确说明只代表当前知识库。"
}
```

`question_type` 允许值：

- `information_extraction`：列举、定义、方法、步骤、特点等信息抽取问题。
- `claim_judgement`：判断某个命题是否成立、是否有好处、能否治疗、是否支持。
- `source_location`：只找出处、位置、原文。
- `comparison`：比较多个对象、方法或观点。
- `summary`：概括某主题。
- `unknown`：无法稳定判断时的保守兜底。

## 数据流

1. 页面提问入口调用 `PageIndexService.ask_knowledge_base_question()`，检索范围是当前知识库下所有已构建 PageIndex 的文档，不是单一文档。
2. 服务层通过 `_list_index_records(knowledge_base_id)` 读取当前知识库下全部 `pageindex_indexes` 记录。
3. `_answer_knowledge_base_with_reasoning_or_fallback()` 逐个文档执行 PageIndex/RAG 召回，并合并多文档证据。
4. LLM 根据“用户问题 + 证据预览”生成 `QuestionPlan`。
5. Python 校验 `QuestionPlan` 字段，不合法则降级为 `unknown`，不再用关键词改写意图。
6. 回答模板同时接收 `question_plan`、证据、结构上下文、证据关系和引用规则。
7. LLM 按模板生成最终答案。
8. Python 保存问答历史、证据、`debug.question_plan` 和导出调试信息。

## 检索范围确认

当前 PageIndex 页面走知识库级检索：

- UI 调用：`pageindex_service.ask_knowledge_base_question(...)`
- 知识库索引读取：`_list_index_records(knowledge_base_id)`
- 多文档聚合：`_answer_knowledge_base_with_reasoning_or_fallback(records, question, ...)`

`ask_question(knowledge_base_id, doc_uid, question, ...)` 仍保留为单文档服务方法，但当前 PageIndex 页面提问不走该入口。

截至 2026-06-23，`default` 知识库下有两个已构建 PageIndex 文档：

- `阿胶历史文化通典_default`
- `阿胶学术论文全集_default`

已验证的多文档命中历史案例：

| query_id | 问题 | 命中文档数 | 证据数 |
| --- | --- | ---: | ---: |
| `piq_09d75d5788ee` | 阿胶对感冒有一定缓解作用 | 2 | 4 |
| `piq_14f55f1319ed` | 心脏病吃阿胶有好处吗 | 2 | 5 |
| `piq_814bd5837669` | 阿胶制作工艺有什么特点 | 2 | 10 |

## 与模板的区别

Question Plan 解决“要答什么、按什么策略答”；模板解决“用什么格式、约束和语气答”。

- Plan：每个问题动态生成。
- 模板：可配置、可复用，适合不同业务场景。
- 模板可以引用 `{question_plan}`，但不负责自己猜问题类型。

## 内置模板梯度

PageIndex 内置模板按“宽松到严谨、普适到专业”设计，不在 Python 中写死医学或行业规则：

| 模板 ID | 场景 | 答案策略 |
| --- | --- | --- |
| `general_summary` | 快速概览、主题摘要、背景梳理 | 不做强命题审判，先给材料概览和要点 |
| `balanced_qa` | 大多数普通问答 | 直接回答问题，同时说明证据能说明什么和不能说明什么 |
| `strict_qa` | 严谨问答、命题判断 | 强制区分直接支持、反对、间接相关和证据不足 |
| `evidence_audit_qa` | 证据审查、评估材料是否足够 | 明确写出证据不能证明什么、哪些地方不能外推 |
| `medical_safety_qa` | 医学疗效、安全性、禁忌、人群边界 | 从严区分临床证据、理论语境、风险边界和证据不足 |
| `source_locator` | 只找出处和原文位置 | 只输出定位和引用，不生成额外结论 |

医学模板只提供安全导向的回答约束，不把外部医学指南或常识伪装成当前知识库证据。不同 LLM API 返回格式不固定，因此模板只约束答案目标和字段倾向，导出层继续做通用结构化渲染。

## 回退策略

LLM 不可用或 plan 生成失败时：

- 不做硬编码问题路由。
- 使用 `unknown` plan。
- 本地答案保持保守：说明只基于命中证据，不能替代完整推理。

这样不会把“质量检测方法有哪些”误判成命题真假，但在无 LLM 场景也不会伪造列表。

## Markdown 导出策略

PageIndex 导出 Markdown 不能依赖固定 LLM 输出 schema，因为不同模型和 API 可能返回不同字段名、不同语言或嵌套结构。

当前导出层采用通用容错策略：

- 如果答案是普通文本，原样输出。
- 如果答案是 JSON 或 Python dict 字符串，解析为结构化对象后渲染为 Markdown 小节。
- `结论`、`证据判断`、`依据`、`来源`、`不确定点` 仅作为展示排序优先级，不作为强制 schema。
- 未知字段、英文字段、额外字段全部保留并渲染。
- 列表、列表内嵌套 dict、dict 内嵌套 list 采用递归 Markdown 渲染，避免输出原始 Python 字符串。
- 解析失败时回退为原文，不影响导出。

## 第一批优化计划

1. 新增 `src/pageindex/question_plan.py`，负责 plan schema、默认值、prompt 构建和归一化。
2. 在最终 LLM 回答前生成 `QuestionPlan`。
3. 在 PageIndex 模板中加入 `{question_plan}` 变量。
4. 移除 Python 中“有哪些/方法/步骤”等硬编码信息抽取路由。
5. 用假 LLM 补单测，覆盖列举类问题会把 `information_extraction` plan 传给最终回答模板。

## 验收标准

- “阿胶有哪些质量检测方法”进入 `information_extraction` plan，最终提示词要求列举方法，而不是判断真假。
- “心脏病吃阿胶有好处吗”进入 `claim_judgement` plan，最终提示词要求判断证据支持关系。
- 自定义 PageIndex 模板可使用 `{question_plan}`。
- LLM plan 失败时不会抛出页面错误，使用 `unknown` 兜底。
- 导出 Markdown 不出现原始 dict 字符串，且不因结构化答案渲染丢失证据。
- 单测通过，且测试不调用外部 API。
