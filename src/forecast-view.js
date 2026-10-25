import { CHEER, HISTORY_URL } from './config.js?v=25';
import { esc } from './views.js?v=25';

const pct = (x, digits = 1) => (100 * x).toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
// A chance is shown between 1% and 99%: beyond that the model's own uncertainty about itself dominates.
const chanceText = (p, decided) => (decided ? '100%' : p > 0.99 ? 'mais de 99%' : p < 0.01 ? 'menos de 1%' : `${pct(p, 0)}%`);
// How often the model's favourite won in the 2022-mold simulations (the closest to 2026: few first-round votes for
// other candidates), by stage of the count (rows) and projected gap in points (columns); null where under 20 cases.
const STAGES = [[0.035, 'até 2%'], [0.125, '5% a 10%'], [0.35, '15% a 30%'], [0.65, '40% a 60%'], [0.85, '70% a 80%'], [Infinity, '90% ou mais']];
const GAPS = [[1, 'menos de 1 ponto'], [2, '1 a 2 pontos'], [3, '2 a 3 pontos'], [5, '3 a 5 pontos'], [8, '5 a 8 pontos'], [Infinity, 'mais de 8 pontos']];
const WON = [[42, 64, 60, 76, 96, 100], [47, 57, 78, 97, 100, 100], [56, 55, 93, 100, 100, 100],
  [50, 81, 100, 100, 100, 100], [69, 97, 100, 100, 100, 100], [85, 100, 100, 100, 100, 100]];
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
    this.shared = []; // the published series, the same for every visitor
    this.chart.setAttribute('viewBox', '0 0 640 50');
    this.chart.innerHTML = '<text x="320" y="28" class="empty">O gráfico começa com a primeira previsão.</text>';
  }

  /** left/right: the two candidates (left is the one the forecast is written for). */
  render(result, left, right, own = true) {
    if (!result) return;
    if (own) {
      this.own = true;
      this.#remember(result);
    }
    this.candidates = [left, right];
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
    this.bet.innerHTML += ForecastView.#caveat(result);
    this.rows.innerHTML = sides.map(s => `
      <div class="chance" style="--c:${this.palette.colorOf(s.c)}">
        <span class="who">${esc(s.c.name)}</span>
        <b>${chanceText(s.chance, result.decided && s === favourite)}</b><span class="sub">de chance de vencer</span>
        <span class="sub">resultado final previsto: <b>${pct(s.share)}% ± ${pct((s.high - s.low) / 2)} pontos</b> dos votos válidos (margem de erro: de ${pct(s.low)}% a ${pct(s.high)}%)</span>
        <div class="meter"><span style="width:${100 * s.chance}%"></span></div>
      </div>`).join('');
    this.note.textContent = `Previsão com ${pct(result.counted)}% do eleitorado nas seções totalizadas. ` +
      'O gráfico mostra a noite inteira, o mesmo para todos os visitantes.';
    this.#drawChart(left, right);
  }

  /** How often a favourite with a similar projected gap, at this stage of the count, won in the simulations. */
  static #caveat({ counted, decided, share }) {
    if (decided) return '';
    const stage = STAGES.findIndex(([upTo]) => counted < upTo);
    const gap = GAPS.findIndex(([upTo]) => Math.abs(share - 0.5) * 200 < upTo);
    const won = WON[stage][gap];
    const done = counted < 0.001 ? 'menos de 0,1%' : `${pct(counted)}%`;
    const reading = counted < 0.1 ? 'ainda é cedo' : counted < 0.5 ? 'a previsão ainda pode mudar' : 'a previsão já está mais firme';
    return `<span class="sub caveat"><b>Quanto confiar agora:</b> com ${done} apurado, ${reading}. ` +
      `Nas simulações a partir do 2º turno de 2022, o mais parecido com este, quando o modelo projetava uma diferença de ${GAPS[gap][1]} ` +
      `com ${STAGES[stage][1]} apurado, o favorito venceu ${won === 100 ? 'em todas' : `em ${won}% delas`}.</span>`;
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

  /** Reads the published series; it lags a few minutes, so this browser's own points fill both ends. */
  async loadShared() {
    try {
      const response = await fetch(HISTORY_URL, { cache: 'no-cache' });
      if (response.ok) this.shared = await response.json();
    } catch { /* keep the last series read */ }
    if (this.candidates) this.showLatest(...this.candidates);
    else this.#drawChart({ number: CHEER.candidate }, { number: CHEER.rival }); // names not loaded yet: colours are enough
  }

  /** Until this page computes its own forecast, the latest published one is shown, with the chart. */
  showLatest(left, right) {
    this.candidates ??= [left, right];
    const last = this.shared.at(-1);
    if (!this.own && last?.high) this.render({ ...last, decided: 0 }, ...this.candidates, false);
    else this.#drawChart(...this.candidates);
  }

  get #points() {
    if (!this.shared.length) return this.history;
    const [first, last] = [this.shared[0].at, this.shared.at(-1).at];
    return [...this.history.filter(p => p.at < first), ...this.shared, ...this.history.filter(p => p.at > last)];
  }

  /** Chance of each candidate over the night: one line each, with the 50% line. */
  #drawChart(left, right) {
    const [w, h, padL, padB, padT] = [640, 220, 34, 22, 8];
    const points = this.#points;
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
