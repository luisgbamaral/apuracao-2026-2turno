import { ABROAD, CANDIDATE_COLORS, ELECTION, MUNICIPAL_REFRESH_MS, PRESIDENT, REFRESH_MS, STATES, TSE_BASE } from './config.js?v=1';
import { LivePage } from './live-page.js?v=1';
import { ChoroplethMap } from './map.js?v=1';
import { MunicipalFeed } from './municipal-feed.js?v=1';
import { RunoffPalette } from './palette.js?v=1';
import { TseClient } from './tse.js?v=1';
import { HeadToHead, StateTable, describeTally, formatInt, renderLegend } from './views.js?v=1';

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
    this.stateMap = new ChoroplethMap({ svg: $('state-map'), tooltip: $('tooltip') },
      uf => describeTally(STATES[uf], this.states[uf], this.palette));
    this.municipalMap = new ChoroplethMap({ svg: $('municipal-map'), tooltip: $('tooltip') },
      code => describeTally(`${this.names.get(code)} (${this.ufOf.get(code).toUpperCase()})`, this.feed.tallies.get(code), this.palette));
  }

  async start() {
    const [stateShapes, municipalShapes] = await Promise.all([
      this.stateMap.load('data/states.json', { idOf: s => s.uf, labelOf: s => s.uf.toUpperCase() }),
      this.municipalMap.load('data/municipalities.json', { idOf: s => s.tse }),
    ]);
    this.names = new Map(municipalShapes.map(s => [s.tse, s.name]));
    this.ufOf = new Map(municipalShapes.map(s => [s.tse, s.uf]));
    this.feed = new MunicipalFeed(this.client, municipalShapes);
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
    for (const legend of document.querySelectorAll('.legend')) renderLegend(legend, this.palette.legend(runoff));
    this.stateMap.paint(uf => this.palette.fill(states[uf]));
    this.table.render(AREAS, states, runoff);
    if (!this.feed.loaded) this.#refreshMunicipalities(); // first pass as soon as there are votes
  }

  /** Municipal files are only worth fetching once the count has started. */
  #refreshMunicipalities() {
    if (!this.national?.validVotes || document.hidden) return;
    this.feed.refresh(() => {
      this.municipalMap.paint(code => this.palette.fill(this.feed.tallies.get(code)));
      $('municipal-status').textContent =
        `${formatInt(this.feed.loaded)} de ${formatInt(this.names.size)} municípios carregados · atualizados a cada ${MUNICIPAL_REFRESH_MS / 60_000} minutos`;
    });
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
