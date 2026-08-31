> **MANDATORY EXECUTION POLICY** — READ BEFORE PROCEEDING
>
> You MUST run the **actual model binary or package** described in this document.
> If the model fails to import, compile, or execute, you MUST:
> 1. Check `diagnostics/triplets.yaml` for a matching error pattern
> 2. Try the fix suggested in the triplet's `remedy` section
> 3. If still failing, report the error to the user with full details
>
> You MUST NOT substitute a simplified Python formula, regression equation,
> or hand-coded approximation in place of the real model. Doing so produces
> scientifically invalid results and defeats the purpose of the KI.
>
> Before starting, run: `python preflight_check.py` (in this KI directory)
> to verify that the model binary/package and required data are available.
>
> **DEBUGGING PROTOCOL** — When something goes wrong (model crashes, wrong output,
> unexpected values), follow this order. Do NOT skip steps or write debug scripts:
> 1. **Check triplets** — `diagnostics/triplets.yaml` may already cover this error
> 2. **Read official docs** — Check the model's own documentation (PDF manual, README,
>    official examples) for expected input formats, variable names, and units
> 3. **Find working examples** — Look in `outputs/` for previous successful runs of
>    this model, or check if the model ships with test/example data
> 4. **Fix the tool** — Now that you know what "correct" looks like, make targeted fixes
>
> Resist the urge to write diagnostic/debug Python scripts. The answers are almost
> always in the official docs and working examples, not in reverse-engineering the binary.

<!-- KI-MAP:BEGIN -->
## KI MAP (projected — do not hand-edit)

| component | read it | why |
|---|---|---|
| `dag.yaml` | before choosing what to compare | the KI's own truth about inputs, outputs, units and which outputs are observable |
| `docs/format_spec.yaml` | when writing or parsing a model file | machine-readable I/O contract, projected from the dag |
| `diagnostics/triplets.yaml` | the moment anything looks wrong | symptom -> diagnosis -> remedy; check here BEFORE writing a debug script |
| `docs/validation_convention.yaml` | before calling a run good or bad | the field's cited pass-bands and each metric's direction |
| `docs/gathered_papers.json` | when a band or a formula needs provenance | the literature this KI was built from, with local text paths |
| `preflight_check.py` | before every run | binary, imports and data files verified; emits PREFLIGHT_REPORT= |
| `knowledge_infrastructure.yaml` | when auditing this KI | projected manifest: tool/triplet counts, observable outputs, validation tier |
| `tools/_hstar_io.py` | at its pipeline stage | executable tool |
| `tools/_local_metrics.py` | at its pipeline stage | executable tool |
| `tools/build_analysis_control.py` | at its pipeline stage | executable tool |
| `tools/build_back_analysis.py` | at its pipeline stage | executable tool |
| `tools/build_boundary_conditions.py` | at its pipeline stage | executable tool |
| `tools/build_case_from_template.py` | at its pipeline stage | executable tool |
| `tools/build_contact_joints.py` | at its pipeline stage | executable tool |
| `tools/build_dynamic_seismic.py` | at its pipeline stage | executable tool |
| `tools/build_loads.py` | at its pipeline stage | executable tool |
| `tools/build_material_file.py` | at its pipeline stage | executable tool |
| `tools/build_mesh_files.py` | at its pipeline stage | executable tool |
| `tools/build_reinforcement.py` | at its pipeline stage | executable tool |
| `tools/build_reliability.py` | at its pipeline stage | executable tool |
| `tools/build_seepage.py` | at its pipeline stage | executable tool |
| `tools/build_stability_analysis.py` | at its pipeline stage | executable tool |
| `tools/build_staged_construction.py` | at its pipeline stage | executable tool |
| `tools/build_thermal.py` | at its pipeline stage | executable tool |
| `tools/parse_outputs.py` | at its pipeline stage | executable tool |
| `tools/run_hstar.py` | at its pipeline stage | executable tool |
| `tools/validate_results.py` | at its pipeline stage | executable tool |
| `docs/s0_overview_and_build.md` | at that stage | stage procedure, verification and traps |
| `docs/s1_case_layout_and_control.md` | at that stage | stage procedure, verification and traps |
| `docs/s2_mesh_and_geometry.md` | at that stage | stage procedure, verification and traps |
| `docs/s3_materials_and_constitutive.md` | at that stage | stage procedure, verification and traps |
| `docs/s4_boundary_conditions_and_loads.md` | at that stage | stage procedure, verification and traps |
| `docs/s5_analysis_control_and_solvers.md` | at that stage | stage procedure, verification and traps |
| `docs/s6_execution.md` | at that stage | stage procedure, verification and traps |
| `docs/s7_outputs_and_parsing.md` | at that stage | stage procedure, verification and traps |
| `docs/s8_validation.md` | at that stage | stage procedure, verification and traps |
| `docs/s9_advanced_capabilities.md` | at that stage | stage procedure, verification and traps |

_20 tool(s), 33 diagnostic triplet(s)._
<!-- KI-MAP:END -->

<!-- KI-TOOL-INDEX:BEGIN -->
### KI TOOL INDEX (projected — exact KI-relative paths)

