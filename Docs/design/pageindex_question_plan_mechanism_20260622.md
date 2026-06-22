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

1. PageIndex/RAG 先召回候选证据。
2. LLM 根据“用户问题 + 证据预览”生成 `QuestionPlan`。
3. Python 校验 `QuestionPlan` 字段，不合法则降级为 `unknown`，不再用关键词改写意图。
4. 回答模板同时接收 `question_plan`、证据、结构上下文、证据关系和引用规则。
5. LLM 按模板生成最终答案。
6. Python 保存问答历史、引用和 debug 信息。

## 与模板的区别

Question Plan 解决“要答什么、按什么策略答”；模板解决“用什么格式、约束和语气答”。

- Plan：每个问题动态生成。
- 模板：可配置、可复用，适合不同业务场景。
- 模板可以引用 `{question_plan}`，但不负责自己猜问题类型。

## 回退策略

LLM 不可用或 plan 生成失败时：

- 不做硬编码问题路由。
- 使用 `unknown` plan。
- 本地答案保持保守：说明只基于命中证据，不能替代完整推理。

这样不会把“质量检测方法有哪些”误判成命题真假，但在无 LLM 场景也不会伪造列表。

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
- 单测通过，且测试不调用外部 API。
