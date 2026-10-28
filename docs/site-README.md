# CreateYourQueue — site et panneau d'administration

Site statique : trois pages HTML, une feuille de style, quelques scripts, cinq
fichiers de langue. Rien à compiler, rien à installer. On envoie le dossier au
serveur d'hébergement, `index.html` à la racine, et c'est en ligne.

## Contenu

```
.htaccess                    cache et HTTPS côté serveur (Apache / LWS)
bump-version.ps1             renumérote les ?v= des assets
deploy-lws.ps1               renumérote puis envoie le site sur cyqbot.eu
deploy-lws.config.exemple.ps1  modèle de réglages FTP (sans mot de passe)
index.html                   accueil public
servers.html                 sélecteur de serveur (après connexion)
dashboard.html               configuration d'un serveur, 9 sections
assets/img/logo.png          logo du bot (marque + favicon)
assets/css/app.css           thème sombre + thème clair, composants
assets/js/config.js          >>> LE SEUL FICHIER À MODIFIER <<<
assets/js/app.js             thème, langues, OAuth, API, comboboxes, validation
assets/js/vendor/            anime.js 4.5.0 (MIT) + sa licence
assets/js/page-home.js       accueil : la cinématique des quatre systèmes
assets/js/page-servers.js    logique du sélecteur de serveur
assets/js/page-dashboard.js  logique du tableau de bord
assets/js/lang/*.js          fr · en · es · de · ko
```

## La seule dépendance : anime.js

`assets/js/vendor/anime.umd.min.js` — version 4.5.0, licence MIT, copiée
depuis le paquet npm `animejs` et **hébergée avec le site**. Pas de CDN :
le site continue de fonctionner hors ligne et ne dépend de personne à
l'exécution. Pas de `npm install` non plus : il n'y a toujours aucune étape
de build, on envoie le dossier tel quel.

Elle pèse 116 Ko minifiée, environ 40 Ko une fois compressée par le
serveur, et n'est chargée que par `index.html` — ni `servers.html` ni
`dashboard.html` n'en ont besoin.

Elle ne sert qu'à ce que le CSS ne sait pas faire :

- **les nombres qui montent** (`0 → 10`, `1000 → 1025`) : une transition CSS
  ne peut pas animer un contenu textuel ;
- **l'arrivée des pions sur un ressort** (`createSpring`), qui donne un
  rebond qu'une courbe de Bézier ne reproduit pas.

Tout le reste de la cinématique reste en CSS, où c'est moins cher et plus
fluide. Et le site dégrade proprement : si le fichier ne charge pas, la
classe `anime` n'est pas posée, les compteurs affichent directement leur
valeur d'arrivée et les pions reprennent leur transition CSS. Rien ne casse.

**Mettre à jour :** remplacez le fichier par le `dist/bundles/anime.umd.min.js`
d'une version plus récente du paquet `animejs`, et gardez `anime.LICENSE.md`
à côté — la licence MIT demande que la mention de copyright accompagne le
code.

## Avant la mise en ligne

Tout se passe dans `assets/js/config.js`.

1. **`CLIENT_ID`** — portail développeur Discord → ton application → *General
   Information*. Ce n'est pas un secret. **Ne mets jamais le `CLIENT_SECRET`
   dans ce fichier** : il serait lisible par n'importe qui. Il n'a sa place que
   sur ton serveur.
2. **`REDIRECT_URI`** — l'URL exacte vers laquelle Discord renvoie après
   connexion. Déclare la même dans *OAuth2 → Redirects*. Au caractère près,
   `https` compris.
3. **`INVITE_PERMISSIONS`** — la somme des permissions demandées à
   l'installation du bot. Recalcule-la dans *OAuth2 → URL Generator* si tu
   changes ce que le bot doit pouvoir faire.
4. **`API_BASE`** — l'URL de ton back-end. **Laisse la chaîne vide tant que tu
   n'en as pas** : le site fonctionne, se navigue, change de langue et de
   thème, et affiche ses états vides réels. Il n'invente aucune donnée.
5. `DOCS_URL`, `SUPPORT_URL`, `STATUS_URL`, `PRIVACY_URL` — tes vraies pages.
   Laissés à `#`, les liens ne mènent nulle part.

## Ce que le site attend du back-end

Le front ne parle à Discord que pour l'écran d'autorisation. Tout le reste
passe par ton API, en `fetch` avec `credentials: 'include'` (donc un cookie de
session, pas un jeton dans le navigateur). **L'échange du code OAuth contre un
jeton doit se faire côté serveur** : c'est la seule étape qui touche au
`CLIENT_SECRET`.

### `GET /guilds`