- `preflight_check.py`
- `tools/build_analysis_control.py`
- `tools/build_back_analysis.py`
- `tools/build_boundary_conditions.py`
- `tools/build_case_from_template.py`
- `tools/build_contact_joints.py`
- `tools/build_dynamic_seismic.py`
- `tools/build_loads.py`
- `tools/build_material_file.py`
- `tools/build_mesh_files.py`
- `tools/build_reinforcement.py`
- `tools/build_reliability.py`
- `tools/build_seepage.py`
- `tools/build_stability_analysis.py`
- `tools/build_staged_construction.py`
- `tools/build_thermal.py`
- `tools/parse_outputs.py`
- `tools/run_hstar.py`
- `tools/validate_results.py`

<!-- KI-TOOL-INDEX:END -->



---

# HSTAR — Knowledge Infrastructure Skill Document

> **Version**: 2025.07 source snapshot (31 Fortran files, ~73 000 lines, 17 compiled units)
> **Domain**: structural_mechanics (hydraulic structures — concrete & rockfill dams, ship locks,
> sluices, slopes, tunnels, reinforced-concrete members)
> **Last updated**: 2026-08-26
> **Validation status**: partial_replacement — real compiled binary, full KI pipeline, verified
> against a closed-form elasticity benchmark (`validation_tier: analytic`)

---

## 1. Model Identity

| Property | Value |
|----------|-------|
| Full name | HSTAR — Hydraulic-STRuctures Analysis, FEM90 kernel |
| Version | 2025.07 source snapshot; implementation id `hstar-fem90-linux-ifx` |
| Language | Fortran 90 (Intel dialect: `FORM='BINARY'`, `pause`, `TIME()`) |
| License | Proprietary / research-group internal |
| Repository | none public (source tree only) |
| Citation | M. Pastor, T. Li and P. Mira (1997), FEM90 kernel; extended by the Chinese hydraulic-structures community through 2025-07 |
| Primary domain | Structural / geotechnical mechanics |
| Spatial mode | Unstructured finite-element mesh, 2-D plane strain / axisymmetric / 3-D |
| Entry point | `PROGRAM FEM90`, `Fem.f90:4` |
| Numerics | Intel MKL — PARDISO (direct sparse), VSL (random fields), RCI `DTRNLSP` (Levenberg–Marquardt inversion) |
| Parallelism | OpenMP inside MKL (`ncpu` in `<probn>.sol`) |

---

## 2. What This Model Does

HSTAR is a general implicit/explicit finite-element solver for the stress, deformation,
temperature, seepage and stability of hydraulic structures and their soil-and-rock foundations.
One binary covers quasi-static and dynamic mechanics, heat conduction in mass concrete
(including embedded pipe cooling), steady and transient groundwater seepage, Biot u–p / u–pw
coupled consolidation, node-pair contact and Goodman joints, sliding-stability safety factors,
FORM reliability, and parameter back-analysis from monitoring data.

Everything is switched from integers and keywords in a single free-format control file
`<probn>.glb`. There is no CLI, no namelist and no self-describing format: **the working
directory is the interface**, because the binary opens a file literally named `inp`.

**What it does NOT do** (from `dag.yaml` `boundary.scope_out`): rainfall–runoff generation (it
*takes* a reservoir level, it does not compute one); free-surface reservoir hydrodynamics (water
is an added mass or a pressure boundary); chemical degradation / ASR / rebar corrosion kinetics;
explicit crack-path tracking (cracking is smeared or damage-based); meteorological forcing of any
kind (thermal boundary conditions are prescribed by the analyst).

---

## 3. Input Requirements

**Exact shapes live in `docs/format_spec.yaml`** (projected from `dag.yaml` + triplets —
regenerate it, never hand-edit). This section explains intent and gotchas; the spec file is the
contract. Full per-file field order is in `docs/s1_…` through `docs/s5_…`.

### 3.1 Time-varying drivers ("forcing")

HSTAR has **no meteorological forcing**. Its four time-varying drivers are all analyst-supplied
boundary conditions, not gridded datasets — so `ki_tools_common.load_forcing` is *not* used by
this KI. See `docs/input_preparation.md` for the reasoning and the schema checks that were run.

| Driver | Unit model expects | Source | Where it goes |
|---|---|---|---|
| `reservoir_water_level` | m (elevation) | user / reservoir operating record | `cor0` on the water edge-load record of `<probn>.loa`; `water_level(1:nblks)` in `<probn>.glb` |
| `base_acceleration_time_history` | m s⁻² | design accelerogram or record | `SEISMIC` time curve in `<probn>.loa`, referenced by `earthquake_curve(1:ndimn)` in `<probn>.man` |
| `boundary_temperature` | °C | ambient / measured surface temperature | prescribed-temperature and convection-edge records in `<probn>.tem` |
| `cooling_water_temperature` | °C | cooling-plant schedule | `water_curve` on the `HEAT` material record of `<probn>.mat`; pipe records in `<probn>.tem` |

### 3.2 Static inputs and parameters

