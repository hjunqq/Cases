# HSTAR 能力差距审计 — 求解器支持 vs 工具链覆盖

> **生成日期**: 2026-08-25 · **一次性人工审计**，不进运行时、不需要维护
> **权威求解器**: `hstarYLOrig/HSTAR`（由 `skills/run_pipeline.py:57` 的 `HSTAR_EXE` 确定；
> `HSTAR_Q/` 是另一条线，本审计不以它为准 —— 两者输出块并不相同，例如
> `acceleration_absolute` 只有 YL 有）
> **工具链侧**: `skills/generator.py`
> **方法**: 扫求解器源码枚举「求解器支持什么」，对照生成器实际写出什么，
> 再用仓库里 242 个真实 `.glb`（`cases/` + `_archive/` + `workspace/`）统计
> 「人类工程师实际用什么」给缺口排序。

**动机**：2026-08-25 发现 `gid_v` / `gid_a` 在 Fortran 里存在多年而生成器从未置位，
`acceleration_absolute`（= 相对加速度 + `fachv`，正是拿去和输入 PGA 对比的量）
一直躺在 `Output.f90:1466` 无人调用。这类「求解器能做、工具链没接」的缺口，
遇到一个修一个是低效的，扫一遍源码列成表是高效的。

---

## 总览

| 维度 | 求解器支持 | 生成器覆盖 | 缺口 |
|---|---:|---:|---:|
| 输出开关 `gid_*` | 20 | 7 | **13** |
| 输出开关 `res_*` | 17 | 5 | **12** |
| 材料模型 | ~22 | 9 | **13** |
| 单元 index | 19 | 4 自动识别 | **15** |

---

## 轴一：输出开关（最高优先级）

`.glb` 里两行开关，顺序见 `hstarYLOrig/HSTAR/Global.f90:960-964`。
「真实 deck 用量」= 242 个人工/历史 `.glb` 中该位为 1 的个数。

### `gid_*`（写入 `1.flavia.res`）

| 开关 | 输出块 | 生成器 | 真实 deck 用量 | 结论 |
|---|---|:---:|---:|---|
| `gid_u` | `DISPLACEMENT` | ✅ 非 S/渗流时置位 | 208 | 已覆盖 |
| `gid_s` | `STRESS` | ✅ 同上 | 205 | 已覆盖 |
| `gid_ms` | `PRINCIPALSTRESS` | ❌ **从不置位** | **18** | **缺口** — 主应力对坝工是常规量 |
| `gid_f` | `tofor`（节点力/反力） | ✅ 2026-08-25 起，力学分析 | 83 | 已覆盖（原最大缺口） |
| `gid_rot` | `ROTATION` | ❌ 从不置位 | 1 | 低优先（梁/板 index 20/22 才有意义） |
| `gid_v` | `velocity` | ✅ 2026-08-25 起 tp=F | 2 | 新覆盖 |
| `gid_a` | `acceleration` + `acceleration_absolute` | ✅ 同上 | 8 | 新覆盖 |
| `gid_T` | `TEMPERATURE` | ✅ tp=S 非渗流 | 30 | 已覆盖 |
| `gid_P` | `PORE-PRESSURE` | ✅ 渗流 | 22 | 已覆盖 |
| `gid_Pv` | `PRESSURE_V` | ❌ | 0 | 无人使用，忽略 |
| `gid_ep` | `PLASTICSTRAIN` | ✅ 塑性类材料 | 8 | 已覆盖 |
| `gid_Y` | `Yield` | ✅ 2026-08-25 起，全部非线性材料 | 48 | 已覆盖（原为仅 CONCRETE） |
| `gid_FC` | `FACTOR` | ❌ | 0 | 无人使用，忽略 |
| `gid_Ns` | `Normal_stress`（节理） | ❌ | 0 | 无人使用，但 GOODMAN 算例理论上该开 |
| `gid_Ss` | `Shear_stress`（节理） | ❌ | 0 | 同上 |
| `gid_Mxy` | `STRESS_Moment` | ❌ | 5 | 缺口 — 梁/板内力，`section_forces.py` 现在自己算 |
| `gid_bem` | 另写 `bem.flavia.msh/res` | ❌ | 2 | 低优先（边界元） |
| `gid_wh` | `WATER-HEAD` | ✅ 渗流 | 18 | 已覆盖 |
| `gid_wv` | `flow_velocity`（渗流流速场） | ❌ **从不置位** | **8** | **缺口** — 渗流只出水头不出流速 |
| `gid_bcs` | 另写边界条件面网格 | ❌ | **25** | 缺口 — 但 `gen_bc_vtp.py` 已用别的路子实现 |

