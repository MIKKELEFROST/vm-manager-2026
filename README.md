# VM Manager 2026 — Spillerdata

Interaktiv, hostet tabel over spillerdata fra Holdet.dk's **VM World Manager 2026** (game id 616).
Siden er en enkelt, selvstændig `index.html` med søgning, sortering, filtre, paginering og CSV-eksport.

🌐 **Live:** https://mikkelefrost.github.io/vm-manager-2026/

## Hvordan live-opdatering virker

`index.html` genereres af [`build.py`](build.py), som fletter to kilder:

Tabellen leder med beslutnings-data (værdi + VM-form); land/rang/position er skubbet til højre.
Runde 1-3 og Program R1-3 er farvekodet efter modstandersværhedsgrad (rød = stærk modstander → grøn = svag),
udledt af modstanderens nationale seedning (`Rang` 1-48). Beregnes i selve siden, så det følger med ved hver opdatering.

| Kilde | Kolonner |
|------|----------|
| **Live** – API `/games/616/players` | Pris, **Vækst** (pris − startpris), Popularitet, Ude af spil |
| **VM** – API `/games/616/standings` | Gruppe, placering, kampe, grp.-point, målforskel (hold-niveau, joinet på land) |
| **Statisk** – `spillere_world_manager_2026.csv` | Land, Rang, Markedsværdi, Program R1-3, Runde 1-3, Position |

`Værdi-indeks` genberegnes som `Markedsværdi / Pris`. Spillere matches på normaliseret navn
(diakritiske tegn og kælenavne fjernes) — alle 1.522 spillere matcher API'et, alle 48 nationer matcher standings.

> **Bemærk:** API'et har ingen individuelle spillerstats (mål/assists/point findes ikke offentligt).
> `Vækst` er den bedste individuelle form-indikator (Holdet hæver prisen når en spiller præsterer);
> VM-stats er derfor på holdniveau. Markedsværdi (Transfermarkt), Rang og kampprogram er statiske
> og opdateres ved at erstatte CSV'en.

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
