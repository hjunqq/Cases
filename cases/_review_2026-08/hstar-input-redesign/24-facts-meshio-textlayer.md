# 事实六：收编第 7 处文本层（open #14），并顺手捞回两个被静默丢弃的算例

> 2026-08-29。回答 `06-open-questions.md` #14。
> 结论可复算，命令见 §6。

## 0. 一句话

`mesh_io.detect_groups_from_glb` 自带的逗号方言解析器已删除，改为调用
`deck_text.expand`；组行的**字段语义**（0=单元类型、1=组名、8=nelgroup、9=matno）
留在原地，因为那是领域知识不是文本规则。

收编本身预期是"行为不变"的重构。实际不是：**89 个算例里 2 个的解析结果变了，
而且两个都是从错的变成对的**——`pile_beam` 此前返回**空列表**（整个算例一个组都
没解析出来），`sluice_3d` 此前少 2 个组。两处都没有任何告警。

## 1. 被删掉的那份实现

`mesh_io.py`（收编前，行号对应提交 `6d6b257`）：

```python
if line.count(",") >= 9:
    parts = [p.strip() for p in line.split(",")]
    parts[1] = parts[1].strip("'\" ")
    # Mixed space+comma rows (e.g. pile_beam: Q4 '  1' 5,CO,…)
    # mis-align under a comma split — their first field keeps
    # internal whitespace; fall back rather than emit garbage.
    if len(parts) < 10 or " " in parts[0]:
        parts = line.split()
else:
    parts = line.split()
if len(parts) >= 10:
    ...
```

它被 4 个模块使用（`import_glb` / `gen_mesh_vtp` / `mesh_preview` / `mesh_io` 自身），
**并且它才是喂 `.glb` 组行进入往返矩阵的那一处**——这就是为什么 `deck_text` 的引号
bug（提交 `264d870`）修好后往返矩阵一格都没动：组行根本不走 `deck_text`。

### 1.1 那条"回退"注释说反了

注释说混合行"fall back rather than emit garbage"。实际后果不是回退到正确解析，
而是**整行被丢弃**：

```
pile_beam/1.glb:57
Q4 '    1' 5,CO,1,U,ST,PS  360     1    0,1,1,1,0,0,0,0

逗号数 12 ≥ 9        → 走逗号路径
parts[0] = "Q4 '    1' 5"  含空格 → 触发回退
line.split()         → ['Q4', "'", "1'", '5,CO,1,U,ST,PS', '360', '1', '0,1,1,1,0,0,0,0']
                       7 项 < 10  → 既不 append，也不走 i += 3
```

`len(parts) >= 10` 不成立时既不记录也不告警，`i` 只 +1，于是这一组连同它的 3 行子记录
一起被跳过。`pile_beam` 的 3 个组全部如此，返回 `[]`。

`sluice_3d` 同理丢了末尾两条 L2 梁组（`1.glb:308` / `:314`）：

```
L2 '    50' 20,BM,1,U,ST,PS  315     9    0,1,1,1,0,0,0,0
```

### 1.2 `pile_beam` 是本项目主症状最纯粹的一个标本

请注意 `pile_beam` 的失败形态不是"解析出了错误的组"，而是**一个组都没有**：

```
detect_groups_from_glb("cases/cases/pile_beam")  →  []
```

没有异常、没有 stderr、没有返回码。函数签名说返回 `list`，它返回了一个合法的 `list`。
下游（`import_glb` / `gen_mesh_vtp` / `mesh_preview`）拿到"这个算例有零个组"，
全部照单全收继续走——生成的 config 没有组、预览图没有分组着色，而且**每一步都"成功"**。

`README.md` 开篇那条判据在这里是字面成立的：

> 本系统的失败模式几乎全部是**语法合法、求解器接受、物理不对**。

这一例连"求解器"都还没轮到——**语法合法、无告警、结果为空、消费者相信**。
它在仓库里存续了多久无法从代码看出，因为从来没有任何东西会因此变红。

## 2. 收编后

```python
parts = expand(line)          # deck_text：空格/逗号/引号/`!`/n*v 一并处理
if len(parts) >= 10:
    name = parts[1].strip() or f"Group{len(groups)+1}"
    nelgroup = int(parts[8]);  matno = int(parts[9])
```

三种方言在同一条路径下都对：

