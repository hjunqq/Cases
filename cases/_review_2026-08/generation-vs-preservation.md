# 生成能力 vs 保存能力 —— 往返矩阵与最佳实践

> 2026-08-27。起因：钢筋混凝土损伤算例在"基准里明明已经实现过"的情况下失败。
> 本文全部数值来自本次实跑，脚本 `roundtrip_matrix.py`，原始数据 `/tmp/claude-1000/roundtrip/matrix/matrix.json`。
> 相关：`vie-evaluation.md`、`rc-damage-kdt-log.md`、`capability-inventory.md`。

---

## 一句话结论

**基准套件全绿测的是"求解器还能不能复现这些 deck"，不是"工具链能不能造出这些 deck"。**
21 个 train 算例里只有 **7 个**有 `config.json`。剩下 14 个的能力只存在于人工 deck 文件里，
工具链从未生成过它们，也**无法**从它们身上学回来。

> **⚠ 本文 2026-08-27 第二版已更正第一版的数据。** 第一版的往返矩阵全表偏差被**我自己的
> 测量脚本 bug 放大**：`import_project` 返回 `{"config":…, "summary":…}` 包装层，
> 而我把整个包装层喂给了 `generate_all`。它不报错——每个键都落空，deck 按全默认值生成，
> 这与"schema 表达不了"在结果上完全无法区分。修正后重测，并据此修了导入器。
> 结论方向不变（生成器精确、导入器是缺的那一半），但**具体数字全部作废，以本版为准**。

---

## 一、为什么这次失败：那两个"成功的 RC 算例"从来没经过生成器

套件 15 个算例的执行模式（`suite.py:190-196` 按 `config.json` 是否存在分流）：

```
走生成器 (config 模式)  6 个: train01 / 02 / 03a / 03b / 04 / 12b
                             —— 全是重力坝静力·地震·模态、梁面荷载、渗流
直接重放人工 deck (legacy) 8 个: train05 / 05b / 06 / 07 / 09 / 10 / 11 / 12
                             —— 含 train06 混凝土损伤、train09 钢筋粘结
无 deck                  1 个: train07b_thermal_steady
```

`train06_concrete_damage`、`train09_rc_bond` 都是 **legacy_deck**。
"RC 能力"住在 deck 文件里，不在工具链里。**生成器从未产出过一个 RC deck。**

这次任务要求生成器产出只有人工 deck 里存在过的东西，于是它拿默认值填满了每一个
schema 里没有的字段——语法合法、求解器接受、物理不对。

---

## 二、往返矩阵：import → 重新生成 → 逐字段 diff

如果 Mode C（`import_glb` 导入既有 deck）能无损往返，第一节的问题就不成立——
拿人工 deck 导进来就能获得生成能力。

判据分两级，这个区分很重要：

- **OK** —— 归一化后逐 token 相同（`1.0e6` 与 `1000000` 视为相同）。
- **OK~** —— 文本不同但**求解器读到的值完全相同**。`10*0` 与 `0 0 0 0 0`、
  节点表每行 8 个与全写一行，Fortran 读起来一模一样。把这类记成"丢失"，
  只会让下一个人去追一个不存在的 bug。这一级用 `.pre`/`.LOA` 的语法解析器对比**结构**。
- **NL** —— 真实差异，N 为差异行数。

### 修复前（测量脚本 bug 已修正后的真实基线）

| case | 1.LOA | 1.pre |
|---|---|---|
| train01_gravdam_static | 46L | OK |
| train02_gravdam_seismic | 105L | OK |
| train02c_dbg / _seismic_wave_compare | 628L | 2L |
| train03a_modal_dry | OK | 3L |
| train03b_modal_ifs | OK | 7L |
| train04_beam_faceload | 46L | 7L |
| train05_slope_stability | 生成崩溃 | 生成崩溃 |
| train05b_slope_srm | 4L | 24L |
| train06_concrete_damage | 42L | 90L |
| train07_thermal_transient | 2L | 8L |
| train09_rc_bond | 6L | 40L |
| train10_dynamic_vie | 511L | 10L |
| train11_staged_foundation | 38L | 30L |
| train12_seepage_steady | OK | 6L |
| train_contact_nonlinear | 71L | 30L |
| train_seepage | 17L | 10L |
| train_seepage_stress | 92L | 30L |
| train_slope_unknown | 19L | 24L |
| train_temp_creep | 导入崩溃 | 导入崩溃 |
| train_vie_boundary | 3025L | 10L |

**`.LOA` 忠实 4/21，`.pre` 忠实 2/21。**

### 修复后

