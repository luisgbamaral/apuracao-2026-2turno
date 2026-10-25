const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = text => String(text).replace(/[&<>"']/g, ch => ESCAPES[ch]);
export const formatInt = n => n.toLocaleString('pt-BR');
const formatPoints = n => n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const swatch = color => `<i class="swatch" style="background:${color}"></i>`;

/** The two candidates side by side, with photo, share, votes and one bar split between them. */
export class HeadToHead {
  constructor(card, palette) {
    this.summary = card.querySelector('.sub');
    this.body = card.querySelector('.duel');
    this.palette = palette;
  }

  render(tally, candidates) {
    if (!tally) {
      this.body.innerHTML = '<p class="sub">Sem dados do TSE no momento.</p>';
      return;
    }
    const winner = tally.winner;
    const tag = c => (winner?.number !== c.number ? ''
      : `<span class="tag">${tally.hasStatuses ? 'Eleito' : 'Matematicamente eleito'}</span>`);
    const [left, right] = candidates; // ballot order of the TSE file, so nobody swaps sides mid-count
    const share = c => (tally.validVotes ? (100 * c.votes) / tally.validVotes : 0);
    this.summary.textContent = tally.leader
      ? `${tally.leader.name} à frente por ${formatInt(tally.lead)} votos (${formatPoints(tally.margin)} pontos)`
      : 'Aguardando os primeiros votos totalizados.';
    this.body.innerHTML = `
      <div class="pair">${candidates.map(c => `
        <figure class="candidate${tally.leader?.number === c.number ? ' leading' : ''}" style="--c:${this.palette.colorOf(c)}">
          <img src="${c.photo}" alt="" loading="lazy" onerror="this.remove()">
          <figcaption>
            <span class="name">${esc(c.name)} <small>${esc(c.party)}</small>${tag(c)}</span>
            <b>${c.pct}%</b>
            <span class="sub">${formatInt(c.votes)} votos</span>
          </figcaption>
        </figure>`).join('')}
      </div>
      <div class="split" role="img" aria-label="Divisão dos votos válidos">
        <span style="width:${share(left)}%;background:${this.palette.colorOf(left)}"></span>
        <span style="width:${share(right)}%;background:${this.palette.colorOf(right)}"></span>
        <i class="half" title="50% dos votos válidos"></i>
      </div>`;
  }
}

/** Legend of a runoff map: one row per candidate, one swatch per band of the lead. */
export function renderLegend(element, rows) {
  element.innerHTML = rows.map(row =>
    `<div><span class="who">${esc(row.name)}</span>${row.swatches.map(s => `<span>${swatch(s.color)}${s.label}</span>`).join('')}</div>`).join('') +
    `<div><span>${swatch('var(--none)')}sem votos ou empate</span></div>`;
}

/** Tooltip body for one area. */
export function describeTally(title, tally, palette) {
  if (!tally) return `<strong>${esc(title)}</strong><span class="sub">ainda não carregado</span>`;
  return `<strong>${esc(title)}</strong><span class="sub">${tally.sectionsPct}% das seções totalizadas</span>` +
    tally.ranked.map(c => `<div><span>${swatch(palette.colorOf(c))}${esc(c.name)}</span><b>${c.pct}%</b></div>`).join('');
}

/** Table view of the state map, plus the votes cast abroad. */
export class StateTable {
  constructor(table, palette) {
    this.table = table;
    this.palette = palette;
  }

  render(areas, tallies, candidates) {
    const head = candidates.map(c => `<th class="num">${swatch(this.palette.colorOf(c))}${esc(c.name)}</th>`).join('');
    const rows = Object.entries(areas).map(([uf, name]) => {
      const tally = tallies[uf];
      const pct = c => tally?.candidates.find(x => x.number === c.number)?.pct;
      const leader = tally?.leader;
      return `<tr><td>${name}</td><td class="num">${tally ? `${tally.sectionsPct}%` : '–'}</td>` +
        candidates.map(c => `<td class="num">${pct(c) ? `${pct(c)}%` : '–'}</td>`).join('') +
        `<td>${leader ? `${swatch(this.palette.colorOf(leader))}${esc(leader.name)} +${formatPoints(tally.margin)}` : '–'}</td></tr>`;
    });
    this.table.innerHTML =
      `<thead><tr><th>Estado</th><th class="num">Seções</th>${head}<th>Vantagem (pontos)</th></tr></thead>` +
      `<tbody>${rows.join('')}</tbody>`;
  }
}
