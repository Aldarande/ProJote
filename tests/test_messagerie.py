"""Tests de la collecte de la messagerie Pronote.

Deux comptes réels, deux échecs à chaque cycle, deux causes sans rapport —
relevés le 17 septembre 2026 dans le journal du Jeedom de développement :

    Erreur lors de l'accès aux discussions Pronote : 'listeEtiquettes'
    Erreur lors de l'accès aux discussions Pronote : Onglet 131 non accessible
      pour ce compte (ListeMessagerie)

Le premier est un défaut : pronotepy lit deux listes — « listeEtiquettes » puis
« listeMessagerie » — que tous les serveurs ne renvoient pas, et la messagerie
de ce compte restait vide pour toujours. Ne réparer que la première faisait
simplement échouer sur la seconde, constaté le 18 septembre en conditions
réelles.
Le second n'en est pas un : l'établissement n'a pas ouvert la messagerie à ce
compte. Le journaliser en erreur remplissait le journal d'une alerte horaire sur
un état parfaitement normal — et noyait les vraies pannes.
"""

import pytest

import pronote_errors


# ── Étiquettes absentes de la réponse du serveur ────────────────────────────


@pytest.fixture
def compat():
    import pronote_compat

    return pronote_compat


def _reponse(donnees):
    return {"dataSec": {"data": donnees}}


def test_liste_etiquettes_ajoutee_quand_le_serveur_l_omet(compat):
    """pronotepy lit listeEtiquettes["V"] sans précaution : sans la clé, KeyError.

    Une liste vide donne exactement ce qu'il attend — des discussions sans
    étiquette, ce qui est le cas sur ces serveurs.
    """
    reponse = _reponse({"listeMessagerie": {"V": []}})
    repare = compat._reparer_reponse_messagerie("ListeMessagerie", reponse)
    assert repare["dataSec"]["data"]["listeEtiquettes"] == {"V": []}


def test_liste_messagerie_ajoutee_aussi(compat):
    """Réparer la première clé faisait simplement échouer sur la suivante.

    Constaté sur le compte concerné le 18 septembre 2026 : une fois
    « listeEtiquettes » complétée, pronotepy tombait sur
    « KeyError: 'listeMessagerie' ». Ce serveur omet les deux.
    """
    reponse = _reponse({"listeEtiquettes": {"V": []}})
    repare = compat._reparer_reponse_messagerie("ListeMessagerie", reponse)
    assert repare["dataSec"]["data"]["listeMessagerie"] == {"V": []}


def test_les_deux_listes_absentes_a_la_fois(compat):
    """Le cas réellement rencontré : la réponse ne porte ni l'une ni l'autre."""
    reponse = _reponse({"autreChose": 1})
    repare = compat._reparer_reponse_messagerie("ListeMessagerie", reponse)
    donnees = repare["dataSec"]["data"]
    assert donnees["listeEtiquettes"] == {"V": []}
    assert donnees["listeMessagerie"] == {"V": []}
    assert donnees["autreChose"] == 1, "le reste de la réponse est intact"


def test_les_listes_du_serveur_ne_sont_pas_ecrasees(compat):
    etiquettes = {"V": [{"N": "1", "G": 2}]}
    discussions = {"V": [{"N": "d1"}]}
    reponse = _reponse({"listeEtiquettes": etiquettes, "listeMessagerie": discussions})
    repare = compat._reparer_reponse_messagerie("ListeMessagerie", reponse)
    assert repare["dataSec"]["data"]["listeEtiquettes"] is etiquettes
    assert repare["dataSec"]["data"]["listeMessagerie"] is discussions


def test_seule_la_messagerie_est_reparee(compat):
    """Aucune autre réponse ne doit se voir ajouter une clé qu'elle n'a pas."""
    reponse = _reponse({"listeAbsences": {"V": []}})
    compat._reparer_reponse_messagerie("PagePresence", reponse)
    assert "listeEtiquettes" not in reponse["dataSec"]["data"]
    assert "listeMessagerie" not in reponse["dataSec"]["data"]


@pytest.mark.parametrize(
    "reponse", [None, "pas un dictionnaire", {}, {"dataSec": {}}, {"dataSec": {"data": None}}]
)
def test_une_reponse_inattendue_traverse_sans_dommage(compat, reponse):
    assert compat._reparer_reponse_messagerie("ListeMessagerie", reponse) is reponse


