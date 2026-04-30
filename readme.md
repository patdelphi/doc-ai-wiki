# 中文知识库系统 MVP

## 项目说明

本项目用于构建一个面向中文内容的知识库系统，当前 MVP 已支持：

- Markdown 文档入库
- SQLite 元数据与 FTS5 全文检索
- ChromaDB 向量索引
- 混合检索
- AI 质检
- 规则命中与风险分级
- 人工审核
- Gradio 最小操作界面

## 目录约定

- `Docs`：开发文档目录，只存方案、设计、接口、任务等文档
- `Input`：知识库原始文档目录，存放已处理好的 `md`、`json` 等业务输入文件
- `src`：项目源码
- `tests`：自动化测试
- `config`：配置文件
- `index`：SQLite 与 ChromaDB 本地索引数据

## 环境准备

建议使用 Python `3.11+`。

安装依赖：

```bash
python -m pip install -e .
```

如果只做本地开发，也可以：

```bash
python -m pip install fastapi uvicorn chromadb gradio pydantic pydantic-settings pyyaml pytest httpx
```

## 配置说明

可参考：

- `.env.example`
- `Docs/env.MD`

关键配置项：

- `INPUT_ROOT`：知识库输入目录，默认 `Input`
- `SQLITE_DB_PATH`：SQLite 数据库路径
- `CHROMA_PERSIST_DIR`：ChromaDB 持久化目录
- `RULES_DIR`：规则目录
- `TEMPLATES_DIR`：模板目录

## 启动 FastAPI

```bash
python -m uvicorn src.app:app --host 127.0.0.1 --port 8000 --reload
```

常用接口：

- `GET /health`
- `POST /ingest/register`
- `POST /ingest/rebuild`
- `GET /ingest/status`
- `GET /search/fulltext`
- `GET /search/vector`
- `GET /search/hybrid`
- `POST /quality/check`
- `GET /quality/result/{check_id}`
- `POST /review/submit`
- `GET /review/list`

## 启动 Gradio

```bash
python -m src.ui.app
```

启动后可使用最小页面：

- 文档管理：扫描 `Input`、注册文档、查看入库状态
- 文档检索：执行混合检索
- AI 质检：执行 claim 质检并生成可审核 claim 列表
- 人工审核：直接选择 claim 并提交审核结果
- 文档状态：注册后自动刷新可重建列表，并显示 `edition/author/source_name/tags`

## Input 使用方式

`Input` 目录是知识库输入目录，不是开发文档目录。

推荐放置：

- `*.md`
- `*.json`

`JSON` 最小推荐格式：

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

说明：

- `title`、`content` 为最小推荐字段
- `source` 与 `source_name` 都可识别
- `tags` 支持单个字符串或字符串数组

示例：

```text
Input/
├── a1.md
└── a2.json
```

当前 UI 的“扫描 Input 文档”会读取该目录下的 `md/json` 文件。

## 测试

运行当前测试：

```bash
python -m pytest tests
```

## 当前状态

当前 MVP 已完成基础开发链路，后续建议继续补：

- 更细的规则包
- 更丰富的审核视图
- 更完整的 JSON 元数据映射
- 更完整的部署与运行文档
