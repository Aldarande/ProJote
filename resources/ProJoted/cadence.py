# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""cadence.py — À quelle fréquence chaque onglet Pronote est réellement collecté.

Le démon interrogeait les douze onglets à chaque cycle, sans distinction. Mesuré
le 17 septembre 2026 sur le compte de démonstration parent, un cycle complet
coûtait **113 requêtes HTTP et 5 ré-authentifications** :

    Emploi_du_temps  45 requêtes            Absences         6 requêtes  1 auth
    Notes            24 requêtes            Devoirs          6 requêtes  1 auth
    Notifications    19 requêtes  3 auths   Menus            2 requêtes
    Messages          9 requêtes            Compétences      1 requête
    Périodes          0 requête             Ical             1 requête
    Retards           0 requête             Punitions        0 requête

Ces chiffres dictent les cadences ci-dessous, et rien d'autre. Trois d'entre eux
méritent un commentaire :

* **Périodes, retards et punitions ne coûtent rien** — les données arrivent avec
  la session ou sont déjà en cache côté pronotepy. Les espacer n'aurait rien
  fait gagner, et aurait ajouté de la complexité pour zéro requête. Ils restent
  donc collectés à chaque cycle.
* **L'emploi du temps est le plus cher (45 requêtes), et reste à chaque cycle.**
  C'est le cœur de ce que le plugin sert à surveiller : une annulation de cours
  vue avec six heures de retard ne vaut rien. On paie sciemment.
* **Notifications et messagerie représentent 28 requêtes et 3 des 5
  ré-authentifications** pour des contenus qui ne sont pas à la minute. Ils
  passent à trois heures, ce qui les retire de deux cycles sur trois.

Une cadence n'est jamais une perte de donnée : l'onglet sauté conserve la valeur
du dernier relevé, renvoyée telle quelle à Jeedom (voir ``ProJoted.collecter``).
Jeedom reçoit donc toujours une charge complète, et le widget ne se vide pas.
"""

# Périodicité minimale entre deux collectes, en secondes. 0 = à chaque cycle.
TROIS_HEURES = 3 * 3600
DOUZE_HEURES = 12 * 3600

CADENCES = {
    # Cœur du suivi scolaire : à chaque cycle, quel qu'en soit le coût.
    "Emploi_du_temps": 0,
    "Notes": 0,
    "Devoirs": 0,
    "Absences": 0,
    "Retards": 0,
    "Punitions": 0,
    "Periodes": 0,
    "Competences": 0,
    "Ical": 0,
    # Consultables plus tard sans conséquence, et chers en requêtes.
    "Notifications": TROIS_HEURES,
    "Messages": TROIS_HEURES,
    # Publiés pour la semaine entière : deux relevés par jour suffisent.
    "Menus": DOUZE_HEURES,
}

# Statuts rapportés à Jeedom pour chaque onglet d'un cycle.
COUPE = "coupe"  # onglet non suivi pour cet équipement : pas de requête du tout
FRAIS = "frais"  # relevé à l'instant
GARDE = "garde"  # sauté par cadence, valeur du dernier relevé conservée
REPLI = "repli"  # la collecte a échoué, valeur du dernier relevé conservée
ECHEC = "echec"  # la collecte a échoué et aucune valeur antérieure n'existe


def periode(cle):
    """Périodicité minimale de l'onglet, en secondes (0 = chaque cycle)."""
    return CADENCES.get(cle, 0)


def doit_collecter(cle, dernier_releve, maintenant):
    """L'onglet doit-il être relevé maintenant ?

    Args:
        cle: nom de l'onglet dans la charge envoyée à Jeedom.
        dernier_releve: horodatage du dernier relevé réussi, ou None.
        maintenant: horodatage courant (``time.time()``).

    Returns:
        bool: True s'il faut interroger Pronote, False si la valeur conservée
        fait encore l'affaire.
    """
    p = periode(cle)
    if p <= 0 or dernier_releve is None:
        return True
    return (maintenant - dernier_releve) >= p
