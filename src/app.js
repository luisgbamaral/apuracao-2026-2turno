import { ABROAD, CANDIDATE_COLORS, CHEER, ELECTION, HISTORY_REFRESH_MS, MUNICIPAL_REFRESH_MS, PRESIDENT, REFRESH_MS, STATES, TSE_BASE } from './config.js?v=24';
import { LivePage } from './live-page.js?v=24';
import { LeadCheer } from './cheer.js?v=24';
import { Forecast } from './forecast.js?v=24';
import { ForecastView } from './forecast-view.js?v=24';
import { ChoroplethMap } from './map.js?v=24';
import { MunicipalFeed } from './municipal-feed.js?v=24';
import { RunoffPalette } from './palette.js?v=24';
import { Tally, TseClient } from './tse.js?v=24';
import { HeadToHead, StateTable, describeTally, formatInt, renderLegend } from './views.js?v=24';

const $ = id => document.getElementById(id);
const AREAS = { ...STATES, ...ABROAD };

class Dashboard extends LivePage {
  constructor() {
    super(REFRESH_MS);
    this.client = new TseClient(TSE_BASE, ELECTION, PRESIDENT);
    this.palette = new RunoffPalette();
    this.status = $('status');
    this.duel = new HeadToHead($('duel'), this.palette);
    this.table = new StateTable($('state-table'), this.palette);
    this.states = {};
    this.forecastView = new ForecastView($('forecast'), this.palette);
    this.cheer = new LeadCheer($('cheer-player'), $('cheer-hint'), () => this.client.tally('br'));
    this.stateMap = new ChoroplethMap({ svg: $('state-map'), tooltip: $('tooltip') },
      uf => describeTally(STATES[uf], this.states[uf], this.palette));
    this.municipalMap = new ChoroplethMap({ svg: $('municipal-map'), tooltip: $('tooltip') },
      code => describeTally(`${this.names.get(code)} (${this.ufOf.get(code).toUpperCase()})`, this.feed.tallies.get(code), this.palette));
  }

  async start() {
    const [stateShapes, municipalShapes, forecast] = await Promise.all([
      this.stateMap.load('data/states.json', { idOf: s => s.uf, labelOf: s => s.uf.toUpperCase() }),
      this.municipalMap.load('data/municipalities.json', { idOf: s => s.tse }),
      Forecast.load(),
    ]);
    this.forecast = forecast;
    this.municipalMap.paint(() => RunoffPalette.NONE);
    this.names = new Map(municipalShapes.map(s => [s.tse, s.name]));
    this.ufOf = new Map(municipalShapes.map(s => [s.tse, s.uf]));
    // Every municipality of the TSE list, including any without a shape on the map; abroad comes from its state file.
    const municipalities = forecast.units.filter(u => u.unit !== 'zz').map(u => ({ uf: u.uf, tse: u.unit.slice(2) }));
    this.feed = new MunicipalFeed(this.client, municipalities);
    this.#setupZoom(stateShapes);
    await super.start();
    setInterval(() => this.#refreshMunicipalities(), MUNICIPAL_REFRESH_MS);
    this.forecastView.loadShared();
    setInterval(() => this.forecastView.loadShared(), HISTORY_REFRESH_MS);
  }

  async load() {
    const areas = Object.keys(AREAS);
    const [national, ...byArea] = await Promise.all([this.client.tally('br'), ...areas.map(uf => this.client.tally(uf))]);
    return { national, states: Object.fromEntries(areas.map((uf, i) => [uf, byArea[i]])) };
  }

  render({ national: file, states }) {
    // The headline follows whichever count is further along: the national file or the states added up.
    const summed = Tally.sum(Object.values(states));
    const ahead = summed && summed.sectionsCounted > (file?.sectionsCounted ?? -1) && summed.validVotes >= (file?.validVotes ?? 0);
    const national = ahead ? summed : file;
    if (!national) {
      this.status.textContent = `Não foi possível consultar o TSE (tentativa às ${new Date().toLocaleTimeString('pt-BR')}). Nova tentativa em 1 minuto.`;
      return;
    }
    this.national = national;
    this.states = states;
    this.status.textContent = national.updatedAt
      ? `Última totalização do TSE: ${national.updatedAt} · ${this.refreshNote}${national.isFinal ? ' · totalização encerrada' : ''}`
      : `O TSE ainda não totalizou nenhuma seção · ${this.refreshNote}`;
    if ([file, ...Object.values(states)].some(t => t?.stale)) {
      this.status.textContent += ` · o TSE não respondeu na tentativa das ${new Date().toLocaleTimeString('pt-BR')}; mostrando o último dado recebido`;
    }
    $('tiles').innerHTML = [
      [`${national.sectionsPct}%`, 'seções totalizadas'],
      [formatInt(national.validVotes), 'votos válidos'],
      [`${national.blankPct}%`, 'brancos'],
      [`${national.nullPct}%`, 'nulos'],
      [`${national.abstentionPct}%`, 'abstenção'],
    ].map(([value, label]) => `<div class="tile"><b>${value}</b><span>${label}</span></div>`).join('');
    const runoff = national.candidates.filter(c => c.number in CANDIDATE_COLORS);
    this.duel.render(national, runoff);
    this.cheer.update(national);
    for (const legend of document.querySelectorAll('.legend')) renderLegend(legend, this.palette.legend(runoff));
    this.stateMap.paint(uf => this.palette.fill(states[uf]));
    this.table.render(AREAS, states, runoff);
    if (!this.feed.loaded) this.#refreshMunicipalities(); // first pass as soon as there are votes
  }

  /** Municipal files are only worth fetching once the count has started. */
  #refreshMunicipalities() {
    if (!this.national?.validVotes || document.hidden) return;
    this.feed.refresh(this.states, () => {
      this.#runForecast();
      this.municipalMap.paint(code => this.palette.fill(this.feed.tallies.get(code)));
      $('municipal-status').textContent =
        `${formatInt(this.feed.loaded)} municípios lidos (os de estados ainda sem apuração não precisam) · conferidos a cada ${MUNICIPAL_REFRESH_MS / 1000} s`;
    });
  }

