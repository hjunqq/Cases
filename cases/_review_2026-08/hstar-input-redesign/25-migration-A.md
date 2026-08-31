# 25 — A 组三个旧格式算例的机械迁移（train_contact_nonlinear / train_seepage / train_seepage_stress）

> 2026-08-29。备份：`/tmp/claude-1000/migrate-A/<case>.orig`（迁移前完整拷贝）。
> 运行工作区：`/tmp/claude-1000/migrate-A/runs/{before,after,final,abl*}-<case>`。
> **所有求解一律经 `fem-chat/harness/_solve_deck.py`，未直接调用 `./hstar`。**

## 0. 结论摘要

| | 迁移前 | 迁移后 |
|---|---|---|
| decoder 走到 | `Global.f90:835`（`.ftr`），`.glb` 游标 22/100 行（22%） | **整棵 ABI 树走完，无停止点** |
| 求解器 | `forrtl severe(64)` 停在 `.glb` 第 1 条记录（`NINIT`） | **三个算例全部 completed，`1.flavia.res` 正常产出，exit 0** |
| 收敛 | — | 三个算例末步 `nchek=0`（收敛） |

| 算例 | decoder 记录数 前→后 | 绑定变量 前→后 |
|---|---|---|
| train_contact_nonlinear | 21 → **307** | 137 → **522** |
| train_seepage | 19 → **193** | 135 → **398** |
| train_seepage_stress | 21 → **310** | 137 → **459** |

**`13-probe` 的"差 4 条记录 14 个字段"是不完整的**——那个探针在补完 4 条后就被 `.ftr`
拦住了（它的 `UNIT_OF` 只覆盖 6 个文件，`verdict.json` 第 4 轮的 locator 还抓到了
harness 的输出文本当标签）。把 `.ftr` 也补上以后，后面**还有 12 类缺陷**，跨 6 个文件。
完整清单见 §2。

**"标签对齐补零"这条规则只覆盖了 12/17 类缺陷。** 另外 5 类不是补零能解决的：
一条是**字段被重排**（`ngaps` 记录），一条是**整条记录缺失**（`water_level`/`modf_dis_blocks`/
`backf()%`/`order_time`/`block_appear_process`/`nrcsteel`），一条是**文件级结构变了**
（`.loa` 从"每块一份完整段"变成"一份 part-A + 每块一份 part-B"），一条是**残留死记录要删**
（`ne_space`），一条是**字符型字段不能填 0**（`type_solver_ctt`）。

---

## 1. 逐算例改动清单（每处带源码行号依据）

三个算例的 `.glb/.ftr/.mat/.nrt/.man` 缺陷**完全相同**（同一批 deck，`13-probe` 的 P6 在这里
再次成立）；`.loa` 因块数不同而不同。下表按记录列出，`+` 表示补的字段。

### 1.1 `1.glb`（三个算例共有）

| deck 行 | 记录 | deck→源码 | 补的字段 | 源码依据 |
|---|---|---|---|---|
| L5/6 | `NINIT …` | 11→**19** | `winit` `block_stab` `nbackf` `nbspring` `ebody` `outind` `nbackdT` `ninistn` | `Global.f90:728` |
| L7/8 | `TYPE_PROBLEM …` | 7→**11** | `state_change` `Bparameter` `balgor` `upliftin` | `Global.f90:753` |
| L10/11 | `NMASS …` | 10→**11** | `ECWPIPE` | `Global.f90:775` |
| L13/14 | `NTSMAT …` | 6→**7** | `submodel` | `Global.f90:790` |
| L33/34* | `gid_u …` | 15→**20** | `gid_Mxy` `gid_bem` `gid_wh` `gid_wv` `gid_bcs` | `Global.f90:959-960` |
| L35/36* | `res_u …` | 15→**17** | `res_Tv` `res_Pa` | `Global.f90:962-963` |
| hdam 之后 | **整条记录缺失** ×2 | — | 新增 `water_level`(nblks) 与 `modf_dis_blocks`(nblks) 两条记录 | `Global.f90:1005` / `1008` |
| uinitial 之后 | **整条记录缺失** | — | 新增标题行 `backf()%` | `Global.f90:1015` |
| 组记录头 | `NAME…group_inf` | 16→**18** | `uplift_ic` `liquj` | `Global.f90:1119-1124` |
| 每组 | **整条记录缺失** | — | 每组补一行 `order_time(2,nrfields)`（全 0） | `Global.f90:1131` |
| ngaps 记录 | `ngaps,ngapb,xlwm,restart_ctt,miter_bt,tor_bt,iblks_bt` | 7→**14**，**且顺序不同** | 见 §1.2 | `Global.f90:3330` |
| 文件尾 | 残留 `ne_space,e_space,nu_space,ngaus_p` | — | **删除**（该记录只被 `Global.f90:2125/2442` 读，那是另一个子程序，当前游标下是死记录） | — |
| 文件尾 | 缺 `nrcsteel` / `nwcpipe` 两条记录 | — | 各补一条（照抄 `train01_gravdam_static/1.glb` 尾部） | — |

