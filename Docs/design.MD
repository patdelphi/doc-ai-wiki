# 中文知识库系统详细设计

> **版本**：v1.0
> **日期**：2026-04-30
> **适用范围**：Markdown 已准备完成后的系统设计
> **说明**：本文档用于支撑 `Docs/tasks.MD` 的开发落地，重点描述模块边界、数据结构、核心流程、事务与异常处理策略。

---

## 一、设计目标

本阶段系统设计只服务以下目标：

- 将已有 Markdown 文档稳定入库
- 建立可追溯的元数据、全文索引、向量索引
- 提供全文检索、语义检索、融合检索能力
- 支持对输入文本进行 claim 拆分与证据核验
- 支持规则校验、人工审核、审核记录查询
- 为后续扩展图谱、多版本比对、API 开放保留边界

本阶段明确不设计以下内容：

- PDF 解析流程
- OCR 流程
- 知识图谱落库与图查询
- 多模型投票常态化调度
- 默认整篇文档长上下文注入

---

## 二、总体架构

```text
Gradio 前端
  ├─ 文档管理页
  ├─ 文档检索页
  ├─ AI 质检台
  └─ 审核记录页

FastAPI 服务层
  ├─ 文档入库模块 ingest
  ├─ 元数据模块 metadata
  ├─ 分块模块 chunking
  ├─ 检索模块 retrieval
  ├─ 规则模块 rules
  ├─ 质检模块 quality
  ├─ 审核模块 review
  └─ 公共基础模块 common

存储层
  ├─ Markdown 文件目录
  ├─ SQLite
  │   ├─ 元数据表
  │   ├─ 全文索引表
  │   ├─ 质检记录表
  │   └─ 审核记录表
  └─ ChromaDB
      └─ 向量索引集合
```

### 2.1 设计原则

- 单一职责：每个模块只负责一个清晰职责
- 可追溯：每条检索结果和质检结果都必须能追溯到原文位置
- 可回滚：数据库写入必须以事务保护，避免半成功状态
- 可降级：任一外部依赖失败时，都有退化路径
- 可测试：模块边界清晰，便于编写单元测试和集成测试

---

## 三、建议目录结构

```text
wiki-donge/
├── Docs/
│   ├── tasks.MD
│   ├── design.MD
│   └── api.MD
├── config/
│   ├── app_config.yaml
│   ├── llm_config.yaml
│   └── logging.yaml
├── data/
│   ├── docs/
│   ├── entities/
│   └── fixtures/
├── index/
│   ├── chroma/
│   └── app.db
├── review/
├── rules/
├── src/
│   ├── app.py
│   ├── common/
│   │   ├── config.py
│   │   ├── errors.py
│   │   ├── logger.py
│   │   ├── models.py
│   │   └── utils.py
│   ├── db/
│   │   ├── connection.py
│   │   ├── repositories.py
│   │   └── transaction.py
│   ├── ingest/
│   │   ├── scanner.py
│   │   ├── registrar.py
│   │   ├── normalizer.py
│   │   └── service.py
│   ├── metadata/
│   │   ├── extractor.py
│   │   ├── resolver.py
│   │   └── service.py
│   ├── chunking/
│   │   ├── splitter.py
│   │   ├── builder.py
│   │   └── service.py
│   ├── retrieval/
│   │   ├── fulltext.py
│   │   ├── vector.py
│   │   ├── fusion.py
│   │   ├── reranker.py
│   │   └── service.py
│   ├── rules/
│   │   ├── loader.py
│   │   ├── matcher.py
│   │   ├── dosage.py
│   │   └── service.py
│   ├── quality/
│   │   ├── claim_parser.py
│   │   ├── entity_parser.py
│   │   ├── context_builder.py
│   │   ├── orchestrator.py
│   │   └── service.py
│   ├── review/
│   │   ├── records.py
│   │   ├── workflow.py
│   │   └── service.py
│   └── ui/
│       ├── pages.py
│       └── viewmodels.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── todo.md
└── chat_history.md
```

---

## 四、模块设计

## 4.1 common 模块

职责：

- 配置加载
- 错误定义
- 日志封装
- 通用数据模型
- 时间、哈希、文本工具函数

