# 事实：`type_problem='WT'` 与 `type_ABC='MIF'` 是什么

> 2026-08-28 初稿；**2026-08-29 用扩展后的 AST（23 个输入文件 / 2385 条 READ /
> 含 GOTO 183 + LABEL 382 节点）全量复核，结论未变，新增 §3 的三条更正与仪器记录。**
> open #3 / #4 的回答。全部结论追到 `文件:行号`，源码根 `hstarYLOrig/HSTAR/`，
> 历史前处理器 `_archive/hstarpre/sourcef90/`。
> **事实**与**推断**在每节里分开标注；标为「猜测」的没有源码支撑。

## 0. 一句话结论

| | 是什么 | 证据强度 | 现成样例 |
|---|---|---|---|
| `type_problem='WT'` | 水分场 + 温度场（冰雪冻融）双场瞬态问题的**占位标记**；除了给每个组分配 2 个高斯点变量并跳过全部固体单元库初始化外，求解器里没有任何其它实现 | **源码确证（含"只有这一处"的确证）** | **无**（仓库 200+ 个 deck 里 0 个） |
| `type_ABC='MIF'` | **多次透射人工边界**（Liao 多次透射公式 MTF）+ **自由场/入射场波场分离**的地震输入方式 | **源码确证**（物理机理逐行可读）+ **hstarpre 中文标签直接写明"透射边界"** | **无**（0 个 deck 设 `ntrans>0` 或 `type_ABC=MIF`） |

---

## 0b. 方法学警告：8 个源文件是 GBK，普通 grep 会静默跳过

```
Elements.f90  Load.f90  Material.f90  meshfine.f90
Output.f90    Prescrib.f90  Solver.f90  Temper.f90
```

`grep` 把它们当二进制、只打印 "Binary file matches" 或直接不报。**必须用 `grep -a`。**
本次调查中，`prescrib%lnofixb / %ldofixb / %bfrecoord / %ifixvar0` 一度看起来
"被读、但从未被赋值"——那是假象：赋值全在 GBK 的 `Prescrib.f90:252-285`。
`epsMIFb` 同样一度看起来是死变量，实际用在 `Prescrib.f90:270`。
（这条与 `03-corrections.md` 里"把观察到的那一条路径当成全部"是同一类错误的变体：
**把工具看不见的部分当成不存在**。）

---

# 一、`type_problem = 'WT'`

## 1.1 全部出现位置（穷举，`grep -a "'WT'" *.f90`，共 4 处）

```fortran
Fem.f90:11694    if(type_problem=='WT')then !20220409 用于冰雪冻融
Fem.f90:11905    if ((jfield/=0.and.field1/='WT').or.icreep.ne.0) then   !!20220409
Fem.f90:11917    if (jfield/=0.and.field1/='WT') then                    !!20220409
Fem.f90:11923    if ((jfield/=0.and.field1/='WT').and.icreep.ne.0) then  !!20220409
```

**假阳性陷阱**：`Stiff.f90:2211 SUBROUTINE HMATRX(WT)` 里的 `WT` 是一个
`character(1)` 哑元（取值 `'W'`），与 `type_problem` 毫无关系。
`Stiff.f90:2280 if (WT=='W'.and.type_problem=='F'...)` 不是 WT 分支。
（调用点全部是 `call hmatrx('W')`：`Fem.f90:7727 / 8320 / 8747 / 9849 / 9997 / 10191 / 10437`。）

## 1.2 唯一的真实分支（事实）

`Fem.f90:11694-11705`，在 `subroutine modf_element_lib`（单元库初始化）开头：

```fortran
if(type_problem=='WT')then !20220409 用于冰雪冻融
    DO jgroup =1,ngroup
        index = group(jgroup)%index
        ngaus =elkn(index)%ggaus(1)%ngaus
        ngvar=2
        DO ielgroup = 1,group(jgroup)%nelgroup
            ielem = group(jgroup)%list(ielgroup)
            allocate(element(ielem)%field(1)%gpvar(ngvar,ngaus))
        end do
    end do
    return          ! ← 整个单元库初始化被跳过
endif
```

**语义（事实）**：给每个单元分配 **2 个**高斯点状态变量，然后 `return`。
`modf_element_lib` 余下的全部内容——应力/应变数组 `stran0`/`dsig`/`omega`、
本构模型专用数组（CONCRETE 的 `rr`、PZ 的 `iload/vdval`、GOODMAN、
`gamamax*`、板/薄膜单元的 `nstre` 覆盖等，`Fem.f90:11710-12200`）——**一概不分配**。

