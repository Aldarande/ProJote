# Contrôle de fuite de données personnelles

Ce dépôt est public. Entre janvier 2025 et septembre 2026, il a porté sans que
personne s'en aperçoive les jetons, les prénoms, les classes, l'établissement et
les **photographies** de quatre enfants, ainsi qu'un identifiant PRONOTE en
clair dans `LoginConnect.py`.

Un commit intitulé « Delete data directory » avait été fait dès janvier 2025. Il
n'avait rien effacé : supprimer un fichier ne le retire pas de l'historique. Il
a fallu réécrire l'historique et republier de force.

`verifier_fuites.py` est le garde-fou qui manquait.

## Installation, une fois par clone

```bash
git config core.hooksPath outils/hooks
```

Le réglage vaut pour tous les worktrees du dépôt. À partir de là, chaque
`git push` est précédé d'un contrôle, et la publication est refusée si quelque
chose d'anormal apparaît dans ce qu'elle ajoute.

## Les motifs nominatifs restent chez vous

Les prénoms et les noms ne sont **pas** dans ce dépôt, et ne doivent jamais y
être : écrire le prénom d'un enfant dans un dépôt public pour empêcher qu'il y
soit publié n'aurait aucun sens.

Ils se déclarent dans un fichier `.motifs-prives` à la racine, que `.gitignore`
écarte. Partez du modèle :

```bash
cp outils/motifs-prives.exemple .motifs-prives
```

Une expression rationnelle par ligne, insensible à la casse. Attention aux
prénoms contenus dans des mots courants — « Marc » se trouve dans
« marcher », « Luc » dans « lucide » — d'où les bornes de mot `\b` du modèle.

Un motif mal formé provoque une **erreur franche** plutôt qu'un silence : un
filtre de confidentialité qui ne détecte plus rien est pire que pas de filtre,
parce qu'il rassure.

## Ce qui est contrôlé

| Règle | Ce qu'elle refuse | Ce qu'elle laisse passer |
|---|---|---|
| chemin interdit | `data/`, `.venv/`, `resources/python_venv/` | le reste |
| établissement réel | une URL PRONOTE d'établissement | `demo.index-education.net`, les codes fictifs `0000000a`…`e` |
| identifiant d'espace | `identifiant=` suivi d'une vraie valeur | `identifiant=EXEMPLE…` |
| jeton | 32 caractères hexadécimaux ou plus | une couleur CSS, un identifiant court |
| chemin utilisateur | `C:\Users\<session>` | `C:\Users\utilisateur` |
| adresse courriel | toute adresse | `example.com`, `noreply@` |
| motif privé | ce que déclare `.motifs-prives` | — |

## Accepter une ligne légitime

Un vecteur de test peut ressembler à un jeton sans en être un. Portez le
marqueur `fuite-acceptee` dans un commentaire, sur la ligne elle-même ou sur
celle qui la précède :

```python
# fuite-acceptee : challenge renvoyé par PRONOTE, pas un jeton de compte.
challenge = "EF4C6F47929D96D7A778BF9EE2E3A48F"
```

## Les deux filets

Le crochet local peut être contourné (`git push --no-verify`) ou absent d'un
autre clone. Un job d'intégration continue relit donc **tout** le contenu suivi
à chaque poussée. Il n'a pas accès à `.motifs-prives`, qui reste local : il ne
vérifie que les règles génériques.

## Vérifier à la main

```bash
python outils/verifier_fuites.py --arbre
python outils/verifier_fuites.py --plage origin/works..HEAD
```

Le rapport ne recopie jamais la valeur trouvée en clair — un journal
d'intégration continue est public lui aussi.
