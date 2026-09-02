"""Tests du filet de sécurité sur le jeton de reconnexion (`token_secours`).

PRONOTE renouvelle le jeton à chaque authentification et refuse tout jeton
antérieur (vérifié sur une instance 2026.2.5). Le fichier de secours est donc
la seule chose qui puisse réparer une connexion sans redemander un QR Code à
l'utilisateur : ces tests verrouillent son écriture et sa relecture.
"""

import json
import os

import pytest

import token_secours


IDENTIFIANTS = {
    "pronote_url": "https://ex.index-education.net/pronote/mobile.parent.html",
    "username": "parent1",
    "password": "JETON-RECENT",
    "client_identifier": "ABC123",
    "uuid": "PJ-1234",
}


class TestAllerRetour:
    def test_enregistre_puis_relit(self, tmp_path):
        token_secours.enregistrer(str(tmp_path), 4, IDENTIFIANTS)

        assert token_secours.charger(str(tmp_path), 4) == IDENTIFIANTS

    def test_range_par_equipement(self, tmp_path):
        token_secours.enregistrer(str(tmp_path), 4, IDENTIFIANTS)
        autre = dict(IDENTIFIANTS, password="AUTRE")
        token_secours.enregistrer(str(tmp_path), 7, autre)

        assert token_secours.charger(str(tmp_path), 4)["password"] == "JETON-RECENT"
        assert token_secours.charger(str(tmp_path), 7)["password"] == "AUTRE"

    def test_ecrase_par_le_plus_recent(self, tmp_path):
        token_secours.enregistrer(str(tmp_path), 4, IDENTIFIANTS)
        token_secours.enregistrer(str(tmp_path), 4, dict(IDENTIFIANTS, password="T2"))

        assert token_secours.charger(str(tmp_path), 4)["password"] == "T2"

    def test_ne_laisse_pas_de_fichier_temporaire(self, tmp_path):
        token_secours.enregistrer(str(tmp_path), 4, IDENTIFIANTS)

        fichiers = os.listdir(tmp_path / "4")
        assert fichiers == [token_secours.NOM_FICHIER]


class TestRefusDesEcrituresInutiles:
    @pytest.mark.parametrize("credentials", [None, {}, {"username": "x"}, {"password": ""}])
    def test_sans_jeton_rien_n_est_ecrit(self, tmp_path, credentials):
        token_secours.enregistrer(str(tmp_path), 4, credentials)

        assert token_secours.charger(str(tmp_path), 4) is None


class TestLectureRobuste:
    def test_absence_de_fichier(self, tmp_path):
        assert token_secours.charger(str(tmp_path), 4) is None

    def test_fichier_illisible(self, tmp_path):
        chemin = tmp_path / "4" / token_secours.NOM_FICHIER
        chemin.parent.mkdir(parents=True)
        chemin.write_text("{ceci n'est pas du json")

        assert token_secours.charger(str(tmp_path), 4) is None

    def test_contenu_sans_jeton(self, tmp_path):
        chemin = tmp_path / "4" / token_secours.NOM_FICHIER
        chemin.parent.mkdir(parents=True)
        chemin.write_text(json.dumps({"username": "parent1"}))

        assert token_secours.charger(str(tmp_path), 4) is None

    def test_ecriture_impossible_ne_leve_pas(self, tmp_path, monkeypatch):
        """Le filet de sécurité ne doit jamais interrompre une collecte."""

        def _refuse(*a, **k):
            raise OSError("disque plein")

        monkeypatch.setattr(token_secours.os, "makedirs", _refuse)
        token_secours.enregistrer(str(tmp_path), 4, IDENTIFIANTS)  # ne lève pas
