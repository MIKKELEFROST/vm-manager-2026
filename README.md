# VM Manager 2026 — Spillerdata

Interaktiv, hostet tabel over spillerdata fra Holdet.dk's **VM World Manager 2026** (game id 616).
Siden er en enkelt, selvstændig `index.html` med søgning, sortering, filtre, paginering og CSV-eksport.

🌐 **Live:** https://mikkelefrost.github.io/vm-manager-2026/

## Hvordan live-opdatering virker

`index.html` genereres af [`build.py`](build.py), som fletter to kilder:

| Kilde | Kolonner |
|------|----------|
| **Live** – Holdet's offentlige API (`/api/games/616/players`) | Pris, Popularitet, Ude af spil |
| **Statisk** – `spillere_world_manager_2026.csv` | Land, Rang, Markedsværdi, Program R1-3, Runde 1-3, Position |

`Værdi-indeks` genberegnes som `Markedsværdi / Pris`. Spillere matches på normaliseret navn
(diakritiske tegn og kælenavne fjernes) — alle 1.522 spillere matcher API'et.

> **Bemærk:** Kun de live-kolonner opdateres automatisk. Markedsværdi (Transfermarkt), Rang og
> kampprogram er ikke i API'et og forbliver på de sidst manuelt opdaterede værdier i CSV'en.

## Tidsplan

GitHub Action [`update.yml`](.github/workflows/update.yml) kører hver time, men `build.py`
bygger kun i det danske vindue: **hver 2. time mellem 19:00 og 09:00** (19, 21, 23, 01, 03, 05, 07, 09),
beregnet i `Europe/Copenhagen` så det holder under både sommer- og vintertid.
Ændrer dataene sig, committes en ny `index.html`, og GitHub Pages redeployer automatisk.

- **Manuel opdatering:** kør workflowet "Opdater spillerdata" via *Actions*-fanen (Run workflow) — bygger altid.
- Planlagte cron-jobs sættes automatisk på pause efter 60 dages inaktivitet i repoet (kør manuelt for at genaktivere).

## Opdater de statiske data

Når Markedsværdi/Rang/kampprogram skal opdateres: erstat `spillere_world_manager_2026.csv`
(behold samme kolonner og `;`-separator) og commit. Næste build fletter live-tallene ovenpå.

## Lokal kørsel

```bash
python build.py --force   # ignorerer tidsvinduet og bygger med det samme
```
