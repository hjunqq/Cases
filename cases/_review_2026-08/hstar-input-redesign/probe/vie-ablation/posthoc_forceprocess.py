#!/usr/bin/env python3
"""POST-HOC (NOT pre-registered, NOT counted in the verdict score).

The registered ablation found fachv non-zero but the solution unchanged. The
reason turned out to be a confound in train10 itself: Fem.f90:13527
`if(force_process(igroup)==0) cycle` skips the whole fachv inertia loop, and
train10's 1.glb carries force_process = 0 0 0 0 0.

This script re-runs the same ablation pair with force_process = 1 1 1 1 1, to
separate "VIE suppresses fachv" from "train10 happens to disable it". Results
are labelled POST-HOC everywhere they appear.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CASE = Path("/home/huijun/HSTAR_Next/cases/cases/train10_dynamic_vie")
ROOT = Path("/tmp/claude-1000/probe-vie")
SOLVE = "/home/huijun/HSTAR_Next/fem-chat/harness/_solve_deck.py"
STALE = ("1.flavia.res", "1max.flavia.res", "1.chk", "run.log")

RUNS = {"ph_base_fp": ("0", "0"), "ph_var_fp": ("2", "0")}


def build(run: str, eq: tuple[str, str]) -> Path:
    dst = ROOT / run
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(CASE, dst, symlinks=True)
    for pat in STALE:
        (dst / pat).unlink(missing_ok=True)
    for p in list(dst.glob("result_b*.vtp")) + list(dst.glob("run_*.log")):
        p.unlink()

    man = (dst / "1.man").read_bytes().decode("latin-1").split("\n")
    t = man[1].split()
    t[2], t[3] = eq
    man[1] = "  " + "  ".join(t)
    (dst / "1.man").write_bytes("\n".join(man).encode("latin-1"))

    glb = (dst / "1.glb").read_bytes().decode("latin-1").split("\n")
    i = next(k for k, l in enumerate(glb) if l.strip().startswith("force_process"))
    assert glb[i + 1].split() == ["0"] * 5, glb[i + 1]
    glb[i + 1] = "  1  1  1  1  1"
    (dst / "1.glb").write_bytes("\n".join(glb).encode("latin-1"))
    print(f"{run}: earthquake_curve={eq}  force_process=1 1 1 1 1")
    return dst


def main() -> None:
    for run, eq in RUNS.items():
        d = build(run, eq)
        r = subprocess.run([sys.executable, SOLVE, str(d)], capture_output=True,
                           text=True, timeout=950,
                           env={**__import__("os").environ, "HSTAR_SUITE_TIMEOUT": "900"})
        print(run, "->", r.stdout.strip().splitlines()[1:3])


if __name__ == "__main__":
    main()
