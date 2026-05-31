<?php
/* ProJote — plugin Jeedom pour Pronote
 * Copyright (C) 2024-2026 Aldarande
 * Licensed under the GNU Affero General Public License v3 or later.
 * See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.
 */

/**
 * calendar.php — Export iCalendar (.ics) natif ProJote (F2, v1.1.0).
 *
 * Génère un calendrier au format iCalendar à partir des données collectées par
 * le démon (stockées dans la configuration widget_json de l'équipement et dans
 * les commandes EDT J+1..J+4) :
 *   - VEVENT pour chaque cours (emploi du temps du jour, prochain jour, J+1..J+4)
 *   - VTODO  pour chaque devoir (échéance = date du devoir)
 *
 * URL d'abonnement :
 *   https://<jeedom>/plugins/ProJote/core/php/calendar.php?apikey=<clé>&id=<eqLogicId>
 *
 * Sécurité : la clé API Jeedom est vérifiée avant tout traitement.
 */

require_once dirname(__FILE__) . "/../../../../core/php/core.inc.php";

if (!jeedom::apiAccess(init('apikey'), 'ProJote')) {
    http_response_code(403);
    echo 'Accès non autorisé';
    die();
}

$eqLogicId = init('id');
$eqLogic = ($eqLogicId !== '') ? eqLogic::byId($eqLogicId) : null;
if (!is_object($eqLogic) || $eqLogic->getEqType_name() !== 'ProJote') {
    http_response_code(404);
    echo 'Équipement ProJote introuvable';
    die();
}

// ── Helpers iCalendar ───────────────────────────────────────────────────────
function ics_escape($s)
{
    return str_replace(
        array("\\", ";", ",", "\r\n", "\n", "\r"),
        array("\\\\", "\\;", "\\,", "\\n", "\\n", "\\n"),
        (string)$s
    );
}

/** Plie une ligne iCalendar à 75 octets (RFC 5545) avec continuation par espace. */
function ics_fold($line)
{
    if (strlen($line) <= 75) {
        return $line;
    }
    $out = '';
    while (strlen($line) > 75) {
        $out .= substr($line, 0, 75) . "\r\n ";
        $line = substr($line, 75);
    }
    return $out . $line;
}

/** Construit un DateTime depuis une date dd/mm/yyyy et une heure HHMM. */
function projote_datetime($date_ddmmyyyy, $heure_hhmm)
{
    $heure_hhmm = str_pad(preg_replace('/[^0-9]/', '', (string)$heure_hhmm), 4, '0', STR_PAD_LEFT);
    $dt = DateTime::createFromFormat('!d/m/Y Hi', trim($date_ddmmyyyy) . ' ' . $heure_hhmm);
    return $dt ?: null;
}

/** Infère une date complète depuis dd/mm (les devoirs n'ont pas l'année). */
function projote_infer_date($ddmm)
{
    $parts = explode('/', trim((string)$ddmm));
    if (count($parts) < 2) {
        return null;
    }
    $d = (int)$parts[0];
    $m = (int)$parts[1];
    if ($d < 1 || $m < 1) {
        return null;
    }
    $today = new DateTime('today');
    $year  = (int)$today->format('Y');
    $cand  = DateTime::createFromFormat('!d/m/Y', sprintf('%02d/%02d/%04d', $d, $m, $year));
    if (!$cand) {
        return null;
    }
    // Si la date tombe nettement dans le passé (>60j), c'est l'année scolaire suivante.
    $diff = (int)$today->diff($cand)->format('%r%a');
    if ($diff < -60) {
        $cand->modify('+1 year');
    }
    return $cand;
}

// ── Lecture des données ─────────────────────────────────────────────────────
$widget = json_decode($eqLogic->getConfiguration('widget_json', '{}'), true);
if (!is_array($widget)) {
    $widget = array();
}

// Cours : aujourd'hui + prochain jour (widget_json) + J+1..J+4 (commandes).
$coursLists = array();
foreach (array('edt_aujourdhui', 'edt_prochainjour') as $k) {
    if (isset($widget[$k]) && is_array($widget[$k])) {
        $coursLists[] = $widget[$k];
    }
}
foreach (array('edt_J1', 'edt_J2', 'edt_J3', 'edt_J4') as $logicalId) {
    $cmd = $eqLogic->getCmd(null, $logicalId);
    if (is_object($cmd)) {
        $decoded = json_decode((string)$cmd->execCmd(), true);
        if (is_array($decoded)) {
            $coursLists[] = $decoded;
        }
    }
}

$devoirsLists = array();
foreach (array('devoirs', 'devoirs_demain') as $k) {
    if (isset($widget[$k]) && is_array($widget[$k])) {
        $devoirsLists[] = $widget[$k];
    }
}

