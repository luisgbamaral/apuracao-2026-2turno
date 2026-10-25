"""Election-night snapshots simulated from finished elections, the training data of the forecast.

A unit is a municipality (all cities abroad are one unit, "zz", as in the live files). For a target vote
(a runoff, or the 2026 first round for calibration) and its prior (the first round before it), the count is
replayed: every unit gets a counting speed (small municipalities and some states report sooner, as on a real
night), sections inside a unit come in random order, and at each moment of the night the features the live
page can compute are recorded together with the unit's final result.

Shares are two-party: left candidate / (left + right), the quantity that decides a runoff.
"""
from pathlib import Path

import numpy as np
import pandas as pd

SECTIONS = "model/cache/sections.parquet"
MOMENTS = [0.01, 0.03, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98]
FEATURES = ["q", "others", "log_electorate", "frac", "p", "d", "swing_state", "frac_state", "swing_nat", "frac_nat", "local", "state_gap"]
STATE_SWING_FROM = 0.01  # share of a state's electorate counted before its own swing replaces the national one
MIX = 1.5  # a unit's own count gets weight f / (f + MIX); chosen on synthetic counts as the least regret across 2018 and 2022


def load(year, round_):
    s = pd.read_parquet(SECTIONS, filters=[("ano", "=", year), ("turno", "=", round_)])
    s["unit"] = np.where(s.uf == "zz", "zz", s.uf + s.mun.astype(str).str.zfill(5))
    return s


def priors(year, round_):
    """Per unit, from the earlier vote: two-party share, share of other candidates, valid votes per elector."""
    u = load(year, round_).groupby(["unit", "uf"], as_index=False)[["l", "r", "valid", "electorate"]].sum()
    out = pd.DataFrame({"unit": u.unit, "uf": u.uf, "q": u.l / (u.l + u.r), "others": 1 - (u.l + u.r) / u.valid,
                        "rate_prior": u.valid / u.electorate.where(u.electorate > 0), "electorate_prior": u.electorate})
    # A unit with no registered electorate in the panel (one in 2018) takes its state's mean rate.
    out["rate_prior"] = out.rate_prior.fillna(out.groupby("uf").rate_prior.transform("mean"))
    return out


def snapshots(target, prior, seeds=(0, 1, 2), moments=MOMENTS):
    """Feature rows for every unit not yet fully counted, at every moment of every replay."""
    s = load(*target)
    pr = priors(*prior)
    units = s.groupby("unit", as_index=False).agg(uf=("uf", "first"), l=("l", "sum"), r=("r", "sum"), electorate=("electorate", "sum"),
                                                  n=("secao", "size"))
    units = units.merge(pr.drop(columns="uf"), on="unit", how="left")
    # A unit new since the prior (e.g. a municipality created in between) takes its state's prior.
    for column in ("q", "others", "rate_prior"):
        units[column] = units[column].fillna(units.groupby("uf")[column].transform("mean"))
    units["y"] = units.l / (units.l + units.r)
    index = pd.Index(units.unit)
    unit_of = index.get_indexer(s.unit)
    state_of = pd.Index(sorted(units.uf.unique())).get_indexer(units.uf)
    rows = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        # Counting speed: states differ, big municipalities are slower, plus noise of each place.
        state_speed = rng.normal(0, 0.35, state_of.max() + 1)
        speed = np.exp(state_speed[state_of] - 0.15 * np.log(units.electorate.clip(lower=1)) + rng.normal(0, 0.4, len(units)))
        order = rng.random(len(s))
        rank = pd.Series(order).groupby(unit_of).rank(pct=True).to_numpy()  # position of each section in its unit's count
        for t in moments:
            lo, hi = 0.0, 1e6
            for _ in range(60):  # scale speeds so that a share t of the national electorate is counted
                k = (lo + hi) / 2
                share = np.minimum(1, k * speed) @ units.electorate / units.electorate.sum()
                lo, hi = (k, hi) if share < t else (lo, k)
            f = np.minimum(1, k * speed)
            counted = rank <= f[unit_of] + 1e-12
            counted &= f[unit_of] > 0
            agg = lambda column: np.bincount(unit_of, weights=s[column].to_numpy() * counted, minlength=len(units))
            lc, rc, ec = agg("l"), agg("r"), agg("electorate")
            nc = np.bincount(unit_of, weights=counted, minlength=len(units))
            snap = units[["unit", "uf", "q", "others", "rate_prior", "electorate", "l", "r", "y"]].copy()
            snap["lc"], snap["rc"], snap["ec"] = lc, rc, ec
            snap["frac"] = nc / units.n
            snap["seed"], snap["moment"] = seed, t
            rows.append(add_features(snap))
    return pd.concat(rows, ignore_index=True)


