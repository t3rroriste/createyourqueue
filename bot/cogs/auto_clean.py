"""
Cog : nettoyage automatique
===========================
`/autoclean on` fait purger un salon à intervalle régulier.

La configuration vivait UNIQUEMENT en mémoire : chaque redémarrage du bot
l'effaçait, et le nettoyage s'arrêtait sans rien dire. On la garde
maintenant dans `data/autoclean.json`, et les boucles repartent au
démarrage — c'est aussi ce qui permet au panneau de l'afficher, un réglage
perdu au prochain redémarrage n'ayant rien à montrer.
"""

import json
import logging
import os

import discord
import embeds
from discord import app_commands
from discord.ext import commands
import asyncio
from guild_settings import is_status_panel_message
from i18n import t
from json_store import write_json

log = logging.getLogger("bot")

# Même dossier et même forme que les autres cogs qui gardent leur état.
AUTOCLEAN_SAVE_FILE = "data/autoclean.json"

# Bornes de l'intervalle. Le minimum vaut celui de /autoclean on ; le
# maximum — une semaine — évite qu'un réglage du panneau programme une
# purge dans un an, ce qui revient à ne rien programmer tout en prétendant
# le contraire.
INTERVAL_MIN = 1
INTERVAL_MAX = 10080


class AutoClean(commands.Cog):
    """Système de nettoyage automatique de salons."""

    # Groupe : /autoclean on, /autoclean off
    autoclean = app_commands.Group(name="autoclean", default_permissions=discord.Permissions(manage_messages=True), description="Nettoyage automatique d'un salon.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.clean_tasks: dict[int, asyncio.Task] = {}  # guild_id -> task
        self.clean_configs: dict[int, dict] = {}  # guild_id -> {channel_id, interval_minutes}
        self.bot.loop.create_task(self.load_clean_config())

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    async def load_clean_config(self):
        """Relit le fichier et relance une boucle par serveur configuré."""
        await self.bot.wait_until_ready()

        if not os.path.exists(AUTOCLEAN_SAVE_FILE):
            os.makedirs(os.path.dirname(AUTOCLEAN_SAVE_FILE), exist_ok=True)
            return

        try:
            with open(AUTOCLEAN_SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log.error(f"Erreur lors du chargement de la configuration autoclean : {e}")
            return

        for guild_id_str, conf in (data or {}).items():
            try:
                guild_id = int(guild_id_str)
                channel_id = int(conf["channel_id"])
                interval = int(conf["interval_minutes"])
            except (KeyError, TypeError, ValueError):
                # Une entrée abîmée ne doit pas empêcher les autres de repartir.
                log.warning(f"Entrée autoclean ignorée pour {guild_id_str!r}")
                continue
            interval = max(INTERVAL_MIN, min(INTERVAL_MAX, interval))
            self.start_clean(guild_id, channel_id, interval)

        log.info(f"Configuration autoclean chargée : {len(self.clean_configs)} serveur(s)")

    def save_clean_config(self):
        """Écrit la configuration. Synchrone : write_json est atomique et bref."""
        try:
            write_json(AUTOCLEAN_SAVE_FILE, self.clean_configs, indent=4)
        except Exception as e:
            log.error(f"Erreur lors de la sauvegarde de la configuration autoclean : {e}")

    def start_clean(self, guild_id: int, channel_id: int, interval: int):
        """Lance (ou relance) la boucle d'un serveur. N'écrit pas le fichier."""
        if guild_id in self.clean_tasks:
            self.clean_tasks[guild_id].cancel()
        self.clean_tasks[guild_id] = self.bot.loop.create_task(
            self.clean_channel_loop(guild_id, channel_id, interval)
        )
        self.clean_configs[guild_id] = {
            "channel_id": channel_id,
            "interval_minutes": interval,
        }

    def stop_clean(self, guild_id: int) -> bool:
        """Arrête la boucle d'un serveur. Rend False si rien ne tournait."""
        tache = self.clean_tasks.pop(guild_id, None)
        self.clean_configs.pop(guild_id, None)
        if tache is None:
            return False
        tache.cancel()
        return True

    # ------------------------------------------------------------------
    # Ce que le panneau lit et écrit (cogs/dashboard_api.py)
    # ------------------------------------------------------------------
    def dashboard_state(self, guild: discord.Guild) -> dict:
        """L'état du nettoyage pour ce serveur, tel que le panneau l'affiche."""
        conf = self.clean_configs.get(guild.id)
        if not conf:
            return {"enabled": False, "channel_id": "", "interval_minutes": 20}
        return {
            "enabled": True,
            "channel_id": str(conf["channel_id"]),
            "interval_minutes": conf["interval_minutes"],
        }

    def dashboard_apply(self, guild: discord.Guild, enabled: bool,
                        channel_id: int | None, interval: int) -> str | None:
        """Applique un réglage venu du panneau. Rend un code d'erreur, ou None.

        Le salon est vérifié ici et pas seulement dans l'API : une purge
        lancée sur un identifiant qui n'est pas un salon textuel de CE
        serveur tournerait dans le vide à chaque réveil.
        """
        if not enabled:
            self.stop_clean(guild.id)
            self.save_clean_config()
            return None

        if channel_id is None:
            return "AUTOCLEAN_SALON_MANQUANT"
        salon = guild.get_channel(channel_id)
        if not isinstance(salon, discord.TextChannel):
            return "AUTOCLEAN_SALON_INVALIDE"
        if not INTERVAL_MIN <= interval <= INTERVAL_MAX:
            return "AUTOCLEAN_INTERVALLE_INVALIDE"

        self.start_clean(guild.id, salon.id, interval)
        self.save_clean_config()
        return None

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
                    # Salon supprimé : la boucle s'arrête, et la configuration
                    # avec elle. La laisser dans le fichier ferait réapparaître
                    # un nettoyage « actif » sur un salon qui n'existe plus à
                    # chaque redémarrage, et le panneau le montrerait comme tel.
                    log.warning(f"Salon {channel_id} introuvable pour le nettoyage automatique")
                    self.clean_configs.pop(guild_id, None)
                    self.clean_tasks.pop(guild_id, None)
                    self.save_clean_config()
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
        # Réponse visible par celui qui lance la commande seulement.
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id

        if interval < 1:
            embed = discord.Embed(
                description=t(guild_id, "moderation.error_manage_channel"),
                color=embeds.ERROR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Le même chemin que le panneau : la commande ne doit pas pouvoir
        # laisser un état que le fichier ignore.
        self.start_clean(guild_id, salon.id, interval)
        self.save_clean_config()

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

        if not self.stop_clean(guild_id):
            embed = discord.Embed(
                description=t(guild_id, "moderation.autoclean_off"),
                color=embeds.ERROR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        self.save_clean_config()

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
