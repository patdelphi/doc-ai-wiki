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

- 项目根目录：`c:\Users\patde\Documents\GitHub\wiki-donge`

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
| `EMBEDDING_PROVIDER` | 否 | `dashscope` | Embedding 提供方 |
| `EMBEDDING_MODEL` | 否 | `text-embedding-v3` | Embedding 模型名 |
| `RERANK_ENABLED` | 否 | `true` | 是否启用重排 |
| `RERANK_PROVIDER` | 否 | `dashscope` | 重排提供方 |
| `RERANK_MODEL` | 否 | `default` | 重排模型名 |
| `LLM_PROVIDER` | 否 | `qwen` | 主 LLM 提供方 |
| `LLM_MODEL` | 否 | `qwen-max` | 主 LLM 模型名 |
| `LLM_TIMEOUT_SECONDS` | 否 | `60` | LLM 超时秒数 |

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
EMBEDDING_PROVIDER=dashscope
EMBEDDING_MODEL=text-embedding-v3
RERANK_ENABLED=true
RERANK_PROVIDER=dashscope
LLM_PROVIDER=qwen
LLM_MODEL=qwen-max
LLM_TIMEOUT_SECONDS=60
DASHSCOPE_API_KEY=your_api_key_here
```

---

## 六、开发阶段约束

- 不在代码中硬编码 API Key
- 不在代码中硬编码绝对路径
- 路径优先从环境变量或配置文件读取
- 所有外部服务调用都必须加异常处理和超时
- 数据库路径变更后必须可通过配置切换

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

### 8.2 前端工具界面

- Gradio 提供操作界面
- 默认端口 `7860`

说明：

- 前后端可分开运行
- 也可以由一个主进程统一启动
- 具体启动方式后续由代码骨架决定

---

## 九、最低就绪条件

开始编码前，建议至少确认以下内容：

- 已准备好 Markdown 样本文档
- 已准备好 DashScope 或等价模型密钥
- 已确认 SQLite 和 Chroma 持久化目录
- 已确认默认模板与规则目录
- 已确定测试数据目录

满足以上条件后，即可进入 MVP 编码阶段。