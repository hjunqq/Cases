#!/usr/bin/env python3
"""Resolve a case's Deck Path: given switch values, what does the solver read?

This is the piece the AST was missing. The tree records every guard as text;
this evaluates them against a switch assignment and returns the ordered
sequence of records the solver will actually consume — the case's own filling
recipe, derived rather than remembered.

Three-valued logic is deliberate. A guard mentioning a variable we have not
supplied evaluates to UNKNOWN, and an UNKNOWN branch is kept and flagged
rather than silently dropped. Dropping it would reproduce the failure this
whole project is about: a record the solver reads that nobody knew to fill.

    python3 case_path.py --switches type_problem=Q,type_ABC=FIX,nblks=2
    python3 case_path.py --case train01_gravdam_static
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNKNOWN = "unknown"

CMP = re.compile(r"""^\s*(?P<l>[A-Za-z_]\w*(?:\([^)]*\))?(?:%\w+(?:\([^)]*\))?)*)\s*
                      (?P<op>==|/=|>=|<=|>|<)\s*
                      (?P<r>'[^']*'|"[^"]*"|-?\d+(?:\.\d*)?|[A-Za-z_]\w*)\s*$""",
                 re.X)


import ast as _pyast

_ALLOWED = (_pyast.Expression, _pyast.BinOp, _pyast.UnaryOp, _pyast.Constant,
            _pyast.Name, _pyast.Load, _pyast.Add, _pyast.Sub, _pyast.Mult,
            _pyast.Div, _pyast.FloorDiv, _pyast.Mod, _pyast.USub, _pyast.UAdd)


class Undecidable(Exception):
    pass


def norm_name(v: str) -> str:
    """`group(igroup)%nrfields` → `group%nrfields`; `a(1:n)` → `a`."""
    parts = [re.sub(r"\(.*", "", x).strip().lower() for x in v.split("%")]
    return "%".join(x for x in parts if x)


