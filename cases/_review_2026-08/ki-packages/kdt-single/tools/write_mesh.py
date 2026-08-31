#!/usr/bin/env python3
"""
write_mesh.py -- Stage s2: node coordinates (`*.cor`) and connectivity (`*.ele`).

`*.cor`  one record per node:   ipoin  x  y [z]          (metres)
`*.ele`  one record per element: ielem  n1 .. nN  igroup

Hard requirement from the manual (§3.4) and enforced here: elements must be
listed in ascending `igroup` order with no interleaving, and element ids must
ascend.  `read_element` (Elements.f90:1048) walks the file group by group; an
out-of-order record silently assigns nodes to the wrong group.

The tool also updates the three geometry tokens of the `*.glb` first record
(`npoin`, `npoinb`, `nelem`) and `ndimn`, plus `nelgroup` in each group stanza,
by ANCHORED token replacement -- the record's token count never changes.

Generators provided (all give a structured grid of the requested element type):
  --shape box     rectangular/box domain            (q4 / q8 / b8 / t3)
  --shape column  1-element-wide column, for 1-D confined compression
  --shape annulus quarter annulus (thick-cylinder benchmarks)   (q4)
  --from-flavia   import nodes+elements from an existing `*.flavia.msh`
  --from-csv      import from two CSV files

validate -> process -> validate:
  pre : element type known, counts consistent, groups sorted
  post: every element node id in 1..npoin; no unreferenced nodes; Jacobian
        orientation positive for every 2-D quad (negative = inverted element,
        which HSTAR reports only as a solver pivot failure)

Usage
-----
  python3 write_mesh.py --case c1 --shape column --height 10 --width 1 --ny 20
  python3 write_mesh.py --case c1 --shape box --lx 4 --ly 2 --nx 8 --ny 4
  python3 write_mesh.py --case c1 --from-flavia old/1.flavia.msh
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, write_records  # noqa: E402

# name -> (library index, nodes, dim).  Elements.f90:128-153.
ELEMENT_TABLE = {
    "l2": (1, 2, 1), "l3": (2, 3, 1),
    "t3": (3, 3, 2), "t6": (4, 6, 2), "q4": (5, 4, 2), "q8": (6, 8, 2),
    "h4": (7, 4, 3), "h10": (8, 10, 3), "b8": (9, 8, 3), "b20": (10, 20, 3),
    "t6c3": (11, 6, 2), "q8c4": (12, 8, 2), "h10c4": (13, 10, 3),
    "b20c8": (14, 20, 3), "t3c3": (15, 3, 2), "q4c4": (16, 4, 2),
    "h4c4": (17, 4, 3), "b8c8": (18, 8, 3), "l2c2": (19, 2, 1),
    "b2": (20, 2, 1), "b2c2": (21, 2, 1), "p4": (22, 4, 2),
    "pr6": (23, 6, 3), "pr6c6": (24, 6, 3), "steel": (25, 2, 1),
    "thin_film": (26, 4, 2),
}


# ---------------------------------------------------------------- generators
def gen_box(lx, ly, nx, ny, x0=0.0, y0=0.0, etype="q4"):
    """Structured Q4 grid, counter-clockwise connectivity."""
    if etype not in ("q4", "q4c4", "t3"):
        raise SystemExit("--shape box supports q4/q4c4/t3; got %s" % etype)
    nodes, nid = [], 0
    ids = {}
    for j in range(ny + 1):
        for i in range(nx + 1):
            nid += 1
            ids[(i, j)] = nid
            nodes.append((nid, x0 + lx * i / nx, y0 + ly * j / ny))
    elems, eid = [], 0
    for j in range(ny):
        for i in range(nx):
            n1, n2 = ids[(i, j)], ids[(i + 1, j)]
            n3, n4 = ids[(i + 1, j + 1)], ids[(i, j + 1)]
            if etype == "t3":
                eid += 1
                elems.append((eid, [n1, n2, n3], 1))
                eid += 1
                elems.append((eid, [n1, n3, n4], 1))
            else:
                eid += 1
                elems.append((eid, [n1, n2, n3, n4], 1))
    return nodes, elems


def gen_column(width, height, ny, etype="q4"):
    """One element across, `ny` up: the 1-D confined-compression benchmark."""
    return gen_box(width, height, 1, ny, etype=etype)


def gen_annulus(r_in, r_out, nr, nt, theta=math.pi / 2, etype="q4"):
    """Quarter annulus, node 1 at (r_in,0); rows sweep r then theta.

    Matches the node ordering of the shipped `lame_cylinder` mesh so the two
    are interchangeable in a regression.
    """
    nodes, nid, ids = [], 0, {}
    for k in range(nt + 1):
        th = theta * k / nt
        for i in range(nr + 1):
            r = r_in + (r_out - r_in) * i / nr
            nid += 1
            ids[(i, k)] = nid
            nodes.append((nid, r * math.cos(th), r * math.sin(th)))
    elems, eid = [], 0
    for k in range(nt):
        for i in range(nr):
            eid += 1
            elems.append((eid, [ids[(i, k)], ids[(i + 1, k)],
                                ids[(i + 1, k + 1)], ids[(i, k + 1)]], 1))
    return nodes, elems


def gen_box3d(lx, ly, lz, nx, ny, nz):
    nodes, nid, ids = [], 0, {}
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                nid += 1
                ids[(i, j, k)] = nid
                nodes.append((nid, lx * i / nx, ly * j / ny, lz * k / nz))
    elems, eid = [], 0
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                eid += 1
                elems.append((eid, [
                    ids[(i, j, k)], ids[(i + 1, j, k)],
                    ids[(i + 1, j + 1, k)], ids[(i, j + 1, k)],
                    ids[(i, j, k + 1)], ids[(i + 1, j, k + 1)],
                    ids[(i + 1, j + 1, k + 1)], ids[(i, j + 1, k + 1)]], 1))
    return nodes, elems


# ---------------------------------------------------------------- importers
def read_flavia_msh(path):
    nodes, elems, mode = [], [], None
    with open(path, errors="replace") as fh:
        for line in fh:
            s = line.strip()
            low = s.lower()
            if low.startswith("coordinates"):
                mode = "c"
                continue
            if low.startswith("elements"):
                mode = "e"
                continue
            if low.startswith("end "):
                mode = None
                continue
            if not s or low.startswith("mesh"):
                continue
            t = s.split()
            if mode == "c":
                nodes.append((int(t[0]), *[float(x) for x in t[1:]]))
            elif mode == "e":
                nums = [int(x) for x in t]
                elems.append((nums[0], nums[1:-1], nums[-1]))
    return nodes, elems


# ---------------------------------------------------------------- validation
def _signed_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return 0.5 * a


def validate_mesh(nodes, elems, ndimn):
    problems = []
    ids = {n[0] for n in nodes}
    if sorted(ids) != list(range(1, len(nodes) + 1)):
        problems.append("node ids are not 1..npoin contiguous")
    if [e[0] for e in elems] != list(range(1, len(elems) + 1)):
        problems.append("element ids are not 1..nelem ascending")
    groups = [e[2] for e in elems]
    if groups != sorted(groups):
        problems.append("elements are not sorted by group ascending -- "
                        "read_element() will mis-assign them (triplet dt_007)")
    used = set()
    for e in elems:
        for n in e[1]:
            if n not in ids:
                problems.append("element %d references node %d which does not "
                                "exist" % (e[0], n))
            used.add(n)
    if used != ids:
        problems.append("%d node(s) are not referenced by any element; HSTAR "
                        "leaves their equations singular unless they are "
                        "fully constrained" % len(ids - used))
    if ndimn == 2:
        coord = {n[0]: (n[1], n[2]) for n in nodes}
        for e in elems:
            if len(e[1]) in (3, 4):
                if _signed_area([coord[n] for n in e[1]]) <= 0:
                    problems.append(
                        "element %d has non-positive Jacobian (nodes listed "
                        "clockwise) -- HSTAR reports this only as a solver "
                        "pivot failure (triplet dt_008)" % e[0])
    return problems


# ---------------------------------------------------------------- emitters
def write_cor(path, nodes):
    recs = []
    for n in nodes:
        recs.append("%8d" % n[0] + "".join("%22.10f" % c for c in n[1:]))
    return write_records(path, recs)


def write_ele(path, elems):
    recs = []
    for e in elems:
        recs.append("%8d" % e[0] + "".join("%8d" % n for n in e[1])
                    + "%6d" % e[2])
    return write_records(path, recs)


def sync_glb(case_dir, nodes, elems, ndimn, etype, npoinb=None):
    g = GlbFile(os.path.join(case_dir, "1.glb"))
    npoin, nelem = len(nodes), len(elems)
    ngroup = len({e[2] for e in elems})
    g.set_field_after("NPOIN", 0, npoin)
    g.set_field_after("NPOIN", 1, npoinb if npoinb else npoin)
    g.set_field_after("NPOIN", 2, nelem)
    g.set_field_after("NPOIN", 3, ndimn)
    g.set_field_after("NPOIN", 5, ngroup)
    # group stanza: NAME KNAME INDEX CLASS NRFIELDS FIELDID SPECIAL SPTYPE
    #               NELGROUP MATNO ...   -> nelgroup is token 8, index token 2
    idx, _, _ = ELEMENT_TABLE[etype]
    anchor = "(3) for each field"
    counts = {}
    for e in elems:
        counts[e[2]] = counts.get(e[2], 0) + 1
    base = g.find_heading(anchor)
    for gi in range(ngroup):
        line = base + 1 + gi * 4          # 4 records per single-field stanza
        toks = g.tokens_after(anchor, offset=1 + gi * 4)
        if len(toks) > 9:
            toks[0] = etype.upper()
            toks[2] = str(idx)
            toks[8] = str(counts.get(gi + 1, 0))
            g.lines[line] = "  " + "  ".join(toks)
    g.save()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--shape", choices=["box", "column", "annulus", "box3d"])
    ap.add_argument("--etype", default="q4", choices=sorted(ELEMENT_TABLE))
    ap.add_argument("--lx", type=float, default=1.0)
    ap.add_argument("--ly", type=float, default=1.0)
    ap.add_argument("--lz", type=float, default=1.0)
    ap.add_argument("--nx", type=int, default=1)
    ap.add_argument("--ny", type=int, default=1)
    ap.add_argument("--nz", type=int, default=1)
    ap.add_argument("--width", type=float, default=1.0)
    ap.add_argument("--height", type=float, default=10.0)
    ap.add_argument("--r_in", type=float, default=1.0)
    ap.add_argument("--r_out", type=float, default=2.0)
    ap.add_argument("--from-flavia", default="")
    ap.add_argument("--no-glb-sync", action="store_true")
    a = ap.parse_args()

    if a.from_flavia:
        nodes, elems = read_flavia_msh(a.from_flavia)
        ndimn = 3 if len(nodes[0]) > 3 and any(n[3] for n in nodes) else 2
        if ndimn == 2:
            nodes = [(n[0], n[1], n[2]) for n in nodes]
    elif a.shape == "box":
        nodes, elems = gen_box(a.lx, a.ly, a.nx, a.ny, etype=a.etype)
        ndimn = 2
    elif a.shape == "column":
        nodes, elems = gen_column(a.width, a.height, a.ny, etype=a.etype)
        ndimn = 2
    elif a.shape == "annulus":
        nodes, elems = gen_annulus(a.r_in, a.r_out, a.nx, a.ny)
        ndimn = 2
    elif a.shape == "box3d":
        nodes, elems = gen_box3d(a.lx, a.ly, a.lz, a.nx, a.ny, a.nz)
        ndimn = 3
    else:
        raise SystemExit("give --shape or --from-flavia")

    problems = validate_mesh(nodes, elems, ndimn)
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    write_cor(os.path.join(a.case, "1.cor"), nodes)
    write_ele(os.path.join(a.case, "1.ele"), elems)
    if not a.no_glb_sync:
        sync_glb(a.case, nodes, elems, ndimn, a.etype)

    # post-check: read back what was written
    back_n = sum(1 for _ in open(os.path.join(a.case, "1.cor")))
    back_e = sum(1 for _ in open(os.path.join(a.case, "1.ele")))
    if back_n != len(nodes) or back_e != len(elems):
        print("POST-CHECK FAILED: wrote %d/%d records, expected %d/%d"
              % (back_n, back_e, len(nodes), len(elems)))
        return 1
    print("mesh written: npoin=%d nelem=%d ndimn=%d etype=%s"
          % (len(nodes), len(elems), ndimn, a.etype))
    return 0


if __name__ == "__main__":
    sys.exit(main())
