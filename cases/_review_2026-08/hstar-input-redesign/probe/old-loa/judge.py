#!/usr/bin/env python3
"""Probe: are the five suspect .LOA decks an older format? (open #1)

Pre-registered — see predictions.json + predictions.sha256. This script runs
the decks and renders the verdict mechanically; the agent does not decide
pass/fail.

Two safeguards carried over from the .man probe, where the instrument was
wrong three times:

  * a CONTROL deck (train01, known-good, current format). If the control does
    not complete, the instrument is broken and every other result is void —
    the script says so and refuses to interpret them.
  * P3 formalises "all five failed identically" as itself suspicious rather
    than as a finding.

Decks are copied to /tmp and run there. The archived 1.flavia.res in cases/
must never be overwritten — it is the only record that these ever ran.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/home/huijun/HSTAR_Next")
CASES = REPO / "cases" / "cases"
SOLVE = REPO / "fem-chat" / "harness" / "_solve_deck.py"
WORK = Path("/tmp/claude-1000/probe-old-loa")

SUSPECT = ["train_contact_nonlinear", "train_seepage", "train_seepage_stress",
           "train_slope_unknown", "train_vie_boundary"]
CONTROL = "train01_gravdam_static"
TIMEOUT = 900

RE_READ_ERR = re.compile(
    r"forrtl.*severe|end-of-file|input statement requires|list-directed", re.I)

# Outputs the solver writes; everything else in the case dir is input.
OUTPUT_SUFFIXES = {".res", ".vtp", ".vtu", ".chk", ".flavia", ".msh",
                   ".pvd", ".log", ".out"}


def stage(case: str) -> Path:
    src, dst = CASES / case, WORK / case
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for p in sorted(src.iterdir()):
        if p.is_file():
            shutil.copy2(p, dst / p.name)
    # Drop pre-existing results so a stale file cannot be mistaken for output.
    for p in list(dst.iterdir()):
        if any(s in p.suffixes for s in OUTPUT_SUFFIXES) or p.name.endswith(
                (".flavia.res", ".flavia.msh")):
            p.unlink()
    return dst


def run(case: str) -> dict:
    d = stage(case)
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, str(SOLVE), "."], cwd=d,
                           capture_output=True, text=True, timeout=TIMEOUT)
        out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
        timed_out = False
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace")
               + (e.stderr or b"").decode("utf-8", "replace"))
        code, timed_out = None, True
    secs = round(time.time() - t0, 1)

    res = d / "1.flavia.res"
    size = res.stat().st_size if res.exists() else 0
    chk = d / "1.chk"
    chk_text = chk.read_text(encoding="utf-8", errors="replace") if chk.exists() else ""

    if timed_out:
        cls = "timeout"
    elif RE_READ_ERR.search(out) or RE_READ_ERR.search(chk_text):
        cls = "read_error"
    elif code == 0 and size > 0:
        cls = "completed"
    else:
        cls = "other_error"

    arch = CASES / case / "1.flavia.res"
    return {
        "case": case, "class": cls, "exit": code, "seconds": secs,
        "res_bytes": size,
        "archived_res_bytes": arch.stat().st_size if arch.exists() else None,
        "chk_bytes": len(chk_text),
        "chk_has_global_stage": bool(re.search(
            r"npoin|nelem|global|ngroup", chk_text, re.I)),
        "tail": out.strip().splitlines()[-6:],
    }


def main():
    pred_path = HERE / "predictions.json"
    pred = json.loads(pred_path.read_text())
    pred_hash = hashlib.sha256(pred_path.read_bytes()).hexdigest()
    print(f"predictions sha256 = {pred_hash}\n")

    runs = {}
    print(f"控制组 {CONTROL} …", flush=True)
    runs[CONTROL] = run(CONTROL)
    print(f"   → {runs[CONTROL]['class']}  ({runs[CONTROL]['seconds']}s)", flush=True)

    for c in SUSPECT:
        print(f"{c} …", flush=True)
        runs[c] = run(c)
        print(f"   → {runs[c]['class']}  ({runs[c]['seconds']}s)", flush=True)

    results = []

    def record(pid, passed, detail, na=False):
        results.append({"id": pid,
                        "verdict": "N/A" if na else ("PASS" if passed else "FALSIFIED"),
                        "detail": detail})

    ctrl_ok = runs[CONTROL]["class"] == "completed"
    record("C0", ctrl_ok, {"control": runs[CONTROL]})

    sus = [runs[c] for c in SUSPECT]
    classes = [r["class"] for r in sus]

    record("P1", any(c == "read_error" for c in classes), {"classes": classes})
    record("P2", not any(c == "completed" for c in classes), {"classes": classes})
    record("P3", len(set(classes)) > 1,
           {"distinct": sorted(set(classes)), "classes": classes})

    comp = [r for r in sus if r["class"] == "completed"]
    if not comp:
        record("P4", None, {"note": "no completed case"}, na=True)
    else:
        record("P4", all(r["res_bytes"] != r["archived_res_bytes"] for r in comp),
               {"completed": [{"case": r["case"], "new": r["res_bytes"],
                               "archived": r["archived_res_bytes"]} for r in comp]})

    failed = [r for r in sus if r["class"] != "completed"]
    record("P5", any(r["chk_has_global_stage"] for r in failed) if failed else False,
           {"failed": [{"case": r["case"], "chk_bytes": r["chk_bytes"],
                        "global_stage": r["chk_has_global_stage"]} for r in failed]})

    verdict = {"probe_id": pred["probe_id"], "predictions_sha256": pred_hash,
               "control_ok": ctrl_ok, "runs": runs, "results": results}
    (HERE / "verdict.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False))

    print()
    if not ctrl_ok:
        print("  C0  FALSIFIED —— 控制组未通过。")
        print("  仪器判定为故障；P1-P5 的结果不得解读。")
    else:
        for r in results:
            print(f"  {r['id']}  {r['verdict']}")
        scored = [r for r in results if r["verdict"] != "N/A"]
        npass = sum(r["verdict"] == "PASS" for r in scored)
        print(f"\n{npass}/{len(scored)} 成立")
    print(f"详见 {HERE/'verdict.json'}")


if __name__ == "__main__":
    main()
