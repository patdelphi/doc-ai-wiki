# P1 PageIndex 最终回答编排职责拆分实施计划

> 状态：已完成

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. 本项目禁止未经批准使用 Subagent。

**Goal:** 将 Question Plan、证据分类、模板渲染、最终 LLM 回答和本地保守回答迁入单一编排器，同时保持检索和公开行为不变。

**Architecture:** 新增具体类 `PageIndexAnswerOrchestrator`，只依赖现有模板服务、Question Plan、Evidence Judge 和预算对象。`PageIndexService` 直接持有该实例，继续负责多轮检索、RAG/FTS、文档路由、vendor 原文和返回结构。

**Tech Stack:** Python 3.11+、Pytest、Ruff、Mypy、现有 PageIndex 模板与预算模块。

## Global Constraints

- 不修改 Prompt 文本、模板 YAML、Evidence Judge 规则、阈值或领域词。
- 不修改公开服务接口、返回结构、LLM 调用顺序和预算消费名称。
- 不引入第三方依赖、Provider、缓存、Factory、Protocol 或依赖注入框架。
- 不调用真实外部 API，不执行数据库迁移、索引重建或部署。
- 未获得单独批准前，不执行 Git commit、push、pull、merge 或 stage。
- 所有新增 Python 文件包含程序说明与必要中文注释；文本文档使用 UTF-8 BOM + CRLF。
- 三个既有噪声文档保持不修改：`Docs/evidence_catalog_20260620.md`、`Docs/pageindex-llm-evaluation-20260618.md`、`Docs/retrieval_alignment_suggestions_20260621.md`。

---

### Task 1: 建立回答编排器直接测试

**Files:**
- Create: `tests/unit/test_pageindex_answer_orchestrator.py`
- Reference: `src/pageindex/templates.py`
- Reference: `src/pageindex/routing.py`
- Reference: `src/pageindex/question_plan.py`

**Interfaces:**
- Consumes: `PageIndexBudget(max_llm_calls, max_rounds, max_documents, max_evidence)`。
- Produces: 对 `PageIndexAnswerOrchestrator` 四个公开方法的行为契约。

- [x] **Step 1: 写入缺失模块的失败测试**

测试文件先导入以下接口，并定义记录 Prompt 的最小 fake：

```python
"""程序说明：验证 PageIndex 最终回答编排、Question Plan 与本地保守回答。"""

from src.pageindex.answer_orchestrator import PageIndexAnswerOrchestrator
from src.pageindex.routing import PageIndexBudget, RetrievalBudgetExceededError


class RecordingTemplateService:
    def __init__(self) -> None:
        self.render_payload: dict = {}

    def get_template(self, template_id: str | None = None) -> dict:
        return {"template_id": template_id or "strict_qa"}

    def render_answer_prompts(self, template: dict, **payload: object) -> tuple[str, str]:
        self.render_payload = {"template": template, **payload}
        return "answer-system", "answer-user"


class RecordingLLMClient:
    def __init__(self, responses: list[dict] | None = None, error: Exception | None = None) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.calls.append((system_prompt, user_prompt))
        if self.error is not None:
            raise self.error
        return self.responses.pop(0) if self.responses else {}
```

增加八组断言：Question Plan 正常/失败/预算超限、已有 plan 不重复调用、模板参数、最终 answer、空证据拒答、证据分类与来源、不吞最终调用异常。

- [x] **Step 2: 运行测试确认 Red**

Run: `python -m pytest tests/unit/test_pageindex_answer_orchestrator.py -q`

Expected: collection 失败，错误为 `ModuleNotFoundError: No module named 'src.pageindex.answer_orchestrator'`。

---

### Task 2: 实现单一最终回答编排器

**Files:**
- Create: `src/pageindex/answer_orchestrator.py`
- Test: `tests/unit/test_pageindex_answer_orchestrator.py`

**Interfaces:**
- Consumes: `PageIndexTemplateService`、`PageIndexBudget`、`build_question_plan_prompts()`、`normalize_question_plan()`、`classify_evidence_relation()`、`infer_conclusion()`。
- Produces: `PageIndexAnswerOrchestrator.build_question_plan()`、`classify_evidence_items()`、`build_local_answer()`、`generate_llm_answer_payload()`。

- [x] **Step 1: 创建类和四个公开方法**

模块采用以下固定结构：

