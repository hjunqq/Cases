# 三方横向比较：HPC-Skills / KISS / ki-harness-langgraph

> 说明：KISS 仓库地址 `github.com/lzwei196/KISS` 现在对匿名访问返回 **404**（已私有或改名），HPC-Skills 抓取正常。下文关于 KISS 的事实全部采用已给定的抓取结果；404 这一条本身影响"照抄其格式"的可行性，见第 6 节。本仓库的所有结论来自实读代码与实查 SQLite 数据库。

---

## 1. 三方对照表

| 维度 | SciMate-AI/HPC-Skills | lzwei196/KISS | ki-harness-langgraph（本仓库） |
|---|---|---|---|
| **知识表示** | Markdown 为主：`SKILL.md`(触发元数据) + `references/`(细节) + `assets/templates/` + `scripts/`，22 个域 | 机器可读为主：`knowledge_infrastructure.yaml`(KI 清单)、`dag.yaml`、`format_spec.yaml`、`validation_convention.yaml`、`diagnostics/triplets.yaml`(2406 条) + `tools/*.py`(835 个) | **混合但两极分化**：`fem-chat/SKILL.md`(渐进披露描述符) + `fem-chat/CLAUDE.md`(107 行路由) + `docs/references/` 13 篇（764 行 / 6,779 词）；机器可读部分只有 `workflow/capability/registry.yaml`（6 个分析类型 + 网格单元类型 + code_patch 策略）与 20 个 `skills/templates/*.json`。**config.json 无任何 schema**（全仓库 grep 不到 jsonschema/schema.json），校验是命令式 Python：`skills/run_pipeline.py:78 validate_config()` |
| **知识获取** | 人工撰写 starter deck | KDT 从源码/文档/例子/数据/专家实践半自动抽取 | 人工 + **运行时沉淀**：`skills/promote_case.py:9-12` 一次调用扇出 4 层（case library / benchmark registry / KI / 文档），`skills/gen_catalog.py:134` 从 DB 反向生成 `docs/benchmark-catalog.md` |
| **执行编排** | 无。skill 只是给 agent 读的静态包 | `dag.yaml` 声明执行顺序/依赖/gate（声明式，无引擎） | **真运行时引擎**：LangGraph StateGraph，15 个节点（`workflow/graph/build.py:12-16` 的链路 intake→capability_gate→context_load→data_audit→data_repair→mesh_workflow→parameter_workflow→preflight→execute→evaluate→finalize，旁路 failure_triage→improve_router→code_patch_proposal→human_review），重试预算 `min(retry_budget,2)`（`workflow/graph/build.py:80`），SQLite checkpoint 可恢复，`workflow/supervisor/` 跨算例调度 |
| **校验与门控** | 无 | 三层协议（一致性 / 物理边界 / 质量守恒）+ NSE 阈值等定量判据，`preflight_check.py` | 两级：通用 `harness/gate.py:43 physics_gate()`（有结果 / 无 crash marker / 有限 / 非全零，注释明确写了"刻意粗糙"`harness/gate.py:45-47`）+ 13 个族级校验器 `skills/validate_results.py:1175 VALIDATORS`（cooks_membrane、lame_cylinder、mini_gravdam、seepage_steady、gravdam_modal_reservoir、gravdam_seismic_2block、beam_faceload_3d、slope_known_surface、slope_srm、staged_foundation、concrete_damage、rc_bond + 通用 golden_regression）。**单一门控**：`workflow/tools/validate_outputs.py:29` 与 `promote_case.py:40` 共用 `harness.gate`，注释记录了它们曾漂移过 |
| **失败恢复** | 无 | 症状→诊断→补救三元组 2406 条，机器可读 YAML | **有运行时自愈，但知识硬编码在 Python 里**：`workflow/graph/nodes/failure_triage.py:24-85` 用字符串匹配分 6 类 / 20+ 子类，`failure_triage.py:12-21 _proposals()` 映射到 data_repair / mesh_workflow / parameter_workflow / human_review 4 个目标。人读的诊断字典在 `docs/references/error-recovery.md`——7 条 `Pattern ID + Symptom + Root cause + First checks + Primary fix`，**形式上已是三元组，但没有一行代码消费它** |
| **经验沉淀闭环** | 无 | 有评测证据，但沉淀靠 KDT 离线打包，非运行时 | **闭环建成且设计精良**：`workflow/store/experience.py:20-58` 的 schema 含 scope / failure_class / failure_subclass / failure_signature / root_cause / fix_action / evidence / confidence / do_not_repeat / solver 血缘；`experience.py:239 expire_for_solver()` 按求解器族过期；`experience.py:313 find_relevant()` 五键排序召回。**但库是空心的**：`_experience_store.db` 实存 13 条，**全部 `outcome=resolved`，`failure_class` 全为 NULL**，root_cause 只有 "promoted: human-confirmed correct run"(11 条) / "validated successful run"(2 条)——**零条失败→恢复经验**，最有价值的 failure_signature 精确召回分支从未命中过 |
| **跨模型可迁移性** | 高（22 个求解器一套格式，框架中立） | 高（119 个 KI 包 × 14 个地学域） | **低**：全部围绕单一 HSTAR Fortran 求解器。MKL 路径注入、`1.cor/1.ele/1.glb/1.flavia.res` 文件名、`type_problem=Q/E/F/S` 语义硬编码在 skills 与文档（`CLAUDE.md:61-68`） |
| **框架耦合度** | 零耦合 | 零耦合（CLAUDE_TEMPLATE.md + AGENT_SERVICE_GUIDE.md） | **中**：分发层中立（`SKILL.md` + `docs/references/`，与 HPC-Skills 同构）；编排层绑定 LangGraph + FastAPI（`workflow/app.py`）+ SQLite |
| **成熟度与证据强度** | 弱：11 commits、76 star、0 issue/PR，只有骨架；抓取确认文档不描述任何验证/基准机制 | **最强**：3000 次试验 × 5 平台，带 KI 84% vs 不带 <40%；专家迁移 75 组合中 60 组达定量判据、零执行失败 | **工程成熟度高，科学证据弱**：31 个 skill / 11,293 行、313 个测试（`workflow/tests/` 260 + `skills/test_skills.py` 53）；但 24 条 benchmark 里只有 11 条有解析解或文献参考值，13 条是 `golden_regression`（min/max/n_values 自比对，只测漂移不测对错）。**无任何 A/B 对照**，"带 KI vs 不带 KI"的效果从未量化 |

