# Stage s8 — Contact, joints, staged construction, reinforcement and dynamics

## Purpose
The capabilities that make HSTAR a dam code rather than a generic FEM solver:
joints that open, structures that are built in lifts, reinforcement that slips,
and reservoirs that add mass and absorb waves.

## Inputs
Depends on the capability; each sub-section lists its own.

## Outputs
`*.ctr` (contact gaps), `*.gdm` (Goodman elements), `*.ojw` (joint stresses),
`*.bar` (bar forces and slip), `*.ctt` (contact state, binary), plus the usual
displacement and stress blocks.

---

## Contact and joints

Three mechanisms, and choosing the wrong one is the usual reason a joint never
opens.

1. **Gap / point-to-point contact** (`ngaps` block of `*.glb`,
   `Global.f90:3328`). Node pairs on facing surfaces, with a closed/open penalty
   pair `kgroup0`/`kgroup1`, tensile strength `ft0`, friction `frict0` and
   cohesion `cohes0`. Iterated in an outer state loop (`miter_bt`, `tor_bt`,
   `miter_state`) with its own solver `type_solver_ctt`.
2. **Goodman joint element** (`gaps%goodman=1`, material `GOODMAN`/`JANBU`).
   Zero-thickness element with stress-dependent normal and shear stiffness;
   `elcod_local` in the group stanza sets its notional thickness.
3. **Thin-layer element** (`gaps%thin_layer=1`, material `CLASSICALEP` with
   criteria `MCJOINT`). A thin continuum band carrying a joint yield surface —
   the standard choice for slope stability on a known slip surface.

Block-pair contact (`ngapb`) links two whole element groups; `block_stab` and
the `.gdm` output refer to it.

`*.glb` contact header, 14 fields:
```
ngaps ngapb ctt_pe miter_bt torbt iblkbt nonsbt xlwsol method_gapi
miter_state type_solver_ctt restart_ctt damp_ctt istatec
```

```bash
python3 tools/write_contact.py --case dam1 \
  --gap "groups=2;kind=goodman;kn=1e11;ks=1e10;ft=0;phi=35;c=0" \
  --solver PARDISO --miter-state 20
python3 tools/write_contact.py --case dam1 --clear      # back to ngaps=0
```

Stiffness guidance: normal stiffness ≈ 10–100× the adjacent rock modulus per
metre. Too soft lets the surfaces interpenetrate; too stiff destroys the
conditioning of the skyline factorisation. `ks ≤ kn` always.

---

## Staged construction and excavation

- An **element group** is a partition of the mesh; every element belongs to one.
- A **run block** (`nblks`) is a complete pass in which each group is active or
  not.
- `APPEAR_PROCESS(1:ngroup, 1:nblks)` — one record per block, `ngroup` integers.
- `MATNO_PROCESS(1:ngroup, 1:nblks)` lets a group change material between
  blocks (fresh vs matured concrete).
- `uinitial(1:nblks)` — 1 clears the previous block's displacement state, 0
  inherits it.
- `.pre`, `.loa` and `.man` are each repeated **once per block**, in block order.

Dam construction is rows that grow (`1*1 29*0`, `2*1 28*0`, …); excavation is the
same rows read backwards.

```bash
python3 tools/write_stages.py --case dam1 --nblks 3 \
  --appear "1,0,0|1,1,0|1,1,1" --matno "1,2,2|1,2,2|1,2,2" \
  --uinitial 0,0,0 --replicate
```
`--replicate` expands single-block `.pre`/`.loa`/`.man` to `nblks` copies and
then verifies the counts against `.glb`.

---

## Reinforcement and bond slip

Reinforcement is `steel` elements (library index 25) **linked** to the
surrounding concrete at run time by `link_concrete_and_steel` (`Fem.f90:188`).
The link, not the mesh, carries the bond law.

```
' nrcsteel' / nrcsteel
per link group:
  listgroup_c listgroup_s nline_g_sc diameter_s e ft ikindsc err_ctl mxter
  nel_steel / <element list>
```
`ikindsc` selects the slip law (0 perfect bond, 1 linear, 2 bilinear,
3 CEB-FIP, 4 exponential softening, 5 user table). Separately, `ikindks` in the
`ftcrack,coefMpa,ikindks,…` record decides whether `steel_spring_parameter` is
called at all (`Fem.f90:1860`).

```bash
python3 tools/write_reinforcement.py --case rc1 --ikindks 5 --ftcrack 2.5e6 \
  --link "concrete=1;steel=2;diameter=0.025;E=2.0e11;ft=4.0e8;bond=3"
```

---

## Reservoir interaction and absorbing boundaries

| model | switch | what it is |
|---|---|---|
| Westergaard added mass | `Icaddmass=1`, `toth` = depth | reservoir replaced by nodal mass on the wet face; lowers every natural frequency |
| Compressible reservoir | `nifsgroup>0` + `p4` pressure elements (index 22) | water is meshed and coupled; `alfa_p4` is the bottom reflection coefficient, `stiff_p4` the fluid penalty |
| Absorbing / transmitting (VIE) | `nabsfgroup`/`nabssgroup`, `type_ABC='VIE'` | viscous dashpot boundary sized from the far-field impedance ρc |

```bash
python3 tools/write_ifs.py --case dam1 --added-mass --water-depth 100
python3 tools/write_ifs.py --case dam1 --absorbing "groups=2;E=1e10;nu=0.25;rho=2600"
python3 tools/write_ifs.py --case dam1 --clear
```

---

## Verification
- `write_contact.py` cross-checks the `.mat` for a `GOODMAN` material (or an
  `MCJOINT` criterion for a thin layer) and range-checks `kn`, `ks`, `phi`.
- `write_stages.py` checks that every block activates at least one group, that
  every referenced material exists, and that `.pre`/`.loa`/`.man` block counts
  equal `nblks`.
- `write_reinforcement.py` checks the steel group's element index is 25/20/1 and
  blocks a slip law with `ikindks=0`.
- `write_ifs.py` requires a wave-type `type_problem` for added mass and
  absorbing boundaries and range-checks the far-field density.
- After a dynamic run with an absorbing boundary, compare early and late |u|max:
  a boundary that reflects shows no decay.

## Traps
- `GOODMAN` joint with no `GOODMAN` material — never opens (`dt_018`).
- Bond law set but `ikindks=0` — slip is identically zero (`dt_020`).
- Absorbing boundary mistuned by a wrong far-field density — reflects silently
  (`dt_019`).
- Raising `nblks` without the per-block file repeats — EOF at the start of
  block 2 (`dt_030`).
- A group switched off in `APPEAR_PROCESS` contributes neither stiffness nor
  weight; the run converges on a structure that is not the one intended
  (`dt_013`).
- Added mass is a **mass-matrix** effect: it does nothing in a static run.

## Example
Three-lift gravity dam on a foundation, with a Goodman base joint:
```bash
python3 tools/write_stages.py --case dam1 --nblks 3 \
    --appear "1,0,0,0|1,1,1,0|1,1,1,1" --matno "1,2,2,2|1,2,2,2|1,2,2,2" \
    --uinitial 1,0,0 --replicate
python3 tools/write_contact.py --case dam1 \
    --gap "groups=4;kind=goodman;kn=5e10;ks=5e9;ft=0;phi=40;c=1e5"
```
