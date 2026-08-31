# HSTAR — Input & Parameter Preparation Plan

**Scope.** Everything HSTAR reads, where it comes from, what changes for a new
case, and what to do when the value is not directly available. Extracted from the
model's own sources (`Global.f90:628-4560`, `Prescrib.f90:170-243`,
`Load.f90`, `Material.f90:275-1000`, `Temper.f90`, `Fem.f90:90-370, 2396-2426`),
its two official manuals, and 93 shipped/working case directories.

---

## 0. Capability inventory (Phase 1b)

`Model: HSTAR` — a ~80 000-line Fortran-90 finite-element code for hydraulic and
geotechnical structures (concrete dams, sluices, slopes, tunnels, RC members).
Direct descendant of **GEHOMadrid** (M. Pastor, Tonchun Li, P. Mira, 1997);
HSTAR is the Hohai University fork that added contact, damage, inverse analysis,
reliability, cooling pipes and the PARDISO/MKL solver path.

| # | Capability | Control | Configure tool | Parse tool |
|---|---|---|---|---|
| 1 | **[PRIMARY]** Static stress analysis (linear & material-nonlinear) | `.glb` `type_problem='Q'` | `set_analysis.py` | `parse_results.py` |
| 2 | Time-dependent / consolidation / transient field analysis | `type_problem='S'` | `set_analysis.py` | `parse_results.py` |
| 3 | Transient dynamic analysis (Newmark implicit, or `EXPLICIT`) | `type_problem='F'` | `set_analysis.py`, `write_loads.py` (SEISMIC curve) | `parse_results.py` |
| 4 | Response-spectrum analysis | `type_problem='E'` | `set_analysis.py` | `parse_results.py` |
| 5 | Modal / frequency analysis | `type_problem='W'` → `frequency_analysis` | `set_analysis.py` | `parse_results.py` |
| 6 | Transient & steady **thermal field** (hydration heat, convection surfaces) | `mdofn=10`, `.tem`, `outintw=1` | `write_thermal.py` | `parse_results.py` |
| 7 | Sequential **thermal-stress** coupling via `.oit` | `outintr/=0` | `write_thermal.py --stress-pass` | `parse_results.py` |
| 8 | **Seepage** field, steady & transient; U–P (Biot) coupling | DOF 8 (`W`), `uwcpl`, `stabpw` | `write_seepage.py` | `parse_results.py` |
| 9 | **Uplift pressure** on dam base | `.glb` `upliftin`, `water_level` | `write_seepage.py --uplift` | `parse_results.py` |
| 10 | **Staged construction / excavation** (element birth–death) | `nblks`, `APPEAR_PROCESS`, `MATNO_PROCESS` | `write_stages.py` | `parse_results.py` |
| 11 | **Contact / joint** analysis (point-to-point gaps, Goodman, thin-layer, MCJOINT) | `.glb` `ngaps/ngapb` block | `write_contact.py` | `parse_results.py` (`.ctr`,`.gdm`,`.ojw`) |
| 12 | **Slope / structural safety factor** (limit state `kstab`, strength reduction `type_load='MAT_DE'`) | `kstab`, `stab_matde` | `set_analysis.py --kstab` | `parse_results.py` |
| 13 | **Concrete damage** (Ghrib–Tinawi), creep, ageing modulus | `.mat` `CONCRETE`, `icreep` | `write_materials.py` | `parse_results.py` |
| 14 | **Reinforcement / bond–slip / prestress** (`steel` element 25, `nrcsteel`) | `.glb` `nrcsteel`, `ikindks` | `write_reinforcement.py` | `parse_results.py` (`.bar`) |
| 15 | **Cooling water pipes** in mass concrete | `.glb` `nwcpipe`, `ECWPIPE` | `write_thermal.py --pipes` | `parse_results.py` |
| 16 | **Fluid–structure interaction**: Westergaard added mass, compressible reservoir, VIE/absorbing boundaries | `.ifs`, `Icaddmass`, `type_ABC` | `write_ifs.py` | `parse_results.py` |
| 17 | **Parameter back-analysis / inversion** (Gauss–Newton and MKL trust-region `dtrnlsp`) | `Bparameter`, `balgor`, `.btl`, `.obs` | `write_inverse.py` | `parse_results.py --inverse` |
| 18 | **Reliability** (FORM β, element and system) | `inp` `relis`,`sysrelis`, `.sto` | `write_reliability.py` | `parse_results.py --reliability` |
| 19 | **Adaptive mesh refinement / submodelling** | `rmesh`, `meshc`, `submodel` | `set_analysis.py` | — |
| 20 | **Restart** from `.rtt` | `inp` `restart` | `run_hstar.py --restart` | — |
| 21 | Level-set (crack/interface tracking) | `level_set` | `set_analysis.py` | — |

