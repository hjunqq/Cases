"""mini_goodman: 2D block on Goodman joint (type=Q).
Two rock blocks with a thin Goodman joint layer between them.
Upper block slides under gravity on inclined joint.
12 Q4 (6 upper + 4 joint + 2 lower), 24 nodes, 3 materials.
"""
import os, math

outdir = os.path.dirname(os.path.abspath(__file__))

def write(name, content):
    with open(os.path.join(outdir, name), "w") as f:
        f.write(content)
    print(f"  {name}")

# ============================================================
# Mesh: 2D block sitting on horizontal Goodman joint on foundation
# Foundation: 10m x 5m, 2x1 = 2 Q4 (group 1)
# Joint layer: 10m x 0.02m, 2x2 = 4 Q4 (group 2, elcod_local=0.02)
# Upper block: 10m x 10m, 2x3 = 6 Q4 (group 3)
# ============================================================
nodes = {}
nid = 0

# Y levels: -5, 0(bottom of joint), 0.01(mid-joint), 0.02(top of joint), 5, 10, 15
# X levels: 0, 5, 10
xs = [0.0, 5.0, 10.0]
# Foundation
ys_found = [-5.0, 0.0]
# Joint (thin: 0.02m thick, split into 2 rows)
ys_joint = [0.0, 0.01, 0.02]
# Upper block
ys_upper = [0.02, 5.0, 10.0, 15.0]

# Build nodes
# Foundation: rows 0-1
for iy, y in enumerate(ys_found):
    for ix, x in enumerate(xs):
        nid += 1
        nodes[nid] = (x, y)

# Joint: rows 1(shared)-3, row 0 of joint shares with foundation top
joint_start_nid = nid + 1
for iy in range(1, len(ys_joint)):  # skip first row (shared)
    for ix, x in enumerate(xs):
        nid += 1
        nodes[nid] = (x, ys_joint[iy])

# Upper block: row 0 shares with joint top
for iy in range(1, len(ys_upper)):
    for ix, x in enumerate(xs):
        nid += 1
        nodes[nid] = (x, ys_upper[iy])

npoin = nid
# Node layout:
# Foundation: 1-3 (y=-5), 4-6 (y=0)
# Joint mid: 7-9 (y=0.01), Joint top: 10-12 (y=0.02)
# Upper: 13-15 (y=5), 16-18 (y=10), 19-21 (y=15)

def get_node(ix, y_level):
    """Find node at (xs[ix], y_level)"""
    for n, (x, y) in nodes.items():
        if abs(x - xs[ix]) < 0.01 and abs(y - y_level) < 0.001:
            return n
    raise ValueError(f"No node at x={xs[ix]}, y={y_level}")

elements = []
# Foundation: 2 elements (group 1)
for ix in range(2):
    n1 = get_node(ix, -5.0)
    n2 = get_node(ix+1, -5.0)
    n3 = get_node(ix+1, 0.0)
    n4 = get_node(ix, 0.0)
    elements.append((n1, n2, n3, n4, 1))

# Joint: 4 elements (group 2, 2 cols x 2 rows)
for iy, (yb, yt) in enumerate([(0.0, 0.01), (0.01, 0.02)]):
    for ix in range(2):
        n1 = get_node(ix, yb)
        n2 = get_node(ix+1, yb)
        n3 = get_node(ix+1, yt)
        n4 = get_node(ix, yt)
        elements.append((n1, n2, n3, n4, 2))

# Upper block: 6 elements (group 3, 2 cols x 3 rows)
for iy, (yb, yt) in enumerate([(0.02, 5.0), (5.0, 10.0), (10.0, 15.0)]):
    for ix in range(2):
        n1 = get_node(ix, yb)
        n2 = get_node(ix+1, yb)
        n3 = get_node(ix+1, yt)
        n4 = get_node(ix, yt)
        elements.append((n1, n2, n3, n4, 3))

nelem = len(elements)
ngroup = 3
print(f"Mesh: {npoin} nodes, {nelem} elements (found={2}, joint={4}, upper={6})")

