"""
Site CreateYourQueue
====================
Deux entrées : inviter le bot, et le tableau de bord.

Le tableau de bord ne sait rien tout seul : il demande tout au bot, qui
tourne sur l'autre serveur (voir bot_api.py et cogs/dashboard_api.py).

Qui a le droit de voir quoi : la personne se connecte avec Discord, et le
site ne lui montre que les serveurs où Discord dit qu'elle est
propriétaire ou « Gérer le serveur ». La liste de ces serveurs est envoyée
au bot à chaque appel : les chiffres et le journal sont calculés pour
eux seuls. La vérification est refaite à chaque page et à chaque
enregistrement, jamais seulement à l'affichage du menu.

Lancement en local pour tester :
    uvicorn main:app --reload --port 8000
Lancement sur le VPS : voir README.md.
"""

import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import bot_api
import discord_oauth
import sessions

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("site")

app = FastAPI(title="CreateYourQueue", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32),
    session_cookie="cyq_session",
    https_only=os.getenv("DISCORD_REDIRECT_URI", "").startswith("https://"),
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Fonctions activables, dans l'ordre d'affichage. Les clés sont celles de
# FEATURE_DEFAULTS (guild_settings.py) : ne pas en inventer ici.
FEATURE_LABELS = {
    "leaderboard": ("Classement", "Classement du serveur et commande /stats"),
    "mvp": ("Match, capitaines et MMR", "Salon de match, choix des capitaines, vote MVP, niveau des joueurs"),
    "clans": ("Clans", "Clans permanents, salon et rôle par clan, ClanWar"),
    "clan_notice": ("Annoncer les demandes de clan", "Les demandes d'adhésion sont annoncées dans le salon du clan"),
    "status": ("Panneau d'état", "Message permanent qui affiche l'état de la queue"),
    "password": ("Queues sous mot de passe", "Il faut un mot de passe pour rejoindre une queue"),
}

# Salons et rôles désignables, mêmes clés que EDITABLE_RESOURCES côté bot.
# (libellé, type attendu, à quoi ça sert)
CHANNEL_FIELDS = {
    "channel_queue_command": ("Salon des commandes", "text",
                              "Là où les joueurs lancent et rejoignent une queue."),
    "channel_queue_announcement": ("Salon des annonces", "text",
                                   "Le bot y annonce les queues qui démarrent."),
    "channel_queue_resultat": ("Salon des résultats", "text",
                               "Le score de chaque partie terminée."),
    "channel_queue_classement": ("Salon du classement", "text",
                                 "Le classement du serveur, tenu à jour tout seul."),
    "voice_queue_waiting": ("Salon vocal d'attente", "voice",
                            "Le vocal où les joueurs patientent avant le lancement."),
}

ROLE_FIELDS = {
    "role_staff": ("Rôle staff", "role",
                   "Peut encadrer une partie et corriger un résultat."),
    "role_queue_notif": ("Rôle notifié", "role",
                         "Mentionné au lancement d'une queue, pour rameuter."),
    "role_connexion": ("Rôle connexion", "role",
                       "Donne l'accès au vocal d'attente pendant les inscriptions."),
    "role_mvp_week": ("Rôle MVP de la semaine", "role",
                      "Attribué chaque dimanche au joueur le plus victorieux."),
}

RESOURCE_LABELS = {**CHANNEL_FIELDS, **ROLE_FIELDS}

# La configuration d'un serveur est découpée : une page par sujet, avec son
# propre bouton Enregistrer. Tout sur une seule page devenait un mur de
# réglages où personne ne retrouvait rien.
SECTIONS = {
    "general": ("Général", "La langue du bot sur ce serveur"),
    "salons": ("Salons", "Où le bot écrit et fait patienter"),
    "roles": ("Rôles", "Qui encadre et qui est prévenu"),
    "fonctions": ("Fonctions", "Ce que le bot propose aux joueurs"),
}


# ---------------------------------------------------------------------
# Mise en forme
# ---------------------------------------------------------------------
def count(value) -> str:
    """1284 -> « 1 284 ». Espace fine insécable, comme en français."""
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def clock(timestamp) -> str:
    """Heure d'une ligne du journal, à la seconde."""
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%H:%M:%S")
    except (TypeError, ValueError, OSError):
        return "—"


