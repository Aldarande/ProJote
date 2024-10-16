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

try {
  require_once dirname(__FILE__) . '/../../../../core/php/core.inc.php';
  include_file('core', 'authentification', 'php');

  if (!isConnect('admin')) {
    throw new Exception(__('401 - Accès non autorisé', __FILE__));
  }

  // Initialisation de la requête AJAX
  ajax::init();
  $action = init('action');
  log::add('ProJote', 'debug', 'Je reçois la demande AJAX : ' . $action);
  // Gestion des actions possibles
  //Récupèration des infos du comptes pour validation
  //
  $eqId = init('id');
  $eqLogic = ProJote::byId($eqId);
  if ($action == "Validate") {
    $password = init('password');
    $login = init('login');
    $url = init('url');
    $ent = init('ent');
    // Le but est d'éxécuter le script pour récupérer les tokens
    log::add('ProJote', 'debug', 'Ajax::Validation de info LOGIN.' . $ent . '' . $login . ' ' . $url);
    $command = 'python3 ../../resources/ProJoted/LoginConnect.py';
    $command .= ' ' . escapeshellarg($url);
    $command .= ' ' . escapeshellarg($login);
    $command .= ' ' . escapeshellarg($password);
    $command .= ' ' . escapeshellarg($ent);
    log::add('ProJote', 'debug', 'Ajax::commande.' . $command);
    exec($command, $output, $return);
    log::add('ProJote', 'debug', 'Ajax::retour LOGIN ' . $return);
    if ($return === 0 && $output !== null) {
      log::add('ProJote', 'debug', 'Ajax::Résultat LoginToken :' . $output);
      ajax::success($output);
      // transférer les donnée reçu dans logs
    }
  } elseif ($action == "ValidateQRCode") {
    log::add('ProJote', 'debug', 'Ajax::Validation de info QRCODE.');
    $dataJson = init('data');
    $pin = init('pin');
    $data = json_decode($dataJson, true);
    if ($data === null) {
      ajax::error('Invalid JSON data.');
      return;
    }

    $jeton = $data['jeton'];
    $login = $data['login'];
    $url = $data['url'];

    log::add('ProJote', 'debug', 'Ajax::info QRCODE ' . $jeton . ' ' . $login . ' ' . $url . ' ' . $pin);

    $command = 'python3 ../../resources/ProJoted/QRConnect.py';
    $command .= ' ' . escapeshellarg($jeton);
    $command .= ' ' . escapeshellarg($login);
    $command .= ' ' . escapeshellarg($url);
    $command .= ' ' . escapeshellarg($pin);

    log::add('ProJote', 'debug', 'Ajax::info QRCODE cmd ' . $command);
    exec($command, $output, $return);
    //$output = implode("\n", $output); // Convertir l'output en chaîne

    //$output = json_decode($output, true);
    log::add('ProJote', 'debug', 'Ajax::retour QRCODE ' . $return);
    if ($return === 0 && $output !== null) {
      log::add('ProJote', 'debug', 'Ajax::Résultat Token :' . $output);
      ajax::success($output);
      // transférer les donnée reçu dans logs

    } else {
      ajax::error('Erreur lors de l\'exécution du script Python. code résultat : ', $output);
    }
    //
    // Affichage des infos du compte
    //
  } elseif ($action == "GetEquipmentInfo") {
    log::add('ProJote', 'debug', 'Ajax::Je recherche le fichier avec la liste d\'enfant');
    //$eqId = init('id');
    //$eqLogic = ProJote::byId(init('id'));

    $filePath = "/tmp/jeedom/ProJote/{$eqId}/listenfant.ProJote";
    log::add('ProJote', 'debug', 'Ajax::Je recherche le fichier ' . $filePath);
    if (file_exists($filePath) && filesize($filePath) > 0) {
      $fileContent = file_get_contents($filePath);
      // Convertir le contenu en un tableau en utilisant explode
      $fileContentArray = explode("\n", $fileContent);
      // Stocker le contenu dans une variable de session
      // $_SESSION['equipment_info'] = $fileContentArray;
      ajax::success($fileContentArray);
    } else {
      ajax::error('Le fichier n\'existe pas ou est vide.');
    }
  } elseif ($action == "validate2") {
    //  FAire un script python pourr valider la connection

  } else {
    // Si aucune action correspondante n'a été trouvée
    throw new Exception(__('Aucune méthode correspondante à', __FILE__) . ' : ' . init('action'));
  }
} catch (Exception $e) {
  ajax::error(displayException($e), $e->getCode());
}
