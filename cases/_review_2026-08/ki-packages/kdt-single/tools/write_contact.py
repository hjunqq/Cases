#!/usr/bin/env python3
"""
write_contact.py -- Capability 11: contact, joints and block interfaces.

HSTAR offers three distinct mechanisms; picking the wrong one is the usual
source of "the joint never opens":

  1. GAP / point-to-point contact  (`ngaps` block of `*.glb`, Global.f90:3328)
     Node pairs on facing surfaces, with a normal/tangential penalty pair
     `kgroup0` (closed) / `kgroup1` (open), a tensile strength `ft0`, friction
     `frict0` and cohesion `cohes0`.  Iterated in an outer state loop
     (`miter_bt`, `tor_bt`, `miter_state`), with its own solver
     (`type_solver_ctt`).
  2. GOODMAN joint element (`gaps%goodman=1`, material `GOODMAN`/`JANBU`)
     A zero-thickness element with stress-dependent normal and shear stiffness.
     `elcod_local` in the group stanza sets its notional thickness.
  3. THIN-LAYER element (`gaps%thin_layer=1`, material `CLASSICALEP`
     criteria `MCJOINT`) A thin continuum band with a joint yield surface --
     the choice used for slope-stability runs on a known slip surface.

Block-pair contact (`ngapb`) links two whole element groups through a rigid or
flexible interface and is what `block_stab` and `.gdm` output refer to.

`*.glb` contact header record (14 fields, Global.f90:3330):
    ngaps ngapb ctt_pe miter_bt torbt iblkbt nonsbt xlwsol method_gapi
    miter_state type_solver_ctt restart_ctt damp_ctt istatec

Per gap group:
    ngroupt xlwmd frict_less goodman thin_layer
    listgroupt(1:ngroupt)
    gapi stateix
    ft0 / frict0 / cohes0
    <stiffness records, one per pair-group>

validate -> process -> validate:
  pre : the referenced element groups exist; a `GOODMAN` gap needs a GOODMAN
        material; a `thin_layer` gap needs criteria='MCJOINT'; penalty
        stiffnesses are within ~1e2..1e6 x the adjacent Young's modulus per
        metre (too soft = interpenetration, too stiff = ill-conditioning)
  post: the header round-trips with 14 tokens and `ngaps` stanzas follow

Usage
-----
  python3 write_contact.py --case c1 \
      --gap "groups=2;kind=goodman;kn=1e11;ks=1e10;ft=0;phi=35;c=0"
  python3 write_contact.py --case c1 \
      --gap "groups=3;kind=thin_layer;kn=1e11;ks=1e10;ft=0;phi=25;c=2e4" \
      --solver PARDISO --miter-state 20
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, read_tokens  # noqa: E402


def parse_gap(spec):
    d = {"groups": "", "kind": "gap", "kn": 1e11, "ks": 1e10,
         "ft": 0.0, "phi": 30.0, "c": 0.0, "gapi": 0.0, "stateix": 1,
         "frict_less": 0, "xlwmd": 0.0}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in d:
            raise SystemExit("unknown key %r in --gap" % k)
        d[k] = v.strip()
    d["kind"] = str(d["kind"]).lower()
    if d["kind"] not in ("gap", "goodman", "thin_layer"):
        raise SystemExit("kind must be gap|goodman|thin_layer")
    return d


def mat_models(case_dir):
    """Which constitutive models the .mat declares (for cross-checking)."""
    models = []
    path = os.path.join(case_dir, "1.mat")
    if not os.path.exists(path):
        return models
    for line in open(path, errors="replace"):
        t = read_tokens(line)
        if t and t[0] in ("GOODMAN", "CLASSICALEP", "ELASTIC_ISOTROPIC",
                          "DUNCANCHANG", "CONCRETE", "CAMCLAY"):
            models.append(t[0])
        if t and t[0] == "MCJOINT":
            models.append("MCJOINT")
        if len(t) > 1 and t[0] == "MC":
            models.append("MC")
    return models


def validate(gaps, ngroup, models, e_ref=2.5e10):
    p = []
    for gp in gaps:
        gl = [int(x) for x in str(gp["groups"]).split(",")]
        for gid in gl:
            if gid < 1 or gid > ngroup:
                p.append("gap references element group %d; the .glb declares "
                         "%d group(s)" % (gid, ngroup))
        if gp["kind"] == "goodman" and "GOODMAN" not in models:
            p.append("kind=goodman but the .mat declares no GOODMAN material -- "
                     "HSTAR falls back to the continuum law and the joint never "
                     "opens (triplet dt_018)")
        if gp["kind"] == "thin_layer" and "MCJOINT" not in models:
            p.append("kind=thin_layer expects a CLASSICALEP material with "
                     "criteria='MCJOINT'")
        kn, ks = float(gp["kn"]), float(gp["ks"])
        if not (1e2 * e_ref >= kn >= 1e-2 * e_ref):
            p.append("normal stiffness kn=%.3g Pa/m is far from the reference "
                     "modulus %.3g Pa: too soft lets the surfaces interpenetrate, "
                     "too stiff makes the skyline solver lose precision"
                     % (kn, e_ref))
        if ks > kn:
            p.append("ks=%.3g > kn=%.3g: shear stiffer than normal is "
                     "unphysical for a joint" % (ks, kn))
        if float(gp["phi"]) < 0 or float(gp["phi"]) > 60:
            p.append("friction angle %s deg out of range" % gp["phi"])
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--gap", action="append", default=[])
    ap.add_argument("--solver", default="PROFILE",
                    choices=["PROFILE", "PARDISO"])
    ap.add_argument("--miter-bt", dest="miter_bt", type=int, default=500)
    ap.add_argument("--tor-bt", dest="tor_bt", default="1.0E-05")
    ap.add_argument("--miter-state", dest="miter_state", type=int, default=1)
    ap.add_argument("--damp", type=float, default=0.0)
    ap.add_argument("--clear", action="store_true",
                    help="reset the contact block to ngaps=0")
    a = ap.parse_args()

    glb = os.path.join(a.case, "1.glb")
    g = GlbFile(glb)
    ngroup = int(g.tokens_after("NPOIN")[5])
    ndimn = int(g.tokens_after("NPOIN")[3])
    anchor = "ngaps ngapb ctt_pe"
    i = g.find_heading(anchor)

    if a.clear:
        g.lines[i + 1] = ("  0  0  1  %d  %s  1  0  0  0  %d  %s  0  %.1f  1"
                          % (a.miter_bt, a.tor_bt, a.miter_state,
                             a.solver, a.damp))
        # drop everything the old stanzas added, up to ' nrcsteel'
        end = g.find_heading("nrcsteel", start=i)
        g.lines[i + 2:end] = []
        g.save()
        print("contact block cleared (ngaps=0)")
        return 0

    gaps = [parse_gap(s) for s in a.gap]
    if not gaps:
        print("BLOCKER: give at least one --gap (or --clear)")
        return 1

    problems = validate(gaps, ngroup, mat_models(a.case))
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    header = ("  %d  0  1  %d  %s  1  0  0  0  %d  %s  0  %.1f  1"
              % (len(gaps), a.miter_bt, a.tor_bt, a.miter_state,
                 a.solver, a.damp))
    body = []
    for k, gp in enumerate(gaps, start=1):
        gl = [int(x) for x in str(gp["groups"]).split(",")]
        body.append(" gap group %d" % k)
        body.append("  %d  %s  %d  %d  %d"
                    % (len(gl), gp["xlwmd"], int(gp["frict_less"]),
                       1 if gp["kind"] == "goodman" else 0,
                       1 if gp["kind"] == "thin_layer" else 0))
        body.append("  " + "  ".join(str(x) for x in gl))
        body.append("  %s  %s" % (gp["gapi"], gp["stateix"]))
        body.append("  %.6E" % float(gp["ft"]))
        body.append("  %.6E" % float(gp["phi"]))
        body.append("  %.6E" % float(gp["c"]))
        ncomp = ndimn if ndimn == 2 else 3
        kn, ks = float(gp["kn"]), float(gp["ks"])
        diag0 = [ks] * (ncomp - 1) + [kn]
        diag1 = [v * 1e-6 for v in diag0]
        body.append("  1  " + "  ".join("%.6E" % v for v in diag0 + diag1))

    end = g.find_heading("nrcsteel", start=i)
    g.lines[i + 1:end] = [header] + body
    g.save()

    g2 = GlbFile(glb)
    toks = g2.tokens_after(anchor)
    if len(toks) != 14 or toks[0] != str(len(gaps)):
        print("POST-CHECK FAILED: contact header is %r" % (toks,))
        return 1
    for k, gp in enumerate(gaps, start=1):
        print("gap %d: kind=%s groups=%s kn=%.3g ks=%.3g ft=%s phi=%s c=%s"
              % (k, gp["kind"], gp["groups"], float(gp["kn"]), float(gp["ks"]),
                 gp["ft"], gp["phi"], gp["c"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
