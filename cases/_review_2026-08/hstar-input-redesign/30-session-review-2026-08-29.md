# 会话复盘 —— 2026-08-29「用 train01-12 走完整个循环」

> 本文写给**外部评审者（包括其他 AI）**。目标不是展示成果，而是把这一轮的
> 方法、数据、判断依据和已知缺陷摆出来，便于被挑错。
>
> 自足阅读：不需要先看仓库其他文档。相关背景文件在结尾"延伸阅读"列出。
> 评审时请优先看 §7「请重点质疑这些」。

---

## 0. 一句话

把 `17-case-research-loop.md` 里写了很久但**从未执行过**的六条放行闸门变成代码，
用 21 个 train 算例跑完整个循环，过程中新增两类第一性原理判据、
把"回读一致"从人工免检变成可判定，并把 config schema 相对求解器 ABI 的缺口
从 513 处降到 157 处。

**通过闸门的算例：0 → 2。**

---

## 1. 背景与问题

HSTAR 是一套 Fortran 有限元求解器（约 76k 行，署名可追到 1997 年 GEHOMadrid），
输入是 23 个纯文本 deck 文件，共 1724 条记录位置。核心难点不是格式复杂，而是：

> **(调度路径, 开关状态) → 记录布局 × 槽位语义**
>
> 同一个槽位在不同开关下含义会漂移。例：`.man` 的 `earthquake_curve` 在
> 固定边界下是地震波曲线号；在 VIE 吸收边界下，驱动改由
> `earthquake_curve_d` / `_v`（位移波 + 速度波）承担。

上一阶段使用者给了一个关键批评：

> "我感觉陷入了一个无底洞，不断发现新的问题，又不断修复，不符合自我研究的方式。"

诊断写在 `28-evidence-triage.md`：**跟的是最强的信号，不是循环。**
每个缺陷都真、都便宜，但没有终止条件。对策是先分诊再调查，
并立下一条硬纪律：**当前问题之外发现的缺陷进待办，不立即修。**

本轮就是在这条纪律下，第一次真正把循环跑完。

---

## 2. 方法：先度量，后修复

### 2.1 把闸门变成代码（`harness/case_gate.py`）

六条放行条件，逐条机械判定：

| # | 条件 | 判定方式 |
|---|---|---|
| 1 | 路径上无未知槽位 | 解码器走完整棵树，且算例有 `config.json` 使槽位可归属 |
| 2 | 每个默认都有交代 | 解码器用到的假设都在 `assumptions.json` 里带 why/declaration/evidence/risk |
| 3 | 回读一致 | 见 §3.3 |
| 4 | 物理证据分级 | `run_validity` 至少有**一条正向**第一性原理检查（`unverified` 不算通过） |
| 5 | 覆盖率已记录 | 该算例覆盖的 ABI 位置已知 |
| 6 | 知识已落地 | 人工判断（唯一非机械项） |

**闸门刻意只做度量、不做修复**：报告每个算例离通过还有多远，然后停。

### 2.2 首次运行的收获：形状比数字重要

```
train01_gravdam_static   READY
其余 20 个                BLOCKED
14 个算例卡在同一个守卫 local_p4(ipoin)/=1
```

**"14 个卡在同一处，且恰好第 1 个通过"是缓存 bug 的指纹，不是求解器的复杂性。**
根因确实是本项目自己的 harness：`decoder._INVISIBLE` 是一组 `id()`，
只对建立它的那棵树有意义，却按 `is not None` 缓存，
同进程解码第二个算例时静默失效（且树被回收后 id 可能复用）。

> 如果一上来就去读 `local_p4` 的 Fortran 语义，会读到一个**真实存在但完全无关**
> 的实现细节，然后"修好"一个不存在的问题。这是"先度量"最直接的收益。

---

## 3. 本轮的四项实质产出

### 3.1 模态第一性原理判据（`harness/mechanics.py`）

模态运行没有力，所有基于力的检查一律 `unverified`。而 `1.chk` 一直在逐阶打印
判定所需的一切：`omega`、`mstar`(=φᵀMφ)、`kstar`(=φᵀKφ)。

| 判据 | 内容 | 为什么是不变量 |
|---|---|---|
| `modal_rayleigh_quotient` | ω² = k\*/m\* | 瑞利商定义。**非构造性恒等式**：ω 出自特征值求解器，m\*/k\* 出自组装矩阵投影 |
| `modal_spectrum_ordering` | ω > 0 且升序 | K 半正定、M 正定 ⇒ 广义谱实非负 |

实测残差 6e-7 ~ 4e-5，**容差由打印精度定**（`1.chk` 只有 5 位有效数字），取 1e-3。

**独立旁证**：train03b（带水 IFS）f₁=3.227 Hz < train03a（干）f₁=3.996 Hz，
附加质量降低频率——理论预言的方向由两个算例自己给出。

### 3.2 动力第一性原理判据 —— ⚠ 本节核心主张已被审计推翻，更正见文末附录

> **审计更正（2026-08-29）**：下文"这条会抓住 PRJ-6057"是**错的**。
> `acceleration_absolute` 是输出时构造的（`Output.f90:1472`：
> `result_second + fachv`），`fachv` 直接取自输入曲线（`Fem.f90:8683-8686`），
> 与激励是否进入 RHS（`Fem.f90:13553`，受 `force_process` 门控）无关。
> `force_process=0` 时该判据照样报 ok。使用者确认 `_absolute` 块就是
> 为后处理观看而加的。该判据已降级为**输入链一致性检查**：
> fail 仍然真实（曲线没被读到/槽位错向），但 ok 不再计入闸门条件 4 的
> 正向物理证据。原文保留如下，供对照。

先量后改：`tofor` 在动力算例里**不含重力**（Σ竖向≈0），
全局 d'Alembert 平衡需要 `βKu̇` 而 K 拿不到——**不是缺理论，是缺输出**。

可用的是纯运动学恒等式：

```
ü_abs(node, t) = ü_rel(node, t) + ü_g(t)
```

所以 `ü_abs − ü_rel` 必须在每个节点上相同，且顺带**反推出求解器实际施加的地面运动**。

这条会抓住本项目最贵的动力事故 PRJ-6057（地震从未进入右端项：deck 声明了曲线、
求解收敛、位移画出来像那么回事，而地面根本没动过，当时所有检查都通过）。
**声明了曲线而反推 ü_g 恒为零是自相矛盾，不是容差问题。**

两个容差陷阱（均已在单元测试中钉死）：
1. **过零点**：ü_g 每周期过零，按瞬时值归一化 = 噪声除以 ~0（第一版在好算例上报 0.33）
2. **灾难性抵消**：打印 `-185.53732` 与 `-185.70464`，八位有效数字，
   差值 0.167 只剩五位。**按被减数量级归一化**：同一个 1.4e-5 抖动，
   除以 0.275 是 5e-5（误判 fail），除以 185 是 8e-8（它真实的样子）

VIE/MIF 算例一律 `skip` 而非通过——它们经 `_d`/`_v` 驱动，这条读不到。
**空洞的通过就是把 `unverified` 当 `pass`。**

### 3.3 语义回读：条件 3 从"免检"变成可判定

