# s7 — Outputs and parsing

## Purpose

Turn HSTAR's result files into labelled, unit-carrying Python objects.

## Inputs

A finished run directory.

## Outputs

A dict from `parse_outputs.parse_run()`, optional JSON and CSV.

## Procedure

### `<probn>.flavia.res` — the main result stream

HSTAR writes this itself (`Output.f90:OUT_GID_WRITE`), not through the gidpost library, so
the layout is fixed by Fortran `FORMAT 101 = (a15, i8, f12.5, 5i8)`:

```
   DISPLACEMENT       1     1.00000       2       1       0
         1        0.00000000E+00        0.00000000E+00
         2        0.11191490E-08        0.00000000E+00
   ...
         STRESS       1     1.00000       3       1       1
 SIGXX
 SIGYY
 SIGXY
 SIGZZ
         1       -0.29430000E+04  ...
```

| field | meaning |
|---|---|
| `a15` | result name, **right-justified in 15 characters and TRUNCATED** |
| `i8` | step index (always 1 in the call sites) |
| `f12.5` | `total_step` — the accumulated time / load factor |
| `i8` | data type: 1 scalar, 2 vector, 3 matrix |
| `i8` | 1 |
| `i8` | location: 0 OnNodes, 1 OnGaussPoints / element |

A matrix block is followed by its component-name lines, then `(i10, 10(2x,e20.8))` data
records. The whole block repeats once per output step (`noutf` in `.man`).

**Names actually emitted** (`Output.f90:1342-1830`), with their units in the SI convention
of the shipped cases:

| name (as written) | unit | notes |
|---|---|---|
| `DISPLACEMENT` | m | vector, OnNodes — the headline output |
| `foundation_DISPLACEMENT`, `dam_DISPLACEMENT` | m | split streams when requested |
| `velocity` | m s⁻¹ | dynamic runs |
| `acceleration` | m s⁻² | dynamic runs |
| `acceleration_ab` | m s⁻² | truncation of `acceleration_absolute` |
| `ROTATION` | rad | beam/plate rotations |
| `STRESS` | Pa | matrix; 2-D components SIGXX SIGYY SIGXY SIGZZ, 3-D six |
| `PRINCIPALSTRESS` | Pa | |
| `PLASTICSTRAIN` | – | |
| `Yield` | – | yield indicator |
| `TEMPERATURE` | °C | |
| `PORE-PRESSURE`, `Excess_PORE-PR` | Pa | |
| `WATER-HEAD` | m | |
| `flow_velocity` | m s⁻¹ | |
| `flow_charg` | m³ s⁻¹ | truncation of `flow_charge` |
| `PRESSURE_V` | Pa | |
| `uplift-PRESSURE` | Pa | |
| `tofor` | N | total external nodal force |

Which of these appear is chosen by the `gid_*` flag record in `.glb`
(`gid_u gid_s gid_ms gid_f gid_rot gid_v gid_a gid_T gid_P gid_Pv gid_ep gid_Y gid_FC
gid_Ns gid_Ss gid_Mxy gid_bem gid_wh gid_wv gid_bcs`).

**Stress is NODE-AVERAGED.** The `average_appear(1:ngroup)` vector selects the mode:
`0` excluded, `1` extrapolate from Gauss points, `2` direct average, `-1/-2` legacy
variants. On a coarse mesh this means the reported nodal stress is an average over the
adjoining elements, not the point value — see the Traps.

### `<probn>.chk` — convergence log and modal results

```
 iblks=  1 iincs=  1 istep=  1 iiter=  1
 resid=  0.000E+000 retot=   20601.0
ratio for residu norm= 0.0000E+00        <- force residual, L2   ** THE EQUILIBRIUM CHECK **
 max_refor= ...   max_tofor= ...
ratio for residu maxm= 0.0000E+00        <- force residual, max norm
               Convergence check for displacement
ratio for norm= 0.1000E+01               <- displacement increment, L2
ratio for maxm= 0.1000E+01
                    not converged for checki=  1      <- absent once converged
```

Modal runs (`type_problem='E'`) additionally write `FORMAT 100`:

```
  order=    1  omega= 0.25109E+02  freq= 0.39962E+01  period= 0.25024E+00 coefx= ...
             mstar= 0.46109E+06 kstar= 0.29069E+09
```

`freq` is in Hz, `omega` in rad s⁻¹, `period` in s, `mstar`/`kstar` are the modal mass and
stiffness. `<probn>.omg` holds the base frequency when that pass ran.

### Other streams

`.opw` nodal results, `.oew` element average stress, `.ogw` gap averages, `.ojw` joint
normal/tangential stress, `.ctr` contact, `.gdm` Goodman, `.bar`/`.bem` rebar and beam
internal forces, `.gpv` Gauss-point variables, `.oid`/`.oip` intermediate dumps,
`.inw` initial-stress write, `.res`/`.resb` binary state, `.rtt` unformatted restart.

## Verification

```bash
python3 tools/parse_outputs.py --dir /tmp/myrun
python3 tools/parse_outputs.py --dir /tmp/myrun --json out.json --csv disp.csv --result DISPLACEMENT
```

The summary reports, per stream, `unit`, `n_entities`, `n_steps`, `min`, `max`, `max_abs`
and per-component maxima, plus `converged`, `final_residual_ratio`, `final_disp_ratio` and
`modal_frequencies_hz`.

## Traps

- **The `a15` name field truncates.** `acceleration_absolute` → `acceleration_ab`,
  `flow_charge` → `flow_charg`, `Excess_PORE-PRESSURE` → `Excess_PORE-PR`. A parser keyed
  on the full name finds nothing. `parse_outputs.RESULT_UNITS` maps both spellings.
- **Nodal stress is averaged, so boundary rows are offset by half an element.** On the
  KI's 20-layer column benchmark the interior σ_yy matches the analytic
  `−ρg(H−y)` to 0.0 %, while the top and bottom rows are offset by exactly
  `ρ g Δy / 2 = 5886 Pa`. That is the averaging, not an error. Compare interior nodes, or
  compare the domain mean (`−ρgH/2`), not the base value (`dt_025`).
- **`converged: true` is not a physics verdict.** It only means the force residual ratio fell
  below the tolerance in `.man`. A structure with a mechanism converges to a wrong answer;
  run the plausibility screen too.
- **`.flavia.res` grows one full block per `noutf` interval.** A 500-step dynamic run with
  `noutf=1` on a 5000-node mesh is hundreds of MB.
- **`outplot='GIDA'` appends** rather than rewriting. Re-running in place then produces a
  file with duplicated blocks and `parse_run` returns them all in file order — the last one
  is the current step.

## Example

```bash
$ python3 tools/parse_outputs.py --dir /tmp/smoke
{
  "DISPLACEMENT": {"unit": "m", "n_entities": 6, "n_steps": 1,
                   "min": -4.23792e-07, "max": 0.0, "max_abs": 4.23792e-07,
                   "comp1_max_abs": 1.65e-24, "comp2_max_abs": 4.23792e-07},
  "STRESS":       {"unit": "Pa", "n_entities": 6, "max_abs": 11772.0},
  "converged": true, "final_residual_ratio": 0.0, "final_disp_ratio": 0.0
}
```
