"""Scenario engine: synthetic elections counted in many different orders, to measure the forecast's errors.

A scenario takes a real runoff (sections of 2018 or 2022) and
  1. moves its result in logit space by national, regional, state and municipal shocks, so the winner and the
     margin vary (tight races included) while the geography stays real;
  2. counts it in an order drawn from families seen on Brazilian nights: states and regions reporting in waves,
     big municipalities late, order correlated with a unit's lean or with its swing, and sections inside a
     municipality arriving in an order correlated with how they vote.
At each moment the page's forecast (base, plus the model if given) is compared with the scenario's final result.
"""
import numpy as np
import pandas as pd

from simulate import REGIONS, add_features, expected_totals, load, national, priors

REGION = {**dict.fromkeys(["ac", "am", "ap", "pa", "ro", "rr", "to"], 0), **dict.fromkeys(["al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se"], 1),
          **dict.fromkeys(["df", "go", "ms", "mt"], 2), **dict.fromkeys(["es", "mg", "rj", "sp"], 3), **dict.fromkeys(["pr", "rs", "sc"], 4), "zz": 5}
MIX_GRID = (0.2, 1.5, 4.0, float("inf"))  # alternatives to MIX for the weight of a unit's partial count; inf = base only
MOMENTS = [0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
logit = lambda p: np.log(p / (1 - p))
expit = lambda x: 1 / (1 + np.exp(-x))


class Election:
    """Sections of one real runoff with its first-round prior, indexed once for fast replays."""

    def __init__(self, target, prior):
        s = load(*target)
        pr = priors(*prior)
        self.units = s.groupby("unit", as_index=False).agg(uf=("uf", "first"), electorate=("electorate", "sum"), n=("secao", "size"))
        self.units = self.units.merge(pr.drop(columns="uf"), on="unit", how="left")
        for column in ("q", "others", "rate_prior"):
            self.units[column] = self.units[column].fillna(self.units.groupby("uf")[column].transform("mean"))
        self.unit_of = pd.Index(self.units.unit).get_indexer(s.unit)
        self.zone_of = pd.Index((s.unit + "-" + s.zona.astype(str)).unique()).get_indexer(s.unit + "-" + s.zona.astype(str))
        self.state_of = pd.Index(sorted(self.units.uf.unique())).get_indexer(self.units.uf)
        self.region_of = self.units.uf.map(REGION).to_numpy()
        self.votes = (s.l + s.r).to_numpy(dtype=float)
        self.share = np.clip(np.where(self.votes > 0, s.l / np.maximum(self.votes, 1), 0.5), 0.01, 0.99)
        self.electorate = s.electorate.to_numpy(dtype=float)
        self.label = f"{target[0]} R{target[1]}"


PP = 0.04  # one point of share is about 0.04 in logit near 50%


def scenario(e: Election, rng, target_share, shocks=(1.0, 1.0, 2.0), order=None):
    """Draws one synthetic election and one counting order.

    Result: the real runoff moved in logit by regional, state and municipal shocks (in points; municipal ones
    with heavy tails, larger in small municipalities), then by a national shift that lands the two-party share
    on target_share.
    Order: speed by state and region (North and Northeast can lag), big municipalities and capitals later,
    abroad last, speed correlated with the unit's prior lean and its share of other candidates, and sections
    inside a unit arriving in an order correlated with how they vote.
    """
    region_pp, state_pp, unit_pp = shocks
    n_units = len(e.units)
    small = (e.units.electorate < 20000).to_numpy()
    shift = (rng.normal(0, region_pp * PP, 6)[e.region_of] + rng.normal(0, state_pp * PP, e.state_of.max() + 1)[e.state_of]
             + rng.standard_t(4, n_units) * unit_pp * PP / np.sqrt(2) * (1 + 0.5 * small))[e.unit_of]
    x = logit(e.share) + shift
    lo, hi = -2.0, 2.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if (expit(x + mid) * e.votes).sum() / e.votes.sum() < target_share else (lo, mid)
    x = x + (lo + hi) / 2
    left = np.round(expit(x) * e.votes)
    right = e.votes - left
    o = order or {}
    unit_left = np.bincount(e.unit_of, weights=left, minlength=n_units)
    unit_votes = np.bincount(e.unit_of, weights=e.votes, minlength=n_units)
    y = unit_left / np.maximum(unit_votes, 1)
    z = lambda v: (v - np.average(v, weights=e.units.electorate)) / np.sqrt(np.cov(v, aweights=e.units.electorate))
    lean, others = z(e.units.q.to_numpy()), z(e.units.others.to_numpy())
    capital = e.units.electorate.to_numpy() == e.units.groupby("uf").electorate.transform("max").to_numpy()
    log_speed = (rng.normal(0, o.get("state_sd", 0.35), e.state_of.max() + 1)[e.state_of]
                 + rng.normal(0, o.get("region_sd", 0.3), 6)[e.region_of]
                 - o.get("north_lag", 0.0) * np.isin(e.region_of, (0, 1))
                 - o.get("size", 0.15) * np.log(e.units.electorate.clip(lower=1)).to_numpy()
                 - o.get("capital_lag", 0.0) * capital
                 + o.get("lean", 0.0) * lean + o.get("others", 0.0) * others
                 + rng.normal(0, o.get("noise", 0.4), n_units))
    log_speed[e.units.uf.to_numpy() == "zz"] = log_speed.min() - 1  # abroad always comes last
    # Inside a municipality, electoral zones come in blocks (whole neighbourhoods), in an order correlated by
    # "within" with how each zone votes against its municipality; sections inside a zone come at random.
    # A municipality with a single zone is unaffected.
    zone_left = np.bincount(e.zone_of, weights=left)
    zone_votes = np.bincount(e.zone_of, weights=e.votes)
    zone_dev = logit(np.clip(zone_left / np.maximum(zone_votes, 1), 0.01, 0.99)) - logit(np.clip(y, 0.01, 0.99))[pd.Series(e.unit_of).groupby(e.zone_of).first().to_numpy()]
    rho = o.get("within", 0.0)
    zone_key = rho * zone_dev / max(zone_dev.std(), 1e-9) + np.sqrt(1 - rho ** 2) * rng.normal(size=len(zone_dev))
    key = zone_key[e.zone_of] + 1e-3 * rng.random(len(e.votes))
    rank = pd.Series(key).groupby(e.unit_of).rank(pct=True).to_numpy()
    return left, right, np.exp(log_speed), rank


def replay(e: Election, left, right, speed, rank, moments=MOMENTS, correct=None, demo=None):
    """National forecast and the truth at each moment of one counted scenario."""
    units = e.units
    truth = left.sum() / (left.sum() + right.sum())
    unit_l = np.bincount(e.unit_of, weights=left, minlength=len(units))
    unit_r = np.bincount(e.unit_of, weights=right, minlength=len(units))
    out = []
    for t in moments:
        lo, hi = 0.0, 1e9
        for _ in range(60):
            k = (lo + hi) / 2
            share = np.minimum(1, k * speed) @ units.electorate / units.electorate.sum()
            lo, hi = (k, hi) if share < t else (lo, k)
        f = np.minimum(1, k * speed)
        counted = rank <= f[e.unit_of] + 1e-12
        agg = lambda v: np.bincount(e.unit_of, weights=v * counted, minlength=len(units))
        snap = units[["unit", "uf", "q", "others", "rate_prior", "electorate"] + list(demo or [])].copy()
        snap["l"], snap["r"] = unit_l, unit_r
        snap["lc"], snap["rc"], snap["ec"] = agg(left), agg(right), agg(e.electorate)
        snap["frac"] = np.bincount(e.unit_of, weights=counted, minlength=len(units)) / units.n
        snap = add_features(snap)
        guess = snap.base if correct is None else snap.base + correct(snap)
        remaining = snap.electorate - snap.ec
        total = expected_totals(snap)
        rest = (total - snap.lc - snap.rc).clip(lower=0) / total.sum()  # each unit's expected remaining votes, share of all
        by_state = pd.DataFrame({"uf": snap.uf, "rest": rest, "ec": snap.ec}).groupby("uf").sum()
        region = snap.uf.map(REGIONS).to_numpy()
        counted_mix = np.bincount(region, weights=snap.ec, minlength=6)
        rest_mix = np.bincount(region, weights=remaining, minlength=6)
        # How different what is left is from what came in: total-variation distance between their regional mixes
        tv = 0.5 * np.abs(counted_mix / counted_mix.sum() - rest_mix / rest_mix.sum()).sum() if counted_mix.sum() > 0 and rest_mix.sum() > 0 else 1.0
        out.append({"moment": t, "frac_nat": snap.frac_nat.iloc[0], "forecast": national(snap, guess), "truth": truth,
                    "forecast_reg": national(snap, snap.base_reg),
                    **{f"forecast_mix_{m}": national(snap, guess, m) for m in MIX_GRID},
                    "partial": snap.lc.sum() / max(snap.lc.sum() + snap.rc.sum(), 1),
                    # how much of what is left sits in states that have barely reported
                    "dark": remaining[snap.frac_state < 0.05].sum() / max(remaining.sum(), 1),
                    "R": float(rest.sum()), "D": float(tv), "R_s": by_state.rest.to_numpy().tolist(), "Ec_s": by_state.ec.to_numpy().tolist()})
    return out
