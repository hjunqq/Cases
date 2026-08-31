# 迁移报告 B 组：`train_slope_unknown` / `train_vie_boundary` / `train_temp_creep`

> 2026-08-29。承 `13-probe-report-old-format-peel.md`（机械迁移形态）与
> `20-facts-glb-dialects.md`（`.glb` 头两种方言）。
> 备份：`/tmp/claude-1000/migrate-B/<name>.orig`（迁移前逐字节副本）。
> 求解一律经 `fem-chat/harness/_solve_deck.py`，工作副本在
> `/tmp/claude-1000/migrate-B/run/`，`cases/` 里不留求解产物。

## 〇、一页结论

| 算例 | decoder 迁移前 | decoder 迁移后 | 求解器 |
|---|---|---|---|
| `train_slope_unknown` | 停在 `Global.f90:835` (.ftr)，`.glb` 22/65 行，且 `.glb` **绑定值已经错位**（`type_problem` 读到的是下一条记录的标签行） | **走完整棵树**，`.glb`/`.mat`/`.ifs`/`.pre`/`inp` 全 100% | exit 0，100 步跑完，**但力学判据 fail，见 §7.1** |
| `train_vie_boundary` | 同上，`.glb` 22/81 行 | **走完整棵树**，`.glb`/`.ifs`/`.loa`/`.man`/`.mat`/`.nrt` 全 100% | exit 0，250 步收敛，**放大系数 1.10 触警，见 §7.2** |
| `train_temp_creep` | 停在 `Global.f90:834` (.ftr 0 字节)，`.glb` 28/54 行，`nelem=3 ndimn=1`（方言 B 误解析） | 头部标量全部正确；`.ftr`/`.nrt`/`.mat` 100%，停点是 **decoder 自身的仪器 bug**（见 §5） | 求解器**读完了全部 10 个输入文件**，在 PARDISO 单元组装里 SIGSEGV；**未归因到任何 deck 字段，没有猜** |

> **验收口径（2026-08-29 升级）**：不再看"位移量级/残差像不像话"，改用**不依赖参照算例的
> 力学判据**逐条判——整体力平衡、自重合力对账、极值原理、辐射衰减、符号与量级。
> 全部结果在 **§7**。按"任何一条不满足即不放行"的规则，**三个算例目前一个都不放行**：
> `slope` 力平衡与收敛 fail（但已证明**不是迁移引入的**，§7.1）、
> `vie` 放大系数 1.10 触警（§7.2）、`temp_creep` 无结果可判（§7.3）。

**`train_vie_boundary` 的 `force_process` = `222*1`，即 ngroup=5 全部为 1 —— 惯性力通路是打开的。**
（对照 `19-probe-report-vie-ablation.md` 里 `train10_dynamic_vie` 的 `0 0 0 0 0`。这是 open #15 的输入数据：
同一批 VIE 算例里，两种取值都出现过，`train10` 的全 0 不是"VIE 算例的通例"。）

---

## 一、`13-probe` 的形态是对的，但只覆盖了迁移的 1/4

探针 3 给出的规则——**按标签名对齐、源码有而标签没有的插 0**——在 B 组一次也没失效。
但探针只跑到"求解器第一次报错的地方就换文件了"，所以它列的 4 条记录只是 `.glb` 里的前 4 条。
实际把整个 deck 走完，`.glb` 一个文件就有 **9 处**记录级差异，另有 5 个文件各有自己的差异。

探针漏掉后 5 处的原因值得记一笔：**`.glb` 里 `gid_*` 那条记录（15→20 字段）会被
list-directed READ 悄悄吃掉下一行的标签行**，只是下一行第一个 token 是 `res_u` 这种非数字，
才在更远处炸出 severe(59)。它属于 `10-roadmap.md §0` 说的"读到了而且是错的"类别，
不是被协议兜住的，是被运气兜住的。

### 1.1 `.glb` 全部 9 处（`train_slope_unknown` / `train_vie_boundary` 相同）

| # | 记录 | deck → 源码 | 源码行 | 补法 |
|---|---|---|---|---|
| 1 | `NINIT …` | 11 → 19 | `Global.f90:747` | 插 `winit`；尾补 `block_stab nbackf nbspring ebody outind nbackdT ninistn` = 0 |
| 2 | `TYPE_PROBLEM …` | 7 → 11 | `Global.f90:753` | 尾补 `state_change Bparameter balgor upliftin` = 0 |
| 3 | `NMASS …` | 10 → 11 | `Global.f90:764` | 尾补 `ECWPIPE` = 0 |
| 4 | `NTSMAT …` | 6 → 7 | `Global.f90:775` | 尾补 `submodel` = 0 |
| 5 | `gid_*` | 15 → 20 | `Global.f90:960` | 尾补 `gid_Mxy gid_bem gid_wh gid_wv gid_bcs` = 0 |
| 6 | `res_*` | 15 → 17 | `Global.f90:963` | 尾补 `res_Tv res_Pa` = 0 |
| 7 | `water_level` / `modf_dis_blocks` | **两条记录整体缺失** | `Global.f90:1006` / `:1008` | 各插「标签行 + 值行」，值 0 |
| 8 | `nbackf` 后那条 `text` | **缺 1 条 text 记录** | `Global.f90:1015` | 插一行占位文本 |
| 9 | group 记录 | 16 → 18 | `Global.f90:1114` | 尾补 `uplift_ic liquj` = 0（每组各一次） |
| 10 | group 的 `order_time` | **整条记录缺失** | `Global.f90:1131` | 每组插 `0 0`（nrfields=1） |
| 11 | `ngaps …` | 7 → 14 | `Global.f90:3330` | 见 §2.1 |
| 12 | `nrcsteel` / `nwcpipe` | **两条记录整体缺失** | `Global.f90:4536` 及 `link_concrete_and_water_pipe` | 各插「标签行 + 0」 |

