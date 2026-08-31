"""mini_thermal: 2D transient heat conduction (type=S).
291 nodes, 250 Q4 elements, 2 groups. Convection BC via .tem file.
Adapted from hstardebug T_1block(1) for hstarYLOrig format.
"""
import os

outdir = os.path.dirname(os.path.abspath(__file__))

def write(name, content):
    with open(os.path.join(outdir, name), "w") as f:
        f.write(content)
    print(f"  {name}")

npoin, nelem, ndimn = 291, 250, 2
ngroup, nblks = 2, 1

# 1.glb: type=S thermal, mdofn=10, ecwpipe=2, PARDISO
# Key: order_time_mdofn has DOF 10 = 1 (thermal time derivative)
# Key: group order_time = [0, 1] (stiffness + capacity)
# Key: nmats=3 (2 HEAT + 1 MECHANICAL for use_duncanchang)
write("1.glb", f"""\
NPOIN npoinb NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh level_set ljdp stab_matde
  {npoin}  {npoin}  {nelem}  {ndimn}  4  {ngroup}  0  GIDR  0.0  0  0  0  0  0  99999
valv1
ndivide
NINIT KINIT winit NBLKS NLINK NONSY OUTIP outir outiw neumn equvs type_ABC block_stab nbackf nbspring ebody outind nbackdT ninistn
  0  0  0  {nblks}  0  0  0  0  1  0  0  FIX  0  0  0  0  0  0  0
TYPE_PROBLEM TYPE_SOLVER TYPE_LOAD TYPE_NL stabpw nlayer kglb state_change Bparameter balgor upliftin
S  PROFILE  LOAD  5  0  0  0  0  0  0  0
type_layer1
NMASS NSMAT NHMAT NQMAT NLDFL KGMAT NSWKW UWCPL NGRAV nflow ECWPIPE
  999  999  999  999  999  0  999  0  999  0  2
nfreeflownode
NTSMAT NTHMAT KSTAT ground_inf src nextrf submodel
  999  999  0  0  0  0  0
MDOFN
  10
  0  0  0  0  0  0  0  0  0  1
  0  0  0  0  0  0  0  0  0  1
BEETA1 BEETA2 THETA1
  0.5  0.25  0.5
equvs_process(1:ngroup)
  0  0
appear_level(1:ngroup)
  0  0
APPEAR_PROCESS
  1  1
MATNO_PROCESS
  1  2
force_process(1:ngroup)
  0  0
average_appear
  -2  -2
gid_u,gid_s,gid_ms,gid_f,gid_rot,gid_v,gid_a,gid_T,gid_P,gid_Pv,gid_ep,gid_Y,gid_FC,gid_Ns,gid_Ss,gid_Mxy,gid_bem,gid_wh,gid_wv,gid_bcs
  0  0  0  0  0  0  0  1  0  0  0  0  0  0  0  0  0  0  0  0
res_u,res_s,res_ms,res_f,res_rot,res_v,res_a,res_T,res_P,res_Pv,res_ep,res_Y,res_FC,res_Ns,res_Ss,res_Tv,res_Pa
  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0
Icaddmass,swlifs2006,toth,ifswater,ifsgravity,absorb,alfa_p4,stiff_p4
  0  100.0  100.0  3  9.8  0.6  -10.0  1.0E+20
ftcrack,coefMpa,ikindks,doubsig,ktan1,ktan2,nlocalbeam,ndimnrt
  1.5e6  1.0e6  0  2  1.0e8  1.0e8  0  0
ntrans,nlaymif,epsMIFb,gamaMIF,ifixvar0_inpb,camif,dxmif
  0  0  1.0e0  0.02  2  1980.0  25.0
hdam
  0.000
water_level
  -99.000
modf_dis_blocks
  0
uinitial
  0
backf()%
1-ILINKS(I0, Freedom, node1,node2)
1-tLINKS(I0, node1,node2)
1-NGROUP--GROUP INFORMATION
INCLUDE (1) NAME KNAME INDEX CLASS NRFIELDS FIELDID SPECIAL
 SPTYPE NELGROUP MATNO TYPE_ALGO TYPE_STIFF TYPE_ECOINT ilayer elcod_local group_inf uplift_ic liquj
         (2) TYPE_MASS(1:NRFIELDS)
         (3) for each field: nfdof-number of freedom,listdof(1:nfdof)
Q4    Concrete       5 CO     1 T   ST   PS           100  1  0  1  1  1       0.000E+00  0  0  0
  0  0.0  0.0
  0  1
  1
  10
Q4    Rock           5 CO     1 T   ST   PS           150  2  0  1  1  1       0.000E+00  0  0  0
  0  0.0  0.0
  0  1
  1
  10
tension_joint
  0
contact_joint
  0
ngaps ngapb ctt_pe miter_bt torbt iblkbt nonsbt xlwsol method_gapi miter_state type_solver_ctt restart_ctt damp_ctt istatec
  0  0  1  500  1.0E-05  1  0  0  0  1  PROFILE  0  0.0  1
 nrcsteel
  0
 nwcpipe
  0
""")

