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
    """Pronote refuse-t-il l'accès à l'onglet Présence, faute de droit ?

    « Accès refusé » et « La page a expiré » étaient traités ici comme une même
    impasse. Ce sont deux choses opposées, et les confondre coûtait cher :

    ===========================  ==========================  =================
    Message PRONOTE              Ce que c'est                Bonne réponse
    ===========================  ==========================  =================
    ``Accès refusé``             un droit non accordé        s'abstenir, c'est
                                                             définitif
    ``La page a expiré``         la session est morte        relire les objets
                                                             et réessayer
    ===========================  ==========================  =================

    Une session expirée prise pour un refus de droit fait abandonner les quatre
    collectes de l'onglet pour tout le cycle, là où relire les périodes aurait
    suffi. Relevé chez un bêta-testeur le 19 septembre 2026 : quatre onglets
    vides sur un simple « La page a expiré ! (11) ».
    """
    message = str(exception).lower()
    return "accès refusé" in message or "acces refuse" in message


def session_expiree(exception):
    """La session PRONOTE est-elle morte ?

    PRONOTE est une application à état : les identifiants de ressources — de
    membre comme de période — ne valent que pour la session qui les a émis. En
    présenter un issu d'une session close fait répondre « La page a expiré »,
    sous des codes qui varient (G=8 « (1) », G=20 « (11) »), que pronotepy ne
    nomme pas — d'où les « Unknown error from pronote: 20 » du journal.

    pronotepy réserve ``ExpiredObject`` (erreur G=22) au cas où il le reconnaît
    lui-même ; on l'accepte des deux façons, par le type comme par le message.
    """
    if type(exception).__name__ == "ExpiredObject":
        return True
    message = str(exception).lower()
    return "page a expiré" in message or "page a expire" in message


def _presence_deja_refusee(eq_id):
    return str(eq_id) in _presence_refusee


def _motif_de_refus(eq_id):
    """Message Pronote du refus retenu pour cet équipement, ou None.

    Sert à remplir la clé ``error`` des collectes qui s'abstiennent : elles
    n'ont pas vu l'erreur passer, mais doivent la rapporter tout de même.
    """
    return _presence_refusee.get(str(eq_id))


# Équipements pour lesquels une reprise après expiration a déjà été tentée sur
# le cycle en cours. Une seule par cycle, et c'est délibéré : chaque reprise
# passe par une authentification complète, et leur accumulation a déjà valu une
# suspension d'adresse IP par PRONOTE — 415 authentifications en quelques
# secondes le 13 septembre 2026, suspension dont la durée double à chaque
# récidive. Mieux vaut un cycle sans absences qu'une adresse bloquée une heure.
_reprise_tentee = set()


def reprise_deja_tentee(eq_id):
    """Une reprise a-t-elle déjà été tentée pour cet équipement sur ce cycle ?"""
    return str(eq_id) in _reprise_tentee


def noter_reprise(eq_id):
    """Retient qu'on vient de dépenser la reprise du cycle."""
    _reprise_tentee.add(str(eq_id))


def _oublier_refus_presence(eq_id):
    """Ouvre un nouveau cycle pour cet équipement : le refus est réessayé.

    La portée est volontairement courte — le refus peut n'être que temporaire
    (début d'année, page non encore initialisée) et un droit accordé
    entre-temps doit être pris en compte dès le cycle suivant.
    """
    _presence_refusee.pop(str(eq_id), None)
    _reprise_tentee.discard(str(eq_id))


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
    return "Onglet Présence (19) inaccessible, rien n'a pu être relevé pour %s : %s" % (
        quoi,
        _motif_de_refus(eq_id) or "motif inconnu",
    )
