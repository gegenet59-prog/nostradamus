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


def saison_de(coup_envoi):
    a, m = int(coup_envoi[:4]), int(coup_envoi[5:7])
    d = a if m >= 7 else a - 1
    return f"{d}-{str(d + 1)[2:]}"


def base():
    """Bloc MA BASE : mes propres relevés. Départ = H-12 (cote Pinnacle), arrivée = H-45. Seuls comptent les matchs
    terminés, avec les 3 relevés complets : ni provisoires, ni « partielles » (sans H-12), qui fausseraient les stats."""
    cellules, comps, saisons, nb = {}, set(), set(), 0
    matchs = []
    for chemin in sorted(os.listdir(os.path.join(RACINE, "matchs"))):
        if chemin.endswith(".json"):
            matchs += (lire(f"matchs/{chemin}") or {}).get("matchs", [])
    for m in matchs:
        f, sc = m.get("feux"), m.get("score")
        if not f or not sc or f.get("provisoire") or f.get("partielle") or not sc.get("issue"):
            continue
        r = m["releves"]
        dep, arr = r["H12"]["pinnacle"], r["H45"]["pinnacle"]
        p0, p1 = sans_marge([dep[i] for i in ISSUES]), sans_marge([arr[i] for i in ISSUES])
        pari = PARIS.index((m.get("marche") or {}).get("pari") or "aucun")
        comps.add(m["competition"]); saisons.add(saison_de(m["coup_envoi"])); nb += 1
        for k, issue in enumerate(ISSUES):
            fi = f["issues"][issue]
            sens = SENS.index(fi["fleche"])
            cle = (m["competition"], saison_de(m["coup_envoi"]), k, NIVEAUX.index(fi["feu"]), sens,
                   tranche(dep[issue]), pari)
            c = cellules.setdefault(cle, [0, 0, 0.0, 0.0])
            c[0] += 1
            c[1] += 1 if sc["issue"] == issue else 0
            c[2] += p0[k]
            c[3] += p1[k]
    comps, saisons = sorted(comps), sorted(saisons)
    lignes = [[comps.index(cp), saisons.index(sa), k, fe, sn, tr, pa, c[0], c[1], round(c[2], 3), round(c[3], 3)]
              for (cp, sa, k, fe, sn, tr, pa), c in sorted(cellules.items())]
    return {"maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "origine": "mes relevés Nostradamus",
            "matchs": nb,
            "explication": "un cas = une issue d'un match ; départ = cote H-12, arrivée = cote H-45 (Pinnacle)",
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
    if "base" in sys.argv[1:]:
        b = base()
        ecrire_compact("stats/base.json", b)
        print(f"stats/base.json : {b['matchs']} matchs, {sum(l[7] for l in b['lignes'])} cas")
        sys.exit(0)
    h = historique()
    if not h["lignes"]:
        print("Aucun historique : rien écrit"); sys.exit(1)
    ecrire_compact("stats/historique.json", h)
    print(f"stats/historique.json : {len(h['lignes'])} lignes, {sum(l[7] for l in h['lignes'])} cas")
