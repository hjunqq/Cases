# HSTAR — Capability Inventory (KDT Phase 1b)

Source read: `/tmp/claude-1000/kdt-work/HSTAR/source` (= `hstarYLOrig/HSTAR`, 31 Fortran files,
~73 000 lines). Official in-repo documentation read:

- `hstarYLOrig/CLAUDE.md` (program overview, module map, build requirements)
- `hstarYLOrig/docs/analysis/program-flow.md` (598 lines — full branch map, input-file table)
- `hstarYLOrig/docs/analysis/constitutive-models.md` (646 lines — 15 material families)
- `hstarYLOrig/docs/analysis/structural-elements.md` (376 lines — 26 element indices)
- `hstarYLOrig/docs/analysis/contact-mechanics.md` (503 lines — `gap_group` structure)
- `hstarYLOrig/docs/analysis/back-analysis.md`, `rigid-body-reliability.md`
- `hstarYLOrig/HSTAR/memory_leak_check.md`, `sanitizer_guide.md`
- `HSTAR_Next/cases/README.md` (23-case regression matrix + case catalogue)
- `HSTAR_Next/_archive/docs/cases/analytical_verification.md` (11 analytic benchmarks)

> **NOTE on `docs/design/architecture-design-part2.md`**: that document specifies the *proposed*
> HSTAR-Next YAML/`*.msh`/`*.mat` formats for a future rewrite. **It does NOT describe the format
> the binary in this KI reads.** The legacy free-format `probn.*` files documented in
> `docs/s1_case_layout_and_control.md` … `docs/s5_analysis_control_and_solvers.md` are
> authoritative, verified by reading `Global.f90`, `Material.f90`, `Load.f90`, `Prescrib.f90` and
> the shipped example cases.

---

## Model identity

| Property | Value |
|---|---|
| Full name | HSTAR — Hydraulic-STRuctures Analysis (FEM90 kernel) |
| Original authors | M. Pastor, Tonchun Li, P. Mira (May 1997); continuously extended by the IWHR / Tsinghua group through 2025 |
| Language | Fortran 90 (fixed global-state architecture, `global_var` module) |
| Domain | Structural / geotechnical mechanics of hydraulic structures (concrete & rockfill dams, ship locks, slopes, tunnels, RC members) |
| Build | Intel Fortran (`ifort`/`ifx`) + Intel MKL (PARDISO, VSL) + gidpost; Windows `.vfproj`, Linux `build_linux.sh` |
| Execution | Single console binary, **no CLI arguments**. Reads a file literally named `inp` from the current working directory; `inp` names the case base name `probn`; every other file is `probn.<ext>` in the same directory |

---

## Capability list

Every capability below is switched from `probn.glb` (and/or an auxiliary file). "Tool" names the
KI tool in `tools/` that configures or parses it.

