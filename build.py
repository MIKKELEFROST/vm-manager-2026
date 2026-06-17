#!/usr/bin/env python3
"""
Build index.html for the VM Manager 2026 player table.

Combines two sources:
  * STATIC  (committed spillere_world_manager_2026.csv): Land, Rang, Markedsvaerdi,
            Program R1-3, Runde 1-3, Position  -- not available from the API.
  * LIVE    (Holdet public API, game 616):            Pris, Popularitet, Ude af spil
            matched onto the static rows by normalized player name.

Vaerdi-indeks is recomputed as Markedsvaerdi / Pris (matches the XLSX formula).

The committed CSV stays the authoritative player set (1522 players) so the table
mirrors the user's sheet; only the live-changing fields are refreshed.

Usage:
  python build.py            # scheduled run: only proceeds during the Danish update window
  python build.py --force    # always build (manual / local runs)
"""
import csv, json, re, sys, unicodedata, urllib.request
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

API_URL  = "https://nexus-app-fantasy.holdet.dk/api/games/616/players"
CSV_FILE = "spillere_world_manager_2026.csv"
TEMPLATE = "index.template.html"
OUTPUT   = "index.html"

# Danish local hours at which a scheduled run should actually rebuild:
# every 2 hours between 19:00 and 09:00 (19,21,23,01,03,05,07,09).
TARGET_HOURS = {19, 21, 23, 1, 3, 5, 7, 9}

COLS = [
    {"key": "Navn",          "label": "Navn",              "type": "text"},
    {"key": "Land",          "label": "Land",              "type": "text", "filter": "select"},
    {"key": "Rang",          "label": "Rang",              "type": "int",
     "hint": "Nationens seedning 1-48 (deles af alle spillere fra samme land)"},
    {"key": "Position",      "label": "Position",          "type": "text", "filter": "select"},
    {"key": "Pris",          "label": "Pris (€)",          "type": "money"},
    {"key": "Markedsværdi",  "label": "Markedsværdi (€)",   "type": "money"},
    {"key": "Værdi-indeks",  "label": "Værdi-indeks",        "type": "float"},
    {"key": "Popularitet",   "label": "Popularitet",       "type": "pct"},
    {"key": "Ude af spil",   "label": "Ude af spil",       "type": "text", "filter": "select"},
    {"key": "Program R1-3",  "label": "Program R1-3",      "type": "float"},
    {"key": "Runde 1",       "label": "Runde 1",           "type": "text"},
    {"key": "Runde 2",       "label": "Runde 2",           "type": "text"},
    {"key": "Runde 3",       "label": "Runde 3",           "type": "text"},
]

# CSV header -> (row key, parser)
SRC = {
    "Navn": ("Navn", "text"), "Land": ("Land", "text"), "Rang": ("Rang", "int"),
    "Position": ("Position", "text"), "Pris": ("Pris", "int"),
    "Markedsværdi (EUR)": ("Markedsværdi", "int"),
    "Værdi-indeks": ("Værdi-indeks", "float"),
    "Popularitet": ("Popularitet", "float"), "Ude af spil": ("Ude af spil", "text"),
    "Program R1-3": ("Program R1-3", "float"),
    "Runde 1": ("Runde 1", "text"), "Runde 2": ("Runde 2", "text"), "Runde 3": ("Runde 3", "text"),
}


def parse(v, t):
    v = (v or "").strip()
    if v == "":
        return None
    if t == "int":
        try: return int(float(v.replace(",", ".")))
        except ValueError: return None
    if t == "float":
        try: return float(v.replace(",", "."))
        except ValueError: return None
    return v


def norm(s):
    """Normalize a name for matching: drop quoted nicknames, diacritics and punctuation."""
    s = s or ""
    s = re.sub(r'["“”‘’\'].*?["“”‘’\']', " ", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def in_window():
    if "--force" in sys.argv:
        return True
    if ZoneInfo is None:
        return True  # fail open if tz database is unavailable
    hour = datetime.now(ZoneInfo("Europe/Copenhagen")).hour
    return hour in TARGET_HOURS


def fetch_api():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "vm-manager-2026-builder"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    persons = data.get("_embedded", {}).get("persons", {})
    live = {}
    for it in data.get("items", []):
        p = persons.get(str(it.get("personId"))) or persons.get(it.get("personId")) or {}
        name = ((p.get("firstName") or "") + " " + (p.get("lastName") or "")).strip()
        if not name:
            continue
        live[norm(name)] = {
            "price": it.get("price"),
            "pop": it.get("popularity"),
            "out": bool(it.get("isOut")),
        }
    return live


def main():
    if not in_window():
        h = datetime.now(ZoneInfo("Europe/Copenhagen")).hour if ZoneInfo else "?"
        print(f"Skip: Copenhagen hour {h} not in update window {sorted(TARGET_HOURS)}")
        return 0

    # 1. static rows from the committed CSV (authoritative player set)
    rows = []
    with open(CSV_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            obj = {key: parse(r.get(src, ""), t) for src, (key, t) in SRC.items()}
            rows.append(obj)

    # 2. live fields from the API
    try:
        live = fetch_api()
    except Exception as e:
        print(f"ERROR: API fetch failed ({e}); leaving {OUTPUT} unchanged", file=sys.stderr)
        return 1
    if len(live) < 500:
        print(f"ERROR: API returned only {len(live)} players; aborting to avoid corrupting data", file=sys.stderr)
        return 1

    # 3. merge live onto static rows by normalized name
    matched = 0
    for obj in rows:
        hit = live.get(norm(obj["Navn"]))
        if hit:
            matched += 1
            if hit["price"] is not None:
                obj["Pris"] = hit["price"]
            if hit["pop"] is not None:
                obj["Popularitet"] = hit["pop"]
            obj["Ude af spil"] = "Ja" if hit["out"] else "Nej"
        # recompute value index = market value / price
        mv, pris = obj.get("Markedsværdi"), obj.get("Pris")
        obj["Værdi-indeks"] = round(mv / pris, 2) if (mv and pris) else None

    stamp = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%Y-%m-%d %H:%M") if ZoneInfo \
        else datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"Matched {matched}/{len(rows)} players to live API data.")

    data = {"generated": stamp, "source": "Holdet.dk · VM Manager 2026",
            "columns": COLS, "rows": rows}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    if html.count("__DATASET__") != 1:
        print("ERROR: template placeholder __DATASET__ not found exactly once", file=sys.stderr)
        return 1
    html = html.replace("__DATASET__", payload)
    # surface the data freshness in the page subtitle
    html = html.replace(
        'Interaktivt datasæt · Kilde: Holdet.dk · VM Manager 2026',
        f'Interaktivt datasæt · Kilde: Holdet.dk · Opdateret {stamp}', 1)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUTPUT} ({len(html):,} bytes) · generated {stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
