import { esc } from './views.js?v=16';

const pct = (x, digits = 1) => (100 * x).toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
// A chance is shown between 1% and 99%: beyond that the model's own uncertainty about itself dominates.
const chanceText = (p, decided) => (decided ? '100%' : p > 0.99 ? 'mais de 99%' : p < 0.01 ? 'menos de 1%' : `${pct(p, 0)}%`);
const LABELS = [[0.95, 'forte favorito'], [0, 'favorito']]; // used once the 80% interval no longer includes 50%

/**
 * The forecast as a snapshot (who the model bets on, each candidate's chance and expected final share with
 * an 80% interval) and as a time series of the chances, kept in this browser so it survives a reload.
 */
export class ForecastView {
  static STORAGE_KEY = 'apuracao2026t2.forecast';

  constructor(card, palette) {
    this.bet = card.querySelector('.bet');
    this.rows = card.querySelector('.chances');
    this.chart = card.querySelector('svg');
    this.note = card.querySelector('.note');
    this.palette = palette;
    this.history = ForecastView.#read();
    this.chart.setAttribute('viewBox', '0 0 640 50');
    this.chart.innerHTML = '<text x="320" y="28" class="empty">O gráfico começa com a primeira previsão.</text>';
  }

  /** left/right: the two candidates (left is the one the forecast is written for). */
  render(result, left, right) {
    if (!result) return;
    this.#remember(result);
    const sides = [
      { c: left, chance: result.chance, share: result.share, low: result.low, high: result.high },
      { c: right, chance: 1 - result.chance, share: 1 - result.share, low: 1 - result.high, high: 1 - result.low },
    ];
    const favourite = sides[0].chance >= sides[1].chance ? sides[0] : sides[1];
    const label = LABELS.find(([from]) => favourite.chance >= from)[1];
    const color = `style="color:${this.palette.colorOf(favourite.c)}"`;
    // A technical tie, as polls call it: the 80% interval of the final share still includes 50%.
    const tie = result.low < 0.5 && result.high > 0.5;
    this.bet.innerHTML = result.decided
      ? `<span class="sub">Definido pela apuração</span><b ${color}>${esc(favourite.c.name)} vence</b>` +
        '<span class="sub">a vantagem já é maior que todos os eleitores que faltam apurar</span>'
      : tie
        ? `<b>Empate técnico</b><span class="sub"><b ${color}>${esc(favourite.c.name)}</b> está à frente na previsão, mas a margem de erro ainda ` +
          `alcança os 50%. Chance de ${esc(favourite.c.name)} vencer: ${chanceText(favourite.chance)}</span>`
        : `<span class="sub">Aposta do modelo: ${label}</span><b ${color}>${esc(favourite.c.name)}</b>` +
          `<span class="sub">com ${chanceText(favourite.chance)} de chance de vencer</span>`;
    this.rows.innerHTML = sides.map(s => `
      <div class="chance" style="--c:${this.palette.colorOf(s.c)}">
        <span class="who">${esc(s.c.name)}</span>
        <b>${chanceText(s.chance, result.decided && s === favourite)}</b><span class="sub">de chance de vencer</span>
        <span class="sub">resultado final previsto: <b>${pct(s.share)}% ± ${pct((s.high - s.low) / 2)} pontos</b> dos votos válidos (margem de erro: de ${pct(s.low)}% a ${pct(s.high)}%)</span>
        <div class="meter"><span style="width:${100 * s.chance}%"></span></div>
      </div>`).join('');
    this.note.textContent = `Previsão com ${pct(result.counted)}% do eleitorado nas seções totalizadas. ` +
      'A série começa quando esta página foi aberta neste navegador.';
    this.#drawChart(left, right);
  }

  #remember(result) {
    const last = this.history.at(-1);
    const same = last && last.counted === result.counted && Math.abs(last.share - result.share) < 1e-6;
    if (same && Date.now() - last.at < 55_000) return; // at most one unchanged point a minute
    this.history.push({ at: Date.now(), counted: result.counted, share: result.share, chance: result.chance });
    this.history = this.history.slice(-2000);
    try {
      localStorage.setItem(ForecastView.STORAGE_KEY, JSON.stringify(this.history));
    } catch { /* storage blocked: the series lasts for this visit */ }
  }

  /** Chance of each candidate over the night: one line each, with the 50% line. */
  #drawChart(left, right) {
    const [w, h, padL, padB, padT] = [640, 220, 34, 22, 8];
    const points = this.history;
    if (!points.length) return;
    const t0 = points[0].at;
    const span = Math.max(points.at(-1).at - t0, 60_000);
    const x = at => padL + ((at - t0) / span) * (w - padL - 8);
    const y = p => padT + (1 - p) * (h - padT - padB);
    const line = (value, color) => `<polyline fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"
      points="${points.map(p => `${x(p.at).toFixed(1)},${y(value(p)).toFixed(1)}`).join(' ')}"/>`;
    const hour = at => new Date(at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    const grid = [0, 0.25, 0.5, 0.75, 1].map(p =>
      `<line x1="${padL}" x2="${w - 8}" y1="${y(p)}" y2="${y(p)}" class="${p === 0.5 ? 'mid' : 'grid'}"/>` +
      `<text x="${padL - 4}" y="${y(p) + 3}" class="axis" text-anchor="end">${p * 100}%</text>`).join('');
    const ticks = [0, 0.5, 1].map(f => t0 + f * span)
      .map(at => `<text x="${x(at)}" y="${h - 6}" class="axis" text-anchor="middle">${hour(at)}</text>`).join('');
    this.chart.setAttribute('viewBox', `0 0 ${w} ${h}`);
    const now = points.at(-1);
    const dot = (value, color) => `<circle cx="${x(now.at).toFixed(1)}" cy="${y(value).toFixed(1)}" r="4" fill="${color}"/>`;
    this.chart.innerHTML = grid + ticks +
      line(p => 1 - p.chance, this.palette.colorOf(right)) + line(p => p.chance, this.palette.colorOf(left)) +
      dot(1 - now.chance, this.palette.colorOf(right)) + dot(now.chance, this.palette.colorOf(left));
  }

  static #read() {
    try {
      return JSON.parse(localStorage.getItem(ForecastView.STORAGE_KEY)) ?? [];
    } catch {
      return [];
    }
  }
}