### `res_*`（写入二进制 `1.res`）

生成器只在三种情况置位：非线性材料 → `res_s`；CONCRETE → `res_u/res_s/res_ms/res_Y`；
tp=F → `res_u/res_v/res_a`。其余 12 位恒为 0。

`res_*` 的实际消费方是二进制 `1.res`，而当前工具链（`flavia_to_vtu.py`、
`run_pipeline.py`）**全部只读 ASCII 的 `1.flavia.res`**，没有任何 `1.res` 读取器。
所以 `res_*` 缺口的优先级整体低于 `gid_*` —— 补开关之前得先有读取器。

---

## 轴二：材料模型

求解器侧（`grep material==` 全源码）约 22 种：

```
CLASSICALEP  ClayPZ  CONCRETE  CONTACT  DUNCANCHANG  ELASTIC  ELASTIC_EP
ELASTIC_FRICTIONLESS  ELASTIC_ISOTROPIC  ELASTIC_SPRING  FCM  GOODMAN
MCJOINT  NSSoil  NSSoilPZ  NSTOKS  PLANE_LOWFT  SandPZ  SoilPZ
STEEL_EP  STEEL_SP  VM
```

生成器写得出的 9 种（`generator.py` `_gen_mat`）：
`ELASTIC` · `SEEPAGE`(→WATER/FLUID) · `HEAT`(→ELASTIC_ISOTROPIC) · `MC`(→CLASSICALEP+MC 准则) ·
`CLASSICALEP` · `GOODMAN` · `CONCRETE` · `DUNCANCHANG` · `GEOMETRY`(ROD_or_BEAM)

**主要缺口**

- **Pastor-Zienkiewicz 广义塑性族**（`SandPZ` / `ClayPZ` / `SoilPZ` / `NSSoilPZ` / `NSSoil`）—
  砂土液化、动力孔压累积。地震 + 地基砂层的题目现在完全做不了。
- **`MCJOINT`**（`CLASSICALEP` 的一个 criteria）— train05a 用过，靠手写 deck。
- **钢材族** `STEEL_EP` / `STEEL_SP` — 钢筋现在靠 `GEOMETRY`+ROD 近似。
- **`CONTACT` / `ELASTIC_FRICTIONLESS`** — `generate_contact.py` 走的是另一条路（`.ctr`），
  与材料层的接触模型不是一回事。
- `VM`（von Mises）、`FCM`、`PLANE_LOWFT`、`ELASTIC_SPRING`、`NSTOKS` — 未接。

### ⚠️ `CAMCLAY` 是死配置

`generator.py:188` 和 `:196` 把 `CAMCLAY` 列进「塑性材料」用于置 `gid_ep` 和
`has_nonlinear`，但 **`_gen_mat` 里没有任何 `CAMCLAY` 分支**。
写 `{"type": "CAMCLAY"}` 会静默落到通用 ELASTIC 路径 —— 输出开关按塑性置位，
材料却是弹性的。**静默失效，应当移除该字符串或补上写出分支。**

---

## 轴三：单元类型

求解器接受的 index（全源码 `grep index==`）：
`1 2 3 4 5 9 10 15 16 17 18 19 20 21 22 23 24 25 26` 共 19 个。

生成器 `elem_info()`（`generator.py:32-41`）只有 5 条映射：

