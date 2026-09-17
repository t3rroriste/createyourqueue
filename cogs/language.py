"""
Cog : Language
==============
Commande : /setlanguage
Permet à un admin de choisir la langue du bot pour son serveur.
CreateYourQueue est toujours en français (non modifiable).
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, GUNZFRANCE_GUILD_ID
from i18n import LANGUAGES, get_lang, set_lang, t
from retranslate import retranslate_guild, summary_text

log = logging.getLogger("bot.language")


class LanguageSelect(discord.ui.Select):
    def __init__(self, guild_id: int):
        current = get_lang(guild_id)
        options = [
            discord.SelectOption(
                label=info["name"],
                emoji=info["flag"],
                value=code,
                default=(code == current),
            )
            for code, info in LANGUAGES.items()
        ]
        super().__init__(
            placeholder=t(guild_id, "language.select_placeholder"),
            options=options,
            min_values=1,
            max_values=1,
        )
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction) -> None:
        chosen = self.values[0]
        previous = get_lang(self.guild_id)
        set_lang(self.guild_id, chosen)
        info = LANGUAGES[chosen]

        embed = discord.Embed(
            description=f"{info['flag']} " + t(self.guild_id, "language.changed", language=info["name"]),
            color=COLOR_SUCCESS,
        )
        # Le renommage des salons peut prendre quelques secondes : on répond
        # d'abord, on retraduit ensuite.
        await interaction.response.edit_message(embed=embed, view=None)
        log.info(f"[LANGUAGE] Guild {self.guild_id} → {chosen}")

        if previous == chosen or interaction.guild is None:
            return

        # Ce qui a déjà été créé porte encore les noms de l'ancienne langue :
        # on rebascule salons, rôles et panneaux publiés.
        result = await retranslate_guild(interaction.client, interaction.guild, previous, chosen)
        if result["renamed"] or result["panels"] or result["failed"]:
            embed.add_field(
                name=t(self.guild_id, "language.retranslate_field"),
                value=summary_text(self.guild_id, result),
                inline=False,
            )
            try:
                await interaction.edit_original_response(embed=embed)
            except discord.HTTPException:
                pass


class LanguageView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=120)
        self.add_item(LanguageSelect(guild_id))


class Language(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="language",
        description="Set the bot language for this server.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setlanguage(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id

        if GUNZFRANCE_GUILD_ID and gid == GUNZFRANCE_GUILD_ID:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="🇫🇷 Le serveur officiel CreateYourQueue est toujours en **Français**.",
                    color=COLOR_INFO,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=t(gid, "language.select_title"),
            description=t(gid, "language.select_desc"),
            color=COLOR_INFO,
        )
        current_lang = get_lang(gid)
        current_info = LANGUAGES.get(current_lang, LANGUAGES["en"])
        embed.add_field(
            name=t(gid, "language.current"),
            value=f"{current_info['flag']} **{current_info['name']}**",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, view=LanguageView(gid), ephemeral=True)

    @setlanguage.error
    async def setlanguage_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=discord.Embed(description="❌ Permission **Manage Server** required.", color=COLOR_ERROR),
                ephemeral=True,
            )
        else:
            log.exception("Erreur setlanguage", exc_info=error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Language(bot))
