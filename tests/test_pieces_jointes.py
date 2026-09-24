"""Tests du rapatriement choisi des pièces jointes d'actualité.

Certains établissements publient le menu de la cantine en PDF attaché à une
actualité plutôt que dans l'onglet prévu. Le fichier était hors de portée du
plugin.

Deux contraintes encadrent la fonctionnalité :

* **on ne télécharge pas tout** — un établissement joint aussi des règlements
  intérieurs et des diaporamas de réunion. L'utilisateur choisit par mots-clés,
  et un champ vide ne rapatrie rien ;
* **le nom du fichier vient de Pronote**, il ne compose donc un chemin qu'une
  fois assaini. Un nom contenant « ../ » écrirait hors du dossier de
  l'équipement.

L'énumération, elle, est gratuite : `attachments()` réutilise la réponse déjà
obtenue pour le contenu de l'actualité. On peut donc toujours dire ce qui
existe, et ne prendre que ce qui a été demandé.
"""

import os

import pytest

import pieces_jointes


PRIS = {"actif": True, "mots": ["menu"], "retention": 30}


def _vieillir(tmp_path, heures=24):
    """Recule la date de dernière vérification, pour franchir VERIFICATION_MIN.

    Sans cela, un second appel dans la même seconde de test tomberait sur le
    délai de revérification et ne demanderait rien au serveur.
    """
    import json
    import time

    index_path = tmp_path / pieces_jointes.DOSSIER / pieces_jointes.INDEX
    index = json.loads(index_path.read_text())
    for entree in index.values():
        entree["verifie_le"] = time.time() - heures * 3600
    index_path.write_text(json.dumps(index))


class _Reponse:
    def __init__(self, contenu, code=200, entetes=None):
        self.status_code = code
        self._contenu = contenu
        self.headers = entetes or {}

    def iter_content(self, taille):
        for i in range(0, len(self._contenu), taille):
            yield self._contenu[i : i + taille]


class _Session:
    """Faux serveur de fichiers : compte les appels et sait répondre 304."""

    def __init__(self, contenu, entetes=None, code=200):
        self.contenu = contenu
        self.entetes = entetes or {}
        self.code = code
        self.appels = []

    def get(self, url, headers=None, stream=False, timeout=None):
        self.appels.append(dict(headers or {}))
        if self.code == 304:
            return _Reponse(b"", 304, self.entetes)
        return _Reponse(self.contenu, self.code, self.entetes)


class _Piece:
    """Doublure d'Attachment : nom, genre, et une charge à servir."""

    def __init__(self, nom, contenu=b"%PDF-1.4 ...", genre=1, session=None):
        self.name = nom
        self.type = genre
        self.url = "https://exemple.invalid/fichier"
        self._contenu = contenu
        self.sauvegardes = []
        self.session = session if session is not None else _Session(contenu)

        class _Communication:
            pass

        class _Client:
            pass

        self._client = _Client()
        self._client.communication = _Communication()
        self._client.communication.session = self.session

    def save(self, chemin):
        self.sauvegardes.append(chemin)
        with open(chemin, "wb") as sortie:
            sortie.write(self._contenu)


# ── Les mots-clés ───────────────────────────────────────────────────────────


class TestMotsCles:
    def test_un_champ_vide_ne_retient_rien(self):
        """Le défaut est de ne rien télécharger."""
        assert pieces_jointes.mots_cles("") == []
        assert pieces_jointes.mots_cles(None) == []

    def test_virgules_et_points_virgules(self):
        assert pieces_jointes.mots_cles("menu, cantine") == ["menu", "cantine"]
        assert pieces_jointes.mots_cles("menu;cantine") == ["menu", "cantine"]

    def test_casse_et_accents_ignores(self):
        """« Élève » et « eleve » doivent se valoir."""
        assert pieces_jointes.mots_cles("Menu, RESTAURATION") == ["menu", "restauration"]
        assert pieces_jointes.mots_cles("Élève") == ["eleve"]

    def test_les_morceaux_vides_sont_ecartes(self):
        assert pieces_jointes.mots_cles("menu,,  ,cantine") == ["menu", "cantine"]


