# 自建架构跑 VIE — 与前两个 VIE deck 的对比

2026-08-27。同规格（100 m 坝 · 地基 3H · 上下游各 2H · 库水单元 · 规范谱 0.2g / 20 s），
走本仓库自己的标准路径：`gen_gravdam.build(reservoir=True)` → `quick_analysis.py . gravdam_dynamic_vie`。

## 第一次尝试：硬失败（好事）

```
forrtl: severe (24): end-of-file during read, unit 4, file .../1.pre
```

`generator.py` 从来不写 VIE 需要的两段（`.ifs` 的 `nabssgroup`、`.pre` 的 `nbounods`）——
这是我自己在 `docs/references/vie-absorbing-boundary.md` 里记过的缺口。
**它是响亮地失败，不是静默出错**，这一点比后面两个 deck 都强。

## 补齐后：三段都由几何推导

| 文件 | 补了什么 |
|---|---|
| `.ifs` | `nabssgroup` 段**从网格算出来**：底边（y == y_min）→ `cdbound=2`，左右（x == x_min/x_max）→ `cdbound=1`；库水域内部的面跳过（那属于 `nabsfgroup`） |
| `.pre` | `nbounods` + 边界节点表 + `bounfreez` 自由面高程 |
| `.man` | `inpcord` 改为按网格 `y_min` 推导（原先取模板默认 `0.0`，本例应为 −300，偏差整整一个地基深度 ≈0.15 s 走时）；`hwdirec` 默认改 0（均匀输入） |

## 三个 VIE deck 的横向对比

用新加的 `harness/consistency.py::check_vie_boundary` 同时判：

| deck | 边位置 | 边覆盖 |
|---|---|---|
| **自建（本目录）** | ✅ 38 条全在声明的面上 | ✅ 每段边界都被覆盖 |
| KDT 指引建的 `dam-vie-100m/case_m` | ✅ 70 条位置对 | ❌ **15 段无吸收边**（库水上游面，且 `nabsfgroup=0`） |
| `train10_dynamic_vie`（Windows 人工核对过） | ❌ **30 条不在声明的面上** | ❌ **61 段无吸收边** |

train10 的 `cdbound=2` 是入射波唯一入口（`Fem.f90:13614`），里面混进 30 条竖直边、
节点不在 `y_min=−250` 上 —— 等于在地基内部凭空注入水平入射波。

> **为什么人工双机核对没发现**：两边跑同一份 `.ifs`，同样的错误给出同样的结果。
> 人工核对能确认"两边一致"，确认不了"物理正确"。

## 自建算例的门控结果

```
physics_gate = True     run_validity = valid     deck_consistency = consistent
  vie_edge_placement  pass
  vie_edge_coverage   pass
```

## 这次对比说明的事

三个 deck 都"跑得出结果"，但只有自建这个的吸收边界在几何上站得住。
差别不在谁的工具更聪明，在于**判据是不是从几何算出来的**：

- 此前唯一的验证是 `Σ sedge == nabssgroup`，而这个计数在三个 deck 里**全都自洽**
- 新检查不看计数，只看位置与覆盖 —— 两个既有 deck 当场现形

这正是「数数不设阈值 = 假检查」。
