"""Golden files for the parity test between model/plan_b.py and src/forecast.js.

Writes model/cache/golden.json: snapshots of synthetic counts (both molds, early to late, random and skewed
orders) with every unit's partial count, the priors used and the Python forecast for each. The page's forecast
must reproduce them (|share diff| < 1e-6, |chance diff| < 1e-4).
Run from the repository root after model/export.py: python model/golden.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from plan_b import forecast  # noqa: E402
from scenarios import Election, scenario  # noqa: E402

MOMENTS = [0.005, 0.02, 0.05, 0.2, 0.4, 0.7, 0.9, 0.99]
ORDERS = [{}, {"north_lag": 1.0, "capital_lag": 1.0, "lean": 0.4, "within": 0.5}]


def main():
    params = json.loads(Path("data/model.json").read_text(encoding="utf-8"))
    cases = []
    for year, seed in ((2022, 1), (2018, 2)):
        e = Election((year, 2), (year, 1))
        rng = np.random.default_rng(seed)
        for order in ORDERS:
            left, right, speed, rank = scenario(e, rng, 0.502, order=order)
            unit_l = np.bincount(e.unit_of, weights=left, minlength=len(e.units))
            for t in MOMENTS:
                lo, hi = 0.0, 1e9
                for _ in range(60):
                    k = (lo + hi) / 2
                    lo, hi = (k, hi) if np.minimum(1, k * speed) @ e.units.electorate / e.units.electorate.sum() < t else (lo, k)
                f = np.minimum(1, k * speed)
                counted = rank <= f[e.unit_of] + 1e-12
                agg = lambda v: np.bincount(e.unit_of, weights=v * counted, minlength=len(e.units))
                snap = e.units[["unit", "uf", "q", "others", "rate_prior", "electorate"]].copy()
                snap["lc"], snap["rc"], snap["ec"] = agg(left), agg(right), agg(e.electorate)
                snap["frac"] = np.bincount(e.unit_of, weights=counted, minlength=len(e.units)) / e.units.n
                snap["l"], snap["r"] = unit_l, 0
                cases.append({"label": f"{year} {'skewed' if order else 'random'} order, {100 * t:g}% counted",
                              "python": forecast(snap, params),
                              "units": e.units.assign(electorate_prior=e.units.electorate)[["unit", "uf", "q", "others", "rate_prior", "electorate_prior"]].to_dict(orient="records"),
                              "tallies": {r.unit: [r.lc, r.rc, r.ec, r.electorate, r.frac] for r in snap.itertuples() if r.frac > 0 or True}})
    Path("model/cache/golden.json").write_text(json.dumps(cases), encoding="utf-8")
    for c in cases:
        print(f"{c['label']:42s} share {c['python']['share']:.5f} chance {c['python']['chance']:.4f} sd {100 * c['python']['sd']:.2f} pp")


if __name__ == "__main__":
    main()
