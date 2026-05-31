"""Tests unitaires des fonctions utilitaires du démon ProJote.

Cible : les helpers purs (sans I/O réseau) de `ProJoted.py`. Les dépendances
externes sont stubées par `conftest.py`.
"""

import datetime
import types


# ── _truncate ────────────────────────────────────────────────────────────────
class TestTruncate:
    def test_empty(self, daemon):
        assert daemon._truncate("") == ""
        assert daemon._truncate(None) == ""

    def test_short_unchanged(self, daemon):
        assert daemon._truncate("Bonjour") == "Bonjour"

    def test_strips_whitespace(self, daemon):
        assert daemon._truncate("  Bonjour  ") == "Bonjour"

    def test_exact_length(self, daemon):
        txt = "a" * 10
        assert daemon._truncate(txt, 10) == txt

    def test_truncated_with_ellipsis(self, daemon):
        txt = "a" * 50
        out = daemon._truncate(txt, 10)
        assert out.endswith("…")
        assert len(out) == 10

    def test_non_string_input(self, daemon):
        assert daemon._truncate(12345) == "12345"


# ── _safe_attr ────────────────────────────────────────────────────────────────
class TestSafeAttr:
    def test_first_present(self, daemon):
        obj = types.SimpleNamespace(a="x", b="y")
        assert daemon._safe_attr(obj, "a", "b") == "x"

    def test_skips_missing_and_empty(self, daemon):
        obj = types.SimpleNamespace(a="", b=None, c="trouvé")
        assert daemon._safe_attr(obj, "a", "b", "c") == "trouvé"

    def test_default_when_none_found(self, daemon):
        obj = types.SimpleNamespace(x="z")
        assert daemon._safe_attr(obj, "a", "b", default="DEF") == "DEF"

    def test_default_empty_string(self, daemon):
        obj = types.SimpleNamespace()
        assert daemon._safe_attr(obj, "a") == ""


# ── _menu_to_text ─────────────────────────────────────────────────────────────
def _food(name):
    return {"name": name}


class TestMenuToText:
    def test_empty_dict(self, daemon):
        assert daemon._menu_to_text({}) == ""

    def test_omits_empty_sections(self, daemon):
        menu = {
            "first_meal": [_food("Salade")],
            "main_meal": [],
            "dessert": [_food("Yaourt")],
        }
        assert daemon._menu_to_text(menu) == "Salade · Yaourt"

    def test_section_order(self, daemon):
        menu = {
            "dessert": [_food("Fruit")],
            "first_meal": [_food("Soupe")],
            "main_meal": [_food("Poulet")],
        }
        # Ordre attendu : entrée, plat, …, dessert (indépendant de l'ordre du dict)
        assert daemon._menu_to_text(menu) == "Soupe · Poulet · Fruit"

    def test_multiple_items_joined_with_comma(self, daemon):
        menu = {"main_meal": [_food("Riz"), _food("Poisson")]}
        assert daemon._menu_to_text(menu) == "Riz, Poisson"


# ── _menu_to_html_row ─────────────────────────────────────────────────────────
class TestMenuToHtmlRow:
    def test_contains_date_and_text(self, daemon):
        menu = {"date": "2026-05-31", "is_lunch": True, "main_meal": [_food("Pâtes")]}
        html = daemon._menu_to_html_row(menu)
        assert "2026-05-31" in html
        assert "Pâtes" in html
        assert "Midi" in html

    def test_escapes_html(self, daemon):
        menu = {"date": "2026-05-31", "is_lunch": True, "main_meal": [_food("<b>x</b>")]}
        html = daemon._menu_to_html_row(menu)
        assert "<b>x</b>" not in html
        assert "&lt;b&gt;" in html

    def test_empty_menu_shows_dash(self, daemon):
        menu = {"date": "2026-05-31", "is_dinner": True}
        html = daemon._menu_to_html_row(menu)
        assert "—" in html
        assert "Soir" in html

    def test_labels_rendered(self, daemon):
        menu = {
            "date": "2026-05-31",
            "is_lunch": True,
            "main_meal": [{"name": "Poulet", "labels": [{"name": "Bio"}, {"name": "Local"}]}],
        }
        html = daemon._menu_to_html_row(menu)
        assert "pj-menu-label" in html
        assert "Bio" in html
        assert "Local" in html

    def test_no_labels_no_chip(self, daemon):
        menu = {"date": "2026-05-31", "is_lunch": True, "main_meal": [{"name": "Poulet"}]}
        html = daemon._menu_to_html_row(menu)
        assert "pj-menu-label" not in html


