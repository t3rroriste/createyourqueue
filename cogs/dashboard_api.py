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

import json
import logging
import secrets
import time
from collections import deque
from typing import Any

import discord
from aiohttp import web
from discord.ext import commands

from config import DASHBOARD_API_HOST, DASHBOARD_API_KEY, DASHBOARD_API_PORT, OWNER_ID
from guild_settings import (
    FEATURE_DEFAULTS,
    clear_resource_id,
    get_features,
    get_resource_id,
    is_setup_complete,
    set_features,
    set_resource_id,
)
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
}

# Journal des commandes, gardé en mémoire : il sert à afficher les dernières
# lignes sur le site, pas à archiver. Un redémarrage le remet à zéro, et
# c'est très bien : ces données ne valent pas un fichier sur le disque.
JOURNAL_SIZE = 200
DAY_SECONDS = 24 * 3600
MAX_TIMES_PER_GUILD = 5000


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
        return web.json_response({
            "status": "ok",
            "bot": str(self.bot.user) if self.bot.user else None,
            "guilds": len(self.bot.guilds),
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

    def _guild_payload(self, guild: discord.Guild) -> dict[str, Any]:
        return {
            "id": str(guild.id),
            "name": guild.name,
            "icon": _icon(guild),
            "members": guild.member_count,
            "setup_complete": is_setup_complete(guild.id),
            "language": get_lang(guild.id),
            "languages": {code: info["name"] for code, info in LANGUAGES.items()},
            "features": get_features(guild.id),
            "resources": {
                key: _resource_entry(guild, key) for key in EDITABLE_RESOURCES
            },
        }

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

        language = data.get("language")
        if language is not None:
            if language not in LANGUAGES:
                return _error(400, "unknown_language")

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

        # Tout est validé : on écrit seulement maintenant, pour ne pas
        # laisser la configuration à moitié modifiée après une erreur.
        if language is not None:
            set_lang(guild.id, language)
        if features:
            set_features(guild.id, **features)
        for key, resource_id in cleaned.items():
            if resource_id is None:
                clear_resource_id(guild.id, key)
            else:
                set_resource_id(guild.id, key, resource_id)

        log.info(f"Tableau de bord : {guild.name} ({guild.id}) modifié")
        return web.json_response(self._guild_payload(guild))

    @staticmethod
    def _matches_kind(guild: discord.Guild, resource_id: int, kind: str) -> bool:
        if kind == "role":
            return guild.get_role(resource_id) is not None
        channel = guild.get_channel(resource_id)
        if kind == "text":
            return isinstance(channel, discord.TextChannel)
        return isinstance(channel, discord.VoiceChannel)


async def setup(bot: commands.Bot):
    await bot.add_cog(DashboardAPI(bot))
