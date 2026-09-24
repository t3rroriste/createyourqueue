"""
Routes — Réglages du serveur (l'équivalent de `/option`).
===========================================================
Mêmes réglages, mêmes fonctions de `guild_settings`, mêmes règles : le rôle
organisateur ne peut pas être @everyone, et les clans ne s'allument pas sans
catégorie. Ce qui change, c'est le confort — un menu Discord plafonne à 25
entrées, une liste déroulante web montre les 300 salons d'un gros serveur.

Le dashboard **désigne** des salons et des rôles existants ; il n'en crée
aucun, exactement comme les sélecteurs de `/option`.

Une carte = un formulaire = une route. Enregistrer les rôles ne réécrit pas
les fonctions : deux administrateurs sur deux onglets ne s'effacent pas l'un
l'autre.
"""

from __future__ import annotations

import logging

from aiohttp import web

from guild_settings import (
    MMR_DEFAULTS,
    clear_resource_id,
    get_features,
    get_mmr_config,
    get_queue_password,
    get_resource_id,
    queue_ready,
    set_features,
    set_mmr_config,
    set_queue_password,
    set_resource_id,
)
from i18n import t

from web.keys import GUILD_ID, MEMBER, SESSION
from web.render import (
    card,
    esc,
    flash,
    icon,
    layout,
    number_input,
    row,
    save_button,
    select,
    switch,
    text_input,
)

log = logging.getLogger("bot.web.server")

# Même limite que le modal de /option (cogs/wizard.py).
PASSWORD_LIMIT = 50

# Les fonctions à la carte, dans l'ordre où /option les présente.
FEATURES = [
    ("leaderboard", "dashboard.feat_leaderboard"),
    ("mvp", "dashboard.feat_mvp"),
    ("clans", "dashboard.feat_clans"),
    ("clan_notice", "dashboard.feat_clan_notice"),
    ("status", "dashboard.feat_status"),
    ("password", "dashboard.feat_password"),
]

# (clé de ressource, type de salon, libellé, obligatoire pour lancer une queue)
CHANNELS = [
    ("channel_queue_command", "text", "dashboard.chan_command", True),
    ("channel_queue_announcement", "text", "dashboard.chan_announcement", True),
    ("voice_queue_waiting", "voice", "dashboard.chan_waiting", True),
    ("channel_queue_resultat", "text", "dashboard.chan_result", False),
    ("channel_queue_classement", "text", "dashboard.chan_ranking", False),
    ("category_clan", "category", "dashboard.chan_clan_category", False),
]

# (clé, libellé, peut valoir « aucun »)
ROLES = [
    ("role_staff", "dashboard.role_staff", False),
    ("role_connexion", "dashboard.role_connexion", True),
    ("role_clan_leader", "dashboard.role_clan_leader", True),
    ("role_clan_transfer", "dashboard.role_clan_transfer", True),
]

# (clé, libellé, minimum, maximum)
MMR_NUMBERS = [
    ("start", "dashboard.mmr_start", 0, 100000),
    ("win", "dashboard.mmr_win", 0, 1000),
    ("loss", "dashboard.mmr_loss", 0, 1000),
    ("mvp_bonus", "dashboard.mmr_mvp", 0, 1000),
    ("streak_bonus", "dashboard.mmr_streak", 0, 1000),
    ("captain_vote_seconds", "dashboard.mmr_captain_seconds", 10, 600),
    ("mvp_vote_seconds", "dashboard.mmr_mvp_seconds", 10, 3600),
    ("cleanup_seconds", "dashboard.mmr_cleanup_seconds", 10, 3600),
]

MMR_SWITCHES = [
    ("enabled", "dashboard.mmr_enabled"),
    ("captains", "dashboard.mmr_captains"),
    ("rank_roles", "dashboard.mmr_rank_roles"),
]


def _checked(form, name: str) -> bool:
    return str(form.get(name, "")).strip() in {"1", "on", "true", "yes"}


def _int_in(raw, low: int, high: int, fallback: int) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return fallback
    return min(max(value, low), high)


# ---------------------------------------------------------------------------
# Listes proposées
# ---------------------------------------------------------------------------

def _channel_options(guild, kind: str, guild_id: int):
    """Les salons du serveur, dans l'ordre où Discord les affiche. Pas de
    plafond à 25 comme dans un menu Discord : tout le serveur tient ici."""
    if kind == "text":
        found = [(c, f"# {c.name}") for c in guild.text_channels]
    elif kind == "voice":
        found = [(c, f"🔊 {c.name}") for c in guild.voice_channels]
    else:
        found = [(c, c.name) for c in guild.categories]

    options = [("", t(guild_id, "dashboard.none"))]
    options += [(str(channel.id), label) for channel, label in found]
    return options


def _role_options(guild, guild_id: int, *, allow_none: bool):
    """Les rôles, du plus haut au plus bas. @everyone n'y figure jamais :
    le donner comme organisateur ouvrirait la queue au serveur entier."""
    options = [("", t(guild_id, "dashboard.none"))] if allow_none else []
    roles = [role for role in guild.roles if not role.is_default()]
    options += [(str(role.id), f"@{role.name}") for role in sorted(
        roles, key=lambda r: r.position, reverse=True
    )]
    return options


