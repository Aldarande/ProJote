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


# ── compute_moyenne_generale (F3) ─────────────────────────────────────────────
def _note(note, sur="20", coeff="1", cours="Maths"):
    return {"note": note, "sur": sur, "coeff": coeff, "cours": cours}


class TestComputeMoyenneGenerale:
    def test_empty_returns_none(self, daemon):
        assert daemon.compute_moyenne_generale([]) is None
        assert daemon.compute_moyenne_generale(None) is None

    def test_single_note(self, daemon):
        assert daemon.compute_moyenne_generale([_note("10", "20", "1")]) == 10.0

    def test_normalized_to_20(self, daemon):
        # 5/10 = 10/20
        assert daemon.compute_moyenne_generale([_note("5", "10", "1")]) == 10.0

    def test_coefficient_weighting(self, daemon):
        # (10*1 + 20*3) / (1+3) = 70/4 = 17.5
        notes = [_note("10", "20", "1"), _note("20", "20", "3")]
        assert daemon.compute_moyenne_generale(notes) == 17.5

    def test_comma_decimal(self, daemon):
        assert daemon.compute_moyenne_generale([_note("12,5", "20", "1")]) == 12.5

    def test_excludes_non_numeric(self, daemon):
        notes = [_note("Absent", "20", "1"), _note("15", "20", "1")]
        assert daemon.compute_moyenne_generale(notes) == 15.0

    def test_excludes_zero_denominator(self, daemon):
        notes = [_note("10", "0", "1"), _note("12", "20", "1")]
        assert daemon.compute_moyenne_generale(notes) == 12.0

    def test_excludes_zero_coefficient(self, daemon):
        # coeff 0 = bonus/optionnel → exclu
        notes = [_note("20", "20", "0"), _note("10", "20", "1")]
        assert daemon.compute_moyenne_generale(notes) == 10.0


# ── detect_subject_trends (F3) ────────────────────────────────────────────────
class TestDetectSubjectTrends:
    def test_empty(self, daemon):
        out = daemon.detect_subject_trends([])
        assert out["matiere_en_baisse"] == ""
        assert out["matiere_en_baisse_detail"] == []

    def test_below_min_notes_not_flagged(self, daemon):
        # 3 notes seulement (< min_notes=4)
        notes = [_note("8"), _note("8"), _note("16")]
        out = daemon.detect_subject_trends(notes)
        assert out["matiere_en_baisse"] == ""

    def test_falling_subject_flagged(self, daemon):
        # note_list = plus récent en premier : récentes basses (8,8), anciennes hautes (16,16)
        notes = [
            _note("8", cours="Maths"),
            _note("8", cours="Maths"),
            _note("16", cours="Maths"),
            _note("16", cours="Maths"),
        ]
        out = daemon.detect_subject_trends(notes)
        assert out["matiere_en_baisse"] == "Maths"
        d = out["matiere_en_baisse_detail"][0]
        assert d["ancienne_moyenne"] == 16.0
        assert d["recente_moyenne"] == 8.0
        assert d["delta"] == -8.0

    def test_improving_subject_not_flagged(self, daemon):
        # récentes hautes, anciennes basses → progression, pas de flag
        notes = [
            _note("17", cours="Physique"),
            _note("18", cours="Physique"),
            _note("9", cours="Physique"),
            _note("8", cours="Physique"),
        ]
        out = daemon.detect_subject_trends(notes)
        assert out["matiere_en_baisse"] == ""

    def test_stable_subject_not_flagged(self, daemon):
        notes = [_note("14"), _note("14"), _note("15"), _note("15")]
        out = daemon.detect_subject_trends(notes)
        assert out["matiere_en_baisse"] == ""

    def test_multiple_subjects_sorted_by_drop(self, daemon):
        # Maths chute de 4, Histoire chute de 8 → Histoire en premier
        notes = [
            _note("12", cours="Maths"), _note("12", cours="Maths"),
            _note("16", cours="Maths"), _note("16", cours="Maths"),
            _note("6", cours="Histoire"), _note("6", cours="Histoire"),
            _note("14", cours="Histoire"), _note("14", cours="Histoire"),
        ]
        out = daemon.detect_subject_trends(notes)
        subjects = [d["matiere"] for d in out["matiere_en_baisse_detail"]]
        assert subjects == ["Histoire", "Maths"]
        assert out["matiere_en_baisse"] == "Histoire · Maths"


# ── P3 : détection des nouveautés (deltas) ────────────────────────────────────
class TestNewItemLabels:
    def test_note_label_full(self, daemon):
        note = {"cours": "Maths", "note_sur": "16 / 20", "commentaire": "DS trigonométrie"}
        assert daemon.format_new_note_label(note) == "Maths : 16 / 20 — DS trigonométrie"

    def test_note_label_no_comment(self, daemon):
        note = {"cours": "Physique", "note": "12", "sur": "20"}
        assert daemon.format_new_note_label(note) == "Physique : 12/20"

    def test_note_label_missing_subject(self, daemon):
        assert daemon.format_new_note_label({"note": "8", "sur": "20"}) == "? : 8/20"

    def test_devoir_label_full(self, daemon):
        dv = {"title": "Maths", "date": "12/03", "description": "exercices p.42"}
        assert daemon.format_new_devoir_label(dv) == "Maths (12/03) : exercices p.42"

    def test_devoir_label_no_desc(self, daemon):
        assert daemon.format_new_devoir_label({"title": "Anglais", "date": "05/04"}) == "Anglais (05/04)"


