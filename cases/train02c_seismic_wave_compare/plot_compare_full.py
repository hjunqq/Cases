import numpy as np, matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['DejaVu Sans']

dt=0.01
def L(p): return np.loadtxt(p)
gb_a=L('earthquake_a.dat'); gb_d=L('earthquake_d.dat')
el_a=L('elcentro/earthquake_a.dat'); el_d=L('elcentro/earthquake_d.dat')
t_a=np.arange(len(gb_a))*dt
gb_c=np.loadtxt('crest_response.txt'); el_c=np.loadtxt('elcentro/crest_response.txt')

fig,ax=plt.subplots(2,2,figsize=(14,8),sharex=True)
C1,C2='#d62728','#1f77b4'

ax[0,0].plot(t_a,gb_a,C1,lw=0.8,label=f'GB artificial (PGA={np.abs(gb_a).max():.2f} m/s²)')
ax[0,0].plot(t_a,el_a,C2,lw=0.8,alpha=0.75,label=f'El-Centro-like (PGA={np.abs(el_a).max():.2f} m/s²)')
ax[0,0].set_title('① Input ground acceleration a_g(t)'); ax[0,0].set_ylabel('a [m/s²]')
ax[0,0].legend(fontsize=9); ax[0,0].grid(alpha=0.3)

ax[0,1].plot(t_a,gb_d*1000,C1,lw=1.0,label=f'GB (PGD={np.abs(gb_d).max()*1000:.1f} mm)')
ax[0,1].plot(t_a,el_d*1000,C2,lw=1.0,alpha=0.75,label=f'El-Centro (PGD={np.abs(el_d).max()*1000:.1f} mm)')
ax[0,1].set_title('② Input ground displacement d_g(t) = ∫∫a_g dt²'); ax[0,1].set_ylabel('d [mm]')
ax[0,1].legend(fontsize=9); ax[0,1].grid(alpha=0.3)

ax[1,0].plot(gb_c[:,0],gb_c[:,1],C1,lw=1.0,label=f'GB crest Ux (peak={np.abs(gb_c[:,1]).max():.2f} mm)')
ax[1,0].plot(el_c[:,0],el_c[:,1],C2,lw=1.0,alpha=0.75,label=f'El-Centro crest Ux (peak={np.abs(el_c[:,1]).max():.2f} mm)')
ax[1,0].set_title('③ Structural response — crest Ux(t)'); ax[1,0].set_ylabel('Ux [mm]'); ax[1,0].set_xlabel('time [s]')
ax[1,0].legend(fontsize=9); ax[1,0].grid(alpha=0.3)

ax[1,1].plot(gb_c[:,0],gb_c[:,2],C1,lw=1.0,label=f'GB crest Uy (peak={np.abs(gb_c[:,2]).max():.2f} mm)')
ax[1,1].plot(el_c[:,0],el_c[:,2],C2,lw=1.0,alpha=0.75,label=f'El-Centro crest Uy (peak={np.abs(el_c[:,2]).max():.2f} mm)')
ax[1,1].set_title('④ Structural response — crest Uy(t)'); ax[1,1].set_ylabel('Uy [mm]'); ax[1,1].set_xlabel('time [s]')
ax[1,1].legend(fontsize=9); ax[1,1].grid(alpha=0.3)

fig.suptitle('GB 51247 artificial  vs  El-Centro-like envelope — input & crest response',fontsize=13,y=1.00)
fig.tight_layout()
fig.savefig('wave_full_compare.png',dpi=140,bbox_inches='tight')
print('saved wave_full_compare.png')

# summary
print(f"GB   PGA={np.abs(gb_a).max():.3f}  PGD={np.abs(gb_d).max()*1000:.2f}mm  |Ux|={np.abs(gb_c[:,1]).max():.3f}mm  |Uy|={np.abs(gb_c[:,2]).max():.3f}mm")
print(f"ElC  PGA={np.abs(el_a).max():.3f}  PGD={np.abs(el_d).max()*1000:.2f}mm  |Ux|={np.abs(el_c[:,1]).max():.3f}mm  |Uy|={np.abs(el_c[:,2]).max():.3f}mm")
