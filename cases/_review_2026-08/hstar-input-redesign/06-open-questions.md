# 待实验判定的问题

> 这些**不是结论**。列在这里是因为 dispatcher 地图的价值之一就是生成可证伪的问题。

## #1 · 那 5 个算例是不是旧格式？【部分回答 2026-08-28】

**已确认是旧格式**，但不兼容点在 `.glb` 的 NINIT 记录（只有 11 项，当前源码读 19 项），
先于 `.LOA` 发生，5 个全部 0.1 秒内 `input conversion error`。
**2026-08-28 续**：补齐 `.glb` 的 4 条旧记录（NINIT/TYPE_PROBLEM/NMASS/NTSMAT，共 14 字段）后，
求解器完整读过 `1.glb`，但失败点转到 **`1.ftr`**——`.LOA` 仍够不着，拦路的换了一个文件。
下一个探针需把补丁范围扩到 `.ftr` 等辅助文件。详见 `12-` 与 `13-probe-report-old-format-peel.md`。

原文如下：


`train_contact_nonlinear` / `train_seepage` / `train_seepage_stress` /
`train_slope_unknown` / `train_vie_boundary` 的 `1.LOA` 每块都带一份时间曲线表。

按当前源码读不通：`external_load_1` 在块循环外只调一次（Fem.f90:1672），
第二块的曲线表会撞进 `external_load_2` 的 `edge_load_group, delgroup`。

但：它们**都有 `1.flavia.res`**（说明历史上跑通过），
且**都不在 15 个基准套件里**（从未被当前求解器验证过）。

**假设**：旧格式，早于 `external_load_1/_2` 的拆分。
**实验**：拿 `train_contact_nonlinear` 过一遍当前求解器。
**影响**：决定 `import_glb` 里那个"显式拒绝"该怎么改——
是补一个旧格式 reader，还是把这 5 个算例标记为需要重建。

**2026-08-28 新证据**：hstarpre 的 `prepare_loa_file` 与当前 consumer 一致——全局时间曲线
只写一次，每施工块只写 `external_load_2` 对应内容。因此那五个每块重复曲线表的文件
不是当前 hstarpre producer 的正常输出；“旧 writer/旧 solver 配对”的假设进一步增强，
但仍必须由当前二进制实跑判定。

## #2 · VIE 下填 `earthquake_curve` 是否真的双重激励？

源码推论见 `02-facts-semantic-drift.md §1`：`fachv` 的计算与施加均不受
`type_ABC` 守卫。

**实验**：同一 VIE deck，`earthquake_curve` 填 / 留 0，跑两遍比结果。
这也是 L4 消融对的第一个标本。

## #3 · `type_problem = 'WT'` 是什么？

源码里存在，文档与工具链完全没有。推测是水+温度耦合。
**实验**：找到它的 dispatcher 分支，看走哪个 reader、`mdofn` 要求什么。

## #4 · `type_ABC = 'MIF'` 是什么？

与 VIE 并列的第三种边界。`.man` 下多读一条
`inpcord, earthquake_curve_MIF(1:ndimn)`（Fem.f90:8530），
消费点在 Fem.f90:17219。**工具链完全不支持。**

## #5 · `train10_dynamic_vie` 修好边界后，0.7~7 倍偏差会不会收敛？

已确认该算例 `cdbound=2` 组混进 30 条竖直边（不在 `y_min` 上），
而入射波只从 `cdbound=2` 进（Fem.f90:13614）。
**实验**：修正 `.ifs` 后重跑，与 Windows 侧结果对比。

## #6 · `.man` 的 17 个 reader 里，静力那 12 个的记录布局差异有多大？

已知 `time_dependent` / `explicit` / `frequency_analysis` 三者首记录不同。
`STATIC_U` / `STATIC_U_reli` / `STATIC_rigid_1` / `STATIC_U_PW` 各 15 条 READ，
布局是否一致未查。**这直接决定 schema 里静力分支要不要再分和类型。**

## #7 · hstarpre 与当前 HSTAR 的兼容矩阵是什么？（新增最高优先级）

