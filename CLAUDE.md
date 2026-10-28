# CreateYourQueue — repère pour Claude Code

Bot Discord de file d'attente, son panneau web, et les outils qui tiennent
les deux à jour. Un seul dépôt, une seule copie de chaque fichier.

## Les dossiers

| Dossier | Statut |
| --- | --- |
| `bot/` | **Le bot Discord vivant** (Python, tourne sur AdKyNet). |
| `site/` | **Le site vivant.** Exactement ce qui part sur LWS. |
| `site/api/` | **L'API de production**, en PHP. |
| `api-locale/` | L'API en Python (`server.py`, port 3000), pour développer. |
| `outils/` | Les scripts : synchro, publication, numérotation. |
| `docs/` | Notes de conception, prompts, journal de refonte. |
| `archives/` | **Lecture seule.** Instantanés de prod, ancien dépôt Vite, captures. |

`archives/` est hors dépôt et refusé en écriture par `.claude/settings.json`.
Si une écriture y est refusée, ce n'est pas un bug.

## Le site — comment ça marche

Site **statique**. Pas de build, pas de bundler, pas de `npm install`.
Apache sert les fichiers tels quels. Tout ce qui est écrit est lu par le
navigateur sans transformation : HTML, CSS et JS vanilla, ES5 prudent,
IIFE, `'use strict'`.

```
site/index.html      accueil public
site/login.html      connexion Discord
site/welcome.html    écran de transition (la file qui se forme)
site/servers.html    sélecteur de serveur
site/dashboard.html  configuration d'un serveur, 10 sections
site/modules.html · site/guide.html · site/support.html

site/assets/css/home.css    accueil, login, welcome — D.A. AUTONOME
site/assets/css/auth.css    login + welcome, par-dessus home.css
site/assets/css/app.css     ancienne D.A. du panneau — plus chargée par aucune page
site/assets/css/dashboard.css · servers.css · modules.css · guide.css
site/assets/js/config.js    le seul fichier à remplir avant mise en ligne
site/assets/js/app.js       thème, langues, OAuth, API, comboboxes, validation
site/assets/js/page-*.js    un script par page
site/assets/js/lang/*.js    fr · en · es · de · ko
site/assets/js/vendor/      anime.js 4.5.0 UMD (MIT), hébergé, pas de CDN
```

### Les deux directions artistiques ne se mélangent pas

`home.css` (accueil, login, welcome) et la D.A. du panneau ne partagent
**aucun token**. C'est volontaire. Ne jamais importer une variable de l'un
dans l'autre, ne jamais « harmoniser » les deux.

- `home.css` : `--bg #0A0908`, `--panel #121110`, `--ink #F4F1EC`,
  `--accent #C08A5A` (cuivre, **un seul emploi par écran**),
  `--hair rgba(244,241,236,.08)`. Police Geist.
- panneau : monochrome crème/noir, `--acc #F6F6F3`, polices Archivo +
  IBM Plex Mono, thème clair via `html[data-theme="light"]`.

`docs/DESIGN-SYSTEM.md` et `docs/DESIGN-AUDIT.md` font loi en cas de doute.

### Les règles qui ne se négocient pas

- **Aucune dépendance nouvelle.** anime.js est la seule, et elle est
  copiée dans `site/assets/js/vendor/`. Pas de CDN, pas de paquet npm.
- **Animations en `transform` et `opacity` uniquement.** Pas de
  `box-shadow` animée, pas de `filter: blur()` animé sur une grande
  surface, rien qui déclenche un layout dans une boucle.
- **`prefers-reduced-motion: reduce`** a toujours une variante calme, et
  `?motion=on` force l'animation pour pouvoir la vérifier.
- **Si anime.js ne charge pas, la page reste lisible.** Les états de
  départ sont posés en JS, jamais en CSS.
- **Commentaires en français**, et ils expliquent le *pourquoi* d'une
  valeur, pas le *quoi* de la ligne. C'est la convention de tout le code,
  bot compris. Ne jamais « nettoyer » un fichier en retirant ses
  commentaires : c'est précisément ce qui a abîmé `dashboard.html` et
  `bot.py` le 28 octobre.
- **i18n** : tout texte visible passe par `data-i18n` et les cinq fichiers
  de langue. Ajouter une clé = l'ajouter dans les cinq.
- **Jamais de données inventées.** Sans API, les écrans affichent leurs
  états vides réels.

### Un fichier neuf doit être déclaré

