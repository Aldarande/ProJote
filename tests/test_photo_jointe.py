"""Tests de l'extraction de la photo de profil jointe à ParametresUtilisateur.

La photo de l'utilisateur n'a jamais transité par FichiersExternes : les deux
clients officiels de PRONOTE 2026, espace classique comme espace mobile, la
lisent dans la réponse ParametresUtilisateur elle-même. Le champ
« photoBase64 » de la ressource ne porte pas la charge mais un renvoi
``{"_T": 25, "V": <indice>}`` vers le tableau ``dataNonSec.fichiers``.

pronotepy ne remonte que la moitié « dataSec » de l'enveloppe : le renvoi
arrivait donc tel quel jusqu'au démon, qui le prenait pour une chaîne vide.
D'où le diagnostic « le serveur ne sert pas la photo sur les sessions
mobiles », resté en place plusieurs mois alors que la charge était là.

Relevé sur le site de démonstration (PRONOTE 2026.2.6) le 13 septembre 2026 :
un compte élève reçoit un tableau à une entrée, un compte parent une entrée par
enfant — Fanny à l'indice 0, Manon à l'indice 1.
"""

import base64
import types

import pytest

# En-têtes réels : le démon refuse ce qu'un navigateur ne saurait afficher.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def _b64(charge, largeur=None):
    """Encode en base64, éventuellement découpé en lignes comme le fait PRONOTE."""
    texte = base64.b64encode(charge).decode()
    if largeur:
        texte = "\n".join(texte[i : i + largeur] for i in range(0, len(texte), largeur))
    return texte


def _client(*charges):
    """Client factice portant les fichiers joints à ParametresUtilisateur."""
    return types.SimpleNamespace(
        parametres_utilisateur={"dataNonSec": {"fichiers": list(charges)}}
    )


def _renvoi(indice):
    return {"_T": 25, "V": indice}


def test_renvoi_vers_le_fichier_joint(daemon):
    """Le cas nominal : le renvoi désigne l'unique fichier de la réponse."""
    client = _client(_b64(JPEG))
    assert daemon.photo_jointe(client, {"photoBase64": _renvoi(0)}) == JPEG


def test_chaque_enfant_pointe_sa_propre_entree(daemon):
    """Compte parent : un tableau partagé, un indice par enfant."""
    fanny = JPEG
    manon = b"\xff\xd8\xff\xe1" + b"\x01" * 300
    client = _client(_b64(fanny), _b64(manon))

    assert daemon.photo_jointe(client, {"photoBase64": _renvoi(0)}) == fanny
    assert daemon.photo_jointe(client, {"photoBase64": _renvoi(1)}) == manon


def test_charge_decoupee_en_lignes(daemon):
    """PRONOTE découpe le base64 : les retours à la ligne n'en font pas partie."""
    client = _client(_b64(JPEG, largeur=76))
    assert daemon.photo_jointe(client, {"photoBase64": _renvoi(0)}) == JPEG


def test_charge_directement_dans_le_champ(daemon):
    """Un serveur qui inscrirait la charge dans le champ reste pris en charge."""
    client = _client()
    assert daemon.photo_jointe(client, {"photoBase64": _b64(PNG)}) == PNG


@pytest.mark.parametrize("indice", [1, -1, 42, None, "0"])
def test_renvoi_hors_bornes(daemon, indice):
    """Un indice qui ne désigne aucun fichier ne doit pas lever."""
    client = _client(_b64(JPEG))
    assert daemon.photo_jointe(client, {"photoBase64": _renvoi(indice)}) is None


def test_sans_champ_photo(daemon):
    """Une ressource sans photo — et une ressource absente — donnent None."""
    client = _client(_b64(JPEG))
    assert daemon.photo_jointe(client, {"avecPhoto": False}) is None
    assert daemon.photo_jointe(client, None) is None


def test_client_sans_parametres_utilisateur(daemon):
    """Le renvoi est inexploitable si la réponse n'a pas été conservée."""
    assert (
        daemon.photo_jointe(types.SimpleNamespace(), {"photoBase64": _renvoi(0)})
        is None
    )


def test_format_inattendu_refuse(daemon):
    """Ni JPEG ni PNG : on refuse plutôt que d'écrire un fichier illisible."""
    client = _client(_b64(b"%PDF-1.4" + b"\x00" * 200))
    assert daemon.photo_jointe(client, {"photoBase64": _renvoi(0)}) is None


def test_charge_trop_courte_ignoree(daemon):
    """Une charge minuscule n'est pas une photo : ne pas tenter de la décoder."""
    client = _client(_b64(b"\xff\xd8\xff\xe0"))
    assert daemon.photo_jointe(client, {"photoBase64": _renvoi(0)}) is None


def test_base64_invalide(daemon):
    """Une charge indécodable est signalée par None, sans exception."""
    client = _client("!" * 400)
    assert daemon.photo_jointe(client, {"photoBase64": _renvoi(0)}) is None
