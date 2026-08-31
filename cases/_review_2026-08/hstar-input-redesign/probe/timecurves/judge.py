#!/usr/bin/env python3
"""Probe `timecurves`: do the four unsupported .loa curve types actually load?

Registered before running: predictions.json (+ predictions.sha256).
Mechanical judgement only — this script classifies outcomes and compares them
against the registered `expect` field. Fixing the instrument is allowed;
editing predictions.json after the fact is not (the sha256 would break).

Substrate: cases/cases/test_arclength (9 nodes, 4 elements, 2D static Q).
Every variant is a full copy under /tmp; cases/ is never written.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/home/huijun/HSTAR_Next")
CASE = REPO / "cases" / "cases" / "test_arclength"
SOLVE = REPO / "fem-chat" / "harness" / "_solve_deck.py"
WORK = Path("/tmp/claude-1000/probe-timecurves")
TIMEOUT = 300

# ---------------------------------------------------------------- deck edits

BASE_LOA = """ (*.loa) Load data
  1
  2  LINEAR  0  2
  0  1
  1  1
"""


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _loa_split(text: str) -> tuple[list[str], list[str]]:
    """Split 1.LOA into (curve-table lines, everything after)."""
    lines = text.splitlines()
    # line0 = header text, line1 = ntcurve, then the curve records.
    # The curve table always ends right before the ' Define point load' label.
    for i, ln in enumerate(lines):
        if "Define point load" in ln:
            return lines[:i], lines[i:]
    raise SystemExit("cannot find 'Define point load' in 1.LOA")


def make_variant(name: str, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(CASE, dst, symlinks=True)
    # drop stale outputs so their presence proves this run produced them
    for stale in ("1.flavia.res", "run.log", "1.res", "1.resb"):
        f = dst / stale
        if f.exists() and not f.is_symlink():
            f.write_text("")
    (dst / "1.flavia.res").unlink(missing_ok=True)

    loa = dst / "1.LOA"
    head, tail = _loa_split(_read(loa))

    if name == "V0_baseline":
        new_head = head
    elif name == "V1_harmonic_identity":
        new_head = [head[0], "  1",
                    "  1  HARMONIC  0  1",
                    "  1.0  0.0  1.0  0.0  0.0  1.0E9"]
    elif name == "V2_waterlevel_identity":
        new_head = [head[0], "  1",
                    "  2  WATERLEVEL  0  2",
                    "  0  1",
                    "  1  1"]
    elif name == "V3_extrapolation_unreferenced":
        new_head = [head[0], "  2",
                    "  2  LINEAR  0  2", "  0  1", "  1  1",
                    "  1  EXTRAPOLATION  0  1",
                    "  1  0.0  1.0"]
    elif name in ("V4_arclength_unreferenced", "V5_arclength_active"):
        new_head = [head[0], "  2",
                    "  2  LINEAR  0  2", "  0  1", "  1  1",
                    "  1  ARCLENGTH  0  1",
                    "  0.0  0.1  1  5"]
    else:
        raise SystemExit(f"unknown variant {name}")

    loa.write_text("\n".join(new_head + tail) + "\n", encoding="utf-8")
    # 1.loa is a symlink to 1.LOA in the source case; keep it that way
    lo = dst / "1.loa"
    if lo.exists() and not lo.is_symlink():
        lo.write_text("\n".join(new_head + tail) + "\n", encoding="utf-8")

    if name == "V5_arclength_active":
        glb = dst / "1.glb"
        txt = _read(glb)
        out, hit = [], 0
        for ln in txt.splitlines():
            parts = ln.split()
            # the TYPE_PROBLEM record: Q PROFILE LOAD 5 0 0 ...
            if len(parts) > 2 and parts[1] == "PROFILE" and parts[2] == "LOAD":
                ln = ln.replace("PROFILE  LOAD", "PROFILE  ARCLENGTH", 1)
                hit += 1
            out.append(ln)
        if hit != 1:
            raise SystemExit(f"V5: expected 1 TYPE_LOAD record, patched {hit}")
        glb.write_text("\n".join(out) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ classify

def run(dst: Path) -> tuple[int, str]:
    try:
        p = subprocess.run([sys.executable, str(SOLVE), str(dst)],
                           capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return (-999, "TIMEOUT")
    log = ""
    rl = dst / "run.log"
    if rl.exists():
        log = _read(rl)
    return (p.returncode, log + "\n----stdout----\n" + (p.stdout or ""))


def classify(dst: Path, rc: int, log: str, baseline: str | None) -> str:
    if rc == -999:
        return "timeout"
    low = log.lower()
    res = dst / "1.flavia.res"
    # INSTRUMENT FIX (after first run, predictions untouched): the original
    # rule scanned the WHOLE log for "input"/"read", so a SIGSEGV in a run
    # whose ordinary stdout mentions "input" was mislabelled read_error.
    # Only the forrtl line itself decides.
    forrtl = [ln for ln in log.splitlines() if "forrtl" in ln.lower()]
    if forrtl:
        f0 = " ".join(forrtl).lower()
        if any(k in f0 for k in ("input conversion", "input statement",
                                 "end-of-file", "end of file",
                                 "list-directed", "input")):
            return "read_error"
        return "crash"
    if not res.exists():
        if "severe" in low or "segmentation" in low:
            return "crash"
        return "no_res"
    text = _read(res)
    if baseline is None:
        return "completed_baseline"
    return "completed_identical" if text == baseline else "completed_different"


def main() -> int:
    # integrity: predictions must not have changed
    pred_p = HERE / "predictions.json"
    want = (HERE / "predictions.sha256").read_text().split()[0]
    got = hashlib.sha256(pred_p.read_bytes()).hexdigest()
    if want != got:
        print(f"REFUSED: predictions.json changed since registration\n"
              f"  registered {want}\n  now        {got}")
        return 2
    pred = json.loads(pred_p.read_text())
    expect = {p["variant"]: (p["id"], p["expect"]) for p in pred["predictions"]}

    WORK.mkdir(parents=True, exist_ok=True)
    order = ["V0_baseline", "V1_harmonic_identity", "V2_waterlevel_identity",
             "V3_extrapolation_unreferenced", "V4_arclength_unreferenced",
             "V5_arclength_active"]

    baseline_res: str | None = None
    results = []
    for name in order:
        dst = WORK / name
        make_variant(name, dst)
        rc, log = run(dst)
        cls = classify(dst, rc, log, baseline_res)
        if name == "V0_baseline":
            if cls != "completed_baseline":
                print(f"CONTROL FAILED: V0 -> {cls}; all results void")
                (HERE / "verdict.json").write_text(json.dumps(
                    {"control": "FAILED", "v0_class": cls,
                     "tail": log.strip().splitlines()[-15:]},
                    ensure_ascii=False, indent=2), encoding="utf-8")
                return 1
            baseline_res = _read(dst / "1.flavia.res")
            cls = "completed_identical"
        pid, exp = expect[name]
        verdict = "PASS" if cls == exp else "FAIL"
        tail = [ln for ln in log.strip().splitlines() if ln.strip()][-8:]
        results.append({"id": pid, "variant": name, "returncode": rc,
                        "class": cls, "expected": exp, "verdict": verdict,
                        "log_tail": tail})
        print(f"{pid} {name:34s} rc={rc:<5} {cls:22s} expect={exp:22s} {verdict}")

    npass = sum(r["verdict"] == "PASS" for r in results)
    out = {"probe_id": pred["probe_id"],
           "predictions_sha256": got,
           "control": "PASS",
           "score": f"{npass}/{len(results)}",
           "results": results}
    (HERE / "verdict.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nscore {npass}/{len(results)}  -> verdict.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
