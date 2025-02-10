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


# Fonction de chiffrage et déchiffrage
# function de chiffrage non utilisé à supprimer
# https://gist.github.com/eoli3n/d6d862feb71102588867516f3b34fef1
def my_encrypt(data, passphrase):
    """
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
        json_data = {}
        json_data["iv"] = iv_64
        json_data["data"] = encrypted_64
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
        unpad = lambda s: s[: -s[-1]]
        key = binascii.unhexlify(passphrase)
        encrypted = json.loads(base64.b64decode(data).decode("ascii"))
        encrypted_data = base64.b64decode(encrypted["data"])
        iv = base64.b64decode(encrypted["iv"])
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted_data)
        clean = unpad(decrypted).decode("ascii").rstrip()
        return clean

    except Exception as e:
        logging.error("Cannot decrypt datas...")
        logging.error(e)
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
        # Vérifier si le dossier existe
        if not os.path.exists(chemin_dossier):
            # Créer le dossier s'il n'existe pas
            os.makedirs(chemin_dossier)
            logging.info(f"Dossier créé avec succès : {chemin_dossier}")
        else:
            logging.info(f"Le dossier existe déjà : {chemin_dossier}")
        return True
    except Exception as e:
        logging.error(f"Erreur lors de la création du dossier : {e}")
        return False


def class_for_name(module_name, class_name):
    try:
        # load the module, will raise ImportError if module cannot be loaded
        m = importlib.import_module(module_name)
        # get the class, will raise AttributeError if class cannot be found
        c = getattr(m, class_name)
        return c
    except:
        return None


def cours_affiche_from_lesson(lesson_data):
    if lesson_data.detention == True:
        return "RETENUE"
    if lesson_data.subject:
        return lesson_data.subject.name
    else:
        return "autre"


def build_cours_data(lesson_data):
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
        data = {}
        # Transformation Json des emplois du temps (J,J+1 et next)
        # Récupération  emploi du temps du jour
        lessons_today = client.lessons(datetime.date.today())
        lessons_today = sorted(lessons_today, key=lambda lesson: lesson.start)
        data["edt_aujourdhui"] = []
        data["edt_aujourdhui_debut"] = ""
        data["edt_aujourdhui_fin"] = ""
        if lessons_today:
            for lesson in lessons_today:
                index = lessons_today.index(lesson)
                if not (
                    lesson.start == lessons_today[index - 1].start
                    and lesson.canceled == True
                ):
                    data["edt_aujourdhui"].append(build_cours_data(lesson))
                if lesson.canceled == False and data["edt_aujourdhui_debut"] == "":
                    data["edt_aujourdhui_debut"] = lesson.start.strftime("%H%M")
            data["edt_aujourdhui_fin"] = lesson.end.strftime("%H%M")

            # Récupération  emploi du lendemain
        lessons_tomorrow = client.lessons(
            datetime.date.today() + datetime.timedelta(days=1)
        )
        lessons_tomorrow = sorted(lessons_tomorrow, key=lambda lesson: lesson.start)

        data["edt_demain"] = []
        data["edt_demain_debut"] = ""
        data["edt_demain_fin"] = ""
        if lessons_tomorrow:
            for lesson in lessons_tomorrow:
                index = lessons_tomorrow.index(lesson)
                if not (
                    lesson.start == lessons_tomorrow[index - 1].start
                    and lesson.canceled == True
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
        while not lessons_nextday:
            lessons_nextday = client.lessons(
                datetime.date.today() + datetime.timedelta(days=delta)
            )
            delta = delta + 1
        lessons_nextday = sorted(lessons_nextday, key=lambda lesson: lesson.start)
        # JE compléte l'emploi du temps du prochain jours
        data["edt_prochainjour"] = []
        data["edt_prochainjour_debut"] = ""
        data["edt_prochainjour_fin"] = ""
        if lessons_nextday:
            for lesson in lessons_nextday:
                index = lessons_nextday.index(lesson)
                if not (
                    lesson.start == lessons_nextday[index - 1].start
                    and lesson.canceled == True
                ):
                    lesson_to_append = build_cours_data(lesson)
                    lesson_to_append["index"] = index
                    data["edt_prochainjour"].append(lesson_to_append)

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

        # Récupération  emploi d'un jour spécifique pour des tests
        lessons_full = client.lessons(
            client.current_period.start, datetime.date.today()
        )
        lessons_full = sorted(lessons_full, key=lambda lesson: lesson.start)

        data["edt_period_full"] = []
        data["edt_absent_full"] = []
        data["edt_Cours_canceled"] = 0
        if lessons_full:
            for lesson in lessons_full:
                lesson_to_append = build_cours_data(lesson)
                lesson_to_append["index"] = index
                lesson_to_append["num"] = lesson.num
                data["edt_period_full"].append(lesson_to_append)
                if lesson.canceled == True:
                    data["edt_absent_full"].append(lesson_to_append)
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
        # Récupération des menus
        menu_today = client.menus(datetime.date.today())
        data = {"Menu": []}
        # Transformation des menu en json
        for menu in menu_today:
            data["Menu"].append(
                {
                    "Nom": (menu.name),
                    "Entree": (menu.first_meal),
                    "Plat": (menu.main_meal),
                    "Accompagnement": (menu.side_meal),
                    "Autre Plat": (menu.other_meal),
                    "Fromage": (menu.cheese),
                    "Dessert": (menu.dessert),
                }
            )
            return data["Menu"]
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des Menus: %s", e)


def notes(client):
    try:
        # Récupération des notes
        grades = client.current_period.grades
        grades = sorted(grades, key=lambda grade: grade.date, reverse=True)

        index_note = 0  # debut de la boucle des notes
        limit_note = 11  # nombre max de note à afficher + 1

        # Transformation des notes en Json
        data = {"note": []}
        for grade in grades:
            index_note += 1
            if index_note == limit_note:
                break
            data["note"].append(
                {
                    "date": grade.date.strftime("%d/%m/%Y"),
                    "date_courte": grade.date.strftime("%d/%m"),
                    "cours": grade.subject.name,
                    "note": grade.grade,
                    "sur": grade.out_of,
                    "note_sur": grade.grade + "\u00A0/\u00A0" + grade.out_of,
                    "coeff": grade.coefficient,
                    "moyenne_classe": grade.average,
                    "max": grade.max,
                    "min": grade.min,
                }
            )
        return data["note"]
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des notes: %s", e)


def devoirs(client):
    try:
        data = {"devoir": [], "devoir_Demain": []}
        Devoir = 0
        Devoirfait = 0
        Devoirnonfait = 0
        # Récupération des devoirs
        homework_today = client.homework(datetime.date.today())
        longmax_devoir = 125  # nombre de caractère max dans la description des devoirs

        # Transformation des devoirs  en Json

        for homework in homework_today:

            data["devoir"].append(
                {
                    "index": homework_today.index(homework),
                    "date": homework.date.strftime("%d/%m"),
                    "title": homework.subject.name,
                    "description": (
                        homework.description.encode("utf-8").decode("unicode_escape")
                    )[0:longmax_devoir],
                    "description_longue": (
                        homework.description.encode("utf-8").decode("unicode_escape")
                    ),
                    "done": homework.done,
                    "est_service_groupe": getattr(homework, "estServiceGroupe", None),
                }
            )
            Devoir = Devoir + 1
            if homework.done == 1:
                Devoirfait = Devoirfait + 1
            else:
                Devoirnonfait = Devoirnonfait + 1
            data["nb_devoir"] = Devoir
            data["nb_devoirF"] = Devoirfait
            data["nb_devoirNF"] = Devoirnonfait

        # Récupération  des devoirs  du prochain jour d'école (ça sert le weekend et les vacances)
        Devoir = 0
        Devoirfait = 0
        Devoirnonfait = 0
        delta = 1
        homework_nextday = client.homework(
            datetime.date.today() + datetime.timedelta(days=delta)
        )

        while not homework_nextday:
            homework_nextday = client.homework(
                datetime.date.today() + datetime.timedelta(days=delta)
            )
            delta = delta + 1

        homework_nextday = sorted(homework_nextday, key=lambda homework: homework.date)
        nextdate = homework_nextday[0].date
        for homework in homework_nextday:

            if homework.date == nextdate:
                data["devoir_Demain"].append(
                    {
                        "index": homework_nextday.index(homework),
                        "date": homework.date.strftime("%d/%m"),
                        "title": homework.subject.name,
                        "description": (
                            homework.description.encode("utf-8").decode(
                                "unicode_escape"
                            )
                        )[0:longmax_devoir],
                        "description_longue": (
                            homework.description.encode("utf-8").decode(
                                "unicode_escape"
                            )
                        ),
                        "done": homework.done,
                        "est_service_groupe": getattr(
                            homework, "estServiceGroupe", None
                        ),
                    }
                )
                Devoir = Devoir + 1
                if homework.done == 1:
                    Devoirfait = Devoirfait + 1
                else:
                    Devoirnonfait = Devoirnonfait + 1

        data["nb_devoir_Demain"] = Devoir
        data["nb_devoirF_Demain"] = Devoirfait
        data["nb_devoirNF_Demain"] = Devoirnonfait

        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Une erreur est retournée sur le traitement des devoirs-lig: %s; %s",
            line_number,
            e,
        )


def notifications(client):
    try:
        # Récupération des notifications
        notification_eleve = client.information_and_surveys()
        data = {"Message": []}
        # Récupération des notifications
        for notif in notification_eleve:
            data["Message"].append(
                {
                    "Sujet": (notif.title),
                    "Auteur": (notif.author),
                    "Création": (notif.creation_date).strftime("%d/%m"),
                }
            )
        return data["Message"]
    except Exception as e:
        logging.error(
            "Un erreur est retourné sur le traitement des notifications: %s", e
        )


def absences(client):
    try:
        # Récupération  des absences pour l'année
        # absences = [period.absences for period in client.periods]
        # Récupération  des absences pour la période en cours
        absences = client.current_period.absences
        absences = sorted(absences, key=lambda absence: absence.from_date, reverse=True)

        # Transformation des absences en Json
        data = {"absence": []}
        nbabsences = 0
        for absence in absences:
            data["absence"].append(
                {
                    "id": absence.id,
                    "date_debut": absence.from_date.strftime("%d/%m/%y %H%M"),
                    "date_debut_format": absence.from_date.strftime("Le %d %b à %H%M"),
                    "date_fin": absence.to_date.strftime("%d/%m/%y %H%M"),
                    "justifie": absence.justified,
                    "nb_heures": absence.hours,
                    "nb_jours": absence.days,
                    "raison": str(absence.reasons)[2:-2],
                }
            )
            nbabsences = nbabsences + 1
        data["nb_absences"] = nbabsences

        return data
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des absences: %s", e)


def punissions(client):
    try:
        # Récupération des punitions
        punitions = client.current_period.punishments
        # Transformation des punition   en Json
        data = {"punition": []}
        nbpunition = 0
        for punition in punitions:
            data["punition"].append(
                {
                    "type": punition.nature,
                    "raison": punition.reasons,
                    "donneur": punition.giver,
                    "date": punition.given.strftime("%d/%m/%Y"),
                    "date_court": punition.given.strftime("%d/%m"),
                    "Competence": punition.grade,
                    "Commentaire": punition.comment,
                    "coeff": punition.coefficient,
                }
            )
            nbpunition = nbpunition + 1
        data["Nb_Punissions"] = nbpunition
        return data
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des Punissions: %s", e)


def ical(client):
    # Récupération des coordonnées ICAL
    try:

        jsondata = {"ICAL": client.export_ical(2)}
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
        logging.debug("Nom de l''identité %s", clientinfo.name)
        logging.debug("Nom de l''identité %s", clientinfo.class_name)
        logging.debug("Nom de l''identité %s", clientinfo.establishment)
        """
            if hasattr(clientinfo, "email"):
                identiteinfo["email"] = append(clientinfo.email)
            else:
                identiteinfo["email"] = ""

        if clientinfo.ine_number:
            identiteinfo["INE"] = append(clientinfo.ine_number)
        else:
            identiteinfo["INE"] = ""

        if clientinfo.phone:
            identiteinfo["Phone"] = clientinfo.phone
        else:
            identiteinfo["Phone"] = ""

        if clientinfo.address:
            (
                identiteinfo["Addresse1"],
                identiteinfo["Addresse2"],
                identiteinfo["Addresse3"],
                identiteinfo["Addresse4"],
                identiteinfo["CP"],
                identiteinfo["Province"],
                identiteinfo["Ville"],
            ) = clientinfo.adress
        else:
            identiteinfo["Addresse1"] = identiteinfo["Addresse2"] = identiteinfo[
                "Addresse3"
            ] = identiteinfo["Addresse4"] = identiteinfo["CP"] = identiteinfo[
                "Province"
            ] = identiteinfo[
                "Ville"
            ] = ""

        if clientinfo.delegue:
            identiteinfo["delegue"] = clientinfo.delegue
        else:
            identiteinfo["delegue"] = ""
        """
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
    # Étape 1 : Extraire la partie de l'URL jusqu'à `/pronote/`
    ## We need to change url because
    base_url = qrcode_data["url"].split("?login=true")[0]
    # base_url = qrcode_data["url"].split("/pronote/")[0] + "/pronote/"

    # Étape 2 : Extraire la dernière partie de l'URL qui commence par `mobile.`

    last_part = base_url.split("parent.html")[0] + "mobile.parent.html"

    qrcode_data["url"] = last_part
    logging.debug("Les info du QRCode : %s", qrcode_data)
    Token_data = Account.qrcode_login(
        qrcode_data,
        "4321",
        uuid="ProJote",
    )
    return Token_data


def RenewToken(client):
    try:
        # Récupération des tokens
        data = {"Token": []}
        data["Token"] = client.export_credentials()

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

    if not pronote_url == "":
        if ent == "":
            if pronote_url.endswith(
                ".index-education.net/pronote/eleve.html?login=true"
            ):
                pronote_url = pronote_url[: -len("?login=true")]
                logging.info("URL  modifiée :", pronote_url)
        else:
            if pronote_url.endswith(".index-education.net/pronote/eleve.html"):
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


def read_socket():
    global JEEDOM_SOCKET_MESSAGE
    try:
        if not JEEDOM_SOCKET_MESSAGE.empty():
            logging.debug("Message received in socket JEEDOM_SOCKET_MESSAGE")

            raw_message = JEEDOM_SOCKET_MESSAGE.get()
            decoded_message = raw_message.decode("utf-8")
            logging.debug("Decoded message: %s", decoded_message)
            if (
                not decoded_message.strip()
            ):  # Vérifier si la chaîne est vide après suppression des espaces
                logging.error("Message vide ou invalide reçu depuis le socket.")
                return
            try:
                message = json.loads(decoded_message)
            except json.JSONDecodeError as e:
                logging.error("Erreur de décodage JSON : %s", e)
                logging.debug("Message en erreur : %s", stripped_message)
                return

            logging.debug("Le MESSAGE reçu est  %s", message)
            if message["apikey"] != _apikey:
                logging.error("Invalid apikey from socket: %s", message)
            # d'abord je me connecte
            # Procédure de connection
            # On test que l'on a bien les information de TOKEN

            # Vérifier que les informations de Token sont présentes et non vides

            required_keys = ["TokenId", "TokenUsername", "TokenPassword", "TokenUrl"]
            all_keys_present = True
            for key in required_keys:
                if key not in message or not message[key].strip():
                    logging.error("Information de Token manquante ou vide : %s", key)
                    all_keys_present = False

            if all_keys_present:
                logging.debug(
                    "Toutes les informations de Token sont présentes et non vides. JE me connecte avec le Token"
                )
                if "parent.html" in message["TokenUrl"]:
                    client = pronotepy.ParentClient.token_login(
                        pronote_url=message["TokenUrl"],
                        username=message["TokenUsername"],
                        password=message["TokenPassword"],
                        client_identifier=message["TokenId"],
                        uuid="ProJote",
                    )
                else:
                    client = pronotepy.Client.token_login(
                        pronote_url=message["TokenUrl"],
                        username=message["TokenUsername"],
                        password=message["TokenPassword"],
                        client_identifier=message["TokenId"],
                        uuid="ProJote",
                    )

                ### 05/01/2025 : A revalider si je dois doubler
                credentials = client.export_credentials()
                # client = pronotepy.Client.token_login(**credentials)

                tokenconnected = "true"
            # Si il manque des informations de Token, ou que l'on n'a pas réussi à se connecter avec le Token, on se connecte avec les informations de compte
            if not all_keys_present:
                logging.info("Je me connecte via la compte et le mot de passe")
                if message["cas"] != "":
                    logging.debug("Cas/Ent reçu : %s", message["cas"])
                    ent = class_for_name("pronotepy.ent", message["cas"])
                else:
                    ent = ""
                # temp en attendant de revalider le champs$response dans PRojote.PHP et docn de finir QRCODE

                if message["CptParent"] == "1":
                    logging.info("Je me connecte en tant que parent")
                    ## connection en tant que parent
                    client, listenfant = Connectparent(
                        pronote_url=message["url"],
                        login=message["login"],
                        password=message["password"],
                        ent=ent,
                        enfant=message["enfant"],
                    )
                else:
                    logging.info("Je me connecte en tant qu'élève")
                    client = Connect(
                        pronote_url=message["url"],
                        login=message["login"],
                        password=message["password"],
                        ent=ent,
                    )
                # Maintenant que connecté je vais chercher les informations de Token pour la prochaine fois

                client = GetTokenFromLogin(client)

                # J'écris le fichier avec les infos de base
                logging.debug("Je vais tester si nous sommes loggué")
            if client is not None and client.logged_in:
                # J'écris le token pour la prochaine fois
                writedataPronotepy(
                    client, "/var/www/html/plugins/ProJote/data", message["CmdId"]
                )
                logging.debug("Nous sommes loggué")
                # Je vais chercher les informations
                jsondata = {}
                jsondata["CmdId"] = message["CmdId"]
                # Liste enfant s'applique que au compte parent
                ### A supprimer
                if message["command"] == "Validate":
                    logging.debug("Je valide que nous sommes connecté")
                    ##Neutralisationdu champs cptype car qrcode non fonctionnel
                    if message["cpttype"] == "compte" or message["cpttype"] == "":
                        dossier = "/tmp/jeedom/ProJote/" + str(message["CmdId"]) + "/"
                        verifdossier(dossier)
                        if message["CptParent"] == "1":
                            # Le but est de tester la connection et de mettre à jours les informations de l'éléve
                            logging.debug("Je lance la commande de Validation")
                            if len(listenfant) != 0:
                                # j'écris dans un fichier la listes des enfants

                                chemin_fichier = os.path.join(
                                    dossier,
                                    "listenfant.ProJote",
                                )
                                write_listenfant_to_file(listenfant, chemin_fichier)
                                writedataPronotepy(
                                    client._selected_child, dossier, message["CmdId"]
                                )
                                logging.debug(
                                    "Je viens de mettre à jours le fichier pour un compte parent : %s",
                                    chemin_fichier,
                                )
                            else:
                                # J'écris le fichier avec les infos de base
                                writedataPronotepy(
                                    client.info, dossier, message["CmdId"]
                                )

                        else:
                            writedataPronotepy(client.info, dossier, message["CmdId"])
                            logging.debug(
                                "Je viens de mettre à jours le fichier : %s",
                                dossier,
                            )
                else:
                    # là nous sommes vraiment en train de chercher les données du comptes
                    # Maintenant que je suis connecté je vais collecter les infos d'identités
                    logging.debug(
                        "Validation Token %s",
                        tokenconnected,
                    )
                    if (tokenconnected == "true") and (message["CptParent"] == "1"):
                        logging.debug(
                            "Le nom de l'élève %s", client._selected_child.name
                        )

                        jsondata["eleve"] = identites(client._selected_child)
                        # Neutralisation car listenfant en erreur
                        # jsondata["listenfant"] = listenfant
                        if (
                            client._selected_child.profile_picture
                            and client._selected_child.profile_picture.url
                        ):
                            jsondata["Photo"] = (
                                client._selected_child.profile_picture.url
                            )
                    else:
                        jsondata["eleve"] = identites(client.info)
                        if (
                            client.info.profile_picture
                            and client.info.profile_picture.url
                        ):
                            jsondata["Photo"] = client.info.profile_picture.url
                    # J'ajoute l'emploi du temps
                    logging.info("Je récupére l'emploi du temps")
                    jsondata["emploi_du_temps"] = Emploidutemps(client)
                    # J'ajoute les notes
                    logging.info("Je récupére les notes")
                    jsondata["notes"] = notes(client)
                    # J'ajoute les devoirs
                    logging.info("Je récupére les devoirs")
                    jsondata["devoirs"] = devoirs(client)
                    # j'ajoute les menus
                    logging.info("Je récupére les menus")
                    jsondata["Menus"] = menus(client)
                    # J'ajoute les Messages
                    logging.info("Je récupére les notifications")
                    jsondata["Notifications"] = notifications(client)
                    # j'ajoutes les absences
                    logging.info("Je récupére les absences")
                    jsondata["Absences"] = absences(client)
                    # J'ajoutes les punitions
                    logging.info("Je récupére les punitions")
                    jsondata["Punissions"] = punissions(client)
                    # J'ajoutes l'ICAL
                    logging.info("Je récupére l'ICAL")
                    jsondata["Ical"] = ical(client)
                    logging.info("Je renew le Token")
                    jsondata["Token"] = RenewToken(client)
                    # J'envoie les données à Jeedom
                    logging.debug("Données à envoyer : %s", json.dumps(jsondata))
                    jeedom_com.send_change_immediate(jsondata)
                    logging.info("Fin de récupération d'info depuis Projoted.py")

            else:
                echo = "Le compte n'est pas loggué"
                logging.error(echo)
                return False
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error("Erreur d'éxécution du deamon : lig. %s -  %s", line_number, e)


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
    try:
        os.remove(_pidfile)
    except:
        pass
    try:
        jeedom_socket.close()
    except:
        pass
    logging.debug("Exit 0")
    # sys.stdout.flush()
    os._exit(0)


# ----------------------------------------------------------------------------
# Ici est le script qui va écouter le socket. Mais la premiére chose qu'il va faire est de renvoyer sont PiD pour validation.
_log_level = "error"
_socket_port = 55369  # Coder la prise en charge du port configurer
_socket_host = "localhost"
_pidfile = "/tmp/ProJoted.pid"
_apikey = ""
_callback = ""
_cycle = 0.3

parser = argparse.ArgumentParser(description="Projoted Daemon for Jeedom plugin")
parser.add_argument("--loglevel", help="Log Level for the daemon", type=str)
parser.add_argument("--callback", help="Callback", type=str)
parser.add_argument("--apikey", help="Apikey", type=str)
parser.add_argument("--cycle", help="Cycle to send event", type=str)
parser.add_argument("--pid", help="Pid file", type=str)
parser.add_argument("--socketport", help="Port for Projote Deamon", type=str)
args = parser.parse_args()

if args.loglevel:
    _log_level = args.loglevel
if args.callback:
    _callback = args.callback
if args.apikey:
    _apikey = args.apikey
if args.pid:
    _pidfile = args.pid
if args.cycle:
    _cycle = float(args.cycle)
if args.socketport:
    _socket_port = args.socketport

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

    logging.info("j'écris " + str(_pidfile))
    jeedom_socket = jeedom_socket(port=_socket_port, address=_socket_host)
    listen()
except Exception as e:
    logging.error("Fatal error: %s", e)
    logging.info(traceback.format_exc())
    shutdown()
