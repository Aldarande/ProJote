"""Tests des évènements de vie scolaire.

PRONOTE mélange tous les évènements du Carnet dans l'unique liste
« listeAbsences » de la réponse PagePresence, distingués par un code « G ».
pronotepy n'en modélise que trois — 13 absence, 14 retard, 41 punition — et
écarte silencieusement les autres.

Relevé sur le serveur de démonstration le 15 septembre 2026 : 25 observations
(code 40), 15 défauts de carnet (46), 5 mesures conservatoires (71), et **pas
une seule occurrence du code 41**. Le plugin interrogeait donc la seule
catégorie que l'établissement n'utilisait pas, et annonçait « aucune punition »
sur un compte dont le Carnet affiche trois entrées.

La collecte passe par une requête directe, aucune propriété pronotepy n'exposant
ces évènements.
"""

import datetime

import pytest

import collecteurs


# ── Doublures ───────────────────────────────────────────────────────────────


class _Periode:
    def __init__(self, nom="Trimestre 1"):
        self.name = nom
        self.id = "P1"
        self.start = datetime.datetime(2026, 9, 1)
        self.end = datetime.datetime(2026, 12, 20)


class _Client:
    """Client pronotepy minimal : périodes et réponse brute de PagePresence."""

    def __init__(self, evenements=None, periodes=None, post_explose=None,
                 periodes_explose=None):
        self._evenements = evenements or []
        self._periodes = periodes if periodes is not None else [_Periode()]
        self._post_explose = post_explose
        self._periodes_explose = periodes_explose
        self.appels = 0

    @property
    def periods(self):
        if self._periodes_explose is not None:
            raise self._periodes_explose
        return self._periodes

    def post(self, fonction, onglet, donnees):
        self.appels += 1
        assert fonction == "PagePresence"
        assert onglet == 19
        if self._post_explose is not None:
            raise self._post_explose
        return {"dataSec": {"data": {"listeAbsences": {"V": self._evenements}}}}


def _brut(genre, identifiant, date, libelle=None, nature=None):
    """Évènement au format brut PRONOTE."""
    e = {"G": genre, "N": identifiant, "dateDebut": {"V": date}}
    if libelle is not None:
        e["L"] = libelle
    if nature is not None:
        e["nature"] = {"V": {"L": nature}}
    return e


@pytest.fixture(autouse=True)
def equipement_connu(monkeypatch):
    """Les collecteurs de l'onglet Présence ont besoin d'un équipement courant."""
    monkeypatch.setattr(collecteurs, "_equipement_en_cours", lambda: 7)
    collecteurs._presence_deja_refusee  # noqa: B018 - présence de la dépendance
    import presence_pronote

    presence_pronote._presence_refusee.clear()


# ── Ce que pronotepy laissait tomber ────────────────────────────────────────


def test_les_trois_categories_sont_collectees():
    client = _Client([
        _brut(collecteurs.G_OBSERVATION, "n1", "17/09/2026 08:00:00"),
        _brut(collecteurs.G_DEFAUT_CARNET, "n2", "16/09/2026 10:00:00", libelle="Carnet oublié"),
        _brut(collecteurs.G_MESURE_CONSERVATOIRE, "n3", "15/09/2026 09:00:00",
              nature="Exclusion conservatoire"),
    ])
    data = collecteurs.evenements_vie_scolaire(client)

    assert data["Nb_Evenements"] == 3
    assert [e["categorie"] for e in data["evenement"]] == [
        "Observation", "Défaut de carnet/carte", "Mesure conservatoire",
    ]


def test_les_codes_modelises_par_pronotepy_sont_ignores():
    """13, 14 et 41 sont déjà collectés ailleurs : les reprendre ferait doublon."""
    client = _Client([
        _brut(13, "a", "17/09/2026 08:00:00"),
        _brut(14, "b", "17/09/2026 08:00:00"),
        _brut(41, "c", "17/09/2026 08:00:00"),
        _brut(collecteurs.G_OBSERVATION, "d", "17/09/2026 08:00:00"),
    ])
    data = collecteurs.evenements_vie_scolaire(client)
    assert data["Nb_Evenements"] == 1
    assert data["evenement"][0]["id"] == "d"


def test_un_code_inconnu_est_ignore():
    client = _Client([_brut(99, "x", "17/09/2026 08:00:00")])
    assert collecteurs.evenements_vie_scolaire(client)["Nb_Evenements"] == 0


# ── Libellé : PRONOTE le range à trois endroits différents ──────────────────


