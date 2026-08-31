# 27 · C 组迁移（只有 `1.LOA` 的算例）与全语料文件名大小写审计

> 2026-08-29。作用域：`cases/cases/` 全部 92 个目录（其中 89 个是算例目录，
> 另有 `_review_2026-08/`、两个纯网格残桩、以及一个 `.html`）。
> 写授权仅限 `train02c_dbg/`、`train02c_seismic_wave_compare/`；其余全程只读。
> 备份：`/tmp/claude-1000/migrate-C/{train02c_dbg,train02c_seismic_wave_compare}`。
> 未 commit（`cases/` 是无 `.git` 的 gitlink，改动对 `git status` 不可见）。

---

## 0. 三条对任务前提的更正（先读这节）

| # | 任务里的说法 | 实测 |
|---|---|---|
| 1 | 「多数算例 `1.loa` 与 `1.LOA` **同时存在且内容相同**」 | **口径不准**。49 个是 **`1.loa` → `1.LOA` 的符号链接**（同一 inode），只有 1 个是真副本。"内容相同"是链接的必然结果，不是巧合，也不是有人维护出来的。**语料的既有约定是 symlink，不是 copy。**（→ §2 回答"复制还是重命名"：两个都不是） |
| 2 | 「只有 `1.LOA` 没有 `1.loa`」的算例有 **2 个** | **3 个**。第三个是 `gravdam_static_demo`，它不在 decoder 的 21 算例集里所以此前没暴露。它同样是坏的。 |
| 3 | 「`open` 会新建一个空文件**然后读失败**」 | **前半句对，后半句要补一句关键的**：`.loa` 的读**没有 `iostat=`**，所以不是"读失败"而是 `forrtl: severe (24)` **硬中止、退出码 24**。这一路是**响的**。真正静默的是同一机制作用在**其它** deck 上（→ §4，语料里已经发生了 5 例）。 |

另外发现一个**仪器 bug**：`fem-chat/harness/_solve_deck.py` 会把这次 severe(24)
崩溃报成**成功**（→ §6）。

---

## 1. 89 个算例的 `1.loa` / `1.LOA` 组合全表

### 1.1 汇总

| 组合 | 数量 | 说明 |
|---|---:|---|
| `1.loa` 是指向 `1.LOA` 的 **symlink** | **49** | 语料主流约定 |
| `1.loa` 与 `1.LOA` 都是**真文件、内容相同** | **1** | `train05b_slope_srm`（395 B / 395 B，md5 同） |
| **只有 `1.loa`**（无 `1.LOA`） | **36** | 现代工具链产出 + xfj 系列 |
| **只有 `1.LOA`**（无 `1.loa`）← **本任务对象** | **3** | `train02c_dbg`、`train02c_seismic_wave_compare`、**`gravdam_static_demo`** |
| 两者都无 | **3** | `benchmark_200x200`、`train07b_thermal_steady`、`train12b_seepage_transient`（纯网格残桩，连 `1.glb` 都没有） |

### 1.2 有没有内容分叉的？

**`.loa` 这一路：没有。** 逐个 `md5sum` 核过：49 个是 symlink（同 inode，
不可能分叉）；`train05b_slope_srm` 的真副本对 md5 一致。
**`.loa` 不存在两份在分叉的荷载文件。**

**但 `.ftr` 这一路有一例真分叉** —— `temp_stress`：

```
1.ftr  72 B (LF)    " nforce,ngaps,nforce_gaps,nsafety_gaps" / "0 0 0 0"      ← 新格式
1.FTR  25 B (CRLF)  " nnforce ngaps_for"                    / "4*0"          ← 旧格式
```

两份都非空、内容不同、格式不同代。求解器只读 `1.ftr`（小写），
所以当前读到的是新格式那份 —— 恰好是对的。
但这是 `13-probe-report-old-format-peel.md` 里"旧格式 `.ftr`"迁移留下的**未清理残骸**：
迁移写了新的小写文件，没有删掉旧的大写文件。**建议删 `temp_stress/1.FTR`**（不在我的写授权内，未动）。

### 1.3 逐算例明细

`SYM` = `1.loa` 是 symlink · `PAIR` = 两个真文件同内容 · `lower` = 只有 `1.loa` ·
**`UPPER`** = 只有 `1.LOA`（缺陷）· `none` = 都没有

