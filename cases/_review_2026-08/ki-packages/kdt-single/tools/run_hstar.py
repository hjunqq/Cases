#!/usr/bin/env python3
"""
run_hstar.py -- Stage s9: execute the HSTAR binary.

Execution contract, forced by the code itself:

  * HSTAR opens `inp` **relative to the current working directory**
    (`Fem.f90:90`), then opens `probn//'.glb'` etc. relative to CWD as well.
    There are no command-line arguments (the `GETARG` calls at Fem.f90:96-101
    are commented out).  Therefore the ONLY way to select a case is to chdir
    into it with `inp` record 4 = `1`.
  * ~40 unit numbers are OPENed unconditionally at start-up.  A run leaves
    ~35 files behind in the working directory, several of them stale from a
    previous run.  Reusing a directory silently mixes results.

So this wrapper follows the KI's execution-wrapper architecture:

  1. COPY the whole prepared case directory to a fresh temp workspace
  2. SWAP IN any user-supplied override files
  3. MODIFY only specific values in `inp` (restart flag, runblks)
  4. RUN the binary with cwd = workspace
  5. COLLECT the outputs into --output_dir

Nothing is regenerated from a Python dict.

validate -> process -> validate:
  pre : binary exists and is executable; the case has the 14 mandatory files;
        `inp` record 4 is `1`; runblks <= nblks
  post: exit status 0; `.chk` exists and its tail does not carry a Fortran
        runtime error; at least one result file is non-empty

Usage
-----
  python3 run_hstar.py --case c1 --output_dir out1
  python3 run_hstar.py --case c1 --output_dir out2 --restart 1 --runblks 2
  python3 run_hstar.py --case c1 --output_dir out3 --threads 8 --timeout 3600
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hstar_io import GlbFile  # noqa: E402
from make_case import MANDATORY  # noqa: E402

KI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BINARY_CANDIDATES = [
    os.environ.get("HSTAR_BIN", ""),
    "/tmp/claude-1000/kdt-single-out/work/bin/hstar",
    os.path.join(KI_DIR, "bin", "hstar"),
    "/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR/x64/Release/hstar",
]

# Files worth keeping.  `.rtt`/`.stf` are large binary state; kept because a
# restart needs them.
COLLECT = [".chk", ".flavia.res", ".flavia.msh", ".gpv", ".act", ".dis",
           ".opw", ".oew", ".ogw", ".ojw", ".ctr", ".gdm", ".bar", ".bem",
           ".res", ".resb", ".oit", ".oip", ".rtt", ".inw", ".fai", ".upf",
           ".stn", ".obsc"]

# Fortran runtime failures that a zero exit status can still hide.
ERROR_MARKERS = [
    "forrtl: severe", "Fortran runtime error", "end of file",
    "Segmentation fault", "insufficient virtual memory",
    "SINGULAR", "singular", "PARDISO error", "not converged for checki",
]


def find_binary(explicit=""):
    for c in ([explicit] if explicit else []) + BINARY_CANDIDATES:
        if c and os.path.exists(c) and os.access(c, os.X_OK):
            return c
    return None


def validate_case(case_dir):
    p = []
    if not os.path.isdir(case_dir):
        return ["case directory not found: %s" % case_dir]
    for f in MANDATORY:
        if not os.path.exists(os.path.join(case_dir, f)):
            p.append("case is missing %s -- HSTAR OPENs it unconditionally "
                     "(Global.f90:628)" % f)
    inp = os.path.join(case_dir, "inp")
    if os.path.exists(inp):
        recs = open(inp).read().split("\n")
        if len(recs) < 5:
            p.append("inp has fewer than 5 records")
        elif recs[3].strip() != "1":
            p.append("inp record 4 (probn) is %r; this wrapper always runs with "
                     "cwd = the case directory, so it must be '1'" % recs[3])
    return p


def patch_inp(workspace, restart=None, runblks=None):
    """MODIFY specific values -- string replacement, never regeneration."""
    path = os.path.join(workspace, "inp")
    recs = open(path).read().split("\n")
    if restart is not None:
        toks = recs[1].split()
        toks[0] = str(restart)
        recs[1] = "  " + "  ".join(toks)
    if runblks is not None:
        recs[4] = str(runblks)
    open(path, "w").write("\n".join(recs))


def scan_log(text):
    hits = []
    low = text
    for m in ERROR_MARKERS:
        if m in low:
            hits.append(m)
    return hits


def run(case_dir, output_dir, binary=None, restart=None, runblks=None,
        threads=None, timeout=7200, keep_workspace=False, overrides=None):
    problems = validate_case(case_dir)
    exe = find_binary(binary or "")
    if exe is None:
        problems.append(
            "HSTAR binary not found. Build it with tools/build_hstar.py "
            "or set HSTAR_BIN. Searched: %s"
            % [c for c in BINARY_CANDIDATES if c])
    if not problems:
        g = GlbFile(os.path.join(case_dir, "1.glb"))
        nblks = int(g.tokens_after("NINIT")[3])
        if runblks is not None and runblks > nblks:
            problems.append("runblks=%d exceeds nblks=%d in .glb"
                            % (runblks, nblks))
    if problems:
        for p in problems:
            print("BLOCKER:", p)
        raise SystemExit(1)

    # 1. COPY
    workspace = tempfile.mkdtemp(prefix="hstar_")
    shutil.copytree(case_dir, workspace, dirs_exist_ok=True)

    # 2. SWAP IN
    for src in (overrides or []):
        shutil.copy2(src, os.path.join(workspace, os.path.basename(src)))

    # 3. MODIFY
    patch_inp(workspace, restart, runblks)

    # 4. RUN
    env = dict(os.environ)
    if threads:
        env["OMP_NUM_THREADS"] = str(threads)
        env["MKL_NUM_THREADS"] = str(threads)
    t0 = time.time()
    log_path = os.path.join(workspace, "run.log")
    with open(log_path, "w") as log:
        proc = subprocess.run([exe], cwd=workspace, stdout=log,
                              stderr=subprocess.STDOUT, env=env,
                              timeout=timeout)
    wall = time.time() - t0
    log_text = open(log_path, errors="replace").read()

    # 5. COLLECT
    os.makedirs(output_dir, exist_ok=True)
    collected = []
    for name in sorted(os.listdir(workspace)):
        if name == "run.log" or any(name.endswith(ext) for ext in COLLECT):
            src = os.path.join(workspace, name)
            if os.path.isfile(src) and os.path.getsize(src) > 0:
                shutil.copy2(src, os.path.join(output_dir, name))
                collected.append(name)

    # post-checks
    post = []
    if proc.returncode != 0:
        post.append("binary exited with status %d" % proc.returncode)
    chk = os.path.join(output_dir, "1.chk")
    if not os.path.exists(chk):
        post.append("no 1.chk was produced -- HSTAR did not get past "
                    "global_data(); the .glb record sequence is wrong "
                    "(triplet dt_004)")
    markers = scan_log(log_text) + scan_log(
        open(chk, errors="replace").read() if os.path.exists(chk) else "")
    if any(m for m in markers if m not in ("not converged for checki",)):
        post.append("log carries failure marker(s): %s" % sorted(set(markers)))
    results = [f for f in collected
               if f.endswith((".flavia.res", ".gpv", ".dis", ".opw"))]
    if not results:
        post.append("no result file was written -- check noutn/noutf in .man "
                    "and the gid_* flags in .glb")

    report = {
        "binary": exe,
        "case_dir": os.path.abspath(case_dir),
        "workspace": workspace if keep_workspace else None,
        "output_dir": os.path.abspath(output_dir),
        "returncode": proc.returncode,
        "wall_seconds": round(wall, 3),
        "collected": collected,
        "log_markers": sorted(set(markers)),
        "post_check_problems": post,
        "ok": proc.returncode == 0 and not post,
    }
    with open(os.path.join(output_dir, "run_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    if not keep_workspace:
        shutil.rmtree(workspace, ignore_errors=True)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--binary", default="")
    ap.add_argument("--restart", type=int)
    ap.add_argument("--runblks", type=int)
    ap.add_argument("--threads", type=int)
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--keep-workspace", action="store_true")
    ap.add_argument("--override", action="append", default=[])
    a = ap.parse_args()

    rep = run(a.case, a.output_dir, a.binary, a.restart, a.runblks,
              a.threads, a.timeout, a.keep_workspace, a.override)
    print(json.dumps(rep, indent=2))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
