#!/usr/bin/env python3
"""build_boundary_conditions — write / inspect `<probn>.pre` (prescribed variables, supports,
prescribed displacements, prescribed heads and temperatures).
(Capability 33 boundary side; needed by capabilities 1-13.)

`.pre` is read by `prescrib_set` (Prescrib.f90:183-250), ONCE PER LOAD BLOCK. Layout:

    text                                            header (positional -- must exist)
    nfixsets  nline
      repeat nfixsets times:
        ifixvar nfixnods itcurve tfixvar outfix jfixvar gamawx nextr    (type_ABC /= 'MIF')
        ifixvar ifixvar0 nfixnods itcurve tfixvar outfix jfixvar gamawx nextr  ('MIF')
        list_fix(1:nfixnods)                        node ids
        val_fix(1:nfixnods)                         values -- `11*0.` repeat form is legal

  ifixvar   DOF index: 1 Ux  2 Uy  3 Uz  4 Thx  5 Thy  6 Thz
                       7 Hydrostatic_pressure  8 Pore_Pressure  9 Air_Pressure 10 Temperature
  nfixnods  how many nodes in this set
  itcurve   time-curve id from .loa (0 = constant)
  tfixvar   the prescribed value multiplying the curve (m, Pa, degC ...)
  outfix    1 = write the reaction for this set to .opw
  jfixvar   secondary DOF flag
  gamawx    water unit weight, N/m3, used when the set prescribes a pressure/head DOF.
            The shipped cases use 0.980E+04 -- that is 9800 N/m3, i.e. SI. A value of 9.8
            here means kN/m3 were used and every pressure is 1000x too small.
  nextr     extrapolation-set flag (>0 pulls an extra node list)

THE BLOCK REPETITION TRAP (triplet dt_007): `.pre` holds ONE COMPLETE SET OF RECORDS PER
LOAD BLOCK. `cases/static` has nblks=2 and its `.pre` repeats the whole "PRESCRIBE SET"
group twice. Adding a load block without appending a matching `.pre` group gives
`forrtl: severe (24)` at the start of block 2 -- after block 1 has already produced output.

Usage:
    python3 build_boundary_conditions.py --case /tmp/mycase --describe
    python3 build_boundary_conditions.py --case /tmp/mycase --write bc.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (DOF_TITLE, GlbDoc, HstarInputError, probn_of,  # noqa: E402
                       read_lines, tokens, write_lines)

FIELDS = ["ifixvar", "nfixnods", "itcurve", "tfixvar", "outfix", "jfixvar",
          "gamawx", "nextr"]
FIELDS_MIF = ["ifixvar", "ifixvar0", "nfixnods", "itcurve", "tfixvar", "outfix",
              "jfixvar", "gamawx", "nextr"]


def _fields(case):
    probn = probn_of(case)
    g = GlbDoc(Path(case) / f"{probn}.glb")
    return (FIELDS_MIF if g.get("type_ABC").upper() == "MIF" else FIELDS), g


def read_pre(case):
    """Parse .pre into per-block lists of sets."""
    case = Path(case)
    probn = probn_of(case)
    fields, g = _fields(case)
    lines, eol = read_lines(case / f"{probn}.pre")
    blocks, i = [], 0
    while i < len(lines):
        while i < len(lines) and not tokens(lines[i]):
            i += 1
        if i >= len(lines):
            break
        i += 1                                       # header text
        if i >= len(lines):
            break
        tk = tokens(lines[i])
        nfixsets = int(float(tk[0]))
        i += 1
        sets = []
        for _ in range(nfixsets):
            while i < len(lines) and not tokens(lines[i]):
                i += 1
            tk = tokens(lines[i])
            if len(tk) < len(fields):
                raise HstarInputError(
                    f"{probn}.pre:{i + 1} has {len(tk)} tokens, HSTAR reads {len(fields)} "
                    f"({' '.join(fields)})")
            s = {f: tk[k] for k, f in enumerate(fields)}
            i += 1
            n = int(float(s["nfixnods"]))
            ids, vals = [], []
            while len(ids) < n:
                ids += tokens(lines[i]); i += 1
            while len(vals) < n:
                vals += tokens(lines[i]); i += 1
            s["nodes"] = [int(float(x)) for x in ids[:n]]
            s["values"] = [float(x) for x in vals[:n]]
            s["dof"] = DOF_TITLE.get(int(float(s["ifixvar"])), "?")
            sets.append(s)
        blocks.append(sets)
        if len(blocks) >= g.nblks:
            break
    return {"blocks": blocks, "fields": fields, "eol": eol,
            "path": str(case / f"{probn}.pre"), "nblks": g.nblks}


def write_pre(case, blocks):
    """Write .pre from a list (one entry per load block) of lists of set dicts."""
    case = Path(case)
    probn = probn_of(case)
    fields, g = _fields(case)
    npoin = int(g.get("npoin"))
    if len(blocks) != g.nblks:
        raise HstarInputError(
            f".pre needs one group of sets per load block: nblks={g.nblks}, got "
            f"{len(blocks)}. (This is the single most common EOF crash -- triplet dt_007.)")
    out = []
    for sets in blocks:
        out.append("                                    PRESCRIBE SET--NFIXSETS")
        out.append(f"  {len(sets)}  0")
        for s in sets:
            nodes = list(s["nodes"])
            if not nodes:
                raise HstarInputError("a prescribed set with zero nodes is not legal")
            for nd in nodes:
                if not 1 <= nd <= npoin:
                    raise HstarInputError(f"node {nd} outside 1..{npoin}")
            dof = int(s.get("ifixvar", s.get("dof_index", 1)))
            if dof not in DOF_TITLE:
                raise HstarInputError(
                    f"ifixvar={dof}; valid 1..10 ({DOF_TITLE})")
            gamawx = float(s.get("gamawx", 0.0))
            if dof in (7, 8, 9) and 0 < gamawx < 1000:
                raise HstarInputError(
                    f"gamawx={gamawx} N/m3 for a pressure DOF. SI water unit weight is "
                    f"9800; a value near 9.8 means kN/m3 and makes every pressure 1000x "
                    f"too small (triplet dt_008).")
            row = {"ifixvar": dof, "ifixvar0": int(s.get("ifixvar0", 0)),
                   "nfixnods": len(nodes), "itcurve": int(s.get("itcurve", 0)),
                   "tfixvar": float(s.get("tfixvar", 0.0)),
                   "outfix": int(s.get("outfix", 0)), "jfixvar": int(s.get("jfixvar", 0)),
                   "gamawx": gamawx, "nextr": int(s.get("nextr", 0))}
            out.append("  " + "  ".join(
                (f"{row[f]:.4E}" if f in ("tfixvar", "gamawx") else str(row[f]))
                for f in fields))
            out.append("  " + "  ".join(f"{n:>7d}" for n in nodes))
            vals = list(s.get("values") or [0.0] * len(nodes))
            if len(vals) != len(nodes):
                raise HstarInputError("values list must match nodes list length")
            out.append("  " + "  ".join(f"{v:.6E}" for v in vals))
    p = Path(case) / f"{probn}.pre"
    _, eol = read_lines(p)
    write_lines(p, out, eol)
    return {"path": str(p), "n_blocks": len(blocks),
            "sets_per_block": [len(b) for b in blocks]}


def describe(case):
    d = read_pre(case)
    return {"path": d["path"], "nblks": d["nblks"], "fields": d["fields"],
            "blocks": [[{"dof": s["dof"], "ifixvar": s["ifixvar"],
                         "n_nodes": len(s["nodes"]), "tfixvar": s["tfixvar"],
                         "itcurve": s["itcurve"], "gamawx": s["gamawx"],
                         "first_nodes": s["nodes"][:8]} for s in blk]
                       for blk in d["blocks"]]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--write", help="JSON file: [[{ifixvar,nodes,values,...}, ...], ...]")
    a = ap.parse_args(argv)
    if a.write:
        blocks = json.loads(Path(a.write).read_text())
        print(json.dumps(write_pre(a.case, blocks), indent=2))
        return 0
    print(json.dumps(describe(a.case), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
