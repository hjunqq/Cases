# 探针报告：VIE 下 `earthquake_curve` 的双重激励消融（预先登记，2026-08-28）

> 第六个预先登记探针，回答 `06-open-questions.md` open #2。
> 材料：`probe/vie-ablation/`（predictions.json + sha256 + judge.py + verdict.json
> + posthoc_*.py + posthoc.json）。
> `predictions.json` 全程未改动，哈希可验：
> `d8c82b9b592f345c911ee449bcc995232bca703c4fe5de1d2cc268a9a8cae570`

## 待检验的源码论断

`02-facts-semantic-drift.md` §1：`Fem.f90:8525` 无条件读 `earthquake_curve`；
`8683-8687` 由它算 `fachv`，无 `type_ABC` 守卫；`fachv` 的施加点也无 `type_ABC`
守卫。**推论：VIE 下填 `earthquake_curve` → 基底加速度叠加在入射波之上。**

## 判决：2/5 成立（对照组 2/2 全过，结果有效）

| | 角色 | 预测 | 判决 |
|---|---|---|---|
| C1 | 对照 | FIX 算例 train02 关掉 `earthquake_curve` 必须同时使 `fachv` 归零且响应显著改变 | **PASS** |
| C2 | 对照 | 同一 deck 跑两遍，坝顶位移时程逐位相同 | **PASS** |
| P1 | 预测 | VIE 基线（`0 0`）全程 `fachv≡0` | **PASS** |
| P2 | 预测 | VIE 下填 `2 0`，`fachv` 变非零（无 `type_ABC` 守卫） | **PASS** |
| P3 | 预测 | 坝顶 x 位移时程相对改变 ≥ 5% | **FALSIFIED**（实测 0.0） |
| P4 | 预测 | 变体峰值 \|ux\| 严格大于基线 | **FALSIFIED**（完全相等） |
| P5 | 预测 | 第二个 VIE 算例 `cases/vie` 复现 P2+P3 | **FALSIFIED**（该算例根本跑不起来） |

对照组证据：

```
C1  fachv_max_2(t02_on)=0.31686   fachv_max_1(t02_on)=0
    fachv_max_2(t02_off)=0        reldiff_y(off vs on)=1.0   （阈值 0.10）
C2  250/250 步、两个分量的十进制字符串完全相同
```

## 登记范围内的结果：填了，`fachv` 活了，解一点没动

| 运行 | `earthquake_curve` | `fachv_max_1` | 坝顶 peak\|ux\| | rms ux |
|---|---|---|---|---|
| t10_base | `0 0` | 0.0 | 0.35015988 | 0.177265465 |
| t10_var  | `2 0` | **3.16860** | 0.35015988 | 0.177265465 |

全场比较（2543 节点 × 250 步，非仅探针节点）：

```
t10_base vs t10_base_rep（跑两遍的噪声地板）  max|Δ| = 1.0e-15   相对 2.8e-15
t10_base vs t10_var    （登记的消融）        max|Δ| = 1.0e-15   相对 2.8e-15
```

**消融效应与"同一个 deck 跑两遍"的末位打印噪声一模一样，即严格为零。**
`fachv` 被算出来了（3.1686，写进 500 行 `1.chk`），但没有进入任何方程。

按登记，P3/P4 判 FALSIFIED，不予追认。

## 为什么是零：一个我在设计实验时没查的开关（POST-HOC）

> 以下全部标注 **POST-HOC**，不在预先登记内，不计入 2/5。

`Fem.f90:13527`：

```fortran
DO igroup = 1,ngroup
    if(force_process(igroup)==0) cycle   !zhao 05/08/05
    ...
        value(idofn+1:idofn+ndimn) = -fachv        ! 13553，惯性力
```

`force_process` 由 `Global.f90:951-952` 从 `.glb` 读入，是**全局唯一**使用点。
两个算例的求解日志：

```
train10_dynamic_vie   force_process = 0 0 0 0 0     ← 惯性力循环对每个组都被跳过
train02_gravdam_seismic force_process = 1 1
```

**我选的 VIE 基线算例，恰好用另一个与 `type_ABC` 无关的开关把 `fachv` 通路整条关掉了。**
这正是 CLAUDE.md 里 PRJ-6057 记的那个故障模式，我在选算例时没有检查。

