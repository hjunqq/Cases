# KISS KI 包格式实证试验 — 用 `gravdam_static_2block` 打一个包并只靠它跑算例

> 日期：2026-08-25 · 性质：**实证实验**，不是格式分析报告
> 试验产物：`fem-chat/docs/research/kiss-trial-pkg/`（research 下，不进运行时）
> 参照：`lzwei196/KISS---Knowledge-Infrastructure-for-Scientific-Simulation` 的 `models/ADCIRC/`

本文按阶段追加写入，边做边记。

---

## 阶段一 · 选目标并读透

### 目标

算例族 **`gravdam_static_2block`**（`fem-chat/skills/templates/gravdam_static_2block.json`）：
重力坝二维静力，地基(group1) → 坝体(group2) 两步施工 + 上游面水压。

模板本体只有 25 行，但要真正跑起来需要的知识分散在至少 8 个地方
（`CLAUDE.md` 的 4 条硬规则、`mesh-and-geometry.md` 的坝体几何与水压边朝向、
`error-recovery.md` 的 7 条 Pattern、`recipe-catalog.md` 的 4 步配方、
`compatibility-matrix.md` 的 type_problem 映射、`run_pipeline.py` 的自动
solver 切换逻辑、`harness/gate.py` 的判分口径、`docs/benchmark-catalog.md`
的注册表）。**这种"知识分散度"正是 KI 包想解决的问题**，所以它是个合适的靶子。

### 读到的关键事实（全部现场核对，非记忆）

**求解器与运行时**

| 事实 | 出处 |
|---|---|
| 求解器二进制 `/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR/x64/Release/hstar`（7.7 MB，2026-06-30） | `skills/run_pipeline.py:57` 的 `HSTAR_EXE`，可用 `HSTAR_EXE` 环境变量覆盖 |
| 必须经 `quick_analysis.py` / `run_pipeline.py` 启动；它们 import `intel_runtime` 注入 `LD_LIBRARY_PATH` | `run_pipeline.py:71-76`，`CLAUDE.md` §Solver invocation rules |
| 本机实测发现 compiler `2026.1` + mkl `2026.1` | `python3 skills/intel_runtime.py -v` |
| 直接 `./hstar` → `libmkl_intel_lp64.so.2 not found` | `error-recovery.md` Pattern `HSTAR_MKL_SONAME_MISSING` |

**配置语义**

- `type_problem`: static=**Q** / modal=**E** / dynamic=**F** / transient·thermal=**S**
- `solver` 自动切换（`run_pipeline.validate_config`）：`tp=F` 且 npoin>1000 → PARDISO；
  任意 npoin>5000 → PARDISO；**FSI 配置强制留 PROFILE**（PARDISO 会静默丢掉
  nifsgroup 耦合项，退化成干模态）
- 水压边必须来自 `gravdam_meta.json` 的 `upstream_face_edges`（模板里写
  `water_pressure.use_meta_edges: true`，由 `run_pipeline.py:283-292` 解析）。
  **全局 x_min 自动探测会打到地基左边界**，导致坝顶往上游跑。
- 一个 job 目录只能跑一次分析（覆盖 `1.flavia.res`）。
- 绝不产出 Abaqus `.inp`。

**判分**

- `harness/gate.py:physics_gate(job_dir)` → `(bool, [problems])`：查 `1.flavia.res` 存在、
  `run.log` 无 `forrtl`/`sigsegv`/`severe`、值有限、非全零。**故意粗**，只挡垃圾。
- **`gravdam_static_2block` 在 `docs/benchmark-catalog.md:13` 明确标注
  `(no validator)`** —— 这个算例族没有注册的解析/参考解校验器。
  可用的相近校验器是 `mini_gravdam`（npoin=46 的 2 步施工小坝，参考沉降 −2.96 mm），
  但它的 mesh fingerprint 对不上，直接调用会 NOT_APPLICABLE。
  → 所以判分层只能是 `physics_gate` + **本包自己写的物理自检**
  （坝顶 +x 位移、uy<0 沉降、量级合理）。这一条是建包过程逼出来的第一个发现。