**本仓库量化汇总**：31 个 Python skill（11,293 行，非 12 个）· 13 篇 reference（764 行 / 6,779 词）· 20 个模板 · 24 条 benchmark 目录项（13 程序级 + 11 回归级，registry DB 实存 11 行）· 13 个解析式校验器 · 11 个 case_library family · 13 条 KI（全为成功沉淀，0 条失败经验）· 313 个测试。

---

## 2. 各自的真实定位（对原判断的两处修正）

**HPC-Skills = 静态知识包分发，无闭环** —— 成立。抓取确认 `references/` 是主要知识载体，仓库文档不描述任何验证/基准机制。价值只在"渐进披露的分发格式"与"22 个域的目录学"。

**KISS = 有论文级证据的知识基础设施规范，无运行时自愈编排，域是地学** —— 成立。`dag.yaml` 是声明式的顺序/门控描述，不是引擎；恢复靠 agent 读三元组自纠，不是状态机重路由。

**"本方案有运行时闭环但知识形式化程度和证据强度较弱"——方向对，但两处要按代码事实修正，第二处更严重：**

**修正一：形式化程度不是"较弱"，是两极分化。** 编排与门控的形式化程度**超过 KISS**：`failure_triage` 的 6 类/20+ 子类分类法、`experience.py:132 _same_solver_lineage()` 的求解器族血缘过期、checkpoint 可恢复——这些 KISS 都没有。真正弱的只有两块：(a) 领域诊断知识（`error-recovery.md` 7 条）停在 markdown，代码不读；(b) **输入格式完全没有机器可读契约**（等价于 KISS `format_spec.yaml` 缺位）——这是最大的洞，`run_pipeline.py:78-140` 把 schema 校验、领域不变量（PRJ-6057 的 `force_process` 自动置 1、FSI 必须 PROFILE）、自动修复三件事全混在 100 行命令式代码里。

