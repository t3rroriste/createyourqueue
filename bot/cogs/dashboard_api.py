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
import re
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
    get_antiraid_config,
    set_antiraid_config,
    MMR_DEFAULTS,
    clear_resource_id,
    get_features,
    get_queue_config,
    get_mmr_config,
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
from cogs.logs import KINDS as LOG_KINDS
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
        # Les retraductions en cours. asyncio ne garde qu'une référence
        # FAIBLE sur une tâche lancée par create_task : sans ce jeu, le
        # ramasse-miettes peut l'emporter en plein milieu, et le renommage
        # s'arrête sans la moindre trace.
        self._retraductions: set[asyncio.Task] = set()

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

    def _logs_cog(self):
        """Le cog des logs, qui garde sa configuration à lui (data/logs.json)."""
        return self.bot.get_cog("Logs")

    def _guild_payload(self, guild: discord.Guild) -> dict[str, Any]:
        logs = self._logs_cog()
        return {
            "logs": logs.dashboard_state(guild) if logs is not None else {},
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
