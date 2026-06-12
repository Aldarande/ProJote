# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""
LoginConnect.py — Connexion à Pronote via identifiants login/mot de passe.

Ce script est appelé par le plugin Jeedom (via ProJote.ajax.php) quand l'utilisateur
valide ses identifiants dans l'interface. Il fait deux choses principales :
  1. Se connecte à Pronote avec le login/mot de passe fourni.
  2. Génère un token de connexion (QR code → session persistante) et sauvegarde
     les informations de l'élève dans un fichier JSON sur le disque.

Ce fichier est aussi importé par QRConnect.py et ProJoted.py pour réutiliser
ses fonctions utilitaires (writedataPronotepy, verifdossier, etc.).

Arguments attendus en ligne de commande :
  --URL       : URL de l'établissement sur Pronote
  --Login     : Identifiant de connexion
  --Password  : Mot de passe
  --Ent       : Nom de l'ENT (Espace Numérique de Travail), ex: "ac_montpellier"
  --Enfant    : Nom de l'enfant à sélectionner (pour les comptes parents)
  --Eqid      : Identifiant de l'équipement Jeedom (pour sauvegarder au bon endroit)
  --Uuid      : UUID unique de l'équipement (identifiant de session Pronote)
  --Loglevel  : Niveau de verbosité des logs (debug, info, warning, error)
