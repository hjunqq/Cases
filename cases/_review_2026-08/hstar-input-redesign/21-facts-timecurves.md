# 事实七：四种工具链不支持的时间曲线类型

> 2026-08-28/29。open #11。源码 `hstarYLOrig/HSTAR/*.f90`（YL 主线），
> 第二来源 `_archive/hstarpre/sourcef90/fempre.f90`，
> 运行证据 `probe/timecurves/`（预先登记，6/6）。

## 0. 先更正一条上游事实

`14-facts-deck-ast.md §3.2` 写「`type_curve` 有 5 种」。**那是 AST 守卫抽取的口径，不是全集。**
`type_curve` 的**唯一权威枚举**在 `Load.f90:164-211` 的 `select case` 加上下游求值器的
`if/elseif` 链，共 **15 种**，且 `_archive/hstarpre/sourcef90/fempre.f90:2665-2680`
用 `number 1..15` 的编号表独立复现了同一张表：

| number | type_curve | number | type_curve |
|---:|---|---:|---|
| 1 | `LINEAR` | 9 | `DEXPONENTIAL` |
| 2 | `LNLINEAR` | 10 | `DABT` |
| 3 | `TEMPERATURE` | 11 | **`ARCLENGTH`** |
| 4 | `COS` | 12 | `DISCONTROL` |
| 5 | `PEAK` | 13 | `DABT`（与 10 重复，hstarpre 的笔误） |
| 6 | **`HARMONIC`** | 14 | **`EXTRAPOLATION`** |
| 7 | `FOURIERSERIES` | 15 | **`WATERLEVEL`** |
| 8 | `SEISMIC` | — | `EQUINCRE`（只在 `Fem.f90:12311` 消费，不在 hstarpre 表里） |

`generator.py:_gen_loa`（`fem-chat/skills/generator.py:574-585`）只写 `LINEAR` 与 `SEISMIC`
两种 —— **净缺 13 种**，不是 4 种。本文只逐条查实任务点名的 4 种，其余在 §7 列清单。

## 1. 唯一的 reader：`Load.f90:147-223`

整张曲线表只有一个 reader，在 `external_load_1` 里，`.loa` 文件开头：

```fortran
Load.f90:141   read(loadunit,*)text          ! 标题行
Load.f90:142   read(loadunit,*)ntcurve       ! 曲线条数
Load.f90:147   do itcurve=1,ntcurve
Load.f90:150      read(loadunit,*)ntime, type_curve, nstoch_curve, nline   ! ← 公共头
Load.f90:161      if(nstoch_curve/=0) read(...)order_stoch_parameter(1:nstoch_curve)
Load.f90:164      select case(type_curve)                                  ! ← 分型
                     ...
Load.f90:211      end select
Load.f90:212      if (type_curve=='SEISMIC')          read dfact_curve            ! 整数组一次读
Load.f90:218      elseif (type_curve 不在 {ARCLENGTH,EXTRAPOLATION,HARMONIC,WATERLEVEL})
Load.f90:220                                          read dfact_curve(1:ntime)   ! 一条记录
Load.f90:222      lineload = lineload + nline
Load.f90:223   end do
```

**三个必须先说清的公共事实：**

1. **读取侧的守卫栈有两层，不是一层。**（2026-08-29 用扩到 23 文件的 AST 重跑后更正；
   原稿写"只有 `type_curve` 字符串本身"，那是只查了一层。）
   - 外层 = **caller 的 `Bparameter` / `RCI_REQUEST` 调度**。`external_load_1` 被 5 个分支调用：
     `Bparameter==-1.or.==-2`｜`(Bparameter>0.and.<=2).and.balgor<=1 ; RCI_REQUEST==1`｜
     同前 `; RCI_REQUEST==2 ; balgor==0`｜`(Bparameter>0.and.<=2).and.balgor==2`｜**`else`**。
     每条曲线记录因此在 Deck ABI 里有 **5 条路径**。
   - 内层 = `select case(type_curve)`（`Load.f90:164`）。
   - **实际影响为零**：第五条分支是 `else`，普通算例 `Bparameter=0` 走它，
     所以"任何算例都能写这四种曲线"这个结论不变——但守卫栈必须写全，
     否则下一个人会以为反演外循环下的填法也一样（它多了 `rewind(loadunit)`，`Load.f90:139`）。
   - 内层之外**没有** `type_problem` / `type_ABC` 守卫。真正的门槛在**下游消费**（§2-§5）。
2. **`nline` 不参与解析。** 只累加进 `lineload`（`Load.f90:222`），而 `lineload` 只在
   `restart==1` 时用来跳过已读行（`Load.f90:131-136`）。**非重启算例填错 `nline` 不会报错**——
   又一个"语法合法、求解器接受"的坑。hstarpre 的 `nline` 计算规则在
   `fempre.f90:2681-2725`，可直接照抄（见各型条目）。
3. **`ntime` 对 HARMONIC / EXTRAPOLATION / ARCLENGTH 是死字段**：`dfact_curve(ntime)`
   在 `Load.f90:157` 被分配，但这三种既不读它也不用它。填 1 即可。

### 与 LINEAR / SEISMIC 的布局对照（一张表）

`H` = 公共头 `ntime type_curve nstoch_curve nline`。

