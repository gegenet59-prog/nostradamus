# Nostradamus — NOTES de reprise

Dernière mise à jour : 13 novembre 2026 (Fable). Cahier des charges : https://claude.ai/artifact/2VJG3mZfF27w6q3h9p2hNY

## Où on en est

| Étape | État |
| --- | --- |
| (a) Points « À vérifier » | **Fait** (détail plus bas, preuves dans `verif/`) |
| (b) Collecteur + base de données | **Fait.** Testé en vrai sur GitHub (passage lancé par une modification du code : OK, `data/etat.json` écrit). Le réveil programmé toutes les 5 min, lui, n'avait pas encore été observé le 13/11 à 0 h 50 (voir point 3). Premiers vrais relevés attendus le 20 novembre |
| Import de l'historique Football-Data | **Fait** : 25 720 matchs dans `data/historique/` |
| Écrans (matchs du jour, statistiques) | **À faire** (autre modèle) |
| Statistiques calculées | **À faire** (autre modèle) |
| Notifications Violet | **À faire** (autre modèle) |

Rien n'a été commencé côté page web : il n'y a pas encore d'`index.html`.

## Résultat des vérifications

1. **Pinnacle et Winamax FR dans la région `eu`** : OK pour 7 compétitions sur 8 (tous les matchs ont les deux cotes).
   Conference League : le 12/11, deux semaines avant ses matchs, seul 1 match sur 8 avait Pinnacle et aucun Winamax.
   Les bookmakers ouvrent cette compétition plus tard. **À recontrôler vers le 25-26 novembre** (regarder les relevés des matchs ECL du 26).
2. **Coût d'un relevé** : 1 crédit par appel, confirmé (en-tête `x-requests-last: 1`). Le calendrier (`/events`) est gratuit.
   **L'estimation de 410 crédits/mois était trop basse.** Simulation sur le vrai calendrier 2025-26 (`verif/budget.json`) :
   avec un H-12 exact par match, les 5 championnats seuls coûtent 270 à 490 crédits par mois, plus 40 à 60 pour les coupes
   d'Europe : 3 à 4 mois par an dépassent 500. **Décision de Gérard (13/11) : H-12 exact par match**, comme dans le cahier
   des charges (`H12_GROUPE = False` dans `collecteur/config.py`). Conséquence assumée : les gros mois, le garde-fou sacrifiera
   des H-3. L'autre option reste disponible (`H12_GROUPE = True` : un seul H-12 par compétition et par jour, 440 crédits au pire).
   Les 20 tests passent toujours (plusieurs se déroulent encore en mode groupé, remis en place par l'un d'eux : à clarifier un jour).
3. **Ponctualité des tâches programmées GitHub** : pas fiable à la minute (retards de 5 à 30 min documentés, parfois plus sur un
   dépôt neuf ; la 1re tâche programmée n'était toujours pas partie 17 min après sa création : mesure en cours dans
   `verif/ticks.json`, écrit par `.github/workflows/mesure.yml`, à supprimer une fois la mesure lue). Le collecteur est donc bâti pour
   s'en moquer : réveil toutes les 5 min, chaque réveil rattrape tout ce qui est dû, un relevé en retard reste accepté
   (H-45 jusqu'à 3 min du coup d'envoi) et son retard réel est noté (`retard_min`). **À contrôler après le week-end du 21-22
   novembre** : si des H-45 ont plus de 20 min de retard ou l'état `manque`, brancher le réveil Cloudflare (voir plus bas).
4. **Minutes GitHub Actions si le dépôt passe en privé** : 2 000 min/mois gratuites, or un réveil toutes les 5 min en consomme
   environ 8 600. **Le dépôt doit rester public** (illimité et gratuit). En privé il faudrait le réveil Cloudflare « intelligent »
   (uniquement quand un relevé est dû), et GitHub Pages sur dépôt privé demande de toute façon une formule payante.
5. **Compos dans API-Football** : la doc annonce une publication 20 à 40 min avant le coup d'envoi, donc souvent APRÈS H-45.
   Le collecteur les demande à H-35, H-20, puis 5 min après le coup d'envoi tant qu'elles manquent, et note l'heure réelle
   d'arrivée (`compos.minutes_avant`). Impossible à mesurer pendant la trêve : **à lire dans la base après le 21-22 novembre**
   pour la Ligue 1 et la Serie A.
6. **Notifications de Mon bus** : mécanisme compris, réutilisable (voir « Notifications » plus bas).

