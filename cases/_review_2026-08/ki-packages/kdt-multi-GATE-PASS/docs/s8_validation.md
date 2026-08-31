# s8 — Validation

## Purpose

Decide whether a finished HSTAR run is a solution, is physically plausible, and agrees with
something independent.

## Inputs

A run directory and (optionally) the case directory, an analytic benchmark, or monitoring
data.

## Outputs

A verdict dict from `validate_results.validate()`; exit code 1 when the plausibility screen
fails.

## Procedure — three layers, in order

### 1. Equilibrium (the conservation check)

A stress solver has no water budget to close, but it has a global equilibrium statement, and
HSTAR writes it every iteration to `<probn>.chk`:

```
ratio for residu norm = ||R|| / ||F_ext||
```

A converged static solution has this ≤ `toler_force` from `.man`. `validate_results`
reads the tolerance the case ACTUALLY asked for (via `build_analysis_control.read_man`)
rather than hard-coding a number, and also checks the displacement-increment ratio.

This is the structural-mechanics analogue of `validate_water_balance(P, ET, Q)`. Nothing in
`ki_tools_common` computes it; `_local_metrics.force_balance_ratio` and
`validate_results.equilibrium_check` do.

### 2. Plausibility screen

HSTAR is unit-agnostic and range-checks nothing, so a metre/millimetre or Pa/MPa slip
produces a perfectly converged, entirely wrong answer. Order-of-magnitude limits for civil
hydraulic structures in SI — **sanity limits, not acceptance criteria**:

| stream | band | rationale |
|---|---|---|
| `DISPLACEMENT` | 1e-9 … 1 m | a 100 m dam moves mm–cm; > 1 m is a unit error or a mechanism |
| `STRESS`, `PRINCIPALSTRESS` | 1e2 … 1e9 Pa | concrete f_t ≈ 1–3 MPa, f_c ≈ 20–40 MPa |
| `TEMPERATURE` | −60 … 200 °C | > 200 usually means kelvin |
| `PORE-PRESSURE` | −1e7 … 1e8 Pa | |
| `WATER-HEAD` | −1e4 … 1e4 m | |
| modal frequency | 0.05 … 200 Hz | a large arch dam's first mode is 1–5 Hz |

Modal frequencies are additionally required to be monotonically increasing with mode order;
if they are not, the eigen-extraction did not converge.

### 3. Comparison

Against a closed-form solution or measured data, through `all_metrics(obs, sim)` —
`ki_tools_common.metrics` when importable, otherwise the in-KI `_local_metrics` fallback
with an identical signature. For a structural model the informative entries are
`rel_err_pct`, `max_rel_err_pct` and `nrmse_pct`; NSE/KGE/PBIAS are computed only so the
dict shape matches the shared library.

### The shipped analytic benchmark

`confined_selfweight_column` — a laterally confined elastic column of height H under its own
weight, base fixed, roller sides:

```
u(y)        = -rho g (H^2 - (H-y)^2) / (2 E_oed),  E_oed = E(1-nu)/((1+nu)(1-2nu))
u_top       = -rho g H^2 / (2 E_oed)
sigma_yy(y) = -rho g (H - y)
sigma_xx    = K0 sigma_yy,  K0 = nu / (1 - nu)
```

It exercises the plane-strain constitutive matrix, the body-force integration, the
displacement boundary conditions and the linear solver, and it has no discretisation error
for linear elements under a linearly varying stress field — so agreement should be at
round-off, and anything else is a real defect.

## Verification — the KI's own validation result

Run 2026-08-26 with the binary built from this source tree
(`/tmp/claude-1000/kdt-work/HSTAR/build/hstar`, Intel ifx 2025.3.3 + MKL), through the full
tool chain:

```
build_case_from_template -> build_mesh_files -> build_boundary_conditions
  -> build_material_file -> build_loads -> run_hstar -> parse_outputs -> validate_results
```

Case: E = 2.5e10 Pa, ν = 0.20, ρ = 2400 kg m⁻³, g = 9.81 m s⁻², H = 10 m, W = 1 m,
20 Q4 plane-strain layers, 42 nodes, PROFILE solver.

| quantity | analytic | HSTAR | error |
|---|---|---|---|
| `u_top` | −4.237920e-05 m | −4.237920e-05 m | 1.6e-14 % |
| `u(y)` over all 42 nodes | — | — | max abs 6.8e-21 m (1.6e-14 %) |
| `σ_yy` at interior nodes | −ρg(H−y) | matched | 0.0 % |
| mean `σ_yy` | −117 720 Pa | −117 720 Pa | 0.0 % |
| mean `σ_xx` (K₀ check) | −29 430 Pa | −29 430 Pa | 0.0 % |
| equilibrium ‖R‖/‖F‖ | ≤ 1e-5 asked | 5.4e-15 | — |

Figure: `/tmp/claude-1000/kdt-work/HSTAR/figures/s8_validation.png`.

**Validation tier: `analytic`.** Not `real`: no dam-monitoring dataset (plumb line,
thermometer, piezometer) for any modelled structure is mounted on this host, so no
independent observation was used. The comparison is against a closed-form elasticity
solution, exercised end-to-end through the real compiled binary.

Two additional confirmations from the same session:

* **Solver independence** — the same case with `PROFILE` and with `PARDISO` gives
  bit-identical displacements.
* **Parameter response** — halving `E` from 2.5e10 to 2.0e10 Pa changed `u_top` from
  4.23792e-07 to 5.29740e-07 m, exactly the analytic ratio `E_oed(2.5)/E_oed(2.0)`;
  doubling gravity doubled the displacement exactly.

## Traps

- **Do not compare nodal stress against the point value at a boundary.** The `.flavia.res`
  STRESS stream is node-averaged, so the outermost rows are offset by half an element
  (`ρ g Δy / 2`). Compare interior nodes or the domain mean (`dt_025`).
- **A `real`-tier claim needs independent observations.** Comparing against another
  simulation, against the same model with different settings, or against a value taken from
  the same case's own previous output is not `real`.
- **`converged: true` is necessary, not sufficient.** Always run the plausibility screen and
  a physical cross-check (K₀ ratio, total reaction = total weight, mode-order monotonicity).
- **The `.chk` layout differs from the console echo.** The file writes
  `ratio for residu norm=`; the terminal prints `ratio1=`. A regex written against the
  console misses every record in the file. `parse_chk` handles both.

## Example

```bash
$ python3 tools/validate_results.py --dir /tmp/valrun --case /tmp/valcase \
      --benchmark confined_selfweight_column --E 2.5e10 --nu 0.2 --rho 2400 --H 10
{ "equilibrium": {"ok": true, "final_force_residual_ratio": 5.4e-15, "tolerance_used": 1e-05},
  "plausibility": {"ok": true},
  "benchmark": {"max_rel_err_pct": 1.6e-14},
  "ok": true }
```
