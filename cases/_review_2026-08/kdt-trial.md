# KDT (Knowledge Dissection Toolkit) 试用记录

> 内部研究笔记。上游 `lzwei196/KDT` 为**私有仓库**，含未发表论文材料。
> 本文只做笔记与短引用，**不得公开发布、不得外传**，也未把上游代码整段拷入本仓库。
>
> 许可证补充事实（与任务简报中"没有 license"略有出入，值得记录）：
> 仓库**根目录确实没有 LICENSE**，但子目录 `kdt-release/` 下**有一份 MIT LICENSE**
> （`Copyright (c) 2026 Jianyun Zhang Research Group, Hohai University`）。
> 也就是说 `kdt-release/`（README / PREFLIGHT / VALIDATION_PROTOCOL / templates/ /
> validators/ / examples/）在其作者意图上是可自由使用的发行版；
> 而 `auto_dissect_multi_agent/`、`auto_dissect/` 等主干代码**不在** MIT 覆盖范围内。
> 结论：真要落地借鉴，**只从 `kdt-release/` 取物**；主干代码只读只学。

试用时间：2026-08-25 ｜ 执行：kdt-trial agent ｜ 本地工作副本：`/tmp/claude-1000/kdt/`（不入库）

---

## 阶段一：规格与裁判

### 0. 术语与全景

KDT 的核心命题只有一句：

> **一个规格**（`build_dissection_prompt()`）说 KI 该长什么样，
> **一个裁判**（`verify_ki_structure.py::verify()`）说这个 KI 合不合格，
> 其余一切（多 agent 编排、self-improve、批处理）都只是"生产能通过裁判的文件"的不同方式。

"KI" = Knowledge Infrastructure，一个模型（如 VIC、SWAT、GLM）的**可执行知识包**：
一个目录，里面装 SKILL.md + tools/ + docs/ + diagnostics/ + dag.yaml + 若干投影产物。
它的读者是 **agent**，不是人——SKILL.md 是"前门"，agent 顺着它找到工具、诊断、判据。

### 1. 规格：`auto_dissect_multi_agent/cli_agent.py::build_dissection_prompt()`

位置：`cli_agent.py:377`（函数体到 ~1093 行，即**一个约 700 行的巨型 f-string prompt**）。
它接收 `model_name / work_dir / output_dir`，读取 `work_dir/probe_report.json`、
`io_graph.json`、`unit_table.yaml` 等探针产物，把领域数据登记表拼进去，产出交给
Claude CLI agent 的一次性长指令。

**注意一处与简报不符的事实**：这个函数里只有 **FILE 1–10**，没有 "FILE 11"。
"FILE 11" 这个编号只出现在**裁判**里（`verify_ki_structure.py` 注释把
`docs/validation_convention.yaml` 叫 FILE 11），而规格里它是 FILE 10。
规格自己也承认编号在漂移——FILE 6 的失败信息写的是
"format_spec.yaml missing (FILE 6 in the current 7-file spec)"。
**编号是历史层积的，不是一套整齐的编号系统。**这本身就是个可借鉴的教训：
编号别写进错误信息里。

prompt 的结构是 5 个 PHASE：

| Phase | 内容 |
|---|---|
| PREFLIGHT | 四层架构说明（L0 数据文档 / L1 共享库 `ki_tools_common` / L2 本 KI / L3 验证）+ 9 条"数据意识规则" |
| PHASE 1 | 只读源码与文档，**不许写文件** |
| PHASE 1b | **能力盘点**：列出模型的**每一个**功能，每个功能都必须有工具 + 文档 + ≥1 条诊断三元组 |
| PHASE 1c | **输入准备计划**（`docs/input_preparation.md`），含"共享库返回值 schema 必须实测"与"Fortran 定宽格式必须 `cat -A` 逐列量"两条硬规则 |
| PHASE 2 | 写 FILE 1–10 |
| PHASE 3 | **必须真编译、真跑模型二进制**，禁止用 Python 解析式替身 |
| PHASE 4 | （由 `_build_phase4_instructions(domain,…)` 按领域注入）验证 |
| FINAL | 跑裁判，非零退出就不许结束 |

#### FILE 1–10 逐条

**FILE 1 — `SKILL.md`**（>200 行）
- 必须以 **MANDATORY EXECUTION POLICY** 护栏块开头（原文给了完整模板文本），
  核心是禁止 agent 用"简化 Python 公式/回归方程/手搓近似"替代真实模型，
  并规定 DEBUGGING PROTOCOL 四步序：查三元组 → 读官方文档 → 找可用样例 → 改工具，
  外加一句 "Resist the urge to write diagnostic/debug Python scripts."
- 护栏之后是 **KI MAP**（`<!-- KI-MAP:BEGIN -->…END`）——**不许手写**，
  由 `generate_skill_map.py --ki_dir` 投影出"哪个组件、什么时候读、为什么读"的表格。
  原话："a component the map does not name is invisible at runtime."
- 正文走 12 节模板（`kdt-release/templates/SKILL_TEMPLATE.md`），其中
  **§6 输出描述**和 **§11 性能指标**是**转述来的，不是写出来的**：
  §6 复述 `dag.yaml` 里 rank-1 变量的原文描述；
  §11 复述 `docs/validation_convention.yaml` 的通过带**连同引文**。
  原话："a metric value without the field's bar is a number, not a verdict."

**FILE 2 — `tools/`**：每个 Phase-1c 类别一个 Python 脚本，外加执行包装器与输出解析器。
最少 3 个（ingestion + execution + parsing），典型 5–10 个。每个工具走 validate→process→validate。
- 对 Fortran/C 模型有**执行包装器架构**硬规定：拷贝整个样例工作区到临时目录 → 换入用户数据
  → 只用字符串替换改控制文件里的**具体值** → 在该工作区里跑 → 收集输出。
  "NEVER generate Fortran fixed-format files from Python dicts."
- 强制复用共享库 `ki_tools_common`（forcing/soil/landcover/metrics/水量平衡/跨平台二进制）。

**FILE 3 — `docs/`**：≥5 篇 markdown，每个流水线阶段一篇，每篇含
Purpose / Inputs / Outputs / Procedure / Verification / Traps / Example。

**FILE 4 — `diagnostics/triplets.yaml`**：≥15 条 symptom→diagnosis→remedy。
- 必须是**顶层 YAML 列表**（以 `- id: dt_001` 开头），**不许**包在 `triplets:` 键下。
  理由写在规格里：包成 mapping 的那些 KI，被 self-improve 覆盖层当成空语料**直接覆写**，
  2026-08 一次性毁掉 13 个 KI 的约 171 条三元组。
- 必须含本模型的单位换算陷阱；id 唯一；含冒号的值必须加引号（有 4 个 KI 因此 YAML 解析失败）。

**FILE 5 — `knowledge_infrastructure.yaml`**：**投影产物**，由
`generate_ki_manifest.py` 从 dag + 目录内容 + models DB 生成。
理由："Counts written by hand go stale silently" —— 有个 KI 的 manifest 写着 20 条三元组，
实际 23 条，全队审计才发现。必须含 `validation.tier`。

**FILE 6 — `docs/format_spec.yaml`**：**dag 的投影**，机器可读 I/O 契约。
裁判会逐条比对：dag 里每个可观测输出都必须在这里出现，**名字与单位完全一致**。
`known_issues` 必须与 triplets **一一对应**。

**FILE 7 — `preflight_check.py`**：**必须存在，且被裁判真正执行**。
检查二进制存在/可执行/能启动、必需 import、必需数据文件。
最后一行必须打印 `PREFLIGHT_REPORT=` + JSON（每项 kind/subject/critical/status/fix），
至少一项 critical。exit 0 = ready，非零 = 有阻塞但仍算"工作正常的 preflight"；
崩溃/超时/静默/零检查 = 不合格。原话："the gate runs this script and rejects theatre."

**FILE 8 — `dag.yaml`**：**必需**，由 `python -m ki_dag_generator --model X` 生成
（5 readers → synthesis → 7 verifiers），锁定 7 块模板：
identity / boundary / inputs / outputs / states / influence / safety。
- 每个 output 必须有 `observability.comparable_obs_shapes` + 决定性指标；
- 每个可观测 output 必须有 `validation_rank`（1 = 头条）；
- **每个变量描述必须点名介质（medium）**："sea water potential temperature"，
  不许光写 "temperature"——因为量纲解析器读这串字选比对哪种观测，
  一个没有介质的 "temperature" 曾让**湖泊模型被拿去和土壤探头比分**。