Each row maps to at least one tool in `tools/` and at least one triplet in
`diagnostics/triplets.yaml`.

---

## 1. Shared-library schema verification

**Result: `ki_tools_common` is NOT installed on this host.**

```
$ ls /mnt/disk1/Hydrocraft_server/
ls: cannot access '/mnt/disk1/Hydrocraft_server/': No such file or directory
```

Neither `ki_tools_common`, the Data-KI tree, nor `hydrocraft.db` exist here, so
the mandated call-and-inspect step could not be performed against the real
functions. **No schema was invented.** Instead:

* `tools/hstar_common.py` defines the two helpers this KI actually needs —
  `all_metrics(obs, sim)` and `check_equilibrium(...)` — and **prefers
  `ki_tools_common` when it is importable**:

  ```python
  try:
      from ki_tools_common.metrics import all_metrics          # authoritative
  except ImportError:
      from .._fallback import all_metrics                       # local, documented
  ```

* The forcing loaders (`load_daily_forcing`, `load_hourly_forcing`),
  `lookup_hwsd`, `rosetta_vgn` and `igbp_to_usgs` are **not applicable to this
  model**. HSTAR is a structural/geotechnical FEM code: it consumes a mesh, a
  constitutive parameter set, kinematic constraints and mechanical/thermal
  loads. It has no meteorological forcing interface, no soil-hydraulic
  pedotransfer input and no land-cover input. `validate_water_balance` likewise
  has no meaning for a stress analysis; the physically equivalent global check
  is **static equilibrium** (Σ reactions + Σ applied load = 0), implemented as
  `hstar_common.check_equilibrium()` and called by `validate_results.py` after
  every run.

The local `all_metrics` returns exactly:
`{'nse','kge','pbias','rmse','mae','r','n'}` — floats plus an int `n`.
Verified by execution, see `tools/hstar_common.py --selftest`.

---

## 2. File-format ground rules (verified, not assumed)

**Every HSTAR input file is read list-directed (`read(unit,*)`), not with a
fixed-width FORMAT.** Verified mechanically:

```
$ grep -c "read *( *[a-z_]*unit *, *\*" Global.f90 Prescrib.f90 Load.f90 Material.f90
```
returns only `*`-form reads for `.glb .cor .ele .pre .loa .mat .man .tem .nrt
.ifs .sol .opr .btl .obs .sto`. There is **no** `read(gunit,'(3I3,5F8.2)')`
anywhere in the input path.

Consequences, and why the "copy-first" rule still applies:

* Column positions are irrelevant — whitespace-separated tokens are fine.
* **Record boundaries and token ORDER are absolutely rigid.** A list-directed
  read consumes one record per `read` statement and stops as soon as its I/O
  list is satisfied; surplus tokens on that record are silently discarded and
  a short record makes the reader continue onto the NEXT record, silently
  absorbing what was meant to be the following field. This is why a
  hand-written `.glb` fails silently rather than loudly (triplet `dt_004`).
* Fortran **repeat counts are legal input**: `10*0`, `9*0.`, `3*1.0e-05` all
  appear in shipped cases and mean "ten zeros", etc. A writer that emits ten
  literal zeros is equally valid; a *reader* must expand `n*v` (implemented in
  `tools/hstar_io.py:read_tokens`).
* Comment/heading records are **positional, not parsed**: `read(gunit,*)text`
  reads one `character(80)` and throws it away. The header text may say
  anything, but the record must be present. Deleting a heading line shifts the
  whole file by one record.

**Therefore:** `.glb` is edited by *anchored record replacement* on a copied
template (find heading record, replace the record after it), never regenerated.
`.cor .ele .pre .loa .mat .man .tem` are emitted whole, because their record
sequence is fully determined by the manual and is verified line-for-line
against the shipped cases by `hstar_io.py`'s round-trip check.

