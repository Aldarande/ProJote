"""Tests de la collecte cadencée et isolée (v1.5.0).

Le démon interrogeait les douze onglets à chaque cycle, sans distinction, et la
moindre exception inattendue d'un collecteur emportait le cycle entier depuis le
gestionnaire de process_message : tout ce qui avait été relevé avant était jeté,
et Jeedom ne recevait qu'une erreur.

Mesuré le 17 septembre 2026 sur le compte de démonstration parent, un cycle
complet coûtait 113 requêtes HTTP et 5 ré-authentifications, dont 28 requêtes et
3 ré-authentifications pour les notifications et la messagerie seules — des
contenus qui ne sont pas à la minute.

Deux règles en découlent, et ces tests les gardent :

* un onglet sauté ou en échec **reste présent dans la charge**, avec sa dernière
  valeur connue. jeeProJote.php reconstruit le widget entièrement à partir de la
  charge : une clé manquante viderait la section correspondante à l'écran ;
* un onglet qui tombe ne coûte que lui-même.
"""

import pytest

import cadence


@pytest.fixture
def collecte(daemon):
    """Démon avec un cache de collecte vierge."""
    daemon._cache_collecte.clear()
    return daemon


def _appels(compteur, cle, valeur=None, explose=False):
    """Fabrique un collecteur qui compte ses appels."""

    def _fn(_client):
        compteur[cle] = compteur.get(cle, 0) + 1
        if explose:
            raise RuntimeError("panne simulée sur " + cle)
        return valeur if valeur is not None else {"valeur": cle}

    return _fn


def _table(daemon, monkeypatch, collecteurs):
    """Remplace la table des onglets par celle du test."""
    monkeypatch.setattr(daemon, "_collecteurs", lambda message: collecteurs)


# ── Cadences ────────────────────────────────────────────────────────────────


def test_cadence_par_defaut_est_chaque_cycle():
    assert cadence.periode("Onglet inconnu") == 0
    assert cadence.doit_collecter("Onglet inconnu", 1000.0, 1000.5) is True


def test_emploi_du_temps_reste_a_chaque_cycle():
    """45 requêtes par cycle, assumées : une annulation de cours doit se voir."""
    assert cadence.periode("Emploi_du_temps") == 0


@pytest.mark.parametrize("cle", ["Notifications", "Messages"])
def test_notifications_et_messagerie_sont_espacees(cle):
    assert cadence.periode(cle) == cadence.TROIS_HEURES


def test_un_onglet_jamais_releve_est_toujours_collecte():
    assert cadence.doit_collecter("Menus", None, 5000.0) is True


def test_onglet_encore_frais_est_saute():
    releve = 10000.0
    assert cadence.doit_collecter("Menus", releve, releve + 60) is False


def test_onglet_perime_est_recollecte():
    releve = 10000.0
    assert cadence.doit_collecter("Menus", releve, releve + cadence.DOUZE_HEURES) is True


def test_les_onglets_gratuits_ne_sont_pas_espaces():
    """Périodes, retards et punitions ne coûtent aucune requête : rien à gagner."""
    for cle in ("Periodes", "Retards", "Punitions"):
        assert cadence.periode(cle) == 0


# ── Isolation des échecs ────────────────────────────────────────────────────


def test_un_collecteur_en_panne_n_emporte_pas_les_autres(collecte, monkeypatch):
    compteur = {}
    _table(
        collecte,
        monkeypatch,
        (
            ("Notes", "les notes", _appels(compteur, "Notes")),
            ("Devoirs", "les devoirs", _appels(compteur, "Devoirs", explose=True)),
            ("Absences", "les absences", _appels(compteur, "Absences")),
        ),
    )
    charge = {}
    statuts = collecte.collecter(object(), 7, {}, charge)

    assert statuts["Devoirs"] == cadence.ECHEC
    assert statuts["Notes"] == cadence.FRAIS
    # L'onglet suivant a bien été relevé : la panne ne s'est pas propagée.
    assert statuts["Absences"] == cadence.FRAIS
    assert charge["Absences"] == {"valeur": "Absences"}
    assert "Devoirs" not in charge


