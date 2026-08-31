# 本次改动实际跑过的算例 — 供人工核对

2026-08-26。**deck（输入）+ 完整结果 + VTP 都在**，共 1.7 GB。
结果文件可用 GiD 直接打开（`1.flavia.msh` + `1.flavia.res` 是原生对）；
`result_b*.vtp` 是给 web 查看器的派生件，用 ParaView 也能开。

不过核对时**更推荐在 Windows 上用你自己的求解器把这些 deck 重跑一遍**，
再和这里的结果比 —— 那能同时验证两件事（deck 对不对、两边求解器一不一致），
比只看我这边 Linux 的结果有意义。前提见下。

## ⚠ 先确认求解器版本

本机 Linux 二进制 `hstarYLOrig/HSTAR/x64/Release/hstar` 与 `cases/cases/train02c_dbg/hstar.exe`
**源码基线不同**：

| | nstepjq | ninistn | 说明 |
|---|:---:|:---:|---|
| Linux（2026-06-30，已用当前源码重建并逐位复现） | ✓ | ✓ | 含 2023-12-15 新增字段 |
| Windows `train02c_dbg/hstar.exe`（文件日期 2026-08-20） | ✗ | ✗ | 老基线 |

`.man` 的 `nstepjq,nstepjp` 那一行**只有新基线会读**。老基线读同一个 deck 会整体错位一行。
下面这些 deck 都是按**新基线**写的，用老 exe 跑会得到错误结果（不一定报错）。
**核对前请先在 Windows 上重编到当前源码。**

---

## `suite/` — 生成器产出的 deck（6 个）

套件里走 `config.json` 模式的算例，deck 由 `skills/generator.py` 生成 —— 也就是今天改动
直接影响的那些。核对重点：

| 算例 | 今天改了什么，怎么看 |
|---|---|
| `train02_gravdam_seismic` | **地震方向**：`1.man` 第 2 行应为 `1 0 2 0`（槽位1=x 水平）。`1.chk` 里 `fachv` 第一个分量在变、第二个恒为 `0.000000E+000` |
| 同上 | **质量矩阵**：`1.glb` 各组第三行应为 `0  2`（不是八个零）。这决定质量项系数是 1.0 还是 `beeta2*ditime²`(~1e-4) |
| `train01` / `train03a` / `train03b` / `train04` | `1.glb` 的 `gid` 行现在会开 `gid_f`（节点力/反力）；力学算例还会写 `tofor` 块 |
| `train12b_seepage_transient` | 流体域 `order_time` **保持 `0 0` 未动**（`0 2` 实测会段错误，无人工 deck 可校对） |

## `vie-audit/` — VIE 对照实验三变体

同一个 `train10_dynamic_vie`，只改一个变量：

| 变体 | 改了什么 | 结果（坝顶 Ux 峰值） |
|---|---|---|
| `base` | 原样 | 351.2 mm |
| `fixed` | 四个组 `order_time` `0 0`→`0 2` | 386.4 mm（+10%） |
| `d2` | 在 `fixed` 基础上，位移曲线（`.LOA` 第 4 条）数值 ×2 | 734.6 mm |

**结论：`order_time` 对 VIE 只有 10% 影响**（激励从边界以位移/速度进入，不经过 `fachv×质量`），
**不是** 0.7~7 倍的主因。`d2` 那组证明响应对位移曲线近似线性（×2 进 → ×1.90 出），
所以"逐点 0.7~7 倍"不可能由全局缩放因子造成 —— 全局因子给出的是恒定比值。

`1.chk` 里可查 `fachv`（VIE 下加速度曲线不用，恒为 0 是正常的，**不能拿它判断地震有没有进去**）。

## `seismic-direction-check/` — 地震方向端到端验证

`gen_gravdam.py` 现生成的 60 m 重力坝（315 节点）+ `gravdam_seismic_2block` 模板。核对：

```
1.man 第2行      1  0  2  0                      earthquake_curve = [2,0]
1.chk fachv      |x| 峰值 4.99013,  |y| 恒为 0    水平激励
坝顶 Ux/Uy 峰峰比  5.9                            悬臂主导,符合水平地震
```

改动前是 `[0,2]`（竖向），比值只有 1.04。

## `suite_state.json`

套件运行台账：每个算例的输入 hash、求解模式、耗时、三轴判定结果。
幂等续跑就靠里面的 `input_hash` —— 产物在且 hash 未变才跳过。