**FILE 9 — `docs/gathered_papers.json`**：**必需**，一个 JSON 列表，每篇论文
`{doi, status, title, text_path, serves[], role}`。全队平均每个 KI 约 16 篇。
- `text_path` 必须是 `paper_fetch.py` 实际写出的路径，加入索引前要 `test -f` 证明文件在；
- 拿不到全文的（paywalled / fetch_failed）进 `paywalled_targets.json`，
  **绝不允许**编造 DOI 或编造路径。原话："A paper you could not read is recorded, not dropped and not invented."

**FILE 10 — `docs/validation_convention.yaml`**（裁判里叫 FILE 11）：
dag 说**哪些比对是合法的**，这个文件说**什么才算通过**。
按 (comparing_variable, obs_shape) 给出头条指标、`direction`
（maximize / minimize / zero_centered）、数值通过带、**以及每条带的引文**。
两条规则：
1. 每条带都是**裸数字 + direction**，于是 NSE/KGE/RMSE/PBIAS/CSI/nRMSE 全部走同一条判定规则，
   不需要 per-metric 表；
2. **没有引文支撑的带必须写 `null`，不许猜**。
   原话："An uncited number is worse than no number."

### 2. 裁判：`verify_ki_structure.py::verify(ki_dir, kind=None)`

742 行，纯 Python + PyYAML。`python3 verify_ki_structure.py <ki_dir> [--json]`，
**exit 0 = PASS，1 = FAIL**，每条失败都点名文件和具体缺陷。

文件头自己写了存在理由，值得整段引用其要旨：

> "`cli_agent.py` asks the dissecting agent for SIX files, but its FINAL CHECKLIST only looked at
> four, printed counts without thresholds, and could not fail — `ls tools/*.py | wc -l` happily
> prints `0`. …… **The rule this encodes: a stage that cannot fail is not a check.**"

#### 2a. kind 分级（`_detect_kind`）

先判断这个 KI 是 `process_model` / `python_lib` / `data_ki` / `coupler`——
查 `hydrocraft.db` 的分类服务。**查不到就回落到 `process_model`（最严格的一档）**，
注释写得很清楚：这样"查询失败永远不会悄悄放松门槛"。这是个好模式。

只有 `process_model` 才被要求 dag / format_spec / manifest / papers / validation_convention；
库和数据集不要求（"`h5py` has no discharge to compare against a gauge"）。

#### 2b. 逐条检查清单

**A. SKILL.md（FILE 1）**
1. `SKILL.md` 必须存在且**就叫这个名**（找到 `SKILL_xxx.md` 也算失败，因为读者按名字找）；
2. 前 8000 字符内必须含 `MANDATORY EXECUTION POLICY`；
3. 必须含 `<!-- KI-MAP:BEGIN`（process_model 为 FAIL，其余为 warn）；
4. **正文标题**必须出现三节（正则匹配 `#` 开头行）：
   `output description|outputs`、`validated results|validation status|performance metrics`、
   `unit conversion|unit table|sign convention`；
5. **★跨文件一致性 1**：正文必须**点名 dag 里 `validation_rank == 1` 的变量名**。
   用**词边界正则**匹配（注释记录了一个真实 bug：原来用子串匹配，
   HBV 的变量名 `Q` 能匹配到任意单词里的 "q"，这条检查**永远不会失败**——
   靠一个"故意删掉变量名、期待失败"的 fixture 才发现）；
6. **★跨文件一致性 2**：正文里所有 `NSE >= 0.x` / `KGE > 0.x` 形态的**数值门槛**，
   必须在 `validation_convention.yaml` 的 bands 里**真实存在**（四舍五入到 4 位比对）。
   正文说了、convention 没有 = "stale or invented bar" = FAIL；
7. **★跨文件一致性 3**：正文里紧挨着 band 语境（"very good"/"good"/"satisfactory"/
   "band"/"bar"/"threshold" 前后 200 字符内）出现的**引文键**（形如 `` `smith2019a` ``），
   必须在 convention 的 `cites` 里存在。
   注释原话："a fabricated citation key next to a real number reads as authority."

**B. tools/（FILE 2）**：递归 `rglob("*.py")`（允许一层嵌套），排除 `__pycache__`，`>= 1`。

**C. docs/（FILE 3）**：不是简单数数。
1. 从 SKILL.md 正则抠出所有 `(docs/)?sN_*.md` 引用，**每个被引用的阶段文档必须存在**
   （断链 = FAIL，"the pipeline walk points at nothing"）；
2. 阶段文档数 `>= 3`（MIN_DOCS，注释强调这是**地板不是目标**）；
3. 另一种合法布局：`sN_<stage>/` **阶段目录**，只要 SKILL.md 里点了名就算覆盖
   （注释说只数 `docs/sN_*.md` 曾把 VIC——全队最经检验的 KI——判失败）；
4. `docs/gathered_papers.json` 单独作为一个维度统计。

**D. diagnostics/triplets.yaml（FILE 4）**
1. 存在。若不存在但 `diagnostics/triplets.*` 有别的后缀 → 专门报
   "这份语料存在但**没有任何读者看得见**，去转换、别重写"（VIC 的 `.md` 语料就这样被当成 0 条）；
2. **必须 YAML 可解析**，失败时直接提示"通常是值里有没引号的 `:`"；
3. **必须是顶层 list**；是 `{triplets: [...]}` mapping → FAIL，
   并明说"没有迁移脚本，手工转"（"audit 2026-08-19: the named one never did"）；
4. `>= 15` 条；
5. 每条要有 symptom/diagnosis/remedy——但**接受同义词**（`signal`/`error`、
   `root_cause`/`cause`、`fix`），同义词记 **warn（该改名）**，真缺字段才记 **FAIL**。
   注释说得很好：把同义词报成"缺失"会派人去重写**已经存在的内容**；
6. id 不能空、不能重复。

**E. FILE 5 / 6 / 7 存在性**：manifest、`preflight_check.py`、`docs/format_spec.yaml`。
`preflight_check.py` 还做**静态源码检查**——源码里必须出现 `PREFLIGHT_REPORT=` 字样。
理由：执行检查只在输出里找那行且只 warn，"所以一次改动可以删掉机器可读契约而零失败"。

**F. dag.yaml**
1. process_model 必须有，能解析；
2. 有 outputs 但**没有任何一个带 `observability.comparable_obs_shapes`** → FAIL；
3. **介质规则**：每个可观测 output 的 `var + description` 拼起来必须命中 38 个介质词之一
   （water/lake/river/ocean/soil/air/ice/snow/canopy/crop/groundwater/sediment/…）。
   这是硬编码词表，**强领域绑定**。

**G. gathered_papers.json**：process_model 与 data_ki 必需，其余 warn。

**H. ★FILE 5/6 内容等价性检查**——本次调研里最有借鉴价值的一段。
它 `import ki_projection_common`（**外部路径** `/mnt/disk1/.../ki_tools_common/`），
用**和生成器同一套共享函数**（`entry_name` / `tool_files` / `read_triplet_entries` /
`observability`）来做比对，注释解释了为什么重写：早期版本"检查 token 而不是等价性，
并且在名字和计数上与生成器意见不一致"。检查项：
- `manifest.summary.total_tools` == 共享计数器数出来的工具数（不等 = 陈旧，FAIL）；
- `manifest.summary.total_diagnostic_triplets` == triplets 实际条数；
- `manifest.outputs.observable` **集合等于** dag 的可观测输出集合（报 missing/extra）；
- `manifest.package.name` == `dag.identity.model_id`；
- `format_spec.outputs.*` 覆盖 dag 的**全部** outputs（可观测的、次要的都要）；
- `format_spec` 每个输出的 `unit` 与 dag **逐字一致**；
- `format_spec.known_issues` **条数等于** triplets 条数（注释特意写 "must mirror, no [:30] sampling"）；
- `known_issues` 不许含 repr 化的字符串（`"{'...`）。

外层包了 `try/except`，但 **except 分支是 `fails.append(...)`**：
"a check that cannot run is not a check that passed"。
（这也意味着**离线跑必然多一条 FAIL**——见阶段二。）

**I. FILE 7 执行检查**：真的 `subprocess.run([sys.executable, preflight_check.py], cwd=ki, timeout=120)`。
- 输出里有 `[MODEL_NAME]` 等未填模板占位符 → FAIL；
- 找不到 `PREFLIGHT_REPORT=` 行 → 走 legacy 分支（有明确 PASS/FAIL 措辞就 warn，否则 FAIL）；
- 找到了：**没有 critical 检查 → FAIL**（"checking nothing"）；
  有 `status == fail` 却没给 `fix` → FAIL；
- 退出码非零 = `model_unhealthy`（warn，排队修，**不判 KI 失败**）；
- 超时/崩溃 → FAIL。
- 注释点名了它防的攻击："codex's 2-line `print PASS; exit 0` exploit passes anything weaker."
- 额外 warn：preflight 自报的可执行文件路径与 models DB 的 `binary_path` 不一致 → 疑似漂移。