class TestSelection:
    def test_le_mot_est_cherche_dans_le_nom_du_fichier(self):
        assert pieces_jointes.retenue("Menu_S39.pdf", "Actualité", ["menu"]) is True

    def test_le_mot_est_aussi_cherche_dans_le_titre(self):
        """Un PDF nommé « S39.pdf » sous une actualité « Menu de la semaine »."""
        assert pieces_jointes.retenue("S39.pdf", "Menu de la semaine", ["menu"]) is True

    def test_sans_mot_cle_rien_n_est_retenu(self):
        assert pieces_jointes.retenue("Menu_S39.pdf", "Menu", []) is False

    def test_un_fichier_hors_sujet_est_ignore(self):
        assert pieces_jointes.retenue(
            "Reglement_interieur.pdf", "Rentrée 2026", ["menu", "cantine"]
        ) is False

    def test_les_accents_du_cote_pronote_aussi(self):
        assert pieces_jointes.retenue("Menu_rentrée.pdf", "", ["rentree"]) is True


# ── Le nom sur disque ───────────────────────────────────────────────────────


class TestNomSurDisque:
    @pytest.mark.parametrize(
        "brut, attendu",
        [
            ("Menu_S39.pdf", "Menu_S39.pdf"),
            ("menu semaine 39.pdf", "menu_semaine_39.pdf"),
            ("Menu_rentrée.pdf", "Menu_rentree.pdf"),
        ],
    )
    def test_noms_ordinaires(self, brut, attendu):
        assert pieces_jointes.nom_sur_disque(brut) == attendu

    @pytest.mark.parametrize(
        "attaque",
        [
            "../../../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "/etc/shadow",
            "dossier/sous/fichier.pdf",
        ],
    )
    def test_aucun_nom_ne_sort_du_dossier(self, attaque):
        """Le nom vient de Pronote : il ne doit jamais composer un chemin."""
        propre = pieces_jointes.nom_sur_disque(attaque)
        assert propre is None or ("/" not in propre and "\\" not in propre)
        assert propre != ".."

    @pytest.mark.parametrize("vide", ["", None, "...", "///", "..."])
    def test_un_nom_inexploitable_est_refuse(self, vide):
        assert pieces_jointes.nom_sur_disque(vide) is None

    def test_le_nom_est_borne(self):
        """Un nom démesuré ne doit pas buter sur la limite du système."""
        assert len(pieces_jointes.nom_sur_disque("a" * 400 + ".pdf")) <= 120


# ── Le rapatriement ─────────────────────────────────────────────────────────


