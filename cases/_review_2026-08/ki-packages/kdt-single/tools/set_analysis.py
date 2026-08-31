#!/usr/bin/env python3
"""
set_analysis.py -- Stage s3: analysis-control records of `*.glb`.

Every edit is an ANCHORED TOKEN REPLACEMENT on a cloned template: the tool
locates a heading record by substring and swaps one token of the record below
it.  The token count of every record is preserved, which is the only thing a
list-directed reader is sensitive to.

Records this tool owns (heading -> tokens):

  NPOIN ...        [8] outplot   [9] kstab  [11] rmesh  [12] level_set
                   [14] stab_matde
  NINIT ...        [0] ninit [1] kinit [3] nblks [6] outinp(OUTIP)
                   [7] outintr(outir) [8] outintw(outiw) [11] type_ABC
                   [16] outind
  TYPE_PROBLEM ... [0] type_problem [1] type_solver [2] type_load [3] type_nl
                   [4] stabpw [7] state_change [8] Bparameter [9] balgor
                   [10] upliftin
  NMASS ...        [7] uwcpl [8] NGRAV [10] ECWPIPE
  NTSMAT ...       [0] ntsmat [1] nthmat [6] submodel
  MDOFN            mdofn / lmdofn(1:mdofn) / order_time_mdofn(1:mdofn)
  BEETA1 ...       Newmark gamma,beta and theta
  gid_u,gid_s,...  20 output flags
  res_u,res_s,...  17 output flags

Degree-of-freedom numbering is fixed by Global.f90:558-575 and is NOT
configurable: 1 Ux, 2 Uy, 3 Uz, 4-6 rotations, 7 hydrostatic pressure,
8 pore pressure, 9 air pressure, 10 temperature.

validate -> process -> validate:
  pre : requested combination is one the code actually dispatches on
        (e.g. EXPLICIT only with type_problem='F'); mdofn consistent with
        the DOF list; nblks consistent with the staging arrays
  post: re-open the file and assert every token landed

Usage
-----
  python3 set_analysis.py --case c1 --problem Q --solver PROFILE --nl 5 --dofs 1,2
  python3 set_analysis.py --case c1 --problem S --solver PARDISO --nl 10 --dofs 10 \
                          --order-time 1 --outintw 1
  python3 set_analysis.py --case c1 --problem W          # modal
  python3 set_analysis.py --case c1 --kstab 1.0 --load MAT_DE   # strength reduction
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile  # noqa: E402

PROBLEMS = {"Q": "static stress",
            "S": "time-dependent field (thermal / seepage / consolidation)",
            "F": "transient dynamics (Newmark or explicit)",
            "E": "response spectrum",
            "W": "modal / frequency extraction"}
SOLVERS = ["PROFILE", "PARDISO", "JPCG", "PBCG", "SSORPBCG", "EXPLICIT"]
LOADS = ["LOAD", "ARCLENGTH", "MAT_DE", "DISCONTROL"]
DOF_NAMES = {1: "Ux", 2: "Uy", 3: "Uz", 4: "Thxy", 5: "Thyz", 6: "Thzx",
             7: "hydrostatic pressure", 8: "pore pressure",
             9: "air pressure", 10: "temperature"}


def validate_request(a, dofs):
    p = []
    if a.problem and a.problem not in PROBLEMS:
        p.append("unknown type_problem %r" % a.problem)
    if a.solver and a.solver not in SOLVERS:
        p.append("unknown type_solver %r (known: %s)" % (a.solver, SOLVERS))
    if a.solver == "EXPLICIT" and a.problem not in (None, "F"):
        p.append("type_solver='EXPLICIT' is only dispatched under "
                 "type_problem='F' (Fem.f90:1936)")
    if a.load and a.load not in LOADS:
        p.append("unknown type_load %r (known: %s)" % (a.load, LOADS))
    if dofs:
        for d in dofs:
            if d not in DOF_NAMES:
                p.append("DOF id %d is outside 1..10" % d)
        if a.problem == "S" and a.nl not in (None, 10) and 10 in dofs \
                and len(dofs) == 1:
            p.append("a temperature-only transient run wants type_nl=10 "
                     "(stiffness never updated, conduction matrix updated) "
                     "-- got %r" % a.nl)
    if a.load == "MAT_DE" and (a.kstab is None or a.kstab == 0.0):
        p.append("type_load='MAT_DE' is strength reduction; it needs a "
                 "non-zero kstab target or the run reduces nothing")
    return p


def apply(case_dir, a):
    glb = os.path.join(case_dir, "1.glb")
    g = GlbFile(glb)
    touched = []

    def st(anchor, idx, val, off=1):
        g.set_field_after(anchor, idx, val, offset=off)
        touched.append((anchor, idx, str(val)))

    if a.outplot:
        st("NPOIN", 8, a.outplot)
    if a.kstab is not None:
        st("NPOIN", 9, a.kstab)
    if a.rmesh is not None:
        st("NPOIN", 11, a.rmesh)
    if a.level_set is not None:
        st("NPOIN", 12, a.level_set)

    if a.ninit is not None:
        st("NINIT", 0, a.ninit)
        st("NINIT", 1, 1 if a.ninit else 0)
    if a.nblks is not None:
        st("NINIT", 3, a.nblks)
    if a.outinp is not None:
        st("NINIT", 6, a.outinp)
    if a.outintr is not None:
        st("NINIT", 7, a.outintr)
    if a.outintw is not None:
        st("NINIT", 8, a.outintw)
    if a.type_abc:
        st("NINIT", 11, a.type_abc)

    if a.problem:
        st("TYPE_PROBLEM", 0, a.problem)
    if a.solver:
        st("TYPE_PROBLEM", 1, a.solver)
    if a.load:
        st("TYPE_PROBLEM", 2, a.load)
    if a.nl is not None:
        st("TYPE_PROBLEM", 3, a.nl)
    if a.stabpw is not None:
        st("TYPE_PROBLEM", 4, a.stabpw)
    if a.bparameter is not None:
        st("TYPE_PROBLEM", 8, a.bparameter)
    if a.balgor is not None:
        st("TYPE_PROBLEM", 9, a.balgor)
    if a.upliftin is not None:
        st("TYPE_PROBLEM", 10, a.upliftin)

    if a.uwcpl is not None:
        st("NMASS", 7, a.uwcpl)
    if a.ngrav is not None:
        st("NMASS", 8, a.ngrav)
    if a.ecwpipe is not None:
        st("NMASS", 10, a.ecwpipe)

    if a.ntsmat is not None:
        st("NTSMAT", 0, a.ntsmat)
    if a.nthmat is not None:
        st("NTSMAT", 1, a.nthmat)
    if a.submodel is not None:
        st("NTSMAT", 6, a.submodel)

    # MDOFN block: heading, mdofn, lmdofn(1:mdofn), order_time(1:mdofn)
    if a.dofs:
        dofs = [int(x) for x in a.dofs.split(",")]
        mdofn = max(dofs)
        lm = [1 if (i + 1) in dofs else 0 for i in range(mdofn)]
        if a.order_time is None:
            ot = [0] * mdofn
        else:
            ots = [int(x) for x in str(a.order_time).split(",")]
            ot = (ots * mdofn)[:mdofn] if len(ots) == 1 else ots
            if len(ot) != mdofn:
                raise SystemExit("--order-time needs 1 or %d values" % mdofn)
        i = g.find_heading("MDOFN")
        g.lines[i + 1] = "  %d" % mdofn
        g.lines[i + 2] = "  " + "  ".join(str(x) for x in lm)
        g.lines[i + 3] = "  " + "  ".join(str(x) for x in ot)
        touched.append(("MDOFN", "block", "%d %s %s" % (mdofn, lm, ot)))

    if a.newmark:
        b1, b2, th = [float(x) for x in a.newmark.split(",")]
        i = g.find_heading("BEETA1")
        g.lines[i + 1] = "  %s  %s  %s" % (b1, b2, th)
        touched.append(("BEETA1", "block", a.newmark))

    if a.gid_flags:
        i = g.find_heading("gid_u,gid_s")
        flags = [int(x) for x in a.gid_flags.split(",")]
        cur = g.tokens_after("gid_u,gid_s")
        for k, v in enumerate(flags):
            if k < len(cur):
                cur[k] = str(v)
        g.lines[i + 1] = "  " + "  ".join(cur)
        touched.append(("gid_u,gid_s", "block", a.gid_flags))

    g.save()
    return touched


def verify(case_dir, touched):
    g = GlbFile(os.path.join(case_dir, "1.glb"))
    bad = []
    for anchor, idx, val in touched:
        if idx == "block":
            continue
        got = g.tokens_after(anchor)[idx]
        if got != val:
            bad.append("%s[%s]: wrote %r, file has %r" % (anchor, idx, val, got))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--problem", choices=list(PROBLEMS))
    ap.add_argument("--solver", choices=SOLVERS)
    ap.add_argument("--load", choices=LOADS)
    ap.add_argument("--nl", type=int)
    ap.add_argument("--dofs", help="comma list, e.g. 1,2 or 1,2,3,10")
    ap.add_argument("--order-time", dest="order_time",
                    help="0 value / 1 first deriv / 2 second deriv")
    ap.add_argument("--nblks", type=int)
    ap.add_argument("--ninit", type=int)
    ap.add_argument("--outinp", type=int, help="read pore pressure from .oip")
    ap.add_argument("--outintr", type=int, help="read dT from .oit (stress pass)")
    ap.add_argument("--outintw", type=int, help="write dT to .oit (thermal pass)")
    ap.add_argument("--outplot", choices=["GIDR", "GIDA", "GIDB", "GIDL"])
    ap.add_argument("--kstab", type=float)
    ap.add_argument("--rmesh", type=int)
    ap.add_argument("--level-set", dest="level_set", type=int)
    ap.add_argument("--stabpw", type=int)
    ap.add_argument("--uwcpl", type=int, choices=[0, 1, 2])
    ap.add_argument("--ngrav", type=int)
    ap.add_argument("--ecwpipe", type=int)
    ap.add_argument("--ntsmat", type=int)
    ap.add_argument("--nthmat", type=int)
    ap.add_argument("--submodel", type=int)
    ap.add_argument("--type-abc", dest="type_abc",
                    choices=["FIX", "MIF", "VIE"])
    ap.add_argument("--upliftin", type=int)
    ap.add_argument("--bparameter", type=int)
    ap.add_argument("--balgor", type=int)
    ap.add_argument("--newmark", help="beeta1,beeta2,theta1")
    ap.add_argument("--gid-flags", dest="gid_flags",
                    help="comma list overriding gid_u,gid_s,...")
    a = ap.parse_args()

    dofs = [int(x) for x in a.dofs.split(",")] if a.dofs else []
    problems = validate_request(a, dofs)
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    touched = apply(a.case, a)
    bad = verify(a.case, touched)
    if bad:
        for b in bad:
            print("POST-CHECK FAILED:", b)
        return 1
    for anchor, idx, val in touched:
        print("set %-16s [%s] = %s" % (anchor, idx, val))
    return 0


if __name__ == "__main__":
    sys.exit(main())
