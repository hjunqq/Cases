# 把 decoder 的停止点往前推

> 2026-08-29。接 `18-decoder-report.md`。改动落在 `tools/decoder.py`、`tools/case_path.py`、
> `data/assumptions.json`。复算：`python3 tools/decode_all.py`；验收 `python3 tools/verify_ast.py`（全程 5/5）。

## 0. 一句话

**2.7% → 29.2%**，21 个算例里 **11 个完整走完整棵树**，声明式假设 **4 条 → 3 条**（净减一条：
新登记 7 条，其中 7 条随 `inp` 建模而退役）。

但这一轮真正的产物不是那 26.5 个百分点，是**七个"会出错而不是不完整"的缺口**——
decoder 在这些地方产出的是错值，不是停止。全部已堵上或已停下。

> ⚠ **口径提醒，先读这段。**`data/deck-ast.json` 在本次工作期间被并行重建了 **8 次**
> （AST 从 6 个输入文件扩到 23 个、加 GOTO/LABEL、加 CYCLE/EXIT、保留被剪分支的守卫、
> 拆 `;` 多语句行、修单行 `if` 括号守卫、加 ALLOC、纳入 `inp`）。
> **中间过程的百分比不可逐个相减**——分母（Deck ABI 记录位置）走过 424 → 677 → 682 → 685。
> 起点 2.7% 与终点 29.2% 都在"扩完 AST 之后"的口径下量，可比。
>
> `18-decoder-report.md` 里的 **26.4% 与本文的任何数字都不可比**：那是 6 个输入文件、
> 424 个位置的口径。扩到 23 个文件后同一份 decoder 的真实覆盖率是 **2.7%**。

## 1. 覆盖率变化

### 起点（AST 已扩到 22 个文件，`DECK_FILE` 尚未同步）

```
21/21 个算例全部停在 L838  undecidable guard: nforce/=0
Deck ABI 685 个位置，覆盖 18 个 (2.7%)      .glb 14.3%，其余全 0
```

原因：`.ftr` 的 READ 进了 AST，但 `DECK_FILE` 还是**手写的 6 条**，`.ftr` 从未被打开，
`nforce` 永远读不到。**手写的第二份清单会过期——这是本项目第 8 次实例。**
已改为从 `deck-ast.json` 里出现过的 deck 派生。

### 终点

```
11 × 完整走完
 5 × deck record version mismatch   老格式 .ftr —— 算例事实，不是 decoder 缺口
 2 × loop bounds                    train02c 只有 1.LOA 没有 1.loa —— 算例缺陷
 2 × undecidable guard              模态响应谱迭代收敛判据 —— 真运行时量
 1 × file exhausted                 train_temp_creep 的 1.ftr 是 0 字节

Deck ABI 685 个位置，覆盖 200 个 (29.2%)
```

| deck | 覆盖 | | deck | 覆盖 |
|---|---|---|---|---|
| `inp` | **5/5 100.0%** | | `.opr` | 8/18 44.4% |
| `.ftr` | 10/15 66.7% | | `.pre` | 8/25 32.0% |
| `.ifs` | 14/21 66.7% | | `.tem` | 10/35 28.6% |
| `.glb` | 77/127 60.6% | | `.mat` | 23/116 19.8% |
| `.loa` | 30/52 57.7% | | `.man` | **12/86 14.0%**（首次非零）|
| | | | `.nrt` | 3/43 7.0% |

### 逐算例

| 算例 | 记录 | 读尽 | 停止 |
|---|---|---|---|
| train04_beam_faceload | 436 | 10/13 | 完整走完 |
| train10_dynamic_vie | 329 | 10/13 | 完整走完 |
| train11_staged_foundation | 267 | 10/13 | 完整走完 |
| train06_concrete_damage | 255 | 10/13 | 完整走完 |
| train01_gravdam_static | 242 | 10/13 | 完整走完 |
| train05_slope_stability | 222 | 10/13 | 完整走完 |
| train09_rc_bond | 188 | 10/13 | 完整走完 |
| train02_gravdam_seismic | 177 | 10/13 | 完整走完 |
| train05b_slope_srm / train07 / train12 | 168 / 168 / 158 | 10–11/13 | 完整走完 |
| train03b_modal_ifs / train03a_modal_dry | 230 / 185 | 11/13 | `Fem.f90/response_spectrum:10338` |
| train02c_dbg / _seismic_wave_compare | 131 | 8/12 | 缺 `1.loa`（只有 `1.LOA`）|
| train_contact_nonlinear 等 5 个 | 19–21 | 2/13 | 老格式 `.ftr` |
| train_temp_creep | 20 | 4/13 | `1.ftr` 是 0 字节 |

