<?php
try {
    require_once dirname(__FILE__) . "/../../../../core/php/core.inc.php";

    if (!jeedom::apiAccess(init('apikey'), 'ProJote')) {
        echo __('Vous n\'etes pas autorisé à effectuer cette action', __FILE__);
        die();
    }

    if (init('test') != '') {
        echo 'OK';
        die();
    }

    $result = json_decode(file_get_contents("php://input"), true);

    if (log::convertLogLevel(log::getLogLevel('ProJote')) == "debug") {
        $result_json = json_encode($result, JSON_PRETTY_PRINT);
        log::add('ProJote', 'debug', 'Résultat reçu : ' . $result_json);
    }
    // Vérifie si le résultat est un tableau 
    if (!is_array($result)) {
        die();
    }

    // Récupère l'eqLogic à l'origine de la demande
    log::add('ProJote', 'info', 'EqLogic : ' . print_r($result['CmdId'], true));
    $eqLogic = eqLogic::byId($result['CmdId']);

    // Vérifie si des informations d'élève sont présentes
    if (is_array($result["eleve"][0])) {
        // Parcourt toutes les clés possibles
        foreach ($result["eleve"][0] as $key => $value) {
            // Vérifie si la clé existe et met à jour la commande correspondante
            if (isset($value) && $eqLogic->getCmd(null, $key)) {
                log::add('ProJote', 'debug', 'Champ reçu : ' . $key . ' - Valeur reçue : ' . print_r($value, true));
                $eqLogic->checkAndUpdateCmd($key, $value);
            }
        }
    }

    //Mise à jour du nom de l'élève
    if (isset($result['eleve']['Nom_Eleve']) && $eqLogic->getCmd(null, 'Nom_Eleve')) {
        $eqLogic->checkAndUpdateCmd('Nom_Eleve', $result['eleve']['Nom_Eleve']);
    }
    //Mise à jour du nom de la classe
    if (isset($result['eleve']['Nom_Classe']) && $eqLogic->getCmd(null, 'Nom_Classe')) {
        $eqLogic->checkAndUpdateCmd('Nom_Classe', $result['eleve']['Nom_Classe']);
    }
    //Mise à jour du nom de l'etablissement'
    if (isset($result['eleve']['Etablissement']) && $eqLogic->getCmd(null, 'Etablissement')) {
        $eqLogic->checkAndUpdateCmd('Etablissement', $result['eleve']['Etablissement']);
    }

    // saisie unitaire des valeurs
    // Met à jour la photo de l'élève si elle est présente
    if (isset($result['Photo']) && $eqLogic->getCmd(null, 'Picture')) {
        $eqLogic->checkAndUpdateCmd('Picture', $result['Photo']);
    }
    // Met à jour le nombre d'absence
    if (isset($result['Absences']['nb_absences']) && $eqLogic->getCmd(null, 'Nb_absences')) {
        $eqLogic->checkAndUpdateCmd('Nb_absences', $result['Absences']['nb_absences']);
    }
    // Met à jour le nombre de Punissions
    if (isset($result['Punissions']['Nb_Punissions']) && $eqLogic->getCmd(null, 'Nb_punission')) {
        $eqLogic->checkAndUpdateCmd('Nb_punission', $result['Punissions']['Nb_Punissions']);
    }
    // Met à jour le lien Ical
    if (isset($result['Ical']) && $eqLogic->getCmd(null, 'URL_Ical')) {
        $eqLogic->checkAndUpdateCmd('URL_Ical', $result['Ical']);
    } else {
        $resultIcal = "Pas d'URL retournée";
        $eqLogic->checkAndUpdateCmd('URL_Ical', "Pas d'URL retournée");
    }


    // saisie globale des valeurs
    // Vérifie les entrés de Emploi du temps
    if (is_array($result["emploi_du_temps"])) {
        // Parcourt toutes les clés possibles
        foreach ($result["emploi_du_temps"] as $key => $value) {
            // Vérifie si la clé existe et met à jour la commande correspondante
            if (isset($value) && $eqLogic->getCmd(null, $key)) {
                log::add('ProJote', 'debug', 'Champ reçu : ' . $key . ' - Valeur reçue : ' . print_r($value, true));
                $eqLogic->checkAndUpdateCmd($key, $value);
            }
        }
    }

    // Vérifie les entrés des Notes
    if (is_array($result["notes"])) {
        // Parcourt toutes les clés possibles
        foreach ($result["notes"] as $key => $value) {
            // Vérifie si la clé existe et met à jour la commande correspondante
            if (isset($value) && $eqLogic->getCmd(null, $key)) {
                log::add('ProJote', 'debug', 'Champ reçu : ' . $key . ' - Valeur reçue : ' . print_r($value, true));
                $eqLogic->checkAndUpdateCmd($key, $value);
            }
        }
    }

    // Vérifie les entrés de devoir
    if (is_array($result["devoirs"])) {
        // Parcourt toutes les clés possibles
        foreach ($result["devoirs"] as $key => $value) {
            // Vérifie si la clé existe et met à jour la commande correspondante
            if (isset($value) && $eqLogic->getCmd(null, $key)) {
                log::add('ProJote', 'debug', 'Champ reçu : ' . $key . ' - Valeur reçue : ' . print_r($value, true));
                $eqLogic->checkAndUpdateCmd($key, $value);
            }
        }
    }

    // Vérifie les entrés des Menus
    if (is_array($result["Menus"])) {
        // Parcourt toutes les clés possibles
        foreach ($result["Menus"] as $key => $value) {
            // Vérifie si la clé existe et met à jour la commande correspondante
            if (isset($value) && $eqLogic->getCmd(null, $key)) {
                log::add('ProJote', 'debug', 'Champ reçu : ' . $key . ' - Valeur reçue : ' . print_r($value, true));
                $eqLogic->checkAndUpdateCmd($key, $value);
            }
        }
    } else {
        log::add('ProJote', 'debug', 'Menus non reçu');
    }

    // Vérifie les entrés des Notifications
    if (is_array($result["Notifications"])) {
        // Parcourt toutes les clés possibles
        foreach ($result["Notifications"] as $key => $value) {
            // Vérifie si la clé existe et met à jour la commande correspondante
            if (isset($value) && $eqLogic->getCmd(null, $key)) {
                log::add('ProJote', 'debug', 'Champ reçu : ' . $key . ' - Valeur reçue : ' . print_r($value, true));
                $eqLogic->checkAndUpdateCmd($key, $value);
            }
        }
    } else {
        log::add('ProJote', 'debug', 'Notifications non reçu');
    }

    if (is_array($result["Token"])) {
        // Correspondance des clés JSON avec les commandes Jeedom
        $cmdMapping = [
            'pronote_url' => 'TokenUrl',
            'username' => 'Username',
            'password' => 'Token',
            'client_identifier' => 'TokenId'
        ];
        // Parcourt toutes les clés possibles
        foreach ($cmdMapping as $jsonKey => $cmdName) {
            // Vérifie si la clé existe et met à jour la commande correspondante
            if (isset($result["Token"][$jsonKey]) && $eqLogic->getCmd(null, $cmdName)) {
                $value = $result["Token"][$jsonKey];
                log::add('ProJote', 'debug', 'Champ reçu : ' . $cmdName . ' - Valeur reçue : ' . print_r($value, true));
                $eqLogic->checkAndUpdateCmd($cmdName, $value);
            }
        }
    } else {
        log::add('ProJote', 'debug', 'Token non reçu');
    }
} catch (Exception $e) {
    log::add('ProJote', 'error', displayException($e));
}
