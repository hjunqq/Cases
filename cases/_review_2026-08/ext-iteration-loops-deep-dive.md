# 两个外部仓库的「迭代优化闭环」深挖报告

调查日期 2026-08-25。全部通过 `gh api <repo>/contents/<path> --jq '.content' | base64 -d` 匿名读取。
行号指本报告下载时的文件内容（HPC-Skills 最新提交 2026-04-06；KISS 最新提交 2026-08-21）。

---

# 仓库 A：SciMate-AI/HPC-Skills

**规模**：22 个 skill，全部在 `skills/` 下；仓库总 457 KB；76 stars；建于 2026-03-16，最后 push 2026-04-06；**11 个提交，0 个 tag，0 个分支保护，无 `.github/`（404）**。

## A.1 节点编排

**结论：不存在可执行的编排层。编排是散文形式的「阶段清单」，由 agent 在自己的推理里执行。**

- `skills/hpc-orchestration/SKILL.md` 是唯一的"编排 skill"，2928 字节。它的正文全部是 `1. Read references/X.md when Y` 这种**渐进式阅读顺序**（12 条），不是节点图。没有 YAML、没有状态机、没有条件分支、没有节点 ID。
- `references/public-protocol.md`「Workflow contract」一节声明了 8 阶段生命周期：
  > `1. stage inputs / 2. generate configuration / 3. validate a small run / 4. submit or launch through the scheduler / 5. monitor queue and logs / 6. classify failures / 7. repair inputs or runtime shape / 8. resume, restart, or post-process`
  紧接着自己承认它不是强制的：
  > "Every solver skill does not need to implement all eight stages directly, but it should be compatible with this lifecycle."
  —— 即：**没有任何机制检查某个 skill 是否符合这个契约**。
- 唯一的"分层"是**职责划分**，写在 `public-protocol.md`「Responsibility split」：solver skill 拥有 domain inputs / physics / 失败分类；`hpc-orchestration` 拥有 scheduler / 队列 / 监控 / 日志驱动的控制流。这是文档约定，没有代码接口。
- `references/lifecycle-manual.md` 只有 1143 字节，是全仓库最接近"编排定义"的东西，全文四节：Lifecycle phases（4 步）、Shared execution layer（5 步）、Self-healing loop（6 步）、Cross-skill coordination。全部是无序散文列表。

## A.2 失败恢复

**结论：这是仓库 A 唯一真正有结构的部分，但仍然是给人/agent 读的知识，不是可执行逻辑。**

### 自愈循环（声明）
`references/lifecycle-manual.md`「Self-healing loop」全文：
```
1. submit
2. monitor
3. tail logs
4. classify failure
5. repair solver input
6. resubmit
Do not improvise repairs before checking the solver-specific error references.
```
`SKILL.md`「Guardrails」补了一条硬规则：
> "Do not resubmit unchanged failing jobs when a solver-specific error dictionary exists."

**这个循环没有任何代码实现。** 谁来执行 submit→monitor→classify→repair→resubmit？是 agent 自己按散文照做。仓库里没有 driver、没有 orchestrator 脚本、没有 while 循环。

### 错误码表（真实存在，质量不错）
`references/error-pattern-dictionary.md`（4736 字节）是**唯一带稳定 ID 的结构化知识**，13 条，schema 固定四字段：

```
### Pattern ID: `HPC_JOB_STUCK_PENDING`
- **Likely symptom**: the job remains pending for too long
- **Root cause**: impossible resource request, wrong partition, or queue backlog
- **First checks**: inspect nodes/tasks/walltime/memory; inspect queue or partition name
- **Primary fix**: reduce or correct the resource request before resubmitting
```
ID 命名空间：`HPC_SCHEDULER_UNKNOWN` / `HPC_BATCH_DIRECTIVE_MISMATCH` / `HPC_LAUNCH_COMMAND_MISMATCH` / `HPC_JOB_STUCK_PENDING` / `HPC_HOME_OR_PROJECT_QUOTA_EXCEEDED` / `HPC_MODULE_STACK_CONFLICT` / `HPC_LOG_NEVER_CREATED` / `HPC_STAGE_IN_INCOMPLETE` / `HPC_REMOTE_TOOL_RUNNING_ON_LOGIN` / `HPC_PORT_FORWARD_MISMATCH` / `HPC_REPEAT_DIVERGENCE_LOOP`。

最后一条 `HPC_REPEAT_DIVERGENCE_LOOP` 值得注意——它专门治"agent 反复重投同一个失败作业"这个循环病：
> Root cause: solver inputs were not actually repaired between runs. Primary fix: repair solver inputs before resubmitting, not after.

### 各 solver skill 的 `references/error-recovery.md`：**两种形态并存，质量落差极大**

| skill | error-recovery.md | 形态 |
|---|---:|---|
| hpc-openfoam | 7626 B | **真决策树 + 可复制命令 + 具体数值** |
| hpc-lammps | 1606 B | 散文 |
| hpc-su2 | 1121 B | 纯散文，全文四节，每节 3-4 条「verify X」 |

OpenFOAM 版本是唯一"生产级"的（有 `## First 5 Things to Check` 五条 shell 命令、一棵 ASCII 决策树、`Courant Number mean: 608.234` 这样的真实日志片段、`p=0.2-0.3, U=0.5-0.7` 这样的具体松弛因子）。SU2 版本全文只有这种句子：
> "If residuals stall or blow up: 1. verify the solver family and boundary setup 2. verify freestream or inlet state consistency..."
—— **没有错误码、没有决策树、没有数值、没有命令**。

所以「solver 特定错误字典」在协议里是必需品，在实现上只有 OpenFOAM 一家做到了。

## A.3 自我研究

