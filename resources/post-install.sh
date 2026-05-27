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
# Format : "nom_pip:contrainte_version" — contrainte vide = dernière version.
PACKAGES=(
    "pronotepy:"
    "autoslot:"
    "cryptography:"
    "pycryptodome:==3.20.0"
    "requests:"
    "beautifulsoup4:"
    "pyserial:"
    "pyudev:"
)

install_failures=0
for entry in "${PACKAGES[@]}"; do
    pkg="${entry%%:*}"
    constraint="${entry#*:}"
    spec="${pkg}${constraint}"

    if [ -n "$constraint" ]; then
        # Avec contrainte de version : pip est lui-même idempotent si la version
        # exacte est déjà installée.
        echo "[ProJote] Installation/vérification : $spec"
        pip_err=$(pip install "$spec" --quiet 2>&1)
        rc=$?
    else
        # Sans contrainte : si déjà présent on saute (évite appel réseau inutile).
        if pip show "$pkg" >/dev/null 2>&1; then
            installed_version=$(pip show "$pkg" 2>/dev/null | awk '/^Version:/ {print $2}')
            echo "[ProJote] Déjà installé : $pkg ($installed_version) — saut."
            continue
        fi
        echo "[ProJote] Installation : $pkg"
        pip_err=$(pip install "$pkg" --quiet 2>&1)
        rc=$?
    fi

    if [ $rc -ne 0 ]; then
        echo "[ProJote][ERROR] Échec installation $pkg : $pip_err" 1>&2
        install_failures=$((install_failures + 1))
    fi
done

if [ $install_failures -gt 0 ]; then
    echo "[ProJote][ERROR] $install_failures paquet(s) n'ont pas pu être installés." 1>&2
    echo "[ProJote][ERROR] Consultez le log d'installation Jeedom pour le détail." 1>&2
    exit 1
fi

echo "[ProJote] Installation terminée avec succès."
echo "[ProJote] Binaire Python : $VENV_DIR/bin/python3"
exit 0