第 10 条的依据：deck 自己的表头只列了 `(1) 组记录 / (2) TYPE_MASS / (3) nfdof,listdof` 三项，
现行源码在 (2) 和 (3) 之间多读一条 `order_time`。值取 `0 0`——`train01_gravdam_static`（静力）
与 `train10_dynamic_vie`（动力）**都**写 `0 0`，且 `Stiff.f90:3350` 对 `type_problem=='F'`
在 `order_time==0` 时给出 `coef=beeta2*Δt²+β·beeta1·Δt`，正是 Newmark 动力系数。

### 1.2 `.glb` 之外的 5 个文件

| 文件 | 差异 | 源码行 |
|---|---|---|
| `.ftr` | `nforce`（1 项）→ `nforce,ngaps,nforce_gaps,nsafety_gaps`（4 项） | `Global.f90:835` |
| `.nrt` | 旧格式只有 **1 行表头**，现行读 **2 行**再读 `transgroup` | `Global.f90:1361-1363` |
| `.mat` | 缺 `nmats` 记录（标签行 + 值）；`SOLID` 记录 8 → 10（`kind_wt jliqu`）；缺 `iE,iNu,density_w` 记录 | `Material.f90:271` / `:289` / `:291` |
| `.LOA` | 时间曲线头 `ntime,type_curve,nline` → `ntime,type_curve,nstoch_curve,nline`；`nplgroup` → `nplgroup,kpload` | `Load.f90:150` / `:229` |
| `.man` | 增量记录 7 → 9（`cwater,Qstatic`）；VIE 另缺 `nstepjq,nstepjp` 与 `hwdirec,hcoord` | `Fem.f90:3608` / `:8526` / `:8528` |

---

## 二、三处**不是**"补零"的取值，各自的源码依据

补零规则在三个地方会给出**必然崩溃或必然改变语义**的结果。这三处逐一给依据。

### 2.1 `ngapb` 必须归零（不是"保留 deck 原值"）

`train_slope_unknown` 原值 `ngapb=3`，`train_vie_boundary` `ngapb=2`，`train_temp_creep` `ngapb=2`，
三者 `ngaps` 全是 0。

```
Global.f90:3334   if (ngaps==0) return          ← 在 allocate(gaps(ngaps),gapb(ngapb)) 之前返回
Global.f90:4869   do igapb=1,ngapb
Global.f90:4871       jgroup=gapb(igapb)%listgroupb(igroup)   ← 解引用未分配的 gapb
```

`contact_pair_process` 在 `block_stab==0` 时无条件被调用（`Fem.f90:1886`）。
所以 **`ngaps==0` 且 `ngapb>0` 是当前求解器的必然 SIGSEGV**。实测确认：保留 `ngapb=3` 时
`train_slope_unknown` 在 `1.chk` 写完 `ikindks=` 之后立刻 severe(174)；改成 0 后越过该点。
其余 13 个字段（`contactpe`/`nonsbt`/`method_gapi`/`miter_state`/`damp_ctt`/`istatec`）
在 `ngaps==0` 下全部不可达，取 0；`type_solver_ctt` 是字符量没有"零"，取 `PROFILE`
（`train01` 的取值，且同样不可达）。**legacy 值写在同行 `!` 注释里保留。**

> 这同时是一条**求解器缺陷**：`contact_pair_process` 缺 `if(ngaps==0) return` 守卫。

### 2.2 `train_temp_creep` 的 `ECWPIPE = 2`（不是 0）

```
Temper.f90:75-79   if(ecwpipe>=1)then ; do igroup=1,ngroup
                      allocate(group(igroup)%water_pipe)
                      group(igroup)%water_pipe%pipecooling=0
                      if(ecwpipe/=1) cycle       ← 2/3 只分配，不多读任何记录
                      … 从 .tem 读每组通水记录 …
Fem.f90:15307      group(igroup)%water_pipe%tp=temperature   ← 无条件解引用
Temper.f90:1107    if(ecwpipe==2)then  ! 常规算法 → call dfact_internal_heat(source_curve,…)
```

- `ecwpipe=0` → `water_pipe` 未分配，`Fem.f90:15307` 必崩（实测：SIGSEGV，`1.chk` 停在
  `maxval(result_zero)=` 之后）。
