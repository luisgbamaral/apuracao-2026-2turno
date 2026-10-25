"""Extracts, from the national section panel, the presidential vote of every section in the five votes used.

Output (model/cache/sections.parquet): one row per election x section with the votes of the left candidate
(13: Haddad 2018, Lula 2022 and 2026), the right candidate (17: Bolsonaro 2018; 22: Bolsonaro 2022,
Flávio Bolsonaro 2026), all valid votes and the electorate of the section (eleitores_federal, which adds up
to the TSE's national electorate).
Run from the repository root: python model/sections.py [path to painel_secao_br_2018_2026.parquet]
"""
import sys
from pathlib import Path

import duckdb

PANEL = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/luisg/rio_painel_secao/data/painel_secao_br_2018_2026.parquet"
OUT = Path("model/cache/sections.parquet")
RIGHT = {2018: 17, 2022: 22, 2026: 22}

OUT.parent.mkdir(parents=True, exist_ok=True)
right = " ".join(f"WHEN {year} THEN {number}" for year, number in RIGHT.items())
duckdb.sql(f"""
    COPY (SELECT ano, turno, lower(sg_uf) AS uf, cd_municipio AS mun, zona, secao,
                 coalesce(sum(qt_votos) FILTER (nr_votavel = 13), 0) AS l,
                 coalesce(sum(qt_votos) FILTER (nr_votavel = CASE ano {right} END), 0) AS r,
                 coalesce(sum(qt_votos) FILTER (nr_votavel NOT IN (95, 96)), 0) AS valid,
                 any_value(eleitores_federal) AS electorate
          FROM '{PANEL}' WHERE cd_cargo = 1 AND (ano, turno) IN ((2018, 1), (2018, 2), (2022, 1), (2022, 2), (2026, 1))
          GROUP BY ALL ORDER BY ALL)
    TO '{OUT}' (FORMAT parquet, COMPRESSION zstd)""")
print(duckdb.sql(f"SELECT ano, turno, count(*) AS sections, sum(l) AS l, sum(r) AS r, sum(valid) AS valid, sum(electorate) AS electorate FROM '{OUT}' GROUP BY ALL ORDER BY ALL").df())
