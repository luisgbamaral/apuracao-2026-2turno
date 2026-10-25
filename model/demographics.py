"""Electorate profile of every municipality (TSE perfil_eleitorado), as shares, for the swing regression.

Reads model/cache/perfil/perfil_eleitorado_<year>.zip and writes model/cache/perfil/demo_<year>.parquet with, per
unit: share of voters with higher education completed, share with at most incomplete primary education
(including illiterate and "reads and writes"), share aged 16 to 24, share aged 60 or more, and share of women.
Run from the repository root: python model/demographics.py 2018 2022 2026
"""
import sys
import zipfile
from pathlib import Path

import duckdb

FOLDER = Path("model/cache/perfil")


def build(year):
    archive = zipfile.ZipFile(FOLDER / f"perfil_eleitorado_{year}.zip")
    members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
    # One file per state when there are several; skip the national file then, so nobody is counted twice.
    members = [n for n in members if "BRASIL" not in n.upper()] if len(members) > 1 else members
    target = FOLDER / str(year)
    for member in members:
        if not (target / member).exists():
            archive.extract(member, target)
    csv = target / "*.csv"
    out = FOLDER / f"demo_{year}.parquet"
    source = f"read_csv('{csv.as_posix()}', delim=';', header=true, encoding='latin-1', all_varchar=false, ignore_errors=true, union_by_name=true)"
    names = [r[0] for r in duckdb.sql(f"DESCRIBE SELECT * FROM {source}").fetchall()]
    count = "QT_ELEITORES_PERFIL" if "QT_ELEITORES_PERFIL" in names else "QT_ELEITORES"  # renamed in the 2026 files
    duckdb.sql(f"""
        COPY (SELECT CASE WHEN SG_UF = 'ZZ' THEN 'zz' ELSE lower(SG_UF) || lpad(CAST(CD_MUNICIPIO AS VARCHAR), 5, '0') END AS unit,
                     sum({count}) AS voters,
                     sum({count}) FILTER (DS_GRAU_ESCOLARIDADE = 'SUPERIOR COMPLETO') / sum({count}) AS demo_higher_ed,
                     sum({count}) FILTER (DS_GRAU_ESCOLARIDADE IN ('ANALFABETO', 'LÊ E ESCREVE', 'ENSINO FUNDAMENTAL INCOMPLETO'))
                         / sum({count}) AS demo_low_ed,
                     sum({count}) FILTER (TRY_CAST(split_part(trim(DS_FAIXA_ETARIA), ' ', 1) AS INT) < 25)
                         / sum({count}) AS demo_young,
                     sum({count}) FILTER (TRY_CAST(split_part(trim(DS_FAIXA_ETARIA), ' ', 1) AS INT) >= 60) / sum({count}) AS demo_old,
                     sum({count}) FILTER (DS_GENERO = 'FEMININO') / sum({count}) AS demo_women
              FROM {source}
              GROUP BY 1)
        TO '{out.as_posix()}' (FORMAT parquet)""")
    print(year, duckdb.sql(f"SELECT count(*) AS units, sum(voters) AS voters, avg(demo_higher_ed) AS higher, avg(demo_low_ed) AS low, avg(demo_young) AS young, avg(demo_old) AS old, avg(demo_women) AS women FROM '{out.as_posix()}'").df().round(3).to_string(index=False))


if __name__ == "__main__":
    for y in sys.argv[1:]:
        build(int(y))
