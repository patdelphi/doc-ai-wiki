## 变更说明

- [ ] 已说明本次修改的业务范围和不包含的范围。
- [ ] 新功能或修复已先补测试。
- [ ] 数据库写操作使用事务；SQLite 保持 WAL / NORMAL。
- [ ] 外部 API、索引重建或迁移已说明执行与回滚方式。

## 必须通过的检查

- [ ] `python -m ruff check src tests .aipython`
- [ ] `python -m mypy src/retrieval src/pageindex src/quality/service.py`
- [ ] `python -m pytest tests --maxfail=1 -q`
- [ ] `python -m build`

## 文档与恢复

- [ ] 相关 `Docs/`、README、changelog 已同步。
- [ ] 已记录索引版本、备份位置、验证门禁和恢复命令。
