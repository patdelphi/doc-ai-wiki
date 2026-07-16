# UI 与认证改造 Todo

> 时间：2026-05-12
> 范围："src/ui"、"src/auth"、"src/db"、"tests/unit"
> 目标：持续收敛登录、刷新、顶部导航、AI 质检首屏与整体交互体验问题

## 2026-06-22 PageIndex Question Plan 机制优化

> 范围：`src/pageindex`、`templates/pageindex`、`tests/unit`
> 设计文档：`Docs/design/pageindex_question_plan_mechanism_20260622.md`
> 目标：用 LLM 生成结构化 Question Plan，替代 Python 硬编码问题路由。

## 2026-06-23 PageIndex 迭代式推理检索计划

> 范围：`src/pageindex/service.py`、`tests/unit/test_pageindex_service.py`、`tests/evaluation/pageindex_cases.jsonl`
> 计划文档：`Docs/optimization-plan/pageindex_iterative_reasoning_plan_20260623.md`
> 目标：把 PageIndex 从“候选节点 rerank + RAG/FTS 补证据”升级为最小可用的“迭代式推理检索”闭环。

## 2026-06-24 AI 质检逻辑回退与 PageIndex 解耦

> 范围：`src/quality/service.py`、`tests/unit/test_quality.py`、`src/quality/verdicts.py`、`tests/unit/test_verdicts.py`
> 计划文档：`Docs/optimization-plan/restore_ai_quality_before_683151e_plan_20260624.md`
> 目标：按 `683151e^` 恢复 AI 质检核心逻辑，同时保留 PageIndex 的 QuestionPlan、模板和 query expansion 能力。

### P0

- [x] 新建安全分支 `codex/revert-ai-quality-before-683151e`
- [x] 确认 AI 质检逻辑污染点：`683151e` 的 `verdicts` 抽象与 `3a324ef` 的 query expansion 接入
- [x] 新增防回归测试：AI 质检不复用 PageIndex 的实体别名扩展
- [x] 从 AI 质检调用链移除 `src.quality.verdicts`
- [x] 从 AI 质检调用链移除 `query_normalizer` / `expand_query_texts`
- [x] 保留 PageIndex 对 `query_normalizer` 的使用
- [x] 标记 `Docs/claim_evaluation_run_20260623.md` 为无效评估，避免继续作为优化依据

### 验收标准

- AI 质检 `_build_retrieval_queries("驴皮胶能改善贫血")` 不再生成 `阿胶能改善贫血`、`阿胶 贫血`
- `tests/unit/test_quality.py` 全量通过
- 默认知识库下拉仍默认选中 `default`
- PageIndex 仍可继续使用 query expansion
- 不自动 commit，完成后等待确认

### P0

- [x] 新增迭代检索 prompt，要求 LLM 返回 `selected_nodes`、`sufficiency`、`missing_information`、`next_search_focus`
- [x] 新增单文档多轮检索闭环：选择节点、读取内容、判断充分性、不足则继续检索
- [x] 将 LLM PageIndex 检索入口从单轮节点选择切换为迭代式检索
- [x] 在 `debug_json` 中记录每轮检索节点、充分性判断、缺失信息和下一轮检索焦点
- [x] 知识库多文档聚合时保留每个文档的检索轮次 debug

### P1

- [x] 增加最小交叉引用识别：`详见`、`参见`、`附录`、`表`、`图`、`第...章`
- [x] 将交叉引用匹配到 PageIndex 树节点，并作为下一轮候选
- [x] 增加 5-10 条 PageIndex 迭代检索评测样例
- [x] 更新答案质量计划，记录迭代检索验收标准

### 验收标准

- 问题证据不足时，检索会继续下一轮，而不是直接生成模糊答案
- 证据充分时，检索能提前停止
- debug 中能看到每一轮选了哪些节点、为什么选、是否充分、还缺什么
- 知识库级检索仍覆盖当前知识库下所有已构建 PageIndex 的文档
- 单测不调用外部 API

### P0

- [x] 单独编写 Question Plan 机制设计文档
- [x] 新增 Question Plan schema、prompt 构建与归一化模块
- [x] 移除“有哪些/方法/步骤”等硬编码信息抽取路由
- [x] 最终回答模板注入 `{question_plan}` 变量
- [x] 补齐假 LLM 单测，验证信息抽取类问题不会被当作命题真假判断

### P1

- [x] 将 Question Plan 写入 PageIndex debug 信息，方便历史结果排查
- [x] 根据 Question Plan 调整候选证据选择提示词，提升召回精度
- [x] 将典型测试问题重新写入 DB，便于 UI 历史查看
- [x] 优化 PageIndex 内置模板梯度：宽松速览、普适问答、严谨问答、证据审查、医学安全、原文定位

### 验收标准

- “阿胶有哪些质量检测方法”应按信息抽取回答，给出方法清单和来源
- “心脏病吃阿胶有好处吗”应按命题判断回答，明确证据是否支持
- 测试不调用外部 API
- PageIndex 模板编辑仍兼容旧模板

## 已完成

- [x] 修复登录后顶部大块空白
- [x] 修复用户名与退出登录位置错乱
- [x] 修复菜单栏高度异常
- [x] 消除登录后持续 `processing` 红框
- [x] 首次进入 AI 质检页不再自动加载上次历史
- [x] 退出登录后清空登录输入框与提示信息
- [x] 登录页外框高度收敛
- [x] 刷新后保持登录态
- [x] 刷新时不再先闪登录页
- [x] 退出登录改为纯文字样式，并与顶部导航对齐

## 进行中

- [x] 继续统一顶部导航文字、间距、字号与点击反馈，消除残余视觉不一致
- [ ] 继续梳理 AI 质检页首屏层级，减少首次进入时的认知负担
- [x] 继续检查认证链路边界行为，确保登录、刷新、登出、回退场景稳定

## 后续待办

### P0

- [x] 盘点并修复其余页面与顶部导航的对齐问题，保持所有页头行为一致
- [ ] 清理认证相关状态流，避免未来继续出现初始化误触发
- [ ] 为登录恢复、登出清理、首屏初始化补齐更聚焦的单测

### P1

- [x] 继续优化 AI 质检页布局密度，减少冗余外框和空白
- [x] 复核知识库管理、人工审核、检索页的顶部样式是否与主导航一致
- [ ] 清理项目中的临时调试文件与本地日志归档策略

### P2

- [ ] 补充 "Docs" 下的任务、设计与变更说明，形成可追踪文档
- [ ] 梳理 `.gitignore` 与本地运行产物边界，避免再次混入无用文件
- [ ] 继续按需完善 UI 回归用例与最小验收清单

## 验收标准

- 顶部导航在所有登录态页面样式一致、位置稳定
- 刷新、登出、重新登录链路无错误中间态
- AI 质检页首屏不自动带入历史结果，且无异常联动
- 相关 UI/认证单测通过，手工浏览器验收通过

## 2026-05-13 P0 第一批执行计划

> 范围："src/app.py"、"src/auth/service.py"、"src/ui/pages.py"、相关测试
> 来源："Docs/code_review_execution_checklist.MD"

