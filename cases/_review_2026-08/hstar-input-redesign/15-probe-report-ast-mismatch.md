# 探针报告：AST 解析器的 40 处构造失配（open #9，预先登记）

> 第四个预先登记探针。材料：`probe/ast-mismatch/`
> （predictions.json + sha256 `b71e80c0…` + baseline.json + judge.py + verdict.json）。

## 判决：6/6 —— 首个全部成立的探针

| | 预测 | 判决 |
|---|---|---|
| P1 | 40 处可归入 ≤5 种语法形态 | **PASS**（3 种） |
| P2 | 至少一种与 goto / 语句标号相关 | **PASS** |
| P3 | 没有一处落在 5 项验收覆盖的子程序内 | **PASS** |
| P4 | 修复后失配降到 0 | **PASS** |
| P5 | 修复后 verify_ast 仍 5/5 | **PASS** |
| P6 | 修复后 Deck ABI 条数变化 | **PASS**（909 → **1012**） |

## 三种语法形态

**A · 老式带标号 DO**（8 个文件共 202 处）

```fortran
do 16 k=i,m
  a(k,i)=scale*a(k,i)
16 continue          ← 终止语句带标号，没有 end do
```

终止语句**未必是 `continue`**：`Stiff.f90:8112` 是 `DO 90 I=1,3` / `90 SIGU(I)=…`。
这是失配的最大来源。

**B · 具名构造**

```fortran
material_select: select case(material)
...
end select  material_select
```

`RE_IF_THEN` 和 `RE_DO` 我都允许了 `name:` 前缀，**唯独 `RE_SELECT` 漏了**。

**C · 嵌套带标号 DO 共享终止标号**

```fortran
DO 311 I=1,4
DO 311 J=1,4
311     DEP(I,J)=0.0     ← 一条语句同时终止两层
```

修法：终止时**不消费该行**，让每一层都看到并逐层退栈，最后由外层序列跳过它。

## 结果

```
闭合率     99.46% → 100.000%   （7445 个 end，失配 0）
AST READ   1203 → 1306
Deck ABI    909 → 1012
  其中 .mat  11 → 114          ← 材料 reader 的子树此前被严重截断
```

`.mat` 从 11 涨到 114 是最大的一处修正：材料读取逻辑几乎整段落在带标号 DO 之后，
此前被吞掉了。这也解释了为什么 `import_glb.parse_mat` 一直靠手写规则拼凑——
它面对的复杂度比我们以为的高一个数量级。

## P3 值得单独说

**40 处失配没有一处落在 5 项验收覆盖的子程序里。**

这解释了为什么解析器带着 0.54% 的失配仍能 5/5 通过验收——
**那五处恰好都在干净区域**。反过来说：

> **此前的 5/5 通过，不构成对失配区域的任何证据。**

P3 是预先登记来专门测这一点的，它通过了，意味着"验收通过但树是错的"这个风险
当时**确实存在**。这条经验应写进验收设计：**验收覆盖面必须与已知缺陷区域交叉核对**，
否则通过率是自我安慰。

## 复算

```bash
cd probe/ast-mismatch
sha256sum -c predictions.sha256
python3 judge.py
```
