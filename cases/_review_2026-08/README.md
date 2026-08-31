# research/ — 一次性调研材料

存放**一次性调研产物**：读完就归档，不进运行时、不需要维护。
与 `docs/references/` 的区别是：references 是 agent 每次干活都要查的操作知识，
research 是做架构决策时的取证材料，决策做完就只剩考古价值。

| 文件 | 内容 | 日期 |
|---|---|---|
| `ki-three-way-report.html` | **三方评估正式报告**（已发布为 Artifact）。HPC-Skills / KISS / 本仓库 ki-harness-langgraph 在迭代闭环上的对照，含五条对前期判断的更正与 P0–P2 路线 | 2026-08-25 |
| `ki-three-way-comparison.md` | 上文的前一版草稿，含更细的本仓库量化数据（skill 行数、测试数、benchmark 构成） | 2026-08-25 |
| `kiss-format-trial.md` | **实证试验**：把 `gravdam_static_2block` 按 KISS 的 KI 包规格打包（产物在 `kiss-trial-pkg/`），再只靠这个包把算例从零跑通。含"漏项清单"（每次不得不回头查包外东西的记录）与一次对照实验：只删 `gravdam_meta.json`，水压全丢、坝顶位移差 60 倍，而六项通用检查全部通过 | 2026-08-25 |
| `kdt-trial.md` | KDT（Knowledge Dissection Toolkit）试用：规格 FILE 1–11、裁判 `verify_ki_structure.py` 的逐条检查与七条元规则、三步验证法、A/B 方法论。来源 `lzwei196/KDT` 目前私有、无 license、含未发表论文材料；本仓库作者是其合作开发者之一，已确认可发布。本文只做笔记与短片段引用，未整段拷贝其代码 | 2026-08-25 |
| `kiss-kdt-usage-report.md` | **使用报告**（已发布为 Artifact）。KISS / KDT 各自跑到什么程度、值得取什么、装不下什么，以及最终落到本仓库的实际改动 | 2026-08-26 |
| `kdt-run-report.md` | **KDT 多 agent 版实跑**（816 行）。本机 clone 后真跑 dissect：唯一实质改动是超时 3600→9000，第二轮 485 秒 **GATE PASS**。补写了三个缺失投影器。抓到一处规格明令禁止而裁判不验的诚实性违规：16 篇论文的 `text_path` 全部不存在于磁盘 | 2026-08-26 |
| `kdt-single-report.md` | **KDT-single 实跑**（817 行）。50 分钟产出完整 KI 包，gate 判 incomplete（8 条：4 环境缺件 / 2 gate 误判 / 2 真实缺陷）。内容抽查 5 项 0 幻觉，且在 `type_problem` 有 5 类（含 `W` 纯模态）这点上比我们的 CLAUDE.md 更准。域回落是 fail-open：未知域静默拿 hydrology 模板 | 2026-08-26 |
| `generation-vs-preservation.md` | **往返能力矩阵 + 导入器修复**（起因：RC 损伤算例在"基准里已实现过"的情况下失败）。21 个 train 算例只有 7 个有 `config.json`。**第二版更正了第一版：第一版全表偏差被我自己的测量脚本 bug 放大**（把 `import_project` 的 `{config,summary}` 包装层整个喂给了生成器，不报错、全按默认值生成）。修正后确认：**生成器是精确的（train01 从人工 config 逐字节等价），缺的是导入器**。本次已修 `.pre` 约束集（21/21）与 `.LOA` 边荷载（15/21，5 个第二方言显式拒绝），含 Fortran list-directed READ 解析器。回归：单测 329 全过、从-config 路径不变、求解套件 13/15 | 2026-08-27 |
| `roundtrip/` | 上文的可复算材料：`roundtrip_matrix.py`（几十秒跑完全量）与 `matrix.json`（每个文件的逐行差异样本） | 2026-08-27 |
| `ext-iteration-loops-deep-dive.md` | 外部两仓库的源码级深挖（42KB）。`dag.yaml` 的 `influence` / `safety.hazards` 段、`calibration.yaml`、CAPABILITY_INVENTORY、KDT 的知识更新方式、HPC-Skills 的 `HPC_*` 错误码表。**写正式报告时只用上了一部分，剩下的仍有参考价值** | 2026-08-25 |

相关的**非**一次性产物（会随代码演进，不放这里）：

- `docs/capability-inventory.md` — HSTAR 求解器能力 vs 工具链覆盖的差距审计
- `skills/test_skills.py` 里的 `solver_contract_*` 系列 — 把上面那份审计的结论
  变成会自动失效报警的检查，见 `docs/capability-inventory.md` 末节
