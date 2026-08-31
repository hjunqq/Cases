#!/usr/bin/env python3
"""
write_reliability.py -- Capability 18: structural reliability (FORM index beta).

Two switches, both on the `inp` control record (`Fem.f90:94`):

    restart  relis  sysrelis  ADINA  Uopt_R  gamamax

  relis    = 1  ELEMENT / point reliability. Dispatched at Fem.f90:1910 into
                `STATIC_U_reli` (block_stab=0) or `static_rigid_reli`
                (block_stab>=1).
  sysrelis > 0  SYSTEM reliability over a set of failure modes
                (Fem.f90:5357, 6207).

The random-variable definition lives in `*.sto` (Fem.f90:4732-4755):

    ' nbeta,nv,mkiter'
    nbeta  nv  mkiter
    ' distribution / mean / cov / correlation'
    ja(1:nv)          distribution type: 1 normal, 2 lognormal, 3 extreme
    ee(1:nv)          mean value of each variable
    ss(1:nv)          standard deviation (or COV, matching how the mean is
                      interpreted in the calling routine)
    cov(i,1:nv)  x nv correlation matrix, one record per row

`nbeta` is the number of limit-state functions, `nv` the number of random
variables, `mkiter` the Hasofer-Lind iteration cap.

Traps this tool guards:
  * a correlation matrix that is not symmetric with a unit diagonal makes the
    Nataf transform produce complex directions; HSTAR does not check it and
    the beta iteration wanders (triplet dt_022);
  * a lognormal variable (ja=2) with a mean <= 0 is undefined;
  * `relis=1` with a purely linear elastic material gives a beta that reflects
    only the load dispersion, which is usually not the question being asked.

validate -> process -> validate:
  pre : matrix square, symmetric, unit diagonal, eigen-positive (checked with
        a Cholesky attempt); distribution codes known; means/sds positive
        where the distribution demands it
  post: `.sto` re-read and shapes match; `inp` record 2 round-trips

Usage
-----
  python3 write_reliability.py --case c1 --mode element \
      --var "name=c;dist=2;mean=2.0e4;sd=4.0e3" \
      --var "name=phi;dist=1;mean=35;sd=3" --corr "1,0.3|0.3,1"
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import write_records  # noqa: E402

DISTS = {1: "normal", 2: "lognormal", 3: "extreme (Gumbel)"}


def parse_var(spec):
    d = {"name": "x", "dist": 1, "mean": 0.0, "sd": 0.0}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in d:
            raise SystemExit("unknown key %r in --var" % k)
        d[k] = v.strip()
    d["dist"] = int(d["dist"])
    d["mean"] = float(d["mean"])
    d["sd"] = float(d["sd"])
    return d


def cholesky_ok(m):
    n = len(m)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                v = m[i][i] - s
                if v <= 0:
                    return False
                L[i][j] = math.sqrt(v)
            else:
                L[i][j] = (m[i][j] - s) / L[j][j]
    return True


def validate(vars_, corr):
    p = []
    n = len(vars_)
    for v in vars_:
        if v["dist"] not in DISTS:
            p.append("variable %r: distribution code %d unknown (1 normal, "
                     "2 lognormal, 3 extreme)" % (v["name"], v["dist"]))
        if v["sd"] < 0:
            p.append("variable %r: standard deviation is negative" % v["name"])
        if v["dist"] == 2 and v["mean"] <= 0:
            p.append("variable %r is lognormal (dist=2) but its mean %g <= 0"
                     % (v["name"], v["mean"]))
        if v["mean"] != 0 and v["sd"] / abs(v["mean"]) > 1.0:
            p.append("variable %r has COV = %.2f > 1; check that `sd` is a "
                     "standard deviation, not a variance"
                     % (v["name"], v["sd"] / abs(v["mean"])))
    if corr is not None:
        if len(corr) != n or any(len(r) != n for r in corr):
            p.append("correlation matrix is %dx%d but there are %d variables"
                     % (len(corr), len(corr[0]) if corr else 0, n))
        else:
            for i in range(n):
                if abs(corr[i][i] - 1.0) > 1e-9:
                    p.append("correlation matrix diagonal [%d][%d] = %g, not 1"
                             % (i, i, corr[i][i]))
                for j in range(n):
                    if abs(corr[i][j] - corr[j][i]) > 1e-9:
                        p.append("correlation matrix is not symmetric at "
                                 "(%d,%d)" % (i, j))
            if not cholesky_ok(corr):
                p.append("correlation matrix is not positive definite; the "
                         "Nataf transform then produces a meaningless search "
                         "direction and beta does not converge (triplet dt_022)")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--mode", choices=["element", "system", "off"],
                    default="element")
    ap.add_argument("--var", action="append", default=[])
    ap.add_argument("--corr", default="", help="rows by |, entries by ,")
    ap.add_argument("--nbeta", type=int, default=1)
    ap.add_argument("--mkiter", type=int, default=50)
    a = ap.parse_args()

    vars_ = [parse_var(s) for s in a.var]
    corr = None
    if a.corr:
        corr = [[float(x) for x in r.split(",")] for r in a.corr.split("|")]
    elif vars_:
        corr = [[1.0 if i == j else 0.0 for j in range(len(vars_))]
                for i in range(len(vars_))]

    if a.mode != "off":
        if not vars_:
            print("BLOCKER: reliability needs at least one --var")
            return 1
        problems = validate(vars_, corr)
        if problems:
            for p in problems:
                print("BLOCKER:", p)
            return 1

    inp = os.path.join(a.case, "inp")
    recs = open(inp).read().split("\n")
    toks = recs[1].split()
    toks[1] = "1" if a.mode == "element" else "0"
    toks[2] = "1" if a.mode == "system" else "0"
    recs[1] = "  " + "  ".join(toks)
    open(inp, "w").write("\n".join(recs))

    if a.mode != "off":
        r = [" nbeta,nv,mkiter", "  %d  %d  %d" % (a.nbeta, len(vars_), a.mkiter),
             " ja(dist) / ee(mean) / ss(sd) / cov(correlation matrix)"]
        r.append("  " + "  ".join(str(v["dist"]) for v in vars_))
        r.append("  " + "  ".join("%.6E" % v["mean"] for v in vars_))
        r.append("  " + "  ".join("%.6E" % v["sd"] for v in vars_))
        for row in corr:
            r.append("  " + "  ".join("%.6f" % x for x in row))
        write_records(os.path.join(a.case, "1.sto"), r)

    back = open(inp).read().split("\n")[1].split()
    if back[1] != ("1" if a.mode == "element" else "0"):
        print("POST-CHECK FAILED: `relis` did not round-trip in inp")
        return 1
    if a.mode == "off":
        print("reliability disabled (relis=0, sysrelis=0)")
    else:
        print("reliability configured: mode=%s, %d random variable(s), "
              "nbeta=%d, mkiter=%d" % (a.mode, len(vars_), a.nbeta, a.mkiter))
        for v in vars_:
            print("  %-10s %-18s mean=%.4g sd=%.4g"
                  % (v["name"], DISTS[v["dist"]], v["mean"], v["sd"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