- `ecwpipe=1` → 需要 `.tem` 里每组的 `ncool` 段，本 deck 没有。
- `ecwpipe=2` → 分配结构体、不读任何额外记录、内热源走 `dfact_internal_heat`，
  即"没有等效通水冷却算法"的行为——**正是本 deck 那个年代的语义**。

> 也是一条**求解器缺陷**：`placement_temperature` 对 `group%water_pipe` 无守卫。

### 2.3 `train_temp_creep` 的 `stab_matde = 99999`（不是 0）

```
Fem.f90:2430  if(iblks>=stab_matde)call stab_initialize
```

`stab_matde=0` 会让 `stab_initialize` **每一块都被调用**，即把一个旧 deck 根本无法表达的
特性打开。88 个方言 A 算例统一用 `9999`/`99999` 作为"关闭"哨兵。故取 `99999`。
同一条记录里 `level_set_problem=0`、`ljdp=0`（`Global.f90:766` 只在 `ljdp/=0` 时告警）。

### 2.4 `train_slope_unknown` 的 `SOLID` 记录尾部两个值必须丢弃

deck 原文：`'CLASSICALEP',2500,1.0,1.0,30e6,0.3,5e-6,0,30e6,0.3` —— 10 个值，
现行 `Material.f90:289` 也要 10 个，**arity 恰好相等**，看起来无需迁移。但：

```
Material.f90:214-215   integer(ink) iE,iNu,mmats,xlwmodel,kind_wt
                       integer(ink) jliqu,…
```

`kind_wt`/`jliqu` 是**整型**，把 `30e6` / `0.3` 按 list-directed 读进整型是非法的。
且这两个值与同记录第 5、6 位的 `e`、`nu` 逐字节相同，而同批的
`train_vie_boundary` 该记录只有 **8** 个值。故判定：旧格式该记录 8 项，
`,30e6,0.3` 是编写残留 → 改为 `,0,0`，被丢弃的值写进同行 `!` 注释。

---

## 三、`train_temp_creep`：方言 B + 空 `.ftr`，逐条

### 3.1 `.ftr` 到底需不需要？—— 需要，且守卫是"没有守卫"

```
Global.f90:651   open(ftfread, file=probn(1:len1)//'.ftr')     ← 无条件 open
Global.f90:834   read(ftfread,*)text                            ← 无条件
Global.f90:835   read(ftfread,*)nforce,ngaps,nforce_gaps,nsafety_gaps
```

这两条 READ 位于 `NTSMAT` 记录之后、group 段之前，**外层没有任何 if**
（其间只有 `if(submodel==1)` 与 `if(outind==-1)` 两个独立块）。
所以 0 字节 `.ftr` 必然 severe(24)。

`nforce=0` 不是编的：**旧 `.glb` 自己带着这个值**。方言 B 的 `TYPE_PROBLEM` 记录标签是
`… kglb nforce ngptrans ,dynaB`，对应值 `… 0, 0, 1, 0`，即 `nforce=0`。
所以写入的最小 `.ftr` 是：

```
nforce,ngaps,nforce_gaps,nsafety_gaps
0 0 0 0
```

同理 `1.ifs` 也是 0 字节而 `Stiff.f90:9580/10213/10315/10412` 无条件读，
补了 `nifsgroup/nabsfgroup/nabssgroup/ifsnedge` 全 0 的最小文件。
（`nabssgroup` 现行只读 1 项，`train01` 那行的 `exx,uxx,densxx` 是注释掉的历史字段。）

### 3.2 头部：方言 B → 方言 A

```
旧  'NPOIN NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh'   (11)
     5628  4720   3     1      1      0    GIDB     0      0        0     0
新  … + npoinb(第2位) + level_set_problem, ljdp, stab_matde(尾3位)                (15)
     5628 5628 4720 3 1 1 0 GIDR 0 0 0 0 0 0 99999
```

- **`npoinb = npoin = 5628` 的依据是统计，不是源码。**
  `20-facts-glb-dialects.md §6` 已经标注过这一点，这里如实重复：
  88/88 个方言 A 算例满足 `npoin == npoinb`；而 `grep -rn npoinb hstarYLOrig/HSTAR/`
  只有 3 行（声明 `Global.f90:151`、READ `:677`、PRINT `:678`），**读进来之后全仓从不使用**。
  所以这个取值在当前求解器下不可能产生任何后果，但它**没有源码依据**。
- `outplot` **`GIDB` → `GIDR`**：`Global.f90:698-706` 里 `outplot(1:3)=='GID'` 打开
  `.flavia.msh`，然后只对 `GIDR`/`GIDA`/`GIDL` 三个值打开结果单元。
  `GIDB` 落进 `GID` 前缀但没有任何分支接它 → **网格照写、结果单元从未 open**，
  后续 `write(out_gid_dis,…)` 会写进 `fort.40`。这是典型的"语法合法、求解器接受、输出去了别处"。
  归档的 `1.flavia.res` 是 GiD 二进制（旧求解器的 `GIDB` 语义），当前源码里对应的是 `GIDL`+`.post.bin`。
  **选 `GIDR`（文本 res）是为了让结果可比对；这是一处有意的语义变更，不是补零。**