**推断（高置信）**：`ngvar=2` 的两个槽位是"含水率 + 含冰率"或"温度 + 含冰率"。
依据是同一批次（`!20220409`）引入的
`Global.f90:200  real,allocatable :: water_level(:),uplift_node(:),thetaice(:),velo_thetai(:)`
——`thetaice`（含冰率 θ_ice）与 `velo_thetai`（含冰率变化率）。
**但这是推断而非事实**：`thetaice` / `velo_thetai` 在整个源码树中
**只有这一条声明，没有任何读写点**（`grep -a` 全树确认）。
即冻融的状态变量声明了但从未被使用。

## 1.3 dispatcher 路径（事实）

`type_problem` 只在 `Global.f90:753` 被读入（`.glb` 第 2 条实数据记录）：

```fortran
read(gunit,*)type_problem,type_solver,type_load,type_nl,stabpw,nlayer,kglb, &
             state_change,Bparameter,balgor,upliftin
```

顶层调度（`Fem.f90:1908-1946`）里**没有任何一处测试 `=='WT'`**。因此：

```
type_problem='WT'
  → 不进 Q 静力子调度（1908）
  → 不进 E 反应谱（1940）
  → 不进 W 频域（1944）；注意 character(50) 下 'WT' /= 'W'，不会误入
  → 落入 1933: if(type_problem/='Q'.and./='E'.and./='W')
       type_solver=='EXPLICIT' ? call explicit (Fem.f90:9959 起)
                               : call time_dependent (Fem.f90:8525 起)
```

**`WT` 与 `F` / `S` 走完全相同的 reader。**

## 1.4 deck 布局差异（事实）

**没有差异。** `.man` 首记录仍是 `time_dependent` 的
`Fem.f90:8525  nincs, cdtest, earthquake_curve(1:ndimn)`，
后接 `Fem.f90:8526  nstepjq, nstepjp`。`.glb`/`.pre`/`.loa`/`.mat` 全无 WT 条件记录。
（`data/deck-abi.json` 中不存在任何以 `type_problem=='WT'` 为守卫的记录。）

**唯一的 deck 侧要求（推断）**：组的 `fieldid` 应写成 `'WT'`（`.glb` 组记录，
`Global.f90:1115` 读入 `group(igroup)%fieldid`），这样单元有 2 个场。

## 1.5 三处 `field1/='WT'` 是死守卫（事实）

`Fem.f90:11905/11917/11923` 全部位于
`Fem.f90:11735  if (field1(1:1)=='U') then` … `Fem.f90:12134  endif !for field(1:1)='U'`
这个块**内部**。块内 `field1` 首字符必为 `'U'`，故 `field1/='WT'` **恒真**。
这三个 20220409 的补丁不改变任何行为。

**推断**：作者的本意大概是"当组既含温度场又含水分场时，不要按热应力路径分配
应力数组"，但写在了错误的分支里；真正生效的是 1.2 那个 `return`。

## 1.6 WT 的实现完成度（推断，高置信）

WT 是**未完成的能力**，理由三条，全部可复核：

1. `modf_element_lib` 只分配 `gpvar`，**没有任何 W–T 耦合刚度/耦合矩阵的组装分支**。
   `hmatrx` 只接受 `'W'`；`Elements.f90` 里所有两场单元的 `couple(1)%field_couple=(/1,2/)`
   是通用声明，不带 W–T 本构。
2. 状态变量 `thetaice` / `velo_thetai` 声明后零引用（`Global.f90:200`）。
3. `Fem.f90:11905/11917/11923` 的补丁写进了不可达分支（§1.5）。

## 1.7 样例（事实）

仓库 `cases/` + `_archive/` 共 171 个 `1.glb`，`type_problem` 取值分布：

```
Q 112    F 22    E 10    S 7    (20 个文件未匹配到该记录，多为片段/模板)
WT 0     W 0
```

**没有任何 WT 算例。** `_archive/hstarpre` 的 20 套 `.ctl` 里也没有。

---

# 二、`type_ABC = 'MIF'`

## 2.1 名字的直接证据（事实 + 猜测）

`_archive/hstarpre/sourcef90/fempre.f90:1741`（GBK，已转码）：

```fortran
write(chk_unit,4)'粘弹性边界（VIE）或透射边界（MIE）=',type_ABC
```

`fempre.f90:2069`：

```fortran
write(chk_unit,*)'    ****与MIF动力边界条件相关控制参数******'
```

