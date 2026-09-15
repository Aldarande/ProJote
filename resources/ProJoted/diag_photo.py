# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""
diag_photo.py — Diagnostic de la récupération de la photo de profil PRONOTE.

Outil hors démon, à lancer à la main sur le Jeedom pour savoir si un
établissement joint bien la photo de l'élève, et si le plugin sait la lire.

# Ce qu'il faut savoir avant de lire la sortie

La photo de l'utilisateur ne transite pas par ``FichiersExternes``. Les deux
clients officiels de PRONOTE 2026, espace classique comme espace mobile, la
lisent dans la réponse ``ParametresUtilisateur`` elle-même :

    dataNonSec.fichiers = ["<base64 du JPEG>", …]
    dataSec.data.ressource.photoBase64 = {"_T": 25, "V": 0}

Le champ « photoBase64 » ne porte donc pas la charge mais un **renvoi** vers le
tableau ``dataNonSec.fichiers`` de cette même réponse : ``_T: 25`` annonce le
renvoi, ``V`` en donne l'indice. Un compte parent reçoit une entrée par enfant.

``FichiersExternes`` et sa fonction ``composeUrlImgPhotoIndividu`` ne servent
qu'à la photo des **autres** individus — professeurs, camarades. C'est pourquoi
les versions précédentes de cet outil accumulaient des 404 : elles frappaient
une porte qui n'a jamais été celle de sa propre photo, et le témoin qu'elles
opposaient — le téléchargement d'une pièce jointe — validait un chemin que la
photo n'emprunte pas. D'où le verdict « le serveur ne sert pas la photo sur les
sessions mobiles », qui était faux.

# Ce que le script établit

  1. Ce que PRONOTE déclare  — avecPhoto, forme du champ photoBase64, nombre de
                               fichiers joints à la réponse.
  2. Ce que le plugin en tire — en appelant ``ProJoted.photo_jointe()``, la
                               fonction que le démon exécute réellement, et non
                               une réplique qui pourrait diverger d'elle.
  3. Le repli FichiersExternes — à titre indicatif seulement : le démon ne s'en
                               sert que si la charge jointe manque.

Sur un compte parent, chaque enfant est examiné.

ATTENTION — le jeton tourne à chaque connexion. Le script se reconnecte avec le
jeton stocké, donc il le consomme. Il réécrit par défaut le jeton rafraîchi dans
le fichier de l'équipement (comme le fait le démon). Arrêter le démon avant de
le lancer, sinon les deux se disputent le jeton et la prochaine reconnexion
échouera. --no-write désactive la réécriture (le jeton stocké devient alors
périmé : il faudra régénérer le QR code).

Usage :
    cd /var/www/html/plugins/ProJote/resources/ProJoted
    ../python_venv/bin/python3 diag_photo.py --eqid 2697
"""

import argparse
import datetime
import json
import logging
import os
import sys

import pronotepy

import pronote_compat

pronote_compat.apply()

# La fonction du démon, importée et non recopiée : un diagnostic qui réplique
# le code qu'il teste finit tôt ou tard par diverger de lui, et c'est
# exactement ce qui a rendu la version précédente trompeuse.
from ProJoted import photo_jointe  # noqa: E402

DATA_DIR = "/var/www/html/plugins/ProJote/data"
NOM_FICHIER = "enfant.ProJote.json.txt"

# Marqueur PRONOTE d'un renvoi vers dataNonSec.fichiers (cf. ProJoted).
RENVOI_FICHIER_JOINT = 25


def charger_token(data_dir, eqid):
    chemin = os.path.join(data_dir, str(eqid), NOM_FICHIER)
    if not os.path.exists(chemin):
        sys.exit(f"Fichier introuvable : {chemin}")
    with open(chemin, "r") as f:
        data = json.load(f)
    token = data.get("Token")
    if not token:
        sys.exit(f"Aucun jeton dans {chemin}")
    return chemin, data, token


def est_parent_url(token):
    return "parent.html" in token["pronote_url"]


def connecter(token, enfant):
    est_parent = est_parent_url(token)
    classe = pronotepy.ParentClient if est_parent else pronotepy.Client
    client = classe.token_login(
        pronote_url=token["pronote_url"],
        username=token["username"],
        password=token["password"],
        client_identifier=token["client_identifier"],
        # « or » et non « get(…, défaut) » : un jeton peut porter une clé uuid
        # vide, que pronotepy refuse (« UUID must not be empty »).
        uuid=token.get("uuid") or "ProJote",
    )
    if est_parent and enfant:
        client.set_child(enfant)
    return client, est_parent


def decrire_champ(champ):
    """Rend lisible la forme du champ photoBase64 tel que PRONOTE l'envoie."""
    if champ is None:
        return "absent"
    if isinstance(champ, str):
        return f"charge en clair dans le champ ({len(champ)} caractères)"
    if isinstance(champ, dict) and champ.get("_T") == RENVOI_FICHIER_JOINT:
        return f"renvoi vers dataNonSec.fichiers[{champ.get('V')}]"
    return f"forme inattendue : {champ!r}"


