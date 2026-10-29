"""
Journal d'activité — qui a changé quoi, et depuis où.
=====================================================
Le bot avait bien un journal, mais EN MÉMOIRE (`cogs/dashboard_api.py`) :
un redémarrage l'effaçait, et il ne retenait que les commandes Discord. Un
réglage modifié depuis le panneau web ne laissait donc aucune trace nulle
part. D'où « c'est pas moi qui ai touché au MMR », auquel personne ne
pouvait répondre.

Celui-ci est écrit sur le disque, un fichier par serveur, et il note les
deux chemins : le panneau et Discord. Une ligne, c'est QUAND, QUI, QUOI,
et D'OÙ.

    {"at": "...", "who": {"id": "...", "name": "..."},
     "source": "panel" | "discord", "action": "settings",
     "details": ["mmr.win", "language"]}

CE QU'IL NE CONTIENT PAS, et c'est délibéré : les VALEURS. Seuls les noms
des réglages touchés sont gardés. Un journal qui note « mot de passe de
queue : hiver2026 » devient lui-même un secret à protéger, et il serait lu
par tous les administrateurs du serveur.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from json_store import write_json

log = logging.getLogger("bot.audit")

AUDIT_DIR = "data/audit"

# 300 lignes, c'est plusieurs mois de réglages pour un serveur ordinaire.
# Au-delà, personne ne remonte : ce qu'on cherche dans un journal, c'est
# « qui a fait ça hier », pas l'archéologie.
MAX_LIGNES = 300

_cache: dict[int, list[dict[str, Any]]] = {}


def _path(guild_id: int) -> str:
    return os.path.join(AUDIT_DIR, f"{guild_id}.json")


def _lire(guild_id: int) -> list[dict[str, Any]]:
    if guild_id in _cache:
        return _cache[guild_id]
    lignes: list[dict[str, Any]] = []
    chemin = _path(guild_id)
    if os.path.exists(chemin):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                brut = json.load(f)
            if isinstance(brut, list):
                lignes = [x for x in brut if isinstance(x, dict)]
        except (OSError, ValueError) as e:
            # Un journal illisible est mis de côté, pas écrasé : c'est
            # précisément le fichier dont on voudra se servir le jour où
            # quelque chose a mal tourné.
            secours = f"{chemin}.illisible-{int(time.time())}"
            try:
                os.replace(chemin, secours)
                log.error(f"Journal illisible ({e}) : mis de côté dans {secours}")
            except OSError:
                log.error(f"Journal illisible ({e}), et impossible à mettre de côté")
    _cache[guild_id] = lignes
    return lignes


def record(guild_id: int, *, action: str, source: str,
           who_id: int | str | None = None, who_name: str | None = None,
           details: list[str] | None = None) -> None:
    """Ajoute une ligne. N'échoue jamais bruyamment : un journal qui
    empêcherait d'enregistrer un réglage serait pire que pas de journal."""
    lignes = _lire(guild_id)
    lignes.insert(0, {
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "panel" if source == "panel" else "discord",
        "action": str(action)[:40],
        "who": {
            "id": str(who_id) if who_id else None,
            "name": (who_name or None),
        },
        # Les NOMS des réglages touchés, jamais leurs valeurs. Trente au
        # plus : un lot qui en change davantage est un import, et la liste
        # complète n'apprendrait rien de plus.
        "details": [str(d)[:60] for d in (details or [])][:30],
    })
    del lignes[MAX_LIGNES:]
    try:
        write_json(_path(guild_id), lignes, indent=2, ensure_ascii=False)
    except OSError as e:
        log.error(f"Journal non enregistré pour {guild_id} : {e}")


def entries(guild_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    """Les dernières lignes, la plus récente d'abord."""
    return _lire(guild_id)[:max(1, limit)]


def forget(guild_id: int) -> None:
    """Oublie ce serveur. Appelé par /reset, et par les tests."""
    _cache.pop(guild_id, None)
    try:
        os.remove(_path(guild_id))
    except OSError:
        pass
