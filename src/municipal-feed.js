/**
 * Keeps the count of every municipality. The TSE publishes one file per municipality (5,570 of them,
 * under 1 kB gzipped each). Three things keep a pass down to what changed:
 *  - files are requested with revalidation, and the TSE answers an unchanged file with an empty 304;
 *  - a state whose own file shows no new totalization is skipped, so its municipalities cost no request;
 *  - a municipality fully counted leaves the queue.
 * The state file and a municipal file can come from CDN copies of different ages, so a state with
 * municipalities still counting is checked again after RECHECK_MS even if its file did not move.
 */
export class MunicipalFeed {
  static CONCURRENCY = 24;
  static PROGRESS_EVERY = 250; // repaint after this many files
  static RECHECK_MS = 300_000;

  #running = false;
  #synced = new Map(); // uf -> { stamp, at } of the state file when its municipalities were last fetched

  constructor(client, municipalities) {
    this.client = client;
    this.municipalities = municipalities; // [{ tse, uf }]
    this.tallies = new Map();
  }

  get running() {
    return this.#running;
  }

  get loaded() {
    return this.tallies.size;
  }

  /** One pass over the municipalities that may have changed; onProgress repaints as files arrive. */
  async refresh(states, onProgress) {
    if (this.#running) return;
    this.#running = true;
    const now = Date.now();
    const stamps = Object.fromEntries(Object.entries(states).map(([uf, t]) => [uf, t && `${t.updatedAt}|${t.sectionsPct}`]));
    const due = uf => {
      const last = this.#synced.get(uf);
      return !last || last.stamp !== stamps[uf] || now - last.at > MunicipalFeed.RECHECK_MS;
    };
    const queue = this.municipalities.filter(m => !this.tallies.get(m.tse)?.isDone && due(m.uf));
    const failed = new Set();
    let fetched = 0;
    const worker = async () => {
      for (let m = queue.shift(); m; m = queue.shift()) {
        const tally = await this.client.tally(m.uf, m.tse);
        if (tally) this.tallies.set(m.tse, tally);
        else failed.add(m.uf);
        if (++fetched % MunicipalFeed.PROGRESS_EVERY === 0) onProgress();
      }
    };
    const ufs = new Set(queue.map(m => m.uf));
    try {
      await Promise.all(Array.from({ length: MunicipalFeed.CONCURRENCY }, worker));
      for (const uf of ufs) if (!failed.has(uf)) this.#synced.set(uf, { stamp: stamps[uf], at: now });
    } finally {
      this.#running = false;
      this.lastPass = fetched;
      onProgress();
    }
  }
}
