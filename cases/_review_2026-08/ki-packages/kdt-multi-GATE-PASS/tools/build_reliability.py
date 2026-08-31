#!/usr/bin/env python3
"""build_reliability — FORM reliability, system reliability and stochastic material fields.
(Capabilities 14, 15, 27.)

SWITCHES (line 2 of `inp`, read at Fem.f90:93):
    restart relis sysrelis ADINA Uopt_R gamamax

    relis     = 1  -> first-order reliability method (FORM).
                     `block_stab==0` routes to `STATIC_U_reli` (Fem.f90:4708-5364);
                     `block_stab>=1` routes to `static_rigid_reli` (5957-6214).
                     Core routines: DANGLI (equivalent-normal transformation),
                     RI3 (Rackwitz-Fiessler design-point update), `betaindex`
                     (beta = Phi^-1(1 - Pf)), `stab_rcandgy_reli`
                     (limit state G = resistance - load).
    sysrelis  > 0  -> system reliability on top of the component analysis:
                     series (any component fails), parallel (all fail), or the
                     narrow-bound method for a general system.

    Random variables are the strength parameters -- friction angle phi and cohesion c by
    default -- with normal, lognormal or extreme-value marginals. Their statistics live in
    `<probn>.sto`, together with the correlation structure used by the MKL VSL
    multivariate-Gaussian generator (`vsl_gauss_module.f90`).

STOCHASTIC FIELDS (capability 27) share `<probn>.sto` and the same generator. `nstoch_curve`
on a `.loa` time-curve record ties a load curve to stochastic parameters.

INTERPRETING beta: Pf = Phi(-beta). beta = 3.0 -> Pf ~ 1.3e-3; beta = 4.2 -> Pf ~ 1.3e-5.
Chinese dam design codes commonly target beta >= 3.2 for serviceability and >= 4.2 for
ultimate limit states of grade-1 structures; ISO 2394 / EN 1990 use beta = 3.8 for a
50-year reference period at consequence class RC2. State which convention you used --
this KI does NOT pick one for you.

A FORM run costs one full non-linear solve PER DESIGN-POINT ITERATION per random variable
(finite-difference gradients). Budget accordingly: a 5-variable problem on a 3000-node mesh
is 15-40 full analyses.

Usage:
    python3 build_reliability.py --case /tmp/mycase --describe
    python3 build_reliability.py --case /tmp/mycase --form --sysrelis 1
    python3 build_reliability.py --run-dir /tmp/myrun --report-beta
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (ENC, GlbDoc, HstarInputError, probn_of, read_lines,  # noqa: E402
                       set_inp, tokens)


def _inp_flags(case):
    lines, _ = read_lines(Path(case) / "inp")
    tk = tokens(lines[1])
    keys = ["restart", "relis", "sysrelis", "ADINA", "Uopt_R", "gamamax"]
    return dict(zip(keys, tk[:6]))


def describe(case):
    flags = _inp_flags(case)
    g = GlbDoc(Path(case) / f"{probn_of(case)}.glb")
    sto = Path(case) / f"{probn_of(case)}.sto"
    return {
        "inp_flags": flags,
        "form_active": int(flags.get("relis", 0)) == 1,
        "system_reliability": int(flags.get("sysrelis", 0)),
        "block_stab": g.get("block_stab"),
        "route": ("static_rigid_reli" if int(flags.get("relis", 0)) == 1
                  and int(g.get("block_stab")) >= 1
                  else "STATIC_U_reli" if int(flags.get("relis", 0)) == 1
                  else "not a reliability run"),
        "sto_file": {"path": str(sto),
                     "bytes": sto.stat().st_size if sto.is_file() else 0,
                     "note": "random-variable statistics + correlation for the MKL VSL "
                             "multivariate Gaussian generator; an EMPTY .sto with relis=1 "
                             "means FORM has no random variables and beta is meaningless "
                             "(triplet dt_022)"},
    }


def enable_form(case, sysrelis=0):
    sto = Path(case) / f"{probn_of(case)}.sto"
    if not sto.is_file() or sto.stat().st_size == 0:
        raise HstarInputError(
            f"{sto} is empty. FORM needs the random-variable statistics (distribution "
            f"type, mean, standard deviation, correlation) before `relis=1` means "
            f"anything -- HSTAR does not error, it reports a beta computed from nothing "
            f"(triplet dt_022). Copy a .sto from a case that has one and edit it.")
    set_inp(case, relis=1, sysrelis=int(sysrelis))
    return describe(case)


def report_beta(run_dir, probn=None):
    """Pull the reliability index and design point out of a finished run's .chk."""
    d = Path(run_dir)
    if probn is None:
        c = sorted(d.glob("*.chk"))
        if not c:
            raise HstarInputError(f"no .chk in {d}")
        probn = c[0].stem
    txt = (d / f"{probn}.chk").read_text(encoding=ENC, errors="replace")
    betas = [float(m.group(1)) for m in
             re.finditer(r"beta\s*=\s*([-\d.EeDd+]+)", txt, re.I)]
    pf = [float(m.group(1)) for m in re.finditer(r"\bPf\s*=\s*([-\d.EeDd+]+)", txt, re.I)]
    out = {"probn": probn, "beta_values": betas, "final_beta": betas[-1] if betas else None,
           "pf_values": pf}
    if out["final_beta"] is not None:
        import math
        b = out["final_beta"]
        out["pf_from_beta"] = 0.5 * math.erfc(b / math.sqrt(2.0))
        out["interpretation"] = ("Pf = Phi(-beta). State which target beta convention you "
                                 "are judging against -- this KI does not choose one.")
    else:
        out["note"] = ("no `beta=` record in .chk -- either relis/=1 or the FORM loop never "
                       "reached betaindex")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case")
    ap.add_argument("--run-dir")
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--form", action="store_true")
    ap.add_argument("--sysrelis", type=int, default=0)
    ap.add_argument("--report-beta", action="store_true")
    a = ap.parse_args(argv)
    out = {}
    if a.case:
        out["before"] = describe(a.case)
        if a.form:
            out["after"] = enable_form(a.case, a.sysrelis)
    if a.report_beta:
        if not a.run_dir:
            ap.error("--report-beta needs --run-dir")
        out["beta"] = report_beta(a.run_dir)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
