# CreateYourQueue

Un bot Discord de file d'attente, son panneau web, et ce qu'il faut pour
tenir les deux à jour depuis deux PC sans y penser.

Tout vit ici. Avant le 28 octobre 2026, le bot était dans un dossier, le
site dans un autre, le site avait en plus deux copies périmées de lui-même,
et il fallait se souvenir de laquelle était vivante. C'était la vraie raison
pour laquelle modifier quoi que ce soit demandait une enquête préalable.

## Où est quoi

| Dossier | Ce que c'est |
| --- | --- |
| `bot/` | Le bot Discord (Python). Tourne sur AdKyNet. |
| `site/` | Le site statique, **exactement** ce qui part sur LWS. |
| `site/api/` | L'API, en PHP — c'est elle qui tourne en production. |
| `api-locale/` | La même API en Python, pour développer hors ligne. |
| `outils/` | Tous les scripts : synchro, publication, numérotation. |
| `docs/` | Les notes de conception, les prompts, le journal. |
| `archives/` | Copies de secours. Hors dépôt, jamais modifiées. |

Il n'y a **qu'une seule copie** de chaque fichier du site. Le dossier
qu'on édite est celui qui part en ligne.

## La commande

```
.\cyq aide
```

| Verbe | Effet |
| --- | --- |
| `.\cyq amorcer` | Prépare ce PC. À faire une fois par machine. |
| `.\cyq veille` | Lance la synchro continue, en arrière-plan. |
| `.\cyq arret` | L'arrête. |
| `.\cyq synchro` | Un passage tout de suite. |
| `.\cyq publier` | Met en ligne maintenant : site sur LWS, bot sur AdKyNet. |
| `.\cyq etat` | Où en est tout : git, veille, dernière publication. |
| `.\cyq pause` | La synchro continue, la mise en ligne attend. |
| `.\cyq reprendre` | Lève la pause — et lève un conflit réglé. |
| `.\cyq local` | Sert le site sur `http://localhost:8765`. |

## Travailler depuis le PC portable

Une seule commande, à coller dans PowerShell sur la machine neuve :

```powershell
powershell -NoProfile -Command "irm https://raw.githubusercontent.com/t3rroriste/createyourqueue/main/outils/installer.ps1 | iex"
```

Elle récupère le bot, le site, l'API et les outils, installe les
dépendances, demande les identifiants qui ne sont pas dans le dépôt, et
pose la veille au démarrage de Windows.

Ensuite, il n'y a plus rien à taper : ce qu'on enregistre sur un PC est sur
l'autre dans la demi-minute, et en ligne dans la foulée.

## Comment la synchro marche

Toutes les trente secondes, `outils/veille.py` fait un passage :

1. si une page, une feuille ou un script du site a changé, il renumérote
   les `?v=` — **avant** d'enregistrer, pour que le numéro parte dans le
   même commit ;
2. il enregistre, récupère ce que l'autre PC a poussé, et pousse ;
3. il publie ce qui a changé depuis la dernière publication **réussie** :
   `site/` sur LWS par FTPS, `bot/` sur AdKyNet par SFTP.

GitHub est la référence, pas l'hébergeur. Rien ne part en ligne sans être
d'abord enregistré — en septembre, cinq jours de travail n'ont existé que
sur AdKyNet parce que le code y partait sans passer par git.

Deux garde-fous :

- **un conflit suspend tout.** Si les deux PC ont modifié les mêmes lignes,
  le rebase est annulé, rien n'est publié, et `.\cyq etat` le dit. On règle
  à la main (`git pull --rebase`), puis `.\cyq reprendre` ;
- **`.\cyq pause`** laisse la synchro entre PC tourner mais retient la mise
  en ligne. C'est ce qu'on veut en pleine refonte d'une page.

Le journal de la veille : `outils/etat/journal.log`.

## Les secrets

Le dépôt est **public**. Rien de sensible n'y entre, et `.gitignore` le
garantit fichier par fichier :

| Fichier | Contenu | Où il vit |
| --- | --- | --- |
| `bot/.env` | Jetons Discord du bot | Sur chaque PC, et sur AdKyNet |
| `site/api/secrets.php` | `CLIENT_SECRET` Discord | Déposé à la main sur LWS |
| `outils/reglages/lws.config.ps1` | Identifiants FTP | Sur chaque PC |
| `outils/reglages/lws.pass` | Mot de passe FTP, chiffré | Sur chaque PC |
| `ADKYNET_SFTP_PASSWORD` | Mot de passe SFTP | Variable d'environnement |

`.env.example`, `lws.config.exemple.ps1` et `secrets.exemple.php` sont là
pour documenter les champs : ce sont eux qu'on édite et qu'on cite.

`lws.pass` est chiffré par Windows pour ton compte sur cette machine : la
copie ne sert à rien sur l'autre PC, qui redemande le mot de passe une fois.

## Ajouter un fichier au site

Une page, une feuille ou un script neuf doit être déclaré dans
`outils/fichiers-du-site.ps1`, et nulle part ailleurs. Sans ça il ne part
pas, et la page s'affiche en HTML nu en production — c'est arrivé à
`servers.css`, à `dashboard.css`, puis à `support.html`.
`outils/numeroter-versions.ps1` avertit quand une page réclame un fichier
qui n'est pas déclaré.
