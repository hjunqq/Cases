# HSTAR — Input & Parameter Preparation Plan (KDT Phase 1c)

This plan is extracted from HSTAR's **own** sources and shipped cases, not from a generic
hydrology/crop template. Every row names the file the binary actually opens, the read statement
that consumes it, and what a NEW case must supply.

---

## 0. Two facts that dominate everything else

### 0.1 HSTAR has NO fixed-width input files

Every `probn.*` text input is read with **Fortran list-directed I/O** (`read(unit,*) ...`).
Verified by grepping every `read(` in `Global.f90`, `Material.f90`, `Load.f90`, `Prescrib.f90`,
`Temper.f90`, `Fem.f90`: there is not a single `FORMAT` statement or format string on an input
read. Consequences:

* Column positions are **irrelevant**. Whitespace-separated tokens on the right lines are what
  matter. The `(3I3, 5I5, 7F8.2)`-style column-shift failure mode that breaks APEX/EPIC/DSSAT
  generators **cannot occur here**.
* What CAN and DOES break is **token count and line order**. A missing integer on a control line
  makes the list-directed read continue onto the NEXT line, silently consuming it, and every
  subsequent record is shifted by one. This is HSTAR's equivalent silent-corruption mode.
* Comment/echo lines are read into a `character(80) text` variable and discarded — but they are
  **positional placeholders**, not optional. Deleting a header line shifts everything after it.

`cat -A` inspection **was** performed on `1.glb`, `1.cor`, `1.ele`, `1.mat`, `1.pre`, `1.loa`,
`1.man`, `1.sol`, `1.tem`, `1.opr`, `1.ftr`, `1.ifs` of `cases/static`. Three findings that a
generator must respect:

1. **Every line ends `^M$` — the shipped cases are CRLF.** They were authored on Windows. Intel
   Fortran on Linux tolerates the trailing CR for the numeric fields these cases end lines with
   (verified: `cases/static` runs to `EXIT=0` under the Linux build). But a **character** field
   that is the LAST token on a CRLF line absorbs the CR — `type_solver` read as `"PARDISO\r"`
   never matches `'PARDISO'` and HSTAR silently falls through to its default solver branch.
   Rule: when editing a control line, keep character keywords away from end-of-line, or normalise
   the whole file's line endings **consistently** (all-LF is also fine). Never mix.
2. **`1.mat` and `1.loa` carry GBK-encoded Chinese comment lines** (`M-hM->M-^S…` in `cat -A`).
   Reading them in Python with the default UTF-8 codec raises `UnicodeDecodeError`. Every tool in
   `tools/` opens HSTAR text files with `encoding="latin-1"`, which is byte-transparent and
   round-trips the GBK bytes untouched.
3. **Tabs (`^I`) appear inside the node lists of `1.loa` and `1.ftr`** — harmless, because
   list-directed input treats a tab as a blank separator.

**Therefore the COPY-FIRST rule still applies, but for a different reason**: the header/echo lines
and the conditional blocks (`if (rmesh/=0) read ...`, `if (nflow/=0) read ...`,
`if (cwater/=0) read ...`) mean a from-scratch generator gets the *record sequence* wrong.
Every tool in `tools/` therefore starts from a shipped template case, and edits values in place.

### 0.2 HSTAR is unit-agnostic — the user chooses a consistent system

There is no unit conversion anywhere in the code. Verified from the shipped cases: all HSTAR test
data uses **strict SI**:

