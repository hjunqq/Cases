# 重力坝 VIE 黏弹性边界动力时程 —— 从零建例日志 / KDT KI 包实战检验

> 任务：用 KDT 自动生成的 KI 包（`cases/cases/_review_2026-08/ki-packages/kdt-multi-GATE-PASS/`）
> 作为**主要指引**，从零建一个重力坝 VIE 动力时程算例并跑出结果。
> 同时记录 KI 包哪里帮上了、哪里不够、哪里是错的。
>
> 算例产物：`/tmp/claude-1000/dam-vie/`（不入仓库、不入 `cases/`）
> 开始时间：2026-08-26

## 目标算例规格

| 项 | 值 |
|---|---|
| 坝高 H | 100 m |
| 地基深度 | 3H = 300 m |
| 上下游边界 | 各 2H = 200 m |
| 水体单元 | 要（上游库水域，非附加质量） |
| 地震波 | 规范谱，PGA = 0.2g，时长 20 s |
| 边界 | VIE 黏弹性人工边界 |
| 分析 | 动力时程 |

---

## 阶段 0 — 通读 KI 包，先看它对 VIE 说了什么

读入：`SKILL.md`（584 行）、`docs/s9_advanced_capabilities.md`、
`tools/build_dynamic_seismic.py`、`docs/capabilities.md`。

### 0.1 全包检索 VIE 的结果

```
grep -riE "vie|viscoelastic|absorb|nabss|nbounod|artificial boundary" 整个 KI 包
```

**VIE 在 584 行 SKILL.md 里出现 0 次。**全包只有 3 处提到它，全是一句话带过：

| 位置 | 原文 | 信息量 |
|---|---|---|
| `docs/capabilities.md:65` | "…fluid & solid absorbing boundaries, **VIE / viscous-elastic artificial boundary**, MIF input wave field" | 只有名字 |
| `docs/s9_advanced_capabilities.md:106` | "`type_ABC` 选 `FIX`、`MIF`（…）**or the viscous-elastic family**" | 只有名字 |
| `tools/build_dynamic_seismic.py:28-30` | "`type_ABC` selects the artificial boundary: 'FIX', 'MIF' …, **or the viscous-elastic (VIE) family**" | 只有名字 |

三处都是同一句话的三个副本。**没有任何一处给出 `type_ABC` 的字面取值是 `'VIE'`**——
"viscous-elastic family" 是英文描述，agent 无从知道要往 `.glb` 里写哪三个字母。

### 0.2 KI 包在 VIE 上的**错误指引**（比缺失更危险）

`tools/build_dynamic_seismic.py:21-27` 的 EARTHQUAKE INPUT 一节，和
`SKILL.md §3.1` 的驱动表，都斩钉截铁地说：

> `.man` 每块首记录 `nincs cdtest earthquake_curve(1:ndimn)` —— 逐方向驱动基底**加速度**的曲线号。
> `.loa` 里 `type_curve='SEISMIC'` 的曲线 …… 单位 m/s²。

并提供了 `set_earthquake_curves()` 这个可执行工具去写它。

**这在 VIE 下是错的。**源码 `Fem.f90:13620-13625`：VIE 走的是
`earthquake_curve_d`（入射位移波）+ `earthquake_curve_v`（入射速度波，源码里 ×2），
`earthquake_curve` 必须留 `0`。一个只有 KI 包的 agent 会：
1. 照 `build_dynamic_seismic.py --earthquake-curves 2 0` 填加速度曲线号；
2. 不知道 `.man` 在 VIE 下要**多插两行**（`hwdirec hcoord` / `inpcord eq_d eq_v`）；
3. 于是 `.man` 记录条数不对，后续所有读取整体错位。

这正是 SKILL.md 自己 `dt_003` 描述的症状，但它的 remedy（"COPY-FIRST from a template"）
在这里无效——**KI 的 11 个模板里没有任何一个是 VIE 算例**
（`static, column_selfweight, lame_cylinder, cooks_membrane, mini_3d, train01_gravdam_static,
train02_gravdam_seismic, train03a_modal_dry, train05_slope_stability, train07_thermal_transient,
train12_seepage_steady`）。`train02_gravdam_seismic` 是加速度驱动的普通动力，
从它 copy-first 恰好会把上面这个错误固化下来。

### 0.3 缺口清单（第 1 批，全部来自阶段 0 通读）

