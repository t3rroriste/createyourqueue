"""
Reglages du site
================
Tout se lit dans le `.env` pose a cote (voir .env.example). Aucun identifiant
n'est ecrit ici : le fichier est fait pour etre lu, pas pour etre rempli.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _need(name: str) -> str:
    """Variable obligatoire. On refuse de demarrer sans, plutot que de
    tomber en panne a la premiere connexion."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} manque dans le .env du site. Copie .env.example en .env "
            f"et remplis-le (voir README.md)."
        )
    return value


# --- Application Discord (discord.com/developers) ---------------------
CLIENT_ID     = _need("DISCORD_CLIENT_ID")
CLIENT_SECRET = _need("DISCORD_CLIENT_SECRET")
REDIRECT_URI  = _need("OAUTH_REDIRECT_URI")

# --- API du bot (voir cogs/dashboard_api.py) --------------------------
BOT_API_URL     = _need("BOT_API_URL")
BOT_API_KEY     = _need("BOT_API_KEY")
BOT_API_TIMEOUT = float(os.getenv("BOT_API_TIMEOUT", "10"))

# --- Session ----------------------------------------------------------
# Signe le cookie de connexion. Le changer deconnecte tout le monde.
SESSION_SECRET = _need("SESSION_SECRET")
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", str(7 * 24 * 3600)))

# Cookie en HTTPS seulement. Mets 0 en developpement local sans certificat.
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "1") not in ("0", "false", "")

# --- Serveur ----------------------------------------------------------
SITE_HOST = os.getenv("SITE_HOST", "127.0.0.1")
SITE_PORT = int(os.getenv("SITE_PORT", "8000"))

# Invitation du bot. Les permissions couvrent ce que le bot fait vraiment :
# gerer salons et roles, envoyer et epingler, reagir, deplacer en vocal.
INVITE_PERMISSIONS = os.getenv("INVITE_PERMISSIONS", "1099780063312")
SUPPORT_INVITE = os.getenv("SUPPORT_INVITE", "").strip()

INVITE_URL = (
    f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}"
    f"&permissions={INVITE_PERMISSIONS}&scope=bot%20applications.commands"
)

# --- Discord OAuth2 ---------------------------------------------------
DISCORD_API = "https://discord.com/api/v10"
OAUTH_SCOPES = "identify guilds"

# Droit « Gerer le serveur ». Seuls le proprietaire et ceux qui l'ont
# voient un serveur dans le tableau de bord.
PERMISSION_MANAGE_GUILD = 1 << 5
