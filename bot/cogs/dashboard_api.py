"""
API du tableau de bord
======================
Le site web tourne sur un autre serveur : il ne peut pas lire les fichiers
de `data/`. Ce cog ouvre donc une petite API HTTP dans le bot, que le site
appelle pour lire et modifier la configuration d'un serveur Discord.

Le bot reste le seul à écrire dans ses fichiers : le site ne fait que
demander. Toutes les écritures passent par guild_settings, comme les
commandes Discord.

Sécurité :
- rien ne démarre tant que DASHBOARD_API_KEY n'est pas défini dans le .env ;
- chaque requête doit porter l'en-tête `X-API-Key` avec cette clé ;
- l'API ne renvoie jamais de token, ni le contenu des messages.

Le site vérifie de son côté que la personne connectée est bien admin du
serveur qu'elle modifie (voir site/main.py) : l'API ne connaît pas les
utilisateurs, elle ne connaît que la clé.
"""

import asyncio
import json
import logging
import os
import re
import secrets
import sys
import time
from collections import deque
from typing import Any

import discord
from aiohttp import web
from discord.ext import commands

from config import DASHBOARD_API_HOST, DASHBOARD_API_KEY, DASHBOARD_API_PORT, OWNER_ID
from guild_settings import (
    FEATURE_DEFAULTS,
    get_antiraid_config,
    set_antiraid_config,
    MMR_DEFAULTS,
    clear_resource_id,
    get_features,
    get_queue_config,
    get_mmr_config,
    get_player_mmr,
    get_schedule,
    set_schedule,
    get_season,
    set_season,
    get_noshow_config,
    set_noshow_config,
    get_noshow_counts,
    reset_noshow,
    get_queue_blacklist_entries,
    add_to_queue_blacklist,
    remove_from_queue_blacklist,
    get_queue_ban_list,
    clear_queue_ban,
    get_webhook_url,
    set_webhook_url,
    get_queue_password,
    get_resource_id,
    is_setup_complete,
    queue_ready,
    save_queue_config,
    set_features,
    set_mmr_config,
    set_queue_password,
    set_resource_id,
)
import audit
import history
from webhook import url_acceptable
from cogs.logs import KINDS as LOG_KINDS
from cogs.auto_clean import INTERVAL_MAX as AUTOCLEAN_MAX, INTERVAL_MIN as AUTOCLEAN_MIN
import mmr
from cogs.queue_config import COLOR_PALETTE
from i18n import LANGUAGES, get_lang, set_lang

log = logging.getLogger("bot.dashboard")

# Salons et rôles modifiables depuis le site, avec le type attendu.
# Même liste que /config, sans les catégories (elles suivent les salons).
EDITABLE_RESOURCES = {
    "channel_queue_command": "text",
    "channel_queue_announcement": "text",
    "channel_queue_resultat": "text",
    "channel_queue_classement": "text",
    "voice_queue_waiting": "voice",
    "role_staff": "role",
    "role_queue_notif": "role",
    "role_connexion": "role",
    "role_mvp_week": "role",
    # Les clans. Le bot les tenait déjà — l'assistant les pose, cogs/clan.py
    # les lit — mais ils manquaient de cette liste ET de PONT_RESSOURCES :
    # le panneau avait trois champs qui n'arrivaient jamais jusqu'ici.
    "category_clan": "category",
    "role_clan_leader": "role",
    "role_clan_transfer": "role",
}

# L'anti-raid, tel que /antiraid config le règle déjà. Les bornes sont
# EXACTEMENT celles de la commande Discord (cogs/antiraid.py) : deux chemins
# vers le même réglage qui n'accepteraient pas les mêmes valeurs, c'est la
# promesse d'un panneau qui refuse ce que Discord vient d'enregistrer.
#
# Il n'y a pas d'interrupteur : l'anti-raid est toujours actif. Le panneau
# en affichait un, qui ne commandait rien.
SECURITY_FIELDS = {
    "join_threshold": (2, 100),
    "join_interval": (2, 300),
    "min_account_age_hours": (0, 720),
    "auto_kick": bool,
}

# Les réglages de queue modifiables depuis le site, avec le type attendu.
# Ce sont les clés de `queue_config` (guild_settings.py) que le panneau sait
# régler ; les autres — l'état d'une partie en cours, par exemple — ne sont
# pas des réglages et n'ont rien à faire ici.
QUEUE_FIELDS = {
    "queue_name": str,
    "type": str,
    "heure": str,
    "num_teams": int,
    "max_players_per_team": int,
    "captains": bool,
    "team_names": list,
    "team_colors": dict,
    # Le message envoyé en MP aux porteurs du rôle Notif Queue. Vide =
    # le texte habituel. Le bot l'efface après usage : il ne sert
    # qu'une fois, pour annoncer un événement précis.
    "notif_message": str,
    # La barre de couleur de l'annonce, en #rrggbb. Vide = le noir
    # d'origine.
    "embed_color": str,
}

# Les douze ronds que le bot sait écrire dans une annonce. Une couleur
# d'équipe qui n'en fait pas partie serait affichée telle quelle au milieu
# du message : on refuse plutôt que de défigurer l'annonce.
RONDS_VALIDES = {rond for rond, _fr, _en in COLOR_PALETTE}

# Les réglages de MMR que le site sait régler. Les autres clés de
# MMR_DEFAULTS (paliers, rôles de rang, délais de nettoyage) n'ont pas
# d'équivalent dans le panneau et ne doivent pas être écrasées par lui.
MMR_FIELDS = {
    "enabled": bool,
    "captains": bool,
    "start": int,
    "win": int,
    "loss": int,
    "mvp_bonus": int,
    "streak_bonus": int,
    "captain_vote_seconds": int,
    "mvp_vote_seconds": int,
    # Les rangs : une liste de paliers, du plus bas au plus haut. C'est eux
    # que /elo affiche et que le bot attribue en rôles. Les laisser régler
    # depuis le panneau évitait d'avoir à toucher un fichier à la main.
    "tiers": list,
}

# Un rang : son nom, le MMR à partir duquel il commence, sa couleur.
# `icon` est gardé s'il existe déjà — le panneau ne le règle pas, et
# l'écraser ferait perdre les emojis posés depuis Discord.
RANG_MAX = 12

# Les commandes qui changent la configuration d'un serveur. Elles seules
# vont dans le journal durable (audit.py) : le reste est de la
# consultation, et un journal où /elo côtoie /reset ne répond plus à la
# question qu'on lui pose.
COMMANDES_ECRIVANTES = {
    "config", "option", "queue", "antiraid", "antilink", "autoclean",
    "schedule", "season", "reset", "logs", "roles", "setup", "clan",
}

# Journal des commandes, gardé en mémoire : il sert à afficher les dernières
# lignes sur le site, pas à archiver. Un redémarrage le remet à zéro, et
# c'est très bien : ces données ne valent pas un fichier sur le disque.
JOURNAL_SIZE = 200
DAY_SECONDS = 24 * 3600
MAX_TIMES_PER_GUILD = 5000


