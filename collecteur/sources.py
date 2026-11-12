"""Appels aux deux API. Les clés viennent des secrets GitHub (variables d'environnement) et ne sont jamais
écrites : ni dans les fichiers, ni dans les journaux (les erreurs n'affichent jamais l'adresse appelée)."""
import json, os, urllib.error, urllib.parse, urllib.request
from . import config as C

ODDS = "https://api.the-odds-api.com/v4"
FOOT = "https://v3.football.api-sports.io"


def _appel(url, entetes=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=entetes or {}), timeout=40) as r:
            return r.status, json.loads(r.read().decode("utf-8")), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, None, {k.lower(): v for k, v in e.headers.items()}
    except Exception:
        return 0, None, {}


def _entier(v):
    try: return int(float(v))
    except (TypeError, ValueError): return None


class Sources:
    """odds_reste / foot_reste : dernier stock connu (lu dans les en-têtes de réponse), None si inconnu."""

    def __init__(self, odds_reste=None, foot_reste=None):
        self.cle_odds = os.environ.get("ODDS_API_KEY", "")
        self.cle_foot = os.environ.get("API_FOOTBALL_KEY", "")
        self.odds_reste, self.foot_reste = odds_reste, foot_reste
        self.journal = []          # ce qui a été appelé pendant ce passage (sans les clés)

    # ---------- The Odds API ----------
    def evenements(self, comp, debut, fin):
        """Calendrier d'une compétition. GRATUIT (ne consomme aucun crédit). Renvoie une liste ou None."""
        q = urllib.parse.urlencode({"apiKey": self.cle_odds, "dateFormat": "iso",
                                    "commenceTimeFrom": debut.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "commenceTimeTo": fin.strftime("%Y-%m-%dT%H:%M:%SZ")})
        code, j, _ = _appel(f"{ODDS}/sports/{C.COMPETITIONS[comp]['odds']}/events?{q}")
        self.journal.append(f"calendrier {comp} : {code}")
        return j if code == 200 and isinstance(j, list) else None

    def cotes(self, comp):
        """Cotes 1N2 de tous les matchs à venir d'une compétition, région eu. COÛT : 1 crédit. Liste ou None."""
        q = urllib.parse.urlencode({"apiKey": self.cle_odds, "regions": "eu", "markets": "h2h",
                                    "oddsFormat": "decimal", "dateFormat": "iso"})
        code, j, h = _appel(f"{ODDS}/sports/{C.COMPETITIONS[comp]['odds']}/odds?{q}")
        reste = _entier(h.get("x-requests-remaining"))
        if reste is not None: self.odds_reste = reste
        elif code == 200 and self.odds_reste is not None: self.odds_reste -= 1
        self.journal.append(f"cotes {comp} : {code}, reste {self.odds_reste} crédits")
        return j if code == 200 and isinstance(j, list) else None

    # ---------- API-Football ----------
    def _foot(self, chemin, nom):
        code, j, h = _appel(f"{FOOT}/{chemin}", {"x-apisports-key": self.cle_foot})
        reste = _entier(h.get("x-ratelimit-requests-remaining"))
        if reste is not None: self.foot_reste = reste
        elif self.foot_reste is not None: self.foot_reste -= 1
        erreurs = (j or {}).get("errors")
        self.journal.append(f"{nom} : {code}{' ' + json.dumps(erreurs, ensure_ascii=False) if erreurs else ''}, reste {self.foot_reste} requêtes")
        return j.get("response") if code == 200 and j and not erreurs else None

    def matchs_du_jour(self, date):
        """Tous les matchs du monde pour une date UTC (AAAA-MM-JJ) : identifiants, statuts et scores. 1 requête.
        La formule gratuite n'autorise que hier, aujourd'hui et demain."""
        return self._foot(f"fixtures?date={date}", f"matchs du {date}")

    def blesses_du_jour(self, date):
        """Blessés et suspendus de tous les matchs d'une date. 1 requête."""
        return self._foot(f"injuries?date={date}", f"absents du {date}")

    def blesses(self, foot_id):
        return self._foot(f"injuries?fixture={foot_id}", f"absents du match {foot_id}")

    def compos(self, foot_id):
        """Compos officielles d'un match. 1 requête. Liste vide tant qu'elles ne sont pas publiées."""
        return self._foot(f"fixtures/lineups?fixture={foot_id}", f"compos du match {foot_id}")
