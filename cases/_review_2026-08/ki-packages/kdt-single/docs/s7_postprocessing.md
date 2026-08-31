# Stage s7 — Reading the results and validating them

## Purpose
Turn HSTAR's output files into data, then decide whether to believe it.

## Inputs
The collected output directory from stage s5.

## Outputs
- `results.json` — every result block, in the model's own units
- `validation.json` — the four validation layers and their verdicts
- A validation figure

## Procedure

### `*.flavia.res`
The primary result file, ASCII when `outplot='GIDR'`/`'GIDA'`. Block header,
FORMAT `(a15,i8,f12.5,5i8)` (`Output.f90:2117`):

```
<NAME>  <1>  <time>  <itype>  <iloc>  <imat>
```
`itype` 1 scalar, 2 vector, 3 matrix; `iloc` 1 = on nodes. When the last flag
is 1, one record per tensor component names it (`SIGXX SIGYY SIGXY SIGZZ`),
then one record per node: `ipoin  v1 [v2 …]`.

Block names `Output.f90` can emit:

| block | unit | written when |
|---|---|---|
| `DISPLACEMENT` | m | `gid_u=1` |
| `dam_DISPLACEMENT`, `foundation_DISPLACEMENT` | m | block-split output |
| `STRESS` | Pa | `gid_s=1` |
| `PRINCIPALSTRESS` | Pa | |
| `PLASTICSTRAIN` | – | |
| `STRESS_Moment` | N·m/m | plate/shell runs |
| `PORE-PRESSURE`, `Excess_PORE-PRESSURE` | Pa | DOF 8 active |
| `uplift-PRESSURE` | Pa | `upliftin≠0` |
| `PRESSURE_V` | Pa | reservoir pressure elements |
| `TEMPERATURE` | °C | DOF 10 active |

### Other files
| file | contents |
|---|---|
| `*.gpv` | Gauss-point stresses: `ielem igaus s1..s7`, after one heading record |
| `*.act` | support reactions per output step, preceded by a `ttime=` record (sets with `outfix=1` only) |
| `*.chk` | the run log: convergence ratios, step trace, equation count, bandwidth, timings |
| `*.ctr` / `*.gdm` / `*.ojw` | contact gaps, Goodman-element state, joint normal and tangential stress |
| `*.bar` | bar axial force and bond slip |
| `*.opw` / `*.oew` / `*.ogw` | nodal results, element-average stress, average gaps |

```bash
python3 tools/parse_results.py --output_dir out1 --json results.json
python3 tools/parse_results.py --output_dir out1 --var DISPLACEMENT --step last
python3 tools/parse_results.py --output_dir out1 --inverse --reliability
```

### Validation, four layers
```bash
python3 tools/validate_results.py --output_dir out1 --case case1 \
    --model-size 10 --analytic confined_column \
    --rho 2400 --g 9.81 --E 2.5e10 --nu 0.2 --H 10
```

1. **Run health** — exit status, `1.chk` convergence ratios, iteration cap.
2. **Plausibility** — |u|max against the model size. An E in MPa inflates
   displacements by 10⁶ and this is the cheapest way to see it.
3. **Equilibrium** — Σ reactions + Σ applied load ≈ 0. This is the structural
   analogue of a water-balance check, and the only cheap test that catches "the
   load was never applied". Requires `outfix=1` on at least one constraint set.
4. **Benchmark** — a closed-form reference or an external series, reported as
   NSE / KGE / PBIAS / RMSE / r **and** max relative error, which is what FEM
   verification actually grades on.

Built-in closed-form references:

- `confined_column` — 1-D confined (oedometer) compression under self weight,
  σ_yy(y) = −ρg(H−y), u_y(y) = −(ρg/M)(Hy − y²/2),
  M = E(1−ν)/((1+ν)(1−2ν)) for plane strain. Linear elements reproduce this
  **exactly at the nodes**, so the expected agreement is round-off.
- `lame_cylinder` — thick-walled cylinder under internal pressure, plane strain,
  u_r(r) = (1+ν)p_i a²/(E(b²−a²)) · [(1−2ν)r + b²/r]. Bilinear quads converge
  to it at O(h²).

## Verification
`parse_results.py` post-checks every block: one data record per node, all values
finite, and it reports (rather than drops) a block with zero data records.

## Traps
- **No result file although the run succeeded** — `gid_u`/`gid_s` are 0, or
  `noutf > nstep`, or `outplot` is a binary mode routed through the gidpost stub
  (`dt_015`).
- **`not converged` buried in `1.chk`** while the exit status is 0 (`dt_026`).
- `*.act` only contains sets declared with `outfix=1`; without it the
  equilibrium layer has nothing to work with.
- The `.act` reaction values are printed with five significant figures, which
  caps the achievable equilibrium residual at ~1e-5 relative — do not read a
  residual of 1e-5 as an error.
- Result files carry no header identifying the case, the parameters or the
  binary. `run_hstar.py` writes `run_report.json` next to them for exactly this
  reason.
- `*.gpv` stresses are raw Gauss-point values; the `.flavia.res` `STRESS` block
  is smoothed to nodes with the scheme selected by `average_appear` in `.glb`.
  They will not agree at a boundary node, and that is not an error.

## Example — the two analytic verifications run for this KI, 2026-08-26

| benchmark | mesh | max rel. error | NSE |
|---|---|---|---|
| confined column, self weight | 1 × 20 Q4 | 1.60e-16 | 1.000000 |
| Lamé cylinder, internal pressure | 8 × 8 Q4 | 4.66e-03 | 0.998865 |

Mesh convergence on the Lamé case:

| mesh | h = 1/N | max rel. error | observed order |
|---|---|---|---|
| 4 × 4 | 0.250 | 1.844e-02 | — |
| 8 × 8 | 0.125 | 4.662e-03 | 1.984 |
| 16 × 16 | 0.0625 | 1.169e-03 | 1.996 |
| 32 × 32 | 0.03125 | 2.925e-04 | 1.999 |

Mean observed order 1.993 against the theoretical 2.000 for bilinear
quadrilaterals — the discretisation error behaves exactly as the element
formulation predicts. Figure: `work/figures/s8_validation.png`.
