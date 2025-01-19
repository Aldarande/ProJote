# Documentation Plugin ProJote de Jeedom

![ProJote Icon](../../plugin_info/ProJote_icon.png)

## Sommaire
- [Documentation Plugin ProJote de Jeedom](#documentation-plugin-projote-de-jeedom)
  - [Sommaire](#sommaire)
  - [Présentation](#présentation)
  - [Installation](#installation)
  - [Connexion](#connexion)
    - [Méthode Login](#méthode-login)
  - [QR Code](#qr-code)
    - [Génération du QR Code](#génération-du-qr-code)
    - [Transmission sur Jeedom](#transmission-sur-jeedom)
  - [Utilisation](#utilisation)
  - [Version](#version)

---

## Présentation

Le rôle de ce plugin Jeedom est de récupérer les informations de l'élève publiées sur PRONOTE.

Pour cela, nous utilisons l'API Wrapper PronotePy :  
[https://github.com/bain3/pronotepy](https://github.com/bain3/pronotepy)

---

## Installation

Pour installer le plugin ProJote, suivez les étapes suivantes :
1. Accédez au Market Jeedom.
2. Recherchez le plugin ProJote.
3. Cliquez sur "Installer" pour ajouter le plugin à votre Jeedom.
4. Une fois l'installation terminée, activez le plugin depuis le menu des plugins.
5. Lancez l'installation des dépendances. Lors de la première exécution, cela peut être long, et vous devrez peut-être la relancer.

Dans le menu **Plugins / Organisations / Plugin Pronote**, cliquez sur **Ajouter**. Choisissez un nom identifiant l’équipement.

---

## Connexion

Il existe deux méthodes de connexion : **Login** ou **QR Code**. La méthode **QR Code** est recommandée.

![Connexion](../picture/Image%20-%20connexion.png)

### Méthode Login

Le but de cette méthode est de vous connecter avec les informations de connexion.

![Login](../picture/Image%20-%20Login.png)

1. Parcourez la liste des ENT/CAS pour trouver celle qui vous correspond. Si vous ne trouvez pas de correspondance, essayez "Aucun" ou d'autres.
2. Si vous utilisez un compte parent, cochez la case.
3. Saisissez le login, le mot de passe et l’URL Pronote que vous utilisez (par exemple : `https://demo.index-education.net/pronote/eleve.html`).

Exemple :
```plaintext
>>> Compte parent : https://XXXXXXXy.index-education.net/pronote/parent.html?login=true
>>> Compte élève : https://demo.index-education.net/pronote/eleve.html

## QR Code

### Génération du QR Code

Nous allons voir en premier lieu comment obtenir le QR CODE. Ensuite, nous verrons comment injecter ce QR code dans ProJote.

D’abord, connectez-vous au site Pronote et générez un QR Code avec un code PIN à 4 chiffres de votre choix. Récupérez le QR Code sur Pronote.

Sur votre site Pronote :

![Picture Pronote](../picture/Image%20-%20Entete%20Pronote.png)
![Picture Gen QRCode](../picture/Image%20-%20Gen%20QR%20CODE%20Pronote.png)

1. Entrez le PIN à 4 chiffres de votre choix.
2. Puis cliquez sur "Générer QR Code".

Une fenêtre va s’ouvrir avec le QR Code.

![Picture QRCode](../picture/Image-%20Projote%20QRCODE.png)

*Tips* : Utilisez l’outil Windows de capture d’écran.

Utilisez l’outil de capture d’écran Windows pour copier le QR Code dans le presse-papier en appuyant simultanément sur les touches suivantes :

![Picture QRCode](../picture/Image%20-%20Racc%20Touches.png)

`Windows` + `Shift` + `S`

Dessinez un carré autour du QR Code. Et l’image sera copiée dans le presse-papier.

### Transmission sur Jeedom

Créez un nouvel équipement ProJote.

![Picture Add](../picture/Image%20-%20ProJote%20add.png)
![Picture Name Eqt](../picture/Image%20-%20ProJote%20Name%20equ.png)

Sélectionnez le paramètre d’authentification QR Code, puis collez le QR en faisant un clic droit.

![Picture QRCode Target](../picture/Image%20-%20PRojote%20Qrcode%20target.png)

Code dans le carré gris ou importez l’image enregistrée. Le code PIN sera requis pour finaliser la configuration.

![Picture QRCode Pin](../picture/Image-%20Projote%20Pin%20code.png)

Attention, à chaque connexion, on renouvelle le token (car il est à usage unique). Si un cycle échoue, il faudra refaire l’authentification par QR CODE.

## Utilisation

Une fois connecté, le plugin va récupérer toutes les heures les mises à jour depuis Pronote.

![Picture cron Hourly](../picture/Image-%20Projote%20Cron%20Hourly.png)

Vous pouvez désactiver ce paramètre dans la configuration du plugin.

**Note** : La mise à jour horaire est désactivée de **22h** à **4h** du matin. Mais si vous demandez à rafraîchir l'équipement, il téléchargera les mises à jour.

Voici la liste des paramètres retournés par le plugin :

| Paramètre                                         | Description                                                    |
| ------------------------------------------------- | -------------------------------------------------------------- |
| Nom de l'élève                                    | Le nom de l'élève                                              |
| Nom de la classe                                  | Le nom de la classe de l'élève                                 |
| Établissement                                     | Le nom de l'établissement scolaire                             |
| Picture                                           | L'URL de l'image de l'élève sur le serveur Pronote             |
| URL Ical                                          | L'URL du calendrier iCal                                       |
| Nombre d'absence                                  | Le nombre d'absences de l'élève **sur la période**             |
| Nombre de punition                                | Le nombre de punitions de l'élève **sur la période**           |
| Nombre de devoir                                  | Le nombre de devoirs de l'élève faits et à faire               |
| Nombre de devoir non fait                         | Le nombre de devoirs non faits par l'élève                     |
| Nombre de devoir fait                             | Le nombre de devoirs faits par l'élève                         |
| Nombre de devoir pour le *prochain jour*          | Le nombre de devoirs pour le *prochain jour* d'école           |
| Nombre de devoir non fait pour le *prochain jour* | Le nombre de devoirs non faits pour le *prochain jour* d'école |
| Nombre de devoir fait pour le *prochain jour*     | Le nombre de devoirs faits pour le *prochain jour* d'école     |
| Heure de début aujourd'hui                        | L'heure de début des cours aujourd'hui                         |
| Heure de fin aujourd'hui                          | L'heure de fin des cours aujourd'hui                           |
| Nombre de cours annulé aujourd'hui                | Le nombre de cours annulés aujourd'hui                         |
| Date du *prochain jour*                           | La date du *prochain jour* de cours                            |
| Heure de début du *prochain jour*                 | L'heure de début des cours du *prochain jour*                  |
| Heure de fin du *prochain jour*                   | L'heure de fin des cours du *prochain jour*                    |
| Nombre de cours annulé du *prochain jour*         | Le nombre de cours annulés du *prochain jour*                  |
| Nombre de cours annulé                            | Le nombre de cours annulés **sur la période**                  |

*Le plugin récupère les informations contenues dans Pronote. Si elles ne sont pas présentes sur le site, elles ne remonteront pas dans le plugin. Donc avant toute demande, vous devez valider que l'information recherchée est présente.*

## Version

- Version Alpha : Première diffusion pour test
- 0.0.1 : Mise en ligne de la première version
- 0.0.2 : Mise à jour de la documentation et du change log
- 0.5 : Ajout de la connexion par QR Code

Dernière modification : `{{ saveDate }}`
