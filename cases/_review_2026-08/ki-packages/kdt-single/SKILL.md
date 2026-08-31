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
## KI map — what is here and when to read it

*(The toolkit's `generate_skill_map.py` is not installed on this host —
`/mnt/disk1/Hydrocraft_server/` does not exist — so this table was projected by
hand from the KI's actual contents. Re-run the generator, or update this table,
whenever a component is added or removed.)*

| component | when to read it | why |
|---|---|---|
| `dag.yaml` | before any validation, and whenever you need to know what HSTAR actually produces | The 7-block knowledge DAG: identity, boundary, inputs, outputs (with `observability` and `validation_rank`), states, influence, safety. Every scoring path reads this. |
| `docs/format_spec.yaml` | when wiring HSTAR to another tool, or when you need an exact variable name and unit | Machine-readable I/O contract, a projection of `dag.yaml`. 9 forcing inputs, 22 parameters, 8 observable outputs, 7 secondary outputs, 32 known issues. |
| `docs/input_preparation.md` | first, before writing anything | The full capability inventory (21 capabilities) and a preparation plan for every input and parameter HSTAR consumes, with what to do when a value is not available. |
| `docs/validation_convention.yaml` | before declaring a run validated | Per (variable, obs_shape): the headline metric, its direction, the pass bands and the citation for each. Six of seven bands are deliberately `null` — see §11. |
| `docs/gathered_papers.json` / `docs/papers_index.md` / `docs/paywalled_targets.json` | when you need the literature behind a band | 23 papers with retrieved full text, 40 recorded-but-unreadable targets. Every `text_path` was verified to exist. |
| `diagnostics/triplets.yaml` | the moment anything goes wrong — before writing a debug script | 32 symptom → diagnosis → remedy entries, including three record-format traps verified by crashing this build on 2026-08-26. |
| `preflight_check.py` | before every run | 21 real checks: binary starts, libraries resolve, template parses, self-tests pass. Exit 0 = ready. |
| `knowledge_infrastructure.yaml` | when auditing the package | Manifest: package, pipeline, validation tier, tools, inputs, outputs. |
| `docs/s0_build.md` … `docs/s9_inversion_and_reliability.md` | one per pipeline stage, as you reach it | Purpose, Inputs, Outputs, Procedure, Verification, Traps, Example. |
| `tools/` (21 scripts) | to actually do the work | One tool per capability category, plus the execution wrapper and the parsers. |
| `templates/static_2d/` | never edit it; clone it | A complete working case, provenance `lame_cylinder`, reproduced bit-for-bit by this KI's Linux build. |
<!-- KI-MAP:END -->

---

## 1. What HSTAR is, and when to use it

HSTAR is a Fortran-90 finite-element solver for **hydraulic and geotechnical
structures** — concrete gravity and arch dams, sluices, slopes, tunnels and
reinforced-concrete members. It is the Hohai University descendant of
**GEHOMadrid** (M. Pastor, Tonchun Li, P. Mira, 1997), extended over two decades
with contact and joint mechanics, concrete damage, parameter inversion,
structural reliability, cooling-pipe modelling and the Intel MKL PARDISO solver.

About 80 000 lines across 17 compilation units. No Makefile; the shipped project
is Visual Studio / Intel Fortran (`hstar.vfproj`).

**Use HSTAR when** the question is the stress, displacement, temperature, pore
pressure, joint behaviour, vibration or safety factor of a solid structure — and
particularly when several of those are coupled, or when the structure is built in
stages.

**Do not use HSTAR for** mesh generation, reservoir hydrodynamics beyond added
mass, chemical degradation, or anything with a meteorological forcing interface.
HSTAR has none: it is a structural code, not a hydrological one.

---

## 2. Quick start

