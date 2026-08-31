#!/usr/bin/env python3
"""
hstar_common.py -- metrics and the structural analogue of a water-balance check.

`ki_tools_common` is preferred when importable.  It is NOT present on this host
(`/mnt/disk1/Hydrocraft_server/` does not exist), so a documented local fallback
is provided rather than an invented schema.  See docs/input_preparation.md §1.

`validate_water_balance` has no meaning for a stress analysis.  Its structural
equivalent -- the check that catches unit errors the same way -- is GLOBAL
STATIC EQUILIBRIUM: the sum of support reactions must balance the sum of applied
loads.  `check_equilibrium` implements it and is called after every run.

Self-test:  python3 hstar_common.py --selftest
"""

import math

try:  # authoritative implementation when the Hydrocraft tree is mounted
    from ki_tools_common.metrics import all_metrics as _upstream_metrics
except Exception:  # pragma: no cover - normal on this host
    _upstream_metrics = None


def _pairs(obs, sim):
    o, s = [], []
    for a, b in zip(obs, sim):
        if a is None or b is None:
            continue
        try:
            a = float(a)
            b = float(b)
        except (TypeError, ValueError):
            continue
        if math.isnan(a) or math.isnan(b):
            continue
        o.append(a)
        s.append(b)
    return o, s


def all_metrics(obs, sim):
    """Return {'nse','kge','pbias','rmse','mae','r','n'}.

    n is an int; every other value is a float or None when undefined
    (zero-variance observations make NSE/KGE/r undefined, not 0.0).
    """
    if _upstream_metrics is not None:
        return _upstream_metrics(obs, sim)

    o, s = _pairs(obs, sim)
    n = len(o)
    out = {"nse": None, "kge": None, "pbias": None,
           "rmse": None, "mae": None, "r": None, "n": n}
    if n == 0:
        return out
    mo = sum(o) / n
    ms = sum(s) / n
    sso = sum((x - mo) ** 2 for x in o)
    sse = sum((a - b) ** 2 for a, b in zip(o, s))
    out["rmse"] = math.sqrt(sse / n)
    out["mae"] = sum(abs(a - b) for a, b in zip(o, s)) / n
    if abs(mo) > 0:
        out["pbias"] = 100.0 * sum(b - a for a, b in zip(o, s)) / sum(o) \
            if sum(o) != 0 else None
    if sso > 0:
        out["nse"] = 1.0 - sse / sso
    if n > 1:
        sdo = math.sqrt(sso / n)
        sds = math.sqrt(sum((x - ms) ** 2 for x in s) / n)
        if sdo > 0 and sds > 0:
            cov = sum((a - mo) * (b - ms) for a, b in zip(o, s)) / n
            r = cov / (sdo * sds)
            out["r"] = r
            if mo != 0:
                out["kge"] = 1.0 - math.sqrt(
                    (r - 1) ** 2 + (sds / sdo - 1) ** 2 + (ms / mo - 1) ** 2)
    return out


def rel_error(reference, computed):
    """Signed relative error, the metric a FEM verification is graded on."""
    reference = float(reference)
    computed = float(computed)
    if reference == 0.0:
        return None if computed == 0.0 else float("inf")
    return (computed - reference) / abs(reference)


def max_rel_error(reference, computed):
    """max |relative error| over two aligned sequences, normalised by max|ref|."""
    o, s = _pairs(reference, computed)
    if not o:
        return None
    scale = max(abs(x) for x in o)
    if scale == 0.0:
        return max(abs(b) for b in s)
    return max(abs(a - b) for a, b in zip(o, s)) / scale


def check_equilibrium(reaction_sum, applied_sum, tol=1e-6, label=""):
    """Global static equilibrium -- the structural analogue of a water balance.

    Parameters are per-DOF sequences (Fx, Fy[, Fz]) in newtons.  Returns a dict
    with the residual, the normalising scale and a pass/fail flag.  A residual
    that is not tiny relative to the applied load means the load was not
    delivered to the mesh at all (wrong face list, curve id 0, group excluded by
    APPEAR_PROCESS) -- exactly the failure that otherwise looks like a
    successful, converged, wrong run.
    """
    r = [float(x) for x in reaction_sum]
    a = [float(x) for x in applied_sum]
    if len(r) != len(a):
        raise ValueError("reaction/applied dimension mismatch")
    resid = [ri + ai for ri, ai in zip(r, a)]
    scale = max([abs(x) for x in a] + [abs(x) for x in r] + [1.0])
    norm = max(abs(x) for x in resid) / scale
    return {
        "label": label,
        "reaction_sum": r,
        "applied_sum": a,
        "residual": resid,
        "relative_residual": norm,
        "tolerance": tol,
        "ok": norm <= tol,
        "message": ("equilibrium satisfied" if norm <= tol else
                    "EQUILIBRIUM VIOLATED: |R+F|/scale = %.3e > %.1e -- the "
                    "applied load never reached the mesh, or reactions were "
                    "not written (outfix=0). See triplet dt_013." % (norm, tol)),
    }


def check_displacement_plausibility(u_max, model_size, e_modulus=None):
    """Cheap unit-error detector: |u|max should be a small fraction of L.

    An E given in MPa instead of Pa inflates displacements by 1e6 and the run
    still converges.  See triplet dt_010.
    """
    ratio = abs(float(u_max)) / float(model_size)
    verdict = "ok"
    if ratio > 0.1:
        verdict = ("IMPLAUSIBLE: |u|max is %.1f%% of the model size. Check that "
                   "E is in Pa (not MPa/GPa) and loads in N/Pa." % (100 * ratio))
    elif ratio < 1e-14:
        verdict = ("SUSPICIOUS: |u|max is ~0. The load was probably never "
                   "applied (time-curve id 0, or empty face list).")
    return {"u_max": float(u_max), "model_size": float(model_size),
            "ratio": ratio, "verdict": verdict, "ok": verdict == "ok",
            "e_modulus": e_modulus}


def _selftest():
    m = all_metrics([1, 2, 3, 4], [1.1, 1.9, 3.05, 3.9])
    assert m["n"] == 4 and m["nse"] > 0.99, m
    assert set(m) == {"nse", "kge", "pbias", "rmse", "mae", "r", "n"}
    assert all_metrics([], [])["n"] == 0
    assert abs(rel_error(2.0, 2.2) - 0.1) < 1e-12
    eq = check_equilibrium([0.0, 1000.0], [0.0, -1000.0])
    assert eq["ok"], eq
    bad = check_equilibrium([0.0, 1000.0], [0.0, -10.0])
    assert not bad["ok"]
    assert not check_displacement_plausibility(5.0, 10.0)["ok"]
    assert check_displacement_plausibility(1e-5, 10.0)["ok"]
    print("hstar_common selftest OK (upstream ki_tools_common: %s)"
          % ("present" if _upstream_metrics else "absent, using local fallback"))


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
