<?php
/* ProJote — plugin Jeedom pour Pronote
 * Copyright (C) 2024-2026 Aldarande
 * Licensed under the GNU Affero General Public License v3 or later.
 * See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.
 */

/**
 * jeeProJote.php — Point de callback HTTP du démon Python vers Jeedom.
 *
 * Ce fichier est l'URL que le démon Python (ProJoted.py) appelle pour envoyer
 * les données Pronote à Jeedom. Il reçoit un JSON en POST et met à jour
 * toutes les commandes de l'équipement concerné.
 *
 * Flux de données :
 *  ProJoted.py → HTTP POST vers /plugins/ProJote/core/php/jeeProJote.php → ici
 *
 * Ce fichier reçoit un JSON structuré contenant :
 *  - CmdId             : ID de l'équipement Jeedom à mettre à jour
 *  - connection_status : 'connected', 'disconnected' ou 'error'
 *  - ConnectionDate    : Date/heure de la dernière connexion réussie
 *  - Eleve             : Infos élève (Nom_Eleve, Nom_Classe, Etablissement)
 *  - Emploi_du_temps   : Emploi du temps du jour et du prochain jour
 *  - Notes, Devoirs, Absences, Retards, Punitions... : Données scolaires
 *  - Emploi_du_temps.edt_next_days : tableau compact [{cours,date,debut,fin,cancel}] pour J+1..J+4
 *  - Emploi_du_temps.edt_J{1..4}[_date|_debut|_fin|_cancel] : commandes Jeedom J+1 à J+4
 *  - Token             : Token de reconnexion Pronote à sauvegarder
 *
 * Sécurité : la clé API Jeedom est vérifiée avant tout traitement.
 */
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

    // ===== GESTION DU STATUT DE CONNEXION =====
    $connection_status = isset($result['connection_status']) ? $result['connection_status'] : 'unknown';

    if ($connection_status === 'disconnected' || $connection_status === 'error') {
        $error_message = isset($result['error']) ? $result['error'] : 'Raison non spécifiée';

        // Expose le statut dans la cmd info "Statut_Connexion" pour le widget et les scénarios.
        if ($eqLogic->getCmd(null, 'Statut_Connexion')) {
            $label = ($connection_status === 'disconnected')
                ? 'Déconnecté : ' . $error_message
                : 'Erreur : ' . $error_message;
            $eqLogic->checkAndUpdateCmd('Statut_Connexion', $label);
        }

        // Log le statut avec différenciation claire
        if ($connection_status === 'disconnected') {
            log::add('ProJote', 'warning', '[SESSION EXPIRÉE] ' . $eqLogic->getHumanName() . ' - ' . $error_message);
        } else {
            log::add('ProJote', 'error', '[CONNEXION ÉCHOUÉE] ' . $eqLogic->getHumanName() . ' - ' . $error_message);
        }

        // Ajoute un message au centre de messages Jeedom
        // Signature: message::add($_type, $_message, $_action='', $_logicalId='')
        if ($connection_status === 'disconnected') {
            message::add(
                'ProJote',
                '[' . $eqLogic->getHumanName() . '] Session expirée — Veuillez rescanner le QR code ou re-valider les identifiants.'
            );
        } else {
            message::add(
                'ProJote',
                '[' . $eqLogic->getHumanName() . '] Connexion échouée : ' . $error_message
            );
        }

        // Fin du traitement - données non traitées
        die();
    }

    //Je met à jours la date de dernière communication
    //Mise à jour du nom de l'élève
    if (isset($result['ConnectionDate']) && $eqLogic->getCmd(null, 'LastLogin')) {
        log::add('ProJote', 'debug', 'Champ reçu : LastLogin - Valeur reçue : ' . $result['ConnectionDate']);
        $eqLogic->checkAndUpdateCmd('LastLogin', $result['ConnectionDate']);
    }

    // Cycle connecté : on rafraîchit la cmd "Statut_Connexion" en positif.
    if ($connection_status === 'connected' && $eqLogic->getCmd(null, 'Statut_Connexion')) {
        $eqLogic->checkAndUpdateCmd('Statut_Connexion', 'Connecté');
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
    // Résolution de la photo selon la préférence photo_source de l'équipement.
    // Valeurs : 'none' (initiales, défaut) | 'pronote' | 'manual' | 'auto' (Pronote puis manuelle)
    $manualPhotoFile = realpath(dirname(__FILE__) . '/../../data') . DIRECTORY_SEPARATOR . $eqLogic->getId() . DIRECTORY_SEPARATOR . 'profile_picture_manual.jpg';
    $manualPhotoUrl  = '/plugins/ProJote/data/' . $eqLogic->getId() . '/profile_picture_manual.jpg';
    $pronotePhotoUrl = !empty($result['Local_Picture']) ? $result['Local_Picture'] : null;
    $manualExists    = file_exists($manualPhotoFile);
    switch ($eqLogic->getConfiguration('photo_source', 'none')) {
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
    if ($eqLogic->getCmd(null, 'Picture')) {
        $eqLogic->checkAndUpdateCmd('Picture', $resolvedPhoto);
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
    // Mise à jour des commandes J+1 à J+4
    for ($j = 1; $j <= 4; $j++) {
        $prefix = "edt_J{$j}";
        if (isset($result['Emploi_du_temps'][$prefix]) && $eqLogic->getCmd(null, $prefix)) {
            $eqLogic->checkAndUpdateCmd($prefix, json_encode($result['Emploi_du_temps'][$prefix]));
        }
        foreach (['_date', '_debut', '_fin', '_cancel'] as $suffix) {
            $key = $prefix . $suffix;
            if (isset($result['Emploi_du_temps'][$key]) && $eqLogic->getCmd(null, $key)) {
                $eqLogic->checkAndUpdateCmd($key, $result['Emploi_du_temps'][$key]);
            }
        }
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

    // Moyenne générale (numérique, historisée) — n'écrit que si une valeur exploitable est calculée (F3, v1.1.0)
    if (isset($result["Notes"]["moyenne_generale"]) && $result["Notes"]["moyenne_generale"] !== "" && $eqLogic->getCmd(null, 'moyenne_generale')) {
        log::add('ProJote', 'debug', 'Champ reçu : moyenne_generale - Valeur reçue : ' . $result["Notes"]["moyenne_generale"]);
        $eqLogic->checkAndUpdateCmd('moyenne_generale', $result["Notes"]["moyenne_generale"]);
    }

    // Matière(s) en baisse (chaîne, détection heuristique sur les notes) (F3, v1.1.0)
    if (isset($result["Notes"]["matiere_en_baisse"]) && $eqLogic->getCmd(null, 'matiere_en_baisse')) {
        log::add('ProJote', 'debug', 'Champ reçu : matiere_en_baisse - Valeur reçue : ' . $result["Notes"]["matiere_en_baisse"]);
        $eqLogic->checkAndUpdateCmd('matiere_en_baisse', $result["Notes"]["matiere_en_baisse"]);
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
            // Saute les structures complexes destinées aux scénarios avancés
            if ($key === 'menus_brut' || $key === 'error') {
                continue;
            }
            // Vérifie si la clé existe et met à jour la commande correspondante
            if (isset($value) && $eqLogic->getCmd(null, $key)) {
                log::add('ProJote', 'debug', 'Champ reçu : ' . $key . ' - Valeur reçue : ' . print_r($value, true));
                $eqLogic->checkAndUpdateCmd($key, $value);
            }
        }
    } else {
        log::add('ProJote', 'debug', 'Menus non reçu');
    }

    // ── Messagerie Pronote (v1.0.1) ─────────────────────────────────────────
    // Le démon envoie un dict avec sous-clés Nb_messages_non_lus,
    // dernier_message_*, messages_html, etc. On itère comme pour Menus.
    if (isset($result["Messages"]) && is_array($result["Messages"])) {
        foreach ($result["Messages"] as $key => $value) {
            if ($key === 'messages_brut' || $key === 'error') {
                continue;
            }
            if (isset($value) && $eqLogic->getCmd(null, $key)) {
                log::add('ProJote', 'debug', 'Champ reçu : ' . $key . ' - Valeur reçue : ' . print_r($value, true));
                $eqLogic->checkAndUpdateCmd($key, $value);
            }
        }
    } else {
        log::add('ProJote', 'debug', 'Messages non reçu');
    }
    // Vérifie les entrées des compétences
    if (isset($result["Competences"]) && $eqLogic->getCmd(null, 'competences')) {
        log::add('ProJote', 'debug', 'Champ reçu : notifications - Valeur reçue : ' . json_encode($result["Competences"]));
        $eqLogic->checkAndUpdateCmd('competences', json_encode($result["Competences"]));
    } else {
        $eqLogic->checkAndUpdateCmd('competences', "Pas de compétences retournée");
    }
    // ── SAUVEGARDE DU TOKEN DE RECONNEXION ──────────────────────────────────
    // Le token permet au démon de se reconnecter à Pronote sans redemander
    // le mot de passe. Il est sauvegardé en configuration Jeedom (BDD chiffrée).
    // Format reçu : { pronote_url, username, password, client_identifier }
    if (is_array($result["Token"])) {
        $tokenMapping = [
            'pronote_url'       => 'Token_pronote_url',
            'username'          => 'Token_username',
            'password'          => 'Token_password',        // Chiffré automatiquement (voir $_encryptConfigKey)
            'client_identifier' => 'Token_client_identifier',
        ];
        foreach ($tokenMapping as $jsonKey => $configKey) {
            if (isset($result["Token"][$jsonKey])) {
                $eqLogic->setConfiguration($configKey, $result["Token"][$jsonKey]);
                log::add('ProJote', 'debug', 'Token config sauvegardé : ' . $configKey);
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

    // Sauvegarde en configuration Jeedom (BDD)
    if (isset($result['Eleve']['Nom_Eleve'])) {
        $eqLogic->setConfiguration('Eleve', $result['Eleve']['Nom_Eleve']);
    }
    if (isset($result['Eleve']['Nom_Classe'])) {
        $eqLogic->setConfiguration('Classe', $result['Eleve']['Nom_Classe']);
    }
    if (isset($result['Eleve']['Etablissement'])) {
        $eqLogic->setConfiguration('Etablissement', $result['Eleve']['Etablissement']);
    }
    if (isset($result['Ical']) && !empty($result['Ical'])) {
        $eqLogic->setConfiguration('Ical', $result['Ical']);
    }
    if (isset($result['Liste_Enfant'])) {
        $listeEnfant = is_array($result['Liste_Enfant']) ? json_encode($result['Liste_Enfant']) : $result['Liste_Enfant'];
        $eqLogic->setConfiguration('Liste_Enfant', $listeEnfant);
    }
    // ── SAUVEGARDE DES DONNÉES DU WIDGET ────────────────────────────────────
    // ── Centre d'alertes (F4, v1.1.0) ──────────────────────────────────────────
    // Génère des événements ProJote en comparant les compteurs courants à ceux du
    // cycle précédent (mémorisés en configuration eqLogic = BDD Jeedom). FIFO de 50.
    $newCounters = array(
        'absences'  => (int)(isset($result['Absences']['nb_absences']) ? $result['Absences']['nb_absences'] : 0),
        'retards'   => (int)(isset($result['Retards']['nb_retard']) ? $result['Retards']['nb_retard'] : 0),
        'punitions' => (int)(isset($result['Punitions']['Nb_Punitions']) ? $result['Punitions']['Nb_Punitions'] : 0),
        'msg_nl'    => (int)(isset($result['Messages']['Nb_messages_non_lus']) ? $result['Messages']['Nb_messages_non_lus'] : 0),
        'ds'        => (string)(isset($result['Devoirs']['prochain_DS_matiere']) ? $result['Devoirs']['prochain_DS_matiere'] : '')
                     . '|' . (string)(isset($result['Devoirs']['prochain_DS_date']) ? $result['Devoirs']['prochain_DS_date'] : ''),
        'meb'       => (string)(isset($result['Notes']['matiere_en_baisse']) ? $result['Notes']['matiere_en_baisse'] : ''),
    );
    $prevCounters = json_decode($eqLogic->getConfiguration('projote_counters_prev', '{}'), true);
    if (!is_array($prevCounters)) $prevCounters = array();
    $events = json_decode($eqLogic->getConfiguration('projote_events', '[]'), true);
    if (!is_array($events)) $events = array();

    $now = date('d/m/Y H:i');
    $addEvent = function ($type, $label) use (&$events, $now) {
        array_unshift($events, array('date' => $now, 'type' => $type, 'label' => $label));
    };
    // Nouveautés détectées par le démon (P3) : nouvelles notes / nouveaux devoirs.
    // Le démon n'émet ces libellés qu'à partir du 2e cycle (pas au branchement).
    $deltas = isset($result['Deltas']) && is_array($result['Deltas']) ? $result['Deltas'] : array();
    $nouvelleNote   = isset($deltas['derniere_nouvelle_note']) ? trim((string)$deltas['derniere_nouvelle_note']) : '';
    $nouveauDevoir  = isset($deltas['dernier_nouveau_devoir']) ? trim((string)$deltas['dernier_nouveau_devoir']) : '';
    // Mise à jour UNIQUEMENT si non vide : écraser par '' déclencherait à tort
    // les scénarios branchés sur ces commandes.
    if ($nouvelleNote !== '' && $eqLogic->getCmd(null, 'nouvelle_note')) {
        $eqLogic->checkAndUpdateCmd('nouvelle_note', $nouvelleNote);
        $addEvent('note', 'Nouvelle note — ' . $nouvelleNote);
    }
    if ($nouveauDevoir !== '' && $eqLogic->getCmd(null, 'nouveau_devoir')) {
        $eqLogic->checkAndUpdateCmd('nouveau_devoir', $nouveauDevoir);
        $addEvent('devoir', 'Nouveau devoir — ' . $nouveauDevoir);
    }

    // On ne génère des événements qu'à partir du 2e cycle (snapshot précédent présent),
    // pour éviter une avalanche d'alertes au premier rafraîchissement.
    if (!empty($prevCounters)) {
        if ($newCounters['absences']  > (isset($prevCounters['absences'])  ? $prevCounters['absences']  : 0)) $addEvent('absence',  'Nouvelle absence');
        if ($newCounters['retards']   > (isset($prevCounters['retards'])   ? $prevCounters['retards']   : 0)) $addEvent('retard',   'Nouveau retard');
        if ($newCounters['punitions'] > (isset($prevCounters['punitions']) ? $prevCounters['punitions'] : 0)) $addEvent('punition', 'Nouvelle punition');
        if ($newCounters['msg_nl']    > (isset($prevCounters['msg_nl'])    ? $prevCounters['msg_nl']    : 0)) $addEvent('message',  'Nouveau message non lu');
        if ($newCounters['ds'] !== (isset($prevCounters['ds']) ? $prevCounters['ds'] : '')
            && isset($result['Devoirs']['prochain_DS_matiere']) && $result['Devoirs']['prochain_DS_matiere'] !== '') {
            $addEvent('ds', 'Contrôle détecté : ' . $result['Devoirs']['prochain_DS_matiere']
                . ' le ' . (isset($result['Devoirs']['prochain_DS_date']) ? $result['Devoirs']['prochain_DS_date'] : '?'));
        }
        if ($newCounters['meb'] !== (isset($prevCounters['meb']) ? $prevCounters['meb'] : '') && $newCounters['meb'] !== '') {
            $addEvent('baisse', 'Matière en baisse : ' . $newCounters['meb']);
        }
    }
    $events = array_slice($events, 0, 50);
    $eqLogic->setConfiguration('projote_events', json_encode($events));
    $eqLogic->setConfiguration('projote_counters_prev', json_encode($newCounters));
    if (count($events) && $eqLogic->getCmd(null, 'event')) {
        $eqLogic->checkAndUpdateCmd('event', $events[0]['label']);
    }

    // Le widget ProJote utilise toHtml() sur l'eqLogic (plus de commande Widget).
    // Les données sont stockées en configuration de l'équipement sous la clé 'widget_json'.
    // toHtml() les lit à chaque rendu ; le JS les récupère via l'action GetWidgetData.
    $widget_data = array(
        'eleve'                 => isset($result['Eleve']['Nom_Eleve'])                       ? $result['Eleve']['Nom_Eleve']                       : '',
        'classe'                => isset($result['Eleve']['Nom_Classe'])                      ? $result['Eleve']['Nom_Classe']                      : '',
        'etablissement'         => isset($result['Eleve']['Etablissement'])                    ? $result['Eleve']['Etablissement']                    : '',
        'notes'                 => isset($result['Notes']['note'])                            ? $result['Notes']['note']                            : array(),
        'moyennes_periodes'     => isset($result['Notes']['moyennes_periodes'])               ? $result['Notes']['moyennes_periodes']               : array(),
        'edt_aujourdhui'        => isset($result['Emploi_du_temps']['edt_aujourdhui'])        ? $result['Emploi_du_temps']['edt_aujourdhui']        : array(),
        'edt_prochainjour'      => isset($result['Emploi_du_temps']['edt_prochainjour'])      ? $result['Emploi_du_temps']['edt_prochainjour']      : array(),
        'edt_prochainjour_date' => isset($result['Emploi_du_temps']['edt_prochainjour_date']) ? $result['Emploi_du_temps']['edt_prochainjour_date'] : '',
        'nb_cours_annules'      => isset($result['Emploi_du_temps']['edt_Cours_canceled'])    ? (int)$result['Emploi_du_temps']['edt_Cours_canceled']    : 0,
        'nb_absences'           => isset($result['Absences']['nb_absences'])                  ? $result['Absences']['nb_absences']                  : 0,
        'nb_retards'            => isset($result['Retards']['nb_retard'])                     ? $result['Retards']['nb_retard']                     : 0,
        'nb_punitions'          => isset($result['Punitions']['Nb_Punitions'])                ? $result['Punitions']['Nb_Punitions']                : 0,
        'nb_devoirs_nf'         => isset($result['Devoirs']['Nb_devoir_NF'])                  ? $result['Devoirs']['Nb_devoir_NF']                  : 0,
        'absences'              => isset($result['Absences']['absence'])                      ? $result['Absences']['absence']                      : array(),
        'retards'               => isset($result['Retards']['retard'])                        ? $result['Retards']['retard']                        : array(),
        'punitions'             => isset($result['Punitions']['punition'])                    ? $result['Punitions']['punition']                    : array(),
        'devoirs'               => isset($result['Devoirs']['devoir'])                        ? $result['Devoirs']['devoir']                        : array(),
        'devoirs_demain'        => isset($result['Devoirs']['devoir_Demain'])                 ? $result['Devoirs']['devoir_Demain']                 : array(),
        'nb_devoirs_f'          => isset($result['Devoirs']['Nb_devoir_F'])                   ? $result['Devoirs']['Nb_devoir_F']                   : 0,
        'edt_next_days'         => isset($result['Emploi_du_temps']['edt_next_days'])          ? $result['Emploi_du_temps']['edt_next_days']          : array(),
        'photo'                 => $resolvedPhoto,
        'pronote_photo'         => $pronotePhotoUrl ?? '',
        'moyenne_generale'         => isset($result['Notes']['moyenne_generale'])         ? $result['Notes']['moyenne_generale']         : '',
        'matiere_en_baisse'        => isset($result['Notes']['matiere_en_baisse'])        ? $result['Notes']['matiere_en_baisse']        : '',
        'matiere_en_baisse_detail' => isset($result['Notes']['matiere_en_baisse_detail']) ? $result['Notes']['matiere_en_baisse_detail'] : array(),
        'notifications'            => isset($result['Notifications']['Notification'])      ? $result['Notifications']['Notification']      : array(),
        'events'                   => $events,
        'last_update'           => date('c'),
    );
    $eqLogic->setConfiguration('widget_json', json_encode($widget_data));
    log::add('ProJote', 'debug', 'widget_json sauvegardé en configuration pour : ' . $eqLogic->getHumanName());

    $eqLogic->save();

    // Écrire le fichier JSON avec toutes les données reçues
    saveDataToJsonFile($eqLogic, $result);
} catch (Exception $e) {
    log::add('ProJote', 'error', displayException($e));
}

/**
 * Écrit le fichier JSON enfant.ProJote.json.txt avec toutes les données reçues du démon
 * Cette fonction garantit que le fichier est toujours à jour avec les dernières données
 */
function saveDataToJsonFile($eqLogic, $result)
{
    try {
        $eqid = $eqLogic->getId();
        $dataDir = dirname(dirname(dirname(__FILE__))) . DIRECTORY_SEPARATOR . 'data' . DIRECTORY_SEPARATOR . $eqid;
        $filePath = $dataDir . DIRECTORY_SEPARATOR . 'enfant.ProJote.json.txt';

        // Créer le répertoire s'il n'existe pas
        if (!is_dir($dataDir)) {
            if (!mkdir($dataDir, 0755, true)) {
                log::add('ProJote', 'error', 'Impossible de créer le répertoire : ' . $dataDir);
                return false;
            }
        }

        // Préparer les données à écrire
        $data = array(
            'Date' => date('Y-m-d H:i:s'),
            'Name' => isset($result['Eleve']['Nom_Eleve']) ? $result['Eleve']['Nom_Eleve'] : 'Unknown',
            'Token' => isset($result['Token']) ? $result['Token'] : [],
            'Eleve' => isset($result['Eleve']['Nom_Eleve']) ? $result['Eleve']['Nom_Eleve'] : 'Unknown',
            'Classe' => isset($result['Eleve']['Nom_Classe']) ? $result['Eleve']['Nom_Classe'] : 'Unknown',
            'Etablissement' => isset($result['Eleve']['Etablissement']) ? $result['Eleve']['Etablissement'] : 'Unknown',
            'Local_Picture' => isset($result['Local_Picture']) ? $result['Local_Picture'] : '',
            'Emploi_du_temps' => isset($result['Emploi_du_temps']) ? $result['Emploi_du_temps'] : [],
            'Notes' => isset($result['Notes']) ? $result['Notes'] : [],
            'Menus' => isset($result['Menus']) ? $result['Menus'] : [],
            'Notifications' => isset($result['Notifications']) ? $result['Notifications'] : [],
            'Absences' => isset($result['Absences']) ? $result['Absences'] : [],
            'Retards' => isset($result['Retards']) ? $result['Retards'] : [],
            'Punitions' => isset($result['Punitions']) ? $result['Punitions'] : [],
            'Devoirs' => isset($result['Devoirs']) ? $result['Devoirs'] : [],
            'Competences' => isset($result['Competences']) ? $result['Competences'] : [],
            'Ical' => isset($result['Ical']) ? $result['Ical'] : '',
            'Liste_Enfant' => isset($result['Liste_Enfant']) ? $result['Liste_Enfant'] : [],
            'Parent' => strpos($result['Token']['pronote_url'] ?? '', 'parent.html') !== false ? '1' : '0'
        );

        // Écrire le fichier JSON
        if (file_put_contents($filePath, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)) !== false) {
            log::add('ProJote', 'debug', 'Fichier JSON sauvegardé avec succès : ' . $filePath);
            return true;
        } else {
            log::add('ProJote', 'error', 'Impossible d\'écrire le fichier JSON : ' . $filePath);
            return false;
        }
    } catch (Exception $e) {
        log::add('ProJote', 'error', 'Erreur lors de la sauvegarde du fichier JSON : ' . $e->getMessage());
        return false;
    }
}
