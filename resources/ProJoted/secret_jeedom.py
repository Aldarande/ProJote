# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""secret_jeedom.py — Déchiffrement des secrets transmis par Jeedom.

Le mot de passe Pronote est chiffré côté PHP par ``ProJote.class.php`` :

    openssl_encrypt($data, 'aes-256-cbc', hex2bin(sha256(apikey)), 0, $iv)

soit AES-256-CBC avec le remplissage PKCS#7 d'OpenSSL, transporté sous la forme
``base64(JSON({iv: base64, data: base64}))``.

Ce module existe pour une raison précise. Le démon et le script de validation
par identifiants portaient chacun leur propre copie du déchiffrement, et toutes
deux retiraient le remplissage ainsi :

    unpad = lambda s: s[: -s[-1]]

Sans vérification. Quand la clé est fausse — ce qui arrive dès que la clé API de
Jeedom est régénérée — le déchiffrement produit seize octets aléatoires. Le
dernier octet vaut alors n'importe quoi entre 0 et 255 ; s'il dépasse la taille
d'un bloc, cette expression **renvoie une chaîne vide**. Le mot de passe partait
donc vide vers Pronote, sans la moindre exception : ni le repli du démon ni
celui de la validation ne se déclenchaient jamais, et l'utilisateur ne lisait
qu'un « identifiants refusés » trompeur. Relevé le 17 septembre 2026 sur le
compte de démonstration, en rejouant une clé API différente.

Le remplissage est désormais vérifié, et le déchiffrement vit à un seul endroit :
une vérification de sécurité dupliquée est une vérification qui finit par diverger.
"""

import base64
import binascii
import hashlib
import json

from Crypto.Cipher import AES

from pronote_errors import DechiffrementImpossible

TAILLE_BLOC = 16


def cle_depuis_apikey(apikey):
    """Clé de chiffrement dérivée de la clé API Jeedom, en hexadécimal.

    SHA-256 de la clé API : 64 caractères hexadécimaux, soit les 32 octets
    attendus par AES-256. Même dérivation que ``ProJote::_getEncryptionKey()``
    côté PHP — les deux doivent rester identiques.

    La dérivation a été auditée (SECURITY-AUDIT.md, M3) : la clé API est un
    secret aléatoire à forte entropie généré par le core Jeedom, pas une valeur
    devinable. SHA-256 suffit ; PBKDF2 n'étirerait qu'un secret faible.
    """
    return hashlib.sha256(apikey.encode()).hexdigest()


def retirer_padding(octets):
    """Retire le remplissage PKCS#7 après l'avoir vérifié.

    Args:
        octets: le texte clair encore rempli, tel que rendu par AES-CBC.

    Returns:
        bytes: le texte clair sans son remplissage.

    Raises:
        DechiffrementImpossible: le remplissage est invalide — signe, en
            pratique, que la clé n'est pas la bonne.
    """
    if not octets or len(octets) % TAILLE_BLOC:
        raise DechiffrementImpossible(
            "longueur déchiffrée invalide : %d octet(s)" % len(octets)
        )
    n = octets[-1]
    if n < 1 or n > TAILLE_BLOC or octets[-n:] != bytes([n]) * n:
        raise DechiffrementImpossible(
            "remplissage PKCS#7 invalide — la clé de chiffrement ne correspond pas"
        )
    return octets[:-n]


def dechiffrer(data, passphrase):
    """Déchiffre un secret produit par ``ProJote::my_encrypt()``.

    Args:
        data: la charge ``base64(JSON({iv, data}))`` reçue de Jeedom.
        passphrase: la clé en hexadécimal (cf. :func:`cle_depuis_apikey`).

    Returns:
        str: le secret en clair.

    Raises:
        DechiffrementImpossible: charge illisible, clé incorrecte ou
            remplissage invalide. L'appelant nomme l'échec pour cet
            équipement ; aucun autre n'est affecté.
    """
    try:
        cle = binascii.unhexlify(passphrase)
        enveloppe = json.loads(base64.b64decode(data).decode("ascii"))
        iv = base64.b64decode(enveloppe["iv"])
        chiffre = base64.b64decode(enveloppe["data"])
    except Exception as e:
        raise DechiffrementImpossible("charge illisible : %s" % e) from e

    try:
        clair = AES.new(cle, AES.MODE_CBC, iv).decrypt(chiffre)
    except Exception as e:
        raise DechiffrementImpossible("déchiffrement AES refusé : %s" % e) from e

    # Le rstrip() est conservé du code d'origine : il ne coûte rien sur un
    # secret correct, et le retirer changerait le mot de passe d'un compte dont
    # le secret se terminerait par une espace. Ce n'est pas le sujet ici.
    try:
        return retirer_padding(clair).decode("ascii").rstrip()
    except UnicodeDecodeError as e:
        raise DechiffrementImpossible("secret non ASCII après déchiffrement") from e
