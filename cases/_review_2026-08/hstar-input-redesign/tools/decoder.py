#!/usr/bin/env python3
"""ABI-driven deck decoder — the shared text layer (roadmap P0-1).

Every previous reader in this project was hand-written, and the same Fortran
text rule (`!` truncation, record-tail discard, `n*v` expansion) was
re-implemented — and got wrong — in six separate places. This is the one
implementation, and it is not hand-written at all: it walks the AST and lets
the solver's own READ statements say what to consume.

The design property that matters:

    THIS DECODER CANNOT BE WRONG. IT CAN ONLY BE INCOMPLETE.

If a guard or an arity cannot be evaluated from what has been read so far, it
stops and reports the exact position instead of guessing. Guessing would
desynchronise the cursor, and a desynchronised cursor produces a plausible
wrong answer — the exact failure mode this whole project is about.

Values read are fed back into the environment, so later guards and array
bounds become decidable as decoding proceeds. That feedback is what makes
real coverage measurable at all (see 17-case-research-loop.md §4).

    python3 decoder.py --case train01_gravdam_static
    python3 decoder.py --case train01_gravdam_static --deck .glb --values
"""
from __future__ import annotations

import argparse
import ast as pyast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = Path("/home/huijun/HSTAR_Next/cases/cases")

def _deck_files() -> dict:
    """`.glb` → `1.glb`, derived from the AST rather than hand-listed.

    Every `open` in the solver is `probn(1:len1)//ext` with `probn='1'` for
    these cases (Global.f90:630-673, Level.f90:209-210), so the file name is
    the extension with the problem name in front — including the two that are
    not really extensions (`_l.glb`, `_l.bou`). Reading the deck names out of
    the AST means the day the AST grows another unit, the decoder opens it too;
    a hand-kept copy of this map is exactly the kind of second list that goes
    stale (the six text-layer copies were the same mistake).
    """
    try:
        ast_ = json.load(open(ROOT / "data" / "deck-ast.json"))
    except OSError:
        return {}
    decks: set[str] = set()

    def walk(n):
        if isinstance(n, dict):
            if n.get("kind") == "READ" and n.get("deck"):
                decks.add(n["deck"])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(ast_["trees"])
    # `probn` is `1` for every case in the suite — and that is read from the
    # deck, not assumed: `inp` record 4 says so (Fem.f90:96). A deck name that
    # does not start with `.` is not an extension but a literal file name
    # (`inp` itself, opened as `open(inpunit,file='inp')`, Fem.f90:92).
    return {d: (d if not d.startswith((".", "_")) else "1" + d)
            for d in sorted(decks)}


DECK_FILE = _deck_files()

# The Fortran text layer is shared with the production importer — there is
# exactly one implementation, in fem-chat/skills/deck_text.py. A second copy
# lived here and drifted; that drift is why several probes reported wrong
# answers before this was consolidated.
sys.path.insert(0, str(ROOT.parents[2] / "skills"))
from deck_text import Deck as Cursor, expand  # noqa: E402


# ── the deck's own version stamp ──────────────────────────────────────────
#
# 13-probe-report-old-format-peel established that each data record in these
# decks is preceded by a label record naming its fields, and that the label is
# the record's VERSION STAMP: an older deck names fewer fields because the
# record itself was shorter then.
#
# That gives a check the decoder can make against the deck itself. When the
# label spells out a strict PREFIX of the variables the READ wants, the record
# in front of us is an older, shorter version of the one the solver now reads —
# and consuming the solver's arity from it would run into the next record and
# desynchronise the cursor. Five `.ftr` files in the suite are exactly this:
# the label says `nforce`, the current solver reads
# `nforce,ngaps,nforce_gaps,nsafety_gaps`.
#
# It only ever produces a STOP; it never lets decoding continue. A prefix match
# is deliberately the strictest possible trigger — prose labels ("remesh
# limited values") share no name with the variables and never fire.

def label_names(raw: str) -> list[str]:
    """Field names a label record spells out, or [] if it is prose."""
    out = []
    for t in re.split(r"[,\s]+", raw.strip().strip("'\"")):
        t = t.strip("'\"()").lower()
        if t:
            out.append(t)
    return out


def version_mismatch(label: list[str], vars_: list[str]) -> str | None:
    """`None` if the label does not contradict the READ."""
    want = [norm_name(v).split("%")[-1] for v in vars_]
    if len(label) >= len(want) or not label:
        return None
    if label != want[:len(label)]:
        return None
    # A label naturally names only the scalars: `listglocbeam(1:nlocalbeam)`
    # contributes zero items when `nlocalbeam=0`, so a shorter label there is
    # the CURRENT format, not an older one. Fire only when everything the label
    # left out is a plain scalar and therefore genuinely missing.
    if any(re.search(r"\(\s*\d*\s*:", v) or "=" in v for v in vars_[len(label):]):
        return None
    return (f"deck record version mismatch: the label names {len(label)} field(s) "
            f"({', '.join(label)}) but this READ takes {len(want)} "
            f"({', '.join(want)}) — the record in the file is an older, shorter "
            f"version, and reading the solver's arity from it would desynchronise "
            f"the cursor")


