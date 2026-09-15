"""Tests de la gestion des suspensions d'adresse IP par Pronote.

Deux volets :
  * `pronote_errors` — reconnaissance des exceptions pronotepy correspondant à
    une suspension d'IP (module pur, sans dépendance) ;
  * la fenêtre de pause globale du démon (`ProJoted.py`) — ouverture,
    escalade de la durée, persistance sur disque, fermeture.
"""

import json
import os
import time
import types

import pronote_errors
import pytest


# ── Détection des erreurs ────────────────────────────────────────────────────
class _FakePronoteError(Exception):
    """Reproduit la forme d'un pronotepy.PronoteAPIError."""

    def __init__(self, message, code=None, pronote_msg=None):
        super().__init__(message)
        self.pronote_error_code = code
        self.pronote_error_msg = pronote_msg


class TestIsIpSuspensionError:
    def test_message_anglais_pronotepy(self):
        exc = _FakePronoteError("Your IP address is suspended.")
        assert pronote_errors.is_ip_suspension_error(exc)

    def test_message_francais(self):
        exc = Exception("Votre adresse IP est provisoirement suspendue")
        assert pronote_errors.is_ip_suspension_error(exc)

    def test_code_erreur_25(self):
        exc = _FakePronoteError("Unknown error", code=25)
        assert pronote_errors.is_ip_suspension_error(exc)

    def test_libelle_max_authorization(self):
        exc = _FakePronoteError(
            "[ERROR 25] Exceeded max authorization requests. Please wait before retrying..."
        )
        assert pronote_errors.is_ip_suspension_error(exc)

    def test_detail_dans_pronote_error_msg(self):
        exc = _FakePronoteError(
            "Unknown error from pronote: 42",
            pronote_msg="Suspension temporaire de l'accès",
        )
        assert pronote_errors.is_ip_suspension_error(exc)

    def test_erreur_sans_rapport(self):
        assert not pronote_errors.is_ip_suspension_error(Exception("Invalid password"))

    def test_token_expire_non_confondu(self):
        exc = _FakePronoteError("The object was from a previous session.", code=22)
        assert not pronote_errors.is_ip_suspension_error(exc)

    def test_none(self):
        assert not pronote_errors.is_ip_suspension_error(None)

    def test_insensible_a_la_casse(self):
        assert pronote_errors.is_ip_suspension_error(
            Exception("YOUR IP ADDRESS IS SUSPENDED.")
        )


class TestIpSuspensionReason:
    def test_sans_exception(self):
        assert (
            pronote_errors.ip_suspension_reason()
            == pronote_errors.IP_SUSPENSION_MESSAGE
        )

    def test_avec_detail(self):
        reason = pronote_errors.ip_suspension_reason(
            Exception("Your IP address is suspended.")
        )
        assert pronote_errors.IP_SUSPENSION_MESSAGE in reason
        assert "Your IP address is suspended." in reason


# ── Fenêtre de pause du démon ────────────────────────────────────────────────
@pytest.fixture
def suspension(daemon, tmp_path):
    """Isole l'état de suspension et le persiste dans un dossier temporaire."""
    original_dir = daemon._data_dir
    daemon._data_dir = str(tmp_path)
    daemon._ip_suspension.update({"until": 0.0, "level": 0, "last": 0.0})
    yield daemon
    daemon._data_dir = original_dir
    daemon._ip_suspension.update({"until": 0.0, "level": 0, "last": 0.0})


