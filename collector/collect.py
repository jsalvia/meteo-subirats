#!/usr/bin/env python3
"""
Recol·lector de les estacions meteorològiques de Subirats.

Una entrada per estació, amb totes les fonts fusionades.

Fonts:
  - Meteoclimatic (RSS): temperatura (amb max/min), humitat, pressio, vent, precipitacio
  - WeatherLink (JSON): Sant Pau d'Ordal, amb "pluja avui" i "pluja de temporada"
  - Weathercloud (JSON): cal obtenir el token CSRF de la galeta abans de demanar valors

Desa:
  data/current.json   - última lectura, una entrada per estació
  data/history.jsonl  - una línia per passada
  data/daily.json     - resum diari
"""
import http.cookiejar
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

# Registre canònic: una estació, totes les seves fonts
ESTACIONS = [
    {"id": "santpau", "nom": "Sant Pau d'Ordal", "mc": "ESCAT0800000008739B", "wl": True},
    {"id": "lavern", "nom": "Lavern", "mc": "ESCAT0800000008739C", "wc": "2131348548"},
    {"id": "cantallops", "nom": "Cantallops", "mc": "ESCAT0800000008739A", "wc": "0379499406"},
    {"id": "ordal", "nom": "Ordal", "wc": "0154096948"},
    {"id": "canmila", "nom": "Can Milà de la Roca", "wc": "1608794808"},
    {"id": "n340", "nom": "N-340 PK 1224", "wc": "6275944158"},
]

CAMP_MC = {
    "temp": r"Temperatura:\s*(-?[\d.,]+)",
    "hum": r"Humedad:\s*([\d.,]+)",
    "pressio": r"Barómetro:\s*([\d.,]+)",
    "vent": r"Viento:\s*([\d.,]+)",
    "pluja_avui": r"Precip\.?:\s*([\d.,]+)",
}
CAMP_WC = {
    "temp": "temp",
    "hum": "hum",
    "vent": "wspd",
    "ratxa": "wspdhi",
    "pressio": "bar",
    "pluja": "rain",
}
CAMP_WL = {
    "temp": "temperature",
    "hum": "humidity",
    "vent": "wind",
    "ratxa": "gust",
    "pressio": "barometer",
    "pluja_avui": "rain",
    "pluja_temporada": "seasonalRain",
}


def num(x):
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None


def get(url, headers=None, tries=3, timeout=15, opener=None):
    for i in range(tries):
        try:
            if opener:
                req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
                with opener.open(req, timeout=timeout) as r:
                    return r.read().decode("utf-8", "replace")
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    return None


# ---------- fonts ----------

def font_meteoclimatic(codi):
    xml = get("https://www.meteoclimatic.net/feed/rss/" + codi, tries=2)
    if not xml:
        return None
    m = re.search(r"<item>(.*?)</item>", xml, re.S)
    d = re.search(r"<description>\s*<!\[CDATA\[(.*?)\]\]>", m.group(1) if m else "", re.S)
    if not d:
        return None
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", d.group(1)))
    out = {}
    for k, pat in CAMP_MC.items():
        mm = re.search(pat, txt, re.I)
        out[k] = num(mm.group(1)) if mm else None
    return out


def font_weatherlink():
    raw = get(SANT_PAU_URL)
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    return {k: num(d.get(v)) for k, v in CAMP_WL.items()}


def font_weathercloud(did):
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    pagina = "https://app.weathercloud.net/d" + did
    if not get(pagina, tries=2, opener=opener):
        return None
    token = None
    for c in cj:
        if c.name == "WEATHERCLOUD_CSRF_TOKEN":
            token = c.value
    h = {"Referer": pagina, "X-Requested-With": "XMLHttpRequest"}
    if token:
        h["X-CSRF-TOKEN"] = token
    raw = get("https://app.weathercloud.net/device/values/%d" % int(did), h, tries=2, opener=opener)
    try:
        d = json.loads(raw) if raw else None
    except Exception:
        d = None
    if not d:
        return None
    return {k: num(d.get(v)) for k, v in CAMP_WC.items()}


# ---------- fusió ----------

