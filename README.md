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
src/forecast.js            Forecast (point, uncertainty, chance)
src/forecast-view.js       ForecastView (bet, chances, time series)
src/cheer.js               LeadCheer (song excerpt when Lula takes the lead, opt-in)
model/                     data extraction, synthetic counts, calibration, export, tests
```

Design notes:

- **Colour follows the candidate.** Blue is Flávio Bolsonaro (22) and red is Lula (13), fixed by ballot number in `src/config.js`. Shades are mixed with the page surface, so they hold in dark mode.
- **The shade is the lead, in points of the valid votes:** up to 5, 5 to 15, more than 15.
- **Nobody swaps sides.** The candidates keep the TSE's ballot order on screen whoever leads.
- **A winner is shown only when the TSE says so:** its "Eleito" status after the count, or its mathematically-decided flag before that, as a neutral tag.
- **Maps are plain SVG.** `tools/build_shapes.py` projects the IBGE boundaries once (equirectangular, integer units, relative moves), so the browser only sets fills. One municipality created after the IBGE boundaries (Boa Esperança do Norte, MT) counts in every total but has no shape.
- **A missing file never blanks the page.** Each request fails on its own and keeps the last good count.

## Forecast

Every minute, once all municipal files are read, the page forecasts the final two-party share and each candidate's chance of winning, with an 80% interval, and keeps a time series of the chances in the browser. A plain-language methodology sits at the end of the forecast card.

- **Point.** Counted votes, plus each municipality's remaining votes at a share that blends its own partial count (weight f/(f+1.5), f = share of its sections counted) with a base: its 2026 first-round two-party share plus the swing seen so far in its state, or nationally while the state has under 1% counted. Remaining votes come from the uncounted electorate at a blended rate of votes per elector.
- **Uncertainty.** Student t (5 degrees of freedom) with sigma^2 = R^(2a) (c^2 + kappa^2 D^2) + tau^2 sum_s (R_s (o0 + O_s))^2 + floor^2, where R is the expected share of votes still to count (R_s per state), D how different the regional mix of what is left is from what came in, and O_s the first-round share of other candidates in the state. Floors keep the start humble: 2.5 points until 3% is counted, 1 point while half of what is left sits in states with under 5% counted. "Defined" only when the lead exceeds every voter left to count.
- **Calibration.** 500 synthetic elections from the real 2018 and 2022 runoffs (sections shocked by regional, state and municipal swings, half of them within one point of a tie), each counted in an order drawn from families seen on Brazilian nights: states and regions in waves, North and Northeast late, capitals and big cities late, order tied to lean or to other candidates' share, whole electoral zones arriving in blocks.

| Check (500 synthetic elections, 14 moments) | Result |
|---|---|
| Loser given 99% or more at any moment | 0% |
| Loser given 95% or more at any moment | 4% |
| 90% interval coverage, all / 2022 mold / 2018 mold | 95% / 97% / 94% |
| 90% interval coverage by share counted | 86% to 99% |
| Calibration error of the chance (ECE) | 0.089 (target was 0.03; the chance errs on the humble side mid-count) |
| Fitted on 2022 only, tested on 2018 | 64% coverage: 2018 (38% of first-round votes for other candidates) is a harder regime than 2022 and 2026 (about 8%) |

The page and its Python twin (`model/plan_b.py`) agree to 1e-13 on 32 golden snapshots (`model/golden.py`); a forecast takes under 10 ms.

**Tested and left out.** XGBoost, LightGBM, CatBoost and random forest, tuned with Optuna (20 trials each) and validated leave-one-election-out on municipal shares, did not beat the base (RMSE 0.0234, 0.0236, 0.0247 and 0.0245 against 0.0233); trees cannot extrapolate the level of a new election. A ridge regression of the swing on municipal characteristics with a vote-transfer term was worse on the synthetic counts. Adding the TSE electorate profile (education, age, sex; `model/demographics.py`) was tested on the real 2018 and 2022 runoffs counted in 60 orders each (`model/test_demographics.py`): mean national error 1.12 and 0.94 points against 1.17 and 0.66 for the state-mean swing, short of the 10% gain required in both years. Laya, a local text model with calibrated typed answers, scored a Brier of 0.355 on 294 anonymised synthetic snapshots against 0.128 for the forecast and 0.257 for the raw count (`model/laya_report.json`). The design was reviewed by a panel of agents (statistics, applied mathematics, empirical economics, data science, quantitative political science) that reached a consensus; the published version is its fallback plan, because the full model's acceptance criteria were not met in time.

**Rebuild** (needs the section panel of `rio_painel_secao`): `python model/sections.py`, `python model/calibrate.py 250 18 2018 model/cache/calib_2018.parquet`, the same for 2022, `python model/fit_sigma.py`, `python model/export.py`, `python model/golden.py`.

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
sed -i -E 's/\?v=[0-9]+/?v=4/' index.html src/*.js
```
