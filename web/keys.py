"""
Clés typées d'aiohttp.
========================
`app["bot"]` et `request["member"]` fonctionnent, mais aiohttp met en garde :
deux extensions peuvent ranger des choses différentes sous la même chaîne.

Ce module existe séparément parce que `server` importe `routes_queue`, qui a
lui aussi besoin de ces clés : les mettre dans `server` créerait un import
circulaire.
"""

from __future__ import annotations

from aiohttp import web

# Application
BOT = web.AppKey("bot")

# Requête, renseignées par le middleware de session (voir web/server.py).
SESSION = web.RequestKey("session")
GUILD_ID = web.RequestKey("guild_id")
MEMBER = web.RequestKey("member")