def add_features(snap):
    """Features the live page computes from what is counted so far (also used at inference, in JS)."""
    snap = snap.copy()
    votes = snap.lc + snap.rc
    snap["p"] = np.where(votes > 0, snap.lc / votes.where(votes > 0, 1), np.nan)
    snap["d"] = snap.p - snap.q
    snap["log_electorate"] = np.log(snap.electorate.clip(lower=1))
    gap = snap.lc - snap.q * votes  # votes the left candidate got beyond the prior share, in counted sections
    for scope, key in (("state", snap.uf), ("nat", pd.Series("br", index=snap.index))):
        g = pd.DataFrame({"gap": gap, "votes": votes, "ec": snap.ec, "e": snap.electorate}).groupby(key.to_numpy())
        sums = g.sum()
        snap[f"swing_{scope}"] = key.map(sums.gap / sums.votes.where(sums.votes > 0)).to_numpy()
        snap[f"frac_{scope}"] = key.map(sums.ec / sums.e).to_numpy()
    # The level comes from the prior and the swing seen so far; the model only learns corrections to it.
    swing = np.where(snap.frac_state >= STATE_SWING_FROM, snap.swing_state, snap.swing_nat)
    snap["base"] = snap.q + np.nan_to_num(swing)
    snap["local"] = snap.p - snap.base  # how this unit's partial count departs from that level
    snap["state_gap"] = snap.swing_state - snap.swing_nat
    snap["base_reg"] = snap.q + regression_swing(snap)
    snap["base_logit"] = logit_base(snap)
    for k in SHRINK_GRID:
        snap[f"base_shrink_{k}"] = snap.q + shrunk_swing(snap, k)
    snap["base_knn"] = snap.q + neighbour_swing(snap)
    capital = snap.electorate.to_numpy() == snap.groupby("uf").electorate.transform("max").to_numpy()
    snap["base_capital"] = snap.q + group_swing(snap, capital.astype(int))
    cuts = np.quantile(snap.q, [1 / 3, 2 / 3])
    snap["base_lean"] = snap.q + group_swing(snap, np.digitize(snap.q, cuts))
    # Voters with no valid first-round vote (absent, blank or null): the pool the runoff draws new votes from.
    pool = 1 - snap.rate_prior.clip(0, 1)
    snap["base_abst"] = snap.q + group_swing(snap, np.digitize(pool, np.quantile(pool, [1 / 3, 2 / 3])))
    snap["base_r1w"] = snap.q + first_round_weighted_swing(snap)
    return snap


def first_round_weighted_swing(snap):
    """The page's swing, but each counted municipality weighs by its first-round size (valid votes), not by the
    votes counted so far: a municipality half counted weighs as much as a fully counted one of the same size."""
    votes = (snap.lc + snap.rc).to_numpy()
    seen = votes > 0
    d = np.where(seen, snap.lc / np.maximum(votes, 1) - snap.q, 0)
    w = np.where(seen, snap.electorate * snap.rate_prior.clip(0, 1), 0)
    out = {}
    for scope, key in (("state", snap.uf.to_numpy()), ("nat", np.full(len(snap), "br"))):
        g = pd.DataFrame({"k": key, "wd": w * d, "w": w}).groupby("k")[["wd", "w"]].transform("sum")
        out[scope] = np.where(g.w > 0, g.wd / g.w.where(g.w > 0, 1), 0)
    return np.where(snap.frac_state >= STATE_SWING_FROM, out["state"], out["nat"])


def group_swing(snap, group):
    """Swing computed separately for each (state, group) once the group has 1% of its electorate counted;
    before that, the group takes its state's swing (or the nation's, as in the base)."""
    votes = (snap.lc + snap.rc).to_numpy()
    gap = (snap.lc - snap.q * (snap.lc + snap.rc)).to_numpy()
    d = pd.DataFrame({"uf": snap.uf.to_numpy(), "g": group, "v": votes, "gap": gap, "ec": snap.ec.to_numpy(), "e": snap.electorate.to_numpy()})
    sums = d.groupby(["uf", "g"])[["v", "gap", "ec", "e"]].transform("sum")
    own = np.where(sums.v > 0, sums.gap / sums.v.where(sums.v > 0, 1), 0)
    fallback = (snap.base - snap.q).to_numpy()
    return np.where(sums.ec / sums.e >= STATE_SWING_FROM, own, fallback)