class TestFenetreDePause:
    def test_aucune_suspension_au_depart(self, suspension):
        assert suspension.ip_suspension_remaining() == 0

    def test_ouverture_duree_de_base(self, suspension):
        delay = suspension.trigger_ip_suspension()
        assert delay == pytest.approx(suspension._IP_SUSPENSION_BASE_DELAY, abs=2)
        assert suspension.ip_suspension_remaining() > 0

    def test_seconde_detection_pendant_la_fenetre_ne_prolonge_pas(self, suspension):
        suspension.trigger_ip_suspension()
        until = suspension._ip_suspension["until"]
        # Un second équipement tombe sur la même suspension : même échéance.
        suspension.trigger_ip_suspension()
        assert suspension._ip_suspension["until"] == until
        assert suspension._ip_suspension["level"] == 1

    def test_escalade_apres_une_nouvelle_suspension(self, suspension):
        suspension.trigger_ip_suspension()
        # Fenêtre écoulée, mais incident récent : la durée double.
        suspension._ip_suspension["until"] = 0.0
        delay = suspension.trigger_ip_suspension()
        assert suspension._ip_suspension["level"] == 2
        assert delay == pytest.approx(2 * suspension._IP_SUSPENSION_BASE_DELAY, abs=2)

    def test_duree_plafonnee(self, suspension):
        suspension._ip_suspension.update({"level": 20, "last": time.time()})
        delay = suspension.trigger_ip_suspension()
        assert delay == pytest.approx(suspension._IP_SUSPENSION_MAX_DELAY, abs=2)

    def test_retour_au_niveau_de_base_apres_24h(self, suspension):
        suspension._ip_suspension.update(
            {
                "level": 4,
                "last": time.time() - suspension._IP_SUSPENSION_LEVEL_RESET - 60,
            }
        )
        delay = suspension.trigger_ip_suspension()
        assert suspension._ip_suspension["level"] == 1
        assert delay == pytest.approx(suspension._IP_SUSPENSION_BASE_DELAY, abs=2)

    def test_fermeture_apres_reconnexion(self, suspension):
        suspension.trigger_ip_suspension()
        assert suspension.clear_ip_suspension() is True
        assert suspension.ip_suspension_remaining() == 0
        # Déjà fermée : rien à faire.
        assert suspension.clear_ip_suspension() is False

    def test_notification_sans_eqlogic_ne_leve_pas(self, suspension):
        # jeedom_com n'est pas initialisé hors démon : la notification doit rester
        # silencieuse plutôt que de casser le traitement.
        suspension.notify_ip_suspension("", time.time() + 60, 60, 1)
        suspension.notify_ip_suspension("42", time.time() + 60, 60, 1)


class TestPersistance:
    def test_ecriture_sur_disque(self, suspension, tmp_path):
        suspension.trigger_ip_suspension()
        path = tmp_path / "ip_suspension.json"
        assert path.exists()
        saved = json.loads(path.read_text())
        assert saved["until"] > time.time()
        assert saved["level"] == 1

    def test_rechargement_au_demarrage(self, suspension, tmp_path):
        until = time.time() + 900
        (tmp_path / "ip_suspension.json").write_text(
            json.dumps({"until": until, "level": 2, "last": time.time()})
        )
        suspension.load_ip_suspension()
        assert suspension._ip_suspension["level"] == 2
        assert suspension.ip_suspension_remaining() == pytest.approx(900, abs=5)

    def test_fenetre_expiree_rechargee_sans_effet(self, suspension, tmp_path):
        (tmp_path / "ip_suspension.json").write_text(
            json.dumps(
                {"until": time.time() - 10, "level": 1, "last": time.time() - 3600}
            )
        )
        suspension.load_ip_suspension()
        assert suspension.ip_suspension_remaining() == 0

    def test_absence_de_fichier_silencieuse(self, suspension, tmp_path):
        assert not os.path.exists(str(tmp_path / "ip_suspension.json"))
        suspension.load_ip_suspension()
        assert suspension.ip_suspension_remaining() == 0

    def test_fichier_corrompu_non_bloquant(self, suspension, tmp_path):
        (tmp_path / "ip_suspension.json").write_text("{ceci n'est pas du json")
        suspension.load_ip_suspension()
        assert suspension.ip_suspension_remaining() == 0


# ── Câblage dans process_message ─────────────────────────────────────────────
class _Recorder:
    """Remplace jeedom_com : mémorise les payloads envoyés à Jeedom."""

    def __init__(self):
        self.sent = []

    def send_change_immediate(self, payload):
        self.sent.append(payload)


