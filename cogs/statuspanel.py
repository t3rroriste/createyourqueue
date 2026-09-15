"""
Cog : Status Panel
==================
Commande : /status <activer> [salon] — administrateur du serveur

Un message unique qu'on laisse dans un salon et que le bot tient à jour en
continu, dans l'esprit des panneaux de statut de serveur FiveM : un en-tête,
l'état en une ligne, puis les chiffres en liste.

- `/status true` publie le panneau dans le salon où l'on tape la commande.
- `/status true #salon` le publie dans ce salon-là. Relancer la commande vers
  un autre salon le déménage : il n'en existe jamais deux.
- `/status false` le retire.

Plus de panneau de réglage : un interrupteur et un salon tiennent dans les
deux paramètres de la commande.

Permanent
---------
Tant que la fonction est allumée, le panneau reste en place :
- il est actualisé toutes les REFRESH_SECONDS secondes ;
- s'il est supprimé (à la main, par un /clear, une purge…), il est republié
  aussitôt dans le même salon ;
- les purges du bot (fin de queue, /autoclean, /clear) l'épargnent — voir
  `guild_settings.is_status_panel_message`.
Une erreur sur un serveur n'interrompt plus la boucle : une seule exception
non rattrapée suffisait à figer tous les panneaux jusqu'au redémarrage.

Détecter le HORS LIGNE
----------------------
Un bot mort ne peut pas modifier un message : afficher « HORS LIGNE » depuis
le bot lui-même est donc impossible dans le cas général. Trois mécanismes se
complètent :

1. Arrêt volontaire (Ctrl+C, arrêt du service, redéploiement) → le bot bascule
   le panneau en HORS LIGNE **avant** de se déconnecter. C'est le cas courant.
2. Coupure brutale (crash, panne de courant, kill -9) → personne ne peut plus
   écrire. Le panneau affiche donc une échéance « prochaine mise à jour
   <t:…:R> » rendue en direct par Discord : dès qu'elle est dépassée, le
   panneau est visiblement périmé, et le pied de page le dit explicitement.
3. Au redémarrage, le panneau est immédiatement repassé en LIGNE.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Collection

import discord
from discord import app_commands
from discord.ext import commands, tasks

import embeds
import resources
from guild_settings import (
    get_status_panel, set_status_panel, clear_status_panel,
    get_features, set_features,
    set_resource_id,
)
from i18n import t
from text_safety import NO_PINGS

log = logging.getLogger("bot.statuspanel")

# 30 s : loin des limites Discord (5 modifications / 5 s par salon) tout en
# gardant un panneau qui paraît vivant.
REFRESH_SECONDS = 30

# Issue d'une mise à jour du panneau.
EDITED = "edited"     # message modifié
MISSING = "missing"   # plus de message : à republier
FAILED = "failed"     # erreur passagère : le message existe, on réessaiera


def _format_uptime(seconds: float, guild_id: int | None) -> str:
    seconds = int(max(0, seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = []
    if days:
        parts.append(t(guild_id, "status.unit_days", n=days))
    if hours or days:
        parts.append(t(guild_id, "status.unit_hours", n=hours))
    parts.append(t(guild_id, "status.unit_minutes", n=minutes))
    return " ".join(parts)


class StatusPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.started_at = time.time()
        # Une seule opération à la fois sur les panneaux : la boucle et la
        # détection de suppression republieraient sinon chacune le sien.
        self._lock = asyncio.Lock()
        # Serveurs où la publication échoue déjà : l'erreur n'est journalisée
        # qu'une fois, pas à chaque tour de boucle.
        self._failing: set[int] = set()

    async def cog_load(self) -> None:
        # Démarrée ici et non dans on_ready : un rechargement du cog ne
        # redéclenche pas on_ready, et le panneau restait figé.
        self.refresh.start()

    def cog_unload(self) -> None:
        self.refresh.cancel()

    # ------------------------------------------------------------------
    # Construction du panneau
    # ------------------------------------------------------------------
    @staticmethod
    def _quality(latency_ms: int, guild_id: int | None) -> str:
        """Qualité de la liaison avec Discord, en clair.

        « 240 ms » ne dit rien à qui ne connaît pas les ordres de grandeur :
        on traduit la mesure en excellent / correct / lent."""
        if latency_ms <= 150:
            return t(guild_id, "status.ping_good")
        if latency_ms <= 400:
            return t(guild_id, "status.ping_ok")
        return t(guild_id, "status.ping_slow")

    def build_content(self, guild_id: int | None, *, online: bool) -> str:
        """Le gros titre, au-dessus du cadre.

        Un titre d'embed est limité en taille d'affichage ; un titre de niveau
        2 en contenu de message se voit de loin, ce qui est tout l'intérêt
        d'un panneau qu'on laisse en haut d'un salon."""
        return "## " + t(guild_id, "status.head_online" if online else "status.head_offline")

    def _bullet(self, guild_id: int | None, label_key: str, value: str) -> str:
        return t(guild_id, "status.bullet", label=t(guild_id, label_key), value=value)

    def build_embed(self, guild: discord.Guild | None, *, online: bool) -> discord.Embed:
        """Le cadre : l'état en une ligne, puis les chiffres en liste — pas en
        grille de champs. Une colonne se lit d'un trait sur téléphone, une
        grille de six champs y déborde."""
        guild_id = guild.id if guild is not None else None
        now = int(time.time())
        name = self.bot.user.display_name if self.bot.user else "Bot"

        state_key = "status.state_online" if online else "status.state_offline"
        lines = [
            t(guild_id, "status.line_state", bot=name, state=t(guild_id, state_key)),
            "",
        ]

        if online:
            latency = self.bot.latency
            # latency vaut nan tant que le premier heartbeat n'est pas revenu
            latency_ms = round(latency * 1000) if latency == latency else 0
            members = sum(g.member_count or 0 for g in self.bot.guilds)
            queue_cog = self.bot.get_cog("QueueConfig")
            active = 0
            if queue_cog is not None:
                active = sum(1 for s in queue_cog.active_sessions.values() if not s.ended)

            lines += [
                self._bullet(guild_id, "status.field_uptime",
                             f"**{_format_uptime(time.time() - self.started_at, guild_id)}**"),
                self._bullet(guild_id, "status.field_latency",
                             f"`{latency_ms} ms` · {self._quality(latency_ms, guild_id)}"),
                self._bullet(guild_id, "status.field_servers", f"`{len(self.bot.guilds)}`"),
                self._bullet(guild_id, "status.field_members",
                             "`%s`" % f"{members:,}".replace(",", " ")),
                self._bullet(guild_id, "status.field_queues", f"`{active}`"),
                "",
                # Rendu par Discord en direct : dès que l'échéance est dépassée
                # sans nouvelle mise à jour, le panneau est visiblement périmé.
                t(guild_id, "status.next_line", next=now + REFRESH_SECONDS),
            ]
        else:
            lines += [
                self._bullet(guild_id, "status.field_stopped", f"<t:{now}:R>"),
                "",
                t(guild_id, "status.offline_desc"),
            ]

        embed = embeds.base(
            guild_id,
            description="\n".join(lines),
            kind="success" if online else "error",
            footer=t(guild_id, "status.footer_online", seconds=REFRESH_SECONDS)
            if online else t(guild_id, "status.footer_offline"),
            timestamp=True,
        )
        # La bannière du serveur donne au panneau l'allure d'une affiche, sans
        # rien demander à personne. Absente, l'embed reste complet.
        if guild is not None and guild.banner is not None:
            embed.set_image(url=guild.banner.url)
        return embed

    # ------------------------------------------------------------------
    # Publier, mettre à jour, retirer
    # Toutes ces méthodes s'appellent sous self._lock.
    # ------------------------------------------------------------------
    async def put_up(self, guild: discord.Guild) -> bool:
        """Publie le panneau dans le salon désigné. False si c'est impossible."""
        channel = resources.get_text_channel(guild, "channel_status")
        if channel is None:
            return False
        try:
            message = await channel.send(
                content=self.build_content(guild.id, online=True),
                embed=self.build_embed(guild, online=True),
                allowed_mentions=NO_PINGS,
            )
        except discord.HTTPException as e:
            if guild.id not in self._failing:
                log.error(f"[{guild.name}] Publication du panneau de statut impossible : {e}")
            self._failing.add(guild.id)
            return False
        self._failing.discard(guild.id)
        set_status_panel(guild.id, channel.id, message.id)
        log.info(f"[{guild.name}] Panneau de statut publié dans #{channel.name}.")
        return True

    async def take_down(self, guild: discord.Guild) -> None:
        """Retire le message. Réservé à `/status false` et au déménagement :
        un panneau figé qu'on croit à jour est pire que pas de panneau."""
        panel = get_status_panel(guild.id)
        if not panel:
            return
        # Référence effacée AVANT la suppression : l'événement de suppression
        # qui suit ne doit pas prendre ce retrait pour un accident à réparer.
        clear_status_panel(guild.id)
        channel = guild.get_channel(panel.get("channel_id") or 0)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.get_partial_message(panel["message_id"]).delete()
            except discord.HTTPException:
                pass

    async def _edit_panel(self, guild: discord.Guild, *, online: bool) -> str:
        panel = get_status_panel(guild.id)
        if not panel:
            return MISSING
        channel = guild.get_channel(panel.get("channel_id") or 0)
        if not isinstance(channel, discord.TextChannel):
            # Serveur momentanément indisponible ou salon supprimé : on garde
            # la référence plutôt que de republier un doublon au retour.
            return FAILED
        try:
            await channel.get_partial_message(panel["message_id"]).edit(
                content=self.build_content(guild.id, online=online),
                embed=self.build_embed(guild, online=online),
                allowed_mentions=NO_PINGS,
            )
            return EDITED
        except discord.NotFound:
            clear_status_panel(guild.id)
            log.info(f"[{guild.name}] Panneau de statut disparu — republication.")
            return MISSING
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Mise à jour du panneau de statut impossible : {e}")
            return FAILED

    async def ensure_panel(self, guild: discord.Guild) -> bool:
        """Le panneau à jour, republié s'il a disparu. False s'il n'est pas en place."""
        result = await self._edit_panel(guild, online=True)
        if result == EDITED:
            return True
        if result == FAILED:
            return False
        return await self.put_up(guild)

    @tasks.loop(seconds=REFRESH_SECONDS)
    async def refresh(self) -> None:
        for guild in list(self.bot.guilds):
            if not get_features(guild.id)["status"]:
                continue
            try:
                async with self._lock:
                    await self.ensure_panel(guild)
            except Exception:
                log.exception(f"[{guild.name}] Actualisation du panneau de statut impossible")

    @refresh.before_loop
    async def before_refresh(self) -> None:
        # Le premier tour part dès que le bot est prêt : c'est lui qui repasse
        # le panneau en LIGNE au redémarrage, ou le republie s'il a disparu
        # pendant l'arrêt.
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        await self._on_deleted(payload.guild_id, {payload.message_id})

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        await self._on_deleted(payload.guild_id, payload.message_ids)

    async def _on_deleted(self, guild_id: int | None, message_ids: Collection[int]) -> None:
        """Panneau supprimé alors que la fonction est allumée : il revient tout de suite."""
        if guild_id is None:
            return
        panel = get_status_panel(guild_id)
        if not panel or panel.get("message_id") not in message_ids:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        async with self._lock:
            # Revérifié sous le verrou : /status a pu le déménager entre-temps.
            panel = get_status_panel(guild_id)
            if not panel or panel.get("message_id") not in message_ids:
                return
            clear_status_panel(guild_id)
            if get_features(guild_id)["status"]:
                log.info(f"[{guild.name}] Panneau de statut supprimé — republication.")
                await self.put_up(guild)

    async def mark_offline(self) -> None:
        """Appelé juste avant la déconnexion (voir bot.py). C'est ce qui rend
        l'arrêt volontaire visible dans le panneau."""
        self.refresh.cancel()
        for guild in self.bot.guilds:
            if not get_status_panel(guild.id):
                continue
            try:
                await self._edit_panel(guild, online=False)
            except Exception:
                log.exception(f"[{guild.name}] Bascule du panneau de statut en hors ligne impossible")
        log.info("Panneau(x) de statut basculé(s) en HORS LIGNE.")

    # ------------------------------------------------------------------
    # Commande
    # ------------------------------------------------------------------
    @app_commands.command(
        name="status",
        description="Panneau d'état du bot, permanent et tenu à jour en continu.",
    )
    @app_commands.describe(
        activer="true : afficher le panneau · false : le retirer",
        salon="Salon du panneau (par défaut : le salon où tu tapes la commande)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(
        self,
        interaction: discord.Interaction,
        activer: bool,
        salon: discord.TextChannel | None = None,
    ) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                t(gid, "common.text_channel_only"), ephemeral=True)
            return

        if not activer:
            await interaction.response.defer(ephemeral=True)
            async with self._lock:
                set_features(gid, status=False)
                await self.take_down(guild)
            await interaction.followup.send(t(gid, "status.disabled_done"), ephemeral=True)
            return

        channel = salon or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(t(gid, "status.bad_channel"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        async with self._lock:
            panel = get_status_panel(gid)
            if panel and panel.get("channel_id") != channel.id:
                # Déménagement : l'ancien panneau part avant que le nouveau arrive.
                await self.take_down(guild)
            set_resource_id(gid, "channel_status", channel.id)
            set_features(gid, status=True)
            # Même salon et message déjà là : une simple mise à jour suffit.
            posted = await self.ensure_panel(guild) or get_status_panel(gid) is not None
            if not posted:
                set_features(gid, status=False)

        if not posted:
            await interaction.followup.send(t(gid, "status.post_failed"), ephemeral=True)
            return
        reply = t(gid, "status.enabled_in", channel=channel.mention, seconds=REFRESH_SECONDS)
        # Le panneau est fait pour être vu de tous : si le salon est masqué à
        # @everyone, on le signale.
        if not channel.permissions_for(guild.default_role).view_channel:
            reply += "\n" + t(gid, "status.not_public", channel=channel.mention)
        await interaction.followup.send(reply, ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    t(interaction.guild_id, "wiz.admin_only"), ephemeral=True)
        else:
            log.exception("[STATUS] Erreur non gérée", exc_info=error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatusPanel(bot))
    log.info("Cog StatusPanel chargé")
