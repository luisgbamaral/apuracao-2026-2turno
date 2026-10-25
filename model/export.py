"""Writes the parameters and unit priors the page reads.

data/model.json: the uncertainty fitted by model/fit_sigma.py, the floors that keep the start of the night
humble, the blending constants and the first-round share of other candidates by state (2026).
data/units.json: per unit, the prior of the 2026 runoff (the 2026 first round).
Run from the repository root after model/fit_sigma.py: python model/export.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from simulate import MIX, STATE_SWING_FROM, priors  # noqa: E402

FLOORS = {  # humility rules agreed by the review panel (see README)
    "floor_start": 0.025, "floor_start_until": 0.02, "floor_start_end": 0.05,  # 2.5 points until 2% is counted, fading to none at 5%
    "floor_dark": 0.01, "dark_from": 0.5,  # at least 1 point while half of what is left is in states with under 5% counted
}


def main():
    fit = json.loads(Path("model/cache/sigma_forecast.json").read_text(encoding="utf-8"))["final"]
    units = priors(2026, 1)
    g = units.assign(w=units.others * units.electorate_prior).groupby("uf")[["w", "electorate_prior"]].sum()
    params = {k: min(v, 1e12) for k, v in fit["params"].items()}  # an "infinite" shrinkage constant means none
    model = {**params, "inflate": fit["inflate"], **FLOORS, "mix": MIX, "state_swing_from": STATE_SWING_FROM,
             "others_by_state": (g.w / g.electorate_prior).round(6).to_dict(),
             "calibration": json.loads(Path("model/cache/calibration.json").read_text(encoding="utf-8"))}  # from model/recalibrate.py
    Path("data/model.json").write_text(json.dumps(model, indent=1), encoding="utf-8")
    Path("data/units.json").write_text(units.round({"q": 6, "others": 6, "rate_prior": 6}).to_json(orient="records"), encoding="utf-8")
    print(json.dumps({k: v for k, v in model.items() if k != "others_by_state"}, indent=1), f"\n{len(units)} units")


if __name__ == "__main__":
    main()