| Input | Unit | Source kind | Tool that prepares it |
|---|---|---|---|
| Mesh coordinates / connectivity | m | user (GiD, mesher) | `tools/build_mesh_files.py` |
| `youngs_modulus` | Pa | calibrated | `tools/build_material_file.py` (token 5, `SOLID` line of `.mat`) |
| `poissons_ratio` | – | default | `tools/build_material_file.py` (token 6) |
| `mass_density` | kg m⁻³ | default | `tools/build_material_file.py` (token 2) |
| `thermal_expansion_coefficient` | °C⁻¹ | default | `tools/build_material_file.py` (token 7) |
| `thermal_diffusivity` | m² per model time unit | calibrated | `tools/build_thermal.py` (`alfa` on the `HEAT` record) |
| `cohesion` | Pa | calibrated | `tools/build_material_file.py` (`CLASSICALEP` / `GOODMAN`) |
| `friction_angle` | degree | calibrated | `tools/build_material_file.py` |
| `tensile_strength` | Pa | calibrated | `ftcrack` in `.glb`; `GOODMAN` sub-record |
| `joint_normal_stiffness` `kn` | Pa m⁻¹ | calibrated | `tools/build_contact_joints.py` |
| `joint_shear_stiffness` `ks` | Pa m⁻¹ | calibrated | `tools/build_contact_joints.py` |
| `hydraulic_conductivity` | m s⁻¹ | calibrated | `tools/build_seepage.py` (`permiability` on the `FLUID` record) |
| `beam_section_properties` `Aera J Iy Iz` | m², m⁴ | user | `tools/build_reinforcement.py` |
| `initial_stress_field` | Pa | derived (previous run) | `<probn>.ini` read when `ninit /= 0` |
| `contact_state` | – | derived | unformatted `<probn>.ctt`, re-read when `restart_ctt /= 0` |
| `restart_state` | – | derived | unformatted `<probn>.rtt`, read when `restart /= 0` on line 2 of `inp` |

### 3.3 Configuration files

A case is **one flat directory** containing `inp` plus ~35 files named `<probn>.<ext>`.

| File | Format | Notes |
|---|---|---|
| `inp` | 5-line free-format | Only fixed name. Line 2 = `restart relis sysrelis ADINA Uopt_R gamamax`; line 4 = `probn`; line 5 = `runblks` |
| `<probn>.glb` | free-format list-directed, **strictly ordered, with conditional records** | Master control: `npoin npoinb nelem ndimn nmats ngroup`, `type_problem`, `type_solver`, `type_load`, `type_nl`, `mdofn`/`lmdofn`, `nblks`, `outplot`, `kstab`, `Bparameter`, `relis` … |
| `<probn>.cor` / `.ele` | free-format | Node coordinates / element connectivity. Counts **must** match `.glb` |
| `<probn>.mat` | keyword records | Material families (15) and constitutive sub-records |
| `<probn>.pre` | free-format | Prescribed variables/supports, **one complete group of sets per load block** |
| `<probn>.loa` | keyword blocks | `gravy`, edge/surface pressure, point loads, time curves |
| `<probn>.man` | free-format | Increment/step schedule, one record group per load block |
| `<probn>.sol` | free-format | Solver settings (`mtype, ncpu, msglvl`), one group per block |
| `<probn>.tem`, `.aqu`, `.ctt`, `.act`, `.bar`, `.ifs`, `.sto`, `.btl`, `.obs` | per-capability | thermal, seepage, contact, staged construction, rebar, fluid-structure, stochastic, back-analysis, observations |

> **COPY-FIRST is mandatory.** Never author `.glb` / `.pre` / `.man` from a Python dict. The
> record order is conditional on switches earlier in the same file, so a "regenerated" file
> silently shifts every downstream read. Start from `tools/build_case_from_template.py` and edit
> named values through `GlbDoc` (see triplet `dt_003`, `dt_029`, `dt_030`).

---

## 4. Build Instructions

```bash
export PATH=/opt/intel/oneapi/compiler/2025.3/bin:$PATH
MKL_INC=/opt/intel/oneapi/mkl/latest/include
MKL_LIB=/opt/intel/oneapi/mkl/latest/lib/intel64
BUILD=/tmp/hstar_build; SRC=/tmp/claude-1000/kdt-work/HSTAR/source
mkdir -p $BUILD
gcc -c /home/huijun/HSTAR_Next/_archive/src/gidpost_stub.c -o $BUILD/gidpost_stub.o

# STRICT dependency order — module files must exist before their users compile
for f in Vartype.f90 Array.f90 Elements.f90 gidpost.F90 vsl_gauss_module.f90 \
         Global.f90 Material.f90 meshfine.f90 Load.f90 Prescrib.f90 Solver.f90 \
         Output.f90 Temper.f90 Stiff.f90 Residu.f90 Level.f90 Fem.f90; do
  ifx -c -O2 -module $BUILD -I $BUILD -I $MKL_INC $SRC/$f -o $BUILD/${f%.*}.o
done

ifx -O2 -qopenmp $BUILD/*.o -o $BUILD/hstar \
    -L$MKL_LIB -lmkl_intel_lp64 -lmkl_intel_thread -lmkl_core -liomp5 -lpthread -lm -ldl
```

Shipped as `/tmp/claude-1000/kdt-work/HSTAR/build_hstar.sh`. Built binary:
`/tmp/claude-1000/kdt-work/HSTAR/build/hstar` (ELF 64-bit LSB, x86-64, ~7.8 MB).