### 本轮目标

- [x] 收敛 API 权限边界，补齐最小认证与鉴权入口
- [x] 修复认证服务中的默认弱口令与禁用用户可登录问题
- [x] 让 UI 真正按 `tab_names` 与 `kb_ids` 控制可见范围
- [x] 先补最小测试，再做小步实现与回归验证

### 当前执行顺序

1. 先确认 API 认证方案与读接口保护范围
2. 先补认证与 API 权限测试
3. 再修改 `"src/auth/service.py"` 与 `"src/app.py"`
4. 最后修改 `"src/ui/pages.py"` 并跑受影响测试

## 2026-05-13 P1 第二批执行计划

> 范围："src/db/schema.py"、"src/db/repositories.py"、"src/knowledge_base/service.py"、相关测试
> 来源："Docs/code_review_execution_checklist.MD"

### 本轮目标

- [x] 为审核记录补齐 Claim 级一致性约束或等效防护
- [x] 收敛知识库删除前的关联数据校验，避免只检查文档数
- [x] 先补回归测试，再做小步修复与验证

### 当前执行顺序

1. 先补知识库删除与审核一致性测试
2. 再修改 `"src/db/schema.py"` 与 `"src/db/repositories.py"`
3. 最后修改 `"src/knowledge_base/service.py"` 并跑聚焦测试

## 2026-05-13 `"src/ui/pages.py"` 稳妥拆分计划

> 范围："src/ui/pages.py"、"src/ui/app.py"、"tests/unit/test_ui.py"
> 目标：在不破坏现有 UI 行为的前提下，逐步拆分 `"src/ui/pages.py"`，降低后续维护与回归风险

### 拆分原则

- [ ] 不做一次性暴力拆分，按“公共 helper -> 独立页面 -> 复杂页面”三阶段推进
- [ ] 每一批只做一种结构调整，避免同时修改页面布局、业务逻辑和事件绑定
- [ ] 先保留 `"src/ui/pages.py"` 作为总装配入口，最后再收缩成轻量编排文件
- [ ] 优先减少闭包依赖与超长 tuple 输出，再做物理文件拆分
- [ ] 每一批重构后都执行聚焦单测与诊断检查，必要时补最小回归测试

### 第一批：抽公共能力

- [ ] 抽离权限相关 helper：知识库可见性、登录态权限解析
- [ ] 抽离分页 helper：分页、页码切换、当前页取行、分页提示
- [ ] 抽离通用 UI helper：统一按钮、表格分页 HTML、导出通用函数
- [ ] 保持 `"build_ui()"` 对外签名不变，避免影响 `"src/ui/app.py"`

### 第二批：先拆低风险页面

- [ ] 先拆 `"知识库检索"` 页，形成 `build_search_tab()` 与 `bind_search_events()`
- [ ] 再拆 `"功能设置"` 页，形成 `build_settings_tab()` 与 `bind_settings_events()`
- [ ] 拆分时统一返回“组件字典/组件对象”，不再依赖散落局部变量
- [ ] 对事件绑定的 `inputs/outputs` 建立命名常量或组件集合，减少顺序错位风险

### 第三批：再拆高耦合页面

- [ ] 拆 `"人工审核"` 页，先收敛筛选、分页、详情、动作提交流程
- [ ] 拆 `"AI 质检"` 页，重点处理 Claim、证据、历史记录、评测联动
- [ ] 最后拆 `"知识库管理"` 页，因为该页输出链最长、联动最复杂
- [ ] 最终让 `"src/ui/pages.py"` 只负责总装配与跨页面共享依赖

### 测试策略

- [ ] 拆分前先补最小保护测试，锁定 `"build_ui()"` 可构建、关键组件存在、关键事件无启动报错
- [ ] 每拆一批都执行 `"tests/unit/test_ui.py"` 聚焦用例，必要时新增页面级回归测试
- [ ] 每拆一批都执行诊断检查，确认无新增导入错误、名称错误、循环依赖
- [ ] 高风险批次完成后再执行更大范围的 UI 相关单测回归

### 每批验收标准

- [ ] `"src/ui/app.py"` 无需修改调用方式，`create_ui_app()` 仍能成功返回 `gr.Blocks`
- [ ] `"tests/unit/test_ui.py"` 相关用例通过
- [ ] 页面组件 `elem_id` 与当前测试依赖的关键结构保持兼容
- [ ] 登录态权限、知识库切换、分页与导出链路不出现回归

### 建议执行顺序

1. 先补 helper 抽离保护测试
2. 再抽公共 helper，不改页面行为
3. 然后拆 `"知识库检索"` 页并跑聚焦测试
4. 再拆 `"功能设置"` 页并跑聚焦测试
5. 最后分批处理 `"人工审核"`、`"AI 质检"`、`"知识库管理"`

## 2026-05-13 用户注册与权限管理开发计划

> 范围："src/ui/pages.py"、"src/ui/settings_page.py"、"src/auth/service.py"、"src/db/schema.py"、"src/db/repositories.py"、相关测试
> 目标：补齐用户注册、后台权限配置，以及功能设置页二级菜单化管理能力

### 需求约束

- [x] 用户注册只输入"用户名"、"密码"、"重复密码"
- [x] 注册密码最多 20 个字符，不增加其他复杂度限制
- [x] 除了"admin"外，新注册用户默认无任何菜单权限、无任何知识库权限
- [x] 用户权限必须在后台配置，至少覆盖"可访问菜单（tab页）"与"可访问知识库"
- [x] "功能设置"页增加主菜单下方二级 tab 标签
- [x] 现有配置管理迁移到二级子页面
- [x] 新增"用户管理"子页面
- [x] 新增"用户权限管理"子页面

### 开发原则

- [ ] 先补测试，再改实现，保持小步提交
- [ ] 不破坏现有"admin"使用路径与已有登录逻辑
- [ ] 所有新增 API / 回调都补异常处理
- [ ] 数据库相关写操作保持事务一致性
- [ ] 先保留现有菜单权限模型，优先复用已有 `tab_names`、`kb_ids` 语义

### 第一批：注册规则收口

- [x] 补充注册输入与校验测试：仅三项输入、密码长度上限 20、两次密码一致
- [x] 调整注册表单与回调，只保留"用户名"、"密码"、"重复密码"
- [x] 修改认证服务注册逻辑，超过 20 字符直接返回业务错误
- [x] 确认非"admin"用户注册后不写入任何默认权限

### 第二批：后台用户管理

- [x] 设计并补充用户管理数据访问测试
- [x] 梳理/补齐用户列表、启用状态、基础信息维护所需的数据层接口
- [x] 在"功能设置"下新增"用户管理"子页面
- [x] 子页面至少提供用户列表、创建结果反馈、基础信息查看入口

### 第三批：后台权限管理

- [x] 设计并补充用户权限管理测试，覆盖菜单权限与知识库权限保存/读取
- [x] 梳理并补齐权限配置所需的数据层接口
- [x] 在"功能设置"下新增"用户权限管理"子页面
- [x] 支持为指定用户配置可访问 tab 页
- [x] 支持为指定用户配置可访问知识库
- [x] 保存后联动现有登录态可见范围逻辑

