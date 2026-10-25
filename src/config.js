export const TSE_BASE = 'https://resultados.tse.jus.br/oficial/ele2026';

// Runoff code from the TSE's oficial/comum/config/ele-c.json. "?eleicao=6257" points the page at the
// first round, which lets it be checked against real numbers before the runoff count starts.
export const ELECTION = new URLSearchParams(location.search).get('eleicao') ?? '6258';
export const PRESIDENT = '0001';

// Colour of each candidate by ballot number: blue for Flávio Bolsonaro, red for Lula.
export const CANDIDATE_COLORS = { 22: 'var(--flavio)', 13: 'var(--lula)' };

export const REFRESH_MS = 60_000; // the TSE serves each file with max-age=57
export const MUNICIPAL_REFRESH_MS = 300_000; // 5,570 files: refreshed less often, finished ones skipped

export const STATES = {
  ac: 'Acre', al: 'Alagoas', am: 'Amazonas', ap: 'Amapá', ba: 'Bahia', ce: 'Ceará', df: 'Distrito Federal',
  es: 'Espírito Santo', go: 'Goiás', ma: 'Maranhão', mg: 'Minas Gerais', ms: 'Mato Grosso do Sul',
  mt: 'Mato Grosso', pa: 'Pará', pb: 'Paraíba', pe: 'Pernambuco', pi: 'Piauí', pr: 'Paraná',
  rj: 'Rio de Janeiro', rn: 'Rio Grande do Norte', ro: 'Rondônia', rr: 'Roraima', rs: 'Rio Grande do Sul',
  sc: 'Santa Catarina', se: 'Sergipe', sp: 'São Paulo', to: 'Tocantins',
};
export const ABROAD = { zz: 'Exterior' }; // counted in the table, not on the maps
