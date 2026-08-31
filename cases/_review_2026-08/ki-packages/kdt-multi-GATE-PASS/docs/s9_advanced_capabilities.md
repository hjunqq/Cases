# s9 — Advanced capabilities

## Purpose

Reach the capabilities beyond a straight elastic stress analysis: contact, stability,
reliability, inversion, thermal, seepage, staged construction, FSI, adaptivity,
sub-modelling and the level-set path.

## Inputs / Outputs

Case-specific; each section names its switch, its auxiliary file and the KI tool.

## Procedure — capability by capability

### Contact and joints (`tools/build_contact_joints.py`)

Control record: `ngaps ngapb ctt_pe miter_bt torbt iblkbt nonsbt xlwsol method_gapi
miter_state type_solver_ctt restart_ctt damp_ctt istatec`.

Contact is a node-pair problem solved in an inner loop (`solve_ctt`), with states
open / closed / slipping tracked in `gaps(:)%state` and persisted to the unformatted
`<probn>.ctt`. Goodman joints are a MATERIAL (zero-thickness interface elements with a
`GOODMAN` record: joint model, `kn`, `ks` in Pa m⁻¹, cohesion Pa, friction degrees, tensile
strength Pa); `MCJOINT` under `CLASSICALEP` is the thin-layer alternative.

Practical guidance: `kn` should be ~10²–10³ × (adjacent E) / (representative element size)
so the joint neither interpenetrates nor destroys the conditioning. Increase `miter_bt` and
`miter_state` before loosening `torbt`.

### Stability — three different answers (`tools/build_stability_analysis.py`)

1. `kstab /= 0` — **limit-state safety factor** on a KNOWN surface declared in `<probn>.ftr`.
2. `type_load='MAT_DE'` + `stab_matde` — **strength reduction** for an UNKNOWN surface.
   FoS = 1 / (reduction at the last converged step). `miter` in `.man` defines when
   "non-convergence" is declared and therefore changes the answer.
3. `block_stab = 1|2` — **rigid-block sliding**, 3(ndimn−1) rigid DOF, `static_rigid_1` +
   `solve_ctt_rigid` + `state_and_stiff_rigid_2021`. `ebody` must be 0 for the pure rigid
   path.

### Reliability (`tools/build_reliability.py`)

`relis=1` routes to `STATIC_U_reli` (`block_stab==0`) or `static_rigid_reli`. FORM with
Rackwitz-Fiessler design-point iteration (`DANGLI`, `RI3`, `betaindex`,
`stab_rcandgy_reli`). Random variables — normally φ and c — and their correlation live in
`<probn>.sto`, generated through the MKL VSL multivariate Gaussian
(`vsl_gauss_module.f90`). `sysrelis > 0` adds series / parallel / narrow-bound system
reliability.

`Pf = Φ(−β)`. Which target β counts as acceptable is a CODE decision (Chinese dam design
codes, ISO 2394, EN 1990 all differ); this KI reports β and does not choose.

Cost: one full non-linear solve per design-point iteration per random variable.

### Parameter inversion (`tools/build_back_analysis.py`)

| `Bparameter` | `balgor` | route |
|---|---|---|
| 1, 2 | 0 | `parameter_back_analysis` — MKL `DTRNLSP` Levenberg-Marquardt, finite-difference Jacobian |
| 1, 2 | 1 | same, ANALYTIC sensitivity (`dudx`, `Fem.f90:4291-4390`) — one solve per iteration instead of n+1 |
| 1, 2 | 2 | `trust_region_back_analysis` — trust region + BFGS, double dog-leg |
| 3 | – | `rigid_dis_back_analysis` — least-squares split of measured displacement into rigid + elastic |
| 4 | – | `nodal_value_back_analysis` — nodal field values from sampled observations |
| −1, −2 | – | `parameter_back_analysis_verify` — Monte-Carlo verification, then STOP |
| (`nbackf/=0`) | – | `back_analysis` / `back_d_analysis` inside `static_U` |

Files: `.btl` control, `.obs` / `.obsc` observations. Observations are in MODEL units
(m, °C, Pa). Millimetres against a metre mesh makes the optimiser converge on a modulus
1000× wrong (`dt_023`).

### Thermal and pipe cooling (`tools/build_thermal.py`)

`kstat` steady/transient, `theta1` the θ-method parameter, `<probn>.tem` for prescribed
temperatures, convection edges, surfaces and cooling pipes (`algo_pipe=3` is the Zhu Bofang
analytic superposition). The HEAT material record supplies the diffusivity `alfa(1:ndimn)`
in m² per **the same time unit as `ditime`** — mixing m²/h into a seconds model cools the
concrete 3600× too fast, invisibly (`dt_013`).

What actually turns the heat equation on is a group whose `fieldid` is `T` (plus a HEAT
material), not `ntsmat`/`nthmat` — those are matrix re-formation intervals.

