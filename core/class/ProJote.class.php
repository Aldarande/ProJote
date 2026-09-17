<?php
/* ProJote — plugin Jeedom pour Pronote
 * Copyright (C) 2024-2026 Aldarande
 *
 * This file is part of ProJote.
 *
 * ProJote is free software: you can redistribute it and/or modify it under
 * the terms of the GNU Affero General Public License as published by the
 * Free Software Foundation, either version 3 of the License, or (at your
 * option) any later version.
 *
 * ProJote is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public
 * License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
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
   * Options exposées dans l'onglet Affichage → Paramètres avancés de l'équipement.
   * Injectées dans ProJote.html via str_replace() dans toHtml() :
   *   #accent_color# — couleur CSS d'accentuation (défaut #94C904)
   *   #font_size#    — taille de police de base (défaut 12px)
   *   #default_tab#  — onglet ouvert au chargement : dv|notes|abs|ret|pun (défaut dv)
   *   #edt_nav_mode# — navigation EDT : next_day (J+1 fixe) | arrows (flèches J+1→J+4)
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
      'font_size' => [
        'allow_displayType' => ['dashboard', 'mobile'],
        'type'              => 'select',
        'label'             => 'Taille de police',
        'default'           => '12px',
        'values'            => ['10px' => '10', '11px' => '11', '12px' => '12 (défaut)', '13px' => '13', '14px' => '14', '15px' => '15', '16px' => '16'],
      ],
      'default_tab' => [
        'allow_displayType' => ['dashboard', 'mobile'],
        'type'              => 'select',
        'label'             => 'Onglet par défaut',
        'default'           => 'dv',
        'values'            => ['dv' => 'Devoirs', 'notes' => 'Notes', 'abs' => 'Absences', 'ret' => 'Retards', 'pun' => 'Punitions', 'menu' => 'Menu cantine', 'msg' => 'Messagerie', 'stats' => 'Statistiques', 'alertes' => 'Alertes', 'comp' => 'Compétences'],
      ],
      'edt_nav_mode' => [
        'allow_displayType' => ['dashboard', 'mobile'],
        'type'              => 'select',
        'label'             => 'Navigation EDT jours suivants',
        'default'           => 'next_day',
        'values'            => ['next_day' => 'Jour suivant (J+1)', 'arrows' => 'Flèches (J+1 à J+4)'],
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
  /**
   * Vérifie que les dépendances Python (venv + pronotepy) sont installées.
   * Utilisé par Jeedom pour afficher le statut "Dépendances OK/NOK" dans la config du plugin.
   */
  public static function dependancy_info()
  {
    $return = array();
    $return['log'] = __CLASS__ . '_update';
    $return['state'] = 'ok';

    $venvPython = realpath(dirname(__FILE__) . '/../../resources') . '/python_venv/bin/python3';
    if (!file_exists($venvPython)) {
      $return['state'] = 'nok';
      return $return;
    }

    // On vérifie non seulement que pronotepy est importable, mais aussi qu'il
    // satisfait le plancher de version de requirements.txt. Sans ce contrôle, un
    // venv resté en 2.14.x (installé avant la mise à jour du plugin) était
    // rapporté « OK » alors que toute connexion échoue sur les serveurs PRONOTE
    // 2026 (KeyError: 'onload'), sans que Jeedom ne propose de réinstaller.
    exec(escapeshellarg($venvPython) . ' -c "import pronotepy; print(pronotepy.__version__)" 2>/dev/null', $output, $rc);
    if ($rc !== 0) {
      $return['state'] = 'nok';
      return $return;
    }

    $installed = trim(implode('', $output));
    $required = self::requiredPronotepyVersion();
    if ($required !== null && $installed !== '' && version_compare($installed, $required, '<')) {
      log::add(__CLASS__, 'warning', 'pronotepy ' . $installed . ' installé, ' . $required . ' minimum requis : réinstallation des dépendances nécessaire.');
      $return['state'] = 'nok';
    }

    return $return;
  }

  /**
   * Version minimale de pronotepy exigée, lue dans resources/requirements.txt
   * (source de vérité unique, partagée avec post-install.sh).
   *
   * @return string|null la version minimale, ou null si elle n'a pas pu être lue.
   */
  private static function requiredPronotepyVersion()
  {
    $requirements = dirname(__FILE__) . '/../../resources/requirements.txt';
    if (!is_readable($requirements)) {
      return null;
    }
    $content = file_get_contents($requirements);
    if ($content === false || !preg_match('/^\s*pronotepy\s*>=\s*([0-9][0-9a-zA-Z.\-]*)/m', $content, $matches)) {
      return null;
    }
    return $matches[1];
  }

  /**
   * Installe les dépendances Python en lançant le script post-install.sh en arrière-plan.
   * Appelé par Jeedom quand l'utilisateur clique sur "Installer les dépendances".
   */
  public static function dependancy_install()
  {
    log::add(__CLASS__, 'info', 'Installation des dépendances ProJote (venv Python)...');
    $script = realpath(dirname(__FILE__) . '/../../resources') . '/post-install.sh';
    $logFile = log::getPathToLog(__CLASS__ . '_update');
    exec('/bin/bash ' . escapeshellarg($script) . ' >> ' . escapeshellarg($logFile) . ' 2>&1 &');
    return array('script' => $script);
  }

  /**
   * Chemins (relatifs au dossier du plugin) à exclure des sauvegardes Jeedom.
   * Le venv Python (~50 Mo de binaires mono-architecture) est reconstruit par
   * post-install.sh : inutile et contre-productif de l'embarquer dans un backup
   * (restauration sur une autre architecture = venv inutilisable).
   */
  public static function backupExclude()
  {
    return array(
      'resources/python_venv',
    );
  }

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

    // Bloquer le démarrage du démon si les dépendances ne sont pas installées.
    $dep = self::dependancy_info();
    if ($dep['state'] !== 'ok') {
      $return['launchable'] = 'nok';
      $return['launchable_message'] = __('Les dépendances Python ne sont pas installées. Cliquez sur "Installer les dépendances" dans la page de configuration du plugin.', __FILE__);
    } else {
      $return['launchable'] = 'ok';
    }

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
    $data_dir = dirname(dirname(dirname(__FILE__))) . '/data';
    $venvPython = realpath(dirname(__FILE__) . '/../../resources') . '/python_venv/bin/python3';
    $cmd = escapeshellarg($venvPython) . " {$path}/ProJoted.py";
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

  // --- SUSPENSION TEMPORAIRE DE L'ADRESSE IP PAR PRONOTE ---
  // Pronote limite le nombre de connexions par adresse IP. Au-delà, il suspend
  // l'IP : toute requête reçoit alors une page d'avertissement au lieu de la page
  // de connexion. Comme l'IP est celle de la box entière, la pause est GLOBALE au
  // plugin (tous les équipements) et non propre à un enfant. Tant que la fenêtre
  // court, aucune requête n'est envoyée au démon : insister prolongerait le blocage.

  /** Clé de configuration stockant la fin de la fenêtre de pause (timestamp). */
  const IP_SUSPENSION_CONFIG_KEY = 'ip_suspended_until';

  /** logicalId du message dans le centre de messages (évite les doublons). */
  const IP_SUSPENSION_MESSAGE_ID = 'ip_suspended';

  /** Durée de pause par défaut quand le démon n'en fournit pas (30 min). */
  const IP_SUSPENSION_DEFAULT_DELAY = 1800;

  /**
   * Secondes restantes avant la fin de la fenêtre de pause.
   *
   * @return int 0 si aucune suspension n'est en cours.
   */
  public static function ipSuspensionRemaining()
  {
    $until = (int) config::byKey(self::IP_SUSPENSION_CONFIG_KEY, __CLASS__, 0);
    $remaining = $until - time();
    return ($remaining > 0) ? $remaining : 0;
  }

  /**
   * Ouvre (ou prolonge) la fenêtre de pause suite à une suspension d'IP.
   *
   * Alimente le centre de messages Jeedom et journalise l'incident. Le message
   * porte un logicalId : il est mis à jour au lieu d'être dupliqué à chaque cycle.
   *
   * @param int    $until   Timestamp de fin fourni par le démon (0 = durée par défaut).
   * @param string $context Équipement ou action à l'origine de la détection (log).
   * @return int Timestamp de fin retenu.
   */
  public static function declareIpSuspension($until = 0, $context = '')
  {
    $until = (int) $until;
    if ($until <= time()) {
      $until = time() + self::IP_SUSPENSION_DEFAULT_DELAY;
    }
    // Ne jamais raccourcir une fenêtre déjà ouverte plus longue.
    $current = (int) config::byKey(self::IP_SUSPENSION_CONFIG_KEY, __CLASS__, 0);
    if ($current > $until) {
      $until = $current;
    }
    config::save(self::IP_SUSPENSION_CONFIG_KEY, $until, __CLASS__);

    $heure = date('H:i', $until);
    $minutes = (int) ceil(($until - time()) / 60);

    log::add(__CLASS__, 'warning', '[IP SUSPENDUE] ' . ($context != '' ? $context . ' — ' : '')
      . 'Pronote a suspendu l\'adresse IP de cette installation. Mise en pause de '
      . $minutes . ' min, reprise à ' . $heure . '.');

    message::add(
      __CLASS__,
      'Pronote a temporairement suspendu l\'adresse IP de votre Jeedom (trop de connexions en peu de temps). '
        . 'Toutes les mises à jour ProJote sont en pause jusqu\'à ' . $heure . ' pour laisser le blocage se lever. '
        . 'Évitez de relancer une validation de compte avant cette heure.',
      '',
      self::IP_SUSPENSION_MESSAGE_ID
    );

    return $until;
  }

  /**
   * Referme la fenêtre de pause (appelée dès qu'une connexion réussit).
   *
   * @return bool true si une fenêtre était ouverte.
   */
  public static function clearIpSuspension()
  {
    if ((int) config::byKey(self::IP_SUSPENSION_CONFIG_KEY, __CLASS__, 0) === 0) {
      return false;
    }
    config::save(self::IP_SUSPENSION_CONFIG_KEY, 0, __CLASS__);
    if (method_exists('message', 'byPluginLogicalId')) {
      $msg = message::byPluginLogicalId(__CLASS__, self::IP_SUSPENSION_MESSAGE_ID);
      if (is_object($msg)) {
        $msg->remove();
      }
    }
    log::add(__CLASS__, 'info', 'Connexion à Pronote rétablie : fin de la pause pour suspension d\'IP.');
    return true;
  }

  /**
   * Tâche planifiée (cron) exécutée toutes les heures par Jeedom.
   *
   * C'est le point d'entrée pour la mise à jour automatique des données.
   * La méthode parcourt tous les équipements ProJote actifs et déclenche
   * une demande de rafraîchissement des données pour chacun.
   */
  /** Heure de début par défaut de la plage de collecte. */
  const HEURE_DEBUT_DEFAUT = 7;

  /** Heure de fin par défaut de la plage de collecte (exclue). */
  const HEURE_FIN_DEFAUT = 20;

  /**
   * Lit une borne de la plage de collecte dans la configuration du plugin.
   *
   * La clé historique 'hour_cron' était lue par cronHourly() mais n'existait
   * dans aucun formulaire : personne ne pouvait la renseigner, et le code qui
   * la consultait ne servait à rien. Elle est remplacée par une vraie plage,
   * réglable dans la configuration du plugin.
   *
   * @param string $_cle 'heure_debut' ou 'heure_fin'.
   * @param int $_defaut valeur retenue si la configuration est vide ou aberrante.
   * @return int une heure entre 0 et 23.
   */
  private static function heureCollecte($_cle, $_defaut)
  {
    $valeur = config::byKey($_cle, __CLASS__, '');
    if ($valeur === '' || $valeur === null || !is_numeric($valeur)) {
      return $_defaut;
    }
    $heure = (int) $valeur;
    return ($heure >= 0 && $heure <= 23) ? $heure : $_defaut;
  }

  /**
   * L'heure donnée tombe-t-elle dans la plage [début, fin[ ?
   *
   * La plage peut enjamber minuit (début 20, fin 7) : c'est un réglage
   * légitime pour qui veut collecter la nuit. Début et fin identiques veulent
   * dire « à toute heure » — refuser toute collecte serait un piège silencieux.
   *
   * @param int $_heure heure courante (0-23).
   * @param int $_debut première heure collectée.
   * @param int $_fin première heure NON collectée.
   * @return bool
   */
  private static function dansLaPlage($_heure, $_debut, $_fin)
  {
    if ($_debut === $_fin) {
      return true;
    }
    if ($_debut < $_fin) {
      return $_heure >= $_debut && $_heure < $_fin;
    }
    return $_heure >= $_debut || $_heure < $_fin;
  }

  public static function cronHourly()
  {
    // Fenêtre de pause : l'adresse IP de la box est suspendue par Pronote.
    // Aucun équipement n'est interrogé tant qu'elle n'est pas écoulée.
    $suspension = self::ipSuspensionRemaining();
    if ($suspension > 0) {
      log::add(__CLASS__, 'info', 'Cron_hourly : adresse IP suspendue par Pronote, mise à jour reportée à '
        . date('H:i', time() + $suspension) . '.');
      return;
    }

    $heure = (int) date('G'); // Heure actuelle (0-23)

    // Droit à la déconnexion : hors de la plage choisie, aucune collecte. La vie
    // scolaire s'arrête le soir, et une note ou une punition récupérée à 23h ne
    // sert qu'à déclencher une notification au mauvais moment. Accessoirement,
    // Pronote est souvent indisponible la nuit.
    // La commande « Rafraîchir » reste utilisable à toute heure : c'est une
    // action volontaire de l'utilisateur, pas une sollicitation automatique.
    $debut = self::heureCollecte('heure_debut', self::HEURE_DEBUT_DEFAUT);
    $fin   = self::heureCollecte('heure_fin', self::HEURE_FIN_DEFAUT);
    if (!self::dansLaPlage($heure, $debut, $fin)) {
      log::add(__CLASS__, 'debug', "Cron_hourly : il est {$heure}h, hors de la plage de collecte ({$debut}h-{$fin}h). Aucune mise à jour lancée.");
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
   * Surcharge eqLogic::save() pour ignorer silencieusement les équipements orphelins.
   *
   * Contexte : lors de la sauvegarde via l'interface Jeedom, le JS peut soumettre
   * un objet ProJote sans nom (équipement fantôme issu d'un état intermédiaire du DOM).
   * Le core Jeedom lève une exception "Le nom de l'équipement ne peut pas être vide"
   * AVANT que preSave() ne s'exécute. On intercepte ici pour éviter cette erreur.
   *
   * Note : la signature $_direct = false est obligatoire pour respecter la compatibilité
   * avec eqLogic::save($_direct = false) sous PHP 8.x (E_COMPILE_ERROR sinon).
   *
   * @param bool $_direct true = pas de cycle preSave/postSave (usage interne Jeedom).
   */
  public function save($_direct = false)
  {
    if (empty(trim((string)$this->getName()))) {
      log::add('ProJote', 'warning', 'ProJote::save() : équipement sans nom ignoré (id=' . $this->getId() . ', order=' . $this->getOrder() . ')');
      return;
    }
    parent::save($_direct);
  }

  /**
   * Exécutée avant la sauvegarde d'un équipement (création ou mise à jour).
   */
  public function preSave()
  {
    // 1. Générer un identifiant unique (UUID) pour cet équipement s'il n'en a pas.
    // Cet UUID est utilisé pour identifier l'appareil de manière unique auprès de Pronote.
    if (empty($this->getConfiguration('uuid'))) {
      // Format UUID standard (RFC 4122 v4) — sans préfixe identifiant le plugin
      $uuid = sprintf(
        '%s-%s-%s-%s-%s',
        bin2hex(random_bytes(4)),
        bin2hex(random_bytes(2)),
        bin2hex(random_bytes(2)),
        bin2hex(random_bytes(2)),
        bin2hex(random_bytes(6))
      );
      $this->setConfiguration('uuid', $uuid);
      log::add('ProJote', 'debug', 'preSave : UUID généré pour ' . $this->getHumanName());
    }

    // 2. Définir la largeur par défaut du tile sur le dashboard (~1/3 de page).
    if (empty($this->getDisplay('width'))) {
      $this->setDisplay('width', '360px');
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
      // Catégorie décochée : la commande n'est pas créée. Une commande déjà
      // existante n'est jamais supprimée ici — elle porte un historique et
      // peut être citée dans un scénario. Elle cesse simplement d'être
      // alimentée, et l'utilisateur la supprime lui-même s'il le souhaite.
      $categorie = self::categorieDeLaCommande($id);
      if ($categorie !== null && !$this->categorieActive($categorie)) {
        continue;
      }
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

    // 1bis. Migration v1.1.0 : aligner l'historisation des commandes existantes sur le modèle.
    // Les versions < 1.1.0 créaient Nb_absences / Nb_retard / Nb_devoir_NF sans historisation.
    // On (ré)active l'historisation pour les commandes que le modèle marque historisées (hist=1),
    // sans jamais la désactiver. Idempotent : ne fait rien si déjà historisée.
    // $cmd->save() ne déclenche pas eqLogic::postSave → pas de récursion.
    foreach ($this->getListeDefaultCommandes() as $id => $data) {
      if (empty($data[4])) { // index 4 = historiser
        continue;
      }
      $cmd = $this->getCmd(null, $id);
      if (is_object($cmd) && $cmd->getIsHistorized() != 1) {
        $cmd->setIsHistorized(1);
        $cmd->save();
        log::add('ProJote', 'info', 'postSave : historisation activée sur ' . $id . ' (alignement modèle v1.1.0).');
      }
    }

    // 1ter. Migration v1.6.0 : poser les gabarits mobiles sur les commandes existantes.
    // Ces commandes portent du JSON. Faute de gabarit mobile, le modèle leur
    // donnait 'core::badge' : l'application mobile affichait donc la chaîne JSON
    // brute, illisible. Les gabarits existent depuis la v1.6.0, mais setTemplate()
    // n'est appelé qu'à la création : sans cette reprise, seuls les équipements
    // créés après la mise à jour en auraient bénéficié.
    //
    // On ne remplace que 'core::badge' — et 'core::picture', l'ancien gabarit de
    // cœur de la photo : le modèle disait 'picture', que setTemplate() préfixe
    // lui-même en 'core::picture'. Un gabarit choisi par l'utilisateur n'est
    // jamais écrasé.
    foreach ($this->getListeDefaultCommandes() as $id => $data) {
      $modele = $data[8];
      if ($modele === 'core::badge') {
        continue;
      }
      $cmd = $this->getCmd(null, $id);
      if (!is_object($cmd)) {
        continue;
      }
      $actuel = $cmd->getTemplate('mobile', '');
      if ($actuel === 'core::badge' || $actuel === 'core::picture' || $actuel === 'picture' || $actuel === '') {
        $cmd->setTemplate('mobile', $modele);
        $cmd->save();
        log::add('ProJote', 'info', 'postSave : gabarit mobile « ' . $modele . ' » posé sur ' . $id . ' (reprise v1.6.0).');
      }
    }

    // 2. Supprimer la commande Widget si elle existe encore (migration depuis l'ancienne architecture).
    // Le widget est maintenant affiché via toHtml() sur l'eqLogic, plus via une commande dédiée.
    $widgetCmd = $this->getCmd(null, 'Widget');
    if (is_object($widgetCmd)) {
      $widgetCmd->remove();
      log::add('ProJote', 'info', 'postSave : commande Widget migrée et supprimée (remplacée par toHtml).');
    }

    // 3. Supprimer les commandes orphelines sans nom ou sans logicalId.
    // Cela peut arriver suite à un bug JS (let vs var dans addCmdToTable) qui créait
    // des lignes vides en base. Sans ce nettoyage, la sauvegarde échoue avec
    // "Le nom de la commande ne peut pas être vide".
    foreach ($this->getCmd() as $cmd) {
      if (empty(trim((string)$cmd->getName())) || empty(trim((string)$cmd->getLogicalId()))) {
        log::add('ProJote', 'warning', 'postSave : suppression commande orpheline (order=' . $cmd->getOrder() . ', id=' . $cmd->getId() . ')');
        $cmd->remove();
      }
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

    if (self::deleteDirectory($dataDir)) {
      log::add('ProJote', 'info', 'Le dossier de données ' . $dataDir . ' a été supprimé avec succès.');
    } else {
      log::add('ProJote', 'error', 'Erreur lors de la suppression du dossier de données ' . $dataDir);
    }
  }

  /**
   * Supprime un dossier et tout son contenu de manière récursive
   * @param string $dir
   * @return bool
   */
  private static function deleteDirectory($dir)
  {
    if (!file_exists($dir)) return true;
    if (!is_dir($dir)) return unlink($dir);
    foreach (scandir($dir) as $item) {
      if ($item == '.' || $item == '..') continue;
      if (!self::deleteDirectory($dir . DIRECTORY_SEPARATOR . $item)) return false;
    }
    return rmdir($dir);
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
  /**
   * Onglets Pronote que l'utilisateur peut ne pas vouloir suivre.
   *
   * Un équipement crée une centaine de commandes, toutes collectées à chaque
   * cycle. Pour une fratrie de trois enfants cela fait trois cents commandes en
   * base et autant de lignes sur le tableau de bord, alors que tout le monde ne
   * suit ni la messagerie, ni la cantine, ni les compétences.
   *
   * Chaque entrée porte l'onglet correspondant côté démon : décocher une
   * catégorie ne se contente pas de masquer des commandes, elle **supprime
   * aussi les requêtes** vers Pronote (cf. cadence.py et ProJoted.collecter).
   *
   * Tout est actif par défaut : un équipement existant ne bouge pas.
   */
  private static function categoriesOptionnelles()
  {
    return array(
      'messagerie' => array(
        'onglet'   => 'Messages',
        'commandes' => array('Nb_messages', 'Nb_messages_non_lus', 'dernier_message_expediteur',
          'dernier_message_sujet', 'dernier_message_date', 'dernier_message_extrait', 'messages_html'),
      ),
      'menus' => array(
        'onglet'   => 'Menus',
        'commandes' => array('menu_midi_aujourdhui', 'menu_midi_demain', 'menu_semaine', 'Nb_menus_semaine'),
      ),
      'competences' => array(
        'onglet'   => 'Competences',
        'commandes' => array('competences'),
      ),
      'notifications' => array(
        'onglet'   => 'Notifications',
        'commandes' => array('notifications', 'derniere_notification'),
      ),
    );
  }

  /**
   * La catégorie est-elle suivie pour cet équipement ?
   *
   * Absence de réglage = actif : les équipements créés avant cette version
   * gardent exactement leur comportement.
   *
   * @param string $_cle clé de categoriesOptionnelles().
   * @return bool
   */
  public function categorieActive($_cle)
  {
    $valeur = $this->getConfiguration('collecte_' . $_cle, '');
    // Vide couvre deux cas qui veulent tous deux dire « suivi » : la clé n'a
    // jamais été enregistrée (équipement antérieur à la 1.5.0), ou le
    // formulaire a été sauvegardé avant que le champ caché ne soit renseigné.
    // (int) '' vaut 0 : sans ce garde, une collecte s'arrêterait toute seule.
    if ($valeur === '' || $valeur === null || is_array($valeur)) {
      return true;
    }
    return (int) $valeur === 1;
  }

  /**
   * Onglets que le démon doit sauter pour cet équipement.
   *
   * @return array liste de clés d'onglets (ex. ['Messages', 'Menus']).
   */
  public function ongletsDesactives()
  {
    $desactives = array();
    foreach (self::categoriesOptionnelles() as $cle => $categorie) {
      if (!$this->categorieActive($cle)) {
        $desactives[] = $categorie['onglet'];
      }
    }
    return $desactives;
  }

  /**
   * Catégorie optionnelle à laquelle appartient une commande, ou null.
   *
   * @param string $_logicalId identifiant logique de la commande.
   * @return string|null
   */
  private static function categorieDeLaCommande($_logicalId)
  {
    foreach (self::categoriesOptionnelles() as $cle => $categorie) {
      if (in_array($_logicalId, $categorie['commandes'], true)) {
        return $cle;
      }
    }
    return null;
  }

  private function getListeDefaultCommandes()
  {
    return array(
      // logicalId => [Nom, Type, Sous-type, Unité, Historiser, Visible, Type Générique, Widget Dash, Widget Mobile]
      // Visible=1 : la section correspondante apparaît dans le widget du dashboard.
      // L'utilisateur peut décocher "Afficher" dans l'onglet Commandes pour masquer une section.
      "refresh"               => array('Rafraichir',                                       'action', 'other',   "",      0, 1, "GENERIC_ACTION",  'core::badge',          'core::badge'),
      "LastLogin"             => array('Derniére Mise à Jour',                             'info',   'string',  "",      0, 0, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Statut_Connexion"      => array('Statut connexion',                                  'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nom_Eleve"             => array("Nom de l'éleve",                                   'info',   'string',  "",      0, 1, "GENERIC_NAME ",   'core::badge',          'core::badge'),
      "Nom_Classe"            => array('Nom de la classe',                                 'info',   'string',  "",      0, 1, "GENERIC_NAME ",   'core::badge',          'core::badge'),
      "Etablissement"         => array('Etablissement',                                    'info',   'string',  "",      0, 1, "GENERIC_NAME ",   'core::badge',          'core::badge'),
      // Période Pronote en cours (trimestre / semestre) et ses bornes.
      "periode_courante"      => array('Période en cours',                                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "periode_debut"         => array('Début de la période',                              'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "periode_fin"           => array('Fin de la période',                                'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      // Bornes de l'année scolaire (englobe toutes les périodes).
      "annee_debut"           => array("Début de l'année scolaire",                        'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "annee_fin"             => array("Fin de l'année scolaire",                          'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      // Prochaines vacances ou prochain jour férié (Pronote les publie ensemble).
      "vacances_nom"          => array('Prochaines vacances',                              'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "vacances_debut"        => array('Début des prochaines vacances',                    'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "vacances_fin"          => array('Fin des prochaines vacances',                      'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "Picture"               => array('Photo de profil',                                  'info',   'string',  "",      0, 1, "GENERIC_PICTURE", 'ProJote::picture',     'ProJote::picture'),
      "URL_Ical"              => array('URL Ical',                                         'info',   'string',  "",      0, 1, "GENERIC_URL",     'core::badge',          'core::badge'),
      "Nb_absences"           => array("Nombre d'absence",                                 'info',   'numeric', "",      1, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_punitions"          => array("Nombre de punitions",                              'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_retard"             => array("Nombre de retard",                                 'info',   'numeric', "",      1, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir"             => array("Nombre de devoir",                                 'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_NF"          => array("Nombre de devoir non fait",                        'info',   'numeric', "",      1, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_F"           => array("Nombre de devoir fait",                            'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_Demain"      => array("Nombre de devoir pour le prochain jour",           'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_Demain_NF"   => array("Nombre de devoir non fait pour le prochain jour",  'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_devoir_Demain_F"    => array("Nombre de devoir fait pour le prochain jour",      'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_aujourdhui_debut"  => array("Heure de début Aujourd'hui",                       'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_aujourdhui_fin"    => array("Heure de fin Aujourd'hui",                         'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_aujourdhui_cancel" => array("Nombre de cours annulé Aujourd'hui",               'info',   'numeric', "cours", 0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_prochainjour_date" => array("Date du Prochain Jour",                            'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_prochainjour_debut" => array("Heure de début du Prochain Jour",                  'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_prochainjour_fin"  => array("Heure de fin du Prochain Jour",                    'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_prochainjour_cancel" => array("Nombre de cours annulé du Prochain Jour",          'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_Cours_canceled"    => array("Nombre de cours annulé",                           'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_prochainjour"      => array("Emploi du temps du Prochain Jour",                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::edt',         'ProJote::edt'),
      // J+1 à J+4 (4 prochains jours scolaires)
      "edt_J1"                => array("Emploi du temps J+1",                              'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::edt',         'ProJote::edt'),
      "edt_J1_date"           => array("Date J+1",                                         'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_J1_debut"          => array("Heure de début J+1",                              'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_J1_fin"            => array("Heure de fin J+1",                                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_J1_cancel"         => array("Cours annulés J+1",                               'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_J2"                => array("Emploi du temps J+2",                              'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::edt',         'ProJote::edt'),
      "edt_J2_date"           => array("Date J+2",                                         'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_J2_debut"          => array("Heure de début J+2",                              'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_J2_fin"            => array("Heure de fin J+2",                                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_J2_cancel"         => array("Cours annulés J+2",                               'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_J3"                => array("Emploi du temps J+3",                              'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::edt',         'ProJote::edt'),
      "edt_J3_date"           => array("Date J+3",                                         'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_J3_debut"          => array("Heure de début J+3",                              'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_J3_fin"            => array("Heure de fin J+3",                                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_J3_cancel"         => array("Cours annulés J+3",                               'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_J4"                => array("Emploi du temps J+4",                              'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::edt',         'ProJote::edt'),
      "edt_J4_date"           => array("Date J+4",                                         'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_J4_debut"          => array("Heure de début J+4",                              'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "edt_J4_fin"            => array("Heure de fin J+4",                                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_J4_cancel"         => array("Cours annulés J+4",                               'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "edt_aujourdhui"        => array("Emploi du temps Aujourd'hui",                      'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::edt',         'ProJote::edt'),
      "devoir"                => array("Liste des devoirs",                                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::devoir',      'ProJote::devoir'),
      "devoir_Demain"         => array("Liste des devoirs pour demain",                    'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::devoir',      'ProJote::devoir'),
      "absence"               => array("Liste des absences",                               'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::absence',     'ProJote::absence'),
      "derniere_absence"      => array("Dernière absence",                                 'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::absence',     'ProJote::absence'),
      "retard"                => array("Liste des 10 derniers retards",                    'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::retard',      'ProJote::retard'),
      "dernier_retard"        => array("Dernier retard",                                   'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::retard',      'ProJote::retard'),
      "punition"              => array("Liste des punitions",                              'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::punition',    'ProJote::punition'),
      "derniere_punition"     => array("Dernière punition",                                'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::punition',    'ProJote::punition'),
      "note"                  => array("Liste des notes",                                  'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::note',        'ProJote::note'),
      "derniere_note"         => array("Dernière note",                                    'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::note',        'ProJote::note'),
      // ── Statistiques (v1.1.0) ──────────────────────────────────────────────
      "moyenne_generale"      => array("Moyenne générale",                                 'info',   'numeric', "/20",   1, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "matiere_en_baisse"     => array("Matière(s) en baisse",                             'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "notifications"         => array("liste des notifications",                          'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::notification', 'ProJote::notification'),
      "derniere_notification" => array("Dernière notification",                            'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::notification', 'ProJote::notification'),
      "competences"           => array("Liste des compétences",                            'info',   'string',  "",      0, 1, "GENERIC_INFO",    'ProJote::competence',  'ProJote::competence'),
      // ── Menu cantine (v1.0.1) ──────────────────────────────────────────────
      "menu_midi_aujourdhui"  => array("Menu cantine - midi aujourd'hui",                  'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "menu_midi_demain"      => array("Menu cantine - midi demain",                       'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "menu_semaine"          => array("Menu cantine - semaine",                           'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_menus_semaine"      => array("Nombre de menus sur la semaine",                   'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      // ── Messagerie Pronote (v1.0.1) ────────────────────────────────────────
      "Nb_messages"           => array("Nombre de discussions",                            'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "Nb_messages_non_lus"   => array("Nombre de messages non lus",                       'info',   'numeric', "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "dernier_message_expediteur" => array("Dernier message - expéditeur",                'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "dernier_message_sujet" => array("Dernier message - sujet",                          'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "dernier_message_date"  => array("Dernier message - date",                           'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "dernier_message_extrait" => array("Dernier message - extrait",                      'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "messages_html"         => array("Liste HTML des discussions",                       'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      // ── Prochain DS / évaluation (v1.0.1) ─────────────────────────────────
      "prochain_DS_matiere"   => array("Prochain DS - matière",                            'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "prochain_DS_date"      => array("Prochain DS - date",                               'info',   'string',  "",      0, 1, "GENERIC_TIME",    'core::badge',          'core::badge'),
      "prochain_DS_dans_jours" => array("Prochain DS - jours restants",                    'info',   'numeric', "j",     0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "prochains_DS_html"     => array("Liste HTML des prochains DS",                      'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      // ── Centre d'alertes (v1.1.0) ──────────────────────────────────────────
      "event"                 => array("Dernier événement",                               'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      // ── Nouveautés (P3, v1.1.0) — déclencheurs de scénarios ────────────────
      "nouvelle_note"         => array("Dernière nouvelle note",                          'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
      "nouveau_devoir"        => array("Dernier nouveau devoir",                          'info',   'string',  "",      0, 1, "GENERIC_INFO",    'core::badge',          'core::badge'),
    );
  }

  /**
   * Retourne la clé de chiffrement dérivée de la clé API Jeedom.
   * hash('sha256', apikey) produit 64 hex chars = 32 octets, format attendu par AES-256-CBC.
   * Cohérence PHP↔Python : Python fait hashlib.sha256(_apikey.encode()).hexdigest().
   * @return string Clé en hexadécimal (64 chars)
   */
  private static function _getEncryptionKey()
  {
    return hash('sha256', jeedom::getApiKey(__CLASS__));
  }

  /** Version d'enveloppe : AES-256-GCM, authentifié. */
  const CHIFFREMENT_VERSION = 2;

  /**
   * Chiffre une chaîne avec AES-256-GCM.
   *
   * Sert à un seul usage, et il vaut d'être dit : passer le mot de passe Pronote
   * de PHP au script Python de validation, en argument de ligne de commande.
   * Le chiffré ne vit donc que le temps d'une requête ; rien n'est conservé sous
   * cette forme.
   *
   * GCM remplace AES-256-CBC (SECURITY-AUDIT.md, finding M3). CBC ne signe pas
   * ce qu'il chiffre : un chiffré altéré se déchiffrait en octets quelconques,
   * que rien ne distinguait d'un mot de passe. GCM refuse la charge modifiée.
   * L'IV fait 12 octets, la taille pour laquelle GCM est défini.
   *
   * La dérivation de clé est inchangée et reste SHA-256 de la clé API Jeedom,
   * un secret aléatoire à forte entropie généré par le cœur — pas un mot de
   * passe humain qu'il faudrait étirer (audit P2c).
   *
   * @param string      $data       Texte clair à chiffrer
   * @param string|null $passphrase Clé hex 64 chars. Si null, utilise la clé API Jeedom.
   * @return string                 JSON {v, iv, data, tag} encodé en base64
   */
  function my_encrypt($data, $passphrase = null)
  {
    if ($passphrase === null) {
      $passphrase = self::_getEncryptionKey();
    }
    $secret_key = hex2bin($passphrase);
    $iv         = openssl_random_pseudo_bytes(12);
    $tag        = '';
    $chiffre    = openssl_encrypt($data, 'aes-256-gcm', $secret_key, OPENSSL_RAW_DATA, $iv, $tag);
    if ($chiffre === false) {
      throw new Exception(__('Chiffrement du mot de passe impossible.', __FILE__));
    }
    $json       = new stdClass();
    $json->v    = self::CHIFFREMENT_VERSION;
    $json->iv   = base64_encode($iv);
    $json->data = base64_encode($chiffre);
    $json->tag  = base64_encode($tag);
    return base64_encode(json_encode($json));
  }

  /**
   * Déchiffre une chaîne produite par my_encrypt().
   *
   * Accepte les deux enveloppes : la nouvelle (GCM, champ « v ») et l'ancienne
   * (CBC, sans « v »). Le repli ne sert qu'aux installations dont le démon
   * tournerait encore avec les fichiers de la version précédente au moment de
   * la mise à jour ; il pourra être retiré d'une version à l'autre.
   *
   * @param string      $data       Données chiffrées (base64 d'un JSON)
   * @param string|null $passphrase Clé hex 64 chars. Si null, utilise la clé API Jeedom.
   * @return string|false           Texte clair, ou false si la charge est refusée
   */
  function my_decrypt($data, $passphrase = null)
  {
    if ($passphrase === null) {
      $passphrase = self::_getEncryptionKey();
    }
    $secret_key = hex2bin($passphrase);
    $json       = json_decode(base64_decode($data));
    if (!is_object($json) || !isset($json->iv) || !isset($json->data)) {
      return false;
    }
    $iv      = base64_decode($json->iv);
    $chiffre = base64_decode($json->data);

    if (isset($json->tag)) {
      return openssl_decrypt($chiffre, 'aes-256-gcm', $secret_key, OPENSSL_RAW_DATA, $iv, base64_decode($json->tag));
    }
    // Enveloppe héritée, non authentifiée.
    return openssl_decrypt($chiffre, 'aes-256-cbc', $secret_key, OPENSSL_RAW_DATA, $iv);
  }

  /**
   * Retourne les données Pronote décodées pour un équipement donné.
   * Lit la configuration 'widget_json' (mise à jour par le démon) et la décode.
   * @param int $eqLogicId ID de l'équipement Jeedom
   * @return array|null Tableau de données, ou null si l'équipement est introuvable
   */
  public static function getPronoteData($eqLogicId)
  {
    $eqLogic = self::byId($eqLogicId);
    if (!is_object($eqLogic)) {
      log::add('ProJote', 'warning', 'getPronoteData() : équipement introuvable pour id=' . $eqLogicId);
      return null;
    }
    $json = $eqLogic->getConfiguration('widget_json', '{}');
    $data = json_decode($json, true);
    return is_array($data) ? $data : null;
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
      $replace['#width#'] = '360px';
      $this->setDisplay('width', '360px');
      $this->save();
    }

    // 3. Lire les données du widget.
    $widgetJson = $this->getConfiguration('widget_json', '{}');
    $widgetData = json_decode($widgetJson, true);
    if (!is_array($widgetData)) {
      $widgetData = [];
    }

    // 3a. État de la connexion — le widget doit pouvoir dire qu'il montre des
    //     données figées.
    //
    //     Quand un cycle échoue, jeeProJote.php s'arrête avant d'écrire
    //     'widget_json' : le blob reste celui du dernier cycle réussi. Rien ne
    //     distinguait donc un widget à jour d'un widget figé depuis des jours —
    //     l'utilisateur lisait des notes et un emploi du temps périmés en les
    //     croyant courants. La commande 'Statut_Connexion', elle, est
    //     rafraîchie sur tous les chemins, y compris ceux qui s'arrêtent tôt.
    //
    //     On la lit à l'affichage plutôt qu'au moment de la collecte : c'est la
    //     seule façon d'informer sur un cycle qui n'écrit rien.
    $cmdStatut = $this->getCmd(null, 'Statut_Connexion');
    if (is_object($cmdStatut)) {
      $statut = trim((string) $cmdStatut->execCmd());
      // Tout ce qui ne commence pas par « Connecté » est un état à signaler :
      // « Déconnecté : … », « Erreur : … », « IP suspendue — reprise à … ».
      if ($statut !== '' && stripos($statut, 'Connecté') !== 0) {
        $estSuspension = (stripos($statut, 'IP suspendue') !== false);
        $widgetData['alerte'] = array(
          'message' => $statut,
          // Date du dernier CHANGEMENT de valeur, pas de la dernière collecte :
          // c'est « depuis quand est-ce cassé », pas « quand a-t-on regardé ».
          'depuis'  => $cmdStatut->getValueDate(),
          // Une suspension d'IP se résorbe seule ; un jeton refusé demande une
          // action. Le widget ne doit pas presser l'utilisateur dans le premier cas.
          'action'  => $estSuspension ? 'attendre' : 'revalider',
        );
      }
    }

    // 3b. Recalcul de la photo en temps réel selon photo_source
    //     (indépendant du démon — toujours à jour après upload/changement de source).
    $dataDir         = realpath(dirname(__FILE__) . '/../../data');
    $manualPhotoFile = $dataDir . DIRECTORY_SEPARATOR . $this->getId() . DIRECTORY_SEPARATOR . 'profile_picture_manual.jpg';
    $manualPhotoUrl  = '/plugins/ProJote/data/' . $this->getId() . '/profile_picture_manual.jpg'
      . '?v=' . (file_exists($manualPhotoFile) ? filemtime($manualPhotoFile) : '0');
    $pronotePhotoUrl = !empty($widgetData['photo']) ? $widgetData['photo'] : null;
    // Si la photo stockée vient de Pronote (et non d'un précédent calcul manuel), on la garde.
    // On utilise le champ 'pronote_photo' s'il existe, sinon on tombe sur la valeur brute.
    if (!empty($widgetData['pronote_photo'])) {
      $pronotePhotoUrl = $widgetData['pronote_photo'];
    }
    $manualExists = file_exists($manualPhotoFile);
    // Défaut « auto » et non « none » : ce réglage a été introduit quand la photo
    // Pronote n'arrivait jamais, et masquer une image absente ne coûtait rien.
    // Depuis qu'elle remonte, ce défaut cachait une photo tout juste téléchargée
    // sans que rien ne l'explique. « auto » prend la photo Pronote et retombe
    // sur la photo manuelle à défaut ; « none » reste disponible pour qui
    // préfère les initiales.
    switch ($this->getConfiguration('photo_source', 'auto')) {
      case 'pronote':
        $resolvedPhoto = $pronotePhotoUrl ?? '';
        break;
      case 'manual':
        $resolvedPhoto = $manualExists ? $manualPhotoUrl : '';
        break;
      case 'auto':
        $resolvedPhoto = $pronotePhotoUrl ?? ($manualExists ? $manualPhotoUrl : '');
        break;
      default:
        $resolvedPhoto = ''; // 'none' → initiales
    }
    $widgetData['photo'] = $resolvedPhoto;

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
      // v1.0.1 — nouveaux onglets et badge
      'menu'             => $vis['menu_midi_aujourdhui'] ?? true,
      'messages'         => $vis['Nb_messages']      ?? true,
      'prochain_ds'      => $vis['prochain_DS_matiere'] ?? true,
      // v1.1.0 — onglet Statistiques
      'stats'            => $vis['moyenne_generale']  ?? true,
      // v1.1.0 — onglet Alertes (événements ProJote + notifications Pronote)
      'alertes'          => ($vis['event'] ?? true) || ($vis['notifications'] ?? true),
      // v1.2.0 — onglet Compétences
      'competences'      => $vis['competences']      ?? true,
    ];

    // 4b. Séries d'historique pour l'onglet Statistiques (v1.1.0).
    //     On lit l'historique Jeedom des commandes historisées, sous-échantillonné
    //     pour garder un payload léger injecté dans le widget.
    $buildSeries = function ($logicalId, $maxPoints = 40) {
      $cmd = $this->getCmd(null, $logicalId);
      if (!is_object($cmd) || $cmd->getIsHistorized() != 1) {
        return [];
      }
      try {
        $history = $cmd->getHistory(date('Y-m-d H:i:s', strtotime('-120 days')));
      } catch (Throwable $e) {
        log::add('ProJote', 'debug', 'toHtml : getHistory(' . $logicalId . ') a échoué : ' . $e->getMessage());
        return [];
      }
      if (!is_array($history) || count($history) === 0) {
        return [];
      }
      $n    = count($history);
      $step = $n > $maxPoints ? (int)ceil($n / $maxPoints) : 1;
      $series = [];
      for ($i = 0; $i < $n; $i += $step) {
        $h = $history[$i];
        $v = $h->getValue();
        if ($v === '' || $v === null || !is_numeric($v)) {
          continue;
        }
        $series[] = ['t' => $h->getDatetime(), 'v' => (float)$v];
      }
      return $series;
    };

    $mebCmd  = $this->getCmd(null, 'matiere_en_baisse');
    $statsData = [
      'moyenne'           => $buildSeries('moyenne_generale'),
      'absences'          => $buildSeries('Nb_absences'),
      'retards'           => $buildSeries('Nb_retard'),
      'devoirs_nf'        => $buildSeries('Nb_devoir_NF'),
      'matiere_en_baisse' => is_object($mebCmd) ? (string)$mebCmd->execCmd() : '',
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
    $content = str_replace('#statsData#',      json_encode($statsData, $flags),  $content);
    // Paramètres widget — lus directement depuis display.parameters_xxx
    // (preToHtml() expose display.parameters.* mais nos champs utilisent display.parameters_xxx,
    //  clé plate avec préfixe → getDisplay('parameters_xxx') est la seule source fiable)
    $accentColor = $this->getDisplay('parameters_accent_color') ?: '#94C904';
    if ($accentColor === 'transparent') $accentColor = '#94C904';
    $content = str_replace('#accent_color#', $accentColor, $content);

    $fontSize = $this->getDisplay('parameters_font_size') ?: '12px';
    $content  = str_replace('#font_size#', $fontSize, $content);

    $defaultTab = $this->getDisplay('parameters_default_tab') ?: 'dv';
    $content    = str_replace('#default_tab#', $defaultTab, $content);

    $edtNavMode = $this->getDisplay('parameters_edt_nav_mode') ?: 'next_day';
    $content    = str_replace('#edt_nav_mode#', $edtNavMode, $content);

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
    // Fenêtre de pause « IP suspendue » : on n'envoie rien au démon. Le garde est
    // aussi présent côté démon, mais l'appliquer ici évite le trajet inutile et
    // couvre les appels manuels (bouton Rafraîchir, scénarios).
    $suspension = self::ipSuspensionRemaining();
    if ($suspension > 0) {
      log::add(__CLASS__, 'info', 'Mise à jour ignorée pour ' . $this->getHumanName()
        . ' (contexte: ' . $command . ') : adresse IP suspendue par Pronote, reprise à '
        . date('H:i', time() + $suspension) . '.');
      return;
    }

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
      'TokenUsername' => $this->getConfiguration('Token_username'),
      'TokenPassword' => $this->getConfiguration('Token_password'),
      'TokenUrl'    => html_entity_decode($this->getConfiguration('Token_pronote_url', '')),
      'TokenUuid'   => $this->getConfiguration('uuid', 'ProJote'),
      // Nombre de jours couverts par la liste des devoirs (7 par défaut).
      'DevoirsJours' => $this->getConfiguration('devoirs_jours', 7),
      // Onglets que l'utilisateur ne suit pas : le démon ne les interroge pas.
      'OngletsDesactives' => $this->ongletsDesactives(),
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
   * Surcharge cmd::save() pour ignorer silencieusement les commandes orphelines.
   *
   * Contexte : un bug JS historique (affectation `let _cmd = {}` à portée de bloc dans
   * addCmdToTable) créait des entrées vides en base (name/logicalId vides, order=59).
   * Le core Jeedom lève "Le nom de la commande ne peut pas être vide" au moment de les
   * sauvegarder. Cette surcharge les supprime proprement si elles ont déjà un id en base,
   * ou les ignore si elles sont purement en mémoire.
   *
   * Note : la signature $_direct = false est obligatoire (PHP 8.x E_COMPILE_ERROR sinon).
   *
   * @param bool $_direct Passage direct (sans cycle pre/postSave) — relayé au parent.
   */
  public function save($_direct = false)
  {
    if (empty(trim((string)$this->getName())) || empty(trim((string)$this->getLogicalId()))) {
      if (!empty($this->getId())) {
        log::add('ProJote', 'warning', 'save() : suppression commande orpheline id=' . $this->getId() . ' order=' . $this->getOrder());
        parent::remove();
      }
      return;
    }
    parent::save($_direct);
  }

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
