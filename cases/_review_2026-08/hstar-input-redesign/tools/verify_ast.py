#!/usr/bin/env python3
"""Acceptance for deck-ast.json: it must re-derive facts established elsewhere.

An extractor that cannot reproduce what we already know by hand and by
experiment is not evidence about the parts we don't know. Each check below
cites where the fact came from independently.
"""
import json, re, sys
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data"
ast = json.load(open(D / "deck-ast.json"))
tree = ast["trees"][ast["driver"]]

flat = []          # (kind, payload, path) in source-visit order
def walk(n, path=()):
    k = n.get("kind")
    if k == "READ":
        flat.append(("READ", n, path))
    elif k == "CALL":
        flat.append(("CALL", n["callee"], path))
        if "body" in n:
            walk(n["body"], path + (("CALL", n["callee"]),))
    elif k == "IF":
        for b in n["branches"]:
            walk(b["body"], path + (("IF", b["guard"]),))
    elif k == "SELECT":
        for c in n["cases"]:
            walk(c["body"], path + (("CASE", f'{n["expr"]}={c["value"]}'),))
    elif k == "LOOP":
        walk(n["body"], path + (("DO", n["bounds"]),))
    elif k == "SEQ":
        for c in n["body"]:
            walk(c, path)
walk(tree)

calls = [(p, x) for k, x, p in flat if k == "CALL"]
reads = [(p, x) for k, x, p in flat if k == "READ"]
ok = []

def check(name, cond, src, detail=""):
    ok.append(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    print(f"         依据: {src}")
    if detail:
        print(f"         {detail}")

# 1 — .ifs four sections, in call order (03-corrections #5, verified Fem.f90:200-203)
order = [c for _, c in calls if c in ("stiff_interface_fluid_solid",
         "stiff_absorb_fluid", "stiff_absorb_solid", "stiff_ifs2006")]
check(".ifs 四段调用顺序",
      order[:4] == ["stiff_interface_fluid_solid", "stiff_absorb_fluid",
                    "stiff_absorb_solid", "stiff_ifs2006"],
      "03-corrections #5 / Fem.f90:200-203", f"AST 给出: {order[:4]}")

# 2 — external_load_1 outside the block loop, _2 inside (03-corrections #3)
def in_block_loop(path):
    return any(k == "DO" and "iblks" in v.lower() for k, v in path)
p1 = [p for p, c in calls if c == "external_load_1"]
p2 = [p for p, c in calls if c == "external_load_2"]
check("external_load_1 在块循环外、_2 在循环内",
      bool(p1) and bool(p2) and not in_block_loop(p1[0]) and in_block_loop(p2[0]),
      "03-corrections #3 / 循环上下文分析",
      f"_1 in loop={in_block_loop(p1[0]) if p1 else '?'}, "
      f"_2 in loop={in_block_loop(p2[0]) if p2 else '?'}")

# 3 — .man dispatch (01-facts §3, verified by probe man-readers)
def guards(name):
    for p, c in calls:
        if c == name:
            return " ; ".join(v for k, v in p if k in ("IF", "CASE"))
    return None
gW, gE = guards("frequency_analysis"), guards("response_spectrum")
gT, gX = guards("time_dependent"), guards("explicit")
check(".man 调度守卫可还原",
      all(g is not None for g in (gW, gE, gT, gX))
      and "w" in (gW or "").lower() and "explicit" in (gX or "").lower(),
      "01-facts §3 / probe man-readers",
      f"frequency_analysis ⇐ {gW}\n         explicit ⇐ {gX}")

# 4 — the four .glb record arities the peel probe found by RUNNING the solver
want = {("Global.f90", 728): "19", ("Global.f90", 753): "11",
        ("Global.f90", 775): "11", ("Global.f90", 790): "7"}
got = {(r.get("file"), r["line"]): r["arity"] for _, r in reads
       if (r.get("file"), r["line"]) in want}
check(".glb 四条记录 arity 与剥洋葱实验一致",
      got == want, "13-probe-report-old-format-peel（动态实验）",
      f"AST 静态给出: {got}")

# 5 — every static .man reader's first data record is `nincs` (probe man-readers)
first = {}
for p, r in reads:
    if r["deck"] != ".man":
        continue
    sub = next((v for k, v in reversed(p) if k == "CALL"), None)
    if sub and sub not in first and not re.fullmatch(r"text\w*", r["vars"][0], re.I):
        first[sub] = r["vars"]
statics = {k: v for k, v in first.items()
           if k.upper().startswith("STATIC") or k.lower().startswith("back_")}
check("静力 .man reader 首记录均为 nincs",
      bool(statics) and all(v == ["nincs"] for v in statics.values()),
      "probe man-readers P1-P3",
      f"{len(statics)} 个: " + ", ".join(sorted(statics)))

print(f"\n{sum(ok)}/{len(ok)} 项验收通过")
sys.exit(0 if all(ok) else 1)
