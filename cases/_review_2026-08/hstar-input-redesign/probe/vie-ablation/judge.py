#!/usr/bin/env python3
"""Mechanical judge for probe vie-ablation (open #2).

Verifies the pre-registration hash, extracts metrics from the seven sandbox
runs, and emits verdict.json. Claude does not participate in the judging: every
criterion below is a direct transcription of the falsified_if strings in
predictions.json.

Usage:  python3 judge.py            # writes verdict.json next to this file
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path("/tmp/claude-1000/probe-vie")
CASES = Path("/home/huijun/HSTAR_Next/cases/cases")

RUN_CASE = {
    "t10_base": "train10_dynamic_vie",
    "t10_base_rep": "train10_dynamic_vie",
    "t10_var": "train10_dynamic_vie",
    "t02_on": "train02_gravdam_seismic",
    "t02_off": "train02_gravdam_seismic",
    "vie_base": "vie",
    "vie_var": "vie",
}

FACHV_RE = re.compile(rb"fachv=\s*(\S+)\s+(\S+)")


# ---------------------------------------------------------------- extraction

def check_hash() -> str:
    digest = hashlib.sha256((HERE / "predictions.json").read_bytes()).hexdigest()
    recorded = (HERE / "predictions.sha256").read_text().split()[0]
    if digest != recorded:
        raise SystemExit(
            f"ABORT: predictions.json has been modified.\n"
            f"  recorded {recorded}\n  actual   {digest}"
        )
    return digest


def probe_node(case: str) -> int:
    """Node with maximum y; ties broken by minimum x."""
    pts = []
    for line in (CASES / case / "1.cor").read_bytes().decode("latin-1").splitlines():
        p = line.split()
        if len(p) >= 3:
            try:
                pts.append((int(p[0]), float(p[1]), float(p[2])))
            except ValueError:
                continue
    ymax = max(p[2] for p in pts)
    crest = [p for p in pts if p[2] == ymax]
    return min(crest, key=lambda t: t[1])[0]


def series(run: str, node: int) -> tuple[list[str], list[str]]:
    """Probe-node (ux, uy) as raw decimal strings, one per DISPLACEMENT block."""
    res = ROOT / run / "1.flavia.res"
    if not res.exists():
        return [], []
    xs: list[str] = []
    ys: list[str] = []
    in_block = False
    with res.open("rb") as fh:
        for raw in fh:
            line = raw.decode("latin-1")
            head = line.strip()
            if head.startswith("DISPLACEMENT"):
                in_block = True
                continue
            if not in_block:
                continue
            p = head.split()
            if len(p) != 3:
                in_block = False
                continue
            try:
                nid = int(p[0])
            except ValueError:
                in_block = False
                continue
            if nid == node:
                xs.append(p[1])
                ys.append(p[2])
                in_block = False
    return xs, ys


def fachv_max(run: str) -> tuple[float, float, int]:
    chk = ROOT / run / "1.chk"
    if not chk.exists():
        return float("nan"), float("nan"), 0
    m1 = m2 = 0.0
    n = 0
    for a, b in FACHV_RE.findall(chk.read_bytes()):
        n += 1
        m1 = max(m1, abs(float(a.replace(b"D", b"E"))))
        m2 = max(m2, abs(float(b.replace(b"D", b"E"))))
    return m1, m2, n


def peak(v: list[float]) -> float:
    return max(abs(x) for x in v) if v else float("nan")


def rms(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v) / len(v)) if v else float("nan")


def reldiff(a: list[float], b: list[float]) -> float:
    """max_t |a-b| / max_t |b|  (b = baseline). nan if unusable."""
    if not a or not b or len(a) != len(b):
        return float("nan")
    denom = peak(b)
    if denom == 0:
        return float("nan")
    return max(abs(x - y) for x, y in zip(a, b)) / denom


# ------------------------------------------------------------------ measure

def measure() -> dict:
    nodes = {c: probe_node(c) for c in set(RUN_CASE.values())}
    out: dict[str, dict] = {"probe_nodes": nodes, "runs": {}}
    for run, case in RUN_CASE.items():
        node = nodes[case]
        xs, ys = series(run, node)
        fx = [float(v) for v in xs]
        fy = [float(v) for v in ys]
        m1, m2, nf = fachv_max(run)
        out["runs"][run] = {
            "case": case,
            "probe_node": node,
            # instrument fix: a 0-byte 1.flavia.res is written before an early
            # solver abort, so existence alone is not "solved".
            "solved": (ROOT / run / "1.flavia.res").exists()
            and (ROOT / run / "1.flavia.res").stat().st_size > 0,
            "n_steps": len(xs),
            "fachv_max_1": m1,
            "fachv_max_2": m2,
            "fachv_lines": nf,
            "peak_x": peak(fx),
            "peak_y": peak(fy),
            "rms_x": rms(fx),
            "rms_y": rms(fy),
            # aliases; same numbers, spelled the way the displacement
            # components are named elsewhere. A key is never omitted: an
            # unextractable series reports NaN, so "missing" and "0" and
            # "not extracted" stay distinguishable.
            "peak_ux": peak(fx),
            "peak_uy": peak(fy),
            "rms_ux": rms(fx),
            "rms_uy": rms(fy),
            "series_extracted": len(xs) > 0,
            "_x_str": xs,
            "_y_str": ys,
            "_x": fx,
            "_y": fy,
        }
    return out


# -------------------------------------------------------------------- judge

def judge(m: dict) -> list[dict]:
    R = m["runs"]
    v: list[dict] = []

    def add(pid, role, verdict, evidence, voids=False):
        v.append({"id": pid, "role": role, "verdict": verdict,
                  "voids_all_if_falsified": voids, "evidence": evidence})

    # ---- C1 positive control (train02, FIX, driven direction = slot 2 / uy)
    on, off = R["t02_on"], R["t02_off"]
    rd_y = reldiff(off["_y"], on["_y"])
    c1 = (on["fachv_max_2"] > 0 and on["fachv_max_1"] == 0
          and off["fachv_max_1"] == 0 and off["fachv_max_2"] == 0
          and rd_y >= 0.10)
    add("C1", "CONTROL", "PASS" if c1 else "FALSIFIED", {
        "fachv_max_1(t02_on)": on["fachv_max_1"],
        "fachv_max_2(t02_on)": on["fachv_max_2"],
        "fachv_max_1(t02_off)": off["fachv_max_1"],
        "fachv_max_2(t02_off)": off["fachv_max_2"],
        "reldiff_y(off vs on)": rd_y,
        "threshold": 0.10,
    }, voids=True)

    # ---- C2 determinism control
    a, b = R["t10_base"], R["t10_base_rep"]
    same = (a["n_steps"] == b["n_steps"] and a["n_steps"] > 0
            and a["_x_str"] == b["_x_str"] and a["_y_str"] == b["_y_str"])
    first_diff = None
    for i, (p, q) in enumerate(zip(a["_x_str"], b["_x_str"])):
        if p != q:
            first_diff = {"step": i, "base": p, "rep": q}
            break
    add("C2", "CONTROL", "PASS" if same else "FALSIFIED", {
        "n_steps(base)": a["n_steps"], "n_steps(rep)": b["n_steps"],
        "bit_identical": same, "first_x_mismatch": first_diff,
    }, voids=True)

    # ---- P1 baseline fachv dormant under VIE
    base = R["t10_base"]
    p1 = base["fachv_max_1"] == 0 and base["fachv_max_2"] == 0
    add("P1", "prediction", "PASS" if p1 else "FALSIFIED", {
        "fachv_max_1": base["fachv_max_1"], "fachv_max_2": base["fachv_max_2"],
        "fachv_lines": base["fachv_lines"],
    })

    # ---- P2 mechanism: fachv non-zero despite VIE
    var = R["t10_var"]
    p2 = var["solved"] and var["fachv_max_1"] > 0
    add("P2", "prediction", "PASS" if p2 else "FALSIFIED", {
        "solved": var["solved"], "fachv_max_1": var["fachv_max_1"],
        "fachv_max_2": var["fachv_max_2"], "fachv_lines": var["fachv_lines"],
    })

    # ---- P3 physics: crest x-history changes
    rd_x = reldiff(var["_x"], base["_x"])
    p3 = rd_x >= 0.05
    add("P3", "prediction", "PASS" if p3 else "FALSIFIED", {
        "reldiff_x": rd_x, "threshold": 0.05,
        "peak_x(base)": base["peak_x"], "peak_x(var)": var["peak_x"],
        "rms_x(base)": base["rms_x"], "rms_x(var)": var["rms_x"],
    })

    # ---- P4 additive, not cancelling
    p4 = var["peak_x"] > base["peak_x"]
    add("P4", "prediction", "PASS" if p4 else "FALSIFIED", {
        "peak_x(base)": base["peak_x"], "peak_x(var)": var["peak_x"],
        "ratio": (var["peak_x"] / base["peak_x"]) if base["peak_x"] else None,
    })

    # ---- P5 replication on cases/vie
    vb, vv = R["vie_base"], R["vie_var"]
    rd_v = reldiff(vv["_x"], vb["_x"])
    p5 = vb["solved"] and vv["solved"] and vv["fachv_max_1"] > 0 and rd_v >= 0.05
    add("P5", "prediction", "PASS" if p5 else "FALSIFIED", {
        "solved(vie_base)": vb["solved"], "solved(vie_var)": vv["solved"],
        "fachv_max_1(vie_base)": vb["fachv_max_1"],
        "fachv_max_1(vie_var)": vv["fachv_max_1"],
        "reldiff_x": rd_v, "threshold": 0.05,
        "peak_x(vie_base)": vb["peak_x"], "peak_x(vie_var)": vv["peak_x"],
    })
    return v


def main() -> None:
    digest = check_hash()
    m = measure()
    verdicts = judge(m)

    controls = [v for v in verdicts if v["role"] == "CONTROL"]
    preds = [v for v in verdicts if v["role"] == "prediction"]
    controls_ok = all(v["verdict"] == "PASS" for v in controls)
    n_pass = sum(1 for v in preds if v["verdict"] == "PASS")

    summary = {
        "predictions_sha256": digest,
        "controls_ok": controls_ok,
        "results_void": not controls_ok,
        "score": f"{n_pass}/{len(preds)}",
        "verdicts": verdicts,
        "metrics": {r: {k: d[k] for k in d if not k.startswith("_")}
                    for r, d in m["runs"].items()},
        "probe_nodes": m["probe_nodes"],
    }
    (HERE / "verdict.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"predictions.json sha256 verified: {digest}")
    print(f"controls_ok = {controls_ok}"
          f"{'' if controls_ok else '   *** ALL RESULTS VOID ***'}")
    for v in verdicts:
        print(f"  {v['id']:3s} [{v['role']:10s}] {v['verdict']}")
    print(f"score (non-control): {n_pass}/{len(preds)}")


if __name__ == "__main__":
    main()