\* 行号为 train_seepage；另两个算例 +2。

**contact 独有**（该 deck 真的带 gaps/gapb 数据，另两个 `ngaps=0`）：

| deck 行 | 记录 | 改动 | 源码依据 |
|---|---|---|---|
| ngaps 之后 | 新增 `block_appear_process(1:ngapb,1:nblks)` = 4 个 0 | 整条记录缺失 | `Global.f90:3336-3337` |
| gaps 头 | `2` → `2 0 0 0 0 0`（`ngroupt`+`xlwmd(1:2)`+`frict_less`+`goodman`+`thin_layer`） | 1→6 | `Global.f90:3346` |
| cohes0 之后 | 新增 `i0,kgroup0(1:ndimn),kgroup1(1:ndimn)` = 5 个 0 | 整条记录缺失 | `Global.f90:3385` else 分支 |
| gapb ×2 | `2 1` → `2 1 0 0`（+`nrdof`,`eblock`） | 2→4 | `Global.f90:3457` |

> `kgroup0/kgroup1` 补 0 **不是随便填的**：`Global.f90:3362-3363` 在这条 READ 之前把两个
> 数组显式置 0，所以补 0 等于"保持源码自己的初值"，不引入新语义。

### 1.2 `ngaps` 记录：唯一一处"补零规则失效"的地方

旧标签 7 项、新 READ 14 项，**而且顺序不是前缀关系**：

```
旧: ngaps ngapb xlwm    restart_ctt miter_bt tor_bt iblks_bt
新: ngaps ngapb contactpe miter_bt tor_bt iblks_bt nonsbt xlwsol
    method_gapi miter_state type_solver_ctt restart_ctt damp_ctt istatec
```

按**名字**（不是位置）映射：`xlwm→xlwsol`、`restart_ctt→restart_ctt`（从第 4 位挪到第 12 位），
其余 6 个新字段填 0。**`type_solver_ctt` 是 `character(50)`（`Global.f90` 声明行），不能填 0**，
填了 deck 里已有的 `'PROFILE'`（与同 deck 的 `type_solver` 一致，也与
`train01_gravdam_static` 的现代写法一致）。

> 如果按位置对齐（探针 3 的 `alike()` 会做的事），`miter_bt` 会拿到 0、`tor_bt` 拿到 500，
> **语法合法、求解器接受、迭代参数全错**——本项目的主症状。这条记录是"标签是记录的版本戳"
> 这个论断的一个**反例**：标签记录了当年的 arity，但**没有**记录当年的顺序。

### 1.3 `1.ftr`（三个算例共有）

`nforce` 1 项 → `nforce,ngaps,nforce_gaps,nsafety_gaps` 4 项（补 3 个 0），依据 `Global.f90:835`。
标签行同步改成 4 个名字。

### 1.4 `1.mat`

| 改动 | deck→源码 | 源码依据 |
|---|---|---|
| 缺整条 `nmats` 记录（标题 + 计数） | — | `Material.f90:263-264` |
| 每个 `SOLID`：`ELASTIC_ISOTROPIC/GOODMAN,…` | 8→**10**（+`kind_wt`,`jliqu`） | `Material.f90:289` |
| 每个 `SOLID`：缺整条 `iE,iNu,density_w` | — | `Material.f90:291`（填 `0 0 1000.`，与 `train01` 现代写法一致） |
| `GOODMAN` 子记录 `XX 1 1` | 3→**5**（+`uniax_cohes`,`frict_angle`） | `Material.f90:524-527` |
| `FLUID` 渗透率行 `3*1.e-5` | 3→**1+ndimn**：`iperm` 前置 + 只保留 ndimn 个 | `Material.f90:931` |

> `FLUID` 那行是**旧 deck 写了 3 个渗透率但网格是 2D**。旧格式没有 `iperm` 前缀字段，
> 直接读会把 `1.e-5` 转成整数 `iperm` 而报 severe(64)。迁移取前 ndimn 个分量。

