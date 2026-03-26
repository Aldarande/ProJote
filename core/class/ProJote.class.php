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

/**
 * Ce fichier contient la définition des classes principales du plugin ProJote.
 * - ProJote : Gère les équipements (les "objets" ProJote dans Jeedom).
 * - ProJoteCmd : Gère les commandes (actions et infos) de ces équipements.
 */
require_once __DIR__  . '/../../../../core/php/core.inc.php';

/**
 * Classe principale du plugin ProJote.
 *
 * Hérite de la classe `eqLogic` de Jeedom, ce qui signifie qu'un objet `ProJote`
 * est un "équipement" dans Jeedom. Il a un nom, un objet parent, est visible
 * sur le dashboard, possède des commandes, etc.
 *
 * Rôle de cette classe :
 * - Gérer le cycle de vie du démon Python (ProJoted.py) qui tourne en fond.
 * - Définir la configuration de chaque équipement (identifiants, tokens...).
 * - Créer et gérer les commandes Jeedom associées (ex: "Nombre de devoirs", "Rafraîchir").
 * - Lancer les mises à jour des données depuis Pronote (via le démon).
 * - Interagir avec la base de données Jeedom pour sauvegarder/lire sa configuration.
 */
class ProJote extends eqLogic
{
  /**
   * Clés de configuration à chiffrer automatiquement en base de données.
   *
   * Jeedom chiffre automatiquement les valeurs des clés listées ici avant de
   * les sauvegarder. C'est une mesure de sécurité pour les données sensibles.
   * Le déchiffrement est aussi automatique lors de la lecture.
   *
   * @var array
   */
  public static $_encryptConfigKey = array('Token_password');

  /**
   * Options exposées dans l'éditeur de widget Jeedom (onglet Affichage avancé).
   * Permet à l'utilisateur de personnaliser la couleur d'accentuation et la taille du widget.
   */
  public static $_widgetPossibility = [
    'custom'         => true,
    'custom::layout' => false,
    'parameters'     => [
      'accent_color' => [
        'allow_displayType' => ['dashboard', 'mobile'],
        'type'              => 'color',
        'label'             => 'Couleur d\'accentuation',
        'default'           => '#94C904',
      ],
    ],
  ];

  /**
   * Vérifie l'état du démon Python (ProJoted.py).
   *
   * Le "démon" est un processus Python qui tourne en permanence en arrière-plan
   * pour maintenir la connexion avec Pronote et récupérer les données.
   *
   * Cette méthode vérifie si le démon est en cours d'exécution en se basant sur
   * un "fichier PID". Au démarrage, le démon écrit son numéro de processus (PID)
   * dans ce fichier. Pour savoir si le démon est vivant, il suffit de vérifier
   * si un processus avec ce PID existe encore sur le système.
   *
   * @return array Un tableau décrivant l'état : ['state' => 'ok' ou 'nok', ...].
   */
  public static function deamon_info()
  {
    $return = array();
    $return['log'] = __CLASS__; // Le nom du fichier de log associé
    $return['state'] = 'nok';   // État par défaut : considéré comme arrêté

    $pid_file = jeedom::getTmpFolder(__CLASS__) . '/deamon.pid';

    // Si le fichier PID existe, le démon a été démarré au moins une fois.
    if (file_exists($pid_file)) {
      $pid = trim(file_get_contents($pid_file));
      // On vérifie si le processus correspondant au PID est toujours actif.
      // posix_getsid() est une fonction système qui renvoie l'ID de session du processus.
      // Si le processus n'existe pas, elle renvoie false.
      if (@posix_getsid($pid)) {
        $return['state'] = 'ok'; // Le démon est en cours d'exécution.
      } else {
        // Le fichier PID est là, mais le processus est mort (ex: a crashé).
        // C'est un état invalide, il faut nettoyer en supprimant le fichier PID.
        log::add(__CLASS__, 'error', "Le fichier PID du démon existe mais le processus est introuvable. Nettoyage.");
        unlink($pid_file);
      }
    }
    // 'launchable' indique à Jeedom si le démon peut être démarré.
    $return['launchable'] = 'ok';
    return $return;
  }