| Quantity | Unit used by every shipped case | Evidence |
|---|---|---|
| Length / coordinate | m | `1.cor` of `lame_cylinder`: radii 1.0 → 2.0 m |
| Young's modulus, stress | Pa | `1.mat`: `2.500E+10` for concrete (25 GPa) |
| Density | kg m⁻³ | `1.mat`: `2.400E+03` |
| Gravity | m s⁻² | `1.loa` body-force block: `9.81000E+00` |
| Force / point load | N | `.loa` `pxyz` |
| Water unit weight | N m⁻³ | `1.pre` of `static`: `0.980E+04` (`gamawx`) |
| Time | s | `.man` `ditime`; Newmark `beeta1/beeta2` dimensionless |
| Temperature | °C | `.mat` `alfa = 1.000E-05` per °C; `.tem` prescribed T |
| Thermal conductivity/diffusivity | `HEAT%alfa(1:ndimn)` — m² per time-unit (diffusivity form used by the pipe-cooling superposition) | `Material.f90:968-990` |
| Permeability | m s⁻¹ (FLUID phase `permiability(1:ndimn)`) | `Material.f90` FLUID block |
| Angles (φ, ψ) | **degrees** in `.mat`, converted internally | `Material.f90` `CLASSICALEP` MC/DP branch |
| Frequency output | Hz | `response_spectrum` / `frequency_analysis` |

**Trap**: mixing MPa for E with metres for coordinates and kg m⁻³ for density silently produces
displacements 10⁶ times too large. There is no range check in HSTAR. `tools/validate_results.py`
implements the plausibility screen HSTAR lacks.

---

## 1. Schema verification of the shared library (mandatory step, performed)

The KDT preflight instructs tools to import `ki_tools_common`. **Verified on this host
(2026-08-26) — the package is NOT importable:**

```
$ /mnt/disk1/Hydrocraft_server/python_env/bin/python -c "import ki_tools_common"
ModuleNotFoundError: No module named 'ki_tools_common'
$ ls /mnt/disk1/Hydrocraft_server/models/ki_tools_common/ki_tools_common/
generate_format_spec.py  generate_ki_manifest.py  generate_skill_map.py  ki_projection_common.py
```

Only the three KI **generator** scripts and `ki_projection_common.py` exist; there is no
`load_forcing`, `soil_utils`, `landcover`, `validation`, `cross_platform`, `metrics` or `units`
submodule to call, so **no return-value schema could be recorded** — attempting to would have
meant inventing one, which is the exact failure this step exists to prevent.

Consequence for this KI:

* `load_daily_forcing` / `load_hourly_forcing` / `lookup_hwsd` / `rosetta_vgn` / `igbp_to_usgs`
  are **not applicable** to HSTAR in any case. HSTAR is a structural/geotechnical FEM solver: its
  drivers are a mesh, material constants, boundary conditions and a load history, not
  meteorological forcing. There is no forcing converter to write.
* `all_metrics`, `validate_water_balance`, `detect_binary_type`, `run_binary`, `convert` ARE
  conceptually useful. Every tool that wants them does:

  ```python
  try:
      from ki_tools_common.metrics import all_metrics          # preferred
  except ImportError:
      from _local_metrics import all_metrics                   # in-KI fallback, same signature
  ```

  `tools/_local_metrics.py` implements RMSE / MAE / relative-error / Pearson r / NSE / KGE / PBIAS
  with the same `all_metrics(obs, sim) -> dict` signature so that the tools work identically once
  the shared library becomes importable.
* `validate_water_balance(P, ET, Q)` has **no meaning for a structural model**. The equivalent
  conservation check for HSTAR is a **static force balance**: ‖residual force‖ / ‖external force‖
  at the last converged iteration, which HSTAR itself writes to `probn.chk`
  (`conver_load check … ratio1= … ratio2= …`). `tools/validate_results.py` parses and enforces it.

---

## 2. The case directory: what a run consists of

HSTAR takes **no command-line arguments**. It opens a file literally named `inp` in the current
working directory:

```
inp                                    (Fem.f90:92-97)
  line 1 : text                        header/echo, content ignored, LINE MUST EXIST
  line 2 : restart relis sysrelis ADINA Uopt_R gamamax
  line 3 : text                        header/echo
  line 4 : probn                       the case BASE NAME (all other files are <probn>.<ext>)
  line 5 : runblks                      how many load blocks to actually run  (Fem.f90:177)
```

