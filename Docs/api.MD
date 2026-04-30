# 中文知识库系统 API 设计

> **版本**：v1.0
> **日期**：2026-04-30
> **适用范围**：Markdown 已准备完成后的中文知识库系统
> **说明**：本文档基于 `tasks.MD` 与 `design.MD`，定义文档入库、检索、质检、审核相关接口。

---

## 一、设计原则

- 所有接口返回 JSON
- 所有写操作必须具备异常处理
- 所有数据库写操作必须走事务
- 所有接口都返回统一响应结构
- 所有高风险结论都必须返回证据来源
- 所有列表接口默认支持分页

---

## 二、统一响应结构

## 2.1 成功响应

```json
{
  "success": true,
  "message": "ok",
  "data": {},
  "request_id": "req_20260430_0001"
}
```

## 2.2 失败响应

```json
{
  "success": false,
  "message": "向量索引写入失败",
  "error_code": "INDEXING_ERROR",
  "details": {
    "doc_uid": "zhongguo_wenxue_v1",
    "stage": "vector_index"
  },
  "request_id": "req_20260430_0001"
}
```

## 2.3 分页结构

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100
  }
}
```

---

## 三、错误码约定

| 错误码 | 说明 |
|------|------|
| `VALIDATION_ERROR` | 输入参数校验失败 |
| `NOT_FOUND` | 资源不存在 |
| `DATABASE_ERROR` | 数据库异常 |
| `INDEXING_ERROR` | 索引构建失败 |
| `EXTERNAL_SERVICE_ERROR` | 模型或重排服务失败 |
| `RULE_ENGINE_ERROR` | 规则执行失败 |
| `QUALITY_CHECK_ERROR` | 质检流程失败 |
| `REVIEW_ERROR` | 审核流程失败 |
| `INTERNAL_ERROR` | 未分类内部异常 |

---

## 四、通用字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `doc_uid` | string | 文档唯一标识 |
| `doc_id` | string | 文献逻辑 ID |
| `doc_title` | string | 文档标题 |
| `edition` | string | 版本 |
| `author` | string | 作者或整理者 |
| `source_name` | string | 来源名称 |
| `tags` | string[] | 标签列表 |
| `section_id` | string | 章节 ID |
| `chunk_id` | string | 分块 ID |
| `source_span` | string | 原文位置 |
| `check_id` | string | 质检任务 ID |
| `review_id` | string | 审核记录 ID |

---

## 五、文档入库接口

## 5.1 注册文档

- 方法：`POST`
- 路径：`/ingest/register`
- 说明：注册一个或多个 Markdown / JSON 文档，并触发元数据抽取、分块、索引流程

### 请求体

```json
{
  "documents": [
    {
      "file_path": "Input/中国文学史纲要/中国文学史纲要_v1.MD",
      "doc_title": "中国文学史纲要",
      "edition": "第一版",
      "author": "张三",
      "source_name": "古籍整理库",
      "tags": ["古文", "文学"]
    }
  ],
  "rebuild_if_exists": false
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `documents` | 是 | 待注册文档列表 |
| `file_path` | 是 | Markdown 或 JSON 文件路径 |
| `doc_title` | 否 | 可手动指定标题，缺失时自动提取 |
| `edition` | 否 | 可手动指定版本 |
| `author` | 否 | 可手动指定作者 |
| `source_name` | 否 | 可手动指定来源名称 |
| `tags` | 否 | 可手动指定标签列表 |
| `rebuild_if_exists` | 否 | 已存在时是否强制重建 |

### JSON 输入最小格式

```json
{
  "title": "本草纲目摘录",
  "content": "这里是正文内容",
  "edition": "校对版",
  "author": "李时珍",
  "source": "整理样本库",
  "tags": ["古文", "医学"]
}
```

- `title`、`content` 为最小推荐字段
- `source` 与 `source_name` 二选一即可
- `tags` 支持单个字符串或字符串数组

### 成功响应

```json
{
  "success": true,
  "message": "documents registered",
  "data": {
    "jobs": [
      {
        "job_id": "job_20260430_0001",
        "doc_uid": "zhongguo_wenxue_v1",
        "status": "queued"
      }
    ]
  },
  "request_id": "req_20260430_0001"
}
```

## 5.2 重建索引

- 方法：`POST`
- 路径：`/ingest/rebuild`
- 说明：对指定文档重建全文索引和向量索引

### 请求体

```json
{
  "doc_uids": ["zhongguo_wenxue_v1"],
  "rebuild_fulltext": true,
  "rebuild_vector": true
}
```

### 成功响应

```json
{
  "success": true,
  "message": "rebuild started",
  "data": {
    "accepted": ["zhongguo_wenxue_v1"]
  },
  "request_id": "req_20260430_0002"
}
```

## 5.3 查询入库状态

- 方法：`GET`
- 路径：`/ingest/status`
- 说明：查看文档入库、分块、索引状态

### 查询参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `doc_uid` | 否 | 指定文档 |
| `status` | 否 | 过滤状态 |
| `page` | 否 | 页码 |
| `page_size` | 否 | 每页数量 |

### 成功响应

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "items": [
      {
        "doc_uid": "zhongguo_wenxue_v1",
        "doc_title": "中国文学史纲要",
        "edition": "第一版",
        "author": "张三",
        "source_name": "古籍整理库",
        "tags": ["古文", "文学"],
        "ingest_status": "completed",
        "index_status": "indexed",
        "error_message": null,
        "updated_at": "2026-04-30T11:30:00"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1
    }
  },
  "request_id": "req_20260430_0003"
}
```

---

## 六、文档查询接口

## 6.1 全文检索

- 方法：`GET`
- 路径：`/search/fulltext`
- 说明：基于 SQLite FTS5 做关键词和短语检索

### 查询参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `query` | 是 | 查询词 |
| `doc_uid` | 否 | 指定文档 |
| `edition` | 否 | 指定版本 |
| `top_k` | 否 | 返回条数，默认 10 |

### 成功响应

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "items": [
      {
        "chunk_id": "zhongguo_wenxue_v1_0001",
        "doc_uid": "zhongguo_wenxue_v1",
        "doc_title": "中国文学史纲要",
        "source_span": "第一章 第二节",
        "score": 12.1,
        "content": "先秦典籍在文体与叙述方式上呈现出明显差异......",
        "retrieval_source": "fulltext"
      }
    ]
  },
  "request_id": "req_20260430_0004"
}
```

