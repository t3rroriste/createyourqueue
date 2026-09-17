"""
Cog : Clans
===========
Équipes permanentes, par-dessus les queues.

Une queue rassemble des joueurs pour une soirée ; un clan les garde. Il a un
nom, un logo, éventuellement son propre serveur Discord, et un classement
qui agrège les victoires de ses membres.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

import custom_emojis
import embeds
import resources
from guild_settings import (
    MAX_CLAN_NAME, get_clans, clan_of, create_clan, clan_named, add_clan_member,
    remove_clan_member, get_clan, get_features, set_clan_fields,
    clan_by_channel, transfer_clan_leader, get_clan_requests, add_clan_request,
    remove_clan_request, get_clan_war_session, get_clan_announcement_count,
    reset_clan_announcement, reset_all_clan_announcements,
)
from i18n import t
from text_safety import sanitize

from cogs.clan_war import ClanWarSession, _slug
from cogs.logs import send_log

log = logging.getLogger("bot.clan")

# Une image de logo doit être une URL http(s) qui ressemble à une image :
# Discord rejette l'embed entier si le lien ne répond pas une image, et on
# perdrait la fiche au lieu du seul logo.
IMAGE_URL = re.compile(r"^https://\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?$", re.IGNORECASE)
INVITE_URL = re.compile(r"^https://(?:discord\.gg|discord\.com/invite)/\S+$", re.IGNORECASE)

# Noir réel. 0x000000 signifie « pas de couleur » pour Discord : un rôle réglé
# sur zéro s'affiche en gris par défaut, pas en noir.
CLAN_ROLE_COLOUR = discord.Colour(0x010101)

# Formats de ClanWar proposés. Au-delà de 5 contre 5, la liste déborde et les
# clans concernés sont assez rares pour s'organiser à la main.
MAX_WAR_SIZE = 5

# Boutons des deux menus du salon de clan : un message du bot qui en porte un
# est un ancien menu, à supprimer avant d'en republier un neuf.
CLAN_MENU_IDS = {"cyq:clan:manage", "cyq:clan:req", "cyq:clan:hist", "cyq:clan:inv",
                 "cyq:clan:war", "cyq:clan:dnd", "cyq:clan:ready"}


# ----------------------------------------------------------------------
# Statistiques
# ----------------------------------------------------------------------
def clan_stats(bot: commands.Bot, guild_id: int, clan: dict) -> tuple[int, int, float]:
    """Victoires, défaites et ratio du clan."""
    cog = bot.get_cog("Classement")
    stats = getattr(cog, "player_stats", {}) if cog is not None else {}
    wins = losses = 0
    for uid in clan.get("members", []):
        entry = stats.get(uid) or {}
        wins += int(entry.get("wins", 0))
        losses += int(entry.get("losses", 0))
    # Sans défaite, le ratio vaut le nombre de victoires : diviser par zéro
    # n'a pas de sens, et « ∞ » ne se compare pas.
    ratio = wins / losses if losses else float(wins)
    return wins, losses, ratio


def sorted_clans(bot: commands.Bot, guild_id: int) -> list[tuple[dict, int, int, float]]:
    """Clans triés par victoires, puis par ratio à égalité."""
    rows = [(clan, *clan_stats(bot, guild_id, clan))
            for clan in get_clans(guild_id).values()]
    rows.sort(key=lambda r: (r[1], r[3]), reverse=True)
    return rows


# ----------------------------------------------------------------------
# Fiche de clan
# ----------------------------------------------------------------------
def clan_embed(bot: commands.Bot, guild_id: int, clan: dict, *, invite: bool = False) -> discord.Embed:
    """La fiche : nom, logo, ratio, effectif, membres, serveur du clan."""
    wins, losses, ratio = clan_stats(bot, guild_id, clan)
    members = clan.get("members", [])
    leader_id = clan.get("leader_id")

    embed = embeds.base(
        guild_id,
        title=t(guild_id, "clan.card_title", name=sanitize(clan.get("name", "?"), MAX_CLAN_NAME)),
        description=t(guild_id, "clan.invite_desc") if invite else None,
        kind="brand",
    )
    if clan.get("icon_url"):
        embed.set_thumbnail(url=clan["icon_url"])

    embed.add_field(name=t(guild_id, "clan.field_record"),
                    value=t(guild_id, "clan.record", wins=wins, losses=losses, kd=f"{ratio:.2f}"),
                    inline=True)
    embed.add_field(name=t(guild_id, "clan.field_size"),
                    value=f"**{len(members)}**", inline=True)

    # Le chef en tête, puis les autres : on voit tout de suite à qui on a
    # affaire.
    names = [t(guild_id, "clan.member_leader", player=f"<@{leader_id}>")]
    names += [f"<@{uid}>" for uid in members if uid != leader_id]
    shown, extra = names[:30], max(0, len(names) - 30)
    roster = ", ".join(shown) + (t(guild_id, "clan.member_more", count=extra) if extra else "")
    embed.add_field(name=t(guild_id, "clan.field_members"), value=roster[:1024], inline=False)

    if clan.get("invite_url"):
        embed.add_field(name=t(guild_id, "clan.field_server"),
                        value=clan["invite_url"], inline=False)
    return embed


# ----------------------------------------------------------------------
# Création
# ----------------------------------------------------------------------
class CreateModal(discord.ui.Modal):
    def __init__(self, cog: "Clan", guild_id: int):
        super().__init__(title=t(guild_id, "clan.create_modal")[:45])
        self.cog = cog
        self.guild_id = guild_id
        self.name = discord.ui.TextInput(
            label=t(guild_id, "clan.field_name")[:45],
            max_length=MAX_CLAN_NAME,
        )
        self.icon = discord.ui.TextInput(
            label=t(guild_id, "clan.field_icon")[:45],
            placeholder="https://.../logo.png",
            required=False, max_length=300,
        )
        self.invite = discord.ui.TextInput(
            label=t(guild_id, "clan.field_invite")[:45],
            placeholder="https://discord.gg/…",
            required=False, max_length=100,
        )
        for item in (self.name, self.icon, self.invite):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = self.guild_id
        name = sanitize(self.name.value.strip(), MAX_CLAN_NAME)
        icon = self.icon.value.strip()
        invite = self.invite.value.strip()

        if not name:
            await interaction.response.send_message(t(gid, "clan.err_name"), ephemeral=True)
            return
        # On refuse un lien invalide plutôt que de l'enregistrer : un logo
        # cassé fait échouer l'affichage de toute la fiche, pas juste l'image.
        if icon and not IMAGE_URL.match(icon):
            await interaction.response.send_message(t(gid, "clan.err_icon"), ephemeral=True)
            return
        if invite and not INVITE_URL.match(invite):
            await interaction.response.send_message(t(gid, "clan.err_invite"), ephemeral=True)
            return

        try:
            clan = create_clan(gid, name=name, leader_id=interaction.user.id,
                               icon_url=icon, invite_url=invite)
        except ValueError as e:
            key = {"name_taken": "clan.err_taken", "already_in_clan": "clan.err_already",
                   "full": "clan.err_full"}.get(str(e), "clan.err_name")
            await interaction.response.send_message(t(gid, key), ephemeral=True)
            return
        send_log(interaction.client, gid, "clan", t(gid, "logs.clan_created"), user=interaction.user,
                 fields=[(t(gid, "logs.f_clan"), name),
                         (t(gid, "logs.f_leader"), interaction.user.mention)])

        # L'ouverture du salon et la création du rôle demandent plusieurs
        # appels à Discord : on rend la main tout de suite pour ne pas laisser
        # expirer l'interaction.
        await interaction.response.defer(ephemeral=True)

        notes = await self.cog.apply_leader_perks(interaction.user, clan)
        notes += await self.cog.open_clan_space(interaction.guild, clan)

        await interaction.followup.send(
            content="\n".join(notes) or None,
            embed=clan_embed(interaction.client, gid, clan),
            view=ClanView(self.cog, gid, clan, interaction.user.id),
            ephemeral=True,
        )
        await self.cog.refresh_leaderboard(interaction.guild)


class CreateView(discord.ui.View):
    def __init__(self, cog: "Clan", guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.create.label = t(guild_id, "clan.btn_create")

    @discord.ui.button(label="Créer", style=discord.ButtonStyle.success, emoji="🛡️")
    async def create(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(CreateModal(self.cog, self.guild_id))


# ----------------------------------------------------------------------
# Fiche + actions
# ----------------------------------------------------------------------
class ClanView(discord.ui.View):
    """Boutons de la fiche. Ce qu'on voit dépend de qui regarde : seul le
    chef peut inviter et dissoudre."""

    def __init__(self, cog: "Clan", guild_id: int, clan: dict, viewer_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.clan = clan
        self.viewer_id = viewer_id
        is_leader = viewer_id == clan.get("leader_id")

        self.invite_member.label = t(guild_id, "clan.btn_invite")
        self.leave.label = t(guild_id, "clan.btn_leave") if not is_leader else t(guild_id, "clan.btn_disband")
        self.invite_member.disabled = not is_leader

        if is_leader:
            select = discord.ui.UserSelect(
                placeholder=t(guild_id, "clan.invite_pick")[:150], row=0,
            )
            select.callback = self._invite_from_select(select)
            self.add_item(select)

    def _invite_from_select(self, select: discord.ui.UserSelect):
        async def callback(interaction: discord.Interaction) -> None:
            target = select.values[0]
            member = interaction.guild.get_member(target.id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message(
                    t(self.guild_id, "clan.err_not_member"), ephemeral=True)
                return
            await self.cog.send_invite(interaction, self.clan, member)
        return callback

    @discord.ui.button(label="Inviter", style=discord.ButtonStyle.primary, emoji="✉️", row=1)
    async def invite_member(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(t(self.guild_id, "clan.invite_hint"), ephemeral=True)

    @discord.ui.button(label="Quitter", style=discord.ButtonStyle.danger, emoji="🚪", row=1)
    async def leave(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        gid = self.guild_id
        clan = get_clan(gid, self.clan["id"])
        if clan is None:
            await interaction.response.send_message(t(gid, "clan.err_gone"), ephemeral=True)
            return
        was_leader = interaction.user.id == clan.get("leader_id")
        # La fiche est lue avant la suppression : après, le clan n'existe plus
        # et on ne saurait plus quel salon ni quel rôle effacer.
        snapshot = dict(clan)
        remove_clan_member(gid, clan["id"], interaction.user.id)
        send_log(interaction.client, gid, "clan",
                 t(gid, "logs.clan_disbanded" if was_leader else "logs.clan_left"),
                 user=interaction.user,
                 fields=[(t(gid, "logs.f_clan"), sanitize(clan.get("name", "?"), MAX_CLAN_NAME))])
        await self.cog.clear_perks(interaction.user, clan)
        await interaction.response.edit_message(
            content=t(gid, "clan.disbanded" if was_leader else "clan.left",
                      name=sanitize(clan.get("name", "?"), MAX_CLAN_NAME)),
            embed=None, view=None,
        )
        if was_leader:
            await self.cog.close_clan_space(interaction.guild, snapshot)
        else:
            await self.cog.set_clan_role(interaction.user, snapshot, add=False)
            await self.cog.refresh_clan_space(interaction.guild, get_clan(gid, snapshot["id"]))
        await self.cog.refresh_leaderboard(interaction.guild)


class InviteView(discord.ui.View):
    """Les deux boutons de l'invitation, en message privé."""

    def __init__(self, cog: "Clan", guild_id: int, clan_id: str, invitee_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.clan_id = clan_id
        self.invitee_id = invitee_id
        self.accept.label = t(guild_id, "clan.btn_accept")
        self.decline.label = t(guild_id, "clan.btn_decline")
        self.accept.emoji = custom_emojis.get("checkmark")
        self.decline.emoji = custom_emojis.get("cross")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invitee_id:
            return True
        await interaction.response.send_message(
            t(self.guild_id, "clan.err_not_you"), ephemeral=True)
        return False

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, emoji="✅",
                       custom_id="cyq:clan:accept")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        gid = self.guild_id
        clan = get_clan(gid, self.clan_id)
        if clan is None:
            await interaction.response.edit_message(
                content=t(gid, "clan.err_gone"), embed=None, view=None)
            return
        if not add_clan_member(gid, self.clan_id, interaction.user.id):
            await interaction.response.edit_message(
                content=t(gid, "clan.err_already"), embed=None, view=None)
            return
        name = sanitize(clan.get("name", "?"), MAX_CLAN_NAME)
        send_log(interaction.client, gid, "clan", t(gid, "logs.clan_joined"), user=interaction.user,
                 fields=[(t(gid, "logs.f_clan"), name)])
        await interaction.response.edit_message(
            content=t(gid, "clan.joined", name=name),
            embed=clan_embed(interaction.client, gid, clan), view=None,
        )
        guild = interaction.client.get_guild(gid)
        await self.cog.on_roster_change(guild, clan, interaction.user.id, joined=True)
        await self.cog.refresh_leaderboard(guild)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.secondary, emoji="✖️",
                       custom_id="cyq:clan:decline")
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            content=t(self.guild_id, "clan.declined"), embed=None, view=None)
        clan = get_clan(self.guild_id, self.clan_id)
        send_log(interaction.client, self.guild_id, "clan", t(self.guild_id, "logs.clan_invite_declined"),
                 user=interaction.user,
                 fields=[(t(self.guild_id, "logs.f_clan"),
                          sanitize(clan.get("name", "?"), MAX_CLAN_NAME) if clan else None)])