### 第四批：功能设置页二级菜单重构

- [x] 先补"功能设置"二级 tab 结构回归测试
- [x] 将现有配置管理迁移到"配置管理"子页面
- [x] 新增"用户管理"子页面布局
- [x] 新增"用户权限管理"子页面布局
- [x] 保持现有 `elem_id` 与主要交互尽量兼容，降低 UI 回归风险

### 验收标准

- [x] 新用户可仅凭用户名和两次密码完成注册
- [x] 超过 20 字符的密码会被拒绝，并返回清晰错误提示
- [x] 新用户首次登录后默认看不到任何业务菜单与知识库
- [x] 管理员可在后台为用户配置菜单权限与知识库权限
- [x] "功能设置"页可通过二级 tab 切换到"配置管理"、"用户管理"、"用户权限管理"
- [x] 相关 UI/认证/启动回归测试通过

### 建议执行顺序

1. 先补注册与权限数据层测试
2. 再收口注册表单与认证服务逻辑
3. 然后补用户管理与权限管理数据接口
4. 再改"功能设置"页二级 tab 与两个新子页面
5. 最后跑 UI 全量、认证相关与启动回归

## 2026-05-13 知识库与文档归属修复计划

> 范围："src/knowledge_base"、"src/ui/pages.py"、"src/ui/viewmodels.py"、"tests/unit"、"tests/integration"
> 目标：收敛知识库目录与 Input 文档归属统一规则，修复默认知识库历史遗留文件不一致问题，并加强知识库管理页场景回归

### 需求约束

- [x] 新建知识库后，自动在 `"Input"` 下创建对应子目录，目录名使用知识库 ID
- [x] 只有放在对应 `"Input/<knowledge_base_id>"` 子目录中的 MD 文件，才允许作为该知识库的自动入库来源
- [x] 处理历史遗留：`"Input"` 根目录下的 `"a1"`、`"a2"` 迁移并归属于 `"Input/default"`
- [x] 修复后需重点回归 `"知识库管理"` 页，覆盖新建、切换、扫描、注册、重建、调整归属、分页等场景

### 开发原则

- [x] 先补测试，再改实现，保持小步修复
- [x] 所有知识库包括 `"default"` 都只识别各自 `"Input/<knowledge_base_id>"` 子目录，不再兼容扫描 `"Input"` 根目录旧文件
- [x] 所有文件移动与数据库归属更新保持一致，不制造“文件在 A、数据库在 B”的分裂状态
- [x] 优先复用现有知识库服务与文档归属调整逻辑，避免重复实现
- [x] 修复后必须跑 UI、知识库、启动相关回归，并补最小手工验收清单

### 第一批：补测试锁定行为

- [x] 补 `"scan_input_documents"` 测试，覆盖 `"default"`、非默认知识库，以及旧根目录文件迁移后的行为
- [x] 补知识库创建测试，覆盖创建后自动生成 `"Input/<knowledge_base_id>"`
- [x] 补 `"知识库管理"` 页 handler 测试，覆盖切换知识库、扫描列表、注册文档、批量注册、重建、归属调整
- [x] 明确 `"a1"`、`"a2"` 历史文件迁移后的归属、扫描展示与入库结果

### 第二批：修目录与扫描规则

- [x] 检查并收口知识库创建后的目录初始化逻辑
- [x] 收口 Input 扫描规则：非默认知识库仅扫自身子目录
- [x] 收口默认知识库扫描规则，使其与其他知识库一致，仅扫 `"Input/default"`
- [x] 确认自动入库只处理当前知识库目录下的 MD 文件

### 第三批：处理历史遗留文件

- [x] 处理 `"Input"` 根目录下 `"a1"`、`"a2"` 的迁移与默认知识库归属修正
- [x] 将旧文件迁移到 `"Input/default"` 并保证数据库归属一致
- [x] 补迁移后的兼容测试，确认默认知识库文档列表与注册结果正确

### 第四批：集中回归知识库管理页

- [x] 回归新建知识库后目录与下拉联动
- [x] 回归切换知识库后的文档列表、摘要、分页与操作按钮状态
- [x] 回归注册单文档、批量注册、查询状态、重建索引
- [x] 回归调整文档归属到其他知识库后的文件移动与列表刷新
- [x] 跑 `"tests/unit/test_ui.py"`、知识库/入库相关单测、`"tests/unit/test_startup_validation.py"`

### 验收标准

- [x] 新建知识库后，磁盘上存在对应 `"Input/<knowledge_base_id>"`
- [x] 非默认知识库不会扫到其他目录或 `"Input"` 根目录下的文档
- [x] 默认知识库仅识别 `"Input/default"`，且能正确承接迁移后的 `"a1"`、`"a2"` 文件
- [x] `"知识库管理"` 页关键路径稳定，无明显错误或状态错乱
- [x] 相关单测、集成测试、启动回归通过

## 2026-05-14 零权限用户登录体验修正计划

> 范围："src/ui/pages.py"、"src/ui/page_helpers.py"、"tests/unit/test_ui.py"、必要的文档说明
> 目标：让“新注册默认无权限”与 UI 体验一致，不再出现菜单先显示后消失、最终落到错误业务页的问题

### 现状问题

- [x] 新用户后端权限为空，但前端初始渲染与登录后权限收口不一致，导致菜单闪烁
- [x] 零权限用户登录后没有合理落点，当前会出现空白或错误停留在某个业务页
- [x] 当前 `"AI 质检"` 残留可见状态不符合“默认无业务权限”的产品语义

### 拟定方案

- [x] 增加一个不受业务权限控制的固定入口页，例如 `"待开通"` 或 `"个人中心"`
- [x] 新用户无菜单权限时，仅显示该固定入口页，不显示任何业务 tab
- [x] 入口页展示当前账号、权限状态、可访问知识库状态，以及“请联系管理员开通权限”的明确提示
- [x] 管理员为当前用户开通权限后，当前登录态即时刷新，业务 tab 立即出现
- [x] 保持 `"admin"` 与已有授权用户的现有路径不变

### 执行顺序

1. 先补零权限用户登录态的 UI 回归测试
2. 再增加固定入口页与零权限落点逻辑
3. 然后收口 tab 可见性与默认选中行为，消除菜单闪烁
4. 最后验证后台改权后的即时联动

### 验收标准

- [x] 新注册用户登录后不会看到任何业务 tab 闪现或点击后消失
- [x] 零权限用户始终有明确可见的落地页，不会出现空白主界面
- [x] 后台开通权限后，当前登录用户无需重新登录即可看到新增功能
- [x] 相关 UI 聚焦测试通过

## 2026-05-14 权限总收口计划

> 范围："src/auth/service.py"、"src/ui/page_helpers.py"、"src/ui/pages.py"、"src/ui/*_page.py"、"src/app.py"、相关测试
> 目标：集中收敛菜单权限、知识库权限、对象级权限与状态刷新链路，消除“显示已收口但实际仍可访问”的混乱状态

### P0

