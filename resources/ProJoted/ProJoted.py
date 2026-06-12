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
    import binascii
    import importlib
    import requests
    import threading

    # import du Plugin Principal
    import pronotepy
    from pronotepy.ent import *
    import pronotepy.dataClasses

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

    # Chiffrement du password
    import hashlib
    from Crypto.Cipher import AES
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


def my_decrypt(data, passphrase=None):
    """
    Déchiffre des données AES-256-CBC chiffrées par my_encrypt() côté PHP.

    Si aucune passphrase n'est fournie, la clé est dérivée de l'API key Jeedom
    via SHA-256 (produit 64 hex chars = 32 octets), assurant la cohérence PHP↔Python.
    Format attendu : base64(JSON({iv: base64, data: base64}))

    Audit sécurité (P2c, juin 2026) — dérivation de clé jugée correcte :
    la clé dérive de l'API key Jeedom, secret ALÉATOIRE à forte entropie généré
    par le core (pas un ID, une constante ou un nom prévisible). SHA-256 comme
    KDF est approprié pour une entrée à forte entropie ; PBKDF2 n'apporterait
    un gain que pour étirer un secret faible (mot de passe humain), ce qui n'est
    pas le cas ici. Limite connue (acceptée, cf. SECURITY-AUDIT.md) : CBC sans
    authentification (pas de HMAC/GCM) — le déchiffrement est local, sans oracle
    exposé à un attaquant réseau.
    """
    if passphrase is None:
        passphrase = hashlib.sha256(_apikey.encode()).hexdigest()
    try:
        unpad = lambda s: s[: -s[-1]]
        key = binascii.unhexlify(passphrase)
        encrypted = json.loads(base64.b64decode(data).decode("ascii"))
        encrypted_data = base64.b64decode(encrypted["data"])
        iv = base64.b64decode(encrypted["iv"])
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted_data)
        return unpad(decrypted).decode("ascii").rstrip()
    except Exception as e:
        logging.error("Cannot decrypt datas: %s", e)
        exit(1)


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
        if client._selected_child == "":
            logging.error("Aucun élève sélectionné.")
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


def cours_affiche_from_lesson(lesson_data):
    if lesson_data.detention == True:
        return "RETENUE"
    try:
        return lesson_data.subject.name if lesson_data.subject else "Repas"
    except Exception:
        return "Repas"


def build_menu_data(menu):
    """
    Construit un dictionnaire contenant toutes les informations d'un menu Pronote.
    Args:
        menu (pronotepy.Menu): Un objet Menu pronotepy.
    Returns:
        dict: Un dictionnaire structuré avec tous les champs utiles.
    """

    def serialize_food_list(food_list):
        if not food_list:
            return []
        result = []
        for food in food_list:
            result.append(
                {
                    "id": getattr(food, "id", ""),
                    "name": getattr(food, "name", ""),
                    "labels": [
                        {
                            "id": getattr(label, "id", ""),
                            "name": getattr(label, "name", ""),
                            "color": getattr(label, "color", ""),
                        }
                        for label in getattr(food, "labels", [])
                    ],
                }
            )
        return result

    return {
        "id": getattr(menu, "id", ""),
        "name": getattr(menu, "name", ""),
        "date": menu.date.strftime("%Y-%m-%d") if getattr(menu, "date", None) else "",
        "is_lunch": getattr(menu, "is_lunch", False),
        "is_dinner": getattr(menu, "is_dinner", False),
        "first_meal": serialize_food_list(getattr(menu, "first_meal", [])),
        "main_meal": serialize_food_list(getattr(menu, "main_meal", [])),
        "side_meal": serialize_food_list(getattr(menu, "side_meal", [])),
        "other_meal": serialize_food_list(getattr(menu, "other_meal", [])),
        "cheese": serialize_food_list(getattr(menu, "cheese", [])),
        "dessert": serialize_food_list(getattr(menu, "dessert", [])),
    }


def build_cours_data(lesson_data):
    """
    Construit un dictionnaire contenant les informations formatées d'un cours.
    Args:
        lesson_data (object): Un objet représentant les données d'un cours.
    Returns:
        dict: Un dictionnaire contenant les informations formatées du cours.
    """
    return {
        "id": lesson_data.id,
        "date_heure": lesson_data.start.strftime("%d/%m/%Y, %H:%M"),
        "date": lesson_data.start.strftime("%d/%m/%Y"),
        "heure": lesson_data.start.strftime("%H%M"),
        "heure_fin": lesson_data.end.strftime("%H%M"),
        "cours": cours_affiche_from_lesson(lesson_data),
        "Professeur": lesson_data.teacher_name,
        "salle": lesson_data.classroom,
        "annulation": lesson_data.canceled,
        "status": lesson_data.status,
        "background_color": lesson_data.background_color,
        "est_service_groupe": getattr(lesson_data, "estServiceGroupe", None),
        "cahier_de_texte": getattr(lesson_data, "cahierDeTextes", None),
        "est_retenue": getattr(lesson_data, "estRetenue", None),
        "liste_visios": getattr(lesson_data, "listeVisios", None),
        "dispense_eleve": getattr(lesson_data, "dispenseEleve", None),
        "est_sortie_pedagogique": getattr(lesson_data, "estSortiePedagogique", None),
        "est_Annule": getattr(lesson_data, "estAnnule", None),
    }


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