```
SYM   benchmark_100x100 benchmark_50x50 contact3d cooks_membrane lame_cylinder
      mini_3d mini_dynamic mini_goodman mini_gravdam mini_mc mini_modal mini_rebar
      mini_thermal new_duncan_chang new_seepage_steady temp_stress test_arclength
      test_beam2d test_biot_1elem test_concrete_tension test_creep_power
      test_duncan_chang test_gen test_goodman_slip test_plate_simply_supported
      test_seepage_stress test_terzaghi test_thermal_expansion test_TWS_coupling
      test_uplift train01_gravdam_static train02_gravdam_seismic train03a_modal_dry
      train03b_modal_ifs train04_beam_faceload train05_slope_stability
      train06_concrete_damage train07_thermal_transient train09_rc_bond
      train10_dynamic_vie train11_staged_foundation train12_seepage_steady
      train_contact_nonlinear train_seepage train_seepage_stress
      train_slope_unknown train_vie_boundary XFJ_S1_2block          (49)

PAIR  train05b_slope_srm                                            (1)

lower box_culvert_3d damage dam_fluid_coupling dam_seepage_3d(0B) disc_contact_3d
      fix freq goodman_evolution goodmanLU gravdam pile_beam rcbeam rcbeam_crack
      rc_lining sluice_3d static train_temp_creep tunnel tunnel_lining tunnel_sl
      vie xfj_a1_convergence_debug xfj_a3_robustness_init1 xfj_inverse_e_dam_t
      xfj_inverse_e_dam_w xfj_inverse_e_dam_w_fd xfj_inverse_e_dam_wt
      xfj_inverse_hc_gf xfj_inverse_mat xfj_inverse_mat1 xfj_inverse_mat2
      xfj_inverse_mat3 xfj_r2a_water xfj_r2b_temp xfj_seepage_transient
      xfj_static xfj_thermal_transient                               (36)

UPPER train02c_dbg  train02c_seismic_wave_compare  gravdam_static_demo   (3)  ★

none  benchmark_200x200 train07b_thermal_steady train12b_seepage_transient (3)
```

---

## 2. `open` 行为：实测

编译器：`/opt/intel/oneapi/2025.3/bin/ifx`（本机唯一的 Fortran 编译器；
`gfortran` / `ifort` 都没装。oneAPI 2026.0/2026.1 只装了 C/C++）。

### 2.1 最小复现

```fortran
open(11, file='1.loa')          ! 默认 status='unknown'，同 Global.f90:633
```

```
 before open, 1.loa exists?  F
 after  open, 1.loa exists?  T      ← 建了
 read char iostat=  -1              ← EOF
 read int  iostat=  -1
 after close, 1.loa exists?  T      ← close 后仍在盘上，0 字节
```

**带 `iostat=` 时**：静默拿到 EOF，程序继续跑。
**不带 `iostat=` 时**（HSTAR 的实际写法）：

```
forrtl: severe (24): end-of-file during read, unit 11, file .../2.loa
EXIT=24
```

### 2.2 真求解器上的对照实验

把 `train02c_dbg` 的 deck 复制到 scratch，**不放** `1.loa`，经
`harness/_solve_deck.py` 跑：

```
Exit code: 24
forrtl: severe (24): end-of-file during read, unit 21,
        file .../ctrl/1.loa
   lblks=0 lincs=0 ttime=0.0        ← 一步都没算
```

跑完后 `ls`：

```
-rw-rw-r-- 1 huijun huijun 0  8月 29 07:00  .../ctrl/1.loa     ← 求解器自己建的
```

### 2.3 结论

**你的描述基本正确，需要补一句**：`open` **确实**新建 0 字节文件并留在盘上
（`Global.f90:633`，默认 `status='unknown'`）。但 `.loa` 的读路径
（`Load.f90:141-142` `read(loadunit,*)text` / `read(loadunit,*)ntcurve`，**无 `iostat=`**）
使后果是**硬中止 severe(24) + 退出码 24**，不是"读失败后继续"。

这个区分是有用的：**`.loa` 这一路会自己喊出来**。
危险的是同一个 `open` 作用在**读路径带守卫**的 deck 上 —— 那才是静默的（→ §4）。

---

## 3. 修法：symlink，不是 copy 也不是 rename

**采用：`ln -s 1.LOA 1.loa`。**

判据（按权重排序，不含偏好）：

1. **语料现状就是 symlink。** 50 个"两者都在"的算例里 49 个是 symlink，
   仅 1 个是真副本。任务里"多数算例两者同时存在且内容相同"的观察**是对的**，
   但机制被误读成了 copy。跟随主流约定 = symlink。
2. **copy 会制造本任务正在担心的那个风险。** 你问"有没有两份在分叉的"——
   `.loa` 目前没有，但 `.ftr` 上**已经有一例**（`temp_stress`，§1.2）。
   真副本是分叉的必要条件；symlink 从构造上排除分叉（同一 inode）。
   既然分叉在这个语料里被证明会发生，就不该主动新增可分叉的副本。
3. **rename 会破坏归档溯源。** 归档的 `1.flavia.res` 与 `.chk` 都是在
   `1.LOA` 这个名字下产出的；改名后无法再对齐。symlink 保留 `1.LOA` 原名。
4. **Windows / Syncthing 侧不受影响。** 这两个算例名以 `train` 开头，
   在 Syncthing 的 `.stignore` 白名单里。Syncthing 在 Windows 端默认**不同步符号链接**，
   所以对端只会看到 `1.LOA` —— 而 Windows 文件系统不区分大小写，
   `open('1.loa')` 照样命中 `1.LOA`。**symlink 在两端都对，且不需要对端做任何事。**
   （rename 则会让对端既有引用失效，正是你担心的那一条。）

已执行：

```
cases/cases/train02c_dbg/1.loa                  -> 1.LOA
cases/cases/train02c_seismic_wave_compare/1.loa -> 1.LOA
```

`gravdam_static_demo` **同病未修**（不在写授权内）。修法相同。

---

