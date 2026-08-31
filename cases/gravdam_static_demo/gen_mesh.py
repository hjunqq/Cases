"""Generate mesh for gravity dam static analysis demo.

Geometry (2D plane strain):
  - Foundation: 120m wide x 60m deep (6 cols x 4 rows = 24 Q4)
  - Dam body:   top width 8m, bottom width 72m, height 80m
    Trapezoidal profile, 4 cols x 5 rows = 20 Q4

Coordinate system: x = horizontal, y = vertical (up positive)
  Foundation bottom: y = -60
  Foundation top / dam base: y = 0
  Dam crest: y = 80

         8m
       +----+
      /      \
     /  Dam   \      80m
    /   Body   \
   /            \
  +--------------+   <- y=0 (dam base)
  |              |
  |  Foundation  |   60m deep
  |              |
  +==============+   <- y=-60 (bottom, fixed Uy)
  x=0          x=120
"""
import os

outdir = os.path.dirname(os.path.abspath(__file__))

def write(name, content):
    with open(os.path.join(outdir, name), "w") as f:
        f.write(content)
    print(f"  wrote {name}")

# ============================================================
# Foundation mesh: 120m wide x 60m deep
# 7 x-nodes x 5 y-nodes = 35 nodes, 6x4 = 24 Q4 elements
# ============================================================
fx = [0.0, 20.0, 40.0, 60.0, 80.0, 100.0, 120.0]  # 7 columns
fy = [-60.0, -45.0, -30.0, -15.0, 0.0]               # 5 rows

nodes = {}
nid = 0
fnode = {}  # (ix, iy) -> nid
for iy, y in enumerate(fy):
    for ix, x in enumerate(fx):
        nid += 1
        nodes[nid] = (x, y)
        fnode[(ix, iy)] = nid

# ============================================================
# Dam body mesh: trapezoidal cross-section
# Base width 72m centered at x=60 -> x=[24, 96] at y=0
# Crest width 8m centered at x=60  -> x=[56, 64] at y=80
# 5 x-nodes per row, 6 y-rows (y=0 shared with foundation top)
# ============================================================
dam_rows = 6  # y levels including base
dam_cols = 5  # x nodes per row
dam_y = [0.0, 16.0, 32.0, 48.0, 64.0, 80.0]
# x coordinates taper linearly from base to crest
dam_x_left  = [24.0, 30.4, 36.8, 43.2, 49.6, 56.0]
dam_x_right = [96.0, 89.6, 83.2, 76.8, 70.4, 64.0]

dnode = {}  # (ix, iy) -> nid
for iy in range(dam_rows):
    xl = dam_x_left[iy]
    xr = dam_x_right[iy]
    xs = [xl + (xr - xl) * j / (dam_cols - 1) for j in range(dam_cols)]
    for ix, x in enumerate(xs):
        if iy == 0:
            # Share with foundation top row: find nearest foundation node
            best = None
            for fix in range(len(fx)):
                if abs(fx[fix] - x) < 0.5:
                    best = fnode[(fix, len(fy) - 1)]
                    break
            if best is None:
                # Dam node not on foundation grid -> create new node
                nid += 1
                nodes[nid] = (x, 0.0)
                dnode[(ix, iy)] = nid
            else:
                dnode[(ix, iy)] = best
        else:
            nid += 1
            nodes[nid] = (x, dam_y[iy])
            dnode[(ix, iy)] = nid

npoin = len(nodes)

# Foundation elements: 6 cols x 4 rows = 24 Q4
elements = []
for iy in range(len(fy) - 1):
    for ix in range(len(fx) - 1):
        n1 = fnode[(ix, iy)]
        n2 = fnode[(ix + 1, iy)]
        n3 = fnode[(ix + 1, iy + 1)]
        n4 = fnode[(ix, iy + 1)]
        elements.append((n1, n2, n3, n4))
nfound = len(elements)

# Dam body elements: 4 cols x 5 rows = 20 Q4
for iy in range(dam_rows - 1):
    for ix in range(dam_cols - 1):
        n1 = dnode[(ix, iy)]
        n2 = dnode[(ix + 1, iy)]
        n3 = dnode[(ix + 1, iy + 1)]
        n4 = dnode[(ix, iy + 1)]
        elements.append((n1, n2, n3, n4))
ndam = len(elements) - nfound

nelem = len(elements)
print(f"Mesh: {npoin} nodes, {nelem} elements (foundation={nfound}, dam={ndam})")

# ---- Write 1.cor ----
cor = []
for n in sorted(nodes):
    x, y = nodes[n]
    cor.append(f"  {n}  {x:.6f}  {y:.6f}")
write("1.cor", "\n".join(cor) + "\n")

# ---- Write 1.ele ----
ele = []
for eid, (n1, n2, n3, n4) in enumerate(elements, 1):
    ele.append(f"  {eid}  {n1}  {n2}  {n3}  {n4}")
write("1.ele", "\n".join(ele) + "\n")

print(f"\nFoundation elements: 1-{nfound}")
print(f"Dam body elements:   {nfound+1}-{nelem}")
print(f"Set nelgroup in problem.toml: Foundation={nfound}, DamBody={ndam}")