**Known build issues:**
- **`gfortran` cannot build HSTAR** — `FORM='BINARY'` (Intel extension, not `access='stream'`),
  `pause`, and portability `TIME(character)`. Triplet `dt_002`.
- **Compilation order is not optional** — `Global.f90` defines `global_var`, `use`d by every
  later unit. Alphabetical order fails with "module not found".
- **`lib64/*.lib` are Windows binaries** (gidpost, hdf5). On Linux link the C stub instead. It
  only matters for `outplot='GIDL'`; every shipped case uses `'GIDR'` (pure-Fortran ASCII).
- **`OPT.F90` and the `.f` / `.inc` files are NOT in the build** — they are absent from the
  Visual Studio project too. `include 'mkl_rci.f90'` at the top of `Fem.f90` is resolved by
  `-I $MKL_INC`.

---

## 5. Execution

```bash
# Smoke test on a shipped template
python3 tools/run_hstar.py --template column_selfweight --outdir /tmp/smoke
python3 tools/parse_outputs.py --dir /tmp/smoke

# A prepared case, with an explicit binary and thread count
HSTAR_BIN=/tmp/claude-1000/kdt-work/HSTAR/build/hstar \
  python3 tools/run_hstar.py --case /tmp/mycase --outdir /tmp/myrun --omp-threads 8
```

`run_hstar.run()` implements the KDT execution-wrapper contract: **copy** the case/template into
a workspace → **swap in** whole user files (`swap_files={"1.cor": "/path/new.cor"}`) → **modify**
only named values through `GlbDoc`/`set_inp` (never regenerate) → `check_consistent()` compares
`.cor`/`.ele` record counts against `npoin`/`nelem` and returns `status: "input_error"` instead
of crashing → **run** with `cwd=workspace` → **collect** results into `--outdir`.

**HSTAR asks questions on stdin.** Three interactive `read *` sites fire in ordinary runs
(`Output.f90:3605` when `winit /= 0`; `Fem.f90:378/385/417` when `submodel < 0`;
`Global.f90:767` `pause` when `ljdp /= 0`). With stdin closed the first produces
`forrtl: severe (24): end-of-file during read, unit -4, file /proc/<pid>/fd/0` **after a fully
converged solution** — the results on disk are valid, only the exit code is wrong (triplet
`dt_001`). `run_hstar.default_stdin()` reads `winit`/`submodel` from the case's own `.glb` and
supplies the answers automatically.

**Template catalogue** (`tools/_hstar_io.TEMPLATES`): `static`, `column_selfweight`,
`lame_cylinder`, `cooks_membrane`, `mini_3d`, `train01_gravdam_static`,
`train02_gravdam_seismic`, `train03a_modal_dry`, `train05_slope_stability`,
`train07_thermal_transient`, `train12_seepage_steady`.

**Expected runtime**: the 42-node `column_selfweight` benchmark completes in < 1 s; the
`train01_gravdam_static` gravity-dam case in a few seconds; transient thermal and seismic cases
scale with `nblks` × steps and the PARDISO factorisation cost.

---

## 6. Output Description

**Sourced from `dag.yaml`** — if this section and the dag disagree, the dag wins and this section
is the bug.

**Headline output** (`validation_rank: 1`):

> `DISPLACEMENT` — Displacement vector at every mesh node of the solid medium - the concrete dam
> or lock body together with its soil and rock foundation. This is the quantity dam monitoring
> instruments (plumb lines, invar wires, geodetic targets, GNSS) measure directly, and the
> quantity every HSTAR analysis is judged by. (m)

| Output variable (dag `var`) | rank | File | Unit | Medium |
|---|---|---|---|---|
| `DISPLACEMENT` | 1 | `<probn>.flavia.res`, block `DISPLACEMENT` | m | solid — concrete + soil/rock foundation |
| `TEMPERATURE` | 2 | `<probn>.flavia.res`, block `TEMPERATURE` | degC | solid — mass concrete + soil/rock |
| `PORE-PRESSURE` | 3 | `<probn>.flavia.res`, block `PORE-PRESSURE` | Pa | pore water in the soil/rock skeleton |
| `WATER-HEAD` | 4 | `<probn>.flavia.res`, block `WATER-HEAD` | m | groundwater in the soil/rock medium |
| `modal_frequency` | 5 | `<probn>.chk` `order= .. omega= .. freq= ..`; base mode in `<probn>.omg` | Hz | dam–foundation(–reservoir) system |
| `acceleration` | 6 | `<probn>.flavia.res`, blocks `acceleration`, `acceleration_ab` | m s⁻² | solid — dam body + foundation |
| `STRESS` | 7 | `<probn>.flavia.res`, block `STRESS` (`SIGXX SIGYY SIGXY SIGZZ` in 2-D) | Pa | solid — concrete + soil/rock |
| `factor_of_safety` | 8 | `<probn>.chk` safety-factor records (`kstab`), or last converged step (strength reduction) | – | structure on its failure surface |

**Secondary (non-observable) outputs**: `velocity` (m s⁻¹), `PRINCIPALSTRESS` (Pa),
`PLASTICSTRAIN` (–), `Yield` (–), `tofor` (N, total external nodal force),
`uplift-PRESSURE` (Pa; binary state in `<probn>.upf`), `reliability_index` β (–, `.chk` records
containing `beta=`), `equilibrium_residual_ratio` (–, `.chk` `ratio for residu norm=`).

