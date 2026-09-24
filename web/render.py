"""
Render — Le HTML du dashboard.
================================
Pas de moteur de templates : `requirements.txt` fige des versions testées, et
ajouter Jinja2 pour quelques pages ne se justifie pas. Les pages se composent
donc ici, à partir de briques communes — `card`, `row`, `switch`, `select`…

Règle unique mais absolue : `esc()` sur TOUTE valeur venant d'un serveur
Discord. Un nom d'équipe, de salon, de rôle ou de serveur peut contenir
n'importe quoi, y compris des chevrons.
"""

from __future__ import annotations

from html import escape

from i18n import get_lang, t


def esc(value) -> str:
    """Échappe une valeur pour le corps du HTML comme pour un attribut."""
    return escape("" if value is None else str(value), quote=True)


# ---------------------------------------------------------------------------
# Icônes — un petit jeu de SVG tracés, hérités de `currentColor`.
# ---------------------------------------------------------------------------

_ICONS = {
    "queue": '<path d="M3 6h18M3 12h18M3 18h12"/>',
    "teams": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>',
    "bookmark": '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
    "toggle": '<rect x="1" y="5" width="22" height="14" rx="7"/><circle cx="16" cy="12" r="3"/>',
    "hash": '<path d="M4 9h16M4 15h16M10 3L8 21M16 3l-2 18"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "trophy": '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/>'
              '<path d="M6 2h12v7a6 6 0 0 1-12 0z"/><path d="M9 22h6M12 15v7"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "alert": '<circle cx="12" cy="12" r="10"/><path d="M12 8v5M12 16h.01"/>',
}


def icon(name: str, *, size: int = 18) -> str:
    path = _ICONS.get(name)
    if not path:
        return ""
    return (
        f'<svg class="icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{path}</svg>'
    )


# ---------------------------------------------------------------------------
# Structure de page
# ---------------------------------------------------------------------------

NAV = (
    ("queue", "queue", "dashboard.nav_queue"),
    ("server", "toggle", "dashboard.nav_server"),
)


def layout(
    guild_id: int | None,
    *,
    title: str,
    body: str,
    guild_name: str = "",
    active: str = "",
    nav_guild_id: int | None = None,
) -> str:
    """Le squelette commun. `lang` suit la langue du serveur, comme les embeds."""
    lang = get_lang(guild_id)

    nav = ""
    if nav_guild_id is not None:
        links = "".join(
            f'<a class="tab{" on" if key == active else ""}" href="/g/{nav_guild_id}/{key}">'
            f'{icon(glyph, size=16)}<span>{esc(t(guild_id, label))}</span></a>'
            for key, glyph, label in NAV
        )
        nav = f'<nav class="tabs">{links}</nav>'

    header = ""
    if guild_name:
        header = (
            '<header class="top">'
            '<div class="top-in">'
            '<div class="brand"><span class="dot"></span>CreateYourQueue</div>'
            f'<div class="guild" title="{esc(guild_name)}">{esc(guild_name)}</div>'
            "</div>"
            f'<div class="top-in">{nav}</div>'
            "</header>"
        )

    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{esc(lang)}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        '<meta name="color-scheme" content="dark light">\n'
        f"<title>{esc(title)}</title>\n"
        '<link rel="stylesheet" href="/static/style.css">\n'
        "</head>\n"
        "<body>\n"
        f"{header}\n"
        f'<main class="wrap">\n{body}\n</main>\n'
        '<script src="/static/app.js" defer></script>\n'
        "</body>\n</html>\n"
    )


def card(*, title: str, body: str, subtitle: str = "", glyph: str = "", footer: str = "",
         form_action: str = "", csrf: str = "") -> str:
    """Une section. Avec `form_action`, la carte EST un formulaire : chaque
    section s'enregistre seule, sans réécrire les réglages des autres."""
    head = '<div class="card-head">'
    if glyph:
        head += f'<div class="card-icon">{icon(glyph)}</div>'
    head += f"<div><h2>{esc(title)}</h2>"
    if subtitle:
        head += f'<p class="sub">{esc(subtitle)}</p>'
    head += "</div></div>"
    inner = head + f'<div class="card-body">{body}</div>'
    if footer:
        inner += f'<div class="card-foot">{footer}</div>'
    if form_action:
        return (
            f'<form method="post" action="{esc(form_action)}" class="card">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}">{inner}</form>'
        )
    return f'<section class="card">{inner}</section>'


