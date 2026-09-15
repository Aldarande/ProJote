"""Tests du masquage des secrets dans les journaux du démon.

Le message que Jeedom envoie au démon par le socket porte les identifiants
Pronote en clair — TokenUsername, TokenPassword, TokenId, TokenUuid. Il était
journalisé entier à chaque cycle, deux fois : par le framework Jeedom
(« Message read from socket », en INFO) et par `read_socket()` du démon, en
DEBUG.

Le mode debug est justement celui qu'on active pour diagnostiquer un problème
de connexion : les journaux joints à une demande d'aide contenaient donc les
secrets du compte, et un journal Jeedom se partage facilement.

Le filtre est posé sur les handlers plutôt que sur les appels, pour couvrir
aussi le site du framework Jeedom — code vendoré, non modifiable ici — et tout
site futur.

Relevé sur l'instance de développement le 13 septembre 2026.
"""

import io
import logging

import pytest


@pytest.fixture
def journal(daemon):
    """Logger racine équipé du filtre, écrivant dans une chaîne."""
    flux = io.StringIO()
    handler = logging.StreamHandler(flux)
    racine = logging.getLogger()
    handlers_avant, niveau_avant = racine.handlers, racine.level
    racine.handlers = [handler]
    racine.setLevel(logging.DEBUG)
    daemon.installer_filtre_secrets()
    yield flux
    racine.handlers, racine.level = handlers_avant, niveau_avant


def test_message_json_du_framework(journal):
    """Le format du framework Jeedom : JSON, guillemets doubles."""
    logging.info(
        "%s",
        'Message read from socket: {"CmdId":16,"TokenUsername":"aletang",'
        '"TokenPassword":"EA7771234FFC4ED9","TokenId":"7C5C98077E98"}',
    )
    sortie = journal.getvalue()
    assert "aletang" not in sortie
    assert "EA7771234FFC4ED9" not in sortie
    assert "7C5C98077E98" not in sortie
    assert '"CmdId":16' in sortie, "le reste du message doit rester lisible"


def test_message_repr_python_du_demon(journal):
    """Le format du démon : repr d'un dict, guillemets simples."""
    logging.debug(
        "Message reçu : %s",
        {
            "command": "cronHourly",
            "TokenUsername": "aletang",
            "TokenPassword": "EA7771234FFC4ED9",
            "TokenUuid": "PJ-10552e26",
            "DevoirsJours": 7,
        },
    )
    sortie = journal.getvalue()
    assert "aletang" not in sortie
    assert "EA7771234FFC4ED9" not in sortie
    assert "PJ-10552e26" not in sortie
    assert "cronHourly" in sortie
    assert "'DevoirsJours': 7" in sortie


def test_le_jeton_du_qr_code_est_masque(journal):
    """`jetonConnexionAppliMobile` est le secret d'authentification du compte."""
    logging.debug("QR : %s", {"jetonConnexionAppliMobile": "ABCDEF0123456789"})
    assert "ABCDEF0123456789" not in journal.getvalue()


def test_l_url_reste_visible(journal):
    """L'URL de l'établissement n'est pas un secret et sert au diagnostic."""
    logging.info(
        "%s",
        '{"TokenUrl":"https://0312307p.index-education.net/pronote/",'
        '"TokenPassword":"secret"}',
    )
    sortie = journal.getvalue()
    assert "0312307p.index-education.net" in sortie
    assert "secret" not in sortie


def test_un_message_sans_secret_est_intact(journal):
    logging.info("Début traitement équipement %s", 16)
    assert "Début traitement équipement 16" in journal.getvalue()


def test_les_arguments_sont_neutralises(daemon, journal):
    """Sans vider `args`, logging réappliquerait les valeurs d'origine.

    Le filtre pré-formate le message ; si les arguments restaient en place,
    l'émission les réinjecterait — secrets compris — et le masquage serait
    sans effet.
    """
    enregistrement = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "%s", ('{"TokenPassword":"zzz"}',), None
    )
    daemon._FiltreSecrets().filter(enregistrement)
    assert enregistrement.args == ()
    assert "zzz" not in enregistrement.getMessage()


def test_installation_idempotente(daemon):
    """Deux appels ne doivent pas empiler deux filtres sur le même handler."""
    handler = logging.StreamHandler(io.StringIO())
    racine = logging.getLogger()
    handlers_avant = racine.handlers
    racine.handlers = [handler]
    try:
        daemon.installer_filtre_secrets()
        daemon.installer_filtre_secrets()
        filtres = [f for f in handler.filters if isinstance(f, daemon._FiltreSecrets)]
        assert len(filtres) == 1
    finally:
        racine.handlers = handlers_avant


def test_un_enregistrement_mal_forme_passe_quand_meme(daemon):
    """Mieux vaut une ligne non masquée qu'une ligne perdue.

    Un `%` mal apparié fait lever `getMessage()` ; le filtre doit alors laisser
    passer l'enregistrement plutôt que de l'escamoter.
    """
    enregistrement = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "%d", ("pas un entier",), None
    )
    assert daemon._FiltreSecrets().filter(enregistrement) is True
