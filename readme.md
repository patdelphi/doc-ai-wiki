# 基于文档的知识库AI查询系统

> **版本**：`0.6`
> **最后更新**：`2026-05-14`
> **分支**：`dev`（开发主线） / `main`（稳定发布）

## 项目背景

本项目面向中文知识内容的整理、检索与质检场景，目标是提供一套可本地运行、可持续扩展、支持多用户多知识库协同的知识库工作台。系统围绕"文档入库 -> 索引构建 -> 混合检索 -> AI 质检 -> 人工审核 -> 结果导出"这一完整链路展开，适用于古籍、医学、企业知识、专题资料等需要可信证据支撑的中文内容治理场景。

## 建设目标

- 建立统一的中文知识库入库与索引能力，支持多知识库隔离管理
- 支持全文检索、向量检索与混合检索
- 支持基于知识库证据的 AI 质检，而不是只做文本表面匹配
- 支持人工审核闭环，降低误判风险
- 支持多用户认证、注册、后台权限配置
- 支持本地页面操作和 API 调用两种使用方式
- 为后续模板增强、规则增强、部署扩展预留清晰边界

## 核心能力

### 1. 认证与用户管理

- 支持用户注册（用户名、密码、重复密码），密码长度限制 20 字符
- 除 `admin` 外，新注册用户默认无任何菜单权限和知识库权限
- 支持后台用户管理：用户列表、启用状态、基础信息维护
- 支持后台权限管理：为指定用户配置可访问菜单（tab 页）与可访问知识库
- 支持零权限用户登录后的固定入口页（"待开通"），不会出现空白主界面或菜单闪烁
- 管理员为用户开通权限后，当前登录态即时刷新，业务 tab 立即出现

### 2. 文档入库

- 支持从 `Input/<knowledge_base_id>` 目录扫描 `Markdown`、`JSON` 文档
- 每个知识库独立对应 `Input` 下的子目录，目录名使用知识库 ID
- 自动完成元数据整理、章节提取、分块、全文索引和向量索引构建
- 支持查看入库状态、失败原因和重建结果
- 支持文档入库质检与结果导出
- 支持调整文档归属到其他知识库，自动完成文件移动与数据库归属更新

### 3. 多知识库管理

- 支持创建、编辑、删除知识库
- 新建知识库后自动在 `Input` 下创建对应子目录
- 支持知识库切换，各页面下拉列表与数据隔离保持一致
- 支持按知识库过滤文档列表、质检历史、审核记录
- 支持知识库删除前的关联数据校验

### 4. 知识库检索

- 支持全文检索、向量检索、混合检索
- 支持候选重排与多路召回结果融合
- 支持查看命中文档、章节位置、检索来源和重排分数
- 支持页面内结果详情和下载导出
- 检索结果按当前知识库过滤，数据隔离

### 5. AI 质检

- 支持对输入文本（2000 字以内）进行 Claim 拆分与逐条核验
- 支持根据模板切换不同质检策略
- 支持显示 Claim、证据关系、证据列表、证据详情、风险等级
- 支持查看最近质检记录、分页切换、历史结果回放
- 支持效果评测与结果导出
- 支持按知识库过滤质检范围

### 6. 人工审核

- 支持从待审核 Claim 列表进入审核流程
- 支持查看 Claim 详情、证据详情、审核历史
- 支持提交审核结论并回写审核记录
- 支持最近审核结果回看与定位
- 审核数据按知识库隔离，无权限知识库的历史不可见

### 7. 功能设置

- 支持质检模板查看、增删改（内置 4 套模板 + 本地 YAML 扩展）
- 支持运行配置展示
- 支持用户管理与用户权限管理
- 支持通过二级 tab 切换到"配置管理"、"用户管理"、"用户权限管理"

## 页面结构

当前 Gradio 页面包含以下主要模块：

- `"待开通"`（零权限用户默认入口）
- `"AI 质检"`
- `"人工审核"`
- `"知识库管理"`
- `"知识库检索"`
- `"功能设置"`（含二级 tab：配置管理、用户管理、用户权限管理）

其中 `"AI 质检"` 是当前最完整的工作台页面，已经串起模板、质检、最近记录、Claim 选择、证据查看、效果评测等功能。

## 技术栈

### 后端与接口

- `Python 3.11+`
- `FastAPI`
- `Pydantic / pydantic-settings`

作用说明：

- `FastAPI`：提供健康检查、入库、检索、质检、审核、用户管理等 API
- `Pydantic`：负责请求响应建模与配置校验

### 前端与交互

- `Gradio`

作用说明：

- 提供本地可用的中文操作界面
- 用于承载文档管理、检索、AI 质检、人工审核、功能设置等页面
- 支持暗色/亮色主题自适应

### 数据与索引

- `SQLite`
- `ChromaDB`

作用说明：

- `SQLite`：保存文档元数据、章节、分块、质检记录、审核记录、用户与权限数据，并提供全文检索能力
- `ChromaDB`：保存向量索引，支持语义召回

### AI 与排序