// ── Génération du flux iCalendar ────────────────────────────────────────────
$eleve   = isset($widget['eleve']) ? $widget['eleve'] : 'Élève';
$nowUtc  = gmdate('Ymd\THis\Z');
$lines   = array();
$lines[] = 'BEGIN:VCALENDAR';
$lines[] = 'VERSION:2.0';
$lines[] = 'PRODID:-//ProJote//Jeedom//FR';
$lines[] = 'CALSCALE:GREGORIAN';
$lines[] = 'METHOD:PUBLISH';
$lines[] = 'X-WR-CALNAME:ProJote — ' . ics_escape($eleve);

$seenEvents = array();
foreach ($coursLists as $list) {
    foreach ($list as $c) {
        if (!is_array($c)) {
            continue;
        }
        $date  = isset($c['date']) ? $c['date'] : '';
        $debut = isset($c['heure']) ? $c['heure'] : '';
        $fin   = isset($c['heure_fin']) ? $c['heure_fin'] : '';
        $dtStart = projote_datetime($date, $debut);
        $dtEnd   = projote_datetime($date, $fin);
        if (!$dtStart) {
            continue;
        }
        if (!$dtEnd || $dtEnd <= $dtStart) {
            $dtEnd = (clone $dtStart)->modify('+55 minutes');
        }
        $uid = md5($date . $debut . (isset($c['cours']) ? $c['cours'] : '') . (isset($c['id']) ? $c['id'] : '')) . '@projote';
        if (isset($seenEvents[$uid])) {
            continue; // dé-doublonnage (un cours peut apparaître dans 2 listes)
        }
        $seenEvents[$uid] = true;

        $matiere = isset($c['cours']) ? $c['cours'] : 'Cours';
        $salle   = isset($c['salle']) ? $c['salle'] : '';
        $prof    = isset($c['Professeur']) ? $c['Professeur'] : '';
        $annule  = !empty($c['annulation']);

        $summary = $matiere . ($salle !== '' ? ' (' . $salle . ')' : '') . ($annule ? ' — Annulé' : '');
        $desc    = trim($prof . ($salle !== '' ? "\nSalle : " . $salle : ''));

        $lines[] = 'BEGIN:VEVENT';
        $lines[] = 'UID:' . $uid;
        $lines[] = 'DTSTAMP:' . $nowUtc;
        $lines[] = 'DTSTART:' . $dtStart->format('Ymd\THis');
        $lines[] = 'DTEND:' . $dtEnd->format('Ymd\THis');
        $lines[] = ics_fold('SUMMARY:' . ics_escape($summary));
        if ($desc !== '') {
            $lines[] = ics_fold('DESCRIPTION:' . ics_escape($desc));
        }
        if ($salle !== '') {
            $lines[] = ics_fold('LOCATION:' . ics_escape($salle));
        }
        if ($annule) {
            $lines[] = 'STATUS:CANCELLED';
        }
        $lines[] = 'END:VEVENT';
    }
}

$seenTodos = array();
foreach ($devoirsLists as $list) {
    foreach ($list as $dv) {
        if (!is_array($dv)) {
            continue;
        }
        $due = projote_infer_date(isset($dv['date']) ? $dv['date'] : '');
        $title = isset($dv['title']) ? $dv['title'] : 'Devoir';
        $descr = isset($dv['description']) ? $dv['description'] : '';
        $done  = !empty($dv['done']);
        $uid   = md5((isset($dv['date']) ? $dv['date'] : '') . $title . $descr) . '@projote-devoir';
        if (isset($seenTodos[$uid])) {
            continue;
        }
        $seenTodos[$uid] = true;

        $lines[] = 'BEGIN:VTODO';
        $lines[] = 'UID:' . $uid;
        $lines[] = 'DTSTAMP:' . $nowUtc;
        if ($due) {
            $lines[] = 'DUE;VALUE=DATE:' . $due->format('Ymd');
        }
        $lines[] = ics_fold('SUMMARY:' . ics_escape('Devoir ' . $title));
        if ($descr !== '') {
            $lines[] = ics_fold('DESCRIPTION:' . ics_escape($descr));
        }
        $lines[] = 'STATUS:' . ($done ? 'COMPLETED' : 'NEEDS-ACTION');
        $lines[] = 'PERCENT-COMPLETE:' . ($done ? '100' : '0');
        $lines[] = 'END:VTODO';
    }
}

$lines[] = 'END:VCALENDAR';

// ── Sortie ──────────────────────────────────────────────────────────────────
header('Content-Type: text/calendar; charset=utf-8');
header('Content-Disposition: inline; filename="projote-' . preg_replace('/[^a-z0-9]/i', '_', $eleve) . '.ics"');
echo implode("\r\n", $lines) . "\r\n";
