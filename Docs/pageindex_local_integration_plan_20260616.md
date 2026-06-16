# PageIndex 本地集成实施计划（2026-06-16）

## 结论

本项目新增独立主 Tab：`PageIndex 深度检索`。实现方式为直接集成 `VectifyAI/PageIndex` 开源项目源码，使用其本地建树与本地检索能力，不接 PageIndex 官方线上服务，不接 MCP。

## 关键说明

### PageIndex 是否直接处理文档

是。PageIndex 的输入是原始文档路径，例如 PDF 或 Markdown 文件路径。

本项目集成后流程为：

```text
Input/<knowledge_base_id>/<document>
    -> PageIndex 本地源码读取文档
    -> PageIndex 构建结构树
    -> 本项目保存结构树和查询记录
    -> 独立 Tab 展示树、问答、引用和检索路径
```

### 是否经过现有 RAG 切片

不经过传统 RAG 固定切片。

PageIndex 不是 `split_text -> embedding -> vector db -> top_k` 这条链路。它会按文档自然结构构建目录树：

- PDF：读取页面文本，识别目录/标题/页码范围，再生成树节点。
- Markdown：按 `#` / `##` / `###` 标题层级构建树节点。

注意：PageIndex 不是完全没有分段，它有节点、页码范围、行号范围、最大页数、最大 token 等边界；但这不是传统 RAG 的固定长度 chunk。

### PageIndex 自己是否用本地 DB 存储

开源项目默认不是数据库，而是本地 JSON workspace。

`PageIndexClient(workspace=...)` 会把索引结果保存为：

```text
workspace/
  _meta.json
  <doc_id>.json
```

本项目不建议直接把它作为最终存储。推荐做法：

- PageIndex 源码负责建树和读取结构。
- 本项目 `PageIndexService` 负责把结果写入 SQLite。
- 原始 PageIndex JSON workspace 可作为调试缓存，但正式状态以 SQLite 为准。

这样能和当前项目的知识库权限、文档状态、查询历史、导出审计统一起来。
## 知识库隔离原则

PageIndex 集成必须遵循当前项目的文档管理结构：先有知识库，再在知识库下管理文档。不能把所有文档放进一个全局 PageIndex 文档池，否则会造成跨知识库知识混淆和权限泄漏。

硬性规则：

- 所有 PageIndex 索引必须绑定 `knowledge_base_id` 和 `doc_uid`。
- UI 先选择知识库，再选择该知识库下的文档。
- 普通用户只能看到自己有权限的知识库和文档。
- PageIndex 查询默认只针对当前选中的单篇文档。
- 后续如果支持多文档查询，也只能在同一个 `knowledge_base_id` 内做候选选择。
- 查询历史必须按 `knowledge_base_id` 过滤。
- 导出结果必须记录 `knowledge_base_id`、`doc_uid`、文档标题和索引版本。

推荐 workspace 结构：

```text
index/pageindex_workspace/
  <knowledge_base_id>/
    <doc_uid>/
      _meta.json
      <pageindex_doc_id>.json
```

不允许使用一个全局 workspace 混放所有知识库文档。

## 集成方式

### 目录结构

新增：

```text
vendor/pageindex/
  LICENSE
  README.md
  pageindex/
    __init__.py
    client.py
    page_index.py
    page_index_md.py
    retrieve.py
    utils.py
    config.yaml

src/pageindex/
  __init__.py
  service.py
  models.py
  adapters.py

src/ui/pageindex_page.py

tests/unit/test_pageindex_service.py
tests/unit/test_pageindex_ui.py
```

### 依赖

PageIndex 开源项目依赖：

```text
litellm==1.83.7
pymupdf==1.26.4
PyPDF2==3.0.1
python-dotenv==1.2.2
pyyaml==6.0.2
```

当前项目已有 `pyyaml`。新增依赖前需要确认兼容性，尤其是：

- `litellm` 是否与当前 Python 版本兼容
- `pymupdf` 在 Windows 上是否安装稳定
- `python-dotenv` 是否会和当前 `pydantic-settings` 的 `.env` 读取产生重复行为

## LLM 配置适配

PageIndex 默认使用 LiteLLM，并默认读 `OPENAI_API_KEY`。本项目不能让它直接漂移读取外部配置，应统一由 `AppSettings` 控制。