## 4. 全语料大小写审计

### 4.1 求解器的字面文件名（`Global.f90:628-673`）

全部小写，无例外：
`.glb .cor .ele .pre .mat .loa .chk .sol .man .opr .opw .oew .ogw .ojw .dis .act
.gpv .ini .inw .vcor .tem .ftf .ftr .ifs .aqu .nrt .bar .bem .ctr .gdm .sto`
（+ 条件打开的 `.btl .obs .obsc .oid .oip .tel .stn .msh` 与二进制 `.rtt .stf .res .resb .fai .ctt`）。
**所以任何大写 deck 文件在 Linux 上一律读不到。**

### 4.2 全语料大小写不匹配清单（完整）

| 算例 | 大写文件 | 小写同名文件的状态 | 后果 |
|---|---|---|---|
| `train02c_dbg` | `1.LOA` 64 KB | **缺失** | severe(24) 中止 — **已修** |
| `train02c_seismic_wave_compare` | `1.LOA` 64 KB | **缺失** | 同上 — **已修** |
| `gravdam_static_demo` | `1.LOA` 741 B | **缺失** | 同上 — **未修**（无写授权） |
| `pile_beam` | `1.FTR 1.IFS 1.OPR 1.SOL 1.TEM` | **存在但 0 字节** | ★ 见 §4.3 |
| `sluice_3d` | `1.FTR 1.IFS 1.OPR 1.SOL 1.TEM` | **存在但 0 字节** | ★ 见 §4.3 |
| `temp_stress` | `1.FTR` 25 B（旧格式） | 存在，72 B（新格式） | 内容分叉，但读的是对的那份；`1.FTR` 是迁移残骸，建议删 |
| 49 个算例 | `1.LOA` | symlink 指向它 | 正常 |

其余大写名（`README.md` ×17、`run_hstarYL*.log` ×39、`1.LOA.bak` ×4、
`orig_1.LOA`、`VALIDATION_STATUS.md`、`_README_R2*.txt`、两个 `.png`）
都不在求解器的 open 表里，无害。

### 4.3 ★ `pile_beam` / `sluice_3d`：同一机制造成的**静默**版本

```
pile_beam/1.SOL   102 B  4月  9 23:49   ← 真 deck
pile_beam/1.sol     0 B  4月 10 00:14   ← 求解器 open() 建的空壳，现在盖住了它
（.ftr .ifs .opr .tem 同样，5 个文件，时间戳全部是 4月10 00:14）
```

同一时间戳 `4月10 00:14` 在 `dam_seepage_3d` 上把**整个目录**铺了 0 字节文件
（`1.pre 1.mat 1.loa 1.man 1.sol 1.opr 1.tem 1.ftr 1.ifs 1.nrt` 全 0 B，
该目录原本只有 `1.cor 1.ele 1.glb`）。
→ **2026-04-10 00:14 有过一次批量求解尝试，在若干目录里留下了 `open()` 的空壳残骸。**
这是 §2 那个机制在语料里的**指纹**，也是它确实会发生的**独立证据**。

为什么这一版是**静默**的：`.sol/.opr/.ifs/.tem/.ftr` 的读路径不像 `.loa` 那样
在函数头无条件读，多数挂在开关下（`1.IFS` 的真内容是 `nifsgroup 0 / nabsfgroup 0 / …`，
空文件与"全 0"在下游几乎无法区分）。所以这两个算例**不会 severe(24)，
会安安静静地按"没有接触面 / 没有求解器控制参数 / 没有温度场"跑完**。

> 这正是 README 那条判据的实例：**语法合法、求解器接受、物理不对。**
> 而且 `pile_beam` / `sluice_3d` **正是 README §陷阱里点名的那两个算例**
> ——既是 31 个 `grep` 不可见 `.glb` 的成员，又是解析器静默丢掉的两个，
> 现在又是 deck 被空壳遮蔽的两个。三个独立缺陷叠在同两个算例上。

**未修（无写授权）。修法：删 5 个 0 字节小写文件，各建 `ln -s 1.XXX 1.xxx`。**
`goodmanLU`（`1.man 1.sol 1.opr 1.tem 1.ftr 1.ifs 1.nrt` 全 0 B，且**无**对应大写文件）
与 `dam_seepage_3d`（同上 + `1.pre 1.mat 1.loa` 全 0 B）不是大小写问题，
是**算例本身残缺**，无法就地修，需要重建 deck。

### 4.4 缺少求解器会无条件打开的输入文件

除上面已列的以外：

- `benchmark_200x200`、`train07b_thermal_steady`、`train12b_seepage_transient`
  —— 只有 `1.cor/1.ele/1.pre`，**连 `1.glb` 都没有**。纯网格残桩，不是可运行算例。
- `1.aqu` 在**全部 89 个算例**里都是 0 字节或缺失 —— 与 ABI 覆盖账本里
  "`.aqu` 覆盖为 0" 一致，不是缺陷，是本套件根本没有 `mwaqu` 类算例。
- `1.opr` 除 `dam_fluid_coupling / fix / train04_beam_faceload / vie` 四个外全是 0 字节；
  `1.ini` / `1.inw` 绝大多数是 0 字节。这些都在开关守卫下，属正常。

