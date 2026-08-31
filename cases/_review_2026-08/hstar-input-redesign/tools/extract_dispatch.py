#!/usr/bin/env python3
"""Extract HSTAR's deck-reading structure from the Fortran source.

Why this exists: the authority on how to fill a deck is not documentation and
not an exemplar case — it is the READ statements in the solver. Exemplar decks
are second-hand truth, and this session proved they can be confidently wrong
(a knowledge package asserted `earthquake_curve` drives VIE; Fem.f90:13620 says
otherwise).

Three things get extracted, because they have three different sources:

  layout    which fields, in what order, per reader subroutine  ← READ statements
  dispatch  which reader actually runs, as a function of switches ← call-site guards
  use-site  what a field MEANS                                  ← where the variable
                                                                  is consumed

Only the first is a grammar. The second is why the same record has different
layouts in different runs. The third is why two adjacent slots in one record can
be unrelated physics — and it cannot be seen in the READ statement at all.

Output: dispatcher-map.json, deck-readers.json  (machine-readable on purpose —
these are meant to be handed to other tools and other models).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1
           else "/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR")
OUT = Path(__file__).resolve().parent.parent / "data"

# unit variable → deck file, from the open() calls in Global.f90
UNITS = {
    # Derived from the `open(unit, file=probn//'.ext')` calls, not hand-listed:
    # every unit that is READ at least three times and has a resolvable file
    # name. `unitread` (31 READs) is excluded — its filename comes from a
    # variable, so the extension cannot be resolved statically.
    "mainunit": ".man", "gunit": ".glb", "munit": ".mat", "loadunit": ".loa",
    "back_ctl_unit": ".btl", "nrtunit": ".nrt", "glbunitl": "_l.glb",
    "tunit": ".tem", "solveunit": ".sol", "punit": ".pre", "ifsunit": ".ifs",
    "outpread": ".opr", "stocunit": ".sto", "ftfread": ".ftr",
    "mwaqu_unit": ".aqu", "vcor_unit": ".vcor", "observc_unit": ".obsc",
    "observ_unit": ".obs", "bouunitl": "_l.bou", "outindunit": ".oid",
    "stnunit": ".stn", "gamamaxunit": ".gamax",
    # `inp` is the master control file and the one exception to the
    # probn//ext rule: Fem.f90:92 opens it by the literal name `inp`, and
    # Fem.f90:96 reads `probn` OUT of it — so this file is what tells the
    # solver every other file's basename. All 85 case directories carry one.
    # Modelling it retires two entries from assumptions.json (`restart`,
    # `Uopt_R`) by reading them instead of assuming them.
    # Consumers must not prepend "1" to this name.
    "inpunit": "inp",
}

RE_SUB = re.compile(r"^\s*(?:recursive\s+)?subroutine\s+(\w+)", re.I)
RE_END_SUB = re.compile(r"^\s*end\s+subroutine", re.I)
RE_DO = re.compile(r"^\s*do\b(?!\s*while)", re.I)
RE_END_DO = re.compile(r"^\s*end\s?do\b", re.I)
RE_IF_THEN = re.compile(r"^\s*if\s*\(.*\)\s*then\s*$", re.I)
RE_END_IF = re.compile(r"^\s*end\s?if\b", re.I)
RE_CALL = re.compile(r"^\s*(?:if\s*\((?P<guard>.*?)\)\s*)?call\s+(?P<name>\w+)", re.I)


def load(name: str) -> list[str]:
    return (SRC / name).read_text(encoding="utf-8", errors="replace").splitlines()


def owner_at(lines: list[str], ln: int) -> str:
    for i in range(ln - 1, 0, -1):
        m = RE_SUB.match(lines[i - 1])
        if m:
            return m.group(1)
    return "?"


def enclosing(lines: list[str], ln: int, kind: str, limit: int = 1200) -> list[dict]:
    """Loops or if-blocks that contain line `ln`, innermost first.

    Counts closers on the way up so a sibling block that already ended is not
    mistaken for an enclosing one.
    """
    opener, closer = (RE_DO, RE_END_DO) if kind == "do" else (RE_IF_THEN, RE_END_IF)
    depth, found = 0, []
    for i in range(ln - 1, max(ln - limit, 0), -1):
        s = lines[i - 1]
        if closer.match(s):
            depth += 1
        elif opener.match(s):
            if depth:
                depth -= 1
            else:
                found.append({"line": i, "text": s.strip()[:110]})
    return found


def read_statements(lines: list[str], fname: str) -> list[dict]:
    """Every deck READ, tagged with its reader subroutine and inline guard."""
    out, cur = [], "?"
    for i, raw in enumerate(lines, 1):
        m = RE_SUB.match(raw)
        if m:
            cur = m.group(1)
        for unit, deck in UNITS.items():
            if not re.search(rf"read\s*\(\s*{unit}\s*,", raw, re.I):
                continue
            guard = re.match(rf"\s*if\s*\((?P<g>.*?)\)\s*read\s*\(\s*{unit}", raw, re.I)
            out.append({
                "file": fname, "line": i, "deck": deck, "unit": unit,
                "reader": cur,
                "guard": guard.group("g").strip() if guard else None,
                "text": re.sub(r"\s+", " ", raw.strip())[:200],
            })
    return out


def call_sites(lines: list[str], fname: str, targets: set[str]) -> list[dict]:
    out = []
    for i, raw in enumerate(lines, 1):
        m = RE_CALL.match(raw)
        if not m or m.group("name") not in targets:
            continue
        out.append({
            "file": fname, "line": i, "callee": m.group("name"),
            "inline_guard": (m.group("guard") or "").strip() or None,
            "loops": enclosing(lines, i, "do"),
            "if_blocks": enclosing(lines, i, "if")[:3],
            "text": re.sub(r"\s+", " ", raw.strip())[:160],
        })
    return out


def use_sites(all_lines: dict[str, list[str]], var: str, decl_skip=True) -> list[dict]:
    """Where a read-in variable is CONSUMED. This is the only place a slot's
    meaning lives; the READ statement shows layout, never semantics."""
    hits = []
    pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(var)}(?![A-Za-z0-9_])")
    for fname, lines in all_lines.items():
        for i, raw in enumerate(lines, 1):
            if not pat.search(raw):
                continue
            s = raw.strip()
            low = s.lower()
            if decl_skip and (low.startswith(("integer", "real", "type", "allocate",
                                              "deallocate", "character", "logical"))
                              or "::" in s):
                continue
            if re.search(rf"read\s*\(.*\)\s*.*{re.escape(var)}", s, re.I):
                continue
            hits.append({"file": fname, "line": i,
                         "reader": owner_at(lines, i),
                         "text": re.sub(r"\s+", " ", s)[:130]})
    return hits


def main():
    files = sorted(p.name for p in SRC.glob("*.f90"))
    all_lines = {f: load(f) for f in files}

    reads = [r for f in files for r in read_statements(all_lines[f], f)]

    by_deck: dict[str, dict] = {}
    for r in reads:
        d = by_deck.setdefault(r["deck"], {"deck": r["deck"], "readers": {}})
        d["readers"].setdefault(r["reader"], []).append(r)
    for d in by_deck.values():
        d["reader_count"] = len(d["readers"])
        d["readers"] = {k: v for k, v in
                        sorted(d["readers"].items(), key=lambda kv: -len(kv[1]))}

    readers = {r["reader"] for r in reads}
    calls = [c for f in files for c in call_sites(all_lines[f], f, readers)]

    # Fields whose meaning is known to shift with a switch. These are the ones
    # that have actually caused wrong physics, so they are tracked explicitly
    # rather than inferred.
    drift_vars = ["earthquake_curve", "earthquake_curve_d", "earthquake_curve_v",
                  "earthquake_curve_MIF", "fachv", "cdtest", "inpcord",
                  "nabssgroup", "nabsfgroup", "order_time", "type_ABC",
                  "type_problem", "type_solver"]
    drift = {v: use_sites(all_lines, v)[:40] for v in drift_vars}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "deck-readers.json").write_text(json.dumps(
        {"source": str(SRC), "units": UNITS, "decks": by_deck},
        indent=2, ensure_ascii=False))
    (OUT / "dispatcher-map.json").write_text(json.dumps(
        {"source": str(SRC), "reader_call_sites": calls},
        indent=2, ensure_ascii=False))
    (OUT / "use-sites.json").write_text(json.dumps(
        {"source": str(SRC), "note":
         "Where each read-in variable is consumed. A slot's meaning lives here, "
         "not in the READ statement.", "variables": drift},
        indent=2, ensure_ascii=False))

    print(f"{len(reads)} deck READ statements across {len(by_deck)} files")
    for d in sorted(by_deck.values(), key=lambda x: -x["reader_count"]):
        names = ", ".join(list(d["readers"])[:6])
        print(f"  {d['deck']:<6} {d['reader_count']} readers: {names}")
    print(f"{len(calls)} reader call sites")
    print(f"wrote {OUT}/deck-readers.json, dispatcher-map.json, use-sites.json")


if __name__ == "__main__":
    main()