  /**
   * Démarre le démon Python ProJoted.py.
   *
   * Cette méthode est appelée par Jeedom (bouton "Démarrer" dans la config)
   * ou lors de l'activation du plugin.
   *
   * Elle construit et exécute une commande shell pour lancer le script Python
   * avec tous les paramètres nécessaires à son fonctionnement.
   */
  public static function deamon_start()
  {
    // On s'assure que toute instance précédente est bien arrêtée avant d'en lancer une nouvelle.
    self::deamon_stop();
    $deamon_info = self::deamon_info();
    if ($deamon_info['launchable'] != 'ok') {
      throw new Exception(__('Veuillez vérifier la configuration', __FILE__));
    }

    // Chemin vers le script du démon
    $path = realpath(dirname(__FILE__) . '/../../resources/ProJoted');
    if (!$path) {
      throw new Exception(__('Chemin vers le démon introuvable.', __FILE__));
    }

    // Paramètres pour le démon :
    $socketport = config::byKey('socketport', __CLASS__, '55369'); // Port d'écoute pour les commandes PHP -> Python
    $callback = network::getNetworkAccess('internal', 'http:127.0.0.1:port:comp'); // URL de retour pour les données Python -> PHP
    $loglevel = log::convertLogLevel(log::getLogLevel(__CLASS__)); // Niveau de log (debug, info, error...)
    $apikey = jeedom::getApiKey(__CLASS__); // Clé API pour sécuriser le callback
    $pid_file = jeedom::getTmpFolder(__CLASS__) . '/deamon.pid'; // Chemin du fichier PID à créer

    // Construction de la commande shell
    $data_dir = dirname(dirname(__FILE__)) . '/data';
    $cmd = system::getCmdPython3(__CLASS__) . " {$path}/ProJoted.py";
    $cmd .= ' --loglevel ' . $loglevel;
    $cmd .= ' --socketport ' . $socketport;
    $cmd .= ' --datadir ' . escapeshellarg($data_dir);
    $cmd .= ' --callback ' . $callback . '/plugins/ProJote/core/php/jeeProJote.php';
    $cmd .= ' --apikey ' . $apikey;
    $cmd .= ' --cycle 3'; // Inutilisé actuellement, pourrait servir pour le rafraîchissement
    $cmd .= ' --pid ' . $pid_file;

    log::add(__CLASS__, 'info', 'Lancement du démon ' . __CLASS__);
    log::add(__CLASS__, 'debug', 'Commande d\'exécution du démon : ' . $cmd);

    // Exécution de la commande en arrière-plan
    // `>> ... 2>&1` redirige toute la sortie (normale et erreurs) vers le fichier de log.
    // `&` à la fin exécute la commande en tâche de fond, pour ne pas bloquer Jeedom.
    exec($cmd . ' >> ' . log::getPathToLog(__CLASS__) . ' 2>&1 &');

    // Attendre que le démon démarre et crée son fichier PID (max 20 secondes).
    // C'est une étape cruciale pour s'assurer que le démarrage a bien eu lieu.
    $i = 0;
    while ($i < 20) {
      $deamon_info = self::deamon_info();
      if ($deamon_info['state'] == 'ok') {
        break; // Succès ! Le démon est démarré.
      }
      sleep(1); // Attendre 1 seconde avant de revérifier.
      $i++;
    }

    if ($i >= 20) {
      log::add(__CLASS__, 'error', __('Impossible de lancer le démon. Vérifiez les logs pour plus de détails (erreurs Python, etc).', __FILE__), 'unableStartDeamon');
      return false;
    }

    message::removeAll(__CLASS__, 'unableStartDeamon'); // Nettoyer les anciens messages d'erreur.
    return true;
  }

  /**
   * Arrête le démon Python.
   *
   * Lit le PID dans le fichier, puis utilise la commande système "kill"
   * pour terminer proprement le processus.
   */
  public static function deamon_stop()
  {
    $pid_file = jeedom::getTmpFolder(__CLASS__) . '/deamon.pid';
    if (file_exists($pid_file)) {
      $pid = intval(trim(file_get_contents($pid_file)));
      system::kill($pid);
      // La suppression du fichier PID est gérée par le démon lui-même à l'extinction,
      // mais on peut forcer la suppression ici si nécessaire.
      // unlink($pid_file);
    }
    // En sécurité supplémentaire, on peut tuer tout processus qui porterait le nom du script.
    // Utile si le fichier PID a été perdu.
    system::kill('ProJoted.py');
    sleep(1);
  }

