"""Réglages de Nostradamus. Tout ce qui peut être recalé plus tard est ici (seuils, quotas, compétitions)."""

# code court -> nom affiché, clé The Odds API, numéro API-Football, code Football-Data (championnats seulement)
COMPETITIONS = {
    "L1":   {"nom": "Ligue 1",              "odds": "soccer_france_ligue_one",              "foot": 61,  "fd": "F1"},
    "SA":   {"nom": "Serie A",              "odds": "soccer_italy_serie_a",                 "foot": 135, "fd": "I1"},
    "LIGA": {"nom": "Liga",                 "odds": "soccer_spain_la_liga",                 "foot": 140, "fd": "SP1"},
    "PL":   {"nom": "Premier League",       "odds": "soccer_epl",                           "foot": 39,  "fd": "E0"},
    "BL":   {"nom": "Bundesliga",           "odds": "soccer_germany_bundesliga",            "foot": 78,  "fd": "D1"},
    "LDC":  {"nom": "Ligue des champions",  "odds": "soccer_uefa_champs_league",            "foot": 2,   "fd": None},
    "EL":   {"nom": "Europa League",        "odds": "soccer_uefa_europa_league",            "foot": 3,   "fd": None},
    "ECL":  {"nom": "Conference League",    "odds": "soccer_uefa_europa_conference_league", "foot": 848, "fd": None},
    "NL":   {"nom": "Ligue des nations",    "odds": "soccer_uefa_nations_league",           "foot": 5,   "fd": None},   # test pendant la trêve
}
BOOKMAKERS = {"pinnacle": "pinnacle", "winamax": "winamax_fr"}   # nom dans la base -> clé The Odds API (région eu)

# ---- Relevés : minutes avant le coup d'envoi, et jusqu'à quand un relevé en retard reste acceptable ----
RELEVES = {
    "H12": {"avant": 720, "limite": 480},   # visé à H-12, accepté jusqu'à H-8
    "H3":  {"avant": 180, "limite": 100},   # visé à H-3,  accepté jusqu'à H-1h40
    "H45": {"avant": 45,  "limite": 3},     # visé à H-45, accepté jusqu'à 3 min avant le coup d'envoi
}
# H-12 groupé : un seul relevé H-12 par compétition et par jour, pris 12 h avant le PREMIER match du jour ; il sert de
# point de départ à tous les matchs de ce jour-là (pour les matchs du soir il est donc pris un peu plus tôt que H-12).
# Sans ça le budget réel dépasse les 500 crédits certains mois (voir NOTES.md). Mettre False pour un H-12 exact par match.
H12_GROUPE = False
AVANCE_TOLEREE = 12   # si un appel part de toute façon pour la compétition, un relevé dû dans les 12 min en profite

# ---- Feux (cahier des charges) : ampleur de la variation entre H-12 et H-45, hausse ou baisse ----
SEUIL_ORANGE, SEUIL_ROUGE, SEUIL_VIOLET = 3.0, 7.0, 15.0
SEUIL_H3_H45 = 4.0        # plus de 4 % rien qu'entre H-3 et H-45 -> au moins Rouge
SEUIL_DESACCORD = 1.0     # Pinnacle et Winamax en sens opposé, d'au moins 1 % chacun -> au moins Orange
COTE_REFERENCE = 2.0      # cote pour laquelle « ampleur » = % classique ; en dessous, le mouvement est amplifié (voir calculs.ampleur)
# ---- Phrase « Le marché annonce » (en points de probabilité) ----
SEUIL_MOUVEMENT = 1.0     # en dessous, « pas de mouvement net »
SEUIL_PERTE = 0.5         # une issue qui perd plus que ça est « quittée » par le marché
SEUIL_MARGE = 1.5         # marge du bookmaker qui bouge de plus d'1,5 point -> « Mouvement incohérent »
# ---- Titulaires (calculé sur notre propre base de compos) ----
TITULAIRE_MATCHS = 5      # on regarde les 5 derniers matchs enregistrés de l'équipe
TITULAIRE_MINI = 3        # il en faut au moins 3 pour juger
TITULAIRE_PART = 0.6      # titulaire régulier = titulaire dans au moins 60 % de ces matchs

# ---- Garde-fou The Odds API (500 crédits par mois, remis à zéro le 1er) ----
ARRET_TOTAL = 20          # plus aucun relevé à 20 crédits restants
RYTHME_COMPLET = 10.0     # s'il reste moins de 10 crédits par jour jusqu'à la fin du mois, on sacrifie les H-3
# ---- Garde-fou API-Football (100 requêtes par jour, remises à zéro à minuit UTC) ----
FOOT_RESERVE = 6          # on garde toujours 6 requêtes (calendrier et scores du lendemain)
COMPOS_ESSAIS = [35, 20, -5]       # minutes avant le coup d'envoi où l'on (re)demande les compos tant qu'elles manquent (-5 = 5 min après)