- `NINIT` 记录：旧方言只有一个 `outint`（值 `-1`），现行分裂成 `outintr`/`outintw`。
  取 `outintr=0, outintw=-1`，依据：`Temper.f90:99` 的 `outintr<0` 分支要求 `.tem`
  末尾每组一条 `temp_pre` 记录，本 deck 没有；`Fem.f90:157` 的 `outintr>0` 只对
  `type_problem=='Q'` 生效，本例是 `'S'`。**这一条是推断，不是硬依据，如实标注。**
- `TYPE_PROBLEM` 记录：`nforce ngptrans dynaB` 三个尾字段**在现行全仓不存在**
  （`grep -an "ngptrans\|dynaB" hstarYLOrig/HSTAR/*.f90` 零命中）→ 丢弃，值写进注释；
  再补 `state_change Bparameter balgor upliftin` = 0。

### 3.3 其余记录（全部按"标签对齐 + 缺记录整条插入"）

`.glb`：`NMASS` 记录在 deck 里**被错误地标成了 `NTSMAT`**（标签行是复制粘贴错的，
值 10 项对得上 NMASS）；补 `nfreeflownode` text 记录（`Global.f90:768`）；
整条插入 `equvs_process` / `appear_level` / `average_appear` / `gid_*` / `res_*` /
`ftcrack` / `modf_dis_blocks` / `order_time`；`Icaddmass` 记录 6→8（`alfa_p4,stiff_p4`=0，
`Global.f90:1350` 只在 `alfa_p4>0` 时调 `form_ipp4`）；group 记录 20 项截成 16 项再补
`uplift_ic,liquj`（第 17-20 项全是 0，数值上无损）。

`average_appear` 取 **0**（`Global.f90:955` 源码自己就是 `average_appear=0`），
而不是其它 deck 常见的 `-2`。**这会改变应力平均方式**（deck 注释：0=不参与应力平均，
-2=按原来方式直接平均）。取源码默认值，如实标注。

`gid_T=1` / `res_T=1`，其余 0：本例 `mdofn=10` 且只有第 10 个自由度（T）激活。

`.nrt`（132 行变动）：旧格式是 `1 行表头 + "63 0"`，其中 63 是 **ntransnode**
（后面正好 63 组三行），deck 把它标成了 `transgroup`。迁成
`2 行表头 / transgroup=1 / "63 0" / 63 × (TRAL ipoin nintf / listf / rintf)`。
`TRAL` 前缀是 `Global.f90:1369-1371` 要求的：`read title_intp,ipoin,nintf` 后
`if(title_intp(1:4)=='TRAL')` 才读插值系数。
> 另一条同样合法的迁法是把 `translg` 改成 **99**（`Global.f90:1389` 那个分支**逐字**读旧格式
> `ipoin,nintf`，不要 title）。没选它，因为 `translg==0` 分支多一个 `IF(itotv>0)` 守卫。

`.tem`：补 `ntemp_surface` 记录（`Temper.f90:122-123`）；6 条
`sedge,nnode,index,beta_bar` 各补 `ibeta_bar=0`（`Temper.f90:161`，只在 `Bparameter/=0`
时使用，惰性）；补 `begin_edge,end_edge = 1 1672`（`Temper.f90:248`，由
`end-begin+1 == sedge == ntelgroup == ntedge == 1672` 唯一确定）。

`.mat`：补 `nmats` 记录；补 `ialfa=0`（`Material.f90:976`，只在 `Bparameter/=0` 时用）。

`.man`：补 `nstepjq,nstepjp = 0 0`（`Fem.f90:8526`）；增量记录 8→9，
在 `nresta` 与 `nbasef` 之间插 `nmcon=0`（deck 自己的注释列的是
`…,nresta,nbasef`，现行是 `…,nresta,nmcon,nbasef`）；
**删掉每个增量后面那行 `0 0 864000.0 1e-3`** —— 现行源码里这条记录没有任何读者
（该子程序内对 `mainunit` 只有 §1.2 列的那几条 READ），保留它会让下一个增量记录读错。
被删的三行原文写在文件末尾的 `!` 注释里。

---

## 四、求解结果，以及与归档结果的差异

### 4.1 `train_slope_unknown`（`type_problem='Q'`, `type_load='MAT_DE'`, 2D, 451 节点）

`exit 0`，100 个增量步全部跑完。最后一步 `iiter=10=miter`、`ratio1=0.63`，**未收敛**——
这正是 MAT_DE 渐进破坏/强度折减算例在破坏点的表现，不是迁移失败。

| | 步数 | 第 1 步 max\|u\| | 末步标签 | 末步 max\|u\| |
|---|---|---|---|---|
| 迁移后 | 100 | **41.815** | t=1.00 | 2.22e5 |
| 归档 | 100 | **41.81** | t=0.50 | 2.34e5 |

**第 1 步逐节点四位有效数字完全一致**（前 19 个节点逐个核对：`-0.43931650E+00` vs `-0.4393E+00` …）。
两处差异如实记录：

1. **时间标签不同**（末步 1.00 vs 0.50）：deck 的 `1.man` 写 `ditime=0.01`，归档那次用的是 `0.005`。**归档结果不是用仓库里这份 `.man` 跑出来的**，
   两者的时间轴差 2 倍。步数和第一步结果相同说明加载路径一致。
