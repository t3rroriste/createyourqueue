"""
Cog : Duel
==========
Commandes : /duel, /createteam, /config-duel

Des duels entre **teams éphémères**, sans passer par un clan.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import discord
from discord import app_commands
from discord.ext import commands

import custom_emojis
import embeds
from cogs.queue_config import COLOR_PALETTE, color_name, voice_announce_path
from guild_settings import (
    MAX_TEAM_NAME, MAX_TEAM_SIZE,
    accept_duel_invite, add_duel_request, add_duel_trash, cancel_duel_trash, clan_named,
    consume_duel, create_duel_team, delete_duel_session, delete_duel_team,
    duel_session_of_team, duel_team_named, duel_team_of, get_duel_config,
    get_duel_request, get_duel_requests, get_duel_sessions, get_duel_team,
    get_duel_teams, leave_duel_team, next_duel_number, pending_duel_request,
    pop_due_duel_trash, remove_duel_request, remove_duel_requests_of_team,
    save_duel_session, set_duel_config, set_duel_team_fields,
    duel_history_game_by_message, get_duel_history, save_duel_history,
)
from i18n import get_lang, t
from rate_limit import throttled_each
from text_safety import NO_PINGS, USERS_ONLY, sanitize

log = logging.getLogger("bot.duel")

# Couleur d'embed de chaque pastille de la palette des queues : une team garde
# la même couleur dans sa fiche, son vocal et ses défis.
TEAM_COLORS = {
    "🔴": 0xED4245, "🔵": 0x3498DB, "🟢": 0x57F287, "🟡": 0xFEE75C,
    "🟣": 0x9B59B6, "🟠": 0xE67E22, "⚪": 0xFFFFFF, "⚫": 0x23272A,
    "🟤": 0x8B5A2B, "🩷": 0xFF69B4, "🩵": 0x5BC0EB, "🟦": 0x1F3A93,
}

LIFETIMES = (1, 3, 5, 0)  # nombre de duels d'une team ; 0 = illimité

MAX_ROUNDS = 15         # rounds d'un duel, choisis dans /duel

JOIN_TIMEOUT = 10 * 60   # pour rejoindre duel-01 une fois le défi accepté
REQUEST_TTL = 30 * 60    # un défi sans réponse
INVITE_TTL = 30 * 60     # une invitation de team sans réponse
EMPTY_GRACE = 60         # vocaux vides depuis tant de secondes : duel fini
THREAD_GRACE = 5 * 60    # le temps de lire le dernier message d'un fil
WATCH_EVERY = 20         # la ronde rattrape ce qu'aucun événement n'a signalé
MAX_ACTIVE_DUELS = 20
ANNOUNCE_MAX_SECONDS = 30

# Permissions du bot, vérifiées et affichées par /config-duel.
CATEGORY_PERMS = ("view_channel", "manage_channels", "manage_roles",
                  "move_members", "connect", "speak")
CHANNEL_PERMS = ("view_channel", "send_messages", "read_message_history",
                 "create_private_threads", "send_messages_in_threads", "manage_threads")

# Annonce vocale du début d'un duel, une par langue, générée avec gTTS (comme
# les traductions de l'annonce de queue).
DUEL_ANNOUNCE_FILES = {
    "fr": "duel_announce_fr.mp3",
    "en": "duel_announce_en.mp3",
    "es": "duel_announce_es.mp3",
    "de": "duel_announce_de.mp3",
    "ko": "duel_announce_ko.mp3",
}


def duel_announce_path(guild_id: int | None) -> str:
    """Annonce du duel dans la langue du serveur, repli sur celle des queues."""
    path = DUEL_ANNOUNCE_FILES.get(get_lang(guild_id), DUEL_ANNOUNCE_FILES["fr"])
    return path if os.path.exists(path) else voice_announce_path(guild_id)


# ----------------------------------------------------------------------
# Textes et embeds
# ----------------------------------------------------------------------
def team_name(team: dict) -> str:
    return sanitize(team.get("name", "?"), MAX_TEAM_NAME)


def team_label(team: dict) -> str:
    return f"{team.get('color', '⚪')} **{team_name(team)}**"


def roster(member_ids: list[int], leader_id: int | None) -> str:
    """Le lead en tête, couronné : c'est à lui qu'on s'adresse."""
    lines = [f"👑 <@{leader_id}>"] if leader_id in member_ids else []
    lines += [f"• <@{uid}>" for uid in member_ids if uid != leader_id]
    return "\n".join(lines) or "—"


def lifetime_label(guild_id: int | None, duels: int) -> str:
    return t(guild_id, "duel.life_unlimited") if not duels else t(guild_id, "duel.life_count", count=duels)


def lifetime_text(guild_id: int | None, team: dict) -> str:
    total = int(team.get("duels_total") or 0)
    if not total:
        return t(guild_id, "duel.life_unlimited")
    return t(guild_id, "duel.life_left", left=team.get("duels_left", total), total=total)


def challenge_error(guild_id: int, team: dict | None, target: dict | None,
                    user_id: int | None) -> str | None:
    """Pourquoi ce défi est impossible (clé de traduction), ou None."""
    if team is None:
        return "duel.err_no_team"
    if team.get("leader_id") != user_id:
        return "duel.err_lead_only"
    if team.get("status") != "ready":
        return "duel.err_team_pending"
    if target is None:
        return "duel.err_target_gone"
    if target["id"] == team["id"]:
        return "duel.err_self"
    if target.get("status") != "ready":
        return "duel.err_target_pending"
    if len(team["members"]) != len(target["members"]):
        return "duel.err_size"
    if duel_session_of_team(guild_id, team["id"]):
        return "duel.err_in_duel"
    if duel_session_of_team(guild_id, target["id"]):
        return "duel.err_target_in_duel"
    if len(get_duel_sessions(guild_id)) >= MAX_ACTIVE_DUELS or not next_duel_number(guild_id):
        return "duel.err_too_many"
    return None


def error_text(guild_id: int | None, key: str, team: dict | None = None,
               target: dict | None = None) -> str:
    """Toutes les variables possibles d'un message d'erreur, toujours fournies :
    une variable manquante afficherait le texte brut avec ses accolades."""
    return t(guild_id, key,
             mine=len(team["members"]) if team else 0,
             theirs=len(target["members"]) if target else 0,
             name=team_name(target) if target else "?",
             max=MAX_TEAM_SIZE)


def team_embed(guild_id: int, team: dict, *, title_key: str = "duel.team_title") -> discord.Embed:
    """La fiche d'une team : joueurs, durée, invités en attente."""
    embed = embeds.base(guild_id, title=t(guild_id, title_key, name=team_name(team)),
                        footer=t(guild_id, "duel.team_footer"))
    embed.color = TEAM_COLORS.get(team.get("color"), embeds.BRAND)
    embed.add_field(name=t(guild_id, "duel.field_players", count=len(team.get("members", []))),
                    value=roster(team.get("members", []), team.get("leader_id")), inline=True)
    embed.add_field(name=t(guild_id, "duel.field_lifetime"), value=lifetime_text(guild_id, team), inline=True)
    if team.get("invited"):
        embed.add_field(name=t(guild_id, "duel.field_invited"),
                        value="\n".join(f"⏳ <@{uid}>" for uid in team["invited"]), inline=False)
    return embed


