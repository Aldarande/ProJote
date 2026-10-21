"""Tests du statut « Pronote injoignable » (`unreachable`).

Le 20 octobre 2026, l'équipement d'un collège a perdu deux cycles sur un timeout
de 120 s, puis un troisième sur une connexion refusée par le réseau :

    ERROR : traitement abandonné (timeout dur 120s, Pronote/ENT injoignable ?)
    ERROR : Connexion au jeton impossible : ('Connection aborted.',
            TimeoutError(110, 'Connection timed out'))
    ERROR : Tous les jetons disponibles ont été refusés pour l'équipement 767.

Le centre de messages a annoncé « Session expirée — Veuillez rescanner le QR
code », et le cycle suivant s'est reconnecté sans aucune action : le jeton
n'avait jamais été en cause. Trois conséquences étaient fausses — le compteur du
circuit breaker, le statut `disconnected`, et le niveau ERROR du journal.

Ces tests verrouillent la frontière : un incident réseau rend `unreachable` et
ne touche à rien, un refus réel garde le comportement d'origine.
"""

import json
import time

import pronote_errors
import pytest
import token_secours


# ── Erreurs reproduites ──────────────────────────────────────────────────────
class _ErreurDeConnexion(Exception):
    """Reproduit `requests.exceptions.ConnectionError` — requests est bouchonné.

    La forme des arguments est celle relevée en production : un libellé, puis
    l'erreur système imbriquée.
    """


def _timeout_reseau():
    return _ErreurDeConnexion(
        "Connection aborted.", TimeoutError(110, "Connection timed out")
    )


IDENTIFIANTS_SECOURS = {
    "pronote_url": "https://ecole.index-education.net/pronote/mobile.eleve.html",
    "username": "eleve",
    "password": "JETON-DE-SECOURS",
    "client_identifier": "client-id",
    "uuid": "PJ-767",
}


# ── Libellés rendus à l'utilisateur ──────────────────────────────────────────
class TestMessageInjoignable:
    def test_timeout_nomme_le_delai(self):
        assert pronote_errors.motif_injoignable(_timeout_reseau()) == (
            pronote_errors.MOTIF_DELAI
        )

    def test_trace_de_production(self):
        """La trace exacte du 20 octobre doit être reconnue comme un délai."""
        message = pronote_errors.message_injoignable(_timeout_reseau())
        assert message == (
            "Pronote injoignable (délai dépassé) — nouvel essai au prochain cycle"
        )

    def test_sans_exception_aucun_motif_inventé(self):
        assert pronote_errors.motif_injoignable() == ""
        assert pronote_errors.message_injoignable() == (
            "Pronote injoignable — nouvel essai au prochain cycle"
        )

    def test_motif_fourni_par_l_appelant(self):
        """Le timeout dur du worker ne lève aucune exception à lire."""
        assert pronote_errors.message_injoignable(motif=pronote_errors.MOTIF_DELAI) == (
            "Pronote injoignable (délai dépassé) — nouvel essai au prochain cycle"
        )

    def test_rien_n_invite_a_revalider(self):
        """Tout le défaut tient là : ne pas envoyer rescanner un QR Code valide."""
        message = pronote_errors.message_injoignable(_timeout_reseau()).lower()
        for mot in ("qr", "rescann", "expir", "identifiant"):
            assert mot not in message


# ── Câblage dans le démon ────────────────────────────────────────────────────
class _Recorder:
    """Remplace jeedom_com : mémorise les payloads envoyés à Jeedom."""

    def __init__(self):
        self.sent = []

    def send_change_immediate(self, payload):
        self.sent.append(payload)


