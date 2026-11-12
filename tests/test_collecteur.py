"""Simulation complète du collecteur avec de fausses API (aucun appel réseau, aucun crédit dépensé)."""
import shutil, tempfile, unittest
from datetime import datetime, timedelta, timezone
from collecteur import base as B, config as C, tick as T

UTC = timezone.utc
J = datetime(2026, 11, 21, tzinfo=UTC)
MATCHS = [  # id, compétition, coup d'envoi, domicile, extérieur, (noms API-Football), n° API-Football
    ("a", "L1", J.replace(hour=16, minute=15), "Nice", "Paris Saint Germain", ("Nice", "Paris Saint Germain"), 101),
    ("b", "L1", J.replace(hour=19, minute=45), "AS Monaco", "Auxerre", ("Monaco", "Auxerre"), 102),
    ("c", "L1", J.replace(hour=19, minute=45), "Strasbourg", "Brest", ("Strasbourg", "Stade Brestois 29"), 103),
    ("d", "SA", J.replace(hour=19, minute=45), "Napoli", "Torino", ("Napoli", "Torino"), 104),
]
ISO = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")


class FaussesSources:
    def __init__(self, odds_reste=500, compos_a=30):
        self.odds_reste, self.foot_reste, self.journal = odds_reste, 100, []
        self.maintenant, self.appels_cotes, self.appels_foot, self.compos_a = None, [], [], compos_a

    def evenements(self, comp, debut, fin):
        return [{"id": i, "commence_time": ISO(ko), "home_team": d, "away_team": e}
                for i, c, ko, d, e, _, _ in MATCHS if c == comp and debut <= ko <= fin]

    def cotes(self, comp):
        self.odds_reste -= 1; self.appels_cotes.append((comp, self.maintenant))
        sortie = []
        for i, c, ko, d, e, _, _ in MATCHS:
            if c != comp or ko <= self.maintenant: continue
            derive = 1 + 0.2 * max(0, 12 - (ko - self.maintenant).total_seconds() / 3600) / 12 if i == "a" else 1   # la cote du PSG grimpe
            prix = lambda k: [{"name": d, "price": round(2.5 * k / (1 + 0.55 * (derive - 1)), 3)}, {"name": e, "price": round(2.9 * derive, 3)}, {"name": "Draw", "price": 3.4}]
            sortie.append({"id": i, "commence_time": ISO(ko), "home_team": d, "away_team": e, "bookmakers": [
                {"key": "pinnacle", "markets": [{"key": "h2h", "last_update": ISO(self.maintenant), "outcomes": prix(1)}]},
                {"key": "winamax_fr", "markets": [{"key": "h2h", "outcomes": prix(0.96)}]}]})
        return sortie

    def _foot(self, quoi):
        self.foot_reste = (100 if self.foot_reste is None else self.foot_reste) - 1; self.appels_foot.append((quoi, self.maintenant))

    def matchs_du_jour(self, date):
        self._foot("matchs " + date)
        return [{"fixture": {"id": n, "date": ko.isoformat(), "status": {"short": "FT" if self.maintenant > ko + timedelta(hours=2) else "NS"}},
                 "league": {"id": C.COMPETITIONS[c]["foot"]}, "teams": {"home": {"id": n * 10, "name": noms[0]}, "away": {"id": n * 10 + 1, "name": noms[1]}},
                 "goals": {"home": 2, "away": 1}, "score": {"fulltime": {"home": 2, "away": 1}}}
                for i, c, ko, d, e, noms, n in MATCHS if ko.strftime("%Y-%m-%d") == date]

    def blesses_du_jour(self, date):
        self._foot("absents " + date)
        return [{"fixture": {"id": 101}, "team": {"id": 1011}, "player": {"id": 7, "name": "Buteur Blessé", "type": "Missing Fixture", "reason": "Knee Injury"}},
                {"fixture": {"id": 101}, "team": {"id": 1010}, "player": {"id": 8, "name": "Incertain", "type": "Questionable", "reason": "Knock"}}]

    def compos(self, n):
        self._foot(f"compos {n}")
        ko = next(m[2] for m in MATCHS if m[6] == n)
        if (ko - self.maintenant).total_seconds() / 60 > self.compos_a: return []
        onze = lambda eq: [{"player": {"id": eq * 100 + k, "name": f"J{k}", "pos": "G" if k == 0 else "D"}} for k in range(11)]
        return [{"team": {"id": n * 10}, "formation": "4-3-3", "startXI": onze(n * 10), "substitutes": []},
                {"team": {"id": n * 10 + 1}, "formation": "4-4-2", "startXI": onze(n * 10 + 1), "substitutes": []}]


