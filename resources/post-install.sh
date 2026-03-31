#!/bin/bash

# Script post-install pour ProJote : configuration du venv Python indépendant.
# Le venv est TOUJOURS créé dans le même dossier que ce script : resources/python_venv/
# Ce script est exécuté par Jeedom à l'installation ET via le bouton "Installer les dépendances".

# Résolution absolue du répertoire resources/ (là où se trouve ce script)
RESOURCES_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$RESOURCES_DIR/python_venv"

echo "[ProJote] Répertoire resources : $RESOURCES_DIR"
echo "[ProJote] Venv cible           : $VENV_DIR/bin/python3"

# Vérifie que python3 est disponible
if ! command -v python3 &>/dev/null; then
    echo "[ProJote] ERREUR : python3 introuvable. Installez python3 (apt install python3)."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "[ProJote] Python système : $PYTHON_VERSION"

# Création du venv s'il n'existe pas
if [ ! -d "$VENV_DIR" ]; then
    echo "[ProJote] Création du venv Python..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "[ProJote] ERREUR : Impossible de créer le venv."
        echo "[ProJote] Assurez-vous que python3-venv est installé : apt install python3-venv"
        exit 1
    fi
else
    echo "[ProJote] Le venv existe déjà, passage à la mise à jour des paquets."
fi

echo "[ProJote] Venv créé : $VENV_DIR/bin/python3"

# Activation et installation des dépendances
source "$VENV_DIR/bin/activate"

echo "[ProJote] Mise à jour de pip..."
pip install --upgrade pip --quiet

echo "[ProJote] Installation des paquets Python..."
pip install pronotepy autoslot cryptography pycryptodome==3.20.0 requests beautifulsoup4 pyserial pyudev

if [ $? -ne 0 ]; then
    echo "[ProJote] ERREUR : Installation des paquets échouée."
    exit 1
fi

echo "[ProJote] Installation terminée avec succès."
echo "[ProJote] Binaire Python : $VENV_DIR/bin/python3"
