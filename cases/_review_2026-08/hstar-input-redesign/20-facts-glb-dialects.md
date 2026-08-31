# 事实五：`.glb` 头部记录的两种方言，及按标签对齐的修法

> 2026-08-28。回答 `06-open-questions.md` #7 / `09-facts-verification.md` §3。
> 全部结论可复算：源码行号可 grep，数字可用本文件末尾的命令重跑。

## 0. 一句话

`.glb` 第一条记录存在**两种字段序**；`import_glb.parse_glb` 按位置取 `vals[2]`/`vals[3]`
只对其中一种成立。已改为**按标签行的字段名对齐**取值。89 个算例中恰好 1 个的解析结果
发生变化（`train_temp_creep`，从垃圾变正确），其余 88 个逐值不变。

顺带查实：**`train_temp_creep/1.glb` 当前求解器根本读不了**——第一条 READ 就
`forrtl: severe (59)`。它此前在往返矩阵里显示为 MISSING，是两层错误叠加。

## 1. 求解器侧：这条 READ 要 15 项

```
hstarYLOrig/HSTAR/Global.f90:677
    read(gunit,*)npoin,npoinb,nelem,ndimn,nmats,ngroup,ntlink,outplot,kstab, &
                 mat_curve,meshc,rmesh,level_set_problem,ljdp,stab_matde
```

- 全仓只有这一处读 `.glb` 头（`grep -rn npoinb hstarYLOrig/HSTAR/` 只命中 3 行：
  声明 151、READ 677、紧随其后的 PRINT 678）。
- 因此 **`npoinb` 在当前求解器里被读进来后从未被使用**——正是这个死字段
  让按位置解析在两种方言之间对不齐。
- 这是 list-directed READ：**它会跨记录继续读，直到 15 项凑满**（`deck_text.py` 规则 1）。
  少给字段不会截断，只会把下一行吃进来。

## 2. 两种方言的完整字段序对照

| # | 方言 A（88/89 个算例 + 全部 40 个 hstarpre 归档算例） | 方言 B（`train_temp_creep`，1 个） |
|---:|---|---|
| 1 | NPOIN | NPOIN |
| 2 | **npoinb** | — *(缺)* |
| 3 | NELEM | NELEM |
| 4 | NDIMN | NDIMN |
| 5 | NMATS | NMATS |
| 6 | NGROUP | NGROUP |
| 7 | NTLINK | NTLINK |
| 8 | outplot | outplot |
| 9 | KSTAB | KSTAB |
| 10 | MAT_curve | MAT_curve |
| 11 | meshc | meshc |
| 12 | rmesh | rmesh |
| 13 | **level_set_problem** | — *(缺)* |
| 14 | **ljdp** | — *(缺)* |
| 15 | **stab_matde** | — *(缺)* |

所以 **方言 B ＝ 方言 A 去掉 `npoinb` 与尾部 3 个字段 ＝ 11 项**。
`09-facts-verification.md` §3 只指出了缺 `npoinb`；尾部也短这一半是本次补上的。

实样：

```
方言 A  cases/cases/train01_gravdam_static/1.glb:1-2
NPOIN npoinb NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh level_set ljdp stab_matde
  1705  1705  1600  2  2  2  0  GIDR  0.0  0  0  0  0  0  99999

方言 B  cases/cases/train_temp_creep/1.glb:1-2
 'NPOIN  NELEM  NDIMN  NMATS  NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh'
   5628   4720    3      1      1      0     GIDB       0       0       0       0
```

### 2.1 方言 B 求解器直接拒收（实测）

把 `cases/cases/train_temp_creep/` 原样拷到临时目录跑当前 `hstar`：

```
 NPOIN  NELEM  NDIMN  NMATS  NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh
forrtl: severe (59): list-directed I/O syntax error, unit 1, file .../1.glb
exit code 59
```

按第 1 节的槽位映射，读到第 7 项 `ntlink`（整型）时拿到的是 `GIDB`，正好在此处炸。
**方言 B 是历史格式，不是当前求解器的合法输入。**
往返生成出的方言 A 版本则读得过头部（`npoin=5628 npoinb=5628 nelem=4720 ndimn=3`
逐项正确），失败点后移到别处（rc 174，超出本题范围）。

`_archive/hstarpre` 的 40 个 `1.glb` 全部是方言 A（7 种排版变体，无一缺 `npoinb`），
所以方言 B 不是 hstarpre 的产物。

### 2.2 标签行的可信范围（重要限制）

`13-probe-report-old-format-peel.md` 说"标签行＝记录的版本戳"。这条成立，但只对
**被标注到的前缀**成立。全部 89 个 `.glb` 的标签数 vs 值数：

| 标签数 | 值数 | 算例数 | 含义 |
|---:|---:|---:|---|
| 15 | 15 | 75 | 全标注 |
| 12 | 15 | 11 | 尾部 3 项存在但**没写标签** |
| 9 | 15 | 2 | 尾部 6 项存在但没写标签（`freq`/`static`） |
| 11 | 11 | 1 | 方言 B：尾部**真的不存在** |

判据：**标签数 < 值数 ⇒ 只是标签写少了；标签数 == 值数 ⇒ 字段序如实**。
仅靠标签名判断"某字段不存在"会误判 13 个算例；两个计数一起看才行。
本次修法只用标签对齐取**前 6 个字段**（`npoin/nelem/ndimn/nmats/ngroup` + `nblks`），
这 6 个在两种方言里都被标注，落在可信前缀内。

