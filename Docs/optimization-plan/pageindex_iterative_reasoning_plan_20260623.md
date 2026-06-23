# PageIndex Iterative Reasoning Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 PageIndex 从“候选节点 rerank + RAG/FTS 补证据”升级为最小可用的“迭代式推理检索”闭环。

**Architecture:** 保留现有 PageIndex 索引、模板、Question Plan、历史与导出机制；新增一个迭代检索控制层，让 LLM 在多轮中选择节点、读取证据、判断信息是否充分，并在不足时继续检索。第一阶段不做大规模重构，不引入新依赖，不自动调用外部基准。

**Tech Stack:** Python, SQLite, PageIndex vendor client, existing LLM client, pytest.

## Global Constraints

- 不新增外部依赖。
- 不改数据库 schema，先把每轮检索过程写入现有 `debug_json`。
- 不替换现有 RAG/FTS，只把它作为补充证据。
- 不写死医学、法律、财务等行业规则；行业差异通过模板和 Question Plan 表达。
- 新功能先写测试，再做实现。
- 不调用外部 API 做测试；单测使用 fake LLM。
- 默认最多 3 轮，每轮最多选择 3 个节点，避免成本失控。

---

## 当前差距

当前实现已经具备：

- PageIndex 语义树索引。
- 知识库多文档 PageIndex 检索。
- LLM 对候选节点做选择。
- Question Plan 与回答模板。
- RAG/FTS 细粒度证据补充。

当前主要缺口：

- LLM 不是直接在树上迭代导航，而是先由本地关键词筛出候选。
- 缺少“证据是否足够”的检索阶段判断。
- 缺少“证据不足则继续找”的多轮闭环。
- 缺少“参见、详见、附录、表、图、章节”等交叉引用跟随。
- 缺少按轮次记录的 debug 视图和评测样例。

## Files

- Modify: `src/pageindex/service.py`
  - 新增迭代检索主流程、轮次 prompt、充分性判断、debug 记录。
- Modify: `tests/unit/test_pageindex_service.py`
  - 增加 fake LLM 测试，覆盖多轮检索、证据充分停止、证据不足继续。
- Modify: `tests/evaluation/pageindex_cases.jsonl`
  - 增加迭代检索场景样例。
- Modify: `Docs/optimization-plan/pageindex_answer_quality_plan_20260622.md`
  - 同步 PageIndex 下一阶段计划。
- Modify: `todo.md`
  - 加入 P0/P1/P2 执行清单。

## Task 1: 迭代检索结果结构与 Prompt

**Files:**

- Modify: `src/pageindex/service.py`
- Test: `tests/unit/test_pageindex_service.py`

**Interfaces:**

- Produces: `_build_iterative_tree_reasoning_prompts(question: str, question_analysis: dict, candidates: list[dict], retrieved_evidence: list[dict], round_index: int) -> tuple[str, str]`
- Produces LLM JSON schema:

```json
{
  "selected_nodes": [{"candidate_id": "node_1", "reason": "选择理由"}],
  "sufficiency": "sufficient | partial | insufficient",
  "missing_information": "还缺什么信息",
  "next_search_focus": "下一轮应该找什么",
  "answer": "基于当前证据的临时答案"
}
```

- [ ] **Step 1: Write failing tests**

```python
def test_pageindex_iterative_prompt_should_require_sufficiency_fields() -> None:
    from src.pageindex.service import PageIndexService

    system_prompt, user_prompt = PageIndexService._build_iterative_tree_reasoning_prompts(
        "阿胶有哪些质量检测方法",
        {"keywords": ["质量检测", "方法"]},
        [
            {
                "candidate_id": "node_1",
                "title": "质量检测",
                "level": 2,
                "position": "line 10",
                "summary": "检测方法概述",
                "content_excerpt": "包括性状、鉴别、含量测定。",
                "score": 10,
            }
        ],
        [],
        1,
    )

    assert "sufficiency" in user_prompt
    assert "missing_information" in user_prompt
    assert "next_search_focus" in user_prompt
    assert "selected_nodes" in user_prompt
    assert "只返回 JSON" in system_prompt
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_service.py::test_pageindex_iterative_prompt_should_require_sufficiency_fields" -q
```

Expected: fail because `_build_iterative_tree_reasoning_prompts` does not exist.

- [ ] **Step 3: Implement minimal prompt builder**

Add static method in `PageIndexService`.

- [ ] **Step 4: Run test**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_service.py::test_pageindex_iterative_prompt_should_require_sufficiency_fields" -q
```

Expected: pass.

## Task 2: 单文档迭代检索闭环

**Files:**

- Modify: `src/pageindex/service.py`
- Test: `tests/unit/test_pageindex_service.py`

**Interfaces:**

- Produces: `_answer_with_iterative_tree_reasoning(record: dict, structure: list[dict], question: str, question_analysis: dict, *, template_id: str | None = None, max_rounds: int = 3) -> tuple[list[dict], str, dict]`
- Debug shape:

```json
{
  "retrieval_rounds": [
    {
      "round": 1,
      "selected_nodes": [],
      "sufficiency": "partial",
      "missing_information": "",
      "next_search_focus": ""
    }
  ]
}
```

- [ ] **Step 1: Write failing test for two-round retrieval**

Use fake LLM:

- Round 1 selects one general node and returns `partial`.
- Round 2 selects a specific node and returns `sufficient`.
- Assert two rounds are saved in debug.
- Assert final evidence includes both selected nodes.

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_service.py::test_pageindex_should_continue_iterative_retrieval_until_sufficient" -q
```

