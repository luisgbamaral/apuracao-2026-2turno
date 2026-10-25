"""Real counting order of the 2018 and 2022 runoffs, from the TSE ballot-box reports (boletins de urna, "bweb").

2022 reports carry DT_BU_RECEBIDO, the time the TSE received each section's report: the real order of the night.
2018 reports do not; their closing time (DT_ENCERRAMENTO) is used as a stand-in, which captures time zones and
queues but not the transmission order.
Writes model/cache/bweb/order_<year>.parquet (uf, mun, zona, secao, time) and deletes each downloaded file
once reduced. Run from the repository root: python model/real_order.py 2022 2018
"""
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

FOLDER = Path("model/cache/bweb")
PACKAGE = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-{year}-boletim-de-urna"


def urls(year):
    with urllib.request.urlopen(PACKAGE.format(year=year), timeout=120) as r:
        resources = json.load(r)["result"]["resources"]
    return [x["url"] for x in resources if x["url"].lower().endswith(".zip") and "_2t_" in x["url"].lower()]


def reduce(year, url):
    """Download one state's reports, keep one row per section with its time, delete the download."""
    archive = FOLDER / url.rsplit("/", 1)[1]
    out = FOLDER / f"order_{year}_{archive.stem}.parquet"
    if out.exists():
        return out
    urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as z:
        member = next(n for n in z.namelist() if n.lower().endswith((".csv", ".txt")))
        z.extract(member, FOLDER)
    csv = FOLDER / member
    names = [r[0] for r in duckdb.sql(f"DESCRIBE SELECT * FROM read_csv('{csv.as_posix()}', delim=';', header=true, encoding='latin-1', all_varchar=true)").fetchall()]
    uf = next(n for n in names if n.replace(" ", "") == "SG_UF")
    time = "DT_BU_RECEBIDO" if "DT_BU_RECEBIDO" in names else "DT_ENCERRAMENTO"
    duckdb.sql(f"""COPY (SELECT lower("{uf}") AS uf, CAST(CD_MUNICIPIO AS INT) AS mun, CAST(NR_ZONA AS INT) AS zona, CAST(NR_SECAO AS INT) AS secao,
                               min(try_strptime({time}, '%d/%m/%Y %H:%M:%S')) AS time, '{time}' AS source
                        FROM read_csv('{csv.as_posix()}', delim=';', header=true, encoding='latin-1', all_varchar=true)
                        WHERE CD_CARGO_PERGUNTA = '1' GROUP BY ALL)
                   TO '{out.as_posix()}' (FORMAT parquet)""")
    csv.unlink()
    archive.unlink()
    return out


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    for year in map(int, sys.argv[1:]):
        parts = [reduce(year, url) for url in urls(year)]
        d = pd.concat(pd.read_parquet(p) for p in parts)
        d.to_parquet(FOLDER / f"order_{year}.parquet")
        print(year, len(d), "sections", d.source.iloc[0], d.time.min(), d.time.max())


if __name__ == "__main__":
    main()