### Byte-level template inspection

```
$ cat -A templates/static_2d/1.glb | sed -n '1,8p'
NPOIN npoinb NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh level_set ljdp stab_matde$
  81  81  64  2  1  1  0  GIDR  0.0  0  0  0  0  0  99999$
valv1$
ndivide$
NINIT KINIT winit NBLKS NLINK NONSY OUTIP outir outiw neumn equvs type_ABC block_stab nbackf nbspring ebody outind nbackdT ninistn$
  0  0  0  1  0  0  0  0  0  0  0  FIX  0  0  0  0  0  0  0$
```
No tabs (`^I`), no trailing-blank significance, LF line endings. Records 3 and 4
(`valv1`, `ndivide`) are **heading-only placeholders that must still exist**:
`Global.f90:690-696` reads them unconditionally and only reads a *data* record
after them when `rmesh/=0` / `meshc/=0`.

---

## 3. Inputs and parameters, one row per thing HSTAR consumes

Legend for "new case": **U** = user must supply, **D** = derivable on this
server from data already present, **T** = take from template unchanged.

### 3.1 Run driver

| Item | Units / type | Lives in | New case | If unavailable |
|---|---|---|---|---|
| `probn` | path prefix (no extension) | `inp` record 4 | U | Always `1` when running inside a per-case directory; `run_hstar.py` enforces this. |
| `runblks` | int ≤ `nblks` | `inp` record 5 | D (= `nblks`) | Default to `nblks`; smaller values stop the run early on purpose. |
| `restart` | 0 new / 1 restart / 2 re-post | `inp` record 2 field 1 | T (=0) | Restart needs a valid `.rtt`; abort with a clear message if absent. |
| `relis`, `sysrelis` | 0/1 reliability switches | `inp` record 2 | T (=0) | Only set with a prepared `.sto`. |
| `ADINA`, `Uopt_R`, `gamamax` | export / coordinate-optimisation / max-shear-strain flags | `inp` record 2 | T (=0) | — |

### 3.2 Geometry (`*.cor`, `*.ele`)

| Item | Units | Source | New case | If unavailable |
|---|---|---|---|---|
| Node coordinates `ipoin, x, y[, z]` | **metres** (SI throughout — see §4) | `.cor`, one record per node, `npoin` records | U (mesh) | Generate with `write_mesh.py` for boxes/columns/annuli; otherwise import from GiD `.msh`, Gmsh or the `flavia.msh` of an existing case (`write_mesh.py --from-flavia`). |
| Element connectivity `ielem, n1..nN, igroup` | int | `.ele`, `nelem` records | U | Same as above. **Elements must be sorted by `igroup` ascending, no gaps** (manual §3.4); `write_mesh.py` sorts and asserts. |
| `npoinb` | first beam-element node id | `.glb` rec 2 | D | Equals `npoin` when there are no beam elements. |
| `ndimn` | 1/2/3 | `.glb` rec 2 | D from `.cor` width | — |

### 3.3 Element-group definition (`*.glb` GROUP INFORMATION block)

One 3-to-4-record stanza per group. `ngroup` stanzas.

| Item | Type | Meaning | New case | If unavailable |
|---|---|---|---|---|
| `name` | char(10) | element name, e.g. `Q4`, `B8`, `L2` | D from `.ele` node count + `ndimn` | Table in §5. |
| `kname` | char(10) | free label (`Default`, `dam`, `foundation`) | U | Any token; never parsed. |
| `index` | int 1..26 | element-library index | D | **Must agree with `name`** — §5 table; mismatch is triplet `dt_006`. |
| `class` | char | `CO` (continuum) | T | — |
| `nrfields` | 1 or 2 | number of physical fields | D from analysis type | 1 for pure U / T / W, 2 for UW / UT. |
| `fieldid` | `U`,`W`,`T`,`UW`,`UT` | which fields | D | — |
| `special` | char | `ST`, or `BB`/`BC` for incompatible-mode elements idx 5/9/12/18 | T (`ST`) | `BB` enables Simo–Rifai bending enrichment; only for idx 5,9,12,16,18. |
| `sptype` | `PE`/`PS` | plane strain / plane stress (2-D only) | U | Dams and slopes: `PE`. Thin plates: `PS`. |
| `nelgroup` | int | element count in group | D from `.ele` | Must sum to `nelem`. |
| `matno` | int | material id | U | — |
| `type_algo`,`type_stiff`,`type_ecoint`,`ilayer` | int | `0,1,1,1` | T | — |
| `elcod_local` | m | pseudo-thickness of zero-thickness interface elements | U for joints | Use 1/1000 of the joint length as a starting value; 0.0 for continuum. |
| `type_mass(1:nrfields)`, `alfa`, `beta` | int, 1/s, s | 0=consistent / 1=lumped; Rayleigh damping | U for dynamics | `alfa=beta=0` for static. Rayleigh from two target modes and ζ: solve `α=2ζω1ω2/(ω1+ω2)`, `β=2ζ/(ω1+ω2)` using a prior `type_problem='W'` run. |
| `order_time(:,ifield)` | int | 0=value, 1=1st deriv, 2=2nd deriv | D | Static U: `0 0`. Transient thermal: `1`. Dynamics: `2`. |
| `nfdof`, `listdof_f(1:nfdof)` | int | DOFs used by that field | D | `2 / 1 2` for 2-D U; `1 / 10` for T; `1 / 8` for W. |

