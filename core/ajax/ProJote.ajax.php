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
  ajax::init(['Validate', 'ValidateQRCode', 'ChangeEnfant', 'GetConfig', 'GetWidgetData', 'UploadManualPhoto', 'DeleteManualPhoto']);

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
      log::add('ProJote', 'error', 'Ajax::Login - Impossible de trouver le dossier des ressources du plugin.');
      ajax::error('Impossible de trouver le dossier des ressources du plugin.');
      return;
    }
    // Chemin vers l'exécutable python dans l'environnement virtuel du plugin
    $pythonBinary = $resourcePath . DIRECTORY_SEPARATOR . 'python_venv' . DIRECTORY_SEPARATOR . 'bin' . DIRECTORY_SEPARATOR . 'python3';
    // Chemin vers le script Python qui gère la connexion par identifiants
    $loginScript = $resourcePath . DIRECTORY_SEPARATOR . 'ProJoted' . DIRECTORY_SEPARATOR . 'LoginConnect.py';

    // Vérification que les fichiers existent avant de continuer
    if (!file_exists($pythonBinary)) {
      $msg = 'Dépendances Python non installées. Allez dans la configuration du plugin et cliquez sur "Installer les dépendances".';
      log::add('ProJote', 'error', 'Ajax::Login - Exécutable Python non trouvé : ' . $pythonBinary);
      ajax::error($msg);
      return;
    }
    if (!file_exists($loginScript)) {
      log::add('ProJote', 'error', 'Ajax::Login - Script LoginConnect.py non trouvé : ' . $loginScript);
      ajax::error('Script LoginConnect.py introuvable. Vérifiez l\'installation du plugin.');
      return;
    }

    // Récupération de l'UUID pour l'identification auprès de Pronote (nécessaire pour certains ENT)
    $eqLogicForUuid = eqLogic::byId($eqLogicId);
    $uuid = (is_object($eqLogicForUuid)) ? $eqLogicForUuid->getConfiguration('uuid', uniqid('projote-', true)) : uniqid('projote-', true);

    // Chiffrement du mot de passe pour le transport sécurisé vers Python
    $proJote = new ProJote();
    $encryptedPassword = $proJote->my_encrypt($password);

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
    $command .= ' --Password ' . escapeshellarg($encryptedPassword);
    if ($ent != null) {
      $command .= ' --Ent ' . escapeshellarg($ent);
    }
    if ($nomenfant != null) {
      $command .= ' --Enfant ' . escapeshellarg($nomenfant);
    }
    $command .= ' --Eqid ' . escapeshellarg($eqLogicId);
    $command .= ' --Uuid ' . escapeshellarg($uuid);
    $command .= ' --apikey ' . escapeshellarg(jeedom::getApiKey('ProJote'));
    $command .= ' --Loglevel ' . (log::convertLogLevel(log::getLogLevel("ProJote")));
    $command .= ' --datadir ' . escapeshellarg(dirname(dirname(dirname(__FILE__))) . '/data');
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
      log::add('ProJote', 'error', 'Ajax::QR - Impossible de déterminer le chemin des ressources');
      ajax::error('Impossible de déterminer le chemin des ressources du plugin.');
      return;
    }
    $pythonBinary = $resourcePath . DIRECTORY_SEPARATOR . 'python_venv' . DIRECTORY_SEPARATOR . 'bin' . DIRECTORY_SEPARATOR . 'python3';
    $qrScript = $resourcePath . DIRECTORY_SEPARATOR . 'ProJoted' . DIRECTORY_SEPARATOR . 'QRConnect.py';

    if (!file_exists($pythonBinary)) {
      $msg = 'Dépendances Python non installées. Allez dans la configuration du plugin et cliquez sur "Installer les dépendances".';
      log::add('ProJote', 'error', 'Ajax::QR - Exécutable Python non trouvé : ' . $pythonBinary);
      ajax::error($msg);
      return;
    }
    if (!file_exists($qrScript)) {
      log::add('ProJote', 'error', 'Ajax::QR - Script QRConnect.py non trouvé : ' . $qrScript);
      ajax::error('Script QRConnect.py introuvable. Vérifiez l\'installation du plugin.');
      return;
    }

    $eqLogicForUuid = eqLogic::byId($eqLogicId);
    $uuid = (is_object($eqLogicForUuid)) ? $eqLogicForUuid->getConfiguration('uuid', uniqid('projote-', true)) : uniqid('projote-', true);

    // Construction de la commande shell avec les arguments spécifiques au QR Code
    $command = escapeshellarg($pythonBinary) . ' ' . escapeshellarg($qrScript);
    $command .= ' --Jeton ' . escapeshellarg($jeton);
    $command .= ' --QRLogin ' . escapeshellarg($login);
    $command .= ' --QRUrl ' . escapeshellarg($url);
    $command .= ' --Pin ' . escapeshellarg($pin);
    $command .= ' --Eqid ' . escapeshellarg($eqLogicId);
    $command .= ' --Uuid ' . escapeshellarg($uuid);
    $command .= ' --apikey ' . escapeshellarg(jeedom::getApiKey('ProJote'));
    $command .= ' --Loglevel ' . escapeshellarg(log::convertLogLevel(log::getLogLevel("ProJote")));
    $command .= ' --datadir ' . escapeshellarg(dirname(dirname(dirname(__FILE__))) . '/data');
    $command .= ' >> ' . log::getPathToLog('ProJote') . ' 2>&1 ';

    // Ne pas logger la commande complète (contient le jeton QR en clair)
    log::add('ProJote', 'debug', 'Ajax::Commande de validation QR Code lancée pour eqLogic ' . $eqLogicId);

    // Exécution de la commande
    exec($command, $output, $return_var);

    log::add('ProJote', 'debug', 'Ajax::QR - Code retour exec : ' . $return_var . (count($output) ? ' | Output : ' . implode(' | ', $output) : ''));

    // Analyse du résultat (idem que pour la validation classique)
    if ($return_var === 0) {
      $eqLogic = eqLogic::byId($eqLogicId);
      log::add('ProJote', 'debug', 'Ajax:: eqLogicId = ' . $eqLogicId);

      // Lecture des informations du compte après connexion réussie
      $data = $eqLogic->ReadEnfantToken();

      // Envoi des données au frontend
      ajax::success($data); // Note: L'ancien code envoyait $output, mais $data est plus correct et cohérent.
    } elseif ($return_var === 3) {
      // Code 3 = QR code expiré ou illisible (cf. QRConnect.py). C'est le cas le
      // plus fréquent : le QR code Pronote n'est valide que 10 minutes.
      ajax::error('Le QR code a expiré (il n\'est valide que 10 minutes). Générez-en un nouveau dans l\'application Pronote et scannez-le immédiatement.');
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
    // ──────────────────────────────────────────────────────────────────────────
    // ACTION : UploadManualPhoto — Enregistre une photo de profil manuelle
    //
    // Utilisée quand Pronote ne fournit pas de photo. L'image est stockée dans
    // data/{eqLogicId}/profile_picture_manual.jpg et sert de fallback dans le widget.
    // ──────────────────────────────────────────────────────────────────────────
  } elseif ($action == 'UploadManualPhoto') {

    $eqLogicId = intval(init('eqlogic'));
    $eqLogic = eqLogic::byId($eqLogicId);
    if (!is_object($eqLogic)) {
      ajax::error('Équipement non trouvé.');
      return;
    }

    if (!isset($_FILES['photo']) || $_FILES['photo']['error'] !== UPLOAD_ERR_OK) {
      ajax::error('Fichier non reçu ou erreur d\'upload (code ' . ($_FILES['photo']['error'] ?? -1) . ').');
      return;
    }

    $file = $_FILES['photo'];

    // Limite à 5 Mo
    if ($file['size'] > 5 * 1024 * 1024) {
      ajax::error('Fichier trop volumineux (max 5 Mo).');
      return;
    }

    // Validation MIME via contenu (pas l'extension déclarée par le client)
    $finfo = new finfo(FILEINFO_MIME_TYPE);
    $mimeType = $finfo->file($file['tmp_name']);
    $allowedMimes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    if (!in_array($mimeType, $allowedMimes, true)) {
      ajax::error('Format non supporté. Utilisez JPEG, PNG, WebP ou GIF.');
      return;
    }

    $dataDir = realpath(dirname(__FILE__) . '/../../data') . DIRECTORY_SEPARATOR . $eqLogicId;
    if (!is_dir($dataDir)) {
      mkdir($dataDir, 0755, true);
    }
    $destPath = $dataDir . DIRECTORY_SEPARATOR . 'profile_picture_manual.jpg';

    if (!move_uploaded_file($file['tmp_name'], $destPath)) {
      ajax::error('Impossible d\'enregistrer le fichier.');
      return;
    }

    log::add('ProJote', 'info', 'Photo manuelle enregistrée pour eqLogic ' . $eqLogicId);
    ajax::success('/plugins/ProJote/data/' . $eqLogicId . '/profile_picture_manual.jpg');

    // ──────────────────────────────────────────────────────────────────────────
    // ACTION : DeleteManualPhoto — Supprime la photo de profil manuelle
    // ──────────────────────────────────────────────────────────────────────────
  } elseif ($action == 'DeleteManualPhoto') {

    $eqLogicId = intval(init('eqlogic'));
    $eqLogic = eqLogic::byId($eqLogicId);
    if (!is_object($eqLogic)) {
      ajax::error('Équipement non trouvé.');
      return;
    }

    $filePath = realpath(dirname(__FILE__) . '/../../data') . DIRECTORY_SEPARATOR . $eqLogicId . DIRECTORY_SEPARATOR . 'profile_picture_manual.jpg';
    if (file_exists($filePath)) {
      unlink($filePath);
      log::add('ProJote', 'info', 'Photo manuelle supprimée pour eqLogic ' . $eqLogicId);
    }
    ajax::success(true);
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