# ── whole-array READs ─────────────────────────────────────────────────────
#
# `read(loadunit,*)tcurves(itcurve)%dfact_curve` (Load.f90:213) reads the WHOLE
# array — 1001 items for a seismic curve — but the statement says nothing about
# its extent, which comes from an `allocate` the AST does not carry. The
# decoder used to treat a bare name as one item and walk on, turning a 1001-item
# record into a 1000-item cursor slip: garbage from there to end of file, with
# no complaint. This is the same failure the whole project is about, so a
# whole-array read has to stop.
#
# The tree can at least PROVE which names are arrays: the same component is read
# elsewhere with an explicit section (`…%dfact_curve(1:ntime)`, Load.f90:220).
# That proves array-ness; it does not prove the extent, because nothing says the
# allocated size equals the section used elsewhere. So this detects and stops —
# it never supplies a length.

def array_names(ast_) -> dict:
    """base name → the section expressions it is read with somewhere."""
    out: dict[str, set] = {}

    def walk(n):
        if isinstance(n, dict):
            if n.get("kind") == "READ":
                for v in n.get("vars", []):
                    m = re.search(r"\(\s*[^,()]*:\s*([^,()]+)\)\s*$", v)
                    if m:
                        out.setdefault(norm_name(v), set()).add(m.group(1).strip())
            for x in n.values():
                walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(ast_["trees"])
    return out


ARRAYS = None


def is_whole_array_read(var: str) -> bool:
    """True when `var` names an array with no section — extent unknown."""
    global ARRAYS
    if ARRAYS is None:
        try:
            ARRAYS = array_names(json.load(open(ROOT / "data" / "deck-ast.json")))
        except OSError:
            ARRAYS = {}
    last = var.split("%")[-1].strip()
    if "(" in last:
        return False                     # an element or an explicit section
    return norm_name(var) in ARRAYS


class _Returned(Exception):
    """Unwinds to the enclosing CALL — a Fortran `return`."""


class _Goto(Exception):
    """Unwinds to the SEQ that holds the target LABEL — a Fortran `goto`.

    Jumps are part of the read protocol, not control-flow noise: the block
    between `111 continue` and `222 continue` in Global.f90 is reachable ONLY
    through `goto 111`, and falling into it consumes `.nrt` records the solver
    never reads. Before this was modelled the decoder walked straight in and
    was saved only by hitting EOF — on a longer file it would have
    desynchronised the cursor silently.
    """

    def __init__(self, label, line):
        super().__init__(label)
        self.label, self.line = label, line


class _Cycle(Exception):
    """Next iteration of the innermost LOOP — a Fortran `cycle`."""


class _Exit(Exception):
    """Leave the innermost LOOP — a Fortran `exit`."""


class Undecidable(Exception):
    def __init__(self, why, where):
        super().__init__(why)
        self.why, self.where = why, where


_ALLOWED = (pyast.Expression, pyast.BinOp, pyast.UnaryOp, pyast.Constant,
            pyast.Name, pyast.Load, pyast.Add, pyast.Sub, pyast.Mult,
            pyast.Div, pyast.FloorDiv, pyast.Mod, pyast.USub, pyast.UAdd,
            pyast.Call)