```bash
python3 preflight_check.py                        # 21 checks; exit 0 = ready

python3 tools/make_case.py        --out case1
python3 tools/write_mesh.py       --case case1 --shape column --width 1 --height 10 --ny 20
python3 tools/set_analysis.py     --case case1 --problem Q --solver PROFILE --nl 5 --dofs 1,2
python3 tools/write_materials.py  --case case1 \
        --mat "id=1;model=ELASTIC_ISOTROPIC;rho=2400;E=2.5e10;nu=0.2;alfa=1e-5"
python3 tools/write_boundary.py   --case case1 \
        --fix "dof=1;where=True" --fix "dof=2;where=y<1e-9;out=1"
python3 tools/write_loads.py      --case case1 --gravity 9.81 --gdir 0,-1
python3 tools/write_steps.py      --case case1 --inc "miter=5;dtime=1.0;nstep=1"

python3 tools/run_hstar.py        --case case1 --output_dir out1
python3 tools/parse_results.py    --output_dir out1 --summary
python3 tools/validate_results.py --output_dir out1 --case case1 --model-size 10 \
        --analytic confined_column --rho 2400 --g 9.81 --E 2.5e10 --nu 0.2 --H 10
```

That sequence is not illustrative — it is the exact chain used to produce this
KI's analytic verification, and it returns `max relative error 1.60e-16`.

---

## 3. Input specification

Exact names, units and record layouts live in **`docs/format_spec.yaml`** and
**`docs/input_preparation.md`**; this section covers only what you must know
before touching a file.

HSTAR reads **fourteen mandatory files** per case, all opened relative to the
current working directory:

| file | contents |
|---|---|
| `inp` | run driver: restart flag, reliability switches, problem-name prefix, `runblks` |
| `1.glb` | ~40 heading/data record pairs of analysis control |
| `1.cor` | node coordinates, metres |
| `1.ele` | element connectivity and group |
| `1.pre` | kinematic and field Dirichlet conditions |
| `1.mat` | constitutive models and parameters |
| `1.loa` | time curves, point/face/body loads |
| `1.man` | load-step and time-step control |
| `1.opr` `1.sol` `1.tem` `1.ifs` `1.nrt` `1.ftr` | recovery, solver, thermal, fluid-interaction, interpolation and force-output control — zero-filled but **present** for an ordinary run |

Optional, capability-specific: `1.oit` `1.oip` `1.ini` `1.rtt` `1.btl` `1.obs`
`1.sto` `1.aqu` `1.stn` `1.upf`.

### The one rule that matters

**Every HSTAR input file is read list-directed** (`read(unit,*)`). Columns do not
matter; **records and token order do, absolutely**:

* `read(gunit,*)text` appears about forty times in `Global.f90` — each consumes
  one whole record and throws it away. Heading records are **positional**.
  Delete one and every later read shifts by a record.
* A record with **too few tokens does not error** — the reader continues onto
  the *next* record to satisfy its I/O list, silently eating the line that
  followed. This is how three of the traps in §9 present.
* Fortran repeat counts (`10*0`, `9*0.`, `3*1.0e-05`) are legal input and appear
  in shipped cases.

Therefore: **`1.glb` is never authored, only cloned and edited by anchored token
replacement.** `tools/set_analysis.py` finds a heading by substring and swaps one
token of the record below it, so the token count cannot drift.

Degree-of-freedom numbering is fixed by `Global.f90:558-575` and is not
configurable: 1 Ux, 2 Uy, 3 Uz, 4-6 rotations, 7 hydrostatic pressure, 8 pore
pressure, 9 air pressure, 10 temperature.

---

## 4. Capabilities

21 capabilities, each with a tool and at least one triplet. Full table in
`docs/input_preparation.md` §0.

