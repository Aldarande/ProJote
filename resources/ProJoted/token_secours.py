# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""
token_secours.py — Filet de sécurité sur le jeton de reconnexion PRONOTE.

# Le problème

PRONOTE renouvelle le ``jetonConnexionAppliMobile`` à **chaque**
authentification, et n'accepte que le dernier émis. Mesuré sur une instance
2026.2.5 :

    - le jeton change à chaque authentification ;
    - un jeton déjà consommé est refusé sèchement (``PronoteAPIError``) ;
    - une session applicative ne peut pas émettre un second QR Code
      (``JetonAppliMobile`` renvoie une réponse sans ``jeton`` ni ``login``),
      donc impossible d'enregistrer un appareil de secours depuis le démon.

Conserver un historique de jetons ne servirait donc à rien, et le second
appareil n'est pas accessible. Le seul filet possible est de **ne jamais
perdre le dernier jeton émis**.

Or pronotepy se ré-authentifie à chaque requête : un cycle de collecte compte
une quarantaine de rotations. Entre la première authentification et l'écriture
en base par Jeedom en fin de cycle, il s'écoule une trentaine de secondes
pendant lesquelles un arrêt du démon, une coupure réseau ou un échec
d'écriture perdrait définitivement le compte — l'utilisateur devrait rescanner
un QR Code.

# Le mécanisme

On enregistre sur disque, **à chaque authentification réussie**, les
identifiants de reconnexion les plus récents. L'écriture est atomique et le
fichier n'est lisible que par son propriétaire.

Quand la reconnexion échoue avec le jeton fourni par Jeedom, le démon relit ce
fichier et retente : c'est le cas où la base contient un jeton périmé alors que
le disque a le bon. La réparation est silencieuse, sans intervention de
l'utilisateur, et le jeton rétabli redescend vers Jeedom en fin de cycle.

Ce filet ne couvre pas la perte du fichier ET de la base : dans ce cas seul un
nouveau QR Code peut relancer la chaîne.

Le fichier vit dans le dossier de données de l'équipement : sa suppression est
déjà assurée par ``preRemove()`` côté PHP, qui efface tout le dossier.
"""

import json
import logging
import os

_installe = False

NOM_FICHIER = "token_secours.json"

# Un incident réseau ou un serveur momentanément fermé n'invalide pas le jeton :
# le rejouer avec celui de secours ne servirait à rien et brûlerait la réserve.
# Cas vécu : « Your IP address is suspended. » après trop de connexions.
_MARQUEURS_TRANSITOIRES = (
    "suspended",
    "suspendue",
    "timeout",
    "timed out",
    "connection",
    "unreachable",
    "unavailable",
    "indisponible",
    "momentan",
    "temporarily",
    "network",
)

# Signes que Pronote a bel et bien refusé le jeton : c'est là que le fichier de
# secours a une chance d'aider. « dataSec » couvre le cas où l'authentification
# est refusée sans exception dédiée : pronotepy échoue ensuite en lisant la
# réponse d'un login qui n'a pas eu lieu.
_MARQUEURS_AUTH = (
    "expir",
    "invalid",
    "refus",
    "unauthorized",
    "authenticat",
    "credentials",
    "datasec",
    "donneessec",
)


def erreur_de_jeton(exception):
    """Le jeton est-il en cause, ou s'agit-il d'un incident passager ?

    ``None`` signifie « Pronote a refusé la connexion sans lever d'exception » :
    le jeton est alors en cause.
    """
    if exception is None:
        return True
    message = str(exception).lower()
    if any(marqueur in message for marqueur in _MARQUEURS_TRANSITOIRES):
        return False
    if type(exception).__name__ in ("ExpiredObject", "CryptoError", "QRCodeDecryptError"):
        return True
    return any(marqueur in message for marqueur in _MARQUEURS_AUTH)


def _chemin(datadir, eq_id):
    return os.path.join(str(datadir), str(eq_id), NOM_FICHIER)


def enregistrer(datadir, eq_id, credentials):
    """Écrit les identifiants de reconnexion de façon atomique.

    L'écriture passe par un fichier temporaire renommé ensuite : une coupure en
    plein milieu laisse l'ancien contenu intact plutôt qu'un fichier tronqué.
    """
    if not credentials or not credentials.get("password"):
        return
    chemin = _chemin(datadir, eq_id)
    try:
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        temporaire = chemin + ".tmp"
        with open(temporaire, "w", encoding="utf-8") as f:
            json.dump(credentials, f)
            # Sans fsync, le renommage peut être visible avant que les données
            # ne soient réellement sur le disque : une coupure de courant
            # laisserait un fichier vide, et le compte serait perdu.
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporaire, 0o600)
        os.replace(temporaire, chemin)
    except Exception as e:
        # Le filet de sécurité ne doit jamais interrompre une collecte.
        logging.warning("token_secours :: écriture impossible (%s) : %s", chemin, e)


def charger(datadir, eq_id):
    """Relit les identifiants de secours, ou None s'il n'y en a pas."""
    chemin = _chemin(datadir, eq_id)
    try:
        with open(chemin, encoding="utf-8") as f:
            credentials = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        logging.warning("token_secours :: lecture impossible (%s) : %s", chemin, e)
        return None
    if not isinstance(credentials, dict) or not credentials.get("password"):
        return None
    return credentials


def installer(datadir, eq_id_courant):
    """Enregistre le jeton après chaque authentification réussie.

    ``eq_id_courant`` est un appelable renvoyant l'identifiant de l'équipement
    en cours de traitement : le démon traite les équipements l'un après l'autre,
    et le jeton doit être rangé dans le dossier du bon.

    Idempotent : le correctif n'est posé qu'une fois.
    """
    global _installe
    if _installe:
        return

    try:
        from pronotepy import clients
    except Exception as e:
        logging.warning("token_secours :: non installé (%s) : %s", type(e).__name__, e)
        return

    _login_origine = clients.ClientBase._login

    def _login_avec_sauvegarde(self):
        connecte = _login_origine(self)
        if not connecte:
            return connecte
        # Seuls les modes sans mot de passe reposent sur un jeton tournant.
        if getattr(self, "login_mode", None) not in ("token", "qr_code"):
            return connecte
        eq_id = eq_id_courant()
        if not eq_id:
            return connecte
        try:
            enregistrer(datadir, eq_id, self.export_credentials())
        except Exception as e:
            logging.warning("token_secours :: export impossible : %s", e)
        return connecte

    clients.ClientBase._login = _login_avec_sauvegarde
    _installe = True
    logging.debug("token_secours :: sauvegarde du jeton à chaque authentification active")
