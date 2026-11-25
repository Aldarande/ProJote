"""Tests de l'extraction du contenu des séances (cahier de textes).

Certains professeurs saisissent des consignes dans le « Contenu » de la séance
plutôt que dans « Travail à faire » : elles doivent remonter avec les devoirs.
"""

import datetime
import types

import pytest


@pytest.fixture
def collecteurs():
    import collecteurs as module  # chemin du démon ajouté par conftest

    return module


def _lesson(lid, start, subject="Mathématiques", color="#ff0000"):
    return types.SimpleNamespace(
        id=lid,
        start=start,
        subject=types.SimpleNamespace(name=subject) if subject else None,
        background_color=color,
    )


def _entry(lid, contenus):
    return {"cours": {"V": {"N": lid}}, "listeContenus": {"V": contenus}}


def _contenu(titre="", desc="", cat="", pieces=None):
    c = {"L": titre, "descriptif": {"V": desc}, "categorie": {"V": {"L": cat}}}
    if pieces is not None:
        c["ListePieceJointe"] = {"V": pieces}
    return c


D_MIN = datetime.date(2026, 11, 14)
D_MAX = datetime.date(2026, 11, 21)


class TestParseContenusCours:
    def test_extrait_et_trie_du_plus_recent(self, collecteurs):
        lessons = {
            "a": _lesson("a", datetime.datetime(2026, 11, 17, 8, 0), "Français"),
            "b": _lesson("b", datetime.datetime(2026, 11, 20, 10, 0), "Anglais"),
        }
        entries = [
            _entry("a", [_contenu("Chapitre 3", "Lire p. 42", "Cours")]),
            _entry("b", [_contenu("", "Exercice 5 pour lundi")]),
        ]
        out = collecteurs.parse_contenus_cours(entries, lessons, D_MIN, D_MAX)
        assert [c["title"] for c in out] == ["Anglais", "Français"]
        assert out[0]["date"] == "20/11" and out[0]["heure"] == "10:00"
        assert out[0]["date_iso"] == "2026-11-20"
        assert out[1]["titre"] == "Chapitre 3"
        assert out[1]["categorie"] == "Cours"
        assert out[1]["description"] == "Lire p. 42"
        assert "_tri" not in out[0]

    def test_titre_seul_ecarte(self, collecteurs):
        """Un titre sans description ni pièce jointe est un objectif de programme."""
        lessons = {"a": _lesson("a", datetime.datetime(2026, 11, 18, 9, 0))}
        entries = [_entry("a", [
            _contenu("Appliquer des principes simples"),
            _contenu("", "", pieces=[{"N": "1"}]),
        ])]
        files = lambda pieces: [{"nom": "fiche.pdf", "url": "u", "type": 1}]
        out = collecteurs.parse_contenus_cours(entries, lessons, D_MIN, D_MAX, files)
        assert len(out) == 1 and out[0]["fichiers"][0]["nom"] == "fiche.pdf"

    def test_piece_jointe_illisible_garde_le_contenu(self, collecteurs):
        lessons = {"a": _lesson("a", datetime.datetime(2026, 11, 18, 9, 0))}
        entries = [_entry("a", [_contenu("Fiche", pieces=[{"N": "1"}])])]

        def boom(pieces):
            raise RuntimeError("illisible")

        out = collecteurs.parse_contenus_cours(entries, lessons, D_MIN, D_MAX, boom)
        assert len(out) == 1 and out[0]["fichiers"] == []

    def test_tous_les_contenus_d_une_seance(self, collecteurs):
        lessons = {"a": _lesson("a", datetime.datetime(2026, 11, 18, 9, 0))}
        entries = [_entry("a", [_contenu("Partie 1", "x"), _contenu("Partie 2", "y")])]
        out = collecteurs.parse_contenus_cours(entries, lessons, D_MIN, D_MAX)
        assert [c["titre"] for c in out] == ["Partie 1", "Partie 2"]

    def test_ignore_vide_hors_plage_et_inconnu(self, collecteurs):
        lessons = {
            "a": _lesson("a", datetime.datetime(2026, 11, 18, 9, 0)),
            "old": _lesson("old", datetime.datetime(2026, 11, 1, 9, 0)),
        }
        entries = [
            _entry("a", [_contenu()]),  # contenu vide
            _entry("old", [_contenu("t", "d")]),  # hors plage
            _entry("inconnu", [_contenu("t", "d")]),  # cours absent
            {"cours": {"V": {}}},  # structure incomplète
        ]
        assert collecteurs.parse_contenus_cours(entries, lessons, D_MIN, D_MAX) == []

    def test_sans_matiere_et_pieces_jointes(self, collecteurs):
        lessons = {"a": _lesson("a", datetime.datetime(2026, 11, 18, 9, 0), subject=None)}
        entries = [_entry("a", [_contenu(pieces=[{"N": "1"}])])]
        files = lambda pieces: [{"nom": "fiche.pdf", "url": "u", "type": 1}]
        out = collecteurs.parse_contenus_cours(entries, lessons, D_MIN, D_MAX, files)
        assert out[0]["title"] == "Inconnu"
        assert out[0]["fichiers"][0]["nom"] == "fiche.pdf"

    def test_limite_du_nombre_d_entrees(self, collecteurs):
        start = datetime.datetime(2026, 11, 18, 8, 0)
        lessons = {
            str(i): _lesson(str(i), start + datetime.timedelta(minutes=i))
            for i in range(50)
        }
        entries = [_entry(str(i), [_contenu("t", "d")]) for i in range(50)]
        out = collecteurs.parse_contenus_cours(entries, lessons, D_MIN, D_MAX)
        assert len(out) == collecteurs.CONTENU_COURS_MAX


