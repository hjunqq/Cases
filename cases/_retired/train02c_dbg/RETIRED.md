# 已退役：train02c_dbg（2026-08-31）

## 身份与退役理由

"_dbg" 后缀表明它是当年调试 train02c 系列时的中间产物。诊断（判据线程
G，2026-08-31）：**死 deck**——没有任何驱动机制：

- `type_ABC = FIX`（非 VIE），`.man` 的 `earthquake_curve = 0 0`，
  也没有 VIE 的 `_d/_v` 记录 → 三条驱动路径全部为零
- 结果响应为机器零：位移量程 6.6e-16

一个声明为动力（type_problem=F）却无激励的算例，任何第一性原理判据
都只能诚实报 unverified——它不度量任何物理，作为算例无价值。

## 保留的价值

无独立价值（train02c_seismic_wave_compare 是同系列的正式算例，READY）。
原文件完整保留于本目录；会话备份
/tmp/claude-1000/legacy-config-backup-0830-1056/train02c_dbg/。