```python
"""程序说明：编排 PageIndex Question Plan、证据分类和最终回答生成。"""

from __future__ import annotations

from src.pageindex.evidence_judge import classify_evidence_relation, infer_conclusion
from src.pageindex.question_plan import build_question_plan_prompts, normalize_question_plan
from src.pageindex.routing import PageIndexBudget, RetrievalBudgetExceededError
from src.pageindex.templates import PageIndexTemplateService


class PageIndexAnswerOrchestrator:
    """把已检索证据转换为可追踪的最终回答。"""

    def __init__(self, template_service: PageIndexTemplateService) -> None:
        self.template_service = template_service

    def build_question_plan(self, llm_client: object, question: str, evidence: list[dict], *, budget: PageIndexBudget | None = None) -> dict:
        system_prompt, user_prompt = build_question_plan_prompts(question, evidence)
        try:
            if budget is not None:
                budget.consume_llm("question_plan")
            payload = llm_client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except RetrievalBudgetExceededError:
            raise
        except Exception:  # noqa: BLE001
            payload = {}
        return normalize_question_plan(payload, question)

    def classify_evidence_items(self, question: str, evidence: list[dict]) -> list[dict]:
        return [classify_evidence_relation(question, dict(item)) for item in evidence]
```

`generate_llm_answer_payload()` 必须保持以下顺序：读取模板、复用或创建 Question Plan、渲染六个现有模板变量、消费 `final_answer` 预算、调用 `complete_json()`、返回 `answer/question_plan`。

`build_local_answer()` 必须保持现有五段输出；空证据仍输出四段拒答。结构上下文、证据判断、证据要点、来源和不确定性使用模块私有函数，不增加公共类。

- [x] **Step 2: 运行直接测试确认 Green**

Run: `python -m pytest tests/unit/test_pageindex_answer_orchestrator.py -q`

Expected: 所有回答编排器直接测试通过；第三方弃用警告可保留。

- [x] **Step 3: 运行静态检查**

Run: `python -m ruff check src/pageindex/answer_orchestrator.py tests/unit/test_pageindex_answer_orchestrator.py`

Expected: `All checks passed!`

Run: `python -m mypy src/pageindex/answer_orchestrator.py`

Expected: `Success: no issues found`。

---

### Task 3: 建立服务职责与依赖门禁

**Files:**
- Modify: `tests/unit/test_quality_gates.py`
- Test: `tests/unit/test_quality_gates.py`

**Interfaces:**
- Consumes: Python AST 与源码文本。
- Produces: 防止回答方法、旧单轮检索和反向依赖回流的质量门禁。

- [x] **Step 1: 添加失败门禁**

新增测试 `test_pageindex_service_should_delegate_final_answer_orchestration()`，固定检查：

```python
migrated_methods = {
    "_generate_llm_answer",
    "_generate_llm_answer_payload",
    "_build_question_plan",
    "_build_answer_structure_context",
    "_build_local_answer",
    "_classify_evidence_items",
    "_classify_single_evidence",
    "_build_local_evidence_judgement",
    "_build_local_evidence_points",
    "_build_local_source_points",
    "_infer_local_conclusion",
    "_infer_local_uncertainty",
    "_is_benefit_or_treatment_question",
    "_is_formula_context_for_single_herb_question",
    "_answer_with_llm_tree_reasoning",
    "_build_tree_reasoning_prompts",
}

assert service_method_names.isdisjoint(migrated_methods)
assert "PageIndexAnswerOrchestrator" in service_source
assert forbidden_dependencies.isdisjoint(orchestrator_imports)
assert "PageIndexClient" not in orchestrator_source
```

禁止依赖集合为 `src.pageindex.service`、`src.db`、`src.retrieval`、`src.common.config` 和 vendor `pageindex`。

- [x] **Step 2: 运行门禁确认 Red**

Run: `python -m pytest tests/unit/test_quality_gates.py::test_pageindex_service_should_delegate_final_answer_orchestration -q`

Expected: 因十六个旧方法仍在服务中而失败。

---

### Task 4: 服务接入编排器并删除旧代码

**Files:**
- Modify: `src/pageindex/service.py`
- Modify: `tests/unit/test_pageindex_service.py`
- Test: `tests/unit/test_pageindex_answer_orchestrator.py`
- Test: `tests/unit/test_pageindex_service.py`
- Test: `tests/unit/test_quality_gates.py`

**Interfaces:**
- Consumes: Task 2 的 `PageIndexAnswerOrchestrator` 四个公开方法。
- Produces: 保持公开行为的精简 `PageIndexService`。

- [x] **Step 1: 初始化唯一编排器实例**

在服务导入并初始化：

