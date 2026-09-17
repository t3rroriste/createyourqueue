"""
Cog : Help
===========
Commande : /help
Aide interactive avec menu déroulant par catégorie.

La liste ci-dessous doit rester synchronisée avec les commandes réellement
enregistrées (voir INITIAL_EXTENSIONS dans config.py) — un cog désactivé ne
doit pas apparaître ici, sinon /help affiche des commandes qui n'existent
pas côté Discord.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import embeds
from i18n import t

log = logging.getLogger("bot.help")

# ------------------------------------------------------------------
# Données des catégories — labels/descriptions de catégorie ET de commande
# passent toutes par i18n (voir locales/*.json → "help").
# ------------------------------------------------------------------
CATEGORIES = {
    "queue": {
        "emoji": "🎮",
        "label_key": "help.cat_queue_label",
        "desc_key": "help.cat_queue_desc",
        "color": discord.Color.blurple(),
        "commands": [
            ("/guide", "help.cmd_guide_desc"),
            ("/queue", "help.cmd_queue_desc"),
            ("/rematch", "help.cmd_rematch_desc"),
            ("/schedule", "help.cmd_schedule_desc"),
            ("/poll", "help.cmd_poll_desc"),
            ("/clan", "help.cmd_clan_desc"),
            ("/clantransfer", "help.cmd_clantransfer_desc"),
            ("/cw", "help.cmd_cw_desc"),
            ("/groupe", "help.cmd_groupe_desc"),
            ("/history", "help.cmd_history_desc"),
            ("/bl", "help.cmd_bl_desc"),
            ("/unbl", "help.cmd_unbl_desc"),
        ],
    },
    "moderation": {
        "emoji": "🔧",
        "label_key": "help.cat_moderation_label",
        "desc_key": "help.cat_moderation_desc",
        "color": discord.Color.orange(),
        "commands": [
            ("/clear", "help.cmd_clear_desc"),
            ("/lock", "help.cmd_lock_desc"),
            ("/unlock", "help.cmd_unlock_desc"),
            ("/warn", "help.cmd_warn_desc"),
            ("/warnings", "help.cmd_warnings_desc"),
            ("/unwarn", "help.cmd_unwarn_desc"),
            ("/timeout", "help.cmd_timeout_desc"),
            ("/untimeout", "help.cmd_untimeout_desc"),
            ("/antilink", "help.cmd_antilink_desc"),
            ("/autoclean", "help.cmd_autoclean_desc"),
        ],
    },
    "antiraid": {
        "emoji": "🛡️",
        "label_key": "help.cat_antiraid_label",
        "desc_key": "help.cat_antiraid_desc",
        "color": discord.Color.red(),
        "commands": [
            ("/antiraid", "help.cmd_antiraid_desc"),
        ],
    },
    "logs": {
        "emoji": "📋",
        "label_key": "help.cat_logs_label",
        "desc_key": "help.cat_logs_desc",
        "color": discord.Color.dark_gray(),
        "commands": [
            ("/logs", "help.cmd_logs_desc"),
            ("/logs-vocal", "logs.what_vocal"),
            ("/logs-message", "logs.what_message"),
            ("/logs-queue", "logs.what_queue"),
            ("/logs-match", "logs.what_match"),
            ("/logs-duel", "logs.what_duel"),
            ("/logs-clan", "logs.what_clan"),
            ("/logs-commande", "logs.what_commande"),
            ("/logs-join", "logs.what_join"),
            ("/logs-moderation", "logs.what_moderation"),
            ("/logs-serveur", "logs.what_serveur"),
            ("/logs-tout", "help.cmd_logs_tout_desc"),
        ],
    },
    "classement": {
        "emoji": "🏆",
        "label_key": "help.cat_classement_label",
        "desc_key": "help.cat_classement_desc",
        "color": discord.Color.gold(),
        "commands": [
            ("/leaderboard", "help.cmd_leaderboard_desc"),
            ("/stats", "help.cmd_stats_desc"),
            ("/serverstats", "help.cmd_serverstats_desc"),
            ("/elo", "help.cmd_elo_desc"),
            ("/podium", "help.cmd_podium_desc"),
            ("/season", "help.cmd_season_desc"),
        ],
    },
    "roles": {
        "emoji": "🎭",
        "label_key": "help.cat_roles_label",
        "desc_key": "help.cat_roles_desc",
        "color": discord.Color.green(),
        "commands": [
            ("/roles", "help.cmd_roles_group_desc"),
        ],
    },
    "info": {
        "emoji": "ℹ️",
        "label_key": "help.cat_info_label",
        "desc_key": "help.cat_info_desc",
        "color": discord.Color.teal(),
        "commands": [
            ("/userinfo", "help.cmd_userinfo_desc"),
            ("/serverinfo", "help.cmd_serverinfo_desc"),
            ("/help", "help.cmd_help_desc"),
            ("/support", "help.cmd_support_desc"),
        ],
    },
    "voice": {
        "emoji": "🔊",
        "label_key": "help.cat_voice_label",
        "desc_key": "help.cat_voice_desc",
        "color": discord.Color.magenta(),
        "commands": [
            ("/voice", "help.cmd_voice_desc"),
        ],
    },
    "config": {
        "emoji": "⚙️",
        "label_key": "help.cat_config_label",
        "desc_key": "help.cat_config_desc",
        "color": discord.Color.dark_gold(),
        "commands": [
            ("/option", "help.cmd_option_desc"),
            ("/config", "help.cmd_config_desc"),
            ("/language", "help.cmd_language_desc"),
            ("/diagnostic", "help.cmd_diagnostic_desc"),
            ("/reset", "help.cmd_reset_desc"),
            ("/status", "help.cmd_status_desc"),
        ],
    },
    "duel": {
        "emoji": "⚔️",
        "label_key": "help.cat_duel_label",
        "desc_key": "help.cat_duel_desc",
        "color": discord.Color.dark_red(),
        "commands": [
            ("/duel", "help.cmd_duel_desc"),
            ("/createteam", "help.cmd_createteam_desc"),
            ("/config-duel", "help.cmd_config_duel_desc"),
        ],
    },
}


def _build_overview_embed(guild_id: int | None) -> discord.Embed:
    total = sum(len(cat.get("commands", [])) for cat in CATEGORIES.values())
    embed = embeds.base(
        guild_id,
        title=t(guild_id, "help.overview_title"),
        description=t(guild_id, "help.overview_desc") + f"\n{embeds.RULE}",
        footer=t(guild_id, "help.overview_footer_count", total=total),
    )
    for cat in CATEGORIES.values():
        count = len(cat.get("commands", []))
        embed.add_field(
            name=f"{cat['emoji']}  {t(guild_id, cat['label_key'])}",
            value=f"{t(guild_id, cat['desc_key'])}\n`{count}` {t(guild_id, 'help.commands_word')}",
            inline=True,
        )
    embeds.align(embed)
    return embed


def _build_category_embed(guild_id: int | None, key: str) -> discord.Embed:
    cat = CATEGORIES[key]
    # Une commande par ligne : `/nom` en gras suivi de sa description. Un champ
    # par commande donnait un embed deux fois plus long pour la même info.
    lines = [f"`{name}`\n{t(guild_id, desc_key)}" for name, desc_key in cat.get("commands", [])]
    embed = embeds.base(
        guild_id,
        title=f"{cat['emoji']}  {t(guild_id, cat['label_key'])}",
        description=t(guild_id, cat["desc_key"]) + f"\n{embeds.RULE}\n\n" + "\n\n".join(lines),
        footer=t(guild_id, "help.back_button"),
    )
    embed.color = cat["color"]
    return embed


# ------------------------------------------------------------------
# UI
# ------------------------------------------------------------------
class HelpSelect(discord.ui.Select):
    def __init__(self, guild_id: int | None):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(
                label=t(guild_id, cat["label_key"]),
                description=t(guild_id, cat["desc_key"]),
                emoji=cat["emoji"],
                value=key,
            )
            for key, cat in CATEGORIES.items()
        ]
        super().__init__(
            placeholder=t(guild_id, "help.select_placeholder"),
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        embed = _build_category_embed(self.guild_id, self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, guild_id: int | None):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.add_item(HelpSelect(guild_id))
        self.overview_button.label = t(guild_id, "help.overview_button")

    @discord.ui.button(label="Overview", style=discord.ButtonStyle.secondary, emoji="🏠", row=1)
    async def overview_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_build_overview_embed(self.guild_id),
            view=self,
        )


# ------------------------------------------------------------------
# Cog
# ------------------------------------------------------------------
class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show the bot's interactive help menu.")
    async def help(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        await interaction.response.send_message(
            embed=_build_overview_embed(guild_id),
            view=HelpView(guild_id),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
