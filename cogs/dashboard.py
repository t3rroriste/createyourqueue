"""
Cog : Dashboard
===============
Commande : /dashboard
Donne un lien de connexion au dashboard web, valable cinq minutes et à usage
unique. La réponse est éphémère : le lien ouvre une session d'administration,
il n'a rien à faire dans l'historique d'un salon.

Le bot sait déjà, à cet instant, si la personne est administratrice du
serveur : c'est ce qui permet de se passer d'OAuth2.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import embeds
from config import COLOR_ERROR
from i18n import t
from web import auth, server

log = logging.getLogger("bot.dashboard")


class Dashboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="dashboard",
        description="Open the web dashboard to configure your queues.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def dashboard(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        member = interaction.user

        if not isinstance(member, discord.Member) or gid is None:
            await interaction.response.send_message(
                embed=discord.Embed(description=t(None, "dashboard.err_perms"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        if not server.is_running(self.bot):
            # Désactivé ou mal configuré : on le dit plutôt que de donner un
            # lien qui n'aboutira nulle part.
            await interaction.response.send_message(
                embed=discord.Embed(description=t(gid, "dashboard.err_offline"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        if not auth.is_dashboard_admin(member):
            await interaction.response.send_message(
                embed=discord.Embed(description=t(gid, "dashboard.err_perms"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        url = f"{server.base_url()}/d/{auth.make_link(gid, member.id)}"
        embed = embeds.base(
            gid,
            title=t(gid, "dashboard.link_title"),
            description=t(gid, "dashboard.link_desc"),
            footer=t(gid, "dashboard.link_footer"),
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=t(gid, "dashboard.link_button"), url=url))

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        log.info(f"[DASHBOARD] Lien généré — guild {gid}, membre {member.id}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Dashboard(bot))
