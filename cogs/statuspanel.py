"""
Cog : Status Panel
==================
Commande : /status — panneau de réglage (administrateur du serveur)

Un message unique qu'on laisse dans un salon et que le bot tient à jour en
continu, dans l'esprit des panneaux de statut de serveur FiveM : un en-tête,
l'état en une ligne, puis les chiffres en liste.

`/status` n'écrit rien tout seul : il ouvre un panneau où l'on **désigne le
salon** et où l'on **allume ou éteint** l'affichage — même geste que les pages
de `/option`. Allumer publie le message, éteindre le supprime.

Pourquoi un message et pas un webhook
-------------------------------------
Un webhook ne saurait pas modifier son propre message sans qu'on stocke en
plus son identifiant, et il ne survit pas à la suppression du salon. Un
message du bot se modifie directement, se retrouve par son identifiant et
disparaît proprement quand on éteint le panneau.

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

import logging
import time

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

# 60 s : très loin des limites Discord (5 modifications / 5 s par salon) tout en
# gardant un panneau qui paraît vivant.
REFRESH_SECONDS = 60


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


class StatusSettings(discord.ui.View):
    """Le panneau de réglage : un salon, un interrupteur.

    Même lecture que les pages de `/option` — le mode retenu en gras, l'autre
    barré — pour qu'un administrateur n'ait pas à réapprendre une interface."""

    def __init__(self, cog: "StatusPanel", guild: discord.Guild):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.gid = guild.id
        self.sync()

    def is_on(self) -> bool:
        return bool(get_features(self.gid)["status"])

    def channel(self) -> discord.TextChannel | None:
        return resources.get_text_channel(self.guild, "channel_status")

    def sync(self) -> None:
        self.clear_items()
        select = discord.ui.ChannelSelect(
            placeholder=t(self.gid, "wiz.opt_pick_channel")[:150],
            channel_types=[discord.ChannelType.text], row=0,
        )
        select.callback = self._set_channel(select)
        self.add_item(select)
        self.add_item(self._toggle_button())

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    def _set_channel(self, select: discord.ui.ChannelSelect):
        async def callback(interaction: discord.Interaction) -> None:
            chosen = select.values[0]
            set_resource_id(self.gid, "channel_status", chosen.id)
            # Panneau déjà allumé : on le déménage plutôt que d'en laisser un
            # deuxième derrière, dont personne ne tiendrait la mise à jour.
            if self.is_on():
                await self.cog.take_down(self.guild)
                await self.cog.put_up(self.guild)
            await self.refresh(interaction)
        return callback

    def _toggle_button(self) -> discord.ui.Button:
        on = self.is_on()
        button = discord.ui.Button(
            label=t(self.gid, "wiz.opt_off_word" if on else "wiz.opt_on_word"),
            emoji="🔴" if on else "🟢",
            style=discord.ButtonStyle.danger if on else discord.ButtonStyle.success,
            row=1,
        )

        async def callback(interaction: discord.Interaction) -> None:
            if on:
                await self.cog.take_down(self.guild)
                set_features(self.gid, status=False)
                await self.refresh(interaction)
                return

            # On ne peut pas allumer un panneau sans dire où l'écrire : le
            # menu juste au-dessus est la seule réponse possible.
            channel = self.channel()
            if channel is None:
                await interaction.response.send_message(
                    t(self.gid, "status.need_channel"), ephemeral=True)
                return

            set_features(self.gid, status=True)
            posted = await self.cog.put_up(self.guild)
            if not posted:
                set_features(self.gid, status=False)
                await interaction.response.send_message(
                    t(self.gid, "status.post_failed"), ephemeral=True)
                return

            await self.refresh(interaction)
            # Le panneau est fait pour être vu de tous : si le salon est
            # masqué à @everyone, on le signale.
            if not channel.permissions_for(self.guild.default_role).view_channel:
                await interaction.followup.send(
                    t(self.gid, "status.not_public", channel=channel.mention), ephemeral=True)
        button.callback = callback
        return button

    def embed(self) -> discord.Embed:
        channel = self.channel()
        embed = embeds.base(
            self.gid,
            title=t(self.gid, "status.panel_title"),
            description="\n".join([
                t(self.gid, "wiz.opt_channel_line",
                  channel=channel.mention if channel is not None
                  else t(self.gid, "wiz.not_set")),
                "",
                embeds.toggle_line(self.gid, self.is_on()),
            ]),
            kind="brand",
        )
        embeds.brand(embed, self.guild)
        return embed


class StatusPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.started_at = time.time()
        self._loop_started = False

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
        """Le cadre : l'état en une ligne, la marche à suivre, puis les
        chiffres en liste — pas en grille de champs. Une colonne se lit d'un
        trait sur téléphone, une grille de six champs y déborde."""
        guild_id = guild.id if guild is not None else None
        now = int(time.time())
        name = self.bot.user.display_name if self.bot.user else "Bot"

        state_key = "status.state_online" if online else "status.state_offline"
        lines = [
            t(guild_id, "status.line_state", bot=name, state=t(guild_id, state_key)),
            "",
            # t(guild_id, "status.hint_online" if online else "status.hint_offline"),  # phrase d'aide retirée
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
        # Logo du bot en haut à droite désactivé
        # if self.bot.user is not None:
        #     embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        # La bannière du serveur donne au panneau l'allure d'une affiche, sans
        # rien demander à personne. Absente, l'embed reste complet.
        if guild is not None and guild.banner is not None:
            embed.set_image(url=guild.banner.url)
        return embed

    # ------------------------------------------------------------------
    # Publier, mettre à jour, retirer
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
            log.error(f"[{guild.name}] Publication du panneau de statut impossible : {e}")
            return False
        set_status_panel(guild.id, channel.id, message.id)
        log.info(f"[{guild.name}] Panneau de statut publié dans #{channel.name}.")
        return True

    async def take_down(self, guild: discord.Guild) -> None:
        """Éteindre, c'est retirer le message : un panneau figé qu'on croit à
        jour est pire que pas de panneau du tout."""
        panel = get_status_panel(guild.id)
        if not panel:
            return
        channel = guild.get_channel(panel.get("channel_id") or 0)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.get_partial_message(panel["message_id"]).delete()
            except discord.HTTPException:
                pass
        clear_status_panel(guild.id)

    async def _edit_panel(self, guild: discord.Guild, *, online: bool) -> bool:
        panel = get_status_panel(guild.id)
        if not panel:
            return False
        channel = guild.get_channel(panel.get("channel_id") or 0)
        if not isinstance(channel, discord.TextChannel):
            return False
        try:
            message = channel.get_partial_message(panel["message_id"])
            await message.edit(
                content=self.build_content(guild.id, online=online),
                embed=self.build_embed(guild, online=online),
                allowed_mentions=NO_PINGS,
            )
            return True
        except discord.NotFound:
            # Panneau supprimé à la main : on oublie la référence plutôt que
            # de réessayer indéfiniment à chaque cycle.
            clear_status_panel(guild.id)
            log.info(f"Panneau de statut disparu sur {guild.name} — référence effacée.")
        except discord.HTTPException as e:
            log.error(f"Mise à jour du panneau de statut impossible sur {guild.name} : {e}")
        return False

    @tasks.loop(seconds=REFRESH_SECONDS)
    async def refresh(self) -> None:
        for guild in self.bot.guilds:
            if get_status_panel(guild.id):
                await self._edit_panel(guild, online=True)

    @refresh.before_loop
    async def before_refresh(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Au (re)démarrage, le panneau repasse en LIGNE immédiatement.

        Si le message a disparu pendant l'arrêt — salon vidé, message effacé —
        mais que la fonction est restée allumée, on le republie : c'est ce qui
        rend l'affichage vraiment permanent."""
        if not self._loop_started:
            self._loop_started = True
            self.refresh.start()
        for guild in self.bot.guilds:
            if get_status_panel(guild.id):
                await self._edit_panel(guild, online=True)
            elif get_features(guild.id)["status"]:
                await self.put_up(guild)

    async def mark_offline(self) -> None:
        """Appelé juste avant la déconnexion (voir bot.py). C'est ce qui rend
        l'arrêt volontaire visible dans le panneau."""
        self.refresh.cancel()
        for guild in self.bot.guilds:
            if get_status_panel(guild.id):
                await self._edit_panel(guild, online=False)
        log.info("Panneau(x) de statut basculé(s) en HORS LIGNE.")

    # ------------------------------------------------------------------
    # Commande
    # ------------------------------------------------------------------
    @app_commands.command(
        name="status",
        description="Panneau d'état du bot : choisis le salon, active ou désactive.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        if interaction.guild is None:
            await interaction.response.send_message(
                t(gid, "common.text_channel_only"), ephemeral=True)
            return
        view = StatusSettings(self, interaction.guild)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

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