def test_un_collecteur_en_panne_garde_sa_valeur_precedente(collecte, monkeypatch):
    """Sans repli, le widget viderait la section à la première panne passagère."""
    compteur = {}
    _table(
        collecte,
        monkeypatch,
        (("Notes", "les notes", _appels(compteur, "Notes", valeur={"note": [1, 2]})),),
    )
    premier = {}
    collecte.collecter(object(), 7, {}, premier)

    _table(
        collecte,
        monkeypatch,
        (("Notes", "les notes", _appels(compteur, "Notes", explose=True)),),
    )
    second = {}
    statuts = collecte.collecter(object(), 7, {}, second)

    assert statuts["Notes"] == cadence.REPLI
    assert second["Notes"] == {"note": [1, 2]}


def test_une_suspension_d_ip_traverse_le_filet(collecte, monkeypatch):
    """SuspensionIP hérite de BaseException : elle doit arrêter le cycle.

    La rattraper onglet par onglet relancerait des requêtes alors que chaque
    tentative supplémentaire prolonge le blocage côté Pronote.
    """
    import pronote_errors

    def _suspendu(_client):
        raise pronote_errors.SuspensionIP("adresse suspendue")

    _table(collecte, monkeypatch, (("Notes", "les notes", _suspendu),))
    with pytest.raises(pronote_errors.SuspensionIP):
        collecte.collecter(object(), 7, {}, {})


# ── Cadence appliquée à la collecte ─────────────────────────────────────────


def test_un_onglet_espace_n_est_pas_reinterroge(collecte, monkeypatch):
    compteur = {}
    table = (("Menus", "les menus", _appels(compteur, "Menus", valeur={"midi": "x"})),)
    _table(collecte, monkeypatch, table)

    premier = {}
    collecte.collecter(object(), 7, {}, premier)
    second = {}
    statuts = collecte.collecter(object(), 7, {}, second)

    assert compteur["Menus"] == 1, "Pronote a été interrogé deux fois"
    assert statuts["Menus"] == cadence.GARDE
    # Et surtout : la charge reste complète.
    assert second["Menus"] == premier["Menus"] == {"midi": "x"}


def test_chaque_equipement_a_sa_propre_fraicheur(collecte, monkeypatch):
    """Le cache d'un enfant ne doit pas faire sauter la collecte d'un autre."""
    compteur = {}
    _table(collecte, monkeypatch, (("Menus", "les menus", _appels(compteur, "Menus")),))
    collecte.collecter(object(), 7, {}, {})
    collecte.collecter(object(), 8, {}, {})
    assert compteur["Menus"] == 2


# ── Onglets non suivis ──────────────────────────────────────────────────────


def test_un_onglet_non_suivi_n_est_pas_interroge(collecte, monkeypatch):
    compteur = {}
    _table(
        collecte,
        monkeypatch,
        (
            ("Messages", "la messagerie", _appels(compteur, "Messages")),
            ("Notes", "les notes", _appels(compteur, "Notes")),
        ),
    )
    charge = {}
    statuts = collecte.collecter(
        object(), 7, {"OngletsDesactives": ["Messages"]}, charge
    )

    assert "Messages" not in compteur, "Pronote a été interrogé pour un onglet coupé"
    assert statuts["Messages"] == cadence.COUPE
    # Rien n'est envoyé : les commandes correspondantes n'existent pas côté Jeedom.
    assert "Messages" not in charge
    assert statuts["Notes"] == cadence.FRAIS


def test_sans_reglage_tous_les_onglets_sont_suivis(collecte, monkeypatch):
    compteur = {}
    _table(
        collecte,
        monkeypatch,
        (("Messages", "la messagerie", _appels(compteur, "Messages")),),
    )
    collecte.collecter(object(), 7, {}, {})
    assert compteur["Messages"] == 1


# ── Charge transmise à Jeedom ───────────────────────────────────────────────


def test_l_erreur_n_est_remontee_que_pour_les_deux_onglets_historiques(
    collecte, monkeypatch
):
    """Comportement d'origine conservé : seuls l'EDT et les notes remontent."""
    compteur = {}
    _table(
        collecte,
        monkeypatch,
        (("Menus", "les menus", _appels(compteur, "Menus", valeur={"error": "zut"})),),
    )
    charge = {}
    collecte.collecter(object(), 7, {}, charge)
    assert "error" not in charge

    _table(
        collecte,
        monkeypatch,
        (("Notes", "les notes", _appels(compteur, "Notes", valeur={"error": "zut"})),),
    )
    charge = {}
    collecte.collecter(object(), 7, {}, charge)
    assert charge["error"] == "zut"