| # | 缺什么 | 我去哪查的 | KI 包里为什么没有 | 本该放进它的哪个文件 |
|---|---|---|---|---|
| G1 | `type_ABC` 的字面取值 `'VIE'` | `fem-chat/docs/references/vie-absorbing-boundary.md`（引 `Global.f90:728`） | KDT 抽取时只抓到了英文描述性短语，没回到源码取字符串常量 | `docs/format_spec.yaml` 的 `type_ABC` 枚举 + `s9` |
| G2 | VIE 用**入射位移波+速度波**而非加速度曲线 | 同上（引 `Fem.f90:13620-13625`） | 见 0.2，KDT 把普通动力的规则当成了通用规则 | `tools/build_dynamic_seismic.py` 的 EARTHQUAKE INPUT 一节 + 一条新 triplet |
| G3 | `.man` 在 VIE 下多两行（`hwdirec hcoord` / `inpcord eq_d eq_v`），位置固定 | 同上（引 `Fem.f90:8528-8529`） | KI 的 `.man` 记录模型是无条件的；它没建模"`type_ABC` 会改变 `.man` 记录数"这个条件依赖 | `docs/input_preparation.md` 的 `.man` 小节 |
| G4 | `.ifs` 的 `nabssgroup` 段怎么填（子组头 `sedge nnode index xyz0 cdbound` + 逐边行） | 同上（引 `Stiff.f90:10412-10453`） | KI 只列出了字段**名**（`build_dynamic_seismic.py:41` 一行），没有记录布局 | `docs/input_preparation.md §3.11`（现在只有一行字段名） |
| G5 | `cdbound` 语义：`1`=侧边界只吸收，`2`=底边界，**入射波只从 2 进** | 同上（引 `Fem.f90:13614,13665`） | 同 G4 | 同 G4 |
| G6 | `.pre` 的 `nbounods` 自由面高程表 | 同上（引 `Fem.f90:8546-8552`） | KI 的 `.pre` 模型只有 prescribe-set，完全没有这一段 | `docs/input_preparation.md` 的 `.pre` 小节 |
| G7 | 没有任何 VIE 模板可 COPY-FIRST，而 SKILL.md 把 COPY-FIRST 定为**强制** | `TEMPLATES` 列表 | 模板集是按已跑通的 train* 挑的，train10（VIE）当时是 parked 状态被排除 | `tools/_hstar_io.TEMPLATES` |
| G8 | 求解器必须经注入 MKL 路径的 wrapper 启动 | `fem-chat/CLAUDE.md` / `skills/quick_analysis.py` | KI 的 `run_hstar.py` 只设 `HSTAR_BIN`，不设 `LD_LIBRARY_PATH`；SKILL.md §4/§5 假设 oneapi 已在环境里 | `docs/s6_execution.md` |

> 注：G1–G7 全部是同一个根因的分身——**KDT 没有沿 `type_ABC` 这个开关做条件记录展开**。
> 它把 `.glb/.man/.pre/.ifs` 建模成了固定布局，而 HSTAR 的真实格式是"后面的记录条数取决于前面的开关"，
> 这一点 SKILL.md 自己在 §3.3 说得很清楚（"strictly ordered, with conditional records"），
> 但工具和 docs 都没有按这句话实现。

**结论（阶段 0）：主要指引在 VIE 这件事上是空的。**
从这里起，实际指引换成 `fem-chat/docs/references/vie-absorbing-boundary.md`，
KI 包降级为对照物。后续每一步继续记录它本可以在哪里帮上忙。

---

## 阶段 1 — 网格与地震波

指引来源：**仓库**（`skills/gen_gravdam.py` 的函数签名、`skills/gen_seismic_wave.py` 的 CLI）。
KI 包在这一步**完全没用上**：它的 `tools/build_mesh_files.py` 只会写 `.cor`/`.ele` 并对齐
`.glb` 计数，不知道重力坝的几何（上游直立面 + 下游 1:0.7 坡 + 共节点地基 + 上游库水域）。

```python
gen_gravdam.build(height=100, crest_width=8, ds_slope=0.7, us_slope=0.0,
                  found_depth=300, found_margin=200,
                  nx=10, ny=16, n_found_y=20, n_margin=10,
                  reservoir=True, water_level=93.75)
```

| 量 | 值 |
|---|---|
| 节点 / 单元 | 977 / 910 |
| 分组 | 1=地基 600、2=坝体 160、3=库水 150（**group1=地基，符合硬约束**） |
| 坐标范围 | x ∈ [0, 478]，y ∈ [−300, 100] |
| 坝踵 / 坝趾 | x = 200 / 278（坝底宽 78 m） |
| 库水位 | 93.75 m（= 100×15/16，取整到坝体网格行，留 6.25 m 超高） |
| 单元尺寸 | 地基 15 m(竖) × 20 m(横)、坝体 ≈ 6.25 × 7.8 m |

