# 事实三：hstarpre 是历史 deck 编译器，但真值仍分散

> 2026-08-28。源码：`_archive/hstarpre/sourcef90/`，主程序：`fempre.f90`。
> 本文只记录可由源码和归档文件直接复核的事实；兼容性推论和新架构建议放在 `08`。

## 0. 一句话结论

`hstarpre` 不是简单地把一个完整控制文件机械拆成六个文件。它实际执行的是：

```
.ctl + 原始/参数化网格 + 模板 model1/1.glb + 若干辅助文件
              │
              ▼
        网格/拓扑处理 + 几何选择 + deck 生成
              │
              ▼
.glb/.loa/.pre/.mat/.ifs/.man + .sol/.opr/.tem/.ftr/.nrt/...
```

因此，HSTAR 输入生产知识至少存在于三处：

1. 当前 HSTAR reader：最终消费协议；
2. hstarpre：历史 producer、几何规则和功能组合；
3. Python `generator.py/import_glb.py`：当前 Web 工具链。

任何一处都不是单独完整的真值。

## 1. 归档资产

`_archive/hstarpre` 包含：

- 24,488 行 Fortran，其中 `fempre.f90` 13,791 行；
- Intel Fortran Visual Studio 工程；
- 32 位 Windows `hstarpre.exe` / `controlfile.exe`；
- 20 个约 19.8–22.0 KB 的 `.ctl` 示例；
- 20 套 `.ifs/.man/.pre/.loa/...` 输出及 20 个 `model1/1.glb` 模板；
- 接触、RC 衬砌、薄膜/壳、重力坝、渗流、位移/渗流反演等算例。

工程依赖 `DFLIB`（`fempre.f90:14`），路径拼接使用反斜杠，归档 exe 是 PE32；原程序不是
当前 Linux 工具链可直接嵌入的可移植库。

## 2. 实际输入不是只有 `.ctl`

`read_control`（`fempre.f90:6184-6577`）先从工作目录的 `input.txt` 读三类信息：

1. `probn`：`.ctl/.cor/.ele/...` 的输入基名；
2. `modeli`：模板模型目录；
3. `out_f_dir`：输出目录。

`open_read_and_output_hstar_file`（1522-1620）明确打开：

```fortran
open(glb_unit,file=modeli//'\1.glb')
open(glbout,file=out_f_dir//'\1.glb')
open(loaout,file=out_f_dir//'\1.loa')
open(preout,file=out_f_dir//'\1.pre')
open(matout,file=out_f_dir//'\1.mat')
open(ifs_unit,file=out_f_dir//'\1.ifs')
open(man_unit,file=out_f_dir//'\1.man')
```

所以 `.ctl` 不是自包含的总控文件。尤其 `.glb` 的大量全局字段来自模板
`model1/1.glb`，不是 `.ctl`。

`prepare_hstar_file`（1625-2612）逐段读取模板 `.glb`，复制或修改后写入输出。例如：

- 第一段从模板读取 `ntlink/outplot/kstab/...`，只用当前网格重写节点、单元、维数、材料、组数；
- `type_ABC`、`type_problem`、`type_solver`、非线性算法、自由度和时间阶次均从模板读取；
- 单元组、施工期出现/材料替换、接触等部分则由当前网格和 `.ctl` 信息重新生成。

这说明 hstarpre 是**模板变换器 + 几何前处理器 + deck writer**，而不是完整的声明式编译器。

## 3. `.ctl` 本身仍是顺序协议

`.ctl` 看起来有大量可读标签和说明，但主程序并不按标签解析。它经常用固定次数读取文本：

```fortran
do i0=1,11
  read(ctl_unit,*) text
end do
```