def uptime(seconds) -> str:
    """47 jours et des poussières -> « 47j 12h 34m »."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "—"
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}j {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


templates.env.filters["count"] = count
templates.env.filters["clock"] = clock
templates.env.filters["uptime"] = uptime

# Nom de domaine affiché en haut à droite, déduit de l'adresse de retour
# Discord : un réglage de moins à tenir à jour.
PUBLIC_HOST = urlparse(os.getenv("DISCORD_REDIRECT_URI", "")).hostname or ""


# ---------------------------------------------------------------------
# Session et droits
# ---------------------------------------------------------------------
def _session(request: Request) -> dict | None:
    """Données de la personne connectée, ou None."""
    return sessions.get(request.session.get("sid"))


def _managed_guild(data: dict, guild_id: str) -> dict | None:
    """Le serveur demandé, s'il fait partie de ceux qu'elle administre."""
    return next((g for g in data["guilds"] if g["id"] == guild_id), None)


def _page(request: Request, name: str, status: int = 200, **context) -> HTMLResponse:
    data = _session(request)
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={"user": data["user"] if data else None,
                 "is_owner": bool(data and data.get("is_owner")),
                 "host": PUBLIC_HOST, "nav": None, "online": None, **context},
        status_code=status,
    )


def _error(request: Request, message: str, status: int = 400) -> HTMLResponse:
    return _page(request, "error.html", status=status, message=message)


async def _server_rows(data: dict) -> tuple[list[dict], str | None]:
    """Les serveurs de la personne connectée, croisés avec ceux du bot."""
    present: dict[str, dict] = {}
    problem = None
    try:
        present = {g["id"]: g for g in await bot_api.guilds()}
    except bot_api.BotApiError as e:
        problem = str(e)
        log.warning(f"Liste des serveurs indisponible : {e}")

    rows = []
    for guild in data["guilds"]:
        known = present.get(guild["id"], {})
        rows.append({**guild,
                     "bot_present": guild["id"] in present,
                     "members": known.get("members"),
                     "joined": known.get("joined"),
                     "available": known.get("available", False),
                     "setup_complete": known.get("setup_complete", False)})
    # Les serveurs où le bot est déjà là d'abord : c'est ce qu'on vient faire.
    rows.sort(key=lambda row: (not row["bot_present"], row["name"].lower()))
    return rows, problem


# ---------------------------------------------------------------------
# Page d'accueil
# ---------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _page(request, "index.html", invite_url=discord_oauth.invite_url())


# ---------------------------------------------------------------------
# Connexion Discord
# ---------------------------------------------------------------------
@app.get("/login")
async def login(request: Request):
    if not discord_oauth.client_id() or not discord_oauth.client_secret():
        return _error(
            request,
            "Le site n'est pas encore configuré : DISCORD_CLIENT_ID ou "
            "DISCORD_CLIENT_SECRET manque dans le fichier .env.",
            status=500,
        )
    # L'état est un mot de passe à usage unique : Discord nous le renvoie,
    # et s'il ne correspond pas, la connexion vient d'ailleurs.
    state = secrets.token_urlsafe(16)
    request.session["state"] = state
    return RedirectResponse(discord_oauth.authorize_url(state), status_code=303)


@app.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    expected = request.session.pop("state", None)
    if error:
        return _error(request, "Connexion annulée.", status=400)
    if not code or not state or state != expected:
        return _error(
            request,
            "Lien de connexion invalide ou expiré. Reviens à l'accueil et reclique sur Connexion.",
            status=400,
        )
    try:
        token = await discord_oauth.exchange_code(code)
        user = await discord_oauth.fetch_user(token)
        guilds = await discord_oauth.fetch_managed_guilds(token)
    except discord_oauth.OAuthError as e:
        log.warning(f"Connexion refusée : {e}")
        return _error(request, "Discord a refusé la connexion. Réessaie dans un instant.", status=502)

    # Demandé une seule fois, au bot : le journal des commandes n'est visible
    # que par le propriétaire du bot, pas par les admins des serveurs.
    owner = await bot_api.is_owner(user["id"])
    request.session["sid"] = sessions.create({"user": user, "guilds": guilds, "is_owner": owner})
    log.info(f"Connexion de {user['name']} ({len(guilds)} serveurs administrés"
             f"{', propriétaire' if owner else ''})")
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    sessions.drop(request.session.get("sid"))
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def overview(request: Request):
    """Les chiffres, les dernières commandes, et les serveurs."""
    data = _session(request)
    if data is None:
        return RedirectResponse("/login", status_code=303)

    rows, problem = await _server_rows(data)
    mine = [row["id"] for row in rows if row["bot_present"]]
    stats, journal = None, []
    if problem is None:
        try:
            stats = await bot_api.stats(mine)
            # Le journal n'existe que pour le propriétaire du bot.
            if data.get("is_owner"):
                journal = await bot_api.commands(data["user"]["id"], limit=12)
        except bot_api.BotApiError as e:
            problem = str(e)
            log.warning(f"Chiffres indisponibles : {e}")

    return _page(request, "overview.html", nav="dashboard", online=problem is None,
                 guilds=rows, stats=stats, journal=journal, problem=problem,
                 invite_url=discord_oauth.invite_url())


@app.get("/dashboard/serveurs", response_class=HTMLResponse)
async def servers_page(request: Request):
    data = _session(request)
    if data is None:
        return RedirectResponse("/login", status_code=303)
    rows, problem = await _server_rows(data)
    return _page(request, "servers.html", nav="servers", online=problem is None,
                 guilds=rows, problem=problem, invite_url=discord_oauth.invite_url())


@app.get("/dashboard/journal", response_class=HTMLResponse)
async def journal_page(request: Request):
    data = _session(request)
    if data is None:
        return RedirectResponse("/login", status_code=303)
    # Réservé au propriétaire du bot. Le bot refuse déjà la demande, mais
    # autant le dire clairement plutôt que d'afficher une page vide.
    if not data.get("is_owner"):
        return _error(request, "Le journal des commandes est réservé au propriétaire du bot.",
                      status=403)

    journal, problem = [], None
    try:
        journal = await bot_api.commands(data["user"]["id"], limit=100)
    except bot_api.BotApiError as e:
        problem = str(e)

    return _page(request, "journal.html", nav="journal", online=problem is None,
                 journal=journal, problem=problem)


@app.get("/dashboard/{guild_id}", response_class=HTMLResponse)
async def guild_home(request: Request, guild_id: str):
    """L'ancienne adresse mène à la première catégorie."""
    return RedirectResponse(f"/dashboard/{guild_id}/general", status_code=303)