Expected: fail because iterative method does not exist.

- [ ] **Step 3: Implement loop**

Implementation rules:

- Build candidates each round with existing `_build_tree_candidates()`.
- Exclude already selected candidate IDs.
- Pass retrieved evidence to the next prompt.
- Stop when `sufficiency == "sufficient"` and evidence is not empty.
- Stop when `round_index == max_rounds`.
- On malformed LLM output, treat as `insufficient` and stop after current round with debug error.

- [ ] **Step 4: Switch LLM path**

Change `_answer_with_reasoning_or_fallback()` to call `_answer_with_iterative_tree_reasoning()` before falling back to keyword mode.

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_service.py" -q
```

Expected: pass.

## Task 3: 知识库多文档聚合支持迭代 debug

**Files:**

- Modify: `src/pageindex/service.py`
- Test: `tests/unit/test_pageindex_service.py`

**Interfaces:**

- Consumes: single-document `debug.retrieval_rounds`.
- Produces aggregate debug:

```json
{
  "document_retrieval_rounds": [
    {
      "doc_uid": "doc-a",
      "rounds": []
    }
  ]
}
```

- [ ] **Step 1: Write failing test**

Assert `ask_knowledge_base_question()` result debug contains per-document retrieval rounds when LLM iterative retrieval is used.

- [ ] **Step 2: Implement aggregation**

In `_answer_knowledge_base_with_reasoning_or_fallback()`, collect each document debug `retrieval_rounds` into `document_retrieval_rounds`.

- [ ] **Step 3: Run focused tests**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_service.py" "tests/unit/test_pageindex_ui.py" -q
```

Expected: pass.

## Task 4: 最小交叉引用识别与跟随

**Files:**

- Modify: `src/pageindex/service.py`
- Test: `tests/unit/test_pageindex_service.py`

**Interfaces:**

- Produces: `_extract_cross_reference_targets(content: str) -> list[str]`
- Produces: `_find_cross_reference_candidates(structure: list[dict], targets: list[str]) -> list[dict]`

- [ ] **Step 1: Write failing tests**

Cases:

- `详见附录 G`
- `参见表 5.3`
- `见第六章`
- `详见“质量标准”`

Expected extracted targets:

```python
["附录 G", "表 5.3", "第六章", "质量标准"]
```

- [ ] **Step 2: Implement target extraction**

Use conservative regex only for explicit reference markers:

- `详见`
- `参见`
- `见`
- `附录`
- `表`
- `图`
- `第...章`

- [ ] **Step 3: Implement candidate matching**

Match targets against node title and summary. Do not search entire document text in this task.

- [ ] **Step 4: Integrate into iterative loop**

After reading selected evidence, extract references and add matched nodes to next-round candidates with reason `交叉引用候选`.

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_service.py" -q
```

Expected: pass.

## Task 5: 评测样例与验收

**Files:**

- Modify: `tests/evaluation/pageindex_cases.jsonl`
- Modify: `Docs/optimization-plan/pageindex_answer_quality_plan_20260622.md`
- Modify: `todo.md`

**Acceptance cases:**

- 信息抽取：`阿胶有哪些质量检测方法`
- 命题判断：`吃阿胶能缓解感冒症状吗`
- 风险边界：`心脏病吃阿胶有好处吗`
- 结构定位：`阿胶应用注意事项在哪里`
- 交叉引用模拟：包含 `详见附录` 或 `参见表` 的测试 fixture

- [ ] **Step 1: Add evaluation cases**

Add 5-10 PageIndex iterative retrieval cases. Each case records:

```json
{
  "question": "...",
  "mode": "iterative_reasoning",
  "expected_behavior": "...",
  "requires_llm": true
}
```

- [ ] **Step 2: Document acceptance**

Update optimization plan with:

- iteration rounds visible in debug
- insufficient evidence triggers another round
- sufficient evidence stops early
- cross-reference candidate appears when explicit reference is present

- [ ] **Step 3: Run final focused tests**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_question_plan.py" "tests/unit/test_pageindex_templates.py" "tests/unit/test_pageindex_evidence_judge.py" "tests/unit/test_pageindex_service.py" "tests/unit/test_pageindex_ui.py" -q
```

Expected: pass.

## Execution Recommendation

建议分两次实现：

1. P0：Task 1-3，先完成多轮迭代检索闭环。
2. P1：Task 4-5，再补交叉引用和评测样例。

P0 是核心收益，预计 0.5-1 天可出可测版本。P1 的复杂度取决于文档结构质量，预计 1-2 天。

## 2026-06-23 Execution Result

- [x] Task 1 完成：新增迭代式检索 prompt，要求返回 `selected_nodes`、`sufficiency`、`missing_information`、`next_search_focus`。
- [x] Task 2 完成：单文档 LLM PageIndex 检索已切换为最多 3 轮迭代闭环。
- [x] Task 3 完成：知识库多文档聚合 debug 已记录 `document_retrieval_rounds`。
- [x] Task 4 完成：新增最小交叉引用识别与树节点候选跟随。
- [x] Task 5 完成：新增 5 条 `iterative_reasoning` 评测样例，并更新答案质量计划和 `todo.md`。

验证命令：

```powershell
python -m pytest "tests/unit/test_pageindex_service.py" "tests/unit/test_pageindex_ui.py" -q
```

已通过：`57 passed`。