原有的 `roundtrip_matrix.py` 按行比对重新生成的 deck，**会过报**。实证：

```
0  0  0  0  0  0  0  0     (原始)
0  2                       (生成)
```

`Global.f90:1131` 在这里只读**一项**，Fortran 记录尾丢弃规则把其余全丢掉——
两份 deck 都绑定 `order_time = 0`，**求解器分不出来**。

条件 3 真正问的是"求解器看到的是不是同一份 deck"，Deck ABI 解码器可直接回答。
`tools/semantic_roundtrip.py` 分三类计数：

| 类别 | 含义 | 是否算差异 |
|---|---|---|
| **数据不同** | READ 绑定的数值不同 | **是** |
| 注释不同 | `text` 读入的抬头行 | 否（读进丢弃变量） |
| 数值等价 | `0` vs `0.0` | 否（同一个 REAL） |

后两类必须分开：第一版按字符串比，`0` vs `0.0` 让**每个算例**都报差异，
`.mat` 里 34 处 `COMMENT` 抬头成了全语料最大的"差异"。

**闸门因此变严：6/21 → 1/21。**此前的 6 里有水分——条件 3 是 `manual`，等于免检。

> **一个只报好消息的闸门没有用。**它拒绝了五个一小时前刚宣布通过的算例，
> 理由具体到源码行号。

### 3.4 三线程并行收口

三个隔离 worktree 并行做三类缺口，回来后逐个合并、每合一个复跑全量：

| 线程 | 目标 | 单独测得 |
|---|---|---|
| A 场类型/自由度 | `fieldid`、`mdofn`、`lmdofn`、`listdof_f` | 513 → 437（目标槽位 67 → 0） |
| B 动力驱动量 | `force_process`、`earthquake_curve`、瑞利阻尼、增量表 | 513 → 481 |
| C VIE/边界表 | `tabss%lnods`、`Global.f90:987/1000` | 513 → 260 |
| **合并** | | **513 → 157（−69%）** |

各自从同一基线量，**单独数字不可相加**；合并低于任何单线程，说明三类基本正交。
**无任何算例的差异数回升。**

---

## 4. 数据

### 4.1 全程指标

| 指标 | 开始 | 结束 |
|---|---:|---:|
| 通过放行闸门 | 0 | **2** / 21 |
| 语义完全一致的算例 | （未度量） | **2** / 21 |
| 语料数据差异合计 | 513 | **157** |
| deck 被完整解码 | 11 / 21 | **20** / 21 |
| 解码器停止点 | 10 | **1** |
| Deck ABI 绝对覆盖 | 138 / 424 | **224 / 685** |
| 单元测试 | 371 | **627** |

### 4.2 逐算例语义差异（数据类）

| 算例 | 前 | 后 | | 算例 | 前 | 后 |
|---|---:|---:|---|---|---:|---:|
| train01_gravdam_static | 0 | **0** | | train10_dynamic_vie | 130 | **6** |
| train02_gravdam_seismic | 6 | **2** | | train11_staged_foundation | 12 | **7** |
| train02c_dbg | 11 | **3** | | train12_seepage_steady | 9 | **3** |
| train02c_seismic_wave_compare | 12 | **3** | | train_contact_nonlinear | 24 | **19** |
| train03a_modal_dry | 2 | **1** | | train_seepage | 37 | **16** |
| train03b_modal_ifs | 10 | **2** | | train_seepage_stress | 32 | **20** |
| train04_beam_faceload | 1 | **0** | | train_slope_unknown | 17 | **14** |
| train05_slope_stability | 21 | **14** | | train_temp_creep | 19 | **10** |
| train05b_slope_srm | 12 | **9** | | train_vie_boundary | 138 | **15** |
| train06_concrete_damage | 4 | **4** | | train07_thermal_transient | 8 | **3** |
| train09_rc_bond | 9 | **6** | | | | |

> 覆盖率的分母同时从 424 涨到 685——树里能走到的地方多了，被枚举出的 ABI
> 位置也就多了。**百分比 32.5% → 32.7% 基本持平，不要读成"没有进展"**：
> 分子分母一起长，绝对覆盖涨了 62%。

### 4.3 剩余缺口的**性质变了**

```
17× Global.f90:960   gid_u,gid_s,…      ← 输出开关，对解无影响
13× Global.f90:963   res_u,res_s,…      ← 同上
13× Prescrib.f90:209 nfixsets,nline     ← 下一批真问题
11× Global.f90:989   ftcrack,ikindks
```

上一轮排头的三类——**场类型丢失、驱动量丢失、边界表丢失，全部改变物理，已清零**。

---

## 5. 本轮修掉的自身缺陷（都由度量暴露，非猜测）

| # | 缺陷 | 后果 | 如何发现 |
|---|---|---|---|
| 1 | `decoder._INVISIBLE` 按 `is not None` 缓存 `id()` 集合 | 同进程第二个算例起，每个本该跨过的守卫都变成停止；树回收后 id 可能复用 | 闸门首跑的**分布形状** |
| 2 | `_invisible_loops` 的 goto 判据过强 | 前向提前退出（`if(converged) goto 10`）被当成不可判定 | 逐个看剩余停止点 |
| 3 | `parse_pre` 的 VIE 自由面读入**从未生效** | 失败的 `find` 把游标留在 EOF，循环后永远读到空记录、静默返回 `None` | 线程 C |
| 4 | `import_glb` 从不读 `.ftr` | train04 丢 `nforce=19` + 231 条记录 | 语义回读 |
| 5 | 我给 `.ftr` 导入器加的第一版**制造了回归** | `train_contact_nonlinear` 从"可对比"变成**生成崩溃** | 强制全量回归检查 |
| 6 | 文档 `str.replace` 锚点失配 | 两次提交的文档**实际没落盘**，而我已在回复里描述了内容 | 事后核对 `git show --stat` |

**第 5 条是最有价值的教训**，已写成纪律：

> **导入一个生成器复现不了的规格，比什么都不导入更糟**——
> 它把一个可度量的差异变成了运行时崩溃。

**第 6 条是诚信问题**：我报告了未写入的内容。`decoder` 的补丁我用了
`assert old in s`，文档的没用。差别就在这里。

---

## 6. 两个方法论判断（可能最值得评审）

### 6.1 判据必须先问"它是不是不变量"

沿用 `28-evidence-triage.md` §4：

```
自重合力对账   Σ反力 = Σρ·V·g      守恒律，是      → 可作判据（闭合到 1.4e-9）
极值原理       内部不超边界         椭圆方程性质，是 → 可作判据（抓出 train12）
瑞利商         ω² = k*/m*          定义，是        → 可作判据（本轮新增）
地面运动恒等式 ü_abs−ü_rel 处处相同 运动学，是      → 可作判据（本轮新增）
衰减比         结构衰减/输入衰减    随频率/阻抗而变，否 → 不可作判据
放大系数       顶/底峰值比          经验带，半是    → 只报 degraded
```

**不是不变量的量，不要试图"规范化"它——直接不做成判据。**

### 6.2 "语句层无条件" ≠ "布局上无条件"

