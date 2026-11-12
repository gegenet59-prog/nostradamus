"""Tests des calculs : python3 -m unittest discover tests"""
import unittest
from collecteur import calculs as K


def cotes_depuis_probas(p1, pn, p2, marge=0.03):
    return {"1": round(1 / (p1 * (1 + marge)), 3), "N": round(1 / (pn * (1 + marge)), 3), "2": round(1 / (p2 * (1 + marge)), 3)}


def match(h12, h45, h3=None, w12=None, w45=None, absents=None):
    r = {"H12": {"pinnacle": h12, "winamax": w12}, "H45": {"pinnacle": h45, "winamax": w45}}
    if h3: r["H3"] = {"pinnacle": h3}
    return K.calculer({"domicile": "Lille", "exterieur": "Lens", "releves": r, "absents": absents})


class Calculs(unittest.TestCase):
    def test_probabilites(self):
        p, marge = K.probabilites({"1": 2.0, "N": 4.0, "2": 4.0})
        self.assertAlmostEqual(sum(p.values()), 1); self.assertAlmostEqual(p["1"], 0.5); self.assertAlmostEqual(marge, 0)

    def test_ampleur_egale_pct_classique_a_cote_3(self):
        self.assertAlmostEqual(K.ampleur(1 / 3, 1 / 3.09), 3.0, delta=0.15)

    def test_petite_cote_pese_autant(self):
        # 1,30 -> 1,25 (4 % à l'écran) doit peser à peu près comme 6,00 -> 7,00 (17 % à l'écran)
        petit, gros = K.ampleur(1 / 1.30, 1 / 1.25), K.ampleur(1 / 6.0, 1 / 7.0)
        self.assertGreater(petit, 7); self.assertLess(abs(petit - gros), 3)

    def test_exemple_du_cahier_des_charges(self):
        m = match({"1": 2.10, "N": 3.40, "2": 3.60}, {"1": 1.974, "N": 3.434, "2": 4.212})
        f = m["feux"]["issues"]
        self.assertEqual((f["1"]["fleche"], f["1"]["pct"]), ("baisse", -6.0))
        self.assertEqual((f["N"]["feu"], f["N"]["fleche"]), ("vert", "hausse"))
        self.assertEqual((f["2"]["feu"], f["2"]["pct"]), ("violet", 17.0))
        self.assertIn(f["1"]["feu"], ("orange", "rouge"))
        self.assertEqual(m["marche"]["phrase"], "Le marché annonce : Lens ne gagne pas (1N)")
        self.assertFalse(m["marche"]["incoherent"]); self.assertFalse(m["feux"]["provisoire"])

    def test_rien_ne_bouge(self):
        c = {"1": 2.10, "N": 3.40, "2": 3.60}
        m = match(c, dict(c))
        self.assertTrue(all(x["feu"] == "vert" for x in m["feux"]["issues"].values()))
        self.assertIsNone(m["marche"]["pari"])

    def test_tous_les_paris(self):
        base = (0.40, 0.28, 0.32)
        cas = {"1": (0.46, 0.25, 0.29), "N": (0.37, 0.34, 0.29), "2": (0.37, 0.25, 0.38),
               "1N": (0.43, 0.31, 0.26), "N2": (0.34, 0.31, 0.35), "12": (0.43, 0.22, 0.35)}
        for attendu, arrivee in cas.items():
            m = match(cotes_depuis_probas(*base), cotes_depuis_probas(*arrivee))
            self.assertEqual(m["marche"]["pari"], attendu)

    def test_mouvement_incoherent(self):
        m = match({"1": 2.10, "N": 3.40, "2": 3.60}, {"1": 2.02, "N": 3.25, "2": 3.45})   # tout baisse : la marge monte
        self.assertTrue(m["marche"]["incoherent"])

    def test_sans_h12_pas_de_feu(self):
        m = K.calculer({"domicile": "A", "exterieur": "B", "releves": {"H45": {"pinnacle": {"1": 2, "N": 3, "2": 4}}}})
        self.assertIsNone(m["feux"]); self.assertIsNone(m["marche"])

    def test_provisoire_sur_h3(self):
        m = K.calculer({"domicile": "A", "exterieur": "B", "releves": {
            "H12": {"pinnacle": {"1": 2.10, "N": 3.40, "2": 3.60}}, "H3": {"pinnacle": {"1": 2.00, "N": 3.45, "2": 3.85}}}})
        self.assertTrue(m["feux"]["provisoire"]); self.assertEqual(m["feux"]["base"], "H12-H3")

    def test_desaccord_winamax(self):
        c = {"1": 2.10, "N": 3.40, "2": 3.60}
        m = match(c, {"1": 2.14, "N": 3.40, "2": 3.52}, w12={"1": 2.00, "N": 3.30, "2": 3.40}, w45={"1": 1.95, "N": 3.30, "2": 3.50})
        self.assertEqual(m["feux"]["issues"]["1"]["feu"], "orange")
        self.assertIn("Pinnacle et Winamax en sens opposé", m["feux"]["issues"]["1"]["raisons"])

    def test_coup_de_derniere_heure(self):
        c = {"1": 2.10, "N": 3.40, "2": 3.60}
        m = match(c, {"1": 2.20, "N": 3.40, "2": 3.38}, h3={"1": 2.06, "N": 3.40, "2": 3.70})
        self.assertEqual(m["feux"]["issues"]["1"]["feu"], "rouge")

    def test_absences(self):
        c = {"1": 2.10, "N": 3.40, "2": 3.60}
        m = match(c, dict(c), absents={"domicile": [{"nom": "X", "titulaire": True}], "exterieur": [{"nom": "Y", "titulaire": True, "cle": "gardien"}]})
        f = m["feux"]["issues"]
        self.assertEqual((f["1"]["feu"], f["N"]["feu"], f["2"]["feu"]), ("orange", "vert", "rouge"))


if __name__ == "__main__":
    unittest.main()