- [x] 去掉 `session=None` 时默认全量放行的权限解析回退
- [x] 去掉普通用户 `user_permissions` 标记缺失时自动回退全菜单/全知识库
- [x] 收口人工审核页，所有候选/历史/提交链路都必须显式带 `login_session`
- [x] 收口知识库管理页，所有扫描/注册/重建/归属调整链路都必须显式带 `login_session`
- [x] 为 UI 关键权限链路补回归测试，覆盖无菜单权限、无知识库权限、旧权限标记缺失三类场景

### P1

- [x] 收口知识库检索页与 AI 质检页剩余未统一的知识库解析入口
- [x] 收口后台改权后的页面状态刷新，统一清空审核/检索/文档管理旧 state
- [x] 收口 API 层对象级权限：`check_id`、`claim_id`、`doc_uid`、`chunk_id`

### 执行顺序

1. 先补测试锁定当前权限漏洞
2. 再改认证权限默认回退
3. 然后修人工审核和知识库管理实际查询/写入入口
4. 最后补 API 对象级权限与状态刷新

## 2026-06-16 优化计划执行记录

> 范围："tests/unit/test_ui.py"、"tests/unit/test_startup_validation.py"
> 来源："Docs/optimization-plan-20260616.md"
> 当前阶段：方案 A - 第 1 步

### 本轮目标

- [x] 修复 `"src.ui.app"` 模块重载导致的 UI 测试顺序依赖
- [x] 保持修改范围最小，不处理删除类操作
- [x] 跑聚焦校验，确认 `"test_startup_validation.py"` 与 `"test_ui.py"` 顺序执行稳定

### 当前执行顺序

1. 先定位 `"src.ui.app"` 相关导入是否被旧模块对象污染
2. 再补最小测试保护或直接修复现有测试导入方式
3. 最后执行 `"python -m pytest \"tests/unit/test_startup_validation.py\" \"tests/unit/test_ui.py\" -q"`

### 当前结果

- [x] 精确复现组合 `"test_create_ui_app_should_auto_rebuild_vectors_when_embedding_dimension_mismatch_at_startup"` + `"test_connection_scoped_auth_service_should_open_and_close_connection_per_call"` 已通过
- [x] 已修复 `"src/ui/pages.py"` 中尾部重复定义的 `_has_tab_access()` 覆盖问题，恢复未登录测试场景的默认放行逻辑
- [x] 聚焦回归 `6` 个失败用例已全部通过
- [x] 整组 `"tests/unit/test_startup_validation.py"` + `"tests/unit/test_ui.py"` 已通过，结果 `62 passed`

### 下一步待确认

- [x] 已清理 Git 已跟踪的 `__pycache__/*.pyc`
- [x] 已处理 `"pytest_collect_output.txt"`
- [x] 当前真实版本以 `"0.6"` 为准

### 版本一致性结果

- [x] 已将 `"pyproject.toml"` 版本从 `"0.5"` 统一为 `"0.6"`
- [x] 已将 `"src/app.py"` 中 FastAPI 应用版本从 `"0.5"` 统一为 `"0.6"`
- [x] 已在 `"tests/unit/test_startup_validation.py"` 增加版本一致性测试
- [x] `python -m pytest "tests/unit/test_startup_validation.py" -q` 结果 `5 passed`
- [x] `python -m pytest "tests/unit/test_startup_validation.py" "tests/unit/test_ui.py" -q` 结果 `63 passed`

### 集成测试补充结果

- [x] 已将 `"tests/integration/test_app.py"` 中版本断言改为动态读取 `"pyproject.toml"`
- [x] 已将集成测试 `"build_test_settings()"` 收口为离线模式：`EMBEDDING_PROVIDER="local"`、`LLM_PROVIDER="disabled"`、`RERANK_ENABLED=False`
- [x] 已同步修正集成测试中 3 处直接构造 `AppSettings(...)` 的离线配置，避免读取本地 `.env` 外联
- [x] `python -m pytest "tests/integration/test_app.py" -q` 结果 `29 passed`
- [x] `python -m pytest tests --maxfail=1 -q` 结果 `223 passed`

### 计划剩余项完成情况

- [x] 已为 pytest 增加 `unit` / `integration` markers，并在 `"tests/conftest.py"` 中按目录自动打标
- [x] 已修正 `"pyproject.toml"` 的 setuptools 包发现配置，覆盖 `"src*"` 子包
- [x] 已统一 `.env.example`、`"readme.md"`、`"Docs/env.MD"` 的运行时配置语义，并明确 `.env` 为主配置来源
- [x] 已为 `"config/app_config.yaml"`、`"config/llm_config.yaml"` 增加“历史样例”说明，避免误当成运行时配置
- [x] 已新增 `"tests/unit/test_config_defaults.py"`，锁定 `.env.example` 与 `AppSettings` 关键默认值一致
- [x] 已将 `"src/ui/pages.py"` 中 `"AI 质检优化 Dummy"` 页签抽离至 `"src/ui/quality_dummy_page.py"`
- [x] 已为 `"Docs/migrations/_apply_auth.py"`、`"Docs/migrations/_apply_auth_v2.py"`、`"Docs/debug_plan_review_tab_jump.md"` 增加归档/禁止执行提示
- [x] 已更新 `"Docs/optimization-plan-20260616.md"`，记录本轮执行结果与最终验证
- [x] `python -m pytest tests -q` 结果 `224 passed`
- [x] `python -m build` 已通过

## 2026-06-17 PageIndex 路径规范优化

- [x] 新增 Input 相对路径解析工具，统一禁止绝对路径入库与路径越界。
- [x] 更新文档注册、知识库迁移、PageIndex 构建逻辑，数据库只保存相对 Input 路径。
- [x] 更新旧绝对路径修复逻辑，将历史路径修复为相对路径。
- [x] 补充并更新聚焦测试，验证注册、迁移、PageIndex 修复均不再写绝对路径。
- [x] 跑聚焦测试并重启本地 Gradio 服务。

## 2026-06-17 PageIndex 语义检索修复

- [x] 确认搜索效果差的根因：提问阶段只做关键词打分，没有使用 LLM 树推理。
- [x] PageIndex 提问改为优先用 LLM 基于树结构选择证据节点。
- [x] 取回证据后优先使用 LLM 生成回答，失败时回退本地关键词与本地摘要。
- [x] 补充 PageIndex 语义检索与 LLM JSON 调用测试。
- [x] 聚焦测试、编译检查通过，并重启 Gradio。

## 2026-06-17 PageIndex LLM 状态显示

- [x] PageIndex 状态卡显示 LLM 状态、当前检索模式和模型信息。
- [x] 提问结果显示本次实际检索模式。
- [x] LLM 调用失败降级时显示降级原因。
- [x] 补充服务层与 UI 层聚焦测试。
- [x] 聚焦测试、编译检查通过，并重启 Gradio。

## 2026-06-17 PageIndex 状态误报修复

