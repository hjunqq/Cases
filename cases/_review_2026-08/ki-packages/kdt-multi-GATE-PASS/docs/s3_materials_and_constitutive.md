# s3 — Materials and constitutive models

## Purpose

Populate `<probn>.mat` and choose the constitutive model per element group.

## Inputs

Elastic constants, strength parameters, thermal properties, beam sections. From the design
report or site investigation where they exist; otherwise from the regional default table
below, explicitly marked `assumed`.

## Outputs

`<probn>.mat`, plus (when a default was used) an `assumed_parameters.json` side-car in the
case directory.

## Procedure

### File structure (`material_set`, `Material.f90:240-1000`)

```
text                                  header
nscurve                               number of stress-strain curves
  per curve:  npoints type_curve
              strain_curve(1:npoints)
              stress_curve(1:npoints)
nline                                 how many comment lines follow
  nline x comment lines               POSITIONAL -- deleting one shifts the file
text
mmats                                 number of material RECORDS
  per record:
    text                              "material_serial  <i>"
    property name imat                MECHANICAL | HEAT | GEOMETRY
    (MECHANICAL) nphase
      per phase: phase                SOLID | FLUID | AIR | OIL
        (SOLID) model density ratio thickness e nu alfa icreep kind_wt jliqu
                iE iNu density_w
                <model-specific sub-records>
        (FLUID) density ratio bulkw
                permiability(1:ndimn)
    (HEAT)     alfa(1:ndimn) source_curve place_curve pipe_cooling
               ialfa
               [water_curve time_cooling gap_cooling eata bcooltime] if pipe_cooling/=0
    (GEOMETRY) Aera J Iy Iz
```

The 10 tokens of the SOLID line, in read order (`Material.f90:289`):

| token | name | unit | meaning |
|---|---|---|---|
| 1 | `model` | – | constitutive-model keyword |
| 2 | `density` | kg m⁻³ | mass density |
| 3 | `ratio` | – | mass-participation scaling |
| 4 | `thickness` | m | 2-D out-of-plane thickness |
| 5 | `e` | Pa | Young's modulus |
| 6 | `nu` | – | Poisson's ratio |
| 7 | `alfa` | °C⁻¹ | linear thermal expansion |
| 8 | `icreep` | flag | creep sub-record follows when ≠ 0 |
| 9 | `kind_wt` | flag | wetting-deformation sub-record |
| 10 | `jliqu` | flag | liquefaction model |

### Model keywords (`case(...)`, `Material.f90:435-920`)

| keyword | family | what it needs beyond the SOLID line |
|---|---|---|
| `ELASTIC_ISOTROPIC` | linear elastic | nothing |
| `ELASTIC_FRICTIONLESS` | elastic, no shear transfer | – |
| `ELASTIC_SPRING` | discrete spring | spring constants `a`, … |
| `ELASTIC_EP` | piecewise elastic-plastic | `np`, `p(:)`, `Es(:)` |
| `PLANE_LOWFT` | low-tension plane (smeared crack) | tensile limits ft₁, ft₂ |
| `CLASSICALEP` | classical plasticity | `criteria sigm0 hardening`; MC/DP also `frict_angle dilan_angle` (DEGREES) |
| `CAMCLAY` | critical state | `Pc lamda Mg Mf D0 D1 gaama` |
| `SoilPZ` / `SandPZ` / `ClayPZ` | Pastor-Zienkiewicz generalized plasticity | model-specific block |
| `CONCRETE` | Ghrib & Tinawi (1995) damage | four damage parameters + `icr` |
| `DUNCANCHANG` | hyperbolic non-linear elastic | `model` (EV/CR/EB), `Cohes phi K n Rf`, `Kb m dphi`, `Pa P0`, `Nur Kur` |
| `GOODMAN` | joint / interface | joint model name, `kn ks` (Pa m⁻¹), cohesion (Pa), friction (deg), tensile strength (Pa) |
| `STEEL_EP` | steel stress-strain curve | `np csigma`, `sig(:)`, `Es(:)` |
| `STEEL_SP` | steel spatial spring | `kxyz ktheta1 ktheta2` |

