# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""
diag_photo.py — Diagnostic de la récupération de la photo de profil PRONOTE.

Outil hors démon, à lancer à la main sur le Jeedom pour savoir POURQUOI la
photo d'un équipement ne remonte pas, et si le canal historique fonctionne
encore sur l'établissement concerné.

Ce que le script établit, sur le serveur réel de l'utilisateur :

  1. Ce que PRONOTE déclare      — avecPhoto, photoBase64, identifiant ressource.
  2. L'URL du client officiel    — réplique exacte de composeUrlImgPhotoIndividu
                                   du JS PRONOTE 2026 (payload {"N":…,"Actif":true},
                                   nom de fichier « Prénom_Nom.jpg »), plus les
                                   variantes (nom photo.jpg, &miniature=).
  3. Un témoin de contrôle       — téléchargement d'une pièce jointe quelconque
                                   par la MÊME mécanique FichiersExternes.

Le témoin est le cœur du diagnostic :

  - témoin OK + photo 404  → la mécanique de chiffrement et la session sont
    saines ; c'est l'endpoint photo qui ne sert plus rien. Rien à corriger côté
    plugin : PRONOTE lui-même affiche sa silhouette de repli dans ce cas.
  - témoin KO              → le problème est en amont (session, chiffrement,
    droits) et concerne tous les fichiers, pas seulement la photo.

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
from urllib.parse import quote

import pronotepy
import requests
from Crypto.Util import Padding

import pronote_compat

pronote_compat.apply()

DATA_DIR = "/var/www/html/plugins/ProJote/data"
NOM_FICHIER = "enfant.ProJote.json.txt"


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


def connecter(token, enfant):
    est_parent = "parent.html" in token["pronote_url"]
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


def url_photo(client, numero, libelle, nom_fichier=None, extra=""):
    """Réplique de composeUrlImgPhotoIndividu (client web PRONOTE 2026)."""
    padd = Padding.pad(
        json.dumps({"N": numero, "Actif": True}).replace(" ", "").encode(), 16
    )
    magic = client.communication.encryption.aes_encrypt(padd).hex()
    nom = nom_fichier or (libelle.replace(" ", "_") + ".jpg")
    return (
        f"{client.communication.root_site}/FichiersExternes/{magic}/"
        + quote(nom, safe="~()*!.'")
        + f"?Session={client.attributes['h']}"
        + extra
    )


def essai(client, label, url, headers=None):
    try:
        r = client.communication.session.get(url, timeout=20, headers=headers or {})
    except Exception as e:
        print(f"  [ERR] {label:<44} {e}")
        return False
    ok = r.status_code == 200 and len(r.content) > 100
    print(
        f"  [{'OK ' if ok else '   '}] {label:<44} HTTP {r.status_code} "
        f"{len(r.content):>8} o  {r.headers.get('Content-Type', '?')[:28]}"
    )
    return ok


