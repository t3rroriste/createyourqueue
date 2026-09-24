"""
Cog : Queue System
==================
Système de queue avec embed et boutons, sans formulaires.
"""

import asyncio
import hmac
import logging
import json
import os
import re
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select

import custom_emojis
import embeds
import resources
from guild_settings import (
    MAX_QUEUE_PRESETS,
    get_mmr_config,
    save_queue_config,
    get_queue_config,
    queue_ready,
    mark_first_queue,
    get_webhook_url,
    get_queue_presets,
    get_queue_preset,
    save_queue_preset,
    get_saved_teams,
    add_saved_team,
    get_queue_history,
    add_queue_history_entry,
    get_queue_blacklist,
    get_queue_blacklist_entries,
    add_to_queue_blacklist,
    remove_from_queue_blacklist,
    active_queue_password,
    is_status_panel_message,
)
from i18n import t, t_in, get_lang
from rate_limit import throttled_each
from text_safety import NO_PINGS, USERS_ONLY, sanitize
from json_store import write_json
from cogs.logs import send_log

log = logging.getLogger("bot.queue_config")

# Sessions actives sérialisées sur disque : sans ça, un redémarrage du bot
# laisse une annonce avec des boutons morts et un vocal verrouillé.
SESSIONS_FILE = "data/queue_sessions.json"

# Palette proposée par le bouton "Couleur" — (emoji, nom FR, nom EN)
COLOR_PALETTE = [
    ("🔴", "Rouge", "Red"),
    ("🔵", "Bleu", "Blue"),
    ("🟢", "Vert", "Green"),
    ("🟡", "Jaune", "Yellow"),
    ("🟣", "Violet", "Purple"),
    ("🟠", "Orange", "Orange"),
    ("⚪", "Blanc", "White"),
    ("⚫", "Noir", "Black"),
    ("🟤", "Marron", "Brown"),
    ("🩷", "Rose", "Pink"),
    ("🩵", "Cyan", "Cyan"),
    ("🟦", "Bleu marine", "Navy"),
]
DEFAULT_TEAM_CIRCLES = [c[0] for c in COLOR_PALETTE[:8]]

# Bornes des menus « nombre d'équipes » et « joueurs par équipe ».
TEAMS_MIN, TEAMS_MAX = 2, 6
PLAYERS_MIN, PLAYERS_MAX = 1, 6


def color_name(lang: str, emoji: str) -> str:
    """Nom d'une couleur de la palette dans une langue donnée."""
    names = t_in(lang, "queue.colors").split("|")
    for i, (candidate, _fr, name_en) in enumerate(COLOR_PALETTE):
        if candidate == emoji:
            return names[i] if i < len(names) and names[i] else name_en
    return emoji

# Annonce vocale de lancement, une par langue (même texte que la voix française
# d'origine, traduit — voir queue_announce_<lang>.mp3). queue_announce.mp3 reste
# le fichier français historique, inchangé, utilisé comme repli si un fichier
# traduit venait à manquer.
VOICE_ANNOUNCE_FILES = {
    "fr": "queue_announce.mp3",
    "en": "queue_announce_en.mp3",
    "es": "queue_announce_es.mp3",
    "de": "queue_announce_de.mp3",
    "ko": "queue_announce_ko.mp3",
}


def voice_announce_path(guild_id: int | None) -> str:
    """Chemin de l'annonce vocale dans la langue du serveur, avec repli sur le
    français si le fichier traduit est absent du disque."""
    path = VOICE_ANNOUNCE_FILES.get(get_lang(guild_id), VOICE_ANNOUNCE_FILES["fr"])
    return path if os.path.exists(path) else VOICE_ANNOUNCE_FILES["fr"]

# Boutons du panneau de configuration : (attribut, emoji, clé du libellé, clé de la description)
# Source unique pour l'emoji et le libellé des boutons ET pour la légende de l'embed :
# tant que les deux étaient écrits séparément, ils divergeaient à chaque changement.
PANEL_BUTTONS = [
    ("title_button", "📛", "queue.btn_title", "queue.btn_title_desc"),
    ("teams_button", "👥", "queue.btn_teams", "queue.btn_teams_desc"),
    ("session_button", "🗓️", "queue.btn_session", "queue.btn_session_desc"),
    ("heure_button", "🕒", "queue.btn_heure", "queue.btn_heure_desc"),
    ("type_button", "🏷️", "queue.btn_type", "queue.btn_type_desc"),
    ("captains_button", "🎖️", "queue.btn_captains", "queue.btn_captains_desc"),
    ("preset_button", "💾", "queue.btn_preset", "queue.btn_preset_desc"),
    ("save_preset_button", "📥", "queue.btn_save_preset", "queue.btn_save_preset_desc"),
    ("start_button", "✅", "queue.btn_start", "queue.btn_start_desc"),
]


def preset_summary(guild_id: int, preset: dict) -> str:
    """Résumé d'une ligne : ce qu'un preset publiera concrètement."""
    return t(
        guild_id, "queue.preset_summary",
        queue=sanitize(str(preset.get("queue_name", "Queue")), 60),
        teams=preset.get("num_teams", 2),
        players=preset.get("max_players_per_team", 4),
        type=sanitize(str(preset.get("type") or "—"), 40),
    )


def build_panel_description(guild_id: int | None) -> str:
    """Légende du panneau, construite depuis PANEL_BUTTONS : chaque ligne reprend
    l'emoji et le libellé réels du bouton correspondant, dans la langue du serveur."""
    lines = [t(guild_id, "queue.panel_intro"), ""]
    for _, emoji, label_key, desc_key in PANEL_BUTTONS:
        lines.append(f"{emoji} **{t(guild_id, label_key)}** — {t(guild_id, desc_key)}")
    return "\n".join(lines)


