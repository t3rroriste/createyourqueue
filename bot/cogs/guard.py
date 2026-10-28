"""
Cog : Guard
===========
Protection des noms de salons créés par le bot.

Le bot retrouve ses salons par identifiant mémorisé, donc un renommage ne
casse rien techniquement — mais il casse tout le reste : les guides, les
messages d'aide et le panneau d'accueil citent les salons par leur nom, et
un membre qui lit « publie dans **queue-annonce** » ne trouve plus rien si
le salon s'appelle désormais autrement.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

import embeds
import resources
from guild_settings import get_resource_id
from i18n import t

log = logging.getLogger("bot.guard")

# Salons créés par /setup dont le nom est protégé.
PROTECTED_KEYS = [
    "category_main",
    "channel_queue_command",
    "channel_queue_announcement",
    "channel_queue_resultat",
    "channel_queue_classement",
    "channel_team_request",
    "voice_queue_waiting",
]


def protected_key(guild: discord.Guild, channel_id: int) -> str | None:
    """Clé de ressource d'un salon protégé, ou None s'il n'appartient pas au bot."""
    for key in PROTECTED_KEYS:
        if get_resource_id(guild.id, key) == channel_id:
            return key
    return None


class Guard(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._repaired = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Réaligne les noms sur la langue du serveur au démarrage."""
        if self._repaired:
            return
        self._repaired = True
        from retranslate import repair_guild
        for guild in self.bot.guilds:
            try:
                await repair_guild(self.bot, guild)
            except Exception as e:
                log.error(f"Réalignement des noms impossible sur {guild.name} : {e}")

    async def _find_renamer(self, channel) -> discord.Member | None:
        """Auteur du renommage, via le journal d'audit."""
        guild = channel.guild
        me = guild.me
        if me is None or not me.guild_permissions.view_audit_log:
            return None
        try:
            async for entry in guild.audit_logs(limit=8, action=discord.AuditLogAction.channel_update):
                if entry.target is not None and entry.target.id == channel.id:
                    return entry.user
        except discord.HTTPException as e:
            log.error(f"Journal d'audit illisible sur {guild.name} : {e}")
        return None

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after) -> None:
        if before.name == after.name:
            return
        guild = after.guild
        key = protected_key(guild, after.id)
        if key is None:
            return

        expected = resources.resource_name(guild.id, key)
        if not expected or after.name == expected:
            # Déjà au bon nom : c'est le bot qui vient de traduire le serveur.
            return

        author = await self._find_renamer(after)
        me = guild.me
        if author is not None and me is not None and author.id == me.id:
            return  # renommage effectué par le bot lui-même

        # `edit()` met à jour l'objet en mémoire : sans cette copie, after.name
        # vaudrait déjà le nom rétabli et le MP citerait deux fois le même nom.
        attempted = after.name

        try:
            await after.edit(name=expected, reason="Nom de salon protégé (CreateYourQueue)")
        except discord.Forbidden:
            log.warning(f"[{guild.name}] Nom de '{attempted}' non rétabli : permission manquante.")
            return
        except discord.HTTPException as e:
            # Typiquement un 429 : Discord limite à 2 renommages / 10 min / salon.
            log.warning(f"[{guild.name}] Nom de '{attempted}' non rétabli tout de suite : {e}")
            return

        log.info(
            f"[{guild.name}] '{attempted}' renommé par "
            f"{author if author else 'inconnu'} → nom rétabli en '{expected}'."
        )

        if author is None or author.bot:
            return
        try:
            await author.send(
                embed=embeds.base(
                    guild.id,
                    title=t(guild.id, "guard.dm_title"),
                    description=t(
                        guild.id, "guard.dm_desc",
                        server=guild.name, attempted=attempted, restored=expected,
                    ),
                    kind="error",
                    footer=t(guild.id, "guard.dm_footer"),
                ),
            )
        except discord.Forbidden:
            pass  # MP fermés : le nom est rétabli, c'est l'essentiel
        except discord.HTTPException as e:
            log.error(f"MP de protection non envoyé à {author} : {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Guard(bot))
    log.info("Cog Guard chargé")
