# Le site CreateYourQueue

Le bouton **Inviter le bot**, et le **tableau de bord** ou un admin regle son
serveur depuis un navigateur : langue, fonctions activees, salons et roles.

```
Navigateur ──> Site (VPS) ──HTTP + cle──> Bot (Pterodactyl) ──> data/*.json
```

Le site ne touche jamais aux fichiers du bot. Il appelle l'API de
[`cogs/dashboard_api.py`](../cogs/dashboard_api.py), protegee par une cle
partagee. Le bot reste le seul a ecrire dans ses fichiers.

---

## Ce qu'il te faut

- Un serveur (VPS) avec Python 3.11 ou plus recent
- Un nom de domaine qui pointe dessus
- Le bot deja en route, avec un port ouvert accessible depuis le VPS

Les deux cotes doivent etre configures. Si tu n'en fais qu'un, le site
demarre mais n'affiche aucun serveur.

---

## 1. Cote bot

Ouvre le `.env` du bot (a la racine du projet, pas celui du site) :

```
DASHBOARD_API_KEY=une_longue_cle_au_hasard
DASHBOARD_API_HOST=0.0.0.0
DASHBOARD_API_PORT=8080
```

Pour generer la cle :

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Trois points a verifier :

- **Le port doit etre une allocation ouverte de ton serveur.** Sur
  Pterodactyl, c'est l'onglet Network. Un port qui n'y figure pas ne
  recevra rien.
- **Tant que `DASHBOARD_API_KEY` est vide, l'API reste eteinte** et le bot
  n'ouvre aucun port. C'est voulu : rien ne s'allume par accident.
- **Redemarre le bot** apres modification, sinon il tourne encore sans API.

Verifie depuis le VPS que le bot repond :

```bash
curl -H "X-API-Key: ta_cle" http://ip-du-bot:8080/api/health
```

Tu dois recevoir `{"status":"ok", ...}`. Un `401` veut dire que la cle ne
correspond pas. Pas de reponse du tout : le port n'est pas ouvert.

---

## 2. Application Discord

Sur [discord.com/developers](https://discord.com/developers/applications),
prends l'application du bot, onglet **OAuth2** :

- Note le **Client ID** et le **Client Secret**
- Dans **Redirects**, ajoute exactement `https://ton-domaine.fr/callback`

L'URL doit etre identique au caractere pres a `OAUTH_REDIRECT_URI`, sinon
Discord refuse la connexion sans expliquer pourquoi.

---

## 3. Cote site

```bash
cd site
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Remplis le `.env` (chaque ligne y est commentee). Puis lance :

```bash
python main.py
```

Le site ecoute sur `127.0.0.1:8000`. Il refuse de demarrer si une variable
obligatoire manque, en te disant laquelle.

---

## 4. nginx et HTTPS

Le site n'ecoute que en local : nginx s'occupe du domaine et du certificat.

```nginx
server {
    listen 80;
    server_name ton-domaine.fr;
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    server_name ton-domaine.fr;

    ssl_certificate     /etc/letsencrypt/live/ton-domaine.fr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ton-domaine.fr/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Le certificat avec certbot :

```bash
sudo certbot --nginx -d ton-domaine.fr
```

---

## 5. Demarrage automatique

Pour que le site reparte apres un redemarrage du VPS, cree
`/etc/systemd/system/cyq-site.service` :

```ini
[Unit]
Description=Site CreateYourQueue
After=network.target

[Service]
User=cyq
WorkingDirectory=/opt/createyourqueue/site
ExecStart=/opt/createyourqueue/site/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now cyq-site
sudo journalctl -u cyq-site -f
```

---

## Qui peut modifier quoi

Tu te connectes avec Discord. Le site releve alors les serveurs ou tu es
**proprietaire** ou as **« Gerer le serveur »**, et ne te propose que
ceux-la. La liste est relue a chaque requete d'enregistrement, pas
seulement a la connexion.

Le site ne stocke rien : ni base de donnees, ni fichier. Seulement un
cookie de session signe, qui retient ton pseudo et la liste de tes
serveurs. Le jeton Discord sert une fois, juste apres la connexion, et
n'est jamais conserve.

---

## Ce que le tableau de bord regle

| Reglage | Detail |
|---|---|
| Langue | Les 5 langues du bot. Salons et roles sont renommes en consequence. |
| Fonctions | Classement, Match et MVP, Clans, Annonces de clan, Panneau d'etat, Queues protegees |
| Salons | Commandes, annonces, resultats, classement, vocal d'attente |
| Roles | Staff, notification de queue |

Ce sont exactement les cles de `FEATURE_DEFAULTS`
([`guild_settings.py`](../guild_settings.py)) et de `EDITABLE_RESOURCES`
([`cogs/dashboard_api.py`](../cogs/dashboard_api.py)). Si le bot en ajoute
une, elle apparait dans le tableau de bord avec sa cle brute : pense a lui
donner un nom lisible dans `FEATURE_LABELS` de `main.py`.

---

## Si ca ne marche pas

| Ce que tu vois | Ce qu'il faut regarder |
|---|---|
| « Le bot ne repond pas » | Le bot tourne ? Le port est-il ouvert cote Pterodactyl ? |
| « Liaison avec le bot impossible » | `BOT_API_KEY` du site et `DASHBOARD_API_KEY` du bot doivent etre identiques |
| « Connexion interrompue » | L'URL de retour ne correspond pas a celle declaree dans Discord |
| Aucun serveur affiche | Le bot n'est pas sur tes serveurs, ou tu n'y as pas « Gerer le serveur » |
| Deconnecte a chaque page | `SESSION_HTTPS_ONLY=1` sans HTTPS : passe par nginx, ou mets 0 en local |

Les journaux du site disent ce qu'il s'est passe :

```bash
sudo journalctl -u cyq-site -n 50
```

---

## Structure

```
site/
├── main.py            # Routes, connexion Discord, verification des droits
├── settings.py        # Lecture du .env, refus de demarrer si incomplet
├── bot_api.py         # Le seul module qui parle a l'API du bot
├── templates/         # base, accueil, liste des serveurs, reglages, erreur
├── static/
│   ├── style.css      # Palette calee sur celle des embeds du bot
│   ├── app.js         # Theme clair ou sombre
│   └── settings.js    # Enregistrement : n'envoie que ce qui a change
├── requirements.txt
└── .env.example
```