### 1.5 `1.nrt`

`Global.f90:1361-1363` 要 `text, text, transgroup` 三条；旧 deck 只有 1 个标题行 + 数据行。
补一行标题 `ntransnode and translg for each transgroup`。（`transgroup=0`，后续循环不执行。）

### 1.6 `1.man`

增量记录 `5 1 1 1 1 1 1` 7 项 → 9 项（+`cwater`,`Qstatic`），
依据 `Fem.f90:3611`（`static_U*` 路径）/ `Fem.f90:7609`（`static_U_Pw` 路径）。
与 `train01_gravdam_static/1.man` 的 `5 1.0 1 1 1 1 1 0 0` 一致。

### 1.7 `1.loa` — 这里是文件级结构变更，不是补字段

字段级：

| 改动 | deck→源码 | 源码依据 |
|---|---|---|
| 时间曲线头 `2,'LINEAR',2` | 3→**4**（+`nstoch_curve`，插在第 3 位） | `Load.f90:150` |
| 点荷载 `0` | 1→**2**（+`kpload`） | `Load.f90:229` |
| `sedge,nnode,index` | 3→**4**（+`vdimn`） | `Load.f90:359` |
| 边荷载组 `1 31 2 2` | 4→**5**（+`code_load`） | `Load.f90:739` |

结构级（**只影响 nblks≥2 的 contact / seepage_stress**）：

`Fem.f90:1672` 的 `call external_load_1` 在 `do iblks=…` 循环**外面**，只调用一次；
`Fem.f90:1886` 的 `call external_load_2` 在循环**里面**，每块一次。
`external_load_1`（`Load.f90:107-458`）读时间曲线 / 点荷载 / edges，
`external_load_2`（`Load.f90:710-`）读边荷载 / 体力 / 分组时间曲线 / nbeamload / nplateload。

所以现代 `.loa` 的布局是（`train11_staged_foundation/1.loa` 实证）：

```
part-A   一次      时间曲线、点荷载、全部 edges（所有块合并，nedge 是总数）
part-B   每块一次   edge_load_group/delgroup、体力、分组时间曲线、nbeamload、nplateload
```

旧 deck 的布局是**每块一份完整的 part-A+part-B**。迁移做法：

- part-A 取 **ntcurve 最大的那一段**的曲线集（contact 的块 2 有 2 条曲线，块 1 的那条与其
  第 1 条逐字相同，是真子集）；
- edges **跨块拼接**，`nedge` = 各块 sedge 之和（contact 0+31=31，seepage_stress 0+31+20=51）。
  边荷载记录里的 `begin_edge,end_edge` 是全局边号，**因为块 1 的 nedge=0，编号无需重排**；
- part-B 按原块顺序保留。

`train_seepage` 只有 1 块，结构本来就吻合，只做了字段级改动。

---

## 2. 缺陷类型统计

```
补零可解（标签对齐）      12 类   .glb 6 + .ftr 1 + .mat 3 + .man 1 + .loa 4  → 实为 15 处记录
整条/多条记录缺失          6 类   water_level, modf_dis_blocks, backf()%, order_time,
                                 block_appear_process, nrcsteel/nwcpipe, nmats, iE/iNu/density_w,
                                 .nrt 标题, gaps 的 kgroup0/1
字段重排                   1 类   ngaps（且含 character 字段，不能填 0）
残留死记录要删             1 类   ne_space
文件级结构重排             1 类   .loa part-A/part-B
```

---

## 3. 与归档 `1.flavia.res` 的差异

**归档结果不是验收基准**（当前求解器读不了原 deck，归档不可能是当前基线产出）。
下面如实记录差异，不试图消除。

对比脚本 `/tmp/claude-1000/migrate-A/cmp2.py`（按结果块出现顺序逐块、逐列比，
`rel = max|a−b| / max|a|`）。

### train_seepage_stress（信息量最大）

| 结果块 | 相对差 |
|---|---|
| [0] DISPLACEMENT 块1 Uy | **0.014 %** |
| [2] tofor 块1 | 0.013 % / 2.56 % |
| [3] SIGZZ 块1 | 0.013 % ~ 0.040 % |
| [4] SIGMA-2 块1 | 0.013 % / 0.040 % |
| [5] DISPLACEMENT 块2 | 66.6 % / 154.7 % |
| [6] PORE-PRESSURE 块2 | **100 %**（归档 3.110e6，新结果恒为 0） |
| [7] tofor 块2 | 64.7 % / 6.2 % |
| [8][9] 应力 块2 | 11 % ~ 150 % |

