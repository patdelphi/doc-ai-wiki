# P1 知识库检索页处理器迁移设计

> 日期：2026-07-17
>
> 分支：`codex/retrieval-pageindex-optimization`
>
> 状态：已确认并进入实施

## 1. 目标

在不改变页面布局、公开接口、权限语义和检索算法的前提下，将“知识库检索”页的页面内处理器从 `src/ui/pages.py` 迁入现有 `src/ui/search_page.py`，让 `build_ui()` 只保留跨页面编排与依赖装配。

本批次只处理一个页面，迁移一块、删除一块，不创建平行兼容层。

## 2. 当前问题

`src/ui/search_page.py` 已负责组件构建和事件绑定，但以下检索页处理器仍嵌套在 `build_ui()`：

- `build_search_detail_payload()`；
- `build_search_detail()`；
- `build_search_table_page_outputs()`；
- `export_search_results()`；
- `run_search()`；
- `run_search_ui()`；
- `reset_search_workspace_ui()`；
- `change_search_page()`；
- `select_search_result()`。

这导致同一页面的组件、事件和行为分散在两个文件中，测试也只能通过构建完整 Gradio 应用间接取得处理器。

`change_search_knowledge_base_ui()` 同时更新文档管理、AI 质检、人工审核和检索页，属于跨页面编排，本批次继续留在 `pages.py`。

## 3. 方案比较

### 方案一：迁入现有 `search_page.py`，依赖显式传入

- 优点：页面组件、事件和页面内行为集中；不新增文件；符合当前按页面拆分结构。
- 缺点：`search_page.py` 会增加约 200 行，但职责仍单一。

### 方案二：新建 `search_handlers.py`

- 优点：组件构建与行为完全分离。
- 缺点：当前只有一个页面需要迁移，会增加文件和跳转成本，容易形成文件爆炸。

### 方案三：只迁移纯格式化函数

- 优点：改动最小。
- 缺点：核心服务调用和权限处理仍留在 `build_ui()`，不能真正降低总装配复杂度。

选择方案一。

## 4. 模块边界

### `src/ui/search_page.py`

负责：

- 检索页组件构建；
- 检索页事件绑定；
- 检索执行、分页、结果选择、详情加载、重置和导出；
- 检索页自身的输入校验与稳定错误展示。

页面内处理器保持模块级函数，不新增 Controller、Manager、Factory 或类层级。

### `src/ui/pages.py`

继续负责：

- 创建并注入 `RetrievalService` 等运行时依赖；
- 用户权限与授权知识库选择的跨页面规则；
- 知识库切换时同步多个页面；
- 调用 `bind_search_events()` 完成总装配。

## 5. 依赖与接口

迁移后的 `run_search()` 保持现有四个页面输入，并通过关键字参数显式接收 `retrieval_service`、`has_tab_access` 和 `resolve_authorized_knowledge_base`；返回现有六项输出 tuple，不增加新的返回包装类型。

`run_search_ui()`、`build_search_detail_payload()`、`build_search_detail()`、`select_search_result()` 和 `export_search_results()` 同样显式接收自身真正需要的服务或回调。

`pages.py` 使用 `functools.partial` 绑定运行时依赖，得到名称稳定的页面处理器；不使用字典式 Service Locator。

现有输出 tuple 的字段数量、顺序和 HTML 格式保持不变，避免 Gradio outputs 错位。

## 6. 数据流

```text
Gradio 事件
-> search_page 模块级处理器
-> pages.py 注入的权限/知识库解析回调
-> RetrievalService.hybrid_search()
-> search_page 格式化、分页、详情或导出
-> 现有 Gradio outputs
```

知识库切换仍由 `pages.py/change_search_knowledge_base_ui()` 负责，并调用迁移后的 `reset_search_workspace_ui()`。

## 7. 错误处理

- 空查询、无菜单权限、无授权知识库继续返回当前稳定提示。
- `RetrievalService` 的 `AppError` 继续转换为带 `error_code` 的页面提示。
- 导出继续复用 `pages.py` 已有的安全导出回调，不扩大文件系统写入范围。
- 不捕获新的宽泛异常，不暴露内部堆栈、密钥、URL 或数据库错误原文。

## 8. 测试策略

新增 `tests/unit/test_search_page.py`，直接测试迁移后的模块级函数：

1. 空查询拒绝；
2. 无菜单权限拒绝；
3. 无授权知识库拒绝；
4. 正常混合检索与首条详情；
5. `AppError` 稳定展示；
6. 分页前后页；
7. 表格选择与详情加载；
8. 重置工作区；
9. 导出参数透传。

保留 `tests/unit/test_ui.py` 作为完整 Gradio 装配回归，并增加 AST 门禁：上述九个处理器不得重新嵌套回 `build_ui()`。

严格执行 Red-Green-Refactor，测试不调用外部 API、不访问真实模型。

## 9. 非目标

- 不调整检索算法、Top-K、RRF、Rerank 或权限规则；
- 不修改页面布局、CSS、组件 ID 和中文文案；
- 不迁移文档管理、AI 质检、人工审核、设置或 PageIndex 页面；
- 不新增依赖、数据库表、索引格式或配置项；
- 不重建检索索引或 PageIndex；
- 不执行部署、commit、push、merge 或 pull。

## 10. 完成标准

- 九个检索页处理器从 `build_ui()` 删除，并在 `search_page.py` 直接可测；
- `change_search_knowledge_base_ui()` 继续承担跨页面同步；
- Gradio outputs 数量和顺序不变；
- 新增直接单测和 AST 防回归门禁通过；
- `test_ui.py`、Ruff、Mypy目标、完整 Pytest、build 和 compileall 通过；
- Todo、变更记录、验收记录和聊天历史同步更新。
