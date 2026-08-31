#!/usr/bin/env python3
"""Preflight check — HSTAR.

Verifies, BEFORE any model setup, that everything an HSTAR run needs is actually present:
the compiled binary (and that it is a native ELF that starts), the Intel toolchain that
built it, the Python imports the KI tools use, the shipped template case library, and the
KI's own diagnostic corpus.

Run:  python preflight_check.py
Exit: 0 = model ready, non-zero = blockers found (each printed with a fix).

Ends with a single machine-readable line:  PREFLIGHT_REPORT={...}
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

MODEL_ID = "HSTAR"

BINARY_CANDIDATES = [
    os.environ.get("HSTAR_BIN", ""),
    "/tmp/claude-1000/kdt-work/HSTAR/build/hstar",
    "/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR/x64/Release/hstar",
]
CASES_DIR = os.environ.get("HSTAR_CASES_DIR", "/home/huijun/HSTAR_Next/cases/cases")
SMOKE_TEMPLATE = "test_thermal_expansion"      # the confined self-weight column
KI_DIR = os.path.dirname(os.path.abspath(__file__))

checks = []


def add(kind, subject, critical, status, fix=None, detail=None):
    c = {"kind": kind, "subject": subject, "critical": bool(critical), "status": status}
    if fix:
        c["fix"] = fix
    if detail:
        c["detail"] = detail
    checks.append(c)
    mark = {"pass": "OK  ", "fail": "FAIL", "warn": "WARN"}.get(status, status)
    print(f"  {mark}  [{kind}] {subject}" + (f"  -- {detail}" if detail else ""))
    if status == "fail" and fix:
        print(f"          fix: {fix}")
    return status == "pass"


def find_binary():
    for cand in BINARY_CANDIDATES:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return os.path.realpath(cand)
    found = shutil.which("hstar")
    return os.path.realpath(found) if found else None


def elf_type(path):
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic == b"\x7fELF":
        return "ELF"
    if magic[:2] == b"MZ":
        return "PE32"
    return "unknown"


def main():
    print("=" * 66)
    print(f"  PREFLIGHT CHECK: {MODEL_ID}")
    print("=" * 66)
    print()

    # ---- 1. the binary (CRITICAL) ------------------------------------------
    exe = find_binary()
    if not exe:
        add("binary", "hstar executable", True, "fail",
            fix="Build it: bash /tmp/claude-1000/kdt-work/HSTAR/build_hstar.sh "
                "(needs Intel ifx + MKL from /opt/intel/oneapi). See "
                "docs/s0_overview_and_build.md and triplet dt_002. Or set $HSTAR_BIN.")
    else:
        kind = elf_type(exe)
        if kind != "ELF":
            add("binary", exe, True, "fail",
                fix=f"{exe} is {kind}, not a native ELF. The Windows hstar.exe cannot run "
                    f"here and wine is not installed. Build the Linux binary with "
                    f"/tmp/claude-1000/kdt-work/HSTAR/build_hstar.sh.",
                detail=kind)
        else:
            add("binary", exe, True, "pass", detail="ELF 64-bit, executable")

    # ---- 2. the binary actually STARTS (CRITICAL) --------------------------
    # HSTAR opens a file literally named `inp` in the CWD. Run it in an empty
    # temp dir: it must start, print its banner and fail on the missing input --
    # that proves the dynamic loader resolved libmkl/libiomp5, which is the real
    # failure mode on a machine without the Intel runtime.
    if exe and elf_type(exe) == "ELF":
        with tempfile.TemporaryDirectory(prefix="hstar_pf_") as td:
            try:
                p = subprocess.run([exe], cwd=td, input="\n", capture_output=True,
                                   text=True, timeout=60)
                out = (p.stdout or "") + (p.stderr or "")
            except subprocess.TimeoutExpired:
                out = "__TIMEOUT__"
            except OSError as e:
                out = f"__OSERROR__ {e}"
            if "__TIMEOUT__" in out:
                add("run", exe, True, "fail",
                    fix="The binary hung with no input. Check that it is the console build "
                        "and not waiting on a `pause` (triplet dt_001).",
                    detail="timeout after 60 s")
            elif "error while loading shared libraries" in out or "__OSERROR__" in out:
                lib = out.strip().splitlines()[0][:120] if out.strip() else "?"
                add("run", exe, True, "fail",
                    fix="Intel runtime not on the loader path. "
                        "source /opt/intel/oneapi/setvars.sh, or set LD_LIBRARY_PATH to "
                        "/opt/intel/oneapi/mkl/latest/lib/intel64 and "
                        "/opt/intel/oneapi/compiler/latest/lib.",
                    detail=lib)
            else:
                # Any Fortran-level complaint about the missing `inp` proves it started.
                started = ("forrtl" in out or "time:" in out or "Input the problem name"
                           in out or "severe" in out)
                if started:
                    add("run", exe, True, "pass",
                        detail="starts and reaches its own input read (no `inp` in the "
                               "temp dir, as expected)")
                else:
                    add("run", exe, True, "fail",
                        fix="The binary produced no recognisable output when started with "
                            "no input. Rebuild with build_hstar.sh and re-run this check.",
                        detail=(out.strip().splitlines() or ["(no output)"])[-1][:110])

    # ---- 3. Intel toolchain (non-critical: only needed to REBUILD) ---------
    ifx = shutil.which("ifx") or next(
        (p for p in ("/opt/intel/oneapi/compiler/2025.3/bin/ifx",
                     "/opt/intel/oneapi/compiler/latest/bin/ifx") if os.path.isfile(p)),
        None)
    if ifx:
        add("dependency", ifx, False, "pass", detail="Intel Fortran available for rebuilds")
    else:
        add("dependency", "ifx (Intel Fortran)", False, "warn",
            fix="Install Intel oneAPI if you need to rebuild. gfortran CANNOT compile this "
                "source (FORM='BINARY', pause, TIME()) -- triplet dt_002.",
            detail="not found; the existing binary can still be run")
    mkl = "/opt/intel/oneapi/mkl/latest/lib/intel64"
    add("dependency", mkl, False, "pass" if os.path.isdir(mkl) else "warn",
        fix=None if os.path.isdir(mkl) else
            "MKL runtime directory missing. If the binary was statically linked this is "
            "harmless; if it fails to load, install oneAPI MKL.")

    # ---- 4. Python imports the KI tools need ------------------------------
    for mod, crit in (("yaml", True), ("json", True)):
        try:
            __import__(mod)
            add("import", mod, crit, "pass")
        except ImportError as e:
            add("import", mod, crit, "fail",
                fix=f"pip install {'pyyaml' if mod == 'yaml' else mod}", detail=str(e)[:80])
    try:
        __import__("ki_tools_common.metrics")
        add("import", "ki_tools_common.metrics", False, "pass")
    except Exception:
        local = os.path.join(KI_DIR, "tools", "_local_metrics.py")
        add("import", "ki_tools_common.metrics", False,
            "pass" if os.path.isfile(local) else "fail",
            fix=None if os.path.isfile(local) else
                "tools/_local_metrics.py is missing and ki_tools_common is not importable; "
                "restore the fallback (triplet dt_033).",
            detail="not importable on this host; the KI falls back to tools/_local_metrics.py")

    # ---- 5. the template case library (CRITICAL) --------------------------
    smoke = os.path.join(CASES_DIR, SMOKE_TEMPLATE)
    if os.path.isdir(CASES_DIR) and os.path.isfile(os.path.join(smoke, "inp")):
        n = len([d for d in os.listdir(CASES_DIR)
                 if os.path.isfile(os.path.join(CASES_DIR, d, "inp"))])
        add("data", CASES_DIR, True, "pass", detail=f"{n} runnable case directories")
    else:
        add("data", CASES_DIR, True, "fail",
            fix="The KI is COPY-FIRST: every tool starts from a shipped case. Set "
                "$HSTAR_CASES_DIR to the directory holding the legacy HSTAR cases "
                "(each contains an `inp` file). Without it no case can be built at all.",
            detail="missing or contains no case with an `inp` file")

    # ---- 6. the KI's own files --------------------------------------------
    for rel, crit in (("diagnostics/triplets.yaml", True),
                      ("dag.yaml", False),
                      ("docs/format_spec.yaml", False),
                      ("tools/run_hstar.py", True),
                      ("tools/_hstar_io.py", True)):
        p = os.path.join(KI_DIR, rel)
        add("data", p, crit, "pass" if os.path.isfile(p) else "fail",
            fix=None if os.path.isfile(p) else f"{rel} is missing from this KI; "
                                               f"re-run the dissection.")

    # ---- 7. the tools import cleanly (CRITICAL) ---------------------------
    try:
        sys.path.insert(0, os.path.join(KI_DIR, "tools"))
        import _hstar_io  # noqa: F401
        import run_hstar  # noqa: F401
        import parse_outputs  # noqa: F401
        add("import", "KI tools (_hstar_io, run_hstar, parse_outputs)", True, "pass")
    except Exception as e:
        add("import", "KI tools", True, "fail",
            fix="A KI tool failed to import; re-run the dissection or fix the traceback.",
            detail=f"{type(e).__name__}: {str(e)[:90]}")

    print()
    trip = os.path.join(KI_DIR, "diagnostics", "triplets.yaml")
    if os.path.isfile(trip):
        print(f"  INFO  Diagnostic triplets: {trip}")
        print("         If the model fails, check them FIRST for a matching pattern.")
    print()
    n_fail = sum(1 for c in checks if c["status"] == "fail")
    n_crit_fail = sum(1 for c in checks if c["status"] == "fail" and c["critical"])
    print(f"  Results: {sum(1 for c in checks if c['status'] == 'pass')} passed, "
          f"{n_fail} failed ({n_crit_fail} critical), "
          f"{sum(1 for c in checks if c['status'] == 'warn')} warnings")
    print("  STATUS: " + ("MODEL READY" if n_crit_fail == 0 else
                          "BLOCKED -- fix the critical failures above"))
    print("PREFLIGHT_REPORT=" + json.dumps({"model_id": MODEL_ID, "checks": checks}))
    sys.exit(0 if n_crit_fail == 0 else 1)


if __name__ == "__main__":
    main()
