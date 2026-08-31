#!/usr/bin/env python3
"""Judge for open #10 — Bparameter semantics (pre-registered).

Everything derives from data/deck-ast.json (100% closure, 5/5 acceptance) and
the decks in cases/. The agent renders no verdict.
"""
import hashlib, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CASES = Path("/home/huijun/HSTAR_Next/cases/cases")
SRC = Path("/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR")

ph = hashlib.sha256((HERE / "predictions.json").read_bytes()).hexdigest()
print(f"predictions sha256 = {ph}\n")

ast = json.loads((ROOT / "data" / "deck-ast.json").read_text())
tree = ast["trees"][ast["driver"]]

paths = []
def walk(n, g=(), sub=None):
    k = n.get("kind")
    if k == "READ":
        paths.append((g, sub, n))
    elif k == "CALL":
        if "body" in n:
            walk(n["body"], g, n["callee"])
    elif k == "IF":
        for b in n["branches"]:
            walk(b["body"], g + (b["guard"],), sub)
    elif k == "SELECT":
        for c in n["cases"]:
            walk(c["body"], g + (f'{n["expr"]}=={c["value"]}',), sub)
    elif k == "LOOP":
        walk(n["body"], g, sub)
    elif k == "SEQ":
        for c in n["body"]:
            walk(c, g, sub)
walk(tree)

BP = re.compile(r"bparameter", re.I)
NEG12 = re.compile(r"bparameter\s*==\s*-\s*[12]", re.I)
POS = re.compile(r"bparameter\s*>\s*0", re.I)

res = []
def rec(pid, ok, detail):
    res.append({"id": pid, "verdict": "PASS" if ok else "FALSIFIED", "detail": detail})

vals, skipped = {}, []
for d in sorted(CASES.glob("train*")):
    g = d / "1.glb"
    if not g.exists():
        continue
    L = g.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, l in enumerate(L):
        if "TYPE_PROBLEM" in l and "TYPE_SOLVER" in l and i + 1 < len(L):
            v = [x.strip("'\"") for x in re.split(r"[,\s]+", L[i+1].strip()) if x]
            if len(v) >= 11:
                vals[d.name] = v[8]
            else:
                skipped.append({"case": d.name, "fields": len(v)})
            break
rec("P1", bool(vals) and all(v == "0" for v in vals.values()),
    {"values": vals, "skipped_old_format": skipped})

free = {}
for r in ("time_dependent", "STATIC_U"):
    ps = [g for g, s, _ in paths if s == r]
    free[r] = {"total_paths": len(ps),
               "without_neg12": sum(1 for g in ps if not any(NEG12.search(x) for x in g))}
rec("P2", any(v["without_neg12"] > 0 for v in free.values()), free)

key = lambda n: (n.get("file"), n["line"])
under_pos, elsewhere = set(), set()
for g, s, n in paths:
    (under_pos if any(POS.search(x) for x in g) else elsewhere).add(key(n))
only_pos = sorted(under_pos - elsewhere)
rec("P3", bool(only_pos),
    {"count": len(only_pos), "sample": [f"{a}:{b}" for a, b in only_pos[:10]]})

srcs = []
for f in sorted(SRC.glob("*.f90")):
    for i, l in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        # Strip the trailing comment before grepping. Sixth time in this
        # project that forgetting this rule produced a wrong answer — here it
        # turned a PASS into a FALSIFIED by counting two comment mentions.
        code = l.split("!", 1)[0]
        if re.search(r"read\s*\(", code, re.I) and BP.search(code):
            srcs.append(f"{f.name}:{i}")
decks = {n["deck"] for _, _, n in paths if any(BP.search(v) for v in n["vars"])}
rec("P4", len(srcs) == 1 and decks == {".glb"},
    {"read_statements": srcs, "decks": sorted(decks)})

preds = sorted({x.strip() for g, _, _ in paths for x in g if BP.search(x)})
rec("P5", len(preds) <= 8, {"count": len(preds), "predicates": preds})

bad = [list(g) for g, _, _ in paths
       if any("rci_request" in x.lower() for x in g) and not any(POS.search(x) for x in g)]
rec("P6", not bad, {"count": len(bad), "violating_paths": bad[:3]})

(HERE / "verdict.json").write_text(json.dumps(
    {"probe_id": "bparameter-semantics-v1", "predictions_sha256": ph, "results": res},
    indent=2, ensure_ascii=False))
for r in res:
    print(f"  {r['id']}  {r['verdict']}")
print(f"\n{sum(r['verdict']=='PASS' for r in res)}/{len(res)} 成立")
