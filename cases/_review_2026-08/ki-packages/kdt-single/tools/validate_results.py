#!/usr/bin/env python3
"""
validate_results.py -- Stage s11: check an HSTAR run before believing it.

Four layers, cheapest first:

  1. RUN HEALTH      exit status, `.chk` convergence ratios, iteration cap hit
  2. PLAUSIBILITY    |u|max vs model size (catches E in MPa),
                     |sigma|max vs the material strength scale
  3. EQUILIBRIUM     sum of reactions + sum of applied load ~ 0.
                     This is the structural analogue of a water-balance check
                     and it is the only cheap test that catches "the load was
                     never applied": a face list that matched nothing, a
                     gravity curve id of 0, or a group switched off by
                     APPEAR_PROCESS all give a converged run with a wrong,
                     smooth, plausible-looking field.
  4. BENCHMARK       compare a named result against a reference series and
                     report NSE / KGE / PBIAS / RMSE / r plus, for FEM
                     verification, the max relative error -- which is the
                     metric the field actually grades on.

Built-in closed-form references (`--analytic`):

  confined_column   1-D confined (oedometer) compression under self weight.
                    sigma_yy(y) = -rho*g*(H-y)
                    u_y(y)      = -(rho*g/M) * (H*y - y^2/2)
                    M = E(1-nu) / ((1+nu)(1-2nu))          [plane strain]
                    Exact at the nodes for linear elements, so the expected
                    agreement is round-off, not discretisation error.

  lame_cylinder     thick-walled cylinder, internal pressure pi, plane strain
                    u_r(r) = (1+nu)*pi*a^2 / (E*(b^2-a^2)) *
                             ((1-2nu)*r + b^2/r)

Usage
-----
  python3 validate_results.py --output_dir out1 --case c1 --model-size 10 \
      --analytic confined_column --rho 2400 --g 9.81 --E 2.5e10 --nu 0.2 --H 10
  python3 validate_results.py --output_dir out1 --reference ref.csv --var DISPLACEMENT
"""

import argparse
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_common import (all_metrics, check_displacement_plausibility,  # noqa
                          check_equilibrium, max_rel_error, rel_error)
from hstar_io import read_tokens  # noqa: E402
from parse_results import collect  # noqa: E402
from write_boundary import read_cor  # noqa: E402


# ------------------------------------------------------------------ analytic
def confined_column(y, rho, g, E, nu, H, plane_strain=True):
    """Vertical displacement of a laterally confined column under self weight."""
    if plane_strain:
        M = E * (1.0 - nu) / ((1.0 + nu) * (1.0 - 2.0 * nu))
    else:
        M = E / (1.0 - nu * nu)
    return -(rho * g / M) * (H * y - 0.5 * y * y)


def confined_column_stress(y, rho, g, H):
    return -rho * g * (H - y)


def lame_ur(r, pi, a, b, E, nu):
    return ((1.0 + nu) * pi * a * a / (E * (b * b - a * a))
            * ((1.0 - 2.0 * nu) * r + b * b / r))


# ------------------------------------------------------------------ helpers
def latest_block(blocks, name):
    cand = [b for b in blocks if b["name"] == name]
    if not cand:
        return None
    tmax = max(b["time"] for b in cand)
    return [b for b in cand if b["time"] == tmax][-1]


def gravity_is_active(case_dir):
    """True when the .loa body-force record carries a non-zero `gravy`.

    Without this guard the equilibrium layer compares pressure-only reactions
    against a zero self weight and reports a spurious violation.
    """
    path = os.path.join(case_dir, "1.loa")
    if not os.path.exists(path):
        return False
    lines = open(path, errors="replace").read().split("\n")
    for k, line in enumerate(lines):
        if "body force" in line.lower():
            t = read_tokens(lines[k + 1])
            try:
                return abs(float(t[0])) > 1e-12 and \
                    any(abs(float(v)) > 1e-12 for v in t[1:])
            except (ValueError, IndexError):
                return False
    return False


def applied_gravity_force(case_dir, rho, g):
    """Total self weight of the mesh, from the .cor/.ele and a uniform rho."""
    nodes = read_cor(os.path.join(case_dir, "1.cor"))
    area = 0.0
    with open(os.path.join(case_dir, "1.ele"), errors="replace") as fh:
        for line in fh:
            t = read_tokens(line)
            if len(t) < 4:
                continue
            conn = [int(x) for x in t[1:-1]]
            if len(conn) != 4:
                return None
            pts = [nodes[n][:2] for n in conn]
            a = 0.0
            for i in range(4):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % 4]
                a += x1 * y2 - x2 * y1
            area += 0.5 * a
    return rho * g * area


