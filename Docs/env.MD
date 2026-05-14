# 中文知识库系统环境配置说明

> **版本**：v1.0
> **日期**：2026-04-30
> **说明**：本文档定义 MVP 开发所需的最小环境变量、默认路径、配置项与本地约定。

---

## 一、环境目标

本环境配置仅覆盖 MVP 开发所需的最小运行条件：

- 本地 Markdown 文档入库
- SQLite 数据库存储
- ChromaDB 向量索引
- Embedding 与 LLM 调用
- 本地 Gradio + FastAPI 开发调试

---

## 二、目录约定

默认工作目录：

- 项目根目录：`c:\Users\patde\Documents\GitHub\doc-ai-wiki`

建议默认路径：

- 文档目录：`Input`
- SQLite 数据库：`index/app.db`
- ChromaDB 目录：`index/chroma`
- 规则目录：`rules`
- 模板目录：`templates`
- 测试数据目录：`tests/fixtures`

---

## 三、最小环境变量

建议使用 `.env` 或等价配置文件管理。

### 3.1 应用基础配置

| 变量名 | 必填 | 默认值 | 说明 |
|------|------|------|------|
| `APP_ENV` | 否 | `dev` | 运行环境 |
| `APP_HOST` | 否 | `127.0.0.1` | 服务监听地址 |
| `APP_PORT` | 否 | `8000` | FastAPI 端口 |
| `GRADIO_PORT` | 否 | `7860` | Gradio 端口 |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |

### 3.2 路径配置

| 变量名 | 必填 | 默认值 | 说明 |
|------|------|------|------|
| `INPUT_ROOT` | 否 | `Input` | 知识库输入目录 |
| `SQLITE_DB_PATH` | 否 | `index/app.db` | SQLite 文件路径 |
| `CHROMA_PERSIST_DIR` | 否 | `index/chroma` | ChromaDB 持久化目录 |
| `RULES_DIR` | 否 | `rules` | 规则目录 |
| `TEMPLATES_DIR` | 否 | `templates` | 模板目录 |

### 3.3 模型与检索配置

| 变量名 | 必填 | 默认值 | 说明 |
|------|------|------|------|
| `EMBEDDING_PROVIDER` | 否 | `local` | Embedding 提供方，支持 `local` / `openai` |
| `EMBEDDING_MODEL` | 否 | `deterministic-v1` | Embedding 模型名 |
| `EMBEDDING_BASE_URL` | 否 | 空 | OpenAI 兼容 Embedding 地址 |
| `EMBEDDING_API_KEY` | 条件必填 | 空 | 在线 Embedding 密钥 |
| `EMBEDDING_TIMEOUT_SECONDS` | 否 | `180` | Embedding 超时秒数，大文档向量重建建议保持较高值 |
| `RERANK_ENABLED` | 否 | `true` | 是否启用重排 |
| `RERANK_PROVIDER` | 否 | `dashscope` | 重排提供方，支持 `dashscope` / `openai` |
| `RERANK_MODEL` | 否 | `default` | 重排模型名 |
| `RERANK_BASE_URL` | 否 | 空 | 自定义重排服务地址 |
| `RERANK_API_KEY` | 条件必填 | 空 | 重排密钥；为空时自动降级为关闭 |
| `RERANK_TIMEOUT_SECONDS` | 否 | `60` | 重排超时秒数 |
| `LLM_PROVIDER` | 否 | `disabled` | 主 LLM 提供方，支持 `disabled` / `openai` / `anthropic` |
| `LLM_BASE_URL` | 否 | 空 | OpenAI 兼容或 Anthropic 自定义地址 |
| `LLM_API_KEY` | 条件必填 | 空 | LLM 统一密钥入口 |
| `LLM_MODEL` | 否 | `disabled` | 主 LLM 模型名 |
| `LLM_TIMEOUT_SECONDS` | 否 | `60` | LLM 超时秒数 |
| `LLM_MAX_TOKENS` | 否 | `1024` | LLM 最大输出 token |
| `LLM_TEMPERATURE` | 否 | `0` | LLM 温度 |
| `LLM_TOP_P` | 否 | `1` | LLM top_p |
| `LLM_ENABLE_THINKING` | 否 | `false` | OpenAI 兼容推理模型是否开启 thinking |
| `ANTHROPIC_API_VERSION` | 否 | `2023-06-01` | Anthropic API 版本头 |

