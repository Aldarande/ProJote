"""Tests des collecteurs d'onglets Pronote.

Ces douze fonctions sont le cœur du plugin : elles transforment les objets
pronotepy en la charge que Jeedom consomme. Jusqu'ici elles n'étaient couvertes
qu'indirectement — les tests portaient sur les fonctions de mise en forme, pas
sur les collecteurs eux-mêmes.

Ils sont écrits ici **avant** le découpage du démon, volontairement : ils
décrivent le contrat de sortie tel qu'il est aujourd'hui, et c'est ce contrat
que le déplacement du code ne doit pas modifier. Chaque clé vérifiée ci-dessous
est lue nommément par `jeeProJote.php` ou par le widget ; en renommer une, ou
en changer le type, viderait une commande ou une section à l'écran.

Les objets pronotepy sont remplacés par des doublures minimales : seuls les
attributs réellement lus par les collecteurs sont fournis. Une doublure qui
diverge du vrai objet se verrait immédiatement, les collecteurs n'accédant à
rien d'autre.
"""

import datetime

import pytest


# ── Doublures ───────────────────────────────────────────────────────────────


class _Absence:
    def __init__(self, id_, debut, fin, justifie=False, heures="2h", jours=0, raisons=None):
        self.id = id_
        self.from_date = debut
        self.to_date = fin
        self.justified = justifie
        self.hours = heures
        self.days = jours
        self.reasons = raisons or []


class _Retard:
    def __init__(self, id_, date, justifie=False, minutes=10, justification="", raisons=None):
        self.id = id_
        self.date = date
        self.justified = justifie
        self.minutes = minutes
        self.justification = justification
        self.reasons = raisons or []


class _Punition:
    def __init__(self, id_, donne, nature="Retenue", raisons=None):
        self.id = id_
        self.given = donne
        self.nature = nature
        self.reasons = raisons or ["Bavardage"]
        self.giver = "M. Dupont"
        self.circumstances = ""
        self.exclusion = False
        self.during_lesson = False
        self.homework = ""
        self.homework_documents = []
        self.schedule = []
        self.schedulable = False
        self.duration = None


class _Periode:
    """Période Pronote : ne porte que les listes lues par les collecteurs."""

    def __init__(self, nom="Trimestre 1", absences=None, retards=None, punitions=None,
                 debut=None, fin=None, explose=None):
        self.name = nom
        self._absences = absences or []
        self._retards = retards or []
        self._punitions = punitions or []
        self.start = debut or datetime.datetime(2026, 9, 1)
        self.end = fin or datetime.datetime(2026, 12, 20)
        self._explose = explose

    def _peut_etre_explose(self):
        if self._explose is not None:
            raise self._explose

    @property
    def absences(self):
        self._peut_etre_explose()
        return self._absences

    @property
    def delays(self):
        self._peut_etre_explose()
        return self._retards

    @property
    def punishments(self):
        self._peut_etre_explose()
        return self._punitions


class _Client:
    def __init__(self, periodes=None, periodes_explose=None):
        self._periodes = periodes or []
        self._periodes_explose = periodes_explose

    @property
    def periods(self):
        if self._periodes_explose is not None:
            raise self._periodes_explose
        return self._periodes


@pytest.fixture
def collecteurs(daemon):
    """Démon avec la mémoire des refus de l'onglet Présence remise à zéro."""
    daemon._presence_refusee.clear()
    return daemon


def _dt(jour, heure=8, minute=0):
    return datetime.datetime(2026, 9, jour, heure, minute)


# ── Absences ────────────────────────────────────────────────────────────────


def test_absences_liste_vide(collecteurs):
    data = collecteurs.absences(_Client([_Periode()]))
    assert data == {"absence": [], "nb_absences": 0, "derniere_absence": []}


def test_absences_format_des_champs(collecteurs):
    absence = _Absence(1, _dt(10, 8), _dt(10, 10), justifie=True, heures="2h",
                       jours=0, raisons=["Maladie", "RDV"])
    data = collecteurs.absences(_Client([_Periode(absences=[absence])]))

    assert data["nb_absences"] == 1
    assert data["absence"][0] == {
        "id": 1,
        "date_debut": "10/09/26 08:00",
        "date_fin": "10/09/26 10:00",
        "justifie": True,
        "nb_heures": "2h",
        "nb_jours": 0,
        # Les motifs multiples sont aplatis : le widget affiche une seule ligne.
        "raison": "Maladie, RDV",
    }


