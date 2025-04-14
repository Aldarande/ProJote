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

/* * ***************************Includes********************************* */
require_once __DIR__  . '/../../../../core/php/core.inc.php';

class ProJote extends eqLogic
{
  /* Aldarande : 16/02/2024 : Info concernant le Deamon */
  public static function deamon_info()
  {
    $return = array();
    $return['log'] = __CLASS__;
    $return['state'] = 'nok';
    $pid_file = jeedom::getTmpFolder(__CLASS__) . '/deamon.pid';

    if (file_exists($pid_file)) {
      if (@posix_getsid(trim(file_get_contents($pid_file)))) {
        $return['state'] = 'ok';
      } else {
        log::add(__CLASS__, 'erreur', "Le fichier existe je le supprime");
        shell_exec(system::getCmdSudo() . 'rm -rf ' . $pid_file . ' 2>&1 > /dev/null');
      }
    }
    $return['launchable'] = 'ok';
    //exemple de message émis
    return $return;
  }

  /* Aldarande : 16/02/2024 : Lancement du deamon  */

  public static function deamon_start()
  {
    self::deamon_stop();
    $deamon_info = self::deamon_info();
    if ($deamon_info['launchable'] != 'ok') {
      throw new Exception(__('Veuillez vérifier la configuration', __FILE__));
    }

    $path = realpath(dirname(__FILE__) . '/../../resources/ProJoted');
    if (!$path) {
      throw new Exception(__('Chemin vers le démon introuvable.', __FILE__));
    }

    $socketport = config::byKey('socketport', __CLASS__, '55369');
    if (!is_string($socketport)) {
      throw new Exception(__('Le socketport doit être une chaîne valide.', __FILE__));
    }

    $callback = network::getNetworkAccess('internal', 'http:127.0.0.1:port:comp');
    if (!is_string($callback)) {
      throw new Exception(__('Le callback doit être une URL valide.', __FILE__));
    }

    $loglevel = log::convertLogLevel(log::getLogLevel(__CLASS__));
    if (!is_string($loglevel)) {
      throw new Exception(__('Le niveau de log est invalide.', __FILE__));
    }

    $cmd = system::getCmdPython3(__CLASS__) . " {$path}/ProJoted.py";
    $cmd .= ' --loglevel ' . $loglevel;
    $cmd .= ' --socketport ' . $socketport;
    $cmd .= ' --callback ' . $callback . '/plugins/ProJote/core/php/jeeProJote.php';
    $cmd .= ' --apikey ' . jeedom::getApiKey(__CLASS__);
    $cmd .= ' --cycle 3';
    $cmd .= ' --pid ' . jeedom::getTmpFolder(__CLASS__) . '/deamon.pid';

    log::add(__CLASS__, 'info', 'Lancement démon ' . __CLASS__);
    log::add(__CLASS__, 'debug', 'Execution demon : ' . $cmd);
    exec($cmd . ' >> ' . log::getPathToLog(__CLASS__) . ' 2>&1 &');

    $i = 0;
    while ($i < 20) {
      $deamon_info = self::deamon_info();
      if ($deamon_info['state'] == 'ok') {
        break;
      }
      sleep(1);
      $i++;
    }

    if ($i >= 20) {
      log::add(__CLASS__, 'error', __('Impossible de lancer le démon, vérifiez le log', __FILE__), 'unableStartDeamon');
      return false;
    }

    message::removeAll(__CLASS__, 'unableStartDeamon');
    return true;
  }


  /* Aldarande : 16/02/2024 : arrete du deamon  */
  public static function deamon_stop()
  {
    $pid_file = jeedom::getTmpFolder(__CLASS__) . '/deamon.pid'; // ne pas modifier
    if (file_exists($pid_file)) {
      $pid = intval(trim(file_get_contents($pid_file)));
      system::kill($pid);
    }
    system::kill('ProJoted.py'); // nom du démon à modifier
    sleep(1);
  }

  /*     * *************************Attributs****************************** */

  /*
  * Permet de définir les possibilités de personnalisation du widget (en cas d'utilisation de la fonction 'toHtml' par exemple)
  * Tableau multidimensionnel - exemple: array('custom' => true, 'custom::layout' => false)
  public static $_widgetPossibility = array();
  */

  /*
  * Permet de crypter/décrypter automatiquement des champs de configuration du plugin
  * Exemple : "param1" & "param2" seront cryptés mais pas "param3"
  public static $_encryptConfigKey = array('param1', 'param2');
  */

  /*     * ***********************Methode static*************************** */

