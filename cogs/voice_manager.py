"""
Cog : Voice Manager
====================
Gestion de la voix du bot pour les queues.
Le bot rejoint le vocal quand nécessaire et gère les salons vocaux.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_SUCCESS, COLOR_ERROR
from i18n import t
import resources

log = logging.getLogger("bot.voice_manager")


def _reply(guild_id: int | None, key: str, color: discord.Color, **kwargs) -> discord.Embed:
    return discord.Embed(description=t(guild_id, key, **kwargs), color=color)


class VoiceManager(commands.Cog):
    """Cog pour la gestion de la voix du bot."""

    # Groupe : /voice join, /voice leave
    voice = app_commands.Group(name="voice", description="Gestion du salon vocal du bot.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_staff(self, member: discord.Member) -> bool:
        """Vérifie si un membre est staff."""
        return resources.is_staff(member)

    @voice.command(name="join", description="Le bot rejoint ton salon vocal.")
    async def join(self, interaction: discord.Interaction):
        """Le bot rejoint le salon vocal de l'utilisateur."""
        gid = interaction.guild_id
        if not self._is_staff(interaction.user):
            await interaction.response.send_message(
                embed=_reply(gid, "queue.organizers_only", COLOR_ERROR), ephemeral=True)
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=_reply(gid, "voice.need_voice", COLOR_ERROR), ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        # La connexion de CE serveur : le bot peut être en vocal sur plusieurs
        # serveurs à la fois.
        current = interaction.guild.voice_client

        try:
            if current is not None and current.is_connected():
                await current.move_to(voice_channel)
            else:
                await voice_channel.connect()

            await interaction.response.send_message(
                embed=_reply(gid, "voice.joined", COLOR_SUCCESS, channel=voice_channel.mention),
                ephemeral=True,
            )
            log.info(f"Bot rejoint {voice_channel.name} dans guild {interaction.guild_id}")

        except discord.Forbidden:
            await interaction.response.send_message(
                embed=_reply(gid, "voice.join_forbidden", COLOR_ERROR), ephemeral=True)
        except Exception as e:
            log.error(f"Erreur lors de la connexion vocale : {e}")
            await interaction.response.send_message(
                embed=_reply(gid, "voice.join_failed", COLOR_ERROR), ephemeral=True)

    @voice.command(name="leave", description="Le bot quitte le salon vocal.")
    async def leave(self, interaction: discord.Interaction):
        """Le bot quitte le salon vocal actuel."""
        gid = interaction.guild_id
        if not self._is_staff(interaction.user):
            await interaction.response.send_message(
                embed=_reply(gid, "queue.organizers_only", COLOR_ERROR), ephemeral=True)
            return

        current = interaction.guild.voice_client
        if current is None or not current.is_connected():
            await interaction.response.send_message(
                embed=_reply(gid, "voice.not_connected", COLOR_ERROR), ephemeral=True)
            return

        try:
            await current.disconnect()
            await interaction.response.send_message(
                embed=_reply(gid, "voice.left", COLOR_SUCCESS), ephemeral=True)
            log.info(f"Bot a quitté le vocal dans guild {interaction.guild_id}")

        except Exception as e:
            log.error(f"Erreur lors de la déconnexion vocale : {e}")
            await interaction.response.send_message(
                embed=_reply(gid, "voice.leave_failed", COLOR_ERROR), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceManager(bot))
    log.info("Cog VoiceManager chargé")
