#!/usr/bin/env python3
"""Preflight for the HSTAR `gravdam_static_2block` KI package.

Runs a fixed list of checks and returns a STRUCTURED result. Nothing is
hardcoded to one machine: the repo root is derived from this file's location
(overridable with HSTAR_REPO), the solver path from HSTAR_EXE with the same
default `run_pipeline.py` uses, and the Intel oneAPI directories are discovered
at runtime by the repo's own `intel_runtime` module.

Usage:
    python3 preflight_check.py [job_dir] [--json] [--quiet]

Exit codes:
    0  all checks pass or warn
    1  at least one check failed
    2  the checker itself could not run (bad repo layout)

Each check yields: id, status (pass|warn|fail|skip), detail, and — when not
passing — `remedy` and the `triplet` id that explains it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

# Repo root: <repo>/fem-chat/docs/research/kiss-trial-pkg/preflight_check.py
_DEFAULT_REPO = Path(__file__).resolve().parents[4]
REPO = Path(os.environ.get("HSTAR_REPO", _DEFAULT_REPO))
FEMCHAT = REPO / "fem-chat"
SKILLS = FEMCHAT / "skills"

# Same default as skills/run_pipeline.py:57, same env override.
DEFAULT_HSTAR_EXE = REPO / "hstarYLOrig" / "HSTAR" / "x64" / "Release" / "hstar"

# The only (nnode, ndimn) pairs generator.py:elem_info() really maps. Anything
# else silently becomes a 2D quad — dt_hstar_012.
REAL_ELEM_MAPPINGS = {(2, 2), (2, 3), (3, 2), (4, 2), (8, 3)}
# What generator.py:_gen_mat can actually write — dt_hstar_013.
SUPPORTED_MATERIALS = {
    "ELASTIC", "SEEPAGE", "HEAT", "MC", "CLASSICALEP",
    "GOODMAN", "CONCRETE", "DUNCANCHANG", "GEOMETRY",
}

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"


@dataclass
class Check:
    id: str
    status: str
    detail: str
    remedy: str | None = None
    triplet: str | None = None
    data: dict = field(default_factory=dict)


def _ok(cid, detail, **data):
    return Check(cid, PASS, detail, data=data)


def _fail(cid, detail, remedy, triplet=None, **data):
    return Check(cid, FAIL, detail, remedy, triplet, data)


def _warn(cid, detail, remedy=None, triplet=None, **data):
    return Check(cid, WARN, detail, remedy, triplet, data)


def _skip(cid, detail):
    return Check(cid, SKIP, detail)


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_python() -> Check:
    v = sys.version_info
    if (v.major, v.minor) < (3, 10):
        return _fail(
            "python_version",
            f"Python {v.major}.{v.minor} — the toolchain uses PEP 604 `X | Y` annotations",
            "Run with python3.10 or newer.",
            version=f"{v.major}.{v.minor}.{v.micro}",
        )
    return _ok("python_version", f"Python {v.major}.{v.minor}.{v.micro}",
               version=f"{v.major}.{v.minor}.{v.micro}")


def check_repo_layout() -> Check:
    missing = [
        str(p.relative_to(REPO))
        for p in (SKILLS / "run_pipeline.py", SKILLS / "generator.py",
                  SKILLS / "quick_analysis.py", SKILLS / "gen_gravdam.py",
                  SKILLS / "intel_runtime.py", FEMCHAT / "harness" / "gate.py")
        if not p.exists()
    ]
    if missing:
        return _fail(
            "repo_layout", f"missing from {REPO}: {', '.join(missing)}",
            "Set HSTAR_REPO to the checkout root (the dir containing fem-chat/).",
            repo=str(REPO), missing=missing,
        )
    return _ok("repo_layout", f"toolchain found under {FEMCHAT}", repo=str(REPO))


def check_solver_binary() -> Check:
    exe = Path(os.environ.get("HSTAR_EXE", DEFAULT_HSTAR_EXE))
    if not exe.exists():
        return _fail(
            "solver_binary", f"not found: {exe}",
            "Build or restore the YL-mainline binary, or point HSTAR_EXE at it. "
            "Note HSTAR_Q/ is a DIFFERENT solver — do not substitute it.",
            exe=str(exe),
        )
    if not os.access(exe, os.X_OK):
        return _fail("solver_binary", f"not executable: {exe}",
                     f"chmod +x {exe}", exe=str(exe))
    st = exe.stat()
    return _ok("solver_binary", f"{exe} ({st.st_size} bytes, mtime {int(st.st_mtime)})",
               exe=str(exe), size=st.st_size, mtime=int(st.st_mtime))


def check_mkl_runtime() -> Check:
    """Delegate to the repo's own discovery — never hardcode an oneAPI path."""
    sys.path.insert(0, str(SKILLS))
    try:
        from intel_runtime import get_intel_paths  # type: ignore
    except Exception as e:  # pragma: no cover
        return _fail("mkl_runtime", f"cannot import intel_runtime: {e}",
                     "Check the repo layout / HSTAR_REPO.", triplet="dt_hstar_001")
    try:
        paths = get_intel_paths()
    except Exception as e:
        return _fail("mkl_runtime", f"intel_runtime.get_intel_paths() raised: {e}",
                     "Install Intel oneAPI (compiler + MKL) under /opt/intel/oneapi.",
                     triplet="dt_hstar_001")
    if not paths:
        return _fail(
            "mkl_runtime",
            "no oneAPI directory carrying the required sonames was found",
            "Install Intel oneAPI MKL. Diagnose with: "
            f"python3 {SKILLS / 'intel_runtime.py'} -v",
            triplet="dt_hstar_001",
        )
    # Confirm the discovered dirs really carry an MKL interface library, so a
    # pass here means more than "a directory exists".
    found = sorted({
        so.name for p in paths for so in Path(p).glob("libmkl_intel_lp64.so*")
    })
    if not found:
        return _fail(
            "mkl_runtime",
            f"discovered {len(paths)} oneAPI dirs but none contains libmkl_intel_lp64.so*",
            "The mkl/latest symlink may have rolled to a release without the "
            "sonames this binary was linked against; install a matching MKL.",
            triplet="dt_hstar_001", paths=paths,
        )
    return _ok("mkl_runtime", f"{len(paths)} oneAPI dirs; MKL interface libs: {', '.join(found)}",
               paths=paths, mkl_libs=found)


