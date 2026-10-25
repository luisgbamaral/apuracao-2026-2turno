"""Dynamic selection: at each stage of the count, use the method (or capital hybrid) that did best, learned out of year.

Candidates are the swing methods of model/test_bases.py plus hybrids where each state's capital uses another method
and the rest uses the page's base. The selector picks, for each stage (up to 10%, 10-50%, over 50% counted, or for
each single moment), the candidate with the lowest mean error in the training runoff, and is scored on the other
runoff, moment by moment, against the page. Run from the repository root after test_bases.py: python model/test_dynamic.py
"""
import pandas as pd

d = pd.read_parquet("model/cache/test_bases.parquet")
CANDIDATES = [c for c in d.columns if c.startswith("forecast") and c not in ("forecast_clip",) and not c.startswith("forecast_mix")]
NAMES = {"forecast": "página", "forecast_logit": "logit", "forecast_lean": "faixas de perfil", "forecast_capital": "capital x interior",
         "forecast_knn": "vizinhos", "forecast_reg": "regressão", "forecast_shrink_20000": "encolhido 20 mil", "forecast_shrink_200000": "encolhido 200 mil",
         "forecast_hyb_capital": "capital própria + página", "forecast_hyb_lean": "capital por perfil + página", "forecast_hyb_reg": "capital por regressão + página",
         "forecast_hyb_logit": "capital logit + página", "forecast_hyb_knn": "capital por vizinhos + página"}
err = d[["year", "order", "moment"]].copy()
for c in CANDIDATES:
    err[c] = (100 * (d[c] - d.truth)).abs()
stage = lambda m: 0 if m < 0.1 else 1 if m < 0.5 else 2

for rule, key in (("por fase (até 10%, 10-50%, acima de 50%)", err.moment.map(stage)), ("por momento", err.moment)):
    err["key"] = key
    print(f"\n######## seleção {rule} ########")
    rows = []
    for train, test in ((2018, 2022), (2022, 2018)):
        choice = err[err.year == train].groupby("key")[CANDIDATES].mean().idxmin(axis=1)
        print(f"escolhas aprendidas em {train}: " + "; ".join(f"{k}: {NAMES.get(v, v)}" for k, v in choice.items()))
        t = err[err.year == test].copy()
        t["seleção"] = [r[choice[r.key]] for _, r in t.iterrows()]
        for order, g in t.groupby("order"):
            m = g.groupby("moment")[["forecast", "seleção"]].mean()
            rows.append({"testado em": f"{test} {order}", "regra de": train,
                         "momentos melhor": int((m["seleção"] < m.forecast - 0.01).sum()), "momentos pior": int((m["seleção"] > m.forecast + 0.01).sum()),
                         "erro médio página": round(m.forecast.mean(), 3), "erro médio seleção": round(m["seleção"].mean(), 3)})
    print(pd.DataFrame(rows).to_string(index=False))
