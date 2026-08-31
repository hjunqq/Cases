# xfj_static

**角色**: 稳定位移场
**来源**: `xfj_new/稳定位移场`（信赖域 / hstardeback / xfj_new）
**说明**: 稳定位移场（type_problem=Q）。两步施工 + 自重 + 水压 + 温度荷载，输出 1.gpv/1.inw/1.rtt 作为反演工况的初始状态。

## 工程库定位

这是新丰江混凝土坝（XFJ）弹性模量反演研究的运行阶段算例（35331 节点 / 28647 单元 B8 / 25 组 / 4 种材料）。
与同坝静力简化版 `XFJ_S1_2block`（17276 节点）相比，本算例使用更精细的网格并配套**温度场 → 静力 → 渗流 → 反演**完整工况链。

## 工况链依赖

```
xfj_thermal_transient   ───┐
xfj_seepage_transient   ───┼──►  xfj_static  ──►  xfj_inverse_mat(1..3)
                            └─►
```

**本工况自洽**，无上游依赖。

## 文件清单

仅入仓求解器**输入文件**（控制 / 网格 / 边界 / 荷载 / 测点）。
**输出文件 + 大型重启态文件**不入仓，需要时由 `prepare.sh` 从 `/mnt/share` 现场拉 symlink。

## 运行

```bash
python /home/huijun/HSTAR_Next/fem-chat/skills/run_pipeline.py .
```

## 注意

- 1.man 第 3 行第 7 字段 = `3` 表示反演模式（仅 inverse 工况）
- 1.glb 第 9 行 `type_problem` 决定求解器分支（S=渗流/温度场, Q=静力含反演）
- run.bat 是原 Windows 调用脚本，Linux 下用上面的 quick_analysis 命令