**已知静默缺陷（素材来源：`docs/capability-inventory.md` + 最近 5 个提交）**

1. `elem_info()` 缺省回退把任何未知 (nnode,ndimn) 组合**静默写成 2D 四边形 index 5**
   （tet/wedge/B20 全中招），而 `workflow/capability/registry.yaml` 对外声明支持 tet。
2. `CAMCLAY` 是死配置：被列进塑性材料用于置 `gid_ep`，但 `_gen_mat` 没有对应分支 →
   开关按塑性置位、材料却落到 ELASTIC。
3. `Yield`/`FACTOR`/`PLASTICSTRAIN`/`PRINCIPALSTRESS` 四个块此前不被解析器识别，
   节点行灌进 `STRESS` 段，报告里的 "Sxx 范围" 实际是屈服指标范围（已于 8e4ad79 修）。
4. 渗流块头连字符不匹配：解析器找 `WATER_HEAD`/`PORE_PRESSURE`，求解器写
   `WATER-HEAD`/`PORE-PRESSURE` → 渗流算例 Step 4 什么都不报（已于 6e1cc19 修）。
5. FSI 配置若被切到 PARDISO，nifsgroup 耦合项静默消失，模态结果退化为干模态
   （已加保护，但保护本身依赖 `fsi.use_meta_edges` 这一个键）。
6. `water_pressure.use_meta_edges=true` 而 `gravdam_meta.json` 缺失时，
   `run_pipeline.py:290` 只打一行 WARNING，`edges_list` 置空 →
   **水压整个消失，算例照常跑完出结果**，这是本次新识别的第 7 条静默失效。

（1、2、6 至今未修，是本包 `safety.hazards` 的核心内容。）

### KISS 侧规格（现场 `gh api` 取回核对）

- `SKILL.md` 开头是 blockquote 的 **MANDATORY EXECUTION POLICY**（必须跑真二进制、
  失败先查 triplets、禁止用简化公式替代）+ **DEBUGGING PROTOCOL**
  （查三元组 → 读官方文档 → 找跑通样例 → 改工具；明确禁止写自定义调试脚本）。无 frontmatter。
- `dag.yaml`：`template_version` / `identity`（含 `implementation.provenance`）/
  `boundary{scope_in,scope_out,spatial,temporal,closure,notes}` / `inputs`（分
  forcing·parameters·initial_conditions·boundary_conditions，每项带 unit +
  `model_input_format` + notes 且 notes 反向链 triplet id）/ `processes` / `safety.hazards`
  （每条 `id`/`kind`/`description`/`severity`）。
- `diagnostics/triplets.yaml`：`id / stage / failure_domain /
  symptom{description,error_pattern,detection_method} /
  diagnosis{root_cause,explanation,affected_components} /
  remedy{action,tool_to_run,manual_steps,prevention} / severity / cross_references`。
  `severity: silent` 是最高优先级类别，ADCIRC 20 条里前 4 条全是 silent。

**决定不建的两个文件**：`knowledge_infrastructure.yaml` 和 `workflow/workflow.md`。
理由见阶段四第 4 问。

---

## 阶段二 · 按 KISS 规格建包

包在 `fem-chat/docs/research/kiss-trial-pkg/`，共 1511 行：

| 文件 | 行数 | 内容 |
|---|---:|---|
| `SKILL.md` | 199 | MANDATORY EXECUTION POLICY + DEBUGGING PROTOCOL 前言，6 个 stage 表，逐参数的 config 语义表，**按信息量排序的 6 条验收检查** |
| `dag.yaml` | 238 | `identity`（含 provenance：YL 主线二进制，明确声明 `HSTAR_Q/` 是另一条线不可混用）+ `boundary`（scope_in 7 条 / **scope_out 10 条**）+ `inputs`（4 类，每项带单位与 `model_input_format`，notes 反链 triplet）+ `processes` + `safety.hazards` **13 条** |
| `diagnostics/triplets.yaml` | 379 | **13 条三元组**，`severity` 分布：silent 10 / degraded 2 / fatal 1 |
| `preflight_check.py` | 415 | 结构化检查，无任何硬编码机器路径 |
| `run_and_score.py` | 280 | 按产物存在性分阶段续跑 + 判分，写 `result.json` |

