"""Tests du correctif de compatibilité `pronote_compat.py`.

Contexte : depuis le 2 septembre 2026, PRONOTE >= 2026.2.5 ne chiffre plus le
challenge d'authentification. pronotepy 2.15.6 tente quand même de le
déchiffrer et échoue (`CryptoError`), ce qui casse tous les modes de connexion
(QR Code, identifiants, jeton). Voir pronotepy issues #346 et #348.

Le correctif intercepte `_Encryption.aes_decrypt` pendant le seul `_login` et,
sur un bloc unique de 16 octets indéchiffrable, renvoie le challenge avec
chaque caractère doublé pour que le filtrage un-sur-deux de `_enleverAlea()`
le restitue intact.

Ces tests fabriquent leurs propres modules pronotepy : ils ne dépendent ni du
réseau, ni de pronotepy, ni de pycryptodome.
"""

import sys
import types

import pytest


def _enlever_alea(texte):
    """Réplique de `pronotepy.pronoteAPI._enleverAlea` (un caractère sur deux)."""
    return "".join(c for i, c in enumerate(texte) if i % 2 == 0)


@pytest.fixture
def faux_pronotepy(monkeypatch):
    """Installe un pronotepy minimal et retourne le module pronote_compat prêt.

    Retourne un objet portant : Encryption (classe patchée pendant le login),
    ClientBase, CryptoError, et `journal` des appels au `_login` d'origine.
    """

    class CryptoError(Exception):
        pass

    class Encryption:
        # Le déchiffrement échoue toujours : c'est le comportement observé sur
        # les instances PRONOTE >= 2026.2.5 pour le challenge.
        def aes_decrypt(self, data):
            raise CryptoError("Decryption failed while trying to un pad.")

    journal = {"appels": 0, "vu_pendant_login": None}

    class ClientBase:
        def _login(self):
            journal["appels"] += 1
            # Capture la méthode active pendant le login.
            journal["vu_pendant_login"] = Encryption.aes_decrypt
            return True

    clients = types.ModuleType("pronotepy.clients")
    clients.ClientBase = ClientBase
    exceptions = types.ModuleType("pronotepy.exceptions")
    exceptions.CryptoError = CryptoError
    api = types.ModuleType("pronotepy.pronoteAPI")
    api._Encryption = Encryption

    paquet = types.ModuleType("pronotepy")
    paquet.clients = clients
    paquet.exceptions = exceptions
    paquet.pronoteAPI = api

    monkeypatch.setitem(sys.modules, "pronotepy", paquet)
    monkeypatch.setitem(sys.modules, "pronotepy.clients", clients)
    monkeypatch.setitem(sys.modules, "pronotepy.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "pronotepy.pronoteAPI", api)

    import pronote_compat

    # Le correctif est idempotent via un drapeau global : on le réarme pour
    # chaque test, et on restaure l'état d'origine ensuite.
    monkeypatch.setattr(pronote_compat, "_applied", False, raising=False)
    original_login = ClientBase._login
    original_decrypt = Encryption.aes_decrypt
    yield types.SimpleNamespace(
        module=pronote_compat,
        Encryption=Encryption,
        ClientBase=ClientBase,
        CryptoError=CryptoError,
        journal=journal,
    )
    ClientBase._login = original_login
    Encryption.aes_decrypt = original_decrypt


class TestChallengeNonChiffre:
    def test_le_challenge_est_restitue_intact(self, faux_pronotepy):
        """Le repli doit rendre le challenge exact après _enleverAlea()."""
        faux_pronotepy.module.apply()
        challenge = "EF4C6F47929D96D7A778BF9EE2E3A48F"  # 16 octets, cas réel

        capture = {}

        def _login(self):
            enc = faux_pronotepy.Encryption()
            dec = enc.aes_decrypt(bytes.fromhex(challenge))
            capture["restitue"] = _enlever_alea(dec.decode())
            return True

        faux_pronotepy.ClientBase._login = _login
        faux_pronotepy.module._applied = False
        faux_pronotepy.module.apply()
        faux_pronotepy.ClientBase._login(object())

        assert capture["restitue"] == challenge

    def test_un_bloc_non_16_octets_remonte_l_erreur(self, faux_pronotepy):
        """Hors challenge, une erreur de déchiffrement doit rester une erreur."""
        faux_pronotepy.module.apply()

        resultat = {}

        def _login(self):
            enc = faux_pronotepy.Encryption()
            try:
                enc.aes_decrypt(b"x" * 112)  # taille d'un jeton de QR Code
            except faux_pronotepy.CryptoError:
                resultat["leve"] = True
            return True

        faux_pronotepy.ClientBase._login = _login
        faux_pronotepy.module._applied = False
        faux_pronotepy.module.apply()
        faux_pronotepy.ClientBase._login(object())

        assert resultat.get("leve") is True


class TestPorteeDuCorrectif:
    def test_actif_pendant_le_login_seulement(self, faux_pronotepy):
        """Hors login, aes_decrypt doit être la méthode d'origine.

        Sans cette restriction, un code PIN erroné ne lèverait plus
        QRCodeDecryptError : le champ « login » d'un QR Code fait lui aussi
        un seul bloc de 16 octets.
        """
        origine = faux_pronotepy.Encryption.aes_decrypt
        faux_pronotepy.module.apply()

        assert faux_pronotepy.Encryption.aes_decrypt is origine

        faux_pronotepy.ClientBase._login(object())

        assert faux_pronotepy.journal["vu_pendant_login"] is not origine
        assert faux_pronotepy.Encryption.aes_decrypt is origine

    def test_restaure_meme_si_le_login_echoue(self, faux_pronotepy):
        origine = faux_pronotepy.Encryption.aes_decrypt

        def _login_qui_plante(self):
            raise RuntimeError("boum")

        faux_pronotepy.ClientBase._login = _login_qui_plante
        faux_pronotepy.module._applied = False
        faux_pronotepy.module.apply()

        with pytest.raises(RuntimeError):
            faux_pronotepy.ClientBase._login(object())

        assert faux_pronotepy.Encryption.aes_decrypt is origine

    def test_idempotent(self, faux_pronotepy):
        faux_pronotepy.module.apply()
        premier = faux_pronotepy.ClientBase._login
        faux_pronotepy.module.apply()

        assert faux_pronotepy.ClientBase._login is premier