**结论：不存在。** 没有任何 skill 有"先做小规模试算再放大"的可执行路径。`public-protocol.md` 的第 3 阶段 "validate a small run" 只是一个词。没有 benchmark、没有 eval 套件、没有 golden case、没有测试。

## A.4 知识自更新

**结论：完全不存在。这个仓库的知识只能由人手工提交。**

证据：
- 无 `CHANGELOG`、无 `VERSION`、无 tag（`gh api .../tags` 返回空）。skill 内部也没有 `version:` 字段——`SKILL.md` 的 frontmatter 只有 `name` 和 `description` 两个键。
- 11 条提交全是人写的批量扩充："Massively enrich hpc-vasp and hpc-openfoam skills with production-grade knowledge density"、"Add production-grade hpc-ls-dyna skill"。没有一条来自"某次运行失败后回写"。
- `AGENTS.md`「Working rules」是唯一的维护规范，是给人看的编辑守则："Keep SKILL.md concise and move deep domain knowledge into references/"、"Prefer official upstream documentation when enriching technical knowledge"。**知识来源明确指向上游官方文档，不是运行经验。**
- `public-protocol.md`「Validation expectations」说 "run the available skill validator when possible" —— **仓库里没有这个 validator**。这是"设计文档声称有、代码里根本不存在"的一处。

## A.5 评测与校准

**结论：零。** 无 CI、无 test、无 metrics、无 benchmark、无 eval。所谓 `scripts/` 只有 4 个文件，且**只在 `hpc-orchestration` 一个 skill 里存在**（我遍历了全部 22 个 skill，其余 21 个都是 `SKILL.md + agents + assets + references`）：

- `hpc_job_submitter.py` (7437 B)
- `hpc_job_monitor.py` (4395 B) —— 读全文：三个 scheduler 各一个函数，把 squeue/qstat/bjobs 的状态归一化成 `PENDING/RUNNING/COMPLETED/FAILED`，`--wait_for_running` 是一个 10 秒轮询的阻塞 while 循环，超时 `sys.exit(1)`。**这是全仓库唯一的"循环"，而且只是等待，不带任何重试或修复。**
- `hpc_log_tracker.py` (4575 B) —— `tools-and-scripts.md` 声称它 "tails logs, extracts metrics, and can kill jobs on explicit divergence signatures"。这是仓库里唯一带"自动动作"的组件。
- `hpc_slurm_deploy.py` (3645 B)

## A.6 `agents/openai.yaml` 到底是什么

**是一个 4 行的 UI 装饰文件，没有任何 agent 语义。** `hpc-orchestration/agents/openai.yaml` 全文 232 字节：
```yaml
interface:
  display_name: "HPC Orchestration"
  short_description: "Coordinate scheduler, monitoring, and end-to-end HPC workflows"
  default_prompt: "Use $hpc-orchestration to design or repair an end-to-end HPC cluster workflow."
```
没有 tools 声明、没有权限、没有模型配置、没有 hooks。`README.md` 自己也这么定位："`agents/openai.yaml` is included where it helps Codex-style UIs, but the skill content stays tool-neutral."

## A.7 `hpc-foundations` 的角色

**是共享基座，但是"知识基座"不是"代码基座"。** `SKILL.md`「Positioning」三句话说得很清楚：
> - Prefer this skill for orientation, taxonomy, and first-pass explanation.
> - Prefer `hpc-orchestration` once the question becomes an execution workflow on a real cluster.
> - Prefer solver-specific skills once the question becomes input-deck or application specific.

它的知识**来源于爬取 hpclib.com**（`references/source-catalog.md` 7994 B 是"page-level lookup of the hpclib.com crawl"），并且 skill 自己给自己打了不信任标签：
> "Treat hpclib.com as a practical knowledge index, not as the final authority for production commands. Re-check scheduler flags, MPI launch syntax, package names, and admin procedures against official upstream documentation before applying them on a live cluster."

它没有 `assets/`、没有 `scripts/`，只有 8 个 references。另有 `references/skillization-roadmap.md`，是"把这个索引拆成更窄的 skill"的计划——**一个人工的、未执行的演进计划**。

## A.8 一处值得注意的原始设计意图

`references/ecosystem-roadmap.md`（8348 B，中文）是这个仓库的原始设计文档，明确宣称设计理念是「摒弃 RAG」：
> "本计划旨在摒弃复杂的外部 RAG 依赖，将所有物理场和求解器的专业知识、API 语法、代码模板以及报错修复规则，**全部固化为高信息密度的结构化 Markdown 文件**。"

它设想的目录里包含 `scripts/log_monitor.py`（实时监听发散并中断）和 `scripts/post_paraview.py`（自动后处理），**每个 solver skill 各一份**。实际实现：只有 orchestration 一个 skill 有 scripts，post_paraview 类脚本一个也没有。这份 roadmap 也承认参考了 OpenFOAMGPT / FoamPilot，并识别出"Agent 最容易失败的地方是超算排队脚本语法和物理量边界条件正交性"。

---

# 仓库 B：lzwei196/KISS

**规模**：`models/` 下 119+ 包（README 说论文冻结队列 119，2026-08-12 提交说 "127 model KI packages"）；`VERSION` = `5.0.1`；25 个提交；有 `CHANGELOG.md`（12921 B）。

## B.1 节点编排

**结论：分裂成两层——一层是"骨架自动生成的空壳"，另一层是"手写的一次性 Python 驱动脚本"。中间没有通用编排引擎。**

### 层一：KDT 自动生成的假 DAG（空壳，必须点名）

