"""Fits the uncertainty of the national forecast on the calibration scenarios and validates it across molds.

sigma^2 = R^(2a) (c^2 + kappa^2 D^2) + tau^2 sum_s (R_s (o0 + O_s))^2 n0 / (n0 + Ec_s) + floor^2
  R    expected remaining votes, share of all; R_s the same per state
  D    how different the regional mix of what is left is from what came in (total variation distance)
  Ec_s electorate already counted in the state
  O_s  share of the state's first-round valid votes that went to other candidates: votes that must move in
       the runoff, the main source of uneven swings (38% in 2018, 8% in 2022, 7.8% in 2026)
Errors are taken as Student t with 5 degrees of freedom (heavier tails than normal). Parameters are fitted by
maximum likelihood on one mold (2018 or 2022) and tested on the other, then refitted on both; an inflation
factor then brings the 90% coverage of the worst plausible family of counting orders to at least 80%.
Run from the repository root: python model/fit_sigma.py [estimator column]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, str(Path(__file__).parent))
from simulate import priors  # noqa: E402

DF = 5
COLUMN = sys.argv[1] if len(sys.argv) > 1 else "forecast"
NAMES = ("c", "kappa", "tau", "n0", "floor", "o0", "a")


def load():
    d = pd.concat([pd.read_parquet(f"model/cache/calib_{year}.parquet") for year in (2018, 2022)], ignore_index=True)
    d["error"] = d[COLUMN] - d.truth
    rs = np.stack(d.R_s.to_numpy())
    ec = np.stack(d.Ec_s.to_numpy())
    # Other candidates' first-round share by state, for the mold each row comes from (states in alphabetical order).
    others = {}
    for year in (2018, 2022):
        pr = priors(year, 1)
        g = pr.assign(w=pr.others * pr.electorate_prior).groupby("uf")[["w", "electorate_prior"]].sum()
        others[f"{year} R2"] = (g.w / g.electorate_prior).sort_index().to_numpy()
    o = np.stack([others[e] for e in d.election])
    return d, rs * 1, ec, o


def sigma(theta, d, rs, ec, o):
    c, kappa, tau, n0, floor, o0, a = np.exp(theta)
    state = ((rs * (o0 + o)) ** 2 * n0 / (n0 + ec)).sum(axis=1)
    return np.sqrt(d.R.to_numpy() ** (2 * a) * (c ** 2 + kappa ** 2 * d.D.to_numpy() ** 2) + tau ** 2 * state + floor ** 2)


def fit(d, rs, ec, o):
    nll = lambda th: -(stats.t.logpdf(d.error.to_numpy() / sigma(th, d, rs, ec, o), DF) - np.log(sigma(th, d, rs, ec, o))).sum()
    start = np.log([0.01, 0.01, 0.1, 1e6, 0.0005, 0.05, 1.0])
    return optimize.minimize(nll, start, method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-4, "fatol": 1e-3}).x


def scores(d, s, inflate=1.0):
    s = s * inflate
    z = d.error.to_numpy() / s
    win = (d.truth > 0.5).to_numpy()
    p = stats.t.cdf((d[COLUMN].to_numpy() - 0.5) / s, DF)
    out = {f"cover{int(100 * level)}": float((np.abs(z) <= stats.t.ppf(0.5 + level / 2, DF)).mean()) for level in (0.5, 0.8, 0.9, 0.95)}
    out["brier"] = float(np.mean((p - win) ** 2))
    out["logloss"] = float(-np.mean(np.log(np.clip(np.where(win, p, 1 - p), 1e-6, 1))))
    bins = np.clip((p * 10).astype(int), 0, 9)
    out["ece"] = float(sum((bins == b).sum() * abs(p[bins == b].mean() - win[bins == b].mean()) for b in range(10) if (bins == b).any()) / len(p))
    loser_conf = pd.Series(np.where(win, 1 - p, p)).groupby(d.scenario.to_numpy() * 10 + (d.election == "2022 R2").to_numpy()).max()
    out["wrong_call_95"] = float((loser_conf >= 0.95).mean())
    out["wrong_call_99"] = float((loser_conf >= 0.99).mean())
    return out


def main():
    d, rs, ec, o = load()
    report = {"column": COLUMN, "rows": len(d)}
    for train, test in (("2018 R2", "2022 R2"), ("2022 R2", "2018 R2")):
        a, b = (d.election == train).to_numpy(), (d.election == test).to_numpy()
        theta = fit(d[a], rs[a], ec[a], o[a])
        report[f"fit {train} -> test {test}"] = {"params": dict(zip(NAMES, np.exp(theta).round(6).tolist())),
                                                 "test": scores(d[b].reset_index(drop=True), sigma(theta, d[b], rs[b], ec[b], o[b]))}
    theta = fit(d, rs, ec, o)
    s = sigma(theta, d, rs, ec, o)
    families = {"order tied to lean": d.lean.abs() > 0.3, "order tied to others": d.others.abs() > 0.3, "zones in blocks": d.within.abs() > 0.35,
                "capitals late": d.capital_lag > 0.7, "North/Northeast late": d.north_lag > 0.7, "tight (|truth-0.5|<1pp)": (d.truth - 0.5).abs() < 0.01}
    # One calibration factor, fitted on the whole mixture of orders (not on the worst family), by log score.
    inflate = float(optimize.minimize_scalar(
        lambda lam: -(stats.t.logpdf(d.error.to_numpy() / (lam * s), DF) - np.log(lam * s)).sum(), bounds=(0.5, 3), method="bounded").x)
    report["final"] = {"params": dict(zip(NAMES, np.exp(theta).tolist())), "inflate": inflate, "df": DF,
                       "all": scores(d, s, inflate),
                       "by_family": {k: scores(d[m].reset_index(drop=True), s[m.to_numpy()], inflate) for k, m in families.items()},
                       "by_moment": {str(t): scores(d[d.moment == t].reset_index(drop=True), s[(d.moment == t).to_numpy()], inflate) for t in sorted(d.moment.unique())},
                       "median_sigma_pp_by_moment": (100 * pd.Series(s * inflate).groupby(d.moment.to_numpy()).median()).round(3).to_dict()}
    Path(f"model/cache/sigma_{COLUMN}.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    pick = lambda r: {k: round(v, 3) for k, v in r.items()}
    for k, v in report.items():
        if k.startswith("fit"):
            print(k, v["params"], pick(v["test"]))
    print("final", report["final"]["params"], "inflate", inflate)
    print("all", pick(report["final"]["all"]))
    for k, v in report["final"]["by_family"].items():
        print("  ", k, pick(v))
    print("sigma (pp) by moment", report["final"]["median_sigma_pp_by_moment"])
    for election in ("2018 R2", "2022 R2"):
        m = (d.election == election).to_numpy()
        print("  in-sample", election, pick(scores(d[m].reset_index(drop=True), s[m], inflate)))
    print("coverage90 by moment", {k: round(v["cover90"], 3) for k, v in report["final"]["by_moment"].items()})


if __name__ == "__main__":
    main()