hstarpre 的 `prepare_man_file` 对所有 `type_problem/='Q'` 都输出
`nincs, cdtest, earthquake_curve`，只额外区分 VIE/MIF；但当前 HSTAR 的 `.man` reader
还区分 `EXPLICIT`、`E`、`W`。归档的 20 个 `.ctl` 示例只看到 `Q/S + PARDISO`，没有覆盖
`F/E/W/EXPLICIT/VIE/MIF`，因此“hstarpre 能生成这些分支”没有证据。

**实验**：建立 `(type_problem, type_solver, type_ABC)` 组合矩阵，分别比较 hstarpre writer
计划和当前 HSTAR reader 计划；无法对齐的组合必须在新能力注册表里标成 unsupported，
而不是由格式校验放行。

## #8 · hstarpre 示例输出是否由归档源码/二进制生成？

归档含 32 位 Windows `hstarpre.exe`、Fortran 源码、20 个 `.ctl` 及成套输出，但尚未建立
可重复构建与逐文件 provenance。部分源码注释更新到 2024，示例文件也可能来自不同构建。

**实验**：在隔离目录用归档二进制重放一个最小 Q 算例和一个 S 算例；记录 exe hash、
模板 `model1/1.glb` hash、`.ctl` hash及输出 diff。若能重编译，再比较重编译产物与归档 exe。

---

## #7 · `.glb` 头部第二方言的完整字段序是什么？（2026-08-28 新增）

`train_temp_creep` 的 `.glb` 头无 `npoinb`（见 `09-facts-verification.md` §3），
`parse_glb` 按位置硬编码，解析出 nelem=3 / ndimn=1。

**待定**：方言 2 是否只少 `npoinb`，尾部字段（`level_set/ljdp/stab_matde`）是否也不同；
它对应哪个求解器版本；求解器当前是按 15 项还是 11 项读这一记录。
**方法**：`global_data` 的第一条 READ 项数即答案。
**影响**：修 `parse_glb` 的前提；也决定 Deck ABI 里这条记录要不要版本化。

## #8 · ~~`.man` 静力 reader 布局是否一致？~~ 【已回答 2026-08-28】

**答：一致。**10 个 reader（含 `response_spectrum`）共用首记录 `[nincs]`，
静力分支在 Semantic IR 里不需要再分和类型。详见 `11-probe-report-man-readers.md`。

原文如下：


原 #6。`08-revised-architecture.md` 的 Semantic IR 需要知道静力分支要不要再分和类型，
而这完全取决于 `STATIC_U` / `STATIC_U_reli` / `STATIC_rigid_1` / `STATIC_U_PW`
（各 15 条 READ）的记录布局是否相同。

**这是纯源码问题，成本很低，却是 schema 设计的前置条件**——建议从 P2 提到 P0。

---

## #9 · ~~AST 解析器的 40 处构造失配~~【已解决 2026-08-28】

**3 种形态**（老式带标号 DO / 具名 select / 嵌套带标号 DO 共享终止标号），
修复后闭合率 **100.000%**，Deck ABI 909 → 1012（`.mat` 11 → 114）。
探针 6/6 全过，详见 `15-probe-report-ast-mismatch.md`。

原文如下：


`tools/deck_ast.py` 全仓闭合率 99.46%：7445 个 `end` 构造中 **40 个失配**。
这些位置的子树可能错位，而 5/5 验收只覆盖了被检查的那五处。

**方法**：逐一定位失配行，判断是解析器缺形态（如 `goto`、`where`、
未支持的构造写法）还是源码本身不规范。
**影响**：决定 Deck ABI 的哪些部分可信。**这是 Deck ABI v1 的前置条件。**

## #10 · ~~`Bparameter` 的完整语义~~【已回答 2026-08-28】

只有 **3 个互异谓词**：`==-1.or.==-2`（常规分析一条支路）、
`(>0.and.<=2).and.balgor<=1` 与 `.and.balgor==2`（参数反演，含 MKL 信赖域）。
**既有 16 个当前格式算例全部 `Bparameter=0`**，走 else 路径。
反演不额外读 6 个主 deck 的记录，其数据在**未建模的 `.btl`** 里。
探针 5/6，详见 `16-probe-report-bparameter.md`。

