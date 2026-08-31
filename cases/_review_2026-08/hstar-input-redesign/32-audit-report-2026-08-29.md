# 对抗性审计报告 —— 2026-08-29

审计对象：`30-session-review-2026-08-29.md` 所述工作及其代码。

审计方法遵循 `31-audit-brief.md`：核查 git 与源码、复现单元测试与两个度量脚本、
执行三处隔离变异测试，并独立分析 `train06_concrete_damage`。审计过程中仅修改
`/tmp` 隔离副本，没有修改算例或求解器。

## 结论

这份工作只能判为**部分可信**：`627` 项测试、`2/21`、`157` 个值差异等表面数字
可以复现，但“六条闸门已经机械化”和“动力判据能抓住 PRJ-6057”不成立。
现有闸门可以让空配置或失效导入器继续显示 `READY`，存在错误结果被放行的路径。

## 已核实

| 主张 | 核实方式 | 结论 |
|---|---|---|
| 当前单元测试 | 运行 `python3 skills/test_skills.py`；允许测试建立仅本机的临时 HTTP 服务 | `627 passed / 0 failed` |
| 三处测试能否失败 | 在 `/tmp` 隔离副本变异后运行全量测试 | 模态阈值：`626/1`；动力 fail 分支：`626/1`；禁用 `parse_ftr`：`618/1`，三处均被捕获 |
| 当前闸门 | 运行 `python3 harness/case_gate.py` | 复现 `2/21 READY` |
| 当前语义回读 | 完整运行 `tools/semantic_roundtrip.py` | 复现 `2/21` 完全一致、`157` 个值不同 |
| 被省略的语义缺口 | 汇总本次新生成的 JSON | 另有 `489` 条仅原始记录；非注释语义不一致总量实际为 `157+489=646` |
| 513 → 157 | 读取 `e1aba42^` 和 HEAD 的 git 数据文件 | `value_diffs` 确为 `513→157`；若包含缺失记录，则为 `1039→646`，只下降约 38% |
| `.ifs` 头部死字段 | 阅读 `Stiff.f90:10413`、`:10457–10462` | 确实只读 `nabssgroup`；波速确实取材料 `props(matno)` |
| `nstepjq` 调用层守卫 | 阅读 `Fem.f90:1937–1939`、`:8470–8526` | `time_dependent` 确实被 `type_problem` 守卫，Q/E/W 不走该 reader |
| 模态量来源 | 阅读 `Fem.f90:10391–10395` | `omega` 来自逆迭代的 `lamda`，`mstar/kstar` 后续分别投影；不是直接用打印的 `k*/m*` 反算 |
| 文档落盘 | 检查 `ec4c656^..HEAD` 每个提交文件列表 | 没找到新的“声称改文档但无文档文件”实例；已承认的漏写最终在 `49e2379` 补入 |

## 发现的问题

严重度定义：致命 = 会让求解结果错误，或让错误结果通过闸门；重要 = 会让度量失真、
让进展被误判，或让后续决策基于错误前提；次要 = 可维护性或文档一致性问题。

| 严重度 | 位置 | 问题 | 我如何确认它是真的 | 后果 |
|---|---|---|---|---|
| 致命 | `harness/case_gate.py:86,127` | 条件 1 只检查“存在 config”，不检查槽位归属；条件 3 只读取缓存 JSON | 把 train01 的 `config.json` 换成 `{}`，未刷新缓存，仍得到 `READY` | 空配置也能被称为“槽位全部可归属” |
| 致命 | `harness/case_gate.py:127` | 回读不是放行时执行，缓存可以过期 | 禁用 `parse_ftr` 后 train04 仍 `READY`；运行语义回读后才变成 `BLOCKED`，显示 1 个值差异和 231 条缺失记录 | 当前生成器已经坏掉时，旧缓存仍可放行 |
| 致命 | `Output.f90:1472`、`Fem.f90:8682–8685` | `ground_motion_input` 不能证明地震进入 RHS | 绝对加速度由 `result_second+fachv` 直接构造，`fachv` 又直接来自输入曲线 | 即使主方程完全没施加地震，检查仍能恢复非零 `fachv` 并通过；“能抓 PRJ-6057”主张错误 |
| 致命 | `harness/case_gate.py:43`、`harness/gate.py:387` | 经验性的 `amplification_factor` 被列为第一性原理，并可给 `pass` | 当前 train10 和 train_vie_boundary 的条件 4 都仅靠它通过 | VIE 地面运动检查虽然 `skip`，仍获得空洞的“物理正向证据” |
| 重要 | `harness/case_gate.py:177` | 条件 6 固定为 `manual`，但 verdict 只排除 `fail` | 两个 READY 算例的第 6 条都是 `?` | “六条全部满足”实际是“五条无 fail，第六条未判断” |
| 重要 | `tools/semantic_roundtrip.py:181` | 69% 指标只统计值不同，未统计缺失记录 | 本次运行得到 157 个值差异、489 条仅原始记录 | 将“schema 相对 ABI 缺口”描述成 157 处明显低估剩余规模 |
| 重要 | `harness/mechanics.py:789` | 地面运动空间误差按所有时刻、所有分量的单一最大 operand 归一化 | 阅读 `operand=max(...)` 与最终单一比值实现 | 一个大分量可能掩盖另一小分量或小时刻中的真实非刚体差异 |
| 重要 | train06、`skills/import_glb.py:302` | concrete importer 只读取密度/E/ν，丢弃整行损伤参数 | 原始 `fc=17 MPa` 等参数被生成器默认值 `34.8 MPa` 等替代 | 这是会改变损伤演化的真实物理缺口，并非输出格式差异 |
| 次要 | `skills/test_skills.py:1395` | 测试硬编码原仓库路径 | 隔离变异时必须重定向路径，否则测试会加载未变异源码 | 测试不可直接迁移到 worktree/隔离副本 |

