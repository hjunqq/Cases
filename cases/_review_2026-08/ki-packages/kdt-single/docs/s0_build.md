# Stage s0 — Build the HSTAR solver

## Purpose
Produce a working `hstar` executable. HSTAR ships as a Visual Studio / Intel
Fortran project (`hstar.vfproj`) targeting Windows; there is no Makefile, no
CMakeLists, and no configure script. This stage reproduces the Windows link
line on Linux.

## Inputs
- The 17 Fortran compilation units: `Vartype.f90 Array.f90 Elements.f90
  gidpost.F90 vsl_gauss_module.f90 Global.f90 Material.f90 meshfine.f90
  Load.f90 Prescrib.f90 Solver.f90 Output.f90 Temper.f90 Stiff.f90 Residu.f90
  Level.f90 Fem.f90`
- Intel `ifx` (or `ifort`) — **not** gfortran
- Intel oneMKL (PARDISO, RCI trust region, VSL random numbers)
- `gidpost_stub.c`, a C stub exporting the `GiD_*` symbols

Files present in the source tree but **not** part of the build: `OPT.F90`,
`ex_nlsqp_f.f`, `vdrnggaussianmv_*.f`, the `*.inc` MKL example includes, and
the whole `vtune_hotspot_*` profiling tree. `hstar.vfproj` lists exactly the 17
units above.

## Outputs
- `hstar` — ELF 64-bit executable, ~120 MB with debug info, ~15 MB optimised
- `_build/*.mod`, `_build/*.o`

## Procedure
```bash
python3 tools/build_hstar.py --check-only          # what is missing?
python3 tools/build_hstar.py \
    --source_dir /path/to/HSTAR \
    --out /path/to/bin/hstar
```
Compilation order matters: it is the `use` graph, not alphabetical. `Vartype`
defines the kind parameters (`ink`, `irk`) every other unit needs, and `Fem.f90`
holds the `PROGRAM` unit and must be last.

Two Windows-only dependencies are handled explicitly.

*gidpost* — the GiD post-processing C library, shipped only as
`lib64/gidpost.lib`. Only the BINARY output path calls into it
(`OUT_GID_BIN_MESH`, `GiD_Begin*Result`, reached when `outplot='GIDB'` or
`'GIDL'`). The ASCII writers used by `outplot='GIDR'`/`'GIDA'` — the default in
every shipped case — emit `.flavia.res` with plain Fortran `write` statements.
A C stub therefore satisfies the linker without changing any result.

*HDF5 / zlib* — referenced by the Windows x64 link line only. No Fortran source
in the tree calls an HDF5 routine, so both are dropped.

## Verification
```bash
file bin/hstar          # ELF 64-bit LSB executable
ldd  bin/hstar          # every line resolved, no "not found"
cd templates/static_2d && /path/to/bin/hstar && echo $?     # 0
```
`build_hstar.py` runs all three as post-checks. The strongest check is the
regression in stage s5: run the shipped `lame_cylinder` case and compare
`1.flavia.res` against the stored result. On this host the Linux build
reproduced it bit-for-bit (`DISPLACEMENT` node 1 = `0.50245203E-05` m).

## Traps
- gfortran cannot compile this code — `FORM='BINARY'`, `buffered=`,
  `blocksize=` are Intel extensions and `MKL_RCI`/`MKL_VSL` are MKL modules.
  Triplet `dt_002`.
- Missing `GiD_*` symbols at link time: triplet `dt_003`. Do not "fix" it by
  switching `outplot` to `GIDB` — that is the one setting that actually calls
  the stub, and it produces an empty result file (`dt_015`).
- `include 'mkl_rci.f90'` at the very top of `Fem.f90`, before `PROGRAM`,
  needs `-I $MKLROOT/include`.
- The debug configuration in the `.vfproj` sets `BoundsCheck=true`. Building
  `-O0 -check all` is worth doing once for a new case class; it is far too slow
  for production.

## Example
Verified on this host, 2026-08-26:

```
$ python3 tools/build_hstar.py --source_dir work/source --out work/bin/hstar
[1/3] gidpost C stub
[2/3] Fortran sources (17 units)
      Vartype.f90              ok
      ...
      Fem.f90                  ok
[3/3] link -> work/bin/hstar
BUILD OK: work/bin/hstar
```
Compiler: `ifx` 2025.3; MKL 2026.0; total build time ~2 minutes.
