# 已退役：train_slope_unknown（2026-08-31）

## 身份

**这是 train05b_slope_srm 修复前的孪生 deck**——旧 `engineering:slope_srm`
基准所引用的"归档参考"（末块 |U|max = 2.35e5 m）的本尊。迁移时来历不明
故名 unknown；证据链（2026-08-31 诊断）：

| | 本 deck | train05b 修复前 |
|---|---|---|
| 网格 | 451 节点，360×180 | 相同 |
| 材料 | `'MC', 4.2e4, 0.` + `17 17`（c=42 kPa, φ=ψ=17°） | 逐字相同 |
| 密度/E/ν | 2500 / 30e6 / 0.3 | 相同 |
| 折减曲线 | LINEAR 1.0→0.5 | 相同 |
| 末块 |U|max | **2.35e5 m** | 旧基准"归档参考"恰为 2.35e5 |

## 为什么退役

坡在**满强度时 FoS≈0.6**：块 1（F=1.01）失衡已 12%、|U|max 已 41.8 m，
全程无收敛平台，块 100 失衡 60%、|U|max 2.35e5 m。整个 SRM 扫描从一个
已坍塌的坡开始，没有任何状态有意义。

修好它（c=60/φ=35）只会得到 train05b 的克隆——同网格同扫描，无独立价值。
放行闸门对它的 `global_equilibrium` fail 是**正确判定**，不可能也不应该
靠改判据消除。

## 历史价值（已在文档闭环）

它证明了旧 slope_srm 基准的参考值是**坏 deck 输出被钉成真值**
（`fem-chat/docs/research/hstar-input-redesign/30-*.md` 附录 5/7，
基准已于 2026-08-30 重锚到修复后的 train05b）。

原始文件完整保留于本目录；另有会话备份
/tmp/claude-1000/legacy-config-backup-0830-1056/train_slope_unknown/。
