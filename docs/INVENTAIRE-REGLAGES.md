# Inventaire des réglages — panneau ↔ bot

État constaté le 29/10/2026, par lecture du code. Ce document répond à une
seule question, réglage par réglage : **qui en est le propriétaire, et le
changement traverse-t-il ?**

> **Le même jour, la plupart des trous ont été comblés.** Le relevé qui suit
> décrit l'état D'AVANT, parce qu'il explique pourquoi chaque chose était
> là ; la dernière section dit ce qui a changé et ce qui reste.

Un réglage « ne se synchronise pas » quand il existe des deux côtés sans
pont entre les deux. Chacun écrit alors dans son coin et le dernier écran
ouvert a l'air d'avoir raison.

## Comment ça circule aujourd'hui

Le panneau ne parle jamais au bot directement. `site/api/index.php` est au
milieu, et il tient **son propre fichier** (`site/api/data/guilds.json`).

- **Lecture** (`GET /guilds/{id}`) : le PHP lit son fichier, appelle
  `reglages_du_bot()`, et **fusionne la réponse du bot PAR-DESSUS** sa
  copie. Pour une clé pontée, le bot a donc toujours le dernier mot — un
  changement fait sur Discord se voit bien dans le panneau.
- **Écriture** (`PATCH /guilds/{id}/settings`) : `trier_pour_le_bot()`
  sépare. Ce qui est ponté part au bot, et son refus ou son silence fait
  échouer **tout** le lot. Puis le PHP enregistre le lot entier chez lui,
  pontées comprises, comme copie de secours.

Quatre tables disent ce qui traverse, dans `site/api/index.php` :
`PONT_RESSOURCES`, `PONT_FONCTIONS`, `PONT_QUEUE`, `PONT_MMR`. Cinq clés
sont traitées à part dans le code : `language`, `queue.captainVote`,
`queue.passwordValue`, les équipes (`queue.teamN.*`) et les rangs
(`mmr.rankN.*`).

**Une clé absente de ces tables ne quitte jamais le fichier du site.** Elle
n'est ni lue ni écrite chez le bot. C'est la définition exacte du bug.

## Ce qui traverse — 28 clés

| Réglage du panneau | Clé du bot | Commande Discord qui l'écrit aussi |
| --- | --- | --- |
| `channel.commands` | `channel_queue_command` | `/config`, assistant |
| `channel.announcements` | `channel_queue_announcement` | `/config`, assistant |
| `channel.results` | `channel_queue_resultat` | `/config`, assistant |
| `channel.leaderboard` | `channel_queue_classement` | `/config`, assistant |
| `channel.waitingVoice` | `voice_queue_waiting` | `/config`, assistant |
| `role.organizer` | `role_staff` | `/config`, assistant |
| `role.queueNotify` | `role_queue_notif` | `/config`, assistant |
| `feature.leaderboard` | `leaderboard` | `/option` |
| `feature.match` | `mvp` | `/option` |
| `feature.clans` | `clans` | `/option` |
| `feature.joinAnnounce` | `clan_notice` | `/option` |
| `feature.statusPanel` | `status` | `/option` |
| `feature.queuePassword` | `password` | `/option` |
| `language` | `guild_langs.json` | — (parti sur le site le 11/10/2026) |
| `queue.name` · `.type` · `.time` | `queue_config` | assistant de queue |
| `queue.teams` · `.players` | `queue_config` | assistant de queue |
| `queue.embedColor` · `.notifMessage` | `queue_config` | assistant de queue |
| `queue.captainVote` | `queue_config.captains` | assistant de queue |
| `queue.passwordValue` | `queue_password` | `/option` |
| `queue.teamN.name` · `.color` | `team_names` · `team_colors` | assistant de queue |
| `mmr.enabled` · `start` · `win` · `loss` | `mmr_config` | `/option` → MMR |
| `mmr.mvpBonus` · `streakBonus` | `mmr_config` | `/option` → MMR |
| `mmr.captainVote` · `resultVote` | `mmr_config` | `/option` → MMR |
| `mmr.rankN.*` · `rankCount` | `mmr_config.tiers` | — |

Ces clés-là vont dans les deux sens. Elles ne sont pas le sujet.

## Ce qui ne traverse pas — les trous

### 1. Le bloc Sécurité en entier — 7 clés

`security.antilink` · `security.autoclean` · `security.autocleanDelay` ·
`security.antiraid` · `security.raidThreshold` · `security.raidWindow` ·
`security.raidAction`