一个并行线程报了存疑项：`Fem.f90:8526` 的 `read(...)nstepjq,nstepjp` 前后
都是无条件读、没有守卫，但语料里只有 `F`/`S` 的 deck 有这一行。

**我做了实验而不是推理**：给 `train01`（`Q`）插入 ` 0 0` 再求解 →

```
forrtl: severe (24): end-of-file during read, unit 9, file 1.man
```

多出的记录把后面每个读取推移一位。真正的原因是**守卫在调用层**：
8526 属于 `subroutine time_dependent`，其唯一调用点被

```fortran
if (type_problem/='Q'.and.type_problem/='E'.and.type_problem/='W')
```

包着。**这正是本项目的核心命题**：只看一条 READ 有没有 `if` 是语句层判断，
真正决定布局的是这个 reader 会不会被调用。解码器从驱动走 AST，早已是对的。

---

## 7. 请重点质疑这些

1. **闸门的六条是否是对的六条？**尤其条件 1（"legacy deck 无 config 即不可归属"）
   是否把一个工具链缺陷伪装成了算例缺陷。
2. **`unverified` 不算通过**这条是否过严？它导致条件 4 大量阻塞，
   但放宽会让"无从判断"混进"判断为对"。
3. **语义回读把 `text` 记录排除在差异之外**——是否漏掉了真实的结构错位？
   （理由：`text` 读进丢弃变量；但记录数不同会移动后续读取。
   现有做法是分开计数而非忽略。）
4. **地面运动判据的容差按被减数量级归一化**（§3.2）——
   是否存在一类真实违反会因此被掩盖？
5. **闸门 2/21 是否代表了真实进展？**语料差异降了 69%，
   但闸门只从 1 涨到 2，因为条件 3 要求恰好为零。二元闸门是否合适？
6. **三线程并行的合并**：两处冲突由我人工判定
   （`import_glb` 两个分支都保留；`generator` 取 A 版）。
   取舍是否正确？见 commit `49724a0`。
7. **train06_concrete_damage 差异 4 → 4，完全没动**。为什么它没被任何一类覆盖？

---

## 8. 已知未决

| 项 | 状态 |
|---|---|
| 剩余 157 处数据差异（36 个槽位） | 已量化定位，未修；前两名是输出开关（30 处，对解无影响） |
| 15 个 legacy deck 无 `config.json` | **结构性**。已确立规则：**不要给它们写 config**——会让 `quick_analysis.py` 走 Mode A 按有损 config 重新生成，丢掉定义算例的物理 |
| `train_temp_creep` PARDISO 组装 SIGSEGV | 未解 |
| `new_seepage_steady` 的 `jfixvar=0` | 同根因，未修 |
| 条件 6「知识已落地」 | 唯一非机械项，仍靠人工 |
| `train02c` 坝/地基分组疑似互换 | 3 行补丁已验证，**未施加**，等使用者判断 |

---

## 9. 延伸阅读（同目录）

- `17-case-research-loop.md` —— 循环定义与闸门六条，含本轮逐段更新
- `28-evidence-triage.md` —— 证据分诊、证据等级、版本敏感性、判据是否为不变量
- `29-schema-gap-quantified.md` —— schema 缺口逐槽位清单（带源码行号）
- `03b-facts-roundtrip.md` —— "生成 vs 保存"的原始结论
- `harness/case_gate.py` / `harness/mechanics.py` / `tools/semantic_roundtrip.py` —— 本轮主要代码

## 10. 复现

```bash
cd fem-chat
python3 harness/case_gate.py                                   # 闸门全量
python3 docs/research/hstar-input-redesign/tools/semantic_roundtrip.py   # 语义回读（约 15 分钟）
python3 skills/test_skills.py                                  # 627 项单元测试
```


---

# 附录：审计结果与处置（2026-08-29，按 31-audit-brief 执行）

> 说明：本次为**自审**（审计者与被审计者同源），此局限已计入结论。

## 结论：部分可信

数字全部复现（627/0 测试、闸门 2/21、语料 157），B4 变异测试 3/3 被抓住
（测试非装饰性），B1 确认自陈的两次文档未落盘无新残留，瑞利商经源码核实
**非空洞**（`omega=1./sqrt(lamda)` 出自幂迭代，`kstar/mstar` 出自独立的
矩阵-向量组装，Fem.f90:10391-10393）。

但发现一处**致命**、一处**重要**：

## F1（致命，已修）：ground_motion_input 抓不住 PRJ-6057

证据链：`Output.f90:1472` `acceleration_absolute = result_second + fachv`
（输出时构造）；`Fem.f90:8683-8686` `fachv = tcurves(earthquake_curve)%dfact`
（直接读输入曲线）；`Fem.f90:13553` 激励进 RHS 处受
`if(associated(...fstif))` 即 `force_process` 门控。三者意味着
`force_process=0` 的故障算例：fachv 非零 → 恒等式成立 → 方向匹配 → 判据 ok
→ 条件 4 正向通过 → **错误结果可 READY**。train02 上 3.3e-8 的闭合是
printf 的证据，不是力学自洽的证据。

**处置**（使用者确认 `_absolute` 就是后处理观看用的）：判据降级为输入链
检查，从 `case_gate.FIRST_PRINCIPLES` 移除；fail 仍拦截（曲线未读/槽位
错向是真故障），ok 不再单独满足条件 4。train02/02c 的条件 4 如实回到 ✗
（它们本就卡在条件 3，READY 计数不变）。"槽位=方向"实验结论**不受影响**
——fachv 的下标在 13553 同时就是力的方向。

## F2（重要，按使用者决定挂起）：材料常数是未分类的改变物理项

B6 解剖 train06 命中：`Material.f90:643` CONCRETE 损伤常数被生成器写死
（deck `ft=1.7e7, D=0.619, n=5` → 生成 `3.48e7, 0.1, 6`，抗拉强度翻倍）。
四分类里没有"材料常数"这一类。

**使用者处置**：槽位作用已知，参考算例给默认值可接受，实际使用时会给
具体值；材料 deck 的 AST 级完整解码复杂度高，**列为后续阶段的问题**，
本轮不追。闸门条件 3 会继续如实拦截此类算例。

## 次要

- `Prescrib.f90:209 nline`：使用者确认是早期程序遗留参数，作用不大
  （核实：不给任何后续 READ 定尺寸，循环由 nfixsets/nfixnods 驱动）。
- 注释差异不入闸门：可辩护——两 deck 同一 AST 解码，记录错位必然
  表现为数值差异。

## 对 §7 七问的裁定

1. 条件 1 确把工具链缺陷记在算例头上，但导出的操作规则正确；改标签不改判定
2. `unverified` 不算通过是**对的**——F1 证明真正的危险在反方向：空洞的正向通过
3. text 排除可辩护  4. 容差没问题，问题在判据含义  5. 二元闸门保留，标量并列报告
6. 合并取舍正确  7. train06 = 材料常数盲点（F2）


---

# 附录 2：交叉审计（Codex，`32-audit-report-2026-08-29.md`）的处置

Codex 独立执行了同一份审计指令，其发现与自审**在 F1 上收敛**（构造性恒等式，
双方独立给出同一证据链），并**多抓到四个自审漏掉的问题**。逐条处置：

