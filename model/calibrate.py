"""Runs many scenarios (synthetic elections x counting orders) and records the national forecast error at each moment.

Scenario parameters are drawn from ranges (PRIORS), so the errors cover the orders the night may bring rather
than one assumed order. The output feeds the uncertainty model of the page (fit_sigma) and its validation.
Run from the repository root: python model/calibrate.py N_SCENARIOS SEED MOLD_YEAR OUT.parquet
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from scenarios import Election, replay, scenario  # noqa: E402

INFLATE = 1.25  # 2026 is a regime not seen in the molds
PRIORS = {  # (low, high) of a uniform draw per scenario; shocks in points of share
    "region_shock": (0.5 * INFLATE, 1.5 * INFLATE), "state_shock": (0.5 * INFLATE, 1.5 * INFLATE), "unit_shock": (1.5 * INFLATE, 2.5 * INFLATE),
    "state_sd": (0.2, 0.6), "region_sd": (0.0, 0.6), "north_lag": (0.0, 1.0), "size": (0.0, 0.3), "capital_lag": (0.0, 1.0),
    "lean": (-0.4, 0.4), "others": (-0.4, 0.4), "within": (-0.5, 0.5), "noise": (0.3, 0.6),
}
ORDER = ("state_sd", "region_sd", "north_lag", "size", "capital_lag", "lean", "others", "within", "noise")


def target(rng):
    """Final two-party share: half the scenarios within one point of a tie, where calibration matters most."""
    u = rng.random()
    return rng.uniform(0.49, 0.51) if u < 0.5 else rng.uniform(0.47, 0.53) if u < 0.8 else rng.uniform(0.44, 0.56)


def run(n, seed, e):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        p = {k: rng.uniform(*v) for k, v in PRIORS.items()} | {"target_share": target(rng)}
        left, right, speed, rank = scenario(e, rng, p["target_share"], shocks=(p["region_shock"], p["state_shock"], p["unit_shock"]),
                                            order={k: p[k] for k in ORDER})
        for r in replay(e, left, right, speed, rank):
            rows.append({"scenario": i, "election": e.label, **p, **r})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    n, seed, year, out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    df = run(n, seed, Election((year, 2), (year, 1)))
    df.to_parquet(out)
    for col in ("forecast", "forecast_reg"):
        err = 100 * (df[col] - df.truth)
        print(col, err.abs().groupby(df.moment).quantile([0.5, 0.9]).unstack().round(2).to_string())
