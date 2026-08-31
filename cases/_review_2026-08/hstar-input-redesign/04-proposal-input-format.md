# 提案：现代化输入格式

> 这是提案，不是事实。依据是 `01`/`02` 两份事实文档。示例见 `examples/*.toml`。
>
> **2026-08-28 补充**：纳入 hstarpre 后，本文的 tagged union、物理命名、几何导出和
> 单向真值原则仍成立；但“直接复用 generator.py”“config.json 作为中间表示”以及
> “dispatcher-map 直接生成高级 schema”需要按 `08-revised-architecture.md` 修订。

## 0. 目标与约束

目标（使用者提出）：**优美、现代、标准的输入。**手工填写不应该像现在这样痛苦。

约束（本会话查实）：输入的真实结构是

```
(dispatch 路径, 开关状态) → 记录布局 × 槽位语义
```

**这两者不冲突。**扁平的 200 参数表既不优美也不安全；
把 dispatch 显式化的格式**两者都能拿到**——因为它消灭了
"这 200 个字段里哪些跟我有关"这个问题，而这正是当前痛苦的来源。

## 1. 七条设计原则

### 原则 1 · 和类型，不是扁平记录（最重要的一条）

输入本质上是 tagged union：

```
analysis = static | modal | spectrum | dynamic | transient | frequency
  dynamic.boundary = fixed | viscoelastic | mif
```

**每个变体只携带自己的字段。**

```toml
[analysis.dynamic.boundary]
kind = "viscoelastic"
[analysis.dynamic.boundary.incident]      # 只在 viscoelastic 分支存在
displacement = { x = "eq_d.dat" }
```

```toml
[analysis.dynamic.boundary]
kind = "fixed"
[analysis.dynamic.boundary.excitation]    # 只在 fixed 分支存在
acceleration = { x = "eq.dat" }
```

**`excitation.acceleration` 在 VIE 分支下根本不存在，所以双重激励这个错误无法表达。**
不是"检查出来"，是**写不出来**。语义漂移从"要靠检查抓"变成"结构上不可能"。

这一条同时解决了优美问题：写一个 VIE 算例时，你面对的是 6 个字段，
不是 200 个里挑 6 个。

### 原则 2 · 物理命名，不是槽位命名

| deck | 新格式 |
|---|---|
| `order_time` 第 2 位 = 2 | `mass = "consistent"` |
| `ikindks = 5` | `[[bond]] model = "steel_concrete"` |
| `index = 25` | `element = "truss"` |
| `cdbound = 2` | `absorbing.bottom` |
| `Icaddmass` | `added_mass.model = "westergaard"` |
| `earthquake_curve` 槽位=方向 | `acceleration = { x = "..." }` |

命名应该说工程师的意思，不是 Fortran 数组下标。**这是"优美"的主要来源。**

### 原则 3 · 几何导出，不是节点表

人不应该手写 3672 个节点号或 85 条吸收边。

```toml
[[constraint]]
where = "y_min"; fix = ["uy"]
```

节点集**计算得到，并且被校验**：`y_min` 上的边必须全部落在 `y_min` 上、
覆盖必须完整。这既省掉最痛苦的手工劳动，又顺手挡住了本会话查实的两类 VIE 边界错误
（一个漏 61 段，一个把 30 条内部竖直边标成底边界）。

`where` 需要支持命名区域（`region = "dam"`）与几何谓词，而不只是 bbox 面——
这是这一条的主要工程量。

### 原则 4 · 无损 + 逃生舱（不可协商）

**任何 deck 能表达的东西，新格式必须能表达。**否则就是重演本会话所有的失败：
生成器"为了简单"隐藏了 `ikindks` / `nabsfgroup` / `order_time`，
每一次的产物都是语法合法、求解器接受、物理不对。

所以必须有逃生舱：

```toml
[raw.glb]
after = "ftcrack"
lines = ["3.270E+07  3.270E+07  1  0  3"]
```

用到逃生舱要**告警**——它是 schema 缺口的探测器，不是长期方案。
每一次使用都应该转成一个 schema 待办。

### 原则 5 · 单向真值：格式 → deck，deck 是构建产物

`1.glb` 等六个文件降级为**构建产物**，像 `.o` 文件一样：不手改、不入库、可重建。

**绝不双向同步。**双向同步意味着两个真值来源，必然漂移。
（这正是 `Easy_HSTAR` 的第二个负担：两个求解器要保持同步。）

需要读旧算例时走一次性的 `import`，产出新格式后**以新格式为准**。

### 原则 6 · dispatcher 生成 Deck ABI，约束 schema 覆盖

这是让格式**不会腐烂**的关键。

```text
求解器源码 ──extract_dispatch.py──▶ Deck ABI / dispatcher map
                                           │
hstarpre producer mapping ─────────────────┼──▶ schema coverage check
                                           │
人工设计的物理 Semantic Schema ────────────┘
```