| Codex 发现 | 严重度 | 处置 |
|---|---|---|
| 条件 1 只查 config **存在**：换成 `{}` 仍 READY | 致命 | **已修**：条件 1 要求 `type_problem`+`groups`+`materials` 齐备。复跑其攻击：空 config → BLOCKED |
| 条件 3 读**过期缓存**：禁用 parse_ftr 后 train04 仍 READY | 致命 | **已修**：条件 3 在闸门运行时**活算**（直接调 `semantic_roundtrip.compare`），缓存仅作导入失败时的降级并标注。复跑其攻击：禁用 parse_ftr → 条件 3 当场 ✗ |
| `amplification_factor` 是经验带却给第一性原理 `pass`；train10/train_vie_boundary 的条件 4 全靠它 | 致命 | **已修**：降为 `info`/`degraded`，从 FIRST_PRINCIPLES 移除。train01 静力的 crest/heel 也有 4.3——它区分不了"地震响应"与"重力静挠度" |
| 剩余缺口只报 `value_diffs`，漏了 489 条 `only_in_orig`：真实非注释缺口是 646 不是 157 | 重要 | **采纳**：此后双数并报（见下） |
| 地面运动 spread 按全局最大 operand 归一化，大分量掩护小分量 | 重要 | **已修**：逐分量归一化 |
| "6 条中无 fail"表述夸大——条件 6 从不拦截 | 重要 | **已修**：输出改为"五条机械条件无 fail；条件 6 仍需人工核定" |
| 测试硬编码仓库绝对路径，不可迁移到隔离副本 | 次要 | 记入待办 |

## 条件 4 的真判据：`seismic_oscillation`

amplification 降级后，动力分支需要一个**真的**第一性原理判据。PRJ-6057 的
教科书症状（CLAUDE.md 原文）是"位移单调爬升、无振荡"——而**振荡性是不变量**：
带惯性的弹性结构在非零瞬态激励下必然围绕准静态解振荡，单调响应不可能。
零/非零判别，不是经验带。

实现：坝顶−坝踵**相对**位移（刚体平动被抵消）的显著方向反转计数
（步长须超过量程 2%，积分噪声伪造不了反转）。实测 train02 = 125 次反转、
train02c = 182 次；证伪测试覆盖单调爬升（fail，报文点名 PRJ-6057）、
爬升+亚阈噪声（仍 fail）、无声明激励（skip）。

## 加固后的数字（全部重测）

| 指标 | 加固前 | 加固后 |
|---|---:|---:|
| 通过闸门 | 2/21 | **4/21**（train01/02/03a/04） |
| 语义完全一致 | 2/21 | **4/21** |
| 值差异 | 157 | **127** |
| 非注释语义缺口合计（含 only_in_orig 489） | 646 | **616** |
| 单元测试 | 627 | **641** |

train02 按使用者指令推过闸门——注意它是在**更严**的闸门上通过的：
条件 3 活算归零（gid/res 逐位透传），条件 4 由振荡不变量而非任何空洞检查支撑。


---

# 附录 3：train02c 与 train03b 过闸（2026-08-30）

两处缺口，性质不同：

## train02c：Newmark 积分常数（`Global.f90:908`）

deck 用 **γ=0.6, β=0.3025**——α=0.1 的数值阻尼 Newmark 对；生成器写死教科书
保守对 0.5/0.25。**这是改时间积分器的差异**，不是格式差异。逐位透传，
新 config 不带 `newmark` 键时保持原默认。

## train03b：FSI 流固耦合边表（`Stiff.f90:10213-10250`）

线程 C 当时**刻意拒绝**导入 `nifsgroup≠0` 的 `.ifs`——理由成立：生成器只会
写 `nifsgroup 0`，导入吸收表而丢整段 FSI 会产出无人记录的缺段 deck。
本轮把拒绝的**前提**解决掉：config 携带逐条边表（`i0, lnods, aelemf,
aelems`，40 条），生成器原样写回——与 VIE 吸收表、`.pre` 自由面表同一
优先级规则（deck 是权威，推导留给新 config）。`nabsfgroup≠0` 仍整文件拒绝。

顺带收益：train02c_dbg（legacy，无 config）的回读也归零——同样的 Newmark
差异；它仍被条件 1 如实拦截。

## 数字（全量重测）

| 指标 | 附录 2 后 | 现在 |
|---|---:|---:|
| 通过闸门 | 4/21 | **6/21** |
| 语义完全一致 | 4/21 | **7/21** |
| 值差异 | 127 | **123** |
| 非注释缺口合计 | 616 | **570**（only_in_orig 489→447） |
| 单元测试 | 641 | **646** |

READY：train01 / train02 / train02c_swc / train03a / train03b / train04。
**有 config.json 的 6 个算例全部在加固后的闸门（活算条件 3 + 振荡不变量）
下通过。**剩余 15 个全部卡在同一个结构性事实上：legacy deck 没有 config。


---

# 附录 4：import 缺口清零——21/21 语义完全一致（2026-08-30）

使用者选定第一条路（"把 import 剩余缺口清完"）后，三个隔离 worktree
并行（D 全局标量 / E 荷载曲线 / F 材料段），逐个在主线独立复跑后合并，
最后补上全语料最后一处（`Prescrib.f90:214` 的 `gamawx`——fixset 头行的
槽位 3/6/7 被读后丢弃，train_seepage 的水容重 10000 被写成 0.）。

```
                值差异   仅原始   仅生成   完全一致
本轮开始          123     447       0       7/21
D 全局标量         52     387       0       9/21
D+E 荷载曲线       25     293       0      11/21
D+E+F 材料段        1       0       0      20/21
gamawx             0       0       0      21/21
```

**import→generate 对 21 个 train 算例已经语义无损**：解码器逐条对比
READ 绑定值，零差异、零缺失记录、零多余记录。单元测试 646 → 771 全绿。

代表性根因（每线程一个）：
- **D**：train_contact_nonlinear 的 NINIT/NBLKS 标签行是小写，大写匹配
  读不到 → nblks 塌成 1，双块结构整簇丢失。
- **E**：parse_loa 对带引号标签方言（`'TIME CURVE in each BLKS'`）整文件
  拒绝——按标签 find() 跳读正是静默漏掉方言的原因，重写为镜像求解器
  READ 顺序的顺序读取器。
- **F**：.glb 头 NMATS 是材料 **ID 数**（props 数组大小），不是 1.mat 的
  块数——train09 NMATS=2 却有 3 块（GEOMETRY 块复用 imat=2）。

三方合并冲突的裁决原则：**更忠实者胜**。E 的 2D `.ftr` 结构化透传胜过
F 的整文件 raw（raw 降为仍被拒形态的回退）；F 的 `tem_raw` 整文件携带
胜过 D 的 `tem_pipe` 单行（后者留作无 raw 时的路径）。

## 这一步解锁了什么

`29-schema-gap-quantified.md` 那条操作规则——"不要给 legacy 算例写
config.json，import 有损"——**前提已经消失**。现在给 15 个 legacy 算例
生成 config 是安全的：regenerate 出的 deck 与原 deck 在求解器看到的
每一个绑定值上一致。闸门条件 1/3 对它们的结构性拦截可以据实解除。

