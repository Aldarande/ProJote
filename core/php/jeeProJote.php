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

    if (!is_object($eqLogic)) {
        log::add('ProJote', 'error', 'EqLogic non trouvé pour CmdId : ' . $result['CmdId']);
        die();
    }
    log::add('ProJote', 'debug', 'EqLogic trouvé : ' . $eqLogic->getHumanName());
    // Vérifie si l'EqLogic est actif
    if (!$eqLogic->getIsEnable()) {
        log::add('ProJote', 'error', 'EqLogic désactivé : ' . $eqLogic->getHumanName());
        die();
    }
    //Je met à jours la date de dernière communication
    //Mise à jour du nom de l'élève
    if (isset($result['ConnectionDate']) && $eqLogic->getCmd(null, 'LastLogin')) {
        log::add('ProJote', 'debug', 'Champ reçu : LastLogin - Valeur reçue : ' . $result['ConnectionDate']);
        $eqLogic->checkAndUpdateCmd('LastLogin', $result['ConnectionDate']);
    }

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
    if (isset($result['Eleve']['Nom_Eleve']) && $eqLogic->getCmd(null, 'Nom_Eleve')) {
        $eqLogic->checkAndUpdateCmd('Nom_Eleve', $result['Eleve']['Nom_Eleve']);
    }
    //Mise à jour du nom de la classe
    if (isset($result['Eleve']['Nom_Classe']) && $eqLogic->getCmd(null, 'Nom_Classe')) {
        $eqLogic->checkAndUpdateCmd('Nom_Classe', $result['Eleve']['Nom_Classe']);
    }
    //Mise à jour du nom de l'etablissement'
    if (isset($result['Eleve']['Etablissement']) && $eqLogic->getCmd(null, 'Etablissement')) {
        $eqLogic->checkAndUpdateCmd('Etablissement', $result['Eleve']['Etablissement']);
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
    if (isset($result['Punitions']['Nb_Punitions']) && $eqLogic->getCmd(null, 'Nb_punitions')) {
        $eqLogic->checkAndUpdateCmd('Nb_punitions', $result['Punitions']['Nb_Punitions']);
    }
    // Met à jour le lien Ical
    if (isset($result['Ical']) && $eqLogic->getCmd(null, 'URL_Ical')) {
        $eqLogic->checkAndUpdateCmd('URL_Ical', $result['Ical']);
    } else {
        $resultIcal = "Pas d'URL retournée";
        $eqLogic->checkAndUpdateCmd('URL_Ical', "Pas d'URL retournée");
    }

    // Met à jour les horaires de l'emploi du temps
    if (isset($result['Emploi_du_temps']['edt_aujourdhui_debut']) && $eqLogic->getCmd(null, 'edt_aujourdhui_debut')) {
        $eqLogic->checkAndUpdateCmd('edt_aujourdhui_debut', $result['Emploi_du_temps']['edt_aujourdhui_debut']);
    } else {
        $eqLogic->checkAndUpdateCmd('edt_aujourdhui_debut', "Pas de cours aujourd'hui retourné");
    }
    if (isset($result['Emploi_du_temps']['edt_aujourdhui_fin']) && $eqLogic->getCmd(null, 'edt_aujourdhui_fin')) {
        $eqLogic->checkAndUpdateCmd('edt_aujourdhui_fin', $result['Emploi_du_temps']['edt_aujourdhui_fin']);
    } else {
        $eqLogic->checkAndUpdateCmd('edt_aujourdhui_fin', "Pas de cours aujourd'hui retourné");
    }
    if (isset($result['Emploi_du_temps']['edt_aujourdhui_cancel']) && $eqLogic->getCmd(null, 'edt_aujourdhui_cancel ')) {
        $eqLogic->checkAndUpdateCmd('edt_aujourdhui_cancel', $result['Emploi_du_temps']['edt_aujourdhui_cancel']);
    } else {
        $eqLogic->checkAndUpdateCmd('edt_aujourdhui_cancel', "0");
    }
    if (isset($result['Emploi_du_temps']['edt_prochainjour_debut']) && $eqLogic->getCmd(null, 'edt_prochainjour_debut')) {
        $eqLogic->checkAndUpdateCmd('edt_prochainjour_debut', $result['Emploi_du_temps']['edt_prochainjour_debut']);
    } else {
        $eqLogic->checkAndUpdateCmd('edt_prochainjour_debut', "Pas de cours suivant retourné");
    }
    if (isset($result['Emploi_du_temps']['edt_prochainjour_fin']) && $eqLogic->getCmd(null, 'edt_prochainjour_fin')) {
        $eqLogic->checkAndUpdateCmd('edt_prochainjour_fin', $result['Emploi_du_temps']['edt_prochainjour_fin']);
    } else {
        $eqLogic->checkAndUpdateCmd('edt_prochainjour_fin', "Pas de cours aujourd'hui retourné");
    }
    if (isset($result['Emploi_du_temps']['edt_prochainjour_cancel']) && $eqLogic->getCmd(null, 'edt_prochainjour_cancel')) {
        $eqLogic->checkAndUpdateCmd('edt_prochainjour_cancel', $result['Emploi_du_temps']['edt_prochainjour_cancel']);
    } else {
        $eqLogic->checkAndUpdateCmd('edt_prochainjour_cancel', "Pas de cours annulé pour le prochain jour");
    }
    if (isset($result['Emploi_du_temps']['edt_prochainjour_date']) && $eqLogic->getCmd(null, 'edt_prochainjour_date')) {
        $eqLogic->checkAndUpdateCmd('edt_prochainjour_date', $result['Emploi_du_temps']['edt_prochainjour_date']);
    } else {
        $eqLogic->checkAndUpdateCmd('edt_prochainjour_date', "Pas de date pour le prochain jour");
    }
    if (isset($result['Emploi_du_temps']['edt_Cours_canceled']) && $eqLogic->getCmd(null, 'edt_Cours_canceled')) {
        $eqLogic->checkAndUpdateCmd('edt_Cours_canceled', $result['Emploi_du_temps']['edt_Cours_canceled']);
    } else {
        $eqLogic->checkAndUpdateCmd('edt_Cours_canceled', "Pas de cours annulé retourné");
    }


    // Vérifie les entrées des Notes (tableaux "note" et "derniere_note")
    if (isset($result["Notes"]["note"]) && $eqLogic->getCmd(null, 'note')) {
        log::add('ProJote', 'debug', 'Champ reçu : note - Valeur reçue : ' . json_encode($result["Notes"]["note"]));
        $eqLogic->checkAndUpdateCmd('note', json_encode($result["Notes"]["note"]));
    } else {
        $eqLogic->checkAndUpdateCmd('note', "Pas de notes retournées");
    }

    if (isset($result["Notes"]["derniere_note"]) && $eqLogic->getCmd(null, 'derniere_note')) {
        log::add('ProJote', 'debug', 'Champ reçu : derniere_note - Valeur reçue : ' . json_encode($result["Notes"]["derniere_note"]));
        $eqLogic->checkAndUpdateCmd('derniere_note', json_encode($result["Notes"]["derniere_note"]));
    } else {
        $eqLogic->checkAndUpdateCmd('derniere_note', "Pas de dernière note retournée");
    }

    // Vérifie les entrées des Retards (tableaux "retard", "dernier_retard" et "nb_retard")
    if (isset($result["Retards"]["retard"]) && $eqLogic->getCmd(null, 'retard')) {
        log::add('ProJote', 'debug', 'Champ reçu : retard - Valeur reçue : ' . json_encode($result["Retards"]["retard"]));
        $eqLogic->checkAndUpdateCmd('retard', json_encode($result["Retards"]["retard"]));
    } else {
        $eqLogic->checkAndUpdateCmd('retard', "Pas de retard retourné");
    }

    if (isset($result["Retards"]["dernier_retard"]) && $eqLogic->getCmd(null, 'dernier_retard')) {
        log::add('ProJote', 'debug', 'Champ reçu : dernier_retard - Valeur reçue : ' . json_encode($result["Retards"]["dernier_retard"]));
        $eqLogic->checkAndUpdateCmd('dernier_retard', json_encode($result["Retards"]["dernier_retard"]));
    } else {
        $eqLogic->checkAndUpdateCmd('dernier_retard', "Pas de dernier retard retourné");
    }

    if (isset($result["Retards"]["nb_retard"]) && $eqLogic->getCmd(null, 'Nb_retard')) {
        log::add('ProJote', 'debug', 'Champ reçu : Nb_retard - Valeur reçue : ' . $result["Retards"]["nb_retard"]);
        $eqLogic->checkAndUpdateCmd('Nb_retard', $result["Retards"]["nb_retard"]);
    } else {
        $eqLogic->checkAndUpdateCmd('Nb_retard', "Pas de nombre de retard retourné");
    }

    // Vérifie les entrées des Punitions (tableaux "punition" et "derniere_punition")
    if (isset($result["Punitions"]["punition"]) && $eqLogic->getCmd(null, 'punition')) {
        log::add('ProJote', 'debug', 'Champ reçu : punition - Valeur reçue : ' . json_encode($result["Punitions"]["punition"]));
        $eqLogic->checkAndUpdateCmd('punition', json_encode($result["Punitions"]["punition"]));
    } else {
        $eqLogic->checkAndUpdateCmd('punition', "Pas de punition retournée");
    }

    if (isset($result["Punitions"]["derniere_punition"]) && $eqLogic->getCmd(null, 'derniere_punition')) {
        log::add('ProJote', 'debug', 'Champ reçu : derniere_punition - Valeur reçue : ' . json_encode($result["Punitions"]["derniere_punition"]));
        $eqLogic->checkAndUpdateCmd('derniere_punition', json_encode($result["Punitions"]["derniere_punition"]));
    } else {
        $eqLogic->checkAndUpdateCmd('derniere_punition', "Pas de dernière punition retournée");
    }

    // Vérifie les entrées des Notifications (tableaux "Notification" et "dernier_Notification")
    if (isset($result["Notifications"]["Notification"]) && $eqLogic->getCmd(null, 'notifications')) {
        log::add('ProJote', 'debug', 'Champ reçu : notifications - Valeur reçue : ' . json_encode($result["Notifications"]["Notification"]));
        $eqLogic->checkAndUpdateCmd('notifications', json_encode($result["Notifications"]["Notification"]));
    } else {
        $eqLogic->checkAndUpdateCmd('notifications', "Pas de notification retournée");
    }

    if (isset($result["Notifications"]["dernier_Notification"]) && $eqLogic->getCmd(null, 'derniere_notification')) {
        log::add('ProJote', 'debug', 'Champ reçu : derniere_notification - Valeur reçue : ' . json_encode($result["Notifications"]["dernier_Notification"]));
        $eqLogic->checkAndUpdateCmd('derniere_notification', json_encode($result["Notifications"]["dernier_Notification"]));
    } else {
        $eqLogic->checkAndUpdateCmd('derniere_notification', "Pas de dernière notification retournée");
    }

    // Vérifie les entrés de devoir
    if (is_array($result["Devoirs"])) {
        // Parcourt toutes les clés possibles
        foreach ($result["Devoirs"] as $key => $value) {
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
    // Vérifie les entrées des compétences
    if (isset($result["Competences"]) && $eqLogic->getCmd(null, 'competences')) {
        log::add('ProJote', 'debug', 'Champ reçu : notifications - Valeur reçue : ' . json_encode($result["Competences"]));
        $eqLogic->checkAndUpdateCmd('competences', json_encode($result["Competences"]));
    } else {
        $eqLogic->checkAndUpdateCmd('competences', "Pas de compétences retournée");
    }
    if (is_array($result["Token"])) {
        // Correspondance des clés JSON avec les commandes Jeedom
        $cmdMapping = [
            'pronote_url' => 'TokenUrl',
            'username' => 'TokenUsername',
            'password' => 'TokenPassword',
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
    // copie l'emploi du temps dans la commande Emploi du temps
    if (isset($result['Emploi_du_temps']['edt_aujourdhui']) && $eqLogic->getCmd(null, 'edt_aujourdhui')) {
        log::add('ProJote', 'debug', 'Champ reçu : edt_aujourdhui - Valeur reçue : ' . json_encode($result['Emploi_du_temps']['edt_aujourdhui'],));
        $eqLogic->checkAndUpdateCmd('edt_aujourdhui', json_encode($result['Emploi_du_temps']['edt_aujourdhui'],));
    } else {
        $eqLogic->checkAndUpdateCmd('edt_aujourdhui', "Pas d'emploi du temps retourné");
    }
    if (isset($result['Emploi_du_temps']['edt_prochainjour']) && $eqLogic->getCmd(null, 'edt_prochainjour')) {
        log::add('ProJote', 'debug', 'Champ reçu : edt_prochainjour - Valeur reçue : ' . json_encode($result['Emploi_du_temps']['edt_prochainjour'],));
        $eqLogic->checkAndUpdateCmd('edt_prochainjour', json_encode($result['Emploi_du_temps']['edt_prochainjour'],));
    } else {
        $eqLogic->checkAndUpdateCmd('edt_prochainjour', "Pas d'emploi du temps retourné");
    }
    // Je recherche devoir
    if (isset($result['Devoirs']['devoir']) && $eqLogic->getCmd(null, 'devoir')) {
        log::add('ProJote', 'debug', 'Champ reçu : devoirs - Valeur reçue : ' . json_encode($result['Devoirs']['devoir'], JSON_PRETTY_PRINT));
        $eqLogic->checkAndUpdateCmd('devoir', json_encode($result['Devoirs']['devoir'],));
    } else {
        $eqLogic->checkAndUpdateCmd('devoir', "Pas de devoirs retourné");
    }
    // Je recherche devoir_Demain
    if (isset($result['Devoirs']['devoir_Demain']) && $eqLogic->getCmd(null, 'devoir_Demain')) {
        log::add('ProJote', 'debug', 'Champ reçu : devoirs - Valeur reçue : ' . json_encode($result['Devoirs']['devoir_Demain'], JSON_PRETTY_PRINT));
        $eqLogic->checkAndUpdateCmd('devoir_Demain', json_encode($result['Devoirs']['devoir_Demain'],));
    } else {
        $eqLogic->checkAndUpdateCmd('devoir_Demain', "Pas de devoir pour demain retourné");
    }
    // Je recherche les absences
    if (isset($result['Absences']['absence']) && $eqLogic->getCmd(null, 'absence')) {
        log::add('ProJote', 'debug', 'Champ reçu : absence - Valeur reçue : ' . json_encode($result['Absences']['absence'],));
        $eqLogic->checkAndUpdateCmd('absence', json_encode($result['Absences']['absence'],));
    } else {
        $eqLogic->checkAndUpdateCmd('absence', "Pas d'absence retourné");
    }
    // Je recherche la derniére absence
    if (isset($result['Absences']['derniere_absence']) && $eqLogic->getCmd(null, 'derniere_absence')) {
        log::add('ProJote', 'debug', 'Champ reçu : derniere_absence - Valeur reçue : ' . json_encode($result['Absences']['derniere_absence'],));
        $eqLogic->checkAndUpdateCmd('derniere_absence', json_encode($result['Absences']['derniere_absence'],));
    } else {
        $eqLogic->checkAndUpdateCmd('derniere_absence', "Pas de dernière absence retournée");
    }
} catch (Exception $e) {
    log::add('ProJote', 'error', displayException($e));
}
