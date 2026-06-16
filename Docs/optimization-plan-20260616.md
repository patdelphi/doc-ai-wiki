# doc-ai-wiki 优化升级计划（2026-06-16）

## 目标

在不改变现有业务能力的前提下，先修复当前可复现错误，再清理仓库冗余与配置不一致，最后分阶段降低 UI 与测试维护成本。

## 本次体检范围

- 读取项目结构、`pyproject.toml`、`readme.md`、核心入口与配置文件。
- 执行幂等校验：`python -m pytest tests --maxfail=1 -q`。
- 扫描冗余文件、Git 跟踪状态、运行期文件、TODO/占位/临时代码关键词。
- 未执行：删除文件、提交、推送、拉取、安装依赖、外部 API 调用、部署、数据库迁移。

## 当前发现

### P0：测试套件存在顺序依赖失败

现象：

- `python -m pytest tests --maxfail=1 -q` 结果：120 个测试通过后失败 1 个。
- 失败用例：`tests/unit/test_ui.py::test_connection_scoped_auth_service_should_open_and_close_connection_per_call`。
- 单独运行该用例可通过：`1 passed in 4.79s`。

初步判断：

- `tests/unit/test_startup_validation.py` 中存在 `sys.modules.pop("src.ui.app", None)` 后重新导入模块。
- `tests/unit/test_ui.py` 文件顶部导入了 `ConnectionScopedAuthService`，后续 monkeypatch 指向重新导入后的 `src.ui.app`，两者可能不是同一个模块对象，导致 patch 未命中。
- 这是测试隔离/模块重载污染问题，不应直接按业务逻辑缺陷处理。

建议处理：

1. 调整测试导入方式：在相关测试内导入当前 `src.ui.app` 模块对象，再从模块对象取 `ConnectionScopedAuthService`。
2. 或在 `test_startup_validation.py` 的模块重载测试后恢复 `sys.modules` 与 monkeypatch 状态。
3. 增加一条测试，确认模块重载不会污染后续 UI 单元测试。

完成标准：

- `python -m pytest tests/unit/test_startup_validation.py tests/unit/test_ui.py -q` 通过。
- `python -m pytest tests --maxfail=1 -q` 不再在该用例失败。

### P0：完整测试耗时偏高且首次运行超时

现象：

- `python -m pytest tests` 在 120 秒超时，并出现 stdout flush 错误。
- 当前 Python 为 `3.13.13`，项目要求为 `>=3.11`，但实际依赖组合可能主要在 3.11/3.12 上验证。
- `--collect-only` 显示共有 222 个测试。

建议处理：

1. 明确官方开发 Python 版本，建议固定为 Python 3.11 或 3.12。
2. 将慢测试拆分标记：`unit`、`integration`、`vector`、`ui`。
3. 在 `pyproject.toml` 配置 pytest markers，默认本地只跑快速单元测试，CI 再跑全量。
4. 为 Chroma/Gradio 相关测试增加超时边界和最小 stub。

完成标准：

- 快速单元测试目标：60 秒内完成。
- 全量测试目标：180 秒内完成，且输出稳定。

### P1：仓库存在已跟踪的 `__pycache__/*.pyc`

现象：

- Git 已跟踪以下运行期缓存文件：
  - `src/chunking/__pycache__/__init__.cpython-313.pyc`
  - `src/chunking/__pycache__/splitter.cpython-313.pyc`
  - `src/ingest/__pycache__/__init__.cpython-313.pyc`
  - `src/quality/__pycache__/__init__.cpython-313.pyc`
  - `src/retrieval/__pycache__/__init__.cpython-313.pyc`
  - `tests/unit/__pycache__/__init__.cpython-313.pyc`

建议处理：

1. 经确认后用 `git rm --cached` 从版本控制移除这些缓存文件。
2. 保留 `.gitignore` 中现有 `__pycache__/`、`*.pyc` 规则。
3. 增加仓库卫生检查，防止再次提交 pyc。

完成标准：

- `git ls-files | rg "(__pycache__|\.pyc$)"` 无输出。
- 测试仍通过。

