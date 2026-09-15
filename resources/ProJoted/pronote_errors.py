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
# Valeur 7 : les codes 3 à 6 sont déjà pris par les diagnostics du QR Code et
# des dépendances (cf. l'en-tête de QRConnect.py).
IP_SUSPENSION_EXIT_CODE = 7

# Code de sortie renvoyé quand le serveur ne délivre aucun jeton d'application
# mobile. ProJote ne conserve jamais le mot de passe : qu'on parte d'un QR Code
# ou d'identifiants, il échange la connexion contre deux jetons — principal et
# secours — et n'enregistre que ceux-là. Sans eux, il n'y a rien à écrire.
#
# Le serveur accepte pourtant l'appel JetonAppliMobile ; il répond seulement une
# charge vide, et pronotepy ne s'en aperçoit qu'en lisant le résultat, d'où un
# « KeyError: 'login' » qui ne désigne pas la cause.
#
# Aucune cause n'est affirmée ici : le seul cas observé est le site de
# démonstration d'Index Éducation, qui n'est pas représentatif d'un
# établissement réel. En déduire une règle serait prématuré.
NO_MOBILE_TOKEN_EXIT_CODE = 8

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


class SuspensionIP(BaseException):
    """Suspension d'IP rencontrée en cours de cycle : le cycle doit s'arrêter.

    Hérite volontairement de ``BaseException`` et non d'``Exception``.

    Les collecteurs du démon (emploi du temps, notes, absences…) rattrapent
    chacun ``Exception`` pour qu'un onglet en panne n'interrompe pas la collecte
    des autres. Une suspension d'IP n'est pas une panne d'onglet : elle vaut
    pour toutes les requêtes suivantes, et chaque tentative supplémentaire
    prolonge le blocage. Elle doit donc traverser ces filets sans être avalée,
    exactement comme ``KeyboardInterrupt`` traverse une boucle de traitement.

    Elle est levée par le garde posé sur ``pronotepy.ClientBase.post`` (voir
    ``ProJoted._installer_garde_suspension``) et rattrapée une seule fois, dans
    ``process_message``, qui ouvre alors la fenêtre de pause.
    """


class NoMobileTokenError(Exception):
    """Le serveur n'a délivré aucun jeton d'application mobile.

    Levée à la validation d'un compte, juste après une connexion réussie : les
    identifiants sont bons, mais ProJote n'a rien à enregistrer puisqu'il ne
    conserve jamais le mot de passe. Distinguée d'un échec d'identifiants pour
    que l'interface n'invite pas à recommencer une saisie déjà correcte.
    """


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


def is_missing_mobile_token(qr_code):
    """Dit si la réponse à une demande de jeton d'application mobile est vide.

    ``request_qr_code_data`` compose son résultat à partir de la charge renvoyée
    par la fonction PRONOTE ``JetonAppliMobile``. Un serveur qui n'offre pas
    l'application mobile accepte l'appel mais répond une charge vide : le
    dictionnaire ne porte alors que l'URL, reconstruite côté client. pronotepy
    ne s'en aperçoit qu'en lisant ``qr_code["login"]``, et lève un
    ``KeyError: 'login'`` qui ne dit rien de la cause.

    Args:
        qr_code: dictionnaire renvoyé par ``request_qr_code_data``.

    Returns:
        bool: True si le jeton est absent ou vide.
    """
    if not isinstance(qr_code, dict):
        return True
    return not qr_code.get("login") or not qr_code.get("jeton")


# Clés de l'enveloppe d'une réponse PRONOTE. pronotepy initialise
# `parametres_utilisateur` à {} (clients.py:136) et n'y met la réponse que si la
# connexion a réussi ; toute lecture ultérieure — ParentClient.__init__ fait
# `self.parametres_utilisateur["dataSec"]` — lève donc un KeyError sur l'une de
# ces clés quand l'authentification a été refusée.
_CLES_ENVELOPPE = ("dataSec", "dataNonSec", "data", "session")


def is_authentification_refusee(exc):
    """Dit si l'exception traduit une authentification refusée, sans plus.

    Le symptôme est un ``KeyError`` portant sur une clé d'enveloppe, levé bien
    après la cause : pronotepy journalise « login failed », rend False, puis
    trébuche sur le dictionnaire resté vide. Le refus lui-même n'est pas
    expliqué — un jeton périmé et un serveur qui refuse temporairement de
    répondre produisent exactement la même trace.

    D'où l'intérêt de la nommer : le message « Token invalide, regénérer le QR
    CODE » qui en découlait affirmait une cause sur deux possibles, et envoyait
    l'utilisateur rescanner un QR Code parfaitement valide.

    Args:
        exc: exception levée par pronotepy.

    Returns:
        bool: True si la trace est celle d'une authentification refusée.
    """
    if not isinstance(exc, KeyError):
        return False
    args = getattr(exc, "args", ())
    return bool(args) and args[0] in _CLES_ENVELOPPE