Les serveurs où la personne connectée est propriétaire ou a « Gérer le
serveur ».

```json
[
  {
    "id": "918244712003118592",
    "name": "Valorant League FR",
    "iconUrl": "https://cdn.discordapp.com/icons/…",
    "memberCount": 1284,
    "canManage": true,
    "botPresent": true,
    "configured": true,
    "missingPermissions": [],
    "updatedAt": "2026-09-22T18:04:00Z"
  }
]
```

Les cinq états de la liste se déduisent de ces champs : `canManage: false`
→ accès révoqué, `missingPermissions` non vide → droits insuffisants,
`botPresent: false` → bot absent, `configured: false` → assistant, sinon
configuré.

### `GET /guilds/{id}`

```json
{
  "id": "918…",
  "name": "Valorant League FR",
  "iconUrl": "…",
  "memberCount": 1284,
  "me": { "name": "nova_admin" },
  "channels":      [{ "id": "1", "name": "commandes-queue", "category": "COMPÉTITION", "disabled": false }],
  "voiceChannels": [{ "id": "2", "name": "Salle d'attente", "type": "voice" }],
  "categories":    [{ "id": "3", "name": "CLANS", "type": "category" }],
  "roles":         [{ "id": "4", "name": "Organisateur", "position": 12, "isBot": false }],
  "botRolePosition": 8,
  "permissions": [
    { "channel": "commandes-queue", "view": true, "write": true, "manage": true },
    { "channel": "résultats-archive", "view": true, "write": "warn", "manage": false, "state": "warn" },
    { "channel": "classement", "view": false, "write": false, "manage": false, "state": "deleted" }
  ],
  "missingPermissions": ["Gérer les salons"],
  "presets": [{ "name": "Scrim 5v5", "teams": 2, "players": 5 }],
  "settings": {
    "language": "fr",
    "feature.leaderboard": true,
    "channel.commands": "1",
    "role.organizer": "4",
    "mmr.enabled": true, "mmr.start": 1000, "mmr.win": 25, "mmr.loss": -18,
    "queue.name": "Scrim 5v5", "queue.teams": 2, "queue.players": 5,
    "queue.team0.name": "Équipe Rouge", "queue.team0.color": "#E05A4E",
    "log.match.enabled": true, "log.match.channel": "1",
    "security.antiraid": false
  }
}
```

`disabled: true` sur un salon le laisse visible dans la liste, grisé, avec la
mention « écriture refusée » : on n'escamote jamais une destination, on dit
pourquoi elle est indisponible.

Les clés de `settings` sont exactement les attributs `data-setting` du HTML.
Pour en ajouter une, il suffit d'ajouter la ligne de réglage correspondante
dans `dashboard.html` — le suivi des modifications et l'enregistrement la
prennent en charge sans toucher au JavaScript.

### `PATCH /guilds/{id}/settings`

Reçoit **uniquement les clés modifiées** de la section enregistrée :

```json
{ "mmr.win": "30", "mmr.loss": "-20" }
```

Réponses attendues : `200`/`204` en cas de succès, `401` si la session a
expiré (le site renvoie alors vers la connexion), `409` en cas de conflit.

### `POST /guilds/{id}/queue/open`

Ouvre une queue **avec la configuration enregistrée**. Le site n'envoie
aucun réglage dans le corps : la configuration qui fait foi est celle du
bot. C'est pour ça que le bouton du panneau reste fermé tant que des
modifications ne sont pas enregistrées.

L'API ne publie rien elle-même : elle relaie au bot, sur `BOT_API_BASE`
(voir `api/.env.example`), et rapporte sa réponse.

```json
{ "channelId": "913…", "messageUrl": "https://discord.com/…", "capacity": 10 }
```

| Code | Ce que le panneau affiche |
|---|---|
| `200` | « Queue ouverte dans #annonces » |
| `409` | le motif du bot, en toutes lettres (voir plus bas) |
| `502` | le bot n'a pas répondu — rien n'a été ouvert |
| `503` | `BOT_API_BASE` n'est pas renseignée |

Ce que l'API envoie au bot (`POST {BOT_API_BASE}/api/guilds/{id}/queue/open`,
en-tête `X-API-Key`) :

```json
{ "openedBy": { "id": "…", "name": "…" } }
```

Rien d'autre : le bot ouvre la queue avec **sa** configuration enregistrée,
exactement comme le bouton « Publier » du panneau `/queue`. C'est aussi lui
qui dit ce qui empêche d'ouvrir, et son motif remonte tel quel dans le `409` :
`already_open`, `no_channel`, `setup_incomplete`, `no_config`,
`missing_permissions`. Le panneau en fait une phrase.

