# Stage s3 — Boundary conditions, loads and load steps

## Purpose
Prescribe what holds the structure (`*.pre`), what pushes on it (`*.loa`), and
how the analysis walks through time (`*.man`).

## Inputs
- The mesh (constraints and load faces are selected from `*.cor`/`*.ele`)
- Gravity, pressures, point loads, seismic records, prescribed values
- Step sizes and convergence tolerances

## Outputs
`1.pre`, `1.loa`, `1.man` — each repeated **once per run block**, in block order.

## Procedure

### Constraints — `*.pre`
```
'PRESCRIBE SET--NFIXSETS'
nfixsets  nline
  ifixvar nfixnods itcurve tfixvar outfix jfixvar gamawx nextr
  list_fix(1:nfixnods)
  val_fix(1:nfixnods)
```
`ifixvar` uses the global DOF numbering. `val_fix` is a **multiplier on time
curve `itcurve`**, not an absolute value — a constant prescribed temperature
needs a flat curve or `itcurve=0` (`dt_031`). `outfix=1` writes the reaction to
`*.act`, which is what makes the equilibrium check possible.

```bash
python3 tools/write_boundary.py --case case1 \
    --fix "dof=1;where=abs(x)<1e-9 or x>0.999" \
    --fix "dof=2;where=y<1e-9;out=1"
```
Nodes are always selected by coordinate predicate. A literal node list survives
exactly until the next remesh (`dt_009`).

### Loads — `*.loa`
Block order is fixed: time curves → point loads → face-load element definitions
→ face-load groups → body force → per-group gravity curves → beam loads →
plate loads.

Time-curve types:

| type | data records | meaning |
|---|---|---|
| `LINEAR`, `LNLINEAR` | times, then factors | piecewise-linear ramp |
| `SIN` | 4 unused values, then `a b c d` | `T = a + b·sin(π(c·t + d)/180)` — ambient air temperature |
| `DABT` | `a`, then `b` | `θ = a·t/(b + t)` — adiabatic hydration rise |
| `SEISMIC` | accelerogram | ground motion |
| `ARCLENGTH` | control record | arc-length load control |

Face pressure: positive is compression onto the face; the face node ordering
must give an **outward** normal. The load varies linearly between `cor0` and
`cor1` along axis `water` (1 = x, 2 = y, 3 = z), from `p0` to `p1`, scaled by
`fact` — hydrostatic load is `p0=0` at the surface, `p1=h`, `fact=9810`.

Body force is `gravy  factg(1:ndimn)  factf(1:ndimn)`; the factors are applied
**opposite** to the gravity vector, so plain 2-D self weight is
`9.81  0 -1  0 -1`. `tcurvegravity(igroup)=0` disables self weight for that
group — the mechanism used for excavation.

```bash
python3 tools/write_loads.py --case case1 --gravity 9.81 --gdir 0,-1 \
    --curve "1:LINEAR:0,1|1,1" \
    --face "x*x+y*y < 1.000001" \
    --edge-load "curve=1;axis=1;cor0=0;cor1=1;p0=1.0e6;p1=1.0e6;fact=1"
```

### Load steps — `*.man`
```
' nincs,cdtest,earthquake_curve(1:ndimn)'
nincs cdtest eq_curves...
  miter ditime noutn noutf nstep inc_step nresta cwater Qstatic
  toler_force toler_var(1:mdofn)
```
`nincs > 1` gives variable stepping inside one run block — short steps for the
first days of hydration, long ones afterwards. Total simulated time is
`Σ ditime·nstep` across all sets and all blocks.

`ditime` is in **seconds** for dynamics and **days** for thermal, creep and
construction staging.

```bash
python3 tools/write_steps.py --case case1 \
    --inc "miter=30;dtime=0.2;nstep=5" --inc "miter=30;dtime=1.0;nstep=9" \
    --toler 1e-2
```

## Verification
- `write_boundary.py` refuses a `.pre` that leaves a translational DOF entirely
  unconstrained, naming the free direction.
- `write_loads.py` refuses an edge-load group whose face list is empty, and
  checks `|gravy| ≈ 9.81` and that `gdir` is a unit vector.
- `write_steps.py` refuses `noutf < 1` (nothing would ever be written).
- After the run: the equilibrium layer of `validate_results.py` — Σ reactions
  must cancel the applied resultant.

## Traps
- **`.man` increment record needs 9 fields, not the manual's 7 or the
  intermediate 8.** `static_U` (`Fem.f90:3590`) reads `Qstatic` as the ninth.
  A short record makes the list-directed read swallow the tolerance record and
  the run dies with `forrtl: severe (24)` on unit 9. Verified 2026-08-26
  (`dt_016`).
- **`.loa` face-class record needs 4 fields** — `sedge nnode index vdimn`
  (`Load.f90:359`, added 2021-10-28). Three fields give
  `forrtl: severe (59)` on unit 21 (`dt_023`).
- **`.loa` edge-load group record needs 5 fields** — `begin end itcurve water
  code_load` (`Load.f90:748`) (`dt_024`).
- Load never applied — empty face list, `tcurvegravity=0`, or the group excluded
  by `APPEAR_PROCESS`. Converges, looks fine, is wrong (`dt_013`).
- Prescribed value multiplied by a curve that evaluates to 0 (`dt_031`).
- Raising `nblks` without appending the per-block repeats of `.pre`/`.loa`/
  `.man` (`dt_030`).

## Example
Hydrostatic reservoir load on the upstream face of a 2-D dam, water surface at
y = 60 m, base at y = 0:
```bash
python3 tools/write_loads.py --case dam1 --gravity 9.81 --gdir 0,-1 \
  --curve "1:LINEAR:0,1|1,1" \
  --face "x < 1e-6 and y <= 60.0" \
  --edge-load "curve=1;axis=2;cor0=60.0;cor1=0.0;p0=0.0;p1=60.0;fact=9810"
```