`equilibrium_residual_ratio` is HSTAR's own conservation check — the structural analogue of a
water balance. **Always read it after a run** (`tools/validate_results.py` does).

---

## 7. Tool Inventory

Every tool traces to a capability in `docs/capabilities.md` (34 capabilities) and a category in
`docs/input_preparation.md`.

| Tool | Purpose | Capability # |
|---|---|---|
| `tools/build_case_from_template.py` | COPY-FIRST entry point: clone a shipped case as the starting workspace | 1 |
| `tools/build_mesh_files.py` | Write `.cor`/`.ele`, reconcile `.glb` counts, structural element indices | 19 |
| `tools/build_material_file.py` | Write/edit `.mat` — 15 constitutive families, creep, section geometry | 17, 18, 19 |
| `tools/build_boundary_conditions.py` | Write/inspect `.pre` — prescribed variables and supports, per load block | BC |
| `tools/build_loads.py` | `.loa` — gravity, edge/surface pressure, hydrostatic + reservoir level, point loads, uplift, time curves | 22, 33 |
| `tools/build_analysis_control.py` | Analysis type, solver, DOF set, time integration, remeshing | 1, 4, 5, 9, 25, 32 |
| `tools/build_thermal.py` | Steady/transient heat conduction, convection edges, embedded pipe cooling | 6, 7 |
| `tools/build_seepage.py` | Steady/transient seepage, free-surface nodes, u–p / u–pw consolidation | 8, 9 |
| `tools/build_contact_joints.py` | Node-pair contact, Goodman joints, thin layers, contact damage | 10 |
| `tools/build_dynamic_seismic.py` | Newmark/explicit integration, earthquake input, added mass, absorbing boundaries, equivalent linearisation, liquefaction | 2, 3, 21, 28, 29 |
| `tools/build_stability_analysis.py` | Limit-state safety factor, strength reduction, rigid-block sliding | 11, 12, 13 |
| `tools/build_reliability.py` | FORM, system reliability, stochastic/random material fields | 14, 15, 27 |
| `tools/build_back_analysis.py` | Parameter inversion against monitoring data (LM / trust region / rigid split) | 16 |
| `tools/build_reinforcement.py` | Rebar, bond-slip, bolts/anchors, beams, cooling-water pipes | 20 |
| `tools/build_staged_construction.py` | Element birth/death, per-block material swap, self-weight release | 23 |
| `tools/run_hstar.py` | **Execution wrapper** — copy → swap → modify → run → collect; restart handling | 1, 30 |
| `tools/parse_outputs.py` | Read every result stream (`.flavia.res`, `.chk`, `.omg`, `.gpv`, `.upf`) → Python/JSON/CSV | 31 |
| `tools/validate_results.py` | Plausibility screen, equilibrium (conservation) check, analytic benchmark, metrics | 34 |
| `tools/_hstar_io.py` | Shared private helpers: `GlbDoc`, `set_inp`, `TEMPLATES`, encoding-safe readers | — |
| `tools/_local_metrics.py` | In-KI fallback for `ki_tools_common.metrics.all_metrics` | — |

### Shared utilities (ki_tools_common)

```python
from ki_tools_common.metrics import all_metrics       # NSE/KGE/PBIAS/RMSE/r — used by validate_results
from ki_tools_common.cross_platform import detect_binary_type, run_binary
```

`load_daily_forcing` / `lookup_hwsd` / `igbp_to_usgs` / `rosetta_vgn` / `validate_water_balance`
are **deliberately not used**: HSTAR consumes no meteorological forcing, no HWSD soil hydraulics
and no land cover, and has no closed water budget (see §2 and `dag.yaml boundary.scope_out`).
`tools/_local_metrics.py` is the fallback when `ki_tools_common` is not importable
(triplet `dt_033`).

---

## 8. Unit Conversion Table

| Variable | Source unit (as normally supplied) | Model unit | Factor | Type |
|---|---|---|---|---|
| Young's modulus | GPa or MPa (engineering practice) | Pa | ×1e9 / ×1e6 | multiplicative |
| Cohesion, tensile strength | kPa or MPa | Pa | ×1e3 / ×1e6 | multiplicative |
| Joint stiffness `kn`, `ks` | MPa/m | Pa m⁻¹ | ×1e6 | multiplicative |
| Water pressure head | m of water | Pa | ×ρ_w g = ×9810 | multiplicative |
| Piezometer head | m | Pa (`PORE-PRESSURE`) | ×9810 | multiplicative |
| Accelerogram in g | g | m s⁻² | ×9.81 | multiplicative |
| Plumb-line displacement | mm | m (`DISPLACEMENT`) | ×1e-3 | multiplicative |
| Hydraulic conductivity | cm/s or m/day | m s⁻¹ | ×1e-2 / ÷86400 | multiplicative |
| Thermal diffusivity | m²/h or m²/day | m² per **model time unit** | must match `.man` step unit | multiplicative |
| Temperature | K | degC | −273.15 | additive |
| Friction angle | radian | degree | ×180/π | multiplicative |

> The two that bite hardest: **the water unit weight** (a factor of 9810 in either direction —
> triplets `dt_008` and `dt_011`) and **the thermal time unit** (`alfa` must be expressed in the
> same time unit as the `.man` increment schedule — triplet `dt_013`).

