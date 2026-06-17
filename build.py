#!/usr/bin/env python3
"""
Build index.html for the VM Manager 2026 player research table.

Sources:
  * STATIC  (committed spillere_world_manager_2026.csv): Land, Rang, Markedsvaerdi,
            Program R1-3, Runde 1-3, Position.
  * LIVE    (Holdet API /games/616/players): Pris, Vaekst (price-startPrice),
            Popularitet, Ude af spil -- matched onto static rows by normalized name.
  * VM      (Holdet API /games/616/standings): per-nation group-stage stats
            (gruppe, placering, kampe, point, maalforskel) -- joined by Danish team name.

Vaerdi-indeks is recomputed as Markedsvaerdi / Pris.

The committed CSV stays the authoritative player set (1522 players); the table
leads with value/form + VM stats (what you research to pick a team).

Usage:
  python build.py            # scheduled: only builds inside the Danish update window
  python build.py --force    # always build (manual / local runs)
"""
import csv, json, re, sys, unicodedata, urllib.request
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

PLAYERS_URL   = "https://nexus-app-fantasy.holdet.dk/api/games/616/players"
STANDINGS_URL = "https://nexus-app-fantasy.holdet.dk/api/games/616/standings"
ROUND_URL     = "https://nexus-app-fantasy.holdet.dk/api/games/616/rounds/{n}/players"
ROUNDS        = [1, 2, 3]  # de runder vi har kampprogram for; tomme indtil de spilles
CSV_FILE = "spillere_world_manager_2026.csv"
TEMPLATE = "index.template.html"
OUTPUT   = "index.html"

# Danish local hours at which a scheduled run rebuilds (every 2h, 19:00-09:00).
TARGET_HOURS = {19, 21, 23, 1, 3, 5, 7, 9}

# Column order = focus. Value + form + VM stats first; land/rang/program last.
COLS = [
    {"key": "Navn",         "label": "Navn",          "type": "text"},
    {"key": "Position",     "label": "Position",      "type": "text", "filter": "select"},
    {"key": "Pris",         "label": "Pris (€)",      "type": "money",
     "hint": "Nuværende holdpris (tæller mod budgettet)"},
    {"key": "Vækst",        "label": "Vækst (€)",     "type": "delta",
     "hint": "Samlet prisændring siden VM-start — markedets reaktion på form"},
    {"key": "VækstR1",      "label": "Vækst R1",      "type": "delta",
     "hint": "Prisændring i runde 1"},
    {"key": "VækstR2",      "label": "Vækst R2",      "type": "delta",
     "hint": "Prisændring i runde 2 (vises når runden er spillet)"},
    {"key": "VækstR3",      "label": "Vækst R3",      "type": "delta",
     "hint": "Prisændring i runde 3 (vises når runden er spillet)"},
    {"key": "Tendens",      "label": "Tendens",       "type": "int",
     "hint": "Handelstendens — hvor meget spilleren købes lige nu (højere = mere efterspurgt)"},
    {"key": "Værdi-indeks", "label": "Værdi-indeks",  "type": "float",
     "hint": "Markedsværdi delt med pris — værdi for pengene"},
    {"key": "Popularitet",  "label": "Popularitet",   "type": "pct",
     "hint": "Andel managers der har valgt spilleren"},
    {"key": "Markedsværdi", "label": "Markedsværdi (€)", "type": "money",
     "hint": "Reel transferværdi (Transfermarkt)"},
    {"key": "Gruppe",       "label": "Gruppe",        "type": "text",
     "hint": "Nationens VM-gruppe"},
    {"key": "VMPlac",       "label": "Plac.",         "type": "int",
     "hint": "Nationens placering i VM-gruppen"},
    {"key": "VMKampe",      "label": "Kampe",         "type": "int",
     "hint": "VM-kampe spillet af nationen"},
    {"key": "VMPoint",      "label": "Grp.-point",    "type": "int",
     "hint": "Nationens point i gruppespillet"},
    {"key": "VMMaalforskel", "label": "Målforskel",   "type": "int",
     "hint": "Nationens VM-målforskel (mål for − imod)"},
    {"key": "Ude af spil",  "label": "Ude af spil",   "type": "text", "filter": "select"},
    {"key": "Land",         "label": "Land",          "type": "text", "filter": "select"},
    {"key": "Rang",         "label": "Rang",          "type": "int",
     "hint": "Nationens seedning 1-48 (deles af alle spillere fra samme land)"},
    {"key": "Program R1-3", "label": "Program R1-3",  "type": "float",
     "hint": "Kampprogrammets sværhedsgrad runde 1-3 (1=svær … 3=let)"},
    {"key": "Runde 1",      "label": "Runde 1",       "type": "text"},
    {"key": "Runde 2",      "label": "Runde 2",       "type": "text"},
    {"key": "Runde 3",      "label": "Runde 3",       "type": "text"},
]

