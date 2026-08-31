# KDT-single 实测报告 —— 对 HSTAR 的一次完整解剖尝试

- 被测工具：`lzwei196/KDT-single` @ `631e5c5` ("chore: prune repository to standalone KDT core")
- 工作区：`/tmp/claude-1000/kdt-single`（源码）、`/tmp/claude-1000/kdt-single-out`（产物）
- 被审模型：HSTAR（Fortran 结构有限元求解器，`/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR/`）
- 执行日期：2026-08-26
- 姊妹报告：`kdt-run-report.md`（多 agent 版 KDT，另一路并行），`kdt-trial.md`（上一轮规格审读）

> 本报告边做边写。阶段按 一→五 顺序追加。

---

## 阶段一：最小可跑路径

### 仓库形态

扁平单层，无 `setup.py`/`pyproject.toml`/`requirements.txt`，不是可安装包，只能以脚本方式在仓库根目录调用。

```
auto_dissect.py      14.7 KB   s0–s1 探针编排 + 检查点
cli_agent.py         30.0 KB   agent 运行时 + 验收序列
dissection_spec.py   58.0 KB   FILE 1–11 契约提示词（唯一真正的"规格"）
verify_ki_structure.py 48.4 KB 裁判
ki_vocabulary.py     11.4 KB   三元组字段词表
run_batch.py         21.2 KB   catalog 批量跑
catalog.json         63.1 KB   已知模型清单
analyzers/  stages/  validators/  domain_protocols/  domain_templates/  data_registry/
```

### 一次完整 dissect 的三段边界

README 自己划了三条界（`README.md:69-75`），代码核对属实：

| 段 | 入口 | 做什么 | 需要 LLM？ |
|---|---|---|---|
| Probe | `auto_dissect.py` | `s0_acquire`（clone/copy 源码、探测语言/构建系统/文档/示例）→ `s1_pipeline_map`（扫 I/O、解析文档、套域模板） | 否，纯 Python |
| Build | `cli_agent.py::spawn_cli_agent` | 用 `dissection_spec.build_dissection_prompt()` 生成巨型提示词，`subprocess.run(['claude','-p',prompt,...])` 起一个 CLI agent 写出候选 KI | 是 |
| Accept | `cli_agent.py::_accept_dissected_ki` | 跑 3 个 projector → 调 `verify_ki_structure.verify()` → 写 `ki_gen_accept.json` → 通过则 git commit | 否 |

`STAGES` 列表只有两项（`auto_dissect.py:41-44`），所以 `--to-stage 2` 就是全部探针。README 里 s0–s9 那种"九个阶段"是**提示词里让 agent 自己做的事**，不是 Python 流水线阶段。这点容易误读。

### CLI 参数清单

`auto_dissect.py`（`parse_args`, 行 329-349）：

```
--url URL              要 clone 的 GitHub 地址
--source PATH          本地源码目录（与 --url 二选一）
--name NAME            模型名（single 模式必填）
--domain DOMAIN        域，默认 hydrology
--output PATH          KI 输出目录
--work-dir PATH        工作目录，默认 /mnt/disk1/Hydrocraft_server/models/<name>/runs
--resume PATH          从 work dir 恢复
--from-stage N / --to-stage N
--batch --catalog FILE --output-root PATH
--max-probe-parallel N (8) --max-cli-parallel N (1) --cli-timeout S (3600)
--probe-only
```

`cli_agent.py`（行 624-635）：`--model --work-dir --output-dir --resume <session_id> --timeout --batch --models --max-parallel`

`verify_ki_structure.py`：`<ki_dir> [--json]`

### gate 在哪一步介入 —— 以及它在本机注定失败的地方

`cli_agent.py:394-396` 三个硬编码常量：

```python
_KI_TOOLS_COMMON = "/mnt/disk1/Hydrocraft_server/models/ki_tools_common/ki_tools_common"
_PINNED_PY       = "/mnt/disk1/Hydrocraft_server/python_env/bin/python"
_MODELS_GIT      = "/mnt/disk1/Hydrocraft_server/models"
```

验收序列（`_accept_dissected_ki`, 行 421-429）先用 `_PINNED_PY` 跑
`generate_format_spec.py` / `generate_ki_manifest.py` / `generate_skill_map.py`。
**这三个 projector 脚本不在本仓库里** —— 它们住在 `ki_tools_common`，KDT-single 没有携带。
在任何非 HydroCraft 服务器上，这三步必然抛异常进 `proj_fails`，于是 `failures` 非空，
于是 `verdict = fail`，于是 `status = ki_incomplete`。README 行 223 把这点写明了
（"missing projectors produce `ki_incomplete` instead of a false pass"），这是**诚实的 fail-closed**，
但也意味着**在本机 KDT-single 的完整验收链路无法给出 pass，除非补齐或短路 projector**。

这是本次实验的第一个必然绕过点，记在阶段三的绕过表里。

值得记一笔的正面设计（`cli_agent.py:436-445`）：gate 报告本身被当作不可信输入校验 ——
`ok` 不是 bool、`failures` 不是 list、`ok=True` 却带 failures、`ok=False` 却空 failures，
四种情况都判 `gate_error`。这是真正的 fail-closed 写法。

---

## 阶段二：★ 域可插拔性

这一节是本次最有价值的发现，先给结论：

> **`domain_protocols/` 在 KDT-single 里是死文件 —— 没有任何一行 Python 读它。**
> 真正影响运行的只有 `domain_templates/`，而它 10 个文件里有 9 个是 10 行的空壳。
> 域未匹配时**不 fail closed，而是静默回落到 hydrology 模板**。

### 1. 两套"域"文件的 schema

**`domain_protocols/*.yaml`（23 个文件，每个 200–370 行）** —— 内容极其丰富，是从已解剖的
KI 里蒸馏出来的领域知识库。以 `groundwater.yaml` 为例，顶层 schema：

```yaml
domain: groundwater
description: >
typical_stages:            # s0_config … s9_validation，每个带 inputs/tools_needed/depends_on/
                           # discretisation_types/data_sources/package_taxonomy/notes
key_parameters:            # 按 category 分组：members / typical_units / physical_range /
                           # where_derived / trap / applies_to / references
validation:
  preferred: [{type: analytic|real, name, description, use_when}]
  required_metrics: [...]
  thresholds: {minimum/good/excellent: {...}}
  figure: "..."
common_traps:              # 自由文本条目，按 单位/几何/求解器/属性/边界/输运/耦合 分节
```

