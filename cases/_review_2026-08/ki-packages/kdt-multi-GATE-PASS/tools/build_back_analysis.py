#!/usr/bin/env python3
"""build_back_analysis — parameter inversion / back analysis against monitoring data.
(Capability 16.)

HSTAR has FIVE distinct inversion routes, selected by `Bparameter` on the
`TYPE_PROBLEM ...` record of `<probn>.glb`, with `balgor` choosing the optimiser
(Fem.f90 main program, docs/analysis/back-analysis.md):

  Bparameter  balgor  route                              what it recovers
  ----------  ------  ---------------------------------  --------------------------------
   1 or 2      0      parameter_back_analysis            material constants; Intel MKL
                                                         DTRNLSP (Levenberg-Marquardt)
                                                         with FINITE-DIFFERENCE Jacobian
   1 or 2      1      parameter_back_analysis            same, but ANALYTIC sensitivity
                                                         (`dudx`, Fem.f90:4291-4390) --
                                                         far cheaper, and the one to use
                                                         when the parameters are moduli
   1 or 2      2      trust_region_back_analysis         trust region + BFGS Hessian,
                                                         double dog-leg sub-problem
   3           -      rigid_dis_back_analysis            least-squares split of a measured
                                                         displacement into rigid-body and
                                                         elastic parts
   4           -      nodal_value_back_analysis          nodal field values from sampled
                                                         observations
  -1 or -2     -      parameter_back_analysis_verify     Monte-Carlo verification of a
                                                         previously identified parameter
                                                         set; STOPS after verifying

  `nbackf /= 0` selects the in-`static_U` variants instead: `back_analysis`
  (`nbackdT==0`) or `back_d_analysis` (`nbackdT/=0`, displacement-temperature coupled).

FILES
  `<probn>.btl`   inversion control: parameter list, initial values, bounds, iteration
                  limits. Opened when `Bparameter==-3 or >0 or nbackf>0 or nbackdT==2`.
  `<probn>.obs`   observations for the parameter routes. Opened when
                  `Bparameter==-3 or >0 or nbackdT==2`.
  `<probn>.obsc`  observations for the `nbackf>0` boundary routes.

Each observation record ties a NODE and a DOF to a MEASURED VALUE and a WEIGHT. Units are
the model's: displacement in m, temperature in degC, pore pressure in Pa. Feeding
millimetres into a model whose coordinates are metres makes the optimiser drive the modulus
1000x in the wrong direction and it CONVERGES -- the residual is minimised, on the wrong
scale (triplet dt_023).

COST: `balgor=0` costs (n_parameters + 1) full non-linear analyses per LM iteration.
`balgor=1` costs one. On a 30 000-node arch dam that is the difference between a coffee
break and a weekend.

Usage:
    python3 build_back_analysis.py --case /tmp/mycase --describe
    python3 build_back_analysis.py --case /tmp/mycase --mode parameter --balgor 1
    python3 build_back_analysis.py --case /tmp/mycase --mode verify
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import GlbDoc, HstarInputError, probn_of, read_lines, tokens  # noqa: E402

MODES = {
    "off": (0, None), "parameter": (1, 0), "trust_region": (1, 2),
    "rigid_split": (3, None), "nodal_value": (4, None), "verify": (-1, None),
}
ROUTE = {
    (1, 0): "parameter_back_analysis (MKL DTRNLSP, finite-difference Jacobian)",
    (1, 1): "parameter_back_analysis (MKL DTRNLSP, analytic sensitivity dudx)",
    (1, 2): "trust_region_back_analysis (trust region + BFGS, double dog-leg)",
    (2, 0): "parameter_back_analysis (MKL DTRNLSP, finite-difference Jacobian)",
    (2, 1): "parameter_back_analysis (MKL DTRNLSP, analytic sensitivity dudx)",
    (2, 2): "trust_region_back_analysis (trust region + BFGS, double dog-leg)",
    (3, 0): "rigid_dis_back_analysis (rigid/elastic least-squares split)",
    (4, 0): "nodal_value_back_analysis",
    (-1, 0): "parameter_back_analysis_verify (Monte Carlo; STOPS after verifying)",
    (-2, 0): "parameter_back_analysis_verify (Monte Carlo; STOPS after verifying)",
    (0, 0): "no inversion -- ordinary forward analysis",
}


def _glb(case):
    return GlbDoc(Path(case) / f"{probn_of(case)}.glb")


def _count(path):
    if not Path(path).is_file() or Path(path).stat().st_size == 0:
        return 0
    lines, _ = read_lines(path)
    return sum(1 for l in lines if tokens(l))


def describe(case):
    g = _glb(case)
    probn = probn_of(case)
    bp, ba = int(g.get("Bparameter")), int(g.get("balgor"))
    return {
        "Bparameter": bp, "balgor": ba, "nbackf": g.get("nbackf"),
        "nbackdT": g.get("nbackdT"),
        "route": ROUTE.get((bp, ba if bp in (1, 2) else 0), f"unmapped ({bp},{ba})"),
        "files": {
            "btl": {"path": str(Path(case) / f"{probn}.btl"),
                    "records": _count(Path(case) / f"{probn}.btl")},
            "obs": {"path": str(Path(case) / f"{probn}.obs"),
                    "records": _count(Path(case) / f"{probn}.obs")},
            "obsc": {"path": str(Path(case) / f"{probn}.obsc"),
                     "records": _count(Path(case) / f"{probn}.obsc")},
        },
        "opened_when": "btl: Bparameter==-3 or >0 or nbackf>0 or nbackdT==2 | "
                       "obs: Bparameter==-3 or >0 or nbackdT==2 | obsc: nbackf>0",
    }


def set_mode(case, mode, balgor=None, nbackf=None, nbackdT=None):
    if mode not in MODES:
        raise HstarInputError(f"mode must be one of {sorted(MODES)}")
    bp, default_ba = MODES[mode]
    ba = default_ba if balgor is None else int(balgor)
    if bp in (1, 2) and ba not in (0, 1, 2):
        raise HstarInputError("balgor must be 0 (FD Jacobian), 1 (analytic dudx) or "
                              "2 (trust region)")
    g = _glb(case)
    probn = probn_of(case)
    if bp != 0:
        for ext, why in (("btl", "inversion control"), ("obs", "observations")):
            p = Path(case) / f"{probn}.{ext}"
            if _count(p) == 0:
                raise HstarInputError(
                    f"{p} is empty but Bparameter={bp} makes HSTAR read it ({why}). "
                    f"Populate it first -- an empty .obs means the objective function has "
                    f"no residual terms and the optimiser 'converges' immediately at the "
                    f"initial guess (triplet dt_023).")
    g.set("Bparameter", bp)
    if ba is not None:
        g.set("balgor", ba)
    if nbackf is not None:
        g.set("nbackf", int(nbackf))
    if nbackdT is not None:
        g.set("nbackdT", int(nbackdT))
    g.save()
    return describe(case)


def read_observations(case, which="obs"):
    """Return the observation records as raw token lists, with a units reminder."""
    probn = probn_of(case)
    p = Path(case) / f"{probn}.{which}"
    lines, _ = read_lines(p)
    recs = [tokens(l) for l in lines if tokens(l)]
    return {"path": str(p), "n_records": len(recs), "first": recs[:5],
            "units": "model units: displacement m, temperature degC, pore pressure Pa. "
                     "Millimetres here with metres in .cor is triplet dt_023."}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--mode", choices=sorted(MODES))
    ap.add_argument("--balgor", type=int, choices=[0, 1, 2])
    ap.add_argument("--nbackf", type=int)
    ap.add_argument("--nbackdT", type=int)
    ap.add_argument("--show-observations", choices=["obs", "obsc", "btl"])
    a = ap.parse_args(argv)
    out = {"before": describe(a.case)}
    if a.mode:
        out["after"] = set_mode(a.case, a.mode, a.balgor, a.nbackf, a.nbackdT)
    if a.show_observations:
        out["observations"] = read_observations(a.case, a.show_observations)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