class TestContenusCours:
    def test_un_seul_appel_au_cahier_de_textes(self, collecteurs):
        today = datetime.date.today()
        ce_matin = datetime.datetime.combine(today, datetime.time(9, 0))
        appels = []

        class _Client:
            def lessons(self, d1, d2):
                return [_lesson("x", ce_matin, "SVT")]

            def get_week(self, d):
                return 10

            def post(self, page, onglet, data):
                appels.append((page, onglet, data))
                return {"dataSec": {"data": {"ListeCahierDeTextes": {"V": [
                    _entry("x", [_contenu("", "Faire la fiche")]),
                ]}}}}

        data = collecteurs.contenus_cours(_Client())
        assert data["Nb_contenu_cours"] == 1
        assert data["contenu_cours"][0]["title"] == "SVT"
        assert appels == [("PageCahierDeTexte", 89, {"domaine": {"_T": 8, "V": "[10..10]"}})]
        assert "error" not in data

    @staticmethod
    def _fige(collecteurs, monkeypatch, jour):
        class _Date(datetime.date):
            @classmethod
            def today(cls):
                return jour

        monkeypatch.setattr(collecteurs.datetime, "date", _Date)

    @staticmethod
    def _client(cours, demandes, rentree=None):
        """Client factice : `cours` = [(id, datetime, annulé)]."""

        class _Client:
            start_day = rentree

            def lessons(self, d1, d2):
                demandes.append((d1, d2))
                fin = datetime.datetime.combine(d2, datetime.time.min)
                debut = datetime.datetime.combine(d1, datetime.time.min)
                return [
                    types.SimpleNamespace(**vars(_lesson(k, dt, k)), canceled=ann)
                    for k, dt, ann in cours
                    if debut <= dt <= fin
                ]

            def get_week(self, d):
                return 12

            def post(self, page, onglet, data):
                return {"dataSec": {"data": {"ListeCahierDeTextes": {"V": [
                    _entry(k, [_contenu("", "Consigne")]) for k, _, _ in cours
                ]}}}}

        return _Client()

    def test_cinq_jours_de_cours_cours_du_jour_compris(self, collecteurs, monkeypatch):
        """Mercredi 25/11 : mercredi, mardi, lundi, vendredi, jeudi. Pronotepy
        coupe la plage à minuit le dernier jour : il faut demander jusqu'à demain."""
        self._fige(collecteurs, monkeypatch, datetime.date(2026, 11, 25))
        a = lambda j, h=9: datetime.datetime(2026, 11, j, h, 0)
        cours = [(str(j), a(j), False) for j in (16, 17, 18, 19, 20, 23, 24, 26)]
        cours.append(("25", a(25, 16), False))
        demandes = []
        data = collecteurs.contenus_cours(self._client(cours, demandes))
        assert demandes == [(datetime.date(2026, 11, 16), datetime.date(2026, 11, 26))]
        assert [c["date"] for c in data["contenu_cours"]] == [
            "25/11", "24/11", "23/11", "20/11", "19/11"]

    def test_jour_annule_ne_compte_pas(self, collecteurs, monkeypatch):
        self._fige(collecteurs, monkeypatch, datetime.date(2026, 11, 25))
        a = lambda j: datetime.datetime(2026, 11, j, 9, 0)
        cours = [(str(j), a(j), j == 24) for j in (18, 19, 20, 23, 24, 25)]
        data = collecteurs.contenus_cours(self._client(cours, []))
        # mardi 24 annulé : la fenêtre remonte jusqu'au mercredi 18
        assert [c["date"] for c in data["contenu_cours"]][-1] == "18/11"

    def test_retour_de_vacances_plafond(self, collecteurs, monkeypatch):
        """Lundi de rentrée après deux semaines : on élargit, sans dépasser 21 jours."""
        self._fige(collecteurs, monkeypatch, datetime.date(2026, 11, 2))
        d = lambda m, j: datetime.datetime(2026, m, j, 9, 0)
        cours = [("a", d(10, 12), False), ("b", d(10, 13), False),
                 ("c", d(10, 15), False), ("d", d(10, 16), False),
                 ("e", d(11, 2), False)]
        demandes = []
        data = collecteurs.contenus_cours(self._client(cours, demandes))
        assert demandes == [
            (datetime.date(2026, 10, 26), datetime.date(2026, 11, 3)),
            (datetime.date(2026, 10, 12), datetime.date(2026, 10, 26)),
        ]
        assert [c["date"] for c in data["contenu_cours"]] == [
            "02/11", "16/10", "15/10", "13/10", "12/10"]

    def test_jamais_avant_la_rentree(self, collecteurs, monkeypatch):
        self._fige(collecteurs, monkeypatch, datetime.date(2026, 9, 2))
        demandes = []
        cours = [("a", datetime.datetime(2026, 9, 1, 9, 0), False)]
        collecteurs.contenus_cours(
            self._client(cours, demandes, rentree=datetime.date(2026, 8, 31)))
        assert all(d1 >= datetime.date(2026, 8, 31) for d1, _ in demandes)

    def test_echec_sans_cle_error(self, collecteurs):
        """Un échec ne doit pas faire passer toute la collecte des devoirs pour ratée."""

        class _Client:
            def lessons(self, d1, d2):
                raise RuntimeError("panne")

        data = collecteurs.contenus_cours(_Client())
        assert data == {"contenu_cours": [], "Nb_contenu_cours": 0}
