"""
Routes — Configuration de queue.
==================================
La page reprend exactement le modèle de données du panneau Discord
(cogs/queue_config.py) et appelle les mêmes fonctions de `guild_settings` :
aucune logique n'est réécrite, les deux interfaces restent d'accord.

Une différence volontaire avec Discord : sur le panneau, enregistrer la
configuration **lance** la queue (`save_queue_config` puis `open_queue`). Ici,
enregistrer n'enregistre que la configuration. Ouvrir une queue reste `/queue`
sur Discord, là où sont les joueurs — personne ne surveille un site web en
attendant une partie.
"""

from __future__ import annotations

import logging

from aiohttp import web

from guild_settings import (
    MAX_QUEUE_PRESETS,
    delete_queue_preset,
    get_mmr_config,
    get_queue_config,
    get_queue_preset,
    get_queue_presets,
    save_queue_config,
    save_queue_preset,
)
from i18n import get_lang, t
from text_safety import sanitize

from web.keys import GUILD_ID, MEMBER, SESSION
from web.render import (
    card,
    esc,
    flash,
    layout,
    row,
    save_button,
    select,
    switch,
    text_input,
)

log = logging.getLogger("bot.web.queue")

NAME_LIMIT = 32
TEAM_NAME_LIMIT = 60
FREE_TEXT_LIMIT = 80
PRESET_NAME_LIMIT = 40


def _bounds():
    """Bornes et palette lues dans le cog : une seule source de vérité. Import
    différé — le cog tire discord.py et tout le système de queue avec lui."""
    from cogs.queue_config import (
        COLOR_PALETTE,
        DEFAULT_TEAM_CIRCLES,
        PLAYERS_MAX,
        PLAYERS_MIN,
        TEAMS_MAX,
        TEAMS_MIN,
        color_name,
    )
    return {
        "palette": COLOR_PALETTE,
        "circles": DEFAULT_TEAM_CIRCLES,
        "teams": (TEAMS_MIN, TEAMS_MAX),
        "players": (PLAYERS_MIN, PLAYERS_MAX),
        "color_name": color_name,
    }


def default_config(guild_id: int) -> dict:
    """La configuration de départ, identique à celle du panneau Discord."""
    return {
        "queue_name": "Queue",
        "num_teams": 2,
        "team_names": [t(guild_id, "queue.team_default", n=1), t(guild_id, "queue.team_default", n=2)],
        "team_colors": {},
        "max_players_per_team": 4,
        "session": "",
        "heure": None,
        "type": "",
        "captains": bool(get_mmr_config(guild_id).get("captains")),
    }


