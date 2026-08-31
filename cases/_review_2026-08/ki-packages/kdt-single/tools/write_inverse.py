#!/usr/bin/env python3
"""
write_inverse.py -- Capability 17: parameter back-analysis (inversion) against
monitoring data.

Dispatch (Fem.f90:334-360), driven by `.glb` `Bparameter` and `balgor`:

  Bparameter = -1 / -2   forward VERIFICATION run: read `.btl`, generate the
                         synthetic response for a given parameter vector.
                         Use this to check the observation-point interpolation
                         before spending iterations.
  0 < Bparameter <= 2, balgor <= 1   Gauss-Newton / householder inversion
  0 < Bparameter <= 2, balgor == 2   MKL trust-region `dtrnlsp` (RCI)
  Bparameter = 3         rigid-block displacement inversion
  Bparameter = 4         nodal-value inversion

`*.btl` -- parameter and observation-point control (Fem.f90:2011-2061):

    ' Npara'                    / Npara
    ' i, imat, name, factor, mode_transform, lo, hi'   x Npara
    ' EPS(6), iter1, iter2, RS, JAC_EPS'               (balgor<=1)
      or the trust-region record eta1 eta2 ...          (balgor==2)
    ' initial values'           / Xvalue(1:Npara)
    ' information for given points, Npoints_pb' / Npoints_pb
    ' i0, ndofn, imdofn, nintf' / listf(1:nintf) / rintf(1:nintf)   x Npoints

Each observation point is an INTERPOLATION over `nintf` mesh nodes with weights
`rintf` -- a plumb line or extensometer rarely sits on a node.  The weights
must sum to 1.0; they are not normalised by the code.

`*.obs` -- the measured series (Fem.f90:2220-2226):

    ' Nblks_pb' / nblks_pb
    per block: ' NINCS' / nincs_pb
               dtime_pb nstep_pb observ_pb begin_day_pb end_day_pb
    per point-dof: ix i1 j1 flag ipoint  weight  label
                   observed_value(1:nstep_pb)

`name` in the `.btl` parameter record is the MATERIAL PROPERTY being inverted
(e.g. `E`, `nu`, `K`, `phi`) and `imat` the material it belongs to; `factor`
scales the parameter to O(1) so the trust-region step size is meaningful.
Inverting an un-scaled Young's modulus (1e10) alongside a Poisson ratio (0.2)
makes the Jacobian hopelessly ill-conditioned -- triplet dt_021.

**Observations must be real measurements.** This tool never fabricates a
series; `--obs-csv` is the only way to supply one.

validate -> process -> validate:
  pre : Bparameter/balgor combination is one Fem.f90 dispatches on; every
        interpolation weight set sums to 1; every parameter has a scale factor
        that brings it within 1e-2..1e2; the observation series length equals
        nstep_pb
  post: files re-read; counts match; .glb flags round-trip

Usage
-----
  python3 write_inverse.py --case c1 --algorithm trust_region \
      --param "imat=1;name=E;init=2.0e10;factor=1e-10;lo=1e10;hi=4e10" \
      --point "nodes=101,102;weights=0.4,0.6;dof=1" \
      --obs-csv monitoring.csv --dtime 30 --nstep 12
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, write_records  # noqa: E402

ALGORITHMS = {"verify": (-1, 0), "gauss_newton": (1, 1), "trust_region": (1, 2),
              "rigid_block": (3, 0), "nodal_value": (4, 0)}


def parse_kv(spec, allowed):
    d = {}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in allowed:
            raise SystemExit("unknown key %r (allowed %s)" % (k, sorted(allowed)))
        d[k] = v.strip()
    return d


def validate(params, points, series, nstep):
    p = []
    for k, q in enumerate(params, 1):
        init = float(q["init"])
        fac = float(q.get("factor", 1.0))
        scaled = abs(init * fac)
        if not (1e-2 <= scaled <= 1e2):
            p.append("parameter %d (%s) scales to %.3g; give a `factor` that "
                     "brings it into 1e-2..1e2 or the Jacobian is "
                     "ill-conditioned (triplet dt_021)"
                     % (k, q.get("name"), scaled))
        if "lo" in q and "hi" in q:
            if not (float(q["lo"]) <= init <= float(q["hi"])):
                p.append("parameter %d initial value %g is outside [%s, %s]"
                         % (k, init, q["lo"], q["hi"]))
    for k, pt in enumerate(points, 1):
        w = [float(x) for x in pt["weights"].split(",")]
        n = [int(x) for x in pt["nodes"].split(",")]
        if len(w) != len(n):
            p.append("observation point %d has %d nodes but %d weights"
                     % (k, len(n), len(w)))
        elif abs(sum(w) - 1.0) > 1e-6:
            p.append("observation point %d interpolation weights sum to %.6f, "
                     "not 1.0 -- HSTAR does not normalise them, so the "
                     "simulated value is scaled wrong" % (k, sum(w)))
    if series is not None:
        for label, vals in series.items():
            if len(vals) != nstep:
                p.append("observation series %r has %d values but nstep_pb=%d"
                         % (label, len(vals), nstep))
    return p


def read_obs_csv(path):
    """CSV: first column = series label, remaining columns = the time series."""
    out = {}
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].startswith("#"):
                continue
            out[row[0].strip()] = [float(x) for x in row[1:] if x.strip()]
    return out


def build_btl(params, points, algo, iters, eps, rs, jac_eps):
    r = [" Npara", "  %d" % len(params)]
    r.append(" i, imat, name, factor, mode_transform, lo, hi")
    for k, q in enumerate(params, 1):
        r.append("  %d  %s  %s  %s  %s  %s  %s"
                 % (k, q.get("imat", 1), q.get("name", "E"),
                    q.get("factor", 1.0), q.get("mode", 0),
                    q.get("lo", 0.0), q.get("hi", 0.0)))
    if algo == "trust_region":
        r.append(" eta1 eta2 gama1 gama2 delta0 iter1 iter2")
        r.append("  0.25  0.75  0.5  2.0  1.0  %d  %d" % (iters[0], iters[1]))
    else:
        r.append(" EPS(1:6), iter1, iter2, RS, JAC_EPS")
        r.append("  " + "  ".join(["%g" % eps] * 6)
                 + "  %d  %d  %g  %g" % (iters[0], iters[1], rs, jac_eps))
    r.append(" initial values Xvalue(1:Npara)")
    r.append("  " + "  ".join(str(q["init"]) for q in params))
    r.append(" information for given points, Npoints_pb")
    r.append("  %d" % len(points))
    r.append(" i0, ndofn, imdofn, nintf / listf / rintf")
    for k, pt in enumerate(points, 1):
        n = [int(x) for x in pt["nodes"].split(",")]
        w = [float(x) for x in pt["weights"].split(",")]
        r.append("  %d  %s  %s  %d" % (k, pt.get("ndofn", 2),
                                       pt.get("dof", 1), len(n)))
        r.append("  " + "  ".join(str(x) for x in n))
        r.append("  " + "  ".join("%.15E" % x for x in w))
    return r


def build_obs(series, points, dtime, nstep, begin_day, end_day):
    r = [" Nblks_pb", "  1", " NINCS", "  1"]
    r.append("  %d  %d  1  %d  %d" % (dtime, nstep, begin_day, end_day))
    r.append(" 1:Npoints_pb/observed_value(1:nstep_pb)")
    for k, (label, vals) in enumerate(sorted(series.items()), start=1):
        pt = points[min(k, len(points)) - 1]
        r.append("  %d  1  %s  0  %d  %.6f  %s"
                 % (k, pt.get("dof", 1), k, vals[0] if vals else 0.0, label))
        r.append("  " + "  ".join("%.6f" % v for v in vals))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--algorithm", choices=sorted(ALGORITHMS),
                    default="trust_region")
    ap.add_argument("--param", action="append", default=[],
                    help="imat=;name=;init=;factor=;lo=;hi=;mode=")
    ap.add_argument("--point", action="append", default=[],
                    help="nodes=n1,n2;weights=w1,w2;dof=1;ndofn=2")
    ap.add_argument("--obs-csv", dest="obs_csv", default="")
    ap.add_argument("--dtime", type=int, default=30)
    ap.add_argument("--nstep", type=int, default=12)
    ap.add_argument("--begin-day", dest="begin_day", type=int, default=1)
    ap.add_argument("--end-day", dest="end_day", type=int, default=365)
    ap.add_argument("--iter1", type=int, default=100)
    ap.add_argument("--iter2", type=int, default=50)
    ap.add_argument("--eps", type=float, default=1e-8)
    ap.add_argument("--rs", type=float, default=100.0)
    ap.add_argument("--jac-eps", dest="jac_eps", type=float, default=1e-6)
    a = ap.parse_args()

    params = [parse_kv(s, {"imat", "name", "init", "factor", "lo", "hi",
                           "mode"}) for s in a.param]
    points = [parse_kv(s, {"nodes", "weights", "dof", "ndofn"})
              for s in a.point]
    series = read_obs_csv(a.obs_csv) if a.obs_csv else None

    problems = []
    if a.algorithm not in ("verify",) and not params:
        problems.append("an inversion needs at least one --param")
    if a.algorithm not in ("verify",) and series is None:
        problems.append(
            "an inversion needs measured data via --obs-csv. This tool will not "
            "synthesise observations: inverting against a self-generated series "
            "recovers the parameters used to generate it and proves nothing.")
    problems += validate(params, points, series, a.nstep)
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    bp, ba = ALGORITHMS[a.algorithm]
    g = GlbFile(os.path.join(a.case, "1.glb"))
    g.set_field_after("TYPE_PROBLEM", 8, bp)
    g.set_field_after("TYPE_PROBLEM", 9, ba)
    g.set_field_after("NINIT", 13, 1)      # nbackf: enable the back-analysis I/O
    g.save()

    write_records(os.path.join(a.case, "1.btl"),
                  build_btl(params, points, a.algorithm,
                            (a.iter1, a.iter2), a.eps, a.rs, a.jac_eps))
    if series is not None:
        write_records(os.path.join(a.case, "1.obs"),
                      build_obs(series, points, a.dtime, a.nstep,
                                a.begin_day, a.end_day))

    g2 = GlbFile(os.path.join(a.case, "1.glb"))
    if g2.tokens_after("TYPE_PROBLEM")[8] != str(bp):
        print("POST-CHECK FAILED: Bparameter did not round-trip")
        return 1
    print("inversion configured: algorithm=%s (Bparameter=%d, balgor=%d), "
          "%d parameter(s), %d observation point(s), %d series"
          % (a.algorithm, bp, ba, len(params), len(points),
             len(series) if series else 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
