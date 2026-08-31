# Stage s2 — Mesh: coordinates, connectivity and element groups

## Purpose
Supply the geometry (`*.cor`), the connectivity (`*.ele`) and the element-group
stanzas of `*.glb` that tell HSTAR which element formulation to use.

## Inputs
- A mesh from any source: the built-in generators, a GiD `*.flavia.msh`, or an
  external mesher exported to two tables
- The element type, in **metres**

## Outputs
- `1.cor` — `ipoin  x  y [z]`, one record per node, `npoin` records
- `1.ele` — `ielem  n1..nN  igroup`, one record per element, `nelem` records
- `1.glb` first record (`npoin npoinb nelem ndimn ... ngroup`) and the group
  stanzas (`name`, `index`, `nelgroup`) kept in sync

## Procedure
```bash
python3 tools/write_mesh.py --case case1 --shape column --width 1 --height 10 --ny 20
python3 tools/write_mesh.py --case case1 --shape annulus --r_in 1 --r_out 2 --nx 8 --ny 8
python3 tools/write_mesh.py --case case1 --shape box3d --lx 4 --ly 2 --lz 1 --nx 8 --ny 4 --nz 2
python3 tools/write_mesh.py --case case1 --from-flavia old_case/1.flavia.msh
```

### The element library
26 entries. The group stanza carries BOTH a name and a library index; the index
is what `Elements.f90:1068` actually uses.

| idx | name | nodes | dim | fields | idx | name | nodes | dim | fields |
|---|---|---|---|---|---|---|---|---|---|
| 1 | l2 | 2 | 1 | 1 | 14 | b20c8 | 20 | 3 | 2 |
| 2 | l3 | 3 | 1 | 1 | 15 | t3c3 | 3 | 2 | 2 |
| 3 | t3 | 3 | 2 | 1 | 16 | q4c4 | 4 | 2 | 2 |
| 4 | t6 | 6 | 2 | 1 | 17 | h4c4 | 4 | 3 | 2 |
| 5 | q4 | 4 | 2 | 1 | 18 | b8c8 | 8 | 3 | 2 |
| 6 | q8 | 8 | 2 | 1 | 19 | l2c2 | 2 | 1 | 2 |
| 7 | h4 (tet4) | 4 | 3 | 1 | 20 | b2 (beam) | 2 | 1 | 1 |
| 8 | h10 (tet10) | 10 | 3 | 1 | 21 | b2c2 | 2 | 1 | 2 |
| 9 | b8 (hex8) | 8 | 3 | 1 | 22 | p4 | 4 | 2 | 1 |
| 10 | b20 (hex20) | 20 | 3 | 1 | 23 | pr6 (wedge) | 6 | 3 | 1 |
| 11 | t6c3 | 6 | 2 | 2 | 24 | pr6c6 | 6 | 3 | 2 |
| 12 | q8c4 | 8 | 2 | 2 | 25 | steel | 2 | 1 | 1 |
| 13 | h10c4 | 10 | 3 | 2 | 26 | thin_film | 4 | 2 | 1 |

`*cN` entries carry a second physical field (U–W or U–T); N is the node count of
that second, lower-order field. Only these can hold pore pressure — a plain `q4`
group declared `fieldid='UW'` allocates no pressure DOF (`dt_017`).

`special='BB'`/`'BC'` enables Simo–Rifai incompatible-mode bending enrichment,
and is only meaningful for indices 3, 5, 9, 16, 18.

## Verification
`write_mesh.py` runs four post-checks before writing:
1. node ids are `1..npoin` contiguous, element ids `1..nelem` ascending;
2. elements sorted by group ascending, no interleaving;
3. every element node exists and every node is referenced by some element;
4. every 2-D quad/triangle has a **positive** signed area.

Then read `1.chk` after the run: it echoes `tvol` (total volume) and `tne` per
group. A group volume that does not match the geometry means the connectivity
was mis-assigned.

## Traps
- Name/index mismatch — `Q4` written with index 9 makes HSTAR read 8 nodes from
  a 4-node table (`dt_006`).
- Elements not sorted by group: silently attributed to the wrong group, so
  staged construction switches off the wrong elements (`dt_007`).
- Clockwise connectivity gives a negative Jacobian; HSTAR does not check, the
  solver reports a bad pivot (`dt_008`).
- Index 22 is claimed by both `p4` and `thin_film` in the source; declare
  thin-film groups as 26 (`dt_014`).
- `npoinb` is the id of the FIRST beam-element node, not a count. Equal to
  `npoin` when there are no beam elements.
- 3-D hexahedra must follow the standard bottom-face-then-top-face ordering; the
  generator and the face extractor in `write_loads.py` both assume it.

## Example
Verified 2026-08-26 — the quarter-annulus generator reproduces the shipped
`lame_cylinder` mesh exactly (81 nodes, 64 Q4, node 1 at (1.0, 0.0), inner-radius
nodes 1, 10, 19, …, 73), which is what makes the Lamé benchmark in
`docs/s7_postprocessing.md` a like-for-like comparison.