`models/ADCIRC/knowledge_infrastructure.yaml`（2113 B，77 行）声明 7 个 stage：
```yaml
pipeline:
  stages:
  - depends_on: []          # ← 7 个 stage 全部 depends_on: []
    description: ''         # ← 7 个 stage 全部空字符串
    id: s0_config
    knowledge_type: procedural
    milestones:
    - description: Stage Configuration completed successfully
      id: m_s0_config
      verification: Output files exist and pass validation   # ← 7 个 stage 逐字相同
    name: Configuration
    tools: []               # ← 7 个 stage 全部空数组
```
`package.version: auto-generated`，`created: '2026-03-25T04:00:26'`。

**这不是 DAG——所有 `depends_on` 都是空，所以它连拓扑序都没有。** milestone 的 `verification` 字段 7 次逐字重复同一句 "Output files exist and pass validation"，`tools` 全空（而 `models/ADCIRC/tools/` 里明明有 4 个真实脚本，17-20 KB 一个，没有一个被登记进去）。

`models/ADCIRC/workflow/workflow.md`（715 B）是**唯一**的 workflow 文件，它是从上面那个 yaml 机械渲染出来的：
```markdown
# ADCIRC — Workflow
Auto-generated pipeline with 7 stages.
### Stage 0: Configuration (`s0_config`)
- **Description**: TBD
- **Dependencies**: none
```
7 个 stage 的 Description 全是 `TBD`，Dependencies 全是 `none`。

**回答 team-lead 的问题 1：`workflow/` 不是编排层。它是 KI manifest 的 markdown 打印件，零信息。**

### 层二：手写的一次性 Python 驱动（真实、可跑，但不可复用）

真正的编排在 `models/VIC/run_and_score*.py` 这一族 8 个文件里（20-44 KB 各不相同）。读 `models/VIC/run_and_score.py`（461 行，实为 Bengbu verify_1 的副本，文件头自称 "VIC VERIFIER runner -- Bengbu (Huai River gauge 51080), verify_1"）：

- 阶段就是**顺序代码块**加注释分隔：`# ---------------- Step s0: delineate basin ---------`、`Step A: default soil params`、`Step s9: routing parameters`、`Step s8: run VIC`、`Step s10: Lohmann routing`、`Step D: score`。全部包在一个 `try:` 里。
- 阶段间靠 `subprocess.run([sys.executable, f"{KI}/s5_routing/build_routing_param.py"], env=env)` 调用，参数通过**环境变量**传递（`VIC_BASIN_NAME`、`VIC_OUTLET_LON`、`VIC_YEAR_START` 等 15 个）。
- **有真实的断点续跑（resumability）**，且是文件存在性判定，写在 docstring 里：
  ```
  * s0  skipped if outputs/.../bengbu_boundary.shp exists.
  * s9  skipped if <routing_param>/BB_direc.txt exists.
  * s8  skipped if all 210 flux files already exist in <work>/vic_result.
  * s10 skipped if <work>/routing/rout_out/*.day already exists.
  Re-launching therefore continues instead of restarting.
  ```
  这是全仓库最像"编排能力"的东西：**幂等 + 续跑**。但它是每个脚本各写一遍的，不是框架提供的。

### 层三：`dag.yaml` —— 给 agent 读的模型本体论，不是编排定义

`models/ADCIRC/dag.yaml` 534 行，八段的实际起始行：
`identity:2` / `boundary:30` / `inputs:52` / `processes:115` / `states:182` / `outputs:224` / `influence:373` / `safety:451`。

**判定：这是模型本体论（ontology），完全不可执行。** 逐段证据：

- **`processes:` (115-181)** —— 两个子键 `modules`（9 个物理过程，各带 `name/role/brief`）和 `internal_edges`（10 条边，`from/to/kind/brief`）。`kind` 只有 `writes_state` 和 `invokes` 两种。这些边描述的是**方程之间的物理耦合**，不是任务依赖：
  ```yaml
  - from: "GWCE solver"
    to: "Momentum equations (2DDI)"
    kind: writes_state
    brief: "Elevation gradient drives the momentum equations."
  ```
  这条边在编排意义上是个环（GWCE↔Momentum 双向），任何 DAG 执行器都跑不了。

- **`states:` (182-223)** —— `provenance: populated`，9 个变量，每个带 `name/symbol/unit/kind/description`。`kind` 取值 `prognostic` / `accumulator` / `static_parameter`。带落地信息（"ASCII fort.63, netCDF 'zeta'"、"Dry nodes carry sentinel DRY_VALUE=-99999"）。这是给 agent 判断"输出该长什么样"的字典。

- **`influence:` (373-450)** —— **这是别处确实没有的东西，也是全仓库最有价值的设计。** 8 条边，schema：
  ```yaml
  - from: "manning_n_bottom_friction"
    to: "peak_surge_elevation"
    sensitivity_grade: MEDIUM
    basis: literature_qualitative
    lever_type: parameter
    citations: [passeri2012_..., garzon2016_..., akbar2017_...]
  ```
  `lever_type` 三种取值：`parameter` / `boundary_forcing` / `structural`。附带 `citation_index`，每条文献带 DOI 和**诚实的证据强度评注**：
  > "Qualitative ('dominant control') — no quantitative SA index."
  > "Magnitude-of-effect reported, not a normalized sensitivity index."

  它的用途在 VIC 侧被明确使用（见 B.5）：**influence 边是校准参数池的种子**。这是"知识→行动"的唯一真实链路。

