"""Vérifications avant construction (cahier des charges, section « À vérifier »).
Lancé par GitHub Actions. N'écrit jamais les clés : ni dans les fichiers, ni dans les journaux."""
import csv, io, json, os, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta, timezone

ODDS = "https://api.the-odds-api.com/v4"
FOOT = "https://v3.football.api-sports.io"
SPORTS = {"L1": "soccer_france_ligue_one", "SA": "soccer_italy_serie_a", "LIGA": "soccer_spain_la_liga",
          "PL": "soccer_epl", "BL": "soccer_germany_bundesliga", "LDC": "soccer_uefa_champs_league",
          "EL": "soccer_uefa_europa_league", "ECL": "soccer_uefa_europa_conference_league"}
LIGUES = {"L1": 61, "SA": 135, "LIGA": 140, "PL": 39, "BL": 78, "LDC": 2, "EL": 3, "ECL": 848}
maintenant = datetime.now(timezone.utc)
R = {"fait_le": maintenant.isoformat(timespec="seconds")}


def appel(url, entetes=None):
    """Renvoie (code, json ou None, en-têtes). Ne lève jamais d'erreur contenant l'adresse (donc la clé)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=entetes or {}), timeout=40) as r:
            return r.status, json.loads(r.read().decode("utf-8")), dict(r.headers)
    except urllib.error.HTTPError as e:
        try: corps = json.loads(e.read().decode("utf-8"))
        except Exception: corps = None
        return e.code, corps, dict(e.headers)
    except Exception as e:
        return 0, {"erreur": type(e).__name__}, {}


def quota(h):
    h = {k.lower(): v for k, v in h.items()}
    return {k: h.get(k) for k in ("x-requests-remaining", "x-requests-used", "x-requests-last")}


# ---------- 1. The Odds API ----------
cle = os.environ.get("ODDS_API_KEY", "")
o = R["odds_api"] = {"cle_presente": bool(cle)}
code, sports, _ = appel(f"{ODDS}/sports/?all=true&apiKey={cle}")
o["sports_code"] = code
if code == 200:
    connus = {s["key"]: s for s in sports}
    o["sports"] = {c: {"existe": k in connus, "actif": connus.get(k, {}).get("active")} for c, k in SPORTS.items()}
o["competitions"] = {}
for c, k in SPORTS.items():
    d = o["competitions"][c] = {}
    code, ev, _ = appel(f"{ODDS}/sports/{k}/events?dateFormat=iso&apiKey={cle}")   # gratuit
    d["events_code"] = code
    if code == 200:
        d["nb_matchs_annonces"] = len(ev)
        d["prochains"] = [f'{e["commence_time"]} {e["home_team"]} - {e["away_team"]}' for e in sorted(ev, key=lambda e: e["commence_time"])[:12]]
        d["equipes"] = sorted({e["home_team"] for e in ev} | {e["away_team"] for e in ev})
    code, od, h = appel(f"{ODDS}/sports/{k}/odds?regions=eu&markets=h2h&oddsFormat=decimal&dateFormat=iso&apiKey={cle}")  # 1 crédit
    d["odds_code"], d["quota"] = code, quota(h)
    if code == 200:
        books = {}
        for e in od:
            for b in e.get("bookmakers", []):
                books[b["key"]] = books.get(b["key"], 0) + 1
        d["nb_matchs_avec_cotes"] = len(od)
        d["bookmakers_eu"] = books
        d["pinnacle"], d["winamax_fr"] = books.get("pinnacle", 0), books.get("winamax_fr", 0)
        for e in od:
            b = {x["key"]: x for x in e.get("bookmakers", [])}
            if "pinnacle" in b and "winamax_fr" in b:
                d["exemple"] = {"match": f'{e["home_team"]} - {e["away_team"]}', "coup_envoi": e["commence_time"],
                                "pinnacle": b["pinnacle"], "winamax_fr": b["winamax_fr"]}
                break
    else:
        d["odds_reponse"] = od

# ---------- 2. API-Football ----------
cle2 = os.environ.get("API_FOOTBALL_KEY", "")
f = R["api_football"] = {"cle_presente": bool(cle2), "tests": {}}
H = {"x-apisports-key": cle2}


def foot(nom, chemin, garder=None):
    code, j, h = appel(f"{FOOT}/{chemin}", H)
    h = {k.lower(): v for k, v in h.items()}
    t = f["tests"][nom] = {"chemin": chemin, "code": code, "reste_jour": h.get("x-ratelimit-requests-remaining"),
                           "erreurs": (j or {}).get("errors"), "nb": (j or {}).get("results")}
    if j and garder:
        try: t["extrait"] = garder(j.get("response"))
        except Exception as e: t["extrait"] = f"illisible ({type(e).__name__})"
    return (j or {}).get("response")


jour = lambda n: (maintenant + timedelta(days=n)).strftime("%Y-%m-%d")
nos = lambda rep: [f'{x["fixture"]["date"]} [{x["league"]["id"]}] {x["teams"]["home"]["name"]} - {x["teams"]["away"]["name"]} ({x["fixture"]["status"]["short"]})'
                   for x in rep if x["league"]["id"] in LIGUES.values()][:20]
foot("statut", "status", lambda r: {"formule": r["subscription"]["plan"], "fin": r["subscription"]["end"], "requetes": r["requests"]})
hier = foot("matchs_hier", f"fixtures?date={jour(-1)}", nos)
foot("matchs_aujourdhui", f"fixtures?date={jour(0)}", nos)
foot("matchs_demain", f"fixtures?date={jour(1)}", nos)
foot("matchs_dans_8_jours", f"fixtures?date={jour(8)}", nos)
foot("ligue1_saison_2026", "fixtures?league=61&season=2026&from=2026-11-20&to=2026-11-23", nos)
foot("ligue1_equipes_2026", "teams?league=61&season=2026", lambda r: sorted(x["team"]["name"] for x in r))
foot("ligue1_buteurs_2026", "players/topscorers?league=61&season=2026", lambda r: [x["player"]["name"] for x in r[:5]])
foot("ligue1_blesses_2026", "injuries?league=61&season=2026&date=" + jour(8), lambda r: len(r))
# compos + blessés d'un match terminé hier (n'importe quelle compétition), pour voir si la formule gratuite y a droit
fini = next((x for x in (hier or []) if x["fixture"]["status"]["short"] == "FT" and x["league"]["id"] in (5, 32, 10, 1, 34, 29, 30, 31, 33, 39, 61, 140, 135, 78, 2, 3, 848)), None) \
    or next((x for x in (hier or []) if x["fixture"]["status"]["short"] == "FT"), None)
if fini:
    i = fini["fixture"]["id"]
    f["match_test"] = f'{fini["league"]["name"]} : {fini["teams"]["home"]["name"]} - {fini["teams"]["away"]["name"]}'
    foot("compos_match_fini", f"fixtures/lineups?fixture={i}", lambda r: [{"equipe": x["team"]["name"], "titulaires": len(x["startXI"]), "exemple": x["startXI"][:2]} for x in r])
    foot("blesses_match_fini", f"injuries?fixture={i}", lambda r: r[:3])

# ---------- 3. Football-Data.co.uk ----------
fd = R["football_data"] = {}
for saison in ("2627", "2526", "1213"):
    for div in ("F1", "I1"):
        try:
            with urllib.request.urlopen(f"https://www.football-data.co.uk/mmz4281/{saison}/{div}.csv", timeout=40) as r:
                lignes = list(csv.DictReader(io.StringIO(r.read().decode("latin-1"))))
            lignes = [l for l in lignes if l.get("HomeTeam")]
            plein = lambda col: sum(1 for l in lignes if (l.get(col) or "").strip())
            fd[f"{saison}/{div}"] = {"matchs": len(lignes), "avec_heure": plein("Time"), "pinnacle_ouverture": plein("PSH"),
                                     "pinnacle_cloture": plein("PSCH"), "dernier": lignes[-1].get("Date") if lignes else None,
                                     "colonnes": [c for c in (lignes[0].keys() if lignes else []) if c and c.startswith(("PS", "P", "Max", "Avg"))][:30]}
        except Exception as e:
            fd[f"{saison}/{div}"] = {"erreur": type(e).__name__}

json.dump(R, open("verif/resultats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Vérifications terminées.")