**事实**：历史前处理器把 `type_ABC` 的两个取值分别标注为
**VIE = 粘弹性边界**、**另一个 = 透射边界**（拼作 `MIE`，同一处上下文写 `MIF`）。
**猜测**：字面缩写可能是 *Multi-transmitting Input Formula* / *Multi-transmitting
Interface*，或就是 MTF（Multi-Transmitting Formula，廖振鹏多次透射公式）的手误变体。
**缩写展开是猜测；"MIF = 透射边界"是事实。**

## 2.2 物理：二阶多次透射公式 + 波场分离（事实，逐行）

### (a) 外推系数由 `s = cₐΔt/Δx` 生成 —— `Fem.f90:8630-8641`

```fortran
if (ntrans>0)then
    s=camif*ditime/dxmif
    k1(1)=(s-3)*s/2+1 ;  k1(2)=(2-s)*s      ;  k1(3)=(s-1)*s/2
    k2(1)=(2*s-3)*s+1 ;  k2(2)=4*(1-s)*s    ;  k2(3)=(2*s-1)*s
    k3(1)=4.5*(s-3.0)*s+1. ; k3(2)=3.0*(2.0-3.0*s)*s ; k3(3)=1.5*(3.0*s-1.0)*s
endif
```

`k1/k2/k3` 声明为 `Global.f90:71  real k1(3),k2(3),k3(3)`。
这是把 `u(x_b − jcₐΔt)` 用**边界内侧 3 个等间距点**（间距 `dxmif`）的二次
Lagrange 插值表出的系数，j = 1, 2, 3。

### (b) 边界位移递推 —— `Fem.f90:12345-12375`（`subroutine modf_var_prescribed`）

```fortran
if (type_problem=='F'.and.ntrans>0)then
    ldofixb=>prescrib(idofix)%ldofixb
    bb=1.0/(gamaMIF+1.0)
    istep==1 :  fixed(ldofix)= inpru/inpzi(ldofix)
    istep==2 :  fixed(ldofix)= 2*bb*(k1 .d. disA_1(ldofixb)) + inpru(ldofix)
    istep>=3 :  fixed(ldofix)= 2*bb*(k1 .d. disA_1(ldofixb))
                             - bb**2*(k2 .d. disA_2(ldofixb)) + inpru(ldofix)
```

这正是**二阶 MTF**：`u^{n+1}_b = 2u^n_1 − u^{n−1}_2`（`u_j` 为沿波传播方向
第 j 个内点的插值值），其中 `bb = 1/(1+γ)` 是廖振鹏的**漂移失稳抑制因子**
（`gamaMIF` = γ）。历史值 `gamaMIF=0.02`。
`disA_1/disA_2`、`disB_1/disB_2` 是散射场的前一步/前两步历史，
在时间步循环开头轮转：`Fem.f90:8650-8653`。

**分支 `ifixvar0_inpb==ifixvar0`（底边界）用 `disA`+`inpru`，否则（侧边界）用
`disB`+`inpzi`。**

### (c) 波场分离 —— `Fem.f90:9266-9285`

```fortran
if(type_ABC=='MIF')then
    do idofix=1,ndofix
        do ilaymif=1,nlaymif
            disA(ldofixb(i)) = result_zero(ldofixb(i)) - inpru(ldofixb(i))
            !对底边界，将总波场分解为入射波场与散射波场，disA即为散射波
            disB(ldofixb(i)) = result_zero(ldofixb(i)) - inpzi(ldofixb(i))
            !对侧边界，将总波场分解为自由波场与散射波场，disB即为散射波
            !原因在于透射边界仅对散射波场，保证散射波场能够穿过人工边界而透向无限远处，
            !但同时与要允许入射波场能够向上传播，故进行波场分离。
        end do
    end do
endif
```

**这是 MIF 与 VIE 的本质区别**：VIE 用粘弹性人工边界（弹簧+阻尼器）+ 入射
位移/速度波等效力；MIF 用**位移外推型透射边界**，且必须先把总场减去
已知场（底边界减入射场、侧边界减自由场）得到散射场，只让散射场透射出去。

### (d) 入射场与自由场的构造 —— `Fem.f90:17208-17245  subroutine modf_inpwav`

```fortran
iwavcurve=earthquake_curve_MIF(ifixvar)      ! 17219  槽=方向，值=曲线号
if(iwavcurve==0)cycle
inpvar=abs(ifixvar0_inpb)
if (ifixvar0_inpb==ifixvar0)then             ! 底边界
    do ilaymif=1,nlaymif
        tcurves(iwavcurve)%dtbegin = abs(coord(inpvar,lnofixb(i))-inpcord)/camif
        call dfact_time_curve(ttime)
        inpru(ldofixb(i)) = tcurves(iwavcurve)%dfact   ! 入射位移波
        tcurves(iwavcurve)%dtbegin = 0.0
    enddo
else                                          ! 侧边界
        dfact1 = 曲线延迟 |coord−inpcord|/camif          ! 上行入射波
        dfact2 = 曲线延迟 |bfrecoord−inpcord|/camif
                        + |coord−bfrecoord|/camif        ! 自由面反射后的下行波
        inpzi(ldofixb(i)) = dfact1 + dfact2              ! 二者迭加 = 自由场
endif
```

