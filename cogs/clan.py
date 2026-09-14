"""
Cog : Clans
===========
Équipes permanentes, par-dessus les queues.

Une queue rassemble des joueurs pour une soirée ; un clan les garde. Il a un
nom, un logo, éventuellement son propre serveur Discord, et un classement
qui agrège les victoires de ses membres.

Ce que fait la commande
-----------------------
- `/clan` — sans rien : ouvre la fiche de ton clan, ou la création si tu n'en
  as pas encore.
- `/clan inviter:@membre` — envoie l'invitation en message privé. Seul
  l'invité peut l'accepter ou la refuser.
- `/clan rejoindre:<nom>` — demande à entrer dans un clan. La demande attend
  dans son salon, derrière le bouton **Invites**.
- `/clantransfer` — passe la propriété d'un clan à un autre membre. Réservé
  au rôle désigné dans `/option → Clan`.

Le salon de liaison
-------------------
Quand les clans sont activés (`/option → Clan`), la création d'un clan ouvre
**un salon privé** dans la catégorie désignée : le clan et le staff, personne
d'autre. On y trouve la fiche du clan — chef, effectif, lien du serveur —
**tenue à jour en direct** à chaque arrivée et à chaque départ, et trois
boutons : lancer un ClanWar, répondre aux défis reçus, traiter les demandes
d'adhésion.

Ce que le bot crée, et pourquoi c'est une exception
---------------------------------------------------
Le bot ne crée jamais de rôle ni de salon **sauf ici** : un salon et un rôle
`Clan - Nom`, à la demande explicite du propriétaire du bot. Ils appartiennent
au clan, naissent avec lui et disparaissent avec lui. Tous les autres rôles
restent **désignés** par l'administrateur dans `/option`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import unicodedata
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

import embeds
import resources
from guild_settings import (
    MAX_CLAN_NAME, get_clans, clan_of, create_clan, clan_named, add_clan_member,
    remove_clan_member, get_clan, get_features, set_features, set_clan_fields,
    clan_by_channel, transfer_clan_leader, get_clan_requests, add_clan_request,
    remove_clan_request, get_clan_war_session, set_clan_war_session,
    clear_clan_war_session
)
from i18n import t
from text_safety import sanitize

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


def _slug(name: str) -> str:
    """Nom de salon à partir d'un nom de clan.

    Discord accepte les accents mais les affiche de façon inégale selon les
    clients : on translittère, et on garde un repli pour un nom entièrement
    composé de caractères non latins (coréen, cyrillique…)."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", plain).strip("-").lower()
    return slug[:90] or "clan"


