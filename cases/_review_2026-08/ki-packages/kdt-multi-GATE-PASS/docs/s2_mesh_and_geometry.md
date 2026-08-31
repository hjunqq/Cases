# s2 — Mesh, element groups and geometry

## Purpose

Supply the geometry: nodes, connectivity, element-type declaration and the group partition
that staged construction and material assignment both key on.

## Inputs

- Node coordinates (m) — from the analyst's mesher (GiD, Gmsh, ANSYS, ABAQUS export).
- Element connectivity in HSTAR's local node order for the declared element type.
- A group id per element.

## Outputs

- `<probn>.cor` — `ipoin x y [z]`, one record per node, `npoin` records.
- `<probn>.ele` — `ielem n1 … n_nnode igroup`, one record per element, `nelem` records.
- Updated `npoin`, `npoinb`, `nelem` and the per-group `nelgroup` in `<probn>.glb`.

## Procedure

```python
from build_mesh_files import write_mesh
write_mesh(case_dir,
           coords=[(x1, y1), (x2, y2), ...],       # metres
           elements=[(n1, n2, n3, n4), ...],       # 1-based, CCW for Q4
           groups=[1, 1, 2, ...],
           element_index=5)                         # 5 = Q4
```

`write_mesh` validates, writes, and then re-reads and cross-checks; it also updates
`nelgroup` on every group declaration line so the `.ele` group column and `.glb` agree.

### Element library (`Elements.f90:128-153`, `kinddefine`)

| idx | name | nodes | dim | note |
|---|---|---|---|---|
| 1 | L2 | 2 | 1 | bar / truss |
| 2 | L3 | 3 | 1 | |
| 3 | T3 | 3 | 2 | constant-strain triangle |
| 4 | T6 | 6 | 2 | |
| 5 | Q4 | 4 | 2 | bilinear quad — the workhorse |
| 6 | Q8 | 8 | 2 | serendipity |
| 7 | H4 | 4 | 3 | linear tetrahedron |
| 8 | H10 | 10 | 3 | |
| 9 | B8 | 8 | 3 | trilinear hexahedron |
| 10 | B20 | 20 | 3 | |
| 11–19 | T6C3 … L2C2 | | | **u-p coupled** pairs of the above |
| 20 | B2 | 2 | 1 | Euler-Bernoulli beam (2-D 3 DOF/node, 3-D 6) |
| 21 | B2C2 | 2 | 1 | beam + contact field |
| 22 | P4 | 4 | 2 | plate (membrane + bending + transverse shear) |
| 23 | PR6 | 6 | 3 | prism / wedge |
| 24 | PR6C6 | 6 | 3 | prism, u-p coupled |
| 25 | STEEL | 2 | 1 | rebar / spring with bond-slip |
| 26 | THIN_FILM | 4 | 2 | thin contact layer (2023) |

### The group declaration block in `.glb`

One block per group, after `average_appear`:

```
NAME KNAME INDEX CLASS NRFIELDS FIELDID SPECIAL SPTYPE NELGROUP MATNO TYPE_ALGO
     TYPE_STIFF TYPE_ECOINT ilayer elcod_local group_inf uplift_ic liquj
TYPE_MASS(1:NRFIELDS)
nfdof  listdof(1:nfdof)        <- one such line per field
```

Example from `cases/static`:

```
Q4    GROUP1         5 CO     1 U     ST   PE          300  1  0  1  1  1   0.000E+00  0  0  0
           0           0           0
         0         0         0         0         0         0         0         0
         2
         1         2
```

- `INDEX` is the element-library index above — it, not `NAME`, is what HSTAR dispatches on.
- `FIELDID` is `U` (displacement), `P`, `W` (water) or `T` (temperature). A thermal or
  seepage run needs a group whose `FIELDID` is `T`/`W`.
- `NELGROUP` must equal the number of `.ele` records carrying that group id.
- `SPTYPE` is `PE` (plane strain), `PS` (plane stress), `AX` (axisymmetric) in 2-D.
- The last line lists which DOF of the field this group carries (`2 / 1 2` = two DOF, Ux Uy).

## Verification

```bash
python3 tools/build_mesh_files.py --case /tmp/c --describe   # counts + bounding box
python3 tools/build_mesh_files.py --case /tmp/c --check      # exits 1 on a mismatch
```

The check reports `elements_per_group` and compares it with each group's declared
`nelgroup`, and it verifies that the node count per element matches the declared element
index.

## Traps

- **Node order matters.** Q4 must be counter-clockwise; a clockwise element produces a
  negative Jacobian. HSTAR does not always stop — it can produce a negative-definite
  element stiffness that PARDISO reports as "tiny pivot" much later, or simply wrong
  stresses.
- **Mixed element types must be in separate groups.** HSTAR reads a fixed node count per
  group from the element index.
- **`npoinb`** (boundary/original node count) is set equal to `npoin` in every shipped case
  and is used by the mesh-refinement path; keep them equal unless `rmesh /= 0`.
- **Too many `.ele` records is silent.** HSTAR reads exactly `nelem` and ignores the rest —
  you get a smaller structure than the file describes.
- **Coordinates are in whatever unit you choose, but everything else must match.** See s3
  and §0.2 of `input_preparation.md`.

## Example

```bash
$ python3 tools/build_mesh_files.py --case /tmp/c --check
{ "npoin": 462, "nelem": 410,
  "elements_per_group": {"1": 300, "2": 100, "3": 10},
  "groups": [{"keyword": "Q4", "index": 5}, ...],
  "problems": [], "ok": true }
```
