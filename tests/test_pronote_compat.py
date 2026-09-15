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

    journal = {
        "appels": 0,
        "vu_pendant_login": None,
        "posts": [],
        "reseau": [],
        "onglets_autorises": [88],
    }

    class ClientBase:
        def post(self, function_name, onglet=None, data=None):
            journal["posts"].append((function_name, onglet))
            return {"ok": True}

        def _login(self):
            journal["appels"] += 1
            # Capture la méthode active pendant le login.
            journal["vu_pendant_login"] = Encryption.aes_decrypt
            return True

    # Les identifiants de ressource PRONOTE changent à chaque session : le faux
    # serveur en émet donc de nouveaux à chaque réinitialisation, comme le vrai.
    journal["sessions"] = 0

    class Communication:
        """Faux serveur : refuse un onglet non accordé, et refuse aussi tout
        membre issu d'une session périmée — comme PRONOTE (« La page a expiré »).
        """

        authorized_onglets = journal["onglets_autorises"]

        def post(self, function_name, post_data):
            journal["reseau"].append((function_name, post_data))
            signature = post_data.get("Signature")
            if signature:
                if signature["onglet"] not in journal["onglets_autorises"]:
                    raise PronoteAPIError("onglet refusé")
                if not signature["membre"]["N"].endswith(f"-s{journal['sessions']}"):
                    raise PronoteAPIError("La page a expiré")
            return {"ok": True}

    class ClientInfo:
        def __init__(self, client, json_):
            self.raw_resource = json_
            self.id = json_["N"]

        @property
        def name(self):
            return self.raw_resource["L"]

    class Client(ClientBase):
        def refresh(self):
            """Réplique du refresh d'origine : nouvelle session, ressource du
            parent restaurée, ni children ni _selected_child reconstruits."""
            self._nouvelle_session()

        def _nouvelle_session(self):
            journal["sessions"] += 1
            s = journal["sessions"]
            self.parametres_utilisateur = {
                "dataSec": {
                    "data": {
                        "ressource": {
                            "N": f"46#parent-s{s}",
                            "L": "PARENT",
                            "listeRessources": [
                                {"N": f"46#enfant-a-s{s}", "L": "ENFANT Un"},
                                {"N": f"46#enfant-b-s{s}", "L": "ENFANT Deux"},
                            ],
                        }
                    }
                }
            }

    class ParentClient(Client):
        # Réplique du ParentClient d'origine : post() ne délègue pas à
        # ClientBase.post, il redescend directement vers la communication.
        def post(self, function_name, onglet=None, data=None):
            post_data = {}
            if onglet:
                post_data["Signature"] = {
                    "onglet": onglet,
                    "membre": {"N": self._selected_child.id, "G": 4},
                }
            if data:
                post_data["data"] = data
            journal["posts"].append((function_name, onglet))
            return self.communication.post(function_name, post_data)

        def __init__(self):
            # Le vrai ParentClient ne passe pas par refresh() à la construction :
            # il ouvre sa session puis sélectionne le premier enfant.
            self.communication = Communication()
            self._nouvelle_session()
            self.children = [
                ClientInfo(self, c)
                for c in self.parametres_utilisateur["dataSec"]["data"]["ressource"][
                    "listeRessources"
                ]
            ]
            self.set_child(self.children[0])

        def set_child(self, child):
            if not isinstance(child, ClientInfo):
                trouve = [c for c in self.children if c.name == child]
                if not trouve:
                    raise ValueError(f"enfant introuvable : {child}")
                child = trouve[0]
            self._selected_child = child
            self.parametres_utilisateur["dataSec"]["data"]["ressource"] = (
                child.raw_resource
            )

    clients = types.ModuleType("pronotepy.clients")
    clients.ClientBase = ClientBase
    clients.Client = Client
    clients.ParentClient = ParentClient
    data_classes = types.ModuleType("pronotepy.dataClasses")
    data_classes.ClientInfo = ClientInfo
    exceptions = types.ModuleType("pronotepy.exceptions")
    exceptions.CryptoError = CryptoError
    exceptions.PronoteAPIError = PronoteAPIError
    api = types.ModuleType("pronotepy.pronoteAPI")
    api._Encryption = Encryption

    paquet = types.ModuleType("pronotepy")
    paquet.clients = clients
    paquet.exceptions = exceptions
    paquet.pronoteAPI = api
    paquet.dataClasses = data_classes

    monkeypatch.setitem(sys.modules, "pronotepy", paquet)
    monkeypatch.setitem(sys.modules, "pronotepy.clients", clients)
    monkeypatch.setitem(sys.modules, "pronotepy.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "pronotepy.pronoteAPI", api)
    monkeypatch.setitem(sys.modules, "pronotepy.dataClasses", data_classes)

    import pronote_compat

    # Le correctif est idempotent via un drapeau global : on le réarme pour
    # chaque test, et on restaure l'état d'origine ensuite.
    monkeypatch.setattr(pronote_compat, "_applied", False, raising=False)
    original_login = ClientBase._login
    original_post = ClientBase.post
    original_decrypt = Encryption.aes_decrypt
    original_refresh = Client.refresh
    original_post_parent = ParentClient.post
    yield types.SimpleNamespace(
        module=pronote_compat,
        Encryption=Encryption,
        ClientBase=ClientBase,
        CryptoError=CryptoError,
        PronoteAPIError=PronoteAPIError,
        Client=Client,
        ParentClient=ParentClient,
        ClientInfo=ClientInfo,
        journal=journal,
    )
    ClientBase._login = original_login
    ClientBase.post = original_post
    Encryption.aes_decrypt = original_decrypt
    Client.refresh = original_refresh
    ParentClient.post = original_post_parent


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


class TestEnfantApresReinitialisation:
    """Compte parent : `refresh()` doit conserver l'enfant sélectionné.

    Sans le correctif, la reconnexion déclenchée par « La page a expiré »
    restaure la ressource du parent et laisse `_selected_child` pointer sur
    l'objet de la session morte. Les identifiants de ressource étant propres à
    une session, toutes les requêtes suivantes portent un identifiant périmé et
    PRONOTE refuse : devoirs vides, évaluations en KeyError.
    """

    def test_sans_correctif_l_enfant_est_perdu(self, faux_pronotepy):
        """Témoin : le comportement d'origine perd bien l'enfant."""
        parent = faux_pronotepy.ParentClient()
        avant = parent._selected_child.id

        parent.refresh()  # correctif non installé

        assert parent._selected_child.id == avant, "le faux client doit figer l'id"
        ressource = parent.parametres_utilisateur["dataSec"]["data"]["ressource"]
        assert ressource["L"] == "PARENT", "la ressource redevient celle du parent"

    def test_l_enfant_est_re_selectionne(self, faux_pronotepy):
        faux_pronotepy.module.apply()
        parent = faux_pronotepy.ParentClient()
        parent.set_child("ENFANT Deux")
        id_avant = parent._selected_child.id

        parent.refresh()

        assert parent._selected_child.name == "ENFANT Deux", "même enfant"
        assert parent._selected_child.id != id_avant, "identifiant de la session neuve"
        ressource = parent.parametres_utilisateur["dataSec"]["data"]["ressource"]
        assert ressource["L"] == "ENFANT Deux"
        assert ressource["N"] == parent._selected_child.id

    def test_les_enfants_sont_reconstruits(self, faux_pronotepy):
        faux_pronotepy.module.apply()
        parent = faux_pronotepy.ParentClient()
        ids_avant = {c.id for c in parent.children}

        parent.refresh()

        ids_apres = {c.id for c in parent.children}
        assert not (ids_avant & ids_apres), "aucun identifiant de session morte"
        assert {c.name for c in parent.children} == {"ENFANT Un", "ENFANT Deux"}

    def test_un_compte_eleve_n_est_pas_touche(self, faux_pronotepy):
        """Le correctif ne doit rien changer pour un client non parent."""
        faux_pronotepy.module.apply()
        eleve = faux_pronotepy.Client()

        eleve.refresh()

        assert not hasattr(eleve, "children")
        assert not hasattr(eleve, "_selected_child")


class TestPostParent:
    """`ParentClient.post` court-circuite ClientBase.post : les garde-fous du
    plugin doivent aussi être posés sur lui.

    Sans quoi, sur un compte parent, chaque appel visant un onglet non accordé
    (la messagerie sur beaucoup d'établissements) part sur le réseau, échoue et
    déclenche une authentification complète — donc une rotation du jeton — à
    chaque cycle du démon.
    """

    def test_un_onglet_non_accorde_ne_touche_pas_le_reseau(self, faux_pronotepy):
        faux_pronotepy.module.apply()
        parent = faux_pronotepy.ParentClient()
        faux_pronotepy.journal["reseau"].clear()
        sessions_avant = faux_pronotepy.journal["sessions"]

        with pytest.raises(faux_pronotepy.PronoteAPIError):
            parent.post("ListeMessagerie", 131)

        assert faux_pronotepy.journal["reseau"] == [], "aucune requête ne doit partir"
        assert faux_pronotepy.journal["sessions"] == sessions_avant, (
            "aucune ré-authentification ne doit être déclenchée"
        )

    def test_un_onglet_accorde_passe(self, faux_pronotepy):
        faux_pronotepy.module.apply()
        parent = faux_pronotepy.ParentClient()

        assert parent.post("PageCahierDeTexte", 88) == {"ok": True}

    def test_le_rejeu_utilise_l_enfant_de_la_nouvelle_session(self, faux_pronotepy):
        """Après un refus, la requête rejouée doit porter l'identifiant frais.

        pronotepy construit sa charge utile avant le refresh et la rejoue telle
        quelle : l'identifiant d'enfant y est celui de la session morte, donc le
        rejeu ne peut qu'échouer à son tour.
        """
        faux_pronotepy.module.apply()
        parent = faux_pronotepy.ParentClient()
        # Le faux serveur refuse tout membre d'une session antérieure : on
        # périme la session courante sans prévenir le client.
        parent._nouvelle_session()
        parent.set_child(parent.children[0])  # enfant de la session périmée
        faux_pronotepy.journal["sessions"] += 1
        faux_pronotepy.journal["reseau"].clear()

        resultat = parent.post("PageCahierDeTexte", 88)

        assert resultat == {"ok": True}
        dernier = faux_pronotepy.journal["reseau"][-1][1]
        attendu = f"-s{faux_pronotepy.journal['sessions']}"
        assert dernier["Signature"]["membre"]["N"].endswith(attendu)

    def test_un_refus_pendant_le_refresh_ne_boucle_pas(self, faux_pronotepy):
        """Le rejeu ne doit pas se relancer lui-même indéfiniment.

        `refresh()` appelle `_login()`, qui poste « Identification » — donc
        cette même méthode. Si le serveur refuse aussi cette Identification, la
        réparation se rappelle elle-même sans fin. Un seul cycle a produit
        415 ré-authentifications en quelques secondes le 13 septembre 2026,
        jusqu'à ce que PRONOTE suspende l'adresse IP — suspension dont la durée
        double à chaque récidive.

        pronotepy protège son propre `ClientBase.post` par le drapeau
        `_refreshing` (« prevent refresh recursion ») ; la redéfinition parent
        l'avait laissé tomber.
        """
        faux_pronotepy.module.apply()
        parent = faux_pronotepy.ParentClient()

        # Le refresh repose « Identification » à travers post(), comme le vrai
        # _login, et le serveur la refuse — la session ne se rétablit jamais.
        def refresh_qui_repose(self):
            self._nouvelle_session()
            self.post("Identification", 88)

        type(parent).refresh = refresh_qui_repose
        journal = faux_pronotepy.journal
        journal["onglets_autorises"][:] = [88]
        journal["reseau"].clear()
        # Périme la session : tout post signé sera refusé, refresh compris.
        parent._nouvelle_session()
        parent.set_child(parent.children[0])
        journal["sessions"] += 1

        with pytest.raises(faux_pronotepy.PronoteAPIError):
            parent.post("PageCahierDeTexte", 88)

        # Sans le garde, le compteur explose (RecursionError) ; avec lui, la
        # tentative de réparation est unique.
        assert len(journal["reseau"]) <= 3, (
            "la réparation doit être tentée une seule fois, "
            f"or {len(journal['reseau'])} requêtes sont parties"
        )

    def test_le_drapeau_est_rendu_meme_si_le_refresh_leve(self, faux_pronotepy):
        """Un refresh qui échoue ne doit pas condamner les cycles suivants.

        Le drapeau est rendu dans un `finally` : laissé armé, il ferait lever
        tout refus ultérieur sans jamais retenter la réparation.
        """
        faux_pronotepy.module.apply()
        parent = faux_pronotepy.ParentClient()

        def refresh_qui_leve(self):
            raise RuntimeError("réseau coupé")

        type(parent).refresh = refresh_qui_leve
        faux_pronotepy.journal["sessions"] += 1  # périme la session

        with pytest.raises(RuntimeError):
            parent.post("PageCahierDeTexte", 88)

        assert getattr(parent, "_refreshing", False) is False
