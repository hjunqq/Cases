#!/usr/bin/env python3
"""Build the 7 sandbox run directories for the VIE double-excitation ablation.

cases/ is read-only: every deck is copied to /tmp/claude-1000/probe-vie/<run>/
and only line 2 of 1.man (tokens 3..4, earthquake_curve(1:ndimn)) is edited.
"""
from __future__ import annotations

import shutil
from pathlib import Path

CASES = Path("/home/huijun/HSTAR_Next/cases/cases")
ROOT = Path("/tmp/claude-1000/probe-vie")

# run name -> (case, earthquake_curve override or None for "leave untouched")
RUNS = {
    "t10_base":     ("train10_dynamic_vie", None),
    "t10_base_rep": ("train10_dynamic_vie", None),
    "t10_var":      ("train10_dynamic_vie", ("2", "0")),
    "t02_on":       ("train02_gravdam_seismic", None),
    "t02_off":      ("train02_gravdam_seismic", ("0", "0")),
    "vie_base":     ("vie", None),
    "vie_var":      ("vie", ("2", "0")),
}

STALE = ("1.flavia.res", "1max.flavia.res", "1.chk", "run.log")


def set_eqcurve(man: Path, vals: tuple[str, str]) -> str:
    raw = man.read_bytes().decode("latin-1").split("\n")
    # line 0 is the label line, line 1 is the data record
    toks = raw[1].split()
    assert len(toks) >= 4, f"{man}: record too short: {raw[1]!r}"
    before = raw[1]
    toks[2], toks[3] = vals
    raw[1] = "  " + "  ".join(toks)
    man.write_bytes("\n".join(raw).encode("latin-1"))
    return f"{before.strip()!r} -> {raw[1].strip()!r}"


def main() -> None:
    import sys
    wanted = sys.argv[1:] or list(RUNS)
    ROOT.mkdir(parents=True, exist_ok=True)
    for run in wanted:
        case, override = RUNS[run]
        dst = ROOT / run
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(CASES / case, dst, symlinks=True)
        for pat in STALE:
            (dst / pat).unlink(missing_ok=True)
        for p in dst.glob("result_b*.vtp"):
            p.unlink()
        for p in dst.glob("run_*.log"):
            p.unlink()
        msg = set_eqcurve(dst / "1.man", override) if override else "unmodified"
        print(f"{run:14s} <- {case:26s} {msg}")


if __name__ == "__main__":
    main()