原文如下：


AST 显示 `Bparameter` 是最外层调度开关，取值 `0 / 2 / -1 / -2`（还有 `>0.and.<=2` 与 `-3`）。
`-1/-2` 走常规分析；`>0` 走含 `RCI_REQUEST`（MKL 信赖域）的参数反演外循环，
在其中 `.man` 被反复重读。

**工具链完全不知道这个开关存在。**它决定了整棵调度树的最外层，
Semantic IR 的顶层建模必须先搞清楚它。

## #11 · 四种未支持的时间曲线类型

`type_curve` 在源码守卫中出现 5 种取值：
`SEISMIC`（已支持）、`EXTRAPOLATION`、`ARCLENGTH`、`HARMONIC`、`WATERLEVEL`。
`generator.py` 只写 `LINEAR` 与 `SEISMIC`。

`ARCLENGTH`（弧长法）与 `WATERLEVEL`（水位曲线）对本仓库的边坡/大坝算例价值明显。
**方法**：从 `deck-abi.json` 取各自的记录布局，用最小算例做探针。


---

## #12 · ~~把 9 个未建模的输入文件纳入 AST~~【已解决 2026-08-28】

`UNITS` 改为从 `open(unit,file=probn//'.ext')` 导出，覆盖全部 **22 个**输入文件
（比预估的 15 个还多）。READ 1306 → 2216，Deck ABI 1012 → **1716 条**。
新纳入：`_l.glb`(180) `.tem`(175) `.oid`(52) `.sto`(45) `.btl`(44) `.nrt`(43)
`.obs`(40) `_l.bou`(30) `.stn`(20) `.opr`(18) `.ftr`(15) `.gamax`(15)
`.aqu`(10) `.vcor`(9) `.obsc`(8)。verify_ast 仍 5/5。
仅 `unitread`（31 READ）未纳入——文件名来自变量，静态解析不出。

原文如下：


`tools/deck_ast.py` 的 `UNITS` 只映射 6 个 unit（496 条 READ）。求解器实际还读：

```
.btl  47 (参数反演控制)   .nrt  43            .tem  38 (温度)
unitread 31 (待定)        .sol  22            .sto  21 (随机)
.opr  18 (输出控制)       .ftr  17            .obs  10 (观测/反分析)
.aqu  10
```

约 **257 条 READ 未建模**。

**为什么优先**：
1. `data/deck-abi.json` 的 1012 条目前只是"6 个主文件"的，不是完整 Deck ABI；
2. 剥洋洋葱探针补齐 `.glb` 后正是卡在 **`1.ftr`**——不建模它就无法继续往下剥；
3. Semantic IR 的 `outputs` / `numerics` / 反演相关对象大概率落在 `.opr` / `.sol` / `.btl` 里。


---

## #13 · `igap0` 分支于一个可能未初始化的分量（2026-08-28 新增，求解器缺陷）

```fortran
Material.f90:396  if (name=='CONTACT') &
Material.f90:397      read(munit,*) props(imat)%mechanical%solid%igap0, …
Material.f90:401  igap0 = props(imat)%mechanical%solid%igap0
Material.f90:402  if (igap0 == 2) then
```

非 CONTACT 材料时第 397 行不执行，而 401/402 仍取值并据以分支。
该分量的声明 `Material.f90:132 integer(ink)igap0,…` **没有默认初值**。

求解器对所有非 CONTACT 材料都正常工作，说明实际运行中它是 0（编译器零初始化）——
**这是观察到的行为，不是语言保证**。换编译器或换选项即可能改变。

**建议**：在 397 之前显式 `props(imat)%mechanical%solid%igap0 = 0`，或给类型加默认初值。
成本一行，消除一处未定义行为。

---

## #14 · `mesh_io.detect_groups_from_glb` 是文本层的第 7 处独立实现（2026-08-28 新增）

`fem-chat/skills/deck_text.py` 的头注释此前声称"现在只有一份实现"。**这是过度声明。**