配套 `*.references.md` 给出每个已解剖模型的文档地标、自带算例、文献。
这套东西的信息密度很高 —— 比如 `groundwater.yaml:270` "K units: m/d (MODFLOW), m/s (PFLOTRAN)
— factor 86400 silent error"，`:189` "DRN conductance vs DRN K confusion — conductance = K × A / L"。
这是真正的领域 know-how。

**`domain_templates/*.yaml`（10 个文件）** —— schema 极简：

```yaml
domain: <name>
typical_stages:
  - {id: sN_xxx, name: "..."}      # 可选 description/data_sources/tools_needed/depends_on/
                                   # parallel_with/critical_units
```

行数说明一切：
```
hydrology.yaml       85 行   ← 唯一写实的
atmospheric/biogeochemistry/crop/geomorphology/glacier/
groundwater/lake/ocean/water_quality   各 10 行  ← 7 个通用阶段名的占位符
```

### 2. 谁在读它们

```
$ grep -rn "domain_protocols\|domain_templates\|protocols" --include=*.py .
stages/s1_pipeline_map.py:20:    template_dir = Path(__file__).parent.parent / 'domain_templates'
```

**唯一一处。** `domain_protocols/` 的 23 个文件、约 5000 行精炼领域知识，在 KDT-single 里
**完全没有被加载、没有进提示词、没有进 gate**。它们大概率是从多 agent 版 KDT 剪枝时一起
拷过来但对应的读取代码没拷（`631e5c5 chore: prune repository to standalone KDT core`）。

这直接改变了对"域可插拔性"的评估：**要接一个新域，真正需要写的不是那份 300 行的
protocol，而是那份 10 行的 template** —— 因为只有后者被消费。而写 protocol 目前是无效功。

### 3. 域不匹配时的行为：fail-open

`stages/s1_pipeline_map.py:18-27`：

```python
def load_domain_template(domain):
    template_file = template_dir / f'{domain}.yaml'
    if template_file.exists():
        with open(template_file) as f:
            return yaml.safe_load(f)
    # Fallback to generic hydrology template
    with open(template_dir / 'hydrology.yaml') as f:
        return yaml.safe_load(f)
```

传 `--domain structural_fem` 而没有对应模板 → **静默拿到 hydrology 的 85 行模板**，
里面是"土壤参数 / 植被覆盖 / 气象强迫 / HWSD / AVHRR / CMFD"。没有警告、没有日志、
没有非零退出。生成的 `pipeline` 会带着一串对结构 FEM 毫无意义的阶段名往下游走，
最终进入 agent 提示词。

这是本次审查里最实在的一个缺陷：**注释写着 "Fallback to generic hydrology template"，
但 hydrology 模板不是 generic 的，它是 hydrology 专用的。** 真正的通用回落应当是
那 10 行的占位 schema（config/domain/data/forcing/parameters/run/output），
而不是 85 行的水文特化版。

另有一处 fail-open：`dissection_spec.py:438` → `_build_phase4_instructions(domain, ...)`，
未知域走 `else` 分支（`:336-379`）。这一支写得**反而是好的** —— 它不假设任何数据集，
要求 agent 用模型自带的 test case / 已发表 benchmark，并强制诚实分级
`real / analytic / synthetic / stub`，明确写着 "NEVER set tier = 'real' unless you used
actual independent observations"。结构 FEM 落到这一支是合适的。

### 4. 能不能加一个 `structural_fem`？

**能，而且成本很低。** 需要动的地方按影响排序：

| 要改的 | 必需？ | 工作量 | 说明 |
|---|---|---|---|
| `domain_templates/structural_fem.yaml` | **必需** | ~40 行 | 唯一被真正消费的域文件。不加就静默拿 hydrology |
| `dissection_spec.py::_build_phase4_instructions` | 否 | 0 | 落 `else` 通用分支即可，且该分支适配良好 |
| `cli_agent.py::_load_data_registry_for_domain` | 否 | 0 | `data_registry/server_datasets.yaml` 按 `applicable_domains` 过滤，无匹配返回空串，提示词里写 "No domain-specific data registered. Use built-in examples or published benchmarks."（`dissection_spec.py:538`）—— 干净的 fail-open |
| `domain_protocols/structural_fem.yaml` | 否（当前无效） | ~300 行 | 写了也没人读。除非同时补读取代码 |
| `ki_vocabulary.py::OBS_MAP_VOCAB["medium"]` | **视 gate 而定** | 1 行 | 见下 |

**对结构 FEM 根本没有对应物的字段：**

1. **`medium`（介质）** —— `ki_vocabulary.py:99-102` 是一个明确声明的**封闭词表**：
   `water | soil | air | ocean | ice | snow | vegetation | sediment | groundwater | bedrock |
   urban_network | organism | not_a_medium`。13 个词，12 个是地学介质。结构 FEM 的
   "混凝土 / 钢筋 / 岩基 / 接触面"一个都没有。注释明写 "Closed vocabulary: an open field
   drifts back into free text and stops being checkable" —— 设计上就是不欢迎外来域的。
   好消息：存在 `not_a_medium` 逃生门，且它就是个 Python dict，加 `concrete`/`steel`/`rock_mass`
   是一行的事（`ki_vocabulary.py:99`）。这是**可扩展的硬编码**，不是不可扩展的硬编码。

2. **`comparing_variable` / 观测量绑定** —— 整套 obs-map 假设"模型输出 vs 独立实测时间序列"
   （站点流量、土壤湿度、GRACE TWS）。结构 FEM 的对照物是**解析解 / 规范算例 / 另一个求解器**，
   本质是 code-to-code 或 code-to-analytic verification，不是 observation validation。
   `validation_tier` 里的 `analytic` 档能容纳它，但 `rank: 1 = the quantity this model is
   judged on` 这种"单一被判定量"的假设，对一个同时给位移/应力/渗流水头/温度的多物理场求解器
   是别扭的。

3. **`data_registry`（服务器数据集清单）** —— 全是 CMFD/MSWX/HWSD/AVHRR/GRDC/GRACE 这类
   地学再分析与遥感数据。结构 FEM 的等价物是"算例库"（本仓库的 `cases/cases/train*`），
   语义完全不同：不是"外部观测数据"，而是"带参考解的自包含输入包"。schema 上勉强能塞进
   `additional_datasets`，但 `applicable_domains` 之外的字段（`period` / `resolution` /
   `variables`+`unit`）全部空转。