def Emploidutemps(client):
    try:
        # Emploi du temps : aujourd'hui + 4 prochains jours scolaires (v0.9b : 1 appel batch sur 14j)
        # Récupération  emploi du temps du jour
        lessons_today = client.lessons(datetime.date.today())
        data = {
            "edt_aujourdhui": [],
            "edt_aujourdhui_debut": "",
            "edt_aujourdhui_fin": "",
            "edt_aujourdhui_cancel": 0,
        }
        lessons_today = sorted(lessons_today, key=lambda lesson: lesson.start)
        if lessons_today:
            for lesson in lessons_today:
                index = lessons_today.index(lesson)
                if (
                    lesson.start != lessons_today[index - 1].start
                    or lesson.canceled != True
                ):
                    data["edt_aujourdhui"].append(build_cours_data(lesson))
                if lesson.canceled == False and data["edt_aujourdhui_debut"] == "":
                    data["edt_aujourdhui_debut"] = lesson.start.strftime("%H%M")
                if lesson.canceled == True:
                    data["edt_aujourdhui_cancel"] = data["edt_aujourdhui_cancel"] + 1
            data["edt_aujourdhui_fin"] = lesson.end.strftime("%H%M")

        # Récupération des 4 prochains jours scolaires (1 seul appel API sur 28 jours
        # pour couvrir les vacances scolaires de 2 semaines)
        try:
            lessons_range = client.lessons(
                datetime.date.today() + datetime.timedelta(days=1),
                datetime.date.today() + datetime.timedelta(days=28),
            )
        except Exception as e:
            logging.warning(f"Impossible de récupérer les jours suivants : {e}")
            lessons_range = []

        # Grouper les cours par date
        days_by_date = {}
        for lesson in lessons_range or []:
            d = lesson.start.date() if hasattr(lesson.start, "date") else lesson.start
            if d not in days_by_date:
                days_by_date[d] = []
            days_by_date[d].append(lesson)

        # Prendre les 4 premières dates avec cours
        next_school_dates = sorted(days_by_date.keys())[:4]

        # Initialiser les 4 slots à vide
        for i in range(1, 5):
            key = f"edt_J{i}"
            data[key] = []
            data[f"{key}_date"] = ""
            data[f"{key}_debut"] = ""
            data[f"{key}_fin"] = ""
            data[f"{key}_cancel"] = 0

        # Remplir les slots disponibles
        for i, school_date in enumerate(next_school_dates, 1):
            key = f"edt_J{i}"
            lessons = sorted(days_by_date[school_date], key=lambda l: l.start)
            data[f"{key}_date"] = school_date.strftime("%d/%m/%Y")
            for lesson in lessons:
                index = lessons.index(lesson)
                if lesson.start != lessons[index - 1].start or lesson.canceled != True:
                    lesson_to_append = build_cours_data(lesson)
                    lesson_to_append["index"] = index
                    data[key].append(lesson_to_append)
                if lesson.canceled == True:
                    data[f"{key}_cancel"] += 1
                if lesson.canceled == False and data[f"{key}_debut"] == "":
                    data[f"{key}_debut"] = lesson.start.strftime("%H%M")
            if lessons:
                data[f"{key}_fin"] = lessons[-1].end.strftime("%H%M")

        # Rétro-compatibilité : edt_prochainjour = J1
        data["edt_prochainjour"] = data["edt_J1"]
        data["edt_prochainjour_date"] = data["edt_J1_date"]
        data["edt_prochainjour_debut"] = data["edt_J1_debut"]
        data["edt_prochainjour_fin"] = data["edt_J1_fin"]
        data["edt_prochainjour_cancel"] = data["edt_J1_cancel"]

        # Tableau compact pour le widget (évite de répliquer les données)
        data["edt_next_days"] = []
        for i in range(1, 5):
            key = f"edt_J{i}"
            if data[f"{key}_date"]:
                data["edt_next_days"].append(
                    {
                        "cours": data[key],
                        "date": data[f"{key}_date"],
                        "debut": data[f"{key}_debut"],
                        "fin": data[f"{key}_fin"],
                        "cancel": data[f"{key}_cancel"],
                    }
                )

        # Récupération emploi du jour courant (date spécifique)
        lessons_specific = client.lessons(datetime.date.today())
        lessons_specific = sorted(lessons_specific, key=lambda lesson: lesson.start)

        data["edt_date_specific"] = []
        if lessons_specific:
            for lesson in lessons_specific:
                index = lessons_specific.index(lesson)
                if lesson.start == lessons_specific[index - 1].start:
                    lesson.num
                else:
                    lesson_to_append = build_cours_data(lesson)
                    lesson_to_append["index"] = index
                    lesson_to_append["num"] = lesson.num
                    data["edt_date_specific"].append(lesson_to_append)

        # Récupération  emploi du temps global de la période en cours
        try:
            lessons_full = client.lessons(
                client.current_period.start, datetime.date.today()
            )
        except Exception as e:
            logging.error(f"Erreur lors de l'accès à l'emploi du temps global : {e}")
            lessons_full = []
        lessons_full = sorted(lessons_full, key=lambda lesson: lesson.start)

        # data["edt_period_full"] = []
        # data["edt_absent_full"] = []
        data["edt_Cours_canceled"] = 0
        if lessons_full:
            for lesson in lessons_full:
                # lesson_to_append = build_cours_data(lesson)
                # lesson_to_append["index"] = index
                # lesson_to_append["num"] = lesson.num
                # data["edt_period_full"].append(lesson_to_append)
                if lesson.canceled == True:
                    # data["edt_absent_full"].append(lesson_to_append)
                    data["edt_Cours_canceled"] += 1
        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "unknown"
        error_msg = f"Erreur lors de la récupération de l'emploi du temps : ligne {line_number} - {str(e)}"
        logging.error(error_msg)
        return {"error": error_msg}


def _menu_to_text(menu_data):
    """Convertit un menu sérialisé (build_menu_data) en chaîne lisible.

    Format : "Entrée · Plat · Accompagnement · Fromage · Dessert"
    Les sections vides sont omises. Renvoie "" si aucun aliment.
    """
    sections = []
    for key in ("first_meal", "main_meal", "side_meal", "cheese", "dessert", "other_meal"):
        items = menu_data.get(key) or []
        names = [str(item.get("name", "")).strip() for item in items if item.get("name")]
        names = [n for n in names if n]
        if names:
            sections.append(", ".join(names))
    return " · ".join(sections)


def _menu_labels(menu_data):
    """Liste dédupliquée des labels/allergènes d'un menu (dans l'ordre d'apparition).

    Les labels Pronote (Bio, Local, Porc, Allergènes…) sont déjà sérialisés par
    build_menu_data sous chaque aliment. On les agrège au niveau du menu pour
    un affichage compact dans le widget.
    """
    seen = []
    for key in ("first_meal", "main_meal", "side_meal", "cheese", "dessert", "other_meal"):
        for item in menu_data.get(key) or []:
            for label in item.get("labels") or []:
                name = str(label.get("name", "")).strip()
                if name and name not in seen:
                    seen.append(name)
    return seen


def _menu_to_html_row(menu_data):
    """Une ligne HTML compacte représentant un menu pour le widget."""
    import html as _html_mod

    date_iso = menu_data.get("date", "")
    is_lunch = menu_data.get("is_lunch", False)
    is_dinner = menu_data.get("is_dinner", False)
    repas_label = "🍽️ Midi" if is_lunch else ("🌙 Soir" if is_dinner else "🍴 Repas")
    text = _menu_to_text(menu_data) or "—"

    # Labels / allergènes (Bio, Local, Porc…) en puces discrètes.
    labels = _menu_labels(menu_data)
    labels_html = ""
    if labels:
        chips = "".join(
            f'<span class="pj-menu-label">{_html_mod.escape(name)}</span>' for name in labels
        )
        labels_html = f'<span class="pj-menu-labels">{chips}</span>'

    return (
        f'<div class="pj-menu-row">'
        f'<span class="pj-menu-date">{_html_mod.escape(date_iso)}</span>'
        f'<span class="pj-menu-type">{_html_mod.escape(repas_label)}</span>'
        f'<span class="pj-menu-text">{_html_mod.escape(text)}</span>'
        f"{labels_html}"
        f"</div>"
    )


def menus(client):
    """Collecte les menus cantine sur 7 jours et construit les agrégats widget.

    Retourne un dict avec :
      - menu_midi_aujourdhui : texte lisible du menu de midi du jour (ou "")
      - menu_midi_demain     : idem pour le lendemain
      - menu_semaine         : HTML compact des 7 prochains jours
      - Nb_menus_semaine     : nombre de menus dans la fenêtre
      - menus_brut           : liste complète des menus sérialisés (build_menu_data)

    pronotepy v2.14+ : client.menus(date_from, date_to=None) → List[Menu]
    En cas d'erreur, retourne un dict avec clé 'error' et valeurs neutres
    (pattern d'isolation des erreurs par feature, cf. notes, devoirs…).
    """
    today = datetime.date.today()
    week_end = today + datetime.timedelta(days=7)
    empty = {
        "menu_midi_aujourdhui": "",
        "menu_midi_demain": "",
        "menu_semaine": "",
        "Nb_menus_semaine": 0,
        "menus_brut": [],
    }
    try:
        menu_list = client.menus(today, week_end)
    except TypeError:
        # Compat ancienne signature : un seul argument
        try:
            menu_list = client.menus(today)
        except Exception as e:
            logging.error("Erreur lors de l'appel client.menus : %s", e)
            empty["error"] = f"Erreur d'accès aux menus : {e}"
            return empty
    except Exception as e:
        logging.error("Erreur lors de l'appel client.menus : %s", e)
        empty["error"] = f"Erreur d'accès aux menus : {e}"
        return empty

    if not menu_list:
        logging.info("Aucun menu cantine trouvé pour la fenêtre %s → %s.", today, week_end)
        return empty

    try:
        menu_list = sorted(menu_list, key=lambda m: m.date)
    except Exception:
        pass

    menus_brut = []
    for menu in menu_list:
        try:
            menus_brut.append(build_menu_data(menu))
        except Exception as e:
            logging.error("Erreur sérialisation menu : %s", e)

    tomorrow = today + datetime.timedelta(days=1)
    today_iso = today.strftime("%Y-%m-%d")
    tomorrow_iso = tomorrow.strftime("%Y-%m-%d")

    menu_midi_today = ""
    menu_midi_tomorrow = ""
    for m in menus_brut:
        if not m.get("is_lunch"):
            continue
        if m.get("date") == today_iso and not menu_midi_today:
            menu_midi_today = _menu_to_text(m)
        elif m.get("date") == tomorrow_iso and not menu_midi_tomorrow:
            menu_midi_tomorrow = _menu_to_text(m)

    menu_semaine_html = "".join(_menu_to_html_row(m) for m in menus_brut)

    return {
        "menu_midi_aujourdhui": menu_midi_today,
        "menu_midi_demain": menu_midi_tomorrow,
        "menu_semaine": menu_semaine_html,
        "Nb_menus_semaine": len(menus_brut),
        "menus_brut": menus_brut,
    }