def test_absences_la_plus_recente_en_tete(collecteurs):
    ancienne = _Absence(1, _dt(2), _dt(2, 10))
    recente = _Absence(2, _dt(20), _dt(20, 10))
    data = collecteurs.absences(_Client([_Periode(absences=[ancienne, recente])]))

    assert [a["id"] for a in data["absence"]] == [2, 1]
    # derniere_absence est une LISTE d'un élément : le widget itère dessus.
    assert data["derniere_absence"] == [data["absence"][0]]


def test_absences_dedoublonnees_entre_periodes(collecteurs):
    """Une absence à cheval sur deux périodes est renvoyée par les deux.

    Sans déduplication par identifiant, elle serait comptée deux fois dans
    Nb_absences — une commande historisée, donc un graphique faux.
    """
    absence = _Absence(7, _dt(10), _dt(10, 10))
    client = _Client([_Periode("T1", absences=[absence]),
                      _Periode("T2", absences=[absence])])
    data = collecteurs.absences(client)
    assert data["nb_absences"] == 1


def test_absences_periodes_inaccessibles(collecteurs):
    data = collecteurs.absences(_Client(periodes_explose=RuntimeError("boum")))
    assert data["nb_absences"] == 0
    assert "boum" in data["error"]


def test_absences_onglet_presence_refuse(collecteurs):
    """Un refus d'accès à l'onglet Présence rend une liste vide, sans lever.

    pronotepy répond à ce refus par une ré-authentification complète avant de
    rejouer : trois collecteurs passent par cet onglet, d'où trois
    authentifications inutiles si le refus n'est pas retenu.
    """
    refus = Exception("Accès refusé")
    client = _Client([_Periode(absences=[_Absence(1, _dt(3), _dt(3, 9))], explose=refus)])
    data = collecteurs.absences(client)
    assert data["absence"] == []


# ── Retards ─────────────────────────────────────────────────────────────────


def test_retards_format_des_champs(collecteurs):
    retard = _Retard(3, _dt(12, 9, 5), justifie=True, minutes=15,
                     justification="Bus", raisons=["Transport"])
    data = collecteurs.retards(_Client([_Periode(retards=[retard])]))

    assert data["nb_retard"] == 1
    assert data["retard"][0] == {
        "id": 3,
        "date": "12/09/26 09:05",
        "justifie": True,
        "nb_minutes": 15,
        "justification": "Bus",
        "raison": "Transport",
    }
    assert data["dernier_retard"] == [data["retard"][0]]


def test_retards_le_plus_recent_en_tete(collecteurs):
    client = _Client([_Periode(retards=[_Retard(1, _dt(2)), _Retard(2, _dt(25))])])
    data = collecteurs.retards(client)
    assert [r["id"] for r in data["retard"]] == [2, 1]


def test_retards_justification_absente(collecteurs):
    """None devient une chaîne vide : le widget concatène sans vérifier."""
    retard = _Retard(1, _dt(5), justification=None, raisons=None)
    data = collecteurs.retards(_Client([_Periode(retards=[retard])]))
    assert data["retard"][0]["justification"] == ""
    assert data["retard"][0]["raison"] == ""


def test_retards_periodes_inaccessibles(collecteurs):
    data = collecteurs.retards(_Client(periodes_explose=RuntimeError("zut")))
    assert data["nb_retard"] == 0
    assert "zut" in data["error"]


# ── Punitions ───────────────────────────────────────────────────────────────


def test_punitions_format_des_champs(collecteurs):
    punition = _Punition(5, datetime.date(2026, 9, 14), nature="Retenue",
                         raisons=["Bavardage", "Retard"])
    data = collecteurs.punitions(_Client([_Periode(punitions=[punition])]))

    assert data["Nb_Punitions"] == 1
    entree = data["punition"][0]
    assert entree["id"] == 5
    assert entree["type"] == "Retenue"
    assert entree["raison"] == "Bavardage, Retard"
    assert entree["donneur"] == "M. Dupont"
    assert entree["date"] == "14/09/2026"
    assert entree["date_court"] == "14/09"
    assert data["derniere_punition"] == [entree]


