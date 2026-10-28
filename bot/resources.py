"""
Resources — Résolution des salons/rôles/catégories gérés par le bot.
======================================================================
Les salons et rôles sont créés avec un nom traduit selon la langue du
serveur (voir locales/*.json → "names"). Chercher un salon/rôle par son
nom casse dès que ce nom change de langue (ou qu'un modérateur le
renomme) : on mémorise donc l'ID de la ressource créée dans
guild_settings et on ne s'appuie sur le nom que pour la première
création ou pour retrouver une ressource créée avant ce système
(migration silencieuse, avec repli sur le nom français historique).
"""

from __future__ import annotations

import discord

from guild_settings import get_resource_id, set_resource_id, get_custom_name
from i18n import t


def resource_name(guild_id: int | None, key: str) -> str:
    """Nom attendu d'une ressource gérée par le bot."""
    if guild_id is not None:
        custom = get_custom_name(guild_id, key)
        if custom:
            return custom
    return t(guild_id, f"names.{key}")


def get_role(guild: discord.Guild, key: str) -> discord.Role | None:
    """Retrouve un rôle géré par le bot (par ID mémorisé, sinon par nom traduit). Ne crée rien."""
    role_id = get_resource_id(guild.id, key)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return role
    found = discord.utils.get(guild.roles, name=resource_name(guild.id, key))
    if found is not None:
        # Retrouve par son nom : on retient son ID pour que la fois
        # suivante soit une lecture de dictionnaire et non un parcours
        # de tout le serveur.
        set_resource_id(guild.id, key, found.id)
    return found


def get_text_channel(guild: discord.Guild, key: str) -> discord.TextChannel | None:
    channel_id = get_resource_id(guild.id, key)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
    found = discord.utils.get(guild.text_channels, name=resource_name(guild.id, key))
    if found is not None:
        # Retrouve par son nom : on retient son ID pour que la fois
        # suivante soit une lecture de dictionnaire et non un parcours
        # de tout le serveur.
        set_resource_id(guild.id, key, found.id)
    return found


def get_voice_channel(guild: discord.Guild, key: str) -> discord.VoiceChannel | None:
    channel_id = get_resource_id(guild.id, key)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.VoiceChannel):
            return channel
    found = discord.utils.get(guild.voice_channels, name=resource_name(guild.id, key))
    if found is not None:
        # Retrouve par son nom : on retient son ID pour que la fois
        # suivante soit une lecture de dictionnaire et non un parcours
        # de tout le serveur.
        set_resource_id(guild.id, key, found.id)
    return found


def get_category(guild: discord.Guild, key: str) -> discord.CategoryChannel | None:
    cat_id = get_resource_id(guild.id, key)
    if cat_id:
        cat = guild.get_channel(cat_id)
        if isinstance(cat, discord.CategoryChannel):
            return cat
    return discord.utils.get(guild.categories, name=resource_name(guild.id, key))


def is_staff(member: discord.Member) -> bool:
    """Vérifie si un membre a le rôle staff (par ID mémorisé, sinon par nom — courant ou historique français)."""
    role_id = get_resource_id(member.guild.id, "role_staff")
    if role_id and any(r.id == role_id for r in member.roles):
        return True

    from config import STAFF_ROLE_NAME

    names = {STAFF_ROLE_NAME, resource_name(member.guild.id, "role_staff")}
    return any(role.name in names for role in member.roles)