def check_solver_links() -> Check:
    """Actually resolve the binary's dynamic deps with the injected env.

    This is the difference between 'MKL exists somewhere' and 'this binary can
    start'. It is the check that would have caught dt_hstar_001 before a run.
    """
    import subprocess
    exe = Path(os.environ.get("HSTAR_EXE", DEFAULT_HSTAR_EXE))
    if not exe.exists():
        return _skip("solver_links", "solver binary absent")
    sys.path.insert(0, str(SKILLS))
    try:
        from intel_runtime import inject_into_env  # type: ignore
        env = inject_into_env(dict(os.environ))
    except Exception as e:
        return _fail("solver_links", f"cannot build injected env: {e}",
                     "See mkl_runtime.", triplet="dt_hstar_001")
    try:
        out = subprocess.run(["ldd", str(exe)], env=env, capture_output=True,
                             text=True, timeout=30).stdout
    except Exception as e:
        return _warn("solver_links", f"ldd unavailable: {e}")
    unresolved = [ln.strip() for ln in out.splitlines() if "not found" in ln]
    if unresolved:
        return _fail(
            "solver_links",
            f"{len(unresolved)} unresolved shared libs: {'; '.join(unresolved[:5])}",
            "Launch only via quick_analysis.py / run_pipeline.py. If those also "
            "fail, the installed oneAPI lacks the sonames the binary needs.",
            triplet="dt_hstar_001", unresolved=unresolved,
        )
    return _ok("solver_links", "all dynamic deps resolve under the injected environment")


