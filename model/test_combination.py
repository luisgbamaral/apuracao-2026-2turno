"""Forecast combination: can a weighted mix of the swing candidates beat the page at every share counted?

Weights (non-negative, summing to 1) minimise the squared error of the national share; they may differ by stage of
the count (early <10%, middle 10-50%, late >50%). They are fitted on one runoff and tested on the other, so the score
never comes from the year that set the weights. The equal-weight average is tested too.
Uses the forecasts saved by model/test_bases.py. Run from the repository root: python model/test_combination.py
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

CANDIDATES = {"página": "forecast", "logit": "forecast_logit", "faixas de perfil": "forecast_lean", "capital x interior": "forecast_capital",
              "vizinhos": "forecast_knn", "regressão": "forecast_reg", "encolhido": "forecast_shrink_20000"}
STAGES = [(0, 0.1), (0.1, 0.5), (0.5, 1.01)]

d = pd.read_parquet("model/cache/test_bases.parquet")
d["stage"] = np.select([d.moment.between(lo, hi - 1e-9) for lo, hi in STAGES], range(len(STAGES)))
X_cols = list(CANDIDATES.values())


def fit(train):
    """Convex weights per stage: minimise mean squared error of the national share."""
    weights = {}
    for stage, g in train.groupby("stage"):
        X, y = g[X_cols].to_numpy(), g.truth.to_numpy()
        k = X.shape[1]
        res = minimize(lambda w: np.mean((100 * (X @ w - y)) ** 2), np.full(k, 1 / k), method="SLSQP",  # in points: the optimiser stalls on fractions
                       bounds=[(0, 1)] * k, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}])
        weights[stage] = res.x
    return weights


def apply(weights, g):
    return np.array([g.loc[i, X_cols].to_numpy() @ weights[g.loc[i, "stage"]] for i in g.index])


out = []
for train_year, test_year in ((2018, 2022), (2022, 2018)):
    w = fit(d[d.year == train_year])
    print(f"\npesos ajustados em {train_year} (por fase: <10%, 10-50%, >50%):")
    print(pd.DataFrame({s: np.round(w[s], 2) for s in w}, index=list(CANDIDATES)).to_string())
    test = d[d.year == test_year].copy()
    test["combinação ajustada"] = apply(w, test)
    test["média simples"] = test[X_cols].mean(axis=1)
    out.append(test)
t = pd.concat(out)
methods = {"página": "forecast", "combinação ajustada": "combinação ajustada", "média simples": "média simples"}
err = pd.DataFrame({k: (100 * (t[v] - t.truth)).abs() for k, v in methods.items()})
err[["year", "order", "moment"]] = t[["year", "order", "moment"]]
rows = []
for (year, order), g in err.groupby(["year", "order"]):
    m = g.groupby("moment")[list(methods)].mean()
    print(f"\n=== {year} ordem {order} (pesos de {2018 if year == 2022 else 2022}): erro médio (pontos) por % apurado ===")
    print(m.round(2).T.to_string())
    rows.append({"bloco": f"{year} {order}", **{k: f"{int((m[k] < m['página'] - 0.01).sum())} melhor / {int((m[k] > m['página'] + 0.01).sum())} pior"
                                               for k in methods if k != "página"}})
print("\n=== em quantos dos 14 momentos erra MENOS que a página ===")
print(pd.DataFrame(rows).to_string(index=False))
