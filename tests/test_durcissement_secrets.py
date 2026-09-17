"""Tests du durcissement issu de l'audit de sécurité (findings L1 à L4).

Quatre comportements relevés par SECURITY-AUDIT.md et corrigés ensemble, parce
qu'ils partagent la même racine : un secret illisible n'était traité nulle part
comme tel.

* **L4** — le démon appelait ``exit(1)`` quand un déchiffrement échouait. Le
  démon sert *tous* les équipements ProJote de l'installation : un seul secret
  illisible emportait la collecte de tous les autres enfants.
* **L1** — la validation par identifiants renvoyait le **chiffré brut** en guise
  de mot de passe. Il partait tel quel vers Pronote, qui le refusait : échec
  garanti, et rien dans les journaux pour en désigner la cause.
* **L3** — l'identifiant d'équipement, reçu du socket, composait directement un
  chemin de fichier.
* **L2** — côté PHP, les actions AJAX chargeaient un équipement sans vérifier
  qu'il appartenait bien à ProJote (non testable ici, faute d'interpréteur PHP).
"""

import base64
import json
import os

import pytest

import pronote_errors
import secret_jeedom
import token_secours

APIKEY = "cle-api-jeedom-de-test"


def _chiffrer(clair, apikey=APIKEY):
    """Chiffre comme ProJote::my_encrypt() : AES-256-CBC + PKCS#7, enveloppe JSON."""
    import os as _os

    from Crypto.Cipher import AES

    cle = bytes.fromhex(secret_jeedom.cle_depuis_apikey(apikey))
    iv = _os.urandom(16)
    n = 16 - len(clair.encode()) % 16
    chiffre = AES.new(cle, AES.MODE_CBC, iv).encrypt(clair.encode() + bytes([n]) * n)
    return base64.b64encode(
        json.dumps(
            {
                "iv": base64.b64encode(iv).decode(),
                "data": base64.b64encode(chiffre).decode(),
            }
        ).encode()
    ).decode()


# ── L4 — un secret illisible ne tue plus le démon ───────────────────────────


def test_my_decrypt_leve_au_lieu_de_tuer_le_demon(daemon):
    """Une donnée indéchiffrable lève, elle n'appelle plus exit()."""
    with pytest.raises(pronote_errors.DechiffrementImpossible):
        daemon.my_decrypt("ceci-n-est-pas-du-base64-chiffre")


def test_my_decrypt_ne_leve_pas_systemexit(daemon):
    """Garde-fou explicite : SystemExit signerait le retour de l'exit(1)."""
    try:
        daemon.my_decrypt("charge-illisible")
    except pronote_errors.DechiffrementImpossible:
        pass
    except SystemExit:  # pragma: no cover - ne doit jamais arriver
        pytest.fail("my_decrypt a appelé exit() : le démon entier tomberait.")


def test_connect_rend_none_sur_secret_illisible(daemon):
    """Connect() abandonne cet équipement et laisse tourner les autres."""
    assert (
        daemon.Connect(
            pronote_url="https://exemple.index-education.net/pronote/eleve.html",
            login="clara",
            password="secret-illisible",
            ent="",
        )
        is None
    )


def test_connectparent_rend_none_sur_secret_illisible(daemon):
    """Connectparent() suit la même règle et rend sa paire (client, enfants)."""
    client, enfants = daemon.Connectparent(
        pronote_url="https://exemple.index-education.net/pronote/parent.html",
        login="parent",
        password="secret-illisible",
        ent="",
        enfant="",
    )
    assert client is None
    assert enfants == []


# ── L3 — l'identifiant d'équipement ne compose plus un chemin tel quel ──────


@pytest.mark.parametrize("valeur, attendu", [(7, "7"), ("7", "7"), (" 12 ", "12")])
def test_id_equipement_accepte_les_entiers(daemon, valeur, attendu):
    assert daemon._id_equipement(valeur) == attendu


@pytest.mark.parametrize("valeur", ["../../etc", "7/../8", "", None, "12; rm -rf /"])
def test_id_equipement_refuse_le_reste(daemon, valeur):
    """Refusé, pas nettoyé : « ../7 » ne doit pas devenir discrètement « 7 »."""
    with pytest.raises(ValueError):
        daemon._id_equipement(valeur)


def test_id_equipement_normalise_les_chiffres_exotiques(daemon):
    """int() accepte les chiffres Unicode ; le rendu reste de l'ASCII canonique.

    « ٧ » (chiffre arabo-indien sept) vaut 7 pour int(). Le passage par
    str(int(...)) le ramène à « 7 » : rien d'exotique n'atteint le chemin.
    """
    assert daemon._id_equipement("٧") == "7"


def test_dossier_equipement_reste_sous_la_racine(daemon, tmp_path):
    dossier = daemon._dossier_equipement(str(tmp_path), 42)
    assert os.path.dirname(dossier) == str(tmp_path)