## 2. 七个"会出错"的缺口

> **这一节比覆盖率重要。**`18-decoder-report.md` §0 写着"只能不完整，不能出错"。
> 这一轮查实：**在七个地方它其实是会出错的**。七处的形态完全一样——
> 游标滑掉若干项、此后全部错位、**不报错**。
>
> 更值得记下的是：其中五处在被发现之前**已经在产出错值**，只是恰好撞上 EOF 或撞上
> "数值记录里混进非数值 token"才停住。**它们不是被协议兜住的，是被运气兜住的。**
> 所以才要一条条堵成显式的停止。

### a · `deck_text.expand` 不认引号（第 7 处文本层 bug，**第一处会绑错值而不是读不到的**）

`'  1'` 在 Fortran list-directed 输入里是**一个**字符项；`re.split(r"[,\s]+", …)`
把它切成 `'` 和 `1'` 两项。train05 的 `.glb` 分组行 `q4,'  1',5,CO,1,U,ST,PE,200,…`
因此整体错位一格：

| 变量 | 正确 | 错成 |
|---|---|---|
| `group%kname` | `  1` | `''`（那个孤立引号）|
| `group%index` | 5 | `1'` |
| `group%class` | CO | 5 |
| `group%nrfields` | **1** | **CO** |
| `group%nelgroup` | 200 | PE |

**它没有报错，绑了一整条错值。**之后在 `Global.f90:1129` 求 `nrfields` 的 arity 时才因为
拿到 `'CO'` 非数值而停下——**是运气，不是设计**。若那一格恰好落在数字上，会一路解到文件尾。

**这一处与前六处文本层 bug 有本质区别**：`18-report §7` 列的那六处（忘了 `!`、
忘了尾空格、grep 原始行……）造成的都是"读不到"；这一处造成的是"读到了、而且是错的"。
前者会自己暴露，后者不会。

修在 `skills/deck_text.py`（第 4 条规则，团队 lead 落的）：`expand()` 改为逐 token 扫描，
引号内整体为一项、不做 `n*v` 展开、不做 `!` 截断。回归 `test_skills` 359 全过、
往返矩阵 `.pre` 仍 21/21。

### b · `!` 吃光整条记录时被当成空记录（第 5 条规则）

`.opr` 第 2 行 `                !=2, nodal stress in whole domain, …` 截断后为空，
`read(outpread,*)text` 于是跳过它、**吃掉了第 3 行真正的数据记录**，
`irecover/wpgroup/wegroup/wggroup/wjgroup` 全部错成 `following is the beginning node`。

Fortran list-directed **输入**里 `!` 不是注释字符——这条记录会把 `!=2,` 作为字符值读给 `text`。
"`!` 截断"之所以在别处成立，是因为注解总在最后一个需要的项之后；
一整条以 `!` 开头的记录不适用。已作为第 5 条规则修入 `deck_text` 并钉进 `test_skills.py`。

### c · `case default` 从来没有被选中 —— **decoder 自己的 bug**

`SELECT` 把 `case default` 当成一个待比较的值，于是 `type_curve=='default'` 永远为假。
`LINEAR` 没有具名 case，于是整个 SELECT **什么都不选、什么都不读**，
游标滞后一条记录，`.loa` 从那里开始全部错位。
修完当时 `.loa` 覆盖从 17% 跳到 71%。

### d · 剪枝把 `if` 的守卫剪没了，只剩 `else`

剪枝规则"到不了 deck READ 的分支剪掉"会把**真分支整个删掉**。decoder 看到
"没有任何非 else 分支为真"，就无条件走 else——而那恰恰是唯一读盘的分支。

