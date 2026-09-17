# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""presence_pronote.py — Mémoire des refus de l'onglet « Présence ».

Absences, retards et punitions passent tous par le même onglet Pronote (19).
Certains comptes le voient déclaré accessible — il figure bien dans
`authorized_onglets` — mais la requête est refusée. pronotepy répond à ce refus
par une ré-authentification complète avant de rejouer : trois collecteurs, trois
authentifications, et aucune donnée au bout.

Le refus est donc retenu le temps du cycle : le premier collecteur essaie, les
deux suivants s'abstiennent. La mémoire est remise à zéro à chaque cycle, si
bien qu'un droit accordé entre-temps est pris en compte immédiatement.

Extrait de ProJoted.py en v1.6.0, sans modification du code.
"""

import logging


# Absences, retards et punitions passent tous par l'onglet « Présence » (19).
# Certains comptes le voient déclaré accessible par Pronote — il figure bien dans
# authorized_onglets — mais la requête est refusée (« Accès refusé »). pronotepy
# répond à ce refus par une ré-authentification complète avant de rejouer, qui
# échoue à son tour : trois collectes, trois authentifications, et aucune donnée.
#
# On retient donc le refus le temps du cycle en cours : la première collecte
# essaie, les deux suivantes s'abstiennent. La mémoire est remise à zéro à chaque
# cycle, si bien qu'un droit accordé entre-temps est pris en compte immédiatement.
_presence_refusee = set()


def _refus_de_presence(exception):
    """Pronote refuse-t-il l'accès à l'onglet Présence ?

    Le refus initial est « Accès refusé » ; après la ré-authentification que
    pronotepy déclenche, le rejeu échoue sur « La page a expiré ». Les deux
    signatures traduisent la même impasse.
    """
    message = str(exception).lower()
    return "accès refusé" in message or "acces refuse" in message or (
        "page a expiré" in message
    )


def _presence_deja_refusee(eq_id):
    return str(eq_id) in _presence_refusee


def _noter_refus_presence(eq_id, quoi, exception):
    _presence_refusee.add(str(eq_id))
    logging.warning(
        "Onglet Présence refusé par Pronote (%s) : %s. Les autres collectes qui en "
        "dépendent sont ignorées pour ce cycle — chacune coûterait une "
        "ré-authentification pour rien.",
        quoi,
        exception,
    )