- [x] 确认数据库 pageindex_indexes 记录为 ready，前端“失败”为状态卡误报。
- [x] 通用操作结果卡在缺少 success 字段时显示“提示”，不再显示“失败”。
- [x] PageIndex 切换到已构建文档时自动加载结构树，并显示“PageIndex 已构建，可直接提问”。
- [x] 补充 PageIndex UI 与通用结果卡回归测试。
- [x] 聚焦测试、编译检查通过，并重启 Gradio。

## 2026-06-17 LLM API 兼容与状态文案修复

- [x] 将中性操作卡从“执行状态：提示”改为“当前状态：状态说明”。
- [x] 定位 LLM 报错不是旧 AI 质检链路，而是 PageIndex 新增 complete_json 链路。
- [x] complete_json 在 response_format 不兼容/超时时，自动重试普通 chat/completions 并提取 JSON。
- [x] 真实 LLM 最小调用通过，返回 ok/pong。
- [x] 聚焦测试、编译检查通过，并重启 Gradio。

## 2026-06-17 AI 质检 RAG 召回修复

- [x] 确认 AI 质检使用 RAG DB 检索，不直接依赖 source_path 原文路径。
- [x] 排查数据库：default 知识库仍有 chunks 与 FTS 数据，历史旧记录有来源文档。
- [x] 定位最近记录无来源的根因：中文整句 Claim 直接检索容易零召回。
- [x] 为普通中文 Claim 增加关键词查询兜底，例如“阿胶能治疗癌症”补充“阿胶 癌症 / 癌症 / 阿胶 治疗”。
- [x] 真实 RAG 检索验证可召回来源，质量/检索单测通过，并重启 Gradio。

## 2026-06-17 PageIndex 明确状态文案

- [x] PageIndex 状态卡显示具体索引状态：已构建、未构建、未选择文档。
- [x] PageIndex 状态卡显示具体 LLM 状态：LLM 可用、LLM 不可用。
- [x] 去除“状态说明”这类抽象文案。
- [x] 补充 UI 文案回归测试。
- [x] 聚焦测试、编译检查通过，并重启 Gradio。

## 2026-06-18 PageIndex 效果优化计划

> 范围："src/pageindex/service.py"、"src/ui/pages.py"、"src/ui/pageindex_page.py"、"tests/unit/test_pageindex_service.py"、"tests/unit/test_pageindex_ui.py"
> 目标：在继续使用本地 PageIndex、不接线上服务或 MCP 的前提下，提高中文长文档问答的召回准确率、回答质量与可解释性。

### 关键假设

- [ ] 继续直接使用 vendor/pageindex 项目，不自造 PageIndex 树结构能力。
- [ ] PageIndex 数据继续按知识库和文档隔离，不能跨知识库混检。
- [ ] PageIndex 主要负责文档结构定位；细粒度事实命中可结合本地 RAG/FTS。
- [ ] 前端继续沿用 Gradio，并参考第一个 tab 的交互方式。
- [ ] 不引入新外部服务；如需调用 LLM，只使用项目现有 LLM 配置。

### 当前问题判断

- [ ] 现在只显示最终命中证据，缺少候选节点、选择理由、原文上下文，无法判断错在召回还是回答。
- [ ] LLM 树推理目前只看节点标题/摘要，原文上下文不足，容易变成标题关键词匹配。
- [ ] 论文集/合集类文档结构复杂，PageIndex 树节点数量大，直接让 LLM 从大量节点里选容易跑偏。
- [ ] 对具体事实类问题，PageIndex 结构定位不一定比 RAG/FTS 更强，需要混合检索。

### P0：增加调试与可解释面板

- [x] 服务层返回 `debug` 字段，包含候选节点、候选分数、LLM 选择理由、是否降级。
- [x] UI 增加“检索诊断”表格，展示本次命中的候选节点、位置、选择理由、检索模式。
- [x] 保留用户正常问答体验，不强迫用户看调试信息。
- [x] 测试覆盖：PageIndex 提问返回 debug；UI 能显示命中理由；LLM 降级时显示降级原因。

### P1：问题理解与查询改写

- [x] 新增本地方法 `_analyze_question()`，提取问题意图、实体、关键词、同义表达。
- [x] LLM 可用时用 LLM 生成结构化 JSON；失败时走本地中文关键词兜底。
- [x] 将改写后的关键词用于 PageIndex 候选召回，避免只按原问题字面匹配。
- [x] 测试覆盖：例如“对皮肤有什么帮助”应能联想到“滋养、润燥、皮肤状态改善”。

### P2：候选节点二次重排

- [x] 第一阶段用本地规则从 PageIndex 树召回 top 30 候选。
- [x] 第二阶段让 LLM 基于“问题 + 标题 + 摘要 + 少量原文”重排候选。
- [x] 限制每个节点原文长度，避免超上下文或调用过慢。
- [x] 测试覆盖：标题不含问题关键词但摘要/原文语义相关时，应排到前面。

### P3：PageIndex + RAG/FTS 混合检索

- [x] PageIndex 先定位章节/节点范围。
- [x] 本地 RAG/FTS 在当前知识库、当前文档范围内补充细粒度原文证据。
- [x] 回答时优先引用“PageIndex 节点 + RAG 原文片段”的组合证据。
- [x] 测试覆盖：当前文档内事实问答能召回具体原文；不同知识库文档不能混入。

### P4：回答生成质量优化

- [x] 回答 prompt 明确要求：只基于证据回答、不知道就说明证据不足、列出来源节点。
- [x] 结果区展示“结论 / 依据 / 来源位置 / 不确定点”。
- [x] 对证据不足的问题返回“未找到充分证据”，不硬编答案。
- [x] 测试覆盖：有证据问题应包含来源标题，LLM prompt 强制证据约束格式。

### P5：建索引前文档清洗

- [x] 针对 Markdown 清理图片占位、目录标题、分隔线噪音。
- [x] 对论文合集类文档识别文章边界，减少一个超大树里混杂太多主题。（已形成计划：`Docs/optimization-plan/pageindex_article_boundary_plan_20260623.md`）
- [x] 清洗只影响 PageIndex workspace 构建输入，不改用户原始文档。
- [x] 测试覆盖：清洗输出保留标题与正文，删除明显噪音。

### 建议执行顺序

1. [x] 先做 P0 调试面板，让效果问题可观察。
2. [x] 再做 P1 问题理解，减少字面关键词匹配。
3. [x] 再做 P2 二次重排，提高命中节点质量。
4. [x] 如果仍然不够，再做 P3 混合检索。
5. [x] 最后做 P5 文档清洗，作为长期质量提升。

### 验收标准

- [x] PageIndex 页面能明确显示：已构建、LLM 可用、本次检索模式、命中节点、选择理由。
- [x] 至少准备 10 条固定问题，对比优化前后命中节点和回答质量。
- [x] 具体事实问题必须显示来源文档与 PageIndex 节点位置。
- [x] 语义问题不能只靠问题关键词匹配；无关键词同义问题也应能命中合理章节。
- [x] 不同知识库之间不发生证据混淆。
- [x] 聚焦测试通过：`python -m pytest "tests/unit/test_pageindex_service.py" "tests/unit/test_pageindex_ui.py" -q`。

### 暂不做

