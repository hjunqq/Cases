#!/usr/bin/env python3
"""parse_outputs — read every HSTAR result stream into plain Python / JSON / CSV.
(Capability 31, and the parsing half of capabilities 1-9 and 34.)

HSTAR writes results in three places and this tool reads all three:

1. `<probn>.flavia.res` -- the GiD "flavia" ASCII result file. HSTAR writes it itself
   (Output.f90:OUT_GID_WRITE), NOT through the gidpost library, so the layout is fixed by
   Fortran FORMAT 101 = `(a15, i8, f12.5, 5i8)`:

       name(15)  step(i8)  total_step(f12.5)  datatype(i8)  1(i8)  location(i8)

   datatype: 1 = scalar, 2 = vector, 3 = matrix.  location: 0 = OnNodes, 1 = OnGaussPoints.
   A matrix block is followed by its component-name lines (SIGXX / SIGYY / SIGXY / SIGZZ in
   2-D, six in 3-D) and then `(i10, 10(2x,e20.8))` data records.
   Result names emitted (Output.f90:1342-1830): DISPLACEMENT, foundation_DISPLACEMENT,
   dam_DISPLACEMENT, velocity, acceleration, acceleration_absolute, ROTATION,
   PORE-PRESSURE, Excess_PORE-PRESSURE, WATER-HEAD, flow_velocity, tofor, PRESSURE_V,
   flow_charge, TEMPERATURE, uplift-PRESSURE, STRESS, PRINCIPALSTRESS, PLASTICSTRAIN, ...

2. `<probn>.chk` -- the convergence / diagnostics log. Two things matter:
     * `conver_load check` blocks: `resid=`, `retot=`, `ratio1=`, `ratio2=`,
       `nchek=` -- this is HSTAR's EQUILIBRIUM RESIDUAL, the structural analogue of a
       water-balance check. `nchek=0` means converged.
     * modal results (`type_problem='E'`), FORMAT 100:
       `order= i5  omega= e12.5  freq= e12.5  period= e12.5 coefx= ... mstar= ... kstar= ...`
       `freq` is in Hz, `omega` in rad/s, `period` in s.

3. `<probn>.omg` -- base frequency (omega, period) when a base-frequency pass ran.

Usage:
    python3 parse_outputs.py --dir /tmp/myrun --json out.json
    python3 parse_outputs.py --dir /tmp/myrun --result DISPLACEMENT --csv disp.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import ENC, HstarInputError, read_lines  # noqa: E402

DATATYPE = {1: "scalar", 2: "vector", 3: "matrix"}
LOCATION = {0: "OnNodes", 1: "OnGaussPoints"}

# unit of each result stream, from the shipped cases' SI convention (docs/s7)
RESULT_UNITS = {
    "DISPLACEMENT": "m", "foundation_DISPLACEMENT": "m", "dam_DISPLACEMENT": "m",
    "velocity": "m/s", "acceleration": "m/s2", "acceleration_absolute": "m/s2",
    "ROTATION": "rad", "PORE-PRESSURE": "Pa", "Excess_PORE-PRESSURE": "Pa",
    "WATER-HEAD": "m", "flow_velocity": "m/s", "tofor": "N", "PRESSURE_V": "Pa",
    "flow_charge": "m3/s", "TEMPERATURE": "degC", "uplift-PRESSURE": "Pa",
    "STRESS": "Pa", "PRINCIPALSTRESS": "Pa", "PLASTICSTRAIN": "-",
    # The a15 name field TRUNCATES: 'acceleration_absolute' is written as
    # 'acceleration_ab'. Both spellings are mapped so a parser never sees "unknown".
    "acceleration_ab": "m/s2", "Yield": "-", "Damage": "-",
    "flow_charg": "m3/s", "Excess_PORE-PR": "Pa",
}

_NUM = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eEdD][-+]?\d+)?$")


def _isnum(tok):
    return bool(_NUM.match(tok.replace("D", "E").replace("d", "e")))


def _f(tok):
    return float(tok.replace("D", "E").replace("d", "e"))


def _is_header(line):
    """FORMAT 101 header: a15 name then >= 4 numeric fields."""
    if len(line) < 16:
        return None
    name = line[:15].strip()
    if not name or _isnum(name):
        return None
    rest = line[15:].split()
    if len(rest) < 4 or not all(_isnum(t) for t in rest[:4]):
        return None
    return name, rest


def parse_flavia_res(path):
    """Parse a .flavia.res into a list of result blocks.

    Each block: {name, unit, step, total_step, datatype, location, components,
                 ids:[int], values:[[float,...]]}
    Repeated blocks (one per output step) are kept in file order.
    """
    lines, _ = read_lines(path)
    blocks, cur = [], None
    for raw in lines:
        if not raw.strip():
            continue
        hdr = _is_header(raw)
        if hdr:
            name, rest = hdr
            cur = {"name": name, "unit": RESULT_UNITS.get(name, "unknown"),
                   "step": int(_f(rest[0])), "total_step": _f(rest[1]),
                   "datatype": DATATYPE.get(int(_f(rest[2])), str(rest[2])),
                   "location": LOCATION.get(int(_f(rest[4])) if len(rest) > 4 else 0,
                                            "OnNodes"),
                   "components": [], "ids": [], "values": []}
            blocks.append(cur)
            continue
        tk = raw.split()
        if cur is None:
            continue
        if not _isnum(tk[0]):
            cur["components"].append(raw.strip())
            continue
        cur["ids"].append(int(_f(tk[0])))
        cur["values"].append([_f(t) for t in tk[1:]])
    return blocks


def parse_chk(path):
    """Convergence records and modal results from <probn>.chk.

    The FILE layout differs from the console echo -- verified against a real run:

        iblks=  1 iincs=  1 istep=  1 iiter=  1
        resid=  0.000E+000 retot=   20601.0
        ratio for residu norm= 0.0000E+00        <- force residual, L2
        max_refor= ...      max_tofor= ...
        ratio for residu maxm= 0.0000E+00        <- force residual, max norm
        ...
        ratio for norm= 0.1000E+01               <- displacement increment, L2
        ratio for maxm= 0.1000E+01               <- displacement increment, max
        not converged for checki=  1             <- absent once converged

    `ratio for residu norm` is the equilibrium check that must fall below
    `toler_force` from probn.man. It is HSTAR's conservation statement.
    """
    txt = Path(path).read_text(encoding=ENC, errors="replace")
    it = [{"iblks": int(m.group(1)), "iincs": int(m.group(2)),
           "istep": int(m.group(3)), "iiter": int(m.group(4)), "pos": m.start()}
          for m in re.finditer(r"iblks=\s*(\d+)\s+iincs=\s*(\d+)\s+istep=\s*(\d+)"
                               r"\s+iiter=\s*(\d+)", txt)]
    resid = [(m.start(), _f(m.group(1)), _f(m.group(2))) for m in re.finditer(
        r"resid=\s*([-\d.EeDd+]+)\s+retot=\s*([-\d.EeDd+]+)", txt)]
    fnorm = [(m.start(), _f(m.group(1))) for m in re.finditer(
        r"ratio for residu norm=\s*([-\d.EeDd+]+)", txt)]
    fmaxm = [(m.start(), _f(m.group(1))) for m in re.finditer(
        r"ratio for residu maxm=\s*([-\d.EeDd+]+)", txt)]
    dnorm = [(m.start(), _f(m.group(1))) for m in re.finditer(
        r"(?<!residu )ratio for norm=\s*([-\d.EeDd+]+)", txt)]
    dmaxm = [(m.start(), _f(m.group(1))) for m in re.finditer(
        r"(?<!residu )ratio for maxm=\s*([-\d.EeDd+]+)", txt)]
    # console-format fallback (`ratio1= ... ratio2= ...`), used when the caller passes
    # hstar_run.log instead of probn.chk
    if not fnorm:
        fnorm = [(m.start(), _f(m.group(1))) for m in re.finditer(
            r"ratio1=\s*([-\d.EeDd+]+)", txt)]
    conv = []
    for k in range(len(resid)):
        rec = {"resid": resid[k][1], "retot": resid[k][2]}
        for key, arr in (("force_ratio_norm", fnorm), ("force_ratio_max", fmaxm),
                         ("disp_ratio_norm", dnorm), ("disp_ratio_max", dmaxm)):
            rec[key] = arr[k][1] if k < len(arr) else None
        for h in it:
            if h["pos"] < resid[k][0]:
                rec.update({q: h[q] for q in ("iblks", "iincs", "istep", "iiter")})
        conv.append(rec)
    modes = []
    for m in re.finditer(
            r"order=\s*(\d+)\s+omega=\s*([-\d.EeDd+]+)\s+freq=\s*([-\d.EeDd+]+)"
            r"\s+period=\s*([-\d.EeDd+]+)", txt):
        modes.append({"order": int(m.group(1)), "omega_rad_s": _f(m.group(2)),
                      "freq_hz": _f(m.group(3)), "period_s": _f(m.group(4))})
    return {"convergence_records": conv, "modes": modes,
            "n_not_converged_checks": txt.count("not converged for checki"),
            "final_residual_ratio": conv[-1]["force_ratio_norm"] if conv else None,
            "final_disp_ratio": conv[-1]["disp_ratio_norm"] if conv else None}


def parse_run(run_dir, probn=None):
    """Parse everything in a finished run directory. Returns one summary dict."""
    d = Path(run_dir)
    if probn is None:
        cands = sorted(d.glob("*.flavia.res")) or sorted(d.glob("*.chk"))
        if not cands:
            raise HstarInputError(
                f"no .flavia.res or .chk in {d} -- HSTAR produced no output. "
                f"Check hstar_run.log and diagnostics/triplets.yaml.")
        probn = cands[0].name.split(".")[0]
    out = {"dir": str(d), "probn": probn, "results": {}, "chk": None}
    res = d / f"{probn}.flavia.res"
    if res.is_file() and res.stat().st_size:
        blocks = parse_flavia_res(res)
        for b in blocks:
            out["results"].setdefault(b["name"], []).append(
                {"step": b["step"], "total_step": b["total_step"], "unit": b["unit"],
                 "datatype": b["datatype"], "location": b["location"],
                 "components": b["components"], "n": len(b["ids"]),
                 "ids": b["ids"], "values": b["values"]})
    chk = d / f"{probn}.chk"
    if chk.is_file() and chk.stat().st_size:
        out["chk"] = parse_chk(chk)
    omg = d / f"{probn}.omg"
    if omg.is_file() and omg.stat().st_size:
        tk = omg.read_text(encoding=ENC, errors="replace").split()
        if len(tk) >= 2:
            out["base_frequency"] = {"omega_rad_s": _f(tk[0]), "period_s": _f(tk[1])}
    out["summary"] = summarise(out)
    return out


def summarise(parsed):
    """Compact, unit-labelled extremes -- the first thing to look at after a run."""
    s = {}
    for name, blocks in parsed["results"].items():
        last = blocks[-1]
        flat = [v for row in last["values"] for v in row]
        if not flat:
            continue
        s[name] = {"unit": last["unit"], "n_entities": last["n"],
                   "n_steps": len(blocks), "min": min(flat), "max": max(flat),
                   "max_abs": max(abs(v) for v in flat)}
        if last["datatype"] == "vector":
            for c in range(len(last["values"][0])):
                col = [row[c] for row in last["values"] if len(row) > c]
                s[name][f"comp{c + 1}_max_abs"] = max(abs(v) for v in col)
    if parsed.get("chk"):
        c = parsed["chk"]
        fr, dr = c["final_residual_ratio"], c["final_disp_ratio"]
        s["converged"] = ((fr is not None and fr < 1e-3)
                          and (dr is None or dr < 1e-3))
        s["final_residual_ratio"] = fr
        s["final_disp_ratio"] = dr
        if parsed["chk"]["modes"]:
            s["modal_frequencies_hz"] = [m["freq_hz"] for m in parsed["chk"]["modes"]]
    return s


def to_csv(parsed, result_name, path):
    blocks = parsed["results"].get(result_name)
    if not blocks:
        raise HstarInputError(
            f"no result named {result_name!r}; available: {sorted(parsed['results'])}")
    last = blocks[-1]
    comps = last["components"] or [f"c{i + 1}" for i in range(len(last["values"][0]))]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id"] + comps + [f"unit={last['unit']}"])
        for i, row in zip(last["ids"], last["values"]):
            w.writerow([i] + row)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", required=True, help="run/output directory")
    ap.add_argument("--probn", help="case base name (auto-detected by default)")
    ap.add_argument("--json", help="write the full parse to this JSON file")
    ap.add_argument("--csv", help="write one result stream to CSV")
    ap.add_argument("--result", default="DISPLACEMENT", help="which stream --csv exports")
    a = ap.parse_args(argv)
    parsed = parse_run(a.dir, a.probn)
    if a.json:
        Path(a.json).write_text(json.dumps(parsed, indent=1))
    if a.csv:
        to_csv(parsed, a.result, a.csv)
    print(json.dumps(parsed["summary"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
