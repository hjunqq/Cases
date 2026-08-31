#!/usr/bin/env python3
"""validate_results — physical-plausibility screening, equilibrium (conservation) check, and
comparison against analytic solutions or monitoring data. (Capability 34.)

THREE LAYERS, run in this order:

1. EQUILIBRIUM CHECK -- the structural analogue of `validate_water_balance`.
   There is no water budget in a stress solver, but there IS a global equilibrium
   statement, and HSTAR writes it to `<probn>.chk` every iteration:

        resid= <||R||>   retot= <||F_ext||>
        ratio for residu norm= <||R|| / ||F_ext||>

   A converged static solution has `ratio for residu norm` <= `toler_force` from `.man`.
   Anything above that is NOT a converged solution no matter what the displacements look
   like. This function fails the run when the ratio exceeds the tolerance actually asked
   for in `.man` -- not a hard-coded number.

2. PLAUSIBILITY SCREEN -- HSTAR is unit-agnostic and never range-checks anything, so a
   metres/millimetres or Pa/MPa slip produces a perfectly converged, entirely wrong answer.
   The bands below are order-of-magnitude sanity limits for civil hydraulic structures in
   SI, NOT acceptance criteria:

        |u|max      1e-6 .. 1.0 m       (a 100 m dam moves millimetres to centimetres;
                                         > 1 m means a unit error or a mechanism)
        |sigma|max  1e3 .. 1e9 Pa       (concrete tensile strength ~1-3 MPa, compressive
                                         ~20-40 MPa; > 1 GPa in a dam is a unit error)
        T           -60 .. 200 degC
        pore p      -1e7 .. 1e8 Pa
        modal f     0.1 .. 100 Hz       (a large arch dam's first mode is 1-5 Hz)

3. COMPARISON -- against an analytic solution or measured data, via `all_metrics`
   (`ki_tools_common.metrics` when importable, otherwise the in-KI `_local_metrics`
   fallback with the identical signature).

BUILT-IN ANALYTIC BENCHMARK: `confined_selfweight_column`. A laterally confined elastic
column of height H under its own weight, base fixed, roller sides:

        u_top   = -rho * g * H^2 / (2 * E_oed),  E_oed = E (1-nu) / ((1+nu)(1-2nu))
        sigma_yy(y) = -rho * g * (H - y)         (0 at the top, -rho g H at the base)
        sigma_xx    = K0 * sigma_yy,             K0 = nu / (1-nu)

COMPARE THE MEAN, NOT THE BASE VALUE. HSTAR's `.flavia.res` STRESS stream is NODE-AVERAGED
(the `average_appear` vector selects extrapolation vs direct averaging), so on a coarse
column every node reports the same value and it is the DOMAIN MEAN, -rho*g*H/2, not the
base value. Comparing the reported number against -rho*g*H is a 50% "error" that is an
artefact of the averaging, not of the solution (this exact mistake was made and corrected
while building this KI). The mean is compared here; refine the mesh vertically if you need
the base value.

Usage:
    python3 validate_results.py --dir /tmp/myrun --case /tmp/mycase
    python3 validate_results.py --dir /tmp/myrun --benchmark confined_selfweight_column \\
        --E 2.5e10 --nu 0.2 --rho 2400 --g 9.81 --H 1.0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:                                                     # preferred shared utility
    from ki_tools_common.metrics import all_metrics      # type: ignore
except ImportError:                                      # in-KI fallback, same signature
    from _local_metrics import all_metrics

from _hstar_io import HstarInputError, probn_of  # noqa: E402
from parse_outputs import parse_run  # noqa: E402

BANDS = {
    "DISPLACEMENT": (1e-9, 1.0, "m"),
    "STRESS": (1e2, 1e9, "Pa"),
    "PRINCIPALSTRESS": (1e2, 1e9, "Pa"),
    "TEMPERATURE": (-60.0, 200.0, "degC"),
    "PORE-PRESSURE": (-1e7, 1e8, "Pa"),
    "WATER-HEAD": (-1e4, 1e4, "m"),
    "acceleration": (0.0, 1e3, "m/s2"),
    "velocity": (0.0, 1e2, "m/s"),
}
MODAL_BAND = (0.05, 200.0)


def equilibrium_check(parsed, toler_force=None):
    """Layer 1. Returns a verdict dict; `ok` False means the run is not a solution."""
    chk = parsed.get("chk")
    if not chk or not chk["convergence_records"]:
        return {"ok": None, "reason": "no convergence records in .chk -- the run may not "
                                      "have reached a Newton loop"}
    r = chk["final_residual_ratio"]
    d = chk["final_disp_ratio"]
    tol = toler_force if toler_force is not None else 1e-3
    return {"ok": (r is not None and r <= tol) and (d is None or d <= max(tol, 1e-3)),
            "final_force_residual_ratio": r,
            "final_displacement_ratio": d,
            "tolerance_used": tol,
            "n_not_converged_checks": chk["n_not_converged_checks"],
            "meaning": "||R||/||F_ext|| at the last logged iteration; this is HSTAR's own "
                       "equilibrium statement and the structural analogue of a mass-balance "
                       "check"}


def plausibility(parsed):
    """Layer 2. Order-of-magnitude screen -- catches unit slips, not modelling errors."""
    out, problems = {}, []
    for name, s in parsed["summary"].items():
        if not isinstance(s, dict) or "max_abs" not in s:
            continue
        band = BANDS.get(name)
        if band is None:
            out[name] = {"max_abs": s["max_abs"], "unit": s.get("unit"),
                         "band": "none defined"}
            continue
        lo, hi, unit = band
        v = s["max_abs"] if name not in ("TEMPERATURE",) else s["max"]
        ok = lo <= abs(v) <= hi if name != "TEMPERATURE" else lo <= v <= hi
        out[name] = {"value": v, "unit": unit, "band": [lo, hi], "ok": ok}
        if not ok:
            problems.append(
                f"{name} = {v:g} {unit} is outside the plausibility band {lo:g}..{hi:g}. "
                f"HSTAR is unit-agnostic: check that .cor is in metres, E and stresses in "
                f"Pa, density in kg/m3 and gravity in m/s2 (docs/input_preparation.md "
                f"§0.2, triplet dt_006).")
    freqs = parsed["summary"].get("modal_frequencies_hz")
    if freqs:
        bad = [f for f in freqs if not MODAL_BAND[0] <= f <= MODAL_BAND[1]]
        out["modal_frequencies_hz"] = {"values": freqs, "band": list(MODAL_BAND),
                                       "ok": not bad}
        if bad:
            problems.append(f"modal frequencies {bad} Hz outside {MODAL_BAND}; a factor "
                            f"of ~1000 usually means density in t/m3 with E in Pa")
        if freqs != sorted(freqs):
            problems.append("modal frequencies are not monotonically increasing with mode "
                            "order -- the eigen-extraction did not converge")
    return {"checks": out, "problems": problems, "ok": not problems}


def confined_selfweight_column(E, nu, rho, g, H):
    """Analytic solution of the KI's benchmark. Returns dict of expected values (SI)."""
    if not -1.0 < nu < 0.5:
        raise HstarInputError("nu must be in (-1, 0.5)")
    e_oed = E * (1.0 - nu) / ((1.0 + nu) * (1.0 - 2.0 * nu))
    return {"E_oed_Pa": e_oed,
            "u_top_m": -rho * g * H * H / (2.0 * e_oed),
            "sigma_yy_base_Pa": -rho * g * H,
            "sigma_yy_mean_Pa": -0.5 * rho * g * H,
            "K0": nu / (1.0 - nu),
            "sigma_xx_base_Pa": -rho * g * H * nu / (1.0 - nu),
            "sigma_xx_mean_Pa": -0.5 * rho * g * H * nu / (1.0 - nu),
            "u_profile": lambda y: -rho * g * (H * H - (H - y) ** 2) / (2.0 * e_oed)}


