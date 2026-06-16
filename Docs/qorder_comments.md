我来对这个 doc-ai-wiki 项目进行全面审查。首先让我了解项目的整体结构和关键信息。


让我系统地读取各核心模块的代码。


项目结构已经清晰了。现在我并行启动多个审查任务，覆盖各核心模块。


审查完成，下面是汇总报告。


## doc-ai-wiki 全面代码审查报告

共发现 **32 个问题**，其中 5 个严重、9 个高危、10 个中危、8 个低危。以下按优先级排列：

---

### 一、严重问题 (Critical) — 需立即修复

**C1. 客户端会话可被伪造，实现权限提升**
- 文件：[pages.py](src/ui/pages.py:122) / [pages.py](src/ui/pages.py:5056)
- `gr.BrowserState` 的 `secret` 硬编码在源码中，会话包含 `is_admin`、`permissions` 等字段，可通过 DevTools 直接篡改实现权限提升。
- **修复**：改用服务端 session 存储（session ID + 数据库 session store），客户端仅保存不可猜测的 token。

**C2. `change_password` 无旧密码验证，IDOR 漏洞**
- 文件：[service.py](src/auth/service.py:165)
- 已认证用户可通过构造 `user_id` 修改任意用户密码，且无 try/except 保护。
- **修复**：增加旧密码参数并验证；添加异常处理。

**C3. LLM 返回结果未做枚举校验**
- 文件：[llm.py](src/ai/llm.py:296)
- `verdict`、`risk_level`、`confidence` 等字段未校验合法值，任意字符串直接写入数据库，污染数据语义。
- **修复**：在 `_parse_llm_result` 中添加枚举白名单校验和 `confidence` 范围约束 `[0.0, 1.0]`。

**C4. IngestService 创建独立 VectorStore，ChromaDB 数据损坏风险**
- 文件：[service.py](src/ingest/service.py:33)
- 两个 `PersistentClient` 指向同一持久化目录，并发写入时可能导致数据损坏。
- **修复**：`IngestService` 接受外部注入 `vector_store`，与 `app.py` 共享同一实例。

**C5. `register_document` 路径遍历漏洞**
- 文件：[service.py](src/ingest/service.py:100)
- 用户可提交系统任意路径，在重定位校验之前已读取文件内容。
- **修复**：读取前校验 `file_path.resolve()` 是否在 `input_root` 范围内。

---

### 二、高危问题 (High)

**H1. `delete_user` 无异常保护** — [service.py](src/auth/service.py:195)
多条 DELETE 无 try/except，可能导致用户表和权限表数据不一致。

**H2. 会话恢复不检查 `is_active` 状态** — [service.py](src/auth/service.py:119)
`get_user_by_id` 不检查激活状态，被禁用用户刷新页面即可恢复登录态。

**H3. 遗留密码验证时序攻击** — [service.py](src/auth/service.py:87)
bcrypt 降级和 SHA256 路径使用 `==` 而非 `hmac.compare_digest()`。

**H4. 硬编码默认管理员密码 "admin"** — [connection.py](src/db/connection.py:272)
建议首次启动生成随机密码或强制修改。

**H5. Rerank 客户端无异常处理** — [rerank.py](src/ai/rerank.py:55)
`httpx.post()` 无保护，网络错误直接中断整个质检流程。

**H6. API 层 `review_action` 未做枚举校验** — [models.py](src/common/models.py:84)
`ReviewSubmitRequest.review_action` 是无约束的 `str`，可写入任意审核状态。

**H7. 向量检索未按 `knowledge_base_id` 过滤** — [service.py](src/retrieval/service.py:94)
向量搜索未传递知识库 ID，可能跨库泄漏数据。全文检索则正确做了过滤。

**H8. 全局异常处理缺失** — [app.py](src/app.py:258)
仅注册了 `AppError` handler，未预期异常返回完整堆栈，暴露内部路径和表结构。

**H9. 空 `knowledge_base_id` 跳过权限检查** — [app.py](src/app.py:132)
非 admin 用户不传 KB ID 时可搜索所有知识库。

---

### 三、中危问题 (Medium)

