"""Tests du garde-fou sur l'onglet « Présence ».

Absences, retards et punitions passent tous par l'onglet 19. Certains comptes le
voient déclaré accessible par Pronote — il figure dans `authorized_onglets` —
mais la requête est refusée. pronotepy répond à ce refus par une
ré-authentification complète avant de rejouer, qui échoue à son tour : trois
collectes, trois authentifications, aucune donnée.

Le refus est donc retenu le temps du cycle. La portée est volontairement courte :
le refus peut être temporaire — début d'année scolaire, page non encore
initialisée, ou simplement aucune absence à ce jour — et un droit accordé
entre-temps doit être pris en compte dès le cycle suivant.
"""

import types

import pytest


class _Periode:
    def __init__(self, nom="Année continue"):
        self.name = nom
        self.id = "P1"
        self.appels = 0

    def _refuser(self):
        self.appels += 1
        raise RuntimeError("Unknown error from pronote: 3 | Accès refusé")

    absences = property(lambda self: self._refuser())
    delays = property(lambda self: self._refuser())
    punishments = property(lambda self: self._refuser())


class _Client:
    def __init__(self, periode):
        self.periods = [periode]


@pytest.fixture
def cycle_neuf(daemon, monkeypatch):
    """Isole la mémoire des refus et fixe l'équipement courant."""
    daemon._presence_refusee.clear()
    monkeypatch.setattr(daemon, "_equipement_en_cours", lambda: 4)
    yield daemon
    daemon._presence_refusee.clear()


class TestDetectionDuRefus:
    @pytest.mark.parametrize(
        "message",
        [
            "Unknown error from pronote: 3 | Accès refusé",
            "Unknown error from pronote: 20 | La page a expiré ! (11)",
            "Unknown error from pronote: 8 | La page a expiré ! (1)",
        ],
    )
    def test_signatures_du_refus(self, daemon, message):
        assert daemon._refus_de_presence(RuntimeError(message)) is True

    @pytest.mark.parametrize(
        "message",
        ["Connection timed out", "Your IP address is suspended.", "boum"],
    )
    def test_autres_erreurs_non_assimilees(self, daemon, message):
        assert daemon._refus_de_presence(RuntimeError(message)) is False


class TestPropagationDansLeCycle:
    def test_le_premier_refus_dispense_les_suivants(self, cycle_neuf):
        """Une seule tentative doit être faite, pas trois."""
        periode = _Periode()
        client = _Client(periode)

        cycle_neuf.absences(client)
        cycle_neuf.retards(client)
        cycle_neuf.punitions(client)

        assert periode.appels == 1

    def test_les_collectes_restent_vides_sans_lever(self, cycle_neuf):
        client = _Client(_Periode())

        assert cycle_neuf.absences(client)["absence"] == []
        assert cycle_neuf.retards(client)["retard"] == []
        assert cycle_neuf.punitions(client)["punition"] == []

    def test_le_refus_est_memorise(self, cycle_neuf):
        cycle_neuf.absences(_Client(_Periode()))

        assert cycle_neuf._presence_deja_refusee(4) is True

    def test_un_nouveau_cycle_reessaie(self, cycle_neuf):
        """Portée volontairement courte : le refus peut n'être que temporaire."""
        cycle_neuf.absences(_Client(_Periode()))
        assert cycle_neuf._presence_deja_refusee(4) is True

        cycle_neuf._presence_refusee.discard("4")  # ce que fait le démon au cycle suivant
        periode = _Periode()
        cycle_neuf.absences(_Client(periode))

        assert periode.appels == 1

    def test_equipements_independants(self, cycle_neuf, monkeypatch):
        cycle_neuf.absences(_Client(_Periode()))

        monkeypatch.setattr(cycle_neuf, "_equipement_en_cours", lambda: 9)
        periode = _Periode()
        cycle_neuf.absences(_Client(periode))

        assert periode.appels == 1