### 3.4 Global analysis control (`*.glb`, ~40 records)

Full record-by-record layout in `docs/format_spec.yaml` and
`docs/s1_case_setup.md`. Key parameters:

| Item | Values | New case | If unavailable |
|---|---|---|---|
| `type_problem` | `Q` static, `S` time-dependent, `F` dynamic, `E` response spectrum, `W` modal | U | Driven by the question being asked. |
| `type_solver` | `PROFILE`, `PARDISO`, `JPCG`, `PBCG`, `SSORPBCG`, `EXPLICIT` | D | `PROFILE` (skyline LU) up to ~5·10⁴ DOF; `PARDISO` above that; `EXPLICIT` only with `type_problem='F'` and lumped mass. |
| `type_load` | `LOAD`, `ARCLENGTH`, `MAT_DE`, `DISCONTROL` | U | `LOAD` unless doing limit-load (`ARCLENGTH`) or strength reduction (`MAT_DE`). |
| `type_nl` | 4 full N-R, 5 modified N-R, 10 field-only | D | 5 for stress; 10 for thermal/seepage-only. |
| `mdofn`, `lmdofn(1:mdofn)`, `order_time_mdofn` | 1..10 | D | DOF numbering is fixed: 1 Ux, 2 Uy, 3 Uz, 4-6 rotations, 7 hydrostatic pressure, 8 pore pressure, 9 air pressure, 10 temperature (`Global.f90:558-575`). |
| `nblks` | int | D from staging plan | 1 if not staged. |
| `APPEAR_PROCESS(ngroup, nblks)` | 0/1 | D from staging plan | All 1 for a single block. |
| `MATNO_PROCESS(ngroup, nblks)` | int | D | Repeat the group `matno`. |
| `beeta1, beeta2, theta1` | – | T (`0.5 0.25 1.0`) | Newmark γ, β and the θ of the θ-method. `0.5/0.25` is unconditionally stable average-acceleration. |
| `gid_*` / `res_*` flags (20 + 17 of them) | 0/1 | U | Which fields go to `.flavia.res` / `.res`. `gid_u=1, gid_s=1` is the useful minimum. |
| `kstab` | real | U | Target limit-state factor for safety analysis; `0.0` disables. |
| `water_level(1:nblks)` | m | U | `-99.0` = no reservoir. |
| `ngaps/ngapb ...` contact header | – | T | Present-but-zero when there is no contact; the record must still exist. |
| `nrcsteel`, `nwcpipe` | int | T (0) | Records must exist even when zero. |

### 3.5 Constraints (`*.pre`)

Per run-block: `nfixsets, nline`, then per set
`ifixvar, nfixnods, itcurve, tfixvar, outfix, jfixvar, gamawx, nextr`, then the
node list, then the value list.

| Item | Units | New case | If unavailable |
|---|---|---|---|
| `ifixvar` | DOF id 1-10 | D | Same numbering as `mdofn`. |
| node list | ids | D from geometry | Select by coordinate tolerance, never by hand-typed index (`write_boundary.py --select "y<1e-9"`). |
| value list | m, or °C for DOF 10, or m head for DOF 8 | U | 0.0 for a fixed support. Non-zero values are **multiplied by time-curve `itcurve`** — for a constant prescribed temperature the curve must be flat (manual, thermal §3). |
| `tfixvar` | 0 disp / 1 vel / 2 accel | T (0) | — |
| `outfix` | 0/1 | U | 1 writes reactions to `.act`; needed for the equilibrium check. |

