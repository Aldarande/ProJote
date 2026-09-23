"""Tests du contrôle de fuite de données personnelles.

Ce dépôt est public, et il a porté pendant vingt mois les jetons, les prénoms,
les classes et les photographies de quatre enfants. Supprimer les fichiers
n'avait rien effacé : l'historique les gardait intacts, et il a fallu le
réécrire puis le republier de force en septembre 2026.

``outils/verifier_fuites.py`` est le garde-fou qui manquait. Il est lui-même
testé, parce qu'un contrôle de sécurité qui ne détecte plus rien est pire que
pas de contrôle du tout : il rassure.

**Aucune donnée réelle dans ce fichier.** Les exemples sensibles sont assemblés
par concaténation, pour que le contrôle appliqué à tout le dépôt ne se
déclenche pas sur ses propres tests.
"""

import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTILS = os.path.join(RACINE, "outils")
if OUTILS not in sys.path:
    sys.path.insert(0, OUTILS)

import verifier_fuites  # noqa: E402


def controler(ligne, prives=None, precedente=""):
    """Raccourci : les noms de règles déclenchées par une ligne."""
    return [nom for nom, _, _ in verifier_fuites.examiner_ligne(ligne, prives or [], precedente)]


# ── Établissements : le réel est refusé, la démonstration passe ─────────────


def test_une_url_d_etablissement_reel_est_refusee():
    """C'est par là que le nom de l'école des enfants était lisible."""
    url = "https://" + "0912109z" + ".index-education.net/pronote/"
    assert "établissement réel" in controler(url)


def test_le_serveur_de_demonstration_est_autorise():
    """Les identifiants de la démonstration sont publics : rien à cacher."""
    assert controler("https://demo.index-education.net/pronote/eleve.html") == []


def test_les_codes_fictifs_des_tests_sont_autorises():
    """Ceux qui ont remplacé les vrais lors de la purge de septembre 2026."""
    assert controler("https://0000000a.index-education.net/pronote/") == []


# ── Identifiants d'espace ───────────────────────────────────────────────────


def test_un_identifiant_d_espace_est_refuse():
    assert "identifiant d'espace" in controler("?" + "identifiant=" + "7tTQmnp4Qyu7ZR58")


def test_le_marqueur_d_exemple_est_autorise():
    assert controler("?" + "identifiant=" + "EXEMPLE5") == []


# ── Jetons ──────────────────────────────────────────────────────────────────


def test_une_longue_chaine_hexadecimale_est_refusee():
    """Trente-deux caractères hexadécimaux, c'est la taille d'un jeton."""
    assert "jeton" in controler('Password = "' + "ab12" * 8 + '"')


def test_une_chaine_hexadecimale_courte_passe():
    """Une couleur CSS ou un petit identifiant ne doivent pas alerter."""
    assert controler("color: #a1b2c3;") == []


# ── Chemins Windows ─────────────────────────────────────────────────────────


def test_un_chemin_windows_nommant_la_session_est_refuse():
    """C'est ainsi que .venv/pyvenv.cfg révélait le nom de session."""
    assert "chemin utilisateur" in controler("home = C:" + chr(92) + "Users" + chr(92) + "dupont")


def test_un_chemin_windows_generique_passe():
    assert controler("home = C:" + chr(92) + "Users" + chr(92) + "utilisateur") == []


# ── Courriels ───────────────────────────────────────────────────────────────


def test_une_adresse_de_courriel_est_refusee():
    assert "adresse courriel" in controler("contact : " + "jean" + "@" + "fournisseur.fr")


def test_les_domaines_d_exemple_sont_autorises():
    assert controler("contact : " + "jean" + "@" + "example.com") == []


# ── Le marqueur d'acceptation ───────────────────────────────────────────────


def test_le_marqueur_sur_la_ligne_leve_l_alerte():
    ligne = '"' + "ab12" * 8 + '"  # ' + verifier_fuites.MARQUEUR
    assert controler(ligne) == []


