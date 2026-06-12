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

#### M3 — AES-256-CBC sans authentification (chiffrement du mot de passe Pronote) — **ACCEPTÉ / DOCUMENTÉ**
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

### LOW

#### L1 — Fallback silencieux du déchiffrement (LoginConnect)
- `LoginConnect.my_decrypt` retourne la **donnée brute** en cas d'échec de déchiffrement
  (« fallback compatibilité ») : un ciphertext corrompu serait envoyé tel quel comme mot de
  passe à Pronote. Échec de connexion garanti mais comportement silencieux.
  *Recommandation : logguer en ERROR et échouer explicitement.*

#### L2 — AJAX : type d'équipement non vérifié
- `ChangeEnfant` / `GetConfig` / `GetWidgetData` chargent `eqLogic::byId(init('eqlogic'))`
  sans vérifier `getEqType_name() === 'ProJote'`. Mitigé : endpoints réservés admin
  (`isConnect('admin')`). *Recommandation : ajouter le contrôle de type (défense en profondeur).*

#### L3 — Démon : identifiants d'équipement non assainis dans les chemins
- `os.path.join(_data_dir, str(eqLogicId))` — `eqLogicId` provient des messages socket.
  Mitigé : le socket exige l'apikey (`message.get("apikey") != _apikey` → rejet) et n'écoute
  que sur 127.0.0.1. *Recommandation : `int(eqLogicId)` avant usage dans un chemin.*

#### L4 — `my_decrypt` (démon) termine le processus sur échec
- `exit(1)` dans `ProJoted.my_decrypt` : un seul payload indéchiffrable tue tout le démon
  (disponibilité multi-équipements). *Recommandation : lever une exception traitée par
  l'appelant, marquer l'équipement en erreur, continuer.*

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
| MEDIUM | 3 | 2 (M1, M2) | 1 (M3) | 0 |
| LOW | 4 | 0 | 0 | 4 (durcissements recommandés) |
| INFO | 4 | — | — | — |

**Plan recommandé :** traiter L1–L4 dans une prochaine version corrective ; planifier la
migration AES-GCM (M3) pour une version majeure avec migration transparente des secrets.