| 方言 | 实样 | `expand` 结果 |
|---|---|---|
| 空格 | `Q4    Foundation     5 CO ... 960  1 ...`（train01:61） | 18 项，8=`960` 9=`1` |
| 逗号 | `q4,'  1',5,CO,1,U,ST,PE,  200,1,0,...`（train05:59） | 18 项，8=`200` 9=`1` |
| 混合 | `Q4 '    1' 5,CO,1,U,ST,PS  360     1    0,...`（pile_beam:57） | 18 项，8=`360` 9=`1` |

**`" " in parts[0]` 那个回退在新语义下不是"可能不需要"，而是它本身就是故障源**——
rule 4（引号内是一个项）恰好覆盖了它想处理的那类行。

留在 `mesh_io` 的领域逻辑：槽位语义、`nnode_map`、`i += 4` 跳表头、`i += 3` 跳子记录、
`tension_joint`/`ngaps` 终止条件。唯一新增的一步是 `parts[1].strip()`——引号内容按
rule 4 是**逐字返回**的（`'  1'` → `"  1"`），补空格的组名要在这里去掉，
这一步是命名规范化，属于领域侧。

## 3. 验收

### 3.1 全字段比对（89 个算例，不是抽样）

`{name, nelgroup, matno, nnode, elem_type}` 逐算例逐组比对：

```
87 个逐字段不变
 2 个变化：
   pile_beam   []                    → 3 组   （Q4×2 + L2×1）
   sluice_3d   49 组                 → 51 组  （补回 L2 '50' / L2 '51'）
组总数 696 → 701
```

### 3.2 独立判据交叉验证（这两个变化确实是修复）

不用"我看着像对的"来判定。`.glb` 头部自带两个独立数字：`NGROUP` 与 `NELEM`。
判据 `len(groups) == ngroup 且 sum(nelgroup) == nelem`：

```
收编前：89 个算例中 2 个不满足
收编后：89/89 全部满足
```

不满足的恰好就是变化的那两个。头部的 `ngroup`/`nelem` 与组行是 `.glb` 里两处独立
书写的信息，二者对上，才说明捞回来的组是真的。

### 3.3 往返矩阵

21 行 × 6 列**逐格不变**（`pile_beam` / `sluice_3d` 不在矩阵的 21 个算例里，
矩阵覆盖的都是 `train*`）。

### 3.4 单测

```
收编前：Passed 362
收编后：Passed 371   (+9，新增两条测试，见下)
```

新增的是两条测试：

- `test_glb_group_rows_use_shared_text_layer` —— 钉"走共享文本层"：
  `mesh_io.expand is deck_text.expand`、源码里不再有 `line.split(",")`、
  混合方言行切成 18 项且 8/9 槽正确、`pile_beam`/`sluice_3d` 按名字点住组数。
- `test_glb_groups_account_for_header` —— 把 §3.2 那条判据固化成**常驻全量检查**，
  89 个算例逐个跑。它的价值在于**自带参照物**：头部与组块是同一文件里两处独立
  书写的信息，对上才算数，不需要任何人去"看着像对的"。
  **不跳过空结果**——返回空正是 `pile_beam` 的失败形态，一跳过就把它藏了
  （最初写了 `if not groups: continue`，变异测试里只报 `1/88`；去掉后才是 `2/89`）。

**变异测试**：把 `mesh_io.py` 恢复成收编前版本再跑，9 项中 5 项失败：

```
FAIL: mesh_io uses the shared expand: expected True, got False
FAIL: mesh_io splits no group row itself: expected False, got True
FAIL: pile_beam: groups recovered: expected 3, got 0
FAIL: sluice_3d: groups recovered: expected 51, got 49
FAIL: every group row accounted for: expected 0, got 2. 2/89 cases
```
测试确实有牙。
第一次写的版本用 `mesh_io.expand` 直接取属性，旧代码下抛 `AttributeError`
把整个测试打断在第一条断言，判据那部分根本没跑到——已改成 `getattr(...)`，
让有牙的那部分一定被执行。

## 4. 报错位置 ≠ 故障位置

这条来自 open #7，值得单独记：

`09-facts-verification.md` §2 把 `elem_info` 从"静默返回 Q4"改成 `raise ValueError`，
方向是对的（"表达不了就拒绝"）。但在 `train_temp_creep` 上它报的是：

```
ValueError: unsupported element: nnode=8, ndimn=1. Known: 4n/2D, 8n/3D, ...
```

网格完全没问题。`ndimn=1` 是**两个文件之外**的 `.glb` 头部误解析漂过来的标量。
严格化把一个静默的错误答案换成了一声响亮的、**指向错误位置**的告警——净收益
（此前"整行往返数字无意义"没人发现），但它会把下一个人送去查网格。

