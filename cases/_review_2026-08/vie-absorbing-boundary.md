# VIE 黏弹性人工边界 — 填一个算例需要什么

> 触发开关：`.glb` 的 `type_ABC = VIE`（`Global.f90:728` 那一行）。
> 一旦置上，求解器会**额外读四处内容**，缺任何一处都会读错位或崩。
> 全部字段语义取自 `hstarYLOrig/HSTAR` 源码，实例值取自
> `cases/cases/train10_dynamic_vie`（2543 节点，x 0~386，y −250~110）。

---

## ⚠ 与普通动力算例最大的一处差别

**VIE 不用加速度曲线驱动，用入射位移波 + 入射速度波。**

```
普通动力   earthquake_curve   = [2, 0]     加速度曲线，经 fachv 进 RHS
VIE       earthquake_curve   = [0, 0]     ← 不用！
          earthquake_curve_d = [4, 0]     入射位移波
          earthquake_curve_v = [3, 0]     入射速度波（源码里 ×2）
```

`Fem.f90:13620-13625`：

```fortran
itdis  = earthquake_curve_d(idimn)
itveloc= earthquake_curve_v(idimn)
if(itdis  >0) dfact1(idimn) =    tcurves(itdis  )%dfact   ! 入射位移波
if(itveloc>0) dfact2(idimn) = 2.*tcurves(itveloc)%dfact   ! 入射速度波 *2
```

槽位含义与普通动力一致：**位置 = 方向**（1 = x 水平/顺河向，2 = y 竖向），
**值 = 该曲线在 `.LOA` 中的出现序号**。train10 的人工 deck 两条都在槽位 1，
即水平入射 —— 与重力坝由水平激励控制一致。

---

## 五个文件分别要填什么

### 1 · `.glb` —— 打开开关

`ninit … type_ABC …` 那一行的第 12 个字段写 `VIE`：

```
NINIT KINIT winit NBLKS NLINK NONSY OUTIP outir outiw neumn equvs type_ABC block_stab …
  0  0  0  1  0  0  0  0  0  0  0  VIE  0  0  0  0  0  0  0
```

### 2 · `.man` —— 多两行，位置固定

标准两行之后**紧接着**插入 VIE 的两行（`Fem.f90:8528-8529`）：

```
 nincs,cdtest,earthquake_curve(1:ndimn)
  1  0  0  0                ← earthquake_curve 全 0（VIE 不用加速度）
  0  0                      ← nstepjq, nstepjp
  0  0.0                    ← hwdirec, hcoord            ← VIE 第 1 行
  -250.0  4  0  3  0        ← inpcord, eq_d(1:ndimn), eq_v(1:ndimn)   ← VIE 第 2 行
  5  0.02  2  2  500  1  1  0  0
  9*1.0e-05
  1  1
```

| 字段 | 含义 | train10 | 依据 |
|---|---|---|---|
| `hwdirec` | 行波方向。**0 = 均匀输入**（无时滞）；>0 / <0 = 沿该坐标轴的行波，按 `timer0=(coord(hwdirec,node)−hcoord)/speed(hwdirec)` 给每个节点加时滞 | `0` | `Fem.f90:13616,13635-13640` |
| `hcoord` | 行波的相位基准坐标，`hwdirec=0` 时无意义 | `0.0` | 同上 |
| `inpcord` | **入射波基准面坐标** —— 传播时间从这里算起：`timer1=(coordzi−inpcord)/speed`。通常取网格底面 | `−250.0`（正是 `y_min`） | `Fem.f90:13678` |
| `earthquake_curve_d` | 入射**位移**波的曲线序号，逐方向 | `4  0` | `Fem.f90:13620` |
| `earthquake_curve_v` | 入射**速度**波的曲线序号，逐方向 | `3  0` | `Fem.f90:13621` |

### 3 · `.ifs` —— 吸收边单元

`nifsgroup` / `nabsfgroup` 两段之后是 `nabssgroup` 段（`Stiff.f90:10412-10453`）：

```
nifsgroup
0
nabsfgroup
0
nabssgroup,exx,uxx,densxx
110         10e9    0.18    2300          ← 边总数 + 边界介质的 E / ν / ρ
sedge,nnode,index,xyz0(1:ndimn),cdbound
60   2     1     193.0  0.0    1          ← 子组：60 条边，L2(nnode=2,index=1)
1471   737   787   1471   3               ← i0, lnods(1:nnode), aelems
1472   693   737   1472   3
…
```

