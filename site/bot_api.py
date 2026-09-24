"""
Client de l'API du bot
======================
Le bot expose son API dans cogs/dashboard_api.py, protegee par une cle.
Ce module est le seul endroit du site qui sait comment lui parler : les
routes de main.py appellent ces fonctions, pas httpx directement.

Aucune de ces fonctions ne leve d'exception HTTP : elles renvoient None ou
remontent une BotUnreachable, et main.py decide quoi afficher.
"""

from typing import Any

import httpx

from settings import BOT_API_KEY, BOT_API_TIMEOUT, BOT_API_URL


class BotUnreachable(Exception):
    """Le bot ne repond pas, ou repond autre chose que ce qu'on attend."""


class BotRefused(Exception):
    """Le bot a repondu, mais il refuse : cle invalide, serveur inconnu."""

    def __init__(self, status: int, code: str):
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code


def _headers() -> dict[str, str]:
    return {"X-API-Key": BOT_API_KEY, "Accept": "application/json"}


async def _call(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{BOT_API_URL.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=BOT_API_TIMEOUT) as client:
            response = await client.request(method, url, headers=_headers(), **kwargs)
    except httpx.HTTPError as e:
        # Bot eteint, port ferme, DNS qui ne repond pas : tout arrive ici.
        raise BotUnreachable(str(e)) from e

    if response.status_code >= 400:
        try:
            code = response.json().get("error", "unknown")
        except ValueError:
            code = "unknown"
        raise BotRefused(response.status_code, code)

    try:
        return response.json()
    except ValueError as e:
        raise BotUnreachable("reponse illisible") from e


async def health() -> dict[str, Any]:
    """Etat du bot. Sert au bandeau d'alerte et a la page d'accueil."""
    return await _call("GET", "/api/health")


async def list_guilds() -> list[dict[str, Any]]:
    """Serveurs ou le bot est present."""
    return await _call("GET", "/api/guilds")


async def get_guild(guild_id: str) -> dict[str, Any]:
    return await _call("GET", f"/api/guilds/{guild_id}")


async def guild_options(guild_id: str) -> dict[str, Any]:
    """Salons et roles proposes dans les listes deroulantes."""
    return await _call("GET", f"/api/guilds/{guild_id}/options")


async def patch_guild(guild_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await _call("PATCH", f"/api/guilds/{guild_id}", json=payload)
