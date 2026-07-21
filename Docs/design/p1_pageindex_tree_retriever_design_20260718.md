# P1 PageIndex 确定性树检索职责拆分设计

> 日期：2026-07-18
> 状态：已实施并完成本地验收
> 范围：`src/pageindex`、PageIndex 单元测试、质量门禁与项目交付文档

## 1. 背景与目标

完成历史导出和持久化拆分后，`PageIndexService` 仍有 2354 行、84 个方法。其中树展开、候选打分、交叉引用、候选合并和调试格式化属于确定性算法，却与 vendor 原文读取、LLM 多轮推理、RAG 补充和回答编排混在同一类中。

本批次采用已确认的 A1 方案：新增 `tree_retriever.py` 承载确定性树候选算法；服务只保留一个具有真实 IO 责任的 `_build_tree_candidates()` 适配方法，用于准备问题词、创建 vendor client 和读取节点原文。

完成后应满足：

- 确定性候选算法可在不创建 `PageIndexService`、数据库或 vendor client 的情况下直接测试；
- 候选顺序、分数、ID、位置、摘要和内容截断保持不变；
- LLM Prompt、调用预算、多轮检索、RAG 补充、证据分类和回答不变；
- 阿胶、疾病、方剂和评测主题词仍留在原有问题词逻辑，等待独立配置化批次；
- 不保留无状态方法的服务包装层；唯一保留的 `_build_tree_candidates()` 必须真实承担 IO 适配，而不是兼容别名。

## 2. 方案比较

### A1：纯算法模块加一个 IO 适配方法（采用）

服务准备问题词和可选内容读取函数，新模块完成树展开、评分、排序和候选构造。

优点：

- 新模块不依赖 LLM、数据库、项目设置或 vendor PageIndex；
- 保留原文读取异常和现有降级边界；
- 不把领域词配置化与结构拆分混在同一批；
- 可删除重复的两套树展开实现。

代价：

- 服务仍保留一个约二十行的 IO 适配方法；
- `tree_retriever` 只完成确定性候选层，不代表回答编排已经拆分。

### A2：候选构建和问题词提取全部迁出

服务更小，但会把阿胶、疾病、方剂和评测主题词一起迁入新模块，使通用树检索继续绑定当前语料，不采用。

### A3：迁移完整 LLM 多轮树推理

需要同时搬迁 LLM client、预算、Question Plan、RAG、证据分类和回答，范围过大且难以证明行为不变，不采用。

## 3. 新模块接口

新增 `src/pageindex/tree_retriever.py`。模块只依赖 Python 标准库，并定义以下公开函数：

```python
ContentLoader = Callable[[dict], str]

def flatten_structure(structure: list[dict]) -> list[dict]: ...
def format_node_position(node: dict) -> str: ...
def score_node(node: dict, terms: list[str]) -> int: ...
def penalize_generic_front_matter(node: dict, score: int) -> int: ...
def build_tree_candidates(
    structure: list[dict],
    terms: list[str],
    *,
    limit: int,
    content_loader: ContentLoader | None = None,
) -> list[dict]: ...
def extract_cross_reference_targets(content: str) -> list[str]: ...
def find_cross_reference_candidates(structure: list[dict], targets: list[str]) -> list[dict]: ...
def merge_tree_candidates(primary: list[dict], supplemental: list[dict]) -> list[dict]: ...
def candidate_to_debug(candidate: dict) -> dict: ...
```

模块私有函数只允许用于文本规范化等局部复用，不新增类、配置对象或策略模式。

## 4. 服务与模块边界

### 4.1 从服务删除的方法

以下九个无状态方法迁入新模块并从 `PageIndexService` 删除：

- `_extract_cross_reference_targets()`；
- `_find_cross_reference_candidates()`；
- `_merge_tree_candidates()`；
- `_flatten_structure_static()`；
- `_score_node()`；
- `_penalize_generic_front_matter()`；
- `_candidate_to_debug()`；
- `_flatten_structure()`；
- `_format_node_position()`。

服务调用点直接导入模块函数，不保留同名包装层。原来完全重复的 `_flatten_structure_static()` 与 `_flatten_structure()` 合并为一个事实源。

### 4.2 保留的 IO 适配方法

`PageIndexService._build_tree_candidates()` 保留，但职责收敛为：

1. 从问题分析和原问题提取并过滤打分词；
2. `include_content=True` 时创建 `PageIndexClient`；
3. 构造 `ContentLoader`，复用 `_load_node_content()`；
4. 调用模块级 `build_tree_candidates()` 并原样返回。

该方法不再遍历树、不再计算分数、不再排序或构造候选字典，因此不是平行算法层。

### 4.3 继续留在服务中的内容