适配规则：

```text
AppSettings.llm_provider == disabled
    -> PageIndex Tab 显示“LLM 未启用”，禁止建树和问答

AppSettings.llm_provider == openai
    -> 设置 LiteLLM 所需模型和环境变量
    -> 使用 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL

AppSettings.llm_provider == anthropic
    -> 使用 LiteLLM 的 anthropic provider 形式
    -> 使用 LLM_API_KEY / LLM_MODEL
```

第一版优先支持 OpenAI 兼容接口，因为当前项目已有 OpenAI-compatible 客户端配置。

## 数据库设计

新增表：`pageindex_documents`

```text
pageindex_doc_id TEXT PRIMARY KEY
doc_uid TEXT NOT NULL
knowledge_base_id TEXT NOT NULL
source_path TEXT NOT NULL
source_hash TEXT NOT NULL
doc_type TEXT NOT NULL
status TEXT NOT NULL
error_message TEXT
tree_json TEXT NOT NULL DEFAULT '{}'
workspace_doc_id TEXT
workspace_path TEXT
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

新增表：`pageindex_queries`

```text
query_id TEXT PRIMARY KEY
pageindex_doc_id TEXT NOT NULL
knowledge_base_id TEXT NOT NULL
doc_uid TEXT NOT NULL
question TEXT NOT NULL
answer TEXT NOT NULL
trace_json TEXT NOT NULL DEFAULT '[]'
evidence_json TEXT NOT NULL DEFAULT '[]'
latency_ms INTEGER NOT NULL DEFAULT 0
created_at TEXT NOT NULL
```

## 服务层

`src/pageindex/service.py`

核心方法：

```python
class PageIndexService:
    def list_available_documents(self, knowledge_base_id: str) -> list[dict]: ...
    def build_index(self, knowledge_base_id: str, doc_uid: str) -> dict: ...
    def get_index(self, knowledge_base_id: str, doc_uid: str) -> dict | None: ...
    def rebuild_index(self, knowledge_base_id: str, doc_uid: str) -> dict: ...
    def ask(self, knowledge_base_id: str, doc_uid: str, question: str) -> dict: ...
    def list_query_history(self, knowledge_base_id: str, doc_uid: str | None = None) -> list[dict]: ...
```

异常处理：

- 文档不存在：`NotFoundAppError`
- 无 LLM 配置：`ValidationAppError`
- PageIndex 建树失败：`DatabaseAppError` 或 `ValidationAppError`
- JSON 解析失败：返回明确错误并保存失败状态

数据库操作全部通过事务。

## UI 设计

新增主 Tab：`PageIndex 深度检索`

前端必须沿用当前 Gradio 架构，不引入新前端框架。实现方式参考第一个业务 Tab `AI 质检` 的逻辑：

- `src/ui/pageindex_page.py` 提供 `build_pageindex_tab()` 和 `bind_pageindex_events()`。
- `build_pageindex_tab()` 只负责构建 Gradio 组件，并返回组件字典。
- `bind_pageindex_events()` 只负责绑定 `.click()`、`.input()`、`.select()` 等事件。
- `src/ui/pages.py` 负责初始化状态、跨 Tab 组件联动、权限可见性和主页面总装配。
- 组件命名、状态对象、分页、按钮样式沿用 `quality_page.py` / `page_helpers.py`。
- 事件输入变化优先使用 `.input()`，避免首屏自动触发长任务。
- 长任务按钮使用 `.click()`，建索引和深度检索都不能在页面加载时自动执行。

建议文件结构：

```python
def build_pageindex_tab(...) -> dict[str, gr.components.Component]:
    """构建 PageIndex 深度检索页组件，并返回事件绑定所需组件集合。"""


def bind_pageindex_events(
    *,
    components: dict[str, gr.components.Component],
    login_state,
    change_pageindex_knowledge_base_ui: Callable,
    change_pageindex_document_ui: Callable,
    build_pageindex_index_ui: Callable,
    ask_pageindex_ui: Callable,
    select_pageindex_tree_node_ui: Callable,
    select_pageindex_history_ui: Callable,
    export_pageindex_result_ui: Callable,
) -> None:
    """绑定 PageIndex 页事件。"""
