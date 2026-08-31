# 事实二：槽位语义漂移 —— 同一格，不同开关，不同物理

> 原始数据 `data/use-sites.json`（13 个关键变量的全部消费点）。

## 0. 为什么这是独立的一层

READ 语句给出**记录布局**：这一格读几个数、什么类型。
它**完全不给出语义**：这一格是什么意思。

语义只存在于**变量被消费的地方**。而两个语义完全无关的字段，
可以在同一条记录里紧挨着，READ 语句长得一模一样。

这不是理论问题。它是本项目历史上代价最大的一类错误。

## 1. 标本：`earthquake_curve` 在 VIE 下不是失效，是有害

### 读取（布局层面看不出任何异常）

```fortran
Fem.f90:8525   read(mainunit,*) nincs, cdtest, earthquake_curve(1:ndimn)
Fem.f90:8529   if(type_ABC=='VIE') read(mainunit,*) inpcord, earthquake_curve_d(1:ndimn), &
                                                            earthquake_curve_v(1:ndimn)
```

`earthquake_curve` 和 `earthquake_curve_d` 是相邻记录里的相邻数组，READ 形态相同。

### 消费（语义在这里，而且完全不同）

```fortran
Fem.f90:8682-8685   where(earthquake_curve==0) fachv=0.0
                    elsewhere                  fachv = tcurves(earthquake_curve)%dfact
                    ↓
                    fachv → 运动方程右端（13553 / 13852 / 14164 / 14272）

Fem.f90:13620-13621 itdis   = earthquake_curve_d(idimn)
                    itveloc = earthquake_curve_v(idimn)
                    ↓
                    入射位移波 + 入射速度波（FORCE_EXTERNAL 内的 VIE 分支）
```

一个进基底加速度，一个进入射波。**两条完全独立的激励路径。**

> **2026-08-28 重要更正（探针 vie-ablation 实测）**：本节原结论只查了 `type_ABC`，
> **漏了第二个守卫**：`Fem.f90:13527  if(force_process(igroup)==0) cycle`——
> 整条惯性力通路由 `force_process` 逐组控制。
> 所以正确表述是：**`fachv` 的施加受 `force_process(igroup)/=0` 约束，
> 但不受 `type_ABC` 约束**。双重激励成立，但需要 `force_process` 先打开。
> 语义漂移由一维（`type_ABC`）变成二维（`type_ABC × force_process`）。

### 关键：两条路径都没有 `type_ABC` 守卫

- `fachv` 的计算（8682-8687）在 `time_dependent` 内，**不受 `type_ABC` 守卫**
- `fachv` 的施加点 13553 / 13852 / 14164 / 14272，**均不受 `type_ABC` 守卫**
  （13852 的守卫是 `icaddmass/=0`，14272 是 `ipea1==1.and.ipea2==1`，都与 `type_ABC` 无关）

**结论：VIE 下如果填了 `earthquake_curve` 且 `force_process(igroup)/=0`，
基底加速度会叠加在入射波之上——双重激励。**

**实测确证**（探针 `vie-ablation`，见 `19-probe-report-vie-ablation.md`）：

```
train10 原样 (force_process = 0 0 0 0 0)
  eq=0 0 → fachv=0        坝顶 peak|ux| = 0.35015988
  eq=2 0 → fachv=3.1686   坝顶 peak|ux| = 0.35015988   ← 一位都没变
                          全场 2543 节点 × 250 步 max|Δ| = 1e-15（噪声地板）

POST-HOC 打开 force_process = 1 1 1 1 1
  eq=0 0 → fachv=0        peak|ux| = 0.35015988
  eq=2 0 → fachv=3.1686   peak|ux| = 0.37357092   ← 坝顶响应改变 13.7%、峰值 +6.7%
```

**一个此前无人记录的事实：`train10_dynamic_vie` 的地震惯性力通路从未打开过。**
`force_process = 0 0 0 0 0`，它的全部动力响应来自 VIE 入射波。
这也违反 `CLAUDE.md` 里明写的动力地震规则（"`force_process(1:ngroup)=1` per group"）——
对 VIE 算例这条规则是否适用，需要单独判定（列入 open #15）。