| | capability | control |
|---|---|---|
| 1 | **Static stress**, linear and material-nonlinear *(primary)* | `type_problem='Q'` |
| 2 | Time-dependent / consolidation | `type_problem='S'` |
| 3 | Transient dynamics (Newmark or explicit) | `type_problem='F'` |
| 4 | Response spectrum | `type_problem='E'` |
| 5 | Modal / frequency extraction | `type_problem='W'` |
| 6 | Thermal field: hydration heat, convection, steady and transient | `mdofn=10`, `.tem`, `outintw` |
| 7 | Sequential thermal-stress coupling via `*.oit` | `outintr` |
| 8 | Seepage, steady and transient; Biot U-P coupling | DOF 8, `uwcpl`, `stabpw` |
| 9 | Dam-base uplift pressure | `upliftin`, `water_level` |
| 10 | Staged construction / excavation (element birth-death) | `nblks`, `APPEAR_PROCESS` |
| 11 | Contact and joints: gap, Goodman, thin-layer, MCJOINT | `.glb` contact block |
| 12 | Safety factor: limit state (`kstab`) and strength reduction (`MAT_DE`) | `kstab`, `type_load` |
| 13 | Concrete damage (Ghrib-Tinawi), creep, ageing modulus | `.mat` `CONCRETE`, `icreep` |
| 14 | Reinforcement, bond slip, anchors | `nrcsteel`, `ikindks` |
| 15 | Cooling water pipes in mass concrete | `nwcpipe`, `ECWPIPE` |
| 16 | Fluid-structure: Westergaard added mass, compressible reservoir, VIE absorbing boundaries | `.ifs`, `Icaddmass`, `type_ABC` |
| 17 | Parameter inversion: Gauss-Newton and MKL trust-region | `Bparameter`, `balgor`, `.btl`, `.obs` |
| 18 | Reliability: FORM β, element and system | `relis`, `sysrelis`, `.sto` |
| 19 | Adaptive mesh refinement and submodelling | `rmesh`, `meshc`, `submodel` |
| 20 | Restart from `*.rtt` | `inp` `restart` |
| 21 | Level-set crack/interface tracking | `level_set` |

Element library: 26 entries — `l2 l3 t3 t6 q4 q8 h4 h10 b8 b20 pr6` continuum,
their two-field `*cN` variants for U-W and U-T coupling, plus beam (`b2`),
reinforcement (`steel`) and `thin_film`. Table in `docs/s2_mesh.md`.

Constitutive models: `ELASTIC_ISOTROPIC`, `ELASTIC_FRICTIONLESS`,
`ELASTIC_SPRING`, `ELASTIC_EP`, `STEEL_EP`, `STEEL_SP`, `DUNCANCHANG`,
`GOODMAN`, `CLASSICALEP` (MC / DP / TC / VM / MCJOINT), `CAMCLAY`, `CONCRETE`,
`ClayPZ`, `SandPZ`, `SoilPZ`, `PLANE_LOWFT`, plus `FLUID`, `HEAT` and `GEOMETRY`
property blocks.

Solvers: `PROFILE` (skyline LU), `PARDISO`, `JPCG`, `PBCG`, `SSORPBCG`,
`EXPLICIT`.

---

## 5. Execution

HSTAR takes **no command-line arguments** — the `GETARG` block at
`Fem.f90:96-101` is commented out. It reads `inp` from the current working
directory and then every data file relative to it. The only way to select a case
is to `cd` into it with `inp` record 4 = `1`.

`tools/run_hstar.py` implements the required wrapper architecture:

1. **copy** the whole case directory to a fresh temp workspace;
2. **swap in** any `--override` files;
3. **modify** only specific values in `inp` (restart flag, `runblks`) by string
   replacement — never regeneration;
4. **run** the binary with `cwd = workspace`;
5. **collect** the non-empty outputs into `--output_dir`, plus
   `run_report.json`.

A run leaves ~35 files behind, several of which (`*.rtt`, `*.oit`, `*.oip`,
`*.ini`, `*.stf`, `*.ctt`) are read back on later runs. Never run twice in the
same directory — triplet `dt_028`.