| case | 1.LOA | 1.pre |
|---|---|---|
| train01 / 02 / 02c×2 / 03a / 03b | OK | OK |
| train04_beam_faceload | OK~ | OK |
| train05_slope_stability | OK~ | OK~ |
| train05b_slope_srm | OK | OK~ |
| train06_concrete_damage | OK | OK~ |
| train07_thermal_transient | OK | OK~ |
| train09_rc_bond | OK~ | OK~ |
| train10_dynamic_vie | OK~ | OK~ |
| train11_staged_foundation | OK | OK~ |
| train12_seepage_steady | OK | OK |
| train_temp_creep | 无此文件 | OK~ |
| train_contact_nonlinear | 71L ⚠ | OK~ |
| train_seepage | 17L ⚠ | OK~ |
| train_seepage_stress | 92L ⚠ | OK~ |
| train_slope_unknown | 19L ⚠ | OK~ |
| train_vie_boundary | 3025L ⚠ | OK~ |

**`.pre` 忠实 21/21，`.LOA` 忠实 15/21。**
⚠ 那 5 个是被**显式拒绝**的第二种 `.LOA` 方言（见 §3.3），不是静默出错。

`.glb`/`.man`/`.mat` 仍有差异，那是下一批工作，不在本次范围。

---

## 三、修了什么

### 3.1 `.pre` 约束集：加 `boundary.fixsets` 直通

几何预设（`bottom_fix_uy` 之类）回答的是"把底面 y 向固定"，**表达不了任意节点集**。
人工 deck 不是用这些预设搭的，所以只能原样搬运。
`import_glb.parse_pre` 读出每条 prescribe 行（dof / 节点表 / 值 / 时间曲线 / jfixvar / f5），
生成器新增 `boundary.fixsets` 直通并按 dict 分支写回。导入器**只发 fixsets、不发预设**——
两者都发会让每个约束翻倍。

顺带修了两处：

- **`[]` 是真答案。**train10 声明 **0 个** prescribe 集。原来 `if fixsets:` 把空集当成"没读到"，
  于是退回预设，凭空造出约束。现在只有 `None` 才表示"这个文件什么也没说"。
- **VIE 的 `nbounods` 自由面表**（`Fem.f90:8546`）现在也随 deck 走。生成器原本总是按网格几何
  重新推导——那会把 deck 实际求解时用的边界悄悄换掉。

### 3.2 `.LOA` 边荷载：加 `edge_definitions` / `edge_loads` 直通

`water_pressure` 路径是从网格和水位**推导**边；来路不同的 deck（旧手工表、GiD 导出）
只能原样搬运。同时把 `time_curves`、重力向量、`time_curve_for_each_group` 一并读回——
边荷载行引用曲线号，缺了曲线整个文件对不上；而 train09 的 `tcg = [1,0,1,1]`
（第 2 组不施加重力）原来是丢的。

### 3.3 第二种 `.LOA` 方言：显式拒绝，不是静默默认

5 个算例（contact / seepage / seepage_stress / slope_unknown / vie_boundary）用
`'TIME CURVE in each BLKS'` 方言：**每个 BLKS 一份时间曲线表**。
config schema 只有一份全局 `time_curves`，**表达不了**。

原来的行为是解析失败→返回空→生成器拿默认值补齐→产出一个语法合法、求解器接受、
物理不同的 deck。现在导入器**报告拒绝**并说明原因。
这正是本文 §5 主张的"表达不了就拒绝"，先用在自己身上。

### 3.4 解析器本身：Fortran list-directed READ

前两版解析器（按行、按扁平 token）都是错的模型，都在真实 deck 上出过错：

| 错误模型 | 撞在哪 |
|---|---|
| 扁平 token 流 | READ 会**丢弃本记录剩余部分**。`1 36 1 10*0` 是完整的 8 项表头，多出的 5 个被丢弃（train06）；`Time_curve_for_each_group` 记录里有几个就是几个，按算出来的 ngroup 去读会一头撞进下一节的标签（train05b、train_slope_unknown） |
| 按行 | READ 会**跨记录**一直读到项数满足。train09 的 132 节点表跨 9 行，按行读只拿到第一行 |

`_Deck` 实现真正的 list-directed 语义，外加 `n*v` 展开、逗号分隔、`!` 尾注截断。

### 3.5 两个附带崩溃

- `generator._gen_glb`：`appear` 为**显式空列表**时 `appear[-1]` 越界，整个生成崩溃（train05）。
  空列表现在与"键不存在"同义。
- `.pre` 的逗号方言（train_temp_creep）。

---

## 四、这解释了本会话所有的静默缺陷

同一个形状反复出现：

| 事故 | 缺的字段 | 默认值给了什么 |
|---|---|---|
| RC 粘结失败 | `ikindks` / `nlocalbeam` / per-group `elem_index` | `ikindks=3`、单组 idx25 → 0 字节输出 |
| VIE 库水面全反射 | `nabsfgroup` | 0 → 上游截断面无吸收 |
| train02 地震质量矩阵 | `order_time` 第二位 | `[0,0]` → 动力算例按准静态求解 |
| train10 底边界混入竖直边 | `.ifs` 几何校验 | 无校验 → 模型内部凭空注入入射波 |

