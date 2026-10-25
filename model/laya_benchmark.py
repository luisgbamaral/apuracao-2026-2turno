"""Offline benchmark of Laya (local text model with typed, calibrated answers) against the statistical forecast.

Laya reads a plain-text snapshot of a synthetic count (candidates anonymised as A and B: raw count, share
counted, how much of what is left sits in states that have barely reported) and answers who wins with a
probability. The statistical forecast's chance for the same snapshot comes from the calibration scenarios.
Both are scored on who actually won. Laya cannot run on the static page, so it is only benchmarked here.

Three steps, because Laya lives in its own environment:
  python model/laya_benchmark.py prepare N        (main environment)
  <laya env python> model/laya_benchmark.py ask   (laya environment: only json and laya needed)
  python model/laya_benchmark.py score            (main environment)
"""
import json
import sys
from pathlib import Path

SNAPSHOTS, ANSWERS = Path("model/cache/laya_snapshots.json"), Path("model/cache/laya_answers.json")


def prepare(n):
    import pandas as pd
    d = pd.concat([pd.read_parquet(f"model/cache/calib_{y}.parquet") for y in (2018, 2022)], ignore_index=True)
    d = d.groupby("moment", group_keys=False).apply(lambda g: g.sample(min(len(g), max(1, n // d.moment.nunique())), random_state=0))
    fmt = lambda x: f"{100 * x:.1f}".replace(".", ",")
    rows = [{"key": [r.election, int(r.scenario), float(r.moment)],
             "body": (f"Apuracao do 2o turno presidencial entre o candidato A e o candidato B. Com {fmt(r.frac_nat)}% do eleitorado apurado, "
                      f"o candidato A tem {fmt(r.partial)}% dos votos validos e o candidato B {fmt(1 - r.partial)}%. "
                      f"Do que falta apurar, {fmt(r.dark)}% esta em estados que quase nao apuraram. "
                      "A apuracao costuma mudar de ritmo por regiao, e a contagem parcial pode virar.")} for r in d.itertuples()]
    SNAPSHOTS.write_text(json.dumps(rows), encoding="utf-8")
    print(len(rows), "snapshots")


def ask():
    import truststore
    truststore.inject_into_ssl()
    from laya import Router
    router = Router()
    question = {"vencedor": {"type": "choice", "instructions": "Quem vai vencer o 2o turno quando a apuracao terminar?",
                             "criteria": {"A": "candidato A vence", "B": "candidato B vence"}}}
    out = []
    for row in json.loads(SNAPSHOTS.read_text(encoding="utf-8")):
        answer = router.predict({"body": row["body"]}, question)["answers"]["vencedor"]
        out.append({"key": row["key"], "p_a": answer["probabilities"]["A"]})
    ANSWERS.write_text(json.dumps(out), encoding="utf-8")
    print(len(out), "answers")


def score():
    import numpy as np
    import pandas as pd
    from scipy import stats
    sys.path.insert(0, str(Path(__file__).parent))
    import fit_sigma
    from fit_sigma import NAMES, load, sigma
    fit_sigma.COLUMN = "forecast"  # the module reads its column from the command line
    fit = json.loads(Path("model/cache/sigma_forecast.json").read_text(encoding="utf-8"))["final"]
    d, rs, ec, o = load()
    theta = np.log([max(fit["params"][k], 1e-300) for k in NAMES])
    d["p_model"] = stats.t.cdf((d.forecast - 0.5) / (fit["inflate"] * sigma(theta, d, rs, ec, o)), 5)
    answers = pd.DataFrame([{"election": a["key"][0], "scenario": a["key"][1], "moment": a["key"][2], "p_laya": a["p_a"]}
                            for a in json.loads(ANSWERS.read_text(encoding="utf-8"))])
    m = answers.merge(d, on=["election", "scenario", "moment"])
    win = (m.truth > 0.5).to_numpy()
    rng = np.random.default_rng(0)
    out = {}
    for name, p in (("laya", m.p_laya.to_numpy()), ("model", m.p_model.to_numpy()), ("raw count (leader 99%)", np.where(m.partial > 0.5, 0.99, 0.01))):
        out[name] = {"brier": float(np.mean((p - win) ** 2)), "logloss": float(-np.mean(np.log(np.clip(np.where(win, p, 1 - p), 1e-6, 1)))),
                     "wrong_with_p_above_0.95": int((np.where(win, 1 - p, p) > 0.95).sum())}
    diff = (m.p_laya.to_numpy() - win) ** 2 - (m.p_model.to_numpy() - win) ** 2
    boot = [rng.choice(diff, len(diff)).mean() for _ in range(2000)]
    out["laya minus model brier, 95% interval"] = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
    out["snapshots"] = len(m)
    Path("model/laya_report.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"prepare": lambda: prepare(int(sys.argv[2])), "ask": ask, "score": score}[sys.argv[1]]()