def invite_embed(guild_id: int, team: dict) -> discord.Embed:
    embed = embeds.base(
        guild_id,
        title=t(guild_id, "duel.inv_title", name=team_name(team)),
        description=t(guild_id, "duel.inv_desc", leader=f"<@{team['leader_id']}>", team=team_label(team)),
        footer=t(guild_id, "duel.inv_footer", minutes=INVITE_TTL // 60),
    )
    embed.color = TEAM_COLORS.get(team.get("color"), embeds.BRAND)
    invited = team.get("invited", [])
    lines = [f"✅ <@{uid}>" for uid in team["members"]] + [f"⏳ <@{uid}>" for uid in invited]
    embed.add_field(name=t(guild_id, "duel.field_players", count=len(team["members"]) + len(invited)),
                    value="\n".join(lines), inline=True)
    embed.add_field(name=t(guild_id, "duel.field_lifetime"), value=lifetime_text(guild_id, team), inline=True)
    return embed


def rounds_value(rounds) -> str:
    return f"**{max(1, int(rounds or 1))}**"


def request_embed(guild_id: int, team: dict, target: dict, rounds: int = 1) -> discord.Embed:
    """Le défi, tel que le lead défié le reçoit : qui, avec quels joueurs, en
    combien de rounds."""
    size = len(team["members"])
    embed = embeds.base(
        guild_id,
        title=t(guild_id, "duel.req_title"),
        description=t(guild_id, "duel.req_desc", team=team_label(team), leader=f"<@{team['leader_id']}>",
                      target=team_label(target), size=size),
        footer=t(guild_id, "duel.req_footer", minutes=REQUEST_TTL // 60),
    )
    embed.color = TEAM_COLORS.get(team.get("color"), embeds.ERROR)
    embed.add_field(name=t(guild_id, "duel.field_team_players", name=team_name(team)),
                    value=roster(team["members"], team["leader_id"]), inline=True)
    embed.add_field(name=t(guild_id, "duel.field_lifetime"), value=lifetime_text(guild_id, team), inline=True)
    embed.add_field(name=t(guild_id, "duel.field_rounds"), value=rounds_value(rounds), inline=True)
    return embed


def session_side(session: dict, side: str) -> tuple[str, list[int]]:
    """(libellé coloré, joueurs) d'un camp, depuis l'instantané du duel."""
    label = f"{session.get(f'color_{side}', '⚪')} **{sanitize(session.get(f'name_{side}', '?'), MAX_TEAM_NAME)}**"
    return label, list(session.get(f"players_{side}", []))


def lobby_embed(guild_id: int, session: dict) -> discord.Embed:
    embed = embeds.base(
        guild_id,
        title=t(guild_id, "duel.lobby_title", number=f"{session['number']:02d}"),
        description=t(guild_id, "duel.lobby_desc", voice=f"<#{session['voice_id']}>",
                      minutes=JOIN_TIMEOUT // 60),
        kind="brand",
    )
    for side in ("a", "b"):
        label, players = session_side(session, side)
        embed.add_field(name=label[:256], value=" ".join(f"<@{uid}>" for uid in players) or "—", inline=True)
    embed.add_field(name=t(guild_id, "duel.field_rounds"), value=rounds_value(session.get("rounds")), inline=True)
    return embed


def started_embed(guild_id: int, session: dict) -> discord.Embed:
    label_a, _ = session_side(session, "a")
    label_b, _ = session_side(session, "b")
    embed = embeds.base(
        guild_id,
        title=t(guild_id, "duel.started_title", number=f"{session['number']:02d}"),
        description=t(guild_id, "duel.started_desc",
                      team_a=label_a, voice_a=f"<#{session.get('voice_a_id')}>",
                      team_b=label_b, voice_b=f"<#{session.get('voice_b_id')}>",
                      voice=f"<#{session['voice_id']}>"),
        footer=t(guild_id, "duel.started_footer"),
        kind="success",
    )
    embed.add_field(name=t(guild_id, "duel.field_rounds"), value=rounds_value(session.get("rounds")), inline=True)
    return embed


# Couleur de l'historique selon l'état de la dernière partie.
HISTORY_KIND = {"waiting": "warning", "playing": "warning", "pending": "brand",
                "won": "gold", "cancelled": "neutral", "undecided": "neutral"}
MAX_HISTORY_LINES = 20


def side_label(source: dict, side: str) -> str:
    """« 🔴 Alpha » depuis un duel ou son historique (champs name_a, color_a…)."""
    return f"{source.get(f'color_{side}', '⚪')} {sanitize(source.get(f'name_{side}', '?'), MAX_TEAM_NAME)}"


def winner_labels(guild_id: int, source: dict) -> tuple[str, str]:
    return tuple(t(guild_id, "duel.btn_win", team=side_label(source, side)) for side in ("a", "b"))


def history_embed(guild_id: int, record: dict) -> discord.Embed:
    """Le message d'historique d'un duel : une ligne par partie, modifiée au
    fil du duel. Un seul message pour tout le duel, relances comprises : le
    salon des demandes ne se remplit pas d'un message par étape."""
    games = record.get("games") or [{"state": "waiting"}]
    lines = []
    for number, game in enumerate(games, 1):
        state = game.get("state", "waiting")
        if state == "won":
            text = t(guild_id, "duel.hist_won", team=f"**{side_label(record, game.get('winner', 'a'))}**")
        else:
            text = t(guild_id, f"duel.hist_{state}")
        lines.append(t(guild_id, "duel.hist_game", n=number, state=text)
                     + (t(guild_id, "duel.hist_rematch") if game.get("rematch") else ""))
    embed = embeds.base(
        guild_id,
        title=t(guild_id, "duel.hist_title", number=f"{record.get('number', 0):02d}",
                team_a=side_label(record, "a"), team_b=side_label(record, "b"))[:256],
        description="\n".join(lines[-MAX_HISTORY_LINES:]),
        kind=HISTORY_KIND.get(games[-1].get("state"), "brand"),
        timestamp=True,
    )
    for side in ("a", "b"):
        embed.add_field(name=t(guild_id, "duel.field_team_players", name=side_label(record, side))[:256],
                        value=roster(record.get(f"players_{side}", []), record.get(f"leader_{side}")) or "—",
                        inline=True)
    embed.add_field(name=t(guild_id, "duel.field_rounds"), value=rounds_value(record.get("rounds")), inline=True)
    return embed


def panel_embed(guild_id: int, user_id: int) -> discord.Embed:
    team = duel_team_of(guild_id, user_id)
    if team is None:
        return embeds.base(guild_id, title=t(guild_id, "duel.panel_title"),
                           description=t(guild_id, "duel.panel_desc") + "\n\n" + t(guild_id, "duel.panel_no_team"),
                           footer=t(guild_id, "duel.team_footer"))
    embed = team_embed(guild_id, team, title_key="duel.team_title")
    embed.description = t(guild_id, "duel.panel_desc")
    if team.get("status") != "ready":
        embed.description += "\n\n" + t(guild_id, "duel.panel_pending")
    return embed


def missing_permissions(guild: discord.Guild, category, channel) -> list[str]:
    """Permissions qui manquent au bot là où le duel en a besoin."""
    missing: list[str] = []
    for place, needed in ((category, CATEGORY_PERMS), (channel, CHANNEL_PERMS)):
        if place is None:
            continue
        perms = place.permissions_for(guild.me)
        missing += [name for name in needed if not getattr(perms, name) and name not in missing]
    return missing


# ----------------------------------------------------------------------
# Création d'une team
# ----------------------------------------------------------------------
class TeamBuilderView(discord.ui.View):
    """Le constructeur de team, dans un message éphémère."""

    def __init__(self, cog: "Duel", guild_id: int, author_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.gid = guild_id
        self.author_id = author_id
        self.name = ""
        self.color = COLOR_PALETTE[0][0]
        self.duels = LIFETIMES[0]
        self.lead_added = False
        self.mates: list[int] = []
        self.sync()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    def players(self) -> list[int]:
        return ([self.author_id] if self.lead_added else []) + self.mates

    def embed(self, notice: str | None = None) -> discord.Embed:
        gid = self.gid
        description = t(gid, "duel.builder_desc", max=MAX_TEAM_SIZE)
        if notice:
            description = f"{notice}\n\n{description}"
        embed = embeds.base(gid, title=t(gid, "duel.builder_title"), description=description,
                            footer=t(gid, "duel.team_footer"))
        embed.color = TEAM_COLORS.get(self.color, embeds.BRAND)
        embed.add_field(name=t(gid, "duel.field_name"),
                        value=f"**{self.name}**" if self.name else t(gid, "duel.not_set"), inline=True)
        embed.add_field(name=t(gid, "duel.field_color"),
                        value=f"{self.color} {color_name(get_lang(gid), self.color)}", inline=True)
        embed.add_field(name=t(gid, "duel.field_lifetime"), value=lifetime_label(gid, self.duels), inline=True)
        players = self.players()
        lines = [f"👑 <@{self.author_id}>"] if self.lead_added else []
        lines += [f"✉️ <@{uid}>" for uid in self.mates]
        embed.add_field(name=t(gid, "duel.field_players", count=len(players)),
                        value="\n".join(lines) or t(gid, "duel.builder_no_player"), inline=False)
        return embed

    def sync(self) -> None:
        self.clear_items()
        gid = self.gid
        lang = get_lang(gid)

        colors = discord.ui.Select(
            placeholder=t(gid, "duel.builder_pick_color")[:150], row=0,
            options=[discord.SelectOption(label=color_name(lang, emoji)[:100], emoji=emoji, value=emoji,
                                          default=emoji == self.color)
                     for emoji, _fr, _en in COLOR_PALETTE],
        )
        colors.callback = self._set_color(colors)
        self.add_item(colors)

        lifetimes = discord.ui.Select(
            placeholder=t(gid, "duel.builder_pick_lifetime")[:150], row=1,
            options=[discord.SelectOption(label=lifetime_label(gid, n)[:100], value=str(n),
                                          emoji="♾️" if not n else "⏳", default=n == self.duels)
                     for n in LIFETIMES],
        )
        lifetimes.callback = self._set_lifetime(lifetimes)
        self.add_item(lifetimes)

        player = discord.ui.Button(label=t(gid, "duel.btn_player")[:80], emoji="👤", row=2,
                                   style=discord.ButtonStyle.success if self.lead_added else discord.ButtonStyle.primary,
                                   disabled=self.lead_added)
        player.callback = self._add_lead
        self.add_item(player)

        mates = discord.ui.Button(label=t(gid, "duel.btn_mates")[:80], emoji="➕", row=2,
                                  style=discord.ButtonStyle.primary)
        mates.callback = self._pick_mates
        self.add_item(mates)

        rename = discord.ui.Button(label=t(gid, "duel.btn_name")[:80], emoji="✏️", row=2,
                                   style=discord.ButtonStyle.secondary)
        rename.callback = self._rename
        self.add_item(rename)

        finish = discord.ui.Button(label=t(gid, "duel.btn_finish")[:80], emoji=custom_emojis.get("checkmark"), row=3,
                                   style=discord.ButtonStyle.success)
        finish.callback = self._finish
        self.add_item(finish)

        cancel = discord.ui.Button(label=t(gid, "duel.btn_cancel")[:80], emoji=custom_emojis.get("cross"), row=3,
                                   style=discord.ButtonStyle.secondary)
        cancel.callback = self._cancel
        self.add_item(cancel)

    async def refresh(self, interaction: discord.Interaction, notice: str | None = None) -> None:
        self.sync()
        await interaction.response.edit_message(content=None, embed=self.embed(notice), view=self)

    def _set_color(self, select: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            self.color = select.values[0]
            await self.refresh(interaction)
        return callback

    def _set_lifetime(self, select: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            self.duels = int(select.values[0])
            await self.refresh(interaction)
        return callback

    async def _add_lead(self, interaction: discord.Interaction) -> None:
        if duel_team_of(self.gid, self.author_id) is not None:
            await self.refresh(interaction, t(self.gid, "duel.err_already_team"))
            return
        self.lead_added = True
        await self.refresh(interaction)

    async def _pick_mates(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self.embed(t(self.gid, "duel.builder_mates_hint", max=MAX_TEAM_SIZE - 1)),
            view=MatesPicker(self),
        )

    async def _rename(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TeamNameModal(self))

    async def _finish(self, interaction: discord.Interaction) -> None:
        if not self.lead_added:
            await self.refresh(interaction, t(self.gid, "duel.err_add_yourself"))
            return
        if not self.name:
            await self.refresh(interaction, t(self.gid, "duel.err_no_name"))
            return
        await self.cog.finish_team(interaction, self)

    async def _cancel(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(content=t(self.gid, "duel.builder_cancelled"),
                                                embed=None, view=None)


class MatesPicker(discord.ui.View):
    """Choisir ses coéquipiers, puis retour au constructeur."""

    def __init__(self, builder: TeamBuilderView):
        super().__init__(timeout=600)
        self.builder = builder
        gid = builder.gid
        select = discord.ui.UserSelect(placeholder=t(gid, "duel.builder_pick_mates")[:150],
                                       min_values=1, max_values=MAX_TEAM_SIZE - 1, row=0)
        select.callback = self._picked(select)
        self.add_item(select)
        back = discord.ui.Button(label=t(gid, "duel.btn_back")[:80],
                                 emoji=custom_emojis.get("replymsg"), row=1,
                                 style=discord.ButtonStyle.secondary)
        back.callback = self._back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.builder.author_id

    def _picked(self, select: discord.ui.UserSelect):
        async def callback(interaction: discord.Interaction) -> None:
            gid = self.builder.gid
            chosen, rejected = [], []
            for user in select.values:
                if user.id == self.builder.author_id:
                    continue
                if user.bot:
                    rejected.append(t(gid, "duel.builder_rejected_bot", user=user.mention))
                elif duel_team_of(gid, user.id) is not None:
                    rejected.append(t(gid, "duel.builder_rejected_busy", user=user.mention))
                else:
                    chosen.append(user.id)
            self.builder.mates = chosen
            await self.builder.refresh(interaction, "\n".join(rejected) or None)
        return callback

    async def _back(self, interaction: discord.Interaction) -> None:
        await self.builder.refresh(interaction)


def name_error(guild_id: int, name: str) -> str | None:
    if len(name) < 2:
        return "duel.err_name"
    if duel_team_named(guild_id, name) is not None:
        return "duel.err_name_taken"
    if clan_named(guild_id, name) is not None:
        return "duel.err_name_clan"
    return None


class TeamNameModal(discord.ui.Modal):
    def __init__(self, builder: TeamBuilderView):
        super().__init__(title=t(builder.gid, "duel.name_modal")[:45])
        self.builder = builder
        self.field = discord.ui.TextInput(label=t(builder.gid, "duel.field_name")[:45],
                                          min_length=2, max_length=MAX_TEAM_NAME,
                                          default=builder.name or None)
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = self.builder.gid
        name = sanitize(self.field.value.strip(), MAX_TEAM_NAME)
        error = name_error(gid, name)
        if error is not None:
            await self.builder.refresh(interaction, t(gid, error))
            return
        self.builder.name = name
        await self.builder.refresh(interaction)


# ----------------------------------------------------------------------
# Panneau /duel et choix de l'adversaire
# ----------------------------------------------------------------------
class DuelPanelView(discord.ui.View):
    """Les boutons de /duel sans option : créer une team, ou la quitter. Le
    défi se lance avec /duel <team> <rounds>, qui porte le nombre de rounds."""

    def __init__(self, cog: "Duel", guild_id: int, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.gid = guild_id
        self.user_id = user_id
        team = duel_team_of(guild_id, user_id)

        if team is None:
            create = discord.ui.Button(label=t(guild_id, "duel.btn_create")[:80], emoji="🛠️",
                                       style=discord.ButtonStyle.success)
            create.callback = self._create
            self.add_item(create)
            return

        is_lead = team.get("leader_id") == user_id
        leave = discord.ui.Button(label=t(guild_id, "duel.btn_dissolve" if is_lead else "duel.btn_leave")[:80],
                                  emoji="🚪", style=discord.ButtonStyle.secondary)
        leave.callback = self._leave
        self.add_item(leave)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def _create(self, interaction: discord.Interaction) -> None:
        if duel_team_of(self.gid, self.user_id) is not None:
            await interaction.response.send_message(t(self.gid, "duel.err_already_team"), ephemeral=True)
            return
        builder = TeamBuilderView(self.cog, self.gid, self.user_id)
        await interaction.response.edit_message(embed=builder.embed(), view=builder)

    async def _leave(self, interaction: discord.Interaction) -> None:
        await self.cog.leave_team(interaction)


# ----------------------------------------------------------------------
# Vues persistantes : elles répondent encore après un redémarrage.
# Les libellés vivent dans le message ; la vue ré-enregistrée au démarrage
# n'a pas de serveur et garde ceux par défaut, que personne ne voit.
# ----------------------------------------------------------------------
class TeamInviteView(discord.ui.View):
    def __init__(self, cog: "Duel", guild_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        if guild_id is not None:
            self.accept.label = t(guild_id, "duel.btn_accept")
            self.decline.label = t(guild_id, "duel.btn_decline")
        self.accept.emoji = custom_emojis.get("checkmark")
        self.decline.emoji = custom_emojis.get("cross")

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, emoji="✅",
                       custom_id="cyq:duel:inv_ok")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.answer_invite(interaction, accepted=True)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="✖️",
                       custom_id="cyq:duel:inv_no")
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.answer_invite(interaction, accepted=False)


class DuelAnswerView(discord.ui.View):
    def __init__(self, cog: "Duel", guild_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        if guild_id is not None:
            self.accept.label = t(guild_id, "duel.btn_accept")
            self.decline.label = t(guild_id, "duel.btn_decline")
        self.decline.emoji = custom_emojis.get("cross")

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, emoji="⚔️",
                       custom_id="cyq:duel:ok")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.answer_challenge(interaction, accepted=True)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="✖️",
                       custom_id="cyq:duel:no")
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.answer_challenge(interaction, accepted=False)


class DuelEndView(discord.ui.View):
    def __init__(self, cog: "Duel", guild_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        if guild_id is not None:
            self.end.label = t(guild_id, "duel.btn_end")

    @discord.ui.button(label="Terminer le duel", style=discord.ButtonStyle.secondary, emoji="🏁",
                       custom_id="cyq:duel:end")
    async def end(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.stop_from_button(interaction)


class DuelRematchView(discord.ui.View):
    """Sous la fin d'un duel : « Relancer » avec le compte des votes, et les
    deux boutons du vainqueur tant qu'il n'est pas désigné."""

    def __init__(self, cog: "Duel", guild_id: int | None = None, votes: int = 0, total: int = 0,
                 *, labels: tuple[str, str] | None = None, rematch: bool = True, close: bool = True):
        super().__init__(timeout=None)
        self.cog = cog
        self.rematch.emoji = custom_emojis.get("replay")
        self.close.emoji = custom_emojis.get("off")
        if guild_id is None:
            return  # exemplaire enregistré au démarrage : tous les boutons
        self.rematch.label = t(guild_id, "duel.btn_rematch", votes=votes, total=total)[:80]
        self.close.label = t(guild_id, "duel.btn_close")[:80]
        if not rematch:
            self.remove_item(self.rematch)
        # « Fin » part avec la relance : une fois un nouveau duel lancé dans
        # le fil, le fermer couperait la partie en cours.
        if not close:
            self.remove_item(self.close)
        if labels is None:
            self.remove_item(self.win_a)
            self.remove_item(self.win_b)
        else:
            self.win_a.label, self.win_b.label = labels[0][:80], labels[1][:80]

    @discord.ui.button(label="Relancer", style=discord.ButtonStyle.success, emoji="🔁",
                       custom_id="cyq:duel:rematch", row=0)
    async def rematch(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.vote_rematch(interaction)

    @discord.ui.button(label="Fin", style=discord.ButtonStyle.danger, emoji="⏹️",
                       custom_id="cyq:duel:close", row=0)
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.close_from_button(interaction)

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary, emoji="🏆",
                       custom_id="cyq:duel:win_a", row=1)
    async def win_a(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.vote_winner(interaction, "a")

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary, emoji="🏆",
                       custom_id="cyq:duel:win_b", row=1)
    async def win_b(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.vote_winner(interaction, "b")


# ----------------------------------------------------------------------
# /config-duel
# ----------------------------------------------------------------------
def _category_of(guild: discord.Guild):
    channel = guild.get_channel(get_duel_config(guild.id).get("category_id") or 0)
    return channel if getattr(channel, "type", None) == discord.ChannelType.category else None


def _requests_channel_of(guild: discord.Guild):
    channel = guild.get_channel(get_duel_config(guild.id).get("requests_channel_id") or 0)
    return channel if getattr(channel, "type", None) == discord.ChannelType.text else None


def config_embed(guild: discord.Guild) -> discord.Embed:
    gid = guild.id
    config = get_duel_config(gid)
    category = _category_of(guild)
    channel = _requests_channel_of(guild)
    embed = embeds.base(gid, title=t(gid, "duel.cfg_title"), description=t(gid, "duel.cfg_desc"))
    embed.add_field(name=t(gid, "duel.cfg_field_state"),
                    value=f"{embeds.state(config['enabled'])} "
                          + t(gid, "duel.cfg_on" if config["enabled"] else "duel.cfg_off"),
                    inline=True)
    embed.add_field(name=t(gid, "duel.cfg_field_category"),
                    value=category.mention if category else t(gid, "duel.not_set"), inline=True)
    embed.add_field(name=t(gid, "duel.cfg_field_channel"),
                    value=channel.mention if channel else t(gid, "duel.not_set"), inline=True)
    missing = missing_permissions(guild, category, channel)
    embed.add_field(name=t(gid, "duel.cfg_field_perms"),
                    value=t(gid, "duel.cfg_perms_missing", perms=", ".join(f"`{p}`" for p in missing))
                    if missing else t(gid, "duel.cfg_perms_ok"),
                    inline=False)
    embeds.brand(embed, guild)
    return embed


class DuelConfigView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild
        self.sync()

    def sync(self) -> None:
        self.clear_items()
        gid = self.guild.id
        category = discord.ui.ChannelSelect(placeholder=t(gid, "duel.cfg_pick_category")[:150],
                                            channel_types=[discord.ChannelType.category], row=0)
        category.callback = self._set("category_id", category)
        self.add_item(category)

        channel = discord.ui.ChannelSelect(placeholder=t(gid, "duel.cfg_pick_channel")[:150],
                                           channel_types=[discord.ChannelType.text], row=1)
        channel.callback = self._set("requests_channel_id", channel)
        self.add_item(channel)

        enabled = get_duel_config(gid)["enabled"]
        toggle = discord.ui.Button(label=t(gid, "duel.cfg_disable" if enabled else "duel.cfg_enable")[:80],
                                   style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
                                   row=2)
        toggle.callback = self._toggle
        self.add_item(toggle)

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.sync()
        await interaction.response.edit_message(embed=config_embed(self.guild), view=self)

    def _set(self, key: str, select: discord.ui.ChannelSelect):
        async def callback(interaction: discord.Interaction) -> None:
            set_duel_config(self.guild.id, **{key: select.values[0].id})
            await self.refresh(interaction)
        return callback

    async def _toggle(self, interaction: discord.Interaction) -> None:
        gid = self.guild.id
        enabled = get_duel_config(gid)["enabled"]
        if not enabled and (_category_of(self.guild) is None or _requests_channel_of(self.guild) is None):
            await interaction.response.send_message(t(gid, "duel.cfg_missing"), ephemeral=True)
            return
        set_duel_config(gid, enabled=not enabled)
        await self.refresh(interaction)


# ----------------------------------------------------------------------
# Le cog
# ----------------------------------------------------------------------
class Duel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._watch_task: asyncio.Task | None = None
        self._launching: set[tuple[int, int]] = set()
        self._empty_since: dict[tuple[int, int], float] = {}
        self._voice_locks: dict[int, asyncio.Lock] = {}
        # Relances proposées : (serveur, fil) -> instantané du duel et votes.
        self._rematch: dict[tuple[int, int], dict] = {}

    async def cog_load(self) -> None:
        # Sans ces lignes, les boutons publiés avant un redémarrage ne
        # répondent plus.
        self.bot.add_view(TeamInviteView(self))
        self.bot.add_view(DuelAnswerView(self))
        self.bot.add_view(DuelEndView(self))
        self.bot.add_view(DuelRematchView(self))

    async def cog_unload(self) -> None:
        if self._watch_task is not None:
            self._watch_task.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # on_ready revient à chaque reconnexion : une seule ronde à la fois.
        if self._watch_task is None or self._watch_task.done():
            self._watch_task = asyncio.create_task(self._watch_loop())

    # -- Ressources désignées --------------------------------------------
    def category(self, guild: discord.Guild):
        return _category_of(guild)

    def requests_channel(self, guild: discord.Guild):
        return _requests_channel_of(guild)

    def ready_error(self, guild: discord.Guild | None) -> str | None:
        if guild is None:
            return "common.members_only"
        if not get_duel_config(guild.id)["enabled"]:
            return "duel.err_disabled"
        if self.category(guild) is None or self.requests_channel(guild) is None:
            return "duel.err_not_configured"
        return None

    # -- Fils privés -----------------------------------------------------
    async def open_thread(self, guild: discord.Guild, name: str, member_ids: list[int]):
        """Fil privé du salon des demandes, avec seulement ces membres."""
        channel = self.requests_channel(guild)
        if channel is None:
            raise RuntimeError("salon des demandes introuvable")
        thread = await channel.create_thread(name=name[:100], type=discord.ChannelType.private_thread,
                                             invitable=False, auto_archive_duration=1440, reason="Duel")
        await throttled_each(list(dict.fromkeys(member_ids)),
                             lambda uid: thread.add_user(discord.Object(id=uid)),
                             delay=0.2, label="membres d'un fil de duel")
        return thread

    async def get_thread(self, guild: discord.Guild, thread_id: int | None):
        if not thread_id:
            return None
        thread = guild.get_thread(thread_id)
        if thread is None:
            # Un fil archivé n'est plus dans le cache.
            try:
                thread = await guild.fetch_channel(thread_id)
            except discord.HTTPException:
                return None
        return thread

    async def post(self, guild: discord.Guild, thread_id: int | None, **kwargs):
        thread = await self.get_thread(guild, thread_id)
        if thread is None:
            return None
        kwargs.setdefault("allowed_mentions", USERS_ONLY)
        try:
            return await thread.send(**kwargs)
        except discord.HTTPException as e:
            log.warning(f"[{guild.name}] Message de duel non envoyé : {e}")
            return None

    async def delete_thread(self, guild: discord.Guild, thread_id: int) -> None:
        thread = await self.get_thread(guild, thread_id)
        if thread is None:
            return
        try:
            await thread.delete()
        except discord.HTTPException as e:
            log.warning(f"[{guild.name}] Fil de duel non supprimé : {e}")

    # -- Commandes -------------------------------------------------------
    async def _guard(self, interaction: discord.Interaction) -> bool:
        error = self.ready_error(interaction.guild)
        if error is None:
            return True
        await interaction.response.send_message(t(interaction.guild_id, error), ephemeral=True)
        return False

    async def team_choices(self, interaction: discord.Interaction,
                           current: str) -> list[app_commands.Choice[str]]:
        gid = interaction.guild_id
        if gid is None:
            return []
        mine = duel_team_of(gid, interaction.user.id)
        wanted = current.casefold()
        choices = [
            app_commands.Choice(
                name=f"{team.get('color', '')} {team.get('name', '?')} · "
                     f"{len(team['members'])} vs {len(team['members'])}"[:100],
                value=team.get("name", "?")[:100],
            )
            for team in sorted(get_duel_teams(gid).values(), key=lambda team: team.get("name", "").casefold())
            if team.get("status") == "ready" and (mine is None or team["id"] != mine["id"])
            and wanted in team.get("name", "").casefold()
        ]
        return choices[:25]

    @app_commands.command(name="duel",
                          description="Défie une team en X rounds. Sans option : ton panneau (créer, quitter).")
    @app_commands.describe(team="Le nom de la team adverse",
                           rounds=f"Nombre de rounds du duel (1 à {MAX_ROUNDS}, 1 par défaut)")
    @app_commands.autocomplete(team=team_choices)
    async def duel(self, interaction: discord.Interaction, team: str | None = None,
                   rounds: app_commands.Range[int, 1, MAX_ROUNDS] = 1) -> None:
        if not await self._guard(interaction):
            return
        gid = interaction.guild_id
        if team:
            await self.send_challenge(interaction, duel_team_named(gid, team), rounds=rounds, from_panel=False)
            return
        await interaction.response.send_message(
            embed=panel_embed(gid, interaction.user.id),
            view=DuelPanelView(self, gid, interaction.user.id),
            ephemeral=True,
        )

    @app_commands.command(name="createteam", description="Crée une team de duel : joueurs, nom, couleur, durée.")
    async def createteam(self, interaction: discord.Interaction) -> None:
        if not await self._guard(interaction):
            return
        gid = interaction.guild_id
        team = duel_team_of(gid, interaction.user.id)
        if team is not None:
            await interaction.response.send_message(t(gid, "duel.err_already_team"), ephemeral=True)
            return
        builder = TeamBuilderView(self, gid, interaction.user.id)
        await interaction.response.send_message(embed=builder.embed(), view=builder, ephemeral=True)

    @app_commands.command(name="config-duel",
                          description="Configure les duels : catégorie, salon des demandes, activation.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def config_duel(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(t(None, "common.members_only"), ephemeral=True)
            return
        await interaction.response.send_message(embed=config_embed(guild), view=DuelConfigView(guild),
                                                ephemeral=True)

    # -- Team : création, invitations, départ ------------------------------
    async def finish_team(self, interaction: discord.Interaction, builder: TeamBuilderView) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        error = self.ready_error(guild)
        if error is not None:
            await builder.refresh(interaction, t(gid, error))
            return
        try:
            team = create_duel_team(gid, name=builder.name, color=builder.color, leader_id=builder.author_id,
                                    invited=builder.mates, duels=builder.duels)
        except ValueError as e:
            key = {"name_taken": "duel.err_name_taken", "clan_name": "duel.err_name_clan",
                   "busy": "duel.err_busy", "size": "duel.err_size_max",
                   "full": "duel.err_full"}.get(str(e), "duel.err_name")
            await builder.refresh(interaction, error_text(gid, key))
            return
        builder.stop()

        if team["status"] == "ready":
            await interaction.response.edit_message(
                content=t(gid, "duel.team_ready_hint"),
                embed=team_embed(gid, team, title_key="duel.team_created"), view=None)
            return

        # Ouvrir le fil et y ajouter chacun demande plusieurs appels : on rend
        # la main tout de suite pour ne pas laisser expirer l'interaction.
        await interaction.response.defer()
        thread = None
        try:
            thread = await self.open_thread(guild, f"👥 {team_name(team)}", [team["leader_id"], *team["invited"]])
            message = await thread.send(
                content=" ".join(f"<@{uid}>" for uid in team["invited"]),
                embed=invite_embed(gid, team), view=TeamInviteView(self, gid),
                allowed_mentions=USERS_ONLY,
            )
        except (discord.HTTPException, RuntimeError) as e:
            log.error(f"[{guild.name}] Invitation de team non envoyée : {e}")
            delete_duel_team(gid, team["id"])
            if thread is not None:
                add_duel_trash(gid, thread.id, time.time())
            await interaction.edit_original_response(content=t(gid, "duel.err_thread"), embed=None, view=None)
            return
        set_duel_team_fields(gid, team["id"], invite_thread_id=thread.id, invite_message_id=message.id)
        await interaction.edit_original_response(
            content=t(gid, "duel.inv_sent", thread=thread.mention),
            embed=team_embed(gid, team, title_key="duel.team_pending_title"), view=None)

    def team_by_invite(self, guild_id: int, message_id: int) -> dict | None:
        return next((team for team in get_duel_teams(guild_id).values()
                     if team.get("invite_message_id") == message_id), None)

    async def answer_invite(self, interaction: discord.Interaction, *, accepted: bool) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        team = self.team_by_invite(gid, interaction.message.id) if gid else None
        if team is None:
            await interaction.response.send_message(t(gid, "duel.inv_gone"), ephemeral=True)
            return
        user = interaction.user
        if user.id not in team.get("invited", []):
            key = "duel.inv_already" if user.id in team.get("members", []) else "duel.inv_not_for_you"
            await interaction.response.send_message(t(gid, key), ephemeral=True)
            return
        thread_id = team.get("invite_thread_id")

        if not accepted:
            delete_duel_team(gid, team["id"])
            await interaction.response.edit_message(
                content=None,
                embed=embeds.base(gid, title=t(gid, "duel.inv_declined_title"),
                                  description=t(gid, "duel.inv_declined_desc", member=user.mention,
                                                team=team_label(team)),
                                  kind="error"),
                view=None)
            add_duel_trash(gid, thread_id, time.time() + THREAD_GRACE)
            return

        result = accept_duel_invite(gid, team["id"], user.id)
        if result == "busy":
            await interaction.response.send_message(t(gid, "duel.err_busy_you"), ephemeral=True)
            return
        if result not in ("waiting", "ready"):
            await interaction.response.send_message(t(gid, "duel.inv_gone"), ephemeral=True)
            return
        team = get_duel_team(gid, team["id"])
        if result == "waiting":
            await interaction.response.edit_message(embed=invite_embed(gid, team), view=TeamInviteView(self, gid))
            return
        await interaction.response.edit_message(
            content=None, embed=team_embed(gid, team, title_key="duel.team_created"), view=None)
        await self.post(guild, thread_id, content=t(gid, "duel.inv_ready_ping", leader=f"<@{team['leader_id']}>"))
        add_duel_trash(gid, thread_id, time.time() + THREAD_GRACE)

    async def close_invite(self, guild: discord.Guild, team: dict, key: str) -> None:
        thread = await self.get_thread(guild, team.get("invite_thread_id"))
        if thread is not None and team.get("invite_message_id"):
            try:
                message = await thread.fetch_message(team["invite_message_id"])
                await message.edit(content=None, view=None,
                                   embed=embeds.base(guild.id, description=t(guild.id, key, team=team_label(team)),
                                                     kind="warning"))
            except discord.HTTPException:
                pass
        add_duel_trash(guild.id, team.get("invite_thread_id"), time.time() + THREAD_GRACE)

    async def leave_team(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        team = duel_team_of(gid, interaction.user.id)
        if team is None:
            await interaction.response.edit_message(content=t(gid, "duel.err_no_team"), embed=None, view=None)
            return
        if duel_session_of_team(gid, team["id"]):
            await interaction.response.send_message(t(gid, "duel.err_leave_in_duel"), ephemeral=True)
            return
        snapshot = dict(team)
        outcome = leave_duel_team(gid, team["id"], interaction.user.id)
        key = "duel.dissolved" if outcome == "dissolved" else "duel.left"
        await interaction.response.edit_message(content=t(gid, key, team=team_label(snapshot)),
                                                embed=None, view=None)
        if outcome == "dissolved":
            await self.drop_team_requests(guild, snapshot["id"])
            if snapshot.get("status") == "pending":
                await self.close_invite(guild, snapshot, "duel.inv_cancelled")

    # -- Défis -------------------------------------------------------------
    async def send_challenge(self, interaction: discord.Interaction, target: dict | None, *,
                             rounds: int = 1, from_panel: bool) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        team = duel_team_of(gid, interaction.user.id)
        error = self.ready_error(guild) or challenge_error(gid, team, target, interaction.user.id)
        if error is None and pending_duel_request(gid, team["id"], target["id"]):
            error = "duel.err_already_sent"
        if error is not None:
            await interaction.response.send_message(error_text(gid, error, team, target), ephemeral=True)
            return

        if from_panel:
            await interaction.response.defer()
        else:
            await interaction.response.defer(ephemeral=True)
        thread = None
        try:
            thread = await self.open_thread(guild, f"⚔️ {team_name(team)} vs {team_name(target)}",
                                            [team["leader_id"], target["leader_id"]])
            message = await thread.send(content=f"<@{target['leader_id']}>",
                                        embed=request_embed(gid, team, target, rounds),
                                        view=DuelAnswerView(self, gid), allowed_mentions=USERS_ONLY)
        except (discord.HTTPException, RuntimeError) as e:
            log.error(f"[{guild.name}] Défi de duel non envoyé : {e}")
            if thread is not None:
                add_duel_trash(gid, thread.id, time.time())
            await interaction.edit_original_response(content=t(gid, "duel.err_thread"), embed=None, view=None)
            return
        add_duel_request(gid, {"message_id": message.id, "thread_id": thread.id,
                               "from_team": team["id"], "to_team": target["id"], "at": int(time.time()),
                               "rounds": rounds})
        await interaction.edit_original_response(
            content=t(gid, "duel.req_sent", team=team_label(target), thread=thread.mention),
            embed=None, view=None)

    async def answer_challenge(self, interaction: discord.Interaction, *, accepted: bool) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        request = get_duel_request(gid, interaction.message.id) if gid else None
        if request is None:
            await interaction.response.send_message(t(gid, "duel.req_gone"), ephemeral=True)
            return
        team = get_duel_team(gid, request["from_team"])
        target = get_duel_team(gid, request["to_team"])
        if target is None or interaction.user.id != target.get("leader_id"):
            await interaction.response.send_message(t(gid, "duel.req_not_for_you"), ephemeral=True)
            return
        remove_duel_request(gid, request["message_id"])
        thread_id = request.get("thread_id")

        if not accepted:
            await interaction.response.edit_message(
                content=None, view=None,
                embed=embeds.base(gid, title=t(gid, "duel.req_declined_title"),
                                  description=t(gid, "duel.req_declined_desc", team=team_label(target)),
                                  kind="warning"))
            if team is not None:
                await self.post(guild, thread_id,
                                content=t(gid, "duel.req_declined_ping", leader=f"<@{team['leader_id']}>"))
            add_duel_trash(gid, thread_id, time.time() + THREAD_GRACE)
            return

        leader = team.get("leader_id") if team else None
        error = self.ready_error(guild) or challenge_error(gid, team, target, leader)
        if error is not None:
            await interaction.response.edit_message(
                content=None, view=None,
                embed=embeds.base(gid, title=t(gid, "duel.req_impossible"),
                                  description=error_text(gid, error, team, target), kind="warning"))
            add_duel_trash(gid, thread_id, time.time() + THREAD_GRACE)
            return

        await interaction.response.edit_message(
            content=None, view=None,
            embed=embeds.base(gid, title=t(gid, "duel.req_accepted_title"),
                              description=t(gid, "duel.req_accepted_desc", team=team_label(team),
                                            target=team_label(target)),
                              kind="success"))
        try:
            await self.start_duel(guild, team, target, thread_id, rounds=request.get("rounds", 1))
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Vocal de duel non créé : {e}")
            await self.post(guild, thread_id, content=t(gid, "duel.err_voice"))
            add_duel_trash(gid, thread_id, time.time() + THREAD_GRACE)

    async def drop_team_requests(self, guild: discord.Guild, team_id: str) -> None:
        """Ferme les défis d'une team qui vient de disparaître."""
        for request in remove_duel_requests_of_team(guild.id, team_id):
            await self.close_request(guild, request, "duel.req_cancelled")

    async def close_request(self, guild: discord.Guild, request: dict, key: str) -> None:
        thread = await self.get_thread(guild, request.get("thread_id"))
        if thread is not None:
            try:
                message = await thread.fetch_message(request["message_id"])
                await message.edit(content=None, view=None,
                                   embed=embeds.base(guild.id, description=t(guild.id, key), kind="warning"))
            except discord.HTTPException:
                pass
        add_duel_trash(guild.id, request.get("thread_id"), time.time() + THREAD_GRACE)

    # -- Le duel -----------------------------------------------------------
    def overwrites(self, guild: discord.Guild, members: list) -> dict:
        """Vocal fermé à tous, ouvert aux joueurs du duel et au bot."""
        rules = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True,
                                                  move_members=True, manage_channels=True),
        }
        for member in members:
            rules[member] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
        return rules

    async def start_duel(self, guild: discord.Guild, team_a: dict, team_b: dict, thread_id: int | None,
                         *, free: bool = False, rounds: int = 1, history_id: str | None = None) -> dict:
        """Défi accepté (ou relance votée) : crée duel-XX et attend les joueurs."""
        gid = guild.id
        number = next_duel_number(gid)
        session = {
            "number": number, "thread_id": thread_id, "phase": "waiting",
            "voice_id": None, "voice_a_id": None, "voice_b_id": None,
            "created_at": int(time.time()), "started_at": None, "free": free,
            "rounds": rounds,
        }
        for side, team in (("a", team_a), ("b", team_b)):
            session[f"team_{side}"] = team["id"]
            session[f"name_{side}"] = team["name"]
            session[f"color_{side}"] = team.get("color", "⚪")
            session[f"players_{side}"] = list(team["members"])
        # Enregistré AVANT de créer le vocal : le numéro est réservé, un autre
        # défi accepté au même instant ne peut pas prendre le même.
        save_duel_session(gid, session)

        players = session["players_a"] + session["players_b"]
        members = [m for m in (guild.get_member(uid) for uid in players) if m is not None]
        try:
            voice = await guild.create_voice_channel(
                name=f"duel-{number:02d}", category=self.category(guild),
                overwrites=self.overwrites(guild, members), user_limit=len(players),
                reason=f"Duel : {team_a['name']} vs {team_b['name']}",
            )
        except discord.HTTPException:
            delete_duel_session(gid, number)
            raise
        session["voice_id"] = voice.id

        # Historique : une relance reprend le message du duel d'origine et y
        # ajoute une ligne, au lieu d'en publier un nouveau.
        record = get_duel_history(gid).get(str(history_id)) if history_id else None
        if record is None:
            record = {"id": f"{number}-{int(time.time() * 1000)}", "message_id": None,
                      "games": [], "created_at": int(time.time())}
        record["number"] = number
        record["rounds"] = rounds
        for side, team in (("a", team_a), ("b", team_b)):
            for field in ("name", "color"):
                record[f"{field}_{side}"] = session[f"{field}_{side}"]
            record[f"players_{side}"] = list(session[f"players_{side}"])
            # Mémorisé : une team dissoute à la fin du duel garde son lead,
            # qui doit encore pouvoir désigner le vainqueur.
            leader = team.get("leader_id") or (get_duel_team(gid, team["id"]) or {}).get("leader_id")
            if leader:
                record[f"leader_{side}"] = leader
        record["games"].append({"state": "waiting", "rematch": free})
        session["history_id"] = record["id"]
        session["game_index"] = len(record["games"]) - 1
        save_duel_history(gid, record)
        save_duel_session(gid, session)
        await self.update_history(guild, record)
        log.info(f"[{guild.name}] Duel {number:02d} : {team_a['name']} vs {team_b['name']}")

        thread = await self.get_thread(guild, thread_id)
        if thread is not None:
            await throttled_each(players, lambda uid: thread.add_user(discord.Object(id=uid)),
                                 delay=0.2, label="joueurs d'un fil de duel")
            try:
                await thread.send(content=" ".join(f"<@{uid}>" for uid in players),
                                  embed=lobby_embed(gid, session), view=DuelEndView(self, gid),
                                  allowed_mentions=USERS_ONLY)
            except discord.HTTPException as e:
                log.warning(f"[{guild.name}] Annonce du duel non envoyée : {e}")
        await self.check_session(guild, session)
        return session

    async def check_session(self, guild: discord.Guild, session: dict, *, now: float | None = None) -> None:
        """Fait avancer un duel selon qui est en vocal. Appelée à chaque
        mouvement vocal et par la ronde : sans risque si elle passe deux fois."""
        now = time.time() if now is None else now
        gid = guild.id
        key = (gid, session["number"])
        if key in self._launching or str(session["number"]) not in get_duel_sessions(gid):
            return
        players = set(session["players_a"]) | set(session["players_b"])

        if session["phase"] == "waiting":
            if session.get("voice_a_id") or session.get("voice_b_id"):
                # Redémarrage pendant la répartition : la partie était lancée.
                session["phase"] = "playing"
                save_duel_session(gid, session)
            elif not session.get("voice_id"):
                return  # vocal en cours de création
            else:
                voice = guild.get_channel(session["voice_id"])
                if voice is None:
                    await self.end_duel(guild, session, "cancelled")
                elif players <= {m.id for m in voice.members}:
                    await self.launch_duel(guild, session)
                elif now - session.get("created_at", now) > JOIN_TIMEOUT:
                    await self.end_duel(guild, session, "timeout")
                return

        channels = [guild.get_channel(session.get(field) or 0)
                    for field in ("voice_id", "voice_a_id", "voice_b_id")]
        if any(m.id in players for channel in channels if channel is not None for m in channel.members):
            self._empty_since.pop(key, None)
            return
        since = self._empty_since.setdefault(key, now)
        if now - since >= EMPTY_GRACE:
            await self.end_duel(guild, session, "finished")

    async def launch_duel(self, guild: discord.Guild, session: dict) -> None:
        """Tout le monde est là : annonce, vocaux de team, répartition."""
        gid = guild.id
        key = (gid, session["number"])
        if key in self._launching:
            return
        self._launching.add(key)
        try:
            voice = guild.get_channel(session["voice_id"])
            await self.post(guild, session["thread_id"],
                            embed=embeds.base(gid, description=t(gid, "duel.launching"), kind="success"))
            await self.play_announce(voice)

            present = {m.id: m for m in voice.members} if voice is not None else {}
            for side in ("a", "b"):
                ids = session[f"players_{side}"]
                members = [m for m in (guild.get_member(uid) for uid in ids) if m is not None]
                channel = await guild.create_voice_channel(
                    name=f"{session[f'color_{side}']} {session[f'name_{side}']}"[:100],
                    category=getattr(voice, "category", None) or self.category(guild),
                    overwrites=self.overwrites(guild, members), user_limit=len(ids),
                    reason="Duel : vocal de team",
                )
                # Mémorisé tout de suite : un redémarrage au milieu ne doit pas
                # laisser ce vocal orphelin.
                session[f"voice_{side}_id"] = channel.id
                save_duel_session(gid, session)
                movers = [present[uid] for uid in ids if uid in present]
                await throttled_each(movers, lambda m, c=channel: m.move_to(c, reason="Duel : répartition par team"),
                                     delay=0.2, label="répartition d'un duel")

            session["phase"] = "playing"
            session["started_at"] = int(time.time())
            save_duel_session(gid, session)
            await self.set_game(guild, session, state="playing")
            await self.post(guild, session["thread_id"], embed=started_embed(gid, session),
                            view=DuelEndView(self, gid))
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Lancement du duel {session['number']:02d} impossible : {e}")
            await self.post(guild, session["thread_id"], content=t(gid, "duel.err_voice"))
            self._launching.discard(key)
            await self.end_duel(guild, session, "cancelled")
        finally:
            self._launching.discard(key)

    async def play_announce(self, channel) -> None:
        """Le bot rejoint le vocal, annonce le début du duel, puis repart."""
        if channel is None:
            return
        guild = channel.guild
        lock = self._voice_locks.setdefault(guild.id, asyncio.Lock())
        async with lock:
            if guild.voice_client is not None:
                log.warning(f"[{guild.name}] Bot déjà en vocal : annonce du duel sautée")
                return
            client = None
            try:
                client = await channel.connect(timeout=15, reconnect=False)
                client.play(discord.FFmpegPCMAudio(duel_announce_path(guild.id)))
                waited = 0.0
                while client.is_playing() and waited < ANNOUNCE_MAX_SECONDS:
                    await asyncio.sleep(0.2)
                    waited += 0.2
                await asyncio.sleep(1)
            except Exception as e:
                log.error(f"[{guild.name}] Annonce vocale du duel impossible : {e}")
            finally:
                if client is not None and client.is_connected():
                    await client.disconnect(force=True)

    async def end_duel(self, guild: discord.Guild, session: dict, reason: str) -> None:
        """reason : finished, timeout, cancelled ou stopped."""
        gid = guild.id
        if delete_duel_session(gid, session["number"]) is None:
            return  # déjà terminé par un autre chemin
        self._empty_since.pop((gid, session["number"]), None)

        for field in ("voice_a_id", "voice_b_id", "voice_id"):
            channel = guild.get_channel(session.get(field) or 0)
            if channel is not None:
                try:
                    await channel.delete(reason="Duel terminé")
                except discord.HTTPException as e:
                    log.warning(f"[{guild.name}] Vocal de duel non supprimé : {e}")

        lines = [t(gid, f"duel.end_{reason}")]
        played = session.get("phase") == "playing"
        # Une relance est gratuite : elle ne consomme rien, même pour une team
        # dont c'était le dernier duel.
        if played and not session.get("free"):
            for side in ("a", "b"):
                label, _ = session_side(session, side)
                outcome = consume_duel(gid, session[f"team_{side}"])
                team = get_duel_team(gid, session[f"team_{side}"])
                if outcome == "dissolved":
                    lines.append(t(gid, "duel.end_team_dissolved", team=label))
                    await self.drop_team_requests(guild, session[f"team_{side}"])
                elif outcome == "kept" and team is not None:
                    lines.append(t(gid, "duel.end_team_kept", team=label, left=lifetime_text(gid, team)))
        log.info(f"[{guild.name}] Duel {session['number']:02d} terminé ({reason})")
        thread_id = session.get("thread_id")
        extra = {}
        # Relance proposée seulement pour un duel vraiment joué : un défi où
        # personne n'est venu n'a rien à rejouer.
        voting = bool(played and thread_id)
        if voting:
            total = len(set(session["players_a"]) | set(session["players_b"]))
            offer = {"session": dict(session), "votes": set(), "message_id": None}
            self._rematch[(gid, thread_id)] = offer
            lines.append(t(gid, "duel.rematch_hint", minutes=THREAD_GRACE // 60))
            lines.append(t(gid, "duel.win_hint"))
            extra["view"] = DuelRematchView(self, gid, 0, total, labels=winner_labels(gid, session))
        message = await self.post(guild, thread_id,
                                  embed=embeds.base(gid, title=t(gid, "duel.end_title", number=f"{session['number']:02d}"),
                                                    description="\n".join(lines), kind="neutral"),
                                  **extra)
        if voting and message is not None:
            offer["message_id"] = message.id
            await self.set_game(guild, session, state="pending", end_message_id=message.id, thread_id=thread_id)
        else:
            await self.set_game(guild, session, state="undecided" if played else "cancelled")
        add_duel_trash(gid, thread_id, time.time() + THREAD_GRACE)

    async def stop_from_button(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        session = next((s for s in get_duel_sessions(gid).values()
                        if s.get("thread_id") == interaction.channel_id), None) if gid else None
        if session is None:
            await interaction.response.send_message(t(gid, "duel.end_gone"), ephemeral=True)
            return
        leaders = {team.get("leader_id") for team in (get_duel_team(gid, session["team_a"]),
                                                      get_duel_team(gid, session["team_b"])) if team}
        user = interaction.user
        if user.id not in leaders and not getattr(user.guild_permissions, "administrator", False):
            await interaction.response.send_message(t(gid, "duel.err_end_leads_only"), ephemeral=True)
            return
        if (gid, session["number"]) in self._launching:
            await interaction.response.send_message(t(gid, "duel.err_launching"), ephemeral=True)
            return
        await interaction.response.send_message(t(gid, "duel.end_requested", member=user.mention),
                                                allowed_mentions=NO_PINGS)
        await self.end_duel(guild, session, "stopped")

    async def vote_rematch(self, interaction: discord.Interaction) -> None:
        """Un vote pour la relance. Il faut TOUS les joueurs du duel : dès que
        le dernier clique, le même duel repart dans le même fil."""
        gid = interaction.guild_id
        guild = interaction.guild
        key = (gid, interaction.channel_id)
        offer = self._rematch.get(key) if gid else None
        if offer is None or guild is None:
            await interaction.response.send_message(t(gid, "duel.rematch_gone"), ephemeral=True)
            return
        old = offer["session"]
        players = set(old["players_a"]) | set(old["players_b"])
        if interaction.user.id not in players:
            await interaction.response.send_message(t(gid, "duel.rematch_not_player"), ephemeral=True)
            return

        votes: set[int] = offer["votes"]
        # Recliquer retire son vote : on peut changer d'avis.
        votes ^= {interaction.user.id}
        if len(votes) < len(players):
            await interaction.response.edit_message(view=DuelRematchView(
                self, gid, len(votes), len(players), labels=self.pending_labels(gid, interaction)))
            return

        # Tout le monde a voté. L'offre est retirée AVANT tout await : deux
        # derniers clics au même instant ne lancent pas deux duels.
        self._rematch.pop(key, None)
        sessions = list(get_duel_sessions(gid).values())
        busy = next((uid for s in sessions for uid in s.get("players_a", []) + s.get("players_b", [])
                     if uid in players), None)
        error = self.ready_error(guild)
        if error is not None:
            problem = t(gid, error)
        elif busy is not None:
            problem = t(gid, "duel.rematch_busy", player=f"<@{busy}>")
        elif len(sessions) >= MAX_ACTIVE_DUELS or next_duel_number(gid) == 0:
            problem = t(gid, "duel.rematch_full")
        else:
            problem = None
        if problem is not None:
            await interaction.response.edit_message(content=problem, view=self.winner_only_view(gid, interaction),
                                                    allowed_mentions=NO_PINGS)
            return

        # Les boutons du vainqueur restent si la partie n'a pas encore le sien.
        await interaction.response.edit_message(content=t(gid, "duel.rematch_start"),
                                                view=self.winner_only_view(gid, interaction))
        # Le fil devait disparaître dans quelques minutes : la relance le garde.
        cancel_duel_trash(gid, interaction.channel_id)
        team_a, team_b = ({"id": old[f"team_{side}"], "name": old[f"name_{side}"],
                           "color": old[f"color_{side}"], "members": list(old[f"players_{side}"])}
                          for side in ("a", "b"))
        try:
            await self.start_duel(guild, team_a, team_b, interaction.channel_id, free=True,
                                  rounds=old.get("rounds", 1), history_id=old.get("history_id"))
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Relance du duel impossible : {e}")
            await self.post(guild, interaction.channel_id, content=t(gid, "duel.err_voice"))
            add_duel_trash(gid, interaction.channel_id, time.time() + THREAD_GRACE)

    # -- Historique et vainqueur ---------------------------------------------
    async def update_history(self, guild: discord.Guild, record: dict) -> None:
        """Publie le message d'historique, ou le modifie s'il existe déjà."""
        channel = self.requests_channel(guild)
        if channel is None:
            return
        embed = history_embed(guild.id, record)
        try:
            if record.get("message_id"):
                try:
                    await channel.get_partial_message(record["message_id"]).edit(embed=embed)
                    return
                except discord.NotFound:
                    record["message_id"] = None  # supprimé à la main : republié
            message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            record["message_id"] = message.id
            save_duel_history(guild.id, record)
        except Exception as e:
            log.warning(f"[{guild.name}] Historique du duel non mis à jour : {e}")

    async def set_game(self, guild: discord.Guild, session: dict, **fields) -> None:
        """Met à jour la partie de ce duel dans son historique, puis le message."""
        record = get_duel_history(guild.id).get(str(session.get("history_id")))
        index = session.get("game_index")
        if record is None or index is None or index >= len(record.get("games", [])):
            return  # duel lancé avant l'historique
        record["games"][index].update(fields)
        save_duel_history(guild.id, record)
        await self.update_history(guild, record)

    def pending_game(self, guild_id: int | None, interaction: discord.Interaction) -> tuple[dict, int] | None:
        """La partie dont ce message de fin attend encore le vainqueur."""
        message_id = getattr(interaction.message, "id", None)
        found = duel_history_game_by_message(guild_id, message_id) if guild_id else None
        if found is None or found[0]["games"][found[1]].get("state") != "pending":
            return None
        return found

    def pending_labels(self, guild_id: int, interaction: discord.Interaction) -> tuple[str, str] | None:
        found = self.pending_game(guild_id, interaction)
        return winner_labels(guild_id, found[0]) if found else None

    def winner_only_view(self, guild_id: int, interaction: discord.Interaction) -> DuelRematchView | None:
        labels = self.pending_labels(guild_id, interaction)
        return DuelRematchView(self, guild_id, labels=labels, rematch=False, close=False) if labels else None

    async def vote_winner(self, interaction: discord.Interaction, side: str) -> None:
        """Un lead désigne le vainqueur. Enregistré quand les deux leads ont
        choisi la même team ; un administrateur tranche seul."""
        gid = interaction.guild_id
        guild = interaction.guild
        found = self.pending_game(gid, interaction)
        if found is None or guild is None:
            await interaction.response.send_message(t(gid, "duel.win_gone"), ephemeral=True)
            return
        record, index = found
        game = record["games"][index]
        user = interaction.user
        leaders = [record.get(f"leader_{s}") for s in ("a", "b") if record.get(f"leader_{s}")]
        admin = bool(getattr(getattr(user, "guild_permissions", None), "administrator", False))
        if user.id not in leaders and not admin:
            await interaction.response.send_message(t(gid, "duel.win_not_lead"), ephemeral=True)
            return

        label = side_label(record, side)
        votes = game.setdefault("votes", {})
        if user.id in leaders:
            votes[str(user.id)] = side
        agreed = all(votes.get(str(uid)) == side for uid in leaders)
        if not (agreed or admin):
            save_duel_history(gid, record)
            conflict = len(set(votes.values())) > 1
            await interaction.response.send_message(
                t(gid, "duel.win_conflict" if conflict else "duel.win_vote_saved", team=label), ephemeral=True)
            return

        game.update(state="won", winner=side)
        game.pop("votes", None)
        save_duel_history(gid, record)
        # Les boutons du vainqueur partent ; « Relancer » reste s'il est
        # encore proposé sous ce message.
        offer = self._rematch.get((gid, interaction.channel_id))
        view = None
        if offer is not None and offer.get("message_id") == getattr(interaction.message, "id", None):
            old = offer["session"]
            view = DuelRematchView(self, gid, len(offer["votes"]),
                                   len(set(old["players_a"]) | set(old["players_b"])))
        await interaction.response.edit_message(view=view)
        await self.post(guild, interaction.channel_id, content=t(gid, "duel.win_done", team=label),
                        allowed_mentions=NO_PINGS)
        await self.update_history(guild, record)

    async def close_from_button(self, interaction: discord.Interaction) -> None:
        """« Fin » : le match est fini, le fil est supprimé tout de suite au
        lieu d'attendre THREAD_GRACE, et l'historique est mis à jour (une
        partie sans vainqueur désigné le dit)."""
        gid = interaction.guild_id
        guild = interaction.guild
        thread_id = interaction.channel_id
        if guild is None:
            return
        if any(s.get("thread_id") == thread_id for s in get_duel_sessions(gid).values()):
            await interaction.response.send_message(
                t(gid, "duel.close_busy", button=t(gid, "duel.btn_end")), ephemeral=True)
            return

        leaders: set[int | None] = set()
        found = duel_history_game_by_message(gid, getattr(interaction.message, "id", None))
        if found is not None:
            leaders |= {found[0].get("leader_a"), found[0].get("leader_b")}
        offer = self._rematch.get((gid, thread_id))
        if offer is not None:
            old = offer["session"]
            leaders |= {(get_duel_team(gid, old[f"team_{side}"]) or {}).get("leader_id") for side in ("a", "b")}
        leaders.discard(None)
        admin = bool(getattr(getattr(interaction.user, "guild_permissions", None), "administrator", False))
        if interaction.user.id not in leaders and not admin:
            await interaction.response.send_message(t(gid, "duel.close_not_lead"), ephemeral=True)
            return

        await interaction.response.defer()
        self._rematch.pop((gid, thread_id), None)
        cancel_duel_trash(gid, thread_id)
        await self.close_pending_games(guild, thread_id)
        await self.delete_thread(guild, thread_id)
        log.info(f"[{guild.name}] Fil de duel fermé par {interaction.user}")

    async def close_pending_games(self, guild: discord.Guild, thread_id: int) -> None:
        """Fil supprimé sans vainqueur désigné : la partie le dit dans l'historique."""
        for record in list(get_duel_history(guild.id).values()):
            changed = False
            for game in record.get("games", []):
                if game.get("state") == "pending" and game.get("thread_id") == thread_id:
                    game["state"] = "undecided"
                    game.pop("votes", None)
                    changed = True
            if changed:
                save_duel_history(guild.id, record)
                await self.update_history(guild, record)

    # -- Surveillance --------------------------------------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if member.bot:
            return
        moved = {channel.id for channel in (before.channel, after.channel) if channel is not None}
        if not moved:
            return
        for session in list(get_duel_sessions(member.guild.id).values()):
            if moved & {session.get("voice_id"), session.get("voice_a_id"), session.get("voice_b_id")}:
                await self.check_session(member.guild, session)

    async def tick(self, guild: discord.Guild, now: float | None = None) -> None:
        """Une ronde : défis et invitations expirés, duels à faire avancer,
        fils à supprimer. Tout ce qui dépend du temps passe par ici, ce qui
        rend le système insensible à un redémarrage."""
        now = time.time() if now is None else now
        gid = guild.id
        for request in list(get_duel_requests(gid)):
            if now - request.get("at", now) > REQUEST_TTL and remove_duel_request(gid, request["message_id"]):
                await self.close_request(guild, request, "duel.req_expired")
        for team in list(get_duel_teams(gid).values()):
            if team.get("status") == "pending" and now - team.get("created_at", now) > INVITE_TTL:
                delete_duel_team(gid, team["id"])
                await self.close_invite(guild, team, "duel.inv_expired")
        for session in list(get_duel_sessions(gid).values()):
            await self.check_session(guild, session, now=now)
        for thread_id in pop_due_duel_trash(gid, now):
            self._rematch.pop((gid, thread_id), None)
            await self.close_pending_games(guild, thread_id)
            await self.delete_thread(guild, thread_id)

    async def _watch_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(WATCH_EVERY)
                for guild in list(self.bot.guilds):
                    try:
                        await self.tick(guild)
                    except Exception:
                        log.exception(f"[{guild.name}] Ronde des duels interrompue")
            except asyncio.CancelledError:
                return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Duel(bot))
    log.info("Cog Duel chargé")
