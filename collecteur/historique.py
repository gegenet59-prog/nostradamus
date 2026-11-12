"""Import de l'historique gratuit Football-Data.co.uk (5 championnats) :

    python3 -m collecteur.historique

Pour chaque match : résultat, cote d'ouverture et cote de clôture. C'est une base « à grosse maille » (2 points
seulement, pas H-12 / H-3 / H-45) : ses statistiques doivent rester affichées à part de celles de la base propre.
Source des cotes, par ordre de préférence : Pinnacle (« pin », disponible de 2012-13 à mi-2025-26), sinon la
moyenne du marché (« moy »), sinon Bet365 (« b365 »). Les feux sont recalculés avec les seuils actuels à chaque import.
Écrit data/historique/<compétition>.json et verif/budget.json (simulation des crédits sur un vrai calendrier)."""
import csv, io, json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone
from . import config as C
from .base import ecrire
from .calculs import ISSUES, NIVEAUX, calculer, cotes_valides

ADRESSE = "https://www.football-data.co.uk/mmz4281/{saison}/{div}.csv"
SOURCES = (("pin", ("PSH", "PSD", "PSA"), ("PSCH", "PSCD", "PSCA")),
           ("moy", ("AvgH", "AvgD", "AvgA"), ("AvgCH", "AvgCD", "AvgCA")),
           ("b365", ("B365H", "B365D", "B365A"), ("B365CH", "B365CD", "B365CA")))
COLONNES = ["saison", "date", "heure", "domicile", "exterieur", "buts_domicile", "buts_exterieur", "issue", "source",
            "ouverture_1", "ouverture_N", "ouverture_2", "cloture_1", "cloture_N", "cloture_2",
            "feu_1", "feu_N", "feu_2", "pari"]


def saisons(premiere=2012):
    m = datetime.now(timezone.utc)
    derniere = m.year if m.month >= 7 else m.year - 1
    return [f"{a % 100:02d}{(a + 1) % 100:02d}" for a in range(premiere, derniere + 1)]


def telecharger(saison, div):
    try:
        with urllib.request.urlopen(ADRESSE.format(saison=saison, div=div), timeout=60) as r:
            brut = r.read()
    except Exception as e:
        print(f"  {saison} {div} : indisponible ({type(e).__name__})"); return []
    try: texte = brut.decode("utf-8-sig")
    except UnicodeDecodeError: texte = brut.decode("latin-1")
    return [l for l in csv.DictReader(io.StringIO(texte)) if (l.get("HomeTeam") or "").strip() and (l.get("FTR") or "").strip()]


def nombre(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def cotes(ligne, colonnes):
    c = dict(zip(ISSUES, (nombre(ligne.get(k)) for k in colonnes)))
    return c if cotes_valides(c) else None


def convertir(ligne, saison):
    jour = ligne["Date"].strip()
    date = datetime.strptime(jour, "%d/%m/%Y" if len(jour) == 10 else "%d/%m/%y").strftime("%Y-%m-%d")
    for source, ouv, clo in SOURCES:
        o, c = cotes(ligne, ouv), cotes(ligne, clo)
        if o and c: break
    else:
        return None
    m = calculer({"domicile": ligne["HomeTeam"].strip(), "exterieur": ligne["AwayTeam"].strip(),
                  "releves": {"H12": {"pinnacle": o}, "H45": {"pinnacle": c}}})
    feux = [NIVEAUX.index(m["feux"]["issues"][i]["feu"]) for i in ISSUES]
    return [saison, date, (ligne.get("Time") or "").strip() or None, m["domicile"], m["exterieur"],
            int(float(ligne["FTHG"])), int(float(ligne["FTAG"])), {"H": "1", "D": "N", "A": "2"}[ligne["FTR"].strip()], source,
            o["1"], o["N"], o["2"], c["1"], c["N"], c["2"], *feux, m["marche"]["pari"]]


def simuler_budget(par_comp):
    """Sur la dernière saison complète : crédits par mois pour les 5 championnats, selon la façon de faire le H-12.
    Un appel sert tous les relevés de la compétition dus au même moment (ou dans les AVANCE_TOLEREE minutes)."""
    saison = saisons()[-2]
    modes = {"h12_exact_par_match": {}, "h12_groupe_par_jour": {}}
    for comp, lignes in par_comp.items():
        kos = sorted({datetime.strptime(f"{l[1]} {l[2]}", "%Y-%m-%d %H:%M") for l in lignes if l[0] == saison and l[2]})
        par_jour = {}
        for k in kos: par_jour.setdefault(k.date(), []).append(k)
        avant = lambda nom: timedelta(minutes=C.RELEVES[nom]["avant"])
        suite = [k - avant(n) for k in kos for n in ("H3", "H45")]
        for mode, h12 in (("h12_exact_par_match", [k - avant("H12") for k in kos]),
                          ("h12_groupe_par_jour", [min(v) - avant("H12") for v in par_jour.values()])):
            dernier = None
            for t in sorted(suite + h12):
                if dernier and t - dernier <= timedelta(minutes=C.AVANCE_TOLEREE): continue
                dernier = t
                modes[mode].setdefault(t.strftime("%Y-%m"), {}).setdefault(comp, 0)
                modes[mode][t.strftime("%Y-%m")][comp] += 1
    return {"saison": saison, "explication": "crédits par mois pour les 5 championnats seuls ; les coupes d'Europe ajoutent environ 40 à 60 crédits les mois où elles se jouent",
            **{mode: {k: {**v, "total": sum(v.values())} for k, v in sorted(mois.items())} for mode, mois in modes.items()}}


def importer():
    par_comp, bilan = {}, {}
    for comp, infos in C.COMPETITIONS.items():
        if not infos["fd"]: continue
        lignes, sources = [], {}
        for saison in saisons():
            for l in telecharger(saison, infos["fd"]):
                try: x = convertir(l, saison)
                except (KeyError, ValueError): x = None
                if x:
                    lignes.append(x); sources[x[8]] = sources.get(x[8], 0) + 1
        if not lignes:
            print(f"{comp} : rien reçu, fichier précédent conservé"); continue
        lignes.sort(key=lambda x: (x[1], x[3]))
        par_comp[comp] = lignes
        bilan[comp] = {"matchs": len(lignes), "du": lignes[0][1], "au": lignes[-1][1], "sources": sources}
        chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "historique", f"{comp}.json")
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:      # une ligne par match : compact et lisible dans GitHub
            f.write('{"competition": %s, "origine": "football-data.co.uk", "colonnes": %s, "feux": %s,\n "matchs": [\n' % (
                json.dumps(comp), json.dumps(COLONNES), json.dumps(list(NIVEAUX))))
            f.write(",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in lignes))
            f.write("\n]}\n")
        print(f"{comp} : {bilan[comp]}")
    if par_comp:
        ecrire("historique/index.json", {"maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "competitions": bilan,
                                         "seuils": {"orange": C.SEUIL_ORANGE, "rouge": C.SEUIL_ROUGE, "violet": C.SEUIL_VIOLET}})
        racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(racine, "verif", "budget.json"), "w", encoding="utf-8") as f:
            json.dump(simuler_budget(par_comp), f, ensure_ascii=False, indent=1)
    return bilan


if __name__ == "__main__":
    sys.exit(0 if importer() else 1)
