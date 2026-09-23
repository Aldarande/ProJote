#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refuse de publier des données personnelles.

Ce dépôt est public. En septembre 2026, on y a découvert — présents depuis
janvier 2025 — les jetons, prénoms, classes, établissement et photographies de
quatre enfants, ainsi qu'un identifiant PRONOTE en clair. Supprimer les
fichiers n'avait rien effacé : l'historique les gardait intacts. Il a fallu le
réécrire et republier de force.

Ce contrôle existe pour que cela n'arrive plus. Il tourne avant chaque
publication (crochet ``pre-push``) et dans l'intégration continue.

**Les motifs nominatifs ne sont pas ici, et c'est délibéré.** Écrire le prénom
d'un enfant dans un dépôt public pour empêcher qu'il y soit publié serait
absurde. Ce fichier ne porte que des motifs génériques ; les motifs privés se
déclarent dans ``.motifs-prives``, que ``.gitignore`` écarte.

Usage :
    python outils/verifier_fuites.py --plage <base>..<sommet>
    python outils/verifier_fuites.py --arbre

Une ligne peut être acceptée explicitement en portant le marqueur prévu dans un
commentaire — pour un vecteur de test, par exemple.
"""

import argparse
import os
import re
import subprocess
import sys

# Composé à l'exécution pour que ce fichier ne se signale pas lui-même.
MARQUEUR = "fuite" + "-acceptee"

# Répertoires qui n'ont jamais leur place dans un commit : ils portent soit des
# données d'exécution (jetons, photos), soit un environnement virtuel dont les
# chemins révèlent le nom de session de la machine.
CHEMINS_INTERDITS = (
    "data/",
    ".venv/",
    "resources/python_venv/",
)

EXTENSIONS_BINAIRES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bundle", ".zip")


def _regles():
    """Les motifs génériques, avec ce qu'il faut dire quand ils se déclenchent.

    Chaque règle rend (nom, expression, explication, exception éventuelle).
    L'exception s'applique à l'extrait trouvé, pas à la ligne entière : une URL
    de démonstration ne doit pas blanchir un jeton présent sur la même ligne.
    """
    return (
        (
            "établissement réel",
            re.compile(r"\b[0-9]{7}[a-zA-Z]\.index-education\.net", re.I),
            "une URL PRONOTE d'établissement réel — seul demo.index-education.net "
            "est public",
            # Les codes fictifs employés par les tests depuis la purge.
            re.compile(r"\b0{7}[a-e]\.index-education\.net", re.I),
        ),
        (
            "identifiant d'espace",
            re.compile(r"identifiant=[A-Za-z0-9]{8,}"),
            "un identifiant d'espace PRONOTE dans une URL",
            re.compile(r"identifiant=EXEMPLE", re.I),
        ),
        (
            "jeton",
            re.compile(r"\b[0-9a-fA-F]{32,}\b"),
            "une chaîne hexadécimale assez longue pour être un jeton d'application",
            None,
        ),
        (
            "chemin utilisateur",
            re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+", re.I),
            "un chemin Windows qui nomme la session de la machine",
            re.compile(r"[\\/](utilisateur|user|username)$", re.I),
        ),
        (
            "adresse courriel",
            re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
            "une adresse de courriel",
            re.compile(r"@(example\.(com|org|net)|attaquant\.fr)|^noreply@", re.I),
        ),
    )


def motifs_prives(racine):
    """Les motifs nominatifs, lus hors du dépôt.

    ``.motifs-prives`` contient une expression rationnelle par ligne ; les
    lignes vides et celles commençant par ``#`` sont ignorées. Le fichier est
    écarté par ``.gitignore`` : c'est tout l'intérêt.

    Un motif mal écrit est refusé bruyamment plutôt qu'ignoré en silence. Le
    cas s'est présenté dès la mise en place : un ``\\b`` écrit par un outil
    intermédiaire était arrivé dans le fichier sous la forme du caractère de
    contrôle 0x08. L'expression compilait, ne correspondait à rien, et le
    contrôle déclarait le dépôt propre. Un filtre de confidentialité muet est
    pire que pas de filtre : il rassure.
    """
    chemin = os.path.join(racine, ".motifs-prives")
    if not os.path.exists(chemin):
        return []
    regles = []
    with open(chemin, encoding="utf-8") as fh:
        for numero, ligne in enumerate(fh, 1):
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#"):
                continue
            controle = [c for c in ligne if ord(c) < 32]
            if controle:
                raise ValueError(
                    ".motifs-prives ligne %d : caractère de contrôle 0x%02x. "
                    "Une séquence comme \\b a probablement été interprétée au "
                    "lieu d'être écrite littéralement." % (numero, ord(controle[0]))
                )
            try:
                regles.append(re.compile(ligne, re.I))
            except re.error as e:
                raise ValueError(".motifs-prives ligne %d : %s" % (numero, e))
    return regles


def _masquer(valeur):
    """Ne jamais recopier la trouvaille en clair : on en dit juste assez.

    Un rapport de fuite qui recopie la fuite se retrouve dans un journal
    d'intégration continue, lui-même public.
    """
    if len(valeur) <= 8:
        return valeur[:2] + "…"
    return "%s…%s (%d caractères)" % (valeur[:4], valeur[-2:], len(valeur))


def examiner_ligne(ligne, prives, precedente=""):
    """Rend la liste des (règle, explication, extrait masqué) d'une ligne.

    Le marqueur d'acceptation vaut sur la ligne elle-même ou sur celle qui la
    précède : une ligne déjà longue n'a pas à porter en plus la justification.
    """
    if MARQUEUR in ligne or MARQUEUR in precedente:
        return []
    trouvailles = []
    for nom, motif, explication, exception in _regles():
        for m in motif.finditer(ligne):
            extrait = m.group(0)
            if exception and exception.search(extrait):
                continue
            trouvailles.append((nom, explication, _masquer(extrait)))
    for motif in prives:
        m = motif.search(ligne)
        if m:
            trouvailles.append(
                (
                    "motif privé",
                    "un motif déclaré dans .motifs-prives",
                    _masquer(m.group(0)),
                )
            )
    return trouvailles


def _git(racine, *args):
    resultat = subprocess.run(
        ["git", "-C", racine] + list(args),
        capture_output=True,
        text=True,
        errors="replace",
    )
    return resultat.stdout


def chemins_interdits(chemins):
    return [c for c in chemins if any(c.startswith(p) for p in CHEMINS_INTERDITS)]


def examiner_plage(racine, plage, prives):
    """Les lignes AJOUTÉES par cette plage de commits, et les chemins créés.

    On ne relit pas tout le dépôt : ce qui est déjà publié l'est, et le refus
    doit porter sur ce que cette publication ajoute.
    """
    ennuis = []

    fichiers = [f for f in _git(racine, "diff", "--name-only", plage).splitlines() if f]
    for chemin in chemins_interdits(fichiers):
        ennuis.append(
            (chemin, 0, "chemin interdit", "ce répertoire ne doit jamais être publié", chemin)
        )

    diff = _git(racine, "diff", "--unified=0", plage)
    fichier = None
    precedente = ""
    for ligne in diff.splitlines():
        if ligne.startswith("+++ b/"):
            fichier = ligne[6:]
            precedente = ""
        elif ligne.startswith("+") and not ligne.startswith("+++"):
            if fichier and fichier.lower().endswith(EXTENSIONS_BINAIRES):
                continue
            contenu = ligne[1:]
            for nom, explication, extrait in examiner_ligne(contenu, prives, precedente):
                ennuis.append((fichier or "?", 0, nom, explication, extrait))
            precedente = contenu
    return ennuis


def examiner_arbre(racine, prives):
    """Tout le contenu suivi, pour l'intégration continue."""
    ennuis = []
    fichiers = [f for f in _git(racine, "ls-files").splitlines() if f]

    for chemin in chemins_interdits(fichiers):
        ennuis.append(
            (chemin, 0, "chemin interdit", "ce répertoire ne doit jamais être publié", chemin)
        )

    for chemin in fichiers:
        if chemin.lower().endswith(EXTENSIONS_BINAIRES):
            continue
        try:
            with open(os.path.join(racine, chemin), encoding="utf-8") as fh:
                precedente = ""
                for numero, ligne in enumerate(fh, 1):
                    for nom, explication, extrait in examiner_ligne(ligne, prives, precedente):
                        ennuis.append((chemin, numero, nom, explication, extrait))
                    precedente = ligne
        except (OSError, UnicodeDecodeError):
            continue
    return ennuis


