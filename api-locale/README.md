# API de connexion Discord

Ce serveur sert le site **et** gère la connexion Discord, sur une seule
adresse. C'est volontaire : un cookie de session posé par une autre origine
que celle du site est un cookie tiers, que Safari refuse par défaut. Tout
servir depuis la même origine supprime le problème.

Aucune dépendance à installer. Python 3.11 ou plus suffit.

---

## Démarrer, en 4 étapes

### 1. Créer l'application Discord

Sur https://discord.com/developers/applications → **New Application**.

### 2. Déclarer l'adresse de retour

Dans votre application → **OAuth2** → **Redirects** → *Add Redirect*, collez
exactement :

```
http://localhost:3000/api/auth/callback
```

Au caractère près. Discord refuse la connexion si l'adresse diffère, ne
serait-ce que d'une barre oblique finale.

### 3. Remplir le fichier `.env`

Copiez `.env.example` en `.env`, puis remplissez :

| Variable | Où la trouver |
|---|---|
| `DISCORD_CLIENT_ID` | Application → General Information |
| `DISCORD_CLIENT_SECRET` | Application → OAuth2 → Client Secret |
| `DISCORD_BOT_TOKEN` | Application → Bot → Token *(facultatif)* |

**Le `CLIENT_SECRET` est un vrai secret.** Il ne sort jamais du serveur. Ne
le mettez jamais dans `config.js` ni dans un fichier du site : tout ce qui
est dans le site est lisible par n'importe quel visiteur. `.env` est déjà
dans `.gitignore`.

### 4. Lancer

```
python server.py
```

Puis ouvrez http://localhost:3000

---

## Ce qui marche, et ce qui manque

| Route | État |
|---|---|
| `GET /api/auth/login` | connexion Discord, avec `state` anti-CSRF |
| `GET /api/auth/callback` | échange du code, ouverture de la session |
| `POST /api/auth/logout` | fermeture de la session |
| `GET /api/me` | le compte connecté |
| `GET /api/guilds` | vos serveurs, filtrés sur « Gérer le serveur » |
| `GET /api/guilds/:id` | un serveur, avec ses salons et ses rôles |
| `PATCH /api/guilds/:id/settings` | enregistre les réglages |

**Sans `DISCORD_BOT_TOKEN`**, la connexion marche et la liste des serveurs
s'affiche, mais les menus de salons et de rôles du panneau restent vides :
un jeton utilisateur ne donne pas accès à ces listes, seul un jeton de bot
le permet.

**Les réglages sont écrits dans `data/guilds.json`.** C'est assez pour une
préversion, et volontairement remplaçable : seules `lire_reglages()` et
`ecrire_reglages()` y touchent. Passez à une vraie base avant d'ouvrir le
site à du monde.

**Les sessions vivent en mémoire.** Redémarrer le serveur déconnecte tout le
monde. C'est acceptable en préversion ; un stockage partagé sera nécessaire
le jour où vous ferez tourner plusieurs instances.

**`/api/guilds/:id` n'est pas encore relié à votre bot.** Le serveur renvoie
ce que Discord sait du serveur, plus ce qui est enregistré dans le fichier.
Les permissions réelles du bot, sa position dans la hiérarchie des rôles et
les presets viennent de votre bot : c'est le branchement qui reste à faire.

---

## Mettre en ligne

Trois changements :

1. `PUBLIC_URL=https://votre-domaine` dans `.env`
2. `ENV=production` — les cookies deviennent `Secure`
3. Ajoutez `https://votre-domaine/api/auth/callback` dans les Redirects Discord

Le HTTPS est obligatoire en production : sans lui, le cookie de session
circule en clair.
