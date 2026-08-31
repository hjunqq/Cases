# 事实一：deck 不是"一份格式"，是被十几个 reader 消费的一条流

> 全部由 `tools/extract_dispatch.py` 从 `hstarYLOrig/HSTAR/*.f90` 提取，
> 原始数据 `data/deck-readers.json` / `data/dispatcher-map.json`。行号可直接复核。

## 0. 核心事实

**506 条 deck READ 语句，分布在 6 个文件、31 个 reader 子程序中。**

```
.man → 17 个 reader      .glb → 6 个      .ifs → 4 个
.pre →  3 个             .loa → 2 个      .mat → 1 个
```

一个 deck 文件被**多个子程序依次消费同一条打开的文件流**，每个子程序的记录布局不同。
所以正确的模型不是 `文件 → 文法`，而是：

```
(dispatch 路径, 开关状态) → 记录布局 × 槽位语义
```

这三样来源不同，必须分开挖：

| | 挖什么 | 来源 |
|---|---|---|
| 记录布局 | 每个 reader 的 READ 序列 | READ 语句 |
| **槽位语义** | 这一格读进来的变量被谁消费 | **变量的使用点**（见 `02-facts-semantic-drift.md`） |
| 路径选择 | 哪个 reader 会跑 | 调用点的守卫与循环 |

**槽位语义完全不在 READ 语句里。**只做文法提取会得到一份看起来完整、实则漏掉全部语义的
schema——这正是本项目历史上所有静默错误的来源。

## 1. unit → 文件绑定（Global.f90:652 附近）

```fortran
open(gunit,     file=probn//'.glb')      open(mainunit,  file=probn//'.man')
open(munit,     file=probn//'.mat')      open(loadunit,  file=probn//'.loa')
open(punit,     file=probn//'.pre')      open(ifsunit,   file=probn//'.ifs')
```

注意 `munit` 是 `.mat` 而不是 `.man`——`.man` 是 `mainunit`。

## 2. 顶层调度骨架（Fem.f90）

```
L109   call global_data                     ← .glb 主体，循环外，一次
L1672  call external_load_1                 ← .loa 曲线表+点载+边定义，循环外,一次
L1673  do iblks = lblks+1, runblks ─────────┐
L1707    if(ground_inf/100==1) estif_semi_space_center
L1708    if(ground_inf/100==2) estif_semi_space
L1863    call prescrib_set                  │ .pre 约束集,每块
L1886    call external_load_2               │ .loa 每块荷载+体力+tcurvegravity
L1890    if(ADINA/=0 .and. iblks==runblks) call GHM2ADINA
L1899    call solve                         │
L1908    if(type_problem=='Q')  → 静力子调度 │
L1933    if(∉{Q,E,W})           → explicit / time_dependent
L1940    elseif(=='E')          → response_spectrum
L1944    if(type_problem=='W')  → frequency_analysis
       ───────────────────────────────────┘
```

**`external_load_1` 在循环外、`external_load_2` 在循环内。**
它们不是二选一，是一前一后（见 `03-corrections.md` 更正 #3）。

## 3. `.man` 的 reader 选择 —— 记录布局随开关变化

| 条件 | reader | `.man` 首记录 |
|---|---|---|
| `type_problem=='W'` | `frequency_analysis` | `nincs, fachv` ← **直接读加速度实数，不是曲线号** |
| `type_problem=='E'` | `response_spectrum` | — |
| `∉{Q,E,W}` 且 `type_solver=='EXPLICIT'` | `explicit` (Fem.f90:9959) | `nincs, earthquake_curve(1:ndimn)` ← **无 cdtest** |
| `∉{Q,E,W}` 否则 | `time_dependent` (Fem.f90:8525) | `nincs, cdtest, earthquake_curve(1:ndimn)` |
| 以上 + `type_ABC=='VIE'` | 同上，**多一条记录** (8529) | `inpcord, eq_curve_d(1:ndimn), eq_curve_v(1:ndimn)` |
| 以上 + `type_ABC=='MIF'` | 同上，**多一条记录** (8530) | `inpcord, eq_curve_MIF(1:ndimn)` |