`probn` is typically `1`, so the whole case is `1.glb`, `1.cor`, … in one flat directory.
`len_trim(probn)` is used to build every other filename, so `probn` must not contain spaces.

### Files HSTAR OPENS UNCONDITIONALLY (`Global.f90:628-673`)

`.glb .cor .ele .pre .mat .loa .chk .sol .man .opr .opw .oew .ogw .ojw .dis .act .gpv .ini .inw
.tem .ftf .ftr .ifs .aqu .nrt .bar .bem .ctr .gdm .sto .rtt .stf .res .resb .fai .ctt`

Fortran `open` **creates** a missing sequential file, so an empty file is legal for the ones that
are only read when a counter is non-zero. But `.glb .cor .ele .pre .mat .loa .man .sol` are always
read and must have real content. A missing/empty one of those is the
`forrtl: severe (24): end-of-file during read` failure (triplet `dt_003`).

---

## 3. Input inventory — per file

### 3.1 `probn.glb` — master control (`Global.f90:628-1100`, unit 1)

Free-format, strictly ordered, header-line-per-record-group. Record sequence:

| # | Line | Fields (verified against `Global.f90`) |
|---|---|---|
| 1 | text | header |
| 2 | values | `npoin npoinb nelem ndimn nmats ngroup ntlink outplot kstab mat_curve meshc rmesh level_set_problem ljdp stab_matde` |
| 3 | text | header (`valv1`) |
| 4 | *conditional* | `valv1 valv2` — **only if `rmesh/=0`** |
| 5 | text | header (`ndivide`) |
| 6 | *conditional* | `ndefault(1:abs(rmesh))` — **only if `rmesh/=0`** |
| 7 | text | header |
| 8 | values | `ninit kinit winit nblks nlinks nonsym outinp outintr outintw neuman equvs type_ABC block_stab nbackf nbspring ebody outind nbackdT ninistn` |
| 9 | text | header |
| 10 | values | `type_problem type_solver type_load type_nl stabpw nlayer kglb state_change Bparameter balgor upliftin` |
| 11 | text | header |
| 12 | *conditional* | `type_nl_layer1 type_nl_layer2 solver_iter` — **only if `nlayer==2`** |
| 13 | text | header |
| 14 | values | `nmass nsmat nhmat nqmat nldfl kgmat nswkw uwcpl ngrav nflow ECWPIPE` |
| 15 | text | header |
| 16 | *conditional* | `nfreeflownode` then `listfreeflownode(:)` — **only if `nflow/=0`** |
| 17 | text | header |
| 18 | values | `ntsmat nthmat kstat ground_inf src nextrf submodel` |
| 19 | text | header (`MDOFN`) |
| 20 | values | `mdofn` |
| 21 | values | `lmdofn(1:mdofn)` — 0 = DOF absent, ≥1 = compressed DOF number |
| 22 | values | `order_time_mdofn(1:mdofn)` — 0 static, 1 velocity, 2 acceleration |
| 23 | text + values | `beeta1 beeta2 theta1` (Newmark β₁, β₂; θ for the field θ-method) |
| 24… | per-group blocks | `equvs_process(1:ngroup)`, `appear_level(1:ngroup)`, `APPEAR_PROCESS(ngroup × nblks)`, `MATNO_PROCESS(ngroup × nblks)`, `force_process`, `average_appear` |
| … | GiD flags | `gid_u gid_s gid_ms gid_f gid_rot gid_v gid_a gid_T gid_P gid_Pv gid_ep gid_Y gid_FC gid_Ns gid_Ss gid_Mxy gid_bem gid_wh gid_wv gid_bcs` |
| … | res flags | `res_u res_s res_ms res_f res_rot res_v res_a res_T res_P res_Pv res_ep res_Y res_FC res_Ns res_Ss res_Tv res_Pa` |
| … | FSI | `Icaddmass swlifs2006 toth ifswater ifsgravity absorb alfa_p4 stiff_p4` |
| … | crack/tangent | `ftcrack coefMpa ikindks doubsig ktan1 ktan2 nlocalbeam ndimnrt` |
| … | MIF | `ntrans nlaymif epsMIFb gamaMIF ifixvar0_inpb camif dxmif` |
| … | per-block | `hdam(1:nblks)`, `water_level(1:nblks)`, `modf_dis_blocks(1:nblks)`, `uinitial(1:nblks)` |
| … | links | `ILINKS`, `tLINKS` |
| … | **group block ×ngroup** | line A: `elemname name kname index class nrfields fieldid special sptype nelgroup matno type_algo type_stiff type_ecoint ilayer elcod_local group_inf uplift_ic liquj`; line B: `type_mass(1:nrfields)`; line C: `nfdof` then `listdof(1:nfdof)` per field |
| … | joints/contact | `tension_joint`, `contact_joint`, `ngaps ngapb ctt_pe miter_bt torbt iblkbt nonsbt xlwsol method_gapi miter_state type_solver_ctt restart_ctt damp_ctt istatec` |
| … | rebar/pipe | `nrcsteel`, `nwcpipe` |

