"""Which swing should the page use for uncounted municipalities? All candidates on the REAL 2018 and 2022 runoffs.

Candidates (columns of simulate.add_features): the page's state-mean swing in points; the same in logit; the state
swing shrunk towards region and nation (two strengths); the swing of the 15 nearest counted municipalities; and a
regression on municipal characteristics. Each runoff is counted
  - in its REAL order: 2022 by the time the TSE received each section's report; 2018 by each ballot box's closing
    time (the 2018 reports have no receipt time), a stand-in that keeps time zones and queues;
  - in N orders drawn from the calibration families.
Gate agreed by the review panel: at least 10% less national error than the page, in both years, without being
worse in the real orders.
Run from the repository root: python model/test_bases.py N
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from calibrate import ORDER, PRIORS  # noqa: E402
from scenarios import Election, replay, scenario  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
MOMENTS = [0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
CANDIDATES = {"página (pontos, média do estado)": "forecast", "logit": "forecast_logit", "encolhido 20 mil": "forecast_shrink_20000",
              "encolhido 200 mil": "forecast_shrink_200000", "vizinhos (15)": "forecast_knn", "regressão": "forecast_reg"}


def real_times(e, year):
    order = pd.read_parquet(f"model/cache/bweb/order_{year}.parquet")
    keys = e.keys.astype({"mun": int, "zona": int, "secao": int})
    t = keys.merge(order[["uf", "mun", "zona", "secao", "time"]], on=["uf", "mun", "zona", "secao"], how="left").time
    seconds = (t - t.min()).dt.total_seconds().to_numpy()
    missing = np.isnan(seconds)
    seconds[missing] = np.nanmax(seconds) + 1  # sections without a report time come last
    return seconds, missing.mean()


rows = []
for year in (2022, 2018):
    e = Election((year, 2), (year, 1))
    truth = (e.share * e.votes).sum() / e.votes.sum()
    left = np.round(e.share * e.votes)
    right = e.votes - left
    times, missing = real_times(e, year)
    print(f"{year}: {100 * missing:.2f}% of sections without a time")
    for r in replay(e, left, right, None, times, moments=MOMENTS):
        rows.append({"year": year, "order": "real", "scenario": -1, **r})
    for i in range(N):
        draws = {k: np.random.default_rng(1000 * year + i).uniform(*PRIORS[k]) for k in ORDER}
        rng = np.random.default_rng(1000 * year + i)
        l, r_, speed, rank = scenario(e, rng, truth, shocks=(0, 0, 0), order=draws)
        for r in replay(e, l, r_, speed, rank, moments=MOMENTS):
            rows.append({"year": year, "order": "sorteada", "scenario": i, **r})
d = pd.DataFrame(rows)
d.to_parquet("model/cache/test_bases.parquet")
err = pd.DataFrame({k: (100 * (d[v] - d.truth)).abs() for k, v in CANDIDATES.items()} | {"contagem bruta": (100 * (d.partial - d.truth)).abs()})
err[["year", "order", "moment"]] = d[["year", "order", "moment"]]
pd.set_option("display.width", 220)
for year in (2022, 2018):
    print(f"\n=== {year}, ordem REAL: erro do % nacional final (pontos) ===")
    print(err[(err.year == year) & (err.order == "real")].set_index("moment").drop(columns=["year", "order"]).round(2).to_string())
summary = err.groupby(["year", "order"]).mean(numeric_only=True).drop(columns="moment")
print("\n=== média sobre os momentos (real) e mediana das médias (sorteadas) ===")
print(summary.round(3).to_string())
