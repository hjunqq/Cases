# Stage s9 — Parameter inversion and structural reliability

## Purpose
Two capabilities that run the forward model many times: recovering material
parameters from monitoring data, and computing a first-order reliability index.

## Inputs
- Inversion: real measured series (`*.obs`), a parameter list with scale factors
  and bounds, and interpolation weights for each instrument point (`*.btl`)
- Reliability: random-variable distributions, means, standard deviations and a
  correlation matrix (`*.sto`)

## Outputs
- Inversion: the iterate trace and the recovered parameter vector in `1.chk`;
  simulated-vs-observed series in `1.obsc`
- Reliability: the β iterates in `1.chk`

---

## Inversion

Dispatch, at `Fem.f90:334-360`:

| `Bparameter` | `balgor` | routine |
|---|---|---|
| −1, −2 | any | forward verification: generate the synthetic response for a given parameter vector |
| 1…2 | ≤1 | Gauss–Newton / householder inversion |
| 1…2 | 2 | MKL trust-region `dtrnlsp` (reverse communication) |
| 3 | — | rigid-block displacement inversion |
| 4 | — | nodal-value inversion |

`*.btl` (`Fem.f90:2011-2061`):
```
' Npara' / Npara
' i, imat, name, factor, mode_transform, lo, hi'      x Npara
' EPS(1:6), iter1, iter2, RS, JAC_EPS'                (balgor<=1)
   or the trust-region record eta1 eta2 gama1 gama2 delta0 iter1 iter2
' initial values' / Xvalue(1:Npara)
' information for given points, Npoints_pb' / Npoints_pb
' i0, ndofn, imdofn, nintf' / listf(1:nintf) / rintf(1:nintf)   x Npoints
```

Each observation point is an **interpolation** over `nintf` mesh nodes with
weights `rintf` — a plumb line or extensometer rarely sits on a node. The
weights must sum to 1.0; HSTAR does not normalise them.

`name` is the material property being inverted (`E`, `nu`, `K`, `phi`), `imat`
the material it belongs to, and `factor` rescales it to O(1).

`*.obs` (`Fem.f90:2220-2226`):
```
' Nblks_pb' / nblks_pb
per block: ' NINCS' / nincs_pb
           dtime_pb nstep_pb observ_pb begin_day_pb end_day_pb
per point-dof: ix i1 j1 flag ipoint weight label
               observed_value(1:nstep_pb)
```

```bash
python3 tools/write_inverse.py --case inv1 --algorithm trust_region \
  --param "imat=1;name=E;init=2.0e10;factor=1e-10;lo=1e10;hi=4e10" \
  --param "imat=2;name=E;init=1.0e10;factor=1e-10;lo=5e9;hi=3e10" \
  --point "nodes=12290,13672,13676;weights=0.4,0.35,0.25;dof=1" \
  --obs-csv plumb_lines.csv --dtime 30 --nstep 12
```

`--obs-csv` is a CSV whose first column is the series label and whose remaining
columns are the measured series. **The tool never synthesises observations.**

---

## Reliability

Two switches on `inp` record 2 (`restart relis sysrelis ADINA Uopt_R gamamax`):

- `relis=1` — element / point reliability, dispatched at `Fem.f90:1910` into
  `STATIC_U_reli` (`block_stab=0`) or `static_rigid_reli` (`block_stab≥1`);
- `sysrelis>0` — system reliability over a set of failure modes
  (`Fem.f90:5357`, `6207`).

`*.sto` (`Fem.f90:4732-4755`):
```
' nbeta,nv,mkiter' / nbeta nv mkiter
' distribution / mean / sd / correlation'
ja(1:nv)        1 normal, 2 lognormal, 3 extreme (Gumbel)
ee(1:nv)        means
ss(1:nv)        standard deviations
cov(i,1:nv)     x nv    correlation matrix, one record per row
```

```bash
python3 tools/write_reliability.py --case rel1 --mode element \
  --var "name=c;dist=2;mean=2.0e4;sd=4.0e3" \
  --var "name=phi;dist=1;mean=35;sd=3" \
  --corr "1,0.3|0.3,1" --nbeta 1 --mkiter 50
```

## Verification
- `write_inverse.py` checks every parameter scales into 1e-2 … 1e2, that the
  initial value lies inside its bounds, that interpolation weights sum to 1,
  and that each series length equals `nstep_pb`.
- `write_reliability.py` checks the distribution codes, rejects a lognormal with
  a non-positive mean, warns on a COV above 1, and requires the correlation
  matrix to be symmetric, unit-diagonal and positive definite (Cholesky).
- Read the results with
  `python3 tools/parse_results.py --output_dir out --inverse --reliability`.
- Before an expensive inversion, run `Bparameter=-1` once: it exercises the
  observation-point interpolation without iterating.

## Traps
- **Unscaled parameters** — a modulus of 2e10 next to a Poisson ratio of 0.2
  gives a Jacobian whose columns differ by eleven orders of magnitude and a
  single trust-region radius cannot serve both (`dt_021`).
- **Interpolation weights that do not sum to 1** — HSTAR does not normalise
  them, so the simulated value is scaled wrong and the inversion compensates by
  distorting the parameters.
- **Inverting against synthetic observations proves nothing** (`dt_027`). If the
  `*.obs` series came from the same model with the same mesh, the recovered
  parameters are the generating ones by construction. Report such a run as
  validation tier `synthetic`, never `real`.
- **Correlation matrix not positive definite** — the Nataf transform produces a
  meaningless search direction and β does not converge (`dt_022`).
- Each inversion iteration is a full forward run. A 35 000-node dam model with
  12 monitoring points and 6 parameters is hours to days, not minutes; check
  `iter1`/`iter2` against the forward run's wall time before starting.

## Example
The HSTAR case library ships a real inverse study (Xinfengjiang arch dam,
35 331 nodes): thermal transient → static displacement → seepage transient →
`xfj_inverse_mat`, inverting 2 to 6 elastic moduli against 12 plumb-line and
extensometer series (`PL_85`, `PL_87`, `IP_81`, `PL_144`, …) over 12 monthly
steps. That case is the reference for what a production inversion looks like:
`.btl` interpolation weights over 6–14 nodes per instrument, and observed
displacements of order 1e-4 to 5e-3 m.
