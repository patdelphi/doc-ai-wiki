# PageIndex 与 AI 质检质量收口执行结果

## 执行基线

- Worktree：`C:\Users\patde\Documents\GitHub\doc-ai-wiki-worktrees\retrieval-pageindex-optimization`
- 分支：`codex/retrieval-pageindex-optimization`
- 基线提交：`28acdef`
- 活动数据库：`index/app.db`
- 模型：`qwen3.7-plus`
- Embedding：`Qwen3-Embedding-8B`
- Rerank：`Qwen3-Reranker-8B`

## 主要优化

1. PageIndex 按回答模板校验必填章节，结构化 JSON 或 Python dict 统一渲染为 Markdown。
2. 最终回答失败或发现库外常识时，保存失败阶段、原因和回答契约，并返回证据限定的终态答案。
3. 医学安全降级答案只保留直接相关的配料、用法或禁忌证据，过滤重复片段和弱相关背景。
4. AI 质检拆分复合 Claim 并继承省略主体，区分全称断言、范围否定、安全边界和证据缺口。
5. “不是唯一”不再误命中 G002 唯一化规则；没有其他产地证据时保持 `needs_review/medium`。
6. 严格 Claim 的理由由证据关系和范围约束生成，不再采用模型补充的库外医学推断。
7. PageIndex 单文档和多文档路径均记录 `answer_contract`、`degraded_stage` 与 `llm_error`。

## 完整真实验收

完整批次共 10 条，全部调用真实模型、检索和重排服务，并逐条从 SQLite 回读。

### AI 质检：6/6 通过

| 场景 | 记录 ID | 结果 | 风险 | Claim 数 |
| --- | --- | --- | --- | --- |
| 安全边界 | `chkres_ecc2df582e97` | passed | low | 2 |
| 证据缺口 | `chkres_0472f8f8d6b6` | needs_review | medium | 1 |
| 产地范围否定 | `chkres_85dc9162990a` | needs_review | medium | 2 |
| 普遍人群与极端剂量 | `chkres_2cbf3aa18087` | rejected | high | 1 |
| 产品配料与不限量食用 | `chkres_21d882d8b61b` | rejected | high | 2 |
| 优效与替代治疗 | `chkres_efe254c42c5f` | rejected | high | 2 |

理由收口后的最终专项复测：

- `chkres_9675f808e8ad`：极端剂量，`rejected/high`，已落库。
- `chkres_36c59bd0f595`：优效与替代治疗，`rejected/high`，已落库。
- `chkres_fc5a7fb74fc0`：产品不限量食用，`rejected/high`；事实 Claim 保持 `verified/low`，风险 Claim 使用证据范围理由，已落库。

### PageIndex：4/4 通过

| 场景 | 记录 ID | 证据追溯 | 章节 | 结果 |
| --- | --- | --- | --- | --- |
| 传统、机制、动物与临床证据分层 | `piq_2f5ed935b4ce` | 8/8 | 完整 | 通过 |
| 东阿道地性与唯一性 | `piq_926b0d9368ac` | 8/8 | 完整 | 通过 |
| 产品配料与特定人群风险 | `piq_e39578b09981` | 8/8 | 完整 | 证据限定降级后通过 |
| 烊化、配伍与长期大剂量边界 | `piq_a24e7066e939` | 8/8 | 完整 | 通过 |

产品风险最终专项复测 `piq_dac3a941ae77` 同样通过：只确认配料表和传统配方事实，明确说明当前证据不能证明特定人群、长期使用和剂量上限下的安全性。

## 数据库与运行状态

- 最终计数：`pageindex_query_history=42`，`quality_checks=74`。
- 项目连接验证：`journal_mode=wal`，`synchronous=1`（NORMAL）。
- 前端：`http://127.0.0.1:7860/`，HTTP 200。
- 后端：`http://127.0.0.1:8000/health`，HTTP 200。
- 浏览器只读验证已加载登录页；登录后的切页和异常终态由自动化测试覆盖，本轮未提交登录凭据。

## 自动化验证

- 完整 Pytest：`482 passed, 6 warnings`。
- Ruff：通过。
- Mypy：4 个受影响源文件通过。
- 验收脚本 `py_compile`：通过。

## 残余风险

- 当前医学安全答案采用证据优先策略；知识库没有特定人群、剂量或长期随访证据时，会明确降级而不是补充外部医学常识。
- 浏览器新会话没有登录态，因此未进行带凭据的人工页面点击；已有登录态恢复、切页和运行终态回归测试均已通过。
- 核心实现和本报告初版已提交为 `801e845`，分支已推送至 `origin/codex/retrieval-pageindex-optimization`。
