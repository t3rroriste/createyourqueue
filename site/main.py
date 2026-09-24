"""
Site CreateYourQueue
====================
Le bouton « Inviter le bot », et le tableau de bord ou un admin regle son
serveur depuis un navigateur.

    Navigateur --> Site (ici) --HTTP + cle--> Bot --> data/*.json

Le site ne touche jamais aux fichiers du bot : il appelle l'API de
cogs/dashboard_api.py (voir bot_api.py). Il ne stocke rien non plus, sinon
un cookie de session signe qui retient qui tu es et quels serveurs tu geres.

Qui peut modifier quoi : tu te connectes avec Discord, et seuls les serveurs
ou tu es proprietaire ou as « Gerer le serveur » te sont proposes. Cette
verification est refaite a chaque requete, pas seulement a la connexion.
"""

import logging
import secrets
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import bot_api
import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("site")

app = FastAPI(title="CreateYourQueue", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    max_age=settings.SESSION_MAX_AGE,
    https_only=settings.SESSION_HTTPS_ONLY,
    same_site="lax",
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Noms affiches des fonctions et des salons/roles. Les cles viennent de
# guild_settings.FEATURE_DEFAULTS et de dashboard_api.EDITABLE_RESOURCES :
# si le bot en ajoute une, elle apparait ici avec sa cle brute tant qu'on
# ne l'a pas nommee, plutot que de disparaitre.
FEATURE_LABELS = {
    "leaderboard": ("Classement", "Classement des joueurs et commande /stats."),
    "mvp":         ("Match et MVP", "Salon de match, capitaines, vote MVP et MMR."),
    "clans":       ("Clans", "Un salon et un role par clan, plus les ClanWar."),
    "clan_notice": ("Annonces de clan", "Les demandes d'adhesion sont annoncees dans le salon du clan."),
    "status":      ("Panneau d'etat", "Un message permanent qui affiche l'etat du bot."),
    "password":    ("Queues protegees", "Les queues demandent un mot de passe pour entrer."),
}

RESOURCE_LABELS = {
    "channel_queue_command":      ("Salon des commandes", "text",  "La ou les joueurs lancent /queue."),
    "channel_queue_announcement": ("Salon des annonces", "text",   "Les queues qui demarrent y sont annoncees."),
    "channel_queue_resultat":     ("Salon des resultats", "text",  "Les scores de fin de partie."),
    "channel_queue_classement":   ("Salon du classement", "text",  "Le tableau du classement, tenu a jour."),
    "voice_queue_waiting":        ("Vocal d'attente", "voice",     "Les joueurs y patientent avant le lancement."),
    "role_staff":                 ("Role staff", "role",           "Peut lancer et arreter les queues."),
    "role_queue_notif":           ("Role notification", "role",    "Mentionne quand une queue demarre."),
}

RESOURCE_ORDER = list(RESOURCE_LABELS)


# ----------------------------------------------------------------------
# Session
# ----------------------------------------------------------------------
def current_user(request: Request) -> dict[str, Any] | None:
    return request.session.get("user")


def managed_guild_ids(request: Request) -> set[str]:
    """Serveurs ou la personne connectee a le droit de reglage.

    Releve a la connexion. On ne rappelle pas Discord a chaque clic : ses
    limites de debit sont vite atteintes, et perdre le droit au milieu
    d'une session reste rattrape par le bot, qui refuse tout ce qu'il ne
    reconnait pas.
    """
    return set(request.session.get("guild_ids", []))


def _render(request: Request, template: str, **context: Any) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "user": current_user(request),
            "invite_url": settings.INVITE_URL,
            "support_invite": settings.SUPPORT_INVITE,
            **context,
        },
    )


def _oops(request: Request, title: str, detail: str, status: int = 500) -> HTMLResponse:
    response = _render(request, "error.html", title=title, detail=detail)
    response.status_code = status
    return response


# ----------------------------------------------------------------------
# Pages publiques
# ----------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Accueil. L'etat du bot y est affiche s'il repond, sans bloquer la
    page s'il est eteint."""
    status = None
    try:
        status = await bot_api.health()
    except (bot_api.BotUnreachable, bot_api.BotRefused):
        pass
    return _render(request, "index.html", status=status)


@app.get("/invite")
async def invite() -> RedirectResponse:
    return RedirectResponse(settings.INVITE_URL, status_code=302)


# ----------------------------------------------------------------------
# Connexion Discord
# ----------------------------------------------------------------------
@app.get("/login")
async def login(request: Request) -> RedirectResponse:
    # L'etat est verifie au retour : il empeche qu'on te fasse valider une
    # connexion que tu n'as pas demandee.
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    url = (
        f"{settings.DISCORD_API}/oauth2/authorize"
        f"?client_id={settings.CLIENT_ID}"
        f"&redirect_uri={httpx.URL(settings.REDIRECT_URI)}"
        f"&response_type=code&scope={settings.OAUTH_SCOPES.replace(' ', '%20')}"
        f"&state={state}&prompt=none"
    )
    return RedirectResponse(url, status_code=302)


@app.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=302)