def arith(expr: str, env: dict):
    """Evaluate a Fortran integer expression against env, or raise Undecidable.

    The single shared evaluator: guards, array bounds and loop bounds all use
    it. `/` becomes floor division — these are integer switches
    (`ground_inf/100==1`), and Fortran truncates toward zero, which agrees
    with floor for the non-negative values these hold.
    """
    e = expr.strip().lower()
    if not e:
        raise Undecidable("empty")
    # Subscripts first: `group(igroup)%nrfields` has `)` before the `%`, so
    # replacing `%` first simply does not match and the name never resolves.
    e = re.sub(r"([a-z_]\w*)\s*\([^()]*\)", r"\1", e)
    # Components nest arbitrarily deep (`props(imat)%mechanical%solid%igap0`).
    # A single pass of a `name%name` substitution only eats the first level and
    # leaves a stray `%`, which Python then reads as modulo.
    e = e.replace("%", "__")
    e = e.replace("/", "//").replace("////", "//")
    try:
        node = _pyast.parse(e, mode="eval")
    except SyntaxError:
        raise Undecidable(f"parse `{expr}`")
    for n in _pyast.walk(node):
        if not isinstance(n, _ALLOWED):
            raise Undecidable(f"syntax `{expr}`")
    scope = {}
    for k, v in env.items():
        if isinstance(v, (int, float)):
            scope[k.replace("%", "__")] = v
    names = {n.id for n in _pyast.walk(node) if isinstance(n, _pyast.Name)}
    miss = sorted(n for n in names if n not in scope)
    if miss:
        raise Undecidable(f"unbound {miss} in `{expr}`")
    try:
        return eval(compile(node, "<arith>", "eval"), {"__builtins__": {}}, scope)
    except Exception as exc:                                    # noqa: BLE001
        raise Undecidable(f"{type(exc).__name__} on `{expr}`")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def eval_guard(g: str, env: dict):
    """Three-valued evaluation of one Fortran guard. True / False / UNKNOWN."""
    s = g.strip()
    if s.lower() == "else":
        return UNKNOWN            # resolved by the caller from its siblings
    s = re.sub(r"\s+", " ", s)
    # Old-style relational operators are still used throughout (`jliqu.ne.0`).
    for a, b in ((".ne.", "/="), (".eq.", "=="), (".ge.", ">="), (".le.", "<="),
                 (".gt.", ">"), (".lt.", "<")):
        s = re.sub(re.escape(a), b, s, flags=re.I)

    # .or. binds loosest, then .and., then .not.
    for op, fold in ((r"\.or\.", any), (r"\.and\.", all)):
        parts = _split_top(s, op)
        if len(parts) > 1:
            vals = [eval_guard(p, env) for p in parts]
            if op == r"\.or\.":
                if any(v is True for v in vals):
                    return True
                return UNKNOWN if UNKNOWN in vals else False
            if any(v is False for v in vals):
                return False
            return UNKNOWN if UNKNOWN in vals else True

    if s.lower().startswith(".not."):
        v = eval_guard(s[5:], env)
        return UNKNOWN if v is UNKNOWN else (not v)
    while s.startswith("(") and s.endswith(")") and _balanced(s[1:-1]):
        s = s[1:-1].strip()
        return eval_guard(s, env)

    # `trim(property)=='MECHANICAL'` — unwrap the character intrinsics so the
    # comparison reduces to a plain name test.
    s = re.sub(r"\b(?:trim|adjustl|adjustr)\s*\(\s*([A-Za-z_]\w*(?:\([^()]*\))?(?:%\w+)*)\s*\)",
               r"\1", s, flags=re.I)

    m = CMP.match(s)
    if not m:
        # `ground_inf/100==1` and friends: not a bare name on the left, so fall
        # back to evaluating both sides arithmetically.
        m2 = re.match(r"^(.*?)(==|/=|>=|<=|>|<)(.*)$", s)
        if not m2:
            return UNKNOWN
        try:
            lv, rv = arith(m2.group(1), env), arith(m2.group(3), env)
        except Undecidable:
            return UNKNOWN
        op = m2.group(2)
        return {"==": lv == rv, "/=": lv != rv, ">": lv > rv,
                "<": lv < rv, ">=": lv >= rv, "<=": lv <= rv}[op]
    name = norm_name(m.group("l"))
    if name not in env:
        return UNKNOWN
    # Fortran substring: `criteria(1:2)=='MC'` asks about the first two
    # characters, not the whole string. Dropping the subscript made every such
    # guard compare 'MCJOINT' with 'MC' and answer False — a wrong answer, not
    # an undecidable one. Only applied when the bound value really is a string;
    # on an array `a(1:2)` is a section and this does not fire.
    sub = re.search(r"\(\s*(\d+)\s*:\s*(\d+)\s*\)\s*$", m.group("l"))
    if sub and isinstance(env.get(name), str):
        lo, hi = int(sub.group(1)), int(sub.group(2))
        env = dict(env, **{name: env[name][lo - 1:hi]})
    raw = m.group("r").strip()
    # In Fortran an unquoted, non-numeric right-hand side is a VARIABLE, not a
    # literal. `tedge<nedge` compares two variables; treating `nedge` as the
    # string "nedge" makes every such guard undecidable (and, for `==`, quietly
    # false). Resolve it against the environment; leave UNKNOWN when it is not
    # bound, which is the honest answer for a name we have not read.
    if re.fullmatch(r"[A-Za-z_]\w*", raw):
        key = raw.lower()
        if key not in env:
            return UNKNOWN
        raw = env[key]
    lhs, rhs, op = env[name], str(raw).strip("'\""), m.group("op")
    ln, rn = _num(lhs), _num(rhs)
    if ln is not None and rn is not None:
        lhs, rhs = ln, rn
    else:
        lhs, rhs = str(lhs).strip().lower(), str(rhs).strip().lower()
        if op in (">", "<", ">=", "<="):
            return UNKNOWN
    return {"==": lhs == rhs, "/=": lhs != rhs, ">": lhs > rhs,
            "<": lhs < rhs, ">=": lhs >= rhs, "<=": lhs <= rhs}[op]


def _balanced(s):
    d = 0
    for c in s:
        d += c == "("
        d -= c == ")"
        if d < 0:
            return False
    return d == 0


