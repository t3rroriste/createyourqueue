# Configuration du bot ModMail

Le bot ModMail permet aux membres de contacter le staff par message privé.

## Installation

1. **Ajoute le token du bot modmail dans `.env` :**

```env
DISCORD_TOKEN_MODMAIL=colle_le_token_du_bot_modmail_ici
```

2. **Renseigne les identifiants dans `.env` :**

```env
MODMAIL_GUILD_ID=1234567890
MODMAIL_STAFF_CHANNEL_ID=9876543210
MODMAIL_STAFF_ROLE_ID=0
```

| Variable | Rôle |
|---|---|
| `MODMAIL_GUILD_ID` | Le serveur de support |
| `MODMAIL_STAFF_CHANNEL_ID` | Le salon staff privé où arrivent les tickets |
| `MODMAIL_STAFF_ROLE_ID` | Facultatif : seul ce rôle peut prendre, répondre et fermer un ticket. `0` = quiconque voit le salon staff |

Pour trouver un identifiant : active le mode développeur dans les paramètres Discord, puis clic droit sur le serveur, le salon ou le rôle › **Copier l'identifiant**.

3. **Installe les dépendances** (détection de langue et traduction) :

```bash
venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Lancer le bot modmail

```bash
python bot.py --bot modmail
```

## Fonctionnement

### Pour les membres

1. Ils envoient un message privé au bot.
2. Ils choisissent une catégorie : **Bug**, **Signalement**, **Question** ou **Suggestion**.
3. Ils décrivent leur demande.
4. Ils reçoivent une confirmation.

Tout ce que voit le membre est dans **sa langue**, détectée d'après son message (français, anglais, espagnol, allemand ou coréen ; anglais par défaut).

Tant que le ticket est ouvert, chaque nouveau message privé du membre est recopié dans le salon staff.

### Pour le staff

Chaque ticket arrive dans le salon staff avec trois boutons :

| Bouton | Effet |
|---|---|
| 🎯 **Prendre** | Prend le ticket en charge. À faire en premier. |
| 📝 **Répondre** | Répond au membre par un message simple « @staff : réponse », traduit dans sa langue. Seule la personne qui a pris le ticket peut répondre. |
| 🔒 **Fermer** | Ferme le ticket et prévient le membre. |

Les boutons sont dans la langue du serveur de support (en français si `SUPPORT_GUILD_ID` est ce serveur).

La réponse du staff est **traduite automatiquement** dans la langue du membre.

Les boutons d'un ticket ouvert **restent utilisables après un redémarrage** du bot.

## Confidentialité

- Le contenu des messages n'est jamais écrit dans les journaux du bot.
- Pour être traduits, les messages passent par Google Traduction ; quand Google est saturé, MyMemory prend le relais. Si les deux le sont, la réponse part sans traduction et le staff en est prévenu.

## Fichiers

- `cogs/modmail.py` : toute la logique du modmail
- `data/modmail_sessions.json` : les tickets, créé automatiquement. Un ancien `modmail_sessions.json` à la racine du projet y est déplacé tout seul au démarrage.
- `.env` et `config.py` : les identifiants

## Commande du propriétaire

`!reset_modmail` efface tous les tickets (réservé au propriétaire de l'application Discord).

## Permissions requises

Le bot modmail a besoin de :
- lire et envoyer des messages privés ;
- voir le salon staff et y envoyer des messages ;
- ajouter des réactions (il met ✅ sur les messages transmis).