4. **`validation.thresholds`（NSE/KGE/PBIAS/RMSE_head_m）** —— 时序拟合优度指标。
   结构 FEM 用的是相对误差百分比、能量范数、网格收敛率（Richardson 外推）。
   `domain_protocols` 的 schema 能表达（`required_metrics` + `thresholds` 是自由 key），
   但既然没人读，不构成阻碍。

**结论（域可插拔性）：** 这套**方法论**（探针 → 契约 → 单 agent 构建 → 确定性 gate；
三元组诊断知识；派生文件必须投影；受控词表）是**域中立**的，没有任何一条依赖地球科学。
但这套**实现**是地学专用的：域知识的载体（protocols）已经断线，唯一活着的载体（templates）
只有水文一份写实，词表的 `medium` 是封闭地学列表，数据注册表全是地学数据集，
未匹配时回落到水文而不是通用。

接一个 `structural_fem` 的真实成本 ≈ 一个 40 行 YAML + 一行词表 + （若要复现其
"领域知识蒸馏"的价值）一份 300 行 protocol **外加自己补上读取它的代码**。
前两项是配置，第三项是给上游提 PR 的活。

### 5. 实测：域回落是真的（证据）

**实验 A —— 不给模板，直接传 `--domain structural_fem`：**

```bash
$ python3 auto_dissect.py --source /home/huijun/HSTAR_Next/hstarYLOrig/HSTAR \
    --name HSTAR --domain structural_fem \
    --work-dir /tmp/claude-1000/kdt-single-out/work \
    --output /tmp/claude-1000/kdt-single-out/ki --to-stage 2
  [0] s0_acquire: COMPLETED (2.5s)
  [1] s1_pipeline_map: COMPLETED (0.2s)
```

零报错、零警告、两个阶段全绿。生成的 `ki/workflow/workflow.md`
（存档：`/tmp/claude-1000/kdt-single-out/evidence/workflow_hydrology_fallback.md`）：

```
### Stage 2: Soil Parameters (`s2_soil`)
- **Description**: Derive soil hydraulic properties from HWSD or SoilGrids
### Stage 3: Vegetation / Land Cover (`s3_vegetation`)
- **Description**: Classify land cover from AVHRR into model vegetation classes
### Stage 4: Meteorological Forcing (`s4_forcing`)
- **Description**: Convert CMFD/MSWX/NASA POWER to model forcing format
### Stage 8: River Routing (optional)
```

一个 Fortran 结构有限元求解器，被派了"从 HWSD 推导土壤水力性质""用 AVHRR 分类植被覆盖"
"转换 CMFD 气象强迫""河道汇流"四个阶段。**这份 YAML 会原封不动进入 agent 提示词
（`dissection_spec.py:417-419` 读 `work/ki/knowledge_infrastructure.yaml` 前 3000 字符）。**
这不是理论缺陷，是实测到的污染。

**实验 B —— 补一个 `domain_templates/structural_fem.yaml`（40 行，schema 照抄 hydrology.yaml）：**

```
Analysis Configuration / Mesh · Domain Definition / Material Assignment /
Boundary Conditions / Loads / Load Steps · Construction Stages /
Solver Execution / Result Extraction / Verification / Reporting
```

**改 Python 代码 0 行。** 域插拔在"模板"这一层是真的可插拔，成本就是一个 YAML 文件。
这是本次实验里对 KDT 最有利的一条结论。

---

## 阶段四：裁判

### 裁判能独立跑，且 fail-closed 做得扎实

`verify_ki_structure.py <ki_dir> --json` 不依赖 HydroCraft 服务器就能跑。判我们手搭的
`kiss-trial-pkg/`（199 行 SKILL.md + 238 行 dag.yaml + 379 行 triplets + 415 行 preflight
+ 280 行 run_and_score，全人工撰写）：

```
ok: false   —— 13 条 failure
  1  SKILL.md body lacks a 'output description' section (template §6/§8/§11)
  2  SKILL.md body lacks a 'validated results' section
  3  SKILL.md body lacks a 'unit table' section
  4  SKILL.md has no KI-map section
  5  tools/: 0 python tools, need >= 1 (FILE 2)
  6  docs/: 0 STAGE skill docs (s1_*.md …), floor is 3 (FILE 3)
  7  diagnostics/triplets.yaml has 13 entries, s5 requires >= 15
  8  knowledge_infrastructure.yaml missing (FILE 5)
  9  preflight_check.py does not emit the PREFLIGHT_REPORT= contract line (FILE 6)
 10  docs/format_spec.yaml missing (FILE 6)
 11  docs/gathered_papers.json missing — REQUIRED
 12  docs/validation_convention.yaml missing (warning)
 13  FILE5/6 content check CRASHED (ModuleNotFoundError: ki_projection_common)
     — "a check that cannot run is not a check that passed"
```

第 13 条值得单独表扬：外部依赖缺失导致检查无法执行时，它**记为 failure 而不是跳过**。
这和 `cli_agent.py:436-445` 的四条报告自洽性校验是同一种工程品味 —— 全仓库最好的部分。

（顺带：`ki_projection_common` 是继 `ki_tools_common` 之后**第二个**未随包发布的外部依赖。
KDT-single 自称 "self-contained"，实际上有两个必需的外部 Python 包缺失。）

### 上一轮发现的"不可失败路径"在 KDT-single 里依然存在

`verify_ki_structure.py:454-463`：

```python
_outs = (_dag.get("outputs") or []) if isinstance(_dag, dict) else []
_obs  = [o for o in _outs if ... .get("comparable_obs_shapes")]
if _outs and not _obs:
    fails.append("dag.yaml has N outputs but NONE carries an observability... block")
```

直接构造三个最小 KI 探测：

| dag.yaml 内容 | `n_dag_outputs` | dag 相关 failure |
|---|---|---|
| `outputs:` 有 1 项，无 observability | 1 | **1 条**（正确失败） |
| **`outputs` 键完全缺失** | 0 | **0 条** |
| `outputs: []` | 0 | **0 条** |

`if _outs and not _obs` 的左操作数为空时整条检查蒸发。下游的 MEDIUM 规则
（`:474` `if ... and info.get("n_observable_outputs")`）同样被 0 短路。
**结果：一个连 `outputs` 都不写的 dag.yaml，比一个写了 outputs 但漏了 observability
的 dag.yaml 更容易过 gate。**"少写一点反而更容易通过"是 gate 设计里最典型的反向激励。

这条在手搭包上是活的、不是理论上的：`kiss-trial-pkg/dag.yaml` 用的是 KISS 3.5 schema
（顶层键 `identity / boundary / inputs / processes / safety`），根本没有 `outputs`，
于是那 13 条 failure 里**一条 dag 内容检查都没有** —— gate 只抱怨了周边文件，
对这份 dag 的实质内容一个字都没审。