`CLASSICALEP` criteria: `MC` (Mohr-Coulomb), `DP` (Drucker-Prager), `VM` (von Mises),
`TC` (Tresca), `MCC`, `DPC` (cap variants), `MCJOINT` (thin-layer joint).

### Regional / material defaults (physically informed starting points, not calibration)

Harvested from the shipped dam cases; use with `--preset`, which writes them into
`assumed_parameters.json`.

| preset | E (Pa) | ν | ρ (kg m⁻³) | α (°C⁻¹) | provenance |
|---|---|---|---|---|---|
| `concrete_dam` | 2.4e10 | 0.167 | 2400 | 1e-5 | `cases/static` group 1 |
| `concrete_rcc` | 2.2e10 | 0.20 | 2400 | 1e-5 | roller-compacted concrete |
| `rock_foundation` | 1.5e10 | 0.25 | 2650 | 8e-6 | `cases/static` groups 2/3 range |
| `weak_rock` | 5.0e9 | 0.30 | 2500 | 8e-6 | weathered / faulted zone |
| `rockfill` | 1.0e8 | 0.30 | 2100 | 0 | use `DUNCANCHANG` in practice |
| `steel_rebar` | 2.1e11 | 0.30 | 7850 | 1.2e-5 | HRB400 class |

## Verification

```bash
python3 tools/build_material_file.py --case /tmp/c --describe
python3 tools/build_material_file.py --case /tmp/c --list-presets
python3 tools/build_material_file.py --case /tmp/c --set 1 e=2.0e10 nu=0.2
```

`set_solid` refuses ν outside (−1, 0.5), E outside 1e3…1e13 Pa, and ρ outside 1…2e4
kg m⁻³ — the three ranges that catch a MPa/Pa or t/m³/kg/m³ slip.

Physical cross-check after a run: for a laterally confined body the ratio σ_xx/σ_yy must be
K₀ = ν/(1−ν). `validate_results.py --benchmark confined_selfweight_column` tests exactly
that and it matched to 0.0 % on this KI's validation run.

## Traps

- **Angles are in DEGREES in `.mat`** and converted internally. Entering radians gives a
  friction angle of ~0.6° and a structure that fails immediately.
- **A comment line in the `.mat` header block can start with a model keyword.** Every
  shipped `.mat` contains a line like `CAMCLAY    :Pc, lamda, Mg, Mf, D0, D1,gaama`. A
  parser that matches on the keyword alone finds phantom material records; `read_mat`
  additionally requires six parseable numbers after the keyword.
- **`.mat` files carry GBK-encoded Chinese comments.** Reading them as UTF-8 raises
  `UnicodeDecodeError`. All KI tools use `encoding="latin-1"` (byte-transparent).
- **`mmats` can exceed `nmats`.** `.glb` declares how many materials the groups reference;
  `.mat` may hold more records (alternates for staged material swapping via
  `MATNO_PROCESS`).
- **`e` in MPa is the single most damaging unit error** — HSTAR range-checks nothing, the
  run converges, and every displacement is 10⁶ times too large. See triplet `dt_006`.

## Example

```bash
$ python3 tools/build_material_file.py --case /tmp/c --preset 1 concrete_dam
{ "record": 1, "now": {"model": "ELASTIC_ISOTROPIC", "e": "2.4000E+10", "nu": "1.6700E-01",
                       "density": "2.4000E+03", ...},
  "assumed": [{"preset": "concrete_dam", "status": "ASSUMED -- physically informed default,
               not measured", "provenance": "mass concrete, from cases/static group 1"}],
  "side_car": "/tmp/c/assumed_parameters.json" }
```
