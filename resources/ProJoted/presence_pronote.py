# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""presence_pronote.py — Mémoire des refus de l'onglet « Présence ».

Absences, retards, punitions et évènements de vie scolaire passent tous par le
même onglet Pronote (19). Certains comptes le voient déclaré accessible — il
figure bien dans `authorized_onglets` — mais la requête est refusée. pronotepy
répond à ce refus par une ré-authentification complète avant de rejouer :
quatre collecteurs, quatre authentifications, et aucune donnée au bout.

Le refus est donc retenu le temps du cycle : le premier collecteur essaie, les
trois suivants s'abstiennent. La mémoire est remise à zéro à chaque cycle, si
bien qu'un droit accordé entre-temps est pris en compte immédiatement.

**Le motif est retenu avec le refus, et pas seulement journalisé.** Sans lui,
les quatre collecteurs rendaient leur structure vide — ``nb_absences: 0``,
``nb_retard: 0``… — sans rien qui distingue « cet enfant n'a aucune absence »
de « le plugin n'a pas pu lire les absences ». Jeedom écrivait donc quatre
commandes à zéro, statut « Connecté », et un scénario d'alerte branché sur ces
compteurs ne pouvait pas se déclencher. Le motif conservé ici devient la clé
``error`` de la charge, que ``ProJoted.collecter()`` traite comme un échec : la
valeur du relevé précédent est conservée au lieu de laisser passer un zéro.

Extrait de ProJoted.py en v1.6.0.
"""

import logging


# Motif du refus de l'onglet « Présence », par équipement (clé : identifiant en
# chaîne). La présence de l'entrée vaut refus ; sa valeur porte le message
# Pronote, repris dans la clé « error » des quatre collecteurs concernés.
#
# Absences, retards, punitions et évènements passent tous par l'onglet
# « Présence » (19). Certains comptes le voient déclaré accessible par Pronote —
# il figure bien dans authorized_onglets — mais la requête est refusée
# (« Accès refusé »). pronotepy répond à ce refus par une ré-authentification
# complète avant de rejouer, qui échoue à son tour : quatre collectes, quatre
# authentifications, et aucune donnée.
#
# On retient donc le refus le temps du cycle en cours : la première collecte
# essaie, les trois suivantes s'abstiennent. La mémoire est remise à zéro à
# chaque cycle, si bien qu'un droit accordé entre-temps est pris en compte
# immédiatement.
_presence_refusee = {}


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


def _motif_de_refus(eq_id):
    """Message Pronote du refus retenu pour cet équipement, ou None.

    Sert à remplir la clé ``error`` des collectes qui s'abstiennent : elles
    n'ont pas vu l'erreur passer, mais doivent la rapporter tout de même.
    """
    return _presence_refusee.get(str(eq_id))


def _oublier_refus_presence(eq_id):
    """Ouvre un nouveau cycle pour cet équipement : le refus est réessayé.

    La portée est volontairement courte — le refus peut n'être que temporaire
    (début d'année, page non encore initialisée) et un droit accordé
    entre-temps doit être pris en compte dès le cycle suivant.
    """
    _presence_refusee.pop(str(eq_id), None)


def _noter_refus_presence(eq_id, quoi, exception):
    _presence_refusee[str(eq_id)] = str(exception)
    logging.warning(
        "Onglet Présence refusé par Pronote (%s) : %s. Les autres collectes qui en "
        "dépendent sont ignorées pour ce cycle — chacune coûterait une "
        "ré-authentification pour rien.",
        quoi,
        exception,
    )


def _erreur_de_refus(eq_id, quoi):
    """Libellé de la clé ``error`` rendue par un collecteur qui s'est abstenu.

    Mentionne l'onglet plutôt que la seule collecte : les quatre commandes à
    zéro d'un même cycle ont une cause unique, et c'est elle qu'il faut lire
    dans le journal Jeedom.
    """
    return "Onglet Présence (19) inaccessible, %s non relevés : %s" % (
        quoi,
        _motif_de_refus(eq_id) or "motif inconnu",
    )