def _truncate(text, max_len=200):
    """Tronque proprement un texte avec ellipse."""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _safe_attr(obj, *names, default=""):
    """Renvoie le premier attribut existant et non-vide parmi `names`.

    Utile pour pronotepy qui peut renommer/déplacer des attributs entre versions.
    """
    for name in names:
        try:
            val = getattr(obj, name, None)
            if val not in (None, ""):
                return val
        except Exception:
            continue
    return default


def messages(client):
    """Collecte les discussions Pronote (messagerie) et construit les agrégats widget.

    Retourne un dict avec :
      - Nb_messages_non_lus       : compteur entier
      - dernier_message_expediteur: nom du créateur du dernier message
      - dernier_message_sujet     : objet (sujet) du dernier message
      - dernier_message_date      : date formatée dd/mm/yyyy HH:MM
      - dernier_message_extrait   : contenu tronqué (200 caractères)
      - messages_html             : liste HTML compacte des discussions pour widget
      - Nb_messages               : compteur total des discussions visibles
      - messages_brut             : liste structurée des discussions

    pronotepy : Client.discussions() → List[Discussion]
    Pattern d'isolation des erreurs (cf. menus, notes…).
    """
    import html as _html_mod

    empty = {
        "Nb_messages": 0,
        "Nb_messages_non_lus": 0,
        "dernier_message_expediteur": "",
        "dernier_message_sujet": "",
        "dernier_message_date": "",
        "dernier_message_extrait": "",
        "messages_html": "",
        "messages_brut": [],
    }

    try:
        # ParentClient peut nécessiter de cibler l'enfant sélectionné. Le client.discussions()
        # fonctionne sur le client courant (élève direct ou child sélectionné via _selected_child).
        discussions = client.discussions()
    except AttributeError:
        logging.info("pronotepy : client.discussions() indisponible — messagerie ignorée.")
        return empty
    except Exception as e:
        logging.error("Erreur lors de l'accès aux discussions Pronote : %s", e)
        empty["error"] = f"Erreur d'accès à la messagerie : {e}"
        return empty

    if not discussions:
        logging.info("Aucune discussion Pronote retournée.")
        return empty

    messages_brut = []
    for disc in discussions:
        try:
            subject = _safe_attr(disc, "subject", default="(sans objet)")
            creator = _safe_attr(disc, "creator", "sender", default="")
            # Date du dernier message — selon pronotepy, attribut date ou date_last_message
            raw_date = _safe_attr(disc, "date", "date_last_message", default=None)
            date_str = ""
            date_sort = ""  # Clé de tri chronologique (ISO ou epoch string)
            if raw_date:
                try:
                    date_str = raw_date.strftime("%d/%m/%Y %H:%M")
                except Exception:
                    date_str = str(raw_date)
                try:
                    # ISO 8601 trie lexicographiquement = chronologiquement
                    date_sort = raw_date.strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    date_sort = str(raw_date)

            unread = bool(_safe_attr(disc, "unread", default=0))
            participants_count = 0
            try:
                participants = _safe_attr(disc, "participants", default=[]) or []
                participants_count = len(participants)
            except Exception:
                participants_count = 0

            # Contenu : Discussion.messages est généralement une List[Message]
            last_content = ""
            try:
                msg_list = _safe_attr(disc, "messages", default=[]) or []
                if msg_list:
                    last_msg = msg_list[-1]
                    last_content = _safe_attr(last_msg, "content", "body", default="")
            except Exception:
                last_content = ""

            messages_brut.append(
                {
                    "subject": str(subject),
                    "creator": str(creator),
                    "date": date_str,
                    "_date_sort": date_sort,  # interne, retiré avant retour
                    "unread": unread,
                    "participants_count": participants_count,
                    "extrait": _truncate(last_content, 200),
                }
            )
        except Exception as e:
            logging.error("Erreur sérialisation discussion : %s", e)

    # « dernier message » = le plus récent chronologiquement, indépendamment du statut lu.
    # Calcul avant tri d'affichage pour ne pas dépendre de l'ordre final.
    dernier = {}
    if messages_brut:
        try:
            dernier = max(messages_brut, key=lambda m: m.get("_date_sort") or "")
        except Exception:
            dernier = messages_brut[0]

    # Tri d'affichage : non-lus d'abord, puis du plus récent au plus ancien.
    # On utilise _date_sort (ISO 8601) qui se trie correctement lexicographiquement.
    try:
        messages_brut.sort(
            key=lambda m: (0 if m["unread"] else 1, m.get("_date_sort") or ""),
            reverse=False,
        )
        # Si deux messages ont le même statut lu/non-lu, on veut le plus récent en premier ;
        # le tri ci-dessus met le plus ancien en premier dans un groupe. On inverse par groupe.
        messages_brut = sorted(
            messages_brut,
            key=lambda m: (0 if m["unread"] else 1, -1),
        )
        # Re-trier finalement avec un comparateur composite : groupes par unread, puis date desc.
        from functools import cmp_to_key

        def _msg_cmp(a, b):
            # Non-lus avant lus
            ua, ub = (0 if a["unread"] else 1), (0 if b["unread"] else 1)
            if ua != ub:
                return ua - ub
            # Date décroissante (plus récent en premier)
            da, db = a.get("_date_sort") or "", b.get("_date_sort") or ""
            if da > db:
                return -1
            if da < db:
                return 1
            return 0

        messages_brut.sort(key=cmp_to_key(_msg_cmp))
    except Exception as e:
        logging.debug("Tri messages : %s", e)

    # Nettoyage : retirer la clé interne _date_sort avant exposition
    for m in messages_brut:
        m.pop("_date_sort", None)
    dernier.pop("_date_sort", None) if isinstance(dernier, dict) else None

    nb_total = len(messages_brut)
    nb_non_lus = sum(1 for m in messages_brut if m["unread"])

    # HTML compact pour le widget — pattern aligné sur les autres listes
    html_parts = []
    for m in messages_brut:
        unread_cls = " pj-msg-unread" if m["unread"] else ""
        html_parts.append(
            f'<div class="pj-msg-row{unread_cls}">'
            f'<div class="pj-msg-head">'
            f'<span class="pj-msg-sender">{_html_mod.escape(m["creator"]) or "—"}</span>'
            f'<span class="pj-msg-date">{_html_mod.escape(m["date"])}</span>'
            f"</div>"
            f'<div class="pj-msg-subject">{_html_mod.escape(m["subject"])}</div>'
            f'<div class="pj-msg-extract">{_html_mod.escape(m["extrait"])}</div>'
            f"</div>"
        )

    return {
        "Nb_messages": nb_total,
        "Nb_messages_non_lus": nb_non_lus,
        "dernier_message_expediteur": dernier.get("creator", ""),
        "dernier_message_sujet": dernier.get("subject", ""),
        "dernier_message_date": dernier.get("date", ""),
        "dernier_message_extrait": dernier.get("extrait", ""),
        "messages_html": "".join(html_parts),
        "messages_brut": messages_brut,
    }


# ── Détection des évaluations / DS dans les devoirs ─────────────────────────
# Pronote ne fournit pas de flag « contrôle » sur Homework. On infère via une
# regex sur la description et le titre.
import re as _re_eval

_EVAL_PATTERN = _re_eval.compile(
    r"\b(contr[ôo]le|DS|[ée]valuation|interro(?:gation)?|test|examen|devoir surveill[ée])\b",
    _re_eval.IGNORECASE,
)