```fortran
Load.f90:788   if (water/=0) then  … 用公式算水压，一条都不读
               else                  read(loadunit,*)i0,(press(…))   ← decoder 走了这里
```
train01 的 `water=2`，decoder 连吞 4 条 `.loa` 记录，把 `Define body force` 这样的标签行
当数值读进 `press`。`Fem.f90:268 if(restart==0) … else <读 .man>` 同形，
**只因为 `do iblks=1,lblks` 在 lblks=0 时零次循环才没造成实际读盘——又一次靠运气。**

我先让 decoder 在这种节点上**停下**，然后 lead 改 `deck_ast`：
IF 只要有任一分支存活，其余分支一律**保留守卫、body 置为控制流骨架**。9 处 → 0 处。
（那个"只剩 else 就停下"的保守判断我**保留在 decoder 里**：现在它是死代码，
但一旦剪枝规则再退化，它会立刻把问题变成停止而不是错值。零成本的回归闸门。）

这是"守卫是读取协议的一部分，不是控制流噪声"的第二次实例
（第一次是 `18-report §3b-b` 的"只含 RETURN 的分支被当成空分支"）。

### e · GOTO / CYCLE 没建模，顺序落进被跳过的段落

- `Global.f90:1634 goto 222` 越过 `111 continue`(:1637) 到 `222 continue`(:1650)。
  中间那段读 `.nrt`。decoder 顺序走进去——13/21 个算例的
  `file exhausted Global.f90:1640` 就是这个，**撞上 EOF 才停住**。
- `Temper.f90:79 if(ecwpipe/=1) cycle`：train07 的 `ecwpipe=2`，求解器每轮都 cycle、
  一条不读；decoder 读掉了 `.tem` 的前两行，此后整个 `.tem` 错位。

lead 加了 `GOTO`/`LABEL`/`CYCLE`/`EXIT` 节点（318 / 466 / 465 / 126 个），
语义在 decoder 侧实现，见 §3。

### f · 整数组 READ 被当成 1 项

```fortran
Load.f90:157   allocate(tcurves(itcurve)%dfact_curve(ntime))
Load.f90:213   read(loadunit,*)tcurves(itcurve)%dfact_curve      ← train02 是 1001 项
```
语句本身不含任何长度信息。decoder 把裸名当 1 项，**游标滑掉 1000 项**，
从那里到文件尾全是垃圾，不报错。**train02 和 train10 之前那两个"完整走完"是假的。**

我先让它**停下**，判据取自树本身：同一分量在 :220 有显式 `(1:ntime)` 段——
**这证明它是数组，但不证明这里的长度**，所以只停不猜。
lead 随后加了 1826 个 `ALLOC` 节点带 `extent`，现在按 extent 表达式在读的那一刻求值：
train02 的这条记录 arity 解出 **1001**，`.loa` 读到 EOF。
**求不出 extent 仍然停**，绝不退回按 1 项读。

### g · `case_path.CMP` 把守卫右侧的裸名当字符串字面量 —— **lead 写的 bug**

```python
(?P<r>'[^']*'|"[^"]*"|-?\d+(?:\.\d*)?|[A-Za-z_]\w*)
```
右侧匹配到 `[A-Za-z_]\w*` 时，代码拿它**当字面量**去比。后果有两层：

- `tedge<nedge` 这类"变量比变量"的守卫**永远 UNKNOWN**（比较 `0` 和字符串 `'nedge'`），
  10 个 `do while` 停止点全部由此而来；
- 更糟的是 `a==b` 形态**永远为假**，那是一个**答错**，不是一个未定。

Fortran 里不加引号的右侧就是变量。改成：裸名先查 env，查不到才 UNKNOWN。

### 附带：`criteria(1:2)=='MC'` 子串比较也在答错

`norm_name` 把下标剥掉，于是拿整串 `'MCJOINT'` 去和 `'MC'` 比，判**假**。
已在 `eval_guard` 里对形如 `name(lo:hi)` 且绑定值确为字符串的情形做真正的子串截取。

## 3. 每一步解锁了什么

每一步都跑 `decode_all` 与 `verify_ast`（全程 5/5）。**三次覆盖率倒退都是有意的，理由在表里。**