### `_MEDIA` —— 38 个词，一个力学词都没有

`verify_ki_structure.py:467-472` 是一个裸元组（不可配置、不读任何 YAML）：

```
water lake river stream ocean sea marine soil land air atmospher ice snow glacier
vegetation canopy crop plant forest groundwater aquifer sediment bed urban sewer
pipe channel catchment basin hillslope wave fire surface subsurface ecosystem
biomass phytoplankton
```

38 个词，全部地学。结构 FEM 的介质（混凝土 / 钢筋 / 岩体 / 接触面 / 结构 / 坝体 / 基础）
一个都不在里面。后果不是"报错"，而是更糟的**误判**：
- `surface_displacement` 因为含 `surface` 而通过 —— 通过的理由和它想检查的语义无关；
- `crest_settlement`（坝顶沉降）因为不含任何词而失败 —— 失败的理由不是描述含糊。

也就是说这条检查对非地学域**既会假阳也会假阴**。它是全仓库唯一一处域知识被硬编码进
**裁判**（而非配置）的地方，也是"这套东西跳出地球科学"最实在的一处摩擦点。
修法很轻（元组加词 / 改读 YAML），但必须动 gate 源码。

---

## 阶段三：真跑一次 dissection

### 实际执行的命令

```bash
# 1. 探针（无 LLM）
python3 auto_dissect.py \
  --source /home/huijun/HSTAR_Next/hstarYLOrig/HSTAR --name HSTAR \
  --domain structural_fem \
  --work-dir /tmp/claude-1000/kdt-single-out/work \
  --output   /tmp/claude-1000/kdt-single-out/ki --to-stage 2

# 2. 单 agent 构建 + 验收（本机 claude CLI 2.1.243 作 builder）
python3 cli_agent.py --model HSTAR \
  --work-dir  /tmp/claude-1000/kdt-single-out/work \
  --output-dir /tmp/claude-1000/kdt-single-out/ki --timeout 5400
```

### s0 探针的实测表现

```
build_system:     unknown        ← 有 hstar.vfproj（Visual Studio Fortran 工程），未识别
primary_language: fortran        ← 正确
file_census:      918 files;  .th 160 · .aux 103 · .mod 103 · .obj 82 · .f90 28
documentation:    readme=None, doc_dirs=[], example_dirs=[], test_dirs=[]
                  manual_files 里混进了 vtune 的 .trace.0.aux
has_examples: False   has_tests: False   has_readme: False
config_formats:   ['ini', 'xml']
```

评价：语言判对了，其余基本失灵。它把整棵源码树（含 `vtune_hotspot_sw_omp8/` 的
性能采集数据、`.obj`/`.mod` 构建残留、`Debug/`/`Release/`）当作模型源码复制并统计，
918 个文件里只有 28 个是 `.f90`。`build_detector` 认识 CMake/Make/setup.py 这类，
不认识 `.vfproj`。`doc_parser` 在没有 README 的仓库上抽出 0 条 workflow 步骤
（`doc_steps_found: 0`），于是 `merge_doc_steps_with_template` 完全退化成"照抄域模板"。

**这是一个诚实的负面结果：KDT 的确定性探针对"没有 README、没有 CMake、没有 examples/
的私有 Fortran 代码库"几乎提取不到信息。** 它对 GitHub 上有完整 README 的开源地学模型
（catalog.json 里那批）才是好用的。HSTAR 恰好是最不利的输入形态。

### 绕过点记录表

| # | 绕过了什么 | 原因 | 改了什么 | 是否影响结论 |
|---|---|---|---|---|
| 1 | `--work-dir` / `--output` 不用默认值 | 默认写死 `/mnt/disk1/Hydrocraft_server/models/<name>/` | 命令行显式传路径（工具本身支持的参数） | 否。这是设计好的参数，不算改代码 |
| 2 | 新增 `domain_templates/structural_fem.yaml` | 不加就静默拿 hydrology 模板 | 新建 40 行 YAML，**未改任何 .py** | 否，且这本身是阶段二实验的一部分。原始污染产物已存档对照 |
| 3 | 三个 projector（`generate_format_spec.py` / `generate_ki_manifest.py` / `generate_skill_map.py`） | 住在未随包发布的 `ki_tools_common`，`_PINNED_PY` 指向不存在的解释器 | **未绕过** —— 让它按设计失败，观察真实 verdict | **是，且是关键**：这意味着本机的完整验收链路必然 `ki_incomplete`。gate 本体的判定仍然有效（可独立运行） |
| 4 | `ki_projection_common`（gate 内 FILE5/6 内容检查的依赖） | 同上，未随包发布 | 未绕过 | 是。gate 自己把它记为 failure（"a check that cannot run is not a check that passed"），行为正确 |
| 5 | `claude` CLI 权限 | —— | **无需绕过**。`claude -p --allowedTools 'Read,Write,Edit,Bash,Glob,Grep'` 冒烟测试直接通过，未使用 `--dangerously-skip-permissions` | 否 |

关于 #3 的公平性：把 projector 短路掉（比如把 `_PINNED_PY` 改成 `sys.executable`、
把三个脚本 stub 成 no-op）能让流程跑到底，但那样得到的 "pass" 是我伪造的，
而且会跳过"派生文件必须从权威源投影"这条 KDT 的核心规则 —— 那正是它区别于
"agent 说写完了就算完"的地方。**伪造这一步会毁掉整个实验的意义**，所以不做。
代价是本机拿不到 `gate: pass`，只能分别评估「gate 本体的判定」与「产物本身的质量」。

### 提示词本体：41,405 字符，16 处指向不存在的路径

`build_dissection_prompt('HSTAR', ...)` 产出 41.4 KB 提示词（存档
`/tmp/claude-1000/kdt-single-out/prompt_preview.md`）。里面把 FILE 1–11 契约、
受控词表、四阶段流程讲得非常细致 —— 这份提示词本身是整个仓库最有价值的资产。

但它对 agent 下达的指令里有 16 处 HydroCraft 专属路径：

