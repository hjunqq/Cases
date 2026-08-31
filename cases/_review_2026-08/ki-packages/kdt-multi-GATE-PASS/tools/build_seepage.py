#!/usr/bin/env python3
"""build_seepage — configure steady/transient seepage and the coupled consolidation modes.
(Capabilities 8 and 9.)

TWO DISTINCT PATHS, often confused:

A. PURE SEEPAGE FIELD (`nflow /= 0`, W degree of freedom)
   Solves the Laplace / transient groundwater equation on its own field. Outputs
   `WATER-HEAD` (m) and `PORE-PRESSURE` (Pa). Steady state is `kstat`-like behaviour on
   the field equation; transient uses `theta1` (0.5 Crank-Nicolson, 1.0 backward Euler).
   `nfreeflownode` + `listfreeflownode` declare the nodes that may sit on a free surface
   (seepage-face / phreatic boundary). `<probn>.aqu` carries the aquifer records.

B. COUPLED CONSOLIDATION (`mdofn` 7 or 8)
   `mdofn=7` + `lmdofn(7)/=0` -> `static_U_P`   (u-p, hydrostatic pressure DOF)
   `mdofn=8` + `lmdofn(8)/=0` -> `static_U_Pw`  (u-pw, Biot pore pressure DOF)
   These need COUPLED ELEMENT TYPES -- indices 11-19 and 24 in the element library
   (T6C3, Q8C4, H10C4, B20C8, T3C3, Q4C4, H4C4, B8C8, L2C2, PR6C6). Declaring
   `lmdofn(8)=3` while the group block still says plain `Q4` (index 5) produces a run
   that converges and reports zero pore pressure everywhere -- the classic silent failure
   (triplet dt_015).

FLUID material phase (Material.f90 FLUID branch) supplies:
    density ratio bulkw            density kg/m3, bulk modulus of water Pa
    permiability(1:ndimn)          m/s, one value per coordinate direction

UNIT TRAP: HSTAR takes permeability as a HYDRAULIC CONDUCTIVITY in m/s, not an intrinsic
permeability in m2. Entering 1e-13 m2 instead of 1e-6 m/s makes the domain effectively
impermeable and every transient run reports the initial condition unchanged (triplet dt_016).

Usage:
    python3 build_seepage.py --case /tmp/mycase --describe
    python3 build_seepage.py --case /tmp/mycase --nflow 1 --free-nodes 12 13 14
    python3 build_seepage.py --case /tmp/mycase --coupled up      # u-p  (mdofn 7)
    python3 build_seepage.py --case /tmp/mycase --coupled upw     # u-pw (mdofn 8)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (ELEMENT_INDEX, GlbDoc, HstarInputError, probn_of,  # noqa: E402
                       tokens)

COUPLED_INDICES = {11, 12, 13, 14, 15, 16, 17, 18, 19, 24}


def _glb(case):
    return GlbDoc(Path(case) / f"{probn_of(case)}.glb")


def _group_indices(g):
    keys = {v[0].upper() for v in ELEMENT_INDEX.values()}
    out = []
    for i in range(g.section["_after_average_appear"], len(g.lines)):
        tk = tokens(g.lines[i])
        if tk and tk[0].upper() in keys:
            for t in tk[1:]:
                if t.lstrip("-").isdigit():
                    out.append((tk[0], int(t)))
                    break
        if len(out) >= g.ngroup:
            break
    return out


def describe(case):
    g = _glb(case)
    lm = [int(t) for t in tokens(g.lines[g.section["lmdofn"]])[:g.mdofn]]
    groups = _group_indices(g)
    return {
        "nflow": g.get("nflow"),
        "mdofn": g.mdofn, "lmdofn": lm,
        "pressure_dof_active": {"hydrostatic(7)": (g.mdofn >= 7 and lm[6] != 0),
                                "pore_water(8)": (g.mdofn >= 8 and lm[7] != 0)},
        "element_groups": [{"keyword": k, "index": i,
                            "coupled": i in COUPLED_INDICES} for k, i in groups],
        "theta1": g.get("theta1"), "type_problem": g.get("type_problem"),
        "uwcpl": g.get("uwcpl"), "nswkw": g.get("nswkw"),
        "nfreeflownode": g.value.get("nfreeflownode", "(record absent -- nflow==0)"),
    }


def set_flow(case, nflow=None, free_nodes=None):
    """Turn the seepage field on/off. Adding the `nfreeflownode` record requires nflow/=0."""
    g = _glb(case)
    before = g.get("nflow")
    if nflow is not None:
        if int(nflow) != 0 and "nfreeflownode" not in g.value:
            raise HstarInputError(
                "nflow is currently 0, so .glb has NO `nfreeflownode` record. HSTAR reads "
                "that record only when nflow/=0, so it must be INSERTED after the "
                "`nfreeflownode` header line before nflow can be switched on. Copy a case "
                "that already has it (cases/train12_seepage_steady) instead of patching "
                "this one -- the record sequence is positional (docs/input_preparation.md "
                "§0.1).")
        g.set("nflow", nflow)
    if free_nodes is not None:
        if "listfreeflownode" not in g.section:
            raise HstarInputError(
                "no free-flow node list record present; see the message above")
        npoin = int(g.get("npoin"))
        for n in free_nodes:
            if not 1 <= int(n) <= npoin:
                raise HstarInputError(f"free-flow node {n} outside 1..{npoin}")
        g.set("nfreeflownode", len(free_nodes))
        g.lines[g.section["listfreeflownode"]] = "  " + "  ".join(
            str(int(n)) for n in free_nodes)
    g.save()
    return {"nflow": {"from": before, "to": g.get("nflow")},
            "n_free_nodes": len(free_nodes) if free_nodes else None}


def set_coupled(case, mode):
    """`mode` is 'up' (mdofn 7, hydrostatic pressure) or 'upw' (mdofn 8, Biot pore water)."""
    if mode not in ("up", "upw"):
        raise HstarInputError("mode must be 'up' or 'upw'")
    slot = 7 if mode == "up" else 8
    g = _glb(case)
    if g.mdofn < slot:
        raise HstarInputError(
            f"mdofn={g.mdofn} but the {mode} path needs DOF slot {slot}. Raise mdofn AND "
            f"extend the lmdofn / order_time_mdofn rows to {slot} entries -- both are read "
            f"with an explicit count.")
    lm = [int(t) for t in tokens(g.lines[g.section["lmdofn"]])[:g.mdofn]]
    ndimn = int(g.get("ndimn"))
    lm = [0] * g.mdofn
    for d in range(ndimn):
        lm[d] = d + 1
    lm[slot - 1] = ndimn + 1
    g.lines[g.section["lmdofn"]] = "  " + "  ".join(f"{v:>3d}" for v in lm)
    g.save()
    groups = _group_indices(g)
    bad = [k for k, i in groups if i not in COUPLED_INDICES]
    warn = None
    if bad:
        warn = (f"element group(s) {bad} use an UNCOUPLED element index. A u-p/u-pw run "
                f"with uncoupled elements converges and reports zero pressure everywhere "
                f"(triplet dt_015). Switch them to a coupled index: "
                + ", ".join(f"{i}={ELEMENT_INDEX[i][0]}" for i in sorted(COUPLED_INDICES)))
    return {"mode": mode, "mdofn": g.mdofn, "lmdofn": lm, "cdofn": ndimn + 1,
            "warning": warn}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--nflow", type=int)
    ap.add_argument("--free-nodes", nargs="+", type=int)
    ap.add_argument("--coupled", choices=["up", "upw"])
    a = ap.parse_args(argv)
    out = {"before": describe(a.case)}
    if a.nflow is not None or a.free_nodes:
        out["flow"] = set_flow(a.case, a.nflow, a.free_nodes)
    if a.coupled:
        out["coupled"] = set_coupled(a.case, a.coupled)
    if a.nflow is not None or a.free_nodes or a.coupled:
        out["after"] = describe(a.case)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