**J. validation_convention.yaml**
- 有 gathered_papers 却没有它 → FAIL；没有 papers → warn（"先修 FILE 9"）；
- `validation:` 块为空 → FAIL；
- **★跨文件一致性 4**：每个块必须以 `dag_variable` 为键，且**该键必须是 dag 里真实的 output**
  （不是 → "ghost" FAIL，"the dag is the source of truth; fix the block or the dag,
  never let them drift"）；
- 退休词汇（`canonical_quantity` / `comparing_variable` / `variable_model` / `quantity_rank`）
  出现即 FAIL。注释记了一条极重要的经验：
  **旧版"两种键都接受"的读法把 240 个未迁移的块藏了好几周——
  "an accept-both checker is an unfailable check"，所以回退路径被删掉了**；
- 任何带数字 band 却没有 `cites` 的指标 → FAIL。

#### 2c. 这套裁判的设计原则（可直接抄）

从注释里提炼出 6 条，全部是有事故背书的：

1. **不能失败的阶段不是检查。** 数数不设阈值 = 假检查。
2. **检查跑不起来 = 失败，不是通过。** 所有 except 分支 append 到 fails。
3. **"两种都接受"的读法是不可失败的检查。** 迁移期过后必须删掉回退分支。
4. **先做回填运动，再把 warn 翻成 fail。** 反复出现的模式：
   "the fleet backfill ran first (444 written, 0 refused), so this flip broke nobody"。
   **绝不制造几百个瞬间失败**（"never manufacture hundreds of instant failures ahead of
   the campaign that satisfies them"）。
5. **区分"真缺"与"叫法不同"。** 同义词 → warn 改名；真没有 → fail。
   报错错了会派人去重写已经存在的东西。
6. **查询失败要回落到最严格的一档**，不能悄悄放松。
7. （附加）**检查器与生成器必须共用同一套读取函数**，否则两边对"名字"和"计数"的理解会分叉。


### 3. 判据形式化：`VALIDATION_CONVENTION_SCHEMA.md` + `VALIDATION_PROTOCOL.md`

#### 3a. `validation_convention.yaml` 的 schema

**唯一让它跨领域通用的设计：`direction`。**
指标名在各领域千差万别（NSE / KGE / RMSE / PBIAS / CSI / nRMSE / d-index / POD / FAR / IoU / bias / r…），
"好"的方向也不一样。KDT 不做 per-metric 硬编码表，而是**每个指标自带一个 direction，
每条带都是裸数字**，于是判定只有三条规则：

| direction | 含义 | 判定（v=值, b=带） | 例 |
|---|---|---|---|
| `maximize` | 越大越好 | `v >= b` | NSE, KGE, R, R², CSI, POD, IoU |
| `minimize` | 越小越好 | `v <= b` | RMSE, MAE, MAPE, nRMSE, FAR |
| `zero_centered` | 越接近 0 越好 | `abs(v) <= b` | PBIAS, bias (MBE) |

band 为 `null` = **没有任何被引用的数值门槛存在** → 门控**不能**自动判定，
也**不许放松**，只能 defer / 按 `confidence` 标记。

其他关键字段：
- `references:` 去重引文表，下面用短 key 引；
- `headline_metrics[]`：**全部**达标才算 validated；每个有 `bands`（very_good/good/satisfactory）、
  `pass_band`（默认 satisfactory）、`cites`（**非 null band 必填，这是"诚实门"**）；
- `secondary_metrics[]`：**永不参与** validated 判定；`status: structurally_limited` 的
  必须给 `ceiling_reason`（有文档支撑的物理/数据上限原因）；
- `evidence_strength: strong|moderate|weak`、`confidence: 0..1`
  （**未引用/推断出来的门槛，confidence 必须 ≤ 0.4**）；
- `deferred_paywalled[]`：能补上缺口但拿不到全文的论文，**记录而非静默丢弃**。

三个消费者都只按 `direction` 读：**gate**（判 validated；
`structurally_limited` 的指标失败 → 判 `acquire_data`/数据天花板，**绝不判 fix_ki**；
null band / confidence ≤ 0.4 只能"提供上下文"、**永不放松**已通过的头条要求）、
**calibration**（headline_metrics 即目标函数集，direction 定 min/max，holdout 用同一套 pass_band）、
**diagnose agent**（当本地文档读，引用具体块）。

> ⚠ **发现一处规格 / 裁判漂移（很讽刺）**：
> `VALIDATION_CONVENTION_SCHEMA.md` 里 validation 块的键仍写作 `canonical_quantity` + `obs_shape`，
> 而 `verify_ki_structure.py` 已经把 `canonical_quantity` / `comparing_variable` /
> `variable_model` / `quantity_rank` 全部列为**退休词汇，出现即 FAIL**，只认 `dag_variable`
> （2026-08-15 obs-map 重接）。**照着 schema 文档写出来的文件会被裁判直接判死。**
> 这正好印证了他们自己的命题：**没有跨文件一致性检查的文档，一定会和代码漂移**——
> 而这套裁判恰恰只检查 KI 包内部的一致性，**不检查工具链自己的文档与自己的代码是否一致**。

#### 3b. `VALIDATION_PROTOCOL.md` — 三步验证法（**对 HSTAR 极高可移植性**）

**Step 1 开发者数据测试**：用模型自带的样例数据、**原样不改**跑通，与作者给的期望结果比对。
证明的是"二进制编译正确、运行环境有效"；**不能**证明工具链能准备出正确输入。

**Step 2 渐进式数据替换**（本文件最有价值的部分）：
把开发者数据**一次只换一个组件**成本方数据，每换一个就回归比对。
理由写得很直白："如果你一次全换掉然后失败了，你根本不知道是哪个替换造成的。"

替换顺序按"跨模型标准化程度"从易到难固定：
气象强迫 → 土壤 → 土地覆盖 → 地形 → 河网 → 初始条件 → 边界条件 → 率定参数。

每步的判定规则：
- 与**上一次成功运行**比，未率定情形下 **20% 以内视为替换有效**；
- 差异显著 = 该组件的工具**有 bug** → 查单位换算 / 列映射 / 格式 → 修 → **记成诊断三元组** → 重跑；
- **硬规则：第 i 步没跑出合理结果，不许进第 i+1 步。**
- 复杂模型必须严格一次一个；简单模型可以 2–3 个一起换。
- 全程维护一张"数据替换跟踪表"（组件 / 来源 / 状态 / 备注）。

**Step 3 全本方数据跑标准流域**（蚌埠）。

**验证状态标签**（写进 SKILL.md 和 manifest）：
`binary_only` → `partial_replacement` → `full_replacement` → `production_validated`。

**反模式清单**（7 条，每条都在骂一种自欺）：
1. "样例数据能跑就发布" —— 只证明了二进制，没证明知识基础设施；
2. "我一次全换了而且能跑" —— 你走运了；失败时你会两眼一抹黑；
3. "结果不一样但模型能跑" —— **不一样多少？10% 是率定，10× 是单位错，1000× 是列映射 bug**；
4. "以后再率定" —— **率定修的是参数，不是数据准备 bug**；强迫单位错了，率定会用错误参数去补偿，
   率定期"能用"、换个时段就崩；
5. "这模型没有蚌埠算例" —— 那就**建一个**，这正是知识基础设施存在的意义；
6. "二进制编不出来，我写个 Python 替身" —— **不行**（同 FILE 1 护栏）；
7. "我跑集总的省时间" —— 为分布式设计的模型必须分布式跑。

另有**强制的率定/验证期切分**（cal/val split）与 `stage_log.json` 记录要求。

### 4. self-improve 管线：`SELF_IMPROVE_HANDOFF.md` + `HOW_TO_USE_SELF_IMPROVE_KI.md`

一次 `python3 orchestrator.py --model X [--forced-obs <id>]` 跑完这条流水线：

```
BUILD（KI 已存在则复用）
  → REAL-CASE TEST                 # agent 在选定观测上真跑模型；重型运行 detached 无时限
  → RUN-VALIDITY CRITIC            # 判「这次运行」对不对，而不是判指标好不好
       model_ok / model_limitation → 接受，指标是真实判决
       workflow_incomplete         → 指标只是暂定 → 进诊断修复环
  → [若 incomplete 或差] DIAGNOSE → FIX → REVIEW → RETEST（最多 N 次）
  → VERIFY（额外地点）→ REVIEW → PROMOTE（auto / STAGED）→ COMPLETE
```

#### 4a. 核心原则：判决权不在指标手里

> "**the run-validity critic, not the raw metric, decides whether a result is a real verdict.**"