---

## 5. 验收

### 5.1 decoder 前后

`python3 tools/decoder.py --case <name>`，两个算例结果完全一致：

| | 修前 | 修后 |
|---|---:|---:|
| 解码记录 | 131 | **199** |
| 绑定变量 | 346 | **458** |
| 走到的文件 | `.ftr .glb .ifs .mat .nrt .opr inp`（7） | + **`.loa`(45 条/645 行 100%) `.man` `.pre` `.tem`**（11） |
| 停止点 | `Load.f90/external_load_1:147`<br>`loop bounds: unbound ['ntcurve']` | **走完整棵树，未遇到不可判定点** |

decoder 修前就已经**主动报出了病因**（值得记一笔，它做对了）：

```
⚠ 1.loa 不存在，但有同名不同大小写的 1.LOA；求解器按字面名 open，.loa 的 READ 全部跳过
```

→ `10-roadmap.md §0` 的「完整走完整棵树 11/21」应更新为 **13/21**
（`gravdam_static_demo` 修掉后视其是否在集内可再 +1）。

### 5.2 求解器

经 `fem-chat/harness/_solve_deck.py`（**未直接调 `./hstar`**），
在 scratch 副本中运行以保持算例目录的归档结果不被覆盖：

| 算例 | 步数 | 退出码 | `1.flavia.res` |
|---|---:|---:|---|
| `train02c_dbg` | 400 × dt=0.005 | **0** | 37.8 MB，400 个 DISPLACEMENT 块 |
| `train02c_seismic_wave_compare` | 2000 × dt=0.01（输出 1000 步） | **0** | 1000 个 DISPLACEMENT 块 |

两个都收敛（`nchek=0`，`ratio1 ~ 1e-16`）。

### 5.3 与归档的差异 —— 并且这里要更正你的认识论前提

你说「归档 `1.flavia.res` 来自能读到 `.loa` 的环境（很可能是 Windows），
**不是本机基线**」。实测：

| 算例 | 步数一致 | 峰值 \|U\| | 最大绝对差 | 相对峰值 |
|---|---|---:|---:|---:|
| `train02c_dbg` | 400 / 400 ✅ | 9.788376 | 4.5e-11 | **4.6e-12** |
| `train02c_seismic_wave_compare` | 1000 / 1000 ✅ | 9.797562 | 1.0e-07 | **1.0e-08** |

**本机重跑与归档在数值上一致到 1e-8 相对量级**（差异量级 = PARDISO/MKL
线程序 round-off；逐字节不同，但打印的 8 位有效数字在峰值处全同）。

所以：**这两个算例的归档结果确实可以当本机基线用。**
旁证：`1.flavia.res` / `1.chk` / `1.gpv` 的 mtime 都是 **8月25 23:47**，
`1.glb` 是 8月25 23:23 —— 这是**本仓库、本机、四天前**的产物，
不是 Windows 归档。当时它是怎么读到 `.loa` 的（临时建过又删了？）已不可考，
但结果是可复现的。

⚠ **但"可复现"不等于"物理对"**：峰值位移 ≈ 9.8（deck 单位），
对一个 100 m 级重力坝的地震时程而言量级偏大。这符合 README 的主判据
（语法合法、求解器接受、物理不对）。**本任务只负责让它在本机可跑可解码，
不对其物理正确性背书。**

### 5.4 两个算例的实际差别（顺带查清）

它们**几乎是同一个算例**：`1.cor 1.ele 1.LOA 1.mat 1.pre 1.tem` md5 全同；
`1.glb` **仅行尾不同**（dbg 是 CRLF，compare 是 LF；`tr -d '\r'` 后逐字节相同）。
唯一实质差别在 `1.man`：

```
train02c_dbg                    nincs,cdtest,earthquake_curve(1:ndimn) =  1 0  0 0
                                nstep=400   dt=0.005
train02c_seismic_wave_compare   nincs,cdtest,earthquake_curve(1:ndimn) =  1 0  2 0
                                nstep=2000  dt=0.01
```

即 **`_dbg` 的 `earthquake_curve = 0 0`** —— 按 `CLAUDE.md` 的 PRJ-6057 规则，
地震**根本没进运动方程**；`_seismic_wave_compare` 是 `2 0`（曲线 2 加在 x 向），
才是正确形态。`_dbg` 顾名思义是关掉地震的调试变体，这**大概率是有意的**，
但没有任何文件记录这一点。**建议在这两个目录各放一行 README 说明**（本次未加，
以免在没确认意图的情况下写入语义断言）。

---

## 6. 我踩到的仪器 bug

### bug #1（严重）· `harness/_solve_deck.py` 把 severe(24) 崩溃报成成功

`fem-chat/harness/_solve_deck.py:56`：

```python
return 0 if (job / "1.flavia.res").exists() else 1
```

放行判据是 **`1.flavia.res` 是否存在**。但 `Global.f90:703` 用
`open(out_gid_dis, file=…//'.flavia.res', …)`，默认 `status='unknown'` —— 
**求解器一启动就把这个文件建出来了**，无论后面算不算得动。

我的对照实验（§2.2）实测：