**New case vs bundled example**: `npoin/nelem/ndimn/nmats/ngroup` and the per-group `nelgroup`
must match the mesh you supply; `nblks` must match the number of `APPEAR_PROCESS` rows and the
number of blocks in `.man`; everything else can be inherited from the template.
`tools/build_case_from_template.py` and `tools/build_analysis_control.py` edit exactly those
values in a copied template and re-verify the counts against `.cor`/`.ele`.

**Derivable vs must-supply**: nothing in `.glb` is derivable from a server dataset — it is all
analyst intent. The tools therefore expose them as explicit keyword arguments with the template's
value as the default, and **refuse** (raise) on an unknown key rather than silently ignoring it.

### 3.2 `probn.cor` — nodal coordinates (unit 2)

One record per node: `ipoin x y [z]` (`ndimn` coordinates). Units: metres. `npoin` records.
New case: supplied by the user's mesher (GiD, Gmsh, ANSYS export) — `tools/build_mesh_files.py`
writes it from a `(npoin, ndimn)` array and cross-checks `npoin` against `.glb`.

### 3.3 `probn.ele` — element connectivity (unit 3)

One record per element: `ielem node_1 … node_nnode igroup`. Node numbering is **1-based** and
must be in the element's canonical local order for the element `index` declared in the `.glb`
group block (Q4 counter-clockwise, B8 bottom face then top face, etc. — `Elements.f90:128-153`).
`tools/build_mesh_files.py` validates that every node id is in `1..npoin` and that the record
count equals `nelem`.

### 3.4 `probn.pre` — prescribed variables / supports (`Prescrib.f90:170-250`, unit 4)

Per load block:
```
text                                     header
nfixsets  nline
  repeat nfixsets times:
    ifixvar nfixnods itcurve tfixvar outfix jfixvar gamawx nextr      (type_ABC /= 'MIF')
    ifixvar ifixvar0 nfixnods itcurve tfixvar outfix jfixvar gamawx nextr  (type_ABC == 'MIF')
    list_fix(1:nfixnods)
    val_fix(1:nfixnods)                  Fortran repeat syntax `11*0.` is legal and used
```
`ifixvar` is the DOF index (1=Ux, 2=Uy, 3=Uz, 4..6=rotations, 7=hydrostatic pressure,
8=pore pressure — `Global.f90:title(1:10)`). `gamawx` is the water unit weight in N m⁻³ used for
the pressure DOF. `tfixvar` is the prescribed value; `itcurve` links it to a time curve in `.loa`.
`tools/build_boundary_conditions.py` builds these sets.

### 3.5 `probn.mat` — materials (`Material.f90:240-1000`, unit 5)

