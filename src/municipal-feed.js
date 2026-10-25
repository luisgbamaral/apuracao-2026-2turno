/**
 * Keeps the count of every municipality. The TSE publishes one file per municipality (5,570 of them,
 * under 1 kB gzipped each), so a pass fetches them a few at a time and skips the ones already finished.
 */
export class MunicipalFeed {
  static CONCURRENCY = 24;
  static PROGRESS_EVERY = 250; // repaint after this many new files

  #running = false;

  constructor(client, municipalities) {
    this.client = client;
    this.municipalities = municipalities; // [{ tse, uf }]
    this.tallies = new Map();
  }

  get loaded() {
    return this.tallies.size;
  }

  /** One pass over the municipalities still counting; onProgress repaints as files arrive. */
  async refresh(onProgress) {
    if (this.#running) return;
    this.#running = true;
    const queue = this.municipalities.filter(m => !this.tallies.get(m.tse)?.isDone);
    let fetched = 0;
    const worker = async () => {
      for (let m = queue.shift(); m; m = queue.shift()) {
        const tally = await this.client.tally(m.uf, m.tse);
        if (tally) this.tallies.set(m.tse, tally);
        if (++fetched % MunicipalFeed.PROGRESS_EVERY === 0) onProgress();
      }
    };
    try {
      await Promise.all(Array.from({ length: MunicipalFeed.CONCURRENCY }, worker));
    } finally {
      this.#running = false;
      onProgress();
    }
  }
}
