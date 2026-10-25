export const TSE_BASE = 'https://resultados.tse.jus.br/oficial/ele2026';

// Runoff code from the TSE's oficial/comum/config/ele-c.json. "?eleicao=6257" points the page at the
// first round, which lets it be checked against real numbers before the runoff count starts.
export const ELECTION = new URLSearchParams(location.search).get('eleicao') ?? '6258';
export const PRESIDENT = '0001';

// Colour of each candidate by ballot number: blue for Flávio Bolsonaro, red for Lula.
export const CANDIDATE_COLORS = { 22: 'var(--flavio)', 13: 'var(--lula)' };

// A song excerpt played when this candidate takes the national lead, stopped if the rival takes it back.
export const CHEER = { candidate: 13, rival: 22, name: 'Lula', track: '65TdX1tJ7TuK4763AqU0yG', seconds: 15 };

export const REFRESH_MS = 60_000; // the TSE serves each file with max-age=57
// The night's forecast series, computed by tools/history.py and published on the "history" branch.
export const HISTORY_URL = 'https://raw.githubusercontent.com/luisgbamaral/apuracao-2026-2turno/history/history.json';
export const HISTORY_REFRESH_MS = 120_000;
export const MUNICIPAL_REFRESH_MS = 60_000; // passes never overlap, and only fetch what may have changed

export const STATES = {
  ac: 'Acre', al: 'Alagoas', am: 'Amazonas', ap: 'Amapá', ba: 'Bahia', ce: 'Ceará', df: 'Distrito Federal',
  es: 'Espírito Santo', go: 'Goiás', ma: 'Maranhão', mg: 'Minas Gerais', ms: 'Mato Grosso do Sul',
  mt: 'Mato Grosso', pa: 'Pará', pb: 'Paraíba', pe: 'Pernambuco', pi: 'Piauí', pr: 'Paraná',
  rj: 'Rio de Janeiro', rn: 'Rio Grande do Norte', ro: 'Rondônia', rr: 'Roraima', rs: 'Rio Grande do Sul',
  sc: 'Santa Catarina', se: 'Sergipe', sp: 'São Paulo', to: 'Tocantins',
};
export const ABROAD = { zz: 'Exterior' }; // counted in the table, not on the maps
