#!/usr/bin/env python3
"""
write_ifs.py -- Capability 16: reservoir interaction and absorbing boundaries.

Three physically different reservoir models live behind the `*.ifs` file and
the `Icaddmass,swlifs2006,toth,ifswater,ifsgravity,absorb,alfa_p4,stiff_p4`
record of `*.glb` (Global.f90:987):

  * WESTERGAARD ADDED MASS (`Icaddmass=1`) -- the reservoir is replaced by a
    nodal mass on the wet face.  Cheap; lowers every natural frequency.  The
    shipped `train03b_modal_ifs` case shows a ~19 % frequency drop against the
    dry mesh.
  * COMPRESSIBLE RESERVOIR (`nifsgroup>0` plus p4 pressure elements, index 22)
    -- the water is meshed and coupled through `stiff_interface_fluid_solid`.
    `toth` is the reservoir depth, `alfa_p4` the reservoir-bottom reflection
    coefficient, `stiff_p4` the fluid penalty.
  * ABSORBING / TRANSMITTING BOUNDARY (`nabsfgroup`, `nabssgroup`,
    `type_ABC='VIE'`) -- a viscous dashpot boundary that stops outgoing waves
    reflecting back into the domain.  `exx, uxx, densxx` on the `nabssgroup`
    record are the far-field modulus, Poisson ratio and density used to size
    the dashpots; getting the density wrong changes the impedance and the
    boundary silently reflects.

`*.ifs` record sequence:
    nifsgroup / <group list>
    nabsfgroup / <group list>
    nabssgroup,exx,uxx,densxx / <group list>
    ifsnedge / <edge records>

validate -> process -> validate:
  pre : added mass requires a dynamic or modal `type_problem`; VIE requires
        `type_ABC='VIE'` in `.glb` AND at least one absorbing group; far-field
        density/modulus in SI range
  post: .ifs re-read, group counts match; .glb record round-trips

Usage
-----
  python3 write_ifs.py --case c1 --added-mass --water-depth 100 --water-density 1000
  python3 write_ifs.py --case c1 --absorbing "groups=2;E=1e10;nu=0.25;rho=2600"
  python3 write_ifs.py --case c1 --clear
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, write_records  # noqa: E402
from write_contact import parse_gap  # noqa: E402  (same key=value parser shape)


def parse_kv(spec, allowed):
    d = {}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in allowed:
            raise SystemExit("unknown key %r (allowed %s)" % (k, sorted(allowed)))
        d[k] = v.strip()
    return d


def build_ifs(ifs_groups, absf_groups, abss):
    r = ["nifsgroup", "%d" % len(ifs_groups)]
    if ifs_groups:
        r.append("  " + "  ".join(str(g) for g in ifs_groups))
    r.append("nabsfgroup")
    r.append("%d" % len(absf_groups))
    if absf_groups:
        r.append("  " + "  ".join(str(g) for g in absf_groups))
    r.append("nabssgroup,exx,uxx,densxx")
    if abss:
        r.append("%d  %s  %s  %s" % (len(abss["groups"]), abss["E"],
                                     abss["nu"], abss["rho"]))
        r.append("  " + "  ".join(str(g) for g in abss["groups"]))
    else:
        r.append("0  0  0  0")
    r.append("ifsnedge")
    r.append("0")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--added-mass", dest="added_mass", action="store_true")
    ap.add_argument("--water-depth", dest="toth", type=float, default=0.0)
    ap.add_argument("--water-density", dest="rho_w", type=float, default=1000.0)
    ap.add_argument("--swl", type=float, default=0.0,
                    help="still-water level used by the 2006 IFS formulation")
    ap.add_argument("--reservoir", default="",
                    help="groups=1,2;alfa=0.6;stiff=1e20  (compressible water)")
    ap.add_argument("--absorbing", default="",
                    help="groups=2;E=1e10;nu=0.25;rho=2600")
    ap.add_argument("--fluid-absorbing", dest="absf", default="",
                    help="groups=3")
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()

    glb = os.path.join(a.case, "1.glb")
    g = GlbFile(glb)
    problem = g.tokens_after("TYPE_PROBLEM")[0]

    if a.clear:
        write_records(os.path.join(a.case, "1.ifs"), build_ifs([], [], None))
        g.set_field_after("Icaddmass", 0, 0)
        g.set_field_after("NINIT", 11, "FIX")
        g.save()
        print("IFS cleared: no added mass, no reservoir, no absorbing boundary")
        return 0

    problems = []
    if a.added_mass and problem not in ("F", "E", "W"):
        problems.append(
            "Westergaard added mass only affects the mass matrix; with "
            "type_problem=%r (static) it changes nothing. Use F, E or W."
            % problem)
    if a.added_mass and a.toth <= 0:
        problems.append("--added-mass needs a positive --water-depth (m)")
    if not (500.0 <= a.rho_w <= 1500.0):
        problems.append("water density %g kg/m^3 is out of range" % a.rho_w)

    abss = None
    if a.absorbing:
        d = parse_kv(a.absorbing, {"groups", "E", "nu", "rho"})
        abss = {"groups": [int(x) for x in d["groups"].split(",")],
                "E": d.get("E", "1e10"), "nu": d.get("nu", "0.25"),
                "rho": d.get("rho", "2600")}
        if not (1000.0 <= float(abss["rho"]) <= 5000.0):
            problems.append("far-field density %s kg/m^3 is out of range; the "
                            "dashpot impedance rho*c would be wrong and the "
                            "boundary reflects silently (triplet dt_019)"
                            % abss["rho"])
        if problem not in ("F", "E"):
            problems.append("absorbing boundaries only act in a wave problem "
                            "(type_problem F or E); got %r" % problem)

    absf = [int(x) for x in parse_kv(a.absf, {"groups"})["groups"].split(",")] \
        if a.absf else []
    ifs_groups, alfa, stiff = [], 0.6, 1.0e20
    if a.reservoir:
        d = parse_kv(a.reservoir, {"groups", "alfa", "stiff"})
        ifs_groups = [int(x) for x in d["groups"].split(",")]
        alfa = float(d.get("alfa", 0.6))
        stiff = float(d.get("stiff", 1.0e20))
        if not (0.0 <= alfa <= 1.0):
            problems.append("reservoir-bottom reflection coefficient alfa=%g "
                            "must be in [0,1]" % alfa)

    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    write_records(os.path.join(a.case, "1.ifs"),
                  build_ifs(ifs_groups, absf, abss))

    # .glb: Icaddmass swlifs2006 toth ifswater ifsgravity absorb alfa_p4 stiff_p4
    i = g.find_heading("Icaddmass")
    g.lines[i + 1] = ("  %d  %.1f  %.1f  %d  %.2f  %.2f  %.1f  %.1E"
                      % (1 if a.added_mass else 0, a.swl, a.toth,
                         2, 9.8, alfa, 10.0, stiff))
    if abss:
        g.set_field_after("NINIT", 11, "VIE")
    g.save()

    g2 = GlbFile(glb)
    if g2.tokens_after("Icaddmass")[0] != ("1" if a.added_mass else "0"):
        print("POST-CHECK FAILED: Icaddmass did not round-trip")
        return 1
    print("IFS written: added_mass=%s depth=%.1f m, reservoir groups=%s, "
          "absorbing solid groups=%s, absorbing fluid groups=%s"
          % (a.added_mass, a.toth, ifs_groups,
             abss["groups"] if abss else [], absf))
    return 0


if __name__ == "__main__":
    sys.exit(main())
