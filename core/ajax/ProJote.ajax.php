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
  // Gestion des actions possibles
  //Récupèration des infos du comptes pour validation
  //

  if ($action == "Validate") {
    $password = init('password');
    $login = init('login');
    $url = init('url');
    $ent = init('ent');
    $nomenfant = init('nomeleve');
<<<<<<< Updated upstream
    $eqLogicId = init('eqlogic');
=======
<<<<<<< HEAD
    $eqId = init('eqlogic');
>>>>>>> Stashed changes

    // Le but est d'exécuter le script pour récupérer les tokens
    log::add('ProJote', 'debug', 'Ajax:: Validation de login : ' . $ent . ' ' . $login . ' ' . $url);
    $command = system::getCmdPython3('ProJote') .  '/var/www/html/plugins/ProJote/resources/ProJoted/LoginConnect.py';
    $command .= ' --URL ' . $url;
    $command .= ' --Login ' . $login;
    $command .= ' --Password ' . $password;
    if ($ent != null) {
      $command .= ' --Ent ' . $ent;
    }
    if ($nomenfant != null) {
      $command .= ' --Enfant "' . $nomenfant . '"';
    }
    $command .= ' --Eqid ' . $eqLogicId;
    $command .= ' --Loglevel ' . (log::convertLogLevel(log::getLogLevel("ProJote")));
    $command .= ' >> ' . log::getPathToLog('ProJote') . ' 2>&1 ';
    log::add('ProJote', 'debug', 'Ajax:: Commande de validation : ' . $command);
    exec($command, $output, $return_var);
    log::add('ProJote', 'debug', 'Ajax::retour commande Validation ' . $return_var);
    if ($return_var === 0) {
<<<<<<< Updated upstream
=======
      log::add('ProJote', 'debug', 'Ajax::Résultat LoginToken : ' . $output);
      ajax::success($output);
      //
      // Demander de rafraichir la page pour afficher les informations
      // Si parent renvoyer la liste d'enfant et commencant par le selctionné
      //
=======
    $eqLogicId = init('eqlogic');

    // Le but est d'exécuter le script pour récupérer les tokens
    log::add('ProJote', 'debug', 'Ajax:: Validation de login : ' . $ent . ' ' . $login . ' ' . $url);
    $command = system::getCmdPython3('ProJote') .  '/var/www/html/plugins/ProJote/resources/ProJoted/LoginConnect.py';
    $command .= ' --URL ' . $url;
    $command .= ' --Login ' . $login;
    $command .= ' --Password ' . $password;
    if ($ent != null) {
      $command .= ' --Ent ' . $ent;
    }
    if ($nomenfant != null) {
      $command .= ' --Enfant "' . $nomenfant . '"';
    }
    $command .= ' --Eqid ' . $eqLogicId;
    $command .= ' --Loglevel ' . (log::convertLogLevel(log::getLogLevel("ProJote")));
    $command .= ' >> ' . log::getPathToLog('ProJote') . ' 2>&1 ';
    log::add('ProJote', 'debug', 'Ajax:: Commande de validation : ' . $command);
    exec($command, $output, $return_var);
    log::add('ProJote', 'debug', 'Ajax::retour commande Validation ' . $return_var);
    if ($return_var === 0) {
>>>>>>> Stashed changes
      // Mise à jour des informations collectées depuis le fichier
      $eqLogic = eqLogic::byId($eqLogicId);
      log::add('ProJote', 'debug', 'Ajax:: eqLogicId = ' . $eqLogicId);
      // Appeler la fonction ReadEnfantToken pour lire et décoder le fichier JSON
      $data = $eqLogic->ReadEnfantToken();
      ajax::success($data); // Renvoie les données JSON en cas de succès
<<<<<<< Updated upstream
=======
>>>>>>> dev
>>>>>>> Stashed changes
    } else {
      ajax::error('Erreur lors de l\'exécution de la commande Python : ' . implode("\n", $output));
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
<<<<<<< Updated upstream
=======
<<<<<<< HEAD

>>>>>>> Stashed changes
    $jeton = $data['jeton'];
    $login = $data['login'];
    $url = $data['url'];
    $eqLogicId = init('eqlogic');
    log::add('ProJote', 'debug', 'Ajax::info QRCODE ' . $jeton . ' ' . $login . ' ' . $url . ' ' . $pin . ' pour eqid : ' . $eqLogicId);

    $command = system::getCmdPython3('ProJote') .  '/var/www/html/plugins/ProJote/resources/ProJoted/QRConnect.py';
    $command .= ' --Jeton ' . escapeshellarg($jeton);
    $command .= ' --QRLogin ' . escapeshellarg($login);
    $command .= ' --QRUrl ' . escapeshellarg($url);
    $command .= ' --Pin ' . escapeshellarg($pin);
    $command .= ' --Eqid ' . $eqLogicId;
    $command .= ' --Loglevel ' . (log::convertLogLevel(log::getLogLevel("ProJote")));
    $command .= ' >> ' . log::getPathToLog('ProJote') . ' 2>&1 ';

    log::add('ProJote', 'debug', 'Ajax::info QRCODE cmd ' . $command);
    exec($command, $output, $return_var);


    if ($return_var === 0) {
      // Mise à jour des informations collectées depuis le fichier
      $eqLogic = eqLogic::byId($eqLogicId);
      log::add('ProJote', 'debug', 'Ajax:: eqLogicId = ' . $eqLogicId);
      // Appeler la fonction ReadEnfantToken pour lire et décoder le fichier JSON
      $data = $eqLogic->ReadEnfantToken();
      ajax::success($output);
    } else {
<<<<<<< Updated upstream
      ajax::error('Erreur lors de l\'exécution du script Python. Vérifiez les logs.');
=======
      ajax::error('Erreur lors de l\'exécution du script Python. code résultat : ', $output);
=======
    $jeton = $data['jeton'];
    $login = $data['login'];
    $url = $data['url'];
    $eqLogicId = init('eqlogic');
    log::add('ProJote', 'debug', 'Ajax::info QRCODE ' . $jeton . ' ' . $login . ' ' . $url . ' ' . $pin . ' pour eqid : ' . $eqLogicId);

    $command = system::getCmdPython3('ProJote') .  '/var/www/html/plugins/ProJote/resources/ProJoted/QRConnect.py';
    $command .= ' --Jeton ' . escapeshellarg($jeton);
    $command .= ' --QRLogin ' . escapeshellarg($login);
    $command .= ' --QRUrl ' . escapeshellarg($url);
    $command .= ' --Pin ' . escapeshellarg($pin);
    $command .= ' --Eqid ' . $eqLogicId;
    $command .= ' --Loglevel ' . (log::convertLogLevel(log::getLogLevel("ProJote")));
    $command .= ' >> ' . log::getPathToLog('ProJote') . ' 2>&1 ';

    log::add('ProJote', 'debug', 'Ajax::info QRCODE cmd ' . $command);
    exec($command, $output, $return_var);


    if ($return_var === 0) {
      // Mise à jour des informations collectées depuis le fichier
      $eqLogic = eqLogic::byId($eqLogicId);
      log::add('ProJote', 'debug', 'Ajax:: eqLogicId = ' . $eqLogicId);
      // Appeler la fonction ReadEnfantToken pour lire et décoder le fichier JSON
      $data = $eqLogic->ReadEnfantToken();
      ajax::success($output);
    } else {
      ajax::error('Erreur lors de l\'exécution du script Python. Vérifiez les logs.');
>>>>>>> dev
>>>>>>> Stashed changes
    }
    //
    // Affichage des infos du compte
    //
<<<<<<< Updated upstream
=======
<<<<<<< HEAD
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

=======
>>>>>>> dev
>>>>>>> Stashed changes
  } else {
    // Si aucune action correspondante n'a été trouvée
    throw new Exception(__('Aucune méthode correspondante à', __FILE__) . ' : ' . init('action'));
  }
} catch (Exception $e) {
  ajax::error(displayException($e), $e->getCode());
}