SHRINK_GRID = (20000, 200000)  # counted two-party votes at which a state (or region) gets half the weight of the level above
NEIGHBOURS = 15
_centroids = None


def centroids():
    """Projected centroid of every municipality, from the page's own map file (abroad has none)."""
    global _centroids
    if _centroids is None:
        import json
        shapes = json.loads(Path(__file__).resolve().parent.parent.joinpath("data/municipalities.json").read_text(encoding="utf-8"))["shapes"]
        points = {}
        for s in shapes:
            xs, ys = [], []
            for ring in s["d"].split("M")[1:]:
                head, _, rest = ring.partition("l")
                x, y = map(float, head.split(","))
                xs.append(x), ys.append(y)
                for step in rest.rstrip("z").split():
                    dx, dy = map(float, step.split(","))
                    x, y = x + dx, y + dy
                    xs.append(x), ys.append(y)
            points[s["uf"] + s["tse"]] = (np.mean(xs), np.mean(ys))
        _centroids = points
    return _centroids


def shrunk_swing(snap, k):
    """State swing pulled towards its region's, and the region's towards the nation's, by counted votes."""
    votes = (snap.lc + snap.rc).to_numpy()
    gap = (snap.lc - snap.q * (snap.lc + snap.rc)).to_numpy()
    region = snap.uf.map(REGIONS).to_numpy()
    nat = gap.sum() / votes.sum() if votes.sum() > 0 else 0.0
    rv, rg = np.bincount(region, weights=votes, minlength=6), np.bincount(region, weights=gap, minlength=6)
    reg = (rg + k * nat) / (rv + k)
    states = pd.DataFrame({"uf": snap.uf, "v": votes, "g": gap, "r": region}).groupby("uf").agg(v=("v", "sum"), g=("g", "sum"), r=("r", "first"))
    state = (states.g + k * reg[states.r.to_numpy()]) / (states.v + k)
    return snap.uf.map(state).to_numpy()


def neighbour_swing(snap):
    """Swing of the nearest counted municipalities (by map distance), weighted by their counted votes."""
    from scipy.spatial import cKDTree
    votes = (snap.lc + snap.rc).to_numpy()
    gap = (snap.lc - snap.q * (snap.lc + snap.rc)).to_numpy()
    nat = gap.sum() / votes.sum() if votes.sum() > 0 else 0.0
    xy = np.array([centroids().get(u, (np.nan, np.nan)) for u in snap.unit])
    seen = (votes > 0) & ~np.isnan(xy[:, 0])
    if seen.sum() < NEIGHBOURS:
        return np.full(len(snap), nat)
    tree = cKDTree(xy[seen])
    out = np.full(len(snap), nat)
    has = ~np.isnan(xy[:, 0])
    _, idx = tree.query(xy[has], k=NEIGHBOURS)
    v, g = votes[seen][idx], gap[seen][idx]
    out[has] = g.sum(axis=1) / np.maximum(v.sum(axis=1), 1)
    return out


def logit_base(snap):
    """Base with the swing applied in logit, which never leaves 0-100%: per state, the shift delta that makes
    expit(logit q + delta) reproduce the left votes counted there (nationally while the state is under 1%)."""
    q = snap.q.clip(0.001, 0.999).to_numpy()
    lq = np.log(q / (1 - q))
    votes = (snap.lc + snap.rc).to_numpy()
    left = snap.lc.to_numpy()

    def shift(mask):
        if votes[mask].sum() <= 0:
            return 0.0
        delta = 0.0
        for _ in range(30):  # Newton on sum(votes * expit(lq + delta)) = sum(left)
            p = 1 / (1 + np.exp(-(lq[mask] + delta)))
            f = (votes[mask] * p).sum() - left[mask].sum()
            g = (votes[mask] * p * (1 - p)).sum()
            if g <= 0:
                break
            delta -= f / g
        return delta

    nat = shift(np.ones(len(snap), dtype=bool))
    uf = snap.uf.to_numpy()
    frac = dict(zip(snap.uf, snap.frac_state))
    deltas = {s: (shift(uf == s) if frac[s] >= STATE_SWING_FROM else nat) for s in frac}
    return 1 / (1 + np.exp(-(lq + np.array([deltas[s] for s in uf]))))


