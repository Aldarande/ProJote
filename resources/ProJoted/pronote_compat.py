# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""
pronote_compat.py — Correctifs de compatibilité appliqués à pronotepy.

# Challenge d'authentification non chiffré (PRONOTE >= 2026.2.5)

Depuis le 2 septembre 2026, certaines instances PRONOTE ne chiffrent plus le
« challenge » renvoyé à l'Identification. pronotepy 2.15.6, lui, applique
toujours le cycle historique :

    déchiffrer le challenge → retirer l'alea (un caractère sur deux) → rechiffrer

Sur ces serveurs, la première étape échoue et pronotepy lève
``CryptoError("Decryption failed while trying to un pad")``, quel que soit le
mode de connexion (QR Code, identifiants ou jeton). Signature du symptôme,
identique à celle relevée sur notre instance :

    - réponse Identification sans champ « alea » ;
    - challenge d'un seul bloc AES (16 octets) ;
    - déchiffrement du contenu du QR Code réussi juste avant.

Le serveur attend en réalité le chiffrement direct de la chaîne brute. Voir
https://github.com/bain3/pronotepy/issues/346 (cause et correctif) et
https://github.com/bain3/pronotepy/issues/348 (même instance que la nôtre,
PRONOTE 2026.2.5.7).

Plutôt que de dupliquer les 110 lignes de ``ClientBase._login``, on intercepte
``_Encryption.aes_decrypt`` **pendant la seule durée du login**. Quand le
déchiffrement d'un bloc unique échoue, on renvoie la chaîne hexadécimale du
challenge avec chaque caractère doublé : ``_enleverAlea()`` — qui ne garde qu'un
caractère sur deux — restitue alors exactement le challenge d'origine, que
pronotepy rechiffre et renvoie. Le résultat est celui du correctif de l'issue
#346, sans réécrire la méthode.

Le patch est délibérément limité :

    - actif uniquement pendant ``_login`` (restauré dans un ``finally``), pour
      ne pas masquer un code PIN erroné : le champ « login » d'un QR Code fait
      lui aussi un seul bloc, et un PIN faux doit continuer à lever
      QRCodeDecryptError ;
    - déclenché uniquement sur un bloc unique de 16 octets ;
    - sans effet sur les serveurs conformes, où le déchiffrement réussit et le
      chemin d'origine s'applique.

À retirer quand pronotepy publiera son propre correctif (le plancher de version
de requirements.txt devra alors être relevé).
"""

import logging

_applied = False


def apply() -> None:
    """Installe les correctifs. Idempotent : les appels suivants sont ignorés.

    Ne lève jamais : ce correctif s'appuie sur des détails internes de
    pronotepy (``ClientBase._login``, ``_Encryption.aes_decrypt``). Si une
    version future les déplace, on veut une connexion qui échoue avec le
    message d'origine — pas un démon qui refuse de démarrer.
    """
    global _applied
    if _applied:
        return

    try:
        _install()
    except Exception as e:
        logging.warning(
            "pronote_compat :: correctif « challenge non chiffré » non installé "
            "(%s: %s). La connexion échouera sur les serveurs PRONOTE >= 2026.2.5.",
            type(e).__name__,
            e,
        )
        return

    _applied = True
    logging.debug(
        "pronote_compat :: correctif « challenge non chiffré » installé "
        "(pronotepy issues #346 / #348)."
    )


def _install() -> None:
    """Pose effectivement le correctif sur les classes de pronotepy."""
    from pronotepy import clients
    from pronotepy.exceptions import CryptoError
    from pronotepy.pronoteAPI import _Encryption

    _original_decrypt = _Encryption.aes_decrypt
    _original_login = clients.ClientBase._login

    def _decrypt_avec_repli(self, data: bytes) -> bytes:
        try:
            return _original_decrypt(self, data)
        except CryptoError:
            if len(data) != 16:
                # Autre chose que le challenge : on laisse remonter l'erreur.
                raise
            logging.info(
                "pronote_compat :: challenge non chiffré détecté (bloc unique de "
                "16 octets) : application du mode PRONOTE >= 2026.2.5."
            )
            # Chaque caractère doublé pour survivre au filtrage un-sur-deux
            # de _enleverAlea() et restituer le challenge intact.
            return "".join(c * 2 for c in data.hex().upper()).encode()

    def _login_avec_repli(self) -> bool:
        _Encryption.aes_decrypt = _decrypt_avec_repli
        try:
            return _original_login(self)
        finally:
            _Encryption.aes_decrypt = _original_decrypt

    clients.ClientBase._login = _login_avec_repli