| type_curve | H 之后的记录 | 尾部 `dfact_curve` 记录 | 总数据行 = hstarpre 的 `nline` |
|---|---|---|---|
| `LINEAR`（default） | `ttime_curve(1:ntime)`（1 行） | 有，1 行 | 2 |
| `SEISMIC` | `dtrec dtbegin dtend ample`（1 行） | **有**，`Load.f90:213` 整数组一次读 | 1 + ntime |
| **`HARMONIC`** | `a0sin asin wsin w0sin dtbegin dtend`（1 行 6 实数） | **无** | 1 |
| **`WATERLEVEL`** | ntime 行，每行 `t f` 一对 | **无** | ntime |
| **`EXTRAPOLATION`** | `nextr ca dx`（1 行，整+实+实） | **无** | 1 |
| **`ARCLENGTH`** | `time_begin fact_inc nalgo giter`（1 行）<br>+ `nalgo==2` 时再 1 行 `inode idofn` | **无** | 1（nalgo=1）/ 2（nalgo=2） |
| `FOURIERSERIES` | `NFS dtbegin dtend` / `AI(1:NFS)` / `omega(1:NFS)`（3 行） | **有**（不在排除表里） | 3 + 1 |

> **`WATERLEVEL` 是唯一"每个时间点一行"的类型**，其余全是"整数组一条记录"。
> 这个差异是 §3 那个跨求解器陷阱的根源。

---

## 2. `HARMONIC` —— 解析式简谐曲线

### 记录布局

```
  <ntime>  HARMONIC  <nstoch_curve>  1
  <a0sin>  <asin>  <wsin>  <w0sin>  <dtbegin>  <dtend>
```
`Load.f90:165-168`（分配 `Load.f90:166`，读 `Load.f90:168`）。无 `dfact_curve` 行
（`Load.f90:218-219` 的排除表含 HARMONIC）。

### 解锁守卫

无。只要 `type_curve` 字符串是 `HARMONIC`。

### 消费点（槽位语义的唯一来源）

`Fem.f90:12642-12655`（主求值器 `dfact_time_curve`）：

```fortran
if (time <  dtbegin)          dfact = 1.e-30
else if (time > dtbegin+dtend) dfact = 1.e-30
else                           dfact = a0sin + asin*sin(wsin*time + w0sin)
```

所以槽位语义是：`a0sin`=常数偏置，`asin`=幅值，`wsin`=**圆频率 rad/s**（不是 Hz、不带 π），
`w0sin`=相位 rad，`dtbegin`=起振时刻，`dtend`=**持续时长**（不是终止时刻——窗口是
`[dtbegin, dtbegin+dtend]`）。窗口外是 `1.e-30` 而**不是 0**。

得到的 `dfact` 之后与 LINEAR 完全同路：乘点荷载（`Fem.f90:13276`）、乘边荷载
（`Fem.f90:13362`）、乘约束值（`Fem.f90:12339 fixed=dfact*vdofix`）。
**HARMONIC 是纯 drop-in：换掉曲线定义，荷载侧一个字不用改。**

### ⚠ 三个求值器语义不一致

| 求值器 | 位置 | HARMONIC 支持 | 差异 |
|---|---|---|---|
| `dfact_time_curve` | `Fem.f90:12642` | 有 | 有 `dtbegin/dtend` 时间窗 |
| `dfact_temp_pre` | `Fem.f90:12555` | 有 | **没有时间窗**，全程 `a0sin+asin*sin(...)` |
| `dfact_internal_heat` | `Temper.f90:1194` | 有 | 需复核 |

同一条 HARMONIC 曲线，用在温度预设边界上和用在力荷载上，起振窗口的行为不同。
这是 `02-facts-semantic-drift.md` 那类漂移的又一实例，且此前未记录。

### 运行证据

探针 P2（`V1_harmonic_identity`）：把 `test_arclength` 的唯一曲线换成
`1 HARMONIC 0 1` + `1.0 0.0 1.0 0.0 0.0 1.0E9`（`asin=0` ⇒ `dfact≡1`，与基线
`LINEAR (0,1)→(1,1)` 数学恒等）。结果 `1.flavia.res` **与基线逐字节相同**。
布局与语义两条同时被验证。

---

## 3. `WATERLEVEL` —— 水位高程曲线

### 记录布局

```
  <ntime>  WATERLEVEL  <nstoch_curve>  <ntime>
  <t_1>  <f_1>
  <t_2>  <f_2>
  ...                      ← 共 ntime 行
```
`Load.f90:179-183`。无 `dfact_curve` 行（在排除表里）。

### 解锁守卫

无。

### 消费点

**第一层（求值）：`Fem.f90:12601` —— 与 `LINEAR`/`LNLINEAR` 共用同一段分段线性插值。**
全仓 grep（`grep -a "WATERLEVEL" *.f90`）**只有这一个命中**。
也就是说 `WATERLEVEL` 在求值层面**与 `LINEAR` 完全等价**，唯一的区别是 `.loa` 记录布局。

**第二层（语义来源）：`Fem.f90:12315-12321`**，`.pre` 的 `ifixvar==8`（水头/孔压）分支：

```fortran
Fem.f90:12315   else if(ifixvar==8.and.jfixvar/=0)then
Fem.f90:12317      inode = prescrib(idofix)%nodfix
Fem.f90:12318      if (jfixvar>0) wpres = (dfact - coord( jfixvar,inode))*gamaw
Fem.f90:12320      else           wpres = (coord(-jfixvar,inode) - dfact)*gamaw
Fem.f90:12322      fixed(ldofix) = wpres
```

