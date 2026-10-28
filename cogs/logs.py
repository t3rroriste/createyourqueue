"""
Cog : Logs
===========
Un salon par type d'événement, que l'on allume et que l'on coupe à la carte.

    /logs-vocal activer:True salon:#logs-vocal   active, dans ce salon
    /logs-vocal activer:False                    coupe (le salon reste mémorisé)
    /logs-vocal activer:True                     rallume dans le salon mémorisé
    /logs-tout  activer:True salon:#logs         tous les types d'un coup
    /logs                                        l'état de chaque type
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import timedelta
from typing import Any, Iterable

import discord
from discord.ext import commands

import embeds
from i18n import t
from json_store import write_json
from text_safety import sanitize

log = logging.getLogger("bot.logs")

LOGS_SAVE_FILE = "data/logs.json"

# type -> (icône, couleur par défaut). L'ordre est celui de /logs.
KINDS: dict[str, tuple[str, int]] = {
    "vocal":      ("🎤", 0x3498DB),
    "message":    ("💬", 0x95A5A6),
    "queue":      ("🔔", 0xF1C40F),
    "match":      ("🎮", 0x5865F2),
    "duel":       ("⚔️", 0xE74C3C),
    "clan":       ("🛡️", 0x9B59B6),
    "commande":   ("⚡", 0xEB459E),
    "join":       ("👋", 0x1ABC9C),
    "moderation": ("🔨", 0xED4245),
    "serveur":    ("🏠", 0xE67E22),
}

# Couleurs d'action, pour qu'une arrivée et un départ se distinguent d'un coup d'œil.
GREEN = embeds.SUCCESS
RED = embeds.ERROR
YELLOW = embeds.WARNING

# Ce qu'il faut au bot pour publier un log.
_SEND_PERMS = ("view_channel", "send_messages", "embed_links")



# ----------------------------------------------------------------------
# Point d'entrée pour les autres cogs
# ----------------------------------------------------------------------
def send_log(
    bot: commands.Bot,
    guild_id: int | None,
    kind: str,
    title: str,
    *,
    description: str | None = None,
    user: discord.abc.User | None = None,
    fields: Iterable[tuple] = (),
    color: int | None = None,
    thumbnail: str | None = None,
) -> None:
    """Publie un log si ce type est activé sur ce serveur. Ne lève jamais."""
    cog = bot.get_cog("Logs")
    if cog is None or guild_id is None:
        return
    cog.emit(guild_id, kind, title, description=description, user=user,
             fields=fields, color=color, thumbnail=thumbnail)


def send_embed(bot: commands.Bot, guild_id: int | None, kind: str, embed: discord.Embed) -> bool:
    """Publie un embed déjà construit. Renvoie False si ce type n'a pas de
    salon actif, pour que l'appelant puisse se rabattre ailleurs."""
    cog = bot.get_cog("Logs")
    if cog is None or guild_id is None:
        return False
    return cog.emit_embed(guild_id, kind, embed)


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _who(user: discord.abc.User) -> str:
    """« Pseudo (@nom) » : le pseudo change, le nom d'utilisateur beaucoup moins."""
    if getattr(user, "display_name", user.name) != user.name:
        return f"{user.display_name} (@{user.name})"
    return f"@{user.name}"


def _stamp(moment) -> str:
    ts = int(moment.timestamp())
    return f"<t:{ts}:D> (<t:{ts}:R>)"


