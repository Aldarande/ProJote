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

# Code de sortie renvoyé quand un secret chiffré par Jeedom n'a pas pu être
# déchiffré (SECURITY-AUDIT.md, findings L1 et L4). Le cas se produit quand la
# clé API du plugin a changé depuis l'enregistrement : la clé de chiffrement en
# dérive, l'ancien secret devient illisible. Rien ne sert de retenter, il faut
# ressaisir les identifiants pour que le secret soit rechiffré.
DECHIFFREMENT_EXIT_CODE = 9

# Code de sortie renvoyé quand Pronote a refusé les identifiants. Il manquait :
# la validation par identifiants se terminait sur 0 — donc « réussi » pour
# ProJote.ajax.php — alors qu'aucun compte n'avait été enregistré. L'interface
# annonçait une validation réussie, puis « Fichier token JSON introuvable ».
IDENTIFIANTS_REFUSES_EXIT_CODE = 10

# Code de sortie renvoyé quand l'ENT choisi n'existe pas dans pronotepy.
# La liste des ENT est figée dans la page de configuration ; pronotepy retire ou
# renomme les siens au fil des versions. Un choix devenu caduc était accepté en
# silence, la connexion se faisait alors SANS ENT, et l'utilisateur recevait une
# erreur incompréhensible venue des entrailles de la bibliothèque — « KeyError:
# 'dataSec' » sur un établissement protégé par EduConnect.
ENT_INCONNU_EXIT_CODE = 11

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


class DechiffrementImpossible(Exception):
    """Un secret chiffré par Jeedom n'a pas pu être déchiffré.

    Deux comportements se rejoignent ici, tous deux relevés par l'audit de
    sécurité (SECURITY-AUDIT.md, findings L1 et L4) :

    * le démon appelait ``exit(1)`` — un seul équipement au secret illisible
      emportait la collecte de tous les autres enfants de l'installation ;
    * la validation par identifiants renvoyait le **chiffré brut** en guise de
      mot de passe, qui partait tel quel vers Pronote : échec garanti, sans que
      rien n'en dise la cause.

    Les deux chemins lèvent désormais cette exception, que l'appelant nomme pour
    ce qu'elle est : le secret a été chiffré avec une autre clé API, il faut le
    ressaisir. Aucun autre équipement n'est affecté.
    """


class NoMobileTokenError(Exception):
    """Le serveur n'a délivré aucun jeton d'application mobile.

    Levée à la validation d'un compte, juste après une connexion réussie : les
    identifiants sont bons, mais ProJote n'a rien à enregistrer puisqu'il ne
    conserve jamais le mot de passe. Distinguée d'un échec d'identifiants pour
    que l'interface n'invite pas à recommencer une saisie déjà correcte.
    """


def est_onglet_non_accessible(exc):
    """L'erreur dit-elle qu'un onglet n'est pas ouvert à ce compte ?

    Le message vient du garde posé par ``pronote_compat`` : quand un onglet ne
    figure pas dans ``authorized_onglets``, la requête est refusée **avant**
    d'être envoyée. Ce n'est pas une panne — l'établissement n'a simplement pas
    ouvert cette fonctionnalité à ce compte, et cela ne changera pas d'un cycle
    à l'autre.

    Le distinguer permet de le journaliser pour ce qu'il est. Écrit en ERREUR,
    comme c'était le cas, il remplissait le journal d'une alerte horaire sur un
    état parfaitement normal, et noyait les vraies pannes.

    Args:
        exc: l'exception rattrapée par un collecteur.

    Returns:
        bool
    """
    return "non accessible pour ce compte" in str(exc)


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