# ---------------------------------------------------------------------------
# Cartes
# ---------------------------------------------------------------------------

def _features_card(guild_id: int, csrf: str) -> str:
    features = get_features(guild_id)
    body = "".join(
        row(
            t(guild_id, label),
            switch(f"f_{key}", bool(features.get(key)), label=t(guild_id, label)),
            hint=t(guild_id, f"{label}_hint"),
        )
        for key, label in FEATURES
    )
    return card(
        glyph="toggle",
        title=t(guild_id, "dashboard.feat_title"),
        subtitle=t(guild_id, "dashboard.feat_desc"),
        form_action=f"/g/{guild_id}/server/features",
        csrf=csrf,
        body=body,
        footer=save_button(guild_id),
    )


def _channels_card(guild, guild_id: int, csrf: str) -> str:
    rows = []
    for key, kind, label, required in CHANNELS:
        current = get_resource_id(guild_id, key) or ""
        rows.append(row(
            t(guild_id, label),
            select(f"c_{key}", _channel_options(guild, kind, guild_id), str(current),
                   label=t(guild_id, label)),
            hint=t(guild_id, "dashboard.chan_required" if required else "dashboard.chan_optional"),
        ))

    ready = queue_ready(guild_id)
    badge = (
        f'<span class="hint">{icon("check" if ready else "alert", size=15)} '
        f'{esc(t(guild_id, "dashboard.ready_ok" if ready else "dashboard.ready_no"))}</span>'
    )
    return card(
        glyph="hash",
        title=t(guild_id, "dashboard.chan_title"),
        subtitle=t(guild_id, "dashboard.chan_desc"),
        form_action=f"/g/{guild_id}/server/channels",
        csrf=csrf,
        body="".join(rows),
        footer=badge + save_button(guild_id),
    )


def _roles_card(guild, guild_id: int, csrf: str) -> str:
    rows = []
    for key, label, allow_none in ROLES:
        current = get_resource_id(guild_id, key) or ""
        rows.append(row(
            t(guild_id, label),
            select(f"r_{key}", _role_options(guild, guild_id, allow_none=allow_none),
                   str(current), label=t(guild_id, label)),
            hint=t(guild_id, f"{label}_hint"),
        ))
    return card(
        glyph="shield",
        title=t(guild_id, "dashboard.role_title"),
        subtitle=t(guild_id, "dashboard.role_desc"),
        form_action=f"/g/{guild_id}/server/roles",
        csrf=csrf,
        body="".join(rows),
        footer=save_button(guild_id),
    )


def _mmr_card(guild_id: int, csrf: str) -> str:
    config = get_mmr_config(guild_id)
    body = "".join(
        row(t(guild_id, label), switch(f"m_{key}", bool(config.get(key)), label=t(guild_id, label)),
            hint=t(guild_id, f"{label}_hint"))
        for key, label in MMR_SWITCHES
    )
    body += "".join(
        row(t(guild_id, label),
            number_input(f"m_{key}", config.get(key, MMR_DEFAULTS[key]),
                         low=low, high=high, label=t(guild_id, label)))
        for key, label, low, high in MMR_NUMBERS
    )
    return card(
        glyph="trophy",
        title=t(guild_id, "dashboard.mmr_title"),
        subtitle=t(guild_id, "dashboard.mmr_desc"),
        form_action=f"/g/{guild_id}/server/mmr",
        csrf=csrf,
        body=body,
        footer=save_button(guild_id),
    )


def _password_card(guild_id: int, csrf: str) -> str:
    current = get_queue_password(guild_id) or ""
    on = bool(get_features(guild_id).get("password"))
    return card(
        glyph="lock",
        title=t(guild_id, "dashboard.pwd_title"),
        subtitle=t(guild_id, "dashboard.pwd_desc"),
        form_action=f"/g/{guild_id}/server/password",
        csrf=csrf,
        body=row(
            t(guild_id, "dashboard.pwd_field"),
            text_input("password", current, limit=PASSWORD_LIMIT,
                       placeholder=t(guild_id, "dashboard.pwd_clear"),
                       label=t(guild_id, "dashboard.pwd_field")),
            # Allumer l'option sans mot de passe ne verrouille rien : c'est le
            # comportement de `active_queue_password`, autant le dire ici.
            hint=t(guild_id, "dashboard.pwd_hint" if on else "dashboard.pwd_off"),
        ),
        footer=save_button(guild_id),
    )


