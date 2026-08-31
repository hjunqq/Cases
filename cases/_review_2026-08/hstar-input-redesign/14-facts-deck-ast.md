# 事实五：输入 AST —— 整个 deck 读取逻辑的控制流树

> 2026-08-28。工具 `tools/deck_ast.py` / `tools/verify_ast.py` / `tools/dispatch_table.py`。
> 产物 `data/deck-ast.json`（树）、`deck-ast.txt`（可读渲染）、`deck-abi.json`（Deck ABI）。

## 0. 为什么需要树

此前所有提取都是**扁平清单**——这里一批 READ、那里一批调用点。
扁平清单回答不了唯一重要的那个问题：

> **给定这些开关，求解器按什么顺序读什么？**

那是一棵树。这份工作把它建出来了。

节点类型：`SEQ` / `READ` / `IF` / `SELECT` / `LOOP` / `CALL`（读 deck 的被调者就地内联）。
凡是到不了 deck READ 的路径全部剪掉——这就是 76k 行求解器能压成一棵可读树的原因。

## 1. 验收：5/5

**接受标准不是"解析成功"，而是"能重现此前用别的方法独立确认过的事实"。**
一个连已知部分都还原不出的提取器，对未知部分不构成证据。

| 检查 | 独立来源 | 结果 |
|---|---|---|
| `.ifs` 四段调用顺序 | 更正 #5 / `Fem.f90:200-203` | **PASS** |
| `external_load_1` 在块循环外、`_2` 在循环内 | 更正 #3 | **PASS** |
| `.man` 调度守卫可还原 | `01-facts §3` / 探针 man-readers | **PASS** |
| `.glb` 四条记录 arity = 19/11/11/7 | **探针 old-format-peel（跑求解器得到）** | **PASS** |
| 静力 `.man` reader 首记录均为 `nincs` | 探针 man-readers P1–P3 | **PASS** |

第 4 项尤其值得注意：**静态提取的 arity 与动态实验逐层剥出来的完全一致**——
两条完全独立的路径互相印证。

## 2. 主产物：Deck ABI

对每一条 deck READ，求出执行它所需的**完整路径条件**（各层守卫的合取 + 循环上下文）。
这个合取式**就是**调度规则——任何文档都没写、任何样例算例都揭示不了的东西。

**1012 条唯一的（记录 × 路径条件）：**（2026-08-28 修复解析器后，原 909）

> **2026-08-28 更新（open #12 已解决）**：AST 现覆盖**全部 22 个输入文件**。
> `UNITS` 不再手写，而是从 `open(unit, file=probn//'.ext')` 导出——
> 凡被 READ 三次以上且文件名可静态解析的 unit 全部纳入。
> READ **1306 → 2216**，Deck ABI **1012 → 1716 条**。
> （`unitread` 的 31 条 READ 仍未纳入：其文件名来自变量，静态解析不出。）

```
.man   366   .loa   260   _l.glb 180   .tem  175   .glb  126   .pre  125
.mat   114   .oid    52   .sto    45   .btl   44   .nrt   43   .obs   40
_l.bou  30   .ifs    21   .stn    20   .opr   18   .ftr   15   .gamax 15
.aqu    10   .vcor    9   .obsc    8                         合计 1716
```

`.man` 的复杂度是其它文件的数倍，这与它有 17 个 reader 一致。

## 3. 新发现

### 3.1 `Bparameter`：一个此前完全不知道的调度开关

> **2026-08-28 更正**：本节原写「整个 `type_problem` 调度外面还套着一层 `Bparameter`」，
> **说过头了**。实测通往 `time_dependent` 的 126 条路径中 **108 条不含该要求**；
> `Bparameter==-1/-2` 只是 18 条的守卫。而且既有 16 个算例全部 `Bparameter=0`，
> 走的是 else 路径。详见 `16-probe-report-bparameter.md`。

```
frequency_analysis ⇐ Bparameter==-1 .or. Bparameter==-2 ; type_problem=='W'
explicit           ⇐ Bparameter==-1 .or. Bparameter==-2
                    ; type_problem/='Q'.and./='E'.and./='W'
                    ; type_solver=='EXPLICIT'
```

