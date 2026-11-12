"""Le collecteur. Lancé toutes les 5 minutes par GitHub Actions (.github/workflows/collecteur.yml) :

    python3 -m collecteur.tick

À chaque passage il regarde ce qui est dû et ne fait QUE ça (la plupart des passages ne font rien) :
  1. planning    : toutes les 6 h, calendrier des 8 compétitions (gratuit) -> crée les matchs et l'heure de leurs 3 relevés
  2. relevés     : cotes Pinnacle + Winamax à H-12, H-3, H-45 (1 crédit par compétition et par créneau), avec garde-fou
  3. API-Football: lien des matchs, blessés/suspendus, compos officielles, scores finaux (garde-fou 100 requêtes/jour)
  4. calculs     : feux, flèches, %, phrase du marché pour chaque match touché
Il peut être relancé sans risque : un relevé déjà fait n'est jamais refait."""
import calendar, sys
from datetime import datetime, timedelta, timezone
from . import config as C
from .base import Base, instant, iso, jour_paris
from .calculs import ISSUES, calculer, cotes_valides
from .rapprochement import rapprocher, ressemblance

TERMINE = ("FT", "AET", "PEN")


# ------------------------------------------------------------------ 1. planning
def planifier(base, src, maintenant):
    """Calendrier des 60 prochaines heures (gratuit). Crée les nouveaux matchs, suit les changements d'horaire."""
    debut, fin = maintenant - timedelta(hours=3), maintenant + timedelta(hours=60)
    dates = [jour_paris(maintenant + timedelta(days=n)) for n in range(-1, 4)]
    connus = {m["id"]: m for m in base.matchs(dates)}
    for comp in C.COMPETITIONS:
        evenements = src.evenements(comp, debut, fin)
        if evenements is None:
            base.alerte(maintenant, f"Calendrier {comp} indisponible"); continue
        vus = set()
        for e in evenements:
            vus.add(e["id"])
            m = connus.get(e["id"])
            if m and m["coup_envoi"] == e["commence_time"]:
                continue
            if m:      # horaire modifié : on déplace le match et on reprogramme les relevés pas encore faits
                base.jour(jour_paris(instant(m["coup_envoi"])))["matchs"].remove(m); base.toucher(m)
                m["coup_envoi"] = e["commence_time"]
            else:
                m = {"id": e["id"], "competition": comp, "coup_envoi": e["commence_time"],
                     "domicile": e["home_team"], "exterieur": e["away_team"], "foot": None, "releves": {},
                     "compos": None, "compos_essais": [], "absents": None, "feux": None, "marche": None, "score": None}
                connus[m["id"]] = m
            ko = instant(m["coup_envoi"])
            for nom, r in C.RELEVES.items():
                if m["releves"].get(nom, {}).get("etat") not in ("fait",):
                    m["releves"][nom] = {"prevu": iso(ko - timedelta(minutes=r["avant"])), "etat": "attente"}
            base.jour(jour_paris(ko))["matchs"].append(m); base.toucher(m)
        # match annoncé puis disparu du calendrier (reporté) : on l'enlève s'il n'a encore aucun relevé
        for m in list(connus.values()):
            if m["competition"] == comp and m["id"] not in vus and debut < instant(m["coup_envoi"]) < fin \
                    and instant(m["coup_envoi"]) > maintenant and not any(r.get("etat") == "fait" for r in m["releves"].values()):
                base.jour(jour_paris(instant(m["coup_envoi"])))["matchs"].remove(m); base.toucher(m); del connus[m["id"]]
                base.alerte(maintenant, f"Match retiré du calendrier : {m['domicile']} - {m['exterieur']}")
    if C.H12_GROUPE:      # un seul H-12 par compétition et par jour : 12 h avant le premier match du jour
        groupes = {}
        for m in connus.values():
            groupes.setdefault((m["competition"], jour_paris(instant(m["coup_envoi"]))), []).append(m)
        for groupe in groupes.values():
            prevu = iso(min(instant(m["coup_envoi"]) for m in groupe) - timedelta(minutes=C.RELEVES["H12"]["avant"]))
            for m in groupe:
                r = m["releves"].get("H12")
                if r and r["etat"] == "attente" and r["prevu"] != prevu:
                    r["prevu"] = prevu; base.toucher(m)
    base.etat["planning_fait_a"] = iso(maintenant); base.etat_modifie = True


