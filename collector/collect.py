#!/usr/bin/env python3
"""
Recol·lector de les estacions meteorològiques de Subirats.

Desa:
  data/current.json   - última lectura de cada estació
  data/history.jsonl  - una línia per passada (s'hi va afegint)
  data/daily.json     - resum diari agregat a partir de l'històric

Només fa servir la biblioteca estàndard de Python.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

UA = "Mozilla/5.0 (compatible; meteo-subirats/1.0; +https://github.com/jsalvia/meteo-subirats)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

SANT_PAU_URL = "https://www.weatherlink.com/embeddablePage/getData/bf48e8ffb92245b495f64248001dff73"

# Weathercloud: (clau, nom, id amb zeros)
WEATHERCLOUD = [
    ("lavern", "Lavern · El Llebeig", "2131348548"),
    ("ordal", "Ordal · Meteo Ordal", "0154096948"),
    ("canmila", "Can Milà de la Roca", "1608794808"),
    ("cantallops", "Cantallops", "0379499406"),
    ("n340", "N-340 PK 1224", "6275944158"),
]

# Meteoclimatic: (clau, codi d'estació)
METEOCLIMATIC = [
    ("ordal", "ESCAT0800000008739B"),
    ("lavern", "ESCAT0800000008739C"),
    ("cantallops", "ESCAT0800000008739A"),
]

TZ = timezone(timedelta(hours=2))  # CEST; el desfasament real va bé per als resums diaris


def get(url, headers=None, tries=3, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    return None


def num(x):
    try:
        return float(x)
    except Exception:
        return None


def sant_pau():
    raw = get(SANT_PAU_URL)
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    return {
        "clau": "santpau",
        "nom": "Sant Pau d'Ordal",
        "xarxa": "WeatherLink",
        "temp": num(d.get("temperature")),
        "hum": num(d.get("humidity")),
        "vent": num(d.get("wind")),
        "ratxa": num(d.get("gust")),
        "pluja_avui": num(d.get("rain")),
        "pluja_temporada": num(d.get("seasonalRain")),
        "pressio": num(d.get("barometer")),
        "font": "https://meteosantpau.eu/",
    }


def weathercloud(i):
    clau, nom, did = i
    raw = get(
        "https://app.weathercloud.net/device/values/%d" % int(did),
        {"Referer": "https://app.weathercloud.net/d" + did},
        tries=2,
    )
    try:
        d = json.loads(raw) if raw else None
    except Exception:
        d = None
    if not d:
        return None
    return {
        "clau": clau,
        "nom": nom,
        "xarxa": "Weathercloud",
        "temp": num(d.get("temp")),
        "hum": num(d.get("hum")),
        "vent": num(d.get("wspd")),
        "ratxa": num(d.get("wspdhi")),
        "pluja": num(d.get("rain")),
        "pluja_avui": None,
        "pressio": num(d.get("bar")),
        "font": "https://app.weathercloud.net/d" + did,
    }


def meteoclimatic(i):
    clau, codi = i
    xml = get("https://www.meteoclimatic.net/feed/rss/" + codi, tries=1)
    if not xml:
        return None
    m = re.search(r"<title>([^<]+)</title>", xml)
    nom = m.group(1).strip() if m else codi
    def troba(pat):
        mm = re.search(pat, xml, re.S | re.I)
        return num(mm.group(1)) if mm else None
    return {
        "clau": clau + "-mc",
        "nom": nom,
        "xarxa": "Meteoclimatic",
        "temp": troba(r"temperatura[^0-9\-]*(-?\d+[.,]?\d*)"),
        "hum": troba(r"humitat[^0-9]*(\d+[.,]?\d*)"),
        "pluja": None,
        "pluja_avui": None,
        "font": "https://www.meteoclimatic.net/perfil/" + codi,
    }


def resum_diari(files):
    dies = {}
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                for linia in fh:
                    linia = linia.strip()
                    if not linia:
                        continue
                    r = json.loads(linia)
                    for e in r.get("estacions", []):
                        if e.get("temp") is None and e.get("pluja") is None:
                            continue
                        dia = datetime.fromtimestamp(r["epoch"], TZ).strftime("%Y-%m-%d")
                        k = (dia, e["clau"])
                        d = dies.setdefault(k, {"dia": dia, "clau": e["clau"], "tmin": None, "tmax": None, "pluja_max": None})
                        if e.get("temp") is not None:
                            d["tmin"] = e["temp"] if d["tmin"] is None else min(d["tmin"], e["temp"])
                            d["tmax"] = e["temp"] if d["tmax"] is None else max(d["tmax"], e["temp"])
                        # el camp de pluja de les estacions és acumulatiu: ens quedem el valor més alt del dia
                        for camp in ("pluja_avui", "pluja", "pluja_temporada"):
                            if e.get(camp) is not None:
                                d["pluja_max"] = e[camp]
                                break
        except Exception:
            continue
    return sorted(dies.values(), key=lambda d: (d["dia"], d["clau"]), reverse=True)[:400]


def main():
    os.makedirs(DATA, exist_ok=True)
    ara = int(time.time())
    estacions = []

    s = sant_pau()
    if s:
        estacions.append(s)

    for i in WEATHERCLOUD:
        r = weathercloud(i)
        if r:
            estacions.append(r)
        time.sleep(1.2)

    for i in METEOCLIMATIC:
        r = meteoclimatic(i)
        if r:
            estacions.append(r)
        time.sleep(1.0)

    current = {
        "actualitzat": datetime.fromtimestamp(ara, TZ).isoformat(),
        "epoch": ara,
        "estacions": estacions,
    }
    with open(os.path.join(DATA, "current.json"), "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=1)

    with open(os.path.join(DATA, "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(current, ensure_ascii=False) + "\n")

    diari = resum_diari([os.path.join(DATA, "history.jsonl")])
    with open(os.path.join(DATA, "daily.json"), "w", encoding="utf-8") as f:
        json.dump(diari, f, ensure_ascii=False, indent=1)

    print("OK: %d estacions amb lectura de %d provades" % (len(estacions), len(WEATHERCLOUD) + len(METEOCLIMATIC) + 1))


if __name__ == "__main__":
    main()