### 3.6 Loads (`*.loa`)

Repeated once per run-block. Blocks in fixed order: time curves → point loads →
edge/face-load element definitions → edge-load groups → body force → group
gravity curves → beam loads → plate loads.

| Item | Units | New case | If unavailable |
|---|---|---|---|
| Time curve `ntime,type_curve,nline` + data | s or days | U | `LINEAR` for ramps; `SEISMIC` for accelerograms; `SIN` for ambient air temperature `T=a+b·sin(π(c·t+d)/180)`; `DABT` for adiabatic hydration rise `θ=a·t/(b+t)`. |
| Point load `pxyz(1:nudofn)` | **N** (2-D: N per unit thickness) | U | — |
| Edge/face load element list | node ids + parent element | D from mesh | `write_loads.py --pressure-face` extracts boundary faces by coordinate predicate and orients the outward normal. |
| Edge load `cor0,cor1,p0,p1,fact` | m, m, Pa, Pa, – | U | Hydrostatic: `p0=0` at the water surface, `p1=γw·h` at the base, `fact=1`; or `p0=0,p1=h,fact=9810`. **Positive = compression onto the surface.** |
| Body force `gravy, factg(1:ndimn), factf(1:ndimn)` | m/s², – | T | `9.81` with `factg=(0,-1)` in 2-D, `(0,0,-1)` in 3-D. |
| `tcurvegravity(1:ngroup)` | curve id | D | 0 disables self-weight for that group — used for excavation. |

### 3.7 Materials (`*.mat`)

Fixed 12-record preamble (`material property curves`, `0`, `10`, ten comment
records, ` nmats`, count) then one stanza per material.

| Model | Parameters (in read order) | Units | If unavailable |
|---|---|---|---|
| `ELASTIC_ISOTROPIC` | density, porosity(ratio), thickness, E, ν, α, icreep, +2 | kg/m³, –, m, **Pa**, –, 1/°C | E from UCS correlations or a modal back-calculation; ν=0.2 concrete, 0.25-0.30 rock/soil; α=1e-5 /°C concrete. |
| `DUNCANCHANG` | model(`EV`/`CR`/`EB`), c, φ, K, n, Rf, Nur, Kur, P0, Pa (+`G,F,Vtf` or `Kb,m,dφ`) | Pa, deg, –, –, –, –, –, Pa, Pa | Standard rockfill sets in the literature (Duncan & Chang 1970). |
| `CLASSICALEP` + `criteria` | `MC`/`DP`/`MCJOINT`, σ0(cohesion, Pa), hardening; then φ, ψ; then curve ids | Pa, deg | Mohr–Coulomb c,φ from triaxial tests; ψ=0 (non-associated) is the safe default for dilatancy. |
| `GOODMAN` (`JANBU`) | K1, n, Kzz, Rf, φ, Kzx, pa, γw, c, Ft (+Kzy in 3-D) | –, –, Pa/m, –, deg, Pa/m, Pa, N/m³, Pa, Pa | Joint normal stiffness ≈ 10-100× the adjacent rock modulus per metre. |
| `CONCRETE` | Ghrib–Tinawi damage set (ft, E, ν, …) | Pa | ft ≈ 0.1·fc. |
| `CAMCLAY`, `ClayPZ`, `SandPZ`, `SoilPZ` | critical-state / generalised-plasticity sets | mixed | Pastor–Zienkiewicz parameter sets from the literature. |
| `STEEL_EP`, `STEEL_SP`, `EQUBOLT`, `WATERTIGHT`, `ELASTIC_SPRING`, `ELASTIC_EP`, `ELASTIC_FRICTIONLESS`, `PLANE_LOWFT`, `NOLINORMK` | see `write_materials.py` | | |
| `FLUID` phase | density, ratio, bulk modulus; then permeability(1:ndimn) | kg/m³, –, Pa; **m/s** | Kw=2.2e9 Pa; k from field pumping tests. |
| `'HEAT','SOLID'` | a(1:3) diffusivity, adiabatic-rise curve id, placing-temperature curve id | **m²/day**, int, int | a = λ/(cρ); concrete λ≈2.3 W/m·K, c≈960 J/kg·K → a≈0.0864 m²/day. |
| `'GEOMETRY'` | beam/bar section properties | m², m⁴ | — |
| Creep (`icreep/=0`) | `nr, a, b` then `c(1:nr), d(1:nr), k(1:nr)` | – | `E(t)=E0(1-e^{-a t^b})`, `C(t,τ)=Σ(Ci+Di τ^{-…})(1-e^{-ki(t-τ)})`. |