YAML 已用 `yaml.safe_load` 验证可解析，13 条 hazard 的 `triplet` 反链全部命中真实 id，无悬空引用。

### 三元组来源分布（诚实标注）

- **dt_hstar_001..008**：`docs/references/error-recovery.md` 的 7 条 Pattern 的**重新编码**（补上 KISS schema 的 `severity` / `detection_method` / `prevention` 三个字段）。这部分**不是新知识**。
- **dt_hstar_009**：`gravdam_static_2block` 无注册校验器 → "physics_gate PASS ≠ 结果正确"。`benchmark-catalog.md` 里只是表格一格 `(no validator)`，从未作为**操作警告**写下来过。
- **dt_hstar_010 / 011**：单位类静默错误（E 用 MPa、`gamma_w` 用 1000）。**references/ 里从未记录过这套 deck 的单位约定** —— HSTAR deck 本身不带量纲。
- **dt_hstar_012 / 013**：`elem_info` 静默回退成 2D 四边形、`CAMCLAY` 死配置。来自 `capability-inventory.md`，此前只在审计文档里，没进过操作路径。
- **dt_hstar_005（新发现）**：见下。

### 建包过程中新发现的静默缺陷 —— dt_hstar_005

在填 `dag.yaml` 的 `inputs.parameters[上游面边表].notes` 时，KISS 的字段结构逼我回答
"这个输入缺失会怎样"。查 `run_pipeline.py:283-292`：

```python
if wp and wp.get("use_meta_edges"):
    meta_path = Path(job_dir) / "gravdam_meta.json"
    if meta_path.exists():
        wp["edges_list"] = [...]
    else:
        print("WARNING: use_meta_edges set but gravdam_meta.json not found — no water edges applied")
        wp["edges_list"] = wp.get("edges_list", [])
```

`gravdam_meta.json` 缺失 → 只打一行 WARNING → `edges_list` 为空 →
**生成的 1.LOA 没有任何面荷载 → 算例照常跑完、照常沉降、照常出结果**。
这条以前不在任何 Pattern 清单里。阶段三对它做了对照实验，结论见下。

**没有建**的两个文件：`knowledge_infrastructure.yaml` 与 `workflow/workflow.md`。
理由见阶段四第 4 问。

---

## 阶段三 · 只靠包把算例跑起来

全新临时目录 `<scratchpad>/kiss-trial-run/`，从空目录开始。

### 3.1 preflight

```
$ python3 …/kiss-trial-pkg/preflight_check.py .
[PASS] python_version: Python 3.12.3
[PASS] repo_layout: toolchain found under /home/huijun/HSTAR_Next/fem-chat
[PASS] solver_binary: …/hstarYLOrig/HSTAR/x64/Release/hstar (7762424 bytes)
[PASS] mkl_runtime: 2 oneAPI dirs; MKL interface libs: libmkl_intel_lp64.so, libmkl_intel_lp64.so.3
[PASS] solver_links: all dynamic deps resolve under the injected environment
[PASS] job_dir: …/kiss-trial-run
[FAIL] mesh_files: missing 1.cor 1.ele
         remedy: python3 …/skills/gen_gravdam.py …/kiss-trial-run --height 100
6 pass · 0 warn · 1 fail · 0 skip  ->  NO-GO
```

`solver_links` 这条比 KISS 那份强：它用 `intel_runtime.inject_into_env` 构造环境后
真的 `ldd` 一遍二进制，"MKL 目录存在" 和 "这个二进制能起来" 是两回事。
本机实测发现的是 `libmkl_intel_lp64.so.3`（2026.1），不是文档里写的 `.so.2` ——
路径发现机制确实在起作用，硬编码路径的写法在这台机器上会直接失败。