## 我无法判定的

- “0 → 2”中的初始 `0` 是代码出现前的历史陈述；git 中首次可执行结果已经是
  `1/21`，无法机械复现更早的零。
- 当前 `627` 已复现，但没有切换到旧提交重新运行“371”基线，因此只核实终值，
  没有独立核实增量。
- 没有直接运行求解器，因此无法判定现有 21 个结果文件本身是否对应当前 deck、
  二进制和求解器源码。
- `60cdcc6` 描述 train04 被重新生成并重算，但提交只包含 decoder 和结果 JSON，
  没有算例输入或求解日志改动；其求解过程缺乏可审计的提交级来源。
- 模态判据能验证特征值、向量和矩阵投影自洽，但不能单独证明模型材料、边界或
  矩阵组装代表了正确物理问题。

## 对 §7 七问的回答

### 1. 闸门的六条是否是对的六条？

不是正确实现的六条。条件 1 是“解码完成且有任意 config 文件”，不是 unknown
槽位归属；条件 6 没参与判定；条件 3 依赖可过期缓存。建议拆成“deck 理解度”、
“迁移可生成性”、“结果有效性”三条独立轴。

### 2. `unverified` 不算通过是否过严？

不过严。问题在于执行不一致：VIE 的地面运动是 `unverified`，随后却能由经验
放大系数取得第一性原理 `pass`。

### 3. 把 `text` 记录排除在数据差异之外是否漏掉结构错位？

同记录数下仅注释内容不同，可以不算求解语义差异。多写或少写一行会移动后续
READ，通常会表现为数据差异、解码停止或 `only_in_*`，不会仅成为 annotation
diff。但把所有名为 `text` 的读取都认定为永远无活性，尚缺全源码的变量活性证明。

### 4. 地面运动容差是否会掩盖真实违反？

会。当前按所有时刻、所有分量的全局最大 operand 归一化。应至少按“每个时刻、
每个分量”的 operand 尺度分别判断，再汇总；不能用全局最大响应保护所有较小分量。

### 5. `2/21` 是否代表真实进展？

不能解释成六闸门完成数。它最多说明五个自动项在当前缓存下无 `fail`。`157` 能表示
值差异进度，但总体语义缺口还包括 489 条缺失记录。

### 6. 三线程合并取舍是否正确？

代码层面有证据支持：`49724a0` 中 generator 确实保留了 nrfields 感知实现，
importer 同时保留 DOF、动力和 VIE 数据；相关变异测试会失败。但三个原始 worktree
的完整对照和求解结果没有留在可审计提交中，因此不能完全判定。

### 7. train06 为什么完全没动？

因为三个线程的目标都没有覆盖它的四类剩余差异：输出开关、混凝土损伤参数，
以及两个 `.pre` 块的 `nline 300→3`。其中混凝土 importer 丢弃专用参数，是此前
分类没有覆盖的一类物理 schema 缺口。

## 复现记录

基线命令：

```bash
cd /home/huijun/HSTAR_Next/fem-chat
python3 skills/test_skills.py
python3 harness/case_gate.py
python3 docs/research/hstar-input-redesign/tools/semantic_roundtrip.py
```

基线输出摘要：

```text
tests                       627 passed / 0 failed
case gate                   2 / 21 READY
semantic complete           2 / 21
value_diffs                 157
only_in_orig                489
only_in_gen                 0
non-annotation mismatches   646
```

变异测试均在 `/tmp` 的隔离副本完成；由于测试文件含绝对导入路径，副本中的该路径
被重定向到对应变异源码。三处变异及结果：

```text
modal_rayleigh_quotient: threshold 1e-3 → 1e9
  626 passed / 1 failed

ground_motion_input: non-uniform fail branch → ok
  626 passed / 1 failed

parse_ftr: always return sections=None
  618 passed / 1 failed
  （测试在首个 None 解引用处异常，后续断言未执行）
```