## 8c. Sign Conventions and Output Units

| Variable | Convention in HSTAR | Common alternative | Impact if wrong |
|---|---|---|---|
| `STRESS` | **compression negative** (continuum-mechanics sign) | geotechnical "compression positive" | every stress sign flips; failure criteria misread |
| `DISPLACEMENT` | in global mesh axes, metres, relative to the *undeformed* mesh | mm relative to an installation datum | 1000× error, or an offset that never cancels |
| `PORE-PRESSURE` | Pa, positive = compressive pore water pressure | m of head | 9810× error |
| `WATER-HEAD` | m, datum = the mesh's own vertical origin | local well datum | constant offset that survives every metric |
| `acceleration` | relative to the moving base | `acceleration_ab` = absolute | the base motion is added twice or omitted |
| `factor_of_safety` | dimensionless, > 1 = stable | — | strength-reduction value depends on `miter` (`dt_021`) |
| `TEMPERATURE` | degC | K | 273-degree offset; thermal stress explodes (`dt_014`) |

**Output verification checklist:**
- [ ] Read `equilibrium_residual_ratio` from `<probn>.chk` — it must be small (≲1e-6); a big
      value means the reported field is *not* an equilibrium solution.
- [ ] Confirm `converged: true` from `tools/parse_outputs.py` before trusting any number.
- [ ] Print the first 10 nodal displacements — right order of magnitude for the structure size?
- [ ] For `STRESS`: remember it is **node-averaged** — boundary rows carry a half-element offset
      by construction, not by error (`dt_025`). Verify against analytics at interior nodes.
- [ ] For `acceleration`: which stream did you parse, `acceleration` or `acceleration_ab`?

---

## 9. Diagnostic Triplets (Top 5)

Full corpus: **33 entries** in `diagnostics/triplets.yaml`. The five most likely to fire:

| # | id | Symptom | Diagnosis | Remedy |
|---|---|---|---|---|
| 1 | `dt_001` | Full converged Newton history, then `forrtl: severe (24)` end-of-file on unit -4 | HSTAR asks an interactive `read *` question (`winit /= 0`) with stdin closed; the solution is already on disk | Let `run_hstar.default_stdin()` answer it; the results are valid, only the exit code is wrong |
| 2 | `dt_003` | `forrtl: severe (24): end-of-file` on unit 1/2/3/4/5/9/21 very early in the run | A `.glb`/`.pre`/`.man` record was authored from scratch and its conditional record order is wrong | COPY-FIRST from a template via `build_case_from_template.py`; edit named values through `GlbDoc` |
| 3 | `dt_011` | Water load ~9810× too large; the structure displaces metres and Newton diverges | A reservoir level or pressure head was supplied in metres where HSTAR expects Pa | Multiply head by ρ_w g = 9810 exactly once; check §8 |
| 4 | `dt_006` | Perfectly converged run whose displacements are a million times too large or too small | `youngs_modulus` given in MPa/GPa instead of Pa in token 5 of the `SOLID` line | Convert to Pa (`build_material_file.py` validates the range) |
| 5 | `dt_025` | Analytic stress verification off by exactly half an element's worth of stress at the boundary | The `.flavia.res` `STRESS` stream is averaged from Gauss points to nodes (`average_appear`) | Compare at **interior** nodes, or on the domain mean; this is by construction, not an error |

Also common: `dt_002` (gfortran cannot build), `dt_029`/`dt_030` (`.glb` value silently ignored,
or a `337*0` list-directed repeat count that breaks a naive parser), `dt_028`
(`UnicodeDecodeError` — case files are GBK-encoded, not UTF-8), `dt_032` (non-reproducible
second run because `restart` was left at 1).

---

## 10. Coupling Interfaces

| Upstream model | Variable exchanged | Unit | Temporal resolution |
|---|---|---|---|
| Reservoir operation model / observed stage record | `reservoir_water_level` | m | daily to monthly |
| Seismic hazard / ground-motion selection | `base_acceleration_time_history` | m s⁻² | event, Δt of the record |
| Ambient/measured surface temperature series | `boundary_temperature` | degC | daily |
| Cooling-plant schedule | `cooling_water_temperature` | degC | daily |

| Downstream model | Variable exchanged | Unit | Temporal resolution |
|---|---|---|---|
| Dam safety assessment / SHM statistical models | `DISPLACEMENT` | m | per load block / step |
| Seepage & drainage design | `WATER-HEAD`, `PORE-PRESSURE` | m, Pa | per step |
| Thermal cracking assessment | `TEMPERATURE`, `STRESS` | degC, Pa | per step |
| Risk analysis | `factor_of_safety`, `reliability_index` | –, – | per case |

HSTAR is a **terminal** structural model in a HydroCraft chain: it consumes a reservoir level, it
never produces one.

---

## 11. Performance Metrics

### Benchmark: confined self-weight elastic column (oedometer condition)

