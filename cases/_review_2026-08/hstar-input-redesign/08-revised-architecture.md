# 综合提案：纳入 hstarpre 后的 HSTAR 输入架构

> 2026-08-28。本文是提案，不是事实。它综合 `01/02/03/03b/07`，并取代 `04/05` 中
> 关于“直接复用 generator”“config 作为唯一 IR”“dispatcher 直接生成高级 schema”的部分。

## 0. 架构判断

HSTAR 当前不是一条输入链，而是三个知识岛：

```
                    ┌─ HSTAR reader：消费协议、运行时分支
工程意图 ──────────┼─ hstarpre：历史生产语义、几何与网格算法
                    └─ Python generator/importer：当前 Web 生产与迁移能力
```

正确目标不是给其中某一个程序换 TOML 外壳，而是建立一个新的强类型 CAE Semantic IR，
让三处知识逐步汇合，并由当前 HSTAR consumer 做最终协议裁判。

## 1. 推荐的编译流水线

```
case.toml
   │  parse（保留文件/行/列与“缺失 vs 显式空值”）
   ▼
Authoring AST
   │  单位、坐标系、名称、引用归一化
   ▼
HSTAR Semantic IR  ← 唯一工程真值
   │
   ├─ capability check（solver profile / reader path）
   ├─ mesh & topology resolution（sets / surfaces / interfaces）
   ├─ phase dependency check（施工、预载、动力、重启）
   └─ physics invariants（DOF、质量、激励、材料/单元兼容）
   ▼
Deck Plan（reader_id + record_id + typed slots）
   │  encode
   ▼
六类 deck + manifest + source map
   │  independent decode
   ▼
Read-back IR ── compare ── Semantic IR
   │
   ▼
solver run → numerical checks → physics V&V
```

### 为什么必须有 Deck Plan

直接让语义对象拼文本，会再次把 dispatcher 隐藏在字符串生成器里。Deck Plan 应显式包含：

- 目标 deck；
- reader 与记录 ID；
- 生效守卫；
- 循环上下文/施工块；
- 槽位类型与来源 IR path；
- 编码版本。

它既是 writer 的输入，也是 read-back diff 和源码覆盖率的共同坐标系。

## 2. Semantic IR 的顶层对象

不建议只保留一个 `analysis.kind`。真实工程包含施工、静力预载、动力续算、重启和反演，
应建模为阶段图：

```toml
[[phase]]
id = "gravity"
kind = "static"
activate = ["foundation", "dam"]
actions = ["self_weight"]

[[phase]]
id = "earthquake"
kind = "dynamic"
initial_state = { from = "gravity" }
boundary = "far_field"
actions = ["incident_wave"]
```

建议 IR 至少包含：

| 对象 | 内容 |
|---|---|
| model | 网格、坐标系、单位制 |
| materials | 物理材料模型及有量纲参数 |
| formulations | 单元公式、场、质量矩阵、截面 |
| regions/sets | 命名节点、边、面、体及选择规则 |
| interfaces | 接触、粘结、FSI、吸收边界、插值 |
| phases | 分期、分析类型、激活/移除、初始状态依赖 |
| actions | 约束、体力、压力、温度、入射波、基底运动 |
| numerics | 非线性算法、线性求解器、步长、容差 |
| outputs | 场输出、历史点、反力、能量与审计量 |

材料、单元公式和连接必须分开。例如 `concrete_damage` 材料不应隐式决定“钢筋粘结 reader
一定被调用”；`bond` 是连接对象，应显式引用 host/embedded group，并联合生成所需槽位。

## 3. 四种 schema，不要混成一张 JSON Schema

### A. Authoring schema

负责字段类型、tagged union、必填项、引用形状和禁止未知字段。TOML + JSON Schema 可承担
其中一部分。

### B. Semantic rules

负责跨字段和物理约束，例如：

- VIE 分支禁止 fixed-base acceleration；
- dynamic phase 必须声明质量模型；
- bond 两侧单元/自由度必须兼容；
- restart 引用的前序 phase 必须产生所需状态；
- 量纲和坐标系必须一致。

这些应写成可执行代码，不能指望 JSON Schema 完成。

### C. Deck ABI

由当前 HSTAR consumer 提取并人工审定：reader、record、slot、guard、loop、版本。dispatcher
扫描器适合生成这一层的变化报告和覆盖率，不能直接命名高级 CAE 概念。

### D. Capability profile

针对具体 solver build 声明哪些 Semantic IR 组合已有 writer + reader + 验证证据：

```text
dynamic + VIE + acoustic fluid
  reader: known
  writer: native-v1
  roundtrip: pass
  numerical probe: pass
  physics benchmark: pending
```

只有四层都通过，才允许标记为生产可用。

## 4. hstarpre 的正确定位

### 应复用的内容

- `.bon` 边界/内部界面拓扑提取思想；
- group/material + bbox + normal 的组合选择语义；
- 接触、钢筋/粘结、冷却水管、薄膜、子模型的生产路径；其中被拆在模板与 `.ctl`
  两侧的参数要显式标记，不能误当成已完成的高层映射；
- 施工期出现/材料替换关系；
- `.ctl → deck` 示例作为 producer golden corpus。

