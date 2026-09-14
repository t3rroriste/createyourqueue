"""
Cog : Temp Bot
===============
Commandes spécifiques pour le bot temporaire, réservées au owner :

- /waiting : envoie le message « Coming soon » dans le salon courant.
- /tempo   : remet le serveur entier à zéro et ne laisse que deux salons,
             « coming-soon » (texte, lecture seule, avec l'embed) et
             « Waiting Room » (vocal).

/tempo — ce qui est fait
------------------------
Supprimé : tous les salons et catégories, tous les rôles que Discord laisse
supprimer, les emojis, stickers, sons, événements et règles AutoMod.
Remis à zéro : les permissions de @everyone (aucune), donc tout salon créé
plus tard est invisible tant qu'on ne l'ouvre pas.
Jamais touché : les membres (aucun kick, aucun ban, pseudos gardés), la
liste des bannis, le nom et l'icône du serveur.

Ce que Discord interdit de supprimer reste, mais rendu inaccessible :
- les salons exigés par la Communauté (règlement, mises à jour) sont vidés
  de leurs permissions et cachés à @everyone ;
- les rôles des bots et des intégrations sont gérés par Discord ; le rôle
  Booster perd ses permissions ;
- les rôles placés au-dessus du rôle du bot restent tels quels : l'aperçu
  les signale avant confirmation.

Sécurité : les deux nouveaux salons sont créés AVANT toute suppression. Si
leur création échoue, rien n'est détruit.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.reset import CAPTCHA_LENGTH, generate_code
from config import OWNER_ID
from rate_limit import throttled_each

log = logging.getLogger("bot.temp_bot")

# Noms des deux salons créés par /tempo.
COMING_SOON_NAME = "🚧・coming-soon"
WAITING_ROOM_NAME = "⏳・Waiting Room"


def waiting_embed() -> discord.Embed:
    """L'embed « Coming soon », commun à /waiting et /tempo."""
    embed = discord.Embed(
        title="**🚧‎ ‎ ‎ ‎ ‎Coming soon ...‎‎ ‎ ‎ ‎ ‎ 🚧**",
        description=(
            ">>> 🇫🇷 : Le serveur Discord est en cours de création. Veuillez patienter.\n"
            "🇺🇸 : The Discord server is currently under construction. Please wait."
        ),
        color=0x000000  # Noir
    )
    embed.set_footer(text="L'equipe CYQ")
    return embed


def split_roles(guild: discord.Guild) -> tuple[list[discord.Role], list[discord.Role]]:
    """(rôles supprimables, rôles intouchables).

    Intouchables : ceux gérés par Discord (bots, intégrations, Booster) et
    ceux au-dessus du rôle du bot. @everyone n'est dans aucune des listes."""
    deletable, untouchable = [], []
    for role in guild.roles:
        if role.is_default():
            continue
        (deletable if role.is_assignable() else untouchable).append(role)
    return deletable, untouchable


def build_preview_embed(guild: discord.Guild, code: str) -> discord.Embed:
    deletable, untouchable = split_roles(guild)
    embed = discord.Embed(
        title="⚠️ /tempo — remise à zéro totale du serveur",
        description=(
            f"**{discord.utils.escape_markdown(guild.name)}** va être vidé. "
            "Cette action est **irréversible**.\n"
            "Aucun membre n'est expulsé ni banni."
        ),
        color=0xED4245,
    )
    embed.add_field(
        name="🗑️ Supprimé",
        value=(
            f"• {len(guild.channels)} salon(s) et catégorie(s)\n"
            f"• {len(deletable)} rôle(s)\n"
            f"• {len(guild.emojis)} emoji(s), {len(guild.stickers)} sticker(s)\n"
            f"• {len(guild.scheduled_events)} événement(s), les sons et les règles AutoMod\n"
            "• toutes les permissions de @everyone"
        ),
        inline=False,
    )
    embed.add_field(
        name="✨ Créé",
        value=(
            f"• `{COMING_SOON_NAME}` — texte, lecture seule, avec l'embed Coming soon\n"
            f"• `{WAITING_ROOM_NAME}` — vocal\n"
            "Les membres ne verront plus que ces deux salons."
        ),
        inline=False,
    )
    above = [r for r in untouchable if not r.managed]
    if above:
        names = ", ".join(r.name for r in above)
        embed.add_field(
            name=f"⛔ {len(above)} rôle(s) au-dessus du bot — ne seront pas supprimés",
            value=(
                discord.utils.escape_markdown(names)[:700]
                + "\nPlace le rôle du bot tout en haut (Paramètres du serveur → Rôles) "
                  "puis relance /tempo."
            ),
            inline=False,
        )
    embed.add_field(name="🔐 Code de confirmation", value=f"`{code}`", inline=False)
    embed.set_footer(text="Clique sur Purger et recopie le code. Panneau valable 5 minutes.")
    return embed