def test_identifiant_d_equipement_assaini(collecte, monkeypatch):
    """La collecte partage la validation d'identifiant du reste du démon."""
    _table(collecte, monkeypatch, ())
    with pytest.raises(ValueError):
        collecte.collecter(object(), "../7", {}, {})


# ── Une collecte en erreur est une collecte en échec ─────────────────────
#
# Les collecteurs ne lèvent pas : ils rattrapent leurs propres erreurs et rendent
# une structure vide, assortie d'une clé « error ». Tant que collecter() ne lisait
# pas cette clé, ces structures vides partaient vers Jeedom comme des données :
# le 17 septembre 2026 sur l'équipement 20, l'onglet Présence refusé sur un
# « La page a expiré ! (11) » a fait écrire Nb_absences = 0, Nb_retard = 0 et
# Nb_punitions = 0, statut « Connecté », sans aucune erreur visible.


def test_une_collecte_en_erreur_garde_la_valeur_precedente(collecte, monkeypatch):
    """Le cas réel : trois absences relevées, puis l'onglet Présence refusé."""
    compteur = {}
    releve = {"absence": [1, 2, 3], "nb_absences": 3}
    _table(
        collecte,
        monkeypatch,
        (("Absences", "les absences", _appels(compteur, "Absences", valeur=releve)),),
    )
    collecte.collecter(object(), 7, {}, {})

    refus = {"absence": [], "nb_absences": 0, "error": "Onglet Présence (19) refusé"}
    _table(
        collecte,
        monkeypatch,
        (("Absences", "les absences", _appels(compteur, "Absences", valeur=refus)),),
    )
    charge = {}
    statuts = collecte.collecter(object(), 7, {}, charge)

    assert statuts["Absences"] == cadence.REPLI
    assert charge["Absences"]["nb_absences"] == 3


def test_une_collecte_en_erreur_ne_devient_pas_la_valeur_de_repli(
    collecte, monkeypatch
):
    """Sinon le zéro trompeur s'installerait : conservé, puis resservi à l'infini."""
    compteur = {}
    releve = {"nb_absences": 3}
    _table(
        collecte,
        monkeypatch,
        (("Absences", "les absences", _appels(compteur, "Absences", valeur=releve)),),
    )
    collecte.collecter(object(), 7, {}, {})

    refus = {"nb_absences": 0, "error": "refusé"}
    _table(
        collecte,
        monkeypatch,
        (("Absences", "les absences", _appels(compteur, "Absences", valeur=refus)),),
    )
    collecte.collecter(object(), 7, {}, {})
    charge = {}
    collecte.collecter(object(), 7, {}, charge)

    assert charge["Absences"]["nb_absences"] == 3


def test_une_collecte_en_erreur_sans_antecedent_est_absente_de_la_charge(
    collecte, monkeypatch
):
    """Rien à conserver : jeeProJote.php laisse alors les commandes en place.

    Un onglet absent de la charge n'y est pas écrit (le `elseif (isset(...))` de
    jeeProJote.php) : Jeedom garde la valeur qu'il avait en base, plus fiable
    qu'un zéro fabriqué par un onglet illisible.
    """
    compteur = {}
    refus = {"nb_absences": 0, "error": "refusé"}
    _table(
        collecte,
        monkeypatch,
        (("Absences", "les absences", _appels(compteur, "Absences", valeur=refus)),),
    )
    charge = {}
    statuts = collecte.collecter(object(), 7, {}, charge)

    assert statuts["Absences"] == cadence.ECHEC
    assert "Absences" not in charge


def test_un_zero_legitime_passe_toujours(collecte, monkeypatch):
    """Le repli ne doit pas figer un compteur : une absence se régularise."""
    compteur = {}
    _table(
        collecte,
        monkeypatch,
        (
            (
                "Absences",
                "les absences",
                _appels(compteur, "Absences", valeur={"nb_absences": 3}),
            ),
        ),
    )
    collecte.collecter(object(), 7, {}, {})

    _table(
        collecte,
        monkeypatch,
        (
            (
                "Absences",
                "les absences",
                _appels(compteur, "Absences", valeur={"nb_absences": 0}),
            ),
        ),
    )
    charge = {}
    statuts = collecte.collecter(object(), 7, {}, charge)

    assert statuts["Absences"] == cadence.FRAIS
    assert charge["Absences"]["nb_absences"] == 0


