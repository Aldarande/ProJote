try:
    # TO DO :: add log to plugin for troubleshoote
    import pronotepy
    import sys
    import json
    import argparse
    import logging
    import json

    sys.path.append("/docker/Jeedom/www/plugins/ProJote/resources/ProJoted")

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

        jeedom_utils.set_log_level(_log_level)

        Qrcode_data = {
            "jeton": Jeton,
            "login": QRLogin,
            "url": QRUrl,
        }

        Qrcode_data_json = json.dumps(Qrcode_data)
        logging.debug(f"QRConnect.py :: {Qrcode_data_json}")
        # Tentative de connexion via le QR code

        if "parent" not in QRUrl:
            # Test de connection en tant que Elève
            Account = pronotepy.Client.qrcode_login(
                qr_code=Qrcode_data, pin=Pin, uuid="ProJote"
            )
        else:
            logging.debug(f"QRConnect.py :: Compte parent")
            Account = pronotepy.ParentClient.qrcode_login(
                qr_code=Qrcode_data, pin=Pin, uuid="ProJote"
            )
            logging.debug(f"QRConnect.py :: {Account}")
        if Account.logged_in:
            logging.info("Client connecté")
            # Je crée le fichier pou le Token.
            writedataPronotepy(Account, "/var/www/html/plugins/ProJote/data", EqID)

except Exception as e:
    line_number = e.__traceback__.tb_lineno
    print("An error occurred: line ", line_number, e)
    sys.exit(1)