def evaluate(expr: str, env: dict) -> int:
    """Integer arity / loop bound. Delegates to the one shared evaluator in
    case_path.arith — deliberately not a second implementation."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from case_path import arith, Undecidable as U
    try:
        v = arith(expr, env)
    except U as exc:
        raise Undecidable(str(exc), expr)
    try:
        return int(v)
    except (TypeError, ValueError):
        raise Undecidable(f"non-integer value {v!r} for `{expr}`", expr)


def _evaluate_unused(expr: str, env: dict) -> int:
    e = expr.strip().lower()
    if not e:
        raise Undecidable("empty expression", expr)
    e = re.sub(r"\bmax\b", "max", e)
    e = re.sub(r"([a-z_]\w*)\s*\([^)]*\)", r"\1", e)      # a(i) → a  (scalarise)
    e = re.sub(r"([a-z_]\w*)%([a-z_]\w*)", r"\1__\2", e)   # a%b → a__b (a valid name)
    try:
        node = pyast.parse(e, mode="eval")
    except SyntaxError:
        raise Undecidable(f"cannot parse `{expr}`", expr)
    for n in pyast.walk(node):
        if not isinstance(n, _ALLOWED):
            raise Undecidable(f"unsupported syntax in `{expr}`", expr)
    names = {n.id for n in pyast.walk(node) if isinstance(n, pyast.Name)}
    miss = [x for x in names
            if x.replace("__", "%") not in env or env[x.replace("__", "%")] is None]
    if miss:
        raise Undecidable(f"unbound {sorted(miss)} in `{expr}`", expr)
    scope = {k.replace("%", "__"): v for k, v in env.items()
             if isinstance(v, (int, float))}
    scope.update({"max": max, "min": min})
    try:
        return int(eval(compile(node, "<arity>", "eval"), {"__builtins__": {}}, scope))
    except Exception as exc:                                    # noqa: BLE001
        raise Undecidable(f"{type(exc).__name__} on `{expr}`", expr)


def norm_name(v: str) -> str:
    """`group(igroup)%nrfields` → `group%nrfields`; `lmdofn(1:mdofn)` → `lmdofn`.

    Subscripts are dropped, so a derived-type component binds to the element
    most recently read. That is correct wherever the READ and the use sit in
    the same loop iteration — which is the case throughout these readers — and
    it is the reason the decoder must stop rather than guess when a name is
    unbound: a stale binding would be worse than none.
    """
    parts = [re.sub(r"\(.*", "", x).strip().lower() for x in v.split("%")]
    return "%".join(x for x in parts if x)


def bind(env: dict, vars_: list[str], vals: list[str]):
    """Bind read values back into the environment — this is the feedback loop."""
    i = 0
    for v in vars_:
        base = norm_name(v)
        m = re.search(r"\(\s*1\s*:\s*([^)]+)\)", v)
        if m:
            try:
                n = evaluate(m.group(1), env)
            except Undecidable:
                return
            env[base] = [_cast(x) for x in vals[i:i + n]]
            i += n
        else:
            if i < len(vals):
                env[base] = _cast(vals[i])
            i += 1


def _cast(s: str):
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s.strip("'\"")


ASSUMPTIONS = None


def load_assumptions():
    """Names the decoder is permitted to bind without having read them.

    Each entry carries a justification and an evidence line. Everything decoded
    after an assumption fires is marked `assumed`, never `certain`, so the
    coverage number never quietly absorbs a guess. Names not listed here still
    stop the decoder — that is what keeps "cannot be wrong" true.
    """
    global ASSUMPTIONS
    if ASSUMPTIONS is None:
        f = ROOT / "data" / "assumptions.json"
        ASSUMPTIONS = ({a["name"].lower(): a for a in
                        json.loads(f.read_text())["assumptions"]}
                       if f.exists() else {})
    return ASSUMPTIONS


def apply_assumption(name: str, env: dict, used: list, at: str = "") -> bool:
    """Bind one declared assumption. Returns True if it fired.

    An entry may carry `"at"` — a source position, or a list of them. Then it
    fires ONLY at that guard, and the caller unbinds it again immediately.
    That matters for names the solver reuses: `idofn` is a mesh-derived DOF
    number in `prescrib_set` and a plain loop counter three subroutines later,
    and a global binding would silently answer the second question with the
    first one's assumption. A stale binding is worse than none — the same rule
    that governs derived-type components in `norm_name`.
    """
    a = load_assumptions().get(name.lower())
    if not a:
        return False
    scope = a.get("at")
    if scope:
        want = [scope] if isinstance(scope, str) else scope
        if not any(at.endswith(w) or w in at for w in want):
            return False
    v = a["value"]
    if isinstance(v, str):                       # an alias for another binding
        if v.lower() not in env:
            return False
        v = env[v.lower()]
    env[name.lower()] = v
    if a["name"] not in used:
        used.append(a["name"])
    return True


def scoped_assumption(name: str) -> bool:
    a = load_assumptions().get(name.lower())
    return bool(a and a.get("at"))


def _first_read(node):
    """The first READ in THIS subroutine — used only to name the file a stop is
    in. Nested CALL bodies are skipped: `process_analysis` lives in Fem.f90 but
    its first READ descendant is in Load.f90, and reporting that file sent the
    first read of this diagnostic to the wrong source line."""
    if isinstance(node, dict):
        if node.get("kind") == "READ":
            return node
        if node.get("kind") == "CALL":
            return None
        for v in node.values():
            r = _first_read(v)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _first_read(v)
            if r:
                return r
    return None


_INERT_CACHE: dict = {}


def _inert(node) -> bool:
    """True when this subtree can neither consume a deck record nor divert
    control out of itself: no READ, no GOTO, no RETURN anywhere under it.

    Such a loop is invisible to the cursor, so when its bound is a
    program-computed quantity (`do jnode=1,nnode_f`, Load.f90:380, where
    `nnode_f` comes from the element-type table) there is nothing to decide:
    running it zero times consumes exactly what running it n times consumes.
    Skipping is not a guess. Anything it would have ASSIGNed simply stays
    unbound, so a later use stops honestly instead of reading a made-up value.

    These loops only appear in the tree at all because they hold a CYCLE or an
    EXIT, which the pruner rightly keeps.
    """
    key = id(node)
    if key in _INERT_CACHE:
        return _INERT_CACHE[key]
    res = True
    if isinstance(node, dict):
        if node.get("kind") in ("READ", "RETURN"):
            res = False
        else:
            res = all(_inert(v) for k, v in node.items() if k != "kind")
    elif isinstance(node, list):
        res = all(_inert(v) for v in node)
    _INERT_CACHE[key] = res
    return res


def _has(node, kinds) -> bool:
    if isinstance(node, dict):
        return (node.get("kind") in kinds
                or any(_has(v, kinds) for k, v in node.items() if k != "kind"))
    if isinstance(node, list):
        return any(_has(v, kinds) for v in node)
    return False


_INVISIBLE = None
_INVISIBLE_ROOT = None      # strong ref, so `is` below can never see a recycled id


def _invisible_loops(root) -> set:
    """Loops that cannot move any deck cursor, however many times they run.

    `_inert` handles the easy case. This handles the one that actually blocks
    eight cases: `do ig=1,listp_group(...)%mgroup` (Prescrib.f90:292) reads
    nothing itself but contains `goto 10`, so control leaves it — and a jump
    could in principle land before a READ. Here it cannot: label 10 and label
    20 both live inside `do igroup=1,ngroup` (Prescrib.f90:290), and that whole
    loop contains no READ at all. Whichever way the search comes out, the
    cursor is in the same place.

    So: find the nearest ancestor holding every label the loop can jump to. If
    that ancestor's subtree reads nothing, the loop is invisible and an
    underivable trip count (`mgroup` is built from the mesh, Global.f90:1340)
    does not need to be decided. If a label is not in the tree at all, the loop
    is NOT invisible — an unknown destination is not a safe one.
    """
    global _INVISIBLE, _INVISIBLE_ROOT
    # The index is a set of `id()`s, so it is only meaningful for the exact
    # tree object it was built from. It used to be cached on "not None", which
    # held for a single decode and broke silently the moment a second tree was
    # decoded in the same process: every node of tree #2 missed the index, so
    # every guard that should have been stepped over became a stop instead.
    # That is how one `local_p4(ipoin)/=1` — a guard whose body reads nothing —
    # came to block 14 of 21 cases in the first release-gate run, while case #1
    # (whose tree WAS the indexed one) sailed through. Worse than stale: once
    # tree #1 is collected its ids can be recycled, so the index could also
    # mark unrelated nodes invisible. Keyed on the root object now, compared by
    # identity and pinned by a strong reference so no id can be reused.
    if _INVISIBLE is not None and _INVISIBLE_ROOT is root:
        return _INVISIBLE
    out: set = set()

    def labels_in(n):
        got = set()
        if isinstance(n, dict):
            if n.get("kind") == "LABEL":
                got.add(n["label"])
            for k, v in n.items():
                if k != "kind":
                    got |= labels_in(v)
        elif isinstance(n, list):
            for v in n:
                got |= labels_in(v)
        return got

    def gotos_in(n):
        got = set()
        if isinstance(n, dict):
            if n.get("kind") == "GOTO":
                got.add(n["label"])
            for k, v in n.items():
                if k != "kind":
                    got |= gotos_in(v)
        elif isinstance(n, list):
            for v in n:
                got |= gotos_in(v)
        return got

    def holds(n, target) -> bool:
        """Is `target` somewhere inside `n`? By identity, not by value."""
        if n is target:
            return True
        if isinstance(n, dict):
            return any(holds(v, target) for k, v in n.items() if k != "kind")
        if isinstance(n, list):
            return any(holds(v, target) for v in n)
        return False

    def forward_skip_is_inert(n, stack) -> bool:
        """A forward `goto` skips a span. Does that span read?

        The `host reads nothing` test above is the right question for a jump
        whose direction is unknown, but it is far too strong for the common
        early exit:

            do jiter=1,miter          <- reads nothing
               ...
               if (converged) goto 10 <- Fem.f90:10338
            end do
        10  continue
            call load_of_mass(...)    <- and THIS reads

        Everything at or after the label runs either way, so it is irrelevant;
        only the span the jump skips can move a cursor. Walking up to the
        parent SEQ and demanding the whole thing be read-free fails here purely
        because of statements *after* the label — which is how the eigenvalue
        convergence test blocked both modal cases while being, in fact,
        perfectly decidable.

        So: find the ancestor SEQ whose body holds the target label, locate the
        child of that SEQ containing this node, and require that the child and
        every sibling up to the label read nothing. Backward jumps (label at or
        before the containing child) are rejected — the span is not bounded by
        the label then, and `_invisible_loops` is not the place to reason about
        a loop the AST does not model as one.
        """
        want = gotos_in(n.get("body", n))
        if not want:
            return False
        for anc in reversed(stack):
            if not (isinstance(anc, dict) and anc.get("kind") == "SEQ"):
                continue
            body = anc.get("body")
            if not isinstance(body, list):
                continue
            here = next((i for i, c in enumerate(body) if holds(c, n)), None)
            if here is None:
                continue
            tgt = [i for i, c in enumerate(body)
                   if isinstance(c, dict) and c.get("kind") == "LABEL"
                   and c.get("label") in want]
            if len(tgt) != len(want) or any(i <= here for i in tgt):
                continue          # label missing, or the jump goes backwards
            return not _has(body[here:min(tgt)], ("READ",))
        return False

    def walk(n, stack):
        if isinstance(n, dict):
            if n.get("kind") in ("LOOP", "IF"):
                body = n.get("body", n)
                if not _has(body, ("READ", "RETURN")):
                    want = gotos_in(body)
                    host = None
                    for anc in reversed(stack):
                        if want <= labels_in(anc):
                            host = anc
                            break
                    if (host is not None and not _has(host, ("READ",))) \
                            or forward_skip_is_inert(n, stack):
                        out.add(id(n))
            for k, v in n.items():
                if k != "kind":
                    walk(v, stack + [n])
        elif isinstance(n, list):
            for v in n:
                walk(v, stack)

    walk(root, [])
    _INVISIBLE, _INVISIBLE_ROOT = out, root
    return out


def _at(where: str, line) -> str:
    return f"{where}:{line}" if where else f"L{line}"


def _where_of(call) -> str:
    """`Load.f90/external_load_1` for a CALL, from its first READ."""
    r = _first_read(call.get("body"))
    sub = call.get("callee") or ""
    f = r["file"] if r else ""
    return f"{f}/{sub}" if f and sub else (f or sub)


def decode(tree, cursors: dict, env: dict, trace: list, stop: list,
           guards=(), depth=0, assumed=None, where=""):
    """Walk the AST, consuming from the real files. Stops at the first
    undecidable point rather than guessing past it.

    `where` carries the enclosing subroutine and its file. Only READ nodes
    record a file, so without it every guard and loop stop reported a bare
    line number — and `L1715` exists in four of the sixteen source files,
    which cost real time to disambiguate by hand.
    """
    if stop:
        return
    if _INVISIBLE_ROOT is not tree and depth == 0:
        _invisible_loops(tree)      # (re)index against THIS tree object
    k = tree.get("kind")
    if k == "SEQ":
        body, i = tree["body"], 0
        while i < len(body):
            try:
                decode(body[i], cursors, env, trace, stop, guards, depth, assumed, where)
            except _Goto as g:
                j = next((x for x, c in enumerate(body)
                          if isinstance(c, dict) and c.get("kind") == "LABEL"
                          and c.get("label") == g.label), None)
                if j is None:
                    raise                    # the label is in an outer scope
                if j <= i:
                    # A backward jump is a loop whose trip count is not in the
                    # tree. Stopping is the only honest answer.
                    stop.append({"why": f"backward goto {g.label} (loop, trip "
                                        f"count not derivable)",
                                 "at": _at(where, g.line), "deck": None, "vars": []})
                    return
                i = j + 1
                continue
            if stop:
                return
            i += 1
    elif k == "CALL":
        if "body" in tree:
            sub_where = _where_of(tree) or where
            try:
                decode(tree["body"], cursors, env, trace, stop, guards, depth, assumed,
                       sub_where)
            except _Returned:
                pass                     # the callee returned; carry on after it
            except _Goto as g:
                # A Fortran jump cannot leave its scoping unit, so reaching the
                # CALL boundary means the target was never emitted into the
                # tree (it sits on a pruned branch). Stop; do not fall through.
                stop.append({"why": f"goto {g.label}: target label not in the "
                                    f"tree for this subroutine",
                             "at": _at(where, g.line), "deck": None, "vars": []})
    elif k == "READ":
        cur = cursors.get(tree["deck"])
        if cur is None:
            return                       # this deck file is absent: skip
        # Item-by-item, binding as we go. A single READ can size a later
        # array from a value read EARLIER IN THE SAME STATEMENT — e.g.
        #   ftcrack, …, nlocalbeam, ndimnrt, listglocbeam(1:nlocalbeam), …
        # Evaluating the whole arity up front cannot work there, and that
        # record is exactly the one the RC-bond case fails on: nlocalbeam=1
        # is what turns the 8-field ftcrack row into 9 fields.
        li0, pos0 = cur.li, cur.pos
        is_label = len(tree["vars"]) == 1 and norm_name(tree["vars"][0]) == "text"
        stamp = getattr(cur, "stamp", None)
        if not is_label and stamp:
            why = version_mismatch(stamp, tree["vars"])
            if why:
                stop.append({"why": why, "at": f"{tree['file']}:{tree['line']}",
                             "deck": tree["deck"], "vars": tree["vars"]})
                return
        got, n = [], 0
        for v in tree["vars"]:
            m = re.search(r"\(\s*1\s*:\s*([^,)]+)", v)
            m2 = re.match(r"^\(.*,\s*\w+\s*=\s*[^,]+,\s*([^)]+)\)$", v.strip())
            expr = m.group(1) if m else (m2.group(1) if m2 else None)
            # An `allocate` executed on this decode path proves array-ness by
            # itself — `props(imat)%heat%alfa` (Material.f90:971/972) is
            # allocated (ndimn) and read bare, but read nowhere else with a
            # section, so ARRAYS cannot know it. Treating it as one item
            # under-consumed ndimn-1 fields and misbound everything after
            # (pipe_cooling read a coordinate), exhausting the file at
            # water_curve. Element/section reads keep a "(" in the last
            # component and are excluded.
            alloc_proven = (expr is None
                            and "(" not in v.split("%")[-1]
                            and norm_name(v) in env.get("__alloc__", {}))
            if expr is None and (alloc_proven or is_whole_array_read(v)):
                # The extent comes from the most recent `allocate` of this name
                # (ALLOC nodes), evaluated here against what the deck has bound
                # so far. No allocate on record, or an extent that will not
                # evaluate, still STOPS — falling back to "one item" is what
                # silently slid the cursor 1000 items on a seismic curve.
                alloc = env.get("__alloc__", {}).get(norm_name(v))
                why = None
                if alloc is None:
                    secs = ", ".join(sorted(ARRAYS.get(norm_name(v), ())))
                    why = (f"whole-array read of `{v}`: no `allocate` for it has "
                           f"been seen on this path, so its extent is unknown. "
                           f"It is read elsewhere as ({secs}), which proves it "
                           f"is an array but not how long it is here")
                else:
                    try:
                        expr = str(evaluate(alloc, env))
                    except Undecidable as u:
                        why = (f"whole-array read of `{v}`: allocated as "
                               f"`{alloc}`, which does not evaluate ({u.why})")
                if why:
                    cur.li, cur.pos = li0, pos0
                    stop.append({"why": why,
                                 "at": f"{tree['file']}:{tree['line']}",
                                 "deck": tree["deck"], "vars": tree["vars"]})
                    return
            try:
                cnt = evaluate(expr, env) if expr else 1
            except Undecidable as u:
                cur.li, cur.pos = li0, pos0
                stop.append({"why": f"arity: {u.why}",
                             "at": f"{tree['file']}:{tree['line']}",
                             "deck": tree["deck"], "vars": tree["vars"]})
                return
            if cnt < 0:
                cnt = 0
            piece = cur.read_items(cnt)
            if len(piece) < cnt:
                stop.append({"why": f"file exhausted: needed {cnt} for `{v}`",
                             "at": f"{tree['file']}:{tree['line']}",
                             "deck": tree["deck"], "vars": tree["vars"]})
                return
            bind(env, [v], piece)
            got += piece
            n += cnt
        # A label record stamps the record that follows it; anything else
        # clears the stamp, so it is never applied to a distant READ.
        cur.stamp = (label_names(cur.lines[li0])
                     if is_label and li0 < len(cur.lines) else None)
        cur.end_statement()
        trace.append({"deck": tree["deck"], "at": f"{tree['file']}:{tree['line']}",
                      "arity": n, "vars": tree["vars"], "values": got,
                      "line_in_deck": cur.li,
                      "assumed": bool(assumed)})
    elif k == "RETURN":
        raise _Returned
    elif k == "ALLOC":
        # `allocate(tcurves(itcurve)%dfact_curve(ntime))` is the only place the
        # length of a whole-array READ is stated. Kept as the EXPRESSION, not a
        # number: it is evaluated at the moment of the read, against whatever
        # the deck has bound by then.
        env.setdefault("__alloc__", {})[norm_name(tree["name"])] = tree.get("extent")
    elif k == "GOTO":
        if tree.get("label") is None:
            # A computed goto, `goto (10,20,30), i`. The destination is a
            # runtime index; nothing static resolves it.
            stop.append({"why": "computed goto: destination is a runtime index",
                         "at": _at(where, tree["line"]), "deck": None, "vars": []})
            return
        raise _Goto(tree["label"], tree["line"])
    elif k == "CYCLE":
        # `if(ecwpipe/=1) cycle` (Temper.f90:79) skips the two `.tem` reads
        # below it on every iteration. Like RETURN and GOTO, an early exit is
        # part of the read protocol, not control-flow noise.
        raise _Cycle
    elif k == "EXIT":
        raise _Exit
    elif k == "LABEL":
        pass                                 # a jump target; nothing is read
    elif k == "ASSIGN":
        lhs, rhs = norm_name(tree["lhs"]), tree["rhs"].strip()
        if re.fullmatch(r"'[^']*'|\"[^\"]*\"", rhs):
            env[lhs] = rhs.strip("'\"")          # a character literal
        elif (re.fullmatch(r"[A-Za-z_]\w*(?:\([^()]*\))?(?:%\w+(?:\([^()]*\))?)*", rhs)
                and norm_name(rhs) in env):
            # A plain name-to-name copy, whatever the type. The arithmetic
            # evaluator only knows numbers, so without this
            # `criteria = props(imat)%mechanical%solid%ClassicalEP%criteria`
            # (Material.f90:600) left `criteria` unbound and every yield
            # criterion guard below it undecidable.
            env[lhs] = env[norm_name(rhs)]
        else:
            try:
                env[lhs] = evaluate(rhs, env)
            except Undecidable:
                # An assignment can be the only path from a declared assumption
                # to the value a later loop bound needs: `blks_new = lblks+1`
                # (Fem.f90:303) sits between the assumed `lblks` and
                # `do iblks=1,blks_new-1`. Assumptions fired here are recorded
                # in `assumed` exactly as they are in a guard, so the record
                # still comes out marked.
                here = _at(where, tree.get("line"))
                if any(apply_assumption(n, env,
                                        assumed if assumed is not None else [],
                                        here)
                       for n in re.findall(r"[A-Za-z_]\w*", rhs)):
                    try:
                        env[lhs] = evaluate(rhs, env)
                    except Undecidable:
                        pass
                else:
                    pass  # not knowable yet, or not numeric: leave unbound
    elif k == "IF":
        from case_path import eval_guard, UNKNOWN
        chosen = None
        for b in tree["branches"]:
            if b["guard"] == "else":
                continue
            v = eval_guard(b["guard"], env)
            if v is UNKNOWN:
                names = re.findall(r"[A-Za-z_]\w*", b["guard"])
                here = _at(where, tree["line"])
                fired = [n for n in names
                         if apply_assumption(n, env,
                                             assumed if assumed is not None else [],
                                             here)]
                if fired:
                    v = eval_guard(b["guard"], env)
                # A position-scoped assumption answers this guard and nothing
                # else; drop it again so it cannot leak into a later use of the
                # same name.
                for n in fired:
                    if scoped_assumption(n):
                        env.pop(n.lower(), None)
                if v is UNKNOWN:
                    if id(tree) in (_INVISIBLE or set()):
                        return    # nothing under this branch reads: skip it
                    stop.append({"why": f"undecidable guard: {b['guard'][:80]}",
                                 "at": _at(where, tree['line']), "deck": None, "vars": []})
                    return
            if v:
                chosen = b
                break
        if chosen is None:
            if not any(b["guard"] != "else" for b in tree["branches"]):
                # Every non-else branch was pruned away (they read no deck), so
                # the guard that would send us AROUND the else is not in the
                # tree. Taking the else unconditionally is a guess, and it is a
                # guess that reads: `if (water/=0)` at Load.f90:788 computes the
                # pressure with no READ, while its else reads one record per
                # edge. Falling into the else consumed four `.loa` records the
                # solver never touches.
                stop.append({"why": "if/else whose non-else guard was pruned "
                                    "from the tree (its branch reads no deck); "
                                    "cannot tell whether the else runs",
                             "at": _at(where, tree["line"]), "deck": None,
                             "vars": []})
                return
            chosen = next((b for b in tree["branches"] if b["guard"] == "else"), None)
        if chosen:
            decode(chosen["body"], cursors, env, trace, stop,
                   guards + (chosen["guard"],), depth + 1, assumed, where)
    elif k == "SELECT":
        from case_path import eval_guard, UNKNOWN
        # `case default` is a fall-through, not a value to compare against.
        # Comparing `type_curve=='default'` makes it permanently false, and a
        # SELECT where nothing matches silently reads nothing — which leaves the
        # cursor one record behind and mis-assigns everything after it. That is
        # exactly how `LINEAR` (which has no named case) desynchronised `.loa`.
        default = None
        for c in tree["cases"]:
            if c["value"].strip("()").strip().lower() == "default":
                default = c
                continue
            g = f'{tree["expr"]}=={c["value"].strip("()")}'
            v = eval_guard(g, env)
            if v is UNKNOWN:
                stop.append({"why": f"undecidable case: {g[:80]}",
                             "at": _at(where, tree['line']), "deck": None, "vars": []})
                return
            if v:
                decode(c["body"], cursors, env, trace, stop, guards + (g,),
                       depth + 1, assumed, where)
                return
        if default is not None:
            decode(default["body"], cursors, env, trace, stop,
                   guards + (f'{tree["expr"]}: default',), depth + 1, assumed, where)
    elif k == "LOOP":
        wm = re.match(r"\s*while\s*\((.*)\)\s*$", tree["bounds"], re.I)
        if wm:
            from case_path import eval_guard, UNKNOWN
            for _ in range(100000):          # backstop against a mis-parsed body
                v = eval_guard(wm.group(1), env)
                if v is UNKNOWN:
                    stop.append({"why": f"do-while condition: {wm.group(1)[:70]}",
                                 "at": _at(where, tree['line']), "deck": None, "vars": []})
                    return
                if not v:
                    return
                before = len(trace)
                try:
                    decode(tree["body"], cursors, env, trace, stop, guards,
                           depth + 1, assumed, where)
                except _Cycle:
                    pass
                except _Exit:
                    return
                if stop:
                    return
                if len(trace) == before:
                    stop.append({"why": "do-while made no progress",
                                 "at": _at(where, tree['line']), "deck": None, "vars": []})
                    return
            return
        m = re.match(r"\s*(\w+)\s*=\s*(.+?)\s*,\s*(.+?)\s*$", tree["bounds"])
        if not m:
            stop.append({"why": f"loop bounds `{tree['bounds'][:60]}`",
                         "at": _at(where, tree['line']), "deck": None, "vars": []})
            return
        var, lo_e, hi_e = m.group(1).lower(), m.group(2), m.group(3)
        try:
            lo, hi = evaluate(lo_e, env), evaluate(hi_e, env)
        except Undecidable:
            for nm in re.findall(r"[A-Za-z_]\w*", lo_e + " " + hi_e):
                apply_assumption(nm, env, assumed if assumed is not None else [])
            try:
                lo, hi = evaluate(lo_e, env), evaluate(hi_e, env)
            except Undecidable as u:
                if _inert(tree["body"]) or id(tree) in (_INVISIBLE or set()):
                    return            # cannot move any cursor: skip it
                stop.append({"why": f"loop bounds: {u.why}", "at": _at(where, tree['line']),
                             "deck": None, "vars": []})
                return
        for i in range(lo, hi + 1):
            env[var] = i
            try:
                decode(tree["body"], cursors, env, trace, stop, guards,
                       depth + 1, assumed, where)
            except _Cycle:
                continue
            except _Exit:
                return
            if stop:
                return


def absent_decks(case_dir) -> list:
    """Deck files the solver opens that this case does not have.

    A missing file makes the decoder skip that deck's READs, which later shows
    up as an unbound name far away from the cause — so say it at the top. The
    case-differing sibling is worth calling out on its own: the solver opens
    `probn//'.loa'` literally, and on a case-sensitive filesystem a case that
    ships only `1.LOA` gets an empty `1.loa` created by the `open` and fails on
    the first read. Two cases in the suite are exactly that.
    """
    out = []
    have = {f.name.lower(): f.name for f in case_dir.iterdir()} if case_dir.exists() else {}
    for deck, fname in sorted(DECK_FILE.items()):
        if (case_dir / fname).exists():
            continue
        alt = have.get(fname.lower())
        if alt:
            # Only the case-differing sibling is reported. Most of the 23 decks
            # are legitimately absent from any given case, and listing all of
            # them would bury the one that is a real defect.
            out.append(f"{fname} 不存在，但有同名不同大小写的 {alt}；"
                       f"求解器按字面名 open，{deck} 的 READ 全部跳过")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--deck")
    ap.add_argument("--values", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()

    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from case_path import switches_from_deck    # noqa: F401  (env seeding aid)

    d = CASES / a.case
    cursors = {k: Cursor(path=d / v) for k, v in DECK_FILE.items() if (d / v).exists()}
    ast_ = json.load(open(ROOT / "data" / "deck-ast.json"))

    env: dict = {}
    trace: list = []
    stop: list = []
    used: list = []
    try:
        decode(ast_["trees"][ast_["driver"]], cursors, env, trace, stop, assumed=used)
    except _Returned:
        pass

    per: dict = {}
    for t in trace:
        per.setdefault(t["deck"], []).append(t)

    print(f"算例 {a.case}")
    print(f"解码记录 {len(trace)} 条；绑定变量 {len(env)} 个")
    for k in sorted(per):
        cur = cursors[k]
        pct = 100 * cur.li / max(len(cur.lines), 1)
        print(f"   {k:<5} {len(per[k]):4d} 条   游标行 {cur.li}/{len(cur.lines)} ({pct:.0f}%)"
              + ("  EOF" if cur.at_eof() else ""))
    if used:
        print(f"   （用到声明的假设: {', '.join(used)}）")
    for note in absent_decks(d):
        print(f"   ⚠ {note}")
    if stop:
        s = stop[0]
        print(f"\n停在: {s['at']}  ({s['deck'] or '-'})")
        print(f"   原因: {s['why']}")
        if s["vars"]:
            print(f"   该记录变量: {', '.join(s['vars'])[:100]}")
    else:
        print("\n走完整棵树，未遇到不可判定点")

    for key in ("npoin", "nelem", "ndimn", "nmats", "ngroup", "nblks",
                "type_problem", "type_solver", "type_abc", "mdofn"):
        if key in env:
            print(f"   {key:<14} = {env[key]}")

    if a.values:
        show = per.get(a.deck) if a.deck else trace
        print(f"\n{'解码流':─^70}")
        for t in (show or [])[:40]:
            v = " ".join(t["values"])[:60]
            print(f"  {t['deck']:<5} [{t['arity']:>4}] {', '.join(t['vars'])[:44]:<44} = {v}")
    if a.json:
        Path(a.json).write_text(json.dumps(
            {"case": a.case, "trace": trace, "stop": stop,
             "env": {k: v for k, v in env.items() if not isinstance(v, list)}},
            indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