我们此前描述的整个 `type_problem` 调度，**外面还套着一层 `Bparameter`**。
`Bparameter>0 .and. <=2` 走的是另一条路径，里面出现 `RCI_REQUEST`
（MKL 信赖域求解器）——那是**参数反演/优化外循环**。

路径条件最深的记录有 **7 层守卫**：

```
.man Fem.f90:2418
  └ (Bparameter>0.and.Bparameter<=2).and.balgor<=1
  └ RCI_REQUEST==(2)
  └ balgor==0
  └ type_problem=='Q'
  └ nbackf/=0
  └ nbackdT==0
  └ cwater/=0.and.delgroup>0
```

**同一个 `.man` 文件，在反演外循环里被反复重读，且每层守卫都改变读什么。**
这解释了为什么 `.man` 有 17 个 reader。

### 3.2 开关清单（守卫中实际被测试的取值）

| 开关 | 被测试过的取值 |
|---|---|
| `bparameter` | 0, 2, -1, -2, **3, 4** |
| `balgor` | 1, 0, 2 |
| `type_problem` | Q, E, W, F |
| `block_stab` | 0, 1, 2 |
| `relis` / `nbackf` / `nbackdt` / `adina` / `qstatic` / `restart` | 反演·稳定·重启族 |
| `kpload` | 1, 2 |
| **`type_curve`** | **EXTRAPOLATION, SEISMIC, ARCLENGTH, HARMONIC, WATERLEVEL** |
| `type_abc` | MIF, VIE |
| `type_solver` | EXPLICIT |

**`type_curve` 有 5 种，而 `generator.py` 只写 LINEAR 和 SEISMIC。**
`ARCLENGTH`（弧长法加载）、`HARMONIC`（谐振）、`WATERLEVEL`（水位曲线）、
`EXTRAPOLATION` 四种时间曲线类型，工具链完全不支持——又一批净新增能力。

## 4. 对架构的直接含义

`08-revised-architecture.md` 提出 Deck ABI 应含
`reader / record / slot / guard / loop / 版本`。**前五项现在有了，是导出的。**
版本那一维由探针 `old-format-peel` 提供形态（标签行 = 记录版本戳）。

这意味着 `10-roadmap.md` 的 **P1「Deck ABI v1」已经有可用的初版**，
而不是从零开始。`data/deck-abi.json` 可直接作为：

- schema coverage 检查的参照（哪些能力有 writer、哪些没有）
- capability profile 的枚举底表（1716 个格子）
- 生成器"表达不了就拒绝"的判据来源

## 5. 诚实的边界

**必须说清楚这棵树不是什么：**

1. **守卫是文本，没有被求值。**没有约束求解，所以不能自动判定
   "`Bparameter==-1` 与 `type_problem=='W'` 能否同时成立"。互斥/可达性分析尚未做。
2. **`goto` 与递归没有建模。**HSTAR 用到语句标号（本次已支持标号前缀的构造，
   但 `goto` 跳转本身不在树里）。
3. ~~**解析器闭合率 99.46%**，40 处失配~~ 【已解决 2026-08-28】
   闭合率现为 **100.000%（7445 个 end，失配 0）**。三种形态：老式带标号 DO、
   具名 `select`、嵌套带标号 DO 共享终止标号。详见 `15-probe-report-ast-mismatch.md`。
   修复后 Deck ABI 909 → 1012，其中 `.mat` 11 → 114。
4. **1716 条是"记录 × 静态路径"，不是"运行时会执行的记录数"。**
   同一条记录在不同路径下重复计数是有意为之——它们的填法可能不同。

现在最需要跟进的是第 1 条（守卫未求值）：没有可达性分析，就无法回答
"哪些开关组合是真实存在的"，而那正是 capability profile 需要枚举的东西。

## 6. 复算

```bash
python3 tools/deck_ast.py        # 建树，写 deck-ast.json / .txt
python3 tools/verify_ast.py      # 5 项验收，任一失败退出码 1
python3 tools/dispatch_table.py  # 导出 Deck ABI + 开关清单
```