```
Exit code: 24                    ← forrtl severe(24)，一步没算
1.flavia.res: yes                ← 0 字节
（脚本 return 0）                 ← 报成功
```

**这是本任务正在调查的那个 bug，长在了调查它的仪器里。**
`open(status='unknown')` 保证了门禁条件恒真。

修法（未改，不在写授权内）：

```python
res = job / "1.flavia.res"
ok = result.returncode == 0 and res.exists() and res.stat().st_size > 0
return 0 if ok else 1
```

`returncode` 与 `st_size > 0` 各自都能独立堵住这一路；两个都加。
同样的门禁写法应在 `run_pipeline.py` 里查一遍。

### bug #2（我自己的，记录以免下一个人重犯）· 结果比对脚本吃进了应力块

第一版比对脚本用 `len(fields) >= 3` 收行，把 `1.flavia.res` 里的
**应力/高斯点结果块**也当成位移收了进去，得出"峰值 2.29e6"。
`.flavia.res` 是**多种结果块顺序拼接**的流，必须按 `DISPLACEMENT` 头分段、
且只收**恰好 3 列**（node, Ux, Uy）的行。改成 `len(fields) == 3` 后峰值是 **9.79**。
—— 量级差 5 个数量级，而且"2.29e6"看起来像个**能自圆其说的坏结果**
（"位移爆了，算例有问题"），不会引起怀疑。典型的 §README 主症状。

### bug #3（环境）· 本机没有 `gfortran`/`ifort`

只有 `/opt/intel/oneapi/2025.3/bin/ifx`（oneAPI 2026.0/2026.1 目录下只有 C/C++，
`compiler/latest/bin` 里**没有** `ifx`）。`which ifx` 是空的。
要做 Fortran 语义实测必须写全路径 `/opt/intel/oneapi/2025.3/bin/ifx`。

### 未踩到但已确认存在的两个陷阱

- `.glb` 的 `grep` 不可见：`train02c_dbg/1.glb` 是 CRLF + 非 UTF-8
  （`file` 报 "Hewlett-Packard Graphics Language"）。全程用 `grep -a` / `iconv` / `tr -d '\r'`。
- 求解器源码 GBK：`Load.f90` 需 `iconv -f GBK`。

---

## 7. 遗留（均无写授权，未动）

| 项 | 位置 | 修法 |
|---|---|---|
| ★ `1.loa` 缺失，severe(24) | `gravdam_static_demo` | `ln -s 1.LOA 1.loa` |
| ★ 5 个 0 字节小写文件遮蔽真 deck | `pile_beam`、`sluice_3d` | 删 0 字节的 `1.{sol,opr,tem,ftr,ifs}`，改建 symlink 指向大写原件 |
| 旧格式 `.ftr` 残骸 | `temp_stress/1.FTR` | 删 |
| 算例残缺（0 字节 deck，无大写原件） | `dam_seepage_3d`、`goodmanLU` | 需重建 deck，不能就地修 |
| 纯网格残桩（无 `1.glb`） | `benchmark_200x200`、`train07b_thermal_steady`、`train12b_seepage_transient` | 需补 deck 或从覆盖账本里剔除 |
| 仪器门禁恒真 | `harness/_solve_deck.py:56`（并查 `run_pipeline.py`） | 加 `returncode == 0` 与 `st_size > 0` |
| 语义未记录 | `train02c_dbg` 的 `earthquake_curve=0 0` | 加一行 README 说明这是有意关掉地震的调试变体 |
| 账本更新 | `10-roadmap.md §0` | 「完整走完整棵树 11/21」→ **13/21**；「2 × 只有 1.LOA」→ **3 ×** |

---

# 附录 A · 力学判据验收（2026-08-29 第二轮，验收标准升级后）

> 使用者要求：**结果对不对用力学基础理论判定，不依赖参照算例。**
> 本附录按 team-lead 给的 5 条判据逐条实测。
> **结论先说：判据 1/2/4 过，判据 5 名义过但具误导性，判据 3 把一个真缺陷挖出来了 —— 故本轮不放行。**
> 文件名大小写这一处修复本身是对的、已复核；挖出来的是这两个算例**先前就存在**的独立缺陷。

## A.0 先更正我上一轮报告里的一个数

上一轮 §5.3 我写「峰值位移 ≈ 9.8（deck 单位），量级偏大」。**那个数是错的。**
`1.flavia.res` 是 8 类结果块顺序拼接（`DISPLACEMENT` `STRESS` `SIGXX/YY/ZZ/XY`
`acceleration` `acceleration_ab`），其中 **`acceleration` 也是 3 列**。
我按"恰好 3 列"取值时把加速度块一起收了 —— **9.79 是重力加速度场，不是位移**
（≈ g，这也是它看起来"像个能自圆其说的坏结果"的原因）。
必须按块头分段并只取 `DISPLACEMENT` 段。真实值见下表，量级完全正常。
（这是同一个仪器 bug 咬了我两次：第一次 2.29e6 是应力块，第二次 9.79 是加速度块。）

## A.1 判据 1 · `fachv` 随时间变化

从 `1.chk` 逐步提取（每步一行 `fachv= <x> <y>`）：

