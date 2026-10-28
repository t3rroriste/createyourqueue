"""
Cog : Ghost
===========
Bot temporaire — /ghost, réservée aux administrateurs.

Ghost ping d'arrivée : chaque nouveau membre est mentionné dans les salons
choisis par l'administrateur, puis le message est supprimé au bout de
2,5 secondes. La notification est partie, le salon reste vide.
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

import embeds
from i18n import get_lang, t
from json_store import write_json

log = logging.getLogger("bot.ghost")

# Fichier à part, pas guild_settings.json : lancé dans un autre processus que
# le bot principal (--bot temporaire), le bot temporaire écraserait sinon les
# réglages que le principal vient d'enregistrer.
GHOST_FILE = "data/ghost_ping.json"

MAX_CHANNELS = 5
DELETE_AFTER = 2.5    # secondes avant la suppression du message
BATCH_WINDOW = 1.0    # les arrivées de la même seconde partent dans un seul message
MAX_MENTIONS = 20     # mentions par message ; au-delà, un message de plus

# Le message ne contient que des mentions de membres : rien d'autre ne doit
# pouvoir sonner.
PING_MENTIONS = discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False)


def seconds_text(guild_id: int | None) -> str:
    """Le délai tel qu'on l'écrit dans la langue du serveur : « 2,5 » en
    français, espagnol et allemand, « 2.5 » en anglais et en coréen."""
    text = f"{DELETE_AFTER:g}"
    return text.replace(".", ",") if get_lang(guild_id) in ("fr", "es", "de") else text


class Ghost(commands.Cog):
    """Ghost ping des nouveaux membres."""

    # default_permissions cache la commande aux non-administrateurs ; le
    # contrôle has_permissions de chaque sous-commande tient même si un
    # serveur rouvre l'accès dans ses réglages d'intégrations.
    ghost = app_commands.Group(
        name="ghost",
        description="Ghost ping des nouveaux membres (administrateurs).",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channels: dict[int, list[int]] = self._load()  # guild_id -> salons
        self.waiting: dict[int, list[int]] = {}             # guild_id -> membres à mentionner
        self.tasks: set[asyncio.Task] = set()

    def cog_unload(self) -> None:
        for task in self.tasks:
            task.cancel()

    # ------------------------------------------------------------------
    # Enregistrement
    # ------------------------------------------------------------------
    @staticmethod
    def _load() -> dict[int, list[int]]:
        """Charge les salons. Un fichier illisible est mis de côté, jamais écrasé."""
        if not os.path.exists(GHOST_FILE):
            return {}
        try:
            with open(GHOST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {int(gid): [int(cid) for cid in ids] for gid, ids in data.items()}
        except (OSError, ValueError, TypeError, AttributeError) as e:
            backup = f"{GHOST_FILE}.illisible-{int(time.time())}"
            try:
                os.replace(GHOST_FILE, backup)
                log.error(f"Salons du ghost ping illisibles ({e}) : fichier mis de côté dans {backup}")
            except OSError:
                log.error(f"Salons du ghost ping illisibles ({e}), et impossibles à mettre de côté")
            return {}

    def _save(self) -> None:
        try:
            write_json(GHOST_FILE, {str(gid): ids for gid, ids in self.channels.items() if ids}, indent=4)
        except OSError as e:
            log.error(f"Salons du ghost ping non enregistrés : {e}")

    # ------------------------------------------------------------------
    # Arrivées
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # Si le serveur a un règlement d'accueil Discord, le nouveau venu ne
        # voit aucun salon tant qu'il ne l'a pas accepté : la mention tomberait
        # dans le vide.
        if not member.bot and not member.pending:
            self._queue(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.pending and not after.pending and not after.bot:
            self._queue(after)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        ids = self.channels.get(channel.guild.id, [])
        if channel.id in ids:
            ids.remove(channel.id)
            self._save()

    def _queue(self, member: discord.Member) -> None:
        gid = member.guild.id
        if not self.channels.get(gid):
            return
        waiting = self.waiting.setdefault(gid, [])
        if member.id in waiting:
            return
        waiting.append(member.id)
        # Premier arrivé de la fournée : on programme l'envoi.
        if len(waiting) == 1:
            task = asyncio.create_task(self._flush(gid))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def _flush(self, guild_id: int) -> None:
        await asyncio.sleep(BATCH_WINDOW)
        # Fournée retirée AVANT l'envoi : un membre qui arrive pendant l'envoi
        # en ouvre une nouvelle au lieu d'être oublié.
        member_ids = self.waiting.pop(guild_id, [])
        guild = self.bot.get_guild(guild_id)
        if guild is not None and member_ids:
            await self._ping(guild, member_ids)

    async def _ping(self, guild: discord.Guild, member_ids: list[int]) -> tuple[int, int]:
        """Ghost ping dans tous les salons du serveur, en même temps."""
        mentions = [f"<@{uid}>" for uid in member_ids]
        messages = [" ".join(mentions[i:i + MAX_MENTIONS]) for i in range(0, len(mentions), MAX_MENTIONS)]
        configured = self.channels.get(guild.id, [])
        channels = []
        for channel_id in configured:
            channel = guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                channels.append(channel)
        results = await asyncio.gather(*(self._send(channel, messages) for channel in channels))
        return sum(results), len(configured)

    @staticmethod
    async def _send(channel: discord.TextChannel, messages: list[str]) -> bool:
        perms = channel.permissions_for(channel.guild.me)
        if not (perms.view_channel and perms.send_messages):
            log.warning(f"[{channel.guild.name}] Ghost ping impossible dans #{channel.name} : permission manquante")
            return False
        try:
            for text in messages:
                # delete_after : discord.py supprime le message en arrière-plan,
                # sans permission particulière (c'est le message du bot).
                await channel.send(text, delete_after=DELETE_AFTER, allowed_mentions=PING_MENTIONS)
        except discord.HTTPException as e:
            log.warning(f"[{channel.guild.name}] Ghost ping échoué dans #{channel.name} : {e}")
            return False
        return True

    # ------------------------------------------------------------------
    # Commandes
    # ------------------------------------------------------------------
    @staticmethod
    async def _reply(interaction: discord.Interaction, text: str, kind: str) -> None:
        embed = embeds.base(interaction.guild_id, description=text, kind=kind)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ghost.command(name="add", description="Ajoute un salon où les nouveaux membres sont ghost ping.")
    @app_commands.describe(salon="Le salon où mentionner les nouveaux membres")
    @app_commands.checks.has_permissions(administrator=True)
    async def add(self, interaction: discord.Interaction, salon: discord.TextChannel):
        gid = interaction.guild_id
        ids = self.channels.get(gid, [])

        if salon.id in ids:
            await self._reply(interaction, t(gid, "ghost.already", channel=salon.mention), "warning")
            return
        if len(ids) >= MAX_CHANNELS:
            await self._reply(interaction, t(gid, "ghost.limit", max=MAX_CHANNELS), "error")
            return
        perms = salon.permissions_for(salon.guild.me)
        if not (perms.view_channel and perms.send_messages):
            await self._reply(interaction, t(gid, "ghost.bot_cannot_write", channel=salon.mention), "error")
            return

        self.channels.setdefault(gid, []).append(salon.id)
        self._save()
        log.info(f"{interaction.user} a activé le ghost ping dans #{salon.name}")

        text = t(gid, "ghost.added", channel=salon.mention, seconds=seconds_text(gid))
        # Première cause d'un ghost ping « qui ne marche pas » : un nouveau
        # membre ne voit pas le salon, donc ne reçoit rien.
        if not salon.permissions_for(salon.guild.default_role).view_channel:
            text += "\n\n" + t(gid, "ghost.hidden_warning")
        await self._reply(interaction, text, "success")

    @ghost.command(name="remove", description="Retire un salon du ghost ping.")
    @app_commands.describe(salon="Le salon à retirer")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove(self, interaction: discord.Interaction, salon: discord.TextChannel):
        gid = interaction.guild_id
        ids = self.channels.get(gid, [])
        if salon.id not in ids:
            await self._reply(interaction, t(gid, "ghost.not_listed", channel=salon.mention), "warning")
            return
        ids.remove(salon.id)
        self._save()
        log.info(f"{interaction.user} a retiré le ghost ping de #{salon.name}")
        await self._reply(interaction, t(gid, "ghost.removed", channel=salon.mention), "success")

    @ghost.command(name="list", description="Affiche les salons du ghost ping.")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_channels(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        ids = self.channels.get(gid, [])
        if not ids:
            await self._reply(interaction, t(gid, "ghost.list_empty"), "info")
            return
        description = t(gid, "ghost.list_desc", seconds=seconds_text(gid), count=len(ids), max=MAX_CHANNELS)
        description += "\n\n" + "\n".join(f"• <#{cid}>" for cid in ids)
        embed = embeds.base(gid, title=t(gid, "ghost.list_title"), description=description, kind="info")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ghost.command(name="test", description="T'envoie un ghost ping dans les salons configurés.")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_ping(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not self.channels.get(gid):
            await self._reply(interaction, t(gid, "ghost.list_empty"), "info")
            return
        await interaction.response.defer(ephemeral=True)
        sent, total = await self._ping(interaction.guild, [interaction.user.id])
        embed = embeds.base(
            gid,
            description=t(gid, "ghost.test_sent", sent=sent, total=total, seconds=seconds_text(gid)),
            kind="success" if sent == total else "warning",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ghost(bot))
    log.info("Cog Ghost chargé")
