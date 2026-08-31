# config schema 相对 Deck ABI 的缺口 —— 量化版

> 2026-08-29。由 `tools/semantic_roundtrip.py` 机械产出：
> `import_glb → config → generate → decode`，与 `decode(原始 deck)` 逐条比对
> READ 绑定的取值。**不是文本 diff**——见 `17-case-research-loop.md` §2.5。

## 结论

**2/21 个算例语义上完全一致**：`train01_gravdam_static`（242 条记录）
与 `train04_beam_faceload`（436 条记录）。

> `train04` 是被本轮补上的。它原本只差**一处**：`Global.f90:835` 的
> `nforce` deck 里是 19、生成写 0，外加 231 条生成 deck 没有的记录。
> 根因不在生成器——`generator._gen_ftr` 一直能从
> `internal_force_sections` 写出 `.ftr`——而在 **`import_glb` 从来不读 `.ftr`**。
> deck 有截面、导出的 config 没有，再生成就写成 `nforce=0`，
> 整个内力截面块随之消失。
>
> 修法上有一个刻意的选择：**截面位置与法向从节点坐标反推，
> 不信 `(station=0.05)` 那行注释。**读注释在我们自己生成的 deck 上能用，
> 在手写 deck 上会失效——正是本项目反复付学费的那种失效。
> 单元测试里专门放了一个"注释撒谎"的用例（写 `station=99.0`，
> 几何是 0.5，必须按 0.5 走）。
>
> 同时补了一条拒绝规则。第一版让 `train_contact_nonlinear` **从"可对比"
> 变成"生成崩溃"**：那是个 2D 算例，按**边**切（`nnode=2`）且记录布局也不同，
> 而 `_gen_ftr` 只写 3D 六面体的 4 节点面。**导入一个生成器复现不了的
> 规格，比什么都不导入更糟**——它把一个可度量的差异变成了运行时崩溃。
> 现在遇到 `nnode≠4` 或 2D 网格一律拒绝并给出理由。

缺口共 **54 个槽位、325 处**，全部带源码行号。这把
"round trip 是有损的"这个定性结论，换成了一张可以照着补的清单。

## 命中最多的槽位

| 算例数 | 位置 | 变量 | deck | 生成 |
|---:|---|---|---|---|
| 53 | `Stiff.f90:10453` | `i0, tabss(tedge)%lnods(1:nnode), tabss(tedge)%` | `['1471', '737', '787', '1471']` | `['1', '1656', '1592', '1501']` |
| 28 | `Global.f90:1114` | `group(igroup)%name, group(igroup)%kname, group` | `['Q4', 'Water', '5', 'CO', '1', 'W', 'ST', '` | `['Q4', 'Water', '5', 'CO', '1', 'U', 'ST', '` |
| 17 | `Global.f90:960` | `gid_u, gid_s, gid_ms, gid_f` | `['1', '1', '0', '0', '0', '0', '1', '0', '0'` | `['1', '1', '0', '1', '0', '1', '1', '0', '0'` |
| 13 | `Global.f90:963` | `res_u, res_s, res_ms, res_f` | `['0', '0', '0', '0', '0', '0', '0', '0', '0'` | `['1', '0', '0', '0', '0', '1', '1', '0', '0'` |
| 12 | `Global.f90:987` | `Icaddmass, swlifs2006, toth, ifswater` | `['0', '202', '202', '2', '9.8', '0.6', '-10'` | `['0', '50.0', '50.0', '2', '9.8', '0.6', '10` |
| 11 | `Global.f90:989` | `ftcrack, coefMpa, ikindks, doubsig` | `['1.5e6', '1.0e6', '5', '1', '1.0e8', '1.0e8` | `['1.500E+06', '1.0e6', '0', '2', '1.0e8', '1` |
| 11 | `Prescrib.f90:209` | `nfixsets, nline` | `['3', '50']` | `['3', '3']` |
| 10 | `Global.f90:958` | `average_appear(1:ngroup)` | `['-2', '-2', '-2', '-2']` | `['2', '2', '2', '2']` |
| 9 | `Global.f90:1140` | `nfdof` | `['1']` | `['2']` |
| 9 | `Global.f90:1145` | `group(igroup)%dof(ifield)%listdof_f(1:nfdof)` | `['8']` | `['1', '2']` |
| 9 | `Global.f90:775` | `nmass, nsmat, nhmat, nqmat` | `['999', '999', '999', '999', '999', '0', '99` | `['1', '1', '1', '1', '0', '0', '1', '0', '1'` |
| 9 | `Global.f90:1000` | `ntrans, nlaymif, epsMIFb, gamaMIF` | `['0', '0', '1.0e0', '0.02', '2', '1979', '25` | `['0', '0', '1.0e0', '0.02', '2', '1980.0', '` |
| 8 | `Global.f90:677` | `npoin, npoinb, nelem, ndimn` | `['322', '322', '285', '2', '4', '4', '0', 'G` | `['322', '322', '285', '2', '4', '4', '0', 'G` |
| 7 | `Global.f90:903` | `mdofn` | `['2']` | `['8']` |