def fusiona(entrades):
    """Primera font amb valor no nul per a cada camp. Les fonts anteriors tenen prioritat."""
    out = {}
    for e in entrades:
        if not e:
            continue
        for k, v in e.items():
            if v is not None and out.get(k) is None:
                out[k] = v
    return out


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
                dia = datetime.fromtimestamp(r["epoch"], TZ).strftime("%Y-%m-%d")
                for e in r.get("estacions", []):
                    eid = e.get("id") or e.get("clau") or e.get("nom") or "?"
                    d = dies.setdefault((dia, eid), {"dia": dia, "id": eid, "nom": e.get("nom", eid),
                                                     "tmin": None, "tmax": None, "pluja": None})
                    if e.get("temp") is not None:
                        d["tmin"] = e["temp"] if d["tmin"] is None else min(d["tmin"], e["temp"])
                        d["tmax"] = e["temp"] if d["tmax"] is None else max(d["tmax"], e["temp"])
                    if e.get("pluja_avui") is not None:
                        d["pluja"] = e["pluja_avui"]
    except Exception:
        return []
    return sorted(dies.values(), key=lambda d: (d["dia"], d["nom"]), reverse=True)[:900]


def resum_mensual(diaris):
    """Agrega el resum diari en mesos, per estacio."""
    mesos = {}
    for d in diaris:
        mes = d["dia"][:7]
        k = (mes, d["id"])
        m = mesos.setdefault(k, {"mes": mes, "id": d["id"], "nom": d["nom"],
                                "pluja": 0.0, "te_pluja": False,
                                "tmax": None, "tmin": None, "dies": 0})
        m["dies"] += 1
        if d.get("pluja") is not None:
            m["pluja"] += d["pluja"]
            m["te_pluja"] = True
        if d.get("tmax") is not None:
            m["tmax"] = d["tmax"] if m["tmax"] is None else max(m["tmax"], d["tmax"])
        if d.get("tmin") is not None:
            m["tmin"] = d["tmin"] if m["tmin"] is None else min(m["tmin"], d["tmin"])
    for m in mesos.values():
        if not m["te_pluja"]:
            m["pluja"] = None
        m.pop("te_pluja", None)
        if m["pluja"] is not None:
            m["pluja"] = round(m["pluja"], 1)
    return sorted(mesos.values(), key=lambda x: (x["mes"], x["nom"]), reverse=True)


def main():
    os.makedirs(DATA, exist_ok=True)
    ara = int(time.time())
    estacions = []

    for est in ESTACIONS:
        entrades = []
        fonts = []
        if est.get("mc"):
            e = font_meteoclimatic(est["mc"])
            entrades.append(e)
            if e:
                fonts.append("Meteoclimatic")
            time.sleep(0.8)
        if est.get("wl"):
            e = font_weatherlink()
            entrades.append(e)
            if e:
                fonts.append("WeatherLink")
        if est.get("wc"):
            e = font_weathercloud(est["wc"])
            entrades.append(e)
            if e:
                fonts.append("Weathercloud")
            time.sleep(1.5)

        dades = fusiona(entrades)
        dades.update({"id": est["id"], "nom": est["nom"], "xarxes": fonts})
        if any(dades.get(k) is not None for k in ("temp", "hum", "vent", "pluja", "pluja_avui")):
            estacions.append(dades)

    current = {
        "actualitzat": datetime.fromtimestamp(ara, TZ).isoformat(),
        "epoch": ara,
        "estacions": estacions,
    }
    with open(os.path.join(DATA, "current.json"), "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(current, ensure_ascii=False) + "\n")
    diaris = resum_diari(os.path.join(DATA, "history.jsonl"))
    with open(os.path.join(DATA, "daily.json"), "w", encoding="utf-8") as f:
        json.dump(diaris, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "monthly.json"), "w", encoding="utf-8") as f:
        json.dump(resum_mensual(diaris), f, ensure_ascii=False, indent=1)

    print("OK %d/%d estacions amb dades" % (len(estacions), len(ESTACIONS)))
    for e in estacions:
        print("   %-22s %6s C  %4s%%  fonts: %s" % (e["nom"], e.get("temp"), e.get("hum"), "/".join(e["xarxes"])))


if __name__ == "__main__":
    main()
