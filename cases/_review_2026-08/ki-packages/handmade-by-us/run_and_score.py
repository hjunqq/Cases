#!/usr/bin/env python3
"""Run and score one `gravdam_static_2block` case.

Stage-resumed by artifact presence (VIC-style): whatever already exists in the
job dir is not redone.

    s1_mesh_generation   skipped when 1.cor + 1.ele exist
    s4_solve             skipped when 1.flavia.res exists (a re-solve would
                         clobber it — dt_hstar_008)
    s6_scoring           always

Scoring = harness/gate.py:physics_gate (the repo's single "not garbage"
definition) PLUS the family-specific physical checks from SKILL.md
"Verification". This family has NO registered benchmark validator
(dt_hstar_009), so result.json records validator: null and says so.

Parsers are the repo's own (tools/flavia_to_vtu.read_flavia_res,
skills/mesh_io) — this script does not re-implement deck or result parsing.

Usage:
    python3 run_and_score.py <job_dir> [--height 100] [--water-level 100]
                             [--json] [--score-only]
Exit: 0 scored PASS · 1 scored FAIL · 2 could not get to a score
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_DEFAULT_REPO = Path(__file__).resolve().parents[4]
REPO = Path(os.environ.get("HSTAR_REPO", _DEFAULT_REPO))
FEMCHAT = REPO / "fem-chat"
SKILLS = FEMCHAT / "skills"
for p in (str(FEMCHAT), str(SKILLS), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

TEMPLATE = "gravdam_static_2block"
# Plausible band for |u| in block 2 of an H~100 m concrete dam on rock, metres.
U_MIN, U_MAX = 1e-5, 1e-1


def _sh(cmd: list[str], cwd: Path) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# --------------------------------------------------------------------------
# stages
# --------------------------------------------------------------------------

def stage_mesh(job: Path, height: float, log: list) -> bool:
    if (job / "1.cor").exists() and (job / "1.ele").exists():
        log.append({"stage": "s1_mesh_generation", "action": "skipped", "reason": "1.cor + 1.ele present"})
        return True
    rc, out = _sh([sys.executable, str(SKILLS / "gen_gravdam.py"), str(job),
                   "--height", str(height)], job)
    log.append({"stage": "s1_mesh_generation", "action": "ran",
                "rc": rc, "tail": out.strip().splitlines()[-5:]})
    return rc == 0


def stage_solve(job: Path, water_level: float, log: list) -> bool:
    if (job / "1.flavia.res").exists():
        log.append({"stage": "s4_solve", "action": "skipped",
                    "reason": "1.flavia.res present — re-solving would clobber it (dt_hstar_008)"})
        return True
    overrides = json.dumps({"water_pressure": {"water_level": water_level}})
    rc, out = _sh([sys.executable, str(SKILLS / "quick_analysis.py"),
                   str(job), TEMPLATE, overrides], job)
    (job / "pipeline_stdout.log").write_text(out, encoding="utf-8")
    log.append({"stage": "s4_solve", "action": "ran", "rc": rc,
                "tail": out.strip().splitlines()[-15:]})
    return (job / "1.flavia.res").exists()


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

def _dam_nodes(job: Path) -> tuple[set[int], dict, str | None]:
    """Node ids belonging to element group 2 (the dam body), plus coords."""
    try:
        import mesh_io  # type: ignore
        coords = mesh_io.read_coords(str(job))
        elements = mesh_io.read_elements(str(job))
        gids = mesh_io.read_element_group_ids(str(job))
    except Exception as e:
        return set(), {}, f"mesh_io failed: {type(e).__name__}: {e}"
    # mesh_io.read_elements -> [(eid, [n1..nN]), ...]
    # mesh_io.read_element_group_ids -> [gid_or_None, ...] aligned to that order
    if not gids:
        return set(), coords, "no element group ids in the mesh"
    nodes: set[int] = set()
    for (_eid, nds), g in zip(elements, gids):
        if g == 2:
            nodes.update(nds)
    return nodes, coords, None


def _group_centroid_y(job: Path, coords: dict) -> dict[int, float]:
    try:
        import mesh_io  # type: ignore
        elements = mesh_io.read_elements(str(job))
        gids = mesh_io.read_element_group_ids(str(job))
    except Exception:
        return {}
    acc: dict[int, list[float]] = {}
    for (_eid, nds), g in zip(elements, gids):
        if g is None:
            continue
        ys = [coords[n][1] for n in nds if n in coords and len(coords[n]) > 1]
        if ys:
            acc.setdefault(g, []).append(sum(ys) / len(ys))
    return {g: sum(v) / len(v) for g, v in acc.items()}


def score(job: Path) -> dict:
    checks: list[dict] = []

    def add(cid, ok, detail, triplet=None, **data):
        checks.append({"id": cid, "status": "pass" if ok else "fail",
                       "detail": detail, "triplet": triplet, **({"data": data} if data else {})})

    def info(cid, detail, **data):
        checks.append({"id": cid, "status": "info", "detail": detail,
                       **({"data": data} if data else {})})

    # 1 — the repo's own gate
    from harness.gate import physics_gate  # type: ignore
    ok, problems = physics_gate(job)
    add("physics_gate", ok, "clean" if ok else "; ".join(problems))

    # 2 — result structure
    try:
        from flavia_to_vtu import read_flavia_res  # type: ignore
        blocks = read_flavia_res(str(job / "1.flavia.res"), ndimn=2)
    except Exception as e:
        add("parse_results", False, f"read_flavia_res failed: {type(e).__name__}: {e}")
        return _wrap(job, checks)
    disp = [b for b in blocks if "DISPLACEMENT" in b["type"].upper()]
    add("two_construction_steps", len(disp) == 2,
        f"{len(disp)} DISPLACEMENT block(s); nblks=2 expects 2",
        n_disp=len(disp))
    info("result_blocks", ", ".join(sorted({b["type"] for b in blocks})) or "none")

    if not disp:
        return _wrap(job, checks)
    final = disp[-1]["data"]

    # 3 — water actually reached the deck
    logtext = ""
    for name in ("run.log", "pipeline_stdout.log"):
        f = job / name
        if f.exists():
            logtext += f.read_text(errors="replace")
    m = re.search(r"Using\s+(\d+)\s+dam upstream-face edges", logtext)
    if m:
        n = int(m.group(1))
        add("water_edges_applied", n > 0, f"{n} upstream-face edges applied",
            triplet="dt_hstar_005", n_edges=n)
    else:
        warn = "use_meta_edges set but gravdam_meta.json not found" in logtext
        add("water_edges_applied", False,
            "no 'Using N dam upstream-face edges' line in the log"
            + (" — and the missing-meta WARNING IS present" if warn else ""),
            triplet="dt_hstar_005")

    # 4 — displacement physics on the dam body
    dam, coords, err = _dam_nodes(job)
    if err or not dam:
        info("dam_nodes", err or "group 2 empty; falling back to all nodes")
        dam = set(final.keys())
    ux = [v[0] for n, v in final.items() if n in dam and len(v) >= 1]
    uy = [v[1] for n, v in final.items() if n in dam and len(v) >= 2]
    if ux and uy:
        add("crest_downstream", max(ux) > 0,
            f"max ux on the dam body = {max(ux):.6g} m (must be > 0, downstream)",
            triplet="dt_hstar_004", max_ux=max(ux))
        add("dam_settles", min(uy) < 0,
            f"min uy on the dam body = {min(uy):.6g} m (must be < 0)",
            max_settlement_mm=min(uy) * 1000.0)
        umax = max(max(abs(x) for x in ux), max(abs(y) for y in uy))
        add("magnitude_sane", U_MIN <= umax <= U_MAX,
            f"max |u| = {umax:.6g} m (plausible band {U_MIN:g}..{U_MAX:g} m)",
            triplet="dt_hstar_010", max_abs_u=umax)
    else:
        add("crest_downstream", False, "no 2-component displacement data on the dam body")

    # 5 — group order (foundation must be the lower group)
    cy = _group_centroid_y(job, coords) if coords else {}
    if 1 in cy and 2 in cy:
        add("group_order", cy[1] < cy[2],
            f"centroid y: group1={cy[1]:.3g}, group2={cy[2]:.3g} "
            "(group1 must be the foundation, i.e. lower)",
            triplet="dt_hstar_006", g1_y=cy[1], g2_y=cy[2])
    else:
        info("group_order", f"could not derive group centroids (groups seen: {sorted(cy)})")

    # 6 — global equilibrium, if nodal forces were written
    forces = [b for b in blocks if "FORCE" in b["type"].upper() or b["type"].lower().startswith("tofor")]
    if forces:
        d = forces[-1]["data"]
        sx = sum(v[0] for v in d.values() if len(v) >= 1)
        sy = sum(v[1] for v in d.values() if len(v) >= 2)
        scale = max(1.0, max((abs(v[1]) for v in d.values() if len(v) >= 2), default=1.0))
        add("global_equilibrium", abs(sx) / scale < 1e-4 and abs(sy) / scale < 1e-4,
            f"sum of nodal forces: Sx={sx:.4g}, Sy={sy:.4g} (scale {scale:.4g})",
            sum_fx=sx, sum_fy=sy)
    else:
        info("global_equilibrium", "no nodal-force block (gid_f off) — check skipped")

    return _wrap(job, checks)


def _wrap(job: Path, checks: list) -> dict:
    failed = [c["id"] for c in checks if c["status"] == "fail"]
    return {
        "package": "hstar-gravdam-static-2block",
        "case_family": "gravdam_static_2block",
        "job_dir": str(job),
        "status": "PASS" if not failed else "FAIL",
        "failed_checks": failed,
        # Explicit, so no report can claim a benchmark that does not exist.
        "validator": None,
        "validation_basis": "harness/gate.py:physics_gate + family physical checks "
                            "(no registered benchmark validator for this family — dt_hstar_009)",
        "checks": checks,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job_dir")
    ap.add_argument("--height", type=float, default=100.0)
    ap.add_argument("--water-level", type=float, default=None,
                    help="default: same as --height (full reservoir)")
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    job = Path(a.job_dir).resolve()
    job.mkdir(parents=True, exist_ok=True)
    wl = a.water_level if a.water_level is not None else a.height

    stage_log: list = []
    if not a.score_only:
        if not stage_mesh(job, a.height, stage_log):
            print(json.dumps({"status": "ERROR", "stage": "s1_mesh_generation",
                              "log": stage_log}, indent=2))
            return 2
        if not stage_solve(job, wl, stage_log):
            print(json.dumps({"status": "ERROR", "stage": "s4_solve",
                              "log": stage_log}, indent=2))
            return 2

    report = score(job)
    report["stages"] = stage_log
    (job / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding="utf-8")

    if a.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for c in report["checks"]:
            print(f"[{c['status'].upper():4}] {c['id']}: {c['detail']}"
                  + (f"  (triplet {c['triplet']})" if c.get("triplet") and c["status"] == "fail" else ""))
        print(f"\n{report['status']} — {report['validation_basis']}")
        print(f"written: {job / 'result.json'}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