def test_punitions_date_et_datetime_melangees(collecteurs):
    """Pronote renvoie tantôt une date, tantôt un datetime.

    Les trier sans précaution lève « can't compare datetime to date ».
    """
    punitions = [
        _Punition(1, datetime.date(2026, 9, 3)),
        _Punition(2, datetime.datetime(2026, 9, 21, 14, 0)),
    ]
    data = collecteurs.punitions(_Client([_Periode(punitions=punitions)]))
    assert [p["id"] for p in data["punition"]] == [2, 1]


def test_punitions_dedoublonnees_entre_periodes(collecteurs):
    punition = _Punition(9, datetime.date(2026, 9, 10))
    client = _Client([_Periode("T1", punitions=[punition]),
                      _Periode("T2", punitions=[punition])])
    assert collecteurs.punitions(client)["Nb_Punitions"] == 1


def test_punitions_periodes_inaccessibles(collecteurs):
    data = collecteurs.punitions(_Client(periodes_explose=RuntimeError("non")))
    assert data["Nb_Punitions"] == 0
    assert "non" in data["error"]


# ── Évaluations ─────────────────────────────────────────────────────────────


class _Matiere:
    def __init__(self, nom):
        self.name = nom


class _Acquisition:
    def __init__(self, nom, niveau):
        self.order = 1
        self.name = nom
        self.name_id = 10
        self.abbreviation = "ABR"
        self.level = niveau
        self.coefficient = 1
        self.domain = "D1"
        self.domain_id = 2
        self.pillar = "P1"
        self.pillar_id = 3


class _Evaluation:
    def __init__(self, id_, nom="Contrôle"):
        self.id = id_
        self.name = nom
        self.domain = "Sciences"
        self.teacher = "Mme Martin"
        self.subject = _Matiere("Physique")
        self.date = datetime.date(2026, 9, 12)
        self.acquisitions = [_Acquisition("Savoir mesurer", "Très bonne maîtrise")]
        self.description = "Chapitre 2"
        self.paliers = []
        self.coefficient = 2


class _ClientEval:
    def __init__(self, evaluations=None, explose=None):
        self._evaluations = evaluations
        self._explose = explose

    @property
    def current_period(self):
        if self._explose is not None:
            raise self._explose
        parent = self

        class _P:
            evaluations = parent._evaluations

        return _P()


def test_evaluations_renvoie_une_liste_pas_un_dictionnaire(collecteurs):
    """Contrat inhabituel, et lu tel quel par jeeProJote.php.

    Le PHP a longtemps cherché $result['Competences']['evaluations'], qui
    n'existe pas : l'onglet Compétences du widget restait vide. Le collecteur
    renvoie la liste elle-même.
    """
    resultat = collecteurs.evaluations(_ClientEval([_Evaluation(1)]))
    assert isinstance(resultat, list)
    assert resultat[0]["nom"] == "Contrôle"
    assert resultat[0]["Sujet"] == "Physique"
    assert resultat[0]["date"] == "12/09/2026"


def test_evaluations_acquisitions_converties(collecteurs):
    """Les objets d'acquisition ne sont pas sérialisables tels quels."""
    resultat = collecteurs.evaluations(_ClientEval([_Evaluation(1)]))
    acquisition = resultat[0]["acquisitions"][0]
    assert acquisition["name"] == "Savoir mesurer"
    assert acquisition["level"] == "Très bonne maîtrise"


def test_evaluations_sans_evaluation(collecteurs):
    assert collecteurs.evaluations(_ClientEval([])) == {"evaluations": []}


def test_evaluations_periode_inaccessible(collecteurs):
    """Le chemin d'erreur rend un dictionnaire, lui : le PHP tolère les deux."""
    resultat = collecteurs.evaluations(_ClientEval(explose=RuntimeError("pas d'accès")))
    assert resultat["evaluations"] == []
    assert "pas d'accès" in resultat["error"]