边界：

- 不直接依赖具体业务表
- 不包含业务判断逻辑

关键对象：

- `AppConfig`
- `LLMConfig`
- `AppError`
- `ValidationError`
- `ExternalServiceError`
- `TransactionError`

## 4.2 db 模块

职责：

- 管理 SQLite 连接
- 提供事务上下文
- 封装 repository 层数据库访问

边界：

- 不做业务编排
- 不直接调用 LLM、ChromaDB

关键约束：

- 所有写操作必须通过事务包装
- repository 只负责 CRUD，不负责业务流程

## 4.3 ingest 模块

职责：

- 扫描 Markdown 文件
- 识别新增、已存在、已变更文档
- 调用标准化和元数据模块完成入库前准备
- 将文档记录写入数据库

输入：

- Markdown 文件路径
- 入库配置

输出：

- 文档注册记录
- 标准化文本
- 入库状态

边界：

- 不负责分块与索引实现
- 只触发后续流程，不承担检索逻辑

## 4.4 metadata 模块

职责：

- 从 Markdown 解析文献名称、版本、章节、页码、段落信息
- 解析文档逻辑层级
- 生成统一主键字段

关键输出：

- `doc_id`
- `edition`
- `section_id`
- `source_span`
- `page_no`

边界：

- 不负责全文索引
- 不负责向量索引

## 4.5 chunking 模块

职责：

- 按语义边界切分 Markdown 文本
- 构造 chunk 元数据
- 保证 chunk 与原文位置映射一致

切块策略：

- 先按标题层级切分
- 再按条目、专题段落、注释块细分
- 对超长段落做保守二次切分
- 禁止简单按固定字数粗暴截断

边界：

- 不直接写入向量库
- 不负责检索排序

## 4.6 retrieval 模块

职责：

- 提供全文检索
- 提供向量检索
- 融合全文与向量结果
- 必要时调用重排服务

子模块职责：

- `fulltext.py`：FTS5 查询
- `vector.py`：ChromaDB 查询
- `fusion.py`：去重、合并、打分归一
- `reranker.py`：对候选结果进行二次排序
- `service.py`：统一对外提供检索能力

边界：

- 不负责 claim 解析
- 不负责规则判断

## 4.7 rules 模块

职责：

- 加载 YAML 规则
- 执行实体匹配、单位换算、固定规则校验
- 输出结构化规则命中结果

首批规则：

- 引用完整性规则
- 标题与结构一致性规则
- 术语规范化规则
- 数字与单位格式规则
- 可选领域规则包

边界：

- 不负责生成最终自然语言解释
- 不依赖检索结果即可独立运行

## 4.8 quality 模块

职责：

- 对输入文本拆分 claim
- 提取实体
- 调用规则模块
- 调用检索模块
- 组织证据上下文
- 调用 LLM 生成结构化判断结果
- 做结果解析与失败重试

子模块职责：

- `claim_parser.py`：claim 拆分
- `entity_parser.py`：实体提取
- `context_builder.py`：证据组织
- `orchestrator.py`：主编排流程

边界：

- 不直接管理审核状态
- 不直接操作前端视图

## 4.9 review 模块

职责：

- 保存审核动作
- 保存人工修改后的 verdict 与备注
- 查询历史审核记录
- 提供审核统计基础数据

边界：

- 不负责重新触发索引
- 不负责规则执行

## 4.10 ui 模块

职责：

- 对外展示检索、质检、审核页面
- 封装表单输入和结果展示模型

边界：

- 不直接访问数据库
- 通过 service 层调用后端逻辑

---

## 五、核心数据模型

## 5.1 文档主键策略

统一主键如下：

- `doc_id`：文献逻辑 ID
- `edition`：版本标识
- `doc_uid`：`doc_id + edition` 组合后的唯一标识
- `section_id`：章节或条文 ID
- `chunk_id`：分块 ID
- `review_id`：审核记录 ID
- `check_id`：一次质检任务 ID

设计原则：

- 文献逻辑实体与文献具体版本分离
- 所有检索和审核都绑定到具体版本
- 所有结果必须能回到 chunk 级别

## 5.2 关键对象定义

### DocumentRecord

