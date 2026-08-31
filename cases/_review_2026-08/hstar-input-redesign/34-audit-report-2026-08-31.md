# 第二轮对抗性审计报告 —— 2026-08-31

审计对象：`30-session-review-2026-08-29.md` 附录 3–10 所述工作，以及
`2ec312a..15eed98` 期间形成的解码器、语义往返、物理判据、case gate 和知识账本。

审计方式：核查 git 与实现源码；读取 `case-gate.json`、`semantic-roundtrip.json`；
运行全量单元测试；在 `/tmp` 隔离副本执行两处指定变异；强制 live compare 抛异常；
并为 `seismic_oscillation` 构造跨方向反例。没有修改求解器或算例。

## 结论

本轮工作只能判为**部分可信**。`18/19 READY` 和回读 `0/0/0` 可以从现有产物
复核，MAT_DE 的关键 fail 分支也有有效变异测试；但门禁仍有三条错误放行路径：

1. `seismic_oscillation` 不按声明方向判断，且把“任意振荡”放大成“声明激励进入方程”；
2. `ground_motion_input` 的 fail 实际不参与 case-gate verdict；
3. live compare 抛异常后仍可用旧缓存得到 READY。

因此当前 `READY` 不能作为 CAE 工具链的发布准入结论。

## 已核实

| 主张 | 核实方式 | 结论 |
|---|---|---|
| 当前门禁产物 | 汇总 `data/case-gate.json` | `18/19 READY`；唯一 BLOCKED 为 `train_temp_creep` |
| 当前回读产物 | 汇总 `data/semantic-roundtrip.json` | 21 个算例 `value_diffs=0 / only_in_orig=0 / only_in_gen=0`；另有 201 条 annotation 差异 |
| 单元测试 | 运行 `python3 skills/test_skills.py` | 本沙箱 `795 passed / 1 failed`；失败为本地 HTTP 监听权限。该异常发生在 15 个后续断言之前，故允许监听的环境中 `810` 总数可以解释 |
| MAT_DE 变异 | `/tmp` 中把 “NO balanced step” 从 fail 改为 pass，运行定向测试 | `7 passed / 1 failed`，变异被捕获 |
| 条件 6 变异 | `/tmp` 中把 ledger 判定改为永真，运行全量测试 | 输出与基线相同；没有测试覆盖 ledger 行为 |
| live compare 异常路径 | 强制 `semantic_roundtrip.compare()` 抛 `RuntimeError`，评价 train04 | 条件 3 仍从 CACHE 得到 pass，最终 `READY` |
| 地震方向反例 | 声明 X 向激励；X 响应单调，仅 Y 向振荡 | `seismic_oscillation` 返回 `ok`，声称激励已进入运动方程 |
| 两例退役理由 | 检查附录 7/8 与两个 `RETIRED.md` | 物理理由独立于“难修”：一个是坏 SRM deck 的重复副本，一个是无驱动的死 deck；但归档没有进入可复现版本链 |

全量 live `case_gate.py` 会逐案执行语义回读，文档预计约 20 分钟；本次运行因耗时中止。
因此上表中的 `18/19` 明确是对已提交产物的核对，不冒充一次完整 live 复算。

## 发现的问题

### F1　致命：`seismic_oscillation` 不是所声称的第一性原理不变量

位置：`harness/mechanics.py:1505–1606`。

实现对 crest-minus-base 的**所有分量**分别统计方向反转，然后取最大反转数：

```python
best = 0
for c in range(ncomp):
    ...
    best = max(best, reversals)
if best >= 2:
    status = "ok"
```

它没有把被检查分量与 `earthquake_curve` 声明的方向对应，也没有验证振荡与输入之间
的因果或时序关系。审计反例中，X 向激励声明存在、X 向响应严格单调，只有 Y 向
人为振荡，检查仍报告：

```text
status=ok
11 significant direction reversals
the declared drive entered the equations of motion
```

此外，“非零瞬态基底激励必然在有限观测窗内出现至少两次显著反转”本身并非普适
不变量。低频缓变输入、短观测窗、强阻尼响应都可能合法地单调；而其他荷载、初始
振动或正交分量也可能制造反转。`2% signal range` 和“至少两次”都是经验分类器，
不是动力学守恒律。

**后果**：未进入声明方向 RHS 的地震工况可以通过条件 4；合法的缓变动力工况也可能
被误杀。该检查最多只能作为 PRJ-6057 的症状诊断，不能独立充当发布门禁。

### F2　致命：`ground_motion_input` 的 fail 不会阻塞 case gate

位置：`harness/case_gate.py:43–69, 197–219, 248–251`。

