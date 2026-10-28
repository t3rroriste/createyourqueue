"""
Visibility — des messages permanents vus par tout le monde.
============================================================
Sans « Voir les anciens messages », Discord ne montre à un membre que les
messages envoyés pendant qu'il est connecté : il quitte le serveur, revient,
et le panneau a disparu pour lui. Les messages faits pour rester — le panneau
/status, l'embed Coming soon du bot temporaire — ont donc besoin de cette
permission pour @everyone dans leur salon.

`ensure_history` l'ajoute sans toucher au reste des permissions du salon.
"""

from __future__ import annotations

import discord

OK = "ok"          # @everyone voit déjà l'historique
FIXED = "fixed"    # la permission vient d'être ajoutée
HIDDEN = "hidden"  # @everyone ne voit pas du tout le salon : choix de l'admin, on n'y touche pas
DENIED = "denied"  # il fallait l'ajouter, mais le bot n'a pas le droit


async def ensure_history(channel: discord.abc.GuildChannel, *, reason: str) -> str:
    """Donne « Voir les anciens messages » à @everyone dans ce salon, si besoin."""
    everyone = channel.guild.default_role
    perms = channel.permissions_for(everyone)
    if not perms.view_channel:
        return HIDDEN
    if perms.read_message_history:
        return OK
    overwrite = channel.overwrites_for(everyone)
    overwrite.read_message_history = True
    try:
        await channel.set_permissions(everyone, overwrite=overwrite, reason=reason)
    except discord.HTTPException:
        return DENIED
    return FIXED
