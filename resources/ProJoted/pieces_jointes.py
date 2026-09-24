# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""pieces_jointes.py — Rapatriement choisi des fichiers joints aux actualités.

Certains établissements ne publient pas le menu de la cantine dans l'onglet
prévu pour cela, mais en PDF attaché à une actualité. Le fichier était donc hors
de portée du plugin.

# Pourquoi ne pas tout prendre

* **La place et la bande passante.** Un établissement joint aussi des règlements
  intérieurs, des diaporamas de réunion, des affiches. Relevé sur un compte réel
  le 24 septembre 2026 : l'unique pièce jointe de l'élève était une affiche PNG
  sans rapport avec la cantine.
* **L'URL d'une pièce jointe meurt avec la session.** Elle porte
  ``?Session=<identifiant>`` et un bloc chiffré avec la clé de session : on ne
  peut pas la ranger dans une commande Jeedom pour la suivre plus tard. Le
  fichier se rapatrie pendant le relevé, ou pas du tout.

# Ce que coûte l'énumération : rien

``Information.attachments()`` et ``Information.content()`` passent par le même
``_fetch_content()``, dont le résultat est mémorisé. Le plugin lisant déjà le
contenu de chaque actualité, **lister les pièces jointes ne coûte aucune requête
supplémentaire** — mesuré sur les comptes de démonstration : ``contenu = 1
requête, pièces jointes = 0``.

On énumère donc toujours, et l'on ne télécharge que ce qui correspond aux mots
choisis. L'affichage montre les deux états : ce qui existe, et ce qui a été pris.

# Ne pas réécrire le même fichier

À chaque relevé, on demande au serveur *si le fichier a changé*, par une requête
conditionnelle (``If-None-Match`` / ``If-Modified-Since``) : un ``304`` ne
transporte aucun octet et vaut « rien de neuf, garde ce que tu as ». Les
empreintes nécessaires sont rangées à côté des fichiers, dans ``.index.json``.

Tous les serveurs n'honorent pas les requêtes conditionnelles. Mesuré sur un
serveur PRONOTE réel le 24 septembre 2026 : **il les ignore** et renvoie le
fichier entier. On compare donc l'empreinte du contenu reçu à celle qu'on
avait — identique, le fichier sur disque n'est pas réécrit et sa date de
rapatriement est conservée, ce qui évite aussi qu'un fichier inchangé échappe
indéfiniment à la rétention.

Le contenu transite donc à chaque collecte des actualités, toutes les trois
heures (cf. ``cadence.py``). C'est le prix d'une détection immédiate : un menu
republié est vu au relevé suivant, et non au bout d'un délai. Le choix est
assumé, la cadence des actualités le borne, et le plafond ``TAILLE_MAX`` évite
qu'un fichier démesuré en fasse les frais.

# Le nom du fichier vient de Pronote