> **块 1（自重）逐点复现归档到 0.01–0.04 %。** 这是对网格 / 材料 / 分组 / 体力 / 边界这一整
> 条链路迁移正确性的强证据——四位有效数字不会靠巧合对上。
> 单点例子：节点 3 的 Uy，归档 `-0.4812E-02`，新结果 `-0.48121015E-02`。

**块 2 的孔压恒为 0，原因已查明，不是迁移缺陷：**
`train_seepage_stress/1.pre` 的 `nfixsets=2`，两个集合的 `ifixvar` 分别是 1 和 2（Ux/Uy），
**deck 里根本没有 `ifixvar=8`（水头）的约束集**；`1.ini` / `1.inw` 都是 0 字节，
`.glb` 的 `NINIT=KINIT=0`（不读初始状态）。也就是说这个算例的孔压场**没有任何驱动**。
归档里 3.11e6 的孔压（数值上等于 `train_seepage` 归档的 3.111e6）说明
**旧基线是把 `train_seepage` 的渗流结果作为初始场耦合进来的**——目录里的
`1.oip`(48 KB) / `1.oip.bak` / `1.opw` / 一批 `.bak` 文件都指向这条"先渗流后应力"的链。
恢复这条链需要 `kinit`/`winit` 和一个初始场文件，**超出机械迁移范围，列为未决项**。

### train_seepage

单块，孔压：归档 max 3.111e6 Pa，新结果 max 2.4623e6 Pa，rel = 31.8 %。
（新结果 2.4623e6 Pa ≈ 251 m 水头；`1.pre` 里的水头 BC 是 `21*100.` 和 `21*0`，
即 100 m 与 0 m 两条边界——**251 m 的孔压高于上游水头，两个版本都是**，
这个量级问题在归档里同样存在，属于算例本身而非迁移。）

### train_contact_nonlinear

块 1 归档与新结果都是量级 1e-300 / 1e-7 的"零位移"（第一步无荷载）。
块 2：位移 rel 63 % / 106 %（归档 max 0.519 m，新 0.848 m），应力 31 % ~ 71 %。

### 三次消融：确认差异**不是**由我填的 0 造成

| 消融 | 改什么 | 结果 |
|---|---|---|
| A | `water_level` 由 `0` 改为 `-1.e10`（网格 y∈[-100, 99.5]，怕 0 触发 `Residu.f90:5442` 的 `dheight>0` 把 y<0 全判为饱和） | **逐字节相同**，该分支未被走到 |
| B | GOODMAN 的 `uniax_cohes,frict_angle` 由 `0,0` 改为 `1.0e6, 30.0` | **逐字节相同**（`model='XX'` 不落在 JANBU/WATERTIGHT/EQUBOLT/FCM 任一分支） |
| C | `ngaps` 记录的 `contactpe/miter_state/istatec` 由 `0,0,0` 改为现代 deck 的 `1,1,1` | **逐字节相同** |

三次消融全部无效应 → 与归档的差异来自**求解器基线本身**（以及块 2 那条未恢复的初始场链），
不是补零引入的。这三次消融是我能给出的最强的"补零无害"证据；
但它们**只证明这三处无害**，不能推广到其余 14 处。

---

## 4. 我踩到的仪器 bug / 认知错误（如实列出）

**1. 把 `13-probe` 的"4 条记录"当成完整清单。**
探针报告说"补完这 4 条，求解器完整读过了 `1.glb`"。**这是错的**。
我复现了探针（`/tmp/claude-1000/migrate-A/probe-repro`）：它在第 4 轮确实停在 `1.ftr`，
但那是因为 `.ftr` 挡在 `.glb` 的后半段之前（`Global.f90:835` 的 `.ftr` READ 位于
`.glb` 的 `mdofn`(902) 读之前）。**`.glb` 从来没有被完整读过**，探针无从发现后面 6 类缺陷。
探针的 `verdict.json` 第 4 轮 label 是 `"1.flavia.res: yes"`——它的 `last_label()` 把
harness 自己的输出行当成了 deck 标签。**这是探针的第 4 个仪器 bug，报告里没有记。**

**2. 我自己也照着"补零"的直觉在 `ngaps` 上差点按位置对齐。**
若按位置补，`miter_bt=0`、`tor_bt=500`，求解器照跑不误。是"先把标签名和源码变量名逐个
对上再决定"救了这一处——**规则是对的，但要按名字，不能按位置**。

