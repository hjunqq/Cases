# P0-1 交付：ABI 驱动的共享 decoder

> 2026-08-28。工具 `tools/decoder.py`、`tools/decode_all.py`。
> 依赖 `data/deck-ast.json`（100% 闭合、5/5 验收）与 `tools/case_path.py` 的共享求值器。

## 0. 它是什么

**不是又一个手写读取器。**它走 AST，让求解器自己的 READ 语句决定读什么、读多少。

此前本项目每个读取器都是手写的，同一条 Fortran 文本规则（`!` 截断、
记录尾丢弃、`n*v` 展开）在**六个地方**各实现一次、各错一次。这是唯一的那一份。

### 设计性质

> **这个 decoder 只能不完整，不能出错。**

守卫或 arity 从已读到的值求不出来时，它**停下并报告确切位置**，绝不猜。
猜会让文件游标失步，而失步产生的是"看起来合理的错误答案"——本项目全部事故的形态。

### 反馈闭环

读到的值**绑回环境**，于是后续守卫与数组界随解码推进而变得可判定。
这正是 `17-case-research-loop.md` §4 指出的、真实覆盖率所必需的东西。

## 1. 实现中撞到的四个真实语义

每一个都不是工程细节，而是这套输入格式的固有性质：

**a · 同一条 READ 内的自反依赖**

```fortran
read(gunit,*) ftcrack, coefMpa, ikindks, doubsig, ktan1, ktan2,
              nlocalbeam, ndimnrt,
              listglocbeam(1:nlocalbeam), lelenrt(1:ndimnrt)
```

后面数组的长度由**同一条记录里刚读到的第 7、8 项**决定。整条 arity 预先求值做不到，
必须逐项读、逐项绑定。

**这就是 RC 粘结那条 `ftcrack` 行 8 字段 vs 9 字段的机制**——`nlocalbeam=1` 多出一项。
此前是靠比对人工 deck 猜出来的，现在是从源码推出来的。

**b · 数组界来自普通赋值，不是 READ**

`Global.f90:1122  nrfields = group(igroup)%nrfields`，下一行就用它做数组界。
AST 原本把所有赋值都剪掉了 —— 现在保留 `ASSIGN` 节点并求值。

**c · 派生类型分量**

`group(igroup)%nrfields` 需要按 `group%nrfields` 归一（去下标）。
这假设"读与用在同一轮循环内"，本项目的 reader 都满足；不满足时 decoder 会停，
不会用陈旧绑定——**停比错好**是贯穿的取舍。

**d · 老式语法**

`ground_inf/100==1`（整数除法当开关）、`jliqu.ne.0`（老式关系运算符）、
`trim(property)=='MECHANICAL'`（字符内建函数）。都已支持。

## 2. 声明式假设：越过"deck 决定不了"的变量

有些分支变量不来自 deck，而来自程序自身（重启簿记、内部计数器、未初始化的派生类型分量）。
对这些，decoder 既不能猜，也不能一律停死。折中是**显式声明的假设**
（`data/assumptions.json`）：

```json
{ "name": "igap0", "value": 0,
  "why": "Material.f90:397 的 READ 受 if(name=='CONTACT') 守卫；非接触材料时该分量
          从未被赋值，而 :401 仍从中取值、:402 据以分支。",
  "declaration": "Material.f90:132 —— 派生类型分量，无默认初值",
  "evidence": "求解器对所有非 CONTACT 材料都正常工作，说明实际为 0（编译器零初始化）。
               这是观察到的行为，不是语言保证。",
  "risk": "若某构建不做零初始化，此处为未定义行为。" }
```

**规则**：只有列在此文件里的名字才能越过 UNKNOWN；此后解出的记录一律标记
`assumed` 而非 `certain`。未列出的名字照旧停下——"只能不完整，不能出错"由此保持。

目前三条：`igap0`、`lblks`、`restart`，各有出处、证据与风险。

> **`igap0` 那条同时是一份求解器缺陷报告**：`Material.f90:402` 对一个可能从未被赋值的
> 派生类型分量做分支，而该分量（`:132`）没有默认初值。已记入 open #13。

## 3. 实测结果

```
case                            解码   读尽   停止原因
train10_dynamic_vie              144   2/6   do-while condition  L10419
train06_concrete_damage          138   3/6   do-while condition  L357
train09_rc_bond                  134   3/6   do-while condition  L357
train03a_modal_dry               132   3/6   do-while condition  L357
train01_gravdam_static           123   3/6   do-while condition  L357
train05_slope_stability           59   0/6   arity  Global.f90:1129
train_contact_nonlinear           39   0/6   arity  Global.f90:989
…（共 21 个）

Deck ABI 记录位置 424 个，确定覆盖 112 个 (26.4%)
   .glb  77/126  61.1%    .ifs  8/21  38.1%    .loa  9/52  17.3%
   .mat  18/114  15.8%    .man  0/86   0.0%    .pre  0/25   0.0%

停止原因：10 × do-while 条件   8 × arity   3 × 循环界
```

**12 个算例完整消费了 6 个 deck 文件中的 3 个**（`.glb` / `.ifs` / `.mat` 全部读到 EOF）。