"""

try:
    # TO DO :: add log to plugin for troubleshoote
    import pronotepy
    from pronotepy.ent import *
    import sys
    import json
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)-15s][%(levelname)s] : %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    import importlib
    import os
    import datetime
    import requests
    import argparse

    # Chiffrement
    import hashlib
    import base64
    import binascii
    from Crypto.Cipher import AES

    try:
        from jeedom.jeedom import *
    except ImportError as e:
        logging.error(
            "Error: importing module jeedom.jeedom lig.%s - %s ",
            e.__traceback__.tb_lineno,
            e,
        )
        sys.exit(1)

    # ─────────────────────────────────────────────────────────────────────────
    # FONCTIONS UTILITAIRES
    # ─────────────────────────────────────────────────────────────────────────

    def my_decrypt(data, apikey, passphrase=None):
        """
        Déchiffre des données AES-256-CBC chiffrées par PHP.
        La clé est dérivée de l'API key Jeedom via SHA-256.

        Audit sécurité (P2c, juin 2026) : dérivation correcte — l'API key Jeedom
        est un secret aléatoire à forte entropie (pas une valeur prévisible),
        SHA-256 suffit comme KDF dans ce cas. Voir SECURITY-AUDIT.md pour les
        limites connues (CBC non authentifié, fallback brut en cas d'échec).
        """
        if not data:
            return ""
        if passphrase is None:
            passphrase = hashlib.sha256(apikey.encode()).hexdigest()
        try:
            unpad = lambda s: s[: -s[-1]]
            key = binascii.unhexlify(passphrase)
            decoded_raw = base64.b64decode(data)
            encrypted = json.loads(decoded_raw.decode("ascii"))
            encrypted_data = base64.b64decode(encrypted["data"])
            iv = base64.b64decode(encrypted["iv"])
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(encrypted_data)
            return unpad(decrypted).decode("ascii").rstrip()
        except Exception as e:
            logging.error("Cannot decrypt datas in LoginConnect: %s", e)
            return data  # Retourne brut si échec (fallback compatibilité)

    # Import de l'ENT
    def class_for_name(module_name, class_name):
        """
        Charge dynamiquement une classe Python par son nom de module et de classe.
        Utilisé pour charger l'ENT (ex: "pronotepy.ent", "ac_montpellier").
        Retourne None si le module ou la classe est introuvable.
        """
        try:
            # load the module, will raise ImportError if module cannot be loaded
            m = importlib.import_module(module_name)
            return getattr(m, class_name)
        except Exception:
            return None

    def Connectparent(pronote_url, login, password, ent, enfant, apikey=None):
        """
        Connecte un compte PARENT à Pronote avec login/mot de passe.

        Un compte parent peut avoir plusieurs enfants. Cette fonction :
          - Se connecte à Pronote en tant que parent
          - Récupère la liste des enfants du compte
          - Sélectionne l'enfant demandé (ou le premier par défaut)

        Args:
            pronote_url (str): URL complète du portail Pronote de l'établissement
            login (str):       Identifiant de connexion
            password (str):    Mot de passe
            ent (class|None):  Classe ENT si l'établissement utilise un ENT, sinon None
            enfant (str):      Nom de l'enfant à sélectionner ("" = premier de la liste)

        Returns:
            pronotepy.ParentClient: Client connecté, ou None si la connexion échoue
        """
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
            if password == "":
                logging.error("pas de password reçu sur le deamon")
            # Maintenant j'essaye de me connecter
            if apikey:
                password = my_decrypt(password, apikey)
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

    def ConnectEleve(pronote_url, login, password, ent, apikey=None):
        """
        Connecte un compte ÉLÈVE à Pronote avec login/mot de passe.

        Contrairement au compte parent, un élève n'a pas de sélection d'enfant.
        La connexion retourne directement le client élève.

        Args:
            pronote_url (str): URL complète du portail Pronote de l'établissement
            login (str):       Identifiant de connexion
            password (str):    Mot de passe
            ent (class|None):  Classe ENT si nécessaire, sinon None

        Returns:
            pronotepy.Client: Client connecté, ou None si la connexion échoue
        """
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
        if password == "":
            logging.error("pas de password reçu sur le deamon")
        try:
            if apikey:
                password = my_decrypt(password, apikey)
            client = pronotepy.Client(pronote_url, login, password, ent)
            logging.info("Je suis connecté")
            return client
        except Exception as e:
            logging.error("Connection échouée :  %s", e)

    def TokenLogin(Account, uuid="ProJote"):
        """
        Génère un token de connexion persistant à partir d'un compte déjà connecté.

        Pronote utilise un système de "QR code interne" pour créer des sessions
        longues durées sans avoir à retaper le mot de passe à chaque fois.
        Cette fonction demande ce QR code à Pronote, puis l'utilise pour créer
        une session token associée à cet équipement (identifié par uuid).

        Le token généré contient : URL, username, password (chiffré), client_identifier.
        Il est ensuite sauvegardé en configuration Jeedom pour les reconnexions futures.

        Args:
            Account: Client pronotepy déjà connecté (parent ou élève)
            uuid (str): Identifiant unique de l'équipement Jeedom (évite les conflits
                        si deux équipements utilisent le même compte Pronote)

        Returns:
            dict: Dictionnaire contenant les informations du token de reconnexion
        """
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
            uuid=uuid,
        )

        return {
            "Token_URL": Token_data.pronote_url,
            "Token_username": Token_data.username,
            "Token_Password": Token_data.password,
            "Token_UUID": Token_data.uuid,
            "pin": "4321",
            "uuid": uuid,
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

    def download_image(url, filepath, session=None):
        """
        Télécharge une image depuis une URL et la sauvegarde localement.

        Compare l'image distante à l'image locale existante pour éviter
        de télécharger inutilement si elle n'a pas changé.

        Args:
            url (str):       URL de l'image à télécharger (ex: photo de profil Pronote)
            filepath (str):  Chemin local où sauvegarder l'image
            session:         Session HTTP authentifiée (optionnel, sinon utilise requests)

        Returns:
            bool: True si le téléchargement a réussi (ou image déjà à jour), False sinon
        """
        try:
            # Effectuer une requête HTTP pour récupérer le contenu de l'image
            if session:
                response = session.get(url)
            else:
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

    def writedataPronotepy(client, dossier, eqid, backup_token=None):
        """
        Sauvegarde toutes les données de l'élève dans un fichier JSON sur le disque.

        Ce fichier (enfant.ProJote.json.txt) est le "fichier central" du plugin :
          - Il est lu par jeeProJote.php pour mettre à jour les commandes Jeedom
          - Il est relu au démarrage du démon pour restaurer la session précédente
          - Il contient le token de reconnexion + les infos élève + la photo

        Le fichier est créé dans : {dossier}/{eqid}/enfant.ProJote.json.txt
        Exemple : /var/www/html/plugins/ProJote/data/3/enfant.ProJote.json.txt

        Args:
            client: Client pronotepy connecté (parent ou élève)
            dossier (str): Répertoire racine des données du plugin
            eqid (str/int): ID de l'équipement Jeedom (détermine le sous-dossier)
        """
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
            credentials = client.export_credentials()
            logging.debug(
                "export_credentials: %s",
                {
                    k: (
                        v[:8] + "..."
                        if isinstance(v, str)
                        and len(v) > 8
                        and k not in ("pronote_url", "uuid")
                        else v
                    )
                    for k, v in credentials.items()
                },
            )
            data = {
                "Date": str(datetime.datetime.now()),
                "Name": client.info.name,
                "Token": credentials,
            }
            if backup_token is not None:
                data["BackupToken"] = backup_token
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
            pronote_session = getattr(
                getattr(client, "communication", None), "session", None
            )
            if client._selected_child:
                if download_image(
                    client._selected_child.profile_picture.url,
                    image_filepath,
                    pronote_session,
                ):
                    data["Local_Picture"] = f"{dossier}/{eqid}/profile_picture.jpg"
            elif download_image(
                client.info.profile_picture.url,
                image_filepath,
                pronote_session,
            ):
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
        # ─────────────────────────────────────────────────────────────────────
        # POINT D'ENTRÉE PRINCIPAL
        # Ce bloc s'exécute uniquement quand le script est lancé directement
        # (pas quand il est importé par ProJoted.py ou QRConnect.py).
        #
        # Flux d'exécution :
        #   1. Lecture des arguments de la ligne de commande
        #   2. Connexion à Pronote (parent ou élève selon l'URL)
        #   3. Génération d'un token de reconnexion via QR code interne
        #   4. Sauvegarde des données élève + token dans un fichier JSON
        # ─────────────────────────────────────────────────────────────────────

        # Définition du niveau de log par défaut
        _log_level = "INFO"

        # Exemple : python3 LoginConnect.py --URL https://... --Login user --Password pass --Eqid 1 --Uuid xxx
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
        parser.add_argument("--Uuid", help="UUID unique de l'équipement", type=str)
        parser.add_argument(
            "--Pin", help="Code PIN pour la génération du jeton", type=str
        )
        parser.add_argument(
            "--apikey", help="Clé API Jeedom pour déchiffrement", type=str
        )
        parser.add_argument(
            "--datadir", help="Chemin du dossier data du plugin", type=str
        )
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
        if args.Pin and len(args.Pin) == 4 and args.Pin.isdigit():
            Pin = args.Pin
            logging.debug("Utilisation du code PIN fourni : %s", Pin)
        else:
            Pin = "4321"  # Default PIN if not provided or invalid
            logging.debug("Utilisation du code PIN par défaut : 4321")
        if args.Loglevel:
            _log_level = args.Loglevel
        Uuid = args.Uuid or None
        DataDir = args.datadir or "/var/www/html/plugins/ProJote/data"
        ApiKey = args.apikey or None

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
                apikey=ApiKey,
            )

        else:
            logging.info("LOG : Je tente de me connecter en tant qu' élève")
            Account = ConnectEleve(
                pronote_url=Pronote_url,
                login=Username,
                password=Password,
                ent=ClassEnt,
                apikey=ApiKey,
            )

        if Account.logged_in:
            logging.info("LOG : Connecté à Pronote, demande du token QR")
            logging.info("Login : %s", Account.username)
            logging.info("URL : %s", Account.pronote_url)
            # Ne jamais logger Account.password
            logging.info("ENT : %s", Account.ent)
            logging.debug("Picture : %s", Account.info.profile_picture)

            # Demander deux QR codes depuis la session mot de passe (avant tout qrcode_login)
            # Ne pas logger les QR codes : ils contiennent des credentials temporaires
            Qrcode_data = Account.request_qr_code_data(Pin)
            Qrcode_data_backup = None
            try:
                Qrcode_data_backup = Account.request_qr_code_data(Pin)
                logging.debug("Second QR code demandé pour le token backup")
            except Exception as e:
                logging.warning(
                    "Impossible de demander le second QR code (backup) : %s", e
                )

            # Connexion principale via le QR code principal
            if "parent" not in Qrcode_data["url"]:
                PrimaryAccount = pronotepy.Client.qrcode_login(
                    qr_code=Qrcode_data, pin=Pin, uuid=Uuid
                )
            else:
                PrimaryAccount = pronotepy.ParentClient.qrcode_login(
                    qr_code=Qrcode_data, pin=Pin, uuid=Uuid
                )
                if NomEnfant != "":
                    PrimaryAccount.set_child(NomEnfant)

            # Génération du token backup depuis le second QR code
            backup_credentials = None
            if Qrcode_data_backup is not None:
                try:
                    backup_uuid = (Uuid + "-bk") if Uuid else None
                    if "parent" not in Qrcode_data_backup["url"]:
                        BackupAccount = pronotepy.Client.qrcode_login(
                            qr_code=Qrcode_data_backup, pin=Pin, uuid=backup_uuid
                        )
                    else:
                        BackupAccount = pronotepy.ParentClient.qrcode_login(
                            qr_code=Qrcode_data_backup, pin=Pin, uuid=backup_uuid
                        )
                    if BackupAccount.logged_in:
                        backup_credentials = BackupAccount.export_credentials()
                        logging.info("Token backup généré avec succès")
                except Exception as e:
                    logging.warning("Génération du token backup échouée : %s", e)

            # Sauvegarde du token principal + backup
            writedataPronotepy(
                PrimaryAccount, DataDir, EqID, backup_token=backup_credentials
            )

except Exception as e:
    line_number = e.__traceback__.tb_lineno