2. **末步差 5%**：末步是发散/破坏态（位移量级 1e5，物理上无意义），
   在这种状态下 5% 差异不构成信息。

> 位移量级本身（第一步就 41.8）在物理上不合理，但**它与归档逐位相同**，
> 所以是这个算例自身的属性，与迁移无关。

### 4.2 `train_vie_boundary`（`type_problem='F'`, `type_ABC='VIE'`, 2D, 2543 节点, 5 组）

`exit 0`，250 步跑完，末步收敛（`ratio1=4.0e-11`、位移检查 `6.9e-8`/`1.4e-7`，`nchek=0`）。

| | 步数 | 时间轴 | 第 1 步 max\|u\| | 末步 max\|u\| |
|---|---|---|---|---|
| 迁移后 | 250 | 0.04 … 10.00 | 1.31e-5 | 4.11e-3 |
| 归档 | 250 | 0.04 … 10.00 | 9.29e-6 | 5.31e-3 |

时间轴与步数完全一致；量级一致；逐点差 0.7~1.4 倍。
这与 `project_train10_vie_parked` 里记的"包络对、逐点 0.7~7×"是同一现象。
**不试图让它们一致**：归档来自更旧的求解器基线，而 VIE/透射边界通路
（`Solver.f90` 的 `nabssgroup` 组装、`earthquake_curve_d/_v` 的双重激励）
在两版之间有已知改动（见 `19-probe-report-vie-ablation.md`）。

**`force_process` = `222*1` → ngroup=5 全部为 1。**
`.glb` 里 `APPEAR_PROCESS = 0 1 1 1 1`、`MATNO_PROCESS = 1 2 3 4 5`，
即第 1 组（地基）不参与出现过程，2-5 组参与；惯性力对全部 5 组打开。

### 4.3 `train_temp_creep`（`type_problem='S'`, 3D, 5628 节点, B8 温度场 + 通水冷却）

求解器**读完了全部输入**：`.glb`（含 group/单元/ngaps/nrcsteel/nwcpipe）、`.cor`、`.ele`、
`.mat`、`.nrt`、`.ftr`、`.ifs`、`.pre`、`.loa`（7 条时间曲线）、`.tem`（1672 条对流边、
`ntelgroup`、`npipe/algo_pipe=3` 的 20 段水管）、`.man`（3 个增量）、`.opr`、`.sol`。
`1.chk` 显示：PARDISO 符号分解完成（`Neq=5564`、`sstore=133754`）、
`prescrib_set` 完成、`placement_temperature` 完成、`STMATRX`（热容矩阵）逐单元写出，
随后 `Begin assemble golbal matrix` —— 然后 SIGSEGV。

崩溃点在 `Stiff.f90:3367` 调用的 `assemble_pardiso_mesh`（`Stiff.f90:3522-3651`）内部，
在它写出第一条 `igroup=… ielem=… order_time=…` 之前。已排除的原因（各做了一次消融）：

| 消融 | 结果 |
|---|---|
| `nonsym` 1 → 0 | 同一 PC 崩溃 |
| `OMP_NUM_THREADS=1` | 同一 PC 崩溃 |
| `type_solver` PARDISO → PROFILE | 越过组装，改为在 `1.sol` 报错（该 deck 的 `.sol` 只有 PARDISO 段，没有 PROFILE 要的 `Iafile icond ipdchk ising`）——**说明故障在 PARDISO 组装路径，不在单元矩阵本身** |

套件里另有 20+ 个 PARDISO 算例跑得通，所以不是"PARDISO 路径整体坏了"。
本例的特异点是 `mdofn=10 / cdofn=1 / 唯一自由度是第 10 个（T）/ index=9(B8) / nrfields=1 / nfdof=1`。
**没有把它归因到任何 deck 字段，也没有为了让它跑起来去改字段值。**
这是 `10-roadmap.md` 意义上的下一个探针题目，不是本次迁移的产物。

归档的 `1.flavia.res` 是 GiD **二进制**（旧 `GIDB` 语义），当前求解器没有对应分支，
所以**即使跑通也无法与归档逐值比对**——这一点在 §3.2 已说明。

---

## 五、踩到的仪器 bug（如实列）

1. **`tools/decoder.py`：派生类型分量的数组形状不解析。**
   `Material.f90:971` `allocate(props(imat)%heat%alfa(ndimn))`，`:972` 的 READ 是
   `alfa, source_curve, place_curve, pipe_cooling` 共 6 项（ndimn=3）。
   decoder 把 `%heat%alfa` 当成 **1 项**，于是把
   `3*.0708, 3, 4, 0` 绑成 `alfa=.0708, source_curve=.0708, place_curve=.0708, pipe_cooling=3`，
   `pipe_cooling≠0` → 走进通水冷却分支 → 报"文件耗尽"。
   **这是 `train_temp_creep` 当前停点的全部原因**；求解器本身读这条记录没有问题（实测已越过）。
   同类：`(group(igroup)%order_time(:,ifield),ifield=1,nrfields)` 这个 implied-DO 也被当成 1 项
   （迁移中途一度让 `train_vie_boundary` 的 group 段整体错位，`游标行 87/86` 溢出 EOF）。