def test_libelle_lu_dans_le_champ_direct():
    client = _Client([_brut(collecteurs.G_DEFAUT_CARNET, "n", "17/09/2026", libelle="Carnet oublié")])
    assert collecteurs.evenements_vie_scolaire(client)["evenement"][0]["libelle"] == "Carnet oublié"


def test_libelle_lu_dans_la_nature():
    client = _Client([_brut(collecteurs.G_MESURE_CONSERVATOIRE, "n", "17/09/2026",
                            nature="Exclusion de cours")])
    assert collecteurs.evenements_vie_scolaire(client)["evenement"][0]["libelle"] == "Exclusion de cours"


def test_sans_libelle_on_retombe_sur_la_categorie():
    """Une observation n'en porte aucun : mieux vaut « Observation » que vide."""
    client = _Client([_brut(collecteurs.G_OBSERVATION, "n", "17/09/2026")])
    assert collecteurs.evenements_vie_scolaire(client)["evenement"][0]["libelle"] == "Observation"


def test_libelle_vide_traite_comme_absent():
    client = _Client([_brut(collecteurs.G_DEFAUT_CARNET, "n", "17/09/2026", libelle="   ")])
    assert (
        collecteurs.evenements_vie_scolaire(client)["evenement"][0]["libelle"]
        == "Défaut de carnet/carte"
    )


# ── Tri chronologique ───────────────────────────────────────────────────────


def test_le_plus_recent_en_tete():
    """Trier les dates en chaîne ordonnait par jour avant le mois.

    « 02/12/2026 » passait alors avant « 17/09/2026 », et dernier_evenement
    désignait le mauvais évènement — celui qu'une notification met en avant.
    """
    client = _Client([
        _brut(collecteurs.G_OBSERVATION, "septembre", "17/09/2026 08:00:00"),
        _brut(collecteurs.G_OBSERVATION, "decembre", "02/12/2026 09:00:00"),
    ])
    data = collecteurs.evenements_vie_scolaire(client)

    assert [e["id"] for e in data["evenement"]] == ["decembre", "septembre"]
    assert data["dernier_evenement"] == [data["evenement"][0]]


@pytest.mark.parametrize(
    "date", ["17/09/2026 08:00:00", "17/09/2026 08:00", "17/09/2026"]
)
def test_les_formes_de_date_rencontrees(date):
    assert collecteurs._quand({"date": date}) == datetime.datetime(
        2026, 9, 17, 8 if " " in date else 0, 0
    )


def test_une_date_illisible_ne_fait_pas_echouer_le_tri():
    client = _Client([
        _brut(collecteurs.G_OBSERVATION, "bonne", "17/09/2026 08:00:00"),
        _brut(collecteurs.G_OBSERVATION, "cassee", "pas une date"),
    ])
    data = collecteurs.evenements_vie_scolaire(client)
    assert [e["id"] for e in data["evenement"]] == ["bonne", "cassee"]


# ── Robustesse ──────────────────────────────────────────────────────────────


def test_dedoublonnage_par_identifiant():
    """Les découpages de périodes se recouvrent : le même évènement revient.

    Sans déduplication, une observation serait comptée deux fois dans
    Nb_Evenements — une commande historisée, donc un graphique faux.
    """
    meme = _brut(collecteurs.G_OBSERVATION, "n1", "17/09/2026 08:00:00")
    client = _Client([meme, dict(meme)])
    assert collecteurs.evenements_vie_scolaire(client)["Nb_Evenements"] == 1


def test_une_requete_par_periode_couvrante():
    """Le coût est proportionnel aux périodes retenues, pas à toutes.

    _periodes_couvrantes écarte les découpages redondants : c'est ce qui évite
    d'interroger PagePresence une fois par trimestre *et* une fois par semestre.
    """
    from periodes_scolaires import _periodes_couvrantes

    periodes = [_Periode("T1"), _Periode("T2")]
    attendu = len(_periodes_couvrantes(periodes))
    client = _Client([], periodes=periodes)
    collecteurs.evenements_vie_scolaire(client)
    assert client.appels == attendu


def test_periodes_inaccessibles():
    data = collecteurs.evenements_vie_scolaire(_Client(periodes_explose=RuntimeError("boum")))
    assert data["Nb_Evenements"] == 0
    assert "boum" in data["error"]


def test_requete_en_echec_rend_une_liste_vide_sans_lever():
    data = collecteurs.evenements_vie_scolaire(_Client(post_explose=RuntimeError("500")))
    assert data == {"evenement": [], "dernier_evenement": [], "Nb_Evenements": 0}