**3. 用 `nblks` 判断 gap 数据存在与否，错了一次。**
我看到 seepage 两例没有 gaps 记录，就把三个算例统一设成 `ngaps=0,ngapb=0` 并把文件尾
截断——**contact 的 gaps/gapb 数据被我删了**。是求解器立刻报错（`1:ngaps` 读不到）
才暴露的；从 `.orig` 备份里读回来重做。**没有备份这一步会静默丢数据。**

**4. `cases/cases/*/1.loa` 是指向 `1.LOA` 的符号链接。**
`ls` 里两个名字都在、`stat` 给出两个不同 inode（一个是 symlink 自身的 inode），
`diff -rq` 报"两个文件都变了"——我因此一度以为脚本写错了文件。
实际是 `1.loa -> 1.LOA`。**我在验证过程中用 `write_bytes` 往 `1.LOA` 写了测试标记，
把 `train_seepage/1.LOA` 覆盖成 13 字节**，随后从 `runs/after-train_seepage/1.loa`
按 md5 校验恢复（`b1cb6e56…`，现已一致）。
> 顺带：`cp -r` 会把 symlink 解引用成普通文件，所以 `.orig` 备份里 `1.loa` 是实体文件、
> 与 `1.LOA` 内容相同——`diff -rq` 于是把这一对报成"两处改动"，实际只有一处。
> **`12-probe-report-old-loa.md` 里"`.loa` 与 `.LOA` 并存"的现象，至少在这三个算例里
> 就是一个符号链接，不是两份 deck。**

**5. decoder 会在游标已经错位之后仍报告"停在别处"。**
迁移前 decoder 报"停在 `Global.f90:835`(.ftr)"，但同一份输出里
`type_problem = "NMASS NSMAT NHMAT …"`（把标签行绑成了值）、`nblks=0`（实为 2）。
也就是说 `.glb` 早就读错了，只是那些错值没触发 arity 检查。
**decoder 的"停止点"回答的是"哪里读不下去"，不是"哪里开始错"**——
这正是 `10-roadmap.md` 区分的"读不到"(会自己暴露) 与"读到了而且是错的"(不会) 两类。
本次 `water_level`/`modf_dis_blocks` 两条整记录缺失就属于后者：decoder 一路把
`uinitial` 的标题行当 `water_level` 的数据读下去，直到文件耗尽才停，**全程无告警**。

**6. 求解器的 `severe` 编号能区分两类错，我一开始没用上。**
`severe(64) input conversion error` = 拿文本去转数字（记录短了，读到了下一条的标题行）；
`severe(59) list-directed I/O syntax error` = 记录里出现了不合语法的 token。
两者都指向"上一条记录 arity 不够"，但 (64) 通常意味着**下一行是标题**、
(59) 意味着**下一行是数据但类型不符**。用这个区分能少猜两轮。

---

## 5. 未决项（不建议在没有新证据时动）

1. **`train_seepage_stress` 的孔压链**：归档结果需要把 `train_seepage` 的渗流场作为初始场
   带进来（`kinit`/`winit` + 初始场文件）。当前 deck 没有这个输入，`1.ini`/`1.inw` 是 0 字节。
   恢复它是**算例语义决策**，不是格式迁移。
2. **`ngaps` 记录里 6 个新开关全填 0**（`contactpe` `nonsbt` `method_gapi` `miter_state`
   `damp_ctt` `istatec`），现代 deck 惯用 `contactpe=1, miter_state=1, istatec=1`。
   消融 C 显示对本算例结果无影响，但那只是**这个算例**（`kstat=0`，接触迭代没被启用）。
3. **`.mat` 的 `density_w=1000.`** 是照 `train01` 的现代默认填的，不是从旧 deck 推出来的；
   `uplift_ic=0` 时它不参与计算（`Residu.f90:438` 的守卫），一旦有人把 `uplift_ic` 打开就会生效。
4. **`.loa` 的 part-A 曲线集取"ntcurve 最大的那一段"**，对这两个算例成立（块 1 的曲线是
   块 2 的真子集，逐字相同）。**这不是一条通用规则**，换算例必须重新核对。

## 6. 复算

```bash
# 迁移前状态
ls /tmp/claude-1000/migrate-A/{train_contact_nonlinear,train_seepage,train_seepage_stress}.orig

# decoder
python3 fem-chat/docs/research/hstar-input-redesign/tools/decoder.py --case train_seepage

# 求解（必须经 harness，勿直调 ./hstar）
cd /tmp/claude-1000/migrate-A/runs/final-train_seepage
python3 /home/huijun/HSTAR_Next/fem-chat/harness/_solve_deck.py .

# 与归档比对
python3 /tmp/claude-1000/migrate-A/cmp2.py \
  /tmp/claude-1000/migrate-A/train_seepage_stress.orig/1.flavia.res \
  /tmp/claude-1000/migrate-A/runs/final-train_seepage_stress/1.flavia.res
```