```json
{
  "doc_uid": "zhongguo_wenxue_v1",
  "doc_id": "zhongguo_wenxue",
  "doc_title": "中国文学史纲要",
  "edition": "第一版",
  "source_path": "Input/中国文学史纲要/中国文学史纲要_v1.MD",
  "source_hash": "sha256_xxx",
  "status": "indexed",
  "created_at": "2026-04-30T10:00:00",
  "updated_at": "2026-04-30T10:30:00"
}
```

### ChunkRecord

```json
{
  "chunk_id": "zhongguo_wenxue_v1_0001",
  "doc_uid": "zhongguo_wenxue_v1",
  "section_id": "chapter_01_section_02",
  "page_no": 12,
  "chunk_type": "paragraph",
  "content": "先秦典籍在文体与叙述方式上呈现出明显差异......",
  "source_span": "第一章 第二节",
  "entities": ["先秦", "典籍", "文体"]
}
```

### CheckResult

```json
{
  "check_id": "chk_20260430_0001",
  "claim": "《论语》成书于春秋战国之际",
  "verdict": "verified",
  "confidence": 0.93,
  "reason": "知识库中存在明确原文支持",
  "evidence": "《论语》由孔子弟子及再传弟子编纂而成，约成书于春秋战国之际......",
  "source_doc": "中国哲学史",
  "source_span": "第一章",
  "retrieval_refs": ["chunk_101", "chunk_134"],
  "review_required": false
}
```

---

## 六、SQLite 数据表设计

说明：以下为逻辑表设计，字段类型可根据 Python ORM 或原生 SQL 实现微调。

## 6.1 documents

用途：保存文档注册信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| doc_uid | TEXT UNIQUE | 文档唯一标识 |
| doc_id | TEXT | 文献逻辑 ID |
| doc_title | TEXT | 文献标题 |
| edition | TEXT | 版本 |
| source_path | TEXT | Markdown 路径 |
| source_hash | TEXT | 文件内容哈希 |
| ingest_status | TEXT | 入库状态 |
| index_status | TEXT | 索引状态 |
| error_message | TEXT | 失败原因 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

索引建议：

- `idx_documents_doc_id`
- `idx_documents_status`
- `idx_documents_source_hash`

## 6.2 document_sections

用途：保存章节、条文、段落层级信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| doc_uid | TEXT | 文档标识 |
| section_id | TEXT | 章节 ID |
| parent_section_id | TEXT | 父章节 ID |
| level | INTEGER | 标题层级 |
| title | TEXT | 标题 |
| page_no | INTEGER | 页码 |
| order_no | INTEGER | 排序号 |
| source_span | TEXT | 原文位置描述 |

## 6.3 chunks

用途：保存分块后的结构化内容。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| chunk_id | TEXT UNIQUE | 分块 ID |
| doc_uid | TEXT | 文档标识 |
| section_id | TEXT | 所属章节 |
| page_no | INTEGER | 页码 |
| chunk_type | TEXT | 分块类型 |
| content | TEXT | 分块文本 |
| content_hash | TEXT | 分块哈希 |
| source_span | TEXT | 原文位置 |
| entity_json | TEXT | 实体 JSON |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

## 6.4 chunk_fts

用途：FTS5 全文索引虚拟表。

建议字段：

- `chunk_id`
- `content`
- `doc_title`
- `edition`
- `source_span`

说明：

- `chunk_fts` 只做检索，不作为事实主表
- 主数据仍以 `chunks` 表为准

## 6.5 ingest_jobs

用途：记录入库任务执行过程。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| job_id | TEXT UNIQUE | 任务 ID |
| doc_uid | TEXT | 文档标识 |
| stage | TEXT | 当前阶段 |
| status | TEXT | 执行状态 |
| message | TEXT | 说明信息 |
| started_at | TEXT | 开始时间 |
| finished_at | TEXT | 结束时间 |

## 6.6 quality_checks

用途：保存一次质检请求的主记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| check_id | TEXT UNIQUE | 质检 ID |
| template_id | TEXT | 质检模板 |
| input_text | TEXT | 用户输入 |
| status | TEXT | 质检状态 |
| model_name | TEXT | 主模型 |
| total_claims | INTEGER | claim 总数 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

