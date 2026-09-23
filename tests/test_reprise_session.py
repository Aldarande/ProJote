"""Tests de la reprise après expiration de session PRONOTE.

PRONOTE est une application à état : l'identifiant d'une période ne vaut que
pour la session qui l'a émise. Quand la session meurt en cours de cycle,
pronotepy se ré-authentifie tout seul (`ClientBase.post` rattrape l'erreur,
appelle `refresh()`, puis rejoue) — mais il rejoue **la même charge**, donc avec
le même objet période, dont l'identifiant appartient à la session morte. Le
rejeu échoue exactement comme la tentative.

`refresh()` reconstruit pourtant `client.periods_` avec des identifiants neufs.
Il suffisait de relire la propriété. Faute de quoi le plugin concluait à un
onglet refusé et abandonnait les quatre collectes du cycle — absences, retards,
punitions, évènements — alors qu'une simple relecture suffisait.

Relevé chez un bêta-testeur le 19 septembre 2026 :

    ERROR - Collecte en erreur pour les absences : Onglet Présence (19)
            inaccessible … Unknown error from pronote: 20 | La page a expiré ! (11)

La reprise est limitée à **une par cycle** : chacune passe par une
authentification complète, et leur accumulation a déjà valu une suspension
d'adresse IP par PRONOTE — 415 authentifications en quelques secondes le
13 septembre 2026.
"""

import datetime

import pytest

import collecteurs
import presence_pronote


EXPIREE = "Unknown error from pronote: 20 | La page a expiré ! (11)"


class _Element:
    def __init__(self, id_):
        self.id = id_


class _Periode:
    """Période liée à une session : elle refuse de répondre si celle-ci est morte.

    C'est le comportement réel de PRONOTE — l'identifiant porté par l'objet
    n'est valable que pour sa session.
    """

    def __init__(self, session, elements, nom="Trimestre 1"):
        self.name = nom
        self.id = "P-%s" % session
        self._session = session
        self._elements = elements
        self.start = datetime.datetime(2026, 9, 1)
        self.end = datetime.datetime(2026, 12, 20)

    def _lire(self):
        if self._session.morte:
            raise RuntimeError(EXPIREE)
        return self._elements

    @property
    def absences(self):
        return self._lire()

    @property
    def delays(self):
        return self._lire()

    @property
    def punishments(self):
        return self._lire()


class _Session:
    def __init__(self):
        self.morte = False


class _Client:
    """Client dont la session meurt, et dont `periods` rend des objets à jour.

    Reproduit la mécanique de pronotepy : `refresh()` (ici implicite, déclenché
    par la relecture) fabrique une session neuve, et `client.periods` rend des
    périodes rattachées à celle-ci.
    """

    def __init__(self, elements, meurt_apres=None):
        self.session = _Session()
        self._elements = elements
        self._meurt_apres = meurt_apres
        self.lectures_periodes = 0

    @property
    def periods(self):
        self.lectures_periodes += 1
        # Relire la propriété vaut réinitialisation : c'est ce que fait
        # pronotepy dans refresh() — periods_ est reconstruit.
        if self.lectures_periodes > 1:
            self.session = _Session()
        session = self.session
        if self._meurt_apres is not None and self.lectures_periodes == self._meurt_apres:
            session.morte = True
        return [_Periode(session, self._elements)]


@pytest.fixture(autouse=True)
def cycle_neuf(monkeypatch):
    """Équipement courant connu, mémoires de refus et de reprise vierges."""
    monkeypatch.setattr(collecteurs, "_equipement_en_cours", lambda: 7)
    presence_pronote._presence_refusee.clear()
    presence_pronote._reprise_tentee.clear()
    yield
    presence_pronote._presence_refusee.clear()
    presence_pronote._reprise_tentee.clear()


# ── Le cas nominal ne doit rien coûter ──────────────────────────────────────


def test_sans_incident_aucune_relecture():
    client = _Client([_Element(1), _Element(2)])
    elements, motif = collecteurs._relever_sur_periodes(
        client, 7, "absences", "absences"
    )
    assert len(elements) == 2
    assert motif is None
    assert client.lectures_periodes == 1, "une relecture inutile a été faite"
    assert not presence_pronote.reprise_deja_tentee(7)