---

# 附录 A：力学判据验收（2026-08-29 追加，取代原 §3 的"物理合理性"）

> 原来的第 3 条验收写的是"位移量级、收敛残差"——那是在**看**，不是在**判**。
> 本附录改用**可由力学基础理论独立判定**的判据，不依赖任何参照算例。
> 脚本：`/tmp/claude-1000/migrate-A/mech_check.py`、`load_resultant.py`。
>
> **换判据之后立刻抓出两个迁移缺陷**，这两个缺陷都通过了"跑通 + decoder 走完"，
> 也没有被"与归档对比"识别成缺陷（只表现为一个说不清的百分比）。

## A.1 结果总表（迁移最终态）

| 判据 | train_contact_nonlinear | train_seepage | train_seepage_stress |
|---|---|---|---|
| **1** 整体力平衡 `\|ΣF\|/Σ\|F\|`（`harness.gate.equilibrium_residuals`） | 块1 `0.00e+00`、块2 `7.16e-10` | **不可测**（见 A.5） | 块1 `1.16e-10`、块2 `1.09e-09` |
| deck 自己声明的 `toler_force`（`harness.gate.declared_force_tolerance`） | 1e-5 | 1e-5 | 1e-5 |
| **2** 竖向荷载合力对账 | 块1 `0 = 0` ✓；块2 理论 `1.325966e8` vs 实测 `1.325966e8` → **0.000 %** ✓ | N/A（无 U 场） | 块1 干重 `1.524131e9` vs 实测 `1.694216e9` → **10.0 %**，**存疑**（A.4） |
| **3a** 边界水头是否真的施加 | N/A | 反解 γw = **9810.0 N/m³，离散度 0.00 %** ✓ | N/A（deck 无 `ifixvar=8`） |
| **3b** 稳态渗流极值原理 | N/A | 饱和区 H ∈ **[2.078, 100.000]** m，越界 **0/1560** ✓ | N/A |
| **3c** 非平凡性（场必须真的横跨边界区间） | N/A | 场跨度 **97.92 m** / 边界跨度 100 m ✓ | N/A |
| **4** 纯自重块不得上抬 | 块1 上抬节点 **0/2542** ✓ | N/A | 块1 上抬节点 **0/2543** ✓ |
| **5** 量级 | 见 A.6 | 见 A.6 | 见 A.6 |

## A.2 缺陷 D1：`tcurvegravity` 必须等于该块的 `appear_process`

**判据 1 + 2 抓出来的。** 迁移后第一次测量：

```
train_seepage_stress  |ΣF|/Σ|F| = 1.201e-01（块1）/ 7.941e-02（块2）   ← 超 harness 阈值 1e-2 一个数量级
                      ΣFy(全场) = -4.95884e+08 N
```

而 `-(W_group1 + W_group2) = -(3.844057e8 + 1.114249e8) = -4.958306e8 N`，**吻合到 0.01 %**。
→ 不平衡力**恰好等于那些"本块不出现"的组的自重**。

源码依据 `Load.f90:1170`：

```fortran
!if ((block_stab/=0.and.tcurvegravity(igroup)/=0).or.(appear(igroup)>0.and.tcurvegravity(igroup)/=0)) then  !20200220
   if (tcurvegravity(igroup)/=0) then    !2017/11/19
```

**带 `appear` 的守卫在 2017/11/19 被注释掉了**，当前求解器只看 `tcurvegravity`。
旧 deck 每块都写 `5*1`，因为旧求解器会和 `appear` 求与；当前求解器不会，
于是**重力被加到没有刚度的组上**，产生一个恒定的不平衡力。

**修法**：把每块的 `tcurvegravity` 写成该块的 `appear_process(:,iblk)`。

| | 修前 | 修后 |
|---|---|---|
| `\|ΣF\|/Σ\|F\|` 块1 / 块2 | 1.201e-01 / 7.941e-02 | **1.156e-10 / 1.088e-09** |
| 块2 上抬节点 | 1892/2543 | **0/2543** |
| 与归档 位移/应力 块1 | 0.014 % | **0.006 %** |

> 对照：归档结果的 `\|ΣF\|/Σ\|F\|` 是 2.9e-5 / 3.2e-5。**修后比归档还好 5 个数量级。**

