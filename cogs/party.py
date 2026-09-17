"""
Cog : Party
===========
Commandes : /duo, /trio, /quatro, /groupe

S'inscrire à plusieurs et être **garanti dans la même équipe**, comme dans
Valorant ou Rocket League.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import custom_emojis
import embeds
import resources
from guild_settings import (
    MAX_PARTY,
    get_party_of, save_party, dissolve_party,
    get_team_request, save_team_request, delete_team_request, get_team_requests,
    get_queue_config,
)
from i18n import t
from text_safety import USERS_ONLY

log = logging.getLogger("bot.party")


def party_members(guild: discord.Guild, user_id: int) -> list[int]:
    """Coéquipiers garantis d'un joueur, lui inclus. Liste vide s'il est seul."""
    party = get_party_of(guild.id, user_id)
    return list(party.get("members", [])) if party else []


def group_players(guild: discord.Guild, players: list) -> list[list]:
    """Regroupe des joueurs par groupe, les solos en groupes d'un."""
    by_id = {m.id: m for m in players}
    seen: set[int] = set()
    blocks: list[list] = []
    for member in players:
        if member.id in seen:
            continue
        ids = [uid for uid in party_members(guild, member.id) if uid in by_id] or [member.id]
        seen.update(ids)
        blocks.append([by_id[uid] for uid in ids])
    return blocks


class RequestView(discord.ui.View):
    """Accepter / refuser une demande d'équipe."""

    def __init__(self, cog: "Party", guild_id: int, message_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.message_id = message_id
        self.accept.label = t(guild_id, "party.btn_accept")
        self.decline.label = t(guild_id, "party.btn_decline")
        self.accept.emoji = custom_emojis.get("checkmark")
        self.decline.emoji = custom_emojis.get("cross")

    def _request(self, interaction: discord.Interaction) -> dict | None:
        message_id = self.message_id or (interaction.message.id if interaction.message else 0)
        return get_team_request(self.guild_id, message_id)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        request = self._request(interaction)
        if request is None:
            await interaction.response.send_message(
                t(self.guild_id, "party.req_gone"), ephemeral=True
            )
            return False
        if interaction.user.id not in request.get("invited", []):
            await interaction.response.send_message(
                t(self.guild_id, "party.req_not_for_you"), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, emoji="✅",
                       custom_id="cyq:party:accept")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        gid = self.guild_id
        request = self._request(interaction)
        if request is None:
            return
        if interaction.user.id in request.get("accepted", []):
            await interaction.response.send_message(t(gid, "party.req_already"), ephemeral=True)
            return

        request.setdefault("accepted", []).append(interaction.user.id)
        pending = [uid for uid in request["invited"] if uid not in request["accepted"]]

        if pending:
            save_team_request(gid, request)
            await interaction.response.edit_message(
                embed=self.cog.request_embed(interaction.guild, request), view=self
            )
            return

        # Tout le monde a accepté : le groupe existe.
        members = [request["leader"]] + list(request["invited"])
        save_party(gid, members)
        delete_team_request(gid, request["message_id"])
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=self.cog.formed_embed(interaction.guild, members), view=self
        )

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="✖️",
                       custom_id="cyq:party:decline")
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        gid = self.guild_id
        request = self._request(interaction)
        if request is None:
            return
        delete_team_request(gid, request["message_id"])
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=embeds.base(
                gid,
                title=t(gid, "party.declined_title"),
                description=t(gid, "party.declined_desc", member=interaction.user.mention),
                kind="error",
            ),
            view=self,
        )