# ------------------------------------------------------------------ 2. relevés de cotes
def mode_quota(reste, maintenant):
    """Garde-fou The Odds API. Renvoie "complet", "sans_H3" (on sacrifie les H-3) ou "arret" (20 crédits ou moins)."""
    if reste is None: return "complet"
    if reste <= C.ARRET_TOTAL: return "arret"
    jours_du_mois = calendar.monthrange(maintenant.year, maintenant.month)[1]
    fin_du_mois = datetime(maintenant.year, maintenant.month, jours_du_mois, tzinfo=timezone.utc) + timedelta(days=1)
    jours_restants = max((fin_du_mois - maintenant).total_seconds() / 86400, 1.0)
    return "complet" if (reste - C.ARRET_TOTAL) / jours_restants >= C.RYTHME_COMPLET else "sans_H3"


def lire_cotes(evenement, cle_bookmaker):
    """Extrait {"1":…, "N":…, "2":…} d'un bookmaker dans la réponse de The Odds API, et l'heure de sa dernière mise à jour."""
    for b in evenement.get("bookmakers", []):
        if b["key"] != cle_bookmaker: continue
        for marche in b.get("markets", []):
            if marche["key"] != "h2h": continue
            prix = {o["name"]: o["price"] for o in marche["outcomes"]}
            cotes = {"1": prix.get(evenement["home_team"]), "N": prix.get("Draw"), "2": prix.get(evenement["away_team"])}
            if cotes_valides(cotes): return cotes, marche.get("last_update") or b.get("last_update")
    return None, None


def relever(base, src, matchs, maintenant):
    """Fait les relevés dus. Un seul appel par compétition sert tous ses matchs dus au même moment."""
    touches, dus = [], {}
    for m in matchs:
        ko = instant(m["coup_envoi"])
        for nom, regle in C.RELEVES.items():
            r = m["releves"].get(nom)
            if not r or r["etat"] not in ("attente", "vide"): continue
            if maintenant > ko - timedelta(minutes=regle["limite"]):          # trop tard : relevé manqué
                r["etat"] = "manque" if r["etat"] == "attente" else "vide_definitif"; base.toucher(m); touches.append(m); continue
            if maintenant >= instant(r["prevu"]) and r["etat"] == "attente":
                dus.setdefault(m["competition"], []).append((m, nom))
    if not dus: return touches
    mode = mode_quota(src.odds_reste, maintenant)
    if base.etat["odds"].get("mode") != mode:
        base.etat["odds"]["mode"] = mode; base.etat_modifie = True
        if mode != "complet": base.alerte(maintenant, {"sans_H3": "Crédits en baisse : les relevés H-3 sont sacrifiés", "arret": "Arrêt total : 20 crédits ou moins"}[mode])
    for comp, liste in dus.items():
        if mode == "sans_H3":
            for m, nom in liste:
                if nom == "H3": m["releves"]["H3"]["etat"] = "sacrifie"; base.toucher(m); touches.append(m)
            liste = [(m, nom) for m, nom in liste if nom != "H3"]
        # un H-12 seul ne sert à rien : on ne le prend que s'il reste de quoi faire aussi le H-45
        if src.odds_reste is not None and src.odds_reste - C.ARRET_TOTAL < 2:
            liste = [(m, nom) for m, nom in liste if nom != "H12"]
        if not liste or mode == "arret" or (src.odds_reste is not None and src.odds_reste <= C.ARRET_TOTAL):
            continue
        reponse = src.cotes(comp)
        base.etat["odds"].update({"reste": src.odds_reste, "maj": iso(maintenant)}); base.etat_modifie = True
        if reponse is None:
            base.alerte(maintenant, f"Cotes {comp} indisponibles"); continue
        par_id = {e["id"]: e for e in reponse}
        # tous les matchs de la compétition dont un relevé est dû (ou le sera dans quelques minutes) profitent de l'appel
        for m in matchs:
            if m["competition"] != comp: continue
            for nom in C.RELEVES:
                r = m["releves"].get(nom)
                if not r or r["etat"] not in ("attente", "vide") or (r["etat"] == "attente" and mode == "sans_H3" and nom == "H3"): continue
                if maintenant < instant(r["prevu"]) - timedelta(minutes=C.AVANCE_TOLEREE): continue
                e = par_id.get(m["id"])
                pin, maj = lire_cotes(e, C.BOOKMAKERS["pinnacle"]) if e else (None, None)
                win, _ = lire_cotes(e, C.BOOKMAKERS["winamax"]) if e else (None, None)
                r.update({"etat": "fait" if pin else "vide", "fait_a": iso(maintenant),
                          "retard_min": round((maintenant - instant(r["prevu"])).total_seconds() / 60),
                          "pinnacle": pin, "winamax": win, "maj_pinnacle": maj})
                base.toucher(m); touches.append(m)
    return touches