### 3.2 跑 + 判分（一条命令）

```
$ python3 …/kiss-trial-pkg/run_and_score.py . --height 100
[PASS] physics_gate: clean
[PASS] two_construction_steps: 2 DISPLACEMENT block(s); nblks=2 expects 2
[INFO] result_blocks: DISPLACEMENT, NODAL_FORCE, STRESS
[PASS] water_edges_applied: 12 upstream-face edges applied
[PASS] crest_downstream: max ux on the dam body = 0.0156481 m (must be > 0, downstream)
[PASS] dam_settles: min uy on the dam body = -0.00829418 m (must be < 0)
[PASS] magnitude_sane: max |u| = 0.0156481 m
[PASS] group_order: centroid y: group1=-37.5, group2=50
[PASS] global_equilibrium: sum of nodal forces: Sx=0.57, Sy=-1.58 (scale 1.028e+08)
PASS
```

**真实求解器、真实 `1.flavia.res`**。H=100 m 满库：坝顶下游位移 **+15.6 mm**、
沉降 **8.3 mm**，量级对得上重力坝工程直觉。全局节点力和 Σ/量级 ≈ 5.5e−9 与 1.5e−8，
平衡自检通过。

再跑一次同一目录，两个 stage 都被产物存在性跳过，`1.flavia.res` 没有被覆盖
（`result.json.stages` 记录 `"reason": "1.flavia.res present — re-solving would clobber it (dt_hstar_008)"`）。

### 3.3 对照实验：dt_hstar_005 真的会静默通过吗

复制同一套网格到 `kiss-trial-nowater/`，**只删掉 `gravdam_meta.json`**，其余全同。

preflight 先拦了一道：
```
[FAIL] gravdam_meta: gravdam_meta.json absent while a mesh is present
         triplet: dt_hstar_005
```

**强行跑过去**，结果：

| 检查 | 有 meta（正确） | 无 meta（水压全丢） |
|---|---|---|
| `physics_gate` | PASS | **PASS** |
| `two_construction_steps` | PASS | **PASS** |
| `crest_downstream` (max ux) | PASS · +15.6 mm | **PASS** · **+0.26 mm** |
| `dam_settles` (min uy) | PASS · −8.3 mm | **PASS** · −12.9 mm |
| `magnitude_sane` | PASS | **PASS** |
| `group_order` | PASS | **PASS** |
| `global_equilibrium` | PASS | **PASS** |
| `water_edges_applied` | PASS · 12 edges | **FAIL** ← 唯一抓到的 |

**这是本次实验最硬的一条证据**：水压整个消失，坝顶位移差 60 倍，
而仓库现有的通用门控（`physics_gate`）、以及连
`error-recovery.md` 里那条经典的"坝顶必须往 +x 走"符号检查，**全部通过** ——
无水时坝顶仍有 +0.26 mm 的泊松外鼓，符号是对的。
只有从 run.log 里解析"实际施加了几条水压边"这一条专门为该缺陷写的检查抓住了它。

> 顺带一条物理观察：无水时沉降反而更大（12.9 mm vs 8.3 mm）。
> 上游面水压有向上的分量并使坝体绕坝踵有轻微转动，抵消了一部分沉降。
> 这也说明"沉降变小了"不能当作"水压加上了"的证据。

### 3.4 漏项清单 —— 本实验最有价值的产出

**每一条都是我在只看包的情况下不得不回头查包外东西的记录。**
（前提坦白：包是我自己建的，所以"我知道什么"这件事无法完全模拟一个陌生读者；
下面只记录**真的发生了、有可复现证据的**回查，不记录我脑子里的东西。）

