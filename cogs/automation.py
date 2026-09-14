"""
Cog : Automation
================
Commandes : /schedule (queue programmée), /season (saisons du classement)

Deux panneaux, zéro commande annexe : tout se règle avec des boutons à
bascule sur l'embed lui-même, qui se réaffiche à jour après chaque clic.

Queue programmée
----------------
Le champ « Heure » du panneau /queue était purement décoratif : on écrivait
21H00 et rien ne se passait. Ici, le bot publie l'annonce tout seul à l'heure
et aux jours choisis, avec un rappel optionnel avant.

Ce qui est publié se choisit dans le panneau : soit un **preset** (une
configuration de queue nommée et enregistrée, créable directement ici), soit
la dernière queue configurée avec /queue. Sans preset, un serveur qui lance
un 2v2 improvisé un soir voyait sa queue automatique du lendemain repartir
sur ce 2v2 : le preset fige la configuration voulue.

Saisons
-------
Le classement s'accumulait indéfiniment : un joueur arrivé en janvier restait
devant tout le monde pour toujours. La remise à zéro mensuelle archive le
podium puis repart de zéro, ce qui laisse une chance aux nouveaux.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

import embeds
import resources
from guild_settings import (
    MAX_QUEUE_PRESETS,
    get_schedule, set_schedule,
    get_season, set_season, add_season_archive,
    get_queue_config, get_queue_presets, get_queue_preset,
    save_queue_preset, delete_queue_preset,
)
from i18n import t
# Un preset est une configuration de queue : c'est le panneau /queue qui sait
# la décrire et qui fixe les bornes, les deux endroits doivent s'accorder.
from cogs.queue_config import preset_summary, TEAMS_MIN, TEAMS_MAX, PLAYERS_MIN, PLAYERS_MAX
from text_safety import NO_PINGS, sanitize

log = logging.getLogger("bot.automation")

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

LAST_CONFIG = "__last__"  # valeur du menu « dernière configuration utilisée »


def _parse_time(value: str) -> tuple[int, int] | None:
    """Accepte 21:00, 21h00, 21H00, 9:5… Retourne None si illisible."""
    cleaned = value.strip().lower().replace("h", ":").replace(" ", "")
    if cleaned.endswith(":"):
        cleaned += "00"
    parts = cleaned.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def next_occurrence(cfg: dict, now: datetime | None = None) -> datetime | None:
    """Prochaine date de publication, ou None si aucun jour n'est coché."""
    days = cfg.get("days") or []
    if not days:
        return None
    parsed = _parse_time(cfg.get("time", "21:00"))
    if parsed is None:
        return None
    hour, minute = parsed
    now = now or datetime.now()
    for offset in range(8):
        candidate = (now + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate.weekday() in days and candidate > now:
            return candidate
    return None


def _bounded_int(value: str, low: int, high: int) -> int | None:
    """Entier saisi dans un modal, ou None s'il est illisible ou hors bornes."""
    cleaned = value.strip()
    if not cleaned.isdigit():
        return None
    number = int(cleaned)
    return number if low <= number <= high else None


def resolve_scheduled_config(guild_id: int) -> tuple[dict | None, str | None, bool]:
    """Ce que le planificateur publiera : (configuration, nom du preset, perdu ?).

    `perdu` signale un preset choisi puis supprimé à la main dans le fichier de
    réglages : on retombe alors sur la dernière configuration, mais le panneau
    doit le dire plutôt que de publier autre chose en silence."""
    name = get_schedule(guild_id).get("preset")
    if name:
        preset = get_queue_preset(guild_id, name)
        if preset is not None:
            return preset, preset.get("name", name), False
        return get_queue_config(guild_id), name, True
    return get_queue_config(guild_id), None, False


# ----------------------------------------------------------------------
# Panneau : queue programmée
# ----------------------------------------------------------------------
def build_schedule_embed(guild: discord.Guild) -> discord.Embed:
    gid = guild.id
    cfg = get_schedule(gid)
    on = cfg["enabled"]

    embed = embeds.base(
        gid,
        title=t(gid, "auto.sched_title"),
        description=t(gid, "auto.sched_desc"),
        kind="success" if on else "neutral",
        footer=t(gid, "auto.sched_footer"),
    )
    embeds.brand(embed, guild)

    nxt = next_occurrence(cfg) if on else None
    embed.add_field(
        name=t(gid, "auto.field_state"),
        value=t(gid, "auto.on" if on else "auto.off"),
        inline=True,
    )
    embeds.stat(embed, t(gid, "auto.field_time"), cfg["time"])
    embed.add_field(
        name=t(gid, "auto.field_reminder"),
        value=(
            t(gid, "auto.reminder_on", minutes=cfg["reminder_minutes"])
            if cfg["reminder"] else t(gid, "auto.reminder_off")
        ),
        inline=True,
    )

    days = cfg.get("days") or []
    if len(days) == 7:
        days_text = t(gid, "auto.days_all")
    elif not days:
        days_text = t(gid, "auto.days_none")
    else:
        # Les sept jours en pastilles : on voit la semaine d'un coup d'œil au
        # lieu de lire une énumération.
        days_text = "  ".join(
            (f"**{t(gid, f'auto.day_{key}')[:3]}**" if i in days else f"~~{t(gid, f'auto.day_{key}')[:3]}~~")
            for i, key in enumerate(DAY_KEYS)
        )
    embeds.section(embed, t(gid, "auto.field_days"), days_text)

    config, preset_name, lost = resolve_scheduled_config(gid)
    if lost:
        published = t(gid, "auto.preset_missing", name=sanitize(preset_name, 60))
        if config is None:
            published += "\n" + t(gid, "auto.preset_no_config")
    elif preset_name:
        published = f"📋 **{sanitize(preset_name, 60)}**\n{preset_summary(gid, config)}"
    elif config:
        published = f"{t(gid, 'auto.preset_none_selected')}\n{preset_summary(gid, config)}"
    else:
        published = t(gid, "auto.preset_no_config")
    embeds.section(embed, t(gid, "auto.field_preset"), published)

    embeds.section(
        embed, t(gid, "auto.field_next"),
        f"<t:{int(nxt.timestamp())}:F>  ·  <t:{int(nxt.timestamp())}:R>" if nxt else t(gid, "auto.next_none"),
    )
    return embed


class ChooserView(discord.ui.View):
    """Menu affiché *à la place* du panneau, qui redevient ensuite le panneau.

    Un second message éphémère obligeait à rouvrir /schedule pour voir le
    résultat de son choix (« Rouvre le panneau pour voir le résumé »). Ici, le
    même message porte le menu puis le panneau à jour."""

    def __init__(self, panel, select: discord.ui.Select, embed_builder):
        super().__init__(timeout=300)
        self.panel = panel
        self.embed_builder = embed_builder
        self.back.label = t(panel.guild.id, "auto.btn_back")
        self.add_item(select)

    async def restore(self, interaction: discord.Interaction, content: str | None = None) -> None:
        self.panel._sync()
        await interaction.response.edit_message(
            content=content, embed=self.embed_builder(self.panel.guild), view=self.panel
        )

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.restore(interaction)


class PresetModal(discord.ui.Modal):
    """Création d'un preset depuis le panneau /schedule.

    Volontairement limité aux cinq champs qu'un modal autorise : le reste
    (couleurs, salon de publication, noms d'équipe) se règle dans /queue puis
    s'enregistre avec le bouton « Enregistrer » du panneau de queue."""

    def __init__(self, panel: "ScheduleView"):
        gid = panel.guild.id
        super().__init__(title=t(gid, "auto.preset_modal"))
        self.panel = panel
        self.f_name = discord.ui.TextInput(
            label=t(gid, "auto.preset_f_name"), placeholder=t(gid, "auto.preset_f_name_ph"), max_length=40
        )
        self.f_queue = discord.ui.TextInput(
            label=t(gid, "auto.preset_f_queue"), placeholder=t(gid, "auto.preset_f_queue_ph"), max_length=40
        )
        self.f_teams = discord.ui.TextInput(label=t(gid, "auto.preset_f_teams"), default="2", max_length=1)
        self.f_players = discord.ui.TextInput(label=t(gid, "auto.preset_f_players"), default="5", max_length=1)
        self.f_type = discord.ui.TextInput(
            label=t(gid, "auto.preset_f_type"), required=False, max_length=30
        )
        for field in (self.f_name, self.f_queue, self.f_teams, self.f_players, self.f_type):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = self.panel.guild.id
        name = sanitize(self.f_name.value.strip(), 40)
        queue_name = sanitize(self.f_queue.value.strip(), 40)
        if not name or not queue_name:
            await interaction.response.send_message(t(gid, "auto.preset_invalid"), ephemeral=True)
            return
        teams = _bounded_int(self.f_teams.value, TEAMS_MIN, TEAMS_MAX)
        players = _bounded_int(self.f_players.value, PLAYERS_MIN, PLAYERS_MAX)
        if teams is None or players is None:
            await interaction.response.send_message(
                t(gid, "auto.preset_range",
                  tmin=TEAMS_MIN, tmax=TEAMS_MAX, pmin=PLAYERS_MIN, pmax=PLAYERS_MAX),
                ephemeral=True,
            )
            return

        preset = {
            "name": name,
            "queue_name": queue_name,
            "num_teams": teams,
            "team_names": [t(gid, "auto.preset_team", n=i + 1) for i in range(teams)],
            "max_players_per_team": players,
            "session": t(gid, "auto.preset_session_default"),
            "heure": get_schedule(gid)["time"],
            "type": sanitize(self.f_type.value.strip(), 30) or t(gid, "auto.preset_type_default"),
        }
        try:
            save_queue_preset(gid, preset)
        except ValueError:
            await interaction.response.send_message(
                t(gid, "auto.preset_full", max=MAX_QUEUE_PRESETS), ephemeral=True
            )
            return

        # Créé depuis ce panneau : il est aussitôt celui qui sera publié, sinon
        # on créerait un preset sans effet visible.
        set_schedule(gid, preset=name)
        self.panel._sync()
        await interaction.response.edit_message(
            content=t(gid, "auto.preset_created", name=name),
            embed=build_schedule_embed(self.panel.guild),
            view=self.panel,
        )


class ScheduleView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild = guild
        self._sync()

    def _sync(self) -> None:
        gid = self.guild.id
        cfg = get_schedule(gid)
        self.toggle.label = t(gid, "auto.btn_off" if cfg["enabled"] else "auto.btn_on")
        self.toggle.style = discord.ButtonStyle.danger if cfg["enabled"] else discord.ButtonStyle.success
        self.toggle.emoji = "⏸️" if cfg["enabled"] else "▶️"
        self.set_time.label = t(gid, "auto.btn_time")
        self.set_days.label = t(gid, "auto.btn_days")
        self.reminder.label = t(gid, "auto.btn_reminder")
        self.pick_preset.label = t(gid, "auto.btn_preset")
        self.new_preset.label = t(gid, "auto.btn_new_preset")
        self.del_preset.label = t(gid, "auto.btn_del_preset")
        self.del_preset.disabled = not get_queue_presets(gid)

    async def _guard(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        allowed = isinstance(user, discord.Member) and (
            user.guild_permissions.manage_guild or resources.is_staff(user)
        )
        if not allowed:
            await interaction.response.send_message(t(self.guild.id, "auto.staff_only"), ephemeral=True)
        return allowed

    async def _refresh(self, interaction: discord.Interaction) -> None:
        self._sync()
        await interaction.response.edit_message(embed=build_schedule_embed(self.guild), view=self)

    @discord.ui.button(label="Activer", style=discord.ButtonStyle.success, emoji="▶️",
                       row=0, custom_id="cyq:sched:toggle")
    async def toggle(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        set_schedule(self.guild.id, enabled=not get_schedule(self.guild.id)["enabled"])
        await self._refresh(interaction)

    @discord.ui.button(label="Heure", style=discord.ButtonStyle.secondary, emoji="🕒",
                       row=0, custom_id="cyq:sched:time")
    async def set_time(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        gid = self.guild.id
        modal = discord.ui.Modal(title=t(gid, "auto.time_modal"))
        field = discord.ui.TextInput(
            label=t(gid, "auto.time_label"),
            default=get_schedule(gid)["time"],
            placeholder="21:00",
            max_length=5,
        )
        modal.add_item(field)

        async def on_submit(modal_interaction: discord.Interaction) -> None:
            parsed = _parse_time(field.value)
            if parsed is None:
                await modal_interaction.response.send_message(t(gid, "auto.time_invalid"), ephemeral=True)
                return
            set_schedule(gid, time=f"{parsed[0]:02d}:{parsed[1]:02d}")
            await self._refresh(modal_interaction)

        modal.on_submit = on_submit  # type: ignore[method-assign]
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Jours", style=discord.ButtonStyle.secondary, emoji="📅",
                       row=0, custom_id="cyq:sched:days")
    async def set_days(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        gid = self.guild.id
        current = set(get_schedule(gid).get("days") or [])
        select = discord.ui.Select(
            placeholder=t(gid, "auto.days_placeholder"),
            min_values=0,
            max_values=7,
            options=[
                discord.SelectOption(label=t(gid, f"auto.day_{key}"), value=str(i), default=i in current)
                for i, key in enumerate(DAY_KEYS)
            ],
        )

        view = ChooserView(self, select, build_schedule_embed)

        async def callback(choice: discord.Interaction) -> None:
            set_schedule(gid, days=sorted(int(v) for v in select.values))
            await view.restore(choice, t(gid, "auto.days_saved"))

        select.callback = callback  # type: ignore[method-assign]
        await interaction.response.edit_message(
            content=t(gid, "auto.days_placeholder"), embed=build_schedule_embed(self.guild), view=view
        )

    @discord.ui.button(label="Rappel", style=discord.ButtonStyle.secondary, emoji="🔔",
                       row=1, custom_id="cyq:sched:reminder")
    async def reminder(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        set_schedule(self.guild.id, reminder=not get_schedule(self.guild.id)["reminder"])
        await self._refresh(interaction)

    @discord.ui.button(label="Queue à publier", style=discord.ButtonStyle.primary, emoji="📋",
                       row=1, custom_id="cyq:sched:preset")
    async def pick_preset(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Choisit CE QUI est publié à l'heure programmée."""
        if not await self._guard(interaction):
            return
        gid = self.guild.id
        current = get_schedule(gid).get("preset")
        presets = get_queue_presets(gid)

        options = [
            discord.SelectOption(
                label=t(gid, "auto.preset_opt_last"),
                description=t(gid, "auto.preset_opt_last_desc")[:100],
                value=LAST_CONFIG,
                emoji="🕘",
                default=not current,
            )
        ]
        for preset in presets:
            name = str(preset.get("name", ""))[:100]
            options.append(
                discord.SelectOption(
                    label=name,
                    description=preset_summary(gid, preset)[:100],
                    value=name,
                    emoji="📋",
                    default=current is not None and name.lower() == str(current).lower(),
                )
            )

        select = discord.ui.Select(placeholder=t(gid, "auto.preset_pick"), options=options)
        view = ChooserView(self, select, build_schedule_embed)

        async def callback(choice: discord.Interaction) -> None:
            value = select.values[0]
            if value == LAST_CONFIG:
                set_schedule(gid, preset=None)
                await view.restore(choice, t(gid, "auto.preset_chosen_last"))
                return
            # Revérifié : le preset a pu être supprimé pendant que le menu était ouvert.
            preset = get_queue_preset(gid, value)
            if preset is None:
                await view.restore(choice, t(gid, "auto.preset_gone"))
                return
            set_schedule(gid, preset=preset["name"])
            await view.restore(choice, t(gid, "auto.preset_chosen", name=preset["name"]))

        select.callback = callback  # type: ignore[method-assign]
        await interaction.response.edit_message(
            content=t(gid, "auto.preset_pick_help"), embed=build_schedule_embed(self.guild), view=view
        )

    @discord.ui.button(label="Créer un preset", style=discord.ButtonStyle.success, emoji="➕",
                       row=2, custom_id="cyq:sched:newpreset")
    async def new_preset(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.send_modal(PresetModal(self))

    @discord.ui.button(label="Supprimer un preset", style=discord.ButtonStyle.danger, emoji="🗑️",
                       row=2, custom_id="cyq:sched:delpreset")
    async def del_preset(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        gid = self.guild.id
        presets = get_queue_presets(gid)
        if not presets:
            await interaction.response.send_message(t(gid, "auto.preset_empty"), ephemeral=True)
            return

        select = discord.ui.Select(
            placeholder=t(gid, "auto.del_pick"),
            options=[
                discord.SelectOption(
                    label=str(p.get("name", ""))[:100],
                    description=preset_summary(gid, p)[:100],
                    value=str(p.get("name", ""))[:100],
                    emoji="📋",
                )
                for p in presets
            ],
        )
        view = ChooserView(self, select, build_schedule_embed)

        async def callback(choice: discord.Interaction) -> None:
            name = select.values[0]
            removed = delete_queue_preset(gid, name)
            # Le preset supprimé ne doit pas rester « choisi » : sinon le
            # planificateur publierait la dernière config sans prévenir.
            if str(get_schedule(gid).get("preset") or "").lower() == name.lower():
                set_schedule(gid, preset=None)
            await view.restore(
                choice,
                t(gid, "auto.preset_deleted", name=name) if removed else t(gid, "auto.preset_gone"),
            )

        select.callback = callback  # type: ignore[method-assign]
        await interaction.response.edit_message(
            content=t(gid, "auto.del_pick_help"), embed=build_schedule_embed(self.guild), view=view
        )


# ----------------------------------------------------------------------
# Panneau : saisons
# ----------------------------------------------------------------------
def build_season_embed(guild: discord.Guild) -> discord.Embed:
    gid = guild.id
    cfg = get_season(gid)
    on = cfg["enabled"]

    embed = embeds.base(
        gid,
        title=t(gid, "auto.season_title"),
        description=t(gid, "auto.season_desc"),
        kind="success" if on else "neutral",
        footer=t(gid, "auto.season_footer"),
    )
    embeds.brand(embed, guild)
    embed.add_field(
        name=t(gid, "auto.field_state"),
        value=t(gid, "auto.on" if on else "auto.off"),
        inline=True,
    )
    embed.add_field(
        name=t(gid, "auto.field_reset_day"),
        value=f"**{t(gid, 'auto.reset_day_value', day=cfg['reset_day'])}**",
        inline=True,
    )
    embed.add_field(
        name=t(gid, "auto.field_announce"),
        value=t(gid, "auto.on" if cfg["announce"] else "auto.off"),
        inline=True,
    )
    archive = cfg.get("archive") or []
    embeds.section(
        embed, t(gid, "auto.field_archive"),
        (t(gid, "auto.archive_count", count=len(archive)) + "\n" + t(gid, "auto.archive_see"))
        if archive else t(gid, "auto.archive_empty"),
    )
    return embed


class SeasonView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild = guild
        self._sync()

    def _sync(self) -> None:
        gid = self.guild.id
        cfg = get_season(gid)
        self.toggle.label = t(gid, "auto.btn_off" if cfg["enabled"] else "auto.btn_on")
        self.toggle.style = discord.ButtonStyle.danger if cfg["enabled"] else discord.ButtonStyle.success
        self.toggle.emoji = "⏸️" if cfg["enabled"] else "▶️"
        self.set_day.label = t(gid, "auto.btn_reset_day")
        self.announce.label = t(gid, "auto.btn_announce")

    async def _guard(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        allowed = isinstance(user, discord.Member) and (
            user.guild_permissions.manage_guild or resources.is_staff(user)
        )
        if not allowed:
            await interaction.response.send_message(t(self.guild.id, "auto.staff_only"), ephemeral=True)
        return allowed

    async def _refresh(self, interaction: discord.Interaction) -> None:
        self._sync()
        await interaction.response.edit_message(embed=build_season_embed(self.guild), view=self)

    @discord.ui.button(label="Activer", style=discord.ButtonStyle.success, emoji="▶️",
                       row=0, custom_id="cyq:season:toggle")
    async def toggle(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        set_season(self.guild.id, enabled=not get_season(self.guild.id)["enabled"])
        await self._refresh(interaction)

    @discord.ui.button(label="Jour du mois", style=discord.ButtonStyle.secondary, emoji="📅",
                       row=0, custom_id="cyq:season:day")
    async def set_day(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        gid = self.guild.id
        current = get_season(gid)["reset_day"]
        # 28 maximum : les mois courts n'ont pas de 29, 30 ni 31, la remise à
        # zéro ne se déclencherait jamais en février.
        select = discord.ui.Select(
            placeholder=t(gid, "auto.reset_day_placeholder"),
            options=[
                discord.SelectOption(label=t(gid, "auto.reset_day_value", day=d), value=str(d), default=d == current)
                for d in (1, 5, 10, 15, 20, 25, 28)
            ],
        )

        view = ChooserView(self, select, build_season_embed)

        async def callback(choice: discord.Interaction) -> None:
            set_season(gid, reset_day=int(select.values[0]))
            await view.restore(choice, t(gid, "auto.days_saved"))

        select.callback = callback  # type: ignore[method-assign]
        await interaction.response.edit_message(
            content=t(gid, "auto.reset_day_placeholder"), embed=build_season_embed(self.guild), view=view
        )

    @discord.ui.button(label="Annonce", style=discord.ButtonStyle.secondary, emoji="📢",
                       row=0, custom_id="cyq:season:announce")
    async def announce(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        set_season(self.guild.id, announce=not get_season(self.guild.id)["announce"])
        await self._refresh(interaction)


# ----------------------------------------------------------------------
# Podium : palmarès des saisons
# ----------------------------------------------------------------------
def period_label(guild_id: int, period: str) -> str:
    """« 2026-07 » → « Juillet 2026 » dans la langue du serveur.

    Les douze mois tiennent dans une seule clé séparée par des barres : douze
    clés par langue pour une info aussi mécanique alourdiraient les fichiers
    de traduction sans rien apporter."""
    try:
        year, month = period.split("-")
        names = t(guild_id, "auto.months").split("|")
        return f"{names[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return period


def build_podium_embed(guild: discord.Guild, classement=None) -> discord.Embed:
    """Saison en cours + podiums archivés, du plus récent au plus ancien."""
    gid = guild.id
    cfg = get_season(gid)
    archive = list(reversed(cfg.get("archive") or []))

    embed = embeds.base(
        gid, title=t(gid, "auto.podium_title"), kind="gold", timestamp=True,
        footer=t(gid, "auto.podium_footer", count=len(archive)),
    )
    embeds.brand(embed, guild)

    # Saison en cours : lue en direct dans le classement, elle n'est archivée
    # qu'à la remise à zéro.
    live = []
    if classement is not None:
        top = sorted(
            classement.player_stats.items(),
            key=lambda x: (x[1].get("wins", 0), x[1].get("max_streak", 0)),
            reverse=True,
        )[:3]
        live = [(uid, s.get("wins", 0)) for uid, s in top if s.get("wins", 0)]

    wins_word = t(gid, "classement.wins_word")
    if live:
        current = "\n".join(
            f"{embeds.medal(i)}  <@{uid}>  ·  **{wins}** {wins_word}"
            for i, (uid, wins) in enumerate(live, start=1)
        )
    else:
        current = t(gid, "auto.podium_current_empty")
    embeds.section(embed, t(gid, "auto.podium_current"), current)

    if not archive:
        embeds.section(embed, embeds.BLANK, t(gid, "auto.podium_none"))
        return embed

    embed.add_field(name=embeds.BLANK, value=embeds.RULE, inline=False)
    for entry in archive[:10]:
        podium = entry.get("podium") or []
        value = "\n".join(
            f"{embeds.medal(i)}  <@{p['user_id']}>  —  **{p.get('wins', 0)}** {wins_word}"
            for i, p in enumerate(podium, start=1)
        ) or t(gid, "auto.podium_current_empty")
        embeds.section(embed, f"📅  {period_label(gid, entry.get('period', '?'))}", value)
    return embed


# ----------------------------------------------------------------------
# Cog
# ----------------------------------------------------------------------
class Automation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._started = False

    def cog_unload(self) -> None:
        self.ticker.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._started:
            self._started = True
            self.ticker.start()

    @tasks.loop(minutes=1)
    async def ticker(self) -> None:
        for guild in list(self.bot.guilds):
            try:
                await self._tick_schedule(guild)
                await self._tick_season(guild)
            except Exception as e:
                log.error(f"Automatisation sur {guild.name} : {e}")

    @ticker.before_loop
    async def before_ticker(self) -> None:
        await self.bot.wait_until_ready()

    # -- Queue programmée ------------------------------------------------
    async def _tick_schedule(self, guild: discord.Guild) -> None:
        cfg = get_schedule(guild.id)
        if not cfg["enabled"]:
            return
        parsed = _parse_time(cfg["time"])
        if parsed is None or not cfg.get("days"):
            return
        hour, minute = parsed
        now = datetime.now()
        if now.weekday() not in cfg["days"]:
            return
        today = now.strftime("%Y-%m-%d")

        # Rappel
        if cfg["reminder"] and cfg.get("last_reminder") != today:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            delta = (target - now).total_seconds() / 60
            if 0 < delta <= cfg["reminder_minutes"]:
                set_schedule(guild.id, last_reminder=today)
                await self._announce_reminder(guild, int(delta) or 1)

        # Publication
        if cfg.get("last_run") == today:
            return
        if now.hour != hour or now.minute < minute:
            return

        queue_cog = self.bot.get_cog("QueueConfig")
        if queue_cog is None:
            return
        existing = queue_cog.active_sessions.get(guild.id)
        if existing and not existing.ended:
            log.info(f"[{guild.name}] Queue programmée ignorée : une queue est déjà en cours.")
            set_schedule(guild.id, last_run=today)
            return

        config, preset_name, lost = resolve_scheduled_config(guild.id)
        if lost:
            log.warning(
                f"[{guild.name}] Preset « {preset_name} » introuvable : publication "
                f"de la dernière configuration à la place."
            )
        if not config:
            log.info(f"[{guild.name}] Queue programmée ignorée : aucune configuration enregistrée.")
            return

        config = dict(config)
        config.pop("name", None)  # étiquette du preset, pas une donnée de queue
        # L'heure affichée dans l'annonce est celle de la publication réelle :
        # un preset créé à 21:00 puis reprogrammé à 22:00 annoncerait sinon
        # une heure fausse.
        config["heure"] = cfg["time"]

        set_schedule(guild.id, last_run=today)
        try:
            await queue_cog.open_queue(guild, guild.me, config)
            log.info(
                f"[{guild.name}] Queue programmée publiée"
                + (f" (preset « {preset_name} »)." if preset_name and not lost else ".")
            )
        except Exception as e:
            log.error(f"[{guild.name}] Queue programmée non publiée : {e}")

    async def _announce_reminder(self, guild: discord.Guild, minutes: int) -> None:
        channel = resources.get_text_channel(guild, "channel_queue_announcement")
        if channel is None:
            return
        try:
            await channel.send(
                t(guild.id, "auto.reminder_message", minutes=minutes),
                allowed_mentions=NO_PINGS,
            )
        except discord.HTTPException:
            pass

    # -- Saisons ---------------------------------------------------------
    async def _tick_season(self, guild: discord.Guild) -> None:
        cfg = get_season(guild.id)
        if not cfg["enabled"]:
            return
        now = datetime.now()
        period = now.strftime("%Y-%m")
        if now.day != cfg["reset_day"] or cfg.get("last_reset") == period:
            return

        classement = self.bot.get_cog("Classement")
        if classement is None:
            return

        # Podium archivé AVANT la remise à zéro, sinon il est perdu.
        top = sorted(
            classement.player_stats.items(),
            key=lambda x: (x[1].get("wins", 0), x[1].get("max_streak", 0)),
            reverse=True,
        )[:3]
        podium = [{"user_id": uid, "wins": s.get("wins", 0)} for uid, s in top if s.get("wins", 0)]

        set_season(guild.id, last_reset=period)
        if cfg["keep_history"] and podium:
            add_season_archive(guild.id, {"period": period, "podium": podium})

        for stats in classement.player_stats.values():
            stats["wins"] = 0
            stats["losses"] = 0
            stats["streak"] = 0
            stats["max_streak"] = 0
            stats["weekly_wins"] = 0
        await classement.save_classement_config()
        await classement.update_classement_channel(guild)
        log.info(f"[{guild.name}] Saison {period} clôturée, classement remis à zéro.")

        if cfg["announce"]:
            await self._announce_season(guild, period, podium)

    async def _announce_season(self, guild: discord.Guild, period: str, podium: list) -> None:
        # Podium de fin de saison : contenu de classement, donc salon classement.
        channel = resources.get_text_channel(guild, "channel_queue_classement")
        if channel is None:
            return
        gid = guild.id
        embed = embeds.base(
            gid,
            title=t(gid, "auto.season_end_title"),
            description=t(gid, "auto.season_end_desc", period=period_label(gid, period)),
            kind="gold",
            footer=t(gid, "auto.season_end_footer"),
            timestamp=True,
        )
        embeds.brand(embed, guild)
        if podium:
            wins_word = t(gid, "classement.wins_word")
            embeds.section(
                embed, t(gid, "auto.season_podium"),
                "\n".join(
                    f"{embeds.medal(i)}  <@{p['user_id']}>  ·"
                    f"  **{p.get('wins', 0)}** {wins_word}"
                    for i, p in enumerate(podium, start=1)
                ),
            )
        try:
            await channel.send(embed=embed, allowed_mentions=NO_PINGS)
        except discord.HTTPException:
            pass

    # -- Commandes -------------------------------------------------------
    @app_commands.command(name="schedule", description="Programme la publication automatique des queues.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def schedule(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        await interaction.response.send_message(
            embed=build_schedule_embed(guild), view=ScheduleView(guild), ephemeral=True
        )

    @app_commands.command(name="season", description="Remise à zéro mensuelle du classement (saisons).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def season(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        await interaction.response.send_message(
            embed=build_season_embed(guild), view=SeasonView(guild), ephemeral=True
        )

    @app_commands.command(name="podium", description="Podiums des saisons passées et saison en cours.")
    async def podium(self, interaction: discord.Interaction) -> None:
        """Le bot archivait les podiums de saison sans jamais les montrer.

        Visible de tout le monde : un palmarès qu'on est seul à voir n'a pas
        d'intérêt."""
        guild = interaction.guild
        if guild is None:
            return
        await interaction.response.send_message(
            embed=build_podium_embed(guild, self.bot.get_cog("Classement"))
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Automation(bot))
    log.info("Cog Automation chargé")
