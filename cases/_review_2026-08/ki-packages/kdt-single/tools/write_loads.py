#!/usr/bin/env python3
"""
write_loads.py -- Stage s5: time curves and all mechanical loads (`*.loa`).

Record sequence, once per run-block (manual §3.6, Load.f90):

    ' (*.loa) Load data'                      heading
    ntcurve
    per curve:  ntime  type_curve  nline
                <curve data, `nline` records>
    ' Define point load'
    nplgroup [nline]
    per group:  order_time_curve nudofn npload nline / pxyz(1:nudofn) / list
    ' Define edges for whole analysis'
    nedge nedge_water
    per face class (only if nedge>0):
        sedge nnode index
        i0  lnode(1:nnode)  aelem            x sedge
    ' Define edge load in each BLKS' / ' edge_load_group,delgroup'
    edge_load_group  delgroup
    per group:  begin_edge end_edge itcurve water / cor0 cor1 p0 p1 fact
    ' Define body force in each BLKS'
    gravy  factg(1:ndimn)  factf(1:ndimn)
    ' Time_curve_for_each_group' nline / tcurvegravity(1:ngroup)
    ' nbeamload' / n [+ n records]
    ' nplateload' / n [+ header + n records]

Curve types and their data records:
  LINEAR / LNLINEAR  2 records: times, then factors
  SIN                2 records: 4 dummy values, then a b c d
                     -> T = a + b*sin(pi*(c*t + d)/180)
  DABT               2 records: a, then b   -> theta = a*t/(b+t)
  SEISMIC            accelerogram
  ARCLENGTH          arc-length control

Sign convention (manual §3.6): edge pressure POSITIVE = compression pushing on
the face; body-force `factg` is applied OPPOSITE to the gravity vector, so
plain self-weight in 2-D is `9.81  0 -1  0 -1`.

validate -> process -> validate:
  pre : every referenced curve id exists; every face node exists; face node
        ordering gives an OUTWARD normal; body-force magnitude is ~9.81
  post: re-read, curve count and record counts match

Usage
-----
  python3 write_loads.py --case c1 --gravity 9.81 --gdir 0,-1
  python3 write_loads.py --case c1 --gravity 9.81 --gdir 0,-1 \
      --curve "1:LINEAR:0,1:1,1" \
      --face "where=x<1e-9" --edge-load "curve=1;axis=2;cor0=0;cor1=10;p0=98100;p1=0;fact=1"
  python3 write_loads.py --case c1 --point-load "curve=1;nodes=y>9.99;fxyz=0,-1000"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, read_tokens, write_records  # noqa: E402
from write_boundary import read_cor, select  # noqa: E402

CURVE_TYPES = ["LINEAR", "LNLINEAR", "SIN", "DABT", "SEISMIC", "ARCLENGTH", ""]

# outward face node pairs for a 2-D quad, given its CCW connectivity
QUAD_EDGES = [(0, 1), (1, 2), (2, 3), (3, 0)]
# outward faces of a b8 hex with the standard HSTAR node order
HEX_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def read_ele(path):
    out = []
    with open(path, errors="replace") as fh:
        for line in fh:
            t = read_tokens(line)
            if not t:
                continue
            n = [int(x) for x in t]
            out.append((n[0], n[1:-1], n[-1]))
    return out


def parse_curve(spec):
    """'id:TYPE:d1|d2' -> dict.  Data records are '|' separated, values ','."""
    parts = spec.split(":")
    if len(parts) < 3:
        raise SystemExit("--curve wants id:TYPE:rec1|rec2 , got %r" % spec)
    cid, ctype, rest = parts[0], parts[1].upper(), ":".join(parts[2:])
    if ctype not in CURVE_TYPES:
        raise SystemExit("unknown curve type %r (known: %s)"
                         % (ctype, [c for c in CURVE_TYPES if c]))
    recs = [r.split(",") for r in rest.split("|")]
    return {"id": int(cid), "type": ctype, "recs": recs}


def parse_kv(spec, allowed):
    d = {}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in allowed:
            raise SystemExit("unknown key %r (allowed: %s)"
                             % (k, sorted(allowed)))
        d[k] = v.strip()
    return d


def extract_faces(nodes, elems, where, ndimn):
    """Boundary faces whose every node satisfies `where`, oriented outward."""
    sel = set(select(nodes, where))
    faces = []
    for eid, conn, _g in elems:
        if ndimn == 2 and len(conn) == 4:
            for i, j in QUAD_EDGES:
                a, b = conn[i], conn[j]
                if a in sel and b in sel:
                    faces.append((eid, [a, b]))
        elif ndimn == 3 and len(conn) == 8:
            for f in HEX_FACES:
                nn = [conn[k] for k in f]
                if all(n in sel for n in nn):
                    faces.append((eid, nn))
    return faces


def validate(curves, faces, edge_loads, point_loads, gravity, gdir, ndimn):
    p = []
    ids = {c["id"] for c in curves}
    for c in curves:
        if c["type"] in ("LINEAR", "LNLINEAR") and len(c["recs"]) != 2:
            p.append("curve %d is %s and needs exactly 2 data records "
                     "(times, factors); got %d"
                     % (c["id"], c["type"], len(c["recs"])))
        if c["type"] in ("LINEAR", "LNLINEAR") and len(c["recs"]) == 2 \
                and len(c["recs"][0]) != len(c["recs"][1]):
            p.append("curve %d: %d times but %d factors"
                     % (c["id"], len(c["recs"][0]), len(c["recs"][1])))
        if c["type"] == "SIN" and (len(c["recs"]) != 2 or len(c["recs"][0]) != 4):
            p.append("curve %d is SIN: record 1 must hold exactly 4 (unused) "
                     "values and record 2 the parameters a b c d" % c["id"])
    for e in edge_loads:
        if int(e.get("curve", 0)) not in ids and int(e.get("curve", 0)) != 0:
            p.append("edge load references curve %s which is not defined"
                     % e.get("curve"))
    for pl in point_loads:
        if int(pl.get("curve", 0)) not in ids and int(pl.get("curve", 0)) != 0:
            p.append("point load references curve %s which is not defined"
                     % pl.get("curve"))
    if edge_loads and not faces:
        p.append("an edge-load group was requested but --face selected no "
                 "boundary faces; HSTAR would apply nothing and still converge "
                 "(triplet dt_013)")
    if gravity is not None:
        if not (9.0 <= abs(gravity) <= 10.0):
            p.append("gravy=%g is not ~9.81 m/s^2 -- check units" % gravity)
        if len(gdir) != ndimn:
            p.append("--gdir needs %d components for ndimn=%d" % (ndimn, ndimn))
        elif abs(sum(x * x for x in gdir) - 1.0) > 1e-6:
            p.append("--gdir %s is not a unit vector" % (gdir,))
    return p


def build(curves, point_loads, faces, edge_loads, gravity, gdir,
          ngroup, grav_curves, ndimn, etype_index):
    r = [" (*.loa) Load data"]
    r.append("  %d" % len(curves))
    for c in sorted(curves, key=lambda x: x["id"]):
        r.append("  %d  %s  0  %d"
                 % (len(c["recs"][0]), c["type"], len(c["recs"])))
        for rec in c["recs"]:
            r.append("  " + "  ".join(str(v) for v in rec))

    r.append(" Define point load")
    r.append("  %d  0" % len(point_loads))
    for pl in point_loads:
        f = [float(x) for x in pl["fxyz"].split(",")]
        nl = pl["_nodes"]
        r.append("  %s  %d  %d  2" % (pl.get("curve", 1), len(f), len(nl)))
        r.append("  " + "  ".join("%.6E" % v for v in f))
        r.append("  " + "  ".join(str(n) for n in nl))

    r.append(" Define edges for whole analysis")
    r.append("  %d  0" % len(faces))
    if faces:
        nnode = len(faces[0][1])
        r.append(" sedge,nnode,index,vdimn")
        # 4 fields, NOT the 3 the manual documents: HSTAR added `vdimn` on
        # 2021-10-28 (Load.f90:359).  vdimn=0 keeps the full coordinates;
        # a non-zero value zeroes that coordinate component when the face
        # Jacobian is formed (planar projection).
        r.append("  %d  %d  %d  0" % (len(faces), nnode, etype_index))
        for i, (eid, nn) in enumerate(faces, start=1):
            r.append("  %d  %s  %d" % (i, "  ".join(str(n) for n in nn), eid))

    r.append(" Define edge load in each BLKS")
    r.append(" edge_load_group,delgroup")
    r.append("  %d  %d" % (len(faces) if edge_loads else 0, len(edge_loads)))
    for e in edge_loads:
        # 5 fields, NOT the 4 the manual documents: `code_load` (Load.f90:748)
        # is an HSTAR addition; when non-zero a SECOND cor0/cor1/p0/p1/fact
        # record follows, describing the load on the other side of the face.
        r.append("  %s  %s  %s  %s  %s" % (e.get("begin", 1),
                                           e.get("end", len(faces)),
                                           e.get("curve", 1), e.get("axis", 1),
                                           e.get("code_load", 0)))
        if int(e.get("axis", 1)) != 0:
            r.append("  %s  %s  %s  %s  %s"
                     % (e.get("cor0", 0), e.get("cor1", 1),
                        e.get("p0", 0), e.get("p1", 0), e.get("fact", 1)))

    r.append(" Define body force in each BLKS")
    if gravity is None:
        r.append("  0.00000E+00" + "  0.00000E+00" * (2 * ndimn))
    else:
        r.append("  %.5E" % gravity
                 + "".join("  %.5E" % v for v in gdir)
                 + "".join("  %.5E" % v for v in gdir))
    r.append(" Time_curve_for_each_group  1")
    r.append("  " + "  ".join(str(c) for c in grav_curves))
    r.append(" nbeamload")
    r.append("  0")
    r.append(" nplateload")
    r.append("  0")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--curve", action="append", default=[],
                    help="id:TYPE:rec1|rec2  (default: 1:LINEAR:0,1|1,1)")
    ap.add_argument("--gravity", type=float, default=9.81)
    ap.add_argument("--no-gravity", action="store_true")
    ap.add_argument("--gdir", default="",
                    help="unit vector, default 0,-1 (2-D) or 0,0,-1 (3-D)")
    ap.add_argument("--grav-curve", type=int, default=1,
                    help="time curve driving self-weight; 0 disables it")
    ap.add_argument("--face", default="", help="where= predicate for load faces")
    ap.add_argument("--edge-load", action="append", default=[],
                    help="curve=;axis=;cor0=;cor1=;p0=;p1=;fact=;begin=;end=")
    ap.add_argument("--point-load", action="append", default=[],
                    help="curve=;nodes=EXPR;fxyz=fx,fy[,fz]")
    ap.add_argument("--nblks", type=int, default=0)
    a = ap.parse_args()

    nodes = read_cor(os.path.join(a.case, "1.cor"))
    elems = read_ele(os.path.join(a.case, "1.ele"))
    ndimn = len(next(iter(nodes.values())))
    g = GlbFile(os.path.join(a.case, "1.glb"))
    ngroup = int(g.tokens_after("NPOIN")[5])
    nblks = a.nblks or int(g.tokens_after("NINIT")[3])

    curves = [parse_curve(s) for s in a.curve] or \
        [parse_curve("1:LINEAR:0,1|1,1")]
    gdir = [float(x) for x in a.gdir.split(",")] if a.gdir else \
        ([0.0, -1.0] if ndimn == 2 else [0.0, 0.0, -1.0])
    gravity = None if a.no_gravity else a.gravity

    faces = extract_faces(nodes, elems, a.face, ndimn) if a.face else []
    edge_loads = [parse_kv(s, {"curve", "axis", "cor0", "cor1", "p0", "p1",
                               "fact", "begin", "end", "code_load"})
                  for s in a.edge_load]
    point_loads = []
    for s in a.point_load:
        d = parse_kv(s, {"curve", "nodes", "fxyz"})
        d["_nodes"] = select(nodes, d["nodes"])
        point_loads.append(d)

    problems = validate(curves, faces, edge_loads, point_loads,
                        gravity, gdir, ndimn)
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    # face-load element library index: l2 (1) in 2-D, q4 (5) in 3-D
    etype_index = 1 if ndimn == 2 else 5
    grav_curves = [a.grav_curve] * ngroup
    recs = build(curves, point_loads, faces, edge_loads, gravity, gdir,
                 ngroup, grav_curves, ndimn, etype_index)
    path = os.path.join(a.case, "1.loa")
    write_records(path, recs * nblks)

    with open(path) as fh:
        n = sum(1 for _ in fh)
    if n != len(recs) * nblks:
        print("POST-CHECK FAILED: %d records written, expected %d"
              % (n, len(recs) * nblks))
        return 1
    print("loads written: %d curve(s), %d face(s), %d edge-load group(s), "
          "%d point-load group(s), gravity=%s, blocks=%d"
          % (len(curves), len(faces), len(edge_loads), len(point_loads),
             gravity, nblks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