def detect_next_evaluations(all_homework, max_keep=5):
    """Repère les devoirs qui ressemblent à un contrôle/DS et renvoie les prochains.

    Retourne un dict avec :
      - prochain_DS_matiere      : matière du prochain DS (ou "")
      - prochain_DS_date         : date dd/mm/yyyy
      - prochain_DS_dans_jours   : nb jours entre aujourd'hui et le DS (int)
      - prochains_DS_html        : HTML compact des `max_keep` prochains DS
      - prochains_DS_brut        : liste structurée

    Robustesse : si all_homework est vide ou si toutes les entrées échouent
    au parsing, on retourne des valeurs neutres.
    """
    import html as _html_mod

    empty = {
        "prochain_DS_matiere": "",
        "prochain_DS_date": "",
        "prochain_DS_dans_jours": -1,
        "prochains_DS_html": "",
        "prochains_DS_brut": [],
    }
    if not all_homework:
        return empty

    today = datetime.date.today()
    candidats = []

    for hw in all_homework:
        try:
            description = (hw.description or "") if hasattr(hw, "description") else ""
            subject_name = ""
            try:
                subject_name = getattr(hw.subject, "name", "") if hw.subject else ""
            except Exception:
                subject_name = ""

            haystack = f"{subject_name} {description}"
            if not _EVAL_PATTERN.search(haystack):
                continue

            hw_date = getattr(hw, "date", None)
            if hw_date is None or hw_date < today:
                continue

            candidats.append(
                {
                    "matiere": subject_name or "—",
                    "date": hw_date.strftime("%d/%m/%Y"),
                    "date_iso": hw_date.isoformat(),
                    "dans_jours": (hw_date - today).days,
                    "extrait": _truncate(description, 120),
                }
            )
        except Exception as e:
            logging.debug("Detection DS : entrée ignorée (%s)", e)

    if not candidats:
        return empty

    candidats.sort(key=lambda c: c["date_iso"])
    prochain = candidats[0]

    top = candidats[:max_keep]
    html_parts = []
    for c in top:
        html_parts.append(
            f'<div class="pj-ds-row">'
            f'<span class="pj-ds-date">{_html_mod.escape(c["date"])}</span>'
            f'<span class="pj-ds-matiere">{_html_mod.escape(c["matiere"])}</span>'
            f'<span class="pj-ds-extrait">{_html_mod.escape(c["extrait"])}</span>'
            f"</div>"
        )

    return {
        "prochain_DS_matiere": prochain["matiere"],
        "prochain_DS_date": prochain["date"],
        "prochain_DS_dans_jours": prochain["dans_jours"],
        "prochains_DS_html": "".join(html_parts),
        "prochains_DS_brut": top,
    }


def evaluations(client):
    try:
        # Récupération des évaluations
        try:
            evaluations = client.current_period.evaluations
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux évaluations : {e}")
            return {
                "evaluations": [],
                "error": f"Erreur d'accès aux évaluations : {str(e)}",
            }
        data = {
            "evaluations": [],
        }
        if evaluations == []:
            return data
        for evaluation in evaluations:

            def acquisition_to_dict(acq):
                # Si c'est déjà un dict, on le retourne
                if isinstance(acq, dict):
                    return acq
                # Sinon, on extrait les attributs principaux
                return {
                    "ordre": getattr(acq, "order", ""),
                    "name": getattr(acq, "name", ""),
                    "name_id": getattr(acq, "name_id", ""),
                    "abbreviation": getattr(acq, "abbreviation", ""),
                    "level": getattr(acq, "level", ""),
                    "coefficient": getattr(acq, "coefficient", ""),
                    "domain": getattr(acq, "domain", ""),
                    "domain_id": getattr(acq, "domain_id", ""),
                    "pillar": getattr(acq, "pillar", ""),
                    "pillar_id": getattr(acq, "pillar_id", ""),
                }

            # Si c'est un dict, on convertit ses valeurs
            if isinstance(evaluation.acquisitions, dict):
                acquisitions = {
                    k: acquisition_to_dict(v)
                    for k, v in evaluation.acquisitions.items()
                }
            # Si c'est une liste
            elif isinstance(evaluation.acquisitions, list):
                acquisitions = [acquisition_to_dict(a) for a in evaluation.acquisitions]
            else:
                acquisitions = evaluation.acquisitions

            try:
                sujet_name = getattr(evaluation.subject, "name", "Inconnu")
            except Exception:
                sujet_name = "Inconnu"
            data["evaluations"].append(
                {
                    "id": evaluation.id,
                    "nom": evaluation.name,
                    "domaine": evaluation.domain,
                    "professeur": evaluation.teacher,
                    "Sujet": sujet_name,
                    "date": evaluation.date.strftime("%d/%m/%Y"),
                    "acquisitions": acquisitions,
                    "description": evaluation.description,
                    "Paliers": evaluation.paliers,
                    "coeff": evaluation.coefficient,
                }
            )
        return data["evaluations"]
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Une erreur est retournée sur le traitement des évaluations-lig: %s; %s",
            line_number,
            e,
        )
        time.sleep(5)


def compute_moyenne_generale(note_list):
    """Moyenne générale pondérée sur 20, calculée à partir de la liste de notes.

    Reprend la logique du widget : chaque note est ramenée sur 20 puis pondérée
    par son coefficient. Sont exclues les notes non numériques, à dénominateur
    nul ou négatif, et de coefficient nul ou négatif (bonus / optionnel).

    Args:
        note_list (list[dict]): notes sérialisées (clés note, sur, coeff).
    Returns:
        float | None: moyenne arrondie à 2 décimales, ou None si aucune note exploitable.
    """
    tot = 0.0
    coefs = 0.0
    for n in note_list or []:
        try:
            note_f = float(str(n.get("note", "")).replace(",", "."))
        except (ValueError, AttributeError):
            continue
        sur_str = str(n.get("sur", "20")).replace(",", ".") or "20"
        try:
            sur_f = float(sur_str)
        except ValueError:
            sur_f = 20.0
        try:
            coeff_f = float(str(n.get("coeff", "1")).replace(",", "."))
        except ValueError:
            coeff_f = 1.0
        if sur_f <= 0 or coeff_f <= 0:
            continue
        tot += (note_f / sur_f) * 20.0 * coeff_f
        coefs += coeff_f
    if coefs <= 0:
        return None
    return round(tot / coefs, 2)


def detect_subject_trends(note_list, min_notes=4, drop_threshold=2.0):
    """Détecte les matières en baisse à partir des notes (ramenées sur 20).

    Pour chaque matière comptant au moins `min_notes` notes numériques, compare
    la moyenne de la moitié la plus récente à celle de la moitié la plus ancienne.
    Une chute supérieure ou égale à `drop_threshold` points (sur 20) signale une
    matière en baisse.

    `note_list` est attendue triée du plus récent au plus ancien (cf. notes()).

    Returns:
        dict avec :
          - matiere_en_baisse        : noms séparés par " · " (ou "")
          - matiere_en_baisse_detail : liste [{matiere, ancienne_moyenne, recente_moyenne, delta}]
    """
    empty = {"matiere_en_baisse": "", "matiere_en_baisse_detail": []}
    if not note_list:
        return empty

    by_subject = {}
    for n in note_list:
        try:
            note_f = float(str(n.get("note", "")).replace(",", "."))
            sur_f = float(str(n.get("sur", "20")).replace(",", ".") or "20")
        except (ValueError, AttributeError):
            continue
        if sur_f <= 0:
            continue
        subj = n.get("cours", "Inconnu") or "Inconnu"
        by_subject.setdefault(subj, []).append((note_f / sur_f) * 20.0)

    detail = []
    for subj, notes20 in by_subject.items():
        if len(notes20) < min_notes:
            continue
        # notes20 va du plus récent au plus ancien → remettre en ordre chronologique
        chrono = list(reversed(notes20))
        half = len(chrono) // 2
        anciennes = chrono[:half]
        recentes = chrono[len(chrono) - half:]
        if not anciennes or not recentes:
            continue
        moy_anc = sum(anciennes) / len(anciennes)
        moy_rec = sum(recentes) / len(recentes)
        if (moy_anc - moy_rec) >= drop_threshold:
            detail.append(
                {
                    "matiere": subj,
                    "ancienne_moyenne": round(moy_anc, 2),
                    "recente_moyenne": round(moy_rec, 2),
                    "delta": round(moy_rec - moy_anc, 2),
                }
            )

    detail.sort(key=lambda d: d["delta"])  # plus forte baisse en premier
    return {
        "matiere_en_baisse": " · ".join(d["matiere"] for d in detail),
        "matiere_en_baisse_detail": detail,
    }


