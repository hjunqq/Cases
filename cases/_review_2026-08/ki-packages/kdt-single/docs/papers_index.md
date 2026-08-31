# HSTAR — literature index

Gathered with the OpenAlex API directly: the toolkit's `openalex_search.py` /
`paper_fetch.py` / `push_papers_to_docs.py` are not installed on this host
(`/home/server/knowledge-dissection-toolkit` does not exist). Producer-side
copies live in `.dag_gen/`; these are the published copies.

Every `text_path` below was verified to exist on disk at publication time.

## Retrieved full text (23)

| DOI | year | role | serves | title |
|---|---|---|---|---|
| `10.1007/s00161-018-0672-4` | 2018 | benchmark | displacement, stress | Nonlinear finite element modeling of vibration control of plane rod-type structural member |
| `10.1007/s13349-020-00380-w` | 2020 | benchmark | temperature, stress | Dynamic structural health monitoring for concrete gravity dams based on the Bayesian infer |
| `10.1007/s40891-016-0076-0` | 2016 | benchmark | safety_factor | Analysis of a Nailed Soil Slope Using Limit Equilibrium and Finite Element Methods |
| `10.1007/s40996-021-00613-y` | 2021 | benchmark | pore_pressure | An Investigation on performance of the cut off wall and numerical analysis of seepage and  |
| `10.1016/j.asoc.2016.12.014` | 2016 | benchmark | displacement | Artificial neural networks for vibration based inverse parametric identifications: A revie |
| `10.1016/j.engstruct.2019.05.072` | 2019 | benchmark | temperature, stress | Concrete gravity dams model parameters updating using static measurements |
| `10.17577/ijertv8is080168` | 2019 | benchmark | pore_pressure | Analysis of Seepage through Earth Dams with Internal Core |
| `10.47260/jesge/1118` | 2020 | benchmark | displacement | Geophysical Methods and their Applications in Dam Safety Monitoring |
| `10.1007/s10706-005-5180-1` | 2006 | calibration | displacement | Settlement behaviour of a concrete faced rock-fill dam |
| `10.1002/nag.2923` | 2019 | definition | pore_pressure, displacement | Low‐order stabilized finite element for the full Biot formulation in soil mechanics at fin |
| `10.1002/nag.2934` | 2019 | definition | acceleration, displacement | Development of a GPGPU‐parallelized hybrid finite‐discrete element method for modeling roc |
| `10.1002/nme.1620360104` | 1993 | definition | joint_stress, displacement | On the numerical integration of interface elements |
| `10.1007/s10064-022-02885-8` | 2022 | definition | joint_stress, displacement | Using PFC2D to simulate the shear behaviour of joints in hard crystalline rock |
| `10.1007/s10518-020-00980-3` | 2020 | definition | damage, stress | Numerical simulation of the seismic response and soil–structure interaction for a monitore |
| `10.1016/j.cemconres.2019.05.015` | 2019 | definition | temperature | Properties of early-age concrete relevant to cracking in massive concrete |
| `10.1016/j.compgeo.2015.04.016` | 2015 | definition | joint_stress, displacement | 3D zero-thickness coupled interface finite element: Formulation and application |
| `10.1016/j.compgeo.2018.04.002` | 2018 | definition | pore_pressure, displacement | Coupled effective stress analysis of insertion problems in geotechnics with the Particle F |
| `10.1016/j.engfracmech.2015.12.028` | 2016 | definition | damage, stress | Modeling tensile crack propagation in concrete gravity dams via crack-path-field and strai |
| `10.1061/(asce)gt.1943-5606.0000060` | 2009 | definition | safety_factor | Probabilistic Analysis of Circular Tunnels in Homogeneous Soil Using Response Surface Meth |
| `10.15623/ijret.2012.0101001` | 2012 | definition | safety_factor | UNCERTAINTY MODELLING AND LIMIT STATE RELIABILITY OF TUNNEL SUPPORTS UNDER SEISMIC EFFECTS |
| `10.1016/j.envsoft.2012.09.011` | 2012 | threshold_convention | displacement, temperature | Characterising performance of environmental models |
| `10.5194/adgeo-5-89-2005` | 2005 | threshold_convention | displacement, temperature | Comparison of different efficiency criteria for hydrological model assessment |
| `10.5194/hess-23-4323-2019` | 2019 | threshold_convention | displacement, temperature | Technical note: Inherent benchmark or not? Comparing Nash–Sutcliffe and Kling–Gupta effici |

## Coverage by comparing_variable

| variable | papers |
|---|---|
| acceleration | 1 |
| damage | 2 |
| displacement | 13 |
| joint_stress | 3 |
| pore_pressure | 4 |
| safety_factor | 3 |
| stress | 5 |
| temperature | 6 |

## Recorded but unreadable (40)

OpenAlex lists an OA location for each of these, but the publisher returned
403 or a non-text landing page. They are recorded, not invented: `text_path`
is null and no content from them is cited anywhere in this KI.