| (nnode, ndimn) | → | 说明 |
|---|---|---|
| (2, 2) / (2, 3) | `L2` index 1 | 杆/梁 |
| (3, 2) | `T3` index 2 | 三角形 |
| (4, 2) | `Q4` index 5 | 四边形 |
| (8, 3) | `B8` index 9 | 六面体 |

外加 `GOODMAN` 材料时把 index 5 改判为 20，以及 config 里手工 `elem_index` 覆盖。

### 🔴 缺省回退是静默错误

```python
return table.get((nnode, ndimn), ("Q4", 5, "Quadrilateral"))
```

任何未列出的组合都**静默返回 2D 四边形 index 5**。实测：

```
nnode=4  ndimn=3  -> ('Q4', 5, 'Quadrilateral')   # 四面体 → 被写成 2D 四边形
nnode=10 ndimn=3  -> ('Q4', 5, 'Quadrilateral')   # 二次四面体
nnode=20 ndimn=3  -> ('Q4', 5, 'Quadrilateral')   # 二次六面体
nnode=6  ndimn=3  -> ('Q4', 5, 'Quadrilateral')   # 楔形
nnode=8  ndimn=2  -> ('Q4', 5, 'Quadrilateral')   # 2D 八节点
```

而 `workflow/capability/registry.yaml` 声明
`supported_element_types: [quad, tri, tet, hex]` —— **tet 是对外承诺支持的，
实际会被静默写成 2D 四边形**。`mesh_io.py:388` 反倒认识 H4/H10/B20（用于取面），
说明这个洞是 `elem_info` 单点遗漏，不是全局设计如此。

**注意修法**：HSTAR 的约定是**退化单元**而非独立的四面体 index ——
`Fem.f90:17801` 的 `change_list` 专门处理「index 5 出现 3 个不重复节点」（退化四边形）
和「index 9 出现 6 个不重复节点」（退化六面体→楔形）。所以正确做法是把
四面体/楔形**退化展开成 8 节点 B8（index 9）**，而不是给它一个新 index。
在动手前必须先确认这一点，否则会写出求解器不认的组合。

---

## 轴四：写死的旋钮

生成器把下列求解器参数固定为常量，config 无法调：

| `.glb` 字段 | 写死值 | 备注 |
|---|---|---|
| `BEETA1 BEETA2` | `0.5 0.25` | Newmark 参数，动力算例可能需要调 |
| `equvs_process` / `appear_level` | 全 0 | 分级加载/等效应力 |
| `ntrans nlaymif epsMIFb gamaMIF ifixvar0_inpb camif dxmif` | `0 0 1.0e0 0.02 2 1980.0 25.0` | MIF 层相关，含两个可疑的量纲常数 |
| `doubsig ktan1 ktan2 nlocalbeam ndimnrt` | `2 1.0e8 1.0e8 0 0` | |
| `absorb alfa_p4 stiff_p4` | `0.6 10.0 1.0E+20` | 吸收边界 / P4 局部坐标 |
| `hdam` / `water_level` / `modf_dis_blocks` | `0` / `-99` / `0` | 按 nblks 铺开 |
| `ikindks` | 仅由「有无 CONCRETE」二选一（3 或 0） | 其他取值（如 5=粘结）只能手改 |

`ikindks=5`（粘结/ftcrack 行）是 train09 钢筋粘结用到的，现在只能手工改 —— 已知痛点。

---

## 缺口排序（按真实使用频次）

按「人类工程师在 242 个真实 deck 里实际开了、而生成器从不开」排序：

1. ~~**`gid_f` → `tofor` 节点力/反力（83 次，34%）**~~ — **已于 2026-08-25 补上**。
   附带收益：全部节点力求和 Σ 应为 0（内力与外力平衡），这是一条免费的
   **全局平衡自检**，实测重力坝静力算例 Σx=0.000E+00、Σy=-2.4 N（相对量级 1e-7）。
