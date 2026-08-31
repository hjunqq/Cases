"""Upgrade mini_gravdam LOA: add upstream water pressure in Block 2.
Water level at dam top (y=60m), triangular pressure on upstream face (x=16m).
Only modifies 1.LOA — run gen_all.py first, then this.
"""
import os, json

outdir = os.path.dirname(os.path.abspath(__file__))

# Read mesh info to find upstream edges
coords = {}
with open(os.path.join(outdir, "1.cor")) as f:
    for line in f:
        p = line.split()
        if len(p) >= 3:
            try: coords[int(p[0])] = (float(p[1]), float(p[2]))
            except: pass

elements = []
with open(os.path.join(outdir, "1.ele")) as f:
    for line in f:
        p = line.split()
        if len(p) >= 5:
            try: elements.append((int(p[0]), [int(x) for x in p[1:5]]))
            except: pass

# Foundation = elements 1-20, Dam = elements 21-32
nfound = 20

# Find upstream edges: dam elements where two nodes have x=16 (left face of dam)
wp_edges = []
for eid, ns in elements[nfound:]:
    left_nodes = [n for n in ns if abs(coords[n][0] - 16.0) < 0.1]
    if len(left_nodes) == 2:
        # Sort by y to get bottom→top ordering
        left_nodes.sort(key=lambda n: coords[n][1])
        wp_edges.append((left_nodes[0], left_nodes[1], eid))

print(f"Found {len(wp_edges)} upstream water pressure edges")
for n1, n2, eid in wp_edges:
    print(f"  Edge: nodes {n1}(y={coords[n1][1]:.0f}) → {n2}(y={coords[n2][1]:.0f}), elem {eid}")

nedge = len(wp_edges)
water_level = 60.0  # dam top

# Write 1.LOA with water pressure in Block 2
L = []
L.append(" (*.loa) Load data")
L.append("  1")
L.append("  2  LINEAR  0  2")
L.append("  0.0  1.0")
L.append("  1.0  1.0")
L.append(" Define point load")
L.append("  0  0")

# Edge definitions (read ONCE, used for all blocks)
L.append(" Define edges for whole analysis")
L.append(f"  {nedge}")
if nedge > 0:
    L.append(" sedge nnode index vdimn")  # text header required!
    L.append(f"  {nedge}  2  1  0")
    for i, (n1, n2, eid) in enumerate(wp_edges):
        L.append(f"  {i+1}  {n1}  {n2}  {eid}")

# Block 1: gravity only, no water pressure
L.append(" Define edge load in each BLKS")
L.append(" edge_load_group,delgroup")
L.append("  0  0")
L.append(" Define body force in each BLKS")
L.append("  9.81000E+00  0.00000E+00  -1.00000E+00  0.00000E+00  -1.00000E+00")
L.append(" Time_curve_for_each_group  1")
L.append("  1  1")
L.append(" nbeamload")
L.append("  0")
L.append(" nplateload")
L.append("  0")

# Block 2: gravity + upstream water pressure
L.append(" Define edge load in each BLKS")
L.append(" edge_load_group,delgroup")
if nedge > 0:
    L.append(f"  {nedge}  1")  # lineload=nedge, delgroup=1
    L.append(f"  1  {nedge}  1  2  0")  # begin end itcurve water_dir=2(y) code_load=0
    L.append(f"  {water_level}  0  0  {water_level}  9810.0")  # ws1 cor0 cor1 ws2 gamma_w
else:
    L.append("  0  0")
L.append(" Define body force in each BLKS")
L.append("  9.81000E+00  0.00000E+00  -1.00000E+00  0.00000E+00  -1.00000E+00")
L.append(" Time_curve_for_each_group  1")
L.append("  1  1")
L.append(" nbeamload")
L.append("  0")
L.append(" nplateload")
L.append("  0")

with open(os.path.join(outdir, "1.LOA"), "w") as f:
    f.write("\n".join(L) + "\n")
print("  Updated 1.LOA with water pressure")
