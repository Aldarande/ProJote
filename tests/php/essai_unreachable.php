<?php
/* ProJote — plugin Jeedom pour Pronote
 * Copyright (C) 2024-2026 Aldarande
 * Licensed under the GNU Affero General Public License v3 or later.
 * See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.
 */

/**
 * essai_unreachable.php — Essai hors Jeedom de la temporisation des messages
 * « Pronote injoignable » (ProJote::declareUnreachable / clearUnreachable).
 *
 * Le dépôt n'a pas d'outillage de test PHP : plutôt que de renoncer, on pose
 * des doublures minimales de `cache`, `message`, `log` et de l'équipement, et
 * on vérifie ce qui compte pour l'utilisateur — un seul message quand
 * l'incident dure, aucun quand il passe, et son effacement au premier relevé
 * réussi.
 *
 * Les deux méthodes sont extraites du fichier de classe plutôt qu'incluses :
 * ProJote.class.php étend eqLogic et tire tout le cœur de Jeedom avec lui.
 *
 * Lancement :
 *     php tests/php/essai_unreachable.php [chemin/vers/ProJote.class.php]
 *
 * Le test pytest `test_php_unreachable.py` l'exécute quand `php` est
 * disponible ; la CI l'appelle depuis le job « Lint PHP ».
 */

function __($t, $f = '') { return $t; }

class _CacheObj
{
    public $value;
    public function __construct($v) { $this->value = $v; }
    public function getValue($default = '') { return $this->value === null ? $default : $this->value; }
}

class cache
{
    public static $store = array();
    public static function byKey($key)
    {
        return new _CacheObj(isset(self::$store[$key]) ? self::$store[$key] : null);
    }
    public static function set($key, $value, $lifetime = 0)
    {
        self::$store[$key] = $value;
    }
}

class message
{
    public static $msgs = array();
    public static function add($plugin, $msg, $action = '', $logicalId = '')
    {
        self::$msgs[] = array('plugin' => $plugin, 'message' => $msg, 'logicalId' => $logicalId);
    }
    public static function removeAll($plugin = '', $logicalId = '')
    {
        $restant = array();
        foreach (self::$msgs as $m) {
            if ($m['plugin'] === $plugin && $m['logicalId'] === $logicalId) continue;
            $restant[] = $m;
        }
        self::$msgs = $restant;
    }
    public static function byPluginLogicalId($plugin, $logicalId) { return null; }
}

class log
{
    public static $lignes = array();
    public static function add($plugin, $level, $msg, $logicalId = '')
    {
        self::$lignes[] = array('level' => $level, 'msg' => $msg);
    }
}

class _FauxEq
{
    private $id;
    public function __construct($id) { $this->id = $id; }
    public function getId() { return $this->id; }
    public function getHumanName() { return '[Salon][Équipement ' . $this->id . ']'; }
}

$cheminClasse = isset($argv[1])
    ? $argv[1]
    : dirname(__FILE__) . '/../../core/class/ProJote.class.php';
if (!is_readable($cheminClasse)) {
    fwrite(STDERR, "Fichier de classe illisible : $cheminClasse\n");
    exit(2);
}
$source = file_get_contents($cheminClasse);
$debut = strpos($source, '  const UNREACHABLE_MESSAGE_PREFIX');
$fin = strpos($source, '  /**', strpos($source, 'public static function clearUnreachable'));
if ($debut === false || $fin === false) {
    fwrite(STDERR, "Méthodes introuvables dans le fichier de classe\n");
    exit(2);
}
$corps = substr($source, $debut, $fin - $debut);
eval('class ProJote { ' . $corps . ' }');

$echecs = 0;
function verifie($libelle, $condition)
{
    global $echecs;
    if ($condition) {
        echo "  ok   $libelle\n";
    } else {
        echo "  ÉCHEC $libelle\n";
        $echecs++;
    }
}

$eq = new _FauxEq(767);

echo "Trois relevés injoignables ne créent qu'un message :\n";
ProJote::declareUnreachable($eq, 'Pronote injoignable (délai dépassé) — nouvel essai au prochain cycle');
verifie('relevé 1 : aucun message', count(message::$msgs) === 0);
ProJote::declareUnreachable($eq, 'Pronote injoignable (délai dépassé)');
verifie('relevé 2 : aucun message', count(message::$msgs) === 0);
ProJote::declareUnreachable($eq, 'Pronote injoignable (délai dépassé)');
verifie('relevé 3 : un message', count(message::$msgs) === 1);
ProJote::declareUnreachable($eq, 'Pronote injoignable (délai dépassé)');
ProJote::declareUnreachable($eq, 'Pronote injoignable (délai dépassé)');
verifie('relevés 4 et 5 : toujours un seul message', count(message::$msgs) === 1);
verifie('logicalId stable', message::$msgs[0]['logicalId'] === 'unreachable_767');
verifie('le message ne parle pas de QR code',
    stripos(message::$msgs[0]['message'], 'qr') === false
    && stripos(message::$msgs[0]['message'], 'expir') === false);
$niveaux = array_unique(array_column(log::$lignes, 'level'));
verifie('journal en avertissement uniquement', $niveaux === array('warning'));

echo "Le relevé réussi suivant efface tout :\n";
verifie('clearUnreachable rend true', ProJote::clearUnreachable($eq) === true);
verifie('plus aucun message', count(message::$msgs) === 0);
verifie('clearUnreachable est idempotent', ProJote::clearUnreachable($eq) === false);

echo "Un nouvel incident repart de zéro :\n";
ProJote::declareUnreachable($eq, 'Pronote injoignable');
ProJote::declareUnreachable($eq, 'Pronote injoignable');
verifie('deux relevés : aucun message', count(message::$msgs) === 0);
ProJote::declareUnreachable($eq, 'Pronote injoignable');
verifie('troisième relevé : un message', count(message::$msgs) === 1);

echo "Six heures d'incident préviennent sans attendre trois relevés :\n";
cache::$store = array();
message::$msgs = array();
cache::set('ProJote::unreachable::767', array(
    'count' => 1, 'since' => time() - 21700, 'notified' => false,
));
ProJote::declareUnreachable($eq, 'Pronote injoignable');
verifie('un message dès le relevé suivant', count(message::$msgs) === 1);

echo "Deux équipements ne partagent ni compteur ni message :\n";
cache::$store = array();
message::$msgs = array();
$autre = new _FauxEq(42);
for ($i = 0; $i < 3; $i++) ProJote::declareUnreachable($eq, 'x');
verifie('767 prévenu', count(message::$msgs) === 1);
ProJote::declareUnreachable($autre, 'x');
verifie('42 pas encore prévenu', count(message::$msgs) === 1);
ProJote::clearUnreachable($eq);
verifie('effacer 767 ne touche pas 42', ProJote::clearUnreachable($autre) === true);

echo $echecs === 0 ? "\nTout est vert.\n" : "\n$echecs échec(s).\n";
exit($echecs === 0 ? 0 : 1);