**`dfact` 在这里是水位高程**，减去节点坐标得到水柱高，乘 `gamaw` 得孔压。
"WATERLEVEL"这个名字的含义**只存在于这里**，不在读取处、不在求值处。
（`jfixvar==0` 时走 `Fem.f90:12324 fixed=dfact*gamaw`，`dfact` 变成"压力水头"而非高程——
同一条曲线两种量纲，取决于 `.pre` 的 `jfixvar`。这与
`project_seepage_head_bc_fix` 记的 `jfixvar` 教训是同一处。）

### 现成 deck 样例（一手证据）

全仓 390 个 `.loa`，`WATERLEVEL` 出现 6 次，分布在 **3 个 deck**：

| deck | 曲线 | 用法 |
|---|---|---|
| `cases/cases/xfj_seepage_transient/1.loa` | 曲线 2（289 点，值 99~113）与曲线 3（289 点，值 32.9~34.9） | `1.pre` 首个 fixset 头 `8 4242 2 0 0 3 9810 0` → `ifixvar=8, itcurve=2, jfixvar=3`（3D 竖向），节点值全 `1`，即水位完全由曲线给出 |
| `_archive/hstarpre/.../甘再渗流场/变化渗流场/ganzai3d_seepage/ganzai3d21/1.loa` | 曲线 1（18 点，值 ~141.4） | 同型 |
| `_archive/hstarpre/.../甘再渗流场/渗流场反演/ganzai3d_seepage/Bganzai3d21/1.loa` | 同上 | 反演变体 |

**这是四种类型里唯一有真实 deck 样例的一种**，而且样例直接给出了填法与量纲（米，高程）。

### ⚠ 跨求解器陷阱：`HSTAR_Q` 完全不支持 WATERLEVEL

`HSTAR_Q/Load.f90` 的 `select case` **没有 `case('WATERLEVEL')`**
（`HSTAR_Q/Load.f90:148,152,163,167,171` 只有 HARMONIC/FOURIERSERIES/SEISMIC/
EXTRAPOLATION/ARCLENGTH），且全文件 grep 不到 `WATERLEVEL`。
于是 WATERLEVEL 曲线在 HSTAR_Q 里落到 `case default`（`HSTAR_Q/Load.f90:187-189`），
按"1 行 ttime_curve + 1 行 dfact_curve"解析 —— **ntime 行的 (t,f) 对会被错读，
而且是"读出数、不报错"的错法**。

考虑到 `project_steady_thermal_use_hstarq` 已决策把稳态温度场迁到 HSTAR_Q，
**任何带 WATERLEVEL 的渗流/水位算例不能直接迁移**。这条必须进迁移检查表。

顺带（同一次比对发现的第二条）：`HSTAR_Q/Load.f90:191-194` 的 SEISMIC 用
`do i1=1,ntime; read(...)dfact_curve(i1)` **一行一个值**读；YL 的
`Load.f90:213` 是整数组一次读。而 `generator.py:580-581` 每行写 10 个值
—— **在 YL 上正确，在 HSTAR_Q 上会静默读错（每行只取第一个数，丢掉 9 个）**。

### 运行证据

探针 P3（`V2_waterlevel_identity`）：`2 WATERLEVEL 0 2` + `0 1` / `1 1`，
结果与基线逐字节相同。证实布局正确且求值等价于 LINEAR。

---

## 4. `EXTRAPOLATION` —— 子模型/透射边界的外推荷载

四种里**最复杂、依赖最多**的一种。它不是"一种时间曲线"，而是一整套子系统的开关。

### 记录布局（`.loa`）

```
  <ntime>  EXTRAPOLATION  <nstoch_curve>  1
  <nextr>  <ca>  <dx>
```
`Load.f90:188-191`。无 `dfact_curve` 行。

### 它同时改变**别处**的记录布局（关键）

**(a) `.loa` 点荷载组**（`Load.f90:271-279`）：若某点荷载组引用的曲线是 EXTRAPOLATION，
该组的节点表**不是** `list(1:npload)` 一行，而是：

```
  <text>                                   ← Load.f90:274，一行被丢弃的标签
  <i1>  <listep(1:2*nextr+1)>              ← Load.f90:277，共 npload 行
```
且 `list(i0)=listep(i0,1)`（`Load.f90:278`）——第一个节点号兼作荷载作用点。

**(b) `.pre` 约束集**（`Prescrib.f90:214,239-245`）：fixset 头的**最后一个字段就是 `nextr`**：

```fortran
Prescrib.f90:214  read(punit,*)ifixvar,nfixnods,itcurve,tfixvar,outfix,jfixvar,gamawx,nextr
Prescrib.f90:240  if (nextr/=0) allocate(...listep(2*nextr+1)...value_ext(2*nextr+1,nextr))
Prescrib.f90:243               read(punit,*)i0, listep(1:2*nextr+1)     ← 每个约束节点一行
```

**(c) `.glb`**：`Global.f90:790` 的 `NTSMAT NTHMAT KSTAT ground_inf src nextrf submodel`
记录里的第 6 位 `nextrf` 是全局总开关（现有 deck 全为 0）。

**(d) `.ftr`**：`Global.f90:835,870-877` 读 `nforce/ngaps/...` 与 `surface_force` 面；
`Global.f90:885` `if(nextrf/=0) allocate(surface_force(iforce)%ftfor_ext(ndimn,npface,nextrf))`。
**没有 `.ftr` 就没有 `ftfor_ext`，EXTRAPOLATION 的点荷载分支必然取不到数据。**