| # | 查了什么 | 为什么包里没有 | 本该放进包的哪个文件 | 证据 |
|---|---|---|---|---|
| L1 | `skills/mesh_io.py` 的 `read_elements` / `read_element_group_ids` 返回值形状 | **KISS 格式没有承载"工具链 Python API 契约"的位置**。`dag.yaml` 的 `processes.modules` 只有 `name/role/brief` 三个散文字段；`inputs[]` 描述的是**求解器**的输入文件，不是**脚本**的函数签名 | 无处可放。要么给 `dag.yaml` 加一个 KISS 没有的 `toolchain_api` 段（我在 `identity.toolchain` 下加了文件路径，但放不下签名），要么就是纯 docstring | `run_and_score.py` 首次运行崩在 `AttributeError: 'list' object has no attribute 'get'` —— 我按 `{eid: nodes}` 猜，实际是 `[(eid,[n…]), …]` + 一个平行的 gid list |
| L2 | `tools/flavia_to_vtu.py` 里有可导入的 `read_flavia_res`，而 `run_pipeline.py` 的同类解析是**内联在 `main()` 里、不可导入的** | 同 L1。而且这条是仓库自身的结构问题：**结果解析有两份实现，只有一份可复用** | 同 L1 | 只能靠读源码确认；`harness/gate.py:result_values` 返回的是**打平的数值列表**，没有 section/block 结构，判分不够用 |
| L3 | `gravdam_static_2block` 到底有没有校验器 | 这条**放得进** KISS 格式（我把它写成了 dt_hstar_009 + `result.json` 的 `validator: null`），但需要先去 `benchmark-catalog.md` 和 `validate_results.py` 查一遍 | 已放入 `diagnostics/triplets.yaml` dt_hstar_009 | `benchmark-catalog.md:13` `(no validator)` |
| L4 | `run_pipeline.validate_config` 的自动 solver 切换阈值（npoin>5000 → PARDISO） | 放得进 `inputs.parameters[控制开关].notes`，我放了 | — | `run_pipeline.py:95-101` |
| L5 | 水压边缺失时的具体行为（只 WARNING、不失败） | 放得进 —— 但**只有先去读源码才写得出来**。KISS 的字段结构提示了要问这个问题，没有提供答案 | dt_hstar_005 | `run_pipeline.py:283-292` |

**结论：漏项集中在一类** —— 「怎么用这个仓库的 Python 函数」。
KISS 的 KI 包描述的是**求解器**（输入文件格式、物理边界、失效模式），
不描述**工具链的编程接口**。对 ADCIRC 那种"少数几个 convert_* 工具"的场景够用；
对 HSTAR 这种"skills/ 下 20+ 个互相 import 的脚本"的场景，这是格式的结构性空白。

### 3.5 DEBUGGING PROTOCOL 走了一遍吗

遇到的唯一一次失败是 L1 的 `AttributeError`。按协议：
1. **查三元组** —— 没有匹配项，因为这是**我的脚本**的 bug，不是求解器/deck 的失效。
   三元组体系按设计就不覆盖这类。
2. **读求解器实际拿到的 deck** —— 不适用。
3. **找跑通的样例** —— 有效：直接读 `mesh_io.py` 的 docstring 拿到返回形状。
4. **改工具** —— 改 `run_and_score.py`，一次成功。

协议本身没坏，但**第 1 步在这次是空转的**。这也印证 3.4 的结论：
三元组覆盖"模型知识"失效，不覆盖"工具链集成"失效。

---

## 阶段四 · 结论

### 1. 只靠 KI 包能不能跑通？跑到什么程度？

**能，一次通过，全绿。** 三个层次分别达到：

| 层次 | 达到了吗 | 证据 |
|---|---|---|
| **出结果** | ✅ | 真实 `hstar` 二进制、真实 `1.flavia.res`（DISPLACEMENT / STRESS / NODAL_FORCE 三块、2 个施工步） |
| **结果正确** | ✅（在"物理自洽"这个可判定的层面） | 坝顶 +15.6 mm 下游、沉降 8.3 mm、全局节点力平衡 Σ/量级 ≈ 1e−8 |
| **打分通过** | ✅ PASS，**但必须带一句限定** | `gravdam_static_2block` **没有注册校验器**，PASS 的口径是 `physics_gate` + 本包自写的 7 条物理检查，**不是**与解析解/参考解的比对。`result.json` 里明写 `"validator": null` |