## 6.7 quality_claims

用途：保存每条 claim 的分析结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| check_id | TEXT | 质检 ID |
| claim_no | INTEGER | claim 序号 |
| claim_text | TEXT | claim 内容 |
| verdict | TEXT | 结论 |
| confidence | REAL | 置信度 |
| reason | TEXT | 原因 |
| evidence | TEXT | 证据内容 |
| source_doc | TEXT | 来源文献 |
| source_span | TEXT | 来源位置 |
| retrieval_refs | TEXT | chunk 引用 JSON |
| review_required | INTEGER | 是否需要人工复核 |

## 6.8 rule_hits

用途：保存规则命中结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| check_id | TEXT | 质检 ID |
| claim_no | INTEGER | claim 序号 |
| rule_id | TEXT | 规则 ID |
| rule_name | TEXT | 规则名称 |
| severity | TEXT | 严重级别 |
| matched_entities | TEXT | 命中实体 JSON |
| source | TEXT | 规则来源 |
| suggestion | TEXT | 建议 |
| created_at | TEXT | 创建时间 |

## 6.9 review_records

用途：保存人工审核动作。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| review_id | TEXT UNIQUE | 审核 ID |
| check_id | TEXT | 质检 ID |
| claim_no | INTEGER | claim 序号 |
| original_verdict | TEXT | 原始结论 |
| reviewed_verdict | TEXT | 审核后结论 |
| action | TEXT | 通过、驳回、修改 |
| comment | TEXT | 审核备注 |
| reviewer | TEXT | 审核人 |
| created_at | TEXT | 创建时间 |

---

## 七、ChromaDB 集合设计

建议使用单集合模式：

- 集合名：`knowledge_chunks`

每条向量记录元数据建议包含：

- `chunk_id`
- `doc_uid`
- `doc_title`
- `edition`
- `section_id`
- `page_no`
- `chunk_type`
- `source_span`

原因：

- 文档规模前期较小，单集合更易维护
- 检索时可通过 metadata 做过滤
- 后续需要拆分多集合时可平滑迁移

---

## 八、核心流程设计

## 8.1 Markdown 入库流程

```text
扫描 Markdown 文件
  -> 计算文件哈希
  -> 检查 documents 是否已存在
  -> 若未变化则跳过
  -> 若新增或变更则开始事务
  -> 标准化文本
  -> 抽取元数据
  -> 写入 documents / document_sections
  -> 提交事务
  -> 分块
  -> 写入 chunks
  -> 更新 FTS5
  -> 写入 ChromaDB
  -> 更新 index_status = indexed
```

关键点：

- 文档注册与元数据写入走同一事务
- 向量写入不与 SQLite 共事务，因此需要状态补偿
- ChromaDB 写入失败时，SQLite 中将 `index_status` 标为 `partial_failed`

## 8.2 检索流程

```text
接收查询
  -> 查询预处理
  -> 执行全文检索
  -> 执行向量检索
  -> 合并去重
  -> 可选重排
  -> 构造统一引用结构
  -> 返回前端或质检模块
```

关键点：

- 全文检索和向量检索可并行
- 重排失败不影响主流程
- 统一输出引用结构，减少上层重复处理

## 8.3 质检流程

```text
输入文本
  -> claim 拆分
  -> claim 实体提取
  -> 规则校验
  -> 对未被硬规则拦截的 claim 执行检索
  -> 构造证据上下文
  -> 调用 LLM 输出结构化结果
  -> 校验 JSON 结构
  -> 持久化 quality_checks / quality_claims / rule_hits
  -> 返回前端
```

关键点：

- 规则模块优先执行，避免无效 LLM 调用
- 没有证据不得输出 `verified`
- 低置信度自动标记人工复核

## 8.4 审核流程

```text
读取质检结果
  -> 用户点击通过 / 驳回 / 修改
  -> 写入 review_records
  -> 更新对应 claim 的审核状态
  -> 返回最新审核结果
```

关键点：

- 审核动作不可覆盖原始模型输出
- 原始 verdict 与审核后 verdict 必须同时保留

---

## 九、事务设计

## 9.1 必须走事务的场景