## 6.2 向量检索

- 方法：`GET`
- 路径：`/search/vector`
- 说明：基于 ChromaDB 做语义检索

### 查询参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `query` | 是 | 查询文本 |
| `doc_uid` | 否 | 指定文档 |
| `top_k` | 否 | 返回条数，默认 10 |

### 成功响应

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "items": [
      {
        "chunk_id": "zhongguo_wenxue_v1_0008",
        "doc_uid": "zhongguo_wenxue_v1",
        "doc_title": "中国文学史纲要",
        "source_span": "第二章 第一节",
        "score": 0.913,
        "content": "战国时期的思想文献出现了更强的论辩性......",
        "retrieval_source": "vector"
      }
    ]
  },
  "request_id": "req_20260430_0005"
}
```

## 6.3 混合检索

- 方法：`GET`
- 路径：`/search/hybrid`
- 说明：综合全文检索和向量检索结果，并可选调用重排

### 查询参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `query` | 是 | 查询文本 |
| `doc_uid` | 否 | 指定文档 |
| `top_k` | 否 | 返回条数，默认 10 |
| `use_rerank` | 否 | 是否启用重排，默认 true |

### 成功响应

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "items": [
      {
        "chunk_id": "zhongguo_wenxue_v1_0008",
        "doc_uid": "zhongguo_wenxue_v1",
        "doc_title": "中国文学史纲要",
        "source_span": "第二章 第一节",
        "score": 0.952,
        "content": "战国时期的思想文献出现了更强的论辩性......",
        "retrieval_source": "hybrid",
        "matched_sources": ["fulltext", "vector"]
      }
    ]
  },
  "request_id": "req_20260430_0006"
}
```

---

## 七、质检接口

## 7.1 提交质检

- 方法：`POST`
- 路径：`/quality/check`
- 说明：输入一段文本，执行 claim 拆分、规则校验、检索和结构化判断

### 请求体

```json
{
  "template_id": "general_fact_check",
  "input_text": "《论语》成书于春秋战国之际，并由孔子弟子编纂。",
  "doc_filters": {
    "doc_uids": ["zhongguo_wenxue_v1"]
  },
  "use_rerank": true
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `template_id` | 是 | 质检模板，如 `general_fact_check` |
| `input_text` | 是 | 待质检文本 |
| `doc_filters` | 否 | 文档过滤条件 |
| `use_rerank` | 否 | 是否启用重排 |

### 成功响应

```json
{
  "success": true,
  "message": "quality check completed",
  "data": {
    "check_id": "chk_20260430_0001",
    "status": "completed",
    "claims": [
      {
        "claim_no": 1,
        "claim_text": "《论语》成书于春秋战国之际",
        "verdict": "verified",
        "confidence": 0.93,
        "reason": "知识库中存在明确原文支持",
        "evidence": "《论语》由孔子弟子及再传弟子编纂而成，约成书于春秋战国之际......",
        "source_doc": "中国哲学史",
        "source_span": "第一章",
        "retrieval_refs": ["zhongguo_wenxue_v1_0008"],
        "review_required": false,
        "rule_hits": []
      }
    ]
  },
  "request_id": "req_20260430_0007"
}
```

## 7.2 查询质检结果

- 方法：`GET`
- 路径：`/quality/result/{check_id}`
- 说明：查看某次质检的主记录与逐条 claim 结果

### 路径参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `check_id` | 是 | 质检任务 ID |

### 成功响应

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "check_id": "chk_20260430_0001",
    "template_id": "general_fact_check",
    "input_text": "《论语》成书于春秋战国之际，并由孔子弟子编纂。",
    "status": "completed",
    "claims": [
      {
        "claim_no": 1,
        "claim_text": "《论语》成书于春秋战国之际",
        "verdict": "verified",
        "confidence": 0.93,
        "reason": "知识库中存在明确原文支持",
        "evidence": "《论语》由孔子弟子及再传弟子编纂而成，约成书于春秋战国之际......",
        "source_doc": "中国哲学史",
        "source_span": "第一章",
        "retrieval_refs": ["zhongguo_wenxue_v1_0008"],
        "review_required": false,
        "rule_hits": []
      }
    ]
  },
  "request_id": "req_20260430_0008"
}
```