尚未做（下一步）：实际为 15 个算例落盘 config.json 并跑闸门。
注意 CLAUDE.md 规则——写入 config.json 会让 quick_analysis.py 走
Mode A 重新生成 deck；现在这是安全的，但落盘前仍应逐例跑一次
semantic_roundtrip 确认，并备份原 deck。


---

# 附录 5：15 个 legacy 算例落盘 config——闸门 8/21（2026-08-30）

前提已由附录 4 建立（import 语义无损）。执行：全目录备份 → 逐例复跑
semantic_roundtrip 确认精确（15/15）→ `import_glb --save` 落盘。

## 闸门 6/21 → 8/21，且阻塞的性质彻底变了

```
train01/02/02c_swc/03a/03b/04          READY（原有 6 个）
train05_slope_stability                READY（新——条件 4 本就有正向自重对账）
train_seepage_stress                   READY（新）
```

**条件 1/3/5 全语料通过**（唯一例外 train_temp_creep 的条件 1，
decoder 停在 `props(imat)%heat%water_curve`——AST 把 `heat%alfa` 按
1 元素解而实际 `allocate(alfa(ndimn))`，线程 F 已定位，属 decoder 缺口
不属 import）。结构性拦截从此消失。

## 剩余 13 个阻塞全部是条件 4，分三类

| 类 | 算例 | 性质 |
|---|---|---|
| 缺该物理类的正向判据 | 10 个（damage/thermal/contact/VIE/staged…） | 检查缺口——mechanics.py 还没有它们那一类的不变量 |
| **真实物理违反** | train05b（global_equilibrium fail）、train12（extremum WATER-HEAD fail） | **闸门正确拦截**——train12 的水头场 [-249,111] 超边界 [0,100] 是本项目最早的实锤发现之一 |
| decoder 缺口 | train_temp_creep | heat%alfa 数组尺寸，已定位 |

**这是闸门第一次把"工具没做完"和"算例真的有问题"分干净**：
两个 fail 是真违反，十个 unverified 是判据覆盖缺口，一个是 AST 缺口。
往 8/21 之上推进的路径不再是修 import——是给渗流/热/损伤/接触各补
一条第一性原理正向判据，以及修那两个真实违反的算例。


---

# 附录 6：三线并行收官——闸门 17/21（2026-08-31）

三个并行线程（G 补判据 / H 修真实违反 / I 修 decoder）全部落地后的最终闸门：

```
READY   17/21
BLOCKED  4/21，全部卡在条件 4，全部有名有姓：
  train02c_dbg        死 deck：无任何驱动机制（FIX 且 earthquake_curve=0 0、
                      无 VIE 记录），响应为机器零（6.6e-16）。修或退役
  train05b_slope_srm  真 SRM 签名：末块失衡是刻意扫过破坏点的量测本身
  train_slope_unknown 真实力平衡违反，尚未调查
  train_temp_creep    结果文件是 gzip 的 GiD 二进制流（GiDPostEx1.1），
                      文本检查读不了；1.chk 为空。需重算才可判
```

## G 落地的四条判据（全部过"是否不变量"审）

| 判据 | 类 | 要点 |
|---|---|---|
| `extremum_principle[水头]` | 稳态渗流 | 极值原理对 h=z+p/γw 成立而非对 p；边界值取 Dirichlet 节点场值并用 deck 曲线回声校验 γw（顺带钉住版本敏感的单位）；APPEAR 过滤死组节点 |
| `thermal_transient_envelope` | 瞬态热 | 抛物型极值原理 + 诚实条款：一致质量阵合法下冲（train07 步1 13%、单调衰减到 0）不设经验松弛——ok=界内或末步前耗散完；fail=末步违反最大（扩散不可能终于其最大违反）或 BC 没落上 |
| `prescribed_displacement` | 非线性静力 | 零/非零判别：零值本质 BC 必须精确满足而自由场在动。docstring 写明 ok 只证"约束在 result_zero（Fem.f90:10798 组装用状态向量）里"——不是 fachv 那种显示副本 |
| `seismic_oscillation` VIE 扩展 | VIE 动力 | 从 1.man 读 `_d/_v` 声明（Fem.f90:8529），同一套反转计数。train10 9 次、train_vie_boundary 40 次 |

## G 否决的方向（负知识，同样留存）

`.act` 反力和（train09/contact 的盘上 1.act 是字节相同的外来陈旧文件，
且两 deck outfix=0——建在垃圾上的检查就是垃圾）；强读法的"规定值相等即
物理"（输出在规定 dof 处来自施加链）；无耗散条款的严格抛物包络（会把
合法离散下冲判 fail，任何固定松弛都是经验带）；应力基平衡/σ=DBu/屈服面
距离（节点外推平均全是容差问题且 σ 与 u 同路径，构造性）。

## H / I 的贡献（详见前两次提交）

train12 的 jfixvar 机械闭环（H=y+1 连 [-249,111] 都解释干净）转 READY；
train05b 修真 deck 错误（满强度 FoS≈0.6）后如实留 ✗；坏基准 2.24e5 重锚。
decoder 的 alloc 定尺寸通用修复清掉 ~80 处潜伏位，temp_creep 解码
286→2089 条，回读仍 21/21。

## 版本敏感性的新实锤（G）

`gamaw`：当前源码硬编码 9810（Global.f90:41）并丢弃 deck 的逐组 gamawx
（Prescrib.f90 的 `%gamaw=` 存储 20230402 被注释），但 train_seepage 的
归档结果按 deck 的 10000 精确闭合——它是 pre-20230402 语义的二进制算的。
**gamawx 列在当前源码下是活诱饵**（open #16 的又一实例）。

## 全程总账（本文档覆盖的两天）

| 指标 | 起点 | 终点 |
|---|---:|---:|
| 通过放行闸门 | 0/21 | **17/21** |
| 语义完全一致（回读） | 未度量 | **21/21** |
| deck 完整解码 | 11/21 | **21/21** |
| 单元测试 | 371 | **802** |
| 真实物理违反被修复 | — | 2（train12、train05b 的 deck 错误） |


---

# 附录 7：train_slope_unknown 诊断与退役（2026-08-31）

## 诊断：它就是 train05b 修复前的孪生 deck

调查其 `global_equilibrium` 违反，证据链完整闭合：

| | train_slope_unknown | train05b 修复前（归档） |
|---|---|---|
| 网格 | 451 节点，360×180 | 相同 |
| 材料 | `'MC', 4.2e4, 0.` + `17 17` → c=42 kPa, φ=ψ=17° | **逐字相同** |
| 折减曲线 | LINEAR 1.0→0.5（F=1→2） | 相同 |
| 末块 \|U\|max | **2.35e5 m** | 旧基准"归档参考"恰为 **2.35e5** |

**旧 slope_srm 基准引用的那次"归档运行"，deck 本尊一直躺在语料里**——
迁移时来历不明才叫 unknown，现在来历清楚了。