## 按性质分四类

| 类别 | 代表 | 后果 | 严重度 |
|---|---|---|---|
| **场类型丢失** | `Global.f90:1114` fieldid `W`→`U`；`mdofn` / `lmdofn` / `listdof_f` | **渗流/温度问题被改写成位移问题**。train12 的 `W` 场（自由度 8 水头）变成 `U` 场（自由度 1,2） | **改变物理** |
| **驱动量丢失** | `force_process`、`earthquake_curve`、瑞利 `alfa/beta`、`miter/ditime` | train02 的地震整个消失——正是 PRJ-6057 的故障模式 | **改变物理** |
| **边界表丢失** | `Stiff.f90:10453` `tabss%lnods`（53 处，最多） | VIE 吸收边界的边节点表对不上，节点号完全不同 | **改变物理** |
| 输出开关 | `gid_*` / `res_*`（30 处） | 只影响输出内容，不影响解 | 无害 |

前三类是 `03b-facts-roundtrip.md` 那个"生成 vs 保存"结论的**逐字段版本**。

## 由此得出的一条操作规则

**不要给这 15 个 legacy 算例写 `config.json`。**

写进去会让 `quick_analysis.py .` 走 Mode A，即"有 config 就按 config 重新
生成 deck"。而上表说明，对这些算例重新生成会**丢掉定义该算例的物理**——
train12 会从渗流变成应力，train02 会丢掉地震。

**闸门条件 1 报"legacy deck 没有 config"是诚实的，
而绕过它的办法不是补一个 config，是先补 schema。**

## 下一步（有序，按解锁算例数）

1. `fieldid` / `mdofn` / `lmdofn` / `listdof_f` —— 场类型与自由度表进 schema
2. `force_process` / `earthquake_curve` / `alfa,beta` / `miter,ditime` —— 动力驱动量
3. `tabss%lnods` —— `.ifs` 吸收边界边表
4. `999` 哨兵（`nmass` 等，train05 系列）—— 先弄清 999 的语义再决定要不要表达


---

# 三线程并行收口（2026-08-29）

三个 worktree 并行做三类缺口，回来后逐个合并、每合一个复跑一次全量语义回读。

| 线程 | 目标 | 单独测得 |
|---|---|---|
| A 场类型/自由度 | `fieldid`、`mdofn`、`lmdofn`、`listdof_f` | 513 → 437（六处目标槽位 67 → 0） |
| B 动力驱动量 | `force_process`、`earthquake_curve`、瑞利阻尼、增量表 | 513 → 481 |
| C VIE/边界表 | `tabss%lnods`、`Global.f90:987/1000` | 513 → 260 |
| **合并** | | **513 → 157（−69%）** |

三者各自从同一基线量，所以**单独的数字不可相加**；合并后比任何单线程都低，
说明三类缺口基本正交。**没有任何算例的差异数回升。**

单元测试 391 → **627**，全绿。

## 合并时的两处冲突（都不是自动可判的）

- `import_glb.py`：A 的自由度块与 C 的附加质量/MIF 块落在同一个循环里，
  **两个都保留**——它们是独立的 `if` 分支。
- `generator.py`：A 与 B 都改了组抬头行写法。**取 A 版**——它是
  `nrfields` 感知的，且会在 `kname` 需要引号时加引号（`'  1'` 与 `1`
  是不同的绑定值，规则 4），B 那一版是 A 之前的旧抬头行，意图已被覆盖。

## 剩余缺口：36 个槽位、157 处

| 算例数 | 位置 | 变量 |
|---:|---|---|
| 17 | `Global.f90:960` | `gid_u, gid_s, gid_ms, gid_f` |
| 13 | `Global.f90:963` | `res_u, res_s, res_ms, res_f` |
| 13 | `Prescrib.f90:209` | `nfixsets, nline` |
| 11 | `Global.f90:989` | `ftcrack, coefMpa, ikindks, doubsig` |
| 9 | `Global.f90:775` | `nmass, nsmat, nhmat, nqmat` |
| 8 | `Global.f90:677` | `npoin, npoinb, nelem, ndimn` |
| 8 | `Temper.f90:300` | `npipe, algo_pipe` |
| 6 | `Global.f90:753` | `type_problem, type_solver, type_load, type_n` |
| 6 | `Material.f90:289` | `material, density, ratio, thickness` |
| 6 | `Global.f90:1005` | `water_level(1:nblks)` |
| 5 | `Output.f90:4155` | `irecover, wpgroup, wegroup, wggroup` |
| 5 | `Global.f90:3330` | `ngaps, ngapb, contactpe, miter_bt` |

