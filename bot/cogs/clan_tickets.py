"""
Tickets du ClanWar
==================
Le bouton « Problème » d'un ClanWar ouvre un ticket vers le salon staff
choisi dans /option. Le ticket s'y affiche comme un ticket de modmail : le
staff clique sur « Répondre », le membre reçoit d'abord « ton ticket est
pris en charge », puis chaque réponse en message privé sous la forme
« **@staff :** … ». Le membre répond dans ce même MP et ses messages
reviennent dans le salon staff : c'est une vraie conversation, jusqu'à la
clôture.

Les tickets sont rangés dans guild_settings (voir save_clan_ticket) : un
redémarrage ne coupe ni les boutons ni la conversation.

Séparé de cogs/clan.py, qui dépassait 2 800 lignes. Ce n'est pas un cog : pas
de setup(), pas d'entrée dans config.py ; cogs/clan_war.py l'importe.
"""

from __future__ import annotations

import logging
import time

import discord

import custom_emojis
import embeds
import resources

from guild_settings import (
    MAX_CLAN_NAME, get_clan_ticket, get_ticket_config, open_clan_ticket_of,
    open_clan_tickets, save_clan_ticket, update_clan_ticket,
)
from i18n import t
from text_safety import sanitize

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cogs.clan_war import ClanWarSession

log = logging.getLogger("bot.clan")


async def send_dm(user: discord.abc.User, content: str | None = None, **kwargs) -> bool:
    """MP au membre. Faux s'il a fermé ses messages privés."""
    try:
        await user.send(content, **kwargs)
        return True
    except discord.HTTPException:
        log.info(f"MP impossible vers {getattr(user, 'id', '?')} (messages privés fermés ?)")
        return False


def ticket_link(guild_id: int, ticket: dict) -> str:
    """Lien vers le message du ticket dans le salon staff."""
    return (f"https://discord.com/channels/{guild_id}/"
            f"{ticket.get('channel_id')}/{ticket.get('message_id')}")


def restore_ticket_views(bot: discord.Client) -> None:
    """Au démarrage : les boutons des tickets encore ouverts répondent à nouveau."""
    restored = 0
    for guild in list(bot.guilds):
        for ticket in open_clan_tickets(guild.id):
            if not ticket.get("message_id"):
                continue
            bot.add_view(TicketActionView(guild.id, ticket["id"]),
                         message_id=int(ticket["message_id"]))
            restored += 1
    if restored:
        log.info(f"{restored} ticket(s) de ClanWar rattaché(s)")


async def forward_member_message(bot: discord.Client, message: discord.Message) -> None:
    """Le MP d'un membre au ticket ouvert repart dans le salon staff."""
    if message.author.bot or not isinstance(message.channel, discord.DMChannel):
        return
    ticket = None
    for guild in list(bot.guilds):
        found = open_clan_ticket_of(guild.id, message.author.id)
        if found and (ticket is None
                      or found.get("created_at", 0) > ticket.get("created_at", 0)):
            ticket = found
    if ticket is None:
        return

    gid = int(ticket["guild_id"])
    channel = bot.get_channel(int(ticket.get("channel_id") or 0))
    if channel is None:
        return
    text = message.content or ""
    if message.attachments:
        text += "\n" + "\n".join(a.url for a in message.attachments[:3])
    if not text.strip():
        return

    embed = discord.Embed(
        title=t(gid, "clan.ticket_member_msg_title", user=str(message.author))[:256],
        description=text[:4000],
        color=embeds.BLACK,
        timestamp=message.created_at,
    )
    embed.set_thumbnail(url=message.author.display_avatar.url)
    embed.add_field(name=t(gid, "clan.ticket_field_link"),
                    value=f"[{t(gid, 'clan.ticket_link_open')}]({ticket_link(gid, ticket)})")
    try:
        await channel.send(embed=embed)
    except discord.HTTPException as e:
        log.warning(f"Message de ticket non transmis au staff : {e}")
        return
    try:
        await message.add_reaction("✅")
    except discord.HTTPException:
        pass