失衡轨迹与 train05b 的病一致：块 1（F=1.01）已失衡 12%、\|U\|max 41.8 m，
全程无收敛平台。坡在满强度时 FoS≈0.6，扫描从已坍塌状态开始，
没有任何有意义的状态。**闸门 fail 是正确判定。**

## 处置（使用者裁定：退役归档）

移入 `cases/cases/_retired/train_slope_unknown/`，附 RETIRED.md 墓碑
（身份证据、退役理由、历史价值）。原文件完整保留。修复无价值——
修好就是 train05b 的克隆；它的历史价值（证明旧基准参考值是坏 deck
输出被钉成真值）已由本文附录 5 与基准重锚记录在案。

注意：`.stignore` 白名单是 `train*`，退役目录以 `_` 开头不再同步
Windows——Office-Q 侧若有旧副本会保留为陈迹。

语料从 21 例变为 **20 例**；闸门 17/21 → **17/20**，
BLOCKED 剩 3 个：train02c_dbg（死 deck，待修或退役）、
train05b（真 SRM 签名）、train_temp_creep（GiD 二进制结果，须重算）。


---

# 附录 8：train02c_dbg 退役 + train_temp_creep 重算受阻（2026-08-31）

## train02c_dbg：退役（使用者裁定）

判据线程 G 的诊断成立：死 deck——三条驱动路径全为零（FIX、
`earthquake_curve=0 0`、无 VIE `_d/_v` 记录），响应为机器零（6.6e-16）。
"_dbg" 后缀表明是当年调试 train02c 系列的中间产物，正式算例
train02c_seismic_wave_compare 已 READY。移入 `_retired/`，附 RETIRED.md。

## train_temp_creep：重算被求解器真 bug 挡住——诚实报告，不硬闯

现存结果是 NTFS 来源的 gzip GiD 二进制（另一台机器、可能另一个二进制
所算），`1.chk` 为空。在 scratch 副本上重算，**当前 YL 二进制在
"Begin assemble golbal matrix" 处 SIGSEGV**——即备案已久的那个组装崩溃。
本次把包围圈收紧到无可再收：

| 假设 | 实验 | 结论 |
|---|---|---|
| PARDISO 特有 | 换 PROFILE（连 1.sol 格式一起换） | **同点崩溃**，排除 |
| NONSYM=1 + mtype 失配 | mtype 11；再 NONSYM=0 + mtype -2 | 同点崩溃，排除 |
| TRAL 插值节点（全语料唯一非空 1.nrt，63 节点） | 1.nrt 清零 | 同点崩溃，排除 |
| 1672 条对流边 | 1.tem 清空 | 同点崩溃，排除 |
| 热源曲线越界（HEAT 行 source_curve=3/place_curve=4） | 数曲线：.loa 声明 7 条 | 索引在界内，排除 |

剩余唯一嫌疑：**3D T 场单元（ikind=15）的核心矩阵组装**本身——
对照 train07（2D T 瞬态、同 PARDISO）正常求解。与既有结论互证：
3D 热在 YL 主线从无跑通记录（PRJ-4611 的 3D 稳态温度与 U+T 均在
HSTAR_Q 侧验证）。

**处置**：真实算例目录未动（所有实验在 /tmp scratch）。重算需要
Fortran 层调试 YL 的 3D 热组装，超出工具链范畴，**挂起**并留此
排除表——下一个接手的人从"只剩一个嫌疑"开始，而不是从零开始。
闸门对它的条件 4 阻塞保持如实（结果不可读 → unverified 不是通过）。

语料 20 → **19 个活跃算例**；闸门 **17/19**，BLOCKED 仅剩 2：
train05b（真 SRM 签名，等分类规则）、train_temp_creep（本附录）。


---

# 附录 9：MAT_DE 平衡规则过不变量审——train05b 过闸，18/19（2026-08-31）

## 不变量形式

线程 H 的建议是"MAT_DE 取最后收敛步判平衡"。过审后落成的形式更准确：

> **平衡是收敛态的不变量。**求解器自己报告未收敛的步，残差正是"未收敛"
> 的度量，拿它判平衡是范畴错误；SRM 扫描刻意驶过破坏点，末段本身是量测。
>
> fail  任一收敛到 deck 自身容差的步不平衡（解的不是所提的问题）
> fail  **全程没有任何一步平衡**（从坍塌态开始的扫描什么都没量到）
> pass  存在平衡台地；发散起点作为 SRM 量测报告，不判

第二条 fail 是防逃逸门：修复前的 train05b / train_slope_unknown
（全程失衡 1e-1~6e-1）恰好死在这条上。仅 type_load=MAT_DE 启用，
其余算例保持末步判定不变。

## 实施中被度量纠正了一次

第一版第二条写的是"无**收敛**步即 fail"——立刻误杀 train05_slope_stability：
它的塑性迭代从不满足 1e-5（残差 0.3~200，miter 打满），
但**每一步的全局合力闭合到 1e-9**。自平衡的残差力求和为零——
**全局平衡是比逐 dof 收敛弱得多（且此处被满足）的陈述**。
判别子改为**平衡轨迹**：修复前的坏 deck 是"没有任何一步平衡"，
这才是"从坍塌开始"的真实指纹。

train05b 实测：4 个严格收敛步全部闭合 5~9e-10；平衡台地到步 96；
发散起点步 87（F=1.77）作为量测报告。证伪测试六条，
含"收敛但不平衡→fail""全程不平衡→fail""不收敛但全平衡→pass（train05 形态）"。

## 最终闸门

```
18/19 READY
train_temp_creep  BLOCKED——等 YL 3D 热组装的 Fortran 修复（附录 8 排除表）
```

条件 6（知识落地）整列人工核定待做；其余机械条件全语料无 fail。


---

# 附录 10：终局与第二轮审计请求（2026-08-31）

## 自附录 6 以来的收官三步

1. **两例退役**（使用者裁定，各带 RETIRED.md 墓碑）：
   `train_slope_unknown`——诊断确认它就是 train05b 修复前的孪生 deck，
   旧 slope_srm 基准"归档参考 2.35e5"的本尊（附录 7）；
   `train02c_dbg`——死 deck，三条驱动路径全零、响应机器零。
2. **MAT_DE 平衡规则过不变量审**（附录 9）：平衡是收敛态的不变量 +
   平衡轨迹判别子。实施中被全量回归当场纠正一次——第一版"无收敛步即
   fail"误杀 train05（塑性迭代从不满足 1e-5 但每步全局合力闭合 1e-9：
   **自平衡残差力求和为零，全局平衡是比逐 dof 收敛弱的陈述**）。
3. **条件 6 人工核定**：33-knowledge-ledger.md 逐案记录"教了什么、
   落在哪"（四类合格去处），data/knowledge-ledger.json 供闸门读取——
   核定一次，闸门永久记住；未核定保持 manual，永不机械 fail。

## 终局数字

```
活跃语料      19 例（退役 2）
闸门          18/19 READY，六条全 ✓
              唯一 BLOCKED：train_temp_creep（YL 3D 热组装 SIGSEGV，
              附录 8 排除表；Fortran 层问题）
回读          语义无损（值差异 0 / 仅原始 0 / 仅生成 0）
解码          21×完整走完（含已退役者）
单元测试      371 → 810 全绿
```