```python
from src.pageindex.answer_orchestrator import PageIndexAnswerOrchestrator

self.template_service = PageIndexTemplateService(settings.templates_dir)
self.answer_orchestrator = PageIndexAnswerOrchestrator(self.template_service)
```

- [x] **Step 2: 替换所有回答调用点**

固定映射如下：

| 原服务方法 | 新调用入口 |
|---|---|
| `_build_question_plan` | `self.answer_orchestrator.build_question_plan` |
| `_classify_evidence_items` | `self.answer_orchestrator.classify_evidence_items` |
| `_build_local_answer` | `self.answer_orchestrator.build_local_answer` |
| `_generate_llm_answer_payload` | `self.answer_orchestrator.generate_llm_answer_payload` |

不得增加同名服务包装方法。

- [x] **Step 3: 删除十六个旧方法**

删除 Task 3 `migrated_methods` 集合中的所有定义。同步删除服务中不再使用的 `classify_evidence_relation`、`infer_conclusion`、`build_question_plan_prompts` 和 `normalize_question_plan` 导入。

- [x] **Step 4: 更新直接调用旧私有方法的测试**

本地回答与最终 LLM 回答测试改为直接创建或使用 `service.answer_orchestrator`：

```python
answer = service.answer_orchestrator.build_local_answer(question, classified_evidence)
payload = service.answer_orchestrator.generate_llm_answer_payload(
    llm_client,
    question,
    evidence,
    template_id=template_id,
)
```

服务集成测试继续通过 `ask_question()` 验证原有公开结果。

- [x] **Step 5: 运行门禁和聚焦回归确认 Green**

Run: `python -m pytest tests/unit/test_pageindex_answer_orchestrator.py tests/unit/test_pageindex_service.py tests/unit/test_quality_gates.py -q`

Expected: 全部通过；不得出现真实外部模型调用。

- [x] **Step 6: 统计复杂度**

统计 `service.py`、`answer_orchestrator.py` 的物理行数和 AST 方法数。验收要求：服务方法数至少减少十六，两个生产文件总行数不超过迁移前 `service.py` 的 2165 行。

实际结果：`service.py` 为 1834 行、59 个方法；`answer_orchestrator.py` 为 172 行、5 个类方法；合计 2006 行，较迁移前净减少 159 行。

---

### Task 5: 完整验证与交付文档收口

**Files:**
- Modify: `Docs/design/p1_pageindex_answer_orchestrator_design_20260719.md`
- Modify: `Docs/tasks/p1_pageindex_answer_orchestrator_plan_20260719.md`
- Modify: `todo.md`
- Modify: `Docs/changelog/retrieval_pageindex_20260716.md`
- Modify: `Docs/acceptance.MD`
- Modify: `Docs/optimization-plan/vibe_coding_code_quality_audit_20260716.md`
- Modify: `Docs/optimization-plan/knowledge_base_maturity_assessment_20260716.md`
- Modify: `chat_history.md`

**Interfaces:**
- Consumes: Task 4 的代码、测试与复杂度结果。
- Produces: 可复核的最终工程记录。

- [x] **Step 1: 运行完整质量检查**

Run: `python -m ruff check src tests .aipython Docs/migrations`

Expected: `All checks passed!`

Run: `python -m mypy src/retrieval src/pageindex src/quality/service.py`

Expected: `Success: no issues found`。

Run: `python -m pytest tests -q`

Expected: 全部测试通过；仅允许现有 PyPDF2/SWIG 第三方弃用警告。

Run: `python -m build`

Expected: 成功生成 sdist 与 wheel。

Run: `python -m compileall -q src`

Expected: 退出码 0。

- [x] **Step 2: 更新所有交付文档**

统一记录：迁移方法、删除死代码、服务/模块行数与方法数、TDD Red→Green、聚焦和完整测试、Ruff/Mypy/build/compileall 结果、未执行事项。

- [x] **Step 3: 文本格式与差异检查**

本批触及的 Markdown、Python 和测试文件统一为 UTF-8 BOM + CRLF。

Run: `git diff --check -- . ":(exclude)Docs/evidence_catalog_20260620.md" ":(exclude)Docs/pageindex-llm-evaluation-20260618.md" ":(exclude)Docs/retrieval_alignment_suggestions_20260621.md"`

Expected: 无输出，退出码 0。

- [x] **Step 4: 停在本地未提交状态**

只报告 `git status --short` 和未执行事项。未获单独批准，不执行 Git stage、commit 或 push。
