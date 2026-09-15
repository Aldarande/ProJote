# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""
pronote_demo.py — Reconnaissance des serveurs de démonstration PRONOTE.

# Pourquoi une exception

ProJote se connecte normalement par jeton d'application mobile : la validation
du compte échange les identifiants contre deux jetons — principal et secours —
et seuls ceux-là sont conservés.

Le site de démonstration d'Index Éducation n'en délivre aucun. La fonction
PRONOTE ``JetonAppliMobile`` y répond 200 avec une charge vide, et
``request_qr_code_data`` ne rend que l'URL, qu'il reconstruit lui-même. Aucun
compte de démonstration ne pouvait donc être enregistré, alors que ce sont
justement les comptes qui permettent d'éprouver le plugin sans toucher aux
données scolaires d'un enfant réel.

Pour ces serveurs — et pour eux seuls — la connexion se fait par identifiants à
chaque cycle, sans jeton.

# Pourquoi c'est acceptable ici, et nulle part ailleurs

Les identifiants de la démonstration sont **publics** : Index Éducation les
pré-remplit dans son propre formulaire de connexion, et ils donnent accès à des
données fictives partagées par tous. Les conserver n'expose rien.

C'est pourquoi la reconnaissance porte sur l'**hôte** et non sur une case à
cocher : un utilisateur ne doit pas pouvoir, par mégarde ou par confort, faire
passer l'établissement de son enfant par ce chemin. La liste ci-dessous est la
seule porte d'entrée.

Ce module ne dépend que de la bibliothèque standard : il est importable par le
démon (``ProJoted.py``), par les scripts de validation (``LoginConnect.py``)
et par les tests unitaires.
"""

try:
    from urllib.parse import urlparse
except ImportError:  # python 2 — jamais utilisé ici, mais l'import ne doit pas casser
    from urlparse import urlparse  # type: ignore

# Hôtes reconnus comme serveurs de démonstration. Volontairement exhaustive et
# comparée à l'identique : aucun motif, aucun joker. Un établissement dont le
# sous-domaine commencerait par « demo » ne doit pas tomber dedans.
HOTES_DEMO = ("demo.index-education.net",)

# Identifiants publics de la démonstration, tels qu'Index Éducation les
# pré-remplit dans son formulaire. Donnés à titre documentaire : le plugin ne
# les injecte pas, l'utilisateur les saisit comme pour n'importe quel compte.
IDENTIFIANTS_PUBLICS = ("demonstration", "pronotevs")


def est_serveur_demo(url):
    """Dit si l'URL désigne un serveur de démonstration PRONOTE.

    Args:
        url: URL du portail, telle que saisie dans l'équipement ou stockée
            dans le jeton. Peut être vide, None, ou ne pas être une chaîne.

    Returns:
        bool: True uniquement pour un hôte de ``HOTES_DEMO``.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        hote = urlparse(url.strip()).hostname
    except Exception:
        return False
    if not hote:
        return False
    return hote.lower() in HOTES_DEMO


def est_compte_demo(message):
    """Dit si le message Jeedom décrit un équipement de démonstration.

    Deux conditions, toutes deux nécessaires : l'URL doit désigner un serveur de
    démonstration, et les identifiants doivent être présents. Sans eux il n'y a
    rien à tenter, et mieux vaut laisser le chemin normal produire son message
    d'erreur habituel que d'inventer un cas particulier de plus.

    L'URL est cherchée dans « url » — ce que l'utilisateur a saisi — puis dans
    « TokenUrl », qu'une validation réussie a pu renseigner.

    Args:
        message: dictionnaire reçu du socket Jeedom.

    Returns:
        bool: True si la connexion doit se faire par identifiants.
    """
    if not isinstance(message, dict):
        return False
    url = message.get("url") or message.get("TokenUrl") or ""
    if not est_serveur_demo(url):
        return False
    return bool((message.get("login") or "").strip()) and bool(
        (message.get("password") or "").strip()
    )
