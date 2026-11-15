"""Statistiques de l'écran Stats, calculées à l'avance pour que la page reste légère sur téléphone.

    python3 -m collecteur.stats

Bloc HISTORIQUE -> data/stats/historique.json : une ligne par combinaison (compétition, saison, issue, feu, sens,
tranche de cote de départ, pari du marché) avec le nombre de cas, le nombre d'issues sorties et la somme des
probabilités « promises » par la cote (marge du bookmaker retirée), au départ puis à l'arrivée. La page additionne
les lignes qui correspondent aux filtres choisis : un « cas » = une issue (1, N ou 2) d'un match.
Dans l'historique, départ = cote d'ouverture et arrivée = cote de clôture (grosse maille)."""
import json, os, sys
from datetime import datetime, timezone
from . import config as C
from .base import RACINE, lire
from .calculs import ISSUES, NIVEAUX

SENS = ["baisse", "hausse", "stable"]
TRANCHES = ["moins de 1,50", "de 1,50 à 2,50", "plus de 2,50"]
PARIS = ["aucun", "1", "N", "2", "1N", "N2", "12"]
COLONNES = ["comp", "saison", "issue", "feu", "sens", "tranche", "pari", "cas", "sorties", "p_depart", "p_arrivee"]


def tranche(cote):
    return 0 if cote < 1.5 else 1 if cote < 2.5 else 2


def sans_marge(cotes):
    inv = [1.0 / c for c in cotes]
    t = sum(inv)
    return [x / t for x in inv]


def historique():
    comps = [c for c, i in C.COMPETITIONS.items() if i["fd"] and lire(f"historique/{c}.json")]
    cellules, saisons = {}, set()
    for ci, comp in enumerate(comps):
        d = lire(f"historique/{comp}.json")
        col = {n: k for k, n in enumerate(d["colonnes"])}
        for m in d["matchs"]:
            saisons.add(m[col["saison"]])
            ouv = [m[col["ouverture_" + i]] for i in ISSUES]
            clo = [m[col["cloture_" + i]] for i in ISSUES]
            p0, p1 = sans_marge(ouv), sans_marge(clo)
            pari = PARIS.index(m[col["pari"]] or "aucun")
            for k, issue in enumerate(ISSUES):
                sens = 1 if clo[k] > ouv[k] else 0 if clo[k] < ouv[k] else 2
                cle = (ci, m[col["saison"]], k, m[col["feu_" + issue]], sens, tranche(ouv[k]), pari)
                c = cellules.setdefault(cle, [0, 0, 0.0, 0.0])
                c[0] += 1
                c[1] += 1 if m[col["issue"]] == issue else 0
                c[2] += p0[k]
                c[3] += p1[k]
    saisons = sorted(saisons)
    lignes = [[ci, saisons.index(s), k, f, sn, tr, pa, c[0], c[1], round(c[2], 3), round(c[3], 3)]
              for (ci, s, k, f, sn, tr, pa), c in sorted(cellules.items())]
    return {"maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "origine": "football-data.co.uk",
            "explication": "un cas = une issue d'un match ; départ = cote d'ouverture, arrivée = cote de clôture",
            "dimensions": {"comp": comps, "saison": saisons, "issue": list(ISSUES), "feu": list(NIVEAUX), "sens": SENS,
                           "tranche": TRANCHES, "pari": PARIS},
            "colonnes": COLONNES, "lignes": lignes}


def ecrire_compact(chemin, contenu):
    complet = os.path.join(RACINE, chemin)
    os.makedirs(os.path.dirname(complet), exist_ok=True)
    lignes = contenu.pop("lignes")
    with open(complet, "w", encoding="utf-8") as f:
        f.write(json.dumps(contenu, ensure_ascii=False)[:-1] + ',\n"lignes": [\n')
        f.write(",\n".join(json.dumps(x, separators=(",", ":")) for x in lignes))
        f.write("\n]}\n")
    contenu["lignes"] = lignes


if __name__ == "__main__":
    h = historique()
    if not h["lignes"]:
        print("Aucun historique : rien écrit"); sys.exit(1)
    ecrire_compact("stats/historique.json", h)
    print(f"stats/historique.json : {len(h['lignes'])} lignes, {sum(l[7] for l in h['lignes'])} cas")