### 不应直接继承的内容

- 固定行数跳过说明文本的 `.ctl` parser；
- `model1/1.glb` 模板作为隐藏默认来源；
- Windows 路径和 DFLIB 运行时；
- writer 与当前 consumer 未经检查的分支；
- 大型共享状态主程序和读写交织的控制流。

推荐采用“行为迁移”，不是“代码嵌入”：先为每个 hstarpre 功能建立输入/输出夹具和映射表，
再把算法重写为纯函数、类型化、可单测的组件。

## 5. 现有 Python generator 的正确定位

`generator.py` 已证明在已覆盖配置上可以精确输出，但当前仍有未知单元回退 Q4、物理默认值、
材料分支缺失后退化等行为。迁移期应增加 strict adapter：

1. Semantic IR 编译时填全所有物理字段；
2. 禁止 generator 自行补材料、边界、分析类型和单元类型；
3. 未识别能力立即返回 typed error；
4. 每一个允许的数值默认值写入 build manifest；
5. 生成后必须由独立 decoder 回读。

长期可把六个 `_gen_*` 逐个替换为 Deck Plan encoder，而不是一次重写。

## 6. 几何/拓扑选择器 v2

hstarpre 已证明几何导出路线可行，但新实现应按以下优先级选择：

1. CAD/网格命名实体；
2. 域之间的拓扑邻接；
3. 外边界连通分量；
4. 面法向与局部坐标系；
5. 尺度相关的几何谓词/bbox。

每次解析都应返回“选择证明”：候选数、排除原因、覆盖率、法向范围、连通分量和最终实体 ID。
吸收边界不仅检查数量，还应检查外边界归属、方向、连续覆盖、固/液域相邻关系和未覆盖段。

## 7. 单位、坐标系和激励约定

新格式必须增加：

- 项目单位制或带单位数值；
- 全局/局部坐标系；
- 压力正负号与面法向约定；
- 重力方向；
- 地震输入是绝对、相对还是基底运动；
- 位移/速度/加速度曲线的量纲；
- 时间曲线插值与外推规则。

这些属于 Semantic IR，不应在 deck encoder 中靠注释约定。

## 8. 无损与 raw 的修订

“任何 deck 都能表达”应拆成三级：

| 级别 | 定义 |
|---|---|
| archive-lossless | 原字节和依赖模板可恢复 |
| reader-lossless | 当前 solver 读取到的记录/值等价 |
| semantic-native | 全部映射到已验证 Semantic IR |

raw 逃生舱只允许在 `legacy_import` 使用，锚点必须是 `reader_id + record_id`，不能是
`after = "ftcrack"` 文本。含 raw 的项目标记为 `IMPORTED_OPAQUE`，不得声称完整语义验证。

## 9. 验证与证据等级

### 编译门控

1. authoring validation；
2. semantic/units validation；
3. topology resolution；
4. capability check；
5. Deck Plan coverage；
6. encode → independent decode → IR compare。

### 数值门控

- solver 是否完成；
- 收敛历史与残差；
- 质量/刚度/反力等不变量；
- 能量输入、耗散与吸收；
- 模态正交性；
- 重启连续性。

### 物理 V&V

- patch test；
- 解析解；
- 网格收敛率；
- 互易性；
- 专项标准算例。

消融对不能只用“结果是否不同”。每个 probe 必须声明预期关系，如
`must_change`、`must_preserve`、`must_reduce(reflected_energy)` 及容差。

## 10. 更新后的实施顺序

### P0：建立兼容事实

1. 修正 `.ifs` 顺序文档（已完成）；
2. 当前 solver 实跑五个可疑旧 `.LOA`；
3. VIE 双重激励消融；
4. 建立 hstarpre writer × 当前 HSTAR reader 的组合矩阵；
5. 选择一个 Q 和一个 S 算例重放 hstarpre，固化 exe/template/ctl/output hash。

### P1：建立中间模型

1. Deck ABI v1；
2. Semantic IR v1；
3. Deck Plan 与 source map；
4. strict generator adapter；
5. 独立 decoder。

首批只做三条纵切：线弹性静力、固定边界动力、VIE 动力。每条必须完整通过编译、回读、
数值探针和至少一个物理 benchmark。

### P2：迁移 hstarpre 的差异能力

按价值和耦合风险排序：

1. 通用拓扑/几何选择器；
2. 施工阶段与激活；
3. RC steel/bond；
4. FSI/吸收边界；
5. 接触与薄层；
6. 冷却水管；
7. 子模型和反演辅助文件。

每迁移一项，就新增一个 capability profile、producer golden、roundtrip test 和 physics probe。

## 11. 最终结论

hstarpre 的发现加强了“新输入格式值得做”的结论，但改变了实现方式：

> 新系统不应是一个更漂亮的 deck 模板，也不应是 hstarpre 的 TOML 翻版；它应是吸收
> hstarpre 生产语义、以当前 HSTAR reader 为协议裁判、用强类型 CAE IR 连接二者的输入编译器。

这样才能同时保留历史程序中已经积累的工程能力，并消除模板、位置流、魔数和静默默认造成的
系统性风险。
