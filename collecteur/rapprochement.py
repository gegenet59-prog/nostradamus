"""Rapproche les matchs de The Odds API de ceux d'API-Football (les noms d'équipes diffèrent d'une source à l'autre)."""
import re, unicodedata
from datetime import datetime
from difflib import SequenceMatcher

VIDES = {"fc", "cf", "ac", "as", "sc", "ssc", "afc", "club", "de", "sv", "vfb", "vfl", "tsg", "rc", "ogc", "us", "ss",
         "calcio", "1", "04", "05", "1899", "fk", "sk", "bk", "if", "jk", "cd", "ud", "rcd", "sd", "ca", "stade", "olympique", "real"}
SURNOMS = {"wolves": "wolverhampton", "psg": "paris", "inter": "internazionale", "man": "manchester", "utd": "united",
           "spurs": "tottenham", "germain": "", "saint": "st", "sporting": "sporting", "munchen": "munich", "koln": "cologne"}


def simplifier(nom):
    s = unicodedata.normalize("NFKD", nom.replace("ø", "o").replace("Ø", "O").replace("ß", "ss")).encode("ascii", "ignore").decode().lower()
    mots = [SURNOMS.get(m, m) for m in re.split(r"[^a-z0-9]+", s) if m]
    utiles = [m for m in mots if m and m not in VIDES]
    return " ".join(utiles or mots)


def ressemblance(a, b):
    a, b = simplifier(a), simplifier(b)
    if not a or not b: return 0.0
    if a == b: return 1.0
    ma, mb = set(a.split()), set(b.split())
    if ma <= mb or mb <= ma: return 0.9
    if a.split()[0] == b.split()[0] and len(a.split()[0]) > 3: return 0.8
    return SequenceMatcher(None, a, b).ratio()


def _instant(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def rapprocher(nos_matchs, matchs_foot, numero_ligue):
    """nos_matchs : matchs d'une compétition (notre base). matchs_foot : réponse API-Football d'un jour.
    Renvoie {notre id: match API-Football}. Un match n'est lié que si l'heure colle (à 2 h près) et que les noms se ressemblent,
    ou s'il est le seul candidat restant à cette heure-là."""
    candidats = [f for f in matchs_foot if f["league"]["id"] == numero_ligue]
    paires = []
    for m in nos_matchs:
        for f in candidats:
            ecart = abs((_instant(m["coup_envoi"]) - _instant(f["fixture"]["date"])).total_seconds())
            if ecart > 7200: continue
            note = (ressemblance(m["domicile"], f["teams"]["home"]["name"]) + ressemblance(m["exterieur"], f["teams"]["away"]["name"])) / 2
            paires.append((note - ecart / 72000, note, m["id"], f["fixture"]["id"], f))
    liens, pris = {}, set()
    for _, note, mid, fid, f in sorted(paires, key=lambda p: -p[0]):
        if mid in liens or fid in pris: continue
        restants = [p for p in paires if p[2] == mid and p[3] not in pris]
        if note >= 0.5 or len(restants) == 1 and note >= 0.25:
            liens[mid] = f; pris.add(fid)
    return liens