`outils/fichiers_du_site.py` est la seule liste de ce qui part en ligne.
Une page, une feuille ou un script absent de cette liste ne part pas —
`servers.css`, `dashboard.css` et `support.html` en ont fait les frais.
`outils/numeroter_versions.py` avertit quand une page réclame un fichier
non déclaré ; il ne connaît pas les pages elles-mêmes, qu'il faut ajouter
à la main.

### Après chaque modification de CSS ou de JS

```
python outils/numeroter_versions.py
```

Le script renumérote les `?v=` de toutes les pages. Sans lui, le navigateur
sert l'ancienne version depuis son cache. La veille le fait toute seule
avant d'enregistrer ; à la main, c'est cette commande.

### Essayer en local

```
.\cyq local        (sur le MacBook : ./cyq local)
```

Puis `http://localhost:8765/welcome.html?guild=test&motion=on` par exemple.
`.claude/launch.json` déclare `cyq-site` (8765), `cyq-api` (3000) et
`cyq-archive` (8766, l'instantané de septembre pour comparer).

## bot/ — le bot Discord

Python, `bot.py` à la racine, les commandes dans `bot/cogs/`, les cinq
langues dans `bot/locales/`. `bot/data/` contient la configuration de TOUS
les serveurs Discord : hors dépôt, et jamais écrasée par une publication.

## api-locale/ — l'API de développement

`server.py`, Python, sans dépendance. Elle sert le dossier `site/` ET
`/api/*` sur la même origine : un cookie de session posé par une autre
origine est un cookie tiers, que Safari refuse. En production, c'est
`site/api/index.php` qui fait le même travail, parce que LWS n'exécute que
du PHP.

Le contrat d'API (`GET /guilds`, `GET /guilds/{id}`, …) est décrit dans
`docs/site-README.md`. Changer une réponse oblige à vérifier le front qui
la consomme — et les deux implémentations, PHP et Python.

## Synchro et publication

`cyq veille` tient les deux machines et les deux hébergeurs à jour tout
seul. `README.md` explique le mécanisme et les garde-fous. Ce qu'il faut
savoir ici : **ne jamais lancer une publication de sa propre initiative.**
`cyq publier`, `outils/publier_site.py` et `outils/publier_bot.py`
envoient en production sur `cyqbot.eu` et sur le serveur du bot. Ce sont
des commandes qu'on demande.

### Deux machines, deux systèmes

Le PC fixe est sous Windows, le portable est un MacBook. **Tout
l'outillage est en Python**, pour cette raison : `outils/cyq.ps1` et
`outils/cyq.sh` sont deux portes d'entrée sur les mêmes scripts. Un geste
nouveau s'écrit dans un `.py` ; les deux fronts l'appellent. Écrire la
logique dans l'un des deux fronts, c'est garantir qu'elle manquera sur
l'autre machine.

Ce qui reste propre à chaque système, et seulement cela : le coffre à mots
de passe (`outils/secrets_locaux.py` — DPAPI contre Trousseau) et le
lancement au démarrage (dossier Démarrage contre `launchd`).

## Secrets — à ne jamais lire ni recopier

- `bot/.env` — jetons du bot et de l'application Discord.
- `site/api/secrets.php` — `CLIENT_SECRET` de l'OAuth Discord.
- `outils/reglages/lws.json` — identifiants FTP (et l'ancien `lws.config.ps1`).
- Les mots de passe FTP et SFTP ne sont dans aucun fichier du dépôt : ils
  vivent dans le coffre du système.

Ces fichiers sont refusés en lecture par `.claude/settings.json`. Les
modèles `.env.example`, `secrets.exemple.php` et `lws.config.exemple.ps1`
documentent les champs : c'est eux qu'on édite et qu'on cite.
`CLIENT_SECRET` n'a jamais sa place dans `site/assets/js/config.js`, qui
est lisible par n'importe qui. **Le dépôt GitHub est public** : un secret
poussé une fois y reste, même effacé ensuite.

## Comment travailler ici

Le périmètre d'écriture est ouvert sur `site/`, `bot/`, `api-locale/`,
`outils/` et `docs/` : pas besoin de demander pour éditer un fichier, créer
une page, lancer un serveur local ou faire un commit. Ce qui reste à
demander est la liste courte : publier, forcer un push, effacer, toucher
aux archives, lire un secret.

Avant de livrer une modification visuelle, vérifie-la : sers le dossier en
local, ouvre la page, regarde la console, teste en `prefers-reduced-motion`
et en 375 px de large. Dis ensuite ce que tu as vérifié et ce que tu n'as
pas pu vérifier.