@pytest.fixture
def daemon_env(daemon, tmp_path, monkeypatch):
    """Démon prêt à traiter un message, avec un dossier de données temporaire."""
    monkeypatch.setattr(daemon, "_apikey", "secret", raising=False)
    monkeypatch.setattr(daemon, "_data_dir", str(tmp_path), raising=False)
    recorder = _Recorder()
    monkeypatch.setattr(daemon, "jeedom_com", recorder, raising=False)
    daemon.failed_attempts.clear()
    daemon._ip_suspension.update({"until": 0.0, "level": 0, "last": 0.0})
    yield daemon, recorder, tmp_path
    daemon.failed_attempts.clear()
    daemon._ip_suspension.update({"until": 0.0, "level": 0, "last": 0.0})


def _message(eq_id="767"):
    return {
        "apikey": "secret",
        "CmdId": eq_id,
        "TokenId": "client-id",
        "TokenUsername": "eleve",
        "TokenPassword": "JETON-EN-BASE",
        "TokenUrl": "https://ecole.index-education.net/pronote/eleve.html",
    }


def _client_qui_leve(monkeypatch, daemon, exception):
    """Branche un pronotepy.Client qui refuse toute connexion, et compte les essais."""
    essais = []

    class _Client:
        @staticmethod
        def token_login(**kwargs):
            essais.append(kwargs.get("password"))
            raise exception

    monkeypatch.setattr(daemon.pronotepy, "Client", _Client, raising=False)
    return essais


class TestIncidentReseau:
    """Pronote n'a pas répondu : rien n'est en cause, rien ne doit bouger."""

    def test_statut_unreachable(self, daemon_env, monkeypatch):
        daemon, recorder, _ = daemon_env
        _client_qui_leve(monkeypatch, daemon, _timeout_reseau())

        daemon.process_message(_message())

        payload = recorder.sent[-1]
        assert payload["connection_status"] == "unreachable"
        assert payload["CmdId"] == "767"
        assert payload["error"] == (
            "Pronote injoignable (délai dépassé) — nouvel essai au prochain cycle"
        )

    def test_aucun_echec_comptabilise(self, daemon_env, monkeypatch):
        """Le cœur du défaut : une panne réseau rapprochait du blocage du jeton."""
        daemon, _recorder, _ = daemon_env
        _client_qui_leve(monkeypatch, daemon, _timeout_reseau())

        daemon.process_message(_message())

        assert daemon.failed_attempts.get("767", {}).get("count", 0) == 0

    def test_jeton_de_secours_intact(self, daemon_env, monkeypatch):
        daemon, _recorder, tmp_path = daemon_env
        token_secours.enregistrer(str(tmp_path), "767", IDENTIFIANTS_SECOURS)
        essais = _client_qui_leve(monkeypatch, daemon, _timeout_reseau())

        daemon.process_message(_message())

        assert essais == ["JETON-EN-BASE"], "le jeton de secours ne doit pas être joué"
        assert token_secours.charger(str(tmp_path), "767") == IDENTIFIANTS_SECOURS

    def test_aucun_statut_disconnected(self, daemon_env, monkeypatch):
        """C'est `disconnected` qui déclenchait « Session expirée » côté PHP."""
        daemon, recorder, _ = daemon_env
        _client_qui_leve(monkeypatch, daemon, _timeout_reseau())

        daemon.process_message(_message())

        statuts = [p.get("connection_status") for p in recorder.sent]
        assert "disconnected" not in statuts

    def test_journalise_en_avertissement(self, daemon_env, monkeypatch, caplog):
        daemon, _recorder, _ = daemon_env
        _client_qui_leve(monkeypatch, daemon, _timeout_reseau())

        with caplog.at_level("WARNING"):
            daemon.process_message(_message())

        niveaux = {
            r.levelname
            for r in caplog.records
            if "injoignable" in r.getMessage().lower()
        }
        assert niveaux == {"WARNING"}

    @pytest.mark.parametrize(
        "exception",
        [
            _ErreurDeConnexion("Connection aborted."),
            TimeoutError(110, "Connection timed out"),
            OSError("Network is unreachable"),
            RuntimeError("Le service est momentanément indisponible"),
        ],
    )
    def test_autres_incidents_passagers(self, daemon_env, monkeypatch, exception):
        daemon, recorder, _ = daemon_env
        _client_qui_leve(monkeypatch, daemon, exception)

        daemon.process_message(_message("12"))

        assert recorder.sent[-1]["connection_status"] == "unreachable"
        assert daemon.failed_attempts.get("12", {}).get("count", 0) == 0


