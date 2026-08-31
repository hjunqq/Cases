#!/usr/bin/env python3
"""build_analysis_control — choose the analysis type, solver, DOF set, time integration,
increment/step schedule and mesh-adaptivity switches.
(Capabilities 1, 4, 5, 9, 25, 32 of docs/capabilities.md.)

Edits, in a COPIED case:
  * `<probn>.glb`  -- type_problem / type_solver / type_load / type_nl / nlayer,
                      mdofn + lmdofn + order_time_mdofn, beeta1/beeta2/theta1,
                      meshc / rmesh
  * `<probn>.man`  -- per-block increment records
                      (miter ditime noutn noutf nstep inc_step nresta cwater Qstatic
                       + toler_force toler_var(1:mdofn))
  * `<probn>.sol`  -- PARDISO mtype / thread count / verbosity

ANALYSIS-TYPE MATRIX (Fem.f90 process_analysis, docs/analysis/program-flow.md)

  type_problem  'Q'  quasi-static      -> static_U / static_U_P / static_U_Pw / rigid / reli
                'F','D'  dynamic       -> time_dependent (Newmark) or explicit
                'S'  transient field   -> thermal / seepage field advance
                'E'  modal + response spectrum
                'W'  steady-state frequency domain (complex arithmetic)
  type_solver   'PARDISO' | 'PROFILE' | 'JPCG' | 'PBCG' | 'EXPLICIT'
  type_load     'LOAD' | 'LOAD2' (mechanical+thermal two-pass) | 'ARCLENGTH' | 'DISCONTROL'
                | 'MAT_DE' (strength reduction -- see build_stability_analysis.py)
  type_nl       8 = modified Newton (BFGS); anything else = full Newton-Raphson
                (5 is the value every shipped case uses)

DOF SET (`mdofn`, `lmdofn`) -- Global.f90 title(1:10)
  1 Ux  2 Uy  3 Uz  4 Thx  5 Thy  6 Thz  7 Hydrostatic_pressure  8 Pore_Pressure
  9 Air_Pressure  10 Temperature
  `lmdofn(i)=0` means the DOF is absent; a non-zero value is its COMPRESSED number. The
  compressed numbers must be 1..cdofn with no gaps -- e.g. plane U-Pw is
  mdofn=8, lmdofn=[1,2,0,0,0,0,0,3].

TIME INTEGRATION
  beeta1 = Newmark gamma, beeta2 = Newmark beta, theta1 = theta for the field (thermal /
  seepage) equation. 0.5 / 0.25 / 1.0 = average acceleration + fully implicit field:
  unconditionally stable, no algorithmic damping. The `static` template ships 0.6/0.302/0.6,
  which adds numerical damping -- do not copy that into a modal or wave-propagation run.

Usage:
    python3 build_analysis_control.py --case /tmp/mycase --type-problem F \\
        --type-solver PARDISO --beeta 0.5 0.25 1.0 \\
        --increment 200 0.01 1 10 500 1 50 --toler-force 1e-4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (GlbDoc, HstarInputError, probn_of, read_lines,  # noqa: E402
                       tokens, write_lines)

PROBLEM_TYPES = {"Q": "quasi-static", "F": "dynamic (Newmark)", "D": "dynamic",
                 "S": "transient field (thermal / seepage)",
                 "E": "modal + response spectrum", "W": "steady-state frequency domain"}
SOLVERS = {"PARDISO", "PROFILE", "JPCG", "PBCG", "EXPLICIT"}
LOAD_TYPES = {"LOAD", "LOAD2", "ARCLENGTH", "DISCONTROL", "MAT_DE"}
PARDISO_MTYPE = {2: "real symmetric positive definite", -2: "real symmetric indefinite",
                 11: "real unsymmetric"}


def set_glb(case, **kw):
    """Set named .glb scalars. Unknown keys raise rather than being ignored."""
    case = Path(case)
    probn = probn_of(case)
    g = GlbDoc(case / f"{probn}.glb")
    changed = {}
    for k, v in kw.items():
        if v is None:
            continue
        if k == "type_problem" and str(v) not in PROBLEM_TYPES:
            raise HstarInputError(f"type_problem={v!r}; valid: {sorted(PROBLEM_TYPES)}")
        if k == "type_solver" and str(v).upper() not in SOLVERS:
            raise HstarInputError(f"type_solver={v!r}; valid: {sorted(SOLVERS)}")
        if k == "type_load" and str(v).upper() not in LOAD_TYPES:
            raise HstarInputError(f"type_load={v!r}; valid: {sorted(LOAD_TYPES)}")
        before = g.get(k)
        g.set(k, v)
        changed[k] = {"from": before, "to": g.get(k)}
    g.save()
    return changed


def set_dofs(case, lmdofn, order_time=None):
    """Rewrite the DOF activation vector. `lmdofn` is a list of length mdofn."""
    case = Path(case)
    probn = probn_of(case)
    g = GlbDoc(case / f"{probn}.glb")
    if len(lmdofn) != g.mdofn:
        raise HstarInputError(f"lmdofn needs mdofn={g.mdofn} entries, got {len(lmdofn)}")
    active = [v for v in lmdofn if int(v) != 0]
    if sorted(int(v) for v in active) != list(range(1, len(active) + 1)):
        raise HstarInputError(
            f"lmdofn non-zero entries must be the compressed numbers 1..{len(active)} with "
            f"no gaps and no repeats; got {active}. HSTAR indexes nodfn() by these numbers, "
            f"so a gap silently mis-maps every equation.")
    li = g.section["lmdofn"]
    g.lines[li] = "  " + "  ".join(f"{int(v):>3d}" for v in lmdofn)
    if order_time is not None:
        if len(order_time) != g.mdofn:
            raise HstarInputError(f"order_time needs mdofn={g.mdofn} entries")
        g.lines[g.section["order_time_mdofn"]] = "  " + "  ".join(
            f"{int(v):>3d}" for v in order_time)
    g.save()
    return {"mdofn": g.mdofn, "lmdofn": list(map(int, lmdofn)), "cdofn": len(active)}


def write_man(case, blocks):
    """Rewrite <probn>.man.

    `blocks` is a list (one per load block) of dicts:
        {"header": "...", "nincs_line": [nincs, cdtest, *earthquake_curve],
         "increments": [{"miter":..., "ditime":..., "noutn":..., "noutf":...,
                         "nstep":..., "inc_step":..., "nresta":..., "cwater":0,
                         "Qstatic":0, "toler_force":1e-5, "toler_var":[...]}]}

    Any missing key inherits the value already in the template's corresponding record, so a
    caller can change only `nstep` without knowing the other eight fields.
    """
    case = Path(case)
    probn = probn_of(case)
    g = GlbDoc(case / f"{probn}.glb")
    mdofn, ndimn = g.mdofn, int(g.get("ndimn"))
    out = []
    for b in blocks:
        out.append(b.get("header", " nincs,cdtest,earthquake_curve(1:ndimn)"))
        nl = list(b.get("nincs_line") or [len(b["increments"])] + [0] * (1 + ndimn))
        nl[0] = len(b["increments"])
        out.append("  " + "  ".join(str(int(v)) for v in nl))
        for inc in b["increments"]:
            out.append("  " + "  ".join([
                str(int(inc.get("miter", 50))),
                f"{float(inc.get('ditime', 1.0)):.4E}",
                str(int(inc.get("noutn", 1))), str(int(inc.get("noutf", 1))),
                str(int(inc.get("nstep", 1))), str(int(inc.get("inc_step", 1))),
                str(int(inc.get("nresta", 1))), str(int(inc.get("cwater", 0))),
                str(int(inc.get("Qstatic", 0)))]))
            tv = inc.get("toler_var") or [inc.get("toler_force", 1e-5)] * mdofn
            if len(tv) != mdofn:
                raise HstarInputError(
                    f"toler_var needs mdofn={mdofn} entries (one per declared DOF slot), "
                    f"got {len(tv)}")
            out.append("  " + "  ".join(
                [f"{float(inc.get('toler_force', 1e-5)):.4E}"]
                + [f"{float(x):.4E}" for x in tv]))
    p = case / f"{probn}.man"
    _, eol = read_lines(p)
    write_lines(p, out, eol)
    return {"path": str(p), "n_blocks": len(blocks),
            "n_increments": [len(b["increments"]) for b in blocks]}


def read_man(case):
    """Parse the template's .man so a caller can edit one field and write it back."""
    case = Path(case)
    probn = probn_of(case)
    g = GlbDoc(case / f"{probn}.glb")
    lines, _ = read_lines(case / f"{probn}.man")
    mdofn = g.mdofn
    blocks, i = [], 0
    keys = ["miter", "ditime", "noutn", "noutf", "nstep", "inc_step", "nresta",
            "cwater", "Qstatic"]
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        header = lines[i]
        i += 1
        nl = [float(t) for t in tokens(lines[i])]
        nincs = int(nl[0])
        i += 1
        incs = []
        for _ in range(nincs):
            tk = tokens(lines[i])
            i += 1
            inc = {k: float(tk[j]) for j, k in enumerate(keys) if j < len(tk)}
            for k in keys:
                if k != "ditime" and k in inc:
                    inc[k] = int(inc[k])
            tk2 = tokens(lines[i])
            i += 1
            inc["toler_force"] = float(tk2[0])
            inc["toler_var"] = [float(x) for x in tk2[1:1 + mdofn]]
            if inc.get("cwater"):
                # coef_water rows follow; keep them verbatim by refusing to round-trip
                raise HstarInputError(
                    "this .man uses cwater/=0 (per-step water coefficients). Edit it by hand "
                    "or write it wholesale with write_man(); read_man() cannot round-trip it.")
            incs.append(inc)
        blocks.append({"header": header, "nincs_line": nl, "increments": incs})
    return blocks