| # | 改动 | 效果 |
|---|---|---|
| 1 | `DECK_FILE` 从 `deck-ast.json` 派生，不再手写 | **2.7% → 12.3%**，`.ftr`/`.nrt` 首次非零 |
| 2 | **deck 版本戳检查**（§4）| **12.3% → 11.8% ↓** —— 5 个算例改停在错位发生的**那一条**上，而不是在错位之后又多解 3 条 `.ftr` 才因别的原因停下。**少的 3 格本来就是脏的。** |
| 3 | **GOTO / LABEL 语义** | 消掉 16 个 `file exhausted` |
| 4 | **`case default`** 修复（§2c）| `.loa` 17% → 71% |
| 5 | **守卫右侧裸名查 env**（§2g）| 10 个 `do-while` 停止点一次全消 |
| 6 | 停止点带**文件/子程序名** | 见下 |
| 7 | 假设 `Uopt_R`/`gamamax`/`relis`/`sysrelis`/`ADINA` | 4 个算例首次完整走完 |
| 8 | 假设机制加 **`at` 位置作用域** + 假设 `idofn` | `.pre`/`.tem` 首次非零 |
| 9 | **`if/else` 守卫被剪光则停**（§2d）| **28.2% → 19.4% ↓** —— 换掉一处正在发生的静默错读；lead 修好剪枝后全部收回 |
| 10 | ASSIGN 支持**名字到名字的拷贝**（含字符型）| `criteria=props(…)%criteria` 解开 |
| 11 | 守卫支持 **Fortran 子串** | 修掉一个**答错**的守卫 |
| 12 | ASSIGN 求值失败时也走假设 | `blks_new=lblks+1` 解开，14 个算例过 `Fem.f90:319` |
| 13 | **整数组读则停**（§2f）| **28.0% → 27.0% ↓** —— 换掉两个算例的静默垃圾 |
| 14 | **CYCLE / EXIT 语义** | train07 越过 `Temper.f90/boundt` |
| 15 | **"游标不可见"的循环与分支可跳过**（§5）| 9 个算例完整走完，`.man` 首次非零 |
| 16 | `inp` 进入 AST → **退役 7 条假设** | 假设 10 → 3 |
| 17 | **ALLOC extent** 用于整数组读 | train02/train10 完整走完，**11 个** |

**第 6 条值得单说。**`LOOP`/`IF` 节点在 AST 里没有 `file`，停止点原来只报 `L1715`——
而 `1715` 这一行在四个源文件里都存在，我照着 `Load.f90:1715`（`name(1:6)=='NSSoil'`）
看了半天，实际是 `Fem.f90:1715`（`gamamax/=0`）。现在报
`Prescrib.f90/prescrib_set:234` 这样的形式。诊断质量不是锦上添花：
**定位错了就会去修不存在的问题。**

## 4. deck 自带的版本戳：把 13-probe 的发现变成可执行判据

`13-probe-report-old-format-peel` 得到过一个观察：**标签行 = 记录的版本戳**。
这一轮把它落成了 decoder 里的一条检查。

> 标签记录（`read(unit,*)text`）拼出的字段名，若是紧随其后那条 READ 变量名的
> **严格前缀**，则文件里的记录是更短的老版本，按当前 arity 读会冲进下一条记录 → **停**。

- **只产生停止，永不放行。**前缀相等是最严的触发条件，散文标签（"remesh limited values"）
  不含变量名，不会误触。
- **我第一版写错了。**没有排除数组尾部：
  `read(gunit,*)ftcrack,…,nlocalbeam,ndimnrt,listglocbeam(1:nlocalbeam),lelenrt(1:ndimnrt)`
  的标签只写 8 个标量，因为那两个数组在 `nlocalbeam=0` 时贡献 **0** 项——
  **标签短是当前格式，不是老格式**。train01 当场把 11 个算例从 ~140 条砍到 43 条，一眼看出。
  改成"只有当标签漏掉的尾部**全是标量**时才触发"。

抓到的实例：`train_contact_nonlinear` / `train_seepage` / `train_seepage_stress` /
`train_slope_unknown` / `train_vie_boundary` 的 `.ftr` 标签只写 `nforce`，
而当前求解器读 `nforce,ngaps,nforce_gaps,nsafety_gaps`。
**这 5 个 deck 对当前求解器就是老格式**——是 deck 的事实，不是 decoder 的缺口。

## 5. 方法论：位置作用域的假设，与"游标不可见"