**修正二："闭环存在"要打折——闭环建好了，但失败侧从未转起来。** 数据库实测：13 条 KI 全部来自 `promote_case` 的人工确认路径，`failure_class` / `failure_signature` / `fix_action` 三个最有价值的字段一条都没填过。`CLAUDE.md:80-81` 那条"不要谎称学到了"的诚实纪律，恰恰说明这个闭环的失败侧至今空转。

---

## 3. 应该吸收什么

### 从 KISS

**① `format_spec.yaml` → config.json 的机器可读契约（洞最大）**
- 落点：新增 `fem-chat/contracts/config_schema.yaml`，由 `skills/run_pipeline.py:78` 与 `workflow/tools/build_parameters.py` 共同消费。
- 收益：把 `validate_config` 里散落的规则变成具名 rule id 后，`compatibility-matrix.md` 可以像 `benchmark-catalog.md` 一样自动生成（`gen_catalog.py` 已有此模式），杜绝文档-代码漂移；agent 也能直接读取约束而不必靠记忆。
- 改动量：中（3-4 天）。风险：低。**但不要把 auto-fix 逻辑一起声明化**——那些带副作用（`run_pipeline.py:130-140` 会改写 config），声明式表达会失真，只声明"校验"，保留"修复"为代码。

**② `diagnostics/triplets.yaml` → 把 `error-recovery.md` 变成代码读得懂的东西（性价比最高）**
- 落点：`fem-chat/knowledge/diagnostics.yaml`，字段直接沿用已有词汇：`pattern_id / symptom / root_cause / first_checks / primary_fix / failure_class / failure_subclass / proposed_target`。7 条现成模式原样搬。
- 三向消费：(a) `workflow/graph/nodes/failure_triage.py:24-85` 的匹配表改为从 YAML 加载，取代硬编码 token；(b) `docs/references/error-recovery.md` 改为由 YAML 生成；(c) `experience.py` 写入时用 `pattern_id` 作 `failure_signature` 前缀，让 KI 与诊断字典对齐、可统计"哪条模式命中最多"。
- 改动量：小（0.5-1 天）。风险：低。这是"知识散在 markdown"这个批评**唯一真正成立**的地方，且结构现成，几乎零设计成本。

**③ `knowledge_infrastructure.yaml` → 统一 KI 清单**
- 落点：`fem-chat/knowledge/ki_manifest.yaml`，按 case_family 聚合：模板名、校验器 key、benchmark id、case_library 快照路径、适用 reference、已知诊断模式。
- 收益：这些信息现在分散在 5 处（`skills/templates/` / `validate_results.py:1175` / `_benchmark_registry.db` / `workspace/case_library/` / `docs/references/`），agent 要靠读 CLAUDE.md 路由自己拼。一份清单让"这个族我到底有什么知识"可被程序回答。
- 改动量：中（2 天）。风险：中——**必须由 `gen_catalog.py` 生成，绝不手维护**，否则立刻腐烂。

**④ `preflight_check.py` → 已有，只需补量纲/范围**
- `workflow/graph/nodes/preflight.py` 已做文件存在性、网格后缀（大小写敏感，`preflight.py:44-47`）、求解器二进制检查。缺参数范围与量纲。落点：`workflow/tools/audit_inputs.py:223`，依赖 ①。改动量：小。