class TestComputeDeltas:
    def _note(self, id, cours="Maths", note="15"):
        return {"id": id, "cours": cours, "date": "01/03", "note": note, "sur": "20",
                "note_sur": note + "/20", "commentaire": ""}

    def test_first_run_no_deltas(self, daemon):
        notes = [self._note(1), self._note(2)]
        deltas, index = daemon.compute_deltas({}, notes, [], [], [])
        assert deltas["nouvelles_notes"] == 0
        assert deltas["derniere_nouvelle_note"] == ""
        # La baseline est enregistrée pour le prochain passage.
        assert len(index["notes"]) == 2

    def test_detects_new_note(self, daemon):
        seen = {"notes": ["1"], "devoirs": [], "punitions": [], "absences": []}
        notes = [self._note(2, cours="Histoire", note="17"), self._note(1)]
        deltas, index = daemon.compute_deltas(seen, notes, [], [], [])
        assert deltas["nouvelles_notes"] == 1
        assert deltas["derniere_nouvelle_note"] == "Histoire : 17/20"
        assert set(index["notes"]) == {"1", "2"}

    def test_no_new_when_all_seen(self, daemon):
        seen = {"notes": ["1", "2"], "devoirs": [], "punitions": [], "absences": []}
        notes = [self._note(1), self._note(2)]
        deltas, _ = daemon.compute_deltas(seen, notes, [], [], [])
        assert deltas["nouvelles_notes"] == 0
        assert deltas["derniere_nouvelle_note"] == ""

    def test_detects_new_devoir_by_signature(self, daemon):
        seen = {"notes": [], "devoirs": ["d:12/03|Maths|ex p.10"], "punitions": [], "absences": []}
        devoirs = [
            {"date": "13/03", "title": "Physique", "description": "TP"},
            {"date": "12/03", "title": "Maths", "description": "ex p.10"},
        ]
        deltas, index = daemon.compute_deltas(seen, [], devoirs, [], [])
        assert deltas["nouveaux_devoirs"] == 1
        assert deltas["dernier_nouveau_devoir"] == "Physique (13/03) : TP"

    def test_counts_punitions_and_absences(self, daemon):
        seen = {"notes": [], "devoirs": [], "punitions": ["p:5"], "absences": []}
        punitions = [{"id": 5}, {"id": 6}]
        absences = [{"id": 9}]
        deltas, _ = daemon.compute_deltas(seen, [], [], punitions, absences)
        assert deltas["nouvelles_punitions"] == 1
        assert deltas["nouvelles_absences"] == 1


# ── P4 : circuit breaker avec backoff exponentiel ─────────────────────────────
class TestCircuitBreaker:
    def _reset(self, daemon, eq="42"):
        daemon.failed_attempts.pop(eq, None)
        return eq

    def test_allows_under_threshold(self, daemon):
        eq = self._reset(daemon)
        # 3 échecs max autorisés (max_attempts=3) → toujours True jusqu'au seuil
        assert daemon.check_and_update_failed_attempts(eq, increment=True) is True
        assert daemon.check_and_update_failed_attempts(eq, increment=True) is True
        assert daemon.check_and_update_failed_attempts(eq, increment=True) is True

    def test_opens_after_threshold(self, daemon):
        eq = self._reset(daemon)
        for _ in range(3):
            daemon.check_and_update_failed_attempts(eq, increment=True)
        # 4e échec → circuit ouvert
        assert daemon.check_and_update_failed_attempts(eq, increment=True) is False

    def test_backoff_grows(self, daemon):
        eq = self._reset(daemon)
        for _ in range(4):  # ouvre le circuit (count=4)
            daemon.check_and_update_failed_attempts(eq, increment=True)
        first_block = daemon.failed_attempts[eq]["blocked_until"]
        # Encore bloqué tant que le backoff n'est pas écoulé
        assert daemon.check_and_update_failed_attempts(eq, increment=False) is False
        # Un échec supplémentaire repousse l'échéance plus loin (backoff plus long)
        daemon.check_and_update_failed_attempts(eq, increment=True)
        assert daemon.failed_attempts[eq]["blocked_until"] >= first_block

    def test_reset_after_cooldown(self, daemon):
        eq = self._reset(daemon)
        for _ in range(4):
            daemon.check_and_update_failed_attempts(eq, increment=True)
        # Simuler la fin du cooldown
        daemon.failed_attempts[eq]["blocked_until"] = 0
        assert daemon.check_and_update_failed_attempts(eq, increment=False) is True
        assert daemon.failed_attempts[eq]["count"] == 0


# ── P4 : _run_with_timeout ────────────────────────────────────────────────────
class TestRunWithTimeout:
    def test_completes_in_time(self, daemon):
        done = {}
        assert daemon._run_with_timeout(lambda: done.setdefault("ok", 1), 5) is True
        assert done.get("ok") == 1

    def test_times_out(self, daemon):
        import time as _t
        assert daemon._run_with_timeout(lambda: _t.sleep(2), 0.2) is False

    def test_propagates_exception(self, daemon):
        import pytest as _pytest

        def boom():
            raise ValueError("boom")

        with _pytest.raises(ValueError):
            daemon._run_with_timeout(boom, 5)