  // Fonctions utilitaires pour obtenir des chemins importants du plugin de manière fiable.
  private static function getDataPath()
  {
    $path = realpath(__DIR__ . '/../..') . DIRECTORY_SEPARATOR . 'data';
    if (!is_dir($path)) mkdir($path);
    return $path;
  }
  /**
   * Tâche planifiée (cron) exécutée toutes les heures par Jeedom.
   *
   * C'est le point d'entrée pour la mise à jour automatique des données.
   * La méthode parcourt tous les équipements ProJote actifs et déclenche
   * une demande de rafraîchissement des données pour chacun.
   */
  public static function cronHourly()
  {
    $heure = date('G'); // Heure actuelle (0-23)

    // Pronote est souvent indisponible la nuit. Inutile de faire des requêtes.
    if ($heure >= 22 || $heure < 4) {
      log::add(__CLASS__, 'debug', "Cron_hourly : Il est $heure heure, période de non-activité. Aucune mise à jour lancée.");
      return;
    }

    // L'utilisateur peut définir une heure de démarrage pour les crons dans la config du plugin.
    $hour_cron = config::byKey('hour_cron', __CLASS__);
    if (!empty($hour_cron) && $heure < $hour_cron) {
      log::add(__CLASS__, 'debug', "Cron_hourly : L'heure de récupération est définie à $hour_cron" . "h, il est trop tôt.");
      return;
    }

    // Récupérer tous les équipements actifs de ce plugin.
    foreach (self::byType(__CLASS__, true) as $eqLogic) {
      if ($eqLogic instanceof ProJote) {
        // Pour chaque équipement, appeler la méthode qui demande la mise à jour.
        $eqLogic->UpdateInfoPronote(__FUNCTION__);
      }
    }
  }

  // --- MÉTHODES DE CYCLE DE VIE DE L'ÉQUIPEMENT (HOOKS) ---
  // Ces méthodes sont appelées automatiquement par Jeedom à des moments
  // clés de la vie d'un équipement.

  /**
   * Exécutée avant la sauvegarde d'un équipement (création ou mise à jour).
   */
  public function preSave()
  {
    // 1. Générer un identifiant unique (UUID) pour cet équipement s'il n'en a pas.
    // Cet UUID est utilisé pour identifier l'appareil de manière unique auprès de Pronote.
    if (empty($this->getConfiguration('uuid'))) {
      // Format UUID standard (RFC 4122 v4) — sans préfixe identifiant le plugin
      $uuid = sprintf('%s-%s-%s-%s-%s',
        bin2hex(random_bytes(4)), bin2hex(random_bytes(2)),
        bin2hex(random_bytes(2)), bin2hex(random_bytes(2)),
        bin2hex(random_bytes(6))
      );
      $this->setConfiguration('uuid', $uuid);
      log::add('ProJote', 'debug', 'preSave : UUID généré pour ' . $this->getHumanName());
    }

    // 2. Définir la largeur par défaut du tile sur le dashboard (~1/3 de page).
    if (empty($this->getDisplay('width'))) {
      $this->setDisplay('width', '300px');
    }

    // 3. Protéger les tokens de session contre l'écrasement.
    // Quand on sauvegarde depuis l'interface web, les champs de token ne sont pas présents
    // dans le formulaire. Sans cette protection, Jeedom les effacerait de la BDD.
    // On recharge donc l'ancienne configuration depuis la BDD pour restaurer les tokens
    // s'ils sont sur le point d'être effacés.
    $tokenKeys = ['Token_pronote_url', 'Token_username', 'Token_password', 'Token_client_identifier'];
    foreach ($tokenKeys as $key) {
      if (empty($this->getConfiguration($key))) { // Si la nouvelle config n'a pas ce token...
        $existing = eqLogic::byId($this->getId()); // ...on charge l'ancienne depuis la BDD...
        if (is_object($existing) && !empty($existing->getConfiguration($key))) {
          $this->setConfiguration($key, $existing->getConfiguration($key)); // ...et on le restaure.
          log::add('ProJote', 'debug', 'preSave : Token "' . $key . '" restauré depuis la BDD.');
        }
      }
    }
  }