- `_extract_question_terms()`、`_expand_meaningful_segment()` 和领域词规则；
- `_normalize_term_list()`、`_analysis_terms()`、`_build_tree_scoring_terms()`；
- `_rank_evidence()` 与 `_load_node_content()`；
- 单轮与多轮 LLM 节点选择；
- Question Plan、预算、RAG 补证据、证据分类和回答；
- vendor client 创建、工作区和文件系统访问。

## 5. 数据流

```text
问题 + question_analysis
    -> PageIndexService 提取/过滤打分词
    -> 可选创建 vendor ContentLoader
    -> tree_retriever.build_tree_candidates
        -> flatten_structure
        -> score_node
        -> penalize_generic_front_matter
        -> 原排序规则
        -> 原候选字典与截断
    -> 服务原有 LLM 选择、RAG、证据和回答流程
```

交叉引用流程改为直接调用：

```text
节点原文
    -> extract_cross_reference_targets
    -> find_cross_reference_candidates
    -> merge_tree_candidates
    -> 原有下一轮候选集合
```

## 6. 算法不变量

迁移必须逐项保持：

- 深度优先树展开顺序；
- 标题命中加 4 分、摘要/正文命中加 2 分；
- 前置泛化节点的原惩罚规则；
- 排序键：分数降序、层级升序、行号升序；
- 只保留分数大于 0 的节点；
- `candidate_id=node_<原展开序号>`；
- 摘要最多 500 字符，内容摘录最多 900 字符；
- 交叉引用候选使用 `xref_<序号>`；
- 候选合并继续按标题、位置和必要时 candidate ID 去重；
- debug 字段、默认 reason 和位置格式不变。

本批次不调整任何阈值、正则、通用词、惩罚词或领域扩展词。

## 7. 错误处理

新模块不捕获 `ContentLoader` 异常。vendor 文件读取失败继续沿现有服务调用栈进入已有降级或错误处理，避免改变异常类型和 `llm_error` 语义。

纯数据输入中的非字典节点继续跳过；缺少字段继续使用现有空字符串、层级 1、分数 0 和空位置回退。模块不增加额外输入验证或防御性包装。

## 8. 测试设计

新增 `tests/unit/test_pageindex_tree_retriever.py`，直接覆盖：

1. 深度优先树展开和非字典节点跳过；
2. 标题/摘要命中分数；
3. 泛化前置节点惩罚；
4. 候选排序、稳定 ID、limit、摘要和内容截断；
5. `ContentLoader=None` 与注入 loader 两种路径；
6. 交叉引用目标提取、候选匹配和去重；
7. 候选合并与 debug 字段；
8. page/line/空位置格式。

现有服务测试继续覆盖：

- `_build_tree_candidates()` 的问题词与 vendor 内容读取适配；
- 负例、质量检测、制作工艺等现有候选排名；
- 本地证据、单轮 LLM 和迭代式检索；
- PageIndex UI、历史和重建行为。

质量门禁新增断言：

- 九个无状态方法不再定义于 `PageIndexService`；
- `tree_retriever.py` 不导入 `PageIndexService`、`PageIndexClient`、LLM、数据库或设置；
- 服务只保留一个 `_build_tree_candidates()` 定义；
- 新模块存在唯一 `flatten_structure()` 实现。

## 9. 验收标准

- 新模块直接测试先 Red 后 Green；
- 九个旧方法从服务删除且无包装别名；
- `_build_tree_candidates()` 只承担打分词和 IO 适配；
- 原候选算法、交叉引用和调试结构逐字段兼容；
- 服务物理行数、方法数和生产代码合计不增加；
- Ruff、PageIndex/质量门禁聚焦测试、Mypy、完整 Pytest、build 和 compileall 全部通过；
- 变更同步到设计、计划、Todo、Changelog、验收、代码质量审计、成熟度评估和聊天记录；
- 不调用外部 API，不执行正式数据库迁移、索引重建、部署、commit 或 push。

## 10. 回滚边界

本批次不修改数据库、索引、Prompt、模板、配置或运行数据。若验证失败，只需回滚模块导入、函数迁移和对应测试，无需恢复数据库或索引。

## 11. 实施结果

- 新增 `tree_retriever.py`，确定性树候选和交叉引用算法可脱离服务直接测试；
- 九个无状态方法已从 `PageIndexService` 删除，服务只保留真实 IO 适配方法；
- 服务由 2354 行、84 个方法降至 2165 行、75 个方法；新模块 189 行，生产代码合计保持 2354 行；
- 新增 8 项算法直接测试和 1 项职责门禁，完整测试增至 446 项；
- Ruff、CI 范围 Mypy、完整 Pytest、build 和 compileall 通过；
- 未调用外部 API，未执行数据库迁移、索引重建、部署或 Git 写操作。