# ── Détection des nouveautés (P3, v1.1.0) ───────────────────────────────────
# À chaque sync, on compare les items courants (notes, devoirs, punitions,
# absences) à un index « déjà vu » persisté par équipement. Les nouveautés
# alimentent des commandes Jeedom qui déclenchent les scénarios utilisateur.

def _item_signature(item, *fields):
    """Signature stable d'un item à partir de champs sélectionnés."""
    return "|".join(str(item.get(f, "")) for f in fields)


def _sig_of(item, kind):
    """Identifiant stable d'un item selon son type (id Pronote si disponible)."""
    sid = item.get("id")
    has_id = sid not in (None, "")
    if kind == "notes":
        return str(sid) if has_id else "n:" + _item_signature(item, "cours", "date", "note", "sur", "commentaire")
    if kind == "devoirs":
        # Les devoirs n'ont pas d'id Pronote stable exposé → signature de contenu.
        return "d:" + _item_signature(item, "date", "title", "description")
    if kind == "punitions":
        return "p:" + (str(sid) if has_id else _item_signature(item, "date", "raison", "type"))
    if kind == "absences":
        return "a:" + (str(sid) if has_id else _item_signature(item, "date_debut", "date_fin"))
    return _item_signature(item, "id")


def format_new_note_label(note):
    """Libellé lisible d'une nouvelle note. Ex : 'Maths : 16/20 — DS trigonométrie'."""
    cours = str(note.get("cours", "")).strip() or "?"
    note_sur = str(note.get("note_sur", "")).replace(" ", " ").strip()
    if not note_sur:
        n = str(note.get("note", "")).strip()
        s = str(note.get("sur", "")).strip()
        note_sur = f"{n}/{s}" if n and s else n
    comm = str(note.get("commentaire", "")).strip()
    label = f"{cours} : {note_sur}" if note_sur else cours
    if comm:
        label += f" — {comm}"
    return label


def format_new_devoir_label(dv):
    """Libellé lisible d'un nouveau devoir. Ex : 'Maths (12/03) : exercices p.42'."""
    matiere = str(dv.get("title", "")).strip() or "?"
    date = str(dv.get("date", "")).strip()
    desc = str(dv.get("description", "")).strip()
    head = f"{matiere} ({date})" if date else matiere
    return f"{head} : {desc}" if desc else head


def compute_deltas(seen_index, notes_list, devoirs_list, punitions_list, absences_list):
    """Compare les items courants à l'index « déjà vu » précédent.

    Retourne (deltas, new_index). Au PREMIER passage (index vide/absent), aucun
    delta n'est émis : on n'enregistre que la baseline pour éviter une avalanche
    de notifications au branchement initial (même logique que le centre d'alertes).

    deltas contient les compteurs de nouveautés et les libellés de la dernière
    nouvelle note / du dernier nouveau devoir (vides si rien de neuf).
    """
    kinds = (
        ("notes", notes_list, "nouvelles_notes"),
        ("devoirs", devoirs_list, "nouveaux_devoirs"),
        ("punitions", punitions_list, "nouvelles_punitions"),
        ("absences", absences_list, "nouvelles_absences"),
    )
    new_index = {kind: [_sig_of(it, kind) for it in (lst or [])] for kind, lst, _ in kinds}

    deltas = {
        "nouvelles_notes": 0,
        "nouveaux_devoirs": 0,
        "nouvelles_punitions": 0,
        "nouvelles_absences": 0,
        "derniere_nouvelle_note": "",
        "dernier_nouveau_devoir": "",
    }
    if not seen_index:
        return deltas, new_index  # premier passage : baseline seulement

    for kind, lst, count_key in kinds:
        seen = set(seen_index.get(kind, []))
        new_sigs = [s for s in new_index[kind] if s not in seen]
        deltas[count_key] = len(new_sigs)

    new_notes = {s for s in new_index["notes"] if s not in set(seen_index.get("notes", []))}
    if new_notes:
        for n in notes_list or []:
            if _sig_of(n, "notes") in new_notes:
                deltas["derniere_nouvelle_note"] = format_new_note_label(n)
                break

    new_dev = {s for s in new_index["devoirs"] if s not in set(seen_index.get("devoirs", []))}
    if new_dev:
        for d in devoirs_list or []:
            if _sig_of(d, "devoirs") in new_dev:
                deltas["dernier_nouveau_devoir"] = format_new_devoir_label(d)
                break

    return deltas, new_index