- [ ] 不替换 PageIndex 项目。
- [ ] 不接 PageIndex 线上服务或 MCP。
- [ ] 不新增数据库迁移，除非 P0/P3 实现时确实需要保存诊断历史。
- [ ] 不自动 commit；执行完成后再由用户确认是否提交。

## 2026-06-20 Markdown 知识库可信 MVP 优化计划

> 范围："src/chunking"、"src/metadata"、"src/ingest"、"src/retrieval"、"src/quality"、"src/db"、"tests"、"Docs"
> 来源："Docs/md_knowledge_base_project_analysis_20260620.md" 复核结果
> 目标：把当前可用 MVP 收口为证据可追溯、测试可验证、验收可交付的可信 MVP。

### 关键假设

- [ ] 不继续扩大新功能范围，优先修正 Markdown 分块、元数据追溯、verdict、评测和运行期数据治理。
- [ ] 当前主 verdict 先以代码实际枚举 `"verified"`、`"needs_review"`、`"rejected"` 为基准，再决定是否迁移到更细枚举。
- [ ] PageIndex 保持长文档增强定位，不替代主 RAG/FTS 检索验收。
- [ ] `python` 与 `pytest` 当前可用；全量测试需要单独安排更长超时时间或分组执行。
- [ ] 所有新增功能先补测试，再做最小实现；数据库结构变更必须有事务和迁移/兼容策略。

### P0：验收与测试状态收口

- [x] 修正分析文档中“python/pytest 不可用”的过期描述，改为“测试可收集，单元与集成测试已分组通过”。
- [x] 分组运行全量测试，至少覆盖 `"tests/unit"`、`"tests/integration"`、PageIndex、UI、质量服务。
- [x] 记录测试结果到 `"Docs/test_report_20260620.md"`，包含命令、耗时、通过/失败/超时情况。
- [x] 基于实际测试结果更新 `"Docs/acceptance.MD"`，避免已实现能力长期未勾选。
- [x] 新增 `"Docs/acceptance_report_20260620.md"`，逐项标注已通过、部分通过、未通过、未验证。

### P0：运行期数据治理

- [x] 复核 `".gitignore"` 对 `"index/"` 的处理边界：当前已忽略数据库和 Chroma，但未忽略 PageIndex workspace JSON。
- [x] 决定 `"index/pageindex_workspace/"` 是否应整体忽略，或改为只保留可公开 fixture。
- [x] 明确 `"logs/"`、`"*.db"`、导出文件、临时运行文件的同步策略。
- [x] 更新 `"readme.md"` 或 `"Docs/deployment"`，说明索引、数据库、PageIndex workspace 的重建方式。
- [x] 验证 `git status --short --branch` 不再出现容易误提交的运行期数据。

### P1：Markdown 结构感知分块

- [x] 为当前固定长度分块补回归测试，锁定长段落、表格、代码块、引用块的期望行为。
- [x] 新增 Markdown 结构解析能力，识别段落、列表、表格、引用块、代码块。
- [x] 以语义块为基本单位合并 chunk，只有超长普通段落才做保守二次切分。
- [x] 保留现有 `split_text()` 兼容入口，入库服务无需改调用方即可使用新分块器。
- [x] 跑 `"tests/unit/test_chunking.py"`、`"tests/unit/test_sections.py"` 和入库相关测试。

### 2026-06-20 P1 Markdown 分块执行结果

- [x] 已将 `"src/chunking/splitter.py"` 从纯固定长度切分升级为 Markdown 语义块优先切分。
- [x] 表格、围栏代码块、连续引用块会保持在同一 chunk 中；超长普通段落继续按长度兜底切分。
- [x] `python -m pytest tests/unit/test_chunking.py -q` 结果 `4 passed`。
- [x] `python -m pytest tests/unit/test_sections.py tests/unit/test_ingest_quality.py tests/unit/test_knowledge_base.py -q` 结果 `18 passed`。
- [x] `python -m pytest tests/integration/test_app.py::test_register_document_and_query_status_should_work tests/integration/test_app.py::test_vector_and_hybrid_search_should_return_results_after_ingest tests/integration/test_app.py::test_rebuild_should_support_fulltext_and_vector_separately -q` 结果 `3 passed`。
- [x] `python -m pytest tests -q` 结果 `267 passed`。

### P1：元数据与证据追溯

- [x] 设计 `heading_path`、`source_start_line`、`source_end_line`、`chunk_type`、`content_hash`、`source_anchor` 的存储或派生方案。
- [x] 如需改表，新增兼容旧数据库的初始化/迁移逻辑，确保事务内完成。
- [x] 入库时为 section 和 chunk 写入稳定出处信息，检索与质检结果透传到 evidence details。
- [x] UI/导出中展示可人工复核的来源位置，不只显示笼统 `source_span`。
- [x] 增加证据可追溯率测试，确认质检结果能定位到原文范围。

### 2026-06-20 P1 元数据追溯执行结果

- [x] `document_sections` 增加 `heading_path`、`source_start_line`、`source_end_line`、`source_anchor`。
- [x] `chunks` 增加 `heading_path`、`source_start_line`、`source_end_line`、`page_no`、`chunk_type`、`content_hash`、`source_anchor`。
- [x] `initialize_database()` 可为旧版章节表和分块表自动补齐追溯列。
- [x] Markdown 章节解析保留标题路径与行号范围。
- [x] 入库写入 chunk 类型、内容 hash 和 source anchor；全文检索、向量检索和 chunk detail 透传追溯字段。
- [x] 审核证据详情、证据 HTML 和质检导出展示标题路径、来源锚点、chunk 类型和内容 hash。
- [x] `python -m pytest tests/unit/test_sections.py tests/unit/test_ingest_quality.py tests/unit/test_retrieval.py -q` 结果 `9 passed`。
- [x] `python -m pytest tests/unit/test_vector_store.py tests/integration/test_app.py::test_vector_and_hybrid_search_should_return_results_after_ingest tests/integration/test_app.py::test_rebuild_should_support_fulltext_and_vector_separately -q` 结果 `9 passed`。
- [x] `python -m pytest tests/unit/test_viewmodels.py -q` 结果 `45 passed`。
- [x] `python -m pytest tests/unit/test_ui.py -q` 结果 `58 passed`。
- [x] `python -m pytest tests -q` 结果 `270 passed`。

### P1：verdict 与证据关系统一

- [x] 梳理当前 `"verified"`、`"needs_review"`、`"rejected"` 与 `"support"`、`"contradict"`、`"insufficient"` 的关系。
- [x] 决定是否引入 `"contradicted"`、`"suspected"`、`"insufficient_evidence"`、`"manual_review_required"` 细枚举。
- [x] 若保持简化枚举，更新设计文档、验收文档、UI 文案和评测口径，避免文档与代码不一致。
- [ ] 若迁移细枚举，先写兼容映射和历史结果展示测试，再改服务、API、UI、导出。
- [x] 增加无证据、弱证据、反证、绝对化、唯一性 claim 的回归测试。

### 2026-06-20 P1 verdict 体系统一执行结果