# Write mesh files
cor = [f"  {n}  {x:.6f}  {y:.6f}" for n, (x, y) in sorted(nodes.items())]
write("1.cor", "\n".join(cor) + "\n")

ele = [f"  {i+1}  {n1}  {n2}  {n3}  {n4}" for i, (n1,n2,n3,n4,g) in enumerate(elements)]
write("1.ele", "\n".join(ele) + "\n")

# flavia.msh
gnames = {1: "Foundation", 2: "GoodmanJoint", 3: "UpperBlock"}
msh = []
groups_e = {1:[], 2:[], 3:[]}
for i, (n1,n2,n3,n4,g) in enumerate(elements):
    groups_e[g].append((i+1, [n1,n2,n3,n4]))
for gid in sorted(groups_e):
    gnodes = sorted(set(n for _,ns in groups_e[gid] for n in ns))
    msh.append(f" mesh {gnames[gid]} dimension  2  elemtype Quadrilateral  nnode 4")
    msh.append(" coordinates")
    for n in gnodes:
        x,y = nodes[n]
        msh.append(f"  {n:8d}  {x:16.8f}  {y:16.8f}  0.00000000")
    msh.append(" end coordinates")
    msh.append(" elements")
    for eid, ns in groups_e[gid]:
        msh.append(f"  {eid:8d}  " + "  ".join(str(n) for n in ns) + f"  {gid}")
    msh.append(" end elements")
write("1.flavia.msh", "\n".join(msh) + "\n")

# BCs: bottom fixed (Uy), sides roller (Ux)
bottom = [get_node(ix, -5.0) for ix in range(3)]
left = [n for n, (x,y) in nodes.items() if abs(x) < 0.01]
right = [n for n, (x,y) in nodes.items() if abs(x-10.0) < 0.01]

pre = []
pre.append("'PRESCRIBE SET--NFIXSETS'")
pre.append(f"  2  2")
ux_nodes = sorted(set(left + right))
pre.append(f"  1  {len(ux_nodes)}  1  0  0  0  0.  0")
pre.append("  " + "  ".join(str(n) for n in ux_nodes))
pre.append(f"  {len(ux_nodes)}*0")
pre.append(f"  2  {len(bottom)}  1  0  0  0  0.  0")
pre.append("  " + "  ".join(str(n) for n in bottom))
pre.append(f"  {len(bottom)}*0")
write("1.pre", "\n".join(pre) + "\n")