**事实**：MIF 用**一维竖向传播**假定构造自由场——把同一条地震时程按
走时 `距离/camif` 平移，侧边界上再叠加一次经自由面（坐标 `bfrecoord`）反射的下行波。
`inpcord` = 入射面（基底）在 `abs(ifixvar0_inpb)` 轴上的坐标。
`camif` 同时是外推波速与走时波速。

调用点 `Fem.f90:8702-8704`（每个时间步）：
```fortran
allocate(inpru(ntotv),inpzi(ntotv)) ; inpru=0.0 ; inpzi=0.0
if(type_abc=='MIF')call modf_inpwav
```
`Fem.f90:9285  deallocate(inpru,inpzi)` —— 每步重建。

**关键耦合（事实）**：`inpru/inpzi` 恒被分配并清零，但只有 `type_ABC=='MIF'`
才填值；而 `Fem.f90:12345` 的透射递推只看 `type_problem=='F' .and. ntrans>0`。
所以：
- `ntrans>0` 且 `type_ABC/='MIF'` → 纯透射边界，**无入射波**（`inpru=inpzi=0`），
  即"总场即散射场"，只能做自由振动/内源问题。
- `type_ABC=='MIF'` 且 `ntrans==0` → 读了 `.man` 那条记录、也算了入射场，
  但 `ldofixb` 从未分配（见 2.4），**波场分离 `Fem.f90:9269` 会解引用未关联指针**。

**两个开关必须同时打开。**

## 2.3 dispatcher 路径（事实）

```
.glb  Global.f90:728   type_ABC          （ninit,…,equvs,type_ABC,block_stab,… 记录的第 12 格）
.glb  Global.f90:1000  ntrans,nlaymif,epsMIFb,gamaMIF,ifixvar0_inpb,camif,dxmif
.pre  Prescrib.f90:213/214  约束集头记录二选一（见 2.4）
.pre  Prescrib.f90:228  frecoord(1:nfixnods)   ⇐ ntrans>0 .and. ifixvar<=ndimn
.man  Fem.f90:8530     inpcord,earthquake_curve_MIF(1:ndimn)  ⇐ type_ABC=='MIF'
```

`.man:8530` 位于 `time_dependent`（`Fem.f90:8525` 起）。
**`explicit` reader（`Fem.f90:9958-9959`）里没有这条记录**——
`nincs, earthquake_curve(1:ndimn)` 之后直接进增量循环。
所以 **MIF 与 `type_solver=='EXPLICIT'` 不兼容**：显式路径既不读那条记录，
也不调用 `modf_inpwav`。

综合可达条件：

```
type_problem=='F'                    （Fem.f90:12345 硬要求；F 之外透射递推不生效）
type_solver /= 'EXPLICIT'            （否则 .man:8530 不被读，deck 会错位）
type_ABC=='MIF'
ntrans>0
nlaymif==3                           （见 2.5 的尺寸约束）
```

`tools/case_path.py --switches type_ABC=MIF,type_problem=F --deck .man` 解出 184 条，
其中 176 条守卫未定——工具目前不做守卫求值（`14-facts-deck-ast.md §5.1` 的已知边界），
所以这里的 deck 布局是**手工从 reader 逐行剥出来的**，
但 `data/deck-abi.json` 独立给出了完全一致的 4 条 MIF/ntrans 条件记录
（`.glb:1000`、`.pre:213`、`.pre:214`、`.pre:228`、`.man:8530`），互为印证。

## 2.4 deck 布局差异（事实，相对 `type_ABC='FIX'`）

### `.glb` —— 记录已存在，只是所有既有算例填 0

`Global.f90:999-1000`：
```
text                                   ← 标签行，内容任意
ntrans nlaymif epsMIFb gamaMIF ifixvar0_inpb camif dxmif
```