Il ne compose donc un chemin qu'une fois assaini — même principe que
l'identifiant d'équipement (SECURITY-AUDIT.md, finding L3). Un nom contenant
``../`` écrirait hors du dossier de l'équipement.
"""

import hashlib
import json
import logging
import os
import re
import time
import unicodedata

# Au-delà, on renonce : un menu de cantine pèse quelques centaines de kilooctets,
# et le dossier de données du plugin n'est pas un espace de stockage.
TAILLE_MAX = 5 * 1024 * 1024

# Sous-dossier, dans data/<équipement>/.
DOSSIER = "file"

# Empreintes des fichiers déjà rapatriés, rangées avec eux.
INDEX = ".index.json"

RETENTION_DEFAUT = 30

_CARACTERES_SURS = re.compile(r"[^A-Za-z0-9._-]+")


def reglages(message):
    """Réglages du rapatriement, lus du message envoyé par Jeedom.

    Returns:
        dict: ``actif`` (bool), ``mots`` (liste) et ``retention`` (jours).
    """
    return {
        "actif": str(message.get("PiecesJointesActif", "0")) in ("1", "true", "True"),
        "mots": mots_cles(message.get("PiecesJointesMots")),
        "retention": _jours(message.get("PiecesJointesRetention")),
    }


def _jours(valeur):
    """Durée de rétention en jours, RETENTION_DEFAUT si la valeur ne dit rien."""
    try:
        jours = int(str(valeur).strip())
    except (TypeError, ValueError):
        return RETENTION_DEFAUT
    return jours if jours > 0 else RETENTION_DEFAUT


def mots_cles(brut):
    """Liste de mots à chercher, depuis le champ de configuration.

    « Menu, Cantine » → ``['menu', 'cantine']``. Un champ vide rend une liste
    vide, ce qui ne retient rien : ne rien télécharger est le défaut.
    """
    if not brut:
        return []
    mots = []
    for morceau in str(brut).replace(";", ",").split(","):
        mot = _sans_accent(morceau.strip().lower())
        if mot:
            mots.append(mot)
    return mots


def _sans_accent(texte):
    """Minuscules sans diacritiques : « Élève » et « eleve » doivent se valoir."""
    decompose = unicodedata.normalize("NFD", str(texte))
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def retenue(nom_fichier, titre_actualite, mots):
    """Ce fichier fait-il partie de ce que l'utilisateur veut rapatrier ?

    Le mot est cherché dans le nom du fichier ET dans le titre de l'actualité
    qui le porte : un établissement qui nomme son PDF « S39.pdf » sous une
    actualité « Menu de la semaine » doit fonctionner, et l'inverse aussi.
    """
    if not mots:
        return False
    foin = _sans_accent("%s %s" % (nom_fichier or "", titre_actualite or "")).lower()
    return any(mot in foin for mot in mots)


def nom_sur_disque(nom):
    """Nom de fichier sûr, dérivé de celui que Pronote annonce.

    On ne garde que le dernier segment, et seulement des caractères inoffensifs.
    Un nom qui ne laisse rien d'exploitable rend None : mieux vaut renoncer au
    fichier que d'inventer un chemin.
    """
    if not nom:
        return None
    # basename des deux mondes : Pronote n'est pas tenu d'utiliser « / ».
    dernier = str(nom).replace("\\", "/").split("/")[-1].strip()
    dernier = _sans_accent(dernier)
    propre = _CARACTERES_SURS.sub("_", dernier).strip("._-")
    if not propre or propre in (".", ".."):
        return None
    return propre[:120]


# ── L'index des empreintes ──────────────────────────────────────────────────


def _chemin_index(cible):
    return os.path.join(cible, INDEX)


def _lire_index(cible):
    try:
        with open(_chemin_index(cible), "r", encoding="utf-8") as f:
            index = json.load(f)
            return index if isinstance(index, dict) else {}
    except Exception:
        return {}


def _ecrire_index(cible, index):
    try:
        with open(_chemin_index(cible), "w", encoding="utf-8") as f:
            json.dump(index, f)
    except Exception as e:
        logging.warning("Index des pièces jointes non écrit : %s", e)


# ── Le rapatriement ─────────────────────────────────────────────────────────


def _session_de(piece):
    """Session HTTP authentifiée de pronotepy, ou None si la structure a changé."""
    communication = getattr(getattr(piece, "_client", None), "communication", None)
    return getattr(communication, "session", None)


def _telecharger(piece, destination, connu):
    """Rapatrie la pièce si elle a changé.

    Args:
        piece: objet ``Attachment`` de pronotepy.
        destination: chemin du fichier sur disque.
        connu: empreintes du dernier rapatriement (dict, vide si inconnu).

    Returns:
        tuple: (repris, empreintes, motif). ``repris`` est False quand le serveur
        a répondu « rien de neuf » ou que le contenu s'avère identique ; le motif
        dit lequel des deux, ce qui n'est pas la même dépense — un 304 ne
        transporte rien, un 200 transporte le fichier entier.
    """
    session = _session_de(piece)
    if session is None:
        # Repli sur pronotepy si sa structure interne a changé : sans plafond ni
        # requête conditionnelle, mais un fichier rapatrié vaut mieux qu'une
        # fonctionnalité muette.
        piece.save(destination)
        return True, {"taille": os.path.getsize(destination)}, "repli pronotepy"

    entetes = {}
    present = os.path.exists(destination)
    if present and connu.get("etag"):
        entetes["If-None-Match"] = connu["etag"]
    if present and connu.get("modifie_le"):
        entetes["If-Modified-Since"] = connu["modifie_le"]

    reponse = session.get(piece.url, headers=entetes, stream=True, timeout=30)
    if reponse.status_code == 304:
        return False, connu, "304, rien transporté"
    if reponse.status_code != 200:
        raise IOError("Pronote a répondu %s" % reponse.status_code)

    empreinte = hashlib.sha256()
    ecrits = 0
    temporaire = destination + ".part"
    try:
        with open(temporaire, "wb") as sortie:
            for bloc in reponse.iter_content(8192):
                ecrits += len(bloc)
                if ecrits > TAILLE_MAX:
                    raise IOError("fichier au-delà de %d octets, abandonné" % TAILLE_MAX)
                empreinte.update(bloc)
                sortie.write(bloc)
        digest = empreinte.hexdigest()

        # Le serveur a renvoyé le fichier malgré la requête conditionnelle : on
        # compare nous-mêmes. Contenu identique, on garde celui qui est en place
        # — et sa date de rapatriement avec lui.
        if present and connu.get("empreinte") == digest:
            os.remove(temporaire)
            return False, connu, "contenu identique, mais le serveur l'a renvoyé"

        os.replace(temporaire, destination)
    finally:
        if os.path.exists(temporaire):
            os.remove(temporaire)

    return True, {
        "empreinte": digest,
        "taille": ecrits,
        "etag": reponse.headers.get("ETag", ""),
        "modifie_le": reponse.headers.get("Last-Modified", ""),
        "repris_le": time.time(),
    }, "contenu neuf"


def decrire(piece, titre_actualite, options, dossier):
    """Décrit une pièce jointe, et la rapatrie si elle est retenue.

    Args:
        piece: objet ``Attachment`` de pronotepy.
        titre_actualite: titre de l'actualité qui la porte.
        options: réglages issus de ``reglages()``.
        dossier: dossier de données de l'équipement, ou None pour ne rien écrire.

    Returns:
        dict: ``nom``, ``lien`` (True si c'est une URL et non un fichier),
        ``recuperee`` (bool) et ``fichier`` (nom sur disque, ou "").
    """
    nom = getattr(piece, "name", "") or ""
    est_lien = getattr(piece, "type", 1) == 0
    decrit = {"nom": nom, "lien": est_lien, "recuperee": False, "fichier": ""}

    if est_lien or not dossier or not options.get("actif"):
        return decrit
    if not retenue(nom, titre_actualite, options.get("mots") or []):
        return decrit

    sur_disque = nom_sur_disque(nom)
    if not sur_disque:
        logging.warning(
            "Pièce jointe « %s » ignorée : son nom ne donne aucun fichier sûr.", nom
        )
        return decrit

    cible = os.path.join(dossier, DOSSIER)
    destination = os.path.join(cible, sur_disque)

    try:
        os.makedirs(cible, exist_ok=True)
        index = _lire_index(cible)
        connu = index.get(sur_disque, {})
        repris, empreintes, motif = _telecharger(piece, destination, connu)
    except Exception as e:
        logging.warning("Pièce jointe « %s » non rapatriée : %s", nom, e)
        # Un échec ne doit pas faire oublier un fichier déjà là.
        if os.path.exists(os.path.join(cible, sur_disque)):
            decrit["recuperee"] = True
            decrit["fichier"] = sur_disque
        return decrit

    if repris:
        logging.info(
            "Pièce jointe rapatriée : %s (%s octets).",
            sur_disque,
            empreintes.get("taille", "?"),
        )
    else:
        logging.debug(
            "Pièce jointe « %s » inchangée, conservée (%s).", sur_disque, motif
        )
    index[sur_disque] = empreintes
    _ecrire_index(cible, index)

    decrit["recuperee"] = True
    decrit["fichier"] = sur_disque
    return decrit


def purger(dossier, retention_jours):
    """Efface les fichiers rapatriés depuis plus de `retention_jours`.

    La date retenue est celle du dernier rapatriement effectif, pas celle du
    dernier passage : un menu inchangé depuis six semaines s'en va, même si le
    plugin l'a revérifié ce matin.

    Returns:
        int: nombre de fichiers effacés.
    """
    if not dossier:
        return 0
    cible = os.path.join(dossier, DOSSIER)
    if not os.path.isdir(cible):
        return 0

    limite = time.time() - max(1, int(retention_jours)) * 86400
    index = _lire_index(cible)
    efface = 0

    for nom in list(os.listdir(cible)):
        if nom == INDEX:
            continue
        chemin = os.path.join(cible, nom)
        if not os.path.isfile(chemin):
            continue
        # `repris_le` fait foi ; à défaut — fichier d'avant l'index — la date du
        # système sert de repli.
        quand = index.get(nom, {}).get("repris_le")
        if quand is None:
            try:
                quand = os.path.getmtime(chemin)
            except OSError:
                continue
        if quand >= limite:
            continue
        try:
            os.remove(chemin)
            index.pop(nom, None)
            efface += 1
            logging.info(
                "Pièce jointe « %s » effacée : au-delà de %s jours de rétention.",
                nom,
                retention_jours,
            )
        except OSError as e:
            logging.warning("Pièce jointe « %s » non effacée : %s", nom, e)

    if efface:
        _ecrire_index(cible, index)
    return efface