| # | 问题 | 文件 | 描述 |
|---|------|------|------|
| M1 | register_user TOCTOU 竞态 | [service.py](src/auth/service.py:144) | SELECT/INSERT 间无锁，泄露 DB 异常文本 |
| M2 | User 类暴露 password_hash | [service.py](src/auth/service.py:30) | 增加敏感数据泄露攻击面 |
| M3 | 空输入导致质检垃圾数据 | [service.py](src/quality/service.py:142) | `max()` 空序列崩溃 |
| M4 | `except Exception` 过宽 | [llm.py](src/ai/llm.py:146) | 吞掉 KeyboardInterrupt，可能泄露 API Key |
| M5 | 模板 `.format()` 花括号崩溃 | [llm.py](src/ai/llm.py:287) | 自定义模板含 JSON 示例时 KeyError |
| M6 | Schema 缺少关键索引 | [schema.py](src/db/schema.py) | check_id、review_status 等高频列无索引 |
| M7 | N+1 查询 (201 次) | [repositories.py](src/db/repositories.py:679) | limit=200 时每页 201 次查询 |
| M8 | SQLite 连接未关闭 | [service.py](src/retrieval/service.py:59) | `with` 仅管事务不管连接关闭 |
| M9 | 分页 HTML 存在 XSS 风险 | [page_helpers.py](src/ui/page_helpers.py:282) | page_info 未 escape |
| M10 | `_do_register` 无异常处理 | [pages.py](src/ui/pages.py:5944) | 注册失败时泄露堆栈 |

---

### 四、低危问题 (Low)

| # | 问题 | 文件 |
|---|------|------|
| L1 | LLM 缺少比较型检测 | [llm.py](src/ai/llm.py:311) |
| L2 | LLM 无连接复用 | [llm.py](src/ai/llm.py:121) |
| L3 | 密码策略薄弱 | [service.py](src/auth/service.py:59) |
| L4 | KB ID 允许中文目录名 | [service.py](src/knowledge_base/service.py:224) |
| L5 | pages.py 6219 行 | [pages.py](src/ui/pages.py) |
| L6 | UI_CSS 重复赋值 | [css.py](src/ui/css.py:3) |
| L7 | exporters 等模块无测试 | [tests/](tests/) |
| L8 | conftest.py 缺少共享 fixture | [conftest.py](tests/conftest.py) |

---

### 五、修复优先级建议

**第一优先级（安全类，立即处理）：**
1. C1 — 服务端 session 替代客户端 BrowserState
2. C5 — 路径遍历修复
3. C2 — change_password IDOR 修复
4. H8 — 全局异常处理器
5. H9 — 空 KB ID 权限绕过

**第二优先级（数据一致性）：**
6. C3 — LLM 输出枚举校验
7. C4 — VectorStore 单例共享
8. H6 — review_action 枚举校验
9. H7 — 向量搜索知识库过滤
10. H1 — delete_user 事务保护

**第三优先级（稳定性和性能）：**
11. H5 — Rerank 异常处理
12. M6/M7 — 数据库索引和 N+1 优化
13. M8 — 连接关闭
14. L2 — LLM 连接复用

---

### 六、正向评价

项目整体架构分层清晰，以下设计值得肯定：
- PBKDF2 密码哈希使用 390,000 次迭代，符合 OWASP 推荐
- SQL 查询全部使用参数化，无 SQL 注入风险
- `_persist_and_verify_result` 写后读校验是良好的防御性编程实践
- 证据检索的多查询策略（literal + relaxed + topic + counter_probe）设计精巧
- 模板系统的内置+覆盖+删除标记管理机制完善
- 错误类型体系（`errors.py`）设计清晰

需要我针对某个具体问题展开详细的修复方案吗？

审查已全部完成。以上可视化面板展示了完整的审查结果，下面是文字版汇总：

---

## doc-ai-wiki 全面代码审查报告

**审查范围**：认证/权限 | 数据库层 | AI质检/审核 | 检索/入库 | UI/测试 | 共 42 个源文件
**发现问题**：32 个（5 严重 / 9 高危 / 10 中危 / 8 低危）

---

### 一、严重问题 (Critical) — 需立即修复

**C1. 客户端会话可被伪造，实现权限提升**
- 文件：[pages.py](src/ui/pages.py:122), [pages.py](src/ui/pages.py:5056)
- `gr.BrowserState` 的 `secret="doc_ai_wiki_auth_session_v1"` 硬编码，会话包含 `is_admin`、`permissions` 等字段，可通过 DevTools 直接篡改。
- **修复**：改用服务端 session 存储（session ID + 数据库 session store），客户端仅保存不可猜测的 token。