**⑤ `validation_convention.yaml` → 只吸收"容差与证据等级声明化"**
- 13 个 validator 已是这东西的 Python 实现，缺的是容差与来源外置。落点：`workflow/store/benchmark_registry.py:19` 的表加 `tolerance / metric / evidence_level`。收益：目前 `golden_regression` 与 `cooks_membrane` 在 `docs/benchmark-catalog.md` 里长得一模一样，但科学分量差一个数量级。改动量：中。

**⑥ KDT 抽取流程 —— 不建流水线，只借一个一次性动作**
- 单求解器不值得建抽取工具链。但值得做一次 Fortran 源码扫描，把 severe/forrtl 诊断字符串批量填进 ②的 diagnostics.yaml（`harness/gate.py:16` 目前只认 3 个 marker）。这是 KDT 思路对本项目唯一高回报的部分。

### 从 HPC-Skills

**⑦ `SKILL.md` + `references/` 渐进披露 —— 已经在做，且做得更细**
`fem-chat/SKILL.md` 已是标准 frontmatter + 触发描述 + 12 条分层路由 + Authoritative facts + Guardrails，`docs/references/` 13 篇就是它的 references。**不需要改。**

**⑧ `skills-index.md` —— 值得补一个场景轴索引**
`skills/README.md` 是中文索引但只按 Python 文件分类。缺"以求解场景为轴"的索引（family → 模板 → 校验器 → reference）。这与 ③是同一份数据的两种渲染，一起做。改动量：小。

---

## 4. 不该吸收什么

- **`dag.yaml` 声明式执行图。** KISS 需要它是因为没有引擎，只能把顺序写给 agent 看。本仓库有 `workflow/graph/build.py` 的 StateGraph + 15 节点 + 8 个条件路由函数 + checkpoint。再加一层 YAML DAG 只会造出第二个事实源。**这是本次比较最容易踩的坑。**
- **NSE / 质量守恒 / 水量平衡判据。** 纯地学水文域特性。结构 FEM 的对应物是能量平衡、残差范数、支座反力平衡——该建自己的，不要套它的名字。
- **多 agent 框架适配层（`agents/openai.yaml`）。** HPC-Skills 追求跨 UI 分发；本项目运行时是自家 Next.js + workflow 服务，多写一份适配只增加维护面。
- **119 个 KI 包的广度。** 他们的广度来自"每模型一个薄包"。本仓库 11 个 family 每个都有 golden + 模板 + 网格快照 + 指纹（`workspace/case_library/*/meta.json`），深度比铺 100 个空包有价值。不要为对标数字灌水 family。
- **把沉淀改成离线 KDT 打包。** `promote_case.py` 的运行时四层扇出比 KISS 的离线抽取先进，别退回去。

---

## 5. 落地路线

### P0（1-2 天，立刻见效）

| 项 | 落点 | 工作量 |
|---|---|---|
| **P0-1 诊断三元组 YAML 化** | 新建 `fem-chat/knowledge/diagnostics.yaml`（搬 `docs/references/error-recovery.md` 现有 7 条）；`workflow/graph/nodes/failure_triage.py:24-85` 的 `_classify_*` 改为从 YAML 加载；`skills/gen_catalog.py` 加一个 renderer 反向生成 error-recovery.md | 0.5-1 天 |
| **P0-2 让 KI 的失败侧真正落数据** | `workflow/graph/nodes/finalize.py` / `improve_router.py`：triage→repair→重试成功时写一条 `failure_class/failure_subclass/failure_signature/fix_action` 齐全的经验（当前 13 条这些字段全 NULL）；同时 `promote_case.py:200-213` 的人工确认记录显式标注来源，与自愈经验区分 | 0.5 天 |
| **P0-3 benchmark 证据等级** | `workflow/store/benchmark_registry.py:19` 加 `evidence_level`（analytic / literature / archive_regression / self_golden），`gen_catalog.py:103` 渲染进目录表 | 0.5 天 |

