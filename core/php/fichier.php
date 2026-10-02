<?php
/* ProJote — plugin Jeedom pour Pronote
 * Copyright (C) 2024-2026 Aldarande
 * Licensed under the GNU Affero General Public License v3 or later.
 * See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.
 */

/**
 * fichier.php — Sert un fichier d'équipement à un utilisateur Jeedom connecté.
 *
 * Tout ce que le plugin range dans `data/` concerne un mineur : sa photo, et
 * les documents joints aux actualités de l'établissement — menu de cantine,
 * circulaires. Rien de cela ne doit être servi à qui connaît l'URL.
 *
 * Le dossier `data/` est donc entièrement fermé par son .htaccess. Les jetons
 * et l'index n'en sortent jamais ; la photo et les pièces jointes passent par
 * ici, où la session Jeedom est vérifiée avant la moindre lecture.
 *
 * Paramètres :
 *   id      — identifiant de l'équipement ProJote
 *   fichier — nom d'une pièce jointe, tel que le collecteur l'a assaini
 *   photo   — « pronote » ou « manual », au lieu de « fichier »
 *
 * Le nom est revalidé ici malgré l'assainissement du collecteur : il transite
 * par l'URL, et un point d'accès ne fait jamais confiance à ce qui lui vient
 * de l'extérieur.
 */

try {
    require_once dirname(__FILE__) . '/../../../../core/php/core.inc.php';
    include_file('core', 'authentification', 'php');

    // Tout utilisateur Jeedom connecté, pas seulement un administrateur : le
    // widget est consulté par les comptes ordinaires de la maison.
    if (!isConnect()) {
        http_response_code(401);
        die('401 - Accès non autorisé');
    }

    $eqLogicId = init('id');
    $demande   = init('fichier');
    $photo     = init('photo');

    $eqLogic = eqLogic::byId($eqLogicId);
    if (!is_object($eqLogic) || $eqLogic->getEqType_name() !== 'ProJote') {
        http_response_code(404);
        die('404 - Équipement inconnu');
    }

    // Les photos portent un nom figé : pas de validation à faire, pas de nom à
    // faire transiter. On s'en remet à un jeu fermé de deux valeurs.
    if ($photo !== '') {
        $noms = array(
            'pronote' => 'profile_picture.jpg',
            'manual'  => 'profile_picture_manual.jpg',
        );
        if (!isset($noms[$photo])) {
            http_response_code(400);
            die('400 - Photo inconnue');
        }
        $chemin = realpath(
            dirname(__FILE__) . '/../../data/' . $eqLogic->getId() . '/' . $noms[$photo]
        );
        if ($chemin === false || !is_file($chemin)) {
            http_response_code(404);
            die('404 - Photo introuvable');
        }
        header('Content-Type: image/jpeg');
        header('X-Content-Type-Options: nosniff');
        header('Content-Length: ' . filesize($chemin));
        header('Cache-Control: private, max-age=300');
        readfile($chemin);
        return;
    }

    // basename() seul ne suffit pas : on exige que le nom soit déjà sa propre
    // base, pour qu'une tentative de remontée soit refusée plutôt que corrigée
    // en silence. Les fichiers cachés — .index.json, .htaccess — sont exclus.
    $nom = basename((string) $demande);
    if (
        $demande === '' || $nom !== $demande
        || $nom[0] === '.'
        || !preg_match('/^[A-Za-z0-9](?:[A-Za-z0-9._ -]*[A-Za-z0-9])?\.[A-Za-z0-9]{1,8}$/', $nom)
    ) {
        http_response_code(400);
        die('400 - Nom de fichier invalide');
    }

    $racine = realpath(dirname(__FILE__) . '/../../data/' . $eqLogic->getId() . '/file');
    $chemin = $racine === false ? false : realpath($racine . DIRECTORY_SEPARATOR . $nom);

    // Deuxième garde, après résolution des liens : le chemin réel doit rester
    // sous le dossier de CET équipement. Un lien symbolique déposé dans le
    // dossier ne doit pas devenir une porte vers le reste du disque.
    if (
        $chemin === false || !is_file($chemin)
        || strpos($chemin, $racine . DIRECTORY_SEPARATOR) !== 0
    ) {
        http_response_code(404);
        die('404 - Pièce jointe introuvable');
    }

    $types = array(
        'pdf'  => 'application/pdf',
        'odt'  => 'application/vnd.oasis.opendocument.text',
        'ods'  => 'application/vnd.oasis.opendocument.spreadsheet',
        'odp'  => 'application/vnd.oasis.opendocument.presentation',
        'doc'  => 'application/msword',
        'docx' => 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'xls'  => 'application/vnd.ms-excel',
        'xlsx' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'ppt'  => 'application/vnd.ms-powerpoint',
        'pptx' => 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'rtf'  => 'application/rtf',
        'txt'  => 'text/plain; charset=utf-8',
        'csv'  => 'text/csv; charset=utf-8',
        'jpg'  => 'image/jpeg',
        'jpeg' => 'image/jpeg',
        'png'  => 'image/png',
        'webp' => 'image/webp',
        'gif'  => 'image/gif',
        'zip'  => 'application/zip',
    );
    $extension = strtolower(pathinfo($nom, PATHINFO_EXTENSION));

    // Extension inconnue : on refuse, au lieu de servir en octet-stream. Le
    // collecteur n'écrit que les types ci-dessus ; tout autre fichier dans ce
    // dossier n'a rien à y faire et ne doit pas sortir — un .php déposé là
    // était auparavant servi en téléchargement, inerte mais sans raison.
    if (!isset($types[$extension])) {
        http_response_code(403);
        die('403 - Type de fichier non servi');
    }
    $type = $types[$extension];

    header('Content-Type: ' . $type);
    header('X-Content-Type-Options: nosniff');
    header('Content-Security-Policy: default-src \'none\'; object-src \'none\'');
    header('Content-Length: ' . filesize($chemin));
    header('Content-Disposition: inline; filename="' . rawurlencode($nom) . '"');
    header('Cache-Control: private, max-age=300');

    readfile($chemin);
} catch (Exception $e) {
    http_response_code(500);
    die('500 - ' . $e->getMessage());
}
