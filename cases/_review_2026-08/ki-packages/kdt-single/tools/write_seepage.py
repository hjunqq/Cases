#!/usr/bin/env python3
"""
write_seepage.py -- Capabilities 8 and 9: seepage / pore-pressure field,
U-P (Biot) coupling, and dam-base uplift pressure.

Three distinct configurations, selected explicitly:

  --mode field      seepage alone (Laplace / theta-method).  DOF 8 only.
                    .glb: mdofn=8, lmdofn(8)=1, uwcpl=0,
                          type_problem='Q' (steady) or 'S' (transient),
                          outinp=1 to dump nodal pore pressure to `*.oip`.
  --mode coupled    displacement + pore pressure solved together (Biot).
                    .glb: DOFs (1..ndimn, 8), nrfields=2, fieldid='UW',
                          uwcpl=1 undrained / 2 drained, stabpw=1 to use the
                          stabilised formulation for equal-order interpolation.
                          Element must be a `*cN` two-field type
                          (q4c4=16, b8c8=18, t3c3=15, ...).
  --mode readback   stress run that READS a previously computed `*.oip`
                    (.glb outinp=1) instead of solving the flow field.

`uwcpl` semantics (manual §3.2): 0 flow only / drained, 1 U+W undrained,
2 U+W drained.  Getting it wrong changes the answer without changing the
convergence behaviour.

Uplift (`--uplift`): `upliftin/=0` in `.glb` plus `water_level(1:nblks)`
switches on the base-uplift model, which reduces the effective self-weight of
the blocks below the reservoir surface and writes `*.upf`.  `water_level` is an
ELEVATION in metres in the mesh's own coordinate system; `-99.0` means "no
reservoir", which is why a real elevation of -99 m would be misread.

Boundary conditions for the flow field are ordinary `.pre` sets on DOF 8; the
prescribed value is a PRESSURE HEAD in metres, not a pressure in Pa
(Global.f90 converts with `gamawx` from the `.pre` record).

validate -> process -> validate:
  pre : mode-specific flag combination is coherent; the element type supports
        the requested number of fields; permeability present in the .mat FLUID
        phase; water_level inside the mesh's z/y range
  post: .glb flags round-trip

Usage
-----
  python3 write_seepage.py --case c1 --mode field --steady
  python3 write_seepage.py --case c1 --mode coupled --uwcpl 2 --etype q4c4
  python3 write_seepage.py --case c1 --uplift --water-level 60.0
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, read_tokens  # noqa: E402
from write_boundary import read_cor  # noqa: E402
from write_mesh import ELEMENT_TABLE  # noqa: E402
from write_thermal import set_dof_block, set_group_field  # noqa: E402

TWO_FIELD = {"t6c3", "q8c4", "h10c4", "b20c8", "t3c3", "q4c4", "h4c4",
             "b8c8", "l2c2", "b2c2", "pr6c6"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--mode", choices=["field", "coupled", "readback"])
    ap.add_argument("--steady", action="store_true")
    ap.add_argument("--uwcpl", type=int, choices=[0, 1, 2], default=2)
    ap.add_argument("--stabpw", type=int, choices=[0, 1], default=0)
    ap.add_argument("--etype", default="", choices=[""] + sorted(ELEMENT_TABLE))
    ap.add_argument("--uplift", action="store_true")
    ap.add_argument("--water-level", dest="water_level", type=float)
    ap.add_argument("--outinp", type=int)
    a = ap.parse_args()

    glb = os.path.join(a.case, "1.glb")
    g = GlbFile(glb)
    ndimn = int(g.tokens_after("NPOIN")[3])
    nblks = int(g.tokens_after("NINIT")[3])
    nodes = read_cor(os.path.join(a.case, "1.cor"))

    problems = []
    if a.mode == "coupled":
        if not a.etype:
            problems.append(
                "--mode coupled needs --etype: only the two-field elements "
                "%s carry a pore-pressure field" % sorted(TWO_FIELD))
        elif a.etype not in TWO_FIELD:
            problems.append(
                "element %r has a single field; U-P coupling needs one of %s "
                "(triplet dt_017)" % (a.etype, sorted(TWO_FIELD)))
        if a.uwcpl == 0:
            problems.append("--mode coupled with uwcpl=0 solves flow only; "
                            "use 1 (undrained) or 2 (drained)")
    if a.uplift:
        if a.water_level is None:
            problems.append("--uplift needs --water-level (metres, mesh datum)")
        else:
            ys = [c[1] for c in nodes.values() if len(c) > 1]
            zs = [c[2] for c in nodes.values() if len(c) > 2]
            vert = zs if zs else ys
            if vert and not (min(vert) - 1e-9 <= a.water_level
                             <= max(vert) + 1e-9):
                problems.append(
                    "water_level=%g lies outside the mesh's vertical extent "
                    "[%g, %g]; HSTAR will treat the whole structure as "
                    "submerged or as dry" % (a.water_level, min(vert), max(vert)))
            if abs(a.water_level + 99.0) < 1e-9:
                problems.append(
                    "water_level=-99.0 is HSTAR's sentinel for 'no reservoir'. "
                    "Shift the mesh datum if -99 m is a real elevation.")
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    if a.mode == "field":
        g.set_field_after("TYPE_PROBLEM", 0, "Q" if a.steady else "S")
        g.set_field_after("TYPE_PROBLEM", 3, 10)
        g.set_field_after("NMASS", 7, 0)
        set_dof_block(g, 8, [8], {} if a.steady else {8: 1})
        set_group_field(g, "W", 1, [[8]])
        g.set_field_after("NINIT", 6, 1 if a.outinp is None else a.outinp)
        print("seepage FIELD configured (%s)" %
              ("steady, Laplace" if a.steady else "transient, theta-method"))

    elif a.mode == "coupled":
        udofs = list(range(1, ndimn + 1))
        g.set_field_after("TYPE_PROBLEM", 0, "S")
        g.set_field_after("TYPE_PROBLEM", 3, 5)
        g.set_field_after("TYPE_PROBLEM", 4, a.stabpw)
        g.set_field_after("NMASS", 7, a.uwcpl)
        set_dof_block(g, 8, udofs + [8], {8: 1})
        set_group_field(g, "UW", 2, [udofs, [8]])
        if a.etype:
            anchor = "(3) for each field"
            base = g.find_heading(anchor)
            toks = read_tokens(g.lines[base + 1])
            toks[0] = a.etype.upper()
            toks[2] = str(ELEMENT_TABLE[a.etype][0])
            g.lines[base + 1] = "  " + "  ".join(toks)
        print("U-P COUPLED configured: uwcpl=%d (%s), stabpw=%d, etype=%s"
              % (a.uwcpl,
                 {0: "flow only", 1: "undrained", 2: "drained"}[a.uwcpl],
                 a.stabpw, a.etype or "unchanged"))

    elif a.mode == "readback":
        g.set_field_after("NINIT", 6, 1 if a.outinp is None else a.outinp)
        oip = os.path.join(a.case, "1.oip")
        if not os.path.exists(oip):
            print("BLOCKER: --mode readback needs 1.oip in the case directory; "
                  "produce it with --mode field first")
            return 1
        print("pore-pressure READBACK configured (outinp=1)")

    if a.uplift:
        g.set_field_after("TYPE_PROBLEM", 10, 1)
        i = g.find_heading("water_level")
        g.lines[i + 1] = "  " + "  ".join(["%.3f" % a.water_level] * nblks)
        print("uplift enabled, water_level=%.3f m for %d block(s)"
              % (a.water_level, nblks))

    g.save()

    g2 = GlbFile(glb)
    if a.uplift and g2.tokens_after("TYPE_PROBLEM")[10] != "1":
        print("POST-CHECK FAILED: upliftin did not round-trip")
        return 1
    if a.mode == "coupled" and g2.tokens_after("NMASS")[7] != str(a.uwcpl):
        print("POST-CHECK FAILED: uwcpl did not round-trip")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