| 槽 | 变量 | 语义（消费点） |
|---|---|---|
| 1 | `ntrans` | 透射边界总开关；`>0` 生效。`Fem.f90:8630`、`12345`、`Prescrib.f90:225`。**注意：阶数没有用它**——见 2.5 |
| 2 | `nlaymif` | 边界内侧参与外推的点数。`Prescrib.f90:262-286` 按它建表；`Fem.f90:9270`、`17225` 按它循环 |
| 3 | `epsMIFb` | 找内侧点时的坐标匹配容差。`Prescrib.f90:270  all(abs(coord(:,ipoin)-xyzx)<=epsMIFb)` |
| 4 | `gamaMIF` | 廖氏漂移抑制系数 γ；`bb=1/(γ+1)`。`Fem.f90:12347` |
| 5 | `ifixvar0_inpb` | **带符号**的轴号，标识"哪个约束集是底/入射边界"。`Fem.f90:12351/17224` 用它与每个约束集的 `ifixvar0` 比对；`abs()` 用作走时坐标轴 `Fem.f90:17223` |
| 6 | `camif` | 人工边界波速 cₐ（外推 + 走时）。`Fem.f90:8631`、`17226/17233/17236` |
| 7 | `dxmif` | 内侧点间距 Δx。`Fem.f90:8631`；`Prescrib.f90:269` 用它生成内侧点坐标 |

### `.pre` —— 约束集头记录**多一格**，另**多一条记录**

> ⚠ **9 格 ⇏ MIF**（2026-08-29 复核新增）：`nbackdT==2` 分支下的约束集头记录
> `Prescrib.f90:185` **无条件**就是 9 格（含 `ifixvar0`），与 `type_ABC` 无关。
> 导入器不能用"头记录有几格"反推 `type_ABC`；必须先读 `.glb` 的 `type_ABC` 与 `nbackdT`。

`Prescrib.f90:213-214`（互斥二选一）：

```fortran
if (type_abc=='MIF') read(punit,*) ifixvar,ifixvar0,nfixnods,itcurve,tfixvar,outfix,jfixvar,gamawx,nextr   ! 9 格
if (type_abc/='MIF') read(punit,*) ifixvar,        nfixnods,itcurve,tfixvar,outfix,jfixvar,gamawx,nextr   ! 8 格
```

**`ifixvar0` 插在第 2 格**——这是一个**记录布局漂移**，与 `01-facts §3`
的 `type_solver` 改布局同类。`ifixvar0` 的语义（`Prescrib.f90:269`）：

```fortran
xyzx(abs(ifixvar0)) = coord(abs(ifixvar0),jpoin) + (ilaymif-1)*dxmif*real(ifixvar0)/real(abs(ifixvar0))
```

即 **`ifixvar0` = 该边界向模型内部推进的带符号轴号**（`+2` = 沿 +y 向内，
`-1` = 沿 −x 向内）。`ifixvar0_inpb` 与之相等的那个集就是入射（底）边界。

`Prescrib.f90:225-228`（在 `val_fix` 之后）：

```fortran
if (ntrans>0 .and. ifixvar<=ndimn) then
    read(punit,*) frecoord(1:nfixnods)   ! 自由面坐标，逐节点一个实数
end if
```

`frecoord` 存进 `prescribx(ndofix)%bfrecoord`（`Prescrib.f90:261`），
在 `Fem.f90:17236` 用来算"入射波传到自由面再反射下来"的走时。

### `.man` —— 多一条记录

`time_dependent` 头部完整顺序（`Fem.f90:8524-8530`）：

```
text
nincs, cdtest, earthquake_curve(1:ndimn)
nstepjq, nstepjp                                  ← 20231215YL 新增，VIE/MIF 之前
[type_ABC=='VIE'] hwdirec, hcoord
[type_ABC=='VIE'] inpcord, eq_curve_d(1:ndimn), eq_curve_v(1:ndimn)
[type_ABC=='MIF'] inpcord, earthquake_curve_MIF(1:ndimn)
```

**`earthquake_curve_MIF` 与 `earthquake_curve` 一样是"槽=方向，值=曲线号"**
（`Fem.f90:17219  iwavcurve=earthquake_curve_MIF(ifixvar)`，`ifixvar` 是被约束的自由度方向）。
与 CLAUDE.md 里 PRJ-6057 那条规则同构。

### `.loa` —— 曲线类型受限（事实）

`modf_inpwav` 通过**临时改写 `tcurves(iwavcurve)%dtbegin`** 实现走时延迟。
`dtbegin` 只在三种曲线下被 `allocate`：
`HARMONIC`（`Load.f90:166`）、`FOURIERSERIES`（`Load.f90:171`）、
`SEISMIC`（`Load.f90:185`）。其它类型（LINEAR/WATERLEVEL/PEAK/…）该指针未分配。

