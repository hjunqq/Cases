#!/usr/bin/env python3
"""
parse_results.py -- Stage s10: turn HSTAR output files into JSON.

Files parsed
------------
`*.flavia.res`  the primary result file (ASCII when `outplot='GIDR'/'GIDA'`).
    Block header, FORMAT `(a15,i8,f12.5,5i8)` (Output.f90:2117):

        <NAME> <1> <time> <itype> <iloc> <imat>

    itype 1 scalar, 2 vector, 3 matrix; iloc 1 = on nodes.
    When the last flag is 1 the header is followed by one record per tensor
    component naming it (`SIGXX`, `SIGYY`, `SIGXY`, `SIGZZ`), then one record
    per node: `ipoin  v1 [v2 ...]`.

    Block names emitted by Output.f90:
        DISPLACEMENT, dam_DISPLACEMENT, foundation_DISPLACEMENT,
        STRESS, PRINCIPALSTRESS, PLASTICSTRAIN, STRESS_Moment,
        PORE-PRESSURE, Excess_PORE-PRESSURE, uplift-PRESSURE,
        PRESSURE_V, TEMPERATURE

`*.gpv`  Gauss-point stresses: `ielem  igaus  s1..s7` after one heading record.
`*.act`  support reactions per output step (`outfix=1` sets), preceded by the
         `ttime=` record.
`*.chk`  the run log: convergence ratios, step/iteration trace, timings.
`*.ctr` / `*.gdm` / `*.ojw`  contact gaps and joint stresses.
`*.bar`  bar / reinforcement forces.

Everything is returned in the model's own units: metres, pascals, degrees
Celsius, newtons. No conversion is applied anywhere.

validate -> process -> validate:
  pre : the file exists and is non-empty
  post: every block has one data record per node the header implies; values
        are finite; a block with zero data records is reported, not dropped

Usage
-----
  python3 parse_results.py --output_dir out1 --json results.json
  python3 parse_results.py --output_dir out1 --var DISPLACEMENT --step last
  python3 parse_results.py --output_dir out1 --summary
"""

import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import read_tokens  # noqa: E402

HEADER_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_\-]*)\s+(\d+)\s+([-+0-9.eEdD]+)"
    r"\s+(\d+)\s+(\d+)\s+(\d+)\s*$")
COMPONENT_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*$")

# Unit of every block name Output.f90 can emit.
UNITS = {
    "DISPLACEMENT": "m", "dam_DISPLACEMENT": "m",
    "foundation_DISPLACEMENT": "m",
    "STRESS": "Pa", "PRINCIPALSTRESS": "Pa", "STRESS_Moment": "N*m/m",
    "PLASTICSTRAIN": "-",
    "PORE-PRESSURE": "Pa", "PORE_PRESSURE": "Pa",
    "Excess_PORE-PRESSURE": "Pa", "uplift-PRESSURE": "Pa",
    "PRESSURE_V": "Pa", "TEMPERATURE": "degC",
    "VELOCITY": "m/s", "ACCELERATION": "m/s2",
}


def _f(tok):
    # Fortran may emit D exponents
    return float(tok.replace("D", "E").replace("d", "e"))