def rapporter(ennuis):
    if not ennuis:
        print("Aucune donnée personnelle détectée.")
        return 0

    print("PUBLICATION REFUSÉE — %d point(s) à vérifier :\n" % len(ennuis))
    for chemin, numero, nom, explication, extrait in ennuis:
        ou = "%s:%d" % (chemin, numero) if numero else chemin
        print("  %s" % ou)
        print("      %s : %s" % (nom, explication))
        print("      trouvé : %s\n" % extrait)
    print("Si une de ces lignes est légitime — un vecteur de test, par exemple —")
    print("ajoutez-y le marqueur « %s » en commentaire." % MARQUEUR)
    return 1


def main(argv=None):
    analyseur = argparse.ArgumentParser(description="Contrôle de fuite de données personnelles.")
    groupe = analyseur.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--plage", help="plage de commits, par exemple origin/works..HEAD")
    groupe.add_argument("--arbre", action="store_true", help="tout le contenu suivi")
    analyseur.add_argument("--racine", default=".", help="racine du dépôt")
    arguments = analyseur.parse_args(argv)

    racine = os.path.abspath(arguments.racine)
    prives = motifs_prives(racine)
    if arguments.arbre:
        ennuis = examiner_arbre(racine, prives)
    else:
        ennuis = examiner_plage(racine, arguments.plage, prives)
    return rapporter(ennuis)


if __name__ == "__main__":
    sys.exit(main())
