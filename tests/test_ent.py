"""Tests de la liste des ENT proposée par la page de configuration.

La liste est écrite en dur dans `desktop/php/ProJote.php`, alors que les
connecteurs ENT vivent dans pronotepy, qui en retire et en renomme au fil des
versions. Les deux dérivent donc l'une de l'autre sans que rien ne le signale.

Relevé le 19 septembre 2026 sur pronotepy 2.15.6 : trois entrées du formulaire
n'existaient plus — `pronotepy.ent` (qui n'a jamais été un ENT, mais le nom du
module), `ozecollege_yvelines` et `pronote_hubeduconnect` — et trois connecteurs
réels manquaient : `bordeaux`, `cas_arsene76`, `cas_ent27`.

Le choix d'une entrée caduque ne produisait aucun message : `class_for_name`
rendait None, la connexion partait **sans ENT**, et l'utilisateur d'un
établissement protégé par EduConnect recevait un « KeyError: 'dataSec' » venu
des entrailles de pronotepy. C'est le symptôme signalé par les utilisateurs de
Poitiers et de Nantes.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP_PATH = os.path.join(ROOT, "desktop", "php", "ProJote.php")

OPTION_RE = re.compile(r'<option value="([^"]*)">\{\{([^}]*)\}\}</option>')


@pytest.fixture(scope="module")
def options():
    """Valeurs du sélecteur « Mode CAS » de la page de configuration."""
    with open(PHP_PATH, encoding="utf-8") as fh:
        contenu = fh.read()
    debut = contenu.index('data-l2key="CasEnt"')
    fin = contenu.index("</select>", debut)
    return OPTION_RE.findall(contenu[debut:fin])


def test_le_selecteur_existe(options):
    assert len(options) > 20, "le sélecteur d'ENT semble vide ou introuvable"


def test_la_premiere_entree_est_aucun(options):
    """« Aucun » doit rester en tête : c'est le cas des établissements sans ENT."""
    assert options[0][0] == ""


def test_pas_de_doublon(options):
    valeurs = [v for v, _ in options]
    assert len(valeurs) == len(set(valeurs))


def test_liste_triee(options):
    """Une liste de quarante entrées ne se parcourt qu'ordonnée."""
    valeurs = [v for v, _ in options if v]
    assert valeurs == sorted(valeurs, key=str.lower)


@pytest.mark.parametrize(
    "caduque",
    [
        # Le nom du module pronotepy, proposé par erreur comme s'il était un ENT.
        "pronotepy.ent",
        # Retirés de pronotepy ; leur choix menait à une connexion sans ENT.
        "ozecollege_yvelines",
        "pronote_hubeduconnect",
    ],
)
def test_les_entrees_caduques_ne_reviennent_pas(options, caduque):
    assert caduque not in [v for v, _ in options]


@pytest.mark.parametrize("connecteur", ["bordeaux", "cas_arsene76", "cas_ent27"])
def test_les_connecteurs_oublies_sont_proposes(options, connecteur):
    assert connecteur in [v for v, _ in options]


def test_la_liste_correspond_a_pronotepy(options):
    """Le seul contrôle qui vaille : la comparer à ce que pronotepy sait faire.

    Ignoré là où pronotepy n'est pas installé — l'intégration continue n'a que
    les dépendances de développement. Le test garde donc toute sa valeur sur le
    poste du développeur et sur l'installation Jeedom, là où la question se
    pose vraiment.
    """
    ent = pytest.importorskip(
        "pronotepy.ent", reason="pronotepy absent de cet environnement"
    )
    # conftest installe une doublure de pronotepy pour que le démon soit
    # importable sans lui. Elle n'a pas de fichier sur disque : c'est ce qui la
    # distingue du vrai paquet. Sans ce garde, le test comparerait la liste à
    # un module vide et échouerait sur les quarante-trois entrées.
    if not getattr(ent, "__file__", None):
        pytest.skip("pronotepy est ici une doublure de test, pas le vrai paquet")
    connus = {
        n
        for n in dir(ent)
        if not n.startswith("_") and callable(getattr(ent, n))
    }
    proposes = {v for v, _ in options if v}

    inconnus = sorted(proposes - connus)
    manquants = sorted(connus - proposes)
    assert not inconnus, (
        f"proposés par le formulaire mais absents de pronotepy : {inconnus} — "
        "leur choix mène à une connexion sans ENT"
    )
    assert not manquants, (
        f"connus de pronotepy mais absents du formulaire : {manquants} — "
        "ces établissements ne peuvent pas être configurés"
    )


def test_un_ent_inconnu_arrete_la_validation():
    """Le silence était le vrai défaut : un réglage caduc doit se voir.

    LoginConnect n'est pas importable en test (bloc principal, argparse), d'où
    un contrôle sur la source.
    """
    chemin = os.path.join(ROOT, "resources", "ProJoted", "LoginConnect.py")
    with open(chemin, encoding="utf-8") as fh:
        source = fh.read()
    assert "sys.exit(ENT_INCONNU_EXIT_CODE)" in source
    assert "n'existe pas dans la version de pronotepy" in source


def test_l_ajax_traduit_le_code_pour_l_utilisateur():
    chemin = os.path.join(ROOT, "core", "ajax", "ProJote.ajax.php")
    with open(chemin, encoding="utf-8") as fh:
        source = fh.read()
    assert "$return_var === 11" in source


def test_le_code_de_sortie_est_distinct():
    import pronote_errors

    codes = [
        pronote_errors.IP_SUSPENSION_EXIT_CODE,
        pronote_errors.NO_MOBILE_TOKEN_EXIT_CODE,
        pronote_errors.DECHIFFREMENT_EXIT_CODE,
        pronote_errors.IDENTIFIANTS_REFUSES_EXIT_CODE,
        pronote_errors.ENT_INCONNU_EXIT_CODE,
    ]
    assert pronote_errors.ENT_INCONNU_EXIT_CODE == 11
    assert len(set(codes)) == len(codes)