- `LLM`：支持 `disabled`、`openai`、`anthropic`
- `Embedding`：支持本地确定性向量或 OpenAI 兼容接口
- `Rerank`：支持 `dashscope` 或 OpenAI 兼容接口

作用说明：

- `LLM`：负责 Claim 判断、证据关系解释、质检辅助推理
- `Embedding`：负责语义向量召回
- `Rerank`：负责对多路召回结果再排序，提升证据相关性

### 认证

- 基于 Session 的认证机制
- 密码使用安全哈希存储
- 支持登录、注册、登出、刷新令牌

## 目录说明

```text
doc-ai-wiki/
├── "Docs/"                 开发文档目录
├── "Input/"                知识库输入目录（按知识库 ID 分子目录）
├── "config/"               配置文件
├── "rules/"                规则文件
├── "templates/quality/"    质检模板
├── "src/"                  源码
│   ├── "app.py"            FastAPI 主入口
│   ├── "ai/"               AI 客户端（LLM、Embedding、Rerank）
│   ├── "auth/"             认证服务
│   ├── "common/"           公共模块（配置、异常、工具）
│   ├── "db/"               数据库（连接、Schema、Repository）
│   ├── "ingest/"           文档入库
│   ├── "knowledge_base/"   知识库管理
│   ├── "quality/"          质检服务
│   ├── "retrieval/"        检索服务
│   ├── "review/"           审核服务
│   ├── "rules/"            规则引擎
│   └── "ui/"               UI 页面与视图
│       ├── "app.py"        Gradio 启动入口
│       ├── "pages.py"      页面总装配
│       ├── "page_helpers.py"  公共 helper（权限、分页、按钮）
│       ├── "search_page.py"   知识库检索页
│       ├── "settings_page.py"  功能设置页
│       ├── "document_page.py"  文档管理页
│       ├── "quality_page.py"   AI 质检页
│       ├── "review_page.py"    人工审核页
│       └── "viewmodels.py"     视图数据转换
├── "tests/"                测试
│   ├── "unit/"             单元测试
│   └── "integration/"      集成测试
├── "index/"                本地运行期索引与导出目录
├── "pyproject.toml"        项目元数据
├── "readme.md"             项目说明
└── "chat_history.md"       会话记录
```

重点约定：

- `Docs` 只放开发文档，不放知识库业务输入
- `Input` 放待入库或已整理好的知识库源文档，按知识库 ID 分子目录
- `index/app.db`、`index/chroma` 属于本地运行期数据，不建议直接同步到远端仓库
- 如果需要同步知识库内容到 GitHub，应优先同步 `Input`、模板、规则和源码

## 快速开始

### 1. 环境要求

- 操作系统：Windows / Linux / macOS
- Python：`3.11` 或以上
- 推荐使用虚拟环境

### 2. 安装依赖

```bash
python -m pip install -e .
```

如需开发测试依赖：

```bash
python -m pip install -e ".[dev]"
```

### 3. 准备配置

复制环境变量模板：

```bash
copy ".env.example" ".env"
```

或手工创建 `.env`，常用配置如下：

```env
APP_ENV=dev
APP_HOST=127.0.0.1
APP_PORT=8000
GRADIO_PORT=7860
INPUT_ROOT=Input
SQLITE_DB_PATH=index/app.db
CHROMA_PERSIST_DIR=index/chroma
RULES_DIR=rules
TEMPLATES_DIR=templates
EMBEDDING_PROVIDER=openai
LLM_PROVIDER=openai
RERANK_ENABLED=true
```

关键配置说明：

- `INPUT_ROOT`：知识库输入目录
- `SQLITE_DB_PATH`：SQLite 数据库路径
- `CHROMA_PERSIST_DIR`：向量索引持久化目录
- `RULES_DIR`：规则目录
- `TEMPLATES_DIR`：质检模板目录
- `EMBEDDING_PROVIDER`：`local` 或 `openai`
- `LLM_PROVIDER`：`disabled`、`openai`、`anthropic`
- `RERANK_ENABLED`：是否启用重排
- `GRADIO_PORT`：Gradio 页面端口，当前默认 `7860`

## 部署与启动

### 方式一：启动 Gradio 页面

这是最常用的本地使用方式：

```bash
python -m src.ui.app
```

默认访问地址：

- `http://127.0.0.1:7860`

也可以使用已固化场景参数的启动脚本：

```powershell
.\start_gradio_local_7860.ps1
```

```sh
sh "./start_gradio_local_7860.sh"
```

服务器对外启动可使用以下脚本：

```powershell
.\start_gradio_server_80.ps1
```

```sh
sh "./start_gradio_server_80.sh"
```

说明：

- 本地脚本固定使用 `APP_HOST=127.0.0.1`、`GRADIO_PORT=7860`
- 服务器脚本固定使用 `APP_HOST=0.0.0.0`、`GRADIO_PORT=80`
- Linux 或 Windows 使用 `80` 端口时，通常需要管理员或 `root` 权限

适用场景：

- 本地知识库管理
- AI 质检与人工审核
- 页面操作验收

### 方式二：启动 FastAPI 服务