| Property | Value |
|---|---|
| Case | 20 Q4 plane-strain layers, 42 nodes, H = 10 m |
| Parameters | E = 2.5e10 Pa, ν = 0.20, ρ = 2400 kg m⁻³, g = 9.81 m s⁻² |
| Analytic solution | u(y) = −ρg(H²−(H−y)²)/(2E_oed), E_oed = E(1−ν)/((1+ν)(1−2ν)); σ_yy = −ρg(H−y); σ_xx = K₀σ_yy, K₀ = ν/(1−ν) |
| Pipeline exercised | `build_case_from_template` → `build_mesh_files` → `build_boundary_conditions` → `build_material_file` → `build_loads` → `run_hstar` → `parse_outputs` → `validate_results` |
| Validation tier | **analytic** |

### Judged against the field's bar — from `docs/validation_convention.yaml`, cited

> Bar for `DISPLACEMENT` (MAE, mm, `direction: minimize`, per **dai2021_dam_displacement_rf**,
> DOI 10.1109/access.2021.3049578): `very_good` ≤ **0.12 mm**, `good` = **no cited threshold
> (null)**, `satisfactory` ≤ **3.12 mm**; `pass_band: satisfactory`.
> Dai et al. monitor radial displacement of a masonry arch dam at point G3-HY and report MAE
> across seven models varying "from 0.12 to 3.12, with high accuracy". Note this is a
> *statistical-model* accuracy on monitoring data, not an FE error band; `evidence_strength:
> weak`, `confidence: 0.45`.
>
> **Achieved on the analytic benchmark**: max absolute displacement error **6.8e-21 m**
> (6.8e-18 mm), i.e. machine precision → **far inside `very_good`**. But this is an *analytic*
> comparison, not a monitoring-record comparison, so it verifies the solver and the KI pipeline;
> it does **not** discharge the `very_good` band against a real dam.

| Metric | Achieved | Bar (convention, cited) |
|---|---|---|
| `max_abs_disp_error` (m) | 6.776e-21 | MAE ≤ 3.12 mm satisfactory, ≤ 0.12 mm very good — dai2021 |
| `max_rel_disp_error` (%) | 1.599e-14 | no cited threshold |
| `u_top` analytic vs HSTAR (m) | −4.23792e-05 vs −4.23792e-05 | — |
| `max_rel_sigma_yy_error_interior` (%) | 0.0 | **no cited threshold** — the model stream is node-averaged and a stress meter measures a local disturbed state, so no band was invented (`structurally_limited`) |
| `equilibrium_residual_ratio` | 5.434e-15 | model's own conservation closure; must be ≪ 1 |
| `n_nodes_compared` | 42 | — |
| Plausibility screen | passed | — |

**Bands that are deliberately `null`** (no cited numeric threshold reachable from this network —
Elsevier, MDPI, IOP, Hindawi and Wiley all return 403 or an Akamai interstitial; the targets are
recorded in `docs/paywalled_targets.json`, not guessed): `TEMPERATURE` (RMSE, degC),
`PORE-PRESSURE` (RMSE, kPa), `WATER-HEAD` (RMSE, m), `modal_frequency` (relative frequency error,
%), `acceleration` (peak relative error, %), `STRESS` (relative error, %), `factor_of_safety`
(relative error, %). A null band means the gate **cannot** auto-validate on it and must not
loosen — report the metric and the loading state, and say it is unbanded.

### Binary and pipeline replacement tracking

| Component | Source | Status | Notes |
|---|---|---|---|
| Compiled binary | Intel ifx 2025.3.3 + MKL 2025.3 | **Validated** | ELF-64; 11/11 shipped template cases parse; `static`, `lame_cylinder`, `cooks_membrane`, `mini_3d`, `train01/02/03a/05/07/12` all EXIT=0 |
| Mesh / geometry | `build_mesh_files.py` | Validated | 42-node column built and run end-to-end |
| Materials | `build_material_file.py` | Validated | E, ν, ρ round-tripped through `.mat` |
| Loads (gravity) | `build_loads.py` | Validated | self-weight benchmark |
| Boundary conditions | `build_boundary_conditions.py` | Validated | oedometer confinement |
| Output parsing | `parse_outputs.py` | Validated | `DISPLACEMENT`, `STRESS`, convergence history |
| Thermal / seepage / contact / seismic / stability / reliability / back-analysis | respective `build_*.py` | **Pending** | configured and exercised on the shipped `train*` cases (EXIT=0), but not benchmarked against an analytic or observed reference |
| Monitoring observations | — | **Not available** | no dam plumb-line / thermometer / piezometer dataset is mounted on this host — this is why the tier is `analytic`, not `real` |

---

## 12. Parameter Selection by Structure Type

> **Not calibration — physically-informed starting points** for a first run, to be replaced by
> back-analysis (`tools/build_back_analysis.py`) once monitoring data exists.

