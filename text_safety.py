"""
Text safety — Neutralisation du texte saisi par les utilisateurs.
==================================================================
Tout ce qu'un membre tape (nom de queue, nom d'équipe, titre de panneau...)
peut se retrouver dans le CONTENU d'un message envoyé par le bot. Un embed ne
déclenche jamais de notification, mais le contenu d'un message, lui, si — et
le bot a souvent la permission de mentionner tout le monde.

Deux protections complémentaires :
- `sanitize()` casse `@everyone` / `@here` en insérant une espace de largeur
  nulle, et borne la longueur avant d'atteindre les limites de Discord.
- `NO_PINGS` est à passer en `allowed_mentions` sur tout envoi contenant du
  texte utilisateur : même si une mention passait au travers, Discord ne
  notifiera personne.
"""

from __future__ import annotations

import discord

# Espace de largeur nulle : invisible à la lecture, mais suffit à empêcher
# Discord de reconnaître la mention.
_ZWSP = "​"

NO_PINGS = discord.AllowedMentions.none()

# Pour les messages qui doivent notifier une personne précise (l'organisateur)
# sans jamais pouvoir déclencher un @everyone/@here ou un ping de rôle.
USERS_ONLY = discord.AllowedMentions(everyone=False, roles=False, users=True)


def sanitize(text: str | None, limit: int = 200) -> str:
    """Rend un texte utilisateur sûr à insérer dans un message, et le tronque."""
    if not text:
        return ""
    cleaned = text.replace("@everyone", f"@{_ZWSP}everyone").replace("@here", f"@{_ZWSP}here")
    return cleaned[:limit]
