"""Tests de la collecte de la messagerie Pronote.

Deux comptes réels, deux échecs à chaque cycle, deux causes sans rapport —
relevés le 17 septembre 2026 dans le journal du Jeedom de développement :

    Erreur lors de l'accès aux discussions Pronote : 'listeEtiquettes'
    Erreur lors de l'accès aux discussions Pronote : Onglet 131 non accessible
      pour ce compte (ListeMessagerie)

Le premier est un défaut : pronotepy lit une clé que tous les serveurs ne
renvoient pas, et la messagerie de ce compte restait vide pour toujours.
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
    repare = compat._reparer_liste_etiquettes("ListeMessagerie", reponse)
    assert repare["dataSec"]["data"]["listeEtiquettes"] == {"V": []}


def test_les_etiquettes_du_serveur_ne_sont_pas_ecrasees(compat):
    etiquettes = {"V": [{"N": "1", "G": 2}]}
    reponse = _reponse({"listeEtiquettes": etiquettes, "listeMessagerie": {"V": []}})
    repare = compat._reparer_liste_etiquettes("ListeMessagerie", reponse)
    assert repare["dataSec"]["data"]["listeEtiquettes"] is etiquettes


def test_seule_la_messagerie_est_reparee(compat):
    """Aucune autre réponse ne doit se voir ajouter une clé qu'elle n'a pas."""
    reponse = _reponse({"listeAbsences": {"V": []}})
    compat._reparer_liste_etiquettes("PagePresence", reponse)
    assert "listeEtiquettes" not in reponse["dataSec"]["data"]


@pytest.mark.parametrize(
    "reponse", [None, "pas un dictionnaire", {}, {"dataSec": {}}, {"dataSec": {"data": None}}]
)
def test_une_reponse_inattendue_traverse_sans_dommage(compat, reponse):
    assert compat._reparer_liste_etiquettes("ListeMessagerie", reponse) is reponse


def test_la_reparation_est_posee_sur_les_deux_chemins():
    """Le client parent redéfinit post() et court-circuite celui du client de base.

    Sans la réparation sur les deux, un compte parent aurait continué d'échouer.
    """
    import os

    chemin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources", "ProJoted", "pronote_compat.py",
    )
    with open(chemin, encoding="utf-8") as f:
        source = f.read()
    # Une définition, un appel côté client de base, deux côté client parent.
    assert source.count("_reparer_liste_etiquettes") == 4


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
