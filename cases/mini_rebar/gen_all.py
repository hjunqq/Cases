"""mini_rebar: 3D RC beam with L2 rebar truss (type=Q).
B8 concrete block (8 elements) + L2 rebar truss (4 elements), 2 groups.
Demonstrates: L2 elements + GEOMETRY material + doubsig=2.
"""
import os

outdir = os.path.dirname(os.path.abspath(__file__))

def write(name, content):
    with open(os.path.join(outdir, name), "w") as f:
        f.write(content)
    print(f"  {name}")

# Mesh: 3D beam 4m x 1m x 1m
# B8 concrete: 2x2x2 = 8 elements, 27 nodes (same as mini_3d)
# L2 rebar: 4 truss elements along bottom edge (y=0, z=0), x=0→0.5→1→1.5→2
nx, ny, nz = 3, 3, 3
Lx, Ly, Lz = 4.0, 1.0, 1.0
npoin_b8 = nx * ny * nz  # 27

def nid_b8(ix, iy, iz): return iz * nx * ny + iy * nx + ix + 1

# B8 nodes
cor = []
for iz in range(nz):
    for iy in range(ny):
        for ix in range(nx):
            x = ix * Lx / (nx-1)
            y = iy * Ly / (ny-1)
            z = iz * Lz / (nz-1)
            cor.append(f"  {nid_b8(ix,iy,iz)}  {x:.6f}  {y:.6f}  {z:.6f}")

# L2 rebar nodes: share bottom edge nodes (y=0, z=0) from B8
# These are nid_b8(ix, 0, 0) = ix + 1 for ix in range(3)
# = nodes 1, 2, 3
# Rebar runs from x=0 to x=4 along bottom edge, 4 L2 elements
# Need 5 nodes: nodes 1(x=0), 2(x=2), 3(x=4) from B8 + 2 new nodes at x=1, x=3
npoin_new = 2  # new rebar-only nodes at x=1 and x=3
n_rebar_mid1 = npoin_b8 + 1  # 28, at x=1
n_rebar_mid2 = npoin_b8 + 2  # 29, at x=3
cor.append(f"  {n_rebar_mid1}  1.000000  0.000000  0.000000")
cor.append(f"  {n_rebar_mid2}  3.000000  0.000000  0.000000")
npoin = npoin_b8 + npoin_new
write("1.cor", "\n".join(cor) + "\n")

# B8 elements (group 1)
ele = []
eid = 0
for iz in range(nz-1):
    for iy in range(ny-1):
        for ix in range(nx-1):
            eid += 1
            n = [nid_b8(ix,iy,iz), nid_b8(ix+1,iy,iz), nid_b8(ix+1,iy+1,iz), nid_b8(ix,iy+1,iz),
                 nid_b8(ix,iy,iz+1), nid_b8(ix+1,iy,iz+1), nid_b8(ix+1,iy+1,iz+1), nid_b8(ix,iy+1,iz+1)]
            ele.append(f"  {eid}  " + "  ".join(str(x) for x in n))
nelem_b8 = eid

# L2 rebar elements (group 2): 4 elements along bottom edge
rebar_nodes = [1, n_rebar_mid1, 2, n_rebar_mid2, 3]  # 5 nodes
for i in range(4):
    eid += 1
    ele.append(f"  {eid}  {rebar_nodes[i]}  {rebar_nodes[i+1]}")
nelem = eid

write("1.ele", "\n".join(ele) + "\n")
print(f"Mesh: {npoin} nodes, {nelem} elements (B8={nelem_b8}, L2={nelem-nelem_b8})")

# flavia.msh (separate mesh blocks for B8 and L2)
msh = []
# B8 block
msh.append(" mesh Concrete dimension  3  elemtype Hexahedra  nnode 8")
msh.append(" coordinates")
for iz in range(nz):
    for iy in range(ny):
        for ix in range(nx):
            n = nid_b8(ix,iy,iz)
            msh.append(f"  {n:8d}  {ix*Lx/(nx-1):16.8f}  {iy*Ly/(ny-1):16.8f}  {iz*Lz/(nz-1):16.8f}")
