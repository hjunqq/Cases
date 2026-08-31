#!/usr/bin/env python3
"""Derive the Deck ABI from deck-ast.json.

For every deck READ, the full path condition that must hold for the solver to
execute it: the conjunction of enclosing guards, plus the loop context. That
conjunction IS the dispatch rule — the thing no document states and no example
case can reveal.
"""
import json, re
from collections import Counter, defaultdict
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data"
ast = json.load(open(D / "deck-ast.json"))
tree = ast["trees"][ast["driver"]]

rows = []
def walk(n, guards=(), loops=(), sub=None):
    k = n.get("kind")
    if k == "READ":
        rows.append({"deck": n["deck"], "file": n.get("file"), "line": n["line"],
                     "reader": sub, "arity": n["arity"], "vars": n["vars"],
                     "guards": list(guards), "loops": list(loops)})
    elif k == "CALL":
        if "body" in n:
            walk(n["body"], guards, loops, n["callee"])
    elif k == "IF":
        for b in n["branches"]:
            walk(b["body"], guards + (b["guard"],), loops, sub)
    elif k == "SELECT":
        for c in n["cases"]:
            walk(c["body"], guards + (f'{n["expr"]}=={c["value"]}',), loops, sub)
    elif k == "LOOP":
        walk(n["body"], guards, loops + (n["bounds"],), sub)
    elif k == "SEQ":
        for c in n["body"]:
            walk(c, guards, loops, sub)
walk(tree)

# de-duplicate: the same statement reached by several call paths
uniq = {}
for r in rows:
    key = (r["file"], r["line"], tuple(r["guards"]))
    uniq.setdefault(key, r)
recs = list(uniq.values())

# ── switch inventory: variables tested in guards, and the values tested ──
SW = defaultdict(Counter)
CMP = re.compile(r"(\w+)\s*(==|/=|>=|<=|>|<)\s*('[^']*'|-?\d+)")
for r in recs:
    for g in r["guards"]:
        for var, op, val in CMP.findall(g):
            if var.lower() in ("i", "j", "n", "i0"):
                continue
            SW[var.lower()][val.strip("'")] += 1

out = {"deck_abi": recs,
       "switch_inventory": {k: dict(v.most_common()) for k, v in
                            sorted(SW.items(), key=lambda kv: -sum(kv[1].values()))}}
(D / "deck-abi.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

per = Counter(r["deck"] for r in recs)
print("每个 deck 文件的唯一 (记录 × 路径条件) 数：")
for d, n in per.most_common():
    print(f"   {d:<6} {n:4d}")
print(f"   合计   {len(recs)}")

print("\n守卫中出现最多的开关（变量 → 被测试过的取值）：")
for k, v in list(out["switch_inventory"].items())[:14]:
    print(f"   {k:<16} {list(v)[:9]}")

deep = sorted(recs, key=lambda r: -len(r["guards"]))[:3]
print("\n路径条件最深的记录：")
for r in deep:
    print(f"   {r['deck']} {r['file']}:{r['line']}  ({len(r['guards'])} 层)")
    for g in r["guards"]:
        print(f"        └ {g[:96]}")
print(f"\nwrote {D/'deck-abi.json'}")