## 3. 修法

`fem-chat/skills/import_glb.py`，新增三个模块级函数，头部与 NBLKS 两处改为调用它们：

- `_labels(line)` — 把标签行切成规范化字段名。**引号在这里是分隔符不是定界符**：
  `train05/train05b/train11/train_slope_unknown` 等 4 个算例把标签行写成
  `... rmesh'level_set_problem,ljdp ,stab_matde`，按引号定界会得到
  `rmeshlevel_set_problem` 这个不存在的字段。同时把 `level_set` 归一到
  `level_set_problem`。
- `_record(label_line, data_line)` — `zip(labels, values)`，**故意是截断式的**：
  标签行普遍比数据行短（见 §2.2），一个名字只对它正下方的那一格负责。
- `_iget(rec, name, default)` — 按名取整数，缺失/非数字返回默认值。

文本层沿用唯一实现：`from deck_text import expand`（`!` 尾注截断、`n*v` 展开、
逗号/空白混合切分）。**没有第七份 Fortran 文本层。**

删掉的旧代码：

```python
info["nelem"] = int(vals[2])   # 只对方言 A 成立
info["ndimn"] = int(vals[3])
...
idx = header.index("NBLKS")    # 原始 split，遇 'NINIT 的前导引号即失效
except: info["nblks"] = int(vals[3])
```

`NBLKS` 那处原本已经在按名对齐，只是用 `line.split()` 没剥引号、并保留了一个
按位置的 `vals[3]` 兜底；一并换成同一套 `_record`，结果不变（89/89 一致）。

### 3.1 逐算例前后对比

`train_temp_creep` 是唯一变化的：

```
字段      旧（按位置）  新（按标签）   真值
npoin        5628         5628        5628
nelem           3         4720        4720   ← 旧值实为 ndimn
ndimn           1            3           3   ← 旧值实为 nmats
nmats           1            1           1
ngroup          0            1           1
```

其余 88 个算例（含 `freq`/`static` 的 9 标签行、`pile_beam`/`sluice_3d` 的粘连引号行、
`box_culvert_3d` 的逗号尾）五个字段全部逐值相同。

## 4. 往返矩阵前后

命令：`python3 fem-chat/docs/research/hstar-input-redesign/tools/roundtrip_matrix.py`

```
                       1.glb    1.man    1.mat    1.LOA   1.pre   1.ifs
修前  train_temp_creep MISSING  MISSING  MISSING    —     MISSING MISSING
修后  train_temp_creep 63L      11L      19L        —     OK~     8L
```

修前那一行还附带一条**错误的诊断信息**：

```
ValueError: unsupported element: nnode=8, ndimn=1. Known: 4n/2D, 8n/3D, ...
```

这是 `09-facts-verification.md` §2 新加的 `elem_info` 严格检查在报警——报得对
（`ndimn=1` 确实非法），但**指错了地方**：网格没问题，`ndimn=1` 是两个文件之外的
头部误解析漂过来的。严格化把一个静默的错误答案换成了一声响亮的、指向错误位置的告警。
这本身是净收益（此前"全部往返数字无意义"没人发现），但值得记一笔：
**报错位置 ≠ 故障位置**，尤其当上游解析静默产出合法但错误的标量时。

**其余 20 行全部逐字符不变**（含 `train01 OK/2L/OK/OK/OK/OK`、
`train_vie_boundary 66L/8L/36L/3025L/OK~/146L` 等），无一格变差。

## 5. 单测

`fem-chat/skills/test_skills.py` 追加 `test_glb_header_dialects`（未改动任何既有测试）：

- 直接对两条真实标签/数据行断言 `_record` 的解析结果（方言 A 有 `npoinb`、
  方言 B 无 `npoinb` 且无 `stab_matde` 尾）；
- 断言粘连引号 `rmesh'level_set_problem` 被切成两个字段；
- 端到端断言两个真实算例 `parse_glb` 的 5 个字段。

```
修前：Passed 337  Failed 0
修后：Passed 359  Failed 0   (+22)
```

## 6. 未做 / 留给下一个探针

- **方言 B 的迁移**只在往返矩阵里"顺带发生"（生成器总是写方言 A）。补 `npoinb` 时
  取 `npoinb = npoin`；依据是 88/88 个方言 A 算例满足 `npoin == npoinb`，
  且求解器读入后从不使用（§1）。这是本文件唯一一处**依据统计而非源码**的取值。
- `train_temp_creep` 迁移到方言 A 后求解器仍失败（rc 174），故障点已不在 `.glb` 头部；
  与 `12-`/`13-` 里"拦路的换了一个文件"是同一模式，未追。
- 其它 deck 文件（`.mat`/`.LOA`/`.man`）是否也存在同类的**记录版本方言**，未查。
  `08-revised-architecture.md` 主张 Deck ABI 带 record ID 与版本，本例是第二个实证。

## 7. 复算命令

```bash
cd /home/huijun/HSTAR_Next
grep -rn npoinb hstarYLOrig/HSTAR/                     # 3 行：声明 / READ 677 / PRINT 678
for f in cases/cases/*/1.glb; do head -1 "$f"; done | sort | uniq -c   # 方言普查
cd fem-chat/skills && python3 test_skills.py           # 359 项
cd /home/huijun/HSTAR_Next && python3 fem-chat/docs/research/hstar-input-redesign/tools/roundtrip_matrix.py
```