于是把同一对消融在 `force_process = 1 1 1 1 1` 下重跑（`posthoc_forceprocess.py`）：

| POST-HOC 运行 | `earthquake_curve` | `force_process` | `fachv_max_1` | 坝顶 peak\|ux\| |
|---|---|---|---|---|
| ph_base_fp | `0 0` | 1 1 1 1 1 | 0.0 | 0.35015988 |
| ph_var_fp  | `2 0` | 1 1 1 1 1 | 3.16860 | **0.37357092** |

```
t10_base   vs ph_base_fp （只开 force_process，不填曲线）  相对 2.8e-13   ← 仍是噪声
ph_base_fp vs ph_var_fp  （POST-HOC 消融）                 相对 0.1368
坝顶 reldiff_x = 0.1372     peak|ux| +6.7%     rms ux +2.7%
```

**结论（POST-HOC）：`type_ABC='VIE'` 确实不守卫 `fachv`。**在 VIE 仍然生效、
入射波仍然施加的情况下，填 `earthquake_curve` 使坝顶响应改变 13.7%、峰值增大 6.7%。
两条激励路径同时活跃，源码论断成立。

## 双重激励是否成立

**成立，但要加一个前提条件。**准确的说法是：

> VIE 下填 `earthquake_curve`，只要 `force_process` 中该组不为 0，
> 基底加速度就会叠加在入射波之上；`type_ABC` 不阻止这件事。
> `force_process(igroup)=0` 会把这条通路关掉——但它同时也关掉了 FIX 算例的地震激励，
> 所以它不是"VIE 的保护"，而是"这个算例本来就没在算地震惯性力"。

`02-facts-semantic-drift.md` §1 的推论**在机制上正确**，
但它漏掉了 `force_process` 这个第二守卫。语义漂移表里
`earthquake_curve` 的条目应改成两维（`type_ABC` × `force_process`），
而不是只按 `type_ABC` 分。

顺带：**`train10_dynamic_vie` 本身是个 `force_process=0` 的算例**，
即它的地震惯性力通路从未打开过。它的动力响应完全来自 VIE 入射波。
这一点此前未见记录。

## 诚实的边界

1. **单算例。**登记的复现（P5，`cases/vie`）失败了，而且失败原因与本课题无关：
   该算例**未经修改的基线**就跑不起来，`forrtl: severe (59): list-directed I/O
   syntax error, unit 14, file .../1.ini`（`NINIT=2 KINIT=2`，初始应力文件读不动）。
   所以"VIE 不守卫 `fachv`"目前只在 `train10_dynamic_vie` 一个网格上验过。
2. **train10 的吸收边界本身是坏的**（30 条竖直边被标成底边界，见 `02` §4）。
   消融对的两次运行用同一份坏边界，所以**消融本身有效**；
   但任何一次运行的**绝对位移值都不可信**，13.7% 这个数字是"在这个坏边界模型上"的量级，
   不是"真实工程中双重激励的误差"。
3. **POST-HOC 部分改了两个槽位**（`earthquake_curve` 与 `force_process`），
   不是最小消融。它证明了"VIE 不守卫 `fachv`"，
   没有单独隔离 `force_process` 与 `type_ABC` 的交互（虽然 `t10_base vs ph_base_fp`
   为噪声，说明单开 `force_process` 本身无效应）。
4. **未检验哪一种激励在物理上正确**，也未量化用户实际会犯多大的错。
5. 曲线 2 被认定为"加速度曲线"，依据是它是 `1.LOA` 里唯一 `SEISMIC` 类型的曲线，
   这是从 deck 读出来的，没有独立对照求解器的曲线索引验证。

## 我踩到的仪器 bug（如实记录）

