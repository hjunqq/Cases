#!/usr/bin/env python3
"""Probe: .man reader layouts (open question #8), pre-registered.

Protocol: predictions.json was written and hashed BEFORE this script existed
and before any static reader's READ sequence was examined. This script
extracts the facts and renders the verdict mechanically. The agent does not
decide pass/fail — that is the whole point of the exercise. A probe whose
expectation is chosen after seeing the data proves nothing.

Outputs verdict.json (machine-readable) and prints a summary.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path("/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR")
CASES = Path("/home/huijun/HSTAR_Next/cases/cases")

RE_SUB = re.compile(r"^\s*(?:recursive\s+)?subroutine\s+(\w+)", re.I)
RE_READ = re.compile(r"read\s*\(\s*mainunit\s*,\s*\*\s*\)(?P<vars>.*)$", re.I)
# A label record: one variable, named text/textt/..., read only to be discarded.
RE_LABEL = re.compile(r"^\s*text\w*\s*$", re.I)


def split_vars(s: str) -> list[str]:
    """Split a READ's variable list on top-level commas (parens protect (1:ndimn))."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return [v for v in out if v]


def extract() -> dict:
    """reader -> ordered list of its mainunit READs (variable lists)."""
    readers: dict[str, list] = OrderedDict()
    for f in sorted(SRC.glob("*.f90")):
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        cur = "?"
        for i, raw in enumerate(lines, 1):
            m = RE_SUB.match(raw)
            if m:
                cur = m.group(1)
            r = RE_READ.search(raw)
            if not r:
                continue
            body = r.group("vars")
            if "!" in body:                      # trailing annotation
                body = body.split("!", 1)[0]
            readers.setdefault(cur, []).append(
                {"file": f.name, "line": i, "vars": split_vars(body)})
    return readers


def first_data_record(reads: list) -> list | None:
    """First READ that is not a discarded label record."""
    for r in reads:
        v = r["vars"]
        if len(v) == 1 and RE_LABEL.match(v[0]):
            continue
        return r
    return None


def norm(vars_: list[str]) -> tuple:
    """Layout signature: variable names with array sections kept (they set arity)."""
    return tuple(v.replace(" ", "").lower() for v in vars_)


def deck_first_record(path: Path) -> tuple[int, str] | None:
    """(token count, text) of the first DATA record of a .man file.

    v1 of this function returned the first non-empty line and every one of the
    21 decks 'failed' P6 identically — the signature of a broken instrument,
    not of 21 broken decks. The .man files open with a human-readable label
    record (`nincs,cdtest,earthquake_curve(1:ndimn)`) that the solver reads
    into `text` and discards. Skip any record whose tokens are not all
    numeric; that is what distinguishes a label from data here.
    """
    def numeric(t: str) -> bool:
        try:
            float(re.sub(r"^\d+\*", "", t))
            return True
        except ValueError:
            return False

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        # Trailing `!` annotation: the READ is already satisfied before it, so
        # the record tail never reaches the parser. Same rule as
        # import_glb._Deck._expand — which is itself the finding that this
        # deck-reading logic is duplicated and drifts between copies.
        raw = raw.split("!", 1)[0]
        toks = [t for t in re.split(r"[,\s]+", raw.strip()) if t]
        if not toks or not all(numeric(t) for t in toks):
            continue
        # expand n*v so the count matches what a list-directed READ consumes
        n = 0
        for t in toks:
            m = re.match(r"^(\d+)\*", t)
            n += int(m.group(1)) if m else 1
        return n, raw.strip()[:90]
    return None


