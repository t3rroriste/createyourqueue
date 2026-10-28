"""
Retranslate — Rebascule un serveur déjà configuré dans une nouvelle langue.
===========================================================================
Changer la langue avec /language ne suffisait pas : les salons et les rôles
avaient été CRÉÉS avec un nom traduit au moment du /setup, et ce nom restait
figé dans l'ancienne langue. Un serveur passé du français à l'anglais gardait
`🔱・queue-annonce` et le rôle `Organisateur`.

Ce module rejoue la traduction sur tout ce qui existe déjà :
"""

from __future__ import annotations

import logging

import discord

import resources
from guild_settings import get_custom_name
from i18n import LANGUAGES, get_lang, t, t_in
from rate_limit import throttled_each

log = logging.getLogger("bot.retranslate")

# Ressources créées par /setup, dans l'ordre où on les renomme.
RENAMABLE = [
    ("category_main", "category"),
    ("channel_queue_command", "text"),
    ("channel_queue_announcement", "text"),
    ("channel_queue_resultat", "text"),
    ("channel_queue_classement", "text"),
    ("channel_team_request", "text"),
    ("voice_queue_waiting", "voice"),
    ("role_staff", "role"),
    ("role_queue_notif", "role"),
    ("role_connexion", "role"),
    ("role_mvp_week", "role"),
]


def _resolve(guild: discord.Guild, key: str, kind: str):
    if kind == "text":
        return resources.get_text_channel(guild, key)
    if kind == "voice":
        return resources.get_voice_channel(guild, key)
    if kind == "category":
        return resources.get_category(guild, key)
    return resources.get_role(guild, key)


def _name_in(lang: str, key: str) -> str:
    """Nom qu'aurait la ressource dans une langue donnée, sans dépendre de la
    langue actuellement configurée pour le serveur."""
    return t_in(lang, f"names.{key}")


def plan_renames(guild: discord.Guild, old_lang: str, new_lang: str) -> list[tuple]:
    """(ressource, ancien nom, nouveau nom) pour tout ce qui doit être renommé."""
    plan = []
    for key, kind in RENAMABLE:
        resource = _resolve(guild, key, kind)
        if resource is None:
            continue
        if get_custom_name(guild.id, key):
            continue  # nom choisi à la main : la langue ne le concerne pas
        expected_old = _name_in(old_lang, key)
        wanted = _name_in(new_lang, key)
        if not wanted or resource.name == wanted:
            continue
        if resource.name != expected_old:
            log.info(
                f"[{guild.name}] '{resource.name}' laissé tel quel : renommé manuellement "
                f"(attendu '{expected_old}')."
            )
            continue
        plan.append((resource, resource.name, wanted))
    return plan


def _language_of_name(key: str, name: str) -> str | None:
    """Langue dans laquelle ce nom correspond à la ressource, ou None."""
    for lang in LANGUAGES:
        if t_in(lang, f"names.{key}") == name:
            return lang
    return None


async def repair_guild(bot, guild: discord.Guild) -> int:
    """Remet les ressources dans la langue ACTUELLE du serveur."""
    current = get_lang(guild.id)
    plan = []
    for key, kind in RENAMABLE:
        resource = _resolve(guild, key, kind)
        if resource is None:
            continue
        if get_custom_name(guild.id, key):
            continue  # nom choisi à la main : on n'y touche jamais
        wanted = _name_in(current, key)
        if not wanted or resource.name == wanted:
            continue
        if _language_of_name(key, resource.name) is None:
            continue  # nom personnalisé : on n'y touche pas
        plan.append((resource, resource.name, wanted))

    if not plan:
        return 0

    async def rename(entry):
        resource, _old, wanted = entry
        await resource.edit(name=wanted, reason=f"Alignement sur la langue du serveur ({current})")

    renamed, failed = await throttled_each(plan, rename, delay=0.4, label=f"réparation {guild.name}")
    log.info(
        f"[{guild.name}] Noms réalignés sur « {current} » : {renamed} corrigé(s), {failed} échec(s)."
    )
    if renamed:
        await refresh_panels(bot, guild)
    return renamed


async def refresh_panels(bot, guild: discord.Guild) -> int:
    """Réécrit les panneaux déjà publiés dans la nouvelle langue."""
    refreshed = 0

    status = bot.get_cog("StatusPanel")
    if status is not None and await status._edit_panel(guild, online=True):
        refreshed += 1

    classement = bot.get_cog("Classement")
    if classement is not None:
        try:
            await classement.update_classement_channel(guild)
            refreshed += 1
        except Exception as e:
            log.error(f"Classement non rafraîchi sur {guild.name} : {e}")

    return refreshed


async def retranslate_guild(bot, guild: discord.Guild, old_lang: str, new_lang: str) -> dict:
    """Rebascule tout le serveur dans `new_lang`. Retourne un compte-rendu."""
    if old_lang == new_lang:
        return {"renamed": 0, "failed": 0, "skipped": 0, "panels": 0}

    plan = plan_renames(guild, old_lang, new_lang)

    async def rename(entry):
        resource, _old, wanted = entry
        await resource.edit(name=wanted, reason=f"Changement de langue {old_lang} → {new_lang}")

    renamed, failed = await throttled_each(
        plan, rename, delay=0.4, label=f"retraduction {guild.name}"
    )
    panels = await refresh_panels(bot, guild)

    log.info(
        f"[{guild.name}] Retraduction {old_lang}→{new_lang} : "
        f"{renamed} renommé(s), {failed} échec(s), {panels} panneau(x) rafraîchi(s)."
    )
    return {"renamed": renamed, "failed": failed, "panels": panels}


def summary_text(guild_id: int, result: dict) -> str:
    """Compte-rendu lisible, dans la NOUVELLE langue."""
    lines = [t(guild_id, "language.retranslate_done", count=result["renamed"])]
    if result["panels"]:
        lines.append(t(guild_id, "language.retranslate_panels", count=result["panels"]))
    if result["failed"]:
        lines.append(t(guild_id, "language.retranslate_failed", count=result["failed"]))
    return "\n".join(lines)
