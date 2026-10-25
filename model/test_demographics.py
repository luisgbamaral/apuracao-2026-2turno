"""Does the electorate profile improve the swing of uncounted municipalities? Tested on the REAL 2018 and 2022 runoffs.

Synthetic shocks are not used here: they are unrelated to education or age, so they could never reward the profile.
Each real runoff is counted in N orders drawn from the calibration families, and three versions of the swing are
compared on the national two-party share: the page's (state mean), a regression on municipal characteristics
without the profile, and the same regression with the profile (education, age, sex).
Gate agreed by the review panel: at least 10% less national error in both years.
Run from the repository root: python model/test_demographics.py N
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from calibrate import ORDER, PRIORS  # noqa: E402
from scenarios import Election, replay, scenario  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
DEMO = ["demo_higher_ed", "demo_low_ed", "demo_young", "demo_old", "demo_women"]
rows = []
for year in (2018, 2022):
    plain = Election((year, 2), (year, 1))
    profiled = Election((year, 2), (year, 1))
    demo = pd.read_parquet(f"model/cache/perfil/demo_{year}.parquet")[["unit"] + DEMO]
    profiled.units = profiled.units.merge(demo, on="unit", how="left")
    profiled.units[DEMO] = profiled.units[DEMO].fillna(profiled.units[DEMO].mean())
    truth = (plain.share * plain.votes).sum() / plain.votes.sum()
    for i in range(N):
        draws = {k: np.random.default_rng(1000 * year + i).uniform(*PRIORS[k]) for k in ORDER}
        for label, e in (("sem perfil", plain), ("com perfil", profiled)):
            rng = np.random.default_rng(1000 * year + i)
            left, right, speed, rank = scenario(e, rng, truth, shocks=(0, 0, 0), order=draws)
            for r in replay(e, left, right, speed, rank, demo=DEMO if label == "com perfil" else None):
                rows.append({"year": year, "scenario": i, "version": label, **{k: r[k] for k in ("moment", "truth", "forecast", "forecast_reg", "forecast_logit", "forecast_clip")}})
d = pd.DataFrame(rows)
d["err_state"] = (d.forecast - d.truth).abs() * 100
d["err_reg"] = (d.forecast_reg - d.truth).abs() * 100
state = d[d.version == "sem perfil"].groupby(["year", "moment"]).err_state.median().rename("média do estado (página)")
reg = d[d.version == "sem perfil"].groupby(["year", "moment"]).err_reg.median().rename("regressão sem perfil")
prof = d[d.version == "com perfil"].groupby(["year", "moment"]).err_reg.median().rename("regressão com perfil")
table = pd.concat([state, reg, prof], axis=1).round(3)
print("erro mediano do % nacional final (pontos), 2º turno real, por % apurado")
print(table.to_string())
summary = table.groupby(level=0).mean()
summary["ganho do perfil sobre a página"] = (1 - summary["regressão com perfil"] / summary["média do estado (página)"]).map("{:.0%}".format)
print("\nmédia sobre os momentos"); print(summary.round(3).to_string())
d.to_parquet("model/cache/test_demographics.parquet")