## 请第二轮审计重点打这些（新增攻击面）

1. **条件 6 的账本机制是不是自我核准？**核定者与被核定工作同源
   （33 号账本由执行者本人填写）。请抽查 3-5 行账本：证据指针是否真实
   存在、"判据级落地"是否真的是判据而非文档句子。
2. **MAT_DE 规则的两个 fail 分支可否被绕过？**构造一个"每步都有一个
   平衡瞬间但物理已坍塌"的反例试试。`skills/test_skills.py` 的
   `srm_equilibrium_converged_states` 是现有防线。
3. **`prescribed_displacement` 撑起了 6 个算例的条件 4**——它的"ok 只证
   约束在 result_zero 里"是否被后续叙述悄悄放大成了更强的主张？
4. **退役是否成了处理不了就扔？**两例退役的证据链在附录 7/8 与各自
   RETIRED.md；请检验退役理由是否独立于"它们恰好难修"。
5. **B4 变异测试请重做**并加两处新目标：gate.py 的 MAT_DE 分支
   （把"NO balanced step"fail 改成 pass）、case_gate 条件 6
   （把 ledger 判定改成永真）。
6. 复现命令同 §10，另加：`python3 harness/case_gate.py`（现约 20 分钟，
   条件 3 活算）。


---

# 附录 11：第二轮审计(34 号)处置——闸门 18/19 回落到 14/19

Codex 第二轮抓到三条真实的错误放行路径,全部复现、全部封死,
其攻击本身全部转为回归测试:

| 发现 | 处置 |
|---|---|
| **F1(致命)**振荡判据方向盲:X 声明、X 单调、Y 人工振荡也报 ok | **已修**:只判声明方向的分量(fixed-base 按 earthquake_curve 槽位、VIE 按 _d/_v 槽位);声明的驱动曲线自身须振荡(≥2 次显著反转)才把单调响应判为矛盾——缓变驱动合法单调,审计警告的误杀关死;ok 措辞降为"与施加了驱动相一致(诊断)",**移出 FIRST_PRINCIPLES**。审计反例成为回归测试 |
| **F2(致命)**非集合检查的 fail 不拦截条件 4 | **已修**:`physics_condition` 统一否决——任何 fail(无论名字)与 run_validity=incomplete 先否决,之后才数正向;正向仍只认 FIRST_PRINCIPLES。抽出为可单测的纯函数并带测试 |
| **F3(致命)**live compare 抛异常后旧缓存放行 | **已修**:fail-closed——异常即条件 3 fail,缓存不再是闸门输入。审计的强制异常攻击成为回归测试(train01 注入坏 compare → BLOCKED) |
| **F4(重要)**preservation 与 authoring 混成一个 READY | **部分修**:条件 1 明示 preservation-grade 及 raw 携带清单("typed 编辑不达 deck");**三态 READY 拆分列为 P1,待使用者定架构** |
| **F5(重要)**cases 不在可复现版本链 | **挂起待使用者决策**:变 submodule/普通仓库/内容寻址数据集是基础设施选择(现行 Syncthing 传输);审计的哈希清单建议已记录 |
| **F6(重要)**条件 6 无测试、证据粗、永真变异不被抓 | **已修可修部分**:`knowledge_condition` 抽出+四条测试(vetted=false/缺证据文件/缺条目/坏 json→manual);账本逐案补 evidence_detail(具体函数/测试名);**不拦截是设计**——"什么算落地"正是被行使的判断,已在 docstring 言明 |
| **F7(次要)**MAT_DE 旧口径注释残留 | **已修**:测试 docstring 更新为平衡轨迹口径 |

审计对六个攻击面的其余裁定照单收下:MAT_DE 规则是 SRM 必要条件而非
稳定性充分证明(已如此表述);prescribed_displacement 是约束链检查而非
算例族特征 V&V(它的 6 个正向维持,但这条批评为下一批"族特征判据"立项);
两例退役理由被判独立于"难修"。

## 诚实的代价:18/19 → 14/19

四个动力算例(train02、train02c_swc、train10、train_vie_boundary)回落
BLOCKED——它们此前唯一的正向证据就是被降级的振荡诊断。**当前工具箱里
不存在从现有输出可判定的动力第一性正向判据**(能量平衡需 C、K,动力
平衡需 M 与阻尼项,均不在输出中)。要重新解锁,需要求解器侧输出
(能量/组装后的地震 RHS)或按审计 P0.4 的方向做,列为后续。

```
闸门   14/19(五条机械 + 账本核定)
测试   810 → 827 全绿(新增:统一否决、fail-closed、方向绑定反例、账本四态)
BLOCKED train02 / train02c_swc / train10 / train_vie_boundary(缺动力正向判据)
        train_temp_creep(YL 3D 热组装,附录 8)
```

**14 这个数字比 18 更值得信**——这正是两轮审计的全部意义。


---

# 附录 12：F5 处置——cases 纳入版本链(submodule,2026-08-31)

## 之前的状态(审计 F5 属实)

主仓把 `cases` 记录为 gitlink `e06c9b4e`,但无 `.gitmodules`、`cases/`
无 `.git`,该对象在任何对象库中都不存在——15 个 config、两次退役、
墓碑文件全部只活在本机目录里。

## 现在

- `cases/` 是真实 git 仓库:**4182 个文件入库**(输入 deck、config、
  网格、判据证据 1.chk/1.act、退役墓碑),首提交 `719b314`,
  当前 `41ca46e`。321M 内容压缩为 39M。
- **大文件策略**(既有政策 + 审计哈希要求的折衷):纯再生态
  (`1.flavia.res` 2.5G、`1.res` 300M、VTP 426M、`hstar.exe` 等)被
  `.gitignore` 排除,但**每个被排除文件的 sha256+size 记入
  `RESULTS-MANIFEST.tsv`(4684 行,已提交)**——结果哈希在链上,
  字节不在。
- 主仓 `.gitmodules` 登记 submodule,gitlink 指向 `41ca46e`
  (一个真实存在的对象)。
- 闸门输出新增 `data/gate-provenance.json`:每次运行盖章
  `cases_commit` + `code_commit`——审计"门禁产物携带哈希"要求的落地。
- 本地裸镜像 `/home/huijun/HSTAR_Next-cases.git` 作离机前的兜底副本。

## 已闭合(2026-08-31 更正:无需新建仓库)

使用者指出 gitea 主仓即在——submodule 指向**同一仓库的另一条孤立分支**
是合法形态。cases 历史已推为主仓的 `cases-corpus` 分支(fa4bb81),
`.gitmodules` 记同 URL + branch,gitlink 钉提交。

**递归克隆实测通过**:

```bash
git clone --depth 1 --recurse-submodules --shallow-submodules \
    https://gitea.hydrosim.cn/HSTAR/HSTAR_Next.git   # 328M,语料完整取回
```

注:`cases-corpus` 未推 github——语料含工程数据,是否公开是使用者的
外发决策,不由本轮代办。github 侧克隆需可达 gitea 才能取 submodule。


---

