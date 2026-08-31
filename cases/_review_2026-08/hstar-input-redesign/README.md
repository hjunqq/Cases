# HSTAR 输入体系：发现、更正与重新设计

> 2026-08-27/28。本文件夹是自足的，可以整包交给另一个 AI 或另一个人分析。
> 仓库：`/home/huijun/HSTAR_Next`，求解器源码：`hstarYLOrig/HSTAR/*.f90`。
> 历史前处理器源码：`_archive/hstarpre/sourcef90/*.f90`。

## 给分析者的说明（请先读这一段）

**本文件夹严格区分三类内容，不要混用：**

| 前缀 | 性质 | 可信度 |
|---|---|---|
| `0x-facts-*` | **事实**。全部带 `文件:行号`，可在源码中直接复核 | 由脚本从源码提取，非人工转述 |
| `0x-proposal-*` | **提案**。设计意见，未实现 | 可以推翻，请推翻 |
| `0x-open-*` | **未决**。需要跑实验才能判定 | 不要当成结论 |
| `data/*.json` | **机器可读的原始提取物** | 与 facts 同源 |

**特别请注意 `03-corrections.md`。**这份工作里已有五次结论被后续复核推翻；前四次中
两次是被自己的复核推翻的。那份更正清单本身就是最有价值的产物之一——它记录了哪些
看起来合理的推断实际上是错的，能让下一个分析者不必重走。

**⚠ 一条工具陷阱，会静默产出错误结论：**

> 求解器源码里有 **8 个文件不是 UTF-8**（GBK/iso-8859-1）：
> `Elements` `Load` `Material` `meshfine` `Output` `Prescrib` `Solver` `Temper`。
> 普通 `grep` 对它们**静默跳过**，什么也不报。
> 人工复核必须 `grep -a`，或先 `iconv -f GBK -t UTF-8`。
> 本项目的 AST 工具读的是字节（`errors="replace"`），不受影响——
> 所以会出现"工具说有、人 grep 说没有"的口径差，
> 而人会倾向相信自己的 grep。已有一次因此把活代码判成死代码
> （`22-facts-wt-mif.md` 的仪器 bug #3）。

> **同一个陷阱在算例侧更严重：`cases/cases/*/1.glb` 里 **31/89** 个对普通 `grep`
> 完全不可见**（ISO-8859 + CRLF 的 2011 年迁移老 deck，`grep` 按二进制处理，
> **静默零输出、退出码 1**）：
>
> ```
> $ grep -c NGROUP cases/cases/pile_beam/1.glb     # 无输出，exit 1
> $ grep -ac NGROUP cases/cases/pile_beam/1.glb    # 2
> ```
>
> box_culvert_3d damage dam_fluid_coupling dam_seepage_3d fix pile_beam rcbeam rcbeam_crack sluice_3d train_contact_nonlinear train_seepage train_seepage_stress train_slope_unknown train_vie_boundary tunnel tunnel_sl …
>
> **而且这不是巧合**：解析器静默丢掉的两个算例 `pile_beam` / `sluice_3d`
> 正是这批里的两个——同一批老 deck 既触发混合方言，又躲开人工复核。
> Python 侧 `errors="replace"` 照常读，所以**工具链看得见、人看不见**。
> 查这类算例时若用了普通 grep，得到的空结果会**确认** bug 而不是发现它。

**一条贯穿全部内容的判据：**

> 本系统的失败模式几乎全部是**语法合法、求解器接受、物理不对**。
> 因此"能跑通"不构成证据，"检查全绿"也不构成证据——本会话查实的两个 VIE 算例
> 都是全绿且边界残缺的。任何结论请追到源码行号或一次消融实验。

## 内容