```
text                                     header
nscurve                                  number of stress-strain curves
  per curve: npoints type_curve / strain_curve(1:npoints) / stress_curve(1:npoints)
nline                                    number of comment lines that follow
  nline × comment lines
text
mmats                                    number of material RECORDS (may exceed nmats)
  per record:
    text                                 "material_serial  <i>"
    property name imat                   property ∈ MECHANICAL | HEAT | GEOMETRY
    (MECHANICAL) nphase
      per phase:
        phase                            SOLID | FLUID | AIR | OIL
        (SOLID) material density ratio thickness e nu alfa icreep kind_wt jliqu
                iE iNu density_w
                … model-specific sub-records (see docs/s3_materials_and_constitutive.md)
        (FLUID) density ratio bulkw  /  permiability(1:ndimn)
    (HEAT)     alfa(1:ndimn) source_curve place_curve pipe_cooling
               ialfa
               [water_curve time_cooling gap_cooling eata bcooltime]  if pipe_cooling/=0
    (GEOMETRY) Aera J Iy Iz
```
Units: `density` kg m⁻³, `e` Pa, `nu` –, `alfa` (thermal expansion) °C⁻¹, `thickness` m
(2-D out-of-plane), `ratio` – (mass-participation scaling). `tools/build_material_file.py`
covers `ELASTIC_ISOTROPIC`, `CLASSICALEP` (MC/DP/VM/TC), `DUNCANCHANG`, `GOODMAN`, `CONCRETE`,
`CREEP`, `PLANE_LOWFT`, `STEEL_EP`, `HEAT`, `GEOMETRY`.

**Derivable?** Concrete/rock elastic constants can be taken from the design report or from the
regional defaults table in `docs/s3_materials_and_constitutive.md` (values harvested from the
shipped dam cases). Strength parameters (c, φ) for a rock foundation should come from the site
investigation. When neither exists: **use the documented regional default AND record it in the
run metadata as `assumed`** — `build_material_file.py` writes an `assumed_parameters` list into
its JSON side-car so it can never be mistaken for a measured value.

### 3.6 `probn.loa` — loads and time curves (`Load.f90:134-760`, unit 21)

```
text
ntcurve                                  number of time curves
  per curve: ntime type_curve nstoch_curve nline
             ttime_curve(1:ntime)  /  dfact_curve(1:ntime)
             (SIN / FOURIER / EARTHQUAKE variants read extra records)
text
nplgroup kpload                          point-load groups
  per group: order_time_curve appear_group / pxyz(1:nudofn) / list(1:npload)
text
nedge                                    edge/face definitions used by pressure loads
  per edge group: sedge nnode index vdimn  then  i0 lnode(1:nnode) aelem
text ; text
edge_load_group delgroup                 per BLOCK edge-load assignment
  per group: begin_edge end_edge itcurve water code_load
text
body force block:  g  dir_x dir_y [dir_z] …   then  time_curve_for_each_group(1:ngroup)
nbeamload   /   nplateload
```
Units: `pxyz` N, body-force first token m s⁻², pressures Pa (`code_load` selects
uniform / hydrostatic / linear). `tools/build_loads.py` builds all of these.

### 3.7 `probn.man` — increment / step control (`Fem.f90:2396-2406, 3582-3600`, unit 9)

One block per load block, `nblks` blocks (only `runblks` are executed):
```
text                                     header line — MUST EXIST
nincs cdtest earthquake_curve(1:ndimn)   static_U reads only nincs from this line
  per increment:
    miter ditime noutn noutf nstep inc_step nresta cwater Qstatic
    toler_force toler_var(1:mdofn)
    [cwater/=0 and delgroup>0]  delgroup × ( idelgroup coef_water(1:nstep) )
    [Qstatic/=0]                6 extra records
```
`ditime` seconds; `toler_*` dimensionless relative tolerances. `tools/build_analysis_control.py`
writes it.

### 3.8 `probn.sol` — linear-solver parameters (unit 8)

