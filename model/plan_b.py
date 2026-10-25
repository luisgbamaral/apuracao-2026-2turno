"""Python twin of src/forecast.js: the published forecast, step by step, for validation and parity tests."""
import numpy as np
import pandas as pd
from scipy import stats

from simulate import MIX, REGIONS, STATE_SWING_FROM, add_features, expected_totals, national

T80 = stats.t.ppf(0.9, 5)


def forecast(snap, p):
    """snap: one unit per row with lc, rc, ec, electorate, frac and the priors. p: the parameters of data/model.json."""
    snap = add_features(snap)
    share = national(snap, snap.base)
    total = expected_totals(snap)
    rest = (total - snap.lc - snap.rc).clip(lower=0) / total.sum()
    states = pd.DataFrame({"uf": snap.uf, "rest": rest, "ec": snap.ec, "e": snap.electorate}).groupby("uf").sum()
    uncounted = (snap.electorate - snap.ec).clip(lower=0)
    region = snap.uf.map(REGIONS).to_numpy()
    counted_mix, left_mix = np.bincount(region, weights=snap.ec, minlength=6), np.bincount(region, weights=uncounted, minlength=6)
    distance = 0.5 * np.abs(counted_mix / counted_mix.sum() - left_mix / left_mix.sum()).sum() if counted_mix.sum() > 0 and left_mix.sum() > 0 else 1.0
    others = states.index.map(p["others_by_state"]).to_numpy(dtype=float)
    state = ((states.rest * (p["o0"] + others)) ** 2 * p["n0"] / (p["n0"] + states.ec)).sum()
    sd = p["inflate"] * np.sqrt(states.rest.sum() ** (2 * p["a"]) * (p["c"] ** 2 + p["kappa"] ** 2 * distance ** 2) + p["tau"] ** 2 * state + p["floor"] ** 2)
    counted = snap.ec.sum() / snap.electorate.sum()
    fade = (p["floor_start_end"] - counted) / (p["floor_start_end"] - p["floor_start_until"])
    sd = max(sd, p["floor_start"] * min(max(fade, 0.0), 1.0))
    dark = uncounted[(snap.uf.map(states.ec / states.e) < 0.05).to_numpy()].sum()
    if uncounted.sum() > 0 and dark / uncounted.sum() >= p["dark_from"]:
        sd = max(sd, p["floor_dark"])
    lead = (snap.lc - snap.rc).sum()
    decided = int(np.sign(lead)) if abs(lead) > uncounted.sum() else 0
    chance = (1.0 if decided > 0 else 0.0) if decided else calibrate(float(stats.t.cdf((share - 0.5) / sd, 5)), counted, p["calibration"])
    return {"share": float(share), "low": float(share - T80 * sd), "high": float(share + T80 * sd), "chance": chance,
            "decided": decided, "counted": float(counted), "sd": float(sd)}


def calibrate(raw, counted, cal):
    """The raw chance mapped to how often a favourite with it won in the simulations at this stage, never above the raw one."""
    fav = max(raw, 1 - raw)
    c = min(fav, float(np.interp(counted, cal["counted"], [np.interp(fav, cal["knots"], v) for v in cal["values"]])))
    return c if raw >= 0.5 else 1 - c


assert MIX and STATE_SWING_FROM  # both are read by the page through data/model.json
