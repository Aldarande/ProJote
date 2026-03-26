"""
QRConnect.py — Connexion à Pronote via QR code scanné depuis l'application mobile.

Ce script est appelé par le plugin Jeedom (via ProJote.ajax.php / action ValidateQRCode)
quand l'utilisateur scanne un QR code Pronote et saisit son PIN.

Le QR code Pronote contient 3 informations :
  - jeton : clé chiffrée temporaire
  - login : identifiant de session
  - url   : URL de l'établissement

Avec ces infos + le PIN choisi par l'utilisateur, Pronote crée une session
token persistante qui permettra des reconnexions automatiques sans ressaisir
le mot de passe.

Arguments attendus en ligne de commande :
  --Jeton    : Jeton extrait du QR code
  --QRLogin  : Login extrait du QR code
  --QRUrl    : URL extraite du QR code
  --Pin      : Code PIN à 4 chiffres saisi par l'utilisateur
  --Eqid     : Identifiant de l'équipement Jeedom
  --Uuid     : UUID unique de l'équipement (identifiant de session Pronote)
  --Loglevel : Niveau de verbosité des logs
"""
try:
    # TO DO :: add log to plugin for troubleshoote
    import pronotepy
    import sys
    import json
    import argparse
    import logging
    import json
    import os

    # Ajout du répertoire du script au `path` pour les imports relatifs
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

    try:
        from jeedom.jeedom import *

        # Importer la fonction writedataPronotepy
        from LoginConnect import *
    except ImportError as e:
        logging.error(
            "Error: importing module jeedom.jeedom lig.%s - %s ",
            e.__traceback__.tb_lineno,
            e,
        )
        sys.exit(1)

    if __name__ == "__main__":
        # ─────────────────────────────────────────────────────────────────────
        # POINT D'ENTRÉE PRINCIPAL
        #
        # Flux d'exécution :
        #   1. Lecture des arguments (jeton, login, url, pin, uuid...)
        #   2. Tentative de connexion via QR code (élève ou parent selon l'URL)
        #   3. Si connexion réussie → sauvegarde du token + infos élève sur disque
        # ─────────────────────────────────────────────────────────────────────

        # Définition du niveau de log par défaut
        _log_level = "INFO"

        parser = argparse.ArgumentParser(
            description="Script de conexion à Pronote avec un QRCode"
        )
        parser.add_argument("--Jeton", help="Jeton de connexion à Projote", type=str)
        parser.add_argument("--QRLogin", help="Login de connexion à Projote", type=str)
        parser.add_argument("--QRUrl", help="URL pour se connecter", type=str)
        parser.add_argument("--Pin", help="Pin", type=str)
        parser.add_argument("--Eqid", help="ID de l'équipement", type=str)
        parser.add_argument("--Loglevel", help="Niveau de log", type=str)
        parser.add_argument("--Uuid", help="UUID unique de l'équipement", type=str)
        parser.add_argument("--datadir", help="Chemin du dossier data du plugin", type=str)
        args = parser.parse_args()

        if args.QRUrl:
            QRUrl = args.QRUrl
        if args.QRLogin:
            QRLogin = args.QRLogin
        if args.Jeton:
            Jeton = args.Jeton
        if args.Pin:
            Pin = str(args.Pin)
        if args.Eqid:
            EqID = str(args.Eqid)
        if args.Loglevel:
            _log_level = args.Loglevel
        Uuid = args.Uuid or None
        DataDir = args.datadir or "/var/www/html/plugins/ProJote/data"

        jeedom_utils.set_log_level(_log_level)

        Qrcode_data = {
            "jeton": Jeton,
            "login": QRLogin,
            "url": QRUrl,
        }
        # Ne pas logger Qrcode_data : contient le jeton et le login (credentials)

        # Tentative de connexion via le QR code.
        # L'URL Pronote indique si c'est un compte parent ("parent.html") ou élève.
        # L'UUID permet à Pronote d'identifier cet équipement de manière unique.
        if "parent" not in QRUrl:
            # Connexion en tant qu'ÉLÈVE directement
            Account = pronotepy.Client.qrcode_login(
                qr_code=Qrcode_data, pin=Pin, uuid=Uuid
            )
        else:
            # Connexion en tant que PARENT (qui peut avoir plusieurs enfants)
            logging.debug(f"QRConnect.py :: Compte parent")
            Account = pronotepy.ParentClient.qrcode_login(
                qr_code=Qrcode_data, pin=Pin, uuid=Uuid
            )
            logging.debug(f"QRConnect.py :: {Account}")

        if Account.logged_in:
            logging.info("Client connecté")
            # Sauvegarde du token et des infos élève dans le fichier JSON de l'équipement
            writedataPronotepy(Account, DataDir, EqID)
except Exception as e:
    line_number = e.__traceback__.tb_lineno
    print("An error occurred: line ", line_number, e)
    sys.exit(1)