class TestRefusReel:
    """Un jeton réellement refusé garde le comportement d'origine."""

    def test_statut_disconnected_et_increment(self, daemon_env, monkeypatch):
        daemon, recorder, _ = daemon_env
        _client_qui_leve(monkeypatch, daemon, KeyError("dataSec"))

        daemon.process_message(_message("9"))

        payload = recorder.sent[-1]
        assert payload["connection_status"] == "disconnected"
        assert daemon.failed_attempts["9"]["count"] == 1

    def test_message_n_affirme_plus_une_cause(self, daemon_env, monkeypatch):
        """PRONOTE ne dit pas pourquoi il refuse : le message ne doit pas trancher."""
        daemon, recorder, _ = daemon_env
        _client_qui_leve(monkeypatch, daemon, KeyError("dataSec"))

        daemon.process_message(_message("9"))

        erreur = recorder.sent[-1]["error"]
        assert erreur == (
            "Pronote a refusé la connexion. Si cela se répète au prochain cycle, "
            "revalidez le compte (QR code ou identifiants)."
        )

    def test_jeton_de_secours_essaye(self, daemon_env, monkeypatch):
        daemon, recorder, tmp_path = daemon_env
        token_secours.enregistrer(str(tmp_path), "9", IDENTIFIANTS_SECOURS)
        essais = _client_qui_leve(monkeypatch, daemon, KeyError("dataSec"))

        daemon.process_message(_message("9"))

        assert essais == ["JETON-EN-BASE", "JETON-DE-SECOURS"]
        assert recorder.sent[-1]["connection_status"] == "disconnected"
        assert daemon.failed_attempts["9"]["count"] == 1

    def test_suspension_d_ip_reste_distincte(self, daemon_env, monkeypatch):
        """Elle a son propre statut et sa propre fenêtre de pause."""
        daemon, recorder, _ = daemon_env
        _client_qui_leve(
            monkeypatch, daemon, RuntimeError("Your IP address is suspended.")
        )

        daemon.process_message(_message("5"))

        assert recorder.sent[-1]["connection_status"] == "ip_suspended"
        assert daemon.failed_attempts.get("5", {}).get("count", 0) == 0


class TestTimeoutDurDuWorker:
    """Le timeout dur par équipement (`_WORKER_TIMEOUT`) suit la même règle."""

    @pytest.fixture
    def worker(self, daemon_env, monkeypatch):
        daemon, recorder, _ = daemon_env
        monkeypatch.setattr(daemon, "_WORKER_TIMEOUT", 0.2, raising=False)

        def _trop_long(message):
            time.sleep(5)

        monkeypatch.setattr(daemon, "process_message", _trop_long)
        daemon._ensure_worker()
        return daemon, recorder

    def _attendre_payload(self, recorder, delai=10.0):
        limite = time.time() + delai
        while time.time() < limite:
            if recorder.sent:
                return recorder.sent[-1]
            time.sleep(0.05)
        raise AssertionError("aucun statut remonté à Jeedom après le timeout dur")

    def test_remonte_unreachable(self, worker):
        daemon, recorder = worker
        with daemon._queued_eq_lock:
            daemon._queued_eq.add("767")
        daemon._work_queue.put(_message())

        payload = self._attendre_payload(recorder)

        assert payload["connection_status"] == "unreachable"
        assert payload["error"] == (
            "Pronote injoignable (délai dépassé) — nouvel essai au prochain cycle"
        )

    def test_n_alimente_pas_le_compteur_de_jetons(self, worker):
        daemon, recorder = worker
        daemon._work_queue.put(_message("768"))

        self._attendre_payload(recorder)

        assert daemon.failed_attempts.get("768", {}).get("count", 0) == 0

    def test_libere_le_slot_de_l_equipement(self, worker):
        daemon, recorder = worker
        with daemon._queued_eq_lock:
            daemon._queued_eq.add("769")
        daemon._work_queue.put(_message("769"))

        self._attendre_payload(recorder)

        with daemon._queued_eq_lock:
            assert "769" not in daemon._queued_eq


