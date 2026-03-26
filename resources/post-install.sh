#!/bin/bash

# Script post-install pour ProJote : configuration du venv indépendant
# Le chemin du plugin est détecté dynamiquement depuis l'emplacement du script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PLUGIN_DIR/resources/python_venv"

echo "Création du venv indépendant pour ProJote..."

# Créer le venv s'il n'existe pas
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# Activer le venv et installer les dépendances
source "$VENV_DIR/bin/activate"

echo "Installation des dépendances Python dans le venv..."
pip install --upgrade pip
pip install pronotepy autoslot cryptography pycryptodome==3.20.0 requests beautifulsoup4 pyserial pyudev

echo "Venv configuré avec succès."