```
4×  /home/server/knowledge-dissection-toolkit          ← 含 ki_dag_generator、SKILL_TEMPLATE.md、
                                                          preflight_check_template.py、paper_cache
5×  /mnt/disk1/Hydrocraft_server/models/ki_tools_common/…/generate_*.py
2×  /mnt/disk1/Hydrocraft_server/python_env/bin/python
1×  /mnt/disk1/Hydrocraft_server/hydrocraft.db          ← FILE 8 让 agent 查 sqlite 确认 dag 落库
1×  /mnt/disk1/Hydrocraft_server/data_ki/               ← "LAYER 0: 41 个 Data KI"
1×  /mnt/disk1/Hydrocraft_server/models/GLM/knowledge_infrastructure/  ← 参考样例
2×  /media/server/hc_ssd/forcing/…                      ← CMFD 强迫数据
```

其中三处是**硬指令**而非可选参考：

- FILE 1 让 agent 从 `kdt-release/templates/SKILL_TEMPLATE.md` 抄结构；
- FILE 7 让 agent 从 `templates/preflight_check_template.py` 抄；
- FILE 8 明写 **"GENERATE IT with the dag generator — do NOT hand-write it"**，
  然后给 `cd /home/server/knowledge-dissection-toolkit && python -m ki_dag_generator`。

本仓库根本没有 `templates/` 目录（只有 `domain_templates/`），也没有 `ki_dag_generator`。
所以 **README 的 "The orchestration, prompt, vocabulary, and gate are local to this repository"
这句是不准确的**：prompt 是本地的，但 prompt 命令 agent 去用的三个模板/生成器全在仓库外，
加上 `ki_tools_common`（projector）和 `ki_projection_common`（gate 内部检查），
一共 **5 个必需外部件缺失**。在非 HydroCraft 机器上，agent 只能靠自己"猜"这些模板长什么样。

这是评估这次跑出来的产物时必须记住的背景：**它是在缺 5 个规格锚点的情况下生成的**，
拿它去和 gate 的完整规格比对，天然不公平。下面阶段四会把"因缺件而失败"和
"因内容不对而失败"分开算。

### 实跑结果：`ki_incomplete`，8 条 failure，耗时 50 分钟

```
Prompt: 41405 chars | Timeout: 5400s
[HSTAR] CLI exited 0 but the KI FAILS acceptance (8 problem(s)) — recorded as ki_incomplete
duration_s: 3016.2   exit_code: 0   gate: fail
```

8 条 failure 按性质拆开（这是关键，不拆就会把环境问题记成质量问题）：

| # | failure | 性质 |
|---|---|---|
| 1-3 | `generate_format_spec/ki_manifest/skill_map.py: FileNotFoundError '/mnt/disk1/…/python'` | **环境**（缺件） |
| 4 | `FILE5/6 content check CRASHED (ModuleNotFoundError: ki_projection_common)` | **环境**（缺件） |
| 5 | `SKILL.md body lacks a 'unit table' section` | **gate 误判**，见下 |
| 6 | `dag.yaml: 2 observable output(s) … does not name a MEDIUM: ['None','None']` | **半误判**，见下 |
| 7 | `preflight execution check CRASHED (AttributeError)` | **产物真实缺陷**（但由缺件诱发） |
| 8 | `docs/validation_convention.yaml has no 'validation:' blocks` | **产物真实缺陷** |

也就是说：**8 条里只有 2 条是产物本身写错了，4 条是环境缺件，2 条是 gate 自己的问题。**

单独跑裁判（`verify_ki_structure.py <ki> --json`，绕开 projector）：**5 条 failure**。

```
n_tools: 21    n_docs: 12   n_stage_docs: 10   n_papers: 23
n_triplets: 32 (list)       n_dag_outputs: 15  n_observable_outputs: 8
```

### gate 的两条误判（都可复现）

**误判 A —— "unit table" 是标题字面匹配。** `verify_ki_structure.py:142-148`：

```python
for _sec, _pat in (("output description", r"output description|outputs"),
                   ("validated results",  r"validated results|validation status|performance metrics"),
                   ("unit table",         r"unit conversion|unit table|sign convention")):
    if not _re2.search(_pat, _heads):     # _heads = 只有 markdown 标题行
        fails.append(f"SKILL.md body lacks a '{_sec}' section")
```

生成的 `SKILL.md:283` 标题是 `## 8. Units`，下面是一张 11 行、逐条注明出处的单位表：

| quantity | unit | verified from |
|---|---|---|
| E, stress, pressure, cohesion | **Pa** | `1.mat` `2.500E+10` |
| unit weight γw | N/m³ (`9810`) | edge-load `fact` |
| thermal diffusivity | **m²/day** | thermal manual §5 |
| time step `ditime` | s for dynamics, **days** for thermal/creep/staging | thermal manual §4 |

内容完全正确（与本仓库已知事实一致），只因标题写的是 "Units" 而不是 "Unit table"
就被判 FAIL。**这条 failure 与 KI 质量无关。**

**误判 B —— MEDIUM 检查读错了键，而且是子串匹配。**
报文里的 `['None','None']` 暴露了 bug：gate 读 `_o.get("var")`（`:487`），
而 agent 按 FILE 8 模板写的是 `name:`。所以 gate 连出问题的变量叫什么都报不出来。

更要命的是**它凭什么放过另外 6 个**。把 `_MEDIA` 那 38 个词逐个回放到这 8 个可观测输出上：

| output | 判定 | 命中的词 | 实际含义 |
|---|---|---|---|
| `displacement_field` | PASS | `soil` | "rock or soil skeleton" — 勉强算对 |
| `stress_field` | PASS | `soil` | 同上 |
| `temperature_field` | PASS | **`pipe`** | 来自 "hydration heat and **pipe** cooling"（混凝土冷却水管）。`_MEDIA` 里的 `pipe` 指的是城市排水管网 |
| `pore_pressure_field` | PASS | `water` | 对 |
| `natural_frequency` | PASS | `water` | 来自附加质量描述，与"介质"无关 |
| `safety_factor` | PASS | **`sea`** | 来自 "limit-state **sea**rch" —— **`search` 里的 `sea`** |
| `joint_relative_displacement` | FAIL | — | 描述其实很清楚，只是没含地学词 |
| `support_reaction` | FAIL | — | 同上 |

`safety_factor` 因为 "search" 里含 "sea" 而被判定"命名了介质：海洋"。
这是纯子串匹配、无词边界的后果，**而且这个 bug 不分域** ——
任何 KI 只要描述里出现 research / seasonal / bedrock / island，都会白捡一个 PASS。

结论：这条 gate 检查对结构 FEM 域的 8 个输出里，**2 个正确、4 个蒙对、2 个冤枉**。
它没有在测它声称要测的东西。

### 误判 C（轻）—— KI 报文格式错被记成"gate 崩溃"

