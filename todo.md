# Todo

## 当前任务

- 收尾 `"全文检索兼容修复"`，确保部分 SQLite / FTS5 环境下 `MATCH ?` 失败时，会自动回退到 `LIKE`，不阻断检索与 AI 质检链路。

## 当前状态

- `src/retrieval/service.py` 已加入 `FTS5 -> LIKE` 兜底逻辑。
- `tests/unit/test_retrieval.py` 已补充回归测试，覆盖 `MATCH` 参数报错时的降级路径。
- 已执行 `python -m pytest "tests/unit/test_retrieval.py" -q`，结果 `1 passed`。
- 已检查 `src/retrieval/service.py` 与 `tests/unit/test_retrieval.py` 诊断，当前无新增报错。
- 现有 `"todo.md"` 中大量历史阶段任务与本轮实际工作不一致，已从当前清单移除。

## 下一步

1. 复核本轮变更范围
- 当前应优先聚焦 `src/retrieval/service.py`、`tests/unit/test_retrieval.py`、`todo.md`、`chat_history.md`。

2. 确认是否进入提交前收口
- 如需继续，可下一步整理本轮变更摘要，等待你确认是否执行 `git commit`。

## 暂不处理

- `"Docs/document_ingest_quality_20260501_111145_0000.csv"`
- `"Docs/document_ingest_quality_20260501_111458_0000.csv"`
- `"index/chroma/chroma.sqlite3"`
- `"todo - 副本.md"`（按你的要求保留，不纳入本轮处理）

## 说明

- 上述文件看起来更像运行产物、环境数据或手动保留副本，本轮先不纳入“当前任务”处理。
- 如需继续清理这些文件，我会先列出影响，再等你确认。