# ── Notifications ───────────────────────────────────────────────────────────


class _Notification:
    def __init__(self, titre, debut, lu=False):
        self.title = titre
        self.author = "La Direction"
        self.start_date = debut
        self.creation_date = debut
        self.category = "Information"
        self.read = lu
        self.content = "Corps du message"


class _ClientNotif:
    def __init__(self, notifications):
        self._notifications = notifications

    def information_and_surveys(self):
        return self._notifications


def test_notifications_la_plus_recente_en_tete(collecteurs):
    client = _ClientNotif([
        _Notification("Ancienne", _dt(2)),
        _Notification("Récente", _dt(20)),
    ])
    data = collecteurs.notifications(client)

    assert [n["sujet"] for n in data["Notification"]] == ["Récente", "Ancienne"]
    assert data["dernier_Notification"] == [data["Notification"][0]]
    assert data["Notification"][0]["creation"] == "20/09"
    assert data["Notification"][0]["auteur"] == "La Direction"
    assert data["Notification"][0]["lu"] is False


def test_notifications_liste_vide(collecteurs):
    data = collecteurs.notifications(_ClientNotif([]))
    assert data == {"Notification": [], "dernier_Notification": []}


# ── Aucune attente sur un relevé vide ───────────────────────────────────────
#
# Trois collecteurs appelaient time.sleep(5) sur leur chemin *nominal* : devoirs
# sans échéance (courant un week-end), aucune notification publiée, aucune
# punition — l'état normal d'un élève. Un enfant sans rien à signaler payait
# donc quinze secondes d'attente par cycle, et trois enfants quarante-cinq, sur
# le temps du worker unique et de son délai d'abandon. Quatre autres attendaient
# cinq secondes dans un gestionnaire d'erreur qui rendait la main juste après :
# aucune n'était un délai de reprise, rien n'étant rejoué.


def _duree(fonction, *args):
    import time as _time

    debut = _time.monotonic()
    fonction(*args)
    return _time.monotonic() - debut


SEUIL = 1.0  # très au-dessus du temps réel attendu, bien en deçà des 5 s retirées


def test_punitions_vides_sans_attente(collecteurs):
    assert _duree(collecteurs.punitions, _Client([_Periode()])) < SEUIL


def test_notifications_vides_sans_attente(collecteurs):
    assert _duree(collecteurs.notifications, _ClientNotif([])) < SEUIL


def test_absences_en_erreur_sans_attente(collecteurs):
    client = _Client(periodes_explose=RuntimeError("panne"))
    assert _duree(collecteurs.absences, client) < SEUIL


def test_evaluations_en_erreur_sans_attente(collecteurs):
    client = _ClientEval(explose=RuntimeError("panne"))
    assert _duree(collecteurs.evaluations, client) < SEUIL


def test_aucune_attente_residuelle_dans_les_collecteurs():
    """Seuls le watchdog et la boucle de lecture du socket peuvent attendre."""
    import os

    chemin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources", "ProJoted", "ProJoted.py",
    )
    with open(chemin, encoding="utf-8") as f:
        source = f.read()
    assert "time.sleep(5)" not in source


# ── Moyennes par période : ce que PRONOTE renvoie qui n'est pas un nombre ───
#
# Relevé le 19 septembre 2026 sur le compte de démonstration : la période
# « Hors période » — un fourre-tout que PRONOTE ajoute en queue de liste —
# renvoie « |5 » comme moyenne, pour l'élève comme pour la classe. Laissée
# passer, cette valeur traversait le démon, le PHP et le widget, et s'affichait
# telle quelle sur le tableau de bord : « |5/20 » en guise de moyenne générale.
# On la prend d'abord pour un caractère rogné, alors que c'est la donnée.


@pytest.mark.parametrize(
    "brute, attendu",
    [
        ("14.87", "14.87"),
        ("12,5", "12,5"),
        ("0", "0"),
        ("20", "20"),
        # Sentinelle documentée de PRONOTE.
        ("-1", ""),
        # Le cas réellement rencontré.
        ("|5", ""),
        ("", ""),
        ("   ", ""),
        (None, ""),
        ("Non noté", ""),
        ("N/A", ""),
    ],
)
def test_seules_les_vraies_moyennes_passent(brute, attendu):
    import collecteurs as module_collecteurs

    assert (
        module_collecteurs._moyenne_utilisable(brute, "Trimestre 1", "élève") == attendu
    )


