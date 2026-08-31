# s6 — Execution

## Purpose

Run the real `hstar` binary on a prepared case, reproducibly, and get a clean exit code.

## Inputs

A prepared case directory and the `hstar` executable.

## Outputs

A run directory holding `<probn>.flavia.res`, `<probn>.flavia.msh`, `<probn>.chk`,
`<probn>.rtt` and the auxiliary result files, plus `hstar_run.log`.

## Procedure

```bash
python3 tools/run_hstar.py --case /tmp/mycase --outdir /tmp/myrun
python3 tools/run_hstar.py --template train01_gravdam_static --outdir /tmp/r --omp-threads 8
HSTAR_BIN=/path/to/hstar python3 tools/run_hstar.py --case /tmp/mycase --outdir /tmp/myrun
```

`run_hstar.run()` implements the KDT execution-wrapper contract:

1. **Copy** the whole case (or template) directory into a workspace.
2. **Swap in** the user's files as whole files (`swap_files={"1.cor": "/path/to/new.cor"}`).
3. **Modify** only named values in control files, through `GlbDoc` / `set_inp` — never by
   regenerating a file from a Python dict.
4. **Validate before running**: `check_consistent()` compares `.cor`/`.ele` record counts
   with `npoin`/`nelem`. A mismatch returns `status: "input_error"` instead of a crash.
5. **Run** with `cwd=workspace`. HSTAR has no arguments; the working directory IS the
   interface, because it opens a file literally named `inp`.
6. **Feed stdin** (see below).
7. **Collect** the result files into `--outdir`.

### HSTAR still asks questions on stdin

Three interactive `read *` sites fire in ordinary runs:

| site | prompt | fires when |
|---|---|---|
| `Output.f90:3605` | `give me the vdimn,coef1 and coef2?` | `winit /= 0` and at least one active `U`-field group — i.e. most static cases that write an initial-stress `.inw` |
| `Fem.f90:378/385/417` | sub-mesh group and element lists | `submodel < 0` |
| `Global.f90:767` | `pause` | `ljdp /= 0` and `type_nl /= 5` |

With stdin closed, the first of these produces

```
forrtl: severe (24): end-of-file during read, unit -4, file /proc/<pid>/fd/0
```

**after a fully converged solution**. The results on disk are valid; only the exit code is
wrong. `run_hstar.default_stdin()` reads `winit` and `submodel` from the case's own `.glb`
and supplies `1 1.0 1.0` (no rescaling of the written initial stress) plus trailing blank
lines for any `pause`. Value answers come first so a blank line can never be consumed by a
value read.

Override with `--stdin-file` when `submodel < 0` requires explicit lists.

### Restart

`inp` line 2 field 1:

| `restart` | behaviour |
|---|---|
| 0 | fresh run |
| 1 | resume from `<probn>.rtt` at the last written block/increment |
| 2 | read `<probn>.rtt`, write the post-processing output, and STOP |

`nresta` in `.man` controls how often `.rtt` is written.

## Verification

```bash
python3 tools/run_hstar.py --case /tmp/mycase --outdir /tmp/myrun | tee run.json
python3 tools/parse_outputs.py --dir /tmp/myrun
python3 tools/validate_results.py --dir /tmp/myrun --case /tmp/mycase
```

A healthy run has `status: "ok"`, `returncode: 0`, a non-empty `1.flavia.res`, and
`converged: true` from `parse_outputs` (which reads the `ratio for residu norm` records out
of `.chk`).

## Traps

- **Never run in the case directory itself.** HSTAR overwrites `.rtt`, `.chk`, `.inw` and
  the result files in place, so a second run silently starts from the first run's restart
  state if `restart /= 0`. `run_hstar` always copies to a workspace.
- **`OMP_NUM_THREADS` and `ncpu` in `.sol` are different knobs.** `ncpu` is passed to
  PARDISO; `OMP_NUM_THREADS` governs the rest of MKL. `--omp-threads` sets the latter.
- **A non-zero exit code is not always a failed solve.** Check `log_tail` for
  `end-of-file during read … fd/0` first — that is the stdin prompt, not a numerical
  failure (`dt_001`).
- **`SIGSEGV` is almost always an input-count problem**, not a compiler bug: a `.glb` count
  that disagrees with `.cor`/`.ele`, a group declaring an element type whose auxiliary file
  is empty, or a node id out of range. Run `build_mesh_files --check` first.
- **Long runs write a very large `.chk`.** `noutf`/`noutn` control GiD output but the
  convergence log is written every iteration.

## Example

```bash
$ python3 tools/run_hstar.py --template column_selfweight --outdir /tmp/smoke
{
  "status": "ok", "returncode": 0, "binary_kind": "ELF",
  "wall_seconds": 0.04,
  "case_info": {"npoin": 6, "nelem": 2, "type_problem": "Q", "type_solver": "PROFILE"},
  "outputs_collected": ["1.chk", "1.flavia.msh", "1.flavia.res", "1.gpv", "1.rtt", ...]
}
```