def test_la_liste_fournie_evite_une_lecture():
    """L'appelant a déjà lu les périodes pour son contrôle d'accès."""
    client = _Client([_Element(1)])
    periodes = client.periods
    client.lectures_periodes = 0

    elements, motif = collecteurs._relever_sur_periodes(
        client, 7, "absences", "absences", periodes=periodes
    )
    assert len(elements) == 1
    assert client.lectures_periodes == 0


# ── La reprise ──────────────────────────────────────────────────────────────


def test_une_session_expiree_est_reprise():
    """Le cœur du correctif : relire les périodes suffit à s'en sortir."""
    client = _Client([_Element(1), _Element(2), _Element(3)], meurt_apres=1)

    elements, motif = collecteurs._relever_sur_periodes(
        client, 7, "absences", "absences"
    )

    assert motif is None, "la reprise aurait dû aboutir"
    assert len(elements) == 3
    assert client.lectures_periodes == 2, "les périodes n'ont pas été relues"


def test_la_reprise_est_notee_pour_le_cycle():
    client = _Client([_Element(1)], meurt_apres=1)
    collecteurs._relever_sur_periodes(client, 7, "absences", "absences")
    assert presence_pronote.reprise_deja_tentee(7)


def test_une_seule_reprise_par_cycle():
    """La seconde collecte ne redépense pas une authentification complète.

    C'est le garde qui évite la cascade : quatre collectes, quatre reprises,
    quatre authentifications — le chemin qui a valu une suspension d'IP.
    """
    presence_pronote.noter_reprise(7)
    client = _Client([_Element(1)], meurt_apres=1)

    elements, motif = collecteurs._relever_sur_periodes(
        client, 7, "delays", "retards"
    )

    assert motif is not None
    assert "reprise déjà tentée" in motif
    assert client.lectures_periodes == 1, "une seconde reprise a été tentée"


def test_une_expiration_qui_persiste_est_rapportee():
    """Si la session remeurt aussitôt, on le dit — sans boucler."""

    class _ClientTetu(_Client):
        @property
        def periods(self):
            self.lectures_periodes += 1
            session = _Session()
            session.morte = True
            return [_Periode(session, self._elements)]

    client = _ClientTetu([_Element(1)])
    elements, motif = collecteurs._relever_sur_periodes(
        client, 7, "absences", "absences"
    )

    assert motif is not None
    assert "malgré une reprise" in motif
    assert client.lectures_periodes == 2, "plus d'une reprise a été tentée"


def test_la_reprise_ne_masque_pas_un_droit_refuse():
    """« Accès refusé » reste définitif : aucune reprise ne le réparerait."""

    class _PeriodeRefusee(_Periode):
        def _lire(self):
            raise RuntimeError("Unknown error from pronote: 3 | Accès refusé")

    class _ClientRefuse(_Client):
        @property
        def periods(self):
            self.lectures_periodes += 1
            return [_PeriodeRefusee(self.session, self._elements)]

    client = _ClientRefuse([_Element(1)])
    elements, motif = collecteurs._relever_sur_periodes(
        client, 7, "absences", "absences"
    )

    assert motif is not None
    assert "Onglet Présence (19) inaccessible" in motif
    assert client.lectures_periodes == 1, "une reprise a été tentée pour rien"
    assert presence_pronote._presence_deja_refusee(7), "le refus doit être retenu"
    assert not presence_pronote.reprise_deja_tentee(7)


def test_un_nouveau_cycle_reautorise_une_reprise():
    presence_pronote.noter_reprise(7)
    assert presence_pronote.reprise_deja_tentee(7)

    presence_pronote._oublier_refus_presence(7)  # ce que fait le worker
    assert not presence_pronote.reprise_deja_tentee(7)


# ── Les trois collecteurs partagent bien ce chemin ──────────────────────────


@pytest.mark.parametrize(
    "collecteur, cle",
    [
        (lambda c: collecteurs.absences(c), "nb_absences"),
        (lambda c: collecteurs.retards(c), "nb_retard"),
        (lambda c: collecteurs.punitions(c), "Nb_Punitions"),
    ],
)
def test_les_trois_collecteurs_reprennent(collecteur, cle, monkeypatch):
    """Une reprise écrite trois fois, c'est trois façons de diverger."""
    monkeypatch.setattr(collecteurs, "_relever_sur_periodes",
                        lambda *a, **k: ([], None))
    client = _Client([])
    data = collecteur(client)
    assert cle in data