```
01-facts-dispatcher.md      deck 由哪些 reader 消费、谁决定走哪个（含 .man 的 17 个 reader）
02-facts-semantic-drift.md  同一槽位在不同开关下语义漂移；VIE 双重激励的源码证据
03-corrections.md           ★ 被后续证据推翻的结论清单
03b-facts-roundtrip.md      往返能力矩阵：生成器是精确的，缺的是导入器
04-proposal-input-format.md ★ 现代化输入格式设计（本文件夹的主提案）
05-proposal-architecture.md 自我研究架构六层
06-open-questions.md        需实验判定的问题
07-facts-hstarpre.md        hstarpre 是历史 deck 编译器；真值分散在三处
08-revised-architecture.md  ★ 综合架构（纳入 hstarpre 后，取代 04/05 的部分结论）
09-facts-verification.md    对 07/08 的独立复核 + 复核中发现的两个活 bug
28-evidence-triage.md       ★★ 证据分诊：先判问题类型再调查，让"查一个问题"有边界
10-roadmap.md               ★ 整体规划：当前状态 + P0/P1/P2/P3
11-probe-report-man-readers.md ★ 第一个预先登记的自我研究闭环：答了 open #8，且探针自己错了三次
12-probe-report-old-loa.md  ★ 第二个探针：5 个 deck 确为旧格式(但在 .glb 不是 .LOA)；教训是「PASS 也可能是错的」
13-probe-report-old-format-peel.md ★ 第三个探针：.glb 旧格式差 4 条记录 14 字段，可机械迁移；标签行=记录版本戳
14-facts-deck-ast.md        ★ 输入 AST：整个 deck 读取逻辑的控制流树，5/5 验收；导出 1012 条 Deck ABI
15-probe-report-ast-mismatch.md 第四个探针（6/6 全过）：解析器闭合率修到 100%，.mat 子树曾被截断 10 倍
16-probe-report-bparameter.md ★ 第五个探针：Bparameter 只有 3 个谓词；发现 AST 只覆盖 6/15 个输入文件
17-case-research-loop.md    ★★ 算例研究循环：算例=ABI 树上的一条路径；六阶段 + 放行闸门 + 覆盖账本
18-decoder-report.md        ★ P0-1 交付：ABI 驱动的共享 decoder（只能不完整、不能出错）
19-probe-report-vie-ablation.md ★ VIE 双重激励消融（2/5）：成立，但源码论断漏了第二个守卫 force_process
20-facts-glb-dialects.md    .glb 头两种方言，改为按标签名对齐（open #7 已解决）
22-facts-wt-mif.md          ★ type_problem='WT'(冰雪冻融) 与 type_ABC='MIF'(多次透射边界) 的完整解剖
probe/                      三个探针的全部材料（predictions + sha256 + judge + verdict）
07-facts-hstarpre.md         hstarpre 的输入、模板依赖、生成路径与能力事实
08-revised-architecture.md   ★ 纳入 hstarpre 后的综合架构建议（后出，冲突时优先）

data/deck-readers.json      506 条 deck READ 语句，按文件×reader 归类
data/dispatcher-map.json    24 个 reader 调用点，含守卫与循环上下文
data/use-sites.json         13 个关键变量的消费点（槽位语义的唯一来源）
data/roundtrip-matrix.json  21 个算例的往返 diff
data/deck-ast.json/.txt     输入 AST（树 + 可读渲染，1203 条 READ）
data/deck-abi.json          Deck ABI：909 条（记录 × 路径条件）+ 开关清单

tools/extract_dispatch.py   生成 reader/dispatch/use-site 三个 json
tools/deck_ast.py           建输入 AST
tools/verify_ast.py         AST 的 5 项验收（必须全过）
tools/dispatch_table.py     从 AST 导出 Deck ABI
tools/case_path.py          给定开关解出算例的 Deck Path（守卫三值求值）
tools/coverage.py           覆盖账本（薄环境估计，已被 decode_all 取代）
tools/decoder.py            ★ ABI 驱动的共享 decoder
tools/decode_all.py         全量解码 + 真实覆盖率
tools/roundtrip_matrix.py   生成往返矩阵

examples/dam-vie.toml       新格式示例：100m 重力坝 VIE 动力时程
examples/dam-fix.toml       同一个坝，固定边界 + 基底加速度
examples/rc-bond.toml       钢筋混凝土粘结（当前工具链造不出来的那个算例）
```

## 一页背景：为什么会有这份东西

起因是一个具体失败：**钢筋混凝土损伤算例，在"基准套件里明明已经实现过"的情况下，
这次却造不出来。**

追下去发现基准套件 15 个算例里，8 个是 `legacy_deck`——人工写好的 deck 被**重放**，
生成器从未产出过它们。套件全绿测的是"求解器还能不能复现这些 deck"，
不是"工具链能不能造出这些 deck"。RC 能力住在文件里，不在工具链里。

再追下去发现更根本的问题：**deck 的填写规则，权威在求解器源码的 READ 语句里，
不在文档、也不在样例算例里。**而源码里的结构远比任何文档描述的复杂——
一个 deck 文件不是"一份格式"，而是被十几个 reader 子程序依次消费的一条流，
每个 reader 的记录布局不同，走哪个由 dispatcher 决定。

这就是 `01` 和 `02` 的内容，也是 `04` 那份格式设计的全部依据。

## 2026-08-28：纳入 hstarpre 后的阅读顺序

`_archive/hstarpre` 证明仓库里还存在一条历史生产路径：

```
.ctl + 网格 + 模板 model1/1.glb ──hstarpre──▶ HSTAR 求解文件
```

它不是单纯的文件拆分器，而是包含网格生成、几何选面、约束/荷载/接口导出、材料与施工阶段
处理的历史编译器。这一发现不推翻“现代输入应建立在 YL 求解器前面”的方向，但推翻了
“只研究求解器 reader 和 Python generator 就覆盖全部生产知识”的隐含前提。

建议新读者按 `01 → 02 → 03 → 07 → 08 → 06` 阅读。`04`/`05` 保留为第一版提案；
与 `08` 冲突时，以纳入 hstarpre 后的 `08` 为准。