# ----------------------------------------------------------------------
# Statistiques
# ----------------------------------------------------------------------
def clan_stats(bot: commands.Bot, guild_id: int, clan: dict) -> tuple[int, int, float]:
    """Victoires, défaites et ratio du clan.

    Les chiffres viennent du classement des joueurs : un clan ne joue pas,
    ses membres jouent. Tenir un second compteur en parallèle le ferait
    diverger dès la première partie non enregistrée."""
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
    """La fiche : nom, logo, ratio, effectif, membres, serveur du clan.

    La même en message privé pour une invitation et sur le serveur pour la
    consulter — on décide en connaissance de cause, pas sur un nom seul."""
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
    # affaire. La liste est bornée — un clan de cent membres déborderait la
    # limite de 1024 caractères d'un champ et Discord refuserait l'embed.
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
    """Les deux boutons de l'invitation, en message privé.

    `interaction_check` est la vraie barrière : un message privé n'est visible
    que par son destinataire, mais la vue est aussi renvoyée sur le serveur
    quand les MP sont fermés — là, n'importe qui pourrait cliquer."""

    def __init__(self, cog: "Clan", guild_id: int, clan_id: str, invitee_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.clan_id = clan_id
        self.invitee_id = invitee_id
        self.accept.label = t(guild_id, "clan.btn_accept")
        self.decline.label = t(guild_id, "clan.btn_decline")

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


# ----------------------------------------------------------------------
# Le salon du clan : fiche vivante et boutons
# ----------------------------------------------------------------------
class ClanSpaceView(discord.ui.View):
    """Les quatre boutons sous la fiche, dans le salon du clan.

    Vue **persistante** : elle doit répondre des semaines après avoir été
    publiée, donc pas d'expiration et un identifiant fixe par bouton. Le clan
    concerné n'est pas codé dans ces identifiants — il se déduit du salon où
    l'on a cliqué, ce qui évite d'avoir un identifiant différent par clan."""

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

    @discord.ui.button(label="ClanWar", style=discord.ButtonStyle.danger,
                       emoji="⚔️", custom_id="cyq:clan:war")
    async def war(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clan = await self._context(interaction)
        if clan is None:
            return
        gid = interaction.guild_id
        rivals = [c for c in get_clans(gid).values() if c["id"] != clan["id"]]
        if not rivals:
            await interaction.response.send_message(t(gid, "clan.war_no_rival"), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embeds.base(gid, title=t(gid, "clan.war_title"),
                              description=t(gid, "clan.war_pick_desc"), kind="error"),
            view=WarSetupView(self.cog, gid, clan, rivals),
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
                       emoji="📜", custom_id="cyq:clan:hist")
    async def history(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clan = await self._context(interaction)
        if clan is None:
            return
        await self.cog.show_history(interaction, clan)

    @discord.ui.button(label="Invites", style=discord.ButtonStyle.secondary,
                       emoji="✉️", custom_id="cyq:clan:inv")
    async def invites(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        clan = await self._context(interaction)
        if clan is None:
            return
        if interaction.user.id != clan.get("leader_id"):
            await interaction.response.send_message(
                t(interaction.guild_id, "clan.err_leader_only"), ephemeral=True)
            return
        await self.cog.show_queue(interaction, clan, "joins")


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
    """Accepter ou refuser un défi, dans le salon du clan défié.

    Persistante elle aussi : un défi posté le soir doit rester cliquable le
    lendemain. Le défi concerné se retrouve par l'identifiant du message."""

    def __init__(self, cog: "Clan", guild_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        # Les libellés vivent dans le message, pas dans la vue : celle qu'on
        # ré-enregistre au démarrage n'a pas de serveur et garde les libellés
        # par défaut, que personne ne verra jamais.
        if guild_id is not None:
            self.accept.label = t(guild_id, "clan.btn_accept")
            self.decline.label = t(guild_id, "clan.btn_decline")

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
    """Les demandes en attente : on en choisit une, puis on répond.

    Le même écran sert aux défis reçus et aux demandes d'adhésion — deux
    files, une seule mécanique. Les séparer en deux vues aurait garanti que
    l'une prenne du retard sur l'autre."""

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
# Session de ClanWar
# ----------------------------------------------------------------------
class ClanWarSession:
    """Gère une session de ClanWar après acceptation.
    
    Cette classe gère :
    - Le timer de 15 minutes pour la préparation
    - La création de salons vocaux privés pour les 2 clans
    - Le système de mute (seuls les leads peuvent parler)
    - L'annonce vocale du bot quand la partie va commencer
    - L'intégration avec le système de vote de capitaine
    """
    
    def __init__(self, cog: "Clan", guild: discord.Guild, clan1: dict, clan2: dict, size: int):
        self.cog = cog
        self.guild = guild
        self.guild_id = guild.id
        self.clan1 = clan1
        self.clan2 = clan2
        self.size = size
        self.started = False
        self.ended = False
        self.preparation_end_time = None
        self.voice_channel = None
        self.team_channels = {}
        self.captain_vote_channel = None
        self.timer_task = None
        self.notification_messages = {}  # channel_id -> message_id
        self.countdown_task = None
        self.countdown_started = False
        self.voice_client = None
        self.leader_timeout_task = None
        self.leader_left_time = None
        self.leader_left_which = None  # "clan1" ou "clan2"
        self.clan1_points = 0
        self.clan2_points = 0
        self.round_votes = {}  # user_id -> clan_choice
        self.main_embed_message = None  # Stocke le message principal pour les mises à jour
    
    def to_dict(self) -> dict[str, Any]:
        """Sérialise la session pour persistance."""
        team1_id = self.team_channels.get("team1").id if self.team_channels.get("team1") else None
        team2_id = self.team_channels.get("team2").id if self.team_channels.get("team2") else None
        
        return {
            "guild_id": self.guild_id,
            "clan1_id": self.clan1["id"],
            "clan2_id": self.clan2["id"],
            "size": self.size,
            "started": self.started,
            "ended": self.ended,
            "preparation_end_time": self.preparation_end_time,
            "voice_channel_id": getattr(self.voice_channel, "id", None),
            "captain_vote_channel_id": getattr(self.captain_vote_channel, "id", None),
            "notification_messages": self.notification_messages,
            "countdown_started": self.countdown_started,
            "team_channels": {
                "team1": team1_id,
                "team2": team2_id,
            },
            "clan1_points": self.clan1_points,
            "clan2_points": self.clan2_points,
            "round_votes": self.round_votes,
        }
    
    @classmethod
    def from_dict(cls, cog: "Clan", guild: discord.Guild, data: dict[str, Any]) -> "ClanWarSession | None":
        """Reconstruit une session depuis les données persistées."""
        if guild is None:
            return None
        
        clan1 = get_clan(guild.id, data.get("clan1_id"))
        clan2 = get_clan(guild.id, data.get("clan2_id"))
        
        if clan1 is None or clan2 is None:
            return None
        
        session = cls(cog, guild, clan1, clan2, data.get("size", 1))
        session.started = data.get("started", False)
        session.ended = data.get("ended", False)
        session.preparation_end_time = data.get("preparation_end_time")
        session.notification_messages = data.get("notification_messages", {})
        session.countdown_started = data.get("countdown_started", False)
        
        # Reconstruire les channels
        voice_channel_id = data.get("voice_channel_id")
        if voice_channel_id:
            session.voice_channel = guild.get_channel(voice_channel_id)
        
        captain_vote_channel_id = data.get("captain_vote_channel_id")
        if captain_vote_channel_id:
            session.captain_vote_channel = guild.get_channel(captain_vote_channel_id)
        
        # Reconstruire les channels d'équipe
        team_channels_data = data.get("team_channels", {})
        session.team_channels = {}
        if team_channels_data.get("team1"):
            session.team_channels["team1"] = guild.get_channel(team_channels_data["team1"])
        if team_channels_data.get("team2"):
            session.team_channels["team2"] = guild.get_channel(team_channels_data["team2"])
        
        # Restaurer les points et votes
        session.clan1_points = data.get("clan1_points", 0)
        session.clan2_points = data.get("clan2_points", 0)
        session.round_votes = data.get("round_votes", {})
        
        return session
        
    async def start(self):
        """Démarre la session de ClanWar."""
        if self.started:
            return
        
        self.started = True
        self.preparation_end_time = time.time() + 900  # 15 minutes = 900 secondes
        
        # Sauvegarder la session
        set_clan_war_session(self.guild_id, self.to_dict())
        
        # Créer le salon vocal privé pour les 2 clans
        await self._create_war_voice_channel()
        
        # Muter tous les membres sauf les leads
        await self._setup_voice_permissions()
        
        # Envoyer les notifications avec le nouveau format (une seule fois)
        if not self.notification_messages:  # Ne pas envoyer si déjà envoyé
            await self._send_war_notifications()
        
        # Lancer le timer de 15 minutes avec mise à jour du minuteur
        self.timer_task = asyncio.create_task(self._preparation_timer_with_update())
        
        log.info(f"[{self.guild.name}] ClanWar démarré: {self.clan1.get('name')} vs {self.clan2.get('name')} ({self.size}v{self.size})")
    
    async def _create_war_voice_channel(self):
        """Crée un salon vocal privé pour les 2 clans avec limite de joueurs."""
        category = resources.get_category(self.guild, "category_clan")
        if category is None:
            log.error(f"[{self.guild.name}] Pas de catégorie clan pour créer le vocal de ClanWar")
            return
        
        # Récupérer les rôles des 2 clans
        role1 = self.cog.clan_role(self.guild, self.clan1)
        role2 = self.cog.clan_role(self.guild, self.clan2)
        
        if role1 is None or role2 is None:
            log.error(f"[{self.guild.name}] Rôles de clan manquants pour le vocal de ClanWar")
            return
        
        # Permissions : seul les 2 clans et le staff peuvent voir/joindre
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(
                view_channel=False, connect=False
            ),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=True, manage_channels=True
            ),
            role1: discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=False  # Muted par défaut
            ),
            role2: discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=False  # Muted par défaut
            ),
        }
        
        staff = resources.get_role(self.guild, "role_staff")
        if staff is not None:
            overwrites[staff] = discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=True
            )
        
        # Donner le droit de parler aux leads
        leader1 = self.guild.get_member(self.clan1.get("leader_id"))
        leader2 = self.guild.get_member(self.clan2.get("leader_id"))
        
        try:
            name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
            name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
            channel_name = f"⚔️-{_slug(name1)}-vs-{_slug(name2)}"
            
            # Limite de joueurs : size vs size
            user_limit = self.size * 2
            
            self.voice_channel = await self.guild.create_voice_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                user_limit=user_limit,
                reason=f"ClanWar: {name1} vs {name2}"
            )
            
            # Permissions spécifiques pour les leads
            if leader1:
                await self.voice_channel.set_permissions(
                    leader1,
                    speak=True,
                    reason="Lead du clan peut parler"
                )
            if leader2:
                await self.voice_channel.set_permissions(
                    leader2,
                    speak=True,
                    reason="Lead du clan peut parler"
                )
            
            log.info(f"[{self.guild.name}] Vocal créé pour ClanWar: {channel_name} (limite: {user_limit} joueurs)")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour créer le vocal de ClanWar")
        except discord.HTTPException as e:
            log.error(f"[{self.guild.name}] Erreur lors de la création du vocal de ClanWar: {e}")
    
    async def _setup_voice_permissions(self):
        """Configure les permissions vocales pour que seuls les leads puissent parler."""
        if self.voice_channel is None:
            return
        
        # Les permissions sont déjà configurées dans _create_war_voice_channel
        # Cette méthode peut être étendue pour gérer les changements dynamiques
        pass
    
    async def _preparation_timer(self):
        """Gère le timer de 15 minutes de préparation."""
        try:
            # Attendre 15 minutes
            await asyncio.sleep(900)
            
            # Le temps est écoulé, lancer la partie
            await self._start_match()
            
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Timer de ClanWar annulé")
    
    async def _send_war_notifications(self):
        """Envoie les notifications de début de ClanWar avec le nouveau format."""
        gid = self.guild_id
        
        # Calculer le temps initial pour le minuteur
        initial_remaining = self.preparation_end_time - time.time()
        initial_minutes = int(initial_remaining // 60)
        initial_seconds = int(initial_remaining % 60)
        initial_timer = t(gid, "clan.war_timer", 
                         minutes=f"{initial_minutes:02d}", seconds=f"{initial_seconds:02d}")
        
        # Notifier le clan 1
        channel1 = self.cog.clan_channel(self.guild, self.clan1)
        if channel1:
            try:
                voice_mention = self.voice_channel.mention if self.voice_channel else "@vocal"
                base_desc = t(gid, "clan.war_started_desc", voice=voice_mention)
                description = f"{base_desc}\n\n{initial_timer}"
                embed = discord.Embed(
                    title=t(gid, "clan.war_started_title"),
                    description=description,
                    color=0x000000  # Noir
                )
                # Pas de footer
                message = await channel1.send(embed=embed)
                self.notification_messages[channel1.id] = message.id
                
                # Incrémenter le compteur d'annonces
                from guild_settings import increment_clan_announcement
                increment_clan_announcement(gid, self.clan1["id"])
            except discord.HTTPException:
                pass
        
        # Notifier le clan 2
        channel2 = self.cog.clan_channel(self.guild, self.clan2)
        if channel2:
            try:
                voice_mention = self.voice_channel.mention if self.voice_channel else "@vocal"
                base_desc = t(gid, "clan.war_started_desc", voice=voice_mention)
                description = f"{base_desc}\n\n{initial_timer}"
                embed = discord.Embed(
                    title=t(gid, "clan.war_started_title"),
                    description=description,
                    color=0x000000  # Noir
                )
                # Pas de footer
                message = await channel2.send(embed=embed)
                self.notification_messages[channel2.id] = message.id
                
                # Incrémenter le compteur d'annonces
                from guild_settings import increment_clan_announcement
                increment_clan_announcement(gid, self.clan2["id"])
            except discord.HTTPException:
                pass
    
    async def _preparation_timer_with_update(self):
        """Gère le timer de 15 minutes avec mise à jour visuelle du minuteur."""
        try:
            log.info(f"[{self.guild.name}] Démarrage du timer de préparation")
            # Lancer le monitoring du vocal en parallèle
            monitoring_task = asyncio.create_task(self._monitor_voice_channel_for_leaders())
            log.info(f"[{self.guild.name}] Tâche de monitoring créée")
            
            # Mettre à jour le minuteur chaque seconde
            while time.time() < self.preparation_end_time:
                await self._update_timer_messages()
                await asyncio.sleep(1)
            
            # Temps écoulé - annuler le monitoring et vérifier si le match a commencé
            if not self.ended:
                log.info(f"[{self.guild.name}] Temps écoulé, annulation du monitoring")
                monitoring_task.cancel()
                await self._check_leader_presence_and_start()
            
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Timer de ClanWar annulé")
    
    async def _update_timer_messages(self):
        """Met à jour les messages de notification avec le temps restant."""
        remaining = self.preparation_end_time - time.time()
        if remaining <= 0:
            return
        
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    timer_text = t(self.guild_id, "clan.war_timer", 
                                  minutes=f"{minutes:02d}", seconds=f"{seconds:02d}")
                    
                    # Remplacer le minuteur existant dans la description
                    embed = message.embeds[0] if message.embeds else None
                    if embed:
                        # La description contient le timer à la fin, on le remplace
                        lines = embed.description.split('\n\n')
                        if lines and lines[-1].startswith('⏱️'):
                            # Remplacer la dernière ligne (le timer)
                            lines[-1] = timer_text
                            new_description = '\n\n'.join(lines)
                        else:
                            # Ajouter le timer s'il n'existe pas
                            new_description = embed.description + f"\n\n{timer_text}"
                        
                        new_embed = discord.Embed(
                            title=embed.title,
                            description=new_description,
                            color=embed.color
                        )
                        await message.edit(embed=new_embed)
                except discord.HTTPException:
                    pass
    
    async def _check_leader_presence_and_start(self):
        """Vérifie la présence des leaders et lance le match si présents."""
        if self.ended:
            return
        
        log.info(f"[{self.guild.name}] Vérification de la présence des leaders")
        
        # Vérifier si les leaders sont présents dans le vocal
        leader1_present = False
        leader2_present = False
        
        if self.voice_channel:
            for member in self.voice_channel.members:
                if member.id == self.clan1.get("leader_id"):
                    leader1_present = True
                    log.info(f"[{self.guild.name}] Leader 1 présent: {member.name}")
                elif member.id == self.clan2.get("leader_id"):
                    leader2_present = True
                    log.info(f"[{self.guild.name}] Leader 2 présent: {member.name}")
        
        log.info(f"[{self.guild.name}] Leaders présents: L1={leader1_present}, L2={leader2_present}")
        
        if not leader1_present or not leader2_present:
            # Annuler le ClanWar si un leader est absent
            log.warning(f"[{self.guild.name}] Un leader est absent, annulation du ClanWar")
            await self._cancel_due_to_missing_leader()
            return
        
        # Les leaders sont présents, lancer le monitoring du vocal
        log.info(f"[{self.guild.name}] Les deux leaders sont présents, lancement du monitoring")
        await self._monitor_voice_channel()
    
    async def _cancel_due_to_missing_leader(self):
        """Annule le ClanWar car un leader est absent."""
        self.ended = True
        
        # Nettoyer la session persistée
        clear_clan_war_session(self.guild_id)
        
        # Envoyer les notifications d'annulation
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = embeds.base(
                        self.guild_id,
                        description=t(self.guild_id, "clan.war_leader_missing"),
                        kind="warning"
                    )
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
        
        # Nettoyer les channels
        await self.cancel()
        
        log.info(f"[{self.guild.name}] ClanWar annulé: leader absent")
    
    async def _monitor_voice_channel_for_leaders(self):
        """Surveille le salon vocal et lance le match quand les 2 leaders sont présents et le vocal est plein."""
        log.info(f"[{self.guild.name}] === DÉBUT DU MONITORING DU VOCAL ===")
        
        if not self.voice_channel:
            log.warning(f"[{self.guild.name}] Aucun channel vocal")
            return
        
        max_players = self.size * 2  # size vs size
        log.info(f"[{self.guild.name}] Monitoring du vocal: limite={max_players}, channel={self.voice_channel.name}")
        
        try:
            while not self.ended:
                # Vérifier si les 2 leaders sont présents
                leader1_present = False
                leader2_present = False
                
                for member in self.voice_channel.members:
                    if member.id == self.clan1.get("leader_id"):
                        leader1_present = True
                    elif member.id == self.clan2.get("leader_id"):
                        leader2_present = True
                
                current_players = len(self.voice_channel.members)
                
                log.info(f"[{self.guild.name}] Leaders présents: L1={leader1_present}, L2={leader2_present}, Joueurs: {current_players}/{max_players}")
                
                # Vérifier les deux conditions : vocal plein ET leaders présents
                if leader1_present and leader2_present and current_players >= max_players:
                    # Les 2 leaders sont présents ET le vocal est plein, lancer le match
                    log.info(f"[{self.guild.name}] Conditions remplies! Lancement du match")
                    await self._start_match()
                    return
                
                # Attendre 2 secondes avant de vérifier à nouveau
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Monitoring des leaders annulé")
        except Exception as e:
            log.error(f"[{self.guild.name}] Erreur dans le monitoring: {e}")
        
        log.info(f"[{self.guild.name}] === FIN DU MONITORING DU VOCAL ===")
    
    async def _monitor_voice_channel(self):
        """Surveille le salon vocal et lance le match quand il est plein."""
        if not self.voice_channel:
            log.warning(f"[{self.guild.name}] Aucun channel vocal, lancement direct du match")
            await self._start_match()
            return
        
        max_players = self.size * 2  # size vs size
        log.info(f"[{self.guild.name}] Monitoring du vocal: limite={max_players}, channel={self.voice_channel.name}")
        
        try:
            while not self.ended:
                current_players = len(self.voice_channel.members)
                log.info(f"[{self.guild.name}] Joueurs dans le vocal: {current_players}/{max_players}")
                
                if current_players >= max_players:
                    # Le salon est plein, lancer le compte à rebours de 30 secondes
                    log.info(f"[{self.guild.name}] Salon plein! Lancement du countdown")
                    if not self.countdown_started:
                        self.countdown_started = True
                        await self._start_countdown()
                    # Le countdown gère le lancement du match, on attend qu'il se termine
                    return
                else:
                    # Attendre 5 secondes avant de vérifier à nouveau
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Monitoring du vocal annulé")
    
    async def _start_countdown(self):
        """Lance le compte à rebours de 30 secondes."""
        countdown = 30
        log.info(f"[{self.guild.name}] Countdown démarré: {countdown}s")
        
        try:
            while countdown > 0 and not self.ended:
                max_players = self.size * 2
                current_players = len(self.voice_channel.members) if self.voice_channel else 0
                
                log.info(f"[{self.guild.name}] Countdown: {countdown}s, joueurs: {current_players}/{max_players}")
                
                if current_players < max_players:
                    # Un joueur a quitté, réinitialiser le compte à rebours
                    log.warning(f"[{self.guild.name}] Joueur parti! Réinitialisation du countdown")
                    await self._notify_player_left()
                    countdown = 30
                    await asyncio.sleep(5)
                    continue
                
                # Mettre à jour le compte à rebours
                if countdown % 10 == 0 or countdown <= 5:
                    await self._send_countdown_update(countdown)
                
                await asyncio.sleep(1)
                countdown -= 1
            
            if countdown <= 0 and not self.ended:
                # Le compte à rebours est terminé, lancer le match
                log.info(f"[{self.guild.name}] Countdown terminé, lancement du match")
                await self._start_match()
        
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Compte à rebours annulé")
    
    async def _notify_player_left(self):
        """Notifie qu'un joueur a quitté le vocal."""
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = embeds.base(
                        self.guild_id,
                        description=t(self.guild_id, "clan.war_player_left"),
                        kind="warning"
                    )
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
    
    async def _send_countdown_update(self, countdown):
        """Envoie une mise à jour du compte à rebours."""
        if countdown == 30:
            message = t(self.guild_id, "clan.war_full_warning")
        elif countdown <= 5:
            message = t(self.guild_id, "clan.war_starting")
        else:
            return
        
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = embeds.base(
                        self.guild_id,
                        description=message,
                        kind="success"
                    )
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
    
    async def _start_match(self):
        """Lance la partie après la période de préparation."""
        log.info(f"[{self.guild.name}] === DÉBUT DE _start_match ===")
        
        if self.ended:
            log.warning(f"[{self.guild.name}] Match déjà terminé, annulation")
            return
        
        self.ended = True
        
        # Nettoyer la session persistée car la phase de préparation est terminée
        log.info(f"[{self.guild.name}] Nettoyage de la session persistée")
        clear_clan_war_session(self.guild_id)
        
        # Envoyer un message pour dire que le match est lancé
        log.info(f"[{self.guild.name}] Envoi de la notification de démarrage")
        await self._send_match_started_notification()
        
        # Créer les channels vocaux séparés pour chaque équipe (déplace les joueurs)
        log.info(f"[{self.guild.name}] Création des channels vocaux d'équipe")
        await self._create_team_voice_channels()
        
        # Le bot rejoint le vocal pour annoncer que le match va commencer
        log.info(f"[{self.guild.name}] Tentative de rejoindre le vocal pour annoncer le début")
        await self._bot_voice_announce()
        
        # Attendre 15 secondes avant de déplacer les joueurs
        log.info(f"[{self.guild.name}] Attente de 15 secondes avant le déplacement des joueurs")
        await asyncio.sleep(15)
        
        # Déplacer les membres du vocal de préparation vers leurs vocaux d'équipe
        log.info(f"[{self.guild.name}] Déplacement des joueurs vers leurs vocaux d'équipe")
        if self.voice_channel:
            for member in self.voice_channel.members:
                if member.id in self.clan1.get("members", []):
                    try:
                        await member.move_to(self.team_channels["team1"])
                        log.info(f"[{self.guild.name}] {member.name} déplacé vers {self.team_channels['team1'].name}")
                    except discord.HTTPException:
                        pass
                elif member.id in self.clan2.get("members", []):
                    try:
                        await member.move_to(self.team_channels["team2"])
                        log.info(f"[{self.guild.name}] {member.name} déplacé vers {self.team_channels['team2'].name}")
                    except discord.HTTPException:
                        pass
        
        # Attendre 15 secondes avant de déplacer les joueurs
        log.info(f"[{self.guild.name}] Attente de 15 secondes avant le déplacement des joueurs")
        await asyncio.sleep(15)
        
        # Déplacer les membres du vocal de préparation vers leurs vocaux d'équipe
        log.info(f"[{self.guild.name}] Déplacement des joueurs vers leurs vocaux d'équipe")
        if self.voice_channel:
            for member in self.voice_channel.members:
                if member.id in self.clan1.get("members", []):
                    try:
                        await member.move_to(self.team_channels["team1"])
                        log.info(f"[{self.guild.name}] {member.name} déplacé vers {self.team_channels['team1'].name}")
                    except discord.HTTPException:
                        pass
                elif member.id in self.clan2.get("members", []):
                    try:
                        await member.move_to(self.team_channels["team2"])
                        log.info(f"[{self.guild.name}] {member.name} déplacé vers {self.team_channels['team2'].name}")
                    except discord.HTTPException:
                        pass
        
        # Créer le channel textuel avec le nouveau système de points
        log.info(f"[{self.guild.name}] Création du channel textuel")
        await self._create_match_text_channel()
        
        # Lancer la surveillance des leaders pour le timeout
        log.info(f"[{self.guild.name}] Lancement de la surveillance des leaders")
        self.leader_timeout_task = asyncio.create_task(self._monitor_leader_timeout())
        
        log.info(f"[{self.guild.name}] ClanWar lancé: {self.clan1.get('name')} vs {self.clan2.get('name')}")
        log.info(f"[{self.guild.name}] === FIN DE _start_match ===")
    
    async def _send_match_started_notification(self):
        """Envoie une notification que le match est lancé."""
        gid = self.guild_id
        name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
        name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
        
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = discord.Embed(
                        title=t(gid, "clan.war_start_title"),
                        description=t(gid, "clan.war_start_desc",
                                     clan1=name1, clan2=name2, size=self.size),
                        color=0x000000  # Rouge
                    )
                    # Pas de footer
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
    
    async def _create_team_voice_channels(self):
        """Crée des channels vocaux séparés pour chaque équipe et y déplace les joueurs."""
        category = resources.get_category(self.guild, "category_clan")
        if category is None:
            log.error(f"[{self.guild.name}] Pas de catégorie clan pour créer les vocaux d'équipe")
            return
        
        # Récupérer les rôles des 2 clans
        role1 = self.cog.clan_role(self.guild, self.clan1)
        role2 = self.cog.clan_role(self.guild, self.clan2)
        
        if role1 is None or role2 is None:
            log.error(f"[{self.guild.name}] Rôles de clan manquants pour les vocaux d'équipe")
            return
        
        try:
            name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
            name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
            
            # Créer le vocal pour l'équipe 1
            overwrites1 = {
                self.guild.default_role: discord.PermissionOverwrite(
                    view_channel=False, connect=False
                ),
                self.guild.me: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True, manage_channels=True
                ),
                role1: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                ),
            }
            
            staff = resources.get_role(self.guild, "role_staff")
            if staff is not None:
                overwrites1[staff] = discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                )
            
            channel1 = await self.guild.create_voice_channel(
                name=f"🎮-{_slug(name1)}",
                category=category,
                overwrites=overwrites1,
                user_limit=self.size,
                reason=f"ClanWar: Équipe {name1}"
            )
            self.team_channels["team1"] = channel1
            log.info(f"[{self.guild.name}] Vocal créé pour l'équipe 1: {channel1.name}")
            
            # Créer le vocal pour l'équipe 2
            overwrites2 = {
                self.guild.default_role: discord.PermissionOverwrite(
                    view_channel=False, connect=False
                ),
                self.guild.me: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True, manage_channels=True
                ),
                role2: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                ),
            }
            
            if staff is not None:
                overwrites2[staff] = discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                )
            
            channel2 = await self.guild.create_voice_channel(
                name=f"🎮-{_slug(name2)}",
                category=category,
                overwrites=overwrites2,
                user_limit=self.size,
                reason=f"ClanWar: Équipe {name2}"
            )
            self.team_channels["team2"] = channel2
            log.info(f"[{self.guild.name}] Vocal créé pour l'équipe 2: {channel2.name}")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour créer les vocaux d'équipe")
        except discord.HTTPException as e:
            log.error(f"[{self.guild.name}] Erreur lors de la création des vocaux d'équipe: {e}")
    
    async def _monitor_leader_timeout(self):
        """Surveille quand un leader quitte le vocal et lance un timer de 10 minutes."""
        log.info(f"[{self.guild.name}] === DÉBUT SURVEILLANCE TIMEOUT LEADER ===")
        
        try:
            while not self.ended:
                # Vérifier si les leaders sont dans n'importe quel vocal
                leader1_in_voice = False
                leader2_in_voice = False
                
                # Vérifier dans tous les vocaux du serveur
                for channel in self.guild.voice_channels:
                    for member in channel.members:
                        if member.id == self.clan1.get("leader_id"):
                            leader1_in_voice = True
                        elif member.id == self.clan2.get("leader_id"):
                            leader2_in_voice = True
                
                log.info(f"[{self.guild.name}] Leaders en vocal: L1={leader1_in_voice}, L2={leader2_in_voice}")
                
                # Si un leader n'est pas en vocal
                if not leader1_in_voice or not leader2_in_voice:
                    # Déterminer quel leader est absent
                    absent_leader = "clan1" if not leader1_in_voice else "clan2"
                    
                    # Si ce n'est pas déjà enregistré
                    if self.leader_left_which is None:
                        self.leader_left_which = absent_leader
                        self.leader_left_time = time.time()
                        log.warning(f"[{self.guild.name}] Leader {absent_leader} a quitté le vocal! Timer de 10min lancé")
                    
                    # Vérifier si 10 minutes se sont écoulées
                    if time.time() - self.leader_left_time >= 600:  # 10 minutes = 600 secondes
                        log.warning(f"[{self.guild.name}] Timeout de 10 minutes écoulé! Victoire par abandon")
                        await self._declare_winner_by_timeout()
                        return
                else:
                    # Les deux leaders sont en vocal, réinitialiser le timer
                    if self.leader_left_which is not None:
                        log.info(f"[{self.guild.name}] Leaders revenus, timer réinitialisé")
                        self.leader_left_which = None
                        self.leader_left_time = None
                
                # Attendre 10 secondes avant de vérifier à nouveau
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Surveillance timeout leader annulée")
        except Exception as e:
            log.error(f"[{self.guild.name}] Erreur dans la surveillance timeout: {e}")
        
        log.info(f"[{self.guild.name}] === FIN SURVEILLANCE TIMEOUT LEADER ===")
    
    async def _declare_winner_by_timeout(self):
        """Déclare le vainqueur par timeout du leader adverse."""
        if self.leader_left_which == "clan1":
            winner = self.clan2
            loser = self.clan1
        else:
            winner = self.clan1
            loser = self.clan2
        
        winner_name = sanitize(winner.get("name", "?"), MAX_CLAN_NAME)
        loser_name = sanitize(loser.get("name", "?"), MAX_CLAN_NAME)
        
        log.info(f"[{self.guild.name}] Victoire par abandon: {winner_name} gagne contre {loser_name}")
        
        # Notifier les deux clans
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = discord.Embed(
                        title=t(self.guild_id, "clan.war_timeout_title"),
                        description=t(self.guild_id, "clan.war_timeout_desc", winner=winner_name, loser=loser_name),
                        color=0x000000
                    )
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
        
        # Terminer la session
        await self.cancel()
    
    async def _bot_voice_announce(self):
        """Le bot rejoint le vocal et annonce le début de la partie."""
        if self.voice_channel is None:
            log.warning(f"[{self.guild.name}] Aucun channel vocal pour l'annonce")
            return
        
        try:
            log.info(f"[{self.guild.name}] Tentative de connexion au vocal: {self.voice_channel.name}")
            # Connecter le bot au vocal
            voice_client = await self.voice_channel.connect()
            
            # Jouer l'annonce vocale
            from cogs.queue_config import voice_announce_path
            voice_file = voice_announce_path(self.guild_id)
            
            if os.path.exists(voice_file):
                audio_source = discord.FFmpegPCMAudio(voice_file)
                voice_client.play(audio_source)
                
                # Attendre que l'audio soit terminé
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)
            else:
                log.warning(f"[{self.guild.name}] Fichier audio non trouvé: {voice_file}")
            
            # Se déconnecter après l'annonce
            await voice_client.disconnect()
            
            log.info(f"[{self.guild.name}] Annonce vocale terminée pour ClanWar")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour rejoindre le vocal")
        except Exception as e:
            log.error(f"[{self.guild.name}] Erreur lors de l'annonce vocale: {e}")
    
    async def _create_match_text_channel(self):
        """Crée un channel textuel pour le match avec le système de points et de vote de manche."""
        category = resources.get_category(self.guild, "category_clan")
        if category is None:
            log.error(f"[{self.guild.name}] Pas de catégorie clan pour créer le channel de match")
            return
        
        # Récupérer les rôles des 2 clans
        role1 = self.cog.clan_role(self.guild, self.clan1)
        role2 = self.cog.clan_role(self.guild, self.clan2)
        
        if role1 is None or role2 is None:
            log.error(f"[{self.guild.name}] Rôles de clan manquants pour le channel de match")
            return
        
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_messages=True
            ),
            role1: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            role2: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        
        staff = resources.get_role(self.guild, "role_staff")
        if staff is not None:
            overwrites[staff] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )
        
        try:
            name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
            name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
            channel_name = f"🎮-{_slug(name1)}-vs-{_slug(name2)}"
            
            self.captain_vote_channel = await self.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Match ClanWar: {name1} vs {name2}"
            )
            
            # Envoyer le message de début avec le système de points
            embed = discord.Embed(
                title=f"🛡️ {name1} vs {name2}",
                description=t(self.guild_id, "clan.war_points_desc", clan1=name1, clan2=name2, points1=self.clan1_points, points2=self.clan2_points),
                color=0x000000
            )
            
            self.main_embed_message = await self.captain_vote_channel.send(embed=embed, view=ClanWarActionView(self))
            
            log.info(f"[{self.guild.name}] Channel de match créé: {channel_name}")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour créer le channel de match")
        except discord.HTTPException as e:
            log.error(f"[{self.guild.name}] Erreur lors de la création du channel de match: {e}")
    
    async def _create_empty_channel(self):
        """Crée un channel vide si l'option capitaine est désactivée."""
        category = resources.get_category(self.guild, "category_clan")
        if category is None:
            return
        
        # Récupérer les rôles des 2 clans
        role1 = self.cog.clan_role(self.guild, self.clan1)
        role2 = self.cog.clan_role(self.guild, self.clan2)
        
        if role1 is None or role2 is None:
            return
        
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_messages=True
            ),
            role1: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            role2: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        
        staff = resources.get_role(self.guild, "role_staff")
        if staff is not None:
            overwrites[staff] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )
        
        try:
            name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
            name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
            channel_name = f"🎮-{_slug(name1)}-vs-{_slug(name2)}"
            
            self.captain_vote_channel = await self.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"ClanWar: {name1} vs {name2}"
            )
            
            # Envoyer un message simple
            await self.captain_vote_channel.send(
                embed=embeds.base(
                    self.guild_id,
                    title=t(self.guild_id, "clan.war_start_title"),
                    description=t(self.guild_id, "clan.war_start_desc",
                                 clan1=name1, clan2=name2, size=self.size),
                    kind="success"
                )
            )
            
            log.info(f"[{self.guild.name}] Channel vide créé pour ClanWar: {channel_name}")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour créer le channel")
        except discord.HTTPException as e:
            log.error(f"[{self.guild.name}] Erreur lors de la création du channel: {e}")
    
    async def forfeit(self, leader_id: int) -> None:
        """Abandon demandé par le chef d'un des deux clans : l'autre clan gagne."""
        if self.ended:
            return
        if leader_id == self.clan1.get("leader_id"):
            loser, winner = self.clan1, self.clan2
        else:
            loser, winner = self.clan2, self.clan1
        winner_name = sanitize(winner.get("name", "?"), MAX_CLAN_NAME)
        loser_name = sanitize(loser.get("name", "?"), MAX_CLAN_NAME)
        log.info(f"[{self.guild.name}] ClanWar abandonné par {loser_name} : victoire de {winner_name}")
        embed = discord.Embed(
            title=t(self.guild_id, "clan.war_forfeit_title"),
            description=t(self.guild_id, "clan.war_forfeit_desc", winner=winner_name, loser=loser_name),
            color=0x000000,
        )
        # Les clés deviennent des chaînes quand la session est relue depuis le disque.
        for channel_id in list(self.notification_messages):
            channel = self.guild.get_channel(int(channel_id))
            if channel is None:
                continue
            try:
                await channel.send(embed=embed)
            except discord.HTTPException as e:
                log.warning(f"[{self.guild.name}] Annonce d'abandon non envoyée : {e}")
        await self.cancel()
        active = getattr(self.cog, "active_war_sessions", None)
        if isinstance(active, dict):
            active.pop(str(self.guild_id), None)

    async def cancel(self):
        """Annule la session de ClanWar."""
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
        if self.countdown_task and not self.countdown_task.done():
            self.countdown_task.cancel()
        if self.leader_timeout_task and not self.leader_timeout_task.done():
            self.leader_timeout_task.cancel()
        
        self.ended = True
        
        # Nettoyer les channels créés
        if self.voice_channel:
            try:
                await self.voice_channel.delete(reason="ClanWar annulé")
            except discord.HTTPException:
                pass
        
        for channel in self.team_channels.values():
            if channel:
                try:
                    await channel.delete(reason="ClanWar annulé")
                except discord.HTTPException:
                    pass
        
        if self.captain_vote_channel:
            try:
                await self.captain_vote_channel.delete(reason="ClanWar annulé")
            except discord.HTTPException:
                pass
        
        # Nettoyer la session persistée
        clear_clan_war_session(self.guild_id)
        
        log.info(f"[{self.guild.name}] ClanWar annulé: {self.clan1.get('name')} vs {self.clan2.get('name')}")


