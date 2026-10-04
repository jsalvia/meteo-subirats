# El temps a Subirats

Web pública amb les dades en directe de les estacions meteorològiques del municipi de **Subirats** (Alt Penedès).

Està publicada amb **GitHub Pages** (gratuït i sense servidor propi).

## Què hi ha

- `index.html` — la web. Un sol fitxer, sense dependències externes, que llegeix el JSON.
- `collector/collect.py` — el recol·lector. Només fa servir la biblioteca estàndard de Python.
- `data/current.json` — l'última lectura de cada estació.
- `data/history.jsonl` — una línia per passada (l'històric).
- `data/daily.json` — resum diari agregat.
- `.github/workflows/collect.yml` — l'automatització: cada 15 minuts recull i desa.

## Les estacions

| Estació | Xarxa |
|---|---|
| Sant Pau d'Ordal | WeatherLink · [meteosantpau.eu](https://meteosantpau.eu/) |
| Lavern · El Llebeig | Weathercloud |
| Ordal · Meteo Ordal | Weathercloud / Meteoclimatic |
| Can Milà de la Roca | Weathercloud |
| Cantallops | Weathercloud / Meteoclimatic |
| N-340 PK 1224 | Weathercloud |

## Avisos

- **Les dades de les estacions particulars no estan certificades.** Per a decisions oficials, feu servir el Servei Meteorològic de Catalunya.
- El camp de pluja de Weathercloud és **acumulatiu**, no diari.
- El feed de Weathercloud **va a batzegades**: cal espaiar les peticions i reintentar.
- Les dades de tercers (Weathercloud, Meteoclimatic, WeatherLink) tenen les **seves pròpies condicions d'ús**. Abans de reutilitzar-les, consulteu-les i demaneu permís als titulars de les estacions.

## Llicència

El codi d'aquest repositori és lliure. **Les dades no**: són de les estacions i de les xarxes que les publiquen.