def current_config(guild_id: int) -> dict:
    cfg = get_queue_config(guild_id)
    return dict(cfg) if isinstance(cfg, dict) else default_config(guild_id)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class Invalid(Exception):
    """Saisie refusée. Le message est une clé de traduction."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def _int_in(raw, low: int, high: int, fallback: int) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return fallback
    return value if low <= value <= high else fallback


def read_form(guild_id: int, form, base: dict) -> dict:
    """Construit la configuration à partir du formulaire.

    On repart de `base` plutôt que d'un dictionnaire vide : une configuration
    peut porter des clés que cette page n'affiche pas (venues d'un preset ou
    d'une version plus récente du panneau), et les effacer en silence serait
    une régression invisible."""
    b = _bounds()
    config = dict(base)

    name = sanitize(str(form.get("queue_name", "")).strip(), NAME_LIMIT)
    if not name:
        raise Invalid("dashboard.flash_err_name")
    config["queue_name"] = name

    num_teams = _int_in(form.get("num_teams"), *b["teams"], fallback=int(base.get("num_teams", 2)))
    config["num_teams"] = num_teams

    names: list[str] = []
    for i in range(num_teams):
        raw = str(form.get(f"team_name_{i}", "")).strip()
        cleaned = sanitize(raw, TEAM_NAME_LIMIT) or t(guild_id, "queue.team_default", n=i + 1)
        names.append(cleaned)
    # `team_colors` est indexé par NOM d'équipe : deux équipes homonymes
    # partageraient leur couleur et l'une écraserait l'autre.
    if len({n.lower() for n in names}) != len(names):
        raise Invalid("dashboard.flash_err_dup")
    config["team_names"] = names

    allowed = {emoji for emoji, _, _ in b["palette"]}
    colors: dict[str, str] = {}
    for i, team in enumerate(names):
        chosen = str(form.get(f"team_color_{i}", "")).strip()
        colors[team] = chosen if chosen in allowed else b["circles"][i % len(b["circles"])]
    # Même nettoyage que le panneau Discord : aucune couleur orpheline ne
    # survit à un changement de nom ou de nombre d'équipes.
    config["team_colors"] = colors

    config["max_players_per_team"] = _int_in(
        form.get("max_players_per_team"), *b["players"],
        fallback=int(base.get("max_players_per_team", 4)),
    )

    config["session"] = sanitize(str(form.get("session", "")).strip(), FREE_TEXT_LIMIT)
    config["type"] = sanitize(str(form.get("type", "")).strip(), FREE_TEXT_LIMIT)
    heure = sanitize(str(form.get("heure", "")).strip(), 40)
    config["heure"] = heure or None
    config["captains"] = str(form.get("captains", "")).strip() in {"1", "on", "true", "yes"}
    return config


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def _identity_card(guild_id: int, config: dict, csrf: str) -> str:
    return card(
        glyph="queue",
        title=t(guild_id, "dashboard.queue_title"),
        subtitle=t(guild_id, "dashboard.queue_desc"),
        form_action=f"/g/{guild_id}/queue",
        csrf=csrf,
        body=(
            row(
                t(guild_id, "dashboard.f_name"),
                text_input("queue_name", config.get("queue_name", ""),
                           limit=NAME_LIMIT, required=True,
                           label=t(guild_id, "dashboard.f_name")),
                hint=t(guild_id, "dashboard.f_name_hint"),
            )
            + row(
                t(guild_id, "dashboard.f_session"),
                text_input("session", config.get("session", ""), limit=FREE_TEXT_LIMIT,
                           placeholder=t(guild_id, "dashboard.f_session_ph"),
                           label=t(guild_id, "dashboard.f_session")),
            )
            + row(
                t(guild_id, "dashboard.f_heure"),
                text_input("heure", config.get("heure") or "", limit=40, placeholder="21:00",
                           label=t(guild_id, "dashboard.f_heure")),
            )
            + row(
                t(guild_id, "dashboard.f_type"),
                text_input("type", config.get("type", ""), limit=FREE_TEXT_LIMIT,
                           placeholder=t(guild_id, "dashboard.f_type_ph"),
                           label=t(guild_id, "dashboard.f_type")),
            )
            + row(
                t(guild_id, "dashboard.f_captains"),
                switch("captains", bool(config.get("captains")),
                       label=t(guild_id, "dashboard.f_captains")),
                hint=t(guild_id, "dashboard.f_captains_hint"),
            )
            + _teams_block(guild_id, config)
        ),
        footer=(
            f'<span class="hint">{esc(t(guild_id, "dashboard.launch_hint"))}</span>'
            + save_button(guild_id)
        ),
    )


def _teams_block(guild_id: int, config: dict) -> str:
    """Nombre d'équipes, joueurs par équipe, puis une ligne par équipe.

    Les six lignes sont toujours écrites ; le script n'affiche que les
    premières. Réduire puis ré-augmenter le nombre d'équipes ne perd donc
    aucun nom déjà saisi."""
    b = _bounds()
    lang = get_lang(guild_id)
    teams_min, teams_max = b["teams"]
    players_min, players_max = b["players"]
    num_teams = int(config.get("num_teams", 2))
    names = list(config.get("team_names", []))
    colors = dict(config.get("team_colors", {}))

    palette = [(emoji, f'{emoji}  {b["color_name"](lang, emoji)}') for emoji, _, _ in b["palette"]]

    rows = []
    for i in range(teams_max):
        label = t(guild_id, "queue.team_default", n=i + 1)
        team_name = names[i] if i < len(names) else label
        chosen = colors.get(team_name, b["circles"][i % len(b["circles"])])
        options = "".join(
            f'<option value="{esc(value)}"{" selected" if value == chosen else ""}>{esc(text)}</option>'
            for value, text in palette
        )
        rows.append(
            f'<div class="team-row" data-index="{i}"{"" if i < num_teams else " hidden"}>'
            f'<input type="text" name="team_name_{i}" value="{esc(team_name)}"'
            f' maxlength="{TEAM_NAME_LIMIT}" aria-label="{esc(label)}">'
            f'<select name="team_color_{i}" aria-label="{esc(label)}">{options}</select>'
            "</div>"
        )

    return (
        row(
            t(guild_id, "dashboard.f_teams"),
            select("num_teams", [(n, str(n)) for n in range(teams_min, teams_max + 1)], num_teams,
                   label=t(guild_id, "dashboard.f_teams")),
        )
        + row(
            t(guild_id, "dashboard.f_players"),
            select("max_players_per_team",
                   [(n, str(n)) for n in range(players_min, players_max + 1)],
                   config.get("max_players_per_team", 4),
                   label=t(guild_id, "dashboard.f_players")),
        )
        + row(
            t(guild_id, "dashboard.f_team_list"),
            "".join(rows),
            hint=t(guild_id, "dashboard.f_team_list_hint"),
            stacked=True,
        )
    )


def _presets_card(guild_id: int, csrf: str) -> str:
    presets = get_queue_presets(guild_id)
    if presets:
        items = "".join(
            f'<li><span class="pname">{esc(preset.get("name", ""))}</span>'
            f'<form method="post" action="/g/{guild_id}/presets/load">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
            f'<input type="hidden" name="name" value="{esc(preset.get("name", ""))}">'
            f'<button type="submit" class="ghost">{esc(t(guild_id, "dashboard.preset_load"))}</button></form>'
            f'<form method="post" action="/g/{guild_id}/presets/delete" class="confirm">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
            f'<input type="hidden" name="name" value="{esc(preset.get("name", ""))}">'
            f'<button type="submit" class="ghost danger">'
            f'{esc(t(guild_id, "dashboard.preset_delete"))}</button></form>'
            "</li>"
            for preset in presets
        )
        listing = f'<ul class="presets">{items}</ul>'
    else:
        listing = f'<p class="empty">{esc(t(guild_id, "dashboard.preset_none"))}</p>'

    return card(
        glyph="bookmark",
        title=t(guild_id, "dashboard.presets_title"),
        subtitle=t(guild_id, "dashboard.presets_desc", max=MAX_QUEUE_PRESETS),
        body=listing,
        footer=(
            f'<form method="post" action="/g/{guild_id}/presets" class="inline">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
            + text_input("name", "", limit=PRESET_NAME_LIMIT, required=True,
                         placeholder=t(guild_id, "dashboard.preset_name_ph"),
                         label=t(guild_id, "dashboard.preset_name_ph"))
            + f'<button type="submit">{esc(t(guild_id, "dashboard.preset_save"))}</button></form>'
        ),
    )


def render_page(guild, guild_id: int, config: dict, csrf: str, notice: str = "") -> str:
    # Le texte de confirmation passe par un élément du document, pas par le
    # script : il est ainsi échappé comme le reste de la page, et le JavaScript
    # reste un fichier statique — la CSP peut donc refuser tout script en ligne.
    hidden_text = f'<p id="confirm-text" hidden>{esc(t(guild_id, "dashboard.preset_confirm"))}</p>'

    return layout(
        guild_id,
        title=t(guild_id, "dashboard.queue_title"),
        body=notice + _identity_card(guild_id, config, csrf)
        + _presets_card(guild_id, csrf) + hidden_text,
        guild_name=guild.name if guild is not None else "",
        active="queue",
        nav_guild_id=guild_id,
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _redirect(guild_id: int, key: str) -> web.HTTPFound:
    return web.HTTPFound(f"/g/{guild_id}/queue?m={key}")


async def get_queue(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    guild = request[MEMBER].guild
    notice = flash(guild_id, request.query.get("m"))
    html = render_page(guild, guild_id, current_config(guild_id), request[SESSION]["csrf"], notice)
    return web.Response(text=html, content_type="text/html")


async def post_queue(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    form = await request.post()
    try:
        config = read_form(guild_id, form, current_config(guild_id))
    except Invalid as bad:
        return _redirect(guild_id, bad.key.split("flash_")[-1])
    save_queue_config(guild_id, config)
    log.info(f"[DASHBOARD] Config de queue enregistrée — guild {guild_id} par {request[MEMBER].id}")
    return _redirect(guild_id, "saved")


async def post_preset_save(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    form = await request.post()
    name = sanitize(str(form.get("name", "")).strip(), PRESET_NAME_LIMIT)
    if not name:
        return _redirect(guild_id, "err_preset_name")
    preset = {k: v for k, v in current_config(guild_id).items() if k != "name"}
    preset["name"] = name
    try:
        save_queue_preset(guild_id, preset)
    except ValueError:
        # guild_settings lève « preset_limit_reached » au-delà de MAX_QUEUE_PRESETS.
        return _redirect(guild_id, "err_preset_limit")
    return _redirect(guild_id, "saved_preset")


async def post_preset_load(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    form = await request.post()
    preset = get_queue_preset(guild_id, str(form.get("name", "")))
    if preset is None:
        return _redirect(guild_id, "err_preset_gone")
    save_queue_config(guild_id, {k: v for k, v in preset.items() if k != "name"})
    return _redirect(guild_id, "loaded_preset")


async def post_preset_delete(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    form = await request.post()
    if not delete_queue_preset(guild_id, str(form.get("name", ""))):
        return _redirect(guild_id, "err_preset_gone")
    return _redirect(guild_id, "deleted_preset")


def add_routes(app: web.Application) -> None:
    app.router.add_get("/g/{gid}/queue", get_queue)
    app.router.add_post("/g/{gid}/queue", post_queue)
    app.router.add_post("/g/{gid}/presets", post_preset_save)
    app.router.add_post("/g/{gid}/presets/load", post_preset_load)
    app.router.add_post("/g/{gid}/presets/delete", post_preset_delete)