def _option_value(value: Any) -> str:
    if hasattr(value, "mention"):
        return value.mention
    return sanitize(str(value), 200)


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> type -> {"on": bool, "channel": id du salon}
        self.config: dict[int, dict[str, dict[str, Any]]] = {}
        # Les envois partent en tâche de fond : on garde une référence,
        # sinon Python peut les ramasser avant qu'elles aient fini.
        self._pending: set[asyncio.Task] = set()
        # (serveur, type) dont le dernier envoi a échoué : une seule ligne
        # d'avertissement par panne, pas une par message du serveur.
        self._failing: set[tuple[int, str]] = set()
        self._load()

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    def _load(self) -> None:
        """Relit les réglages. Un fichier illisible est mis de côté, jamais
        écrasé par le premier réglage qui suit (même règle que guild_settings)."""
        if not os.path.exists(LOGS_SAVE_FILE):
            return
        try:
            with open(LOGS_SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for gid, kinds in data.items():
                entries = {}
                for kind, value in kinds.items():
                    if kind not in KINDS:
                        continue
                    if isinstance(value, dict):
                        entries[kind] = {"on": bool(value.get("on")),
                                         "channel": int(value.get("channel") or 0)}
                    else:
                        # Ancien format : {type: id du salon}, toujours actif.
                        entries[kind] = {"on": True, "channel": int(value)}
                self.config[int(gid)] = entries
        except (OSError, ValueError, TypeError, AttributeError) as e:
            self.config = {}
            backup = f"{LOGS_SAVE_FILE}.illisible-{int(time.time())}"
            try:
                os.replace(LOGS_SAVE_FILE, backup)
                log.error(f"Réglages des logs illisibles ({e}) : fichier mis de côté dans {backup}")
            except OSError:
                log.error(f"Réglages des logs illisibles ({e}), et impossibles à mettre de côté")
            return
        log.info(f"Logs chargés : {len(self.config)} serveur(s)")

    def _save(self) -> None:
        try:
            write_json(LOGS_SAVE_FILE, {str(gid): kinds for gid, kinds in self.config.items()}, indent=4)
        except Exception as e:
            log.error(f"Erreur sauvegarde logs : {e}")

    # ------------------------------------------------------------------
    # Envoi
    # ------------------------------------------------------------------
    def target(self, guild_id: int, kind: str) -> discord.TextChannel | None:
        """Le salon actif pour ce type, ou None (coupé, jamais réglé, supprimé)."""
        entry = self.config.get(guild_id, {}).get(kind)
        if not entry or not entry.get("on"):
            return None
        channel = self.bot.get_channel(entry.get("channel") or 0)
        return channel if isinstance(channel, discord.TextChannel) else None

    def build(
        self,
        guild_id: int,
        kind: str,
        title: str,
        *,
        description: str | None = None,
        user: discord.abc.User | None = None,
        fields: Iterable[tuple] = (),
        color: int | None = None,
        thumbnail: str | None = None,
    ) -> discord.Embed:
        icon, default_color = KINDS[kind]
        embed = discord.Embed(
            title=_cut(f"{icon}  {title}", 256),
            description=_cut(description, 4096) if description else None,
            color=default_color if color is None else color,
            timestamp=discord.utils.utcnow(),
        )
        footer = t(guild_id, f"logs.kind_{kind}")
        if user is not None:
            embed.set_author(name=_cut(_who(user), 256), icon_url=user.display_avatar.url)
            footer += f"  ·  ID {user.id}"
        embed.set_footer(text=footer)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        for field in list(fields)[:25]:
            name, value, *rest = field
            if value is None or value == "":
                continue
            embed.add_field(name=_cut(str(name), 256), value=_cut(str(value), 1024),
                            inline=rest[0] if rest else True)
        return embed

    def emit(self, guild_id: int, kind: str, title: str, **kwargs: Any) -> None:
        try:
            channel = self.target(guild_id, kind)
            if channel is None:
                return
            self._deliver(channel, guild_id, kind, self.build(guild_id, kind, title, **kwargs))
        except Exception:
            log.exception(f"Log {kind} non construit")

    def emit_embed(self, guild_id: int, kind: str, embed: discord.Embed) -> bool:
        channel = self.target(guild_id, kind)
        if channel is None:
            return False
        self._deliver(channel, guild_id, kind, embed)
        return True

    def _deliver(self, channel: discord.TextChannel, guild_id: int, kind: str, embed: discord.Embed) -> None:
        # Tous les logs en rouge, quel que soit leur type.
        embed.colour = RED
        task = asyncio.create_task(self._send(channel, guild_id, kind, embed))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _send(self, channel: discord.TextChannel, guild_id: int, kind: str, embed: discord.Embed) -> None:
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            if (guild_id, kind) not in self._failing:
                self._failing.add((guild_id, kind))
                log.warning(f"[{channel.guild.name}] Log {kind} non publié dans #{channel.name} : {e}")
            return
        self._failing.discard((guild_id, kind))

    async def _audit_entry(self, guild: discord.Guild, action: discord.AuditLogAction,
                           target_id: int) -> discord.AuditLogEntry | None:
        """Qui a fait quoi, d'après le journal d'audit du serveur."""
        if not guild.me.guild_permissions.view_audit_log:
            return None
        await asyncio.sleep(1)
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if (getattr(entry.target, "id", None) == target_id
                        and discord.utils.utcnow() - entry.created_at < timedelta(seconds=30)):
                    return entry
        except discord.HTTPException:
            return None
        return None

    @staticmethod
    def _missing_perms(channel: discord.TextChannel) -> list[str]:
        perms = channel.permissions_for(channel.guild.me)
        return [name for name in _SEND_PERMS if not getattr(perms, name)]

    # ------------------------------------------------------------------
    # Lu et écrit par le tableau de bord (voir cogs/dashboard_api.py)
    #
    # Les commandes /logs, /logs-vocal, /logs-message… ont été retirées le
    # 11/10/2026 : douze commandes pour cocher dix cases, c'était le genre
    # de réglage qui se fait mieux sur une page web. Le cog, lui, écrit
    # toujours les logs exactement comme avant.
    # ------------------------------------------------------------------
    def dashboard_state(self, guild: discord.Guild) -> dict[str, dict]:
        """L'état de chaque type : allumé ou non, et dans quel salon."""
        entries = self.config.get(guild.id, {})
        state = {}
        for kind in KINDS:
            entry = entries.get(kind) or {}
            channel_id = entry.get("channel")
            channel = guild.get_channel(channel_id) if channel_id else None
            state[kind] = {
                "on": bool(entry.get("on")),
                "channel": str(channel_id) if channel_id else None,
                # Le site affiche « à redésigner » quand le salon a disparu.
                "channel_name": channel.name if channel is not None else None,
                # Et prévient quand le bot n'a pas le droit d'y écrire :
                # sinon le type reste allumé et silencieux, sans raison visible.
                "writable": (not self._missing_perms(channel)
                             if isinstance(channel, discord.TextChannel) else None),
            }
        return state

    def dashboard_update(self, guild: discord.Guild, changes: dict[str, dict]) -> None:
        """Applique ce que le site envoie : un salon et un interrupteur par type."""
        entries = self.config.setdefault(guild.id, {})
        for kind, wanted in changes.items():
            entry = entries.setdefault(kind, {"on": False, "channel": None})
            if "channel" in wanted:
                entry["channel"] = wanted["channel"]
            if "on" in wanted:
                entry["on"] = bool(wanted["on"])
            # Allumé sans salon, ça n'écrit nulle part : autant l'éteindre
            # pour de bon, et que le site le montre éteint.
            if entry["on"] and not entry["channel"]:
                entry["on"] = False
        self._save()

    # ------------------------------------------------------------------
    # Vocal
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        gid = member.guild.id
        if member.bot or self.target(gid, "vocal") is None:
            return
        channel_field = t(gid, "logs.f_channel")

        if before.channel != after.channel:
            if before.channel is None:
                self.emit(gid, "vocal", t(gid, "logs.voice_join"), user=member, color=GREEN,
                          fields=[(channel_field, after.channel.mention)])
            elif after.channel is None:
                self.emit(gid, "vocal", t(gid, "logs.voice_leave"), user=member, color=RED,
                          fields=[(channel_field, before.channel.mention)])
            else:
                self.emit(gid, "vocal", t(gid, "logs.voice_move"), user=member,
                          fields=[(t(gid, "logs.f_from"), before.channel.mention),
                                  (t(gid, "logs.f_to"), after.channel.mention)])
            return

        here = [(channel_field, after.channel.mention if after.channel else None)]
        if before.mute != after.mute:
            self.emit(gid, "vocal", t(gid, "logs.voice_mute" if after.mute else "logs.voice_unmute"),
                      user=member, color=YELLOW if after.mute else GREEN, fields=here)
        if before.deaf != after.deaf:
            self.emit(gid, "vocal", t(gid, "logs.voice_deaf" if after.deaf else "logs.voice_undeaf"),
                      user=member, color=YELLOW if after.deaf else GREEN, fields=here)
        if before.self_stream != after.self_stream:
            self.emit(gid, "vocal", t(gid, "logs.voice_stream_on" if after.self_stream else "logs.voice_stream_off"),
                      user=member, fields=here)

    # ------------------------------------------------------------------
    # Messages
    #
    # Seuls les messages modifiés et supprimés sont journalisés : copier
    # chaque message envoyé doublerait le salon, pour rien.
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild is None or after.author.bot or before.content == after.content:
            return
        gid = after.guild.id
        self.emit(gid, "message", t(gid, "logs.msg_edited"), user=after.author,
                  description=f"[{t(gid, 'logs.jump')}]({after.jump_url})",
                  fields=[(t(gid, "logs.f_channel"), after.channel.mention),
                          (t(gid, "logs.f_before"), before.content or "—", False),
                          (t(gid, "logs.f_after"), after.content or "—", False)])

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        gid = message.guild.id
        files = ", ".join(a.filename for a in message.attachments)
        self.emit(gid, "message", t(gid, "logs.msg_deleted"), user=message.author, color=RED,
                  fields=[(t(gid, "logs.f_channel"), message.channel.mention),
                          (t(gid, "logs.f_sent"), f"<t:{int(message.created_at.timestamp())}:R>"),
                          (t(gid, "logs.f_content"), message.content or "—", False),
                          (t(gid, "logs.f_attachments"), files, False)])

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        gid = payload.guild_id
        if gid is None:
            return
        self.emit(gid, "message", t(gid, "logs.msg_bulk"), color=RED,
                  fields=[(t(gid, "logs.f_channel"), f"<#{payload.channel_id}>"),
                          (t(gid, "logs.f_count"), len(payload.message_ids))])

    # ------------------------------------------------------------------
    # Arrivées, départs, et modération vue du serveur
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        gid = member.guild.id
        recent = discord.utils.utcnow() - member.created_at < timedelta(days=7)
        self.emit(gid, "join", t(gid, "logs.member_join"), user=member,
                  thumbnail=member.display_avatar.url, color=YELLOW if recent else GREEN,
                  description=member.mention + ("\n" + t(gid, "logs.new_account") if recent else ""),
                  fields=[(t(gid, "logs.f_created"), _stamp(member.created_at)),
                          (t(gid, "logs.f_members"), member.guild.member_count)])

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        gid = member.guild.id
        roles = " ".join(r.mention for r in reversed(member.roles) if not r.is_default())
        self.emit(gid, "join", t(gid, "logs.member_leave"), user=member,
                  thumbnail=member.display_avatar.url, color=RED,
                  description=member.mention,
                  fields=[(t(gid, "logs.f_joined"), _stamp(member.joined_at) if member.joined_at else None),
                          (t(gid, "logs.f_members"), member.guild.member_count),
                          (t(gid, "logs.f_roles"), roles, False)])

        # Un départ peut être une expulsion : seul le journal d'audit le dit.
        if self.target(gid, "moderation") is not None:
            entry = await self._audit_entry(member.guild, discord.AuditLogAction.kick, member.id)
            if entry is not None:
                self._mod_from_audit(gid, "logs.mod_kick", member, entry)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if self.target(guild.id, "moderation") is None:
            return
        entry = await self._audit_entry(guild, discord.AuditLogAction.ban, user.id)
        self._mod_from_audit(guild.id, "logs.mod_ban", user, entry)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if self.target(guild.id, "moderation") is None:
            return
        entry = await self._audit_entry(guild, discord.AuditLogAction.unban, user.id)
        self._mod_from_audit(guild.id, "logs.mod_unban", user, entry, color=GREEN)

    def _mod_from_audit(self, gid: int, key: str, user: discord.abc.User,
                        entry: discord.AuditLogEntry | None, *, color: int | None = None,
                        extra: Iterable[tuple] = ()) -> None:
        self.emit(gid, "moderation", t(gid, key), user=user, color=color,
                  description=user.mention,
                  fields=[(t(gid, "logs.f_by"), entry.user.mention if entry and entry.user else None),
                          *extra,
                          (t(gid, "logs.f_reason"), (entry.reason if entry else None) or t(gid, "logs.no_reason"), False)])

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        gid = after.guild.id

        if before.nick != after.nick:
            self.emit(gid, "serveur", t(gid, "logs.nick_change"), user=after,
                      fields=[(t(gid, "logs.f_before"), before.nick or before.name),
                              (t(gid, "logs.f_after"), after.nick or after.name)])

        added = [r.mention for r in after.roles if r not in before.roles]
        removed = [r.mention for r in before.roles if r not in after.roles]
        if added or removed:
            self.emit(gid, "serveur", t(gid, "logs.roles_change"), user=after,
                      fields=[(t(gid, "logs.f_added"), " ".join(added), False),
                              (t(gid, "logs.f_removed"), " ".join(removed), False)])

        # Sourdine posée depuis Discord.
        if (before.timed_out_until != after.timed_out_until
                and self.target(gid, "moderation") is not None):
            entry = await self._audit_entry(after.guild, discord.AuditLogAction.member_update, after.id)
            if entry is None or (entry.user and entry.user.id == self.bot.user.id):
                return
            if after.is_timed_out():
                self._mod_from_audit(gid, "logs.mod_timeout", after, entry, color=YELLOW, extra=[
                    (t(gid, "logs.f_until"), f"<t:{int(after.timed_out_until.timestamp())}:R>")])
            else:
                self._mod_from_audit(gid, "logs.mod_untimeout", after, entry, color=GREEN)

    # ------------------------------------------------------------------
    # Commandes utilisées
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        gid = interaction.guild_id
        if gid is None or self.target(gid, "commande") is None:
            return
        # Format court, une ligne comme le message du /lock : ce log tombe à
        # chaque commande.
        icon, color = KINDS["commande"]
        line = f"{icon} **/{command.qualified_name}** · {interaction.user.mention}"
        channel = getattr(interaction.channel, "mention", None)
        if channel:
            line += f" · {channel}"
        options = " · ".join(f"`{name}` : {_option_value(value).replace(chr(10), ' ')}"
                             for name, value in interaction.namespace)
        if options:
            line += f"\n-# {options}"
        self.emit_embed(gid, "commande", discord.Embed(description=_cut(line, 4096), color=color))

    # ------------------------------------------------------------------
    # Salons et rôles
    # ------------------------------------------------------------------
    def _channel_fields(self, gid: int, channel: discord.abc.GuildChannel, *, mention: bool) -> list[tuple]:
        return [(t(gid, "logs.f_channel"), f"{channel.mention} (`{channel.name}`)" if mention else f"`{channel.name}`"),
                (t(gid, "logs.f_type"), str(channel.type)),
                (t(gid, "logs.f_category"), channel.category.name if channel.category else None)]

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        gid = channel.guild.id
        self.emit(gid, "serveur", t(gid, "logs.channel_create"), color=GREEN,
                  fields=self._channel_fields(gid, channel, mention=True))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        gid = channel.guild.id
        self.emit(gid, "serveur", t(gid, "logs.channel_delete"), color=RED,
                  fields=self._channel_fields(gid, channel, mention=False))

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        gid = role.guild.id
        self.emit(gid, "serveur", t(gid, "logs.role_create"), color=GREEN,
                  fields=[(t(gid, "logs.f_role"), f"{role.mention} (`{role.name}`)")])

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        gid = role.guild.id
        self.emit(gid, "serveur", t(gid, "logs.role_delete"), color=RED,
                  fields=[(t(gid, "logs.f_role"), f"`{role.name}`")])


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
