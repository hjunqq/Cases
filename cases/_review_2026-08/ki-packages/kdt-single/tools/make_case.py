#!/usr/bin/env python3
"""
make_case.py -- Stage s1: create a new HSTAR case by CLONING a working template.

RULE 0 of this KI: never author an HSTAR input set from scratch.  `*.glb` alone
has ~40 heading/data record pairs whose presence is positional; a missing
heading shifts every later `read(gunit,*)` by one record and the run either
dies with a Fortran EOF or -- worse -- succeeds on garbage.  This tool copies a
complete, verified-running case directory and hands the copy to the writers.

Templates shipped with this KI (`templates/`):

  static_2d   2-D plane-strain static stress, Q4 continuum, PROFILE solver,
              self-weight only, 1 run-block, 1 material, 1 group.
              Provenance: the `lame_cylinder` case of the HSTAR case library;
              re-run under this KI's Linux build and reproduced bit-for-bit.

validate -> process -> validate:
  pre : template exists and carries the 17 mandatory files
  post: the clone opens as a GlbFile and its first record parses to 15 tokens

Usage
-----
  python3 make_case.py --out /path/to/case1 [--template static_2d] [--overwrite]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, copy_template  # noqa: E402

KI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(KI_DIR, "templates")

# Files HSTAR unconditionally OPENs at start-up (Global.f90:628-673).  A missing
# one is created empty by the OPEN, but a missing *record* inside one is fatal.
MANDATORY = ["1.glb", "1.cor", "1.ele", "1.pre", "1.mat", "1.loa", "1.man",
             "1.opr", "1.sol", "1.tem", "1.ifs", "1.nrt", "1.ftr", "inp"]


def validate_template(tdir):
    problems = []
    if not os.path.isdir(tdir):
        return ["template directory not found: %s" % tdir]
    for f in MANDATORY:
        if not os.path.exists(os.path.join(tdir, f)):
            problems.append("template is missing %s" % f)
    return problems


def validate_case(cdir):
    problems = []
    glb = os.path.join(cdir, "1.glb")
    if not os.path.exists(glb):
        return ["clone has no 1.glb"]
    g = GlbFile(glb)
    toks = g.tokens_after("NPOIN")
    if len(toks) != 15:
        problems.append(
            "first .glb data record has %d tokens, expected 15 "
            "(npoin npoinb nelem ndimn nmats ngroup ntlink outplot kstab "
            "mat_curve meshc rmesh level_set ljdp stab_matde)" % len(toks))
    inp = os.path.join(cdir, "inp")
    with open(inp) as fh:
        recs = [l.rstrip("\n") for l in fh]
    if len(recs) < 5:
        problems.append("inp has %d records, expected >= 5" % len(recs))
    elif recs[3].strip() != "1":
        problems.append("inp record 4 (probn) is %r, expected '1' -- run_hstar.py "
                        "always executes with the case directory as CWD" % recs[3])
    return problems


def make_case(out_dir, template="static_2d", overwrite=False):
    tdir = os.path.join(TEMPLATE_DIR, template)
    problems = validate_template(tdir)
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        raise SystemExit(1)

    copy_template(tdir, out_dir, overwrite=overwrite)

    problems = validate_case(out_dir)
    if problems:
        for p in problems:
            print("POST-CHECK FAILED:", p)
        raise SystemExit(1)
    return out_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", default="static_2d")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for d in sorted(os.listdir(TEMPLATE_DIR)):
            print(d)
        return 0
    d = make_case(a.out, a.template, a.overwrite)
    print("case created:", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
