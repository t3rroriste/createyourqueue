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
from typing import Any
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
    if guild_id is None:
        return "en"
    if _official_guild and guild_id == _official_guild:
        return "fr"
    return _guild_langs.get(guild_id, "en")


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
    text = str(value)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def t_in(lang: str, key: str, **kwargs: Any) -> str:
    """Traduit dans une langue EXPLICITE, sans passer par celle du serveur.

    Nécessaire pour comparer le nom actuel d'un salon au nom qu'il aurait dans
    l'ancienne langue (voir retranslate.py) : au moment où on vérifie, la
    nouvelle langue est déjà enregistrée."""
    value = _resolve(lang, key)
    if value is None:
        return ""
    text = str(value)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def _resolve(lang: str, key: str) -> Any:
    """Valeur d une cle pointee, memorisee.

    Les traductions sont chargees une fois et ne changent plus en cours
    d execution : redecouper la cle et retraverser le JSON a chaque appel
    coutait pour rien. Le cache est vide par load_langs()."""
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