- **`safety:` (451-534)** —— 四个子段。`hazards`（16 条，每条 `id/kind/description/severity`，severity 取值 `silent`/`fatal`/`degraded`/`fatal_or_silent`，且**每条都反向引用一个 triplet ID**，如 "(dt_002)"）；`validation_limits`（4 条，其中一条自曝家底："KI validation_status = build_tested only; no real-basin validation case documented"）；`warnings`（3 条，其中一条记录了 KI 内部两个抽取器的矛盾："fort.73/fort.74 are swapped between docs_reader and ki_reader; docs_reader is authoritative"）；`assumptions`（3 条，带 `statement/scope/source/status: adopted`）。

  `hazards` 的 `kind` 分类值得抄：`soil_semantic` / `control_semantic` / `weather_file_semantic` / `parser_semantic` / `coefficient_runtime_silent_fallback` / `numerical_instability`。

**综合判定（回答问题 5）：`dag.yaml` 是给 agent 读的模型本体论，不是可执行编排定义。** 它没有任何执行器会解析它——`preflight_check.py` 不读它，`run_and_score.py` 不读它，`workflow.md` 不是从它生成的（是从那个空壳 yaml 生成的）。唯一被机器消费的是 `influence` 段（人工地）被 `calibration.yaml` 引用为参数池来源。

## B.2 失败恢复

**结论：形态是「fail-closed + 人工事后写成 triplet」。没有自动恢复。**

### `preflight_check.py`（ADCIRC，65 行，全文读完）

极其简单，三个检查函数（`check_file` / `check_dir` / `check_import`），main 只做三件事：
1. `check_dir(".../knowledge_infrastructure/tools", "KI tools directory")`
2. `check_file(".../build/adcirc", "ADCIRC binary", executable=True)` —— **硬编码了一条 `/home/server/knowledge-dissection-toolkit/auto_dissect/_work/ADCIRC/source/repo/build/adcirc` 的绝对路径，只在原作者服务器上成立**
3. 如果 `diagnostics/triplets.yaml` 存在，打印一行 `INFO Diagnostics available: <path>`

输出是人类可读文本 `OK/WARN/FAIL <label>: <path>`，末尾 `Results: N passed, M failed`，`sys.exit(1 if FAIL > 0 else 0)`。

**给 agent 的信息量极低**：不返回 JSON、不返回结构化 code、失败时唯一的"修复提示"是 `check_import` 里的一行 `Fix: pip install {module}`（而这条分支在 ADCIRC 的 main 里根本没被调用）。它还偷偷把 `/mnt/disk1/Hydrocraft_server/python_env/...site-packages` 插进 `sys.path`。

**这就是"README 说有、实现是空壳"的又一处**：README 把 `preflight_check.py` 列为 KI 三层里的 "Staged domain protocols" 支柱之一，实际是 2 KB 的三行检查。

### `diagnostics/triplets.yaml`（ADCIRC，567 行，20 条）—— 主流形态，schema 完整

字段树：
```yaml
- id: dt_001
  stage: s1_mesh_preparation
  failure_domain: unit_conversion
  symptom:
    description: "..."
    error_pattern: "all nodes dry"
    detection_method: value_comparison
  diagnosis:
    root_cause: "Depth sign convention inverted"
    explanation: >
    affected_components: [fort.14, convert_bathymetry_to_fort14]
  remedy:
    action: "Negate all depth values: DP = -elevation"
    tool_to_run: convert_bathymetry_to_fort14     # ← 可为 null
    manual_steps: [...]
    prevention: "validate_outputs() checks for positive ocean depths"
  severity: silent
  cross_references: [dt_002]
```
`remedy.tool_to_run` 是**唯一的机器可执行钩子**，但很多条是 `null`（dt_002 就是 null，只有 manual_steps）。`severity: silent` 是这套东西真正的核心洞察——它专门编码"模型正常退出但结果错误"这一类。

### VIC 的 `diagnostics/triplets.md`（33431 B，31 条）—— 散文版，但内容深度反而更高

标题是 `### dt_vic_023 — Stage script SIGSEGVs at exit *after* writing correct output; pipeline dies with rc=1`，正文三段 **Symptom / Diagnosis / Remedy**，没有 YAML 字段。

**判定（回答问题 7）：yaml 版是"主流形态"（KDT 自动生成的模板产物，119 个包里绝大多数是 yaml），md 版是"人工深挖产物"。但 md 版信息密度和可信度都高得多**——它带最小复现命令、带 root cause 到源码行、带回归防护 grep：

> `python3 -c 'import xarray as xr; xr.open_dataset("grid.nc").close()'` → rc=139 SIGSEGV
> `grep -rn "open_dataset(" --include=*.py s1_grid s2_forcing ... | grep -v "engine="` 必须返回空

dt_vic_023 还给出了一条**反模式警告**，直接针对"agent 自动重试"这种做法：
> "Do **not** 'fix' this by making the driver tolerate a nonzero return code: a real crash and a teardown crash are then indistinguishable, and the next genuine failure will be silently scored."

### 实际的失败处理代码：`die()` + fail-closed，零重试

`run_and_score.py` 里唯一的失败处理是：
```python
def die(msg):
    result["notes"] = msg
    write_result()
    sys.exit(1)
```
每个阶段失败都 `result["tools_failed"].append(<tool>)` 然后 `die(...)`。整个脚本包在 `try/except Exception` 里，异常时写 `"Runner crashed: " + traceback.format_exc()[-800:]` 到 result.json 再 exit 1。

**没有任何自动重试、没有参数回退、没有降级路径。** 唯一的"恢复"是人重新启动脚本，靠 B.1 说的续跑跳过已完成阶段。

## B.3 自我研究

**结论：有，但是人做的，不是 agent 做的；成果落在 markdown 里而不是回到包里。**

`models/VIC/CAPABILITY_INVENTORY.md`（22380 B，425 行）是这方面唯一的实物。