# ----------------------------------------------------------------------
# Le salon du clan : fiche vivante et boutons
# ----------------------------------------------------------------------
class ClanSpaceView(discord.ui.View):
    """Les quatre boutons de la fiche, dans le salon du clan : Clan Manage,
    Request, History, Invites. Le ClanWar a son propre menu, juste en dessous
    (ClanWarMenuView)."""

    def __init__(self, cog: "Clan"):
        super().__init__(timeout=None)
        self.cog = cog

    async def _context(self, interaction: discord.Interaction) -> dict | None:
        """Le clan de ce salon, si celui qui clique en fait partie."""
        gid = interaction.guild_id
        clan = clan_by_channel(gid, interaction.channel_id) if gid else None
        if clan is None:
            await interaction.response.send_message(t(gid, "clan.err_gone"), ephemeral=True)
            return None
        if interaction.user.id not in clan.get("members", []):
            await interaction.response.send_message(
                t(gid, "clan.err_not_in_clan"), ephemeral=True)
            return None
        return clan

    @discord.ui.button(label="Clan Manage", style=discord.ButtonStyle.primary,
                       emoji="🔧", custom_id="cyq:clan:manage")
    async def manage(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clan = await self._context(interaction)
        if clan is None:
            return
        gid = interaction.guild_id
        # La même fiche que /clan : inviter (chef), quitter ou dissoudre.
        await interaction.response.send_message(
            embed=clan_embed(self.cog.bot, gid, clan),
            view=ClanView(self.cog, gid, clan, interaction.user.id),
            ephemeral=True,
        )

    @discord.ui.button(label="Request", style=discord.ButtonStyle.secondary,
                       emoji="📩", custom_id="cyq:clan:req")
    async def requests(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clan = await self._context(interaction)
        if clan is None:
            return
        await self.cog.show_queue(interaction, clan, "wars")

    @discord.ui.button(label="History", style=discord.ButtonStyle.secondary,
                       emoji="🧾", custom_id="cyq:clan:hist")
    async def history(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clan = await self._context(interaction)
        if clan is None:
            return
        await self.cog.show_history(interaction, clan)

    @discord.ui.button(label="Invites", style=discord.ButtonStyle.secondary,
                       emoji="📧", custom_id="cyq:clan:inv")
    async def invites(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clan = await self._context(interaction)
        if clan is None:
            return
        if interaction.user.id != clan.get("leader_id"):
            await interaction.response.send_message(
                t(interaction.guild_id, "clan.err_leader_only"), ephemeral=True)
            return
        await self.cog.show_queue(interaction, clan, "joins")


def war_menu_embed(guild_id: int, clan: dict) -> discord.Embed:
    """Le menu ClanWar, sous la fiche : lancer un ClanWar, et l'état du
    clan — l'état retenu en gras, l'autre barré."""
    ready = clan.get("war_ready", True)
    return embeds.base(
        guild_id,
        title=t(guild_id, "clan.menu_title"),
        description=(
            t(guild_id, "clan.menu_start") + "\n"
            + embeds.pick_line(guild_id, "clan.menu_dnd", "clan.menu_ready", not ready)
            + "\n\n" + t(guild_id, "clan.menu_hint")
        ),
        kind="error",
    )


class ClanWarMenuView(discord.ui.View):
    """Les boutons du menu ClanWar. Persistante, comme ClanSpaceView : le
    clan se déduit du salon. Le bouton de l'état déjà actif est grisé."""

    # Même contrôle que la fiche : le clan de ce salon, et un de ses membres.
    _context = ClanSpaceView._context

    def __init__(self, cog: "Clan", guild_id: int | None = None, is_ready: bool = True):
        super().__init__(timeout=None)
        self.cog = cog
        if guild_id is not None:
            self.dnd.label = t(guild_id, "clan.btn_dnd")[:80]
            self.ready.label = t(guild_id, "clan.btn_ready")[:80]
            self.dnd.disabled = not is_ready
            self.ready.disabled = is_ready

    @discord.ui.button(label="ClanWar", style=discord.ButtonStyle.danger,
                       emoji="⚔️", custom_id="cyq:clan:war")
    async def war(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clan = await self._context(interaction)
        if clan is None:
            return
        gid = interaction.guild_id
        if not clan.get("war_ready", True):
            await interaction.response.send_message(t(gid, "clan.war_err_self_dnd"), ephemeral=True)
            return
        others = [c for c in get_clans(gid).values() if c["id"] != clan["id"]]
        # Un clan en Ne pas déranger ne se défie pas : il n'est pas proposé.
        rivals = [c for c in others if c.get("war_ready", True)]
        if not rivals:
            key = "clan.war_no_ready_rival" if others else "clan.war_no_rival"
            await interaction.response.send_message(t(gid, key), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embeds.base(gid, title=t(gid, "clan.war_title"),
                              description=t(gid, "clan.war_pick_desc"), kind="error"),
            view=WarSetupView(self.cog, gid, clan, rivals),
            ephemeral=True,
        )

    @discord.ui.button(label="Ne pas déranger", style=discord.ButtonStyle.secondary,
                       emoji="⭕", custom_id="cyq:clan:dnd")
    async def dnd(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._set_ready(interaction, False)

    @discord.ui.button(label="Prêt à jouer", style=discord.ButtonStyle.success,
                       emoji="✔️", custom_id="cyq:clan:ready")
    async def ready(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._set_ready(interaction, True)

    async def _set_ready(self, interaction: discord.Interaction, ready: bool) -> None:
        clan = await self._context(interaction)
        if clan is None:
            return
        gid = interaction.guild_id
        if interaction.user.id != clan.get("leader_id"):
            await interaction.response.send_message(t(gid, "clan.err_leader_only"), ephemeral=True)
            return
        clan = set_clan_fields(gid, clan["id"], war_ready=ready) or clan
        await interaction.response.edit_message(
            embed=war_menu_embed(gid, clan), view=ClanWarMenuView(self.cog, gid, ready))


class WarSetupView(discord.ui.View):
    """Choisir l'adversaire, puis le format. Deux menus dans le même message
    éphémère : le second n'apparaît qu'une fois le premier répondu, pour ne
    pas proposer un 5 contre 5 avant de savoir qui est en face."""

    def __init__(self, cog: "Clan", guild_id: int, clan: dict, rivals: list[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.gid = guild_id
        self.clan = clan
        self.target: dict | None = None

        select = discord.ui.Select(
            placeholder=t(guild_id, "clan.war_pick_clan")[:150],
            options=[
                discord.SelectOption(
                    label=sanitize(c.get("name", "?"), MAX_CLAN_NAME)[:100],
                    description=t(guild_id, "clan.war_size", count=len(c.get("members", [])))[:100],
                    value=c["id"],
                )
                # Discord n'accepte que 25 choix : les clans les plus fournis
                # d'abord, ce sont ceux avec qui un duel est jouable.
                for c in sorted(rivals, key=lambda c: -len(c.get("members", [])))[:25]
            ],
            row=0,
        )
        select.callback = self._pick_target(select)
        self.add_item(select)

    def _pick_target(self, select: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            target = get_clan(self.gid, select.values[0])
            if target is None:
                await interaction.response.send_message(
                    t(self.gid, "clan.err_gone"), ephemeral=True)
                return
            self.target = target
            self.clear_items()
            self.add_item(select)
            # Le format est borné par le plus petit des deux effectifs :
            # proposer un 5 contre 5 à un clan de deux n'a aucun sens.
            cap = max(1, min(len(self.clan.get("members", [])),
                             len(target.get("members", [])), MAX_WAR_SIZE))
            sizes = discord.ui.Select(
                placeholder=t(self.gid, "clan.war_pick_size")[:150],
                options=[discord.SelectOption(label=f"{n} vs {n}", value=str(n))
                         for n in range(1, cap + 1)],
                row=1,
            )
            sizes.callback = self._send(sizes)
            self.add_item(sizes)
            await interaction.response.edit_message(
                embed=embeds.base(
                    self.gid, title=t(self.gid, "clan.war_title"),
                    description=t(self.gid, "clan.war_size_desc",
                                  name=sanitize(target.get("name", "?"), MAX_CLAN_NAME)),
                    kind="error"),
                view=self,
            )
        return callback

    def _send(self, select: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            size = int(select.values[0])
            await self.cog.send_war_request(interaction, self.clan, self.target, size)
        return callback


class WarAnswerView(discord.ui.View):
    """Accepter ou refuser un défi, dans le salon du clan défié."""

    def __init__(self, cog: "Clan", guild_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        # Les libellés vivent dans le message, pas dans la vue : celle qu'on
        # ré-enregistre au démarrage n'a pas de serveur et garde les libellés
        # par défaut, que personne ne verra jamais.
        if guild_id is not None:
            self.accept.label = t(guild_id, "clan.btn_accept")
            self.decline.label = t(guild_id, "clan.btn_decline")
        self.accept.emoji = custom_emojis.get("checkmark")
        self.decline.emoji = custom_emojis.get("cross")

    async def _resolve(self, interaction: discord.Interaction) -> tuple[dict, dict] | None:
        gid = interaction.guild_id
        clan = clan_by_channel(gid, interaction.channel_id) if gid else None
        if clan is None:
            await interaction.response.send_message(t(gid, "clan.err_gone"), ephemeral=True)
            return None
        if interaction.user.id not in clan.get("members", []):
            await interaction.response.send_message(
                t(gid, "clan.err_not_in_clan"), ephemeral=True)
            return None
        for request in get_clan_requests(gid, clan["id"], "wars"):
            if request.get("message_id") == interaction.message.id:
                return clan, request
        await interaction.response.send_message(t(gid, "clan.war_gone"), ephemeral=True)
        return None

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, emoji="✅",
                       custom_id="cyq:clan:war_ok")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        found = await self._resolve(interaction)
        if found is not None:
            await self.cog.answer_war(interaction, *found, accepted=True)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.secondary, emoji="✖️",
                       custom_id="cyq:clan:war_no")
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        found = await self._resolve(interaction)
        if found is not None:
            await self.cog.answer_war(interaction, *found, accepted=False)


class QueueView(discord.ui.View):
    """Les demandes en attente : on en choisit une, puis on répond."""

    def __init__(self, cog: "Clan", guild: discord.Guild, clan: dict, kind: str,
                 entries: list[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.gid = guild.id
        self.clan = clan
        self.kind = kind
        self.entries = entries
        self.picked: str | None = None

        options = []
        for entry in entries[:25]:
            if kind == "wars":
                rival = get_clan(self.gid, entry.get("from_clan"))
                label = sanitize(rival.get("name", "?"), MAX_CLAN_NAME) if rival else "?"
                desc = f"{entry.get('size', 0)} vs {entry.get('size', 0)}"
                value = str(entry.get("from_clan"))
            else:
                # Un libellé de menu n'interprète pas les mentions : il faut
                # le vrai pseudo, pas « <@123> ».
                uid = entry.get("user_id")
                member = guild.get_member(uid)
                label = member.display_name if member is not None else str(uid)
                desc = ""
                value = str(uid)
            options.append(discord.SelectOption(label=label[:100], description=desc[:100],
                                                value=value))

        select = discord.ui.Select(
            placeholder=t(self.gid, "clan.queue_pick")[:150], options=options, row=0)
        select.callback = self._pick(select)
        self.add_item(select)
        self.accept.label = t(self.gid, "clan.btn_accept")
        self.decline.label = t(self.gid, "clan.btn_decline")
        self.accept.emoji = custom_emojis.get("checkmark")
        self.decline.emoji = custom_emojis.get("cross")
        self.accept.disabled = True
        self.decline.disabled = True

    def _pick(self, select: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            self.picked = select.values[0]
            self.accept.disabled = False
            self.decline.disabled = False
            await interaction.response.edit_message(view=self)
        return callback

    async def _answer(self, interaction: discord.Interaction, accepted: bool) -> None:
        if self.picked is None:
            await interaction.response.send_message(
                t(self.gid, "clan.queue_none_picked"), ephemeral=True)
            return
        if self.kind == "wars":
            request = None
            for entry in get_clan_requests(self.gid, self.clan["id"], "wars"):
                if str(entry.get("from_clan")) == self.picked:
                    request = entry
                    break
            if request is None:
                await interaction.response.send_message(t(self.gid, "clan.war_gone"), ephemeral=True)
                return
            await self.cog.answer_war(interaction, self.clan, request, accepted=accepted)
        else:
            await self.cog.answer_join(interaction, self.clan, int(self.picked), accepted=accepted)

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, emoji="✅", row=1)
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._answer(interaction, True)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.secondary, emoji="✖️", row=1)
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._answer(interaction, False)


# ----------------------------------------------------------------------
# Cog
# ----------------------------------------------------------------------
class Clan(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_war_sessions: dict[str, ClanWarSession] = {}  # guild_id -> ClanWarSession

    async def cog_load(self) -> None:
        # Les boutons publiés dans les salons de clan doivent répondre après
        # un redémarrage : sans ces deux lignes, un clic reste sans effet.
        self.bot.add_view(ClanSpaceView(self))
        self.bot.add_view(ClanWarMenuView(self))
        self.bot.add_view(WarAnswerView(self))
        
        # Restaurer les sessions de ClanWar actives
        await self._restore_war_sessions()
        
        # Lancer la tâche de vérification des channels de liaison
        self._liaison_check_task = self.bot.loop.create_task(self._check_clan_liaison_channels())

        # Les deux menus de chaque salon de clan, republiés une fois connecté
        self._menus_task = asyncio.create_task(self._repost_clan_menus())

    async def cog_unload(self) -> None:
        """Déchargement du cog : annule la tâche de fond et réinitialise les channels."""
        if hasattr(self, "_liaison_check_task"):
            self._liaison_check_task.cancel()
        if hasattr(self, "_menus_task"):
            self._menus_task.cancel()
        
        # Réinitialiser tous les channels de liaison quand le bot se déconnecte
        for guild in self.bot.guilds:
            try:
                clans = get_clans(guild.id)
                for clan in clans.values():
                    await self._reset_clan_liaison_channel(guild, clan)
            except Exception as e:
                log.error(f"Erreur lors de la réinitialisation des channels pour {guild.name}: {e}")
        
        # Réinitialiser tous les compteurs d'annonces
        for guild in self.bot.guilds:
            try:
                reset_all_clan_announcements(guild.id)
            except Exception as e:
                log.error(f"Erreur lors de la réinitialisation des compteurs pour {guild.name}: {e}")
    
    async def _restore_war_sessions(self) -> None:
        """Restaure les sessions de ClanWar actives après un redémarrage."""
        for guild in self.bot.guilds:
            try:
                session_data = get_clan_war_session(guild.id)
                if session_data and not session_data.get("ended", False):
                    session = ClanWarSession.from_dict(self, guild, session_data)
                    if session and session.started and not session.ended:
                        # Vérifier si le temps de préparation est déjà écoulé
                        if session.preparation_end_time and time.time() >= session.preparation_end_time:
                            # Le temps est écoulé, vérifier la présence des leaders
                            await session._check_leader_presence_and_start()
                        else:
                            # Recréer le timer avec le temps restant
                            remaining_time = session.preparation_end_time - time.time()
                            if remaining_time > 0:
                                session.timer_task = asyncio.create_task(
                                    session._preparation_timer_with_update()
                                )
                                self.active_war_sessions[str(guild.id)] = session
                                log.info(f"[{guild.name}] Session ClanWar restaurée: {session.clan1.get('name')} vs {session.clan2.get('name')}")
            except Exception as e:
                log.error(f"Erreur lors de la restauration de la session ClanWar pour {guild.name}: {e}")
    
    async def _check_clan_liaison_channels(self):
        """Tâche de fond qui vérifie toutes les 30 min si les channels doivent être réinitialisés."""
        
        while True:
            try:
                await asyncio.sleep(1800)  # 30 minutes = 1800 secondes
                log.info("Vérification périodique des channels de liaison (toutes les 30 min)")
                
                for guild in self.bot.guilds:
                    try:
                        clans = get_clans(guild.id)
                        for clan in clans.values():
                            # Réinitialiser SEULEMENT si plus de 3 annonces
                            announcement_count = get_clan_announcement_count(guild.id, clan["id"])
                            clan_name = clan.get("name", "?")
                            log.info(f"[{guild.name}] Clan {clan_name}: {announcement_count} annonces")
                            
                            if announcement_count >= 3:
                                log.info(f"[{guild.name}] Réinitialisation du channel de liaison pour {clan_name} ({announcement_count} annonces)")
                                await self._reset_clan_liaison_channel(guild, clan)
                            else:
                                log.info(f"[{guild.name}] Pas de réinitialisation pour {clan_name} (moins de 3 annonces)")
                    except Exception as e:
                        log.error(f"Erreur lors de la vérification des channels de liaison pour {guild.name}: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Erreur dans la tâche de vérification des channels de liaison: {e}")
                await asyncio.sleep(60)  # Attendre 1 minute avant de réessayer

    # -- Rôle et pseudo du chef -----------------------------------------
    async def apply_leader_perks(self, member: discord.Member, clan: dict) -> list[str]:
        """Rôle de chef et tag de clan dans le pseudo."""
        gid = member.guild.id
        notes: list[str] = []
        name = sanitize(clan.get("name", "?"), MAX_CLAN_NAME)

        role = resources.get_role(member.guild, "role_clan_leader")
        if role is None:
            notes.append(t(gid, "clan.warn_no_role"))
        else:
            try:
                await member.add_roles(role, reason=f"Chef du clan {name}")
            except discord.Forbidden:
                notes.append(t(gid, "clan.warn_role_perm", role=role.name))
            except discord.HTTPException:
                pass

        try:
            await member.edit(nick=f"({name}) {member.name}"[:32],
                              reason=f"Tag du clan {name}")
        except discord.Forbidden:
            notes.append(t(gid, "clan.warn_nick"))
        except discord.HTTPException:
            pass
        return notes

    async def clear_perks(self, member: discord.Member, clan: dict) -> None:
        """Retire le rôle et le tag quand on quitte ou dissout."""
        role = resources.get_role(member.guild, "role_clan_leader")
        if role is not None and role in getattr(member, "roles", []):
            try:
                await member.remove_roles(role, reason="Clan quitté")
            except discord.HTTPException:
                pass
        tag = f"({sanitize(clan.get('name', '?'), MAX_CLAN_NAME)}) "
        if (member.nick or "").startswith(tag):
            try:
                await member.edit(nick=member.nick[len(tag):] or None, reason="Clan quitté")
            except discord.HTTPException:
                pass

    # -- Le salon et le rôle du clan ------------------------------------
    def enabled(self, guild_id: int) -> bool:
        return bool(get_features(guild_id)["clans"])

    def clan_role(self, guild: discord.Guild, clan: dict) -> discord.Role | None:
        role_id = clan.get("role_id")
        return guild.get_role(role_id) if role_id else None

    def clan_channel(self, guild: discord.Guild, clan: dict) -> discord.TextChannel | None:
        channel_id = clan.get("channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def set_clan_role(self, member: discord.Member, clan: dict, *, add: bool) -> None:
        """Le rôle `Clan - Nom` suit l'effectif, sans jamais faire échouer
        l'action principale : entrer dans un clan doit marcher même si le bot
        n'a pas la main sur les rôles."""
        role = self.clan_role(member.guild, clan)
        if role is None:
            return
        try:
            if add:
                await member.add_roles(role, reason="Membre du clan")
            else:
                await member.remove_roles(role, reason="Quitte le clan")
        except discord.HTTPException:
            pass

    async def open_clan_space(self, guild: discord.Guild | None, clan: dict) -> list[str]:
        """Crée le rôle du clan et son salon privé, puis y publie la fiche."""
        if guild is None or not self.enabled(guild.id):
            return []
        gid = guild.id
        name = sanitize(clan.get("name", "?"), MAX_CLAN_NAME)
        notes: list[str] = []

        category = resources.get_category(guild, "category_clan")
        if category is None:
            return [t(gid, "clan.warn_no_category")]

        role = None
        try:
            role = await guild.create_role(
                name=t(gid, "clan.role_name", name=name)[:100],
                colour=CLAN_ROLE_COLOUR,
                reason=f"Clan {name}",
            )
        except discord.Forbidden:
            notes.append(t(gid, "clan.warn_role_create"))
        except discord.HTTPException as e:
            log.warning(f"[{guild.name}] Rôle de clan refusé : {e}")
            notes.append(t(gid, "clan.warn_role_create"))

        # Donner le rôle est une seconde opération : elle peut échouer alors
        # que le rôle existe bel et bien, et le salon doit quand même s'ouvrir
        # avec les bonnes permissions.
        leader = guild.get_member(clan["leader_id"])
        if role is not None and leader is not None:
            try:
                await leader.add_roles(role, reason=f"Chef du clan {name}")
            except discord.HTTPException:
                pass

        # Privé : le clan et le staff. Le reste du serveur ne voit rien —
        # c'est un salon de liaison, pas une vitrine.
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_messages=True),
        }
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        staff = resources.get_role(guild, "role_staff")
        if staff is not None:
            overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        try:
            channel = await guild.create_text_channel(
                name=_slug(name), category=category, overwrites=overwrites,
                reason=f"Salon du clan {name}",
            )
        except discord.Forbidden:
            notes.append(t(gid, "clan.warn_channel_perm"))
            set_clan_fields(gid, clan["id"], role_id=role.id if role else None)
            return notes
        except discord.HTTPException as e:
            log.warning(f"[{guild.name}] Salon de clan refusé : {e}")
            notes.append(t(gid, "clan.warn_channel_perm"))
            return notes

        set_clan_fields(gid, clan["id"], channel_id=channel.id,
                        role_id=role.id if role else None)
        await self.post_clan_menus(channel, clan)
        notes.append(t(gid, "clan.space_open", channel=channel.mention))
        log.info(f"[{guild.name}] Salon du clan {name} ouvert : #{channel.name}")
        return notes
    
    async def _reset_clan_liaison_channel(self, guild: discord.Guild, clan: dict) -> None:
        """Réinitialise le channel de liaison d'un clan (supprime seulement les demandes CW, garde les stats)."""
        gid = guild.id
        clan_id = clan["id"]
        channel_id = clan.get("channel_id")
        
        if not channel_id:
            return
        
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        
        try:
            # Ne supprimer que les messages de demande de ClanWar (ceux qui contiennent "vs" ou "ClanWar")
            deleted_count = 0
            async for message in channel.history(limit=None):
                # Garder l'embed de carte et les boutons
                if message.id == clan.get("card_message_id"):
                    continue
                
                # Garder les messages de stats (ceux qui ne sont pas des demandes CW)
                content_lower = message.content.lower() if message.content else ""
                if "vs" not in content_lower and "clanwar" not in content_lower and "guerre" not in content_lower:
                    continue
                
                # Supprimer seulement les demandes de ClanWar
                try:
                    await message.delete()
                    deleted_count += 1
                    # Petit délai pour éviter le rate limiting
                    if deleted_count % 5 == 0:
                        await asyncio.sleep(0.5)
                except discord.HTTPException:
                    pass
            
            log.info(f"[{guild.name}] Demandes CW supprimées dans le channel de liaison du clan {clan.get('name')} ({deleted_count} messages)")
            
            # Réinitialiser le compteur d'annonces
            reset_clan_announcement(gid, clan_id)
            
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Erreur lors de la réinitialisation du channel de liaison: {e}")

    # -- Les deux menus du salon ---------------------------------------
    async def post_clan_menus(self, channel: discord.TextChannel, clan: dict) -> None:
        """Publie la fiche avec ses quatre boutons, puis le menu ClanWar.
        Leurs identifiants sont mémorisés pour les remplacer au démarrage."""
        gid = channel.guild.id
        card = await channel.send(embed=self.space_embed(gid, clan), view=ClanSpaceView(self))
        menu = await channel.send(embed=war_menu_embed(gid, clan),
                                  view=ClanWarMenuView(self, gid, clan.get("war_ready", True)))
        set_clan_fields(gid, clan["id"], card_message_id=card.id, war_menu_message_id=menu.id)

    async def _clear_clan_menus(self, channel: discord.TextChannel, clan: dict) -> None:
        """Supprime les menus déjà publiés : ceux dont l'identifiant est
        mémorisé, et les anciens messages de boutons qui n'en avaient pas."""
        stale = {clan.get("card_message_id"), clan.get("war_menu_message_id")} - {None}
        async for message in channel.history(limit=50):
            if self.bot.user is None or message.author.id != self.bot.user.id:
                continue
            ids = {getattr(child, "custom_id", None)
                   for row in message.components for child in getattr(row, "children", [])}
            if ids & CLAN_MENU_IDS:
                stale.add(message.id)
        for message_id in stale:
            try:
                await channel.get_partial_message(message_id).delete()
            except discord.NotFound:
                pass

    async def _repost_clan_menus(self) -> None:
        """Au démarrage, chaque salon de clan reçoit ses deux menus tout neufs."""
        await self.bot.wait_until_ready()
        for guild in list(self.bot.guilds):
            if not self.enabled(guild.id):
                continue
            for clan in list(get_clans(guild.id).values()):
                channel = self.clan_channel(guild, clan)
                if channel is None:
                    continue
                try:
                    await self._clear_clan_menus(channel, clan)
                    await self.post_clan_menus(channel, clan)
                except discord.HTTPException as e:
                    log.warning(f"[{guild.name}] Menus du clan {clan.get('name')} non republiés : {e}")
                # Cadence douce : deux cents clans ne partent pas d'un coup.
                await asyncio.sleep(1)

    def space_embed(self, guild_id: int, clan: dict) -> discord.Embed:
        """La fiche affichée dans le salon du clan."""
        embed = clan_embed(self.bot, guild_id, clan)
        created = clan.get("created_at")
        if created:
            embed.add_field(name=t(guild_id, "clan.field_since"),
                            value=f"<t:{int(created)}:D>", inline=True)
        embed.set_footer(text=t(guild_id, "clan.space_footer"))
        return embed

    async def refresh_clan_space(self, guild: discord.Guild | None, clan: dict | None) -> None:
        """Réécrit la fiche du salon. C'est ce qui la tient à jour « en
        direct » : on modifie le message publié, on n'en poste pas un second
        à chaque arrivée."""
        if guild is None or clan is None:
            return
        channel = self.clan_channel(guild, clan)
        message_id = clan.get("card_message_id")
        if channel is None or not message_id:
            return
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=self.space_embed(guild.id, clan))
        except discord.NotFound:
            # La fiche a été supprimée à la main : on en republie une plutôt
            # que de laisser le salon sans rien.
            try:
                card = await channel.send(embed=self.space_embed(guild.id, clan), view=ClanSpaceView(self))
                set_clan_fields(guild.id, clan["id"], card_message_id=card.id)
            except discord.HTTPException:
                pass
        except discord.HTTPException as e:
            log.warning(f"[{guild.name}] Fiche de clan non mise à jour : {e}")

    async def close_clan_space(self, guild: discord.Guild | None, clan: dict) -> None:
        """Le clan est dissous : son salon et son rôle disparaissent avec lui.
        Les laisser derrière remplirait la catégorie de salons fantômes."""
        if guild is None:
            return
        name = sanitize(clan.get("name", "?"), MAX_CLAN_NAME)
        channel = self.clan_channel(guild, clan)
        if channel is not None:
            try:
                await channel.delete(reason=f"Clan {name} dissous")
            except discord.HTTPException:
                pass
        role = self.clan_role(guild, clan)
        if role is not None:
            try:
                await role.delete(reason=f"Clan {name} dissous")
            except discord.HTTPException:
                pass

    async def on_roster_change(self, guild: discord.Guild | None, clan: dict,
                               user_id: int, *, joined: bool) -> None:
        """Un membre entre ou sort : rôle mis à jour, fiche réécrite."""
        if guild is None:
            return
        member = guild.get_member(user_id)
        if member is not None:
            await self.set_clan_role(member, clan, add=joined)
        await self.refresh_clan_space(guild, get_clan(guild.id, clan["id"]))

    # -- Invitation ------------------------------------------------------
    async def send_invite(self, interaction: discord.Interaction,
                          clan: dict, member: discord.Member) -> None:
        gid = interaction.guild_id
        name = sanitize(clan.get("name", "?"), MAX_CLAN_NAME)
        if member.bot:
            await interaction.response.send_message(t(gid, "clan.err_bot"), ephemeral=True)
            return
        if clan_of(gid, member.id) is not None:
            await interaction.response.send_message(
                t(gid, "clan.err_target_clan", player=member.mention), ephemeral=True)
            return

        send_log(self.bot, gid, "clan", t(gid, "logs.clan_invite"), user=interaction.user,
                 fields=[(t(gid, "logs.f_clan"), name), (t(gid, "logs.f_member"), member.mention)])
        embed = clan_embed(self.bot, gid, clan, invite=True)
        view = InviteView(self, gid, clan["id"], member.id)
        try:
            await member.send(embed=embed, view=view)
        except discord.Forbidden:
            # MP fermés : l'invitation part dans le salon, toujours cliquable
            # par le seul invité — sinon l'invitation serait perdue sans que
            # personne ne sache pourquoi.
            await interaction.response.send_message(
                content=t(gid, "clan.invite_public", player=member.mention),
                embed=embed, view=view,
            )
            return
        await interaction.response.send_message(
            t(gid, "clan.invite_sent", player=member.mention, name=name), ephemeral=True)

    # -- ClanWar ---------------------------------------------------------
    async def send_war_request(self, interaction: discord.Interaction,
                               clan: dict, target: dict, size: int) -> None:
        """Publie le défi dans le salon du clan visé et l'inscrit dans sa file."""
        gid = interaction.guild_id
        
        # Le ClanWar suit l'option Clan de /option : c'est elle qui ouvre les
        # clans, leurs salons et leurs défis.
        if not self.enabled(gid):
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=t(gid, "clan.war_system_disabled"), kind="error"),
                view=None)
            return
        
        # L'état a pu changer depuis l'ouverture du menu : on relit les deux
        # clans avant de publier le défi.
        clan = get_clan(gid, clan["id"]) or clan
        target = get_clan(gid, target["id"]) or target
        if not clan.get("war_ready", True) or not target.get("war_ready", True):
            description = (t(gid, "clan.war_err_self_dnd") if not clan.get("war_ready", True)
                           else t(gid, "clan.war_err_target_dnd",
                                  name=sanitize(target.get("name", "?"), MAX_CLAN_NAME)))
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=description, kind="warning"), view=None)
            return

        guild = interaction.guild
        channel = self.clan_channel(guild, target) if guild else None
        if channel is None:
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=t(gid, "clan.war_no_channel"), kind="error"),
                view=None)
            return

        mine = sanitize(clan.get("name", "?"), MAX_CLAN_NAME)
        embed = embeds.base(
            gid,
            title=t(gid, "clan.war_offer_title", name=mine),
            description=t(gid, "clan.war_offer_desc",
                          leader=f"<@{clan.get('leader_id')}>", size=size),
            kind="error",
        )
        if clan.get("icon_url"):
            embed.set_thumbnail(url=clan["icon_url"])

        role = self.clan_role(guild, target)
        try:
            message = await channel.send(
                content=role.mention if role is not None else None,
                allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role] if role else False),
                embed=embed, view=WarAnswerView(self, gid),
            )
        except discord.HTTPException:
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=t(gid, "clan.war_no_channel"), kind="error"),
                view=None)
            return

        # Supprimer toutes les anciennes demandes de wars
        self._clear_old_war_requests(gid, target["id"])

        added = add_clan_request(gid, target["id"], "wars", {
            "from_clan": clan["id"], "size": size,
            "at": int(time.time()), "message_id": message.id,
        })
        if not added:
            # Un défi du même clan attendait déjà : on retire le doublon
            # qu'on vient de publier plutôt que d'en laisser deux.
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=t(gid, "clan.war_already"), kind="warning"),
                view=None)
            return

        await interaction.response.edit_message(
            embed=embeds.base(
                gid,
                description=t(gid, "clan.war_sent",
                              name=sanitize(target.get("name", "?"), MAX_CLAN_NAME), size=size),
                kind="success"),
            view=None,
        )
        send_log(self.bot, gid, "duel", t(gid, "logs.duel_sent"), user=interaction.user,
                 fields=[(t(gid, "logs.f_clan"), mine),
                         (t(gid, "logs.f_rival"), sanitize(target.get("name", "?"), MAX_CLAN_NAME)),
                         (t(gid, "logs.f_format"), f"{size} vs {size}")])
    
    def _clear_old_war_requests(self, guild_id: int, clan_id: str) -> None:
        """Supprime toutes les anciennes demandes de wars d'un clan."""
        try:
            old_requests = get_clan_requests(guild_id, clan_id, "wars")
            for request in old_requests:
                # On ne supprime que de la liste, pas les messages (ils seront supprimés automatiquement)
                # ou on pourrait aussi supprimer les messages si on veut
                pass
        except Exception as e:
            log.error(f"Erreur lors de la suppression des anciennes demandes de wars: {e}")

    async def answer_war(self, interaction: discord.Interaction, clan: dict,
                         request: dict, *, accepted: bool) -> None:
        """Répond au défi, et prévient le clan qui l'a lancé dans son salon."""
        gid = interaction.guild_id
        guild = interaction.guild
        rival = get_clan(gid, request.get("from_clan"))
        size = int(request.get("size", 0))
        remove_clan_request(gid, clan["id"], "wars", request.get("from_clan"))

        mine = sanitize(clan.get("name", "?"), MAX_CLAN_NAME)
        key = "clan.war_accepted" if accepted else "clan.war_declined"
        answer = embeds.base(gid, description=t(gid, key, name=mine, size=size),
                             kind="success" if accepted else "warning")
        await interaction.response.edit_message(content=None, embed=answer, view=None)
        send_log(self.bot, gid, "duel", t(gid, "logs.duel_accepted" if accepted else "logs.duel_declined"),
                 user=interaction.user, color=embeds.SUCCESS if accepted else None,
                 fields=[(t(gid, "logs.f_clan"), mine),
                         (t(gid, "logs.f_rival"), sanitize(rival.get("name", "?"), MAX_CLAN_NAME) if rival else None),
                         (t(gid, "logs.f_format"), f"{size} vs {size}")])

        # Répondu depuis la liste « Request » : le défi d'origine porte encore
        # ses deux boutons dans le salon. On les retire et on supprime le message.
        origin_id = request.get("message_id")
        if guild is not None and origin_id and origin_id != interaction.message.id:
            channel = self.clan_channel(guild, clan)
            if channel is not None:
                try:
                    origin = await channel.fetch_message(origin_id)
                    await origin.edit(view=None)
                    # Supprimer le message d'origine
                    await origin.delete()
                except discord.HTTPException:
                    pass
        
        # Ajouter à l'historique du clan
        self._add_to_war_history(gid, clan, request, accepted)

        if rival is None or guild is None:
            return
        channel = self.clan_channel(guild, rival)
        if channel is None:
            return
        role = self.clan_role(guild, rival)
        try:
            await channel.send(
                content=role.mention if role is not None else None,
                allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role] if role else False),
                embed=embeds.base(
                    gid,
                    title=t(gid, "clan.war_reply_title"),
                    description=t(gid, key, name=mine, size=size),
                    kind="success" if accepted else "warning"),
            )
        except discord.HTTPException:
            pass
        
        # Si accepté, lancer la session de ClanWar
        if accepted and guild is not None and rival is not None:
            await self._start_clan_war_session(guild, clan, rival, size)
    
    def _add_to_war_history(self, guild_id: int, clan: dict, request: dict, accepted: bool) -> None:
        """Ajoute une demande de war traitée à l'historique du clan."""
        try:
            if "war_history" not in clan:
                clan["war_history"] = []
            
            # Garder seulement les 20 derniers éléments
            history_entry = {
                "from_clan": request.get("from_clan"),
                "size": request.get("size", 0),
                "at": request.get("at", int(time.time())),
                "status": "accepted" if accepted else "declined"
            }
            clan["war_history"].append(history_entry)
            if len(clan["war_history"]) > 20:
                clan["war_history"] = clan["war_history"][-20:]
            
            # Sauvegarder les modifications
            set_clan_fields(guild_id, clan["id"], war_history=clan["war_history"])
        except Exception as e:
            log.error(f"Erreur lors de l'ajout à l'historique des wars: {e}")
    
    async def _start_clan_war_session(self, guild: discord.Guild, clan1: dict, clan2: dict, size: int) -> None:
        """Démarre une session de ClanWar entre deux clans."""
        gid = guild.id
        
        # Annuler toute session existante pour ce serveur
        if str(gid) in self.active_war_sessions:
            old_session = self.active_war_sessions[str(gid)]
            await old_session.cancel()
        
        # Créer et démarrer la nouvelle session
        session = ClanWarSession(self, guild, clan1, clan2, size)
        self.active_war_sessions[str(gid)] = session
        
        try:
            await session.start()
            
        except Exception as e:
            log.error(f"[{guild.name}] Erreur lors du démarrage du ClanWar: {e}")
            await session.cancel()
            if str(gid) in self.active_war_sessions:
                del self.active_war_sessions[str(gid)]

    # -- Demandes en attente ---------------------------------------------
    async def notify_join(self, guild: discord.Guild | None, clan: dict,
                          applicant: discord.abc.User) -> None:
        """Annonce une demande d'adhésion dans le salon du clan."""
        if guild is None or not get_features(guild.id)["clan_notice"]:
            return
        channel = self.clan_channel(guild, clan)
        if channel is None:
            return
        try:
            await channel.send(
                content=f"<@{clan.get('leader_id')}>",
                embed=embeds.base(
                    guild.id,
                    title=t(guild.id, "clan.queue_joins_title"),
                    description=t(guild.id, "clan.join_notice", player=applicant.mention),
                    kind="brand"),
            )
        except discord.HTTPException:
            pass

    async def show_queue(self, interaction: discord.Interaction, clan: dict, kind: str) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        if guild is None:
            return
        entries = get_clan_requests(gid, clan["id"], kind)
        title = t(gid, "clan.queue_wars_title" if kind == "wars" else "clan.queue_joins_title")
        if not entries:
            await interaction.response.send_message(
                embed=embeds.base(gid, title=title,
                                  description=t(gid, "clan.queue_empty"), kind="brand"),
                ephemeral=True)
            return

        lines = []
        for entry in entries:
            if kind == "wars":
                rival = get_clan(gid, entry.get("from_clan"))
                name = sanitize(rival.get("name", "?"), MAX_CLAN_NAME) if rival else "?"
                lines.append(t(gid, "clan.queue_war_line", name=name, size=entry.get("size", 0),
                               when=f"<t:{int(entry.get('at', 0))}:R>"))
            else:
                lines.append(t(gid, "clan.queue_join_line", player=f"<@{entry.get('user_id')}>",
                               when=f"<t:{int(entry.get('at', 0))}:R>"))

        await interaction.response.send_message(
            embed=embeds.base(gid, title=title, description="\n".join(lines)[:4000], kind="brand"),
            view=QueueView(self, guild, clan, kind, entries),
            ephemeral=True,
        )
    
    async def show_history(self, interaction: discord.Interaction, clan: dict) -> None:
        """Affiche l'historique des demandes de wars traitées."""
        gid = interaction.guild_id
        guild = interaction.guild
        if guild is None:
            return
        
        # Récupérer l'historique depuis les settings du clan
        history = clan.get("war_history", [])
        title = t(gid, "clan.history_title")
        
        if not history:
            await interaction.response.send_message(
                embed=embeds.base(gid, title=title,
                                  description=t(gid, "clan.history_empty"), kind="brand"),
                ephemeral=True)
            return

        lines = []
        for entry in history:
            rival = get_clan(gid, entry.get("from_clan"))
            name = sanitize(rival.get("name", "?"), MAX_CLAN_NAME) if rival else "?"
            status = entry.get("status", "?")
            status_emoji = "✅" if status == "accepted" else "❌" if status == "declined" else "❓"
            lines.append(f"{status_emoji} **{name}** — {entry.get('size', 0)} vs {entry.get('size', 0)} — <t:{int(entry.get('at', 0))}:R>")

        await interaction.response.send_message(
            embed=embeds.base(gid, title=title, description="\n".join(lines)[:4000], kind="brand"),
            ephemeral=True,
        )

    async def answer_join(self, interaction: discord.Interaction, clan: dict,
                          user_id: int, *, accepted: bool) -> None:
        gid = interaction.guild_id
        remove_clan_request(gid, clan["id"], "joins", user_id)
        name = sanitize(clan.get("name", "?"), MAX_CLAN_NAME)
        send_log(self.bot, gid, "clan",
                 t(gid, "logs.clan_request_accepted" if accepted else "logs.clan_request_refused"),
                 user=interaction.user,
                 fields=[(t(gid, "logs.f_clan"), name), (t(gid, "logs.f_member"), f"<@{user_id}>")])

        if not accepted:
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=t(gid, "clan.join_refused",
                                                     player=f"<@{user_id}>"), kind="warning"),
                view=None)
            return

        if not add_clan_member(gid, clan["id"], user_id):
            # Le joueur a rejoint un autre clan entre-temps : sa demande n'a
            # plus d'objet, on le dit au lieu de laisser croire à un bug.
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=t(gid, "clan.join_gone",
                                                     player=f"<@{user_id}>"), kind="warning"),
                view=None)
            return

        await interaction.response.edit_message(
            embed=embeds.base(gid, description=t(gid, "clan.join_accepted",
                                                 player=f"<@{user_id}>", name=name),
                              kind="success"),
            view=None)
        await self.on_roster_change(interaction.guild, clan, user_id, joined=True)
        await self.refresh_leaderboard(interaction.guild)

    # -- Classement des clans -------------------------------------------
    async def refresh_leaderboard(self, guild: discord.Guild | None) -> None:
        """Republie le classement dès qu'un clan bouge."""
        if guild is None:
            return
        cog = self.bot.get_cog("Classement")
        if cog is None:
            return
        try:
            await cog.update_classement_channel(guild)
        except Exception as e:
            log.error(f"[{guild.name}] Classement des clans non republié : {e}")

    # -- Complétion des noms de clan -------------------------------------
    async def clan_choices(self, interaction: discord.Interaction,
                           current: str) -> list[app_commands.Choice[str]]:
        gid = interaction.guild_id
        if gid is None:
            return []
        wanted = current.casefold()
        return [
            app_commands.Choice(
                name=sanitize(clan.get("name", "?"), MAX_CLAN_NAME)[:100], value=clan["id"])
            for clan in get_clans(gid).values()
            if wanted in clan.get("name", "").casefold()
        ][:25]

    # -- Commandes -------------------------------------------------------
    @app_commands.command(name="clan", description="Ton clan : fiche, création et invitations.")
    @app_commands.describe(inviter="Le membre à inviter dans ton clan",
                           rejoindre="Le clan à qui envoyer une demande d'adhésion")
    @app_commands.autocomplete(rejoindre=clan_choices)
    async def clan(self, interaction: discord.Interaction,
                   inviter: discord.Member | None = None,
                   rejoindre: str | None = None) -> None:
        gid = interaction.guild_id
        if gid is None or interaction.guild is None:
            await interaction.response.send_message(t(gid, "common.members_only"), ephemeral=True)
            return

        mine = clan_of(gid, interaction.user.id)

        if rejoindre is not None:
            await self.request_join(interaction, rejoindre, mine)
            return

        if inviter is not None:
            if mine is None:
                await interaction.response.send_message(t(gid, "clan.err_no_clan"), ephemeral=True)
                return
            if interaction.user.id != mine.get("leader_id"):
                await interaction.response.send_message(t(gid, "clan.err_leader_only"), ephemeral=True)
                return
            await self.send_invite(interaction, mine, inviter)
            return

        if mine is None:
            embed = embeds.base(
                gid,
                title=t(gid, "clan.create_title"),
                description=t(gid, "clan.create_desc"),
                kind="brand",
                footer=t(gid, "clan.create_footer"),
            )
            embeds.brand(embed, interaction.guild)
            await interaction.response.send_message(
                embed=embed, view=CreateView(self, gid), ephemeral=True)
            return

        await interaction.response.send_message(
            embed=clan_embed(self.bot, gid, mine),
            view=ClanView(self, gid, mine, interaction.user.id),
            ephemeral=True,
        )

    async def request_join(self, interaction: discord.Interaction,
                           wanted: str, mine: dict | None) -> None:
        """Dépose une demande d'adhésion. Elle attend dans le salon du clan,
        derrière le bouton **Invites** — le chef décide."""
        gid = interaction.guild_id
        if mine is not None:
            await interaction.response.send_message(t(gid, "clan.err_already"), ephemeral=True)
            return
        # L'autocomplétion renvoie un identifiant, mais rien n'empêche de
        # taper un nom à la main : on accepte les deux.
        target = get_clan(gid, wanted) or clan_named(gid, wanted)
        if target is None:
            await interaction.response.send_message(t(gid, "clan.err_unknown"), ephemeral=True)
            return
        name = sanitize(target.get("name", "?"), MAX_CLAN_NAME)
        if not add_clan_request(gid, target["id"], "joins",
                                {"user_id": interaction.user.id, "at": int(time.time())}):
            await interaction.response.send_message(
                t(gid, "clan.join_pending", name=name), ephemeral=True)
            return
        await interaction.response.send_message(
            t(gid, "clan.join_sent", name=name), ephemeral=True)
        send_log(self.bot, gid, "clan", t(gid, "logs.clan_request"), user=interaction.user,
                 fields=[(t(gid, "logs.f_clan"), name)])
        await self.notify_join(interaction.guild, target, interaction.user)

    @app_commands.command(
        name="clantransfer",
        description="Transfère la propriété d'un clan à un autre membre.",
    )
    @app_commands.describe(clan="Le clan à transférer",
                           nouveau_chef="Le membre qui devient chef")
    @app_commands.autocomplete(clan=clan_choices)
    async def clantransfer(self, interaction: discord.Interaction,
                           clan: str, nouveau_chef: discord.Member) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        if gid is None or guild is None:
            await interaction.response.send_message(t(gid, "common.members_only"), ephemeral=True)
            return

        # Le verrou est un rôle **désigné**, pas une permission Discord :
        # transférer un clan est un arbitrage, pas de l'administration.
        role = resources.get_role(guild, "role_clan_transfer")
        if role is None:
            await interaction.response.send_message(t(gid, "clan.transfer_no_role"), ephemeral=True)
            return
        if role not in getattr(interaction.user, "roles", []):
            await interaction.response.send_message(
                t(gid, "clan.transfer_denied", role=role.name), ephemeral=True)
            return

        target = get_clan(gid, clan) or clan_named(gid, clan)
        if target is None:
            await interaction.response.send_message(t(gid, "clan.err_unknown"), ephemeral=True)
            return
        if nouveau_chef.bot:
            await interaction.response.send_message(t(gid, "clan.err_bot"), ephemeral=True)
            return

        name = sanitize(target.get("name", "?"), MAX_CLAN_NAME)
        old_leader_id = target.get("leader_id")
        if nouveau_chef.id == old_leader_id:
            await interaction.response.send_message(
                t(gid, "clan.transfer_same"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Pas encore membre : on l'ajoute, sauf s'il appartient déjà ailleurs.
        if nouveau_chef.id not in target.get("members", []):
            if clan_of(gid, nouveau_chef.id) is not None:
                await interaction.followup.send(
                    t(gid, "clan.err_target_clan", player=nouveau_chef.mention), ephemeral=True)
                return
            add_clan_member(gid, target["id"], nouveau_chef.id)
            await self.on_roster_change(guild, target, nouveau_chef.id, joined=True)

        transfer_clan_leader(gid, target["id"], nouveau_chef.id)
        send_log(self.bot, gid, "clan", t(gid, "logs.clan_transfer"), user=interaction.user,
                 fields=[(t(gid, "logs.f_clan"), name),
                         (t(gid, "logs.f_old_leader"), f"<@{old_leader_id}>" if old_leader_id else None),
                         (t(gid, "logs.f_new_leader"), nouveau_chef.mention)])

        old_leader = guild.get_member(old_leader_id) if old_leader_id else None
        if old_leader is not None:
            # L'ancien chef reste dans le clan : il perd le rôle et le tag,
            # pas sa place.
            await self.clear_perks(old_leader, target)
        notes = await self.apply_leader_perks(nouveau_chef, target)

        await self.refresh_clan_space(guild, get_clan(gid, target["id"]))
        await self.refresh_leaderboard(guild)

        await interaction.followup.send(
            content="\n".join(notes) or None,
            embed=embeds.base(
                gid,
                title=t(gid, "clan.transfer_title"),
                description=t(gid, "clan.transfer_done",
                              name=name, player=nouveau_chef.mention),
                kind="success"),
            ephemeral=True,
        )
        log.info(f"[{guild.name}] Clan {name} transféré à {nouveau_chef} par {interaction.user}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Clan(bot))
    log.info("Cog Clan chargé")