从空目录到 PASS 的全部命令只有两条：`preflight_check.py .` 和 `run_and_score.py . --height 100`。
包内 SKILL.md 的信息足够走完全程，**唯一的实质性回查是漏项 L1**（`mesh_io` 的返回形状），
且那是**建包**时的问题，不是**用包**时的问题。

### 2. 漏项清单里，哪些是「KISS 格式本身没有位置安放」的知识？

**只有一类，但它很重要：工具链的编程接口契约（L1 / L2）。**

KISS 的 KI 包是**围绕求解器**设计的：`inputs[]` 描述求解器吃什么文件、什么单位、
什么格式；`triplets` 描述这些文件填错了会怎样；`processes.modules` 只有三个散文字段。
整套 schema 里**没有一个位置**能放下
"`mesh_io.read_elements()` 返回 `[(eid, [n1..nN]), …]` 而不是 dict"这种事实。

这对 ADCIRC 是合理的 —— 它的 KI 包只有 4 个 `convert_*` 工具，接口窄。
对 HSTAR 不合理 —— `skills/` 下 20+ 个脚本互相 import，
**"知道求解器要什么" 和 "知道怎么调用这个仓库" 是两个规模相当的知识体**，
KISS 只覆盖前者。我在 `identity.toolchain` 下塞了文件路径当权宜之计，
但那放不下签名和返回形状。

顺带暴露一个仓库自身的问题（不是格式的锅）：**结果解析有两份实现**，
`run_pipeline.py` 那份内联在 `main()` 里不可导入，`tools/flavia_to_vtu.py` 那份可导入。
判分脚本只能用后者。

其余漏项（L3/L4/L5）**都放得进** KISS 格式，只是需要先去读源码才写得出来 ——
那是建包成本，不是格式缺陷。

### 3. KISS 格式逼我写下了什么，是现有 `docs/references/` 没有的？

四条，按价值排序：

**a) `boundary.scope_out` —— 明确写下"这个算例族不能算什么"（10 条）**
最有价值的一条是 **"不建模扬压力（uplift）"**。重力坝抗滑稳定验算离不开扬压力，
而这套 conforming 网格共节点、界面上没有压力自由度，**根本算不了**。
这个事实在 `docs/references/` 的任何一篇里都没有写过 —— references 全是
"怎么做 X"，从来没有一处系统地写"X 做不了什么"。
scope_out 是 KISS 格式里**信噪比最高的一段**。

**b) dt_hstar_005 —— 一条真实的、此前无人记录的静默缺陷**
不是从已有文档里搬来的，是被 `inputs[].notes` 那个"这个输入缺失会怎样"的
字段结构问出来的。阶段三的对照实验证明它足够危险：
**水压全丢，坝顶位移差 60 倍，而 `physics_gate` 和经典的符号检查全部通过。**
这一条足以单独证明格式有价值。

**c) 单位约定（dt_hstar_010 / 011）**
HSTAR 的 deck 完全不带量纲，而 `docs/references/` 从未写过这套模板的单位约定。
KISS 的 `inputs[].unit` 是**必填字段**，逼我把 "E 在 Pa、`gamma_w` 是 N/m³ 不是 kg/m³、
坐标是 m、所以位移出来是 m" 这条链写清楚。ADCIRC 那 20 条三元组里前 4 条全是单位错误
——他们踩过同样的坑。

**d) 按信息量排序的验收清单**
SKILL.md 的 "Verification" 段被迫从"最便宜"排到"最有信息量"，
于是暴露出一个此前没意识到的事实：**前 3 条（gate / 符号 / 量级）在 dt_hstar_005 下全部失效**，
真正有鉴别力的是第 4 条"水压边数 > 0"。
不排这个序，就发现不了"我们现有的检查其实挡不住最危险的那个失效"。

