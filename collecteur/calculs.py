"""Calculs de Nostradamus : feux, flèches, % et phrase « Le marché annonce ».
Aucun appel réseau ici : uniquement des fonctions testables (tests/test_calculs.py).

Vocabulaire : une « cote » est un dictionnaire {"1": 2.05, "N": 3.62, "2": 3.66}."""
import math
from . import config as C

ISSUES = ("1", "N", "2")
NIVEAUX = ("vert", "orange", "rouge", "violet")


def probabilites(cotes):
    """Cotes -> probabilités sans la marge du bookmaker (somme = 1), et la marge en points."""
    inverses = {i: 1.0 / cotes[i] for i in ISSUES}
    total = sum(inverses.values())
    return {i: inverses[i] / total for i in ISSUES}, (total - 1.0) * 100


def variation_classique(avant, apres):
    """Le % affiché à l'écran : +5.0 = la cote a monté de 5 %."""
    return (apres / avant - 1.0) * 100


def ampleur(p_avant, p_apres):
    """Le « calcul en coulisse » : ampleur d'un mouvement, comparable entre petites et grosses cotes.

    On mesure le déplacement de la probabilité sur une échelle « logit » (celle où 1,30 -> 1,25 pèse autant
    que 6,00 -> 7,00), puis on le ramène à un pourcentage qui vaut exactement le % classique pour une cote
    de 2,00. Résultat : pour une petite cote l'ampleur est plus forte que le % affiché, pour une grosse
    cote elle est un peu plus faible. Le feu retenu est le plus sévère des deux lectures (voir calculer) :
    le tableau du cahier des charges reste donc toujours vrai avec le % affiché, et les petites cotes
    ne passent plus sous le radar."""
    logit = lambda p: math.log(p / (1.0 - p))
    echelle = 1.0 - 1.0 / C.COTE_REFERENCE
    return (math.exp(abs(logit(p_apres) - logit(p_avant)) * echelle) - 1.0) * 100


def niveau_selon_ampleur(a):
    return 3 if a > C.SEUIL_VIOLET else 2 if a >= C.SEUIL_ROUGE else 1 if a >= C.SEUIL_ORANGE else 0


def cotes_valides(c):
    return bool(c) and all(isinstance(c.get(i), (int, float)) and c[i] > 1.0 for i in ISSUES)


def phrase_marche(pari, domicile, exterieur):
    textes = {"1": f"{domicile} gagne (1)", "2": f"{exterieur} gagne (2)", "N": "match nul (N)",
              "1N": f"{exterieur} ne gagne pas (1N)", "N2": f"{domicile} ne gagne pas (N2)",
              "12": "pas de match nul (12)", None: "pas de mouvement net"}
    return "Le marché annonce : " + textes[pari]


def lecture_marche(depart, arrivee, domicile, exterieur):
    """D'où part la probabilité, où elle arrive -> le pari que le marché soutient (1, N, 2, 1N, N2, 12 ou rien).

    Règle : les issues « quittées » sont celles qui perdent plus de SEUIL_PERTE point ; le pari soutenu est
    l'ensemble des autres. Si rien ne bouge d'au moins SEUIL_MOUVEMENT point : pas de mouvement net."""
    p0, m0 = probabilites(depart)
    p1, m1 = probabilites(arrivee)
    d = {i: (p1[i] - p0[i]) * 100 for i in ISSUES}
    pari = None
    if max(abs(x) for x in d.values()) >= C.SEUIL_MOUVEMENT:
        gardees = [i for i in ISSUES if d[i] >= -C.SEUIL_PERTE]
        if 1 <= len(gardees) <= 2:
            pari = "".join(gardees)
    # incohérent : les 3 cotes bougent dans le même sens, ou la marge du bookmaker a nettement changé
    sens = [variation_classique(depart[i], arrivee[i]) for i in ISSUES]
    incoherent = all(s > 0.5 for s in sens) or all(s < -0.5 for s in sens) or abs(m1 - m0) > C.SEUIL_MARGE
    return {"pari": pari, "phrase": phrase_marche(pari, domicile, exterieur), "incoherent": incoherent,
            "deplacement": {i: round(d[i], 2) for i in ISSUES}, "marge": [round(m0, 2), round(m1, 2)]}