One block per load block:
```
text            " mtype, ncpu, msglvl"
mtype ncpu msglvl
text            " isdefault"
isdefault
```
`mtype` is the **PARDISO matrix type** (−2 = real symmetric indefinite, 2 = real SPD, 11 = real
unsymmetric); `ncpu` = MKL threads; `msglvl` = PARDISO verbosity. `tools/build_analysis_control.py`.

### 3.9 `probn.act` — staged construction record (unit 12)

Written **and** read by HSTAR; `appear_process` in `.glb` is the authoritative declaration.
`tools/build_staged_construction.py` edits the `.glb` `APPEAR_PROCESS` / `MATNO_PROCESS` matrices
(`ngroup` columns × `nblks` rows; `1` = active, `0` = not yet built, `−1` = removed this block).

### 3.10 `probn.tem` — thermal boundary conditions and pipe cooling (`Temper.f90`, unit 22)

```
text ; n_prescribed_T   [ then node/value records ]
text ; nedge_convection [ then edge records ]
text ; nsurf            [ then surface records ]
text ; npipe algo_pipe  [ then per-pipe records ]
```
`tools/build_thermal.py`.

### 3.11 `probn.ifs` — fluid–structure interface / absorbing boundaries (unit 30)

`nifsgroup`, `nabsgroup`, `nabssgroup`, `ifsnedge` and their element lists.
`tools/build_dynamic_seismic.py`.

### 3.12 `probn.ftr` — force / safety-factor extraction surfaces (unit 29)

```
text ; nforce ngaps nforce_gaps nsafety_gaps
text ; nforce_appear                 1=safety factor 2=internal force 3=both
  per force set: lgroup neface node_face nliste  then the face list
```
`tools/build_stability_analysis.py`.

### 3.13 `probn.opr` — output request (unit 10)

`Irecover wgroup` + per-group node ranges, element ranges `(e1:e2,istre)`, gap list, joint list.
`tools/parse_outputs.py` reads it back to know which groups were written.

### 3.14 `probn.btl` / `probn.obs` / `probn.obsc` — back-analysis control and observations

`.btl` holds the inversion control (parameter list, bounds, initial values, iteration limits);
`.obs`/`.obsc` hold the monitored quantities (node id, DOF, measured value, weight).
`tools/build_back_analysis.py`.

### 3.15 `probn.bar` / `probn.bem` — rebar and beam definitions

`.bar` reinforcement segments + bond law id (`ikindks` 1..5); `.bem` beam section/orientation.
`tools/build_reinforcement.py`, `tools/build_mesh_files.py`.

---

## 4. What must be supplied vs derived vs asked-for

| Category | New case must supply | Derivable on this server | If unavailable |
|---|---|---|---|
| Mesh (`.cor`,`.ele`) | Yes — from the analyst's mesher | No | **Abort and ask.** There is no DEM-to-mesh path for a dam; a fabricated mesh is a fabricated structure. |
| Element type / group split | Yes | Partly — inferable from node count per element | Infer from `nnode` via `Elements.f90:128-153` table; warn. |
| Elastic constants (E, ν, ρ) | Preferably from the design report | Regional defaults in `docs/s3_materials_and_constitutive.md` (concrete 20–30 GPa, ν 0.167–0.2, ρ 2400; rock 5–25 GPa, ν 0.25, ρ 2600–2700) | Use the default, mark `assumed`. |
| Strength (c, φ, ft) | From site investigation | Literature ranges in `docs/s3_materials_and_constitutive.md` | Use range midpoint, mark `assumed`, and run the strength-reduction sweep (`build_stability_analysis.py`) instead of trusting a single value. |
| Reservoir level / `water_level` | Yes (operating condition) | No | Ask. |
| Earthquake time history | Yes | No | Ask, or use a code-spectrum-compatible synthetic and say so. |
| Thermal boundary (air/water T) | Yes | Could come from a meteorological dataset if one were mounted — **none is on this host** | Ask, or run the isothermal case. |
| Newmark β₁,β₂ / θ | No — defaults 0.5/0.25/1.0 (average acceleration, unconditionally stable) | Yes | Use defaults. |
| Solver choice | No | Yes — PARDISO for ≥10⁴ DOF, PROFILE for small/2-D | Default PARDISO with `mtype=-2`. |
| Convergence tolerances | No | Yes — 1e-5 force/displacement for elastic, 1e-3…1e-4 for strongly non-linear contact | Defaults from templates. |

