"""
Cog : Anti-Link
==================
Commande pour activer/désactiver l'anti-link sur un salon spécifique.
"""

import logging
import re
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_WARNING, COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO
import resources
from i18n import t
from json_store import write_json

log = logging.getLogger("bot.antilink")

# Pattern pour détecter les URLs simples (http, https, discord.gg, .com, .fr)
LINK_PATTERN = re.compile(
    r"(https?://|discord\.gg/|\.com|\.fr)"
)

# Fichier de sauvegarde
ANTILINK_SAVE_FILE = "data/antilink.json"


class AntiLink(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> {channel_id: bool}
        self.antilink_channels: dict[int, dict[int, bool]] = {}
        self.bot.loop.create_task(self.load_antilink_config())

    def _is_staff(self, member: discord.Member) -> bool:
        """Vérifie si le membre a le rôle staff."""
        return resources.is_staff(member)

    async def load_antilink_config(self):
        """Charge la configuration antilink depuis le fichier."""
        await self.bot.wait_until_ready()

        if not os.path.exists(ANTILINK_SAVE_FILE):
            os.makedirs(os.path.dirname(ANTILINK_SAVE_FILE), exist_ok=True)
            return

        try:
            with open(ANTILINK_SAVE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convertir les clés string en int
                for guild_id_str, channels in data.items():
                    guild_id = int(guild_id_str)
                    self.antilink_channels[guild_id] = {}
                    for channel_id_str, enabled in channels.items():
                        channel_id = int(channel_id_str)
                        self.antilink_channels[guild_id][channel_id] = enabled
            log.info(f"Configuration antilink chargée : {len(self.antilink_channels)} serveur(s)")
        except Exception as e:
            log.error(f"Erreur lors du chargement de la configuration antilink : {e}")

    async def save_antilink_config(self):
        """Sauvegarde la configuration antilink dans le fichier."""
        try:
            write_json(ANTILINK_SAVE_FILE, self.antilink_channels, indent=4)
            log.info("Configuration antilink sauvegardée")
        except Exception as e:
            log.error(f"Erreur lors de la sauvegarde de la configuration antilink : {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Vérifie chaque message pour les liens"""

        # Ignore les messages du bot
        if message.author.bot:
            return

        # Ignore les messages en DM
        if isinstance(message.channel, discord.DMChannel):
            return

        # Vérifie si l'antilink est activé sur ce salon
        guild_id = message.guild.id
        channel_id = message.channel.id

        if guild_id not in self.antilink_channels:
            return

        if channel_id not in self.antilink_channels[guild_id]:
            return

        if not self.antilink_channels[guild_id][channel_id]:
            return

        # Vérifie les permissions de l'auteur
        if isinstance(message.author, discord.Member):
            # Le staff peut poster des liens
            if self._is_staff(message.author):
                return

        # Détecte les liens
        if LINK_PATTERN.search(message.content):
            try:
                # Supprime le message
                await message.delete()

                # Envoie un avertissement privé
                embed = discord.Embed(
                    title=t(guild_id, "moderation.antilink_title"),
                    description=t(guild_id, "moderation.antilink_deleted",
                                  channel=message.channel.mention),
                    color=COLOR_WARNING,
                )
                await message.author.send(embed=embed)

                log.info(f"Message supprimé: {message.author} a posté un lien dans {message.channel}")
            except discord.Forbidden:
                log.warning(f"Impossible de supprimer le message ou d'envoyer un DM à {message.author}")

    @app_commands.command(name="antilink", description="Active ou désactive l'anti-link sur ce salon (staff uniquement).")
    @app_commands.describe(action="Active ou désactive l'anti-link")
    @app_commands.choices(action=[
        app_commands.Choice(name="Activer", value="enable"),
        app_commands.Choice(name="Désactiver", value="disable"),
        app_commands.Choice(name="Statut", value="status"),
    ])
    async def antilink(self, interaction: discord.Interaction, action: str):
        guild_id = interaction.guild_id

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(t(guild_id, "common.members_only"), ephemeral=True)
            return

        if not self._is_staff(interaction.user):
            embed = discord.Embed(
                description=t(guild_id, "moderation.error_permission"),
                color=COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        channel_id = interaction.channel.id

        if guild_id not in self.antilink_channels:
            self.antilink_channels[guild_id] = {}

        if action == "enable":
            self.antilink_channels[guild_id][channel_id] = True
            await self.save_antilink_config()
            embed = discord.Embed(
                description=t(guild_id, "moderation.antilink_on"),
                color=COLOR_SUCCESS,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.info(f"{interaction.user} a activé l'antilink sur {interaction.channel}")

        elif action == "disable":
            self.antilink_channels[guild_id][channel_id] = False
            await self.save_antilink_config()
            embed = discord.Embed(
                description=t(guild_id, "moderation.antilink_off"),
                color=COLOR_WARNING,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            log.info(f"{interaction.user} a désactivé l'antilink sur {interaction.channel}")

        elif action == "status":
            is_enabled = self.antilink_channels[guild_id].get(channel_id, False)
            status_text = t(guild_id, "antiraid.toggled_on") if is_enabled else t(guild_id, "antiraid.toggled_off")
            embed = discord.Embed(
                description=f"{interaction.channel.mention}: {status_text}",
                color=COLOR_INFO,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiLink(bot))