# 1.glb
write("1.glb", f"""\
NPOIN npoinb NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh level_set ljdp stab_matde
  {npoin}  {npoin}  {nelem}  2  3  {ngroup}  0  GIDR  1.0  0  0  0  0  0  99999
valv1
ndivide
NINIT KINIT winit NBLKS NLINK NONSY OUTIP outir outiw neumn equvs type_ABC block_stab nbackf nbspring ebody outind nbackdT ninistn
  0  0  0  1  0  0  0  0  0  0  0  FIX  0  0  0  0  0  0  0
TYPE_PROBLEM TYPE_SOLVER TYPE_LOAD TYPE_NL stabpw nlayer kglb state_change Bparameter balgor upliftin
Q  PARDISO  LOAD  5  0  0  0  0  0  0  0
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
  0  0  0
appear_level(1:ngroup)
  0  0  0
APPEAR_PROCESS
  1  1  1
MATNO_PROCESS
  1  3  2
force_process(1:ngroup)
  0  0  0
average_appear
  2  2  2
gid_u,gid_s,gid_ms,gid_f,gid_rot,gid_v,gid_a,gid_T,gid_P,gid_Pv,gid_ep,gid_Y,gid_FC,gid_Ns,gid_Ss,gid_Mxy,gid_bem,gid_wh,gid_wv,gid_bcs
  1  1  0  0  0  0  0  0  0  0  0  1  0  0  0  0  0  0  0  0
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
Q4    Foundation     5 CO     1 U   ST   PE             2  1  0  1  1  1       0.000E+00  0  0  0
  0  0.0  0.0
  0  0
  2
  1  2
Q4    Joint          5 CO     1 U   ST   PE             4  3  0  1  1  1       2.000E-02  0  0  0
  0  0.0  0.0
  0  0
  2
  1  2
Q4    UpperBlock     5 CO     1 U   ST   PE             6  2  0  1  1  1       0.000E+00  0  0  0
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

# 1.mat: rock + upper block + Goodman joint
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
  3
     material_serial         1
          MECHANICAL           SOLID         1
  1
               SOLID
ELASTIC_ISOTROPIC       2.600E+03       1.000E+00       1.000E+00       2.000E+10       2.500E-01       1.000E-05  0  0  0
  0  0       1.000E+03
     material_serial         2
          MECHANICAL           SOLID         2
  1
               SOLID
ELASTIC_ISOTROPIC       2.400E+03       1.000E+00       1.000E+00       2.500E+10       1.670E-01       1.000E-05  0  0  0
  0  0       1.000E+03
     material_serial         3
          MECHANICAL           SOLID         3
  1
               SOLID
GOODMAN                 0.240E+04       0.100E+01       0.100E+01       0.097E+11       0.250E+00       0.100E-04  0  0  0
  0  0  0  0.100E+04
JANBU  0  0  0  0
  0.48e+5  0.0  0.700E+13  0.990E+00  0.366E+02  0.48e+4  0.100E+06  0.100E+04  0.100E+07  0.100E+06
""")

# 1.LOA, 1.man, 1.sol, auxiliary files
L = []
L.append(" (*.loa) Load data")
L.append("  1")
L.append("  2  LINEAR  0  2")
L.append("  0.0  1.0")
L.append("  1.0  1.0")
L.append(" Define point load")
L.append("  0  0")
L.append(" Define edges for whole analysis")
L.append("  0")
L.append(" Define edge load in each BLKS")
L.append(" edge_load_group,delgroup")
L.append("  0  0")
L.append(" Define body force in each BLKS")
L.append("  9.81000E+00  0.00000E+00  -1.00000E+00  0.00000E+00  -1.00000E+00")
L.append(" Time_curve_for_each_group  1")
L.append("  1  1  1")
L.append(" nbeamload")
L.append("  0")
L.append(" nplateload")
L.append("  0")
write("1.LOA", "\n".join(L) + "\n")

write("1.man", """\
 nincs,cdtest,earthquake_curve(1:ndimn)
  1  0  0  0
  10  1.0  1  1  1  1  1  0  0
  3*1.0e-05
""")

sol = []
for _ in range(200):
    sol.extend([" mtype, ncpu, msglvl", "  -2  4  0", " isdefault", "  0"])
write("1.sol", "\n".join(sol) + "\n")

write("1.ftr", " nforce,ngaps,nforce_gaps,nsafety_gaps\n       0       0       0       0\n")
write("1.opr", " Irecover wgroup\n (output control flags)\n  0  0  0  0  0\n following is for stress output groups\n node ranges per group\n one line for each group\n following is for elements\n following is for gaps\n following is for joints\n")
write("1.nrt", " The interpolation groups: transgroup\n ntransnode and translg for each transgroup\n       0\n")
tem = [" temperature prescribed data","  0"," surface convection edges (nedge)","  0"," surface convection (type 2)"," surface list (1:nsurf)","  0"," pipe cooling info"," algo_pipe=3","  0  3",""]
tem.extend(["  0"]*20)
write("1.tem", "\n".join(tem) + "\n")
write("1.ifs", "nifsgroup\n0\nnabsfgroup\n0\nnabssgroup,exx,uxx,densxx\n0  0  0  0\nifsnedge\n0\n")
write("inp", "restart,relis,sysrelis,ADINA,Uopt_R,gamamax\n0  0  0  0  0  0\nprobn\n1\n1\n")

print("\nAll mini_goodman files generated!")
