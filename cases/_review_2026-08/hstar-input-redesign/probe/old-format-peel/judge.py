#!/usr/bin/env python3
"""Probe: peel the old-format deck one record at a time (pre-registered).

Method (registered before running): run → locate the failing record from the
label the solver echoed just before the error → align that label's names
against the source READ's variable list → insert 0 for every variable the old
label lacks → run again. At most 8 rounds.

Locator mechanism: the solver echoes each label record to stdout as it reads
it, so the last echoed label before `forrtl` names the record that failed.

Carried over from probe `old-loa`, where P1 passed for the wrong reason: the
outcome class carries the FILE and the RECORD, not just "read_error". A class
that cannot distinguish "failed in .glb" from "failed in .loa" lets a
prediction about .loa pass on a .glb failure.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/home/huijun/HSTAR_Next")
CASES = REPO / "cases" / "cases"
SRC = REPO / "hstarYLOrig" / "HSTAR"
SOLVE = REPO / "fem-chat" / "harness" / "_solve_deck.py"
WORK = Path("/tmp/claude-1000/probe-peel")

TARGET = "train_contact_nonlinear"
OTHERS = ["train_seepage", "train_seepage_stress", "train_slope_unknown",
          "train_vie_boundary"]
CONTROL = "train01_gravdam_static"
MAX_ROUNDS = 8
TIMEOUT = 600

RE_FORRTL = re.compile(r"forrtl:\s*severe\s*\((\d+)\):\s*(.*?),\s*unit\s*\d+,\s*file\s*(\S+)", re.I)
OUTPUT_DROP = (".chk", ".res", ".flavia.res", ".flavia.msh", ".vtp", ".vtu", ".pvd")


def stage(case: str, into: Path) -> Path:
    src = CASES / case
    if into.exists():
        shutil.rmtree(into)
    into.mkdir(parents=True)
    for p in sorted(src.iterdir()):
        if p.is_file():
            shutil.copy2(p, into / p.name)
    for p in list(into.iterdir()):
        if p.name.endswith(OUTPUT_DROP):
            p.unlink()
    return into


def run(d: Path) -> dict:
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, str(SOLVE), "."], cwd=d,
                           capture_output=True, text=True, timeout=TIMEOUT)
        out, code, to = (r.stdout or "") + (r.stderr or ""), r.returncode, False
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace")
               + (e.stderr or b"").decode("utf-8", "replace"))
        code, to = None, True
    secs = round(time.time() - t0, 1)
    res = d / "1.flavia.res"
    size = res.stat().st_size if res.exists() else 0

    if to:
        return {"class": "timeout", "seconds": secs, "out": out}
    m = RE_FORRTL.search(out)
    if m:
        fname = Path(m.group(3)).name
        label = last_label(out, m.start())
        return {"class": f"read_error@{fname}:{label or '?'}", "seconds": secs,
                "severe": m.group(1), "reason": m.group(2).strip(),
                "file": fname, "label": label, "out": out}
    if code == 0 and size > 0:
        return {"class": "completed", "seconds": secs, "res_bytes": size, "out": out}
    return {"class": "other_error", "seconds": secs, "exit": code, "out": out}


def last_label(out: str, before: int) -> str | None:
    """Last echoed label line before the error. Labels are the non-numeric,
    multi-word records the solver prints as it consumes them."""
    for line in reversed(out[:before].splitlines()):
        s = line.strip().strip("'\"")
        if not s or s.lower().startswith(("time:", "forrtl", "image", "hstar", "libc")):
            continue
        toks = [t for t in re.split(r"[,\s]+", s) if t]
        if len(toks) < 2:
            continue
        if all(re.fullmatch(r"[-+0-9.eEdD*]+", t) for t in toks):
            continue                                  # numeric record, not a label
        return s
    return None


def names(line: str) -> list[str]:
    """Variable-ish names in a label line.

    The `!` split is not optional: a label line routinely carries a trailing
    note (`'NMASS ... nflow' !uwcpl=0,drained(w);1,undrained(u-pw);`) whose
    words are indistinguishable from variable names once tokenised. Without it
    the alignment consumes phantom names and concludes nothing is missing.
    This is the THIRD place in this project where forgetting the `!` rule
    produced a wrong answer (import_glb._Deck, the .man probe, here) — the
    strongest single argument for one shared deck decoder.
    """
    line = line.split("!", 1)[0]
    out = []
    for t in re.split(r"[,\s()/]+", line.strip().strip("'\"")):
        t = t.strip("'\"").strip()
        if t and re.fullmatch(r"[A-Za-z_]\w*", t):
            out.append(t.lower())
    return out


def source_read_vars(first_name: str, unit_hint: str) -> list[str] | None:
    """The source READ whose first variable is `first_name`, for this unit."""
    for f in sorted(SRC.glob("*.f90")):
        for raw in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(rf"read\s*\(\s*{unit_hint}\s*,\s*\*\s*\)(.*)$", raw, re.I)
            if not m:
                continue
            body = m.group(1).split("!", 1)[0]
            vs, depth, cur = [], 0, ""
            for ch in body:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                if ch == "," and depth == 0:
                    vs.append(cur.strip()); cur = ""
                else:
                    cur += ch
            if cur.strip():
                vs.append(cur.strip())
            vs = [v.strip().lower() for v in vs if v.strip()]
            if vs and vs[0].split("(")[0] == first_name:
                return vs
    return None


def alike(a: str, b: str) -> bool:
    a, b = a.split("(")[0], b.split("(")[0]
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


def patch_record(deck: Path, label_line: str, src_vars: list[str]) -> dict | None:
    """Insert 0 for every source variable the old label lacks. Returns info."""
    def key(x: str) -> str:
        # Fourth appearance of the same rule in this project. The deck line is
        # `'NMASS ... nflow' !uwcpl=0,...` while the solver echoes it without
        # the note, so the two only match after the `!` is cut.
        return re.sub(r"\s+", " ", x.split("!", 1)[0].strip().strip("'\"")).strip().lower()

    lines = deck.read_text(encoding="utf-8", errors="replace").splitlines()
    idx = next((i for i, l in enumerate(lines) if key(l) == key(label_line)), None)
    if idx is None or idx + 1 >= len(lines):
        return None
    old_names = names(label_line)
    data_line = lines[idx + 1]
    vals = [v for v in re.split(r"[,\s]+", data_line.split("!", 1)[0].strip()) if v]

    new_vals, oi, inserted = [], 0, []
    for sv in src_vars:
        if oi < len(old_names) and alike(sv, old_names[oi]):
            new_vals.append(vals[oi] if oi < len(vals) else "0")
            oi += 1
        else:
            new_vals.append("0")
            inserted.append(sv)
    if not inserted:
        return None
    lines[idx + 1] = "  " + "  ".join(new_vals)
    deck.write_text("\n".join(lines) + "\n")
    return {"label": label_line.strip()[:70], "src_arity": len(src_vars),
            "deck_arity": len(old_names), "inserted": inserted}


UNIT_OF = {"1.glb": "gunit", "1.loa": "loadunit", "1.man": "mainunit",
           "1.pre": "punit", "1.mat": "munit", "1.ifs": "ifsunit"}


def peel(case: str) -> dict:
    d = stage(case, WORK / f"{case}-peel")
    rounds, patches = [], []
    for n in range(MAX_ROUNDS):
        r = run(d)
        rounds.append({"round": n, "class": r["class"], "seconds": r["seconds"],
                       "reason": r.get("reason"), "label": r.get("label")})
        print(f"     round {n}: {r['class']}  ({r['seconds']}s)", flush=True)
        if not r["class"].startswith("read_error"):
            break
        fname, label = r["file"], r["label"]
        unit = UNIT_OF.get(fname.lower())
        if not (unit and label):
            rounds[-1]["patch"] = "no locator"
            break
        nm = names(label)
        sv = source_read_vars(nm[0], unit) if nm else None
        if not sv:
            rounds[-1]["patch"] = f"no source READ starting with {nm[0] if nm else '?'}"
            break
        p = patch_record(d / fname, label, sv)
        if not p:
            rounds[-1]["patch"] = "nothing to insert"
            break
        p["file"] = fname
        patches.append(p)
        rounds[-1]["patch"] = p
        print(f"        补 {fname} «{p['label'][:44]}»: "
              f"{p['deck_arity']}→{p['src_arity']} 项，插入 {p['inserted']}", flush=True)
    return {"case": case, "rounds": rounds, "patches": patches,
            "final_class": rounds[-1]["class"]}


def main():
    pp = HERE / "predictions.json"
    pred_hash = hashlib.sha256(pp.read_bytes()).hexdigest()
    print(f"predictions sha256 = {pred_hash}\n")

    print(f"控制组 {CONTROL} …", flush=True)
    ctrl = run(stage(CONTROL, WORK / CONTROL))
    print(f"   → {ctrl['class']}", flush=True)
    ctrl_ok = ctrl["class"] == "completed"

    print(f"\n剥洋葱 {TARGET}:", flush=True)
    peeled = peel(TARGET)

    print(f"\n另外 4 个 deck 的第 0 轮形态:", flush=True)
    others = {}
    for c in OTHERS:
        r = run(stage(c, WORK / c))
        others[c] = {"class": r["class"], "label": r.get("label")}
        print(f"   {c:<26} {r['class']}", flush=True)

    results = []

    def rec(pid, ok, detail):
        results.append({"id": pid, "verdict": "PASS" if ok else "FALSIFIED",
                        "detail": detail})

    rec("C0", ctrl_ok, {"control_class": ctrl["class"]})

    r0, r1 = peeled["rounds"][0], (peeled["rounds"][1] if len(peeled["rounds"]) > 1 else None)
    rec("P1", bool(r1) and (r1["label"] or "") != (r0["label"] or ""),
        {"round0": r0.get("label"), "round1": r1.get("label") if r1 else None})
    rec("P2", bool(r1) and "1.glb" in (r1["class"] or ""),
        {"round1_class": r1["class"] if r1 else None})
    glb_patches = [p for p in peeled["patches"] if p["file"].lower() == "1.glb"]
    rec("P3", len(glb_patches) >= 2, {"glb_patch_count": len(glb_patches),
                                      "patches": glb_patches})
    rec("P4", any("1.loa" in (x["class"] or "").lower() for x in peeled["rounds"]),
        {"classes": [x["class"] for x in peeled["rounds"]]})
    rec("P5", not any(x["class"] == "completed" for x in peeled["rounds"]),
        {"classes": [x["class"] for x in peeled["rounds"]]})
    rec("P6", all(o["class"] == r0["class"] for o in others.values()),
        {"target_round0": r0["class"],
         "others": {k: v["class"] for k, v in others.items()}})

    verdict = {"probe_id": "old-format-peel-v1", "predictions_sha256": pred_hash,
               "control_ok": ctrl_ok, "target": peeled, "others": others,
               "results": results}
    (HERE / "verdict.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False))

    print()
    if not ctrl_ok:
        print("  C0  FALSIFIED —— 控制组未通过，其余结果不得解读。")
    else:
        for r in results:
            print(f"  {r['id']}  {r['verdict']}")
        n = sum(r["verdict"] == "PASS" for r in results)
        print(f"\n{n}/{len(results)} 成立")
    print(f"详见 {HERE/'verdict.json'}")


if __name__ == "__main__":
    main()