### 消费点

**路径一（点荷载，`Fem.f90:13181-13248`）：**

```fortran
Fem.f90:13185-13190   ss = ca*ditime/dx                       ← Courant 数
                      t1=(2-ss)(1-ss)/2 ; t2=ss(2-ss) ; t3=ss(ss-1)/2   ← 二次插值权
Fem.f90:13191-13197   nextr=1 → cc=[1] ; nextr=2 → cc=[2,-1] ; nextr=5 → cc=[3,-3,1]
Fem.f90:13215-13219   forceint(:,ipoin) = surface_force(iforce)%ftfor_ext(:,ipface,iextr)
Fem.f90:13241         tofor(itotv) = tofor(itotv) + (cc .d. loadlocal(i0,i1,:))
```

槽位语义：**`ca` = 波速，`dx` = 网格间距，`nextr` = 外推阶数**。
物理上这是"用界面上过去 `nextr` 步的力，沿特征线外推出当前步的边界力"——
一个**特征线透射边界 / 子模型驱动**机制，与 VIE/MIF 是同一族但另一条实现路径。

**路径二（预设位移，`Fem.f90:9245-9265`）：** `nextrf/=0` 且该约束的曲线是 EXTRAPOLATION 时，
每步把 `result_zero(prescrib%listep)` 推进 `value_ext` 的历史环形缓冲。

**求值器：`Fem.f90:12714 goto 1`** —— EXTRAPOLATION 不写 `tcurves%dfact`。
它绕过整个 `dfact` 机制，直接生成 `tofor`。

### ⚠ 源码 bug：`nextr=5` 是坏的

`Fem.f90:13191-13197` 只对 `nextr==1/2/5` 设 `cc`，且 `nextr==5` 时只填 `cc(1:3)`，
`cc(4),cc(5)` 未初始化；而 `Fem.f90:13241` 的 `cc .d. loadlocal(i0,i1,:)` 是 5 元点积。
同样 `Fem.f90:13203-13212` 的 `tt` 只对 `iextr==1/2/5` 赋值，`do iextr=1,nextr` 在
`iextr=3,4` 时 `tt` 分配了却未赋值。**`nextr` 只有 1 和 2 可用**（`nextr=2` 时循环
`iextr=1,2` 都有分支，`cc` 两项都填，自洽）。

### 现成 deck 样例

**没有。** 全仓 390 个 `.loa` 零命中；154 个 `.glb` 的 `nextrf` 全为 0。

### 运行证据

探针 P4（`V3_extrapolation_unreferenced`）：追加一条 `1 EXTRAPOLATION 0 1` + `1 0.0 1.0`，
无人引用。结果与基线逐字节相同 —— **布局被接受**（这只验证了 §"记录布局"一节，
没有验证消费路径；后者需要一个带 `.ftr` 的完整算例，本次未做）。

---

## 5. `ARCLENGTH` —— 弧长法加载 **（在 YL 主线是死代码）**

### 记录布局（`.loa`）

```
  <ntime>  ARCLENGTH  <nstoch_curve>  <1 或 2>
  <time_begin>  <fact_inc>  <nalgo>  <giter>
  <inode>  <idofn>                            ← 仅当 nalgo==2
```
`Load.f90:192-207`。无 `dfact_curve` 行。

`Load.f90:193 arc_curve=itcurve` —— **全局只能有一条 ARCLENGTH 曲线**，写多条则最后一条生效。

`Load.f90:201-206`：`nalgo==2` 时读 `(inode, idofn)` 并转成全局方程号
`ncdis=nodfn(idofn,inode)`；`ncdis==0` 直接 `stop 'error in input of arclength control'`
（即该自由度必须是**未被约束**的活动自由度）。

### 解锁守卫（**两处，缺一不可**）

1. `.loa` 曲线的 `type_curve == 'ARCLENGTH'`；
2. **`.glb` 的 `TYPE_LOAD` 字段必须是 `ARCLENGTH`** ——
   `Global.f90:753 read(gunit,*)type_problem,type_solver,type_load,...`（第 3 位）。
   全部 `type_load=='ARCLENGTH'` 的分支（`Fem.f90:3995,4037,5183,5218,7987,8023,13174`）
   都只看 `type_load`，不看 `type_curve`。

**两个开关分处两个文件，语义耦合，任何文档都没写。** 只填其一 = 静默无效。

### 消费点

```fortran
Fem.f90:13174           if(type_load=='ARCLENGTH') tofor_arclength = 0.
Fem.f90:13277           tofor_arclength(itotv)  += pload%pxyz(idofn)      ← 点荷载参考向量
Fem.f90:13365           tofor_arclength(itotv)  += edload(idofn)          ← 边荷载参考向量
Fem.f90:13423           tofor_arclength(ldofs_f)+= rload
Fem.f90:4009/5197/8001  delta_arclength = result                          ← 切线解
Fem.f90:4038            call find_dfact_of_arclength(irst)
Solver.f90:10695-10788  弧长约束求解本体
Fem.f90:4080            tcurves(arc_curve)%piter = iiter                  ← 回写上步迭代数
```

`Solver.f90:10695-10788` 给出全部槽位语义：