@app.get("/callback", response_class=HTMLResponse)
async def callback(request: Request, code: str = "", state: str = "") -> Any:
    expected = request.session.pop("oauth_state", None)
    if not code or not state or state != expected:
        return _oops(
            request, "Connexion interrompue",
            "La demande de connexion n'a pas abouti. Reessaie depuis l'accueil.",
            status=400,
        )

    try:
        token = await _exchange_code(code)
        user, guild_ids = await _fetch_identity(token)
    except httpx.HTTPError as e:
        log.warning(f"Discord injoignable pendant la connexion : {e}")
        return _oops(
            request, "Discord ne repond pas",
            "Impossible de verifier ton compte pour le moment. Reessaie dans un instant.",
            status=502,
        )
    except PermissionError:
        return _oops(
            request, "Connexion refusee",
            "Discord a refuse la connexion. Verifie que tu autorises bien l'application.",
            status=403,
        )

    request.session["user"] = user
    request.session["guild_ids"] = sorted(guild_ids)
    log.info(f"Connexion : {user['name']} ({user['id']}), {len(guild_ids)} serveur(s) gere(s)")
    return RedirectResponse("/dashboard", status_code=302)


async def _exchange_code(code: str) -> str:
    """Code a usage unique contre jeton d'acces. Le jeton sert une fois,
    juste apres, et n'est jamais mis en session."""
    data = {
        "client_id": settings.CLIENT_ID,
        "client_secret": settings.CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.DISCORD_API}/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code != 200:
        raise PermissionError(response.text)
    return response.json()["access_token"]


async def _fetch_identity(token: str) -> tuple[dict[str, Any], set[str]]:
    """Qui tu es, et quels serveurs tu peux regler."""
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=10) as client:
        me = await client.get(f"{settings.DISCORD_API}/users/@me", headers=headers)
        guilds = await client.get(f"{settings.DISCORD_API}/users/@me/guilds", headers=headers)

    if me.status_code != 200 or guilds.status_code != 200:
        raise PermissionError("Discord a refuse la lecture du compte")

    account = me.json()
    avatar = None
    if account.get("avatar"):
        avatar = (
            f"https://cdn.discordapp.com/avatars/{account['id']}"
            f"/{account['avatar']}.png?size=64"
        )

    user = {
        "id": account["id"],
        "name": account.get("global_name") or account["username"],
        "avatar": avatar,
    }

    allowed = {
        str(guild["id"])
        for guild in guilds.json()
        if guild.get("owner")
        or int(guild.get("permissions", 0)) & settings.PERMISSION_MANAGE_GUILD
    }
    return user, allowed


# ----------------------------------------------------------------------
# Tableau de bord
# ----------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> Any:
    if not current_user(request):
        return RedirectResponse("/login", status_code=302)

    try:
        present = await bot_api.list_guilds()
    except bot_api.BotUnreachable:
        return _oops(
            request, "Le bot ne repond pas",
            "Il est peut-etre en train de redemarrer. Reessaie dans une minute.",
            status=503,
        )
    except bot_api.BotRefused as e:
        log.error(f"API du bot refusee ({e.code}) : verifie BOT_API_KEY")
        return _oops(
            request, "Liaison avec le bot impossible",
            "Le site n'arrive pas a s'authentifier aupres du bot. Previens un administrateur.",
            status=502,
        )

    mine = managed_guild_ids(request)
    guilds = sorted(
        (guild for guild in present if str(guild["id"]) in mine),
        key=lambda g: g["name"].lower(),
    )
    return _render(request, "guilds.html", guilds=guilds, total=len(present))


@app.get("/dashboard/{guild_id}", response_class=HTMLResponse)
async def guild_page(request: Request, guild_id: str) -> Any:
    if not current_user(request):
        return RedirectResponse("/login", status_code=302)
    if guild_id not in managed_guild_ids(request):
        return _oops(
            request, "Serveur non autorise",
            "Tu n'as pas « Gerer le serveur » sur celui-ci, ou le bot n'y est pas.",
            status=403,
        )

    try:
        guild = await bot_api.get_guild(guild_id)
        options = await bot_api.guild_options(guild_id)
    except bot_api.BotUnreachable:
        return _oops(
            request, "Le bot ne repond pas",
            "Impossible de lire la configuration de ce serveur pour le moment.",
            status=503,
        )
    except bot_api.BotRefused as e:
        if e.status == 404:
            return _oops(
                request, "Serveur introuvable",
                "Le bot n'est plus sur ce serveur. Invite-le a nouveau pour le regler.",
                status=404,
            )
        raise

    return _render(
        request, "guild.html",
        guild=guild,
        options=options,
        feature_labels=FEATURE_LABELS,
        resource_labels=RESOURCE_LABELS,
        resource_order=RESOURCE_ORDER,
    )


@app.patch("/dashboard/{guild_id}")
async def save_guild(request: Request, guild_id: str) -> JSONResponse:
    """Enregistrement depuis la page de reglages.

    Le site ne valide rien lui-meme : il verifie qui tu es, puis laisse le
    bot accepter ou refuser. Une seule regle vaut, et c'est la sienne.
    """
    if not current_user(request):
        return JSONResponse({"error": "not_logged_in"}, status_code=401)
    if guild_id not in managed_guild_ids(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    try:
        updated = await bot_api.patch_guild(guild_id, payload)
    except bot_api.BotUnreachable:
        return JSONResponse({"error": "bot_unreachable"}, status_code=503)
    except bot_api.BotRefused as e:
        return JSONResponse({"error": e.code}, status_code=e.status)

    log.info(f"Reglages enregistres : {updated['name']} ({guild_id})")
    return JSONResponse(updated)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.SITE_HOST, port=settings.SITE_PORT)