或者用首字符 `\` 跳过一段说明，再 `backspace` 到第一条数据记录。`prepare_loa_file`、
`prepare_pre_file`、`prepare_ifs_file`、`prepare_man_file` 又各自从同一个 `ctl_unit` 继续向后消费。

所以 `.ctl` 与求解 deck 具有相同的核心脆弱性：

```
(执行路径, 先前读取位置, 开关状态) → 后续记录布局
```

增加或删除一条说明行就可能让后续 reader 错位。标签提高了人工可读性，但不是结构化语法。

## 4. hstarpre 已经实现的高层生产知识

### 4.1 网格与拓扑

主程序和模块包含：

- 节点带宽优化；
- 2D 边界线和 3D 边界面提取；
- 网格加密；
- 非协调网格插值；
- 自动接触单元；
- 桩、板、薄膜、块体转壳；
- 参数化 RC 隧洞衬砌与钢筋/粘结单元；
- 冷却水管；
- 子模型边界插值；
- 渡槽附加质量/弹簧。

这批功能明显超过当前 Python generator 的能力范围。

### 4.2 几何选择器

`prepare_loa_file`、`prepare_pre_file` 和 `prepare_ifs_file` 重复使用同一种选择模式：

1. 从 `.bon` 读取外边界和内部界面的拓扑；
2. 按单元组或材料组过滤；
3. 用 `axis_ctl + vmin/vmax` 做坐标范围过滤；
4. 计算局部法向；
5. 用 `axis_rot + rotmin/rotmax` 做法向过滤；
6. 将选中节点/边/面展开成 deck 表。

这直接证明“由几何/拓扑规则生成节点表和边表”不是新设想，hstarpre 已经实现过可工作的
原型。新体系应提取并测试其语义，而不是重新从 bbox 预设开始发明。

但现有实现仍依赖绝对容差和轴向区间，且没有显式的命名实体、坐标系、连通分量与覆盖证明；
它是新选择器的算法资产，不是最终 API。

### 4.3 跨文件联合生成与隐藏模板参数

hstarpre 已经把若干分散槽位作为一个功能联合处理：

- 单元组、材料号、施工期 `appear_process`；
- 接触组及接触材料；
- 钢筋/粘结单元的几何与组；
- 流固界面、固体/流体吸收边界；
- 冷却水管的网格、材料、温度边界和附属文件；
- 子模型的网格、插值和边界条件。

但联合并不完整。例如 `fempre.f90:2052-2057` 的 `ikindks/ktan1/ktan2/nlocalbeam` 是从
模板 `.glb` 读取后原样写出，而 `mesh_add_plate_pile_pipe` 又根据 `.ctl` 生成钢筋和粘结单元。
也就是说，一个“钢筋粘结”能力已经被拆在模板参数与 `.ctl` 几何两处，hstarpre 不会证明
两者相容。这正是新 Semantic IR 应用单个 `bond` 对象收拢的关系。

这些联合关系及其断裂位置，都是新 Semantic IR 中 `interface / phase / action` 对象的
主要事实来源。

## 5. producer 与当前 consumer 的已确认对应

### 5.1 `.LOA`

`prepare_loa_file`（2614-3203）先输出一次全局时间曲线、集中荷载和边/面定义，然后在
`do iblks=1,nblks` 内输出每施工块的边荷载、体力、组时间曲线、梁载和板载。

这与当前 HSTAR 的 `external_load_1` 循环外、`external_load_2` 循环内一致。它是
`03-corrections.md` 更正 #3 的独立 producer 侧证据。

### 5.2 `.ifs`

当前 HSTAR 在 `Fem.f90:200-203` 依次调用：

```
stiff_interface_fluid_solid
stiff_absorb_fluid
stiff_absorb_solid
stiff_ifs2006
```

hstarpre `prepare_ifs_file` 按同一顺序输出：

```
nifsgroup
nabsgroup       # 标签名；求解器变量为 nabsfgroup
nabssgroup
ifsnedge
```

这次双向核对推翻了 `01` 原先错误的段顺序，已记入 `03-corrections.md` #5。

### 5.3 `.man` 的已知边界

`prepare_man_file`（5908-5992）只做以下分支：

```fortran
if(type_problem/='Q') then
  read(... ) nincs, cdtest, earthquake_curve
  if(type_ABC=='VIE') read(...) inpcord, earthquake_curve_d, earthquake_curve_v
  if(type_ABC=='MIF') read(...) inpcord, earthquake_curve_MIF
else
  read(...) nincs
endif
```

它没有根据 `type_solver=='EXPLICIT'`、`type_problem=='E'` 或 `type_problem=='W'` 改变布局。
当前 HSTAR consumer 却有这些独立 reader。因此，hstarpre 不能被视为所有当前 `.man` 分支的
权威 writer。

归档的 20 个 `.ctl`/输出实例只观察到 `Q/S + PARDISO`；没有 F/E/W/EXPLICIT/VIE/MIF
样例为这些分支背书。

## 6. 能力证据应如何使用

hstarpre 的价值不是“旧程序能跑，所以直接继续维护”，而是提供四类一手证据：

1. **producer mapping**：工程概念如何联合落到多个 deck 槽位；
2. **几何算法**：如何从网格拓扑导出荷载、约束、接口和插值；
3. **能力清单**：当前 Python 工具链尚未表达的大量功能；
4. **历史版本信号**：writer 与当前 reader 不一致的位置即潜在格式演化点。

每条 hstarpre 映射必须用当前 HSTAR consumer 或一次实验复核。hstarpre 源码本身不能覆盖
当前求解器的全部分支，也不能证明物理正确。

## 7. 对此前结论的影响

| 此前结论 | 纳入 hstarpre 后 |
|---|---|
| deck 规则只存在于 HSTAR reader | 更正为：消费协议在 reader；生产语义还大量存在于 hstarpre |
| 当前 generator 是唯一可复用后端 | 更正为：generator 与 hstarpre 都是能力不完整、版本相关的后端/知识源 |
| 几何选择器需要新建 | 更正为：hstarpre 已有原型，应迁移语义并重写为可测试组件 |
| config 可作为 TOML 的中间表示 | 降级：应建立独立强类型 Semantic IR，吸收两条 producer 的能力 |
| 只扫描 HSTAR 就能生成 schema | 降级：还需 producer mapping；高级物理 schema 不能由 READ 自动生成 |
