#!/usr/bin/env python3
"""build_loads — inspect and edit `<probn>.loa` (time curves, point loads, edge/pressure
loads, hydrostatic water pressure, gravity/body force) and the uplift switch.
(Capabilities 22, 33.)

`.loa` is re-read for EVERY LOAD BLOCK by `external_load_2` (Load.f90:134-960). One complete
group of records exists per block. The read sequence this tool replays:

    text ; ntcurve
      per curve:  ntime type_curve nstoch_curve nline
                  [order_stoch_parameter]          if nstoch_curve /= 0
                  <type-specific record(s)>        HARMONIC | FOURIERSERIES | WATERLEVEL
                                                   | SEISMIC | EXTRAPOLATION | ARCLENGTH
                  ttime_curve(1:ntime)             (default types, e.g. LINEAR)
                  dfact_curve(1:ntime)
    text ; nplgroup kpload                          point loads
      kpload==1: per group  order_time_curve nudofn npload nline
                            pxyz(1:nudofn)          FORCE in N
                            list(1:npload)          node ids
    text ; nedge                                    edge/face definitions
      per edge group: text ; sedge nnode index vdimn ; sedge x (i0 lnode(1:nnode) aelem)
    text ; text ; edge_load_group delgroup
      per delgroup: begin_edge end_edge itcurve water code_load
                    [cor0 cor1 p0 p1 fact]          if water /= 0   <- HYDROSTATIC PRESSURE
                    [cor01 cor11 p01 p11 fact1]     if code_load /= 0
    text ; gravy factg(1:ndimn) factf(1:ndimn)      <- GRAVITY / BODY FORCE
    text nline ; tcurvegravity(1:ngroup)
    text ; nbeamload
    text ; nplateload

UNITS: `gravy` m/s2 (9.81); `factg`/`factf` are dimensionless direction cosines for the
solid and fluid phases (0 -1 in 2-D = downward). `pxyz` N.

The hydrostatic record is `cor0 cor1 p0 p1 fact` and Load.f90:800 evaluates

    press = -(p0 + (cor0 - x)/(cor0 - cor1) * (p1 - p0)) * fact

so `cor0`/`cor1` are the ELEVATIONS (m) between which the pressure ramps linearly, and the
PRODUCT `p x fact` is the pressure in Pa. The shipped cases put HEAD IN METRES in `p0`/`p1`
and the water unit weight 9810 N/m3 in `fact` -- `cases/static` ships `40 0 0 40 9810`,
i.e. 0 Pa at elevation 40 m rising to 40 x 9810 = 392.4 kPa at elevation 0. Setting
`fact` to 1.0 and `p0/p1` in Pa is equally valid; what is NOT valid is leaving `fact=9810`
while also entering `p1` in Pa, which inflates the load 9810x (triplet dt_011).

THE RESERVOIR-LEVEL EDIT is the most common one: raising the water surface means changing
`cor0` (and `p0`, which is the pressure at `cor0`, normally 0) in every `water/=0` record,
AND `water_level(1:nblks)` in `.glb`. Doing only one of the two is triplet dt_010.

Usage:
    python3 build_loads.py --case /tmp/mycase --describe
    python3 build_loads.py --case /tmp/mycase --gravity 9.81 0 -1
    python3 build_loads.py --case /tmp/mycase --water-level 120.0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (GlbDoc, HstarInputError, probn_of, read_lines,  # noqa: E402
                       tokens, write_lines)

SPECIAL_CURVES = {"HARMONIC": 1, "FOURIERSERIES": 3, "WATERLEVEL": None,
                  "SEISMIC": 1, "EXTRAPOLATION": 1, "ARCLENGTH": 1}


class Loa:
    """A replayed `<probn>.loa`, with line indices for the records worth editing."""

    def __init__(self, case):
        self.case = Path(case)
        self.probn = probn_of(self.case)
        self.path = self.case / f"{self.probn}.loa"
        g = GlbDoc(self.case / f"{self.probn}.glb")
        self.ndimn, self.ngroup = int(g.get("ndimn")), g.ngroup
        self.lines, self.eol = read_lines(self.path)
        self.curves, self.water_records, self.gravity_line = [], [], None
        self.point_loads, self.edge_groups = [], []
        self._parse()

    def _tk(self, i):
        return tokens(self.lines[i])

    def _parse(self):
        i = 1                                            # text
        ntcurve = int(float(self._tk(i)[0])); i += 1
        for _ in range(ntcurve):
            tk = self._tk(i)
            ntime, type_curve = int(float(tk[0])), tk[1]
            nstoch = int(float(tk[2])) if len(tk) > 2 else 0
            head = i; i += 1
            if nstoch:
                i += 1
            if type_curve == "WATERLEVEL":
                i += ntime
            elif type_curve in SPECIAL_CURVES:
                i += SPECIAL_CURVES[type_curve]
            else:
                i += 1                                   # ttime_curve
            if type_curve in ("SEISMIC",) or type_curve not in (
                    "ARCLENGTH", "EXTRAPOLATION", "HARMONIC", "WATERLEVEL"):
                dline = i; i += 1
            else:
                dline = None
            self.curves.append({"line": head, "ntime": ntime, "type": type_curve,
                                "dfact_line": dline})
        i += 1                                           # text
        nplgroup, kpload = (int(float(x)) for x in self._tk(i)[:2]); i += 1
        if nplgroup and kpload == 1:
            for _ in range(nplgroup):
                tk = self._tk(i)
                npload = int(float(tk[2]))
                self.point_loads.append({"line": i, "order_time_curve": int(float(tk[0])),
                                         "nudofn": int(float(tk[1])), "npload": npload,
                                         "pxyz_line": i + 1})
                i += 2
                got = 0
                while got < npload:
                    got += len(self._tk(i)); i += 1
        elif nplgroup:
            raise HstarInputError(
                f"kpload={kpload} (coordinate-located point loads, Load.f90:291) is not "
                f"round-tripped by this tool; edit .loa by hand for this case")
        i += 1                                           # text
        nedge = int(float(self._tk(i)[0])); i += 1
        for _ in range(nedge and 1 or 0):
            pass
        if nedge:
            i += 1                                       # text ('sedge')
            tk = self._tk(i)
            sedge, nnode = int(float(tk[0])), int(float(tk[1]))
            self.edge_groups.append({"line": i, "sedge": sedge, "nnode": nnode,
                                     "index": int(float(tk[2])),
                                     "vdimn": int(float(tk[3])) if len(tk) > 3 else 0})
            i += 1 + sedge
        i += 2                                           # text ; text
        tk = self._tk(i)
        edge_load_group, delgroup = int(float(tk[0])), int(float(tk[1])); i += 1
        if edge_load_group:
            for _ in range(delgroup):
                tk = self._tk(i)
                water, code_load = int(float(tk[3])), int(float(tk[4]))
                i += 1
                if water:
                    self.water_records.append({"line": i, "delgroup_line": i - 1})
                    i += 1
                if code_load:
                    i += 1
        i += 1                                           # text
        self.gravity_line = i

    # -- editing --------------------------------------------------------
    def set_gravity(self, gravy=None, factg=None, factf=None):
        tk = self._tk(self.gravity_line)
        n = self.ndimn
        if len(tk) < 1 + 2 * n:
            raise HstarInputError(
                f"{self.path}:{self.gravity_line + 1} has {len(tk)} tokens, HSTAR reads "
                f"gravy + factg(1:{n}) + factf(1:{n}) = {1 + 2 * n}")
        if gravy is not None:
            if not 0 <= float(gravy) <= 100:
                raise HstarInputError(
                    f"gravy={gravy} m/s2 is implausible; SI gravity is 9.81. A value near "
                    f"9810 means mm were used for length (triplet dt_006).")
            tk[0] = f"{float(gravy):.5E}"
        if factg is not None:
            if len(factg) != n:
                raise HstarInputError(f"factg needs ndimn={n} components")
            for k, v in enumerate(factg):
                tk[1 + k] = f"{float(v):.5E}"
        if factf is not None:
            if len(factf) != n:
                raise HstarInputError(f"factf needs ndimn={n} components")
            for k, v in enumerate(factf):
                tk[1 + n + k] = f"{float(v):.5E}"
        self.lines[self.gravity_line] = "  " + "  ".join(tk)
        return self

    def set_water(self, cor0=None, cor1=None, p0=None, p1=None, fact=None, which=None):
        """Edit the hydrostatic-pressure record(s): cor0 cor1 p0 p1 fact."""
        if not self.water_records:
            raise HstarInputError(
                "this .loa has no `water/=0` edge-load group, so there is no hydrostatic "
                "pressure record to edit. Add the edge group first (COPY it from "
                "cases/static or cases/train01_gravdam_static).")
        targets = self.water_records if which is None else [self.water_records[which]]
        for wr in targets:
            tk = self._tk(wr["line"])
            if len(tk) < 5:
                raise HstarInputError(
                    f"{self.path}:{wr['line'] + 1} has {len(tk)} tokens, HSTAR reads "
                    f"cor0 cor1 p0 p1 fact")
            for k, v in enumerate([cor0, cor1, p0, p1, fact]):
                if v is not None:
                    tk[k] = f"{float(v):.5E}"
            self.lines[wr["line"]] = "  " + "  ".join(tk)
        return self

    def save(self):
        write_lines(self.path, self.lines, self.eol)
        return self.path

    def describe(self):
        return {
            "path": str(self.path), "ndimn": self.ndimn, "ngroup": self.ngroup,
            "curves": [{"id": k + 1, "type": c["type"], "ntime": c["ntime"],
                        "line": c["line"] + 1} for k, c in enumerate(self.curves)],
            "point_load_groups": [{"line": p["line"] + 1, "npload": p["npload"],
                                   "pxyz": self._tk(p["pxyz_line"])}
                                  for p in self.point_loads],
            "edge_groups": [{k: v for k, v in e.items() if k != "line"}
                            for e in self.edge_groups],
            "hydrostatic_records": [
                {"line": w["line"] + 1,
                 "cor0_m": self._tk(w["line"])[0], "cor1_m": self._tk(w["line"])[1],
                 "p0_Pa": self._tk(w["line"])[2], "p1_Pa": self._tk(w["line"])[3],
                 "fact": self._tk(w["line"])[4]} for w in self.water_records],
            "gravity": {"line": self.gravity_line + 1,
                        "gravy_m_s2": self._tk(self.gravity_line)[0],
                        "factg": self._tk(self.gravity_line)[1:1 + self.ndimn],
                        "factf": self._tk(self.gravity_line)[
                            1 + self.ndimn:1 + 2 * self.ndimn]},
        }


def set_reservoir_level(case, level_m, block=None):
    """Raise/lower the reservoir: `cor0` in .loa AND `water_level` in .glb, together."""
    lo = Loa(case)
    lo.set_water(cor0=level_m).save()
    probn = probn_of(case)
    g = GlbDoc(Path(case) / f"{probn}.glb")
    li = g.find("water_level")
    vals = tokens(g.lines[li + 1])
    idxs = range(len(vals)) if block is None else [block]
    for k in idxs:
        if k < len(vals):
            vals[k] = f"{float(level_m):.5E}"
    g.lines[li + 1] = "  " + "  ".join(vals)
    g.save()
    return {"loa": str(lo.path), "glb_water_level_line": li + 2, "level_m": float(level_m),
            "note": "both .loa cor0 and .glb water_level were updated -- changing only "
                    "one is triplet dt_010"}


def set_uplift(case, upliftin):
    """Turn the uplift-pressure model on/off (capability 22). Writes <probn>.upf when on."""
    probn = probn_of(case)
    g = GlbDoc(Path(case) / f"{probn}.glb")
    before = g.get("upliftin")
    g.set("upliftin", int(upliftin)).save()
    return {"upliftin": {"from": before, "to": str(int(upliftin))},
            "effect": "HSTAR opens <probn>.upf (binary) and subtracts the uplift pressure "
                      "from the effective normal stress on the declared surfaces"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--gravity", nargs="+", type=float,
                    metavar="G DX DY [DZ]", help="gravity magnitude then direction cosines")
    ap.add_argument("--water", nargs=5, type=float,
                    metavar=("COR0", "COR1", "P0", "P1", "FACT"))
    ap.add_argument("--water-level", type=float,
                    help="reservoir surface elevation (m) -- edits .loa AND .glb")
    ap.add_argument("--uplift", type=int, choices=[0, 1])
    a = ap.parse_args(argv)
    out = {}
    if a.gravity:
        lo = Loa(a.case)
        lo.set_gravity(gravy=a.gravity[0], factg=a.gravity[1:1 + lo.ndimn])
        lo.save()
        out["gravity"] = lo.describe()["gravity"]
    if a.water:
        lo = Loa(a.case)
        lo.set_water(*a.water).save()
        out["water"] = lo.describe()["hydrostatic_records"]
    if a.water_level is not None:
        out["reservoir"] = set_reservoir_level(a.case, a.water_level)
    if a.uplift is not None:
        out["uplift"] = set_uplift(a.case, a.uplift)
    if a.describe or not out:
        out["describe"] = Loa(a.case).describe()
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