def test_refus_de_l_onglet_presence_memorise():
    """Le refus est retenu : les collecteurs suivants s'abstiennent.

    Sans cela, chaque collecteur de cet onglet provoquerait une
    ré-authentification complète pour rien.
    """
    import presence_pronote

    refus = RuntimeError("Unknown error from pronote: 3 | Accès refusé")
    client = _Client(post_explose=refus)
    data = collecteurs.evenements_vie_scolaire(client)

    assert data["evenement"] == []
    assert presence_pronote._presence_deja_refusee(7) is True


def test_liste_absente_de_la_reponse():
    """Un serveur qui ne renvoie pas listeAbsences ne doit pas faire échouer."""

    class _Muet(_Client):
        def post(self, fonction, onglet, donnees):
            self.appels += 1
            return {"dataSec": {"data": {}}}

    assert collecteurs.evenements_vie_scolaire(_Muet())["Nb_Evenements"] == 0


# ── Contrat vers Jeedom ─────────────────────────────────────────────────────


def test_les_cles_attendues_par_le_php():
    data = collecteurs.evenements_vie_scolaire(_Client())
    assert set(data) == {"evenement", "dernier_evenement", "Nb_Evenements"}


def test_champs_d_un_evenement():
    client = _Client([_brut(collecteurs.G_OBSERVATION, "n1", "17/09/2026 08:00:00")])
    entree = collecteurs.evenements_vie_scolaire(client)["evenement"][0]
    assert set(entree) == {"id", "categorie", "libelle", "date", "periode"}
    assert entree["periode"] == "Trimestre 1"


# ── La date n'est pas rangée au même endroit selon la catégorie ─────────────
#
# Relevé sur le serveur de démonstration le 17 septembre 2026 :
#   G=40 Observation            → dateDebut
#   G=46 Défaut de carnet/carte → date, et rien d'autre
#   G=71 Mesure conservatoire   → dateDebut, dateDemande, dateFin
#
# Ne lire que dateDebut laissait les défauts de carnet sans date. Constaté sur
# un compte réel : quatre défauts de carnet remontés avec une date vide, donc
# relégués en queue de tri.


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ({"dateDebut": {"V": "01/10/2025 08:00:00"}}, "01/10/2025 08:00:00"),
        ({"date": {"V": "28/11/2025 09:00:00"}}, "28/11/2025 09:00:00"),
        ({"dateDemande": {"V": "10/07/2025 13:41:06"}}, "10/07/2025 13:41:06"),
        # dateDebut l'emporte quand plusieurs sont présentes.
        (
            {"dateDebut": {"V": "11/07/2025 08:00:00"}, "dateDemande": {"V": "10/07/2025 13:41:06"}},
            "11/07/2025 08:00:00",
        ),
        ({}, ""),
        ({"dateDebut": {}}, ""),
        ({"dateDebut": {"V": "   "}}, ""),
        ({"dateDebut": "pas un dictionnaire"}, "pas un dictionnaire"),
    ],
)
def test_date_lue_selon_la_categorie(brut, attendu):
    assert collecteurs._date_evenement(brut) == attendu


def test_un_defaut_de_carnet_a_bien_sa_date():
    """Le cas qui manquait : la date est dans « date », pas dans « dateDebut »."""
    client = _Client([
        {"G": collecteurs.G_DEFAUT_CARNET, "N": "n1", "L": "Défauts de carnet/carte",
         "date": {"_T": 7, "V": "28/11/2025 09:00:00"}},
    ])
    entree = collecteurs.evenements_vie_scolaire(client)["evenement"][0]
    assert entree["date"] == "28/11/2025 09:00:00"


def test_les_trois_categories_gardent_leur_date():
    client = _Client([
        {"G": collecteurs.G_OBSERVATION, "N": "o", "dateDebut": {"V": "01/10/2025 08:00:00"}},
        {"G": collecteurs.G_DEFAUT_CARNET, "N": "d", "date": {"V": "28/11/2025 09:00:00"}},
        {"G": collecteurs.G_MESURE_CONSERVATOIRE, "N": "m",
         "dateDebut": {"V": "11/07/2025 08:00:00"}, "dateDemande": {"V": "10/07/2025 13:41:06"}},
    ])
    data = collecteurs.evenements_vie_scolaire(client)
    assert all(e["date"] for e in data["evenement"]), "une date manque"
    # Et le tri reste chronologique, toutes catégories confondues.
    assert [e["id"] for e in data["evenement"]] == ["d", "o", "m"]