单元尺寸校核：地基 Vs = √(G/ρ) = √(1.0e10/2.4/2600) = 1266 m/s，10 Hz 时 λ = 127 m，
λ/8 ≈ 16 m，与 15~20 m 网格相当，勉强够用（这条校核 KI 包里没有）。

地震波：

```bash
python3 skills/gen_seismic_wave.py <case> --pga 0.2g --dur 20 --dt 0.01 --Tg 0.35
```

| 量 | 值 |
|---|---|
| PGA | 1.9632 m/s² = **0.2001 g** ✓ |
| PGV | 0.0755 m/s |
| PGD | 0.0159 m |
| 点数 / 时长 | 2001 / 20.0 s ✓ |

> ⚠ **PGV/PGA = 0.038 s，而实测强震记录典型值是 0.1 s 左右。**
> 合成波的能量偏高频（加速度谱峰 7.15 Hz）。对普通加速度驱动的动力分析影响有限，
> 但 **VIE 直接吃 v(t) 和 d(t)**，所以这个比值偏低会实打实地压低 VIE 的输入能量。
> 这是本次做出来才发现的，见阶段 5。

---

## 阶段 2 — 生成 deck，并补上 generator 不写的两段

### 2.1 KI 包在这里给了什么

`SKILL.md §3.3` 把 **COPY-FIRST 定为强制**："Never author `.glb`/`.pre`/`.man` from a
Python dict … Start from `tools/build_case_from_template.py`"。
但 11 个模板里**没有一个是 VIE**，最接近的 `train02_gravdam_seismic` 是加速度驱动的普通动力。
从它 copy-first，再用 `tools/build_dynamic_seismic.py --earthquake-curves 2 0`
（KI 唯一给出的地震输入手段），得到的是**一个 `.man` 少两行、且用错驱动量的 deck**。

所以这一步只能改走仓库路径：`skills/generator.py`（它认识 `type_ABC=VIE`，会写 `.man` 的两行）
+ 手工补 `.ifs`/`.pre`。

### 2.2 从源码定死的四个字段语义（KI 包一个都没有）

读 `hstarYLOrig/HSTAR` 源码得到，其中三条连仓库的
`docs/references/vie-absorbing-boundary.md` 也说得不够或不对：

| 事实 | 源码位置 | 状态 |
|---|---|---|
| `.ifs` 头部的 `exx/uxx/densxx` **被源码注释掉了，根本不读**；`E/ν/ρ` 一律取自**吸收边所贴附实体单元的材料** | `Stiff.f90:10419` `read(ifsunit,*)nabssgroup   !,exx,uxx,densxx`；`10460-10464` `e=props(matno)%…%e !exx !` | 仓库参考文档说这三个值"用于算波速"、"填错不会报错只是吸收特性不对"——**实际是完全被忽略**，是一处需要更正的说法 |
| `xyz0` 不是装饰，它是**散射源点**：弹簧刚度按 `K += w·|J|/(2R)` 累加，`R = |高斯点 − xyz0|` | `Stiff.f90:10530` | 仓库文档只列了字段名，没说它是什么；train10 填 `(193, 0)` = 其网格 x 中心 + 地表，本例照此取 `(239.0, 0.0)` |
| 边的绕向决定法向 `n = (−dy, dx)`；**只有 `cdbound=1` 侧边界用到法向**（`xyz1 = dsxyz .x. rr`），阻尼/弹簧矩阵都是二次型因而与绕向无关 | `Stiff.f90:normal_local_b`；`Fem.f90:13707` | 两处文档都没写；本例按 train10 的实测绕向（法向指向域**内**）填 |
| 每条边只有 4 个数 `i0, lnods(1:nnode), aelems`；train10 行末那个多出来的 `3` 被 list-directed read 丢弃 | `Stiff.f90:10450` | 仓库文档描述是对的 |

### 2.3 顺手发现：train10 的 `cdbound=2` 组是错的

train10 是本仓库唯一"人工核对过"的 VIE 实例，它在
`project_train10_vie_parked` 里因"逐点幅值差 0.7~7 倍"挂起。核对它的 `.ifs` 时发现：

```
cdbound=2 子组（底边界，入射波唯一入口）共 50 条边
  → 水平边 20 条，竖直边 30 条
```

