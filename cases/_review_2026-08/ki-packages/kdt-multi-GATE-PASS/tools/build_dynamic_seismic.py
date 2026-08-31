#!/usr/bin/env python3
"""build_dynamic_seismic — dynamic analysis: Newmark/explicit integration, earthquake input,
absorbing boundaries, Westergaard added mass, equivalent linearisation, liquefaction.
(Capabilities 2, 3, 21, 28, 29.)

TIME INTEGRATION (`.glb` record `BEETA1 BEETA2 THETA1`)
  beeta1 = Newmark gamma, beeta2 = Newmark beta.
    0.50 / 0.2500  average acceleration -- unconditionally stable, NO algorithmic damping.
                   Use for modal verification and wave propagation.
    0.60 / 0.3025  the shipped `cases/static` values -- gamma>1/2 adds numerical damping,
                   which quietly attenuates high-frequency content. Copying these into a
                   seismic run under-predicts peak acceleration (triplet dt_019).
  `order_time_mdofn(i)` must be 2 for the displacement DOFs of a dynamic run (0 static,
  1 velocity, 2 acceleration) or HSTAR never allocates result_first/result_second and the
  velocity/acceleration output streams stay empty.

EXPLICIT (`type_solver='EXPLICIT'`) uses lumped mass and no linear solve; the time step is
CFL-limited by the smallest element and HSTAR does NOT check it -- an over-long step blows
up as NaN within a few hundred steps (triplet dt_020).

EARTHQUAKE INPUT
  * `.man` first record of each block: `nincs cdtest earthquake_curve(1:ndimn)` -- the
    curve ids (from `.loa`) driving base acceleration per direction. 0 = no input in that
    direction.
  * `.loa` curve of `type_curve = 'SEISMIC'`: record `dtrec dtbegin dtend ample`, then the
    acceleration series. `dtrec` is the record interval of the accelerogram (s), `ample` a
    scale factor. Units are m/s2; a record in g must be multiplied by 9.81 first.
  * `type_ABC` selects the artificial boundary: 'FIX', 'MIF' (multi-transmitting /
    input-wave field), or the viscous-elastic (VIE) family. With 'MIF' the `.pre` record
    gains an extra leading field `ifixvar0` -- see build_boundary_conditions.

FLUID-STRUCTURE (`.glb` record `Icaddmass swlifs2006 toth ifswater ifsgravity absorb
alfa_p4 stiff_p4`)
  Icaddmass   Westergaard added-mass switch (reservoir represented as added mass)
  swlifs2006  still-water surface elevation used by the IFS2006 interface (m) -- a REAL,
              not a switch (Global.f90:138,987)
  toth        total water depth (m) used by the Westergaard formula
  ifswater    water density / reference (kg/m3 or index)
  ifsgravity  gravity used inside the FSI terms (m/s2, 9.8 in the shipped cases)
  absorb      absorbing-boundary coefficient
`<probn>.ifs` carries `nifsgroup`, `nabsgroup`, `nabssgroup`, `ifsnedge` and their lists.

EQUIVALENT LINEARISATION: `gamamax` on line 2 of `inp` plus `equvs` in `.glb` and
`equvs_process(1:ngroup)`. HSTAR iterates the shear modulus against the maximum shear strain
and writes `<probn>.gamax`.

Usage:
    python3 build_dynamic_seismic.py --case /tmp/mycase --describe
    python3 build_dynamic_seismic.py --case /tmp/mycase --newmark 0.5 0.25 --dynamic
    python3 build_dynamic_seismic.py --case /tmp/mycase --earthquake-curves 2 0
    python3 build_dynamic_seismic.py --case /tmp/mycase --added-mass 1 --water-depth 116.0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (GlbDoc, HstarInputError, probn_of, read_lines,  # noqa: E402
                       set_inp, tokens, write_lines)

IFS_FIELDS = ["Icaddmass", "swlifs2006", "toth", "ifswater", "ifsgravity", "absorb",
              "alfa_p4", "stiff_p4"]


def _glb(case):
    return GlbDoc(Path(case) / f"{probn_of(case)}.glb")


def _ifs_line(g):
    li = g.find("Icaddmass")
    return li + 1, tokens(g.lines[li + 1])


def describe(case):
    g = _glb(case)
    lm = [int(t) for t in tokens(g.lines[g.section["lmdofn"]])[:g.mdofn]]
    ot = [int(t) for t in tokens(g.lines[g.section["order_time_mdofn"]])[:g.mdofn]]
    li, tk = _ifs_line(g)
    probn = probn_of(case)
    man, _ = read_lines(Path(case) / f"{probn}.man")
    eq = tokens(man[1])[1:] if len(man) > 1 else []
    return {
        "type_problem": g.get("type_problem"), "type_solver": g.get("type_solver"),
        "beeta1_gamma": g.get("beeta1"), "beeta2_beta": g.get("beeta2"),
        "newmark_damped": float(g.get("beeta1")) > 0.5,
        "order_time_mdofn": ot, "lmdofn": lm,
        "dynamic_dofs_ready": all(ot[i] == 2 for i, v in enumerate(lm)
                                  if v and i < int(g.get("ndimn"))),
        "type_ABC": g.get("type_ABC"),
        "fsi": dict(zip(IFS_FIELDS, tk[:len(IFS_FIELDS)])),
        "man_block1_cdtest_and_eq_curves": eq,
        "equvs": g.get("equvs"), "ninistn": g.get("ninistn"), "ljdp": g.get("ljdp"),
    }


def set_newmark(case, gamma, beta, theta=None):
    if not 0.0 <= float(gamma) <= 1.0 or not 0.0 <= float(beta) <= 1.0:
        raise HstarInputError("Newmark gamma and beta must be in [0,1]")
    if float(beta) < 0.25 * (0.5 + float(gamma)) ** 2:
        raise HstarInputError(
            f"beta={beta} < (gamma+0.5)^2/4 = {0.25 * (0.5 + float(gamma)) ** 2:.4f}: this "
            f"Newmark pair is only CONDITIONALLY stable and HSTAR performs no step-size "
            f"check. Use 0.5/0.25 (average acceleration) unless you have a reason.")
    g = _glb(case)
    g.set("beeta1", float(gamma)).set("beeta2", float(beta))
    if theta is not None:
        g.set("theta1", float(theta))
    g.save()
    return {"beeta1": g.get("beeta1"), "beeta2": g.get("beeta2"),
            "theta1": g.get("theta1"),
            "note": "gamma=0.5 gives no algorithmic damping; gamma>0.5 damps high "
                    "frequencies (triplet dt_019)"}


def make_dynamic(case, explicit=False):
    """Set type_problem='F', order_time_mdofn=2 on the displacement DOFs."""
    g = _glb(case)
    ndimn = int(g.get("ndimn"))
    lm = [int(t) for t in tokens(g.lines[g.section["lmdofn"]])[:g.mdofn]]
    ot = [int(t) for t in tokens(g.lines[g.section["order_time_mdofn"]])[:g.mdofn]]
    for i in range(min(ndimn, g.mdofn)):
        if lm[i]:
            ot[i] = 2
    g.lines[g.section["order_time_mdofn"]] = "  " + "  ".join(f"{v:>3d}" for v in ot)
    g.set("type_problem", "F")
    if explicit:
        g.set("type_solver", "EXPLICIT")
    g.save()
    return {"type_problem": g.get("type_problem"), "type_solver": g.get("type_solver"),
            "order_time_mdofn": ot,
            "note": "explicit integration is CFL-limited and HSTAR does not check the step "
                    "size (triplet dt_020)" if explicit else None}


def set_earthquake_curves(case, curves, block=None):
    """Set `earthquake_curve(1:ndimn)` on the first record of each `.man` block."""
    probn = probn_of(case)
    g = _glb(case)
    ndimn = int(g.get("ndimn"))
    if len(curves) != ndimn:
        raise HstarInputError(f"need ndimn={ndimn} curve ids (0 = no input in that "
                              f"direction)")
    p = Path(case) / f"{probn}.man"
    lines, eol = read_lines(p)
    touched = []
    blk = 0
    i = 0
    while i < len(lines):
        if not tokens(lines[i]):
            i += 1
            continue
        i += 1                                   # header text
        if i >= len(lines):
            break
        blk += 1
        tk = tokens(lines[i])
        if block is None or blk == block:
            while len(tk) < 2 + ndimn:
                tk.append("0")
            for k, c in enumerate(curves):
                tk[2 + k] = str(int(c))
            lines[i] = "  " + "  ".join(tk)
            touched.append(blk)
        nincs = int(float(tk[0]))
        i += 1 + 2 * nincs
    write_lines(p, lines, eol)
    return {"path": str(p), "blocks_updated": touched, "curves": list(map(int, curves)),
            "note": "the curve must exist in .loa; a SEISMIC curve there carries "
                    "dtrec dtbegin dtend ample and then the accelerogram in m/s2"}


def set_fsi(case, **kw):
    g = _glb(case)
    li, tk = _ifs_line(g)
    changed = {}
    for k, v in kw.items():
        if v is None:
            continue
        if k not in IFS_FIELDS:
            raise HstarInputError(f"unknown FSI field {k!r}; valid: {IFS_FIELDS}")
        p = IFS_FIELDS.index(k)
        new = (str(int(v)) if k in ("Icaddmass", "ifswater")
               else f"{float(v):.3E}")
        if k == "toth" and float(v) < 0:
            raise HstarInputError("toth (total water depth) must be >= 0 m")
        changed[k] = {"from": tk[p], "to": new}
        tk[p] = new
    g.lines[li] = "  " + "  ".join(tk)
    g.save()
    return changed


def set_equivalent_linearisation(case, gamamax=1, equvs=1):
    """Turn on the gamma_max equivalent-linearisation loop (capability 28)."""
    set_inp(case, gamamax=gamamax)
    g = _glb(case)
    before = g.get("equvs")
    g.set("equvs", int(equvs)).save()
    return {"inp_gamamax": int(gamamax), "equvs": {"from": before, "to": g.get("equvs")},
            "writes": [f"{probn_of(case)}.gamax", f"{probn_of(case)}.tel"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--newmark", nargs=2, type=float, metavar=("GAMMA", "BETA"))
    ap.add_argument("--theta", type=float)
    ap.add_argument("--dynamic", action="store_true")
    ap.add_argument("--explicit", action="store_true")
    ap.add_argument("--earthquake-curves", nargs="+", type=int)
    ap.add_argument("--added-mass", type=int)
    ap.add_argument("--water-depth", type=float)
    ap.add_argument("--absorb", type=float)
    ap.add_argument("--equivalent-linearisation", action="store_true")
    a = ap.parse_args(argv)
    out = {"before": describe(a.case)}
    if a.newmark:
        out["newmark"] = set_newmark(a.case, a.newmark[0], a.newmark[1], a.theta)
    if a.dynamic or a.explicit:
        out["dynamic"] = make_dynamic(a.case, explicit=a.explicit)
    if a.earthquake_curves:
        out["earthquake"] = set_earthquake_curves(a.case, a.earthquake_curves)
    if a.added_mass is not None or a.water_depth is not None or a.absorb is not None:
        out["fsi"] = set_fsi(a.case, Icaddmass=a.added_mass, toth=a.water_depth,
                             absorb=a.absorb)
    if a.equivalent_linearisation:
        out["equvs"] = set_equivalent_linearisation(a.case)
    out["after"] = describe(a.case)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
