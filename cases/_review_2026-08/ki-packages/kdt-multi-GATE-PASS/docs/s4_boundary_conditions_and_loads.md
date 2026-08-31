# s4 — Boundary conditions and loads

## Purpose

Constrain the structure and apply gravity, water pressure, point loads, prescribed
displacements, temperature loads, uplift and earthquake input.

## Inputs

Support node sets, the reservoir level, load magnitudes, time curves.

## Outputs

`<probn>.pre` (prescribed variables), `<probn>.loa` (loads and time curves), and the
`water_level` / `hdam` / `upliftin` fields in `<probn>.glb`.

## Procedure

### `<probn>.pre` — prescribed variables (`Prescrib.f90:183-250`)

**One complete group of records per load block.**

```
text                                                   header
nfixsets  nline
  repeat nfixsets times:
    ifixvar nfixnods itcurve tfixvar outfix jfixvar gamawx nextr     (type_ABC /= 'MIF')
    ifixvar ifixvar0 nfixnods itcurve tfixvar outfix jfixvar gamawx nextr   ('MIF')
    list_fix(1:nfixnods)
    val_fix(1:nfixnods)                                `11*0.` repeat form is legal
```

`ifixvar` is the DOF index — `Global.f90` `title(1:10)`:

| 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|
| Ux | Uy | Uz | Thx | Thy | Thz | Hydrostatic_pressure | Pore_Pressure | Air_Pressure | Temperature |

`gamawx` is the water unit weight in N m⁻³, used when the set prescribes a pressure/head
DOF. The shipped cases use `0.980E+04`.

### `<probn>.loa` — loads (`Load.f90:134-960`)

```
text ; ntcurve
  per curve: ntime type_curve nstoch_curve nline
             [order_stoch_parameter]                 if nstoch_curve /= 0
             <type-specific record(s)>
             ttime_curve(1:ntime)                    default types (e.g. LINEAR)
             dfact_curve(1:ntime)
text ; nplgroup kpload                                point loads
  kpload==1: per group  order_time_curve nudofn npload nline
                        pxyz(1:nudofn)               N
                        list(1:npload)
text ; nedge                                          edge/face definitions
  per edge group: text ; sedge nnode index vdimn ; sedge x (i0 lnode(1:nnode) aelem)
text ; text ; edge_load_group delgroup
  per delgroup: begin_edge end_edge itcurve water code_load
                [cor0 cor1 p0 p1 fact]                if water /= 0
                [cor01 cor11 p01 p11 fact1]           if code_load /= 0
text ; gravy factg(1:ndimn) factf(1:ndimn)            gravity / body force
text nline ; tcurvegravity(1:ngroup)
text ; nbeamload
text ; nplateload
```

**Time-curve types** (`Load.f90:162-215`): `HARMONIC`, `FOURIERSERIES`, `WATERLEVEL`,
`SEISMIC`, `EXTRAPOLATION`, `ARCLENGTH`, and a default branch (`LINEAR` and anything else)
that reads a time vector followed by a factor vector.

**Hydrostatic pressure.** For a `water /= 0` group, `Load.f90:800` evaluates

```
press = -( p0 + (cor0 - x) / (cor0 - cor1) * (p1 - p0) ) * fact
```

`cor0`/`cor1` are elevations in m; `p × fact` is a pressure in Pa. `cases/static` ships
`40 0 0 40 9810`: head in metres in `p0`/`p1` and γ_w = 9810 N m⁻³ in `fact`. Putting Pa in
`p1` while leaving `fact = 9810` inflates the load 9810× (`dt_011`).

**Gravity.** `gravy factg(1:ndimn) factf(1:ndimn)`: magnitude in m s⁻², then direction
cosines for the solid and the fluid phase. 2-D downward is `9.81 0 -1 0 -1`.

**Uplift** is a separate mechanism: `upliftin` in `.glb`, per-group `uplift_ic`, and the
binary `<probn>.upf`.

## Verification

```bash
python3 tools/build_boundary_conditions.py --case /tmp/c --describe
python3 tools/build_loads.py --case /tmp/c --describe
```

`build_loads.Loa` replays the whole read sequence, so `hydrostatic_records` and
`gravity` report the FILE LINE each value sits on — check that line by eye before trusting
an edit.

**Prove a load actually does something.** HSTAR silently ignores a load whose parent
element group is not `appear` in that block. The decisive test:

```bash
python3 tools/build_loads.py --case /tmp/c2 --water 40 0 0 40 0.0   # fact -> 0
python3 tools/run_hstar.py --case /tmp/c2 --outdir /tmp/r2
# then diff DISPLACEMENT between /tmp/r1 and /tmp/r2
```

If the displacements are bit-identical, the load was already contributing nothing. This is
exactly what happens in `cases/static` (verified 2026-08-26) — see triplet `dt_024`.

## Traps

- **`.pre` repeats per load block.** `cases/static` has `nblks=2` and its `.pre` contains the
  whole PRESCRIBE SET group twice. Adding a block without appending a group gives
  `forrtl: severe (24)` at the start of block 2, after block 1 has already written output
  (`dt_007`).
- **`gamawx` in kN m⁻³** (9.8 instead of 9800) makes every prescribed pressure 1000× too
  small (`dt_008`).
- **Reservoir level lives in two places** — `cor0` in `.loa` and `water_level(1:nblks)` in
  `.glb`. `build_loads.set_reservoir_level` writes both; editing one alone is `dt_010`.
- **A `SEISMIC` accelerogram is in m s⁻².** A record in g must be multiplied by 9.81, or
  scaled with the `ample` field on the curve's parameter record.
- **`1.LOA` and `1.loa` both exist in several shipped cases.** Linux is case-sensitive and
  HSTAR opens the lowercase name. Editing `1.LOA` changes nothing.

## Example

```bash
$ python3 tools/build_loads.py --case /tmp/c --water-level 35.0
{ "reservoir": { "loa": "/tmp/c/1.loa", "glb_water_level_line": 53, "level_m": 35.0,
                 "note": "both .loa cor0 and .glb water_level were updated" } }
```
