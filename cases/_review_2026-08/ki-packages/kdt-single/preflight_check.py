#!/usr/bin/env python3
"""
preflight_check.py -- verify that everything an HSTAR run needs is present,
BEFORE the run.

Checks performed (all real; nothing is asserted without being looked at):

  binary      the hstar executable exists, is executable, is an ELF file, has
              every shared library resolved, and actually STARTS -- it is
              launched in a scratch directory with no `inp`, where a healthy
              binary must fail on the missing file rather than on a loader
              error or a crash.
  compiler    ifx and oneMKL, needed to (re)build
  imports     the Python modules the tools need
  ki_files    the KI's own tools, docs, templates and diagnostics
  template    the shipped template case has all 14 mandatory files and its
              .glb first record parses to 15 tokens
  selftest    hstar_io and hstar_common self-tests pass

Exit 0 = ready to run. Non-zero = blockers found, each with a fix printed.
The last line is always `PREFLIGHT_REPORT=<json>`.
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

KI_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(KI_DIR, "tools")
sys.path.insert(0, TOOLS)

BINARY_CANDIDATES = [
    os.environ.get("HSTAR_BIN", ""),
    "/tmp/claude-1000/kdt-single-out/work/bin/hstar",
    os.path.join(KI_DIR, "bin", "hstar"),
    "/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR/x64/Release/hstar",
]
IFX_CANDIDATES = [
    "/opt/intel/oneapi/compiler/2025.3/bin/ifx",
    "/opt/intel/oneapi/compiler/latest/bin/ifx",
    "/opt/intel/oneapi/compiler/latest/linux/bin/ifx",
]
MKL_ROOT = "/opt/intel/oneapi/mkl/latest"
MANDATORY_CASE_FILES = ["1.glb", "1.cor", "1.ele", "1.pre", "1.mat", "1.loa",
                        "1.man", "1.opr", "1.sol", "1.tem", "1.ifs", "1.nrt",
                        "1.ftr", "inp"]

checks = []


def add(kind, subject, critical, status, fix=""):
    checks.append({"kind": kind, "subject": subject, "critical": bool(critical),
                   "status": status, "fix": fix})
    mark = {"ok": "OK  ", "fail": "FAIL", "warn": "WARN"}.get(status, "????")
    print("[%s] %-11s %s" % (mark, kind, subject))
    if status != "ok" and fix:
        print("            fix: %s" % fix)


# ---------------------------------------------------------------- binary
def find_binary():
    for c in BINARY_CANDIDATES:
        if c and os.path.exists(c):
            return c
    return None


exe = find_binary()
if exe is None:
    add("binary", "hstar executable", True, "fail",
        "build it: python3 %s/tools/build_hstar.py --source_dir <HSTAR src> "
        "--out <path>/hstar   (searched: %s)"
        % (KI_DIR, [c for c in BINARY_CANDIDATES if c]))
else:
    real = os.path.realpath(exe)
    if not os.access(real, os.X_OK):
        add("binary", real, True, "fail", "chmod +x %s" % real)
    else:
        head = open(real, "rb").read(4)
        if head != b"\x7fELF":
            add("binary", real, True, "fail",
                "not an ELF executable (got %r) -- this is probably the Windows "
                "hstar.exe; rebuild with tools/build_hstar.py" % head)
        else:
            add("binary", real, True, "ok")

            # shared libraries
            try:
                ldd = subprocess.run(["ldd", real], capture_output=True,
                                     text=True, timeout=60)
                missing = [l.strip() for l in ldd.stdout.splitlines()
                           if "not found" in l]
                if missing:
                    add("library", "shared library resolution", True, "fail",
                        "unresolved: %s -- source the oneAPI environment "
                        "(`. /opt/intel/oneapi/setvars.sh`) or set "
                        "LD_LIBRARY_PATH" % missing)
                else:
                    add("library", "shared library resolution", True, "ok")
            except Exception as exc:
                add("library", "shared library resolution", True, "fail",
                    "ldd failed: %s" % exc)

            # does it actually start?  In an empty directory with no `inp`,
            # a healthy binary must die on the missing file, not on a loader
            # error or a signal.
            scratch = tempfile.mkdtemp(prefix="hstar_preflight_")
            try:
                p = subprocess.run([real], cwd=scratch, capture_output=True,
                                   text=True, timeout=120)
                out = (p.stdout or "") + (p.stderr or "")
                if p.returncode < 0:
                    add("binary", "startup smoke test", True, "fail",
                        "binary died on signal %d before reading `inp`; rebuild "
                        "with tools/build_hstar.py" % -p.returncode)
                elif "error while loading shared libraries" in out:
                    add("binary", "startup smoke test", True, "fail",
                        "dynamic loader error: %s" % out.strip().splitlines()[0])
                elif "inp" in out or "No such file" in out or \
                        "forrtl" in out or p.returncode != 0:
                    add("binary", "startup smoke test", True, "ok")
                else:
                    add("binary", "startup smoke test", False, "warn",
                        "binary exited 0 with no `inp` present, which is "
                        "unexpected; check the output: %s" % out[:200])
            except subprocess.TimeoutExpired:
                add("binary", "startup smoke test", True, "fail",
                    "binary hung for 120 s with no `inp` present")
            except Exception as exc:
                add("binary", "startup smoke test", True, "fail",
                    "could not launch: %s" % exc)
            finally:
                shutil.rmtree(scratch, ignore_errors=True)

# ------------------------------------------------------------- compiler
ifx = next((c for c in IFX_CANDIDATES if os.path.exists(c)), None) \
    or shutil.which("ifx") or shutil.which("ifort")
if ifx:
    add("compiler", ifx, False, "ok")
else:
    add("compiler", "Intel ifx / ifort", False, "warn",
        "needed only to REBUILD. gfortran cannot compile HSTAR (Intel "
        "extensions FORM='BINARY', buffered=, blocksize=, MKL_RCI/VSL) -- "
        "see triplet dt_002. Install oneAPI HPC Toolkit.")

mkl_lib = None
for d in (os.path.join(MKL_ROOT, "lib", "intel64"), os.path.join(MKL_ROOT, "lib")):
    if glob.glob(os.path.join(d, "libmkl_core.so*")):
        mkl_lib = d
        break
if mkl_lib:
    add("library", "oneMKL (%s)" % mkl_lib, False, "ok")
else:
    add("library", "oneMKL", False, "warn",
        "PARDISO, the trust-region inversion and the VSL random numbers all "
        "come from MKL; needed to rebuild and at run time")

# -------------------------------------------------------------- imports
for mod, critical, why in (("yaml", True, "reads diagnostics/triplets.yaml"),
                           ("json", True, "result serialisation"),
                           ("matplotlib", False, "validation figures")):
    try:
        __import__(mod)
        add("import", mod, critical, "ok")
    except ImportError:
        add("import", mod, critical, "fail" if critical else "warn",
            "pip install %s   (%s)" % (mod, why))

# ------------------------------------------------------------- KI files
for rel, critical in (("SKILL.md", True),
                      ("dag.yaml", True),
                      ("diagnostics/triplets.yaml", True),
                      ("knowledge_infrastructure.yaml", True),
                      ("docs/format_spec.yaml", True),
                      ("docs/input_preparation.md", True),
                      ("docs/validation_convention.yaml", False),
                      ("docs/gathered_papers.json", False)):
    p = os.path.join(KI_DIR, rel)
    add("ki_file", rel, critical, "ok" if os.path.exists(p) else
        ("fail" if critical else "warn"),
        "" if os.path.exists(p) else "missing from the KI package")

tools = sorted(glob.glob(os.path.join(TOOLS, "*.py")))
add("ki_file", "tools/ (%d scripts)" % len(tools), True,
    "ok" if len(tools) >= 3 else "fail",
    "" if len(tools) >= 3 else "the KI needs at least ingestion + execution + "
                               "parsing tools")

try:
    import yaml
    trip = yaml.safe_load(open(os.path.join(KI_DIR,
                                            "diagnostics/triplets.yaml")))
    if not isinstance(trip, list):
        add("ki_file", "triplets.yaml is a top-level list", True, "fail",
            "it parsed as %s; the self-improve overlay cannot read a "
            "`triplets:` mapping and has erased corpora stored that way"
            % type(trip).__name__)
    elif len(trip) < 15:
        add("ki_file", "triplets.yaml has %d entries" % len(trip), True, "fail",
            "at least 15 are required")
    else:
        bad = [t.get("id") for t in trip
               if not all(k in t for k in ("id", "symptom", "diagnosis",
                                           "remedy"))]
        if bad:
            add("ki_file", "triplet field completeness", True, "fail",
                "these entries lack id/symptom/diagnosis/remedy: %s" % bad)
        else:
            add("ki_file", "triplets.yaml (%d entries)" % len(trip), True, "ok")
except Exception as exc:
    add("ki_file", "triplets.yaml parses", True, "fail", "YAML error: %s" % exc)

# ------------------------------------------------------------- template
tdir = os.path.join(KI_DIR, "templates", "static_2d")
missing = [f for f in MANDATORY_CASE_FILES
           if not os.path.exists(os.path.join(tdir, f))]
if missing:
    add("data", "template case static_2d", True, "fail",
        "missing %s -- HSTAR OPENs every one of these unconditionally "
        "(Global.f90:628)" % missing)
else:
    try:
        from hstar_io import GlbFile
        toks = GlbFile(os.path.join(tdir, "1.glb")).tokens_after("NPOIN")
        if len(toks) != 15:
            add("data", "template 1.glb first record", True, "fail",
                "parsed to %d tokens, expected 15 -- the template is a "
                "different vintage (triplet dt_005)" % len(toks))
        else:
            add("data", "template case static_2d (14 files, .glb ok)", True, "ok")
    except Exception as exc:
        add("data", "template 1.glb parses", True, "fail", str(exc))

# ------------------------------------------------------------- selftests
for mod in ("hstar_io", "hstar_common"):
    p = os.path.join(TOOLS, mod + ".py")
    if not os.path.exists(p):
        add("selftest", mod, True, "fail", "tool missing from the KI")
        continue
    try:
        r = subprocess.run([sys.executable, p, "--selftest"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and "OK" in r.stdout:
            add("selftest", "%s --selftest" % mod, True, "ok")
        else:
            add("selftest", "%s --selftest" % mod, True, "fail",
                (r.stdout + r.stderr).strip()[:300])
    except Exception as exc:
        add("selftest", "%s --selftest" % mod, True, "fail", str(exc))

# ---------------------------------------------------------------- report
fails = [c for c in checks if c["critical"] and c["status"] == "fail"]
print()
print("%d check(s): %d ok, %d warn, %d fail (%d critical)"
      % (len(checks),
         sum(1 for c in checks if c["status"] == "ok"),
         sum(1 for c in checks if c["status"] == "warn"),
         sum(1 for c in checks if c["status"] == "fail"),
         len(fails)))
if fails:
    print("BLOCKED. See diagnostics/triplets.yaml for recovery: "
          "dt_002 (compiler), dt_003 (gidpost), dt_004/dt_005 (.glb records).")
else:
    print("HSTAR is ready to run. Start at docs/s1_case_setup.md.")
print("PREFLIGHT_REPORT=" + json.dumps(checks))
sys.exit(1 if fails else 0)
