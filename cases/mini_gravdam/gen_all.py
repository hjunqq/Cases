"""Generate all hstarYLOrig legacy files for mini gravity dam.
Realistic dimensions: dam 60m high, foundation 80m wide x 40m deep.
Foundation 20 Q4, dam body 12 Q4, 2-block staged construction.
BCs: bottom Uy=0 only, sides Ux=0 only (normal constraints).
"""
import os

outdir = os.path.dirname(os.path.abspath(__file__))

def write(name, content):
    with open(os.path.join(outdir, name), "w") as f:
        f.write(content)
    print(f"  {name}")

# ============================================================
# Mesh: foundation 80m wide x 40m deep + dam 36m wide x 60m high
# Foundation: 5 cols x 4 rows = 20 Q4
# Dam body:   3 cols x 4 rows = 12 Q4
# ============================================================
# Foundation nodes: x=[0,16,32,48,64,80], y=[-40,-30,-20,-10,0]
fx = [0.0, 16.0, 32.0, 48.0, 64.0, 80.0]
fy = [-40.0, -30.0, -20.0, -10.0, 0.0]
# Dam nodes: x=[16,32,48,64] (aligns with foundation grid), y=[0,15,30,45,60]
dam_x = [16.0, 32.0, 48.0, 64.0]
dam_y = [0.0, 15.0, 30.0, 45.0, 60.0]

nodes = {}
nid = 0
fnode = {}
for iy, y in enumerate(fy):
    for ix, x in enumerate(fx):
        nid += 1
        nodes[nid] = (x, y)
        fnode[(ix, iy)] = nid
# 30 foundation nodes

dnode = {}
for iy, y in enumerate(dam_y):
    for ix, x in enumerate(dam_x):
        if iy == 0:
            # share with foundation top row (match x)
            for fix in range(len(fx)):
                if abs(fx[fix] - x) < 0.01:
                    dnode[(ix, iy)] = fnode[(fix, len(fy)-1)]
                    break
        else:
            nid += 1
            nodes[nid] = (x, y)
            dnode[(ix, iy)] = nid

npoin = len(nodes)

# Foundation elements: 5 cols x 4 rows = 20
elements = []
for iy in range(len(fy)-1):
    for ix in range(len(fx)-1):
        n1, n2 = fnode[(ix,iy)], fnode[(ix+1,iy)]
        n3, n4 = fnode[(ix+1,iy+1)], fnode[(ix,iy+1)]
        elements.append((n1, n2, n3, n4, 1))
nfound = len(elements)

# Dam elements: 3 cols x 4 rows = 12
for iy in range(len(dam_y)-1):
    for ix in range(len(dam_x)-1):
        n1, n2 = dnode[(ix,iy)], dnode[(ix+1,iy)]
        n3, n4 = dnode[(ix+1,iy+1)], dnode[(ix,iy+1)]
        elements.append((n1, n2, n3, n4, 2))

nelem = len(elements)
ngroup = 2
nblks = 2
nmats = 2

print(f"Mesh: {npoin} nodes, {nelem} elements (foundation={nfound}, dam={nelem-nfound})")

# ---- Write 1.cor ----
cor = []
for n in sorted(nodes):
    x, y = nodes[n]
    cor.append(f"  {n}  {x:.6f}  {y:.6f}")
write("1.cor", "\n".join(cor) + "\n")

# ---- Write 1.ele ----
ele = []
for eid, (n1,n2,n3,n4,g) in enumerate(elements, 1):
    ele.append(f"  {eid}  {n1}  {n2}  {n3}  {n4}")
write("1.ele", "\n".join(ele) + "\n")

# ---- Write 1.flavia.msh ----
groups_elems = {1: [], 2: []}
for i, (n1,n2,n3,n4,g) in enumerate(elements):
    groups_elems[g].append((i+1, [n1,n2,n3,n4]))