Build: `tools/build_hstar.py`, Intel `ifx` + oneMKL. gfortran cannot compile this
code (`dt_002`); the GiD post-processing library is replaced by a C stub, which
is safe as long as `outplot` stays `GIDR`/`GIDA` (`dt_003`, `dt_015`).

---

## 6. Output description

Sourced from `dag.yaml`. The rank-1 variable comes first, with its description
verbatim.

**`displacement_field`** — unit **m**, validation rank **1**, emitted in
`*.flavia.res` block `DISPLACEMENT`, `*.opw`, `*.dis`:

> Displacement vector of the solid structural continuum (concrete, rock or soil
> skeleton) at every mesh node, per output step.

The remaining observable outputs, in rank order:

| rank | output | unit | emitted in | description (verbatim from `dag.yaml`) |
|---|---|---|---|---|
| 2 | `stress_field` | Pa | `*.flavia.res` `STRESS`, `*.gpv`, `*.oew` | Cauchy stress tensor in the solid structural continuum (concrete, rock or soil skeleton), smoothed to nodes and raw at Gauss points. |
| 3 | `temperature_field` | degC | `*.flavia.res` `TEMPERATURE`, binary `*.oit` | Temperature of the solid concrete / rock continuum at every mesh node, including hydration heat and pipe cooling. |
| 4 | `pore_pressure_field` | Pa | `*.flavia.res` `PORE-PRESSURE` / `Excess_PORE-PRESSURE`, binary `*.oip` | Pore water pressure within the porous solid skeleton (dam foundation, embankment or rock mass); the excess block reports the departure from the steady state. |
| 5 | `joint_relative_displacement` | m | `*.ctr`, `*.gdm`, `*.ojw` | Normal opening and tangential slip across a construction joint, contact interface or rock discontinuity in the solid structure. |
| 6 | `natural_frequency` | Hz | `*.chk` | Natural vibration frequency of the structural solid, optionally including Westergaard added mass from the reservoir water. |
| 7 | `support_reaction` | N | `*.act` | Reaction force at constrained nodes of the solid structure; its sum is the global equilibrium check against the applied load. |
| 8 | `safety_factor` | 1 | `*.chk`, `*.fai` | Limit-state or strength-reduction factor of the solid slope / structure, from the kstab limit-state search or the MAT_DE strength-reduction sweep. |

Secondary (not independently observable): `principal_stress`, `plastic_strain`,
`concrete_damage_index`, `bar_axial_force`, `reliability_index`,
`inverted_parameters`, `restart_state`.

`*.flavia.res` block header format is `(a15,i8,f12.5,5i8)` (`Output.f90:2117`);
matrix blocks are followed by one record per component name. Parser:
`tools/parse_results.py`.

---

## 7. Pipeline

```
s0_build            tools/build_hstar.py          docs/s0_build.md
s1_case_setup       make_case.py, set_analysis.py docs/s1_case_setup.md
s2_mesh             write_mesh.py                 docs/s2_mesh.md
s3_boundary_cond.   write_boundary.py             docs/s3_loads_and_bcs.md
s4_materials        write_materials.py            docs/s4_materials.md
s5_loads            write_loads.py                docs/s3_loads_and_bcs.md
s6_thermal_seepage  write_thermal.py,
                    write_seepage.py              docs/s6_thermal_and_seepage.md
s7_load_steps       write_steps.py                docs/s3_loads_and_bcs.md
s8_capabilities     write_stages.py, write_contact.py,
                    write_ifs.py, write_reinforcement.py
                                                  docs/s8_contact_and_stages.md
s9_execution        run_hstar.py                  docs/s5_execution.md
s10_postprocessing  parse_results.py              docs/s7_postprocessing.md
s11_validation      validate_results.py           docs/s7_postprocessing.md
s12_inversion       write_inverse.py,
                    write_reliability.py          docs/s9_inversion_and_reliability.md
```

