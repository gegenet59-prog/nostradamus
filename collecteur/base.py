"""La base de données : des fichiers JSON dans le dossier data/ du dépôt (lus tels quels par la page web).

data/matchs/AAAA-MM-JJ.json  un fichier par jour (date du coup d'envoi, heure de Paris) avec tous les matchs du jour
data/index.json              la liste des jours présents dans la base
data/etat.json               état du collecteur : quotas restants, dernier passage, alertes
data/equipes.json            les dernières compos connues de chaque équipe (pour savoir qui est titulaire régulier)
data/historique/*.json       l'historique Football-Data (voir collecteur/historique.py)"""
import json, os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
RACINE = os.environ.get("NOSTRADAMUS_DATA", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))


def instant(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jour_paris(dt):
    return dt.astimezone(PARIS).strftime("%Y-%m-%d")


def lire(chemin, defaut=None):
    try:
        with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return defaut


def ecrire(chemin, contenu):
    complet = os.path.join(RACINE, chemin)
    os.makedirs(os.path.dirname(complet), exist_ok=True)
    with open(complet, "w", encoding="utf-8") as f:
        json.dump(contenu, f, ensure_ascii=False, indent=1)
        f.write("\n")


class Base:
    """Charge les jours demandés, retient ceux qui ont changé et ne réécrit que ceux-là."""

    def __init__(self):
        self.jours, self.modifies = {}, set()
        self.etat = lire("etat.json", {"odds": {}, "foot": {}, "jours_foot": {}, "alertes": []})
        self.equipes = lire("equipes.json", {})
        self.etat_modifie = self.equipes_modifiees = False

    def jour(self, date):
        if date not in self.jours:
            self.jours[date] = lire(f"matchs/{date}.json", {"date": date, "matchs": []})
        return self.jours[date]

    def matchs(self, dates):
        return [m for d in dates for m in self.jour(d)["matchs"]]

    def toucher(self, match):
        self.modifies.add(jour_paris(instant(match["coup_envoi"])))

    def alerte(self, maintenant, texte):
        self.etat["alertes"] = ([{"quand": iso(maintenant), "texte": texte}] + self.etat.get("alertes", []))[:30]
        self.etat_modifie = True

    def enregistrer(self, maintenant):
        """Écrit ce qui a changé. Renvoie True si quelque chose a été écrit."""
        if not (self.modifies or self.etat_modifie or self.equipes_modifiees):
            return False
        for d in sorted(self.modifies):
            j = self.jours[d]
            j["matchs"].sort(key=lambda m: (m["coup_envoi"], m["competition"], m["domicile"]))
            j["maj"] = iso(maintenant)
            ecrire(f"matchs/{d}.json", j)
        if self.modifies:
            index = lire("index.json", {"jours": {}})
            for d in self.modifies:
                if self.jours[d]["matchs"]: index["jours"][d] = len(self.jours[d]["matchs"])
                else: index["jours"].pop(d, None)
            index["jours"] = dict(sorted(index["jours"].items()))
            index["maj"] = iso(maintenant)
            ecrire("index.json", index)
        if self.equipes_modifiees:
            ecrire("equipes.json", self.equipes)
        self.etat["dernier_passage_utile"] = iso(maintenant)
        ecrire("etat.json", self.etat)
        return True