### 3.4 密钥配置

| 变量名 | 必填 | 说明 |
|------|------|------|
| `DASHSCOPE_API_KEY` | 条件必填 | 使用 DashScope 时必填 |
| `ANTHROPIC_API_KEY` | 条件必填 | 使用 Claude 时必填 |
| `OPENAI_API_KEY` | 条件必填 | 使用 OpenAI 兼容服务时必填 |
| `COHERE_API_KEY` | 条件必填 | 使用 Cohere Rerank 时必填 |

---

## 四、推荐配置文件

建议至少准备以下配置文件：

- `config/app_config.yaml`
- `config/llm_config.yaml`
- `config/logging.yaml`
- `.env`

### 4.1 app_config.yaml 建议项

- 默认分页大小
- 默认 `top_k`
- 是否启用缓存
- 最大文本长度
- 默认质检模板
- 重试次数

### 4.2 llm_config.yaml 建议项

- 主模型
- 备用模型
- Embedding 模型
- 重排模型
- 超时时间
- 成本阈值

### 4.3 logging.yaml 建议项

- 控制台日志格式
- 文件日志路径
- 错误日志分流
- 第三方库日志级别

---

## 五、本地开发最小配置示例

```env
APP_ENV=dev
APP_HOST=127.0.0.1
APP_PORT=8000
GRADIO_PORT=7860
LOG_LEVEL=INFO
INPUT_ROOT=Input
SQLITE_DB_PATH=index/app.db
CHROMA_PERSIST_DIR=index/chroma
RULES_DIR=rules
TEMPLATES_DIR=templates
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_TIMEOUT_SECONDS=180
RERANK_ENABLED=true
RERANK_PROVIDER=dashscope
RERANK_MODEL=default
RERANK_BASE_URL=
RERANK_API_KEY=your_rerank_api_key
RERANK_TIMEOUT_SECONDS=60
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your_llm_api_key
LLM_MODEL=gpt-4.1-mini
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=1024
LLM_TEMPERATURE=0
LLM_TOP_P=1
LLM_ENABLE_THINKING=false
ANTHROPIC_API_VERSION=2023-06-01
```

---

## 六、开发阶段约束

- 不在代码中硬编码 API Key
- 不在代码中硬编码绝对路径
- 路径优先从环境变量或配置文件读取
- 所有外部服务调用都必须加异常处理和超时
- 数据库路径变更后必须可通过配置切换
- 可通过 `python ".aipython/check_model_connectivity.py"` 同时检查 `LLM/Embedding/Rerank` 连通性

---

## 七、测试环境建议

测试环境建议单独使用以下配置：

- 测试数据库：`index/test_app.db`
- 测试 Chroma 目录：`index/test_chroma`
- 测试输入目录：`tests/fixtures/docs`
- 测试规则目录：`tests/fixtures/rules`

建议增加以下环境变量：

| 变量名 | 说明 |
|------|------|
| `TEST_SQLITE_DB_PATH` | 测试数据库路径 |
| `TEST_CHROMA_PERSIST_DIR` | 测试向量目录 |
| `TEST_INPUT_ROOT` | 测试输入目录 |

---

## 八、默认运行方式建议

本地开发建议分两类运行：

### 8.1 后端接口

- FastAPI 提供接口服务
- 默认端口 `8000`
- 启动命令：`python -m uvicorn src.app:app --host 127.0.0.1 --port 8000 --reload`

### 8.2 前端工具界面

- Gradio 提供操作界面
- 默认端口 `7860`
- 启动命令：`python -m src.ui.app`

说明：

- 前后端可分开运行
- 也可以由一个主进程统一启动
- 当前最小 UI 已支持：
- 扫描 `Input` 目录中的 `md/json`
- 注册选中文档或全部文档
- 查看入库状态与重建索引
- 执行检索、质检与人工审核

---

## 九、最低就绪条件

开始编码前，建议至少确认以下内容：

- 已准备好 Markdown 样本文档
- 已准备好 OpenAI 兼容或 Anthropic LLM 密钥
- 已确认 Embedding 使用在线模型还是本地回退
- 已确认 SQLite 和 Chroma 持久化目录
- 已确认默认模板与规则目录
- 已确定测试数据目录

满足以上条件后，即可进入 MVP 编码阶段。
