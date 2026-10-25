/**
 * The election-night forecast (model/plan_b.py is its Python twin; tests check both give the same numbers).
 *
 * Point: what is counted, plus each unit's remaining votes at a share that blends its own partial count with
 * a base (its first-round share plus the swing seen so far in its state, or nationally while the state has
 * barely reported). Uncertainty: grows with what is left, with how different the regional mix of what is left
 * is from what came in, and with the remaining votes of states that have counted little, weighted by how many
 * first-round votes went to other candidates there. Fitted on synthetic elections counted in many orders.
 */
const REGIONS = { ac: 0, am: 0, ap: 0, pa: 0, ro: 0, rr: 0, to: 0, al: 1, ba: 1, ce: 1, ma: 1, pb: 1, pe: 1, pi: 1, rn: 1, se: 1,
  df: 2, go: 2, ms: 2, mt: 2, es: 3, mg: 3, rj: 3, sp: 3, pr: 4, rs: 4, sc: 4, zz: 5 };
const T80 = 1.4759; // 90th percentile of Student t with 5 degrees of freedom: the 80% interval

/** CDF of Student t with 5 degrees of freedom (closed form for odd degrees). */
export function t5(x) {
  const theta = Math.atan(x / Math.sqrt(5));
  const c = Math.cos(theta);
  return 0.5 + (theta + Math.sin(theta) * c * (1 + (2 / 3) * c * c)) / Math.PI;
}

const sum = values => values.reduce((a, b) => a + b, 0);

export class Forecast {
  constructor(model, units, { left = 13, right = 22 } = {}) {
    this.p = model; // parameters written by model/export.py
    this.units = units; // [{ unit, uf, q, others, rate_prior, electorate_prior }]
    this.left = left;
    this.right = right;
  }

  static async load(options) {
    const [model, units] = await Promise.all(['data/model.json', 'data/units.json'].map(async url => (await fetch(url)).json()));
    return new Forecast(model, units, options);
  }

  /** tallyOf(unit) -> Tally or null. Returns the national forecast for the left candidate's two-party share. */
  run(tallyOf) {
    const p = this.p;
    const rows = this.units.map(u => {
      const tally = tallyOf(u.unit);
      const votes = n => tally?.candidates.find(c => c.number === n)?.votes ?? 0;
      return { ...u, lc: votes(this.left), rc: votes(this.right), ec: tally?.electorateCounted ?? 0,
        electorate: tally?.electorate || u.electorate_prior, frac: tally?.sections ? tally.sectionsCounted / tally.sections : 0 };
    });

    // Swing seen so far (left votes beyond the first-round share, per counted two-party vote), by state and nationally.
    const scopes = { state: new Map(), nat: new Map() };
    for (const r of rows) {
      for (const [scope, key] of [['state', r.uf], ['nat', 'br']]) {
        const s = scopes[scope].get(key) ?? { gap: 0, votes: 0, ec: 0, e: 0 };
        s.gap += r.lc - r.q * (r.lc + r.rc);
        s.votes += r.lc + r.rc;
        s.ec += r.ec;
        s.e += r.electorate;
        scopes[scope].set(key, s);
      }
    }
    const nat = scopes.nat.get('br');
    const swingNat = nat.votes > 0 ? nat.gap / nat.votes : 0;

    // Expected final two-party votes per unit: counted plus uncounted electorate at a blended rate.
    let counted = 0;
    let expected = 0;
    for (const r of rows) {
      if (r.frac <= 0) continue;
      counted += r.lc + r.rc;
      expected += r.ec * r.rate_prior;
    }
    const ratio = expected > 0 ? counted / expected : 0.97;
    let leftVotes = 0;
    let total = 0;
    for (const r of rows) {
      const st = scopes.state.get(r.uf);
      const swing = st.ec / st.e >= p.state_swing_from ? (st.votes > 0 ? st.gap / st.votes : 0) : swingNat;
      const base = r.q + swing;
      const votesC = r.lc + r.rc;
      const w = r.frac / (r.frac + p.mix);
      const own = r.ec > 0 ? votesC / r.ec : 0;
      const rate = w * own + (1 - w) * r.rate_prior * ratio;
      r.expected = votesC + Math.max(r.electorate - r.ec, 0) * rate;
      const partial = votesC > 0 ? r.lc / votesC : 0;
      leftVotes += r.lc + (w * partial + (1 - w) * base) * (r.expected - votesC);
      total += r.expected;
    }
    const share = leftVotes / total;
    const sd = this.#sigma(rows, total, scopes.state, nat.ec / nat.e);
    // The count can no longer change the winner: the lead exceeds every voter still to be counted.
    const lead = sum(rows.map(r => r.lc - r.rc));
    const uncounted = sum(rows.map(r => Math.max(r.electorate - r.ec, 0)));
    const decided = Math.abs(lead) > uncounted ? Math.sign(lead) : 0;
    const chance = decided ? (decided > 0 ? 1 : 0) : t5((share - 0.5) / sd);
    // Where the counted votes come from, biggest first: early on, the forecast leans on these places.
    const where = [...scopes.state.entries()].filter(([, s]) => s.ec > 0).sort((a, b) => b[1].ec - a[1].ec)
      .map(([uf, s]) => ({ uf, share: s.ec / nat.ec }));
    return { share, low: share - T80 * sd, high: share + T80 * sd, chance, decided, counted: nat.ec / nat.e, sd, where };
  }

  /** Uncertainty of the national share, with floors that keep the start of the night humble. */
  #sigma(rows, total, states, countedShare) {
    const { c, kappa, tau, n0, floor, o0, a, inflate, floor_start, floor_start_until, floor_dark, dark_from, others_by_state } = this.p;
    const restOf = new Map();
    const countedMix = new Array(6).fill(0);
    const leftMix = new Array(6).fill(0);
    let rest = 0;
    let dark = 0;
    let remaining = 0;
    for (const r of rows) {
      const unitRest = Math.max(r.expected - r.lc - r.rc, 0) / total;
      rest += unitRest;
      restOf.set(r.uf, (restOf.get(r.uf) ?? 0) + unitRest);
      const uncounted = Math.max(r.electorate - r.ec, 0);
      countedMix[REGIONS[r.uf]] += r.ec;
      leftMix[REGIONS[r.uf]] += uncounted;
      remaining += uncounted;
      const st = states.get(r.uf);
      if (st.ec / st.e < 0.05) dark += uncounted;
    }
    const distance = sum(countedMix) > 0 && sum(leftMix) > 0
      ? 0.5 * countedMix.reduce((acc, x, i) => acc + Math.abs(x / sum(countedMix) - leftMix[i] / sum(leftMix)), 0) : 1;
    let state = 0;
    for (const [uf, r] of restOf) state += (r * (o0 + others_by_state[uf])) ** 2 * n0 / (n0 + states.get(uf).ec);
    let sd = inflate * Math.sqrt(rest ** (2 * a) * (c * c + kappa * kappa * distance * distance) + tau * tau * state + floor * floor);
    if (countedShare < floor_start_until) sd = Math.max(sd, floor_start);
    if (remaining > 0 && dark / remaining >= dark_from) sd = Math.max(sd, floor_dark);
    return sd;
  }
}