  /*
  * Fonction exécutée automatiquement toutes les minutes par Jeedom
  public static function cron() {}
  */

  /*
  * Fonction exécutée automatiquement toutes les 5 minutes par Jeedom
  public static function cron5() {}
  */

  /*
  * Fonction exécutée automatiquement toutes les 10 minutes par Jeedom
  public static function cron10() {}
  */

  /*
  * Fonction exécutée automatiquement toutes les 15 minutes par Jeedom
  public static function cron15() {}
  */

  /*
  * Fonction exécutée automatiquement toutes les 30 minutes par Jeedom
  public static function cron30() {}
  */

  /*
  * Fonction exécutée automatiquement toutes les heures par Jeedom*/
  public static function cronHourly()
  {
    //log::add(__CLASS__, 'debug', ' '.__FUNCTION__. ' start..');
    $heure = date('G');
    if ($heure >= 22 || $heure < 4) {
      $msg = " Inutile de chercher à cette heure-ci... $heure heure, tout le monde dors !";
      log::add(__CLASS__, 'debug', ' ' . __FUNCTION__ . $msg);
      return;
    }
    $hour_cron = config::byKey(
      'hour_cron',
      __CLASS__
    );
    if (!empty($hour_cron) && $heure < $hour_cron) {
      log::add(__CLASS__, 'debug', ' ' . __FUNCTION__ . " Je ne fais rien, l'heure de récupération est définie à $hour_cron heure");
      return;
    }
    if ($heure % 2 == 1 && $heure != $hour_cron) {
      $msg = " Je ne fais rien à cette heure-ci... $heure heure, prochain essaie dans une heure";
      log::add(__CLASS__, 'debug', ' ' . __FUNCTION__ . $msg);
      return;
    }


    $eqLogics = self::byType(__CLASS__, true);
    if (count($eqLogics) == 0) {
      log::add(__CLASS__, 'debug', __FUNCTION__ . ' *	Aucun Equipement trouvé!');
      return;
    }
    foreach ($eqLogics as $eqLogic) {
      /* if ($eqLogic->getConfiguration('synced', 0) == 0) {
        log::add(__CLASS__, 'warning', $eqLogic->getHumanName() . ' Equipement invalide ou non synchronisé ');
        continue;
      } */
      $eqLogic->UpdateInfoPronote(__FUNCTION__);
    }
  }

  /*
  * Fonction exécutée automatiquement tous les jours par Jeedom
  public static function cronDaily() {}
  */

  /*
  * Permet de déclencher une action avant modification d'une variable de configuration du plugin
  * Exemple avec la variable "param3"
  
  public static function preConfig_param3( $value ) {
    // do some checks or modify on $value
    return $value;
  }
  

  /*
  * Permet de déclencher une action après modification d'une variable de configuration du plugin
  * Exemple avec la variable "param3"
  public static function postConfig_param3($value)
  {
    // no return value
  }
 */

  /*
   * Permet d'indiquer des éléments supplémentaires à remonter dans les informations de configuration
   * lors de la création semi-automatique d'un post sur le forum community
   * public static function getConfigForCommunity() {
   * return "les infos essentiel de mon plugin";
   *}
   */

  /*     * *********************Méthodes d'instance************************* */

  // Fonction exécutée automatiquement avant la création de l'équipement
  public function preInsert() {}

  // Fonction exécutée automatiquement après la création de l'équipement
  public function postInsert() {}

  // Fonction exécutée automatiquement avant la mise à jour de l'équipement
  public function preUpdate() {}

  // Fonction exécutée automatiquement après la mise à jour de l'équipement
  public function postUpdate() {}

  // Fonction exécutée automatiquement avant la sauvegarde (création ou mise à jour) de l'équipement
  public function preSave() {}

