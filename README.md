# 📚 ProJote - Plugin JEEDOM Pronote

![Version](https://img.shields.io/badge/version-0.8-blue)
![License](https://img.shields.io/badge/license-AGPL-green)
![Jeedom](https://img.shields.io/badge/Jeedom-4.3+-orange)

**ProJote** est un plugin JEEDOM qui vous permet de **récupérer automatiquement les informations de votre compte Pronote** directement dans Jeedom. Consultez vos notes, emplois du temps, devoirs, absences et bien plus encore!

---

## 🎯 Fonctionnalités

✅ **Intégration Pronote complète**
- Récupération des notes et moyennes
- Emploi du temps (EDT) du jour et du lendemain
- Liste des devoirs et travail à faire
- Absences et retards
- Punitions et sanctions
- Notifications

✅ **Gestion multi-comptes**
- Support des comptes élèves
- Support des comptes parents
- Gestion des enfants multiples

✅ **Modes de connexion flexibles**
- Connexion par QR code
- Connexion par identifiants (CAS, URL)
- Gestion sécurisée des tokens

✅ **Automatisation**
- Synchronisation périodique configurable
- Cron toutes les heures (horaire d'école)
- Commandes d'actualisation manuelles
- Webhooks pour intégrations externes

✅ **Multi-plateforme**
- Compatible Jeedom Smart, Luna, Atlas
- Support Raspberry Pi, Docker, DIY
- Interface mobile responsive

---

## 📋 Prérequis

- **Jeedom 4.3** minimum
- **Python 3.7+** avec environnement virtuel
- **PronotePy** (installé automatiquement)
- **PHP 7.4+**
- Port réseau **55369** disponible (configurable)
- Compte **Pronote** actif (élève ou parent)

---

## 🚀 Installation

### Via le Market Jeedom (Recommandé)

1. Allez dans **Plugins** → **Gestion des plugins**
2. Cliquez sur **Ajouter** → **ProJote**
3. Cliquez sur **Installer**
4. Attendez la fin de l'installation

### Installation Manuelle

```bash
# Cloner le repository
cd /var/www/html/plugins
git clone https://github.com/aldarande/ProJote.git ProJote
cd ProJote

# Installation des dépendances Python
python3 -m venv resources/python_venv
source resources/python_venv/bin/activate
pip install -r requirements.txt

# Permissions
sudo chown www-data:www-data -R /var/www/html/plugins/ProJote/
```

---

## ⚙️ Configuration

### 1. Configuration Globale du Plugin

1. Allez dans **Plugins** → **Organisation** → **ProJote**
2. Cliquez sur l'onglet **Configuration**

| Paramètre | Description | Par défaut |
|-----------|-------------|-----------|
| **Port du Démon** | Port socket pour communication | 55369 |
| **Niveau de log** | Niveau de verbosité (debug/info/warning) | info |

### 2. Création d'un Équipement

#### Option A : Par QR Code (Recommandé)

1. Allez dans **Plugins** → **Organisation** → **ProJote**
2. Cliquez sur **Ajouter un équipement**
3. Remplissez :
   - **Nom** : Ex. "Pronote Élève" ou "Pronote Parent"
   - **Objet parent** : Sélectionnez une pièce
4. Sélectionnez **Connexion par QR Code**
5. Cliquez sur le bouton **📱 Scanner QR**
6. Scannez le QR code Pronote
7. **Sauvegardez**

#### Option B : Par Identifiants

1. Allez dans **Plugins** → **Organisation** → **ProJote**
2. Cliquez sur **Ajouter un équipement**
3. Remplissez :
   - **Nom** : Ex. "Pronote Élève"
   - **Type de compte** : "Élève" ou "Parent"
   - **Mode CAS** : Choisissez le type CAS (ViaUrl par défaut)
   - **URL Pronote** : URL de votre établissement (ex: https://pronote.example.com)
   - **Identifiants** : Nom d'utilisateur et mot de passe
4. Si parent, sélectionnez le **nom de l'enfant**
5. **Sauvegardez**

### 3. Configuration Avancée

Une fois l'équipement créé :

| Paramètre | Description |
|-----------|-------------|
| **Horaire de récupération** | Heure de début des syncs (ex: 6h du matin) |
| **Intervalle de synchro** | Fréquence de mise à jour (en minutes) |
| **Actif** | Cochez pour activer la synchronisation |

---

## 📱 Utilisation

### Commandes Disponibles

#### Actions (Manuelles)
- **Rafraîchir** : Force une synchronisation immédiate

#### Informations Disponibles

**Identité**
- 👤 Nom de l'élève
- 🏫 Nom de la classe
- 🏢 Établissement
- 📷 Photo de profil
- 🔗 URL iCal (abonnement calendrier)

**Notes & Résultats**
- 📝 Liste des notes (détail)
- 📋 Dernière note
- 📊 Moyennes par matière

**Emploi du Temps**
- 📅 EDT du jour
- 📆 EDT du prochain jour
- ⏰ Heure de début/fin
- ❌ Cours annulés

**Travail à Faire**
- 📚 Liste des devoirs
- 📚 Devoirs pour demain
- ✅ Devoirs faits
- ❌ Devoirs non faits

**Comportement**
- 📍 Absences (liste et dernière)
- ⏱️ Retards (liste et dernier)
- ⚠️ Punitions (liste et dernière)

**Autres**
- 🔔 Notifications
- 📈 Compétences travaillées

### Exemples d'Automatisation

#### Notification sur nouvelle note
```
Si [Pronote].Dernière note change
   Envoyer notification "Nouvelle note : [Pronote].Dernière note"
```

#### Rappel devoirs
```
Si [Pronote].Devoirs pour demain > 0
   Envoyer notification "Devoirs pour demain : [Pronote].Nombre de devoir Demain"
```

#### Alerte absences
```
Si [Pronote].Nombre d'absence augmente
   Envoyer alerte "Nouvelle absence détectée"
```

---

## 🔐 Sécurité

⚠️ **Points importants**

- **Tokens stockés localement** dans `/data/[equipmentId]/` (non synchronisés cloud)
- **Mot de passe chiffré** (AES-256) en configuration
- **HTTPS recommandé** pour accéder à Jeedom
- **Port socket (55369)** en localhost uniquement
- **Logs sensibles** à vérifier en cas de problème

---

## 📊 Logs & Diagnostic

### Afficher les logs

1. **Interface Jeedom** → **Administration** → **Logs**
2. Sélectionnez **ProJote** dans la liste
3. Augmentez le niveau de **debug** si besoin

### Logs importants
```
ProJote : Lancement démon ProJote
ProJote : Envoie au demon Python des infos Pronotes : {...}
ProJote : Création de la commande : refresh
```

### Résoudre les problèmes

| Erreur | Solution |
|--------|----------|
| "Le démon n'est pas démarré" | Relancez le démon (Plugins → ProJote → Démon) |
| "Impossible de lancer le démon" | Vérifiez Python, vérifiez le port 55369 |
| "Port déjà utilisé" | Changez le port dans Configuration (55370 par ex.) |
| "Authentification échouée" | Vérifiez les identifiants, testez sur pronote.net |
| "Timeout socket" | Relancez le démon, vérifiez la connectivité réseau |

---

## 🔄 Mise à Jour

### Depuis le Market
Les mises à jour sont **automatiques** si activées dans les paramètres Jeedom.

### Manuelle
```bash
cd /var/www/html/plugins/ProJote
git pull origin master
```

Vérifiez les **nouveautés** : [Changelog](https://aldarande.github.io/ProJote/fr_FR/index.html#Version)

---

## 📚 Documentation Complète

Pour une documentation détaillée :
- 📖 [Documentation officielle](https://aldarande.github.io/ProJote/fr_FR/index.html)
- 🐛 [Signaler un bug](https://github.com/aldarande/ProJote/issues)
- 💬 [Support Jeedom Community](https://community.jeedom.com/)

---

## 🤝 Contribution

Les contributions sont bienvenues ! Pour participer :

1. **Fork** le projet
2. Créez une branche feature (`git checkout -b feature/AmazingFeature`)
3. **Commit** vos changements (`git commit -m 'Add AmazingFeature'`)
4. **Push** vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrez une **Pull Request**

---

## 📄 Licence

Ce projet est sous licence **AGPL v3.0** - voir [LICENSE](./LICENSE) pour détails.

---

## ✨ Auteur

**Aldarande** - [GitHub](https://github.com/aldarande)

---

## 🙏 Remerciements

- [PronotePy](https://github.com/Pronotepy/PronotePy) - Librairie Pronote
- [JEEDOM](https://www.jeedom.com/) - Plateforme domotique
- Communauté JEEDOM pour les retours

---

## ❓ FAQ

**Q: Puis-je utiliser ce plugin en compte parent?**  
R: Oui! Sélectionnez "Parent" lors de la configuration et choisissez l'enfant.

**Q: Comment changer le mot de passe stocké?**  
R: Modifiez l'équipement et sauvegardez - les nouveaux identifiants remplacent les anciens.

**Q: Les données sont-elles envoyées à l'auteur?**  
R: Non. Tout reste en local sur votre Jeedom. Aucune télémétrie.

**Q: Puis-je utiliser plusieurs comptes?**  
R: Oui! Créez plusieurs équipements ProJote (parent + enfants, par exemple).

**Q: Quel est l'intervalle de synchro minimum?**  
R: 1 minute par défaut, mais recommandé 5-10 minutes pour limiter les appels Pronote.

---

**Version:** 0.8  
**Dernière mise à jour:** 2024-02  
**Support:** Jeedom 4.3+