2. ~~**`gid_Y` 覆盖过窄（48 次）**~~ — **已于 2026-08-25 扩到全部非线性材料**。
   连带修掉一个既有的静默错报：`Yield` / `FACTOR` / `PLASTICSTRAIN` /
   `PRINCIPALSTRESS` 四个块此前不被 `run_pipeline.py` 的解析器识别，其节点行
   会灌进仍然开着的 `STRESS` 段；而 `Yield` / `FACTOR` 是单值行，会把每个节点
   覆写成 1 分量 —— 报告里打印的 "Sxx 范围" 实际是屈服指标范围。
   已用 `_archive/process/rcbeam/1.flavia.res` 复现并验证修复
   （修复前 30 个 STRESS 段全被覆写为 1 分量，修复后 4 分量 + 独立的 30 个 Yield 段）。
3. **`gid_bcs`（25 次）** — 但 `gen_bc_vtp.py` 已用别路实现，实际优先级低。
4. **`gid_ms` → 主应力（18 次）** — 一行改动。
5. **`gid_wv` → 渗流流速场（8 次）** — 渗流算例现在只出水头。
6. **单元 `elem_info` 静默回退** — 使用频次为 0（因为没人敢用），但这是**承诺支持却会
   静默出错**的一类，危险度高于频次。
7. **PZ 广义塑性材料族** — 频次为 0，因为压根做不了；属于「能力天花板」而非「缺口」。

---

## 不要做什么

- **不要为了补齐而全量补齐。** `gid_Pv` / `gid_FC` / `gid_Ns` / `gid_Ss` 在 242 个真实
  deck 里用量为 0，补了没有消费方。
- **不要先补 `res_*` 开关。** 二进制 `1.res` 当前没有任何读取器，先开开关只会让文件变大。
- **不要给四面体新增一个 index。** HSTAR 用退化单元约定，见轴三的说明。
- **不要动 `generator.py` 里已被基准覆盖的路径而不重跑基准。** 11 个注册家族里多数
  依赖 `.glb` 逐字节稳定；改输出开关会改变 `1.flavia.res` 的行数，
  `golden_regression` 的 `n_values` 随之变化，需要 `promote_case.py --refresh-golden`
  重刷（2026-08-25 的 `mech_dynamic_2d` 就是这样处理的）。

---

## 裁判层：三条轴

2026-08-25 的四方架构对照（见 `research/ki-three-way-report.html`）得出一个结论：
四家的差距不在组件多少，在**谁把知识接到了会自动失败的东西上**。本仓库此前是
「有引擎没裁判」——执行侧有 checkpoint、批调度、302 个测试，知识侧裸奔。
于是把门控从一维拆成三条正交的轴：

| 轴 | 位置 | 回答什么 | 三态 |
|---|---|---|---|
| **结果是不是垃圾** | `harness/gate.py::physics_gate` | 崩溃标记 / NaN / 全零 | bool（原有，未改） |
| **这次跑合不合法** | `harness/gate.py::run_validity` | 收敛了吗（`1.chk` 的 `ratio for residu norm`）、全局平衡吗（`tofor` 的 \|ΣF\|/Σ\|F\|） | valid / **unverified** / incomplete |
| **文件之间对不对得上** | `harness/consistency.py::deck_consistency` | config 的 `type_problem` vs `1.glb` vs 配置特征所隐含的；声明的荷载真进 `1.LOA` 了吗 | consistent / **unverified** / inconsistent |

**为什么必须拆开**：一次运行可以有限、非零、无崩溃、且数字落在金标准区间内，
同时完全不描述你提的那个问题。两个实测案例：

- 重力坝的水压整个丢失（`gravdam_meta.json` 缺失），坝顶位移 0.26 mm 而非 15.6 mm，
  **60 倍误差**；`physics_gate`、坝顶符号检查、量级检查、平衡检查**全部通过**。
- MC 算例残力比外力还大（残差 1.83），照样产出有限非零数值，`physics_gate` 判 PASS，
  而平衡残差是 0.985。

**为什么是三态而不是布尔**：老结果没有 `tofor` 块（`gid_f` 是今天才默认开的），
纯温度/渗流算例没有力平衡可言。`unverified` 表示「没有可判据的证据」——
既不算通过也不算失败，因此老基准不会被误杀，但促进者能在报告里看见它。