class TestRapatriement:
    def test_une_piece_hors_selection_est_signalee_sans_etre_prise(self, tmp_path):
        piece = _Piece("Reglement.pdf")

        decrit = pieces_jointes.decrire(piece, "Rentrée", PRIS, str(tmp_path))

        assert decrit["nom"] == "Reglement.pdf"
        assert decrit["recuperee"] is False
        assert decrit["fichier"] == ""
        assert piece.sauvegardes == [], "un fichier non retenu a été téléchargé"

    def test_une_piece_retenue_est_ecrite_sur_disque(self, tmp_path):
        piece = _Piece("Menu_S39.pdf")

        decrit = pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert decrit["recuperee"] is True
        assert decrit["fichier"] == "Menu_S39.pdf"
        attendu = tmp_path / pieces_jointes.DOSSIER / "Menu_S39.pdf"
        assert attendu.exists()

    def test_un_lien_n_est_jamais_telecharge(self, tmp_path):
        """Genre 0 = une URL, pas un fichier : il n'y a rien à rapatrier."""
        piece = _Piece("https://exemple.invalid/menu", genre=0)

        decrit = pieces_jointes.decrire(piece, "Menu", PRIS, str(tmp_path))

        assert decrit["lien"] is True
        assert decrit["recuperee"] is False
        assert piece.sauvegardes == []

    def test_le_second_passage_demande_si_le_fichier_a_change(self, tmp_path):
        """La requête conditionnelle porte les empreintes du premier passage."""
        piece = _Piece("Menu_S39.pdf", session=_Session(
            b"%PDF-1.4 menu", {"ETag": '"abc"', "Last-Modified": "Mon, 22 Sep 2026 08:00:00 GMT"}
        ))
        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))
        _vieillir(tmp_path)

        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert len(piece.session.appels) == 2
        assert piece.session.appels[1]["If-None-Match"] == '"abc"'
        assert "If-Modified-Since" in piece.session.appels[1]

    def test_un_304_conserve_le_fichier_en_place(self, tmp_path):
        """« Rien de neuf » : aucun octet transporté, rien de réécrit."""
        session = _Session(b"%PDF-1.4 menu", {"ETag": '"abc"'})
        piece = _Piece("Menu_S39.pdf", session=session)
        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))
        fichier = tmp_path / pieces_jointes.DOSSIER / "Menu_S39.pdf"
        empreinte_avant = fichier.read_bytes()
        _vieillir(tmp_path)

        session.code = 304
        decrit = pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert decrit["recuperee"] is True
        assert fichier.read_bytes() == empreinte_avant

    def test_un_serveur_qui_ignore_le_conditionnel_ne_reecrit_pas_pour_rien(self, tmp_path):
        """Certains serveurs renvoient 200 quoi qu'on demande : on compare nous-mêmes."""
        piece = _Piece("Menu_S39.pdf", session=_Session(b"%PDF-1.4 menu"))
        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))
        fichier = tmp_path / pieces_jointes.DOSSIER / "Menu_S39.pdf"
        date_avant = fichier.stat().st_mtime_ns
        _vieillir(tmp_path)

        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert fichier.stat().st_mtime_ns == date_avant, "le fichier a été réécrit"

    def test_un_contenu_different_remplace_le_fichier(self, tmp_path):
        """Le menu de la semaine suivante doit bien arriver."""
        session = _Session(b"semaine 39")
        piece = _Piece("Menu.pdf", session=session)
        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        _vieillir(tmp_path)
        session.contenu = b"semaine 40"
        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        fichier = tmp_path / pieces_jointes.DOSSIER / "Menu.pdf"
        assert fichier.read_bytes() == b"semaine 40"

    def test_sans_dossier_on_signale_sans_ecrire(self, tmp_path):
        """Le démon peut ne pas savoir où écrire : ce n'est pas une panne."""
        piece = _Piece("Menu_S39.pdf")

        decrit = pieces_jointes.decrire(piece, "Cantine", PRIS, None)

        assert decrit["nom"] == "Menu_S39.pdf"
        assert decrit["recuperee"] is False

    def test_une_remontee_de_dossier_est_neutralisee(self, tmp_path):
        """« ../menu » se ramène à « menu » : le fichier est pris, mais dedans.

        Neutraliser plutôt que refuser est délibéré — un nom malheureux ne doit
        pas priver l'utilisateur de son menu, du moment qu'il ne compose plus
        de chemin.
        """
        piece = _Piece("../menu")

        decrit = pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert decrit["recuperee"] is True
        assert decrit["fichier"] == "menu"
        assert (tmp_path / pieces_jointes.DOSSIER / "menu").exists()
        assert not (tmp_path.parent / "menu").exists()

    def test_un_nom_sans_rien_d_exploitable_est_refuse(self, tmp_path):
        """« ... » ne laisse aucun caractère sûr : on renonce au fichier."""
        piece = _Piece("...")

        decrit = pieces_jointes.decrire(piece, "menu", PRIS, str(tmp_path))

        assert decrit["recuperee"] is False
        assert piece.sauvegardes == []

    def test_un_echec_de_telechargement_est_rattrape(self, tmp_path):
        """Une panne réseau ne doit pas emporter la collecte des notifications."""

        class _SessionCassee(_Session):
            def get(self, url, headers=None, stream=False, timeout=None):
                raise IOError("réseau coupé")

        piece = _Piece("Menu_S39.pdf", session=_SessionCassee(b""))

        decrit = pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert decrit["recuperee"] is False

    def test_un_echec_ne_fait_pas_oublier_un_fichier_deja_la(self, tmp_path):
        """Le menu de la semaine reste consultable si le réseau tombe."""
        piece = _Piece("Menu_S39.pdf")
        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        class _SessionCassee(_Session):
            def get(self, url, headers=None, stream=False, timeout=None):
                raise IOError("réseau coupé")

        casse = _Piece("Menu_S39.pdf", session=_SessionCassee(b""))
        decrit = pieces_jointes.decrire(casse, "Cantine", PRIS, str(tmp_path))

        assert decrit["recuperee"] is True
        assert decrit["fichier"] == "Menu_S39.pdf"

    def test_le_fichier_reste_dans_le_dossier_de_l_equipement(self, tmp_path):
        """Quel que soit le nom annonce par Pronote."""
        piece = _Piece("../../menu-evade.pdf")

        decrit = pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert decrit["recuperee"] is True
        ecrit = os.path.join(str(tmp_path), pieces_jointes.DOSSIER, decrit["fichier"])
        racine = os.path.realpath(str(tmp_path))
        assert os.path.realpath(ecrit).startswith(racine)
        assert os.path.exists(ecrit)


