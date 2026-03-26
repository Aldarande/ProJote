# This file is part of Jeedom
# Jeedom is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Jeedom is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Jeedom. If not, see <http://www.gnu.org/licenses/>.

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
        text = _re.sub(r'<br\s*/?>', ' ', html_text, flags=_re.IGNORECASE)
        text = _re.sub(r'<[^>]+>', '', text)
        text = _unescape(text)
        text = _re.sub(r'  +', ' ', text).strip()
        return text

    pronotepy.dataClasses.Util.html_parse = _patched_html_parse

    from LoginConnect import writedataPronotepy

    # Chiffrement du password
    from Crypto.Cipher import AES
    from random import Random

    # from Crypto import Random
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

# Threads actifs par équipement — garantit qu'un seul thread tourne par eqLogicId
_active_eq_lock = threading.Lock()
_active_eq = {}  # Format: {eqLogicId: threading.Thread}

# Variable globale pour stocker les info de connexion Jeedom
_callback_url = None
_apikey_global = None


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

        # Envoyer la requête GET (plus simple pour Jeedom)
        response = requests.get(message_action_url, params=params, timeout=5)

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


# Fonction de chiffrage et déchiffrage
# function de chiffrage non utilisé à supprimer
# https://gist.github.com/eoli3n/d6d862feb71102588867516f3b34fef1
def my_encrypt(data, passphrase):
    """
    # cSpell:disable
    Encrypt using AES-256-CBC with random/shared iv
    'passphrase' must be in hex, generate with 'openssl rand -hex 32'

    """
    try:
        key = binascii.unhexlify(passphrase)
        pad = lambda s: s + chr(16 - len(s) % 16) * (16 - len(s) % 16)
        iv = Random.get_random_bytes(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted_64 = base64.b64encode(cipher.encrypt(pad(data).encode())).decode(
            "ascii"
        )
        iv_64 = base64.b64encode(iv).decode("ascii")
        json_data = {"iv": iv_64, "data": encrypted_64}
        clean = base64.b64encode(json.dumps(json_data).encode("ascii"))
    except Exception as e:
        logging.error("Cannot encrypt datas...")
        logging.error(e)
        exit(1)
    return clean


def my_decrypt(data, passphrase):
    """
    Decrypt using AES-256-CBC with iv
    'passphrase' must be in hex, generate with 'openssl rand -hex 32'
    # https://stackoverflow.com/a/54166852/11061370
    """
    try:
        return _extracted_from_my_decrypt_(passphrase, data)
    except Exception as e:
        logging.error("Cannot decrypt datas...")
        logging.error(e)
        exit(1)


# TODO Rename this here and in `my_decrypt`
def _extracted_from_my_decrypt_(passphrase, data):
    unpad = lambda s: s[: -s[-1]]
    key = binascii.unhexlify(passphrase)
    encrypted = json.loads(base64.b64decode(data).decode("ascii"))
    encrypted_data = base64.b64decode(encrypted["data"])
    iv = base64.b64decode(encrypted["iv"])
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(encrypted_data)
    return unpad(decrypted).decode("ascii").rstrip()


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
        # Transformation Json des emplois du temps (J,J+1 et next)
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

            # Récupération  emploi du lendemain
        lessons_tomorrow = client.lessons(
            datetime.date.today() + datetime.timedelta(days=1)
        )
        lessons_tomorrow = sorted(lessons_tomorrow, key=lambda lesson: lesson.start)

        data["edt_demain"] = []
        data["edt_demain_debut"] = ""
        data["edt_demain_fin"] = ""
        data["edt_demain_Annul"] = ""
        if lessons_tomorrow:
            for lesson in lessons_tomorrow:
                index = lessons_tomorrow.index(lesson)
                if (
                    lesson.start != lessons_tomorrow[index - 1].start
                    or lesson.canceled != True
                ):
                    data["edt_demain"].append(build_cours_data(lesson))
                if lesson.canceled == False and data["edt_demain_debut"] == "":
                    data["edt_demain_debut"] = lesson.start.strftime("%H%M")
            data["edt_demain_fin"] = lesson.end.strftime("%H%M")

        # Récupération  emploi du prochain jour d'école (ça sert le weekend et les vacances)
        delta = 1
        lessons_nextday = client.lessons(
            datetime.date.today() + datetime.timedelta(days=delta)
        )
        while not lessons_nextday and delta < 120:
            lessons_nextday = client.lessons(
                datetime.date.today() + datetime.timedelta(days=delta)
            )
            delta += 1
        lessons_nextday = sorted(lessons_nextday, key=lambda lesson: lesson.start)
        # JE compléte l'emploi du temps du prochain jours
        data["edt_prochainjour"] = []
        data["edt_prochainjour_debut"] = ""
        data["edt_prochainjour_fin"] = ""
        data["edt_prochainjour_cancel"] = 0
        if lessons_nextday:
            for lesson in lessons_nextday:
                index = lessons_nextday.index(lesson)
                if (
                    lesson.start != lessons_nextday[index - 1].start
                    or lesson.canceled != True
                ):
                    lesson_to_append = build_cours_data(lesson)
                    lesson_to_append["index"] = index
                    data["edt_prochainjour"].append(lesson_to_append)

                if lesson.canceled == True:
                    data["edt_prochainjour_cancel"] += 1

                if lesson.canceled == False and data["edt_prochainjour_debut"] == "":
                    data["edt_prochainjour_debut"] = lesson.start.strftime("%H%M")
            data["edt_prochainjour_fin"] = lesson.end.strftime("%H%M")
            data["edt_prochainjour_date"] = lesson.start.strftime("%d/%m/%Y")

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


def menus(client):
    try:
        data = {"Menu": []}
        # Récupération des menus
        menu_today = client.menus(datetime.date.today())
        if not menu_today == []:
            # On trie les menus par date
            menu_today = sorted(menu_today, key=lambda m: m.date)
            # Transformation des menu en json
            for menu in menu_today:
                data["Menu"].append(build_menu_data(menu))
        else:
            logging.info("Aucun menu trouvé pour la date du jour.")
            time.sleep(5)
        return data["Menu"]
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des Menus: %s", e)


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
                for grade in (period_grades or []):
                    all_grades.append((grade, period_name))
            except Exception as e:
                logging.warning(f"Impossible de lire les notes de la période {getattr(period, 'name', '?')} : {e}")

            # Moyennes générales par période (élève + classe)
            try:
                moy_eleve = getattr(period, "overall_average", "") or ""
                moy_classe = getattr(period, "class_overall_average", "") or ""
                if moy_eleve or moy_classe:
                    data["moyennes_periodes"].append({
                        "periode": getattr(period, "name", ""),
                        "moyenne_eleve": str(moy_eleve),
                        "moyenne_classe": str(moy_classe),
                    })
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

                note_value   = getattr(grade, "grade", "")
                out_of_value = getattr(grade, "out_of", "")
                note_sur     = f"{note_value}\u00a0/\u00a0{out_of_value}" if note_value and out_of_value else ""
                grade_date   = getattr(grade, "date", None) or datetime.date.today()

                data["note"].append(
                    {
                        "id": getattr(grade, "id", ""),
                        "periode": period_name,
                        "date": grade_date.strftime("%d/%m/%Y"),
                        "date_courte": grade_date.strftime("%d/%m"),
                        "cours": cours_name,
                        "note": note_value,
                        "sur": out_of_value,
                        "note_sur": note_sur,
                        "coeff": getattr(grade, "coefficient", "1"),
                        "moyenne_classe": getattr(grade, "average", ""),
                        "max": getattr(grade, "max", ""),
                        "min": getattr(grade, "min", ""),
                        "commentaire": getattr(grade, "comment", ""),
                        "optionnel": getattr(grade, "is_optionnal", False),
                        "bonus": getattr(grade, "is_bonus", False),
                    }
                )

            if data["note"]:
                data["derniere_note"].append(data["note"][0])
        else:
            logging.info("Aucune note trouvée pour l'année scolaire.")

        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "unknown"
        error_msg = f"Erreur lors de la récupération des notes : ligne {line_number} - {str(e)}"
        logging.error(error_msg)
        logging.debug(traceback.format_exc())
        return {"note": [], "derniere_note": [], "error": error_msg}



def process_homework(homework_list, data, key):
    if not homework_list:
        logging.info(f"Aucun devoir trouvé pour {key}.")
        data[f"nb_{key}"] = 0
        data[f"nb_{key}_F"] = 0
        data[f"nb_{key}_NF"] = 0
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
                fichiers.append({
                    "nom": f.name,
                    "url": f.url,
                    "type": f.type,  # 0 = lien externe, 1 = fichier Pronote
                })
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
                for d in (period.delays or []):
                    all_retards_map[d.id] = d
            except Exception as e:
                logging.warning(f"Impossible de lire les retards de la période {getattr(period, 'name', '?')} : {e}")

        all_retards = list(all_retards_map.values())
        if all_retards:
            all_retards = sorted(all_retards, key=lambda delay: delay.date, reverse=True)
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
            return {"absence": [], "nb_absences": 0, "derniere_absence": [], "error": str(e)}

        all_absences_map = {}
        for period in all_periods:
            try:
                for a in (period.absences or []):
                    all_absences_map[a.id] = a
            except Exception as e:
                logging.warning(f"Impossible de lire les absences de la période {getattr(period, 'name', '?')} : {e}")

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
            return {"punition": [], "derniere_punition": [], "Nb_Punitions": 0, "error": str(e)}

        all_punitions_map = {}
        for period in all_periods:
            try:
                for p in (period.punishments or []):
                    all_punitions_map[p.id] = p
            except Exception as e:
                logging.warning(f"Impossible de lire les punitions de la période {getattr(period, 'name', '?')} : {e}")

        import datetime as _dt
        def _punition_sort_key(p):
            g = p.given
            if isinstance(g, _dt.datetime):
                return g.date()
            return g if isinstance(g, _dt.date) else _dt.date.min

        punitions = sorted(all_punitions_map.values(), key=_punition_sort_key, reverse=True) if all_punitions_map else []
        if punitions:

            def format_punition(p):
                # Créneaux planifiés (ex : retenues programmées)
                schedule = []
                for s in (p.schedule or []):
                    try:
                        start_str = s.start.strftime("%d/%m %H:%M") if hasattr(s.start, "strftime") else str(s.start)
                        duree_min = int(s.duration.total_seconds() // 60) if s.duration else None
                        schedule.append({"start": start_str, "duree": duree_min})
                    except Exception:
                        pass
                return {
                    "id": p.id,
                    "type": p.nature,
                    "raison": ", ".join(p.reasons) if p.reasons else "",
                    "donneur": p.giver,
                    "date": p.given.strftime("%d/%m/%Y") if hasattr(p.given, "strftime") else str(p.given),
                    "date_court": p.given.strftime("%d/%m") if hasattr(p.given, "strftime") else str(p.given),
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
            data["derniere_punition"] = [data["punition"][0]] if data["punition"] else []
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
    Note: pour les comptes parent avec Pronote 2024+ (N au format '46#...'), le téléchargement
    de la photo n'est pas supporté — FichiersExternes requiert une session web (cookies)
    que les sessions mobile API ne possèdent pas.

    Args:
        client: Objet client PronotePy
        eqLogicId: ID de l'équipement Jeedom
        tokenconnected: Indicateur si connecté via token
        message: Dictionnaire du message reçu

    Returns:
        str or None: Chemin relatif de la photo, ou None si échec
    """
    try:
        is_parent = (tokenconnected == "true") and ("parent.html" in message["TokenUrl"])
        photo = None

        if is_parent:
            if client._selected_child and client._selected_child.profile_picture:
                child_n = client._selected_child.raw_resource.get("N", "")
                if "#" in str(child_n):
                    logging.debug("Photo non disponible : compte parent avec Pronote 2024+ (N=%s...). FichiersExternes requiert une session web.", str(child_n)[:10])
                    return None
                photo = client._selected_child.profile_picture
                logging.debug("Photo trouvée pour l'enfant : %s", client._selected_child.name)
        else:
            if client.info.profile_picture:
                photo = client.info.profile_picture
                logging.debug("Photo trouvée pour l'élève")

        if not photo:
            logging.debug("Aucune photo trouvée dans Pronote")
            return None

        data_dir = os.path.join(_data_dir, str(eqLogicId)) + "/"
        verifdossier(data_dir)
        final_path = f"{data_dir}profile_picture.jpg"
        temp_path = f"{data_dir}profile_picture_temp.jpg"

        downloaded = False

        logging.debug("URL de la photo : %s", photo.url)
        try:
            photo.save(temp_path)
            logging.info("Photo téléchargée avec succès via FichiersExternes")
            downloaded = True
        except FileNotFoundError:
            # FichiersExternes retourne 404 — tenter avec headers supplémentaires
            logging.debug("FichiersExternes 404, tentative avec Referer/Origin")
            try:
                headers = {
                    "Referer": client.communication.root_site + "/",
                    "Origin": client.communication.root_site,
                }
                resp = client.communication.session.get(photo.url, headers=headers)
                if resp.status_code == 200 and len(resp.content) > 100:
                    with open(temp_path, "wb") as f:
                        f.write(resp.content)
                    logging.info("Photo téléchargée avec Referer/Origin")
                    downloaded = True
                else:
                    logging.error("Échec du téléchargement de la photo : %s (status %d)", photo.url, resp.status_code)
            except Exception as e:
                logging.error("Échec du téléchargement de la photo : %s", e)
        except Exception as e:
            logging.error("Échec du téléchargement de la photo : %s", e)

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
        estab = (clientinfo.establishment or '').strip()
        words = estab.split()
        mid = len(words) // 2
        if mid > 0 and words[:mid] == words[mid:]:
            estab = ' '.join(words[:mid])

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
            password = my_decrypt(
                password,
                "084781141BD01304180B9B58120E4E058C1434394DDED646BF4ECC95380B9442",
            )
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
        password = my_decrypt(
            password, "084781141BD01304180B9B58120E4E058C1434394DDED646BF4ECC95380B9442"
        )
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
                                    logging.warning("Impossible de sélectionner l'enfant (backup) : %s", e2)
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
                                renew_uuid = backup_uuid + "2" if backup_uuid.endswith("-bk") else backup_uuid + "-bk"
                                if "parent.html" in backup_token["pronote_url"]:
                                    new_backup_client = pronotepy.ParentClient.token_login(
                                        pronote_url=backup_token["pronote_url"],
                                        username=backup_token["username"],
                                        password=backup_token["password"],
                                        client_identifier=backup_token["client_identifier"],
                                        uuid=renew_uuid,
                                    )
                                else:
                                    new_backup_client = pronotepy.Client.token_login(
                                        pronote_url=backup_token["pronote_url"],
                                        username=backup_token["username"],
                                        password=backup_token["password"],
                                        client_identifier=backup_token["client_identifier"],
                                        uuid=renew_uuid,
                                    )
                                if new_backup_client and new_backup_client.logged_in:
                                    new_backup_credentials = new_backup_client.export_credentials()
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
                                    eqLogicId, e_bk,
                                )
                            # Sauvegarder le nouveau token principal + backup (si disponible)
                            try:
                                writedataPronotepy(client, _data_dir, eqLogicId, backup_token=new_backup_credentials)
                                logging.warning(
                                    "ProJote — Tokens renouvelés pour l'équipement %s. Token backup : %s.",
                                    eqLogicId,
                                    "régénéré avec succès" if new_backup_credentials else "non régénéré — reconnexion QR recommandée",
                                )
                            except Exception as e_save:
                                logging.warning(
                                    "ProJote — Sauvegarde des tokens renouvelés échouée pour l'équipement %s : %s",
                                    eqLogicId, e_save,
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
    Exécuté dans un thread dédié par équipement (eqLogicId).
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
                    nb_attempts = failed_attempts.get(str(eqLogicId), {"count": 0})["count"]
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
            logging.error("Aucun token disponible. Configurez la connexion via QR code.")
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
            if (tokenconnected == "true") and (
                "parent.html" in message["TokenUrl"]
            ):
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
        # Libérer le slot pour cet équipement une fois le traitement terminé
        with _active_eq_lock:
            _active_eq.pop(eq_id, None)


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

        logging.debug("Le MESSAGE reçu est : %s", message)

        eq_id = str(message.get("CmdId", ""))

        # Un seul thread actif par équipement — évite les traitements simultanés
        with _active_eq_lock:
            existing = _active_eq.get(eq_id)
            if existing and existing.is_alive():
                logging.warning(
                    "Équipement %s déjà en cours de traitement — requête ignorée.", eq_id
                )
                return
            t = threading.Thread(
                target=process_message,
                args=(message,),
                daemon=True,
                name=f"eq-{eq_id}",
            )
            _active_eq[eq_id] = t
            t.start()
            logging.debug("Thread démarré pour l'équipement %s", eq_id)

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
    jeedom_socket = jeedom_socket(port=_socket_port, address=_socket_host)
    listen()
except Exception as e:
    logging.error("Fatal error: %s", e)
    logging.info(traceback.format_exc())
    shutdown()