class ConfirmModal(discord.ui.Modal, title="Confirmer /tempo"):
    def __init__(self, view: "TempoView"):
        super().__init__()
        self.view = view
        self.field = discord.ui.TextInput(
            label=f"Recopie le code : {view.code}",
            placeholder=view.code,
            min_length=CAPTCHA_LENGTH,
            max_length=CAPTCHA_LENGTH,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Un seul essai : un code faux ferme le panneau, il faut relancer
        # /tempo — donc relire l'aperçu.
        for item in self.view.children:
            item.disabled = True
        self.view.stop()
        if self.field.value.strip().upper() != self.view.code:
            await interaction.response.edit_message(
                content="❌ Code incorrect. Rien n'a été supprimé — relance /tempo.",
                embed=None,
                view=self.view,
            )
            return
        await self.view.cog.run_tempo(interaction, self.view.guild)


class TempoView(discord.ui.View):
    def __init__(self, cog: "TempBot", guild: discord.Guild, author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author_id = author_id
        self.code = generate_code()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce panneau ne t'appartient pas.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Purger", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(ConfirmModal(self))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        for item in self.children:
            item.disabled = True
        self.stop()
        await interaction.response.edit_message(content="Annulé, rien n'a été touché.", embed=None, view=self)


class TempBot(commands.Cog):
    """Commandes spécifiques pour le bot temporaire."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Stocker les IDs des messages waiting par salon pour pouvoir les mettre à jour
        self.waiting_messages = {}  # {channel_id: message_id}
        # Serveurs où un /tempo tourne : deux purges croisées se marcheraient dessus.
        self.tempo_running: set[int] = set()

    async def _is_owner(self, user: discord.abc.User) -> bool:
        if OWNER_ID and user.id == OWNER_ID:
            return True
        return await self.bot.is_owner(user)

    @app_commands.command(name="waiting", description="Envoie le message d'attente (owner uniquement)")
    async def waiting(self, interaction: discord.Interaction) -> None:
        """Envoie le message d'attente et supprime la commande (owner uniquement)."""


        # Propriétaire : OWNER_ID dans .env, ou le propriétaire de l'application Discord
        if not await self._is_owner(interaction.user):
            await interaction.response.send_message("Cette commande est réservée au owner du bot.", ephemeral=True)
            return

        # Supprimer le message de commande
        try:
            await interaction.response.defer(ephemeral=True)
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass

        embed = waiting_embed()

        # Vérifier s'il y a déjà un message waiting dans ce salon
        channel_id = interaction.channel.id
        if channel_id in self.waiting_messages:
            try:
                # Supprimer l'ancien message
                old_message_id = self.waiting_messages[channel_id]
                old_message = await interaction.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException:
                pass  # L'ancien message n'existe plus ou ne peut pas être supprimé

        # Envoyer le nouveau message
        message = await interaction.channel.send(embed=embed)

        # Stocker l'ID du nouveau message
        self.waiting_messages[channel_id] = message.id

    @app_commands.command(name="tempo", description="Remet tout le serveur à zéro : ne garde que coming-soon et Waiting Room (owner uniquement)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def tempo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not await self._is_owner(interaction.user):
            await interaction.response.send_message("Cette commande est réservée au owner du bot.", ephemeral=True)
            return
        if not guild.me.guild_permissions.administrator:
            await interaction.response.send_message(
                "Le bot a besoin de la permission **Administrateur** sur ce serveur pour tout remettre à zéro.",
                ephemeral=True,
            )
            return
        if guild.id in self.tempo_running:
            await interaction.response.send_message("Un /tempo est déjà en cours sur ce serveur.", ephemeral=True)
            return

        view = TempoView(self, guild, interaction.user.id)
        await interaction.response.send_message(
            embed=build_preview_embed(guild, view.code), view=view, ephemeral=True
        )

    # ------------------------------------------------------------------
    async def run_tempo(self, interaction: discord.Interaction, guild: discord.Guild) -> None:
        if guild.id in self.tempo_running:
            await interaction.response.edit_message(content="Un /tempo est déjà en cours sur ce serveur.", embed=None, view=None)
            return
        self.tempo_running.add(guild.id)
        try:
            await interaction.response.edit_message(
                content="⏳ Remise à zéro en cours… Le compte-rendu arrivera ici ou en message privé.",
                embed=None,
                view=None,
            )
            report = await self._purge(guild, interaction.user)
        finally:
            self.tempo_running.discard(guild.id)

        # Le salon d'où /tempo a été lancé vient d'être supprimé : la réponse
        # éphémère peut échouer (10003 Unknown Channel). Repli sur un MP.
        try:
            await interaction.followup.send(embed=report, ephemeral=True)
        except discord.HTTPException:
            try:
                await interaction.user.send(embed=report)
            except discord.HTTPException:
                log.warning(f"[{guild.name}] Compte-rendu de /tempo non remis à {interaction.user}.")

    async def _purge(self, guild: discord.Guild, author: discord.abc.User) -> discord.Embed:
        reason = f"/tempo par {author}"
        everyone = guild.default_role
        lines: list[str] = []

        # 1. Les deux salons d'abord : si Discord refuse de les créer (limite
        #    de 500 salons atteinte, panne), on s'arrête avant d'avoir détruit
        #    quoi que ce soit.
        try:
            coming_soon = await guild.create_text_channel(
                COMING_SOON_NAME,
                reason=reason,
                overwrites={everyone: discord.PermissionOverwrite(
                    view_channel=True, read_message_history=True,
                    send_messages=False, add_reactions=False,
                    create_public_threads=False, create_private_threads=False,
                    send_messages_in_threads=False,
                )},
            )
            waiting_room = await guild.create_voice_channel(
                WAITING_ROOM_NAME,
                reason=reason,
                overwrites={everyone: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True, use_voice_activation=True,
                    stream=False, send_messages=False,
                )},
            )
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] /tempo interrompu, salons non créés : {e}")
            return discord.Embed(
                title="❌ /tempo interrompu",
                description=f"Les salons n'ont pas pu être créés ({e.text or e.status}).\n**Rien n'a été supprimé.**",
                color=0xED4245,
            )
        keep = {coming_soon.id, waiting_room.id}
        log.warning(f"[{guild.name}] /tempo lancé par {author}")

        # 2. @everyone sans aucune permission : seuls les deux salons, qui
        #    l'autorisent explicitement, restent visibles.
        try:
            await everyone.edit(permissions=discord.Permissions.none(), reason=reason)
        except discord.HTTPException as e:
            lines.append(f"⚠️ Permissions de @everyone non réinitialisées : {e.text or e.status}")

        # 3. L'onboarding impose des salons par défaut : actif, il bloquerait
        #    leur suppression.
        if "COMMUNITY" in guild.features:
            try:
                await guild.edit_onboarding(enabled=False, reason=reason)
            except discord.HTTPException:
                pass  # Pas d'onboarding configuré

        # 4. Salons. Les catégories en dernier, pour des logs lisibles. Un
        #    salon que Discord refuse de supprimer (règlement ou mises à jour
        #    d'un serveur Communauté) est caché à la place.
        channels = [c for c in guild.channels if c.id not in keep]
        channels.sort(key=lambda c: isinstance(c, discord.CategoryChannel))
        hidden: list[str] = []

        async def delete_or_hide(channel: discord.abc.GuildChannel) -> None:
            try:
                await channel.delete(reason=reason)
            except discord.NotFound:
                pass
            except discord.HTTPException:
                await channel.edit(
                    overwrites={everyone: discord.PermissionOverwrite(view_channel=False)},
                    reason=reason,
                )
                hidden.append(channel.name)

        deleted_channels, failed_channels = await throttled_each(
            channels, delete_or_hide, delay=0.4, label=f"tempo salons {guild.name}"
        )
        deleted_channels -= len(hidden)
        lines.append(f"🗑️ {deleted_channels} salon(s) supprimé(s)")
        if hidden:
            lines.append(
                f"🙈 {len(hidden)} salon(s) exigé(s) par la Communauté, cachés : "
                + discord.utils.escape_markdown(", ".join(hidden))[:300]
                + " — désactive la Communauté pour pouvoir les supprimer"
            )
        if failed_channels:
            lines.append(f"⚠️ {failed_channels} salon(s) ni supprimé(s) ni caché(s)")

        # 5. Rôles.
        deletable, untouchable = split_roles(guild)
        deleted_roles, failed_roles = await throttled_each(
            deletable, lambda r: r.delete(reason=reason), delay=0.4, label=f"tempo rôles {guild.name}"
        )
        lines.append(f"🗑️ {deleted_roles} rôle(s) supprimé(s)")
        if failed_roles:
            lines.append(f"⚠️ {failed_roles} rôle(s) non supprimé(s)")
        # Booster : géré par Discord, mais ses permissions se modifient.
        booster = guild.premium_subscriber_role
        if booster is not None and booster < guild.me.top_role:
            try:
                await booster.edit(permissions=discord.Permissions.none(), reason=reason)
            except discord.HTTPException:
                pass
        above = [r for r in untouchable if not r.managed]
        if above:
            lines.append(
                f"⛔ {len(above)} rôle(s) au-dessus du bot gardé(s) : "
                + discord.utils.escape_markdown(", ".join(r.name for r in above))[:300]
            )

        # 6. Emojis, stickers, événements, sons, AutoMod.
        extras: list = [*guild.emojis, *guild.stickers, *guild.scheduled_events]
        for fetch in (guild.fetch_soundboard_sounds, guild.fetch_automod_rules):
            try:
                extras.extend(await fetch())
            except discord.HTTPException as e:
                log.warning(f"[{guild.name}] /tempo : {fetch.__name__} impossible : {e}")
        deleted_extras, failed_extras = await throttled_each(
            extras, lambda x: x.delete(reason=reason), delay=0.5, label=f"tempo extras {guild.name}"
        )
        lines.append(f"🗑️ {deleted_extras} emoji(s), sticker(s), événement(s), son(s) et règle(s) AutoMod")
        if failed_extras:
            lines.append(f"⚠️ {failed_extras} élément(s) non supprimé(s)")

        # 7. L'embed dans coming-soon.
        try:
            message = await coming_soon.send(embed=waiting_embed())
            self.waiting_messages[coming_soon.id] = message.id
        except discord.HTTPException as e:
            lines.append(f"⚠️ Embed Coming soon non envoyé : {e.text or e.status}")

        failed = failed_channels + failed_roles + failed_extras
        log.warning(
            f"[{guild.name}] /tempo terminé : {deleted_channels} salon(s), {deleted_roles} rôle(s), "
            f"{deleted_extras} extra(s) supprimé(s), {len(hidden)} caché(s), {failed} échec(s)."
        )
        lines.append(f"\n✨ Créés : {coming_soon.mention} et {waiting_room.mention}")
        return discord.Embed(
            title="✅ Serveur remis à zéro" if not failed else "⚠️ Serveur remis à zéro, avec des échecs",
            description="\n".join(lines)[:4000],
            color=0x57F287 if not failed else 0xFEE75C,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TempBot(bot))