### 3.8 Load-step control (`*.man`)

Per run-block: heading, `nincs`, then `nincs` pairs of
`miter, ditime, noutn, noutf, nstep, inc_step, nresta, cwater` and
`toler_force, toler_var(1:mdofn)`.

| Item | Units | New case | If unavailable |
|---|---|---|---|
| `miter` | – | U | 20-30 for nonlinear; 5 for linear. |
| `ditime` | s (dynamics) or **days** (thermal/creep) | U | Thermal: 0.2 d for the first days of hydration, then 1 d. Dynamics: ≤ T_min/20. |
| `nstep` | – | U | — |
| `noutn`, `noutf`, `nresta` | – | U | 1 = every step. |
| `toler_force`, `toler_var` | – | T | `1e-5`; `1e-2` is acceptable for thermal. |

### 3.9 Optional / capability-specific files

| File | Needed when | Contents | If unavailable |
|---|---|---|---|
| `.tem` | thermal run | prescribed-T sets, convection surfaces (`sedge,nnode,index,beta_bar`), pipe-cooling block | `beta_bar = β/(cρ) = a·β/λ`; β≈ 20-30 W/m²·K for a concrete face in air. Records must exist with count 0 for a non-thermal run. |
| `.oit` | thermal-stress pass | **binary** nodal ΔT per step, written by the thermal run | Cannot be authored by hand — run the thermal pass first (`write_thermal.py --stress-pass` refuses without it). |
| `.oip` | seepage-pressure coupling | nodal pore pressures | Produced by the seepage run (`outinp=1`). |
| `.ifs` | reservoir interaction | `nifsgroup`, absorbing-boundary groups, `ifsnedge` | Zero-filled template for dry analyses. |
| `.nrt` | non-conforming mesh interfaces | interpolation node list + weights | `0` when meshes are conforming. |
| `.sol` | every run | `Iafile icond ipdchk ising` — one heading + one record per block×incs | Template repeats `0 0 1 1`; harmless for all solvers. |
| `.opr` | every run | recovery/stress-output group control | Template's zero-filled version. |
| `.ftr` | reaction/interface force output | `nforce,ngaps,nforce_gaps,nsafety_gaps` | Zeros. |
| `.ini` | `ninit/=0` | initial stress field | Produce with `ninit=-1` on a gravity-only run first. |
| `.btl`,`.obs` | inversion | parameter list + trust-region controls; observation time series | Observations must be real monitoring data (plumb lines, extensometers); never synthesise. `Bparameter=-1` runs a forward verification instead. |
| `.sto` | reliability | `nbeta,nv,mkiter`; distribution types, means, COVs, correlation matrix | Distribution type 1 normal / 2 lognormal / 3 extreme. |
| `.rtt` | restart | binary state dump | Only from a prior successful run of the SAME model. |
| `.aqu`, `.ftf`, `.stn`, `.upf` | added-mass water, control-node forces, permanent strain, uplift | | Empty/zero templates. |

---

## 4. Units — verified, and where the traps are

HSTAR is **unit-agnostic**: it never converts. Every shipped case uses strict
SI, and the KI standardises on it:

| Quantity | Unit | Verified from |
|---|---|---|
| Length / coordinate / displacement | m | `1.cor` r=1.0→2.0 m; `1.flavia.res` DISPLACEMENT ≈5e-6 |
| Density | kg/m³ | `1.mat` `2.400E+03` for concrete |
| Young's modulus, stress, pressure, cohesion | **Pa** | `1.mat` `2.500E+10` = 25 GPa |
| Force | N | |
| Gravity | m/s² (`9.81`) | `1.loa` body-force record |
| Unit weight γw | N/m³ (`9810`) | edge-load `fact` |
| Temperature | °C | manual, thermal §5 |
| Thermal diffusivity `a` | **m²/day**, *not* m²/s | manual, thermal §5 (`3*.1` with day-based `ditime`) |
| Permeability | m/s | `Material.f90` FLUID phase |
| Time (`ditime`) | s for dynamics, **days** for thermal/creep | manual, thermal §4 |