gnames = {1: "Foundation", 2: "DamBody"}
msh = []
for gid in sorted(groups_elems):
    gnodes = sorted(set(n for _,ns in groups_elems[gid] for n in ns))
    msh.append(f" mesh {gnames[gid]} dimension  2  elemtype Quadrilateral  nnode 4")
    msh.append(" coordinates")
    for n in gnodes:
        x, y = nodes[n]
        msh.append(f"  {n:8d}  {x:16.8f}  {y:16.8f}  0.00000000")
    msh.append(" end coordinates")
    msh.append(" elements")
    for eid, ns in groups_elems[gid]:
        msh.append(f"  {eid:8d}  " + "  ".join(str(n) for n in ns) + f"  {gid}")
    msh.append(" end elements")
write("1.flavia.msh", "\n".join(msh) + "\n")

# ---- BCs: normal constraints only ----
# Bottom (y=-40): Uy=0 only (allow horizontal sliding)
bottom = [fnode[(ix, 0)] for ix in range(len(fx))]
# Left (x=0): Ux=0 only (allow vertical movement)
left = [fnode[(0, iy)] for iy in range(len(fy))]
# Right (x=80): Ux=0 only
right = [fnode[(len(fx)-1, iy)] for iy in range(len(fy))]
# All Ux-fixed nodes (sides only, not bottom)
ux_nodes = sorted(set(left + right))
# Uy-fixed nodes (bottom only)
uy_nodes = sorted(bottom)

print(f"BCs: {len(ux_nodes)} Ux fixed (sides), {len(uy_nodes)} Uy fixed (bottom)")

# ---- Write 1.pre (repeat per block) ----
pre_block = []
pre_block.append("'PRESCRIBE SET--NFIXSETS'")
pre_block.append(f"  2  2")
pre_block.append(f"  1  {len(ux_nodes)}  1  0  0  0  0.  0")
pre_block.append("  " + "  ".join(str(n) for n in ux_nodes))
pre_block.append(f"  {len(ux_nodes)}*0")
pre_block.append(f"  2  {len(uy_nodes)}  1  0  0  0  0.  0")
pre_block.append("  " + "  ".join(str(n) for n in uy_nodes))
pre_block.append(f"  {len(uy_nodes)}*0")
pre_str = "\n".join(pre_block) + "\n"
write("1.pre", pre_str + pre_str)  # repeat for 2 blocks

# ---- 1.glb ----
write("1.glb", f"""\
NPOIN npoinb NELEM NDIMN NMATS NGROUP NTLINK outplot KSTAB MAT_curve meshc rmesh level_set ljdp stab_matde
  {npoin}  {npoin}  {nelem}  2  {nmats}  {ngroup}  0  GIDR  0.0  0  0  0  0  0  99999
valv1
ndivide
NINIT KINIT winit NBLKS NLINK NONSY OUTIP outir outiw neumn equvs type_ABC block_stab nbackf nbspring ebody outind nbackdT ninistn
  0  0  0  {nblks}  0  0  0  0  0  0  0  FIX  0  0  0  0  0  0  0
TYPE_PROBLEM TYPE_SOLVER TYPE_LOAD TYPE_NL stabpw nlayer kglb state_change Bparameter balgor upliftin
Q  PROFILE  LOAD  5  0  0  0  0  0  0  0
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
  1  0
  1  1
MATNO_PROCESS
  1  2
  1  2
force_process(1:ngroup)
  0  0
average_appear
  2  2
gid_u,gid_s,gid_ms,gid_f,gid_rot,gid_v,gid_a,gid_T,gid_P,gid_Pv,gid_ep,gid_Y,gid_FC,gid_Ns,gid_Ss,gid_Mxy,gid_bem,gid_wh,gid_wv,gid_bcs
  1  1  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0
res_u,res_s,res_ms,res_f,res_rot,res_v,res_a,res_T,res_P,res_Pv,res_ep,res_Y,res_FC,res_Ns,res_Ss,res_Tv,res_Pa
  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0
Icaddmass,swlifs2006,toth,ifswater,ifsgravity,absorb,alfa_p4,stiff_p4
  0  50.0  50.0  2  9.8  0.6  10.0  1.0E+20
ftcrack,coefMpa,ikindks,doubsig,ktan1,ktan2,nlocalbeam,ndimnrt
  1.5e6  1.0e6  0  2  1.0e8  1.0e8  0  0
ntrans,nlaymif,epsMIFb,gamaMIF,ifixvar0_inpb,camif,dxmif
  0  0  1.0e0  0.02  2  1980.0  25.0
hdam
  0.000  0.000
water_level
  -99.000  60.000
modf_dis_blocks
  0  0
uinitial
  0  1
backf()%
1-ILINKS(I0, Freedom, node1,node2)
1-tLINKS(I0, node1,node2)
1-NGROUP--GROUP INFORMATION
INCLUDE (1) NAME KNAME INDEX CLASS NRFIELDS FIELDID SPECIAL
 SPTYPE NELGROUP MATNO TYPE_ALGO TYPE_STIFF TYPE_ECOINT ilayer elcod_local group_inf uplift_ic liquj
         (2) TYPE_MASS(1:NRFIELDS)
         (3) for each field: nfdof-number of freedom,listdof(1:nfdof)
Q4    Foundation     5 CO     1 U   ST   PE            {nfound}  1  0  1  1  1       0.000E+00  0  0  0
  0  0.0  0.0
  0  0
  2
  1  2
Q4    DamBody        5 CO     1 U   ST   PE            {nelem-nfound}  2  0  1  1  1       0.000E+00  0  0  0
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

# ---- 1.mat: foundation rock + dam concrete (SI units: Pa, kg/m3) ----
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
ELASTIC_ISOTROPIC       2.600E+03       1.000E+00       1.000E+00       2.000E+10       2.500E-01       1.000E-05  0  0  0
  0  0       1.000E+03
     material_serial         2
          MECHANICAL           SOLID         2
  1
               SOLID
ELASTIC_ISOTROPIC       2.400E+03       1.000E+00       1.000E+00       2.500E+10       1.670E-01       1.000E-05  0  0  0
  0  0       1.000E+03
""")