**C2. `change_password` 无旧密码验证，IDOR 漏洞**
- 文件：[service.py](src/auth/service.py:165)
- 已认证用户可通过构造 `user_id` 修改任意其他用户密码，且无 try/except 保护。
- **修复**：增加旧密码参数并验证；添加异常处理和 rollback。

**C3. LLM 返回结果未做枚举校验，非法值污染数据库**
- 文件：[llm.py](src/ai/llm.py:296)
- `verdict`、`risk_level`、`confidence` 等字段未校验合法枚举值，任意字符串直接写入数据库。
- **修复**：添加枚举白名单和 `confidence` 范围约束 `[0.0, 1.0]`：
```python
_VALID_VERDICTS = {"verified", "needs_review", "rejected"}
verdict = payload.get("verdict", "needs_review")
if verdict not in _VALID_VERDICTS:
    verdict = "needs_review"
confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.2))))
```

**C4. IngestService 创建独立 VectorStore，ChromaDB 数据损坏风险**
- 文件：[service.py](src/ingest/service.py:33)
- 两个 `PersistentClient` 指向同一持久化目录，并发写入时可能导致数据损坏或锁竞争。
- **修复**：`IngestService` 接受外部注入 `vector_store`，与 `app.py` 共享同一实例。

**C5. `register_document` 路径遍历漏洞**
- 文件：[service.py](src/ingest/service.py:100)
- 用户提交的 `file_path` 可以是系统任意路径，在重定位校验之前已读取文件内容。
- **修复**：
```python
resolved = file_path.resolve()
if not str(resolved).startswith(str(self.settings.input_root.resolve())):
    raise ValidationAppError("文件路径不在允许的输入目录内")
```

---

### 二、高危问题 (High)

**H1. `delete_user` 多条 DELETE 无异常保护**
- 文件：[service.py](src/auth/service.py:195)
- 无 try/except 包裹，如果最后一条 DELETE 失败，前面已执行的数据处于不一致状态。
- **修复**：用 try/except 包裹并在异常时显式 rollback()。

**H2. 会话恢复不检查 `is_active` 状态**
- 文件：[service.py](src/auth/service.py:119)
- `get_user_by_id()` 不检查激活状态，被禁用用户刷新页面即可恢复完整登录态。
- **修复**：在 `get_user_by_id` 或 `_restore_login_session` 中额外检查 `is_active`。

**H3. 遗留密码验证存在时序攻击漏洞**
- 文件：[service.py](src/auth/service.py:87), [service.py](src/auth/service.py:97)
- bcrypt 降级和 SHA256 路径使用 `==` 运算符而非 `hmac.compare_digest()`。
- **修复**：统一使用 `hmac.compare_digest()` 进行比较。

**H4. 硬编码默认管理员密码 "admin"**
- 文件：[connection.py](src/db/connection.py:272)
- 每次初始化数据库自动创建密码为 `admin` 的管理员账户。
- **修复**：首次启动时生成随机密码并输出到日志，或强制首次登录修改密码。

**H5. Rerank 客户端完全无异常处理**
- 文件：[rerank.py](src/ai/rerank.py:55)
- `httpx.post()` + `raise_for_status()` 没有 try/except，任何网络错误直接中断整个质检流程。
- **修复**：添加异常处理，失败时优雅降级为返回原始顺序。

**H6. API 层 `review_action` 未做枚举校验**
- 文件：[models.py](src/common/models.py:84), [service.py](src/review/service.py:18)
- `ReviewSubmitRequest.review_action` 是无约束的 `str`，任意字符串直接写入数据库和 claim 的 review_status。
- **修复**：在 Pydantic model 中使用 `Literal["approved", "rejected", "updated"]`。

**H7. 向量检索未按 `knowledge_base_id` 过滤**
- 文件：[service.py](src/retrieval/service.py:94)
- 向量搜索未传递知识库 ID，可能跨知识库泄漏数据。全文检索则正确使用了 SQL JOIN 做过滤。
- **修复**：在 `VectorStore.upsert_chunks` metadata 中增加 `knowledge_base_id`，查询时按此过滤。

**H8. 全局未捕获异常泄漏内部堆栈信息**
- 文件：[app.py](src/app.py:258)
- 仅注册了 `AppError` handler，`sqlite3.OperationalError` 等未预期异常会返回完整 Python 堆栈。
- **修复**：
```python
@app.exception_handler(Exception)
async def handle_unexpected_error(request, exc):
    logger.exception("未预期异常: %s", exc)
    return JSONResponse(status_code=500, content={
        "success": False, "message": "服务器内部错误", "error_code": "INTERNAL_ERROR"
    })
```

