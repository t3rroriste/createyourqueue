"""
Serveur web — démarré avec le bot, arrêté avec lui.
=====================================================
`aiohttp` est déjà installé (dépendance de discord.py) et le bot tourne déjà
sur une boucle asyncio : le serveur s'y greffe sans process ni dépendance en
plus, et partage donc la mémoire de `guild_settings`.

Le dashboard ne démarre que si DASHBOARD_ENABLED vaut 1 **et** que
DASHBOARD_SECRET est correctement renseignée. Un échec ici n'empêche jamais le
bot de fonctionner : il se contente de le signaler et les commandes Discord
continuent comme avant.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from aiohttp import web

from web import auth, routes_queue, routes_server
from web.keys import BOT, GUILD_ID, MEMBER, SESSION
from web.render import message_page

log = logging.getLogger("bot.web")

STATIC_DIR = Path(__file__).parent / "static"


# Fenêtre glissante par IP. `rate_limit.py` protège les appels SORTANTS vers
# Discord ; il n'a rien à voir avec les requêtes entrantes.
RATE_WINDOW = 60.0
RATE_MAX = 90
_hits: dict[str, list[float]] = {}


def _enabled() -> bool:
    return os.getenv("DASHBOARD_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def base_url() -> str:
    """Adresse publique du dashboard, sans barre oblique finale."""
    return os.getenv("DASHBOARD_BASE_URL", "").strip().rstrip("/")


def is_running(bot) -> bool:
    return getattr(bot, "dashboard_runner", None) is not None


# ---------------------------------------------------------------------------
# Middlewares
# ---------------------------------------------------------------------------

@web.middleware
async def rate_limit_middleware(request: web.Request, handler):
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
        request.remote or "?"
    )
    now = time.time()
    recent = [stamp for stamp in _hits.get(ip, []) if now - stamp < RATE_WINDOW]
    if len(recent) >= RATE_MAX:
        _hits[ip] = recent
        raise web.HTTPTooManyRequests(text="Trop de requêtes.")
    recent.append(now)
    _hits[ip] = recent
    # Les IP inactives ne doivent pas s'accumuler indéfiniment en mémoire.
    if len(_hits) > 4096:
        for old, stamps in list(_hits.items()):
            if not stamps or now - stamps[-1] > RATE_WINDOW:
                del _hits[old]
    return await handler(request)


@web.middleware
async def security_headers_middleware(request: web.Request, handler):
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    # Tout vient du dashboard lui-même : aucun script en ligne, aucun CDN.
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'",
    )
    if isinstance(response, web.HTTPException):
        raise response
    return response


@web.middleware
async def session_middleware(request: web.Request, handler):
    """Garde des pages `/g/...` : session valide, serveur cohérent, droits
    d'administration **relus sur Discord**, et jeton CSRF sur chaque POST."""
    if not request.path.startswith("/g/"):
        return await handler(request)

    bot = request.app[BOT]
    session = auth.read_session(request.cookies.get(auth.COOKIE_NAME))
    if session is None:
        return web.Response(
            text=message_page(None, "dashboard.err_session"),
            content_type="text/html",
            status=401,
        )

    try:
        guild_id = int(request.match_info["gid"])
    except (KeyError, TypeError, ValueError):
        raise web.HTTPNotFound()

    # Le cookie est signé pour UN serveur : il ne donne pas accès à un autre.
    if int(session["g"]) != guild_id:
        return web.Response(
            text=message_page(None, "dashboard.err_session"),
            content_type="text/html",
            status=403,
        )

    member = auth.require_admin(bot, guild_id, int(session["u"]))
    if member is None:
        return web.Response(
            text=message_page(guild_id, "dashboard.err_perms"),
            content_type="text/html",
            status=403,
        )

    if request.method == "POST":
        form = await request.post()
        if not auth.check_csrf(session, form.get("csrf")):
            return web.Response(
                text=message_page(guild_id, "dashboard.err_csrf"),
                content_type="text/html",
                status=403,
            )

    request[SESSION] = session
    request[GUILD_ID] = guild_id
    request[MEMBER] = member
    return await handler(request)


