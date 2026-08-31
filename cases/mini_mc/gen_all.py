"""mini_mc: 2D slope with Mohr-Coulomb material (type=Q, CLASSICALEP).
Simple slope: 10m high, 20m wide. Gravity loading.
2 groups: elastic base + MC slope body.
30 nodes, 20 Q4 elements.
"""
import os

outdir = os.path.dirname(os.path.abspath(__file__))

def write(name, content):
    with open(os.path.join(outdir, name), "w") as f:
        f.write(content)
    print(f"  {name}")

# Mesh: 5 cols x 4 rows = 20 Q4, domain 20m x 10m
nx, ny = 6, 5
Lx, Ly = 20.0, 10.0
npoin = nx * ny
nelem = (nx-1) * (ny-1)

def nid(ix, iy): return iy * nx + ix + 1

cor = [f"  {nid(ix,iy)}  {ix*Lx/(nx-1):.6f}  {iy*Ly/(ny-1):.6f}"
       for iy in range(ny) for ix in range(nx)]
write("1.cor", "\n".join(cor) + "\n")

ele = []
eid = 0
for iy in range(ny-1):
    for ix in range(nx-1):
        eid += 1
        # Group 1 (base): bottom 2 rows = 10 elements
        # Group 2 (MC slope): top 2 rows = 10 elements
        grp = 1 if iy < 2 else 2
        ele.append(f"  {eid}  {nid(ix,iy)}  {nid(ix+1,iy)}  {nid(ix+1,iy+1)}  {nid(ix,iy+1)}")
write("1.ele", "\n".join(ele) + "\n")

# flavia.msh
msh = [" mesh Slope dimension  2  elemtype Quadrilateral  nnode 4", " coordinates"]
for iy in range(ny):
    for ix in range(nx):
        n = nid(ix,iy)
        msh.append(f"  {n:8d}  {ix*Lx/(nx-1):16.8f}  {iy*Ly/(ny-1):16.8f}  0.00000000")
msh.append(" end coordinates")
msh.append(" elements")
eid = 0
for iy in range(ny-1):
    for ix in range(nx-1):
        eid += 1
        grp = 1 if iy < 2 else 2
        msh.append(f"  {eid:8d}  {nid(ix,iy)}  {nid(ix+1,iy)}  {nid(ix+1,iy+1)}  {nid(ix,iy+1)}  {grp}")
msh.append(" end elements")
write("1.flavia.msh", "\n".join(msh) + "\n")

# BCs
bottom = [nid(ix, 0) for ix in range(nx)]
left = [nid(0, iy) for iy in range(ny)]
right = [nid(nx-1, iy) for iy in range(ny)]
ux_nodes = sorted(set(left + right))
pre = ["'PRESCRIBE SET--NFIXSETS'", "  2  2",
       f"  1  {len(ux_nodes)}  1  0  0  0  0.  0",
       "  " + "  ".join(str(n) for n in ux_nodes), f"  {len(ux_nodes)}*0",
       f"  2  {len(bottom)}  1  0  0  0  0.  0",
       "  " + "  ".join(str(n) for n in bottom), f"  {len(bottom)}*0"]
write("1.pre", "\n".join(pre) + "\n")