def test_seen_index_refuse_un_identifiant_de_traversee(daemon, tmp_path):
    """L'identifiant est validé avant toute lecture : rien n'est ouvert.

    L'erreur remonte plutôt que de rendre un index vide : process_message la
    rattrape et la journalise, là où un {} silencieux ferait passer une
    tentative de traversée pour un premier cycle ordinaire.
    """
    with pytest.raises(ValueError):
        daemon._load_seen_index(str(tmp_path), "../../etc/passwd")


def test_seen_index_reste_nominal(daemon, tmp_path):
    """Le chemin normal continue de fonctionner : absent = index vide."""
    assert daemon._load_seen_index(str(tmp_path), 4) == {}
    daemon._save_seen_index(str(tmp_path), 4, {"note": ["sig"]})
    assert daemon._load_seen_index(str(tmp_path), 4) == {"note": ["sig"]}


def test_chemin_du_jeton_de_secours_refuse_la_traversee():
    with pytest.raises(ValueError):
        token_secours._chemin("/tmp", "../../root")


def test_chemin_du_jeton_de_secours_reste_nominal(tmp_path):
    chemin = token_secours._chemin(str(tmp_path), 4)
    assert chemin == os.path.join(str(tmp_path), "4", token_secours.NOM_FICHIER)


# ── L1 — plus de repli silencieux sur le chiffré brut ───────────────────────


def _source_login_connect():
    ici = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(
        os.path.dirname(ici), "resources", "ProJoted", "LoginConnect.py"
    )
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def test_login_connect_ne_renvoie_plus_le_chiffre_brut():
    """LoginConnect n'est pas importable en test (bloc principal, ENT, argparse).

    Le contrôle se fait donc sur la source : c'est le repli lui-même qu'on
    interdit de revenir, avec sa formulation d'origine.
    """
    source = _source_login_connect()
    assert "return data  # Retourne brut si échec" not in source
    # Le déchiffrement est délégué au module partagé, qui lève.
    assert "secret_jeedom.dechiffrer(data, passphrase)" in source


def test_login_connect_sort_sur_un_code_dedie():
    source = _source_login_connect()
    assert "sys.exit(DECHIFFREMENT_EXIT_CODE)" in source


def test_code_de_sortie_dedie_et_distinct():
    """9 : les codes 3 à 8 sont déjà pris (QR Code, dépendances, IP, jeton)."""
    assert pronote_errors.DECHIFFREMENT_EXIT_CODE == 9
    assert pronote_errors.DECHIFFREMENT_EXIT_CODE not in (
        pronote_errors.IP_SUSPENSION_EXIT_CODE,
        pronote_errors.NO_MOBILE_TOKEN_EXIT_CODE,
    )


def test_ajax_php_traite_le_code_dedie():
    """Sans ce branchement PHP, l'utilisateur ne verrait qu'une erreur générique."""
    ici = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(
        os.path.dirname(ici), "core", "ajax", "ProJote.ajax.php"
    )
    with open(chemin, encoding="utf-8") as f:
        source = f.read()
    assert "$return_var === 9" in source


# ── L2 — contrôle du type d'équipement côté PHP ─────────────────────────────


def test_ajax_php_verifie_le_type_d_equipement():
    """Aucune action ne doit plus charger un équipement sans contrôler son type."""
    ici = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(
        os.path.dirname(ici), "core", "ajax", "ProJote.ajax.php"
    )
    with open(chemin, encoding="utf-8") as f:
        source = f.read()
    assert "function projoteChargerEquipement" in source
    assert "getEqType_name() !== 'ProJote'" in source
    # Plus aucune action ne charge son équipement de travail directement.
    assert "$eqLogic = eqLogic::byId(" not in source
    # Restent les deux lectures d'UUID, qui tolèrent l'absence d'équipement
    # (validation avant première sauvegarde) : elles portent le contrôle en
    # ligne plutôt que d'échouer.
    assert source.count("$eqLogicForUuid->getEqType_name() === 'ProJote'") == 2


# ── Le piège qui rendait L1 et L4 inopérants : un remplissage non vérifié ───
#
# Relevé le 17 septembre 2026 en rejouant une clé API différente sur le compte
# de démonstration. Les deux déchiffrements retiraient le remplissage PKCS#7
# ainsi : `unpad = lambda s: s[: -s[-1]]`, sans le vérifier. Avec une mauvaise
# clé, les seize octets obtenus sont aléatoires ; dès que le dernier dépasse la
# taille d'un bloc — quinze fois sur seize — cette expression rend une chaîne
# **vide**. Aucune exception n'était donc levée : ni le repli du démon ni celui
# de la validation ne se déclenchaient, et Pronote refusait un mot de passe vide
# sous le libellé « identifiants incorrects ».


def test_padding_valide_est_retire():
    assert secret_jeedom.retirer_padding(b"abc" + bytes([13]) * 13) == b"abc"