如果需要通过接口调用，可启动 API：

```bash
python -m uvicorn src.app:app --host 127.0.0.1 --port 8000 --reload
```

常用接口：

- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /users`
- `PUT /users/{username}/permissions`
- `POST /ingest/register`
- `POST /ingest/rebuild`
- `GET /ingest/status`
- `GET /search/fulltext`
- `GET /search/vector`
- `GET /search/hybrid`
- `GET /quality/templates`
- `POST /quality/check`
- `GET /quality/result/{check_id}`
- `POST /review/submit`
- `GET /review/list`

### 方式三：同时使用

本地开发时可以：

- 使用 `FastAPI` 做接口调试
- 使用 `Gradio` 做页面操作与验收

如果只做页面使用，直接启动 `Gradio` 即可。

## 输入文档格式

`Input` 目录支持以下常见格式：

- `*.md`
- `*.json`

推荐的 `JSON` 最小格式：

```json
{
  "title": "示例文档",
  "content": "这里是正文内容",
  "edition": "v1",
  "author": "整理者",
  "source": "样本来源",
  "tags": ["古文", "医学"]
}
```

字段说明：

- `title`、`content` 为最小推荐字段
- `source` 与 `source_name` 均可识别
- `tags` 支持单字符串或字符串数组

## 内置质检模板

当前内置模板包括：

- `general_fact_check`：通用事实核检（默认）
- `strict_evidence_check`：严格证据核验
- `ancient_text_review`：古文审慎解读
- `medical_safety_review`：医学内容审慎质检

模板不仅影响提示词，还会联动检索与判定策略，例如：

- `rule_tags`
- `retrieval_policy.fulltext_top_k`
- `retrieval_policy.vector_top_k`
- `retrieval_policy.final_top_k`
- `retrieval_policy.use_rerank`
- `retrieval_policy.neighbor_window`
- `retrieval_policy.include_section_context`

自定义模板目录：

- `templates/quality`

## 权限模型

### 默认权限

- `admin` 用户拥有所有菜单权限和所有知识库权限
- 新注册用户默认无任何菜单权限、无任何知识库权限
- 零权限用户登录后进入"待开通"入口页，不会出现空白主界面

### 权限配置

- 在"功能设置" -> "用户权限管理"中为用户配置权限
- 可配置项：可访问菜单（tab 页）、可访问知识库
- 配置后立即生效，当前登录态无需重新登录即可刷新

### 权限收口

- 所有 API 接口均需要认证，对象级访问会校验知识库权限
- UI 页面按 `tab_names` 与 `kb_ids` 控制可见范围
- 无权限用户看不到对应菜单项，也看不到对应知识库的数据

## 测试与校验

### 运行测试

```bash
python -m pytest tests
```

### 模型连通性自检

```bash
python ".aipython/check_model_connectivity.py"
```

该脚本会检查：

- `LLM`
- `Embedding`
- `Rerank`

输出统一 `JSON` 结果，便于排查模型地址、密钥和模型名配置问题。

### 索引状态检查

```bash
python ".aipython/inspect_index_status.py"
```

适用场景：

- 检查当前数据库与索引状态
- 辅助排查入库是否完整

## 部署建议

### 本地开发

- 优先使用 `Gradio` 页面进行操作和验收
- `Embedding`、`LLM`、`Rerank` 可按需接入在线服务
- 未配置 `LLM` 时系统会降级到更保守的规则与启发式逻辑

### 生产或演示环境

- 建议显式配置 `LLM`、`Embedding`、`Rerank`
- 建议将 `.env` 与密钥文件排除出版本控制
- 建议不要把 `index/app.db`、`index/chroma` 直接作为 Git 仓库内容同步
- 如果需要共享知识库基础数据，优先共享 `Input`、规则文件、模板文件和导出的开发文档

## 当前版本边界

当前 `0.6` 版本已完成以下能力：

- 多知识库隔离管理与数据隔离
- 用户注册、登录、登出、刷新完整认证链路
- 后台用户管理与权限配置
- 零权限用户登录体验修正
- 权限总收口（菜单权限、知识库权限、对象级权限）
- UI 页面结构优化与统一

仍有以下边界未完全覆盖：

- 更复杂的知识图谱能力尚未接入
- PDF/OCR 解析不是当前默认范围
- 多模型投票与大规模调度未做成标准能力
- 质检效果仍依赖知识库质量、模板设计与模型配置
- 运行期索引数据默认走本地目录，不适合直接当作长期版本资产管理

## 相关文档

- `Docs/design.MD`：详细设计
- `Docs/api.MD`：API 设计
- `Docs/tasks.MD`：任务清单
- `Docs/env.MD`：环境说明
- `Docs/acceptance.MD`：验收标准
- `Docs/ui_redesign_design.MD`：UI 设计规范
- `todo.md`：当前开发待办

## 适用场景总结

如果你希望构建一套"中文资料可入库、可检索、可质检、可人工复核"的本地系统，并且需要支持多用户、多知识库协同与精细化权限管理，这个项目已经提供了一个可以直接运行和继续扩展的起点。
