# 100 m 重力坝 · VIE 黏弹性边界 · 动力时程

2026-08-26 从零建例。**用 KDT 自动生成的 KI 包作为主要指引**，同时检验那份 KI 能不能真支撑干活。
完整过程见 `BUILD-LOG.md`（466 行，含漏项清单与两处"似是而非的错误指引"）。

## 规格

| 项 | 值 |
|---|---|
| 坝高 | 100 m |
| 地基深度 | 3H = 300 m |
| 上下游各 | 2H = 200 m |
| 库水 | 位移型流体单元（真 W 场声学流体试过走不通，见 BUILD-LOG §3.1，**已如实记录未掩盖**） |
| 地震波 | 规范谱，**PGA = 1.9632 m/s² = 0.2001 g**，2001 点，20.0 s |
| 边界 | VIE，`nabssgroup=70` |
| 时程 | 1000 步 × 0.02 s = 20 s |

## 四个目录

| 目录 | 内容 | 状态 |
|---|---|---|
| **`case_m`** | **交付主算例** —— VIE + 库水 + 0.2g，无重力 | ✅ 退出码 0，1000 步，183 MB 结果 |
| `case_g` | 同上 + 重力在动力块内 | ✅ 对照，重力阶跃瞬态 |
| `case_fix` | **固定边界 + 加速度曲线驱动** 的对照组 | ✅ 对照（`type_ABC=FIX`，所以 `.man` 没有 VIE 那两行，正常） |
| `case` | 真 W 场 FSI 尝试 | ❌ 退出码 24（`.man` EOF），未跑通 |

`build.py` 是复现脚本。求解器 `hstarYLOrig/HSTAR/x64/Release/hstar`，
经 `harness/_solve_deck.py` 启动（注入 MKL 路径）。单次墙钟约 20 s。

## 自查结果

| 检查 | 结果 |
|---|---|
| `physics_gate` | PASS |
| `run_validity` | **valid** —— 最差步 879 两次迭代后 ratio 3.654e−14（deck 自己的容差 1e−5）；`global_equilibrium` = unverified（动力下 `tofor` 不含惯性力，属预期） |
| `deck_consistency` | consistent |
| 组块 `order_time` | ✓ 三组全部 `0  2`（质量矩阵参与） |
| 坝顶水平 ≫ 竖向 | ✓ **47.06 mm vs 10.29 mm，比值 4.6** |
| PGA | ✓ 0.2001 g |

**`fachv` 恒为 0 的交叉验证**（这条容易误判）：`case_m` 的 1000 条 `fachv` 全是 `0.0 0.0`，
而对照组 `case_fix`（FIX + 加速度驱动）同一字段是变化的（−1.895e−3、−1.551e−3…，
正是 `earthquake_a.dat` 的逐点值）。**说明 VIE 下 `fachv=0` 是正常表现，不是"地震没进去"。**

## ⚠ 建例过程中查出的三条，都影响仓库现有资料

1. **`time_curve_for_each_group = 0` 是"该组完全不施加重力"，不是"重力保持静态"。**
   源码两处佐证：`Load.f90:887-888` 的注释、`Load.f90:1170` 的 `if (tcurvegravity(igroup)/=0)`。
   而 `fem-chat/CLAUDE.md` 的 PRJ-6057 护栏写的是"（gravity stays static）"—— **写反了**，
   且该条标着 human-confirmed · highest priority。VIE 模板也照抄了 `[0,0,0]`。

2. **绕过 `run_pipeline` 直接调 `generator.generate_all()`，地震波会静默变成两个常量 1.0。**
   SEISMIC 曲线数据不是 generator 写的，是 `run_pipeline.py:262-274` 在调 generator **之前**
   把 `earthquake_*.dat` 读进 `tc["values"]` 的。不报错、deck 正常、求解器读得下去，
   第一次就这么跑了 1000 步、残差每步 ×2.2 指数发散到 1e40 才暴露。

3. **`train10_dynamic_vie` 的 `cdbound=2` 底边界组混进 30 条竖直边**（节点不在 `y_min=-250` 上）。
   入射波只从 `cdbound=2` 进，等于在地基内部竖直面上凭空注入水平入射波。
   **这是 train10「逐点 0.7~7 倍」的有力候选根因。**
   注意它与"Windows 上核对没问题"并不矛盾 —— 两边跑同一份 `.ifs`，
   同样的错误给出同样的结果；人工核对能确认"两边一致"，确认不了"物理正确"。

## KDT KI 包在这个任务上的表现

**给了错误指引**（比缺失更危险）：`tools/build_dynamic_seismic.py` 与 `SKILL.md §3.1` 都断言
用 `earthquake_curve` 填基底**加速度**曲线号 —— 这在 VIE 下是错的（VIE 走
`earthquake_curve_d`/`_v`，`earthquake_curve` 必须留 0）。而它 11 个模板里**没有任何 VIE 算例**，
其 `dt_003` 给的 remedy "COPY-FIRST from a template" 在这里反而会从
`train02_gravdam_seismic`（加速度驱动的普通动力）把错误固化下来。
