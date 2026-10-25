import { ABROAD, CANDIDATE_COLORS, CHEER, ELECTION, MUNICIPAL_REFRESH_MS, PRESIDENT, REFRESH_MS, STATES, TSE_BASE } from './config.js?v=4';
import { LivePage } from './live-page.js?v=4';
import { LeadCheer } from './cheer.js?v=4';
import { Forecast } from './forecast.js?v=4';
import { ForecastView } from './forecast-view.js?v=4';
import { ChoroplethMap } from './map.js?v=4';
import { MunicipalFeed } from './municipal-feed.js?v=4';
import { RunoffPalette } from './palette.js?v=4';
import { TseClient } from './tse.js?v=4';
import { HeadToHead, StateTable, describeTally, formatInt, renderLegend } from './views.js?v=4';

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
    this.cheer = new LeadCheer($('cheer'), $('cheer-player'), () => this.client.tally('br'));
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
  }

  async load() {
    const areas = Object.keys(AREAS);
    const [national, ...byArea] = await Promise.all([this.client.tally('br'), ...areas.map(uf => this.client.tally(uf))]);
    return { national, states: Object.fromEntries(areas.map((uf, i) => [uf, byArea[i]])) };
  }

  render({ national, states }) {
    if (!national) {
      this.status.textContent = 'Não foi possível consultar o TSE. Nova tentativa em instantes.';
      return;
    }
    this.national = national;
    this.states = states;
    this.status.textContent = national.updatedAt
      ? `Última totalização do TSE: ${national.updatedAt} · ${this.refreshNote}${national.isFinal ? ' · totalização encerrada' : ''}`
      : `O TSE ainda não totalizou nenhuma seção · ${this.refreshNote}`;
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
      if (!this.feed.running) this.#runForecast();
      this.municipalMap.paint(code => this.palette.fill(this.feed.tallies.get(code)));
      $('municipal-status').textContent =
        `${formatInt(this.feed.loaded)} de ${formatInt(this.feed.municipalities.length)} municípios carregados · conferidos a cada ${MUNICIPAL_REFRESH_MS / 1000} s, baixando só os que mudaram`;
    });
  }

  /** Once every municipality has been read, after each pass. */
  #runForecast() {
    if (this.feed.loaded < this.feed.municipalities.length * 0.99) return;
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

new Dashboard().start();