failure #7 的真实成因：生成的 `preflight_check.py` 输出
`PREFLIGHT_REPORT=[{...}, {...}]`（裸列表），而 gate 期望
`{"checks": [...]}`，于是 `_rep.get("checks")` 在 list 上抛 `AttributeError`
（`verify_ki_structure.py:643`）。

这**是产物的错**（schema 不对），但 gate 把它报成 "preflight execution check CRASHED —
a check that cannot run is not a check that passed"，指向了自己而不是 KI。
诊断信息误导。而且这个 schema 之所以猜错，正是因为
`templates/preflight_check_template.py` 不在这台机器上（缺件 #2）——
agent 没有可抄的规格。

### 与手搭包的 FAIL 清单对比

| | 自动生成 KI | 手搭 `kiss-trial-pkg` |
|---|---|---|
| gate failures（独立跑） | **5** | **13** |
| tools | 21 | 0 |
| docs / stage docs | 12 / 10 | 0 / 0 |
| triplets | **32**（14 条 severity=silent，32 条全有 detection） | 13 |
| dag outputs / observable | 15 / 8 | **0 / 0**（KISS schema 无 `outputs` 键） |
| gathered papers | 23 | 0 |
| preflight | 有，能跑，报文 schema 错 | 有，legacy 格式 |
| format_spec / validation_convention | 有（convention 是空壳） | 无 |

两份 FAIL 清单的差集说明了一件事：**手搭包的 13 条失败几乎全是"文件不存在"
（tools/ 空、docs/ 空、manifest 缺、format_spec 缺、papers 缺），
自动生成 KI 的 5 条失败已经推进到"文件存在但内容/格式不对"这一层。**
按 KDT 自己的规格衡量，机器生成的包比人手搭的包完整得多 —— 这个结论必须诚实地记下来。

但要加一条重要的注脚：`kiss-trial-pkg` 从来不是照 KDT 的 FILE 1–11 规格写的，
它是 KISS 3.5 格式的实验品。**拿 KDT 的裁判去判它，本来就是判一个没参加这场考试的人。**
它 13 条 failure 里没有一条是 dag 内容检查（因为 KISS schema 没有 `outputs` 键，
整段检查被上文那条"不可失败路径"跳过了）—— 这恰恰说明那条短路有多严重。

---

## 阶段五：结论

### 1. 跑通到什么程度

| 环节 | 结果 |
|---|---|
| 探针 s0–s1 | ✅ 跑通，零改动。但对 HSTAR 这种无 README / 无 CMake / 无 examples 的私有仓库几乎提取不到信息 |
| 单 agent 构建 | ✅ 跑通，50 分钟，exit 0，产出 21 个工具 + 12 篇文档 + 32 条三元组 + 15 输出 dag + 23 篇文献 + 一套可运行模板算例 |
| 验收 projector | ❌ 无法运行（缺 `ki_tools_common`），设计上就会导致 `ki_incomplete` |
| gate | ✅ 能独立跑，判出 5 条 failure（其中 2 条是 gate 自己误判） |
| 总 verdict | **`ki_incomplete`** —— 在本机拿不到 pass，且不是因为产物差 |

**"有产物 / 过 gate / 产物内容真的对"三档里：产物有，且很实；gate 没过，
但过不了的主因是环境缺件和 gate 自身缺陷；内容对不对见下。**

超出预期的部分（这是本次最意外的发现）：agent 不满足于读代码，它

1. **真的把 HSTAR 在 Linux 上编译出来了。** `work/bin/hstar`（7.76 MB，本机 md5
   `c05bc962…`，与仓库内 Windows 构建的 `x64/Release/hstar` md5 `20d8588e…` 不同），
   用 Intel ifx 2025.3 + oneMKL 2026.0，按 `hstar.vfproj` 复原链接行，
   17 个编译单元按 use-graph 顺序编译，并为 Windows-only 的 `gidpost.lib`
   写了一个 C stub 顶替。`work/build/` 里有全部 `.o` / `.mod`。
2. **真的用这个二进制跑了验证。** 两个解析解算例 + 一个四级网格收敛研究
   （`conv_4/8/16/32`）：
   - 一维受限自重柱（confined column）：NSE = 1.0，PBIAS = 8.4e-15；
     **整体平衡校核** 反力和 235417 N vs 施加荷载 235440 N，相对残差 9.8e-5（容差 1e-4）
   - Lamé 厚壁圆筒内压：NSE = 0.9989，KGE = 0.9914，PBIAS = −0.40%
   - 求解健康度：力残差比 4.0e-15、位移残差比 8.4e-15
3. **诚实分级。** `validation_tier: "analytic"`，理由写着
   "No independent observed data was used, so this is NOT 'real'"。没有把解析解冒充观测。
4. **主动补上缺失的裁判。** 找不到 gate，它自己写了个
   `work/verify_ki_structure_standin.py` 并在 stage_log 里注明
   "PASS (stand-in verifier; the toolkit gate … is not installed on this host)"。

第 4 点要双面看：披露是诚实的，但"agent 自己写裁判自己判自己 PASS"正是
KDT 设立 gate 要防的事。**而 gate 确实防住了** —— 真 gate 判出 5 条 failure，
stand-in 判 PASS。这一次算是 KDT 的核心主张（"the agent builds; the gate judges;
a clean process exit is never proof"）在真实场景下被验证了一回。

### 2. ★ 生成的 KI 质量 —— 抽查（最重要的一节）

**抽查 A：`type_problem` 映射 —— KI 对，我们自己的文档不够准。**

生成的 `SKILL.md:157-161` / `docs/input_preparation.md:196`：

```
Q 静力  ·  S 时变/固结  ·  F 瞬态动力  ·  E 反应谱  ·  W 模态/频率
```

我们自己的 `fem-chat/CLAUDE.md`（标注"human-confirmed · highest priority"）写的是
`Q 静力 / E 模态 / F 动力 / S 瞬态`，**没有 W**。查源码 `Fem.f90:1933-1944`：

```fortran
if (type_problem/='Q'.and.type_problem/='E'.and.type_problem/='W') then
    call modf_time_order; ... call time_dependent
elseif(type_problem=='E') then
    call response_spectrum
endif
if(type_problem=='W') call frequency_analysis   !freq2006
```

**源码站在 KI 这边：`E` → `response_spectrum`，`W` → `frequency_analysis`。**
我们的工具链把模态当 `E` 跑是能work的 —— 因为 `response_spectrum` 内部也做特征值提取，
`Fem.f90:10394` 那行 format 正是 `run_pipeline.py:629` 的 `parse_modal_chk` 在读的
`order= omega= freq= period=`。但严格讲 `E` 是反应谱、`W` 才是纯模态，
而我们的文档把这个区分抹掉了、也完全不知道有 `W` 这条路径。

