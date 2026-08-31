# xfj_inverse_mat

**角色**: 反演分析
**来源**: `xfj_new/反演分析_mat`（信赖域 / hstardeback / xfj_new）
**说明**: 弹性模量反演（type_problem=Q + 1.man 第 7 标志 = 3）。读上游静力/温度场状态，按测点位移（1.obs）反演坝体 E 值，使用信赖域算法。

## 工程库定位

这是新丰江混凝土坝（XFJ）弹性模量反演研究的运行阶段算例（35331 节点 / 28647 单元 B8 / 25 组 / 4 种材料）。
与同坝静力简化版 `XFJ_S1_2block`（17276 节点）相比，本算例使用更精细的网格并配套**温度场 → 静力 → 渗流 → 反演**完整工况链。

## 工况链依赖

```
xfj_thermal_transient   ───┐
xfj_seepage_transient   ───┼──►  xfj_static  ──►  xfj_inverse_mat(1..3)
                            └─►
```

**本工况依赖上游输出**：

- `xfj_static` 的求解结果（1.gpv / 1.inw / 1.oit / 1.upf / 1.rtt / 1.res 等）
- `xfj_thermal_transient` 的求解结果（1.gpv / 1.inw / 1.oit / 1.upf / 1.rtt / 1.res 等）

运行前请先：

```bash
bash prepare.sh   # 从 /mnt/share 拉取上游状态文件 symlink
```

## 文件清单

仅入仓求解器**输入文件**（控制 / 网格 / 边界 / 荷载 / 测点）。
**输出文件 + 大型重启态文件**不入仓，需要时由 `prepare.sh` 从 `/mnt/share` 现场拉 symlink。

## 运行

```bash
bash prepare.sh
python /home/huijun/HSTAR_Next/fem-chat/skills/run_pipeline.py .
# 注: type_problem=6/反演模式当前不在 fem-chat 模板预设中，
#     run_pipeline 会按 1.glb 原样调求解器。
```

## 注意

- 1.man 第 3 行第 7 字段 = `3` 表示反演模式（仅 inverse 工况）
- 1.glb 第 9 行 `type_problem` 决定求解器分支（S=渗流/温度场, Q=静力含反演）
- run.bat 是原 Windows 调用脚本，Linux 下用上面的 quick_analysis 命令