## 7.3 查询质检历史

- 方法：`GET`
- 路径：`/quality/history`
- 说明：分页查询历史质检记录

### 查询参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `template_id` | 否 | 模板过滤 |
| `status` | 否 | 状态过滤 |
| `page` | 否 | 页码 |
| `page_size` | 否 | 每页数量 |

---

## 八、审核接口

## 8.1 提交审核

- 方法：`POST`
- 路径：`/review/submit`
- 说明：对某条 claim 提交人工审核动作

### 请求体

```json
{
  "check_id": "chk_20260430_0001",
  "claim_no": 1,
  "action": "approve",
  "reviewed_verdict": "verified",
  "comment": "证据充分，结论正确",
  "reviewer": "patde"
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `check_id` | 是 | 质检任务 ID |
| `claim_no` | 是 | claim 序号 |
| `action` | 是 | `approve` / `reject` / `modify` |
| `reviewed_verdict` | 否 | 修改后的结论 |
| `comment` | 否 | 审核备注 |
| `reviewer` | 否 | 审核人 |

### 成功响应

```json
{
  "success": true,
  "message": "review submitted",
  "data": {
    "review_id": "rev_20260430_0001",
    "check_id": "chk_20260430_0001",
    "claim_no": 1,
    "action": "approve",
    "reviewed_verdict": "verified"
  },
  "request_id": "req_20260430_0009"
}
```

## 8.2 查询审核记录

- 方法：`GET`
- 路径：`/review/list`
- 说明：查询审核历史

### 查询参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `check_id` | 否 | 指定质检任务 |
| `action` | 否 | 审核动作 |
| `reviewer` | 否 | 审核人 |
| `page` | 否 | 页码 |
| `page_size` | 否 | 每页数量 |

### 成功响应

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "items": [
      {
        "review_id": "rev_20260430_0001",
        "check_id": "chk_20260430_0001",
        "claim_no": 1,
        "action": "approve",
        "original_verdict": "verified",
        "reviewed_verdict": "verified",
        "comment": "证据充分，结论正确",
        "reviewer": "patde",
        "created_at": "2026-04-30T12:00:00"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1
    }
  },
  "request_id": "req_20260430_0010"
}
```

---

## 九、辅助接口

## 9.1 查询文档列表

- 方法：`GET`
- 路径：`/documents`
- 说明：用于前端下拉选择和文档管理页

### 查询参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `keyword` | 否 | 标题关键词 |
| `page` | 否 | 页码 |
| `page_size` | 否 | 每页数量 |

## 9.2 查询文档详情

- 方法：`GET`
- 路径：`/documents/{doc_uid}`
- 说明：返回文档基本信息、章节信息和索引状态

## 9.3 查询文档片段

- 方法：`GET`
- 路径：`/documents/{doc_uid}/chunks`
- 说明：按章节或分页查看 chunk 内容

---

## 十、接口状态码建议

| HTTP 状态码 | 使用场景 |
|------|------|
| `200` | 查询成功 |
| `201` | 创建成功 |
| `400` | 参数错误 |
| `404` | 资源不存在 |
| `409` | 资源冲突 |
| `422` | 业务校验失败 |
| `500` | 内部错误 |
| `502` | 外部服务异常 |

---

## 十一、模板建议

当前阶段建议支持以下质检模板：

| 模板 ID | 说明 |
|------|------|
| `general_fact_check` | 通用事实核验 |
| `citation_check` | 引用与出处核验 |
| `structure_check` | 文档结构与规范检查 |
| `medical_check_optional` | 可选医学内容检查 |

说明：

- `medical_check_optional` 为可选模板，不应影响主链路
- 后续如需接入法律、财务等规则，也采用同样的可选模板机制

---

## 十二、实现建议

- 先实现 `/ingest/register`、`/search/hybrid`、`/quality/check`、`/review/submit`
- 先保证所有接口跑通，再补列表查询和管理接口
- 所有接口层只做参数校验和响应封装，业务编排应放在 service 层
- 所有异常统一转换为标准错误响应，不向前端暴露原始堆栈

如果下一步继续，我建议直接开始输出最小可用的 `FastAPI` 路由草案和数据模型骨架。