```

区域：

1. 知识库和文档选择
2. 索引状态
3. 构建 / 重建索引按钮
4. 结构树展示
5. 问题输入
6. 查询按钮
7. 答案展示
8. 检索路径和证据展示
9. 查询历史
10. 导出 Markdown

Tab 权限：

- `AUTH_TAB_NAMES` 增加 `PageIndex 深度检索`
- 管理员默认有权限
- 普通用户必须显式配置该 Tab 权限
- 文档选择必须按 `knowledge_base_id` 过滤

## 用户前端流程与 UX 设计

### 目标用户

该 Tab 面向需要“精读长文档”的用户，而不是普通全库搜索用户。典型任务是：选择某个知识库下的一篇长文档，生成结构树，然后围绕这篇文档做可追溯问答。

### 主流程

```text
进入 PageIndex 深度检索
    -> 选择知识库
    -> 选择该知识库下的文档
    -> 查看当前 PageIndex 索引状态
    -> 未建索引：点击“构建 PageIndex 索引”
    -> 已建索引：查看结构树
    -> 输入问题
    -> 点击“深度检索”
    -> 查看答案、检索路径、引用证据
    -> 可导出 Markdown 结果
```

### 首屏布局

首屏不做营销说明，直接进入工具界面。

建议从上到下分为四个区域：

1. **文档选择栏**
   - 知识库下拉框
   - 文档下拉框
   - 索引状态标签
   - 构建 / 重建按钮

2. **结构树区域**
   - 左侧展示 PageIndex 树
   - 节点显示标题、节点 ID、页码或行号范围
   - 点击节点后，右侧显示节点摘要和原文片段

3. **问答区域**
   - 问题输入框
   - “深度检索”按钮
   - 回答结果

4. **证据与历史区域**
   - 检索路径
   - 命中节点
   - 原文证据
   - 最近查询历史
   - 导出按钮

### 状态设计

#### 未选择知识库

显示空状态：

```text
请先选择一个知识库。
PageIndex 会严格在当前知识库范围内工作，不会跨知识库混用文档。
```

#### 知识库无文档

显示空状态：

```text
当前知识库下暂无可用文档。
请先到“知识库管理”中上传并入库文档。
```

#### 文档未建索引

显示：

- 索引状态：未构建
- 主按钮：构建 PageIndex 索引
- 问答输入区置灰

提示：

```text
该文档尚未生成 PageIndex 结构树。构建过程会调用当前项目配置的 LLM。
```

#### 正在建索引

显示进度面板：

- 当前阶段：读取文档 / 构建树 / 生成摘要 / 保存索引
- 当前文档
- 耗时
- 错误时保留失败原因

第一版可以用同步按钮返回结果，不做后台队列；如果长文档耗时明显，再升级为任务队列。

#### 已建索引

显示：

- 索引状态：已完成
- 构建时间
- 文档 hash
- 节点数量
- 根节点数量
- 重建按钮

如果源文档 hash 变化：

```text
源文档已变化，建议重建 PageIndex 索引。
```

#### LLM 未启用

如果 `LLM_PROVIDER=disabled`：

- 构建按钮禁用
- 深度检索按钮禁用

提示：

```text
PageIndex 需要 LLM 才能构建摘要和执行树搜索。请在环境变量中启用 LLM_PROVIDER。
```

### 问答交互

用户输入问题后，点击“深度检索”。

结果区按这个顺序展示：

1. **答案**
2. **检索路径**
3. **引用证据**
4. **原始节点内容**

检索路径示例：

```text
文档：xxx.md
路径：总论 > 第二章 风险因素 > 2.3 数据来源限制
命中原因：该节点摘要包含“审计”“引用依据”“跨章节说明”等关键词，并被 LLM 判断为最相关。
```

证据表字段：

```text
序号 | 节点 ID | 标题路径 | 页码/行号 | 摘要 | 原文片段
```

### 查询历史

历史记录只显示当前知识库范围内的数据。

切换知识库时：

- 清空当前文档选择
- 清空结构树
- 清空问答结果
- 刷新该知识库的历史记录

切换文档时：

- 刷新索引状态
- 刷新结构树
- 清空当前问答结果
- 历史记录过滤到当前文档

### 防混淆 UX

页面上必须明确显示当前范围：

```text
当前知识库：xxx
当前文档：yyy
```

所有答案和导出结果都必须带上：

- `knowledge_base_id`
- 知识库名称
- `doc_uid`
- 文档标题
- PageIndex 索引构建时间

避免用户误以为答案来自全库。

### 错误提示

常见错误需要用用户能理解的话呈现：

- 文档不存在：`源文档不存在，请回到知识库管理检查文档状态。`
- 文档格式不支持：`第一阶段仅支持 Markdown，PDF 将在后续阶段支持。`
- LLM 未配置：`PageIndex 需要启用 LLM 后才能运行。`
- 建树失败：`PageIndex 索引构建失败，请查看错误详情。`
- 查询失败：`深度检索失败，请检查 LLM 配置或重建索引。`

### MVP 验收标准

- 用户能清楚知道自己正在操作哪个知识库和哪篇文档。
- 没有索引时，用户知道下一步是构建索引。
- 构建完成后，用户能看到结构树。
- 提问后，用户能看到答案和引用证据。
- 切换知识库不会残留上一个知识库的文档、树、答案或历史。
- 无权限用户看不到该 Tab 或看不到未授权知识库数据。

## 第一阶段 MVP

目标：让用户能在独立 Tab 中对单篇已入库 Markdown 文档使用 PageIndex 本地源码建树和问答。

范围：

- vendor PageIndex 源码
- 新增依赖
- Markdown 建树
- SQLite 保存 tree_json
- UI 展示树
- 单文档问答
- 权限接入
- 单元测试

暂不做：

- PageIndex 官方线上服务
- MCP
- 多文档全局 PageIndex File System
- OCR
- 扫描件 PDF 深度优化
- 高并发队列

## 第二阶段

增加 PDF 支持：

- 只支持可提取文本的 PDF
- 使用 PageIndex 开源项目标准 PDF parsing
- 在 UI 中提示“扫描件/OCR PDF 效果不保证”

## 第三阶段

增强能力：

- 查询历史导出
- 与现有知识库检索做候选文档联动
- PageIndex 结果用于 AI 质检证据复核
- 查询耗时、LLM 调用失败、索引失败统计

## 测试计划

### 单元测试

- PageIndexService 在 LLM disabled 时拒绝建树
- Markdown 文档可生成 PageIndex 树
- 树结果可写入并读回 SQLite
- 未授权知识库文档不会出现在下拉列表
- 查询结果包含 answer、trace、evidence
- PageIndex 源码异常时保存失败状态

### UI 测试

- 新 Tab 存在
- 权限控制生效
- 文档下拉按知识库刷新
- 点击建树按钮注册事件
- 点击查询按钮注册事件

### 回归测试

```powershell
python -m pytest tests/unit/test_pageindex_service.py -q
python -m pytest tests/unit/test_pageindex_ui.py -q
python -m pytest tests/unit/test_ui.py -q
python -m pytest tests -q
```

## 风险与处理

| 风险 | 处理 |
|---|---|
| PageIndex 源码不是标准包 | vendor 源码并保留 LICENSE |
| LiteLLM 配置和项目配置冲突 | 由 adapter 统一设置环境变量和模型 |
| PageIndex 默认写 `logs/` / workspace JSON | 指定到 `index/pageindex_workspace/` |
| PDF 解析质量不稳定 | 第一版先 Markdown，第二阶段再 PDF |
| LLM 成本和延迟高 | UI 显示耗时，历史记录保存 latency |
| 与现有权限系统脱节 | 所有文档选择和查询都经过 knowledge_base_id 过滤 |

## 执行顺序

1. 复制 PageIndex MIT 源码到 `vendor/pageindex/`
2. 新增依赖到 `pyproject.toml`
3. 新增 PageIndex 数据表和兼容初始化逻辑
4. 新增 `PageIndexService`
5. 写服务层测试
6. 新增 `src/ui/pageindex_page.py`
7. 接入 `src/ui/pages.py` 主 Tab
8. 接入权限菜单
9. 写 UI 测试
10. 跑全量测试
11. 更新 README / Docs / todo.md

## 是否进入执行

该计划确认后，再开始改代码。执行前需要再次确认：

- 是否允许新增依赖并安装验证
- 是否允许复制 PageIndex 源码到 `vendor/pageindex/`
- 第一阶段是否只做 Markdown
