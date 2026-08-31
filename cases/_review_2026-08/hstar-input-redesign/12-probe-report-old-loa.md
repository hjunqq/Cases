# 探针报告：5 个可疑 deck 是否旧格式（open #1，预先登记）

> 第二个预先登记探针。这次引入了"跑求解器"这一维——有副作用、慢、结果不可预知。
> 材料：`probe/old-loa/`（predictions.json + sha256 `cc967ba1…` + judge.py + verdict.json）。

## 判决（按登记结果，不追认）

| | 预测 | 判决 |
|---|---|---|
| **C0** | 对照组 train01 completed | **PASS**（0.2s，713106 B）→ 仪器可信 |
| P1 | 5 个中至少 1 个 read_error | **PASS** ⚠ 见下 |
| P2 | 5 个全部不是 completed | **PASS** |
| P3 | 5 个分类结果不全相同 | **FALSIFIED**（清一色 read_error） |
| P4 | completed 者结果字节数与归档不同 | **N/A**（无 completed） |
| P5 | 至少一个失败案例 `.chk` 含全局数据阶段输出 | **FALSIFIED**（`.chk` 全为 0 字节） |

## 登记的问题：**无法回答**

5 个 deck 全部在 **0.1 秒**内失败，失败点在 **`1.glb`**：

```
forrtl: severe (64): input conversion error, unit 1, file .../1.glb
```

**`.LOA` 从未被读到。**关于"每 BLKS 一份时间曲线表是不是旧格式"这个问题，
本探针**够不着**，只能判为 inconclusive。

## 但撞到了真正的东西：`.glb` 的 NINIT 记录也有两种格式

```
源码 Global.f90:728 读 19 项：
  ninit, kinit, winit, nblks, nlinks, nonsym, outinp, outintr, outintw,
  neuman, equvs, type_ABC, block_stab, nbackf, nbspring, ebody, outind,
  nbackdT, ninistn

train01（当前格式）  0 0 0 2 0 0 0 0 0 0 0 FIX 0 0 0 0 0 0 0     19 项 ✓
5 个旧 deck          0 0   2 0 0 0 0 0 0 0 FIX                   11 项 ✗
                         ↑缺 winit                ↑缺尾部 7 项
```

list-directed READ 取满 11 项后**跨记录继续读**，撞上非数字文本，转换失败。

**所以"这 5 个是旧格式"这个判断成立，但机制与登记假设不同：
不兼容出现在 `.glb`，且先于 `.LOA` 发生。**

这与 `09-facts-verification.md` §3 发现的 `.glb` 头部两种方言（`train_temp_creep`
缺 `npoinb`）指向同一件事：**`.glb` 的旧格式是系统性的，不止一条记录。**

## 本次最重要的方法论教训：**PASS 也可能是错的**

P1 判 PASS——"5 个中至少 1 个 read_error"，字面为真。
**但那个 read_error 发生在 `.glb`，而假设说的是 `.LOA`。**

> **P1 是因为错误的原因而通过的。**

这比误判 FALSIFIED 危险得多，因为**没有人会去调查一个 PASS**。
如果只看判决表（C0/P1/P2 三个 PASS），会得出"假设得到支持"的结论——错的。

**可推广的规则**：

> 结局分类必须**细到只有假设成立时才可能 PASS**。
> 本例中 `read_error` 这个类别太粗——它没有记录**是哪个文件失败的**。
> 分类应为 `read_error@1.glb` / `read_error@1.loa` / …，那样 P1 会正确地判 FALSIFIED。

这条已经可以写进探针设计规范。

## 顺带核过并排除的假设

`1.loa`（小写）与 `1.LOA`（大写）同时存在，而求解器
`open(loadunit, file=probn//'.loa')` 读的是小写——怀疑此前全部 `.LOA` 分析读错了文件。
**逐一 `cmp` 核对：凡两者都存在的算例，内容完全相同。**假设排除。
（`train_temp_creep` 只有 `1.loa`，这解释了往返矩阵里它 `1.LOA` 那格的"—"。）

## 探针自身的缺陷（本次两处）

1. **分类粒度不足**（上文），导致 P1 假通过。
2. **P5 的观测位置错了**：我去 `.chk` 找阶段信息，但失败发生在 `.chk` 落盘之前，
   阶段标签打在 stdout 上。P5 因此判 FALSIFIED——**判决按登记保留**，
   但它证伪的是我的观测方法，不是被测对象。

比探针 1 少（3 → 2 处），但性质更严重：探针 1 的错误制造**假否定**，
探针 2 的错误制造**假肯定**。

## 对 open #1 的处置

- **已确认**：5 个 deck 是旧格式，`.glb` NINIT 记录只有 11 项（当前需 19 项）。
- **仍未答**：它们的 `.LOA` 是否也是旧格式。
- **下一个探针**（需新的预先登记）：把 NINIT 记录补齐到 19 项后重跑。
  若随后在 `.loa` 失败，则 `.LOA` 旧格式假设得证；若跑通，则该假设被推翻。
  这是一次**便宜且判据干净**的实验。

## 复算

```bash
cd probe/old-loa
sha256sum -c predictions.sha256
python3 judge.py            # 约 1 分钟，全部在 /tmp 下运行，不触碰 cases/
```