- 区域聚合观测（如 FAOSTAT 国家产量）上的负 NSE **不是失败**——
  `dag_driven_gate.py` 按 `(variable, obs_shape)` 查 dag 里允许的 `metric_families`，
  对 `regional_aggregate_time_series` 直接 **REJECT NSE**，改用 trend + PBIAS。
  "在那里报 NSE 才是 bug。"
- 反过来：一次数字好看、但用了稀疏代理数据而不是 dag 规定的跑法的运行，**判 incomplete**。

指标族映射：`temporal_pattern_match ← NSE/KGE/R`（仅时间序列）、
`magnitude_accuracy ← PBIAS/nRMSE/%-within/RMSE/MAE`、`trend_match`、
`spatial_pattern_match`、`timing_accuracy`、`ranking_quality`、`distributional`。
门控输出 `PASS / REJECT_WRONG_METRIC / REJECT_MISSING_DETRENDING / WARN / N/A`。

#### 4b. 破坏性写入保护与回滚（简报重点问的）

一共五道，全部是"写入 canonical 之前"的关卡：

1. **快照 + 独立评审 + 回滚。** 所有工具代码改动（**包括 real-case 阶段 agent 为了让模型跑起来
   顺手改的 tools/**）都要过 `tool_reviewer.py` 的**独立 codex 评审**。
   REJECT / REQUEST_CHANGES → **回滚到测试前快照** + 跳过重测 + 标 STAGED（**永不晋升**）。
   开关 `KDT_REVIEW_REALCASE_EDITS`，**默认开**。原话：
   "canonical never holds unreviewed code."
2. **暂存区隔离。** 未晋升的候选一律落在 `<KI>/.kdt_candidates/<MODEL>_retry<N>/`，
   canonical KI 目录不动。**STAGED ≠ promoted。**
3. **分级晋升策略**（`promotion_policy.py`，纯函数无副作用，执行由 `auto_promote.py` 做）：
   - **KI-local 且可逆**的 tier 才有资格自动晋升：`tier3_triplet_addition`、
     `tier2_format_spec_proposal`、`tier2_ki_override_patch`、`tier4_decision_log_entry`、
     `tier4_tried_and_failed_entry`；
   - **跨模型 / 定义"什么算有效"**的 tier **永远走人工**：`tier1_dag_yaml`、
     `tier2_shared_spec_proposal`、`tier2_interface_contracts_update`；
   - 提案若声称"这次验证本身无效"（`asserts_invalid`，一个有后果的认识论主张）→ **永远人工**；
   - `regressed`（任何此前 PASS 的算例掉下去了）→ 不许自动晋升；
   - **改动类型分类学**（比 tier 更准的判别器）：`knowledge_doc` / `measurement_corrected` /
     `tool_fix` / `capability_tuned` / `contract_change`。
     **只有 `capability_tuned`（调参/率定）需要跨地点泛化验证**才能晋升——
     一条"LST vs UTC 时钟"的知识型三元组，从**一个**观测就能确认为正确，
     而一个调过的参数不跨地点验证就是对单流域过拟合；
   - **bundle 汇总保守**：一个 bundle 里**每一条**都是 AUTO 才整体 AUTO，
     只要有一条要人工，整包走人工——"so a tier1 edit can't ride in on a tier3 triplet's coattails"。
4. **并发保护。** 同一模型**绝不允许**两个 orchestrator 同时跑（共享 KI 目录和快照，
   "WILL corrupt each other"）。全局也是**一次只跑一个 campaign**
   （2026-06-23 两个 session 并跑，互相覆写 KI 状态并把月度预算烧穿）。
5. **优雅停机。** 停止时先杀 python orchestrator，然后**等它的 `claude -p` 子进程自己退出**
   （"drain children"）——半路杀掉正在写文件的 claude CLI 会**损坏 `~/.claude.json`**。

#### 4c. 另外两个值得抄的机制

- **环境中断 ≠ 模型失败。** `_is_env_abort()` + `run_claude_resilient()`（3 次重试、180s 退避）。
  被月度额度 / session 上限 / "Stream idle timeout" / socket 断 / overloaded 打死的 agent，
  过去被记成 `nse: None` → 校验器判 `insufficient_data` → **像模型失败一样阻断晋升**。
  现在重试，仍然耗尽则标 `env_aborted`，并返回一个**独立的新状态
  `incomplete_environmental`**。"a billing/rate-limit gap is no longer mistaken for a model verdict."
- **确定性的全有全无指标。** 强制走 `all_metrics(obs, sim)` 一次调用出 nse/r/kge/pbias；
  只有"无时间重叠"才允许 null 且**必须给 `metrics_null_reason`**；
  NaN（零方差 / 少于 2 点）必须对齐时段后重算，**不许静默变 null**。
  修掉了长期存在的"有 r 但 NSE 为 null"不一致。
- **fix_class 路由**：`requires_calibration` / `requires_human_engineering` / `requires_data`
  三类明确**判定为超出 self-improve 范围**，转成提案、终止循环——**不硬修**。
- **codex 评审不设硬超时**（`KDT_CODEX_TIMEOUT_S` 默认不设）：
  硬超时会在 codex 推理中途杀掉它 → 输出被截断 → **被读成 REJECT**。
  改用**停滞检测**（`KDT_CODEX_STALL_S=900`，stdout+stderr 零增长才中止）。

---

## 阶段二：可运行性评估

### 1. 结论先行

| 组件 | 能否在本机跑 | 说明 |
|---|---|---|
| `verify_ki_structure.py`（**裁判**） | ✅ **能跑，已实测** | 只需 Python 3.12 + PyYAML + 同目录的 `ki_vocabulary.py`。**唯一副作用：会多出 1 条虚假 FAIL**（见下） |
| `build_dissection_prompt()`（**规格**） | ✅ **能跑，已实测** | 纯字符串拼接，无外部依赖。喂一个手写的 `probe_report.json` 即可产出完整 prompt |
| `orchestrator.py`（self-improve） | ❌ 不可能 | 553 KB 单文件，深度绑定 `hydrocraft.db`、`model_obs_map`、观测数据集、codex CLI |
| `ki_dag_generator`（dag 生成） | ❌ 未评估/不可用 | 需要 LLM 后端 + 论文缓存 |
| `calibration_kit` | ❌ 不适用 | spotpy/pymoo 率定引擎，面向参数反演，非本仓库当前需求 |
| `kdt-release/`（MIT） | ✅ 纯文档 + 模板 + 3 个 validator | **优先取物的地方**，见下 |

### 2. 依赖

- **Python**：`pyproject.toml` 声明 3.10+；本机 3.12.3 实测可跑裁判与规格生成器。
- **包**：裁判只用标准库 + `PyYAML`（本机已装）。
- **外部二进制**：
  - `claude` CLI —— `spawn_cli_agent()` 直接 `subprocess.run(['claude','-p',prompt,
    '--allowedTools','Read,Write,Edit,Bash,Glob,Grep'], timeout=3600)`，
    env 里塞 `CLAUDE_AUTO_DISSECT=1`。**这就是它的 LLM 后端：Claude Code CLI 本身**，
    没有 API key 配置、没有 SDK，就是起一个子进程 agent。
  - `codex` CLI —— self-improve 的独立评审员，**版本围栏 ≥ 0.144**
    （`KDT_CODEX_BIN_TRUST=1` 可绕过），显式拒绝 npm 全局的 0.123。
  - 各模型自己的编译器（gfortran / cmake / R / Julia）。

### 3. 硬编码外部路径

在 `cli_agent.py` + `verify_ki_structure.py` 两个文件里数出 **30+ 处**绝对路径，
分四个根：`/mnt/disk1/Hydrocraft_server/`、`/home/server/knowledge-dissection-toolkit/`、
`/media/server/hc_ssd/forcing/`、`/mnt/datasets/`。按能否绕过分类：

**A. 软依赖（失败即静默回落，可绕过）**
- `/mnt/disk1/Hydrocraft_server/Hydrocraft/hydrocraft-web`（`backend.services.ki_kind`）
  + `hydrocraft.db` → `_detect_kind()` 查不到就回落 `process_model`（最严格档）。**这是好设计。**
- preflight 的 `binary_path` 漂移检查：查不到 DB 就跳过（只影响一条 warn）。

**B. 硬依赖（不可绕过，会制造假失败）——只有一处，但很关键**
```
/mnt/disk1/Hydrocraft_server/models/ki_tools_common/ki_tools_common/ki_projection_common
```
这是**跨文件一致性检查（manifest↔dag、format_spec↔dag、known_issues↔triplets）唯一的实现**。
导入失败时外层 `except` 会 `fails.append("FILE5/6 content check CRASHED …")`。
实测输出里就有这一条。
**代价**：离线跑裁判必然多 1 条 FAIL，而且**最有借鉴价值的那组等价性检查根本没执行**。
要真用起来，得自己重写 `entry_name` / `tool_files` / `read_triplet_entries` / `observability`
这四个共享读取函数——不难（都是 dict 取值 + 归一化），但**必须重写**。

**C. 规格 prompt 里的路径（只影响被 dissect 的 agent，不影响裁判）**
`python_env/bin/python`、三个投影生成器（`generate_skill_map.py` /
`generate_ki_manifest.py` / `generate_format_spec.py`）、
`kdt-release/templates/{SKILL_TEMPLATE.md, preflight_check_template.py}`、
`ki_dag_generator`、`openalex_search.py` / `paper_fetch.py` / `push_papers_to_docs.py`、
`stepb_dispatch_prep.py` / `stepb_verify.py`、代理 `127.0.0.1:7897`、
CMFD/HWSD/AVHRR/DEM/GRACE 等数据集路径、`data_registry/server_datasets.yaml`。
**其中三个投影生成器不在这个仓库里**（在 `ki_tools_common` 外部路径），
所以简报里"3 个组件是投影产物、从不手写"这条**在本机无法复现**——
生成器拿不到。要用只能自己写投影器。

### 4. 跑一次的代价

`spawn_cli_agent` 默认 `timeout=3600`（每模型 1 小时）；self-improve 的
`KDT_MAX_RETRIES_TOOL_BUILD` 默认 **20 次**重试，重型模型走 detached、**无时限**
（文档里提到 MARRMoT/Octave 单次 `PER_RUN_TIMEOUT` 设到 **6 小时**）。
`SELF_IMPROVE_HANDOFF.md` 明确记载：2026-06-23 两个 campaign 并跑
**把月度 Claude 额度烧穿了**。
量级判断：**一次完整 dissect = 1 个长时 Claude Code 会话（数十分钟到数小时）；
一次 self-improve campaign = 数十到上百个这样的会话 + 同量级的 codex 评审。**
这不是"跑一下试试"的量级。

### 5. `kdt-release/` 是不是更自足的发行版？

**是，而且是唯一带 MIT LICENSE 的部分。**内容：

```
kdt-release/
  LICENSE (MIT)  VERSION  README.md(27K)  CHANGELOG.md  DESIGN_RATIONALE_v5.1.md
  PREFLIGHT.md(25K)  VALIDATION_PROTOCOL.md(15K)
  pipeline/    AGENT_PROMPT_GUIDE.md  PIPELINE_GUIDE.md  DATA_REGISTRY_GUIDE.md
  validators/  preflight_forcing.py(40K)  check_calval_split.py(21K)  standard_calval.py(12K)
  templates/   SKILL_TEMPLATE.md  preflight_check_template.py  triplets_template.yaml
               knowledge_infrastructure_template.yaml  validation_sheet_template.md
               stage_log_template.json  DATA_KI_TEMPLATE.md  DATA_KI_DISSECTION_GUIDE.md
  examples/    unit_conversion_example.py  validation_example.py
```

**但它不含裁判**（`verify_ki_structure.py` 只在 `auto_dissect*/` 下），
也不含 `cli_agent.py`。所以：
- **要模板和协议** → 从 `kdt-release/` 拿，MIT，可以直接用；
- **要裁判的思想** → 只能读 `auto_dissect_multi_agent/`，然后**自己写**。

它的 `validators/` 三个脚本是领域绑定的（forcing 预检、率定/验证期切分检查），
对 HSTAR 不直接适用——我们没有"强迫数据"和"率定期"。

---

## 阶段三：实际尝试

### 3.1 ★ 用他们的裁判判我们手搭的 HSTAR KI 包（本次最有信息量的一次运行）

**做法**：把 `verify_ki_structure.py` + `ki_vocabulary.py` 单独放到 `/tmp/claude-1000/kdt/ma/`，
直接指向另一路 `kiss-trial` agent 正在搭的包。**没有做任何适配和让步。**

**注意**：该包当时**仍在建设中**（快照时间 2026-08-25 22:41，仅有
`SKILL.md` / `dag.yaml` / `diagnostics/triplets.yaml` / `preflight_check.py` / `run_and_score.py`，
`docs/`、`tools/` 目录尚未创建）。所以下面的失败**大部分是"还没建完"，不是"建错了"**。

```console
$ python3 verify_ki_structure.py .../docs/research/kiss-trial-pkg
KI: /home/huijun/HSTAR_Next/fem-chat/docs/research/kiss-trial-pkg
    tools=0 stage_docs=0 papers=0 triplets=13 shape=list
  FAIL  SKILL.md body lacks a 'output description' section (template §6/§8/§11)
  FAIL  SKILL.md body lacks a 'validated results' section (template §6/§8/§11)
  FAIL  SKILL.md body lacks a 'unit table' section (template §6/§8/§11)
  FAIL  SKILL.md has no KI-map section
  FAIL  tools/: 0 python tools, need >= 1 (FILE 2)
  FAIL  docs/: 0 STAGE skill docs (s1_*.md …), floor is 3 (FILE 3)
  FAIL  diagnostics/triplets.yaml has 13 entries, s5 requires >= 15
  FAIL  knowledge_infrastructure.yaml missing (FILE 5)
  FAIL  preflight_check.py does not emit the PREFLIGHT_REPORT= contract line (FILE 6)
  FAIL  docs/format_spec.yaml missing (FILE 6 in the current 7-file spec)
  FAIL  docs/gathered_papers.json missing — REQUIRED
  FAIL  FILE5/6 content check CRASHED (ModuleNotFoundError: 'ki_projection_common')
  warn  preflight: legacy (no PREFLIGHT_REPORT line) — retrofit to the report contract
  warn  docs/validation_convention.yaml missing, and there are no gathered papers …
