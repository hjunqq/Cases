#!/usr/bin/env python3
"""_local_metrics — in-KI fallback for `ki_tools_common.metrics.all_metrics`.

Verified 2026-08-26: `ki_tools_common` is NOT importable on this host (only the three KI
generator scripts exist under models/ki_tools_common/). Every tool therefore does:

    try:
        from ki_tools_common.metrics import all_metrics
    except ImportError:
        from _local_metrics import all_metrics

Same signature -- `all_metrics(obs, sim) -> dict` -- so the tools behave identically once the
shared library becomes importable.

For a structural FEM model the interesting metrics are absolute/relative error against an
analytic or measured value, not the hydrological skill scores; NSE/KGE/PBIAS are included so
the dict shape matches the shared library, but `rel_err_pct` and `max_abs_err` are what the
HSTAR validation convention actually grades on.
"""
from __future__ import annotations

import math


def _pairs(obs, sim):
    o, s = [], []
    for a, b in zip(obs, sim):
        if a is None or b is None:
            continue
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            continue
        if math.isnan(a) or math.isnan(b):
            continue
        o.append(a)
        s.append(b)
    return o, s


def all_metrics(obs, sim):
    """Return the standard metric dict. Missing/NaN pairs are dropped."""
    o, s = _pairs(obs, sim)
    n = len(o)
    if n == 0:
        return {"n": 0}
    mo = sum(o) / n
    ms = sum(s) / n
    sse = sum((a - b) ** 2 for a, b in zip(o, s))
    sst = sum((a - mo) ** 2 for a in o)
    sae = sum(abs(a - b) for a, b in zip(o, s))
    out = {
        "n": n,
        "rmse": math.sqrt(sse / n),
        "mae": sae / n,
        "bias": ms - mo,
        "max_abs_err": max(abs(a - b) for a, b in zip(o, s)),
        "obs_mean": mo,
        "sim_mean": ms,
    }
    denom = max(abs(a) for a in o)
    out["max_rel_err_pct"] = (out["max_abs_err"] / denom * 100.0) if denom else float("nan")
    out["rel_err_pct"] = ((abs(ms - mo) / abs(mo) * 100.0) if mo else float("nan"))
    out["nrmse_pct"] = (out["rmse"] / denom * 100.0) if denom else float("nan")
    out["nse"] = (1.0 - sse / sst) if sst > 0 else float("nan")
    out["pbias"] = ((sum(s) - sum(o)) / sum(o) * 100.0) if sum(o) else float("nan")
    # Pearson r
    do = [a - mo for a in o]
    ds = [b - ms for b in s]
    num = sum(a * b for a, b in zip(do, ds))
    den = math.sqrt(sum(a * a for a in do) * sum(b * b for b in ds))
    r = num / den if den > 0 else float("nan")
    out["r"] = r
    # KGE (Gupta 2009)
    so = math.sqrt(sum(a * a for a in do) / n)
    ss = math.sqrt(sum(b * b for b in ds) / n)
    if mo and so and not math.isnan(r):
        out["kge"] = 1.0 - math.sqrt((r - 1) ** 2 + (ss / so - 1) ** 2 + (ms / mo - 1) ** 2)
    else:
        out["kge"] = float("nan")
    return out


def force_balance_ratio(residual_norm, external_norm):
    """HSTAR's conservation check: ||R|| / ||F_ext|| at the last converged iteration.

    This is the structural-mechanics analogue of `validate_water_balance` -- there is no water
    budget to close in an FEM stress solver, but there IS a global equilibrium residual, and
    HSTAR writes it to probn.chk on every iteration.
    """
    if not external_norm:
        return float("nan")
    return abs(residual_norm) / abs(external_norm)
