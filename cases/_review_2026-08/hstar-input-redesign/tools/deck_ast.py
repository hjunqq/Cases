#!/usr/bin/env python3
"""Build an AST of HSTAR's deck-reading logic from the Fortran source.

Everything before this extracted flat lists — READ statements here, call sites
there — and a flat list cannot answer the question that actually matters:
*given these switches, what does the solver read, in what order?* That is a
tree, and this builds it.

Node kinds:
    SEQ      ordered children
    READ     one record: unit, variables, arity expression
    IF       guard + then/else subtrees
    SELECT   select-case with per-case subtrees
    LOOP     do-construct, with its bounds expression
    CALL     call into another reader; inlined when the callee reads a deck

Everything not on a path to a deck READ is pruned, which is what keeps a
76k-line solver's control flow down to a readable tree.

Acceptance is not "it parsed". The tree must reproduce facts established
independently by other means — see --verify. A grammar extractor that cannot
re-derive what we already know by hand is not evidence about the parts we
don't.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC = Path("/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR")

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

# ── lexing ────────────────────────────────────────────────────────────────

def logical_lines(path: Path) -> list[tuple[int, str]]:
    """(line_no, text) with comments stripped and `&` continuations joined.

    `!` only starts a comment outside quotes — deck labels are quoted strings
    that routinely contain `!`, and treating those as comments truncates real
    statements.
    """
    out, buf, start = [], "", None
    for n, raw in enumerate(path.read_text(encoding="utf-8", errors="replace")
                            .splitlines(), 1):
        s, q, cut = raw, None, None
        for i, ch in enumerate(s):
            if q:
                if ch == q:
                    q = None
            elif ch in "'\"":
                q = ch
            elif ch == "!":
                cut = i
                break
        if cut is not None:
            s = s[:cut]
        s = s.rstrip()
        if not s.strip():
            continue
        if start is None:
            start = n
        if s.rstrip().endswith("&"):
            buf += s.rstrip()[:-1]
            continue
        # Fortran allows several statements on one line separated by `;`
        # (179 such lines here, e.g. `freez=0.0 ; nbounods=0`). Treating the
        # line as one statement keeps only the first: every later assignment
        # loses its node, and a variable that is only ever initialised there
        # becomes permanently unknown. Split at top level; a `;` inside quotes
        # is data.
        for piece in split_semicolons((buf + s).strip()):
            out.append((start, piece))
        buf, start = "", None
    if buf:
        out.append((start or 0, buf.strip()))
    return out


LBL = r"^\s*(?:\d+\s+)?"   # optional numeric statement label
def split_semicolons(stmt: str) -> list[str]:
    """Split a line at top-level `;`, leaving quoted text alone."""
    if ";" not in stmt:
        return [stmt]
    out, cur, q = [], "", None
    for ch in stmt:
        if q:
            cur += ch
            if ch == q:
                q = None
            continue
        if ch in "'\"":
            q = ch
            cur += ch
        elif ch == ";":
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out or [stmt]


RE_SUB = re.compile(LBL + r"(?:recursive\s+)?(?:subroutine|program)\s+(\w+)", re.I)
RE_END_SUB = re.compile(LBL + r"end\s*(?:subroutine|program)\b", re.I)
RE_IF_THEN = re.compile(LBL + r"(?:\w+\s*:\s*)?if\s*\((?P<g>.*)\)\s*then\s*$", re.I)
RE_ELSE_IF = re.compile(LBL + r"else\s*if\s*\((?P<g>.*)\)\s*then\s*$", re.I)
RE_ELSE = re.compile(LBL + r"else\s*$", re.I)
RE_END_IF = re.compile(LBL + r"end\s*if\b", re.I)
RE_IF_HEAD = re.compile(LBL + r"if\s*\(", re.I)


def split_if_one(text: str):
    """Single-line `if (guard) stmt` → (guard, stmt), or None.

    A regex cannot do this: `if(vdimn/=abs(water))cycle` has parentheses inside
    the guard, and a non-greedy `.*?` stops at the FIRST `)`, yielding the guard
    `vdimn/=abs(water` and the statement `)cycle`. Every single-line `if` whose
    condition contains a call or a nested group was being mis-parsed — the
    statement was lost, so its READ / CALL / CYCLE never entered the tree.
    Scan to the matching paren instead.
    """
    m = RE_IF_HEAD.match(text)
    if not m:
        return None
    i, depth = m.end() - 1, 0
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    else:
        return None
    guard = text[m.end():i].strip()
    stmt = text[i + 1:].strip()
    if not stmt or re.match(r"^then\b", stmt, re.I):
        return None
    return guard, stmt
RE_DO_LBL = re.compile(LBL + r"do\s+(?P<lbl>\d+)\s+(?P<b>\w+\s*=.*)$", re.I)
RE_LEAD_LBL = re.compile(r"^\s*(?P<lbl>\d+)\b")
RE_DO = re.compile(LBL + r"(?:\w+\s*:\s*)?do\b\s*(?P<b>.*)$", re.I)
RE_END_DO = re.compile(LBL + r"end\s*do\b", re.I)
RE_SELECT = re.compile(LBL + r"(?:\w+\s*:\s*)?select\s+case\s*\((?P<e>.*)\)\s*$", re.I)
RE_CASE = re.compile(LBL + r"case\s*(?P<v>\(.*\)|default)\s*$", re.I)
RE_END_SELECT = re.compile(LBL + r"end\s*select\b", re.I)
RE_ALLOC = re.compile(LBL + r"allocate\s*\((?P<args>.*)\)\s*$", re.I)
RE_EXIT = re.compile(LBL + r"exit\s*(?:\w+)?\s*$", re.I)
RE_CYCLE = re.compile(LBL + r"cycle\s*(?:\w+)?\s*$", re.I)
RE_GOTO = re.compile(LBL + r"go\s*to\s+(?P<lbl>\d+)\s*$", re.I)
RE_GOTO_COMPUTED = re.compile(LBL + r"go\s*to\s*\(", re.I)
RE_RETURN = re.compile(LBL + r"return\s*$", re.I)
RE_CALL = re.compile(LBL + r"call\s+(?P<n>\w+)", re.I)
RE_ASSIGN = re.compile(LBL + r"(?P<lhs>[A-Za-z_]\w*(?:\([^()]*\))?(?:%\w+(?:\([^()]*\))?)*)\s*=\s*(?P<rhs>[^=<>].*)$")
RE_READ = re.compile(LBL + r"read\s*\(\s*(?P<u>\w+)\s*,(?P<rest>.*)$", re.I)


def split_args(s: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return [x for x in out if x]


def parse_read(text: str, line: int, fname: str = "?") -> dict | None:
    m = RE_READ.match(text)
    if not m:
        return None
    unit = m.group("u").lower()
    if unit not in UNITS:
        return None
    rest = m.group("rest")
    depth, i = 1, 0
    while i < len(rest) and depth:
        if rest[i] == "(":
            depth += 1
        elif rest[i] == ")":
            depth -= 1
        i += 1
    vars_ = split_args(rest[i:])
    return {"kind": "READ", "line": line, "file": fname, "unit": unit,
            "deck": UNITS[unit], "vars": vars_, "arity": arity_of(vars_)}


def arity_of(vars_: list[str]) -> str:
    """How many values this READ consumes: an integer, or a symbolic sum."""
    terms, const = [], 0
    for v in vars_:
        # a(1:n) and a(1:n,j) alike consume n — stop at the comma, or a
        # 2-D section yields the uninterpretable arity "n,j".
        m = re.search(r"\(\s*1\s*:\s*([^,)]+)", v)              # a(1:n) / a(1:n,j)
        m2 = re.match(r"^\(.*,\s*\w+\s*=\s*[^,]+,\s*([^)]+)\)$", v)  # (x(i),i=1,n)
        if m:
            terms.append(m.group(1).strip())
        elif m2:
            terms.append(m2.group(1).strip())
        else:
            const += 1
    if const:
        terms.insert(0, str(const))
    return " + ".join(terms) if terms else "0"


# ── block parsing ─────────────────────────────────────────────────────────

def parse_subroutine(lines: list[tuple[int, str]], i: int, fname: str = "?",
                     stop_label: str | None = None) -> tuple[dict, int]:
    """Parse a statement sequence into a SEQ node. Returns (node, next_index)."""
    body = []
    while i < len(lines):
        ln, text = lines[i]
        if RE_END_SUB.match(text) or RE_SUB.match(text):
            break
        # Old-style labeled DO terminates at the statement bearing its label,
        # which is often `N continue` but may be any statement (`90 SIGU(I)=…`).
        # 202 such loops exist across 8 files; treating them as unterminated
        # was the single largest source of tree corruption.
        if stop_label is not None:
            m_lbl = RE_LEAD_LBL.match(text)
            if m_lbl and m_lbl.group("lbl") == stop_label:
                # Do NOT consume: nested labeled DOs may share one terminator
                # (`DO 311 I=1,4` / `DO 311 J=1,4` / `311 DEP(I,J)=0.0`), so
                # every level with this label must see it and unwind. The
                # enclosing sequence then skips the statement itself.
                break
        if RE_END_IF.match(text) or RE_ELSE.match(text) or RE_ELSE_IF.match(text) \
           or RE_END_DO.match(text) or RE_CASE.match(text) or RE_END_SELECT.match(text):
            break

        if (mlbl := RE_LEAD_LBL.match(text)) and stop_label != mlbl.group("lbl"):
            # A goto target. Emitted as a marker before the statement itself,
            # which is then parsed normally.
            body.append({"kind": "LABEL", "line": ln, "label": mlbl.group("lbl")})

        if (m := RE_IF_THEN.match(text)):
            node = {"kind": "IF", "line": ln, "guard": m.group("g").strip(),
                    "branches": []}
            i += 1
            then, i = parse_subroutine(lines, i, fname)
            node["branches"].append({"guard": m.group("g").strip(), "body": then})
            while i < len(lines):
                _, t2 = lines[i]
                if (m2 := RE_ELSE_IF.match(t2)):
                    i += 1
                    b, i = parse_subroutine(lines, i, fname)
                    node["branches"].append({"guard": m2.group("g").strip(), "body": b})
                elif RE_ELSE.match(t2):
                    i += 1
                    b, i = parse_subroutine(lines, i, fname)
                    node["branches"].append({"guard": "else", "body": b})
                else:
                    break
            if i < len(lines) and RE_END_IF.match(lines[i][1]):
                i += 1
            body.append(node)
            continue

        if (m := RE_SELECT.match(text)):
            node = {"kind": "SELECT", "line": ln, "expr": m.group("e").strip(),
                    "cases": []}
            i += 1
            while i < len(lines) and not RE_END_SELECT.match(lines[i][1]):
                if (mc := RE_CASE.match(lines[i][1])):
                    i += 1
                    b, i = parse_subroutine(lines, i, fname)
                    node["cases"].append({"value": mc.group("v"), "body": b})
                else:
                    i += 1
            if i < len(lines):
                i += 1
            body.append(node)
            continue

        if (m := RE_DO_LBL.match(text)):
            lbl = m.group("lbl")
            i += 1
            inner, i = parse_subroutine(lines, i, fname, stop_label=lbl)
            body.append({"kind": "LOOP", "line": ln,
                         "bounds": m.group("b").strip(), "label": lbl,
                         "body": inner})
            continue

        if RE_DO.match(text) and not RE_END_DO.match(text):
            b = RE_DO.match(text).group("b").strip()
            i += 1
            inner, i = parse_subroutine(lines, i, fname)
            if i < len(lines) and RE_END_DO.match(lines[i][1]):
                i += 1
            body.append({"kind": "LOOP", "line": ln, "bounds": b, "body": inner})
            continue

        if (r := parse_read(text, ln, fname)):
            body.append(r)
            i += 1
            continue

        if (m := RE_ASSIGN.match(text)) and not split_if_one(text):
            # Scalar assignments matter: an array bound in a later READ can be
            # a plain local set by one (`nrfields = group(igroup)%nrfields`,
            # Global.f90:1122). Dropping them makes the decoder stop where the
            # solver has no difficulty at all.
            body.append({"kind": "ASSIGN", "line": ln,
                         "lhs": m.group("lhs").strip(),
                         "rhs": m.group("rhs").strip()})
            i += 1
            continue

        if (one := split_if_one(text)):
            g, inner_txt = one
            child = parse_read(inner_txt, ln, fname) or (
                {"kind": "CALL", "line": ln, "callee": RE_CALL.match(inner_txt).group("n")}
                if RE_CALL.match(inner_txt) else
                ({"kind": "RETURN", "line": ln} if RE_RETURN.match(inner_txt) else
                 ({"kind": "GOTO", "line": ln,
                   "label": RE_GOTO.match(inner_txt).group("lbl")}
                  if RE_GOTO.match(inner_txt) else
                  ({"kind": "CYCLE", "line": ln}
                   if RE_CYCLE.match(inner_txt) else
                   ({"kind": "EXIT", "line": ln}
                    if RE_EXIT.match(inner_txt) else None)))))
            if child:
                body.append({"kind": "IF", "line": ln, "guard": g,
                             "branches": [{"guard": g,
                                           "body": {"kind": "SEQ", "body": [child]}}]})
            i += 1
            continue

        if (m := RE_ALLOC.match(text)):
            # `read(unit,*) a%b` with no section reads the WHOLE array, and the
            # only statement of its length is the allocate. Carry the extent so
            # a consumer can size the read instead of guessing 1 item — a
            # 1001-entry curve read as 1 item slides the cursor by 1000 and
            # every later record is garbage, silently.
            for a in split_args(m.group("args")):
                mm = re.match(r"^([A-Za-z_]\w*(?:\([^()]*\))?(?:%\w+)*)\s*\((.+)\)$",
                              a.strip())
                if mm:
                    dims = split_args(mm.group(2))
                    if len(dims) == 1:
                        body.append({"kind": "ALLOC", "line": ln,
                                     "name": mm.group(1).strip(),
                                     "extent": dims[0].strip()})
            i += 1
            continue

        if RE_EXIT.match(text):
            body.append({"kind": "EXIT", "line": ln})
            i += 1
            continue

        if RE_CYCLE.match(text):
            # Same family as GOTO/RETURN: an early exit that changes what is
            # read afterwards. `Load.f90:813 if(vdimn/=abs(water))cycle`.
            body.append({"kind": "CYCLE", "line": ln})
            i += 1
            continue

        if (m := RE_GOTO.match(text)):
            # 392 goto statements repo-wide, and the deck readers use them to
            # skip whole sections: `goto 222` at Global.f90:1634 jumps over the
            # `111 continue` block that reads .nrt. Without this node a decoder
            # walks straight into skipped records and desynchronises its
            # cursor — a wrong answer, not an incomplete one.
            body.append({"kind": "GOTO", "line": ln, "label": m.group("lbl")})
            i += 1
            continue

        if RE_GOTO_COMPUTED.match(text):
            # `goto (10,20,30), i` — a jump we cannot resolve statically.
            # Mark it so the decoder stops instead of falling through.
            body.append({"kind": "GOTO", "line": ln, "label": None})
            i += 1
            continue

        if RE_RETURN.match(text):
            # Without RETURN the decoder walks past `if (ngaps==0) return`
            # (Global.f90:3333) and consumes the next section's label as data.
            # An early return is part of the read protocol, not control-flow
            # noise.
            body.append({"kind": "RETURN", "line": ln})
            i += 1
            continue

        if (m := RE_CALL.match(text)):
            body.append({"kind": "CALL", "line": ln, "callee": m.group("n")})
            i += 1
            continue

        i += 1
    return {"kind": "SEQ", "body": body}, i


def parse_file(path: Path) -> dict[str, dict]:
    lines = logical_lines(path)
    subs, i = {}, 0
    while i < len(lines):
        m = RE_SUB.match(lines[i][1])
        if not m:
            i += 1
            continue
        name, start = m.group(1), lines[i][0]
        i += 1
        node, i = parse_subroutine(lines, i, path.name)
        node["name"], node["file"], node["line"] = name, path.name, start
        subs[name] = node
        if i < len(lines) and RE_END_SUB.match(lines[i][1]):
            i += 1
    return subs


# ── pruning and inlining ──────────────────────────────────────────────────

def reads_deck(node: dict, subs: dict, seen: set | None = None) -> bool:
    seen = seen if seen is not None else set()
    k = node.get("kind")
    if k == "READ":
        return True
    if k == "CALL":
        c = node["callee"]
        if c in seen or c not in subs:
            return False
        seen.add(c)
        return reads_deck(subs[c], subs, seen)
    for child in children(node):
        if reads_deck(child, subs, seen):
            return True
    return False


def children(node: dict):
    k = node.get("kind")
    if k == "SEQ":
        return node["body"]
    if k == "IF":
        return [b["body"] for b in node["branches"]]
    if k == "SELECT":
        return [c["body"] for c in node["cases"]]
    if k == "LOOP":
        return [node["body"]]
    return []


CONTROL = ("CYCLE", "GOTO", "RETURN", "EXIT")


def control_skeleton(node: dict) -> dict | None:
    """Keep only the control-flow of an otherwise-dead branch.

    A branch with no READ is not inert: a `cycle` inside it skips the rest of
    the enclosing loop iteration, and that iteration may read further down.
    Emitting an empty body would tell a consumer "nothing happens here", which
    is wrong in exactly the silent way this project keeps getting bitten by.
    Structure (IF / LOOP / SELECT) is preserved so a conditional `cycle` does
    not become an unconditional one.
    """
    k = node.get("kind")
    if k in CONTROL:
        return node
    if k == "SEQ":
        kids = [x for x in (control_skeleton(c) for c in node["body"]) if x]
        return {"kind": "SEQ", "body": kids} if kids else None
    if k == "IF":
        brs = [{"guard": b["guard"], "body": cb}
               for b in node["branches"]
               if (cb := control_skeleton(b["body"]))]
        return {"kind": "IF", "line": node["line"], "branches": brs} if brs else None
    if k == "LOOP":
        cb = control_skeleton(node["body"])
        return {"kind": "LOOP", "line": node["line"], "bounds": node["bounds"],
                "body": cb} if cb else None
    if k == "SELECT":
        cs = [{"value": c["value"], "body": cb} for c in node["cases"]
              if (cb := control_skeleton(c["body"]))]
        return {"kind": "SELECT", "line": node["line"], "expr": node["expr"],
                "cases": cs} if cs else None
    return None


def prune(node: dict, subs: dict, stack: tuple = (),
          live: frozenset = frozenset()) -> dict | None:
    """Drop everything that cannot reach a deck READ; inline reader calls.

    `live` carries the variables tested by enclosing `do while(...)` guards.
    An assign-only subtree is normally dead weight, but one that WRITES a
    live variable is part of the read protocol: `do while(tedge<ntelgroup)`
    (Temper.f90:245) advances `tedge` only inside `do ipegroup=1,sedge`, a
    loop with no READs at all. Pruning it froze the guard and the consumer
    looped until the deck ran dry.
    """
    k = node.get("kind")
    if k == "READ":
        return node
    if k == "CALL":
        c = node["callee"]
        if c not in subs or c in stack or not reads_deck(subs[c], subs):
            return None
        inner = prune(subs[c], subs, stack + (c,), live)
        if inner is None:
            return None
        return {"kind": "CALL", "line": node["line"], "callee": c, "body": inner}
    if k in ("ASSIGN", "RETURN", "GOTO", "LABEL", "CYCLE", "EXIT", "ALLOC"):
        return node
    if k == "SEQ":
        kids = [x for x in (prune(c, subs, stack, live) for c in node["body"]) if x]
        # A branch whose whole body is a RETURN is precisely the one that must
        # survive: it changes what gets read afterwards. Only an all-ASSIGN
        # sequence is truly empty for our purposes — unless one of those
        # assigns writes a variable an enclosing while-guard tests (see the
        # docstring): dropping that would freeze the loop condition.
        if not any(x for x in kids if x.get("kind") not in ("ASSIGN", "LABEL", "ALLOC")):
            if not any(x.get("kind") == "ASSIGN"
                       and re.sub(r"\(.*", "", x["lhs"].split("%")[0]).strip().lower()
                           in live
                       for x in kids):
                return None
        out = {"kind": "SEQ", "body": kids}
        for f in ("name", "file", "line"):
            if f in node:
                out[f] = node[f]
        return out
    if k == "IF":
        # Keep the GUARD of every branch, even when its body prunes to nothing.
        # Dropping a guard turns `if (water/=0) then <no reads> else <reads> end
        # if` into an IF whose only branch is `else` — and a consumer then takes
        # else unconditionally and reads records the solver never reads. Nine
        # such nodes existed (Fem.f90:268, Load.f90:788, Output.f90:4170).
        # A guard is part of the read protocol; the same lesson as the
        # RETURN-only branch. An empty body is fine; a missing guard is not.
        brs, any_live = [], False
        for b in node["branches"]:
            pb = prune(b["body"], subs, stack, live)
            if pb:
                any_live = True
                brs.append({"guard": b["guard"], "body": pb})
            else:
                brs.append({"guard": b["guard"],
                            "body": control_skeleton(b["body"])
                                    or {"kind": "SEQ", "body": []}})
        return {"kind": "IF", "line": node["line"], "branches": brs} if any_live else None
    if k == "SELECT":
        cs = []
        for c in node["cases"]:
            pc = prune(c["body"], subs, stack, live)
            if pc:
                cs.append({"value": c["value"], "body": pc})
        return {"kind": "SELECT", "line": node["line"], "expr": node["expr"],
                "cases": cs} if cs else None
    if k == "LOOP":
        wm = re.match(r"\s*while\s*\((.*)\)\s*$", node["bounds"], re.I)
        inner_live = (live | {t.lower() for t in
                              re.findall(r"[A-Za-z_]\w*", wm.group(1))}
                      if wm else live)
        pb = prune(node["body"], subs, stack, inner_live)
        return {"kind": "LOOP", "line": node["line"], "bounds": node["bounds"],
                "body": pb} if pb else None
    return None


# ── rendering ─────────────────────────────────────────────────────────────

def render(node: dict, ind: int = 0, out: list | None = None) -> list[str]:
    out = out if out is not None else []
    p = "  " * ind
    k = node.get("kind")
    if k == "SEQ":
        if "name" in node:
            out.append(f"{p}▸ {node['name']}  ({node['file']}:{node['line']})")
            ind += 1
        for c in node["body"]:
            render(c, ind, out)
    elif k == "READ":
        v = ", ".join(node["vars"])
        if len(v) > 84:
            v = v[:81] + "…"
        out.append(f"{p}READ {node['deck']:<5} [{node['arity']:>14}]  {v}   {node.get('file','?')}:{node['line']}")
    elif k == "IF":
        for i, b in enumerate(node["branches"]):
            kw = "IF" if i == 0 else ("ELSE" if b["guard"] == "else" else "ELIF")
            g = "" if b["guard"] == "else" else f" ({b['guard'][:70]})"
            out.append(f"{p}{kw}{g}")
            render(b["body"], ind + 1, out)
    elif k == "SELECT":
        out.append(f"{p}SELECT CASE ({node['expr']})")
        for c in node["cases"]:
            out.append(f"{p}  CASE {c['value']}")
            render(c["body"], ind + 2, out)
    elif k == "LOOP":
        out.append(f"{p}DO {node['bounds'][:60]}")
        render(node["body"], ind + 1, out)
    elif k == "ASSIGN":
        out.append(f"{p}SET  {node['lhs']} = {node['rhs'][:60]}   L{node['line']}")
    elif k == "RETURN":
        out.append(f"{p}RETURN   L{node['line']}")
    elif k == "GOTO":
        out.append(f"{p}GOTO {node['label'] or '<computed>'}   L{node['line']}")
    elif k == "CYCLE":
        out.append(f"{p}CYCLE   L{node['line']}")
    elif k == "EXIT":
        out.append(f"{p}EXIT   L{node['line']}")
    elif k == "ALLOC":
        out.append(f"{p}ALLOC {node['name']}({node['extent']})   L{node['line']}")
    elif k == "LABEL":
        out.append(f"{p}{node['label']}:   L{node['line']}")
    elif k == "CALL":
        out.append(f"{p}CALL {node['callee']}   L{node['line']}")
        render(node["body"], ind + 1, out)
    return out


def walk(node: dict, fn, path: tuple = ()):
    fn(node, path)
    k = node.get("kind")
    if k == "IF":
        for b in node["branches"]:
            walk(b["body"], fn, path + (("IF", b["guard"]),))
    elif k == "SELECT":
        for c in node["cases"]:
            walk(c["body"], fn, path + (("CASE", f"{node['expr']}={c['value']}"),))
    elif k == "LOOP":
        walk(node["body"], fn, path + (("DO", node["bounds"]),))
    elif k == "CALL" and "body" in node:   # un-inlined calls have no subtree
        walk(node["body"], fn, path + (("CALL", node["callee"]),))
    elif k == "SEQ":
        for c in node["body"]:
            walk(c, fn, path)


def main():
    subs = {}
    for f in sorted(SRC.glob("*.f90")):
        subs.update(parse_file(f))

    # The real entry is the driver that dispatches; find whoever calls global_data.
    driver = None
    for name, node in subs.items():
        found = []
        walk(node, lambda n, p: found.append(n) if n.get("kind") == "CALL"
             and n.get("callee") == "global_data" else None)
        if found:
            driver = name
            break

    trees = {}
    for name in [n for n in (driver, "global_data") if n]:
        t = prune(subs[name], subs)
        if t:
            trees[name] = t

    OUT = Path(__file__).resolve().parent.parent / "data"
    OUT.mkdir(exist_ok=True)
    (OUT / "deck-ast.json").write_text(json.dumps(
        {"source": str(SRC), "driver": driver, "trees": trees},
        indent=1, ensure_ascii=False))

    txt = []
    for name, t in trees.items():
        txt.append(f"{'='*100}\nROOT {name}\n{'='*100}")
        txt += render(t)
    (OUT / "deck-ast.txt").write_text("\n".join(txt))

    nreads = [0]
    walk(trees[driver] if driver else list(trees.values())[0],
         lambda n, p: nreads.__setitem__(0, nreads[0] + 1) if n.get("kind") == "READ" else None)
    print(f"子程序 {len(subs)} 个；driver = {driver}")
    print(f"剪枝后的树含 READ {nreads[0]} 条")
    print(f"wrote {OUT/'deck-ast.json'}  {OUT/'deck-ast.txt'}")


if __name__ == "__main__":
    main()
