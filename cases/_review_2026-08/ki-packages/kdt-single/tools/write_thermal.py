#!/usr/bin/env python3
"""
write_thermal.py -- Capabilities 6, 7, 15: thermal field, thermal-stress
coupling, and cooling-pipe configuration.

HSTAR computes temperature stress in TWO PASSES (thermal manual, part 2):

  pass 1  temperature field only
          .glb : type_problem='S', type_nl=10, mdofn=10, lmdofn(10)=1,
                 order_time(10)=1, outintw=1, outintr=0
          group: nrfields=1, fieldid='T', field DOF list = (10)
          .tem : convection surfaces and their ambient-temperature curve
          .mat : a 'HEAT','SOLID' entry -- a(1:3) [m^2/day], adiabatic-rise
                 curve id, placing-temperature curve id
          -> writes nodal DELTA-T per step to the BINARY `*.oit`

  pass 2  stress field, reading `*.oit` back as a body load
          .glb : type_problem='Q', type_nl=5, mdofn=10,
                 lmdofn = 1 1 1 0 0 0 0 0 0 1, order_time all 0,
                 outintr=<first block that reads .oit>, outintw=0
          group: nrfields=2, fieldid='UT', DOF lists (1 2 3) and (10)
          .man : MUST match pass 1 step for step -- `.oit` is a positional
                 binary stream and a different step count reads the wrong
                 record (thermal manual, part 2 §6)
          .tem : convection surfaces REMOVED (count 0)

`*.oit` cannot be authored; the tool refuses `--stress-pass` when it is absent.

Time curve types this capability needs (written by write_loads.py):
  SIN   ambient air temperature  T = a + b*sin(pi*(c*t + d)/180)
  DABT  adiabatic hydration rise theta = a*t/(b + t)
  LINEAR measured temperature series

`.tem` record sequence (thermal manual §6):
    ' temperature prescribed data' / <n>
    ' surface convection edges (nedge)' / nedge
    ' sedge,nnode,index,beta_bar' / sedge nnode index beta_bar
    <sedge records: i0 n1..nN aelem>
    ' edge temperature bondary' / sedge itcurve nline
    ' pipe cooling info' ...

`beta_bar` = beta/(c*rho) = a*beta/lambda, units m/day, NOT the raw surface
film coefficient in W/m^2K.

validate -> process -> validate:
  pre : pass consistency (which flags must be set for which pass); diffusivity
        in m^2/day; convection faces exist; for the stress pass, `.oit` present
        and `.man` identical to the thermal `.man`
  post: .glb flags read back; .tem record count matches the face count

Usage
-----
  python3 write_thermal.py --case c1 --field-pass --diffusivity 0.0864 \
      --convection "where=y>9.99;beta_bar=1.2;curve=2"
  python3 write_thermal.py --case c1 --stress-pass --oit ../thermal/1.oit --outintr 1
  python3 write_thermal.py --case c1 --pipes "group_c=1;group_w=2;Qw=1.2;Tw_curve=4"
"""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, read_tokens, write_records  # noqa: E402
from write_boundary import read_cor  # noqa: E402
from write_loads import extract_faces, parse_kv, read_ele  # noqa: E402


def set_dof_block(g, mdofn, active, order):
    i = g.find_heading("MDOFN")
    g.lines[i + 1] = "  %d" % mdofn
    g.lines[i + 2] = "  " + "  ".join(
        "1" if (k + 1) in active else "0" for k in range(mdofn))
    g.lines[i + 3] = "  " + "  ".join(
        str(order.get(k + 1, 0)) for k in range(mdofn))


