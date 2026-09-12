"""Tests de `_periodes_couvrantes` — réduction des requêtes PagePresence.

Pronote publie une douzaine de découpages qui se recouvrent. Absences, retards
et punitions s'interrogent par plage de dates : les demander pour chaque
découpage renvoie douze fois les mêmes enregistrements, et chaque requête coûte
une ré-authentification complète sur les serveurs 2026.

Ces tests vérifient que la sélection couvre exactement la même plage tout en
retenant le minimum de périodes.
"""

import datetime
import types


def _p(nom, debut, fin):
    return types.SimpleNamespace(
        name=nom, start=datetime.datetime(*debut), end=datetime.datetime(*fin)
    )


ANNEE = _p("Année continue", (2026, 9, 1), (2027, 7, 4))
SEM1 = _p("Semestre 1", (2026, 9, 1), (2027, 1, 18))
SEM2 = _p("Semestre 2", (2027, 1, 19), (2027, 7, 4))
TRIM1 = _p("Trimestre 1", (2026, 9, 1), (2026, 11, 23))
TRIM2 = _p("Trimestre 2", (2026, 11, 24), (2027, 3, 1))
TRIM3 = _p("Trimestre 3", (2027, 3, 2), (2027, 7, 4))


def _noms(periodes):
    return [p.name for p in periodes]


class TestReduction:
    def test_une_periode_englobante_suffit(self, daemon):
        """Le cas réel : douze découpages, tous inclus dans l'année."""
        toutes = [TRIM1, SEM1, ANNEE, TRIM2, SEM2, TRIM3]

        assert _noms(daemon._periodes_couvrantes(toutes)) == ["Année continue"]

    def test_sans_englobante_les_semestres_suffisent(self, daemon):
        """Deux semestres contigus couvrent les trois trimestres."""
        retenues = _noms(daemon._periodes_couvrantes([TRIM1, TRIM2, TRIM3, SEM1, SEM2]))

        assert sorted(retenues) == ["Semestre 1", "Semestre 2"]

    def test_une_periode_qui_depasse_est_conservee(self, daemon):
        """Une période hors de l'année ne doit pas être perdue."""
        hors = _p("Hors période", (2027, 8, 1), (2027, 8, 20))
        retenues = _noms(daemon._periodes_couvrantes([ANNEE, SEM1, hors]))

        assert sorted(retenues) == ["Année continue", "Hors période"]

    def test_periodes_contigues_en_couvrent_une_a_cheval(self, daemon):
        """La fusion des intervalles doit rendre le trimestre 2 superflu."""
        a_cheval = _p("mi semestre", (2026, 12, 1), (2027, 2, 1))
        retenues = _noms(daemon._periodes_couvrantes([SEM1, SEM2, a_cheval]))

        assert sorted(retenues) == ["Semestre 1", "Semestre 2"]


class TestRobustesse:
    def test_liste_vide(self, daemon):
        assert daemon._periodes_couvrantes([]) == []

    def test_none(self, daemon):
        assert daemon._periodes_couvrantes(None) == []

    def test_periodes_sans_dates_sont_toutes_rendues(self, daemon):
        """Sans dates exploitables, on ne peut pas raisonner : on ne filtre pas."""
        bancales = [
            types.SimpleNamespace(name="A", start=None, end=None),
            types.SimpleNamespace(name="B", start=None, end=None),
        ]

        assert _noms(daemon._periodes_couvrantes(bancales)) == ["A", "B"]

    def test_dates_incoherentes_ignorees(self, daemon):
        """Une période dont la fin précède le début est écartée du calcul."""
        absurde = _p("Absurde", (2027, 5, 1), (2026, 5, 1))
        retenues = _noms(daemon._periodes_couvrantes([ANNEE, absurde]))

        assert retenues == ["Année continue"]

    def test_une_seule_periode(self, daemon):
        assert _noms(daemon._periodes_couvrantes([SEM1])) == ["Semestre 1"]