本次 open #14 是同一模式的另一面：`mesh_io` 那处**连告警都没有**，
`pile_beam` 静静地返回 `[]`，下游拿到"这个算例没有组"继续走。
两者合起来给出一条可操作的规则：

> **拒绝要拒绝在源头，不能拒绝在下游。**
> 下游的严格检查只能证明"上游给了非法值"，不能指出上游是谁。
> 一个解析器如果可能产出**合法但错误**的标量（`ndimn=1`、`groups=[]`），
> 那么它自己必须有校验；把校验推给消费者，得到的是指错地方的告警。

对应到本次两处修复，源头校验各自是：`.glb` 头部按标签名对齐（open #7）、
组行数与 `NGROUP`/`NELEM` 对账（本文件 §3.2，已进单测）。

## 5. 未做 / 留下的洞

- **`nnode_map` 仍是静默默认**：`nnode_map.get(parts[0], 4)`。全语料出现的单元类型是
  `B8`×500 `Q4`×168 `L2`×23 `p4`×4 `q4`×4 `Q8`×1 `B20`×1。其中 **`p4` 不在表里**
  （`box_culvert_3d`，一个 3D 算例），静默拿到 `nnode=4`；`q4` 小写也不在表里，
  拿到 4 只是碰巧对。这与 `09-§2` 的 `elem_info` 是同一个失败家族，本次未动
  （改它会牵动 `gen_mesh_vtp`/`mesh_preview` 的行为，超出 open #14 范围）。
- **表头跳行 `i += 4` 靠运气**：`train01` 的第 5 行表头以 `(` 开头被 `startswith("(")`
  滤掉；`train05` 的同一行以 `'` 开头**滤不掉**，是靠"字段数 < 10"才没被当成组行。
  两条路径都通，但都不是设计出来的。未改。
- **`deck_text.py` 的模块 docstring 已更新**（六处→七处、补 `mesh_io` 那行、
  open #14 段改成已收编并点明"其中一个静默返回零组"、修 "three rules"→"four rules"
  的既有笔误）。该文件是生产共享层，改动前经 team-lead 批准，只动 docstring 不动代码。

## 5b. 仪器风险：31 个 `.glb` 对普通 `grep` 不可见

本次差点第二次栽在同一个坑上。`cases/cases/*/1.glb` 里有 **31/89 个是 ISO-8859 + CRLF**
（迁移自 2011 年的老 deck），`grep` 把它们当二进制，**静默什么都不输出、退出码 1**：

```
$ grep -c NGROUP cases/cases/pile_beam/1.glb     # 无输出，exit 1
$ grep -ac NGROUP cases/cases/pile_beam/1.glb    # 2
```

**而且这不是巧合**：被解析器丢掉的两个算例 `pile_beam` / `sluice_3d`，
正是 `grep` 看不见的那 31 个里的两个——同一批老 deck 既触发混合方言，
又躲开人工复核。任何"我 grep 过了，没有这种行"的结论，在这个仓库里默认无效。

清单（31 个）：`box_culvert_3d` `damage` `dam_fluid_coupling` `dam_seepage_3d` `fix`
`pile_beam` `rcbeam` `rcbeam_crack` `sluice_3d` `train_contact_nonlinear`
`train_seepage` `train_seepage_stress` `train_slope_unknown` `train_vie_boundary`
`tunnel` `tunnel_sl` + 15 个 `xfj_*`。

Python 侧不受影响：`open(..., errors="replace")` 照常读，所以工具链看得见、人看不见——
这正是最糟的组合。（team-lead 另报了 8 个 GBK 求解器源文件有同样问题；`.glb` 这 31 个
是同一类风险的另一处，比例更高。）

## 6. 复算命令

```bash
cd /home/huijun/HSTAR_Next/fem-chat/skills

# 全字段比对（改前改后各跑一次，diff 两份 json）
python3 -c "
import sys,json; sys.path.insert(0,'.')
from pathlib import Path
from mesh_io import detect_groups_from_glb
print(json.dumps({p.parent.name: detect_groups_from_glb(str(p.parent))
      for p in sorted(Path('../../cases/cases').glob('*/1.glb'))}, sort_keys=True, indent=1))"

python3 test_skills.py glb_group_rows_shared_layer glb_groups_account_for_header   # 9 项
python3 test_skills.py                               # 371 项
cd /home/huijun/HSTAR_Next && python3 fem-chat/docs/research/hstar-input-redesign/tools/roundtrip_matrix.py
```