def _split_top(s, op):
    """Split on `op` at paren depth 0.

    The depth must advance from the PREVIOUS match, not from the last split
    point — otherwise the prefix is counted again at every match and
    `(A.and.B).and.C` never splits, which silently made every parenthesised
    compound guard undecidable.
    """
    out, depth, last, prev = [], 0, 0, 0
    for m in re.finditer(op, s, re.I):
        chunk = s[prev:m.start()]
        depth += chunk.count("(") - chunk.count(")")
        prev = m.end()
        if depth == 0:
            out.append(s[last:m.start()])
            last = m.end()
    out.append(s[last:])
    return [x for x in out if x.strip()] if len(out) > 1 else [s]


def resolve(node, env, guards=(), loops=(), sub=None, out=None):
    out = out if out is not None else []
    k = node.get("kind")
    if k == "READ":
        out.append({"deck": node["deck"], "file": node.get("file"),
                    "line": node["line"], "arity": node["arity"],
                    "vars": node["vars"], "reader": sub,
                    "guards": list(guards), "loops": list(loops),
                    "certain": all(c for _, c in guards)})
    elif k == "CALL" and "body" in node:
        resolve(node["body"], env, guards, loops, node["callee"], out)
    elif k == "IF":
        taken = None
        for b in node["branches"]:
            if b["guard"] == "else":
                continue
            v = eval_guard(b["guard"], env)
            if v is True and taken is None:
                taken = b
            if v is True or v is UNKNOWN:
                resolve(b["body"], env, guards + ((b["guard"], v is True),),
                        loops, sub, out)
        # `else` runs only if no sibling was definitely true
        if taken is None:
            for b in node["branches"]:
                if b["guard"] == "else":
                    known_false = all(eval_guard(x["guard"], env) is False
                                      for x in node["branches"]
                                      if x["guard"] != "else")
                    resolve(b["body"], env, guards + (("else", known_false),),
                            loops, sub, out)
    elif k == "SELECT":
        for c in node["cases"]:
            g = f'{node["expr"]}=={c["value"].strip("()")}'
            v = eval_guard(g, env)
            if v is not False:
                resolve(c["body"], env, guards + ((g, v is True),), loops, sub, out)
    elif k == "LOOP":
        resolve(node["body"], env, guards, loops + (node["bounds"],), sub, out)
    elif k == "SEQ":
        for c in node["body"]:
            resolve(c, env, guards, loops, sub, out)
    return out


def switches_from_deck(case_dir: Path) -> dict:
    """Read the switch values a real deck declares, so a case can be replayed."""
    env, glb = {}, case_dir / "1.glb"
    if not glb.exists():
        return env
    L = glb.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, l in enumerate(L):
        nxt = L[i + 1] if i + 1 < len(L) else ""
        vals = [x.strip("'\"") for x in re.split(r"[,\s]+", nxt.strip()) if x]
        if "NPOIN" in l and "NDIMN" in l and len(vals) >= 6:
            names = [h.lower() for h in re.split(r"[,\s']+", l) if h]
            for n, v in zip(names, vals):
                env.setdefault(n, v)
        if "NINIT" in l and "NBLKS" in l:
            names = [h.lower() for h in re.split(r"[,\s']+", l) if h]
            for n, v in zip(names, vals):
                env.setdefault(n, v)
        if "TYPE_PROBLEM" in l and "TYPE_SOLVER" in l:
            names = [h.lower() for h in re.split(r"[,\s']+", l) if h]
            for n, v in zip(names, vals):
                env.setdefault(n, v)
    return env


