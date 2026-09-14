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

from typing import Optional

from config import COLOR_SUCCESS, COLOR_ERROR
import resources

log = logging.getLogger("bot.voice_manager")


class VoiceManager(commands.Cog):
    """Cog pour la gestion de la voix du bot."""

    # Groupe : /voice join, /voice leave
    voice = app_commands.Group(name="voice", description="Gestion du salon vocal du bot.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_client: Optional[discord.VoiceClient] = None

    def _is_staff(self, member: discord.Member) -> bool:
        """Vérifie si un membre est staff."""
        return resources.is_staff(member)
    
    @voice.command(name="join", description="Le bot rejoint ton salon vocal.")
    async def join(self, interaction: discord.Interaction):
        """Le bot rejoint le salon vocal de l'utilisateur."""
        if not self._is_staff(interaction.user):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Cette commande est réservée aux organisateurs.",
                    color=COLOR_ERROR
                ),
                ephemeral=True,
            )
            return
        
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Vous devez être connecté à un salon vocal.",
                    color=COLOR_ERROR
                ),
                ephemeral=True,
            )
            return
        
        voice_channel = interaction.user.voice.channel
        
        try:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.move_to(voice_channel)
            else:
                self.voice_client = await voice_channel.connect()
            
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"✅ J'ai rejoint {voice_channel.mention}",
                    color=COLOR_SUCCESS
                ),
                ephemeral=True,
            )
            log.info(f"Bot rejoint {voice_channel.name} dans guild {interaction.guild_id}")
            
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Je n'ai pas la permission de rejoindre ce salon vocal.",
                    color=COLOR_ERROR
                ),
                ephemeral=True,
            )
        except Exception as e:
            log.error(f"Erreur lors de la connexion vocale : {e}")
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Une erreur s'est produite lors de la connexion vocale.",
                    color=COLOR_ERROR
                ),
                ephemeral=True,
            )
    
    @voice.command(name="leave", description="Le bot quitte le salon vocal.")
    async def leave(self, interaction: discord.Interaction):
        """Le bot quitte le salon vocal actuel."""
        if not self._is_staff(interaction.user):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Cette commande est réservée aux organisateurs.",
                    color=COLOR_ERROR
                ),
                ephemeral=True,
            )
            return
        
        if not self.voice_client or not self.voice_client.is_connected():
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Je ne suis pas connecté à un salon vocal.",
                    color=COLOR_ERROR
                ),
                ephemeral=True,
            )
            return
        
        try:
            await self.voice_client.disconnect()
            self.voice_client = None
            
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="✅ J'ai quitté le salon vocal.",
                    color=COLOR_SUCCESS
                ),
                ephemeral=True,
            )
            log.info(f"Bot a quitté le vocal dans guild {interaction.guild_id}")
            
        except Exception as e:
            log.error(f"Erreur lors de la déconnexion vocale : {e}")
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Une erreur s'est produite lors de la déconnexion.",
                    color=COLOR_ERROR
                ),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceManager(bot))
    log.info("Cog VoiceManager chargé")
