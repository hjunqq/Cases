# s5 — Analysis control, DOF set, time integration and solvers

## Purpose

Choose which physics HSTAR solves, with which degrees of freedom, over what increment and
step schedule, with which linear solver.

## Inputs

The analysis intent: static / dynamic / modal / field, coupled or not, how many steps.

## Outputs

The `TYPE_PROBLEM …` and `MDOFN` records of `<probn>.glb`, `<probn>.man` and `<probn>.sol`.

## Procedure

### The analysis-type matrix (`process_analysis`, `Fem.f90:1633-1999`)

```
type_problem = 'Q'  quasi-static
    relis==1 & block_stab==0  -> STATIC_U_reli          FORM reliability
    relis==1 & block_stab>=1  -> static_rigid_reli
    block_stab>=1 & ebody==0  -> static_rigid_1         rigid-block stability
    mdofn==7 & lmdofn(7)/=0   -> static_U_P             u-p consolidation
    mdofn==8 & lmdofn(8)/=0   -> static_U_Pw            u-pw consolidation
    nbackf/=0 & nbackdT==0    -> back_analysis
    nbackf/=0 & nbackdT/=0    -> back_d_analysis
    else                      -> static_U               <- the standard path
type_problem = 'F','D'        -> time_dependent (Newmark) or explicit
type_problem = 'S'            -> transient field advance (thermal / seepage)
type_problem = 'E'            -> response_spectrum (modal extraction + spectrum)
type_problem = 'W'            -> frequency_analysis (complex arithmetic)
```

### The DOF set

```
mdofn                 how many DOF SLOTS the file declares (up to 10)
lmdofn(1:mdofn)       0 = slot absent; non-zero = its COMPRESSED number
order_time_mdofn(...) 0 static, 1 velocity, 2 acceleration
cdofn                 = count of non-zero lmdofn = DOF per node actually assembled
```

The non-zero entries of `lmdofn` **must be exactly 1..cdofn with no gaps**: `nodfn()` is
indexed by them. Plane u-pw is `mdofn=8, lmdofn=[1,2,0,0,0,0,0,3]`.
`build_analysis_control.set_dofs` enforces this.

For a dynamic run, `order_time_mdofn` must be 2 on the displacement slots, or HSTAR never
allocates `result_first`/`result_second` and the velocity/acceleration output streams stay
empty.

### Time integration

`BEETA1 BEETA2 THETA1` = Newmark γ, Newmark β, θ for the field (thermal/seepage) equation.

| γ / β | behaviour |
|---|---|
| 0.50 / 0.2500 | average acceleration — unconditionally stable, no algorithmic damping |
| 0.60 / 0.3025 | what `cases/static` ships — γ > ½ adds numerical damping |

`build_dynamic_seismic.set_newmark` refuses a pair with β < (γ+½)²/4, which is only
conditionally stable and which HSTAR does not check.

### `<probn>.man` — increment / step schedule (`Fem.f90:3582-3600`)

One group per load block:

```
text                                       header, must exist
nincs cdtest earthquake_curve(1:ndimn)     static_U consumes only nincs from this record
  per increment:
    miter ditime noutn noutf nstep inc_step nresta cwater Qstatic
    toler_force toler_var(1:mdofn)
    [cwater/=0 & delgroup>0]  delgroup x ( idelgroup coef_water(1:nstep) )
    [Qstatic/=0]              6 extra records
```

| field | meaning |
|---|---|
| `miter` | max Newton iterations per step |
| `ditime` | time-step size (s) |
| `noutn` | nodal-result output interval (steps) |
| `noutf` | full-output / GiD write interval |
| `nstep` | number of steps in this increment |
| `inc_step` | step stride |
| `nresta` | restart-file write interval |
| `cwater` | per-step water-coefficient records follow |
| `Qstatic` | static-field records follow |
| `toler_force` | relative force-residual tolerance |
| `toler_var(1:mdofn)` | relative tolerance per DOF slot |

### Matrix re-formation intervals

`nmass nsmat nhmat nqmat` and `ntsmat nthmat` are **not** material ids — they are how often
each matrix is re-formed (`modf_time_order`, `Fem.f90:15480-15545`):

```
KxMAT = 1 if NxMAT==0, or (istep==inc_step and iiter==1), or mod(istep, NxMAT)==0
```

so `0` = every iteration, `1` = every step, `999` = effectively only at the start of each
increment. Reading `999` as "off" is wrong.

### `<probn>.sol` — linear solver

One group per load block:

```
text            " mtype, ncpu, msglvl"
mtype ncpu msglvl
text            " isdefault"
isdefault
```

`mtype` is the PARDISO matrix type: `2` real SPD, `-2` real symmetric indefinite (what every
shipped case uses), `11` real unsymmetric. `ncpu` is the MKL thread count. `msglvl` is
PARDISO verbosity.

| solver | when |
|---|---|
| `PARDISO` | ≥ ~10⁴ DOF, 3-D, contact; the default |
| `PROFILE` | small / 2-D; skyline LDLᵀ, no MKL dependence |
| `JPCG` | element-by-element Jacobi PCG, low memory, needs a well-conditioned matrix |
| `PBCG` | preconditioned bi-CG |
| `EXPLICIT` | central difference, lumped mass, no linear solve |

## Verification

```bash
python3 tools/build_analysis_control.py --case /tmp/c --describe
python3 tools/build_analysis_control.py --case /tmp/c --type-solver PARDISO --mtype -2 --ncpu 4
```

**Solver independence** is the strongest check available: the same case solved with
`PROFILE` and with `PARDISO` must agree to round-off. Verified on the column benchmark —
both produce `u_top = -4.23792e-07 m`, bit-identical.

## Traps

- **`mtype` mismatched to the physics.** A u-p coupled or contact problem is symmetric
  INDEFINITE (`-2`). Declaring `2` (SPD) makes PARDISO report zero or tiny pivots.
- **`nonsym /= 0` needs `mtype = 11`.**
- **`toler_var` must have `mdofn` entries**, not `cdofn`. A short line spills into the next
  record.
- **`miter` silently defines "failure"** for the strength-reduction path — see s9.
- **Copying `beeta1=0.6` from `cases/static` into a seismic run** damps out high-frequency
  response (`dt_019`).
- **`EXPLICIT` is CFL-limited and HSTAR does not check the step size** — an over-long
  `ditime` diverges to NaN (`dt_020`).

## Example

```bash
$ python3 tools/build_analysis_control.py --case /tmp/c \
      --type-problem F --type-solver PARDISO --beeta 0.5 0.25 1.0 \
      --increment 200 0.01 1 10 500 1 50 --toler-force 1e-4 --mtype -2 --ncpu 8
```
