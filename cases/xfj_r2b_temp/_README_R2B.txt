R2-B: Pure temperature forward run
==================================
Created from full copy of E_dam(w+T) (NO hard links — safe for Windows).
Same 1.btl, 1.mat, 1.oit, 1.glb as parent case (uses warm-start X with α=1.23e-5, mat 2 E=50 GPa).
Modifications:
  1.man line 3, 8th field:  cwater = 3 → 0   (disables water pressure loading)
  1.btl iter1:                200 → 1        (single forward pass)
Run hstar.exe in this directory; the resulting 1.flavia.res contains pure-temperature displacements.
