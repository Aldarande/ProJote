"""Vérifie que les URL internes du plugin désignent des fichiers qui existent.

Né d'un défaut livré aux bêta-testeurs le 3 octobre 2026. Le point d'accès aux
pièces jointes avait été renommé `piece_jointe.php` → `fichier.php` ; les URL de
photo avaient suivi, mais les deux constructeurs de liens de pièces jointes —
widget et panneau — étaient restés sur l'ancien nom. L'utilisateur recevait un
« Not Found » en cliquant sur le menu de la cantine.

La relecture qui a suivi le renommage n'a rien vu : elle cherchait le NOUVEAU
nom, et trouvait partout des occurrences correctes. Chercher ce qui a disparu
est plus difficile que vérifier ce qui est là — d'où ce test, qui part des
appels et remonte vers les fichiers plutôt que l'inverse.

Il couvre tout `/plugins/ProJote/...` référencé depuis le PHP, le JavaScript et
les gabarits : scripts, images, feuilles de style. Un renommage non répercuté
casse désormais la suite de tests, pas l'expérience d'un utilisateur.
"""

import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dossiers servis au navigateur. `data/` en est exclu : il est fermé par son
# .htaccess, et ce qu'il contient est servi par core/php/fichier.php.
DOSSIERS = ("core", "desktop", "plugin_info", "3rdparty")

EXTENSIONS = (".php", ".js", ".html")

# « /plugins/ProJote/<chemin> », avec ou sans slash initial, jusqu'au premier
# caractère qui ne peut pas appartenir à un chemin de fichier.
MOTIF = re.compile(r"""plugins/ProJote/([A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,5})""")

# Chemins construits dynamiquement : le motif y capturerait un fragment qui ne
# désigne aucun fichier réel. Ils sont vérifiés ailleurs, à l'exécution.
TOLERES = ("data/",)


def _fichiers_a_analyser():
    for dossier in DOSSIERS:
        base = os.path.join(RACINE, dossier)
        if not os.path.isdir(base):
            continue
        for racine, _, noms in os.walk(base):
            for nom in noms:
                if nom.endswith(EXTENSIONS):
                    yield os.path.join(racine, nom)


def _references():
    """Rend (fichier source, numéro de ligne, chemin référencé)."""
    for chemin in _fichiers_a_analyser():
        with open(chemin, "r", encoding="utf-8", errors="replace") as f:
            for numero, ligne in enumerate(f, 1):
                for cible in MOTIF.findall(ligne):
                    if cible.startswith(TOLERES):
                        continue
                    yield os.path.relpath(chemin, RACINE), numero, cible


def test_il_y_a_bien_des_references_a_verifier():
    """Garde-fou : un motif cassé rendrait ce fichier silencieusement inutile."""
    assert len(list(_references())) >= 3


@pytest.mark.parametrize(
    "source,ligne,cible",
    [pytest.param(*r, id="%s:%d" % (r[0], r[1])) for r in _references()],
)
def test_la_cible_existe(source, ligne, cible):
    """Chaque /plugins/ProJote/... référencé doit exister sur le disque."""
    assert os.path.isfile(os.path.join(RACINE, cible)), (
        "%s ligne %d référence « %s », qui n'existe pas. "
        "Un renommage n'a pas été répercuté." % (source, ligne, cible)
    )
