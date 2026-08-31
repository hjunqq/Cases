#!/usr/bin/env python3
"""build_material_file — write / edit `<probn>.mat`. (Capabilities 17, 18, 19 material side.)

`.mat` is read by `material_set` (Material.f90:240-1000). Structure:

    text                                  header/echo
    nscurve                               number of stress-strain curves
      per curve:  npoints type_curve
                  strain_curve(1:npoints)
                  stress_curve(1:npoints)
    nline                                 how many comment lines follow
      nline x comment lines               (positional -- deleting one shifts everything)
    text
    mmats                                 number of material RECORDS
      per record:
        text                              "material_serial  <i>"
        property  name  imat              property = MECHANICAL | HEAT | GEOMETRY
        (MECHANICAL) nphase
          per phase:
            phase                         SOLID | FLUID | AIR | OIL
            (SOLID) model density ratio thickness e nu alfa icreep kind_wt jliqu
                    iE iNu density_w
                    <model-specific sub-records>
            (FLUID) density ratio bulkw
                    permiability(1:ndimn)
        (HEAT)     alfa(1:ndimn) source_curve place_curve pipe_cooling
                   ialfa
                   [water_curve time_cooling gap_cooling eata bcooltime] if pipe_cooling/=0
        (GEOMETRY) Aera J Iy Iz

UNITS (verified against every shipped case, docs/input_preparation.md §0.2):
  density kg/m3 | e Pa | nu - | alfa 1/degC | thickness m (2-D out-of-plane)
  cohesion Pa | friction & dilation angle DEGREES | Kn,Ks Pa/m | permeability m/s

SOLID MODEL KEYWORDS accepted by Material.f90 (`case(...)` at lines 435-920):
  PLANE_LOWFT ELASTIC_ISOTROPIC ELASTIC_FRICTIONLESS ELASTIC_SPRING ELASTIC_EP
  STEEL_EP STEEL_SP DUNCANCHANG GOODMAN CLASSICALEP CAMCLAY CONCRETE ClayPZ SandPZ SoilPZ
CLASSICALEP criteria: MC DP VM TC MCC DPC MCJOINT

REGIONAL / MATERIAL DEFAULTS harvested from the shipped dam cases -- physically informed
starting points, NOT calibration. Anything taken from here is flagged `assumed` in the JSON
side-car so it can never be mistaken for a measured value.

Usage:
    python3 build_material_file.py --case /tmp/mycase --describe
    python3 build_material_file.py --case /tmp/mycase --set 1 e=2.0e10 nu=0.2 density=2450
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (ENC, HstarInputError, probn_of, raw_tokens,  # noqa: E402
                       read_lines, tokens, write_lines)

SOLID_MODELS = {
    "ELASTIC_ISOTROPIC", "ELASTIC_FRICTIONLESS", "ELASTIC_SPRING", "ELASTIC_EP",
    "PLANE_LOWFT", "STEEL_EP", "STEEL_SP", "DUNCANCHANG", "GOODMAN", "CLASSICALEP",
    "CAMCLAY", "CONCRETE", "ClayPZ", "SandPZ", "SoilPZ",
}
CLASSICALEP_CRITERIA = {"MC", "DP", "VM", "TC", "MCC", "DPC", "MCJOINT"}

# The 10 tokens of the SOLID line, in read order (Material.f90:289)
SOLID_FIELDS = ["model", "density", "ratio", "thickness", "e", "nu", "alfa",
                "icreep", "kind_wt", "jliqu"]
SOLID_UNITS = {"density": "kg/m3", "ratio": "-", "thickness": "m", "e": "Pa",
               "nu": "-", "alfa": "1/degC", "icreep": "flag", "kind_wt": "flag",
               "jliqu": "flag"}

DEFAULTS = {
    # material            E (Pa)     nu     rho     alfa      note
    "concrete_dam":      (2.4e10, 0.167, 2400.0, 1.0e-5,
                          "mass concrete, from cases/static group 1"),
    "concrete_rcc":      (2.2e10, 0.20, 2400.0, 1.0e-5, "roller-compacted concrete"),
    "rock_foundation":   (1.5e10, 0.25, 2650.0, 8.0e-6,
                          "sound rock foundation, cases/static group 2/3 range"),
    "weak_rock":         (5.0e9, 0.30, 2500.0, 8.0e-6, "weathered / faulted zone"),
    "rockfill":          (1.0e8, 0.30, 2100.0, 0.0, "use DUNCANCHANG in practice"),
    "steel_rebar":       (2.1e11, 0.30, 7850.0, 1.2e-5, "HRB400 class"),
}


def read_mat(case):
    """Locate every SOLID parameter line so a caller can edit one value in place."""
    case = Path(case)
    probn = probn_of(case)
    p = case / f"{probn}.mat"
    lines, eol = read_lines(p)
    records = []
    for i, line in enumerate(lines):
        tk = raw_tokens(line)
        if not (tk and tk[0].upper() in {m.upper() for m in SOLID_MODELS} and len(tk) >= 7):
            continue
        # The comment block near the top of every .mat also starts lines with a model
        # keyword ("CAMCLAY    :Pc, lamda, Mg, ..."). A real parameter line has six
        # numbers after the keyword; a comment line does not.
        try:
            [float(t) for t in tk[1:7]]
        except ValueError:
            continue
        rec = {"line": i, "model": tk[0]}
        if True:
            for k, f in enumerate(SOLID_FIELDS):
                if k < len(tk):
                    rec[f] = tk[k]
            rec["unit"] = dict(SOLID_UNITS)
            records.append(rec)
    return {"path": str(p), "lines": lines, "eol": eol, "solid_records": records}


def describe(case):
    d = read_mat(case)
    out = []
    for r in d["solid_records"]:
        row = {"line": r["line"] + 1, "model": r["model"]}
        for f in SOLID_FIELDS[1:]:
            if f in r:
                row[f] = r[f]
        out.append(row)
    return {"path": d["path"], "n_solid_records": len(out), "solid_records": out,
            "units": SOLID_UNITS}


def set_solid(case, index, **kw):
    """Edit the `index`-th (1-based) SOLID parameter line. Keys are SOLID_FIELDS."""
    d = read_mat(case)
    recs = d["solid_records"]
    if not 1 <= index <= len(recs):
        raise HstarInputError(
            f"material record {index} out of range 1..{len(recs)}")
    r = recs[index - 1]
    tk = raw_tokens(d["lines"][r["line"]])
    assumed = []
    for k, v in kw.items():
        if k not in SOLID_FIELDS:
            raise HstarInputError(
                f"unknown SOLID field {k!r}; the line is "
                f"{' '.join(SOLID_FIELDS)} (Material.f90:289)")
        pos = SOLID_FIELDS.index(k)
        if pos >= len(tk):
            raise HstarInputError(
                f"this SOLID line has only {len(tk)} tokens; field {k!r} is at position "
                f"{pos + 1}. Do not append -- HSTAR reads a fixed count and a longer line "
                f"is harmless but a SHORT one spills into the next record.")
        if k == "model":
            if str(v) not in SOLID_MODELS:
                raise HstarInputError(f"unknown solid model {v!r}; "
                                      f"valid: {sorted(SOLID_MODELS)}")
            tk[pos] = str(v)
        elif k in ("icreep", "kind_wt", "jliqu"):
            tk[pos] = str(int(v))
        else:
            val = float(v)
            if k == "nu" and not -1.0 < val < 0.5:
                raise HstarInputError(
                    f"nu={val}: Poisson's ratio must be in (-1, 0.5); 0.5 is incompressible "
                    f"and makes the plane-strain D matrix singular")
            if k == "e" and not 1e3 < val < 1e13:
                raise HstarInputError(
                    f"e={val} Pa is outside 1e3..1e13. HSTAR is unit-agnostic and will NOT "
                    f"warn you: a value near 2.5e4 usually means MPa were entered where Pa "
                    f"are expected, which scales every displacement by 1e6 (triplet dt_006).")
            if k == "density" and not 1.0 < val < 2e4:
                raise HstarInputError(f"density={val} kg/m3 is outside 1..2e4")
            tk[pos] = f"{val:.4E}"
    d["lines"][r["line"]] = " " + "  ".join(tk)
    write_lines(d["path"], d["lines"], d["eol"])
    return {"path": d["path"], "record": index, "line": r["line"] + 1,
            "now": dict(zip(SOLID_FIELDS, tk)), "assumed": assumed}


def apply_default(case, index, preset):
    """Set E/nu/density/alfa from the regional default table, and record the assumption."""
    if preset not in DEFAULTS:
        raise HstarInputError(f"unknown preset {preset!r}; known: {sorted(DEFAULTS)}")
    e, nu, rho, alfa, note = DEFAULTS[preset]
    r = set_solid(case, index, e=e, nu=nu, density=rho, alfa=alfa)
    r["assumed"] = [{"preset": preset, "e": e, "nu": nu, "density": rho, "alfa": alfa,
                     "provenance": note,
                     "status": "ASSUMED -- physically informed default, not measured"}]
    side = Path(case) / "assumed_parameters.json"
    prev = json.loads(side.read_text()) if side.is_file() else []
    prev.append({"material_record": index, **r["assumed"][0]})
    side.write_text(json.dumps(prev, indent=1))
    r["side_car"] = str(side)
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--set", nargs="+", metavar="INDEX KEY=VAL",
                    help="e.g. --set 1 e=2.0e10 nu=0.2")
    ap.add_argument("--preset", nargs=2, metavar=("INDEX", "NAME"),
                    help="apply a regional default, e.g. --preset 1 concrete_dam")
    ap.add_argument("--list-presets", action="store_true")
    a = ap.parse_args(argv)
    if a.list_presets:
        print(json.dumps({k: {"E_Pa": v[0], "nu": v[1], "density_kg_m3": v[2],
                              "alfa_1_degC": v[3], "note": v[4]}
                          for k, v in DEFAULTS.items()}, indent=2))
        return 0
    if a.set:
        idx = int(a.set[0])
        kw = {}
        for kv in a.set[1:]:
            k, _, v = kv.partition("=")
            kw[k] = v
        print(json.dumps(set_solid(a.case, idx, **kw), indent=2))
        return 0
    if a.preset:
        print(json.dumps(apply_default(a.case, int(a.preset[0]), a.preset[1]), indent=2))
        return 0
    print(json.dumps(describe(a.case), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
