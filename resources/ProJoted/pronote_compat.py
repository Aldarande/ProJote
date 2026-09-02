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

Le JS officiel du client PRONOTE 2026 confirme le nouveau comportement : sa
méthode ``getNouveauChallenge()`` chiffre directement la chaîne reçue, sans
aucune étape de déchiffrement ni de retrait d'aléa. Ce n'est donc pas un
contournement mais bien le protocole en vigueur.

Plutôt que de dupliquer les 110 lignes de ``ClientBase._login``, on intercepte
``_Encryption.aes_decrypt`` **pendant la seule durée du login**. Pour le
challenge, on renvoie sa chaîne hexadécimale avec chaque caractère doublé :
``_enleverAlea()`` — qui ne garde qu'un caractère sur deux — restitue alors
exactement le challenge, que pronotepy rechiffre et renvoie. Le résultat est
celui du correctif de l'issue #346, sans réécrire la méthode.

Le patch est délibérément limité :

    - actif uniquement pendant ``_login`` (restauré dans un ``finally``), pour
      ne pas masquer un code PIN erroné : le champ « login » d'un QR Code fait
      lui aussi un seul bloc, et un PIN faux doit continuer à lever
      QRCodeDecryptError ;
    - réservé à l'instance ``_Encryption`` locale à ``_login`` — celle qui
      traite le challenge — et non à celle de la communication, qui déchiffre
      les réponses du serveur et la clé de session dans ``after_auth`` ;
    - déclenché sur un challenge d'un seul bloc AES, signature du protocole
      2026 : les serveurs antérieurs renvoient une chaîne entrelacée d'aléa,
      toujours plus longue. Trancher sur la taille plutôt que sur l'échec du
      déchiffrement évite un piège : avec une mauvaise clé, le dépadding
      réussit par hasard environ une fois sur 256, et l'ancien chemin
      produirait alors une réponse fausse — soit, au rythme du démon, un échec
      inexpliqué tous les deux jours environ.

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

    def _challenge_brut(data: bytes) -> bytes:
        """Rend le challenge tel quel, sous une forme que pronotepy restituera.

        pronotepy applique `_enleverAlea()` (un caractère sur deux) au résultat
        du déchiffrement ; on double donc chaque caractère pour qu'il retrouve
        la chaîne d'origine, qu'il rechiffrera et renverra au serveur.
        """
        return "".join(c * 2 for c in data.hex().upper()).encode()

    def _login_avec_repli(self) -> bool:
        # Le challenge est déchiffré dans _login par une instance _Encryption
        # locale, distincte de celle de la communication (qui sert, elle, aux
        # réponses du serveur et à la clé de session dans after_auth). Cette
        # distinction permet de ne détourner QUE le challenge.
        communication = getattr(self, "communication", None)
        chiffrement_session = getattr(communication, "encryption", None)

        def _decrypt(enc_self, data: bytes) -> bytes:
            challenge = (
                chiffrement_session is not None
                and enc_self is not chiffrement_session
                and len(data) == 16
            )
            if challenge:
                # Un challenge d'un seul bloc AES est la signature du protocole
                # PRONOTE >= 2026.2.5 : le client officiel ne le déchiffre plus
                # du tout (getNouveauChallenge() chiffre la chaîne brute). On
                # tranche donc sur la taille plutôt que sur l'échec du
                # déchiffrement : avec une mauvaise clé, le dépadding réussit
                # par hasard une fois sur 256 environ, et pronotepy repartirait
                # alors sur l'ancien chemin pour produire une réponse fausse.
                # Sur les serveurs antérieurs, le challenge contient une chaîne
                # entrelacée d'aléa : il fait toujours plus d'un bloc.
                logging.info(
                    "pronote_compat :: challenge d'un seul bloc : mode PRONOTE "
                    ">= 2026.2.5 (chiffrement direct de la chaîne brute)."
                )
                return _challenge_brut(data)
            try:
                return _original_decrypt(enc_self, data)
            except CryptoError:
                if len(data) != 16:
                    raise
                # Filet de sécurité si la structure interne de pronotepy change
                # et que le challenge n'est plus reconnaissable ci-dessus.
                logging.info(
                    "pronote_compat :: repli sur le mode PRONOTE >= 2026.2.5 "
                    "après échec du déchiffrement d'un bloc unique."
                )
                return _challenge_brut(data)

        _Encryption.aes_decrypt = _decrypt
        try:
            return _original_login(self)
        finally:
            _Encryption.aes_decrypt = _original_decrypt

    clients.ClientBase._login = _login_avec_repli
