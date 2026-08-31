# 探针报告：`Bparameter` 的语义（open #10，预先登记）

> 第五个预先登记探针。材料：`probe/bparameter/`
> （predictions.json + sha256 `76c1986f…` + judge.py + verdict.json）。

## 判决

| | 预测 | 判决 |
|---|---|---|
| P1 | 采用 11 字段 TYPE_PROBLEM 的既有算例 `Bparameter` 均为 0 | **PASS**（16/16） |
| P2 | 存在不要求 `Bparameter∈{-1,-2}` 的常规 reader 路径 | **PASS** |
| P3 | 存在只在 `Bparameter>0` 才可达的 deck 记录 | **FALSIFIED** |
| P4 | `Bparameter` 只被读入一次且来自 `.glb` | **PASS**（初判 FALSIFIED，系仪器故障，见下） |
| P5 | 含 `Bparameter` 的互异谓词 ≤ 8 | **PASS**（3 个） |
| P6 | `RCI_REQUEST` 只出现在 `Bparameter>0` 之下 | **PASS** |

## 1. `Bparameter` 到底是什么

只有 **3 个互异谓词**，整个开关的语义就这么点：

```
Bparameter == -1 .or. Bparameter == -2                        常规分析的一条支路
(Bparameter > 0 .and. Bparameter <= 2) .and. balgor <= 1       参数反演，含 MKL 信赖域
(Bparameter > 0 .and. Bparameter <= 2) .and. balgor == 2       参数反演，另一算法
```

**既有 16 个当前格式算例全部是 `Bparameter = 0`**——都不落在上面任何一个谓词里，
走的是各自的 `else` 路径。

## 2. 对 `14-facts-deck-ast.md` §3.1 的更正

我在 `14` 里写「整个 `type_problem` 调度外面还套着一层 `Bparameter`」。**说过头了。**

实测：通往 `time_dependent` 的 **126 条路径中，108 条不含 `Bparameter∈{-1,-2}` 的要求**。
`Bparameter==-1/-2` 只是其中 18 条的守卫，不是总开关。

我当时只看了路径最深的那几条样本，就把局部当成了全局——
**又一次"把观察到的那一条路径当成全部"**（`03-corrections.md` 横向观察里的同一形态，
这是第四次）。

## 3. P3 证伪，而原因比预测本身有价值

`Bparameter>0` 分支下**没有任何一条专属的 deck 记录**——反演循环是把同样的记录
反复重读，不额外读别的。

追下去发现真正的原因：**反演所需的额外数据在另一个文件里，而那个文件不在 AST 的建模范围内。**

```fortran
Global.f90:756   open(back_ctl_unit, file=probn//'.btl')
Global.f90:1770  if(Bparameter>0 .or. nbackdT==2) then
Global.f90:1771      read(back_ctl_unit,*) text
Global.f90:1772      read(back_ctl_unit,*) Npoints_pb
```

## 4. 最重要的发现：AST 只覆盖了 6 个输入文件，实际至少 15 个

`tools/deck_ast.py` 的 `UNITS` 只映射了 6 个 unit。全仓按 READ 数统计：

| unit | 文件 | READ 数 | 已建模 |
|---|---|---|---|
| mainunit | `.man` | 153 | ✅ |
| gunit | `.glb` | 133 | ✅ |
| munit | `.mat` | 108 | ✅ |
| loadunit | `.loa` | 56 | ✅ |
| punit | `.pre` | 25 | ✅ |
| ifsunit | `.ifs` | 21 | ✅ |
| **back_ctl_unit** | **`.btl`** | **47** | ❌ 参数反演控制 |
| **nrtunit** | **`.nrt`** | **43** | ❌ |
| **tunit** | **`.tem`** | **38** | ❌ 温度 |
| **unitread** | ? | **31** | ❌ |
| **solveunit** | **`.sol`** | **22** | ❌ |
| **stocunit** | **`.sto`** | **21** | ❌ 随机 |
| **outpread** | **`.opr`** | **18** | ❌ 输出控制 |
| **ftfread** | **`.ftr`** | **17** | ❌ |
| **observ_unit** | **`.obs`** | **10** | ❌ 观测/反分析 |
| **mwaqu_unit** | **`.aqu`** | **10** | ❌ |

**已建模 496 条 READ，未建模约 257 条。**

`.ftr` 尤其值得注意：**剥洋葱探针把 `.glb` 的 4 条旧记录补齐后，
求解器正是卡在 `1.ftr`**（`13-probe-report-old-format-peel.md`）。
两个独立探针在同一个未建模文件上会合。

所以 `data/deck-abi.json` 的 1012 条应重新表述为：
**"6 个主 deck 文件的 1012 条"，不是全部输入。**

## 5. 探针自身：第 6 次同类仪器 bug

P4 初判 FALSIFIED，报告有 3 条 READ 读 `Bparameter`。查证：

```
Global.f90:1771   read(back_ctl_unit,*)text  !……Bparameter/=0 时……   ← 注释里提到
Fem.f90:2215      !read(back_ctl_unit,*)text  !……Bparameter……        ← 整行被注释掉
```

两条都是我在 judge 里 grep 原始行、**没剥 `!` 注释**造成的假阳性。
修掉后 P4 PASS。

**这是同一条 deck/源码文本归一化规则在本项目第 6 次咬人**
（`import_glb._Deck` 对了，`man-readers/judge` 忘、`old-format-peel` 忘两次、
本次忘一次）。它已经不是巧合，是结论：**必须只有一个共享的文本层。**

有意思的是：**这次的仪器 bug 反而带来了本探针最有价值的发现**——
正是那两条假阳性把 `back_ctl_unit` 暴露了出来。

## 6. 后续

- 新增 open #12：把 9 个未建模输入文件纳入 AST（`.btl` / `.nrt` / `.tem` /
  `.sol` / `.sto` / `.opr` / `.ftr` / `.obs` / `.aqu` + `unitread`）。
  这直接决定 Deck ABI 的完整性，也是剥洋葱探针继续往下走的前提。
- `14-facts-deck-ast.md` §3.1 的过头表述已更正；1012 条的口径已加限定。

## 复算

```bash
cd probe/bparameter
sha256sum -c predictions.sha256
python3 judge.py
```