La route côté bot est `cogs/dashboard_api.py`, méthode `open_queue` ; elle
appelle `QueueConfig.open_queue()`, le même point d'entrée que Discord.

## Mise en ligne

Hébergement de fichiers : aucun build, aucun `node_modules`, on envoie des
fichiers.

### Deux domaines

| Domaine | Contenu | Pages |
|---|---|---|
| `cyqbot.eu` | la vitrine | `index`, `modules`, `guide` |
| `dashboard.cyqbot.eu` | l'application | `login`, `welcome`, `servers`, `dashboard` |

Les deux adresses sont déclarées en haut de `assets/js/config.js`
(`SITE_ORIGIN`, `APP_ORIGIN`). C'est de là que tout découle :

- `app.js` récrit les liens marqués `data-site` (vers la vitrine) et
  `data-app` (vers l'application), ainsi que tous les « Se connecter »
  (`[data-login]`, via `CYQ.loginUrl()`). Un lien relatif ne traverse pas
  d'un domaine à l'autre : il faut une adresse absolue, et c'est elle que
  ces attributs produisent.
- `OAUTH_REDIRECT_URI` se calcule à partir d'`APP_ORIGIN`, puisque
  `login.html` n'existe plus que là.
- **Hors de ces deux domaines — en local, sur une IP, sur un serveur de
  test — la scission se désactive d'elle-même** et tous les liens
  redeviennent relatifs. Le dossier se teste donc comme avant, sans rien
  changer à la configuration.

Pour revenir à un domaine unique : vide les deux chaînes, et c'est tout.

### Avant le premier envoi sur le sous-domaine

1. **Créer le sous-domaine** : panneau client LWS → *Domaines* →
   *Sous-domaines* → `dashboard.cyqbot.eu`, en notant le dossier qu'il
   demande (souvent `/dashboard`). Puis **activer son certificat SSL** :
   sans HTTPS, la redirection du `.htaccess` boucle et Discord refuse le
   retour OAuth.
2. **Déclarer l'adresse de retour** dans le portail développeur Discord →
   *OAuth2* → *Redirects* : `https://dashboard.cyqbot.eu/login.html`, au
   caractère près. La redirection 301 du `.htaccess` n'y suffit pas :
   Discord compare l'URL **avant** toute redirection.
3. Copier `deploy-lws.config.exemple.ps1` en `deploy-lws.config.ps1` et
   remplir serveur FTP, identifiant, `RacineSite` et `RacineApp` (panneau
   LWS → *FTP*). **Le mot de passe ne se met pas dans ce fichier** : le
   script le demande, ou le lit dans `$env:LWS_FTP_PASS`.

### Envoyer

```
powershell -ExecutionPolicy Bypass -File deploy-lws.ps1
```

Le script renumérote les assets, puis envoie 20 fichiers à la vitrine et 22
à l'application — le socle commun (`app.js`, `config.js`, les cinq langues,
anime.js, le logo, `home.css`, `.htaccess`) part des deux côtés. La
documentation, les scripts et les captures restent sur ta machine.

| Option | Effet |
|---|---|
| `-Cible site` / `-Cible app` | ne met à jour qu'un seul des deux domaines |
| `-ListRemote` | liste les deux dossiers distants — sert à trouver les racines, n'envoie rien |
| `-DryRun` | montre la liste de ce qui partirait, n'envoie rien |

Les anciennes adresses (`cyqbot.eu/dashboard.html`…) sont renvoyées en 301
vers le sous-domaine par le `.htaccess`. La règle est conditionnée à l'hôte,
sinon elle boucherait sur elle-même une fois le fichier déployé des deux
côtés.

### Le cache : pourquoi « j'ai modifié et rien ne change »

Deux mécanismes, et il faut les deux :

1. **`bump-version.ps1`** (lancé tout seul par `deploy-lws.ps1`) renumérote
   le `?v=…` de tous les assets dans les cinq pages HTML. Le numéro change,
   l'URL change, le navigateur retélécharge. Sans ça, il garde `app.css` et
   `app.js` et affiche l'ancienne version, même après un `F5`.
2. **`.htaccess`** dit au serveur LWS de ne jamais faire garder les pages
   `.html`, et de faire garder le CSS et le JS un an — ce qui n'est sans
   danger **que** grâce au point 1.

Conséquence : on ne modifie jamais un fichier en ligne sans renuméroter.
Côté navigateur, un `Ctrl + Maj + R` une seule fois après la mise en ligne.

Si le site renvoie une erreur 500 juste après avoir envoyé `.htaccess`,
c'est qu'un module Apache manque chez l'hébergeur : commente le bloc
`mod_rewrite` (la redirection HTTPS) en premier, c'est le plus exigeant.

