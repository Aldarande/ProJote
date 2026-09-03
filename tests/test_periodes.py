"""Tests du collecteur de périodes du démon (`ProJoted.periodes`).

Pronote publie plusieurs découpages simultanés (trimestres, semestres, « Année
continue »). La source de vérité est `client.current_period`, que Pronote
désigne lui-même ; le repli par dates ne sert que si cette propriété est
indisponible, et doit alors retenir la période la plus courte.
"""

import datetime
import types


def _periode(identifiant, nom, debut, fin):
    """Fabrique un objet période minimal, comme pronotepy en expose."""
    return types.SimpleNamespace(
        id=identifiant,
        name=nom,
        start=datetime.datetime(*debut),
        end=datetime.datetime(*fin),
    )


TRIMESTRE_1 = _periode("T1", "Trimestre 1", (2026, 9, 1), (2026, 11, 22))
TRIMESTRE_2 = _periode("T2", "Trimestre 2", (2026, 11, 23), (2027, 3, 7))
ANNEE = _periode("A", "Année continue", (2026, 9, 1), (2027, 7, 4))


class _Client:
    """Client Pronote factice : périodes fixes, current_period paramétrable."""

    def __init__(self, periods, current=None, current_raise=False, general=None):
        self.periods = periods
        self._current = current
        self._current_raise = current_raise
        # Paramètres publiés par Pronote à la connexion (bloc « General »).
        self.func_options = {"dataSec": {"data": {"General": general or {}}}}

    @property
    def current_period(self):
        if self._current_raise:
            raise KeyError("listeOngletsPourPeriodes")
        return self._current


class TestPeriodeCourante:
    def test_utilise_current_period_en_priorite(self, daemon):
        """Même si d'autres périodes contiennent la date du jour."""
        client = _Client([TRIMESTRE_1, TRIMESTRE_2, ANNEE], current=TRIMESTRE_2)

        data = daemon.periodes(client)

        assert data["periode_courante"] == "Trimestre 2"
        assert data["periode_debut"] == "23/11/2026"
        assert data["periode_fin"] == "07/03/2027"

    def test_marque_la_periode_en_cours_dans_la_liste(self, daemon):
        client = _Client([TRIMESTRE_1, TRIMESTRE_2, ANNEE], current=TRIMESTRE_1)

        data = daemon.periodes(client)

        en_cours = [p["nom"] for p in data["periodes"] if p["en_cours"]]
        assert en_cours == ["Trimestre 1"]
        assert len(data["periodes"]) == 3

    def test_liste_complete_avec_dates_formatees(self, daemon):
        client = _Client([TRIMESTRE_1], current=TRIMESTRE_1)

        data = daemon.periodes(client)

        assert data["periodes"][0] == {
            "nom": "Trimestre 1",
            "debut": "01/09/2026",
            "fin": "22/11/2026",
            "en_cours": True,
        }


class TestAnneeScolaire:
    """Bornes de l'année scolaire, exposées en plus de la période en cours."""

    def test_lues_dans_les_parametres_pronote(self, daemon, monkeypatch):
        """Pronote les publie au login : aucune requête supplémentaire."""
        monkeypatch.setattr(
            daemon.pronotepy.dataClasses.Util,
            "datetime_parse",
            lambda v: datetime.datetime.strptime(v, "%d/%m/%Y %H:%M:%S"),
            raising=False,
        )
        client = _Client(
            [TRIMESTRE_1],
            current=TRIMESTRE_1,
            general={
                "PremiereDate": {"_T": 7, "V": "01/09/2026 00:00:00"},
                "DerniereDate": {"_T": 7, "V": "04/07/2027 00:00:00"},
            },
        )

        data = daemon.periodes(client)

        assert data["annee_debut"] == "01/09/2026"
        assert data["annee_fin"] == "04/07/2027"

    def test_repli_sur_la_periode_la_plus_large(self, daemon):
        """Sans paramètres exploitables, « Année continue » fait référence."""
        client = _Client([TRIMESTRE_1, TRIMESTRE_2, ANNEE], current=TRIMESTRE_1)

        data = daemon.periodes(client)

        assert data["annee_debut"] == "01/09/2026"
        assert data["annee_fin"] == "04/07/2027"

    def test_aucune_donnee_exploitable(self, daemon):
        client = _Client([], current=None)

        data = daemon.periodes(client)

        assert data["annee_debut"] == ""
        assert data["annee_fin"] == ""


class TestRepliParDates:
    def test_retient_la_periode_la_plus_courte(self, daemon, monkeypatch):
        """« Année continue » contient aussi la date du jour : ne pas la choisir."""

        class _Date(datetime.date):
            @classmethod
            def today(cls):
                return datetime.date(2026, 10, 15)

        monkeypatch.setattr(daemon.datetime, "date", _Date)
        client = _Client([ANNEE, TRIMESTRE_1, TRIMESTRE_2], current_raise=True)

        data = daemon.periodes(client)

        assert data["periode_courante"] == "Trimestre 1"

    def test_aucune_periode_ne_contient_le_jour(self, daemon, monkeypatch):
        class _Date(datetime.date):
            @classmethod
            def today(cls):
                return datetime.date(2027, 8, 15)  # plein été

        monkeypatch.setattr(daemon.datetime, "date", _Date)
        client = _Client([TRIMESTRE_1, TRIMESTRE_2], current_raise=True)

        data = daemon.periodes(client)

        assert data["periode_courante"] == ""
        assert data["periode_debut"] == ""
        assert len(data["periodes"]) == 2


class TestRobustesse:
    def test_erreur_d_acces_aux_periodes(self, daemon):
        class _ClientKO:
            @property
            def periods(self):
                raise RuntimeError("session expirée")

        data = daemon.periodes(_ClientKO())

        assert data["periode_courante"] == ""
        assert data["periodes"] == []
        assert "session expirée" in data["error"]

    def test_periode_sans_dates(self, daemon):
        bancale = types.SimpleNamespace(id="X", name="Sans dates", start=None, end=None)
        client = _Client([bancale], current=bancale)

        data = daemon.periodes(client)

        assert data["periode_courante"] == "Sans dates"
        assert data["periode_debut"] == ""
        assert data["periode_fin"] == ""

    def test_aucune_periode_retournee(self, daemon):
        data = daemon.periodes(_Client([], current=None))

        assert data["periodes"] == []
        assert data["periode_courante"] == ""
