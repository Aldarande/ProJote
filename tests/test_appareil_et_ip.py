"""Tests de deux correctifs de pronote_compat signalés par un utilisateur.

1. Nom d'appareil : quand l'établissement impose l'enregistrement des
   appareils, pronotepy exige un nom (« A device identifier is required for
   this account ») que ProJote ne transmettait pas.
2. Fausse suspension d'IP : pronotepy concluait à une IP suspendue dès que la
   page contenait « IP », par exemple dans le nom d'un collège SAINT-PHILIPPE.

Ces tests fabriquent leur propre pronotepy : ni réseau, ni dépendance.
"""

import importlib
import sys
import types

import pytest


@pytest.fixture
def compat(monkeypatch):
    class PronoteAPIError(Exception):
        pass

    class MFAError(PronoteAPIError):
        pass

    appels = []

    class ClientBase:
        def _do_2fa(self, doVerifyPin=False, doRegisterDevice=False, pin=None, identifier=None):
            if doRegisterDevice and identifier is None:
                raise MFAError("A device identifier is required for this account")
            appels.append((doVerifyPin, doRegisterDevice, pin, identifier))

    class _Communication:
        def _parse_html(self, html):  # comportement d'origine de pronotepy
            if "IP" in html:
                raise PronoteAPIError("Your IP address is suspended.")
            return {}

    pronotepy = types.ModuleType("pronotepy")
    clients = types.ModuleType("pronotepy.clients")
    clients.ClientBase = ClientBase
    api = types.ModuleType("pronotepy.pronoteAPI")
    api._Communication = _Communication
    exc = types.ModuleType("pronotepy.exceptions")
    exc.PronoteAPIError = PronoteAPIError
    pronotepy.clients, pronotepy.pronoteAPI, pronotepy.exceptions = clients, api, exc
    for nom, mod in (("pronotepy", pronotepy), ("pronotepy.clients", clients),
                     ("pronotepy.pronoteAPI", api), ("pronotepy.exceptions", exc)):
        monkeypatch.setitem(sys.modules, nom, mod)

    import pronote_compat

    module = importlib.reload(pronote_compat)
    module._installer_nom_appareil()
    module._installer_detection_ip()
    module.ClientBase, module.Communication = ClientBase, _Communication
    module.PronoteAPIError, module.appels = PronoteAPIError, appels
    return module


PAGE = (
    "<html><head><title>PRONOTE - COLLEGE SAINT-PHILIPPE</title></head>"
    "<body onload=\"try { Start ({h:'1234',a:3,d:true,MR:'ABCDEF',ER:'10001'}) } catch (e) {}\">"
    "</body></html>"
)


class TestNomAppareil:
    def test_nom_par_defaut_quand_pronote_demande_l_enregistrement(self, compat):
        compat.ClientBase()._do_2fa(False, True, None, None)
        assert compat.appels == [(False, True, None, "Domotique")]

    def test_nom_configure(self, compat):
        compat.definir_nom_appareil("  Box   du salon ")
        compat.ClientBase()._do_2fa(False, True, None, None)
        assert compat.appels[-1][3] == "Box du salon"

    def test_nom_vide_ou_trop_long(self, compat):
        assert compat.definir_nom_appareil("") == "Domotique"
        assert compat.definir_nom_appareil(None) == "Domotique"
        assert len(compat.definir_nom_appareil("x" * 80)) == 40

    def test_nom_explicite_respecte_et_rien_sans_enregistrement(self, compat):
        compat.ClientBase()._do_2fa(False, True, None, "Choisi")
        compat.ClientBase()._do_2fa(True, False, "1234", None)
        assert compat.appels == [(False, True, None, "Choisi"), (True, False, "1234", None)]

    def test_installation_idempotente(self, compat):
        avant = compat.ClientBase._do_2fa
        compat._installer_nom_appareil()
        assert compat.ClientBase._do_2fa is avant


class TestDetectionIP:
    def test_ip_dans_un_nom_de_ville_n_est_pas_une_suspension(self, compat):
        attributs = compat.Communication()._parse_html(PAGE)
        assert attributs["h"] == "1234" and attributs["MR"] == "ABCDEF"

    @pytest.mark.parametrize("page", [
        "<html><body>Votre adresse IP est provisoirement suspendue.</body></html>",
        "<html><body>Accès SUSPENDU temporairement</body></html>",
        "<html><body>IP bloquée</body></html>",
    ])
    def test_vraie_suspension_toujours_detectee(self, compat, page):
        with pytest.raises(compat.PronoteAPIError, match="IP address is suspended"):
            compat.Communication()._parse_html(page)

    def test_page_inattendue(self, compat):
        with pytest.raises(compat.PronoteAPIError, match="different than expected"):
            compat.Communication()._parse_html("<html><title>SAINT-PHILIPPE</title></html>")

    def test_page_sans_h_reessayee(self, compat):
        with pytest.raises(ValueError):
            compat.Communication()._parse_html("<body onload=\"Start ({a:3})\">SAINT-PHILIPPE</body>")

    def test_reconnu_par_pronote_errors(self, compat):
        import pronote_errors

        try:
            compat.Communication()._parse_html("<body>adresse IP suspendue</body>")
        except compat.PronoteAPIError as e:
            assert pronote_errors.is_ip_suspension_error(e)