**这条抽查的结论是反直觉的：自动生成的 KI 在这一点上比我们人工维护了几个月的
CLAUDE.md 更准确。** 它不是在编，是真的把 dispatcher 读了。

**抽查 B：`dt_001`（运行方式）—— 逐字核对属实。**

> diagnosis: `Fem.f90:96-101` shows the `CALL GETARG` block commented out. The only run
> selector is the file `inp` in the CURRENT WORKING DIRECTORY: record 4 is the problem-name
> prefix and record 5 is `runblks`.

核对 `Fem.f90:92-103`：

```fortran
open(inpunit,file='inp')
read (inpunit,*) text            ! rec 1
read (inpunit,*) restart,relis,sysrelis,ADINA,Uopt_R,gamamax   ! rec 2
read (inpunit,*) text            ! rec 3
read (inpunit,*) probn           ! rec 4  ← 问题名，正如它所说
!CALL GETARG (1, probn,mystatus(1))     ← 全部注释掉，正如它所说
!CALL GETARG (2, t2,mystatus(2))
!CALL GETARG (3, t3,mystatus(3))
```

行号差 3（它说 96-101，实际 99-103），**事实完全正确**。

**抽查 C：`dt_011`（热扩散率单位）—— 物理和算术都对。**

> `*.mat` `'HEAT','SOLID'` expects diffusivity per DAY … Concrete is a ~0.0864 m2/day,
> i.e. 1.0e-6 m2/s. Supplying 1.0e-6 with day-based steps under-diffuses by 86400x.

0.0864 m²/day ÷ 86400 s/day = 1.0e-6 m²/s ✅。混凝土热扩散率量级正确。
与本仓库积累的"温度场"经验一致，且它把这条标为 `severity: silent` ——
分类准确（跑得完、结果错，正是最危险的一类）。

**抽查 D：输出文件扩展名 —— 找到了我们文档里没有的。**

`dag.yaml` 的 `emitted_in` 字段提到 `*.opw` / `*.dis` / `*.oew` / `*.oit` / `*.oip`。
我们的 `docs/references/glossary.md` 一个都没收录。逐个回源码验：

```
opw → Global.f90    dis → Global.f90(3) Fem.f90    oew → Global.f90
oit → Global.f90(2) Fem.f90(7)          oip → Global.f90(2)
```

**五个全部真实存在。零幻觉。** 它比我们的人工术语表更完整。

**抽查 E：单位表 —— 全对，且注明出处。**

`SKILL.md §8`：SI 严格制，E/应力/压强 = Pa（源自 `1.mat` 的 `2.500E+10`），
密度 kg/m³（`2.400E+03`），γw = 9810 N/m³，热扩散率 m²/day，
`ditime` 动力用秒、热/徐变/分期用天。全部与已知事实吻合，且每行标了"verified from"。

**总体幻觉率：抽查 5 项，0 项虚构。** 32 条三元组里 14 条 `severity: silent`、
32 条全部带可执行的 `detection` 命令。这不是"跑了个流程凑齐文件"的产物。

**它没抓到的（真实盲区）：**

- **`ifixvar=8` 的水头 BC 必须同时写 `jfixvar=ndimn`**，否则 `vdofix` 在
  `Fem.f90:12326` 被绕过、只用时间曲线常值 —— 这是本仓库真实踩过的坑
  （见 `generator.py` 的渗流水头修复）。KI 正确说了"水头 BC 就是 DOF 8 的普通 `.pre` 集"，
  但漏了这个静默失效条件。
- 我们的其它已知领域坑（重力坝分组顺序必须 group1=地基、VIE 吸收边界用
  `earthquake_curve_d/_v` 而非 `earthquake_curve`、`force_process` 与
  `earthquake_curve` 槽位=方向的语义）都不在 32 条里。
- 这些都是**从算例和失败历史里长出来的知识**，不在 `.f90` 源码字面里。
  agent 只拿到了源码树，拿不到 `cases/cases/train*` 和几个月的 workflow 失败记录。
  **这是方法本身的边界，不是这次实现的 bug：从源码能读出"代码怎么运行"，
  读不出"哪些配置组合会静默出错"。** 后者只能靠跑。

### 3. 域可插拔性的结论

**方法论是域中立的；实现是地学专用的。** 两句话分开说：

*域中立的部分（可以原样搬到任何计算模型）：*
探针 → 契约 → 单 agent 构建 → 确定性 gate 的四段结构；
FILE 1–11 的输出契约；"派生文件必须从权威源投影，不许手写"；
`symptom/diagnosis/remedy` 三元组 + `severity: silent` 这个分类；
受控词表反同义词漂移；"a check that cannot run is not a check that passed"；
gate 报告本身要做自洽性校验。**这七条里没有一条依赖地球科学。**

*地学专用的部分（换域必须动的）：*

| 位置 | 性质 | 换域成本 |
|---|---|---|
| `domain_templates/*.yaml` | 配置 | **一个 40 行 YAML，0 行代码**（已实测） |
| 未匹配域 → 静默回落 hydrology | **缺陷** | 应改成回落到 10 行通用占位模板，1 行代码 |
| `verify_ki_structure.py:467-472` `_MEDIA` 38 词 | **硬编码进裁判** | 必须改 gate 源码；且现有实现是无词边界子串匹配，本身就有 bug |
| `ki_vocabulary.py:99` `medium` 封闭词表 | 可扩展硬编码 | 1 行 |
| `data_registry/server_datasets.yaml` | 配置 | 无匹配则干净留空，不阻塞 |
| `dissection_spec.py` phase4 通用分支 | 已经写好了 | 0 |
| `domain_protocols/*.yaml`（5000 行领域知识） | **死代码** | 写了也没人读，除非先补读取逻辑 |

*对结构 FEM 根本没有对应物的概念（换域时必须重新定义，不是改个词的事）：*

1. **观测量绑定**。整套 obs-map 假设"模型输出 ↔ 独立实测时间序列"（水文站流量、
   土壤湿度探头、GRACE）。结构 FEM 的对照物是解析解 / 规范算例 / 另一个求解器 ——
   本质是 code-to-code 与 code-to-analytic **verification**，不是 observation
   **validation**。这次跑出来的包正好证明了这点：它的 `validation_tier` 只能是
   `analytic`，`comparable_obs_shapes` 里填的是
   `dam_displacement_timeseries` / `strain_gauge_derived_stress` 这类
   "理论上存在但这次并没用上"的东西。
