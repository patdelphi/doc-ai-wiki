# AI质检逻辑回退到 683151e 之前的详细计划

## 目标

按 `683151e` 之前的实现恢复 AI 质检逻辑，同时保留已经独立演进的 PageIndex 逻辑、PageIndex 模板管理、PageIndex 检索增强和当前默认知识库修复。

## 关键假设

1. `683151e` 是第一次实质性改动 AI 质检核心判断逻辑的提交。
2. 需要恢复的是 AI 质检模块的旧检索、证据判断、结果组织逻辑，而不是回退整个仓库。
3. PageIndex 与 AI 质检现在应当解耦：PageIndex 可以继续使用新的 QuestionPlan、模板、迭代推理、query expansion 等能力；AI 质检恢复旧逻辑。
4. `3a324ef` 之后新增的 `query_normalizer` 可能已被 PageIndex 使用，因此不能粗暴删除，只能从 AI 质检调用链中移除。
5. 当前默认知识库下拉修复应保留，因为这是独立 UI 问题，不属于 AI 质检逻辑回退。

## 分支策略

新建安全分支：`codex/revert-ai-quality-before-683151e`

理由：

- 这是选择性回退，不适合直接在 `dev` 上试错。
- 需要同时保留 PageIndex 新逻辑，不能用 `git revert` 或 `git reset` 做整体回退。
- 分支便于比较、验证和必要时丢弃。

## 完成标准

1. AI 质检核心逻辑恢复到 `683151e^` 的行为边界。
2. PageIndex 相关功能文件不被回退。
3. 默认知识库 `default` 下拉仍然默认选中。
4. AI 质检结果渲染样式若确实被共享改动破坏，恢复旧样式；若无证据，不改 UI 渲染。
5. 删除或隔离本轮错误评估产生的无效文档/测试入口，避免继续误导。
6. 聚焦测试通过，并补充至少一个防回归测试。
7. 执行完成后暂停，等待你确认是否 commit。

## 执行步骤

### 1. 建分支并确认基线

- 检查当前 `git status --short` 必须只包含计划文档和 chat history，不能有未知业务改动。
- 创建分支 `codex/revert-ai-quality-before-683151e`。
- 记录当前 HEAD：`bde6cdc`。
- 确认 `683151e^` 的实际提交号。

### 2. 精确定位 AI 质检改动范围

对比以下提交：

- `683151e^..683151e`
- `683151e..3a324ef`
- `963c08a`
- `9926910`

重点文件：

- `src/quality/service.py`
- `src/quality/verdicts.py`
- `tests/unit/test_verdicts.py`
- `tests/unit/test_quality_service.py`
- `src/retrieval/query_normalizer.py`
- `src/ui/viewmodels.py`
- `src/ui/pages.py`

判断规则：

- AI 质检核心逻辑改动：回退。
- PageIndex 专用逻辑：保留。
- 共享 UI 改动：只在确认影响 AI 质检样式时局部恢复。
- 默认知识库修复：保留。

### 3. 先写防回归测试

新增或修改测试，覆盖：

1. AI 质检在有证据时沿用旧 verified/unsupported/uncertain 判定路径。
2. AI 质检不调用 PageIndex 的 QuestionPlan。
3. AI 质检不依赖 PageIndex 模板。
4. AI 质检不使用后续为 PageIndex 做的 query expansion 作为核心判断入口。
5. `default` 知识库在未登录/空 session 下仍默认选中。

### 4. 恢复 AI 质检核心逻辑

- 从 `683151e^` 提取 `src/quality/service.py` 的 AI 质检旧实现。
- 手工合并到当前文件，保留当前仍需要的接口签名和外部调用入口。
- 移除 AI 质检对 `src.quality.verdicts` 的依赖。
- 移除 AI 质检对 `query_normalizer` 的核心路由依赖。
- 保留事务、异常处理和现有 DB 写入结构。

### 5. 清理错误引入的 AI 质检规则文件

- 如果 `src/quality/verdicts.py` 只服务于错误的新 AI 质检逻辑，则删除。
- 如果被 PageIndex 或其他模块引用，则保留但从 AI 质检路径移除。
- 同步删除或调整对应错误测试。

### 6. 检查并恢复 AI 质检渲染样式

- 对比 `683151e^` 与当前 `src/ui/viewmodels.py`。
- 只检查 AI 质检结果渲染相关函数。
- 如果当前渲染确实偏离旧样式，局部恢复。
- 不改 PageIndex preview / markdown 渲染。

### 7. 文档与 todo 同步

- 更新 `todo.md`：标记“AI 质检错误共用 PageIndex 逻辑，需要恢复旧逻辑并解耦”。
- 处理 `Docs/claim_evaluation_run_20260623.md`：标记为无效评估或移除，避免作为后续优化依据。
- 文档统一 UTF-8 BOM + CRLF。

### 8. 验证

先跑聚焦测试：

- `python -m pytest tests/unit/test_quality_service.py -q`
- `python -m pytest tests/unit/test_ui.py -q`
- 如涉及 PageIndex 共享文件，再跑 PageIndex 相关聚焦测试。

再做静态检查：

- `rg "verdicts|QuestionPlan|query_normalizer" src tests`
- 确认 AI 质检路径没有错误依赖，PageIndex 路径仍可使用新能力。

### 9. 暂停确认

完成后汇报：

- 改了哪些文件。
- 哪些测试通过。
- AI 质检恢复到哪个基线。
- PageIndex 哪些逻辑明确保留。
- 未自动 commit，等待你确认。