Shared primitives: `tools/hstar_io.py` (record tokenising with repeat-count
expansion, anchored `.glb` editing, template cloning) and
`tools/hstar_common.py` (metrics, equilibrium check, plausibility check). Both
carry `--selftest`.

---

## 8. Units

HSTAR **converts nothing and checks nothing**. Everything is strict SI, verified
against shipped cases:

| quantity | unit | verified from |
|---|---|---|
| length, displacement | m | `1.cor` r = 1.0 → 2.0 m |
| density | kg/m³ | `1.mat` `2.400E+03` |
| E, stress, pressure, cohesion | **Pa** | `1.mat` `2.500E+10` |
| force | N | |
| gravity | m/s² (`9.81`) | `1.loa` body force |
| unit weight γw | N/m³ (`9810`) | edge-load `fact` |
| temperature | °C | thermal manual §5 |
| thermal diffusivity | **m²/day** | thermal manual §5 |
| permeability | m/s | `Material.f90` FLUID phase |
| time step `ditime` | s for dynamics, **days** for thermal/creep/staging | thermal manual §4 |

The two unit errors that produce a converged wrong answer rather than a crash:

* **E in MPa instead of Pa** → displacements 10⁶ × too large (`dt_010`);
* **diffusivity in m²/s with day-based steps** → 86 400 × over-diffusion, the
  field flattens in one step and looks converged (`dt_011`).

`coefMpa` in `.glb` (`1.0e6`) is a *display* scale for stress reporting, not an
input conversion.

---

## 9. Diagnostics

32 entries in `diagnostics/triplets.yaml`, `dt_001` … `dt_032`. Read that file
before writing any debug script — it is the corpus, and this section is only an
index into it.

Start here by symptom:

| what you see | triplet |
|---|---|
| build fails on `FORM='BINARY'` or missing MKL modules | `dt_002` |
| link fails on `GiD_*` symbols | `dt_003` |
| immediate EOF on unit 1, or nonsense control values in `1.chk` | `dt_004`, `dt_005` |
| `forrtl: severe (24)` on unit 9 after ` in static_U**` | `dt_016` |
| `forrtl: severe (59)` on unit 21 after `nedge=` | `dt_023`, `dt_024` |
| EOF at the start of run block 2 | `dt_030` |
| singular matrix, zero pivot, PARDISO error −4 | `dt_012`, `dt_008` |
| exit 0 but no `1.flavia.res` | `dt_015` |
| displacements in metres where millimetres were expected | `dt_010` |
| thermal field flattens in one step | `dt_011` |
| converged run, displacement far too small or exactly zero | `dt_013` |
| `not converged` buried in `1.chk`, exit status 0 | `dt_026` |
| joint never opens | `dt_018` |
| bond slip identically zero | `dt_020` |
| absorbing boundary reflects | `dt_019` |
| inversion never reduces the residual | `dt_021` |
| FORM β oscillates or goes negative | `dt_022` |
| re-run reproduces the previous answer | `dt_028` |
| uplift does nothing although `upliftin=1` | `dt_029` |
| out of memory on a 3-D model | `dt_032` |

`dt_016`, `dt_023` and `dt_024` are the three record-format traps found by
crashing this build during the 2026-08-26 verification: the `.man` increment
record needs **9** fields (not the manual's 7), the `.loa` face-class record
needs **4** (not 3), and the `.loa` edge-load group record needs **5** (not 4).
All three are HSTAR extensions the GEHOMadrid manual predates.

---

## 10. Provenance and limitations

**Sources.** The model's own Fortran (`Fem.f90`, `Global.f90`, `Output.f90`,
`Material.f90`, `Elements.f90`, `Load.f90`, `Prescrib.f90`, `Temper.f90`), two
internal Hohai University manuals — *GEHOMadrid 程序使用说明 (Beta 1.0)*, April
2004, and *GEHOMadrid 温度场及温度应力场计算说明* — and 93 working case
directories from the HSTAR case library.