- [x] 新增 `"src/quality/verdicts.py"`，集中定义 claim verdict、证据关系、保守合并和总体 verdict 聚合。
- [x] 当前阶段保留 API 简化枚举：`"verified"`、`"needs_review"`、`"rejected"`；总体全通过仍输出 `"passed"`。
- [x] 证据关系细分保留在 `"support"`、`"contradict"`、`"insufficient"`，用于修正模型 verdict。
- [x] `QualityService` 的总体 verdict 聚合与 LLM/启发式合并已改用统一 helper。
- [x] `python -m pytest tests/unit/test_verdicts.py tests/unit/test_quality.py -q` 结果 `23 passed`。
- [x] `python -m pytest tests/unit/test_viewmodels.py::test_claim_display_helpers_should_generate_markdown_and_rows tests/integration/test_app.py::test_quality_and_review_flow_should_persist_result -q` 结果 `2 passed`。
- [x] `python -m pytest tests -q` 结果 `275 passed`。

### P1：实体归一与查询扩展

- [x] 建立最小实体词表目录，例如 `"data/entities"`，先覆盖当前知识库高频术语和别名。
- [x] 新增 query normalization，处理别名、同义表达、繁简/异体、领域术语。
- [x] 在入库、检索、质检三处复用同一套归一逻辑，避免各模块硬编码补丁分裂。
- [x] 增加中文问法变化、别名查询、同义查询的检索测试。

### 2026-06-20 P1 实体归一与查询扩展执行结果

- [x] 新增 `"data/entities/term_dictionary.json"`，先覆盖 `"阿胶"`、`"驴皮胶"`、`"驢皮膠"`、`"东阿阿胶"` 等最小别名和异体写法。
- [x] 新增 `"src/retrieval/query_normalizer.py"`，集中提供查询归一、查询扩展和入库索引文本归一。
- [x] 入库写入 FTS 时保留原始 chunk 内容，并追加归一文本，不改写 `"chunks.content"` 原文。
- [x] 全文检索会按原 query、标准名 query、别名 query 依次检索并按 `chunk_id` 去重。
- [x] AI 质检的 retrieval queries 复用同一套归一扩展，别名 Claim 会生成标准名与关键词查询。
- [x] `python -m pytest "tests/unit/test_query_normalizer.py" "tests/unit/test_retrieval.py" "tests/unit/test_quality.py" -q` 结果 `25 passed`。
- [x] `python -m pytest "tests/unit/test_ingest_quality.py" "tests/integration/test_app.py::test_register_document_and_query_status_should_work" "tests/integration/test_app.py::test_vector_and_hybrid_search_should_return_results_after_ingest" -q` 结果 `8 passed`。

### P2：正式评测集与质量指标

- [x] 新增 `"tests/evaluation/retrieval_cases.jsonl"`，至少 50 条问题与标准证据。
- [x] 新增 `"tests/evaluation/claim_check_cases.jsonl"`，至少 50 条 claim 与人工标注 verdict。
- [x] 新增 `"tests/evaluation/rule_cases.jsonl"`，覆盖命中与非命中样例。
- [x] 扩展 PageIndex 固定问题到 50 条，并区分真实 LLM 与离线降级结果。
- [x] 输出固定指标：Top-5 命中率、claim 准确率、无证据 verified 率、证据可追溯率。

### 2026-06-20 P2 正式评测集与质量指标执行结果

- [x] 新增 `"src/retrieval/evaluation.py"`，提供 JSONL 读取、检索 Top-K 命中率、证据追溯率、Claim verdict 准确率、无证据 verified 率计算。
- [x] 新增 `"tests/evaluation/retrieval_cases.jsonl"`，当前 `50` 条检索问题与标准证据标注。
- [x] 新增 `"tests/evaluation/claim_check_cases.jsonl"`，当前 `50` 条 Claim 与人工标注 verdict。
- [x] 新增 `"tests/evaluation/rule_cases.jsonl"`，覆盖规则命中与非命中样例。
- [x] 新增 `"tests/unit/test_retrieval_evaluation.py"` 与 `"tests/unit/test_evaluation_fixtures.py"`，锁定指标计算和评测集最低规模。
- [x] `python -m pytest "tests/unit/test_retrieval_evaluation.py" "tests/unit/test_evaluation_fixtures.py" -q` 结果 `6 passed`。
- [x] 新增 `"tests/evaluation/pageindex_cases.jsonl"`，当前 `50` 条 PageIndex 固定问题，并用 `requires_llm` / `mode` 区分真实 LLM 推理与离线降级样例。
- [x] 新增 `"Docs/retrieval_evaluation_run_20260620.md"`，记录本地只读检索评测运行结果。
- [x] 新增 `"Docs/evidence_catalog_20260620.md"`，从真实 SQLite 只读导出 `200` 条候选证据目录，用于人工对齐标准证据 ID。
- [x] 新增 `"Docs/retrieval_alignment_suggestions_20260621.md"`，为 `50` 条检索样例生成真实证据 ID 候选建议，覆盖率 `1.0`。
- [ ] 当前检索评测样例的标准 `doc_uid` / `chunk_id` 尚未与本机真实知识库 ID 对齐，Top-5 命中率为 `0.0`，后续需补对齐后的真实评测集。
- [x] 已基于真实本地知识库形成 Claim 本地离线评测运行结果：`Docs/claim_evaluation_run_20260623.md`，50 条样例准确率 `0.18`，无证据 verified 率 `0.0`，差距已明确记录；PageIndex 真实 LLM / 离线降级分组运行结果仍需单独执行。

### P2：PageIndex 与主链路融合

- [ ] 保持 PageIndex 作为长文档结构增强，主验收仍以 RAG/FTS/质检链路为准。
- [x] 检查 PageIndex 主证据与 RAG/FTS 补充证据是否稳定合并，而不是互相覆盖。
- [x] 对论文合集类 Markdown 增加文章边界识别计划，减少一个超大树中主题混杂。（见 `Docs/optimization-plan/pageindex_article_boundary_plan_20260623.md`）
- [x] 设计跨文档 PageIndex 检索策略，但不在可信 MVP 收口前优先实现。（见 `Docs/optimization-plan/pageindex_cross_document_retrieval_strategy_20260623.md`）

### 2026-06-22 PageIndex 答案质量 P0 执行计划

- [x] 将 PageIndex 提问和历史从单文档范围修正为知识库范围。
- [x] PageIndex 主证据与 RAG/FTS 补充证据合并保留，避免引用不完整。
- [x] 本地降级回答改为“结论 / 证据判断 / 依据 / 来源 / 不确定点”。
- [x] 增加证据分类：`direct_support`、`indirect_related`、`risk_warning`、`locator_only`。
- [x] PageIndex 证据表增加“证据类型”列。
- [x] LLM 回答提示词要求区分直接支持、间接相关、风险提醒和仅定位信息。
- [x] P1 服务层新增 PageIndex 模板管理，复用 AI 质检模板的 YAML 管理思路，但使用独立目录和变量。
- [x] P1 PageIndex 页新增回答模板选择，并接入 LLM 最终回答 prompt。
- [x] P1 接入设置页 UI，实现 PageIndex 模板可视化新增、编辑、删除。
- [x] P2 后续按需开放 PageIndex 模板高级检索策略配置。

