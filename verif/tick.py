"""Mesure de la ponctualité des tâches programmées GitHub : note l'heure réelle de chaque réveil (30 au maximum)."""
import json, os, sys
from datetime import datetime, timezone
chemin = "verif/ticks.json"
t = json.load(open(chemin)) if os.path.exists(chemin) else []
if len(t) >= 30:
    sys.exit(0)
t.append(datetime.now(timezone.utc).isoformat(timespec="seconds"))
json.dump(t, open(chemin, "w"), indent=0)