# ---- 1.LOA: gravity only, per block ----
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
for _ in range(nblks):
    L.append(" Define edge load in each BLKS")
    L.append(" edge_load_group,delgroup")
    L.append("  0  0")
    L.append(" Define body force in each BLKS")
    L.append("  9.81000E+00  0.00000E+00  -1.00000E+00  0.00000E+00  -1.00000E+00")
    L.append(f" Time_curve_for_each_group  1")
    L.append("  " + "  ".join(["1"] * ngroup))
    L.append(" nbeamload")
    L.append("  0")
    L.append(" nplateload")
    L.append("  0")
write("1.LOA", "\n".join(L) + "\n")

# ---- 1.man: 2 blocks, tolerance = mdofn+1 = 3 values ----
write("1.man", """\
 nincs,cdtest,earthquake_curve(1:ndimn)
  1  0  0  0
  5  1.0  1  1  1  1  1  0  0
  3*1.0e-05
 nincs,cdtest,earthquake_curve(1:ndimn)
  1  0  0  0
  10  1.0  1  1  1  1  1  0  0
  3*1.0e-05
""")

# ---- 1.sol (PROFILE) ----
sol = []
for _ in range(50):
    sol.extend([" Iafile icond ipdchk ising", "  0  0  1  1"])
write("1.sol", "\n".join(sol) + "\n")

# ---- Auxiliary files ----
write("1.ftr", " nforce,ngaps,nforce_gaps,nsafety_gaps\n       0       0       0       0\n")
write("1.opr", " Irecover wgroup\n (output control flags)\n  0  0  0  0  0\n following is for stress output groups\n node ranges per group\n one line for each group\n following is for elements\n following is for gaps\n following is for joints\n")
write("1.nrt", " The interpolation groups: transgroup\n ntransnode and translg for each transgroup\n       0\n")
tem = [" temperature prescribed data","  0"," surface convection edges (nedge)","  0",
       " surface convection (type 2)"," surface list (1:nsurf)","  0",
       " pipe cooling info"," algo_pipe=3","  0  3",""]
tem.extend(["  0"]*20)
write("1.tem", "\n".join(tem) + "\n")
write("1.ifs", "nifsgroup\n0\nnabsfgroup\n0\nnabssgroup,exx,uxx,densxx\n0  0  0  0\nifsnedge\n0\n")
write("inp", f"restart,relis,sysrelis,ADINA,Uopt_R,gamamax\n0  0  0  0  0  0\nprobn\n1\n{nblks}\n")

print("\nAll files generated!")