Deux réglages utiles côté hébergeur : servir `dashboard.html` en HTTPS
uniquement, et autoriser ton domaine dans les en-têtes CORS de l'API
(`Access-Control-Allow-Origin` sur ton domaine exact, pas `*`, puisque les
requêtes portent un cookie de session).

Les polices (Archivo et IBM Plex Mono) sont chargées depuis Google Fonts. Si
tu préfères les héberger toi-même, remplace le `<link>` en tête des trois
pages par tes propres `@font-face`.

## Ce qui est volontaire dans ce design

- **Noir et blanc, les deux couleurs du logo.** Le crème du disque
  (`#F6F6F3`) et le noir du tracé (`#0C0C0B`) ; tout le reste est un gris
  tiré de l'un vers l'autre. En monochrome, ce qui distingue l'action n'est
  plus la teinte mais **l'aplat** : un bouton plein reste le seul objet
  rempli de l'écran, le texte de la même couleur n'est jamais un aplat.
- **Un seul objet rempli par écran.** C'est pour ça que le sélecteur de
  serveur n'a aucun bouton accentué : sept serveurs veulent sept actions
  différentes, et sept boutons pleins ne hiérarchisent plus rien.
- **Aucune couleur seule ne porte une information.** Les trois couleurs
  d'état (succès, attention, erreur) sont les seules couleurs de
  l'interface, à chroma volontairement basse, et toujours doublées d'un
  glyphe et d'un mot. L'interface reste exacte en niveaux de gris. La
  palette d'équipe de la section *Queue* est la seule exception : ces
  couleurs appartiennent à l'admin et sont reportées sur les rôles Discord.
  Elle est dans `TEAM_COLORS`, au début de `page-dashboard.js`.
- **Pas de bouton « Enregistrer » global.** Chaque section a sa propre barre,
  qui n'apparaît que s'il y a des changements, les compte, les nomme, et se
  bloque tant qu'une saisie est invalide.
- **Rien n'est masqué.** Un réglage dépendant d'un interrupteur éteint reste
  affiché, atténué, avec la raison écrite à côté.
- **Aucune donnée inventée.** Sans `API_BASE`, les écrans montrent leurs états
  vides plutôt que de faux serveurs et de faux joueurs.
- **La cinématique de l'accueil.** Chaque système occupe une piste de
  `300vh` ; l'étage y reste collé (`position: sticky`) et la position du
  défilement dans la piste choisit lequel des quatre temps est joué. Le
  JavaScript ne fait que poser des classes — `paint()` dans
  `page-home.js` — et toute l'interpolation revient au CSS, sur `opacity`
  et `transform` seulement, donc la mise en page n'est jamais recalculée
  pendant l'animation. Les lectures de position sont groupées dans un
  `requestAnimationFrame`, une par image au maximum.
  Pour ajouter un temps à une scène, il suffit de poser `data-from="2"`
  (et `data-to` si l'élément doit disparaître ensuite) sur un élément de
  la démo : aucun code à écrire.
- **Une animation JavaScript doit se couper elle-même.** La règle CSS
  `prefers-reduced-motion` ne suspend que les transitions CSS : anime.js
  continuerait d'animer par-dessus. `countTo()` et `popSlots()` testent
  donc `calm.matches` et posent directement l'état d'arrivée. De même, un
  ressort a une longue traîne : `stopSlots()` l'annule avant toute remise
  à zéro, sinon sa frame suivante réécrase l'état qu'on vient de poser.
- **La cinématique est un supplément, jamais le contenu.** Sous
  `prefers-reduced-motion`, ou si le navigateur ne gère pas `sticky` ou
  `IntersectionObserver`, la classe `cine` n'est pas posée : les quatre
  scènes redeviennent une page qui se lit de haut en bas, toutes les
  légendes et toutes les démos visibles d'un coup. La page passe alors de
  treize écrans à moins de trois. Une animation coupée ne doit jamais
  laisser du contenu invisible.

## Accessibilité

Contraste AA vérifié séparément dans les deux thèmes (le ratio de chaque
couleur est en commentaire dans `app.css`). Les contours de **contrôle**
utilisent leur propre variable, `--ctl-line`, tenue à 3:1 contre le fond du
contrôle — c'est le seuil WCAG 1.4.11 pour les bordures qui servent à
identifier un champ ou un bouton, distinct du filet décoratif `--line` qui
ne sépare que deux lignes. Focus visible partout, navigation
complète au clavier y compris dans les listes de salons (↑↓ ⏎ Échap), lien
d'évitement, et `prefers-reduced-motion` respecté. Testé sans débordement
horizontal de 1440 px à 375 px, en français comme en allemand.