### 4. 哪些部分纯粹是开销？

**a) `knowledge_infrastructure.yaml` 和 `workflow/workflow.md` —— 没建，建议永远不建。**
ADCIRC 那两个是 KDT 自动生成的空壳（description 全空、tools 全空、stage 全 TBD）。
它们承载的信息（有哪些 stage、每个 stage 跑什么工具）在 SKILL.md 的 stage 表里
已经有了，而且是有内容的版本。多一份必然腐烂的副本是负收益。

**b) `identity.ki_class` / `boundary.spatial` / `temporal` / `closure`。**
这些字段是为**跨模型编目**设计的 —— HydroCraft 要在一个平台上比较
ADCIRC / VIC / CaMa-Flood，所以需要"这个模型是 2D 还是 3D、亚小时还是日尺度、
守质量还是守能量"这种可排序的元数据。
**HSTAR 项目只有一个求解器，没有比较对象。**
我填了（`spatial: 2-D`、`closure: force equilibrium`），但它们不服务任何查询。

**c) `inputs.forcing` / `inputs.initial_conditions`。**
准静态结构分析没有时间序列驱动、没有初始场。我把 `initial_conditions` 填成
"None + 一句解释"，`forcing` 直接不写。这两类是水文/气象模型的形状。

**d) `processes.modules`。**
HSTAR 是**一个单体 Fortran 二进制**，没有可插拔的物理模块。
我写的三条（Deck generation / Assembly+solve / Result output）是**工具链的阶段**，
不是模型的过程模块 —— 语义上已经跑偏了。ADCIRC 有 GWCE solver、动量方程、
SWAN 耦合等真实模块，这个字段对它有意义。

**e) 13 条三元组里有 8 条是 `error-recovery.md` 的重新编码。**
增量价值在 schema 的三个字段：`severity`（silent/degraded/fatal 的分级）、
`detection_method`（怎么自动检出）、`prevention`（哪个工具的哪个检查守着它）。
`prevention` 这个字段特别好 —— 它逼你把每条知识**接到一个会自动跑的检查上**，
否则就要承认"没有防护"。这与仓库已有的"契约检查棘轮"思路是同一个方向。
但**内容本身**是搬运，不要重复计入收益。

---

### 总评（一句话）

**对 HSTAR 有净收益，但收益集中在两个具体的段落上，不在整套格式上。**

值得吸收的是三样东西，而且**不需要引入 KISS 的目录结构就能吸收**：

1. **`scope_out`**（明写不能算什么）→ 建议加进 `docs/references/` 的每篇 recipe，
   或给 `skills/templates/*.json` 加一个 `_scope_out` 字段。
2. **`severity: silent` 这个分类**，以及配套的 `prevention`（每条静默失效必须
   指向一个会自动跑的检查）→ 建议把 `error-recovery.md` 的 7 条 Pattern
   补上这两个字段，和 `test_skills.py` 的契约检查对齐。
3. **可执行的 preflight + 结构化 result.json** → 这两个脚本本身就能用，
   `run_and_score.py` 的 `water_edges_applied` 检查建议直接进
   `harness/gate.py` 或 `validate_results.py`（它抓到了 `physics_gate` 抓不到的东西）。

不值得引入的是：`knowledge_infrastructure.yaml` / `workflow/workflow.md` 空壳、
跨模型编目字段（`ki_class`/`spatial`/`temporal`/`closure`）、
`processes.modules`、以及 `forcing`/`initial_conditions` 这两类输入分类。

**最该记住的一条实验事实**：满库和无水两个算例，`physics_gate`、坝顶位移符号、
量级、两步施工、组序、全局平衡 —— **六项通用检查全部通过**，
坝顶位移却差 60 倍。**通用门控挡不住"荷载整个丢了"这类失效**，
只有为具体算例族写的、检查"这个荷载真的进了 deck"的那一条能挡住。
这一条与格式无关，但只有在按 KISS 格式逐字段填写时才被逼出来。
