"""
Command sync — Synchronisation des commandes slash sans gaspiller le quota.
============================================================================
`bot.tree.sync()` est une des routes les plus limitées de l'API Discord. Or
`on_ready` ne se déclenche pas seulement au démarrage : il repart à CHAQUE
reconnexion au gateway (coupure réseau, RESUME raté, redéploiement...). Un
`sync()` posé là finit par épuiser le quota, et Discord répond alors 429 sur
toutes les tentatives suivantes — les nouvelles commandes n'apparaissent plus.

Deux protections :
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import discord
from discord import app_commands
from json_store import write_json

log = logging.getLogger("bot.command_sync")

FINGERPRINT_FILE = "data/command_sync.json"


def _describe_parameter(param: app_commands.Parameter) -> dict[str, Any]:
    return {
        "name": param.name,
        "description": param.description,
        "required": param.required,
        "type": str(param.type),
        "choices": sorted(str(c.value) for c in param.choices),
    }


def _flags(value: Any) -> Any:
    return getattr(value, "value", None) if value is not None else None


def _describe(command: Any) -> dict[str, Any]:
    """Représentation stable d'une commande ou d'un groupe, pour comparaison."""
    if isinstance(command, app_commands.Group):
        return {
            "name": command.name,
            "description": command.description,
            "permissions": _flags(getattr(command, "default_permissions", None)),
            "options": sorted(
                (_describe(sub) for sub in command.commands),
                key=lambda d: d["name"],
            ),
        }
    return {
        "name": command.name,
        "description": getattr(command, "description", ""),
        "params": [_describe_parameter(p) for p in getattr(command, "parameters", [])],
        "permissions": _flags(getattr(command, "default_permissions", None)),
    }


def fingerprint(tree: app_commands.CommandTree) -> str:
    payload = {
        "commands": sorted((_describe(c) for c in tree.get_commands()), key=lambda d: d["name"]),
        "contexts": _flags(getattr(tree, "allowed_contexts", None)),
        "installs": [getattr(tree.allowed_installs, "guild", None), getattr(tree.allowed_installs, "user", None)]
        if getattr(tree, "allowed_installs", None) else None,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_stored() -> str | None:
    if not os.path.exists(FINGERPRINT_FILE):
        return None
    try:
        with open(FINGERPRINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("fingerprint")
    except Exception:
        return None


def _store(value: str) -> None:
    try:
        write_json(FINGERPRINT_FILE, {'fingerprint': value}, indent=4)
    except Exception as e:
        log.error(f"Impossible d'enregistrer l'empreinte des commandes : {e}")


async def sync_if_changed(bot: discord.Client, *, force: bool = False) -> int | None:
    """Synchronise l'arbre des commandes seulement si nécessaire."""
    if getattr(bot, "_cyq_synced", False) and not force:
        return None

    tree = bot.tree  # type: ignore[attr-defined]
    current = fingerprint(tree)
    stored = _load_stored()

    if current == stored and not force:
        bot._cyq_synced = True  # type: ignore[attr-defined]
        log.info("Commandes inchangées depuis la dernière synchronisation — sync évité.")
        return None

    try:
        synced = await tree.sync()
    except discord.HTTPException as e:
        if e.status == 429:
            retry = getattr(e, "retry_after", None)
            wait = f" Réessaie dans {retry:.0f}s." if retry else ""
            log.error(
                "Synchronisation des commandes limitée par Discord (429)." + wait +
                " Les commandes déjà enregistrées continuent de fonctionner ;"
                " la synchronisation sera retentée au prochain démarrage."
            )
        else:
            log.error(f"Erreur lors de la synchronisation des commandes : {e}")
        return None
    except Exception as e:
        log.error(f"Erreur lors de la synchronisation des commandes : {e}")
        return None

    bot._cyq_synced = True  # type: ignore[attr-defined]
    _store(current)
    log.info(f"{len(synced)} commande(s) slash synchronisée(s).")
    return len(synced)