Aucune n'est dans une table de pont. Elles ne quittent jamais
`site/api/data/guilds.json`. **Le panneau affiche et enregistre sept
réglages de sécurité qui n'arrivent jamais au bot** : on coche « Anti-raid »,
le panneau dit « Enregistré », et le bot continue exactement comme avant.

Ce que le bot a vraiment, de son côté :

- **Anti-raid** : `get_antiraid_config` / `set_antiraid_config`
  (`bot/guild_settings.py:680`), écrits par `/antiraid config`
  (`bot/cogs/antiraid.py:240`). Quatre valeurs : `join_threshold`,
  `join_interval`, `min_account_age_hours`, `auto_kick`.
  Le pont est presque évident — `raidThreshold` → `join_threshold`,
  `raidWindow` → `join_interval` — **sauf pour deux choses** :
  - le bot n'a **pas d'interrupteur** anti-raid, il est toujours actif ;
    `security.antiraid` ne correspond à rien ;
  - `security.raidAction` propose quatre actions (alerter, exclure
    temporairement, expulser, bannir) là où le bot n'a qu'un booléen
    `auto_kick`. Deux des quatre choix du panneau n'existent pas dans le bot.
  - et le bot a `min_account_age_hours`, que le panneau ne montre pas.
- **Anti-lien** : par **salon**, pas par serveur (`data/antilink.json`,
  écrit par `/antilink`, `bot/cogs/antilink.py:123`). L'interrupteur unique
  du panneau ne peut pas représenter ça tel quel.
- **Nettoyage automatique** : `self.clean_configs`, **en mémoire seulement**
  (`bot/cogs/auto_clean.py:22`). Rien n'est écrit sur le disque : la
  configuration est perdue à chaque redémarrage du bot. Il n'y a donc rien
  à synchroniser tant que ce cog ne persiste pas.

### 2. Les clans — 3 clés

`channel.clanCategory` · `role.clanLeader` · `role.clanTransfer`

Le bot **a** ces ressources : `role_clan_leader` (`bot/cogs/clan.py:813`) et
`role_clan_transfer` (`bot/cogs/clan.py:1572`), posées par l'assistant
(`bot/cogs/wizard.py:548`). Elles manquent des **deux** listes :
`EDITABLE_RESOURCES` côté bot et `PONT_RESSOURCES` côté PHP. Le pont serait
mécanique — c'est un oubli, pas un désaccord de modèle.

### 3. Trois réglages MMR inventés par le panneau

`mmr.mvpEnabled` · `mmr.streakEnabled` · `mmr.streakRequired`

Le bot n'a **aucun** équivalent. Il a `mvp_bonus` et `streak_bonus` (zéro =
éteint), pas d'interrupteur séparé, et rien du tout pour « victoires
consécutives requises ». Ces trois champs n'ont jamais eu d'effet.

### 4. `queue.session` et `queue.password`

- `queue.session` (à la demande / programmée) : pas d'équivalent bot. Le bot
  déduit de `heure`.
- `queue.password` : interrupteur en double avec `feature.queuePassword`,
  qui est ponté, lui. Deux cases du même panneau pour une seule réalité.

### 5. `bot.nick` — l'autre sens manque

Il part bien sur Discord (`PATCH /guilds/{id}/members/@me`,
`site/api/index.php:948`), mais il est **relu depuis la copie locale**.
Changé à la main sur Discord, le panneau continue d'afficher l'ancien.

### 6. Deux rôles du bot que le panneau ignore

`role_connexion` et `role_mvp_week` sont dans `EDITABLE_RESOURCES`
(`bot/cogs/dashboard_api.py:70`) et dans `/config`
(`bot/cogs/config.py:47`). Le panneau n'a pas de champ pour eux. Ce n'est
pas un bug de synchro, c'est un manque : ils ne se règlent que sur Discord.

## Le silence du bot ne se voit pas

`reglages_du_bot()` rend un tableau vide quand le bot ne répond pas
(`site/api/index.php:606`). La lecture sert alors `$local` — **sans le
dire**. Le panneau affiche une copie qui peut dater de plusieurs jours avec
exactement la même assurance qu'une lecture fraîche.

L'écriture, elle, est honnête : elle renvoie `BOT_INJOIGNABLE` (502) et
n'enregistre rien. L'asymétrie est le problème : on lit un écran qui a l'air
juste, on modifie un champ, et c'est le refus qui apprend que le bot dort.

Il faut que la réponse de lecture porte de quoi le dire — un `botJoignable`
que le panneau sait afficher.