| Structure / material | Key parameters | Rationale |
|---|---|---|
| Mass concrete (dam body) | E = 2.0–3.0e10 Pa, ν = 0.17–0.22, ρ = 2400 kg m⁻³, α = 1.0e-5 °C⁻¹ | Standard C15–C25 dam concrete; α from the JCI early-age report |
| Rock foundation (sound) | E = 1.0–3.0e10 Pa, ν = 0.20–0.25, ρ = 2600–2700 kg m⁻³ | Deformation modulus usually 0.3–1.0× the concrete modulus; the ratio drives the heel stress |
| Rock foundation (weathered / faulted) | E = 1.0–5.0e9 Pa, ν = 0.25–0.30 | Model the weak zone as a separate `nmats` group, not by softening the whole foundation |
| Soil embankment / rockfill | `DUNCANCHANG` (EV/CR/EB) or `SoilPZ`, ρ = 2000–2200 kg m⁻³ | Non-linear stiffness dominates settlement; linear elastic under-predicts crest settlement badly |
| Dam–foundation contact | `GOODMAN`, kn = 1e10–1e12 Pa m⁻¹, ks = 0.1–1.0 × kn, c and φ from the site | kn too soft gives spurious opening; too stiff destroys conditioning (`dt_018`) |
| Mass concrete thermal | diffusivity ≈ 0.10 m²/day ≈ 4.2e-3 m²/h — **express in the `.man` time unit** | Classic value for dam concrete; the unit mismatch is `dt_013` |
| Seepage, foundation rock | k = 1e-7–1e-5 m s⁻¹; grout curtain 1–2 orders lower | Curtain contrast, not absolute k, controls the phreatic surface |
| Rayleigh damping (seismic) | ξ = 5 % at the 1st and 3rd modes | Run `type_problem='E'` first to get the frequencies, then set β₁, β₂ (`dt_019`) |

---

## 13. Known Limitations

- **No observed-data validation.** Tier is `analytic`. No dam monitoring dataset is mounted on
  this host, so `DISPLACEMENT` has never been compared against a plumb line here.
- **Only 6 of 8 observable outputs have any cited band, and 7 of 8 bands are `null`.** Only
  `DISPLACEMENT` (MAE, mm) carries a citable number, from a single arch-dam study.
- **`STRESS` is node-averaged** and structurally not comparable with an embedded stress meter at
  the same scale (`dt_025`, `structurally_limited` in the convention).
- **`factor_of_safety` by strength reduction depends on `miter`** — a solver setting leaking into
  a physical answer (`dt_021`). Always report `miter`, `toler_force` and the reduction schedule.
- **Intel-only build.** gfortran cannot compile the source; there is no portable fallback.
- **No CLI.** The working directory is the interface; every run must be wrapped
  (`tools/run_hstar.py`). Concurrent runs in the same directory will corrupt each other.
- **Case files are GBK-encoded**, not UTF-8 (`dt_028`). All KI readers open them with an
  explicit encoding and a fallback.
- **Capabilities 24 (level set) and 26 (sub-modelling)** are documented in
  `docs/s9_advanced_capabilities.md` but have no preparation tool: they are two integer switches
  plus files produced by a *previous* HSTAR run, so there is nothing to derive.

---

## 14. Spinup / Initialisation Requirements

| Parameter | Value |
|---|---|
| Spinup length | **Not time-based.** HSTAR needs a *stress* initialisation, not a warm-up period |
| Standard procedure | Run a gravity-only block with `winit /= 0` to write `<probn>.inw`, then re-run the real load case with `ninit /= 0` reading it as `<probn>.ini` |
| Why | Without an initial geostatic stress field, the first real load block starts from a zero-stress foundation, so settlement and the failure zone are wrong |
| Staged construction | Use `build_staged_construction.py` (`appear_process`) instead of a single gravity block whenever the construction sequence matters (`dt_012`) |
| Transient thermal | Set the initial temperature field to the placement temperature, not to zero (`dt_014`) |
| Discard from metrics | Yes — the initialisation block's displacements are an artefact; compare *increments* from the end of the initialisation block |
| Restart | `restart=0` fresh, `=1` resume from `<probn>.rtt`, `=2` post-process only. Leaving `restart=1` between runs is `dt_032` |

---

## 15. References

1. Pastor, M., Li, T. and Mira, P. (1997). FEM90 finite-element kernel — the code base HSTAR
   extends (source markers in `Fem.f90`, `Global.f90`).
2. Dai, B. et al. (2021). *An Improved Random Forest Model for the Prediction of Dam
   Displacement.* IEEE Access. DOI 10.1109/access.2021.3049578 — **the only cited numeric band
   in `docs/validation_convention.yaml`.**
3. Li, F. et al. (2020). *The Prediction of Dam Displacement Time Series Using STL, Extra-Trees,
   and Stacked LSTM.* IEEE Access. DOI 10.1109/access.2020.2995592.
4. Cao, W. et al. (2019). *Concrete gravity dams model parameters updating using static
   measurements.* Engineering Structures. DOI 10.1016/j.engstruct.2019.05.072.
5. JCI (2004). *State-of-the-Art Report on Control of Cracking in Early Age Concrete.* J. Adv.
   Concrete Technology. DOI 10.3151/jact.2.141 — the hydration-heat / pipe-cooling physics.
6. Carol, I. et al. (2015). *3D zero-thickness coupled interface finite element.* Computers and
   Geotechnics. DOI 10.1016/j.compgeo.2015.04.016.
7. Hohberg, J.-M. (1993). *On the numerical integration of interface elements.* IJNME.
   DOI 10.1002/nme.1620360104.
8. Full index with cached full-text paths: `docs/gathered_papers.json` (16 papers) and
   `docs/papers_index.md`; unreachable targets in `docs/paywalled_targets.json`.

---

*Generated by the Knowledge Dissection Toolkit.*
