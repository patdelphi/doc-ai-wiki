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
- `LLM_PROVIDER`：`disabled`、`openai`、`anthropic`
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`：LLM 在线调用配置
- `LLM_ENABLE_THINKING`：OpenAI 兼容推理模型是否开启 thinking，默认建议 `false`
- `EMBEDDING_PROVIDER`：`local` 或 `openai`
- `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL`：Embedding 配置
- `RERANK_ENABLED` / `RERANK_PROVIDER` / `RERANK_MODEL`：候选重排配置，支持 `dashscope` / `openai`
- `RERANK_BASE_URL` / `RERANK_API_KEY`：自定义重排服务地址与密钥；未配置密钥时自动降级为关闭

当前建议：

- `LLM` 生产环境优先使用在线 API，通过 `.env` 在 `openai` / `anthropic` 间切换
- `Embedding` 优先使用在线模型；测试和离线开发默认回退到本地确定性向量

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
- `GET /quality/templates`
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
- 文档检索：执行混合检索，并展示 `doc_title/author/source_name/tags`
- 混合检索：支持 `use_rerank` 开关；命中多路召回时会返回 `matched_sources`，启用重排后会返回 `rerank_score`
- AI 质检：执行 `2000` 字以内 claim 质检，可按 `doc_uid` 限制证据范围，并支持切换预设 Prompt 模板
- 人工审核：可直接选择 claim，查看 claim 摘要区和证据表后再提交审核结果；提交后会自动刷新当前 claim 状态、最近质检结果和最近审核记录
- 审核定位：支持从“最近审核记录”下拉中直接定位回对应 claim，减少手工查找
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

当前内置质检模板：

- `general_fact_check`：通用事实核检
- `strict_evidence_check`：严格证据核验
- `ancient_text_review`：古文审慎解读
- `medical_safety_review`：医学内容审慎质检

模板不仅切换 Prompt，还会联动质检策略：

- `rule_tags`：控制当前模板会启用哪些规则包
- `retrieval_policy.fulltext_top_k`：控制全文检索候选数
- `retrieval_policy.vector_top_k`：控制向量检索候选数
- `retrieval_policy.final_top_k`：控制最终送入质检的证据条数
- `retrieval_policy.use_rerank`：控制当前模板在质检检索时是否启用重排
- `retrieval_policy.neighbor_window`：控制是否补邻接 chunk 上下文
- `retrieval_policy.include_section_context`：控制是否补章节级上下文摘要

自定义模板文件放在 `"templates/quality"` 下，支持使用同名 `template_id` 覆盖内置模板。

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

模型连通性自检：

```bash
python ".aipython/check_model_connectivity.py"
```

说明：

- 该脚本会读取当前 `.env`
- 该脚本会分别测试 `LLM`、`Embedding` 与 `Rerank`
- 输出统一的 `JSON` 结果，便于排查模型地址、密钥和模型名是否可用

## 当前状态

当前 MVP 已完成基础开发链路，后续建议继续补：

- 更细的规则包
- 更丰富的审核视图
- 更完整的 JSON 元数据映射
- 更完整的部署与运行文档
