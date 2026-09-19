"""Validation du manifest plugin_info/info.json (D5).

Garantit que le manifest reste conforme aux attentes du canal stable Jeedom
et aux préférences du projet (monolingue fr_FR, licence AGPL, version SemVer).
"""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFO_PATH = os.path.join(ROOT, "plugin_info", "info.json")

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


@pytest.fixture(scope="module")
def info():
    with open(INFO_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_info_json_is_valid_json(info):
    assert isinstance(info, dict)


def test_required_fields_present(info):
    for field in ("id", "name", "pluginVersion", "description", "licence", "author", "require"):
        assert field in info, f"Champ requis manquant : {field}"


def test_id_is_projote(info):
    assert info["id"] == "ProJote"


def test_version_is_semver(info):
    assert SEMVER_RE.match(info["pluginVersion"]), (
        f"pluginVersion '{info['pluginVersion']}' n'est pas au format X.Y.Z"
    )


def test_licence_agpl(info):
    assert "AGPL" in info["licence"].upper()


def test_monolingual_fr_fr(info):
    # Préférence projet : monolingue fr_FR, aucune référence en_US.
    assert "fr_FR" in info["description"]
    assert "en_US" not in info["description"], "Aucune description en_US attendue"
    if "language" in info:
        assert "en_US" not in info["language"], "Aucune langue en_US attendue"


def test_require_is_supported(info):
    # Jeedom 4.4 minimum.
    assert info["require"] in ("4.4", "4.5", "4.6", "5.0")


# ── Gabarits de commandes ────────────────────────────────────────────────────
#
# Le modèle de commandes désigne un gabarit par son nom (« ProJote::edt ») ;
# Jeedom le résout en core/template/<version>/cmd.<type>.<sous-type>.<nom>.html.
# Un nom sans fichier ne produit aucune erreur : la commande s'affiche vide.

CLASS_PATH = os.path.join(ROOT, "core", "class", "ProJote.class.php")

MODELE_RE = re.compile(
    r'"(?P<logical>[A-Za-z0-9_]+)"\s*=> array\('
    r"\s*(?P<nom>'[^']*'|\"[^\"]*\")\s*,"
    r"\s*'(?P<type>[a-z]+)'\s*,"
    r"\s*'(?P<sous_type>[a-z]+)'\s*,"
    r"[^\n]*?,\s*'(?P<dashboard>[^']+)'\s*,\s*'(?P<mobile>[^']+)'\s*\)"
)


@pytest.fixture(scope="module")
def commandes():
    with open(CLASS_PATH, encoding="utf-8") as fh:
        lignes = MODELE_RE.findall(fh.read())
    assert lignes, "modèle de commandes introuvable"
    return [
        {
            "logical": logical, "type": type_, "sous_type": sous_type,
            "dashboard": dashboard, "mobile": mobile,
        }
        for logical, _nom, type_, sous_type, dashboard, mobile in lignes
    ]


def _chemin_gabarit(version, cmd, gabarit):
    nom = gabarit.split("::", 1)[1]
    return os.path.join(
        ROOT, "core", "template", version,
        f"cmd.{cmd['type']}.{cmd['sous_type']}.{nom}.html",
    )


@pytest.mark.parametrize("version", ["dashboard", "mobile"])
def test_gabarits_projote_existent(commandes, version):
    manquants = [
        (cmd["logical"], cmd[version])
        for cmd in commandes
        if cmd[version].startswith("ProJote::")
        and not os.path.exists(_chemin_gabarit(version, cmd, cmd[version]))
    ]
    assert not manquants, f"gabarits {version} désignés mais absents : {manquants}"


def test_les_commandes_riches_ont_un_gabarit_mobile(commandes):
    """Une commande qui porte du JSON doit être rendue, pas affichée brute.

    Sans gabarit mobile, ces commandes retombaient sur « core::badge » et
    l'application mobile montrait la chaîne JSON telle quelle.
    """
    sans_mobile = [
        cmd["logical"]
        for cmd in commandes
        if cmd["dashboard"].startswith("ProJote::")
        and not cmd["mobile"].startswith("ProJote::")
    ]
    assert not sans_mobile, f"gabarit dashboard riche mais mobile en badge : {sans_mobile}"


# ── Images de la documentation ───────────────────────────────────────────────
#
# Les pages de doc référencent leurs images en relatif (« ../picture/… »).
# Rien ne signale une image absente : la page se publie, et le lecteur voit un
# cadre vide. Quatre d'entre elles ont ainsi disparu d'un commit intitulé
# « test » en juillet 2025 et sont restées manquantes plus d'un an.

IMAGE_RE = re.compile(r'src="(?P<chemin>\.\./[^"]+\.(?:png|jpg|jpeg|gif|webp|svg))"')


@pytest.mark.parametrize("page", ["index.html", "beta.html", "dev.html"])
def test_les_images_de_la_doc_existent(page):
    chemin_page = os.path.join(ROOT, "docs", "fr_FR", page)
    if not os.path.exists(chemin_page):
        pytest.skip(f"{page} absent")
    with open(chemin_page, encoding="utf-8") as fh:
        references = IMAGE_RE.findall(fh.read())

    manquantes = [
        ref
        for ref in references
        if not os.path.exists(
            os.path.normpath(os.path.join(ROOT, "docs", "fr_FR", ref))
        )
    ]
    assert not manquantes, f"images référencées mais absentes dans {page} : {manquantes}"


def test_les_captures_d_apercu_sont_presentes():
    """Les trois captures de la section « Aperçu », qui servent aussi au Market."""
    dossier = os.path.join(ROOT, "docs", "picture")
    for nom in (
        "apercu-panneau-eleves.png",
        "apercu-widget-messagerie.png",
        "apercu-widget-retards.png",
    ):
        chemin = os.path.join(dossier, nom)
        assert os.path.exists(chemin), f"capture manquante : {nom}"
        with open(chemin, "rb") as fh:
            assert fh.read(8).startswith(b"\x89PNG"), f"{nom} n'est pas un PNG"


def test_les_captures_du_market_suivent_la_convention():
    """Le Market nomme les captures <id>_screenshotN.png, comme l'icône <id>_icon.png.

    Convention relevée sur le Market lui-même : les images d'une fiche y sont
    servies depuis filestore/market/plugin/images/<id>_screenshotN.png. Elle
    prolonge celle de l'icône, que le Market lit bien dans plugin_info/.
    Un nom qui s'en écarte ne serait simplement jamais repris — sans erreur.
    """
    with open(INFO_PATH, encoding="utf-8") as fh:
        plugin_id = json.load(fh)["id"]

    dossier = os.path.join(ROOT, "plugin_info")
    captures = sorted(
        f for f in os.listdir(dossier) if "_screenshot" in f.lower()
    )
    assert captures, "aucune capture pour la fiche du Market"

    attendus = [f"{plugin_id}_screenshot{n}.png" for n in range(1, len(captures) + 1)]
    assert captures == attendus, (
        f"nommage attendu {attendus}, trouvé {captures} — "
        "la numérotation doit être continue et commencer à 1"
    )
    for nom in captures:
        with open(os.path.join(dossier, nom), "rb") as fh:
            assert fh.read(8).startswith(b"\x89PNG"), f"{nom} n'est pas un PNG"
