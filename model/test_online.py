"""Online weights learned during the night itself (Hedge, exponential weights), tested on the real 2018 and 2022 runoffs.

At every new batch of the count, each swing method is scored on the votes that just arrived: what it predicted for the
remaining votes of each municipality at the previous batch, against what those municipalities then reported. Methods
that predicted the new votes better gain weight; the forecast is the weighted mean of the methods' national forecasts.
Weights start leaning on the page's method (prior PRIOR), and only move if the night itself says another method fits.
Nothing is learned across years: each night starts from the same prior.
Run from the repository root: python model/test_online.py N_RANDOM_ORDERS
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from calibrate import ORDER, PRIORS  # noqa: E402
from scenarios import Election, scenario  # noqa: E402
from simulate import add_features, national, weight  # noqa: E402
from test_bases import real_times  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
MOMENTS = [round(x, 4) for x in np.concatenate([[0.005, 0.01, 0.02, 0.03, 0.05], np.arange(0.075, 0.976, 0.025)])]
METHODS = {"página": "base", "logit": "base_logit", "faixas": "base_lean", "encolhido": "base_shrink_20000", "regressão": "base_reg",
           "capital": "base_capital", "vizinhos": "base_knn"}
PRIOR = {"página": 0.5} | {m: 0.5 / (len(METHODS) - 1) for m in METHODS if m != "página"}
ETAS = (0.5, 1.0, 2.0, 4.0)  # learning rates, scored in points of the new votes' share


def night(e, left, right, counted_at):
    """Per moment: truth, each method's national forecast and its error on the votes that arrived since the last moment."""
    truth = left.sum() / (left.sum() + right.sum())
    unit_l = np.bincount(e.unit_of, weights=left, minlength=len(e.units))
    unit_r = np.bincount(e.unit_of, weights=right, minlength=len(e.units))
    previous, rows = None, []
    for t in MOMENTS:
        counted = counted_at(t)
        agg = lambda v: np.bincount(e.unit_of, weights=v * counted, minlength=len(e.units))
        snap = e.units[["unit", "uf", "q", "others", "rate_prior", "electorate"]].copy()
        snap["l"], snap["r"] = unit_l, unit_r
        snap["lc"], snap["rc"], snap["ec"] = agg(left), agg(right), agg(e.electorate)
        snap["frac"] = np.bincount(e.unit_of, weights=counted, minlength=len(e.units)) / e.units.n
        snap = add_features(snap)
        votes = (snap.lc + snap.rc).to_numpy()
        w = weight(snap).to_numpy()
        partial = np.where(votes > 0, snap.lc / np.maximum(votes, 1), 0)
        rest = {m: w * partial + (1 - w) * snap[c].to_numpy() for m, c in METHODS.items()}
        row = {"moment": t, "truth": truth, **{f"f_{m}": national(snap, snap[c]) for m, c in METHODS.items()}}
        if previous is not None:
            new_votes = votes - previous["votes"]
            new_left = snap.lc.to_numpy() - previous["lc"]
            if new_votes.sum() > 0:
                for m in METHODS:
                    row[f"e_{m}"] = 100 * ((previous["rest"][m] * new_votes).sum() - new_left.sum()) / new_votes.sum()
        rows.append(row)
        previous = {"votes": votes, "lc": snap.lc.to_numpy(), "rest": rest}
    return rows


def hedge(df, eta):
    """Weighted forecast per moment, weights updated with the increment errors seen up to that moment."""
    logw = np.log(np.array([PRIOR[m] for m in METHODS]))
    out = []
    for _, r in df.iterrows():
        if f"e_{'página'}" in r and not np.isnan(r.get("e_página", np.nan)):
            logw -= eta * np.array([r[f"e_{m}"] ** 2 for m in METHODS])
        w = np.exp(logw - logw.max())
        w /= w.sum()
        out.append(float(np.dot(w, [r[f"f_{m}"] for m in METHODS])))
    return out


def main():
    rows = []
    for year in (2022, 2018):
        e = Election((year, 2), (year, 1))
        truth = (e.share * e.votes).sum() / e.votes.sum()
        left = np.round(e.share * e.votes)
        right = e.votes - left
        times, _ = real_times(e, year)
        order = np.argsort(times, kind="stable")
        cum = np.cumsum(e.electorate[order]) / e.electorate.sum()
        real = lambda t: times <= times[order][min(np.searchsorted(cum, t), len(times) - 1)]
        for r in night(e, left, right, real):
            rows.append({"year": year, "order": "real", "scenario": -1, **r})
        for i in range(N):
            draws = {k: np.random.default_rng(1000 * year + i).uniform(*PRIORS[k]) for k in ORDER}
            l, r_, speed, rank = scenario(e, np.random.default_rng(1000 * year + i), truth, shocks=(0, 0, 0), order=draws)

            def at(t, speed=speed, rank=rank):
                lo, hi = 0.0, 1e9
                for _ in range(60):
                    k = (lo + hi) / 2
                    lo, hi = (k, hi) if np.minimum(1, k * speed) @ e.units.electorate / e.units.electorate.sum() < t else (lo, k)
                return rank <= np.minimum(1, k * speed)[e.unit_of] + 1e-12

            for r in night(e, l, r_, at):
                rows.append({"year": year, "order": "sorteada", "scenario": i, **r})
            print(year, i, flush=True)
    d = pd.DataFrame(rows)
    d.to_parquet("model/cache/test_online.parquet")
    for eta in ETAS:
        d[f"hedge_{eta}"] = pd.concat([pd.Series(hedge(g, eta), index=g.index) for _, g in d.groupby(["year", "order", "scenario"])])
    summary = []
    for (year, order), g in d.groupby(["year", "order"]):
        err = lambda c: (100 * (g[c] - g.truth)).abs().groupby(g.moment).mean()
        page = err("f_página")
        for eta in ETAS:
            h = err(f"hedge_{eta}")
            summary.append({"bloco": f"{year} {order}", "eta": eta, "momentos melhor": int((h < page - 0.01).sum()), "momentos pior": int((h > page + 0.01).sum()),
                            "de": len(page), "erro médio página": round(page.mean(), 3), "erro médio hedge": round(h.mean(), 3)})
    print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    main()
