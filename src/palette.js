import { CANDIDATE_COLORS } from './config.js?v=18';

/**
 * Colours of the runoff maps: the hue says who leads an area, the shade how wide the lead is.
 * Shades mix the candidate colour with the page surface, so they work in light and dark mode.
 */
export class RunoffPalette {
  static NONE = 'var(--none)';
  static BANDS = [
    { below: 5, strength: 40, label: 'até 5 pontos' },
    { below: 15, strength: 70, label: '5 a 15 pontos' },
    { below: Infinity, strength: 100, label: 'mais de 15 pontos' },
  ];

  colorOf(candidate) {
    return CANDIDATE_COLORS[candidate?.number] ?? RunoffPalette.NONE;
  }

  /** Fill of an area: its leader's colour, stronger as the lead widens. */
  fill(tally) {
    const leader = tally?.leader;
    if (!leader) return RunoffPalette.NONE;
    const { strength } = RunoffPalette.BANDS.find(band => tally.margin < band.below);
    return RunoffPalette.#shade(this.colorOf(leader), strength);
  }

  /** Legend rows: one per candidate, one swatch per band. */
  legend(candidates) {
    return candidates.map(c => ({
      name: c.name,
      swatches: RunoffPalette.BANDS.map(band => ({ color: RunoffPalette.#shade(this.colorOf(c), band.strength), label: band.label })),
    }));
  }

  static #shade(color, strength) {
    return strength === 100 ? color : `color-mix(in srgb, ${color} ${strength}%, var(--surface))`;
  }
}