底边界组里塞了 30 条**竖直**边（如节点 300→302，都在 x=236，y 从 −250 到 −241.667）。
入射波只从 `cdbound=2` 进（`Fem.f90:13614`），把侧面竖直边当底边界注入，
等于在地基内部竖直面上凭空注入水平入射波。**这是 train10 幅值对不上的一个很有力的候选根因**，
不在本任务范围内，但值得单独回去查。

### 2.4 本例的补齐脚本

`/tmp/claude-1000/dam-vie/patch_vie.py`（生成后打补丁，不改仓库代码）：

* 用"只被一个实体单元引用的边"提取外边界，再按坐标分成三段
* `cdbound=2`（底边界 y = −300）：**30 条，全部水平边**，绕向左→右（内法向 (0,+1)）
* `cdbound=1`（侧边界 x = 0 / x = 478，y ∈ [−300, 0]）：40 条，绕向使内法向指向域内
* `xyz0 = (239.0, 0.0)` = 域 x 中心 + 地表
* `.pre` 追加 `nbounods = 42`（两侧各 21 个节点）+ `42*0.0` 自由面高程（地表就在 y=0）
* 库水域左端面（x=0, y ∈ [0, 93.75]）**不设吸收边** —— 见阶段 5 的局限说明

```
1.ifs  : nabssgroup=70  (bottom cdbound=2: 30, sides cdbound=1: 40)
         xyz0 = (239.0, 0.0)
1.pre  : nbounods=42  free-surface elevation 0.0
```

---

## 阶段 3 — 两个把算例卡住的坑（都不在任何文档里）

### 3.1 库水域走真 W 场（声学流体）—— 试了，走不通，**已放弃并如实记录**

任务要求"水体单元，非附加质量"。仓库里唯一真正的水单元路径是
`gravdam_modal_fsi.json` 的做法：库水组 `field: "W"`（自由度 8）+ `SEEPAGE` 材料 +
`.ifs` 的 `nifsgroup` 界面边，坝面 U 场与库水 W 场耦合。三个障碍：

1. **`generator.py` 的 `tp=="F"` 分支排在 FSI 分支前面**（`skills/generator.py:96-118`），
   动力算例永远拿不到 `lmdofn(8)=1`，W 自由度根本没启用。手工把 `.glb` 的
   `MDOFN` 块改成 `8 / 1 1 0 0 0 0 0 1 / 2 2 0 0 0 0 0 2` 之后——
2. 求解器在 `Fem.f90:8610` 读 `.man` 时 EOF（`forrtl: severe (24) … unit 9`）。
   同一个 `.man` 在 `lmdofn(8)=0` 时读得下去，说明**开了 W 自由度会改变 `.man` 的记录需求**，
   而这条依赖没有任何文档记载，源码里也没找到对应的额外 `read(mainunit,…)`。
3. 就算读过去，`generator.py:690-697` 自己的注释已经写明：
   **`nifsgroup` 耦合要求 `PROFILE` 求解器，PARDISO 会把 U×W 交叉项静默丢掉、退化成干坝**。

在给定时间内没有把这条路走通。**如实记录为未完成**，改用下面的方案。

### 3.2 库水域改用位移型流体单元（本次交付采用）

真 Q4 单元、真水密度、真水体积模量 —— **不是 Westergaard 附加质量**（`Icaddmass = 0`）：

| 参数 | 值 | 依据 |
|---|---|---|
| ρ | 1000 kg/m³ | 水 |
| ν | 0.49 | K₀ = ν/(1−ν) = 0.96 → 静水压力的横向传递到坝面达真值 96% |
| E | 1.24e8 Pa | 使 K = E/(3(1−2ν)) = **2.07e9 Pa** = 水的体积模量 |
| 导出 | G = 4.2e7 Pa，c_p = √((K+4G/3)/ρ) = **1459 m/s** ≈ 水中声速 1440 m/s ✓ |

残余剪切刚度 G = 4.2e7 是位移型流体单元的已知代价（水本应无剪切刚度）。
不另加静水压力边荷载，静、动水压力全部由这组单元承担，避免重复计入。

### 3.3 ⚠ 直接调 `generator.generate_all()` 会把地震波悄悄换成常量 1.0

**这是本次最险的一个坑。**`.LOA` 里的 SEISMIC 曲线数据**不是 generator 写的**，
是 `run_pipeline.py:262-274` 在调 generator **之前**把 `earthquake_*.dat` 读进
`tc["values"]` 的。绕过 run_pipeline 直接调 `generate_all()`，得到的是：

