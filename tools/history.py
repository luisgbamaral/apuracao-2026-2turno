"""Computes the page's forecast every minute and publishes the series, so every visitor sees the whole night.

Reads the TSE files the page reads (national, states, municipalities of states whose count moved), runs the Python
twin of the page's forecast (model/plan_b.py, checked against src/forecast.js) with the published data/model.json,
appends a point in the page's own format and pushes history.json to the "history" branch every PUSH_EVERY seconds.
That branch is read through raw.githubusercontent.com, so a point never triggers a rebuild of the site.
Run from the repository root: python tools/history.py WORKTREE   (WORKTREE: a checkout of the history branch)
"""
import json
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import truststore

truststore.inject_into_ssl()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "model"))
from plan_b import forecast  # noqa: E402

BASE = "https://resultados.tse.jus.br/oficial/ele2026/6258/dados"
LEFT, RIGHT = "13", "22"
EVERY, PUSH_EVERY, RECHECK = 60, 120, 300  # seconds: forecast, push, re-read a state's municipalities anyway
WORKTREE = Path(sys.argv[1])
OUT = WORKTREE / "history.json"


def tally(uf, mun=""):
    """Two-party votes and progress of one TSE file, or None if it could not be read."""
    try:
        request = urllib.request.Request(f"{BASE}/{uf}/{uf}{mun}-c0001-e006258-u.json", headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=20) as r:
            j = json.load(r)
    except Exception as error:  # noqa: BLE001 - keep the last good file, as the page does
        print("unavailable", uf, mun, error, flush=True)
        return None
    votes = {c["n"]: int(c.get("vap") or 0) for g in j["carg"][0]["agr"] for p in g["par"] for c in p["cand"]}
    s, e = j.get("s", {}), j.get("e", {})
    return {"lc": votes.get(LEFT, 0), "rc": votes.get(RIGHT, 0), "ec": int(e.get("est") or 0), "e": int(e.get("te") or 0),
            "st": int(s.get("st") or 0), "ts": int(s.get("ts") or 0), "stamp": f"{j.get('dt')} {j.get('ht')} {s.get('st')}"}


def main():
    units = pd.read_json("data/units.json")
    params = json.loads(Path("data/model.json").read_text(encoding="utf-8"))
    ufs = sorted(units.uf.unique())  # the states and zz (abroad, read from its state file)
    municipalities = {uf: list(g.unit) for uf, g in units[units.uf != "zz"].groupby("uf")}
    history = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    tallies, synced, pushed = {}, {}, time.time()
    pool = ThreadPoolExecutor(32)
    while True:
        start = time.time()
        states = dict(zip(ufs, pool.map(tally, ufs)))
        for uf, st in states.items():
            if uf == "zz" or not st or not st["st"]:
                continue
            if st["stamp"] != synced.get(uf, ("",))[0] or start - synced[uf][1] > RECHECK:
                for unit, t in zip(municipalities[uf], pool.map(lambda u: tally(u[:2], u[2:]), municipalities[uf])):
                    tallies[unit] = t or tallies.get(unit)
                synced[uf] = (st["stamp"], start)
        if states.get("zz"):
            tallies["zz"] = states["zz"]
        read = sum(t["lc"] + t["rc"] for t in tallies.values() if t)
        counted = sum(t["lc"] + t["rc"] for t in states.values() if t)
        complete = all(uf in synced for uf, st in states.items() if uf != "zz" and st and st["st"])
        if counted and (complete or read >= 0.95 * counted):  # the page's rule: every counting state read, or 95% of its votes
            snap = units.rename(columns={"electorate_prior": "electorate"}).copy()
            get = lambda key, default=0: snap.unit.map(lambda u: (tallies.get(u) or {}).get(key, default))
            snap["lc"], snap["rc"], snap["ec"] = get("lc"), get("rc"), get("ec")
            snap["electorate"] = get("e").where(get("e") > 0, snap.electorate)
            snap["frac"] = get("st") / get("ts").where(get("ts") > 0, 1)
            f = forecast(snap, params)
            last = history[-1] if history else None
            same = last and last["counted"] == f["counted"] and abs(last["share"] - f["share"]) < 1e-6
            if not (same and time.time() * 1000 - last["at"] < 55_000):
                history.append({"at": int(time.time() * 1000), "counted": f["counted"], "share": f["share"], "chance": f["chance"]})
                OUT.write_text(json.dumps(history, separators=(",", ":")), encoding="utf-8")
                print(time.strftime("%H:%M:%S"), f"{100 * f['counted']:.2f}% apurado, Lula {100 * f['share']:.2f}%, chance {100 * f['chance']:.0f}%", flush=True)
        if time.time() - pushed >= PUSH_EVERY and subprocess.run(["git", "-C", str(WORKTREE), "diff", "--quiet"]).returncode:
            subprocess.run(["git", "-C", str(WORKTREE), "commit", "-qam", f"History at {time.strftime('%H:%M')}"], check=True)
            subprocess.run(["git", "-C", str(WORKTREE), "push", "-q", "origin", "history"], check=False)
            pushed = time.time()
        time.sleep(max(0, EVERY - (time.time() - start)))


if __name__ == "__main__":
    main()