2. **`.glb` 记录版本不匹配时，decoder 的检查是不完整的。**
   迁移前 `train_slope_unknown` 在 `NINIT`（11→19）和 `TYPE_PROBLEM`（7→11）两处
   **没有**触发 "deck record version mismatch"，而是照读，绑出
   `type_problem = "NMASS NSMAT NHMAT …"`、`type_abc = "TYPE_PROBLEM TYPE_SOLVER …"`
   这种把标签行当值的结果，一路滑到 `.ftr` 才停。也就是说**停点报告的位置不是故障位置**
   （与 `20-facts-glb-dialects.md §4` 记的是同一种病）。
   `gid_*`（15→20）那处倒是正确触发了 mismatch —— 两条路径不一致。

3. **我自己写坏一次算例文件。**
   `open(p,'wb').write('\n'.join(L).encode('latin-1'))`：`encode` 抛异常时
   `open(...,'wb')` **已经把文件截成 0 字节**。含中文注释的一次改写把
   `cases/cases/train_temp_creep/1.glb` 清空了。已从 `/tmp` 备份恢复并重跑迁移脚本。
   教训与项目主症状同源：**先截断后校验**。任何"原地改 deck"的工具都应该写临时文件再 rename。

4. **`grep` 陷阱两条都撞到了**，确认 README 的描述属实：
   三个算例的 `1.glb` 对普通 `grep` 全部零输出 rc=1（必须 `grep -a` 或 `iconv`）；
   `Material.f90` / `Temper.f90` / `Prescrib.f90` / `Solver.f90` / `Output.f90` 是 GBK，
   `sed | iconv -f GBK` 才能读注释。本报告里所有源码引用都是这么取的。

---

## 六、顺带查实的两条求解器缺陷（不是 deck 问题）

| # | 位置 | 形态 |
|---|---|---|
| 1 | `Global.f90:4869` `contact_pair_process` | 缺 `if(ngaps==0) return`；`ngaps==0 && ngapb>0` 必 SIGSEGV（`Global.f90:3334` 提前返回，`gapb` 未分配） |
| 2 | `Fem.f90:15307` `placement_temperature` | 无条件解引用 `group(igroup)%water_pipe`，而它只在 `ecwpipe>=1` 时分配（`Temper.f90:75-77`） |

两条都是"**deck 里一个看似无关的开关取 0，求解器就崩**"，
和 `10-roadmap.md §0` 那七个缺口是同一族：**守卫写在读的地方，用的地方没有守卫。**

---

## 七、力学判据验收（2026-08-29 追加，取代原来的"看着合理"）

判据全部**不依赖任何参照算例**。现成实现：`harness/gate.py` 的
`equilibrium_residuals` / `declared_force_tolerance` / `solver_residuals`，
`harness/mechanics.py` 的 `self_weight_resultant` / `extremum_principle` /
`amplification_factor`。手工补算的部分见 §7.5。

### 7.0 结论先行：**三个算例都不放行**

| 算例 | 判据 | 结论 |
|---|---|---|
| `train_slope_unknown` | 整体力平衡 **fail**、收敛 **fail（100/100 步全部未收敛）** | **不放行** |
| `train_vie_boundary` | 收敛 ✓、辐射衰减 ✓、**坝体放大系数 1.10 触警** | **不放行**（一条触警） |
| `train_temp_creep` | 跑不完，无结果可判 | **不放行** |

### 7.1 `train_slope_unknown`：交付的 deck 不满足力平衡，但**迁移是对的**

**交付的 deck（`CLASSICALEP` + `MC`, c=4.2e4 Pa, φ=17°）**

```
整体力平衡   |ΣF|/Σ|F|   末步 0.598   容差 0.010                    ✗ fail
             逐步：step1 0.119  step10 0.0199(最好)  step50 0.303  step100 0.598
求解收敛     deck 自报 toler_force = 1e-5
             100 步**全部**打满 miter=10 未收敛，ratio 0.44 ~ 1.31   ✗ fail
```

**弹性消融**（仅把 `'MC'` 的 `sigma0` 4.2e4 → 4.2e12，即抑制屈服；`/tmp` 副本，仓库未改）

```
整体力平衡   |ΣF|/Σ|F| = 1.55e-9    容差 0.010                       ✓
求解收敛     step1 2 次迭代 residu 2.4e-15；step2-100 各 1 次 2e-16  ✓
自重合力对账 理论 ΣρVg              = 1.14777e9 N
             其中约束节点自身分担    = 5.73885e7 N (5.000%)
             理论应出现的支反力      = 1.09038e9 N
             实测 ΣFy(41 个 y=0 约束节点) = 1.09038e9 N
             相对差 2.8e-9                                            ✓
符号         max Uy = 0，min Uy = -10.09 m，451 个节点**无一上抬**    ✓
量级         δ ~ ρgh²/E = 2500·9.81·180²/30e6 = 26.5 m，实测 10.09 m
             同一数量级                                               ✓
```