2. **`validation_rank: 1`（唯一被判定量）**。对一个同时输出位移/应力/水头/温度/
   安全系数的多物理场求解器，"这个模型被哪个量判定"没有唯一答案 —— 取决于算例。
3. **`medium`（介质）**。见上，词表和 gate 都要改。
4. **`data_registry` 的语义**。地学侧是"外部再分析/遥感数据集"；结构 FEM 侧
   的等价物是"带参考解的自包含输入包"（本仓库的 `cases/cases/train*`），
   `period` / `resolution` / `variables+unit` 这些字段全部空转。

**一句话回答"能不能跳出地球科学域"：能，而且这次已经跳了一次并且跳得不错。
挡路的不是方法论，是三处地学假设 —— 一处是配置（40 行 YAML 解决）、
一处是缺陷（回落到 hydrology）、一处是硬编码进裁判的 38 词表（必须改源码）。
真正无法靠改配置解决的，只有"用观测数据验证"这一整套语义在结构 FEM 里换成了
"用解析解验证"，那是要重新设计一段规格、不是改个字段。**

### 4. 与手搭包的对比

**它做得比人好的：**

1. **覆盖广度**。21 个工具覆盖到 `write_ifs.py`（VIE 吸收边界）、`write_inverse.py`
   （反演）、`write_reliability.py`（可靠度）、`write_reinforcement.py`（配筋）、
   `write_contact.py`（接触）—— 手搭包只覆盖一个算例族（`gravdam_static_2block`）。
   它是从 `.f90` 里把求解器的**全部能力**扫出来的。
2. **三元组数量与质量**。32 条 vs 13 条；14 条标为 `silent`；32 条全部带
   可执行的 `detection` 命令。手搭包的 13 条没有统一的 detection 契约。
3. **真的编译并跑了**。手搭包是围绕已有二进制写的说明书，它是从源码重建了工具链
   （ifx + oneMKL + gidpost stub），并跑了两个解析解 + 四级网格收敛。
4. **文献**。23 篇真实相关文献（重力坝参数反演、零厚度接触单元、贝叶斯健康监测）。
   手搭包 0 篇。
5. **发现了我们文档的错漏**：`E` vs `W` 的区分、5 个未收录的输出扩展名。

**它不如人的：**

1. **踩坑知识**。前面列的四个真实静默坑（`jfixvar`、重力坝分组顺序、VIE 的
   `earthquake_curve_d/_v`、`force_process` 槽位语义）一个都没有。这些是
   项目历史里用失败换来的，源码字面读不出来。手搭包的 13 条三元组虽然少，
   但条条是踩过的。
2. **算例族的具体性**。手搭包绑定一个真实算例族（含网格指纹、参考解、
   `case_family` 标识），可以直接拿去判回归；生成的包是"求解器说明书"，
   没有绑定任何一个可复现的基准。
3. **格式契约**。`preflight_check.py` 的报文 schema 猜错了（裸 list 而非
   `{"checks": […]}`），`validation_convention.yaml` 是空壳。这两处是缺件
   （没有可抄的模板）导致的，但结果就是不符合规格。
4. **和平台工具链脱节**。它写的 21 个工具与 `fem-chat/skills/` 的 20+ 个 Python
   完全平行、互不知晓，甚至重新实现了 `.glb` 写入 —— 而本仓库的硬规矩是
   "不要手写 `.glb`，用 `generator.py`"。直接采用会造成两套工具链。

### 5. 一句话总评

**KDT-single 的方法论是对的，规格是好的，裁判有真牙齿但也有三处会误判的钝口；
它的域知识全是地学，但换域主要是配置活；它在本机跑不出 `pass` 是因为
五个必需外部件没随包发布，不是因为它做得差 —— 恰恰相反，它在 50 分钟里
从一份没有 README 的 Fortran 源码重建了工具链、编译出二进制、跑通两个解析解验证，
并写出了一份在若干点上比我们人工文档更准确的知识包。它拿不到的只有一样东西:
从失败历史里长出来的踩坑知识。**

### 附：如果要在本仓库落地，最小改动清单

1. `cli_agent.py:394-396` 三个常量改成可由环境变量覆盖（`_PINNED_PY` 默认
   `sys.executable`），并把 `ki_tools_common` 的三个 projector 补进仓库 —— 否则
   任何非 HydroCraft 机器都拿不到 pass。
2. `stages/s1_pipeline_map.py:24-27` 未匹配域改为回落到通用 7 阶段占位模板，
   并 `warnings.warn` 一句，不要静默套 hydrology。
3. `verify_ki_structure.py:467-472` `_MEDIA` 改为读 YAML + 加词边界
   （`\bsea\b`），否则 "search" 会一直蒙混过关。
4. `verify_ki_structure.py:487` 的 `_o.get("var")` 与 FILE 8 模板的 `name:` 对齐
   （报文里出现 `['None','None']` 就是这个不一致）。
5. `verify_ki_structure.py:144` 的 `unit table` 正则加上 `|^#+\s*\d*\.?\s*units?\b`。
6. `verify_ki_structure.py:459` 的 `if _outs and not _obs` 改成
   `if not _obs`（`outputs` 缺失/为空本身就该判 fail），堵掉不可失败路径。
7. 新增 `domain_templates/structural_fem.yaml` —— 已在
   `/tmp/claude-1000/kdt-single/domain_templates/structural_fem.yaml` 写好，可直接取用。

### 附：产物位置

```
/tmp/claude-1000/kdt-single/                       KDT-single 源码（+ 我加的 structural_fem.yaml）
/tmp/claude-1000/kdt-single-out/ki/                生成的 KI（21 tools / 12 docs / 32 triplets / dag 15 outputs）
/tmp/claude-1000/kdt-single-out/ki/ki_gen_accept.json   验收判决书
/tmp/claude-1000/kdt-single-out/work/bin/hstar     agent 自己在 Linux 上编译出的 HSTAR
/tmp/claude-1000/kdt-single-out/work/val_*_report.json  两个解析解验证报告
/tmp/claude-1000/kdt-single-out/work/conv_{4,8,16,32}/  网格收敛研究
/tmp/claude-1000/kdt-single-out/work/agent_output.log   agent 全程日志
/tmp/claude-1000/kdt-single-out/prompt_preview.md       41 KB 的 FILE 1–11 提示词
/tmp/claude-1000/kdt-single-out/evidence/               域回落污染产物（对照用）
```
