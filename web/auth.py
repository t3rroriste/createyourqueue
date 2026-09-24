"""
Web auth — Se connecter au dashboard depuis Discord.
======================================================
Pas d'OAuth2 : quand un membre tape `/dashboard`, le bot a déjà l'objet
`Member` sous la main et sait donc s'il est administrateur. Inutile de
redemander à Discord ce qu'on sait déjà. La commande signe un lien valable
cinq minutes, à usage unique, envoyé en éphémère ; le clic ouvre une session.

Deux jetons, la même signature HMAC-SHA256 :
- le **lien** (`/d/<token>`), très court et consommé au premier usage ;
- le **cookie de session**, deux heures, qui porte aussi le jeton CSRF.

Un cookie valide ne suffit jamais à agir : les permissions sont revérifiées
sur le serveur Discord à CHAQUE requête (voir `require_admin`). Un
administrateur rétrogradé perd l'accès dans la seconde, sans attendre
l'expiration du cookie.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import secrets
import time
from hashlib import sha256
from typing import Any

log = logging.getLogger("bot.web.auth")

LINK_TTL = 300              # 5 minutes : le temps de cliquer, pas plus.
SESSION_TTL = 2 * 3600      # 2 heures.
COOKIE_NAME = "cyq_session"

# Nonces des liens déjà utilisés. Un lien ne sert qu'une fois : s'il traîne
# dans un historique de navigateur ou un presse-papier, il ne rouvre rien.
_used_links: dict[str, float] = {}


class SecretMissing(RuntimeError):
    """DASHBOARD_SECRET absente ou trop courte."""


def secret() -> bytes:
    """La clé de signature. Sans elle, le dashboard refuse de démarrer : une
    clé par défaut laisserait n'importe qui fabriquer un cookie d'admin."""
    raw = os.getenv("DASHBOARD_SECRET", "").strip()
    if len(raw) < 32:
        raise SecretMissing(
            "DASHBOARD_SECRET manquante ou trop courte (32 caractères minimum). "
            "Génère-la avec : python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return raw.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def _sign(body: str) -> str:
    return _b64e(hmac.new(secret(), body.encode("ascii"), sha256).digest())


def dumps(payload: dict[str, Any]) -> str:
    """Encode et signe un petit dictionnaire."""
    body = _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def loads(token: str | None) -> dict[str, Any] | None:
    """Vérifie la signature et l'expiration. Retourne None au moindre doute."""
    if not token or token.count(".") != 1:
        return None
    body, _, sig = token.partition(".")
    if not body or not sig:
        return None
    try:
        expected = _sign(body)
    except SecretMissing:
        return None
    # compare_digest : la comparaison ne doit pas fuir la signature attendue
    # par le temps qu'elle met à échouer.
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        if float(payload.get("exp", 0)) < time.time():
            return None
    except (TypeError, ValueError):
        return None
    return payload


# ---------------------------------------------------------------------------
# Lien de connexion envoyé par /dashboard
# ---------------------------------------------------------------------------

def make_link(guild_id: int, user_id: int) -> str:
    """Jeton du lien `/d/<token>`, à usage unique."""
    return dumps({
        "g": int(guild_id),
        "u": int(user_id),
        "n": secrets.token_urlsafe(9),
        "exp": time.time() + LINK_TTL,
    })


def consume_link(token: str) -> tuple[int, int] | None:
    """Valide le lien et le brûle. Retourne (guild_id, user_id) ou None."""
    payload = loads(token)
    if payload is None:
        return None
    nonce = str(payload.get("n", ""))
    if not nonce:
        return None

    now = time.time()
    # Les nonces expirés ne servent plus à rien : le jeton qui les porte est
    # de toute façon refusé par `loads`.
    for used, expiry in list(_used_links.items()):
        if expiry < now:
            del _used_links[used]

    if nonce in _used_links:
        return None
    _used_links[nonce] = float(payload.get("exp", now))
    try:
        return int(payload["g"]), int(payload["u"])
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Cookie de session
# ---------------------------------------------------------------------------

def make_session(guild_id: int, user_id: int) -> str:
    """Cookie signé. Le jeton CSRF voyage dedans : il est donc lui aussi
    protégé par la signature, et n'a pas besoin d'un stockage serveur."""
    return dumps({
        "g": int(guild_id),
        "u": int(user_id),
        "csrf": secrets.token_urlsafe(24),
        "exp": time.time() + SESSION_TTL,
    })


def read_session(raw_cookie: str | None) -> dict[str, Any] | None:
    """Session valide, ou None. Ne dit RIEN des permissions : celles-ci se
    vérifient sur le serveur Discord, à chaque requête."""
    payload = loads(raw_cookie)
    if payload is None:
        return None
    try:
        int(payload["g"]), int(payload["u"])
    except (KeyError, TypeError, ValueError):
        return None
    if not payload.get("csrf"):
        return None
    return payload


def check_csrf(session: dict[str, Any], submitted: str | None) -> bool:
    """Un formulaire web, contrairement à une interaction Discord, peut être
    déclenché depuis un autre site. Chaque POST porte donc ce jeton."""
    if not submitted:
        return False
    return hmac.compare_digest(str(session.get("csrf", "")), str(submitted))


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

def is_dashboard_admin(member) -> bool:
    """Même règle que sur Discord (cogs/queue_config.py) : administrateur du
    serveur, ou porteur du rôle staff. Un seul endroit décide, les deux
    interfaces donnent exactement les mêmes droits."""
    import resources

    if member is None:
        return False
    try:
        return bool(member.guild_permissions.administrator) or resources.is_staff(member)
    except AttributeError:
        return False


def require_admin(bot, guild_id: int, user_id: int):
    """Le membre, s'il est toujours là et toujours autorisé. Sinon None.

    Relu à chaque requête, jamais mémorisé dans le cookie : quitter le
    serveur ou perdre ses droits coupe l'accès immédiatement."""
    guild = bot.get_guild(int(guild_id))
    if guild is None:
        return None
    member = guild.get_member(int(user_id))
    if member is None:
        return None
    return member if is_dashboard_admin(member) else None
