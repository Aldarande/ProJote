<?php

/**
 * ProJote.ajax.php — Gestionnaire des requêtes AJAX de l'interface de configuration.
 *
 * Ce fichier est le "cerveau" côté serveur pour la page de configuration du plugin ProJote dans Jeedom.
 * Il agit comme un pont entre les actions de l'utilisateur sur l'interface web (en JavaScript)
 * et les scripts Python qui communiquent avec les serveurs Pronote.
 *
 * Quand vous cliquez sur un bouton dans la page de configuration (ex: "Valider", "Tester"),
 * votre navigateur envoie une requête AJAX à ce fichier. Ce fichier analyse la requête,
 * exécute l'action demandée (souvent en lançant un script Python), puis renvoie une réponse.
 *
 * @package ProJote
 * @since 1.0.0
 * @author Aldarande
 */

/*
 * Note sur le contexte Jeedom :
 * Ce fichier s'exécute dans l'environnement Jeedom. Il a donc accès à toutes les classes
 * et fonctions de l'API Jeedom, comme:
 * - require_once, include_file : pour charger les fichiers nécessaires.
 * - isConnect('admin') : pour vérifier les droits de l'utilisateur.
 * - ajax::init(), ajax::success(), ajax::error() : pour gérer la communication AJAX.
 * - eqLogic::byId() : pour manipuler les équipements Jeedom.
 * - log::add() : pour écrire dans les fichiers de log.
 * - init() : pour récupérer les paramètres envoyés par la requête AJAX.
 */

