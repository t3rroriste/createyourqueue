"""
i18n — Moteur de traduction multi-langue
=========================================
Utilisation : from i18n import t
              t(interaction.guild_id, "help.overview_title")
              t(interaction.guild_id, "queue.started_desc", team=name)

Langues : fr (défaut CreateYourQueue), en (défaut autres serveurs), es, de, ko
"""

import json
import os
import re
from typing import Any

import custom_emojis
from json_store import write_json
import logging

# Chargé au démarrage, mis à jour par set_lang()
_guild_langs: dict[int, str] = {}
_locale_cache: dict[str, dict] = {}

LANG_FILE = "data/guild_langs.json"
log = logging.getLogger("bot.i18n")

LANGUAGES: dict[str, dict[str, str]] = {
    "fr": {"name": "Français",  "flag": "🇫🇷"},
    "en": {"name": "English",   "flag": "🇬🇧"},
    "es": {"name": "Español",   "flag": "🇪🇸"},
    "de": {"name": "Deutsch",   "flag": "🇩🇪"},
    "ko": {"name": "한국어",     "flag": "🇰🇷"},
}

# ⚠️ et ❌ s'affichent avec les emojis perso Zoom125 et cross du bot principal.
# Le modmail et le bot temporaire (ghost ping, suggestions) sont d'autres
# applications : un emoji d'application ne s'affiche que pour la sienne, ils
# gardent les emojis de Discord.
_CUSTOM = ((re.compile("⚠️?"), "zoom125"), (re.compile("❌"), "cross"))
_OTHER_BOTS = ("modmail.", "ghost.", "suggest.")


# Cache des cles deja resolues : {langue: {cle: valeur}}. Vide au rechargement.
_resolved: dict[str, dict[str, Any]] = {}

# Le serveur officiel est toujours en francais (voir config.py).
_official_guild: int = 0


def load_langs() -> None:
    global _guild_langs, _official_guild
    _resolved.clear()
    _locale_cache.clear()
    from config import GUNZFRANCE_GUILD_ID
    _official_guild = GUNZFRANCE_GUILD_ID or 0
    if not os.path.exists(LANG_FILE):
        return
    try:
        with open(LANG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _guild_langs = {int(k): v for k, v in data.items()}
    except (OSError, ValueError, AttributeError) as e:
        log.warning(f"Langues des serveurs illisibles ({e}) : langue par défaut partout")


def save_langs() -> None:
    write_json(LANG_FILE, {str(k): v for k, v in _guild_langs.items()}, indent=4)


def set_lang(guild_id: int, lang: str) -> None:
    _guild_langs[guild_id] = lang
    save_langs()


def get_lang(guild_id: int | None) -> str:
    """La langue d'un serveur : son choix s'il en a fait un, sinon le défaut.

    Le serveur officiel était VERROUILLÉ en français ici, avant tout examen
    de ce qui avait été choisi. `set_lang` écrivait donc dans le vide : le
    tableau de bord affichait « Enregistré », le fichier gardait la nouvelle
    langue, et le bot continuait de répondre en français. Un réglage qu'on
    accepte et qu'on ignore ensuite, c'est exactement ce que le projet
    s'interdit — un écran qui ment.

    Le français reste le DÉFAUT du serveur officiel, ce qui était l'intention
    (voir config.py), mais un choix explicite l'emporte. Rien n'est perdu :
    sans intervention, ce serveur est toujours en français.
    """
    if guild_id is None:
        return "en"
    choisie = _guild_langs.get(guild_id)
    if choisie is not None:
        return choisie
    if _official_guild and guild_id == _official_guild:
        return "fr"
    return "en"


def _get_locale(lang: str) -> dict:
    if lang not in _locale_cache:
        path = f"locales/{lang}.json"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    _locale_cache[lang] = json.load(f)
            except Exception:
                _locale_cache[lang] = {}
        else:
            _locale_cache[lang] = {}
    return _locale_cache[lang]


def _emojis(key: str, text: str) -> str:
    """Remplace ⚠️ et ❌ par les emojis perso, avant d'insérer les variables :
    le texte saisi par un membre n'est jamais touché."""
    if key.startswith(_OTHER_BOTS):
        return text
    for pattern, name in _CUSTOM:
        text = pattern.sub(custom_emojis.get(name), text)
    return text


def t(guild_id: int | None, key: str, **kwargs: Any) -> str:
    """Translate a dot-separated key for the given guild's language."""
    lang  = get_lang(guild_id)
    value = _resolve(lang, key)
    if value is None and lang != "en":
        value = _resolve("en", key)
    if value is None and lang != "fr":
        value = _resolve("fr", key)
    if value is None:
        return key
    text = _emojis(key, str(value))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def t_in(lang: str, key: str, **kwargs: Any) -> str:
    """Traduit dans une langue EXPLICITE, sans passer par celle du serveur."""
    value = _resolve(lang, key)
    if value is None:
        return ""
    text = _emojis(key, str(value))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def _resolve(lang: str, key: str) -> Any:
    """Valeur d une cle pointee, memorisee."""
    memo = _resolved.get(lang)
    if memo is None:
        memo = _resolved[lang] = {}
    elif key in memo:
        return memo[key]
    node: Any = _get_locale(lang)
    for part in key.split("."):
        if not isinstance(node, dict):
            node = None
            break
        node = node.get(part)
    memo[key] = node
    return node