def test_la_reparation_est_posee_sur_les_deux_chemins():
    """Le client parent redéfinit post() et court-circuite celui du client de base.

    Sans la réparation sur les deux, un compte parent aurait continué d'échouer.
    Depuis le 23 septembre 2026 les deux chemins partagent la même reprise de
    session (``_poster_avec_reprise``), où la réparation est appliquée une fois
    pour la tentative et une fois pour le rejeu : c'est ce partage qui garantit
    désormais qu'aucun des deux ne puisse l'oublier.
    """
    import os

    chemin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources", "ProJoted", "pronote_compat.py",
    )
    with open(chemin, encoding="utf-8") as f:
        source = f.read()
    # Une définition, et les deux appels de la reprise partagée.
    assert source.count("_reparer_reponse_messagerie") == 3
    # Un branchement depuis chacun des deux chemins, et pas un de moins.
    assert source.count("return _poster_avec_reprise(self,") == 2


# ── Onglet non ouvert à ce compte ───────────────────────────────────────────


def test_reconnaissance_de_l_onglet_non_accessible():
    exc = Exception("Onglet 131 non accessible pour ce compte (ListeMessagerie)")
    assert pronote_errors.est_onglet_non_accessible(exc) is True


@pytest.mark.parametrize(
    "message",
    [
        "'listeEtiquettes'",
        "Connection timed out",
        "Your IP address is suspended.",
        "Unknown error from pronote: 3 | Accès refusé",
    ],
)
def test_les_vraies_pannes_ne_sont_pas_assimilees(message):
    assert pronote_errors.est_onglet_non_accessible(Exception(message)) is False


class _ClientSansMessagerie:
    def discussions(self):
        raise Exception("Onglet 131 non accessible pour ce compte (ListeMessagerie)")


class _ClientEnPanne:
    def discussions(self):
        raise Exception("Connection timed out")


def test_un_compte_sans_messagerie_ne_remonte_pas_d_erreur(daemon, caplog):
    """Ce n'est pas une panne : rien ne doit partir en ERREUR, ni en « error »."""
    import logging

    import collecteurs

    with caplog.at_level(logging.INFO):
        data = collecteurs.messages(_ClientSansMessagerie())

    assert "error" not in data
    assert data["Nb_messages"] == 0
    assert not [e for e in caplog.records if e.levelno >= logging.WARNING]
    assert any("non ouverte à ce compte" in e.message for e in caplog.records)


def test_une_vraie_panne_reste_une_erreur(daemon, caplog):
    """Le contraire serait pire : une messagerie en panne doit se voir."""
    import logging

    import collecteurs

    with caplog.at_level(logging.INFO):
        data = collecteurs.messages(_ClientEnPanne())

    assert "error" in data
    assert [e for e in caplog.records if e.levelno >= logging.ERROR]


def test_le_journal_montre_les_cles_du_serveur_pas_les_notres(compat, caplog):
    """Journaliser les clés après insertion ne renseignait sur rien.

    La ligne affichait « listeEtiquettes, listeMessagerie » — celles qu'on
    venait d'ajouter — au lieu de ce que le serveur avait réellement envoyé.
    """
    import logging

    reponse = _reponse({"parametresChargement": 1})
    with caplog.at_level(logging.DEBUG):
        compat._reparer_reponse_messagerie("ListeMessagerie", reponse)

    trace = " ".join(e.getMessage() for e in caplog.records)
    assert "parametresChargement" in trace
    # Ce qui suit « réellement reçues » ne doit contenir que les clés du serveur.
    assert "listeEtiquettes" not in trace.split("réellement reçues")[-1]


# ── iCal : un export que l'établissement n'a pas ouvert ─────────────────────
#
# Retour d'un bêta-testeur le 19 septembre 2026 :
#
#   ERROR - Une erreur est survenue lors de la récupération de l'URL iCal:
#           ligne 1285 - Could not parse ICal params
#
# pronotepy lève cela quand la réponse de PageInfosPerso ne porte aucune entrée
# iCal : l'établissement n'a pas ouvert l'export de calendrier à ce compte. Un
# état, pas un incident — et pourtant une alerte à chaque cycle, toutes les
# heures, qui noyait les vraies pannes. Même famille que l'onglet 131 fermé.


class _ClientSansIcal:
    def export_ical(self):
        raise Exception("Could not parse ICal params")


class _ClientIcalEnPanne:
    def export_ical(self):
        raise Exception("Connection timed out")


def test_un_export_ical_non_propose_ne_remonte_pas_d_erreur(daemon, caplog):
    import logging

    import collecteurs

    with caplog.at_level(logging.INFO):
        url = collecteurs.ical(_ClientSansIcal())

    assert url == ""
    assert not [e for e in caplog.records if e.levelno >= logging.WARNING]
    assert any("non proposé par l'établissement" in e.getMessage() for e in caplog.records)


def test_une_vraie_panne_ical_reste_une_erreur(daemon, caplog):
    import logging

    import collecteurs

    with caplog.at_level(logging.INFO):
        assert collecteurs.ical(_ClientIcalEnPanne()) == ""

    assert [e for e in caplog.records if e.levelno >= logging.ERROR]