def check_job_dir(job_dir: Path | None) -> list[Check]:
    if job_dir is None:
        return [_skip("job_dir", "no job dir given — environment-only preflight")]
    checks: list[Check] = []
    if not job_dir.is_dir():
        return [_fail("job_dir", f"not a directory: {job_dir}",
                      "Create it and generate a mesh with gen_gravdam.py.")]
    checks.append(_ok("job_dir", str(job_dir), path=str(job_dir)))

    cor, ele = job_dir / "1.cor", job_dir / "1.ele"
    if not cor.exists() or not ele.exists():
        checks.append(_fail(
            "mesh_files", f"missing {'1.cor' if not cor.exists() else ''} "
                          f"{'1.ele' if not ele.exists() else ''}".strip(),
            f"python3 {SKILLS / 'gen_gravdam.py'} {job_dir} --height 100",
        ))
        return checks

    npoin = sum(1 for ln in cor.read_text(errors="replace").splitlines() if ln.split())
    ele_lines = [ln.split() for ln in ele.read_text(errors="replace").splitlines() if ln.split()]
    nelem = len(ele_lines)
    checks.append(_ok("mesh_files", f"npoin={npoin} nelem={nelem}",
                      npoin=npoin, nelem=nelem))

    # ndimn from the coordinate columns; nnode from the element rows. The last
    # element column is the group id when present, so take the modal width.
    first = cor.read_text(errors="replace").split("\n")[0].split()
    ndimn = max(0, len(first) - 1)
    widths = {len(r) for r in ele_lines}
    # element row = id + nnode [+ group]; assume a uniform mesh
    w = max(widths) if widths else 0
    nnode_with_group = w - 2
    nnode_no_group = w - 1
    nnode = nnode_with_group if (nnode_with_group, ndimn) in REAL_ELEM_MAPPINGS else nnode_no_group
    if (nnode, ndimn) not in REAL_ELEM_MAPPINGS:
        checks.append(_fail(
            "mesh_element_type",
            f"(nnode={nnode}, ndimn={ndimn}) has no real mapping in generator.elem_info()",
            "generator.py would SILENTLY emit a 2D quad (index 5) for this mesh. "
            "Use a 2D Q4/T3 mesh for this family.",
            triplet="dt_hstar_012", nnode=nnode, ndimn=ndimn,
        ))
    elif (nnode, ndimn) != (4, 2):
        checks.append(_warn(
            "mesh_element_type",
            f"(nnode={nnode}, ndimn={ndimn}) is mapped, but this family expects 2D Q4 (4,2)",
            nnode=nnode, ndimn=ndimn,
        ))
    else:
        checks.append(_ok("mesh_element_type", "2D Q4 (nnode=4, ndimn=2)",
                          nnode=nnode, ndimn=ndimn))

    meta = job_dir / "gravdam_meta.json"
    if not meta.exists():
        checks.append(_fail(
            "gravdam_meta", "gravdam_meta.json absent while a mesh is present",
            "water_pressure.use_meta_edges would resolve to an EMPTY edge list "
            "with only a WARNING, and the run would finish with no water load. "
            "Regenerate the mesh with gen_gravdam.py, or copy the meta file.",
            triplet="dt_hstar_005",
        ))
    else:
        try:
            edges = json.loads(meta.read_text()).get("upstream_face_edges", [])
        except Exception as e:
            checks.append(_fail("gravdam_meta", f"unparseable: {e}",
                                "Regenerate with gen_gravdam.py", triplet="dt_hstar_005"))
        else:
            if not edges:
                checks.append(_fail(
                    "gravdam_meta", "upstream_face_edges is empty",
                    "Regenerate the mesh; without edges there is no water load.",
                    triplet="dt_hstar_005",
                ))
            else:
                checks.append(_ok("gravdam_meta", f"{len(edges)} upstream-face edges",
                                  n_edges=len(edges)))

    res = job_dir / "1.flavia.res"
    if res.exists():
        checks.append(_warn(
            "clean_job_dir", "1.flavia.res already present — a new solve would overwrite it",
            "One analysis per job dir; use a fresh dir or the case mechanism.",
            triplet="dt_hstar_008",
        ))
    else:
        checks.append(_ok("clean_job_dir", "no prior 1.flavia.res"))

    cfg = job_dir / "config.json"
    if cfg.exists():
        checks.extend(_check_config(json.loads(cfg.read_text(encoding="utf-8"))))
    return checks


