#!/usr/bin/env python3
"""build_thermal — configure steady/transient heat conduction and embedded pipe cooling.
(Capabilities 6 and 7.)

SWITCHES (`<probn>.glb`)
  ntsmat, nthmat   MATRIX RE-FORMATION INTERVALS for the thermal SOURCE (ts) and thermal
                   CONDUCTION (th) matrices -- **not** material ids. `modf_time_order`
                   (Fem.f90:15509-15531) sets
                       KTSMAT = 1 if NTSMAT==0 or (istep==inc_step and iiter==1)
                                  or mod(istep, NTSMAT)==0
                   and only then calls `stmatrx` / `htmatrx`. So:
                       0   -> re-form EVERY iteration (most robust, most expensive)
                       1   -> re-form every step
                       999 -> re-form only on the first step of each increment
                   The same convention governs `nmass nsmat nhmat nqmat` on the record
                   above. Reading 999 as "thermal is off" is wrong -- what actually turns
                   the heat equation on is a group whose `fieldid` is 'T' plus a HEAT
                   material record.
  kstat            0 = transient, 1 = steady state (the field equation drops its d/dt term)
  ground_inf       ground-temperature influence switch
  src              distributed heat-source switch
  theta1           theta for the field time integration (0.5 Crank-Nicolson,
                   1.0 fully implicit). Lives on the BEETA1 BEETA2 THETA1 record.
  ECWPIPE, nwcpipe cooling-water-pipe element coupling
  type_problem     'S' advances a transient field; 'Q' with kstat=1 solves the steady field

DOF: temperature is DOF slot 10 (`Global.f90` title(10)='Temperature'). A thermo-mechanical
run needs it switched on in `lmdofn` -- see build_analysis_control.set_dofs.

`<probn>.tem` (Temper.f90) is read as:
    text ; n_prescribed_T          [ node/value records ]
    text ; nedge_convection        [ edge records: element, face, h, T_env ]
    text ; nsurf                   [ surface records ]
    text ; npipe algo_pipe         [ per-pipe records ]      algo_pipe=3 = Zhu Bofang
                                                             analytic superposition

HEAT material record (Material.f90:968-990):
    alfa(1:ndimn) source_curve place_curve pipe_cooling
    ialfa
    [ water_curve time_cooling gap_cooling eata bcooltime ]   if pipe_cooling /= 0
`alfa` is the thermal DIFFUSIVITY per coordinate direction, in m2 per time unit -- the same
time unit as `ditime` in `.man`. Mixing m2/h into a model whose `ditime` is in seconds makes
the concrete cool 3600x too fast and is invisible in the output (triplet dt_013).

Usage:
    python3 build_thermal.py --case /tmp/mycase --describe
    python3 build_thermal.py --case /tmp/mycase --enable --ntsmat 3 --nthmat 3 --steady
    python3 build_thermal.py --case /tmp/mycase --theta 0.5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (GlbDoc, HstarInputError, probn_of, read_lines,  # noqa: E402
                       tokens)

def _glb(case):
    return GlbDoc(Path(case) / f"{probn_of(case)}.glb")


def _reform(n):
    n = int(n)
    return ("every iteration" if n == 0 else
            "every step" if n == 1 else
            f"every {n} steps (and on the first step of each increment)")


def thermal_groups(case):
    """Groups whose `fieldid` is 'T' -- the real switch for the heat equation."""
    g = _glb(case)
    out = []
    for i in range(g.section["_after_average_appear"], len(g.lines)):
        tk = tokens(g.lines[i])
        if tk and "T" in tk[:10] and len(tk) > 8:
            out.append({"line": i + 1, "tokens": tk[:10]})
    return out


def describe(case):
    g = _glb(case)
    probn = probn_of(case)
    tem, _ = read_lines(Path(case) / f"{probn}.tem")
    vals = [tokens(l) for l in tem]
    counters = [v[0] for v in vals if v and v[0].lstrip("-").isdigit()]
    tg = thermal_groups(case)
    return {
        "ntsmat": g.get("ntsmat"),
        "ntsmat_meaning": "re-form the thermal SOURCE matrix " + _reform(g.get("ntsmat")),
        "nthmat": g.get("nthmat"),
        "nthmat_meaning": "re-form the thermal CONDUCTION matrix "
                          + _reform(g.get("nthmat")),
        "n_T_field_groups": len(tg),
        "thermal_enabled": bool(tg) or g.get("type_problem") == "S",
        "kstat": g.get("kstat"),
        "kstat_meaning": "steady state" if int(g.get("kstat")) == 1 else "transient",
        "ground_inf": g.get("ground_inf"), "src": g.get("src"),
        "theta1": g.get("theta1"), "ECWPIPE": g.get("ECWPIPE"),
        "type_problem": g.get("type_problem"),
        "tem_counters_in_order": counters[:8],
        "tem_note": "counters are, in order: n_prescribed_T, nedge_convection, nsurf, "
                    "npipe, algo_pipe",
    }


def enable(case, ntsmat=None, nthmat=None, steady=None, theta1=None,
           ground_inf=None, src=None, ecwpipe=None):
    g = _glb(case)
    changed = {}
    for k, v in (("ntsmat", ntsmat), ("nthmat", nthmat), ("ground_inf", ground_inf),
                 ("src", src), ("ECWPIPE", ecwpipe)):
        if v is not None:
            changed[k] = {"from": g.get(k), "to": str(int(v))}
            g.set(k, v)
    if steady is not None:
        changed["kstat"] = {"from": g.get("kstat"), "to": str(int(bool(steady)))}
        g.set("kstat", int(bool(steady)))
    if theta1 is not None:
        t = float(theta1)
        if not 0.0 <= t <= 1.0:
            raise HstarInputError(
                f"theta1={t}: the theta-method parameter must be in [0,1]. 0.5 = "
                f"Crank-Nicolson (2nd order, can oscillate on a coarse time step), "
                f"1.0 = backward Euler (1st order, unconditionally monotone).")
        changed["theta1"] = {"from": g.get("theta1"), "to": t}
        g.set("theta1", t)
    g.save()
    if not thermal_groups(case) and g.get("type_problem") != "S":
        changed["warning"] = (
            "no element group declares fieldid 'T' and type_problem is not 'S', so the "
            "heat equation will not be assembled no matter what ntsmat/nthmat/kstat say. "
            "Add a T-field group to the .glb group block (COPY one from "
            "cases/train07_thermal_transient).")
    return changed


def write_tem(case, prescribed=None, convection=None, surfaces=None, pipes=None,
              algo_pipe=3):
    """Write `<probn>.tem`.

    prescribed : [(node_id, temperature_degC), ...]
    convection : [(element, face, h_W_m2K, T_env_degC), ...]
    surfaces   : [[...], ...]   raw records, passed through
    pipes      : [[...], ...]   raw records, passed through
    """
    from _hstar_io import write_lines
    probn = probn_of(case)
    p = Path(case) / f"{probn}.tem"
    _, eol = read_lines(p)
    prescribed = prescribed or []
    convection = convection or []
    surfaces = surfaces or []
    pipes = pipes or []
    for nid, t in prescribed:
        if not -100.0 <= float(t) <= 500.0:
            raise HstarInputError(
                f"prescribed temperature {t} degC at node {nid} is outside -100..500. "
                f"HSTAR takes degC; a value near 300 usually means kelvin were entered "
                f"(triplet dt_014).")
    out = [" prescribed temperature (node, T in degC)", f"  {len(prescribed)}"]
    out += [f"  {int(n)}  {float(t):.5E}" for n, t in prescribed]
    out += [" surface convection edges (element, face, h, T_env)", f"  {len(convection)}"]
    out += ["  " + "  ".join(str(x) for x in rec) for rec in convection]
    out += [" surface list", f"  {len(surfaces)}"]
    out += ["  " + "  ".join(str(x) for x in rec) for rec in surfaces]
    out += [" pipe cooling: npipe algo_pipe", f"  {len(pipes)}  {int(algo_pipe)}"]
    out += ["  " + "  ".join(str(x) for x in rec) for rec in pipes]
    write_lines(p, out, eol)
    return {"path": str(p), "n_prescribed": len(prescribed),
            "n_convection": len(convection), "n_pipes": len(pipes),
            "algo_pipe": int(algo_pipe)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--ntsmat", type=int)
    ap.add_argument("--nthmat", type=int)
    ap.add_argument("--steady", dest="steady", action="store_true", default=None)
    ap.add_argument("--transient", dest="steady", action="store_false")
    ap.add_argument("--theta", type=float)
    ap.add_argument("--ground-inf", type=int)
    ap.add_argument("--src", type=int)
    ap.add_argument("--ecwpipe", type=int)
    a = ap.parse_args(argv)
    out = {"before": describe(a.case)}
    if a.enable or any(v is not None for v in
                       (a.ntsmat, a.nthmat, a.steady, a.theta, a.ground_inf, a.src,
                        a.ecwpipe)):
        out["changes"] = enable(a.case, a.ntsmat, a.nthmat, a.steady, a.theta,
                                a.ground_inf, a.src, a.ecwpipe)
        out["after"] = describe(a.case)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