FAIL (12 problems)   EXIT=1
```

#### 逐条判读：哪些对我们有意义，哪些是他们的领域税

| 失败 | 判读 |
|---|---|
| triplets 13 < 15 | **有意义但门槛任意**。13 条真三元组和 15 条没有本质差别；这是个"地板"，凑数就能过 |
| SKILL.md 缺三节 / 缺 KI-MAP | **有意义**。"输出描述 / 已验证结果 / 单位表"三节对 HSTAR 完全适用（Uz 量级、基准算例通过情况、mm-vs-m 单位陷阱）。KI-MAP 需要一个投影器 |
| tools=0, stage_docs=0 | **纯粹是没建完**，不是设计分歧 |
| manifest / format_spec 缺失 | **有意义但需自建投影器**（生成器在他们服务器上） |
| preflight 没有 `PREFLIGHT_REPORT=` | **高度可移植**。HSTAR 完全可以做：MKL `.so` 在不在、`hstar` 二进制可执行否、`1.cor`/`1.ele` 齐否、`LD_LIBRARY_PATH` 对否——每项 kind/subject/critical/status/**fix**，最后打一行 JSON |
| `gathered_papers.json` 缺失 | **地学域特有税**。他们的判据带来自文献；HSTAR 的判据来自**解析解和基准算例**，不是论文。这条不该照搬（但"判据必须有出处"的**精神**该搬——出处换成"train05 基准 + 解析解"） |
| `ki_projection_common` CRASHED | **环境假失败**，见阶段二 B |

#### ★ 顺带发现他们裁判的一个真漏洞

我们的 `dag.yaml`（KISS 格式）**根本没有 `outputs:` 键**——它用的是
`identity / boundary / inputs / processes / safety`。结果：
**裁判对 dag 报了零条失败。**

代码原因（`verify_ki_structure.py`）：
```python
_outs = (_dag.get("outputs") or [])
_obs  = [o for o in _outs if (o.get("observability") or {}).get("comparable_obs_shapes")]
if _outs and not _obs:      # ← 只有「有 outputs 但都不可观测」才失败
    fails.append(...)