| 槽位 | 语义 | 源码 |
|---|---|---|
| `time_begin` | 弧长控制的**启动时刻**；`ttime<=time_begin` 直接 return，此前是普通加载 | `Solver.f90:10708` |
| `fact_inc` | 首增量步的荷载因子增量 | `Solver.f90:10721` |
| `nalgo` | `1`=Crisfield 柱面弧长（`detal=fact_inc*‖Δp‖`）；`2`=位移控制（`detal=|fact_inc*Δp(ncdis)|`） | `Solver.f90:10726-10731` |
| `giter` | **目标迭代次数**；每步 `detal *= giter/piter` 自适应缩放弧长 | `Solver.f90:10736-10739` |
| `piter` | 上一步实际迭代次数，**不从文件读**，由 `Fem.f90:4080` 回写 | — |
| `ncdis` | `nalgo==2` 时被控自由度的全局方程号 | `Load.f90:202` |
| `detal` | 当前弧长半径，**不从文件读**，运行时演化；发散时 `Fem.f90:4043` 折半 | — |
| `tcurves(arc_curve)%dfact` | 累积荷载因子 λ，`Solver.f90:10786` 逐迭代累加 `fact_inc` | — |

`Fem.f90:12710 goto 1` —— ARCLENGTH 不经 `dfact_time_curve`，λ 完全由弧长求解器驱动。

### ★ `tofor_arclength` / `delta_arclength` 从未被 allocate

```
Global.f90:199   real(irk),allocatable :: tofor_arclength(:), delta_arclength(:)
```

**全仓四棵源码树** —— `hstarYLOrig/HSTAR`、`hstarYLOrig/next`、`HSTAR_Q`、`_archive/src`
—— `grep -ain arclength` 共 0 处 `allocate`。而 `Fem.f90:13174` 的
`tofor_arclength=0.` 位于 `FORCE_EXTERNAL`，静力 `Q` 路径必经。

**结论：`type_load='ARCLENGTH'` 一开步就写未分配数组。**

### 现成 deck 样例

**没有。** `.loa` 零命中；154 个 `.glb` 里 `type_load` 只出现 `LOAD` / `LOAD2`(7) / `MAT_DE`(3)，
**没有一个 `ARCLENGTH`**。

> ⚠ `cases/cases/test_arclength` 这个目录名**具有误导性**：它的 `1.glb` 是
> `Q PROFILE LOAD 5 ...`，`1.LOA` 是一条 `LINEAR`，与弧长法毫无关系。
> 不要把它当成 ARCLENGTH 的样例（本探针正是拿它当干净基材用的）。

### 运行证据（本文件最硬的一条）

| 探针 | 变体 | 结果 |
|---|---|---|
| P5 | `.loa` 加一条 ARCLENGTH 曲线，`type_load` 仍为 `LOAD` | **completed，与基线逐字节相同** ⇒ 记录布局正确，且单开曲线开关完全无效 |
| P6 | 同上 + `.glb` 的 `TYPE_LOAD` 改为 `ARCLENGTH` | **`forrtl: severe (174): SIGSEGV`**，`1.flavia.res` 0 字节 |

崩溃位置：`run.log` 最后打印 `ntelgroup=0` 后立即段错误 —— 正是进入
`FORCE_EXTERNAL`（`Fem.f90:13174`）的时刻。曲线本身被正确解析
（`run.log:117  ntime= 1 ARCLENGTH  0  1`）。

**ARCLENGTH 在 YL 主线是不可用的：不是"工具链不支持"，是求解器缺代码。**
这与 `project_hstarq_thermal_only_blocked` 记的那类"dispatcher 源码缺口"同型。

---

## 6. 接入 `generator.py` 各需要什么（清单，未改任何代码）

生成器侧的共同前置：`_gen_loa`（`fem-chat/skills/generator.py:574-585`）现在是
`if SEISMIC / else LINEAR` 的二分支硬编码，`nline` 也是硬编码的 `2` / `len(times)+1`。
接任何新类型都要先把它改成**按类型分派 + 按类型算 nline** 的表驱动结构。

### 6.1 `HARMONIC` —— 成本最低，建议先做

- [ ] config schema：`{"type":"HARMONIC","a0":,"amp":,"omega":,"phase":,"t_begin":,"t_end":}`
- [ ] `_gen_loa`：写 `  1  HARMONIC  0  1` + 一行 6 实数；**不写** `ttime`/`dfact` 行
- [ ] 文档/校验：`omega` 是 rad/s；`t_end` 是**持续时长**不是终止时刻；窗口外为 `1e-30`
- [ ] 校验器：若该曲线被 `.pre` 温度边界引用，提示 `dfact_temp_pre`(`Fem.f90:12555`) 无时间窗
- [ ] 无其它文件改动。运行证据已有（P2）

### 6.2 `WATERLEVEL` —— 次低，且有真实样例可对照

- [ ] config schema：`{"type":"WATERLEVEL","times":[...],"levels":[...]}`（levels 单位=高程 m）
- [ ] `_gen_loa`：头 `  <n>  WATERLEVEL  0  <n>`，随后 **n 行 `t level`**；不写尾部 dfact 行
- [ ] 与 `.pre` 联动校验（这是真正的价值所在，也是最容易错的地方）：
      引用该曲线的 fixset 必须 `ifixvar=8` 且 `jfixvar=±竖向维度号`（3D 填 3，2D 填 2），
      节点值一般填 `1`；`jfixvar=0` 会把曲线值当压力水头而非高程
- [ ] 回归对照：`cases/cases/xfj_seepage_transient` 可作为 golden
- [ ] **迁移禁令**：带 WATERLEVEL 的算例不得走 HSTAR_Q（§3 陷阱），需在 harness 门控里加一条
- [ ] 运行证据已有（P3）