# ---------------------------------------------------------------------------
# Routes communes
# ---------------------------------------------------------------------------

async def healthz(request: web.Request) -> web.Response:
    bot = request.app[BOT]
    ready = bot.is_ready()
    return web.json_response({"ok": ready}, status=200 if ready else 503)


async def enter(request: web.Request) -> web.Response:
    """`/d/<token>` — le lien envoyé par /dashboard. Consommé au premier clic."""
    result = auth.consume_link(request.match_info.get("token", ""))
    if result is None:
        return web.Response(
            text=message_page(None, "dashboard.err_link"),
            content_type="text/html",
            status=403,
        )
    guild_id, user_id = result

    # Le lien prouve qui vous êtes ; il ne remplace pas la vérification des
    # droits, qui a pu changer entre la commande et le clic.
    if auth.require_admin(request.app[BOT], guild_id, user_id) is None:
        return web.Response(
            text=message_page(guild_id, "dashboard.err_perms"),
            content_type="text/html",
            status=403,
        )

    response = web.HTTPFound(f"/g/{guild_id}/queue")
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.make_session(guild_id, user_id),
        max_age=auth.SESSION_TTL,
        httponly=True,
        secure=base_url().startswith("https://"),
        samesite="Lax",
        path="/",
    )
    return response


async def logout(request: web.Request) -> web.Response:
    response = web.HTTPFound("/")
    response.del_cookie(auth.COOKIE_NAME, path="/")
    return response


async def home(request: web.Request) -> web.Response:
    """Rien à voir sans passer par Discord : la page d'accueil le dit, et
    n'expose aucune information sur les serveurs."""
    return web.Response(
        text=message_page(None, "dashboard.home_desc", title_key="dashboard.home_title"),
        content_type="text/html",
    )


# ---------------------------------------------------------------------------
# Démarrage / arrêt
# ---------------------------------------------------------------------------

def build_app(bot) -> web.Application:
    app = web.Application(middlewares=[
        rate_limit_middleware,
        security_headers_middleware,
        session_middleware,
    ])
    app[BOT] = bot
    app.router.add_get("/", home)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/d/{token}", enter)
    app.router.add_post("/logout", logout)
    routes_queue.add_routes(app)
    routes_server.add_routes(app)
    if STATIC_DIR.is_dir():
        app.router.add_static("/static/", path=str(STATIC_DIR), name="static")
    return app


async def start(bot) -> None:
    """Lance le serveur. Ne lève jamais : le bot doit démarrer quoi qu'il arrive."""
    if not _enabled():
        log.info("Dashboard désactivé (DASHBOARD_ENABLED absent ou à 0).")
        return
    try:
        auth.secret()
    except auth.SecretMissing as e:
        log.error(f"Dashboard non démarré : {e}")
        return
    if not base_url():
        log.error("Dashboard non démarré : DASHBOARD_BASE_URL manquante (lien de /dashboard).")
        return

    port = int(os.getenv("PORT") or os.getenv("DASHBOARD_PORT") or "8080")
    runner = web.AppRunner(build_app(bot), access_log=None)
    try:
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
    except OSError as e:
        log.error(f"Dashboard non démarré (port {port} indisponible) : {e}")
        await runner.cleanup()
        return

    bot.dashboard_runner = runner
    log.info(f"Dashboard en écoute sur le port {port} — {base_url()}")


async def stop(bot) -> None:
    runner = getattr(bot, "dashboard_runner", None)
    if runner is None:
        return
    bot.dashboard_runner = None
    try:
        await runner.cleanup()
        log.info("Dashboard arrêté.")
    except Exception as e:
        log.error(f"Arrêt du dashboard : {e}")
