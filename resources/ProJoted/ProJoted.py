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

    # import du Plugin Principal
    import pronotepy
    from pronotepy.ent import *

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
    sys.exit(1)


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
            chemin_fichier = "/var/www/html/plugins/ProJote/data"
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
        # load the module, will raise ImportError if module cannot be loaded
        m = importlib.import_module(module_name)
        return getattr(m, class_name)
    except e:
        # ModuleNotFoundError will be a subclass of OSError
        logging.error("Error importing module %s: %s", module_name, e)
        return None


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
    return lesson_data.subject.name if lesson_data.subject else "autre"


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


def download_image(url, filepath):
    try:
        # Effectuer une requête HTTP pour récupérer le contenu de l'image
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

        # Récupération  emploi d'un jour spécifique pour des tests
        lessons_specific = client.lessons(datetime.date(2024, 4, 23))
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
        lessons_full = client.lessons(
            client.current_period.start, datetime.date.today()
        )
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
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Une erreur est retournée sur le traitement de l'emploi du temps-lig: %s; %s",
            line_number,
            e,
        )


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
        evaluations = client.current_period.evaluations
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

            data["evaluations"].append(
                {
                    "id": evaluation.id,
                    "nom": evaluation.name,
                    "domaine": evaluation.domain,
                    "professeur": evaluation.teacher,
                    "Sujet": getattr(
                        evaluation.subject, "name", str(evaluation.subject)
                    ),
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
    try:
        data = {"note": [], "derniere_note": []}
        grades = client.current_period.grades
        if not grades == []:
            grades = sorted(grades, key=lambda grade: grade.date, reverse=True)
            index_note = 0  # debut de la boucle des notes
            limit_note = 11  # nombre max de note à récupérer + 1
            # Transformation des notes en Json
            for grade in grades:
                index_note += 1
                # Attention je ne prend que 11 notes pour éviter de surcharger le système et bloquer l'adresse IP
                if index_note == limit_note:
                    break
                data["note"].append(
                    {
                        "id": grade.id,
                        "date": grade.date.strftime("%d/%m/%Y"),
                        "date_courte": grade.date.strftime("%d/%m"),
                        "cours": grade.subject.name,
                        "note": grade.grade,
                        "sur": grade.out_of,
                        "note_sur": grade.grade + "\u00a0/\u00a0" + grade.out_of,
                        "coeff": grade.coefficient,
                        "moyenne_classe": grade.average,
                        "max": grade.max,
                        "min": grade.min,
                        "commentaire": grade.comment,
                        "optionnel": grade.is_optionnal,
                        "bonus": grade.is_bonus,
                    }
                )
                # je récupére la derniére note
            if index_note > 0:
                data["derniere_note"].append(data["note"][0])
        else:
            logging.info("Aucune note trouvée pour la période en cours.")
            data = {"note": [], "derniere_note": []}
        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Une erreur est retournée sur le traitement des notes -lig: %s; %s",
            line_number,
            e,
        )
        time.sleep(5)
        return {"note": [], "derniere_note": []}


def process_homework(homework_list, data, key, longmax_devoir):
    if not homework_list:
        logging.info(f"Aucun devoir trouvé pour {key}.")
        return

    for homework in homework_list:
        data[key].append(
            {
                "index": homework_list.index(homework),
                "date": homework.date.strftime("%d/%m"),
                "title": homework.subject.name,
                "description": (
                    homework.description.encode("utf-8").decode("unicode_escape")
                )[:longmax_devoir],
                "color": homework.background_color,
                "done": homework.done,
                "est_service_groupe": getattr(homework, "estServiceGroupe", None),
            }
        )


import datetime
import logging


def process_homework(homework_list, data, key, longmax_devoir):
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
        data[key].append(
            {
                "index": homework_list.index(homework),
                "date": homework.date.strftime("%d/%m"),
                "title": homework.subject.name,
                "description": (
                    homework.description.encode("utf-8").decode("unicode_escape")
                )[:longmax_devoir],
                "color": homework.background_color,
                "done": homework.done,
                "est_service_groupe": getattr(homework, "estServiceGroupe", None),
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
        longmax_devoir = 120
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
        process_homework(homework_today, data, "devoir", longmax_devoir)
        # Traiter les devoirs pour le prochain jour d'école
        if next_school_day:
            process_homework(next_school_day, data, "devoir_Demain", longmax_devoir)
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
        # recupération des retards
        retards = client.current_period.delays
        if not retards == []:
            # tri des retards par date décroissante
            retards = sorted(retards, key=lambda delay: delay.date, reverse=True)

            nbretard = 0
            # Récupération des retards pour la période en cours
            for retard in retards:
                data["retard"].append(
                    {
                        "id": retard.id,
                        "date": retard.date.strftime("%d/%m/%y %H:%M"),
                        "justifie": retard.justified,
                        "nb_minutes": retard.minutes,
                        "justification": retard.justification,
                        "raison": str(retard.reasons)[2:-2],
                    }
                )
                nbretard = nbretard + 1
            data["nb_retard"] = nbretard
            # récupération du denrier retard
            data["dernier_retard"] = [data["retard"][0]] if data["retard"] else []
            # transformation des retards en Json
        else:
            time.sleep(5)
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
        # Récupération  des absences pour la période en cours
        data = {"absence": [], "nb_absences": 0, "derniere_absence": []}
        absences = client.current_period.absences
        if not absences == []:
            absences = sorted(
                absences, key=lambda absence: absence.from_date, reverse=True
            )
            nbabsences = 0
            for absence in absences:
                data["absence"].append(
                    {
                        "id": absence.id,
                        "date_debut": absence.from_date.strftime("%d/%m/%y %H:%M"),
                        "date_fin": absence.to_date.strftime("%d/%m/%y %H:%M"),
                        "justifie": absence.justified,
                        "nb_heures": absence.hours,
                        "nb_jours": absence.days,
                        "raison": str(absence.reasons)[2:-2],
                    }
                )
                nbabsences += 1
            data["nb_absences"] = nbabsences
            # Je récupére la derniére absence
            if nbabsences > 0:
                data["derniere_absence"].append(
                    {
                        "id": absences[0].id,
                        "date_debut": absences[0].from_date.strftime("%d/%m/%y %H:%M"),
                        "date_fin": absences[0].to_date.strftime("%d/%m/%y %H:%M"),
                        "justifie": absences[0].justified,
                        "nb_heures": absences[0].hours,
                        "nb_jours": absences[0].days,
                        "raison": str(absences[0].reasons)[2:-2],
                    }
                )
            else:
                time.sleep(5)
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
        # Récupération des punitions
        data = {"punition": [], "derniere_punition": [], "Nb_Punitions": 0}
        punitions = client.current_period.punishments
        if not punitions == []:
            data["derniere_punition"].append(
                {
                    "id": punitions[0].id,
                    "type": punitions[0].nature,
                    "raison": punitions[0].reasons,
                    "donneur": punitions[0].giver,
                    "date": punitions[0].given.strftime("%d/%m/%Y"),
                    "date_court": punitions[0].given.strftime("%d/%m"),
                    "circonstances": punitions[0].circumstances,
                    "exclusion": punitions[0].exclusion,
                    "duree": int(punitions[0].duration.total_seconds() // 60),
                }
            )
            nbpunition = 0
            for punition in punitions:
                data["punition"].append(
                    {
                        "id": punition.id,
                        "type": punition.nature,
                        "raison": punition.reasons,
                        "donneur": punition.giver,
                        "date": punition.given.strftime("%d/%m/%Y"),
                        "date_court": punition.given.strftime("%d/%m"),
                        "circonstances": punition.circumstances,
                        "exclusion": punition.exclusion,
                        "duree": int(punition.duration.total_seconds() // 60),
                    }
                )
                nbpunition = nbpunition + 1
            data["Nb_Punitions"] = nbpunition
        else:
            time.sleep(5)
        return data
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des Punissions: %s", e)
        time.sleep(5)
        return data


def ical(client):
    # Récupération des coordonnées ICAL
    try:
        jsondata = {"ICAL": client.export_ical()}
    except Exception as e:
        jsondata = {"ICAL": ""}
        logging.info("Un erreur est retourné sur le traitement de l'ICAL: %s", e)
    return jsondata["ICAL"]


def identites(clientinfo):
    # Le but est de collecter toutes les informations concernant l'identité de l'élève
    try:
        data = {"identiteinfo": []}
        # Création du dictionnaire d'informations d'identité avec des valeurs non vides
        IdentityInfo = {
            "Nom_Eleve": clientinfo.name,
            "Nom_Classe": clientinfo.class_name,
            "Etablissement": clientinfo.establishment,
            # "Email": clientinfo.email,
        }
        logging.debug("Nom de l''identité nom  %s", clientinfo.name)
        logging.debug("Nom de l''identité Classe %s", clientinfo.class_name)
        logging.debug("Nom de l''identité Etablissement %s", clientinfo.establishment)
        return IdentityInfo
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.info(
            "Tous les champs identité n'ont pas pu être récupéré: lig. %s -   %s",
            line_number,
            e,
        )


def GetTokenFromLogin(Account):
    qrcode_data = Account.request_qr_code_data("4321")
    logging.debug("Les info du QRCode : %s", qrcode_data["url"])
    return Account.qrcode_login(
        qrcode_data,
        "4321",
        uuid="ProJote",
    )


def RenewToken(client):
    try:
        # Récupération des tokens
        data = {"Token": client.export_credentials()}
        logging.debug("Les tokens sont : %s", data["Token"])
        return data["Token"]
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des tokens: %s", e)


def Connectparent(pronote_url, login, password, ent, enfant):
    # Je valide que j'ai les bonnes informations pour me connecter en tant que Parent
    try:
        if login == "":
            logging.error("Pas de login reçu sur le deamon")
            if pronote_url == "":
                logging.error("pas d'URL reçu sur le deamon")
            elif ent == "":
                if pronote_url.endswith(
                    ".index-education.net/pronote/parent.html?login=true"
                ):
                    pronote_url = pronote_url[: -len("?login=true")]
                    logging.info("URL  modifiée : %s", pronote_url)
            elif pronote_url.endswith(".index-education.net/pronote/parent.html"):
                pronote_url += "?login=true"
                logging.info("URL  modifiée : %s", pronote_url)
        logging.debug("password chiffré : %s", password)
        """ if password != "":
            if isinstance(password, str):
                password = my_decrypt(
                    password,
                    "084781141BD01304180B9B58120E4E058C1434394DDED646BF4ECC95380B9442",
                )
                logging.debug("password déchiffré : %s", password)
            else:
                logging.error("Le password n'est pas un string")
        else:
            logging.error("pas de password reçu sur le deamon") """
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
        line_number = e.__traceback__.tb_lineno
        logging.error("Connection parent échouée : lig. %s -   %s", line_number, e)


def Connect(pronote_url, login, password, ent):
    if login == "":
        logging.error("Pas de login reçu sur le deamon")

    if pronote_url != "":
        if ent == "":
            if pronote_url.endswith(
                ".index-education.net/pronote/eleve.html?login=true"
            ):
                pronote_url = pronote_url[: -len("?login=true")]
                logging.info("URL  modifiée :", pronote_url)
        elif pronote_url.endswith(".index-education.net/pronote/eleve.html"):
            pronote_url += "?login=true"
            logging.info("URL  modifiée : %s", pronote_url)
        logging.debug("L'url pour se connecter est  : %s", pronote_url)
    else:
        logging.error("pas d'URL reçu sur le deamon")
    if password != "":

        password = my_decrypt(
            password, "084781141BD01304180B9B58120E4E058C1434394DDED646BF4ECC95380B9442"
        )

    else:
        logging.error("pas de password reçu sur le deamon")
    try:
        client = pronotepy.Client(pronote_url, login, password, ent)
        logging.info("Je suis connecté")
        return client
    except Exception as e:
        logging.error("Connection échouée :  %s", e)


def read_socket():  # sourcery skip: extract-method, merge-dict-assign
    global JEEDOM_SOCKET_MESSAGE
    try:
        if not JEEDOM_SOCKET_MESSAGE.empty():
            logging.debug("Notification received in socket JEEDOM_SOCKET_MESSAGE")

            raw_message = JEEDOM_SOCKET_MESSAGE.get()
            decoded_message = raw_message.decode("utf-8")
            logging.debug("Decoded message: %s", decoded_message)
            if (
                not decoded_message.strip()
            ):  # Vérifier si la chaîne est vide après suppression des espaces
                logging.error("Notification vide ou invalide reçu depuis le socket.")
                return
            try:
                message = json.loads(decoded_message)
            except json.JSONDecodeError as e:
                logging.error("Erreur de décodage JSON : %s", e)
                logging.debug("Notification en erreur : %s", raw_message)
                return

            logging.debug("Le MESSAGE reçu est : %s", message)
            if message["apikey"] != _apikey:
                logging.error("Invalid apikey from socket: %s", message)
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
                try:
                    if "parent.html" in message["TokenUrl"]:
                        client = pronotepy.ParentClient.token_login(
                            pronote_url=message["TokenUrl"],
                            username=message["TokenUsername"],
                            password=message["TokenPassword"],
                            client_identifier=message["TokenId"],
                            uuid="ProJote",
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
                            uuid="ProJote",
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
                else:
                    logging.error("Connection avec le Token échouée ")
                    required_keys = ["url", "login", "password"]
                    all_Comptekeys_present = True
                    for key in required_keys:
                        if key not in message or not message[key].strip():
                            logging.error(
                                "Information de login manquante ou vide : %s", key
                            )
                            all_Comptekeys_present = False
                    # sourcery skip: raise-specific-error
                    Exception(
                        "Connection avec le Token échouée et les inforamtions de login sont manquantes."
                    )
            else:
                logging.info("Je me connecte via la compte et le mot de passe.")
                required_keys = ["url", "login", "password"]
                if (all_Comptekeys_present != True) or not all_Comptekeys_present:
                    all_Comptekeys_present = True
                    for key in required_keys:
                        if key not in message or not message[key].strip():
                            logging.error(
                                "Information de login manquante ou vide : %s", key
                            )
                            all_Comptekeys_present = False

                if message["cas"] != "":
                    logging.debug("Cas/Ent reçu : %s", message["cas"])
                    ent = class_for_name("pronotepy.ent", message["cas"])
                else:
                    ent = ""
                if (message["CptParent"] == "1") or (
                    "parent.html" in message["TokenUrl"]
                ):
                    logging.info("Je me connecte en tant que parent")
                    ## connection en tant que parent
                    client, listenfant = Connectparent(
                        pronote_url=message["url"],
                        login=message["login"],
                        password=message["password"],
                        ent=ent,
                        enfant=message["enfant"],
                    )
                    message["CptParent"] == "1"
                else:
                    logging.info("Je me connecte en tant qu'élève")
                    client = Connect(
                        pronote_url=message["url"],
                        login=message["login"],
                        password=message["password"],
                        ent=ent,
                    )
                # Maintenant que je suis connecté je vais chercher les informations de Token pour la prochaine fois
                client = GetTokenFromLogin(client)
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
                logging.debug(
                    "Validation Token %s",
                    tokenconnected,
                )
                if (tokenconnected == "true") and (
                    "parent.html" in message["TokenUrl"]
                ):
                    logging.debug("Le nom de l'élève %s", client._selected_child.name)
                    jsondata["Eleve"] = identites(client._selected_child)
                    if (
                        client._selected_child.profile_picture
                        and client._selected_child.profile_picture.url
                    ):
                        jsondata["Photo"] = client._selected_child.profile_picture.url
                else:
                    jsondata["Eleve"] = identites(client.info)
                    if client.info.profile_picture and client.info.profile_picture.url:
                        jsondata["Photo"] = client.info.profile_picture.url
                # je renew le token
                logging.info("Je renew le Token")
                jsondata["Token"] = RenewToken(client)
                # Je valide que le fichier équipement est à jours
                # je lance la foncton qui recherche si le nom de l'enfant à changer dans l'équipement
                Checkeleve(client, message["CmdId"])
                # J'ajoute l'emploi du temps
                logging.info("Je récupére l'emploi du temps")
                jsondata["Emploi_du_temps"] = Emploidutemps(client)
                # J'ajoute les notes
                logging.info("Je récupére les notes")
                jsondata["Notes"] = notes(client)
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
                return False
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error("Erreur d'éxécution du deamon : lig. %s -  %s", line_number, e)
        jeedom_com.send_change_immediate(jsondata)


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
args = parser.parse_args()

_log_level = args.loglevel or "error"
_callback = args.callback or ""
_apikey = args.apikey or ""
_pidfile = args.pid or "/tmp/ProJoted.pid"
_cycle = float(args.cycle) if args.cycle else 0.3
_socket_port = args.socketport or 55369
_socket_port = int(_socket_port)
_cycle = int(_cycle)

jeedom_utils.set_log_level(_log_level)

logging.info("Start demond")
logging.info("Log level: %s", _log_level)
logging.info("Socket port: %s", _socket_port)
logging.info("Socket host: %s", _socket_host)
logging.info("PID file: %s", _pidfile)
logging.info("Apikey: %s", _apikey)


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
    logging.info(f"j'écris {str(_pidfile)}")
    jeedom_socket = jeedom_socket(port=_socket_port, address=_socket_host)
    listen()
except Exception as e:
    logging.error("Fatal error: %s", e)
    logging.info(traceback.format_exc())
    shutdown()