### Seepage and consolidation (`tools/build_seepage.py`)

Pure field: `nflow /= 0`, a `W`/`P`-field group, `nfreeflownode` + node list for the
phreatic boundary, `<probn>.aqu`. `cases/train12_seepage_steady` runs with
`mdofn=8, lmdofn=[0,…,0,1]` — pressure DOF only, ordinary Q4 elements.

Coupled: `mdofn=7` (`static_U_P`) or `mdofn=8` (`static_U_Pw`) with BOTH the displacement
and pressure slots active — and this needs COUPLED element indices 11–19 or 24. Coupled DOF
with uncoupled elements converges and reports zero pressure everywhere (`dt_015`).

Permeability is a hydraulic conductivity in m s⁻¹, not an intrinsic permeability in m²
(`dt_016`).

### Staged construction (`tools/build_staged_construction.py`)

`APPEAR_PROCESS(igroup, iblks)`: `1` active, `0` absent, `−1` **killed this block with
stress release** — the difference between `0` and `−1` is the difference between deleting
an element and excavating it (`dt_012`). `MATNO_PROCESS` swaps the material per block
(maturing concrete). `average_appear` selects the stress-averaging mode used for output.

### Fluid–structure interaction and artificial boundaries (`tools/build_dynamic_seismic.py`)

`Icaddmass` (Westergaard added mass), `swlifs2006` (IFS2006 still-water level, m), `toth`
(total water depth, m), `absorb`, and `<probn>.ifs` for the interface / absorbing-boundary
element groups. `type_ABC` selects `FIX`, `MIF` (input-wave field — note that `MIF` adds a
leading `ifixvar0` field to every `.pre` record) or the viscous-elastic family.

### Equivalent linearisation, liquefaction, permanent deformation

`gamamax` (line 2 of `inp`) + `equvs` + `equvs_process` iterate the shear modulus against
γ_max and write `<probn>.gamax` / `<probn>.tel`. `jliqu` on the SOLID material line,
`ljdp` and `ninistn` in `.glb` drive the liquefaction judgement and the residual-strain /
permanent-deformation output (`.lqu`, `.pmt`, `.stn`).

`ljdp /= 0` with `type_nl /= 5` reaches a `pause` at `Global.f90:767` and blocks on stdin —
`run_hstar` sends trailing blank lines so it does not hang.

### Adaptive meshing, sub-modelling, level set — configured, not derived

These three have no preparation tool because there is nothing to derive: they are switched
by one or two integers plus files produced by a PREVIOUS HSTAR run.

- **Mesh adaptivity**: `rmesh` (with `valv1 valv2` and `ndefault`) and `meshc` in `.glb`;
  `meshfine.f90` refines/coarsens and transfers results through `trans`/`trans_c`. Setting
  `rmesh /= 0` ADDS two conditional records to `.glb` — copy a case that has them rather
  than inserting by hand.
- **Sub-modelling**: `submodel = +1` reads the boundary state from `<probn>.resb` written by
  a coarse global run; `submodel = −1` EXPORTS a sub-mesh and asks for the group and element
  lists on stdin (`Fem.f90:378-417`), so it needs `run_hstar --stdin-file`.
- **Level set**: `level_set_problem` and `appear_level(1:ngroup)`; implementation in
  `Level.f90`.

## Verification

```bash
python3 tools/build_contact_joints.py     --case /tmp/c --describe
python3 tools/build_stability_analysis.py --case /tmp/c --describe
python3 tools/build_reliability.py        --case /tmp/c --describe
python3 tools/build_back_analysis.py      --case /tmp/c --describe
python3 tools/build_thermal.py            --case /tmp/c --describe
python3 tools/build_seepage.py            --case /tmp/c --describe
python3 tools/build_staged_construction.py --case /tmp/c --describe
python3 tools/build_dynamic_seismic.py    --case /tmp/c --describe
python3 tools/build_reinforcement.py      --case /tmp/c --describe
```

Each `--describe` reports the switch, the route HSTAR will take, and whether the auxiliary
file the switch implies is actually populated.

## Traps

Summarised above and enumerated with detections in `diagnostics/triplets.yaml`
(`dt_009`, `dt_012`, `dt_013`, `dt_015`–`dt_018`, `dt_021`–`dt_023`, `dt_026`, `dt_027`).

## Example

```bash
$ python3 tools/build_stability_analysis.py --case /tmp/slope --strength-reduction 1.0 0.5 100
{ "type_load": {"from": "LOAD", "to": "MAT_DE"},
  "reduction": {"from": 1.0, "to": 0.5, "nstep": 100},
  "note": "FoS = 1 / (reduction at the last CONVERGED step). miter controls when
           'non-convergence' is declared, so it changes the reported FoS (triplet dt_021);
           it has been set to 200" }
```