@app.get("/dashboard/{guild_id}/{section}", response_class=HTMLResponse)
async def guild_section(request: Request, guild_id: str, section: str, saved: int = 0):
    data = _session(request)
    if data is None:
        return RedirectResponse("/login", status_code=303)
    if _managed_guild(data, guild_id) is None:
        return _error(request, "Tu n'es pas administrateur de ce serveur.", status=403)
    if section not in SECTIONS:
        return _error(request, "Cette page de configuration n'existe pas.", status=404)

    try:
        info = await bot_api.guild(guild_id)
        # Les listes de salons et de rôles ne servent qu'à ces deux pages :
        # ailleurs, c'est un aller-retour de plus pour rien.
        options = await bot_api.options(guild_id) if section in ("salons", "roles") else None
    except bot_api.BotApiError as e:
        return _error(request, f"Configuration indisponible : {e}.", status=502)

    return _page(request, f"guild_{section}.html", nav="servers", online=True,
                 guild=info, options=options, section=section, sections=SECTIONS,
                 saved=bool(saved), features=FEATURE_LABELS,
                 channels=CHANNEL_FIELDS, roles=ROLE_FIELDS)


@app.post("/dashboard/{guild_id}/{section}")
async def guild_save(request: Request, guild_id: str, section: str):
    data = _session(request)
    if data is None:
        return RedirectResponse("/login", status_code=303)
    # Revérifié ici : sans ça, quelqu'un pourrait envoyer le formulaire
    # d'un serveur qu'il n'administre pas sans jamais ouvrir la page.
    if _managed_guild(data, guild_id) is None:
        return _error(request, "Tu n'es pas administrateur de ce serveur.", status=403)
    if section not in SECTIONS:
        return _error(request, "Cette page de configuration n'existe pas.", status=404)

    form = await request.form()
    # Chaque page n'envoie que ce qu'elle affiche : enregistrer les salons ne
    # doit pas remettre à zéro ce qui se règle sur une autre page.
    if section == "general":
        payload = {"language": form.get("language")}
    elif section == "salons":
        payload = {"resources": {key: (form.get(f"resource_{key}") or None) for key in CHANNEL_FIELDS}}
    elif section == "roles":
        payload = {"resources": {key: (form.get(f"resource_{key}") or None) for key in ROLE_FIELDS}}
    else:
        # Une case décochée n'est pas envoyée par le navigateur : on parcourt
        # nos clés à nous, sinon décocher ne changerait jamais rien.
        payload = {"features": {key: form.get(f"feature_{key}") is not None for key in FEATURE_LABELS}}

    try:
        await bot_api.patch(guild_id, payload)
    except bot_api.BotApiError as e:
        return _error(request, f"Enregistrement impossible : {e}.", status=502)

    log.info(f"{data['user']['name']} a modifié {section} sur le serveur {guild_id}")
    return RedirectResponse(f"/dashboard/{guild_id}/{section}?saved=1", status_code=303)