class QueueSession:
    """Représente une session de queue en cours."""
    
    def __init__(self, author, announcement_channel, queue_config):
        self.author = author
        self.guild_id = author.guild.id
        self.announcement_channel = announcement_channel
        self.queue_config = queue_config
        self.message = None
        self.launch_message = None  # panel "Lancer la partie" dans le salon queue
        self.result_message = None  # panel de suivi des scores dans le salon queue
        self.waiting_channel = None
        self.config_channel = None
        self.team_channels = {}  # team_name -> discord.VoiceChannel, créés au lancement
        self.waiting_players = []
        self.teams = {}
        self.team_colors = {}
        self.started = False
        self.ended = False
        self.winner = None
        self.win_log = []  # [(team_name, datetime), ...] chronologique
        self.full_alert_sent = False  # évite de re-notifier l'organisateur à chaque réaction une fois plein
        # Mot de passe demandé pour s'inscrire (/option → Mot de passe), figé à
        # la publication. None : inscription par la réaction ✅.
        self.password = None

        # Initialiser les équipes avec couleurs
        colors = [0xFF0000, 0x0000FF, 0x00FF00, 0xFFFF00, 0xFF00FF, 0x00FFFF, 0xFFA500, 0x800080, 0x008080, 0xFFC0CB]
        for i, team_name in enumerate(queue_config.get("team_names", [])):
            self.teams[team_name] = []
            self.team_colors[team_name] = colors[i % len(colors)]

    def get_capacity(self):
        return self.queue_config.get("max_players_per_team", 4) * len(self.teams)

    def add_waiting(self, member):
        """Ajoute un joueur à la file d'attente (pas encore réparti en équipe)."""
        if member in self.waiting_players:
            return True
        if len(self.waiting_players) >= self.get_capacity():
            return False
        self.waiting_players.append(member)
        return True

    def remove_waiting(self, member):
        """Retire un joueur de la file d'attente."""
        if member in self.waiting_players:
            self.waiting_players.remove(member)
            return True
        return False

    def launch(self):
        """Répartit la file d'attente dans les équipes et démarre la partie."""
        team_names = list(self.teams.keys())
        max_players = self.queue_config.get("max_players_per_team", 4)
        for team_name in team_names:
            self.teams[team_name] = []

        players = list(self.waiting_players)

        # Duos, trios et quatros sont placés d'un bloc : séparer un groupe
        # qui a explicitement demandé à jouer ensemble viderait la promesse
        # faite au moment du /duo.
        guild = getattr(self.author, "guild", None)
        if guild is not None:
            try:
                from cogs.party import group_players
                blocks = group_players(guild, players)
            except Exception as e:
                log.error(f"Groupes ignorés dans la répartition : {e}")
                blocks = [[m] for m in players]
        else:
            blocks = [[m] for m in players]
        # Les plus gros blocs d'abord : un trio placé en dernier ne trouve
        # plus trois places libres côte à côte.
        blocks.sort(key=len, reverse=True)

        index, step = 0, 1
        for block in blocks:
            placed = False
            for _ in range(len(team_names)):
                name = team_names[index]
                if len(self.teams[name]) + len(block) <= max_players:
                    self.teams[name].extend(block)
                    placed = True
                    break
                index, step = self._next_index(index, step, len(team_names))
            if not placed:
                # Aucune équipe ne peut accueillir le bloc entier : ses membres
                # sont replacés un par un plutôt que laissés de côté.
                for member in block:
                    for _ in range(len(team_names)):
                        name = team_names[index]
                        if len(self.teams[name]) < max_players:
                            self.teams[name].append(member)
                            break
                        index, step = self._next_index(index, step, len(team_names))
                    index, step = self._next_index(index, step, len(team_names))
                continue
            index, step = self._next_index(index, step, len(team_names))
        self.started = True

    @staticmethod
    def _next_index(index: int, step: int, size: int) -> tuple[int, int]:
        """Avance dans les équipes en serpentin : 0,1,2 puis 2,1,0, etc."""
        if size <= 1:
            return 0, step
        nxt = index + step
        if nxt >= size or nxt < 0:
            # Arrivé au bout : on change de sens SANS bouger.
            step = -step
            nxt = index
        return nxt, step

    def get_total_players(self):
        return sum(len(team) for team in self.teams.values())

    def is_waiting_full(self):
        """La file d'attente a-t-elle atteint la capacité totale (avant lancement) ?"""
        return len(self.waiting_players) >= self.get_capacity()

    def is_full(self):
        max_players = self.queue_config.get("max_players_per_team", 4)
        return all(len(team) >= max_players for team in self.teams.values())

    # ------------------------------------------------------------------
    # Persistance (survie au redémarrage du bot)
    # ------------------------------------------------------------------
    def to_dict(self):
        """Sérialise la session en IDs — les objets discord.py ne sont pas picklables
        et deviennent obsolètes après un redémarrage."""
        return {
            "guild_id": self.guild_id,
            "author_id": getattr(self.author, "id", None),
            "queue_config": self.queue_config,
            "announcement_channel_id": getattr(self.announcement_channel, "id", None),
            "message_id": getattr(self.message, "id", None),
            "config_channel_id": getattr(self.config_channel, "id", None),
            "launch_message_id": getattr(self.launch_message, "id", None),
            "result_message_id": getattr(self.result_message, "id", None),
            "waiting_channel_id": getattr(self.waiting_channel, "id", None),
            "team_channel_ids": {name: ch.id for name, ch in self.team_channels.items()},
            "waiting_player_ids": [m.id for m in self.waiting_players],
            "team_member_ids": {name: [m.id for m in members] for name, members in self.teams.items()},
            "started": self.started,
            "ended": self.ended,
            "winner": self.winner,
            "win_log": [(team, ts.isoformat()) for team, ts in self.win_log],
            "password": self.password,
        }

    @classmethod
    def from_dict(cls, guild: discord.Guild, data: dict):
        """Reconstruit une session depuis le disque. Retourne None si le serveur,
        l'organisateur ou le message d'annonce n'existent plus."""
        author = guild.get_member(data.get("author_id") or 0)
        if author is None:
            return None

        announcement_channel = guild.get_channel(data.get("announcement_channel_id") or 0)
        if announcement_channel is None:
            return None

        session = cls(author, announcement_channel, data.get("queue_config", {}))

        # Messages : PartialMessage suffit pour .edit()/.remove_reaction() et évite un appel API
        if data.get("message_id"):
            session.message = announcement_channel.get_partial_message(data["message_id"])

        config_channel = guild.get_channel(data.get("config_channel_id") or 0)
        session.config_channel = config_channel
        if config_channel:
            if data.get("launch_message_id"):
                session.launch_message = config_channel.get_partial_message(data["launch_message_id"])
            if data.get("result_message_id"):
                session.result_message = config_channel.get_partial_message(data["result_message_id"])

        session.waiting_channel = guild.get_channel(data.get("waiting_channel_id") or 0)
        for name, cid in (data.get("team_channel_ids") or {}).items():
            channel = guild.get_channel(cid)
            if channel:
                session.team_channels[name] = channel

        session.waiting_players = [
            m for m in (guild.get_member(uid) for uid in data.get("waiting_player_ids", [])) if m
        ]
        for name, ids in (data.get("team_member_ids") or {}).items():
            if name in session.teams:
                session.teams[name] = [m for m in (guild.get_member(uid) for uid in ids) if m]

        session.started = data.get("started", False)
        session.ended = data.get("ended", False)
        session.winner = data.get("winner")
        session.password = data.get("password") or None
        session.win_log = [
            (team, datetime.fromisoformat(ts)) for team, ts in data.get("win_log", [])
        ]
        return session
    
    def build_embed(self):
        """Une seule et même base d'embed pour les trois états de l'annonce
        (inscriptions, partie lancée, match terminé) : seuls la ligne de statut
        et le pied de page changent."""
        return self._embed_preparation()

    def _embed_preparation(self):
        """Embed de l'annonce — même base pour les trois états (inscriptions,
        partie lancée, match terminé) : seuls le bloc central et le pied de
        page changent."""
        gid = self.guild_id
        cfg = self.queue_config
        queue_name = sanitize(str(cfg.get("queue_name", "Queue")), 80)

        embed = discord.Embed(
            title=t(gid, "queue.ann_title", name=queue_name),
            color=embeds.BLACK,
        )

        # Tout le corps tient dans la description : des champs séparés
        # espaçaient chaque ligne et étiraient l'annonce sur deux écrans.
        block = [t(gid, "queue.ann_by", author=self.author.mention), ""]

        team_colors = cfg.get("team_colors", {})
        for i, (team_name, members) in enumerate(self.teams.items()):
            circle = team_colors.get(team_name, DEFAULT_TEAM_CIRCLES[i % len(DEFAULT_TEAM_CIRCLES)])
            trophy = " 🏆" if self.winner == team_name else ""
            block.append(
                t(gid, "queue.ann_team_line",
                  n=i + 1, name=sanitize(team_name, 60), color=circle) + trophy
            )
            # Une fois la partie lancée, la composition s'affiche sous l'équipe.
            if self.started and members:
                block.append(" ".join(m.mention for m in members))

        if cfg.get("session"):
            block.append(t(gid, "queue.ann_session", value=sanitize(str(cfg["session"]), 80)))

        # Seule cette dernière ligne change d'un état à l'autre : le reste de
        # l'annonce garde exactement la même forme du début à la fin, pour
        # qu'on reconnaisse le message d'un coup d'œil.
        block.append("")
        if self.ended:
            block.append(t(gid, "queue.embed_finished"))
            # Raccourcis vers le détail du match et le classement, comme sur
            # le message de fin : on suit le lien au lieu de chercher le salon.
            guild = getattr(self.author, "guild", None)
            links = []
            if guild is not None:
                resultat = resources.get_text_channel(guild, "channel_queue_resultat")
                if resultat is not None:
                    links.append(t(gid, "queue.finished_result_link", channel=resultat.mention))
                classement = resources.get_text_channel(guild, "channel_queue_classement")
                if classement is not None:
                    links.append(t(gid, "queue.finished_ranking_link", channel=classement.mention))
            block.extend(links)
        elif self.started:
            block.append(t(gid, "queue.ann_started"))
        else:
            voice_name = resources.resource_name(gid, "voice_queue_waiting")
            cta = "queue.ann_cta_password" if self.password else "queue.ann_cta"
            block.append(t(gid, cta, channel=voice_name))
        embed.description = "\n".join(block)

        # Heure et type côte à côte, en bas, comme sur l'annonce d'origine.
        embed.add_field(
            name=t(gid, "queue.field_time"),
            value=f"**{sanitize(str(cfg.get('heure') or '—'), 20)}**",
            inline=True,
        )
        embed.add_field(
            name=t(gid, "queue.field_type"),
            value=f"**{sanitize(str(cfg.get('type') or '—'), 40)}**",
            inline=True,
        )

        if self.ended:
            embed.set_footer(text=t(gid, "queue.finished_footer"))
        elif not self.started:
            embed.set_footer(text=t(gid, "queue.ann_footer_password" if self.password
                                    else "queue.ann_footer_join"))
        return embed


