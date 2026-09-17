# Audit de sécurité — ProJote

**Date :** juin 2026 · **Périmètre :** version 1.1.0 (branche `works`) · **Auditeur :** revue assistée (Claude, Anthropic)

**Fichiers analysés :** `core/ajax/ProJote.ajax.php`, `core/php/jeeProJote.php`, `core/php/calendar.php`, `core/class/ProJote.class.php`, `resources/ProJoted/ProJoted.py`, `resources/ProJoted/LoginConnect.py`, `resources/ProJoted/QRConnect.py`, `desktop/js/ProJote.js`, `resources/post-install.sh`.

## Score global : **88 / 100**

Le plugin présente une posture de sécurité solide : authentification systématique des endpoints
(`jeedom::apiAccess` / `isConnect('admin')`), whitelist d'actions AJAX, échappement shell
(`escapeshellarg`) sur toutes les commandes, validation MIME par contenu des uploads, échappement
HTML côté widget (`esc()` JS / `html.escape` Python), masquage de l'apikey dans les logs du démon.
Les findings MEDIUM identifiés lors de cet audit ont été **corrigés dans la même passe** (P2a, P2b).

---

## Findings

### CRITICAL — néant

### HIGH — néant

### MEDIUM

#### M1 — Apikey transmise en GET (access logs) — **CORRIGÉ**
- **CWE-598** (Information Exposure Through Query Strings) · OWASP A09:2021
- **Fichier :** `resources/ProJoted/ProJoted.py` (`send_jeedom_message`)
- L'apikey Jeedom partait en paramètre de query string GET vers
  `message.action.php` → persistée en clair dans les access logs du serveur web.

```python
# Vulnérable
response = requests.get(message_action_url, params=params, timeout=5)
# Corrigé — apikey dans le corps POST (init()/$_REQUEST côté Jeedom accepte les deux)
response = requests.post(message_action_url, data=params, timeout=5)
```

#### M2 — Logging DEBUG forcé à l'import — **CORRIGÉ**
- **CWE-532** (Insertion of Sensitive Information into Log File)
- **Fichier :** `resources/ProJoted/ProJoted.py` (en-tête)
- `logging.basicConfig(level=DEBUG)` était câblé en dur avant le parsing de `--loglevel` :
  tout log émis entre l'import et la reconfiguration partait en DEBUG sur stdout, avec un
  formatter **sans** le masquage d'apikey (présent uniquement dans `jeedom_utils.set_log_level`).

```python
# Vulnérable
logging.basicConfig(level=logging.DEBUG, ...)
# Corrigé — WARNING initial, niveau définitif appliqué par set_log_level(--loglevel)
logging.basicConfig(level=logging.WARNING, ...)
```

#### M3 — AES-256-CBC sans authentification (chiffrement du mot de passe Pronote) — **CORRIGÉ (v1.7.0)**

> **Rectification de l'audit.** La recommandation ci-dessous prévoyait un « re-chiffrement
> transparent au premier accès ». La relecture faite pour l'appliquer a montré que la prémisse
> était fausse : **aucun secret n'est conservé sous ce chiffrement.** `my_encrypt()` n'est appelé
> qu'à un seul endroit — `ProJote.ajax.php`, pour passer le mot de passe au script de validation
> en argument de ligne de commande — et le chiffré ne vit que le temps d'une requête. Le secret
> gardé en base (`Token_password`) est chiffré par le cœur de Jeedom via `$_encryptConfigKey`,
> pas par ce code. Il n'y avait donc rien à migrer, et le passage à GCM s'est fait sans reprise.
>
> La même relecture a montré que `ProJoted.my_decrypt()` — la fonction visée par le finding L4 —
> n'était atteignable que depuis `Connect()` et `Connectparent()`, **que rien n'appelait**. Le
> correctif L4 portait donc sur du code mort côté démon ; il reste entier pour `LoginConnect`, où
> le défaut était bien atteint à chaque validation par identifiants. Les trois fonctions ont été
> supprimées en v1.7.0, et le déchiffrement ne vit plus qu'à un seul endroit.

**Traitement retenu :** AES-256-GCM (IV de 12 octets, tag authentifié) pour le transport
PHP → Python. Une charge altérée est refusée des deux côtés, là où CBC la déchiffrait en octets
quelconques que rien ne distinguait d'un mot de passe. L'ancienne enveloppe reste lue au
déchiffrement, le temps qu'une mise à jour en cours ne laisse pas un démon d'avant face à un
chiffré d'après. Couvert par `tests/test_durcissement_secrets.py`, et éprouvé de bout en bout
sur le compte de démonstration (chiffrement PHP réel → validation Python réelle).

<details><summary>Constat d'origine (juin 2026)</summary>

- **CWE-353** (Missing Support for Integrity Check) · OWASP A02:2021
- **Fichiers :** `ProJote.class.php` (`my_encrypt`/`my_decrypt`), `ProJoted.py`, `LoginConnect.py`
- Le mot de passe Pronote est chiffré en AES-256-CBC **sans MAC/AEAD** : un ciphertext altéré
  n'est pas détecté (malléabilité). **Dérivation de clé auditée et jugée correcte** : la clé est
  `SHA-256(apikey Jeedom)` — l'apikey est un secret *aléatoire à forte entropie* généré par le
  core, pas une valeur prévisible (ID/constante/nom) ; PBKDF2 n'apporterait un gain que pour un
  secret faible. **Exploitabilité très faible** : chiffrement/déchiffrement strictement locaux
  (BDD Jeedom ↔ démon sur la même machine), aucun oracle de padding exposé à un attaquant réseau.