### P1：版本号不一致

现象：

- `pyproject.toml`：`version = "0.5"`。
- `readme.md`：版本写为 `0.6`。
- `src/app.py` FastAPI 版本：`0.5`。

建议处理：

1. 确认当前真实发布版本是 `0.5` 还是 `0.6`。
2. 将 `pyproject.toml`、`src/app.py`、`readme.md` 统一。
3. 后续增加一个轻量测试校验版本一致性。

完成标准：

- 三处版本一致。
- `python -m pytest tests/unit/test_startup_validation.py -q` 或新增版本测试通过。

### P1：当前工作区已有未提交变更

现象：

- `qorder_comments.md` 被删除。
- `Docs/qorder_comments.md` 为未跟踪文件。
- 本次体检额外生成了 `pytest_collect_output.txt`，用于保存测试收集输出。

建议处理：

1. 先确认 `qorder_comments.md` 是否是有意移动到 `Docs/`。
2. 如果是，按文档变更走 Code Review，说明移动原因和验证结果。
3. `pytest_collect_output.txt` 是本次诊断临时产物，建议确认后删除或加入忽略。

完成标准：

- `git status --short` 只剩预期变更。
- 文档移动有明确说明，不静默合并。

### P2：UI 入口文件过大，维护成本高

现象：

- `src/ui/pages.py` 约 309 KB，承担大量状态转换、事件绑定、页面组装和分页逻辑。
- `src/ui/viewmodels.py` 约 130 KB，展示数据转换逻辑集中。
- `src/ui/pages/` 目录目前只有 `__pycache__`，没有真实模块，疑似历史拆分遗留。

建议处理：

1. 先不做大重构，按“页面域”切分：document、quality、review、search、settings。
2. 每次只迁移一组纯函数或一组事件绑定，迁移前先写/保留对应测试。
3. `src/ui/pages.py` 保留总装配职责，逐步减到 80 KB 以下。
4. 清理空的 `src/ui/pages/` 目录前必须确认，因为涉及删除操作。

完成标准：

- 每次拆分后相关 UI 单元测试通过。
- `src/ui/pages.py` 行数/体积下降，职责更清晰。

### P2：打包配置可能未包含子包

现象：

- `pyproject.toml` 当前写法：`packages = ["src"]`。
- 项目实际代码在 `src/ai`、`src/ui`、`src/db` 等子包中。

风险：

- 可编辑安装和本地 `pythonpath = ["."]` 下测试可能正常，但构建 wheel/sdist 时可能漏掉子包。

建议处理：

1. 改为 setuptools 自动发现包。
2. 增加构建验证：构建后在干净环境导入 `src.ui.app`、`src.app`。
3. 如短期不发布包，至少在文档中标记当前安装方式边界。

完成标准：

- 构建产物包含所有 `src.*` 子包。
- 导入冒烟测试通过。

### P2：配置文件语义不统一

现象：

- `.env.example` 使用 `EMBEDDING_PROVIDER=openai`、`LLM_PROVIDER=openai`。
- `config/llm_config.yaml` 使用 `primary_provider: qwen`、`embedding_provider: dashscope`。
- `AppSettings` 实际主要从环境变量读取，`config/app_config.yaml`、`config/llm_config.yaml` 是否仍被运行时使用不明确。

建议处理：

1. 梳理运行时配置入口，只保留一个权威来源。
2. 如果 YAML 是旧配置，移动到文档示例或标记 deprecated。
3. README 与 `.env.example` 保持一致。

完成标准：

- 新开发者能从 README 明确知道使用 `.env` 还是 YAML。
- 配置测试覆盖默认值和环境变量覆盖。

### P3：历史迁移脚本和调试痕迹需要归档

现象：

- `Docs/migrations/_apply_auth.py`、`Docs/migrations/_apply_auth_v2.py` 含大量 `print` 和直接改文件逻辑。
- `Docs/debug_plan_review_tab_jump.md` 是历史调试计划。

建议处理：

1. 确认这些脚本是否仍需要执行。
2. 若仅作历史记录，移动到 `Docs/archive/` 或在文件头标明“历史脚本，禁止直接运行”。
3. 真正需要的迁移逻辑应进入受测试的迁移工具，而不是 Docs 下临时脚本。

