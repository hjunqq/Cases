# KISS / KDT 使用报告 · v2

> 2026-08-26。**v2 推翻了 v1 的核心结论。**
> v1（同日上午）写的是"KDT 本体在 HSTAR 上跑不起来"。当天下午两路 agent 在本机真跑之后，
> 这句是错的：多 agent 版 **GATE PASS**，唯一实质改动是把默认超时从 3600 改到 9000。
> 详细过程见同目录 `kdt-run-report.md`(816 行) / `kdt-single-report.md`(817 行) /
> `kdt-trial.md`(933 行) / `kiss-format-trial.md`(380 行)。
> KDT 目前私有、无 license 且含未发表论文材料；本仓库作者是其合作开发者之一，已确认可发布。

---

## 一句话结论

**KISS 的包格式只值得取三样；KDT 能跑，而且它自动生成的知识在两处比我们人工维护的文档更准 ——
但它的裁判有三个空洞，"过了 gate"不等于"内容对"。**

---

## 一、v1 错在哪里

| v1 的说法 | 实测 | 错因 |
|---|---|---|
| "orchestrator 不可能跑" | 多 agent 版 **485 秒 GATE PASS** | 只看了 553 KB 单文件与硬编码路径，没试最小可跑路径 |
| "需要 LLM 后端，本机没有" | **`claude` CLI 2.1.243 一直装着** —— 它的 builder 就是这个 | 想当然以为要 API key/SDK；它是起子进程 |
| "跑不了完整 dissect" | KDT-single 50 分钟出完整包；multi 版过 gate | 真实门槛是 5 个外部件缺失 + 默认超时太短，不是不可能 |

**教训**：判定"跑不起来"之前必须先试绕过方案。v1 是读源码读出来的结论，不是跑出来的。

---

## 二、KDT 实跑结果

| | multi (`lzwei196/KDT`) | single (`KDT-single`) |
|---|---|---|
| 耗时 | 485 s（第二轮） | 50 min |
| 裁决 | **`gate: pass`，零 failure** | `ki_incomplete`，8 条 |
| 上游改动 | **仅 `spawn_cli_agent` 超时 3600→9000** | 无（另补 40 行域模板） |
| 额外工作 | 补写 3 个缺失的投影器（真实缺口，生成器在其服务器上） | — |
| 产出 | SKILL.md 584 行 · 33 triplets · 20 tools · 13 docs · dag.yaml 35 KB | SKILL.md 509 行 · 32 triplets |

KDT-single 那 8 条 failure 按性质拆开才有意义：**4 条环境缺件 / 2 条裁判误判 / 2 条产物真实缺陷**。
不拆就会把环境问题记成质量问题。

三个包（含我们手搭的对照组）已同步到 Windows 的 `_review_2026-08/ki-packages/`，可人工核对。

---

## 三、生成内容的质量 —— 抽查 5 项，0 项虚构

这是最该担心的一点：自动生成的知识若是幻觉，过了 gate 也没价值。结果反过来了。

**两处比我们自己的文档更准：**

1. **`type_problem` 有 5 类，不是 4 类。**
   KI 写 `Q 静力 / S 时变 / F 动力 / E 反应谱 / W 纯模态`。
   我们标着"human-confirmed · highest priority"的 `CLAUDE.md` 只有 4 类、把模态记作 `E`。
   源码 `Fem.f90:1933-1944` 站在 KI 这边：`E → response_spectrum`，`W → frequency_analysis`。
   我们用 `E` 跑模态能work（反应谱内部也做特征值提取），但严格讲 `W` 才是纯模态，
   而我们**完全不知道有这条路径**。

2. **5 个输出扩展名我们的术语表一个都没收录**：`.opw` / `.dis` / `.oew` / `.oit` / `.oip`，
   逐个回源码验证**全部真实存在**。

其余抽查（`dt_001` 运行方式逐字属实、`dt_011` 热扩散率 0.0864 m²/day = 1.0e-6 m²/s 物理与算术皆对、
单位表每行标 "verified from" 且全对）也无虚构。32 条 triplet 里 14 条标 `severity: silent`，
全部带可执行的 detection 命令。

**它的盲区，边界很清楚：**漏掉的全是"从算例和失败史里长出来的知识" ——
`ifixvar=8` 必须同时写 `jfixvar=ndimn`、重力坝 group1 必须是地基、
VIE 用 `earthquake_curve_d/_v` 而非 `earthquake_curve`、`earthquake_curve` 的槽位=方向。
agent 只拿到源码树，拿不到 `cases/cases/train*` 和几个月的 workflow 失败记录。
**从源码能读出"代码怎么运行"，读不出"哪些配置组合会静默出错"。**这是方法边界，不是实现缺陷。

---

## 四、裁判的三个空洞（"过 gate" ≠ "内容对"）

| # | 空洞 | 证据 | 修法 |
|---|---|---|---|
| 1 | `docs/gathered_papers.json` 的 `text_path` **一条都不验** | multi 版登记 16 篇论文、每篇声明路径，**磁盘上一条都不存在**。规格 FILE 9 明文要求 `test -f`，还写着 *"A paper you could not read is recorded, not dropped and not invented"* | 一行 `test -f` 循环 |
| 2 | MEDIUM 检查是**无词边界子串匹配** | `safety_factor` 因描述含 "limit-state **sea**rch" 里的 `sea` 被判"命名了海洋介质"。8 个输出里 **2 对 4 蒙 2 冤**。且不分域：任何 KI 出现 research/seasonal/bedrock/island 都白捡 PASS | 正则加 `\b` |
| 3 | dag 缺 `outputs` 键时 `if X and not Y` **短路** | 我们的 dag 根本没有 `outputs:`，裁判对 dag 报零失败 | 空集合单独判 |