# 附录 13：F4 处置——三态 READY 拆分(P/A/V)+ raw 冲突防线(2026-08-31)

## 三态网格(按审计的表落地)

| 态 | 判定 | 当前 |
|---|---|---|
| **P** preservation | 条件 1 ∧ 条件 3(无损导入-再生) | **19/19** |
| **A** authoring | P ∧ 无不透明 raw 携带(mat_raw/contact_raw/nrt_raw/tem_raw/opr_raw/ftr_raw) | **6/19** |
| **V** verification | 条件 4 ∧ 条件 2 | **14/19** |

12 个算例是 `P · V`——**能无损保存、有物理证据,但材料等区域是 raw 携带,
typed 编辑到不了 deck**。这正是审计说被一个 READY 掩盖的事实,现在
逐案可见(闸门表新增 P A V 列,grades 进 case-gate.json)。

## raw 不再静默胜出

审计的第二个要求:"raw 与 typed 冲突必须拒绝/显式优先/冲突报告"。落地:

- import 对 raw/typed 并存的对(materials↔mat_raw、opr↔opr_raw、
  tem_pipe↔tem_raw)盖 `_raw_guard` 指纹(typed 侧的 sha256);
  15 个在盘 config 已补章(13 个有并存对)
- generate_all 入口校验:typed 被改而 raw 仍在 → **ValueError**,
  报文写明两条出路(删 raw 换语义作者权,或还原编辑)
- 测试 `raw_typed_conflict_guard` 三态:原样过 / 改 typed 报错 /
  删 raw 后 typed 编辑真实到达 1.mat(E=1.234E+04 实测落盘)

## Authoring 缺口从此是一张清单,不是一句含糊话

`grades.authoring_blockers` 逐案列出挡路的 raw 键。要把某算例推成 A,
路径明确:为该 raw 区域建 typed schema + 生成器出码(train06 的材料
常数即第一候选,29 号文档已有裁定与延期记录)。

830 测试全绿;闸门 14/19 不变(P/A/V 是并列坐标,不改 verdict 语义)。


---

# 附录 14:train06 材料常数 typed schema——A 列 6→7(2026-09-01)

## 两个发现让这件事比预想便宜

1. **生成器侧早就齐了**:`_gen_mat` 的 CONCRETE 分支本就按 `m["concrete"]`
   15 参出码(conc_A..irevert,与 deck 行逐位对应)——缺口只在 import 侧
   从不提取,于是导入的 config 带默认值、差异被 mat_raw 掩盖。
2. **挡 A 的一半是冗余**:train06 剥掉 mat_raw 后仍被 contact_raw/
   nrt_raw/tem_raw 挡住——查看内容,三者全是**生成器自己的默认桩**
   (这 deck 历史上被本管线重生成过)。携带自己的默认值只会锁死作者权。

## 落地

- `parse_mat`:CONCRETE 块提取损伤行(Material.f90:643 绑定 9 项
  A,B,C,D,Fc,Ct,Gf,h,icr;尾部 6 值为注记,一并携带以保逐位)
- **raw-drop 白名单**:全块类型 ∈ {ELASTIC, CONCRETE(含损伤行)} 且
  前导为标准形 → 不再携带 mat_raw。其余 deck 保守持有(拒绝优先)
- **默认桩等价剥离**:`_drop_default_raws` 按**绑定值等价**比对
  nrt/contact/tem 桩与生成器默认——等价即冗余即丢弃;7 个 config 顺带
  剥离。防漂移锁:新测试断言"新生成 deck 再导入必须零 raw 携带",
  两侧任一漂移即红
- 作者权实测:改 `concrete.fc=2.5e7` → `1.mat` 落 `2.500E+07`,
  再导入 typed 往返

## 数字

```
A 列   6 → 7(train06 达成 P A V)
回读   19/19 精确(含无 raw 的 train06 与 7 个剥桩 config)
闸门   14/19 不变;测试 830 → 842 全绿
```

剩余 P·V 算例的 A 缺口清单(grades.authoring_blockers):大头是
train09/contact/seepage 系的 mat_raw(GEOMETRY/WATER/CLASSICALEP 全参数
/HEAT 等块尚无 typed 表达)与 train_contact 的 contact_raw(非零接触段)。
每补一类 typed schema 解锁一批——模式已被本次验证。


---

# 附录 15:A 列推进——7 → 15/19(2026-09-01)

## 本轮新增 typed schema(每类都双侧落地 + 回读裁决)

| 类 | 关键点 | 解锁 |
|---|---|---|
| GEOMETRY | Material.f90:991 绑定 4 项(aera,J,Iy,Iz),parse 原只取 aera | train09 |
| SEEPAGE/WATER | typed 早齐;fmt_e **有损才加宽**修掉 bulkw 2044900e3→2.045E+09 的精度丢失 | train12、train_seepage |
| CLASSICALEP 全参 | criteria 参数化(原写死 MC)+ csigma0/cfrict/cdilan 三段链;MC/DP 准入 | train05b |
| HEAT(单相) | alfa(ndimn)+source/place/pipe+ialfa;**每条目单块**模式仅对导入形(带 heat 字典)生效,作者式 conductivity 条目保留旧成对发射 | train07 |
| 纯 ELASTIC 复裁 | train10/11 只是 config 早于白名单 | train10、train11 |
| 桩试剥-回读裁决 | 以回读判官逐键裁决非默认桩 | vie_boundary 等 7 例 |

## 过程中被防线抓住的三次

1. **UW 双相误放行**:白名单把 seepage_stress 的 nphase=2 块当纯 ELASTIC,
   typed 出码写 nphase=1——**回读当场抓住**(条件 3 fail),加"SOLID+FLUID
   同块即拒"守卫后复位。
2. **热管线回归**:每条目单块模式误伤作者式配置(求解器 exit 3)——
   既有管线测试抓住,改为只认导入形。
3. **陈旧 EXIT 假读**:等待循环匹配到旧文件里的标记,读了一张
   GEOMETRY 之前的过期闸门表;僵尸等待进程还把 pgrep 等待卡成死循环。
   教训:**长跑输出文件必须带时间戳并以 mtime 验新**。

## 终态

```
P 19/19   A 15/19   V 14/19    闸门 14/19    回读 19/19 精确    843 测试全绿
```

A 列剩 4 个,全部是**具名的真不可表达区**(宁拒绝纪律下的诚实边界):

| 算例 | 挡路者 | 性质 |
|---|---|---|
| train05 | CLASSICALEP=MCJOINT(ft/cft/sigmat/csigmat 追加行) | 待 MCJOINT schema |
| train_contact | 引号方言 CLASSICALEP×5 + **非零接触段**(contact_raw 是真内容) | 待接触段 schema |
| train_seepage_stress | UW 双相材料(nphase=2,SOLID+FLUID 同块) | 待双相 schema |
| train_temp_creep | 引号方言 HEAT + **真实 nrt/tem**(63 TRAL 节点、1672 对流边) | 待热边界段 schema |

这四类每一个都是一段新的 Fortran 读链——照本轮模式(读源码 → 双侧 typed
→ 白名单 → 回读裁决 → 防漂移测试)逐类补即可。