# 1.mat: MECHANICAL (dummy for use_duncanchang) + 2 HEAT materials
# Conductivity=0.096 W/(m·K·day), source_curve=3(group1)/0(group2), place_curve=1
write("1.mat", """\
 material property curves
  1
  7  LINEAR  2.0
  3  7  14  20  28  65  90
  1.36e-6  3.21e-6  4.98e-6  5.58e-6  6.20e-6  7.91e-6  7.55e-6
  10
MATERIAL PROPERTIES-INPUT FOR 1 TO NMATS
NAME FOR MATERIAL---FOR COMMENTS
FIRST:NAME---MECHANICAL, TEMPERATURE, ETC
FOR MECHNICAL, SECOND:PHASE---SOLID, FLUID, AIR OR OIL
NUMBER OF PHASE
FOR SOLID: MATERIAL(CLASSICALEP,CAMCLAY,ETC),density,ratio,thick,e,nu
FOR MATERISL: CLASSICALEP:CRITERIA(TC,VM,DP,MC),sigm0,hardening
FOR MC OR DP: FRICT_ANGLE, DILAN_ANGLE
CAMCLAY    :Pc, lamda, Mg, Mf, D0, D1,gaama
FOR FLUID: (1) density,ratio,bulkw (2)permiability(1:ndimn)
 nmats
  4
     material_serial         1
          MECHANICAL           SOLID         1
  1
               SOLID
ELASTIC_ISOTROPIC       0.000E+00       1.000E+00       1.000E+00       1.000E+10       1.670E-01       1.000E-06  0  0  0
  0  0  0  1000.
     material_serial         2
          HEAT                 SOLID         1
  0.096  0.096  3  1  0
  0
     material_serial         3
          MECHANICAL           SOLID         2
  1
               SOLID
ELASTIC_ISOTROPIC       0.000E+00       1.000E+00       1.000E+00       1.000E+10       1.670E-01       1.000E-06  0  0  0
  0  0  0  1000.
     material_serial         4
          HEAT                 SOLID         2
  0.096  0.096  0  1  0
  0
""")

# 1.LOA: 2 time curves (placement temp + hydration source)
write("1.LOA", """\
 (*.loa) Load data
  3
  2  LINEAR  0  2
  0.0  1000.0
  1.0  1.0
  2  LINEAR  0  2
  0.0  1000.0
  15.0  15.0
  7  LINEAR  0  2
  3.0  7.0  14.0  28.0  65.0  90.0  180.0
  1.0e-5  3.0e-5  4.0e-5  5.0e-5  6.0e-5  7.0e-5  7.5e-5
 Define point load
  0  0
 Define edges for whole analysis
  0
 Define edge load in each BLKS
 edge_load_group,delgroup
  0  0
 Define body force in each BLKS
  0.00000E+00  0.00000E+00  -1.00000E+00  0.00000E+00  -1.00000E+00
 Time_curve_for_each_group  1
  1  1
 nbeamload
  0
 nplateload
  0
""")

# 1.man: type=S needs nstepjq/nstepjp after nincs
write("1.man", """\
 nincs,cdtest,earthquake_curve(1:ndimn)
  1  0  0  0
  0  0
  5  0.20  1  1  100  1  1  0  0
  11*1.0e-05
""")

# 1.pre: no temperature fixsets (BCs via .tem convection)
write("1.pre", """\
PRESCRIBE SET--NFIXSETS
  0  0
""")

# 1.sol (PROFILE)
sol = []
for _ in range(200):
    sol.extend([" Iafile icond ipdchk ising", "  0  0  1  1"])
write("1.sol", "\n".join(sol) + "\n")

# Auxiliary
write("1.ftr", " nforce,ngaps,nforce_gaps,nsafety_gaps\n       0       0       0       0\n")
write("1.opr", " Irecover wgroup\n (output control flags)\n  0  0  0  0  0\n following is for stress output groups\n node ranges per group\n one line for each group\n following is for elements\n following is for gaps\n following is for joints\n")
write("1.nrt", " The interpolation groups: transgroup\n ntransnode and translg for each transgroup\n       0\n")
write("1.ifs", "nifsgroup\n0\nnabsfgroup\n0\nnabssgroup,exx,uxx,densxx\n0  0  0  0\nifsnedge\n0\n")
write("inp", f"restart,relis,sysrelis,ADINA,Uopt_R,gamamax\n0  0  0  0  0  0\nprobn\n1\n{nblks}\n")

# .tem is already copied from debug case (has convection edges)
print("\nAll mini_thermal files generated!")
print("Note: 1.cor, 1.ele, 1.tem, 1.flavia.msh copied from hstardebug T_1block(1)")
