const toNumber = pct => parseFloat(pct.replace(',', '.'));

/** The presidential count in one area (Brazil, a state or a municipality), parsed from a TSE result file. */
export class Tally {
  constructor(json, photoBase) {
    const { s = {}, e = {}, v = {} } = json; // absent until the area reports its first section
    this.area = json.cdabr;
    this.election = json.ele;
    this.candidates = json.carg[0].agr
      .flatMap(group => group.par.flatMap(party => party.cand.map(c => ({
        number: Number(c.n),
        name: c.nmu,
        party: party.sg,
        photo: `${photoBase}/${c.sqcand}.jpeg`,
        votes: Number(c.vap) || 0,
        pct: c.pvap || '0,00',
        // The "e" flag is also set for candidates going to a runoff, so only the status text counts.
        elected: (c.st ?? '').startsWith('Eleito'),
      }))));
    this.updatedAt = `${json.dt} ${json.ht}`.trim();
    this.isFinal = json.tf === 's';
    this.hasStatuses = this.candidates.some(c => c.elected);
    this.isMathematicallyDecided = json.md === 'e'; // published while counting, gone once the count ends
    this.sectionsPct = s.pst || '0,00';
    this.sections = Number(s.ts) || 0;
    this.sectionsCounted = Number(s.st) || 0;
    this.electorate = Number(e.te) || 0;
    this.electorateCounted = Number(e.est) || 0; // voters registered in the sections already counted
    this.isDone = this.isFinal || this.sectionsPct === '100,00';
    this.validVotes = Number(v.vv) || 0;
    this.totalVotes = Number(v.tv) || 0;
    this.blankVotes = Number(v.vb) || 0;
    this.nullVotes = Number(v.tvn) || 0;
    this.abstentions = Number(e.a) || 0;
    this.blankPct = v.pvb || '0,00';
    this.nullPct = v.ptvn || '0,00';
    this.abstentionPct = e.pa || '0,00';
  }

  /**
   * The count of several areas added up (the states and abroad give Brazil). Used when the national file lags
   * behind the state files, so the headline always shows the furthest count published.
   */
  static sum(tallies) {
    const list = tallies.filter(Boolean);
    if (!list.length) return null;
    const total = key => list.reduce((acc, t) => acc + t[key], 0);
    const pct = (part, whole) => (whole ? (100 * part) / whole : 0).toFixed(2).replace('.', ',');
    const byNumber = new Map();
    for (const t of list) {
      for (const c of t.candidates) byNumber.set(c.number, { ...c, votes: (byNumber.get(c.number)?.votes ?? 0) + c.votes, elected: false });
    }
    const out = Object.create(Tally.prototype);
    const stamp = t => t.updatedAt.replace(/(\d+)\/(\d+)\/(\d+) (.*)/, '$3-$2-$1 $4');
    Object.assign(out, {
      area: 'br', election: list[0].election, isFinal: false, hasStatuses: false, isMathematicallyDecided: false,
      updatedAt: list.filter(t => t.updatedAt).sort((a, b) => stamp(b).localeCompare(stamp(a)))[0]?.updatedAt ?? '',
      sections: total('sections'), sectionsCounted: total('sectionsCounted'), electorate: total('electorate'),
      electorateCounted: total('electorateCounted'), validVotes: total('validVotes'), totalVotes: total('totalVotes'),
      blankVotes: total('blankVotes'), nullVotes: total('nullVotes'), abstentions: total('abstentions'),
    });
    out.candidates = list[0].candidates.map(c => ({ ...byNumber.get(c.number), pct: pct(byNumber.get(c.number).votes, out.validVotes) }));
    out.sectionsPct = pct(out.sectionsCounted, out.sections);
    out.isDone = out.sectionsPct === '100,00';
    out.blankPct = pct(out.blankVotes, out.totalVotes);
    out.nullPct = pct(out.nullVotes, out.totalVotes);
    out.abstentionPct = pct(out.abstentions, out.electorateCounted); // as the TSE: over the sections counted
    return out;
  }

  /** Candidates by votes, most voted first. */
  get ranked() {
    return [...this.candidates].sort((a, b) => b.votes - a.votes);
  }

  /** The candidate strictly ahead; null while there are no votes or the top two are tied. */
  get leader() {
    const [first, second] = this.ranked;
    return first?.votes > (second?.votes ?? 0) ? first : null;
  }

  /** Lead of the first over the second, in points of the valid votes. */
  get margin() {
    const [first, second] = this.ranked;
    return first && second ? toNumber(first.pct) - toNumber(second.pct) : 0;
  }

  get lead() {
    const [first, second] = this.ranked;
    return first && second ? first.votes - second.votes : 0;
  }

  /** The winner once the TSE says so: by status after the count, by the "decided" flag before that. */
  get winner() {
    if (this.hasStatuses) return this.candidates.find(c => c.elected) ?? null;
    return this.isMathematicallyDecided ? this.leader : null;
  }
}

/** Reads the public result files. The TSE echoes the Origin header, so no proxy is needed. */
export class TseClient {
  #lastGood = new Map();

  constructor(baseUrl, election, office) {
    this.root = `${baseUrl}/${election}`;
    this.election = election;
    this.suffix = `-c${office}-e${election.padStart(6, '0')}-u.json`;
  }

  /**
   * The Tally of a state ("sp"), Brazil ("br") or a municipality (state and TSE code). If the file is
   * unavailable or is not the one requested, falls back to the last good Tally (stale beats wrong), or null.
   */
  async tally(uf, municipality = '') {
    const area = municipality || uf;
    const url = `${this.root}/dados/${uf}/${uf}${municipality}${this.suffix}`;
    try {
      const response = await fetch(url, { cache: 'no-cache', signal: AbortSignal.timeout(20_000) }); // a hung request must not stall the page
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const tally = new Tally(await response.json(), `${this.root}/fotos/br`);
      if (tally.election !== this.election || tally.area !== area) {
        throw new Error(`unexpected content: ${tally.election} ${tally.area}`);
      }
      this.#lastGood.set(url, tally);
    } catch (error) {
      console.warn(`TSE file unavailable: ${url}`, error);
      if (this.#lastGood.has(url)) this.#lastGood.get(url).stale = true; // shown as a failed attempt
    }
    return this.#lastGood.get(url) ?? null;
  }
}
