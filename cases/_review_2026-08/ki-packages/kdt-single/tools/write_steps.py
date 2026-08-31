#!/usr/bin/env python3
"""
write_steps.py -- Stage s7: load-step / time-step control (`*.man`).

Record sequence, once per run-block (Fem.f90:2396-2426):

    ' nincs,cdtest,earthquake_curve(1:ndimn)'      heading + control record
    nincs
    per increment set:
        miter ditime noutn noutf nstep inc_step nresta cwater
        toler_force  toler_var(1:mdofn)

NOTE the two HSTAR extensions the GEHOMadrid manual does not document.  The
manual's record is 7 fields (`miter ditime noutn noutf nstep inc_step nresta`).
HSTAR added `cwater` (8th) and `Qstatic` (9th):

    Fem.f90:2405  read(mainunit,*) ... nresta, cwater             ! 8 fields
    Fem.f90:3590  read(mainunit,*) ... nresta, cwater, Qstatic    ! 9 fields
                  (static_U -- the routine every 'Q' run goes through)

A list-directed read whose I/O list is longer than the record simply CONTINUES
ONTO THE NEXT RECORD.  Writing 8 fields therefore makes `static_U` swallow the
tolerance record looking for `Qstatic`, and the run dies with

    forrtl: severe (24): end-of-file during read, unit 9, file <case>/1.man

VERIFIED on this KI's build, 2026-08-26 -- see triplet dt_016.  Always write
9 fields; the 8-field readers discard the surplus token harmlessly.

`ditime` units follow the analysis: SECONDS for dynamics, DAYS for thermal,
creep and construction staging.  The same number means different physics in
each -- this is trap dt_011's twin.

Variable stepping is the point of `nincs > 1`: hydration-heat runs use a short
step for the first days and a long one afterwards, and the total simulated time
is `sum(ditime_i * nstep_i)` across all sets and all blocks.

validate -> process -> validate:
  pre : nstep, miter positive; tolerance count == mdofn+1; ditime positive;
        for `type_problem='F'` warn when ditime looks larger than a sensible
        fraction of the shortest period the mesh can resolve
  post: re-read; record count == nblks*(2 + 2*nincs)

Usage
-----
  python3 write_steps.py --case c1 --inc "miter=5;dtime=1.0;nstep=1"
  python3 write_steps.py --case c1 \
      --inc "miter=30;dtime=0.2;nstep=5;noutf=1" \
      --inc "miter=30;dtime=1.0;nstep=9;noutf=1" --toler 1e-2
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, read_tokens, write_records  # noqa: E402

DEFAULTS = {"miter": 20, "dtime": 1.0, "noutn": 1, "noutf": 1, "nstep": 1,
            "inc_step": 1, "nresta": 1, "cwater": 0, "qstatic": 0}


def parse_inc(spec):
    d = dict(DEFAULTS)
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in d:
            raise SystemExit("unknown key %r in --inc (allowed: %s)"
                             % (k, sorted(d)))
        d[k] = float(v) if k == "dtime" else int(v)
    return d


def mdofn_of(case_dir):
    g = GlbFile(os.path.join(case_dir, "1.glb"))
    i = g.find_heading("MDOFN")
    return int(read_tokens(g.lines[i + 1])[0])


def validate(incs, mdofn, problem):
    p = []
    for k, d in enumerate(incs, start=1):
        if d["nstep"] < 1:
            p.append("increment set %d: nstep=%d must be >= 1" % (k, d["nstep"]))
        if d["miter"] < 1:
            p.append("increment set %d: miter=%d must be >= 1" % (k, d["miter"]))
        if d["dtime"] <= 0:
            p.append("increment set %d: ditime=%g must be > 0"
                     % (k, d["dtime"]))
        if problem == "F" and d["dtime"] > 0.1:
            p.append("increment set %d: ditime=%g s for a dynamic run is "
                     "likely too coarse -- Newmark is stable but the response "
                     "is smeared; use <= T_min/20" % (k, d["dtime"]))
        if d["noutf"] < 1 or d["noutn"] < 1:
            p.append("increment set %d: noutn/noutf < 1 means NOTHING is ever "
                     "written to .flavia.res or .opw" % k)
    if mdofn < 1:
        p.append("mdofn read from .glb is %d" % mdofn)
    return p


def build(incs, mdofn, toler, ndimn, eq_curves):
    r = [" nincs,cdtest,earthquake_curve(1:ndimn)"]
    r.append("  %d  0  %s" % (len(incs),
                              "  ".join(str(c) for c in eq_curves[:ndimn])))
    for d in incs:
        r.append("  %d  %s  %d  %d  %d  %d  %d  %d  %d"
                 % (d["miter"], repr(d["dtime"]), d["noutn"], d["noutf"],
                    d["nstep"], d["inc_step"], d["nresta"], d["cwater"],
                    d["qstatic"]))
        r.append("  %d*%s" % (mdofn + 1, toler))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--inc", action="append", default=[])
    ap.add_argument("--toler", default="1.0e-05")
    ap.add_argument("--nblks", type=int, default=0)
    ap.add_argument("--earthquake-curves", default="0,0,0")
    a = ap.parse_args()

    incs = [parse_inc(s) for s in a.inc] or [dict(DEFAULTS)]
    mdofn = mdofn_of(a.case)
    g = GlbFile(os.path.join(a.case, "1.glb"))
    ndimn = int(g.tokens_after("NPOIN")[3])
    problem = g.tokens_after("TYPE_PROBLEM")[0]
    nblks = a.nblks or int(g.tokens_after("NINIT")[3])

    problems = validate(incs, mdofn, problem)
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    eq = [int(x) for x in a.earthquake_curves.split(",")]
    recs = build(incs, mdofn, a.toler, ndimn, eq) * nblks
    path = os.path.join(a.case, "1.man")
    write_records(path, recs)

    expect = nblks * (2 + 2 * len(incs))
    got = sum(1 for _ in open(path))
    if got != expect:
        print("POST-CHECK FAILED: %d records, expected %d" % (got, expect))
        return 1
    total = sum(d["dtime"] * d["nstep"] for d in incs) * nblks
    print("steps written: %d block(s) x %d increment set(s); total simulated "
          "time = %g (%s)" % (nblks, len(incs), total,
                              "s" if problem == "F" else "days/steps"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