# ------------------------------------------------------------------ 3. API-Football
def foot_permis(src, reserve=0):
    return src.foot_reste is None or src.foot_reste > C.FOOT_RESERVE + reserve


def score_depuis(f):
    """Score de la fin du temps réglementaire (c'est lui qui compte pour le 1N2), ou None si le match n'est pas fini."""
    if f["fixture"]["status"]["short"] not in TERMINE: return None
    plein = (f.get("score") or {}).get("fulltime") or {}
    d, e = (plein.get("home"), plein.get("away")) if plein.get("home") is not None else (f["goals"]["home"], f["goals"]["away"])
    if d is None or e is None: return None
    return {"domicile": d, "exterieur": e, "issue": "1" if d > e else "2" if e > d else "N", "statut": f["fixture"]["status"]["short"]}


def titulaires_reguliers(base, equipe_id):
    """D'après nos propres compos enregistrées : {id joueur: "gardien" ou True} des titulaires réguliers de l'équipe."""
    passes = (base.equipes.get(str(equipe_id)) or {}).get("matchs", [])[-C.TITULAIRE_MATCHS:]
    if len(passes) < C.TITULAIRE_MINI: return {}
    compte, gardien = {}, {}
    for p in passes:
        for j in p["onze"]: compte[j] = compte.get(j, 0) + 1
        if p.get("gardien"): gardien[p["gardien"]] = gardien.get(p["gardien"], 0) + 1
    seuil = C.TITULAIRE_PART * len(passes)
    return {j: ("gardien" if gardien.get(j, 0) >= seuil else True) for j, n in compte.items() if n >= seuil}


def marquer_absents(base, m):
    """Complète la liste des absents : qui est titulaire régulier, qui est joueur clé ; ajoute les titulaires réguliers
    laissés hors du onze de départ quand la compo officielle est connue."""
    if not m.get("foot"): return
    absents = m.get("absents") or {"domicile": [], "exterieur": []}
    for cote in ("domicile", "exterieur"):
        reguliers = titulaires_reguliers(base, m["foot"][cote])
        liste = [a for a in absents.get(cote, []) if a.get("source") != "compo"]
        for a in liste:
            a["titulaire"] = a["id"] in reguliers
            a["cle"] = "gardien" if reguliers.get(a["id"]) == "gardien" else None
        compo = (m.get("compos") or {}).get(cote)
        if compo and compo["titulaires"]:
            onze, deja = {j["id"] for j in compo["titulaires"]}, {a["id"] for a in liste}
            noms = (base.equipes.get(str(m["foot"][cote])) or {}).get("joueurs", {})
            banc = {j["id"] for j in compo.get("remplacants", [])}
            for j, role in reguliers.items():
                if j not in onze and j not in deja:
                    liste.append({"id": j, "nom": noms.get(str(j), "?"), "motif": "sur le banc" if j in banc else "hors du groupe",
                                  "source": "compo", "titulaire": True, "cle": "gardien" if role == "gardien" else None})
        absents[cote] = liste
    m["absents"] = absents


