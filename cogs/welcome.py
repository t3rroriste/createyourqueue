"""
Cog : Welcome
=============
Le message d'arrivée : quand le bot rejoint un serveur, il se présente et fait
choisir la langue. Le même message passe ensuite au choix des salons
(voir cogs/wizard.py).
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from config import COLOR_INFO
from guild_settings import set_setup_panel
from i18n import set_lang, t

log = logging.getLogger("bot.welcome")

# Salons essayés d'abord, dans cet ordre ; sinon, le premier où le bot peut écrire.
PREFERRED_CHANNELS = ("general", "général", "accueil", "welcome")

# Code, libellé, drapeau. Les identifiants `lang_xx` sont ceux des messages
# d'arrivée déjà envoyés : les garder, c'est ce qui laisse ces messages
# fonctionner.
LANGUAGES = [
    ("fr", "France", "🇫🇷"),
    ("en", "English", "🇬🇧"),
    ("es", "Español", "🇪🇸"),
    ("de", "Deutsch", "🇩🇪"),
    ("ko", "한국어", "🇰🇷"),
]


class LanguageSelectView(discord.ui.View):
    """Les cinq boutons de langue du message d'arrivée.

    Persistante : enregistrée une fois au chargement du cog, elle répond sur
    tous les messages d'arrivée, y compris après un redémarrage. Avant, les
    boutons ne répondaient plus dès que le bot avait redémarré."""

    def __init__(self, guild_id: int = 0) -> None:
        super().__init__(timeout=None)
        self.guild_id = guild_id
        for code, label, emoji in LANGUAGES:
            button = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.primary,
                custom_id=f"lang_{code}",
            )
            button.callback = self._choose(code)
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Choisir la langue du serveur et ouvrir sa configuration : réservé à
        # qui peut gérer le serveur, comme le reste de l'assistant. Avant,
        # n'importe quel membre pouvait changer la langue.
        member = interaction.user
        if isinstance(member, discord.Member) and member.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message(t(interaction.guild_id, "wiz.admin_only"), ephemeral=True)
        return False

    @staticmethod
    def _choose(code: str):
        async def callback(interaction: discord.Interaction) -> None:
            from cogs.wizard import ChannelsWizard, channels_embed

            guild = interaction.guild
            if guild is None:
                return
            set_lang(guild.id, code)
            # Le message de langue devient le panneau des salons : pas de
            # second message.
            await interaction.response.edit_message(
                content=None,
                embed=channels_embed(guild, intro=True),
                view=ChannelsWizard(guild, intro=True),
            )
        return callback


class Welcome(commands.Cog):
    """Système d'accueil et sélection de langue."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(LanguageSelectView())

    @staticmethod
    def _pick_channel(guild: discord.Guild) -> discord.TextChannel | None:
        def can_write(channel: discord.TextChannel) -> bool:
            return channel.permissions_for(guild.me).send_messages

        for name in PREFERRED_CHANNELS:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel is not None and can_write(channel):
                return channel
        return next((c for c in guild.text_channels if can_write(c)), None)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Envoyé quand le bot rejoint un serveur."""
        channel = self._pick_channel(guild)
        if channel is None:
            log.info(f"[{guild.name}] Aucun salon où écrire : message d'arrivée non envoyé.")
            return

        embed = discord.Embed(
            title=t(guild.id, "welcome.title"),
            description=t(guild.id, "welcome.description"),
            color=COLOR_INFO,
        )
        try:
            message = await channel.send(embed=embed, view=LanguageSelectView(guild.id))
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Message d'arrivée non envoyé : {e}")
            return
        # Mémorisé pour que l'assistant réattache ses menus de salons à ce
        # message après un redémarrage (voir cogs/wizard.py, on_ready).
        set_setup_panel(guild.id, channel.id, message.id)
        log.info(f"[{guild.name}] Message d'arrivée envoyé dans #{channel.name}.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
