try:
    # TO DO :: add log to plugin for troubleshoote
    import pronotepy
    from pronotepy.ent import *
    import sys
    import json
    import logging
    import importlib
    import os
    import datetime
    import requests
    import argparse

    try:
        from jeedom.jeedom import *
    except ImportError as e:
        logging.error(
            "Error: importing module jeedom.jeedom lig.%s - %s ",
            e.__traceback__.tb_lineno,
            e,
        )
        sys.exit(1)

    # Import de l'ENT
    def class_for_name(module_name, class_name):
        try:
            # load the module, will raise ImportError if module cannot be loaded
            m = importlib.import_module(module_name)
            return getattr(m, class_name)
        except Exception:
            return None

    def Connectparent(pronote_url, login, password, ent, enfant):
        client = None  # Initialisation de la variable client
        # Je valide que j'ai les bonnes informations pour me connecter en tant que Parent
        try:
            if login == "":
                logging.error("Pas de login reçu ")
                if pronote_url == "":
                    logging.error("pas d'URL reçu")
                elif ent == "":
                    if pronote_url.endswith(
                        ".index-education.net/pronote/parent.html?login=true"
                    ):
                        pronote_url = pronote_url[: -len("?login=true")]
                        logging.info("URL  modifiée : %s", pronote_url)
                elif pronote_url.endswith(".index-education.net/pronote/parent.html"):
                    pronote_url += "?login=true"
                    logging.info("URL  modifiée : %s", pronote_url)
            if password != "":
                ### neutralisé pour le moment
                """if isinstance(password, str):
                    password = my_decrypt(
                        password,
                        "084781141BD01304180B9B58120E4E058C1434394DDED646BF4ECC95380B9442",
                    )
                else:
                    logging.error("Le password n'est pas un string")"""
            else:
                logging.error("pas de password reçu sur le deamon")
            # Maintenant j'essaye de me connecter
            logging.debug("Tentative de connection en tant que parent")
            client = pronotepy.ParentClient(pronote_url, login, password, ent)
            logging.info("Je suis connecté en tant que parent")

            client.parent = 1
            client.listenfant = []
            # Je retourne la liste d'enfants du compte parent
            for child in client.children:
                logging.debug(
                    "Liste des enfants trouvés du compte Parent : %s", child.name
                )
                client.listenfant.append(child.name)
            # Si pas d'enfant  par défault je prend le premier enfant
            if enfant == "":
                client.set_child(client.listenfant[0])
                logging.info(
                    "Je suis connecté à l'enfant par défault %s", client.listenfant[0]
                )

            else:
                # Pour mettre à jour la liste d'enfant, je vérifie toujorus la liste
                client.set_child(enfant)
                logging.info("Je suis connecté à l'enfant : %s", enfant)

            return client  # , listenfant

        except Exception as e:
            line_number = e.__traceback__.tb_lineno
            logging.error("Connection parent échouée : lig. %s -   %s", line_number, e)

    def ConnectEleve(pronote_url, login, password, ent):
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
            # Neutralisé pour le moment
            """password = my_decrypt(
                password, "084781141BD01304180B9B58120E4E058C1434394DDED646BF4ECC95380B9442"
            )"""
        else:
            logging.error("pas de password reçu sur le deamon")
        try:
            client = pronotepy.Client(pronote_url, login, password, ent)
            logging.info("Je suis connecté")
            return client
        except Exception as e:
            logging.error("Connection échouée :  %s", e)

    def TokenLogin(Account):
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

        return {
            "Token_URL": Token_data.pronote_url,
            "Token_username": Token_data.username,
            "Token_Password": Token_data.password,
            "Token_UUID": Token_data.uuid,
            "pin": "4321",
            "uuid": "ProJote",
        }

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

    def download_image(url, filepath):
        try:
            # Effectuer une requête HTTP pour récupérer le contenu de l'image
            response = requests.get(url)
            # Vérifier si la requête a réussi (code de statut 200)
            if response.status_code == 200:
                # J'aimerai un valider que l'image récupérée via url est bien différente de l'image de filepath
                if os.path.exists(filepath):
                    with open(filepath, "rb") as f:
                        existing_image = f.read()
                    if existing_image == response.content:
                        logging.info(
                            "L'image est déjà à jour, pas besoin de la télécharger."
                        )

                    else:
                        # Ouvrir un fichier en mode écriture binaire
                        logging.info("L'image est différente,je la télécharge.")
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

    def writedataPronotepy(client, dossier, eqid):
        try:
            # nom_fichier = f"{client.name}.ProJote"
            nom_fichier = "enfant.ProJote.json.txt"
            # nom_fichier = nom_fichier.replace(" ", "")
            eqid = str(eqid)
            chemin_fichier = f"{dossier}/{eqid}"
            verifdossier(chemin_fichier)
            chemin_fichier = os.path.join(f"{dossier}/{eqid}", nom_fichier)
            logging.debug("voici les informations d'écriture : %s", chemin_fichier)
            # Lire le fichier pour récupérer les données existantes
            existing_data = {}
            if os.path.exists(chemin_fichier):
                with open(chemin_fichier, "r") as fichier:
                    lines = fichier.readlines()
                    for line in lines:
                        line = line.strip()
                        if ": " in line:  # Vérifie que la ligne contient ": "
                            key, value = line.split(": ", 1)
                            existing_data[key.lower().replace(" ", "_")] = value.strip()
            # Ouvrir le fichier en mode écriture, ou créer s'il n'existe pas
            # Préparer les données à écrire
            data = {
                "Date": str(datetime.datetime.now()),
                "Name": client.info.name,
                "Token": client.export_credentials(),
            }
            if client._selected_child:
                logging.debug(
                    "Je recherche l'enfants : %s", client._selected_child.name
                )
                # Je retourne la liste d'enfants du compte parent
                client.listenfant = []
                for child in client.children:
                    logging.debug(
                        "Liste des enfants trouvés du compte Parent : %s", child.name
                    )
                    client.listenfant.append(child.name)
                data["Parent"] = "1"
                data["Liste_Enfant"] = json.dumps(
                    client.listenfant, separators=(",", ":")
                )

                data["Eleve"] = client._selected_child.name
                data["Classe"] = client._selected_child.class_name
                data["Etablissement"] = client._selected_child.establishment
                # data["Raw_Parent"] = client._selected_child.raw_resource
                data["Picture"] = client._selected_child.profile_picture.url
            else:
                data["Eleve"] = client.info.name
                data["Class_Name"] = client.info.class_name
                data["Establishment"] = client.info.establishment
                data["Parent"] = "0"
                data["Picture"] = client.info.profile_picture.url
                data["Classe"] = client.info.class_name
                data["Etablissement"] = client.info.establishment
                # Recherche de l'image et téléchargement
                # Télécharger l'image localement
            image_filepath = os.path.join(f"{dossier}/{eqid}", "profile_picture.jpg")
            if client._selected_child:
                if download_image(
                    client._selected_child.profile_picture.url, image_filepath
                ):
                    data["Local_Picture"] = f"{dossier}/{eqid}/profile_picture.jpg"
            elif download_image(client.info.profile_picture.url, image_filepath):
                data["Local_Picture"] = f"{dossier}/{eqid}/profile_picture.jpg"
            else:
                logging.error("Erreur lors du téléchargement de l'image")
            # Écrire les données au format JSON dans un fichier
            with open(chemin_fichier, "w") as fichier:
                json.dump(data, fichier, indent=4)
        except Exception as e:
            line_number = e.__traceback__.tb_lineno
            logging.error("Ecriture du fichier échoué : lig.%s - %s", line_number, e)

    if __name__ == "__main__":
        # Définition du niveau de log par défaut
        _log_level = "INFO"

        # type de commande python3 ../../resources/ProJoted/LoginConnect.py 'E2A24D72F39BA48F2E400CA838E5CCB5F5F6733C64FA762F8FEF473AA7D5BBAD05F641FFE8C6CFE9486564470BB8FCD0F9E4EAE77338B2B45B9A28DB85EC79AE0729E20FF4D0D60D79A7E0CA0380364CB05DC4C1FC3D71E2575423FECF4A0BDD74ADE24A020B222916617B30B189C724' '4C0B20E070291B38E256452F80138CBE' 'https://0912109y.index-education.net/pronote/parent.html?identifiant=7tTQmnp4Qyu7ZR58#/mobile.parent.html' '1234'
        # get Arguments in right order : Jeton, Login, Url, Pin, Loglevel
        parser = argparse.ArgumentParser(
            description="Script de conexion à Pronote avec Login"
        )
        parser.add_argument("--URL", help="URL de connexion à Projote", type=str)
        parser.add_argument("--Login", help="Login de connexion à Projote", type=str)
        parser.add_argument(
            "--Password", help="Mot de passe de connexion à Projote", type=str
        )
        parser.add_argument("--Ent", help="Nom de l'ENT", type=str)
        parser.add_argument("--Enfant", help="Nom de l'enfant", type=str)
        parser.add_argument("--Eqid", help="ID de l'équipement", type=str)
        parser.add_argument("--Loglevel", help="Niveau de log", type=str)
        args = parser.parse_args()

        if args.URL:
            Pronote_url = args.URL
        if args.Login:
            Username = args.Login
        if args.Password:
            Password = args.Password
        if args.Ent:
            Ent = args.Ent
        else:
            Ent = None
        if args.Enfant:
            NomEnfant = args.Enfant
        else:
            NomEnfant = ""
        if args.Eqid:
            EqID = args.Eqid
        if args.Loglevel:
            _log_level = args.Loglevel

        jeedom_utils.set_log_level(_log_level)

        # Je qualifie l'ENT
        if Ent != "Inconnu" or None:
            ClassEnt = class_for_name("pronotepy.ent", Ent)
        else:
            ClassEnt = ""

        # Identification d'un compte parent
        if not Pronote_url.endswith("?login=true"):
            Pronote_url = Pronote_url + "?login=true"

        if "parent.html" in Pronote_url:
            logging.info("LOG : Je tente de me connecter en tant que Parent")
            Account = Connectparent(
                pronote_url=Pronote_url,
                login=Username,
                password=Password,
                ent=ClassEnt,
                enfant=NomEnfant,
            )

        else:
            logging.info("LOG : Je tente de me connecter en tant qu' élève")
            Account = ConnectEleve(
                pronote_url=Pronote_url, login=Username, password=Password, ent=ClassEnt
            )

        if Account.logged_in:
            logging.info("LOG : Je suis connecté et je demande le QR LOG")
            logging.info("Login : %s", Account.username)
            logging.info("URL : %s", Account.pronote_url)
            logging.info("Password : %s", Account.password)
            logging.info("ENT : %s", Account.ent)
            logging.info("Picture : %s", Account.info.profile_picture)
            # je requête le QR code
            Pin = "4321"
            Qrcode_data = Account.request_qr_code_data(Pin)
            logging.debug("QR_code : %s", Qrcode_data)
            # JE me loggue avec le QR code

            # Tentative de connexion via le QR code

        if "parent" not in Qrcode_data["url"]:
            # Test de connection en tant que Parent
            Account = pronotepy.Client.qrcode_login(
                qr_code=Qrcode_data, pin=Pin, uuid="ProJote"
            )
        else:
            Account = pronotepy.ParentClient.qrcode_login(
                qr_code=Qrcode_data, pin=Pin, uuid="ProJote"
            )
            if NomEnfant != "":
                Account.set_child(NomEnfant)
            # Je crée le fichier pou le Token.
            writedataPronotepy(Account, "/var/www/html/plugins/ProJote/data", EqID)

except Exception as e:
    line_number = e.__traceback__.tb_lineno
    logging.error("Ecriture du fichier échoué : lig.%s - %s", line_number, e)
    sys.exit(1)
