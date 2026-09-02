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

Codes de sortie (interprétés par ProJote.ajax.php pour afficher un message clair) :
  0 : connexion réussie, token sauvegardé
  1 : erreur générique (voir les logs)
  3 : déchiffrement impossible → code PIN erroné
  4 : contenu du QR Code invalide (mal décodé, champs manquants, PIN mal formé)
  5 : Pronote a refusé le jeton → QR Code expiré (10 min) ou déjà utilisé
"""
try:
    import pronotepy
    import sys
    import json
    import argparse
    import logging
    import os
    import re

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

        # Validation du contenu du QR Code AVANT d'appeler pronotepy.
        # « jeton » et « login » sont chiffrés puis encodés en hexadécimal par
        # Pronote : si l'image a été mal décodée côté navigateur, on obtient ici
        # des caractères non hexadécimaux et pronotepy plante sur un
        # « non-hexadecimal number found in fromhex() » peu parlant.
        if not re.fullmatch(r"[0-9a-fA-F]+", Jeton) or not re.fullmatch(
            r"[0-9a-fA-F]+", QRLogin
        ):
            logging.error(
                "QRConnect.py :: Contenu du QR Code illisible : jeton/login ne sont pas "
                "hexadécimaux (longueurs jeton=%d login=%d). Le QR Code a probablement "
                "été mal décodé.",
                len(Jeton),
                len(QRLogin),
            )
            sys.exit(4)
        if not re.fullmatch(r"[0-9]{4}", Pin):
            logging.error(
                "QRConnect.py :: Code PIN invalide : 4 chiffres attendus (reçu %d caractère(s))",
                len(Pin),
            )
            sys.exit(4)

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

        if not Account.logged_in:
            # Sans ce garde-fou, le script sortait en code 0 sans rien sauvegarder :
            # le PHP annonçait alors une connexion réussie alors qu'aucun token
            # n'avait été écrit.
            logging.error(
                "QRConnect.py :: Pronote a refusé la connexion (aucune session ouverte). "
                "Le QR Code a probablement déjà été utilisé ou a expiré."
            )
            sys.exit(5)

        logging.info("Client connecté")

        # Génération d'un token backup pour permettre une reconnexion automatique
        # même si le jeton principal est invalidé plus tard.
        #
        # Attention : ici la session provient déjà d'un qrcode_login (session
        # « token », sans mot de passe). Certaines instances Pronote ne renvoient
        # alors pas un QR code complet — la clé "login" est absente — ce qui faisait
        # planter qrcode_login avec « KeyError: 'login' ». On valide donc la structure
        # avant de tenter le login backup, et on échoue proprement sans bloquer la
        # connexion principale (déjà sauvegardée juste après).
        backup_credentials = None
        try:
            backup_uuid = (Uuid + "-bk") if Uuid else None
            Qrcode_backup = Account.request_qr_code_data(Pin)

            missing = [
                k for k in ("jeton", "login", "url")
                if not (isinstance(Qrcode_backup, dict) and Qrcode_backup.get(k))
            ]
            if missing:
                logging.warning(
                    "Token backup non généré : la session QR ne permet pas d'émettre "
                    "un second jeton (champ(s) manquant(s) : %s). La reconnexion "
                    "automatique utilisera le token principal.",
                    ", ".join(missing),
                )
            elif "parent" not in QRUrl:
                BackupAccount = pronotepy.Client.qrcode_login(
                    qr_code=Qrcode_backup, pin=Pin, uuid=backup_uuid
                )
                if BackupAccount.logged_in:
                    backup_credentials = BackupAccount.export_credentials()
                    logging.info("Token backup généré avec succès")
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
    # Codes de sortie dédiés, pour que le PHP affiche un message utile plutôt
    # qu'un « erreur lors de l'exécution du script » générique :
    #   3 → déchiffrement impossible  → code PIN erroné (cas le plus fréquent)
    #   4 → contenu du QR Code invalide (mal décodé, champs manquants)
    #   5 → Pronote refuse le jeton   → QR Code expiré ou déjà utilisé
    #   1 → autre erreur
    #
    # Attention : pronotepy lève QRCodeDecryptError("invalid confirmation code")
    # quand le déchiffrement AES échoue. Ce déchiffrement est purement local et
    # ne dépend QUE du code PIN : ce n'est donc PAS un QR Code expiré (ce dernier
    # est refusé plus tard, par le serveur Pronote). L'ancien code renvoyait 3
    # dans les deux cas et affichait « le QR code a expiré », ce qui envoyait
    # l'utilisateur régénérer un QR Code alors qu'il avait juste saisi le mauvais PIN.
    exc_name = type(e).__name__
    msg = str(e).lower()
    if (
        exc_name in ("CryptoError", "QRCodeDecryptError")
        or "invalid confirmation code" in msg
        or "padding is incorrect" in msg
        or "decryption failed" in msg
    ):
        sys.exit(3)
    if exc_name == "KeyError" or "fromhex" in msg or "non-hexadecimal" in msg:
        sys.exit(4)
    if exc_name == "ExpiredObject" or "expired" in msg or "expir" in msg:
        sys.exit(5)
    try:
        _api_error = pronotepy.PronoteAPIError
    except NameError:  # l'import de pronotepy lui-même a échoué
        _api_error = ()
    if isinstance(e, _api_error):
        # Le serveur a rejeté le jeton : QR déjà consommé, expiré, ou espace
        # mobile désactivé par l'établissement.
        sys.exit(5)
    sys.exit(1)