class TicketProblemModal(discord.ui.Modal):
    """Modal pour signaler un problème."""

    def __init__(self, session: "ClanWarSession"):
        gid = session.guild_id
        super().__init__(title=t(gid, "clan.ticket_modal_title")[:45])
        self.session = session
        self.problem_type = discord.ui.TextInput(
            label=t(gid, "clan.ticket_type_label")[:45],
            style=discord.TextStyle.short,
            placeholder=t(gid, "clan.ticket_type_placeholder")[:100],
            required=True,
            max_length=50,
        )
        self.description = discord.ui.TextInput(
            label=t(gid, "clan.ticket_desc_label")[:45],
            style=discord.TextStyle.paragraph,
            placeholder=t(gid, "clan.ticket_desc_placeholder")[:100],
            required=True,
            max_length=1000,
        )
        self.add_item(self.problem_type)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Envoie le ticket au staff."""
        session = self.session
        gid = interaction.guild_id
        problem_type = sanitize(self.problem_type.value, 50)
        description = self.description.value

        ticket_config = get_ticket_config(gid)
        if not ticket_config or not ticket_config.get("enabled", False):
            await interaction.response.send_message(t(gid, "clan.ticket_disabled"), ephemeral=True)
            return

        staff_channel_id = ticket_config.get("staff_channel_id")
        if not staff_channel_id:
            await interaction.response.send_message(
                t(gid, "clan.ticket_no_staff_channel"), ephemeral=True)
            return

        staff_channel = interaction.guild.get_channel(staff_channel_id)
        if not staff_channel:
            await interaction.response.send_message(
                t(gid, "clan.ticket_staff_channel_missing"), ephemeral=True)
            return

        name1 = sanitize(session.clan1.get("name", "?"), MAX_CLAN_NAME)
        name2 = sanitize(session.clan2.get("name", "?"), MAX_CLAN_NAME)
        ticket = {
            "id": str(interaction.id),
            "guild_id": gid,
            "user_id": interaction.user.id,
            "channel_id": staff_channel.id,
            "message_id": None,
            "type": problem_type,
            "description": description,
            "session": f"{name1} vs {name2}",
            "taken_by": None,
            "closed": False,
            "created_at": int(time.time()),
        }

        embed = discord.Embed(
            title=t(gid, "clan.ticket_title", type=problem_type)[:256],
            description=t(gid, "clan.ticket_desc", user=interaction.user.mention,
                          user_id=interaction.user.id) + f"\n\n{description[:3500]}",
            color=embeds.BLACK,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name=t(gid, "clan.ticket_field_session"), value=ticket["session"])
        embed.set_footer(text=t(gid, "clan.ticket_footer_waiting"))

        try:
            message = await staff_channel.send(
                embed=embed, view=TicketActionView(gid, ticket["id"]))
        except discord.HTTPException as e:
            log.warning(f"Ticket de ClanWar non envoyé au staff : {e}")
            await interaction.response.send_message(
                t(gid, "clan.ticket_staff_channel_missing"), ephemeral=True)
            return

        ticket["message_id"] = message.id
        save_clan_ticket(gid, ticket)
        await interaction.response.send_message(t(gid, "clan.ticket_sent"), ephemeral=True)


class TicketActionView(discord.ui.View):
    """Répondre et clôturer, dans le salon staff. Les identifiants portent le
    ticket : les boutons répondent encore après un redémarrage."""

    def __init__(self, guild_id: int | None, ticket_id: str):
        super().__init__(timeout=None)
        self.gid = guild_id
        self.ticket_id = str(ticket_id)

        reply = discord.ui.Button(
            label=t(guild_id, "clan.ticket_btn_reply")[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"cyq:clanticket:reply:{self.ticket_id}"[:100],
        )
        reply.callback = self.reply
        self.add_item(reply)

        close = discord.ui.Button(
            label=t(guild_id, "clan.ticket_btn_close")[:80],
            style=discord.ButtonStyle.danger,
            custom_id=f"cyq:clanticket:close:{self.ticket_id}"[:100],
        )
        close.callback = self.close
        self.add_item(close)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        if resources.is_staff(user) or getattr(user.guild_permissions, "manage_guild", False):
            return True
        await interaction.response.send_message(
            t(interaction.guild_id, "common.no_permission"), ephemeral=True)
        return False

    def _open_ticket(self, guild_id: int | None) -> dict | None:
        ticket = get_clan_ticket(guild_id, self.ticket_id)
        return ticket if ticket and not ticket.get("closed") else None

    async def reply(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        ticket = self._open_ticket(gid)
        if ticket is None:
            await interaction.response.send_message(t(gid, "clan.ticket_err_closed"), ephemeral=True)
            return
        await interaction.response.send_modal(
            TicketResponseModal(self.ticket_id, interaction.message))

    async def close(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        ticket = self._open_ticket(gid)
        if ticket is None:
            await interaction.response.send_message(t(gid, "clan.ticket_err_closed"), ephemeral=True)
            return
        update_clan_ticket(gid, self.ticket_id, closed=True)
        self.stop()

        message = interaction.message
        embed = message.embeds[0] if message is not None and message.embeds else discord.Embed(color=embeds.BLACK)
        embed.set_footer(text=t(gid, "clan.ticket_closed"))
        await interaction.response.edit_message(embed=embed, view=None)

        user = interaction.guild.get_member(ticket.get("user_id", 0))
        if user is not None:
            await send_dm(user, embed=embeds.base(
                gid, title=t(gid, "clan.ticket_closed_dm_title"),
                description=t(gid, "clan.ticket_closed_dm_desc"), kind="warning"))


class TicketResponseModal(discord.ui.Modal):
    """La réponse du staff, envoyée en message privé au membre."""

    def __init__(self, ticket_id: str, message: discord.Message | None):
        self.ticket_id = str(ticket_id)
        self.message = message
        gid = message.guild.id if message is not None and message.guild else None
        super().__init__(title=t(gid, "clan.ticket_reply_modal_title")[:45])
        self.response = discord.ui.TextInput(
            label=t(gid, "clan.ticket_reply_label")[:45],
            style=discord.TextStyle.paragraph,
            placeholder=t(gid, "clan.ticket_reply_placeholder")[:100],
            required=True,
            max_length=1000,
        )
        self.add_item(self.response)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        ticket = get_clan_ticket(gid, self.ticket_id)
        if ticket is None or ticket.get("closed"):
            await interaction.response.send_message(t(gid, "clan.ticket_err_closed"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        user = interaction.guild.get_member(ticket.get("user_id", 0))
        if user is None:
            await interaction.followup.send(t(gid, "clan.ticket_dm_closed"), ephemeral=True)
            return

        staff = interaction.user
        # Première réponse : le membre apprend d'abord que son ticket est pris
        # en charge, et qu'il peut répondre dans ce MP.
        if ticket.get("taken_by") is None:
            taken = embeds.base(
                gid, title=t(gid, "clan.ticket_taken_title"),
                description=t(gid, "clan.ticket_taken_desc", staff=staff.mention,
                              icon=custom_emojis.get("communication")),
                kind="brand")
            taken.set_footer(text=t(gid, "clan.ticket_footer_session",
                                    session=ticket.get("session", "?")))
            if not await send_dm(user, embed=taken):
                await interaction.followup.send(t(gid, "clan.ticket_dm_closed"), ephemeral=True)
                return
            update_clan_ticket(gid, self.ticket_id, taken_by=staff.id)

        text = t(gid, "clan.ticket_reply_dm", staff=staff.mention, message=self.response.value)
        if not await send_dm(user, text[:2000], allowed_mentions=discord.AllowedMentions.none()):
            await interaction.followup.send(t(gid, "clan.ticket_dm_closed"), ephemeral=True)
            return

        # Le salon staff garde la trace : sans ça, personne d'autre ne sait
        # ce qui a été répondu au membre.
        if self.message is not None:
            embed = self.message.embeds[0] if self.message.embeds else None
            if embed is not None:
                embed.set_footer(text=t(gid, "clan.ticket_taken_by", staff=staff.display_name))
                try:
                    await self.message.edit(embed=embed)
                except discord.HTTPException:
                    pass
            echo = discord.Embed(
                title=t(gid, "clan.ticket_staff_echo_title", staff=staff.display_name)[:256],
                description=self.response.value[:4000],
                color=embeds.BLACK,
                timestamp=discord.utils.utcnow(),
            )
            try:
                await self.message.channel.send(embed=echo)
            except discord.HTTPException:
                pass

        await interaction.followup.send(t(gid, "clan.ticket_reply_sent"), ephemeral=True)