REGIONS = {**dict.fromkeys(["ac", "am", "ap", "pa", "ro", "rr", "to"], 0), **dict.fromkeys(["al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se"], 1),
           **dict.fromkeys(["df", "go", "ms", "mt"], 2), **dict.fromkeys(["es", "mg", "rj", "sp"], 3), **dict.fromkeys(["pr", "rs", "sc"], 4), "zz": 5}
RIDGE = 30.0          # pulls the slopes towards zero while few units have reported (in units of counted-vote weight share)
STATE_SHRINK = 20000  # counted votes at which a state's own residual swing gets half weight


def design(snap):
    """Unit characteristics the swing may depend on: prior lean, other candidates, size, region."""
    region = snap.uf.map(REGIONS).to_numpy()
    # (q - 0.5) * others is the vote-transfer term: a runoff share is about q * (1 - others) + a * others.
    cols = [np.ones(len(snap)), snap.q - 0.5, snap.others, (snap.q - 0.5) * snap.others, np.log(snap.electorate.clip(lower=1)) - 9]
    cols += [(region == r).astype(float) for r in range(1, 6)]
    # Electorate profile (education, age, sex), when the snapshot carries it: centred shares.
    cols += [snap[c] - snap[c].mean() for c in snap.columns if c.startswith("demo_")]
    return np.column_stack(cols)


def regression_swing(snap):
    """Swing of every unit predicted from the counted ones: weighted ridge regression of (p - q) on the unit's
    characteristics, plus each state's leftover swing shrunk by how much of it has been counted."""
    votes = (snap.lc + snap.rc).to_numpy()
    seen = votes > 0
    if seen.sum() < 3:
        return np.zeros(len(snap))
    x = design(snap)
    d = np.where(seen, snap.lc / np.where(seen, votes, 1) - snap.q, 0)
    w = votes / votes.sum()
    penalty = np.eye(x.shape[1]) * RIDGE / max(votes.sum(), 1) * 1e4
    penalty[0, 0] = 0  # never shrink the intercept: it is the national swing
    xw = x[seen] * w[seen, None]
    beta = np.linalg.solve(x[seen].T @ xw + penalty * w[seen].sum() / 1e4, xw.T @ d[seen])
    fit = x @ beta
    resid = pd.DataFrame({"uf": snap.uf, "r": np.where(seen, (d - fit) * votes, 0), "v": votes}).groupby("uf").sum()
    state = (resid.r / (resid.v + STATE_SHRINK)).reindex(snap.uf).to_numpy()
    return fit + state


def weight(snap, mix=None):
    """How much a unit's own partial count is trusted for what is left of it."""
    mix = MIX if mix is None else mix
    return snap.frac * 0 if np.isinf(mix) else snap.frac / (snap.frac + mix)


def expected_totals(snap, mix=None, by_state=False):
    """Two-party votes each unit will have at the end: the counted ones plus its uncounted electorate times a
    rate that blends the unit's own votes per elector with its prior rate scaled by the ratio seen so far."""
    votes_c = snap.lc + snap.rc
    counted = snap.frac > 0
    ratio = votes_c[counted].sum() / (snap.ec[counted] * snap.rate_prior[counted]).sum() if counted.any() else 0.97
    if by_state:  # turnout change against the first round, state by state (national while the state has none counted)
        g = pd.DataFrame({"uf": snap.uf, "v": votes_c.where(counted, 0), "x": (snap.ec * snap.rate_prior).where(counted, 0)}).groupby("uf").sum()
        ratio = snap.uf.map((g.v / g.x).where(g.x > 0)).fillna(ratio).to_numpy()
    own = (votes_c / snap.ec.where(snap.ec > 0)).fillna(0)
    w = weight(snap, mix)
    rate = w * own + (1 - w) * snap.rate_prior * ratio
    return votes_c + (snap.electorate - snap.ec).clip(lower=0) * rate


def national(snap, base_share, mix=None, by_state=False):
    """National two-party share expected at the end: what is counted, plus each unit's remaining votes at a
    share that blends its own partial count with its base."""
    votes_c = snap.lc + snap.rc
    total = expected_totals(snap, mix, by_state)
    w = weight(snap, mix)
    partial = (snap.lc / votes_c.where(votes_c > 0)).fillna(0)
    rest_share = w * partial + (1 - w) * base_share
    left = snap.lc + rest_share * (total - votes_c)
    return left.sum() / total.sum()