def write_sol(case, mtype=-2, ncpu=4, msglvl=0, isdefault=0, nblocks=None):
    """Rewrite <probn>.sol -- one (mtype, ncpu, msglvl) + isdefault pair per load block."""
    if int(mtype) not in PARDISO_MTYPE:
        raise HstarInputError(
            f"PARDISO mtype={mtype}; valid: "
            + ", ".join(f"{k} ({v})" for k, v in PARDISO_MTYPE.items()))
    case = Path(case)
    probn = probn_of(case)
    g = GlbDoc(case / f"{probn}.glb")
    n = nblocks or g.nblks
    out = []
    for _ in range(n):
        out += [" mtype, ncpu, msglvl",
                f"  {int(mtype)}   {int(ncpu)}   {int(msglvl)}",
                " isdefault", f"  {int(isdefault)}"]
    p = case / f"{probn}.sol"
    _, eol = read_lines(p)
    write_lines(p, out, eol)
    return {"path": str(p), "mtype": int(mtype), "mtype_meaning": PARDISO_MTYPE[int(mtype)],
            "ncpu": int(ncpu), "blocks": n}


def describe(case):
    case = Path(case)
    probn = probn_of(case)
    g = GlbDoc(case / f"{probn}.glb")
    return {"probn": probn,
            "type_problem": g.get("type_problem"),
            "type_problem_meaning": PROBLEM_TYPES.get(g.get("type_problem"), "?"),
            "type_solver": g.get("type_solver"), "type_load": g.get("type_load"),
            "type_nl": g.get("type_nl"), "mdofn": g.mdofn,
            "lmdofn": [int(t) for t in tokens(g.lines[g.section["lmdofn"]])[:g.mdofn]],
            "beeta1": g.get("beeta1"), "beeta2": g.get("beeta2"),
            "theta1": g.get("theta1"), "nblks": g.nblks, "ngroup": g.ngroup,
            "meshc": g.get("meshc"), "rmesh": g.get("rmesh")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--type-problem", choices=sorted(PROBLEM_TYPES))
    ap.add_argument("--type-solver", choices=sorted(SOLVERS))
    ap.add_argument("--type-load", choices=sorted(LOAD_TYPES))
    ap.add_argument("--type-nl", type=int)
    ap.add_argument("--meshc", type=int)
    ap.add_argument("--rmesh", type=int)
    ap.add_argument("--beeta", nargs=3, type=float, metavar=("B1", "B2", "THETA"))
    ap.add_argument("--lmdofn", nargs="+", type=int)
    ap.add_argument("--increment", nargs=7, type=float,
                    metavar=("MITER", "DITIME", "NOUTN", "NOUTF", "NSTEP", "INC_STEP",
                             "NRESTA"),
                    help="replace every increment of every block with this one")
    ap.add_argument("--toler-force", type=float, default=1e-5)
    ap.add_argument("--mtype", type=int)
    ap.add_argument("--ncpu", type=int)
    ap.add_argument("--describe", action="store_true")
    a = ap.parse_args(argv)

    report = {"before": describe(a.case)}
    kw = {"type_problem": a.type_problem, "type_solver": a.type_solver,
          "type_load": a.type_load, "type_nl": a.type_nl,
          "meshc": a.meshc, "rmesh": a.rmesh}
    if a.beeta:
        kw.update(beeta1=a.beeta[0], beeta2=a.beeta[1], theta1=a.beeta[2])
    report["glb_changes"] = set_glb(a.case, **kw)
    if a.lmdofn:
        report["dofs"] = set_dofs(a.case, a.lmdofn)
    if a.increment:
        m, dt, non, nof, ns, ist, nr = a.increment
        blocks = read_man(a.case)
        for b in blocks:
            b["increments"] = [{"miter": int(m), "ditime": dt, "noutn": int(non),
                                "noutf": int(nof), "nstep": int(ns), "inc_step": int(ist),
                                "nresta": int(nr), "toler_force": a.toler_force}]
        report["man"] = write_man(a.case, blocks)
    if a.mtype is not None or a.ncpu is not None:
        report["sol"] = write_sol(a.case, mtype=a.mtype if a.mtype is not None else -2,
                                  ncpu=a.ncpu or 4)
    report["after"] = describe(a.case)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
