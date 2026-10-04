#!/usr/bin/env python3
"""
Recol·lector de les estacions meteorològiques de Subirats.

Fonts, per ordre de fiabilitat:
  1. Meteoclimatic (RSS)  - dona temperatura amb max/min, humitat, pressio, vent i precipitacio
  2. WeatherLink (JSON)   - Sant Pau d'Ordal
  3. Weathercloud (JSON)  - la resta; va a batzegades, s'hi reintenta

Desa:
  data/current.json   - última lectura
  data/history.jsonl  - una línia per passada
  data/daily.json     - resum diari
"""
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone, timedelta

UA = "Mozilla/5.0 (compatible; meteo-subirats/1.0; +https://github.com/jsalvia/meteo-subirats)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TZ = timezone(timedelta(hours=2))

SANT_PAU_URL = "https://www.weatherlink.com/embeddablePage/getData/bf48e8ffb92245b495f64248001dff73"

# Meteoclimatic: (codi, nom)
METEOCLIMATIC = [
    ("ESCAT0800000008739A", "Cantallops"),
    ("ESCAT0800000008739B", "Sant Pau d'Ordal"),
    ("ESCAT0800000008739C", "Lavern"),
]

# Weathercloud: (clau, nom, id amb zeros)
WEATHERCLOUD = [
    ("lavern-wc", "Lavern · El Llebeig", "2131348548"),
    ("ordal-wc", "Ordal · Meteo Ordal", "0154096948"),
    ("canmila", "Can Milà de la Roca", "1608794808"),
    ("cantallops-wc", "Cantallops (Weathercloud)", "0379499406"),
    ("n340", "N-340 PK 1224", "6275944158"),
]


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
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None


def meteoclimatic(codi, nom):
    xml = get("https://www.meteoclimatic.net/feed/rss/" + codi, tries=2)
    if not xml:
        return None
    m = re.search(r"<item>(.*?)</item>", xml, re.S)
    item = m.group(1) if m else ""
    d = re.search(r"<description>\s*<!\[CDATA\[(.*?)\]\]>", item, re.S)
    if not d:
        return None
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", d.group(1)))

    def v(pat):
        mm = re.search(pat, txt, re.I)
        return num(mm.group(1)) if mm else None

    return {
        "clau": "mc-" + codi[-4:].lower(),
        "nom": nom,
        "xarxa": "Meteoclimatic",
        "temp": v(r"Temperatura:\s*(-?[\d.,]+)"),
        "tmin": v(r"Mín\.?:\s*(-?[\d.,]+)\s*º?\s*C(?!\w)"),
        "hum": v(r"Humedad:\s*([\d.,]+)"),
        "vent": v(r"Viento:\s*([\d.,]+)"),
        "ratxa": v(r"Máx\.?:\s*([\d.,]+)\s*\)"),
        "pressio": v(r"Barómetro:\s*([\d.,]+)"),
        "pluja_avui": v(r"Precip\.?:\s*([\d.,]+)"),
        "font": "https://www.meteoclimatic.net/perfil/" + codi,
    }


def sant_pau():
    raw = get(SANT_PAU_URL)
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    return {
        "clau": "santpau-wl",
        "nom": "Sant Pau d'Ordal",
        "xarxa": "WeatherLink",
        "temp": num(d.get("temperature")),
        "hum": num(d.get("humidity")),
        "vent": num(d.get("wind")),
        "ratxa": num(d.get("gust")),
        "pressio": num(d.get("barometer")),
        "pluja_avui": num(d.get("rain")),
        "pluja_temporada": num(d.get("seasonalRain")),
        "font": "https://meteosantpau.eu/",
    }


def weathercloud(clau, nom, did):
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
        "pressio": num(d.get("bar")),
        "pluja": num(d.get("rain")),
        "font": "https://app.weathercloud.net/d" + did,
    }


def te_dades(e):
    return any(e.get(k) is not None for k in ("temp", "hum", "vent", "pluja", "pluja_avui"))


def resum_diari(fitxer):
    dies = {}
    try:
        with open(fitxer, encoding="utf-8") as fh:
            for linia in fh:
                linia = linia.strip()
                if not linia:
                    continue
                try:
                    r = json.loads(linia)
                except Exception:
                    continue
                for e in r.get("estacions", []):
                    dia = datetime.fromtimestamp(r["epoch"], TZ).strftime("%Y-%m-%d")
                    k = (dia, e["clau"])
                    d = dies.setdefault(k, {"dia": dia, "clau": e["clau"], "nom": e.get("nom"),
                                            "tmin": None, "tmax": None, "pluja": None})
                    if e.get("temp") is not None:
                        d["tmin"] = e["temp"] if d["tmin"] is None else min(d["tmin"], e["temp"])
                        d["tmax"] = e["temp"] if d["tmax"] is None else max(d["tmax"], e["temp"])
                    if e.get("pluja_avui") is not None:
                        d["pluja"] = e["pluja_avui"]
    except Exception:
        return []
    return sorted(dies.values(), key=lambda d: (d["dia"], d["clau"]), reverse=True)[:600]


def main():
    os.makedirs(DATA, exist_ok=True)
    ara = int(time.time())
    estacions = []
    fallades = []

    for codi, nom in METEOCLIMATIC:
        r = meteoclimatic(codi, nom)
        if r and te_dades(r):
            estacions.append(r)
        else:
            fallades.append("Meteoclimatic " + nom)
        time.sleep(0.8)

    r = sant_pau()
    if r and te_dades(r):
        estacions.append(r)
    else:
        fallades.append("WeatherLink Sant Pau")

    for clau, nom, did in WEATHERCLOUD:
        r = weathercloud(clau, nom, did)
        if r and te_dades(r):
            estacions.append(r)
        else:
            fallades.append("Weathercloud " + nom)
        time.sleep(1.2)

    current = {
        "actualitzat": datetime.fromtimestamp(ara, TZ).isoformat(),
        "epoch": ara,
        "estacions": estacions,
        "sense_lectura": fallades,
    }
    for cami, obj in ((os.path.join(DATA, "current.json"), current),):
        with open(cami, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    with open(os.path.join(DATA, "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(current, ensure_ascii=False) + "\n")

    with open(os.path.join(DATA, "daily.json"), "w", encoding="utf-8") as f:
        json.dump(resum_diari(os.path.join(DATA, "history.jsonl")), f, ensure_ascii=False, indent=1)

    print("OK: %d estacions amb dades | %d sense: %s" % (len(estacions), len(fallades), ", ".join(fallades)))


if __name__ == "__main__":
    main()