| # | Capability | Control | Tool |
|---|---|---|---|
| 1 | **[PRIMARY] Quasi-static stress/displacement analysis** — Newton-Raphson, load blocks, increments/steps | `type_problem='Q'` → `static_U` | `build_analysis_control.py`, `run_hstar.py`, `parse_outputs.py` |
| 2 | **Implicit dynamic analysis (Newmark)** — velocity/acceleration fields, Rayleigh damping | `type_problem='F'`/`'D'` → `time_dependent`; `beeta1,beeta2,theta1` | `build_dynamic_seismic.py` |
| 3 | **Explicit dynamic (central difference)** — lumped mass, no linear solve | `type_solver='EXPLICIT'` → `explicit` | `build_dynamic_seismic.py` |
| 4 | **Modal / eigenfrequency analysis** | `type_problem='E'` → `response_spectrum` (modal extraction + response spectrum) | `build_analysis_control.py`, `parse_outputs.py` |
| 5 | **Steady-state frequency-domain analysis** (complex stiffness) | `type_problem='W'` → `frequency_analysis` | `build_analysis_control.py` |
| 6 | **Thermal analysis** — steady and transient (Crank-Nicolson / θ-method), conduction + convection edges + heat source curves | `ntsmat`,`nthmat`,`kstat` in `.glb`; `probn.tem`; `HEAT` material | `build_thermal.py` |
| 7 | **Pipe-cooling of mass concrete** (embedded cooling-water pipes, Zhu Bofang analytic-superposition `algo_pipe=3`) | `HEAT.pipe_cooling`, `ECWPIPE`, `nwcpipe`, `probn.tem` | `build_thermal.py` |
| 8 | **Seepage / groundwater flow** — steady (Laplace) and transient (θ-method), free-surface nodes | `nflow`, `nfreeflownode`, W degree-of-freedom, `probn.aqu` | `build_seepage.py` |
| 9 | **Coupled consolidation** — U-P (Biot) and U-Pw | `mdofn=7`+`lmdofn(7)/=0` → `static_U_P`; `mdofn=8` → `static_U_Pw`; coupled element indices 11–19, 24 | `build_seepage.py`, `build_analysis_control.py` |
| 10 | **Contact / joint analysis** — node-pair contact, Goodman joints, thin-layer, open/closed/slip states, contact damage | `ngaps`,`ngapb`,`method_gapi`,`type_solver_ctt`; `probn.ctt`; `GOODMAN` material | `build_contact_joints.py` |
| 11 | **Stability: limit-state safety factor** (known slip surface) | `kstab /= 0` → `safety_factor` | `build_stability_analysis.py` |
| 12 | **Stability: strength reduction method** (unknown slip surface) | `stab_matde` (MAT_DE reduction sequence) | `build_stability_analysis.py` |
| 13 | **Rigid-block sliding stability** (dam/retaining-wall block kinematics, 3(ndimn−1) rigid DOF) | `block_stab=1|2` → `static_rigid_1`, `solve_ctt_rigid` | `build_stability_analysis.py` |
| 14 | **Reliability analysis (FORM)** — Rackwitz-Fiessler, normal/lognormal/extreme-value variables, reliability index β | `relis=1` → `STATIC_U_reli` / `static_rigid_reli` | `build_reliability.py` |
| 15 | **System reliability** — series / parallel / narrow-bound | `sysrelis>0` | `build_reliability.py` |
| 16 | **Parameter back-analysis / inversion** — MKL `DTRNLSP` Levenberg-Marquardt (`balgor=0` FD Jacobian, `balgor=1` analytic sensitivity), trust-region + BFGS dog-leg (`balgor=2`), rigid-displacement decomposition (`Bparameter=3`), nodal-value inversion (`Bparameter=4`), Monte-Carlo verification (`Bparameter=-1,-2`) | `Bparameter`,`balgor`,`nbackf`,`nbackdT`; `probn.btl`, `probn.obs`, `probn.obsc` | `build_back_analysis.py` |
| 17 | **Constitutive model selection** — 15 families: `ELASTIC_ISOTROPIC`, `ELASTIC_FRICTIONLESS`, `ELASTIC_SPRING`, `ELASTIC_EP`, `PLANE_LOWFT`, `CLASSICALEP` (criteria `MC`/`DP`/`VM`/`TC`/`MCC`/`DPC`/`MCJOINT`), `CAMCLAY`, `SoilPZ`/`SandPZ`/`ClayPZ` (Pastor-Zienkiewicz generalized plasticity), `CONCRETE` (Ghrib & Tinawi damage), `DUNCANCHANG` (EV/CR/EB), `GOODMAN`, `STEEL_EP`, `STEEL_SP` | `probn.mat` | `build_material_file.py` |
| 18 | **Creep & time-dependent deformation** — Burgers (`Ek, etak, etam`), power-law, rockfill creep, wetting (collapse) deformation | `icreep`, `CREEP` sub-block, `creep_strain_of_rock_fill`, `wetting_strain_of_rock_fill` | `build_material_file.py` |
| 19 | **Structural elements** — truss/bar `L2`, Euler-Bernoulli beam `b2` (2D 3-DOF / 3D 6-DOF), plate `p4` (membrane+bending+shear), prism `pr6`, thin-film contact layer | element `index` in the `.glb` group block; `GEOMETRY` material (`Aera,J,Iy,Iz`); `probn.bem` | `build_mesh_files.py`, `build_material_file.py` |
| 20 | **Reinforcement / rebar bond** — steel elements embedded in concrete, 5 bond-slip constitutive laws | `nrcsteel`, `ikindks`, `link_concrete_and_steel`, `probn.bar` | `build_reinforcement.py` |
| 21 | **Fluid-structure interaction** — Westergaard added mass (`Icaddmass`), IFS2006 interface, fluid & solid absorbing boundaries, VIE / viscous-elastic artificial boundary, MIF input wave field | `probn.ifs`, `type_ABC`, `Icaddmass`, `swlifs2006`, `nlaymif` | `build_dynamic_seismic.py` |
| 22 | **Uplift pressure** on dam base / joints | `upliftin`, `uplift_ic`, `probn.upf` | `build_loads.py` |
| 23 | **Staged construction / element birth-death** — per-block group activation, per-block material swap, per-block self-weight release | `appear_process`, `matno_process`, `average_appear`, `equvs_process`; `probn.act` | `build_staged_construction.py` |
| 24 | **Level-set method** | `level_set_problem`, `appear_level`, `Level.f90` | documented in `docs/s9_advanced_capabilities.md` |
| 25 | **Adaptive mesh refinement / coarsening** and result transfer | `rmesh`, `meshc`, `ndefault`, `valv1/valv2`, `meshfine.f90` | `build_analysis_control.py` |
| 26 | **Sub-modelling** — export/import boundary state from a coarse global run | `submodel=±1`, `probn.msh`, `probn.resb` | documented in `docs/s9_advanced_capabilities.md` |
| 27 | **Stochastic / random-field generation** — MKL VSL multivariate Gaussian, correlated material fields | `nstoch`, `probn.sto`, `vsl_gauss_module.f90`, `gauss_random.txt` | `build_reliability.py` |
| 28 | **Equivalent linearisation for seismic soil** (γ_max iteration) | `gamamax`, `equvs`, `probn.gamax`, `probn.tel` | `build_dynamic_seismic.py` |
| 29 | **Liquefaction judgement & permanent deformation** | `jliqu`, `ljdp`, `ninistn`, `probn.lqu/.pmt/.stn` | `build_dynamic_seismic.py` |
| 30 | **Restart / checkpointing** — `restart=0` fresh, `=1` resume, `=2` post-process only | `inp` line 2, `probn.rtt` | `run_hstar.py` |
| 31 | **Output** — GiD "flavia" ASCII msh/res, GiD binary post, COSMOS, nodal/element/Gauss-point files, convergence log `.chk`, observation extraction `.obs/.obsc` | `outplot`, `gid_*` flags, `res_*` flags, `probn.opr` | `parse_outputs.py` |
| 32 | **Linear solvers** — Intel MKL PARDISO, skyline PROFILE (LDLᵀ), Jacobi-PCG, PBCG/SSOR-PBCG, explicit (none) | `type_solver`; `probn.sol` (`mtype, ncpu, msglvl`) | `build_analysis_control.py` |
| 33 | **Load types** — gravity/body force, edge & surface pressure, hydrostatic water pressure with reservoir level, point loads, prescribed displacement, temperature load, inertia load, beam/plate loads, earthquake time history, arc-length and displacement control | `probn.loa`, `type_load` (`LOAD`/`LOAD2`/`ARCLENGTH`/`DISCONTROL`) | `build_loads.py` |
| 34 | **Result validation against monitoring data** — nodal observation extraction and metrics | `probn.obs`, `nbackf` | `validate_results.py` |

---

## Traceability: capability → tool

Every tool in `tools/` maps back to one or more rows above; no tool exists without a capability,
and no capability in the table is left without either a tool or an explicit
`docs/s9_advanced_capabilities.md` entry (capabilities 24 and 26, which are configured entirely by
two integer switches in `.glb` plus files produced by a *previous* HSTAR run — there is nothing for
a preparation tool to derive).
