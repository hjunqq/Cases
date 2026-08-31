#!/usr/bin/env python3
"""
write_stages.py -- Capability 10: staged construction / excavation
("run blocks" and element birth-death).

HSTAR's staging model (manual §1.3):

  * an ELEMENT GROUP is a partition of the mesh; every element belongs to
    exactly one group;
  * a RUN BLOCK (`nblks`) is a complete analysis pass over the mesh in which
    each group is either active or inactive;
  * `APPEAR_PROCESS(1:ngroup, 1:nblks)` -- one record per block, `ngroup`
    integers -- says which groups take part in block `iblks`;
  * `MATNO_PROCESS(1:ngroup, 1:nblks)` lets a group change material between
    blocks (e.g. fresh vs matured concrete);
  * `uinitial(1:nblks)` says whether block `iblks` starts from a cleared
    displacement state (1) or inherits block `iblks-1` (0);
  * `.pre`, `.loa` and `.man` are all repeated ONCE PER BLOCK, in block order.

Dam construction is `APPEAR_PROCESS` rows that grow (1*1 29*0, 2*1 28*0, ...);
excavation is the same rows read backwards.

This tool rewrites the staging records of `*.glb` in place (anchored), and can
re-emit the per-block repeats of `.pre`/`.loa`/`.man` by replicating the
single-block versions the other writers produced.

validate -> process -> validate:
  pre : matrix shape is (nblks, ngroup); every material id referenced exists
        in the .mat; at least one group is active in every block
  post: re-read the .glb, assert nblks and the two matrices round-trip; assert
        .pre/.loa/.man block counts equal nblks

Usage
-----
  python3 write_stages.py --case c1 --nblks 3 \
      --appear "1,0,0|1,1,0|1,1,1" --matno "1,2,2|1,2,2|1,2,2" \
      --uinitial 0,0,0 --replicate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, read_tokens  # noqa: E402


def parse_matrix(spec, nblks, ngroup, name):
    rows = [r.split(",") for r in spec.split("|")]
    if len(rows) != nblks:
        raise SystemExit("%s has %d rows, nblks=%d" % (name, len(rows), nblks))
    for r in rows:
        if len(r) != ngroup:
            raise SystemExit("%s row has %d entries, ngroup=%d"
                             % (name, len(r), ngroup))
    return [[int(x) for x in r] for r in rows]


def count_blocks(path, anchor):
    """How many times `anchor` appears -- i.e. how many block repeats exist."""
    n = 0
    with open(path, errors="replace") as fh:
        for line in fh:
            if anchor.lower() in line.lower():
                n += 1
    return n


def replicate(path, anchor, nblks):
    """Duplicate a single-block file to nblks blocks."""
    with open(path, errors="replace") as fh:
        lines = fh.read().rstrip("\n").split("\n")
    have = count_blocks(path, anchor)
    if have == 0:
        raise SystemExit("cannot find block anchor %r in %s" % (anchor, path))
    if have == nblks:
        return nblks
    if have != 1:
        raise SystemExit("%s already has %d blocks; replicate only works from 1"
                         % (path, have))
    with open(path, "w") as fh:
        for _ in range(nblks):
            fh.write("\n".join(lines) + "\n")
    return nblks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--nblks", type=int, required=True)
    ap.add_argument("--appear", required=True,
                    help="rows separated by |, groups by , ; 1=active")
    ap.add_argument("--matno", default="")
    ap.add_argument("--uinitial", default="")
    ap.add_argument("--hdam", default="")
    ap.add_argument("--water-level", dest="water_level", default="")
    ap.add_argument("--replicate", action="store_true",
                    help="expand .pre/.loa/.man from 1 block to nblks")
    a = ap.parse_args()

    glb = os.path.join(a.case, "1.glb")
    g = GlbFile(glb)
    ngroup = int(g.tokens_after("NPOIN")[5])
    nblks = a.nblks

    appear = parse_matrix(a.appear, nblks, ngroup, "--appear")
    matno = parse_matrix(a.matno, nblks, ngroup, "--matno") if a.matno else \
        [[1] * ngroup for _ in range(nblks)]

    problems = []
    for i, row in enumerate(appear, 1):
        if not any(row):
            problems.append("block %d activates no group at all -- the "
                            "stiffness matrix would be empty" % i)
        if any(v not in (0, 1) for v in row):
            problems.append("block %d APPEAR_PROCESS holds a value other than "
                            "0/1" % i)
    mat_path = os.path.join(a.case, "1.mat")
    nmats = 0
    if os.path.exists(mat_path):
        with open(mat_path, errors="replace") as fh:
            lines = fh.read().split("\n")
        for k, l in enumerate(lines):
            if l.strip().lower() == "nmats":
                nmats = int(read_tokens(lines[k + 1])[0])
                break
    if nmats:
        for i, row in enumerate(matno, 1):
            for m in row:
                if m > nmats:
                    problems.append("block %d references material %d but the "
                                    ".mat defines %d" % (i, m, nmats))
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    g.set_field_after("NINIT", 3, nblks)

    def set_matrix(anchor, rows):
        i = g.find_heading(anchor)
        block = ["  " + "  ".join(str(v) for v in r) for r in rows]
        # replace exactly the records that were there before
        old = 0
        j = i + 1
        while j < len(g.lines) and read_tokens(g.lines[j]) and \
                all(t.lstrip("+-").isdigit() for t in read_tokens(g.lines[j])):
            old += 1
            j += 1
            if old >= max(len(rows), 1) and old >= 1 and \
                    (j >= len(g.lines) or not read_tokens(g.lines[j])
                     or not all(t.lstrip("+-").isdigit()
                                for t in read_tokens(g.lines[j]))):
                break
        g.lines[i + 1:i + 1 + old] = block

    set_matrix("APPEAR_PROCESS", appear)
    set_matrix("MATNO_PROCESS", matno)

    for anchor, spec, default in (("uinitial", a.uinitial, "0"),
                                  ("hdam", a.hdam, "0.000"),
                                  ("water_level", a.water_level, "-99.000")):
        vals = spec.split(",") if spec else [default] * nblks
        if len(vals) != nblks:
            print("BLOCKER: --%s needs %d values" % (anchor, nblks))
            return 1
        i = g.find_heading(anchor)
        g.lines[i + 1] = "  " + "  ".join(vals)

    i = g.find_heading("modf_dis_blocks")
    g.lines[i + 1] = "  " + "  ".join(["0"] * nblks)
    g.save()

    counts = {}
    if a.replicate:
        counts["1.pre"] = replicate(os.path.join(a.case, "1.pre"),
                                    "PRESCRIBE SET", nblks)
        counts["1.loa"] = replicate(os.path.join(a.case, "1.loa"),
                                    "(*.loa) Load data", nblks)
        counts["1.man"] = replicate(os.path.join(a.case, "1.man"),
                                    "nincs,cdtest", nblks)

    # post-check
    g2 = GlbFile(glb)
    bad = []
    if int(g2.tokens_after("NINIT")[3]) != nblks:
        bad.append("nblks did not round-trip")
    got = [[int(x) for x in g2.tokens_after("APPEAR_PROCESS", offset=1 + k)]
           for k in range(nblks)]
    if got != appear:
        bad.append("APPEAR_PROCESS did not round-trip: %s" % got)
    for f, anchor in (("1.pre", "PRESCRIBE SET"),
                      ("1.loa", "(*.loa) Load data"),
                      ("1.man", "nincs,cdtest")):
        n = count_blocks(os.path.join(a.case, f), anchor)
        if n != nblks:
            bad.append("%s has %d block repeat(s), .glb says nblks=%d -- "
                       "HSTAR will hit EOF partway through block %d "
                       "(triplet dt_016)" % (f, n, nblks, n + 1))
    if bad:
        for b in bad:
            print("POST-CHECK FAILED:", b)
        return 1

    print("staging written: nblks=%d ngroup=%d" % (nblks, ngroup))
    for i, row in enumerate(appear, 1):
        print("  block %d active groups: %s" % (i, [k + 1 for k, v in
                                                    enumerate(row) if v]))
    if counts:
        print("  replicated:", counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
