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
    this.isDone = this.isFinal || this.sectionsPct === '100,00';
    this.validVotes = Number(v.vv) || 0;
    this.blankPct = v.pvb || '0,00';
    this.nullPct = v.ptvn || '0,00';
    this.abstentionPct = e.pa || '0,00';
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
      const response = await fetch(url, { cache: 'no-cache' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const tally = new Tally(await response.json(), `${this.root}/fotos/br`);
      if (tally.election !== this.election || tally.area !== area) {
        throw new Error(`unexpected content: ${tally.election} ${tally.area}`);
      }
      this.#lastGood.set(url, tally);
    } catch (error) {
      console.warn(`TSE file unavailable: ${url}`, error);
    }
    return this.#lastGood.get(url) ?? null;
  }
}
