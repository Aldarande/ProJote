<?php
/* ProJote — Panneau d'accueil (desktop panel)
 * Copyright (C) 2024-2026 Aldarande
 *
 * Page affichée sous le menu « Accueil » de Jeedom lorsque l'option
 * « Afficher le panneau desktop » est activée dans la gestion du plugin.
 *
 * Mécanisme Jeedom natif :
 *   - info.json : "display": "panel"  → Jeedom propose le toggle displayDesktopPanel.
 *   - index.php ajoute l'entrée de menu si config::byKey('displayDesktopPanel','ProJote') != 0.
 *   - Cette page est incluse comme FRAGMENT dans #div_pageContainer (pas de <html>/<head>).
 *     FontAwesome et jQuery sont déjà chargés par le core.
 *
 * Rôle : vue d'ensemble multi-élèves (un onglet par équipement ProJote actif),
 * alimentée par le blob widget_json mis à jour par le démon (ProJote::getPronoteData()).
 */

require_once dirname(__FILE__) . '/../../../../core/php/core.inc.php';
require_once dirname(__FILE__) . '/../../core/class/ProJote.class.php';

if (!isConnect()) {
    throw new Exception('{{401 - Accès non autorisé}}');
}

// Rassembler les données de chaque équipement ProJote actif et visible.
$students = array();
foreach (eqLogic::byType('ProJote', true) as $eq) {
    if (!$eq->getIsEnable()) {
        continue;
    }
    $data = ProJote::getPronoteData($eq->getId());
    if (!is_array($data)) {
        $data = array();
    }
    $refreshCmd   = $eq->getCmd(null, 'refresh');
    $students[] = array(
        'id'        => $eq->getId(),
        'name'      => $eq->getName(),
        'refreshId' => is_object($refreshCmd) ? $refreshCmd->getId() : 0,
        'data'      => $data,
    );
}
// JSON_HEX_* : empêche toute évasion du contexte <script> (sécurité XSS).
$jsonFlags = JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT;
?>