class Collecteur(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp(); B.RACINE = self.dossier

    def tearDown(self):
        shutil.rmtree(self.dossier)

    def dérouler(self, src, debut, fin, pas=5, decalage=1):
        t = debut + timedelta(minutes=decalage)
        while t <= fin:
            src.maintenant = t; src.journal = []
            T.passage(src, t)
            t += timedelta(minutes=pas)
        return {m["id"]: m for m in B.lire("matchs/2026-11-21.json")["matchs"]}

    def test_journee_complete(self):
        src = FaussesSources()
        m = self.dérouler(src, J - timedelta(hours=10), J + timedelta(days=1, hours=7))
        # 3 créneaux (L1 16:15, L1 19:45, SA 19:45) x 3 relevés = 9 crédits, pas un de plus
        self.assertEqual(len(src.appels_cotes), 9); self.assertEqual(src.odds_reste, 491)
        for x in m.values():
            for nom in ("H12", "H3", "H45"):
                r = x["releves"][nom]
                self.assertEqual(r["etat"], "fait"); self.assertLessEqual(abs(r["retard_min"]), 5)
                self.assertEqual(set(r["pinnacle"]), {"1", "N", "2"}); self.assertTrue(r["winamax"])
            self.assertEqual(x["score"], {"domicile": 2, "exterieur": 1, "issue": "1", "statut": "FT"})
            self.assertTrue(x["compos"]); self.assertEqual(len(x["compos"]["domicile"]["titulaires"]), 11)
            self.assertFalse(x["feux"]["provisoire"])
        # lien malgré des noms différents (AS Monaco / Monaco, Brest / Stade Brestois 29)
        self.assertEqual([m[i]["foot"]["id"] for i in "abcd"], [101, 102, 103, 104])
        # la cote du PSG a grimpé de ~19 % : Violet à la hausse, et le marché « quitte » le 2
        f = m["a"]["feux"]["issues"]["2"]
        self.assertEqual((f["feu"], f["fleche"]), ("violet", "hausse")); self.assertEqual(m["a"]["marche"]["pari"], "1N")
        self.assertEqual(m["b"]["feux"]["issues"]["1"]["feu"], "vert"); self.assertIsNone(m["b"]["marche"]["pari"])
        # absents : le blessé est gardé, l'incertain non
        self.assertEqual([a["nom"] for a in m["a"]["absents"]["exterieur"]], ["Buteur Blessé"]); self.assertEqual(m["a"]["absents"]["domicile"], [])
        # API-Football : très loin des 100 requêtes
        self.assertLess(len(src.appels_foot), 20)
        self.assertEqual(B.lire("index.json")["jours"], {"2026-11-21": 4})
        self.assertEqual(B.lire("etat.json")["odds"]["reste"], 491)

    def test_relance_sans_double_depense(self):
        src = FaussesSources()
        self.dérouler(src, J - timedelta(hours=10), J + timedelta(hours=8), pas=1)     # un passage par minute
        self.assertEqual(len(src.appels_cotes), 3)                                      # les 3 H-12 de la matinée, une seule fois chacun

    def test_reveils_en_retard(self):
        src = FaussesSources()
        m = self.dérouler(src, J - timedelta(hours=10), J + timedelta(hours=20), pas=25, decalage=13)   # GitHub en retard : 25 min entre deux passages
        self.assertTrue(all(x["releves"][n]["etat"] == "fait" for x in m.values() for n in ("H12", "H3", "H45")))
        self.assertLessEqual(max(x["releves"]["H45"]["retard_min"] for x in m.values()), 25)

    def test_h3_sacrifies_quand_le_stock_baisse(self):
        src = FaussesSources(odds_reste=120)        # 100 crédits utiles pour 10 jours : 10 par jour, sous le rythme complet
        m = self.dérouler(src, J - timedelta(hours=10), J + timedelta(hours=20))
        self.assertTrue(all(x["releves"]["H3"]["etat"] == "sacrifie" for x in m.values()))
        self.assertTrue(all(x["releves"][n]["etat"] == "fait" for x in m.values() for n in ("H12", "H45")))
        self.assertEqual(len(src.appels_cotes), 6); self.assertFalse(m["a"]["feux"]["provisoire"])
        self.assertEqual(B.lire("etat.json")["odds"]["mode"], "sans_H3")

    def test_arret_total_a_20_credits(self):
        src = FaussesSources(odds_reste=23)
        m = self.dérouler(src, J - timedelta(hours=10), J + timedelta(hours=20))
        self.assertEqual(src.odds_reste, 20)                                            # jamais en dessous de 20
        self.assertEqual(B.lire("etat.json")["odds"]["mode"], "arret")

    def test_changement_d_horaire(self):
        src = FaussesSources()
        self.dérouler(src, J - timedelta(hours=30), J - timedelta(hours=20))
        MATCHS[3] = MATCHS[3][:2] + (J.replace(hour=17, minute=0),) + MATCHS[3][3:]
        try:
            m = self.dérouler(src, J - timedelta(hours=13), J + timedelta(hours=20))
            self.assertEqual(m["d"]["coup_envoi"], "2026-11-21T17:00:00Z"); self.assertEqual(m["d"]["releves"]["H45"]["prevu"], "2026-11-21T16:15:00Z")
            self.assertEqual(m["d"]["releves"]["H45"]["etat"], "fait"); self.assertEqual(len(m), 4)
        finally:
            MATCHS[3] = MATCHS[3][:2] + (J.replace(hour=19, minute=45),) + MATCHS[3][3:]

    def test_titulaire_regulier_absent(self):
        base = B.Base()
        base.equipes["1010"] = {"nom": "Nice", "joueurs": {"5": "Pilier", "1": "Gardien"}, "matchs": [
            {"match": k, "date": f"2026-11-0{k}", "onze": [1, 5, 6], "gardien": 1} for k in range(1, 5)]}
        m = {"domicile": "Nice", "exterieur": "PSG", "foot": {"id": 101, "domicile": 1010, "exterieur": 1011},
             "absents": {"domicile": [{"id": 5, "nom": "Pilier", "source": "blesses"}], "exterieur": []},
             "compos": {"domicile": {"titulaires": [{"id": 6, "nom": "x", "poste": "D"}, {"id": 99, "nom": "Doublure", "poste": "G"}], "remplacants": [{"id": 1, "nom": "Gardien", "poste": "G"}]},
                        "exterieur": {"titulaires": [], "remplacants": []}}}
        T.marquer_absents(base, m)
        d = {a["nom"]: a for a in m["absents"]["domicile"]}
        self.assertTrue(d["Pilier"]["titulaire"]); self.assertIsNone(d["Pilier"]["cle"])
        self.assertEqual((d["Gardien"]["cle"], d["Gardien"]["motif"]), ("gardien", "sur le banc"))


if __name__ == "__main__":
    unittest.main()