网格体积 46800.0 m²（单位厚度）与求解器自己打印的 `tvol=46800.0000000000` 逐位相同，
所以对账式右边完全独立于求解器。

**判读**：荷载通路、约束、单元体积、材料密度全部正确进入方程——
**这一条正是 `order_time` / `force_process` 两次事故的判据，本次通过。**
交付 deck 之所以失败，是本构层面的：c=42 kPa、φ=17° 的材料在
360×180 m、ρ=2500 的自重下（180 m 深处自重应力约 4.4 MPa）**从第一步起就整体屈服**。
`type_load='MAT_DE'`（材料渐进劣化）+ 算例名 `slope_unknown` 与此一致：
**这个 deck 描述的是一个在自重下垮掉的边坡**。

且归档结果的第 1 步位移场与迁移后**逐节点四位有效数字相同**，
说明旧求解器给出的是同一个未收敛状态——**不收敛是算例自带的，不是迁移引入的**。

> 因此：迁移可以判"完成"，**算例不可以判"通过"**。
> 要让它成为可验收算例，需要的是本构/加载参数的重新标定（`miter=10` 也明显不够），
> 那超出"格式迁移"的范围，我没有动。

### 7.2 `train_vie_boundary`

```
求解收敛     worst step 107，2 次迭代，ratio 5.56e-8 ≤ 1e-5           ✓
整体力平衡   unverified —— 动力算例 tofor 不含惯性力（gate.py 已如此处理）
自重         **本算例根本不加自重**：tcurvegravity = 5*0，
             Load.f90:1170 `if (tcurvegravity(igroup)/=0)` 逐组跳过 → 判据不适用
材料阻尼     5 组 alfa=beta=0（type_mass 记录 `0 0 0.0 0.0`）→ 辐射阻尼是唯一耗能机制
```

**输入是否真的进去了（自重对账的动力对应物）**

VIE 激励记录 `inpcord=-250, earthquake_curve_d=(4,0), earthquake_curve_v=(3,0)`，
即曲线 4 = 位移、曲线 3 = 速度。RMS 衰减比（后 1/4 / 前 1/2）：

```
输入曲线 4（位移，实际驱动量）   1.208
模型底边界节点 Ux               1.210     ← 与输入逐位吻合  ✓ 激励确实进入了
```

**辐射衰减判据**（`vie-evaluation.md` P1）

```
结构变形（顶-底相对 Ux）衰减比   1.017
输入位移衰减比                   1.208
相对                             0.842      ✓ （< 1：变形衰减快于输入，辐射阻尼在耗能）
对照 train10_dynamic_vie                    1.638（异常）
```

> 量纲说明：`vie-evaluation.md` 原文拿"输入波 a"（加速度）作分母。本 deck 的 VIE 记录
> **只引用曲线 3/4（v 与 d），不引用加速度曲线 2**（`earthquake_curve=(0,0)`）。
> 拿位移响应比加速度输入的包络是量纲不一致的比较（积分改变频率成分进而改变包络），
> 所以这里用位移比位移。若硬按曲线 2（衰减 0.2138）比，相对值是 4.76 ——
> **这条判据的分母必须写清楚是哪一条曲线，否则同一个算例能得出相反结论。**

**放大系数（触警）**

```
坝体 = group2（混凝土 ρ=2500 E=25e9，x∈[150,236] y∈[0.02,110]）
坝顶 2048 peak|Ux| = 0.1256 m
坝踵 2533 peak|Ux| = 0.1146 m
放大系数 = 1.10      峰值相对变形 = 1.3 cm / 12.6 cm 总位移
```

`mechanics.amplification_factor` 自带的判据是"重力坝在 0.2g 下放大 2~8；接近 1 即
**在平动而不是在变形**"。**1.10 落在它标注的病态区**，与 `train02c` 的 1.114 同签名。

但两点保留，我不下结论：
1. 该 2~8 区间是按"加速度输入的重力坝模型"标定的；本例是在 y=-250 处施加
   **位移/速度**的 VIE 边界，波要穿过 250 m 地基上来；
2. 本 deck **不加自重**（已核实），所以它更像一个波传播算例而不是坝体响应算例。

**处置：按你的规则，触警即不放行，交给你判。**

### 7.3 `train_temp_creep`：判据备好了，但没有结果可判

极值原理是这三条里最强的一条，可惜求解器崩在组装阶段（§4.3），没有温度场可查。
把边界数据先记下来，等它跑通可以直接判：

```
1.pre  自由度 10（T）规定值：4 个水管管口节点 = 1.0
1.loa  曲线 2 气温 20.0 / 曲线 4 浇筑温度 20.0 / 曲线 5 冷却水温 15.0 /
       曲线 6-7 通水温度 16.08 / 曲线 3 'DABT' 绝热温升 25
1.tem  1672 条对流边，beta_bar = 0.4242
```

瞬态判据：任一内部节点温度不得越出
**[初始场 ∪ 全部边界规定值 ∪ 对流参考温度]** 的包络，绝热温升作为源项另计上界。
稳态判据更强：直接不得越出 [min,max] 边界值。

### 7.4 `harness` 现成检查在 B 组上的实际表现