# ── _menu_labels ──────────────────────────────────────────────────────────────
class TestMenuLabels:
    def test_empty(self, daemon):
        assert daemon._menu_labels({}) == []

    def test_dedup_and_order(self, daemon):
        menu = {
            "first_meal": [{"name": "Salade", "labels": [{"name": "Bio"}]}],
            "main_meal": [{"name": "Poulet", "labels": [{"name": "Local"}, {"name": "Bio"}]}],
        }
        # Bio puis Local (ordre d'apparition), sans doublon.
        assert daemon._menu_labels(menu) == ["Bio", "Local"]

    def test_ignores_blank_labels(self, daemon):
        menu = {"main_meal": [{"name": "X", "labels": [{"name": ""}, {"name": "  "}]}]}
        assert daemon._menu_labels(menu) == []


# ── build_menu_data ───────────────────────────────────────────────────────────
class _Label:
    def __init__(self, id, name, color):
        self.id = id
        self.name = name
        self.color = color


class _Food:
    def __init__(self, id, name, labels=None):
        self.id = id
        self.name = name
        self.labels = labels or []


class _Menu:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class TestBuildMenuData:
    def test_full_serialization(self, daemon):
        menu = _Menu(
            id="M1",
            name="Déjeuner",
            date=datetime.date(2026, 5, 31),
            is_lunch=True,
            is_dinner=False,
            first_meal=[_Food("f1", "Salade", [_Label("l1", "Bio", "#0f0")])],
            main_meal=[_Food("f2", "Poulet")],
        )
        out = daemon.build_menu_data(menu)
        assert out["id"] == "M1"
        assert out["date"] == "2026-05-31"
        assert out["is_lunch"] is True
        assert out["first_meal"][0]["name"] == "Salade"
        assert out["first_meal"][0]["labels"][0]["name"] == "Bio"
        assert out["main_meal"][0]["name"] == "Poulet"

    def test_missing_attrs_defaults(self, daemon):
        menu = _Menu()
        out = daemon.build_menu_data(menu)
        assert out["id"] == ""
        assert out["date"] == ""
        assert out["is_lunch"] is False
        assert out["main_meal"] == []


# ── build_cours_data ──────────────────────────────────────────────────────────
class _Subject:
    def __init__(self, name):
        self.name = name


class _Lesson:
    def __init__(self, **kw):
        self.detention = kw.pop("detention", False)
        self.__dict__.update(kw)


class TestBuildCoursData:
    def _lesson(self, **over):
        base = dict(
            id="L1",
            start=datetime.datetime(2026, 5, 31, 8, 30),
            end=datetime.datetime(2026, 5, 31, 9, 30),
            teacher_name="M. Dupont",
            classroom="B12",
            canceled=False,
            status=None,
            background_color="#fff",
            subject=_Subject("Maths"),
            detention=False,
        )
        base.update(over)
        return _Lesson(**base)

    def test_basic_fields(self, daemon):
        out = daemon.build_cours_data(self._lesson())
        assert out["id"] == "L1"
        assert out["heure"] == "0830"
        assert out["heure_fin"] == "0930"
        assert out["date"] == "31/05/2026"
        assert out["Professeur"] == "M. Dupont"
        assert out["salle"] == "B12"
        assert out["cours"] == "Maths"
        assert out["annulation"] is False

    def test_detention_label(self, daemon):
        out = daemon.build_cours_data(self._lesson(detention=True))
        assert out["cours"] == "RETENUE"

    def test_no_subject_is_repas(self, daemon):
        out = daemon.build_cours_data(self._lesson(subject=None))
        assert out["cours"] == "Repas"


# ── detect_next_evaluations ───────────────────────────────────────────────────
class _Homework:
    def __init__(self, description, subject_name, date):
        self.description = description
        self.subject = _Subject(subject_name)
        self.date = date