# .glb: 2 groups, 2 materials, type_nl=4 (full Newton for nonlinear)
write("1.glb", f"""\
NPOIN npoinb NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh level_set ljdp stab_matde
  {npoin}  {npoin}  {nelem}  2  2  2  0  GIDR  0.0  0  0  0  0  0  99999
valv1
ndivide
NINIT KINIT winit NBLKS NLINK NONSY OUTIP outir outiw neumn equvs type_ABC block_stab nbackf nbspring ebody outind nbackdT ninistn
  0  0  0  1  0  0  0  0  0  0  0  FIX  0  0  0  0  0  0  0
TYPE_PROBLEM TYPE_SOLVER TYPE_LOAD TYPE_NL stabpw nlayer kglb state_change Bparameter balgor upliftin
Q  PROFILE  LOAD  4  0  0  0  0  0  0  0
type_layer1
NMASS NSMAT NHMAT NQMAT NLDFL KGMAT NSWKW UWCPL NGRAV nflow ECWPIPE
  1  1  1  1  0  0  1  0  1  0  0
nfreeflownode
NTSMAT NTHMAT KSTAT ground_inf src nextrf submodel
  999  999  0  0  0  0  0
MDOFN
  2
  1  1
  0  0
BEETA1 BEETA2 THETA1
  0.5  0.25  1.0
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
  2  2
gid_u,gid_s,gid_ms,gid_f,gid_rot,gid_v,gid_a,gid_T,gid_P,gid_Pv,gid_ep,gid_Y,gid_FC,gid_Ns,gid_Ss,gid_Mxy,gid_bem,gid_wh,gid_wv,gid_bcs
  1  1  0  0  0  0  0  0  0  0  1  0  0  0  0  0  0  0  0  0
res_u,res_s,res_ms,res_f,res_rot,res_v,res_a,res_T,res_P,res_Pv,res_ep,res_Y,res_FC,res_Ns,res_Ss,res_Tv,res_Pa
  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0
Icaddmass,swlifs2006,toth,ifswater,ifsgravity,absorb,alfa_p4,stiff_p4
  0  50.0  50.0  2  9.8  0.6  10.0  1.0E+20
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
Q4    Base           5 CO     1 U   ST   PE            10  1  0  1  1  1       0.000E+00  0  0  0
  0  0.0  0.0
  0  0
  2
  1  2
Q4    Slope          5 CO     1 U   ST   PE            10  2  0  1  1  1       0.000E+00  0  0  0
  0  0.0  0.0
  0  0
  2
  1  2
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

# .mat: elastic base + CLASSICALEP MC slope
# MC format: CLASSICALEP density ratio thick E nu alfa 0 0 0
#            kind_wt density_w bulkw
#            MC, cohesion, hardening
#            friction_angle  dilation_angle
write("1.mat", """\
 material property curves
  0
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
  2
     material_serial         1
          MECHANICAL           SOLID         1
  1
               SOLID
ELASTIC_ISOTROPIC       2.500E+03       1.000E+00       1.000E+00       2.000E+10       2.500E-01       1.000E-05  0  0  0
  0  0       1.000E+03
     material_serial         2
          MECHANICAL           SOLID         2
  1
               SOLID
CLASSICALEP             2.000E+03       1.000E+00       1.000E+00       5.000E+07       3.500E-01       1.000E-05  0  0  0
  0  0       1.000E+03
  MC  5.0e4  0.0
  30.0  15.0
  0.0
  0.0  0.0
""")

# .LOA
L = [" (*.loa) Load data", "  1", "  2  LINEAR  0  2", "  0.0  1.0", "  1.0  1.0",
     " Define point load", "  0  0", " Define edges for whole analysis", "  0",
     " Define edge load in each BLKS", " edge_load_group,delgroup", "  0  0",
     " Define body force in each BLKS",
     "  9.81000E+00  0.00000E+00  -1.00000E+00  0.00000E+00  -1.00000E+00",
     " Time_curve_for_each_group  1", "  1  1",
     " nbeamload", "  0", " nplateload", "  0"]
write("1.LOA", "\n".join(L) + "\n")

# .man: type_nl=4 (full Newton), 10 iterations
write("1.man", " nincs,cdtest,earthquake_curve(1:ndimn)\n  1  0  0  0\n  10  1.0  1  1  1  1  1  0  0\n  3*1.0e-05\n")

sol = []
for _ in range(50):
    sol.extend([" Iafile icond ipdchk ising", "  0  0  1  1"])
write("1.sol", "\n".join(sol) + "\n")

write("1.ftr", " nforce,ngaps,nforce_gaps,nsafety_gaps\n       0       0       0       0\n")
write("1.opr", " Irecover wgroup\n (output control flags)\n  0  0  0  0  0\n following is for stress output groups\n node ranges per group\n one line for each group\n following is for elements\n following is for gaps\n following is for joints\n")
write("1.nrt", " The interpolation groups: transgroup\n ntransnode and translg for each transgroup\n       0\n")
tem = [" temperature prescribed data","  0"," surface convection edges (nedge)","  0"," surface convection (type 2)"," surface list (1:nsurf)","  0"," pipe cooling info"," algo_pipe=3","  0  3",""]
tem.extend(["  0"]*20)
write("1.tem", "\n".join(tem) + "\n")
write("1.ifs", "nifsgroup\n0\nnabsfgroup\n0\nnabssgroup,exx,uxx,densxx\n0  0  0  0\nifsnedge\n0\n")
write("inp", "restart,relis,sysrelis,ADINA,Uopt_R,gamamax\n0  0  0  0  0  0\nprobn\n1\n1\n")

print(f"\nAll mini_mc files generated! ({npoin} nodes, {nelem} elements)")