P0 做完，"诊断知识散在 markdown、KI 库空心、benchmark 分量不可辨"三个最实的短板同时消掉。

### P1（1-2 周）

| 项 | 落点 | 工作量 |
|---|---|---|
| **P1-1 config 机器可读契约** | `fem-chat/contracts/config_schema.yaml` + `skills/run_pipeline.py:78` 消费；PRJ-6057 / FSI-PROFILE / 材料引用 / appear 行数等不变量登记为具名 rule id，与 diagnostics 的 pattern_id 打通 | 3-4 天 |
| **P1-2 KI 清单 + 场景索引自动生成** | `fem-chat/knowledge/ki_manifest.yaml` 由 `skills/gen_catalog.py` 从 5 个源聚合；同时输出 `docs/skills-index.md` | 2 天 |
| **P1-3 preflight 补量纲/范围** | `workflow/tools/audit_inputs.py:223`，依赖 P1-1 | 1-2 天 |
| **P1-4 容差声明化** | `skills/validate_results.py` 13 个 validator 的容差外置到 registry | 2 天 |

### P2（1 个月+）

| 项 | 说明 |
|---|---|
| **P2-1 KI 效果 A/B 量化** | **这是相对 KISS 唯一真正缺的东西。** 选 5 个 family，各跑 N 次「带 KI 召回」vs「禁用 experience store」，统计首次成功率与迭代次数。架构天生支持——`experience.py:313 find_relevant()` 加个开关即可。有了这组数据，在证据强度上不输 KISS，而且测的是**运行时自愈**，比他们的静态知识注入更硬。 |
| **P2-2 Fortran 错误码扫描** | 一次性投入，把 diagnostics 从 7 条扩到几十条 |
| **P2-3 KI 包只读导出器** | 见下节 |

---

## 6. 取舍建议：**双轨，但严重不对称——自研为主干，KI 包只做导出层**

**推荐：继续自研演进（95% 精力），把"重打包成 KISS KI 包格式"降级为 P2 的一个只读导出器（5% 精力），且不早于 P1-2 完成。**

1. **架构在关键维度上领先，重打包是降维。** KISS 的核心资产是知识规范 + 评测证据；它没有 LangGraph 那样的失败重路由、没有求解器血缘驱动的经验过期（`experience.py:132`）、没有 checkpoint 可恢复。把本仓库的东西塞进它的目录格式，编排层的价值无处安放。

2. **可迁移性没有真实需求。** KISS 的格式价值来自 119 包 × 14 域的横向复用。本项目只有一个 Fortran 求解器，跨模型迁移收益接近零，为不存在的需求付格式税不划算。

3. **可发表性是唯一真动机，但达成它的路径不是换格式，而是 P2-1 那组 A/B 数据。** KISS 论文的说服力来自 3000 次试验的 84% vs 40%，不来自 YAML 长什么样。现已有 24 个 benchmark、11 个 family、313 个测试、一套完整闭环——缺的只是把开关关掉再跑一遍对照。**先出数据，再谈格式。**

4. **KISS 仓库现在匿名 404，1 star、25 commits。** 把知识资产绑定到可用性未知、社区规模为零的外部格式上是纯风险。相反，吸收它的**设计思想**（三元组、format_spec、KI 清单）零风险——那些本来就是好工程实践，与其仓库存亡无关。

**唯一值得做的"双轨"动作**：P1-2 的 `ki_manifest.yaml` 建成后，写一个约 200 行的 `skills/export_ki_package.py`，把单个 case_family 导出成 KISS 风格的自足目录（SKILL.md + format_spec + triplets + validation + tools 软链）。它只是清单的又一个 renderer，成本极低，需要投稿或对外交付时随时可用——但**内部主干永远是自己的 registry + LangGraph，不做双向同步**。
