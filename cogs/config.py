"""
Cog : Config
============
Commande : /config
Panneau interactif pour l'apparence du bot (avatar, bannière, surnom) et le
renommage de ses salons et rôles.

Ce qui en est parti le 11/10/2026, parce que le tableau de bord le fait :
la langue du serveur, la désignation des salons et celle des rôles. Deux
endroits pour un même réglage, c'est un moyen sûr de se contredire.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import (
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_SUCCESS,
    GUNZFRANCE_GUILD_ID,
)
import custom_emojis
import resources
import net_safety
from guild_settings import set_custom_name
from i18n import t
from text_safety import sanitize

log = logging.getLogger("bot.config")

# Ressources renommables depuis /config -> Salons -> Renommer.
RENAMABLE_RESOURCES = [
    ("category_main", "category"),
    ("channel_queue_command", "text"),
    ("channel_queue_announcement", "text"),
    ("channel_queue_resultat", "text"),
    ("channel_queue_classement", "text"),
    ("channel_team_request", "text"),
    ("voice_queue_waiting", "voice"),
    ("role_staff", "role"),
    ("role_queue_notif", "role"),
    ("role_connexion", "role"),
    ("role_mvp_week", "role"),
]

async def _fetch_image(url: str) -> bytes | None:
    return await net_safety.safe_fetch(url, max_bytes=8 * 1024 * 1024)


def _main_embed(guild: discord.Guild) -> discord.Embed:
    gid = guild.id
    me = guild.me

    embed = discord.Embed(
        title=t(gid, "config.main_title"),
        description=t(gid, "config.main_desc") + "\n\n" + t(gid, "config.main_dashboard"),
        color=COLOR_INFO,
    )
    embed.add_field(
        name=t(gid, "config.field_nickname"),
        value=f"**{me.display_name}**",
        inline=True,
    )
    embed.add_field(
        name=t(gid, "config.field_avatar"),
        value=t(gid, "config.customized") if me.guild_avatar else t(gid, "config.default"),
        inline=True,
    )
    embed.set_thumbnail(url=me.display_avatar.url)
    embed.set_footer(text=t(gid, "config.footer"))
    return embed


# La création automatique des salons et des rôles a été retirée : c'est
# l'assistant (cogs/wizard.py) qui fait désigner des salons existants.


class UrlModal(discord.ui.Modal):
    def __init__(self, guild_id: int, field: str, title: str, label: str, placeholder: str):
        super().__init__(title=title, timeout=300)
        self.guild_id = guild_id
        self.field = field
        self.url_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=False,
            max_length=500,
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        url = self.url_input.value.strip()
        gid = self.guild_id
        await interaction.response.defer(ephemeral=True)

        if not url:
            try:
                if self.field == "avatar":
                    await guild.me.edit(avatar=None)
                    msg = t(gid, "config.avatar_reset")
                else:
                    await guild.me.edit(banner=None)
                    msg = t(gid, "config.banner_reset")
            except discord.Forbidden:
                msg = t(gid, "config.no_permission")
            await interaction.followup.send(embed=discord.Embed(description=msg, color=COLOR_SUCCESS), ephemeral=True)
            return

        data = await _fetch_image(url)
        if data is None:
            await interaction.followup.send(
                embed=discord.Embed(description=t(gid, "config.image_fetch_error"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return
        if len(data) > 8 * 1024 * 1024:
            await interaction.followup.send(
                embed=discord.Embed(description=t(gid, "config.image_size_error"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        try:
            if self.field == "avatar":
                await guild.me.edit(avatar=data)
                msg = t(gid, "config.avatar_changed")
            else:
                await guild.me.edit(banner=data)
                msg = t(gid, "config.banner_changed")
        except discord.Forbidden:
            msg = t(gid, "config.no_permission")
        except discord.HTTPException:
            msg = t(gid, "config.image_format_error")

        await interaction.followup.send(embed=discord.Embed(description=msg, color=COLOR_SUCCESS), ephemeral=True)


class NicknameModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title=t(guild_id, "config.nickname_modal_title"), timeout=300)
        self.guild_id = guild_id
        self.nick_input = discord.ui.TextInput(
            label=t(guild_id, "config.nickname_label"),
            placeholder=t(guild_id, "config.nickname_placeholder"),
            required=False,
            max_length=32,
        )
        self.add_item(self.nick_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        gid = self.guild_id
        nick = self.nick_input.value.strip()
        new_nick = nick if nick else None

        try:
            await guild.me.edit(nick=new_nick)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(description=t(gid, "config.no_permission"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{custom_emojis.get('cross')} {e}", color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        if new_nick:
            msg = t(gid, "config.nickname_changed", name=new_nick)
        else:
            msg = t(gid, "config.nickname_reset")
        await interaction.response.send_message(
            embed=discord.Embed(description=msg, color=COLOR_SUCCESS),
            ephemeral=True,
        )


class ConfigView(discord.ui.View):
    """Ce que /config sait encore faire.

    La langue, les salons et les rôles sont partis sur cyqbot.eu le
    11/10/2026 : les régler à deux endroits, c'était deux endroits à tenir
    à jour et un moyen sûr de se contredire. Restent ici l'apparence du
    bot et le renommage de ses salons, que le site ne fait pas."""

    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild
        self.guild_id = guild.id

    @discord.ui.button(label="🎨", style=discord.ButtonStyle.secondary, row=0, custom_id="cfg:appearance")
    async def btn_appearance(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        gid = self.guild_id
        embed = discord.Embed(
            title=t(gid, "config.appearance_title"),
            description=t(gid, "config.appearance_desc"),
            color=COLOR_INFO,
        )
        embed.set_footer(text=t(gid, "config.footer"))
        await interaction.response.edit_message(embed=embed, view=AppearanceView(self.guild))

    @discord.ui.button(label="✏️", style=discord.ButtonStyle.primary, row=0, custom_id="cfg:rename")
    async def btn_rename(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Choisir un salon ou un rôle du bot, puis lui donner le nom qu'on veut."""
        gid = self.guild_id
        options = []
        for key, kind in RENAMABLE_RESOURCES:
            resource = _resolve_resource(self.guild, key, kind)
            if resource is None:
                continue
            options.append(
                discord.SelectOption(
                    label=resources.resource_name(gid, key)[:100],
                    value=key,
                    description=t(gid, f"config.kind_{kind}")[:100],
                    emoji=RESOURCE_EMOJI.get(kind, "📁"),
                )
            )
        if not options:
            await interaction.response.send_message(t(gid, "config.rename_nothing"), ephemeral=True)
            return

        select = discord.ui.Select(placeholder=t(gid, "config.rename_pick"), options=options[:25])

        async def pick(choice: discord.Interaction) -> None:
            await choice.response.send_modal(RenameModal(self.guild, select.values[0]))

        select.callback = pick
        view = discord.ui.View(timeout=300)
        view.add_item(select)
        await interaction.response.send_message(
            content=t(gid, "config.rename_help"), view=view, ephemeral=True
        )

    @discord.ui.button(label="🏠", style=discord.ButtonStyle.success, row=1, custom_id="cfg:home")
    async def btn_home(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=_main_embed(self.guild), view=self)