def temoin_piece_jointe(client):
    """Télécharge n'importe quelle pièce jointe par la même mécanique."""
    debut = client.start_day
    try:
        for hw in client.homework(debut, debut + datetime.timedelta(days=60)):
            for f in hw.files:
                if f.type == 1:
                    return essai(client, f"pièce jointe devoir : {f.name[:26]}", f.url)
    except Exception as e:
        print("  (devoirs indisponibles :", e, ")")
    try:
        for lesson in client.lessons(debut, debut + datetime.timedelta(days=20)):
            try:
                contenu = lesson.content
            except Exception:
                continue
            for f in getattr(contenu, "files", None) or []:
                if f.type == 1:
                    return essai(client, f"contenu de cours : {f.name[:30]}", f.url)
    except Exception as e:
        print("  (contenus de cours indisponibles :", e, ")")
    print("  aucune pièce jointe trouvée : témoin non concluant")
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eqid", required=True, help="ID de l'équipement Jeedom")
    parser.add_argument("--datadir", default=DATA_DIR)
    parser.add_argument("--enfant", default=None, help="Nom de l'enfant (compte parent)")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Ne pas réécrire le jeton rafraîchi (le jeton stocké devient périmé)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    chemin, data, token = charger_token(args.datadir, args.eqid)
    enfant = args.enfant or data.get("Eleve")
    print(f"Fichier   : {chemin}")
    print(f"URL       : {token['pronote_url']}")
    print(f"Élève     : {enfant}")

    client, est_parent = connecter(token, enfant if est_parent_url(token) else None)
    print(f"Connecté  : {client.logged_in}  (compte {'parent' if est_parent else 'élève'})")

    if not args.no_write:
        data["Token"] = client.export_credentials()
        data["Date"] = str(datetime.datetime.now())
        with open(chemin, "w") as f:
            json.dump(data, f, indent=4)
        print("Jeton rafraîchi réécrit dans le fichier.")
    else:
        print("!! Jeton NON réécrit : le jeton stocké est maintenant périmé.")

    info = client._selected_child if est_parent and client._selected_child else client.info
    raw = info.raw_resource

    print("\n=== 1. Ce que PRONOTE déclare ===")
    print("  nom          :", info.name)
    print("  N (ressource):", raw.get("N"))
    print("  avecPhoto    :", raw.get("avecPhoto"))
    print("  photoBase64  :", raw.get("photoBase64"))
    print("  profile_picture pronotepy :", "None" if info.profile_picture is None else "Attachment")

    print("\n=== 2. URL du client officiel et variantes ===")
    n = raw.get("N")
    if not n:
        print("  pas d'identifiant de ressource, arrêt")
        return
    essai(client, "nom officiel « Prénom_Nom.jpg »", url_photo(client, n, info.name))
    essai(client, "nom pronotepy « photo.jpg »", url_photo(client, n, info.name, "photo.jpg"))
    essai(client, "nom officiel + &miniature=1", url_photo(client, n, info.name, None, "&miniature=1"))

    print("\n=== 2 bis. Stratégies de repli du démon ===")
    url = url_photo(client, n, info.name, "photo.jpg")
    root = client.communication.root_site
    essai(
        client,
        "stratégie 2 : Referer + Origin",
        url,
        headers={"Referer": root + "/", "Origin": root},
    )
    try:
        r = requests.get(
            url,
            cookies=client.communication.session.cookies,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0", "Referer": root + "/"},
        )
        print(
            f"  [{'OK ' if r.status_code == 200 and len(r.content) > 100 else '   '}] "
            f"{'stratégie 3 : cookies de session':<44} HTTP {r.status_code} "
            f"{len(r.content):>8} o  {r.headers.get('Content-Type', '?')[:28]}"
        )
    except Exception as e:
        print(f"  [ERR] {'stratégie 3 : cookies de session':<44} {e}")
    essai(
        client,
        "silhouette de repli du client officiel",
        root + "/FichiersRessource/PortraitSilhouette.png",
    )

    print("\n=== 3. Témoin de contrôle (même mécanique, autre fichier) ===")
    temoin = temoin_piece_jointe(client)

    print("\n=== VERDICT ===")
    if temoin:
        print("  Le témoin passe : session et chiffrement sains.")
        print("  ATTENTION — le témoin ne valide PAS la composition de l'URL :")
        print("  une pièce jointe porte une URL fournie par le serveur, alors que")
        print("  la photo est composée par le client. Il n'exerce donc pas le")
        print("  chemin qui échoue.")
        print("  Ce qui a été établi le 13 septembre 2026, sur deux établissements :")
        print("    - la composition est correcte : la charge déchiffrée d'une pièce")
        print("      jointe qui fonctionne a exactement la même forme que la nôtre,")
        print("      {\"N\":…,\"Actif\":true}, au préfixe de ressource près ;")
        print("    - les 8 variantes de charge et de padding renvoient 404 ;")
        print("    - photoBase64 revient vide alors qu'avecPhoto vaut True ;")
        print("    - l'espace classique, lui, affiche bien la photo, mais il refuse")
        print("      le jeton d'application mobile.")
        print("  Conclusion : sur une connexion par QR Code (espace mobile), le")
        print("  serveur ne sert pas la photo d'un individu. Ne pas en conclure")
        print("  que le compte n'a pas de photo.")
    elif temoin is False:
        print("  Le témoin échoue aussi : le problème touche TOUS les fichiers,")
        print("  pas seulement la photo (session, chiffrement ou droits).")
    else:
        print("  Témoin non concluant : relancer quand des pièces jointes existent.")


def est_parent_url(token):
    return "parent.html" in token["pronote_url"]


if __name__ == "__main__":
    main()
