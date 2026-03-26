<?php
// Fichier ProJoteInterface.php
// Interface dédiée pour afficher les informations Pronote dans Jeedom

// Inclure les fichiers nécessaires
require_once dirname(__FILE__) . '/../../../../core/php/core.inc.php';
require_once dirname(__FILE__) . '/../../../ProJote/core/class/ProJote.class.php';

// Vérifier l'authentification
if (!isConnect()) {
    throw new Exception(__('401 - Accès non autorisé', __FILE__));
}

// Récupérer l'ID de l'équipement depuis les paramètres GET
$eqLogicId = init('id');

// Vérifier si l'ID de l'équipement est valide
if (!$eqLogicId) {
    throw new Exception(__('ID de l'équipement non spécifié', __FILE__));
}

// Récupérer les données de l'équipement
$eqLogic = eqLogic::byId($eqLogicId);
if (!is_object($eqLogic)) {
    throw new Exception(__('Équipement non trouvé', __FILE__));
}

// Récupérer les données Pronote
$proJote = new ProJote();
$pronoteData = $proJote->getPronoteData($eqLogicId);

// Inclure le template de l'interface
include_file('desktop', 'ProJoteInterface', 'php', 'ProJote');

// Afficher les données Pronote
if ($pronoteData) {
    echo json_encode($pronoteData);
} else {
    echo json_encode(['error' => __('Aucune donnée Pronote trouvée', __FILE__)]);
}
?>