class SingleFieldModal(discord.ui.Modal):
    """Modal générique à un seul champ texte, écrit dans self.target_config[config_key]."""

    def __init__(self, title, label, default, config_key, target_config, lang, placeholder=None):
        super().__init__(title=title)
        self.config_key = config_key
        self.target_config = target_config
        self.lang = lang
        self.input = discord.ui.TextInput(
            label=label,
            default=default or "",
            placeholder=placeholder,
            required=True,
            max_length=100,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.target_config[self.config_key] = self.input.value
        await interaction.response.send_message(
            content=(
                f"✅ Mis à jour : {sanitize(self.input.value, 100)}" if self.lang != "en"
                else f"✅ Updated: {sanitize(self.input.value, 100)}"
            ),
            allowed_mentions=NO_PINGS,
            ephemeral=True,
        )


class TeamNameModal(discord.ui.Modal):
    """Saisie du nom d'une nouvelle équipe, depuis le menu des noms d'équipe."""

    def __init__(self, picker):
        self.picker = picker
        gid = picker.guild_id
        super().__init__(title=t(gid, "queue.lib_create_modal_title"))
        self.name_input = discord.ui.TextInput(
            label=t(gid, "queue.lib_create_modal_label"),
            max_length=50,
            required=True,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.picker.prompt_color(interaction, sanitize(self.name_input.value.strip(), 50))


class TeamSearchModal(discord.ui.Modal):
    """Filtre la bibliothèque d'équipes par nom."""

    def __init__(self, picker):
        self.picker = picker
        gid = picker.guild_id
        super().__init__(title=t(gid, "queue.lib_search_modal_title"))
        self.query_input = discord.ui.TextInput(
            label=t(gid, "queue.lib_search_modal_label"),
            max_length=50,
            required=False,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.picker.apply_filter(interaction, sanitize(self.query_input.value.strip(), 50))


# Modes de tri proposés par le menu des noms d'équipe.
SORT_MODES = ["az", "za", "num"]


def _natural_key(name: str):
    """Découpe le nom en morceaux texte/nombre pour que « Team2 » passe avant
    « Team10 » — un tri purement alphabétique les mettrait dans l'autre sens."""
    return [
        (0, int(chunk), "") if chunk.isdigit() else (1, 0, chunk.lower())
        for chunk in re.split(r"(\d+)", name)
        if chunk
    ]


def sort_teams(teams: list[dict], mode: str) -> list[dict]:
    """A→Z et Z→A rangent les noms qui commencent par un chiffre à la fin ;
    le mode 0-9 les remonte en tête. Les trois donnent donc bien trois ordres
    différents, et les nombres restent triés numériquement dans tous les cas."""
    def starts_with_digit(team: dict) -> bool:
        return team["name"][:1].isdigit()

    if mode == "za":
        return sorted(teams, key=lambda x: (starts_with_digit(x), _natural_key(x["name"])), reverse=True)
    if mode == "num":
        return sorted(teams, key=lambda x: (not starts_with_digit(x), _natural_key(x["name"])))
    return sorted(teams, key=lambda x: (starts_with_digit(x), _natural_key(x["name"])))


class TeamPickerView(View):
    """Menu contextuel des noms d'équipe, sur le modèle du bouton Couleur :
    on choisit d'abord l'équipe à modifier, puis son nom et sa couleur."""

    MAX_OPTIONS = 25

    def __init__(self, config_view, slot: int, query: str = "", sort_mode: str = "az"):
        super().__init__(timeout=300)
        self.config_view = config_view
        self.guild_id = config_view.guild_id
        self.slot = slot
        self.query = query
        self.sort_mode = sort_mode
        self._build()

    # -- données -------------------------------------------------------
    @property
    def current_name(self) -> str:
        names = self.config_view.config.get("team_names", [])
        return names[self.slot] if self.slot < len(names) else "—"

    @property
    def current_color(self) -> str:
        colors = self.config_view.config.get("team_colors", {})
        return colors.get(self.current_name, DEFAULT_TEAM_CIRCLES[self.slot % len(DEFAULT_TEAM_CIRCLES)])

    def _matching_teams(self) -> list[dict]:
        teams = get_saved_teams(self.guild_id)
        if self.query:
            needle = self.query.lower()
            teams = [team for team in teams if needle in team["name"].lower()]
        return sort_teams(teams, self.sort_mode)

    def content(self) -> str:
        gid = self.guild_id
        header = t(gid, "queue.lib_editing", slot=self.slot + 1, name=self.current_name, color=self.current_color)
        teams = self._matching_teams()
        if not teams:
            body = t(gid, "queue.lib_search_none", query=self.query) if self.query else t(gid, "queue.lib_empty")
            return header + "\n\n" + body

        if self.query:
            body = t(gid, "queue.lib_search_results", count=len(teams), query=self.query)
        else:
            body = t(gid, "queue.lib_title", count=len(teams))
        lines = [f"{team['color']} **{team['name']}**" for team in teams[: self.MAX_OPTIONS]]
        if len(teams) > self.MAX_OPTIONS:
            lines.append(t(gid, "queue.lib_truncated"))
        return header + "\n\n" + body + "\n" + "\n".join(lines)

    def sort_label(self) -> str:
        return t(self.guild_id, f"queue.lib_sort_{self.sort_mode}")

    # -- construction de la vue ----------------------------------------
    def _build(self) -> None:
        self.clear_items()
        gid = self.guild_id
        teams = self._matching_teams()

        if teams:
            select = Select(
                placeholder=t(gid, "queue.lib_select_placeholder"),
                options=[
                    discord.SelectOption(label=team["name"], emoji=team["color"], value=team["name"])
                    for team in teams[: self.MAX_OPTIONS]
                ],
                row=0,
            )
            select.callback = self._make_apply_callback(select)
            self.add_item(select)

        create = Button(label=t(gid, "queue.lib_btn_create"), style=discord.ButtonStyle.success, emoji="➕", row=1)
        create.callback = self._create_callback
        self.add_item(create)

        search = Button(label=t(gid, "queue.lib_btn_search"), style=discord.ButtonStyle.primary, emoji="🔍", row=1)
        search.callback = self._search_callback
        self.add_item(search)

        sort = Button(
            label=t(gid, "queue.lib_btn_sort", mode=self.sort_label()),
            style=discord.ButtonStyle.secondary,
            emoji="🔤",
            row=1,
        )
        sort.callback = self._sort_callback
        self.add_item(sort)

        if self.query:
            reset = Button(label=t(gid, "queue.lib_btn_all"), style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
            reset.callback = self._reset_callback
            self.add_item(reset)

    async def refresh(self, interaction: discord.Interaction, prefix: str = ""):
        self._build()
        content = (prefix + "\n\n" if prefix else "") + self.content()
        await interaction.response.edit_message(content=content, view=self)

    # -- callbacks -----------------------------------------------------
    async def _create_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TeamNameModal(self))

    async def _search_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TeamSearchModal(self))

    async def _reset_callback(self, interaction: discord.Interaction):
        await self.apply_filter(interaction, "")

    async def _sort_callback(self, interaction: discord.Interaction):
        self.sort_mode = SORT_MODES[(SORT_MODES.index(self.sort_mode) + 1) % len(SORT_MODES)]
        await self.refresh(interaction)

    async def apply_filter(self, interaction: discord.Interaction, query: str):
        self.query = query
        await self.refresh(interaction)

    def apply_team(self, name: str, color: str):
        """Écrit le nom et la couleur choisis dans le slot en cours d'édition."""
        cfg = self.config_view.config
        names = list(cfg.get("team_names", []))
        if self.slot >= len(names):
            return
        replaced = names[self.slot]
        names[self.slot] = name
        cfg["team_names"] = names
        # Réassignation plutôt que mutation : self.config peut être un .copy() de preset.
        colors = {k: v for k, v in cfg.get("team_colors", {}).items() if k != replaced}
        colors[name] = color
        cfg["team_colors"] = colors

    def _make_apply_callback(self, select: Select):
        async def callback(interaction: discord.Interaction):
            chosen = select.values[0]
            team = next((x for x in get_saved_teams(self.guild_id) if x["name"] == chosen), None)
            if team is None:
                await self.refresh(interaction)
                return
            self.apply_team(team["name"], team["color"])
            await self.refresh(
                interaction,
                t(self.guild_id, "queue.lib_applied", slot=self.slot + 1, name=team["name"], color=team["color"]),
            )

        return callback

    async def prompt_color(self, interaction: discord.Interaction, name: str):
        """Deuxième étape de la création : la couleur, puis enregistrement
        dans la bibliothèque et application au slot."""
        gid = self.guild_id
        if not name:
            await self.refresh(interaction)
            return

        lang = get_lang(gid)
        color_select = Select(
            placeholder=t(gid, "queue.lib_color_placeholder", name=name)[:150],
            options=[
                discord.SelectOption(label=color_name(lang, emoji), emoji=emoji, value=emoji)
                for emoji, _fr, _en in COLOR_PALETTE
            ],
        )

        async def color_callback(color_interaction: discord.Interaction):
            chosen = color_select.values[0]
            add_saved_team(gid, name, chosen)
            self.apply_team(name, chosen)
            self.query = ""
            await self.refresh(
                color_interaction,
                t(gid, "queue.lib_saved", name=name, color=chosen)
                + "\n"
                + t(gid, "queue.lib_applied", slot=self.slot + 1, name=name, color=chosen),
            )

        color_select.callback = color_callback
        color_view = View(timeout=300)
        color_view.add_item(color_select)
        await interaction.response.edit_message(
            content=t(gid, "queue.lib_color_step", name=name),
            view=color_view,
        )


class TeamsBuilderView(View):
    """Tout ce qui concerne les équipes, au même endroit."""

    def __init__(self, config_view: "QueueConfigView"):
        super().__init__(timeout=300)
        self.config_view = config_view
        self.guild_id = config_view.guild_id
        gid = self.guild_id
        config = config_view.config

        teams = Select(
            placeholder=t(gid, "queue.cfg_teams_ph"),
            options=[
                discord.SelectOption(
                    label=t(gid, "queue.cfg_teams_opt", n=n), value=str(n),
                    default=n == config.get("num_teams", 2),
                )
                for n in range(TEAMS_MIN, TEAMS_MAX + 1)
            ],
            row=0,
        )
        teams.callback = self._set_teams(teams)
        self.add_item(teams)

        players = Select(
            placeholder=t(gid, "queue.cfg_players_ph"),
            options=[
                discord.SelectOption(
                    label=t(gid, "queue.cfg_players_opt", n=n), value=str(n),
                    default=n == config.get("max_players_per_team", 4),
                )
                for n in range(PLAYERS_MIN, PLAYERS_MAX + 1)
            ],
            row=1,
        )
        players.callback = self._set_players(players)
        self.add_item(players)

        names = config.get("team_names", [])
        colors = config.get("team_colors", {})
        edit = Select(
            placeholder=t(gid, "queue.cfg_team_ph"),
            options=[
                discord.SelectOption(
                    label=f"{i + 1}. {name}"[:100],
                    value=str(i),
                    emoji=colors.get(name, DEFAULT_TEAM_CIRCLES[i % len(DEFAULT_TEAM_CIRCLES)]),
                )
                for i, name in enumerate(names)
            ] or [discord.SelectOption(label="—", value="0")],
            row=2,
        )
        edit.callback = self._edit_team(edit)
        self.add_item(edit)

    def embed(self) -> discord.Embed:
        """Récapitulatif de la composition telle qu'elle est réglée."""
        gid = self.guild_id
        config = self.config_view.config
        colors = config.get("team_colors", {})
        per_team = config.get("max_players_per_team", 4)
        lines = [
            f"{colors.get(name, DEFAULT_TEAM_CIRCLES[i % len(DEFAULT_TEAM_CIRCLES)])} "
            f"・**{sanitize(name, 60)}** — {t(gid, 'queue.cfg_players_opt', n=per_team)}"
            for i, name in enumerate(config.get("team_names", []))
        ]
        embed = embeds.base(
            gid,
            title=t(gid, "queue.builder_title"),
            description=t(gid, "queue.builder_desc") + "\n\n" + ("\n".join(lines) or "—"),
            footer=t(gid, "queue.builder_footer"),
        )
        return embed

    async def refresh(self, interaction: discord.Interaction) -> None:
        """Le menu des équipes dépend de leur nombre : on reconstruit la vue."""
        fresh = TeamsBuilderView(self.config_view)
        await interaction.response.edit_message(embed=fresh.embed(), view=fresh)

    def _set_teams(self, select: Select):
        async def callback(interaction: discord.Interaction) -> None:
            gid = self.guild_id
            count = int(select.values[0])
            config = self.config_view.config
            config["num_teams"] = count
            # On garde les noms déjà personnalisés et on complète le reste :
            # changer le nombre d'équipes ne doit pas effacer le travail fait.
            names = list(config.get("team_names", []))[:count]
            while len(names) < count:
                names.append(t(gid, "queue.team_default", n=len(names) + 1))
            config["team_names"] = names
            config["team_colors"] = {
                name: color for name, color in config.get("team_colors", {}).items()
                if name in names
            }
            await self.refresh(interaction)
        return callback

    def _set_players(self, select: Select):
        async def callback(interaction: discord.Interaction) -> None:
            self.config_view.config["max_players_per_team"] = int(select.values[0])
            await self.refresh(interaction)
        return callback

    def _edit_team(self, select: Select):
        async def callback(interaction: discord.Interaction) -> None:
            if not self.config_view.config.get("team_names"):
                await self.refresh(interaction)
                return
            picker = TeamPickerView(self.config_view, int(select.values[0]))
            await interaction.response.edit_message(
                content=picker.content(), embed=None, view=picker
            )
        return callback


class QueueConfigView(View):
    """Vue pour la configuration de queue avec boutons."""

    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.config = {
            "queue_name": "Queue",
            "num_teams": 2,
            "team_names": ["Team 1", "Team 2"],
            "max_players_per_team": 4,
            "session": t(guild_id, "auto.preset_session_default"),
            "heure": None,
            "type": t(guild_id, "auto.preset_type_default"),
            # Vote des capitaines : part du réglage du serveur (/option → MMR),
            # et se coupe pour cette queue-là sans le modifier — une partie
            # entre amis n'a pas besoin de draft, celle du soir si.
            "captains": bool(get_mmr_config(guild_id).get("captains")),
        }

        for attr, emoji, label_key, _ in PANEL_BUTTONS:
            button = getattr(self, attr)
            button.label = t(guild_id, label_key)
            button.emoji = emoji
        self.sync_captains()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Le panneau est posté dans le salon : sans ce contrôle, n'importe quel
        # membre pouvait le régler et publier la queue avec son @everyone.
        if self.cog._is_staff(interaction.user):
            return True
        await interaction.response.send_message(t(self.guild_id, "queue.organizers_only"), ephemeral=True)
        return False

    def sync_captains(self) -> None:
        """Le bouton dit son état : vert allumé, gris éteint."""
        gid = self.guild_id
        config = get_mmr_config(gid)
        on = bool(self.config.get("captains"))
        self.captains_button.style = (discord.ButtonStyle.success if on
                                      else discord.ButtonStyle.secondary)
        self.captains_button.disabled = not config.get("enabled")

    @discord.ui.button(label="Titre", style=discord.ButtonStyle.secondary, row=0)
    async def title_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Change le titre de l'annonce."""
        gid = self.guild_id
        modal = SingleFieldModal(
            title=t(gid, "queue.cfg_title_modal"),
            label=t(gid, "queue.cfg_title_label"),
            default=self.config.get("queue_name", "Queue"),
            config_key="queue_name",
            target_config=self.config,
            lang=get_lang(gid),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Teams", style=discord.ButtonStyle.secondary, row=0)
    async def teams_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ouvre le constructeur d'équipes."""
        view = TeamsBuilderView(self)
        await interaction.response.send_message(
            embed=view.embed(), view=view, ephemeral=True
        )

    @discord.ui.button(label="Session", style=discord.ButtonStyle.secondary, row=0)
    async def session_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Configure le nom/numéro de la session."""
        gid = self.guild_id
        modal = SingleFieldModal(
            title=t(gid, "queue.cfg_session_modal"),
            label=t(gid, "queue.cfg_session_label"),
            default=self.config.get("session") or t(gid, "auto.preset_session_default"),
            config_key="session",
            target_config=self.config,
            lang=get_lang(gid),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Heure", style=discord.ButtonStyle.secondary, row=1)
    async def heure_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Configure l'heure de la session."""
        gid = self.guild_id
        modal = SingleFieldModal(
            title=t(gid, "queue.cfg_time_modal"),
            label=t(gid, "queue.cfg_time_label"),
            default=self.config.get("heure") or "",
            config_key="heure",
            target_config=self.config,
            lang=get_lang(gid),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Type", style=discord.ButtonStyle.secondary, row=1)
    async def type_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Configure le type de session (texte libre)."""
        gid = self.guild_id
        modal = SingleFieldModal(
            title=t(gid, "queue.cfg_type_modal"),
            label=t(gid, "queue.cfg_type_label"),
            default=self.config.get("type") or t(gid, "auto.preset_type_default"),
            config_key="type",
            target_config=self.config,
            lang=get_lang(gid),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Captains", style=discord.ButtonStyle.secondary, row=1)
    async def captains_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Active ou coupe le vote des capitaines pour cette queue."""
        self.config["captains"] = not self.config.get("captains")
        self.sync_captains()
        # La légende du panneau ne bouge pas : c'est la couleur du bouton qui
        # dit l'état, donc on ne réécrit que la vue.
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Preset", style=discord.ButtonStyle.primary, row=2)
    async def preset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Recharge une configuration enregistrée dans le panneau."""
        gid = self.guild_id
        presets = get_queue_presets(gid)
        if not presets:
            await interaction.response.send_message(t(gid, "queue.preset_none"), ephemeral=True)
            return

        select = Select(
            placeholder=t(gid, "queue.preset_pick"),
            options=[
                discord.SelectOption(
                    label=str(p.get("name", "Preset"))[:100],
                    value=str(p.get("name", "Preset"))[:100],
                    description=preset_summary(gid, p)[:100],
                    emoji="📋",
                )
                for p in presets
            ],
        )

        async def select_callback(choice: discord.Interaction):
            # Relu à la sélection : le preset a pu être supprimé depuis /schedule
            # pendant que le menu était ouvert.
            preset = get_queue_preset(gid, select.values[0])
            if preset is None:
                await choice.response.edit_message(content=t(gid, "queue.preset_gone"), view=None)
                return
            # Mis à jour sur place : un modal déjà ouvert écrit dans ce même
            # dictionnaire, le remplacer ferait disparaître sa saisie.
            self.config.clear()
            self.config.update({k: v for k, v in preset.items() if k != "name"})
            await choice.response.edit_message(
                content=t(gid, "queue.preset_loaded", name=preset["name"]), view=None
            )

        select.callback = select_callback
        view = View()
        view.add_item(select)
        await interaction.response.send_message(view=view, ephemeral=True)

    @discord.ui.button(label="Save Preset", style=discord.ButtonStyle.success, row=2)
    async def save_preset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Enregistre la configuration actuelle sous un nom réutilisable."""
        gid = self.guild_id
        modal = discord.ui.Modal(title=t(gid, "queue.preset_save_modal"))
        field = discord.ui.TextInput(
            label=t(gid, "queue.preset_name_label"),
            default=str(self.config.get("queue_name", "Queue"))[:40],
            max_length=40,
        )
        modal.add_item(field)

        async def on_submit(modal_interaction: discord.Interaction):
            name = sanitize(field.value.strip(), 40)
            if not name:
                await modal_interaction.response.send_message(
                    t(gid, "queue.preset_name_required"), ephemeral=True
                )
                return
            try:
                save_queue_preset(gid, {**self.config, "name": name})
            except ValueError:
                await modal_interaction.response.send_message(
                    t(gid, "queue.preset_full", max=MAX_QUEUE_PRESETS), ephemeral=True
                )
                return
            await modal_interaction.response.send_message(
                t(gid, "queue.preset_saved", name=name), ephemeral=True
            )

        modal.on_submit = on_submit  # type: ignore[method-assign]
        await interaction.response.send_modal(modal)


    @discord.ui.button(label="Start", style=discord.ButtonStyle.green, row=2)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Montre l'aperçu AVANT de publier."""
        gid = self.guild_id
        existing = self.cog.active_sessions.get(gid)
        if existing and not existing.ended:
            await interaction.response.send_message(
                content=t(gid, "queue.already_active"),
                ephemeral=True,
            )
            return

        # Session jetable : sert uniquement à composer l'aperçu, elle n'est
        # enregistrée nulle part tant que la publication n'est pas confirmée.
        preview = QueueSession(interaction.user, None, self.config)
        preview.password = active_queue_password(gid)
        embed = preview.build_embed()
        embed.set_footer(text=t(gid, "queue.preview_footer"))

        await interaction.response.send_message(
            content=t(gid, "queue.preview_check"),
            embed=embed,
            view=ConfirmPublishView(self, interaction.user.id),
            ephemeral=True,
        )


class ConfirmPublishView(View):
    """Dernier filet avant le @everyone : publier, ou revenir corriger."""

    def __init__(self, config_view: "QueueConfigView", author_id: int):
        super().__init__(timeout=600)
        self.config_view = config_view
        self.author_id = author_id
        gid = config_view.guild_id
        self.publish.label = t(gid, "queue.btn_publish_now")
        self.modify.label = t(gid, "queue.btn_modify")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                t(self.config_view.guild_id, "queue.preview_not_yours"), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Publier", style=discord.ButtonStyle.success, emoji="📢")
    async def publish(self, interaction: discord.Interaction, _: discord.ui.Button):
        cog = self.config_view.cog
        gid = self.config_view.guild_id

        # Revérifié ici : une autre queue a pu démarrer pendant la relecture.
        existing = cog.active_sessions.get(gid)
        if existing and not existing.ended:
            await interaction.response.edit_message(
                content=t(gid, "queue.preview_already"), embed=None, view=None
            )
            return

        await interaction.response.defer()
        save_queue_config(gid, self.config_view.config)
        await cog.open_queue(
            interaction.guild, interaction.user, self.config_view.config,
            fallback_channel=interaction.channel,
        )
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(
            content=t(gid, "queue.preview_published"), embed=None, view=None
        )

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def modify(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(
            content=t(self.config_view.guild_id, "queue.preview_modify"),
            embed=None,
            view=None,
        )


class RematchView(View):
    """Confirmation d'un /rematch : republier tel quel, ou en prévenant les
    joueurs de la partie précédente."""

    def __init__(self, cog, guild_id: int, author_id: int, config: dict, players: list[int]):
        super().__init__(timeout=600)
        self.cog = cog
        self.author_id = author_id
        self.config = config
        self.players = players
        self.relaunch.label = t(guild_id, "queue.rematch_btn_go")
        self.recall.label = t(guild_id, "queue.rematch_btn_recall")
        self.cancel.label = t(guild_id, "queue.rematch_btn_cancel")
        self.relaunch.emoji = custom_emojis.get("replay")
        self.cancel.emoji = custom_emojis.get("cross")
        # Sans joueurs identifiables, « prévenir » n'aurait personne à citer.
        self.recall.disabled = not players

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                t(interaction.guild_id, "queue.preview_not_yours"), ephemeral=True
            )
            return False
        return True

    async def _publish(self, interaction: discord.Interaction, recall: bool) -> None:
        gid = interaction.guild_id
        # Revérifié ici : une queue a pu démarrer pendant la relecture.
        existing = self.cog.active_sessions.get(gid)
        if existing and not existing.ended:
            await interaction.response.edit_message(
                content=t(gid, "queue.rematch_active"), embed=None, view=None
            )
            return

        await interaction.response.defer()
        save_queue_config(gid, self.config)
        session = await self.cog.open_queue(
            interaction.guild, interaction.user, self.config, fallback_channel=interaction.channel
        )

        recalled = 0
        if recall and session is not None and session.announcement_channel is not None:
            # Les anciens joueurs sont mentionnés dans un message à part : le
            # coller à l'annonce noierait l'embed sous une liste de pseudos.
            mentions = [f"<@{uid}>" for uid in dict.fromkeys(self.players)
                        if interaction.guild.get_member(uid) is not None]
            recalled = len(mentions)
            for chunk in [mentions[i:i + 20] for i in range(0, len(mentions), 20)]:
                try:
                    await session.announcement_channel.send(
                        t(gid, "queue.rematch_recall_msg", players=" ".join(chunk)),
                        allowed_mentions=USERS_ONLY,
                    )
                except discord.HTTPException as e:
                    log.error(f"Rappel des joueurs impossible : {e}")
                    break

        await interaction.edit_original_response(
            content=t(gid, "queue.rematch_done", count=recalled) if recall
            else t(gid, "queue.preview_published"),
            embed=None, view=None,
        )

    @discord.ui.button(label="Relancer", style=discord.ButtonStyle.success, emoji="🔁")
    async def relaunch(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._publish(interaction, recall=False)

    @discord.ui.button(label="Relancer et prévenir", style=discord.ButtonStyle.primary, emoji="👥")
    async def recall(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._publish(interaction, recall=True)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(
            content=t(interaction.guild_id, "queue.rematch_cancelled"), embed=None, view=None
        )


class LaunchView(View):
    """Panel organisateur : répartit la file d'attente en équipes et démarre la partie."""

    def __init__(self, cog, session: QueueSession):
        super().__init__(timeout=None)
        self.cog = cog
        self.session = session
        self.launch_button.label = t(session.guild_id, "queue.btn_launch")
        self.cancel_button.label = t(session.guild_id, "queue.btn_cancel")

    @discord.ui.button(
        label="Lancer la partie", style=discord.ButtonStyle.success, emoji="🚀", custom_id="cyq:queue:launch"
    )
    async def launch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.session.guild_id

        if not self.cog._is_staff(interaction.user):
            await interaction.response.send_message(
                content=t(gid, "queue.organizers_only"),
                ephemeral=True,
            )
            return

        if self.session.started or self.session.ended:
            await interaction.response.send_message(
                content=t(gid, "queue.launch_already"),
                ephemeral=True,
            )
            return

        if not self.session.waiting_players:
            await interaction.response.send_message(
                content=t(gid, "queue.launch_empty"),
                ephemeral=True,
            )
            return

        # Crée des salons vocaux et déplace des membres : peut prendre plus de 3s,
        # donc on accuse réception tout de suite pour éviter "Unknown interaction".
        await interaction.response.defer()

        # Salon de match privé + capitaines : quand le mode est actif, les
        # équipes ne sont pas encore formées ici — c'est le draft qui les
        # composera, puis le cog Match rappellera la suite du lancement.
        match_cog = interaction.client.get_cog("Match")
        drafting = False
        if match_cog is not None and match_cog.enabled(gid):
            try:
                drafting = await match_cog.begin(interaction.guild, self.session, interaction.user)
            except Exception as e:
                log.error(f"Salon de match non ouvert : {e}")
                drafting = False
        if drafting and match_cog.captains_mode(gid):
            button.disabled = True
            self.cancel_button.disabled = True
            await interaction.edit_original_response(
                content=t(gid, "queue.launch_drafting"), view=self
            )
            self.cog.save_sessions()
            return

        self.session.launch()
        await self.cog.deploy_teams(interaction.guild, self.session)
        if drafting:
            await match_cog.go_live(interaction.guild, self.session)

        button.disabled = True
        self.cancel_button.disabled = True
        await interaction.edit_original_response(
            content=t(gid, "queue.launch_done"),
            view=self,
        )
        self.cog.save_sessions()

    @discord.ui.button(
        label="Annuler", style=discord.ButtonStyle.danger, emoji="🛑", custom_id="cyq:queue:cancel"
    )
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Annule la queue : supprime l'annonce, déverrouille le vocal, libère la session."""
        gid = self.session.guild_id

        if not self.cog._is_staff(interaction.user):
            await interaction.response.send_message(
                content=t(gid, "queue.organizers_only"),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        send_log(interaction.client, gid, "queue", t(gid, "logs.queue_cancelled"), user=interaction.user,
                 color=embeds.ERROR,
                 fields=[(t(gid, "logs.f_queue"), sanitize(str(self.session.queue_config.get("queue_name", "Queue")), 60)),
                         (t(gid, "logs.f_players"), len(self.session.waiting_players))])
        await self.cog.teardown_session(interaction.guild, self.session, cancelled=True)

        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(
            content=t(gid, "queue.cancel_done"),
            view=self,
        )


class PasswordJoinView(View):
    """Inscription à une queue sous mot de passe : Rejoindre / Quitter."""

    def __init__(self, cog, guild_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        if guild_id is not None:
            self.join_button.label = t(guild_id, "queue.pw_btn_join")
            self.leave_button.label = t(guild_id, "queue.pw_btn_leave")

    def _session(self, interaction: discord.Interaction):
        message = interaction.message
        session = self.cog.session_by_message.get(message.id) if message is not None else None
        if session is None or session.started or session.ended or not session.password:
            return None
        return session

    @discord.ui.button(label="Rejoindre", style=discord.ButtonStyle.success, emoji="🔒",
                       custom_id="cyq:queue:pw_join")
    async def join_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        gid = interaction.guild_id
        session = self._session(interaction)
        if session is None:
            await interaction.response.send_message(t(gid, "queue.pw_closed"), ephemeral=True)
            return
        if interaction.user.id in get_queue_blacklist(gid):
            await interaction.response.send_message(t(gid, "queue.blacklist_blocked_dm"), ephemeral=True)
            return
        if any(m.id == interaction.user.id for m in session.waiting_players):
            await interaction.response.send_message(t(gid, "queue.pw_already"), ephemeral=True)
            return
        await interaction.response.send_modal(QueuePasswordModal(self.cog, session))

    @discord.ui.button(label="Quitter", style=discord.ButtonStyle.secondary, emoji="🚪",
                       custom_id="cyq:queue:pw_leave")
    async def leave_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        gid = interaction.guild_id
        session = self._session(interaction)
        if session is None:
            await interaction.response.send_message(t(gid, "queue.pw_closed"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        left = await self.cog.remove_player(session, interaction.user)
        await interaction.followup.send(
            t(gid, "queue.pw_left" if left else "queue.pw_not_in"), ephemeral=True)


class QueuePasswordModal(discord.ui.Modal):
    """Le mot de passe, demandé avant l'inscription."""

    def __init__(self, cog, session: QueueSession):
        gid = session.guild_id
        super().__init__(title=t(gid, "queue.pw_modal_title")[:45])
        self.cog = cog
        self.session = session
        self.answer = discord.ui.TextInput(label=t(gid, "queue.pw_modal_label")[:45], max_length=100)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        session = self.session
        gid = session.guild_id
        # La queue a pu démarrer ou être annulée pendant la saisie.
        if session.started or session.ended or self.cog.active_sessions.get(gid) is not session:
            await interaction.response.send_message(t(gid, "queue.pw_closed"), ephemeral=True)
            return
        # Comparaison à temps constant : la durée de la réponse ne dit pas
        # combien de caractères étaient justes.
        if not hmac.compare_digest(self.answer.value.strip().encode(), (session.password or "").encode()):
            await interaction.response.send_message(t(gid, "queue.pw_wrong"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await self.cog.add_player(session, interaction.user)
        keys = {
            "joined": "queue.pw_joined",
            "already": "queue.pw_already",
            "full": "queue.pw_full",
            "blacklisted": "queue.blacklist_blocked_dm",
        }
        await interaction.followup.send(
            t(gid, keys[result], channel=resources.resource_name(gid, "voice_queue_waiting")),
            ephemeral=True,
        )


class QueueConfig(commands.Cog):
    """Cog pour le système de queue avec embed et boutons."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_sessions = {}
        self.result_messages = {}
        self.session_by_message = {}
        self._restored = False

    async def cog_load(self):
        # Boutons des queues sous mot de passe : un exemplaire pour toutes les
        # annonces, présentes et à venir (voir PasswordJoinView).
        self.bot.add_view(PasswordJoinView(self))

    def _is_staff(self, member):
        return resources.is_staff(member)

    def get_classement_cog(self):
        return self.bot.get_cog("Classement")

    async def open_queue(self, guild, author, config, *, fallback_channel=None):
        """Publie une queue et met en place tous ses panneaux."""
        # Toujours le salon d'annonces désigné à la configuration : le choisir
        # une deuxième fois à chaque queue était une occasion de se tromper,
        # et un ancien choix enregistré pouvait publier ailleurs sans prévenir.
        queue_channel = resources.get_text_channel(guild, "channel_queue_announcement")
        if not queue_channel:
            queue_channel = resources.get_text_channel(guild, "channel_queue_command") or fallback_channel
        if queue_channel is None:
            raise RuntimeError("aucun salon disponible pour publier l'annonce")

        session = QueueSession(author, queue_channel, config)
        session.password = active_queue_password(guild.id)

        extra = {"view": PasswordJoinView(self, guild.id)} if session.password else {}
        message = await queue_channel.send(
            content="@everyone",
            embed=session.build_embed(),
            allowed_mentions=discord.AllowedMentions(everyone=True),
            **extra,
        )
        session.message = message
        # Sous mot de passe, on s'inscrit par le bouton : une réaction ✅
        # laisserait croire qu'elle suffit.
        if not session.password:
            try:
                await message.add_reaction("✅")
            except discord.HTTPException:
                pass

        self.active_sessions[guild.id] = session
        self.session_by_message[message.id] = session

        waiting_channel = resources.get_voice_channel(guild, "voice_queue_waiting")
        session.waiting_channel = waiting_channel
        await self.clear_connexion_role(guild, reason="Nouvelle queue : reset des accès")
        await self.apply_waiting_lock(guild, waiting_channel, open_for_connexion=True)

        config_channel = resources.get_text_channel(guild, "channel_queue_command") or fallback_channel
        session.config_channel = config_channel
        if config_channel is not None:
            await self.lock_queue_channel_to_staff(guild, config_channel)
            panel_embed = embeds.base(
                guild.id,
                title=t(guild.id, "queue.panel_launch_title"),
                description=t(guild.id, "queue.panel_launch_desc"),
            )
            session.launch_message = await config_channel.send(
                embed=panel_embed, view=LaunchView(self, session)
            )
            await self.create_result_panel(guild, session, config_channel)

        self.save_sessions()
        mark_first_queue(guild.id)
        asyncio.create_task(self.notify_queue_role(guild, session))
        send_log(self.bot, guild.id, "queue", t(guild.id, "logs.queue_opened"), user=author,
                 color=embeds.SUCCESS,
                 fields=[(t(guild.id, "logs.f_queue"), sanitize(str(config.get("queue_name", "Queue")), 60)),
                         (t(guild.id, "logs.f_players"), session.get_capacity()),
                         (t(guild.id, "logs.f_link"), f"[{queue_channel.mention}]({message.jump_url})")])
        return session

    async def deploy_teams(self, guild: discord.Guild, session: "QueueSession") -> None:
        """Met la partie en place une fois les équipes formées."""
        # Annonce audio "la partie commence" dans le salon d'attente, avant de
        # séparer les joueurs en salons d'équipe.
        if session.waiting_channel:
            voice_client = None
            try:
                voice_client = await session.waiting_channel.connect()
                voice_client.play(discord.FFmpegPCMAudio(voice_announce_path(guild.id)))
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)
                await asyncio.sleep(3)
            except Exception as e:
                log.error(f"Erreur lors de l'annonce audio : {e}")
            finally:
                if voice_client and voice_client.is_connected():
                    await voice_client.disconnect()

        category = session.waiting_channel.category if session.waiting_channel else None
        max_players = session.queue_config.get("max_players_per_team", 4)
        for team_name, members in session.teams.items():
            try:
                team_channel = await guild.create_voice_channel(
                    name=team_name,
                    category=category,
                    user_limit=max_players,
                    reason="Queue lancée : salon d'équipe",
                )
            except discord.HTTPException as e:
                log.error(f"Erreur création du salon d'équipe '{team_name}' : {e}")
                continue
            session.team_channels[team_name] = team_channel
            await throttled_each(
                members,
                lambda m, c=team_channel: m.move_to(c, reason="Queue lancée : répartition en équipe"),
                label="répartition en équipes",
            )

        # Split terminé : le vocal d'attente se referme complètement.
        await self.clear_connexion_role(guild, reason="Queue lancée : accès révoqué")
        await self.apply_waiting_lock(guild, session.waiting_channel, open_for_connexion=False)

        # Reste-t-il quelqu'un dans le vocal d'attente après la répartition ?
        # C'est forcément un accès non prévu : on le sort.
        if session.waiting_channel:
            assigned = {m.id for members in session.teams.values() for m in members}
            leftover = [
                m for m in session.waiting_channel.members
                if not m.bot and m.id not in assigned and not self._is_staff(m)
            ]
            await throttled_each(
                leftover,
                lambda m: m.move_to(None, reason="Queue lancée : vocal d'attente fermé"),
                label="fermeture du vocal d'attente",
            )

        if session.message is not None:
            try:
                await session.message.edit(embed=session.build_embed())
            except discord.HTTPException:
                pass
        self.save_sessions()
        # Ici plutôt qu'au clic : le mode capitaines passe par le draft et
        # arrive aussi dans cette fonction, avec des équipes enfin formées.
        send_log(self.bot, guild.id, "queue", t(guild.id, "logs.queue_launched"), user=session.author,
                 color=embeds.SUCCESS,
                 fields=[(t(guild.id, "logs.f_queue"), sanitize(str(session.queue_config.get("queue_name", "Queue")), 60), False),
                         *[(sanitize(name, 60), "\n".join(m.mention for m in members) or "—")
                           for name, members in session.teams.items()]])

    # ------------------------------------------------------------------
    # Persistance des sessions
    # ------------------------------------------------------------------
    def save_sessions(self):
        """Écrit les sessions actives sur disque (appelé à chaque changement d'état)."""
        try:
            os.makedirs(os.path.dirname(SESSIONS_FILE), exist_ok=True)
            payload = {
                str(gid): session.to_dict()
                for gid, session in self.active_sessions.items()
                if not session.ended
            }
            write_json(SESSIONS_FILE, payload, indent=4, ensure_ascii=False)
        except Exception as e:
            log.error(f"Erreur sauvegarde des sessions de queue : {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        """Restaure les queues en cours après un redémarrage : sans ça, l'annonce
        reste affichée mais ses boutons et réactions ne répondent plus."""
        if self._restored:
            return
        self._restored = True

        data = {}
        if os.path.exists(SESSIONS_FILE):
            try:
                with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                log.error(f"Erreur lecture des sessions de queue : {e}")

        restored = 0
        for gid_str, sdata in data.items():
            guild = self.bot.get_guild(int(gid_str))
            if guild is None:
                continue
            session = QueueSession.from_dict(guild, sdata)
            if session is None:
                log.warning(f"Session de queue non restaurable pour le serveur {gid_str} (message/organisateur disparu)")
                continue

            self.active_sessions[guild.id] = session
            if session.message:
                self.session_by_message[session.message.id] = session

            # Réattacher les vues aux messages existants pour réactiver les
            # boutons.
            try:
                if session.launch_message:
                    view = LaunchView(self, session)
                    if session.started:
                        for item in view.children:
                            item.disabled = True
                    self.bot.add_view(view, message_id=session.launch_message.id)
                if session.result_message:
                    result_view = ResultView(self, session, guild.id)
                    result_view.message = session.result_message
                    self.bot.add_view(result_view, message_id=session.result_message.id)
            except Exception as e:
                log.error(f"Vues de queue non réattachées sur {guild.name} : {e}")
            restored += 1

        if restored:
            log.info(f"{restored} queue(s) restaurée(s) après redémarrage.")
        self.save_sessions()

        # Le vocal d'attente doit être verrouillé en permanence : on réapplique
        # l'état correct au démarrage, sinon un déverrouillage manuel ou un arrêt
        # du bot en pleine queue laisserait le salon ouvert à tout le monde.
        for guild in self.bot.guilds:
            waiting = resources.get_voice_channel(guild, "voice_queue_waiting")
            if waiting is None:
                continue
            session = self.active_sessions.get(guild.id)
            recruiting = session is not None and not session.started and not session.ended
            if not recruiting:
                await self.clear_connexion_role(guild, reason="Démarrage : aucune queue en inscription")
            await self.apply_waiting_lock(guild, waiting, open_for_connexion=recruiting)

    async def teardown_session(self, guild: discord.Guild, session: "QueueSession", *, cancelled: bool = False):
        """Nettoyage commun de fin de queue : supprime les salons d'équipe, purge et
        reverrouille le salon queue, et libère la session (mémoire + disque)."""
        session.ended = True

        if cancelled and session.message:
            try:
                await session.message.delete()
            except discord.HTTPException:
                pass

        for team_channel in session.team_channels.values():
            try:
                await team_channel.delete(reason="Queue terminée : nettoyage des salons d'équipe")
            except discord.HTTPException:
                pass
        session.team_channels.clear()

        # Le vocal d'attente reste verrouillé entre deux queues, et plus personne
        # ne garde le rôle Connexion : réagir sur une vieille annonce ne donne rien.
        await self.clear_connexion_role(guild, reason="Queue terminée : accès révoqué")
        waiting_channel = session.waiting_channel or resources.get_voice_channel(guild, "voice_queue_waiting")
        await self.apply_waiting_lock(guild, waiting_channel, open_for_connexion=False)

        if session.config_channel:
            try:
                await session.config_channel.purge(
                    limit=None, reason="Queue terminée : reset du salon",
                    # Le panneau /status a pu être posé ici : il reste.
                    check=lambda m: not is_status_panel_message(guild.id, m.id))
            except discord.HTTPException as e:
                log.error(f"Erreur lors du reset du salon queue : {e}")
            await self.lock_queue_channel_to_staff(guild, session.config_channel)

        self.active_sessions.pop(guild.id, None)
        if session.message:
            self.session_by_message.pop(session.message.id, None)
        self.save_sessions()

    async def lock_queue_channel_to_staff(self, guild: discord.Guild, channel: discord.TextChannel):
        """Restreint le salon 'queue' au rôle staff (organisateurs) + au bot.
        Les administrateurs du serveur outrepassent toujours les permissions de
        salon côté Discord, donc ils y ont accès sans overwrite dédié."""
        for target in list(channel.overwrites.keys()):
            if target != guild.default_role:
                try:
                    await channel.set_permissions(target, overwrite=None, reason="Salon queue : reset des accès")
                except discord.HTTPException:
                    pass
        try:
            await channel.set_permissions(
                guild.default_role, view_channel=False, reason="Salon queue : accès staff/admin uniquement"
            )
            staff_role = resources.get_role(guild, "role_staff")
            if staff_role:
                await channel.set_permissions(
                    staff_role, view_channel=True, send_messages=True, reason="Salon queue : accès staff"
                )
            await channel.set_permissions(
                guild.me, view_channel=True, send_messages=True, reason="Salon queue : accès du bot"
            )
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    # Rôle "Connexion" et verrouillage du vocal d'attente
    #
    # Le vocal d'attente est verrouillé en permanence pour @everyone. Le seul
    # moyen d'y entrer est le rôle Connexion, donné uniquement en réagissant ✅
    # sur l'annonce d'une queue encore en phase d'inscription. Le rôle est retiré
    # à tout le monde au lancement et à la fin : personne ne le conserve d'une
    # queue à l'autre.
    # ------------------------------------------------------------------
    def get_connexion_role(self, guild: discord.Guild) -> discord.Role | None:
        """Rôle d'accès au vocal d'attente, **désigné** par l'administrateur."""
        role = resources.get_role(guild, "role_connexion")
        if role is None:
            log.info(
                f"[{guild.name}] Aucun rôle Connexion désigné : le vocal d'attente "
                f"n'est pas verrouillé par le bot."
            )
        return role

    async def apply_waiting_lock(
        self, guild: discord.Guild, channel: discord.VoiceChannel | None, *, open_for_connexion: bool
    ):
        """État des permissions du vocal d'attente."""
        if channel is None:
            return
        role = self.get_connexion_role(guild)

        # Aucun rôle Connexion désigné = le vocal reste ouvert à tout le monde.
        if role is None:
            try:
                await channel.set_permissions(
                    guild.default_role, overwrite=None,
                    reason="Queue : aucun rôle Connexion, vocal d'attente ouvert",
                )
            except discord.HTTPException as e:
                log.error(f"Erreur lors de la réouverture du vocal d'attente : {e}")
            return

        for target in list(channel.overwrites.keys()):
            if isinstance(target, discord.Member):
                try:
                    await channel.set_permissions(target, overwrite=None, reason="Queue : purge des accès individuels")
                except discord.HTTPException:
                    pass
        try:
            await channel.set_permissions(
                guild.default_role, connect=False, reason="Queue : vocal d'attente verrouillé en permanence"
            )
            await channel.set_permissions(
                role,
                connect=open_for_connexion,
                view_channel=True,
                reason="Queue : accès du rôle Connexion",
            )
            await channel.set_permissions(
                guild.me, connect=True, view_channel=True, move_members=True, reason="Queue : accès du bot"
            )
        except discord.HTTPException as e:
            # Ignorer les erreurs temporaires de Discord (503, etc.)
            if e.status in (503, 502, 504):
                log.warning(f"Erreur temporaire Discord lors du verrouillage du vocal (ignorée) : {e}")
            else:
                log.error(f"Erreur lors du verrouillage du vocal d'attente : {e}")

    async def clear_connexion_role(self, guild: discord.Guild, *, reason: str):
        """Retire le rôle Connexion à tous ses porteurs (fin/lancement de queue)."""
        role = resources.get_role(guild, "role_connexion")
        if not role:
            return
        await throttled_each(
            list(role.members),
            lambda m: m.remove_roles(role, reason=reason),
            label="retrait du rôle Connexion",
        )

    async def grant_connexion(self, member: discord.Member) -> bool:
        role = self.get_connexion_role(member.guild)
        if not role:
            return False
        try:
            await member.add_roles(role, reason="Queue : accès accordé via réaction ✅")
            return True
        except discord.HTTPException as e:
            log.error(f"Impossible de donner le rôle Connexion à {member} : {e}")
            return False

    async def revoke_connexion(self, member: discord.Member):
        role = resources.get_role(member.guild, "role_connexion")
        if not role or role not in member.roles:
            return
        try:
            await member.remove_roles(role, reason="Queue : accès retiré (réaction enlevée)")
        except discord.HTTPException:
            pass

    def may_stay_in_waiting(self, member: discord.Member) -> bool:
        """Un membre a-t-il le droit d'être dans le vocal d'attente à cet instant ?"""
        if member.bot:
            return True
        # Sans rôle Connexion, le vocal d'attente est ouvert : éjecter les
        # arrivants contredirait ce que l'organisateur a choisi.
        if resources.get_role(member.guild, "role_connexion") is None:
            return True
        if member.guild_permissions.administrator or resources.is_staff(member):
            return True
        session = self.active_sessions.get(member.guild.id)
        if session is None or session.ended or session.started:
            return False
        return any(m.id == member.id for m in session.waiting_players)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        """Filtre l'entrée dans le vocal d'attente : droit d'accès, puis places."""
        if after.channel is None or after.channel == before.channel:
            return
        guild = member.guild
        waiting = resources.get_voice_channel(guild, "voice_queue_waiting")
        if waiting is None or after.channel.id != waiting.id:
            return

        if not self.may_stay_in_waiting(member):
            try:
                await member.move_to(None, reason="Queue : entrée non autorisée dans le vocal d'attente")
                log.info(f"Vocal d'attente : {member} éjecté (accès non autorisé) sur {guild.name}.")
                send_log(self.bot, guild.id, "queue", t(guild.id, "logs.queue_waiting_denied"),
                         user=member, color=embeds.WARNING,
                         fields=[(t(guild.id, "logs.f_channel"), waiting.mention)])
            except discord.HTTPException:
                pass
            return

        # Le staff peut toujours entrer : il doit pouvoir surveiller le vocal
        # même quand la queue affiche complet.
        if self._is_staff(member):
            return

        session = self.active_sessions.get(guild.id)
        if session is None or session.started or session.ended:
            return
        capacity = session.get_capacity()
        occupants = [m for m in waiting.members if not m.bot and m.id != member.id
                     and not self._is_staff(m)]
        if len(occupants) < capacity:
            return

        try:
            await member.move_to(None, reason="Queue : vocal d'attente complet")
            log.info(f"Vocal d'attente plein : {member} déconnecté sur {guild.name}.")
            send_log(self.bot, guild.id, "queue", t(guild.id, "logs.queue_waiting_full"),
                     user=member, color=embeds.WARNING,
                     fields=[(t(guild.id, "logs.f_channel"), waiting.mention),
                             (t(guild.id, "logs.f_players"), f"{len(occupants)}/{capacity}")])
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Déconnexion du vocal plein impossible : {e}")
            return

        try:
            await member.send(
                t(guild.id, "queue.waiting_full_dm", server=guild.name, capacity=capacity)
            )
        except discord.HTTPException:
            pass  # MP fermés : la déconnexion suffit à faire passer le message

    # ------------------------------------------------------------------
    # Notifications MP du rôle "Notif Queue"
    # ------------------------------------------------------------------
    async def notify_queue_role(self, guild: discord.Guild, session: "QueueSession"):
        """Envoie un MP à tous les porteurs du rôle Notif Queue, organisateur inclus."""
        gid = guild.id
        report_channel = session.config_channel

        async def report(key: str, **kwargs):
            if report_channel:
                try:
                    await report_channel.send(t(gid, key, **kwargs), allowed_mentions=NO_PINGS)
                except discord.HTTPException:
                    pass

        role = resources.get_role(guild, "role_queue_notif")
        if not role:
            log.warning(f"Notif Queue : rôle introuvable sur {guild.name}.")
            await report("queue.notif_no_role")
            return

        targets = [m for m in role.members if not m.bot]
        if not targets:
            log.info(f"Notif Queue : personne n'a le rôle sur {guild.name}.")
            await report("queue.notif_no_members", role=role.name)
            return

        description = t(
            gid,
            "queue.notif_dm_desc",
            author=session.author.display_name,
            queue=session.queue_config.get("queue_name", "Queue"),
            guild=guild.name,
            role=resources.resource_name(gid, "role_connexion"),
        )
        jump_url = getattr(session.message, "jump_url", None)
        if jump_url:
            description += "\n\n" + t(gid, "queue.notif_dm_link", url=jump_url)

        embed = embeds.base(
            gid,
            title=t(gid, "queue.notif_dm_title", notif=custom_emojis.get("discord_notification_settings_d")),
            description=description,
            kind="warning",
            footer=t(gid, "queue.notif_dm_footer", role=role.name),
        )
        embeds.brand(embed, guild)

        blocked = 0

        def _count_blocked(member, error):
            nonlocal blocked
            blocked += 1
            if not isinstance(error, discord.Forbidden):
                log.error(f"Notif Queue : erreur MP vers {member} : {error}")

        # Ouvrir un salon MP est fortement rate-limité : délai plus large que la
        # valeur par défaut entre chaque envoi.
        sent, _ = await throttled_each(
            targets,
            lambda m: m.send(embed=embed),
            delay=0.5,
            label="MP Notif Queue",
            on_error=_count_blocked,
        )

        log.info(f"Notif Queue : {sent}/{len(targets)} MP envoyé(s) sur {guild.name}.")
        await report("queue.notif_report", sent=sent, total=len(targets), blocked=blocked)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Ajoute un joueur à la file d'attente quand il réagit avec ✅ sur l'annonce."""
        if str(payload.emoji) != "✅" or payload.guild_id is None:
            return
        if payload.user_id == self.bot.user.id:
            return

        session = self.session_by_message.get(payload.message_id)
        if not session or session.started or session.ended:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return

        if session.password:
            # Queue sous mot de passe : la réaction ne compte pas, seul le
            # bouton Rejoindre inscrit.
            try:
                await session.message.remove_reaction("✅", member)
            except discord.HTTPException:
                pass
            return

        result = await self.add_player(session, member)
        if result in ("blacklisted", "full"):
            try:
                await session.message.remove_reaction("✅", member)
            except discord.HTTPException:
                pass
        if result == "blacklisted":
            try:
                await member.send(t(guild.id, "queue.blacklist_blocked_dm"))
            except discord.HTTPException:
                pass  # MP fermés : rien à faire, le retrait de la réaction suffit

    async def add_player(self, session: "QueueSession", member: discord.Member) -> str:
        """Inscrit un joueur — commun à la réaction ✅ et au bouton du mot de passe."""
        guild = member.guild
        if member.id in get_queue_blacklist(guild.id):
            send_log(self.bot, guild.id, "queue", t(guild.id, "logs.queue_blocked"),
                     user=member, color=embeds.WARNING)
            return "blacklisted"
        if any(m.id == member.id for m in session.waiting_players):
            return "already"
        if not session.add_waiting(member):
            return "full"

        send_log(self.bot, guild.id, "queue", t(guild.id, "logs.queue_joined"), user=member,
                 color=embeds.SUCCESS,
                 fields=[(t(guild.id, "logs.f_players"),
                          f"{len(session.waiting_players)}/{session.get_capacity()}")])
        await self.grant_connexion(member)
        try:
            await session.message.edit(embed=session.build_embed())
        except discord.HTTPException:
            pass
        self.save_sessions()

        if session.is_waiting_full() and not session.full_alert_sent:
            session.full_alert_sent = True
            target = session.config_channel or session.announcement_channel
            if target:
                try:
                    await target.send(
                        content=t(
                            guild.id, "queue.pool_full",
                            organizer=session.author.mention,
                            capacity=session.get_capacity(),
                        ),
                        allowed_mentions=USERS_ONLY,
                    )
                except discord.HTTPException:
                    pass
        return "joined"

    async def remove_player(self, session: "QueueSession", member: discord.Member) -> bool:
        """Désinscrit un joueur. False s'il n'était pas inscrit."""
        if not session.remove_waiting(member):
            return False
        guild = member.guild
        send_log(self.bot, guild.id, "queue", t(guild.id, "logs.queue_left"), user=member,
                 color=embeds.ERROR,
                 fields=[(t(guild.id, "logs.f_players"),
                          f"{len(session.waiting_players)}/{session.get_capacity()}")])
        # Le rôle est retiré, mais on ne déconnecte pas : un membre déjà dans le
        # vocal y reste (choix explicite de l'organisateur).
        await self.revoke_connexion(member)
        try:
            await session.message.edit(embed=session.build_embed())
        except discord.HTTPException:
            pass
        if not session.is_waiting_full():
            session.full_alert_sent = False
        self.save_sessions()
        return True

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Retire un joueur de la file d'attente quand il enlève sa réaction ✅."""
        if str(payload.emoji) != "✅" or payload.guild_id is None:
            return
        if payload.user_id == self.bot.user.id:
            return

        session = self.session_by_message.get(payload.message_id)
        # Sous mot de passe, c'est le bot qui retire les réactions égarées :
        # ce retrait ne doit pas désinscrire quelqu'un passé par le bouton.
        if not session or session.started or session.ended or session.password:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return

        await self.remove_player(session, member)

    async def create_result_panel(self, guild, session, channel):
        """Crée le panel de suivi des scores (une équipe par bouton + Finish) dans le salon donné."""
        view = ResultView(self, session, guild.id)
        message = await channel.send(embed=build_score_embed(session), view=view)
        view.message = message
        session.result_message = message
        self.result_messages[guild.id] = message
    
    @app_commands.command(name="queue", description="Create a new queue")
    async def queue(self, interaction: discord.Interaction):
        """Crée une nouvelle queue, ou ouvre l'assistant si rien n'est réglé."""
        gid = interaction.guild_id
        if not queue_ready(gid):
            # N'importe qui peut lancer la configuration maintenant
            from cogs.wizard import open_wizard
            await open_wizard(interaction)
            return

        if not self._is_staff(interaction.user):
            await interaction.response.send_message(
                embed=embeds.base(
                    interaction.guild_id,
                    description=t(interaction.guild_id, "queue.organizers_only"),
                    kind="error",
                ),
                ephemeral=True,
            )
            return
        
        embed = embeds.base(
            interaction.guild_id,
            title=t(interaction.guild_id, "queue.panel_config_title"),
            description=build_panel_description(interaction.guild_id),
        )
        embeds.brand(embed, interaction.guild)

        view = QueueConfigView(self, interaction.guild_id)

        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="history", description="Affiche l'historique des dernières parties de queue.")
    async def history(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        entries = get_queue_history(gid)[:10]
        if not entries:
            await interaction.response.send_message(t(gid, "queue.history_empty"), ephemeral=True)
            return

        embed = embeds.base(
            gid, title=t(gid, "queue.history_title"), kind="brand", timestamp=True,
            footer=t(gid, "queue.history_footer", count=len(get_queue_history(gid))),
        )
        embeds.brand(embed, interaction.guild)
        for entry in entries:
            ts = entry.get("ended_at")
            when = f"<t:{int(datetime.fromisoformat(ts).timestamp())}:R>" if ts else "—"
            winner = entry.get("winner")
            teams = entry.get("teams", {})
            lines = []
            for team_name, info in teams.items():
                won = team_name == winner
                lines.append(
                    f"{'🏆' if won else '▫️'} {'**' if won else ''}{sanitize(team_name, 40)}"
                    f"{'**' if won else ''}  ·  "
                    + t(gid, "queue.history_score",
                        points=info.get("points", 0), count=len(info.get("members", [])))
                )
            embeds.section(
                embed,
                f"🎮  {sanitize(entry.get('queue_name', 'Queue'), 60)}  ·  {when}",
                "\n".join(lines) or "—",
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rematch", description="Relance la dernière partie avec les mêmes réglages.")
    async def rematch(self, interaction: discord.Interaction):
        """Relance la dernière queue terminée sans rien reconfigurer."""
        gid = interaction.guild_id
        if not self._is_staff(interaction.user):
            await interaction.response.send_message(t(gid, "queue.rematch_staff_only"), ephemeral=True)
            return

        existing = self.active_sessions.get(gid)
        if existing and not existing.ended:
            await interaction.response.send_message(t(gid, "queue.rematch_active"), ephemeral=True)
            return

        history = get_queue_history(gid)
        last = history[0] if history else None
        if last is None:
            await interaction.response.send_message(t(gid, "queue.rematch_empty"), ephemeral=True)
            return

        # Les parties enregistrées avant /rematch n'ont pas de config : on
        # retombe sur la dernière configuration connue plutôt que d'abandonner.
        config = dict(last.get("config") or get_queue_config(gid) or {})
        if not config:
            await interaction.response.send_message(t(gid, "queue.rematch_no_config"), ephemeral=True)
            return
        config.pop("name", None)

        players = [uid for info in last.get("teams", {}).values() for uid in info.get("members", [])]
        preview = QueueSession(interaction.user, None, config)
        embed = preview.build_embed()
        embed.set_footer(text=t(gid, "queue.preview_footer"))

        await interaction.response.send_message(
            content=t(gid, "queue.rematch_check",
                      name=sanitize(last.get("queue_name", "Queue"), 60), count=len(players)),
            embed=embed,
            view=RematchView(self, gid, interaction.user.id, config, players),
            ephemeral=True,
        )

    @app_commands.command(name="bl", description="Bloque un membre de la queue (laisse vide pour voir la liste).")
    @app_commands.describe(
        membre="Le membre à bloquer (laisse vide pour afficher la liste noire)",
        raison="Pourquoi ce membre est bloqué",
    )
    async def bl(
        self,
        interaction: discord.Interaction,
        membre: discord.Member | None = None,
        raison: str | None = None,
    ):
        """Bloquer et débloquer sont deux commandes distinctes : une seule
        commande à bascule rendait l'effet imprévisible (on ne sait pas si le
        membre est déjà dans la liste avant de valider)."""
        gid = interaction.guild_id
        if not self._is_staff(interaction.user):
            await interaction.response.send_message(t(gid, "queue.blacklist_staff_only"), ephemeral=True)
            return

        if membre is None:
            await self._send_blacklist(interaction)
            return

        if membre.id == interaction.user.id:
            await interaction.response.send_message(t(gid, "queue.blacklist_cant_self"), ephemeral=True)
            return

        clean_reason = sanitize(raison, 200) if raison else None
        if add_to_queue_blacklist(gid, membre.id, clean_reason, interaction.user.id):
            send_log(self.bot, gid, "queue", t(gid, "logs.queue_bl"), user=membre, color=embeds.WARNING,
                     fields=[(t(gid, "logs.f_by"), interaction.user.mention),
                             (t(gid, "logs.f_reason"), clean_reason or t(gid, "logs.no_reason"), False)])
            content = t(
                gid, "queue.blacklist_added",
                member=membre.mention,
                reason=clean_reason or t(gid, "queue.blacklist_no_reason"),
            )
        else:
            content = t(gid, "queue.blacklist_already", member=membre.mention)

        await interaction.response.send_message(content, ephemeral=True, allowed_mentions=NO_PINGS)

    @app_commands.command(name="unbl", description="Débloque un membre de la queue.")
    @app_commands.describe(membre="Le membre à débloquer")
    async def unbl(self, interaction: discord.Interaction, membre: discord.Member):
        gid = interaction.guild_id
        if not self._is_staff(interaction.user):
            await interaction.response.send_message(t(gid, "queue.blacklist_staff_only"), ephemeral=True)
            return

        removed = remove_from_queue_blacklist(gid, membre.id)
        key = "queue.blacklist_removed" if removed else "queue.blacklist_not_found"
        if removed:
            send_log(self.bot, gid, "queue", t(gid, "logs.queue_unbl"), user=membre, color=embeds.SUCCESS,
                     fields=[(t(gid, "logs.f_by"), interaction.user.mention)])
        await interaction.response.send_message(
            t(gid, key, member=membre.mention), ephemeral=True, allowed_mentions=NO_PINGS
        )

    async def _send_blacklist(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        entries = get_queue_blacklist_entries(gid)
        if not entries:
            await interaction.response.send_message(t(gid, "queue.blacklist_list_empty"), ephemeral=True)
            return
        lines = []
        for entry in entries:
            reason = sanitize(entry.get("reason") or t(gid, "queue.blacklist_no_reason"), 150)
            lines.append(f"• <@{entry['user_id']}> — *{reason}*")
        embed = embeds.base(
            gid,
            title=t(gid, "queue.blacklist_list_title"),
            description="\n".join(lines),
            footer=t(gid, "queue.blacklist_footer"),
        )
        embeds.brand(embed, interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)


    def record_queue_history(self, guild: discord.Guild, session: "QueueSession") -> None:
        """Enregistre une queue terminée dans l'historique persistant du serveur."""
        points: dict[str, int] = {}
        for team, _ in session.win_log:
            points[team] = points.get(team, 0) + 1
        entry = {
            "queue_name": session.queue_config.get("queue_name", "Queue"),
            "ended_at": discord.utils.utcnow().isoformat(),
            "winner": session.winner,
            # Configuration complète : sans elle, /rematch ne pourrait pas
            # reproduire la partie (taille des équipes, couleurs, salon).
            "config": dict(session.queue_config),
            "teams": {
                team_name: {"members": [m.id for m in members], "points": points.get(team_name, 0)}
                for team_name, members in session.teams.items()
            },
        }
        add_queue_history_entry(guild.id, entry)

    async def update_classement(self, guild: discord.Guild, session: QueueSession):
        """Met à jour le classement après une queue terminée."""
        classement_cog = self.get_classement_cog()
        if not classement_cog:
            return

        if session.winner:
            for team_name, members in session.teams.items():
                for member in members:
                    if team_name == session.winner:
                        classement_cog.add_win(guild.id, member.id)
                    else:
                        classement_cog.add_loss(guild.id, member.id)

            await classement_cog.save_classement_config()

        classement_cog.record_queue(guild.id)
        await classement_cog.save_server_stats()
        await classement_cog.update_classement_channel(guild)


def build_score_embed(session: QueueSession, *, final: bool = False) -> discord.Embed:
    """Le tableau des points, en direct puis publié."""
    gid = session.guild_id
    queue_name = sanitize(str(session.queue_config.get("queue_name", "Queue")), 60)
    embed = discord.Embed(
        title=(t(gid, "queue.result_title", name=queue_name) if final
               else f"📊  {t(gid, 'queue.score_title')}"),
        color=0xFFFFFF,
    )

    team_colors = session.queue_config.get("team_colors", {})
    scores = {
        name: sum(1 for team, _ in session.win_log if team == name)
        for name in session.teams
    }
    for i, (team_name, members) in enumerate(session.teams.items()):
        circle = team_colors.get(team_name, DEFAULT_TEAM_CIRCLES[i % len(DEFAULT_TEAM_CIRCLES)])
        points = scores[team_name]
        roster = "\n".join(m.mention for m in members) or "—"
        trophy = "🏆 " if session.winner == team_name else ""
        score_line = (
            t(gid, "queue.result_point" if points <= 1 else "queue.result_points", n=points)
            if final else f"**{points}**"
        )
        embed.add_field(
            name=f"{trophy}{sanitize(team_name, 60)} {circle}",
            value=f"{score_line}\n{roster}",
            inline=True,
        )
    embeds.align(embed)

    history = (
        "\n".join(f"{ts.strftime('%H:%M')}  →  {team}" for team, ts in session.win_log)
        if session.win_log else t(gid, "queue.score_no_points")
    )
    embeds.section(embed, t(gid, "queue.score_history"), f"```\n{history}\n```")
    embed.set_footer(
        text=t(gid, "queue.result_footer", rounds=len(session.win_log)) if final
        else t(gid, "queue.score_footer")
    )
    return embed


class ResultView(View):
    """Panel de suivi des scores : un bouton par équipe + Finish pour clore et publier le résultat."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Les points et la clôture écrivent le classement.
        if self.cog._is_staff(interaction.user):
            return True
        await interaction.response.send_message(t(self.guild_id, "queue.organizers_only"), ephemeral=True)
        return False

    TEAM_STYLES = [
        discord.ButtonStyle.primary,
        discord.ButtonStyle.success,
        discord.ButtonStyle.danger,
        discord.ButtonStyle.secondary,
    ]

    def __init__(self, cog, session: QueueSession, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.session = session
        self.guild_id = guild_id
        self.message = None
        self.finished = False

        # Les custom_id doivent être STABLES : sans eux, discord.py en génère
        # un aléatoire à chaque démarrage, la vue n'est plus « persistante » et
        # bot.add_view() la refuse au redémarrage (ValueError), ce qui rendait
        # les boutons de score morts après un simple restart.
        team_colors = session.queue_config.get("team_colors", {})
        for i, team_name in enumerate(session.teams.keys()):
            button = discord.ui.Button(
                label=team_name,
                emoji=team_colors.get(team_name, DEFAULT_TEAM_CIRCLES[i % len(DEFAULT_TEAM_CIRCLES)]),
                style=self.TEAM_STYLES[i % len(self.TEAM_STYLES)],
                row=i // 5,
                custom_id=f"cyq:score:team:{i}",
            )
            button.callback = lambda interaction, team=team_name: self.team_point_callback(interaction, team)
            self.add_item(button)

        finish_row = (len(session.teams) - 1) // 5 + 1
        finish_button = discord.ui.Button(
            label=t(guild_id, "queue.btn_finish"),
            style=discord.ButtonStyle.gray,
            emoji="🏁",
            row=min(finish_row, 4),
            custom_id="cyq:score:finish",
        )
        finish_button.callback = self.finish_callback
        self.add_item(finish_button)

    async def team_point_callback(self, interaction: discord.Interaction, team_name: str):
        """Ajoute un point horodaté à l'équipe cliquée."""
        gid = self.guild_id
        if self.finished:
            await interaction.response.send_message(t(gid, "queue.result_already"), ephemeral=True)
            return
        if not self.session.started:
            await interaction.response.send_message(t(gid, "queue.result_not_started"), ephemeral=True)
            return

        self.session.win_log.append((team_name, discord.utils.utcnow()))
        await interaction.response.edit_message(embed=build_score_embed(self.session), view=self)
        send_log(interaction.client, gid, "queue", t(gid, "logs.queue_point"), user=interaction.user,
                 fields=[(t(gid, "logs.f_team"), sanitize(team_name, 60)),
                         (t(gid, "logs.f_score"), sum(1 for team, _ in self.session.win_log if team == team_name))])
        self.cog.save_sessions()

    async def finish_callback(self, interaction: discord.Interaction):
        """Clôture le suivi et envoie le résultat final dans #queue-resultat."""
        gid = self.guild_id
        if self.finished:
            await interaction.response.send_message(t(gid, "queue.result_already"), ephemeral=True)
            return
        if not self.session.win_log:
            await interaction.response.send_message(t(gid, "queue.result_no_points"), ephemeral=True)
            return
        if not self.session.started:
            await interaction.response.send_message(t(gid, "queue.result_not_launched"), ephemeral=True)
            return

        counts = {}
        for team, _ in self.session.win_log:
            counts[team] = counts.get(team, 0) + 1
        self.session.winner = max(counts, key=counts.get)
        self.session.ended = True
        self.finished = True

        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        send_log(interaction.client, gid, "queue", t(gid, "logs.queue_finished"), user=interaction.user,
                 color=embeds.GOLD,
                 fields=[(t(gid, "logs.f_queue"), sanitize(str(self.session.queue_config.get("queue_name", "Queue")), 60)),
                         (t(gid, "logs.f_winner"), sanitize(self.session.winner, 60)),
                         (t(gid, "logs.f_rounds"), len(self.session.win_log)),
                         (t(gid, "logs.f_score"), "\n".join(f"{sanitize(team, 60)} : **{points}**"
                                                            for team, points in counts.items()), False)])

        guild = interaction.guild

        # Salon de match ouvert : le vote du MVP y démarre, et c'est lui qui
        # appliquera le MMR puis fermera tout.
        match_cog = interaction.client.get_cog("Match")
        if match_cog is not None and match_cog.enabled(gid):
            try:
                await match_cog.begin_mvp_vote(guild, self.session)
            except Exception as e:
                log.error(f"Vote MVP non lancé : {e}")

        result_embed = build_score_embed(self.session, final=True)

        webhook_url = get_webhook_url(guild.id)
        sent = False
        if webhook_url:
            try:
                # Webhook asynchrone : SyncWebhook bloquait la boucle, donc les trois bots.
                webhook = discord.Webhook.from_url(webhook_url, client=interaction.client)
                await webhook.send(embed=result_embed, allowed_mentions=NO_PINGS)
                sent = True
            except Exception as e:
                log.error(f"Erreur lors de l'envoi du résultat via webhook : {e}")

        if not sent:
            resultats_channel = resources.get_text_channel(guild, "channel_queue_resultat")
            if resultats_channel:
                try:
                    await resultats_channel.send(embed=result_embed)
                    sent = True
                except discord.HTTPException as e:
                    log.error(f"Erreur lors de l'envoi du résultat : {e}")

        if not sent:
            await interaction.followup.send(
                t(gid, "queue.result_no_channel",
                  channel=resources.resource_name(gid, "channel_queue_resultat")),
                ephemeral=True,
            )

        await self.cog.update_classement(guild, self.session)
        self.cog.record_queue_history(guild, self.session)

        # L'annonce d'origine passe en « match terminé », raccourcis compris.
        try:
            await self.session.message.edit(embed=self.session.build_embed())
        except (discord.HTTPException, AttributeError) as e:
            log.error(f"Annonce non mise à jour en fin de match : {e}")

        # Nettoyage commun (salons d'équipe, reset du salon queue, libération de la session)
        await self.cog.teardown_session(guild, self.session)


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueConfig(bot))
    log.info("Cog QueueConfig chargé")
