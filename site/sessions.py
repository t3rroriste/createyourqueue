"""
Sessions du site
================
Le cookie du navigateur ne contient qu'un identifiant au hasard ; tout le
reste (pseudo, serveurs, jeton Discord) reste ici, en mémoire du site.
Le jeton Discord ne sort donc jamais du serveur.

Conséquence assumée : redémarrer le site déconnecte tout le monde. C'est
sans gravité, il suffit de se reconnecter en un clic. Si un jour le site
tourne sur plusieurs processus, il faudra remplacer ce dictionnaire par
Redis ou une base.
"""

import secrets
import time
from typing import Any

# Durée d'une session : 12 h, puis il faut se reconnecter.
TTL_SECONDS = 12 * 3600

_store: dict[str, dict[str, Any]] = {}


def _purge() -> None:
    now = time.time()
    for sid in [sid for sid, entry in _store.items() if entry["expires_at"] < now]:
        del _store[sid]


def create(data: dict[str, Any]) -> str:
    """Enregistre une session et renvoie son identifiant."""
    _purge()
    sid = secrets.token_urlsafe(32)
    _store[sid] = {"data": data, "expires_at": time.time() + TTL_SECONDS}
    return sid


def get(sid: str | None) -> dict[str, Any] | None:
    if not sid:
        return None
    entry = _store.get(sid)
    if entry is None:
        return None
    if entry["expires_at"] < time.time():
        del _store[sid]
        return None
    return entry["data"]


def drop(sid: str | None) -> None:
    if sid:
        _store.pop(sid, None)
