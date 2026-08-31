#!/usr/bin/env python3
"""
write_reinforcement.py -- Capability 14: reinforcement, bond-slip and anchors.

HSTAR embeds reinforcement as `steel` elements (library index 25, 2 nodes,
`b2%name='steel'`, Elements.f90:236) that are LINKED to the surrounding
concrete elements at run time by `link_concrete_and_steel` (Fem.f90:188).  The
link, not the mesh, carries the bond law.

`*.glb` tail records (Global.f90:4536-4560):

    ' nrcsteel'
    nrcsteel
    per link group:
        listgroup_c  listgroup_s  nline_g_sc  diameter_s  e  ft  ikindsc
        err_ctl  mxter
        nel_steel
        <element list>

`ikindsc` selects the bond-slip constitutive law (`ikindks` in the earlier
`ftcrack,coefMpa,ikindks,...` record selects the spring model used by
`steel_spring_parameter`, Fem.f90:1860):

    0  perfect bond (steel nodes share concrete displacement)
    1  linear bond spring
    2  bilinear
    3  CEB-FIP style multilinear
    4  exponential softening
    5  user table

Setting `ikindks=0` while expecting slip is the classic silent failure: the run
converges, the bar force is right, and the slip output in `*.bar` is
identically zero (triplet dt_020).

`ftcrack` (Pa) is the concrete tensile strength used for the smeared-crack
check; `coefMpa` is the DISPLAY scale for stresses, not a unit conversion.

validate -> process -> validate:
  pre : the steel group exists and uses element index 25 (or 20/1 for a plain
        bar); bar diameter, E and ft in SI range; ikindsc known
  post: .glb round-trips with nrcsteel stanzas present

Usage
-----
  python3 write_reinforcement.py --case c1 \
      --link "concrete=1;steel=2;diameter=0.025;E=2.0e11;ft=4.0e8;bond=3"
  python3 write_reinforcement.py --case c1 --ikindks 5 --ftcrack 2.5e6
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile, read_tokens  # noqa: E402

BOND_LAWS = {0: "perfect bond", 1: "linear spring", 2: "bilinear",
             3: "CEB-FIP multilinear", 4: "exponential softening",
             5: "user table"}


def parse_link(spec):
    d = {"concrete": 1, "steel": 2, "diameter": 0.02, "E": 2.0e11,
         "ft": 4.0e8, "bond": 0, "err": 1.0e-4, "mxter": 20, "elements": ""}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in d:
            raise SystemExit("unknown key %r in --link" % k)
        d[k] = v.strip()
    return d


def group_indices(case_dir):
    """(group number -> element library index) from the .glb group stanzas."""
    g = GlbFile(os.path.join(case_dir, "1.glb"))
    ngroup = int(g.tokens_after("NPOIN")[5])
    base = g.find_heading("(3) for each field")
    out = {}
    for gi in range(ngroup):
        toks = read_tokens(g.lines[base + 1 + gi * 4])
        if len(toks) > 2 and toks[2].isdigit():
            out[gi + 1] = int(toks[2])
    return out


def validate(links, gidx, ikindks):
    p = []
    for L in links:
        cg, sg = int(L["concrete"]), int(L["steel"])
        for gid in (cg, sg):
            if gid not in gidx:
                p.append("group %d referenced by --link does not exist" % gid)
        if sg in gidx and gidx[sg] not in (25, 20, 1):
            p.append("steel group %d uses element index %d; reinforcement "
                     "needs index 25 (steel), 20 (beam) or 1 (l2 bar)"
                     % (sg, gidx[sg]))
        d = float(L["diameter"])
        if not (0.002 <= d <= 0.1):
            p.append("bar diameter %g m is outside 2 mm .. 100 mm" % d)
        E = float(L["E"])
        if not (1.0e10 <= E <= 4.0e11):
            p.append("steel E=%g Pa is out of range -- steel is ~2.0e11 Pa "
                     "(GPa/MPa mix-up, triplet dt_010)" % E)
        ft = float(L["ft"])
        if not (1.0e7 <= ft <= 2.0e9):
            p.append("steel ft=%g Pa is out of range" % ft)
        if int(L["bond"]) not in BOND_LAWS:
            p.append("bond=%s unknown; known: %s" % (L["bond"], BOND_LAWS))
        if int(L["bond"]) != 0 and ikindks == 0:
            p.append("a slip law was requested (bond=%s) but ikindks=0 in the "
                     ".glb: steel_spring_parameter() is never called, slip is "
                     "identically zero and the run still converges "
                     "(triplet dt_020)" % L["bond"])
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--link", action="append", default=[])
    ap.add_argument("--ikindks", type=int)
    ap.add_argument("--ftcrack", type=float)
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()

    glb = os.path.join(a.case, "1.glb")
    g = GlbFile(glb)
    cur = g.tokens_after("ftcrack,coefMpa")
    ikindks = int(a.ikindks) if a.ikindks is not None else int(float(cur[2]))

    if a.clear:
        i = g.find_heading("nrcsteel")
        j = g.find_heading("nwcpipe", start=i)
        g.lines[i + 1:j] = ["  0"]
        g.save()
        print("reinforcement cleared (nrcsteel=0)")
        return 0

    links = [parse_link(s) for s in a.link]
    gidx = group_indices(a.case)
    problems = validate(links, gidx, ikindks) if links else []
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    if a.ikindks is not None or a.ftcrack is not None:
        toks = list(cur)
        if a.ftcrack is not None:
            toks[0] = "%.3E" % a.ftcrack
        if a.ikindks is not None:
            toks[2] = str(a.ikindks)
        i = g.find_heading("ftcrack,coefMpa")
        g.lines[i + 1] = "  " + "  ".join(toks)

    if links:
        i = g.find_heading("nrcsteel")
        j = g.find_heading("nwcpipe", start=i)
        body = ["  %d" % len(links)]
        for L in links:
            body.append(" listgroup_c listgroup_s nline_g_sc diameter_s e ft "
                        "ikindsc err_ctl mxter")
            body.append("  %s  %s  1  %.6E  %.6E  %.6E  %s  %.1E  %s"
                        % (L["concrete"], L["steel"], float(L["diameter"]),
                           float(L["E"]), float(L["ft"]), L["bond"],
                           float(L["err"]), L["mxter"]))
            els = [x for x in str(L["elements"]).split(",") if x]
            body.append("  %d" % len(els))
            if els:
                body.append("  " + "  ".join(els))
        g.lines[i + 1:j] = body

    g.save()

    g2 = GlbFile(glb)
    if links and g2.tokens_after("nrcsteel")[0] != str(len(links)):
        print("POST-CHECK FAILED: nrcsteel did not round-trip")
        return 1
    for L in links:
        print("link: concrete group %s <-> steel group %s, d=%s m, bond=%s (%s)"
              % (L["concrete"], L["steel"], L["diameter"], L["bond"],
                 BOND_LAWS[int(L["bond"])]))
    print("ikindks =", ikindks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
