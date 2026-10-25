"""Trains the election-night forecast and exports it for the page.

Data: replayed counts (simulate.py) of the 2018 and 2022 runoffs, each with its own first round as prior.
Target: a unit's final two-party share minus its base (prior share plus the swing seen so far in its state,
or nationally while the state has barely reported): trees cannot extrapolate the level of a new election,
so the base carries the level and the model learns the corrections. Weight: the unit's final two-party votes.
Selection: XGBoost, LightGBM, CatBoost and random forest, each tuned by Optuna with leave-one-election-out
cross-validation (train on 2018, test on 2022, and the reverse); the baseline is prior + national swing.
Calibration: the 2026 first round, replayed with the 2022 first round as prior, never seen in tuning.
Outputs: data/model.json (trees of the chosen model, uncertainty of the national forecast by share counted)
and data/units.json (prior of every unit for the 2026 runoff: the 2026 first round).
Run from the repository root: python model/train.py
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import optuna
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from simulate import FEATURES, MOMENTS, national, priors, snapshots  # noqa: E402

TRIALS = 20
RUNOFFS = {2018: ((2018, 2), (2018, 1)), 2022: ((2022, 2), (2022, 1))}
CALIBRATION = ((2026, 1), (2022, 1))
REPORT = Path("model/report.json")
optuna.logging.set_verbosity(optuna.logging.WARNING)


def matrix(df):
    """Features with no missing values: an uncounted unit or state carries no partial result and no swing."""
    x = df[FEATURES].copy()
    x["p"] = x.p.fillna(df.q)
    for column in ("d", "swing_state", "swing_nat", "local", "state_gap"):
        x[column] = x[column].fillna(0)
    return x.to_numpy(dtype=np.float32)


def build(seed_list):
    data = {year: snapshots(target, prior, seeds=seed_list) for year, (target, prior) in RUNOFFS.items()}
    return {year: d[d.frac < 1].reset_index(drop=True) for year, d in data.items()}


def make(name, params):
    if name == "xgboost":
        from xgboost import XGBRegressor
        return XGBRegressor(tree_method="hist", n_jobs=-1, **params)
    if name == "lightgbm":
        from lightgbm import LGBMRegressor
        return LGBMRegressor(verbose=-1, n_jobs=-1, **params)
    if name == "catboost":
        from catboost import CatBoostRegressor
        return CatBoostRegressor(verbose=0, thread_count=-1, **params)
    from sklearn.ensemble import RandomForestRegressor
    return RandomForestRegressor(n_jobs=-1, random_state=0, **params)


def space(name, trial):
    if name == "xgboost":
        return dict(n_estimators=trial.suggest_int("n_estimators", 100, 400), max_depth=trial.suggest_int("max_depth", 3, 7),
                    learning_rate=trial.suggest_float("learning_rate", 0.02, 0.2, log=True), subsample=trial.suggest_float("subsample", 0.6, 1),
                    colsample_bytree=trial.suggest_float("colsample_bytree", 0.6, 1), min_child_weight=trial.suggest_float("min_child_weight", 1, 1e4, log=True),
                    reg_lambda=trial.suggest_float("reg_lambda", 1e-2, 100, log=True))
    if name == "lightgbm":
        return dict(n_estimators=trial.suggest_int("n_estimators", 100, 400), num_leaves=trial.suggest_int("num_leaves", 8, 64),
                    learning_rate=trial.suggest_float("learning_rate", 0.02, 0.2, log=True), subsample=trial.suggest_float("subsample", 0.6, 1), subsample_freq=1,
                    colsample_bytree=trial.suggest_float("colsample_bytree", 0.6, 1), min_child_samples=trial.suggest_int("min_child_samples", 20, 2000, log=True),
                    reg_lambda=trial.suggest_float("reg_lambda", 1e-2, 100, log=True))
    if name == "catboost":
        return dict(iterations=trial.suggest_int("iterations", 100, 400), depth=trial.suggest_int("depth", 3, 7),
                    learning_rate=trial.suggest_float("learning_rate", 0.02, 0.2, log=True), l2_leaf_reg=trial.suggest_float("l2_leaf_reg", 1, 30, log=True))
    return dict(n_estimators=trial.suggest_int("n_estimators", 50, 150), max_depth=trial.suggest_int("max_depth", 6, 14),
                min_samples_leaf=trial.suggest_int("min_samples_leaf", 5, 200, log=True), max_features=trial.suggest_float("max_features", 0.4, 1),
                max_samples=trial.suggest_float("max_samples", 0.2, 0.6))


def fit(name, params, frames):
    df = pd.concat(frames, ignore_index=True)
    model = make(name, params)
    model.fit(matrix(df), (df.y - df.base).to_numpy(), sample_weight=(df.l + df.r).to_numpy())
    return model


def rmse(model, df):
    error = model.predict(matrix(df)) + df.base - df.y
    return math.sqrt(np.average(error ** 2, weights=df.l + df.r))


def loeo(name, params, data):
    """Leave one election out: mean weighted RMSE of the unit shares over the two held-out runoffs."""
    return np.mean([rmse(fit(name, params, [data[a]]), data[b]) for a, b in ((2018, 2022), (2022, 2018))])


def national_errors(predict, frames):
    """National two-party share forecast minus the final result, per replay and moment."""
    out = []
    for label, df in frames.items():
        for (seed, moment), g in df.groupby(["seed", "moment"]):
            truth = g.l.sum() / (g.l.sum() + g.r.sum())
            out.append({"vote": label, "seed": seed, "moment": moment, "frac_nat": g.frac_nat.iloc[0],
                        "error": national(g, predict(g)) - truth, "partial_error": g.lc.sum() / (g.lc.sum() + g.rc.sum()) - truth})
    return pd.DataFrame(out)


def main():
    t0 = time.time()
    tune = build((0,))
    print(f"tuning data: {[len(d) for d in tune.values()]} rows ({time.time() - t0:.0f}s)")
    results = {}
    for label, guess in (("baseline: prior + national swing", lambda d: d.q + d.swing_nat.fillna(0)), ("baseline: prior + state swing", lambda d: d.base)):
        results[label] = {"loeo_rmse": np.mean([math.sqrt(np.average((guess(d) - d.y) ** 2, weights=d.l + d.r)) for d in tune.values()])}
        print(f"{label}: RMSE {results[label]['loeo_rmse']:.5f}")
    for name in ("xgboost", "lightgbm", "catboost", "random_forest"):
        study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=0))
        study.optimize(lambda trial: loeo(name, space(name, trial), tune), n_trials=TRIALS, timeout=600)
        results[name] = {"loeo_rmse": study.best_value, "params": study.best_params, "trials": len(study.trials)}
        print(f"{name}: RMSE {study.best_value:.5f} after {len(study.trials)} trials ({time.time() - t0:.0f}s)")
    best = min((n for n in results if not n.startswith("baseline")), key=lambda n: results[n]["loeo_rmse"])
    params = results[best]["params"] | ({"subsample_freq": 1} if best == "lightgbm" else {})
    print("best:", best)

    full = build((0, 1, 2))
    oof = {}
    for a, b in ((2018, 2022), (2022, 2018)):
        model = fit(best, params, [full[a]])
        oof[f"{b} runoff (trained on {a})"] = (model, full[b])
    errors = pd.concat([national_errors(lambda g, m=m: g.base + m.predict(matrix(g)), {k: d}) for k, (m, d) in oof.items()])
    base_errors = pd.concat([national_errors(lambda g: g.base, {k: d}) for k, (_, d) in oof.items()])

    final = fit(best, params, list(full.values()))
    calib = snapshots(*CALIBRATION, seeds=(0, 1, 2))
    calib = calib[calib.frac < 1].reset_index(drop=True)
    calib_errors = national_errors(lambda g: g.base + final.predict(matrix(g)), {"2026 first round (calibration)": calib})
    calib_base = national_errors(lambda g: g.base, {"2026 first round (calibration)": calib})

    # Uncertainty of the national forecast as a function of the share counted: sigma(t) = max(floor, k * sqrt(1 - t)),
    # k from the pooled out-of-election and calibration errors.
    pooled = pd.concat([errors, calib_errors])
    k = math.sqrt(np.mean(pooled.error ** 2 / (1 - pooled.frac_nat)))
    report = {"models": results, "best": best, "seconds": round(time.time() - t0),
              "national_abs_error_pp": {
                  "model, runoffs held out": errors.groupby("moment").error.apply(lambda e: round(100 * e.abs().mean(), 3)).to_dict(),
                  "baseline, runoffs held out": base_errors.groupby("moment").error.apply(lambda e: round(100 * e.abs().mean(), 3)).to_dict(),
                  "partial count, runoffs": errors.groupby("moment").partial_error.apply(lambda e: round(100 * e.abs().mean(), 3)).to_dict(),
                  "model, 2026 first round": calib_errors.groupby("moment").error.apply(lambda e: round(100 * e.abs().mean(), 3)).to_dict(),
                  "baseline, 2026 first round": calib_base.groupby("moment").error.apply(lambda e: round(100 * e.abs().mean(), 3)).to_dict()},
              "sigma_k": k}
    REPORT.write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
    print(json.dumps(report["national_abs_error_pp"], indent=1))
    print("sigma k:", k)
    import joblib
    joblib.dump({"name": best, "params": params, "model": final, "k": k}, "model/cache/final.joblib")


if __name__ == "__main__":
    main()