def _load_seen_index(data_dir, eq_id):
    """Charge l'index « déjà vu » d'un équipement (dict, {} si absent/illisible)."""
    path = os.path.join(str(data_dir), str(eq_id), "seen_index.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_seen_index(data_dir, eq_id, index):
    """Persiste l'index « déjà vu » d'un équipement."""
    folder = os.path.join(str(data_dir), str(eq_id))
    try:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "seen_index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f)
    except Exception as e:
        logging.error("Impossible d'écrire seen_index.json (eq %s) : %s", eq_id, e)


def notes(client):
    """
    Récupère toutes les notes de l'année scolaire (toutes périodes) et les formate en JSON.
    """
    try:
        data = {"note": [], "derniere_note": [], "moyennes_periodes": []}

        try:
            all_periods = client.periods
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux périodes : {e}")
            return {"note": [], "derniere_note": [], "error": str(e)}

        all_grades = []
        for period in all_periods:
            try:
                period_grades = period.grades
                period_name = getattr(period, "name", "")
                for grade in period_grades or []:
                    all_grades.append((grade, period_name))
            except Exception as e:
                logging.warning(
                    f"Impossible de lire les notes de la période {getattr(period, 'name', '?')} : {e}"
                )

            # Moyennes générales par période (élève + classe)
            try:
                period_name = getattr(period, "name", "?")
                moy_eleve_raw = getattr(period, "overall_average", "") or ""
                moy_classe_raw = getattr(period, "class_overall_average", "") or ""
                logging.debug(
                    "Moyenne brute Pronote — période=%s  élève=%r  classe=%r",
                    period_name, moy_eleve_raw, moy_classe_raw,
                )
                moy_eleve = moy_eleve_raw
                moy_classe = moy_classe_raw
                # Pronote retourne "-1" comme sentinelle quand la moyenne n'est pas disponible
                if str(moy_eleve).strip() == "-1":
                    logging.debug("Moyenne élève ignorée (sentinelle -1) — période=%s", period_name)
                    moy_eleve = ""
                if str(moy_classe).strip() == "-1":
                    logging.debug("Moyenne classe ignorée (sentinelle -1) — période=%s", period_name)
                    moy_classe = ""
                if moy_eleve or moy_classe:
                    logging.debug(
                        "Moyenne retenue — période=%s  élève=%s  classe=%s",
                        period_name,
                        str(moy_eleve).replace(",", "."),
                        str(moy_classe).replace(",", "."),
                    )
                    data["moyennes_periodes"].append(
                        {
                            "periode": period_name,
                            "moyenne_eleve": str(moy_eleve).replace(",", "."),
                            "moyenne_classe": str(moy_classe).replace(",", "."),
                        }
                    )
                else:
                    logging.debug("Aucune moyenne disponible pour la période=%s", period_name)
            except Exception:
                pass

        if all_grades:
            # Tri toutes périodes confondues, du plus récent au plus ancien
            all_grades = sorted(
                all_grades,
                key=lambda x: getattr(x[0], "date", datetime.date.min),
                reverse=True,
            )

            for grade, period_name in all_grades:
                cours_name = "Inconnu"
                if hasattr(grade, "subject") and grade.subject:
                    cours_name = getattr(grade.subject, "name", "Inconnu")

                note_value = getattr(grade, "grade", "")
                out_of_value = getattr(grade, "out_of", "")
                note_sur = (
                    f"{note_value}\u00a0/\u00a0{out_of_value}"
                    if note_value and out_of_value
                    else ""
                )
                grade_date = getattr(grade, "date", None) or datetime.date.today()

                # Pronote renvoie parfois des objets {"V": valeur} au lieu de scalaires
                coeff_raw = getattr(grade, "coefficient", "1")
                if isinstance(coeff_raw, dict):
                    coeff_raw = coeff_raw.get("V", "1")
                comment_raw = getattr(grade, "comment", "")
                if isinstance(comment_raw, dict):
                    comment_raw = comment_raw.get("V", "")

                data["note"].append(
                    {
                        "id": getattr(grade, "id", ""),
                        "periode": period_name,
                        "date": grade_date.strftime("%d/%m/%Y"),
                        "date_courte": grade_date.strftime("%d/%m"),
                        "cours": cours_name,
                        "note": str(note_value).replace(",", "."),
                        "sur": str(out_of_value).replace(",", "."),
                        "note_sur": note_sur,
                        "coeff": str(coeff_raw).replace(",", "."),
                        "moyenne_classe": str(getattr(grade, "average", "")).replace(
                            ",", "."
                        ),
                        "max": str(getattr(grade, "max", "")).replace(",", "."),
                        "min": str(getattr(grade, "min", "")).replace(",", "."),
                        "commentaire": str(comment_raw),
                        "optionnel": getattr(grade, "is_optionnal", False),
                        "bonus": getattr(grade, "is_bonus", False),
                    }
                )

            if data["note"]:
                data["derniere_note"].append(data["note"][0])

            # ── Moyenne générale + détection des matières en baisse (F3, v1.1.0) ─
            moy_gen = compute_moyenne_generale(data["note"])
            data["moyenne_generale"] = "" if moy_gen is None else str(moy_gen)
            data.update(detect_subject_trends(data["note"]))

            # ── Calcul debug de la moyenne (même logique que le widget JS) ──────
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                tot = 0.0
                coefs = 0.0
                skipped = 0
                logging.debug("── Détail calcul moyenne générale (%d notes) ──", len(data["note"]))
                for n in data["note"]:
                    note_str = str(n.get("note", "")).replace(",", ".")
                    sur_str  = str(n.get("sur",  "20")).replace(",", ".") or "20"
                    coeff_str = str(n.get("coeff", "1")).replace(",", ".")
                    try:
                        note_f  = float(note_str)
                        sur_f   = float(sur_str) if sur_str else 20.0
                        coeff_f = float(coeff_str) if coeff_str else 1.0
                    except ValueError:
                        logging.debug(
                            "  IGNORÉE  %-30s  %s — valeur non numérique (note=%r sur=%r coeff=%r)",
                            n.get("cours", "?"), n.get("date", "?"),
                            n.get("note"), n.get("sur"), n.get("coeff"),
                        )
                        skipped += 1
                        continue
                    if sur_f <= 0:
                        logging.debug(
                            "  IGNORÉE  %-30s  %s — dénominateur nul ou négatif (sur=%s)",
                            n.get("cours", "?"), n.get("date", "?"), sur_str,
                        )
                        skipped += 1
                        continue
                    contribution = (note_f / sur_f) * 20.0 * coeff_f
                    tot   += contribution
                    coefs += coeff_f
                    logging.debug(
                        "  INCLUSE  %-30s  %s  note=%s/%s  coeff=%s  contrib=%.4f  (tot=%.4f coefs=%.2f)",
                        n.get("cours", "?"), n.get("date", "?"),
                        note_str, sur_str, coeff_str,
                        contribution, tot, coefs,
                    )
                if coefs > 0:
                    moy_calc = tot / coefs
                    logging.debug(
                        "── Résultat calcul : %.2f/20  (%d notes incluses, %d ignorées) ──",
                        moy_calc, len(data["note"]) - skipped, skipped,
                    )
                else:
                    logging.debug("── Résultat calcul : aucune note valide ──")
        else:
            logging.info("Aucune note trouvée pour l'année scolaire.")

        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "unknown"
        error_msg = (
            f"Erreur lors de la récupération des notes : ligne {line_number} - {str(e)}"
        )
        logging.error(error_msg)
        logging.debug(traceback.format_exc())
        return {"note": [], "derniere_note": [], "error": error_msg}


def process_homework(homework_list, data, key):
    if not homework_list:
        logging.info(f"Aucun devoir trouvé pour {key}.")
        data[f"Nb_{key}"] = 0
        data[f"Nb_{key}_F"] = 0
        data[f"Nb_{key}_NF"] = 0
        return 0, 0, 0

    Devoir = 0
    Devoirfait = 0
    Devoirnonfait = 0

    for homework in homework_list:
        try:
            title = (
                getattr(homework.subject, "name", "Inconnu")
                if homework.subject
                else "Inconnu"
            )
        except Exception:
            title = "Inconnu"

        # Description : Util.html_parse est patché pour préserver les espaces inter-mots
        description = homework.description or ""

        # Pièces jointes et liens
        fichiers = []
        try:
            for f in homework.files:
                fichiers.append(
                    {
                        "nom": f.name,
                        "url": f.url,
                        "type": f.type,  # 0 = lien externe, 1 = fichier Pronote
                    }
                )
        except Exception:
            pass

        data[key].append(
            {
                "index": homework_list.index(homework),
                "date": homework.date.strftime("%d/%m"),
                "title": title,
                "description": description,
                "color": homework.background_color,
                "done": homework.done,
                "fichiers": fichiers,
            }
        )
        Devoir += 1
        if homework.done == 1:
            Devoirfait += 1
        else:
            Devoirnonfait += 1

    data[f"Nb_{key}"] = Devoir
    data[f"Nb_{key}_F"] = Devoirfait
    data[f"Nb_{key}_NF"] = Devoirnonfait

    return Devoir, Devoirfait, Devoirnonfait


def devoirs(client):
    try:
        data = {"devoir": [], "devoir_Demain": []}

        # Supposons que cette méthode récupère tous les devoirs pour une période donnée
        all_homework = client.homework(
            date_from=datetime.date.today(),
            date_to=datetime.date.today() + datetime.timedelta(days=120),
        )

        if not all_homework:
            logging.info("Aucun devoir trouvé pour la période spécifiée.")
            for key in ["devoir", "devoir_Demain"]:
                data[f"Nb_{key}"] = 0
                data[f"Nb_{key}_F"] = 0
                data[f"Nb_{key}_NF"] = 0
                data[key] = []
            # Fusionne agrégats DS vides pour cohérence des cmd Jeedom
            data.update(detect_next_evaluations([]))
            time.sleep(5)
            return data

        # Filtrer les devoirs pour aujourd'hui
        today = datetime.date.today()
        homework_today = [hw for hw in all_homework if hw.date == today]

        # Filtrer les devoirs pour le prochain jour d'école
        delta = 1
        next_school_day = None
        while delta < 120:
            next_day = today + datetime.timedelta(days=delta)
            homework_nextday = [hw for hw in all_homework if hw.date == next_day]
            if homework_nextday:
                next_school_day = homework_nextday
                break
            delta += 1
        # Traiter les devoirs pour aujourd'hui
        process_homework(homework_today, data, "devoir")
        # Traiter les devoirs pour le prochain jour d'école
        if next_school_day:
            process_homework(next_school_day, data, "devoir_Demain")
        else:
            logging.info("Aucun devoir trouvé pour le prochain jour d'école.")

        # ── Détection des évaluations / DS à venir ─────────────────────────
        # Pattern heuristique sur l'ensemble des devoirs collectés.
        try:
            data.update(detect_next_evaluations(all_homework))
        except Exception as e:
            logging.error("Erreur detect_next_evaluations : %s", e)
            data.update(detect_next_evaluations([]))

        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Une erreur est retournée sur le traitement des devoirs-ligne: %s; %s",
            line_number,
            e,
        )
        time.sleep(5)
        return data


def notifications(client):
    try:
        data = {"Notification": [], "dernier_Notification": []}
        # Récupération des notifications
        notification_eleve = client.information_and_surveys()
        if not notification_eleve == []:
            notification_eleve = sorted(
                notification_eleve,
                key=lambda information_and_survey: information_and_survey.start_date,
                reverse=True,
            )
            # Récupération des notifications
            for notif in notification_eleve:
                data["Notification"].append(
                    {
                        "sujet": (notif.title),
                        "auteur": (notif.author),
                        "creation": (notif.creation_date).strftime("%d/%m"),
                        "message": (notif.content),
                        "categorie": (notif.category),
                        "lu": (notif.read),
                    }
                )
                # récupération du dernier message
            if data["Notification"]:
                data["dernier_Notification"] = (
                    [data["Notification"][0]] if data["Notification"] else []
                )
            else:
                time.sleep(5)
        return data
    except Exception as e:
        logging.error(
            "Un erreur est retourné sur le traitement des notifications: %s", e
        )