### 验收标准

- [x] `python -m pytest tests` 能完成并形成可追踪报告。
- [x] `"Docs/acceptance.MD"` 与实际代码、测试状态一致。
- [x] 运行期 `"index/"`、日志、数据库不会被误提交。
- [x] 每个 chunk 至少能追溯到标题路径、原文范围和 chunk 类型。
- [x] 无证据或证据不足时不会输出 `"verified"`。
- [x] 50 条检索样例 Top-5 命中率达到 80% 或明确记录差距。
- [x] 50 条 claim 样例准确率达到 80% 或明确记录差距。（2026-06-23 本地离线评测准确率 `0.18`，见 `Docs/claim_evaluation_run_20260623.md`）
- [x] 人工审核可保存、可查询，原始 verdict 不被覆盖。

## 2026-07-16 项目整体与检索算法审计计划

> 时间：2026-07-16
> 性质：只读审计；未经确认不修改业务代码、不调用外部 API、不安装依赖
> 重点：检索链路清晰度、检索质量、性能、可维护性、评测可信度

### P0：建立当前基线

- [x] 检查 Git 状态、项目结构、依赖、配置、启动入口与现有文档，识别当前版本真实状态。
- [x] 梳理从文档入库、切分、索引、查询归一、召回、融合、重排到证据输出的完整数据流。
- [x] 执行测试收集与聚焦的幂等校验，避免外部网络调用；记录通过、失败和未执行项。

### P0：检索算法专项审计

- [x] 审查 FTS/BM25、向量检索、混合检索、查询扩展、去重与分数融合策略。
- [x] 审查 PageIndex 的候选生成、Question Plan、迭代式检索、节点选择、补充证据和无答案保护。
- [x] 检查分块边界、元数据追溯、实体归一、通用词过滤、跨文档检索和缓存一致性。
- [x] 识别重复召回、隐式降级、阈值散落、规则互相覆盖及算法职责混杂等复杂度来源。

### P1：质量与性能验证

- [x] 核验评测集是否与当前真实知识库 ID 对齐，避免指标失真或假绿。
- [x] 复核 Top-K 命中率、无答案准确性、证据可追溯率、重复率与端到端延迟指标。（未调用外部服务，延迟仅完成静态调用链审查）
- [x] 覆盖正例、负例、歧义问题、别名问题、跨文档问题及“无直接证据”问题。
- [x] 检查数据库访问、索引使用、批处理、缓存和 LLM 调用次数中的明显性能瓶颈。

### P1：架构与工程质量审计

- [x] 检查模块边界、异常处理、事务、SQLite WAL 配置、配置管理、日志和安全边界。
- [x] 检查测试分层、离线隔离、环境变量泄漏、文档与代码漂移、冗余代码及过期产物。
- [x] 只记录与当前目标相关的问题，不进行顺手重构。

### 输出与完成标准

- [x] 输出按 P0/P1/P2 排序的问题清单，每项包含证据、影响、根因与建议。
- [x] 给出简洁的检索架构图和推荐目标链路，明确保留、合并、删除或延后的模块。
- [x] 给出分阶段优化路线、验收指标、测试建议和风险说明。
- [x] 未经再次确认，不实施代码修改、Git 操作、外部 API 调用或依赖变更。

### 2026-07-16 审计结果

- [x] 专项报告：`Docs/optimization-plan/retrieval_pageindex_audit_20260716.md`。
- [x] 主检索专项测试：`29 passed`。
- [x] PageIndex 专项测试：`83 passed`。
- [x] 测试收集：`350 tests collected`。
- [x] 全量首错：`tests/unit/test_auth_service.py::test_auth_service_should_create_disabled_admin_without_default_password`，原因是测试读取真实 `.env` 配置。
- [x] 未执行业务代码修改、外部 API、索引重建、数据库迁移、依赖安装和 Git 操作。

### 2026-07-16 AI 检索与 PageIndex 优化设计

- [x] 确认采用分阶段闭环修复方案。
- [x] 确认 AI 检索目标流程、算法边界和单次检索索引重建策略。
- [x] 确认 PageIndex 层级树、文档路由、动态多轮检索和单次重建策略。
- [x] 确认测试、验收、回滚和执行边界。
- [x] 将设计过程同步到 `Docs/design/retrieval_pageindex_optimization_design_20260716.md`。
- [x] 完成设计文档自检并由用户最终确认。
- [x] 编写可执行实施计划：`Docs/tasks/retrieval_pageindex_implementation_plan_20260716.md`。
- [ ] 按实施计划执行；未经确认不调用外部服务、不安装依赖、不迁移数据库、不重建正式索引。

### 2026-07-16 实施进度

- [x] 完成实施计划 Task 1-10 的本地代码和隔离测试。
- [x] 完成 Task 11 的指标算法与只读评测 CLI。
- [x] 完成 Task 12 的 CI、PR 检查模板和交付文档代码。
- [x] 本地验证：Mypy 18 个目标文件通过；完整测试 `378 passed, 6 warnings in 198.03s`；sdist/wheel 构建成功。
- [x] 安装 Ruff 并执行 lint。
- [x] 完成外部模型连通性验证、真实数据库追溯字段回填、检索索引与 PageIndex 正式重建。
- [x] 重建后运行 50 条真实候选回归评测并生成 `Docs/retrieval_pageindex_evaluation_20260716.md`。
- [ ] 指标达标并完成恢复演练后，将“按实施计划执行”标记完成。

### 2026-07-16 正式执行结果

- [x] 安装 Ruff 并通过 `python -m ruff check src tests .aipython`。
- [x] 验证 LLM、Embedding、Rerank 连通；正式评测 Rerank 覆盖率 1.0、降级样例 0。
- [x] 正式重建 Trigram FTS 与 Chroma：SQLite/FTS/向量均为 4207 条，`consistent=true`。
- [x] 正式重建两个 Markdown PageIndex：352/953 节点，深度 4/6，追溯率与覆盖率均为 1.0。
- [x] 事务化回填 1164 个章节和 4206 个业务 chunk 的追溯字段，备份与活动库完整性通过。
- [x] 修复向量结果从 SQLite 刷新追溯字段和 PageIndex `抗贫血研究` 长短语拆解。
- [x] 生成真实 ID 候选回归集与 `Docs/retrieval_pageindex_evaluation_20260716.md`。
- [x] 完成检索与 PageIndex `restore --latest` dry-run；未实际覆盖已验证活动索引。
- [x] 最终校验：Ruff 通过；Pytest `390 passed, 6 warnings`；Mypy 通过；build/compileall 通过。
- [ ] 人工复核 50 条检索样例的一个或多个真实相关 chunk；当前候选回归指标不代表正式质量。
- [ ] 重标 55 条 PageIndex 样例的真实文档和稳定节点 ID，再运行 Node Hit@5 与拒答准确率。
- [ ] 相关性与 PageIndex 正式指标达到门槛后，再把专项质量验收标记为完全通过。
