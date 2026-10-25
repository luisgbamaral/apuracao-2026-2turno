import { CHEER } from './config.js?v=6';

/**
 * Plays a short excerpt of a song (Spotify embed) whenever one candidate takes the national lead, and stops
 * it early if the rival takes the lead back meanwhile. Always on. Browsers only let a page play sound after
 * the visitor has interacted with it once, so a hint asks for one tap anywhere until that happens.
 */
export class LeadCheer {
  #previous; // leader seen at the last update; undefined until the first one, so opening the page never plays
  #controller = null;
  #stopTimer = 0;
  #watchTimer = 0;

  constructor(holder, hint, poll) {
    this.poll = poll; // async () => national Tally, to catch a reversal faster than the page refresh
    LeadCheer.#embed(holder).then(controller => (this.#controller = controller));
    const unlock = () => {
      hint.hidden = true;
      for (const type of ['pointerdown', 'keydown']) document.removeEventListener(type, unlock);
    };
    for (const type of ['pointerdown', 'keydown']) document.addEventListener(type, unlock);
  }

  get playing() {
    return Boolean(this.#stopTimer);
  }

  update(national) {
    const leader = national?.leader?.number ?? null;
    if (this.#previous !== undefined && this.#previous !== CHEER.candidate && leader === CHEER.candidate) this.#play();
    if (this.playing && leader === CHEER.rival) this.#stop();
    this.#previous = leader;
  }

  #play() {
    if (!this.#controller) return;
    clearTimeout(this.#stopTimer);
    clearInterval(this.#watchTimer);
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