### 6.3 `EXTRAPOLATION` —— 大工程，不建议在生成器层面接

不是"多写一条曲线"，而是要同时产出四处联动内容：

- [ ] `.glb`：`Global.f90:790` 记录第 6 位 `nextrf` = 外推历史深度
- [ ] `.loa`：曲线记录 `nextr ca dx`；**且**引用它的点荷载组换成
      `text` + npload 行 `i1 listep(1:2*nextr+1)` 布局（`Load.f90:274-279`）
- [ ] `.pre`：相关 fixset 头末位 `nextr/=0`，每节点追加一行 `i0 listep(1:2*nextr+1)`
      （`Prescrib.f90:214,243`）
- [ ] `.ftr`：必须存在且定义 `surface_force` 面（`Global.f90:835-885`），否则 `ftfor_ext` 无数据
- [ ] 几何前处理：`listep` 是沿特征线方向的 `2*nextr+1` 个节点串 —— 需要**新的几何选点能力**，
      现有 `mesh_io` / `gravdam_meta` 都没有
- [ ] 限制：`nextr` 只能填 1 或 2（`nextr=5` 是坏的，§4）
- [ ] 先决条件：需要一个能跑通的参考算例。**目前全仓没有**，只能从零构造，
      因此消费路径尚无任何运行证据

### 6.4 `ARCLENGTH` —— 生成器改动很小，但**当前不可交付**

生成器侧只要：
- [ ] `.loa`：`  1  ARCLENGTH  0  1` + `time_begin fact_inc nalgo giter`（nalgo=2 再一行 `inode idofn`）
- [ ] `.glb`：`TYPE_LOAD` 写 `ARCLENGTH`（`Global.f90:753` 第 3 位）
- [ ] 校验：全局至多一条 ARCLENGTH 曲线；`nalgo=2` 时 `(inode,idofn)` 必须是活动自由度
- [ ] 校验：**弧长法仅静力可用** —— `find_dfact_of_arclength` 只在 `STATIC_U` /
      `STATIC_U_reli` / `STATIC_U_PW` 里被调用，`time_dependent` 无此分支；
      `type_problem` 只能是 `Q`
- [ ] 校验：`rmesh/=0`（重网格）时边荷载不进弧长参考向量（`Fem.f90:13349`），应直接拒绝该组合

**但先决条件是求解器补洞**：在 `Fem.f90` 分配 `tofor_arclength(ntotv)` /
`delta_arclength(ntotv)`（自然位置是 `Fem.f90:234` 那批 `allocate(tofor,...)` 旁边，
条件 `type_load=='ARCLENGTH'`）。**不补洞就是 SIGSEGV（P6 已实测）。**
补洞后还需一次独立验证（软化梁 / 边坡极限荷载的 snap-through 算例），
因为 `Solver.f90:10695` 这段代码从未在本仓被执行过，其正确性完全未知。

---

## 7. 顺带查实的其它事项（不在任务范围内，但影响同一段代码）

1. **`generator.py:596` 把 `kpload` 写成了 `nplgroups`。**
   `Load.f90:229 read(loadunit,*)nplgroup,kpload`，`kpload==1` 与 `kpload==2` 是两套完全不同的
   点荷载布局（`Load.f90:233` vs `Load.f90:283-308`）。生成器写
   `f"  {nplgroups}  {nplgroups}"` —— 只有 1 个点荷载组时碰巧正确，**≥2 组时 `kpload=2`，
   求解器会去按"界面插值点荷载"格式解析，必然读错。** 未修改，仅记录。
2. **其余 9 种未支持的曲线类型**（同样只需 `_gen_loa` 分支）：
   `LNLINEAR`(取 exp)、`TEMPERATURE`、`COS`、`PEAK`(阶梯)、`FOURIERSERIES`、
   `DEXPONENTIAL`、`DABT`、`DISCONTROL`、`EQUINCRE`。
   其中 `DABT` 已有真实样例 `cases/cases/train_temp_creep/1.loa`。
   `DISCONTROL` 与 ARCLENGTH 同样需要 `.glb` 的 `TYPE_LOAD` 配套（`Fem.f90:1684-1685,2486`）。
3. **`Temper.f90:1165+ dfact_internal_heat` 是第三个独立求值器**，只认
   `LINEAR/LNLINEAR/HARMONIC/DEXPONENTIAL/DABT/HTG_EQ`，其余一律 `stop 'no type_curve'`。
   内热源曲线不能用 SEISMIC/WATERLEVEL/ARCLENGTH/EXTRAPOLATION。

## 7b. 消费侧的**完整**守卫栈（2026-08-29 补，回应"别只查一层守卫"）

`vie-ablation` 那一路发现"`fachv` 不受 `type_ABC` 守卫"漏了第二层 `force_process`
（`Fem.f90:13527`）。同样的复核在这里做了一遍：**每个消费点的全部嵌套守卫**，
逐层从外到内。READ 侧由 `data/deck-abi.json` 机械给出，消费侧（非 READ，ABI 不覆盖）
逐段读源码得出。