<style>
    #pj-panel { --pj-green:#94C904; --pj-green-d:#7aa600; padding:6px 4px 40px; }
    #pj-panel .pj-head {
        display:flex; align-items:center; gap:16px;
        background:linear-gradient(135deg, var(--pj-green) 0%, var(--pj-green-d) 100%);
        color:#fff; padding:16px 24px; border-radius:12px; margin-bottom:18px;
        box-shadow:0 4px 14px rgba(122,166,0,.28);
    }
    #pj-panel .pj-head .pj-logo {
        width:54px; height:54px; flex-shrink:0; border-radius:50%; background:#fff;
        display:flex; align-items:center; justify-content:center; overflow:hidden;
    }
    #pj-panel .pj-head .pj-logo img { width:100%; height:100%; object-fit:contain; padding:6px; }
    #pj-panel .pj-head h1 { margin:0; font-size:1.5em; font-weight:700; }
    #pj-panel .pj-head p  { margin:3px 0 0; opacity:.9; font-size:.9em; }

    #pj-panel .pj-tabs { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:18px; }
    #pj-panel .pj-tab {
        padding:7px 18px; border-radius:22px; cursor:pointer; font-weight:600; font-size:.9em;
        border:2px solid var(--pj-green); background:transparent; color:var(--pj-green-d);
        transition:all .15s;
    }
    #pj-panel .pj-tab.active { background:var(--pj-green); color:#fff; }
    #pj-panel .pj-tab:hover:not(.active) { background:rgba(148,201,4,.12); }

    #pj-panel .pj-student { display:none; }
    #pj-panel .pj-student.active { display:block; }

    #pj-panel .pj-grid {
        display:grid; grid-template-columns:repeat(auto-fill, minmax(290px, 1fr));
        gap:16px; margin-bottom:16px;
        /* Sans `start`, une carte repliee s'etire a la hauteur de la plus haute
           de sa rangee : « Devoirs — Aucun devoir » occupait 596 px pour une
           ligne de texte, alignee sur la liste des notes. */
        align-items:start;
    }
    #pj-panel .pj-card {
        border:1px solid rgba(128,128,128,.22); border-radius:12px; overflow:hidden;
        background:rgba(127,127,127,.04); box-shadow:0 2px 6px rgba(0,0,0,.06);
    }
    /* Les huit sections d'un élève portaient toutes le même bandeau vert plein :
       « Identité » pesait autant que « Emploi du temps », et l'œil n'avait aucun
       point d'entrée. Le bandeau courant est maintenant une teinte légère avec
       un filet d'accent ; seule la carte d'identité garde le vert plein. */
    #pj-panel .pj-card-h {
        background:rgba(148,201,4,.16); color:inherit; padding:9px 14px; font-weight:700;
        font-size:.85em; display:flex; align-items:center; gap:8px;
        border-left:3px solid var(--pj-green);
    }
    #pj-panel .pj-card-h i { color:var(--pj-green-d); }
    #pj-panel .pj-card-h-fort {
        background:var(--pj-green); color:#fff; border-left-color:var(--pj-green-d);
    }
    #pj-panel .pj-card-h-fort i { color:#fff; }

    /* Section sans contenu : le bandeau seul, avec la mention à droite. Elle
       occupait jusqu'ici un bloc entier — quatre sections vides sur huit chez un
       élève sans cours du jour, soit près d'un quart de la page à dire qu'il n'y
       a rien. On la garde visible, mais elle ne coûte plus qu'une ligne. */
    #pj-panel .pj-vide {
        margin-left:auto; font-weight:500; font-style:italic; font-size:.92em; opacity:.75;
    }
    #pj-panel .pj-card-repliee { background:transparent; box-shadow:none; }
    #pj-panel .pj-card-b { padding:14px; }

    /* Pièces jointes d'une actualité : disquette opaque quand le fichier est
       sur le disque de Jeedom, grisée quand il est resté chez Pronote. Mêmes
       états que dans le widget, pour qu'on les reconnaisse d'une vue à l'autre. */
    #pj-panel .pj-pj-liste { display:flex; flex-wrap:wrap; gap:5px; margin-top:5px; }
    #pj-panel .pj-pj {
        display:inline-flex; align-items:center; gap:5px; max-width:100%;
        padding:2px 8px; border-radius:11px; font-size:.78em;
        background:rgba(128,128,128,.12); opacity:.55;
        text-decoration:none; color:inherit;
    }
    #pj-panel .pj-pj span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    #pj-panel .pj-pj-prise {
        opacity:1; font-weight:600; background:rgba(39,174,96,.16);
    }
    #pj-panel a.pj-pj-prise:hover { background:rgba(39,174,96,.28); }

    #pj-panel .pj-notif { padding:7px 0; border-bottom:1px solid rgba(128,128,128,.15); }
    #pj-panel .pj-notif:last-child { border-bottom:none; }
    #pj-panel .pj-notif-nonlue { border-left:3px solid var(--pj-green); padding-left:8px; }
    #pj-panel .pj-notif-tete { display:flex; justify-content:space-between; gap:10px; font-size:.78em; opacity:.75; }
    #pj-panel .pj-notif-sujet { font-weight:600; font-size:.9em; margin-top:2px; }
    #pj-panel .pj-span2 { grid-column:span 2; }

    #pj-panel .pj-id { display:flex; align-items:center; gap:16px; }
    #pj-panel .pj-photo {
        width:74px; height:74px; flex-shrink:0; border-radius:50%; object-fit:cover;
        border:3px solid var(--pj-green); background:rgba(148,201,4,.12);
        display:flex; align-items:center; justify-content:center; font-size:1.8em; color:var(--pj-green-d);
    }
    #pj-panel .pj-id h2 { margin:0; font-size:1.2em; color:var(--pj-green-d); }
    #pj-panel .pj-id p  { margin:2px 0; font-size:.85em; opacity:.8; }

    #pj-panel .pj-stats { display:flex; gap:10px; flex-wrap:wrap; }
    #pj-panel .pj-stat {
        flex:1; min-width:72px; text-align:center; padding:10px 6px; border-radius:9px;
        background:rgba(148,201,4,.1);
    }
    #pj-panel .pj-stat .n { display:block; font-size:1.6em; font-weight:800; color:var(--pj-green-d); }
    #pj-panel .pj-stat .l { font-size:.68em; text-transform:uppercase; opacity:.7; }
    #pj-panel .pj-stat.warn .n { color:#e08e00; }
    #pj-panel .pj-stat.bad  .n { color:#c0392b; }

    #pj-panel table.pj-edt { width:100%; border-collapse:collapse; font-size:.85em; }
    #pj-panel table.pj-edt th { background:var(--pj-green); color:#fff; padding:7px 9px; text-align:left; }
    #pj-panel table.pj-edt td { padding:6px 9px; border-bottom:1px solid rgba(128,128,128,.15); }
    #pj-panel table.pj-edt tr:last-child td { border-bottom:none; }
    #pj-panel .pj-cancel { text-decoration:line-through; opacity:.6; }
    #pj-panel .pj-pill {
        display:inline-block; padding:2px 8px; border-radius:9px; font-size:.85em;
        font-weight:600; background:rgba(148,201,4,.16); color:var(--pj-green-d);
    }

    #pj-panel ul.pj-list { list-style:none; padding:0; margin:0; }
    #pj-panel ul.pj-list li { padding:7px 0; border-bottom:1px solid rgba(128,128,128,.15); }
    #pj-panel ul.pj-list li:last-child { border-bottom:none; }
    #pj-panel .pj-note { display:flex; justify-content:space-between; align-items:center; }
    #pj-panel .pj-note .v { font-size:1.15em; font-weight:800; color:var(--pj-green-d); }
    #pj-panel .pj-note .meta { font-size:.78em; opacity:.65; }
    #pj-panel .pj-hw-done { color:#27ae60; }
    #pj-panel .pj-hw-todo { color:#e08e00; }

    #pj-panel .pj-ical {
        display:inline-flex; align-items:center; gap:7px; padding:8px 14px;
        background:var(--pj-green); color:#fff; border-radius:6px; text-decoration:none; font-size:.88em;
    }
    #pj-panel .pj-ical:hover { background:var(--pj-green-d); color:#fff; }
    #pj-panel .pj-empty { opacity:.55; font-style:italic; text-align:center; padding:16px; }
    #pj-panel .pj-refresh { float:right; }
