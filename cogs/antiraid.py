"""
Cog : Anti-Raid
====================
Détection automatique de raids + verrouillage + auto-kick.

Logique :
- Si ANTIRAID_JOIN_THRESHOLD membres rejoignent en ANTIRAID_JOIN_INTERVAL secondes
  → alerte + lockdown automatique (permission send_messages=False sur @everyone).
- Comptes < ANTIRAID_MIN_ACCOUNT_AGE_HOURS heures → signalés et optionnellement kickés.
- Avec ANTIRAID_AUTO_KICK=True : tout nouveau membre qui arrive pendant un lockdown
  actif est expulsé automatiquement.
"""

import logging
from collections import deque
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_ERROR, COLOR_SUCCESS, COLOR_WARNING
from guild_settings import get_antiraid_config, set_antiraid_config
from i18n import t
from rate_limit import guarded_call
from cogs.logs import send_embed

log = logging.getLogger("bot.antiraid")


def _ts(dt: datetime) -> str:
    return f"<t:{int(dt.timestamp())}:R>"


class AntiRaid(commands.Cog):
    # Groupe de sous-commandes : /antiraid status, /antiraid config...
    antiraid = app_commands.Group(name="antiraid", description="Protection anti-raid du serveur.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled: dict[int, bool] = {}
        self.join_history: dict[int, deque] = {}
        self.raid_lockdown: dict[int, bool] = {}
        self._log_channel_cache: dict[int, int | None] = {}

    def is_enabled(self, guild_id: int) -> bool:
        return self.enabled.get(guild_id, True)

    # ------------------------------------------------------------------
    # Recherche du canal de logs
    # ------------------------------------------------------------------
    def _find_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        if guild.id in self._log_channel_cache:
            cid = self._log_channel_cache[guild.id]
            if cid is None:
                return None
            ch = guild.get_channel(cid)
            if isinstance(ch, discord.TextChannel):
                return ch

        channel = discord.utils.find(
            lambda c: isinstance(c, discord.TextChannel)
            and any(k in c.name.lower() for k in ("log", "mod", "raid")),
            guild.text_channels,
        )
        self._log_channel_cache[guild.id] = channel.id if channel else None
        return channel  # type: ignore[return-value]

    async def _send_alert(self, guild: discord.Guild, embed: discord.Embed):
        log.warning(f"[{guild.name}] {embed.description or embed.title}")
        # Le salon de /logs-moderation d'abord ; deviner un salon d'après son
        # nom reste le repli des serveurs qui n'en ont pas désigné.
        if send_embed(self.bot, guild.id, "moderation", embed):
            return
        channel = self._find_log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    # ------------------------------------------------------------------
    # Listener
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild

        if not self.is_enabled(guild.id):
            return

        cfg = get_antiraid_config(guild.id)
        now = datetime.now(timezone.utc)

        # --- Auto-kick pendant un lockdown actif ---
        if self.raid_lockdown.get(guild.id, False) and cfg["auto_kick"]:
            try:
                # Un raid fait arriver plusieurs comptes en même temps : chaque
                # arrivée déclenche ce handler en parallèle.
                await guarded_call(
                    member.kick(reason="Anti-raid : arrivée pendant lockdown actif"),
                    guild_id=guild.id,
                    action="antiraid_kick",
                    concurrency=2,
                )
                embed = discord.Embed(
                    title=t(guild.id, "antiraid.lockdown_title"),
                    description=t(
                        guild.id,
                        "antiraid.autokick_alert",
                        mention=member.mention,
                        member=str(member),
                        created=_ts(member.created_at),
                    ),
                    color=COLOR_ERROR,
                    timestamp=discord.utils.utcnow(),
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                await self._send_alert(guild, embed)
            except discord.Forbidden:
                pass
            return

        # --- Fenêtre glissante ---
        history = self.join_history.setdefault(guild.id, deque())
        history.append(now)
        while history and (now - history[0]).total_seconds() > cfg["join_interval"]:
            history.popleft()

        # --- Compte récent ---
        account_age_hours = (now - member.created_at).total_seconds() / 3600
        if account_age_hours < cfg["min_account_age_hours"]:
            embed = discord.Embed(
                title=t(guild.id, "antiraid.status_title"),
                description=t(
                    guild.id,
                    "antiraid.suspicious_account",
                    mention=member.mention,
                    member=str(member),
                    created=_ts(member.created_at),
                ),
                color=COLOR_WARNING,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await self._send_alert(guild, embed)

        # --- Seuil de raid ---
        if len(history) >= cfg["join_threshold"] and not self.raid_lockdown.get(guild.id, False):
            await self._trigger_lockdown(guild, len(history), cfg)

    # ------------------------------------------------------------------
    # Lockdown
    # ------------------------------------------------------------------
    async def _trigger_lockdown(self, guild: discord.Guild, join_count: int, cfg: dict):
        self.raid_lockdown[guild.id] = True
        everyone = guild.default_role
        locked = 0

        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(everyone)
                overwrite.send_messages = False
                await channel.set_permissions(everyone, overwrite=overwrite, reason="Anti-raid auto-lockdown")
                locked += 1
            except discord.Forbidden:
                continue

        embed = discord.Embed(
            title=t(guild.id, "antiraid.lockdown_title"),
            color=COLOR_ERROR,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name=t(guild.id, "antiraid.field_trigger"),
            value=t(guild.id, "antiraid.lockdown_trigger", count=join_count, interval=cfg["join_interval"]),
            inline=True,
        )
        embed.add_field(
            name=t(guild.id, "antiraid.field_locked"),
            value=t(guild.id, "antiraid.lockdown_channels_value", count=locked),
            inline=True,
        )
        embed.add_field(
            name=t(guild.id, "antiraid.lockdown_autokick"),
            value=t(guild.id, "antiraid.toggled_on") if cfg["auto_kick"] else t(guild.id, "antiraid.toggled_off"),
            inline=True,
        )
        await self._send_alert(guild, embed)

    # ------------------------------------------------------------------
    # Commandes
    # ------------------------------------------------------------------
    @antiraid.command(name="status", description="Affiche l'état du système anti-raid.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        cfg = get_antiraid_config(gid)
        enabled  = self.is_enabled(gid)
        lockdown = self.raid_lockdown.get(gid, False)
        recent   = len(self.join_history.get(gid, deque()))

        embed = discord.Embed(
            title=t(gid, "antiraid.status_title"),
            color=COLOR_SUCCESS if enabled else COLOR_ERROR,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name=t(gid, "antiraid.status_enabled"),
            value=t(gid, "antiraid.toggled_on") if enabled else t(gid, "antiraid.toggled_off"),
            inline=True,
        )
        embed.add_field(
            name=t(gid, "antiraid.lockdown_title"),
            value=t(gid, "antiraid.status_enabled") if lockdown else t(gid, "antiraid.status_disabled"),
            inline=True,
        )
        embed.add_field(
            name=t(gid, "antiraid.lockdown_autokick"),
            value=t(gid, "antiraid.toggled_on") if cfg["auto_kick"] else t(gid, "antiraid.toggled_off"),
            inline=True,
        )
        embed.add_field(
            name=t(gid, "antiraid.field_trigger"),
            value=t(gid, "antiraid.config_trigger", threshold=cfg["join_threshold"], interval=cfg["join_interval"]),
            inline=True,
        )
        embed.add_field(
            name=t(gid, "antiraid.field_min_age"),
            value=t(gid, "antiraid.config_min_age", hours=cfg["min_account_age_hours"]),
            inline=True,
        )
        embed.add_field(
            name=t(gid, "antiraid.field_recent_joins"),
            value=f"**{recent}** / {cfg['join_threshold']}",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antiraid.command(name="config", description="Configure les seuils de détection anti-raid.")
    @app_commands.describe(
        seuil="Nombre d'arrivées qui déclenche le lockdown (défaut serveur si omis)",
        intervalle="Fenêtre de temps en secondes pour ce seuil",
        age_minimum="Âge minimum du compte en heures avant d'être signalé comme suspect",
        auto_kick="Expulser automatiquement les nouveaux arrivants pendant un lockdown actif",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config(
        self,
        interaction: discord.Interaction,
        seuil: app_commands.Range[int, 2, 100] | None = None,
        intervalle: app_commands.Range[int, 2, 300] | None = None,
        age_minimum: app_commands.Range[int, 0, 720] | None = None,
        auto_kick: bool | None = None,
    ):
        gid = interaction.guild_id
        overrides = {}
        if seuil is not None:
            overrides["join_threshold"] = seuil
        if intervalle is not None:
            overrides["join_interval"] = intervalle
        if age_minimum is not None:
            overrides["min_account_age_hours"] = age_minimum
        if auto_kick is not None:
            overrides["auto_kick"] = auto_kick

        if overrides:
            set_antiraid_config(gid, **overrides)

        cfg = get_antiraid_config(gid)
        embed = discord.Embed(
            description=t(gid, "antiraid.config_success") + "\n" + t(
                gid, "antiraid.config_current",
                threshold=cfg["join_threshold"], interval=cfg["join_interval"],
                age=cfg["min_account_age_hours"],
                autokick=(t(gid, "antiraid.toggled_on") if cfg["auto_kick"] else t(gid, "antiraid.toggled_off")),
            ),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antiraid.command(name="toggle", description="Active ou désactive le système anti-raid.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        current = self.is_enabled(gid)
        self.enabled[gid] = not current
        embed = discord.Embed(
            description=t(gid, "antiraid.toggled_on") if not current else t(gid, "antiraid.toggled_off"),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antiraid.command(name="unlock", description="Lève le verrouillage anti-raid sur tous les salons.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def unlock(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild    = interaction.guild
        everyone = guild.default_role
        unlocked = 0

        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(everyone)
                overwrite.send_messages = None
                await channel.set_permissions(everyone, overwrite=overwrite, reason="Anti-raid manual unlock")
                unlocked += 1
            except discord.Forbidden:
                continue

        self.raid_lockdown[guild.id] = False
        self.join_history[guild.id]  = deque()

        embed = discord.Embed(
            description=t(interaction.guild_id, "antiraid.unlocked",
                          member=interaction.user.mention, count=unlocked),
            color=COLOR_SUCCESS,
            timestamp=discord.utils.utcnow(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Gestion d'erreurs
    # ------------------------------------------------------------------
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                description=t(interaction.guild_id, "antiraid.error_permission"),
                color=COLOR_ERROR,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            log.exception("Erreur dans le cog antiraid", exc_info=error)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