class AppearanceView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild
        self.guild_id = guild.id

    @discord.ui.button(label="Avatar", style=discord.ButtonStyle.primary, emoji="🖼️", row=0)
    async def btn_avatar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            UrlModal(
                self.guild_id,
                "avatar",
                t(self.guild_id, "config.avatar_modal_title"),
                t(self.guild_id, "config.url_label"),
                "https://…",
            )
        )

    @discord.ui.button(label="Banner", style=discord.ButtonStyle.primary, emoji="🏞️", row=0)
    async def btn_banner(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            UrlModal(
                self.guild_id,
                "banner",
                t(self.guild_id, "config.banner_modal_title"),
                t(self.guild_id, "config.url_label"),
                "https://…",
            )
        )

    @discord.ui.button(label="Nickname", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def btn_nickname(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(NicknameModal(self.guild_id))

    @discord.ui.button(emoji=custom_emojis.get("replymsg"), style=discord.ButtonStyle.secondary, row=1)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=_main_embed(self.guild), view=ConfigView(self.guild))


RESOURCE_EMOJI = {"text": "💬", "voice": "🔊", "category": "📂", "role": "🎭"}


def _resolve_resource(guild: discord.Guild, key: str, kind: str):
    if kind == "text":
        return resources.get_text_channel(guild, key)
    if kind == "voice":
        return resources.get_voice_channel(guild, key)
    if kind == "category":
        return resources.get_category(guild, key)
    return resources.get_role(guild, key)


class RenameModal(discord.ui.Modal):
    """Renomme un salon ou un rôle du bot, et mémorise le choix."""

    def __init__(self, guild: discord.Guild, key: str):
        gid = guild.id
        super().__init__(title=t(gid, "config.rename_modal")[:45])
        self.guild = guild
        self.key = key
        self.field = discord.ui.TextInput(
            label=t(gid, "config.rename_label")[:45],
            default=resources.resource_name(gid, key)[:100],
            placeholder=t(gid, "config.rename_placeholder")[:100],
            required=False,
            max_length=90,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = self.guild.id
        kind = dict(RENAMABLE_RESOURCES)[self.key]
        resource = _resolve_resource(self.guild, self.key, kind)
        if resource is None:
            await interaction.response.send_message(t(gid, "config.rename_gone"), ephemeral=True)
            return

        raw = sanitize(self.field.value.strip(), 90)
        # Champ vidé : on retire le nom personnalisé et on revient au traduit.
        set_custom_name(gid, self.key, raw or None)
        wanted = resources.resource_name(gid, self.key)

        try:
            await resource.edit(name=wanted, reason="Renommage demandé via /config")
        except discord.Forbidden:
            await interaction.response.send_message(t(gid, "config.rename_no_perm"), ephemeral=True)
            return
        except discord.HTTPException as e:
            # Discord limite les renommages de salon à 2 par 10 min : le nom
            # est mémorisé quand même, il s'appliquera au prochain essai.
            log.warning(f"[{self.guild.name}] Renommage refusé par Discord : {e}")
            await interaction.response.send_message(
                t(gid, "config.rename_rate_limited", name=wanted), ephemeral=True
            )
            return

        await interaction.response.send_message(
            t(gid, "config.rename_done" if raw else "config.rename_reset", name=wanted),
            ephemeral=True,
        )


class Config(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="config",
        description="Open the interactive configuration panel for this server.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        if gid is None or guild is None:
            return

        if GUNZFRANCE_GUILD_ID and gid == GUNZFRANCE_GUILD_ID:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="🇫🇷 Utilise les commandes admin du serveur officiel.",
                    color=COLOR_INFO,
                ),
                ephemeral=True,
            )
            return

        # Pas de « configure d'abord le bot » : /config est une commande
        # d'administration, utilisable dès l'arrivée du bot.
        await interaction.response.send_message(
            embed=_main_embed(guild),
            view=ConfigView(guild),
            ephemeral=True,
        )

    @config.error
    async def config_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=discord.Embed(description=t(interaction.guild_id, "config.no_permission"), color=COLOR_ERROR),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Config(bot))