- 子组头可出现多次，直到累计边数达到 `nabssgroup`
- 每条边一行：`i0`、`nnode` 个节点号、`aelems`（该边贴附的实体单元号）
- **`cdbound` 是边界类型**：`1` = 侧边界，`2` = 底边界（`Fem.f90:13614,13665`）。
  **入射波只从 `cdbound=2` 的边进入**；侧边界只做吸收
- 头部的 `exx / uxx / densxx` 用于算波速：
  P 波 `sqrt(alfa/ρ)`、S 波 `sqrt(G/ρ)`（`Fem.f90:13608-13613`）。
  **这套参数与实体单元的材料是分开填的**，填错不会报错，只会让吸收特性不对

### 4 · `.pre` —— 自由面高程表

在 prescribe-set 之后（`Fem.f90:8546-8552`）：

```
62                                        ← nbounods
1 3 6 12 18 28 37 51 63 79 97 119 …       ← list_bound(1:nbounods)，边界节点号
62*0.                                     ← bounfreez(1:nbounods)
```

`bounfreez` → `freez(ipoin)` → `tabss%cordzfree`，用于侧边界的反射波路径：
`timer2 = (cordzfree−inpcord)/speed + (cordzfree−coordzi)/speed`（`Fem.f90:13715`）。
填的是**该边界节点对应的自由面高程**。train10 全填 `0.`（地表在 y=0）。

`nbounods=0` 时整段跳过，`cordzfree` 不被赋值 —— 侧边界的反射项就失效。

### 5 · `.LOA` —— 曲线本体

至少要有位移波与速度波两条 `SEISMIC` 曲线，且 `.man` 里的 `_d` / `_v`
按**出现顺序**引用它们。train10 是第 4 条（位移）与第 3 条（速度）。

`gen_seismic_wave.py` 能合成 a / v / d 三分量（规范谱 + 基线校正），
`run_pipeline.py:234` 在缺 `earthquake_a/v/d.dat` 时自动触发。

---

## 填写顺序建议

1. 先定 `inpcord` = 网格底面高程，再定 `.ifs` 里 `cdbound=2` 的那组边（必须真的在底面）
2. `.ifs` 头部的 `exx/uxx/densxx` 填**边界外侧半无限介质**的参数，不是坝体的
3. `.man` 的 `earthquake_curve` 留 `0`，把曲线号填进 `_d` / `_v`
4. `.pre` 的 `bounfreez` 按侧边界节点逐个填自由面高程
5. 起步先用 `hwdirec=0`（均匀输入），行波时滞等基本工况跑通再开

---

## 自检

| 检查 | 期望 |
|---|---|
| `1.chk` 的 `fachv` | VIE 下加速度曲线不用，**`fachv` 可以恒为 0** —— 不能用它判断"地震有没有进去" |
| 边总数 | `.ifs` 各子组 `sedge` 之和 == `nabssgroup` |
| `aelems` | 每条吸收边引用的实体单元必须存在且贴附该边 |
| `nbounods` | == `list_bound` 与 `bounfreez` 两行的元素个数 |
| `inpcord` | 一般应等于网格 `y_min`；偏离会让传播时滞整体平移 |

---

## 未决 / 注意

- **`gravdam_dynamic_vie.json` 模板当前是错的。**2026-08-26 统一改地震方向时，
  按普通动力的规则给它填了 `earthquake_curve=[2,0]`，但 VIE 不用加速度曲线，
  该字段应为 `[0,0]`。`_v` / `_d` 改到槽位 1（水平）与 train10 的人工 deck 一致，
  这部分是对的。**待修。**
- train10 本身在 `project_train10_vie_parked` 里是挂起状态：包络衰减对得上，
  逐点幅值差 0.7~7 倍未解决。本文只抽取"怎么填"，不代表 train10 的参数值已被验证。
- 生成器 `generator.py` 目前**不写** `.ifs` 的 `nabssgroup` 段与 `.pre` 的
  `nbounods` 段，VIE 算例的这两部分仍需手工准备或从既有 deck 继承。
