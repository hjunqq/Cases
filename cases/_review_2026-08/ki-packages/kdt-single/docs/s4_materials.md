# Stage s4 — Materials and constitutive models

## Purpose
Assign a constitutive model and its parameters to every material id referenced
by an element group.

## Inputs
Material parameters in **strict SI**: Pa, kg/m³, m/s, °C, degrees, m²/day.
HSTAR converts nothing, checks nothing, and reports nothing when a value is
absurd.

## Outputs
`1.mat`, with a fixed 12-record preamble followed by one stanza per material.

## Procedure
```
' material property curves'
ncurve                 0 unless a property varies with a time curve
10                     number of comment records that follow
COMMENT  x10           free text, but exactly ten records
' nmats'
nmats
per material:
  '     material_serial   <imat>'
  '          MECHANICAL   SOLID  <imat>'     (or HEAT / GEOMETRY)
  nphase                                     1 solid only, 2 solid+fluid
  '               SOLID'
  MODEL density ratio thickness E nu alfa icreep i1 i2
  <model-specific extra records>
```

```bash
python3 tools/write_materials.py --case case1 \
  --mat "id=1;model=ELASTIC_ISOTROPIC;rho=2400;E=2.5e10;nu=0.2;alfa=1e-5"
python3 tools/write_materials.py --list-models
```

### Models `Material.f90` dispatches on
`PLANE_LOWFT`, `ELASTIC_ISOTROPIC`, `ELASTIC_FRICTIONLESS`, `ELASTIC_SPRING`,
`ELASTIC_EP`, `STEEL_EP`, `STEEL_SP`, `DUNCANCHANG`, `GOODMAN`, `CLASSICALEP`,
`CAMCLAY`, `CONCRETE`, `ClayPZ`, `SandPZ`, `SoilPZ`; plus the `FLUID` phase and
the `HEAT` and `GEOMETRY` property blocks.

| model | extra records, in read order |
|---|---|
| `ELASTIC_SPRING` | `a b c d l0` |
| `DUNCANCHANG` | `model c phi K n Rf Nur Kur P0 Pa`; then `G F Vtf` (EV/CR) or `Kb m dphi` (EB) |
| `GOODMAN` | `JANBU`; then `K1 n Kzz Rf phi Kzx pa gamaw c Ft`; then `Kzy` in 3-D |
| `CLASSICALEP` | `criteria sigma0 hardening` / `frict_angle dilan_angle` / `csigma0` / `cfrict cdilan`; plus `ft cft sigmat csigmat` when criteria=`MCJOINT` |
| `CONCRETE` | Ghrib–Tinawi damage set |
| `CAMCLAY`, `ClayPZ`, `SandPZ`, `SoilPZ`, `ELASTIC_EP`, `STEEL_*` | model-specific; the tool requires `extra=` and refuses to guess |

Criteria for `CLASSICALEP`: `MC`, `DP`, `TC`, `VM`, `MCJOINT`.

`FLUID` phase (when `nphase=2`): `density ratio bulkw`, then
`permeability(1:ndimn)` in m/s.

`'HEAT','SOLID'`: `a(1:3)  adiabatic_curve  placing_temperature_curve`, with
diffusivity in **m²/day**.

Creep and ageing (`icreep/=0`): `nr a b`, then `c(1:nr) d(1:nr) k(1:nr)`.
`E(t) = E0(1 − e^{−a t^b})` and
`C(t,τ) = Σᵢ (Cᵢ + Dᵢ τ^{−…})(1 − e^{−kᵢ(t−τ)})`.
`icreep=0` none, `2` both creep and ageing modulus, any other non-zero value
ageing modulus only.

## Verification
`write_materials.py` range-checks before writing:

| parameter | band | what a violation usually means |
|---|---|---|
| `rho` | 500 – 12000 kg/m³ | given in t/m³ or g/cm³ |
| `E` | 1e4 – 1e12 Pa | given in MPa or GPa |
| `nu` | −0.999 – 0.4999 | ν ≥ 0.5 makes the bulk modulus infinite |
| `alfa` | 0 – 1e-3 /°C | |
| `phi` | 0 – 60° | |
| `c` | 0 – 1e9 Pa | given in kPa/MPa |
| `a` | 1e-4 – 1 m²/day | given in m²/s — 86400× wrong |

After the run, `validate_results.py --model-size L` flags |u|max above L/10,
which is the downstream signature of an E unit error.

## Traps
- **E in MPa**: displacements 10⁶× too large, run converges normally
  (`dt_010`).
- **Diffusivity in m²/s with day-based steps**: field flattens in one step and
  looks converged (`dt_011`).
- `coefMpa` in `*.glb` (`1.0e6`) is a *display* scale for stress reporting, not
  an input conversion. Changing it changes the numbers you read out of `.gpv`
  without changing the physics.
- `ratio` in the common record is POROSITY, not Poisson's ratio — ν is the
  fifth numeric field.
- `thickness` matters only for plane problems; it multiplies the self-weight
  resultant, so a wrong value breaks the equilibrium check.
- A `GOODMAN` joint declared in the contact block with no `GOODMAN` material
  falls back to the continuum law and never opens (`dt_018`).

## Example
Mohr–Coulomb foundation plus elastic concrete, verified to write and parse:
```bash
python3 tools/write_materials.py --case dam1 \
  --mat "id=1;model=ELASTIC_ISOTROPIC;rho=2400;E=2.5e10;nu=0.167;alfa=1.0e-5" \
  --mat "id=2;model=CLASSICALEP;criteria=MC;rho=2650;E=1.0e10;nu=0.25;alfa=0;c=5.0e5;phi=45;psi=0"
```
