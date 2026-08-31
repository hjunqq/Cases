# 探针报告：`.man` reader 布局（预先登记，2026-08-28）

> 这是第一个按预先登记协议跑的自我研究闭环。目的有二：回答 open #8，
> 并检验"这套流程到底能不能自我研究"。
> 材料：`probe/man-readers/`（predictions.json + sha256 + judge.py + verdict.json）。

## 协议

```
1. 写 predictions.json（6 条可证伪预测）  ← 此时未看过任何静力 reader 的 READ 序列
2. sha256 落盘：59877bc3da40f8c52d3196781dba465e5866a15947c183a0e795f23c57859ec3
3. 写 judge.py：从源码提取 + 机械判定
4. 每次运行前校验哈希，确认 predictions 未被改动
5. 判决由 judge.py 给出，Claude 不参与判定
```

## 判决：4 条成立，2 条被证伪

| | 预测 | 判决 |
|---|---|---|
| P1 | 四个 15-READ 静力 reader 首记录布局相同 | **PASS** |
| P2 | 该首记录只读 `nincs` 一个变量 | **PASS** |
| P3 | 全部静力 reader 首记录布局彼此相同 | **PASS** |
| P4 | 没有静力 reader 读 `earthquake_curve` | **PASS** |
| P5 | 17 个 reader 的首记录布局去重 ≤ 5 种 | **FALSIFIED**（实为 6 种） |
| P6 | 每个既有 deck 的 `.man` 首记录与其开关所选 reader 一致 | **FALSIFIED** |

## 产出的新事实

### 1. open #8 已回答：静力分支不需要再分和类型

**10 个 reader 共用同一个首记录布局 `[nincs]`**：

```
STATIC_U  STATIC_U_P  STATIC_U_PW  STATIC_U_PWm  STATIC_U_reli
STATIC_rigid_1  STATIC_rigid_reli  back_analysis  back_d_analysis
response_spectrum          ← 此前在 01-facts 里记为"—"（未知）
```

**这是 Semantic IR 的直接设计输入**：静力（含 E 响应谱）在 `.man` 首记录这一层是**一个**变体，
不需要按 7 个静力子调度分支再分和类型。此前只能靠猜。

### 2. 第 6 种布局：`GHM2ADINA`

```
['nincs']                                       10 个 reader
['nincs', 'cdtest', 'earthquake_curve(1:ndimn)']  time_dependent
['nincs', 'earthquake_curve(1:ndimn)']            explicit
['nincs', 'fachv']                                frequency_analysis
['nincs', 'r0', 'r1', 'earthquake_curve']         GHM2ADINA        ← 全新，4 变量
['nincs_pb']                                      parameter_back_analysis_verify(_read)
```

`GHM2ADINA` 的 `nincs, r0, r1, earthquake_curve` 此前完全未知。

### 3. `train_vie_boundary` 是唯一真实回读异常

事后按正确判据（见下）复算，21 个算例中 **20 个一致**，唯一异常是
`train_vie_boundary`（期望 ≥4 token，实得 3）。它正是 open #1 里那 5 个疑似旧格式
deck 之一——**独立佐证**，不是新问题。

---

## 更重要的部分：这次探针自己错了三次

| 版本 | 仪器 bug | 后果 |
|---|---|---|
| v1 | 把 `.man` 的标签行当成数据行 | **21/21 算例全部"证伪"** |
| v2 | 判据写成 `==` 而非 `>=` | Fortran 读满即弃记录余部，多余 token 合法 |
| v3 | 没处理 `!` 尾注 | 4 个算例读不到任何数据行 |

**v1 如果由 agent 自由判定，产出的结论会是"全部 21 个 deck 与源码不一致"——
一个惊天动地的假发现。这正是"跑很久、结果全错"的标准形态。**

抓住它的不是更仔细的思考，是**证伪的形态**：

> **21 个算例以完全相同的方式失败，是仪器故障的特征，不是数据事实。**
> 真实的数据差异是参差不齐的（v2 之后就变成了参差不齐）。

这条可以写成自动规则：**当一个 probe 的失败率接近 100% 且形态高度一致时，
先怀疑 probe，不要报告发现。**

### 预先登记在此处生效了

事后用正确的 Fortran 语义判据复算，P6 其实 20/21 一致。
**但 P6 按登记结果仍判 FALSIFIED，不予追认。**

判据是我自己写错的（`==` vs `>=`），而且写错的正是我自己在
`import_glb._Deck` 里已经实现对了的语义。允许事后改判据，就等于允许
"看到结果之后再决定什么算对"——预先登记存在的全部理由就是禁止这件事。

修**仪器**合规，改**预测**不合规。`predictions.json` 全程未动，哈希可验。

### 附带的结构性发现

`!` 尾注截断这条规则，我在 `import_glb._Deck._expand` 里已经实现过一次，
在 `judge.py` 里又忘了一次。**deck 解析逻辑已经在多处重复并各自漂移。**
这是 `10-roadmap.md` 里 P0-1（独立 decoder 作为共享组件）的直接论据。

---

## 对"能不能自我研究"的结论

**在这个维度上、按这套协议，可以。**成本约 15 分钟，产出 4 条新的真事实并回答了一个 open question。

但支撑它成立的**不是 agent 的推理能力**，而是四个条件同时具备：

| 条件 | 本次是否满足 |
|---|---|
| 问题**有限可枚举** | ✅ 17 个 reader，不是开放探索 |
| 真值来自**外部**（源码），不是上一步产物 | ✅ |
| 判定**机械**，agent 不参与 | ✅ judge.py |
| 验证回路在**秒级** | ✅ 每次重跑 < 2 秒，所以三个仪器 bug 都被便宜地抓住 |

**四条缺任何一条，就退化成你经历过的那种情况。**

而且必须承认：本次 agent 的推理**错了三次**，全部由协议兜住。
所以这套东西能不能自我研究，取决于**协议的强度，不取决于 agent 的聪明程度**——
这也意味着它是可以工程化的。

## 复算

```bash
cd probe/man-readers
sha256sum -c predictions.sha256   # 确认预测未被改动
python3 judge.py                  # 重新判定
```