`fem-chat/skills/mesh_io.py:192 detect_groups_from_glb` 自带一份逗号方言解析
（`:216-229`：`line.count(",") >= 9` 就 `split(",")`，再 `parts[1].strip("'\" ")`），
不 import `deck_text`，被 4 个模块使用（`import_glb` / `gen_mesh_vtp` / `mesh_preview` /
`mesh_io` 自身）。

**而它才是喂 `.glb` 组行往返的那一处。**这解释了一件我判断错了的事：
我曾说引号 bug（264d870）会影响 train05/05b/11 的往返矩阵——**不会**。
三次实测（基线 / 方言修复后 / 264d870 后）21 行 × 6 列逐字符相同，
因为组行根本不走 `deck_text`，而 `mesh_io` 那份碰巧对引号是对的。

**要做的**：把 `detect_groups_from_glb` 的文本层收编进 `deck_text`，
保留它的领域逻辑（组行字段语义、混合空格+逗号行的回退）。
验收：89 个 `.glb` 的解析结果逐个不变，往返矩阵逐格不变，单测全过。

**为什么重要**：碰巧正确不是正确。这一处目前只是运气好——
同一条规则在本项目已被写错 7 次，第 7 次（引号）之所以没造成往返矩阵的损害，
纯粹因为受害路径没走它。

---

## #15 · ~~VIE 算例该不该开 `force_process`？~~【已有决定性数据 2026-08-29】

**`train_vie_boundary` 的 `force_process = 222*1`（全 5 组为 1，惯性力通路开着）。**
对照 `train10_dynamic_vie` 的 `0 0 0 0 0`。

**同一批 VIE 算例两种取值都出现过 → train10 的 0 不是"VIE 通例"。**
所以 `CLAUDE.md` 那条 `force_process(1:ngroup)=1` 规则**不需要加"VIE 除外"的限定**；
需要判定的变成一个更窄的问题：**train10 的 0 是有意还是遗漏**。
鉴于 `19-probe` 实测 train10 在 fp=0 下地震惯性力完全不参与
（填 earthquake_curve 后全场 max|Δ| = 1e-15），若其本意是地震算例，那是遗漏。

原文如下：


`CLAUDE.md` 的动力地震规则明写 **`force_process(1:ngroup)=1` per group**
（来源：PRJ-6057，硬编码 `force_process=0` 曾导致地震注入失效）。

但 `train10_dynamic_vie` 是 `force_process = 0 0 0 0 0`，
其全部动力响应来自 VIE 入射波，惯性力通路从未打开
（探针 `vie-ablation` 实测：填 `earthquake_curve` 后全场 max|Δ| = 1e-15）。

**问题**：对 VIE 算例，`force_process=0` 是正确设计（入射波已含全部激励，
再开惯性力就是双重计入）还是遗漏？

**为什么必须判定**：
- 若是正确设计，`CLAUDE.md` 那条规则要加"VIE 除外"的限定，否则下一个人会照规则改坏 train10。
- 若是遗漏，train10 的全部历史结果都少了一部分激励。

**方法**：查 `force_process` 在 VIE 相关代码路径中的消费点，看入射波是否也受它守卫；
配合一次带预期关系的消融。

---

## #16 · 诱饵字段：`.ele` 末列与 `.glb` 组块的 `MATNO` 不被消费（2026-08-28 新增）

`migrate-C` 用四次消融钉死的一条 Deck ABI 事实：

```
真实链路：.ele 文件顺序 + NELGROUP → 组号 → .glb 的 MATNO_PROCESS → 1.mat 序号

消融 a  .glb 组块 MATNO 对调        → 坝顶位移 2.21 mm，无影响
消融 b  .ele 最后一列 1↔2 全表对调  → 2.21 mm，无影响
消融 c  1.mat 两条材料行对调        → 15.08 mm
消融 d  MATNO_PROCESS 1 2 → 2 1     → 15.08 mm（与 c 逐位相同）
```

**组块里明写着 `NELGROUP MATNO`，看起来最权威，实际在这条路径上是死的。**

这是"改了看起来对的地方、语法合法、求解器接受、物理不变"的教科书样本。
任何"改了材料号但物理没变"的调试都会在这里空转。

