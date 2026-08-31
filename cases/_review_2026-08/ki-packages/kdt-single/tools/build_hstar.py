#!/usr/bin/env python3
"""
build_hstar.py -- Stage s0_build: compile the HSTAR Fortran solver on Linux.

HSTAR ships as a Visual Studio / Intel Fortran (`hstar.vfproj`) project targeting
Windows.  There is no Makefile and no CMakeLists.  This tool reproduces the
Windows link line on Linux with `ifx` + oneMKL, in the dependency order the
`.vfproj` implies (module files must exist before the units that `use` them).

Two Windows-only dependencies are handled explicitly:

  * gidpost  -- the GiD post-processing C library (`gidpost.lib`).  Only the
    binary-mode writers (`OUT_GID_BIN_MESH`, `GiD_Begin*Result`) call into it.
    A C stub providing the exported symbols satisfies the linker; ASCII output
    (`outplot='GIDR'`/`'GIDA'`, the default) never enters those code paths.
  * HDF5 / zlib -- referenced only by the Windows x64 link line; the Fortran
    sources contain no HDF5 calls, so they are dropped on Linux.

validate -> process -> validate:
  pre : compiler present, MKL present, all 17 sources present
  post: ELF executable produced, `ldd` fully resolved, binary starts

Usage
-----
  python3 build_hstar.py --source_dir <dir with Fem.f90> [--out <exe path>]
  python3 build_hstar.py --check-only
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

# Compilation order.  Derived from the `use` graph, NOT alphabetical:
# Vartype defines the kind parameters everything else needs; Fem.f90 (the
# PROGRAM unit) must be last.
SRCS = [
    "Vartype.f90",
    "Array.f90",
    "Elements.f90",
    "gidpost.F90",
    "vsl_gauss_module.f90",
    "Global.f90",
    "Material.f90",
    "meshfine.f90",
    "Load.f90",
    "Prescrib.f90",
    "Solver.f90",
    "Output.f90",
    "Temper.f90",
    "Stiff.f90",
    "Residu.f90",
    "Level.f90",
    "Fem.f90",
]

DEFAULT_IFX_CANDIDATES = [
    "/opt/intel/oneapi/compiler/2025.3/bin/ifx",
    "/opt/intel/oneapi/compiler/latest/bin/ifx",
    "/opt/intel/oneapi/compiler/latest/linux/bin/ifx",
]
DEFAULT_MKL_ROOT = "/opt/intel/oneapi/mkl/latest"
DEFAULT_STUB = "/home/huijun/HSTAR_Next/_archive/src/gidpost_stub.c"


def find_ifx(explicit=None):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    for c in DEFAULT_IFX_CANDIDATES:
        if os.path.exists(c):
            return c
    return shutil.which("ifx")


def find_mkl(explicit=None):
    root = explicit or DEFAULT_MKL_ROOT
    inc = os.path.join(root, "include")
    for libdir in (os.path.join(root, "lib", "intel64"), os.path.join(root, "lib")):
        if os.path.exists(os.path.join(libdir, "libmkl_core.so")) or glob.glob(
            os.path.join(libdir, "libmkl_core.so*")
        ):
            return inc, libdir
    return inc, None


def validate_inputs(source_dir, ifx, mkl_inc, mkl_lib, stub):
    problems = []
    if not ifx:
        problems.append(
            "Intel ifx not found. HSTAR uses Intel-specific extensions "
            "(FORM='BINARY', buffered=/blocksize= OPEN specifiers, MKL_RCI, "
            "VSL) that gfortran rejects -- see triplet dt_002."
        )
    if not mkl_lib:
        problems.append("oneMKL runtime libraries not found under %s" % mkl_inc)
    if not os.path.isdir(source_dir):
        problems.append("source_dir does not exist: %s" % source_dir)
    else:
        for s in SRCS:
            if not os.path.exists(os.path.join(source_dir, s)):
                problems.append("missing source file: %s" % s)
    if not os.path.exists(stub):
        problems.append(
            "gidpost C stub not found at %s -- needed to resolve GiD_* symbols "
            "(see triplet dt_003)" % stub
        )
    return problems


def validate_outputs(exe):
    problems = []
    if not os.path.exists(exe):
        return ["executable was not produced: %s" % exe]
    if not os.access(exe, os.X_OK):
        problems.append("executable is not executable: %s" % exe)
    head = open(exe, "rb").read(4)
    if head != b"\x7fELF":
        problems.append("not an ELF binary (got %r)" % head)
    try:
        ldd = subprocess.run(["ldd", exe], capture_output=True, text=True, timeout=60)
        for line in ldd.stdout.splitlines():
            if "not found" in line:
                problems.append("unresolved shared library: %s" % line.strip())
    except Exception as exc:  # pragma: no cover
        problems.append("ldd failed: %s" % exc)
    return problems


def build(source_dir, out_exe, ifx, mkl_inc, mkl_lib, stub, build_dir, opt="-O2"):
    os.makedirs(build_dir, exist_ok=True)
    objs = []

    print("[1/3] gidpost C stub")
    stub_o = os.path.join(build_dir, "gidpost_stub.o")
    subprocess.run(["gcc", "-c", stub, "-o", stub_o], check=True)

    print("[2/3] Fortran sources (%d units)" % len(SRCS))
    for f in SRCS:
        obj = os.path.join(build_dir, os.path.splitext(f)[0] + ".o")
        cmd = [ifx, "-c", opt, "-module", build_dir, "-I", build_dir,
               "-I", mkl_inc, os.path.join(source_dir, f), "-o", obj]
        print("      %-24s" % f, end="", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(" FAILED")
            sys.stderr.write(r.stdout + r.stderr)
            raise SystemExit("compilation of %s failed" % f)
        print(" ok")
        objs.append(obj)

    print("[3/3] link -> %s" % out_exe)
    os.makedirs(os.path.dirname(out_exe) or ".", exist_ok=True)
    cmd = ([ifx, opt, "-qopenmp"] + objs + [stub_o, "-o", out_exe,
           "-L", mkl_lib, "-lmkl_intel_lp64", "-lmkl_intel_thread",
           "-lmkl_core", "-liomp5", "-lpthread", "-lm", "-ldl"])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("link failed")
    os.chmod(out_exe, 0o755)
    return out_exe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source_dir", default=os.environ.get("HSTAR_SRC", ""))
    ap.add_argument("--out", default="")
    ap.add_argument("--build_dir", default="")
    ap.add_argument("--ifx", default="")
    ap.add_argument("--mkl_root", default="")
    ap.add_argument("--stub", default=DEFAULT_STUB)
    ap.add_argument("--opt", default="-O2")
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()

    ifx = find_ifx(a.ifx or None)
    mkl_inc, mkl_lib = find_mkl(a.mkl_root or None)
    src = a.source_dir or "."
    out = a.out or os.path.join(src, "x64", "Release", "hstar")
    bdir = a.build_dir or os.path.join(os.path.dirname(out) or ".", "_build")

    problems = validate_inputs(src, ifx, mkl_inc, mkl_lib, a.stub)
    if a.check_only:
        for p in problems:
            print("BLOCKER:", p)
        print("ifx      :", ifx)
        print("mkl_inc  :", mkl_inc)
        print("mkl_lib  :", mkl_lib)
        return 1 if problems else 0
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        return 1

    build(src, out, ifx, mkl_inc, mkl_lib, a.stub, bdir, a.opt)
    problems = validate_outputs(out)
    for p in problems:
        print("POST-CHECK FAILED:", p)
    if problems:
        return 1
    print("BUILD OK:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