def suivre_foot(base, src, matchs, maintenant):
    """Lien avec API-Football, absents, compos, scores. Chaque étape vérifie le garde-fou des 100 requêtes par jour."""
    touches = []
    jours = base.etat.setdefault("jours_foot", {})
    aujourd_hui = maintenant.strftime("%Y-%m-%d")
    if base.etat["foot"].get("jour") != aujourd_hui:          # le compteur repart à minuit UTC
        base.etat["foot"] = {"jour": aujourd_hui, "reste": None}; src.foot_reste = None; base.etat_modifie = True
    futurs = [m for m in matchs if instant(m["coup_envoi"]) > maintenant]

    # a) une fois par jour : lier les matchs d'aujourd'hui (identifiants API-Football), lire les scores d'hier
    for vieux in [d for d in jours if d < (maintenant - timedelta(days=5)).strftime("%Y-%m-%d")]: del jours[vieux]
    for decalage, quoi in ((0, "lien"), (-1, "scores")):
        date = (maintenant + timedelta(days=decalage)).strftime("%Y-%m-%d")
        du_jour = [m for m in matchs if m["coup_envoi"][:10] == date]
        fait = jours.setdefault(date, {})
        if quoi == "lien":
            if not du_jour or all(m.get("foot") for m in du_jour): continue
            if fait.get("lien_jour") == aujourd_hui and maintenant.hour < fait.get("lien_heure", 0) + 6: continue   # un essai toutes les 6 h au plus
        else:
            if not du_jour or maintenant.hour < 5 or fait.get("scores_jour") == aujourd_hui: continue
            if all(m.get("score") for m in du_jour): continue
        if not foot_permis(src, -C.FOOT_RESERVE if quoi == "scores" else 0): continue
        reponse = src.matchs_du_jour(date)
        base.etat_modifie = True
        fait.update({"lien_jour": aujourd_hui, "lien_heure": maintenant.hour} if quoi == "lien" else {"scores_jour": aujourd_hui})
        if reponse is None:
            base.alerte(maintenant, f"API-Football : matchs du {date} indisponibles"); continue
        for comp, infos in C.COMPETITIONS.items():
            liens = rapprocher([m for m in du_jour if m["competition"] == comp], reponse, infos["foot"])
            for m in du_jour:
                f = liens.get(m["id"])
                if m["competition"] != comp or not f: continue
                nouveau = {"id": f["fixture"]["id"], "domicile": f["teams"]["home"]["id"], "exterieur": f["teams"]["away"]["id"],
                           "nom_domicile": f["teams"]["home"]["name"], "nom_exterieur": f["teams"]["away"]["name"]}
                score = score_depuis(f)
                if m.get("foot") != nouveau or (score and m.get("score") != score):
                    m["foot"] = nouveau
                    if score: m["score"] = score
                    base.toucher(m); touches.append(m)
        orphelins = [f"{m['domicile']} - {m['exterieur']}" for m in du_jour if not m.get("foot")]
        if orphelins: base.alerte(maintenant, f"API-Football : match(s) non retrouvé(s) le {date} : " + ", ".join(orphelins))

    # b) absents (blessés et suspendus) : 1 requête pour toute la journée, le matin puis avant chaque vague de H-45
    for date in sorted({m["coup_envoi"][:10] for m in futurs if m.get("foot")}):
        if date not in (aujourd_hui, (maintenant + timedelta(days=1)).strftime("%Y-%m-%d")): continue
        du_jour = [m for m in futurs if m["coup_envoi"][:10] == date and m.get("foot")]
        proche = any(instant(m["coup_envoi"]) - maintenant <= timedelta(minutes=50) for m in du_jour)
        fait = jours.setdefault(date, {})
        dernier = instant(fait["absents"]) if fait.get("absents") else None
        if dernier and not (proche and maintenant - dernier > timedelta(minutes=110)): continue
        if not dernier and date != aujourd_hui: continue
        if not foot_permis(src, len(du_jour)): continue
        reponse = src.blesses_du_jour(date)
        fait["absents"] = iso(maintenant); base.etat_modifie = True
        if reponse is None: continue
        for m in du_jour:
            absents = {"releve_a": iso(maintenant), "domicile": [], "exterieur": []}
            for x in reponse:
                if x["fixture"]["id"] != m["foot"]["id"]: continue
                cote = "domicile" if x["team"]["id"] == m["foot"]["domicile"] else "exterieur"
                if x["player"].get("type") == "Questionable": continue      # incertain : pas compté comme absent
                absents[cote].append({"id": x["player"]["id"], "nom": x["player"]["name"], "motif": x["player"].get("reason"), "source": "blesses"})
            ancien = m.get("absents")
            m["absents"] = absents; marquer_absents(base, m)
            if not ancien or [ancien.get(c) for c in ("domicile", "exterieur")] != [m["absents"][c] for c in ("domicile", "exterieur")]:
                base.toucher(m); touches.append(m)
            elif ancien: m["absents"]["releve_a"] = ancien.get("releve_a", m["absents"]["releve_a"])

    # c) compos officielles : demandées à H-35, H-20, puis une dernière fois 5 min après le coup d'envoi
    en_attente = [m for m in matchs if m.get("foot") and not m.get("compos")
                  and timedelta(minutes=-40) <= instant(m["coup_envoi"]) - maintenant <= timedelta(minutes=max(C.COMPOS_ESSAIS))]
    for m in sorted(en_attente, key=lambda m: m["coup_envoi"]):
        avant = (instant(m["coup_envoi"]) - maintenant).total_seconds() / 60
        essais = m.setdefault("compos_essais", [])
        rang = sum(1 for e in C.COMPOS_ESSAIS if avant <= e)       # combien d'essais devraient déjà avoir eu lieu
        if len(essais) >= rang: continue
        dernier_essai = rang == len(C.COMPOS_ESSAIS)
        # avant le coup d'envoi, on garde de quoi faire le dernier essai de tous les matchs encore sans compo
        if not foot_permis(src, 0 if dernier_essai else len(en_attente)): continue
        reponse = src.compos(m["foot"]["id"])
        essais.extend([iso(maintenant)] * (rang - len(essais))); base.toucher(m); base.etat_modifie = True
        if not reponse or not all(x.get("startXI") for x in reponse) or len(reponse) < 2: continue
        compos = {"recue_a": iso(maintenant), "minutes_avant": round(avant)}
        for x in reponse:
            cote = "domicile" if x["team"]["id"] == m["foot"]["domicile"] else "exterieur"
            joueur = lambda p: {"id": p["player"]["id"], "nom": p["player"]["name"], "poste": p["player"].get("pos")}
            compos[cote] = {"formation": x.get("formation"), "titulaires": [joueur(p) for p in x["startXI"]],
                            "remplacants": [joueur(p) for p in x.get("substitutes") or []]}
        if "domicile" not in compos or "exterieur" not in compos: continue
        m["compos"] = compos
        marquer_absents(base, m)             # d'abord avec la mémoire d'avant ce match…
        for cote in ("domicile", "exterieur"):   # …puis on ajoute ce match à la mémoire de l'équipe
            eq = base.equipes.setdefault(str(m["foot"][cote]), {"nom": m[cote], "matchs": [], "joueurs": {}})
            eq["matchs"] = [p for p in eq["matchs"] if p["match"] != m["foot"]["id"]]
            eq["matchs"].append({"match": m["foot"]["id"], "date": m["coup_envoi"][:10], "onze": [j["id"] for j in compos[cote]["titulaires"]],
                                 "gardien": next((j["id"] for j in compos[cote]["titulaires"] if j["poste"] == "G"), None)})
            eq["matchs"] = sorted(eq["matchs"], key=lambda p: p["date"])[-8:]
            for j in compos[cote]["titulaires"] + compos[cote]["remplacants"]: eq["joueurs"][str(j["id"])] = j["nom"]
            if len(eq["joueurs"]) > 60: eq["joueurs"] = dict(list(eq["joueurs"].items())[-60:])
        base.equipes_modifiees = True; touches.append(m)
    for vide in [d for d, v in jours.items() if not v]: del jours[vide]
    base.etat["foot"]["reste"] = src.foot_reste
    return touches