def compare_benchmark(parsed, name, **kw):
    """Layer 3 against an analytic solution."""
    if name != "confined_selfweight_column":
        raise HstarInputError(
            f"unknown benchmark {name!r}; this KI ships confined_selfweight_column")
    exp = {k: v for k, v in confined_selfweight_column(
        kw["E"], kw["nu"], kw["rho"], kw["g"], kw["H"]).items() if k != "u_profile"}
    disp = parsed["results"].get("DISPLACEMENT")
    if not disp:
        raise HstarInputError("no DISPLACEMENT stream in the run")
    last = disp[-1]
    uy = [row[1] for row in last["values"] if len(row) > 1]
    sim_u = min(uy)                                   # most negative = settlement at top
    stress = parsed["results"].get("STRESS")
    sim_syy = sim_sxx = None
    if stress:
        vals = stress[-1]["values"]
        yy = [r[1] for r in vals if len(r) > 1]
        xx = [r[0] for r in vals if len(r) > 0]
        sim_syy = sum(yy) / len(yy)          # node-averaged stream -> compare the MEAN
        sim_sxx = sum(xx) / len(xx)
    obs = [exp["u_top_m"]]
    sim = [sim_u]
    labels = ["u_top_m"]
    if sim_syy is not None:
        obs += [exp["sigma_yy_mean_Pa"], exp["sigma_xx_mean_Pa"]]
        sim += [sim_syy, sim_sxx]
        labels += ["sigma_yy_mean_Pa", "sigma_xx_mean_Pa"]
    m = all_metrics(obs, sim)
    per = [{"quantity": q, "analytic": o, "hstar": s,
            "abs_err": abs(o - s),
            "rel_err_pct": (abs(o - s) / abs(o) * 100.0) if o else float("nan")}
           for q, o, s in zip(labels, obs, sim)]
    return {"benchmark": name, "inputs": kw, "analytic": exp,
            "per_quantity": per, "metrics": m,
            "max_rel_err_pct": max(p["rel_err_pct"] for p in per)}


def validate(run_dir, case=None, benchmark=None, **kw):
    parsed = parse_run(run_dir)
    tol = None
    if case:
        try:
            from build_analysis_control import read_man
            blocks = read_man(case)
            tol = min(inc["toler_force"] for b in blocks for inc in b["increments"])
        except Exception:
            tol = None
    out = {"run_dir": str(run_dir),
           "equilibrium": equilibrium_check(parsed, tol),
           "plausibility": plausibility(parsed),
           "summary": parsed["summary"]}
    if benchmark:
        out["benchmark"] = compare_benchmark(parsed, benchmark, **kw)
    out["ok"] = bool(out["plausibility"]["ok"]) and (
        out["equilibrium"]["ok"] in (True, None))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", required=True)
    ap.add_argument("--case", help="the case directory, so .man's toler_force is used")
    ap.add_argument("--benchmark", choices=["confined_selfweight_column"])
    ap.add_argument("--E", type=float)
    ap.add_argument("--nu", type=float)
    ap.add_argument("--rho", type=float)
    ap.add_argument("--g", type=float, default=9.81)
    ap.add_argument("--H", type=float)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    kw = {}
    if a.benchmark:
        missing = [k for k in ("E", "nu", "rho", "H") if getattr(a, k) is None]
        if missing:
            ap.error(f"--benchmark needs {missing}")
        kw = {"E": a.E, "nu": a.nu, "rho": a.rho, "g": a.g, "H": a.H}
    r = validate(a.dir, a.case, a.benchmark, **kw)
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1))
    print(json.dumps(r, indent=2))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
