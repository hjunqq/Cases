#!/usr/bin/env python3
"""
write_materials.py -- Stage s6: constitutive models and parameters (`*.mat`).

File layout (manual §3.7, Material.f90:275-1000):

    ' material property curves'
    <ncurve>                      0 when no property varies with a time curve
    10                            number of comment records that follow
    COMMENT x10                   free text, but exactly this many records
    ' nmats'
    nmats
    per material:
        '     material_serial   <imat>'
        '          <PROPERTY>  <NAME>  <imat>'    MECHANICAL|HEAT|GEOMETRY
        <nphase>                                  MECHANICAL only
        '               SOLID'                    phase heading
        <MODEL> density ratio thickness E nu alfa icreep i1 i2
        <model-specific extra records>

Supported `MECHANICAL/SOLID` models and their extra records, in read order:

  ELASTIC_ISOTROPIC        (none beyond the common record)
  ELASTIC_FRICTIONLESS     (none)
  ELASTIC_SPRING           a b c d l0
  ELASTIC_EP / STEEL_EP    yield / hardening set
  STEEL_SP                 slip law set
  DUNCANCHANG              model c phi K n Rf Nur Kur P0 Pa
                           + (G F Vtf) for EV/CR, or (Kb m dphi) for EB
  GOODMAN  JANBU           K1 n Kzz Rf phi Kzx pa gamaw cohes Ft [+ Kzy in 3-D]
  CLASSICALEP              criteria sigma0 hardening
                           / frict_angle dilan_angle / csigma0 / cfrict cdilan
                           + (ft cft sigmat csigmat) when criteria='MCJOINT'
  CONCRETE                 Ghrib-Tinawi damage set
  CAMCLAY / ClayPZ / SandPZ / SoilPZ   critical-state / generalised plasticity

`HEAT/SOLID`:  a(1:3)  adiabatic_curve  placing_temperature_curve
               -- diffusivity is in **m^2/day** when `.man` `ditime` is in days.

UNITS ARE NOT CONVERTED BY HSTAR.  E and every stress-like parameter must be in
Pa.  Passing 25000 (MPa) instead of 2.5e10 (Pa) gives a converged run with
displacements 1e6 too large -- see triplet dt_010, which this tool pre-empts by
range-checking E, density and nu.

validate -> process -> validate:
  pre : model name is one Material.f90 dispatches on; E, rho, nu, alfa in
        physically sane SI ranges; the extra-record set is complete
  post: re-read the file, count materials and stanza records

Usage
-----
  python3 write_materials.py --case c1 \
      --mat "id=1;model=ELASTIC_ISOTROPIC;rho=2400;E=2.5e10;nu=0.2;alfa=1e-5"
  python3 write_materials.py --case c1 \
      --mat "id=1;model=CLASSICALEP;criteria=MC;rho=2000;E=5e7;nu=0.3;c=20000;phi=30;psi=0"
  python3 write_materials.py --case c1 --mat "id=1;model=HEAT;a=0.0864;curve_adiabatic=3;curve_place=1"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import write_records  # noqa: E402

SOLID_MODELS = ["PLANE_LOWFT", "ELASTIC_ISOTROPIC", "ELASTIC_FRICTIONLESS",
                "ELASTIC_SPRING", "ELASTIC_EP", "STEEL_EP", "STEEL_SP",
                "DUNCANCHANG", "GOODMAN", "CLASSICALEP", "CAMCLAY",
                "CONCRETE", "ClayPZ", "SandPZ", "SoilPZ"]
CRITERIA = ["MC", "DP", "TC", "VM", "MCJOINT"]

RANGES = {  # (lo, hi, unit, what a violation usually means)
    "rho": (500.0, 12000.0, "kg/m^3", "density given in t/m^3 or g/cm^3"),
    "E": (1.0e4, 1.0e12, "Pa", "E given in MPa or GPa instead of Pa"),
    "nu": (-0.999, 0.4999, "-", "nu >= 0.5 makes the bulk modulus infinite"),
    "alfa": (0.0, 1.0e-3, "1/degC", "thermal expansion out of range"),
    "phi": (0.0, 60.0, "deg", "friction angle out of range"),
    "c": (0.0, 1.0e9, "Pa", "cohesion given in kPa/MPa instead of Pa"),
    "a": (1.0e-4, 1.0, "m^2/day", "diffusivity given in m^2/s (86400x too "
                                  "small) -- see triplet dt_011"),
}


def parse_mat(spec):
    d = {}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        d[k.strip()] = v.strip()
    return d


def num(d, key, default=None):
    if key not in d:
        if default is None:
            raise SystemExit("material spec is missing %r" % key)
        return default
    return float(d[key])


def validate(mats):
    p = []
    seen = set()
    for m in mats:
        mid = int(m.get("id", 0))
        if mid in seen:
            p.append("duplicate material id %d" % mid)
        seen.add(mid)
        model = m.get("model", "")
        if model == "HEAT":
            pass
        elif model == "GEOMETRY":
            pass
        elif model not in SOLID_MODELS:
            p.append("unknown model %r (Material.f90 dispatches on: %s)"
                     % (model, SOLID_MODELS))
        if model == "CLASSICALEP" and m.get("criteria") not in CRITERIA:
            p.append("CLASSICALEP needs criteria= one of %s" % CRITERIA)
        if model == "DUNCANCHANG" and m.get("dcmodel", "EB") not in \
                ("EV", "CR", "EB"):
            p.append("DUNCANCHANG model= must be EV, CR or EB")
        for key, (lo, hi, unit, why) in RANGES.items():
            if key in m:
                v = float(m[key])
                if not (lo <= v <= hi):
                    p.append("material %d: %s=%g %s is outside [%g, %g] -- %s"
                             % (mid, key, v, unit, lo, hi, why))
    return p


def stanza(m):
    mid = int(m["id"])
    model = m["model"]
    out = ["     material_serial   %7d" % mid]

    if model == "HEAT":
        out.append("          HEAT           SOLID  %4d" % mid)
        a = num(m, "a")
        out.append("  %.6E  %.6E  %.6E  %d  %d"
                   % (a, num(m, "ay", a), num(m, "az", a),
                      int(m.get("curve_adiabatic", 0)),
                      int(m.get("curve_place", 0))))
        return out

    if model == "GEOMETRY":
        out.append("          GEOMETRY       SOLID  %4d" % mid)
        out.append("  " + "  ".join("%.6E" % float(v)
                                    for v in m.get("props", "0").split(",")))
        return out

    out.append("          MECHANICAL           SOLID  %4d" % mid)
    nphase = int(m.get("nphase", 1))
    out.append("  %d" % nphase)
    out.append("               SOLID")
    icreep = int(m.get("icreep", 0))
    out.append("%-24s%15.3E%15.3E%15.3E%15.3E%15.3E%15.3E  %d  %d  %d"
               % (model, num(m, "rho"), num(m, "ratio", 1.0),
                  num(m, "thickness", 1.0), num(m, "E"), num(m, "nu"),
                  num(m, "alfa", 0.0), icreep,
                  int(m.get("i1", 0)), int(m.get("i2", 0))))

    if model == "ELASTIC_SPRING":
        out.append("  %s" % "  ".join(
            "%.6E" % num(m, k) for k in ("a", "b", "c", "d", "l0")))
    elif model == "DUNCANCHANG":
        dc = m.get("dcmodel", "EB")
        out.append("  %s  %s" % (dc, "  ".join(
            "%.6E" % num(m, k) for k in
            ("c", "phi", "K", "n", "Rf", "Nur", "Kur", "P0", "Pa"))))
        if dc in ("EV", "CR"):
            out.append("  %s" % "  ".join(
                "%.6E" % num(m, k) for k in ("G", "F", "Vtf")))
        else:
            out.append("  %s" % "  ".join(
                "%.6E" % num(m, k) for k in ("Kb", "mm", "dphi")))
    elif model == "GOODMAN":
        out.append("  JANBU")
        keys = ["K1", "n", "Kzz", "Rf", "phi", "Kzx", "pa", "gamaw", "c", "Ft"]
        out.append("  " + "  ".join("%.6E" % num(m, k) for k in keys))
        if int(m.get("ndimn", 2)) == 3:
            out.append("  %.6E" % num(m, "Kzy"))
    elif model == "CLASSICALEP":
        out.append("  %s  %.6E  %.6E"
                   % (m["criteria"], num(m, "c"), num(m, "hardening", 0.0)))
        out.append("  %.6E  %.6E" % (num(m, "phi"), num(m, "psi", 0.0)))
        out.append("  %d" % int(m.get("ccurve", 0)))
        out.append("  %d  %d" % (int(m.get("cfrict", 0)),
                                 int(m.get("cdilan", 0))))
        if m["criteria"] == "MCJOINT":
            out.append("  %.6E  %d  %.6E  %d"
                       % (num(m, "ft", 0.0), int(m.get("cft", 0)),
                          num(m, "sigmat", 0.0), int(m.get("csigmat", 0))))
    elif model == "CONCRETE":
        keys = ["ft", "icr", "Gf", "beta"]
        out.append("  " + "  ".join(str(m.get(k, 0)) for k in keys))
    elif model in ("CAMCLAY", "ClayPZ", "SandPZ", "SoilPZ", "ELASTIC_EP",
                   "STEEL_EP", "STEEL_SP"):
        if "extra" not in m:
            raise SystemExit(
                "model %s needs extra=v1,v2,...  -- the parameter set is "
                "model-specific; read Material.f90 case('%s') for the exact "
                "read order before guessing" % (model, model))
        for rec in m["extra"].split("|"):
            out.append("  " + "  ".join(
                "%.6E" % float(v) for v in rec.split(",")))

    if icreep != 0:
        out.append("  %d  %.6E  %.6E"
                   % (int(m.get("nr", 2)), num(m, "ca", 0.0), num(m, "cb", 1.0)))
        if icreep == 2:
            for key in ("cc", "cd", "ck"):
                out.append("  " + "  ".join(
                    "%.6E" % float(v) for v in m[key].split(",")))
    else:
        out.append("  0  0       1.000E+03")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--mat", action="append", required=True)
    ap.add_argument("--ncurve", type=int, default=0)
    ap.add_argument("--list-models", action="store_true")
    a = ap.parse_args()

    if a.list_models:
        print("\n".join(SOLID_MODELS))
        return 0

    mats = [parse_mat(s) for s in a.mat]
    problems = validate(mats)
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    recs = [" material property curves", "  %d" % a.ncurve, "  10"]
    recs += ["COMMENT"] * 10
    recs += [" nmats", "  %d" % len(mats)]
    for m in sorted(mats, key=lambda x: int(x["id"])):
        recs += stanza(m)

    path = os.path.join(a.case, "1.mat")
    write_records(path, recs)

    with open(path) as fh:
        got = sum(1 for _ in fh)
    if got != len(recs):
        print("POST-CHECK FAILED: %d records on disk, %d built" % (got, len(recs)))
        return 1
    for m in mats:
        print("material %s: %s" % (m["id"], m["model"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
