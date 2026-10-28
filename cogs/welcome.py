"""
Cog : Welcome
=============
Le message d'arrivée : quand le bot rejoint un serveur, il dit bonjour et
renvoie au panneau web. Rien d'autre.

Il y avait ici un parcours complet : choix de la langue par boutons, puis
passage au choix des salons (cogs/wizard.py). Il a été retiré le
11/10/2026, parce que toute la configuration vit maintenant sur
cyqbot.eu. Configurer un serveur à coups de menus dans un salon était la
seule solution tant qu'il n'y avait pas de panneau ; elle laissait un
message d'assistant épinglé dans le salon de tout le monde, et elle
dupliquait des réglages qui existent désormais ailleurs, en mieux.

Ce qui N'A PAS été retiré, et qui reste donc joignable :
  · /setup et /option ouvrent toujours l'assistant dans Discord ;
  · cogs/reset.py republie toujours son panneau après une remise à zéro ;
  · LanguageSelectView est conservée — cogs/wizard.py l'importe pour son
    bouton « revenir à la langue », et les messages déjà envoyés sur les
    serveurs existants continuent de répondre.
Supprimer tout ça est une autre décision, qui casserait ces trois chemins.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

import custom_emojis
import embeds
from i18n import set_lang, t

log = logging.getLogger("bot.welcome")

# Salons essayés d'abord, dans cet ordre ; sinon, le premier où le bot peut écrire.
PREFERRED_CHANNELS = ("general", "général", "accueil", "welcome")

# Code, libellé, drapeau.
LANGUAGES = [
    ("fr", "France", "🇫🇷"),
    ("en", "English", "🇬🇧"),
    ("es", "Español", "🇪🇸"),
    ("de", "Deutsch", "🇩🇪"),
    ("ko", "한국어", "🇰🇷"),
]

# Le message d'arrivée, en embed.
#
# En anglais et sans traduction : la langue du serveur n'est plus demandée à
# l'arrivée, donc on ne la connaît pas encore au moment d'écrire. L'anglais
# est le plus sûr des défauts, et le lien, lui, parle toutes les langues.
DASHBOARD_URL = "https://cyqbot.eu/"
JOIN_TITLE = "Thanks for adding me !"
JOIN_BODY = "Manage all your discord with dashboard !"


def join_embed() -> discord.Embed:
    """Le message d'arrivée : tout dans la description, pas de titre
    d'embed, pour garder exactement la mise en forme demandée.

    Les deux emojis viennent de l'application (Developer Portal → Emojis).
    S'ils n'y sont pas, custom_emojis rend 👋 et 📊 : le message reste
    lisible, il perd juste les emojis perso."""
    hello = custom_emojis.get("hellowave")
    dashboard = custom_emojis.get("wobble6")
    return embeds.base(
        None,
        description=(f"{hello} **{JOIN_TITLE}**\n\n"
                     f"{dashboard} **{JOIN_BODY}**\n\n"
                     f"> {DASHBOARD_URL}"),
    )


def join_view() -> discord.ui.View:
    """Le bouton Dashboard.

    Un bouton de lien n'a pas d'identifiant et n'appelle jamais le bot :
    il n'y a donc rien à réenregistrer au démarrage, il marchera encore
    dans un an sur un message publié aujourd'hui."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Dashboard", url=DASHBOARD_URL,
                                    style=discord.ButtonStyle.link))
    return view


class LanguageSelectView(discord.ui.View):
    """Les cinq boutons de langue.

    Plus envoyée à l'arrivée, mais toujours vivante : wizard.py s'en sert
    pour revenir au choix de la langue, et les messages déjà postés sur les
    serveurs doivent continuer de répondre après un redémarrage.
    """

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
        # qui peut gérer le serveur, comme le reste de l'assistant.
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
    """Le message d'arrivée, et rien de plus."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Les panneaux de langue déjà en place sur les serveurs doivent
        # répondre après un redémarrage, même si on n'en envoie plus.
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
        """Un seul message, aucune suite."""
        channel = self._pick_channel(guild)
        if channel is None:
            log.info(f"[{guild.name}] Aucun salon où écrire : message d'arrivée non envoyé.")
            return

        try:
            await channel.send(embed=join_embed(), view=join_view())
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Message d'arrivée non envoyé : {e}")
            return

        log.info(f"[{guild.name}] Message d'arrivée envoyé dans #{channel.name}.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