**它是什么（回答问题 4）：一份「模型源码能力 vs KI 已覆盖能力」的差距审计表**，不是运行时能力清单。头部：
> Generated: 2026-04-03 / Source: VIC 5.1.0, 59 C source files in `vic_run/src/`, 3 drivers / Current KI version: 1.1 (2025-02-01) / Usage: 64 VIC result directories in outputs/ — the most-used model in HydroCraft (vs 15 HYPE, ~249 total)

核心是一张 10 类 37 项能力的三列表：`Total Capabilities / In Current KI / Missing from KI` = **37 / 12 / 25**。每一项带 `Status`（DONE in KI / NOT in KI）、`Source`（C 源文件名，如 `runoff.c`, `compute_zwt.c`）、`KI tools`、`KI GAP` 说明。

**与 `knowledge_infrastructure.yaml` 的关系**：CAPABILITY_INVENTORY 明确把后者列为**当时 VIC 缺失的东西**——文末「Gap Analysis」表里 `knowledge_infrastructure.yaml | YES(HYPE/MODFLOW6) | NO(VIC) | MISSING`。也就是说这两个文件不是父子关系，而是 **inventory 是审计者，manifest 是被审计项之一**。inventory 自己写道 `CAPABILITY_INVENTORY.md | YES | NO (now created) | FIXED`。

文末「RECOMMENDATION」给出 Priority 1/2/3 共 14 条整改项，还有一节「What NOT to do」：
> "Do NOT restructure the existing s1-s4 scripts internally — they work and are battle-tested across 64+ basins."

**这是真正的自我研究，但它是一次性的人工产物（2026-04-03 生成，一次），不是循环。** 而且到 2026-08 抓取时，Priority 1 的整改只部分落地：`models/VIC/tools/` 确实建了，但里面 `s1_grid`/`s2_forcing`/`s3_soil`/`s4_veg` **四个都是指向 `../s1_grid` 的 symlink**（`gh api` 返回 `{"type":"symlink","target":"../s1_grid","size":10}`），`tools/calibration/` 下三个条目也全是 symlink（67/83/87 字节）。inventory 点名要修的 stale Mac 路径也**没修**：`models/VIC/tools/check_data.py` 现在仍然写着
```python
WORKSPACE_ROOT = Path("/Volumes/Expansion2t/hydro-model-workspace")
```

## B.4 知识自更新

**结论：全靠人。没有任何"这次跑失败学到的东西自动回写进 KI 包"的机制。证据链完整。**

1. **代码里没有写回路径。** `run_and_score.py` 唯一的写出目标是 `detached/verify_1/result.json`（`write_result()` 在每条退出路径都调用一次）。它**不写 triplets、不写 dag.yaml、不写 SKILL.md**。

2. **本次运行发现的 KI bug 被塞进了 result.json 的一个自由文本 `notes` 字段里**，长达一整段（`run_and_score.py` 尾部）：
   > "KI BUG found at s0: the shipped snap_distance_m=3000 mis-snaps this gauge onto a 146 km2 tributary (the DEM channel is 5.4 km from the published coordinate), silently delineating a 145 km2 'basin'; raising stream_threshold alone does not fix it because the snap radius is the binding constraint. Fixed with snap=6000 m + stream_threshold=1e6 px and guarded by a published-area assertion."

   —— **"Fixed with..." 是人在写脚本时手改的，不是程序做的。这段发现停留在一个 JSON 字符串里，没有变成 triplet ID，也没有进 dag.safety.hazards。**

3. **triplets 里的日期标注确认是人工事后补的。** VIC triplets.md 里出现日期的地方：
   - 行 12：`**Diagnosis** (ROOT CAUSE, identified 2026-07-09): config_paths.create_global_param() substituted paths with the UNANCHORED pattern r'SOIL\s+.*'`
   - 行 201：`built by the KI tool s5_routing/build_routing_param.py (added 2026-07-09)`
   - 行 246：`The 2026-07-09 唐乃亥 detached run died exactly here: state.json recorded returncode: 1 at s6 process_forcing.py, all 251 forcing files were correct, and the orchestrator captured null metrics for a run whose physics were fine.`
   - 行 289：`**Remedy**: FIXED (2026-07-10, Harbin/Songhua run).`
   - 行 366：`Verified 2026-07-10: the 哈尔滨 run burned 13 min of VIC + routing and was...`

   这些是**叙事性的、带具体运行编号和主观判断的散文**（"It was never the template's fault — the generator corrupted its own output on every run"、"Reproduce with: re.sub(...)"）。没有任何生成器能写出这个。**结论：人跑失败 → 人诊断 → 人手写 triplet → 人 commit。**

4. **提交历史印证同一模式**：知识更新是**批量同步整个工作树**，不是增量回写：
   - `2026-08-12 Refresh all 127 model KI packages from the working tree`
   - `2026-04-14 Sync all 123 model KIs from HydroCraft server (post-revalidation)`
   - `2026-04-13 Push all 123 model KIs from HydroCraft server`
   —— 真实工作发生在一台叫 HydroCraft 的服务器上，这个 GitHub 仓库只是**周期性快照倾倒**。

5. **CHANGELOG 是唯一的"学习记录"，而且质量很高**（12921 B，v4.0.0 → v5.0.0 → v5.0.1）。它记录的正是"跑失败 → 读源码 → 修工具 → 加 triplet"的完整循环，但**这个循环的执行者是人**：
   > v5.0.1: "Fixed: SUMMA KI (7 bugs, 6 new triplets, 1 new tool) — Bug fixes from Fortran source code analysis: `set_trial_parameters.py` — vGn_alpha range (0.001,10) → (-1.0,-0.01). SUMMA uses negative matric head convention. Positive values cause NaN in Richards solver (dt_019)"
   > "**Triplets:** 18 → 24 (+6: dt_019 through dt_024)"
   > v5.0.0 新增 **Debugging Protocol (Rule 0)**，加到全部 124 个 SKILL.md：4 步 "(1) check triplets → (2) read official docs → (3) find working examples → (4) fix the tool"，动机写得很直白：
   > "Motivated by mizuRoute/wflow revalidation where 20+ debug scripts were written when answers were in the docs"

   注意最后这条：**它是在治 agent 的病（agent 一遇错就狂写 debug 脚本），治法是往 124 个文件里塞一条散文规则**。这是仓库 B 全部"知识自更新"的真实形态。