class _PeriodeAvecMoyenne:
    def __init__(self, nom, eleve, classe):
        self.name = nom
        self.overall_average = eleve
        self.class_overall_average = classe
        self.grades = []
        self.start = datetime.datetime(2026, 9, 1)
        self.end = datetime.datetime(2026, 12, 20)


def test_la_periode_fourre_tout_n_entre_pas_dans_la_charge(collecteurs):
    """Le tableau transmis à Jeedom ne doit porter que des moyennes exploitables."""
    client = _Client([
        _PeriodeAvecMoyenne("Trimestre 1", "14.87", "11.65"),
        _PeriodeAvecMoyenne("Hors période", "|5", "|5"),
    ])
    data = collecteurs.notes(client)

    periodes = {m["periode"]: m for m in data["moyennes_periodes"]}
    assert "Trimestre 1" in periodes
    assert periodes["Trimestre 1"]["moyenne_eleve"] == "14.87"
    assert "Hors période" not in periodes, "une moyenne non numérique a été transmise"


# ── Une note, une seule entrée ──────────────────────────────────────────────
#
# PRONOTE publie plusieurs découpages qui se recouvrent — trimestres, semestres,
# « Année continue » — et rend la même note sous chacun de ceux qui la
# contiennent. Relevé le 23 septembre 2026 sur un compte de démonstration :
# 104 entrées pour 53 notes réelles, chacune affichée deux fois dans le widget,
# et le compteur de nouveautés qui comptait double.


class _Note:
    def __init__(self, identifiant, matiere="FRANCAIS", valeur="14"):
        self.id = identifiant
        self.grade = valeur
        self.out_of = "20"
        self.coefficient = "1"
        self.average = "11.72"
        self.max = "18"
        self.min = "5"
        self.date = datetime.date(2026, 9, 18)
        self.comment = ""
        self.is_bonus = False
        self.is_optionnal = False
        self.subject = type("M", (), {"name": matiere})()


class _PeriodeAvecNotes:
    def __init__(self, nom, notes):
        self.name = nom
        self.grades = notes
        self.overall_average = None
        self.class_overall_average = None
        self.start = datetime.datetime(2026, 9, 1)
        self.end = datetime.datetime(2026, 12, 20)


def test_une_note_rendue_par_deux_periodes_n_apparait_qu_une_fois(collecteurs):
    """Le cas réel : la même note sous « Trimestre 1 » et sous « Année continue »."""
    note = _Note("33#une-note")
    client = _Client([
        _PeriodeAvecNotes("Trimestre 1", [note]),
        _PeriodeAvecNotes("Année continue", [note]),
    ])

    data = collecteurs.notes(client)

    assert len(data["note"]) == 1, "la note est comptée deux fois"


def test_la_periode_retenue_est_la_plus_precise(collecteurs):
    """`client.periods` liste les trimestres avant les regroupements larges."""
    note = _Note("33#une-note")
    client = _Client([
        _PeriodeAvecNotes("Trimestre 1", [note]),
        _PeriodeAvecNotes("Année continue", [note]),
    ])

    data = collecteurs.notes(client)

    assert data["note"][0]["periode"] == "Trimestre 1"


def test_deux_notes_distinctes_restent_deux(collecteurs):
    """Le dédoublonnage ne doit pas avaler des notes réellement différentes."""
    client = _Client([
        _PeriodeAvecNotes("Trimestre 1", [_Note("33#a"), _Note("33#b", valeur="9")]),
    ])

    data = collecteurs.notes(client)

    assert len(data["note"]) == 2


def test_une_note_sans_identifiant_passe_quand_meme(collecteurs):
    """Mieux vaut un doublon qu'une note perdue si PRONOTE n'expose pas d'id."""
    sans_id = _Note(None)
    client = _Client([_PeriodeAvecNotes("Trimestre 1", [sans_id])])

    data = collecteurs.notes(client)

    assert len(data["note"]) == 1
