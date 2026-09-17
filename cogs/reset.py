"""
Cog : Reset
===========
Commande : /reset (administrateur uniquement)

Remet le serveur à zéro : supprime les salons et rôles créés par le bot,
efface toute la configuration, puis relance l'assistant de première
configuration.
"""

from __future__ import annotations

import logging
import secrets

import discord
from discord import app_commands
from discord.ext import commands

import custom_emojis
import embeds
from guild_settings import get_resource_id, reset_guild, set_setup_panel
from i18n import t
from rate_limit import throttled_each
from text_safety import NO_PINGS

log = logging.getLogger("bot.reset")

# Toutes les ressources que le bot a pu créer, avec leur type.
RESOURCE_KEYS = [
    ("channel_queue_command", "channel"),
    ("channel_queue_announcement", "channel"),
    ("channel_queue_resultat", "channel"),
    ("channel_queue_classement", "channel"),
    ("channel_team_request", "channel"),
    ("voice_queue_waiting", "channel"),
    ("category_main", "channel"),          # supprimée en dernier, une fois vidée
    ("role_staff", "role"),
    ("role_queue_notif", "role"),
    ("role_connexion", "role"),
    ("role_mvp_week", "role"),
]


# Alphabet sans caractères ambigus : ni O/0, ni I/1/l, ni 5/S — un code mal
# recopié ferait échouer la confirmation pour une mauvaise raison.
CAPTCHA_ALPHABET = "ABCDEFGHJKMNPQRTUVWXYZ2346789"
CAPTCHA_LENGTH = 5
MAX_ATTEMPTS = 3


def generate_code() -> str:
    """Code aléatoire à recopier. `secrets` plutôt que `random` : ce code garde
    une action destructive, il ne doit pas être prévisible."""
    return "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(CAPTCHA_LENGTH))


def collect_targets(guild: discord.Guild) -> list:
    """Ressources réellement présentes, retrouvées par ID mémorisé."""
    targets = []
    for key, kind in RESOURCE_KEYS:
        rid = get_resource_id(guild.id, key)
        if not rid:
            continue
        found = guild.get_channel(rid) if kind == "channel" else guild.get_role(rid)
        if found is not None:
            targets.append(found)
    return targets


def build_preview_embed(guild: discord.Guild, wipe_stats: bool, code: str = "") -> discord.Embed:
    gid = guild.id
    targets = collect_targets(guild)
    channels = [r for r in targets if not isinstance(r, discord.Role)]
    roles = [r for r in targets if isinstance(r, discord.Role)]

    embed = embeds.base(
        gid,
        title=t(gid, "reset.title"),
        description=t(gid, "reset.warning"),
        kind="error",
    )
    embeds.brand(embed, guild)
    embed.add_field(
        name=t(gid, "reset.field_channels", count=len(channels)),
        value=("\n".join(f"• {c.name}" for c in channels) or t(gid, "reset.nothing"))[:1000],
        inline=False,
    )
    embed.add_field(
        name=t(gid, "reset.field_roles", count=len(roles)),
        value=("\n".join(f"• {r.name}" for r in roles) or t(gid, "reset.nothing"))[:1000],
        inline=False,
    )
    embed.add_field(name=t(gid, "reset.field_data"), value=t(gid, "reset.data_list"), inline=False)
    embed.add_field(
        name=t(gid, "reset.field_stats"),
        value=t(gid, "reset.stats_on" if wipe_stats else "reset.stats_off"),
        inline=False,
    )
    if code:
        embed.add_field(
            name=t(gid, "reset.field_captcha"),
            value=t(gid, "reset.captcha_value", code=code),
            inline=False,
        )
    embed.set_footer(text=t(gid, "reset.footer"))
    return embed