def test_le_marqueur_sur_la_ligne_precedente_leve_l_alerte():
    """Une ligne déjà longue n'a pas à porter en plus sa justification."""
    assert controler('"' + "ab12" * 8 + '"', precedente="# " + verifier_fuites.MARQUEUR) == []


# ── Motifs privés ───────────────────────────────────────────────────────────


def test_un_motif_prive_est_applique(tmp_path):
    """Les prénoms vivent hors du dépôt ; le contrôle les lit quand même."""
    (tmp_path / ".motifs-prives").write_text(
        "# commentaire ignoré\n\n" + chr(92) + "bmartin" + chr(92) + "b\n",
        encoding="utf-8",
    )
    prives = verifier_fuites.motifs_prives(str(tmp_path))
    assert len(prives) == 1
    assert "motif privé" in controler("eleve = Martin", prives)
    assert controler("eleve = Dupont", prives) == []


def test_un_motif_avec_caractere_de_controle_est_refuse(tmp_path):
    """Le piège rencontré à la mise en place, le 22 septembre 2026.

    Un outil intermédiaire avait interprété la borne de mot des expressions
    rationnelles au lieu de l'écrire : le fichier contenait le caractère de
    contrôle 0x08 à sa place. L'expression
    compilait, ne correspondait plus à rien, et le contrôle annonçait un dépôt
    propre. Un filtre de confidentialité muet est pire que pas de filtre.
    """
    (tmp_path / ".motifs-prives").write_text(
        chr(8) + "martin" + chr(8) + chr(10), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="caractère de contrôle"):
        verifier_fuites.motifs_prives(str(tmp_path))


def test_une_expression_invalide_est_refusee(tmp_path):
    """Mieux vaut une erreur franche qu'un motif silencieusement ignoré."""
    (tmp_path / ".motifs-prives").write_text("[non-ferme" + chr(10), encoding="utf-8")
    with pytest.raises(ValueError, match="ligne 1"):
        verifier_fuites.motifs_prives(str(tmp_path))


def test_sans_fichier_de_motifs_le_controle_fonctionne(tmp_path):
    """Un clone neuf n'a pas ce fichier : les règles génériques suffisent."""
    assert verifier_fuites.motifs_prives(str(tmp_path)) == []


# ── Chemins interdits ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "chemin",
    [
        "data/14/enfant.ProJote.json.txt",
        "data/2/profile_picture.jpg",
        ".venv/pyvenv.cfg",
        "resources/python_venv/lib/python3.11/site-packages/pip/__init__.py",
    ],
)
def test_les_repertoires_interdits_sont_reconnus(chemin):
    """Les quatre familles de fichiers retirées de l'historique en 2026."""
    assert verifier_fuites.chemins_interdits([chemin]) == [chemin]


def test_un_chemin_legitime_passe():
    assert verifier_fuites.chemins_interdits(["resources/ProJoted/collecteurs.py"]) == []


# ── Le rapport ne doit pas recopier la fuite ────────────────────────────────


def test_la_valeur_trouvee_est_masquee():
    """Un rapport qui recopie la fuite finit dans un journal public."""
    secret = "ab12" * 8
    masque = verifier_fuites._masquer(secret)
    assert secret not in masque
    assert "32 caractères" in masque


def test_une_valeur_courte_est_masquee_aussi():
    assert verifier_fuites._masquer("secret") == "se…"


# ── L'arbre du dépôt lui-même ───────────────────────────────────────────────


def test_le_depot_est_propre():
    """Le contrôle que fait la CI, rejoué ici : la boucle doit rester fermée."""
    ennuis = verifier_fuites.examiner_arbre(RACINE, verifier_fuites.motifs_prives(RACINE))
    assert ennuis == [], "\n".join("%s : %s" % (e[0], e[2]) for e in ennuis)
