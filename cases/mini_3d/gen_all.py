"""mini_3d: 3D cube under compression (type=Q).
8 B8 hex elements, 27 nodes. Bottom fixed, top prescribed displacement.
"""
import os
outdir = os.path.dirname(os.path.abspath(__file__))

def write(name, content):
    with open(os.path.join(outdir, name), "w") as f:
        f.write(content)
    print(f"  {name}")

# ---- Mesh: 2x2x2 = 8 B8 hex, cube 10m x 10m x 10m ----
nx, ny, nz = 3, 3, 3
Lx, Ly, Lz = 10.0, 10.0, 10.0
npoin = nx * ny * nz  # 27
nelem = (nx-1)*(ny-1)*(nz-1)  # 8

def nid(ix, iy, iz): return iz * nx * ny + iy * nx + ix + 1

# 1.cor (3D)
cor = []
for iz in range(nz):
    for iy in range(ny):
        for ix in range(nx):
            cor.append(f"  {nid(ix,iy,iz)}  {ix*Lx/(nx-1):.6f}  {iy*Ly/(ny-1):.6f}  {iz*Lz/(nz-1):.6f}")
write("1.cor", "\n".join(cor) + "\n")

# 1.ele (B8: 8 nodes per hex)
ele = []
eid = 0
for iz in range(nz-1):
    for iy in range(ny-1):
        for ix in range(nx-1):
            eid += 1
            n = [nid(ix,iy,iz), nid(ix+1,iy,iz), nid(ix+1,iy+1,iz), nid(ix,iy+1,iz),
                 nid(ix,iy,iz+1), nid(ix+1,iy,iz+1), nid(ix+1,iy+1,iz+1), nid(ix,iy+1,iz+1)]
            ele.append(f"  {eid}  " + "  ".join(str(x) for x in n))
write("1.ele", "\n".join(ele) + "\n")

# 1.flavia.msh
msh = [" mesh Cube dimension  3  elemtype Hexahedra  nnode 8", " coordinates"]
for iz in range(nz):
    for iy in range(ny):
        for ix in range(nx):
            n = nid(ix,iy,iz)
            msh.append(f"  {n:8d}  {ix*Lx/(nx-1):16.8f}  {iy*Ly/(ny-1):16.8f}  {iz*Lz/(nz-1):16.8f}")
msh.append(" end coordinates")
msh.append(" elements")
eid = 0
for iz in range(nz-1):
    for iy in range(ny-1):
        for ix in range(nx-1):
            eid += 1
            n = [nid(ix,iy,iz), nid(ix+1,iy,iz), nid(ix+1,iy+1,iz), nid(ix,iy+1,iz),
                 nid(ix,iy,iz+1), nid(ix+1,iy,iz+1), nid(ix+1,iy+1,iz+1), nid(ix,iy+1,iz+1)]
            msh.append(f"  {eid:8d}  " + "  ".join(str(x) for x in n) + "  1")
msh.append(" end elements")
write("1.flavia.msh", "\n".join(msh) + "\n")

# BCs
bottom = [nid(ix,iy,0) for iy in range(ny) for ix in range(nx)]  # z=0, 9 nodes
top = [nid(ix,iy,nz-1) for iy in range(ny) for ix in range(nx)]  # z=1, 9 nodes
# Rigid body: fix Ux at node 1, Uy at nodes 1,2,3
node1 = nid(0,0,0)
uy_fix = [nid(ix,0,0) for ix in range(nx)]  # bottom edge y=0

# 1.pre: Uz=0 bottom, Ux=0 node1, Uy=0 bottom-y-edge, Uz=-0.001 top
pre = []
pre.append("'PRESCRIBE SET--NFIXSETS'")
pre.append("  4  4")
# Uz=0 bottom
pre.append(f"  3  {len(bottom)}  1  0  0  0  0.  0")
pre.append("  " + "  ".join(str(n) for n in bottom))
pre.append(f"  {len(bottom)}*0")
# Ux=0 node1
pre.append(f"  1  1  1  0  0  0  0.  0")
pre.append(f"  {node1}")
pre.append(f"  1*0")
# Uy=0 bottom y-edge
pre.append(f"  2  {len(uy_fix)}  1  0  0  0  0.  0")
pre.append("  " + "  ".join(str(n) for n in uy_fix))
pre.append(f"  {len(uy_fix)}*0")
# Uz=-0.001 top (prescribed displacement)
pre.append(f"  3  {len(top)}  1  0  0  0  0.  0")
pre.append("  " + "  ".join(str(n) for n in top))
pre.append("  " + "  ".join(["-0.01"] * len(top)))
write("1.pre", "\n".join(pre) + "\n")