### HARMONIC
| 消费点 | 完整守卫栈 |
|---|---|
| `Fem.f90:12642`（`dfact_time_curve`） | `do itcurve=1,ntcurve` → `type_curve=='HARMONIC'` → 运行期 `dtbegin<=time<=dtbegin+dtend`（否则 `1e-30`）。**外面没有别的层。** |
| `Fem.f90:12555`（`dfact_temp_pre`） | 被调时才求值；`type_curve=='HARMONIC'`。**无时间窗**——这就是那处漂移 |
| `Temper.f90:1194`（`dfact_internal_heat`） | `type_curve=='HARMONIC'` |

**HARMONIC 是四种里唯一守卫栈只有一层的。**

### WATERLEVEL
| 消费点 | 完整守卫栈 |
|---|---|
| `Fem.f90:12601`（求值） | `type_curve=='LINEAR'.or.=='LNLINEAR'.or.=='WATERLEVEL'`，一层 |
| `Fem.f90:12315`（语义：水位→孔压） | ① 在 `modf_var_prescribed`（`Fem.f90:12286`）内的 `do idofix=1,ndofix` ② `type_curve/='EQUINCRE'`（`Fem.f90:12311` 的 if 先手） ③ **`ifixvar==8`** ④ **`jfixvar/=0`**。<br>**②③④ 三层缺一，曲线值的物理含义就变了**：`jfixvar==0` → `Fem.f90:12324 fixed=dfact*gamaw`（值变成压力水头）；`ifixvar/=8` → `Fem.f90:12339 fixed=dfact*vdofix`（值变成普通倍率）。<br>**"WATERLEVEL 的值是高程"只在 `ifixvar==8 .and. jfixvar/=0` 下成立。** |

### EXTRAPOLATION
| 消费点 | 完整守卫栈 |
|---|---|
| `Fem.f90:13181`（点荷载外推） | ① `FORCE_EXTERNAL`（`Fem.f90:13147`）② `do iplgroup=1,nplgroup` ③ **`nplgroup/=0`**（`Load.f90:232 goto 11` 决定该组是否存在）④ **`kpload==1`**（`Load.f90:233`；`kpload==2` 是另一套结构，无 EXTRAPOLATION 分支）⑤ `type_curve=='EXTRAPOLATION'` ⑥ 数据来自 `surface_force%ftfor_ext`，只在 **`nextrf/=0`** 时分配（`Global.f90:885`）⑦ 该数组只在 `nforce/=0.or.ngaps/=0` 时由 `force_interface` 填（`Fem.f90:9240`, `16911`）。**七层。** |
| `Fem.f90:9245`（预设位移历史） | ① `time_dependent`（`Fem.f90:8470`）② **`nextrf/=0`** ③ `do idofix=1,ndofix` ④ `type_curve=='EXTRAPOLATION'` ⑤ 分 `istep>nextrf` / 否 两支 |
| `.pre` 侧 READ `Prescrib.f90:243` | ABI 给出守卫 `… ; else ; nextr/=0`，arity `1 + 2*nextr+1` |

⚠ 其中 ③`nplgroup/=0` 是**新补的一层**：它由 `Load.f90:232` 的 `goto 11` 实现，
而 AST 的 GOTO 节点**不产生守卫**（见 §8-5），所以 Deck ABI 在 `Load.f90:236/250/274/277`
上少了这一条。原稿也少了。

### ARCLENGTH
| 消费点 | 完整守卫栈 |
|---|---|
| `Fem.f90:13174` `tofor_arclength=0.` | ① `FORCE_EXTERNAL` ② **`type_load=='ARCLENGTH'`**（`.glb`，`Global.f90:753` 第 3 位）。**两层，且这就是 SIGSEGV 触发处** |
| `Fem.f90:13277`（点荷载参考向量） | ① `FORCE_EXTERNAL` ② `nplgroup/=0` ③ `kpload==1` ④ **`type_curve/='EXTRAPOLATION'`** ⑤ `jdofn=lmdofn(idofn)/=0` ⑥ `type_curve=='ARCLENGTH'` |
| `Fem.f90:13365`（边荷载参考向量） | ① `FORCE_EXTERNAL` ② `do ielgroup=1,edge_load_group` ③ **`rmesh==0`**（`Fem.f90:13349`）④ `type_curve=='ARCLENGTH'`。<br>**③ 是新补的一层：`rmesh/=0`（重网格）分支里没有 ARCLENGTH 累加**，弧长参考荷载会漏掉全部边荷载 |
| `Fem.f90:13423`（体力/重力参考向量） | ① `FORCE_EXTERNAL` ② `associated(rload)` ③ **`fieldid(ifield)=='U'.or.=='W'`**（T 场不计）④ **`tcurvegravity(igroup)/=0`** ⑤ `type_curve=='ARCLENGTH'` |
| `Fem.f90:4038` `call find_dfact_of_arclength` | ① **只在 `STATIC_U`(3560) / `STATIC_U_reli`(4708) / `STATIC_U_PW`(7574) 三个求解器里**②`type_load=='ARCLENGTH'`。<br>**`time_dependent`（动力）里没有任何 ARCLENGTH 分支 ⇒ 弧长法是静力专用。**这是此前没写的一条 |
| `Solver.f90:10708` | 运行期 `ttime>time_begin` 才启动 |

**ARCLENGTH 的守卫栈里有两个开关分处两个文件（`.loa` 的 `type_curve` + `.glb` 的 `type_load`），
还有一个隐含的求解器族限制（仅静力）。任何一层漏掉都是静默失效，不是报错。**

## 7c. 用扩容后的工具复核（2026-08-29）