# ------------------------------------------------------------------ le passage complet
def passage(src, maintenant=None, base=None):
    maintenant = maintenant or datetime.now(timezone.utc)
    base = base or Base()
    src.odds_reste = base.etat.get("odds", {}).get("reste") if src.odds_reste is None else src.odds_reste
    if base.etat.get("foot", {}).get("jour") == maintenant.strftime("%Y-%m-%d") and src.foot_reste is None:
        src.foot_reste = base.etat["foot"].get("reste")
    fait = base.etat.get("planning_fait_a")
    if not fait or maintenant - instant(fait) >= timedelta(hours=6):
        planifier(base, src, maintenant)
    dates = [jour_paris(maintenant + timedelta(days=n)) for n in range(-2, 3)]
    matchs = base.matchs(dates)
    touches = relever(base, src, matchs, maintenant)
    touches += suivre_foot(base, src, matchs, maintenant)
    for m in {id(m): m for m in touches}.values():
        calculer(m); base.toucher(m)
    ecrit = base.enregistrer(maintenant)
    return {"ecrit": ecrit, "matchs_touches": len({id(m) for m in touches}), "journal": src.journal}


if __name__ == "__main__":
    from .sources import Sources
    bilan = passage(Sources())
    for ligne in bilan["journal"]: print(ligne)
    print(f"Passage terminé : {bilan['matchs_touches']} match(s) mis à jour." if bilan["ecrit"] else "Rien à faire.")
    sys.exit(0)
