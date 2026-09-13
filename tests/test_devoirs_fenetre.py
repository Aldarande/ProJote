"""Tests de la fenêtre couverte par la liste des devoirs.

Historiquement `devoir` ne retenait que l'échéance du jour même. La liste était
donc vide tous les week-ends et tous les soirs sans devoir à rendre le
lendemain, alors que Pronote fournit 120 jours d'avance — d'où un compteur à 0
pendant que « devoirs demain » en annonçait un.
"""

import datetime
import types

import pytest


def _devoir(jour, matiere="FRANCAIS", fait=False):
    return types.SimpleNamespace(
        date=jour,
        subject=types.SimpleNamespace(name=matiere),
        description="à faire",
        background_color="#E73A1F",
        done=fait,
        files=[],
    )


class _Client:
    """Client factice : renvoie les devoirs fournis, quelle que soit la plage."""

    def __init__(self, devoirs):
        self._devoirs = devoirs

    def homework(self, date_from, date_to):
        return [d for d in self._devoirs if date_from <= d.date <= date_to]


@pytest.fixture
def dimanche(daemon, monkeypatch):
    """Fige la date au dimanche 13 septembre 2026, le cas signalé."""

    class _Date(datetime.date):
        @classmethod
        def today(cls):
            return datetime.date(2026, 9, 13)

    monkeypatch.setattr(daemon.datetime, "date", _Date)
    return datetime.date(2026, 9, 13)


class TestFenetreParDefaut:
    def test_un_dimanche_les_devoirs_de_la_semaine_remontent(self, daemon, dimanche):
        """Le cas réel : rien à rendre dimanche, mais du travail dès lundi."""
        client = _Client([_devoir(dimanche + datetime.timedelta(days=1))])

        data = daemon.devoirs(client)

        assert data["Nb_devoir"] == 1
        assert data["devoir"][0]["date"] == "14/09"

    def test_les_devoirs_du_jour_restent_inclus(self, daemon, dimanche):
        client = _Client([_devoir(dimanche), _devoir(dimanche + datetime.timedelta(days=2))])

        data = daemon.devoirs(client)

        assert data["Nb_devoir"] == 2

    def test_au_dela_de_la_fenetre_exclu(self, daemon, dimanche):
        client = _Client([_devoir(dimanche + datetime.timedelta(days=8))])

        data = daemon.devoirs(client)

        assert data["Nb_devoir"] == 0

    def test_liste_triee_par_echeance(self, daemon, dimanche):
        client = _Client(
            [
                _devoir(dimanche + datetime.timedelta(days=5), "MATHS"),
                _devoir(dimanche + datetime.timedelta(days=1), "FRANCAIS"),
                _devoir(dimanche + datetime.timedelta(days=3), "HISTOIRE"),
            ]
        )

        data = daemon.devoirs(client)

        assert [d["title"] for d in data["devoir"]] == ["FRANCAIS", "HISTOIRE", "MATHS"]

    def test_compteurs_fait_et_non_fait(self, daemon, dimanche):
        client = _Client(
            [
                _devoir(dimanche + datetime.timedelta(days=1), fait=True),
                _devoir(dimanche + datetime.timedelta(days=2), fait=False),
            ]
        )

        data = daemon.devoirs(client)

        assert (data["Nb_devoir"], data["Nb_devoir_F"], data["Nb_devoir_NF"]) == (2, 1, 1)


class TestDateExposeeAuWidget:
    """Le widget compose l'échéance en toutes lettres au moment du rendu.

    Il lui faut donc la date complète : le « jj/mm » historique ne permet ni de
    situer l'année, ni de dire « Demain » sans ambiguïté.
    """

    def test_chaque_devoir_porte_sa_date_iso(self, daemon, dimanche):
        client = _Client([_devoir(dimanche + datetime.timedelta(days=1))])

        data = daemon.devoirs(client)

        assert data["devoir"][0]["date_iso"] == "2026-09-14"

    def test_le_format_court_reste_disponible(self, daemon, dimanche):
        """Compatibilité : les anciens rendus s'appuient encore sur « date »."""
        client = _Client([_devoir(dimanche + datetime.timedelta(days=1))])

        data = daemon.devoirs(client)

        assert data["devoir"][0]["date"] == "14/09"

    def test_devoirs_demain_aussi(self, daemon, dimanche):
        client = _Client([_devoir(dimanche + datetime.timedelta(days=1))])

        data = daemon.devoirs(client)

        assert data["devoir_Demain"][0]["date_iso"] == "2026-09-14"


class TestFenetreConfigurable:
    def test_un_seul_jour_retrouve_l_ancien_comportement(self, daemon, dimanche):
        client = _Client([_devoir(dimanche + datetime.timedelta(days=1))])

        data = daemon.devoirs(client, fenetre_jours=1)

        assert data["Nb_devoir"] == 0

    def test_fenetre_elargie(self, daemon, dimanche):
        client = _Client([_devoir(dimanche + datetime.timedelta(days=20))])

        assert daemon.devoirs(client, fenetre_jours=30)["Nb_devoir"] == 1


class TestLectureDeLaConfiguration:
    @pytest.mark.parametrize(
        "message,attendu",
        [
            ({"DevoirsJours": 14}, 14),
            ({"DevoirsJours": "3"}, 3),
            ({}, 7),
            ({"DevoirsJours": ""}, 7),
            ({"DevoirsJours": None}, 7),
            ({"DevoirsJours": "abc"}, 7),
            ({"DevoirsJours": 0}, 7),
            ({"DevoirsJours": -5}, 7),
            ({"DevoirsJours": 999}, 7),
        ],
    )
    def test_valeurs_acceptees_et_repli(self, daemon, message, attendu):
        assert daemon._fenetre_devoirs(message) == attendu


class TestDevoirsDemainInchange:
    def test_le_prochain_jour_reste_isole(self, daemon, dimanche):
        """« Devoirs demain » garde sa sémantique : le prochain jour concerné."""
        client = _Client(
            [
                _devoir(dimanche + datetime.timedelta(days=1), "FRANCAIS"),
                _devoir(dimanche + datetime.timedelta(days=4), "MATHS"),
            ]
        )

        data = daemon.devoirs(client)

        assert data["Nb_devoir_Demain"] == 1
        assert data["devoir_Demain"][0]["title"] == "FRANCAIS"
