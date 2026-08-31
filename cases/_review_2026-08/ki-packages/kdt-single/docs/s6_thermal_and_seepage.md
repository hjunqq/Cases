# Stage s6 — Thermal field, thermal stress, seepage and uplift

## Purpose
Configure the two non-mechanical fields HSTAR solves, and the two ways each of
them talks back to the stress field.

## Inputs
- Thermal: diffusivity, convection surfaces and their film coefficient, ambient
  air temperature curve, adiabatic hydration rise curve, placing temperature
- Seepage: permeability, head boundary conditions, drainage condition
- Uplift: reservoir elevation per run block

## Outputs
- Thermal field pass → `1.flavia.res` block `TEMPERATURE`, binary `1.oit`
- Thermal stress pass → `DISPLACEMENT` / `STRESS` including thermal strain
- Seepage → `PORE-PRESSURE`, `Excess_PORE-PRESSURE`, binary `1.oip`
- Uplift → `1.upf`, and a reduced effective self weight

## Procedure

### Thermal, two passes
The thermal manual is explicit: temperature stress is computed **in two runs**.

Pass 1, temperature field only:
```
.glb : type_problem='S', type_nl=10, mdofn=10, lmdofn(10)=1,
       order_time(10)=1, outintw=1, outintr=0
group: nrfields=1, fieldid='T', field DOF list = (10)
.mat : a 'HEAT','SOLID' entry -- a(1:3) in m^2/day, adiabatic curve id,
       placing-temperature curve id
.tem : convection surfaces and the ambient-temperature curve
```
```bash
python3 tools/write_thermal.py --case thermal1 --field-pass \
    --diffusivity 0.0864 --curve-adiabatic 3 --curve-place 1 \
    --convection "where=y>19.99;beta_bar=1.2;curve=2"
```

Pass 2, stress reading `*.oit` back as a body load:
```
.glb : type_problem='Q', type_nl=5, mdofn=10,
       lmdofn = 1 1 1 0 0 0 0 0 0 1, order_time all 0,
       outintr=<first block that reads .oit>, outintw=0
group: nrfields=2, fieldid='UT', DOF lists (1 2 3) and (10)
.man : IDENTICAL to pass 1
.tem : convection surfaces REMOVED (count 0)
```
```bash
python3 tools/write_thermal.py --case stress1 --stress-pass \
    --oit ../thermal1/1.oit --outintr 1 --ref-man ../thermal1/1.man
```

`*.tem` record sequence:
```
' temperature prescribed data' / n
' surface convection edges (nedge)' / nedge
' sedge,nnode,index,beta_bar' / sedge nnode index beta_bar
<sedge records: i0  n1..nN  aelem>
' edge temperature bondary' / sedge
' sedge,itcurve,nline' / sedge itcurve nline
' pipe cooling info' ...
```
`beta_bar = β/(cρ) = a·β/λ`, in **m/day** — it is the film coefficient divided
by the volumetric heat capacity, not the raw W/m²K value. For a concrete face
in still air β ≈ 20–30 W/m²K, λ ≈ 2.3 W/m·K, a ≈ 0.0864 m²/day, giving
beta_bar ≈ 0.75–1.1 m/day.

Curve types this stage needs (written by `write_loads.py`): `SIN` for ambient
air temperature, `DABT` for adiabatic hydration rise, `LINEAR` for a measured
series.

### Cooling pipes
```bash
python3 tools/write_thermal.py --case thermal1 \
    --pipes "group_c=1;group_w=2;Qw=1.2;Tw_curve=4;begin_time=0;end_time=20"
```
Sets `ECWPIPE=1` in `.glb` and writes the `nwcpipe` stanza
(`Global.f90:4402-4433`): concrete group, pipe group, flow rate, water thermal
properties, start/end time and the inlet-temperature curve.

### Seepage
Three distinct configurations, chosen explicitly:

| mode | what it does | key flags |
|---|---|---|
| `field` | flow alone, Laplace (steady) or θ-method (transient) | DOF 8 only, `uwcpl=0`, `outinp=1` to dump `*.oip` |
| `coupled` | Biot u–p solved monolithically | DOFs (1..ndimn, 8), `nrfields=2`, `fieldid='UW'`, `uwcpl=1` undrained or `2` drained, two-field element |
| `readback` | stress run reading a previous `*.oip` | `outinp=1`, `*.oip` present |

```bash
python3 tools/write_seepage.py --case seep1 --mode field --steady
python3 tools/write_seepage.py --case biot1 --mode coupled --uwcpl 2 --etype q4c4
```
Head boundary conditions are ordinary `.pre` sets on DOF 8; the prescribed value
is a **pressure head in metres**, converted internally with `gamawx` from the
`.pre` record.

`stabpw=1` selects the stabilised formulation, which is what makes equal-order
u–p interpolation (`q4c4`) admissible.

### Uplift
```bash
python3 tools/write_seepage.py --case dam1 --uplift --water-level 60.0
```
Sets `upliftin=1` and `water_level(1:nblks)`. The level is an **elevation in the
mesh datum**, in metres.

## Verification
- `write_thermal.py` range-checks diffusivity to 1e-4 … 1 m²/day.
- `--ref-man` compares the two passes' `*.man` token-wise and blocks a mismatch.
- `--stress-pass` refuses to run without an existing `*.oit`.
- `write_seepage.py` checks that the element supports two fields, that
  `uwcpl≠0` for a coupled run, and that `water_level` lies inside the mesh's
  vertical extent and is not the `-99.0` sentinel.
- After the run: temperature must lie between the coldest boundary value and
  the placing temperature plus the adiabatic rise; pore pressure must not exceed
  the imposed head times γw.

## Traps
- **Diffusivity unit** (`dt_011`) — the single most damaging silent error in
  this stage.
- **`*.oit` step mismatch** (`dt_025`) — `*.oit` is a positional binary stream;
  a different step count in the stress pass reads the wrong record. When the
  stress pass needs an extra leading block for the foundation, prepend a
  zero-duration block rather than editing the existing ones.
- **U–P on a single-field element** (`dt_017`) — no pressure DOF is allocated
  and the pore-pressure block never appears.
- **`water_level = -99.0` is a sentinel** for "no reservoir", not an elevation
  (`dt_029`).
- `*.oit` and `*.oip` cannot be authored by hand. They come from a prior run.
- A thermal-only run has no nodal loads, no face loads and no self weight — the
  `.loa` still needs all its heading records with zero counts.

## Example
Hydration-heat run of a 20 m concrete lift, 46 steps over 30 days:
```bash
python3 tools/set_analysis.py --case t1 --problem S --solver PARDISO --nl 10 \
        --dofs 10 --order-time 1 --outintw 1
python3 tools/write_loads.py --case t1 --no-gravity --grav-curve 0 \
    --curve "1:LINEAR:0,30|1,1" \
    --curve "2:SIN:0,1000,2000,3000|16.4,8.0,0.97,-110" \
    --curve "3:DABT:14.39|4.75"
python3 tools/write_materials.py --case t1 \
    --mat "id=1;model=HEAT;a=0.0864;curve_adiabatic=3;curve_place=1"
python3 tools/write_thermal.py --case t1 --field-pass --diffusivity 0.0864 \
    --convection "where=y>19.99;beta_bar=1.0;curve=2"
python3 tools/write_steps.py --case t1 \
    --inc "miter=30;dtime=0.2;nstep=5" --inc "miter=30;dtime=1.0;nstep=29" \
    --toler 1e-2
```
Total simulated time = 0.2·5 + 1.0·29 = 30 days.
