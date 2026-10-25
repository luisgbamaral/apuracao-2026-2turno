import { CHEER } from './config.js?v=4';

/**
 * Plays a short excerpt of a song (Spotify embed) whenever one candidate takes the national lead, and stops
 * it early if the rival takes the lead back meanwhile. Off until the visitor turns it on: browsers only let
 * a page play sound after a click, and nobody gets music they did not ask for.
 */
export class LeadCheer {
  #previous; // leader seen at the last update; undefined until the first one, so opening the page never plays
  #controller = null;
  #stopTimer = 0;
  #watchTimer = 0;

  constructor(button, holder, poll) {
    this.button = button;
    this.holder = holder;
    this.poll = poll; // async () => national Tally, to catch a reversal faster than the page refresh
    this.on = false;
    button.addEventListener('click', () => this.#toggle());
    this.#label();
  }

  get playing() {
    return Boolean(this.#stopTimer);
  }

  update(national) {
    const leader = national?.leader?.number ?? null;
    if (this.on && this.#previous !== undefined && this.#previous !== CHEER.candidate && leader === CHEER.candidate) this.#play();
    if (this.playing && leader === CHEER.rival) this.#stop();
    this.#previous = leader;
  }

  async #toggle() {
    this.on = !this.on;
    this.#label();
    if (!this.on) return this.#stop();
    this.holder.hidden = false;
    this.#controller ??= await LeadCheer.#embed(this.holder);
  }

  #play() {
    if (!this.#controller) return;
    clearTimeout(this.#stopTimer);
    this.#controller.play();
    this.#stopTimer = setTimeout(() => this.#stop(), CHEER.seconds * 1000);
    this.#watchTimer = setInterval(async () => {
      if ((await this.poll())?.leader?.number === CHEER.rival) this.#stop();
    }, 5000);
  }

  #stop() {
    clearTimeout(this.#stopTimer);
    clearInterval(this.#watchTimer);
    this.#stopTimer = this.#watchTimer = 0;
    this.#controller?.pause();
  }

  #label() {
    this.button.setAttribute('aria-pressed', String(this.on));
    this.button.textContent = `${this.on ? '♪ Música ligada' : '♪ Ligar música'} quando ${CHEER.name} passar à frente`;
  }

  /** Loads Spotify's iFrame API once and resolves to a controller for the track. */
  static #embed(holder) {
    return new Promise(resolve => {
      window.onSpotifyIframeApiReady = api => {
        const target = document.createElement('div');
        holder.append(target);
        api.createController(target, { uri: `spotify:track:${CHEER.track}`, width: '100%', height: 80 }, resolve);
      };
      const script = document.createElement('script');
      script.src = 'https://open.spotify.com/embed/iframe-api/v1';
      document.head.append(script);
    });
  }
}