**机制**：模板是 deck 的有损压缩，压缩取舍围绕"当初有人想到要变的字段"。
没进 schema 的一律硬编码默认值，而默认值按常见情形选。
对稀有耦合（粘结、VIE、FSI），默认值必然是错的。

### 最刺人的一条

`capability-inventory.md` 第四轴「写死的旋钮」，**前一天就明确写了这条**：

> `ikindks` 仅由「有无 CONCRETE」二选一（3 或 0），其他取值（如 5=粘结）只能手改

**知识存在、写下来了、一天前写的——照样撞上去。因为它是一份清单，不是一条会失败的检查。**

---

## 五、最佳实践（按价值排序）

### P0 · 把往返矩阵变成常驻测试

本文第二节的脚本就是。它是**唯一诚实回答"工具链能表达哪些算例类型"**的手段，
成本极低（21 个算例几十秒）。它在任何 RC / VIE 工作开始之前就能告警"这个类型表达不了"。

判据：新增算例类型时，`import → 生成 → diff` 必须逐字段等价，否则记为显式能力缺口。

### P0 · 修导入器，这是投入产出比最高的一项 —— **已完成前两项**

生成器本身是精确的（train01 从人工 config 生成，六个文件逐字节等价；
其余 1~5 行差异经逐条核对，全部是本会话有意做的改动：
`gid_f`/`gid_v`/`gid_a` 输出开关、`order_time` 的 `0 2`、`earthquake_curve` 改水平向优先）。
缺的是导入器。剩余优先级：

| | 状态 |
|---|---|
| `.pre` 约束集 | ✅ 21/21（§3.1） |
| `.LOA` 边荷载 | ✅ 15/21，5 个显式拒绝（§3.2、§3.3） |
| 多材料 / 多组（`.mat`、`.glb` 的 NMATS/NGROUP/elem_index） | 待做，量最大 |
| 求解器与步长（PARDISO/PROFILE、`nincs`、LOAD n） | 待做 |
| 粘结字段（`ikindks` / `nlocalbeam` / `ftcrack`） | 待做 |
| 第二种 `.LOA` 方言（每 BLKS 一份时间曲线） | 需要 schema 改动，非解析器问题 |

### P0 · 套件判决必须区分"保存"与"生成"

`legacy_deck` 的 PASS 只说明"求解器还能复现这个 deck"，仅此而已。
现在 14/15 读起来像平台能力，这个误读直接导致了本次失败。
判决里加一维 `mode`，并对每个 legacy 算例记录其「生成孪生」的状态。

### P1 · 生成器遇到表达不了的东西必须拒绝，而不是填默认值

`type_ABC=VIE` 配 `nabssgroup=0` 应当**根本写不出来**；
有 index-25 组却 `ikindks≠5` 应当**根本写不出来**。
把"不能失败的检查不是检查"用在**写方**——今天的生成器对舒适区之外的一切是台静默出错机。

### P1 · COPY-FIRST 应是一等公民，但要靠能力矩阵决定何时用

KDT 这次赢在具体一点：它从 train09 整体复制，把四组拆分、`ikindks=5`、
`nlocalbeam=1` 原封带过来。但上一轮 VIE 时 COPY-FIRST 恰是它的**弱点**——
没有 VIE 样例，从加速度驱动的算例复制会固化错误。
**同一机制，有对口样例是优势，没有是陷阱。**能力矩阵正是判断"有没有对口样例"的依据。

### P2 · 让 config 自包含

`train03b` 依赖算例目录里不存在的 `gravdam_meta.json`。
config 应当能脱离生成时的临时状态独立重放。

### P2 · 补那三个字段

`ikindks` / `nlocalbeam` / per-group `elem_index` 透传。
能让 RC 算例跑通，但不做前面几条，下一个稀有耦合还会以同样方式失败。

---

## 附：复算与回归

```bash
python3 roundtrip_matrix.py                 # 全量往返矩阵
python3 roundtrip_matrix.py train09_rc_bond # 单例
```

输出 `matrix.json` 含每个文件的逐行差异样本与 `semantic_equal` 判定。

**回归状态**（本次改动后实跑）：

- `skills/test_skills.py` —— **329 项全过**（新增 3 项：`_Deck` 的 READ 语义、
  train01 的 `.pre`/`.LOA` 往返、拒绝不支持方言）
- 从人工 `config.json` 生成的路径 —— 与改动前**完全一致**，train01 仍逐字节等价
- `harness/suite.py --force` —— **PASS 13/15**

关于 13/15：与此前记录的 14/15 的差别是 `train10_dynamic_vie` 现在 FAIL，
**不是本次改动引起的**——`harness/_solve_deck.py` 走 legacy 路径，
既不 import 生成器也不 import 导入器。触发的是本会话早前加的 VIE 几何一致性检查：
30 条吸收边不在其声称的边界上、61 段边界无吸收边。
这两条正是 `vie-evaluation.md` 已独立查实的 train10 缺陷，检查在正常工作。
另一个非 PASS 是 `train07b_thermal_steady`（根本没有 deck）。