**正确性抽查**（train01）：`npoin=1705 nelem=1600 ndimn=2 nmats=2 ngroup=2 nblks=2
type_problem=Q type_solver=PROFILE type_abc=FIX mdofn=2`，
`matno_process = 1 2`（两块各一次）、`order_time_mdofn = 0 0` —— 全部与 deck 一致。
`.glb` 恰好 80/80 行、`.mat` 27/27、`.ifs` 8/8 —— **一字不多、一字不少**。

## 3b. 过程中修掉的三个真 bug

**a · 缺 `RETURN` 节点。**`Global.f90:3333 if (ngaps==0) return` 之后，解码器继续往下读，
把下一段的标签 `nwcpipe` 当数据吞掉。**早退是读取协议的一部分，不是控制流噪声。**
（发现方式很能说明问题：decoder 读到 EOF 后仍要求更多，用"数值记录里混入非数值 token"
一扫就定位到了。**它自己把自己的错误暴露了出来。**）

**b · `RETURN` 分支被剪枝剪掉。**我的 SEQ 保留规则把"只含 RETURN 的分支"当成空的——
而那恰恰是最必须保留的，因为它改变后续读什么。

**c · 复合守卫从不拆分。**`_split_top` 的括号深度从上一个"分割点"而非上一个"匹配点"
累加，前缀被反复计数，导致 `(A.and.B).and.C` 永远拆不开。
**所有带括号的复合守卫因此一律不可判定。**修掉后 `.loa` 才第一次开始解码。

## 4. 边界（诚实）## 4. 边界（诚实）

1. **仍停在"由程序计算而非 deck 决定"的变量上。**现在集中在两类：
   `do while(tedge<nedge)` 这样的内部计数器（10 个算例），以及旧格式 deck 的
   `ftcrack` / `nrfields`（8 个）。要越过前者，需把数据流分析从简单赋值
   扩展到循环内累加。这是清晰的下一步，不是墙。
2. **派生类型分量按"最近读到的元素"绑定**（见 §1c）。不满足时会停而不是错。
3. **只覆盖 6 个主 deck 文件**；另有 9 个输入文件未建模（open #12）。
4. **`/` 按 floor 除法求值**。Fortran 向零截断，二者在非负值上一致；
   这些开关都是非负的，但这是一条假设。

## 5. 它现在能支撑什么

按 `10-roadmap.md`，P0-1 是三件事共用的枢纽，现在这三件都有了地基：

| 用途 | 现状 |
|---|---|
| 回读比对（阶段 3） | decoder 输出的记录流即 read-back IR，可与 Case Path 逐条比对 |
| ABI 驱动的校验 | 生成的 deck 用同一个 decoder 解码，对不上就是 writer 错了 |
| 覆盖账本（阶段 5） | 26.4% 是真实分子，随停止点前移而增长（本次已从 21.5% → 26.4%，`.loa`/`.ifs` 首次非零） |

而且它**替换掉了六份手写读取逻辑中的一份**——`import_glb._Deck` 之外的那五份
（两个 probe judge、往返矩阵、`parse_pre`/`parse_loa`）都应逐步改为调用它。

## 6. 复算

```bash
python3 tools/decoder.py --case train01_gravdam_static
python3 tools/decoder.py --case train09_rc_bond --deck .glb --values
python3 tools/decode_all.py        # 全部 21 个算例 + 真实覆盖率
```

---

## 7. 后续：文本层已合并为一份（2026-08-28）

**改了什么**：把 Fortran 文本层从 `import_glb._Deck` 提取为
`fem-chat/skills/deck_text.py`，生产侧的 `import_glb` 与研究侧的
`tools/decoder.py` 现在导入同一份。

**为什么是这个范围，而不是"用 decoder 替换 import_glb 的解析器"**：

咬过我们六次的**不是语法解析器，是文本层**：

```
import_glb._Deck._expand            对
probe/man-readers/judge.py          忘了 !
probe/old-format-peel names()       忘了 !
probe/old-format-peel key()         忘了 ! 与尾空格
probe/bparameter/judge.py           grep 原始行，! 又一次
tools/decoder.Cursor                第二份平行实现
```

而语法层不能现在替换：**decoder 目前解不到 `.pre`（覆盖 0%），
而 `import_glb.parse_pre` 是 21/21 忠实往返。**整体替换会是回归。
等 decoder 的停止点推进到 `.pre`/`.man`，再逐个把 `parse_*` 换成 ABI 驱动，
并用往返矩阵做验收。

**落成检查而非散文**：`test_skills.py` 新增
`test_deck_text_is_single_implementation`，钉住三条规则
（跨记录读、记录尾丢弃、`n*v` 展开与 `!` 截断），
并断言 `import_glb._Deck is deck_text.Deck` 且源码里不再有第二个 `class _Deck`。
**再出现一份拷贝，测试会失败。**

**回归**：单测 337 全过（新增 8 项）；往返矩阵与改动前逐格相同；
decoder 全量数字不变（26.4%，`.glb` 61.1% / `.ifs` 38.1% / `.loa` 17.3%）。

四个探针 judge 里的旧拷贝没有改动——它们是已归档的实验材料，
改写会破坏"预先登记 + 可复算"的性质。新写的判定脚本应导入 `deck_text`。
