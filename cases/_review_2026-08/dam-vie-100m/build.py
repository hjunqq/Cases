#!/usr/bin/env python3
"""Build the H=100 m gravity-dam VIE dynamic deck end to end.

  generator.generate_all()  ->  hand-patch the two VIE sections  ->  ready to solve

The two patches exist because skills/generator.py does not write them:
  * 1.ifs  nabssgroup   (viscous-spring absorbing edges)
  * 1.pre  nbounods     (free-surface elevation table)
and, for the W-field reservoir, because generator's tp=="F" branch fires before
the FSI branch and therefore never enables the pore/acoustic DOF 8.
"""
import json, subprocess, sys
from pathlib import Path

FEM = Path("/home/huijun/HSTAR_Next/fem-chat")
sys.path.insert(0, str(FEM / "skills"))
CASE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/claude-1000/dam-vie/case")
WATER_MODE = sys.argv[2] if len(sys.argv) > 2 else "wfield"   # wfield | massonly

import generator  # noqa: E402

cfg = json.loads((CASE / "config.json").read_text())

if WATER_MODE == "massonly":
    # Reservoir as displacement-based fluid elements: real Q4 water elements
    # carrying water mass and water bulk stiffness -- NOT Westergaard added mass.
    #   nu = 0.49  ->  K0 = nu/(1-nu) = 0.96, so the static lateral push on the
    #                  dam face is 96 % of true hydrostatic (no separate
    #                  hydrostatic edge load is applied, to avoid double counting)
    #   E  = 1.24e8 with nu = 0.49  ->  K = E/(3(1-2nu)) = 2.07e9 Pa (water bulk)
    #                  and G = E/(2(1+nu)) = 4.2e7 Pa, the small spurious shear
    #                  stiffness that is the known cost of a displacement-based
    #                  fluid element.  c_p = sqrt((K+4G/3)/rho) = 1459 m/s (water).
    cfg["groups"][2].pop("field", None)
    cfg["materials"][2] = {"id": 3, "type": "ELASTIC", "E": 1.24e8, "nu": 0.49,
                           "density": 1000.0}
    cfg.pop("fsi", None)
    cfg["solver"] = "PARDISO"
else:
    cfg["solver"] = "PROFILE"     # nifsgroup U-W coupling is dropped by PARDISO
    cfg["fsi"] = {"use_meta_edges": True}

# --- inject the seismic time series (run_pipeline does this; generate_all does NOT) ---
# Without this the generator writes each SEISMIC curve as two constant 1.0 points:
# the deck solves, but the "earthquake" is a constant unit incident wave.
for tc in cfg.get("time_curves", []):
    if tc.get("type") == "SEISMIC" and tc.get("file"):
        f = CASE / tc["file"]
        if not f.exists():
            raise SystemExit(f"missing wave file {f}")
        vals = [float(x) for x in f.read_text().split() if x.strip()]
        dt = tc.get("dt", 0.01)
        tc["times"] = [i * dt for i in range(len(vals))]
        tc["values"] = vals
        tc["dtrec"], tc["dtbegin"] = dt, 0
        tc["dtend"] = (len(vals) - 1) * dt
        tc["ample"] = 1.0
        print(f"loaded {len(vals)} points from {tc['file']} "
              f"(peak {max(abs(v) for v in vals):.4g})")
        del tc["file"]

generator.generate_all(str(CASE), cfg)

# --- patch MDOFN / lmdofn / order_time_mdofn for the coupled dynamic FSI case ---
if WATER_MODE == "wfield":
    glb = (CASE / "1.glb").read_text().splitlines()
    i = next(k for k, l in enumerate(glb) if l.strip() == "MDOFN")
    glb[i + 1] = "  8"
    glb[i + 2] = "  1  1  0  0  0  0  0  1"      # lmdofn: ux uy + W(dof 8)
    glb[i + 3] = "  2  2  0  0  0  0  0  2"      # order_time_mdofn
    (CASE / "1.glb").write_text("\n".join(glb) + "\n")
    print("patched MDOFN block for U+W dynamic FSI")

subprocess.check_call([sys.executable, "/tmp/claude-1000/dam-vie/patch_vie.py", str(CASE)])
print("deck ready:", CASE)