**要做的**：`deck-abi.json` 应标注诱饵字段——即被 READ 读入但在该路径下无消费点的槽位。
`data/use-sites.json` 已有原料（消费点为空即诱饵）。这能自动化。

## #17 · `train02c_*` 的坝体与地基接反（2026-08-28 新增，待使用者决策）

```
组 "Dam"         120 单元  x[0,478] y[-300,0]   143400 m²   ← 实为地基
组 "Foundation"  196 单元  x[200,278] y[0,100]    4300 m²   ← 实为 100m 高坝体
MATNO_PROCESS 1 2  →  地基几何拿 ρ=2400 混凝土，坝体几何拿 ρ=0
tcurvegravity 1 0  →  重力只给地基几何
```

材料参数本身是教科书标准配对，接反了几何。四次消融钉死，修复后自重合力
3.376e9 → 1.0124e8 N（逐位等于坝体理论自重）、坝顶相对位移 2.21 → 27.04 mm、
放大系数 1.114 → 7.29、主周期 0.357 → 0.381 s（百米重力坝一阶 0.3–0.4 s）。

**补丁已验证但未施加**：三行改动会改变算例物理、使归档结果失效，
而"哪个是本意"是建模决策。等使用者判定。

**顺带**：`train02c_dbg` 的 `earthquake_curve = 0 0`，fachv 400 步恒 0
——它根本不是地震算例，是自重突加的自由振动算例。`_dbg` 大概率是有意的调试变体，
但**没有任何文件记录这一点**。

---

## #18 · ~~两个生产渗流算例违反极值原理~~【判据已接入门控 2026-08-29】

**已接入 `run_validity`**：`train12_seepage_steady` 从 PASS 变为 **FAIL**
（`run_validity = incomplete`），套件 13/15 → **12/15**。那个 FAIL 是对的。

接入过程中三条误报被消除（一条会因错误原因失败的检查比没有检查更糟）：
- 模态算例（`type_problem=E`）没有静力反力，`train03b` 曾因"自重消失了"误 FAIL
- 全体积落在约束边界上的模型（`train04`，V=0.02 / V_held=0.001）除零得 rel=inf
- 瞬态场（`type_problem=S`）的界是"初始场 ∪ 边界值 ∪ 对流参考温度"的包络，
  不是边界值本身；`train07` 曾因此误 FAIL

`new_seepage_steady` 不在套件里，仍未修，根因同为 `.pre` 的 `jfixvar=0`。

原文如下：


```
train12_seepage_steady   边界水头 [0, 100] m   场 [-249, 111] m   1010/1035 节点越界
new_seepage_steady       同上
```

**根因（源码确证）**：两者 `.pre` 的 `ifixvar=8` 记录里 **`jfixvar = 0`**。

```fortran
Fem.f90:12314  else if(ifixvar==8 .and. jfixvar/=0) then
                   wpres = (dfact - coord(jfixvar,inode)) * gamaw     ← 用高程，正确
Fem.f90:12326  else if(ifixvar==8 .and. jfixvar==0) then
                   ← 另一分支，.pre 的值表被完全忽略，水头取自时间曲线常值
```

deck 里写着 `62*100.0` 的水头**根本没有被使用**。

**这与已记录的知识是同一根因**：`generator.py` 早已修正（写 `ifixvar=8` 时必须
`jfixvar=ndimn`），但这两个是 **legacy_deck，原样重放，修复从未触及它们**。

**要紧的是**：`train12_seepage_steady` 在 15 个基准算例里，**当前判 PASS**。
三轴门控查收敛、查跨文件一致性，**不查物理**——一个水头场从 −249 跑到 111
而边界只有 [0,100] 的算例，一路绿灯。

`harness/mechanics.py` 的 `extremum_principle` 能把它变成自动红灯。
**是否接入门控需要决策**：接入会让套件从 13/15 变成 12/15，而那个 FAIL 是对的。

> 顺带一条自纠：该检查初版把 `PORE-PRESSURE`（Pa）拿来和水头边界（m）比，
> 在 `train_seepage` 上产生了一次**因错误原因的失败**。已限定为单位可比的场
> （WATER-HEAD / TEMPERATURE）。**一条会因错误原因失败的检查比没有检查更糟。**
