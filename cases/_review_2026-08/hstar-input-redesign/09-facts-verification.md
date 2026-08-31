# 事实四：对 07/08 的独立复核，及复核中新发现的两个活 bug

> 2026-08-28，Claude 侧独立复核。方法与结论同样可复算。

## 1. 更正 #5（`.ifs` 段序）—— 确认成立

```
Fem.f90:200   call stiff_interface_fluid_solid    !!ifs2000
Fem.f90:201   call stiff_absorb_fluid             !!ifs2000
Fem.f90:202   call stiff_absorb_solid             !!ifs2000
Fem.f90:203   call stiff_ifs2006                  !!ifs2006
```

四个调用**各一次、无守卫、无其它调用点**（全仓 `grep call stiff_*` 只有这四行）。
producer 侧 `fempre.f90:5766-5777` 同序。更正成立。

**我原先错在哪**：我按这四个子程序在 `Stiff.f90` 里的**定义行号**排序，
当成了执行顺序。**定义顺序 ≠ 调用顺序**——这与更正 #3 是同一个错误家族
（把"我观察到的那一面"当成全部），也再次说明 07/08 强调的
"reader 集合不含执行顺序，顺序必须由调用点确认"是对的。

## 2. 新发现 A：`elem_info` 静默把一切未知单元变成 Q4（已修）

`generator.py:42` 的查表只有 5 条，其余**全部静默返回 `("Q4", 5, "Quadrilateral")`**：

```
nnode=8  ndimn=2  → Q4   ← Q8 被当成 Q4
nnode=20 ndimn=3  → Q4   ← 20 节点六面体被当成 4 节点四边形
nnode=10 ndimn=3  → Q4   ← 10 节点四面体
nnode=4  ndimn=3  → Q4   ← 3D 四面体被当成 2D 四边形
```

对照 `05-proposal-architecture.md` 的能力挖掘：源码里至少有 12 个单元 index
（1 3 5 9 16 18 20 21 22 23 25 26），生成器认识其中 4 个。

这是本项目主症状的又一个标本：**产物语法合法、求解器接受、单元类型是错的**，
而且没有任何地方会告警。

**已修**：改为 `raise ValueError`，并按"表达不了就拒绝"原则给出可操作的错误信息。

### 修严后立刻炸出 5 个真实算例

`train05b_slope_srm` / `train11_staged_foundation` / `train_contact_nonlinear` /
`train_slope_unknown` 使用 **8 节点 2D 单元**，此前经导入路径全部被静默写成 Q4。

正确取值从四个**能跑的人工 deck**里直接读到，四者一致：

```
train05b / train11 / train_contact / train_slope_unknown
  组行： B8,'  1',5,CO,1,U,ST,PE,  400,1,0,1,1,1,0,0,0,0
         ^^        ^
         名字 B8   index 仍是 5
```

**2D 的 8 节点单元在 deck 里叫 `B8`，index 与 Q4 相同（5），靠节点数区分。**
已补入表：`(8, 2): ("B8", 5, "Quadrilateral")`。

回归：单测 329 全过；往返矩阵中这 4 个算例从"崩溃"恢复为可生成。

## 3. 新发现 B：`.glb` 头部有两种方言，`parse_glb` 按位置硬编码（未修）

```
方言 1（train01 / train11）:
  NPOIN npoinb NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB ...
   1705  1705  1600   2     2      2      0     GIDR    0.0

方言 2（train_temp_creep）:
  'NPOIN  NELEM  NDIMN  NMATS  NGROUP NTLINK outplot KSTAB ...'     ← 无 npoinb
    5628   4720    3      1      1      0     GIDB       0
```

`import_glb.parse_glb` 取 `vals[2]` 作 nelem、`vals[3]` 作 ndimn，
只对方言 1 成立。对方言 2 得到 **nelem=3、ndimn=1**——全是垃圾。

**而且现有的识别条件挡不住**：`parse_glb` 只检查该行同时含 `NPOIN`/`NELEM`/`NDIMN`，
两种方言都满足。

后果：`train_temp_creep` 的全部往返矩阵数字**无意义**，此前未被发现。
这也是 `08-revised-architecture.md` 主张"Deck ABI 必须带 record ID 与版本"的一个实证。

**未修**：需要先确定方言 2 的完整字段序（是否只差 `npoinb`，还是尾部也不同），
以及它对应哪个求解器版本。列入 `06-open-questions.md` #7。

## 4. 这两个发现对提案的支持

新发现 A 是**"独立 decoder + 回读比对"价值的直接证据**：
它不需要 Semantic IR、不需要 Deck Plan，仅靠"生成后回读并比对"这一条，
一次运行就找出 5 个被静默损坏的算例。

新发现 B 是**"capability profile 必须记录证据来源"的直接证据**：
`train_temp_creep` 在往返矩阵里一直有数字，看起来是被覆盖的；
实际上那些数字是从垃圾解析结果生成的。**有数字不等于有证据。**