def _minutes_du_jour(heure: str) -> int | None:
    """« 21:00 » -> 1260. None si la chaîne ne dit pas une heure du jour.

    Le format est celui que /schedule enregistre : le panneau et la
    commande doivent écrire la même chose, sinon l'un rend l'autre
    illisible.
    """
    morceaux = str(heure).split(":")
    if len(morceaux) != 2 or not all(m.isdigit() for m in morceaux):
        return None
    h, m = int(morceaux[0]), int(morceaux[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def _error(status: int, code: str) -> web.Response:
    return web.json_response({"error": code}, status=status)


def _icon(guild: discord.Guild) -> str | None:
    return guild.icon.url if guild.icon else None


def _joined_at(guild: discord.Guild) -> str | None:
    """Date d'arrivée du bot sur ce serveur, au format AAAA-MM-JJ."""
    me = guild.me
    joined = getattr(me, "joined_at", None) if me is not None else None
    return joined.date().isoformat() if joined else None


def _resource_entry(guild: discord.Guild, key: str) -> dict[str, Any] | None:
    """Salon ou rôle désigné pour cette clé, avec son nom actuel."""
    resource_id = get_resource_id(guild.id, key)
    if not resource_id:
        return None
    found = guild.get_channel(resource_id) or guild.get_role(resource_id)
    if found is None:
        # Désigné puis supprimé sur Discord : le site affichera « à redéfinir ».
        return {"id": str(resource_id), "name": None}
    return {"id": str(resource_id), "name": found.name}


class DashboardAPI(commands.Cog):
    """Serveur HTTP interne, éteint tant qu'aucune clé n'est configurée."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.started_at = time.time()
        # Les dernières commandes, la plus récente d'abord.
        self.journal: deque[dict[str, Any]] = deque(maxlen=JOURNAL_SIZE)
        # Et, par serveur, l'heure de chaque commande : de quoi compter
        # celles des 24 dernières heures sans garder tout le journal.
        self.command_times: dict[int, list[float]] = {}
        # Les retraductions en cours. asyncio ne garde qu'une référence
        # FAIBLE sur une tâche lancée par create_task : sans ce jeu, le
        # ramasse-miettes peut l'emporter en plein milieu, et le renommage
        # s'arrête sans la moindre trace.
        self._retraductions: set[asyncio.Task] = set()
        # La relance en cours, gardée pour la même raison. Un jeu à part et
        # non celui des retraductions : deux choses sans rapport dans le même
        # ensemble, c'est la prochaine personne qui en vide un et casse
        # l'autre.
        self._relances: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # Démarrage et arrêt
    # ------------------------------------------------------------------
    def build_app(self) -> web.Application:
        """Routes de l'API. À part pour les tests, personne n'appelle ça
        directement : c'est cog_load qui met le serveur en route."""
        app = web.Application(middlewares=[self._check_key])
        app.add_routes([
            web.get("/api/health", self.health),
            web.get("/api/stats", self.stats),
            web.get("/api/viewer", self.viewer),
            web.get("/api/commands", self.commands_journal),
            web.get("/api/guilds", self.list_guilds),
            web.get("/api/guilds/{guild_id}", self.get_guild),
            web.get("/api/guilds/{guild_id}/options", self.guild_options),
            web.patch("/api/guilds/{guild_id}", self.patch_guild),
            web.post("/api/guilds/{guild_id}/queue/open", self.open_queue),
            web.post("/api/guilds/{guild_id}/queue/close", self.close_queue),
            # Le redémarrage. Volontairement ABSENTE du relais PHP
            # (site/api/index.php ne recopie que les routes qu'il connaît) :
            # c'est un geste d'exploitation, demandé par les outils depuis un
            # PC, pas une action que le panneau web doit offrir à un admin de
            # serveur Discord.
            web.post("/api/restart", self.restart),
            # Les routes de LECTURE seule : l'historique, les fiches de
            # joueur, le relevé d'activité et le journal. Hors de
            # `/guilds/{id}` parce qu'elles sont volumineuses et paginées —
            # les coller dans la charge utile des réglages ferait payer
            # cinq cents matchs à chaque ouverture du panneau.
            web.get("/api/guilds/{guild_id}/matches", self.list_matches),
            web.get("/api/guilds/{guild_id}/players/{user_id}", self.player_card),
            web.get("/api/guilds/{guild_id}/activity", self.activity),
            web.get("/api/guilds/{guild_id}/audit", self.audit_log),
        ])
        return app

    async def cog_load(self) -> None:
        if not DASHBOARD_API_KEY:
            log.info("API du tableau de bord éteinte (DASHBOARD_API_KEY vide)")
            return

        self.runner = web.AppRunner(self.build_app(), access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, DASHBOARD_API_HOST, DASHBOARD_API_PORT).start()
        log.info(f"API du tableau de bord sur {DASHBOARD_API_HOST}:{DASHBOARD_API_PORT}")

    async def cog_unload(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None

    # ------------------------------------------------------------------
    # Contrôle de la clé, sur toutes les routes
    # ------------------------------------------------------------------
    @web.middleware
    async def _check_key(self, request: web.Request, handler) -> web.StreamResponse:
        sent = request.headers.get("X-API-Key", "")
        # compare_digest : la comparaison prend le même temps quelle que soit
        # la clé envoyée, on n'aide personne à la deviner caractère par caractère.
        if not secrets.compare_digest(sent, DASHBOARD_API_KEY):
            return _error(401, "unauthorized")
        return await handler(request)

    # ------------------------------------------------------------------
    # Journal des commandes
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command) -> None:
        self._record(interaction, command, "OK")

    @commands.Cog.listener()
    async def on_app_command_failed(self, interaction: discord.Interaction) -> None:
        """Envoyé par le gestionnaire d'erreurs de bot.py."""
        self._record(interaction, interaction.command, "ERR")

    def _record(self, interaction: discord.Interaction, command, status: str) -> None:
        """Une ligne : quand, où, qui, quelle commande, et si ça a marché.

        Jamais les arguments : `/warn` porte un motif, `/suggest` un texte.
        Le site n'a pas à les afficher, l'API n'a donc pas à les connaître."""
        if interaction.guild_id is None:
            return
        now = time.time()
        self.journal.appendleft({
            "at": now,
            "guild_id": str(interaction.guild_id),
            "guild": interaction.guild.name if interaction.guild else "?",
            "user": getattr(interaction.user, "display_name", "?"),
            "command": f"/{command.qualified_name}" if command is not None else "/?",
            "status": status,
        })
        # Le journal durable ne retient que les commandes qui MODIFIENT
        # quelque chose. Y mettre /elo ou /help le noierait sous des
        # consultations, et ce qu'on y cherche est « qui a changé ça ».
        nom = command.qualified_name if command is not None else ""
        if status != "ERR" and nom.split(" ")[0] in COMMANDES_ECRIVANTES:
            audit.record(
                interaction.guild_id, action=f"/{nom}", source="discord",
                who_id=interaction.user.id,
                who_name=getattr(interaction.user, "display_name", None),
            )

        times = self.command_times.setdefault(interaction.guild_id, [])
        times.append(now)
        if len(times) > MAX_TIMES_PER_GUILD:
            del times[:len(times) - MAX_TIMES_PER_GUILD]

    def _commands_last_day(self, wanted: set[int] | None) -> int:
        """Combien de commandes depuis 24 h, en oubliant les plus vieilles."""
        floor = time.time() - DAY_SECONDS
        total = 0
        for guild_id, times in list(self.command_times.items()):
            kept = [moment for moment in times if moment >= floor]
            if kept:
                self.command_times[guild_id] = kept
            else:
                del self.command_times[guild_id]
            if wanted is None or guild_id in wanted:
                total += len(kept)
        return total

    def _is_owner(self, user_id: int | None) -> bool:
        """Cette personne est-elle le propriétaire du bot ?

        Le journal des commandes lui est réservé : un admin de serveur voit
        ses réglages et ses chiffres, pas qui a lancé quoi. En cas de doute
        (OWNER_ID vide et application pas encore connue), c'est non."""
        if not user_id:
            return False
        if OWNER_ID:
            return user_id == OWNER_ID
        if getattr(self.bot, "owner_id", None):
            return user_id == self.bot.owner_id
        application = getattr(self.bot, "application", None)
        team = getattr(application, "team", None)
        if team is not None:
            return any(member.id == user_id for member in team.members)
        owner = getattr(application, "owner", None)
        return owner is not None and owner.id == user_id

    @staticmethod
    def _viewer(request: web.Request) -> int | None:
        """L'identifiant Discord de la personne connectée au site."""
        raw = request.query.get("user", "")
        return int(raw) if raw.isdigit() else None

    @staticmethod
    def _wanted(request: web.Request) -> set[int] | None:
        """Les serveurs demandés (`?guilds=1,2`).

        Le site n'envoie que ceux de la personne connectée : c'est ce qui
        empêche un admin de voir l'activité d'un serveur qui n'est pas le sien.
        Sans le paramètre, on renvoie None (aucun filtre) ; `guilds=` vide,
        lui, veut dire « aucun serveur » et surtout pas « tous » : quelqu'un
        qui n'administre rien ne doit rien voir."""
        if "guilds" not in request.query:
            return None
        wanted = set()
        for piece in request.query["guilds"].split(","):
            piece = piece.strip()
            if piece.isdigit():
                wanted.add(int(piece))
        return wanted

    def _guild_or_none(self, request: web.Request) -> discord.Guild | None:
        try:
            guild_id = int(request.match_info["guild_id"])
        except ValueError:
            return None
        return self.bot.get_guild(guild_id)

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    async def health(self, request: web.Request) -> web.Response:
        """L'état du bot, pour le panneau et pour la page d'état publique.

        Les trois champs d'origine ne bougent pas. Trois autres s'ajoutent,
        et ce sont EXACTEMENT ceux que cogs/statuspanel.py publie déjà dans
        Discord : deux endroits qui mesurent la même chose doivent la
        mesurer pareil. Les gardes sont donc les mêmes que build_embed() —
        une latence `nan` tant que le premier heartbeat n'est pas revenu
        vaut 0, un cog absent vaut 0 — jamais une valeur devinée.
        """
        latency = self.bot.latency
        # latency != latency est vrai pour nan, et seulement pour nan.
        latency_ms = round(latency * 1000) if latency == latency else 0

        queue_cog = self.bot.get_cog("QueueConfig")
        active = 0
        if queue_cog is not None:
            active = sum(1 for s in queue_cog.active_sessions.values() if not s.ended)

        return web.json_response({
            "status": "ok",
            "bot": str(self.bot.user) if self.bot.user else None,
            "guilds": len(self.bot.guilds),
            "latency_ms": latency_ms,
            "active_queues": active,
            "uptime_seconds": int(time.time() - self.started_at),
        })

    async def stats(self, request: web.Request) -> web.Response:
        """Les chiffres du haut du tableau de bord, pour les serveurs demandés."""
        wanted = self._wanted(request)
        guilds = [g for g in self.bot.guilds if wanted is None or g.id in wanted]
        return web.json_response({
            "uptime_seconds": int(time.time() - self.started_at),
            "servers": len(guilds),
            "users": sum(guild.member_count or 0 for guild in guilds),
            "commands_24h": self._commands_last_day(wanted),
        })

    async def viewer(self, request: web.Request) -> web.Response:
        """Ce que cette personne a le droit de voir. Le site le demande une
        fois à la connexion et s'en souvient le temps de la session."""
        return web.json_response({"owner": self._is_owner(self._viewer(request))})

    async def commands_journal(self, request: web.Request) -> web.Response:
        """Les dernières commandes, réservées au propriétaire du bot.

        Le contrôle est fait ici et pas seulement sur le site : cacher un
        lien n'est pas une protection, il suffirait de taper l'adresse."""
        if not self._is_owner(self._viewer(request)):
            return _error(403, "forbidden")
        wanted = self._wanted(request)
        try:
            limit = min(int(request.query.get("limit", "25")), JOURNAL_SIZE)
        except ValueError:
            limit = 25
        rows = [entry for entry in self.journal
                if wanted is None or int(entry["guild_id"]) in wanted]
        return web.json_response(rows[:max(limit, 0)])

    async def list_guilds(self, request: web.Request) -> web.Response:
        """Serveurs où le bot est présent. Le site croise cette liste avec
        celle de la personne connectée pour n'afficher que les siens."""
        return web.json_response([
            {
                "id": str(guild.id),
                "name": guild.name,
                "icon": _icon(guild),
                "members": guild.member_count,
                "setup_complete": is_setup_complete(guild.id),
                "joined": _joined_at(guild),
                "available": not guild.unavailable,
            }
            for guild in self.bot.guilds
        ])

    async def get_guild(self, request: web.Request) -> web.Response:
        guild = self._guild_or_none(request)
        if guild is None:
            return _error(404, "guild_not_found")
        return web.json_response(self._guild_payload(guild))

    def _logs_cog(self):
        """Le cog des logs, qui garde sa configuration à lui (data/logs.json)."""
        return self.bot.get_cog("Logs")

    def _autoclean_cog(self):
        """Le cog du nettoyage, qui garde sa configuration à lui (data/autoclean.json)."""
        return self.bot.get_cog("AutoClean")

    def _antilink_cog(self):
        """Le cog de l'anti-lien, qui garde sa configuration à lui (data/antilink.json)."""
        return self.bot.get_cog("AntiLink")

    def _guild_payload(self, guild: discord.Guild) -> dict[str, Any]:
        logs = self._logs_cog()
        nettoyage = self._autoclean_cog()
        antilien = self._antilink_cog()
        return {
            "logs": logs.dashboard_state(guild) if logs is not None else {},
            # Le nettoyage automatique. Il ne se réglait que par /autoclean,
            # et sa configuration ne survivait pas à un redémarrage : elle le
            # fait depuis qu'elle est écrite sur le disque, et le panneau peut
            # donc l'afficher sans mentir.
            "autoclean": nettoyage.dashboard_state(guild) if nettoyage is not None else {},
            # L'anti-lien, salon par salon. Le panneau n'avait qu'un
            # interrupteur de serveur, qui ne pouvait pas représenter ça.
            "antilink": antilien.dashboard_state(guild) if antilien is not None else {},
            "id": str(guild.id),
            "name": guild.name,
            "icon": _icon(guild),
            "members": guild.member_count,
            # Le surnom du bot SUR CE SERVEUR. Le panneau l'écrivait déjà
            # (PATCH /members/@me côté PHP) mais le relisait depuis sa propre
            # copie : renommé à la main sur Discord, il montrait l'ancien.
            # Vide = aucun surnom, le bot porte son nom d'application.
            "nick": (guild.me.nick or "") if guild.me is not None else "",
            "setup_complete": is_setup_complete(guild.id),
            "language": get_lang(guild.id),
            "languages": {code: info["name"] for code, info in LANGUAGES.items()},
            "features": get_features(guild.id),
            "resources": {
                key: _resource_entry(guild, key) for key in EDITABLE_RESOURCES
            },
            # La configuration de queue telle que le bot l'utilisera à la
            # prochaine ouverture. Le mot de passe en fait partie : le site
            # doit pouvoir montrer celui qui est posé, sinon on le règle à
            # l'aveugle. Ce n'est pas un jeton, et la route est déjà fermée
            # par la clé.
            "queue": get_queue_config(guild.id) or {},
            # Le MMR : c'est `enabled` ici — et pas la fonction `mvp` — qui
            # commande /elo, le classement et l'attribution des points.
            "mmr": {**{cle: get_mmr_config(guild.id).get(cle, MMR_DEFAULTS.get(cle))
                       for cle in MMR_FIELDS},
                    # Les rangs en vigueur : ceux du serveur, ou ceux
                    # d'origine traduits, qu'il faut bien montrer pour
                    # pouvoir les modifier.
                    "tiers": mmr.sorted_tiers(get_mmr_config(guild.id))
                             or mmr.default_tiers(guild.id)},
            "queue_password": get_queue_password(guild.id) or "",
            # L'anti-raid. Le lire importe autant que l'écrire : réglé par
            # /antiraid config sur Discord, il doit se voir dans le panneau.
            "security": {cle: get_antiraid_config(guild.id)[cle]
                         for cle in SECURITY_FIELDS},
            # La file programmée (/schedule) et les saisons (/season). Les
            # deux existaient depuis toujours côté bot et ne se réglaient
            # que sur Discord ; `season.archive` est le palmarès.
            "schedule": get_schedule(guild.id),
            "season": get_season(guild.id),
            # Les absences : le réglage, et les compteurs en cours.
            "noshow": {**get_noshow_config(guild.id),
                       "counts": get_noshow_counts(guild.id)},
            # Les deux listes d'exclusion, avec les pseudos : le site n'a
            # pas de jeton pour traduire un identifiant Discord lui-même.
            "blacklist": self._liste_exclus(guild),
            "queueBans": self._liste_bans(guild),
            # Le webhook sortant. L'URL n'est pas un secret — elle est
            # choisie par l'organisateur — mais c'est à lui de la relire.
            "webhook": get_webhook_url(guild.id),
        }

    def _liste_exclus(self, guild: discord.Guild) -> list[dict[str, Any]]:
        """La liste noire posée à la main : qui, par qui, quand, pourquoi."""
        sortie = []
        for entree in get_queue_blacklist_entries(guild.id):
            membre = guild.get_member(int(entree.get("user_id") or 0))
            sortie.append({
                "id": str(entree.get("user_id")),
                "name": membre.display_name if membre else None,
                "reason": entree.get("reason"),
                "by": str(entree["by"]) if entree.get("by") else None,
                "at": entree.get("at"),
            })
        return sortie

    def _liste_bans(self, guild: discord.Guild) -> list[dict[str, Any]]:
        """Les exclusions automatiques en cours, avec leur échéance."""
        maintenant = time.time()
        sortie = []
        for uid, fin in get_queue_ban_list(guild.id).items():
            if fin and fin <= maintenant:
                continue   # arrivée à terme : elle n'existe plus vraiment
            membre = guild.get_member(int(uid))
            sortie.append({
                "id": uid,
                "name": membre.display_name if membre else None,
                "until": fin or None,
            })
        return sortie

    async def guild_options(self, request: web.Request) -> web.Response:
        """De quoi remplir les listes déroulantes du site."""
        guild = self._guild_or_none(request)
        if guild is None:
            return _error(404, "guild_not_found")
        me = guild.me
        return web.json_response({
            "text": [
                {"id": str(c.id), "name": c.name}
                for c in guild.text_channels
                if me is None or c.permissions_for(me).send_messages
            ],
            "voice": [
                {"id": str(c.id), "name": c.name} for c in guild.voice_channels
            ],
            # Les catégories : la catégorie des clans se règle depuis le
            # panneau, il lui faut donc la liste.
            "category": [
                {"id": str(c.id), "name": c.name} for c in guild.categories
            ],
            "role": [
                {"id": str(r.id), "name": r.name}
                for r in guild.roles
                if not r.is_default() and not r.managed
            ],
        })

    # ------------------------------------------------------------------
    # Écriture
    # ------------------------------------------------------------------
    async def patch_guild(self, request: web.Request) -> web.Response:
        """Modifie la langue, les fonctions activées et les salons/rôles.

        Corps attendu (tout est facultatif) :
            {"language": "fr",
             "features": {"leaderboard": true},
             "resources": {"channel_queue_command": "123", "role_staff": null}}
        """
        guild = self._guild_or_none(request)
        if guild is None:
            return _error(404, "guild_not_found")

        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            return _error(400, "invalid_json")
        if not isinstance(data, dict):
            return _error(400, "invalid_json")

        # Qui agit, tel que le site le connaît. L'API ne sait pas vérifier
        # cette identité — elle ne connaît que la clé — mais le PHP, lui, a
        # déjà vérifié que la personne est admin du serveur. Le journal le
        # note donc tel quel, et c'est la seule façon de répondre à « qui a
        # changé ça ? » pour un geste venu du panneau.
        acteur = data.get("actor") if isinstance(data.get("actor"), dict) else {}
        try:
            auteur_id = int(acteur["id"]) if acteur.get("id") else None
        except (TypeError, ValueError):
            auteur_id = None
        auteur_nom = str(acteur.get("name") or "")[:80] or None

        """Les réglages de queue, validés clé par clé. Un lot refusé ne
           modifie RIEN : enregistrer la moitié d'un formulaire serait pire
           que de le refuser en entier."""
        queue = data.get("queue")
        queue_propre = None
        if queue is not None:
            if not isinstance(queue, dict):
                return _error(400, "invalid_queue")
            queue_propre = {}
            for cle, valeur in queue.items():
                attendu = QUEUE_FIELDS.get(cle)
                if attendu is None:
                    return _error(400, "invalid_queue")
                # bool avant int : en Python, True est un entier.
                if attendu is bool:
                    if not isinstance(valeur, bool):
                        return _error(400, "invalid_queue")
                elif attendu is int:
                    if isinstance(valeur, bool) or not isinstance(valeur, int):
                        return _error(400, "invalid_queue")
                    if not (1 <= valeur <= 12):
                        return _error(400, "invalid_queue")
                elif attendu is str:
                    # Le message de MP est le seul champ long : c'est un
                    # texte, pas une étiquette.
                    maxi = 1500 if cle == "notif_message" else 80
                    if not isinstance(valeur, str) or len(valeur) > maxi:
                        return _error(400, "invalid_queue")
                    if cle == "embed_color" and valeur and not re.fullmatch(r"#[0-9a-fA-F]{6}", valeur):
                        return _error(400, "invalid_queue_color")
                elif attendu is list:
                    if not isinstance(valeur, list) or len(valeur) > 12:
                        return _error(400, "invalid_queue")
                    if any(not isinstance(x, str) or len(x) > 60 for x in valeur):
                        return _error(400, "invalid_queue")
                elif attendu is dict:
                    if not isinstance(valeur, dict) or len(valeur) > 12:
                        return _error(400, "invalid_queue")
                    if any(v not in RONDS_VALIDES for v in valeur.values()):
                        return _error(400, "invalid_queue_color")
                queue_propre[cle] = valeur

        mmr = data.get("mmr")
        mmr_propre = None
        if mmr is not None:
            if not isinstance(mmr, dict):
                return _error(400, "invalid_mmr")
            mmr_propre = {}
            for cle, valeur in mmr.items():
                attendu = MMR_FIELDS.get(cle)
                if attendu is None:
                    return _error(400, "invalid_mmr")
                if attendu is list:
                    if not isinstance(valeur, list) or not (1 <= len(valeur) <= RANG_MAX):
                        return _error(400, "invalid_tiers")
                    propres = []
                    for rang in valeur:
                        if not isinstance(rang, dict):
                            return _error(400, "invalid_tiers")
                        nom = str(rang.get("name") or "").strip()
                        if not nom or len(nom) > 32:
                            return _error(400, "invalid_tiers")
                        try:
                            seuil = int(rang.get("min", 0))
                            couleur = int(rang.get("color", 0xF1C40F))
                        except (TypeError, ValueError):
                            return _error(400, "invalid_tiers")
                        if not (0 <= seuil <= 100000) or not (0 <= couleur <= 0xFFFFFF):
                            return _error(400, "invalid_tiers")
                        propre = {"name": nom, "min": seuil, "color": couleur}
                        if rang.get("icon"):
                            propre["icon"] = str(rang["icon"])[:8]
                        propres.append(propre)
                    # Triés ici : un rang plus bas que le précédent casserait
                    # /elo, qui lit la liste dans l'ordre.
                    valeur = sorted(propres, key=lambda r: r["min"])
                elif attendu is bool:
                    if not isinstance(valeur, bool):
                        return _error(400, "invalid_mmr")
                else:
                    if isinstance(valeur, bool) or not isinstance(valeur, int):
                        return _error(400, "invalid_mmr")
                    # Bornes larges : on se garde d'un zéro mal placé ou
                    # d'un nombre absurde, pas du choix de l'organisateur.
                    if not (0 <= valeur <= 100000):
                        return _error(400, "invalid_mmr")
                mmr_propre[cle] = valeur

        mot_de_passe = data.get("queue_password")
        if mot_de_passe is not None:
            if not isinstance(mot_de_passe, str) or len(mot_de_passe) > 64:
                return _error(400, "invalid_password")

        securite = data.get("security")
        securite_propre = None
        if securite is not None:
            if not isinstance(securite, dict):
                return _error(400, "invalid_security")
            securite_propre = {}
            for cle, valeur in securite.items():
                borne = SECURITY_FIELDS.get(cle)
                if borne is None:
                    return _error(400, "invalid_security")
                if borne is bool:
                    if not isinstance(valeur, bool):
                        return _error(400, "invalid_security")
                else:
                    mini, maxi = borne
                    # bool avant int : en Python, True est un entier.
                    if isinstance(valeur, bool) or not isinstance(valeur, int):
                        return _error(400, "invalid_security")
                    if not (mini <= valeur <= maxi):
                        return _error(400, "invalid_security")
                securite_propre[cle] = valeur

        # Le nettoyage automatique. Il n'est pas rangé avec l'anti-raid
        # parce qu'il ne vit pas au même endroit : l'anti-raid est dans
        # guild_settings, celui-ci dans son cog. Le panneau, lui, les montre
        # côte à côte sous « Sécurité ».
        nettoyage = data.get("autoclean")
        nettoyage_propre = None
        if nettoyage is not None:
            if not isinstance(nettoyage, dict):
                return _error(400, "invalid_autoclean")
            cog_nettoyage = self._autoclean_cog()
            if cog_nettoyage is None:
                return _error(400, "autoclean_unavailable")
            actif = nettoyage.get("enabled", False)
            if not isinstance(actif, bool):
                return _error(400, "invalid_autoclean")
            salon_brut = nettoyage.get("channel_id")
            salon_id: int | None = None
            if salon_brut not in (None, ""):
                try:
                    salon_id = int(salon_brut)
                except (TypeError, ValueError):
                    return _error(400, "invalid_autoclean")
            minutes = nettoyage.get("interval_minutes", 20)
            # bool avant int : en Python, True est un entier.
            if isinstance(minutes, bool) or not isinstance(minutes, int):
                return _error(400, "invalid_autoclean")
            # Les bornes sont celles du cog : deux chemins vers le même
            # réglage qui n'accepteraient pas les mêmes valeurs, c'est la
            # promesse d'un panneau qui refuse ce que Discord vient
            # d'enregistrer.
            if not (AUTOCLEAN_MIN <= minutes <= AUTOCLEAN_MAX):
                return _error(400, "invalid_autoclean")
            # Le salon est vérifié ICI, avant la moindre écriture : laissé au
            # cog, son refus arriverait après que la langue, les fonctions et
            # les ressources ont déjà été enregistrées — une configuration à
            # moitié modifiée, et un panneau qui dit « échec ».
            if actif:
                if salon_id is None:
                    return _error(400, "autoclean_salon_manquant")
                if not isinstance(guild.get_channel(salon_id), discord.TextChannel):
                    return _error(400, "wrong_resource_type")
            nettoyage_propre = (actif, salon_id, minutes)

        # L'anti-lien : la liste COMPLÈTE des salons surveillés, pas un
        # ajout. Un lot partiel ne dirait pas lesquels retirer, et il n'y a
        # aucun ordre dans lequel « ajouter » et « retirer » séparément
        # donneraient un résultat prévisible si deux onglets enregistrent.
        antilien = data.get("antilink")
        antilien_propre = None
        if antilien is not None:
            if not isinstance(antilien, dict):
                return _error(400, "invalid_antilink")
            if self._antilink_cog() is None:
                return _error(400, "antilink_unavailable")
            brut = antilien.get("channels")
            if not isinstance(brut, list):
                return _error(400, "invalid_antilink")
            antilien_propre = []
            for valeur in brut:
                try:
                    salon_id = int(valeur)
                except (TypeError, ValueError):
                    return _error(400, "invalid_antilink")
                if not isinstance(guild.get_channel(salon_id), discord.TextChannel):
                    return _error(400, "wrong_resource_type")
                antilien_propre.append(salon_id)

        # La file programmée. Les bornes sont celles de /schedule : deux
        # chemins vers le même réglage qui n'accepteraient pas les mêmes
        # valeurs, c'est un panneau qui refuse ce que Discord vient
        # d'enregistrer.
        programme = data.get("schedule")
        programme_propre = None
        if programme is not None:
            if not isinstance(programme, dict):
                return _error(400, "invalid_schedule")
            programme_propre = {}
            for cle, valeur in programme.items():
                if cle in ("enabled", "reminder"):
                    if not isinstance(valeur, bool):
                        return _error(400, "invalid_schedule")
                elif cle == "time":
                    if not isinstance(valeur, str) or _minutes_du_jour(valeur) is None:
                        return _error(400, "invalid_schedule")
                elif cle == "days":
                    if (not isinstance(valeur, list)
                            or not all(isinstance(j, int) and not isinstance(j, bool)
                                       and 0 <= j <= 6 for j in valeur)):
                        return _error(400, "invalid_schedule")
                    # Dédoublonnés et triés : la liste sert telle quelle à
                    # calculer la prochaine occurrence.
                    valeur = sorted(set(valeur))
                elif cle == "reminder_minutes":
                    if isinstance(valeur, bool) or not isinstance(valeur, int):
                        return _error(400, "invalid_schedule")
                    if not (1 <= valeur <= 1440):
                        return _error(400, "invalid_schedule")
                elif cle == "preset":
                    if valeur is not None and not isinstance(valeur, str):
                        return _error(400, "invalid_schedule")
                else:
                    # `last_run` et `last_reminder` appartiennent au bot : le
                    # panneau n'a pas à raconter ce qui a déjà eu lieu.
                    return _error(400, "invalid_schedule")
                programme_propre[cle] = valeur

        # Les saisons. Même principe : /season les règle déjà.
        saison = data.get("season")
        saison_propre = None
        if saison is not None:
            if not isinstance(saison, dict):
                return _error(400, "invalid_season")
            saison_propre = {}
            for cle, valeur in saison.items():
                if cle in ("enabled", "announce", "keep_history"):
                    if not isinstance(valeur, bool):
                        return _error(400, "invalid_season")
                elif cle == "reset_day":
                    if isinstance(valeur, bool) or not isinstance(valeur, int):
                        return _error(400, "invalid_season")
                    # 28 et pas 31 : un reset au 31 ne tomberait jamais en
                    # février, et la saison ne se fermerait pas ce mois-là.
                    if not (1 <= valeur <= 28):
                        return _error(400, "invalid_season")
                else:
                    # `archive` et `last_reset` sont l'histoire : elle se lit,
                    # elle ne se réécrit pas depuis un formulaire.
                    return _error(400, "invalid_season")
                saison_propre[cle] = valeur

        # Les absences.
        absences = data.get("noshow")
        absences_propre = None
        if absences is not None:
            if not isinstance(absences, dict):
                return _error(400, "invalid_noshow")
            absences_propre = {}
            for cle, valeur in absences.items():
                if cle == "enabled":
                    if not isinstance(valeur, bool):
                        return _error(400, "invalid_noshow")
                elif cle == "threshold":
                    if isinstance(valeur, bool) or not isinstance(valeur, int):
                        return _error(400, "invalid_noshow")
                    # Jamais 1 : une seule déconnexion ne fait pas un joueur
                    # qui se moque du monde, et le bot ne doit pas pouvoir
                    # exclure sur un incident.
                    if not (2 <= valeur <= 20):
                        return _error(400, "invalid_noshow")
                elif cle == "ban_hours":
                    if isinstance(valeur, bool) or not isinstance(valeur, int):
                        return _error(400, "invalid_noshow")
                    if not (1 <= valeur <= 720):
                        return _error(400, "invalid_noshow")
                else:
                    return _error(400, "invalid_noshow")
                absences_propre[cle] = valeur

        # Le webhook sortant. L'adresse est vérifiée ICI, à l'enregistrement :
        # refusée seulement à l'envoi, elle resterait dans la configuration et
        # le panneau l'afficherait comme un réglage valide.
        adresse = data.get("webhook")
        adresse_propre = None
        if adresse is not None:
            if not isinstance(adresse, str):
                return _error(400, "invalid_webhook")
            adresse = adresse.strip()
            if adresse and not url_acceptable(adresse):
                return _error(400, "invalid_webhook")
            adresse_propre = adresse

        # Les exclusions : des GESTES, pas un état. Le panneau envoie
        # « ajoute celui-ci », « retire celui-là ». Remplacer la liste entière
        # effacerait ce qu'un autre onglet vient d'ajouter.
        exclusions = data.get("bans")
        exclusions_propre = None
        if exclusions is not None:
            if not isinstance(exclusions, dict):
                return _error(400, "invalid_bans")
            exclusions_propre = {"add": [], "remove": [], "lift": []}
            for geste in ("add", "remove", "lift"):
                for valeur in (exclusions.get(geste) or []):
                    try:
                        exclusions_propre[geste].append(int(valeur))
                    except (TypeError, ValueError):
                        return _error(400, "invalid_bans")
            motif = exclusions.get("reason")
            if motif is not None and not isinstance(motif, str):
                return _error(400, "invalid_bans")
            exclusions_propre["reason"] = (motif or "")[:200]

        language = data.get("language")
        if language is not None:
            if language not in LANGUAGES:
                return _error(400, "unknown_language")
        # Capturée AVANT l'écriture : la retraduction a besoin de savoir d'où
        # l'on vient pour reconnaître les noms qu'elle a le droit de changer.
        # Lue après set_lang, elle vaudrait déjà la nouvelle langue et le
        # renommage ne trouverait plus rien à faire.
        langue_avant = get_lang(guild.id) if language is not None else None

        features = data.get("features") or {}
        if not isinstance(features, dict):
            return _error(400, "invalid_features")
        for key, value in features.items():
            if key not in FEATURE_DEFAULTS or not isinstance(value, bool):
                return _error(400, "invalid_features")

        resources = data.get("resources") or {}
        if not isinstance(resources, dict):
            return _error(400, "invalid_resources")
        cleaned: dict[str, int | None] = {}
        for key, value in resources.items():
            kind = EDITABLE_RESOURCES.get(key)
            if kind is None:
                return _error(400, "unknown_resource")
            if value in (None, ""):
                cleaned[key] = None
                continue
            try:
                resource_id = int(value)
            except (TypeError, ValueError):
                return _error(400, "invalid_resource_id")
            if not self._matches_kind(guild, resource_id, kind):
                return _error(400, "wrong_resource_type")
            cleaned[key] = resource_id

        logs = data.get("logs") or {}
        if not isinstance(logs, dict):
            return _error(400, "invalid_logs")
        logs_cog = self._logs_cog()
        if logs and logs_cog is None:
            return _error(400, "logs_unavailable")
        logs_cleaned: dict[str, dict[str, Any]] = {}
        for kind, wanted in logs.items():
            if kind not in LOG_KINDS or not isinstance(wanted, dict):
                return _error(400, "invalid_logs")
            entry: dict[str, Any] = {}
            if "on" in wanted:
                if not isinstance(wanted["on"], bool):
                    return _error(400, "invalid_logs")
                entry["on"] = wanted["on"]
            if "channel" in wanted:
                value = wanted["channel"]
                if value in (None, ""):
                    entry["channel"] = None
                else:
                    try:
                        channel_id = int(value)
                    except (TypeError, ValueError):
                        return _error(400, "invalid_logs")
                    if not isinstance(guild.get_channel(channel_id), discord.TextChannel):
                        return _error(400, "wrong_resource_type")
                    entry["channel"] = channel_id
            logs_cleaned[kind] = entry

        # Tout est validé : on écrit seulement maintenant, pour ne pas
        # laisser la configuration à moitié modifiée après une erreur.
        if language is not None:
            set_lang(guild.id, language)
        if logs_cleaned:
            logs_cog.dashboard_update(guild, logs_cleaned)
        if features:
            set_features(guild.id, **features)
        for key, resource_id in cleaned.items():
            if resource_id is None:
                clear_resource_id(guild.id, key)
            else:
                set_resource_id(guild.id, key, resource_id)

        if queue_propre is not None:
            # Fusion, pas remplacement : le site n'envoie que ce qu'il règle,
            # et le reste de la configuration ne lui appartient pas.
            save_queue_config(guild.id, {**(get_queue_config(guild.id) or {}), **queue_propre})
        if mmr_propre:
            set_mmr_config(guild.id, **mmr_propre)
        if mot_de_passe is not None:
            set_queue_password(guild.id, mot_de_passe or None)
        if securite_propre:
            set_antiraid_config(guild.id, **securite_propre)
        if nettoyage_propre is not None:
            actif, salon_id, minutes = nettoyage_propre
            souci = self._autoclean_cog().dashboard_apply(guild, actif, salon_id, minutes)
            if souci is not None:
                # Le cog refait la vérification du salon : lui seul sait si
                # l'identifiant désigne encore un salon textuel de ce serveur.
                return _error(400, souci.lower())

        if antilien_propre is not None:
            await self._antilink_cog().dashboard_apply(guild, antilien_propre)
        if programme_propre:
            set_schedule(guild.id, **programme_propre)
        if saison_propre:
            set_season(guild.id, **saison_propre)
        if absences_propre:
            set_noshow_config(guild.id, **absences_propre)
        if adresse_propre is not None:
            set_webhook_url(guild.id, adresse_propre or None)
        if exclusions_propre:
            for uid in exclusions_propre["add"]:
                add_to_queue_blacklist(guild.id, uid,
                                       exclusions_propre["reason"] or None,
                                       by=auteur_id)
            for uid in exclusions_propre["remove"]:
                remove_from_queue_blacklist(guild.id, uid)
            for uid in exclusions_propre["lift"]:
                # Lever une exclusion automatique, c'est aussi remettre le
                # compteur à zéro : sans cela, la prochaine absence la
                # reposerait immédiatement.
                clear_queue_ban(guild.id, uid)
                reset_noshow(guild.id, uid)

        # Le journal durable. Les NOMS des blocs touchés, jamais leurs
        # valeurs : un journal qui note « mot de passe de queue : hiver2026 »
        # devient lui-même un secret, lisible par tous les administrateurs.
        touches = [cle for cle in data if cle != "actor"]
        if touches:
            audit.record(guild.id, action="settings", source="panel",
                         who_id=auteur_id, who_name=auteur_nom, details=touches)

        log.info(f"Tableau de bord : {guild.name} ({guild.id}) modifié")

        if language is not None and langue_avant != language:
            self._retraduire(guild, langue_avant, language)

        return web.json_response(self._guild_payload(guild))

    def _retraduire(self, guild: discord.Guild, ancienne: str, nouvelle: str) -> None:
        """Rebascule le serveur dans la nouvelle langue, en arrière-plan.

        POURQUOI CECI EXISTE. `set_lang` ne change que les messages À VENIR.
        Les salons et les rôles, eux, ont été CRÉÉS avec un nom traduit au
        moment du /setup, et ce nom reste figé : un serveur passé du français
        à l'anglais gardait `🔱・queue-annonce` et le rôle `Organisateur`.
        Les panneaux déjà publiés restaient eux aussi dans l'ancienne langue.
        C'est tout ce qu'on VOIT d'un bot, et ça ne bougeait pas — d'où
        « je change la langue et il ne se passe rien ».

        `retranslate.py` fait ce travail depuis toujours. Il était appelé par
        /language, qui est partie sur le site le 11/10/2026 : le tableau de
        bord a repris la commande, mais pas ses conséquences. Plus personne
        n'appelait `retranslate_guild`, et seul un redémarrage du bot
        réalignait les noms, par le `repair_guild` de guard.py.

        EN ARRIÈRE-PLAN, et c'est important. Onze ressources renommées à
        0,4 s d'intervalle, plus les panneaux, dépassent les 12 secondes que
        le PHP accorde à son appel (CURLOPT_TIMEOUT dans site/api/index.php).
        Attendre ici ferait répondre « bot injoignable » au panneau pendant
        que le bot, lui, travaille : le pire des deux mondes. On rend donc la
        main tout de suite, et le renommage se poursuit.
        """
        async def courir() -> None:
            try:
                from retranslate import retranslate_guild
                await retranslate_guild(self.bot, guild, ancienne, nouvelle)
            except Exception as e:
                # Un échec ne doit jamais remonter jusqu'à faire tomber la
                # boucle : la langue EST changée, seuls les noms traînent.
                # guard.py les réalignera au prochain démarrage.
                log.error(
                    f"Retraduction {ancienne}→{nouvelle} impossible sur "
                    f"{guild.name} ({guild.id}) : {e}"
                )

        tache = asyncio.create_task(courir())
        self._retraductions.add(tache)
        tache.add_done_callback(self._retraductions.discard)

    # ------------------------------------------------------------------
    # Ce que le bot se souvient : matchs, joueurs, activité, journal
    # ------------------------------------------------------------------
    def _entier(self, request: web.Request, nom: str, defaut: int,
                mini: int, maxi: int) -> int:
        """Un paramètre de requête, borné. Une valeur illisible vaut le
        défaut : refuser la page entière pour un `?limit=abc` serait
        disproportionné."""
        try:
            valeur = int(request.query.get(nom, defaut))
        except (TypeError, ValueError):
            return defaut
        return max(mini, min(maxi, valeur))

    async def list_matches(self, request: web.Request) -> web.Response:
        """Les matchs joués, du plus récent au plus ancien.

        `?player=` filtre sur un joueur, `?season=` sur une saison.
        `total` dit combien sont CONSERVÉS, pas combien ont été joués : au
        delà de history.MAX_MATCHES, les plus vieux sont tombés, et le
        panneau doit pouvoir le dire plutôt que d'afficher un total faux.
        """
        guild = self._guild_or_none(request)
        if guild is None:
            return _error(404, "guild_not_found")

        joueur = request.query.get("player")
        saison = request.query.get("season")
        try:
            joueur_id = int(joueur) if joueur else None
            saison_n = int(saison) if saison else None
        except (TypeError, ValueError):
            return _error(400, "invalid_filter")

        limite = self._entier(request, "limit", 25, 1, 100)
        depuis = self._entier(request, "offset", 0, 0, history.MAX_MATCHES)
        lignes = history.matches(guild.id, limit=limite, offset=depuis,
                                 player_id=joueur_id, season=saison_n)
        return web.json_response({
            "matches": lignes,
            "total": history.match_count(guild.id),
            "kept": history.MAX_MATCHES,
            "season": history.current_season(guild.id),
            # Les pseudos des joueurs cités : le site n'a pas de jeton pour
            # les demander à Discord, et une liste d'identifiants nus n'est
            # lisible par personne.
            "names": self._pseudos(guild, lignes),
        })

    def _pseudos(self, guild: discord.Guild, lignes: list[dict]) -> dict[str, str]:
        noms: dict[str, str] = {}
        for ligne in lignes:
            for uid in (ligne.get("players") or {}):
                if uid not in noms:
                    membre = guild.get_member(int(uid))
                    noms[uid] = membre.display_name if membre else ""
        return noms

    async def player_card(self, request: web.Request) -> web.Response:
        """La fiche d'un joueur : bilan, série, courbe de MMR, partenaires."""
        guild = self._guild_or_none(request)
        if guild is None:
            return _error(404, "guild_not_found")
        try:
            user_id = int(request.match_info["user_id"])
        except (KeyError, TypeError, ValueError):
            return _error(400, "invalid_user")

        fiche = history.player_card(guild.id, user_id)
        membre = guild.get_member(user_id)
        fiche["name"] = membre.display_name if membre else None
        fiche["avatar"] = membre.display_avatar.url if membre else None
        # Le MMR COURANT vient des réglages, pas de l'historique : c'est lui
        # qui fait foi, et un joueur dont les vieux matchs sont tombés en
        # aurait sinon un qui ne correspond à rien.
        config = get_mmr_config(guild.id)
        fiche["mmr"] = get_player_mmr(guild.id, user_id, config["start"])
        fiche["mates"] = [
            {**duo, "name": (guild.get_member(int(duo["id"])).display_name
                             if guild.get_member(int(duo["id"])) else None)}
            for duo in fiche["mates"]
        ]
        return web.json_response(fiche)

    async def activity(self, request: web.Request) -> web.Response:
        """Le relevé d'activité : files ouvertes, lancées, abandonnées,
        attente moyenne, et la répartition par jour et par heure."""
        guild = self._guild_or_none(request)
        if guild is None:
            return _error(404, "guild_not_found")
        jours = self._entier(request, "days", 30, 1, 90)
        return web.json_response(history.stats(guild.id, days=jours))

    async def audit_log(self, request: web.Request) -> web.Response:
        """Qui a changé quoi, depuis le panneau comme depuis Discord."""
        guild = self._guild_or_none(request)
        if guild is None:
            return _error(404, "guild_not_found")
        limite = self._entier(request, "limit", 50, 1, 200)
        return web.json_response({"entries": audit.entries(guild.id, limit=limite)})

    # ------------------------------------------------------------------
    # Ouvrir une queue depuis le site
    # ------------------------------------------------------------------
    async def open_queue(self, request: web.Request) -> web.Response:
        """Ouvre une queue avec la configuration déjà enregistrée.

        C'est exactement ce que fait le bouton « Publier » du panneau
        `/queue`, moins le panneau : même `open_queue`, même configuration
        enregistrée, mêmes salons. Le site ne transmet aucun réglage — s'il
        en envoyait, deux vérités cohabiteraient, celle du site et celle du
        bot, et la queue ouverte ne serait ni l'une ni l'autre.

        Corps (facultatif) :
            {"openedBy": {"id": "123", "name": "Nova"}}

        `openedBy` désigne l'organisateur de la queue : celui que le bot
        traite comme son auteur, et qui apparaît dans les logs. Introuvable
        sur le serveur, on retombe sur le bot lui-même plutôt que de
        refuser : la queue compte plus que la signature.
        """
        guild = self._guild_or_none(request)
        if guild is None:
            return _error(404, "guild_not_found")

        cog = self.bot.get_cog("QueueConfig")
        if cog is None:
            return _error(503, "queue_cog_absent")

        if not queue_ready(guild.id):
            # Salons ou rôle staff manquants : l'assistant n'a jamais tourné.
            return _error(409, "setup_incomplete")

        existing = cog.active_sessions.get(guild.id)
        if existing is not None and not existing.ended:
            return _error(409, "already_open")

        reste = cog.cooldown_restant(guild.id)
        if reste:
            # Le panneau affiche les secondes : « réessaie dans 9 s » se
            # comprend, « trop tôt » ne se comprend pas.
            rep = web.json_response({"error": "cooldown", "retryAfter": reste}, status=409)
            return rep

        config = get_queue_config(guild.id)
        if not config:
            # Jamais aucune queue configurée : il n'y a rien à rouvrir, et
            # inventer un format par défaut serait pire que de refuser.
            return _error(409, "no_config")

        auteur = None
        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            data = {}
        if isinstance(data, dict):
            demandeur = data.get("openedBy") or {}
            if isinstance(demandeur, dict) and demandeur.get("id"):
                try:
                    auteur = guild.get_member(int(demandeur["id"]))
                except (TypeError, ValueError):
                    auteur = None
        if auteur is None:
            auteur = guild.me

        try:
            session = await cog.open_queue(guild, auteur, config)
        except RuntimeError:
            # Aucun salon où publier : c'est la seule erreur que open_queue
            # lève elle-même, et elle se répare dans la configuration.
            return _error(409, "no_channel")
        except discord.Forbidden as refus:
            # Écrit en toutes lettres : le panneau ne peut dire que « droits
            # manquants », alors que Discord, lui, nomme ce qui a manqué.
            log.warning(f"Ouverture de queue refusée par Discord sur {guild.id} : {refus}")
            return _error(409, "missing_permissions")
        except Exception:
            log.exception(f"Ouverture de queue refusée pour {guild.id}")
            return _error(500, "open_failed")

        message = session.message
        log.info(f"Tableau de bord : queue ouverte sur {guild.name} ({guild.id})")
        return web.json_response({
            "channelId": str(message.channel.id) if message else None,
            "messageId": str(message.id) if message else None,
            "messageUrl": message.jump_url if message else None,
            "capacity": session.get_capacity(),
        })

    async def close_queue(self, request: web.Request) -> web.Response:
        """Ferme la queue en cours sur ce serveur.

        Même geste que le bouton « Annuler » du panneau de lancement :
        l'annonce est supprimée, les salons d'équipe aussi, les accès sont
        révoqués et le salon de commande repurgé. C'est donc une fermeture
        définitive, pas une mise en pause — le panneau web le dit avant de
        l'appeler.

        Corps (facultatif) : {"closedBy": {"id": "123", "name": "Nova"}}
        """
        guild = self._guild_or_none(request)
        if guild is None:
            return _error(404, "guild_not_found")

        cog = self.bot.get_cog("QueueConfig")
        if cog is None:
            return _error(503, "queue_cog_absent")

        auteur = None
        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            data = {}
        if isinstance(data, dict):
            demandeur = data.get("closedBy") or {}
            if isinstance(demandeur, dict) and demandeur.get("id"):
                try:
                    auteur = guild.get_member(int(demandeur["id"]))
                except (TypeError, ValueError):
                    auteur = None
        if auteur is None:
            auteur = guild.me

        try:
            resume = await cog.close_queue(guild, auteur)
        except discord.Forbidden as refus:
            log.warning(f"Fermeture de queue refusée par Discord sur {guild.id} : {refus}")
            return _error(409, "missing_permissions")
        except Exception:
            log.exception(f"Fermeture de queue impossible pour {guild.id}")
            return _error(500, "close_failed")

        if resume is None:
            # Rien à fermer : ce n'est pas une panne, c'est un état.
            return _error(409, "no_queue")

        log.info(f"Tableau de bord : queue fermée sur {guild.name} ({guild.id})")
        return web.json_response(resume)

    @staticmethod
    def _matches_kind(guild: discord.Guild, resource_id: int, kind: str) -> bool:
        if kind == "role":
            return guild.get_role(resource_id) is not None
        channel = guild.get_channel(resource_id)
        if kind == "text":
            return isinstance(channel, discord.TextChannel)
        if kind == "category":
            return isinstance(channel, discord.CategoryChannel)
        if kind == "voice":
            return isinstance(channel, discord.VoiceChannel)
        # Un type qu'on ne connaît pas se refuse. Le repli muet sur « vocal »
        # revenait à accepter la première valeur venue pour une clé mal
        # déclarée.
        return False


async def setup(bot: commands.Bot):
    await bot.add_cog(DashboardAPI(bot))