# CSV header -> (row key, parser) for the static columns
SRC = {
    "Navn": ("Navn", "text"), "Land": ("Land", "text"), "Rang": ("Rang", "int"),
    "Position": ("Position", "text"), "Pris": ("Pris", "int"),
    "Markedsværdi (EUR)": ("Markedsværdi", "int"),
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
        return True
    return datetime.now(ZoneInfo("Europe/Copenhagen")).hour in TARGET_HOURS


def now_stamp():
    if ZoneInfo:
        return datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%Y-%m-%d %H:%M")
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M")


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vm-manager-2026-builder"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def load_static_rows():
    rows = []
    with open(CSV_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            rows.append({key: parse(r.get(src, ""), t) for src, (key, t) in SRC.items()})
    return rows


def parse_players(api):
    persons = api.get("_embedded", {}).get("persons", {})
    live = {}
    for it in api.get("items", []):
        p = persons.get(str(it.get("personId"))) or {}
        name = ((p.get("firstName") or "") + " " + (p.get("lastName") or "")).strip()
        if not name:
            continue
        price, start = it.get("price"), it.get("startPrice")
        live[norm(name)] = {
            "price": price,
            "start": start,
            "vaekst": (price - start) if (price is not None and start is not None) else None,
            "pop": it.get("popularity"),
            "out": bool(it.get("isOut")),
        }
    return live


def person_norm_map(api):
    """personId (str) -> normalized name, for matching the per-round endpoints."""
    m = {}
    for pid, p in api.get("_embedded", {}).get("persons", {}).items():
        name = ((p.get("firstName") or "") + " " + (p.get("lastName") or "")).strip()
        if name:
            m[str(pid)] = norm(name)
    return m


def parse_round(rj, pmap):
    """round-players json -> {normName: {pc, trend}}; empty dict if round not played yet."""
    out = {}
    for it in rj.get("items", []):
        nn = pmap.get(str(it.get("personId")))
        if nn:
            out[nn] = {"pc": it.get("priceChange"), "trend": it.get("trend")}
    return out


def parse_standings(st):
    """Danish team name -> group-stage stats."""
    teams = {}
    for grp in st:
        g = (grp.get("name") or "").upper()
        for r in grp.get("rankings", []):
            name = (r.get("team") or {}).get("name")
            if not name:
                continue
            teams[name] = {
                "group": g, "rank": r.get("rank"), "matches": r.get("matches"),
                "points": r.get("points"),
                "gd": (r.get("goalsFor") or 0) - (r.get("goalsAgainst") or 0),
            }
    return teams


def merge(rows, live, standings, round_growth, trend_map):
    matched = 0
    for obj in rows:
        nn = norm(obj["Navn"])
        hit = live.get(nn)
        if hit:
            matched += 1
            if hit["price"] is not None:
                obj["Pris"] = hit["price"]
            obj["Vækst"] = hit["vaekst"]
            obj["startPris"] = hit["start"]
            if hit["pop"] is not None:
                obj["Popularitet"] = hit["pop"]
            obj["Ude af spil"] = "Ja" if hit["out"] else "Nej"
        else:
            obj["Vækst"] = None
            obj["startPris"] = None
        # per-round growth (priceChange) — None until the round is played
        for n in ROUNDS:
            rec = (round_growth.get(n) or {}).get(nn)
            obj["VækstR" + str(n)] = rec["pc"] if rec else None
        tr = trend_map.get(nn)
        obj["Tendens"] = tr["trend"] if tr else None
        # VM team stats by Danish land name
        vm = standings.get(obj.get("Land"))
        obj["Gruppe"]        = vm["group"]   if vm else None
        obj["VMPlac"]        = vm["rank"]    if vm else None
        obj["VMKampe"]       = vm["matches"] if vm else None
        obj["VMPoint"]       = vm["points"]  if vm else None
        obj["VMMaalforskel"] = vm["gd"]      if vm else None
        # value index = market value / price
        mv, pris = obj.get("Markedsværdi"), obj.get("Pris")
        obj["Værdi-indeks"] = round(mv / pris, 2) if (mv and pris) else None
    return matched


def render(rows, stamp, iso, rounds_played):
    data = {"generated": stamp, "generatedISO": iso, "source": "Holdet.dk · VM Manager 2026",
            "roundsPlayed": rounds_played, "columns": COLS, "rows": rows}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    if html.count("__DATASET__") != 1:
        raise RuntimeError("template placeholder __DATASET__ not found exactly once")
    html = html.replace("__DATASET__", payload)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    return len(html)


def main():
    if not in_window():
        h = datetime.now(ZoneInfo("Europe/Copenhagen")).hour if ZoneInfo else "?"
        print(f"Skip: Copenhagen hour {h} not in update window {sorted(TARGET_HOURS)}")
        return 0

    rows = load_static_rows()
    try:
        api = fetch_json(PLAYERS_URL)
        live = parse_players(api)
        pmap = person_norm_map(api)
        standings = parse_standings(fetch_json(STANDINGS_URL))
        round_growth, rounds_played = {}, []
        for n in ROUNDS:
            try:
                rj = fetch_json(ROUND_URL.format(n=n))
            except Exception:
                rj = {"items": []}
            rg = parse_round(rj, pmap)
            round_growth[n] = rg
            if rg:
                rounds_played.append(n)
        # trend = buy-demand from the most recently played round
        trend_map = round_growth.get(max(rounds_played)) if rounds_played else {}
    except Exception as e:
        print(f"ERROR: API fetch failed ({e}); leaving {OUTPUT} unchanged", file=sys.stderr)
        return 1
    if len(live) < 500 or len(standings) < 40:
        print(f"ERROR: suspiciously little data (players={len(live)}, teams={len(standings)}); aborting",
              file=sys.stderr)
        return 1

    matched = merge(rows, live, standings, round_growth, trend_map or {})
    stamp = now_stamp()
    iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    size = render(rows, stamp, iso, rounds_played)
    print(f"Matched {matched}/{len(rows)} players · {len(standings)} VM teams · "
          f"runder spillet {rounds_played} · wrote {OUTPUT} ({size:,} bytes) · {stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