  /**
   * Exécutée après la sauvegarde (création ou mise à jour) de l'équipement.
   *
   * Rôle principal : créer toutes les commandes Jeedom nécessaires si elles
   * n'existent pas encore, et configurer leur visibilité.
   */
  public function postSave()
  {
    // 1. Créer les commandes manquantes à partir d'une liste modèle.
    foreach ($this->getListeDefaultCommandes() as $id => $data) {
      $cmd = $this->getCmd(null, $id);
      if (!is_object($cmd)) {
        list($name, $type, $subtype, $unit, $hist, $visible, $generic_type, $template_dashboard, $template_mobile) = $data;
        log::add('ProJote', 'debug', 'postSave : Création de la commande manquante : ' . $name);
        $cmd = new ProJoteCmd();
        $cmd->setName($name);
        $cmd->setEqLogic_id($this->getId());
        $cmd->setType($type);
        $cmd->setSubType($subtype);
        $cmd->setLogicalId($id);
        $cmd->setIsHistorized($hist);
        $cmd->setIsVisible($visible);
        $cmd->setDisplay('generic_type', $generic_type);
        $cmd->setTemplate('dashboard', $template_dashboard);
        $cmd->setTemplate('mobile', $template_mobile);
        $cmd->save();
      }
    }

    // 2. Supprimer la commande Widget si elle existe encore (migration depuis l'ancienne architecture).
    // Le widget est maintenant affiché via toHtml() sur l'eqLogic, plus via une commande dédiée.
    $widgetCmd = $this->getCmd(null, 'Widget');
    if (is_object($widgetCmd)) {
      $widgetCmd->remove();
      log::add('ProJote', 'info', 'postSave : commande Widget migrée et supprimée (remplacée par toHtml).');
    }

    // 3. La visibilité des commandes info est gérée par l'utilisateur via la case "Afficher"
    // dans l'onglet Commandes. Elle détermine quelles sections apparaissent dans le widget.
    // On ne la modifie pas ici : les valeurs par défaut viennent de getListeDefaultCommandes().
  }

  /**
   * Exécutée avant la suppression de l'équipement.
   *
   * Rôle : nettoyer les fichiers de données spécifiques à cet équipement
   * pour ne pas laisser de "fichiers orphelins" sur le disque.
   */
  public function preRemove()
  {
    $eqLogicId = $this->getId();
    log::add('ProJote', 'debug', 'Début de la suppression des données pour l\'EqID : ' . $eqLogicId);
    $dataDir = self::getDataPath() . DIRECTORY_SEPARATOR . $eqLogicId;

    // Fonction pour supprimer un dossier et tout son contenu.
    function deleteDirectory($dir) {
      if (!file_exists($dir)) return true;
      if (!is_dir($dir)) return unlink($dir);
      foreach (scandir($dir) as $item) {
        if ($item == '.' || $item == '..') continue;
        if (!deleteDirectory($dir . DIRECTORY_SEPARATOR . $item)) return false;
      }
      return rmdir($dir);
    }

    if (deleteDirectory($dataDir)) {
      log::add('ProJote', 'info', 'Le dossier de données ' . $dataDir . ' a été supprimé avec succès.');
    } else {
      log::add('ProJote', 'error', 'Erreur lors de la suppression du dossier de données ' . $dataDir);
    }
  }