求解器改了 → Deck ABI 变了 → schema coverage 失败 → **你知道了**。

高级 CAE schema 不能由 READ/CALL 正则直接生成：源码变量不会自动变成“粘结”“入射波”或
“一致质量矩阵”等工程对象，跨字段、单位和几何规则也不属于 JSON Schema。自动提取器负责
指出 consumer 新增或变化了哪些槽位；物理映射由 Semantic IR 明确定义，并由覆盖检查约束。

手写 schema 做不到这一点。`docs/capability-inventory.md` 第四轴用散文写下
"`ikindks` 只能手改"，一天后照样撞上去——**散文不会失败，检查才会。**

### 原则 7 · 求解器基线绑定

```toml
[case]
solver = "hstar-yl@26ffc9b"
```

schema 与求解器 commit 绑定。这不是形式主义：本会话已经确认存在**两套求解器基线**，
且 5 个算例疑似是**旧格式**（`06-open-questions.md` #1）。
没有基线声明，"这个 deck 能不能跑"这个问题就没有确定答案。

## 2. 格式选择

**TOML**（沿用 `Easy_HSTAR` 的选择），配 JSON Schema 做校验。

理由：人写友好、注释是一等公民（deck 里 `!` 只能靠"读到即弃"苟活）、
表数组 `[[group]]` 天然适合重复段、生态成熟。

和类型在 TOML 里用 `kind = "..."` + 子表达成，配合 JSON Schema 的 `oneOf`
可以做到"选错分支立刻报错，且错误信息指到行"。

## 3. 与现有资产的关系

**不重写求解器。不迁移任何 deck。**

| 现有资产 | 在新体系里的角色 |
|---|---|
| `generator.py` | 兼容后端；必须置于 strict adapter 后，禁止默认降级 |
| `config.json` | 旧中间表示/迁移输入，不再作为新体系的唯一语义 IR |
| `hstarpre/fempre.f90` | 历史 producer 与几何算法知识源；不是新格式前端 |
| 往返矩阵 | **验收判据**：新格式必须能无损往返 21 个既有 deck |
| `harness/consistency.py` | 原则 3 的校验落点 |
| 三轴门控 | 不变 |

**关键判断：`Easy_HSTAR` 的初衷（现代化输入）可以在已验证的 YL 主线上单独实现，
不需要重写求解器。**那次尝试之所以越搞越复杂，是把两件独立的事绑在了一起：
新输入格式 + 30k 行求解器重写。解绑之后，前者是几周的工作，后者是几年的工作。

新发现进一步说明，工程知识至少分布在三个位置：HSTAR consumer、hstarpre producer、
Python generator/importer。新体系应先汇总为强类型语义 IR，再选择后端，不能把其中任一
现有程序直接提升为唯一真值。

## 4. 分期

| 期 | 做什么 | 验收 |
|---|---|---|
| **1** | dispatcher 地图 → Deck ABI + schema coverage | 当前 reader 记录全有稳定 ID；未映射能力显式列出 |
| **2** | TOML → Semantic IR → Deck Plan 前端 + 原则 3 的几何选择器 | 往返矩阵：TOML 重建的 deck 与原 deck 等价 |
| **3** | 语义漂移表 → 跨字段校验 | 能拦住 VIE 双重激励、缺 `nabsfgroup`、`order_time` 误设 |
| **4** | `import`：旧 deck → TOML（一次性） | 21 个算例全部转出，逃生舱使用量即 schema 缺口清单 |
| **5** | 逃生舱清零 | 每条转成 schema 字段 |

**第 1 期就有独立价值**：即使不换格式，Deck ABI 也能对 reader 变化和 writer 覆盖缺口
给出机器可失败的报告。它不能单独证明 21 个 deck 物理正确；五个可疑 `.LOA` 仍须由当前
solver 实跑和 read trace 判定。

## 5. 这个设计解决了哪些已发生的错误

| 已发生的错误 | 新格式下 |
|---|---|
| VIE 填了 `earthquake_curve` → 双重激励 | 该字段在 VIE 分支**不存在** |
| `nabsfgroup=0` → 库水面全反射 | 有 W 场组而缺 `absorbing.fluid` → **schema 报错** |
| `order_time=[0,0]` → 动力算例按准静态求解 | `mass = "consistent"`，动力分析下**必填** |
| `ikindks=3` 而非 5 → RC 粘结失效 | `[[bond]]` 一个对象决定三处槽位 |
| 30 条吸收边错位 / 61 段未覆盖 | 边由几何导出并校验，手写不了也就错不了 |
| `elem_index 25→1` 钢桁架退化 | `element = "truss"` |

六条里有五条是"结构上无法表达"，不是"靠检查抓住"。**这是和类型的红利。**