注释声称 `ground_motion_input` 的 ok 不提供正向证据，但 fail 会经 `run_validity`
阻塞。实现却只从 `FIRST_PRINCIPLES` 集合筛选失败项，而该集合明确不含
`ground_motion_input`：

```python
fp = [c for c in v.get("checks", [])
      if c["check"].split("[")[0] in FIRST_PRINCIPLES]
failed = [c for c in fp if c["status"] == "fail"]
```

`out["run_validity"]` 仅被记录，最终 verdict 不检查它是否为 `incomplete`。
所以只要 F1 的振荡判据给出 positive，方向映射或输入链即使明确 fail，条件 4 仍可 pass。

**后果**：一个已知错误的地震输入链可以被另一条弱判据覆盖，错误结果通过总门禁。

### F3　致命：实时回读仍可被旧缓存替代

位置：`harness/case_gate.py:154–195`。

条件 3 已改为优先执行 live compare，但 `except Exception` 后仍读取
`semantic-roundtrip.json`。审计中强制 live compare 抛异常，train04 得到：

```text
('pass', '436 bound records identical')
condition 3 from CACHE (live compare failed: RuntimeError: forced live failure)
READY
```

这与上一轮审计指出的故障类别相同：当前 importer、generator 或 decoder 已坏，昨日
缓存仍可放行。缓存没有绑定代码 SHA、配置哈希、原始 deck 哈希、ABI 哈希或工具版本。

**后果**：门禁基础设施本身失败时，系统不是 fail-closed，而是静默采用历史结论。

### F4　重要：回读无损主要证明 preservation，不证明 authoring 完成

位置：`skills/generator.py:590–627`、`skills/import_glb.py:1927–1965`、
`harness/case_gate.py:106–133`。

19 个活跃算例中，15 个 config 含 `glb_rows`、`mat_raw`、`contact_raw`、
`nrt_raw`、`tem_raw` 等 opaque/verbatim 携带字段。尤其 `mat_raw` 存在时完全覆盖
typed `materials` writer：

```python
if mat_raw:
    ...
    return "\n".join(out)
```

因此 `0/0/0` 可以支持“导入后原样保存”，但不能支持以下更强主张：

- typed Semantic IR 已能表达这些物理；
- 使用者修改 typed `materials` 后会作用于求解 deck；
- 每个 Deck ABI 槽位已有字段或明确派生规则。

条件 1 目前只检查 config 中 `type_problem/groups/materials` 三项非空，就报告
`walked, config-attributable`，没有生成逐槽位归属清单。

**后果**：保存能力和编辑能力被压成同一个 READY。对 imported config 修改 typed 字段时，
raw 区可能静默胜出，形成“界面上改了、求解 deck 没改”的 CAE 高风险行为。

### F5　重要：算例状态没有进入可复现版本链

根仓库把 `cases` 记录为 gitlink：

```text
160000 commit e06c9b4e4654f895b69c5764cc4d01d636d49fb1 cases
```

但当前仓库没有 `.gitmodules`，本地 `cases/` 也没有自己的 `.git`，上述对象在当前对象库
中不存在。`8f1344a` 声称落盘的 15 个 `config.json`、两次退役及两个 `RETIRED.md`
均没有出现在对应提交的文件列表中。

退役判断本身有证据：

- `train_slope_unknown` 是修复前 train05b 的坏 deck 孪生体，满强度即失衡；
- `train02c_dbg` 三条驱动路径全零，响应为机器零。

但这些算例、config 和墓碑目前只存在于本机目录。重新 clone 或换一台机器，无法按提交
恢复门禁所使用的语料状态。

**后果**：`18/19`、`0/0/0` 和退役后的 19 例口径不是可复现构建产物。

### F6　重要：条件 6 既不阻塞，也没有测试

位置：`harness/case_gate.py:226–278`、`data/knowledge-ledger.json`、
`33-knowledge-ledger.md`。

未核定算例被标为 `manual`，最终 verdict 只收集 `fail`。因此将来一个未核定算例只要
前五项通过，仍会 READY。“六条全 ✓”只是当前 18 个 READY 算例的快照，不是 gate 的
行为保证。

知识账本的机器镜像也只为每例保存相同的宽泛指针：

```json
{"vetted": true, "date": "2026-08-31", "evidence": "33-knowledge-ledger.md"}
```

它没有逐项证据 ID、代码符号、测试名及可验证路径。将 ledger 分支变异成永真后，
全量测试输出完全不变，证明这条机制目前没有回归防线。

**后果**：条件 6 是人工说明栏，不是 release gate；由同一执行者填写和核准时还存在
自我核准风险。

### F7　次要：MAT_DE 文档和实现注释存在旧口径残留