文档说"VIE 下 `earthquake_curve` 必须留 0"是对的，但理由不是"没用"，
而是"会多加一份激励"。这个区别很重要：前者听起来像风格建议，后者是错误。

> ⚠ 这是源码推论。物理后果应由一次消融实验确认：同一 VIE deck，
> `earthquake_curve` 填 / 不填，跑两遍比结果。见 `06-open-questions.md`。

### 这个错误实际发生过

外部知识包（KDT 生成的 `SKILL.md §3.1` 与 `build_dynamic_seismic.py`）
断言 VIE 用 `earthquake_curve` 填加速度曲线号。该知识包内部完全自洽、
每条有引用、裁判全绿——因为它的真值来源是文档和样例，不是源码。

## 2. 语义漂移表：应该自动生成的产物

对每个字段，列出「在哪些开关状态下，它的消费者集合发生变化」：

```
earthquake_curve                                    ← 二维:type_ABC × force_process
  type_ABC=FIX, force_process/=0   消费者 = {fachv → 运动方程右端}
  type_ABC=VIE, force_process/=0   消费者 = {fachv → 运动方程右端}   ← 不受 type_ABC 守卫
                                   同时 eq_curve_d/_v 另起一路 → 入射波
                                   ⇒ 告警:两条激励路径同时活跃(实测 13.7%)
  任意 type_ABC, force_process==0  消费者 = {}          ← Fem.f90:13527 cycle
                                   ⇒ 填了也无效,且不报错

cdtest
  time_dependent      存在（第 2 格）
  explicit            不存在 ← 第 2 格变成 earthquake_curve(1)
  frequency_analysis  不存在 ← 第 2 格变成 fachv(1),且是实数不是索引
  ⇒ 告警:同一字节位置三种语义
```

**这张表能自动生成，而且会在任何人动手写 deck 之前就报警。**
它抓的不是"某个字段填错了"，是"这个字段在这个开关下语义漂移了"——整整一类错误。

`data/use-sites.json` 是它的原料，已提取。

## 3. 已确认的其它漂移点

| 字段 | 漂移条件 | 后果 |
|---|---|---|
| `.man` 第 2 格 | `time_dependent` / `explicit` / `frequency_analysis` | `cdtest` / 曲线号 / 加速度实数 |
| `order_time` 第 2 位 | 固体域 vs 流体域 | 质量矩阵指示器；动力算例填 `[0,0]` 会按准静态求解且不报错 |
| `ikindks` | `=3` 损伤 / `=5` 粘结 | `=5` 时 `ftcrack` 变 9 字段且需 `nlocalbeam=1`；生成器写死为二选一 |
| `.ifs` `bkind` | `==2` 多读 `selem` | 条件字段 |
| `.pre` 尾部 | `type_ABC=='VIE'` 时 `time_dependent` 追加读 `nbounods` 表 | 缺失 → `end-of-file during read, unit 4`（文件位置共享） |
| `nabssgroup` / `nabsfgroup` | 有流体域时后者必需 | 缺失 → 流体域全反射，且**所有检查全绿** |

## 4. 为什么"数数自洽"挡不住

本会话查实的两个 VIE 算例都满足 `Σ sedge == nabssgroup`，都通过了当时的全部检查，
而它们的吸收边界一个漏（覆盖不全 61 段）、一个错（30 条竖直边被标成底边界）。

**能通过的检查不构成证据。**可用的判据必须是几何的或实验的：

```
cdbound=2 的边必须全部落在 y_min 上
cdbound=1 的边必须全部落在 x_min / x_max 上
Σ(几何上应有的段数) == nabssgroup + nabsfgroup
有流体域(W 场组) 且 nabsfgroup==0 → 报错
```

这四条已实现在 `fem-chat/harness/consistency.py`，随即抓出 `train10_dynamic_vie`
的 30 条错位边——那个算例此前被人工双机核对过，"两边结果一致"。
**人工双机核对能确认"两边一致"，确认不了"物理正确"。**