```
  2  SEISMIC  0  3
  0.01  0  10  1
  1.000000  1.000000        ← 两个常量点，不是 2001 个采样
```

后果：deck 生成正常、求解器读得下去、**不报任何错**，但"地震"变成了一个恒为 1.0 的
入射位移波 + 恒为 1.0 的入射速度波。第一次运行就这么跑了 1000 步，
残差按每步 ≈2.2 倍指数发散到 1e40 才暴露。

修复：在 build 脚本里复刻 run_pipeline 的注入逻辑。修好后：

```
loaded 2001 points from earthquake_a.dat (peak 1.963)
loaded 2001 points from earthquake_v.dat (peak 0.07547)
loaded 2001 points from earthquake_d.dat (peak 0.01588)
```

### 3.4 ⚠ `time_curve_for_each_group = 0` 不是"重力保持静态"，是**重力完全不施加**

第一次成功跑完后，坝顶 t=0.04 s 的位移是 −4e−12 m —— 机器零，重力根本没进去。
查源码：

```fortran
! Load.f90:888-889
! if(tcurvegravity(igroup)==0.or.appear(igroup)<=0),
!                                 no gravity in igroup
! Load.f90:1170
if (tcurvegravity(igroup)/=0) then    !2017/11/19
```

`fem-chat/CLAUDE.md` 的动力地震规则写的是"**`time_curve_for_each_group=0`（gravity stays static）**"，
VIE 模板 `gravdam_dynamic_vie.json` 也照抄了 `[0,0,0]`。
按源码，`0` = **该组不施加重力**，正确写法是填一条常值曲线的编号（本例 curve 1）。
这条同样值得回去更正仓库文档与模板。

### 3.5 但重力也不该在动力块里加 —— 实测确认

把 `time_curve_for_each_group` 改成 `[1,1,1]` 重跑（`case_g`）：

| 测点 | 无重力 `case_m` | 加重力 `case_g` |
|---|---|---|
| 坝顶 ux 峰值 | 47.06 mm | 86.19 mm |
| 坝顶 uy 峰值 | 10.29 mm | **497.89 mm** |
| 坝顶 uy 均值 | 0.02 mm | **−476.43 mm** |
| 坝顶 uy 动力分量 | 10.27 mm | 471.55 mm |

VIE 边界只靠黏弹性弹簧约束（`.pre` 里 `NFIXSETS = 0`，train10 也是 0），
重力在动力块里作为 t=0 的阶跃施加，整个模型下沉约 0.48 m 并以 ±0.47 m 全程振荡，
把地震响应完全淹没。**结论：VIE 算例的重力必须放在前置静力块，不能在动力块里阶跃施加。**
本模型全线性弹性，叠加成立，所以交付结果取**无重力的地震增量响应**（`case_m`）。

---

## 阶段 4 — 结果

### 4.1 运行状态

| 算例 | 内容 | 退出码 | 步数 | 结果文件 |
|---|---|---|---|---|
| `case_m` | **交付主算例** · VIE + 库水单元 + 规范谱 0.2g，无重力 | **0** | 1000 × 0.02 s = 20 s | `1.flavia.res` 183 MB |
| `case_g` | 同上 + 重力在动力块内 | 0 | 1000 | 重力阶跃瞬态，仅作对照 |
| `case_fix` | 固定边界 + 加速度曲线驱动，对照 | 0 | 1000 | 对照 |
| `case`   | 真 W 场 FSI 尝试 | **24（.man EOF）** | 0 | 未跑通，见 3.1 |

求解器：`hstarYLOrig/HSTAR/x64/Release/hstar`，经 `harness/_solve_deck.py` 启动（注入 MKL 路径）。
单次求解墙钟约 20 s。

### 4.2 三轴门控（`case_m`）

```python
from harness.gate import physics_gate, run_validity
from harness.consistency import deck_consistency
```

| 门 | 结果 |
|---|---|
| `physics_gate` | **PASS**（无告警） |
| `run_validity` | **valid** · `solver_convergence` pass，最差步 879 两次迭代后 ratio = 3.654e−14（容差 1e−5）；`global_equilibrium` = unverified（动力算例 tofor 不含惯性力，属预期） |
| `deck_consistency` | **consistent** · `type_problem` config 与 `.glb` 一致为 F；地震特征齐备且 `type_problem=F` |

### 4.3 任务清单里的自查项

