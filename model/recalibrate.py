"""Recalibrates the chance of winning on the 500 calibration elections, so that "80%" means the favourite won about 80% of the time.

The raw chance (Student t of the forecast over its uncertainty) was too confident between 60% and 90%, mostly in
near ties. For each stage of the count, an isotonic map takes the favourite's raw chance to the share of those
elections the favourite actually won; the page interpolates it between stages and between knots. Scored out of
sample with 5 folds by scenario (each fold's map fitted on the other four), and leaving one mold out. The map
never raises a chance above the raw one: plain isotonic maps reached 100% at a raw 95% and failed across molds.
Writes model/cache/calibration.json, which model/export.py puts in data/model.json.
Run from the repository root after fit_sigma.py: python model/recalibrate.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.isotonic import IsotonicRegression

sys.path.insert(0, str(Path(__file__).parent))
from export import FLOORS  # noqa: E402
from fit_sigma import load, sigma  # noqa: E402
from plan_b import calibrate  # noqa: E402

STAGES = [[0.01, 0.02], [0.05, 0.1], [0.15, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8], [0.9, 0.95]]
KNOTS = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999, 1.0]


def raw_chance(d, rs, ec, o):
    """The page's chance before recalibration, with the published uncertainty and floors."""
    fit = json.loads(Path("model/cache/sigma_forecast.json").read_text(encoding="utf-8"))["final"]
    theta = np.log([fit["params"][k] for k in ("c", "kappa", "tau", "n0", "floor", "o0", "a")])
    s = fit["inflate"] * sigma(theta, d, rs, ec, o)
    c = d.frac_nat.to_numpy()
    s = np.maximum(s, start_floor(c))
    s = np.where(d.dark.to_numpy() >= FLOORS["dark_from"], np.maximum(s, FLOORS["floor_dark"]), s)
    return stats.t.cdf((d.forecast.to_numpy() - 0.5) / s, 5)


def start_floor(counted):
    """Held until floor_start_until is counted, then fading to zero at floor_start_end (no jump)."""
    fade = (FLOORS["floor_start_end"] - counted) / (FLOORS["floor_start_end"] - FLOORS["floor_start_until"])
    return FLOORS["floor_start"] * np.clip(fade, 0, 1)


def fit_map(fav, won):
    """Favourite's raw chance -> share of wins, monotone, never below a coin toss; read at the knots."""
    iso = IsotonicRegression(y_min=0.5, y_max=1.0, increasing=True, out_of_bounds="clip").fit(fav, won)
    return iso.predict(KNOTS)


def apply(maps, centers, raw, counted):
    cal = {"counted": centers, "knots": KNOTS, "values": maps}
    return np.array([calibrate(r, c, cal) for r, c in zip(raw, counted)])


def fit_all(fav, won, moment):
    return [fit_map(fav[np.isin(moment, s)], won[np.isin(moment, s)]) for s in STAGES]


def scores(p, win):
    bins = pd.cut(np.maximum(p, 1 - p), [0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0001], include_lowest=True)
    fav_won = np.where(p >= 0.5, win, ~win)
    table = pd.DataFrame({"disse": np.maximum(p, 1 - p), "venceu": fav_won}).groupby(bins, observed=True).mean().round(3)
    return {"logloss": round(float(-np.mean(np.log(np.clip(np.where(win, p, 1 - p), 1e-6, 1)))), 4),
            "brier": round(float(np.mean((p - win) ** 2)), 4)}, table


def main():
    d, rs, ec, o = load()
    raw = raw_chance(d, rs, ec, o)
    win = (d.truth > 0.5).to_numpy()
    fav = np.maximum(raw, 1 - raw)
    fav_won = np.where(raw >= 0.5, win, ~win)
    moment = d.moment.to_numpy()
    centers = [float(np.mean(s)) for s in STAGES]

    fold = (d.scenario.to_numpy() * 7 + (d.election == "2022 R2").to_numpy()) % 5
    oof = np.empty(len(d))
    for k in range(5):
        tr, te = fold != k, fold == k
        oof[te] = apply(fit_all(fav[tr], fav_won[tr], moment[tr]), centers, raw[te], d.frac_nat.to_numpy()[te])
    for name, p in (("antes", raw), ("recalibrada (5 grupos, fora da amostra)", oof)):
        s, table = scores(p, win)
        print(f"\n=== {name}: {s}"); print(table.T.to_string())
    for tr_mold, te_mold in (("2018 R2", "2022 R2"), ("2022 R2", "2018 R2")):
        tr, te = (d.election == tr_mold).to_numpy(), (d.election == te_mold).to_numpy()
        p = apply(fit_all(fav[tr], fav_won[tr], moment[tr]), centers, raw[te], d.frac_nat.to_numpy()[te])
        print(f"\nmapa de {tr_mold}, testado em {te_mold}: antes {scores(raw[te], win[te])[0]}, depois {scores(p, win[te])[0]}")

    maps = fit_all(fav, fav_won, moment)
    print("\nmapa final (linhas: % apurado no centro da fase; colunas: chance bruta do favorito)")
    print(pd.DataFrame(np.round(maps, 3), index=[f"{100 * c:.1f}%" for c in centers], columns=KNOTS).to_string())
    Path("model/cache/calibration.json").write_text(json.dumps({"counted": centers, "knots": KNOTS, "values": np.round(maps, 4).tolist()}), encoding="utf-8")


if __name__ == "__main__":
    main()