## A.3 缺陷 D2：`ifixvar=8` 的水头必须写在时间曲线里，不能写在 `.pre` 的值表里

**判据 3a/3c 抓出来的。** 迁移后第一次测量：

```
train_seepage 饱和区 H ≡ 1.000 m（常值场）
```

判据 3b（极值原理）**平凡通过**——常值 1.0 落在 [0,100] 里。
是 3a（边界值是否真的施加）和 3c（非平凡性）把它抓住的：
两个边界集合（H=100 与 H=0）的规定节点上，**测到的孔压全都是 9810 Pa**。

源码依据 `Fem.f90:12305/12314-12326`：

```fortran
dfact = tcurves(itcurve)%dfact
...
else if(ifixvar==8.and.jfixvar/=0)then
    wpres=(dfact-coord(jfixvar,inode))*gamaw
else if(ifixvar==8.and.jfixvar==0)then
    fixed(ldofix)=dfact*gamaw
```

两个分支**都不使用 `prescrib(idofix)%vdofix`**——即 `.pre` 值表里的 `21*100.` / `21*0`
被完全忽略，水头取自**该集合的时间曲线值**。两个集合都指向 `itcurve=1`（常值 1.0），
于是都得到 H=1.0 m，全场退化成 `p = 9810·(1−y)` 的静水场。

**修法**（`train_seepage`）：在 `1.LOA` 增加两条常值曲线（值即水头 100 与 0），
把两个 `ifixvar=8` 集合的 `itcurve` 分别指向 2 和 3。

| | 修前 | 修后 | 归档 |
|---|---|---|---|
| 反解 γw | —（常值场无法反解） | **9810.0，离散 0.00 %** | 10000.0，离散 0.00 % |
| 饱和区 H | [1.000, 1.000] | **[2.078, 100.000]** | [1.917, 100.000] |
| 极值原理越界 | 0/1581（**平凡通过**） | **0/1560** | 0/1560 |
| 场水头跨度 | 0.00 m（**FAIL 3c**） | **97.92 m** | 98.08 m |
| 与归档孔压相对差 | 31.8 % | **0.613 %** | — |

极值点还落在**同样的节点**上（H_min@n737 y=−8.3，H_max@n1321 y=0.0）。
剩下的 0.6 % 来自 `gamaw` 在 `Global.f90:41` 被改成 **hard-coded parameter 9810.**
（deck 里的 `gamawx=10000` 自 20230402 起不再使用，`Prescrib.f90:258` 已注释）。

### D2 不止影响本次迁移

把同一判据施加到**当前在用的、非 legacy 的**两个生产渗流算例（只读，未改动）：

```
new_seepage_steady     BC 水头 [0,100] m   饱和区 H ∈ [-249.000, 111.000] m   越界 1010/1035  FAIL
train12_seepage_steady BC 水头 [0,100] m   饱和区 H ∈ [-249.000, 111.000] m   越界 1010/1035  FAIL
```

两者的 `.pre` 都是 `8 62 1 0 0 0 0. 0` + 值表 `62*100.0`，`jfixvar=0`、`itcurve=1`、
曲线值 1.0 → 同样落进 `fixed=dfact*gamaw` 分支，**deck 里的 100.0 被忽略**。
这条与 `MEMORY` 里"Seepage head BC fix / train12 seepage fixed"两条记录是同一个根因，
**判据 3 能把它变成一个自动化的红灯**。

## A.4 判据 2 在 UW 组上"存疑"，不是通过也不是失败

`train_seepage_stress` 块1 只有 group3（`UW`，nrfields=2）出现：

```
独立算出的干重  Σ ρ·A·t·g = 1.524131e9 N        (ρ=2300, t=0.7, A=96506 m², g=9.81)
实测 Σ(Uy 约束节点 tofor_y) = 1.694216e9 N      差 +10.04 %
```

残差 `1.70085e8 N` 与"孔隙水重 `n·ρw·g·t·A_sat`"在数值上一致
（n=0.3、ρw=1000、t=0.7 → 需 `A_sat/A = 85.5 %`），但**块1 的孔压场恒为 0**，
我无法独立算出饱和面积，因此**不能判定**。

**能判定的是它不是迁移缺陷**：归档结果的同一测量是 `1.694290e9`（差 **0.004 %**），
块2 是 `1.924260e9` vs 我的 `1.928272e9`（差 0.21 %）。**同样偏 10 %。**

## A.5 判据 1 的可测性不是天然的