**What is missing on this host, and what was done instead.**
The Hydrocraft server tree (`/mnt/disk1/Hydrocraft_server/`) and the
knowledge-dissection toolkit (`/home/server/knowledge-dissection-toolkit`) are
both absent. That means `ki_tools_common`, `generate_skill_map.py`,
`generate_ki_manifest.py`, `generate_format_spec.py`, `ki_dag_generator`,
`openalex_search.py`, `paper_fetch.py`, `stepb_*` and
`verify_ki_structure.py` could not be run. Consequences, all stated where they
apply:

* `dag.yaml`, `docs/format_spec.yaml`, `knowledge_infrastructure.yaml` and the
  KI map above were authored by hand against the documented shapes, and
  `format_spec.yaml` was checked name-by-name and unit-by-unit against
  `dag.yaml`.
* No obs-map row could be confirmed in `hydrocraft.db` — the database does not
  exist here. The dag satisfies the two things the KI controls: every observable
  output carries a `validation_rank`, and every observable output's description
  names its medium.
* `ki_tools_common` schemas were **not invented**. `tools/hstar_common.py`
  imports the upstream `all_metrics` when it is available and otherwise uses a
  documented local fallback. The forcing loaders, HWSD lookup, ROSETTA and land
  cover crosswalk are **not applicable** — HSTAR is a structural code with no
  meteorological, soil-hydraulic or land-cover interface. `validate_water_balance`
  likewise has no meaning here; its structural analogue, global static
  equilibrium, is implemented as `check_equilibrium()` and runs after every run.
* Literature was gathered by talking to the OpenAlex API directly. 23 papers with
  full text retrieved and verified on disk; 40 on-topic targets recorded as
  unreadable with `text_path: null`. Nothing was fabricated.

**Model limitations.**
* Windows-first code: Intel Fortran extensions throughout, and the GiD binary
  output path needs a real `gidpost` library.
* No provenance in any output file — nothing identifies the case, the parameters
  or the binary that produced it.
* Non-convergence is a warning, not an error. HSTAR proceeds to the next load
  step regardless.
* No unit or range checking on any input.
* Mesh generation is out of scope; `tools/write_mesh.py` covers structured boxes,
  columns and annuli, and imports GiD `*.flavia.msh` for anything else.

---

## 11. Performance metrics

Bands and citations come from `docs/validation_convention.yaml`. A metric value
without its band is a number, not a verdict — so both are stated here.

### Displacement vs a closed-form elasticity solution — the tier this KI was validated at

Headline metric **max relative error**, direction **minimize**:

| band | threshold |
|---|---|
| excellent | ≤ 1.0e-3 |
| good | ≤ 1.0e-2 |
| acceptable | ≤ 5.0e-2 |
| unacceptable | > 5.0e-2 |

*Citation:* this KI's own verification, `work/stage_log.json:s8_validation` and
`work/figures/s8_validation.png`, 2026-08-26. Secondary metric NSE, direction
maximize: excellent ≥ 0.999, good ≥ 0.99, acceptable ≥ 0.95.

**Achieved on the Linux ifx/oneMKL build:**

| benchmark | mesh | max rel. error | NSE | band |
|---|---|---|---|---|
| 1-D confined column under self weight | 1 × 20 Q4 | **1.60e-16** | 1.000000 | excellent |
| Lamé thick-walled cylinder, internal pressure | 8 × 8 Q4 | **4.66e-03** | 0.998865 | good |
| Lamé, refined | 16 × 16 Q4 | 1.17e-03 | 0.999920 | good |
| Lamé, refined | 32 × 32 Q4 | 2.92e-04 | 0.999995 | excellent |

Convergence requirement — observed order of accuracy, expected 2.0 for bilinear
elements; bands excellent ≥ 1.95, good ≥ 1.8, acceptable ≥ 1.5:

| refinement | observed order |
|---|---|
| 4×4 → 8×8 | 1.984 |
| 8×8 → 16×16 | 1.996 |
| 16×16 → 32×32 | 1.999 |

