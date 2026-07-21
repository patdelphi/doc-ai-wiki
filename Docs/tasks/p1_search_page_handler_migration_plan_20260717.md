# P1 知识库检索页处理器迁移实施计划

> **执行要求：** 使用 `superpowers:executing-plans` 在当前会话逐项执行；不使用 Subagent。步骤使用复选框跟踪。

**目标：** 将九个知识库检索页处理器从 `src/ui/pages.py` 迁移到 `src/ui/search_page.py`，保持现有 UI、权限和检索行为不变。

**架构：** `search_page.py` 负责页面组件、事件和页面内处理器；`pages.py` 只注入运行时依赖并保留跨页面同步。服务依赖通过关键字参数显式传入，`pages.py` 用 `functools.partial` 与 `functools.update_wrapper` 生成名称稳定的 Gradio 回调。

**技术栈：** Python 3.11+、Gradio 6、Pytest、Ruff、Mypy。

## 全局约束

- 不改变检索算法、权限规则、页面布局、组件 ID、中文文案和输出 tuple 顺序。
- 不新增第三方依赖、数据库变更、索引格式或配置项。
- 测试不调用外部 API 或真实模型。
- 不执行索引重建、数据库迁移、部署、commit、push、merge 或 pull。
- 所有新增/修改 Markdown 与 Python 使用 UTF-8 BOM + CRLF；`pyproject.toml` 保持 UTF-8 无 BOM + CRLF。

---

### Task 1：为检索页模块级处理器建立直接单测

**文件：**

- 新建：`tests/unit/test_search_page.py`
- 修改：`tests/unit/test_quality_gates.py`

**接口：**

- 直接导入 `run_search()`、`run_search_ui()`、`reset_search_workspace_ui()`、`change_search_page()`、`select_search_result()`、`export_search_results()`。
- 使用内存 Stub RetrievalService，只实现 `hybrid_search()` 和 `get_chunk_detail()`。

- [x] **Step 1：写失败测试**

覆盖以下断言：

```python
assert "请输入关键词" in run_search(
    "", 10, None, None,
    retrieval_service=stub_service,
    has_tab_access=lambda session, tab: True,
    resolve_authorized_knowledge_base=lambda choice, session: "default",
)[0]
assert "没有知识库检索权限" in run_search(
    "阿胶", 10, "default", restricted_session,
    retrieval_service=stub_service,
    has_tab_access=lambda session, tab: False,
    resolve_authorized_knowledge_base=lambda choice, session: "default",
)[0]
assert run_search_ui(
    "阿胶", 10, "default", None,
    retrieval_service=stub_service,
    has_tab_access=lambda session, tab: False,
    resolve_authorized_knowledge_base=lambda choice, session: "default",
)[2] == []
assert reset_search_workspace_ui("default")[2] == []
assert export_callback_calls[0][0:2] == ("文档检索", "检索结果")
```

在 `test_quality_gates.py` 中解析 `src/ui/pages.py` AST，断言九个处理器名称不再作为 `build_ui()` 内部函数存在。

- [x] **Step 2：运行 Red 测试**

运行：

```powershell
python -m pytest "tests/unit/test_search_page.py" "tests/unit/test_quality_gates.py" -q
```

预期：因 `search_page.py` 尚未导出处理器而收集失败，或 AST 门禁发现旧嵌套函数而失败。

---

### Task 2：迁移九个页面内处理器

**文件：**

- 修改：`src/ui/search_page.py`
- 测试：`tests/unit/test_search_page.py`

**接口：**

- 新增 `build_search_table_page_outputs(search_rows, page=1)`。
- 新增 `build_search_detail_payload(search_row, *, retrieval_service)`。
- 新增 `build_search_detail(search_row, query_text, *, retrieval_service)`。
- 新增 `export_search_results(search_rows, selected_search_row, query_text, *, export_markdown_result)`。
- 新增 `run_search(query, top_k, knowledge_base_choice=None, login_session=None, *, retrieval_service, has_tab_access, resolve_authorized_knowledge_base)`。
- 新增 `run_search_ui(query, top_k, knowledge_base_choice=None, login_session=None, *, retrieval_service, has_tab_access, resolve_authorized_knowledge_base)`。
- 新增 `reset_search_workspace_ui(knowledge_base_choice=None)`。
- 新增 `change_search_page(search_rows, current_page, action)`。
- 新增 `select_search_result(current_page_rows, search_rows, query_text, evt, *, retrieval_service)`。

