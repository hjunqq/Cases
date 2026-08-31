#!/usr/bin/env python3
"""Judge for open #9 (pre-registered). Mechanical; the agent does not decide."""
import hashlib, json, re, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from deck_ast import (SRC, logical_lines, RE_SUB, RE_IF_THEN, RE_SELECT,
                      RE_DO, RE_DO_LBL, RE_END_DO, RE_END_IF, RE_END_SELECT,
                      RE_LEAD_LBL, parse_file)

base = json.loads((HERE / "baseline.json").read_text())
ph = hashlib.sha256((HERE / "predictions.json").read_bytes()).hexdigest()
print(f"predictions sha256 = {ph}\n")

# ── closure after the fix, mirroring parse_subroutine's precedence ──
tot = bad = 0
rest = []
for f in sorted(SRC.glob("*.f90")):
    st = []
    for ln, t in logical_lines(f):
        m = RE_LEAD_LBL.match(t)
        if m and st and st[-1][0] == "dol" and st[-1][2] == m.group("lbl"):
            while st and st[-1][0] == "dol" and st[-1][2] == m.group("lbl"):
                st.pop()
            continue
        if RE_SUB.match(t):
            st = []
        elif RE_IF_THEN.match(t):
            st.append(("if", ln, None))
        elif RE_SELECT.match(t):
            st.append(("sel", ln, None))
        elif RE_DO_LBL.match(t):
            st.append(("dol", ln, RE_DO_LBL.match(t).group("lbl")))
        elif RE_DO.match(t) and not RE_END_DO.match(t):
            st.append(("do", ln, None))
        elif RE_END_IF.match(t) or RE_END_DO.match(t) or RE_END_SELECT.match(t):
            want = ("if" if RE_END_IF.match(t) else
                    "do" if RE_END_DO.match(t) else "sel")
            tot += 1
            if st and st[-1][0] == want:
                st.pop()
            else:
                bad += 1
                rest.append(f"{f.name}:{ln} end{want}")

# ── which subroutine each pre-fix mismatch sat in ──
subs = {}
for f in sorted(SRC.glob("*.f90")):
    for name, node in parse_file(f).items():
        subs.setdefault(f.name, []).append((node["line"], name))
def owner(fname, line):
    cands = [(l, n) for l, n in subs.get(fname, []) if l <= line]
    return max(cands)[1] if cands else "?"
hit = []
for fn, lns in base["mismatch_locations_before"].items():
    for ln in lns:
        o = owner(fn, ln)
        if o in base["acceptance_covered_subroutines"]:
            hit.append(f"{fn}:{ln} in {o}")

forms = ["labeled DO terminated by a labeled statement (not end do)",
         "named construct: `name: select case(...)` / `end select name`",
         "nested labeled DOs sharing one terminator label"]

v = subprocess.run([sys.executable, str(ROOT / "tools" / "verify_ast.py")],
                   capture_output=True, text=True)
verify_ok = v.returncode == 0
abi = json.loads((ROOT / "data" / "deck-abi.json").read_text())
n_abi = len(abi["deck_abi"])

res = []
def rec(pid, ok, detail):
    res.append({"id": pid, "verdict": "PASS" if ok else "FALSIFIED", "detail": detail})

rec("P1", len(forms) <= 5, {"form_count": len(forms), "forms": forms})
rec("P2", any("label" in f.lower() for f in forms), {"forms": forms})
rec("P3", not hit, {"mismatches_inside_covered_subroutines": hit})
rec("P4", bad == 0, {"mismatches_after": bad, "total_end": tot, "remaining": rest})
rec("P5", verify_ok, {"verify_ast": v.stdout.strip().splitlines()[-1] if v.stdout else "?"})
rec("P6", n_abi != base["deck_abi_records_before"],
    {"before": base["deck_abi_records_before"], "after": n_abi})

(HERE / "verdict.json").write_text(json.dumps(
    {"probe_id": "ast-construct-mismatch-v1", "predictions_sha256": ph,
     "closure_after": {"total": tot, "mismatches": bad},
     "results": res}, indent=2, ensure_ascii=False))
for r in res:
    print(f"  {r['id']}  {r['verdict']}")
n = sum(r["verdict"] == "PASS" for r in res)
print(f"\n{n}/{len(res)} 成立")
print(f"闭合：{tot} 个 end，失配 {bad}")
print(f"Deck ABI：{base['deck_abi_records_before']} → {n_abi}")
