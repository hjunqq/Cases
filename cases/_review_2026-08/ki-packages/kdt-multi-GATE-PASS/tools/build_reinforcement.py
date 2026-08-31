#!/usr/bin/env python3
"""build_reinforcement — rebar, bond-slip, bolts/anchors, beams and cooling-water pipes.
(Capabilities 19 structural elements, 20 rebar bond, 7 pipe coupling.)

HSTAR embeds discrete reinforcement in a continuum mesh by GEOMETRIC LINKING rather than by
matching nodes: `link_concrete_and_steel` (called from the main program) finds, for every
steel element node, the host solid element containing it and builds the transfer. The same
mechanism links cooling-water pipes (`link_concrete_and_water_pipe`).

SWITCHES
  `nrcsteel`  (last-but-one record of `.glb`)  number of reinforced-concrete steel sets
  `nwcpipe`   (last record of `.glb`)          number of cooling-water pipe sets
  `ikindks`   (on the `ftcrack coefMpa ikindks doubsig ktan1 ktan2 nlocalbeam ndimnrt`
              record)                          BOND-SLIP LAW selector, 0..5.
              0 = perfect bond (no slip). 1-5 are the five slip constitutive laws;
              `cases/train09_rc_bond` uses ikindks=5.
  `nlocalbeam`                                 local beam-direction handling
  `ndimnrt`                                    rotation/normal handling for the steel set

FILES
  `<probn>.bar`   reinforcement segments: end coordinates or node ids, area, material.
  `<probn>.bem`   beam element section/orientation data. A group that declares element
                  index 20/21 (B2/B2C2) with an EMPTY `.bem` has no section to read; the
                  `describe()` check below flags it before the run.

                  SEPARATELY VERIFIED (2026-08-26): `cases/test_beam2d` segfaults under
                  the legacy Linux binary right after `tcurvegravity=1`. Its `.bem` is
                  empty, but its group declares element index 1 (L2 bar), not a beam, so
                  the root cause is NOT the empty `.bem`. That case was converted for the
                  Easy_HSTAR rewrite and its legacy files are not a runnable legacy case --
                  do not use it as a template. See triplet dt_009.

BEAM SECTION properties come from a `GEOMETRY` material record (Material.f90:988):
    Aera  J  Iy  Iz        m2, m4, m4, m4
A 2-D beam uses 3 DOF per node (ux, uy, thz) and a 3-D beam 6 (ux..thz), so `mdofn` must
expose the rotation slots 4-6 in `lmdofn` or the bending stiffness is assembled into
equations that do not exist.

Usage:
    python3 build_reinforcement.py --case /tmp/mycase --describe
    python3 build_reinforcement.py --case /tmp/mycase --bond-law 5
    python3 build_reinforcement.py --case /tmp/mycase --nrcsteel 2 --nwcpipe 0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (ELEMENT_INDEX, GlbDoc, HstarInputError, probn_of,  # noqa: E402
                       read_lines, tokens)

BOND_LAWS = {0: "perfect bond (no relative slip)",
             1: "bond-slip law 1", 2: "bond-slip law 2", 3: "bond-slip law 3",
             4: "bond-slip law 4", 5: "bond-slip law 5 (used by train09_rc_bond)"}
CRACK_FIELDS = ["ftcrack", "coefMpa", "ikindks", "doubsig", "ktan1", "ktan2",
                "nlocalbeam", "ndimnrt"]
BEAM_INDICES = {20, 21}


def _glb(case):
    return GlbDoc(Path(case) / f"{probn_of(case)}.glb")


def _crack_line(g):
    li = g.find("ftcrack")
    return li + 1, tokens(g.lines[li + 1])


def _tail_counter(g, name):
    li = g.find(name)
    return li + 1, tokens(g.lines[li + 1])


def _declared_indices(g):
    keys = {v[0].upper() for v in ELEMENT_INDEX.values()}
    out = []
    for i in range(g.section["_after_average_appear"], len(g.lines)):
        tk = tokens(g.lines[i])
        if tk and tk[0].upper() in keys:
            for t in tk[1:]:
                if t.lstrip("-").isdigit():
                    out.append(int(t))
                    break
        if len(out) >= g.ngroup:
            break
    return out


def describe(case):
    g = _glb(case)
    probn = probn_of(case)
    _, ck = _crack_line(g)
    d = dict(zip(CRACK_FIELDS, ck[:len(CRACK_FIELDS)]))
    _, rc = _tail_counter(g, "nrcsteel")
    _, wp = _tail_counter(g, "nwcpipe")
    bar = Path(case) / f"{probn}.bar"
    bem = Path(case) / f"{probn}.bem"
    idxs = _declared_indices(g)
    problems = []
    if any(i in BEAM_INDICES for i in idxs) and (
            not bem.is_file() or bem.stat().st_size == 0):
        problems.append(
            f"a group declares a beam element index {sorted(set(idxs) & BEAM_INDICES)} but "
            f"{bem.name} is empty -> SIGSEGV, not an error message (triplet dt_009)")
    return {
        "crack_bond_record": d,
        "ikindks": d.get("ikindks"),
        "bond_law": BOND_LAWS.get(int(float(d.get("ikindks", 0))), "unknown"),
        "nrcsteel": rc[0] if rc else None, "nwcpipe": wp[0] if wp else None,
        "bar_bytes": bar.stat().st_size if bar.is_file() else 0,
        "bem_bytes": bem.stat().st_size if bem.is_file() else 0,
        "declared_element_indices": idxs,
        "problems": problems, "ok": not problems,
    }


def set_bond_law(case, ikindks):
    if int(ikindks) not in BOND_LAWS:
        raise HstarInputError(f"ikindks must be one of {sorted(BOND_LAWS)}: "
                              + "; ".join(f"{k}={v}" for k, v in BOND_LAWS.items()))
    g = _glb(case)
    li, tk = _crack_line(g)
    before = tk[CRACK_FIELDS.index("ikindks")]
    tk[CRACK_FIELDS.index("ikindks")] = str(int(ikindks))
    g.lines[li] = "  " + "  ".join(tk)
    g.save()
    return {"ikindks": {"from": before, "to": str(int(ikindks))},
            "meaning": BOND_LAWS[int(ikindks)]}


def set_counts(case, nrcsteel=None, nwcpipe=None):
    g = _glb(case)
    out = {}
    for name, v in (("nrcsteel", nrcsteel), ("nwcpipe", nwcpipe)):
        if v is None:
            continue
        li, tk = _tail_counter(g, name)
        out[name] = {"from": tk[0], "to": str(int(v))}
        tk[0] = str(int(v))
        g.lines[li] = "  " + "  ".join(tk)
        if int(v) > 0:
            probn = probn_of(case)
            aux = Path(case) / (f"{probn}.bar" if name == "nrcsteel" else f"{probn}.tem")
            if not aux.is_file() or aux.stat().st_size == 0:
                out.setdefault("warnings", []).append(
                    f"{name}={int(v)} but {aux.name} is empty; HSTAR will read past the "
                    f"end of the file")
    g.save()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--bond-law", type=int, choices=sorted(BOND_LAWS))
    ap.add_argument("--nrcsteel", type=int)
    ap.add_argument("--nwcpipe", type=int)
    a = ap.parse_args(argv)
    out = {"before": describe(a.case)}
    if a.bond_law is not None:
        out["bond"] = set_bond_law(a.case, a.bond_law)
    if a.nrcsteel is not None or a.nwcpipe is not None:
        out["counts"] = set_counts(a.case, a.nrcsteel, a.nwcpipe)
    if len(out) > 1:
        out["after"] = describe(a.case)
    print(json.dumps(out, indent=2))
    return 0 if out["before"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