| DOI | year | role | title |
|---|---|---|---|
| `10.1002/0470091355.ecm026` | 2004 | benchmark | Models and Finite Elements for Thin‐Walled Structures |
| `10.1002/nag.3476` | 2022 | definition | Inspection of two sophisticated models for sand based on generalized plasticity: Monotonic |
| `10.1002/nag.645` | 2007 | definition | Effective stress concept in unsaturated soils: Clarification and validation of a unified f |
| `10.1002/stc.2074` | 2017 | calibration | A statistical model of deformation during the construction of a concrete face rockfill dam |
| `10.1002/uog.5256` | 2008 | definition | Reliability, repeatability and reproducibility: analysis of measurement errors in continuo |
| `10.1007/s10346-011-0303-7` | 2011 | benchmark | Evaluation of slope stability by finite element method using observed displacement of land |
| `10.1016/j.apm.2010.03.019` | 2010 | benchmark | Non-linear seismic response of concrete gravity dams to near-fault ground motions includin |
| `10.1016/j.apm.2017.09.017` | 2017 | definition | A hybrid self-adaptive conjugate first order reliability method for robust structural reli |
| `10.1016/j.aqpro.2015.02.110` | 2015 | benchmark | Seepage and Stability Analyses of Earth Dam Using Finite Element Method |
| `10.1016/j.cam.2016.06.003` | 2016 | definition | A nonconforming finite element method for the Biot’s consolidation model in poroelasticity |
| `10.1016/j.compgeo.2021.104364` | 2021 | benchmark | A direct time-domain procedure for the seismic analysis of dam–foundation–reservoir system |
| `10.1016/j.compgeo.2024.106593` | 2024 | benchmark | An efficient strength reduction method for finite element slope stability analysis |
| `10.1016/j.csite.2024.105456` | 2024 | benchmark | Optimization of cooling system parameters with temperature field of mass concrete during h |
| `10.1016/j.engstruct.2015.01.047` | 2015 | benchmark | Thermal displacements of concrete dams: Accounting for water temperature in statistical mo |
| `10.1016/j.ijsolstr.2005.05.038` | 2005 | definition | An energy release rate-based plastic-damage model for concrete |
| `10.1016/j.ijsolstr.2012.06.009` | 2012 | benchmark | Shape sensing of 3D frame structures using an inverse Finite Element Method |
| `10.1016/j.ijsolstr.2017.03.005` | 2017 | definition | Fractional order plasticity model for granular soils subjected to monotonic triaxial compr |
| `10.1016/j.ijsolstr.2018.02.004` | 2018 | definition | A novel positive/negative projection in energy norm for the damage modeling of quasi-britt |
| `10.1016/j.jrmge.2013.12.003` | 2013 | definition | Discrete modeling of rock joints with a smooth-joint contact model |
| `10.1016/j.jrmge.2018.09.002` | 2018 | benchmark | Finite element analyses of slope stability problems using non-associated plasticity |
| `10.1016/j.jrmge.2020.05.011` | 2020 | benchmark | Improved prediction of slope stability using a hybrid stacking ensemble method based on fi |
| `10.1016/j.sandf.2021.09.007` | 2021 | calibration | Strength and stiffness parameters for hardening soil model of rockfill materials |
| `10.1016/j.sandf.2021.10.004` | 2021 | calibration | 3D analysis of the 174-m high Quxue asphalt-core rockfill dam in a narrow canyon |
| `10.1016/j.wse.2017.06.004` | 2017 | benchmark | Thermal field in water pipe cooling concrete hydrostructures simulated with singular bound |
| `10.1016/j.ymeth.2020.01.011` | 2020 | threshold_convention | In silico trials: Verification, validation and uncertainty quantification of predictive mo |
| `10.1016/s0898-1221(00)00317-5` | 2001 | threshold_convention | Goal-oriented error estimation and adaptivity for the finite element method |
| `10.1061/(asce)0733-9429(2005)131:6(431)` | 2005 | benchmark | Case Study: Finite Element Method and Artificial Neural Network Models for Flow through Je |
| `10.1063/1.3565032` | 2011 | threshold_convention | Markov models of molecular kinetics: Generation and validation |
| `10.1080/13632469.2018.1453409` | 2018 | benchmark | The Effects of Dam–Reservoir Interaction on the Nonlinear Seismic Response of Earth Dams |
| `10.1088/0965-0393/17/4/043001` | 2009 | threshold_convention | A review of extended/generalized finite element methods for material modeling |
| `10.1111/mice.13141` | 2023 | benchmark | Inverse analysis of deformation moduli for high arch dams using the displacement reconstru |
| `10.1115/1.1523350` | 2003 | benchmark | Boundary Element Programming in Mechanics |
| `10.1155/2013/709430` | 2013 | definition | Comparison between Duncan and Chang’s EB Model and the Generalized Plasticity Model in the |
| `10.1155/2015/817241` | 2015 | benchmark | Zoning Modulus Inversion Method for Concrete Dams Based on Chaos Genetic Optimization Algo |
| `10.2172/759450` | 2000 | threshold_convention | Code Verification by the Method of Manufactured Solutions |
| `10.2172/793406` | 2002 | threshold_convention | Verification and Validation in Computational Fluid Dynamics |
| `10.2172/835920` | 2004 | threshold_convention | Concepts of Model Verification and Validation |
| `10.2172/901974` | 2007 | threshold_convention | Verification and validation benchmarks. |
| `10.3390/polym12040818` | 2020 | benchmark | Application of the Finite Element Method in the Analysis of Composite Materials: A Review |
| `10.3390/w13213072` | 2021 | benchmark | Influences on the Seismic Response of a Gravity Dam with Different Foundation and Reservoi |

## Not available online

The two primary sources for HSTAR's file formats are internal Hohai
University documents with no DOI and no online presence. They are the
authority for everything in `docs/input_preparation.md` and are cited as
such throughout:

- *GEHOMadrid 程序使用说明 (Beta 1.0)*, Institute of Hydraulic Structures,
  Hohai University, April 2004 — 14 pp. Input/output file formats.
- *GEHOMadrid 温度场及温度应力场计算说明*, same institute — the two-pass
  thermal-stress procedure.

