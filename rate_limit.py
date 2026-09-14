"""
Rate limit — Protection des appels Discord en masse.
======================================================
discord.py gère déjà les rate limits standards (buckets HTTP, retry_after) :
un appel isolé n'a normalement rien à craindre. Le vrai risque vient des
BOUCLES qui envoient beaucoup de requêtes d'affilée sur le même salon ou
serveur — retirer un rôle à des centaines de membres, kicker plusieurs
comptes en même temps pendant un raid, MP toute une liste d'inscrits... Ça
peut saturer un bucket, et pour les actions sensibles (kick/ban), déclencher
la détection d'abus de Discord indépendamment du rate limit habituel.

Deux outils :
- `throttled_each` : applique une action à une liste d'éléments avec un
  court délai entre chaque appel ; un échec sur un élément n'interrompt pas
  le reste du lot, et une 429 imprévue déclenche une pause avant de reprendre.
- `guarded_call` : limite le nombre d'appels concurrents d'un même type
  d'action risquée (kick, ban) sur un même serveur — utile quand plusieurs
  événements (arrivées de membres pendant un raid) déclenchent l'action en
  parallèle plutôt qu'en boucle séquentielle.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

import discord

log = logging.getLogger("bot.rate_limit")

T = TypeVar("T")

# Un sémaphore par (serveur, action) : jamais plus de `concurrency` appels de
# cette action en parallèle sur ce serveur, même si plusieurs événements
# Discord la déclenchent en même temps (ex: plusieurs join simultanés).
_semaphores: dict[tuple[int, str], asyncio.Semaphore] = {}


def _semaphore(guild_id: int, action: str, concurrency: int) -> asyncio.Semaphore:
    key = (guild_id, action)
    sem = _semaphores.get(key)
    if sem is None:
        sem = asyncio.Semaphore(concurrency)
        _semaphores[key] = sem
    return sem


async def guarded_call(coro: Awaitable, *, guild_id: int, action: str, concurrency: int = 2):
    """Exécute un appel Discord risqué sous un sémaphore par (serveur, action).

    À utiliser pour des actions ponctuelles déclenchées par des événements
    indépendants (ex: kick anti-raid dans `on_member_join`) plutôt que dans
    une boucle — `throttled_each` est fait pour les boucles."""
    sem = _semaphore(guild_id, action, concurrency)
    async with sem:
        return await coro


async def throttled_each(
    items: list[T],
    action: Callable[[T], Awaitable],
    *,
    delay: float = 0.3,
    label: str = "lot",
    on_error: Callable[[T, Exception], None] | None = None,
) -> tuple[int, int]:
    """Applique `action(item)` à chaque élément avec un court délai entre
    chaque appel. Un échec sur un élément n'interrompt pas les suivants ; une
    429 imprévue (rare, discord.py absorbe déjà la plupart) déclenche une
    pause supplémentaire avant de reprendre. Retourne (succès, échecs)."""
    ok = failed = 0
    for item in items:
        try:
            await action(item)
            ok += 1
        except discord.HTTPException as e:
            failed += 1
            if e.status == 429:
                wait = getattr(e, "retry_after", None) or 2.0
                log.warning(f"Rate limit atteint pendant '{label}', pause {wait:.1f}s")
                await asyncio.sleep(wait)
            if on_error:
                on_error(item, e)
            else:
                log.error(f"Erreur sur un élément de '{label}' : {e}")
        except Exception as e:
            failed += 1
            if on_error:
                on_error(item, e)
            else:
                log.error(f"Erreur sur un élément de '{label}' : {e}")
        if delay:
            await asyncio.sleep(delay)
    return ok, failed
