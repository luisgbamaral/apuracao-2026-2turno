# Apuração 2026 · 2º turno

Live dashboard of the 2026 Brazilian presidential runoff, Flávio Bolsonaro against Lula, read straight from the public result files of the Superior Electoral Court (TSE). First round: [apuracao-2026](https://github.com/luisgbamaral/apuracao-2026).

**Live:** https://luisgbamaral.github.io/apuracao-2026-2turno/

- The two candidates side by side, with their official TSE photos, share, votes and a bar split at 50%.
- Map by state and map by municipality (all 5,570): blue where Flávio leads, red where Lula leads, darker as the lead widens. The municipal map zooms into any state.
- Table with both shares and the lead in every state and abroad.
- The national count refreshes every 60 seconds; municipalities every 5 minutes. Light or dark mode.

## How it works

The page is fully static: no build step, no dependencies, no backend. The TSE publishes one JSON file per area and allows cross-origin reads, so each visitor's browser fetches what it needs: Brazil, the 27 states and abroad every minute, and the 5,570 municipal files (under 1 kB gzipped each) in a background pass that skips municipalities already fully counted.

```
index.html                 the page
styles.css                 theme tokens and layout
data/states.json           projected state outlines        } built by tools/build_shapes.py
data/municipalities.json   projected municipal outlines    } from IBGE boundaries and the TSE list
src/config.js              election code, candidate colours, refresh intervals, states
src/tse.js                 TseClient (fetch) and Tally (one area)
src/municipal-feed.js      MunicipalFeed (throttled pass over the municipal files)
src/palette.js             RunoffPalette (hue by leader, shade by lead)
src/map.js                 ChoroplethMap (SVG map, tooltip, zoom)
src/views.js               HeadToHead, StateTable, legend and tooltip
src/live-page.js           LivePage (refresh loop)
src/app.js                 Dashboard
```

Design notes:

- **Colour follows the candidate.** Blue is Flávio Bolsonaro (22) and red is Lula (13), fixed by ballot number in `src/config.js`. Shades are mixed with the page surface, so they hold in dark mode.
- **The shade is the lead, in points of the valid votes:** up to 5, 5 to 15, more than 15.
- **Nobody swaps sides.** The candidates keep the TSE's ballot order on screen whoever leads.
- **A winner is shown only when the TSE says so:** its "Eleito" status after the count, or its mathematically-decided flag before that, as a neutral tag.
- **Maps are plain SVG.** `tools/build_shapes.py` projects the IBGE boundaries once (equirectangular, integer units, relative moves), so the browser only sets fills. One municipality created after the IBGE boundaries (Boa Esperança do Norte, MT) counts in every total but has no shape.
- **A missing file never blanks the page.** Each request fails on its own and keeps the last good count.

## Run locally

```bash
python -m http.server 8000
```

Then open http://localhost:8000. Before the runoff count starts, `?eleicao=6257` points the page at the first round, to check it against real numbers.

## Data

Results and photos: [TSE](https://resultados.tse.jus.br). Boundaries and names: [IBGE](https://servicodados.ibge.gov.br/api/docs). Counts are partial until the TSE closes the tally. This project is not affiliated with the TSE.

## Deploying

GitHub Pages caches every file for 10 minutes, so every stylesheet, script and import carries a `?v=N` query; bump it in one go before publishing:

```bash
sed -i -E 's/\?v=[0-9]+/?v=2/' index.html src/*.js
```