| 算例 | n | max\|fachv_x\| | max\|fachv_y\| | 互异值个数 | 判定 |
|---|---:|---:|---:|---:|:--:|
| `train02c_seismic_wave_compare` | 2000 | **1.963249** | 0.0 | **2000（全异）** | **✓ PASS** |
| `train02c_dbg` | 400 | 0.0 | 0.0 | 1（恒零） | ✗ 地震未进入 |

**加强证据**：`max|fachv_x| = 1.963249` 与 `1.LOA` 里 SEISMIC 曲线的
`max|a| = 1.9632` **逐位相同**，且 `fachv_x` 首三步 `-1.929e-3 / -1.895e-3 / -1.745e-3`
与曲线第 2/3/4 个采样点 `-0.001929 / -0.001895 / -0.001745` **逐点一致**。
→ 地震时程**完整、无缩放、无错位**地进入了 RHS，且只加在 x 向（y 向恒 0，符合水平激励意图）。

**PGA 标定**：曲线 `n=2001, dt=0.01, T=20 s`，`max|a| = 1.9632 m/s² = 0.2003 g`。
—— 与 team-lead 判据 5 里说的"0.2g 量级"**精确吻合**，可确认 deck 单位是 SI（m, kg, s, Pa）。

`train02c_dbg` 的 `earthquake_curve = 0 0`（见上一轮 §5.4），恒零是必然结果。
**按判据 1，`train02c_dbg` 不是地震算例**，它是"自重突加 → 自由振动"的动力松弛算例。
对它套用地震判据没有意义；下面判据 2/5 只对 `_seismic_wave_compare` 判。

## A.2 判据 2 · 位移振荡而非单调爬升

坝顶节点自动选取：`y = y_max = 100`（15 个候选），取 `|Ux|` 行程最大者。

| 算例 | 坝顶节点 | 均值 | min | max | 过均值零点数 | 严格单调? | 判定 |
|---|---|---:|---:|---:|---:|:--:|:--:|
| `_seismic_wave_compare` | 344 (x=200.57) | 5.0e-6 | -8.99 mm | +9.42 mm | **137** | 否 | **✓ PASS** |
| `_dbg` | 356 | 1.7e-17 | -2.2e-16 | +3.2e-16 | 11 | 否 | 数值零 |

`_seismic_wave_compare` 20 s 内 137 次过零、正负幅值基本对称 → 典型受迫振动，
**不是** `CLAUDE.md` 描述的"单调爬升"失败形态。

## A.3 判据 4 · 初始条件无突跳

| 算例 | 首步 t | 坝顶 Ux | 坝顶 Uy | 全场 max\|U\| | 判定 |
|---|---:|---:|---:|---:|:--:|
| `_seismic_wave_compare` | 0.02 | 2.67e-7 m | −1.367 mm | 1.367 mm | ✓ |
| `_dbg` | 0.005 | 3.1e-18 m | −0.074 mm | 0.074 mm | ✓ |

首步位移是自重加载的起步量，非零但很小、方向向下（Uy<0），**无突跳** → PASS。

## A.4 ★ 判据 3 · 自重合力对账 —— 这条不过，而且挖出了真缺陷

### A.4.1 反力的取得

`tofor`（`Residu.f90:4858` `tofor(ldofix)=tofor(ldofix)+eload(idofn) !! reaction=internal force`）
默认**不输出**：`1.glb` 的 `gid_f = 0`。
在 **scratch 副本**（不动算例目录）里把 `gid_f: 0 → 1` 重跑，`1.flavia.res` 多出 400 个
`tofor` 块。**自由节点上的 `tofor` 就是施加的外载**（约束节点上是外载+反力的和，不可直接用）。

### A.4.2 独立理论值

由 `1.cor`（鞋带公式算单元面积）+ `1.mat`（密度）+ `1.LOA` 的重力块
（`Define body force in each BLKS` → `9.81000E+00 0 -1 0 -1`，**g = 9.81**，方向 (0,−1)）
各单元自重按 1/4 集中到 4 个节点，再对自由节点求和。

### A.4.3 对账结果

```
理论 Σ Fy(自由节点)  = -2.663219e+09 N
实测 Σ Fy(自由节点)  = -2.663219e+09 N     （400 步完全恒定，spread = 0）
相对差              = 7.5e-08              ✓ 数值上完全闭合
```

**荷载确实进去了，而且精确。**——但它进到了**错误的物体**上。

### A.4.4 ★ 缺陷：分组、材料与几何三者错位

`1.glb` 的组定义（第 59/64 行）与实际网格几何：

| 组 | `.glb` 里的名字 | NELGROUP | 单元 | **实际几何** | 面积 | 材料 | ρ | E |
|---|---|---:|---|---|---:|---|---:|---:|
| 1 | **`Dam`** | 120 | 1–120 | x[0,478] y[−300,0] | **143 400 m²** | mat 1 | **2400** | 2.5e10 |
| 2 | **`Foundation`** | 196 | 121–316 | x[200,278] y[0,100] | **4 300 m²** | mat 2 | **0** | 1.0e10 |