完成标准：

- 现役脚本和历史记录边界清晰。
- 不再误把历史脚本当作可执行维护入口。

## 推荐执行顺序

1. 修复测试顺序依赖失败。
2. 确认并清理 Git 跟踪的 `pyc` 缓存文件。
3. 统一版本号。
4. 清理或处理 `pytest_collect_output.txt`、`qorder_comments.md` 移动状态。
5. 增加 pytest markers，拆分快速测试和全量测试。
6. 修正打包配置并增加导入冒烟验证。
7. 梳理配置文件权威来源。
8. 分阶段拆分 `src/ui/pages.py` 和 `src/ui/viewmodels.py`。
9. 归档历史迁移/调试脚本。

## 建议第一批执行任务

### 任务 1：修复测试顺序依赖

涉及文件：

- `tests/unit/test_ui.py`
- `tests/unit/test_startup_validation.py`（必要时）

验证命令：

```powershell
python -m pytest "tests/unit/test_startup_validation.py" "tests/unit/test_ui.py" -q
python -m pytest tests --maxfail=1 -q
```

### 任务 2：仓库卫生清理

涉及文件：

- Git 索引中的 `__pycache__/*.pyc`
- `.gitignore`（如需补充检查规则）
- `pytest_collect_output.txt`（确认后删除）

验证命令：

```powershell
git ls-files | rg "(__pycache__|\.pyc$)"
git status --short
```

### 任务 3：版本一致性

涉及文件：

- `pyproject.toml`
- `readme.md`
- `src/app.py`
- `tests/unit/test_startup_validation.py` 或新增轻量测试

验证命令：

```powershell
python -m pytest tests/unit/test_startup_validation.py -q
```

## 需要你确认的问题

1. 当前真实版本以 `0.6` 为准，还是以代码里的 `0.5` 为准？
2. `qorder_comments.md` 是否确认移动到 `Docs/qorder_comments.md`？
3. 是否允许清理 Git 已跟踪的 `__pycache__/*.pyc` 与本次生成的 `pytest_collect_output.txt`？
4. 第一批是否按“测试失败 -> 仓库卫生 -> 版本一致性”的顺序执行？

## 2026-06-16 执行结果

- 已修复 `tests/unit/test_ui.py` 与 `tests/unit/test_startup_validation.py` 的顺序依赖，并消除 `src.ui.app` 模块重载导致的旧对象污染。
- 已修复 `src/ui/pages.py` 中重复定义 `_has_tab_access()` 的权限覆盖问题，恢复未登录测试场景的默认放行逻辑。
- 已统一版本号到 `0.6`，同步更新 `pyproject.toml`、`src/app.py` 与版本相关测试。
- 已修复 `tests/integration/test_app.py` 中写死版本号与测试外联问题，集成测试默认显式收口为离线模式。
- 已将 Git 索引中的 `__pycache__/*.pyc` 缓存文件移除，并处理 `pytest_collect_output.txt`。
- 已补充 pytest markers 与按目录自动打标逻辑，支持 `unit` / `integration` 分类。
- 已修正 `pyproject.toml` 的 setuptools 包发现配置，`python -m build` 已通过。
- 已统一配置来源说明：运行时主配置以 `.env` / 环境变量为准，`config/logging.yaml` 与 `templates/settings/ingest_quality.yaml` 作为例外配置源；`config/app_config.yaml` 与 `config/llm_config.yaml` 标记为历史样例。
- 已将 `src/ui/pages.py` 中 `AI 质检优化 Dummy` 页签抽离到 `src/ui/quality_dummy_page.py`，降低主入口文件体积与维护成本。
- 已对历史迁移脚本与调试文档补充“归档参考 / 禁止执行”提示，避免被误当成现役入口。

### 最终验证

```powershell
python -m pytest tests -q
python -m build
```

验证结果：

- `python -m pytest tests -q`：`224 passed`
- `python -m build`：通过，成功生成 `sdist` 与 `wheel`
