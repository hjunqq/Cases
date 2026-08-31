> **MANDATORY EXECUTION POLICY** — READ BEFORE PROCEEDING
>
> You MUST run the **actual HSTAR solver binary** described in this document.
> If the solve fails to launch or crashes, you MUST:
> 1. Check `diagnostics/triplets.yaml` for a matching `symptom.error_pattern`
> 2. Apply the fix in that triplet's `remedy` section
> 3. If still failing, report the error with the full `run.log` tail
>
> You MUST NOT substitute an analytical formula, a beam/gravity hand-calculation,
> or any simplified stress estimate in place of the real solve. A gravity-dam
> stress field is not reproducible by a closed-form expression.
>
> You MUST NOT produce an Abaqus `.inp`, `.vtu`-as-input, or any other
> non-HSTAR deck as a "fallback". This platform has exactly one solver.
>
> Before starting, run: `python3 preflight_check.py` (in this KI directory).
>
> **DEBUGGING PROTOCOL** — When something goes wrong, follow this order:
> 1. **Check triplets** — `diagnostics/triplets.yaml`
> 2. **Read the deck the solver actually got** — `1.glb` / `1.LOA` / `1.man` in the job dir,
>    plus `config.json` which `run_pipeline` writes *after* resolving `__MESH__`,
>    water edges and curve indices. This is the ground truth, not your input JSON.
> 3. **Find a working example** — `fem-chat/cases/`, `fem-chat/workspace/`, or the
>    templates under `fem-chat/skills/templates/`
> 4. **Fix the tool** — `skills/generator.py` / `skills/run_pipeline.py`
>
> Do NOT write custom debug scripts that re-implement the pipeline. Do NOT spawn
> `./hstar` directly (see `hstar_mkl_soname_missing`).

# HSTAR `gravdam_static_2block` — Knowledge Infrastructure

**Package**: `hstar-gravdam-static-2block` v0.1.0 (experimental — KISS-format trial)
**Model**: HSTAR (YL mainline), Fortran structural FEM
**Case family**: `gravdam_static_2block` — 2D gravity dam, 2-stage construction, hydrostatic load
**Created**: 2026-08-25 · `fem-chat/docs/research/kiss-trial-pkg/`
**Validation status**: `run_tested` (see `docs/trial-log.md` in the parent report)
**Stats**: 1 preflight tool | 1 run-and-score tool | 13 diagnostic triplets | 12 hazards

---

## Overview

Plane-strain (2D) linear-elastic static analysis of a concrete gravity dam on a
conforming rock foundation, loaded by self-weight applied in two construction
stages (foundation first, then dam body) plus a linearly-varying hydrostatic
pressure on the vertical upstream face.

**What this family answers**: crest displacement under full reservoir, settlement
of the dam body, the stress field in dam and foundation, and (since 2026-08-25)
nodal reactions via `gid_f`/`tofor` which give a free global-equilibrium self-check.

**What it does not answer**: see `dag.yaml → boundary.scope_out`. In short: no
uplift, no joints, no cracking, no seepage coupling, no thermal, no dynamics.

---

## Installation / environment

Nothing to build. The solver is a prebuilt binary:

```
/home/huijun/HSTAR_Next/hstarYLOrig/HSTAR/x64/Release/hstar
```

Override with `HSTAR_EXE` if it moved. It links against Intel oneAPI MKL with
`.so.2` sonames; the `mkl/latest` symlink has rolled forward to versions that no
longer ship those, so the path is **discovered at runtime**, never hardcoded:

```bash
python3 /home/huijun/HSTAR_Next/fem-chat/skills/intel_runtime.py -v
```

`run_pipeline.py` imports `intel_runtime` and injects `LD_LIBRARY_PATH`/`PATH`
before spawning the binary. **This is the only supported launch path.**

Python: 3.10+ (the codebase uses `X | Y` type syntax). No third-party packages
are required for the solve path; `numpy` is only needed by some post-processors.

---

## Stages

| stage id | what it does | tool | produces |
|---|---|---|---|
| `s1_mesh_generation` | parametric dam + conforming foundation mesh | `skills/gen_gravdam.py` | `1.cor`, `1.ele`, `1.flavia.msh`, `gravdam_meta.json` |
| `s2_config_assembly` | template + overrides → effective config | `skills/quick_analysis.py` | `config.json` (written by the pipeline, post-resolution) |
| `s3_deck_generation` | config → HSTAR input deck | `skills/generator.py` (called by pipeline) | `1.glb`, `1.mat`, `1.LOA`, `1.man`, `1.fix` … |
| `s4_solve` | run the binary with MKL paths injected | `skills/run_pipeline.py` | `1.flavia.res`, `1.chk`, `run.log` |
| `s5_postprocess` | parse + convert | `run_pipeline` Step 4, `tools/flavia_to_vtu.py` | per-block ranges, `result_b*.vtp` |
| `s6_scoring` | gate + physical self-check | `run_and_score.py` (this package) | `result.json` |

---

## Procedure

### 1. Preflight (mandatory)

```bash
python3 <this_dir>/preflight_check.py --json
```

Exit 0 = go. Exit 1 = a `fail` check; read its `remedy` field, it names the triplet.