x[0,478]×y[−300,0]、面积 143 400 m²、单元最大 3 333 m² —— **这是地基**。
x[200,278]×y[0,100]、面积 4 300 m²、单元 5–39 m² —— **这是 100 m 高的坝体**（底宽 78 m）。

**名字、材料与几何全部对调了。**
`1.mat` 里那对材料参数恰恰是教科书标准配对
（混凝土 ρ=2400 E=2.5e10 ν=0.167 ／ **无质量地基** ρ=0 E=1e10 ν=0.20）——
参数本身没错，**只是接到了相反的几何上**。这不是建模选择，是对调。

独立佐证：`max_tofor`（最大单节点力）= 7.848e7 N。
按大单元（3 333 m²）× 2400 × 9.81 ≈ 7.85e7 ✓；
若自重真在坝体（单元 ≤39 m²），最大单节点力应为 ~9e5 N，**差 87 倍**。

**备选假设定量排除**：若坝体承重，W = 4300×2400×9.81 = 1.012e8 N；
实测 2.663e9 N，**差 26.3 倍**。

### A.4.5 病因链（四次消融实验定位）

在 scratch 里逐个改单一字段重跑，看物理是否改变：

| # | 改动 | 坝顶相对位移 | 放大系数 | 结论 |
|---|---|---:|---:|---|
| 0 | 原样 | 2.21 mm | 1.114 | 基线 |
| a | `.glb` 组块 `MATNO` 字段对调（保字节长度） | 2.21 mm | 1.114 | **完全无影响 → 该字段是死的** |
| b | `.ele` 最后一列 1↔2 全表对调 | 2.21 mm | 1.114 | **完全无影响 → 该列是死的** |
| c | `1.mat` 两条 `ELASTIC_ISOTROPIC` 行对调 | 15.08 mm | 8.154 | 有影响 |
| d | `.glb` `MATNO_PROCESS: 1 2 → 2 1` | 15.08 mm | 8.154 | 有影响（与 c 逐位相同） |

> ★ **Deck ABI 新事实（两个诱饵字段）**：
> 单元→材料的链路是
> **单元在 `1.ele` 里的文件顺序 + 各组 `NELGROUP` → 组号 → `.glb` 的 `MATNO_PROCESS(igroup)` → `1.mat` 材料序号**。
> `.ele` 的最后一列、以及 `.glb` 组块里那个 `MATNO` 字段，**在本 deck 路径上都不被消费**。
> 两者看起来都像权威来源（尤其组块里就写着 `NELGROUP MATNO`），实际改了毫无反应。
> 这正是本项目主症状的教科书样本：**改了"看起来对的地方"，语法合法、求解器接受、物理不变。**
> 建议写进 `14-facts-deck-ast.md` / `data/deck-abi.json` 的诱饵字段清单。

但 d 单独改**还不是修复**：`train02c_dbg` 在 d 之下 `max|U| = 0.000000e+00`（一动不动）。
病因的另一半在 `1.LOA`：

```
 Time_curve_for_each_group  1
   1  0                      ← 组1 用曲线1（重力），组2 用曲线 0（无）
```

**自重只施加给组 1。** 于是：
- 原样：组1 = 地基几何 + 混凝土 → 3.376e9 N 全压在地基上（实测精确吻合）
- 只改 d：组1 变无质量 → 全场无自重；组2（坝体）**因为曲线号是 0，无论密度多大都拿不到重力** → 位移恒 0

### A.4.6 完整修复及其验证

两处字段（外加一处纯装饰的组名对调）：

```
1.glb   MATNO_PROCESS              1  2   →   2  1
1.LOA   Time_curve_for_each_group  1  0   →   0  1
1.glb   组名  "Dam" ↔ "Foundation"（仅可读性，求解器不消费）
```

scratch 里施加后重跑 `train02c_seismic_wave_compare`：

```
[判据3] 实测 Σ Fy(自由节点) = -1.012392e+08 N
[判据3] 理论 坝体自重       = -1.012392e+08 N   (4300 m² × 2400 × 9.81)
        → 逐位相同
```

| 指标 | 原样 | **完整修复后** | 力学预期（100 m 重力坝 @0.2g） |
|---|---:|---:|---|
| 自重合力 | 3.376e9 N（**压在地基上**） | **1.0124e8 N（坝体）** | 1.0124e8 N ✓ |
| 坝顶 \|Ux\| 绝对 | 9.42 mm | 28.96 mm | — |
| 坝踵 \|Ux\| | 8.46 mm | 3.97 mm | — |
| **坝顶相对位移** | **2.21 mm** | **27.04 mm** | cm 量级 ✓ |
| **放大系数 顶/底** | **1.114** | **7.29** | 明显放大 ✓ |
| 主周期 | 0.357 s | **0.381 s** | 100 m 重力坝一阶 0.3–0.4 s ✓ |

**未施加到算例目录。** 理由：这超出"修文件名大小写"的授权范围，且会改变算例物理、
使归档结果失效；"哪个才是本意"是建模决策，应由使用者拍板。补丁已验证，随时可落。

## A.5 判据 5 · 量级 —— 名义通过，但这条判据会放过错误算例