def retards(client):
    try:
        data = {"retard": [], "dernier_retard": [], "nb_retard": 0}
        try:
            all_periods = client.periods
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux périodes (retards) : {e}")
            return {"retard": [], "dernier_retard": [], "nb_retard": 0, "error": str(e)}

        all_retards_map = {}
        for period in all_periods:
            try:
                for d in period.delays or []:
                    all_retards_map[d.id] = d
            except Exception as e:
                logging.warning(
                    f"Impossible de lire les retards de la période {getattr(period, 'name', '?')} : {e}"
                )

        all_retards = list(all_retards_map.values())
        if all_retards:
            all_retards = sorted(
                all_retards, key=lambda delay: delay.date, reverse=True
            )
            for retard in all_retards:
                data["retard"].append(
                    {
                        "id": retard.id,
                        "date": retard.date.strftime("%d/%m/%y %H:%M"),
                        "justifie": retard.justified,
                        "nb_minutes": retard.minutes,
                        "justification": retard.justification or "",
                        "raison": ", ".join(retard.reasons) if retard.reasons else "",
                    }
                )
            data["nb_retard"] = len(data["retard"])
            data["dernier_retard"] = [data["retard"][0]]
        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Un erreur est retourné sur le traitement des retards: %s; %s",
            line_number,
            e,
        )


def absences(client):
    try:
        data = {"absence": [], "nb_absences": 0, "derniere_absence": []}
        try:
            all_periods = client.periods
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux périodes (absences) : {e}")
            return {
                "absence": [],
                "nb_absences": 0,
                "derniere_absence": [],
                "error": str(e),
            }

        all_absences_map = {}
        for period in all_periods:
            try:
                for a in period.absences or []:
                    all_absences_map[a.id] = a
            except Exception as e:
                logging.warning(
                    f"Impossible de lire les absences de la période {getattr(period, 'name', '?')} : {e}"
                )

        all_absences = list(all_absences_map.values())
        if all_absences:
            all_absences = sorted(all_absences, key=lambda a: a.from_date, reverse=True)
            for absence in all_absences:
                data["absence"].append(
                    {
                        "id": absence.id,
                        "date_debut": absence.from_date.strftime("%d/%m/%y %H:%M"),
                        "date_fin": absence.to_date.strftime("%d/%m/%y %H:%M"),
                        "justifie": absence.justified,
                        "nb_heures": absence.hours or "",
                        "nb_jours": absence.days or 0,
                        "raison": ", ".join(absence.reasons) if absence.reasons else "",
                    }
                )
            data["nb_absences"] = len(data["absence"])
            data["derniere_absence"] = [data["absence"][0]]
        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Un erreur est retourné sur le traitement des absences: %s; %s",
            line_number,
            e,
        )
        time.sleep(5)
        return data