def test_un_collecteur_qui_ne_rend_rien_est_un_echec(collecte, monkeypatch):
    """Aucun collecteur ne rend None en marche normale.

    C'est la trace d'un `except` de dernier recours qui a laissé la fonction
    retomber sans valeur — `retards()` et `notifications()` en ont un.
    """
    compteur = {}

    def _muet(_client):
        compteur["Retards"] = compteur.get("Retards", 0) + 1
        return None

    _table(collecte, monkeypatch, (("Retards", "les retards", _muet),))
    statuts = collecte.collecter(object(), 7, {}, {})

    assert statuts["Retards"] == cadence.ECHEC


# ── Bruit du journal : une cause, une alerte ────────────────────────────────
#
# Retour d'un bêta-testeur le 19 septembre 2026 : quatre lignes ERROR à la même
# seconde, pour un seul refus de l'onglet Présence.
#
#   ERROR - Collecte en erreur pour les absences : … La page a expiré ! (11)
#   ERROR - Collecte en erreur pour les retards : … La page a expiré ! (11)
#   ERROR - Collecte en erreur pour les punitions : … La page a expiré ! (11)
#   ERROR - Collecte en erreur pour les évènements … La page a expiré ! (11)
#
# Quatre onglets partagent cet onglet Pronote : le premier refus vaut pour tous.
# Le répéter en erreur fait passer un incident pour quatre, et noie les pannes
# réellement distinctes.


def _rend(valeur):
    return lambda _client: valeur


def test_une_cause_commune_ne_sonne_qu_une_fois(collecte, monkeypatch, caplog):
    import logging

    motif = "Onglet Présence (19) inaccessible : La page a expiré ! (11)"
    _table(
        collecte,
        monkeypatch,
        (
            ("Absences", "les absences", _rend({"error": motif})),
            ("Retards", "les retards", _rend({"error": motif})),
            ("Punitions", "les punitions", _rend({"error": motif})),
            ("Evenements", "les évènements de vie scolaire", _rend({"error": motif})),
        ),
    )
    with caplog.at_level(logging.INFO):
        statuts = collecte.collecter(object(), 7, {}, {})

    erreurs = [e for e in caplog.records if e.levelno >= logging.ERROR]
    assert len(erreurs) == 1, f"{len(erreurs)} alertes pour une seule cause"
    assert motif in erreurs[0].getMessage()

    # Les trois autres restent signalés, mais sans alarme.
    rattachements = [
        e for e in caplog.records
        if e.levelno == logging.INFO and "même cause" in e.getMessage()
    ]
    assert len(rattachements) == 3

    # Et surtout : le statut de chaque onglet est inchangé.
    assert all(statuts[c] == cadence.ECHEC for c in
               ("Absences", "Retards", "Punitions", "Evenements"))


def test_deux_causes_distinctes_sonnent_chacune(collecte, monkeypatch, caplog):
    """Le regroupement ne doit pas masquer une seconde panne, bien réelle."""
    import logging

    _table(
        collecte,
        monkeypatch,
        (
            ("Absences", "les absences", _rend({"error": "onglet Présence refusé"})),
            ("Retards", "les retards", _rend({"error": "onglet Présence refusé"})),
            ("Notes", "les notes", _rend({"error": "serveur injoignable"})),
        ),
    )
    with caplog.at_level(logging.INFO):
        collecte.collecter(object(), 7, {}, {})

    erreurs = [e.getMessage() for e in caplog.records if e.levelno >= logging.ERROR]
    assert len(erreurs) == 2
    assert any("serveur injoignable" in m for m in erreurs)


def test_le_repli_sur_valeur_precedente_survit_au_regroupement(collecte, monkeypatch):
    """Le regroupement ne touche qu'au journal, jamais à la charge."""
    compteur = {}
    _table(collecte, monkeypatch,
           (("Notes", "les notes", _appels(compteur, "Notes", valeur={"note": [1]})),))
    collecte.collecter(object(), 7, {}, {})

    _table(collecte, monkeypatch, (("Notes", "les notes", _rend({"error": "boum"})),))
    charge = {}
    statuts = collecte.collecter(object(), 7, {}, charge)

    assert statuts["Notes"] == cadence.REPLI
    assert charge["Notes"] == {"note": [1]}