class Party(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._restored = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Réactive les boutons des demandes encore en attente."""
        if self._restored:
            return
        self._restored = True
        for guild in self.bot.guilds:
            for request in get_team_requests(guild.id):
                try:
                    self.bot.add_view(
                        RequestView(self, guild.id, request["message_id"]),
                        message_id=request["message_id"],
                    )
                except Exception as e:
                    log.error(f"Demande d'équipe non restaurée sur {guild.name} : {e}")

    # -- Embeds ----------------------------------------------------------
    def request_embed(self, guild: discord.Guild, request: dict) -> discord.Embed:
        gid = guild.id
        invited = request["invited"]
        accepted = request.get("accepted", [])
        embed = embeds.base(
            gid,
            title=t(gid, "party.req_title", size=len(invited) + 1),
            description=t(gid, "party.req_desc", leader=f"<@{request['leader']}>"),
            kind="brand",
        )
        embeds.brand(embed, guild)
        embeds.section(
            embed, t(gid, "party.field_invited"),
            "\n".join(
                f"{'✅' if uid in accepted else '⏳'} <@{uid}>" for uid in invited
            ),
        )
        embed.set_footer(text=t(gid, "party.req_footer"))
        return embed

    def formed_embed(self, guild: discord.Guild, members: list[int]) -> discord.Embed:
        gid = guild.id
        embed = embeds.base(
            gid,
            title=t(gid, "party.formed_title", size=len(members)),
            description=" ".join(f"<@{uid}>" for uid in members),
            kind="success",
            footer=t(gid, "party.formed_footer"),
        )
        embeds.brand(embed, guild)
        return embed

    # -- Création d'une demande ------------------------------------------
    async def _request(self, interaction: discord.Interaction, invited: list[discord.Member]) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        author = interaction.user

        cleaned, seen = [], {author.id}
        for member in invited:
            if member is None or member.id in seen:
                continue
            seen.add(member.id)
            cleaned.append(member)

        if not cleaned:
            await interaction.response.send_message(t(gid, "party.err_empty"), ephemeral=True)
            return
        if any(m.bot for m in cleaned):
            await interaction.response.send_message(t(gid, "party.err_bot"), ephemeral=True)
            return

        size = len(cleaned) + 1
        if size > MAX_PARTY:
            await interaction.response.send_message(
                t(gid, "party.err_too_big", max=MAX_PARTY), ephemeral=True
            )
            return

        # Un groupe plus grand qu'une équipe ne pourrait jamais tenir : mieux
        # vaut le refuser tout de suite que le trahir au lancement.
        config = get_queue_config(gid) or {}
        limit = int(config.get("max_players_per_team", MAX_PARTY) or MAX_PARTY)
        if size > limit:
            await interaction.response.send_message(
                t(gid, "party.err_bigger_than_team", size=size, limit=limit), ephemeral=True
            )
            return

        busy = [m for m in cleaned if get_party_of(gid, m.id)]
        if busy:
            await interaction.response.send_message(
                t(gid, "party.err_busy", members=", ".join(m.mention for m in busy)),
                ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        channel = resources.get_text_channel(guild, "channel_team_request")
        if channel is None:
            await interaction.response.send_message(
                t(gid, "party.err_no_channel",
                  channel=resources.resource_name(gid, "channel_team_request")),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        request = {
            "message_id": 0,
            "leader": author.id,
            "invited": [m.id for m in cleaned],
            "accepted": [],
        }
        try:
            # Publié sans vue : l'identifiant du message n'existe pas encore,
            # et la vue en a besoin pour retrouver sa demande.
            message = await channel.send(
                content=" ".join(m.mention for m in cleaned),
                embed=self.request_embed(guild, request),
                allowed_mentions=USERS_ONLY,
            )
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Demande d'équipe non publiée : {e}")
            await interaction.followup.send(t(gid, "party.err_failed"), ephemeral=True)
            return

        request["message_id"] = message.id
        save_team_request(gid, request)
        view = RequestView(self, gid, message.id)
        try:
            await message.edit(view=view)
            self.bot.add_view(view, message_id=message.id)
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Boutons de la demande non attachés : {e}")
            delete_team_request(gid, message.id)
            await interaction.followup.send(t(gid, "party.err_failed"), ephemeral=True)
            return

        await interaction.followup.send(
            t(gid, "party.req_sent", link=message.jump_url), ephemeral=True
        )

    # -- Commandes -------------------------------------------------------
    @app_commands.command(name="groupe", description="Affiche ton groupe, ou le dissout.")
    @app_commands.describe(dissoudre="Coche pour quitter ton groupe")
    async def groupe(self, interaction: discord.Interaction, dissoudre: bool = False) -> None:
        gid = interaction.guild_id
        if dissoudre:
            removed = dissolve_party(gid, interaction.user.id)
            await interaction.response.send_message(
                t(gid, "party.dissolved" if removed else "party.none"), ephemeral=True
            )
            return

        party = get_party_of(gid, interaction.user.id)
        if party is None:
            await interaction.response.send_message(t(gid, "party.none"), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=self.formed_embed(interaction.guild, party["members"]), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Party(bot))
    log.info("Cog Party chargé")
