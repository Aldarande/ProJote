"""Exécute l'essai PHP de la temporisation des messages « Pronote injoignable ».

Le dépôt n'a pas de PHPUnit, et il n'en mérite pas pour deux méthodes. Le
scénario vit donc dans `tests/php/essai_unreachable.php`, avec des doublures de
`cache`, `message` et `log` ; ce test ne fait que le lancer et lire son verdict.

Il est ignoré quand `php` n'est pas installé — le cas sur un poste Windows. La
CI, elle, le joue depuis le job « Lint PHP », qui a bien un interpréteur.
"""

import os
import shutil
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESSAI = os.path.join(RACINE, "tests", "php", "essai_unreachable.php")
CLASSE = os.path.join(RACINE, "core", "class", "ProJote.class.php")


@pytest.mark.skipif(shutil.which("php") is None, reason="php n'est pas installé")
def test_temporisation_des_messages():
    resultat = subprocess.run(
        [shutil.which("php"), ESSAI, CLASSE],
        capture_output=True,
        text=True,
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
