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


# ── L4 — le démon ne déchiffre plus rien du tout ────────────────────────────
#
# Le finding L4 visait l'exit(1) de ProJoted.my_decrypt(). En préparant le
# passage à AES-GCM, la lecture du code a montré que cette fonction n'était
# atteignable que depuis Connect() et Connectparent() — deux fonctions que rien
# n'appelait. process_message n'a que trois chemins : compte de démonstration,
# jeton, et « aucun jeton disponible » qui rend la main.
#
# Le correctif de la v1.4.7 portait donc, pour le démon, sur du code mort ; il
# reste entier pour LoginConnect, où le même défaut était bien atteint à chaque
# validation par identifiants. Les trois fonctions ont été supprimées, et ces
# tests gardent leur absence : les faire revenir remettrait une seconde copie du
# déchiffrement, et c'est la divergence des deux copies qui avait laissé passer
# le remplissage non vérifié.


def test_le_demon_ne_porte_plus_de_dechiffrement(daemon):
    for nom in ("my_decrypt", "Connect", "Connectparent"):
        assert not hasattr(daemon, nom), (
            f"{nom}() est revenue dans le démon : code mort, et seconde copie "
            "du déchiffrement"
        )


def test_le_demon_ne_se_connecte_que_par_jeton_ou_demonstration(daemon):
    """Garde du fait qui rend ce code mort : il n'y a pas de troisième chemin."""
    import inspect

    source = inspect.getsource(daemon.process_message)
    assert "connexion_demo(message)" in source
    assert "token_login(" in source
    assert "Aucun token disponible" in source


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


def test_le_dechiffrement_ne_vit_qu_a_un_endroit():
    """Une vérification de sécurité dupliquée finit par diverger.

    C'est exactement ce qui s'était produit : deux copies du déchiffrement, et
    un remplissage non vérifié dans les deux. Il n'en reste qu'une, appelée par
    LoginConnect — seul chemin où un secret chiffré arrive réellement.
    """
    racine = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources",
        "ProJoted",
    )
    with open(os.path.join(racine, "LoginConnect.py"), encoding="utf-8") as f:
        assert "secret_jeedom.dechiffrer(" in f.read()

    # secret_jeedom.py est exclu : sa documentation cite l'expression fautive
    # pour expliquer ce qu'elle faisait. C'est du texte, pas du code.
    for fichier in ("ProJoted.py", "LoginConnect.py"):
        with open(os.path.join(racine, fichier), encoding="utf-8") as f:
            assert "unpad = lambda s: s[: -s[-1]]" not in f.read(), fichier


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


# ── M3 — AES-256-GCM, et ce que l'audit supposait à tort ────────────────────
#
# L'audit recommandait AES-GCM « avec re-chiffrement transparent au premier
# accès ». La lecture du code a montré qu'il n'y a rien à migrer : `my_encrypt`
# n'est appelé qu'à un seul endroit, ProJote.ajax.php, pour passer le mot de
# passe au script de validation en argument de ligne de commande. Le chiffré ne
# vit que le temps d'une requête. Le secret conservé en base, lui, est chiffré
# par le cœur de Jeedom ($_encryptConfigKey), pas par ce code.
#
# GCM apporte donc ici une chose précise : une charge altérée est refusée, là où
# CBC la déchiffrait en octets quelconques que rien ne distinguait d'un mot de
# passe.


def _chiffrer_gcm(clair, apikey=APIKEY):
    """Chiffre comme ProJote::my_encrypt() depuis la v1.7.0 : AES-256-GCM."""
    import os as _os

    from Crypto.Cipher import AES

    cle = bytes.fromhex(secret_jeedom.cle_depuis_apikey(apikey))
    iv = _os.urandom(12)
    chiffre, tag = AES.new(cle, AES.MODE_GCM, nonce=iv).encrypt_and_digest(clair.encode())
    return base64.b64encode(
        json.dumps(
            {
                "v": 2,
                "iv": base64.b64encode(iv).decode(),
                "data": base64.b64encode(chiffre).decode(),
                "tag": base64.b64encode(tag).decode(),
            }
        ).encode()
    ).decode()


def test_gcm_aller_retour():
    chiffre = _chiffrer_gcm("pronotevs")
    assert (
        secret_jeedom.dechiffrer(chiffre, secret_jeedom.cle_depuis_apikey(APIKEY))
        == "pronotevs"
    )


def test_gcm_refuse_une_charge_alteree():
    """Le gain de GCM sur CBC, en un test."""
    chiffre = _chiffrer_gcm("pronotevs")
    enveloppe = json.loads(base64.b64decode(chiffre).decode())
    octets = bytearray(base64.b64decode(enveloppe["data"]))
    octets[0] ^= 0x01
    enveloppe["data"] = base64.b64encode(bytes(octets)).decode()
    altere = base64.b64encode(json.dumps(enveloppe).encode()).decode()

    with pytest.raises(pronote_errors.DechiffrementImpossible):
        secret_jeedom.dechiffrer(altere, secret_jeedom.cle_depuis_apikey(APIKEY))


def test_gcm_refuse_un_tag_valide_pour_une_autre_cle():
    chiffre = _chiffrer_gcm("pronotevs", apikey="une-autre-cle")
    with pytest.raises(pronote_errors.DechiffrementImpossible):
        secret_jeedom.dechiffrer(chiffre, secret_jeedom.cle_depuis_apikey(APIKEY))


def test_l_ancienne_enveloppe_reste_lisible():
    """Le démon peut tourner un instant avec les fichiers de la version d'avant."""
    chiffre = _chiffrer("pronotevs")  # enveloppe CBC, sans champ « tag »
    assert (
        secret_jeedom.dechiffrer(chiffre, secret_jeedom.cle_depuis_apikey(APIKEY))
        == "pronotevs"
    )


def test_le_php_chiffre_bien_en_gcm():
    """Les deux côtés doivent parler la même enveloppe."""
    ici = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(
        os.path.dirname(ici), "core", "class", "ProJote.class.php"
    )
    with open(chemin, encoding="utf-8") as f:
        source = f.read()
    assert "aes-256-gcm" in source
    # L'IV de GCM fait 12 octets : la taille pour laquelle le mode est défini.
    assert "openssl_random_pseudo_bytes(12)" in source