Autres découvertes importantes (formule gratuite d'API-Football, testée en vrai) :

- Calendrier par date : seulement hier, aujourd'hui, demain. Suffisant (lien des matchs le jour même, scores le lendemain).
- Tout ce qui demande la saison 2026 est refusé : pas de meilleurs buteurs, pas d'effectifs. Le paramètre `ids` (appels groupés) aussi.
- Compos par match : OK. Blessés par match : OK. Blessés de toute une journée en 1 appel (`injuries?date=`) : accepté.
- Conséquence : **« joueur clé » = gardien titulaire seulement pour l'instant.** Meilleur buteur et capitaine ne sont pas
  accessibles gratuitement. « Titulaire régulier » est déduit de nos propres compos enregistrées (titulaire dans 60 % des
  5 derniers matchs connus, 3 matchs minimum) : cette détection ne marchera qu'après 3 journées enregistrées par équipe.
- Football-Data : les cotes Pinnacle n'existent que de 2012-13 à la mi-saison 2025-26 (pas « 25 saisons »). Après, l'import
  prend la moyenne du marché (colonne `source` = `moy`).

Quotas au 13/11 : The Odds API 491 crédits restants sur 500 (9 dépensés en vérifications) ; API-Football une dizaine de requêtes.

## Comment ça marche

```
.github/workflows/collecteur.yml   réveil toutes les 5 min (+ à chaque modification de collecteur/) -> python3 -m collecteur.tick
.github/workflows/historique.yml   chaque mardi (+ si calculs/seuils changent) -> python3 -m collecteur.historique
collecteur/config.py               TOUS les réglages : compétitions, seuils des feux, garde-fous
collecteur/tick.py                 le collecteur : planning, relevés, API-Football, calculs, enregistrement
collecteur/calculs.py              feux, flèches, %, phrase « Le marché annonce », « Mouvement incohérent »
collecteur/sources.py              les appels aux 2 API (clés lues dans les secrets, jamais écrites)
collecteur/rapprochement.py        relie un match The Odds API à son jumeau API-Football (noms d'équipes différents)
collecteur/base.py                 lecture / écriture des fichiers de data/
collecteur/historique.py           import Football-Data + simulation de budget
tests/                             python3 -m unittest discover tests   (20 tests, aucune API appelée)
verif/                             scripts et résultats des vérifications (preuves, plus utilisés)
```

Un passage du collecteur :

1. **Planning** (toutes les 6 h, gratuit) : calendrier des 60 prochaines heures pour les 8 compétitions. Crée les matchs et
   l'heure prévue de leurs 3 relevés. Suit les changements d'horaire.
2. **Relevés** : pour chaque compétition ayant un relevé dû, 1 appel (1 crédit) qui sert tous les matchs concernés.
3. **API-Football** : lien des matchs du jour (1 requête), absents du jour (1 requête le matin, puis avant chaque vague de
   H-45), compos (1 à 3 requêtes par match), scores de la veille (1 requête après 5 h UTC).
4. **Calculs** puis écriture dans `data/` ; le workflow enregistre dans le dépôt seulement si quelque chose a changé.

Garde-fous : The Odds API (`mode_quota` dans tick.py) : H-3 sacrifiés s'il reste moins de 10 crédits par jour jusqu'à la fin du
mois, arrêt total à 20 crédits. API-Football : 6 requêtes toujours gardées en réserve, compos prioritaires.

## La base (dossier `data/`, lisible par la page web)

- `data/index.json` : `{"jours": {"2026-11-21": 37, …}}` (jours présents et nombre de matchs).
- `data/matchs/AAAA-MM-JJ.json` : tous les matchs d'un jour (date du coup d'envoi, heure de Paris), triés par heure. Par match :
  - `id`, `competition` (L1, SA, LIGA, PL, BL, LDC, EL, ECL ; noms complets dans config.py), `coup_envoi` (UTC), `domicile`, `exterieur`
  - `releves.H12 / H3 / H45` : `prevu`, `etat` (`attente`, `fait`, `vide` = pas de cote Pinnacle, `manque`, `sacrifie`),
    `fait_a`, `retard_min`, `pinnacle` et `winamax` sous la forme `{"1": 2.05, "N": 3.62, "2": 3.66}`
  - `feux` : `null` tant qu'il manque H-12 ou un relevé plus récent. Sinon `issues["1"|"N"|"2"]` = `feu` (vert, orange, rouge,
    violet), `fleche` (hausse, baisse, stable), `pct` (le % classique à afficher), `ampleur` (calcul en coulisse), `raisons` ;
    `provisoire: true` tant que H-45 n'est pas fait (calcul sur H-12 → H-3)
  - `marche` : `pari` (1, N, 2, 1N, N2, 12 ou null), `phrase` (prête à afficher), `incoherent` (afficher « Mouvement incohérent »)
  - `compos` (titulaires, remplaçants, heure d'arrivée), `absents.domicile / exterieur` (nom, motif, `titulaire`, `cle`)
  - `score` : `domicile`, `exterieur`, `issue` (1, N, 2), au temps réglementaire ; `foot` : identifiants API-Football
- `data/etat.json` : crédits restants, mode du garde-fou (`complet`, `sans_H3`, `arret`), dernier passage utile, alertes du collecteur.
- `data/equipes.json` : dernières compos par équipe (créé au premier match).
- `data/historique/<L1|SA|LIGA|PL|BL>.json` : une ligne par match, colonnes décrites en tête de fichier (cotes d'ouverture et
  de clôture, feux 0-3 = vert-violet, pari du marché, résultat). `index.json` à côté donne le bilan.

## Choix de calcul à connaître (calculs.py)

- **% affiché** = variation classique de la cote Pinnacle entre H-12 et H-45.
- **Feu** = le tableau du cahier des charges appliqué au % affiché. Le « calcul en coulisse » (probabilités, marge retirée)
  ne peut que **monter** le feu, et seulement pour les cotes sous 2,00 (ex. 1,30 → 1,25 : 4 % affichés mais feu Rouge).
  La raison est alors écrite dans `raisons`.
- Absences : elles montent le feu de l'issue « victoire » de l'équipe concernée (1 ou 2), pas le nul.
- **Phrase** : les issues qui perdent plus de 0,5 point de probabilité sont « quittées » ; le pari annoncé est l'ensemble des
  autres. Moins d'1 point de mouvement partout : « pas de mouvement net ».
- **Incohérent** : les 3 cotes bougent dans le même sens, ou la marge du bookmaker change de plus d'1,5 point.
- Dans l'historique, la variation va de l'ouverture (plusieurs jours avant) à la clôture : elle est bien plus grande que
  H-12 → H-45 (19 % de matchs avec un Violet). À afficher à part, comme prévu.

## Ce qui reste à faire (dans l'ordre conseillé)

1. **Contrôles du premier week-end (21-23 novembre)** en lisant `data/matchs/2026-11-2x.json` et `data/etat.json` :
   retards des H-45, matchs sans `foot` (rapprochement raté : compléter `SURNOMS` dans rapprochement.py), heure d'arrivée des
   compos, absents bien remplis, scores présents le lendemain, crédits consommés par rapport au budget.
2. **Écran principal** (`index.html` à la racine, sur le modèle de Mon bus) : lit `data/index.json` puis `data/matchs/<jour>.json`.
   Vérifier d'abord que GitHub Pages republie bien après les enregistrements du robot
   (https://gegenet59-prog.github.io/nostradamus/data/etat.json doit suivre). Sinon lire les fichiers via
   `https://raw.githubusercontent.com/gegenet59-prog/nostradamus/main/data/…`.
3. **Statistiques** : à calculer par le collecteur (cahier des charges) à partir de `data/matchs/` (base propre) et de
   `data/historique/` (à part). Rien n'est encore calculé.
4. **Notifications Violet**, sur le modèle de Mon bus (`mon-bus/sw.js`, `mon-bus/relais/src/alertes.js`, `index.html` fonction
   `enregistrerAlertes`) : Web Push « réveil sans contenu » envoyé par un Worker Cloudflare (Durable Object qui garde la clé VAPID
   et les abonnés) ; le téléphone réveillé va lire son message chez le Worker, et un appui ouvre l'appli. Pour Nostradamus :
   un Worker dédié dont la tâche programmée lit `data/matchs/<jour>.json` (public, aucune clé nécessaire), repère les nouvelles
   issues `violet` et réveille les abonnés. Le dépôt mon-bus est déployé automatiquement par Cloudflare (`wrangler.toml`).
5. **Réveil Cloudflare** (seulement si GitHub est trop en retard) : un Worker avec tâche programmée qui appelle
   `POST https://api.github.com/repos/gegenet59-prog/nostradamus/dispatches` avec `{"event_type":"tick"}`. Le workflow l'accepte
   déjà (`repository_dispatch`). Il faut un jeton GitHub (accès « Contents : écriture » sur ce seul dépôt) rangé dans les secrets
   Cloudflare : c'est Gérard qui doit le créer.
6. Recaler les seuils après 4 à 6 semaines (config.py), puis relancer l'historique (automatique dès que config.py change).

## Règles à garder

- Formules gratuites uniquement. Ne jamais appeler The Odds API « pour voir » : chaque appel `/odds` coûte 1 crédit.
- Les clés restent dans les secrets du dépôt. Jamais dans le code, la page, les fichiers de `data/` ou les journaux.
- Pour tester : `python3 -m unittest discover tests` (fausses API). `verif/essai.py` fait un essai réel pour 1 crédit.
- Gérard n'est pas développeur et travaille surtout sur son téléphone Android : lui expliquer simplement.
