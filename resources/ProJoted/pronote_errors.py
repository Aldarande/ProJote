# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""
pronote_errors.py — Reconnaissance des erreurs « adresse IP suspendue ».

Pronote applique une limite de débit par adresse IP. Quand elle est dépassée,
le serveur ne renvoie plus la page de connexion mais une page d'avertissement,
et pronotepy lève alors :

  * ``PronoteAPIError("Your IP address is suspended.")``
    (``pronoteAPI._Communication._parse_html``), ou
  * ``PronoteAPIError`` avec ``pronote_error_code == 25``
    (« Exceeded max authorization requests. Please wait before retrying... »).

Aucune exception dédiée n'existe côté pronotepy : la détection se fait donc sur
le code d'erreur Pronote quand il est disponible, sinon sur le texte du message.

Ce module ne dépend que de la bibliothèque standard : il est importable aussi
bien par le démon (``ProJoted.py``) que par les scripts de validation de compte
(``LoginConnect.py``, ``QRConnect.py``) et par les tests unitaires.
"""

# Code de sortie renvoyé par LoginConnect.py / QRConnect.py quand la connexion
# a échoué parce que Pronote a suspendu l'adresse IP. Le PHP (ProJote.ajax.php)
# s'en sert pour afficher un message explicite plutôt qu'une erreur générique.
IP_SUSPENSION_EXIT_CODE = 4

# Codes d'erreur Pronote considérés comme une limitation de débit.
# 25 = « Exceeded max authorization requests. Please wait before retrying... »
IP_SUSPENSION_PRONOTE_CODES = (25,)

# Fragments recherchés (en minuscules) dans le message d'erreur. On couvre le
# texte anglais de pronotepy et les formulations françaises renvoyées par
# certaines instances Pronote.
_IP_SUSPENSION_MARKERS = (
    "ip address is suspended",
    "adresse ip est provisoirement suspendue",
    "adresse ip est suspendue",
    "suspension temporaire de l",
    "exceeded max authorization requests",
)

# Message affiché à l'utilisateur (logs Jeedom, centre de messages, AJAX).
IP_SUSPENSION_MESSAGE = (
    "Pronote a temporairement suspendu l'adresse IP de cette installation "
    "(trop de connexions en peu de temps)"
)


def is_ip_suspension_error(exc):
    """Indique si l'exception correspond à une suspension d'IP par Pronote.

    Args:
        exc: exception levée par pronotepy (ou n'importe quel objet).

    Returns:
        bool: True si Pronote a suspendu l'adresse IP / limité le débit.
    """
    if exc is None:
        return False

    code = getattr(exc, "pronote_error_code", None)
    if code in IP_SUSPENSION_PRONOTE_CODES:
        return True

    haystack = " ".join(
        str(part).lower()
        for part in (exc, getattr(exc, "pronote_error_msg", ""))
        if part
    )
    return any(marker in haystack for marker in _IP_SUSPENSION_MARKERS)


def ip_suspension_reason(exc=None):
    """Retourne un libellé court expliquant la suspension, pour les logs.

    Args:
        exc: exception d'origine (facultative).

    Returns:
        str: message prêt à être affiché.
    """
    detail = str(exc).strip() if exc is not None else ""
    if not detail:
        return IP_SUSPENSION_MESSAGE
    return "%s — détail : %s" % (IP_SUSPENSION_MESSAGE, detail)
