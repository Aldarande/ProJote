# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
#
# This file is part of ProJote.
#
# ProJote is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# ProJote is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public
# License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

### Sources ###
# API WRAPPER PronotePy :  https://github.com/bain3/pronotepy
# API WRAPPER Documentation : https://pronotepy.readthedocs.io/en/stable/
# Plugin Jeedom Dev : https://doc.jeedom.com/fr_FR/dev/
# Plugin Jeedom Deamon Dev : https://doc.jeedom.com/fr_FR/dev/daemon_plugin
# Pluugin Jeedom Template : https://github.com/jeedom/plugin-template
### ###


import contextlib

try:
    import logging
    import sys
    # Niveau initial volontairement WARNING : entre l'import et l'appel à
    # jeedom_utils.set_log_level(--loglevel) dans _run_daemon(), rien de
    # sensible/verbeux ne doit partir sur stdout (P2a, audit sécurité).
    # Le niveau définitif est reconfiguré par set_log_level() selon --loglevel.
    logging.basicConfig(
        level=logging.WARNING,
        format="[%(asctime)-15s][%(levelname)s] : %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    import os
    import time
    import datetime
    import traceback
    import signal
    import json
    import argparse
    import base64
    import importlib
    import requests
    import threading

    # import du Plugin Principal
    import pronotepy
    from pronotepy.ent import *
    import pronotepy.dataClasses

    # Correctifs de compatibilité pronotepy (voir pronote_compat.py) :
    # PRONOTE >= 2026.2.5 ne chiffre plus le challenge d'authentification,
    # ce qui fait échouer TOUS les modes de connexion de pronotepy 2.15.6.
    import pronote_compat

    pronote_compat.apply()

    import token_secours

    # Monkey patch : Correction à la volée pour gérer l'absence de noteMax/noteMin/estBonus
    _original_grade_init = pronotepy.dataClasses.Grade.__init__

    def _patched_grade_init(self, json_data):
        if "noteMax" not in json_data:
            json_data["noteMax"] = {"V": ""}
        if "noteMin" not in json_data:
            json_data["noteMin"] = {"V": ""}
        if "coefficient" not in json_data:
            json_data["coefficient"] = {"V": "1"}
        if "commentaire" not in json_data:
            json_data["commentaire"] = {"V": ""}
        if "estBonus" not in json_data:
            json_data["estBonus"] = {"V": False}
        if "estFacultatif" not in json_data:
            json_data["estFacultatif"] = {"V": False}
        if "estRamenerSur20" not in json_data:
            json_data["estRamenerSur20"] = {"V": False}
        _original_grade_init(self, json_data)

    pronotepy.dataClasses.Grade.__init__ = _patched_grade_init

    # Monkey patch : html_parse — remplace <br> par un espace avant de supprimer les balises
    # Sans ce patch, "Faire ex 1<br>Apprendre la leçon" devient "Faire ex 1Apprendre la leçon"
    import re as _re
    from html import unescape as _unescape

    @staticmethod
    def _patched_html_parse(html_text: str) -> str:
        if not html_text:
            return ""
        text = _re.sub(r"<br\s*/?>", " ", html_text, flags=_re.IGNORECASE)
        text = _re.sub(r"<[^>]+>", "", text)
        text = _unescape(text)
        text = _re.sub(r"  +", " ", text).strip()
        return text

    pronotepy.dataClasses.Util.html_parse = _patched_html_parse

    from LoginConnect import writedataPronotepy

    # Détection des suspensions d'IP par Pronote (module local, stdlib uniquement).
    from pronote_demo import est_compte_demo
    import cadence
    import collecteurs  # noqa: F401 - façade
    from collecteurs import (  # noqa: F401 - façade
        DEVOIRS_FENETRE_DEFAUT,
        DEVOIRS_FENETRE_MAX,
        Emploidutemps,
        _fenetre_devoirs,
        absences,
        devoirs,
        evaluations,
        evenements_vie_scolaire,
        ical,
        menus,
        messages,
        notes,
        notifications,
        process_homework,
        punitions,
        retards,
    )

    # ── Modules extraits du démon en v1.6.0 ──────────────────────────────────
    #
    # Les noms sont réimportés ici plutôt que d'être appelés par leur module :
    # ProJoted reste la façade du démon. Les collecteurs y font référence sans
    # préfixe, et les tests passent par la fixture `daemon`, qui est ce module.
    # Les faire disparaître d'ici obligerait à réécrire les appels et les tests
    # pour un découpage qui, lui, ne change aucun comportement.
    #
    # Certains ne sont donc pas utilisés par le code restant de ce fichier :
    # c'est le propre d'une réexportation, d'où les noqa.
    import analyse_scolaire  # noqa: F401 - façade
    import format_pronote  # noqa: F401 - façade
    import periodes_scolaires  # noqa: F401 - façade
    import presence_pronote  # noqa: F401 - façade
    from analyse_scolaire import (  # noqa: F401 - façade
        DS_HORIZON_JOURS,
        compute_deltas,
        compute_moyenne_generale,
        detect_next_evaluations,
        detect_subject_trends,
        format_new_devoir_label,
        format_new_note_label,
    )
    from format_pronote import (  # noqa: F401 - façade
        _information_content,
        _menu_labels,
        _menu_to_html_row,
        _menu_to_text,
        _safe_attr,
        _truncate,
        build_cours_data,
        build_menu_data,
        cours_affiche_from_lesson,
    )
    from periodes_scolaires import _periodes_couvrantes, periodes  # noqa: F401
    from presence_pronote import (  # noqa: F401 - façade
        _noter_refus_presence,
        _presence_deja_refusee,
        _presence_refusee,
        _refus_de_presence,
    )
    from pronote_errors import (
        SuspensionIP,
        ip_suspension_reason,
        is_authentification_refusee,
        is_ip_suspension_error,
    )

except ImportError as e:
    logging.error("Error: importing module lig.%s - %s ", e.__traceback__.tb_lineno, e)
    sys.exit(1)

try:
    from jeedom.jeedom import *
except ImportError as e:
    logging.error(
        "Error: importing module jeedom.jeedom lig.%s - %s ",
        e.__traceback__.tb_lineno,
        e,
    )
    sys.exit(1)


# Dictionnaire global pour tracker les tentatives échouées de connexion
# Utilise pour implémenter un "circuit breaker" et éviter les boucles infinies
failed_attempts = {}  # Format: {eqLogicId: {"count": N, "timestamp": time.time()}}
_failed_attempts_lock = threading.Lock()

# ── File d'attente sérialisée ────────────────────────────────────────────────
# Un seul thread worker traite les messages un par un (séquentiellement).
# _queued_eq évite d'enqueuer deux fois le même équipement.
import queue as _queue_module

_work_queue = _queue_module.Queue()
_queued_eq = set()  # eqLogicId en attente ou en cours de traitement
_queued_eq_lock = threading.Lock()
_worker_thread = None  # Thread worker unique (démarré au premier message)

# Watchdog : si le worker bloque plus de N secondes sur un équipement, WARNING
_WORKER_TIMEOUT = 120  # secondes
_worker_eq_id = None  # équipement actuellement traité


def _equipement_en_cours():
    """Identifiant de l'équipement en cours de traitement.

    Le démon traite les équipements l'un après l'autre et le sait seul. Deux
    modules en ont besoin sans devoir dépendre du démon : token_secours, pour
    ranger le jeton dans le bon dossier, et collecteurs, pour mémoriser un refus
    de l'onglet Présence au nom du bon équipement. Tous deux le reçoivent par
    injection plutôt que par import.
    """
    with _worker_state_lock:
        return _worker_eq_id


# Injecté dès l'import, et non au démarrage du démon : les collecteurs sont
# éprouvés sans démon, le câblage doit être vrai là aussi.
collecteurs.installer(_equipement_en_cours)
_worker_eq_start = None  # horodatage de début du traitement en cours
_worker_state_lock = threading.Lock()

# Variable globale pour stocker les info de connexion Jeedom
_callback_url = None
_apikey_global = None

# Valeurs par défaut des paramètres du démon. Elles sont surchargées par les
# arguments de la ligne de commande dans le bloc de démarrage (if __name__ == "__main__").
# Les définir ici rend le module importable (tests unitaires) sans démarrer le démon.
_socket_host = "localhost"
_log_level = "error"
_callback = ""
_apikey = ""
_pidfile = "/tmp/ProJoted.pid"
_cycle = 0.3
_socket_port = 55369
_data_dir = "/var/www/html/plugins/ProJote/data"


# ── Masquage des secrets dans les journaux ───────────────────────────────────
# Le message que Jeedom envoie au démon porte les identifiants Pronote en clair :
# TokenUsername, TokenPassword, TokenId, TokenUuid. Il était journalisé entier à
# chaque cycle, deux fois — par le framework Jeedom (jeedom.py, « Message read
# from socket », en INFO) et par read_socket() ici même, en DEBUG. Or le mode
# debug est précisément celui qu'on active pour diagnostiquer un problème de
# connexion : les journaux transmis pour demander de l'aide contenaient donc les
# secrets du compte.
#
# Le filtre est posé sur les handlers plutôt que sur les appels : il couvre les
# deux sites, dont celui du framework Jeedom — code vendoré, non maintenu ici
# (cf. ruff.toml) — et tout site futur, sans avoir à les recenser.
_CLES_SECRETES = (
    "TokenPassword",
    "TokenUsername",
    "TokenId",
    "TokenUuid",
    "jetonConnexionAppliMobile",
    "jeton",
    "password",
    "login",
)

# Reconnaît « "clé": "valeur" » comme « 'clé': 'valeur' » : le message traverse
# les journaux tantôt en JSON (framework Jeedom), tantôt en repr Python (démon).
_MOTIF_SECRET = _re.compile(
    r"(?P<avant>['\"](?:%s)['\"]\s*:\s*)['\"][^'\"]*['\"]" % "|".join(_CLES_SECRETES)
)


class _FiltreSecrets(logging.Filter):
    """Remplace la valeur des clés sensibles par « *** » dans tout message."""

    def filter(self, record):
        try:
            texte = record.getMessage()
        except Exception:
            # Un enregistrement mal formé ne doit pas faire disparaître la ligne :
            # mieux vaut la laisser passer telle quelle que perdre la trace.
            return True
        masque = _MOTIF_SECRET.sub(r'\g<avant>"***"', texte)
        if masque != texte:
            # msg pré-formaté et args vidés : sinon logging réappliquerait les
            # arguments d'origine, secrets compris, au moment de l'émission.
            record.msg = masque
            record.args = ()
        return True


def installer_filtre_secrets():
    """Pose le filtre sur les handlers du logger racine (idempotent)."""
    racine = logging.getLogger()
    for handler in racine.handlers:
        if not any(isinstance(f, _FiltreSecrets) for f in handler.filters):
            handler.addFilter(_FiltreSecrets())


def send_jeedom_message(message, message_type="error"):
    """
    Envoie un message au centre de messages Jeedom.

    Args:
        message: Le texte du message à afficher
        message_type: Type de message ('error', 'warning', 'info')
    """
    global _callback_url, _apikey_global

    if not _callback_url or not _apikey_global:
        logging.warning("URL Jeedom ou API key non disponible pour envoyer un message")
        return False

    try:
        # Construire l'URL pour ajouter un message au centre de messages
        # _callback_url format: http://172.17.0.2:80/plugins/ProJote/core/php/jeeProJote.php
        # Target URL: http://172.17.0.2:80/plugins/message/core/php/message.action.php

        # Extraire l'URL de base (schéma + host)
        # Exemples: http://172.17.0.2:80 ou http://localhost
        url_parts = _callback_url.split("/")
        # Récupérer schéma:// + host + port
        base_url = "/".join(url_parts[:3])  # http://172.17.0.2:80

        # Construire le URL du centre de messages
        message_action_url = f"{base_url}/plugins/message/core/php/message.action.php"

        params = {
            "apikey": _apikey_global,
            "action": "add",
            "message": message,
            "type": message_type,
        }

        logging.debug(f"Envoi du message Jeedom vers: {message_action_url}")

        # POST avec l'apikey dans le corps : en GET, la clé apparaissait en clair
        # dans les access logs du serveur web (P2b, audit sécurité). Le endpoint
        # Jeedom lit init()/$_REQUEST, qui accepte indifféremment GET et POST.
        response = requests.post(message_action_url, data=params, timeout=5)

        if response.status_code == 200:
            logging.info(f"Message Jeedom envoyé avec succès: {message[:50]}...")
            return True
        else:
            logging.warning(
                f"Erreur lors de l'envoi du message Jeedom: {response.status_code}"
            )
            return False

    except Exception as e:
        logging.warning(f"Erreur lors de l'envoi du message Jeedom: {e}")
        return False


# ── Suspension temporaire de l'adresse IP par Pronote ────────────────────────
# Pronote limite le nombre de connexions par adresse IP. Au-delà, il suspend
# l'IP : pronotepy lève « Your IP address is suspended. » ou l'erreur 25
# (« Exceeded max authorization requests »). Continuer à interroger Pronote
# pendant ce blocage ne fait que le prolonger.
#
# On ouvre donc une FENÊTRE DE PAUSE GLOBALE (et non par équipement) : l'IP est
# commune à toute la box, un seul compte suspendu suspend tous les autres. Tant
# que la fenêtre court, le démon ne contacte plus Pronote du tout.
#
# La durée double à chaque nouvelle suspension (30 min → 1 h → 2 h…, plafond
# 6 h), puis repart à la durée de base après 24 h sans incident. La fenêtre est
# persistée sur disque : sans cela, un redémarrage du démon relancerait les
# requêtes immédiatement et prolongerait la suspension.
_IP_SUSPENSION_BASE_DELAY = 1800  # 30 min pour la 1re suspension
_IP_SUSPENSION_MAX_DELAY = 21600  # plafond : 6 h
_IP_SUSPENSION_LEVEL_RESET = 86400  # 24 h sans suspension → retour à 30 min

_ip_suspension_lock = threading.Lock()
# until : fin de la fenêtre (epoch) — level : nombre de suspensions consécutives
# last  : horodatage de la dernière suspension (sert au retour au niveau 1)
_ip_suspension = {"until": 0.0, "level": 0, "last": 0.0}


def _ip_suspension_file():
    """Chemin du fichier de persistance de la fenêtre de pause."""
    return os.path.join(_data_dir, "ip_suspension.json")


def _save_ip_suspension():
    """Écrit la fenêtre courante sur disque. À appeler sous _ip_suspension_lock."""
    try:
        path = _ip_suspension_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(_ip_suspension, f)
    except Exception as e:
        logging.warning("Écriture de l'état de suspension d'IP impossible : %s", e)


def load_ip_suspension():
    """Recharge la fenêtre de pause depuis le disque au démarrage du démon."""
    try:
        with open(_ip_suspension_file(), "r") as f:
            data = json.load(f)
        with _ip_suspension_lock:
            _ip_suspension["until"] = float(data.get("until", 0) or 0)
            _ip_suspension["level"] = int(data.get("level", 0) or 0)
            _ip_suspension["last"] = float(data.get("last", 0) or 0)
            remaining = _ip_suspension["until"] - time.time()
        if remaining > 0:
            logging.warning(
                "Suspension d'IP Pronote toujours active au démarrage du démon : "
                "aucune requête ne sera envoyée avant %s (%d min).",
                datetime.datetime.fromtimestamp(
                    time.time() + remaining
                ).strftime("%H:%M"),
                int(remaining // 60) + 1,
            )
    except FileNotFoundError:
        pass
    except Exception as e:
        logging.warning("Lecture de l'état de suspension d'IP impossible : %s", e)


def ip_suspension_remaining():
    """Secondes restantes avant la fin de la fenêtre de pause (0 si aucune)."""
    with _ip_suspension_lock:
        remaining = _ip_suspension["until"] - time.time()
    return int(remaining) if remaining > 0 else 0


def notify_ip_suspension(eqLogicId, until, delay, level, exc=None):
    """Informe Jeedom de la fenêtre de pause.

    Le PHP (jeeProJote.php) enregistre la fenêtre, alimente le centre de
    messages et met à jour la commande « Statut_Connexion ».
    """
    if not eqLogicId:
        return
    try:
        jeedom_com.send_change_immediate(
            {
                "CmdId": eqLogicId,
                "connection_status": "ip_suspended",
                "error": ip_suspension_reason(exc),
                "ip_suspended_until": int(until),
                "ip_suspended_delay": int(delay),
                "ip_suspended_level": int(level),
            }
        )
    except Exception as e:
        logging.warning(
            "Notification de suspension d'IP non transmise à Jeedom : %s", e
        )


def trigger_ip_suspension(eqLogicId="", exc=None):
    """Ouvre la fenêtre de pause après une suspension d'IP détectée.

    Si une fenêtre est déjà ouverte (un second équipement tombe sur la même
    suspension), on ne ré-escalade pas la durée : on se contente de rappeler
    l'échéance en cours à Jeedom.

    Args:
        eqLogicId: équipement à l'origine de la détection (pour la notification)
        exc: exception pronotepy d'origine

    Returns:
        int: durée restante de la fenêtre, en secondes.
    """
    now = time.time()
    with _ip_suspension_lock:
        already_open = _ip_suspension["until"] > now
        if not already_open:
            # 24 h sans suspension → on repart de la durée de base.
            if now - _ip_suspension["last"] > _IP_SUSPENSION_LEVEL_RESET:
                _ip_suspension["level"] = 0
            _ip_suspension["level"] += 1
            delay = min(
                _IP_SUSPENSION_BASE_DELAY * (2 ** (_ip_suspension["level"] - 1)),
                _IP_SUSPENSION_MAX_DELAY,
            )
            _ip_suspension["until"] = now + delay
            _ip_suspension["last"] = now
            _save_ip_suspension()
        until = _ip_suspension["until"]
        level = _ip_suspension["level"]
        delay = int(until - now)

    if not already_open:
        logging.error(
            "%s. Toutes les requêtes Pronote sont suspendues pendant %d min "
            "(reprise à %s) pour laisser le blocage se lever.",
            ip_suspension_reason(exc),
            delay // 60,
            datetime.datetime.fromtimestamp(until).strftime("%H:%M"),
        )
    notify_ip_suspension(eqLogicId, until, delay, level, exc)
    return delay


_garde_suspension_installee = False


def _installer_garde_suspension():
    """Empêche pronotepy de se ré-authentifier en boucle sur une IP suspendue.

    Toute erreur Pronote qui n'est pas ``ExpiredObject`` pousse pronotepy à
    jeter la session et à en rouvrir une (``ClientBase.post`` →  ``refresh()``),
    ce qui commence par un GET de la page de connexion — précisément la requête
    qui renvoie la page « adresse IP suspendue ». L'exception remonte ensuite au
    collecteur, qui l'avale, et le collecteur suivant recommence : une vingtaine
    de requêtes émises pendant le blocage qu'on cherche justement à laisser
    retomber.

    Le garde transforme cette erreur en ``SuspensionIP``, qui hérite de
    ``BaseException`` et traverse donc les ``except Exception`` des collecteurs
    jusqu'à ``process_message``. Le cycle s'arrête au premier échec au lieu de
    parcourir les douze collecteurs.

    ``post()`` est le seul chemin vers le réseau une fois la session ouverte
    (``dataClasses`` l'appelle vingt-six fois), d'où ce point d'accroche unique.
    ``ParentClient`` redéfinit la méthode — sans le garde anti-récursion de
    ``ClientBase``, d'ailleurs — et doit donc être traité à part.

    Idempotent et silencieux en cas d'échec : comme ``pronote_compat.apply()``,
    ce correctif s'appuie sur des détails internes de pronotepy. Si une version
    future les déplace, on veut le comportement d'origine, pas un démon qui
    refuse de démarrer.
    """
    global _garde_suspension_installee
    if _garde_suspension_installee:
        return

    def _garder(post_origine):
        def post(self, *args, **kwargs):
            try:
                return post_origine(self, *args, **kwargs)
            except SuspensionIP:
                raise
            except BaseException as e:
                if is_ip_suspension_error(e):
                    logging.error(
                        "%s. Cycle interrompu immédiatement : poursuivre les "
                        "collectes rallongerait la suspension.",
                        ip_suspension_reason(e),
                    )
                    raise SuspensionIP(ip_suspension_reason(e)) from e
                raise

        post.__doc__ = getattr(post_origine, "__doc__", None)
        post._projote_garde_suspension = True
        return post

    try:
        cibles = [pronotepy.ClientBase]
        # ParentClient redéfinit post() : l'hériter ne suffit pas.
        if pronotepy.ParentClient.post is not pronotepy.ClientBase.post:
            cibles.append(pronotepy.ParentClient)
        for classe in cibles:
            if not getattr(classe.post, "_projote_garde_suspension", False):
                classe.post = _garder(classe.post)
    except Exception as e:
        logging.warning(
            "Garde « suspension d'IP » non installé (%s: %s) : un blocage en "
            "cours de cycle sera détecté au cycle suivant seulement.",
            type(e).__name__,
            e,
        )
        return

    _garde_suspension_installee = True
    logging.debug("Garde « suspension d'IP » installé sur pronotepy.post.")


def clear_ip_suspension():
    """Referme la fenêtre de pause après une connexion réussie.

    Returns:
        bool: True si une fenêtre était ouverte et vient d'être refermée.
    """
    with _ip_suspension_lock:
        if not _ip_suspension["until"]:
            return False
        _ip_suspension["until"] = 0.0
        _save_ip_suspension()
    logging.info(
        "Connexion à Pronote rétablie : fin de la pause pour suspension d'IP."
    )
    return True


def verifdossier(chemin_dossier):
    """
    Vérifie si un dossier existe, sinon le crée.

    Args:
        chemin_dossier (str): Le chemin du dossier à vérifier/créer.

    Returns:
        bool: True si le dossier existe ou a été créé avec succès, False sinon.
    """
    try:
        # Créer le dossier s'il n'existe pas, sinon ne rien faire
        os.makedirs(chemin_dossier, exist_ok=True)
        logging.info(f"Dossier vérifié ou créé avec succès : {chemin_dossier}")
        return True
    except Exception as e:
        logging.error(f"Erreur lors de la vérification ou création du dossier : {e}")
        return False


def Checkeleve(client, CmdId):
    try:
        # `_selected_child` n'existe que sur ParentClient : pronotepy ne
        # l'assigne nulle part ailleurs. L'accès direct levait donc une
        # AttributeError à chaque cycle sur un compte élève, avalée par le
        # `except` ci-dessous et journalisée comme une panne. Il n'y en a pas :
        # un compte élève n'a pas d'enfant à sélectionner, donc rien à vérifier.
        enfant = getattr(client, "_selected_child", None)
        if not enfant:
            logging.debug(
                "Compte sans enfant sélectionné (compte élève) : rien à vérifier."
            )
            return False
        else:
            chemin_fichier = _data_dir
            if not os.path.exists(chemin_fichier):
                logging.error(f"Le fichier {chemin_fichier} n'existe pas.")
                return False
            with open(f"{chemin_fichier}/{CmdId}/enfant.ProJote.json.txt", "r") as file:
                data = json.load(file)
                if data["Eleve"] != client._selected_child.name:
                    logging.info(
                        f"L'élève sélectionné ({client._selected_child.name}) ne correspond pas à celui dans le fichier ({data['Eleve']}), je modifie le fichier."
                    )
                    writedataPronotepy(client, chemin_fichier, CmdId)
                else:
                    logging.info(
                        f"L'élève sélectionné est valide : {client._selected_child.name}"
                    )
                    logging.info(f"Le fichier {chemin_fichier} est à jour.")
                return True
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Une erreur est retournée sur le traitement de sélection d'élève-lig: %s; %s",
            line_number,
            e,
        )
        return False


def class_for_name(module_name, class_name):
    try:
        # Load the module, will raise ImportError if module cannot be loaded
        m = importlib.import_module(module_name)
        return getattr(m, class_name)
    except ImportError as e:
        logging.error("Error importing module %s: %s", module_name, e)
    except AttributeError as e:
        logging.error(
            "Error getting class %s from module %s: %s", class_name, module_name, e
        )
    return None


def download_image(url, filepath, session=None):
    try:
        # Effectuer une requête HTTP pour récupérer le contenu de l'image
        if session:
            response = session.get(url)
        else:
            response = requests.get(url)
        # Vérifier si la requête a réussi (code de statut 200)
        if response.status_code == 200:
            # Ouvrir un fichier en mode écriture binaire
            with open(filepath, "wb") as f:
                # Écrire le contenu de l'image dans le fichier
                f.write(response.content)
            return True
        else:
            # Afficher un message d'erreur si la requête a échoué
            logging.error(
                f"Erreur lors du téléchargement de l'image : {response.status_code}"
            )
            return False
    except Exception as e:

        # Afficher un message d'erreur en cas d'exception
        logging.error(f"Erreur lors du téléchargement de l'image : {e}")
        return False


def replace_if_different_no_lib(file1_path, file2_path):
    """
    Remplace le contenu de file2 par celui de file1 si les deux fichiers sont différents,
    sans utiliser de bibliothèques supplémentaires.

    :param file1_path: Chemin du premier fichier JPEG.
    :param file2_path: Chemin du second fichier JPEG.
    """
    # Lire le contenu des deux fichiers
    with open(file1_path, "rb") as f1, open(file2_path, "rb") as f2:
        content1 = f1.read()
        content2 = f2.read()

    # Comparer les contenus
    if content1 != content2:
        # Écrire le contenu de file1 dans file2
        with open(file2_path, "wb") as f2:
            f2.write(content1)
        print(f"Le contenu de {file1_path} a été copié dans {file2_path}.")
    else:
        print(
            f"Les fichiers {file1_path} et {file2_path} sont identiques. Aucune copie effectuée."
        )


# Exemple d'utilisation
# replace_if_different_no_lib('chemin/vers/image1.jpg', 'chemin/vers/image2.jpg')


def write_listenfant_to_file(listenfant, filename):
    try:
        with open(filename, "w") as file:
            for enfant in listenfant:
                file.write(enfant + "\n")
        logging.info("Liste des enfants écrite dans le fichier : %s", filename)
    except Exception as e:
        logging.error(
            "Échec de l'écriture de la liste des enfants dans le fichier : %s", e
        )


# ── Détection des nouveautés (P3, v1.1.0) ───────────────────────────────────
# À chaque sync, on compare les items courants (notes, devoirs, punitions,
# absences) à un index « déjà vu » persisté par équipement. Les nouveautés
# alimentent des commandes Jeedom qui déclenchent les scénarios utilisateur.


def _id_equipement(eq_id):
    """Rend l'identifiant d'équipement assaini, prêt à entrer dans un chemin.

    L'identifiant arrive du socket : il ne doit jamais servir tel quel à
    composer un chemin de fichier (SECURITY-AUDIT.md, finding L3). Jeedom
    n'émet que des entiers ; tout le reste est refusé plutôt que nettoyé, pour
    ne pas transformer discrètement « ../7 » en « 7 ».

    Args:
        eq_id: identifiant reçu, de n'importe quel type.

    Returns:
        str: l'identifiant sous sa forme canonique (``"12"``).

    Raises:
        ValueError: l'identifiant n'est pas un entier.
    """
    try:
        return str(int(str(eq_id).strip()))
    except (TypeError, ValueError):
        raise ValueError(f"Identifiant d'équipement invalide : {eq_id!r}")


def _dossier_equipement(data_dir, eq_id):
    """Dossier de données d'un équipement, identifiant assaini (cf. _id_equipement)."""
    return os.path.join(str(data_dir), _id_equipement(eq_id))


def _load_seen_index(data_dir, eq_id):
    """Charge l'index « déjà vu » d'un équipement (dict, {} si absent/illisible)."""
    path = os.path.join(_dossier_equipement(data_dir, eq_id), "seen_index.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_seen_index(data_dir, eq_id, index):
    """Persiste l'index « déjà vu » d'un équipement."""
    folder = _dossier_equipement(data_dir, eq_id)
    try:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "seen_index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f)
    except Exception as e:
        logging.error("Impossible d'écrire seen_index.json (eq %s) : %s", eq_id, e)


# Marqueur PRONOTE d'un renvoi vers la charge d'un fichier joint à la réponse :
# le champ ne porte pas la donnée mais son indice dans « dataNonSec.fichiers ».
_RENVOI_FICHIER_JOINT = 25


def photo_jointe(client, raw):
    """Extrait la photo de profil de la réponse ParametresUtilisateur.

    C'est ainsi que procèdent les deux clients officiels de PRONOTE 2026,
    espace classique comme espace mobile : la photo de l'utilisateur n'est pas
    téléchargée depuis FichiersExternes — cet endpoint ne sert que la photo des
    AUTRES individus, professeurs et camarades — elle accompagne la réponse.

    Le champ « photoBase64 » de la ressource ne contient pas la charge mais un
    renvoi ``{"_T": 25, "V": <indice>}`` vers le tableau ``dataNonSec.fichiers``
    de cette même réponse. Un compte parent reçoit un tableau à plusieurs
    entrées, une par enfant, chacun désigné par son propre indice.

    pronotepy ne lit que la moitié « dataSec » de l'enveloppe et laisse tomber
    « dataNonSec » : le renvoi arrive donc tel quel jusqu'ici. Le prendre pour
    une chaîne le fait passer pour vide, d'où le diagnostic « le serveur ne
    sert pas la photo sur les sessions mobiles », longtemps retenu à tort.

    Args:
        client: client pronotepy connecté
        raw: ``raw_resource`` de l'élève ou de l'enfant sélectionné

    Returns:
        bytes or None: la charge de l'image, ou None si absente ou illisible.
    """
    champ = (raw or {}).get("photoBase64")

    if isinstance(champ, str):
        # Un serveur qui inscrirait la charge directement dans le champ.
        charge = champ
    elif isinstance(champ, dict) and champ.get("_T") == _RENVOI_FICHIER_JOINT:
        fichiers = (
            (getattr(client, "parametres_utilisateur", None) or {})
            .get("dataNonSec", {})
            .get("fichiers")
            or []
        )
        indice = champ.get("V")
        if not isinstance(indice, int) or not 0 <= indice < len(fichiers):
            logging.info(
                "Renvoi photo inexploitable : indice %r pour %d fichier(s) joint(s)",
                indice,
                len(fichiers),
            )
            return None
        charge = fichiers[indice]
    else:
        return None

    if not isinstance(charge, str) or len(charge) < 100:
        return None

    try:
        # La charge est découpée en lignes : les blancs ne font pas partie du
        # base64.
        image = base64.b64decode("".join(charge.split()))
    except Exception as e:
        logging.info("Charge photo indécodable : %s", e)
        return None

    # N'écrire que ce qu'un navigateur saura afficher, plutôt que de propager
    # une charge inattendue jusqu'au widget.
    if not (image.startswith(b"\xff\xd8\xff") or image.startswith(b"\x89PNG")):
        logging.info(
            "Charge photo d'un format inattendu (%s), ignorée", image[:4].hex()
        )
        return None

    return image


def download_photo(client, eqLogicId, tokenconnected, message):
    """
    Récupère la photo de profil de l'élève ou de l'enfant sélectionné.

    La photo accompagne la réponse ParametresUtilisateur (voir
    :func:`photo_jointe`) ; c'est le chemin normal. Les stratégies
    FichiersExternes qui suivent ne sont qu'un repli pour les serveurs qui ne
    joindraient pas la charge.

    Args:
        client: Objet client PronotePy
        eqLogicId: ID de l'équipement Jeedom
        tokenconnected: Indicateur si connecté via token
        message: Dictionnaire du message reçu

    Returns:
        str or None: Chemin relatif de la photo, ou None si échec
    """
    try:
        # Comme pour l'identité : c'est l'enfant sélectionné qui fait le compte
        # parent, pas le mode de connexion. Un compte de démonstration parent
        # n'a pas de jeton et « TokenUrl » peut manquer.
        is_parent = bool(getattr(client, "_selected_child", None))

        data_dir = _dossier_equipement(_data_dir, eqLogicId) + "/"
        verifdossier(data_dir)
        final_path = f"{data_dir}profile_picture.jpg"
        temp_path = f"{data_dir}profile_picture_temp.jpg"

        # ── Compte parent : extraction base64 depuis l'API Pronote ───────────
        if is_parent:
            if not client._selected_child:
                logging.debug("Pas d'enfant sélectionné, photo ignorée")
                return None

            raw = client._selected_child.raw_resource
            if not raw.get("avecPhoto"):
                logging.debug("Pas de photo pour cet enfant (avecPhoto=False)")
                return None

            downloaded = False

            # ── Stratégie 0 : charge jointe à ParametresUtilisateur ───────────
            image = photo_jointe(client, raw)
            if image:
                with open(temp_path, "wb") as f:
                    f.write(image)
                logging.info(
                    "Photo parent obtenue — stratégie 0 (charge jointe, %d octets)",
                    len(image),
                )
                downloaded = True

            photo = None
            if not downloaded:
                photo = client._selected_child.profile_picture
                if not photo:
                    logging.debug("Aucune photo trouvée pour l'enfant")
                    return None
                logging.info("Téléchargement photo parent — URL : %s", photo.url)

            # ── Stratégie 1 : méthode native pronotepy ────────────────────────
            if not downloaded:
                try:
                    photo.save(temp_path)
                    logging.info(
                        "Photo téléchargée — stratégie 1 (FichiersExternes natif)"
                    )
                    downloaded = True
                except FileNotFoundError:
                    logging.info("Stratégie 1 échouée (404) — essai stratégie 2")
                except Exception as e:
                    logging.info("Stratégie 1 échouée (%s) — essai stratégie 2", e)

            # ── Stratégie 2 : session + headers Referer/Origin ────────────────
            if not downloaded:
                try:
                    headers = {
                        "Referer": client.communication.root_site + "/",
                        "Origin": client.communication.root_site,
                    }
                    resp = client.communication.session.get(
                        photo.url, headers=headers, timeout=15
                    )
                    if resp.status_code == 200 and len(resp.content) > 100:
                        with open(temp_path, "wb") as f:
                            f.write(resp.content)
                        logging.info("Photo téléchargée — stratégie 2 (Referer/Origin)")
                        downloaded = True
                    else:
                        logging.info(
                            "Stratégie 2 échouée — HTTP %d — essai stratégie 3",
                            resp.status_code,
                        )
                except Exception as e:
                    logging.info("Stratégie 2 échouée (%s) — essai stratégie 3", e)

            # ── Stratégie 3 : cookies de session ─────────────────────────────
            if not downloaded:
                try:
                    resp = requests.get(
                        photo.url,
                        cookies=client.communication.session.cookies,
                        timeout=15,
                        headers={
                            "User-Agent": "Mozilla/5.0",
                            "Referer": client.communication.root_site + "/",
                        },
                    )
                    if resp.status_code == 200 and len(resp.content) > 100:
                        with open(temp_path, "wb") as f:
                            f.write(resp.content)
                        logging.info(
                            "Photo téléchargée — stratégie 3 (cookies session)"
                        )
                        downloaded = True
                    else:
                        logging.warning(
                            "ProJote — Photo introuvable équipement %s (HTTP %d)",
                            eqLogicId,
                            resp.status_code,
                        )
                except Exception as e:
                    logging.warning(
                        "ProJote — Échec photo équipement %s : %s", eqLogicId, e
                    )

            if not downloaded:
                return None

            # Comparer et remplacer
            if os.path.exists(final_path):
                try:
                    with open(temp_path, "rb") as f1, open(final_path, "rb") as f2:
                        if f1.read() == f2.read():
                            logging.info("Photo identique, pas de remplacement")
                            os.remove(temp_path)
                            return (
                                f"/plugins/ProJote/data/{eqLogicId}/profile_picture.jpg"
                            )
                except Exception as e:
                    logging.error("Erreur comparaison photo : %s", e)
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    return None

            try:
                os.rename(temp_path, final_path)
                logging.info("Photo parent mise à jour : %s", final_path)
                return f"/plugins/ProJote/data/{eqLogicId}/profile_picture.jpg"
            except Exception as e:
                logging.error("Erreur remplacement photo : %s", e)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return None

        # ── Compte élève ─────────────────────────────────────────────────────
        downloaded = False

        # ── Stratégie 0 : charge jointe à ParametresUtilisateur ──────────────
        image = photo_jointe(client, client.info.raw_resource)
        if image:
            with open(temp_path, "wb") as f:
                f.write(image)
            logging.info(
                "Photo obtenue — stratégie 0 (charge jointe, %d octets)", len(image)
            )
            downloaded = True

        photo = None
        if not downloaded:
            photo = client.info.profile_picture
            if not photo:
                logging.debug("Aucune photo trouvée dans Pronote")
                return None
            logging.info("Téléchargement photo — URL : %s", photo.url)

        # ── Stratégie 1 : méthode native pronotepy (photo.save) ──────────────
        if not downloaded:
            try:
                photo.save(temp_path)
                logging.info("Photo téléchargée — stratégie 1 (FichiersExternes natif)")
                downloaded = True
            except FileNotFoundError:
                logging.info(
                    "Stratégie 1 échouée (404 FichiersExternes) — essai stratégie 2"
                )
            except Exception as e:
                logging.info("Stratégie 1 échouée (%s) — essai stratégie 2", e)

        # ── Stratégie 2 : session API + headers Referer/Origin ───────────────
        if not downloaded:
            try:
                headers = {
                    "Referer": client.communication.root_site + "/",
                    "Origin": client.communication.root_site,
                }
                resp = client.communication.session.get(
                    photo.url, headers=headers, timeout=15
                )
                if resp.status_code == 200 and len(resp.content) > 100:
                    with open(temp_path, "wb") as f:
                        f.write(resp.content)
                    logging.info("Photo téléchargée — stratégie 2 (Referer/Origin)")
                    downloaded = True
                else:
                    logging.info(
                        "Stratégie 2 échouée — HTTP %d, taille %d octets — essai stratégie 3",
                        resp.status_code,
                        len(resp.content),
                    )
            except Exception as e:
                logging.info("Stratégie 2 échouée (%s) — essai stratégie 3", e)

        # ── Stratégie 3 : cookies de la session HTTP ──────────────────────────
        if not downloaded:
            try:
                session_cookies = client.communication.session.cookies
                resp = requests.get(
                    photo.url,
                    cookies=session_cookies,
                    timeout=15,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": client.communication.root_site + "/",
                    },
                )
                if resp.status_code == 200 and len(resp.content) > 100:
                    with open(temp_path, "wb") as f:
                        f.write(resp.content)
                    logging.info("Photo téléchargée — stratégie 3 (cookies session)")
                    downloaded = True
                else:
                    logging.warning(
                        "ProJote — Photo introuvable pour l'équipement %s "
                        "(toutes stratégies échouées — HTTP %d). URL : %s",
                        eqLogicId,
                        resp.status_code,
                        photo.url,
                    )
            except Exception as e:
                logging.warning(
                    "ProJote — Échec téléchargement photo équipement %s (stratégie 3) : %s. "
                    "URL : %s",
                    eqLogicId,
                    e,
                    photo.url,
                )

        if not downloaded:
            return None

        # Vérifier si le fichier final existe et comparer
        if os.path.exists(final_path):
            try:
                with open(temp_path, "rb") as f1, open(final_path, "rb") as f2:
                    if f1.read() == f2.read():
                        logging.info("La photo est identique, pas de remplacement")
                        os.remove(temp_path)
                        return f"/plugins/ProJote/data/{eqLogicId}/profile_picture.jpg"
                    else:
                        logging.info("La photo est différente, remplacement")
            except Exception as e:
                logging.error("Erreur lors de la comparaison des photos : %s", e)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return None

        # Remplacer ou créer le fichier final
        try:
            os.rename(temp_path, final_path)
            logging.info("Photo mise à jour : %s", final_path)
            return f"/plugins/ProJote/data/{eqLogicId}/profile_picture.jpg"
        except Exception as e:
            logging.error("Erreur lors du remplacement de la photo : %s", e)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return None

    except Exception as e:
        logging.error("Erreur lors du téléchargement de la photo : %s", e)
        return None


def identites(clientinfo):
    # Le but est de collecter toutes les informations concernant l'identité de l'élève
    try:
        data = {"identiteinfo": []}
        # Création du dictionnaire d'informations d'identité avec des valeurs non vides
        estab = (clientinfo.establishment or "").strip()
        words = estab.split()
        mid = len(words) // 2
        if mid > 0 and words[:mid] == words[mid:]:
            estab = " ".join(words[:mid])

        IdentityInfo = {
            "Nom_Eleve": clientinfo.name,
            "Nom_Classe": clientinfo.class_name,
            "Etablissement": estab,
            # "Email": clientinfo.email,
        }
        logging.debug("Nom de l''identité nom  %s", clientinfo.name)
        logging.debug("Nom de l''identité Classe %s", clientinfo.class_name)
        logging.debug("Nom de l''identité Etablissement %s", estab)
        return IdentityInfo
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.info(
            "Tous les champs identité n'ont pas pu être récupéré: lig. %s -   %s",
            line_number,
            e,
        )


def connexion_demo(message):
    """Connecte un équipement de démonstration par identifiants.

    Chemin réservé aux serveurs de ``pronote_demo.HOTES_DEMO``. La démonstration
    ne délivre aucun jeton d'application mobile : sans cette voie, aucun compte
    de démonstration ne peut être enregistré, et il faut éprouver le plugin sur
    les données scolaires d'un enfant réel.

    Le mot de passe arrive **en clair** dans le message. Les anciennes fonctions
    Connectparent()/Connect() lui appliquaient ``my_decrypt()``, ce qui ne
    correspond plus à ce que Jeedom transmet : « password » ne figure pas dans
    ``$_encryptConfigKey`` côté PHP. Les réveiller telles quelles aurait
    réintroduit ce décalage, d'où cette fonction distincte.

    Args:
        message: dictionnaire reçu du socket Jeedom.

    Returns:
        Le client pronotepy connecté, ou None si la connexion échoue. La liste
        des enfants n'est pas rendue : la section de collecte la reconstruit
        depuis ``client.children``.
    """
    url = (message.get("url") or message.get("TokenUrl") or "").strip()
    login = (message.get("login") or "").strip()
    password = message.get("password") or ""
    enfant = (message.get("enfant") or "").strip()
    est_parent = "parent.html" in url

    try:
        classe = pronotepy.ParentClient if est_parent else pronotepy.Client
        client = classe(url, login, password)
        if not client.logged_in:
            logging.error(
                "Compte de démonstration : identifiants refusés pour %s", url
            )
            return None
    except Exception as e:
        if is_ip_suspension_error(e):
            raise
        logging.error(
            "Compte de démonstration : connexion impossible (%s) — %s",
            type(e).__name__,
            e,
        )
        return None

    if est_parent:
        listenfant = [c.name for c in client.children]
        cible = enfant if enfant in listenfant else (listenfant[0] if listenfant else "")
        if not cible:
            logging.error("Compte de démonstration parent sans enfant.")
            return None
        client.set_child(cible)
        logging.info("Compte de démonstration : connecté à l'enfant %s", cible)
    else:
        logging.info("Compte de démonstration : connecté en tant qu'élève")

    return client


def GetTokenFromLogin(Account, pin="4321", uuid=None):
    """Génère un jeton de connexion (credentials) à partir d'un compte déjà connecté."""
    qrcode_data = Account.request_qr_code_data(pin)
    logging.debug("Les info du QRCode url : %s", qrcode_data.get("url", ""))
    # Ne pas logger le contenu complet du qrcode_data (contient le jeton)
    return Account.qrcode_login(
        qrcode_data,
        pin,
        uuid=uuid,
    )


def RenewToken(client):
    try:
        # Récupération des tokens
        data = {"Token": client.export_credentials()}
        # Ne jamais logger le contenu du token (contient username/password chiffré)
        logging.debug("Token de reconnexion exporté avec succès")
        return data["Token"]
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des tokens: %s", e)


def check_and_update_failed_attempts(eqLogicId, increment=False):
    """
    Implémente un circuit breaker pour éviter les boucles infinies de reconnexion.
    Thread-safe via _failed_attempts_lock.

    Args:
        eqLogicId: ID de l'équipement
        increment: Si True, incrémente le compteur d'échecs

    Returns:
        True si les tentatives sont autorisées, False si circuit ouvert
    """
    global failed_attempts
    eqLogicId = str(eqLogicId)
    max_attempts = 3
    base_backoff = 60     # 1re ouverture du circuit : 60 s
    max_backoff = 3600    # plafond : 1 h

    current_time = time.time()

    with _failed_attempts_lock:
        # Initialiser si n'existe pas
        st = failed_attempts.setdefault(
            eqLogicId, {"count": 0, "timestamp": current_time, "blocked_until": 0}
        )
        st.setdefault("blocked_until", 0)

        # Cooldown (backoff) écoulé → on réautorise (compteur remis à zéro)
        if st["count"] > max_attempts and current_time >= st["blocked_until"]:
            st["count"] = 0
            st["blocked_until"] = 0

        # Incrémenter si demandé
        if increment:
            st["count"] += 1
            st["timestamp"] = current_time
            if st["count"] > max_attempts:
                # Backoff exponentiel : 60s, 120s, 240s… plafonné à max_backoff.
                backoff = min(
                    base_backoff * (2 ** (st["count"] - max_attempts - 1)),
                    max_backoff,
                )
                st["blocked_until"] = current_time + backoff
                logging.error(
                    "Circuit breaker OUVERT pour eqLogicId %s : %d échecs consécutifs, "
                    "prochain essai dans %ds. (Token Pronote expiré ? Rescanez le QR code.)",
                    eqLogicId, st["count"], int(backoff),
                )
                return False

        # Circuit encore en cooldown (backoff non écoulé)
        if st["count"] > max_attempts and current_time < st["blocked_until"]:
            remaining = int(st["blocked_until"] - current_time)
            logging.error(
                "Circuit breaker bloqué pour eqLogicId %s : nouvel essai dans %ds.",
                eqLogicId, remaining,
            )
            return False

    return True


def load_persistent_token(eqLogicId):
    """
    Charge le token persistant depuis le fichier enfant.ProJote.json.txt
    et l'utilise pour se reconnecter automatiquement au redémarrage du daemon.

    Args:
        eqLogicId: ID de l'équipement Jeedom

    Returns:
        tuple: (client, tokenconnected, enfant) ou (None, None, None) si échec
    """
    try:
        data_dir = _data_dir
        file_path = os.path.join(
            _dossier_equipement(data_dir, eqLogicId), "enfant.ProJote.json.txt"
        )

        if not os.path.exists(file_path):
            logging.info("Fichier token persistant non trouvé : %s", file_path)
            return None, None, None

        with open(file_path, "r") as f:
            data = json.load(f)

        if "Token" not in data:
            logging.warning("Token absent du fichier persistant")
            return None, None, None

        token = data["Token"]
        enfant = data.get("Eleve", "")

        # Vérifier que le token contient les informations requises
        required_token_keys = [
            "pronote_url",
            "username",
            "password",
            "client_identifier",
        ]
        if not all(key in token for key in required_token_keys):
            logging.error("Token persistant incomplet, reconnexion requise")
            return None, None, None

        logging.info("Tentative de reconnexion avec le token persistant...")
        try:
            if "parent.html" in token["pronote_url"]:
                client = pronotepy.ParentClient.token_login(
                    pronote_url=token["pronote_url"],
                    username=token["username"],
                    password=token["password"],
                    client_identifier=token["client_identifier"],
                    uuid=token.get("uuid", "ProJote"),
                )
                # Sélectionner l'enfant si spécifié
                if enfant and enfant != "":
                    try:
                        client.set_child(enfant)
                        logging.info("Reconnecté à l'enfant persistant : %s", enfant)
                    except Exception as e:
                        logging.warning("Impossible de sélectionner l'enfant : %s", e)
            else:
                client = pronotepy.Client.token_login(
                    pronote_url=token["pronote_url"],
                    username=token["username"],
                    password=token["password"],
                    client_identifier=token["client_identifier"],
                    uuid=token.get("uuid", "ProJote"),
                )

            if client and client.logged_in:
                logging.info("Reconnexion avec token persistant réussie !")
                # Sauvegarder les credentials frais sur disque à chaque connexion réussie
                # (pronotepy renouvelle les credentials internes à chaque token_login)
                try:
                    writedataPronotepy(
                        client,
                        _data_dir,
                        eqLogicId,
                        backup_token=data.get("BackupToken"),
                    )
                    logging.debug(
                        "Credentials renouvelés et sauvegardés pour l'équipement %s.",
                        eqLogicId,
                    )
                except Exception as e_save:
                    logging.warning(
                        "Sauvegarde des credentials renouvelés échouée pour %s : %s",
                        eqLogicId,
                        e_save,
                    )
                return client, "true", enfant
            else:
                logging.error(
                    "Le token persistant n'a pas permis une reconnexion valide"
                )
                return None, None, None

        except Exception as e:
            logging.warning("Reconnexion avec token persistant échouée : %s", e)

            # Tentative avec le token backup si disponible
            if "BackupToken" in data:
                logging.info("Tentative de reconnexion avec le token backup...")
                try:
                    backup_token = data["BackupToken"]
                    if not all(key in backup_token for key in required_token_keys):
                        logging.error("Token backup incomplet, reconnexion requise")
                    else:
                        if "parent.html" in backup_token["pronote_url"]:
                            client = pronotepy.ParentClient.token_login(
                                pronote_url=backup_token["pronote_url"],
                                username=backup_token["username"],
                                password=backup_token["password"],
                                client_identifier=backup_token["client_identifier"],
                                uuid=backup_token.get("uuid", "ProJote"),
                            )
                            if enfant and enfant != "":
                                try:
                                    client.set_child(enfant)
                                except Exception as e2:
                                    logging.warning(
                                        "Impossible de sélectionner l'enfant (backup) : %s",
                                        e2,
                                    )
                        else:
                            client = pronotepy.Client.token_login(
                                pronote_url=backup_token["pronote_url"],
                                username=backup_token["username"],
                                password=backup_token["password"],
                                client_identifier=backup_token["client_identifier"],
                                uuid=backup_token.get("uuid", "ProJote"),
                            )
                        if client and client.logged_in:
                            logging.warning(
                                "ProJote — Token principal expiré pour l'équipement %s. "
                                "Token backup utilisé. Renouvellement automatique des tokens en cours.",
                                eqLogicId,
                            )
                            # Tenter de renouveler le token backup via une 2e session indépendante
                            new_backup_credentials = None
                            try:
                                backup_uuid = backup_token.get("uuid", "ProJote")
                                # Utiliser un UUID distinct pour la nouvelle session backup
                                renew_uuid = (
                                    backup_uuid + "2"
                                    if backup_uuid.endswith("-bk")
                                    else backup_uuid + "-bk"
                                )
                                if "parent.html" in backup_token["pronote_url"]:
                                    new_backup_client = (
                                        pronotepy.ParentClient.token_login(
                                            pronote_url=backup_token["pronote_url"],
                                            username=backup_token["username"],
                                            password=backup_token["password"],
                                            client_identifier=backup_token[
                                                "client_identifier"
                                            ],
                                            uuid=renew_uuid,
                                        )
                                    )
                                else:
                                    new_backup_client = pronotepy.Client.token_login(
                                        pronote_url=backup_token["pronote_url"],
                                        username=backup_token["username"],
                                        password=backup_token["password"],
                                        client_identifier=backup_token[
                                            "client_identifier"
                                        ],
                                        uuid=renew_uuid,
                                    )
                                if new_backup_client and new_backup_client.logged_in:
                                    new_backup_credentials = (
                                        new_backup_client.export_credentials()
                                    )
                                    logging.info("Token backup renouvelé avec succès")
                                else:
                                    logging.warning(
                                        "ProJote — Token backup non renouvelé pour l'équipement %s. "
                                        "Reconnexion via QR recommandée pour régénérer un token de secours.",
                                        eqLogicId,
                                    )
                            except Exception as e_bk:
                                logging.warning(
                                    "ProJote — Renouvellement du token backup échoué pour l'équipement %s : %s. "
                                    "Reconnexion via QR recommandée.",
                                    eqLogicId,
                                    e_bk,
                                )
                            # Sauvegarder le nouveau token principal + backup (si disponible)
                            try:
                                writedataPronotepy(
                                    client,
                                    _data_dir,
                                    eqLogicId,
                                    backup_token=new_backup_credentials,
                                )
                                logging.warning(
                                    "ProJote — Tokens renouvelés pour l'équipement %s. Token backup : %s.",
                                    eqLogicId,
                                    (
                                        "régénéré avec succès"
                                        if new_backup_credentials
                                        else "non régénéré — reconnexion QR recommandée"
                                    ),
                                )
                            except Exception as e_save:
                                logging.warning(
                                    "ProJote — Sauvegarde des tokens renouvelés échouée pour l'équipement %s : %s",
                                    eqLogicId,
                                    e_save,
                                )
                            return client, "true", enfant
                except Exception as e2:
                    logging.warning("Reconnexion avec token backup échouée : %s", e2)

            logging.debug("Le token doit être regénéré via QR code")
            return None, None, None

    except Exception as e:
        logging.error("Erreur lors du chargement du token persistant : %s", e)
        return None, None, None


# Dernière valeur relevée pour chaque onglet, par équipement. Sert à deux
# choses : renvoyer à Jeedom la valeur conservée d'un onglet sauté par cadence,
# et celle d'un onglet dont la collecte vient d'échouer.
#
# En mémoire seulement, volontairement. Ce cache ne protège de rien de durable :
# après un redémarrage du démon, le premier cycle relève tout, ce qui était déjà
# le comportement. L'écrire sur disque ajouterait des écritures à chaque cycle,
# un format à faire évoluer et une corruption possible, pour éviter une seule
# collecte complète après un redémarrage.
_cache_collecte = {}
_cache_collecte_lock = threading.Lock()

# Seuls ces deux onglets remontent leur erreur dans la charge, comme avant :
# jeeProJote.php ne lit « error » que si connection_status vaut disconnected ou
# error, mais élargir la règle changerait la charge sans nécessité.
_ONGLETS_A_ERREUR_REMONTEE = ("Emploi_du_temps", "Notes")


def _collecteurs(message):
    """Table des onglets : clé de la charge, libellé de journal, appel.

    L'ordre est celui de la collecte linéaire d'origine : les journaux d'un
    cycle restent comparables à ceux des versions précédentes.
    """
    return (
        ("Emploi_du_temps", "l'emploi du temps", Emploidutemps),
        ("Notes", "les notes", notes),
        ("Periodes", "les dates de période", periodes),
        ("Menus", "les menus", menus),
        ("Messages", "la messagerie", messages),
        ("Notifications", "les notifications", notifications),
        ("Absences", "les absences", absences),
        ("Retards", "les retards", retards),
        ("Punitions", "les punitions", punitions),
        ("Devoirs", "les devoirs", lambda c: devoirs(c, _fenetre_devoirs(message))),
        ("Competences", "les évaluations", evaluations),
        ("Evenements", "les évènements de vie scolaire", evenements_vie_scolaire),
        ("Ical", "l'ICAL", ical),
    )


def collecter(client, eq_id, message, jsondata):
    """Relève les onglets Pronote et remplit ``jsondata``.

    Deux changements par rapport à la collecte linéaire d'origine :

    * **Chaque onglet est isolé.** Les collecteurs rattrapent déjà leurs propres
      erreurs, mais rien ne protégeait d'une exception inattendue : elle
      remontait jusqu'au gestionnaire de ``process_message``, qui abandonnait le
      cycle entier. Tout ce qui avait été relevé avant était perdu, et Jeedom ne
      recevait qu'une erreur. Un onglet qui tombe ne coûte désormais que
      lui-même.
    * **Chaque onglet suit sa cadence** (cadence.py). Un onglet sauté n'est pas
      absent de la charge : sa dernière valeur connue y est replacée. Jeedom
      reçoit toujours une charge complète — indispensable, car jeeProJote.php
      reconstruit le widget entièrement à partir d'elle, et une clé manquante
      viderait la section correspondante.

    ``SuspensionIP`` hérite de ``BaseException`` : elle traverse ce filet sans
    être rattrapée, comme prévu, pour arrêter le cycle immédiatement.

    Args:
        client: client pronotepy connecté.
        eq_id: identifiant de l'équipement Jeedom.
        message: message reçu du socket (porte la fenêtre des devoirs).
        jsondata: charge en cours de construction, complétée sur place.

    Returns:
        dict: statut de chaque onglet (cf. cadence.FRAIS / GARDE / REPLI / ECHEC).
    """
    eq = _id_equipement(eq_id)
    maintenant = time.time()
    with _cache_collecte_lock:
        cache = _cache_collecte.setdefault(eq, {"valeurs": {}, "horodatages": {}})
    statuts = {}
    # Onglets que l'utilisateur ne suit pas (cases de la page de configuration).
    # Leurs commandes ne sont pas créées côté Jeedom : ne rien envoyer est donc
    # cohérent, et surtout aucune requête n'est faite vers Pronote.
    coupes = set(message.get("OngletsDesactives") or [])

    for cle, libelle, appel in _collecteurs(message):
        if cle in coupes:
            statuts[cle] = cadence.COUPE
            logging.info("Je saute %s : onglet non suivi pour cet équipement.", libelle)
            continue
        connu = cache["valeurs"].get(cle)
        if not cadence.doit_collecter(cle, cache["horodatages"].get(cle), maintenant):
            jsondata[cle] = connu
            statuts[cle] = cadence.GARDE
            logging.info(
                "Je conserve %s : relevé il y a moins de %d min.",
                libelle,
                cadence.periode(cle) // 60,
            )
            continue

        logging.info("Je récupére %s", libelle)
        try:
            valeur = appel(client)
        except Exception as e:
            if connu is None:
                statuts[cle] = cadence.ECHEC
                logging.error(
                    "Échec de la collecte de %s : %s. Aucune valeur antérieure, "
                    "cet onglet sera absent de ce cycle.",
                    libelle,
                    e,
                )
            else:
                jsondata[cle] = connu
                statuts[cle] = cadence.REPLI
                logging.error(
                    "Échec de la collecte de %s : %s. La valeur du relevé "
                    "précédent est conservée.",
                    libelle,
                    e,
                )
            logging.debug("Traceback complet : %s", traceback.format_exc())
            continue

        jsondata[cle] = valeur
        statuts[cle] = cadence.FRAIS
        cache["valeurs"][cle] = valeur
        cache["horodatages"][cle] = maintenant
        if (
            cle in _ONGLETS_A_ERREUR_REMONTEE
            and isinstance(valeur, dict)
            and "error" in valeur
        ):
            jsondata["error"] = valeur["error"]

    _resume = {}
    for statut in statuts.values():
        _resume[statut] = _resume.get(statut, 0) + 1
    logging.info(
        "Collecte terminée : %s.",
        ", ".join(f"{n} {s}" for s, n in sorted(_resume.items())) or "rien",
    )
    return statuts


def process_message(message):
    """
    Traite un message reçu depuis le socket Jeedom.
    Appelé séquentiellement par le thread worker unique (_worker_loop).
    """
    eq_id = str(message.get("CmdId", ""))
    try:
        if message.get("apikey") != _apikey:
            logging.error("Invalid apikey from socket: %s", message.get("apikey"))
            # Envoyer une notification d'erreur à Jeedom
            jeedom_com.send_change_immediate(
                {
                    "error": "Invalid API key",
                    "CmdId": message.get("CmdId", ""),
                    "connection_status": "error",
                }
            )
            return

        # Fenêtre de pause : Pronote a suspendu l'IP de la box, on ne tente rien.
        # Insister pendant la suspension ne ferait que la prolonger.
        remaining = ip_suspension_remaining()
        if remaining > 0:
            with _ip_suspension_lock:
                until = _ip_suspension["until"]
                level = _ip_suspension["level"]
            logging.warning(
                "Équipement %s : mise à jour ignorée, l'adresse IP est suspendue "
                "par Pronote. Reprise prévue à %s (dans %d min).",
                eq_id,
                datetime.datetime.fromtimestamp(until).strftime("%H:%M"),
                remaining // 60 + 1,
            )
            notify_ip_suspension(eq_id, until, remaining, level)
            return

        # ========================================================
        #   0 : Cas particulier des serveurs de démonstration
        # ========================================================
        # La démonstration ne délivre aucun jeton d'application mobile : la
        # connexion s'y fait par identifiants, à chaque cycle. Le test porte sur
        # l'hôte (cf. pronote_demo), jamais sur un réglage — un établissement
        # réel ne doit pas pouvoir emprunter ce chemin.
        mode_demo = est_compte_demo(message)

        # ========================================================
        #   1 : On se connecte avec le Token réçu par défault
        # ========================================================
        # Vérifier que les informations de Token sont présentes et non vides
        required_keys = ["TokenId", "TokenUsername", "TokenPassword", "TokenUrl"]
        all_keys_present = True
        for key in required_keys:
            if key not in message or not message[key].strip():
                if not mode_demo:
                    logging.error("Information de Token manquante ou vide : %s", key)
                all_keys_present = False
        if mode_demo:
            # Le cas démonstration passe AVANT le jeton, et non après : une
            # validation antérieure a pu laisser des champs Token_* renseignés,
            # qui enverraient le cycle sur un chemin voué à l'échec.
            client = connexion_demo(message)
            if client is None:
                jeedom_com.send_change_immediate(
                    {
                        "error": (
                            "Compte de démonstration : identifiants refusés. "
                            "Vérifiez l'identifiant et le mot de passe."
                        ),
                        "CmdId": message.get("CmdId", ""),
                        "connection_status": "disconnected",
                    }
                )
                return
            # `enfant` n'est pas repris ici : la section de collecte lit
            # l'enfant directement sur le client, jamais une variable locale.
            tokenconnected = "false"
        elif all_keys_present:
            logging.debug(
                "Toutes les informations de Token sont présentes et non vides. Je me connecte avec le Token"
            )

            # Vérifier le circuit breaker avant de tenter la connexion
            eqLogicId = message.get("CmdId", "")
            if not check_and_update_failed_attempts(eqLogicId, increment=False):
                error_msg = (
                    f"ProJote - Token expiré pour équipement {eqLogicId}. "
                    f"Trop de tentatives échouées. "
                    f"Supprimez le token et rescanez le code QR pour générer une nouvelle connexion."
                )
                logging.error(
                    f"Circuit breaker BLOQUÉ pour eqLogicId {eqLogicId}. "
                    f"Les tentatives de connexion au token repétées ont échoué. "
                    f"Le token est probablement expiré. "
                    f"Supprimez le fichier token et rescanez le code QR."
                )
                # Note: Le message est envoyé via jeeProJote.php après réception du JSON
                # send_jeedom_message() est désactivé car la route n'existe pas en Jeedom 4.3+

                with _failed_attempts_lock:
                    nb_attempts = failed_attempts.get(str(eqLogicId), {"count": 0})[
                        "count"
                    ]
                jeedom_com.send_change_immediate(
                    {
                        "error": f"Token expiré. Trop de tentatives échouées ({nb_attempts} tentatives). "
                        f"Supprimez le token et rescanez le code QR.",
                        "CmdId": eqLogicId,
                        "connection_status": "disconnected",
                    }
                )
                return

            # Retenue pour distinguer un jeton refusé d'un incident passager :
            # reste à None si Pronote refuse la connexion sans lever d'exception.
            _erreur_connexion = None
            try:
                if "parent.html" in message["TokenUrl"]:
                    client = pronotepy.ParentClient.token_login(
                        pronote_url=message["TokenUrl"],
                        username=message["TokenUsername"],
                        password=message["TokenPassword"],
                        client_identifier=message["TokenId"],
                        # Fallback "ProJote" : compat tokens créés avant v0.9 (uuid non stocké)
                        uuid=message.get("TokenUuid", "ProJote"),
                    )
                    # Je sélectionne l'enfant si il est spécifié
                    if "enfant" in message and message["enfant"] != "":
                        # Pour mettre à jour la liste d'enfant, je vérifie toujours la liste
                        client.set_child(message["enfant"])
                        logging.info(
                            "Je suis connecté à l'enfant %s", message["enfant"]
                        )
                else:
                    client = pronotepy.Client.token_login(
                        pronote_url=message["TokenUrl"],
                        username=message["TokenUsername"],
                        password=message["TokenPassword"],
                        client_identifier=message["TokenId"],
                        # Fallback "ProJote" : compat tokens créés avant v0.9 (uuid non stocké)
                        uuid=message.get("TokenUuid", "ProJote"),
                    )
            except Exception as e:
                # Suspension d'IP : le token n'est pas en cause, on ne doit ni
                # incrémenter le circuit breaker ni conseiller de rescanner le QR.
                if is_ip_suspension_error(e):
                    trigger_ip_suspension(eqLogicId=eqLogicId, exc=e)
                    return
                if is_authentification_refusee(e):
                    # Le refus lui-même n'est pas expliqué par PRONOTE : un jeton
                    # périmé et un serveur qui refuse temporairement de répondre
                    # laissent exactement la même trace. N'affirmer ni l'un ni
                    # l'autre — d'autant que le jeton de secours est essayé juste
                    # après, et qu'il répare le cas le plus fréquent sans que
                    # l'utilisateur ait à toucher à quoi que ce soit.
                    logging.error(
                        "Authentification refusée par Pronote (%s). Le jeton de "
                        "secours va être essayé. Si les cycles suivants échouent "
                        "aussi, alors seulement revalidez le compte.",
                        e,
                    )
                else:
                    logging.error(
                        "Connexion au jeton impossible : %s",
                        e,
                    )
                _erreur_connexion = e
                client = None
            # Le jeton transmis par Jeedom est refusé : avant d'exiger un
            # nouveau QR Code, on retente avec le dernier jeton rangé sur disque
            # par token_secours. Il est plus récent que celui de la base si le
            # cycle précédent s'est interrompu avant l'écriture, ou si cette
            # écriture a échoué. PRONOTE n'acceptant que le tout dernier jeton
            # émis, c'est la seule réparation possible sans l'utilisateur.
            if client is None or not client.logged_in:
                _eq_id = message.get("CmdId", "")
                _secours = token_secours.charger(_data_dir, _eq_id)
                if not token_secours.erreur_de_jeton(_erreur_connexion):
                    # Incident réseau ou serveur momentanément fermé : le jeton
                    # stocké reste valable et sera rejoué au prochain cycle.
                    # Consommer le jeton de secours ici le gaspillerait.
                    logging.warning(
                        "Échec de connexion sans rapport avec le jeton (%s) : le jeton "
                        "de secours est conservé intact.",
                        _erreur_connexion,
                    )
                    _secours = None
                if _secours and _secours.get("password") != message.get("TokenPassword"):
                    logging.warning(
                        "Jeton refusé par Pronote : nouvelle tentative avec le jeton "
                        "de secours enregistré sur disque."
                    )
                    try:
                        _url = _secours.get("pronote_url", "")
                        _classe = (
                            pronotepy.ParentClient
                            if "parent.html" in _url
                            else pronotepy.Client
                        )
                        client = _classe.token_login(
                            pronote_url=_url,
                            username=_secours["username"],
                            password=_secours["password"],
                            client_identifier=_secours.get("client_identifier"),
                            uuid=_secours.get(
                                "uuid", message.get("TokenUuid", "ProJote")
                            ),
                        )
                        if (
                            client.logged_in
                            and message.get("enfant")
                            and _classe is pronotepy.ParentClient
                        ):
                            client.set_child(message["enfant"])
                        if client.logged_in:
                            logging.info(
                                "Connexion rétablie avec le jeton de secours. Le jeton "
                                "à jour redescendra vers Jeedom en fin de cycle."
                            )
                    except Exception as e:
                        # La suspension peut aussi n'apparaître qu'ici : on ouvre
                        # la fenêtre de pause plutôt que d'accuser le jeton.
                        if is_ip_suspension_error(e):
                            trigger_ip_suspension(eqLogicId=_eq_id, exc=e)
                            return
                        logging.error(
                            "Le jeton de secours a été refusé lui aussi : %s", e
                        )
                        client = None

            ### 05/01/2025 : A revalider si je dois doubler
            # A supprimer car doublon avec ligne 1155
            # credentials = client.export_credentials()
            if client is not None and client.logged_in:
                tokenconnected = "true"
                # Pronote répond de nouveau : on referme la fenêtre de pause.
                clear_ip_suspension()
                logging.debug(
                    "Onglets autorisés par Pronote pour ce compte : %s",
                    getattr(client.communication, "authorized_onglets", None),
                )
                # Réinitialiser le compteur d'échecs en cas de connexion réussie
                eqLogicId = message.get("CmdId", "")
                with _failed_attempts_lock:
                    if str(eqLogicId) in failed_attempts:
                        failed_attempts[str(eqLogicId)] = {
                            "count": 0,
                            "timestamp": time.time(),
                            "blocked_until": 0,
                        }
            else:
                logging.error(
                    "Tous les jetons disponibles ont été refusés pour l'équipement %s.",
                    message.get("CmdId", ""),
                )
                eqLogicId = message.get("CmdId", "")
                check_and_update_failed_attempts(eqLogicId, increment=True)
                # Prévenir Jeedom de l'échec. Sans cet envoi, la commande
                # Statut_Connexion restait figée sur la valeur du dernier cycle
                # réussi — relevée à près de quatre mois sur un équipement — et
                # le widget continuait d'afficher notes et emploi du temps
                # périmés comme s'ils étaient du jour. Le chemin « aucun jeton »
                # juste en dessous prévenait déjà ; celui-ci l'avait oublié.
                # Le message part vers le widget et le centre de messages : il
                # doit parler à l'utilisateur. Un refus d'authentification se
                # présente sous la forme d'un KeyError sur une clé d'enveloppe
                # (« 'dataSec' ») — inutile de le lui montrer, cela n'aide qu'à
                # lire les logs. Tout autre détail, lui, est conservé : il peut
                # nommer une panne réseau ou une réponse inattendue du serveur.
                detail = "" if is_authentification_refusee(_erreur_connexion) else (
                    str(_erreur_connexion).strip() if _erreur_connexion else ""
                )
                jeedom_com.send_change_immediate(
                    {
                        "error": (
                            "Pronote a refusé le jeton de connexion"
                            + (" (" + detail + ")" if detail else "")
                        ),
                        "CmdId": eqLogicId,
                        "connection_status": "disconnected",
                    }
                )
                return
        else:
            logging.error(
                "Aucun token disponible. Configurez la connexion via QR code."
            )
            jeedom_com.send_change_immediate(
                {
                    "error": "Aucun token disponible, connexion impossible. Configurez via QR code.",
                    "CmdId": message.get("CmdId", ""),
                    "connection_status": "disconnected",
                }
            )
            return
        # ==================================================================================
        #  3 :  Je récupére les informations de l'élève
        # ==================================================================================
        if client is not None and client.logged_in:
            logging.debug("Nous sommes loggué")
            # Je récupére les informations de l'élève
            jsondata = {}
            jsondata["CmdId"] = message["CmdId"]
            jsondata["ConnectionDate"] = datetime.datetime.now().strftime(
                " %H:%M:%S %d/%m/%Y"
            )
            jsondata["connection_status"] = "connected"
            logging.debug(
                "Validation Token %s",
                tokenconnected,
            )
            # Se fier à l'enfant sélectionné plutôt qu'au mode de connexion :
            # un compte de démonstration parent n'a pas de jeton, et « TokenUrl »
            # peut manquer — l'ancien test partait alors sur l'identité du
            # parent au lieu de celle de l'enfant.
            if getattr(client, "_selected_child", None):
                logging.debug("Le nom de l'élève %s", client._selected_child.name)
                jsondata["Eleve"] = identites(client._selected_child)
                # Ajouter la liste des enfants pour les comptes parents
                list_enfant = []
                for child in client.children:
                    list_enfant.append(child.name)
                jsondata["Liste_Enfant"] = json.dumps(
                    list_enfant, separators=(",", ":")
                )
            else:
                jsondata["Eleve"] = identites(client.info)
            # Téléchargement de la photo
            local_picture_path = download_photo(
                client, message["CmdId"], tokenconnected, message
            )
            if local_picture_path:
                jsondata["Local_Picture"] = local_picture_path
            # Le token n'est PAS exporté ici : PRONOTE le fait tourner à chaque
            # authentification, et pronotepy se ré-authentifie à chaque requête
            # (plusieurs dizaines de fois par cycle). Un token capturé maintenant
            # serait périmé dès la fin de la collecte, et la connexion suivante
            # échouerait sur « Token invalide, regénérer le QR CODE ». Il est donc
            # exporté juste avant l'envoi à Jeedom, une fois toutes les requêtes
            # terminées : voir plus bas, avant send_change_immediate().
            # Je valide que le fichier équipement est à jours
            # je lance la foncton qui recherche si le nom de l'enfant à changer dans l'équipement
            Checkeleve(client, message["CmdId"])
            # Collecte des douze onglets. Chacun est isolé du voisin et suit sa
            # propre cadence — voir collecter() et cadence.py.
            jsondata["Collecte"] = collecter(client, message["CmdId"], message, jsondata)
            notes_data = jsondata.get("Notes") or {}
            # Détection des nouveautés depuis la sync précédente (P3, v1.1.0)
            try:
                _seen = _load_seen_index(_data_dir, message["CmdId"])
                # .get() et non [] : depuis la collecte isolée (v1.5.0), un onglet
                # dont la collecte a échoué sans valeur antérieure connue est absent
                # de la charge. Une clé manquante ne doit pas priver de détection
                # les deux autres.
                _dev = jsondata.get("Devoirs") if isinstance(jsondata.get("Devoirs"), dict) else {}
                _abs = jsondata.get("Absences") if isinstance(jsondata.get("Absences"), dict) else {}
                _pun = jsondata.get("Punitions") if isinstance(jsondata.get("Punitions"), dict) else {}
                _deltas, _new_index = compute_deltas(
                    _seen,
                    notes_data.get("note", []) if isinstance(notes_data, dict) else [],
                    _dev.get("devoir", []),
                    _pun.get("punition", []),
                    _abs.get("absence", []),
                )
                jsondata["Deltas"] = _deltas
                _save_seen_index(_data_dir, message["CmdId"], _new_index)
            except Exception as _e:
                logging.error("Détection des nouveautés (deltas) échouée : %s", _e)
            # Export du token en tout dernier, après la totalité des requêtes :
            # c'est la seule valeur encore acceptée par PRONOTE au prochain cycle.
            logging.info("Je renew le Token")
            jsondata["Token"] = RenewToken(client)
            # J'envoie les données à Jeedom
            logging.debug(
                "Projoted.py :: Données JSON à envoyer : %s", json.dumps(jsondata)
            )
            jeedom_com.send_change_immediate(jsondata)
            logging.info("Fin de récupération d'info depuis Projoted.py")
        else:
            echo = "Le compte n'est pas loggué"
            logging.error(echo)
            jeedom_com.send_change_immediate(
                {
                    "error": echo,
                    "CmdId": message.get("CmdId", ""),
                    "connection_status": "disconnected",
                }
            )
            return False
    except SuspensionIP as e:
        # Levée par le garde posé sur pronotepy.post : une suspension est apparue
        # en cours de cycle. Elle a traversé les except Exception des collecteurs,
        # le cycle s'est donc arrêté à la première requête refusée. On n'envoie
        # pas le jsondata partiel : Jeedom conserve ses valeurs précédentes au
        # lieu d'être écrasé par des données vides.
        trigger_ip_suspension(eqLogicId=message.get("CmdId", ""), exc=e)
        return
    except Exception as e:
        # Filet pour les chemins qui ne passent pas par post() — la connexion
        # initiale, par exemple, où la suspension est vue dans initialise().
        if is_ip_suspension_error(e):
            trigger_ip_suspension(eqLogicId=message.get("CmdId", ""), exc=e)
            return
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "unknown"
        error_msg = f"Erreur d'éxécution du daemon : ligne {line_number} - {str(e)}"
        logging.error(error_msg)
        logging.debug("Traceback complet : %s", traceback.format_exc())
        jeedom_com.send_change_immediate(
            {
                "error": error_msg,
                "CmdId": message.get("CmdId", ""),
                "connection_status": "error",
            }
        )
    finally:
        # Retirer l'équipement du set — libère la place pour une prochaine requête
        with _queued_eq_lock:
            _queued_eq.discard(eq_id)


def _run_with_timeout(target, timeout):
    """Exécute target() dans un thread et attend au plus `timeout` secondes.

    Retourne True si terminé dans les temps, False sur timeout. Sur timeout, le
    thread orphelin continue en arrière-plan (impossible de tuer un thread en
    Python) mais le worker est libéré pour traiter l'équipement suivant : un
    compte Pronote lent (ENT qui timeout) ne bloque plus les autres enfants.
    Une éventuelle exception levée par target() est propagée à l'appelant.
    """
    holder = {}

    def _wrap():
        try:
            target()
        except Exception as exc:  # noqa: BLE001 - on propage à l'appelant
            holder["exc"] = exc

    t = threading.Thread(target=_wrap, daemon=True, name="projote-task")
    t.start()
    t.join(timeout)
    if t.is_alive():
        return False
    if "exc" in holder:
        raise holder["exc"]
    return True


def _worker_loop():
    """
    Boucle du thread worker unique.
    Dépile les messages de _work_queue et les traite séquentiellement.
    Les logs sont ainsi linéaires et faciles à lire.
    """
    global _worker_eq_id, _worker_eq_start
    logging.info("Worker ProJote démarré — traitement séquentiel des équipements.")
    while True:
        try:
            message = _work_queue.get(timeout=1.0)
        except _queue_module.Empty:
            continue
        eq_id = str(message.get("CmdId", ""))
        with _worker_state_lock:
            _worker_eq_id = eq_id
            _worker_eq_start = time.time()
        # Nouveau cycle : on réessaie l'onglet Présence, un droit a pu être accordé.
        _presence_refusee.discard(str(eq_id))
        logging.info(
            "=== Début traitement équipement %s (file restante : %d) ===",
            eq_id,
            _work_queue.qsize(),
        )
        try:
            # Timeout dur par équipement : au-delà de _WORKER_TIMEOUT, on abandonne
            # ce traitement (compte injoignable) et on passe au suivant.
            finished = _run_with_timeout(
                lambda: process_message(message), _WORKER_TIMEOUT
            )
            if not finished:
                logging.error(
                    "ProJote — équipement %s : traitement abandonné (timeout dur %ds, "
                    "Pronote/ENT injoignable ?). Circuit breaker incrémenté, passage au suivant.",
                    eq_id,
                    _WORKER_TIMEOUT,
                )
                check_and_update_failed_attempts(eq_id, increment=True)
                with _queued_eq_lock:
                    _queued_eq.discard(eq_id)
        except Exception as e:
            logging.error("Erreur non capturée pour l'équipement %s : %s", eq_id, e)
        finally:
            with _worker_state_lock:
                _worker_eq_id = None
                _worker_eq_start = None
            _work_queue.task_done()
            logging.info("=== Fin traitement équipement %s ===", eq_id)


def _watchdog_loop():
    """
    Surveille le worker toutes les 30 secondes.
    Si un équipement monopolise le worker plus de _WORKER_TIMEOUT secondes,
    émet un WARNING et libère son slot dans _queued_eq pour ne pas bloquer
    les requêtes suivantes.
    """
    while True:
        time.sleep(30)
        with _worker_state_lock:
            eq_id = _worker_eq_id
            start = _worker_eq_start
        if eq_id is not None and start is not None:
            elapsed = time.time() - start
            if elapsed > _WORKER_TIMEOUT:
                logging.warning(
                    "ProJote — Watchdog : équipement %s en cours depuis %.0fs "
                    "(timeout %ds). Le worker est peut-être bloqué (Pronote injoignable ?). "
                    "Libération forcée du slot.",
                    eq_id,
                    elapsed,
                    _WORKER_TIMEOUT,
                )
                with _queued_eq_lock:
                    _queued_eq.discard(eq_id)


def _ensure_worker():
    """Démarre le thread worker et le watchdog s'ils ne sont pas encore actifs."""
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(
            target=_worker_loop, daemon=True, name="projote-worker"
        )
        _worker_thread.start()
        logging.info("Thread worker ProJote lancé.")
        watchdog = threading.Thread(
            target=_watchdog_loop, daemon=True, name="projote-watchdog"
        )
        watchdog.start()
        logging.debug("Thread watchdog ProJote lancé (timeout %ds).", _WORKER_TIMEOUT)


def read_socket():
    global JEEDOM_SOCKET_MESSAGE
    try:
        if JEEDOM_SOCKET_MESSAGE.empty():
            return

        raw_message = JEEDOM_SOCKET_MESSAGE.get()
        decoded_message = raw_message.decode("utf-8")
        if not decoded_message.strip():
            logging.error("Notification vide ou invalide reçu depuis le socket.")
            return
        try:
            message = json.loads(decoded_message)
        except json.JSONDecodeError as e:
            logging.error("Erreur de décodage JSON : %s", e)
            logging.debug("Notification en erreur : %s", raw_message)
            return

        logging.debug("Message reçu : %s", message)
        eq_id = str(message.get("CmdId", ""))

        with _queued_eq_lock:
            if eq_id in _queued_eq:
                logging.warning(
                    "Équipement %s déjà dans la file — requête ignorée.", eq_id
                )
                return
            _queued_eq.add(eq_id)

        _ensure_worker()
        _work_queue.put(message)
        logging.info(
            "Équipement %s ajouté à la file (taille file : %d).",
            eq_id,
            _work_queue.qsize(),
        )

    except Exception as e:
        logging.error("Erreur dans read_socket : %s", e)


def listen():
    jeedom_socket.open()
    try:
        while 1:
            time.sleep(0.5)
            read_socket()
    except KeyboardInterrupt:
        shutdown()


# ----------------------------------------------------------------------------


def handler(signum=None, frame=None):
    logging.debug("Signal %i caught, exiting...", int(signum))
    shutdown()


def shutdown():
    logging.debug("Shutdown")
    logging.debug("Removing PID file %s", _pidfile)
    with contextlib.suppress(Exception):
        os.remove(_pidfile)
    with contextlib.suppress(Exception):
        jeedom_socket.close()
    logging.debug("Exit 0")
    # sys.stdout.flush()
    os._exit(0)


# ── Démarrage du démon ──────────────────────────────────────────────────────
# Bloc exécuté uniquement quand le fichier est lancé comme script (python ProJoted.py …).
# Le guard __main__ permet d'importer ce module dans les tests unitaires sans
# démarrer le démon (pas de parsing d'arguments, pas de socket, pas de signaux).
def _run_daemon():
    """Point d'entrée du démon : parse les arguments, ouvre le socket et écoute."""
    global _socket_host, _log_level, _callback, _apikey, _pidfile, _cycle
    global _socket_port, _data_dir, _callback_url, _apikey_global
    global jeedom_com, jeedom_socket

    # Ici est le script qui va écouter le socket. Mais la premiére chose qu'il va faire est de renvoyer sont PiD pour validation.
    _socket_host = "localhost"
    parser = argparse.ArgumentParser(description="Projoted Daemon for Jeedom plugin")
    parser.add_argument("--loglevel", help="Log Level for the daemon", type=str)
    parser.add_argument("--callback", help="Callback", type=str)
    parser.add_argument("--apikey", help="Apikey", type=str)
    parser.add_argument("--cycle", help="Cycle to send event", type=str)
    parser.add_argument("--pid", help="Pid file", type=str)
    parser.add_argument("--socketport", help="Port for Projote Deamon", type=str)
    parser.add_argument("--datadir", help="Path to plugin data directory", type=str)
    args = parser.parse_args()

    _log_level = args.loglevel or "error"
    _callback = args.callback or ""
    _apikey = args.apikey or ""
    _pidfile = args.pid or "/tmp/ProJoted.pid"
    _cycle = float(args.cycle) if args.cycle else 0.3
    _socket_port = args.socketport or 55369
    _data_dir = args.datadir or "/var/www/html/plugins/ProJote/data"
    _socket_port = int(_socket_port)
    _cycle = int(_cycle)

    jeedom_utils.set_log_level(_log_level)

    # Après set_log_level(), qui installe les handlers : un filtre posé avant
    # serait perdu. Avant toute lecture du socket, en revanche — c'est là que
    # les identifiants arrivent.
    installer_filtre_secrets()

    # Filet de sécurité sur le jeton : PRONOTE le renouvelle à chaque
    # authentification et refuse tout jeton antérieur. On le range sur disque
    # dès qu'il change, pour pouvoir réparer la connexion sans redemander un
    # QR Code à l'utilisateur si la base contient une valeur périmée.
    token_secours.installer(_data_dir, _equipement_en_cours)

    # Filtre les messages DEBUG verbeux de PronotePy (champs optionnels absents)
    class _PronotepyNoiseFilter(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            return "setting to default" not in msg and "Could not get value for" not in msg

    for _log_handler in logging.root.handlers:
        _log_handler.addFilter(_PronotepyNoiseFilter())

    logging.info("Start demond")
    logging.info("Log level: %s", _log_level)
    logging.info("Socket port: %s", _socket_port)
    logging.info("Socket host: %s", _socket_host)
    logging.info("PID file: %s", _pidfile)
    logging.info("Apikey: %s", _apikey)

    # Initialiser les variables globales pour les messages Jeedom
    _callback_url = _callback
    _apikey_global = _apikey

    # Restaure une éventuelle fenêtre de pause « IP suspendue » laissée par une
    # exécution précédente : sans cela, un redémarrage du démon repartirait
    # aussitôt en requêtes et prolongerait la suspension.
    load_ip_suspension()
    _installer_garde_suspension()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    try:
        jeedom_utils.write_pid(str(_pidfile))
        jeedom_com = jeedom_com(apikey=_apikey, url=_callback, cycle=_cycle)
        if not jeedom_com.test():
            logging.error(
                "Network communication issues. Please fixe your Jeedom network configuration."
            )
            shutdown()
        jeedom_socket = jeedom_socket(port=_socket_port, address=_socket_host)
        listen()
    except Exception as e:
        logging.error("Fatal error: %s", e)
        logging.info(traceback.format_exc())
        shutdown()


if __name__ == "__main__":
    _run_daemon()