@pytest.fixture
def daemon_env(suspension, monkeypatch):
    """Démon prêt à traiter un message : apikey, jeedom_com et pronotepy factices."""
    daemon = suspension
    monkeypatch.setattr(daemon, "_apikey", "secret", raising=False)
    recorder = _Recorder()
    monkeypatch.setattr(daemon, "jeedom_com", recorder, raising=False)
    daemon.failed_attempts.clear()
    yield daemon, recorder
    daemon.failed_attempts.clear()


def _message(eq_id="7"):
    return {
        "apikey": "secret",
        "CmdId": eq_id,
        "TokenId": "client-id",
        "TokenUsername": "eleve",
        "TokenPassword": "chiffre",
        "TokenUrl": "https://ecole.index-education.net/pronote/eleve.html",
    }


class TestProcessMessage:
    def test_suspension_detectee_ouvre_la_fenetre(self, daemon_env, monkeypatch):
        daemon, recorder = daemon_env

        class _Client:
            @staticmethod
            def token_login(**kwargs):
                raise _FakePronoteError("Your IP address is suspended.")

        monkeypatch.setattr(daemon.pronotepy, "Client", _Client, raising=False)

        daemon.process_message(_message())

        assert daemon.ip_suspension_remaining() > 0
        payload = recorder.sent[-1]
        assert payload["connection_status"] == "ip_suspended"
        assert payload["CmdId"] == "7"
        assert payload["ip_suspended_until"] > time.time()
        # Le token n'est pas en cause : le circuit breaker ne doit pas compter d'échec.
        assert daemon.failed_attempts.get("7", {}).get("count", 0) == 0

    def test_requete_ignoree_pendant_la_fenetre(self, daemon_env, monkeypatch):
        daemon, recorder = daemon_env
        appels = []

        class _Client:
            @staticmethod
            def token_login(**kwargs):
                appels.append(1)
                raise AssertionError(
                    "Pronote ne doit pas être contacté pendant la pause"
                )

        monkeypatch.setattr(daemon.pronotepy, "Client", _Client, raising=False)
        daemon.trigger_ip_suspension()

        daemon.process_message(_message())

        assert appels == []
        assert recorder.sent[-1]["connection_status"] == "ip_suspended"

    def test_erreur_classique_non_confondue(self, daemon_env, monkeypatch):
        daemon, _recorder = daemon_env

        class _Client:
            @staticmethod
            def token_login(**kwargs):
                raise _FakePronoteError("Invalid credentials")

        monkeypatch.setattr(daemon.pronotepy, "Client", _Client, raising=False)

        daemon.process_message(_message("9"))

        # Token réellement invalide : pas de pause, mais un échec comptabilisé.
        assert daemon.ip_suspension_remaining() == 0
        assert daemon.failed_attempts["9"]["count"] == 1


# ── Garde posé sur pronotepy.post ────────────────────────────────────────────
class TestSuspensionIP:
    def test_traverse_les_except_exception(self):
        """C'est toute la raison d'être de l'héritage BaseException."""
        avale = False
        try:
            try:
                raise pronote_errors.SuspensionIP("suspendue")
            except Exception:  # noqa: BLE001 - reproduit le filet des collecteurs
                avale = True
        except pronote_errors.SuspensionIP:
            pass
        assert avale is False

    def test_n_est_pas_une_exception_ordinaire(self):
        assert issubclass(pronote_errors.SuspensionIP, BaseException)
        assert not issubclass(pronote_errors.SuspensionIP, Exception)


class _FauxClientBase:
    """Reproduit ClientBase.post : lève ce qu'on lui demande."""

    a_lever = None
    appels = 0

    def post(self, function_name, onglet=None, data=None):
        type(self).appels += 1
        if type(self).a_lever is not None:
            raise type(self).a_lever
        return {"ok": function_name}


class _FauxParentClient(_FauxClientBase):
    def post(self, function_name, onglet=None, data=None):  # override, comme pronotepy
        return _FauxClientBase.post(self, function_name, onglet, data)