6. `2026-04-04 Add 6-level Debug Triage Framework (KDT 5.0)` 这条提交提到的框架，**在仓库根目录三个 doc（README/DEPLOYMENT/AGENT_SERVICE_GUIDE）里 grep 不到 "triage"**，应该只在 `kdt-release.zip` 或未同步的服务器侧。

## B.5 评测与校准

### `run_and_score.py` 家族 —— 是评测，不是迭代闭环（回答问题 2）

8 个文件：`run_and_score.py` + `verify1_{,bengbu,nahanni,nahanni_mswx}` + `verify2_{johnday,nuxia,retest}`。命名对应 README 说的 "3 sites per model × 3 independent agent sessions"（`revalidation_3x3_results.xlsx` 就是这个的记录）。**它们是彼此的手工 fork**——`run_and_score.py` 和 `run_and_score_verify1_bengbu.py` 一个 20 KB 一个 25 KB，同一个 Bengbu 案例两个版本。没有共享 driver。

- **评分指标**：`from ki_tools_common.metrics import all_metrics` → NSE / KGE / PBIAS / r / RMSE；外加 `from validators.standard_calval import compute_calval_metrics` 做 cal/val 分段；外加 `from ki_tools_common.validation import validate_water_balance` 做物理守恒检查（返回 `status` + `residual_pct`）。这三个模块**不在本仓库**，在 `kdt-release.zip/{ki_tools_common,validators}` 里（`metrics.py` 8255 B，`standard_calval.py` 12526 B，`validation.py` 11014 B）。zip 里唯一的测试是 `ki_tools_common/tests/test_units.py`。
- **失败处理**：`die()`，见 B.2。
- **自动重试/参数调整**：**没有。而且是刻意没有。** 文件头 docstring：
  > "The real-case was run UNCALIBRATED (default soil/veg parameters, nothing tuned on either period), so this verifier MUST use the same protocol at Bengbu; a calibrated Bengbu score would manufacture false 'consistency'."

  代码里还有一道硬断言防止有人偷偷调参：
  ```python
  if not (np.allclose(binfilt, 0.30) and np.allclose(Ds, 0.02)
          and np.allclose(Dsmax, 10.0) and np.allclose(Ws, 0.70)):
      die("SOIL params are not VIC defaults -- verifier must run uncalibrated")
  ```
- **结果写到哪**：`detached/verify_1/result.json`，schema 固定：`model_id / this_location / obs_source / status / tools_used[] / tools_failed[] / metrics{nse,kge,pbias,r,period} / water_balance{status,residual_pct} / notes`。
- **是否回写知识**：不。见 B.4。

### `calibration.yaml`（VIC，617 行）—— 参数标定，但**是知识密集型的参数标定**（回答问题 3）

明确是**参数标定**（tuning VIC 的 binfilt/Ds/Dsmax/Ws/depths/albedo/LAI/Rmin），不是知识标定。八段：
`identity:3` / `obs_contract:33` / `run_health:82` / `injection:95` / `targets:98` / `parameters:133` / `constraints:546` / `runner:575` / `strategy:581`。

它是这两个仓库里**设计最扎实的单个文件**，值得逐条学：

- **`obs_contract` (33-81)**：把观测数据的"指纹"写死成断言，防止悄悄换数据集：`station_code: 40100350`、`missing_sentinel: -99`，以及每个 split 的精确整数包络 `n_days: 1826 / q_min: 117.0 / q_max: 2680.0 / q_sum: 1198400.0`。注释说明为什么可以用精确整数："the CNGF Q column is integer m3/s, so n_days / sum / min / max are exact fingerprints of the series."
- **它自己发现并记录了一个上游数据库 bug**（identity 段的 `case_id_note`）：
  > "The dispatch record carries obs_id `bengbu_51080`, which is a DB-wide default written onto every row of this model's case table, NOT this case's gauge... Bengbu 51080 is a Huai-basin gauge on a different river system entirely."
- **`run_health` (82-94)**：四个必须存在的健康指标 `[n_cells, flux_records, routed_days, paired_days]`，注释写明策略："fail-closed: absent/None => no metrics, nonzero exit; never defaulted to a passing value."
- **`parameters` (133-545)**：13 个参数，每个带 `name/description/type/default/range/hard_bounds/transform/scope/zone_key/tie/activation/expected_sensitivity/confidence/cite/address`。`address` 段是**参数到文件字节位置的映射**：
  ```yaml
  address:
    kind: table_cell
    file: "outputs/tangnaihai/vic_temp/soil/SOIL_PARAM_COMPLETE.txt"
    row: "*"
    col: 4
    delimiter: " "
  ```
- **参数池的来源就是 `dag.yaml` 的 `influence` 段**——这是全仓库唯一一处"知识文件驱动行动"的实链路，注释原文：
  > "POOL. Seeded from dag.yaml influence.edges with sensitivity_grade HIGH/MEDIUM and lever_type: parameter. Sepulveda et al. 2022 (DELSA, 5574 VIC cells) names exactly 12 dominant parameters... No literature-supported edge is pruned: the kit's Morris screen confirms or demotes each ON THIS SITE, literature is only the prior."
