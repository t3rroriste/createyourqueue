"""
Connexion avec Discord (OAuth2)
===============================
Le site ne demande jamais de mot de passe : la personne se connecte chez
Discord, qui renvoie un code, que le site échange contre un jeton. Ce jeton
sert uniquement à demander « qui es-tu ? » et « sur quels serveurs es-tu
admin ? », puis il reste en mémoire du site (voir sessions.py).

Permissions demandées (scopes) :
- identify : le pseudo et l'avatar, rien d'autre (pas l'adresse e-mail) ;
- guilds   : la liste des serveurs de la personne, pour savoir lesquels
             elle a le droit de configurer.
"""

import os

import httpx

API_BASE = "https://discord.com/api/v10"
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = f"{API_BASE}/oauth2/token"
SCOPES = "identify guilds"

# Bit « Gérer le serveur » dans les permissions Discord.
MANAGE_GUILD = 1 << 5


class OAuthError(Exception):
    """Discord a refusé la connexion (code expiré, secret faux...)."""


def client_id() -> str:
    return os.getenv("DISCORD_CLIENT_ID", "").strip()


def client_secret() -> str:
    return os.getenv("DISCORD_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    return os.getenv("DISCORD_REDIRECT_URI", "").strip()


def authorize_url(state: str) -> str:
    """Adresse de la page de connexion Discord."""
    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "prompt": "none",  # pas de réautorisation si c'est déjà fait
    }
    return f"{AUTHORIZE_URL}?{httpx.QueryParams(params)}"


def invite_url() -> str:
    """Lien « Inviter le bot » de la page d'accueil."""
    params = {
        "client_id": client_id(),
        "permissions": os.getenv("BOT_INVITE_PERMISSIONS", "8").strip() or "8",
        "scope": "bot applications.commands",
    }
    return f"{AUTHORIZE_URL}?{httpx.QueryParams(params)}"


async def exchange_code(code: str) -> str:
    """Échange le code renvoyé par Discord contre un jeton d'accès."""
    data = {
        "client_id": client_id(),
        "client_secret": client_secret(),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            TOKEN_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code != 200:
        raise OAuthError(f"échange du code refusé ({response.status_code})")
    token = response.json().get("access_token")
    if not token:
        raise OAuthError("réponse sans jeton")
    return token


async def _get(path: str, token: str):
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{API_BASE}{path}", headers={"Authorization": f"Bearer {token}"}
        )
    if response.status_code != 200:
        raise OAuthError(f"{path} : réponse {response.status_code}")
    return response.json()


async def fetch_user(token: str) -> dict:
    user = await _get("/users/@me", token)
    return {
        "id": str(user["id"]),
        "name": user.get("global_name") or user.get("username", "?"),
        "avatar": (
            f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png"
            if user.get("avatar") else None
        ),
    }


async def fetch_managed_guilds(token: str) -> list[dict]:
    """Serveurs où la personne est propriétaire ou a « Gérer le serveur ».

    C'est ce qui décide qui peut configurer quoi : quelqu'un qui n'a pas
    cette permission sur Discord ne verra pas le serveur dans le tableau
    de bord, et ne pourra rien y modifier.
    """
    guilds = await _get("/users/@me/guilds", token)
    managed = []
    for guild in guilds:
        permissions = int(guild.get("permissions", 0))
        if guild.get("owner") or permissions & MANAGE_GUILD:
            managed.append({
                "id": str(guild["id"]),
                "name": guild.get("name", "?"),
                "icon": (
                    f"https://cdn.discordapp.com/icons/{guild['id']}/{guild['icon']}.png"
                    if guild.get("icon") else None
                ),
            })
    managed.sort(key=lambda g: g["name"].lower())
    return managed