# ── Une fois la reprise perdue, l'onglet est clos pour le cycle ─────────────
#
# La distinction entre « Accès refusé » et « La page a expiré » porte sur ce
# qu'il faut TENTER : le premier est définitif, la seconde se répare en relisant
# les périodes. Une fois la tentative faite et perdue, les deux mènent au même
# endroit — l'onglet ne répondra plus de ce cycle.
#
# Tant que l'expiration ne l'était pas retenue, chacune des quatre collectes
# redécouvrait la panne pour son compte : une requête, une ré-authentification
# complète et un rejeu perdu d'avance, quatre fois. Relevé chez un bêta-testeur
# le 22 septembre 2026, à raison d'un cycle sur un :
#
#     11:02:27 ERROR … pour les absences : Session PRONOTE expirée malgré une reprise
#     11:02:28 ERROR … pour les retards  : … et reprise déjà tentée sur ce cycle
#
# C'est le régime exact qui avait valu la suspension d'adresse IP du
# 13 septembre, dont la durée double à chaque récidive.


class _ClientTetu(_Client):
    """Session qui remeurt aussitôt renouvelée : la reprise ne peut pas aboutir."""

    @property
    def periods(self):
        self.lectures_periodes += 1
        session = _Session()
        session.morte = True
        return [_Periode(session, self._elements)]


def test_une_expiration_qui_survit_a_la_reprise_clot_l_onglet():
    client = _ClientTetu([_Element(1)])

    collecteurs._relever_sur_periodes(client, 7, "absences", "absences")

    assert presence_pronote._presence_deja_refusee(7), (
        "les trois autres collectes vont refaire la panne pour leur compte"
    )


def test_les_collectes_suivantes_ne_touchent_plus_le_reseau():
    """Le vrai gain : de cinq authentifications par cycle à deux."""
    client = _ClientTetu([_Element(1)])
    collecteurs._relever_sur_periodes(client, 7, "absences", "absences")
    lectures_apres_absences = client.lectures_periodes

    collecteurs.retards(client)
    collecteurs.punitions(client)
    collecteurs.evenements_vie_scolaire(client)

    # Chaque collecteur lit `client.periods` une fois pour son contrôle d'accès,
    # puis s'arrête net : aucune ne redescend vers PRONOTE.
    assert client.lectures_periodes == lectures_apres_absences + 3


def test_les_collectes_suivantes_rapportent_la_cause():
    """Un onglet illisible ne doit jamais ressembler à un onglet vide."""
    client = _ClientTetu([_Element(1)])
    collecteurs._relever_sur_periodes(client, 7, "absences", "absences")

    data = collecteurs.retards(client)

    assert data["nb_retard"] == 0
    assert "error" in data
    assert "Présence" in data["error"]


def test_une_reprise_deja_depensee_clot_aussi_l_onglet():
    """Le premier collecteur a dépensé la reprise sans le dire : on le dit ici."""
    presence_pronote.noter_reprise(7)
    client = _Client([_Element(1)], meurt_apres=1)

    collecteurs._relever_sur_periodes(client, 7, "delays", "retards")

    assert presence_pronote._presence_deja_refusee(7)


def test_une_reprise_reussie_ne_clot_rien():
    """Le cas nominal du correctif : on ne doit pénaliser personne."""
    client = _Client([_Element(1)], meurt_apres=1)

    _, motif = collecteurs._relever_sur_periodes(client, 7, "absences", "absences")

    assert motif is None
    assert not presence_pronote._presence_deja_refusee(7)


def test_le_cycle_suivant_repart_de_zero():
    client = _ClientTetu([_Element(1)])
    collecteurs._relever_sur_periodes(client, 7, "absences", "absences")

    presence_pronote._oublier_refus_presence(7)  # ce que fait le worker

    assert not presence_pronote._presence_deja_refusee(7)
    assert not presence_pronote.reprise_deja_tentee(7)
