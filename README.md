# 🎮 CreateYourQueue

Bot Discord de queues et de matchs : inscription, composition des équipes, capitaines, MMR, classements, clans et ClanWar — plus la modération, l'anti-raid et les logs du serveur.

Le bot parle **5 langues** (français, anglais, espagnol, allemand, coréen) et chaque serveur choisit la sienne avec `/language`.

---

## 🤖 Trois bots dans un seul projet

`bot.py` peut lancer trois bots Discord différents, chacun avec son propre token :

| Bot | Rôle | Token dans `.env` | Cogs chargés (`config.py`) |
|---|---|---|---|
| **Principal** | Toutes les commandes ci-dessous | `DISCORD_TOKEN` | `INITIAL_EXTENSIONS` + `WELCOME_EXTENSIONS` |
| **Temporaire** | `/waiting` et `/tempo` (remise à zéro totale du serveur), réservées au propriétaire ; `/ghost` (ghost ping d'arrivée), réservée aux administrateurs | `DISCORD_TOKEN_TEMPORAIRE` | `TEMPORARY_EXTENSIONS` |
| **ModMail** | Support par message privé — voir [`MODMAIL_SETUP.md`](MODMAIL_SETUP.md) | `DISCORD_TOKEN_MODMAIL` | `MODMAIL_EXTENSIONS` |

On choisit lesquels lancer avec `--bot` :

```bash
python bot.py --bot main
```

| Commande | Lance | Tokens nécessaires |
|---|---|---|
| `python bot.py --bot main` | le principal seul | 1 |
| `python bot.py --bot modmail` | le modmail seul | 1 |
| `python bot.py --bot temporaire` | le temporaire seul | 1 |
| `python bot.py --bot both` | principal + temporaire | 2 |
| `python bot.py` | **les trois** (c'est le défaut) | 3 |

⚠️ **`python bot.py` sans option lance les trois bots**, et s'arrête tout de suite s'il manque un seul des trois tokens. Si tu n'utilises que le bot principal, lance toujours `--bot main`.

### 👻 `/ghost` — ghost ping d'arrivée (bot temporaire)

Chaque nouveau membre est mentionné dans les salons choisis, puis le message est supprimé au bout de 5 secondes : la notification est partie, le salon reste vide. Réservée aux administrateurs.

| Commande | Effet |
|---|---|
| `/ghost add salon` | Ajoute un salon (5 maximum) |
| `/ghost remove salon` | Le retire |
| `/ghost list` | Salons configurés |
| `/ghost test` | T'envoie un ghost ping pour vérifier |

- Les arrivées de la même seconde partent dans **un seul message** : un raid ne fait pas 50 messages.
- Si le serveur a un **règlement d'accueil** Discord, le ping part quand le membre l'accepte — avant, il ne voit aucun salon.
- Dans chaque salon choisi, le bot a besoin de **Voir le salon** et **Envoyer des messages**, et le nouveau membre doit pouvoir voir le salon.
- Les salons sont enregistrés dans `data/ghost_ping.json`.

---

## 📋 Les commandes du bot principal

**Queue et matchs**

| Commande | Description |
|---|---|
| `/guide` | Le guide de configuration, pas à pas |
| `/queue` | Crée une queue, avec son panneau de réglages *(organisateur)* |
| `/rematch` | Relance la dernière partie avec les mêmes réglages |
| `/schedule` | Publie une queue automatiquement à l'heure choisie |
| `/poll` | Un sondage à boutons (jeu, horaire, format…) |
| `/groupe` | Affiche ton groupe, ou le dissout |
| `/history` | L'historique des dernières parties |
| `/bl` `/unbl` | Bloque / débloque un membre de la queue |

**Clans**

| Commande | Description |
|---|---|
| `/clan` | Ton clan : fiche, création, invitations, `rejoindre:` pour demander à entrer |
| `/clantransfer` | Passe la propriété d'un clan à un autre membre *(rôle désigné)* |
| `/cw` | Active ou désactive le système de ClanWar *(admin)* |

**Classement**

| Commande | Description |
|---|---|
| `/leaderboard` | Met à jour le classement dans son salon |
| `/stats` `/serverstats` | Statistiques d'un joueur, du serveur |
| `/elo` | Ton niveau, ton rang, ce qu'il reste avant le suivant |
| `/podium` | Podiums des saisons passées |
| `/season` | Remise à zéro mensuelle du classement |

**Modération et sécurité**

| Commande | Description |
|---|---|
| `/clear` | Supprime des messages *(Gérer les messages)* |
| `/lock` `/unlock` | Verrouille / déverrouille un salon *(Gérer les salons)* |
| `/warn` `/warnings` `/unwarn` | Avertissements *(Exclure temporairement des membres ; Gérer le serveur pour `/unwarn`)* |
| `/timeout` `/untimeout` | Sourdine temporaire *(Exclure temporairement des membres)* |
| `/antilink` | Anti-lien sur un salon |
| `/autoclean` | Nettoyage automatique d'un salon |
| `/antiraid` | Protection anti-raid : état, réglages, déverrouillage |
| `/logs` | Le salon qui reçoit les logs |

**Configuration et infos**

| Commande | Description |
|---|---|
| `/option` | Rôle organisateur, salons, fonctions à activer (dont les clans) |
| `/config` | Salons, langue, et l'apparence du bot sur ce serveur — avatar, bannière, pseudo *(admin)* |
| `/language` | La langue du bot sur ce serveur |
| `/roles` | Panneaux de rôles à cliquer |
| `/voice` | Le bot rejoint ou quitte un vocal |
| `/status` | Panneau d'état du bot, mis à jour toutes les 60 s — salon et activation |
| `/userinfo` `/serverinfo` | Informations sur un membre, sur le serveur |
| `/diagnostic` | Vérifie que tout fonctionne |
| `/reset` | Remet le bot à zéro sur ce serveur |
| `/help` | Le menu d'aide complet |

41 commandes au total. Le menu `/help` les liste exactement (vérifié par les tests).

### Les salons et rôles

L'administrateur désigne ses propres salons et rôles dans `/option` et `/config` : organisateur, connexion, annonces, résultats, classement…

Le bot crée néanmoins des salons et des rôles **temporaires** pendant le jeu :

| Quand | Ce qui est créé | Supprimé |
|---|---|---|
| Lancement d'une queue | un salon vocal par équipe | à la fin de la partie |
| Match avec MMR | un salon de match privé et un rôle par équipe | à la fin du match |
| MMR, « Rôles de rang » activé | un rôle par rang | — |
| Création d'un clan (`/option → Clan`) | un salon privé et un rôle `Clan - Nom` | avec le clan |
| ClanWar | un vocal de préparation, un vocal par équipe et un salon de match | à la fin du ClanWar |

---

## 🗂️ Structure du projet

```
createyourqueue/
├── bot.py               # Point d'entrée : lance le bot principal, temporaire et/ou modmail
├── config.py            # Listes de cogs par bot, couleurs, seuils ; les IDs viennent de .env
├── embeds.py            # Le style commun de tous les embeds
├── i18n.py              # Moteur de traduction — la fonction t()
├── guild_settings.py    # Les réglages de chaque serveur
├── json_store.py        # Écriture sûre des fichiers de data/ (jamais de fichier à moitié écrit)
├── resources.py         # Retrouve un salon / un rôle configuré
├── mmr.py               # Calcul du MMR et des paliers
├── command_sync.py      # Synchronise les commandes sans épuiser le quota
├── rate_limit.py        # Appels Discord étalés dans le temps
├── net_safety.py        # Vérification des liens (logos, avatars)
├── text_safety.py       # Nettoyage des textes saisis
├── retranslate.py       # Renomme salons et rôles au changement de langue
├── MODMAIL_SETUP.md     # Mise en place du bot modmail
├── locales/             # fr.json, en.json, es.json, de.json, ko.json
├── data/                # Ce que le bot a mémorisé (dont les tickets modmail) — ne pas éditer à la main
├── tests/               # Les tests automatiques — voir « Vérifier »
├── graphify-out/        # La carte du code (graph.html) — voir plus bas
└── cogs/
    ├── info.py          # /userinfo, /serverinfo — LE MODÈLE à copier
    ├── queue_config.py  # /queue, /history, /bl, /unbl
    ├── match.py         # Salon de match, capitaines, MVP, MMR, /elo
    ├── automation.py    # /schedule, /season, /podium
    ├── classement.py    # /leaderboard, /stats, /serverstats
    ├── clan.py          # /clan, /clantransfer, /cw
    ├── clan_war.py      # ClanWar : session, boutons, abandon (importé par clan.py)
    ├── clan_tickets.py  # Tickets du bouton « Problème » d'un ClanWar
    ├── party.py         # /groupe
    ├── wizard.py        # /option
    ├── welcome.py       # Message d'arrivée et choix de la langue
    ├── config.py        # /config
    ├── roles.py         # /roles
    ├── moderation.py    # /clear, /warn, /timeout…
    ├── statuspanel.py   # /status
    ├── modmail.py       # Bot modmail : support par MP
    ├── temp_bot.py      # Bot temporaire : /waiting, /tempo
    ├── ghost.py         # Bot temporaire : /ghost (ghost ping d'arrivée)
    ├── antiraid.py  antilink.py  auto_clean.py  logs.py
    └── help.py  language.py  diagnostic.py  reset.py
        guard.py  poll.py  queue_guide.py  voice_manager.py
```

---

## 🛠️ Ajouter une commande

Le modèle à copier est **`cogs/info.py`** : un vrai cog du projet, court et propre, qui montre un embed complet et les traductions. En résumé :

1. Copie `cogs/info.py` en `cogs/tonnom.py`
2. Renomme la classe `Info` en `TonNom`, en haut du fichier **et** dans `setup()` tout en bas
3. Remplace `/userinfo` et `/serverinfo` par ta commande
4. Ajoute `"cogs.tonnom",` dans la bonne liste de `config.py` — `INITIAL_EXTENSIONS` pour le bot principal
5. Relance : `python bot.py --bot main`
6. Ajoute-la au menu `/help` (`cogs/help.py` + les 5 fichiers de `locales/`)

Une commande réservée au staff doit porter un contrôle de permission, par exemple `@app_commands.checks.has_permissions(manage_messages=True)` juste au-dessus de `async def`. Sans lui, **n'importe quel membre** peut l'utiliser. Pour qu'un membre sans permission reçoive un message au lieu de rien, copie la fonction `cog_app_command_error` tout en bas de **`cogs/moderation.py`**.

Les textes passent tous par `t(guild_id, "cle")` et doivent exister dans **les cinq** fichiers de `locales/`, sinon la clé s'affiche telle quelle à l'écran.

Pour écrire un fichier dans `data/`, utilise `write_json` de `json_store.py` plutôt que `open(..., "w")` : un arrêt pendant l'écriture ne peut alors plus vider le fichier.

Le guide complet — embeds, options, boutons, erreurs courantes — est ici : https://claude.ai/code/artifact/c2713b13-4167-48eb-9e42-7cc0f8a6eefd

---

## 🚀 Installation en local (VS Code)

### 1. Prérequis
- [Python 3.14](https://www.python.org/downloads/) installé (coche « Add to PATH » pendant l'install)
- [VS Code](https://code.visualstudio.com/) avec l'extension **Python** (Microsoft)
- [FFmpeg](https://ffmpeg.org/download.html) dans le PATH, pour les annonces vocales

### 2. Créer l'application Discord
À faire **une fois par bot** que tu veux lancer (principal, et éventuellement temporaire et modmail).

1. Va sur https://discord.com/developers/applications
2. **New Application** → donne-lui un nom
3. Onglet **Bot** → **Reset Token** → copie le token (tu ne le reverras plus, garde-le secret)
4. Toujours dans l'onglet Bot, active ces **Privileged Gateway Intents** :
   - `SERVER MEMBERS INTENT`
   - `MESSAGE CONTENT INTENT`
   - (Presence Intent n'est pas nécessaire)
5. Onglet **OAuth2 → URL Generator** :
   - Scopes : `bot` + `applications.commands`
   - Permissions : `Administrator` (le plus simple) ou au minimum : Gérer les rôles, Gérer les salons, Gérer les messages, Déplacer les membres, Voir/Envoyer des messages
   - Copie l'URL générée en bas et ouvre-la dans ton navigateur pour inviter le bot

### 3. Mettre le projet dans VS Code
1. Ouvre le dossier `createyourqueue` dans VS Code (`Fichier > Ouvrir un dossier`)
2. Ouvre un terminal (`Terminal > Nouveau Terminal`)
3. Crée l'environnement virtuel et installe les dépendances :

```bash
python -m venv venv
```

```bash
venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

Les versions de `requirements.txt` sont **figées** : tout le monde, et l'hébergeur, installe exactement les mêmes.

4. Crée ton fichier `.env` à partir du modèle :

```bash
copy .env.example .env
```

5. Ouvre `.env` et remplis-le :

| Variable | Obligatoire ? |
|---|---|
| `DISCORD_TOKEN` | Oui |
| `DISCORD_TOKEN_TEMPORAIRE` | Seulement pour lancer le bot temporaire |
| `DISCORD_TOKEN_MODMAIL` | Seulement pour lancer le bot modmail |
| `OWNER_ID` | Non — ton ID Discord, seul autorisé à utiliser `/waiting` et `/tempo` (sinon : le propriétaire de l'application) |
| `SUPPORT_GUILD_ID` | Non — ton serveur officiel, toujours en français |
| `SUPPORT_INVITE` | Non — bouton d'invitation dans le message d'arrivée |
| `MODMAIL_GUILD_ID`, `MODMAIL_STAFF_CHANNEL_ID`, `MODMAIL_STAFF_ROLE_ID` | Pour le modmail |
| `DIAGNOSTIC_CHANNEL_ID` | Non — salon qui reçoit les messages de démarrage des bots |

Un token ne va **que dans `.env`**, jamais dans un fichier `.md`, `.py` ou `.json`. Aucun ID n'est écrit dans le code : tout se règle dans `.env`.

### 4. Lancer le bot

```bash
python bot.py --bot main
```

Si tout va bien, le terminal affiche une ligne `Extension chargée` par cog, puis :
```
[INFO] bot: [Main] Connecté en tant que CreateYourQueue#1234
[INFO] bot.command_sync: X commande(s) slash synchronisée(s).
```

`Commandes inchangées depuis la dernière synchronisation` est tout aussi normal : le bot n'envoie la liste à Discord que quand elle a vraiment changé, pour ne pas épuiser le quota.

Les commandes `/` peuvent mettre jusqu'à 1 h à apparaître dans l'autocomplétion la première fois — c'est une limite Discord, pas un bug. Elles fonctionnent déjà si on tape leur nom en entier.

### 5. Vérifier

Les tests automatiques contrôlent les traductions (mêmes clés dans les 5 langues, aucune clé manquante), le calcul du MMR, l'écriture des données, et que le bot charge tous ses cogs avec un `/help` à jour :

```bash
venv\Scripts\python.exe -m unittest discover -s tests -t .
```

pyflakes signale les fautes sans lancer le bot :

```bash
venv\Scripts\python.exe -m pyflakes bot.py config.py cogs
```

La plupart de ses remarques sont bénignes (`imported but unused` : un import inutile). **Une seule est grave : `undefined name`** — le code appelle quelque chose qui n'existe pas, et plantera au moment où cette ligne s'exécute.

Depuis Discord, `/diagnostic` contrôle que tout est chargé et configuré.

### 6. Garder l'historique avec git

Le dossier est un dépôt git : chaque « commit » est une sauvegarde à laquelle tu peux revenir. `.gitignore` exclut déjà `.env`, `venv/` et `data/`. Pour enregistrer l'état actuel :

```bash
git add .
```

```bash
git commit -m "Description de ce qui a changé"
```

### 7. La carte du code

`graphify-out/graph.html` s'ouvre dans le navigateur : chaque fichier, fonction et classe, et leurs liens. Pratique pour savoir ce qu'une modification va toucher. Pour la remettre à jour après avoir changé le code :

```bash
~/.local/bin/graphify.exe update .
```

---

## ⚙️ Configurer un serveur

Tout se fait depuis Discord, pas dans le code :

- **`/option`** — le rôle organisateur, le rôle de connexion, le chef de clan, les salons facultatifs, et les fonctions à activer (classement, résultats, MMR, clans)
- **`/config`** — les salons et rôles que le bot doit utiliser, et son apparence
- **`/language`** — la langue du serveur
- **`/status`** — le panneau d'état permanent
- **`/cw`** — le système de ClanWar

Dans `config.py`, on touche à trois choses : les listes de cogs, les couleurs des embeds et les seuils de l'anti-raid.

---

## ☁️ Hébergement gratuit 24/24

`Procfile`, `Dockerfile` et `railway.json` lancent `python bot.py --bot main` : **le bot principal seul**, avec un seul token. Pour héberger aussi le temporaire ou le modmail, change la commande et ajoute leurs tokens.

L'image Docker utilise Python 3.14 et installe FFmpeg pour les annonces vocales. `.dockerignore` garde `.env`, `venv/` et `data/` hors de l'image.

⚠️ **`data/` contient la configuration de chaque serveur.** Sur un hébergeur à conteneurs, ajoute un **volume persistant monté sur `/app/data`** : sans lui, tout est effacé à chaque redéploiement.

### Le plus simple : **Railway**
- https://railway.app
- Pousse ce projet sur un repo GitHub, puis « New Project → Deploy from GitHub repo »
- Ajoute tes variables (`DISCORD_TOKEN`, etc.) dans l'onglet **Variables**
- Ajoute un **Volume** au service, monté sur `/app/data`
- Railway construit le `Dockerfile` et lance la commande de `railway.json`
- Crédit gratuit mensuel limité — largement suffisant pour un bot, mais surveille la conso

### Gratuit à vie : **Oracle Cloud Free Tier**
- https://www.oracle.com/cloud/free/
- Une VM gratuite à vie (pas un essai), largement assez pour ce bot
- Plus technique : VM Linux, installer Python et FFmpeg, puis lancer le bot avec `screen`, `pm2` ou `systemd` pour qu'il survive à la déconnexion :
```bash
sudo apt update && sudo apt install python3-pip ffmpeg screen -y && screen -S bot
```
Puis, dans la session `screen` : `python3 bot.py --bot main`, et **Ctrl+A** puis **D** pour détacher — le bot continue de tourner. Ici `data/` reste sur le disque de la VM.
- Inconvénient connu : Oracle refuse parfois les inscriptions, au hasard

### Dédié aux workers : **Render**
- https://render.com
- Crée un « Background Worker » (**pas** un Web Service)
- Build : `pip install -r requirements.txt` · Start : `python bot.py --bot main`
- Ajoute tes variables dans Environment Variables, et un disque persistant pour `data/`

---

## 🔒 Sécurité

- Ne mets **jamais** ton `.env` ou un token sur GitHub — le `.gitignore` fourni exclut déjà `.env`, `data/` (dont les tickets du modmail) et les journaux
- Un token ne s'écrit **que** dans `.env`. Un token collé dans un `.md` ou un `.py` part sur GitHub avec le reste
- Si un token a fuité, régénère-le immédiatement dans le Developer Portal (`Bot → Reset Token`) : l'ancien cesse alors de fonctionner