**`type_solver`——一个"求解器"开关——会改变 deck 的记录布局。**
`nincs` 后面那一格是 `cdtest` / 曲线编号 / 加速度实数，取决于哪个 reader 在跑。
没有任何文档写过这一条，也没有任何样例算例能揭示它。

## 4. `type_problem=='Q'` 的静力子调度（Fem.f90:1908-1930）

```fortran
if(relis==1 .and. block_stab==0)        call STATIC_U_reli
elseif(relis==1 .and. block_stab>=1)    call static_rigid_reli
elseif(block_stab>=1 .and. ebody==0)    call static_rigid_1
elseif(mdofn==7)   then if(lmdofn(7)/=0) call static_U_P
elseif(mdofn==8)   then if(lmdofn(8)/=0) call static_U_Pw
elseif(nbackf/=0)  then  nbackdT==0 ? back_analysis : back_d_analysis
else                                     call static_U
```

**这一条解释了一个已知未解 bug**：`HSTAR_Q` 单场稳态温度场走 `static_U` 然后 SIGSEGV。
温度场的 `mdofn` 既不是 7 也不是 8，`nbackf` 为 0，于是落进 `else` 进了位移求解器。
在此之前这是一次崩溃；有了地图它是一句可读的话。

## 5. `.ifs` 的四段（固定顺序，2026-08-28 更正）

```
stiff_interface_fluid_solid  nifsgroup     ← 流固界面组
stiff_absorb_fluid           nabsfgroup    ← 流体吸收边界
stiff_absorb_solid           nabssgroup    ← 固体吸收边界
stiff_ifs2006                ifsnedge      ← 2006 界面/边界边
```

调用点在 `Fem.f90:200-203`，顺序就是上表。原文把 `stiff_ifs2006` 错放在第一段，
原因是只看了 reader 列表，没有回到调用点复核顺序。`hstarpre` 的
`prepare_ifs_file`（`fempre.f90:5609-5842`）也按同一顺序输出：
`nifsgroup → nabsgroup → nabssgroup → ifsnedge`；其中标签 `nabsgroup` 对应求解器变量
`nabsfgroup`，标签行本身只被读掉，内容不参与语义。

每段前有一条 `text` 记录（读掉即弃——这就是标签行存在的原因，标签内容任意）。
`bkind==2` 时多读一个 `selem` 字段（Stiff.f90:9607/9608）——条件字段。

**`nabsfgroup` 排在 `nabssgroup` 之前。**本会话建的 100m 坝 `nabsfgroup=0`，
导致库水上游截断面全反射；在段序里这是一眼可见的空缺。

## 6. `.glb` 的 6 个 reader

```
global_data                   86 条   主体
contact_point_to_point        27 条   接触
link_concrete_and_water_pipe   6 条   混凝土-水管连接
link_concrete_and_steel        5 条   混凝土-钢筋粘结  ← RC 算例卡在这
estif_semi_space_center        5 条   半无限地基,  ground_inf/100==1
estif_semi_space               4 条   半无限地基,  ground_inf/100==2
```

后五个各自在 `.glb` 尾部追加自己的段，是否出现由开关决定。
`ground_inf/100` 这种**整数除法当开关**的写法，任何基于样例的推断都不可能发现。

## 7. rewind

```fortran
Load.f90:138   if(meshc==1 .or. rmesh/=0) rewind(loadunit)
Load.f90:139   if(Bparameter/=0)          rewind(loadunit)
Fem.f90:2390   if(meshc==1 .or. rmesh/=0) rewind(mainunit)
```

`meshc` / `rmesh` / `Bparameter`（重网格、重启）会让文件从头重读。

## 8. 对基于样例的方法的判决

上面每一条——`type_solver` 改布局、`ground_inf/100` 开关、`.man` 的 17 个 reader、
`external_load_1/2` 的前后关系——**都不可能从样例算例中推出来**。
样例只能展示被走过的那一条路径，而且不会告诉你还有别的路径存在。

**源码是唯一能知道这些东西存在的地方。**这是"无算例自我实现"成立的根据，
也是任何 KI/知识包方法在工程 CAE 上的天花板：它们的真值来源是文档与样例，
都是二手的。
