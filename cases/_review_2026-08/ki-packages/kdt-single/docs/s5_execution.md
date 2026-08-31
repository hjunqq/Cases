# Stage s5 — Running HSTAR

## Purpose
Execute the solver on a prepared case, safely and reproducibly.

## Inputs
- A prepared case directory (stages s1–s4)
- The `hstar` binary from stage s0

## Outputs
- ~35 files in the working directory, of which the useful ones are collected:
  `1.chk`, `1.flavia.res`, `1.flavia.msh`, `1.gpv`, `1.act`, `1.opw`, `1.oew`,
  `1.ogw`, `1.ojw`, `1.ctr`, `1.gdm`, `1.bar`, `1.rtt`, `1.oit`, `1.oip`,
  `run.log`, plus `run_report.json`

## Procedure
```bash
python3 tools/run_hstar.py --case case1 --output_dir out1
python3 tools/run_hstar.py --case case1 --output_dir out2 --restart 1 --runblks 2
python3 tools/run_hstar.py --case case1 --output_dir out3 --threads 8 --timeout 3600
```

### The execution contract
HSTAR takes **no command-line arguments** — the `GETARG` block at
`Fem.f90:96-101` is commented out. It opens `inp` relative to the current
working directory and then every data file relative to CWD as well:

```
inp record 1   'input'                heading
inp record 2   restart relis sysrelis ADINA Uopt_R gamamax
inp record 3   'input'                heading
inp record 4   probn                  the problem-name prefix
inp record 5   runblks                how many run blocks to execute (<= nblks)
```

So the only way to select a case is to `cd` into it with `probn = 1`.
`run_hstar.py` therefore:

1. **copies** the whole case directory to a fresh temp workspace;
2. **swaps in** any `--override` files;
3. **modifies** only the specific values in `inp` (restart flag, runblks) by
   string replacement;
4. **runs** the binary with `cwd = workspace`;
5. **collects** the non-empty outputs into `--output_dir`.

Nothing is regenerated from a Python dict, and no run ever reuses a directory.

`restart` values: `0` new, `1` restart from `*.rtt`, `2` re-post-process an
existing state. `runblks < nblks` stops the run early on purpose — useful for
checking that block 1 of a staged construction is right before paying for the
rest.

Threading: HSTAR uses MKL's threaded PARDISO and some OpenMP loops.
`--threads N` sets both `OMP_NUM_THREADS` and `MKL_NUM_THREADS`.

## Verification
`run_hstar.py` post-checks:
- exit status 0;
- `1.chk` exists — if it does not, HSTAR never got past `global_data()` and the
  `.glb` record sequence is wrong (`dt_004`);
- the log and `1.chk` carry no failure marker (`forrtl: severe`,
  `Fortran runtime error`, `SINGULAR`, `PARDISO error`, `insufficient virtual
  memory`);
- at least one result file was written.

Useful lines that `1.chk` prints on every run, before the factorisation:
```
 No. of equations        =        144
 Max half band width     =         18
 length half stiff matrix=       1830
```
These predict the cost of `PROFILE` exactly, from a short trial run.

## Traps
- **Exit status 0 does not mean converged.** When `miter` is reached without
  meeting `toler_force`, HSTAR prints `not converged for checki` to `1.chk` and
  moves on to the next load step. The manual is explicit about this. Always
  parse `1.chk` (`dt_026`).
- **Stale files.** `*.rtt`, `*.oit`, `*.oip`, `*.ini`, `*.stf`, `*.ctt` are all
  read back when the corresponding flag is set. Running twice in one directory
  mixes generations (`dt_028`).
- Passing the case as an argument does nothing (`dt_001`).
- `PROFILE` on a large 3-D model exhausts memory; switch to `PARDISO`
  (`dt_032`).
- The `.chk` file is opened with `status` defaulting to unknown, so it is
  overwritten each run — copy it out before re-running.

## Example
Verified 2026-08-26 on the shipped `lame_cylinder` case, Linux ifx build:
```
 time: 10:53:34
 NPOIN  81 81 64 2 1 1 0 GIDR ...
 TYPE_PROBLEM  Q PROFILE LOAD 5 ...
 No. of equations        =        144
 istep= 1 iiter= 2  resid= 4.873E-20  retot= 8.2349E+08  ratio1= 7.693E-15
 ***********RESTART FILE IS UPDATED!*******
```
Exit status 0; `DISPLACEMENT` node 1 = `0.50245203E-05` m, bit-identical to the
stored reference result for that case.
