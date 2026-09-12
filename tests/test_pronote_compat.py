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

    class PronoteAPIError(Exception):
        pass

    class CryptoError(PronoteAPIError):
        pass

    class Encryption:
        # Le déchiffrement échoue toujours : c'est le comportement observé sur
        # les instances PRONOTE >= 2026.2.5 pour le challenge.
        def aes_decrypt(self, data):
            raise CryptoError("Decryption failed while trying to un pad.")

    journal = {"appels": 0, "vu_pendant_login": None, "posts": []}

    class ClientBase:
        def post(self, function_name, onglet=None, data=None):
            journal["posts"].append((function_name, onglet))
            return {"ok": True}

        def _login(self):
            journal["appels"] += 1
            # Capture la méthode active pendant le login.
            journal["vu_pendant_login"] = Encryption.aes_decrypt
            return True

    clients = types.ModuleType("pronotepy.clients")
    clients.ClientBase = ClientBase
    exceptions = types.ModuleType("pronotepy.exceptions")
    exceptions.CryptoError = CryptoError
    exceptions.PronoteAPIError = PronoteAPIError
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
    original_post = ClientBase.post
    original_decrypt = Encryption.aes_decrypt
    yield types.SimpleNamespace(
        module=pronote_compat,
        Encryption=Encryption,
        ClientBase=ClientBase,
        CryptoError=CryptoError,
        PronoteAPIError=PronoteAPIError,
        journal=journal,
    )
    ClientBase._login = original_login
    ClientBase.post = original_post
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


class TestOngletsNonAccessibles:
    """Une requête vers un onglet interdit ne doit pas coûter de connexion.

    pronotepy la rejette avant tout appel réseau, mais traite ensuite l'erreur
    comme n'importe quelle autre : il se ré-authentifie puis rejoue la requête,
    qui échoue forcément — une nouvelle session ne donne aucun droit de plus.
    Or chaque authentification fait tourner le jeton, et leur accumulation a
    valu une suspension d'adresse IP par Pronote.
    """

    def _client(self, faux_pronotepy, onglets):
        client = faux_pronotepy.ClientBase()
        client.communication = types.SimpleNamespace(authorized_onglets=onglets)
        return client

    def test_onglet_interdit_leve_sans_appel(self, faux_pronotepy):
        faux_pronotepy.module.apply()
        client = self._client(faux_pronotepy, [7, 198])
        faux_pronotepy.journal["posts"].clear()

        with pytest.raises(faux_pronotepy.PronoteAPIError):
            client.post("PagePresence", 19, {})

        assert faux_pronotepy.journal["posts"] == []

    def test_onglet_autorise_passe(self, faux_pronotepy):
        faux_pronotepy.module.apply()
        client = self._client(faux_pronotepy, [7, 198])
        faux_pronotepy.journal["posts"].clear()

        assert client.post("DernieresNotes", 198, {}) == {"ok": True}
        assert faux_pronotepy.journal["posts"] == [("DernieresNotes", 198)]

    def test_requete_sans_onglet_passe(self, faux_pronotepy):
        faux_pronotepy.module.apply()
        client = self._client(faux_pronotepy, [7])
        faux_pronotepy.journal["posts"].clear()

        assert client.post("ParametresUtilisateur") == {"ok": True}
        assert faux_pronotepy.journal["posts"] == [("ParametresUtilisateur", None)]

    def test_liste_vide_ne_filtre_rien(self, faux_pronotepy):
        """Avant le login, la liste est vide : ne rien bloquer."""
        faux_pronotepy.module.apply()
        client = self._client(faux_pronotepy, [])
        faux_pronotepy.journal["posts"].clear()

        assert client.post("FonctionParametres", 7, {}) == {"ok": True}
