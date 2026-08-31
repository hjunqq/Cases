#!/usr/bin/env python3
"""Coverage ledger: which Deck ABI cells do the existing cases actually exercise?

A case is a path through the ABI tree. Union the paths of all cases and you get
the honest answer to "how much of this solver do we understand", with a
denominator that is derived rather than guessed.

Cells never touched by any case are where the next silent-wrong-answer lives.
"""
import json, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from case_path import resolve, switches_from_deck

CASES = Path("/home/huijun/HSTAR_Next/cases/cases")
ast = json.load(open(ROOT / "data" / "deck-ast.json"))
tree = ast["trees"][ast["driver"]]
abi = json.load(open(ROOT / "data" / "deck-abi.json"))["deck_abi"]

total = {(r["file"], r["line"]) for r in abi}
by_deck_total = Counter(r["deck"] for r in abi)

covered, per_case = set(), {}
for d in sorted(CASES.glob("train*")):
    if not (d / "1.glb").exists():
        continue
    env = switches_from_deck(d)
    cells = {(r["file"], r["line"]) for r in resolve(tree, env) if r["certain"]}
    per_case[d.name] = cells
    covered |= cells

deck_of = {(r["file"], r["line"]): r["deck"] for r in abi}
cov_by_deck = Counter(deck_of[c] for c in covered if c in deck_of)

print(f"Deck ABI 记录位置 {len(total)} 个（去重到 file:line）")
print(f"{len(per_case)} 个算例确定覆盖 {len(covered & total)} 个 "
      f"({100*len(covered & total)/len(total):.1f}%)\n")
print("按文件：")
for d, n in by_deck_total.most_common():
    c = cov_by_deck.get(d, 0)
    print(f"   {d:<6} {c:4d} / {n:4d}   {100*c/n:5.1f}%")

print("\n每个算例新增覆盖（按加入顺序的边际贡献）：")
seen, rows = set(), []
for name, cells in per_case.items():
    new = len((cells & total) - seen)
    seen |= (cells & total)
    rows.append((name, len(cells & total), new))
for name, tot_, new in rows:
    bar = "█" * min(new // 2, 30)
    print(f"   {name:<30} 覆盖 {tot_:4d}  新增 {new:4d} {bar}")
print(f"\n未被任何算例覆盖：{len(total - covered)} 个 —— 下一个静默错误就住在这里")