| 检查 | 结果 |
|---|---|
| `1.chk` 的 `fachv` 恒为 0（VIE 不用加速度曲线） | ✓ 1000 条记录全部 `0.0 0.0`。对照 `case_fix`（FIX + 加速度驱动）同一字段是变化的（−1.895e−3、−1.551e−3…，正是 `earthquake_a.dat` 的逐点值），说明 fachv=0 确实是 VIE 的正常表现而非"地震没进去" |
| 组块 `order_time` = `0 2` | ✓ 三个组全部 `0  2` |
| 坝顶水平位移 ≫ 竖向 | ✓ 47.06 mm vs 10.29 mm，**比值 4.6** |
| 地震波峰值 ≈ 0.2g | ✓ PGA = 1.9632 m/s² = 0.2001 g，2001 点，20.0 s |

### 4.4 位移结果（`case_m`，绝对位移，VIE 下含基底运动）

| 测点 | 位置 | ux 峰值 | uy 峰值 |
|---|---|---|---|
| 坝顶上游角 (node 817) | (200, 100) | **47.06 mm** | 10.29 mm |
| 坝顶下游角 (node 827) | (208, 100) | 47.05 mm | 7.08 mm |
| 坝踵 (node 631) | (200, 0) | 29.65 mm | 5.51 mm |
| 远场地表 (node 651) | (478, 0) | 29.95 mm | 7.23 mm |
| 底边界 (node 31) | (478, −300) | 20.62 mm | 9.25 mm |

派生量：

| 量 | 值 |
|---|---|
| 输入 PGD | 15.9 mm |
| 底边界节点位移 | 20.1 mm（入射 + 反射，介于 PGD 与 2×PGD 之间 ✓） |
| 远场地表 / 底边界 | 29.95 / 20.62 = **1.45**（自由地表放大 ✓） |
| 坝顶绝对 / 远场地表 | 47.06 / 29.95 = **1.57**（坝体放大 ✓） |
| **坝顶相对远场地表** | **37.40 mm**（t = 15.76 s） |
| 坝顶相对底边界 | 36.24 mm |

### 4.5 与固定边界算例的对照（`case_fix`）

| | VIE（入射波驱动） | FIX（加速度驱动） |
|---|---|---|
| `fachv` | 恒 0 | 随时程变化 |
| 坝顶相对位移峰值 | **37.40 mm** | **34.99 mm** |
| 坝踵 ux | 29.65 mm（绝对） | 10.93 mm（相对） |

两条完全不同的驱动路径给出同量级的坝顶相对位移（差 7%），互为交叉验证。
VIE 略大是合理的：它同时放开了地基柔度与摇摆，这一项放大与辐射阻尼的衰减相互抵消一部分。

### 4.6 频率成分

| 信号 | 主频 |
|---|---|
| 输入加速度 a(t) | **7.15 Hz** |
| 输入位移 d(t) | **0.30 Hz** |
| 远场地表绝对位移 | 0.30 Hz |
| 坝顶绝对位移 | 0.30 Hz |
| **坝顶相对位移** | **0.70 Hz**（次峰 1.15 / 1.55 / 1.75 Hz） |

解读：

* 两次积分把能量强烈搬到低频，d(t) 主频 0.30 Hz。VIE 吃的是 d/v，所以**绝对**位移几乎就是跟着地面走，主频等于 d(t) 的主频，这是正确行为不是缺陷。
* 坝顶**相对**位移主频 0.70 Hz，接近 300 m 深地基柱的一阶剪切频率 Vs/(4H) = 1266/1200 = **1.06 Hz**；即体系响应由**坝—地基**系统而非固定基频（估算 5.5H/√(E/ρ) = 0.17 s → 5.9 Hz）主导。3H 深地基 + 辐射边界下这是预期的。
* 输出采样 0.04 s（Nyquist 12.5 Hz），5.9 Hz 附近能分辨但不精细；若要看坝体自身模态需要减小 `noutn`。

---

## 阶段 5 — 已知局限（不掩饰）