- 文档注册
- 元数据写入
- sections 写入
- chunks 主表写入
- quality_checks 与 quality_claims 批量写入
- review_records 写入

## 9.2 事务边界建议

### 文档入库事务

事务内：

- 写 documents
- 写 document_sections
- 更新 ingest_jobs

事务外：

- ChromaDB 向量写入
- 外部 embedding 调用

原因：

- SQLite 与外部向量库无法做真正分布式事务
- 应通过状态字段实现补偿，而不是强行捆绑

### 质检写入事务

事务内：

- 写 quality_checks
- 写 quality_claims
- 写 rule_hits

要求：

- 任一 claim 落库失败时，整次质检记录回滚

---

## 十、异常处理设计

## 10.1 错误分类

建议错误分为以下几类：

- `ValidationError`：输入校验失败
- `NotFoundError`：数据不存在
- `DatabaseError`：数据库异常
- `ExternalServiceError`：模型或重排服务失败
- `IndexingError`：索引构建失败
- `BusinessRuleError`：业务约束异常

## 10.2 统一错误返回结构

```json
{
  "success": false,
  "error_code": "INDEXING_ERROR",
  "message": "向量索引写入失败",
  "details": {
    "doc_uid": "zhongguo_wenxue_v1",
    "stage": "vector_index"
  }
}
```

## 10.3 模块级降级策略

- FTS5 可用、向量检索失败：退化为全文检索
- 向量可用、重排失败：退化为融合排序
- LLM 输出结构化失败：触发一次重试
- 连续失败：标记 `manual_review_required`

---

## 十一、缓存设计

当前阶段只做轻量缓存。

## 11.1 缓存对象

- embedding 结果缓存
- 热门检索结果缓存
- 规则文件加载缓存

## 11.2 缓存键建议

- embedding：`emb:{model}:{sha256(text)}`
- search：`search:{query_hash}:{filters_hash}`
- rules：`rules:{file_hash}`

## 11.3 缓存边界

- 不缓存审核动作
- 不缓存最终数据库写结果
- 规则文件修改后必须自动失效

---

## 十二、接口职责划分

说明：详细请求响应体放到 `api.MD`，这里仅定义职责边界。

### 12.1 入库相关

- `POST /ingest/register`：注册一个或多个 Markdown 文档
- `POST /ingest/rebuild`：重建指定文档索引
- `GET /ingest/status`：查询入库与索引状态

### 12.2 检索相关

- `GET /search/fulltext`：全文检索
- `GET /search/vector`：向量检索
- `GET /search/hybrid`：混合检索

### 12.3 质检相关

- `POST /quality/check`：提交质检文本
- `GET /quality/result/{check_id}`：获取质检结果

### 12.4 审核相关

- `POST /review/submit`：提交审核动作
- `GET /review/list`：查询审核记录

---

## 十三、测试设计

## 13.1 单元测试重点

- 元数据抽取
- 分块逻辑
- 规则匹配
- 融合排序
- 输出结构校验

## 13.2 集成测试重点

- Markdown 入库到 SQLite + ChromaDB
- 检索主链路
- 质检主链路
- 审核落库流程

## 13.3 回归测试重点

- 规则误报与漏报
- 检索命中率变化
- claim verdict 准确率变化

---

## 十四、后续扩展预留

当前设计已为以下方向保留扩展位：

- `metadata` 模块可扩展多版本对照
- `retrieval` 模块可扩展图谱检索入口
- `quality` 模块可扩展争议内容二次模型判断
- `review` 模块可扩展审核反馈反哺 prompt 或规则

但当前阶段不实现，以避免范围失控。

---

## 十五、开发建议

建议按以下顺序编码：

1. `common` + `db`
2. `ingest` + `metadata`
3. `chunking`
4. `retrieval`
5. `rules`
6. `quality`
7. `review`
8. `ui`

建议按以下顺序补测试：

1. 元数据抽取测试
2. 分块测试
3. FTS5 检索测试
4. 融合检索测试
5. 规则命中测试
6. 质检输出结构测试
7. 审核持久化测试

如果下一步继续写 `api.MD`，就以本设计中的模块边界和表结构作为接口定义基础。
