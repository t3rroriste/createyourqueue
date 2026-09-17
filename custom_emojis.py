"""
Custom emojis — les emojis perso du bot principal.
===================================================
Les emojis se téléversent une seule fois, dans le Developer Portal : ton
application → **Emojis** → Upload. Au démarrage, le bot récupère ceux de son
application et les range par nom : aucun identifiant à recopier dans le code.

Le nom à donner dans le portail est celui de la colonne de gauche de
FALLBACKS, avec ou sans le numéro d'emoji.gg devant : « replay » et
« 8562_replay » marchent tous les deux. Discord n'accepte que des lettres,
des chiffres et « _ », 32 caractères au maximum.
"""

from __future__ import annotations

import logging
import re

import discord

log = logging.getLogger("bot.emojis")

# Nom attendu dans le portail -> emoji de secours.
FALLBACKS: dict[str, str] = {
    # Relancer une partie ou une queue
    "replay": "🔁",
    # Notifications de queue en MP (panneau Notif Queue et message privé)
    "discord_notification_settings_d": "🔔",
    # Oui / Non : accepter, refuser, terminer, annuler
    "checkmark": "✅",
    "cross": "✖️",
    # Sondages : options « Oui » et « Non »
    "yes": "✅",
    "no": "❌",
    # Panneau /status
    "tools": "⚙️",
    "statusonline": "🟢",
    "statusoffline": "🔴",
    "stats": "・",
    "green_point": "🟢",
    "yellow_point": "🟡",
    "red_point": "🔴",
    # /schedule et /season
    "clock": "🕒",
    "pause": "⏸️",
    "calender": "📅",
    "notification": "🔔",
    "clipboard": "📋",
    # ModMail (application ModMail) : tickets et messages transmis au staff
    "letter": "📨",
    "communication": "🎯",
    # Duels : bouton « Fin » (fermer le fil tout de suite)
    "off": "⏹️",
}

# Autres noms acceptés pour le même emoji.
ALIASES = {
    "calendar": "calender",
    "notif_queue": "discord_notification_settings_d",
}

# Emojis déjà téléversés, codes copiés depuis Discord. Ils servent même si le
# chargement par nom échoue ; un emoji d'application du même nom les remplace.
MANUAL: dict[str, str] = {
    "pause": "<:776450pause:1549536033215877170>",
    "clipboard": "<:559950clipboard:1549536030590505000>",
    "calender": "<:473488calender:1549536029038354482>",
    "clock": "<:138210clock:1549536027402838146>",
    "yellow_point": "<:90417yellowpoint:1549536026027106334>",
    "green_point": "<:78184greenpoint:1549536024554774688>",
    "red_point": "<:43885redpoint:1549533281496727645>",
    "tools": "<:43365tools:1549536023300538478>",
    "stats": "<:9656stats:1549536021698584748>",
    "replay": "<:8562replay:1549536019882450944>",
    # Même emoji que « notification » : renommé dans le portail le 16/09.
    "discord_notification_settings_d": "<:862785notification:1549536018502394056>",
    "notification": "<:862785notification:1549536018502394056>",
    "cross": "<:2360cross:1549536017105821809>",
    "checkmark": "<:1372checkmark:1549536015734149200>",
    "yes": "<:275836yes:1549841314017837136>",
    "no": "<:975790no:1549841321148157982>",
    "statusonline": "<:971828statusonline:1549841319571230720>",
    "statusoffline": "<:460240statusoffline:1549841317197123694>",
    "off": "<:4247off:1549851998755495987>",
}

_loaded: dict[str, str] = dict(MANUAL)


def _squash(name: str) -> str:
    """Nom sans numéro d'emoji.gg, sans « _ » ni « - », en minuscules : le
    portail retire les « _ », « green_point » devient « 78184greenpoint »."""
    return re.sub(r"[_\-\s]", "", re.sub(r"^\d+", "", name.strip().lower()))


_LOOKUP = {_squash(key): key for key in FALLBACKS}
_LOOKUP.update({_squash(alias): key for alias, key in ALIASES.items()})


def _key(name: str) -> str:
    """« 8562_replay », « 78184greenpoint », « Replay » → le nom de FALLBACKS
    correspondant, ou le nom tel quel s'il n'en correspond aucun."""
    return _LOOKUP.get(_squash(name), name)


async def load(client: discord.Client) -> None:
    """Récupère les emojis de l'application. Une erreur n'empêche jamais le
    bot de démarrer : il garde simplement les emojis de secours."""
    try:
        found = await client.fetch_application_emojis()
    except Exception as e:
        log.warning(f"Emojis perso non chargés, emojis de secours utilisés : {e}")
        return
    for emoji in found:
        key = _key(emoji.name)
        if key in FALLBACKS:
            _loaded[key] = str(emoji)
    missing = sorted(set(FALLBACKS) - set(_loaded))
    log.info(f"{len(_loaded)}/{len(FALLBACKS)} emoji(s) perso chargé(s)"
             + (f" — absents : {', '.join(missing)}" if missing else ""))


async def fetch_own(client: discord.Client, names) -> dict[str, str]:
    """Emojis d'application d'un autre bot du processus (modmail), pour lui seul."""
    wanted = set(names)
    try:
        found = await client.fetch_application_emojis()
    except Exception as e:
        log.warning(f"Emojis perso non chargés, emojis de secours utilisés : {e}")
        return {}
    own = {key: str(emoji) for emoji in found if (key := _key(emoji.name)) in wanted}
    missing = sorted(wanted - set(own))
    if missing:
        log.info(f"Emoji(s) absent(s) de l'application {client.user} : {', '.join(missing)}")
    return own


def get(name: str) -> str:
    """L'emoji perso s'il a été téléversé, sinon celui de secours."""
    return _loaded.get(name) or FALLBACKS[name]


def has(name: str) -> bool:
    """Vrai si l'emoji perso a été trouvé dans l'application."""
    return name in _loaded