| # | bug | 后果 | 怎么抓住的 |
|---|---|---|---|
| 1 | **看到 base/rep 两次运行末步 `resid` 不同（1.1903124088e-3 vs 1.1903125117e-3），当场判定"求解器不确定，C2 必挂，全部作废"，准备去 pin `MKL_NUM_THREADS=1` 重跑全部** | 差点因误判去改整套仪器配置 | 实际按登记判据（坝顶时程字符串）一比，逐位相同，C2 PASS。**登记时把判据写死在具体量上，救了一次过度反应。** |
| 2 | `judge.py` 的 `solved` 只查 `1.flavia.res` 存在 | `cases/vie` 崩溃前会先写一个 0 字节的 `1.flavia.res`，被判成"跑成功了"，P5 的证据栏显示 `solved: true` 但 `n_steps: 0` | 看 verdict.json 时发现 `n_steps=0` 与 `solved=true` 矛盾；已修为 `size > 0`，重跑判决，P5 结论不变 |
| 3 | **算例选择错误：没查 `force_process` 就选了 train10 做 VIE 基线** | P3/P4 被证伪，且如果只报登记结果，会得出"VIE 下双重激励不存在"这个**与事实相反**的结论 | 结果形态可疑——`fachv` 明明非零而全场差异恰好等于噪声地板，说明"算了但没用"，于是回去找施加点的守卫，命中 `13527` |
| 4 | 清理列表只删了 `1.flavia.res/1max/1.chk/run.log`，`1.bar/1.bem/1.ctr/1.gdm/1.gpv/1.rtt` 也是求解器输出但没删 | 未造成错误（消融对两侧对称，都从 `cases/` 的同一份副本出发），但属于隐患 | 跑完后 `diff -rq` 看到这些文件出现差异才注意到 |

另有一条不算 bug 但值得记的**可读性缺陷**：metrics 的位移键原本只叫
`peak_x` / `rms_x`，复核者按 `peak_ux` / `rms_ux` 去找，找不到，
合理地怀疑"指标提取失败、P3/P4 判在空数据上"。
已加同值别名 `peak_ux/peak_uy/rms_ux/rms_uy` 与显式的 `series_extracted` 布尔，
并保证**任何情况下键都存在**（提不出来时写 NaN 而非省略），
使"缺失 / 0 / 提取失败"三者在 verdict.json 里可区分。
重跑 judge，`verdicts` 逐条完全相同，2/5 不变。

**bug #3 是本次最重要的一条。**它不是判据写错，是**实验设计错**——
预先登记只能保证"不追认"，保证不了"选对了标本"。
2/5 这个分数如果照单全收，产出的会是一条错误的负面结论。

抓住它的是形态判据，和 `11-probe-report-man-readers.md` 里那条同源：

> **当一个消融"上游明明变了、下游差异恰好等于噪声地板"时，
> 先怀疑中间有个你没查的守卫，不要报告"无效应"。**

这条可以直接写成规则：**任何消融实验，在跑之前必须枚举目标变量的
全部消费点守卫**（`data/use-sites.json` 已有原料），
把每个守卫在基线 deck 里的取值打印出来。本次如果做了这一步，
`force_process=0 0 0 0 0` 会在写 predictions 之前就暴露。

## 对 `02-facts-semantic-drift.md` 的更正建议

§1 末尾的结论行建议改为：

```
VIE 下如果填了 earthquake_curve，且 force_process 中该组 /= 0，
基底加速度会叠加在入射波之上——双重激励。（实验确认：坝顶响应改变 13.7%）
force_process(igroup)==0 会关掉这条通路（Fem.f90:13527），
但它同时也关掉 FIX 下的地震激励，不是 VIE 专有的保护。
```

§2 的语义漂移表里 `earthquake_curve` 条目应加一维 `force_process`。

## 复算

```bash
cd fem-chat/docs/research/hstar-input-redesign/probe/vie-ablation
sha256sum -c predictions.sha256      # 确认预测未被改动
python3 setup_runs.py                # 在 /tmp/claude-1000/probe-vie 重建 7 个运行目录
for r in t10_base t10_base_rep t10_var t02_on t02_off vie_base vie_var; do
  HSTAR_SUITE_TIMEOUT=900 python3 ../../../../harness/_solve_deck.py /tmp/claude-1000/probe-vie/$r
done
python3 judge.py                     # 登记判决 -> verdict.json
python3 posthoc_forceprocess.py      # POST-HOC 的 force_process=1 消融对
python3 posthoc_report.py            # POST-HOC 全场比较 -> posthoc.json
```

`cases/` 全程只读；求解一律经 `harness/_solve_deck.py`，未直接调用 `./hstar`。
