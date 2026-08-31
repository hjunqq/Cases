# 探针报告：逐层剥洋葱，旧格式到底差在哪（预先登记）

> 第三个预先登记探针。材料：`probe/old-format-peel/`
> （predictions.json + sha256 `c10b786f…` + judge.py + verdict.json）。

## 方法（登记在先）

```
跑 → 从求解器回显的最后一条标签定位失败记录
   → 把标签名与源码 READ 变量名对齐，源码有而标签没有的插入 0
   → 再跑。最多 8 轮。
```

补丁规则是**标签对齐补零**，登记时明确标注"标签顺序与源码变量顺序一致"是假设。
分类携带**文件名 + 记录标签**——这是探针 2 的教训（`read_error` 太粗，让 P1 因错误的原因通过）。

## 判决

| | 预测 | 判决 |
|---|---|---|
| **C0** | 对照组 train01 completed | **PASS** |
| P1 | 补齐 NINIT 后失败点不再是 NINIT | **PASS** |
| P2 | 第 1 轮失败点仍在 `1.glb` | **PASS** |
| P3 | `1.glb` 需补齐的记录 ≥ 2 条 | **PASS**（实为 **4** 条） |
| P4 | 8 轮内失败点至少一次落在 `1.loa` | **FALSIFIED**（落在 `1.ftr`） |
| P5 | 8 轮内不会 completed | **PASS** |
| P6 | 另外 4 个 deck 第 0 轮失败点与目标完全相同 | **PASS** |

## 主结果：`.glb` 旧格式差 4 条记录、14 个字段

逐轮剥出来的完整清单：

| 轮 | 记录 | deck 供 → 源码需 | 缺的字段 |
|---|---|---|---|
| 0 | `NINIT KINIT NBLKS …` | 11 → **19** | `winit` `block_stab` `nbackf` `nbspring` `ebody` `outind` `nbackdt` `ninistn` |
| 1 | `TYPE_PROBLEM TYPE_SOLVER …` | 7 → **11** | `state_change` `bparameter` `balgor` `upliftin` |
| 2 | `NMASS NSMAT NHMAT …` | 10 → **11** | `ecwpipe` |
| 3 | `NTSMAT NTHMAT KSTAT …` | 6 → **7** | `submodel` |

补完这 4 条，求解器**完整读过了 `1.glb`**，失败点转到 **`1.ftr`**——另一个文件，
超出本探针登记的补丁范围（`UNIT_OF` 只覆盖 6 个主 deck 文件）。

### 这说明什么

1. **`.glb` 的格式演化是"只加不改"的追加式**：14 个字段全部是在既有记录尾部或中部
   插入的新开关（子模型、反演、冷却水管、上浮、状态变化…）。
2. **旧 deck 可以机械迁移。**标签对齐补零这条规则，4 条记录一次成功，无需人工判断每个字段。
   这是 `08-revised-architecture.md` 里 `legacy_import` 路径的可行性证据。
3. **P6 PASS**：5 个 deck 在第 0 轮的失败点完全相同 → 它们是同一批、同一版本。
4. **`.LOA` 仍未够着**，但原因变了：不是 `.glb` 拦着，是 `.ftr` 拦着。
   这是新信息，`06-open-questions.md` #1 相应更新。

### 对 Deck ABI 的直接含义

`08` 提出 Deck ABI 要带 `reader / record / slot / guard / loop / 版本`。
本探针给出了**版本这一维的实证形态**：同一条记录在不同年代有不同 arity，
而 deck 里的人可读标签**恰好记录了它当年的 arity**。

> 标签行不只是给人看的——它是**事实上的记录版本戳**。
> 一个按标签对齐的解码器，可以自动判定一条记录属于哪个年代。

这比"给每条记录人工编版本号"便宜得多，建议写进 Deck ABI v1。

## 探针自身：3 处仪器 bug，全是同一类

| | bug | 后果 |
|---|---|---|
| 1 | `names()` 没去 `!` 尾注 | 把注释里的词当变量名，判"无需插入" |
| 2 | `patch_record` 回找原行的比较没去 `!` | 找不到行，判"无需插入" |
| 3 | 归一化收尾少一个 `.strip()` | 引号内尾空格导致标签匹配失败 |

**三处都是 deck 文本归一化。**加上前两个探针，本项目至今：

```
import_glb._Deck._expand          实现对了
man-readers/judge.py              忘了 !            ← 第 2 次
old-format-peel/judge.py names()  忘了 !            ← 第 3 次
old-format-peel/judge.py key()    忘了 ! + 尾空格   ← 第 4、5 次
```

**同一条规则，我在五个地方各写错一次。**

这是整个项目里**"必须只有一个共享 decoder"最强的单条论据**——
比任何架构论证都直接。它同时说明 `10-roadmap.md` 里 P0-1（独立 decoder 独立成件）
不是锦上添花，是止血。

## 一个诚实的方法论区分

三个探针里我改过两次东西，性质完全不同：

| | 动作 | 是否合规 |
|---|---|---|
| 探针 2 | 想把判据从 `==` 改成 `>=` | **不合规**——改判据 = 看到结果后决定什么算对。P6 保留 FALSIFIED |
| 探针 1、3 | 修解析 bug 后重跑 | **合规**——仪器坏了，登记的判据根本没被真正测量过 |

区别是：**改判据改变"什么算成功"；修仪器让不变的判据得以被测量。**
前者摧毁预先登记的意义，后者是它的前提。

本探针 P4 的 FALSIFIED 是在仪器修好、连续推进 4 轮之后得到的，属于真实数据结论。

## 复算

```bash
cd probe/old-format-peel
sha256sum -c predictions.sha256
python3 judge.py     # 约 1 分钟，全部在 /tmp 下，cases/ 只读
```
