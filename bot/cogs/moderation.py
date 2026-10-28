"""
Cog : Modération
====================
Commandes : /clear, /lock, /unlock,
            /warn, /warnings, /unwarn, /timeout, /untimeout

Chaque action est journalisée dans le salon de /logs-moderation.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, COLOR_WARNING
import embeds
from guild_settings import is_status_panel_message
from i18n import t
from json_store import write_json
from cogs.logs import send_log

log = logging.getLogger("bot.moderation")

WARNINGS_FILE = "data/warnings.json"


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> user_id -> [{"reason", "by", "at"}]
        self.warnings: dict[int, dict[int, list[dict]]] = {}
        self.bot.loop.create_task(self._load_warnings())

    # -------------------------------------------------------------
    # Persistance des avertissements
    # -------------------------------------------------------------
    async def _load_warnings(self):
        await self.bot.wait_until_ready()
        if not os.path.exists(WARNINGS_FILE):
            return
        try:
            with open(WARNINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.warnings = {
                int(gid): {int(uid): warns for uid, warns in users.items()}
                for gid, users in data.items()
            }
            log.info(f"Warnings chargés : {len(self.warnings)} serveur(s)")
        except Exception as e:
            log.error(f"Erreur chargement warnings : {e}")

    def _save_warnings(self):
        try:
            write_json(WARNINGS_FILE, {str(gid): {str(uid): warns for uid, warns in users.items()} for gid, users in self.warnings.items()}, indent=4, ensure_ascii=False)
        except Exception as e:
            log.error(f"Erreur sauvegarde warnings : {e}")

    # -------------------------------------------------------------
    # Journal de modération (voir cogs/logs.py)
    #
    # /modlog a été retiré : il rangeait son salon dans un dictionnaire en
    # mémoire, perdu à chaque redémarrage. Le log porte le vrai modérateur :
    # vu du journal d'audit, c'est le bot qui a agi.
    # -------------------------------------------------------------
    def _mod_log(self, interaction: discord.Interaction, key: str, *,
                 target: discord.abc.User | None = None, fields: list[tuple] = (),
                 color: int | None = None) -> None:
        gid = interaction.guild_id
        send_log(self.bot, gid, "moderation", t(gid, key), user=target, color=color,
                 description=target.mention if target else None,
                 fields=[(t(gid, "logs.f_by"), interaction.user.mention), *fields])

    # -------------------------------------------------------------
    # /clears
    # -------------------------------------------------------------
    @app_commands.command(
        name="clear",
        description="Supprime un nombre de messages dans ce salon.",
    )
    @app_commands.describe(nombre="Nombre de messages à supprimer (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clears(self, interaction: discord.Interaction, nombre: app_commands.Range[int, 1, 100]):
        # purge() n'existe pas sur un forum.
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(t(interaction.guild_id, "common.text_channel_only"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        # Le panneau /status reste en place : il est fait pour ne jamais partir.
        deleted = await interaction.channel.purge(
            limit=nombre, check=lambda m: not is_status_panel_message(interaction.guild_id, m.id))
        embed = discord.Embed(
            description=t(interaction.guild_id, "moderation.clears_done").format(count=len(deleted)),
            color=COLOR_SUCCESS,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        self._mod_log(interaction, "logs.mod_clear", fields=[
            (t(interaction.guild_id, "logs.f_channel"), interaction.channel.mention),
            (t(interaction.guild_id, "logs.f_count"), len(deleted))])

    # -------------------------------------------------------------
    # /lock
    # -------------------------------------------------------------
    @app_commands.command(
        name="lock",
        description="Verrouille ce salon (empêche @everyone d'écrire).",
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(t(interaction.guild_id, "common.text_channel_only"), ephemeral=True)
            return
        channel = interaction.channel
        everyone = interaction.guild.default_role

        overwrite = channel.overwrites_for(everyone)
        overwrite.send_messages = False
        await channel.set_permissions(everyone, overwrite=overwrite, reason=f"Lock par {interaction.user}")

        embed = discord.Embed(
            description=t(interaction.guild_id, "moderation.locked"),
            color=COLOR_INFO,
        )
        # Pas de log de modération : le message ci-dessus le dit déjà, dans
        # le salon concerné.
        await interaction.response.send_message(embed=embed)

    # -------------------------------------------------------------
    # /unlock
    # -------------------------------------------------------------
    @app_commands.command(
        name="unlock",
        description="Déverrouille ce salon.",
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(t(interaction.guild_id, "common.text_channel_only"), ephemeral=True)
            return
        channel = interaction.channel
        everyone = interaction.guild.default_role

        overwrite = channel.overwrites_for(everyone)
        overwrite.send_messages = None
        await channel.set_permissions(everyone, overwrite=overwrite, reason=f"Unlock par {interaction.user}")

        embed = discord.Embed(
            description=t(interaction.guild_id, "moderation.unlocked"),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # /cleanup a été retiré : il cherchait des salons nommés « 🔵 Équipe 1 » et
    # « 🔴 Équipe 2 », créés par un ancien système de queue.

    # -------------------------------------------------------------
    # /warn
    # -------------------------------------------------------------
    @app_commands.command(name="warn", description="Avertit un membre (avertissement enregistré).")
    @app_commands.describe(membre="Le membre à avertir", raison="Raison de l'avertissement")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, membre: discord.Member, raison: str):
        gid = interaction.guild_id
        entry = {
            "reason": raison,
            "by": str(interaction.user),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.warnings.setdefault(gid, {}).setdefault(membre.id, []).append(entry)
        self._save_warnings()
        count = len(self.warnings[gid][membre.id])

        try:
            await membre.send(
                embed=discord.Embed(
                    title=t(gid, "moderation.warn_dm_title"),
                    description=t(gid, "moderation.warn_dm_desc", guild=interaction.guild.name, reason=raison),
                    color=COLOR_WARNING,
                )
            )
        except discord.HTTPException:
            pass

        embed = discord.Embed(
            description=t(gid, "moderation.warn_success", member=membre.mention, reason=raison, count=count),
            color=COLOR_WARNING,
        )
        await interaction.response.send_message(embed=embed)
        self._mod_log(interaction, "logs.mod_warn", target=membre, color=embeds.WARNING, fields=[
            (t(gid, "logs.f_warnings"), count),
            (t(gid, "logs.f_reason"), raison, False)])

    # -------------------------------------------------------------
    # /warnings
    # -------------------------------------------------------------
    @app_commands.command(name="warnings", description="Affiche l'historique d'avertissements d'un membre.")
    @app_commands.describe(membre="Le membre à consulter")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings_cmd(self, interaction: discord.Interaction, membre: discord.Member):
        gid = interaction.guild_id
        entries = self.warnings.get(gid, {}).get(membre.id, [])

        embed = embeds.base(
            gid,
            title=t(gid, "moderation.warnings_title", member=membre.display_name),
            # Un casier vierge n'est pas une alerte : la couleur suit la gravité.
            kind="success" if not entries else ("error" if len(entries) >= 3 else "warning"),
            footer=t(gid, "moderation.warnings_footer", count=len(entries)),
        )
        embed.set_thumbnail(url=membre.display_avatar.url)
        if not entries:
            embed.description = t(gid, "moderation.warnings_none", member=membre.mention)
        else:
            lines = []
            for i, w in enumerate(entries, start=1):
                date = w.get("at", "")[:10]
                lines.append(t(gid, "moderation.warnings_entry", index=i, reason=w["reason"], date=date, by=w["by"]))
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------------------------------------------------------------
    # /clearwarnings
    # -------------------------------------------------------------
    @app_commands.command(name="unwarn", description="Efface l'historique d'avertissements d'un membre.")
    @app_commands.describe(membre="Le membre dont effacer les avertissements")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def clearwarnings(self, interaction: discord.Interaction, membre: discord.Member):
        gid = interaction.guild_id
        count = len(self.warnings.get(gid, {}).get(membre.id, []))
        self.warnings.setdefault(gid, {})[membre.id] = []
        self._save_warnings()

        embed = discord.Embed(
            description=t(gid, "moderation.clearwarnings_success", member=membre.mention, count=count),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self._mod_log(interaction, "logs.mod_unwarn", target=membre, color=embeds.SUCCESS,
                      fields=[(t(gid, "logs.f_warnings"), count)])

    # -------------------------------------------------------------
    # /timeout
    # -------------------------------------------------------------
    @app_commands.command(name="timeout", description="Met un membre en sourdine temporairement.")
    @app_commands.describe(
        membre="Le membre à mettre en sourdine",
        minutes="Durée en minutes (max 40320 = 28 jours)",
        raison="Raison de la sourdine",
    )
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        raison: str = "",
    ):
        gid = interaction.guild_id
        try:
            await membre.timeout(timedelta(minutes=minutes), reason=raison or f"Timeout par {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(description=t(gid, "moderation.timeout_error"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            description=t(gid, "moderation.timeout_success", member=membre.mention, minutes=minutes, reason=raison or "—"),
            color=COLOR_WARNING,
        )
        await interaction.response.send_message(embed=embed)
        until = int((discord.utils.utcnow() + timedelta(minutes=minutes)).timestamp())
        self._mod_log(interaction, "logs.mod_timeout", target=membre, color=embeds.WARNING, fields=[
            (t(gid, "logs.f_until"), f"<t:{until}:R>"),
            (t(gid, "logs.f_reason"), raison or t(gid, "logs.no_reason"), False)])

    # -------------------------------------------------------------
    # /untimeout
    # -------------------------------------------------------------
    @app_commands.command(name="untimeout", description="Retire la sourdine d'un membre.")
    @app_commands.describe(membre="Le membre dont retirer la sourdine")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, membre: discord.Member):
        gid = interaction.guild_id
        if not membre.is_timed_out():
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=t(gid, "moderation.untimeout_not_muted", member=membre.mention),
                    color=COLOR_ERROR,
                ),
                ephemeral=True,
            )
            return

        try:
            await membre.timeout(None, reason=f"Sourdine retirée par {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(description=t(gid, "moderation.timeout_error"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            description=t(gid, "moderation.untimeout_success", member=membre.mention),
            color=COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)
        self._mod_log(interaction, "logs.mod_untimeout", target=membre, color=embeds.SUCCESS)

    # -------------------------------------------------------------
    # Gestion des erreurs de permissions
    # -------------------------------------------------------------
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                description=t(interaction.guild_id, "moderation.error_permission"),
                color=COLOR_ERROR,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            log.exception("Erreur dans le cog moderation", exc_info=error)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
