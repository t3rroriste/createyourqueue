"""
Cog : Queue Guide
=================
Commande : /queue-guide

Guide pas-à-pas pour organiser une queue de A à Z, destiné à quelqu'un qui
n'a jamais utilisé le bot. Chaque étape tient sur un écran, avec des boutons
Précédent / Suivant plutôt qu'un pavé de texte que personne ne lit.

Le guide affiche aussi un état en direct de la configuration du serveur
(salons créés ? rôles en place ?) : la première cause de blocage est un
`/setup` jamais lancé, et un texte statique ne peut pas le signaler.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import embeds
import resources
from i18n import t

log = logging.getLogger("bot.queue_guide")

# (emoji, clé du titre, clé du corps) — l'ordre définit les étapes.
STEPS = [
    ("🛠️", "qguide.s1_title", "qguide.s1_body"),
    ("🎮", "qguide.s2_title", "qguide.s2_body"),
    ("✅", "qguide.s3_title", "qguide.s3_body"),
    ("🚀", "qguide.s4_title", "qguide.s4_body"),
    ("🏆", "qguide.s5_title", "qguide.s5_body"),
    ("🧰", "qguide.s6_title", "qguide.s6_body"),
]


def server_status(guild: discord.Guild) -> str:
    """État de la configuration du serveur, en clair, pour l'étape 1."""
    gid = guild.id
    checks = [
        ("channel_queue_command", resources.get_text_channel(guild, "channel_queue_command")),
        ("channel_queue_announcement", resources.get_text_channel(guild, "channel_queue_announcement")),
        ("channel_queue_resultat", resources.get_text_channel(guild, "channel_queue_resultat")),
        ("channel_queue_classement", resources.get_text_channel(guild, "channel_queue_classement")),
        ("voice_queue_waiting", resources.get_voice_channel(guild, "voice_queue_waiting")),
        ("role_staff", resources.get_role(guild, "role_staff")),
    ]
    missing = [key for key, found in checks if found is None]
    if not missing:
        return t(gid, "qguide.status_ready")
    names = ", ".join(f"`{resources.resource_name(gid, key)}`" for key in missing)
    return t(gid, "qguide.status_missing", items=names)


def build_step_embed(guild: discord.Guild, index: int) -> discord.Embed:
    gid = guild.id
    emoji, title_key, body_key = STEPS[index]
    embed = embeds.base(
        gid,
        title=f"{emoji}  {t(gid, title_key)}",
        description=t(gid, body_key),
        footer=t(gid, "qguide.footer", step=index + 1, total=len(STEPS)),
    )
    embeds.brand(embed, guild)
    if index == 0:
        embeds.section(embed, t(gid, "qguide.status_field"), server_status(guild))
    return embed


class GuideView(discord.ui.View):
    def __init__(self, guild: discord.Guild, author_id: int, index: int = 0):
        super().__init__(timeout=600)
        self.guild = guild
        self.author_id = author_id
        self.index = index
        self._sync()

    def _sync(self) -> None:
        gid = self.guild.id
        self.prev.label = t(gid, "qguide.btn_prev")
        self.next.label = t(gid, "qguide.btn_next")
        self.prev.disabled = self.index == 0
        self.next.disabled = self.index >= len(STEPS) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(t(self.guild.id, "qguide.not_yours"), ephemeral=True)
            return False
        return True

    async def _show(self, interaction: discord.Interaction) -> None:
        self._sync()
        await interaction.response.edit_message(embed=build_step_embed(self.guild, self.index), view=self)

    @discord.ui.button(label="Précédent", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def prev(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.index = max(0, self.index - 1)
        await self._show(interaction)

    @discord.ui.button(label="Suivant", style=discord.ButtonStyle.primary, emoji="▶️")
    async def next(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.index = min(len(STEPS) - 1, self.index + 1)
        await self._show(interaction)


class QueueGuide(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="guide", description="Guide pas-à-pas pour organiser ta première queue.")
    async def queue_guide(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(t(None, "common.members_only"), ephemeral=True)
            return
        view = GuideView(guild, interaction.user.id)
        await interaction.response.send_message(
            embed=build_step_embed(guild, 0), view=view, ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QueueGuide(bot))
    log.info("Cog QueueGuide chargé")