def punitions(client):
    try:
        data = {"punition": [], "derniere_punition": [], "Nb_Punitions": 0}
        try:
            all_periods = client.periods
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux périodes (punitions) : {e}")
            return {
                "punition": [],
                "derniere_punition": [],
                "Nb_Punitions": 0,
                "error": str(e),
            }

        all_punitions_map = {}
        for period in all_periods:
            try:
                for p in period.punishments or []:
                    all_punitions_map[p.id] = p
            except Exception as e:
                logging.warning(
                    f"Impossible de lire les punitions de la période {getattr(period, 'name', '?')} : {e}"
                )

        import datetime as _dt

        def _punition_sort_key(p):
            g = p.given
            if isinstance(g, _dt.datetime):
                return g.date()
            return g if isinstance(g, _dt.date) else _dt.date.min

        punitions = (
            sorted(all_punitions_map.values(), key=_punition_sort_key, reverse=True)
            if all_punitions_map
            else []
        )
        if punitions:

            def format_punition(p):
                # Créneaux planifiés (ex : retenues programmées)
                schedule = []
                for s in p.schedule or []:
                    try:
                        start_str = (
                            s.start.strftime("%d/%m %H:%M")
                            if hasattr(s.start, "strftime")
                            else str(s.start)
                        )
                        duree_min = (
                            int(s.duration.total_seconds() // 60)
                            if s.duration
                            else None
                        )
                        schedule.append({"start": start_str, "duree": duree_min})
                    except Exception:
                        pass
                return {
                    "id": p.id,
                    "type": p.nature,
                    "raison": ", ".join(p.reasons) if p.reasons else "",
                    "donneur": p.giver,
                    "date": (
                        p.given.strftime("%d/%m/%Y")
                        if hasattr(p.given, "strftime")
                        else str(p.given)
                    ),
                    "date_court": (
                        p.given.strftime("%d/%m")
                        if hasattr(p.given, "strftime")
                        else str(p.given)
                    ),
                    "circonstances": p.circumstances or "",
                    "exclusion": p.exclusion,
                    "pendant_cours": p.during_lesson,
                    "travail": p.homework or "",
                    "duree": int(p.duration.total_seconds() // 60) if p.duration else 0,
                    "schedule": schedule,
                }

            nbpunition = 0
            for punition in punitions:
                data["punition"].append(format_punition(punition))
                nbpunition += 1
            data["Nb_Punitions"] = nbpunition
            # Dernière punition (liste déjà triée par date desc)
            data["derniere_punition"] = (
                [data["punition"][0]] if data["punition"] else []
            )
        else:
            time.sleep(5)
        return data
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des Punitions: %s", e)
        time.sleep(5)
        return data


def ical(client):
    """
    Récupère l'URL du calendrier iCal de l'utilisateur.

    Args:
        client: L'objet client pronotepy connecté.

    Returns:
        str: L'URL du calendrier iCal, ou une chaîne vide si non trouvée ou en cas d'erreur.
    """
    try:
        # pronotepy expose l'URL iCal comme un attribut de l'objet client
        ical_url = getattr(client, "ical_url", None)
        if ical_url:
            logging.info("URL iCal récupérée avec succès.")
            return ical_url
        else:
            logging.warning("Aucune URL iCal n'a été trouvée pour ce compte.")
            return ""
    except Exception as e:
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "unknown"
        logging.error(
            "Une erreur est survenue lors de la récupération de l'URL iCal: ligne %s - %s",
            line_number,
            e,
        )
        return ""


def download_photo(client, eqLogicId, tokenconnected, message):
    """
    Télécharge la photo de profil de l'élève ou de l'enfant sélectionné.
    Pour les comptes parent (Pronote 2024+) : la photo est extraite en base64
    depuis la réponse de l'API Pronote (PageEmploiDuTemps), car FichiersExternes
    retourne systématiquement 404 avec les sessions mobiles/token.

    Args:
        client: Objet client PronotePy
        eqLogicId: ID de l'équipement Jeedom
        tokenconnected: Indicateur si connecté via token
        message: Dictionnaire du message reçu

    Returns:
        str or None: Chemin relatif de la photo, ou None si échec
    """
    try:
        is_parent = (tokenconnected == "true") and (
            "parent.html" in message["TokenUrl"]
        )

        data_dir = os.path.join(_data_dir, str(eqLogicId)) + "/"
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

            photo = client._selected_child.profile_picture
            if not photo:
                logging.debug("Aucune photo trouvée pour l'enfant")
                return None

            downloaded = False
            logging.info("Téléchargement photo parent — URL : %s", photo.url)

            # ── Stratégie 1 : méthode native pronotepy ────────────────────────
            try:
                photo.save(temp_path)
                logging.info("Photo téléchargée — stratégie 1 (FichiersExternes natif)")
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

        # ── Compte élève : méthode standard FichiersExternes ─────────────────
        photo = None
        if client.info.profile_picture:
            photo = client.info.profile_picture
            logging.debug("Photo trouvée pour l'élève")

        if not photo:
            logging.debug("Aucune photo trouvée dans Pronote")
            return None

        downloaded = False
        logging.info("Téléchargement photo — URL : %s", photo.url)

        # ── Stratégie 1 : méthode native pronotepy (photo.save) ──────────────
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


def Connectparent(pronote_url, login, password, ent, enfant):
    # Je valide que j'ai les bonnes informations pour me connecter en tant que Parent
    try:
        if login == "":
            logging.error("Pas de login reçu sur le daemon")
            return None, []
        if pronote_url == "":
            logging.error("Pas d'URL reçue sur le daemon")
            return None, []
        if password != "":
            password = my_decrypt(password)
        else:
            logging.error("Pas de password reçu sur le daemon")
            return None, []
        # Maintenant j'essaye de me connecter
        client = pronotepy.ParentClient(pronote_url, login, password, ent)
        logging.info("Je suis connecté en tant que parent")

        # je récupére la liste des enfants
        listenfant = []
        # je retourne la liste d'enfant du compte parent
        for child in client.children:
            logging.debug("Listes des enfants trouvé du compte Parent : %s", child.name)
            listenfant.append(child.name)
        # Si pas d'enfant  par défault je prend le premier enfant
        logging.debug("Je me connecte à l''enfant %s", enfant)
        if enfant == "":
            client.set_child(listenfant[0])
            logging.info("Je suis connecté à l'enfant par défault %s", listenfant[0])
        else:
            # Pour mettre à jour la liste d'enfant, je vérifie toujorus la liste
            client.set_child(enfant)
            logging.info("Je suis connecté à l'enfant %s", enfant)
        return client, listenfant
    except Exception as e:
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "unknown"
        logging.error("Connection parent échouée : ligne %s - %s", line_number, e)
        return None, []


def Connect(pronote_url, login, password, ent):
    if login == "":
        logging.error("Pas de login reçu sur le daemon")
        return None

    if pronote_url != "":
        if ent == "":
            if pronote_url.endswith(
                ".index-education.net/pronote/eleve.html?login=true"
            ):
                pronote_url = pronote_url[: -len("?login=true")]
                logging.info("URL modifiée :", pronote_url)
        elif pronote_url.endswith(".index-education.net/pronote/eleve.html"):
            pronote_url += "?login=true"
            logging.info("URL modifiée : %s", pronote_url)
        logging.debug("L'url pour se connecter est : %s", pronote_url)
    else:
        logging.error("Pas d'URL reçue sur le daemon")
        return None
    if password != "":
        password = my_decrypt(password)
    else:
        logging.error("Pas de password reçu sur le daemon")
        return None
    try:
        client = pronotepy.Client(pronote_url, login, password, ent)
        logging.info("Je suis connecté")
        return client
    except Exception as e:
        logging.error("Connection échouée : %s", e)
        return None


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
    timeout_seconds = 300  # Réinitialiser après 5 minutes

    current_time = time.time()

    with _failed_attempts_lock:
        # Initialiser si n'existe pas
        if eqLogicId not in failed_attempts:
            failed_attempts[eqLogicId] = {"count": 0, "timestamp": current_time}

        # Réinitialiser après timeout
        if current_time - failed_attempts[eqLogicId]["timestamp"] > timeout_seconds:
            failed_attempts[eqLogicId] = {"count": 0, "timestamp": current_time}

        # Incrémenter si demandé
        if increment:
            failed_attempts[eqLogicId]["count"] += 1
            if failed_attempts[eqLogicId]["count"] > max_attempts:
                error_msg = (
                    f"ProJote - Circuit breaker: {failed_attempts[eqLogicId]['count']} tentatives échouées. "
                    f"Le token Pronote est expiré. Supprimez le token et rescanez le code QR pour générer une nouvelle connexion."
                )
                logging.error(
                    f"Circuit breaker OUVERT pour eqLogicId {eqLogicId}: {error_msg}"
                )
                return False

        # Vérifier si circuit est ouvert
        if failed_attempts[eqLogicId]["count"] > max_attempts:
            error_msg = (
                f"ProJote - Circuit breaker bloqué pour eqLogicId {eqLogicId}. "
                f"Attendez 5 minutes ou supprimez le token manuellement."
            )
            logging.error(error_msg)
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
        file_path = os.path.join(data_dir, str(eqLogicId), "enfant.ProJote.json.txt")

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
        # ========================================================
        #   1 : On se connecte avec le Token réçu par défault
        # ========================================================
        # Vérifier que les informations de Token sont présentes et non vides
        required_keys = ["TokenId", "TokenUsername", "TokenPassword", "TokenUrl"]
        all_keys_present = True
        for key in required_keys:
            if key not in message or not message[key].strip():
                logging.error("Information de Token manquante ou vide : %s", key)
                all_keys_present = False
        if all_keys_present:
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
                logging.error(
                    "Token invalide, regénérer le QR CODE ou re valider le compte : %s",
                    e,
                )
                client = None
            ### 05/01/2025 : A revalider si je dois doubler
            # A supprimer car doublon avec ligne 1155
            # credentials = client.export_credentials()
            if client is not None and client.logged_in:
                tokenconnected = "true"
                # Réinitialiser le compteur d'échecs en cas de connexion réussie
                eqLogicId = message.get("CmdId", "")
                with _failed_attempts_lock:
                    if str(eqLogicId) in failed_attempts:
                        failed_attempts[str(eqLogicId)] = {
                            "count": 0,
                            "timestamp": time.time(),
                        }
            else:
                logging.error("Connection avec le Token échouée. Regénérez le QR code.")
                eqLogicId = message.get("CmdId", "")
                check_and_update_failed_attempts(eqLogicId, increment=True)
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
            if (tokenconnected == "true") and ("parent.html" in message["TokenUrl"]):
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
            # je renew le token
            logging.info("Je renew le Token")
            jsondata["Token"] = RenewToken(client)
            # Je valide que le fichier équipement est à jours
            # je lance la foncton qui recherche si le nom de l'enfant à changer dans l'équipement
            Checkeleve(client, message["CmdId"])
            # J'ajoute l'emploi du temps
            logging.info("Je récupére l'emploi du temps")
            edt_data = Emploidutemps(client)
            jsondata["Emploi_du_temps"] = edt_data
            if "error" in edt_data:
                jsondata["error"] = edt_data["error"]
            # J'ajoute les notes
            logging.info("Je récupére les notes")
            notes_data = notes(client)
            jsondata["Notes"] = notes_data
            if "error" in notes_data:
                jsondata["error"] = notes_data["error"]
            # j'ajoute les menus
            logging.info("Je récupére les menus")
            jsondata["Menus"] = menus(client)
            # j'ajoute la messagerie (discussions Pronote)
            logging.info("Je récupére la messagerie")
            jsondata["Messages"] = messages(client)
            # J'ajoute les Notifications
            logging.info("Je récupére les notifications")
            jsondata["Notifications"] = notifications(client)
            # j'ajoutes les absences
            logging.info("Je récupére les absences")
            jsondata["Absences"] = absences(client)
            # J'ajoutes les retards
            logging.info("Je récupére les retards")
            jsondata["Retards"] = retards(client)
            # J'ajoutes les punitions
            logging.info("Je récupére les punitions")
            jsondata["Punitions"] = punitions(client)
            # J'ajoute les devoirs
            logging.info("Je récupére les devoirs")
            jsondata["Devoirs"] = devoirs(client)
            # J'ajoutes des évaluations -- à finir
            logging.info("Je récupére les évaluations")
            jsondata["Competences"] = evaluations(client)
            # J'ajoutes l'ICAL
            logging.info("Je récupére l'ICAL")
            jsondata["Ical"] = ical(client)
            # Détection des nouveautés depuis la sync précédente (P3, v1.1.0)
            try:
                _seen = _load_seen_index(_data_dir, message["CmdId"])
                _dev = jsondata["Devoirs"] if isinstance(jsondata["Devoirs"], dict) else {}
                _abs = jsondata["Absences"] if isinstance(jsondata["Absences"], dict) else {}
                _pun = jsondata["Punitions"] if isinstance(jsondata["Punitions"], dict) else {}
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
    except Exception as e:
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
        logging.info(
            "=== Début traitement équipement %s (file restante : %d) ===",
            eq_id,
            _work_queue.qsize(),
        )
        try:
            process_message(message)
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