class ClanWarActionView(discord.ui.View):
    """Boutons d'action pour le ClanWar (Manche, Abandonné, Problème)."""
    
    def __init__(self, session: "ClanWarSession"):
        super().__init__(timeout=None)
        self.session = session
        gid = session.guild_id
        self.round.label = t(gid, "clan.war_btn_round")
        self.abandon.label = t(gid, "clan.war_btn_abandon")
        self.problem.label = t(gid, "clan.war_btn_problem")
    
    @discord.ui.button(label="Manche", style=discord.ButtonStyle.secondary, emoji="🏴", custom_id="cyq:clanwar:round")
    async def round(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Lance le vote pour la manche."""
        session = self.session
        gid = interaction.guild_id
        
        # Vérifier que c'est un membre d'un clan
        user = interaction.user
        if user.id not in session.clan1.get("members", []) and user.id not in session.clan2.get("members", []):
            await interaction.response.send_message(t(gid, "clan.war_err_member_vote"), ephemeral=True)
            return
        
        # Ouvrir le modal de vote de manche
        await interaction.response.send_message(
            embed=discord.Embed(
                title=t(gid, "clan.war_round_vote_title"),
                description=t(gid, "clan.war_round_vote_desc"),
                color=0x000000
            ),
            view=RoundVoteView(session),
            ephemeral=True
        )
    
    @discord.ui.button(label="Abandonné", style=discord.ButtonStyle.secondary, emoji="🏳", custom_id="cyq:clanwar:abandon")
    async def abandon(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """L'abandon du ClanWar."""
        session = self.session
        gid = interaction.guild_id
        
        # Vérifier que c'est un leader
        user = interaction.user
        if user.id != session.clan1.get("leader_id") and user.id != session.clan2.get("leader_id"):
            await interaction.response.send_message(t(gid, "clan.err_leader_only"), ephemeral=True)
            return
        
        # Confirmer l'abandon
        await interaction.response.send_message(
            embed=embeds.base(gid, description=t(gid, "clan.war_abandon_confirm"), kind="warning"),
            view=AbandonConfirmView(session, user.id),
            ephemeral=True
        )
    
    @discord.ui.button(label="Problème", style=discord.ButtonStyle.secondary, emoji="⚠️", custom_id="cyq:clanwar:problem")
    async def problem(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Signale un problème au staff via ticket."""
        session = self.session
        gid = interaction.guild_id
        
        # Vérifier que c'est un membre d'un clan
        user = interaction.user
        if user.id not in session.clan1.get("members", []) and user.id not in session.clan2.get("members", []):
            await interaction.response.send_message(t(gid, "clan.war_err_member_problem"), ephemeral=True)
            return
        
        # Vérifier si le système de ticket est configuré
        from guild_settings import get_ticket_config
        ticket_config = get_ticket_config(gid)
        log.info(f"[{session.guild.name}] Vérification ticket: config={ticket_config}, enabled={ticket_config.get('enabled', False) if ticket_config else None}")
        
        if not ticket_config or not ticket_config.get("enabled", False):
            await interaction.response.send_message(
                t(gid, "clan.ticket_disabled"),
                ephemeral=True
            )
            return
        
        # Ouvrir le modal de ticket
        await interaction.response.send_modal(TicketProblemModal(session))


class AbandonConfirmView(discord.ui.View):
    """Confirmation de l'abandon d'un ClanWar, réservée au chef qui l'a demandé.

    Le bouton « Abandonné » ouvrait cette vue alors qu'elle n'existait nulle
    part : le clic plantait et aucun clan ne pouvait abandonner."""

    def __init__(self, session: "ClanWarSession", leader_id: int):
        super().__init__(timeout=60)
        self.session = session
        self.leader_id = leader_id
        gid = session.guild_id
        self.confirm.label = t(gid, "clan.war_abandon_yes")
        self.keep_playing.label = t(gid, "clan.war_abandon_no")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.leader_id:
            return True
        await interaction.response.send_message(t(interaction.guild_id, "clan.err_leader_only"), ephemeral=True)
        return False

    @discord.ui.button(label="Abandonner", style=discord.ButtonStyle.danger, emoji="🏳")
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        gid = interaction.guild_id
        if self.session.ended:
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=t(gid, "clan.war_gone"), kind="error"), view=None)
            return
        await interaction.response.edit_message(
            embed=embeds.base(gid, description=t(gid, "clan.war_abandon_done"), kind="warning"), view=None)
        await self.session.forfeit(self.leader_id)

    @discord.ui.button(label="Continuer", style=discord.ButtonStyle.secondary)
    async def keep_playing(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        gid = interaction.guild_id
        await interaction.response.edit_message(
            embed=embeds.base(gid, description=t(gid, "clan.war_abandon_cancelled"), kind="brand"), view=None)



class RoundVoteView(discord.ui.View):
    """View pour voter quelle équipe a gagné la manche."""
    
    def __init__(self, session: "ClanWarSession"):
        super().__init__(timeout=None)
        self.session = session
        # Les boutons portent le nom des clans plutôt que « Clan 1 » / « Clan 2 ».
        self.vote_clan1.label = sanitize(session.clan1.get("name", "?"), MAX_CLAN_NAME)[:80]
        self.vote_clan2.label = sanitize(session.clan2.get("name", "?"), MAX_CLAN_NAME)[:80]
    
    @discord.ui.button(label="Clan 1", style=discord.ButtonStyle.primary)
    async def vote_clan1(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Vote pour le clan 1."""
        await self._record_vote(interaction, "clan1")
    
    @discord.ui.button(label="Clan 2", style=discord.ButtonStyle.primary)
    async def vote_clan2(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Vote pour le clan 2."""
        await self._record_vote(interaction, "clan2")
    
    async def _record_vote(self, interaction: discord.Interaction, clan_choice: str) -> None:
        """Enregistre le vote et affiche les résultats."""
        session = self.session
        user = interaction.user
        
        # Vérifier si l'utilisateur a déjà voté
        if user.id in session.round_votes:
            await interaction.response.send_message(t(session.guild_id, "clan.war_err_already_voted"), ephemeral=True)
            return
        
        # Enregistrer le vote
        session.round_votes[user.id] = clan_choice
        
        # Compter les votes
        clan1_votes = sum(1 for v in session.round_votes.values() if v == "clan1")
        clan2_votes = sum(1 for v in session.round_votes.values() if v == "clan2")
        
        # Déterminer le gagnant
        winner = "clan1" if clan1_votes > clan2_votes else "clan2"
        
        # Mettre à jour les points
        if winner == "clan1":
            session.clan1_points += 1
        else:
            session.clan2_points += 1
        
        # Créer le message de résultats temporaire
        name1 = sanitize(session.clan1.get("name", "?"), MAX_CLAN_NAME)
        name2 = sanitize(session.clan2.get("name", "?"), MAX_CLAN_NAME)
        
        vote_list = []
        for user_id, choice in session.round_votes.items():
            member = session.guild.get_member(user_id)
            if member:
                clan_name = name1 if choice == "clan1" else name2
                vote_list.append(t(session.guild_id, "clan.war_vote_line", player=member.mention, clan=clan_name))
        
        result_embed = discord.Embed(
            title=t(session.guild_id, "clan.war_round_result_title"),
            description=t(session.guild_id, "clan.war_round_result_desc", clan1=name1, votes1=clan1_votes, clan2=name2, votes2=clan2_votes),
            color=0x000000
        )
        
        if vote_list:
            result_embed.add_field(name=t(session.guild_id, "clan.war_votes_field"), value="\n".join(vote_list))
        
        await interaction.response.edit_message(
            embed=result_embed,
            view=None
        )
        
        # Mettre à jour le message principal avec les nouveaux points (éditer le message existant)
        if session.main_embed_message:
            main_embed = discord.Embed(
                title=f"🛡️ {name1} vs {name2}",
                description=t(session.guild_id, "clan.war_points_desc", clan1=name1, clan2=name2, points1=session.clan1_points, points2=session.clan2_points),
                color=0x000000
            )
            # Réinitialiser les votes pour la prochaine manche
            session.round_votes = {}
            
            # Éditer le message principal existant
            await session.main_embed_message.edit(embed=main_embed, view=ClanWarActionView(session))


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
        from guild_settings import get_ticket_config
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
            color=0x000000
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
                color=0x000000
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
        self.bot.add_view(WarAnswerView(self))
        
        # Restaurer les sessions de ClanWar actives
        await self._restore_war_sessions()
        
        # Lancer la tâche de vérification des channels de liaison
        self._liaison_check_task = self.bot.loop.create_task(self._check_clan_liaison_channels())
    
    async def cog_unload(self) -> None:
        """Déchargement du cog : annule la tâche de fond et réinitialise les channels."""
        if hasattr(self, "_liaison_check_task"):
            self._liaison_check_task.cancel()
        
        # Réinitialiser tous les channels de liaison quand le bot se déconnecte
        for guild in self.bot.guilds:
            try:
                clans = get_clans(guild.id)
                for clan in clans.values():
                    await self._reset_clan_liaison_channel(guild, clan)
            except Exception as e:
                log.error(f"Erreur lors de la réinitialisation des channels pour {guild.name}: {e}")
        
        # Réinitialiser tous les compteurs d'annonces
        from guild_settings import reset_all_clan_announcements
        for guild in self.bot.guilds:
            try:
                reset_all_clan_announcements(guild.id)
            except Exception as e:
                log.error(f"Erreur lors de la réinitialisation des compteurs pour {guild.name}: {e}")
    
    @app_commands.command(name="cw", description="Activer ou désactiver le système de ClanWar")
    @app_commands.default_permissions(administrator=True)
    async def cw(self, interaction: discord.Interaction, enabled: bool):
        """Active ou désactive le système de ClanWar."""
        gid = interaction.guild_id
        
        # Mettre à jour le statut du ClanWar
        set_features(gid, clan_wars=enabled)
        
        # Message de confirmation
        if enabled:
            await interaction.response.send_message(
                embed=embeds.base(gid, description=t(gid, "clan.cw_enabled"), kind="success")
            )
        else:
            await interaction.response.send_message(
                embed=embeds.base(gid, description=t(gid, "clan.cw_disabled"), kind="warning")
            )
    
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
        import asyncio
        from guild_settings import get_clan_announcement_count
        
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
        """Rôle de chef et tag de clan dans le pseudo.

        Le rôle n'est **pas créé** : c'est celui que l'administrateur a
        désigné dans `/option → Rôle`. Sans désignation, le clan existe
        quand même — on le dit, on ne bloque pas. Chaque échec renvoie une
        ligne d'explication plutôt qu'un silence : « le bot n'a rien fait »
        sans raison est le pire des retours."""
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
        """Retire le rôle et le tag quand on quitte ou dissout.

        Le pseudo n'est remis à zéro que s'il porte bien le tag de CE clan :
        écraser un pseudo choisi par le membre serait une intrusion."""
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
        """Crée le rôle du clan et son salon privé, puis y publie la fiche.

        Chaque échec renvoie une ligne d'explication et laisse le clan
        exister : un clan sans salon reste un clan."""
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

        card = await channel.send(embed=self.space_embed(gid, clan))
        # Un message qui ne porte que des boutons : l'espace invisible est le
        # seul contenu accepté par Discord pour un message sans texte.
        await channel.send(content=embeds.BLANK, view=ClanSpaceView(self))
        set_clan_fields(gid, clan["id"], channel_id=channel.id,
                        role_id=role.id if role else None, card_message_id=card.id)
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
            import asyncio
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
            from guild_settings import reset_clan_announcement
            reset_clan_announcement(gid, clan_id)
            
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Erreur lors de la réinitialisation du channel de liaison: {e}")

    def space_embed(self, guild_id: int, clan: dict) -> discord.Embed:
        """La fiche affichée dans le salon du clan.

        Elle reprend la fiche habituelle et ajoute ce qui n'a de sens que
        chez soi : depuis quand le clan existe."""
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
                card = await channel.send(embed=self.space_embed(guild.id, clan))
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
        
        # Vérifier si le système de ClanWar est activé
        features = get_features(gid)
        if not features or not features.get("clan_wars", False):
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=t(gid, "clan.war_system_disabled"), kind="error"),
                view=None)
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
    
    def _clear_old_war_requests(self, guild_id: int, clan_id: str) -> None:
        """Supprime toutes les anciennes demandes de wars d'un clan."""
        try:
            from guild_settings import get_clan_requests
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
            from guild_settings import set_clan_fields
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
        """Annonce une demande d'adhésion dans le salon du clan.

        Sans annonce, la demande dort derrière le bouton **Invites** : rien
        n'invite le chef à aller regarder. Certains serveurs préfèrent ce
        silence, d'où l'interrupteur de `/option → Clan`. On mentionne le chef
        seul, et pas le rôle du clan — c'est lui qui décide, prévenir tout le
        monde serait du bruit."""
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
        """Republie le classement dès qu'un clan bouge.

        Sans ça, le classement des clans n'apparaîtrait qu'à la fin de la
        partie suivante — un clan créé le matin resterait invisible tout le
        jour."""
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