  /**
   * As municipal files arrive, once the municipalities read hold 95% of the votes the state files show as counted
   * (the rest is taken as not counted yet, which the early uncertainty floor covers). The national file can run
   * ahead of the state and municipal ones, so it is not the yardstick.
   */
  #runForecast() {
    const votes = tally => tally?.candidates.filter(c => c.number in CANDIDATE_COLORS).reduce((sum, c) => sum + c.votes, 0) ?? 0;
    let read = votes(this.states.zz);
    for (const tally of this.feed.tallies.values()) read += votes(tally);
    const counted = Object.values(this.states).reduce((sum, tally) => sum + votes(tally), 0);
    if (!counted || (!this.feed.complete && read < 0.95 * counted)) return;
    const result = this.forecast.run(unit => (unit === 'zz' ? this.states.zz : this.feed.tallies.get(unit.slice(2))));
    const [left, right] = [CHEER.candidate, CHEER.rival].map(n => this.national.candidates.find(c => c.number === n));
    this.forecastView.render(result, left, right);
  }

  #setupZoom(stateShapes) {
    const select = $('zoom');
    const boxes = Object.fromEntries(stateShapes.map(s => [s.uf, s.box]));
    select.innerHTML = '<option value="">Brasil inteiro</option>' +
      Object.entries(STATES).sort((a, b) => a[1].localeCompare(b[1])).map(([uf, name]) => `<option value="${uf}">${name}</option>`).join('');
    select.addEventListener('change', () => this.municipalMap.zoom(boxes[select.value]));
  }
}

/** Two tabs, the real count and the forecast; the address keeps the choice (#previsao) so a link opens it. */
function setupTabs() {
  const buttons = document.querySelectorAll('.tabs button');
  const show = name => {
    for (const b of buttons) {
      const on = b.dataset.tab === name;
      b.setAttribute('aria-selected', String(on));
      $(`tab-${b.dataset.tab}`).hidden = !on;
    }
  };
  for (const b of buttons) b.addEventListener('click', () => { show(b.dataset.tab); history.replaceState(null, '', `#${b.dataset.tab}`); });
  show(location.hash === '#previsao' ? 'previsao' : 'apuracao');
}

setupTabs();
window.dashboard = new Dashboard(); // exposed for inspection from the console
window.dashboard.start();