第 1 条最严重：规格把"出处不许编"列为最重纪律，裁判零验证。
第 3 条恰是它自己文件头那句 *"a stage that cannot fail is not a check"* 的反例。

---

## 五、域可插拔性

`stages/s1_pipeline_map.py:18-27` 找不到域模板时**静默回落 hydrology**：

```python
    # Fallback to generic hydrology template
    with open(template_dir / 'hydrology.yaml') as f:
```

注释说 "generic"，但 hydrology 模板不是 generic 的。实测传 `--domain structural_fem`，
零报错零警告，给一个 Fortran 结构有限元求解器派了
"从 HWSD 推导土壤水力性质 / 用 AVHRR 分类植被 / 转换 CMFD 气象强迫 / 河道汇流"四个阶段，
而这份 YAML **会原封不动进入 agent 提示词**。

**好消息**：补一个 40 行的 `domain_templates/structural_fem.yaml`，**改 Python 0 行**，域就插上了。
真正对结构 FEM 没有对应物的只有 `medium`（`ki_vocabulary.py` 的 13 词封闭表，12 个是地学介质）。

---

## 六、KISS 包格式：值得取的三样

1. **`boundary.scope_out` —— 明写"不能算什么"。**填这个字段逼出了一条我们从没记录过的事实：
   这套 conforming 网格共节点、界面无压力自由度，**根本算不了扬压力**——而重力坝抗滑稳定验算离不开它。
   `docs/references/` 十三篇全是"怎么做 X"，没有一处系统写"X 做不了什么"。
2. **`severity: silent` + `remedy.prevention`。**后者要求每条知识指向一个会自动跑的检查，
   否则就得承认"没有防护"。
3. **可执行 preflight + `PREFLIGHT_REPORT=` 结构化契约**，失败项必须带 `fix`。

**最硬的一条实验证据**（来自手工建包）：只删 `gravdam_meta.json`，其余全同 →
水压整个消失，坝顶位移 **0.26 mm vs 15.6 mm（60 倍）**，而 `physics_gate`、坝顶符号、量级、
两步施工、组序、全局平衡——**六项通用检查全部通过**。只有"实际施加了几条水压边"抓住了它。

**格式装不下的**：工具链的编程接口契约。KI 包围绕求解器设计，整套 schema 没有位置放
"`mesh_io.read_elements()` 返回 tuple 列表而非 dict"。对 ADCIRC 那种 4 个 convert 工具够用；
对 `skills/` 下 20+ 个互相 import 的脚本是结构性空白。

**不值得取的**：自动生成的空壳（`knowledge_infrastructure.yaml`、`workflow.md` 全 `TBD`）、
跨模型编目字段（`ki_class`/`spatial`/`temporal`/`closure`）、`processes.modules`、
`forcing`/`initial_conditions`、文献管线（我们的判据来自解析解与基准算例）。

---

## 七、一处必须更正的引用数据

"带 KI **up to 84%** vs 不带 <40%"（3000 试验 / 10 agent / 5 平台 / 14 里程碑 / NSE ≥ 0.2）：

- 是 **"up to"，不是中位数**
- **判定代码与试验记录在两个仓库里都不存在** —— 作者声明，非可独立复现的证据
- KDT 里真正做过、**样本先锁定**的对照实验是 **Caravan 配对臂**：
  锁定 30 个流域跑三条臂，默认参数 test-NSE 中位数 −0.05 / 人工 DDS +0.56 /
  agent 自主设计 0.555 vs 同流域人工 0.475。**有地板臂、配对比较、报分布不报均值** —— 这才是模板。

---

## 八、最终落到本仓库的东西

这次评估不是以"采纳某个格式"收尾，而是以**把门控从一维布尔推到三条正交的轴**收尾。

| 来源 | 落成什么 |
|---|---|
| KISS 的 60 倍对照实验 | `run_pipeline.py` 的 `gravdam_meta` 缺失改硬失败；`harness/consistency.py` 的 load provenance 检查 |
| KDT 的四条跨文件一致性检查 | `harness/consistency.py` —— `type_problem` 三方交叉核对 |
| KDT 的 run-validity critic 三态 | `harness/gate.py::run_validity` 的 `valid`/`degraded`/`incomplete` |
| 元规则 1（不能失败的检查不是检查） | 每个谓词区分"不存在"与"存在但错了"，前者判 `unverified` |
| 元规则 7（检查器与生成器共用读取器） | `1.glb` 一律走 `import_glb.parse_glb` |
| KISS 的幂等续跑（并补其盲点） | `harness/suite.py` —— 跳过条件是"产物存在 **AND** 输入 hash 未变" |

**两者各自的盲点也都被实测暴露并写进了注释**：KISS 的续跑不检测输入变化；KDT 的裁判有不可失败路径。

顺带，用整套 train 算例检验架构（14/15 通过）的过程中，另外查出并修掉了 8 个静默缺陷 ——
包括动力算例的**质量矩阵从未生效**（`order_time` 写成按自由度索引的 8 个零，求解器只读前 2 个 → 静力）
和**地震一直加在竖向**（`earthquake_curve` 槽位=方向，全仓库写成 `[0,2]`）。
这两条都不是 KISS/KDT 教的，是跑出来的 —— 印证了第三节那个"方法边界"的判断。

---

## 九、取舍（不变）

自研为主干。把"重打包成 KI 包格式"降级为一个只读导出器，且不早于内部清单建成 ——
他们格式的价值来自 119 包 × 14 域的横向复用，我们只有一个求解器。
**可发表性的路径不是换格式，是补 Caravan 那种配对臂数据。**

但对 KDT 本身的评价要上调：**它能跑，产出质量超预期，元规则值得抄。**
三个裁判空洞各改 1~3 行即可，作为合作开发者值得提上游。