  /**
   * Retourne la liste de toutes les commandes à créer pour un équipement.
   *
   * C'est le "modèle" ou "template" de toutes les commandes qu'un équipement
   * ProJote doit avoir. La méthode `postSave` utilise cette liste pour
   * vérifier et créer les commandes manquantes.
   *
   * @return array Tableau associatif décrivant chaque commande.
   */
  private function getListeDefaultCommandes()
  {
    return array(
      // logicalId => [Nom, Type, Sous-type, Unité, Historiser, Visible, Type Générique, Widget Dash, Widget Mobile]
      // Visible=1 : la section correspondante apparaît dans le widget du dashboard.
      // L'utilisateur peut décocher "Afficher" dans l'onglet Commandes pour masquer une section.
      "refresh"               => array('Rafraichir',                                       'action', 'other',   "",      0, 1, "GENERIC_ACTION",  'core::badge',          'core::badge'),
      "LastLogin"             => array('Derniére Mise à Jour',                             'info',   'string',  "",      0, 0, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nom_Eleve"             => array("Nom de l'éleve",                                   'info',   'string',  "",      0, 1, "GENERIC_NAME ",   'core::badge',          'core::badge'),
      "Nom_Classe"            => array('Nom de la classe',                                 'info',   'string',  "",      0, 1, "GENERIC_NAME ",   'core::badge',          'core::badge'),
      "Etablissement"         => array('Etablissement',                                    'info',   'string',  "",      0, 1, "GENERIC_NAME ",   'core::badge',          'core::badge'),
      "Picture"               => array('Photo de profil',                                  'info',   'string',  "",      0, 1, "GENERIC_PICTURE", 'ProJote::picture',     'picture'),
      "URL_Ical"              => array('URL Ical',                                         'info',   'string',  "",      0, 1, "GENERIC_URL",     'core::badge',          'core::badge'),
      "Nb_absences"           => array("Nombre d'absence",                                 'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_punitions"          => array("Nombre de punitions",                              'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_retard"             => array("Nombre de retard",                                 'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir"             => array("Nombre de devoir",                                 'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_NF"          => array("Nombre de devoir non fait",                        'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_F"           => array("Nombre de devoir fait",                            'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_Demain"      => array("Nombre de devoir pour le prochain jour",           'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_Demain_NF"   => array("Nombre de devoir non fait pour le prochain jour",  'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_Demain_F"    => array("Nombre de devoir fait pour le prochain jour",      'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_aujourdhui_debut"  => array("Heure de début Aujourd'hui",                       'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_aujourdhui_fin"    => array("Heure de fin Aujourd'hui",                         'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_aujourdhui_cancel" => array("Nombre de cours annulé Aujourd'hui",               'info',   'numeric', "cours", 0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_prochainjour_date" => array("Date du Prochain Jour",                            'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_prochainjour_debut"=> array("Heure de début du Prochain Jour",                  'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_prochainjour_fin"  => array("Heure de fin du Prochain Jour",                    'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_prochainjour_cancel"=>array("Nombre de cours annulé du Prochain Jour",          'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_Cours_canceled"    => array("Nombre de cours annulé",                           'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_prochainjour"      => array("Emploi du temps du Prochain Jour",                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::edt',         'core::badge'),
      "edt_aujourdhui"        => array("Emploi du temps Aujourd'hui",                      'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::edt',         'core::badge'),
      "devoir"                => array("Liste des devoirs",                                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::devoir',      'core::badge'),
      "devoir_Demain"         => array("Liste des devoirs pour demain",                    'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::devoir',      'core::badge'),
      "absence"               => array("Liste des absences",                               'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::absence',     'core::badge'),
      "derniere_absence"      => array("Dernière absence",                                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::absence',     'core::badge'),
      "retard"                => array("Liste des 10 derniers retards",                    'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::retard',      'core::badge'),
      "dernier_retard"        => array("Dernier retard",                                   'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::retard',      'core::badge'),
      "punition"              => array("Liste des punitions",                              'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::punition',    'core::badge'),
      "derniere_punition"     => array("Dernière punition",                                'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::punition',    'core::badge'),
      "note"                  => array("Liste des notes",                                  'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::note',        'core::badge'),
      "derniere_note"         => array("Dernière note",                                    'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::note',        'core::badge'),
      "notifications"         => array("liste des notifications",                          'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::notification','core::badge'),
      "derniere_notification" => array("Dernière notification",                            'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::notification','core::badge'),
      "competences"           => array("Liste des compétences",                            'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::competence',  'core::badge'),
    );
  }

  /**
   * Chiffre une chaîne avec AES-256-CBC.
   * Un IV aléatoire est généré à chaque appel pour que le même texte
   * donne des résultats différents à chaque chiffrement.
   * @param string $data       Texte clair à chiffrer
   * @param string $passphrase Clé en hexadécimal (64 hex = 32 octets)
   * @return string            JSON {iv, data} encodé en base64
   */
  function my_encrypt($data, $passphrase)
  {
    $secret_key    = hex2bin($passphrase);
    $iv            = openssl_random_pseudo_bytes(openssl_cipher_iv_length('aes-256-cbc'));
    $encrypted_64  = openssl_encrypt($data, 'aes-256-cbc', $secret_key, 0, $iv);
    $iv_64         = base64_encode($iv);
    $json          = new stdClass();
    $json->iv      = $iv_64;
    $json->data    = $encrypted_64;
    return base64_encode(json_encode($json));
  }

  /**
   * Déchiffre une chaîne produite par my_encrypt().
   * @param string $data       Données chiffrées (base64 du JSON {iv, data})
   * @param string $passphrase Clé identique à celle utilisée lors du chiffrement
   * @return string            Texte clair original
   */
  function my_decrypt($data, $passphrase)
  {
    $secret_key     = hex2bin($passphrase);
    $json           = json_decode(base64_decode($data));
    $iv             = base64_decode($json->{'iv'});
    $data_encrypted = base64_decode($json->{'data'});
    return openssl_decrypt($data_encrypted, 'aes-256-cbc', $secret_key, OPENSSL_RAW_DATA, $iv);
  }

  /**
   * Envoie une commande au démon Python via une socket TCP.
   *
   * C'est la méthode de communication principale de PHP vers le démon Python.
   * PHP se connecte au port d'écoute du démon, envoie les données au format JSON,
   * puis referme la connexion.
   *
   * @param array $params Tableau des données à envoyer au démon.
   */
  public static function sendToDaemon($params)
  {
    log::add(__CLASS__, 'debug',  'Envoi d\'une commande générique vers le démon.');
    if (self::deamon_info()['state'] != 'ok') {
      throw new Exception("Le démon ProJote n'est pas démarré.");
    }
    $params['apikey'] = jeedom::getApiKey(__CLASS__); // Ajout de la clé API pour la sécurité
    $payLoad = json_encode($params);
    $socket = socket_create(AF_INET, SOCK_STREAM, 0);
    socket_connect($socket, '127.0.0.1', config::byKey('socketport', __CLASS__, '55369'));
    socket_write($socket, $payLoad, strlen($payLoad));
    socket_close($socket);
  }

  /**
   * Génère et retourne le HTML du widget affiché sur le dashboard Jeedom.
   *
   * Cette méthode est appelée automatiquement par Jeedom à chaque fois qu'il
   * doit afficher la tuile de cet équipement sur le dashboard. Elle lit les
   * données enregistrées par le démon (via jeeProJote.php → configuration 'widget_json'),
   * charge le template HTML, remplace les variables, et retourne le HTML final.
   *
   * Le widget s'affiche TOUJOURS, même sans commande dédiée. Il se rafraîchit
   * automatiquement via JavaScript en écoutant la commande LastLogin.
   *
   * @param string $_version 'dashboard' ou 'mobile'
   * @return string HTML du widget
   */
  public function toHtml($_version = 'dashboard')
  {
    // 1. Vérifications et tableau de remplacement standard Jeedom.
    //    preToHtml() gère droits, isEnable, cache, #width#, #height#, etc.
    $replace = $this->preToHtml($_version);
    if (!is_array($replace)) {
      return $replace; // cache hit ou équipement non autorisé
    }

    // 2. Forcer la largeur par défaut si non définie par l'utilisateur.
    if ($replace['#width#'] === 'auto' || empty($this->getDisplay('width'))) {
      $replace['#width#'] = '300px';
      $this->setDisplay('width', '300px');
      $this->save();
    }

    // 3. Lire les données du widget.
    $widgetJson = $this->getConfiguration('widget_json', '{}');
    $widgetData = json_decode($widgetJson, true);
    if (!is_array($widgetData)) {
      $widgetData = [];
    }

    // 4. Carte de visibilité des sections.
    $vis = [];
    foreach ($this->getCmd('info') as $cmd) {
      $vis[$cmd->getLogicalId()] = (bool)$cmd->getIsVisible();
    }
    $visibility = [
      'header'           => $vis['Nom_Eleve']       ?? true,
      'photo'            => $vis['Picture']          ?? true,
      'vie_scolaire'     => (($vis['Nb_absences'] ?? true) || ($vis['Nb_retard'] ?? true) || ($vis['Nb_punitions'] ?? true) || ($vis['Nb_devoir_NF'] ?? true)),
      'edt_aujourdhui'   => $vis['edt_aujourdhui']   ?? true,
      'edt_prochainjour' => $vis['edt_prochainjour'] ?? true,
      'notes'            => $vis['note']             ?? true,
      'devoirs'          => $vis['devoir']           ?? true,
      'absences'         => $vis['Nb_absences']      ?? true,
      'retards'          => $vis['Nb_retard']        ?? true,
      'punitions'        => $vis['Nb_punitions']     ?? true,
    ];

    // 5. ID de la commande LastLogin pour le rafraîchissement JS.
    $lastLoginCmd   = $this->getCmd(null, 'LastLogin');
    $lastLoginCmdId = is_object($lastLoginCmd) ? $lastLoginCmd->getId() : 0;

    // 6. Charger le template ProJote et injecter les données.
    $templatePath = dirname(__FILE__) . '/../template/dashboard/ProJote.html';
    if (!file_exists($templatePath)) {
      log::add('ProJote', 'error', 'toHtml : template introuvable : ' . $templatePath);
      return '<div style="color:red;">Widget ProJote : template introuvable.</div>';
    }
    $flags   = JSON_HEX_TAG | JSON_HEX_AMP;
    $content = file_get_contents($templatePath);
    $content = str_replace('#id#',             $this->getId(),                   $content);
    $content = str_replace('#lastLoginCmdId#', $lastLoginCmdId,                  $content);
    $content = str_replace('#initData#',       json_encode($widgetData, $flags), $content);
    $content = str_replace('#visibilityMap#',  json_encode($visibility, $flags), $content);
    // Couleur d'accentuation (paramètre éditeur de widget avancé)
    $accentColor = $replace['#accent_color#'] ?? '#94C904';
    if (empty($accentColor) || $accentColor === 'transparent') $accentColor = '#94C904';
    $content = str_replace('#accent_color#', $accentColor, $content);

    // 7. Injecter dans le wrapper standard Jeedom (#cmd#) puis appliquer le template core.
    //    Cela donne le tile correct avec les poignées de redimensionnement/déplacement.
    $replace['#cmd#']          = $content;
    $replace['#eqLogic_class#'] = 'eqLogic_layout_default';
    $replace['#calledFrom#']    = __CLASS__;

    $_v = jeedom::versionAlias($_version);
    $coreTemplate = getTemplate('core', $_v, 'eqLogic');

    return $this->postToHtml($_version, template_replace($replace, $coreTemplate));
  }

  /**
   * Demande au démon Python de mettre à jour les données Pronote pour cet équipement.
   *
   * C'est une méthode spécifique qui rassemble toutes les informations de connexion
   * (tokens, identifiants, etc.) de l'équipement actuel et les envoie au démon
   * avec l'instruction de se connecter à Pronote et de rafraîchir les données.
   *
   * @param string $command Le contexte de l'appel (ex: "cronHourly", "refresh").
   */
  public function UpdateInfoPronote($command = "Test")
  {
    // Rassembler toutes les informations de configuration nécessaires
    $params = array(
      'command'     => $command,
      'CmdId'       => $this->getId(),
      'cpttype'     => $this->getConfiguration("Cpttype"),
      'cas'         => $this->getConfiguration("CasEnt", "ViaUrl"),
      'CptParent'   => $this->getConfiguration("CptParent", "0"),
      'url'         => $this->getConfiguration("url", "NC"),
      'login'       => $this->getConfiguration("login"),
      'password'    => $this->getConfiguration("password"),
      'enfant'      => $this->getConfiguration("enfant"),
      'TokenId'     => $this->getConfiguration('Token_client_identifier'),
      'TokenUsername'=> $this->getConfiguration('Token_username'),
      'TokenPassword'=> $this->getConfiguration('Token_password'),
      'TokenUrl'    => html_entity_decode($this->getConfiguration('Token_pronote_url', '')),
      'TokenUuid'   => $this->getConfiguration('uuid', 'ProJote'),
      'Log'         => log::convertLogLevel(log::getLogLevel(__CLASS__)),
    );
    // Envoi des paramètres au démon via la méthode générique.
    self::sendToDaemon($params);
    log::add(__CLASS__, 'info', 'Demande de mise à jour envoyée au démon pour ' . $this->getHumanName() . ' (contexte: ' . $command . ')');
  }

  /**
   * Lit un fichier JSON local et met à jour la configuration de l'équipement.
   *
   * Après une connexion réussie (via `LoginConnect.py` ou `QRConnect.py`),
   * le script Python écrit les informations du compte et le token de session
   * dans un fichier `enfant.ProJote.json.txt`.
   * Cette méthode lit ce fichier, en extrait les informations, et les sauvegarde
   * dans la configuration de l'équipement en base de données.
   *
   * @return array Les données lues du fichier JSON.
   */
  public function ReadEnfantToken()
  {
    $eqLogicId = $this->getId();
    $filePath = self::getDataPath() . "/{$eqLogicId}/enfant.ProJote.json.txt";

    if (!file_exists($filePath)) throw new Exception('Fichier token JSON introuvable : ' . $filePath);

    $jsonContent = file_get_contents($filePath);
    if ($jsonContent === false) throw new Exception('Erreur de lecture du fichier JSON : ' . $filePath);

    $data = json_decode($jsonContent, true);
    if ($data === null) throw new Exception('Erreur de décodage du fichier JSON : ' . $filePath . ' - Contenu: ' . $jsonContent);

    log::add('ProJote', 'debug', 'Lecture et traitement du fichier token JSON pour eqLogic ' . $eqLogicId);

    // Sauvegarde des tokens de session
    if (isset($data['Token'])) {
      $this->setConfiguration('Token_pronote_url', $data['Token']['pronote_url'] ?? '');
      $this->setConfiguration('Token_username', $data['Token']['username'] ?? '');
      $this->setConfiguration('Token_password', $data['Token']['password'] ?? '');
      $this->setConfiguration('Token_client_identifier', $data['Token']['client_identifier'] ?? '');
    }

    // Sauvegarde des informations de l'élève
    if (isset($data['Eleve']) && $data['Eleve'] !== 'Unknown') $this->setConfiguration('Eleve', $data['Eleve']);
    if (isset($data['Classe']) && $data['Classe'] !== 'Unknown') $this->setConfiguration('Classe', $data['Classe']);
    if (isset($data['Etablissement']) && $data['Etablissement'] !== 'Unknown') $this->setConfiguration('Etablissement', $data['Etablissement']);
    if (!empty($data['Liste_Enfant'])) $this->setConfiguration('Liste_Enfant', is_string($data['Liste_Enfant']) ? $data['Liste_Enfant'] : json_encode($data['Liste_Enfant']));
    if (!empty($data['Ical'])) $this->setConfiguration('Ical', $data['Ical']);

    $this->save(); // Sauvegarder toutes les modifications en BDD.
    log::add('ProJote', 'info', 'La configuration a été mise à jour depuis le fichier token pour ' . $this->getHumanName());
    return $data;
  }

  /**
   * Met à jour la commande affichant le nom de l'élève.
   */
  public function SwitchEleve($value)
  {
    if (isset($value)) {
      $this->checkAndUpdateCmd('Nom_Eleve', $value);
      log::add('ProJote', 'debug', 'Mise à jour du nom de l\'élève affiché : ' . $value);
      return true;
    }
    return false;
  }
}

/**
 * Classe pour les commandes du plugin ProJote.
 *
 * Hérite de la classe `cmd` de Jeedom.
 * Permet de définir un comportement spécifique pour les commandes, notamment
 * pour l'exécution des commandes de type "action".
 */
class ProJoteCmd extends cmd
{
  /**
   * Exécute une commande de type "action".
   *
   * C'est le point d'entrée pour toutes les actions déclenchées depuis Jeedom
   * (scénario, dashboard, etc.).
   *
   * @param mixed $options Options passées par Jeedom (souvent inutilisées).
   */
  public function execute($options = 'Default')
  {
    $eqlogic = $this->getEqLogic(); // Récupère l'équipement parent de cette commande.
    if (!is_object($eqlogic)) {
      log::add('ProJote', 'error', 'Équipement parent introuvable pour la commande ' . $this->getHumanName());
      return;
    }

    // Aiguillage en fonction de l'identifiant logique de la commande
    switch ($this->getLogicalId()) {
      case 'refresh':
        // Si la commande "Rafraîchir" est appelée...
        log::add('ProJote', 'info', 'Rafraîchissement manuel demandé pour ' . $eqlogic->getHumanName());
        // ...on lance la mise à jour des informations depuis Pronote.
        if ($eqlogic instanceof ProJote) {
          $eqlogic->UpdateInfoPronote('refresh');
        }
        break;
        // On pourrait ajouter d'autres 'case' pour d'autres commandes 'action'.
    }
  }
}
