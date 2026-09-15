"""Tests de la reconnaissance des serveurs de démonstration PRONOTE.

Le site de démonstration d'Index Éducation ne délivre aucun jeton d'application
mobile : ``JetonAppliMobile`` y répond 200 avec une charge vide. Aucun compte de
démonstration ne pouvait donc être enregistré, alors que ce sont justement les
comptes qui permettent d'éprouver le plugin sans toucher aux données scolaires
d'un enfant réel.

Ces serveurs — et eux seuls — se connectent par identifiants à chaque cycle.
C'est une exception à la règle « jamais de mot de passe conservé », et elle ne
tient que parce que les identifiants de la démonstration sont publics.

D'où la sévérité de ces tests : la porte doit être étroite. Un établissement
réel ne doit jamais pouvoir l'emprunter, ni par un sous-domaine qui ressemble,
ni par une URL forgée.
"""

import pronote_demo
import pytest

DEMO_PARENT = "https://demo.index-education.net/pronote/parent.html"
DEMO_ELEVE = "https://demo.index-education.net/pronote/eleve.html"
REEL = "https://0000000a.index-education.net/pronote/mobile.parent.html"


class TestEstServeurDemo:
    @pytest.mark.parametrize(
        "url",
        [
            DEMO_PARENT,
            DEMO_ELEVE,
            "https://demo.index-education.net/pronote/mobile.parent.html?fd=1",
            "http://demo.index-education.net/pronote/",
            "HTTPS://DEMO.INDEX-EDUCATION.NET/pronote/parent.html",
            "  https://demo.index-education.net/pronote/parent.html  ",
        ],
    )
    def test_hotes_de_demonstration(self, url):
        assert pronote_demo.est_serveur_demo(url)

    @pytest.mark.parametrize(
        "url",
        [
            REEL,
            "https://0000000b.index-education.net/pronote/parent.html",
            # Sous-domaine qui commence par « demo » sans être la démonstration.
            "https://demo2.index-education.net/pronote/parent.html",
            "https://demonstration.index-education.net/pronote/parent.html",
            # L'hôte de démonstration relégué en chemin, en identifiant ou en
            # paramètre : autant de façons de tenter de forcer la porte.
            "https://mon-etablissement.fr/demo.index-education.net/pronote/",
            "https://demo.index-education.net.attaquant.fr/pronote/",
            "https://attaquant.fr/?x=demo.index-education.net",
            "https://demo.index-education.net@attaquant.fr/pronote/",
        ],
    )
    def test_tout_le_reste_est_refuse(self, url):
        assert not pronote_demo.est_serveur_demo(url)

    @pytest.mark.parametrize("valeur", ["", None, 42, [], {}, "pas une url"])
    def test_entrees_invalides(self, valeur):
        assert not pronote_demo.est_serveur_demo(valeur)


class TestEstCompteDemo:
    def _message(self, **extra):
        base = {
            "url": DEMO_PARENT,
            "login": "demonstration",
            "password": "pronotevs",
        }
        base.update(extra)
        return base

    def test_cas_nominal(self):
        assert pronote_demo.est_compte_demo(self._message())

    def test_url_seulement_dans_le_jeton(self):
        """Une validation réussie a pu renseigner TokenUrl et laisser url vide."""
        msg = self._message(url="", TokenUrl=DEMO_ELEVE)
        assert pronote_demo.est_compte_demo(msg)

    @pytest.mark.parametrize("champ", ["login", "password"])
    def test_identifiants_manquants(self, champ):
        """Sans identifiants il n'y a rien à tenter : laisser le chemin normal
        produire son message d'erreur habituel."""
        assert not pronote_demo.est_compte_demo(self._message(**{champ: ""}))
        assert not pronote_demo.est_compte_demo(self._message(**{champ: "   "}))

    def test_etablissement_reel_avec_identifiants(self):
        """Le cœur de la garantie : des identifiants ne suffisent pas.

        Un équipement réel en mode « Login » porte lui aussi un login et un mot
        de passe en configuration. Seul l'hôte doit ouvrir ce chemin.
        """
        assert not pronote_demo.est_compte_demo(self._message(url=REEL))

    def test_message_qui_n_est_pas_un_dictionnaire(self):
        for valeur in (None, "", [], 0):
            assert not pronote_demo.est_compte_demo(valeur)

    def test_identifiants_publics_documentes(self):
        """La constante sert de repère : elle ne doit pas être injectée."""
        assert pronote_demo.IDENTIFIANTS_PUBLICS == ("demonstration", "pronotevs")