- **参数池是针对具体误差模式设计的**，不是无脑全调：
  > "ERROR MODE THIS POOL MUST BE ABLE TO CLOSE: the uncalibrated run has PBIAS +16.75% (val +22.0%) — the basin sheds too much water — with r = 0.849 already good. That is a VOLUME bias, not a shape error, so the pool deliberately spans BOTH the runoff-generation levers AND the levers that can remove water without touching the hydrograph shape."
- **有明确的排除理由**（诚实性）：`fcanopy` 被排除，因为 "the KI's veg parameter file is written without an FCAN block... so there is no token in the effective artifact to address. C1/C3 honesty: declaring it would be a dangling address."
- **`constraints` (546-574)**：3 条物理/源码约束，每条注明源码出处，如 `snow_utility.c:253-263 -> albedo = new_snow_albedo * A^(age^B)`。
- **`runner` (575-580)**：`kind: subprocess`，`command: ["/usr/bin/python3", "tools/calib_run.py", "--workdir", "{workdir}", "--out", "{metrics_json}"]`，`timeout: 1800`。`tools/calib_run.py` 在仓库里，47271 B。
- **`strategy` (581-617)**：**这是"闭环"真正被声明的地方**：
  ```yaml
  cost_class: expensive           # ~2.5 min CPU per eval
  default_algorithm: dds
  max_evaluations: 150
  staged: true                    # Morris-screen the 13-param pool, then calibrate few, then escalate
  staged_start: 3
  staged_step: 2
  screen_trajectories: 4
  holdout:
    kind: years
    protocol: blocked_temporal
    fraction: 0.5
    calibration_period: ["2007-01-01", "2011-12-31"]
    holdout_period:     ["2012-01-01", "2016-12-31"]
  ```
  holdout 的 `rationale` 有一整段方法论论证（为什么必须 blocked 而不能 random split：日流量强自相关，随机分割会把同一场洪水的退水段泄漏到两边），带引文 `klemes1986_operational_testing` / `arsenault2018_calibration_data_length`。

  **但优化器本身（DDS + Morris 筛选 + staged escalation）不在这个仓库里。** `calibration.yaml` 只是声明；执行它的 "kit" 在 KDT 侧，`kdt-release.zip` 里也没有（zip 里只有 units/humidity/netcdf/validation/metrics/forcing_sources + 3 个 validator + 模板 + 文档，39 个文件）。仓库里能看到的只有 `tools/calib_run.py`（单次 eval 的执行+打分）和 `tools/calibration/` 下三个**指向仓库外的 symlink**。

  即：**"迭代优化闭环"在 KISS 里是一份规格说明 + 一个单步执行器；驱动循环的那一层没有开源。**

### KDT 的 agent 运行时设想（回答问题 8）

`AGENT_SERVICE_GUIDE.md`（22299 B）描绘的架构：浏览器 → WebSocket → FastAPI 后端 → **每个会话 spawn 一个 CLI agent 子进程** → agent 读 CLAUDE.md/SKILL.md、调 KI 工具、跑模型二进制。

**有没有循环/重试/人工介入？**
- **没有自动循环，没有自动重试。** 全文没有 retry 逻辑，唯一的"控制"是三层提示词注入（Layer 1 主指令文件 ~1000 行 / Layer 2 后端注入的 system prompt ~200 行 / Layer 3 每条消息都注入的 ~10 行 reminder），以及对不同 provider 的差异化处理：
  ```python
  if provider == "claude-code":
      prompt = f"[run_id={run_id}]\n{user_message}"   # CLAUDE.md 自动进 system prompt
  else:
      prompt = f"{SYSTEM_PROMPT}\n{REMINDER}\n{user_message}"
  ```
- **有明确的人工介入门**，写在 Agent Discipline 第 1 条（`CLAUDE_TEMPLATE.md`「Agent Discipline」）：
  > "**PLAN FIRST**: Before executing anything, show a numbered plan with data paths and estimated times. **Wait for user confirmation.**"
- **有一个真实的运行时工程问题解法**：孤儿进程监控。`nohup ... &` 起的模型进程会被 reparent 到 PID 1，`psutil.children()` 找不到。解法是把 conversation ID 写进输出目录名，然后全进程扫描 cmdline 匹配前 8 位。
- **测试是人工测试矩阵 + 7 条 Red Flags**，全是自然语言判据，例如：
  > "Agent reports 'expected values from literature' instead of actual simulation results"
  > "Agent runs VIC Steps 8-10 (Lohmann) when user asked for flood simulation (CaMa)"
  > "Model runs successfully but yields/discharge are off by orders of magnitude (unit trap)"

  **没有一条是自动化的。**
- 最重要的一条护栏，在 guide 和 template 里各出现一次：
  > "**NEVER write custom scripts when a validated tool exists in the KI.** Custom scripts reintroduce the exact bugs these tools were built to prevent."
  > "This rule prevents the #1 agent failure mode: the agent writes a Python script to prepare model input, misses a unit conversion, and the model runs successfully with wrong results."

### README 声称的 vs 仓库里有的

README「Evidence from the paper」给了一堆数字：3000 次试验、14 milestones、KI 组 84% vs 无 KI 组 <40%、835 tools 分七类、2406 个 diagnostic recovery mechanisms（55% 是单位/格式错误）、3478 个 decision points 分 11 类、Spearman ρ=0.75。

**这些实验的代码、试验记录、milestone 定义、判定脚本，仓库里一个都没有。** 仓库里只有 `revalidation_3x3_results.xlsx`（33 KB，对应 25 包 × 3 站 × 3 会话那一组）和 KI 包本身。README 也没有假装有——它明说 "This repository contains the model-level knowledge artifacts."。但要注意：**"14 milestones" 这个 benchmark 的 milestone 定义，跟 `knowledge_infrastructure.yaml` 里那个每包 7 条、verification 全同一句的 `milestones` 字段，不是一回事**，别把后者当成前者。