class TestNotifierInjoignable:
    def test_sans_equipement_reste_silencieux(self, daemon_env):
        """Hors démon, jeedom_com n'est pas initialisé : ne rien casser."""
        daemon, recorder, _ = daemon_env

        assert daemon.notifier_injoignable("") == (
            "Pronote injoignable — nouvel essai au prochain cycle"
        )
        assert recorder.sent == []

    def test_envoi_en_echec_ne_leve_pas(self, daemon_env, monkeypatch):
        daemon, _recorder, _ = daemon_env

        class _Casse:
            def send_change_immediate(self, payload):
                raise OSError("callback injoignable")

        monkeypatch.setattr(daemon, "jeedom_com", _Casse(), raising=False)

        daemon.notifier_injoignable("767", _timeout_reseau())


# ── Côté PHP : contrat vérifié par lecture du code ───────────────────────────
class TestContratPhp:
    """Le dépôt n'a pas d'outillage de test PHP : on verrouille le contrat.

    Ces assertions ne remplacent pas l'essai sur Jeedom (voir la documentation),
    mais elles empêchent le statut `unreachable` de redevenir muet côté PHP — et
    donc de retomber dans le chemin « Session expirée ».
    """

    @pytest.fixture
    def php(self):
        import os

        racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(
            os.path.join(racine, "core", "php", "jeeProJote.php"), encoding="utf-8"
        ) as f:
            callback = f.read()
        with open(
            os.path.join(racine, "core", "class", "ProJote.class.php"),
            encoding="utf-8",
        ) as f:
            classe = f.read()
        return callback, classe

    def test_statut_traite_avant_disconnected(self, php):
        callback, _classe = php
        assert callback.index("'unreachable'") < callback.index("'disconnected' ||")

    def test_message_differe_et_efface(self, php):
        _callback, classe = php
        assert "UNREACHABLE_CYCLES = 3" in classe
        assert "UNREACHABLE_DELAY = 21600" in classe
        assert "message::removeAll(__CLASS__, self::unreachableMessageId(" in classe

    def test_remise_a_zero_au_premier_cycle_reussi(self, php):
        callback, _classe = php
        connecte = callback[callback.index("$connection_status === 'connected'") :]
        assert "ProJote::clearUnreachable($eqLogic);" in connecte

    def test_widget_n_invite_pas_a_revalider(self, php):
        _callback, classe = php
        assert "stripos($statut, 'injoignable') !== false" in classe
        assert "$seResorbeSeul ? 'attendre' : 'revalider'" in classe


# ── Non-régression du classement des erreurs ─────────────────────────────────
class TestFrontiere:
    """`token_secours.erreur_de_jeton` est l'arbitre : il décide des deux voies."""

    def test_timeout_classe_passager(self):
        assert token_secours.erreur_de_jeton(_timeout_reseau()) is False

    def test_dataSec_classe_refus(self):
        assert token_secours.erreur_de_jeton(KeyError("dataSec")) is True

    def test_refus_sans_exception_classe_refus(self):
        """Pronote peut refuser sans rien lever : le jeton est alors en cause."""
        assert token_secours.erreur_de_jeton(None) is True


def test_charge_jeedom_complete(daemon_env, monkeypatch):
    """La charge doit porter les trois clés que jeeProJote.php lit."""
    daemon, recorder, _ = daemon_env
    _client_qui_leve(monkeypatch, daemon, _timeout_reseau())

    daemon.process_message(_message())

    payload = recorder.sent[-1]
    assert set(payload) == {"CmdId", "connection_status", "error"}
    assert json.dumps(payload)  # sérialisable tel quel