## Ce qui a été corrigé, et ce qui reste

**Corrigé le 29/10/2026.**

1. **L'anti-raid traverse** dans les deux sens : `PONT_SECURITE` côté PHP,
   `SECURITY_FIELDS` et un bloc `security` côté bot. Les bornes du panneau
   sont maintenant celles de `/antiraid config`, au nombre près — deux
   chemins vers le même réglage qui n'accepteraient pas les mêmes valeurs,
   c'est la promesse d'un panneau qui refuse ce que Discord vient
   d'enregistrer. `min_account_age_hours` a gagné son champ au passage.
2. **Les trois clés de clan traversent** : ajoutées à `EDITABLE_RESOURCES`
   et à `PONT_RESSOURCES`. `_matches_kind` sait maintenant reconnaître une
   catégorie, et refuse tout type qu'il ne connaît pas — son repli muet sur
   « est-ce un salon vocal ? » acceptait la première valeur venue.
3. **Ce qui ne correspondait à rien a disparu du panneau** plutôt que d'être
   ponté de force :
   - l'interrupteur anti-raid (la détection est toujours active) ;
   - deux de ses quatre actions, que le bot ne sait pas faire — il n'a
     qu'une expulsion pendant un lockdown, devenue un interrupteur ;
   - `mmr.mvpEnabled` et `mmr.streakEnabled` : le bot n'a que `mvp_bonus` et
     `streak_bonus`, où zéro vaut éteint. Leurs champs sont désormais
     toujours visibles ;
   - `mmr.streakRequired`, qui n'existe nulle part dans le bot ;
   - `queue.password`, doublon de `feature.queuePassword`. C'est ce dernier,
     le vrai, qui découvre maintenant le champ du mot de passe.
4. **Le silence du bot se dit** : la lecture renvoie `botJoignable`, et le
   panneau en fait un bandeau. L'écriture était honnête depuis toujours
   (`BOT_INJOIGNABLE`), la lecture non.
5. **L'anti-lien et le nettoyage automatique** ne prétendent plus se régler
   ici. Ils apparaissent avec leur commande — `/antilink`, `/autoclean on` —
   dans un groupe « À régler sur Discord ».

**Corrigé le 29/10/2026, deuxième passe.**

6. **Les journaux ne traversaient pas non plus**, et personne ne l'avait
   relevé : le bot avait son bloc `logs` et son `dashboard_update` depuis
   le début, mais aucune table de `site/api/index.php` ne connaissait
   `log.<type>.enabled` ni `log.<type>.channel`. On allumait « Modération »,
   le panneau disait « Enregistré », et aucun log n'arrivait. `PONT_JOURNAUX`
   les ponte dans les deux sens, chaque type envoyé d'un bloc — le bot
   éteint un journal allumé sans salon, donc l'interrupteur seul
   l'éteindrait aussitôt.
7. **Le nettoyage automatique est enregistré sur le disque**
   (`data/autoclean.json`) et les boucles repartent au démarrage. Il se
   règle maintenant depuis le panneau : salon, intervalle, interrupteur.
   `/autoclean on` et le panneau écrivent par le même chemin
   (`start_clean` / `stop_clean`), donc ils ne peuvent pas se contredire.
   Un salon supprimé efface sa propre entrée.
8. **L'anti-lien se règle depuis le panneau, salon par salon**, c'est-à-dire
   comme le bot le tient vraiment. Le panneau envoie la liste COMPLÈTE :
   un lot partiel ne dirait pas lesquels retirer.
9. **`role_connexion` et `role_mvp_week` ont leurs champs** dans la section
   Rôles, et leurs entrées dans `PONT_RESSOURCES`.
10. **`bot.nick` se relit depuis Discord** : le bot le rend dans sa charge
    utile (`guild.me.nick`), et la fusion de lecture le fait gagner sur la
    copie du site. Renommé à la main sur Discord, le panneau le montre.

**Ce qui reste.**

- **`queue.session`** (à la demande / programmée) reste un réglage
  d'affichage du site : il décide si le champ « heure » se montre. Le bot
  n'a que `heure`. Lui donner un sens côté bot demande de savoir ce qu'il
  fait d'une heure vide, ce qui n'a pas été vérifié.
- **Les presets de queue** restent dans le fichier du site, faute de route
  côté bot.

Et, à chaque fois : `api-locale/server.py` doit suivre `site/api/index.php`,
et `docs/site-README.md` doit décrire le contrat réel.