这一轮加进来的两个可复用机制。

### 5.1 `at` —— 位置作用域的假设

假设条目可带 `"at": "Prescrib.f90/prescrib_set:234"`，则**只在该源位置的守卫上生效，
求值后立刻解绑**。

为什么必须有：`idofn` 在 `prescrib_set` 里是 `nodfn(…)` 算出来的自由度号，
在别处是普通循环计数器。全局绑定会让陈旧值**静默回答别处的问题**——
正是 `norm_name` 那条注释里"陈旧绑定比没有绑定更糟"的同一条规则。
**假设应当有作用域，就像变量有作用域。**

### 5.2 "游标不可见"的循环与分支

收益最大的一步（放行 9 个算例）。

`do ig=1,listp_group(list_fix(ifixnods))%mgroup`（`Prescrib.f90:292`）的次数来自
`listp_group%mgroup`——`Global.f90:1340` 那段从网格算出来的表，deck 里定不出。
按老规则只能停。但这个循环**自己一条 deck 记录都不读**；它进树只是因为里面有 `goto 10`。

> 一个循环或分支，若其子树内**没有 READ、没有 RETURN**，
> 且它能跳到的每个标号都落在某个**同样不含 READ** 的祖先子树内，
> 那么它跑 0 次和跑 n 次对游标的影响完全相同 —— **跳过它不是猜。**

`goto 10` / `goto 20` 的标号都在 `do igroup=1,ngroup`(`Prescrib.f90:290`) 之内，
而那整个循环不含任何 READ。**搜索结果无论如何，游标都在同一处。**

三条边界：
- 标号在树里找不到 → **不算不可见**（不知去向的跳转不是安全的跳转）；
- 被跳过的循环里的 ASSIGN 也不执行，相关变量保持未绑定，后面用到时**照常停下**——
  是不完整，不是错；
- 同一判据用在守卫不可判定的 `IF` 上（`Prescrib.f90:420 if(local_p4(ipoin)/=1)cycle`）。

### 5.3 GOTO 的三条实现约束（按 lead 的要求）

- **`label` 为 `null`**（计算跳转 `goto (10,20,30),i`）→ **停**，报"destination is a runtime index"。
  当前树里此类节点为 0，处理是预置的。
- **标号是子程序作用域的。**跳转目标只在**当前 CALL 体内**逐层 SEQ 向上找；
  找到 CALL 边界还没找到就停。树里 `222:` 在多个子程序各出现一次，
  跨子程序解析会跳到另一个子程序的同名标号上——**那会比原问题更糟。**
- **后向跳转 = 循环，次数不在树里 → 停。**

## 6. 声明式假设：4 条 → 3 条

### 现存 3 条

| 名字 | 值 | 为什么 deck 定不出 |
|---|---|---|
| `igap0` | 0 | 派生类型分量无默认初值，非 CONTACT 材料从未被赋值（求解器缺陷，open #13）|
| `lblks` | 0 | `restart==0` 分支里的 `lblks=0`，该分支不读 deck 因而 body 被剪空 |
| `idofn` | 非零（`at` 作用域）| `nodfn` 是 `set_elem_dofs` 从网格算出的自由度编号表 |

### 登记后又退役的 7 条

`restart`、`Uopt_R`、`gamamax`、`relis`、`sysrelis`、`ADINA`、`runblks`。全部出自同一条记录：

```fortran
Fem.f90:92   open(inpunit,file='inp')       ! 字面文件名，不是 probn//ext
Fem.f90:94   read(inpunit,*) restart,relis,sysrelis,ADINA,Uopt_R,gamamax
Fem.f90:96   read(inpunit,*) probn
Fem.f90:177  read(inpunit,*) runblks
```

`UNITS` 只收 `probn//ext` 形态的单元，所以 **`inp` 这个主控文件整个漏掉了**——
而 cases 下 **85 个算例目录都有它**。我先按假设机制逐条登记
（why / declaration / evidence / risk 齐全，证据是对 85 个 `inp` 的普查，
其中 74 个 `0 0 0 0 0 0`、5 个五字段老格式、其余同值），
lead 把 `inp` 加进 AST 之后，**七条全部改为读出来的**。