# ---- 1.glb: 3D static, mdofn=3, B8 index=9 ----
write("1.glb", f"""\
NPOIN npoinb NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh level_set ljdp stab_matde
  {npoin}  {npoin}  {nelem}  3  1  1  0  GIDR  0.0  0  0  0  0  0  99999
valv1
ndivide
NINIT KINIT winit NBLKS NLINK NONSY OUTIP outir outiw neumn equvs type_ABC block_stab nbackf nbspring ebody outind nbackdT ninistn
  0  0  0  1  0  0  0  0  0  0  0  FIX  0  0  0  0  0  0  0
TYPE_PROBLEM TYPE_SOLVER TYPE_LOAD TYPE_NL stabpw nlayer kglb state_change Bparameter balgor upliftin
Q  PROFILE  LOAD  5  0  0  0  0  0  0  0
type_layer1
NMASS NSMAT NHMAT NQMAT NLDFL KGMAT NSWKW UWCPL NGRAV nflow ECWPIPE
  1  1  1  1  0  0  1  0  1  0  0
nfreeflownode
NTSMAT NTHMAT KSTAT ground_inf src nextrf submodel
  999  999  0  0  0  0  0
MDOFN
  3
  1  1  1
  0  0  0
BEETA1 BEETA2 THETA1
  0.5  0.25  1.0
equvs_process(1:ngroup)
  0
appear_level(1:ngroup)
  0
APPEAR_PROCESS
  1
MATNO_PROCESS
  1
force_process(1:ngroup)
  0
average_appear
  -2
gid_u,gid_s,gid_ms,gid_f,gid_rot,gid_v,gid_a,gid_T,gid_P,gid_Pv,gid_ep,gid_Y,gid_FC,gid_Ns,gid_Ss,gid_Mxy,gid_bem,gid_wh,gid_wv,gid_bcs
  1  1  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0
res_u,res_s,res_ms,res_f,res_rot,res_v,res_a,res_T,res_P,res_Pv,res_ep,res_Y,res_FC,res_Ns,res_Ss,res_Tv,res_Pa
  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0
Icaddmass,swlifs2006,toth,ifswater,ifsgravity,absorb,alfa_p4,stiff_p4
  0  50.0  50.0  3  9.8  0.6  10.0  1.0E+20
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
B8    Cube           9 CO     1 U   ST   PE             {nelem}  1  0  1  1  1       0.000E+00  0  0  0
  0  0.0  0.0
  0  0
  3
  1  2  3
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

# 1.mat (3D, same E/nu but density irrelevant for prescribed disp)
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
  1
     material_serial         1
          MECHANICAL           SOLID         1
  1
               SOLID
ELASTIC_ISOTROPIC       2.400E+03       1.000E+00       1.000E+00       2.500E+10       2.000E-01       1.000E-05  0  0  0
  0  0       1.000E+03
""")

# 1.LOA: no gravity (prescribed displacement test)
write("1.LOA", """\
 (*.loa) Load data
  1
  2  LINEAR  0  2
  0.0  1.0
  1.0  1.0
 Define point load
  0  0
 Define edges for whole analysis
  0
 Define edge load in each BLKS
 edge_load_group,delgroup
  0  0
 Define body force in each BLKS
  0.00000E+00  0.00000E+00  0.00000E+00  -1.00000E+00  0.00000E+00  0.00000E+00  -1.00000E+00
 Time_curve_for_each_group  1
  1
 nbeamload
  0
 nplateload
  0
""")

# 1.man: 1 block, mdofn=3 → 4 tolerance values
write("1.man", """\
 nincs,cdtest,earthquake_curve(1:ndimn)
  1  0  0  0  0
  5  1.0  1  1  1  1  1  0  0
  4*1.0e-05
""")

# 1.sol (PROFILE)
sol = []
for _ in range(50):
    sol.extend([" Iafile icond ipdchk ising", "  0  0  1  1"])
write("1.sol", "\n".join(sol) + "\n")

# Auxiliary
write("1.ftr", " nforce,ngaps,nforce_gaps,nsafety_gaps\n       0       0       0       0\n")
write("1.opr", " Irecover wgroup\n (output control flags)\n  0  0  0  0  0\n following is for stress output groups\n node ranges per group\n one line for each group\n following is for elements\n following is for gaps\n following is for joints\n")
write("1.nrt", " The interpolation groups: transgroup\n ntransnode and translg for each transgroup\n       0\n")
tem = [" temperature prescribed data","  0"," surface convection edges (nedge)","  0"," surface convection (type 2)"," surface list (1:nsurf)","  0"," pipe cooling info"," algo_pipe=3","  0  3",""]
tem.extend(["  0"]*20)
write("1.tem", "\n".join(tem) + "\n")
write("1.ifs", "nifsgroup\n0\nnabsfgroup\n0\nnabssgroup,exx,uxx,densxx\n0  0  0  0\nifsnedge\n0\n")
write("inp", "restart,relis,sysrelis,ADINA,Uopt_R,gamamax\n0  0  0  0  0  0\nprobn\n1\n1\n")

print("\nAll mini_3d files generated!")
