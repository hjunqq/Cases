#!/usr/bin/env python3
"""build_contact_joints — configure node-pair contact, Goodman joints and thin layers.
(Capability 10.)

THE CONTROL RECORD (last numeric record of `<probn>.glb`, before `nrcsteel`):

    ngaps ngapb ctt_pe miter_bt torbt iblkbt nonsbt xlwsol method_gapi miter_state
    type_solver_ctt restart_ctt damp_ctt istatec

    ngaps            number of contact-pair GROUPS  (0 = no contact)
    ngapb            number of contact BLOCK groups (rigid-block kinematics)
    ctt_pe           contact penalty/element flag
    miter_bt         max iterations of the contact (bisection/trial) loop -- 500 in the
                     shipped cases
    torbt            contact-force tolerance (1e-5 shipped)
    iblkbt           block id the contact loop belongs to
    nonsbt           non-symmetric contact flag
    xlwsol           lower-bound solution flag
    method_gapi      gap-interpolation method
    miter_state      max contact-STATE (open/closed/slip) iterations
    type_solver_ctt  solver used for the contact sub-problem ('PROFILE' / 'PARDISO')
    restart_ctt      restart the contact state from `.ctt`
    damp_ctt         contact damping
    istatec          initial contact state (1 = closed)

`<probn>.ctt` is the UNFORMATTED contact-state restart file HSTAR writes and re-reads; it is
not human-editable and must be deleted (or `restart_ctt` set to 0) when the mesh changes,
otherwise HSTAR reads a state array sized for the OLD mesh (triplet dt_017).

GOODMAN JOINTS are a MATERIAL, not a contact group: a group of zero-thickness interface
elements whose material record is `GOODMAN`. Its sub-record carries the joint model name and
the normal/shear stiffnesses kn, ks in Pa/m plus cohesion (Pa), friction angle (DEGREES) and
tensile strength (Pa). `MCJOINT` under `CLASSICALEP` is the thin-layer alternative used by
cases/train05_slope_stability.

STIFFNESS SCALING TRAP: kn and ks are stiffness PER UNIT AREA (Pa/m), so their magnitude must
be ~100-1000x the adjacent solid's E divided by a representative element size. Values that
are too small let the joint interpenetrate (negative gap, unphysical); values that are too
large make the global matrix ill-conditioned and PARDISO returns tiny pivots. See
diagnostics/triplets.yaml dt_018.

Usage:
    python3 build_contact_joints.py --case /tmp/mycase --describe
    python3 build_contact_joints.py --case /tmp/mycase --miter-bt 800 --torbt 1e-6 \
        --type-solver-ctt PARDISO
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import GlbDoc, HstarInputError, probn_of, tokens, write_lines  # noqa: E402

FIELDS = ["ngaps", "ngapb", "ctt_pe", "miter_bt", "torbt", "iblkbt", "nonsbt", "xlwsol",
          "method_gapi", "miter_state", "type_solver_ctt", "restart_ctt", "damp_ctt",
          "istatec"]
INT_POS = {0, 1, 2, 3, 5, 6, 7, 8, 9, 11, 13}
FLOAT_POS = {4, 12}
CHAR_POS = {10}


def _locate(case):
    probn = probn_of(case)
    g = GlbDoc(Path(case) / f"{probn}.glb")
    hdr = g.find("ngaps")
    li = hdr + 1
    tk = tokens(g.lines[li])
    if len(tk) < len(FIELDS):
        raise HstarInputError(
            f"{probn}.glb:{li + 1} has {len(tk)} tokens, HSTAR reads {len(FIELDS)} "
            f"({' '.join(FIELDS)})")
    return g, li, tk


def describe(case):
    g, li, tk = _locate(case)
    d = dict(zip(FIELDS, tk[:len(FIELDS)]))
    d["line"] = li + 1
    d["contact_active"] = int(float(d["ngaps"])) != 0 or int(float(d["ngapb"])) != 0
    ctt = Path(case) / f"{probn_of(case)}.ctt"
    d["ctt_file"] = {"path": str(ctt),
                     "bytes": ctt.stat().st_size if ctt.is_file() else 0,
                     "note": "unformatted contact-state restart; delete it when the mesh "
                             "changes or set restart_ctt=0 (triplet dt_017)"}
    return d


def configure(case, **kw):
    g, li, tk = _locate(case)
    changed = {}
    for k, v in kw.items():
        if v is None:
            continue
        if k not in FIELDS:
            raise HstarInputError(f"unknown contact field {k!r}; valid: {FIELDS}")
        p = FIELDS.index(k)
        if p in CHAR_POS:
            new = str(v).upper()
            if new not in ("PROFILE", "PARDISO", "JPCG", "PBCG"):
                raise HstarInputError(f"type_solver_ctt={v!r}; valid PROFILE/PARDISO/"
                                      f"JPCG/PBCG")
        elif p in FLOAT_POS:
            new = f"{float(v):.3E}"
            if k == "torbt" and not 0 < float(v) < 1:
                raise HstarInputError(
                    f"torbt={v}: the contact-force tolerance is relative and must be in "
                    f"(0,1); the shipped cases use 1e-5")
        else:
            new = str(int(v))
            if k == "miter_bt" and int(v) < 1:
                raise HstarInputError("miter_bt must be >= 1")
        changed[k] = {"from": tk[p], "to": new}
        tk[p] = new
    g.lines[li] = "  " + "  ".join(tk)
    g.save()
    return changed


def clear_contact_state(case):
    """Delete the unformatted `.ctt` restart so a changed mesh cannot read a stale state."""
    p = Path(case) / f"{probn_of(case)}.ctt"
    n = p.stat().st_size if p.is_file() else 0
    if p.is_file():
        p.write_bytes(b"")
    return {"path": str(p), "bytes_cleared": n}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--ngaps", type=int)
    ap.add_argument("--ngapb", type=int)
    ap.add_argument("--miter-bt", type=int)
    ap.add_argument("--miter-state", type=int)
    ap.add_argument("--torbt", type=float)
    ap.add_argument("--damp-ctt", type=float)
    ap.add_argument("--istatec", type=int)
    ap.add_argument("--restart-ctt", type=int)
    ap.add_argument("--type-solver-ctt")
    ap.add_argument("--clear-state", action="store_true")
    a = ap.parse_args(argv)
    out = {"before": describe(a.case)}
    kw = {"ngaps": a.ngaps, "ngapb": a.ngapb, "miter_bt": a.miter_bt,
          "miter_state": a.miter_state, "torbt": a.torbt, "damp_ctt": a.damp_ctt,
          "istatec": a.istatec, "restart_ctt": a.restart_ctt,
          "type_solver_ctt": a.type_solver_ctt}
    if any(v is not None for v in kw.values()):
        out["changes"] = configure(a.case, **kw)
        out["after"] = describe(a.case)
    if a.clear_state:
        out["cleared"] = clear_contact_state(a.case)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
