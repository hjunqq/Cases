# s0 — Overview, build and environment

## Purpose

Get a working `hstar` executable and understand what kind of program it is, before touching
any input file.

## What HSTAR is

HSTAR is a general finite-element solver for hydraulic structures — concrete gravity and arch
dams, ship locks, sluices, slopes, tunnels, rockfill dams, reinforced-concrete members. It
began as the FEM90 kernel of M. Pastor, Tonchun Li and P. Mira (May 1997) and has been
extended continuously by the Chinese hydraulic-engineering community; the source in this KI
carries change markers up to 2025-07.

It is ~73 000 lines of Fortran 90 in 17 compiled units, driven by a single very large global
state module (`global_var` in `Global.f90`). Everything is switched from integers and
keywords in one control file; there is no CLI, no namelist, no self-describing format.

| Property | Value |
|---|---|
| Language | Fortran 90 (Intel dialect: `FORM='BINARY'`, `pause`, `TIME()`) |
| Numerics | Intel MKL — PARDISO (direct sparse), VSL (random fields), RCI `DTRNLSP` (Levenberg-Marquardt for inversion) |
| Post-processing | GiD "flavia" ASCII + GiD binary via `gidpost`; COSMOS |
| Parallelism | OpenMP inside MKL (`ncpu` in `<probn>.sol`) |
| Entry point | `PROGRAM FEM90`, `Fem.f90:4` |

## Inputs

- The source tree (`Fem.f90`, `Global.f90`, … 17 units + `gidpost.F90`).
- Intel oneAPI: `ifx` (or `ifort`) and MKL. Verified present on this host at
  `/opt/intel/oneapi/compiler/2025.3/bin/ifx` (ifx 2025.3.3) and
  `/opt/intel/oneapi/mkl/latest`.
- A C stub for the gidpost library when the real `libgidpost` is not available
  (`_archive/src/gidpost_stub.c`).

## Outputs

- `hstar` — an ELF-64 executable, ~7.8 MB.

## Procedure

```bash
export PATH=/opt/intel/oneapi/compiler/2025.3/bin:$PATH
MKL_INC=/opt/intel/oneapi/mkl/latest/include
MKL_LIB=/opt/intel/oneapi/mkl/latest/lib/intel64
BUILD=/tmp/hstar_build; SRC=<the HSTAR source dir>
mkdir -p $BUILD
gcc -c /home/huijun/HSTAR_Next/_archive/src/gidpost_stub.c -o $BUILD/gidpost_stub.o

# STRICT dependency order -- module files must exist before their users compile
for f in Vartype.f90 Array.f90 Elements.f90 gidpost.F90 vsl_gauss_module.f90 \
         Global.f90 Material.f90 meshfine.f90 Load.f90 Prescrib.f90 Solver.f90 \
         Output.f90 Temper.f90 Stiff.f90 Residu.f90 Level.f90 Fem.f90; do
  ifx -c -O2 -module $BUILD -I $BUILD -I $MKL_INC $SRC/$f -o $BUILD/${f%.*}.o
done

ifx -O2 -qopenmp $BUILD/*.o -o $BUILD/hstar \
    -L$MKL_LIB -lmkl_intel_lp64 -lmkl_intel_thread -lmkl_core -liomp5 -lpthread -lm -ldl
```

The KI ships this as `/tmp/claude-1000/kdt-work/HSTAR/build_hstar.sh`.

## Verification

```bash
file $BUILD/hstar                 # ELF 64-bit LSB executable
python3 tools/run_hstar.py --template column_selfweight --outdir /tmp/smoke
# expect {"status": "ok", "returncode": 0, ...} and a non-empty 1.flavia.res
python3 tools/parse_outputs.py --dir /tmp/smoke
# expect DISPLACEMENT max_abs ~4.24e-07 m and STRESS max_abs 11772 Pa
```

`preflight_check.py` in the KI root runs the binary-existence, ELF-type, MKL, template and
import checks and prints a machine-readable `PREFLIGHT_REPORT=` line.

## Traps

- **`gfortran` cannot build HSTAR.** The code uses `FORM='BINARY'` (Intel extension, not
  `access='stream'`), `pause`, and the Intel portability `TIME(character)`. gfortran is not
  installed on this host in any case.
- **Compilation order is not optional.** `Global.f90` defines `global_var`, which every
  later unit `use`s. Compiling alphabetically fails with "module not found".
- **`gidpost.lib` / `libhdf5` are Windows binaries** in the source tree (`lib64/*.lib`).
  On Linux, link against the C stub instead. The stub only matters when `outplot='GIDL'`
  (GiD binary post); every shipped case uses `'GIDR'`, the ASCII writer, which is pure
  Fortran inside `Output.f90`.
- **`OPT.F90` and the `.f`/`.inc` files are NOT in the build.** They are not listed in the
  Visual Studio project either. `include 'mkl_rci.f90'` at the very top of `Fem.f90`
  supplies the MKL RCI interfaces and is resolved by `-I $MKL_INC`.
- **Windows path leftovers.** The shipped `inp` file in the source root points at
  `D:\Projects\...` and `G:\BB\...`. It is a scratch file, not a template; always start
  from a case directory under the case library.

## Example

```bash
$ bash build_hstar.sh
  Vartype.f90 ... OK
  ...
  Fem.f90 ... OK
BUILT: /tmp/claude-1000/kdt-work/HSTAR/build/hstar

$ HSTAR_BIN=/tmp/claude-1000/kdt-work/HSTAR/build/hstar \
  python3 tools/run_hstar.py --template column_selfweight --outdir /tmp/smoke
{"status": "ok", "returncode": 0, "binary_kind": "ELF", ...}
```