def row(label: str, control: str, *, hint: str = "", stacked: bool = False) -> str:
    """Une ligne de réglage : intitulé à gauche, contrôle à droite."""
    text = f'<div class="row-text"><span>{esc(label)}</span>'
    if hint:
        text += f'<small>{esc(hint)}</small>'
    text += "</div>"
    return f'<div class="row{" stacked" if stacked else ""}">{text}<div class="row-ctl">{control}</div></div>'


def save_button(guild_id: int | None) -> str:
    return f'<button type="submit" class="primary">{esc(t(guild_id, "dashboard.save"))}</button>'


# ---------------------------------------------------------------------------
# Contrôles
# ---------------------------------------------------------------------------

def switch(name: str, checked: bool, *, label: str = "") -> str:
    """Interrupteur : une case à cocher habillée, donc utilisable au clavier
    et envoyée par le formulaire même sans JavaScript."""
    return (
        f'<label class="switch"><input type="checkbox" name="{esc(name)}" value="1"'
        f'{" checked" if checked else ""}'
        + (f' aria-label="{esc(label)}"' if label else "")
        + '><span class="track"></span></label>'
    )


def select(name: str, options, selected, *, label: str = "") -> str:
    opts = "".join(
        f'<option value="{esc(value)}"{" selected" if str(value) == str(selected) else ""}>'
        f"{esc(text)}</option>"
        for value, text in options
    )
    aria = f' aria-label="{esc(label)}"' if label else ""
    return f'<select name="{esc(name)}"{aria}>{opts}</select>'


def text_input(name: str, value, *, limit: int, required: bool = False,
               placeholder: str = "", label: str = "", kind: str = "text") -> str:
    aria = f' aria-label="{esc(label)}"' if label else ""
    value = "" if value is None else value
    return (
        f'<input type="{esc(kind)}" name="{esc(name)}" value="{esc(value)}"'
        f' maxlength="{limit}"{" required" if required else ""}'
        f' placeholder="{esc(placeholder)}"{aria}>'
    )


def number_input(name: str, value, *, low: int, high: int, label: str = "") -> str:
    aria = f' aria-label="{esc(label)}"' if label else ""
    return (
        f'<input type="number" class="num" name="{esc(name)}" value="{esc(value)}"'
        f' min="{low}" max="{high}" step="1"{aria}>'
    )


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

# Le paramètre `?m=` vient de l'URL, donc de l'utilisateur. Sans cette liste,
# n'importe quelle valeur s'afficherait telle quelle (`t()` renvoie la clé
# quand elle est inconnue) : échappée, donc inoffensive, mais incompréhensible.
FLASH_KEYS = frozenset({
    "saved", "saved_preset", "loaded_preset", "deleted_preset",
    "saved_features", "saved_channels", "saved_roles", "saved_mmr", "saved_password",
    "err_name", "err_dup", "err_preset_name", "err_preset_limit", "err_preset_gone",
    "err_staff_everyone", "err_clan_category",
})


def flash(guild_id: int | None, kind: str | None) -> str:
    """Bandeau de retour après un POST (`?m=saved`, `?m=err_dup`…)."""
    if not kind or kind not in FLASH_KEYS:
        return ""
    bad = kind.startswith("err_")
    return (
        f'<div class="flash {"err" if bad else "ok"}">'
        f'{icon("alert" if bad else "check", size=16)}'
        f'<span>{esc(t(guild_id, f"dashboard.flash_{kind}"))}</span></div>'
    )


def message_page(guild_id: int | None, key: str, *, title_key: str = "dashboard.err_title") -> str:
    """Page d'erreur ou d'information, sans rien divulguer de plus que le message."""
    body = (
        '<section class="card solo">'
        '<div class="card-body">'
        f'<div class="solo-mark">{icon("shield", size=28)}</div>'
        f"<h1>{esc(t(guild_id, title_key))}</h1>"
        f'<p class="sub">{esc(t(guild_id, key))}</p>'
        "</div></section>"
    )
    return layout(guild_id, title=t(guild_id, title_key), body=body)