def _check_config(cfg: dict) -> list[Check]:
    out: list[Check] = []
    tp = cfg.get("type_problem")
    if tp != "Q":
        out.append(_fail("type_problem", f"type_problem={tp!r}, expected 'Q' for static",
                         "static=Q, modal=E, dynamic=F, transient/thermal/seepage=S",
                         triplet="dt_hstar_003"))
    else:
        out.append(_ok("type_problem", "Q (static)"))

    bad = [m.get("type") for m in cfg.get("materials", [])
           if m.get("type") not in SUPPORTED_MATERIALS]
    if bad:
        out.append(_fail(
            "material_types_supported", f"generator cannot write: {bad}",
            f"Supported: {sorted(SUPPORTED_MATERIALS)}. CAMCLAY in particular is a "
            "dead config — it sets plastic output switches but falls through to ELASTIC.",
            triplet="dt_hstar_013", bad=bad,
        ))
    else:
        out.append(_ok("material_types_supported",
                       f"{len(cfg.get('materials', []))} materials, all writable"))

    for m in cfg.get("materials", []):
        E = m.get("E")
        if isinstance(E, (int, float)) and 0 < E < 1e8:
            out.append(_warn(
                "modulus_units", f"material {m.get('id')} has E={E:g} — suspiciously small for Pa",
                "E must be in Pa (concrete ~2.5e10, rock ~1e10). MPa/GPa inflate "
                "displacements by 1e6/1e9 with no error.",
                triplet="dt_hstar_010", material=m.get("id"), E=E,
            ))
            break
    else:
        if cfg.get("materials"):
            out.append(_ok("modulus_units", "all E values plausible as Pa"))

    wp = cfg.get("water_pressure") or {}
    if wp:
        g = wp.get("gamma_w")
        if isinstance(g, (int, float)) and g < 5000:
            out.append(_fail(
                "gamma_w_unit", f"gamma_w={g} looks like a density, not a unit weight",
                "gamma_w = 9810 N/m^3. 1000 kg/m^3 under-loads the reservoir 9.81x.",
                triplet="dt_hstar_011", gamma_w=g,
            ))
        else:
            out.append(_ok("gamma_w_unit", f"gamma_w={g}"))
        if not wp.get("use_meta_edges") and not wp.get("edges_list"):
            out.append(_fail(
                "water_edges_source", "neither use_meta_edges nor an explicit edges_list",
                "Auto-detection by global x_min hits the FOUNDATION's left boundary. "
                "Set use_meta_edges: true.",
                triplet="dt_hstar_004",
            ))
        else:
            out.append(_ok("water_edges_source",
                           "use_meta_edges" if wp.get("use_meta_edges") else "explicit edges_list"))

    if cfg.get("boundary") and cfg.get("node_fixes"):
        out.append(_fail(
            "boundary_not_stacked", "boundary presets AND node_fixes both present",
            "Over-constrained. Dam family: presets only, no node_fixes.",
            triplet="dt_hstar_007",
        ))
    return out


def run(job_dir: Path | None) -> dict:
    checks = [check_python(), check_repo_layout()]
    if checks[1].status == PASS:
        checks += [check_solver_binary(), check_mkl_runtime(), check_solver_links()]
    checks += check_job_dir(job_dir)
    counts = {s: sum(1 for c in checks if c.status == s) for s in (PASS, WARN, FAIL, SKIP)}
    return {
        "package": "hstar-gravdam-static-2block",
        "case_family": "gravdam_static_2block",
        "repo": str(REPO),
        "job_dir": str(job_dir) if job_dir else None,
        "ok": counts[FAIL] == 0,
        "counts": counts,
        "checks": [asdict(c) for c in checks],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job_dir", nargs="?", default=None)
    ap.add_argument("--json", action="store_true", help="emit the structured result only")
    ap.add_argument("--quiet", action="store_true", help="print failures/warnings only")
    a = ap.parse_args()

    report = run(Path(a.job_dir).resolve() if a.job_dir else None)

    if a.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        mark = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL", SKIP: "skip"}
        for c in report["checks"]:
            if a.quiet and c["status"] in (PASS, SKIP):
                continue
            print(f"[{mark[c['status']]}] {c['id']}: {c['detail']}")
            if c.get("remedy"):
                print(f"         remedy: {c['remedy']}")
            if c.get("triplet"):
                print(f"         triplet: {c['triplet']}")
        n = report["counts"]
        print(f"\n{n[PASS]} pass · {n[WARN]} warn · {n[FAIL]} fail · {n[SKIP]} skip"
              f"  ->  {'GO' if report['ok'] else 'NO-GO'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # the checker itself broke
        print(f"preflight_check.py failed to run: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
