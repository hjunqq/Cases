#!/usr/bin/env python3
"""build_stability_analysis — the three stability paths: limit-state safety factor,
strength reduction, and rigid-block sliding. (Capabilities 11, 12, 13.)

HSTAR offers THREE DIFFERENT answers to "is it stable?", and they are not interchangeable:

1. LIMIT-STATE SAFETY FACTOR  (`kstab /= 0`)
   The slip surface is KNOWN -- it is the set of joint/interface elements you declared.
   HSTAR calls `safety_factor` and reports the ratio of available to mobilised shear on
   that surface. `kstab` is a REAL on the first `.glb` record (cases/static ships 1.000,
   cases/train05 ships 0.0). The surfaces come from `<probn>.ftr`:
       nforce ngaps nforce_gaps nsafety_gaps
       nforce_appear        1 = safety factor, 2 = internal force, 3 = both
       per set: lgroup neface node_face nliste  then the face list
   Use when the failure path is a bedding plane, a dam-foundation contact, or a designed
   joint.

2. STRENGTH REDUCTION  (`type_load = 'MAT_DE'`, with `stab_matde` on the first `.glb`
   record)
   The slip surface is UNKNOWN. HSTAR divides c and tan(phi) by a factor that marches from
   1.0 downwards over the increments, and the factor at which the Newton loop stops
   converging is the factor of safety. This is what `cases/train05b_slope_srm` does
   (MAT_DE 1.0 -> 0.5 over 100 steps).
   READING THE ANSWER: the FoS is `1 / reduction at the last CONVERGED step`. Because the
   criterion is non-convergence, `miter` in `.man` changes the answer -- a small `miter`
   declares failure early and reports a LOW FoS. Fix `miter` (>= 200) before comparing
   runs (triplet dt_021).

3. RIGID-BLOCK SLIDING  (`block_stab = 1` or `2`)
   The structure above the failure surface is treated as a rigid body with 3(ndimn-1)
   DOF (2-D: tx, ty, thz). `static_rigid_1` + `solve_ctt_rigid` solve the contact problem
   on the interface only. `block_stab=1` keeps the interface deformable, `=2` mixes rigid
   DOF with ordinary nodal DOF. `ebody` must be 0 for the pure rigid path.

Usage:
    python3 build_stability_analysis.py --case /tmp/mycase --describe
    python3 build_stability_analysis.py --case /tmp/mycase --kstab 1.0
    python3 build_stability_analysis.py --case /tmp/mycase --strength-reduction 1.0 0.5 100
    python3 build_stability_analysis.py --case /tmp/mycase --block-stab 1
    python3 build_stability_analysis.py --run-dir /tmp/myrun --report-fos
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (ENC, GlbDoc, HstarInputError, probn_of, read_lines,  # noqa: E402
                       tokens)
from build_analysis_control import read_man, write_man  # noqa: E402


def _glb(case):
    return GlbDoc(Path(case) / f"{probn_of(case)}.glb")


def describe(case):
    g = _glb(case)
    probn = probn_of(case)
    ftr, _ = read_lines(Path(case) / f"{probn}.ftr")
    nums = [tokens(l) for l in ftr if tokens(l)]
    hdr = next((t for t in nums if len(t) == 4 and all(
        x.lstrip("-").isdigit() for x in t)), None)
    return {
        "kstab": g.get("kstab"),
        "kstab_active": float(g.get("kstab")) != 0.0,
        "type_load": g.get("type_load"),
        "strength_reduction_active": g.get("type_load").upper() == "MAT_DE",
        "stab_matde": g.get("stab_matde"),
        "block_stab": g.get("block_stab"),
        "block_stab_meaning": {0: "standard deformable", 1: "rigid block, deformable "
                                                            "interface",
                              2: "mixed rigid + nodal DOF"}.get(
            int(g.get("block_stab")), "?"),
        "ebody": g.get("ebody"),
        "ftr_header": dict(zip(["nforce", "ngaps", "nforce_gaps", "nsafety_gaps"], hdr))
        if hdr else None,
    }


def set_kstab(case, kstab):
    g = _glb(case)
    before = g.get("kstab")
    g.set("kstab", float(kstab)).save()
    return {"kstab": {"from": before, "to": g.get("kstab")},
            "note": "kstab/=0 makes HSTAR call safety_factor over the surfaces declared in "
                    "<probn>.ftr; an empty .ftr means it reports nothing and says nothing"}


def set_strength_reduction(case, start=1.0, end=0.5, nstep=100, miter=200):
    """Switch to the MAT_DE path and give it enough iterations to be meaningful."""
    g = _glb(case)
    if float(start) <= 0 or float(end) <= 0 or float(end) >= float(start):
        raise HstarInputError(
            "the reduction sequence must march DOWN from `start` to `end`, both > 0 "
            "(e.g. 1.0 -> 0.5)")
    before = g.get("type_load")
    g.set("type_load", "MAT_DE").set("stab_matde", float(end)).save()
    blocks = read_man(case)
    for b in blocks:
        for inc in b["increments"]:
            inc["nstep"] = int(nstep)
            inc["inc_step"] = 1
            inc["miter"] = int(miter)
    man = write_man(case, blocks)
    return {"type_load": {"from": before, "to": "MAT_DE"},
            "stab_matde": g.get("stab_matde"),
            "man": man,
            "reduction": {"from": float(start), "to": float(end), "nstep": int(nstep)},
            "note": "FoS = 1 / (reduction at the last CONVERGED step). miter controls "
                    "when 'non-convergence' is declared, so it changes the reported FoS "
                    "(triplet dt_021); it has been set to " + str(int(miter))}


def set_block_stab(case, mode, ebody=0):
    if int(mode) not in (0, 1, 2):
        raise HstarInputError("block_stab must be 0, 1 or 2")
    g = _glb(case)
    before = g.get("block_stab")
    g.set("block_stab", int(mode))
    if int(mode) >= 1 and int(g.get("ebody")) != int(ebody):
        g.set("ebody", int(ebody))
    g.save()
    return {"block_stab": {"from": before, "to": g.get("block_stab")},
            "ebody": g.get("ebody"),
            "route": {0: "static_U", 1: "static_rigid_1 + solve_ctt_rigid",
                      2: "static_rigid_1 with mixed DOF"}[int(mode)]}


def report_fos(run_dir, probn=None):
    """Extract the strength-reduction factor of safety from a finished run.

    The criterion is the LAST STEP THAT CONVERGED. `.chk` marks a non-converged iteration
    with `not converged for checki=`; the step counter is on the preceding
    `iblks= .. iincs= .. istep= .. iiter= ..` line.
    """
    d = Path(run_dir)
    if probn is None:
        c = sorted(d.glob("*.chk"))
        if not c:
            raise HstarInputError(f"no .chk in {d}")
        probn = c[0].stem
    txt = (d / f"{probn}.chk").read_text(encoding=ENC, errors="replace")
    import re
    steps = [(m.start(), int(m.group(3)))
             for m in re.finditer(r"iblks=\s*(\d+)\s+iincs=\s*(\d+)\s+istep=\s*(\d+)"
                                  r"\s+iiter=\s*(\d+)", txt)]
    fails = [m.start() for m in re.finditer(r"not converged for checki", txt)]
    if not steps:
        return {"error": "no step markers in .chk -- did the run reach static_U?"}
    last_converged = None
    for pos, st in steps:
        later_fail = [f for f in fails if pos < f < (pos + 4000)]
        if not later_fail:
            last_converged = st
    return {"probn": probn, "n_steps_logged": max(s for _, s in steps),
            "last_converged_step": last_converged,
            "how_to_read": "FoS = the strength-reduction value in force at "
                           "`last_converged_step`. With a linear march from `start` to "
                           "`end` over `nstep`, that is "
                           "start + (end-start)*(last_converged_step-1)/(nstep-1); "
                           "the factor of safety is 1/that value.",
            "caveat": "non-convergence is the criterion, so `miter` in .man changes this "
                      "number (triplet dt_021)"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case")
    ap.add_argument("--run-dir")
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--kstab", type=float)
    ap.add_argument("--strength-reduction", nargs=3, type=float,
                    metavar=("START", "END", "NSTEP"))
    ap.add_argument("--miter", type=int, default=200)
    ap.add_argument("--block-stab", type=int, choices=[0, 1, 2])
    ap.add_argument("--report-fos", action="store_true")
    a = ap.parse_args(argv)
    out = {}
    if a.report_fos:
        if not a.run_dir:
            ap.error("--report-fos needs --run-dir")
        out["fos"] = report_fos(a.run_dir)
    if a.case:
        out["before"] = describe(a.case)
        if a.kstab is not None:
            out["kstab"] = set_kstab(a.case, a.kstab)
        if a.strength_reduction:
            s, e, n = a.strength_reduction
            out["strength_reduction"] = set_strength_reduction(a.case, s, e, int(n),
                                                               a.miter)
        if a.block_stab is not None:
            out["block_stab"] = set_block_stab(a.case, a.block_stab)
        out["after"] = describe(a.case)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
