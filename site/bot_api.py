"""
Dialogue avec le bot
====================
Le site n'ouvre jamais les fichiers du bot : il appelle l'API que le bot
expose (voir cogs/dashboard_api.py), avec la clé partagée BOT_API_KEY.

Si le bot est éteint ou injoignable, toutes ces fonctions lèvent
BotApiError : le site affiche alors une page « bot injoignable » au lieu
de planter.
"""

import os
from typing import Any

import httpx


class BotApiError(Exception):
    """Le bot n'a pas répondu, ou a répondu une erreur."""


def _base_url() -> str:
    return os.getenv("BOT_API_URL", "").strip().rstrip("/")


def _headers() -> dict[str, str]:
    return {"X-API-Key": os.getenv("BOT_API_KEY", "").strip()}


async def _request(method: str, path: str, **kwargs) -> Any:
    base = _base_url()
    if not base:
        raise BotApiError("BOT_API_URL n'est pas renseigné dans le .env du site")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(
                method, f"{base}{path}", headers=_headers(), **kwargs
            )
    except httpx.HTTPError as e:
        raise BotApiError(f"bot injoignable ({e.__class__.__name__})") from e

    if response.status_code == 401:
        raise BotApiError("clé refusée par le bot : BOT_API_KEY ne correspond pas")
    if response.status_code == 404:
        raise BotApiError("le bot n'est pas sur ce serveur")
    if response.status_code >= 400:
        detail = ""
        try:
            detail = response.json().get("error", "")
        except ValueError:
            pass
        raise BotApiError(f"réponse {response.status_code} du bot {detail}".strip())
    return response.json()


async def health() -> dict:
    return await _request("GET", "/api/health")


async def guilds() -> list[dict]:
    """Serveurs où le bot est présent."""
    return await _request("GET", "/api/guilds")


def _only(guild_ids: list[str]) -> str:
    """Les serveurs demandés, en paramètre d'adresse."""
    return ",".join(str(guild_id) for guild_id in guild_ids)


async def stats(guild_ids: list[str]) -> dict:
    """Uptime, nombre de serveurs, de membres et de commandes du jour."""
    return await _request("GET", "/api/stats", params={"guilds": _only(guild_ids)})


async def is_owner(user_id: str) -> bool:
    """Cette personne est-elle le propriétaire du bot ?

    Demandé une fois à la connexion. Si le bot ne répond pas, la réponse
    est non : mieux vaut cacher le journal que le montrer par erreur."""
    try:
        return bool((await _request("GET", "/api/viewer", params={"user": user_id}))["owner"])
    except (BotApiError, KeyError, TypeError):
        return False


async def commands(user_id: str, limit: int = 25) -> list[dict]:
    """Les dernières commandes, tous serveurs confondus.

    Réservé au propriétaire du bot : c'est l'API qui le vérifie, à partir
    de l'identifiant Discord de la personne connectée."""
    return await _request("GET", "/api/commands",
                          params={"user": user_id, "limit": limit})


async def guild(guild_id: str) -> dict:
    return await _request("GET", f"/api/guilds/{guild_id}")


async def options(guild_id: str) -> dict:
    """Salons et rôles proposés dans les listes déroulantes."""
    return await _request("GET", f"/api/guilds/{guild_id}/options")


async def patch(guild_id: str, payload: dict) -> dict:
    return await _request("PATCH", f"/api/guilds/{guild_id}", json=payload)
