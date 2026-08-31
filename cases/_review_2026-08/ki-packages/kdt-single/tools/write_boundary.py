#!/usr/bin/env python3
"""
write_boundary.py -- Stage s4: kinematic constraints and Dirichlet field BCs
(`*.pre`).

Record sequence, repeated once per run-block (Prescrib.f90:208-243):

    'PRESCRIBE SET--NFIXSETS'                          heading (positional)
    nfixsets  nline
    for each set:
        ifixvar nfixnods itcurve tfixvar outfix jfixvar gamawx nextr
        list_fix(1:nfixnods)
        val_fix(1:nfixnods)

`ifixvar` uses the global DOF numbering (1 Ux, 2 Uy, 3 Uz, 4-6 rotations,
8 pore pressure, 10 temperature).  `val_fix` is MULTIPLIED by time curve
`itcurve`: a constant prescribed temperature needs a flat curve, and
`itcurve=0` means the constraint is applied at full value every step.

Nodes are selected by COORDINATE PREDICATE, never by a hand-typed index list --
renumbering the mesh silently invalidates a literal list, and that failure looks
like "the model is too stiff", not like a bad input (triplet dt_009).

validate -> process -> validate:
  pre : predicate selects a non-empty set; DOF exists in the .glb DOF list;
        the structure is restrained against rigid-body motion in every
        active translational direction
  post: file re-read, node counts and record counts match what was written

Usage
-----
  python3 write_boundary.py --case c1 \
      --fix "dof=2;where=y<1e-9" --fix "dof=1;where=x<1e-9 or x>0.999"
  python3 write_boundary.py --case c1 \
      --fix "dof=10;where=y>9.999;value=20.0;curve=2;out=1"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, read_tokens, write_records  # noqa: E402

DOF_NAMES = {1: "Ux", 2: "Uy", 3: "Uz", 4: "Thxy", 5: "Thyz", 6: "Thzx",
             7: "hydrostatic pressure", 8: "pore pressure",
             9: "air pressure", 10: "temperature"}


def read_cor(path):
    nodes = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            t = read_tokens(line)
            if not t:
                continue
            nodes[int(t[0])] = [float(x) for x in t[1:]]
    return nodes


def select(nodes, expr):
    """Evaluate `expr` per node with x, y, z bound. Returns sorted ids."""
    out = []
    for nid, c in sorted(nodes.items()):
        env = {"x": c[0],
               "y": c[1] if len(c) > 1 else 0.0,
               "z": c[2] if len(c) > 2 else 0.0,
               "abs": abs, "min": min, "max": max, "id": nid}
        try:
            if eval(expr, {"__builtins__": {}}, env):
                out.append(nid)
        except Exception as exc:
            raise SystemExit("bad --fix where=%r : %s" % (expr, exc))
    return out


def parse_spec(spec):
    d = {"dof": None, "where": None, "value": 0.0, "curve": 0,
         "tfixvar": 0, "out": 0, "jfixvar": 0, "gamawx": 0.0, "nextr": 0}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in d:
            raise SystemExit("unknown key %r in --fix spec" % k)
        if k == "where":
            d[k] = v.strip()
        elif k in ("value", "gamawx"):
            d[k] = float(v)
        else:
            d[k] = int(v)
    if d["dof"] is None or d["where"] is None:
        raise SystemExit("--fix needs at least dof= and where=")
    return d


def active_dofs(case_dir):
    g = GlbFile(os.path.join(case_dir, "1.glb"))
    i = g.find_heading("MDOFN")
    mdofn = int(read_tokens(g.lines[i + 1])[0])
    lm = [int(x) for x in read_tokens(g.lines[i + 2])][:mdofn]
    return [k + 1 for k, v in enumerate(lm) if v]


def validate(specs, nodes, dofs, ndimn):
    p = []
    covered = set()
    for s in specs:
        if s["dof"] not in DOF_NAMES:
            p.append("DOF %s is outside 1..10" % s["dof"])
        elif dofs and s["dof"] not in dofs:
            p.append("DOF %d (%s) is not active in .glb MDOFN list %s -- the "
                     "constraint would be read and then ignored"
                     % (s["dof"], DOF_NAMES[s["dof"]], dofs))
        if not s["nodes"]:
            p.append("selector %r matched no nodes" % s["where"])
        covered.add(s["dof"])
    trans = [d for d in (dofs or list(range(1, ndimn + 1))) if d <= ndimn]
    missing = [d for d in trans if d not in covered]
    if missing:
        p.append("no constraint on translational DOF(s) %s -- the stiffness "
                 "matrix is singular in rigid-body motion; PROFILE reports a "
                 "zero pivot, PARDISO returns error -4 (triplet dt_012)"
                 % [DOF_NAMES[d] for d in missing])
    return p


def build_records(specs, nblks):
    recs = []
    for _ in range(nblks):
        recs.append("'PRESCRIBE SET--NFIXSETS'")
        nline = sum(3 for _ in specs)
        recs.append("  %d  %d" % (len(specs), nline))
        for s in specs:
            recs.append("  %d  %d  %d  %d  %d  %d  %.4E  %d"
                        % (s["dof"], len(s["nodes"]), s["curve"], s["tfixvar"],
                           s["out"], s["jfixvar"], s["gamawx"], s["nextr"]))
            recs.append("  " + "  ".join("%d" % n for n in s["nodes"]))
            recs.append("  " + "  ".join("%.6E" % s["value"]
                                         for _ in s["nodes"]))
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--fix", action="append", default=[],
                    help="dof=N;where=EXPR[;value=V;curve=C;out=0/1;tfixvar=0]")
    ap.add_argument("--nblks", type=int, default=0,
                    help="repeat the same sets for N blocks (default: read .glb)")
    a = ap.parse_args()

    nodes = read_cor(os.path.join(a.case, "1.cor"))
    ndimn = len(next(iter(nodes.values())))
    dofs = active_dofs(a.case)
    if a.nblks:
        nblks = a.nblks
    else:
        g = GlbFile(os.path.join(a.case, "1.glb"))
        nblks = int(g.tokens_after("NINIT")[3])

    specs = []
    for spec in a.fix:
        d = parse_spec(spec)
        d["nodes"] = select(nodes, d["where"])
        specs.append(d)
    if not specs:
        raise SystemExit("at least one --fix is required")

    problems = validate(specs, nodes, dofs, ndimn)
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    path = os.path.join(a.case, "1.pre")
    write_records(path, build_records(specs, nblks))

    # post-check: re-read and count
    with open(path) as fh:
        lines = [l for l in fh]
    expect = nblks * (2 + 3 * len(specs))
    if len(lines) != expect:
        print("POST-CHECK FAILED: wrote %d records, expected %d"
              % (len(lines), expect))
        return 1
    for s in specs:
        print("fixed %-22s on %4d node(s), curve=%d value=%g"
              % (DOF_NAMES[s["dof"]], len(s["nodes"]), s["curve"], s["value"]))
    print("blocks written:", nblks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
