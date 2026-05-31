"""Configuration pytest pour les tests du démon ProJote.

Le démon `ProJoted.py` importe au chargement plusieurs dépendances externes
(pronotepy, Crypto, requests) et des modules locaux du framework Jeedom
(jeedom.jeedom, LoginConnect). Pour des tests unitaires hermétiques et rapides,
on enregistre des stubs légers dans sys.modules AVANT d'importer le démon.

Le module ProJoted étant désormais protégé par `if __name__ == "__main__"`,
son import ne démarre pas le démon (pas de socket, pas de signaux, pas de
parsing d'arguments) : seules les définitions de fonctions sont exécutées.
"""

import os
import sys
import types

import pytest

# ── Chemins ─────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAEMON_DIR = os.path.join(ROOT, "resources", "ProJoted")
if DAEMON_DIR not in sys.path:
    sys.path.insert(0, DAEMON_DIR)


def _register(name):
    """Crée un module factice (vrai ModuleType) et l'enregistre dans sys.modules."""
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _install_stubs():
    """Installe les stubs des dépendances externes nécessaires à l'import."""
    # requests : utilisé pour le téléchargement d'images uniquement.
    if "requests" not in sys.modules:
        requests = _register("requests")
        requests.get = lambda *a, **k: None

    # pronotepy + sous-modules ent et dataClasses (monkey-patchés à l'import).
    if "pronotepy" not in sys.modules:
        pronotepy = _register("pronotepy")
        ent = _register("pronotepy.ent")
        data_classes = _register("pronotepy.dataClasses")
        pronotepy.ent = ent
        pronotepy.dataClasses = data_classes

        class Grade:  # noqa: D401 - stub
            def __init__(self, json_data):
                self.json_data = json_data

        class Util:  # noqa: D401 - stub
            @staticmethod
            def html_parse(html_text):
                return html_text or ""

        data_classes.Grade = Grade
        data_classes.Util = Util

    # Crypto.Cipher.AES (pycryptodome) : utilisé pour le déchiffrement.
    if "Crypto" not in sys.modules:
        crypto = _register("Crypto")
        cipher = _register("Crypto.Cipher")
        crypto.Cipher = cipher

        class AES:  # noqa: D401 - stub
            MODE_CBC = 2

        cipher.AES = AES

    # LoginConnect : module local du plugin (connexion Pronote).
    if "LoginConnect" not in sys.modules:
        login = _register("LoginConnect")
        login.writedataPronotepy = lambda *a, **k: None

    # jeedom.jeedom : framework démon Jeedom. Importé via `from jeedom.jeedom import *`.
    if "jeedom" not in sys.modules:
        jeedom_pkg = _register("jeedom")
        jeedom_mod = _register("jeedom.jeedom")
        jeedom_pkg.jeedom = jeedom_mod

        class _Dummy:
            def __getattr__(self, _name):
                return lambda *a, **k: None

        jeedom_mod.jeedom_utils = _Dummy()
        jeedom_mod.jeedom_com = object
        jeedom_mod.jeedom_socket = object
        jeedom_mod.__all__ = ["jeedom_utils", "jeedom_com", "jeedom_socket"]


_install_stubs()


@pytest.fixture(scope="session")
def daemon():
    """Importe le module ProJoted (une seule fois) avec les stubs en place."""
    import ProJoted  # noqa: E402 - import après installation des stubs

    return ProJoted