> **因此 `earthquake_curve_MIF` 指向的曲线必须是 SEISMIC（或 HARMONIC /
> FOURIERSERIES）**，否则 `Fem.f90:17226` 写未分配指针。
> 且 `dfact_time_curve` 在 `time<dtbegin` 时返回 `1.e-30`（`Fem.f90:12649-12651`、
> `12681` 附近），这正是"波还没传到"的实现方式。

## 2.5 三个必须知道的坑（事实 + 推断）

1. **`nlaymif` 事实上必须 = 3。**
   `k1/k2` 是 `real(3)`（`Global.f90:71`），而 `Fem.f90:12359/12366` 做
   `k1 .d. disA_1(ldofixb)`，`ldofixb` 长度 = `nlaymif`（`Prescrib.f90:262`）。
   `.d.`（`Array.f90:11` 定义的点积）在长度不等时越界/形状不符。
   deck 里那行历史缺省 `nlaymif=0` 与实际要求不符——**任何人照抄现有 deck 打开
   `ntrans` 都会崩**。

2. **`ntrans` 只是开关，不是阶数。**
   `k3`（三阶系数）在 `Fem.f90:8638-8640` 算出后**在全树中再无引用**
   （`grep -a k3` 只有这三行）。`Fem.f90:12345-12374` 无条件走二阶。
   *推断*：三阶 MTF 写了一半。

3. **`ntrans>0` 时，凡 `ifixvar>ndimn` 的约束集会崩。**
   `ldofixb` 只在 `ntrans>0 .and. ifixvar<=ndimn` 时被 `allocate`
   （`Prescrib.f90:225/262`），而 `Fem.f90:12348` 对**所有** `idofix` 无条件
   `ldofixb=>prescrib(idofix)%ldofixb` 并在 12359 解引用。
   孔压（`ifixvar=8`）、温度（`ifixvar=10`）等约束集与 MIF 同时存在即为未定义行为。
   *这是推断（未跑实验证实），但指针未关联是源码可确证的。*

4. **`modf_inpwav` 破坏原曲线的 `dtbegin`。**
   `Fem.f90:17228/17240` 用完后恢复成 `0.0` 而不是原值。
   若 `.loa` 里该 SEISMIC 曲线本来 `dtbegin/=0`，第一步之后就丢了。

## 2.6 样例（事实）

- 仓库 `cases/` + `_archive/` 全部 `.glb`：**`ntrans` 一律为 `0`**
  （`grep -a` 逐文件核对 200+ 个 deck；唯一"非零"的第 2 格是
  `train_temp_creep/1.glb` 等 8 个文件的 `nlaymif=3, camif=1000, dxmif=10`，
  但它们 `ntrans=0`）。
- `type_ABC` 取值统计（172 个 `.glb`，按文件计）：含 `FIX` 160 / 含 `VIE` 12 / `type_ABC=MIF` **0**。
  其中 6 个文件同时出现 `FIX` 与 `MIF` 字样——那 6 处 "MIF" 全部是标签行
  （`MIF params` / `ntrans,nlaymif,epsMIFb,...`），`type_ABC` 仍是 `FIX`。
- `_archive/hstarpre` 的 20 套 `.ctl`：**0 个**设 MIF；但**多套 `.ctl` 的内嵌文档
  写明了这条记录**，例如
  `_archive/hstarpre/controlfile/examples/典型算例文件/隧洞衬砌/lining/1.ctl:441`：
  ```
  'If (type_ABC =='MIF')输入：read(mainunit,*)inpcord,earthquake_curve_MIF(1:ndimn)'
  ```
  这是**一手的历史文档证据**（与 `.man` reader 完全一致），但**不是样例**。

**结论：没有任何可回归的 MIF 算例。** `03-corrections.md` 的判据在此适用——
第一个 MIF 算例不能靠"跑通"验收，必须做**消融/解析对拍**（见 2.7）。

## 2.7 接入工具链需要什么

### `generator.py` 侧（写 deck）

| 文件 | 动作 |
|---|---|
| `.glb` | 第 12 格写 `MIF`；MIF 参数行写 `ntrans=1, nlaymif=3, epsMIFb=<网格容差>, gamaMIF=0.02, ifixvar0_inpb=<±轴号>, camif=<波速>, dxmif=<内侧点间距>` |
| `.pre` | **每个约束集头记录改成 9 格**（插入 `ifixvar0`）；位移类集（`ifixvar<=ndimn`）在 `val_fix` 后加一行 `frecoord(1:nfixnods)` |
| `.man` | `nstepjq,nstepjp` 之后加一行 `inpcord, earthquake_curve_MIF(1:ndimn)` |
| `.loa` | 目标曲线必须是 `SEISMIC` |
| 网格 | 人工边界每个节点，沿 `sign(ifixvar0)` 方向、间距 `dxmif`，必须**恰好**存在 3 个内侧节点（`Prescrib.f90:272-282` 找不到唯一匹配就 `stop`） |