  private function getListeDefaultCommandes()
  {
    return array(
      //"Nom de la commande" => array("name", "type", "subtype", "unit", "hist", "visible", "generic_type", "template_dashboard", "template_mobile"),
      //$id = > array($name, $type, $subtype, $unit, $hist, $visible, $generic_type, $template_dashboard, $template_mobile),
      "refresh" => array('Rafraichir', 'action', 'other', "", 0, 1, "GENERIC_ACTION", 'core::badge', 'core::badge'),
      "LastLogin" => array('Derniére Mise à Jour', 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "TokenUsername" => array('Token Username', 'info', 'string', "", 0, 0, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "TokenPassword" => array('Token Password', 'info', 'string', "", 0, 0, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "TokenUrl" => array('Token_Url', 'info', 'string', "", 0, 0, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "TokenUrl" => array('Token_Id', 'info', 'string', "", 0, 0, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Nom_Eleve" => array("Nom de l'éleve", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Nom_Classe" => array('Nom de la classe', 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Etablissement" => array('Etablissement', 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Picture" => array('Picture', 'info', 'string', "", 0, 1, "GENERIC_INFO", 'picture', 'picture'),
      "URL_Ical" => array('URL Ical', 'info', 'string', "", 0, 0, "GENERIC_INFO", 'picture', 'picture'),
      "Nb_absences" => array("Nombre d'absence", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Nb_punission" => array("Nombre de punission", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Nb_devoir" => array("Nombre de Devoir", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Nb_devoirNF" => array("Nombre de Devoir non fait", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Nb_devoirF" => array("Nombre de Devoir fait", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Nb_devoir_Demain" => array("Nombre de Devoir pour le prochain jour", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Nb_devoirNF_Demain" => array("Nombre de Devoir non fait pour le prochain jour", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "Nb_devoirF_Demain" => array("Nombre de Devoir fait pour le prochain jour", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "edt_aujourdhui_debut" => array("Heure de début Aujourd'hui", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "edt_aujourdhui_fin" => array("Heure de fin Aujourd'hui", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "edt_aujourdhui_cancel" => array("Nombre de cours annulé Aujourd'hui", 'info', 'string', "cours", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "edt_prochainjour_date" => array("Date du Prochain Jour", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "edt_prochainjour_debut" => array("Heure de début du Prochain Jour", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "edt_prochainjour_fin" => array("Heure de fin du Prochain Jour", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "edt_prochainjour_cancel" => array("Nombre de cours annulé du Prochain Jour", 'info', 'string', "cours", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "edt_aujourdhui_fin" => array("Heure de fin Aujourd'hui", 'info', 'string', "", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge'),
      "edt_Cours_canceled" => array("Nombre de cours annulé", 'info', 'string', "cours", 0, 1, "GENERIC_INFO", 'core::badge', 'core::badge')
    );
  }

  // Fonction exécutée automatiquement après la sauvegarde (création ou mise à jour) de l'équipement
  public function postSave()
  {
    // je boucle pour créer toutes le commandes listée dans getlisteDefaultCommandes
    foreach ($this->getListeDefaultCommandes() as $id => $data) {
      list($name, $type, $subtype, $unit, $hist, $visible, $generic_type, $template_dashboard, $template_mobile) = $data;
      $cmd = $this->getCmd(null, $id);
      if (!is_object($cmd)) {
        $cmd = $this->getCmd(null, $id);
        $cmd = new ProJoteCmd();
        $cmd->setName($name);
        $cmd->setEqLogic_id($this->getId());
        $cmd->setType($type);
        $cmd->setSubType($subtype);
        //$cmd->setUnite($unit);
        $cmd->setLogicalId($id);
        $cmd->setIsHistorized($hist);
        $cmd->setIsVisible($visible);
        $cmd->setDisplay('generic_type', $generic_type);
        $cmd->setTemplate('dashboard', $template_dashboard);
        $cmd->setTemplate('mobile', $template_mobile);
        $cmd->save();
      }
    }
    //Je crée les entrer pour le TOKEN de l'utilisateur

  }

  // Fonction exécutée automatiquement avant la suppression de l'équipement
  public function preRemove() {}

  // Fonction exécutée automatiquement après la suppression de l'équipement
  public function postRemove()
  {
    $eqId = $this->getId();
    $dataDir = '/var/www/html/plugins/ProJote/data/' . $eqId;

    // Fonction récursive pour supprimer un dossier et tous ses fichiers et sous-dossiers
    function deleteDirectory($dir)
    {
      if (!file_exists($dir)) {
        return true;
      }

      if (!is_dir($dir)) {
        return unlink($dir);
      }

      foreach (scandir($dir) as $item) {
        if ($item == '.' || $item == '..') {
          continue;
        }

        if (!deleteDirectory($dir . DIRECTORY_SEPARATOR . $item)) {
          return false;
        }
      }

      return rmdir($dir);
    }

    // Supprimer le dossier correspondant à l'EqID
    if (deleteDirectory($dataDir)) {
      log::add('ProJote', 'info', 'Le dossier ' . $dataDir . ' a été supprimé avec succès.');
    } else {
      log::add('ProJote', 'error', 'Erreur lors de la suppression du dossier ' . $dataDir);
    }
  }


  /* Permet de crypter/décrypter automatiquement des champs de configuration des équipements
  * Exemple avec le champ "Mot de passe" (password)*/
  function my_encrypt($data, $passphrase)
  {
    $secret_key = hex2bin($passphrase);
    $iv = openssl_random_pseudo_bytes(openssl_cipher_iv_length('aes-256-cbc'));
    $encrypted_64 = openssl_encrypt($data, 'aes-256-cbc', $secret_key, 0, $iv);
    $iv_64 = base64_encode($iv);
    $json = new stdClass();
    $json->iv = $iv_64;
    $json->data = $encrypted_64;
    return base64_encode(json_encode($json));
  }

  function my_decrypt($data, $passphrase)
  {
    $secret_key = hex2bin($passphrase);
    $json = json_decode(base64_decode($data));
    $iv = base64_decode($json->{'iv'});
    $encrypted_64 = $json->{'data'};
    $data_encrypted = base64_decode($encrypted_64);
    $decrypted = openssl_decrypt($data_encrypted, 'aes-256-cbc', $secret_key, OPENSSL_RAW_DATA, $iv);
    return $decrypted;
  }


  /*
    * Permet de modifier l'affichage du widget (également utilisable par les commandes)
  public function toHtml($_version = 'dashboard')
  {
  }*/



  /*     * **********************Getteur Setteur*************************** */
  /*La requéte envoyé au deamon*/
  public static function sendToDaemon($params)
  {
    log::add(__CLASS__, 'debug',  'Envoie vers le deamon');
    $deamon_info = self::deamon_info();
    if ($deamon_info['state'] != 'ok') {
      throw new Exception("Le démon n'est pas démarré");
    }
    $params['apikey'] = jeedom::getApiKey(__CLASS__);
    $payLoad = json_encode($params);
    $socket = socket_create(AF_INET, SOCK_STREAM, 0);
    socket_connect($socket, '127.0.0.1', config::byKey('socketport', __CLASS__, '55369'));

    socket_write($socket, $payLoad, strlen($payLoad));
    socket_close($socket);
  }


  public function UpdateInfoPronote($command = "Test")
  {
    $apikey = jeedom::getApiKey(__CLASS__);
    $Cpttype = $this->getConfiguration("Cpttype", "");
    $login = $this->getConfiguration("login", "");
    $CAS = $this->getConfiguration("CasEnt", "ViaUrl");
    $url = $this->getConfiguration("url", "NC");
    $CptParent = $this->getConfiguration("CptParent", "0");
    $password = $this->getConfiguration("password", "");
    //$password = $this->my_encrypt($password, "084781141BD01304180B9B58120E4E058C1434394DDED646BF4ECC95380B9442");
    $CmdId = $this->getId();
    $TokenId = (is_object($cmdTokenId = $this->getCmd(null, 'TokenId'))) ? $cmdTokenId->execCmd() : '';
    $TokenUsername = (is_object($cmdTokenUsername = $this->getCmd(null, 'TokenUsername'))) ? $cmdTokenUsername->execCmd() : '';
    $TokenPassword = (is_object($cmdTokenPassword = $this->getCmd(null, 'TokenPassword'))) ? $cmdTokenPassword->execCmd() : '';
    $TokenUrl = (is_object($cmdTokenUrl = $this->getCmd(null, 'TokenUrl'))) ? $cmdTokenUrl->execCmd() : '';
    $enfant = $this->getConfiguration("enfant", "");
    $values = array('command' => $command, 'cpttype' => $Cpttype, 'apikey' => $apikey, 'cas' => $CAS, 'CptParent' => $CptParent, 'login' => $login, 'password' => $password, 'url' => $url, 'enfant' => $enfant, 'CmdId' => $CmdId, 'TokenId' => $TokenId, 'TokenUsername' => $TokenUsername, 'TokenPassword' => $TokenPassword, 'TokenUrl' => $TokenUrl);
    $values = json_encode($values);
    if (log::convertLogLevel(log::getLogLevel(__CLASS__)) == "debug") {
      log::add(__CLASS__, 'debug', $value);
    }
    $socket = socket_create(AF_INET, SOCK_STREAM, 0);
    socket_connect($socket, '127.0.0.1', config::byKey('socketport', __CLASS__, '55369'));
    log::add(__CLASS__, 'debug', 'Envoie au demon Python des infos Pronotes');
    socket_write($socket, $values, strlen($values));
    socket_close($socket);
  }

  //Aldarande : 04/01/2025

  public function ReadEnfantToken()
  {
    $eqLogicId = $this->getId();
    $filePath = '/var/www/html/plugins/ProJote/data/' . $eqLogicId . '/enfant.ProJote.json.txt';

    if (!file_exists($filePath)) {
      throw new Exception('Fichier JSON introuvable : ' . $filePath);
    }

    $jsonContent = file_get_contents($filePath);
    if ($jsonContent === false) {
      throw new Exception('Erreur lors de la lecture du fichier JSON : ' . $filePath);
    }

    $data = json_decode($jsonContent, true);
    if ($data === null) {
      throw new Exception('Erreur lors du décodage du fichier JSON : ' . $filePath);
    }
    $TokenData = isset($data['Token']) ? $data['Token'] : [];
    // Mise à jour des commandes avec les données du fichier JSON
    // foreach ($data as $key => $value) {
    //$eqLogic->checkAndUpdateCmd($key, $value);
    //}
    log::add('ProJote', 'debug', 'Class ReadEnfantToken::Résultat LoginToken : ' . json_encode($TokenData));
    $eqLogic = eqLogic::byId($eqLogicId);
    // Correspondance des clés JSON avec les commandes Jeedom
    log::add('ProJote', 'debug', 'Class ReadEnfantToken:: Clé JSON : ' . $TokenData['pronote_url']);
    if (isset($TokenData['pronote_url']) && $eqLogic->getCmd(null, 'TokenUrl')) {
      $eqLogic->checkAndUpdateCmd('TokenUrl', $TokenData['pronote_url']);
    } else {
      log::add('ProJote', 'debug', 'Class ReadEnfantToken:: Clé JSON non trouvée : pronote_url');
    }
    log::add('ProJote', 'debug', 'Class ReadEnfantToken:: Clé TokenUsername : ' . $TokenData['username']);
    if (isset($TokenData['username']) && $eqLogic->getCmd(null, 'TokenUsername')) {
      $eqLogic->checkAndUpdateCmd('TokenUsername', $TokenData['username']);
    } else {
      log::add('ProJote', 'debug', 'Class ReadEnfantToken:: Clé JSON non trouvée : username');
    }
    log::add('ProJote', 'debug', 'Class ReadEnfantToken:: Clé TokenPassword : ' . $TokenData['password']);
    if (isset($TokenData['password']) && $eqLogic->getCmd(null, 'TokenPassword')) {

      $eqLogic->checkAndUpdateCmd('TokenPassword', $TokenData['password']);
    } else {
      log::add('ProJote', 'debug', 'Class ReadEnfantToken:: Clé JSON non trouvée : password');
    }
    log::add('ProJote', 'debug', 'Class ReadEnfantToken:: Clé TokenPassword : ' . $TokenData['client_identifier']);
    if (isset($TokenData['client_identifier']) && $eqLogic->getCmd(null, 'TokenId')) {
      $eqLogic->checkAndUpdateCmd('TokenId', $TokenData['client_identifier']);
    } else {
      log::add('ProJote', 'debug', 'Class ReadEnfantToken:: Clé JSON non trouvée : client_identifier');
    }
    $output = True;
    return $output;
  }
}




class ProJoteCmd extends cmd
{
  /*     * *************************Attributs****************************** */

  /*
  public static $_widgetPossibility = array();
  */

  /*     * ***********************Methode static*************************** */


  /*     * *********************Methode d'instance************************* */

  /*
  * Permet d'empêcher la suppression des commandes même si elles ne sont pas dans la nouvelle configuration de l'équipement envoyé en JS
  public function dontRemoveCmd() {
    return true;
  }
  */

  // Exécution d'une commande
  public function execute($options = 'Default')
  {
    $eqlogic = $this->getEqLogic(); //récupère l'éqlogic de la commande $this
    switch ($this->getLogicalId()) { //vérifie le logicalid de la commande
      case 'refresh': // LogicalId de la commande rafraîchir que l’on a créé dans la méthode Postsave de la classe vdm .
        //Aldarande - 18/02/2024 : Changement à faire si apres
        $eqlogic->UpdateInfoPronote($options); //On lance la fonction UpdateInfoPronote() pour récupérer les infos 
        $date = date("d-m-Y H:i:s"); // transfert la date d'éxécution dans la variable $date 
        $eqlogic->checkAndUpdateCmd('LastLogin', $date); //on met à jour la commande avec le LogicalId "LastLogin"  de l'eqlogic avec la variable $date 
        break;
    }
  }
  /*     * **********************Getteur Setteur*************************** */
}
