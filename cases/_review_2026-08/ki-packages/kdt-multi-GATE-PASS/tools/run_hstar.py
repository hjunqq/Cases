#!/usr/bin/env python3
"""run_hstar — execute the real HSTAR binary on a prepared case. (Capability 1, 30)

ARCHITECTURE (KDT execution-wrapper rules, plus three HSTAR-specific ones):

  1. COPY the whole template/case directory into a workspace.
  2. SWAP IN the user's files (mesh, materials, loads, ...) as whole files.
  3. MODIFY only named values in control files -- via _hstar_io.GlbDoc / set_inp, never by
     regenerating a file from a Python dict.
  4. RUN from the workspace directory. HSTAR takes NO command-line arguments: it opens a file
     literally called `inp` in the CURRENT WORKING DIRECTORY. `cwd=workspace` is not a
     convenience, it is the entire interface.
  5. FEED STDIN. HSTAR still contains interactive `read *` prompts that fire in ordinary runs:
       * Output.f90:3605  "give me the vdimn,coef1 and coef2?"  -- whenever `winit /= 0`
         and at least one active U-field group exists (i.e. almost every static case that
         writes an initial-stress .inw file).
       * Fem.f90:378/385/417  sub-mesh group and element lists  -- when `submodel < 0`.
       * Global.f90:767 `pause` -- when `ljdp /= 0` and `type_nl /= 5`.
     With stdin closed these become
     `forrtl: severe (24): end-of-file during read, unit -4, file /proc/<pid>/fd/0`
     AFTER a fully converged solution -- the results on disk are valid but the exit code is
     non-zero. See diagnostics/triplets.yaml dt_001.
  6. COLLECT outputs.

Usage:
    python3 run_hstar.py --case /tmp/mycase --outdir /tmp/myrun
    python3 run_hstar.py --case /tmp/mycase --binary /path/to/hstar --timeout 3600
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (ENC, GlbDoc, HstarInputError, check_consistent,  # noqa: E402
                       copy_template, probn_of, read_lines)

DEFAULT_BINARIES = [
    os.environ.get("HSTAR_BIN", ""),
    "/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR/x64/Release/hstar",
    "/tmp/claude-1000/kdt-work/HSTAR/build/hstar",
]

# Files HSTAR writes that are worth collecting. Everything else in the workspace is either
# an input or an intermediate.
OUTPUT_GLOBS = ["*.flavia.res", "*.flavia.msh", "*.post.bin", "*.chk", "*.opw", "*.oew",
                "*.ogw", "*.ojw", "*.dis", "*.gpv", "*.inw", "*.ctr", "*.gdm", "*.bar",
                "*.bem", "*.act", "*.rtt", "*.oid", "*.obsc", "*.cosm.dis", "*.cosm.gpv"]


def find_binary(explicit=None):
    for cand in ([explicit] if explicit else []) + DEFAULT_BINARIES:
        if cand and Path(cand).is_file() and os.access(cand, os.X_OK):
            return str(Path(cand).resolve())
    raise HstarInputError(
        "HSTAR binary not found. Set $HSTAR_BIN, or build it with "
        "`bash /home/huijun/HSTAR_Next/hstarYLOrig/build_linux.sh` "
        "(needs Intel ifx + MKL from /opt/intel/oneapi). See docs/s0_overview_and_build.md.")


def binary_kind(path):
    """Report ELF vs PE32 without ki_tools_common.cross_platform (not importable here)."""
    try:
        from ki_tools_common.cross_platform import detect_binary_type  # type: ignore
        return detect_binary_type(path)
    except Exception:
        pass
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic[:4] == b"\x7fELF":
        return "ELF"
    if magic[:2] == b"MZ":
        return "PE32 (Windows -- needs wine, which is NOT installed on this host)"
    return "unknown"


def default_stdin(case_dir):
    """Answers for HSTAR's interactive prompts, derived from the case's own switches."""
    probn = probn_of(case_dir)
    g = GlbDoc(Path(case_dir) / f"{probn}.glb")
    lines = []
    if int(g.get("winit")) != 0:
        # vdimn coef1 coef2 -- metadata written into the .inw initial-stress header
        # (Output.f90:3605-3614). 1 / 1.0 / 1.0 = no rescaling.
        lines.append("1 1.0 1.0")
    if int(g.get("submodel")) < 0:
        raise HstarInputError(
            "submodel<0 asks for sub-mesh group/element lists on stdin "
            "(Fem.f90:378-417). Pass them explicitly with --stdin-file.")
    # Trailing blanks satisfy any `pause` (Global.f90:767) without being consumed by a
    # value read, because value reads come first.
    lines += ["", "", ""]
    return lines


def run(case=None, template=None, outdir=None, binary=None, timeout=7200,
        workspace=None, swap_files=None, stdin_lines=None, keep_workspace=False,
        omp_threads=None):
    """Run HSTAR. Returns a result dict; never raises on a model-side failure."""
    t0 = time.time()
    exe = find_binary(binary)
    kind = binary_kind(exe)
    if not kind.startswith("ELF"):
        raise HstarInputError(f"{exe} is {kind}; this KI drives the native Linux build")

    # 1. workspace
    if workspace is None:
        workspace = tempfile.mkdtemp(prefix="hstar_")
    workspace = Path(workspace)
    if case:
        if workspace.exists():
            shutil.rmtree(workspace)
        shutil.copytree(case, workspace)
    elif template:
        copy_template(template, workspace, overwrite=True)
    else:
        raise HstarInputError("one of case= or template= is required")
    for p in workspace.rglob("*"):
        if p.is_file():
            p.chmod(p.stat().st_mode | 0o200)

    # 2. swap in user files
    for dest_name, src in (swap_files or {}).items():
        shutil.copy2(src, workspace / dest_name)

    # 3./validate before running -- the counts check is what turns a silent truncated mesh
    #    into an error message.
    info = check_consistent(workspace)
    if not info["ok"]:
        return {"status": "input_error", "problems": info["problems"],
                "workspace": str(workspace), "binary": exe}

    # 4. run
    stdin_lines = default_stdin(workspace) if stdin_lines is None else list(stdin_lines)
    env = dict(os.environ)
    if omp_threads:
        env["OMP_NUM_THREADS"] = str(int(omp_threads))
    log = workspace / "hstar_run.log"
    try:
        with open(log, "w", encoding=ENC, errors="replace") as fh:
            proc = subprocess.run([exe], cwd=str(workspace), env=env,
                                  input="\n".join(stdin_lines) + "\n",
                                  stdout=fh, stderr=subprocess.STDOUT,
                                  text=True, timeout=timeout)
        rc = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        rc, timed_out = -1, True

    tail = ""
    if log.is_file():
        tail = log.read_text(encoding=ENC, errors="replace")[-4000:]

    # 5. collect
    produced = []
    if outdir:
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        for pat in OUTPUT_GLOBS:
            for p in workspace.glob(pat):
                if p.stat().st_size > 0:
                    shutil.copy2(p, outdir / p.name)
                    produced.append(p.name)
        shutil.copy2(log, outdir / "hstar_run.log")

    res = {
        "status": ("timeout" if timed_out else "ok" if rc == 0 else "nonzero_exit"),
        "returncode": rc,
        "binary": exe,
        "binary_kind": kind,
        "workspace": str(workspace),
        "outdir": str(outdir) if outdir else None,
        "wall_seconds": round(time.time() - t0, 2),
        "case_info": info,
        "outputs_collected": sorted(set(produced)),
        "log_tail": tail[-1500:],
    }
    if rc != 0 and "end-of-file during read" in tail and "fd/0" in tail:
        res["diagnosis"] = ("HSTAR asked for input on stdin and got EOF -- see triplet dt_001. "
                            "The solution on disk is usually complete; re-run with the right "
                            "--stdin-file to get a clean exit.")
    if rc != 0 and "SIGSEGV" in tail:
        res["diagnosis"] = ("segmentation fault -- almost always a mesh/.glb count mismatch or "
                            "a group block that declares an element type whose auxiliary file "
                            "(.bem/.bar) is empty. See triplets dt_004, dt_009.")
    if not keep_workspace and outdir and res["status"] == "ok":
        shutil.rmtree(workspace, ignore_errors=True)
        res["workspace"] = "(removed)"
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", help="a prepared case directory (contains `inp`)")
    ap.add_argument("--template", help="a template name from _hstar_io.TEMPLATES")
    ap.add_argument("--outdir")
    ap.add_argument("--binary")
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--workspace")
    ap.add_argument("--keep-workspace", action="store_true")
    ap.add_argument("--omp-threads", type=int)
    ap.add_argument("--stdin-file", help="file whose lines are fed to HSTAR's stdin")
    a = ap.parse_args(argv)
    stdin_lines = None
    if a.stdin_file:
        stdin_lines, _ = read_lines(a.stdin_file)
    r = run(case=a.case, template=a.template, outdir=a.outdir, binary=a.binary,
            timeout=a.timeout, workspace=a.workspace, stdin_lines=stdin_lines,
            keep_workspace=a.keep_workspace, omp_threads=a.omp_threads)
    print(json.dumps(r, indent=2))
    return 0 if r["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
