#!/usr/bin/env python3
"""build_staged_construction — element birth/death and per-block material swapping.
(Capability 23.)

Staged construction is HSTAR's most-used non-trivial feature: a dam is built lift by lift, a
tunnel is excavated ring by ring, a foundation is loaded in stages. It is driven entirely by
two integer matrices in `<probn>.glb`, each `nblks` rows x `ngroup` columns:

    APPEAR_PROCESS(igroup, iblks)     1 = the group is ACTIVE in this block
                                      0 = not yet built / already removed (contributes no
                                          stiffness, no mass, no load)
                                     -1 = KILLED IN THIS BLOCK -- its stiffness is removed
                                          AND its internal forces are released onto the
                                          remaining structure. This is how excavation is
                                          modelled; using 0 instead of -1 removes the
                                          element WITHOUT releasing its stress, which
                                          silently under-predicts the excavation heave
                                          (triplet dt_012).
    MATNO_PROCESS(igroup, iblks)      which material record each group uses in this block
                                      (lets fresh concrete mature between blocks)

plus two per-group vectors:
    force_process(1:ngroup)           self-weight release control
    average_appear(1:ngroup)          stress-averaging mode for output
                                      0 = excluded from averaging, 1 = extrapolate,
                                      2 = direct average, -1/-2 = legacy variants
    equvs_process(1:ngroup)           equivalent-linearisation participation

`runblks` in `inp` decides how many of the `nblks` columns are actually executed, so a long
construction sequence can be run incrementally and restarted (`restart=1`).

Usage:
    python3 build_staged_construction.py --case /tmp/mycase --describe
    python3 build_staged_construction.py --case /tmp/mycase --appear 0 1 1 1 --block 1
    python3 build_staged_construction.py --case /tmp/mycase --lift-sequence
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import GlbDoc, HstarInputError, probn_of  # noqa: E402

APPEAR_MEANING = {1: "active", 0: "absent (no stiffness, no stress release)",
                  -1: "killed this block (stiffness removed AND stress released)"}


def _glb(case):
    probn = probn_of(case)
    return GlbDoc(Path(case) / f"{probn}.glb")


def describe(case):
    g = _glb(case)
    out = {"ngroup": g.ngroup, "nblks": g.nblks, "matrices": {}}
    for sec in ("appear_process", "matno_process"):
        rows = [g.get_row(sec, r) for r in range(g.section[sec + "_nrows"])]
        out["matrices"][sec] = rows
    for sec in ("equvs_process", "appear_level", "force_process", "average_appear"):
        out["matrices"][sec] = g.get_row(sec, 0)
    out["appear_legend"] = APPEAR_MEANING
    out["lift_sequence"] = [
        {"block": b + 1,
         "active_groups": [i + 1 for i, v in enumerate(out["matrices"]["appear_process"][b])
                           if v == 1],
         "killed_groups": [i + 1 for i, v in enumerate(out["matrices"]["appear_process"][b])
                           if v == -1]}
        for b in range(len(out["matrices"]["appear_process"]))]
    return out


def set_appear(case, block, values):
    """`block` is 1-based. `values` has one entry per group: 1 / 0 / -1."""
    g = _glb(case)
    for v in values:
        if int(v) not in APPEAR_MEANING:
            raise HstarInputError(
                f"appear value {v} is not one of {sorted(APPEAR_MEANING)}: "
                + "; ".join(f"{k}={d}" for k, d in APPEAR_MEANING.items()))
    g.set_row("appear_process", int(block) - 1, values)
    g.save()
    return describe(case)


def set_matno(case, block, values):
    g = _glb(case)
    for v in values:
        if int(v) < 1:
            raise HstarInputError(f"material record id must be >= 1, got {v}")
    g.set_row("matno_process", int(block) - 1, values)
    g.save()
    return describe(case)


def set_average_appear(case, values):
    g = _glb(case)
    g.set_row("average_appear", 0, values)
    g.save()
    return describe(case)


def build_lift_sequence(case, order=None):
    """Fill APPEAR_PROCESS as a monotone build-up: block k activates groups order[:k].

    `order` defaults to 1..ngroup. Requires nblks >= len(order); each row is cumulative,
    which is what a construction sequence means (a lift stays once placed).
    """
    g = _glb(case)
    order = list(order or range(1, g.ngroup + 1))
    if len(order) > g.nblks:
        raise HstarInputError(
            f"{len(order)} lifts but nblks={g.nblks}. Increase nblks in .glb AND append a "
            f"matching group of records to .pre, .sol and .man -- every one of those files "
            f"carries one record group per load block (triplet dt_007).")
    for b in range(g.nblks):
        row = [1 if (i + 1) in order[:min(b + 1, len(order))] else 0
               for i in range(g.ngroup)]
        g.set_row("appear_process", b, row)
    g.save()
    return describe(case)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--block", type=int, help="1-based load block")
    ap.add_argument("--appear", nargs="+", type=int, help="one value per group")
    ap.add_argument("--matno", nargs="+", type=int)
    ap.add_argument("--average-appear", nargs="+", type=int)
    ap.add_argument("--lift-sequence", action="store_true",
                    help="fill APPEAR_PROCESS as a cumulative build-up")
    ap.add_argument("--order", nargs="+", type=int)
    a = ap.parse_args(argv)
    if a.appear:
        if a.block is None:
            ap.error("--appear needs --block")
        print(json.dumps(set_appear(a.case, a.block, a.appear), indent=2))
    elif a.matno:
        if a.block is None:
            ap.error("--matno needs --block")
        print(json.dumps(set_matno(a.case, a.block, a.matno), indent=2))
    elif a.average_appear:
        print(json.dumps(set_average_appear(a.case, a.average_appear), indent=2))
    elif a.lift_sequence:
        print(json.dumps(build_lift_sequence(a.case, a.order), indent=2))
    else:
        print(json.dumps(describe(a.case), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