```
`outputs` 整个键缺失 → `_outs == []` → 条件短路 → **不报错**。
后面的"介质规则"由 `if info.get("n_observable_outputs")` 守卫，`0` 也跳过。
于是一个**完全没有输出定义的 dag** 干干净净通过了所有 dag 检查。

这正是他们自己文件头那句话的反例——
"**a stage that cannot fail is not a check**"——他们在这条路径上恰好造了一个。
**给我们的教训：写门控时，"空集合"和"合规集合"必须区分开；
`if X and not Y` 这种写法天然放过 `X` 为空的情况。**

### 3.2 对 HSTAR 跑 dissect：卡在哪

按可行性递减，实际做到了第 3 步（最权威的那步）：

**跑不了完整 dissect。**阻塞点按顺序：
1. `orchestrator.py` 的 Phase 1 探针（`probe_report.json` / `io_graph.json` 生成器）在
   `stages/` 下，未评估；
2. FILE 5/6/8 三个投影生成器不在仓库里；
3. FILE 8 的 `ki_dag_generator` 需要 LLM 后端 + 论文语料；
4. FILE 9/10 需要 `openalex_search.py` + `paper_fetch.py` + 代理 —— 对 HSTAR **本来就不适用**。

### 3.3 ✅ 打印出了给 HSTAR 生成的完整 dissection prompt

**这一步成功了**，也是简报说的"最权威的『KI 该长什么样』的描述"。做法：
手写一份 `probe_report.json`（`domain: structural_fem`、`primary_language: Fortran`、
`build_system: make`），直接调 `build_dissection_prompt('HSTAR', work, out)`。

产出：**41,382 字符 / 731 行**，落在 `/tmp/claude-1000/kdt/hstar_prompt.md`（不入库）。

两个观察：
- **领域回落是干净的**。`structural_fem` 不在他们的 data registry 里，于是那一节印
  "No domain-specific data registered. Use built-in examples or published benchmarks."
  ——**恰好就是 HSTAR 该走的路**。
- **Phase 4 的通用回落对我们直接可用**，它给了一套**验证分级**：

  | tier | 含义 |
  |---|---|
  | `real` | 与独立实测数据比对 |
  | `analytic` | 与已发表的**解析解 / 基准解**比对 |
  | `synthetic` | 与自己生成的数据比对（只证明管线通） |
  | `stub` | 没有任何验证数据 |

  并且硬性规定："**NEVER set tier = 'real' unless you used actual independent observations.**"
  HSTAR 的绝大多数算例是 `analytic`（train01–train12 基准 + 解析解），
  少数（若有现场监测）才是 `real`。**这套分级建议直接搬进本仓库的 benchmark 元数据。**
- prompt 里为 Fortran 模型准备的两条铁律，**对 HSTAR 几乎是量身定做**：
  1. **copy-first**：绝不从 Python dict 生成 Fortran 定宽文件，必须"拷模板 → 按记录的列位切片替换"。
     附了真实事故：APEX 的 `_format_row` 用 f-string 写成 `(3I3, 4I5, 7F8.2)`，
     实际需要 `(3I3, 5I5, 7F8.2)`，**差一个 I5 列，静默列偏移**，
     诊断-修复-重试环**无法自动收敛**，因为 bug 在格式串生成模式本身而不在任何单个值上。
  2. 写任何 Fortran 输入生成器之前，必须 `cat -A <template> | head -20` 逐字节量列宽，
     把列布局记进 `input_preparation.md`。

  > 本仓库的 `skills/generator.py` 正是"从 Python 生成 `.glb`/`.LOA`/`.mat`"的写法。
  > 我们靠 `harness/gate.py` + 基准回归兜住了，但**没有列布局文档，也没有"从模板切片"的写法**。
  > train06/train09/train11/train12 那一串迁移事故（丢掉块 2 的 30 个水压面、
  > 丢掉粘结参数、水头 BC 施加到错误几何边界）在形态上和 APEX 那个 I5 列偏移是同一类病。

---

## 阶段四：A/B 方法论

### 4.0 先说一个必须纠正的前提

**简报里"带 KI 84% vs 不带 <40%"这个数字，在 KDT 仓库里不存在。**

我做了这些检索，全部落空：
- `gh search code --repo lzwei196/KDT "84%"` → **唯一命中**是
  `ki_counts.py` 的一句注释："tools: RECURSE. Flat `tools/*.py` is the common case (**84%**)
  but nesting is real (pySTEPS)" —— 说的是**工具目录扁平布局占比 84%**，与 A/B 无关；
- 检索 `without KI` / `no-KI` / `ablation` / `control arm` / `milestone` → 没有任何
  "带 KI vs 不带 KI"的对照实验；
- `AXIS_AB_RESULTS.md` 的 "A/B" **不是** with-KI / without-KI，
  而是 **Axis A（setup correctness）/ Axis B（decision correctness）**——
  测的是"**率定**框架"：agent 自主设计的率定方案能不能跑通、
  它选的优化器是不是跑全所有优化器之后的经验赢家；
- `ROBUSTNESS_TEST_PLAN.md` 同样是率定框架的鲁棒性矩阵。

所以那个数字要么来自 KISS 仓库、要么来自别处（另一路 `ki-compare` agent 可能有线索）。
**这一节我不编造它的测法**，改为：把 KDT **确实有**的、成熟的实验方法论提炼出来，
写成本仓库可以照着执行的版本。

### 4.1 他们真正的对照实验：Caravan 配对臂

这是 KDT 里唯一一个真正做过、有数字的对照设计。

**设计**：锁定 30 个流域（`sample30.json`，**先锁样本再跑**），跑三条臂，同一批流域、同一指标：

| 臂 | 做法 | 结果（test-NSE 中位数） |
|---|---|---|
| **default 臂** | 模型默认参数，不率定 | **−0.05** |
| **human 臂** | 人工搭的 DDS 率定（`dds_one.py`） | **+0.56**（93% 为正） |
| **agent 臂** | agent 读 KI 自主设计整套率定 | n=1 时 **0.555 ≥ human 0.475**（同一流域配对比较） |

方法论要点：
1. **样本先锁**（locked catchments 文件），不允许跑完再挑；
2. **三条臂共享同一评价代码**（`hbv_caravan.py` 同一 runner），差异只在"谁做决策"；
3. **配对比较**（同流域 agent vs human），不是两个分布对撞；
4. **有一个"地板"臂**（default / random），用来确认差距不是噪声；
5. **报告分布不报告平均**（ECDF 图），并给"为正的比例"。

### 4.2 他们的多维鲁棒性矩阵（A–H）——可直接改写成我们的验收表

`ROBUSTNESS_TEST_PLAN.md` 的核心是：**每个维度都有一条"绿灯判据"，而不是一个笼统的"跑通了"**。

| # | 维度 | 证明什么 | 绿灯判据 |
|---|---|---|---|
| A | **广度**（模型 × 领域） | 不是单模型运气 | ≥15 模型 / ≥6 领域，每个都真跑过 |
| B | **规模**（每模型多算例） | 不是单站点运气 | ≥1 个模型有 ≥100 算例的大样本分布 |
| C | **优化器通用性** | 不绑死一种搜索 | 4 种优化器端到端全跑通 |
| D | **判决诚实性** ⭐ | **没有虚假 PASS** | 每一条 `pass` 要么被证实、要么被降级 |
| E | **护栏有效性 / 对抗** | 护栏能抓到注入的故障 | 消融 + 故障注入，**给出检出率** |
| F | **可复现性** | LLM 随机性有界 | ≥5 算例 × ≥3 种子，判决与精度一致 |
| G | **专家对比** | 与人工相当 | 大样本上配对统计 agent ≈ human |
| H | **失败诚实性** | 不假装成功 | 结构性不可率定的算例被正确标出而非通过 |

**执行顺序按"鲁棒性价值"排，不按难度排**：D（判决诚实性）→ F（可复现性）→
E（护栏消融）→ B/G → A。理由一句话：
"**a framework that passes bad calibrations is not robust. Everything else assumes
the verdicts mean something.**"

**维度 D 的做法（最值得抄）**：把历史上**所有** 17 条 `holdout_pass` 拉出来，
逐条列 `baseline_r → calibrated_r`，人工判读"真的还是假的"，
然后**为每一个假 PASS 定位一个具体的门控漏洞**并修掉：
- 漏洞 1 **没有相关性地板** → GLM_AED 的 r 从 −0.89 变成 **−0.97**（更反相关了）却 PASS。
  修法：`corr_floor=0.5`，且用 **`min(cal_r, holdout_r)`**——
  防止一个短窗口单调趋势的高 r 把欠拟合"救"回来（焦作案例：holdout r 0.965 但 cal r 0.04）。
  **双向验证**：焦作必须失败、贵溪必须通过（防止修出假阴性）。重审 17 条：10 条真的存活，3 条翻转。
- 漏洞 2 **判据带挂不上** → `groundwater_level` 对不上 convention 的 `water_table`，
  退化成"只要打赢 baseline 就算过"。修法：量纲别名 + **无带时的量级兜底**（bias > 30% 直接失败）。
- 漏洞 3 **无证据的历史 PASS** → 5 条早于"证据记录"上线的记录，指标字段全 NULL，
  **不可审计** → 一律降级为 `holdout_inconclusive`，重跑。

三条修完的共同形态：**先审计存量 → 每个假 PASS 对应一个具名漏洞 → 修 → 双向验证 → 重审全部存量。**

### 4.3 他们的"多地点自改进"实验（§7）—— 与我们要做的 A/B 最接近

`HOW_TO_USE_SELF_IMPROVE_KI.md` §7 定义了一个 **每模型 5 个地点**的实验，
测量四个量（**这四个量正是我们要的**）：

1. **PASS 率 k/5** + 该 obs_shape 对应的**族内适用指标**的离散度；
2. **KI 稳定化**：每个新地点产生的**新提案条数**——
   应该在第 3–5 个地点**下降**（如果不降，说明经验没有沉淀）；
3. **泛化**：地点 1 上做的修复，有没有让地点 2–5 **不需要新修复就直接通过**；
4. **无回归**：此前 PASS 的地点没有掉下去。

### 4.4 照着写给本仓库的 A/B 执行方案

把上面三节合成一个**可以直接照着跑**的方案，针对"5 个算例族 × 开/关经验召回"：

**样本与锁定**
- 先写 `docs/research/ab-sample.json` 锁定 5 个算例族及其**具体变体**
  （建议：重力坝静力 / 重力坝地震 / 边坡 / 稳态渗流 / 温度场——覆盖 4 种 `type_problem`
  Q/F/S/E 且都有已迁移基准）。**先锁再跑，跑完不许换样本。**
- 每族取 **3 个变体**（如 train05a / train05b / 一个新参数点），共 **15 个算例**。

**三条臂（不是两条）**
| 臂 | 配置 | 作用 |
|---|---|---|
| **floor** | 只给 CLAUDE.md，无 references、无 KI 召回 | 地板，确认差距不是噪声 |
| **A（关经验）** | 完整 references，但**关掉** LangGraph 的经验召回/KI 注入 | 对照组 |
| **B（开经验）** | 完整 references + 经验召回开 | 实验组 |

**统一评价代码**：三条臂全部经 `harness/gate.py` 判 PASS，
**不允许任何一条臂走人工判读**。这对应他们的"三条臂共享同一 runner"。

**里程碑定义（必须先写死，跑之前定）**——建议四级，逐级更严：
| M | 里程碑 | 机器判据 |
|---|---|---|
| M1 | 生成的输入文件齐备 | `.glb`/`.mat`/`.LOA`/`.cor`/`.ele` 全在，且 `type_problem` 与目标分析一致 |
| M2 | 求解器正常退出 | 退出码 0 且 `1.flavia.res` 存在、非空 |
| M3 | 结果物理合理 | 位移量级在基准的 **[0.2×, 5×]** 区间内（防"跑通但离谱"） |
| M4 | **PASS** | `harness/gate.py` 判定通过（与基准的相对误差在阈值内） |

**指标（每条臂、每个算例）**
1. **首次成功率** = M4 在**第一次**尝试即达成的比例（这是主指标）；
2. **迭代次数** = 达到 M4 所需的 workflow 轮次（未达成记为**右删失**，报中位数而非均值）；
3. **最远里程碑** = 未 PASS 时停在 M1/M2/M3 的哪一级（这比二值"失败"信息量大得多）；
4. **新提案数** = 该次运行产生的新 KI 条目数（用于测 4.3 的"稳定化"）。

**判定谁来做**：`harness/gate.py`，**机器判**。
人只在两处介入且必须记录：(a) 判据阈值的事前设定；(b) 事后对**每一条 PASS 的诚实性审计**
（照 4.2 维度 D 的做法，逐条问"这个 PASS 是真的吗"）。

**重复次数**：每算例 **3 个种子**（改变 agent 的随机性来源），共 15 × 3 × 3 臂 = **135 次运行**。
若成本太高，先做 D 维度（5 算例 × 3 种子 × 2 臂 = 30 次），**F 维度的可复现性比广度更值钱**。

**混淆控制**（他们踩过的坑，逐条对应）
- **同一算例上配对比较**，不做分布对撞；
- **臂之间只差经验召回一个开关**，references / 模板 / 求解器版本全部冻结（记 git commit）；
- **一次只跑一条臂**（他们并跑两个 campaign 互相覆写状态 + 烧穿预算）；
- **环境中断 ≠ 失败**：API 限流 / 超时 / 网络断，必须标成独立状态
  （对应他们的 `incomplete_environmental`），**不许计入分母当作模型失败**；
- **基准算例本身不能进实验集**——如果经验库里已经有这个算例的答案，B 臂就是在背答案。
  必须用**同族的新变体**（这一条他们用 holdout split 解决，我们用"变体"解决）；
- **右删失处理**：达不到 M4 的运行，迭代次数不能记 0 也不能记 ∞，报"k 次内达成率"曲线。

**绿灯判据（事前写死，防止事后挪门槛）**
> B 臂的首次成功率显著高于 A 臂（15 配对，符号检验 p<0.05），
> **且** B 臂在第 2、3 个同族变体上的新提案数低于第 1 个（经验确实在沉淀），
> **且** B 臂没有任何一个此前 PASS 的算例发生回归。

---

## 阶段五：结论

### 5.1 KDT 能不能直接用在 HSTAR 上？

**不能直接用。三层拦路，从硬到软：**

1. **基础设施绑死（硬）。**主干工具链假定一台特定服务器：
   `/mnt/disk1/Hydrocraft_server/hydrocraft.db`（模型登记、观测映射、KI 分类）、
   `ki_tools_common` 共享库、`ki_dag_generator`、论文缓存与 OpenAlex 代理。
   其中**三个投影生成器（skill_map / manifest / format_spec）根本不在仓库里**，
   所以"11 个组件里 3 个是投影产物"这个设计**在本机无法复现**——生成器拿不到。
2. **领域绑死（硬）。**它整套判据学是"**模型输出 vs 野外观测**"：
   `observability.comparable_obs_shapes`、`obs_shape` 分类、
   介质词表（water/soil/ocean/ice/…，38 个硬编码词，**一个力学词都没有**）、
   `gathered_papers.json` 文献带、`model_obs_map`。
   HSTAR 是**单一确定性求解器 + 解析解/基准算例**验证——
   我们没有"观测形态"，也不从论文里读通过带。
   照搬 dag/convention 这套会强行造出一堆空壳。
3. **成本（软）。**一次 dissect = 一个长时 Claude Code 会话；
   一次 campaign = 数十上百个。他们自己烧穿过月度额度。

**但"整体不能用"不等于"没有可用的东西"**——见 5.2。
另外**许可上唯一干净的取物口是 `kdt-release/`（MIT）**：
`SKILL_TEMPLATE.md` / `preflight_check_template.py` / `triplets_template.yaml` /
`stage_log_template.json` / `VALIDATION_PROTOCOL.md` 可以直接拿来改。

### 5.2 「一个规格 + 一个裁判」对本仓库的可迁移之处

本仓库现状：`fem-chat/harness/gate.py` 是**单一 PASS 门控**——
它检查 `run.log` 的崩溃标记（forrtl / sigsegv / severe）、
解析 `1.flavia.res` 的节点场值、判物理合理性，
并被 `workflow/tools/validate_outputs.py` 和 `skills/promote_case.py` 共同调用
（文件头明说：就是为了消除两套并行 PASS 门控的漂移）。
**架构方向和 KDT 一致，但它只看"这次运行的结果"，不看"文档说的和代码做的对不对得上"。**

建议按投入产出排序，落成 `harness/consistency.py`（新增，与 `gate.py` 并列）：

**P0 —— 立刻能做、成本最低、正中当前痛点**

1. **`type_problem` 一致性检查。**
   CLAUDE.md 里写死了 static=Q / modal=E / dynamic=F / transient=S，
   并特意警告"⚠ 是 Q 不是 F"、"复制模板后必须核对"。
   **这条规则现在只存在于文档里，没有任何代码验证。**
   做法：在 gate 前置一步，解析 `config.json` 的 `analysis_type` 与生成的 `.glb` 里的
   `type_problem`，不一致直接 FAIL。
   —— 这就是 KDT 的"SKILL.md 必须点名 dag 的 rank-1 变量"的同构物。
2. **`preflight_check.py` + `PREFLIGHT_REPORT=` 契约**（几乎零成本，收益极高）。
   把现在散在 `intel_runtime.py` / `quick_analysis.py` 里的隐式前置检查显式化成一个脚本：
   MKL `.so` 目录找到没、`hstar` 二进制存在且可执行否、`1.cor`/`1.ele` 齐否、
   模板与 override JSON 能否合并、`gravdam_meta.json` 边缘信息在否。
   每项 `{kind, subject, critical, status, fix}`，最后一行打 `PREFLIGHT_REPORT={...}`。
   **关键是每条失败必须带 `fix`**——KDT 的裁判把"failed check without a fix"判 FAIL，
   因为没有修法的报错等于噪声。
3. **文档↔代码的数值一致性。**
   `docs/references/*.md` 里写的每一个数值门槛、每一个参数名、每一个文件扩展名，
   都应该在代码里存在。最小可行版：抽取 references 里所有形如
   `` `xxx=N` `` / `` `*.ext` `` / 函数名的 token，grep 全仓库，找不到就报。
   —— 这是 KDT 的"SKILL.md 说的 NSE≥0.x 必须在 convention 里存在"的同构物。

**P1 —— 中等成本，结构性收益**

4. **`docs/references/` 与 CLAUDE.md 路由表的断链检查。**
   CLAUDE.md 列了 12 个 reference 文件，**每一个都必须存在**
   （KDT：SKILL.md 引用的每个 stage doc 必须存在，断链即 FAIL —— "the pipeline walk points at nothing"）。
   反向也查：`docs/references/` 下有而路由表里没提的文件 = 运行时不可见。
5. **基准元数据引入 KDT 的验证分级**：`real / analytic / synthetic / stub`，
   并硬性规定"没有真实独立观测就不许标 real"。
   HSTAR 的 train01–train12 绝大多数是 `analytic`。
   现在我们只有二值的 PASS/FAIL，**丢失了"这个 PASS 有多硬"的信息**。
6. **`direction` + 引文式判据表。**
   给每个基准算例写一份 `validation_convention`：
   比对量（Uz / Ux / 频率 / 水头）、`direction`、通过带（相对误差 %）、
   **以及这条带的出处**（"train05 基准" / "解析解 XX 式" / "人工确认 2026-xx-xx"）。
   规则照抄：**没出处的门槛写 `null`，不许猜**。
   本仓库的记忆里已经有一堆"人工确认"的判定（train11 的 0.03%/0.07%、train09 的 5.7%），
   这些数字现在散在提交信息和记忆文件里，**没有一处机器可读**。

**P2 —— 大成本，先别做**

7. KI-MAP 投影、manifest 投影 —— 需要先有稳定的组件清单才值得投影。

**最后，抄他们的元规则（比抄任何一条检查都值钱）：**
- 不能失败的阶段不是检查；
- **检查跑不起来 = 失败**（`except: fails.append(...)`，不是 `except: pass`）；
- "两种格式都接受"的读法是不可失败的检查，迁移期一过必须删掉回退分支；
- **先做回填运动，再把 warn 翻成 fail**——绝不制造几百个瞬间失败；
- 区分"真缺"与"叫法不同"：同义词报 warn（改名），真没有才报 fail；
- 查询失败要回落到**最严格**的一档；
- 检查器与生成器**共用同一套读取函数**；
- ⚠ 外加一条**从他们的 bug 里学到的**（见 3.1）：
  **`if X and not Y` 会静默放过 `X` 为空的情况**——写门控时必须把"空集合"单列一个失败分支。

### 5.3 self-improve 有而本仓库 LangGraph 闭环没有的机制

本仓库已有：失败→triage→修复、基准门控、经验（KI）沉淀、人工审查中断。
KDT 多出来的，按价值排：

1. **★独立评审员 + 快照回滚。**
   所有工具代码改动过**另一个模型**（codex）的评审，
   REJECT → **回滚到测试前快照** + 标 STAGED，**canonical 永远不持有未评审代码**。
   而且**连"为了让模型跑起来顺手改的代码"也要评审**（`KDT_REVIEW_REALCASE_EDITS` 默认开）。
   本仓库的闭环里，修复是自己改自己审。
2. **★run-validity critic：判"这次运行合不合法"，与"指标好不好"分开。**
   `model_ok / model_limitation / workflow_incomplete` 三态。
   数字好看但跑法不对 → 判 incomplete；数字难看但跑法对且是模型固有局限 → 接受为真实判决。
   本仓库只有 PASS/FAIL 一维，**"这次跑对了吗"和"这次结果好吗"混在一起**。
   映射到 HSTAR：用了错误的 `type_problem`、地震没进运动方程（PRJ-6057 那类）、
   水压面丢了一半——这些都是 `workflow_incomplete`，
   哪怕位移数字碰巧落在基准区间里也不该算数。
3. **★分级晋升 + 改动类型分类学。**
   `promotion_policy.py` 是个**纯函数**（无副作用，执行交给 `auto_promote.py`）——
   这个"策略与执行分离"本身就值得抄。规则：
   KI-local 可逆的自动晋升；跨模型/定义"什么算有效"的永远人工；
   **只有"调过的参数"才需要跨算例泛化验证**，知识型条目从一个算例就能确认；
   bundle 保守汇总（一票否决），防止 tier1 改动搭 tier3 三元组的便车。
4. **★环境中断 ≠ 模型判决。**独立状态 `incomplete_environmental` / `env_aborted`，
   限流/超时自动重试（3 次 / 180s 退避）。
   本仓库如果一次 API 超时被记成"这个算例失败了"，经验库就被污染了。
5. **确定性的全有全无指标。**一次 `all_metrics()` 出全套，
   只有"无重叠"允许 null 且必须给 `metrics_null_reason`；NaN 必须重算不许静默变 null。
6. **超出范围就停手。**`requires_calibration` / `requires_human_engineering` /
   `requires_data` 三类明确判定为**不是 self-improve 能修的**，转提案、终止循环。
   本仓库的闭环缺这个"认输出口"，容易在不可修的问题上空转
   （train05a MAT_DE、train10 VIE 就是这种，最后靠人工挂起）。
7. **重型运行 detached + 可恢复。**长运行交给独立进程、**无时限**轮询，
   runner 必须能跳过已完成单元，让进度跨重试累积。
8. **并发与停机纪律。**同模型禁止并发；停止时先杀编排器再**等 agent 子进程自然退出**
   （半路杀掉正在写文件的 CLI 会损坏 `~/.claude.json`）。
9. **评审器不设硬超时，改用停滞检测。**硬超时会把 codex 的推理截断，
   **截断的输出被读成 REJECT** —— 一个非常隐蔽的坑。

### 5.4 哪些是他们领域/多模型语料特有的，单求解器项目**不该**照搬

| 机制 | 为什么不该搬 |
|---|---|
| `gathered_papers.json` + OpenAlex/paper_fetch 文献管线 | 他们的通过带来自各模型自己的领域文献（每 KI 约 16 篇）。HSTAR 的判据来自解析解与基准算例，**没有对应的文献层**。硬搬会造出一堆空 JSON |
| `observability.comparable_obs_shapes` / `obs_shape` 分类 / `model_obs_map` | 这套是为"**把野外观测绑到模型变量上**"设计的。我们没有观测，只有基准 |
| 38 词**介质词表** | 纯地学：water/lake/ocean/soil/ice/snow/canopy/crop/…，**一个力学词都没有**。这类"防止湖泊模型对上土壤探头"的歧义在单求解器里不存在 |
| `_detect_kind` 的四类 KI（process_model / python_lib / data_ki / coupler） | 因为他们要管 270+ 个异质模型 + 135 个库 + 38 个数据集。我们只有**一个**求解器 |
| 四层架构（L0 数据文档 / L1 共享库 / L2 模型 KI / L3 验证） | L0/L1 是为跨模型复用强迫/土壤/地表数据而生。HSTAR 的输入是网格与材料，没有这个跨模型复用面 |
| `ki_tools_common` 强制复用条款 | 同上 |
| `calibration_kit`（DDS / SCE-UA / DREAM / NSGA-II） | 参数率定引擎。**但注意**：XFJ 反演算例链（`inverse_mat[1-3]`）在概念上是率定，将来若要做参数反演的自动化，这套"agent 设计率定方案 + 引擎跑 + holdout 门控"的分工值得回头再看 |
| ≥15 条三元组、≥5 篇 docs、>200 行 SKILL.md 这些**数字门槛** | 是他们 270+ 模型舰队统计出来的地板，对我们没有校准意义。**要设阈值就自己量一遍再定** |

### 5.5 一句话总结

**KDT 本体在 HSTAR 上跑不起来**（基础设施与领域双重绑死，投影生成器还不在仓库里）；
**但它的裁判可以离线运行，我实际用它判了我们手搭的 KI 包**，
结果是 12 条 FAIL（其中 1 条是环境造成的假失败，多数是包还没建完），
**同时反过来暴露了他们裁判自己的一个不可失败路径**（dag 缺 `outputs` 键 → 零失败）。
真正值得搬的不是它的组件清单，而是它的**元规则**（不能失败的阶段不是检查、
检查跑不起来即失败、先回填再翻硬、区分真缺与改名）、
它的**跨文件一致性检查**这个类别（本仓库完全空白，而 `type_problem` 映射、
references 路由表、判据数值这三处正好都是文档说一套、代码无人验的高危区），
以及 self-improve 里的**独立评审+快照回滚**与**run-validity critic**这两个我们闭环没有的关卡。
