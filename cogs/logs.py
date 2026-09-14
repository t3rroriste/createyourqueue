"""
Cog : Logs
===========
Système de journalisation avec embeds colorés et timestamps Discord.
Commande : /logs — un salon par type d'événement (ou le même pour tout).

Types : vocal, queue, modération, messages, commandes, arrivées.
"""

import logging
import json
import os
import time

import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_SUCCESS
from i18n import t
from json_store import write_json

log = logging.getLogger("bot.logs")

LOGS_SAVE_FILE = "data/logs.json"

# Couleur par type de log
_LOG_COLORS = {
    "vocal":      discord.Color.blue(),
    "queue":      discord.Color.gold(),
    "moderation": discord.Color.red(),
    "message":    discord.Color.greyple(),
    "commande":   discord.Color.purple(),
    "join":       discord.Color.teal(),
}

_LOG_ICONS = {
    "vocal":      "🎤",
    "queue":      "🔔",
    "moderation": "🛡️",
    "message":    "💬",
    "commande":   "⚡",
    "join":       "👋",
}


def _now_ts() -> str:
    """Retourne un timestamp Discord relatif."""
    return f"<t:{int(time.time())}:R>"


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_channels: dict[int, dict[str, int]] = {}
        self.log_types = ["vocal", "queue", "moderation", "message", "commande", "join"]
        self.bot.loop.create_task(self.load_logs_config())

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    async def load_logs_config(self):
        await self.bot.wait_until_ready()
        if not os.path.exists(LOGS_SAVE_FILE):
            os.makedirs(os.path.dirname(LOGS_SAVE_FILE), exist_ok=True)
            return
        try:
            with open(LOGS_SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for gid_str, channels in data.items():
                gid = int(gid_str)
                self.log_channels[gid] = {k: int(v) for k, v in channels.items()}
            log.info(f"Logs chargés : {len(self.log_channels)} serveur(s)")
        except Exception as e:
            log.error(f"Erreur chargement logs : {e}")

    async def save_logs_config(self):
        try:
            write_json(LOGS_SAVE_FILE, self.log_channels, indent=4)
        except Exception as e:
            log.error(f"Erreur sauvegarde logs : {e}")

    # ------------------------------------------------------------------
    # Envoi centralisé (embed)
    # ------------------------------------------------------------------
    async def _send_log(self, guild_id: int, log_type: str, embed: discord.Embed):
        """Envoie un embed de log dans le channel configuré pour ce type."""
        channels = self.log_channels.get(guild_id, {})
        channel_id = channels.get(log_type)
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    def _base_embed(self, guild_id: int, log_type: str, description: str) -> discord.Embed:
        embed = discord.Embed(
            description=description,
            color=_LOG_COLORS.get(log_type, discord.Color.default()),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"{_LOG_ICONS.get(log_type, '•')} Logs · {log_type.capitalize()}")
        return embed

    # ------------------------------------------------------------------
    # Méthodes publiques de log
    # ------------------------------------------------------------------
    async def add_voice_log(
        self,
        member: discord.Member,
        action: str,
        channel: discord.VoiceChannel | None = None,
    ):
        guild_id = member.guild.id
        channel_text = channel.mention if channel else "—"
        if action == "a rejoint":
            desc = t(guild_id, "logs.voice_join", member=member.mention, channel=channel_text, ts=_now_ts())
        else:
            desc = t(guild_id, "logs.voice_leave", member=member.mention, channel=channel_text, ts=_now_ts())
        embed = self._base_embed(guild_id, "vocal", desc)
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        await self._send_log(guild_id, "vocal", embed)

    async def add_queue_log(self, action: str, author: discord.Member, details: str = ""):
        guild_id = author.guild.id
        desc = t(guild_id, "logs.queue_log", ts=_now_ts(), member=author.mention, action=action)
        if details:
            desc += f"\n> {details}"
        embed = self._base_embed(guild_id, "queue", desc)
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
        await self._send_log(guild_id, "queue", embed)

    _MESSAGE_LOG_KEYS = {
        "sent": "logs.msg_sent",
        "edited": "logs.msg_edited",
        "deleted": "logs.msg_deleted",
    }

    async def add_message_log(
        self, member: discord.Member, channel: discord.TextChannel, content: str, action: str = "sent"
    ):
        guild_id = member.guild.id
        preview = content[:200] + "…" if len(content) > 200 else content
        key = self._MESSAGE_LOG_KEYS.get(action, self._MESSAGE_LOG_KEYS["sent"])
        desc = t(guild_id, key, ts=_now_ts(), member=member.mention, channel=channel.mention, content=preview)
        embed = self._base_embed(guild_id, "message", desc)
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        await self._send_log(guild_id, "message", embed)

    async def add_commande_log(self, member: discord.Member, command: str, details: str = ""):
        guild_id = member.guild.id
        desc = t(guild_id, "logs.cmd_used", ts=_now_ts(), member=member.mention, command=command)
        if details:
            desc += f"\n> {details}"
        embed = self._base_embed(guild_id, "commande", desc)
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        await self._send_log(guild_id, "commande", embed)

    async def add_moderation_log(self, guild_id: int, embed: discord.Embed):
        """Copie d'une sanction dans le salon de logs de modération.

        L'ancien `/modlog` gardait son salon dans un simple dictionnaire en
        mémoire : le réglage disparaissait au premier redémarrage. Ici, le
        salon vient de `/logs`, qui est enregistré sur disque."""
        embed.set_footer(text=f"{_LOG_ICONS['moderation']} Logs · Modération")
        await self._send_log(guild_id, "moderation", embed)

    async def add_join_log(self, member: discord.Member):
        guild_id = member.guild.id
        now = discord.utils.utcnow()
        account_age = (now - member.created_at).days
        created_ts  = f"<t:{int(member.created_at.timestamp())}:D>"

        if account_age < 7:
            age_text = t(guild_id, "logs.join_new_account", days=account_age)
        else:
            age_text = f"{account_age} jour(s)"

        desc = t(
            guild_id,
            "logs.join_title",
            ts=_now_ts(),
            member=member.mention,
            created=created_ts,
            age=age_text,
        )
        embed = self._base_embed(guild_id, "join", desc)
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(guild_id, "join", embed)

    # ------------------------------------------------------------------
    # Commande /logs
    #
    # Les sept anciennes commandes /setlog-* faisaient toutes exactement la
    # même chose sur une clé différente : elles sont fusionnées en une seule
    # commande à choix, comme le font les bots les plus connus.
    # ------------------------------------------------------------------
    @app_commands.command(name="logs", description="Choisit le salon qui reçoit un type de logs.")
    @app_commands.describe(type="Le type de logs à configurer", salon="Salon où envoyer ces logs")
    @app_commands.choices(type=[
        app_commands.Choice(name="Vocal", value="vocal"),
        app_commands.Choice(name="Queue", value="queue"),
        app_commands.Choice(name="Modération", value="moderation"),
        app_commands.Choice(name="Messages", value="message"),
        app_commands.Choice(name="Commandes", value="commande"),
        app_commands.Choice(name="Arrivées", value="join"),
        app_commands.Choice(name="Tout", value="all"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        salon: discord.TextChannel,
    ):
        gid = interaction.guild_id
        if gid is None:
            return

        if type.value == "all":
            self.log_channels[gid] = {lt: salon.id for lt in self.log_types}
        else:
            self.log_channels.setdefault(gid, {})[type.value] = salon.id
        await self.save_logs_config()

        await interaction.response.send_message(
            embed=discord.Embed(
                description=t(gid, "moderation.setup_done", channel=salon.mention),
                color=COLOR_SUCCESS,
            ),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.add_join_log(member)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