def guard_names(ast_) -> set:
    """Every identifier that appears in a guard, a loop bound, or an arity.

    A switch name outside this set changes nothing, whatever it is set to. The
    tool used to accept such a name and drop it without a word, so
    `--switches ntrans=1` came back identical to omitting it — and a reader
    concludes `ntrans` does not affect the deck, when in fact
    `Prescrib.f90:228 frecoord` is guarded by it (the name there is spelled
    differently). Silent degradation is this project's own main symptom; it has
    no business in the tool that measures it.
    """
    out: set = set()

    def add(txt):
        out.update(x.lower() for x in re.findall(r"[A-Za-z_]\w*", str(txt)))

    def walk(n):
        if isinstance(n, dict):
            k = n.get("kind")
            if k == "IF":
                for b in n["branches"]:
                    add(b["guard"])
            elif k == "SELECT":
                add(n["expr"])
                for c in n["cases"]:
                    add(c["value"])
            elif k == "LOOP":
                add(n["bounds"])
            elif k == "READ":
                add(n.get("arity", ""))
                for v in n.get("vars", []):
                    add(v)
            elif k == "ASSIGN":
                add(n.get("lhs", ""))
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(ast_["trees"])
    return out


def check_switches(env: dict, known: set) -> list:
    import difflib
    bad = []
    for k in env:
        base = k.split("%")[0]
        if base not in known:
            bad.append((k, difflib.get_close_matches(base, sorted(known), 3, 0.7)))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--switches", default="")
    ap.add_argument("--case")
    ap.add_argument("--deck", help="only this deck file, e.g. .glb")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow-unknown", action="store_true",
                    help="proceed even if a switch name appears in no guard")
    a = ap.parse_args()

    env = {}
    if a.case:
        env = switches_from_deck(Path("/home/huijun/HSTAR_Next/cases/cases") / a.case)
    for kv in filter(None, a.switches.split(",")):
        k, _, v = kv.partition("=")
        env[k.strip().lower()] = v.strip()

    ast = json.load(open(ROOT / "data" / "deck-ast.json"))

    # Names given on the command line are checked against the tree. Names read
    # out of a deck are not: a deck legitimately declares fields no guard tests.
    given = {kv.partition("=")[0].strip().lower()
             for kv in filter(None, a.switches.split(","))}
    unknown = check_switches({k: env[k] for k in given if k in env},
                             guard_names(ast))
    if unknown:
        import sys as _sys
        for name, near in unknown:
            hint = f"；最接近的是 {', '.join(near)}" if near else "（树里没有相近的名字）"
            print(f"错误: 开关 `{name}` 在整棵树的守卫、循环界与 arity 里从未出现，"
                  f"设成什么都不会改变结果{hint}", file=_sys.stderr)
        if not a.allow_unknown:
            print("已中止。用 --allow-unknown 可以继续（结果与不给该开关时完全相同）。",
                  file=_sys.stderr)
            raise SystemExit(2)

    path = resolve(ast["trees"][ast["driver"]], env)
    if a.deck:
        path = [r for r in path if r["deck"] == a.deck]

    if a.json:
        print(json.dumps({"switches": env,
                          "unknown_switches": [n for n, _ in unknown],
                          "path": path}, indent=1, ensure_ascii=False))
        return

    cert = sum(r["certain"] for r in path)
    print(f"开关 {len(env)} 个: " + ", ".join(f"{k}={v}" for k, v in
                                              sorted(env.items()) if v not in ("", "0"))[:150])
    print(f"解出记录 {len(path)} 条，其中条件完全确定 {cert} 条，"
          f"含未定守卫 {len(path)-cert} 条")
    if path and (len(path) - cert) > len(path) // 2:
        print(f"⚠ 未定守卫占 {100*(len(path)-cert)//len(path)}%——**绝对条数不可当作结论**。"
              f"这个数主要反映有多少守卫还没被开关定死。"
              f"要得到可信结果，请比较两组开关的**差集**，不要比较总数。")
    print()
    per = {}
    for r in path:
        per.setdefault(r["deck"], []).append(r)
    for d, rs in per.items():
        print(f"  {d}: {len(rs)} 条 (确定 {sum(x['certain'] for x in rs)})")
    print("\n前 18 条（? = 守卫未定）:")
    for r in path[:18]:
        mark = " " if r["certain"] else "?"
        v = ", ".join(r["vars"])[:64]
        print(f" {mark} {r['deck']:<5} [{r['arity']:>10}] {v}   {r['file']}:{r['line']}")


if __name__ == "__main__":
    main()
