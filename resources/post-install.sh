#!/bin/bash
# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

# Script post-install pour ProJote : configuration du venv Python indépendant.
# Le venv est TOUJOURS créé dans le même dossier que ce script : resources/python_venv/
# Idempotent : peut être relancé sans risque, ne réinstalle pas ce qui est déjà à jour.

set -u  # variables non définies → erreur (mais pas -e, on gère les pip individuellement)

# ── Résolution des chemins ──────────────────────────────────────────────────
RESOURCES_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$RESOURCES_DIR/python_venv"

echo "[ProJote] Répertoire resources : $RESOURCES_DIR"
echo "[ProJote] Venv cible           : $VENV_DIR/bin/python3"

# ── Vérification python3 ───────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ProJote][ERROR] python3 introuvable. Installez-le : apt install python3" 1>&2
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "[ProJote] Python système : $PYTHON_VERSION"

# ── Check version Python ≥ 3.8 ─────────────────────────────────────────────
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
    echo "[ProJote][ERROR] Python 3.8 ou supérieur requis (détecté : $PYTHON_VERSION)." 1>&2
    echo "[ProJote][ERROR] Mettez à jour Python avant de relancer l'installation." 1>&2
    exit 1
fi

# ── Création / réutilisation du venv ───────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[ProJote] Création du venv Python..."
    if ! python3 -m venv "$VENV_DIR"; then
        echo "[ProJote][ERROR] Impossible de créer le venv." 1>&2
        echo "[ProJote][ERROR] Assurez-vous que python3-venv est installé : apt install python3-venv" 1>&2
        exit 1
    fi
else
    echo "[ProJote] Le venv existe déjà, vérification des paquets."
fi

# Sanity check : le binaire python du venv existe-t-il vraiment ?
if [ ! -x "$VENV_DIR/bin/python3" ]; then
    echo "[ProJote][ERROR] Le venv semble corrompu ($VENV_DIR/bin/python3 absent)." 1>&2
    echo "[ProJote][ERROR] Supprimez le dossier python_venv puis relancez l'installation." 1>&2
    exit 1
fi

# ── Activation et mise à jour pip ──────────────────────────────────────────
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[ProJote] Mise à jour de pip..."
pip_err=$(pip install --upgrade pip --quiet 2>&1)
if [ $? -ne 0 ]; then
    echo "[ProJote][WARNING] Échec mise à jour pip : $pip_err" 1>&2
    # Non bloquant : on continue avec le pip existant
fi

# ── Installation idempotente des paquets ───────────────────────────────────
# Source de vérité unique : resources/requirements.txt (versions épinglées).
# pip est idempotent : si les versions exactes sont déjà installées, rien n'est
# retéléchargé.
REQUIREMENTS="$RESOURCES_DIR/requirements.txt"
if [ ! -f "$REQUIREMENTS" ]; then
    echo "[ProJote][ERROR] Fichier requirements.txt introuvable : $REQUIREMENTS" 1>&2
    exit 1
fi

echo "[ProJote] Installation des dépendances depuis requirements.txt..."
pip_err=$(pip install -r "$REQUIREMENTS" --quiet 2>&1)
if [ $? -ne 0 ]; then
    echo "[ProJote][ERROR] Échec installation des dépendances : $pip_err" 1>&2
    echo "[ProJote][ERROR] Consultez le log d'installation Jeedom pour le détail." 1>&2
    exit 1
fi

echo "[ProJote] Installation terminée avec succès."
echo "[ProJote] Binaire Python : $VENV_DIR/bin/python3"
exit 0
