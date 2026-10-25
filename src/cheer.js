import { CHEER } from './config.js?v=23';

/**
 * Plays a short excerpt of a song (Spotify embed) whenever one candidate takes the national lead, and stops
 * it early if the rival takes the lead back meanwhile, including when the page opens with that candidate ahead.
 * Always on. Browsers only let a page play sound after the visitor has interacted with it once, so a hint asks for
 * one tap anywhere until then, and a lead taken before that tap plays on the tap if it still holds.
 */
export class LeadCheer {
  #previous = null; // leader seen at the last update: none before the first one, so a lead at opening counts as taken
  #controller = null;
  #unlocked = false;
  #pending = false; // a lead taken while sound was still locked
  #stopTimer = 0;
  #watchTimer = 0;

  constructor(holder, hint, poll) {
    this.poll = poll; // async () => national Tally, to catch a reversal faster than the page refresh
    LeadCheer.#embed(holder).then(controller => {
      this.#controller = controller;
      this.#playPending(); // a lead taken while the player was loading
    });
    const unlock = () => {
      hint.hidden = true;
      this.#unlocked = true;
      this.#playPending();
      for (const type of ['pointerdown', 'keydown']) document.removeEventListener(type, unlock);
    };
    for (const type of ['pointerdown', 'keydown']) document.addEventListener(type, unlock);
  }

  get playing() {
    return Boolean(this.#stopTimer);
  }

  update(national) {
    const leader = national?.leader?.number ?? null;
    if (this.#previous !== CHEER.candidate && leader === CHEER.candidate) {
      if (this.#unlocked) this.#play();
      else this.#pending = true;
    }
    if (leader === CHEER.rival) {
      this.#pending = false;
      if (this.playing) this.#stop();
    }
    this.#previous = leader;
  }

  #playPending() {
    if (!this.#pending || !this.#unlocked || !this.#controller) return;
    this.#pending = false;
    if (this.#previous === CHEER.candidate) this.#play();
  }

  #play() {
    if (!this.#controller) {
      this.#pending = true; // the player is still loading: retry on the next tap
      return;
    }
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
