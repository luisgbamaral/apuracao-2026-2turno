"""Two checks that use the real 2026 first-round night (5 Oct 2026), replayed in the order the ballot boxes reached the TSE.

1. Prior: the 2022 runoff. Target: Lula's two-party share against Flávio Bolsonaro in the 2026 first round. A harder
   jump than tonight (four years instead of three weeks), with this year's real counting order and geography.
2. Prior: the 2022 first round. Target: the 2022 runoff, the same jump as tonight, counted in this year's order: each
   2022 section takes the 2026 receipt time of the same section (same state, municipality, zone and number) or, if it
   no longer exists, the time of a random 2026 section of its municipality. The 2022 real order is shown for comparison.
Each prints, moment by moment, the error of every swing method and what the page would have shown (forecast, margin
and chance, with the parameters published in data/model.json).
Run from the repository root after real_order.py 2026:1: python model/test_2026r1.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from plan_b import forecast  # noqa: E402
from scenarios import Election, replay  # noqa: E402

MOMENTS = [0.005, 0.01, 0.02, 0.03, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
CANDIDATES = {"página": "forecast", "logit": "forecast_logit", "encolhido": "forecast_shrink_20000", "vizinhos": "forecast_knn",
              "regressão": "forecast_reg", "capital x interior": "forecast_capital", "faixas de perfil": "forecast_lean",
              "faixas de abstenção": "forecast_abst", "participação por estado": "forecast_turnout_state"}
KEYS = ["uf", "mun", "zona", "secao"]
PARAMS = json.loads(Path("data/model.json").read_text(encoding="utf-8"))  # exactly what is published


def seconds_from(e, order, fill_by_municipality=False):
    """Receipt time of each section of election e, in seconds after the first report."""
    keys = e.keys.astype({"mun": int, "zona": int, "secao": int})
    t = keys.merge(order[KEYS + ["time"]], on=KEYS, how="left").time
    exact = t.notna().mean()
    if fill_by_municipality:  # sections renumbered since: a random time from the same municipality
        rng = np.random.default_rng(0)
        pool = order.dropna(subset=["time"]).groupby(["uf", "mun"]).time.apply(np.array)
        for i in np.flatnonzero(t.isna().to_numpy()):
            times = pool.get((keys.uf.iat[i], keys.mun.iat[i]))
            if times is not None:
                t.iat[i] = rng.choice(times)
    seconds = (t - t.min()).dt.total_seconds().to_numpy()
    print(f"seções com horário da mesma seção: {100 * exact:.1f}%; sem horário nenhum (vão por último): {100 * np.isnan(seconds).mean():.2f}%")
    seconds[np.isnan(seconds)] = np.nanmax(seconds) + 1
    return seconds


def night(e, seconds, title):
    left = np.round(e.share * e.votes)
    right = e.votes - left
    truth = left.sum() / e.votes.sum()
    d = pd.DataFrame(replay(e, left, right, None, seconds, moments=MOMENTS))
    err = pd.DataFrame({k: (100 * (d[v] - d.truth)).abs() for k, v in CANDIDATES.items()} | {"contagem bruta": (100 * (d.partial - d.truth)).abs()})
    err.index = [f"{100 * m:g}%" for m in d.moment]
    print(f"\n######## {title}: Lula {100 * truth:.2f}% dos votos dos dois ########")
    print("erro do % final previsto (pontos), por % apurado")
    print(err.round(2).T.to_string())

    order_idx = np.argsort(seconds, kind="stable")
    cum = np.cumsum(e.electorate[order_idx]) / e.electorate.sum()
    out = []
    for m in MOMENTS:
        c = seconds <= seconds[order_idx][min(np.searchsorted(cum, m), len(seconds) - 1)]
        agg = lambda v: np.bincount(e.unit_of, weights=v * c, minlength=len(e.units))
        snap = e.units[["unit", "uf", "q", "others", "rate_prior", "electorate"]].copy()
        snap["lc"], snap["rc"], snap["ec"] = agg(left), agg(right), agg(e.electorate)
        snap["frac"] = np.bincount(e.unit_of, weights=c, minlength=len(e.units)) / e.units.n
        f = forecast(snap, PARAMS)
        out.append({"apurado": f"{100 * m:g}%", "contagem bruta": round(100 * snap.lc.sum() / (snap.lc + snap.rc).sum(), 2),
                    "previsão": round(100 * f["share"], 2), "± pontos": round(100 * (f["high"] - f["low"]) / 2, 1),
                    "resultado dentro da margem": "sim" if f["low"] <= truth <= f["high"] else "NÃO", "chance de Lula": f"{100 * f['chance']:.0f}%"})
    print("o que a página teria mostrado")
    print(pd.DataFrame(out).to_string(index=False))


order_2026 = pd.read_parquet("model/cache/bweb/order_2026_1t.parquet")
e = Election((2026, 1), (2022, 2))
night(e, seconds_from(e, order_2026), "1. 2º turno de 2022 -> 1º turno de 2026, ordem real de 2026")
e = Election((2022, 2), (2022, 1))
night(e, seconds_from(e, order_2026, fill_by_municipality=True), "2. 1º turno -> 2º turno de 2022, na ordem de chegada de 2026")
night(e, seconds_from(e, pd.read_parquet("model/cache/bweb/order_2022.parquet")), "2b. o mesmo, na ordem real de 2022 (comparação)")
