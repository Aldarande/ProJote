"""Tests du garde-fou sur l'onglet « Présence ».

Absences, retards, punitions et évènements de vie scolaire passent tous par
l'onglet 19. Certains comptes le voient déclaré accessible par Pronote — il
figure dans `authorized_onglets` — mais la requête est refusée. pronotepy répond
à ce refus par une ré-authentification complète avant de rejouer, qui échoue à
son tour : quatre collectes, quatre authentifications, aucune donnée.

Le refus est donc retenu le temps du cycle. La portée est volontairement courte :
le refus peut être temporaire — début d'année scolaire, page non encore
initialisée, ou simplement aucune absence à ce jour — et un droit accordé
entre-temps doit être pris en compte dès le cycle suivant.
"""

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
    """Isole la mémoire des refus et fixe l'équipement courant.

    L'équipement courant est connu du démon seul et injecté dans le module des
    collecteurs (cf. collecteurs.installer) : c'est donc là qu'il se remplace.
    """
    import collecteurs

    daemon._presence_refusee.clear()
    monkeypatch.setattr(collecteurs, "_equipement_en_cours", lambda: 4)
    yield daemon
    daemon._presence_refusee.clear()


class TestDetectionDuRefus:
    """« Accès refusé » et « La page a expiré » ne disent pas la même chose.

    Les confondre — ce que faisait le code jusqu'au 20 septembre 2026 — fait
    abandonner les quatre collectes de l'onglet pour tout le cycle, alors qu'une
    session expirée se répare en relisant les périodes. Un bêta-testeur y a
    perdu ses absences, retards, punitions et évènements sur un simple
    « La page a expiré ! (11) ».
    """

    @pytest.mark.parametrize(
        "message",
        [
            "Unknown error from pronote: 3 | Accès refusé",
            "Acces refuse",
        ],
    )
    def test_un_droit_non_accorde_est_un_refus(self, daemon, message):
        assert daemon._refus_de_presence(RuntimeError(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "Unknown error from pronote: 20 | La page a expiré ! (11)",
            "Unknown error from pronote: 8 | La page a expiré ! (1)",
        ],
    )
    def test_une_session_morte_n_est_pas_un_refus(self, daemon, message):
        """C'est réparable : la traiter comme un refus interdit la reprise."""
        import presence_pronote

        assert daemon._refus_de_presence(RuntimeError(message)) is False
        assert presence_pronote.session_expiree(RuntimeError(message)) is True

    def test_l_exception_dediee_de_pronotepy_est_reconnue(self):
        """pronotepy réserve ExpiredObject (erreur G=22) au cas qu'il nomme."""
        import presence_pronote

        class ExpiredObject(Exception):
            pass

        assert presence_pronote.session_expiree(ExpiredObject("objet expiré")) is True

    @pytest.mark.parametrize(
        "message",
        ["Connection timed out", "Your IP address is suspended.", "boum"],
    )
    def test_ni_refus_ni_expiration(self, daemon, message):
        import presence_pronote

        assert presence_pronote.session_expiree(RuntimeError(message)) is False

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

        cycle_neuf._oublier_refus_presence(4)  # ce que fait le démon au cycle suivant
        periode = _Periode()
        cycle_neuf.absences(_Client(periode))

        assert periode.appels == 1

    def test_equipements_independants(self, cycle_neuf, monkeypatch):
        cycle_neuf.absences(_Client(_Periode()))

        import collecteurs

        monkeypatch.setattr(collecteurs, "_equipement_en_cours", lambda: 9)
        periode = _Periode()
        cycle_neuf.absences(_Client(periode))

        assert periode.appels == 1


class TestLeRefusSeVoitDansLaCharge:
    """Un onglet illisible ne doit pas ressembler à un onglet vide.

    Sans clause ``error``, les quatre collectes rendaient ``nb_absences: 0``,
    ``nb_retard: 0``, ``Nb_Punitions: 0`` et des listes vides. Jeedom écrivait
    donc quatre commandes à zéro, statut « Connecté » : pour un parent qui suit
    la vie scolaire, un zéro rassurant là où le plugin n'avait rien pu lire, et
    aucun scénario d'alerte branché sur ces compteurs ne pouvait se déclencher.
    """

    def test_le_collecteur_qui_essuie_le_refus_le_rapporte(self, cycle_neuf):
        rendu = cycle_neuf.absences(_Client(_Periode()))

        assert "error" in rendu
        assert "Présence" in rendu["error"]

    def test_les_collecteurs_qui_s_abstiennent_le_rapportent_aussi(self, cycle_neuf):
        """Ils n'ont pas vu l'erreur passer, mais la cause est la même."""
        cycle_neuf.absences(_Client(_Periode()))

        for rendu in (
            cycle_neuf.retards(_Client(_Periode())),
            cycle_neuf.punitions(_Client(_Periode())),
        ):
            assert "error" in rendu

    def test_le_motif_pronote_est_conserve(self, cycle_neuf):
        """C'est lui qui distingue un droit manquant d'une session expirée."""
        cycle_neuf.absences(_Client(_Periode()))

        assert "Accès refusé" in cycle_neuf._motif_de_refus(4)
        assert "Accès refusé" in cycle_neuf.retards(_Client(_Periode()))["error"]

    def test_une_collecte_qui_reussit_ne_porte_pas_d_erreur(self, cycle_neuf):
        """Le zéro légitime doit continuer de passer : aucun repli ne doit le figer."""

        class _PeriodeVide:
            name = "Année continue"
            id = "P1"
            absences = []

        rendu = cycle_neuf.absences(_Client(_PeriodeVide()))

        assert rendu["nb_absences"] == 0
        assert "error" not in rendu