定向变异证明 MAT_DE 的“无平衡步”fail 分支有测试保护，现实现按**平衡轨迹**而不是
“是否有收敛步”判别，方向合理。但 `gate.py` 和测试 docstring 仍有“NO converged step
anywhere”旧描述，而后续正文与实际代码允许“塑性迭代未满足 deck tolerance、但全局
平衡轨迹成立”的情况。

**后果**：后续维护者可能按旧注释重新引入曾经误杀 train05 的规则。

## 对第二轮六个攻击面的回答

### 1. 条件 6 是否自我核准？

是。抽查的账本条目大多能找到对应函数或测试，但机器账本只指向整个 33 号文档，
没有逐条可验证证据；核定者与实现者同源，且永真变异不被测试捕获。

### 2. MAT_DE fail 分支能否被简单绕过？

指定变异会被测试捕获，因此简单把 “NO balanced step” 改成 pass 不能静默混过。
但目前规则仍只判断全局合力轨迹；“局部已形成机构而全局合力偶然闭合”不是该指标能
排除的情形。它应被描述为 SRM 必要条件，不是充分的稳定性证明。

### 3. `prescribed_displacement` 是否被放大？

代码 docstring 对能力边界写得较诚实：ok 只证明声明的零位移约束出现在求解状态向量，
不证明材料、荷载和其余方程正确。但 case gate 把它作为足以撑起条件 4 的 positive，
使六个算例即使没有针对各自特质的物理判据也可 READY。它适合作为约束链检查，不能
替代算例族的特征性 V&V。

### 4. 退役是否成为垃圾桶？

本次两例的退役理由不是“难修”：一个无独立信息且复制坏基准，一个没有任何激励。
判断可接受。问题是归档没有进入可恢复的版本库，`RETIRED.md` 也只是本机文件。

### 5. 两处新增变异测试结果？

- MAT_DE 变异：被捕获；
- ledger 永真变异：未被捕获。

### 6. 基线数字是否复现？

提交产物中的 `18/19` 和回读 `0/0/0` 已复核。单测在当前沙箱为 `795/1`，缺失的
15 个 pass 可由 HTTP 测试在建立本地监听前异常、导致后续 15 个断言未运行解释。
全量 live gate 本次未完成，不能把缓存值称作 live 复现。

## CAE 架构建议

### P0：先封死错误放行

1. live compare 任何异常都必须让条件 3 fail；缓存只能用于 UI 展示。
2. 条件 4 首先执行统一否决规则：`run_validity == incomplete` 或任一 applicable check
   为 fail，立即阻塞；之后才判断是否存在 positive evidence。
3. `seismic_oscillation` 降级为 diagnostic/degraded，不再独立提供 positive。
4. 地震验证至少绑定声明方向；更可靠的目标是检查组装后的地震 RHS、输入功，或动力
   平衡 `M·a + C·v + K·u − f = 0`，而不是仅看输出波形是否“像振动”。

### P1：拆开三个 READY

建议分别维护：

| 状态 | 回答的问题 |
|---|---|
| preservation-ready | 旧 deck 能否无损导入、保存、再生 |
| authoring-ready | typed Semantic IR 能否表达和安全修改该算例 |
| verification-ready | 求解结果是否有针对该物理类别的验证证据 |

raw/verbatim 字段只能满足第一类。若 raw 与 typed 字段同时存在且覆盖同一 deck 区域，
必须拒绝、显式选择优先级，或生成冲突报告，不能静默由 raw 获胜。

### P1：修复语料版本治理

把 `cases` 变成真实可获取的 submodule、普通仓库内容，或内容寻址的数据集；提交中必须
记录算例数据版本、config 版本和结果版本。门禁产物应携带：

- solver binary/source hash；
- importer/generator/decoder hash；
- Deck ABI hash；
- 原始 deck 与 config hash；
- 结果文件 hash。

### P1：补 case-gate 自身测试

至少增加以下反例：

1. live compare 抛异常时必须 BLOCKED；
2. `ground_motion_input=fail` 且其他 positive 时仍必须 BLOCKED；
3. 声明 X 激励、仅 Y 振荡不得通过；
4. ledger 缺项、`vetted=false`、证据文件不存在；
5. raw 与 typed 字段冲突时拒绝生成；
6. 缓存哈希与当前代码或 deck 不一致时拒绝使用。

## 最终判断

本轮解决了大量“旧 deck 能否被完整保存”的工程问题，也让若干物理检查进入代码；但
当前终局数字把 preservation、authoring 和 verification 混成一个 READY。只要上述三条
错误放行路径仍存在，`18/19 READY` 就不能解释为“18 个算例已经具备可发布的输入与
验证能力”。