1. **真声学 W 场库水没跑通**（3.1）。交付用的是位移型流体单元，残余剪切刚度 G = 4.2e7 Pa，会略微高估坝—库耦合刚度。
2. **库水域左端面（x=0, y ∈ [0, 93.75]）是自由面**，没有辐射边界，库区动水压力波在此全反射。工程上应加 Sommerfeld 辐射条件，本次未加。
3. **重力未包含在交付结果里**（3.5 已说明理由）。完整工况应先跑静力块再接动力块（`nblks=2`），本次为单块。
4. **合成波 PGV/PGA = 0.038 s 偏低**（阶段 1）。VIE 由 v/d 驱动，这个比值直接决定输入能量，所以此处的 47 mm 与用真实强震记录相比可能偏保守。这是 `gen_seismic_wave.py` 值得回头调的一点。
5. **无实测/基准可比**。KI 包自己的 `validation_convention.yaml` 里 `DISPLACEMENT` 唯一可引的带（dai2021，MAE 0.12–3.12 mm）是**监测数据上统计模型的精度**，不是 FE 误差带，套不到本例。本例只做了物理自洽性与交叉验证，没有做定量验证。
6. **地基单元 15–20 m**，10 Hz 时约 λ/8，边缘够用；若关注 >10 Hz 成分需加密。

---

## 阶段 6 — 对 KDT KI 包的总评

### 6.1 完整漏项清单

阶段 0 的 G1–G8 之外，做的过程中又新增：

| # | 缺什么 | 我去哪查的 | KI 包里为什么没有 | 本该放进它的哪个文件 |
|---|---|---|---|---|
| G9 | `.ifs` 头部 `exx/uxx/densxx` **被源码注释掉、根本不读**，波速取自贴附单元的材料 | `Stiff.f90:10419, 10460-10464` | KI 只从字段名清单抄了名字，没读 reader 实现 | `docs/input_preparation.md §3.11` + 一条 triplet |
| G10 | `xyz0` 是散射源点，`R=|gp−xyz0|` 进弹簧刚度分母 | `Stiff.f90:10530` | 同上 | 同上 |
| G11 | L2 吸收边的绕向 / 法向约定，以及"只有 cdbound=1 用法向" | `Stiff.f90:normal_local_b`、`Fem.f90:13707` | 同上 | 同上 |
| G12 | 重力坝的几何生成（上游直立 + 下游坡 + 共节点地基 + 库水域） | `skills/gen_gravdam.py` | KI 的 `build_mesh_files.py` 是通用的写 `.cor/.ele`，没有结构型式的先验 | 一个新的 `build_gravdam_mesh.py` 工具 |
| G13 | 规范谱人工波合成 + a/v/d 三分量 + 基线校正 | `skills/gen_seismic_wave.py` | KI 把 `base_acceleration_time_history` 列为"analyst-supplied"，不生成它；但 VIE 必须要 v 和 d | `tools/build_dynamic_seismic.py` 加一个合成子命令 |
| G14 | `time_curve_for_each_group = 0` 表示**不施加重力** | `Load.f90:888-889, 1170` | KI 的 `.loa` 模型只到"gravity / edge pressure / point loads / time curves"这一层，没进到逐组开关 | `docs/s4_boundary_conditions_and_loads.md` |
| G15 | VIE 下重力不能在动力块里阶跃施加（`NFIXSETS=0` 的模型会整体下沉振荡） | 本次实测 | KI 的 §14 讲了 `winit/ninit` 应力初始化，但没有把它和"无固定支座的吸收边界模型"联系起来 | `SKILL.md §14` |
| G16 | 网格尺寸 ≤ λ/8 的波传播判据 | 常规做法 + `gen_gravdam` 参数 | KI 的 `s2_mesh_and_geometry.md` 只讲计数一致性，没有动力分析的网格判据 | `docs/s2_mesh_and_geometry.md` |

### 6.2 KI 包给出的**错误指引**（比幻觉更危险的"似是而非"）

只有一条，但它是致命的：

> **`tools/build_dynamic_seismic.py` + `SKILL.md §3.1` 把"地震通过 `earthquake_curve` 引用一条
> 加速度 SEISMIC 曲线"当作 HSTAR 的普遍规则，并提供了 `set_earthquake_curves()` 去写它。**

这句话在 `type_ABC = FIX` 下完全正确（本次 `case_fix` 就是这么跑的，`fachv` 确实变化）。
但在 VIE 下它是错的，而且**错得不会报错**：
`earthquake_curve` 填了值也只是被 `dfact_time_curve` 算出 `fachv` 然后……在 VIE 分支里根本不用；
真正驱动模型的 `earthquake_curve_d/_v` 保持 0，于是**地震输入为零，算例安静地跑完 1000 步，
输出一片近似静力的结果**。KI 包的输出检查清单（§8c）里没有任何一条能抓住它——
它甚至会建议去看 `fachv`，而 VIE 下 fachv 恒为 0 正是**正常**的。