msh.append(" end coordinates")
msh.append(" elements")
eid2 = 0
for iz in range(nz-1):
    for iy in range(ny-1):
        for ix in range(nx-1):
            eid2 += 1
            n = [nid_b8(ix,iy,iz), nid_b8(ix+1,iy,iz), nid_b8(ix+1,iy+1,iz), nid_b8(ix,iy+1,iz),
                 nid_b8(ix,iy,iz+1), nid_b8(ix+1,iy,iz+1), nid_b8(ix+1,iy+1,iz+1), nid_b8(ix,iy+1,iz+1)]
            msh.append(f"  {eid2:8d}  " + "  ".join(str(x) for x in n) + "  1")
msh.append(" end elements")
# L2 block
msh.append(" mesh Rebar dimension  3  elemtype Linear  nnode 2")
msh.append(" coordinates")
for n in sorted(set(rebar_nodes)):
    idx = cor[n-1].split()
    msh.append(f"  {n:8d}  {float(idx[1]):16.8f}  {float(idx[2]):16.8f}  {float(idx[3]):16.8f}")
msh.append(" end coordinates")
msh.append(" elements")
for i in range(4):
    msh.append(f"  {nelem_b8+i+1:8d}  {rebar_nodes[i]}  {rebar_nodes[i+1]}  2")
msh.append(" end elements")
write("1.flavia.msh", "\n".join(msh) + "\n")

# BCs: left face (x=0) fixed all
left = [nid_b8(0,iy,iz) for iz in range(nz) for iy in range(ny)] + [1]  # includes rebar node 1
left = sorted(set(left))
pre = ["'PRESCRIBE SET--NFIXSETS'", "  3  3"]
for dof in [1, 2, 3]:
    pre.append(f"  {dof}  {len(left)}  1  0  0  0  0.  0")
    pre.append("  " + "  ".join(str(n) for n in left))
    pre.append(f"  {len(left)}*0")
write("1.pre", "\n".join(pre) + "\n")

# .glb: 3D, mdofn=3, 2 groups (B8+L2), ikindks=0, doubsig=2
write("1.glb", f"""\
NPOIN npoinb NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh level_set ljdp stab_matde
  {npoin}  {npoin}  {nelem}  3  3  2  0  GIDR  0.0  0  0  0  0  0  99999
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
B8    Concrete       9 CO     1 U   ST   PE             {nelem_b8}  1  0  1  1  1       0.000E+00  0  0  0
  0  0.0  0.0
  0  0
  3
  1  2  3
L2    Rebar          1 CO     1 U   ST   PE             {nelem-nelem_b8}  2  0  1  1  1       0.000E+00  0  0  0
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

# .mat: concrete + steel + GEOMETRY (for L2 cross-section area)
write("1.mat", f"""\
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
  3
     material_serial         1
          MECHANICAL           SOLID         1
  1
               SOLID
ELASTIC_ISOTROPIC       2.400E+03       1.000E+00       1.000E+00       2.500E+10       1.670E-01       1.000E-05  0  0  0
  0  0       1.000E+03
     material_serial         2
          MECHANICAL           SOLID         2
  1
               SOLID
ELASTIC_ISOTROPIC       7.800E+03       1.000E+00       8.042E-04       2.000E+11       2.300E-01       1.000E-05  0  0  0
  0  0       1.000E+03
     material_serial         3
            GEOMETRY         ROD_or_BEAM    2
  8.042E-04  0.000E+00  0.000E+00  0.000E+00
""")

# .LOA, .man, .sol, aux
L = [" (*.loa) Load data", "  1", "  2  LINEAR  0  2", "  0.0  1.0", "  1.0  1.0",
     " Define point load", "  0  0", " Define edges for whole analysis", "  0",
     " Define edge load in each BLKS", " edge_load_group,delgroup", "  0  0",
     " Define body force in each BLKS",
     "  9.81000E+00  0.00000E+00  0.00000E+00  -1.00000E+00  0.00000E+00  0.00000E+00  -1.00000E+00",
     " Time_curve_for_each_group  1", "  1  1", " nbeamload", "  0", " nplateload", "  0"]
write("1.LOA", "\n".join(L) + "\n")
write("1.man", " nincs,cdtest,earthquake_curve(1:ndimn)\n  1  0  0  0  0\n  5  1.0  1  1  1  1  1  0  0\n  4*1.0e-05\n")
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

print("\\nAll mini_rebar files generated!")