def examiner(client, libelle, raw, dossier_sortie):
    """Examine un sujet — l'élève, ou un enfant d'un compte parent."""
    print(f"\n--- {libelle}")
    champ = (raw or {}).get("photoBase64")
    print("    avecPhoto    :", raw.get("avecPhoto"))
    print("    photoBase64  :", decrire_champ(champ))

    image = photo_jointe(client, raw)
    if image:
        nom = "".join(c if c.isalnum() else "_" for c in libelle)
        chemin = os.path.join(dossier_sortie, f"diag_photo_{nom}.jpg")
        try:
            with open(chemin, "wb") as f:
                f.write(image)
            ecrit = chemin
        except OSError as e:
            ecrit = f"(écriture impossible : {e})"
        print(
            f"    >>> CHARGE LUE : {len(image)} octets, "
            f"format {image[:4].hex()} — écrite dans {ecrit}"
        )
        return True

    if raw.get("avecPhoto") and champ is not None:
        print("    >>> la charge est annoncée mais illisible (voir les logs ci-dessus)")
    elif not raw.get("avecPhoto"):
        print("    >>> ce compte n'a pas de photo dans PRONOTE (avecPhoto=False)")
    else:
        print("    >>> aucune charge jointe à la réponse")

    # Repli indicatif : c'est ce que tenterait le démon à défaut de charge.
    photo = None
    try:
        photo = (
            client._selected_child.profile_picture
            if getattr(client, "_selected_child", None)
            else client.info.profile_picture
        )
    except Exception as e:
        print("    repli FichiersExternes indisponible :", e)
    if photo:
        try:
            r = client.communication.session.get(photo.url, timeout=20)
            print(
                f"    repli FichiersExternes : HTTP {r.status_code}, "
                f"{len(r.content)} octets"
            )
        except Exception as e:
            print("    repli FichiersExternes : échec —", e)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eqid", required=True, help="ID de l'équipement Jeedom")
    parser.add_argument("--datadir", default=DATA_DIR)
    parser.add_argument(
        "--enfant", default=None, help="Nom de l'enfant (compte parent)"
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Ne pas réécrire le jeton rafraîchi (le jeton stocké devient périmé)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="    [%(levelname)s] %(message)s")

    chemin, data, token = charger_token(args.datadir, args.eqid)
    enfant = args.enfant or data.get("Eleve")
    print(f"Fichier   : {chemin}")
    print(f"URL       : {token['pronote_url']}")
    print(f"Élève     : {enfant}")

    client, est_parent = connecter(token, enfant if est_parent_url(token) else None)
    print(
        f"Connecté  : {client.logged_in}  "
        f"(compte {'parent' if est_parent else 'élève'})"
    )

    if not args.no_write:
        data["Token"] = client.export_credentials()
        data["Date"] = str(datetime.datetime.now())
        with open(chemin, "w") as f:
            json.dump(data, f, indent=4)
        print("Jeton rafraîchi réécrit dans le fichier.")
    else:
        print("!! Jeton NON réécrit : le jeton stocké est maintenant périmé.")

    parametres = getattr(client, "parametres_utilisateur", None) or {}
    fichiers = parametres.get("dataNonSec", {}).get("fichiers") or []

    print("\n=== 1. Ce que PRONOTE joint à ParametresUtilisateur ===")
    print(f"    fichiers joints : {len(fichiers)}")
    for i, charge in enumerate(fichiers):
        taille = len(charge) if isinstance(charge, str) else "?"
        print(f"      [{i}] {taille} caractères de base64")
    if not fichiers:
        print("      (aucun — voir le verdict)")

    print("\n=== 2. Ce que le plugin en tire (ProJoted.photo_jointe) ===")
    dossier = os.path.join(args.datadir, str(args.eqid))
    resultats = {}
    if est_parent:
        enfants = list(getattr(client, "children", []) or [])
        if not enfants:
            print("    Aucun enfant listé sur ce compte parent.")
        for ch in enfants:
            client.set_child(ch)
            resultats[ch.name] = examiner(
                client, ch.name, client._selected_child.raw_resource, dossier
            )
        # Rendre la sélection à l'enfant de l'équipement, par politesse pour
        # le prochain cycle du démon s'il partage le même jeton.
        if enfant:
            try:
                client.set_child(enfant)
            except Exception:
                pass
    else:
        resultats[client.info.name] = examiner(
            client, client.info.name, client.info.raw_resource, dossier
        )

    print("\n=== VERDICT ===")
    lues = [nom for nom, ok in resultats.items() if ok]
    manquantes = [nom for nom, ok in resultats.items() if not ok]
    if lues and not manquantes:
        print("    Photo disponible et lisible pour :", ", ".join(lues))
        print("    Rien à corriger : le démon écrira ces images telles quelles.")
    elif lues:
        print("    Photo lue pour   :", ", ".join(lues))
        print("    Photo manquante  :", ", ".join(manquantes))
        print("    Comparer les deux cas ci-dessus : si avecPhoto vaut False, le")
        print("    compte n'a simplement pas de photo dans PRONOTE.")
    else:
        print("    Aucune photo lue.")
        print("    Si avecPhoto vaut True et qu'aucun fichier n'est joint, cet")
        print("    établissement ne diffuse pas la photo à l'application mobile ;")
        print("    l'espace web de l'établissement permet de le confirmer.")
        print("    Si avecPhoto vaut False, le compte n'a pas de photo : c'est")
        print("    normal, et le widget affichera les initiales.")


if __name__ == "__main__":
    main()
