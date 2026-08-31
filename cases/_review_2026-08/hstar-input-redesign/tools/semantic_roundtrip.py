#!/usr/bin/env python3
"""Read-back, judged on bound values instead of on text.

`roundtrip_matrix.py` compares the regenerated deck to the original line by
line. That was the honest first instrument, but it over-reports, and this
project now has proof: `train02_gravdam_seismic` writes

    0  0  0  0  0  0  0  0        (original)
    0  2                          (generated)

for `group%order_time`, and `Global.f90:1131` reads exactly ONE item there. The
Fortran record-tail rule discards the rest, so both decks bind `order_time = 0`.
A textual diff calls that a difference; the solver cannot tell them apart.

The question condition 3 actually asks is *does the solver see the same deck*,
and the Deck ABI decoder answers it directly: walk both decks and compare the
`(position, variables, values)` the READs bind. A difference here is real by
construction — it is a value the solver would consume differently.

Per case:

    import_glb  ->  config  ->  generate  ->  decode  ==  decode(original)?

Cases with no `config.json` are exactly the ones this is for: the import step
is what a legacy deck is missing, and this measures whether that import is
faithful enough to stand in for the deck.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
FEMCHAT = RESEARCH.parent.parent.parent   # …/fem-chat
CASES = FEMCHAT.parent / "cases" / "cases"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FEMCHAT / "skills"))

MESH = ("1.cor", "1.ele")

# --dump-only-in-orig: additionally record WHICH (at, vars) keys the original
# deck's decode binds that the regenerated decode does not (and the reverse).
# Purely additive debug output — the summary numbers do not change.
DUMP_ONLY = False


def _decode(case_dir: Path):
    from decoder import Cursor, decode, DECK_FILE
    tree = json.loads((RESEARCH / "data" / "deck-ast.json").read_text())
    tree = tree["trees"][tree["driver"]]
    cur = {k: Cursor(path=case_dir / v)
           for k, v in DECK_FILE.items() if (case_dir / v).exists()}
    env, trace, stop, used = {}, [], [], []
    try:
        decode(tree, cur, env, trace, stop, assumed=used)
    except Exception as exc:                                   # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    return trace, (stop[0]["why"][:60] if stop else None)


def _key(rec):
    return (rec.get("at"), tuple(rec.get("vars") or ()))


def _same(a, b) -> bool:
    """Do these two bound values reach the solver as the same thing?

    Deck values are kept as strings because a record can mix `2 LINEAR 0 2`,
    but `'0'` and `'0.0'` are the same number and Fortran reads both into the
    same REAL. Comparing as strings reported a difference on every single case
    (`ttime_curve` is `0 1` in a hand deck and `0.0 1.0` from the generator)
    and buried the differences that matter under noise.
    """
    if a is None or b is None:
        return a == b
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        try:
            if float(x) == float(y):
                continue
        except (TypeError, ValueError):
            pass
        return False
    return True


def compare(case: str) -> dict:
    src = CASES / case
    out = {"case": case}
    if not (src / "1.glb").exists():
        return {**out, "status": "no-deck"}

    # 1. import the deck into a config
    r = subprocess.run([sys.executable, str(FEMCHAT / "skills" / "import_glb.py"),
                        str(src)], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return {**out, "status": "import-failed", "detail": r.stderr[-200:]}
    try:
        cfg = json.loads(r.stdout)["config"]
    except Exception as exc:                                   # noqa: BLE001
        return {**out, "status": "import-unparsable", "detail": str(exc)[:150]}

    # 2. regenerate from it, on the same mesh
    tmp = Path(tempfile.mkdtemp(prefix=f"srt-{case}-"))
    try:
        for m in MESH:
            if (src / m).exists():
                shutil.copy2(src / m, tmp / m)
        for extra in ("gravdam_meta.json",):
            if (src / extra).exists():
                shutil.copy2(src / extra, tmp / extra)
        from generator import generate_all
        try:
            generate_all(str(tmp), cfg)
        except Exception as exc:                               # noqa: BLE001
            return {**out, "status": "generate-failed",
                    "detail": f"{type(exc).__name__}: {exc}"[:180]}

        # 3. decode both and compare what the READs bind
        a, stop_a = _decode(src)
        b, stop_b = _decode(tmp)
        if a is None or b is None:
            return {**out, "status": "decode-error", "detail": stop_a or stop_b}

        # `text` reads land in a throwaway CHARACTER variable — they are the
        # deck's own header/annotation lines, not data. A generator that writes
        # `MDOFN` where the hand deck writes `MDOFN(/Ux Uy Uz Thxy …)` has
        # changed a comment, not the problem. Counted, but kept apart: mixing
        # them in made 34 `.mat` COMMENT lines the single largest "difference"
        # in the corpus and buried the ones that change the physics.
        diffs, annot, only_a, only_b = [], [], 0, 0
        only_a_keys: list = []
        ib = {}
        for rec in b:
            ib.setdefault(_key(rec), []).append(rec)
        seen: dict = {}
        for rec in a:
            k = _key(rec)
            n = seen.get(k, 0)
            seen[k] = n + 1
            cand = ib.get(k, [])
            if n >= len(cand):
                only_a += 1
                if DUMP_ONLY:
                    only_a_keys.append({"at": k[0], "vars": list(k[1])[:4],
                                        "values": (rec.get("values") or [])[:10]})
                continue
            va, vb = rec.get("values"), cand[n].get("values")
            if not _same(va, vb):
                item = {"at": k[0], "vars": list(k[1])[:4],
                        "orig": va[:14] if va else va,
                        "gen": vb[:14] if vb else vb}
                (annot if list(k[1]) == ["text"] else diffs).append(item)
        only_b = max(0, len(b) - len(a))
        res = {**out, "status": "compared", "records": len(a),
               "records_gen": len(b), "value_diffs": len(diffs),
               "annotation_diffs": len(annot),
               "only_in_orig": only_a, "only_in_gen": only_b,
               "stop_orig": stop_a, "stop_gen": stop_b,
               "diffs": diffs[:40], "annotations": annot[:10]}
        if DUMP_ONLY:
            res["only_in_orig_keys"] = only_a_keys[:80]
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    global DUMP_ONLY
    argv = [a for a in sys.argv[1:] if a != "--dump-only-in-orig"]
    DUMP_ONLY = len(argv) != len(sys.argv[1:])
    sys.argv[1:] = argv
    names = sys.argv[1:] or sorted(
        p.name for p in CASES.iterdir()
        if p.is_dir() and p.name.startswith("train") and (p / "1.glb").exists())
    rows = [compare(n) for n in names]
    w = max(len(r["case"]) for r in rows) + 2
    print(f"{'case':<{w}}{'状态':<16}{'记录':>6}{'数据不同':>9}{'注释不同':>9}"
          f"{'仅原始':>7}{'仅生成':>7}")
    for r in rows:
        if r["status"] != "compared":
            print(f"{r['case']:<{w}}{r['status']:<16}"
                  f"  {str(r.get('detail',''))[:60]}")
            continue
        print(f"{r['case']:<{w}}{'已对比':<16}{r['records']:>6}"
              f"{r['value_diffs']:>9}{r['annotation_diffs']:>9}"
              f"{r['only_in_orig']:>7}{r['only_in_gen']:>7}")
    ok = [r for r in rows if r["status"] == "compared" and r["value_diffs"] == 0
          and r["only_in_orig"] == 0 and r["only_in_gen"] == 0]
    print(f"\n语义上完全一致：{len(ok)}/{len(rows)}")
    out = RESEARCH / "data" / "semantic-roundtrip.json"
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(out)


if __name__ == "__main__":
    main()
