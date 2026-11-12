"""Vérification API-Football : les blessés de toute une journée en un seul appel (formule gratuite) ?"""
import json, os, urllib.request
from datetime import datetime, timezone
H = {"x-apisports-key": os.environ.get("API_FOOTBALL_KEY", "")}
R = {"fait_le": datetime.now(timezone.utc).isoformat(timespec="seconds")}
for nom, chemin in (("blesses_du_jour", "injuries?date=" + datetime.now(timezone.utc).strftime("%Y-%m-%d")),):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://v3.football.api-sports.io/" + chemin, headers=H), timeout=40) as r:
            j = json.loads(r.read().decode("utf-8"))
        ligues = {}
        for x in j.get("response", []):
            k = f'{x["league"]["id"]} {x["league"]["name"]}'; ligues[k] = ligues.get(k, 0) + 1
        R[nom] = {"erreurs": j.get("errors"), "nb": j.get("results"), "ligues": ligues, "extrait": j.get("response", [])[:2]}
    except Exception as e:
        R[nom] = {"erreur": type(e).__name__}
json.dump(R, open("verif/resultats3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