它们没有被删除，而是移进 `data/assumptions.json` 的 `retired` 段，记录曾经是什么、依据是什么。

> **一条假设一旦其真实来源进入 AST，就应当退役。**读出来的值永远优于假设的值，
> 而留着一条不再触发的假设只会让人以为还有更多未知。

顺带：`inp` 第 4 条记录 `probn=1`，这直接**证明**了 `_deck_files()` 里
"文件名 = `1` + 扩展名"那条推断——它不再是推断。

## 7. `case_path.py`：静默丢弃未知开关（已修）+ 一条更正

### 修了什么

未知开关名现在**报错并中止**（exit 2），列出最接近的候选；
`--allow-unknown` 可以继续。判据是扫全树的守卫、`select` 表达式、循环界、arity 与 READ 变量名。

```
$ python3 tools/case_path.py --switches type_ABC=MIF,ntrans_typo=1
错误: 开关 `ntrans_typo` 在整棵树的守卫、循环界与 arity 里从未出现，
      设成什么都不会改变结果；最接近的是 ntrans
已中止。用 --allow-unknown 可以继续（结果与不给该开关时完全相同）。
```

另外，未定守卫过半时输出里直接打一行 ⚠，明说**绝对条数不可当作结论、请比较差集**。

### 一条更正：`ntrans` 的现象不是"被丢弃"

`wt-mif` 报的是"`ntrans` 从 switches 里消失、结果与不给它时逐条相同"。
**前半句我复现不出来**——当前 `ntrans=1` 在输出里在，也在 `--json` 的 `switches` 里。
后半句是真的，但**原因不是丢弃，是三值逻辑的固有性质**：

```
type_ABC=MIF,type_problem=F            → 1797 条，含 Prescrib.f90:228
type_ABC=MIF,type_problem=F,ntrans=1   → 1797 条，含 Prescrib.f90:228   ← 与不给时相同
type_ABC=MIF,type_problem=F,ntrans=0   → 1790 条，不含 Prescrib.f90:228 ← 少 7 条
```

`resolve()` 把 UNKNOWN 分支**保留**，所以不给 `ntrans` 时 `ntrans>0` 那一支本来就在路径里。
**给一个"为真"的值不可能增加记录，只有"为假"的值才看得出效果。**
`certain` 计数也没动，因为同一条守卫是 `ntrans>0.and.ifixvar<=ndimn`，`ifixvar` 仍未定。

这与 `wt-mif` 自己的结论"差集比较才可靠"是同一件事，但机制要说清楚：
**不是工具丢了你的输入，是三值逻辑下"真"不产生差异。**

## 8. 剩余停止点的分类与建议

### A · 求解器运行时量（2 个算例，真边界）

```fortran
Fem.f90/response_spectrum:10338
   if(abs(lamda(istep)-lamda_iter)/abs(lamda(istep)).le.1.e-12) goto 10
```
模态迭代的收敛判据。**deck 里不可能有任何东西定得出它。**

建议：**不要试图推进**。这是"算例 = ABI 树上的一条路径"这个模型的真实边界——
路径的一部分由数值迭代决定，静态解码只能到此为止。
若一定要过，应当是"两条分支各走一遍、取记录集的并/交"这种**分叉解码**，而不是假设。
分叉解码会把"确定覆盖"降级成"两种可能之一"，需要先想清楚覆盖账本怎么记。

### B · 算例本身的缺陷（8 个算例，不是 decoder 的问题）

| 现象 | 算例 | 事实 |
|---|---|---|
| 只有 `1.LOA` 没有 `1.loa` | train02c_dbg、train02c_seismic_wave_compare | 求解器 `open(loadunit,file=probn//'.loa')` 在区分大小写的文件系统上会**新建一个空文件**然后读失败。**这两个算例在本机不可复现。** |
| 老格式 `.ftr`（标签只写 `nforce`）| train_contact_nonlinear、train_seepage、train_seepage_stress、train_slope_unknown、train_vie_boundary | 当前求解器读 4 个字段 |
| `1.ftr` 是 0 字节 | train_temp_creep | `Global.f90:834 read(ftfread,*)text` 直接 EOF |