class ConfirmModal(discord.ui.Modal):
    """Vérification par code aléatoire."""

    def __init__(self, view: "ResetView"):
        self.view = view
        gid = view.guild.id
        super().__init__(title=t(gid, "reset.modal_title"))
        self.field = discord.ui.TextInput(
            label=t(gid, "reset.modal_label", code=view.code),
            placeholder=view.code,
            min_length=CAPTCHA_LENGTH,
            max_length=CAPTCHA_LENGTH,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.field.value.strip().upper() == self.view.code:
            await self.view.execute(interaction)
            return
        await self.view.wrong_code(interaction)


class ResetView(discord.ui.View):
    def __init__(self, guild: discord.Guild, author_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.author_id = author_id
        self.wipe_stats = False
        self.code = generate_code()
        self.attempts = 0
        self._sync()

    def _sync(self) -> None:
        gid = self.guild.id
        self.confirm.label = t(gid, "reset.btn_confirm")
        self.stats.label = t(gid, "reset.btn_stats_on" if self.wipe_stats else "reset.btn_stats_off")
        self.stats.style = discord.ButtonStyle.danger if self.wipe_stats else discord.ButtonStyle.secondary
        self.cancel.label = t(gid, "reset.btn_cancel")
        self.cancel.emoji = custom_emojis.get("cross")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Réservé à son auteur, et la permission est revérifiée : elle a pu
        être retirée depuis l'ouverture du panneau."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(t(self.guild.id, "reset.not_yours"), ephemeral=True)
            return False
        if not (isinstance(interaction.user, discord.Member)
                and interaction.user.guild_permissions.administrator):
            await interaction.response.send_message(t(self.guild.id, "reset.admin_only"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger, emoji="⚠️", row=0)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(ConfirmModal(self))

    @discord.ui.button(label="Statistiques", style=discord.ButtonStyle.secondary, emoji="📊", row=0)
    async def stats(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.wipe_stats = not self.wipe_stats
        self._sync()
        await interaction.response.edit_message(
            embed=build_preview_embed(self.guild, self.wipe_stats, self.code), view=self
        )

    async def wrong_code(self, interaction: discord.Interaction) -> None:
        """Code refusé : on en génère un nouveau. Sans ça, réessayer en aveugle
        finirait par passer. Au bout de MAX_ATTEMPTS, le panneau se ferme."""
        self.attempts += 1
        gid = self.guild.id

        if self.attempts >= MAX_ATTEMPTS:
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(
                embed=embeds.base(
                    gid,
                    title=t(gid, "reset.locked_title"),
                    description=t(gid, "reset.locked_desc", max=MAX_ATTEMPTS),
                    kind="error",
                ),
                view=self,
            )
            log.warning(f"[{self.guild.name}] /reset abandonné : {MAX_ATTEMPTS} codes erronés.")
            return

        self.code = generate_code()
        embed = build_preview_embed(self.guild, self.wipe_stats, self.code)
        embed.insert_field_at(
            0,
            name=t(gid, "reset.field_wrong"),
            value=t(gid, "reset.wrong_desc", left=MAX_ATTEMPTS - self.attempts),
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.success, emoji="✖️", row=0)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=embeds.base(self.guild.id, description=t(self.guild.id, "reset.cancelled"), kind="success"),
            view=self,
        )

    # ------------------------------------------------------------------
    async def execute(self, interaction: discord.Interaction) -> None:
        guild = self.guild
        gid = guild.id
        await interaction.response.defer(ephemeral=True)

        # 1. Libérer la queue en cours, sinon ses panneaux pointeraient vers
        #    des salons supprimés.
        queue_cog = interaction.client.get_cog("QueueConfig")
        if queue_cog is not None:
            session = queue_cog.active_sessions.get(gid)
            if session is not None:
                try:
                    await queue_cog.teardown_session(guild, session, cancelled=True)
                except Exception as e:
                    log.error(f"[{guild.name}] Queue non libérée pendant le reset : {e}")

        # 2. Supprimer les ressources. La catégorie passe en dernier : Discord
        #    refuse de supprimer une catégorie qui contient encore des salons.
        targets = collect_targets(guild)
        targets.sort(key=lambda r: isinstance(r, discord.CategoryChannel))
        deleted, failed = await throttled_each(
            targets,
            lambda r: r.delete(reason=f"/reset par {interaction.user}"),
            delay=0.4,
            label=f"reset {guild.name}",
        )

        # 3. Effacer la configuration du serveur.
        cleared = reset_guild(gid)

        # 4. Statistiques : uniquement si la case a été cochée.
        stats_wiped = 0
        if self.wipe_stats:
            classement = interaction.client.get_cog("Classement")
            if classement is not None:
                stats_wiped = len(classement.player_stats)
                classement.player_stats.clear()
                try:
                    await classement.save_classement_config()
                except Exception as e:
                    log.error(f"Statistiques non sauvegardées après reset : {e}")

        log.warning(
            f"[{guild.name}] RESET par {interaction.user} : {deleted} ressource(s) supprimée(s), "
            f"{failed} échec(s), {len(cleared)} section(s) de config effacée(s), "
            f"{stats_wiped} joueur(s) réinitialisé(s)."
        )

        embed = embeds.base(
            gid,
            title=t(gid, "reset.done_title"),
            description=t(gid, "reset.done_desc", deleted=deleted, cleared=len(cleared)),
            kind="warning" if failed else "success",
        )
        if failed:
            embed.add_field(name=t(gid, "reset.field_failed"), value=t(gid, "reset.failed_desc", count=failed), inline=False)
        if stats_wiped:
            embed.add_field(name=t(gid, "reset.field_stats"), value=t(gid, "reset.stats_wiped", count=stats_wiped), inline=False)
        embed.add_field(name=t(gid, "reset.field_next"), value=t(gid, "reset.next_desc"), inline=False)
        # /reset est souvent lancé DEPUIS un salon que le reset vient de
        # supprimer : le webhook de l'interaction meurt avec lui (10003 Unknown
        # Channel).
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException:
            try:
                await interaction.user.send(embed=embed)
            except discord.HTTPException:
                log.warning(f"[{guild.name}] Compte-rendu de reset non remis à {interaction.user}.")

        # 5. Republier l'assistant dans un salon encore vivant : après un
        # reset, le serveur se retrouve dans l'état d'un premier ajout.
        me = guild.me
        # Comparaison par ID : les objets salons restent en cache après
        # suppression, `not in targets` laisserait passer un salon mort.
        deleted_ids = {r.id for r in targets}
        channel = next(
            (c for c in guild.text_channels
             if me and c.id not in deleted_ids and c.permissions_for(me).send_messages),
            None,
        )
        if channel is None:
            return
        try:
            from cogs.wizard import channels_embed, ChannelsWizard
            view = ChannelsWizard(guild, intro=True)
            message = await channel.send(embed=channels_embed(guild, intro=True), view=view)
            set_setup_panel(guild.id, channel.id, message.id)
            interaction.client.add_view(view, message_id=message.id)
        except Exception as e:
            log.error(f"[{guild.name}] Assistant non republié après le reset : {e}")


class Reset(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="reset", description="Remet le bot à zéro sur ce serveur (supprime salons et rôles).")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(t(None, "common.members_only"), ephemeral=True)
            return
        view = ResetView(guild, interaction.user.id)
        await interaction.response.send_message(
            embed=build_preview_embed(guild, False, view.code),
            view=view,
            ephemeral=True,
            allowed_mentions=NO_PINGS,
        )

    @reset.error
    async def reset_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                t(interaction.guild_id, "reset.admin_only"), ephemeral=True
            )
        else:
            log.exception("Erreur cog reset", exc_info=error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reset(bot))
    log.info("Cog Reset chargé")
