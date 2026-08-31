#!/usr/bin/env python3
"""build_mesh_files — write `<probn>.cor` / `<probn>.ele` and reconcile the `.glb` counts
and element-group block. (Capabilities 19 mesh side, plus the geometry half of 1-13.)

`.cor`  one record per node:     ipoin  x  y [z]                 (metres)
`.ele`  one record per element:  ielem  n1 ... n_nnode  igroup   (1-based node ids)

Both are read with list-directed I/O, so only token count and record order matter. What DOES
bite is the count triple: HSTAR allocates from `npoin`/`nelem`/`ngroup` in `.glb` and then
reads exactly that many records. Too few records -> `forrtl: severe (24)` end-of-file. Too
many -> the extras are silently ignored and you are analysing a different structure than you
think you are (triplet dt_004).

Element `index` -> node count is fixed by Elements.f90:128-153 (`kinddefine`); this tool
refuses a connectivity whose node count contradicts the declared element type.

Usage (as a library -- the normal path, because a mesh comes from a mesher, not a CLI):

    from build_mesh_files import write_mesh
    write_mesh("/tmp/mycase",
               coords=[(0,0),(1,0),(1,1),(0,1)],
               elements=[(1,2,3,4)],
               groups=[1],
               element_index=5)            # Q4

CLI:
    python3 build_mesh_files.py --case /tmp/mycase --describe
    python3 build_mesh_files.py --case /tmp/mycase --check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (ELEMENT_INDEX, GlbDoc, HstarInputError, probn_of,  # noqa: E402
                       read_lines, tokens, write_lines)


def read_mesh(case):
    case = Path(case)
    probn = probn_of(case)
    cor, _ = read_lines(case / f"{probn}.cor")
    ele, _ = read_lines(case / f"{probn}.ele")
    coords, elements, groups = [], [], []
    for line in cor:
        tk = tokens(line)
        if len(tk) >= 2:
            coords.append(tuple(float(t) for t in tk[1:]))
    for line in ele:
        tk = tokens(line)
        if len(tk) >= 3:
            elements.append(tuple(int(float(t)) for t in tk[1:-1]))
            groups.append(int(float(tk[-1])))
    return coords, elements, groups


def group_blocks(case):
    """The per-group declaration lines from `.glb`, located after `average_appear`.

    Each group's first line is
      elemname name kname index class nrfields fieldid special sptype nelgroup matno ...
    The element-type KEYWORD is token 0 and the numeric `index` is token 2 in the shipped
    cases; both are reported so a caller can cross-check.
    """
    case = Path(case)
    probn = probn_of(case)
    g = GlbDoc(case / f"{probn}.glb")
    out, seen = [], 0
    keys = {v[0].upper() for v in ELEMENT_INDEX.values()}
    for i in range(g.section["_after_average_appear"], len(g.lines)):
        tk = tokens(g.lines[i])
        if tk and tk[0].upper() in keys:
            idx = None
            for t in tk[1:]:
                if t.lstrip("-").isdigit():
                    idx = int(t)
                    break
            out.append({"line": i, "elem_keyword": tk[0], "declared_index": idx,
                        "tokens": tk})
            seen += 1
            if seen >= g.ngroup:
                break
    return g, out


# Token layout of a `.glb` group declaration line, from the header comment in every
# shipped case:
#   NAME KNAME INDEX CLASS NRFIELDS FIELDID SPECIAL SPTYPE NELGROUP MATNO TYPE_ALGO
#   TYPE_STIFF TYPE_ECOINT ilayer elcod_local group_inf uplift_ic liquj
GROUP_FIELDS = ["name", "kname", "index", "class", "nrfields", "fieldid", "special",
                "sptype", "nelgroup", "matno", "type_algo", "type_stiff", "type_ecoint",
                "ilayer", "elcod_local", "group_inf", "uplift_ic", "liquj"]


def set_group_field(case, group, field, value):
    """Edit one field of the `group`-th (1-based) .glb group declaration line."""
    if field not in GROUP_FIELDS:
        raise HstarInputError(f"unknown group field {field!r}; valid: {GROUP_FIELDS}")
    g, blocks = group_blocks(case)
    if not 1 <= group <= len(blocks):
        raise HstarInputError(f"group {group} out of range 1..{len(blocks)}")
    b = blocks[group - 1]
    tk = tokens(g.lines[b["line"]])
    pos = GROUP_FIELDS.index(field)
    if pos >= len(tk):
        raise HstarInputError(
            f"this group line has {len(tk)} tokens; {field!r} sits at position {pos + 1}")
    before = tk[pos]
    tk[pos] = str(value)
    g.lines[b["line"]] = "  " + "  ".join(tk)
    g.save()
    return {"group": group, "field": field, "from": before, "to": str(value),
            "line": b["line"] + 1}


def write_mesh(case, coords, elements, groups=None, element_index=None,
               update_glb=True):
    """Write .cor/.ele and (optionally) sync npoin/nelem/npoinb in .glb.

    validate -> process -> validate.
    """
    case = Path(case)
    probn = probn_of(case)
    g = GlbDoc(case / f"{probn}.glb")
    ndimn = int(g.get("ndimn"))
    npoin, nelem = len(coords), len(elements)

    # -- validate inputs
    if npoin == 0 or nelem == 0:
        raise HstarInputError("empty mesh")
    for k, c in enumerate(coords):
        if len(c) != ndimn:
            raise HstarInputError(
                f"node {k + 1} has {len(c)} coordinates but .glb declares ndimn={ndimn}. "
                f"Change ndimn first (it drives every element library lookup).")
    nn = len(elements[0])
    if element_index is not None:
        want = ELEMENT_INDEX.get(int(element_index))
        if want is None:
            raise HstarInputError(
                f"element index {element_index} is not in the HSTAR element library. "
                f"Known: " + ", ".join(f"{k}={v[0]}" for k, v in ELEMENT_INDEX.items()))
        if want[1] != nn:
            raise HstarInputError(
                f"element index {element_index} ({want[0]}) has {want[1]} nodes, but the "
                f"connectivity supplies {nn}")
        if want[2] != ndimn and want[2] != 1:
            raise HstarInputError(
                f"element {want[0]} is {want[2]}-D but .glb declares ndimn={ndimn}")
    for k, e in enumerate(elements):
        if len(e) != nn:
            raise HstarInputError(
                f"element {k + 1} has {len(e)} nodes, element 1 has {nn}. HSTAR reads a "
                f"fixed node count per group -- split mixed element types into separate "
                f"groups.")
        for nd in e:
            if not 1 <= nd <= npoin:
                raise HstarInputError(
                    f"element {k + 1} references node {nd}, outside 1..{npoin}")
    groups = list(groups) if groups is not None else [1] * nelem
    if len(groups) != nelem:
        raise HstarInputError("groups list must have one entry per element")
    if max(groups) > g.ngroup:
        raise HstarInputError(
            f"element group id {max(groups)} exceeds .glb ngroup={g.ngroup}")

    # -- process
    _, eol = read_lines(case / f"{probn}.cor")
    write_lines(case / f"{probn}.cor",
                [f"{i + 1:>8d}" + "".join(f"{v:>22.10f}" for v in c)
                 for i, c in enumerate(coords)], eol)
    write_lines(case / f"{probn}.ele",
                [f"{i + 1:>10d}" + "".join(f"{n:>10d}" for n in e) + f"{grp:>10d}"
                 for i, (e, grp) in enumerate(zip(elements, groups))], eol)
    if update_glb:
        g.set("npoin", npoin).set("nelem", nelem)
        if int(g.get("npoinb")) != npoin:
            g.set("npoinb", npoin)
        g.save()
        # nelgroup on every group declaration line must match the .ele group column,
        # otherwise HSTAR walks off the end of group(igroup)%list
        counts = {}
        for grp in groups:
            counts[grp] = counts.get(grp, 0) + 1
        for gid, n in sorted(counts.items()):
            set_group_field(case, gid, "nelgroup", n)

    # -- validate the result
    c2, e2, g2 = read_mesh(case)
    if len(c2) != npoin or len(e2) != nelem:
        raise HstarInputError("post-write readback mismatch")
    counts = {}
    for grp in g2:
        counts[grp] = counts.get(grp, 0) + 1
    return {"npoin": npoin, "nelem": nelem, "ndimn": ndimn, "nodes_per_element": nn,
            "elements_per_group": counts,
            "note": "nelgroup in each .glb group block must match elements_per_group; "
                    "use --check to verify"}


def check(case):
    case = Path(case)
    coords, elements, groups = read_mesh(case)
    g, blocks = group_blocks(case)
    problems = []
    if len(coords) != int(g.get("npoin")):
        problems.append(f".cor {len(coords)} records vs npoin={g.get('npoin')}")
    if len(elements) != int(g.get("nelem")):
        problems.append(f".ele {len(elements)} records vs nelem={g.get('nelem')}")
    counts = {}
    for grp in groups:
        counts[grp] = counts.get(grp, 0) + 1
    for k, b in enumerate(blocks, start=1):
        want = ELEMENT_INDEX.get(b["declared_index"] or -1)
        nel_declared = None
        for t in b["tokens"]:
            if t.lstrip("-").isdigit() and int(t) == counts.get(k, -999):
                nel_declared = int(t)
        if want and elements:
            in_group = [e for e, grp in zip(elements, groups) if grp == k]
            if in_group and len(in_group[0]) != want[1]:
                problems.append(
                    f"group {k} declares {want[0]} ({want[1]} nodes) but its elements have "
                    f"{len(in_group[0])}")
        if nel_declared is None and k in counts:
            problems.append(
                f"group {k}: could not find nelgroup={counts[k]} on its .glb declaration "
                f"line -- check it by hand (line {b['line'] + 1})")
    return {"npoin": len(coords), "nelem": len(elements),
            "elements_per_group": counts,
            "groups": [{"keyword": b["elem_keyword"], "index": b["declared_index"]}
                       for b in blocks],
            "problems": problems, "ok": not problems}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.describe or not a.check:
        coords, elements, groups = read_mesh(a.case)
        xs = list(zip(*coords)) if coords else []
        print(json.dumps({
            "npoin": len(coords), "nelem": len(elements),
            "bbox": [[min(c), max(c)] for c in xs],
            "nodes_per_element": len(elements[0]) if elements else 0,
            "group_ids": sorted(set(groups))}, indent=2))
    if a.check:
        r = check(a.case)
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
