<?php
/* This file is part of Jeedom.
*
* Jeedom is free software: you can redistribute it and/or modify
* it under the terms of the GNU General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* Jeedom is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with Jeedom. If not, see <http://www.gnu.org/licenses/>.
*/

require_once dirname(__FILE__) . '/../../../core/php/core.inc.php';

function _ProJote_setVersion() {
  $info = json_decode(file_get_contents(dirname(__FILE__) . '/info.json'), true);
  $version = $info['pluginVersion'] ?? null;
  if (!$version) return;
  $update = update::byLogicalId('ProJote', 'plugin');
  if (is_object($update)) {
    $update->setLocalVersion($version);
    $update->save();
  }
}

/**
 * Ferme le dossier de données à tout accès HTTP direct.
 *
 * `data/` contient les jetons de reconnexion Pronote, la photo de l'élève et
 * les pièces jointes rapatriées — rien qui doive être joignable par qui
 * connaît l'URL. Le dossier est exclu du dépôt (voir .gitignore) : sans cette
 * écriture, une installation neuve le laissait entièrement ouvert, et seules
 * les machines où le fichier avait été posé à la main étaient protégées.
 *
 * Photo et pièces jointes sortent par core/php/fichier.php, qui vérifie la
 * session Jeedom. Les jetons, eux, ne sortent jamais.
 *
 * Rejoué à chaque mise à jour, et non à la seule installation : les
 * installations existantes doivent être rattrapées, et un fichier effacé ou
 * modifié à la main doit être rétabli.
 */
function _ProJote_protegerDossierDonnees() {
  $dossier = dirname(__FILE__) . '/../data';
  $regles = "# Généré par ProJote — ne pas modifier à la main.\n"
    . "#\n"
    . "# Aucun accès direct : jetons de reconnexion, photo de l'élève et pièces\n"
    . "# jointes. Photo et pièces jointes sont servies par\n"
    . "# core/php/fichier.php, qui exige une session Jeedom authentifiée.\n"
    . "Require all denied\n";

  try {
    if (!is_dir($dossier) && !@mkdir($dossier, 0775, true)) {
      log::add('ProJote', 'error', 'Dossier de données introuvable et non créable : ' . $dossier);
      return;
    }
    $chemin = $dossier . '/.htaccess';
    if (file_exists($chemin) && file_get_contents($chemin) === $regles) {
      return;
    }
    if (file_put_contents($chemin, $regles) === false) {
      log::add('ProJote', 'error',
        'Impossible d\'écrire ' . $chemin . ' : le dossier de données reste accessible en HTTP.');
      return;
    }
    log::add('ProJote', 'info', 'Dossier de données fermé à tout accès HTTP direct.');
  } catch (Exception $e) {
    log::add('ProJote', 'error', 'Protection du dossier de données échouée : ' . $e->getMessage());
  }
}

// Fonction exécutée automatiquement après l'installation du plugin
function ProJote_install() {
  _ProJote_setVersion();
  _ProJote_protegerDossierDonnees();
}

// Fonction exécutée automatiquement après la mise à jour du plugin
function ProJote_update() {
  _ProJote_setVersion();
  _ProJote_createMissingCmds();
  _ProJote_protegerDossierDonnees();
}

/**
 * Crée les commandes ajoutées par une mise à jour sur les équipements existants.
 *
 * postSave() crée les commandes manquantes à partir du modèle, mais il n'est
 * joué qu'à l'enregistrement d'un équipement. Sans ce passage, les commandes
 * introduites par une nouvelle version (ex. « Période en cours » en 1.4.1)
 * n'apparaîtraient qu'après une sauvegarde manuelle de chaque équipement.
 *
 * On appelle postSave() directement plutôt que save() : postSave() n'agit que
 * sur les commandes, alors que save() réécrirait la ligne de l'équipement. Or
 * le jeton de connexion PRONOTE tourne à chaque authentification et le démon
 * l'enregistre en configuration ; réécrire l'équipement à partir d'un objet
 * chargé quelques instants plus tôt y remettrait un jeton déjà consommé, et la
 * connexion suivante serait refusée.
 *
 * Une erreur sur un équipement ne doit pas interrompre le traitement des
 * autres : chaque appel est isolé.
 */
function _ProJote_createMissingCmds() {
  foreach (eqLogic::byType('ProJote') as $eqLogic) {
    try {
      $eqLogic->postSave();
    } catch (Exception $e) {
      log::add('ProJote', 'error', 'Mise à jour : impossible de créer les commandes manquantes pour '
        . $eqLogic->getHumanName() . ' — ' . $e->getMessage());
    }
  }
}

// Fonction exécutée automatiquement après la suppression du plugin
function ProJote_remove() {}