---

## 5. Template inventory (COPY-FIRST sources)

`tools/build_case_from_template.py` ships with this catalogue of **verified-runnable** legacy
cases (all confirmed to run to `EXIT=0` under the Linux `hstar` binary on 2026-08-26):

| Template | Path | Demonstrates |
|---|---|---|
| `static` | `HSTAR_Next/cases/cases/static` | 2-D `Q` analysis, PARDISO, 2 blocks, hydrostatic edge load, `winit=-2` |
| `column_selfweight` | `HSTAR_Next/cases/cases/test_thermal_expansion` | minimal 2-D Q4 confined self-weight column — the analytic benchmark |
| `lame_cylinder` | `HSTAR_Next/cases/cases/lame_cylinder` | 81-node quarter annulus, PROFILE solver |
| `cooks_membrane` | `HSTAR_Next/cases/cases/cooks_membrane` | classic distorted-mesh patch |
| `mini_3d` | `HSTAR_Next/cases/cases/mini_3d` | 3-D B8 elements |
| `train01_gravdam_static` | `…/train01_gravdam_static` | gravity dam, 2 blocks, water pressure, 2705 nodes |
| `train02_gravdam_seismic` | `…/train02_gravdam_seismic` | `F` dynamic, 500 Newmark steps, earthquake curve |
| `train03a_modal_dry` | `…/train03a_modal_dry` | `E` modal, 5 modes |
| `train05_slope_stability` | `…/train05_slope_stability` | `MCJOINT` thin layer, `kstab` limit state |
| `train07_thermal_transient` | `…/train07_thermal_transient` | transient thermal, Crank-Nicolson |
| `train12_seepage_steady` | `…/train12_seepage_steady` | steady seepage, W-DOF |

Each tool **copies the whole template directory**, then edits named values in place. No tool
writes an HSTAR input file from an empty string.

---

## 6. Traceability to Phase 1b capabilities

| Capability (docs/capabilities.md) | Preparation category above | Tool |
|---|---|---|
| 1, 4, 5, 25, 32 | 3.1, 3.7, 3.8 | `build_analysis_control.py` |
| 2, 3, 21, 28, 29 | 3.1, 3.6, 3.11 | `build_dynamic_seismic.py` |
| 6, 7 | 3.5, 3.10 | `build_thermal.py` |
| 8, 9 | 3.1, 3.5 | `build_seepage.py` |
| 10 | 3.1, 3.5 | `build_contact_joints.py` |
| 11, 12, 13 | 3.1, 3.12 | `build_stability_analysis.py` |
| 14, 15, 27 | 3.1, 3.5 | `build_reliability.py` |
| 16 | 3.14 | `build_back_analysis.py` |
| 17, 18, 19 | 3.5 | `build_material_file.py` |
| 19 (mesh side) | 3.2, 3.3 | `build_mesh_files.py` |
| 20 | 3.15 | `build_reinforcement.py` |
| 22, 33 | 3.6 | `build_loads.py` |
| 23 | 3.9 | `build_staged_construction.py` |
| 30 | 2 | `run_hstar.py` |
| 31 | 3.13 | `parse_outputs.py` |
| 34 | — | `validate_results.py` |
| 24, 26 | two `.glb` switches + files produced by a prior HSTAR run — nothing to derive | `docs/s9_advanced_capabilities.md` |
