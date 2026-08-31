# 三个 HSTAR KI 包 — 供人工核对

2026-08-26。同一个被审对象（HSTAR，Fortran 结构有限元求解器），三种产出方式并排放在这里。

| 目录 | 谁做的 | 规模 | 裁判结果 |
|---|---|---|---|
| `kdt-multi-GATE-PASS/` | KDT 多 agent 版自动生成，本机 `claude` CLI 作 builder，485 秒 | SKILL.md 584 行 · 33 triplets · 20 tools · 13 docs | **GATE PASS**，零 failure |
| `kdt-single/` | KDT-single 自动生成，50 分钟 | SKILL.md 509 行 · 32 triplets | `ki_incomplete`，8 条（4 环境缺件 / 2 裁判误判 / 2 真实缺陷） |
| `handmade-by-us/` | 我按 KISS 规格手工搭的 | SKILL.md 199 行 · 13 triplets · 无 tools/docs | 未过（故意没建 tools/ 与 docs/，工具指向仓库现有 skills/） |

## 核对时值得重点看的

**一、内容真伪。**自动生成的知识如果是幻觉，过了裁判也没价值。抽查过 5 项、0 项虚构，但只是抽查：

- `SKILL.md` 的 `type_problem` 映射写了 **5 类**（`Q` 静力 / `S` 时变 / `F` 动力 / `E` 反应谱 / `W` 纯模态）。
  **比我们自己的 `CLAUDE.md` 多一类** —— 我们标着"human-confirmed · highest priority"的表里只有 4 类、把模态记作 `E`。
  源码 `Fem.f90:1933-1944` 站在 KI 这边：`E → response_spectrum`，`W → frequency_analysis`。
- `dag.yaml` 提到 `.opw` / `.dis` / `.oew` / `.oit` / `.oip` 五个输出扩展名，我们的 `glossary.md` 一个都没收录，
  逐个回源码验证**全部真实存在**。
- 单位表每行标了 "verified from"，抽查全对（E/应力 = Pa、γw = 9810 N/m³、热扩散率 m²/day）。

**二、它的盲区（已知）。**漏掉的全是"从算例和失败史里长出来的知识"，不在 `.f90` 字面里：

- `ifixvar=8` 的水头 BC 必须同时写 `jfixvar=ndimn`，否则 `vdofix` 在 `Fem.f90:12326` 被绕过
- 重力坝分组顺序必须 group1 = 地基
- VIE 用 `earthquake_curve_d` / `_v` 而非 `earthquake_curve`
- `earthquake_curve` 的槽位 = 方向

agent 只拿到源码树，拿不到 `cases/cases/train*` 和几个月的 workflow 失败记录。
**这是方法的边界，不是这次实现的缺陷。**

**三、裁判本身有三个空洞**（核对时别把"过了裁判"当成"内容对"）：

1. `docs/gathered_papers.json` 的 `text_path` **一条都不验** —— multi 版那 16 篇论文的路径在磁盘上全部不存在，
   而规格 FILE 9 明文要求 `test -f` 证明文件在
2. MEDIUM 检查是**无词边界子串匹配** —— `safety_factor` 因描述里 "limit-state **sea**rch" 含 `sea`
   被判"命名了海洋介质"；8 个输出里 2 对 4 蒙 2 冤
3. `dag.yaml` 缺 `outputs` 键时 `if X and not Y` 短路 → 该检查零失败通过

## 出处

完整过程见同级目录的 `kdt-run-report.md`（816 行）与 `kdt-single-report.md`（817 行）。