def main():
    pred = json.loads((HERE / "predictions.json").read_text())
    pred_hash = hashlib.sha256((HERE / "predictions.json").read_bytes()).hexdigest()

    readers = extract()
    man = {k: v for k, v in readers.items() if k != "?"}

    STATIC4 = ["STATIC_U", "STATIC_U_reli", "STATIC_rigid_1", "STATIC_U_PW"]
    firsts = {k: first_data_record(v) for k, v in man.items()}
    layouts = {k: (norm(r["vars"]) if r else None) for k, r in firsts.items()}

    results = []

    def record(pid, passed, detail):
        results.append({"id": pid, "verdict": "PASS" if passed else "FALSIFIED",
                        "detail": detail})

    # P1 — the four 15-READ static readers share a first-record layout
    present = [s for s in STATIC4 if s in layouts]
    sigs = {s: layouts.get(s) for s in present}
    record("P1", len(set(sigs.values())) == 1 and present,
           {"readers": present, "layouts": {k: list(v) if v else None
                                            for k, v in sigs.items()}})

    # P2 — that first record reads exactly one variable
    arities = {s: (len(layouts[s]) if layouts.get(s) else None) for s in present}
    record("P2", bool(present) and all(a == 1 for a in arities.values()),
           {"arity": arities})

    # P3 — ALL static readers share one first-record layout
    static_all = [k for k in man if k.upper().startswith("STATIC")
                  or k.lower().startswith("back_")]
    ssig = {k: layouts.get(k) for k in static_all}
    distinct = {v for v in ssig.values() if v is not None}
    record("P3", len(distinct) == 1,
           {"readers": static_all, "distinct_layout_count": len(distinct),
            "layouts": {k: list(v) if v else None for k, v in ssig.items()}})

    # P4 — no static reader touches earthquake_curve
    offenders = {k: [r["line"] for r in man[k]
                     if any("earthquake_curve" in v.lower() for v in r["vars"])]
                 for k in static_all}
    offenders = {k: v for k, v in offenders.items() if v}
    record("P4", not offenders, {"offenders": offenders})

    # P5 — <= 5 distinct first-record layouts across all .man readers
    alld = {v for v in layouts.values() if v is not None}
    record("P5", len(alld) <= 5,
           {"distinct_count": len(alld),
            "layouts": sorted(list(x) for x in alld)})

    # P6 — read-back: each deck's .man first record vs the layout its switches select
    def expected_reader(tp, ts):
        if tp == "W":
            return "frequency_analysis"
        if tp == "E":
            return "response_spectrum"
        if tp == "Q":
            return "STATIC_U"
        return "explicit" if ts.upper() == "EXPLICIT" else "time_dependent"

    def deck_switches(glb: Path):
        txt = glb.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, l in enumerate(txt):
            if "TYPE_PROBLEM" in l and "TYPE_SOLVER" in l and i + 1 < len(txt):
                v = [x.strip("'\"") for x in
                     re.split(r"[,\s]+", txt[i + 1].strip()) if x]
                if len(v) >= 2:
                    return v[0], v[1]
        return None, None

    def ndimn_of(glb: Path):
        txt = glb.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, l in enumerate(txt):
            if "NPOIN" in l and "NELEM" in l and "NDIMN" in l and i + 1 < len(txt):
                hdr = [h for h in re.split(r"[,\s']+", l.strip()) if h]
                vals = [v for v in re.split(r"[,\s]+", txt[i + 1].strip()) if v]
                try:
                    return int(vals[hdr.index("NDIMN")])
                except (ValueError, IndexError):
                    return None
        return None

    checks, mismatches = [], []
    for d in sorted(CASES.glob("train*")):
        mp, gp = d / "1.man", d / "1.glb"
        if not (mp.exists() and gp.exists()):
            continue
        tp, ts = deck_switches(gp)
        nd = ndimn_of(gp)
        if tp is None or nd is None:
            checks.append({"case": d.name, "status": "skipped",
                           "why": "switches or ndimn unreadable"})
            continue
        rd = expected_reader(tp, ts or "")
        lay = layouts.get(rd)
        if lay is None:
            checks.append({"case": d.name, "status": "skipped",
                           "why": f"no layout for {rd}"})
            continue
        exp = sum(nd if "(1:ndimn)" in v else 1 for v in lay)
        got = deck_first_record(mp)
        ok = got is not None and got[0] == exp
        row = {"case": d.name, "type_problem": tp, "type_solver": ts,
               "ndimn": nd, "reader": rd, "expected_tokens": exp,
               "got_tokens": got[0] if got else None,
               "first_record": got[1] if got else None,
               "status": "match" if ok else "MISMATCH"}
        checks.append(row)
        if not ok:
            mismatches.append(row)
    record("P6", not mismatches,
           {"checked": len([c for c in checks if c["status"] != "skipped"]),
            "mismatches": mismatches,
            "skipped": [c for c in checks if c["status"] == "skipped"]})

    verdict = {
        "probe_id": pred["probe_id"],
        "predictions_sha256": pred_hash,
        "reader_count": len(man),
        "results": results,
        "first_records": {k: {"line": firsts[k]["line"] if firsts[k] else None,
                              "vars": list(layouts[k]) if layouts[k] else None}
                          for k in sorted(man)},
        "readback": checks,
    }
    (HERE / "verdict.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False))

    print(f"predictions sha256 = {pred_hash}")
    print(f".man readers found = {len(man)}\n")
    for r in results:
        print(f"  {r['id']}  {r['verdict']}")
    npass = sum(r["verdict"] == "PASS" for r in results)
    print(f"\n{npass}/{len(results)} 预测成立, {len(results)-npass} 条被证伪")
    print(f"详见 {HERE/'verdict.json'}")


if __name__ == "__main__":
    main()