@pytest.fixture
def garde(daemon, monkeypatch):
    """Installe le garde sur des classes factices, puis remet tout en place."""
    faux = types.SimpleNamespace(
        ClientBase=_FauxClientBase, ParentClient=_FauxParentClient
    )
    monkeypatch.setattr(daemon, "pronotepy", faux, raising=False)
    monkeypatch.setattr(daemon, "_garde_suspension_installee", False, raising=False)
    post_base, post_parent = _FauxClientBase.post, _FauxParentClient.post
    _FauxClientBase.a_lever = None
    _FauxClientBase.appels = 0
    yield daemon
    _FauxClientBase.post, _FauxParentClient.post = post_base, post_parent
    _FauxClientBase.a_lever = None
    daemon._garde_suspension_installee = False


class TestGardeSuspension:
    def test_suspension_convertie(self, garde):
        garde._installer_garde_suspension()
        _FauxClientBase.a_lever = _FakePronoteError("Your IP address is suspended.")
        with pytest.raises(pronote_errors.SuspensionIP):
            _FauxClientBase().post("PageEmploiDuTemps")

    def test_compte_parent_couvert(self, garde):
        garde._installer_garde_suspension()
        _FauxClientBase.a_lever = _FakePronoteError("Unknown error", code=25)
        with pytest.raises(pronote_errors.SuspensionIP):
            _FauxParentClient().post("PagePresence")

    def test_autres_erreurs_inchangees(self, garde):
        garde._installer_garde_suspension()
        _FauxClientBase.a_lever = ValueError("panne d'onglet")
        with pytest.raises(ValueError):
            _FauxClientBase().post("PageNotes")

    def test_appel_normal_transparent(self, garde):
        garde._installer_garde_suspension()
        assert _FauxClientBase().post("PageNotes") == {"ok": "PageNotes"}

    def test_idempotent(self, garde):
        garde._installer_garde_suspension()
        pose = _FauxClientBase.post
        garde._garde_suspension_installee = False  # force un second passage
        garde._installer_garde_suspension()
        assert _FauxClientBase.post is pose, "le garde ne doit pas s'empiler"

    def test_installation_silencieuse_si_pronotepy_change(self, garde, monkeypatch):
        # Si une version future de pronotepy déplace post(), le démon démarre
        # quand même — sans le garde.
        monkeypatch.setattr(garde, "pronotepy", types.SimpleNamespace(), raising=False)
        garde._installer_garde_suspension()
        assert garde._garde_suspension_installee is False


class TestCollecteInterrompue:
    def test_collecteur_ne_peut_pas_avaler_la_suspension(self, daemon_env, monkeypatch):
        """Le cas réel : la suspension tombe pendant la collecte."""
        daemon, recorder = daemon_env

        class _Client:
            @staticmethod
            def token_login(**kwargs):
                return types.SimpleNamespace(
                    logged_in=True,
                    info=types.SimpleNamespace(name="Élève", class_name="3A"),
                    communication=types.SimpleNamespace(authorized_onglets=[]),
                )

        def _edt_qui_avale(client):
            # Reproduit fidèlement le filet d'un collecteur.
            try:
                raise pronote_errors.SuspensionIP("suspendue")
            except Exception:  # noqa: BLE001
                return {"error": "avalé"}

        monkeypatch.setattr(daemon.pronotepy, "Client", _Client, raising=False)
        monkeypatch.setattr(daemon, "Checkeleve", lambda *a, **k: None)
        monkeypatch.setattr(daemon, "identites", lambda *a, **k: {})
        monkeypatch.setattr(daemon, "download_photo", lambda *a, **k: None)
        monkeypatch.setattr(daemon, "Emploidutemps", _edt_qui_avale)

        daemon.process_message(_message("11"))

        assert daemon.ip_suspension_remaining() > 0, (
            "la suspension doit ouvrir la fenêtre malgré le except Exception du collecteur"
        )
        statuts = [p.get("connection_status") for p in recorder.sent]
        assert "connected" not in statuts, "aucune donnée partielle ne doit partir"
        assert statuts[-1] == "ip_suspended"