- [x] **Step 1：补齐模块依赖导入**

`search_page.py` 从现有模块导入 `AppError`、分页 helper、选择 helper，以及检索结果格式化函数；不复制任何 helper 实现。

- [x] **Step 2：逐函数迁移原逻辑**

逐字保持输入校验、稳定中文提示、`AppError` 转换、分页语义、首条详情和导出参数，只把 `retrieval_service`、权限判断、授权知识库解析、导出回调改为显式关键字依赖。

- [x] **Step 3：运行 Green 测试**

运行：

```powershell
python -m pytest "tests/unit/test_search_page.py" -q
```

预期：直接处理器测试全部通过，无网络或真实模型调用。

---

### Task 3：在总装配中绑定依赖并删除旧实现

**文件：**

- 修改：`src/ui/pages.py`
- 修改：`tests/unit/test_quality_gates.py`
- 测试：`tests/unit/test_ui.py`

**接口：**

- 从 `search_page.py` 以 `search_*` 别名导入模块级处理器。
- `pages.py` 使用下列绑定方式保持 Gradio 回调名称：

```python
run_search_ui = update_wrapper(
    partial(
        search_run_search_ui,
        retrieval_service=retrieval_service,
        has_tab_access=_has_tab_access,
        resolve_authorized_knowledge_base=_resolve_authorized_knowledge_base_choice,
    ),
    search_run_search_ui,
)
```

- [x] **Step 1：绑定运行时依赖**

在 `export_markdown_result()` 定义后绑定需要服务或回调的处理器；纯分页和重置函数直接使用模块导入。

- [x] **Step 2：删除九个嵌套旧实现**

删除 `build_search_table_page_outputs()` 到 `select_search_result()` 的检索页旧定义；保留 `select_document_quality_search_result()`，让它调用已绑定的详情处理器。

- [x] **Step 3：保留跨页面同步**

不移动 `change_search_knowledge_base_ui()`；确认它继续调用迁移后的 `reset_search_workspace_ui()` 并保持十二项输出顺序。

- [x] **Step 4：运行装配与门禁测试**

运行：

```powershell
python -m pytest "tests/unit/test_search_page.py" "tests/unit/test_quality_gates.py" "tests/unit/test_ui.py" -q
```

预期：直接单测、AST 门禁和完整 Gradio 装配测试全部通过。

---

### Task 4：文档、格式和完整验收

**文件：**

- 修改：`todo.md`
- 修改：`Docs/changelog/retrieval_pageindex_20260716.md`
- 修改：`Docs/acceptance.MD`
- 修改：`Docs/optimization-plan/vibe_coding_code_quality_audit_20260716.md`
- 修改：`chat_history.md`

- [x] **Step 1：更新项目文档**

记录迁移函数清单、`pages.py` 净减少行数、测试结果和未迁移的跨页面职责；不把单页迁移描述为整个 UI 拆分完成。

- [x] **Step 2：执行完整质量门禁**

依次运行：

```powershell
python -m ruff check src tests .aipython Docs/migrations
python -m mypy src/retrieval src/pageindex src/quality/service.py
python -m pytest tests --maxfail=1 -q
python -m build
python -m compileall -q src tests .aipython
```

预期：所有命令退出码为 0；文档只记录本轮实际输出。

- [x] **Step 3：检查差异与文件格式**

排除三份既有行尾噪声文档后执行 `git diff --check`；验证本轮 Markdown/Python 为 UTF-8 BOM + CRLF，`pyproject.toml` 无 BOM + CRLF。

- [x] **Step 4：保持 Git 边界**

报告工作区状态，不执行 commit 或 push，等待用户单独确认。
