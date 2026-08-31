# s1 — Case layout, `inp`, and the master control file `<probn>.glb`

## Purpose

Understand how HSTAR finds its inputs, and how the one control file selects the analysis.

## Inputs

A **case directory**: one flat directory containing `inp` and ~35 files named
`<probn>.<ext>`. Copy one from the template catalogue (`tools/_hstar_io.TEMPLATES`); never
create one from scratch.

## Outputs

A prepared case directory whose `.glb` counts agree with its `.cor`/`.ele`.

## Procedure

### 1. `inp` — the only thing HSTAR looks for by a fixed name

HSTAR takes **no command-line arguments**. `Fem.f90:92-97, 177`:

```
line 1  text                                        header, content ignored, MUST EXIST
line 2  restart relis sysrelis ADINA Uopt_R gamamax
line 3  text                                        header
line 4  probn                                       case base name
line 5  runblks                                     how many load blocks to execute
```

* `restart` — 0 fresh, 1 resume from `<probn>.rtt`, 2 post-process an existing state and stop
* `relis` — 1 turns on FORM reliability
* `sysrelis` — >0 turns on system reliability
* `ADINA` — ADINA-format export switch
* `Uopt_R` — 1 activates the coordinate-modification pass (reads `<probn>.vcor`)
* `gamamax` — equivalent-linearisation switch

Because the working directory *is* the interface, `tools/run_hstar.py` always copies the case
into a workspace and runs with `cwd=workspace`.

### 2. `<probn>.glb` — the master control file

Read by `global_data` (`Global.f90:628-1100`). It is free-format list-directed, strictly
ordered, with a header/echo line before each value record. Several records are
**conditional** — they exist only when a switch above them is non-zero:

| Conditional record | Appears when |
|---|---|
| `valv1 valv2` | `rmesh /= 0` |
| `ndefault(1:abs(rmesh))` | `rmesh /= 0` |
| `type_nl_layer1 type_nl_layer2 solver_iter` | `nlayer == 2` |
| `nfreeflownode` + node list | `nflow /= 0` |

`tools/_hstar_io.GlbDoc` replays this exact sequence, so every named scalar resolves to a
(line, token) position in the file and can be edited without disturbing anything else.

The record sequence, in order, is tabulated in `input_preparation.md` §3.1.

### 3. The key switches

| Switch | Meaning |
|---|---|
| `npoin npoinb nelem ndimn nmats ngroup` | mesh and material counts — **must** match `.cor`/`.ele` |
| `outplot` | `GIDR` (rewrite ASCII), `GIDA` (append), `GIDL` (binary via gidpost), `COSMOSR/A` |
| `kstab` | REAL; non-zero calls `safety_factor` |
| `nblks` | number of load blocks; `.pre`, `.man` and `.sol` each carry one record group per block |
| `type_problem` | `Q` quasi-static, `F`/`D` dynamic, `S` transient field, `E` modal, `W` frequency domain |
| `type_solver` | `PARDISO`, `PROFILE`, `JPCG`, `PBCG`, `EXPLICIT` |
| `type_load` | `LOAD`, `LOAD2`, `ARCLENGTH`, `DISCONTROL`, `MAT_DE` |
| `mdofn` / `lmdofn` | DOF slots and their compressed numbering (see s5) |
| `nmass nsmat nhmat nqmat` and `ntsmat nthmat` | **matrix re-formation intervals**, not material ids (see s5) |
| `Bparameter` / `balgor` | inversion route (see s9) |
| `block_stab`, `relis`, `sysrelis` | stability / reliability routes (see s9) |

## Verification

```bash
python3 tools/build_case_from_template.py --list          # which templates exist
python3 tools/build_case_from_template.py --template static --dest /tmp/c --overwrite
python3 tools/build_mesh_files.py --case /tmp/c --check    # counts vs .glb
python3 tools/build_analysis_control.py --case /tmp/c --describe
```

`check_consistent()` (called by both `build_case_from_template` and `run_hstar`) fails the
case when `.cor`/`.ele` record counts disagree with `npoin`/`nelem`.

## Traps

- **Header lines are positional placeholders**, not comments. `read(gunit,*)text` consumes a
  whole record. Deleting one shifts every subsequent record by one, and list-directed input
  will happily read the next line's numbers into the wrong variables — no error.
- **A SHORT value line is worse than a missing one.** List-directed input continues onto the
  next record until it has all its items, silently swallowing the following line.
- **Fortran repeat counts are legal input**: `337*0`, `4*1`, `1000*-2` all appear in
  `cases/train05_slope_stability/1.glb`. A tokeniser that splits on whitespace and calls
  `int()` breaks on them. `_hstar_io.tokens()` expands them.
- **Quoted keywords are legal**: `'Q','PARDISO','MAT_DE',4,0,...`. Commas are separators.
- **Files are CRLF.** A character keyword that lands at end-of-line absorbs the `\r` and
  stops matching (`"PARDISO\r" /= 'PARDISO'`). `GlbDoc.set` refuses to create that situation.
- **`nblks` is not `runblks`.** `.glb` declares how many blocks the model has; `inp` line 5
  says how many to run now. Increasing `nblks` without appending record groups to `.pre`,
  `.man` and `.sol` is the most common `forrtl: severe (24)`.

## Example

```bash
$ python3 tools/build_case_from_template.py --template static --dest /tmp/c --runblks 2
{ "probn": "1", "npoin": 462, "nelem": 410, "ndimn": 2, "ngroup": 3, "nblks": 2,
  "type_problem": "Q", "type_solver": "PARDISO", "ok": true }
```