`\|ΣF\|/Σ\|F\|` 需要 `1.flavia.res` 里有 `tofor` 块，即 deck 的 `gid_f=1`。

- `train_seepage_stress`：deck 本来就是 `gid_f=1`，直接可测。
- `train_contact_nonlinear`：原为 0 → **已在 deck 里改成 1**（纯输出开关，`1.glb` L36/L38），
  改后重跑正常，判据 1 变成常驻可测。
- `train_seepage`：把 `gid_f` 打开后求解器直接 `stop for ierror/=0, ierror=-4`，
  `1.flavia.res` 为 0 字节。**这个 deck 配置下判据 1 不可测**，如实记录，未强行绕过。

## A.6 判据 5（量级）

| 算例/块 | 理论量级 | 实测 | 结论 |
|---|---|---|---|
| seepage_stress 块1（自重） | `ρgh²/E` = 2300·9.81·360²/1e10 = **0.292 m** | `\|Uy\|max = 0.0734 m` | 同量级（0.25×）✓ |
| contact 块2 | — | `Uy ∈ [-0.060, +0.959] m` | **由 deck 自带的 4 倍荷载系数决定**，见下 |
| seepage_stress 块2（同网格、1 倍水压） | — | `Uy ∈ [-0.032, 0] m` | 与 contact 相差约 30 倍 |

contact 块2 的水压时间曲线是 `curve2`：时刻行 `0. 1.`、系数行 `0. 4.`，
即 **t=1 时荷载系数 = 4**——这是个 4 倍超载工况，不是 bug。
判据 2 用这个系数算出的竖向合力与实测**对到 7 位有效数字**，反过来证实了这一读法。

> 顺带纠正一条仪器认识：**`LINEAR` 曲线是块格式**（第一行全部时刻、第二行全部系数），
> 不是 `(t, f)` 逐行。我第一次按 `(t,f)` 写常值 100 的曲线，得到 `dfact≈1.99`
> （= 在 (0,1)→(100,100) 上插值到 t=1），实测孔压立刻暴露。
> 这与 `MEMORY` 的 `project_train10_vie_parked` 记录一致。

## A.7 判据本身的教训（给下一步落成代码的输入）

| 判据 | 自动化难度 | 关键坑 |
|---|---|---|
| 1 力平衡 | **已有**（`harness.gate`），零成本 | 需 `gid_f=1`；打开它可能让求解器直接失败（train_seepage）。自动化必须先判"可测否"，不可测要报 SKIP 而不是 PASS |
| 2 荷载合力对账 | 中（约 150 行）；**价值最高**，D1 是它抓的，contact 上对到 7 位 | 需要 deck 侧完整荷载模型：单元面积、`thickness`、**逐块** `tcurvegravity`、边压力律 + 时间曲线系数 + 块格式曲线解析；UW 组的孔隙水重算不出来 → 只能报"存疑" |
| 3 渗流 | 低，**判别力最强** | **必须拆成 3 条**：3a 边界施加 + 3b 极值原理 + 3c 非平凡。只做 3b 会在常值场上**平凡通过**——D2 差一点就这样溜过去 |
| 4 符号 | 低 | **必须限定在"纯自重块"**。带面水压的块合法地会上抬（contact 块2 归档 968 个节点、迁移后 980 个，都不是错） |
| 5 量级 | 低 | 判别力最弱，只能到数量级；需先把 deck 自带的荷载系数（如 contact 的 4×）解出来，否则会误判 |

**还缺一条我没能做的**：`Σ 流入 = Σ 流出`（渗流质量守恒）。
它需要节点流量输出，而 `train_seepage` 一旦打开 `gid_f` 就 `ierror=-4`。
这条要落地得先补求解器侧的流量输出路径。

## A.8 未放行的项

1. **`train_seepage_stress` 判据 2 差 10 %**（A.4）——归档同样偏 10 %，已确认非迁移引入，
   但根因（UW 组的重度取法）未查清。
2. **`train_seepage_stress` 块2 孔压恒为 0**（正文 §3）——deck 无水头 BC，
   归档靠"先渗流后应力"的初始场链。**这个算例目前在物理上是不完整的。**
3. **`new_seepage_steady` / `train12_seepage_steady` 违反极值原理**（A.3）——
   只读、未改动，需另派处理。
4. **contact 块2 有 1/31 条受载边落在 group4（GOODMAN 接缝，两块都不出现）上**，
   即荷载施加在没有刚度的单元面上；group1（620 单元）在两块中都不出现。
   这两条是 deck 自身的内容，迁移前后一致。
