"""Vérification complémentaire API-Football (formule gratuite) : forme exacte des compos, appels groupés."""
import json, os, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
FOOT = "https://v3.football.api-sports.io"
H = {"x-apisports-key": os.environ.get("API_FOOTBALL_KEY", "")}
R = {"fait_le": datetime.now(timezone.utc).isoformat(timespec="seconds")}

def foot(chemin):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{FOOT}/{chemin}", headers=H), timeout=40) as r:
            return json.loads(r.read().decode("utf-8")), {k.lower(): v for k, v in r.headers.items()}
    except Exception as e:
        return {"errors": type(e).__name__, "response": []}, {}

hier = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
j, h = foot(f"fixtures?date={hier}")
finis = [x for x in j["response"] if x["fixture"]["status"]["short"] == "FT"]
ligues = {}
for x in finis:
    cle = f'{x["league"]["id"]} {x["league"]["name"]} ({x["league"]["country"]})'
    ligues[cle] = ligues.get(cle, 0) + 1
R["ligues_hier"] = dict(sorted(ligues.items(), key=lambda kv: -kv[1])[:40])
R["forme_match"] = finis[0] if finis else None
prefere = [x for x in finis if x["league"]["id"] in (32, 5, 6, 34, 29, 30, 31, 33, 960, 4, 1)] or finis
ids = [str(x["fixture"]["id"]) for x in prefere[:3]]
R["ids_testes"] = [f'{x["league"]["name"]} : {x["teams"]["home"]["name"]} - {x["teams"]["away"]["name"]}' for x in prefere[:3]]
j, h = foot("fixtures?ids=" + "-".join(ids))
R["groupe"] = {"erreurs": j.get("errors"), "nb": j.get("results"), "reste_jour": h.get("x-ratelimit-requests-remaining"),
               "cles": sorted(j["response"][0].keys()) if j.get("response") else None,
               "compos": [[{"equipe": l["team"], "formation": l.get("formation"), "titulaires": l.get("startXI", [])[:3], "nb": len(l.get("startXI") or [])}
                           for l in x.get("lineups", [])] for x in j.get("response", [])],
               "joueurs_extrait": (j["response"][0].get("players") or [{}])[0].get("players", [])[:2] if j.get("response") else None,
               "buts_extrait": [e for x in j.get("response", []) for e in (x.get("events") or []) if e.get("type") == "Goal"][:3]}
j, h = foot("fixtures/lineups?fixture=" + ids[0])
R["compos_seul"] = {"erreurs": j.get("errors"), "nb": j.get("results"), "brut": json.dumps(j.get("response"))[:1500]}
j, h = foot("injuries?ids=" + "-".join(ids))
R["blesses_groupe"] = {"erreurs": j.get("errors"), "nb": j.get("results"), "extrait": j.get("response", [])[:3], "reste_jour": h.get("x-ratelimit-requests-remaining"),
                       "limite_minute": h.get("x-ratelimit-remaining")}
json.dump(R, open("verif/resultats2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