- **Recommandation (prochaine version majeure) :** migrer vers AES-256-GCM (IV 12 o, tag
  authentifié) avec re-chiffrement transparent au premier accès (déchiffrer ancien format →
  rechiffrer nouveau).

</details>

### LOW

#### L1 — Fallback silencieux du déchiffrement (LoginConnect) — **CORRIGÉ (v1.4.7)**
- `LoginConnect.my_decrypt` retournait la **donnée brute** en cas d'échec de déchiffrement
  (« fallback compatibilité ») : le ciphertext partait tel quel comme mot de passe vers
  Pronote. Échec de connexion garanti, et muet — l'utilisateur ressaisissait indéfiniment
  des identifiants pourtant corrects.
- Lève désormais `DechiffrementImpossible` (`pronote_errors.py`), remontée jusqu'au
  gestionnaire global qui sort sur le **code dédié 9**. `ProJote.ajax.php` le traduit en
  « le mot de passe a été chiffré avec une autre clé API, ressaisissez-le ».

#### L2 — AJAX : type d'équipement non vérifié — **CORRIGÉ (v1.4.7)**
- `ChangeEnfant` / `GetConfig` / `GetWidgetData` (et les deux actions photo) chargeaient
  `eqLogic::byId(init('eqlogic'))` sans vérifier `getEqType_name() === 'ProJote'`.
- Toutes passent désormais par `projoteChargerEquipement()`, qui applique `intval()`,
  vérifie le type et refuse le reste. Les deux lectures d'UUID, qui doivent tolérer un
  équipement pas encore enregistré, portent le contrôle en ligne.

#### L3 — Démon : identifiants d'équipement non assainis dans les chemins — **CORRIGÉ (v1.4.7)**
- `os.path.join(_data_dir, str(eqLogicId))` — `eqLogicId` provenait des messages socket.
- `_id_equipement()` / `_dossier_equipement()` (`ProJoted.py`) et `token_secours._chemin()`
  **refusent** ce qui n'est pas un entier au lieu de le nettoyer : « ../7 » ne devient pas
  discrètement « 7 ». Les cinq compositions de chemin du démon y passent.

#### L4 — `my_decrypt` (démon) termine le processus sur échec — **CORRIGÉ (v1.4.7)**
- `exit(1)` dans `ProJoted.my_decrypt` : un seul payload indéchiffrable tuait tout le démon,
  donc la collecte de tous les autres enfants de l'installation.
- Lève `DechiffrementImpossible` ; `Connect()` et `Connectparent()` la nomment et rendent
  `None` pour cet équipement seul. Le cycle continue pour les autres.

### INFO

- **I1 — calendar.php :** l'URL d'abonnement iCal contient l'apikey (inhérent au modèle
  d'abonnement par URL). `jeedom::apiAccess` est bien appliqué. Servir en HTTPS ; régénérer la
  clé API du plugin en cas de fuite de l'URL.
- **I2 — Dépendances épinglées :** `requirements.txt` fige les versions (dont
  `pycryptodome==3.20.0`) — penser à un rafraîchissement périodique (suivi CVE).
- **I3 — Bonnes pratiques relevées :** masquage de l'apikey dans le formatter de logs du démon ;
  `escapeshellarg` sur tous les `exec()` ; whitelist `ajax::init([...])` ; upload photo validé
  par contenu (finfo) + taille + `intval(eqlogic)` ; mots de passe jamais loggés (commande de
  validation non tracée) ; `jeedom::apiAccess` sur les deux endpoints HTTP (`jeeProJote.php`,
  `calendar.php`) ; socket démon lié à 127.0.0.1 + apikey obligatoire ; widget : échappement
  systématique (`esc()` JS, `html.escape` Python côté HTML pré-rendu).
- **I4 — post-install.sh :** `set -u`, chemins quotés, pas d'`eval`, échecs pip bloquants —
  conforme.

---

## Synthèse

| Sévérité | Total | Corrigés | Acceptés/documentés | Ouverts |
|---|---|---|---|---|
| CRITICAL | 0 | — | — | 0 |
| HIGH | 0 | — | — | 0 |
| MEDIUM | 3 | 3 (M1, M2, M3) | 0 | 0 |
| LOW | 4 | 4 (L1–L4, v1.4.7) | 0 | 0 |
| INFO | 4 | — | — | — |

**État :** tous les findings sont traités. L1–L4 en v1.4.7, M3 en v1.7.0, l'ensemble couvert par
`tests/test_durcissement_secrets.py`.

**Deux enseignements de cette campagne**, qui valent plus que les correctifs eux-mêmes :

1. **Un finding peut viser du code mort.** L4 décrivait un `exit(1)` réel, dans une fonction que
   rien n'appelait. L'audit avait lu le code, pas les chemins d'exécution. Vérifier l'accessibilité
   avant d'estimer une sévérité.
2. **Le défaut le plus grave n'était dans aucun finding.** Le remplissage PKCS#7 n'était pas
   vérifié au déchiffrement : avec une mauvaise clé, l'opération rendait une chaîne vide quinze
   fois sur seize, en silence. Le plugin envoyait alors un mot de passe vide à Pronote et
   annonçait « identifiants incorrects ». Il a été trouvé en **éprouvant** les correctifs sur un
   compte réel, pas en relisant le code — les deux findings qui l'encadraient ne se
   déclenchaient d'ailleurs jamais à cause de lui.