def calculer(match):
    """Calcule feux, flèches, % et lecture du marché d'un match à partir de ses relevés. Modifie et renvoie le match.

    Sans relevé H-12 (ou sans aucun relevé plus récent), rien n'est calculé : feux = None.
    Tant que H-45 n'est pas fait, le calcul se fait sur le dernier relevé disponible, marqué « provisoire »."""
    r = match.get("releves", {})
    pin = lambda nom: (r.get(nom) or {}).get("pinnacle")
    win = lambda nom: (r.get(nom) or {}).get("winamax")
    dernier = "H45" if cotes_valides(pin("H45")) else "H3" if cotes_valides(pin("H3")) else None
    if not cotes_valides(pin("H12")) or not dernier:
        match["feux"], match["marche"] = None, None
        return match
    depart, arrivee = pin("H12"), pin(dernier)
    # Probabilité d'une issue, marge retirée. On retire aux deux relevés la marge constatée à H-12 : ainsi une cote
    # qui n'a pas bougé a une ampleur de 0, même si le bookmaker a changé sa marge entre-temps.
    total = sum(1.0 / depart[i] for i in ISSUES)
    proba = lambda cotes, i: min(1.0 / cotes[i] / total, 0.995)
    absents = match.get("absents") or {}
    feux = {}
    for i in ISSUES:
        pct = variation_classique(depart[i], arrivee[i])
        a = ampleur(proba(depart, i), proba(arrivee, i))
        # le feu suit le tableau avec le % affiché ; le calcul en coulisse ne peut que le monter (petites cotes)
        niveau, raisons = niveau_selon_ampleur(abs(pct)), []
        if niveau_selon_ampleur(a) > niveau:
            niveau = niveau_selon_ampleur(a); raisons.append("petite cote : mouvement plus fort qu'il n'y paraît")
        # Pinnacle et Winamax bougent en sens opposé -> au moins Orange
        if cotes_valides(win("H12")) and cotes_valides(win(dernier)):
            pw = variation_classique(win("H12")[i], win(dernier)[i])
            if pct * pw < 0 and min(abs(pct), abs(pw)) >= C.SEUIL_DESACCORD:
                niveau = max(niveau, 1); raisons.append("Pinnacle et Winamax en sens opposé")
        # plus de 4 % rien qu'entre H-3 et H-45 -> au moins Rouge
        if dernier == "H45" and cotes_valides(pin("H3")):
            derniere_heure = max(abs(variation_classique(pin("H3")[i], arrivee[i])), ampleur(proba(pin("H3"), i), proba(arrivee, i)))
            if derniere_heure > C.SEUIL_H3_H45:
                niveau = max(niveau, 2); raisons.append("plus de 4 % entre H-3 et H-45")
        # absences : elles touchent l'issue « victoire » de l'équipe concernée (1 = domicile, 2 = extérieur)
        cote = {"1": "domicile", "2": "exterieur"}.get(i)
        if cote:
            liste = absents.get(cote) or []
            if any(j.get("cle") for j in liste):
                niveau = max(niveau, 2); raisons.append("joueur clé absent")
            elif any(j.get("titulaire") for j in liste):
                niveau = max(niveau, 1); raisons.append("titulaire régulier absent")
        feux[i] = {"feu": NIVEAUX[niveau], "fleche": "hausse" if pct > 0 else "baisse" if pct < 0 else "stable",
                   "pct": round(pct, 1), "ampleur": round(a, 1), "raisons": raisons}
    match["feux"] = {"issues": feux, "base": f"H12-{dernier}", "provisoire": dernier != "H45"}
    match["marche"] = lecture_marche(depart, arrivee, match["domicile"], match["exterieur"])
    return match