def render_page(guild, guild_id: int, csrf: str, notice: str = "") -> str:
    body = (
        notice
        + _features_card(guild_id, csrf)
        + _channels_card(guild, guild_id, csrf)
        + _roles_card(guild, guild_id, csrf)
        + _mmr_card(guild_id, csrf)
        + _password_card(guild_id, csrf)
    )
    return layout(
        guild_id,
        title=t(guild_id, "dashboard.server_title"),
        body=body,
        guild_name=guild.name if guild is not None else "",
        active="server",
        nav_guild_id=guild_id,
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _redirect(guild_id: int, key: str) -> web.HTTPFound:
    return web.HTTPFound(f"/g/{guild_id}/server?m={key}")


async def get_server(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    guild = request[MEMBER].guild
    notice = flash(guild_id, request.query.get("m"))
    html = render_page(guild, guild_id, request[SESSION]["csrf"], notice)
    return web.Response(text=html, content_type="text/html")


async def post_features(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    form = await request.post()
    wanted = {key: _checked(form, f"f_{key}") for key, _label in FEATURES}

    # Même garde que /option : sans catégorie, les salons de clan n'ont nulle
    # part où être créés. On refuse plutôt que d'allumer une fonction cassée.
    if wanted.get("clans") and not get_resource_id(guild_id, "category_clan"):
        return _redirect(guild_id, "err_clan_category")

    set_features(guild_id, **wanted)
    log.info(f"[DASHBOARD] Fonctions mises à jour — guild {guild_id} par {request[MEMBER].id}")
    return _redirect(guild_id, "saved_features")


async def post_channels(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    guild = request[MEMBER].guild
    form = await request.post()

    for key, kind, _label, _required in CHANNELS:
        raw = str(form.get(f"c_{key}", "")).strip()
        if not raw:
            clear_resource_id(guild_id, key)
            continue
        try:
            channel = guild.get_channel(int(raw))
        except (TypeError, ValueError):
            channel = None
        # Un identifiant bricolé, ou un salon supprimé entre l'affichage et
        # l'envoi : on ne mémorise que ce qui existe vraiment, du bon type.
        if channel is None or not _matches(channel, kind):
            continue
        set_resource_id(guild_id, key, channel.id)

    log.info(f"[DASHBOARD] Salons mis à jour — guild {guild_id} par {request[MEMBER].id}")
    return _redirect(guild_id, "saved_channels")


def _matches(channel, kind: str) -> bool:
    import discord

    if kind == "text":
        return isinstance(channel, discord.TextChannel)
    if kind == "voice":
        return isinstance(channel, discord.VoiceChannel)
    return isinstance(channel, discord.CategoryChannel)


async def post_roles(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    guild = request[MEMBER].guild
    form = await request.post()

    chosen: dict[str, object] = {}
    for key, _label, allow_none in ROLES:
        raw = str(form.get(f"r_{key}", "")).strip()
        if not raw:
            if not allow_none:
                continue  # le rôle organisateur ne se retire pas
            chosen[key] = None
            continue
        try:
            role = guild.get_role(int(raw))
        except (TypeError, ValueError):
            role = None
        if role is None:
            continue
        if role.is_default():
            # @everyone comme organisateur donnerait la queue à tout le monde.
            if not allow_none:
                return _redirect(guild_id, "err_staff_everyone")
            chosen[key] = None
            continue
        chosen[key] = role.id

    for key, value in chosen.items():
        if value is None:
            clear_resource_id(guild_id, key)
        else:
            set_resource_id(guild_id, key, int(value))

    log.info(f"[DASHBOARD] Rôles mis à jour — guild {guild_id} par {request[MEMBER].id}")
    return _redirect(guild_id, "saved_roles")


async def post_mmr(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    form = await request.post()
    current = get_mmr_config(guild_id)

    changes: dict[str, object] = {key: _checked(form, f"m_{key}") for key, _label in MMR_SWITCHES}
    for key, _label, low, high in MMR_NUMBERS:
        changes[key] = _int_in(form.get(f"m_{key}"), low, high,
                               int(current.get(key, MMR_DEFAULTS[key])))

    set_mmr_config(guild_id, **changes)
    log.info(f"[DASHBOARD] MMR mis à jour — guild {guild_id} par {request[MEMBER].id}")
    return _redirect(guild_id, "saved_mmr")


async def post_password(request: web.Request) -> web.Response:
    guild_id = request[GUILD_ID]
    form = await request.post()
    # Pas de `sanitize` ici, contrairement au reste : le mot de passe est
    # comparé caractère par caractère à ce que tape un joueur
    # (hmac.compare_digest dans cogs/queue_config.py). Une espace de largeur
    # nulle glissée dedans le rendrait impossible à saisir.
    password = str(form.get("password", "")).strip()[:PASSWORD_LIMIT]
    set_queue_password(guild_id, password or None)
    if not password:
        # Même conséquence que dans /option : sans mot de passe, l'option
        # n'aurait plus rien à demander.
        set_features(guild_id, password=False)
    log.info(f"[DASHBOARD] Mot de passe de queue modifié — guild {guild_id}")
    return _redirect(guild_id, "saved_password")


def add_routes(app: web.Application) -> None:
    app.router.add_get("/g/{gid}/server", get_server)
    app.router.add_post("/g/{gid}/server/features", post_features)
    app.router.add_post("/g/{gid}/server/channels", post_channels)
    app.router.add_post("/g/{gid}/server/roles", post_roles)
    app.router.add_post("/g/{gid}/server/mmr", post_mmr)
    app.router.add_post("/g/{gid}/server/password", post_password)