# ── L'interrupteur et les réglages ──────────────────────────────────────────


class TestReglages:
    def test_desactive_par_defaut(self):
        """Rien ne doit partir tant que l'utilisateur n'a rien demandé."""
        r = pieces_jointes.reglages({})
        assert r["actif"] is False
        assert r["mots"] == []
        assert r["retention"] == pieces_jointes.RETENTION_DEFAUT

    def test_lecture_du_message(self):
        r = pieces_jointes.reglages({
            "PiecesJointesActif": 1,
            "PiecesJointesMots": "menu, cantine",
            "PiecesJointesRetention": "7",
        })
        assert r["actif"] is True
        assert r["mots"] == ["menu", "cantine"]
        assert r["retention"] == 7

    @pytest.mark.parametrize("brut", ["", None, "zero", "0", "-3"])
    def test_une_retention_absurde_retombe_sur_le_defaut(self, brut):
        r = pieces_jointes.reglages({"PiecesJointesRetention": brut})
        assert r["retention"] == pieces_jointes.RETENTION_DEFAUT

    def test_l_interrupteur_ferme_ne_telecharge_rien(self, tmp_path):
        """Même avec les bons mots-clés."""
        piece = _Piece("Menu_S39.pdf")
        options = {"actif": False, "mots": ["menu"], "retention": 30}

        decrit = pieces_jointes.decrire(piece, "Cantine", options, str(tmp_path))

        assert decrit["nom"] == "Menu_S39.pdf"
        assert decrit["recuperee"] is False
        assert piece.session.appels == []


# ── La rétention ────────────────────────────────────────────────────────────


