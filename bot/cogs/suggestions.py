"""
Cog : Suggestions
=================
Bot temporaire — /suggestions, réservée aux administrateurs.

Chaque nouvelle suggestion reçoit deux réactions pour voter : Wobble4 pour,
Wobble3 contre. Dans un forum, la réaction va sur le premier message de
chaque post ; dans un salon textuel, sur chaque message d'un membre.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import discord
from discord import app_commands
from discord.ext import commands

import custom_emojis
import embeds
from i18n import t
from json_store import write_json

log = logging.getLogger("bot.suggestions")

# Fichier à part, comme le ghost ping : le bot temporaire tourne parfois dans
# un autre processus que le principal.
SUGGESTIONS_FILE = "data/suggestions.json"

# (nom de l'emoji, repli) : cherché sur le serveur, puis dans l'application.
UPVOTE = ("Wobble4", "👍")
DOWNVOTE = ("Wobble3", "👎")

REACT_PERMS = ("view_channel", "add_reactions", "read_message_history")


class Suggestions(commands.Cog):
    """Réactions de vote automatiques sur les suggestions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channels: dict[int, int] = self._load()  # guild_id -> salon des suggestions
        self._app_emojis: list[discord.Emoji] | None = None

    # ------------------------------------------------------------------
    # Enregistrement
    # ------------------------------------------------------------------
    @staticmethod
    def _load() -> dict[int, int]:
        """Charge les salons. Un fichier illisible est mis de côté, jamais écrasé."""
        if not os.path.exists(SUGGESTIONS_FILE):
            return {}
        try:
            with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
                return {int(gid): int(cid) for gid, cid in json.load(f).items()}
        except (OSError, ValueError, TypeError, AttributeError) as e:
            backup = f"{SUGGESTIONS_FILE}.illisible-{int(time.time())}"
            try:
                os.replace(SUGGESTIONS_FILE, backup)
                log.error(f"Salons de suggestions illisibles ({e}) : fichier mis de côté dans {backup}")
            except OSError:
                log.error(f"Salons de suggestions illisibles ({e}), et impossibles à mettre de côté")
            return {}

    def _save(self) -> None:
        try:
            write_json(SUGGESTIONS_FILE, {str(gid): cid for gid, cid in self.channels.items()}, indent=4)
        except OSError as e:
            log.error(f"Salons de suggestions non enregistrés : {e}")

    # ------------------------------------------------------------------
    # Réactions
    # ------------------------------------------------------------------
    async def vote_emojis(self, guild: discord.Guild) -> tuple[list, list[str]]:
        """Les deux emojis de vote, et les noms introuvables (remplacés par 👍 / 👎)."""
        if self._app_emojis is None:
            try:
                self._app_emojis = list(await self.bot.fetch_application_emojis())
            except discord.HTTPException as e:
                log.warning(f"Emojis de l'application non chargés : {e}")
        found, missing = [], []
        for name, fallback in (UPVOTE, DOWNVOTE):
            emoji = (custom_emojis.find(guild.emojis, name)
                     or custom_emojis.find(self._app_emojis or [], name))
            if emoji is None:
                missing.append(name)
            found.append(emoji or fallback)
        return found, missing

    def is_suggestion(self, message: discord.Message) -> bool:
        if message.guild is None or message.author.bot:
            return False
        target = self.channels.get(message.guild.id)
        channel = message.channel
        if isinstance(channel, discord.Thread):
            # Forum : la suggestion est le premier message du post, qui porte
            # le même identifiant que le post. Les réponses n'ont rien.
            return channel.parent_id == target and message.id == channel.id
        return channel.id == target

    async def add_votes(self, message: discord.Message) -> None:
        emojis, _ = await self.vote_emojis(message.guild)
        for emoji in emojis:
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException as e:
                log.warning(f"[{message.guild.name}] Réaction de vote impossible : {e}")
                return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if self.is_suggestion(message):
            await self.add_votes(message)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        """Filet de sécurité pour les forums : le premier message d'un post peut
        arriver avant le post lui-même. Réagir deux fois ne change rien."""
        if (thread.parent_id != self.channels.get(thread.guild.id)
                or not isinstance(thread.parent, discord.ForumChannel)):
            return
        await asyncio.sleep(2)
        try:
            message = thread.starter_message or await thread.fetch_message(thread.id)
        except discord.HTTPException:
            return
        if not message.author.bot:
            await self.add_votes(message)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if self.channels.get(channel.guild.id) == channel.id:
            del self.channels[channel.guild.id]
            self._save()

    # ------------------------------------------------------------------
    # Commande
    # ------------------------------------------------------------------
    @staticmethod
    async def _reply(interaction: discord.Interaction, text: str, kind: str) -> None:
        embed = embeds.base(interaction.guild_id, description=text, kind=kind)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="suggestions",
                          description="Réactions de vote automatiques sur les suggestions (administrateurs).")
    @app_commands.describe(activer="True pour activer, False pour couper",
                           salon="Le forum ou le salon des suggestions")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def suggestions(self, interaction: discord.Interaction, activer: bool,
                          salon: discord.ForumChannel | discord.TextChannel | None = None):
        gid = interaction.guild_id
        if not activer:
            if self.channels.pop(gid, None) is not None:
                self._save()
            await self._reply(interaction, t(gid, "suggest.disabled"), "warning")
            return

        channel = salon or interaction.guild.get_channel(self.channels.get(gid) or 0)
        if channel is None:
            await self._reply(interaction, t(gid, "suggest.need_channel"), "error")
            return
        perms = channel.permissions_for(interaction.guild.me)
        if not all(getattr(perms, name) for name in REACT_PERMS):
            await self._reply(interaction, t(gid, "suggest.bot_cannot_react", channel=channel.mention), "error")
            return

        # Les emojis de l'application peuvent demander un appel à Discord.
        await interaction.response.defer(ephemeral=True)
        self.channels[gid] = channel.id
        self._save()
        log.info(f"{interaction.user} a activé les réactions de suggestions dans #{channel.name}")

        (up, down), missing = await self.vote_emojis(interaction.guild)
        text = t(gid, "suggest.enabled", channel=channel.mention, up=up, down=down)
        if missing:
            text += "\n\n" + t(gid, "suggest.missing_emojis", names=", ".join(f"`{n}`" for n in missing))
        await self._reply(interaction, text, "success")


async def setup(bot: commands.Bot):
    await bot.add_cog(Suggestions(bot))
    log.info("Cog Suggestions chargé")
