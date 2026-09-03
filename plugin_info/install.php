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

// Fonction exécutée automatiquement après l'installation du plugin
function ProJote_install() {
  _ProJote_setVersion();
}

// Fonction exécutée automatiquement après la mise à jour du plugin
function ProJote_update() {
  _ProJote_setVersion();
  _ProJote_createMissingCmds();
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