### 2. Mesh

```bash
python3 /home/huijun/HSTAR_Next/fem-chat/skills/gen_gravdam.py <job_dir> \
    --height 100 --crest-width 8 --ds-slope 0.7
```

Geometry contract (violating it makes the whole run meaningless):

- **Upstream face vertical** (`--us-slope 0`, the default). Water side, −x.
- **Downstream face single slope** 1:0.7. **Not symmetric** — a symmetric trapezoid
  is a teaching demo, not a gravity dam (`dam_templates.py scale` produces one; do not use it).
- Base width = crest + ds_slope × height.
- **Conforming mesh**: foundation (y<0) and dam (y≥0) share the y=0 interface nodes.
  No contact element. Foundation extends ≈1.5 H sideways and ≈0.75 H down.
- Element group 1 = **foundation**, group 2 = **dam body**. This order is load-bearing;
  reversing it silently swaps the two materials (`gravdam_group_order_reversed`).
- `gravdam_meta.json` carries `upstream_face_edges`, already oriented so that the
  n1→n2 normal points **+x, into the dam**.

### 3. Run

```bash
python3 /home/huijun/HSTAR_Next/fem-chat/skills/quick_analysis.py <job_dir> \
    gravdam_static_2block '<overrides_json>'
```

The template already sets everything below; overrides only change materials /
water level / mesh-dependent counts.

| key | value | why |
|---|---|---|
| `type_problem` | `"Q"` | static is **Q**, not F |
| `solver` | `"PROFILE"` | auto-switches to PARDISO above npoin=5000 — fine for this family |
| `nblks` | `2` | two construction stages |
| `groups` | `[Foundation matno=1, Dam matno=2]` | **order = mesh group order** |
| `blocks.appear` | `[[1,0],[1,1]]` | stage 1: foundation only; stage 2: + dam |
| `blocks.gravity` | `[9.81, 0, -1, 0, -1]` | 2D, Y downward; length must be `1+2*ndimn` |
| `boundary` | `bottom_fix_uy`, `sides_fix_ux` | dam/retaining-wall preset. **Never stack these on `node_fixes`** |
| `water_pressure.use_meta_edges` | `true` | resolves to `gravdam_meta.json` edges. **Never let it auto-detect x_min** |
| `water_pressure.water_level` | `50.0` (override to H for full reservoir) | metres above y=0 |
| `water_pressure.block` | `2` | water appears in construction stage 2 only |

One job dir = **one** analysis. A second run overwrites `1.flavia.res`
(`hstar_results_clobbered`).

### 4. Score

```bash
python3 <this_dir>/run_and_score.py <job_dir> --json
```

Writes `<job_dir>/result.json`. It resumes by artifact presence: mesh present →
skip s1; `1.glb` + `1.flavia.res` present → skip the solve and score only.

---

## Verification — what "correct" looks like

Ordered from cheapest to most informative. `run_and_score.py` automates 1–4.

1. **Gate** (`harness/gate.py:physics_gate`): `1.flavia.res` exists, `run.log` has no
   `forrtl`/`sigsegv`/`severe`, values finite, not all-zero. Coarse by design.
2. **Crest moves downstream**: max `ux` in block 2 is **positive** (+x).
   Negative ⇒ `hstar_water_edges_reversed`.
3. **Dam settles**: min `uy` in block 2 is **negative**, magnitude of order
   1–10 mm for an H≈100 m concrete dam on rock. Exactly 0 in stage 2 ⇒ gravity
   or `appear` is wrong.
4. **Water actually loaded**: run.log must contain the
   `Using N dam upstream-face edges from gravdam_meta.json` line with **N > 0**.
   N = 0 or the line absent ⇒ `hstar_water_edges_silently_empty` — the run still
   succeeds and still settles under gravity, so nothing else catches it.
5. **Global equilibrium** (if `gid_f` on): Σ of all nodal forces ≈ 0.
   Measured on a reference gravdam static run: Σx = 0.000E+00, Σy = −2.4 N
   (relative magnitude 1e−7).
6. **Two stages present**: `1.flavia.res` must contain results for **2** steps.
   Only 1 ⇒ `appear` / `increments` collapsed to one block.

**There is no registered analytical validator for this family**
(`docs/benchmark-catalog.md` line 13 says `(no validator)`). The nearest one,
`mini_gravdam`, is keyed to npoin=46 and returns NOT_APPLICABLE on any other mesh.
So checks 2–6 above *are* the validation. Do not claim "validated against a
benchmark" for this family.

---

## Where the knowledge outside this package lives

Deliberately listed, because this package does not duplicate it:

- `fem-chat/CLAUDE.md` — routing between `quick_analysis` and `run_workflow`
- `fem-chat/docs/references/mesh-and-geometry.md` — dam geometry, FSI/modal variants
- `fem-chat/docs/references/loads-and-constraints.md` — non-standard BCs
- `fem-chat/docs/references/error-recovery.md` — the 7 upstream Pattern IDs
  (this package's triplets `hstar_*` are 1:1 with them plus 6 more)
- `fem-chat/docs/capability-inventory.md` — solver-vs-generator gap audit