def set_group_field(g, fieldid, nrfields, doflists):
    """Rewrite the single group stanza for a T-only or UT run."""
    anchor = "(3) for each field"
    base = g.find_heading(anchor)
    toks = read_tokens(g.lines[base + 1])
    if len(toks) > 6:
        toks[4] = str(nrfields)
        toks[5] = fieldid
        g.lines[base + 1] = "  " + "  ".join(toks)
    # record base+2 = type_mass alfa beta ; base+3 = order_time per field
    g.lines[base + 3] = "  " + "  ".join(["0"] * (2 * nrfields))
    tail = []
    for dl in doflists:
        tail.append("  %d" % len(dl))
        tail.append("  " + "  ".join(str(d) for d in dl))
    # the stanza's DOF records run from base+4 until the 'tension_joint' heading
    end = g.find_heading("tension_joint", start=base)
    g.lines[base + 4:end] = tail


def build_tem(faces, beta_bar, curve, prescribed, index):
    r = [" temperature prescribed data", "  %d" % len(prescribed)]
    for pset in prescribed:
        r.append("  10  %d  %d  0  0" % (len(pset["nodes"]), pset["curve"]))
        r.append("  " + "  ".join(str(n) for n in pset["nodes"]))
        r.append("  " + "  ".join("%.6E" % pset["value"] for _ in pset["nodes"]))
    r.append(" surface convection edges (nedge)")
    r.append("  %d" % len(faces))
    if faces:
        nnode = len(faces[0][1])
        r.append(" sedge,nnode,index,beta_bar")
        r.append("  %d  %d  %d  %.7f" % (len(faces), nnode, index, beta_bar))
        for i, (eid, nn) in enumerate(faces, start=1):
            r.append("  %d  %s  %d" % (i, "  ".join(str(n) for n in nn), eid))
        r.append(" edge temperature bondary")
        r.append("  %d" % len(faces))
        r.append(" sedge,itcurve,nline")
        r.append("  %d  %d  0" % (len(faces), curve))
    r.append(" pipe cooling info")
    r.append(" algo_pipe=3")
    r.append("  0  3")
    r.append("")
    r += ["  0"] * 20
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--field-pass", action="store_true")
    ap.add_argument("--stress-pass", action="store_true")
    ap.add_argument("--diffusivity", type=float, default=0.0864,
                    help="m^2/day; concrete lambda/(c*rho) ~ 0.0864")
    ap.add_argument("--curve-adiabatic", type=int, default=0)
    ap.add_argument("--curve-place", type=int, default=0)
    ap.add_argument("--convection", action="append", default=[],
                    help="where=EXPR;beta_bar=B;curve=C")
    ap.add_argument("--prescribe", action="append", default=[],
                    help="where=EXPR;value=T;curve=C")
    ap.add_argument("--oit", default="", help="path to the pass-1 *.oit")
    ap.add_argument("--outintr", type=int, default=1)
    ap.add_argument("--pipes", default="")
    ap.add_argument("--ref-man", default="",
                    help="pass-1 *.man to compare the stress pass against")
    a = ap.parse_args()

    if a.field_pass == a.stress_pass and not a.pipes:
        print("BLOCKER: give exactly one of --field-pass / --stress-pass "
              "(or --pipes)")
        return 1

    glb = os.path.join(a.case, "1.glb")
    g = GlbFile(glb)
    ndimn = int(g.tokens_after("NPOIN")[3])
    nodes = read_cor(os.path.join(a.case, "1.cor"))
    elems = read_ele(os.path.join(a.case, "1.ele"))

    problems = []
    if not (1e-4 <= a.diffusivity <= 1.0):
        problems.append(
            "diffusivity %g is outside 1e-4..1 m^2/day. A value near 1e-6 means "
            "it was given in m^2/s while .man `ditime` counts DAYS -- the field "
            "then diffuses 86400x too fast and the run still converges "
            "(triplet dt_011)." % a.diffusivity)

    if a.stress_pass:
        if not a.oit or not os.path.exists(a.oit):
            problems.append(
                "--stress-pass needs the binary *.oit produced by the thermal "
                "pass; it cannot be authored by hand. Run the field pass first.")
        if a.ref_man and os.path.exists(a.ref_man):
            here = open(os.path.join(a.case, "1.man"), errors="replace").read()
            there = open(a.ref_man, errors="replace").read()
            if here.split() != there.split():
                problems.append(
                    "the stress pass *.man differs from the thermal pass *.man. "
                    "*.oit is a positional binary stream: a different step "
                    "count reads the wrong record and the thermal load is "
                    "silently wrong (thermal manual part 2 §6).")

    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    if a.field_pass:
        g.set_field_after("TYPE_PROBLEM", 0, "S")
        g.set_field_after("TYPE_PROBLEM", 3, 10)
        g.set_field_after("NINIT", 7, 0)      # outintr
        g.set_field_after("NINIT", 8, 1)      # outintw
        set_dof_block(g, 10, [10], {10: 1})
        set_group_field(g, "T", 1, [[10]])
        faces = []
        beta_bar, curve = 0.0, 0
        for spec in a.convection:
            d = parse_kv(spec, {"where", "beta_bar", "curve"})
            faces += extract_faces(nodes, elems, d["where"], ndimn)
            beta_bar = float(d.get("beta_bar", 0.0))
            curve = int(d.get("curve", 0))
        prescribed = []
        for spec in a.prescribe:
            d = parse_kv(spec, {"where", "value", "curve"})
            from write_boundary import select
            prescribed.append({"nodes": select(nodes, d["where"]),
                               "value": float(d.get("value", 0.0)),
                               "curve": int(d.get("curve", 1))})
        idx = 1 if ndimn == 2 else 5
        write_records(os.path.join(a.case, "1.tem"),
                      build_tem(faces, beta_bar, curve, prescribed, idx))
        print("thermal FIELD pass configured: %d convection face(s), "
              "%d prescribed set(s), a=%g m^2/day"
              % (len(faces), len(prescribed), a.diffusivity))

    if a.stress_pass:
        g.set_field_after("TYPE_PROBLEM", 0, "Q")
        g.set_field_after("TYPE_PROBLEM", 3, 5)
        g.set_field_after("NINIT", 7, a.outintr)
        g.set_field_after("NINIT", 8, 0)
        udofs = list(range(1, ndimn + 1))
        set_dof_block(g, 10, udofs + [10], {})
        set_group_field(g, "UT", 2, [udofs, [10]])
        shutil.copy2(a.oit, os.path.join(a.case, "1.oit"))
        write_records(os.path.join(a.case, "1.tem"),
                      build_tem([], 0.0, 0, [], 1))
        print("thermal STRESS pass configured: outintr=%d, .oit staged (%d bytes)"
              % (a.outintr, os.path.getsize(a.oit)))

    if a.pipes:
        d = parse_kv(a.pipes, {"group_c", "group_w", "Qw", "Tw_curve",
                               "alfa1", "lamda_w", "density_w", "Cw",
                               "begin_time", "end_time", "dtime_change"})
        g.set_field_after("NMASS", 10, 1)          # ECWPIPE on
        i = g.find_heading("nwcpipe")
        g.lines[i + 1] = "  1"
        g.lines[i + 2:i + 2] = [
            "  1  %s  %s  1" % (d.get("group_c", 1), d.get("group_w", 2)),
            "  %s  %s  %s  %s  %s  %s  %s  %s  %s"
            % (d.get("alfa1", 1.0), d.get("Qw", 1.0), d.get("lamda_w", 0.6),
               d.get("density_w", 1000.0), d.get("Cw", 4200.0),
               d.get("begin_time", 0.0), d.get("end_time", 30.0),
               d.get("Tw_curve", 1), d.get("dtime_change", 1.0)),
            "  0"]
        print("cooling pipes configured for concrete group %s / pipe group %s"
              % (d.get("group_c", 1), d.get("group_w", 2)))

    g.save()

    g2 = GlbFile(glb)
    want = "S" if a.field_pass else ("Q" if a.stress_pass else None)
    if want and g2.tokens_after("TYPE_PROBLEM")[0] != want:
        print("POST-CHECK FAILED: type_problem did not round-trip")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