def test_bloc_entierement_de_remplissage():
    """Un secret d'exactement 16 octets porte un bloc de remplissage complet."""
    assert secret_jeedom.retirer_padding(b"a" * 16 + bytes([16]) * 16) == b"a" * 16


@pytest.mark.parametrize(
    "octets, pourquoi",
    [
        (b"", "charge vide"),
        (b"abc", "longueur non multiple de 16"),
        (b"a" * 15 + bytes([0]), "remplissage annoncé nul"),
        (b"a" * 15 + bytes([200]), "remplissage annoncé plus grand qu'un bloc"),
        (b"a" * 13 + bytes([1, 2, 3]), "octets de remplissage incohérents"),
    ],
)
def test_padding_invalide_est_refuse(octets, pourquoi):
    with pytest.raises(pronote_errors.DechiffrementImpossible):
        secret_jeedom.retirer_padding(octets)


def test_aller_retour_avec_la_bonne_cle():
    """Non-régression : un secret valide se déchiffre à l'identique."""
    chiffre = _chiffrer("pronotevs")
    clair = secret_jeedom.dechiffrer(
        chiffre, secret_jeedom.cle_depuis_apikey(APIKEY)
    )
    assert clair == "pronotevs"


def test_secret_de_seize_octets_pile():
    """Le cas limite du bloc plein passe aussi par le chemin complet."""
    secret = "0123456789abcdef"
    chiffre = _chiffrer(secret)
    assert (
        secret_jeedom.dechiffrer(chiffre, secret_jeedom.cle_depuis_apikey(APIKEY))
        == secret
    )


def test_mauvaise_cle_leve_au_lieu_de_rendre_une_chaine_vide():
    """Le cœur du piège : l'échec doit être bruyant, pas un mot de passe vide."""
    chiffre = _chiffrer("pronotevs", apikey="une-autre-cle-api")
    with pytest.raises(pronote_errors.DechiffrementImpossible):
        secret_jeedom.dechiffrer(chiffre, secret_jeedom.cle_depuis_apikey(APIKEY))


def test_mauvaise_cle_ne_rend_jamais_rien_de_silencieux():
    """Sur cinquante clés fausses, aucune ne doit passer en silence.

    Une par une, la probabilité qu'un remplissage aléatoire soit valide est
    faible mais non nulle ; ce qui compte est qu'aucune ne rende une valeur
    utilisable comme mot de passe sans le signaler.
    """
    for i in range(50):
        chiffre = _chiffrer("pronotevs", apikey=f"cle-fausse-{i}")
        try:
            obtenu = secret_jeedom.dechiffrer(
                chiffre, secret_jeedom.cle_depuis_apikey(APIKEY)
            )
        except pronote_errors.DechiffrementImpossible:
            continue
        pytest.fail(
            f"clé fausse n°{i} : déchiffrement silencieux, résultat {obtenu!r}"
        )


def test_charge_illisible_leve_aussi():
    with pytest.raises(pronote_errors.DechiffrementImpossible):
        secret_jeedom.dechiffrer("pas-du-base64", secret_jeedom.cle_depuis_apikey(APIKEY))


def test_demon_et_validation_partagent_le_meme_dechiffrement():
    """Une vérification de sécurité dupliquée finit par diverger."""
    for fichier in ("ProJoted.py", "LoginConnect.py"):
        chemin = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "resources",
            "ProJoted",
            fichier,
        )
        with open(chemin, encoding="utf-8") as f:
            source = f.read()
        assert "secret_jeedom.dechiffrer(" in source, fichier
        assert "unpad = lambda s: s[: -s[-1]]" not in source, fichier


# ── Un refus d'identifiants ne passe plus pour une réussite ─────────────────


def test_code_de_sortie_identifiants_refuses():
    assert pronote_errors.IDENTIFIANTS_REFUSES_EXIT_CODE == 10
    codes = (
        pronote_errors.IP_SUSPENSION_EXIT_CODE,
        pronote_errors.NO_MOBILE_TOKEN_EXIT_CODE,
        pronote_errors.DECHIFFREMENT_EXIT_CODE,
        pronote_errors.IDENTIFIANTS_REFUSES_EXIT_CODE,
    )
    assert len(set(codes)) == len(codes)


def test_login_connect_sort_sur_un_refus_d_identifiants():
    """pronotepy ne lève pas sur un refus : il rend un client non connecté.

    Sans ce garde, le script finissait sur 0 — « validation réussie » pour
    l'interface — alors qu'aucun compte n'avait été écrit.
    """
    source = _source_login_connect()
    assert "sys.exit(IDENTIFIANTS_REFUSES_EXIT_CODE)" in source
    assert "if Account is None or not Account.logged_in:" in source


def test_ajax_php_traite_le_refus_d_identifiants():
    ici = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(os.path.dirname(ici), "core", "ajax", "ProJote.ajax.php")
    with open(chemin, encoding="utf-8") as f:
        source = f.read()
    assert "$return_var === 10" in source