| 算例 | 坝顶 \|Ux\| 绝对 | 判据 5 判定 |
|---|---:|:--:|
| `_seismic_wave_compare` 原样 | **9.42 mm** | "cm 量级" → **✓ 通过** |

**但这个算例是错的。**9.42 mm 里有 8.46 mm 是**地基整体平动**，
坝体自身只变形了 2.21 mm；坝顶/坝踵放大系数只有 **1.114** ——
一个真的 100 m 重力坝在 0.2g 下放大系数应在 2–8，这里几乎不放大，
因为坝体 ρ=0 **没有惯性、不参与动力响应**，只是被动跟着地基平移。

> **建议把判据 5 改成两个量，原判据留作粗筛：**
> - **5a 坝顶相对位移**（坝顶 Ux − 坝踵 Ux）在 cm 量级 —— 原样 2.21 mm（偏小），修复后 27.0 mm ✓
> - **5b 放大系数**（坝顶/坝底 \|Ux\| 峰值比）显著 > 1 —— 原样 **1.11（判死）**，修复后 7.29 ✓
>
> 绝对位移量级判据对"地基整体平动"完全免疫，正是本例中最有迷惑性的地方。

## A.6 验收结论

| 判据 | `train02c_seismic_wave_compare` | `train02c_dbg` |
|---|:--|:--|
| 1 `fachv` 变化 | ✓ 2000 值全异，峰值=曲线 PGA 逐位一致 | ✗ 恒 0（`earthquake_curve=0 0`，设计如此，非地震算例） |
| 2 振荡非单调 | ✓ 137 次过零 | n/a（响应为数值零） |
| 3 自重合力对账 | 数值闭合到 7.5e-8，**但自重加在地基几何上** ✗ | 同（同一网格与 glb 缺陷） |
| 4 初始条件 | ✓ 无突跳 | ✓ |
| 5 量级 | 名义 ✓（9.42 mm）；按 5a/5b **✗**（相对位移 2.21 mm，放大 1.11） | n/a |

**→ 两个算例均不放行。**
文件名大小写修复本身正确、已独立复核（decoder 走完整棵树、求解器 Exit 0、与归档一致到 1e-8）；
挡住放行的是这两个 deck **先前就存在的、与大小写无关的**分组/材料/重力曲线三处错位，
修法已定位并验证，等使用者拍板。

## A.7 哪几条能固化成常驻检查

| 判据 | 自动化难度 | 说明 |
|---|---|---|
| **1 `fachv`** | **容易** | `grep fachv= 1.chk` → 统计互异值数、峰值。再加一条**强化检查**：峰值应等于 `.LOA` 对应曲线的 `max\|a\|`（本例逐位相同），能同时验出缩放/错位。**例外**：`type_ABC=VIE` 下 `fachv` 恒 0 才正常，需读 `.glb` 的 `type_ABC` 分流。 |
| **4 初始条件** | **容易** | 读首个 `DISPLACEMENT` 块，检查无突跳。 |
| **3 自重对账** | **中等，但价值最高（本轮就是它挖出缺陷的）** | 需要四件东西，都是可读的：① `1.cor`+`1.ele` 算单元面积/体积；② `MATNO_PROCESS` → `1.mat` 取密度（**不能用 `.ele` 末列或组块 `MATNO`，是诱饵**）；③ `1.LOA` 重力块取 g 与方向；④ `Time_curve_for_each_group` 判断哪些组真拿到重力。**唯一障碍**：反力默认不输出，需 `gid_f=1`。建议 harness 增加一个 `--diagnostic` 通道，自动在临时副本里置 `gid_f=1` 跑一遍。 |
| **2 振荡** | **中等** | 需要知道"坝顶节点"。取 `y_max` 在本例可行，但**通用性依赖算例声明关键节点** —— 而本例恰恰是几何语义被搞反的，自动取点也可能取错。建议算例目录里放一个 `probe_nodes.json`（坝顶/坝踵/基底）。 |
| **5a/5b 相对位移与放大系数** | **中等** | 同样需要坝顶+坝踵两个节点。一旦有 `probe_nodes.json` 就很容易，且**比绝对量级判据强得多**。 |

**建议的落地顺序**：判据 1 与 4 立刻可做（纯读 `.chk`/`.res`，零改动）；
判据 3 做成 harness 的诊断通道，收益最大；判据 2/5 等 `probe_nodes.json` 约定确立后再做。

## A.8 本轮新增的仪器 bug

- **#4（我的，被同一个坑咬了两次）**：`1.flavia.res` 有 **8 类结果块**，其中
  `DISPLACEMENT`、`acceleration`、`acceleration_ab` **都是 3 列**，
  `STRESS`/`SIGxx` 是别的列数。只按列数过滤会静默混入加速度和应力。
  第一次得到 2.29e6（应力），第二次 9.79（加速度 ≈ g）。
  **两次都得到了"看起来能自圆其说的坏结果"**，不会触发怀疑。
  必须按块头分段。已改为 `header == "DISPLACEMENT"` 分段 + 恰好 3 列。
- **#5（生产代码里的诱饵）**：`.ele` 末列与 `.glb` 组块 `MATNO` 不被消费（A.4.5）。
  任何"改了材料号但物理没变"的调试都会在这里空转。
