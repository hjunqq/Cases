# HSTAR_TestData — 算例数据目录

路径: `D:\Projects\HSTAR_Next\HSTAR_TestData\cases\`

## 目录结构

```
HSTAR_TestData/cases/
│
├── 基础验证算例 (Easy_HSTAR 初始开发时创建)
│   ├── static/              2D 小坝静力 (462节点, 3组, legacy+TOML)
│   ├── freq/                2D 小坝模态 (462节点, lumped+consistent)
│   ├── fix/                 2D 小坝动力 (462节点, Newmark+Rayleigh+地震)
│   ├── damage/              3D 单元弹性 (单个 H8 元素)
│   └── gravdam/             2D 重力坝+Goodman接缝
│
├── 培训算例 (课题组12个算例, 从 Z:\HSTAR_Archive 迁移)
│   ├── train01_gravdam_static/      重力坝静力 (2block+水压, 2705节点)
│   ├── train02_gravdam_seismic/     重力坝地震 (500步Newmark, 地震时程)
│   ├── train03a_modal_dry/          模态干态 (3920节点, 5阶)
│   ├── train03b_modal_ifs/          模态有水 (Westergaard附加质量, .set)
│   ├── train04_beam_faceload/       3D梁面荷载 (B8, 40个Q4面)
│   ├── train05_slope_stability/     边坡稳定-已知滑面 (MCJOINT薄层, kstab极限状态, PARDISO)
│   ├── train05b_slope_srm/          边坡稳定-未知滑面 (强度折减 MAT_DE 1.0→0.5×100步)
│   ├── train06_concrete_damage/     混凝土损伤 (Ghrib icr=5, 3D 2block)
│   ├── train07_thermal_transient/   瞬态热分析 (3D 5628节点, Crank-Nicolson)
│   ├── train07b_thermal_steady/     稳态热分析 (同网格)
│   ├── train09_rc_bond/             钢筋粘结 (B8+L2+steel, 5种滑移本构)
│   ├── train10_dynamic_vie/         动力VIE边界 (110条吸收边, .set)
│   ├── train11_staged_foundation/   分级施工基础 (5组2block)
│   ├── train12_seepage_steady/      稳态渗流 (Laplace, W-DOF)
│   └── train12b_seepage_transient/  非稳态渗流 (θ-法)
│
├── XFJ 新丰江反演研究算例 (信赖域/hstardeback 整套工况, 35331节点)
│   ├── xfj_thermal_transient/      瞬态温度场 (type_problem=S, 289步)
│   ├── xfj_static/                 稳定位移场 (type_problem=Q, 2步施工+水压+温度)
│   ├── xfj_seepage_transient/      变化渗流场 (type_problem=S, 289步水位)
│   ├── xfj_inverse_mat/            弹性模量反演 (信赖域, 12测点位移)
│   ├── xfj_inverse_mat1/           反演变体 (2参数, 50/100/90 初值)
│   ├── xfj_inverse_mat2/           反演变体 (6参数, 12测点)
│   └── xfj_inverse_mat3/           反演变体 (6参数, 12测点)
│   注: 上游状态文件(.gpv/.inw/.oit/.upf/.rtt/.res)未入仓,
│       每个 case 自带 prepare.sh 从 /mnt/share 现场拉 symlink
│
├── 功能验证算例 (新功能的单元级测试)
│   ├── test_beam2d/                 悬臂梁弯曲 (EB梁, 解析解验证 <0.01%)
│   ├── test_duncan_chang/           Duncan-Chang土柱 (双曲线模型)
│   ├── test_concrete_tension/       混凝土拉裂 (d≈0.5, 18次迭代)
│   └── test_arclength/              弧长法追踪 (Crisfield, 10步)
│
└── Legacy baseline (hstar_toml.exe 用, 非 Easy_HSTAR)
    ├── goodmanLU/                   Goodman LU 分解
    ├── rcbeam/                      RC梁非线性
    ├── temp_stress/                 温度+徐变应力
    ├── tunnel/                      隧道开挖
    ├── tunnel_sl/                   隧道多步
    └── vie/                         VIE 边界 (旧格式)
```

## 运行方法

```bash
# Easy_HSTAR (TOML 格式)
cd D:\Projects\HSTAR_Next\Easy_HSTAR
easy_hstar.exe ..\HSTAR_TestData\cases\train01_gravdam_static\1.toml

# 回归测试 (全部23个)
python tests\regression\test_regression.py
```

## 回归测试覆盖 (23个)

| # | 测试名 | 算例目录 | 分析类型 | 关键验证 |
|---|--------|---------|---------|---------|
| 1 | 2D_static | static | Q 2D | 收敛 |
| 2 | 3D_elastic | damage | Q 3D | Uz |
| 3 | modal_freq | freq | E | 前3阶频率 |
| 4 | gravdam | gravdam | Q+Goodman | 收敛 |
| 5 | duncan_chang | test_duncan_chang | Q+DC | Uy |
| 6 | concrete_tension | test_concrete_tension | Q+CONCRETE | d≈0.5 |
| 7 | beam2d | test_beam2d | Q+梁 | PL³/3EI |
| 8 | train04 | train04_beam_faceload | Q 3D面荷载 | <0.3% |
| 9 | train01 | train01_gravdam_static | Q 2block+水压 | 0.8% |
| 10 | train03a | train03a_modal_dry | E 5阶 | 频率 |
| 11 | train03b | train03b_modal_ifs | E+IFS | 频率降19% |
| 12 | train05 | train05_slope_stability | Q+MCJOINT kstab | k_safety=kstab+塑性带 |
| 12b | train05b | train05b_slope_srm | Q+MAT_DE 强度折减 | 终步\|U\|max 0.1% |
| 13 | train11 | train11_staged_foundation | Q 5组 2block | 块2 Ux -5.50/Uy -4.02 (0.03%/0.07%) |
| 14 | train09 | train09_rc_bond | Q+bond ikindks=5 | Uy 5.7%/Ux 1.5% |
| 15 | train06 | train06_concrete_damage | Q+CONCRETE 2block+30水压面 | 块1 Uz 精确; 块2 Uz 0.6%/Ux 11.7% |
| 16 | train10 | train10_dynamic_vie | F+VIE | 衰减14800× |
| 17 | train12b | train12b_seepage_transient | 渗流瞬态 | θ-法 |
| 18 | train07b | train07b_thermal_steady | 热稳态 | T |
| 19 | train07 | train07_thermal_transient | 热瞬态 | 46步 |
| 20 | train12 | train12_seepage_steady | 渗流稳态 h(竖直边界BC) | 孔压[-1.34,1.18]MPa 水头[-249,111] |
| 21 | train02 | train02_gravdam_seismic | F+地震 | 500步 |
| 22 | kinit2 | fix | F+kinit2 | 初态 |
| 23 | kinit1 | fix (temp) | F+kinit1 | 自动平衡 |

## 另外的目录

| 路径 | 说明 |
|------|------|
| `D:\Projects\HSTAR_Next\process\` | 老程序 legacy baseline (hstar_toml.exe), 不用于 Easy_HSTAR |
| `D:\Projects\HSTAR_Next\Easy_HSTAR\` | 源代码 + 构建 + 测试脚本 |
| `D:\Projects\HSTAR_Next\hstarYLOrig\` | 原始 HSTAR 源码 (73000行) |
| `D:\Projects\HSTAR_Next\docs\cases\` | 算例说明文档 |
