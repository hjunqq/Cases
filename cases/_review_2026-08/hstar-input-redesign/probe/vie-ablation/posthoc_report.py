#!/usr/bin/env python3
"""POST-HOC metrics (NOT pre-registered, NOT part of the verdict).

Prints:
  - full displacement-field comparisons (all nodes, all steps) rather than the
    single crest node, so that "no effect" can be distinguished from "no effect
    at the probe node";
  - the run-to-run noise floor (t10_base vs t10_base_rep) that any claimed
    effect has to exceed;
  - the force_process=1 pair from posthoc_forceprocess.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge  # noqa: E402

ROOT = judge.ROOT


def field(run: str):
    p = ROOT / run / "1.flavia.res"
    if not p.exists() or p.stat().st_size == 0:
        return None
    steps, inb = [], False
    for raw in p.open("rb"):
        line = raw.decode("latin-1").strip()
        if line.startswith("DISPLACEMENT"):
            inb = True
            steps.append([])
            continue
        if not inb:
            continue
        q = line.split()
        if len(q) == 3:
            try:
                int(q[0])
            except ValueError:
                inb = False
                continue
            steps[-1].append((float(q[1]), float(q[2])))
        else:
            inb = False
    return steps


def compare(a, b):
    m = scale = 0.0
    for sa, sb in zip(a, b):
        for (x1, y1), (x2, y2) in zip(sa, sb):
            m = max(m, abs(x1 - x2), abs(y1 - y2))
            scale = max(scale, abs(x1), abs(y1))
    return {"max_abs_diff": m, "field_peak": scale,
            "relative": (m / scale) if scale else None}


def main() -> None:
    runs = ["t10_base", "t10_base_rep", "t10_var", "ph_base_fp", "ph_var_fp"]
    f = {r: field(r) for r in runs}
    out = {"note": "POST-HOC, not pre-registered", "runs": {}, "comparisons": {}}
    for r in runs:
        out["runs"][r] = {
            "present": f[r] is not None,
            "steps": len(f[r]) if f[r] else 0,
            "nodes": len(f[r][0]) if f[r] else 0,
            "fachv_max": judge.fachv_max(r)[:2],
        }
    pairs = [
        ("t10_base", "t10_base_rep", "run-to-run noise floor"),
        ("t10_base", "t10_var", "registered ablation (force_process=0)"),
        ("t10_base", "ph_base_fp", "force_process 0 -> 1, no earthquake_curve"),
        ("ph_base_fp", "ph_var_fp", "POST-HOC ablation with force_process=1"),
    ]
    for a, b, label in pairs:
        if f[a] and f[b] and len(f[a]) == len(f[b]):
            out["comparisons"][f"{a} vs {b}"] = {"label": label, **compare(f[a], f[b])}
        else:
            out["comparisons"][f"{a} vs {b}"] = {"label": label, "error": "unusable"}
    (HERE / "posthoc.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