建议：这八个应当先做**一次 deck 迁移**（`13-probe` 已给出 `.glb` 的机械迁移形态），
再谈覆盖率。`decoder --case <name>` 现在会在"文件缺失且存在同名不同大小写的文件"时
直接打 `⚠`，不必再从"某个名字莫名其妙 unbound"往回追。

### C · 还没走到的 deck（覆盖 0%，共 142 条）

`.btl`(44，反演控制)、`_l.glb`/`_l.bou`(42，分层)、
`.aqu`/`.vcor`/`.sto`/`.obs`/`.obsc`/`.oid`/`.stn`/`.gamax`(56)。

**这些不是 decoder 走不到，是本套件 21 个算例里根本没有这些文件。**
`.man` 只有 14.0% 同理：它 17 个 reader 大多挂在 `Bparameter/=0`（反演外循环）
和 `relis/=0`（可靠度）下面，而 21 个算例全部是 `Bparameter=0, relis=0`。

**要让它们非零，需要的是新算例，不是新代码。**
这正是 `17-case-research-loop.md` 说的"覆盖账本推动算例设计"——
覆盖账本第一次能明确指出**缺哪一类算例**，而不只是"覆盖率低"。

## 9. 仪器 bug 清单（如实，含别人写的）

### 我自己写错、被立刻抓住的四个

1. **版本戳检查第一版没排除数组尾部**（§4）。train01 当场把 11 个算例从 ~140 条砍到 43 条。
2. **`_where_of` 用"子树里第一条 READ"定位子程序所在文件**——`process_analysis` 在 `Fem.f90`，
   但它内联调用的第一条 READ 在 `Load.f90`，于是报了 `Load.f90/process_analysis:1715`，
   **我照着去看 Load.f90:1715，看错了地方**。改成不下钻 CALL body 后正确。
3. **`_invisible_loops` 用 `id(node)` 建索引，却在 decoder 内部重新 `json.load` 了一份树**——
   两份树的 id 不同，索引**全部静默失效，不报错**。改成在 `decode` 首次进入时针对
   **正在解码的那棵树对象**建索引。
4. **一次覆盖率下降的归因错了。**188 → 159 我一度归给刚加的 `_inert`，
   写了对照实验才发现两边都是 159 —— 真因是 `data/deck-ast.json` 在两次测量之间被并行重建了。
   **"我改了 X，数字变了，所以是 X"在共享状态下不成立。**
   这是本轮唯一一次差点写进报告的错误归因。

### 别人写的两个（应当记名，本项目的更正清单是最有价值的产物之一）

5. **`case_path.CMP` 把守卫右侧的裸名当字符串字面量**（lead 写的，§2g）。
   `a==b` 形态**永远为假**——是答错不是未定。
6. **单行 `if` 的守卫用非贪婪 `.*?`，遇到守卫内含括号就在第一个 `)` 处截断**（lead 写的，lead 自己发现）。
   `if(vdimn/=abs(water))cycle` 被切成守卫 `vdimn/=abs(water` + 语句 `)cycle`，**语句整个丢失**。
   任何单行 `if` 只要条件里有函数调用或嵌套括号都中招。修完：
   `CYCLE 150→465、GOTO 183→315、RETURN 18→38、READ 2221→2224`。
   **树此前是不完整的，连 READ 都少了 3 条。**

### 一条环境陷阱

**8 个求解器源文件是 GBK 编码**（`Elements` `Load` `Material` `meshfine` `Output`
`Prescrib` `Solver` `Temper`），普通 `grep` 会**静默跳过**它们。
本文所有工具按字节读（`errors="replace"`）不受影响，但**人工复核必须 `grep -a`**。
`wt-mif` 因此把活代码判成了死代码。

## 10. 复算

```bash
python3 tools/verify_ast.py                                  # 必须 5/5
python3 tools/decode_all.py                                  # 21 个算例 + 真实覆盖率
python3 tools/decoder.py --case train01_gravdam_static
python3 tools/decoder.py --case train02_gravdam_seismic      # ALLOC extent → arity 1001
python3 tools/decoder.py --case train_contact_nonlinear      # 版本戳停止
python3 tools/decoder.py --case train02c_dbg                 # 大小写文件名 ⚠
python3 tools/case_path.py --switches type_ABC=MIF,ntrans_typo=1   # 未知开关 → exit 2
```