def read_reference_csv(path):
    xs, ys = [], []
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].startswith("#"):
                continue
            xs.append(float(row[0]))
            ys.append(float(row[1]))
    return xs, ys


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--case", default="")
    ap.add_argument("--var", default="DISPLACEMENT")
    ap.add_argument("--component", type=int, default=1,
                    help="0-based component of a vector/matrix block")
    ap.add_argument("--magnitude", action="store_true",
                    help="use the vector magnitude instead of one component "
                         "(the radial displacement of an axisymmetric problem)")
    ap.add_argument("--model-size", dest="model_size", type=float)
    ap.add_argument("--analytic", choices=["confined_column", "lame_cylinder"])
    ap.add_argument("--reference", default="")
    ap.add_argument("--rho", type=float, default=2400.0)
    ap.add_argument("--g", type=float, default=9.81)
    ap.add_argument("--E", type=float, default=2.5e10)
    ap.add_argument("--nu", type=float, default=0.2)
    ap.add_argument("--H", type=float, default=10.0)
    ap.add_argument("--pi", type=float, default=1.0e6)
    ap.add_argument("--a", type=float, default=1.0)
    ap.add_argument("--b", type=float, default=2.0)
    ap.add_argument("--plane-stress", dest="plane_stress", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    report = {"output_dir": os.path.abspath(a.output_dir), "checks": []}

    # --- layer 1: run health -------------------------------------------
    res = collect(a.output_dir)
    conv = res.get("convergence") or {}
    health = {"layer": "run_health",
              "final_ratio_force": conv.get("final_ratio_force"),
              "final_ratio_disp": conv.get("final_ratio_disp"),
              "parse_problems": res["problems"]}
    fr = conv.get("final_ratio_force")
    health["ok"] = bool(res["blocks"]) and (fr is None or fr < 1e-3)
    if not health["ok"]:
        health["message"] = ("final force residual ratio %s is not small, or no "
                             "result blocks were written" % fr)
    report["checks"].append(health)

    blk = latest_block(res["blocks"], a.var)
    if blk is None:
        report["checks"].append({"layer": "presence", "ok": False,
                                 "message": "no %r block in the results; "
                                            "available: %s"
                                 % (a.var, sorted({b["name"]
                                                   for b in res["blocks"]}))})
        print(json.dumps(report, indent=2))
        return 1

    if a.magnitude:
        vals = [math.sqrt(sum(v * v for v in row)) for row in blk["values"]]
    else:
        vals = [row[a.component] if a.component < len(row) else row[-1]
                for row in blk["values"]]
    absmax = max(abs(v) for v in vals)

    # --- layer 2: plausibility -----------------------------------------
    if a.model_size:
        pl = check_displacement_plausibility(absmax, a.model_size, a.E)
        pl["layer"] = "plausibility"
        report["checks"].append(pl)

    # --- layer 3: equilibrium ------------------------------------------
    if a.case and res["reactions"] and not gravity_is_active(a.case):
        report["checks"].append({
            "layer": "equilibrium", "ok": None,
            "message": "self weight is not active in this case, so the "
                       "built-in gravity resultant is not a valid reference. "
                       "Supply the applied resultant explicitly to check "
                       "equilibrium for a pressure- or point-loaded model."})
    elif a.case and res["reactions"]:
        rsum = sum(res["reactions"][-1]["values"])
        applied = applied_gravity_force(a.case, a.rho, a.g)
        if applied is not None:
            eq = check_equilibrium([rsum], [-applied], tol=1e-4,
                                   label="vertical self weight")
            eq["layer"] = "equilibrium"
            report["checks"].append(eq)
        else:
            report["checks"].append({
                "layer": "equilibrium", "ok": None,
                "message": "self-weight resultant is only computed for 4-node "
                           "2-D meshes; supply the applied load explicitly for "
                           "other element types"})

    # --- layer 4: benchmark --------------------------------------------
    if a.analytic and a.case:
        nodes = read_cor(os.path.join(a.case, "1.cor"))
        ref, sim, coord = [], [], []
        for nid, v in zip(blk["nodes"], vals):
            c = nodes[nid]
            if a.analytic == "confined_column":
                ref.append(confined_column(c[1], a.rho, a.g, a.E, a.nu, a.H,
                                           not a.plane_stress))
            else:
                r = math.hypot(c[0], c[1])
                ref.append(lame_ur(r, a.pi, a.a, a.b, a.E, a.nu))
            sim.append(v)
            coord.append(c[1] if a.analytic == "confined_column" else
                         math.hypot(c[0], c[1]))
        m = all_metrics(ref, sim)
        mre = max_rel_error(ref, sim)
        i_ext = max(range(len(ref)), key=lambda k: abs(ref[k]))
        bench = {"layer": "benchmark", "reference": a.analytic,
                 "metrics": m, "max_rel_error": mre,
                 "extreme_reference": ref[i_ext],
                 "extreme_simulated": sim[i_ext],
                 "extreme_rel_error": rel_error(ref[i_ext], sim[i_ext]),
                 "n_points": len(ref),
                 "ok": mre is not None and mre < 0.01}
        bench["message"] = ("max relative error %.3e over %d nodes"
                            % (mre, len(ref)) if mre is not None else "n/a")
        report["checks"].append(bench)
        report["series"] = {"coordinate": coord, "reference": ref,
                            "simulated": sim}

    if a.reference:
        xs, ys = read_reference_csv(a.reference)
        m = all_metrics(ys, vals[:len(ys)])
        report["checks"].append({"layer": "benchmark",
                                 "reference": os.path.abspath(a.reference),
                                 "metrics": m,
                                 "ok": m["nse"] is not None and m["nse"] > 0.9})

    report["ok"] = all(c.get("ok") is not False for c in report["checks"])
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(report, fh, indent=2)
    printable = dict(report)
    printable.pop("series", None)
    print(json.dumps(printable, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