第二条较轻但同类：**`SKILL.md` 把 COPY-FIRST 列为强制**，而 KI 的模板集里没有 VIE 算例。
"从 `train02_gravdam_seismic` copy-first" 会把上面这个错误原样继承下来，
并且因为 `.man` 少两行导致后续记录整体错位——落回 `dt_003`，而 `dt_003` 的 remedy 就是 COPY-FIRST。
**诊断闭环在这里自指且无出口。**

### 6.3 只给一个陌生 agent 这个 KI 包、不给仓库其余资料，它能走多远？

分四段回答：

| 阶段 | 能不能过 | 说明 |
|---|---|---|
| 编译 / 跑通一个 shipped 模板 | **能** | §4/§5 的构建脚本、`run_hstar.py` 的 stdin 处理、`dt_001` 对 `severe (24)` 的解释都到位且正确。这部分做得好 |
| 建一个**普通**重力坝静力 / 加速度驱动动力算例 | **大概率能** | 从 `train01/train02` copy-first，改材料、改曲线，`build_*.py` 的 `--describe` 也确实有用 |
| 建**本任务这个** VIE 算例 | **不能** | 卡在第一步：它不知道 `type_ABC` 要写 `'VIE'` 这三个字母（G1）。就算猜对了，`.man` 少两行、`.ifs` 的 `nabssgroup` 空着、`.pre` 的 `nbounods` 缺失，任一处都会立刻 `severe (24)`，而 triplet 给的 remedy 是 COPY-FIRST，没有可 copy 的 VIE 模板 |
| 万一它蒙对了文件结构 | **会产出一个错但看起来对的结果** | 见 6.2：填 `earthquake_curve` 而不填 `_d/_v`，算例跑完、门控式检查全过、`fachv=0` 还被文档暗示成需要警惕的信号——它会交出一份"地震输入为零"的动力时程报告 |

**一句话**：这个 KI 包在"HSTAR 是什么、怎么编、怎么跑、常见坑在哪"这一层是可用的、
质量不低（33 条 triplet 里 `dt_001/dt_003/dt_006/dt_011/dt_028` 都真实且有价值）；
但在"某个具体开关打开后，输入文件的结构和物理量都会变"这一层是**空的**。
它把 HSTAR 建模成了一组固定格式的文件，而 HSTAR 真正的复杂度恰恰在
SKILL.md 自己写下却没有实现的那句话上——**"strictly ordered, with conditional records"**。
KDT 的下一步该做的不是多抽 13 篇 docs，而是**沿每个控制开关做一次条件记录展开**，
并且**为每条 build_* 工具补一条"这个开关会让哪些别的记录出现/消失/改语义"的表**。

### 6.4 KI 包实际帮上忙的地方（要给分就给这些）

1. `dt_001` —— 事先知道 `forrtl: severe (24)` 在收敛后出现是 stdin 问题、结果有效。省了排查时间。
2. `dt_028` —— 案例文件是 GBK；`grep` 源码要 `-a`。确实踩到了。
3. §8c 的符号约定表（应力受压为负、`acceleration` 是相对而 `acceleration_ab` 是绝对）—— 读结果时用到了。
4. §12 的参数取值表 —— 坝体 E = 2.0–3.0e10 / ν 0.17–0.22 / ρ 2400、地基 E = 1.0–3.0e10 / ρ 2600–2700，本例材料直接落在它给的区间里。
5. `order_time_mdofn` 必须为 2 否则速度/加速度输出流为空（`build_dynamic_seismic.py:13-15`）—— 正确且有用。

---

## 交付清单

| 内容 | 路径 |
|---|---|
| 主算例（VIE + 库水单元 + 0.2g/20s，已跑通、三门全过） | `/tmp/claude-1000/dam-vie/case_m/` |
| 重力对照 | `/tmp/claude-1000/dam-vie/case_g/` |
| 固定边界对照 | `/tmp/claude-1000/dam-vie/case_fix/` |
| 真 W 场 FSI 尝试（未跑通） | `/tmp/claude-1000/dam-vie/case/` |
| 建例脚本 | `/tmp/claude-1000/dam-vie/build.py` |
| VIE 两段补齐脚本 | `/tmp/claude-1000/dam-vie/patch_vie.py` |
| 结果提取脚本 | `/tmp/claude-1000/dam-vie/extract.py` |
| 坝顶时程 JSON | `/tmp/claude-1000/dam-vie/ts_case_*_*.json` |

仓库与 `cases/` 未被写入任何算例产物；本日志是本次唯一的仓库改动。
