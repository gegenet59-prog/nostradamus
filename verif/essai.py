"""Essai en vrai du collecteur pendant la trêve : calendrier réel sur 12 jours (gratuit) + 1 seul relevé réel de Ligue 1
(1 crédit), dans un dossier provisoire. Vérifie que les vraies réponses sont bien lues. Résultat : verif/essai.json"""
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collecteur import base as B, config as C, tick as T
from collecteur.sources import Sources
from collecteur.calculs import calculer

B.RACINE = tempfile.mkdtemp()
maintenant = datetime.now(timezone.utc)
src, R = Sources(), {"fait_le": B.iso(maintenant), "calendrier": {}}
for comp in C.COMPETITIONS:
    ev = src.evenements(comp, maintenant, maintenant + timedelta(days=12))
    R["calendrier"][comp] = None if ev is None else {"matchs": len(ev), "creneaux": len({e["commence_time"] for e in ev})}
reponse = src.cotes("L1")
lus = []
for e in reponse or []:
    pin, maj = T.lire_cotes(e, C.BOOKMAKERS["pinnacle"]); win, _ = T.lire_cotes(e, C.BOOKMAKERS["winamax"])
    lus.append({"match": f'{e["home_team"]} - {e["away_team"]}', "coup_envoi": e["commence_time"], "pinnacle": pin, "winamax": win, "maj_pinnacle": maj})
R["releve_L1"] = {"matchs": len(lus), "pinnacle_lu": sum(1 for x in lus if x["pinnacle"]), "winamax_lu": sum(1 for x in lus if x["winamax"]), "detail": lus[:4]}
R["credits_restants"] = src.odds_reste
if lus and lus[0]["pinnacle"]:          # fiche de démonstration : le vrai relevé comme H-12, puis une variation inventée comme H-45
    p = lus[0]["pinnacle"]
    demo = calculer({"domicile": lus[0]["match"].split(" - ")[0], "exterieur": lus[0]["match"].split(" - ")[1],
                     "releves": {"H12": {"pinnacle": p}, "H45": {"pinnacle": {"1": round(p["1"] * 0.94, 2), "N": round(p["N"] * 1.01, 2), "2": round(p["2"] * 1.17, 2)}}}})
    R["demonstration_variation_inventee"] = {"feux": demo["feux"], "marche": demo["marche"]}
# un passage complet « à blanc » du vrai collecteur (planning réel ; aucun relevé n'est dû avant le 20 novembre)
bilan = T.passage(Sources(odds_reste=src.odds_reste), maintenant)
R["passage_a_blanc"] = {"journal": bilan["journal"], "etat": B.lire("etat.json")}
R["journal"] = src.journal
json.dump(R, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "essai.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