按要求用**扩到 23 个输入文件 / 2221 条 READ 的 AST** 重跑了
`extract_dispatch.py → deck_ast.py → verify_ast.py（5/5）→ dispatch_table.py`（Deck ABI 1721 条）。

| 复核项 | 结果 |
|---|---|
| 时间曲线记录是否落在新纳入的文件（`.btl`/`.sto`/`.nrt`/`.tem`/`.ftr`/`inp` …） | **没有**。ABI 里 `deck/='.loa'` 且守卫含 `type_curve` 的记录 = **0 条**。曲线表仍然只有 `Load.f90:147-223` 一个 reader |
| ABI 给出的 arity 是否与本文表格一致 | **一致**。`Load.f90:168`=6（HARMONIC）、`:182`=2×ntime（WATERLEVEL）、`:186`=4（SEISMIC）、`:190`=3（EXTRAPOLATION）、`:196`=4 + `:201`=2（ARCLENGTH，后者守卫 `nalgo==2`）、`:210`=ntime（default） |
| `.pre` 的 EXTRAPOLATION 侧 | ABI 独立给出 `Prescrib.f90:243`，arity `1 + 2*nextr+1`，守卫 `nextr/=0` —— 与本文 §4 一致 |
| 开关清单 | `type_curve` 现为 `{EXTRAPOLATION:20, SEISMIC:5, ARCLENGTH:5, HARMONIC:5, WATERLEVEL:5}`；新出现 `kpload:{1:25,2:20}`、`nextr:{0:5}`，与 §7-1 的 `kpload` bug 相互印证 |
| GOTO/LABEL 节点是否改变结论 | **补了一层守卫，不推翻任何结论**（见 §7b 的 `nplgroup/=0`） |
| `deck_text.expand()` 引号规则 | 与本文无关：本文对 deck 文本只做了 `grep` 字面统计与人工读表，没有用 expand 解析 |
| `case_path.py --switches type_curve=ARCLENGTH --deck .loa` | 正确解出 `:196` + `:201`，排除 `:168/173/182/186/190`；**但 `:210`（`case default`）仍被列出**——见 §8-6 |

**四种类型的结论一条未变。**

## 8. 仪器 bug（如实列出）

1. **`grep` 默认跳过 GBK 源码文件。** `Prescrib.f90` 含 GBK 中文注释，被 grep 判为 binary，
   **不加 `-a` 时静默返回 0 命中**。我因此一度以为 `prescrib%value_ext` / `%listep`
   在源码里不存在、`Fem.f90:9252` 是无法编译的代码。
   **本仓所有源码检索必须 `grep -a`**（`project_train09_migration` 已记过同一条，我又踩了一次）。
   连带影响：`14-facts-deck-ast.md` 的 AST 是否也漏读了 GBK 文件，值得复核。
2. **`judge.py` 第一版的 `read_error` 分类过宽**：规则是"全文含 forrtl 且全文含
   input/read"，而正常 stdout 里就有 `input`，于是把 P6 的 SIGSEGV 误判成 `read_error`
   （首跑 5/6）。改成"只看 forrtl 那一行"后 6/6。
   **改的是仪器，`predictions.json` 未动，sha256 由 judge 每次自校验。**
3. **`fem-chat/harness/_solve_deck.py:57` 用"`1.flavia.res` 是否存在"作退出码**，
   但求解器 OPEN 后崩溃会留下一个 **0 字节**的 `1.flavia.res`，于是返回 0。
   P6 的 `rc=0` 就是这么来的。判定必须看日志，不能看退出码。未修改该文件（不在我的写权限内）。
4. 我一次 `cat` 了 `xfj_seepage_transient/1.pre` 的整行节点表（4242 个节点号），
   白白灌了大量上下文。检索大 deck 应先 `cut -c1-200`。
5. **`deck_ast.py` 的 GOTO 节点不产生守卫。** `Load.f90:232 if(nplgroup==0) goto 11`
   在树里是 GOTO 节点（183 个），但 `Load.f90:236/250/274/277` 的路径条件里
   **没有 `nplgroup/=0`**。Deck ABI 因此**过列**这些记录。
   （另：`deck-ast.txt` 里 `grep -c LABEL` = 0，标号是作为构造前缀渲染的，不是独立节点，
   所以"180/379 个 GOTO/LABEL"在可读渲染里只看得到 GOTO 一半。）
6. **`case_path.py` 无法排除 `select case` 的 `case default` 分支。**
   `--switches type_curve=ARCLENGTH --deck .loa` 仍列出 `Load.f90:210`
   （default 分支的 `ttime_curve(1:ntime)`），因为 default 没有可求值的文本守卫。
   凡是 `select case` 的题目，`case_path` 的输出是**上界**不是精确路径。
7. **`decoder.py` 到不了 `.loa`。** 对 `xfj_seepage_transient`（唯一的 WATERLEVEL 真实算例）
   在 `Global.f90:905` 就停住（`type_problem` 被绑成 `type_layer1`，即 `.glb` 少读一行的方言问题，
   属 `20-facts-glb-dialects` 的范围）。**WATERLEVEL 样例的解读是人工读表得到的，不是 decoder 产物。**

## 9. 复算

```bash
cd fem-chat/docs/research/hstar-input-redesign/probe/timecurves
sha256sum -c predictions.sha256      # 必须 OK
python3 judge.py                     # 6/6，写 verdict.json
```

判定基材 `cases/cases/test_arclength` 只读；全部变体在
`/tmp/claude-1000/probe-timecurves/` 下运行。