Mean **1.993** against the theoretical 2.000 — **excellent**.

### Global equilibrium — always checkable

Headline metric **relative residual**, direction **minimize**: excellent
≤ 1e-6, good ≤ 1e-4, acceptable ≤ 1e-3.

Achieved: reactions 2.35417e5 N against an applied self weight of 2.35440e5 N,
relative residual **9.77e-5** — **good**. That floor is set by HSTAR's own
`*.act` print format (five significant figures), not by solver accuracy.

### The bands that are deliberately null

For **dam displacement monitoring**, **concrete temperature**, **piezometer pore
pressure**, **modal frequency** and **safety factor**, no numeric acceptance
threshold could be cited from the open literature this KI was able to retrieve.
Those bands are `null` and the gate must abstain rather than substitute a
default — the searches performed and what they returned are recorded in
`docs/validation_convention.yaml`. The relevant practice standards (ICOLD
bulletins, Chinese dam-monitoring codes) are not open access; they are listed in
`docs/paywalled_targets.json`.

One caution that *is* citable: if NSE or KGE is reported for a monitoring
comparison, remember their zero points differ — a mean-of-observations benchmark
attains KGE = −0.41, not 0, so "positive KGE" is not evidence of skill (Knoben,
Freer & Woods 2019, doi:10.5194/hess-23-4323-2019).

### Honest tier statement

**Validation tier: `analytic`.** Compared against closed-form elasticity
solutions and a mesh-convergence study. **Not `real`** — no independent observed
data was used. **Not `synthetic`** — the references are exact analytic solutions,
not self-generated model output.

---

## 12. References

**Primary, not online** (the authority for every file format in this KI):

* *GEHOMadrid 程序使用说明 (Beta 1.0)*, Institute of Hydraulic Structures, Hohai
  University, April 2004. 14 pp. Input/output file formats; §3.1 `inp`,
  §3.2 `.glb`, §3.3 `.cor`, §3.4 `.ele`, §3.5 `.pre`, §3.6 `.loa`, §3.7 `.mat`,
  §3.8 `.man`.
* *GEHOMadrid 温度场及温度应力场计算说明*, same institute. The two-pass
  thermal-stress procedure, the `SIN`/`DABT` curve forms, and the `beta_bar`
  definition.
* Pastor, M., Li, T. and Mira, P. (1997) — the authorship line carried in
  `Fem.f90:6-8`.

**Retrieved open-access literature:** 23 papers, indexed in
`docs/papers_index.md` with DOI, role and the `comparing_variable` each serves;
full metadata in `docs/gathered_papers.json`. Those most load-bearing here:

* Knoben, Freer & Woods (2019), doi:10.5194/hess-23-4323-2019 — the NSE/KGE
  zero-point caution used in §11.
* Krause, Boyle & Bäse (2005), doi:10.5194/adgeo-5-89-2005 — efficiency-criterion
  comparison.
* Bennett et al. (2013), doi:10.1016/j.envsoft.2012.09.011 — characterising
  model performance.
* Gens, Carol & Alonso (1993), doi:10.1002/nme.1620360104 — numerical integration
  of interface elements, the formulation behind HSTAR's zero-thickness joints.
* Aliabadian et al. / Cerfontaine et al., doi:10.1016/j.compgeo.2015.04.016 — 3-D
  zero-thickness coupled interface elements.
* Monforte et al., doi:10.1002/nag.2923 — low-order stabilised Biot formulation,
  the reason `stabpw=1` exists for equal-order U-P elements.
* Sevieri & De Falco, doi:10.1016/j.engstruct.2019.05.072 — concrete gravity dam
  model updating from static measurements.

**Unreadable but recorded:** 40 on-topic targets in
`docs/paywalled_targets.json`, each with `text_path: null` and a note saying what
was tried. No content from them is cited anywhere in this KI.