**有牙齿的地方**：`promote_case.py` 现在会**拒绝**沉淀 `incomplete` / `inconsistent` 的运行
（哪怕数字碰巧落在金标准区间里）；`validate_outputs.py` 会在 benchmark 报 PASS
但运行不合法时**覆写成 failed** 并留一条 warning。理由是：把这种运行沉淀成金标准，
比什么都不沉淀更糟——它会成为后续所有运行的参照系。

两条设计规则借自 KDT 的裁判，都是我们已经被咬过的：

1. **不能失败的检查不是检查。**`if X and not Y` 在 X 为空时静默通过——他们自己的
   dag 检查就有这个洞（缺 `outputs` 键 → 零失败）。所以这里每个谓词都区分
   「不存在」与「存在但错了」，前者报 `unverified` 而非 `pass`。
2. **检查器与生成器必须共用一个读取器。**两份「这个文件说了什么」的实现，
   正是 golden 守卫死掉的原因（矢量解析器写、单值正则读）。所以 `1.glb` 走
   `import_glb.parse_glb`，与迁移路径同一个函数。

---

## 让这份审计不腐烂：契约检查

一次性审计会过期。KISS 的 `CAPABILITY_INVENTORY.md`（2026-04-03）就是证据 ——
它自己提的 Priority 1 整改到 8 月只落地一半，被点名的硬编码路径至今还在。
所以本审计的核心结论已经**固化成两条会自动报警的检查**，在
`skills/test_skills.py` 里（求解器源码不存在时自动跳过）：

| 检查 | 守什么 |
|---|---|
| `solver_contract_glb_switches` | 生成器写出的 `gid_*` / `res_*` 表头，必须与 `Global.f90` 的 read 语句**同名、同序、同数量**，且值行数量与名字数量一致。`.glb` 这两行是**位置相关**的 —— 求解器一旦插入/改名/换序一个开关，生成器之后的每个标志都会整体错位，且不报错 |
| `solver_contract_flavia_blocks` | `Output.f90` 里每个会写进 `1.flavia.res` 的块标签（按 `a15` 截断后），必须**要么被两个解析器都认识，要么在 `UNREAD_FLAVIA_BLOCKS` 里带理由登记**。同时反向检查豁免清单不留陈旧条目 |

第二条的设计要点是**棘轮**：求解器新增一个输出块时，测试会失败，逼你做一次
显式决策（接进来，还是写明为什么不接），而不是默默忽略。已验证四种劣化都能
被抓到：解析器丢掉一个已支持的块、豁免清单留陈旧条目、求解器新增未知块、
求解器在开关行中间插入新字段。

**这两条检查是本次审计真正的产物**，表格只是它们的可读快照。

### 契约检查上线当天抓到的第六个缺陷

`run_pipeline.py` 匹配的是 `WATER_HEAD` / `PORE_PRESSURE`（**下划线**），
而求解器写的是 `WATER-HEAD` / `PORE-PRESSURE`（**连字符**，已用
`PRJ-0559` 的真实渗流输出核对）。永远匹配不上；而渗流算例的第一个块就是
`PORE-PRESSURE`，此时还没有 section 打开，于是所有节点行被直接丢弃 ——
**Step 4 对渗流算例什么都不报**。已修，并顺手把孔压与水头分成两段
（量纲不同：Pa vs m）。

---

## 复核方式

本审计的数字可重现：

```bash
# 求解器侧输出开关
grep -na "read(gunit,\*)gid_" hstarYLOrig/HSTAR/Global.f90
# 求解器侧材料
grep -rna "material==" hstarYLOrig/HSTAR/*.f90 | sed "s/.*=='//;s/'.*//" | sort -u
# 求解器侧单元 index
grep -rna "index==" hstarYLOrig/HSTAR/*.f90 | sed 's/.*index==//;s/[^0-9].*//' | sort -n -u
# 真实 deck 用量（脚本见本次审计会话）
```