**网格约束是硬的**：`dxmif` 必须等于人工边界法向的实际网格步长，且该方向
网格必须均匀 3 层以上。这不是"参数"，是**网格生成的前置条件**——
应进 `mesh-and-geometry.md` 而不只是模板。

### 验收（不能只看"跑通"）

1. **一维自由场对拍**：单柱网格 + 底边界 MIF，检查侧边界处
   `inpzi` 与解析自由场（入射 + 自由面反射）逐点一致。
2. **消融**：`ntrans` 0↔1 对比，看人工边界处是否消除反射（`disA` 应随时程衰减而不驻留）。
3. **与 VIE 交叉验证**：同一网格同一地震动，VIE 与 MIF 的坝顶时程应量级一致。

### 对 `WT`

**不建议接入。**§1.6 三条证据表明它没有实现体。若将来要做冻融，
真正缺的是 W–T 耦合本构与 `thetaice` 的演化方程，
不是 deck 格式——deck 侧与 `F`/`S` 完全相同，工具链已经能写。

---

# 三、2026-08-29 复核：用扩展后的 AST + `case_path.py` 重跑

工具在初稿之后有两处变化，都可能推翻结论，因此全部重跑：
AST 从 6 个输入文件扩到 **23 个**（`data/deck-ast.json`，2385 条 READ），
并新增 **GOTO(183) / LABEL(382)** 节点。

## 3.1 结果：两条主结论都不变（事实）

### (a) WT 的 deck 布局 = `S`，与 `F` 只差 2 条（**工具独立复现**）

```
python3 tools/case_path.py --switches type_problem=WT --json   → 627 条唯一记录
python3 tools/case_path.py --switches type_problem=S  --json   → 627 条
python3 tools/case_path.py --switches type_problem=F  --json   → 629 条

WT △ S = ∅                       ← 完全相同
F − WT = 2 条:
    .man Fem.f90:18259
    .mat Material.f90:493  DuncanChang%k1,k2,nd,lamdaMax
```

两条都是被 `type_problem=='F'` 自身守卫的记录。
**这独立证实了 §1.4 的手工结论：`WT` 不改变任何 deck 记录。**

顺带一条本次才看见的事实（不在本任务范围，供后续）：
**`.mat` 的 DuncanChang 记录条数随 `type_problem` 变化**
（`Material.f90:493` 只在 `type_problem=='F'` 下读 4 个附加参数），
这是 `.mat` 的又一处布局漂移。

### (b) 全树没有任何 deck READ 被 `WT` 守卫（**新 AST 穷举**）

遍历新 AST 全部 2385 条 READ 的路径条件，涉及 `type_problem` 的守卫**只有 5 种**：

```
type_problem=='Q'   type_problem=='E'   type_problem=='W'   type_problem=='F'
type_problem/='Q'.and.type_problem/='E'.and.type_problem/='W'
```

**没有 `=='WT'`，也没有任何含 `WT` 字样的守卫。**

### (c) MIF 的 deck 差异：`case_path` 差集与手工剥出的完全一致

```
type_ABC=MIF,type_problem=F  vs  type_ABC=FIX,type_problem=F
  MIF 独有: .man Fem.f90:8530  inpcord, earthquake_curve_MIF(1:ndimn)
            .pre Prescrib.f90:213  (9 格头记录，含 ifixvar0)
  FIX 独有: .pre Prescrib.f90:214  (8 格头记录)
对照 VIE 独有: .man 8528 hwdirec,hcoord / .man 8529 inpcord,eq_d,eq_v / .pre Fem.f90:8546 nbounods
```

`.pre Prescrib.f90:228 frecoord` 在两边都出现——因为它的守卫是
`ntrans>0.and.ifixvar<=ndimn`，与 `type_ABC` 无关（见 3.3 的仪器说明）。
这不是矛盾：`ntrans>0` 与 `type_ABC='FIX'` 在源码里确实可以并存（§2.2 末）。

### (d) GOTO 不影响本结论（事实）

在新 AST 里检索 MIF 相关代码区间的 GOTO / LABEL 节点：

```
Fem.f90 8400–8760   （time_dependent 头部 + MIF 分配 + modf_inpwav 调用）→ 0 个
Prescrib.f90 150–340（.pre 约束集读取 + MIF 内点建表）                  → 0 个
```