//
// ═════════════════════════════════════════════════════════════════════════════
// INITIALISATION ET SÉCURITÉ
// ═════════════════════════════════════════════════════════════════════════════
//
try {
  // 1. CHARGEMENT DES DÉPENDANCES
  // Il faut inclure les fichiers essentiels de Jeedom et du plugin pour que le code fonctionne.
  // core.inc.php est le cœur de Jeedom.
  require_once dirname(__FILE__) . '/../../../../core/php/core.inc.php';
  // authentification.php gère la sécurité et la connexion.
  include_file('core', 'authentification', 'php');
  // ProJote.class.php contient la classe principale du plugin, avec des fonctions utiles.
  require_once dirname(__FILE__) . '/../class/ProJote.class.php';

  // 2. VÉRIFICATION DES DROITS
  // On s'assure que seul un administrateur Jeedom peut exécuter ce code.
  // C'est une mesure de sécurité cruciale pour éviter des actions non autorisées.
  if (!isConnect('admin')) {
    throw new Exception(__('401 - Accès non autorisé', __FILE__));
  }

  // 3. INITIALISATION DE LA RÉPONSE AJAX
  // Prépare Jeedom à renvoyer une réponse au format JSON pour le JavaScript.
  ajax::init(['Validate', 'ValidateQRCode', 'ChangeEnfant', 'GetConfig', 'GetWidgetData']);

  // 4. RÉCUPÉRATION DE L'ACTION DEMANDÉE
  // Le JavaScript envoie un paramètre "action" qui nous dit quoi faire.
  // Ex: 'Validate', 'GetConfig', etc.
  $action = init('action');

  //
  // ═════════════════════════════════════════════════════════════════════════════
  // GESTIONNAIRE D'ACTIONS (l'"aiguillage")
  // ═════════════════════════════════════════════════════════════════════════════
  //
  // Le code ci-dessous utilise une structure if/elseif pour exécuter le bloc
  // correspondant à l'action demandée.
  //

  // ──────────────────────────────────────────────────────────────────────────
  // ACTION : Validate — Connexion via login / mot de passe
  //
  // Appelée quand l'utilisateur clique "Valider" après avoir saisi ses
  // identifiants Pronote (URL, ENT, login, mot de passe).
  // Le but est de lancer un script Python qui va se connecter à Pronote,
  // récupérer des "tokens" de session, et les sauvegarder pour une utilisation future.
  // ──────────────────────────────────────────────────────────────────────────
  if ($action == "Validate") {

    // Récupération des données envoyées par le formulaire (via la requête AJAX)
    $password = init('password');
    $login = init('login');
    $url = init('url');
    $ent = init('ent'); // Espace Numérique de Travail, ex: "cas_agora06" (optionnel)
    $nomenfant = init('nomeleve'); // Le nom de l'enfant si spécifié (optionnel)
    $eqLogicId = init('eqlogic'); // L'ID de l'équipement Jeedom concerné

    log::add('ProJote', 'debug', 'Ajax::Début de la validation des identifiants pour eqLogic ' . $eqLogicId);

    // Étape 1 : Construire le chemin vers l'interpréteur Python et le script à exécuter.
    // On utilise des chemins relatifs pour que cela fonctionne sur toutes les installations.
    $resourcePath = realpath(dirname(__FILE__) . '/../../resources');
    if (!$resourcePath) {
      throw new Exception('Impossible de trouver le dossier des ressources du plugin.');
    }
    // Chemin vers l'exécutable python dans l'environnement virtuel du plugin
    $pythonBinary = $resourcePath . DIRECTORY_SEPARATOR . 'python_venv' . DIRECTORY_SEPARATOR . 'bin' . DIRECTORY_SEPARATOR . 'python3';
    // Chemin vers le script Python qui gère la connexion par identifiants
    $loginScript = $resourcePath . DIRECTORY_SEPARATOR . 'ProJoted' . DIRECTORY_SEPARATOR . 'LoginConnect.py';

    // Vérification que les fichiers existent avant de continuer
    if (!file_exists($pythonBinary)) {
      throw new Exception('Exécutable Python non trouvé à : ' . $pythonBinary);
    }
    if (!file_exists($loginScript)) {
      throw new Exception('Script LoginConnect.py non trouvé à : ' . $loginScript);
    }

    // Récupération de l'UUID pour l'identification auprès de Pronote (nécessaire pour certains ENT)
    $eqLogicForUuid = eqLogic::byId($eqLogicId);
    $uuid = (is_object($eqLogicForUuid)) ? $eqLogicForUuid->getConfiguration('uuid', jeedom::createUniqueId()) : jeedom::createUniqueId();

    // Étape 2 : Construire la commande shell à exécuter.
    // C'est ici que l'on assemble la commande qui sera lancée, comme si on la tapait dans un terminal.
    // Ex: /usr/bin/python3 /chemin/vers/script.py --URL "http://pronote.ecole.fr" ...

    // On commence par le binaire python et le script
    $command = escapeshellarg($pythonBinary) . ' ' . escapeshellarg($loginScript);

    // On ajoute chaque paramètre l'un après l'autre.
    // escapeshellarg() est TRÈS important : il sécurise les arguments pour éviter
    // des injections de commandes malveillantes.
    $command .= ' --URL ' . escapeshellarg($url);
    $command .= ' --Login ' . escapeshellarg($login);
    $command .= ' --Password ' . escapeshellarg($password);
    if ($ent != null) {
      $command .= ' --Ent ' . escapeshellarg($ent);
    }
    if ($nomenfant != null) {
      $command .= ' --Enfant ' . escapeshellarg($nomenfant);
    }
    $command .= ' --Eqid ' . escapeshellarg($eqLogicId);
    $command .= ' --Uuid ' . escapeshellarg($uuid);
    $command .= ' --Loglevel ' . (log::convertLogLevel(log::getLogLevel("ProJote")));
    $command .= ' --datadir ' . escapeshellarg(dirname(dirname(__FILE__)) . '/data');
    $command .= ' >> ' . log::getPathToLog('ProJote') . ' 2>&1 ';

    // Ne pas logger la commande complète (contient le mot de passe en clair)
    log::add('ProJote', 'debug', 'Ajax::Commande de validation lancée pour eqLogic ' . $eqLogicId);

    // Étape 3 : Exécuter la commande et récupérer le résultat.
    exec($command, $output, $return_var);

    log::add('ProJote', 'debug', 'Ajax::Retour de la commande de validation. Code: ' . $return_var);

    // Étape 4 : Analyser le résultat.
    // Un code de retour ($return_var) de 0 signifie que le script s'est terminé sans erreur.
    if ($return_var === 0) {
      // Le script a réussi. Il a normalement créé un fichier contenant les infos du compte.
      // On charge l'équipement pour pouvoir lire ce fichier.
      $eqLogic = eqLogic::byId($eqLogicId);

      // Cette fonction va lire le fichier "enfant.ProJote.json.txt", le décoder,
      // et retourner les informations (nom de l'élève, classe, liste des enfants, etc.).
      $data = $eqLogic->ReadEnfantToken();

      // On renvoie ces données au JavaScript (frontend) qui va les utiliser pour
      // mettre à jour l'affichage de la page de configuration.
      ajax::success($data);
    } else {
      // Le script a échoué. On renvoie un message d'erreur au JavaScript.
      // L'utilisateur verra une notification d'erreur.
      // Les détails de l'erreur se trouvent dans les logs grâce à la redirection faite plus haut.
      ajax::error('Erreur lors de l\'exécution de la commande Python : ' . implode("\n", $output));
    }


    // ──────────────────────────────────────────────────────────────────────────
    // ACTION : ValidateQRCode — Connexion via QR code scanné + PIN
    //
    // Appelée quand l'utilisateur a scanné le QR code avec l'app Pronote
    // et a saisi son code PIN à 4 chiffres.
    // Le JavaScript a déjà décodé l'image QR et envoie les informations ici.
    // ──────────────────────────────────────────────────────────────────────────
  } elseif ($action == "ValidateQRCode") {

    log::add('ProJote', 'debug', 'Ajax::Début de la validation du QR Code.');

    // Récupération des données envoyées par la requête AJAX
    $dataJson = init('QRinfo'); // Contient les infos du QR Code en format JSON (chaîne de caractères)
    $pin = init('pin');         // Le code PIN à 4 chiffres
    $eqLogicId = init('eqlogic'); // L'ID de l'équipement

    // Le JSON est reçu comme une chaîne de caractères, il faut le "parser" (décoder)
    // pour le transformer en objet ou tableau PHP.
    $data = json_decode($dataJson, true);
    if ($data === null) {
      // Si le JSON est mal formé, on s'arrête ici.
      ajax::error('Données JSON du QR Code invalides.');
      return;
    }
    // Extraction des informations du QR Code
    $jeton = $data['jeton'];
    $login = $data['login'];
    $url = $data['url'];

    log::add('ProJote', 'debug', 'Ajax::Infos QR Code reçues pour eqid : ' . $eqLogicId);

    // Le reste du processus est très similaire à la validation par login/mot de passe,
    // mais en utilisant un script Python différent : QRConnect.py

    $resourcePath = realpath(dirname(__FILE__) . '/../../resources');
    if (!$resourcePath) {
      throw new Exception('Impossible de déterminer le chemin des ressources');
    }
    $pythonBinary = $resourcePath . DIRECTORY_SEPARATOR . 'python_venv' . DIRECTORY_SEPARATOR . 'bin' . DIRECTORY_SEPARATOR . 'python3';
    $qrScript = $resourcePath . DIRECTORY_SEPARATOR . 'ProJoted' . DIRECTORY_SEPARATOR . 'QRConnect.py';

    if (!file_exists($pythonBinary)) {
      throw new Exception('Exécutable Python non trouvé à : ' . $pythonBinary);
    }
    if (!file_exists($qrScript)) {
      throw new Exception('Script QRConnect.py non trouvé à : ' . $qrScript);
    }

    $eqLogicForUuid = eqLogic::byId($eqLogicId);
    $uuid = (is_object($eqLogicForUuid)) ? $eqLogicForUuid->getConfiguration('uuid', jeedom::createUniqueId()) : jeedom::createUniqueId();

    // Construction de la commande shell avec les arguments spécifiques au QR Code
    $command = escapeshellarg($pythonBinary) . ' ' . escapeshellarg($qrScript);
    $command .= ' --Jeton ' . escapeshellarg($jeton);
    $command .= ' --QRLogin ' . escapeshellarg($login);
    $command .= ' --QRUrl ' . escapeshellarg($url);
    $command .= ' --Pin ' . escapeshellarg($pin);
    $command .= ' --Eqid ' . escapeshellarg($eqLogicId);
    $command .= ' --Uuid ' . escapeshellarg($uuid);
    $command .= ' --Loglevel ' . escapeshellarg(log::convertLogLevel(log::getLogLevel("ProJote")));
    $command .= ' --datadir ' . escapeshellarg(dirname(dirname(__FILE__)) . '/data');
    $command .= ' >> ' . log::getPathToLog('ProJote') . ' 2>&1 ';

    // Ne pas logger la commande complète (contient le jeton QR en clair)
    log::add('ProJote', 'debug', 'Ajax::Commande de validation QR Code lancée pour eqLogic ' . $eqLogicId);

    // Exécution de la commande
    exec($command, $output, $return_var);

    // Analyse du résultat (idem que pour la validation classique)
    if ($return_var === 0) {
      $eqLogic = eqLogic::byId($eqLogicId);
      log::add('ProJote', 'debug', 'Ajax:: eqLogicId = ' . $eqLogicId);

      // Lecture des informations du compte après connexion réussie
      $data = $eqLogic->ReadEnfantToken();

      // Envoi des données au frontend
      ajax::success($data); // Note: L'ancien code envoyait $output, mais $data est plus correct et cohérent.
    } else {
      ajax::error('Erreur lors de l\'exécution du script Python. Vérifiez les logs pour plus de détails.');
    }


    // ──────────────────────────────────────────────────────────────────────────
    // ACTION : ChangeEnfant — Changer l'enfant actif pour un compte parent
    //
    // Un compte Pronote de type "Parent" peut être lié à plusieurs enfants.
    // Cette action est appelée quand l'utilisateur sélectionne un autre enfant
    // dans la liste déroulante de la configuration.
    // ──────────────────────────────────────────────────────────────────────────
  } elseif ($action == "ChangeEnfant") {

    log::add('ProJote', 'debug', "Ajax::Requête de changement d'enfant.");

    // Récupération du nom de l'enfant choisi et de l'ID de l'équipement
    $nomenfant = init('nomeleve');
    $eqLogicId = init('eqlogic');

    // On charge l'objet équipement correspondant
    $eqLogic = eqLogic::byId($eqLogicId);
    if (!is_object($eqLogic)) {
      ajax::error('Equipement non trouvé pour l\'ID: ' . $eqLogicId);
      return;
    }
    log::add('ProJote', 'debug', 'Ajax::Changement vers l\'enfant "' . $nomenfant . '" pour eqid : ' . $eqLogicId);

    // Étape 1 : Mettre à jour la configuration de l'équipement.
    // On sauvegarde le nom de l'enfant qui est maintenant l'enfant "actif".
    $eqLogic->setConfiguration('enfant', $nomenfant);
    $eqLogic->save(); // Ne pas oublier de sauvegarder les changements !

    // Étape 2 : Déclencher une mise à jour des données.
    // Maintenant que l'enfant actif a changé, on demande au démon Python de
    // récupérer immédiatement les nouvelles informations (notes, emploi du temps, etc.)
    // pour cet enfant.
    $eqLogic->UpdateInfoPronote('ChangeEnfant');

    // On informe le frontend que l'opération a réussi.
    ajax::success(true);


    // ──────────────────────────────────────────────────────────────────────────
    // ACTION : GetConfig — Retourne la configuration actuelle de l'équipement
    //
    // Appelée au chargement de la page de configuration.
    // Permet de pré-remplir les champs avec les valeurs déjà sauvegardées pour
    // cet équipement (nom de l'élève, classe, établissement, liste des enfants, etc.).
    // ──────────────────────────────────────────────────────────────────────────
  // ──────────────────────────────────────────────────────────────────────────
  // ACTION : GetWidgetData — Retourne les données du widget pour le rafraîchissement JS
  //
  // Appelée par le JavaScript du widget (dans ProJote.html) quand la commande
  // LastLogin se met à jour. Retourne le JSON 'widget_json' stocké en configuration,
  // ce qui permet au widget de se mettre à jour sans recharger la page.
  // ──────────────────────────────────────────────────────────────────────────
  } elseif ($action == "GetWidgetData") {

    $eqLogicId = init('eqlogic');
    $eqLogic = eqLogic::byId($eqLogicId);
    if (!is_object($eqLogic)) {
      ajax::error('Equipement non trouvé pour l\'ID: ' . $eqLogicId);
      return;
    }

    // Lire les données du widget depuis la configuration de l'équipement.
    // Ces données sont mises à jour par jeeProJote.php à chaque callback du démon.
    $widgetJson = $eqLogic->getConfiguration('widget_json', '{}');
    $widgetData = json_decode($widgetJson, true);
    ajax::success(is_array($widgetData) ? $widgetData : []);

  } elseif ($action == "GetConfig") {

    $eqLogicId = init('eqlogic');
    $eqLogic = eqLogic::byId($eqLogicId);
    if (!is_object($eqLogic)) {
      ajax::error('Equipement non trouvé pour l\'ID: ' . $eqLogicId);
      return;
    }

    // On construit un tableau associatif avec les clés et les valeurs de configuration
    // que le JavaScript a besoin de connaître.
    $configData = array(
      'Eleve'            => $eqLogic->getConfiguration('Eleve', ''), // Nom de l'élève
      'Classe'           => $eqLogic->getConfiguration('Classe', ''), // Sa classe
      'Etablissement'    => $eqLogic->getConfiguration('Etablissement', ''), // Son établissement
      'Ical'             => $eqLogic->getConfiguration('Ical', ''), // URL du calendrier iCal
      'Liste_Enfant'     => $eqLogic->getConfiguration('Liste_Enfant', '[]'), // Liste des enfants (JSON)
      'Token_pronote_url' => $eqLogic->getConfiguration('Token_pronote_url', ''), // URL de connexion sauvegardée
    );

    // On renvoie ce tableau au format JSON au frontend.
    ajax::success($configData);
  } else {
    // Si le paramètre 'action' ne correspond à aucune des conditions ci-dessus,
    // c'est une erreur : le JavaScript a demandé une action inconnue.
    throw new Exception(__('Action non supportée :', __FILE__) . ' ' . init('action'));
  }

  //
  // ═════════════════════════════════════════════════════════════════════════════
  // GESTION CENTRALE DES ERREURS
  // ═════════════════════════════════════════════════════════════════════════════
  //
} catch (Exception $e) {
  // Le bloc "try...catch" permet d'attraper toutes les erreurs (Exceptions) qui pourraient
  // survenir dans le code ci-dessus.
  // Au lieu de faire planter le script, l'erreur est "attrapée" ici.
  // On la formate de manière propre et on la renvoie au JavaScript.
  // L'utilisateur verra un message d'erreur clair dans Jeedom.
  ajax::error(displayException($e), $e->getCode());
}