---

# 横向对比：迭代闭环维度上，各自真正有什么 / 真正没有什么

## SciMate-AI/HPC-Skills

**真正有的**
- 一套写清楚的自愈循环语义（submit→monitor→tail→classify→repair→resubmit）和一条防呆规则（"不要重投未修改的失败作业"）。
- 13 条带稳定 ID、四字段固定 schema 的编排层错误码表（`HPC_*`）。
- 3 个 scheduler 的状态归一化脚本（PENDING/RUNNING/COMPLETED/FAILED），是唯一能被程序调用的东西。
- 一条 OpenFOAM 的、真正生产级的错误决策树（命令 + 数值 + ASCII 树）。
- 明确的分层职责契约（solver skill 管物理，orchestration 管集群）。

**真正没有的**
- 没有任何编排执行器：8 阶段生命周期是散文，没有代码读它。
- 没有版本号、没有 CHANGELOG、没有 tag，skill frontmatter 只有 name/description。
- 没有 CI、没有测试、没有 eval、没有 benchmark、没有 golden case。
- `public-protocol.md` 说的 "run the available skill validator" —— 这个 validator 在仓库里不存在。
- 21/22 个 skill 没有任何可执行代码，只有 markdown。
- 错误恢复质量在 skill 之间落差数量级（OpenFOAM 7.6 KB 决策树 vs SU2 1.1 KB 空话）。
- 知识只来自上游官方文档和人工扩充，与实际运行结果之间没有任何反馈通路。
- `agents/openai.yaml` 是 4 行 UI 元数据，不承载 agent 语义。

## lzwei196/KISS

**真正有的**
- `dag.yaml` 的 `influence` 段：把"哪个参数影响哪个输出、影响多强、证据来自哪篇文献、证据强度是定性还是定量"编码成机器可读的边，并附诚实的证据降级说明。这是两个仓库里唯一的独创物。
- `dag.yaml` 的 `safety.hazards`：16 条静默失败清单，每条带 severity（`silent` 是核心类别）并反向链到 triplet ID。
- `calibration.yaml`：obs 指纹断言 + run_health fail-closed 门 + 参数到文件字节位置的 `address` + 面向具体误差模式设计的参数池 + blocked temporal holdout 及其方法论论证。规格层面是工业级的。
- 手写 driver 里真实可用的**幂等续跑**（按产物文件存在性跳过阶段）。
- 高质量的人工 triplet（VIC md 版）：带最小复现命令、根因到源码行、回归防护 grep、以及"不要这样修"的反模式警告。
- 一份认真的能力差距审计（CAPABILITY_INVENTORY，37 项能力 12 覆盖 25 缺失）。
- 一份记录了真实"失败→读源码→修工具→加 triplet"循环的 CHANGELOG。
- 多 provider agent 部署的工程经验（三层提示词注入、孤儿进程按 conversation ID 扫描）。

**真正没有的**
- 没有通用编排引擎。`workflow/workflow.md` 是空壳（7 stage 全 `TBD` + `Dependencies: none`），`knowledge_infrastructure.yaml` 的 `depends_on` 全为空、`tools` 全为空、`verification` 7 次逐字重复。**它连拓扑序都没有，不是 DAG。**
- `dag.yaml` 不可执行，没有任何程序解析它；`processes.internal_edges` 是物理耦合环，DAG 执行器跑不了。
- 没有自动重试、没有参数回退、没有降级路径。唯一的失败动作是 `die()` + 写 result.json + exit 1（而且这是刻意的设计选择，triplets 里有明文反对宽容 returncode）。
- 没有知识回写：本次运行发现的 KI bug 停在 result.json 的自由文本 `notes` 字段里，没有变成 triplet、没有进 safety.hazards。triplets 里的 "identified 2026-07-09" 是人工事后叙事补写，不是自动标注。
- 知识更新方式是"周期性把 HydroCraft 服务器的工作树整包倒进 git"（`Refresh all 127 model KI packages from the working tree`），不是增量回写。
- 驱动 150 次 DDS 迭代的优化器**不在开源范围内**；仓库里只有单次 eval 的 `calib_run.py`，`tools/calibration/` 下三个条目全是指向仓库外的 symlink。
- `preflight_check.py` 是 2 KB 三行检查，硬编码原作者服务器绝对路径，输出纯文本、不返回结构化信息给 agent —— 与 README 把它列为三大知识层支柱之一严重不符。
- CAPABILITY_INVENTORY 提的 Priority 1 整改到 2026-08 只部分落地：`tools/s{1..4}_*` 是 symlink，被点名的 stale Mac 路径 `/Volumes/Expansion2t/` 至今还在 `tools/check_data.py` 里。
- README 的 3000-trial / 14-milestone benchmark，判定代码与试验记录均不在仓库。
- 各 `run_and_score_*.py` 是彼此手工 fork（8 个文件、20-44 KB），没有共享 driver，同一个 Bengbu 案例存在两个不同版本。

## 一句话总结这两者的关系

**HPC-Skills 把"闭环"写成了给 agent 读的散文规则（有语义、无执行）；KISS 把"闭环"写成了给机器读的规格说明（有 schema、执行器不开源），并且把真正跑通的那部分固化成了一堆一次性手写脚本。两者都没有"运行结果自动回流进知识包"这一环——KISS 至少把这一环的人工版本记录得很完整（CHANGELOG + 带日期的 triplet），HPC-Skills 连这个记录都没有。**