**这两段没有任何标号跳转**，所以"顺序穿过 goto"的隐患在此不成立。

## 3.2 更正（相对本文件初稿）

| # | 初稿说法 | 更正 |
|---|---|---|
| 1 | "`.pre` 头记录 9 格 ⇔ `type_ABC=='MIF'`" | **不对**。`nbackdT==2` 分支的 `Prescrib.f90:185` 也是 9 格且无条件。已在 §2.4 加警告 |
| 2 | 只报了 `data/deck-abi.json` 里 4 条 MIF 记录 | 新 AST 下 `.pre` 侧还应连带 `Prescrib.f90:185` 一起看（共 3 条 `.pre` 变体 + 1 条 `.man` + 1 条 `.glb`） |
| 3 | 未说明 `frecoord` 为何在 FIX 路径里也出现 | 其守卫是 `ntrans`，不是 `type_ABC`；见 3.1(c) |

**没有一条主结论被推翻**：WT 仍是无实现体的占位符，MIF 仍是多次透射边界 + 波场分离。

## 3.3 踩到的仪器问题（如实列出）

1. **`data/deck-abi.json` 相对新 AST 是陈旧的。**
   `deck-ast.json` 时间戳 `08-29 00:02`，`deck-abi.json` 停在 `08-28 23:49`，
   条目数仍是 1716。`dispatch_table.py` 未随 AST 重建一起跑。
   *本文件的 ABI 引用因此改为直接遍历 `deck-ast.json`。*
   （按任务约定我不写 `data/`，故未重新生成——**建议 owner 补跑
   `python3 tools/dispatch_table.py`**。）

2. **`case_path.py` 静默丢弃它不认识的开关名。**
   `--switches type_ABC=MIF,type_problem=F,ntrans=1` 的输出里
   `"switches": {"type_abc": "MIF", "type_problem": "F"}`——`ntrans` 没了，
   **没有任何警告**，且结果与不给 `ntrans` 时逐条相同（625 vs 625）。
   使用者会误以为"`ntrans` 不影响 deck"，而实际上 `Prescrib.f90:228`
   正是被它守卫的。**建议：未知开关名应报错或至少 warn。**

3. **8 个求解器源文件是 GBK，普通 `grep` 静默跳过**（见 §0b）。
   这条不是新工具的问题，但它是本次调查里唯一一次真的把我引向错误结论
   （`epsMIFb` / `prescrib%lnofixb` 一度被判为死代码）。
   AST 工具本身读到了 `Prescrib.f90`（`.pre` 125 条记录在树里），
   **所以是"人用 grep"与"工具用 AST"之间的口径差**，
   任何人工复核这些文件时必须 `grep -a` 或先 `iconv`。

4. **`tools/case_path.py` 的"确定/未定"计数会随口径大幅跳动。**
   同一开关集下，`--deck .man` 报 191 条、全量报 1814 条；
   未定守卫占 90% 以上。这不是 bug（`14-facts §5.1` 已声明守卫未求值），
   但**差集比较（A vs B）是可靠的，绝对条数不是**——本节全部用差集。

---

## 附：复核命令

```bash
cd /home/huijun/HSTAR_Next/hstarYLOrig/HSTAR
grep -an "'WT'" *.f90                      # 4 处，只有 11694 是真分支
grep -an "MIF\|ntrans\|nlaymif\|camif\|dxmif\|gamaMIF\|epsMIFb" *.f90
iconv -f GBK -t UTF-8 Prescrib.f90 | sed -n '205,290p'   # .pre 的 MIF 布局
iconv -f GBK -t UTF-8 ../../_archive/hstarpre/sourcef90/fempre.f90 | sed -n '1741p'
cd /home/huijun/HSTAR_Next/fem-chat/docs/research/hstar-input-redesign
python3 -c "import json;d=json.load(open('data/deck-abi.json'))['deck_abi'];\
[print(r['deck'],r['file'],r['line'],r['vars']) for r in d if 'MIF' in str(r) or 'ntrans' in str(r)]" | sort -u
```

### 2026-08-29 复核用（差集法，绝对条数不可信，差集可信）

```bash
cd /home/huijun/HSTAR_Next/fem-chat/docs/research/hstar-input-redesign
for sw in "type_problem=WT" "type_problem=F" "type_problem=S" \
          "type_ABC=MIF,type_problem=F" "type_ABC=FIX,type_problem=F" "type_ABC=VIE,type_problem=F"; do
  python3 tools/case_path.py --switches "$sw" --json > "/tmp/$(echo $sw|tr ',=' '__').json"
done
# 再对 json['path'] 取 (deck,file,line,vars) 集合做差集
```
