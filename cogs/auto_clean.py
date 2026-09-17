import discord
import embeds
from discord import app_commands
from discord.ext import commands
import logging
import asyncio
from guild_settings import is_status_panel_message
from i18n import t

log = logging.getLogger("bot")


class AutoClean(commands.Cog):
    """Système de nettoyage automatique de salons."""

    # Groupe : /autoclean on, /autoclean off
    autoclean = app_commands.Group(name="autoclean", default_permissions=discord.Permissions(manage_messages=True), description="Nettoyage automatique d'un salon.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.clean_tasks: dict[int, asyncio.Task] = {}  # guild_id -> task
        self.clean_configs: dict[int, dict] = {}  # guild_id -> {channel_id, interval_minutes}

    def cog_unload(self):
        """Annuler toutes les tâches de nettoyage lors du déchargement."""
        for task in self.clean_tasks.values():
            task.cancel()

    async def clean_channel_loop(self, guild_id: int, channel_id: int, interval_minutes: int):
        """Boucle de nettoyage automatique d'un salon."""
        while True:
            try:
                await asyncio.sleep(interval_minutes * 60)

                guild = self.bot.get_guild(guild_id)
                if not guild:
                    break

                channel = guild.get_channel(channel_id)
                if not channel:
                    log.warning(f"Salon {channel_id} introuvable pour le nettoyage automatique")
                    break

                # Suppression en masse (jusqu'à 100 messages par appel, messages de
                # moins de 14 jours) plutôt qu'un message à la fois : nettement moins
                # d'appels à l'API, donc nettement moins de risque de rate limit sur
                # un salon actif. purge() bascule automatiquement en suppression
                # individuelle pour les messages plus anciens que 14 jours.
                try:
                    deleted = await channel.purge(
                        limit=None, check=lambda m: not is_status_panel_message(guild_id, m.id))
                    log.info(f"Nettoyage automatique: {len(deleted)} messages supprimés dans {channel.name}")
                except discord.HTTPException as e:
                    log.error(f"Erreur lors du nettoyage automatique de {channel.name} : {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Erreur dans clean_channel_loop: {e}")

    @autoclean.command(name="on", description="Active le nettoyage automatique d'un salon.")
    @app_commands.describe(
        salon="Le salon à nettoyer automatiquement",
        interval="Intervalle en minutes (par défaut: 20min)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def on(self, interaction: discord.Interaction, salon: discord.TextChannel, interval: int = 20):
        """Configure le nettoyage automatique d'un salon."""
        await interaction.response.defer()

        guild_id = interaction.guild_id

        if interval < 1:
            embed = discord.Embed(
                description=t(guild_id, "moderation.error_manage_channel"),
                color=embeds.ERROR,
            )
            await interaction.followup.send(embed=embed)
            return

        # Annuler la tâche existante si elle existe
        if guild_id in self.clean_tasks:
            self.clean_tasks[guild_id].cancel()

        # Démarrer la nouvelle tâche
        task = self.bot.loop.create_task(
            self.clean_channel_loop(guild_id, salon.id, interval)
        )
        self.clean_tasks[guild_id] = task
        self.clean_configs[guild_id] = {
            "channel_id": salon.id,
            "interval_minutes": interval
        }

        embed = discord.Embed(
            description=t(guild_id, "moderation.autoclean_on", channel=salon.mention, interval=interval),
            color=embeds.SUCCESS,
        )
        await interaction.followup.send(embed=embed)

        log.info(f"{interaction.user} a configuré le nettoyage automatique pour {salon.name} toutes les {interval}min")

    @autoclean.command(name="off", description="Arrête le nettoyage automatique.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def off(self, interaction: discord.Interaction):
        """Arrête le nettoyage automatique."""
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id

        if guild_id not in self.clean_tasks:
            embed = discord.Embed(
                description=t(guild_id, "moderation.autoclean_off"),
                color=embeds.ERROR,
            )
            await interaction.followup.send(embed=embed)
            return

        self.clean_tasks[guild_id].cancel()
        del self.clean_tasks[guild_id]
        del self.clean_configs[guild_id]

        embed = discord.Embed(
            description=t(guild_id, "moderation.autoclean_stopped"),
            color=embeds.SUCCESS,
        )
        await interaction.followup.send(embed=embed)

        log.info(f"{interaction.user} a arrêté le nettoyage automatique")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                description=t(interaction.guild_id, "moderation.error_permission"),
                color=embeds.ERROR,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            log.exception("Erreur dans le cog auto_clean", exc_info=error)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoClean(bot))