</style>

<div id="pj-panel">
    <div class="pj-head">
        <div class="pj-logo"><img src="plugins/ProJote/plugin_info/ProJote_icon.png" alt="ProJote" onerror="this.parentNode.innerHTML='<i class=&quot;fas fa-graduation-cap&quot; style=&quot;color:#7aa600&quot;></i>'"></div>
        <div style="flex:1;">
            <h1>ProJote</h1>
            <p>{{Vue d'ensemble des élèves}}</p>
        </div>
        <a class="btn btn-default btn-sm pj-refresh" id="pj-refresh-all" title="{{Actualiser depuis Pronote}}">
            <i class="fas fa-sync-alt"></i> {{Actualiser}}
        </a>
    </div>

    <div class="pj-tabs" id="pj-tabs"></div>
    <div id="pj-students"></div>
</div>

<script>
(function () {
    var STUDENTS = <?php echo json_encode($students, $jsonFlags); ?>;

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    function fmtH(h) { return h ? String(h).slice(0, 5) : '--'; }
    function asArray(v) { return Array.isArray(v) ? v : []; }

    /* Rend une carte. `corps` vide → carte repliée sur son bandeau, la mention
       `vide` s'affichant à droite du titre. C'est ce qui évite qu'une section
       sans contenu coûte autant qu'une section pleine. */
    function carte(icone, titre, corps, vide, suffixeTitre, classes) {
        var replie = !corps;
        return '<div class="pj-card' + (replie ? ' pj-card-repliee' : '') +
               (classes ? ' ' + classes : '') + '">' +
               '<div class="pj-card-h"><i class="fas ' + icone + '"></i> ' + titre +
               (suffixeTitre || '') +
               (replie ? '<span class="pj-vide">' + vide + '</span>' : '') +
               '</div>' +
               (replie ? '' : '<div class="pj-card-b">' + corps + '</div>') +
               '</div>';
    }

    function edtTable(courses) {
        courses = asArray(courses);
        if (!courses.length) return '';
        var h = '<table class="pj-edt"><thead><tr><th>{{Horaire}}</th><th>{{Cours}}</th><th>{{Salle}}</th></tr></thead><tbody>';
        courses.forEach(function (c) {
            var cancel = c.annulation ? ' class="pj-cancel"' : '';
            h += '<tr' + cancel + '>';
            h += '<td>' + esc(fmtH(c.heure)) + ' - ' + esc(fmtH(c.heure_fin)) + '</td>';
            h += '<td><span class="pj-pill">' + esc(c.cours || '--') + '</span>' + (c.annulation ? ' <small>(annulé)</small>' : '') + '</td>';
            h += '<td>' + esc(c.salle || '--') + '</td>';
            h += '</tr>';
        });
        return h + '</tbody></table>';
    }

    function notesList(notes) {
        notes = asArray(notes);
        if (!notes.length) return '';
        var h = '<ul class="pj-list">';
        notes.slice(0, 10).forEach(function (n) {
            var mat = (n.cours || '–'); if (mat.indexOf(' > ') !== -1) mat = mat.split(' > ').pop();
            h += '<li class="pj-note"><div><div style="font-weight:600">' + esc(mat) + '</div>' +
                 '<div class="meta">' + esc((n.date || '').slice(0, 5)) +
                 (n.moyenne_classe ? ' · cl. ' + esc(n.moyenne_classe) : '') + '</div></div>' +
                 '<div class="v">' + esc(n.note || '?') + (n.sur ? '<small>/' + esc(n.sur) + '</small>' : '') + '</div></li>';
        });
        return h + '</ul>';
    }

    function homeworkList(d) {
        var list = asArray(d.devoirs).concat(asArray(d.devoirs_demain));
        if (!list.length) return '';
        var h = '<ul class="pj-list">';
        list.slice(0, 15).forEach(function (dv) {
            var done = !!dv.done;
            h += '<li><i class="fas ' + (done ? 'fa-check-circle pj-hw-done' : 'fa-circle pj-hw-todo') + '"></i> ' +
                 '<strong>' + esc(dv.title || '–') + '</strong>' +
                 (dv.description ? '<div class="meta" style="font-size:.8em;opacity:.7">' + esc(dv.description) + '</div>' : '') +
                 '</li>';
        });
        return h + '</ul>';
    }

    function punitionsList(list) {
        list = asArray(list);
        if (!list.length) return '';
        var h = '<ul class="pj-list">';
        list.slice(0, 10).forEach(function (p) {
            h += '<li><strong>' + esc(p.nature || p.type || 'Punition') + '</strong>' +
                 (p.raison ? ' — ' + esc(p.raison) : '') +
                 (p.date ? ' <small class="meta">(' + esc(p.date) + ')</small>' : '') + '</li>';
        });
        return h + '</ul>';
    }

    /* Observations, défauts de carnet et mesures conservatoires. Collectés
       depuis la v1.7.0, affichés dans le widget depuis la v1.7.1, ils
       manquaient encore ici. */
    function carnetList(list) {
        list = asArray(list);
        if (!list.length) return '';
        var h = '<ul class="pj-list">';
        list.slice(0, 10).forEach(function (e) {
            var jour = String(e.date || '').split(' ')[0];
            var meme = String(e.libelle || '').toLowerCase() === String(e.categorie || '').toLowerCase();
            h += '<li><strong>' + esc(e.categorie || '--') + '</strong>' +
                 (e.libelle && !meme ? ' — ' + esc(e.libelle) : '') +
                 (jour ? ' <small class="meta">(' + esc(jour) + ')</small>' : '') + '</li>';
        });
        return h + '</ul>';
    }

    /* Actualités publiées par l'établissement, avec les fichiers joints.
       La disquette opaque ouvre le fichier rapatrié ; grisée, elle dit qu'il
       existe chez Pronote sans avoir été demandé. */
    function notificationsList(list, eqId) {
        list = asArray(list);
        if (!list.length) return '';
        var racine = 'plugins/ProJote/data/' + encodeURIComponent(eqId) + '/file/';
        var h = '';
        list.slice(0, 10).forEach(function (n) {
            var nonlue = (n.lu === false || n.lu === 0);
            var pj = asArray(n.pieces_jointes).map(function (p) {
                var nom = esc(p.nom || '?');
                if (p.recuperee && p.fichier) {
                    return '<a class="pj-pj pj-pj-prise" target="_blank" rel="noopener" href="' +
                        racine + encodeURIComponent(p.fichier) +
                        '" title="{{Enregistre par ProJote - ouvrir}}">' +
                        '<i class="fas fa-save"></i><span>' + nom + '</span></a>';
                }
                return '<span class="pj-pj" title="' +
                    (p.lien ? '{{Lien externe, non telecharge}}' : '{{Non rapatrie}}') + '">' +
                    '<i class="fas ' + (p.lien ? 'fa-link' : 'fa-save') + '"></i>' +
                    '<span>' + nom + '</span></span>';
            }).join('');
            h += '<div class="pj-notif' + (nonlue ? ' pj-notif-nonlue' : '') + '">' +
                 '<div class="pj-notif-tete"><span>' + esc(n.auteur || '—') + '</span>' +
                 '<span>' + esc(n.creation || '') + '</span></div>' +
                 '<div class="pj-notif-sujet">' + esc(n.sujet || '') + '</div>' +
                 (pj ? '<div class="pj-pj-liste">' + pj + '</div>' : '') +
                 '</div>';
        });
        return h;
    }

    /* Ce que ProJote a repéré lui-même : nouvelle note, nouvelle absence,
       matière en baisse. À distinguer du Carnet, qui vient de Pronote. */
    function evenementsProjoteList(list) {
        list = asArray(list);
        if (!list.length) return '';
        var h = '<ul class="pj-list">';
        list.slice(0, 15).forEach(function (e) {
            h += '<li><small class="meta">' + esc(e.date || '') + '</small> ' +
                 esc(e.label || '') + '</li>';
        });
        return h + '</ul>';
    }

    function renderStudent(s) {
        var d = s.data || {};
        var h = '<div class="pj-grid">';

        // Identité
        h += '<div class="pj-card pj-span2"><div class="pj-card-h pj-card-h-fort"><i class="fas fa-user-graduate"></i> {{Identité}}</div>';
        h += '<div class="pj-card-b"><div class="pj-id">';
        if (d.photo) {
            h += '<img class="pj-photo" src="' + esc(d.photo) + '" onerror="this.outerHTML=\'<div class=&quot;pj-photo&quot;><i class=&quot;fas fa-user-graduate&quot;></i></div>\'">';
        } else {
            h += '<div class="pj-photo"><i class="fas fa-user-graduate"></i></div>';
        }
        h += '<div><h2>' + esc(d.eleve || s.name) + '</h2>' +
             '<p><i class="fas fa-chalkboard"></i> ' + esc(d.classe || '--') + '</p>' +
             '<p><i class="fas fa-school"></i> ' + esc(d.etablissement || '--') + '</p></div>';
        h += '</div></div></div>';

        // Statistiques
        h += '<div class="pj-card"><div class="pj-card-h"><i class="fas fa-chart-bar"></i> {{Statistiques}}</div>';
        h += '<div class="pj-card-b"><div class="pj-stats">' +
             '<div class="pj-stat warn"><span class="n">' + (d.nb_absences || 0) + '</span><span class="l">{{Absences}}</span></div>' +
             '<div class="pj-stat warn"><span class="n">' + (d.nb_retards || 0) + '</span><span class="l">{{Retards}}</span></div>' +
             '<div class="pj-stat bad"><span class="n">' + (d.nb_punitions || 0) + '</span><span class="l">{{Punitions}}</span></div>' +
             '<div class="pj-stat warn"><span class="n">' + (d.nb_evenements || 0) + '</span><span class="l">{{Carnet}}</span></div>' +
             '</div></div></div>';

        // Prochain DS
        if (d.prochain_DS_matiere) {
            h += '<div class="pj-card"><div class="pj-card-h"><i class="fas fa-pen"></i> {{Prochain contrôle}}</div>';
            h += '<div class="pj-card-b"><strong>' + esc(d.prochain_DS_matiere) + '</strong>' +
                 (d.prochain_DS_date ? '<div class="meta">' + esc(d.prochain_DS_date) + '</div>' : '') +
                 (d.prochain_DS_dans_jours != null ? '<span class="pj-pill" style="margin-top:6px;display:inline-block">{{dans}} ' + esc(d.prochain_DS_dans_jours) + ' {{j}}</span>' : '') +
                 '</div></div>';
        }
        h += '</div>'; // grid

        // EDT aujourd'hui puis prochain jour
        h += '<div style="margin-bottom:16px">' +
             carte('fa-calendar-day', '{{Emploi du temps — aujourd\'hui}}',
                   edtTable(d.edt_aujourdhui), '{{Pas de cours}}') + '</div>';

        var quand = d.edt_prochainjour_date
            ? ' <small style="opacity:.85">(' + esc(d.edt_prochainjour_date) + ')</small>' : '';
        h += '<div style="margin-bottom:16px">' +
             carte('fa-calendar-alt', '{{Emploi du temps — prochain jour}}',
                   edtTable(d.edt_prochainjour), '{{Pas de cours}}', quand) + '</div>';

        // Notes / Devoirs / Punitions / Carnet
        h += '<div class="pj-grid">';
        h += carte('fa-star', '{{Dernières notes}}', notesList(d.notes), '{{Aucune note}}');
        h += carte('fa-book', '{{Devoirs}}', homeworkList(d), '{{Aucun devoir}}');
        h += carte('fa-exclamation-triangle', '{{Punitions}}', punitionsList(d.punitions), '{{Aucune punition}}');
        h += carte('fa-clipboard-list', '{{Carnet}}', carnetList(d.evenements), '{{Aucun évènement}}');
        h += carte('fa-bullhorn', '{{Notifications}}',
                   notificationsList(d.notifications, s.id), '{{Aucune notification}}');
        h += carte('fa-bell', '{{Évènements ProJote}}',
                   evenementsProjoteList(d.events), '{{Aucun évènement}}');

        // ICAL
        if (d.URL_Ical || d.ical) {
            var ical = d.URL_Ical || d.ical;
            h += '<div class="pj-card"><div class="pj-card-h"><i class="fas fa-calendar-check"></i> {{Calendrier ICAL}}</div>' +
                 '<div class="pj-card-b"><a class="pj-ical" href="' + esc(ical) + '" target="_blank"><i class="fas fa-download"></i> {{S\'abonner}}</a></div></div>';
        }
        h += '</div>'; // grid

        return h;
    }

    var tabs = document.getElementById('pj-tabs');
    var panes = document.getElementById('pj-students');

    if (!STUDENTS.length) {
        panes.innerHTML = '<div class="alert alert-info"><i class="fas fa-info-circle"></i> ' +
            "{{Aucun équipement ProJote actif. Ajoutez un élève dans Plugins → Organisation → ProJote.}}" + '</div>';
        document.getElementById('pj-refresh-all').style.display = 'none';
        return;
    }

    var tabsHtml = '', panesHtml = '';
    STUDENTS.forEach(function (s, i) {
        var label = (s.data && s.data.eleve) ? s.data.eleve : s.name;
        tabsHtml  += '<div class="pj-tab' + (i === 0 ? ' active' : '') + '" data-i="' + i + '">' + esc(label) + '</div>';
        panesHtml += '<div class="pj-student' + (i === 0 ? ' active' : '') + '" data-i="' + i + '">' + renderStudent(s) + '</div>';
    });
    tabs.innerHTML = tabsHtml;
    panes.innerHTML = panesHtml;

    tabs.addEventListener('click', function (e) {
        var t = e.target.closest('.pj-tab'); if (!t) return;
        var i = t.getAttribute('data-i');
        tabs.querySelectorAll('.pj-tab').forEach(function (x) { x.classList.remove('active'); });
        panes.querySelectorAll('.pj-student').forEach(function (x) { x.classList.remove('active'); });
        t.classList.add('active');
        panes.querySelector('.pj-student[data-i="' + i + '"]').classList.add('active');
    });

    // Actualiser : déclenche la commande refresh de chaque élève (si jeedom dispo), puis recharge.
    document.getElementById('pj-refresh-all').addEventListener('click', function () {
        var btn = this;
        btn.querySelector('i').classList.add('fa-spin');
        var ids = STUDENTS.map(function (s) { return s.refreshId; }).filter(Boolean);
        if (typeof jeedom !== 'undefined' && jeedom.cmd && ids.length) {
            var pending = ids.length;
            ids.forEach(function (id) {
                jeedom.cmd.execute({ id: id, error: function () {}, success: function () {} });
            });
            setTimeout(function () { window.location.reload(); }, 4000);
        } else {
            window.location.reload();
        }
    });
})();
</script>
