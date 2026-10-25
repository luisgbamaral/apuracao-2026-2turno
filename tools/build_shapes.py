"""Builds the two map files the page reads: data/states.json and data/municipalities.json.

Run once, from the repository root: python tools/build_shapes.py
Sources: IBGE boundaries (minimal quality) and municipality names, and the TSE list of municipalities of
the runoff, which links the TSE code used in the result files to the IBGE code used in the boundaries.

Both files share one equirectangular projection in integer units (1 unit = 0.005 degree), and every
path is written with relative moves, which keeps the national municipal map near 1 MB before gzip.
"""
import gzip
import json
import math
import urllib.request
from pathlib import Path

IBGE = "https://servicodados.ibge.gov.br/api"
MESH = IBGE + "/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson&intrarregiao={level}&qualidade=minima"
NAMES = IBGE + "/v1/localidades/municipios"
TSE_MUNICIPALITIES = "https://resultados.tse.jus.br/oficial/ele2026/6258/config/mun-e006258-cm.json"
UNITS_PER_DEGREE = 200
SQUEEZE = math.cos(math.radians(15))  # equirectangular, true at Brazil's mid latitude
WEST, NORTH = -74.0, 5.4
OUT = Path("data")
GZIP = bytes([0x1F, 0x8B])


def get(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        body = response.read()
    return json.loads((gzip.decompress(body) if body.startswith(GZIP) else body).decode('utf-8'))  # IBGE always gzips


def project(lon, lat):
    return round((lon - WEST) * SQUEEZE * UNITS_PER_DEGREE), round((NORTH - lat) * UNITS_PER_DEGREE)


def rings(geometry):
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for polygon in polygons:
        for ring in polygon:
            points = []
            for lon, lat in ring:
                point = project(lon, lat)
                if not points or point != points[-1]:
                    points.append(point)
            if len(points) >= 3:
                yield points


def path(geometry):
    """SVG path with an absolute start and relative moves for every ring."""
    out = []
    for ring in rings(geometry):
        (x, y), steps = ring[0], []
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            steps.append(f"{x1 - x0},{y1 - y0}")
        out.append(f"M{x},{y}l" + " ".join(steps) + "z")
    return "".join(out)


def box(geometry):
    points = [p for ring in rings(geometry) for p in ring]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def main():
    tse = get(TSE_MUNICIPALITIES)
    by_ibge = {int(m["cdi"]): (state["cd"], m["cd"]) for state in tse["abr"] if state["cd"] != "zz" for m in state["mu"]}
    names = {m["id"]: m["nome"] for m in get(NAMES)}
    municipalities = get(MESH.format(level="municipio"))["features"]
    states = get(MESH.format(level="UF"))["features"]
    uf_of = {code // 100000: uf for code, (uf, _) in by_ibge.items()}

    state_rows = []
    for feature in states:
        geometry, code = feature["geometry"], int(feature["properties"]["codarea"])
        x0, y0, x1, y1 = box(geometry)
        main_ring = max(rings(geometry), key=len)
        label = [round((min(p[0] for p in main_ring) + max(p[0] for p in main_ring)) / 2),
                 round((min(p[1] for p in main_ring) + max(p[1] for p in main_ring)) / 2)]
        state_rows.append({"uf": uf_of[code], "box": [x0, y0, x1, y1], "label": label, "d": path(geometry)})

    municipal_rows, missing = [], []
    for feature in municipalities:
        code = int(feature["properties"]["codarea"])
        if code not in by_ibge:
            missing.append(code)
            continue
        uf, tse_code = by_ibge[code]
        municipal_rows.append({"tse": tse_code, "uf": uf, "name": names[code], "d": path(feature["geometry"])})
    assert not missing, f"IBGE municipalities without a TSE code: {missing}"
    # The TSE may list a municipality newer than the IBGE boundaries; it counts in every total, just has no shape.
    drawn = {r["tse"] for r in municipal_rows}
    print("TSE municipalities without a boundary:", [(uf, code) for uf, code in by_ibge.values() if code not in drawn])

    xs = [r["box"][2] for r in state_rows]
    ys = [r["box"][3] for r in state_rows]
    view_box = [0, 0, max(xs), max(ys)]
    OUT.mkdir(exist_ok=True)
    for name, rows in (("states", state_rows), ("municipalities", municipal_rows)):
        target = OUT / f"{name}.json"
        target.write_text(json.dumps({"viewBox": view_box, "shapes": rows}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{target}: {len(rows)} shapes, {target.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
