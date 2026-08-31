#!/usr/bin/env python3
"""Round-trip capability matrix.

For every case directory: import the hand-authored deck back into a config,
regenerate the deck from that config, and diff the two.  What the diff loses
is exactly what the generator cannot express.

Nothing here judges physics.  A file that comes back byte-equivalent means
the toolchain can author that file; anything else is a capability boundary.
"""
import difflib
import json
import shutil
import sys
import traceback
from pathlib import Path

REPO = Path("/home/huijun/HSTAR_Next")
sys.path.insert(0, str(REPO / "fem-chat" / "skills"))
CASES = REPO / "cases" / "cases"
WORK = Path("/tmp/claude-1000/roundtrip/matrix")

# Files the generator is supposed to author.  Mesh files (1.cor/1.ele) are
# inputs on both sides, so they are excluded by construction.
DECK_FILES = ["1.glb", "1.man", "1.mat", "1.LOA", "1.pre", "1.ifs"]


def tokens(path):
    """Whitespace-token stream per line, numbers normalised so 1.0e6 == 1000000."""
    out = []
    for raw in path.read_bytes().decode("utf-8", "replace").splitlines():
        row = []
        for t in raw.split():
            try:
                row.append(f"{float(t):.6g}")
            except ValueError:
                row.append(t)
        if row:
            out.append(" ".join(row))
    return out


def semantic_diff(name, orig, regen):
    """For the two files we have a grammar for, compare what the solver READS.

    A text diff counts `10*0` against `0 0 0 0 0`, and a node list wrapped at
    8 per line against the same list on one line. Fortran reads both pairs
    identically, so those are formatting, not loss — and reporting them as
    loss would send the next person hunting for a bug that isn't there.
    Returns True/False, or None when there is no parser for this file.
    """
    import import_glb
    try:
        if name == "1.pre":
            return import_glb.parse_pre(orig)[::3] == import_glb.parse_pre(regen)[::3]
        if name == "1.LOA":
            a, b = import_glb.parse_loa(orig), import_glb.parse_loa(regen)
            if a.get("unsupported"):
                return None
            return a == b
    except Exception:
        return False
    return None


def diff_file(orig, regen):
    if not regen.exists():
        return {"status": "not-generated", "lines": len(tokens(orig))}
    a, b = tokens(orig), tokens(regen)
    if a == b:
        return {"status": "identical", "lines": len(a)}
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changed, samples = 0, []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        changed += max(i2 - i1, j2 - j1)
        if len(samples) < 4:
            samples.append({
                "op": tag,
                "orig": a[i1:i2][:2],
                "regen": b[j1:j2][:2],
            })
    return {"status": "differs", "lines": len(a), "changed": changed,
            "ratio": round(1 - sm.ratio(), 3), "samples": samples}


def roundtrip(case):
    src = CASES / case
    if not (src / "1.glb").exists():
        return {"case": case, "skip": "no 1.glb"}
    work = WORK / case
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    for name in ("1.cor", "1.ele"):
        if (src / name).exists():
            shutil.copy2(src / name, work / name)

    rec = {"case": case, "files": {}}
    try:
        import import_glb
        # import_project returns {"config": …, "summary": …}; the generator
        # takes the config alone. Handing it the wrapper does not raise — every
        # key simply misses and the deck comes out all-defaults, which is
        # indistinguishable from "the schema cannot express this case".
        cfg = import_glb.import_project(str(src))["config"]
    except Exception as exc:
        rec["import_error"] = f"{type(exc).__name__}: {exc}"
        return rec
    (work / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    rec["config_keys"] = sorted(cfg.keys())

    try:
        import generator
        generator.generate_all(str(work), cfg)
    except Exception as exc:
        rec["generate_error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc(limit=3)

    for name in DECK_FILES:
        o = src / name
        if not o.exists():
            continue
        d = diff_file(o, work / name)
        if d["status"] == "differs":
            sem = semantic_diff(name, o, work / name)
            if sem is not None:
                d["semantic_equal"] = sem
        rec["files"][name] = d
    return rec


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(
        p.name for p in CASES.iterdir()
        if p.is_dir() and p.name.startswith("train") and (p / "1.glb").exists()
    )
    results = [roundtrip(n) for n in names]
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "matrix.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))

    w = max(len(r["case"]) for r in results) + 2
    print(f"{'case':<{w}}" + "".join(f"{n:<10}" for n in DECK_FILES))
    for r in results:
        cells = []
        for n in DECK_FILES:
            f = r["files"].get(n)
            if f is None:
                cells.append("—")
            elif f["status"] == "identical":
                cells.append("OK")
            elif f["status"] == "not-generated":
                cells.append("MISSING")
            elif f.get("semantic_equal") is True:
                cells.append("OK~")          # same values, different formatting
            else:
                cells.append(f"{f['changed']}L")
        note = r.get("import_error") or r.get("generate_error") or r.get("skip") or ""
        print(f"{r['case']:<{w}}" + "".join(f"{c:<10}" for c in cells) + ("  " + note if note else ""))
    print(f"\n{WORK / 'matrix.json'}")