class TestRetention:
    def _poser(self, tmp_path, nom, age_jours):
        """Pose un fichier rapatrié il y a `age_jours`, index compris."""
        import json
        import time

        cible = tmp_path / pieces_jointes.DOSSIER
        cible.mkdir(parents=True, exist_ok=True)
        (cible / nom).write_bytes(b"x")
        index_path = cible / pieces_jointes.INDEX
        index = json.loads(index_path.read_text()) if index_path.exists() else {}
        index[nom] = {"repris_le": time.time() - age_jours * 86400}
        index_path.write_text(json.dumps(index))

    def test_un_fichier_trop_vieux_est_efface(self, tmp_path):
        self._poser(tmp_path, "vieux.pdf", 45)

        efface = pieces_jointes.purger(str(tmp_path), 30)

        assert efface == 1
        assert not (tmp_path / pieces_jointes.DOSSIER / "vieux.pdf").exists()

    def test_un_fichier_recent_est_garde(self, tmp_path):
        self._poser(tmp_path, "recent.pdf", 3)

        assert pieces_jointes.purger(str(tmp_path), 30) == 0
        assert (tmp_path / pieces_jointes.DOSSIER / "recent.pdf").exists()

    def test_l_age_se_compte_depuis_le_telechargement_pas_la_verification(self, tmp_path):
        """Un menu revérifié ce matin mais inchangé depuis six semaines s'en va."""
        self._poser(tmp_path, "menu.pdf", 42)
        # Le fichier a été touché aujourd'hui par une vérification.
        os.utime(str(tmp_path / pieces_jointes.DOSSIER / "menu.pdf"), None)

        assert pieces_jointes.purger(str(tmp_path), 30) == 1

    def test_l_index_n_est_jamais_efface(self, tmp_path):
        self._poser(tmp_path, "vieux.pdf", 45)

        pieces_jointes.purger(str(tmp_path), 30)

        assert (tmp_path / pieces_jointes.DOSSIER / pieces_jointes.INDEX).exists()

    def test_purger_un_dossier_absent_ne_leve_pas(self, tmp_path):
        assert pieces_jointes.purger(str(tmp_path / "inexistant"), 30) == 0
        assert pieces_jointes.purger(None, 30) == 0

    def test_un_fichier_sans_index_retombe_sur_sa_date_systeme(self, tmp_path):
        """Fichier posé avant l'existence de l'index : il ne doit pas rester à vie."""
        import time

        cible = tmp_path / pieces_jointes.DOSSIER
        cible.mkdir(parents=True)
        vieux = cible / "orphelin.pdf"
        vieux.write_bytes(b"x")
        ancien = time.time() - 60 * 86400
        os.utime(str(vieux), (ancien, ancien))

        assert pieces_jointes.purger(str(tmp_path), 30) == 1


# ── Le délai de revérification ──────────────────────────────────────────────
#
# La requête conditionnelle devait rendre la vérification gratuite. Mesuré sur
# un serveur PRONOTE réel le 24 septembre 2026 : il ignore « If-Modified-Since »
# et renvoie le fichier entier. Vérifier coûte donc le transfert complet, et les
# notifications sont collectées huit fois par jour.


class TestDelaiDeVerification:
    def test_un_fichier_verifie_recemment_n_est_pas_redemande(self, tmp_path):
        piece = _Piece("Menu_S39.pdf")
        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))
        appels_apres_premier = len(piece.session.appels)

        decrit = pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert len(piece.session.appels) == appels_apres_premier, (
            "le serveur a été sollicité alors que le fichier venait d'être vu"
        )
        assert decrit["recuperee"] is True, "le fichier reste disponible"

    def test_passe_le_delai_on_revient_demander(self, tmp_path):
        piece = _Piece("Menu_S39.pdf")
        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))
        _vieillir(tmp_path, heures=13)

        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert len(piece.session.appels) == 2

    def test_un_fichier_efface_est_repris_sans_attendre(self, tmp_path):
        """La rétention l'a emporté, ou l'utilisateur l'a supprimé."""
        piece = _Piece("Menu_S39.pdf")
        pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))
        (tmp_path / pieces_jointes.DOSSIER / "Menu_S39.pdf").unlink()

        decrit = pieces_jointes.decrire(piece, "Cantine", PRIS, str(tmp_path))

        assert len(piece.session.appels) == 2
        assert decrit["recuperee"] is True
