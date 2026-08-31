# Stage s1 — Case setup and the `*.glb` analysis-control file

## Purpose
Create a case directory that HSTAR can open, and set the ~40 analysis-control
records that decide what physics is solved.

## Inputs
- A working template case (`templates/static_2d`, provenance: the
  `lame_cylinder` case, re-run and reproduced bit-for-bit under this KI's build)
- The analysis intent: static / transient / dynamic / modal / thermal / seepage,
  dimensionality, solver, number of run blocks

## Outputs
- A case directory holding the 14 mandatory files (`1.glb 1.cor 1.ele 1.pre
  1.mat 1.loa 1.man 1.opr 1.sol 1.tem 1.ifs 1.nrt 1.ftr inp`)
- `1.glb` with the requested analysis control

## Procedure
```bash
python3 tools/make_case.py   --out case1 --template static_2d
python3 tools/set_analysis.py --case case1 \
        --problem Q --solver PROFILE --load LOAD --nl 5 --dofs 1,2 --nblks 1
```

### Why the file is never authored from scratch
Every HSTAR input is read **list-directed** (`read(unit,*)`), so columns do not
matter — but records do. `read(gunit,*)text` appears about forty times in
`Global.f90`; each consumes one whole record and discards it. Heading records
are therefore **positional**. Deleting one shifts every later read by a record.
Two records in particular look like stray text and are not: `valv1` and
`ndivide` (`Global.f90:690-696`) are mandatory placeholders whose *data* record
only exists when `rmesh/=0` / `meshc/=0`.

`set_analysis.py` therefore locates a heading by substring and replaces one
token of the record below it, preserving the token count.

### The records that matter most

| Heading | Token | Meaning |
|---|---|---|
| `NPOIN ...` | 0-3 | npoin, npoinb, nelem, ndimn |
| | 5 | ngroup |
| | 8 | `outplot` — `GIDR` (ASCII, rewrite) / `GIDA` (ASCII, append) / `GIDB`,`GIDL` (binary, needs real gidpost) |
| | 9 | `kstab` — target limit-state factor; 0.0 disables |
| `NINIT ...` | 0,1 | `ninit`, `kinit` — initial-stress control; `ninit=-1` writes `.ini` |
| | 3 | `nblks` — number of run blocks |
| | 6,7,8 | `outinp` (read `.oip`), `outintr` (read `.oit`), `outintw` (write `.oit`) |
| | 11 | `type_ABC` — `FIX` / `MIF` / `VIE` |
| `TYPE_PROBLEM ...` | 0 | `Q` static, `S` time-dependent, `F` dynamic, `E` response spectrum, `W` modal |
| | 1 | `PROFILE`, `PARDISO`, `JPCG`, `PBCG`, `SSORPBCG`, `EXPLICIT` |
| | 2 | `LOAD`, `ARCLENGTH`, `MAT_DE`, `DISCONTROL` |
| | 3 | `type_nl` — 4 full Newton, 5 modified Newton, 10 field-only |
| | 8,9 | `Bparameter`, `balgor` — inversion dispatch |
| | 10 | `upliftin` |
| `NMASS ...` | 7 | `uwcpl` — 0 flow only, 1 undrained, 2 drained |
| `MDOFN` | block | `mdofn` / `lmdofn(1:mdofn)` / `order_time_mdofn(1:mdofn)` |
| `BEETA1 ...` | | Newmark γ, β and the θ of the θ-method (`0.5 0.25 1.0`) |
| `APPEAR_PROCESS` | nblks × ngroup | element birth-death per run block |
| `gid_u,gid_s,...` | 20 flags | which result blocks reach `.flavia.res` |

Degree-of-freedom numbering is **fixed** by `Global.f90:558-575` and cannot be
remapped: 1 Ux, 2 Uy, 3 Uz, 4-6 rotations, 7 hydrostatic pressure, 8 pore
pressure, 9 air pressure, 10 temperature.

## Verification
```bash
python3 -c "import sys; sys.path.insert(0,'tools'); from hstar_io import GlbFile;
g=GlbFile('case1/1.glb'); print(g.tokens_after('TYPE_PROBLEM'))"
```
`set_analysis.py` re-opens the file after writing and asserts every token it set
came back unchanged. `1.chk` echoes the parsed values at the top of every run —
read it, not the file you wrote.

## Traps
- Deleting or adding a heading record: `dt_004`.
- Anchored edit fails on an older case file that genuinely lacks the record:
  `dt_005`.
- `EXPLICIT` only dispatches under `type_problem='F'` (`Fem.f90:1936`);
  elsewhere it is silently ignored.
- `PROFILE` is a skyline solver: memory grows with bandwidth squared.
  Above ~5·10⁴ DOF use `PARDISO` (`dt_032`).
- `type_load='MAT_DE'` is strength reduction and does nothing useful with
  `kstab=0`.

## Example
Setting up a transient thermal field pass:
```bash
python3 tools/make_case.py --out thermal1
python3 tools/set_analysis.py --case thermal1 \
        --problem S --solver PARDISO --nl 10 --dofs 10 --order-time 1 \
        --outintw 1 --outintr 0
python3 tools/write_thermal.py --case thermal1 --field-pass \
        --diffusivity 0.0864 \
        --convection "where=y>19.99;beta_bar=1.2;curve=2"
```
