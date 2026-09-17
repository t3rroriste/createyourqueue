"""
Tickets du ClanWar
==================
Le bouton « Problème » d'un ClanWar ouvre un ticket vers le salon staff
choisi dans /option. Le staff y répond ou le clôture ; la réponse part en
message privé au membre.

Séparé de cogs/clan.py, qui dépassait 2 800 lignes. Ce n'est pas un cog : pas
de setup(), pas d'entrée dans config.py ; cogs/clan_war.py l'importe.
"""

from __future__ import annotations

import discord
import embeds

from guild_settings import MAX_CLAN_NAME, get_ticket_config
from i18n import t
from text_safety import sanitize

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cogs.clan_war import ClanWarSession


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
        problem_type = self.problem_type.value
        description = self.description.value
        
        # Récupérer la configuration du ticket
        ticket_config = get_ticket_config(gid)
        
        if not ticket_config or not ticket_config.get("enabled", False):
            await interaction.response.send_message(
                t(gid, "clan.ticket_disabled"),
                ephemeral=True
            )
            return
        
        staff_channel_id = ticket_config.get("staff_channel_id")
        if not staff_channel_id:
            await interaction.response.send_message(
                t(gid, "clan.ticket_no_staff_channel"),
                ephemeral=True
            )
            return
        
        staff_channel = interaction.guild.get_channel(staff_channel_id)
        if not staff_channel:
            await interaction.response.send_message(
                t(gid, "clan.ticket_staff_channel_missing"),
                ephemeral=True
            )
            return
        
        # Créer l'embed du ticket
        name1 = sanitize(session.clan1.get("name", "?"), MAX_CLAN_NAME)
        name2 = sanitize(session.clan2.get("name", "?"), MAX_CLAN_NAME)
        
        embed = discord.Embed(
            title=t(gid, "clan.ticket_title", type=problem_type)[:256],
            description=description,
            color=embeds.BLACK
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name=t(gid, "clan.ticket_field_user"), value=f"{interaction.user.mention} ({interaction.user.name})")
        embed.add_field(name=t(gid, "clan.ticket_field_session"), value=f"{name1} vs {name2}")
        embed.add_field(name=t(gid, "clan.ticket_field_id"), value=f"`{interaction.id}`")
        embed.set_footer(text=t(gid, "clan.ticket_footer_waiting"))
        embed.timestamp = discord.utils.utcnow()
        
        # Envoyer le ticket avec les boutons
        await staff_channel.send(embed=embed, view=TicketActionView(interaction.user, session))
        
        await interaction.response.send_message(
            t(gid, "clan.ticket_sent"),
            ephemeral=True
        )


class TicketActionView(discord.ui.View):
    """View pour gérer les tickets du staff."""
    
    def __init__(self, user: discord.Member, session: "ClanWarSession"):
        super().__init__(timeout=None)
        self.user = user
        self.session = session
        self.claimed = False
        self.respond.label = t(session.guild_id, "clan.ticket_btn_reply")
        self.close.label = t(session.guild_id, "clan.ticket_btn_close")
    
    @discord.ui.button(label="Répondre", style=discord.ButtonStyle.primary)
    async def respond(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Ouvre le modal de réponse."""
        await interaction.response.send_modal(TicketResponseModal(self.user, self.session, self))
    
    @discord.ui.button(label="Clôturer", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Clôture le ticket."""
        await interaction.response.edit_message(
            embed=interaction.message.embeds[0].set_footer(text=t(interaction.guild_id, "clan.ticket_closed")),
            view=None
        )


class TicketResponseModal(discord.ui.Modal):
    """Modal pour répondre à un ticket."""

    def __init__(self, user: discord.Member, session: "ClanWarSession", view: "TicketActionView"):
        gid = session.guild_id
        super().__init__(title=t(gid, "clan.ticket_reply_modal_title")[:45])
        self.user = user
        self.session = session
        self.view = view
        self.response = discord.ui.TextInput(
            label=t(gid, "clan.ticket_reply_label")[:45],
            style=discord.TextStyle.paragraph,
            placeholder=t(gid, "clan.ticket_reply_placeholder")[:100],
            required=True,
            max_length=1000,
        )
        self.add_item(self.response)
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Envoie la réponse à l'utilisateur."""
        response_text = self.response.value
        
        # Marquer comme claimé
        self.view.claimed = True
        
        # Envoyer un message ephemeral à l'utilisateur
        try:
            # Créer un channel ou envoyer un DM
            dm_channel = await self.user.create_dm()
            
            embed = discord.Embed(
                title=t(self.session.guild_id, "clan.ticket_reply_title"),
                description=response_text,
                color=embeds.BLACK
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(name=t(self.session.guild_id, "clan.ticket_field_staff"), value=f"{interaction.user.mention} ({interaction.user.name})")
            embed.set_footer(text=t(self.session.guild_id, "clan.ticket_footer_session", clan1=self.session.clan1.get("name", "?"), clan2=self.session.clan2.get("name", "?")))
            
            await dm_channel.send(embed=embed)
            
            # Mettre à jour le ticket dans le channel staff
            await interaction.response.edit_message(
                embed=interaction.message.embeds[0].set_footer(text=t(self.session.guild_id, "clan.ticket_answered_by", staff=interaction.user.name)),
                view=None
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                t(self.session.guild_id, "clan.ticket_dm_closed"),
                ephemeral=True
            )
