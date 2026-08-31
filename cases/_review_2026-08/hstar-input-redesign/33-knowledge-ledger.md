# 知识落地账本 —— 条件 6 的人工核定记录

> 2026-08-31 首次全量核定。条件 6 问的是:**这个算例教给平台的东西,落在哪了?**
> 合格的去处只有四类(28-triage §5):mechanics/consistency 的一条检查、
> deck-ABI/文档的一条协议事实、一条对账测试、或一条**否决记录**。
> "在对话里说过"不算落地。
>
> 机器可读镜像:`data/knowledge-ledger.json`,闸门条件 6 读它——
> 人工核定一次,闸门永久记住;未核定的算例保持 manual。

| 算例 | 教了什么 | 落在哪(证据) |
|---|---|---|
| train01_gravdam_static | 自重合力对账是可判定守恒律(闭合 1.4e-9);受约束节点自身份额必须扣除 | `mechanics.self_weight_resultant` + 单元测试;30-review §6.1 |
| train02_gravdam_seismic | PRJ-6057 全链条:槽位=方向由实验确证;`acc_absolute` 是构造量(fachv);振荡性才是动力不变量 | `seismic_oscillation` + 证伪测试;`ground_motion_input` 降级记录(30 附录 1);CLAUDE.md 既有规则获实验背书 |
| train02c_seismic_wave_compare | Newmark 耗散对 γ=0.6/β=0.3025 是真物理差异;ratio 1.11=平动不是响应 | `newmark` 透传 + `test_newmark_passthrough`;`amplification_factor` 降级注释里的实例 |
| train03a_modal_dry | 瑞利商 ω²=k*/m* 跨两条组装路径(源码核实非构造);容差由打印精度导出 | `modal_rayleigh_quotient`/`modal_spectrum_ordering` + 证伪测试;30 §3.1 |
| train03b_modal_ifs | 附加质量降频(f₁ 3.996→3.227 Hz)方向性旁证;FSI 边表 verbatim 携带 | 30 §3.1 旁证记录;`parse_ifs` FSI 段 + 回读测试 |
| train04_beam_faceload | .ftr 内力截面"写得出读不回"不对称;截面从坐标反推、不信注释(撒谎注释测试) | `parse_ftr` + `test_ftr_roundtrip`(station=99 撒谎用例);30 附录 3 |
| train05_slope_stability | 自平衡残差力求和为零——全局平衡是比逐 dof 收敛弱的陈述;误杀即回归的活教材 | 附录 9 + `srm` 测试"不收敛但全平衡→pass"用例;`matno_process` 逐块透传 |
| train05b_slope_srm | SRM 平衡的不变量形式(收敛态+平衡轨迹判别子);满强度 FoS<1 的 deck 病;坏基准重锚 | gate.py MAT_DE 分支 + 6 条证伪测试;benchmarks.py 重锚注释;附录 9 |
| train06_concrete_damage | 材料常数是未分类的改变物理项(ft 翻倍);裁定:默认可用、用时给值、AST 级解码列后续 | 29 处置表;`mat_raw` verbatim 携带 + 测试;审计 F2 记录 |
| train07_thermal_transient | 抛物极值原理带 DMP 诚实条款:一致质量阵合法下冲不设经验松弛 | `thermal_transient_envelope` + 证伪测试(growth-fail/dissipated-pass);附录 6 |
| train09_rc_bond | ikindks=5 选粘结模型(bond 行透传);盘上 .act 是字节相同的外来陈旧物(否决记录) | `glb_rows.bond` 透传 + 测试;附录 6 否决清单;NMATS=材料ID数≠块数(F 线程事实) |
| train10_dynamic_vie | .ifs 头 exx/uxx/densxx 是死字段、xyz0 活(弹簧参考点);VIE 自由面读入从未生效的 find/EOF 病 | vie-absorbing-boundary.md 更正;`parse_pre` 修复;`_ifs_absorbing_table` |
| train11_staged_foundation | 双块 per-BLKS 向量 arity 随 nblks;uinitial/matno_process 逐块真值 | glb_rows/blocks 透传 + `multiblock_nblks_import` 测试 |
| train12_seepage_steady | jfixvar=0 使逐点值表被绕过(H=y+1 机制闭环);零水头不能落常值 1.0 曲线 | 附录 5;generator `_head_curve`/`_sb` 修复;`extremum_principle` 正向;记忆 seepage-head-bc-fix 既有条目获第二实例 |
| train_contact_nonlinear | 小写标签行使 nblks 塌成 1(整簇 arity 根因);2D .ftr 按边切、导入生成必须两侧一起扩 | 大小写不敏感匹配 + 测试;`.ftr` 2D verbatim + 拒绝规则测试;contact_raw 携带 |
| train_seepage | gamawx 是版本敏感活诱饵(20230402 注释掉存储,归档按 10000 闭合=旧二进制);极值原理对 h 不对 p | 附录 6 版本实锤;`_extremum_pore_head`(γw 回声校验)+ 测试;parse_loa 顺序读取器重写 |
| train_seepage_stress | nrfields>1 真实存在:UW 双场组、fieldid 'UW' 是一个 item、双 nfdof/listdof 对 | A 线程事实(commit c2fa9b5)+ `import_field_dof_roundtrip` 测试守 UW 形态 |
| train_vie_boundary | VIE 驱动经 _d/_v(earthquake_curve 留 0);材料 imat 2..5 的 only_in_orig 诊断路径 | `seismic_oscillation` VIE 扩展(_declared_vie_drive)+ 测试;E 线程诊断记录 |

## 核定结论

18/18 全部有至少一条**判据级或测试级**落地(不只是文档),多数三类俱全。
两处相对薄的如实记录:

- **train_seepage_stress**:落地主要是"协议事实 + 回读测试",尚无 UW 耦合的
  **物理**判据(Biot 耦合下无极值原理,G 线程已如实 recuse)——它的条件 4
  靠 equilibrium+prescribed_displacement,成立但与"双场"特质无关。
- **train06**:损伤常数走 verbatim 携带,语义解码按使用者裁定列后续——
  落地的是**决定**而非能力,这正是否决/延期记录该有的样子。

未核定:train_temp_creep(BLOCKED,等 Fortran 修复,教训已在附录 8 排除表)。