```
train_slope_unknown   run_validity = incomplete
                      global_equilibrium fail 0.598 > 0.01
                      solver_convergence degraded 1.31 > 1e-5
train_vie_boundary    run_validity = valid
                      solver_convergence pass 5.56e-8
                      global_equilibrium unverified（动力，正确处理）
```

`run_validity` 对 `train_vie_boundary` 判 `valid`，而放大系数 1.10 触警——
**说明"整体力平衡 + 收敛"这两条对动力算例的覆盖是空的**（一条 unverified、一条只看残差），
放大系数与衰减比不在 `run_validity` 里，得单独调。这是下一步该补的洞。

### 7.5 哪几条能直接自动化、哪几条卡住（落成代码的输入）

| 判据 | 现状 | 卡在哪 |
|---|---|---|
| 整体力平衡 | **已可用**，`gate.equilibrium_residuals`，动力三值处理正确 | — |
| 收敛残差 | **已可用**，容差从 deck 自报的 `toler_force` 取 | — |
| **自重合力对账** | `mechanics.self_weight_resultant` 在 B 组**三个算例全部 skip** | 见下面 3 个 bug |
| 极值原理 | `mechanics.extremum_principle` 只认 `1.pre` 里 **dof==8**（渗流/孔压） | **温度是 dof 10**，`train_temp_creep` 直接 skip。需要把 dof 8/10 都收进来，并把 `.tem` 的对流参考温度并入边界集合 |
| VIE 衰减比 | **无实现**，本次手算 | 需要固化"分母是哪条曲线"（见 §7.2 的量纲坑），以及从 `.man` 的 `earthquake_curve_d/_v` 解出实际驱动曲线号 |
| 放大系数 | `mechanics.amplification_factor` 能跑，但默认按 y_min 取基准点，**取到了模型底边界**（y=-250） | 需要 `probe_nodes.json`（该函数注释里已提出）；本次是手工按 group2 的节点集重新定位坝顶/坝踵 |
| 符号 / 量级 | **无实现**，本次手算（无上抬、δ~ρgh²/E 同量级） | 容易固化 |

`self_weight_resultant` 的三个具体缺陷（都在 B 组上实测到）：

1. **重力值解析不过逗号。** B 组这一批 deck 写的是 `9.81, 0 -1. , 0 -1.`，
   代码 `float(nxt[0])` 拿到 `'9.81,'` 抛 `ValueError` → 报 "gravity magnitude not found"，
   **三个算例全部 skip**。修法：这一行走 `deck_text.expand`，别用裸 `split()`。
   （这与 `20-facts-glb-dialects.md §3` 那次"引号是分隔符不是定界符"是同一族。）
2. **没有读 `tcurvegravity`。** 函数的 `assumptions` 里写着"all groups assumed to carry
   gravity; a deck with tcurvegravity=0 on some group will read high"——
   `train_vie_boundary` 就是 `5*0`（全组无自重），此时该判 **N/A 而不是 fail**。
   `Load.f90:1170` 是现成的守卫，照抄即可。
3. **对账式少了一项，系统性偏低。** 判据现在是 `ΣFy(约束节点) ≈ ρVg`，
   但 `tofor` 在约束节点上给出的是**支反力减去该节点自身分担的重力一致节点力**。
   正确的等式是

   ```
   ΣFy(约束节点) = ρVg − Σ_e ρ g V_e · (该单元落在约束节点上的节点数 / 单元节点数)
   ```

   本例这一项正好是 5.000%：按现行式子算相对差 0.05（"看着还行"），
   按正确式子算相对差 **2.8e-9**（精确闭合）。
   **现在 10% 的宽容差正是在容纳这个本可以精确扣掉的项**，
   补上之后阈值可以收到 1e-6 量级，判据强度完全不同。

---

## 八、复算

```bash
cd /home/huijun/HSTAR_Next
T=fem-chat/docs/research/hstar-input-redesign/tools
for c in train_slope_unknown train_vie_boundary train_temp_creep; do python3 $T/decoder.py --case $c; done

# 求解（务必用 harness，不要直接 ./hstar）
mkdir -p /tmp/mB && cp -rL cases/cases/train_slope_unknown /tmp/mB/ && \
  python3 fem-chat/harness/_solve_deck.py /tmp/mB/train_slope_unknown

# 迁移前后 diff
diff <(iconv -f ISO-8859-1 -t UTF-8 /tmp/claude-1000/migrate-B/train_slope_unknown.orig/1.glb) \
     <(iconv -f ISO-8859-1 -t UTF-8 cases/cases/train_slope_unknown/1.glb)
```

改动行数（`diff` 计 `<`/`>` 行）：

```
train_slope_unknown   1.glb 42  1.ftr 4  1.mat 5  1.nrt 1  1.man 2  1.LOA 6
train_vie_boundary    1.glb 54  1.ftr 4  1.mat 17 1.nrt 1  1.man 6  1.LOA 10
train_temp_creep      1.glb 53  1.ftr NEW(2) 1.ifs NEW(8) 1.mat 3  1.nrt 132  1.man 11  1.loa 14  1.tem 15
```