class TestDetectNextEvaluations:
    def test_empty_returns_neutral(self, daemon):
        out = daemon.detect_next_evaluations([])
        assert out["prochain_DS_matiere"] == ""
        assert out["prochain_DS_dans_jours"] == -1
        assert out["prochains_DS_brut"] == []

    def test_detects_keyword(self, daemon):
        today = datetime.date.today()
        hw = [_Homework("Contrôle chapitre 5", "Maths", today + datetime.timedelta(days=3))]
        out = daemon.detect_next_evaluations(hw)
        assert out["prochain_DS_matiere"] == "Maths"
        assert out["prochain_DS_dans_jours"] == 3

    def test_ignores_non_eval(self, daemon):
        today = datetime.date.today()
        hw = [_Homework("Lire le chapitre 2", "Français", today + datetime.timedelta(days=1))]
        out = daemon.detect_next_evaluations(hw)
        assert out["prochain_DS_matiere"] == ""

    def test_ignores_past_dates(self, daemon):
        today = datetime.date.today()
        hw = [_Homework("DS révisions", "Histoire", today - datetime.timedelta(days=2))]
        out = daemon.detect_next_evaluations(hw)
        assert out["prochain_DS_matiere"] == ""

    def test_sorted_by_date(self, daemon):
        today = datetime.date.today()
        hw = [
            _Homework("Examen final", "SVT", today + datetime.timedelta(days=10)),
            _Homework("Évaluation rapide", "Physique", today + datetime.timedelta(days=2)),
        ]
        out = daemon.detect_next_evaluations(hw)
        assert out["prochain_DS_matiere"] == "Physique"
        assert len(out["prochains_DS_brut"]) == 2

    def test_max_keep(self, daemon):
        today = datetime.date.today()
        hw = [
            _Homework("Test", "Mat%d" % i, today + datetime.timedelta(days=i + 1))
            for i in range(10)
        ]
        out = daemon.detect_next_evaluations(hw, max_keep=3)
        assert len(out["prochains_DS_brut"]) == 3


# ── messages (tri + agrégats) ─────────────────────────────────────────────────
class _Msg:
    def __init__(self, content):
        self.content = content


class _Discussion:
    def __init__(self, subject, creator, date, unread, content):
        self.subject = subject
        self.creator = creator
        self.date = date
        self.unread = unread
        self.participants = [creator]
        self.messages = [_Msg(content)]


class _Client:
    def __init__(self, discussions):
        self._discussions = discussions

    def discussions(self):
        return self._discussions


class TestMessages:
    def test_no_discussions(self, daemon):
        out = daemon.messages(_Client([]))
        assert out["Nb_messages"] == 0
        assert out["Nb_messages_non_lus"] == 0

    def test_attribute_error_returns_empty(self, daemon):
        class Broken:
            pass

        out = daemon.messages(Broken())
        assert out["Nb_messages"] == 0

    def test_aggregates_and_sort(self, daemon):
        # A (lu, ancien), B (non lu, ancien), C (lu, récent), D (non lu, récent)
        d = datetime.datetime
        discs = [
            _Discussion("A", "Prof A", d(2026, 1, 15, 9, 0), False, "contenu A"),
            _Discussion("B", "Prof B", d(2026, 1, 10, 9, 0), True, "contenu B"),
            _Discussion("C", "Prof C", d(2026, 2, 2, 9, 0), False, "contenu C"),
            _Discussion("D", "Prof D", d(2026, 2, 5, 9, 0), True, "contenu D"),
        ]
        out = daemon.messages(_Client(discs))
        assert out["Nb_messages"] == 4
        assert out["Nb_messages_non_lus"] == 2
        # « dernier message » = le plus récent chronologiquement (D, 5 février)
        assert out["dernier_message_sujet"] == "D"
        # Tri d'affichage : non-lus d'abord (D puis B), puis lus (C puis A)
        order = [m["subject"] for m in out["messages_brut"]]
        assert order == ["D", "B", "C", "A"]

    def test_internal_sort_key_removed(self, daemon):
        d = datetime.datetime
        discs = [_Discussion("X", "P", d(2026, 1, 1, 8, 0), False, "c")]
        out = daemon.messages(_Client(discs))
        assert "_date_sort" not in out["messages_brut"][0]

    def test_extract_truncated(self, daemon):
        d = datetime.datetime
        long_content = "z" * 400
        discs = [_Discussion("X", "P", d(2026, 1, 1, 8, 0), False, long_content)]
        out = daemon.messages(_Client(discs))
        assert len(out["messages_brut"][0]["extrait"]) <= 200
