# Site CreateYourQueue

Le site fait deux choses : **inviter le bot** et **ouvrir le tableau de bord**.

Il tourne sur un serveur différent de celui du bot. Il ne lit jamais les fichiers
du bot : il lui parle par HTTP (voir [`../cogs/dashboard_api.py`](../cogs/dashboard_api.py)).

```
Navigateur ──> Site (VPS n°2) ──HTTP + clé──> Bot (serveur n°1) ──> data/*.json
```

## Les fichiers

| Fichier | Rôle |
|---|---|
| `main.py` | Les pages : accueil, connexion, liste des serveurs, configuration |
| `discord_oauth.py` | Connexion avec Discord, et lien d'invitation du bot |
| `bot_api.py` | Les appels au bot |
| `sessions.py` | Qui est connecté (en mémoire) |
| `templates/` | Les pages HTML (`guild_base.html` + une page par catégorie) |
| `static/style.css` | Le style, un seul fichier |

## Installation

### 1. Côté bot (serveur n°1)

Dans le `.env` du bot :

```
DASHBOARD_API_KEY=une_longue_chaine_au_hasard
DASHBOARD_API_HOST=0.0.0.0
DASHBOARD_API_PORT=8080
```

Le port doit être un port ouvert de ton allocation Pterodactyl. Redémarre le bot :
au démarrage, la console affiche `API du tableau de bord sur 0.0.0.0:8080`.
Sans clé, le bot n'ouvre aucun port, comme avant.

Pour générer la clé :

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Côté site (serveur n°2)

```bash
cd site
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Remplis `.env` : identifiants de ton application Discord, `SESSION_SECRET`,
`BOT_API_URL` (l'adresse du serveur du bot et son port), et `BOT_API_KEY`
(exactement la même clé que côté bot).

### 3. Côté Discord

Sur [discord.com/developers](https://discord.com/developers/applications), ton
application > **OAuth2** > **Redirects** : ajoute l'adresse de retour, mot pour mot,
la même que `DISCORD_REDIRECT_URI` (par exemple `https://ton-domaine.fr/callback`).

### 4. Lancer

Pour tester :

```bash
venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Pour de bon, un service qui redémarre tout seul. Dans `/etc/systemd/system/cyq-site.service` :

```ini
[Unit]
Description=Site CreateYourQueue
After=network.target

[Service]
WorkingDirectory=/chemin/vers/site
ExecStart=/chemin/vers/site/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now cyq-site
```

Puis nginx devant, pour le nom de domaine et le HTTPS (`certbot --nginx`) :

```nginx
server {
    server_name ton-domaine.fr;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Sécurité

- Le `.env` (des deux côtés) ne se partage pas et ne se committe pas.
- **Ferme le port de l'API du bot à tout le monde sauf au site.** La clé protège
  déjà l'API, mais tant que l'adresse est en `http://`, elle circule en clair :
  autorise seulement l'IP du VPS du site dans le pare-feu du serveur du bot.
- Le site ne demande à Discord que le pseudo et la liste des serveurs, jamais
  l'adresse e-mail, et le jeton Discord ne quitte pas la mémoire du site.
- Qui peut modifier quoi : uniquement les serveurs où Discord dit que tu es
  propriétaire ou « Gérer le serveur ». C'est revérifié à l'enregistrement.

## Les pages

| Adresse | Contenu |
|---|---|
| `/` | L'accueil : inviter le bot, ouvrir le dashboard |
| `/dashboard` | Les chiffres, les dernières commandes, les serveurs |
| `/dashboard/serveurs` | La liste complète de tes serveurs |
| `/dashboard/journal` | Les 100 dernières commandes — **propriétaire du bot uniquement** |

Les chiffres sont calculés **pour tes serveurs seulement** : le site envoie la
liste de ceux que tu administres à chaque appel, et le bot ne répond que sur
ceux-là.

**Le journal est réservé au propriétaire du bot** (`OWNER_ID` dans le `.env` du
bot, sinon le propriétaire de l'application Discord). Un admin de serveur ne
voit ni l'onglet, ni la page, ni les lignes : le bot refuse la demande, ce n'est
pas juste un lien caché. Le site demande une fois à la connexion qui tu es et
s'en souvient le temps de la session.

Le journal vit dans la mémoire du bot : 200 lignes au maximum, remises à zéro à
chaque redémarrage, et **sans les arguments des commandes** (un `/warn` porte un
motif, un `/suggest` un texte : ça ne sort pas de Discord). Tant que le bot n'a
pas tourné 24 h, le compteur « commandes / 24 h » ne compte que depuis son
démarrage, et le dit.

## Ce que le tableau de bord sait faire pour l'instant

La configuration d'un serveur est découpée en quatre catégories, une page
chacune, avec son propre bouton Enregistrer :

| Adresse | Contenu |
|---|---|
| `/dashboard/<serveur>/general` | La langue du bot |
| `/dashboard/<serveur>/salons` | Les 5 salons utilisés par les queues |
| `/dashboard/<serveur>/roles` | Rôle staff, rôle notifié, rôle connexion, rôle MVP de la semaine |
| `/dashboard/<serveur>/fonctions` | Classement, match/MMR, clans, panneau d'état, mot de passe |

Chaque page n'envoie au bot que ce qu'elle affiche : enregistrer les salons ne
touche jamais aux fonctions.

**Ajouter une catégorie** : une ligne dans `SECTIONS` (`main.py`), le cas
correspondant dans `guild_save`, et un fichier `templates/guild_<nom>.html` qui
étend `guild_base.html`. Rien d'autre à toucher.

Depuis le 11/10/2026, la langue, les salons et les rôles **ne se règlent plus
que là** : `/language` a été supprimée et `/config` ne garde que l'apparence du
bot et le renommage de ses salons. Le reste (queues, MMR, clans, logs, anti-raid)
est encore sur Discord, avec `/option` et les commandes dédiées.

## Vérifier le site

```bash
cd site
venv/bin/python -m unittest test_site
```

18 tests, sans Discord ni bot réels. Ils vérifient surtout **qui voit quoi** :
un admin de serveur n'a pas le journal, ne voit que ses serveurs, et chaque page
de configuration n'envoie au bot que ses propres réglages.