def parse_flavia_res(path):
    """-> list of blocks {name, step_index, time, itype, iloc, components,
                          nodes:[id], values:[[...]] }"""
    blocks = []
    cur = None
    with open(path, errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            m = HEADER_RE.match(line)
            if m and not line.split()[0].lstrip("+-").replace(".", "").isdigit():
                cur = {"name": m.group(1),
                       "series": int(m.group(2)),
                       "time": _f(m.group(3)),
                       "itype": int(m.group(4)),
                       "iloc": int(m.group(5)),
                       "imat": int(m.group(6)),
                       "unit": UNITS.get(m.group(1), "unknown"),
                       "components": [],
                       "nodes": [], "values": []}
                blocks.append(cur)
                continue
            if cur is None:
                continue
            cm = COMPONENT_RE.match(line)
            if cm and not cur["nodes"]:
                cur["components"].append(cm.group(1))
                continue
            toks = read_tokens(line)
            try:
                nid = int(toks[0])
                vals = [_f(t) for t in toks[1:]]
            except (ValueError, IndexError):
                continue
            cur["nodes"].append(nid)
            cur["values"].append(vals)
    return blocks


def parse_gpv(path):
    """Gauss-point stresses: ielem igaus s1..s7."""
    rows = []
    with open(path, errors="replace") as fh:
        for raw in fh:
            toks = read_tokens(raw)
            if len(toks) < 3:
                continue
            try:
                ie, ig = int(toks[0]), int(toks[1])
                vals = [_f(t) for t in toks[2:]]
            except ValueError:
                continue
            rows.append({"element": ie, "gauss": ig, "stress": vals})
    return rows


def parse_act(path):
    """Reactions. Records alternate between a `ttime=` marker and value rows."""
    steps, cur = [], None
    with open(path, errors="replace") as fh:
        for raw in fh:
            s = raw.strip()
            if "ttime=" in s:
                cur = {"time": None, "values": [], "nodes": []}
                try:
                    cur["time"] = _f(s.split("ttime=")[1].split()[0])
                except (IndexError, ValueError):
                    pass
                steps.append(cur)
                continue
            if "*" in s or not s:
                continue
            toks = read_tokens(s)
            try:
                vals = [_f(t) for t in toks]
            except ValueError:
                continue
            if cur is None:
                cur = {"time": None, "values": [], "nodes": []}
                steps.append(cur)
            cur["values"].extend(vals)
    return steps


def parse_chk(path):
    """Convergence trace from the run log."""
    info = {"steps": [], "final_ratio_force": None,
            "final_ratio_disp": None, "not_converged": 0, "blocks": []}
    last_force = last_disp = None
    with open(path, errors="replace") as fh:
        for raw in fh:
            s = raw.strip()
            if s.startswith("iblks=") or "iblks=" in s:
                info["blocks"].append(s)
            if "ratio for residu norm=" in s:
                try:
                    last_force = _f(s.split("=")[-1])
                except ValueError:
                    pass
            if "ratio for norm=" in s:
                try:
                    last_disp = _f(s.split("=")[-1])
                except ValueError:
                    pass
            if "not converged" in s:
                info["not_converged"] += 1
    info["final_ratio_force"] = last_force
    info["final_ratio_disp"] = last_disp
    return info


def parse_frequency(path):
    """Modal frequencies written by frequency_analysis (type_problem='W')."""
    freqs = []
    with open(path, errors="replace") as fh:
        for raw in fh:
            s = raw.strip().lower()
            if "frequency" in s or "freq=" in s:
                for t in read_tokens(raw):
                    try:
                        v = _f(t)
                    except ValueError:
                        continue
                    if 0.0 < v < 1.0e5:
                        freqs.append(v)
    return freqs


def parse_inverse(chk_path):
    """Trust-region / Gauss-Newton iterates from the back-analysis log."""
    it = []
    with open(chk_path, errors="replace") as fh:
        for raw in fh:
            s = raw.strip()
            if s.lower().startswith(("xvalue", "iter=", "r1=", "r2=")):
                it.append(s)
    return it


def parse_reliability(chk_path):
    """FORM beta iterates."""
    betas = []
    with open(chk_path, errors="replace") as fh:
        for raw in fh:
            if "beta" in raw.lower():
                for t in read_tokens(raw):
                    try:
                        v = _f(t)
                    except ValueError:
                        continue
                    if -20 < v < 20:
                        betas.append(v)
    return betas


def summarise(blocks):
    out = []
    for b in blocks:
        flat = [v for row in b["values"] for v in row]
        finite = [v for v in flat if math.isfinite(v)]
        entry = {"name": b["name"], "time": b["time"], "unit": b["unit"],
                 "n_nodes": len(b["nodes"]),
                 "components": b["components"] or None}
        if finite:
            entry["min"] = min(finite)
            entry["max"] = max(finite)
            entry["absmax"] = max(abs(v) for v in finite)
        if len(finite) != len(flat):
            entry["non_finite"] = len(flat) - len(finite)
        out.append(entry)
    return out


def validate_blocks(blocks, npoin=None):
    p = []
    for b in blocks:
        if not b["nodes"]:
            p.append("block %s @ t=%s has no data records" % (b["name"], b["time"]))
        if npoin and b["nodes"] and len(b["nodes"]) != npoin:
            p.append("block %s @ t=%s has %d node records but the mesh has %d"
                     % (b["name"], b["time"], len(b["nodes"]), npoin))
        for row in b["values"]:
            for v in row:
                if not math.isfinite(v):
                    p.append("block %s @ t=%s contains a non-finite value"
                             % (b["name"], b["time"]))
                    break
            else:
                continue
            break
    return p


def collect(output_dir, npoin=None):
    res = {"output_dir": os.path.abspath(output_dir), "blocks": [],
           "gauss_points": [], "reactions": [], "convergence": None,
           "frequencies": [], "problems": []}
    f = os.path.join(output_dir, "1.flavia.res")
    if os.path.exists(f) and os.path.getsize(f):
        res["blocks"] = parse_flavia_res(f)
        res["problems"] += validate_blocks(res["blocks"], npoin)
    g = os.path.join(output_dir, "1.gpv")
    if os.path.exists(g) and os.path.getsize(g):
        res["gauss_points"] = parse_gpv(g)
    a = os.path.join(output_dir, "1.act")
    if os.path.exists(a) and os.path.getsize(a):
        res["reactions"] = parse_act(a)
    c = os.path.join(output_dir, "1.chk")
    if os.path.exists(c) and os.path.getsize(c):
        res["convergence"] = parse_chk(c)
        res["frequencies"] = parse_frequency(c)
    if not res["blocks"]:
        res["problems"].append(
            "no result blocks found in 1.flavia.res -- either gid_u/gid_s are 0 "
            "in .glb, or noutf in .man is larger than nstep (triplet dt_015)")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--json", default="")
    ap.add_argument("--var", default="")
    ap.add_argument("--step", default="")
    ap.add_argument("--npoin", type=int)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--inverse", action="store_true")
    ap.add_argument("--reliability", action="store_true")
    a = ap.parse_args()

    res = collect(a.output_dir, a.npoin)
    chk = os.path.join(a.output_dir, "1.chk")
    if a.inverse and os.path.exists(chk):
        res["inverse_iterations"] = parse_inverse(chk)
    if a.reliability and os.path.exists(chk):
        res["reliability_beta"] = parse_reliability(chk)

    blocks = res["blocks"]
    if a.var:
        blocks = [b for b in blocks if b["name"] == a.var]
        if not blocks:
            print("no block named %r; available: %s"
                  % (a.var, sorted({b["name"] for b in res["blocks"]})))
            return 1
    if a.step == "last" and blocks:
        tmax = max(b["time"] for b in blocks)
        blocks = [b for b in blocks if b["time"] == tmax]
    res["blocks"] = blocks

    if a.json:
        with open(a.json, "w") as fh:
            json.dump(res, fh, indent=2)
        print("wrote", a.json)
    if a.summary or not a.json:
        print(json.dumps({"summary": summarise(blocks),
                          "convergence": res["convergence"],
                          "n_gauss_rows": len(res["gauss_points"]),
                          "problems": res["problems"]}, indent=2))
    return 1 if res["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
