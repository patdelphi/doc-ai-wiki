# PageIndex 答案质量 P0 优化计划

## 目标

把 PageIndex 默认回答从“命中说明”升级为“证据审查式答案”：先给结论，再说明依据、来源、证据类型和不确定点。
结论必须直接回答用户问题；当证据只支持方剂、章节或间接语境时，要明确说明不能证明用户问句本身，不能让用户自行阅读证据后再做判断。

## 本次执行范围

1. 增加证据分类：直接支持、间接相关、风险提醒、仅定位信息。
2. 本地降级答案使用证据分类判断结论，避免把“相关”误判成“支持”。
3. PageIndex 证据表增加“证据类型”，让用户看得出每条证据的作用。
4. LLM 回答提示词增加证据类型要求，并支持 PageIndex 专用回答模板。
5. 针对“吃阿胶能缓解痛经”这类疗效问题，方剂语境只作为间接证据，结论明确写出不能证明单独吃阿胶可获得该效果。
6. PageIndex 页面提问范围确认调整为知识库级：当前知识库下所有已构建 PageIndex 文档都会参与检索，最终合并多文档证据后回答。
7. PageIndex 历史与导出保存 `debug.question_plan`，便于复盘每次回答策略。
8. Markdown 导出支持通用结构化答案渲染，不依赖固定 LLM 字段名。

## 暂不执行

1. 不做 PageIndex 高级检索策略的可视化配置。
2. 不做破坏性数据库迁移；仅为历史表兼容补充 `debug_json` 字段。
3. 不改 PageIndex 构建流程。
4. 不做外部医学知识补充。

## 验收标准

1. “心脏病吃阿胶有好处”这类问题，不能只返回命中位置。
2. 如果证据只是“心脏相关病证”和“医师指导/禁忌”，结论必须是证据不足，不能直接得出有好处。
3. 证据表能显示每条证据是直接支持、间接相关还是风险提醒。
4. PageIndex 相关单测通过，全量测试通过。
5. “吃阿胶能缓解痛经”这类问题不能输出“具体判断需结合依据”，必须给出明确结论。
6. PageIndex 页面提问必须调用知识库级入口 `ask_knowledge_base_question()`。
7. `default` 知识库下可查到同一次 query 命中 `阿胶历史文化通典_default` 和 `阿胶学术论文全集_default` 的案例。
8. 导出 Markdown 中结构化答案应渲染为标题、段落和列表，不能原样输出 `{'结论': ...}`；同时不能丢失证据区。

## P1 模板服务层追加计划

1. 复用 AI 质检模板的管理思路：内置模板、本地 YAML 覆盖、自定义模板、删除标记。
2. PageIndex 使用独立目录 `templates/pageindex`，避免和 `templates/quality` 混用。
3. PageIndex 模板使用独立变量：`question`、`evidence_json`、`structure_context`、`evidence_judgement`、`citation_rules`。
4. PageIndex 模板使用独立回答模式：`general_summary`、`balanced_qa`、`strict_qa`、`evidence_audit_qa`、`medical_safety_qa`、`source_locator`。
5. 本阶段完成服务层、单测、PageIndex 页模板选择和 LLM 回答链路接入。
6. 设置页复用现有 AI 质检模板管理交互，支持 PageIndex 模板新增、编辑、删除。
7. 设置页当前暴露基础模板字段；PageIndex 高级检索策略继续使用模板服务默认值，后续按需要再单独开放。

## 2026-06-23 模板梯度优化

- [x] 新增 `general_summary`：宽松速览，适合摘要、背景、主题概览。
- [x] 新增 `balanced_qa`：普适问答，先直接回答，再说明证据边界。
- [x] 保留并强化 `strict_qa`：证据关系判断仍是默认严谨模式。
- [x] 新增 `evidence_audit_qa`：专门处理“证据是否足够证明结论”的审查问题。
- [x] 强化 `medical_safety_qa`：医学场景从严，但不把外部医学知识伪装成已检索证据。
- [x] 保留 `source_locator`：只做原文定位，不生成结论。
- [x] 模板列表固定为从宽松到严谨的展示顺序。

## 2026-06-23 验证记录

### 知识库级检索

当前 PageIndex 页面提问链路：

1. `src/ui/pages.py` 调用 `pageindex_service.ask_knowledge_base_question(...)`。
2. `PageIndexService.ask_knowledge_base_question()` 调用 `_list_index_records(knowledge_base_id)`。
3. `_list_index_records("default")` 当前返回：
   - `阿胶历史文化通典_default`
   - `阿胶学术论文全集_default`
4. `_answer_knowledge_base_with_reasoning_or_fallback()` 对全部记录逐个检索并合并证据。

真实历史中已确认多文档命中：

| query_id | 问题 | 命中文档 | 证据数 |
| --- | --- | --- | ---: |
| `piq_09d75d5788ee` | 阿胶对感冒有一定缓解作用 | `阿胶历史文化通典_default`、`阿胶学术论文全集_default` | 4 |
| `piq_14f55f1319ed` | 心脏病吃阿胶有好处吗 | `阿胶历史文化通典_default`、`阿胶学术论文全集_default` | 5 |
| `piq_814bd5837669` | 阿胶制作工艺有什么特点 | `阿胶历史文化通典_default`、`阿胶学术论文全集_default` | 10 |

### Markdown 导出

导出层已经改为通用结构化渲染：

- 支持普通文本答案。
- 支持 JSON 字符串答案。
- 支持 Python dict 字符串答案。
- 支持中文字段、英文字段和模型自定义字段。
- 支持列表中嵌套 dict 的引用信息。
- 结构化答案只影响回答区排版，不影响证据区输出。