差异最多的算例：

| 算例 | 数据不同 |
|---|---:|
| `train_seepage_stress` | 20 |
| `train_contact_nonlinear` | 19 |
| `train_seepage` | 16 |
| `train_vie_boundary` | 15 |
| `train05_slope_stability` | 14 |
| `train_slope_unknown` | 14 |
| `train_temp_creep` | 10 |
| `train05b_slope_srm` | 9 |

**性质变了。**上一轮排在最前的是"场类型丢失""驱动量丢失""边界表丢失"
——都改变物理。现在前两名是 `gid_*` / `res_*` **输出开关**（30 处），
对解无影响；`Prescrib.f90:209 nfixsets,nline` 与 `Global.f90:989 ftcrack`
等才是下一批真问题。

## 闸门仍是 2/21

条件 3 要求**恰好为零**，所以 6→2、10→2 这样的改善不体现在闸门上。
但离通过很近的算例多了：`train03a` 剩 1 处，`train02` / `train02c_dbg` /
`train02c_seismic_wave_compare` / `train03b` 各剩 2-3 处。


---

# `nstepjq, nstepjp`：一次"源码语句 vs 调度层"的误判（2026-08-29）

并行线程报了一条存疑项：`Fem.f90:8526`

```fortran
read(mainunit,*)text
read(mainunit,*)nincs,cdtest,earthquake_curve(1:ndimn)
read(mainunit,*)nstepjq,nstepjp !20231215YL      ← 前后都是无条件读，没有守卫
```

看上去是**无条件**的，但语料里只有 `F`/`S` 的 deck 有这一行，
`Q`/`E` 的没有。结论似乎是"要么部署的求解器有归档源码没有的守卫，
要么那些 deck 解码整体错位"。

## 实验先于推理

给 `train01`（`type_problem=Q`）插入一行 ` 0  0` 再求解：

```
forrtl: severe (24): end-of-file during read, unit 9, file 1.man
```

**多出来的那条记录把后面每一个读取都推移一位，文件提前读完。**
不改动的对照副本正常求解。所以"补 0"不是无害的，是**会打断每一个
Q/E 算例**。

## 真正的原因：守卫在调用层，不在语句层

`Fem.f90:8526` 属于 `subroutine time_dependent`（定义在 8470 行），
而它的唯一调用点是 `Fem.f90:1938`：

```fortran
if (type_problem/='Q'.and.type_problem/='E'.and.type_problem/='W') then
    call modf_time_order
    if(type_solver=='EXPLICIT') then
        call explicit
    else
        call time_dependent          ← 8526 在这里面
```

所以这条读**在 `time_dependent` 内部确实无条件，但 `time_dependent`
本身是被调度的**：`Q`/`E`/`W` 走另一个 `.man` reader，根本不读它。
语料的分布（`F` 有、`Q`/`E` 没有）与生成器现有规则**完全正确**。

## 这正是本项目的核心命题

> **(调度路径, 开关状态) → 记录布局**

只看一条 READ 语句有没有 `if`，是**语句层**的判断；
真正决定布局的是**这个 reader 会不会被调用**。
本项目建 AST、建 dispatcher map，要解决的就是这一层。

**解码器早已是对的**——它从驱动走 AST，天然带着 `Fem.f90:1937` 那个守卫：

| 算例 | type_problem | 读 `Fem.f90:8526`？ |
|---|:---:|---|
| `train01_gravdam_static` | Q | 否 ✓ |
| `train03a_modal_dry` | E | 否 ✓ |
| `train12_seepage_steady` | Q | 否 ✓ |
| `train02_gravdam_seismic` | F | **是** ✓ |

**结论：不补 0，什么都不改。**生成器、解码器、语料三者本来就是一致的。


---

# 处置记录（2026-08-29 审计后，使用者裁定）

| 类别 | 裁定 |
|---|---|
| **材料常数**（`Material.f90:643` CONCRETE 等，train06 型） | 槽位作用已知；参考算例给默认值可接受，实际使用时给具体值。材料 deck 的 AST 级完整解码复杂度高，**列为后续阶段问题**，本轮不追。条件 3 继续如实拦截 |
| `Prescrib.f90:209 nline` | 早期程序遗留参数，作用不大（已核实不给任何 READ 定尺寸）。低优先级 |
| `gid_*` / `res_*` 输出开关（30 处） | 对解无影响，维持现状 |