**The two unit traps that produce a plausible-but-wrong answer, not a crash:**

1. **E in MPa instead of Pa** → displacements 10⁶× too large; the run converges
   normally. `validate_results.py` flags |u|max > L/10 (triplet `dt_010`).
2. **Thermal diffusivity in m²/s with `ditime` in days** → 86 400× too much
   diffusion; the temperature field flattens to the boundary value in one step
   and looks "converged" (triplet `dt_011`).

A third, softer trap: `.glb` `coefMpa` (`1.0e6`) is a *display* scale used when
reporting stresses in MPa, not an input conversion. Changing it does not change
the physics but does change the numbers you read out of `.gpv`.

---

## 5. Element library — name ↔ index (from `Elements.f90:128-153`)

| idx | name | nodes | dim | fields | idx | name | nodes | dim | fields |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `l2` | 2 | 1 | 1 | 14 | `b20c8` | 20 | 3 | 2 |
| 2 | `l3` | 3 | 1 | 1 | 15 | `t3c3` | 3 | 2 | 2 |
| 3 | `t3` | 3 | 2 | 1 | 16 | `q4c4` | 4 | 2 | 2 |
| 4 | `t6` | 6 | 2 | 1 | 17 | `h4c4` | 4 | 3 | 2 |
| 5 | `q4` | 4 | 2 | 1 | 18 | `b8c8` | 8 | 3 | 2 |
| 6 | `q8` | 8 | 2 | 1 | 19 | `l2c2` | 2 | 1 | 2 |
| 7 | `h4` (tet4) | 4 | 3 | 1 | 20 | `b2` (beam) | 2 | 1 | 1 |
| 8 | `h10` (tet10) | 10 | 3 | 1 | 21 | `b2c2` | 2 | 1 | 2 |
| 9 | `b8` (hex8) | 8 | 3 | 1 | 22 | `p4` / `thin_film` | 4 | 2 | 1 |
| 10 | `b20` (hex20) | 20 | 3 | 1 | 23 | `pr6` (wedge) | 6 | 3 | 1 |
| 11 | `t6c3` | 6 | 2 | 2 | 24 | `pr6c6` | 6 | 3 | 2 |
| 12 | `q8c4` | 8 | 2 | 2 | 25 | `steel` | 2 | 1 | 1 |
| 13 | `h10c4` | 10 | 3 | 2 | 26 | `thin_film` | 4 | 2 | 1 |

`*cN` variants are the two-field (U–W / U–T) forms: N is the node count of the
*second*, lower-order field. Index 22 is claimed by both `p4` and `thin_film`
in the source (`Elements.f90:931` and `:958`); `thin_film` overwrites `p4`
unless `modf_element_lib` restores it — see triplet `dt_014`.

---

## 6. Preparation flow for a brand-new case

```
make_case.py            copy a shipped template workspace (COPY-FIRST)
   ↓
write_mesh.py           .cor + .ele   (+ anchored npoin/nelem/ndimn in .glb)
   ↓
set_analysis.py         .glb analysis-control records (anchored replacement)
   ↓
write_materials.py      .mat
write_boundary.py       .pre
write_loads.py          .loa
write_stages.py         .glb staging records + per-block .pre/.loa/.man repeats
write_steps.py          .man
   ↓  (capability add-ons, each anchored/whole-file)
write_thermal.py  write_seepage.py  write_contact.py  write_ifs.py
write_reinforcement.py  write_inverse.py  write_reliability.py
   ↓
run_hstar.py            copy workspace → temp dir → run binary → collect
   ↓
parse_results.py        .flavia.res / .gpv / .act / .chk → JSON
validate_results.py     equilibrium + range checks + metrics vs reference
```

Nothing in this chain writes an HSTAR input file from an f-string template of
the *whole* file: `.glb` edits are anchored on its heading records, and every
generated file is round-trip-checked against the shipped example that defines
its record sequence.