# ── Serveur sans application mobile ──────────────────────────────────────────
class TestIsMissingMobileToken:
    """Un serveur peut accepter la demande de jeton et répondre une charge vide.

    Relevé le 13 septembre 2026 sur le site de démonstration d'Index Éducation :
    ``JetonAppliMobile`` renvoie ``dataSec.data == {}``, si bien que
    ``request_qr_code_data`` ne rend que l'URL, qu'il reconstruit lui-même.
    pronotepy ne le découvre qu'en lisant ``qr_code["login"]`` — d'où un
    ``KeyError: 'login'`` illisible.

    Un site de démonstration n'est pas un établissement : on ne sait pas si la
    cause est une option désactivée, une restriction propre à la démo, ou un
    état passager. La garde se contente donc de constater l'absence de jeton,
    sans rien conclure — c'est aussi ce que dit le message rendu à
    l'utilisateur.
    """

    def test_jeton_complet(self):
        qr = {
            "url": "https://x/pronote/mobile.eleve.html",
            "login": "ab",
            "jeton": "cd",
        }
        assert pronote_errors.is_missing_mobile_token(qr) is False

    def test_charge_vide_seule_url(self):
        assert pronote_errors.is_missing_mobile_token(
            {"url": "https://x/pronote/mobile.eleve.html"}
        )

    def test_login_present_mais_vide(self):
        assert pronote_errors.is_missing_mobile_token({"login": "", "jeton": "cd"})

    def test_jeton_present_mais_vide(self):
        assert pronote_errors.is_missing_mobile_token({"login": "ab", "jeton": ""})

    @pytest.mark.parametrize("valeur", [None, "", [], 0])
    def test_reponse_qui_n_est_pas_un_dictionnaire(self, valeur):
        assert pronote_errors.is_missing_mobile_token(valeur)


# ── Authentification refusée, sans cause connue ──────────────────────────────
class TestIsAuthentificationRefusee:
    """pronotepy initialise `parametres_utilisateur` à {} et n'y range la
    réponse que si la connexion a réussi. Après un refus, `ParentClient.__init__`
    lit `self.parametres_utilisateur["dataSec"]` et lève un KeyError bien après
    la cause — pronotepy a seulement journalisé « login failed » entre-temps.

    Le démon en déduisait « Token invalide, regénérer le QR CODE ». Or un jeton
    périmé et un serveur qui refuse temporairement de répondre laissent la même
    trace : le message affirmait une cause sur deux, et envoyait rescanner un QR
    Code parfois valide. Observé le 13 septembre 2026, vingt secondes avant que
    la vraie cause — une suspension d'IP — ne se déclare.
    """

    @pytest.mark.parametrize("cle", ["dataSec", "dataNonSec", "data", "session"])
    def test_cles_d_enveloppe(self, cle):
        assert pronote_errors.is_authentification_refusee(KeyError(cle))

    def test_autre_cle_non_confondue(self):
        """Un KeyError métier ne doit pas passer pour un refus d'authentification."""
        assert not pronote_errors.is_authentification_refusee(KeyError("listeAbsences"))

    def test_autre_exception(self):
        assert not pronote_errors.is_authentification_refusee(ValueError("dataSec"))

    def test_none(self):
        assert not pronote_errors.is_authentification_refusee(None)

    def test_keyerror_sans_argument(self):
        assert not pronote_errors.is_authentification_refusee(KeyError())

    def test_non_confondu_avec_une_suspension_d_ip(self):
        """Les deux diagnostics doivent rester disjoints : la suspension est
        testée en premier dans le démon, et ouvre une fenêtre de pause."""
        suspension = _FakePronoteError("Your IP address is suspended.")
        assert pronote_errors.is_ip_suspension_error(suspension)
        assert not pronote_errors.is_authentification_refusee(suspension)
