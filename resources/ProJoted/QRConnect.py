# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

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
    import pronotepy
    import sys
    import json
    import argparse
    import logging
    import os

    # Activation du logging dès le départ pour que les erreurs précoces soient visibles
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)-15s][%(levelname)s] : %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

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
        # --apikey est passé par le PHP (cohérence avec LoginConnect.py). Les données du
        # QR Code transitent en clair (non chiffrées par la clé API), donc l'argument est
        # accepté mais non utilisé ici. Sans cette déclaration, argparse rejette l'appel
        # ("unrecognized arguments: --apikey") et la validation du QR échoue (code 2).
        parser.add_argument("--apikey", help="Clé API Jeedom (non utilisée ici)", type=str)
        args = parser.parse_args()

        QRUrl   = args.QRUrl   or ''
        QRLogin = args.QRLogin or ''
        Jeton   = args.Jeton   or ''
        Pin     = str(args.Pin)  if args.Pin   else ''
        EqID    = str(args.Eqid) if args.Eqid  else ''
        if args.Loglevel:
            _log_level = args.Loglevel
        Uuid    = args.Uuid    or None
        DataDir = args.datadir or "/var/www/html/plugins/ProJote/data"

        if not QRUrl or not QRLogin or not Jeton or not Pin:
            logging.error("QRConnect.py :: Arguments manquants — QRUrl=%s QRLogin=%s Jeton=%s Pin=%s",
                          bool(QRUrl), bool(QRLogin), bool(Jeton), bool(Pin))
            sys.exit(1)

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

            # Génération d'un token backup depuis la session persistante principale
            # La session token (issue de qrcode_login) supporte request_qr_code_data
            backup_credentials = None
            try:
                backup_uuid = (Uuid + "-bk") if Uuid else None
                Qrcode_backup = Account.request_qr_code_data(Pin)
                if "parent" not in QRUrl:
                    BackupAccount = pronotepy.Client.qrcode_login(
                        qr_code=Qrcode_backup, pin=Pin, uuid=backup_uuid
                    )
                else:
                    BackupAccount = pronotepy.ParentClient.qrcode_login(
                        qr_code=Qrcode_backup, pin=Pin, uuid=backup_uuid
                    )
                if BackupAccount.logged_in:
                    backup_credentials = BackupAccount.export_credentials()
                    logging.info("Token backup généré avec succès")
            except Exception as e:
                logging.warning("Génération du token backup échouée : %s", e)

            # Sauvegarde du token principal + backup
            writedataPronotepy(Account, DataDir, EqID, backup_token=backup_credentials)
except Exception as e:
    import traceback
    tb_lineno = e.__traceback__.tb_lineno if e.__traceback__ else '?'
    print(f"QRConnect.py ERREUR (ligne {tb_lineno}): {e}", flush=True)
    print(traceback.format_exc(), flush=True)
    sys.exit(1)