**H9. 空 `knowledge_base_id` 直接跳过权限检查**
- 文件：[app.py](src/app.py:132)
- 非 admin 用户不传知识库 ID 时可搜索所有知识库内容，结合 H7 问题被放大。
- **修复**：空 KB ID 时将搜索限定在用户有权限的知识库范围内。

---

### 三、中危问题 (Medium)

| # | 问题 | 文件 | 建议 |
|---|------|------|------|
| M1 | `register_user` TOCTOU 竞态条件 | [service.py](src/auth/service.py:144) | 直接 INSERT 捕获 IntegrityError |
| M2 | User 类暴露 password_hash | [service.py](src/auth/service.py:30) | 移除敏感字段或创建 DTO |
| M3 | 空输入导致质检垃圾数据 | [service.py](src/quality/service.py:142) | 入口添加非空校验 |
| M4 | `except Exception` 过宽 | [llm.py](src/ai/llm.py:146) | 按类型分别处理异常 |
| M5 | 模板 `.format()` 花括号崩溃 | [llm.py](src/ai/llm.py:287) | 改用 `string.Template` |
| M6 | Schema 缺少关键索引 | [schema.py](src/db/schema.py) | 为 check_id、review_status 等加索引 |
| M7 | N+1 查询（201 次） | [repositories.py](src/db/repositories.py:679) | 用 `WHERE check_id IN (...)` 批量获取 |
| M8 | SQLite 连接未关闭 | [service.py](src/retrieval/service.py:59) | 使用 `contextlib.closing` |
| M9 | 分页 HTML 存在 XSS 风险 | [page_helpers.py](src/ui/page_helpers.py:282) | 对 page_info 调用 `html.escape()` |
| M10 | `_do_register` 无异常处理 | [pages.py](src/ui/pages.py:5944) | 添加 try/except |

---

### 四、低危问题 (Low)

| # | 问题 | 文件 |
|---|------|------|
| L1 | LLM 逻辑约束块缺少比较型检测 | [llm.py](src/ai/llm.py:311) |
| L2 | 每次 LLM 调用创建新 httpx 连接，无复用 | [llm.py](src/ai/llm.py:121) |
| L3 | 密码策略薄弱（最长20字符，无最小长度） | [service.py](src/auth/service.py:59) |
| L4 | KB ID 允许中文目录名，跨平台风险 | [service.py](src/knowledge_base/service.py:224) |
| L5 | pages.py 单文件 6219 行，可维护性低 | [pages.py](src/ui/pages.py) |
| L6 | UI_CSS 重复赋值 | [css.py](src/ui/css.py:3) |
| L7 | exporters 和各 page 模块无单元测试 | tests/ |
| L8 | conftest.py 仅 8 行，缺少共享 fixture | [conftest.py](tests/conftest.py) |

---

### 五、修复优先级路线图

**第一阶段（安全类，立即处理）：**
1. C1 — 服务端 session 替代客户端 BrowserState
2. C5 — 路径遍历修复
3. C2 — change_password IDOR 修复
4. H8 — 全局异常处理器
5. H9 — 空 KB ID 权限绕过

**第二阶段（数据一致性）：**
6. C3 — LLM 输出枚举校验
7. C4 — VectorStore 单例共享
8. H6 — review_action 枚举校验
9. H7 — 向量搜索知识库过滤
10. H1 — delete_user 事务保护

**第三阶段（稳定性和性能）：**
11. H5 — Rerank 异常处理
12. M6/M7 — 数据库索引和 N+1 优化
13. M8 — 连接关闭
14. L2 — LLM 连接复用

---

### 六、正向评价

项目整体架构分层清晰，以下设计值得肯定：
- PBKDF2 密码哈希使用 390,000 次迭代，符合 OWASP 推荐标准
- 所有 SQL 查询使用参数化（`?`），无 SQL 注入风险
- `_persist_and_verify_result` 写后读校验是优秀的防御性编程实践
- 证据检索的多查询策略（literal + relaxed + topic + counter_probe）设计精巧
- 模板系统的内置+覆盖+删除标记管理机制完善
- 错误类型体系（`errors.py`）设计清晰规范

需要我针对某个具体问题展开详细的修复代码吗？