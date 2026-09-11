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
            "Unknown error from pronote: 42", pronote_msg="Suspension temporaire de l'accès"
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
        assert pronote_errors.is_ip_suspension_error(Exception("YOUR IP ADDRESS IS SUSPENDED."))


class TestIpSuspensionReason:
    def test_sans_exception(self):
        assert pronote_errors.ip_suspension_reason() == pronote_errors.IP_SUSPENSION_MESSAGE

    def test_avec_detail(self):
        reason = pronote_errors.ip_suspension_reason(Exception("Your IP address is suspended."))
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
            {"level": 4, "last": time.time() - suspension._IP_SUSPENSION_LEVEL_RESET - 60}
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
            json.dumps({"until": time.time() - 10, "level": 1, "last": time.time() - 3600})
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
                raise AssertionError("Pronote ne doit pas être contacté pendant la pause")

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
