"""
Cog : Wizard
============
Assistant de configuration — le parcours d'entrée du bot.

Principe : **on n'impose rien.**

L'ancien `/setup` créait d'office une catégorie, six salons et quatre rôles
avec des noms imposés. Un serveur qui avait déjà ses salons se retrouvait
avec des doublons, et il fallait ensuite tout renommer ou tout supprimer.
Ici, l'organisateur **désigne des salons qui existent déjà** chez lui, quels
que soient leur nom et leur emplacement, et n'active que ce qu'il veut.

Le parcours
-----------
1. **Le bot arrive** : un seul message, qui explique ce qu'il fait **et**
   demande directement quel salon sert à quoi, avec un menu par salon.
2. **Continuer** : le même message passe au rôle organisateur, aux salons
   facultatifs et aux fonctions à activer ou non.
3. **`/queue`** ouvre alors le panneau de queue. Tant que la configuration
   n'est pas finie, `/queue` ramène là où il reste à faire.

Les salons désignés sont enregistrés par **identifiant** (voir resources.py) :
les renommer plus tard ne casse rien.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import embeds
import resources
from config import SUPPORT_INVITE
from guild_settings import (
    WIZARD_SLOTS, OPTIONAL_SLOTS, get_features, set_features, channels_ready,
    queue_ready, set_resource_id, clear_resource_id, get_mmr_config, set_mmr_config,
    mark_setup_complete, get_setup_panel
)
from i18n import t

log = logging.getLogger("bot.wizard")

SLOT_KINDS = {key: kind for key, kind, _req in list(WIZARD_SLOTS) + list(OPTIONAL_SLOTS)}

SLOT_EMOJI = {
    "channel_queue_command": "🛠️",
    "channel_queue_announcement": "📢",
    "voice_queue_waiting": "🎙️",
    "channel_queue_resultat": "📜",
    "channel_queue_classement": "📊",
}


def _resolve(guild: discord.Guild, key: str):
    kind = SLOT_KINDS.get(key)
    if kind == "voice":
        return resources.get_voice_channel(guild, key)
    return resources.get_text_channel(guild, key)


def _may_configure(user) -> bool:
    """Qui a le droit de configurer : les administrateurs du serveur.

    Volontairement pas le rôle organisateur — c'est justement lui qu'on est
    en train de définir."""
    return isinstance(user, discord.Member) and user.guild_permissions.manage_guild


# ----------------------------------------------------------------------
# Panneau des salons
# ----------------------------------------------------------------------
def channels_embed(guild: discord.Guild, *, intro: bool = False) -> discord.Embed:
    """Panneau de désignation des salons.

    `intro=True` pour le message d'arrivée : le bot se présente **et** pose
    la première question dans le même message. Souhaiter la bienvenue puis
    renvoyer vers une commande ajoutait une étape pour rien — la question
    « quel salon ? » se pose tout de suite."""
    gid = guild.id
    done = sum(1 for key, _k, _r in WIZARD_SLOTS if _resolve(guild, key) is not None)

    # Une ligne par salon, pas un paragraphe. La version détaillée faisait
    # quatre pavés d'explication avant même le premier menu : on ne voyait
    # plus qu'il suffisait de dérouler et cliquer.
    # Les facultatifs sont listés ici pour qu'on sache à quoi s'attendre,
    # mais ils se règlent sur le panneau suivant : cinq menus + un bouton ne
    # tiennent pas dans les cinq rangées d'une vue Discord.
    lines = []
    for key, _kind, required in list(WIZARD_SLOTS) + list(OPTIONAL_SLOTS):
        resource = _resolve(guild, key)
        value = (
            resource.mention if isinstance(resource, discord.TextChannel)
            else f"**{resource.name}**" if resource is not None
            else t(gid, "wiz.not_set")
        )
        lines.append(
            f"{SLOT_EMOJI.get(key, '📁')} ・{t(gid, f'wiz.slot_{key}')} — {value}"
            + ("" if required else f" (__{t(gid, 'wiz.optional')}__)")
        )

    header = f"{t(gid, 'wiz.hello_desc')}\n\n" if intro else ""
    embed = embeds.base(
        gid,
        title=t(gid, "wiz.hello_title") if intro else t(gid, "wiz.ch_title"),
        description=(
            f"{header}{t(gid, 'wiz.ch_desc')}\n\n"
            + "\n".join(lines)
            + f"\n\n**{done}/{len(WIZARD_SLOTS)}**"
        ),
        kind="brand",
        footer=t(gid, "wiz.ch_footer"),
    )
    embeds.brand(embed, guild)
    return embed


class ChannelsWizard(discord.ui.View):
    """Un menu par salon à désigner, alimenté par les salons du serveur."""

    def __init__(self, guild: discord.Guild, *, intro: bool = False):
        # Sans expiration : ce panneau est publié dans un salon du serveur et
        # doit répondre encore le lendemain, pas seulement 15 minutes.
        super().__init__(timeout=None)
        self.guild = guild
        self.intro = intro
        gid = guild.id

        for index, (key, kind, _required) in enumerate(WIZARD_SLOTS):
            select = discord.ui.ChannelSelect(
                placeholder=f"{SLOT_EMOJI.get(key, '📁')}  {t(gid, f'wiz.slot_{key}')}"[:150],
                channel_types=[discord.ChannelType.voice] if kind == "voice"
                else [discord.ChannelType.text],
                row=index,
                custom_id=f"cyq:wiz:slot:{key}",
            )
            select.callback = self._assign(key, select)
            self.add_item(select)

        self.finish.label = t(gid, "wiz.btn_next")
        self.finish.disabled = not channels_ready(gid)
        self.skip.label = "Skip"
        self.missclick.label = t(gid, "welcome.missclick")
        if SUPPORT_INVITE:
            self.add_item(discord.ui.Button(
                label=t(gid, "wiz.btn_support"), emoji="💬", url=SUPPORT_INVITE, row=4
            ))

    def _assign(self, key: str, select: discord.ui.ChannelSelect):
        async def callback(interaction: discord.Interaction) -> None:
            if not _may_configure(interaction.user):
                await interaction.response.send_message(
                    t(self.guild.id, "wiz.admin_only"), ephemeral=True
                )
                return
            chosen = select.values[0]
            set_resource_id(self.guild.id, key, chosen.id)
            self.finish.disabled = not channels_ready(self.guild.id)
            await interaction.response.edit_message(
                embed=channels_embed(self.guild, intro=self.intro), view=self
            )
        return callback

    @discord.ui.button(label="Suivant", style=discord.ButtonStyle.success, emoji="➡️", row=4)
    async def finish(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not _may_configure(interaction.user):
            await interaction.response.send_message(
                t(self.guild.id, "wiz.admin_only"), ephemeral=True
            )
            return
        if not channels_ready(self.guild.id):
            await interaction.response.send_message(
                t(self.guild.id, "wiz.ch_incomplete"), ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=options_embed(self.guild),
            view=OptionsWizard(self.guild),
        )

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, emoji="⏭️", row=4)
    async def skip(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not _may_configure(interaction.user):
            await interaction.response.send_message(
                t(self.guild.id, "wiz.admin_only"), ephemeral=True
            )
            return
        # Skip les salons et passer directement aux options
        await interaction.response.edit_message(
            content=None,
            embed=options_embed(self.guild),
            view=OptionsWizard(self.guild),
        )

    @discord.ui.button(label="MissClick", style=discord.ButtonStyle.danger, row=4)
    async def missclick(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Revient à la sélection de langue en cas d'erreur."""
        from i18n import t
        if not _may_configure(interaction.user):
            await interaction.response.send_message(
                t(self.guild.id, "wiz.admin_only"), ephemeral=True
            )
            return
        
        # Revenir au message de sélection de langue
        from cogs.welcome import LanguageSelectView
        embed = discord.Embed(
            title=t(self.guild.id, "welcome.title"),
            description=t(self.guild.id, "welcome.description"),
            color=0x5865F2
        )
        view = LanguageSelectView(self.guild.id)
        
        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=view
        )


# ----------------------------------------------------------------------
# Panneau des options
#
# Un menu d'accueil, puis un panneau par sujet. La version précédente
# entassait cinq menus et quatre boutons sur un seul écran : on ne savait
# plus ce qui allait avec quoi. Ici chaque page ne traite qu'une question,
# et l'état choisi se lit sans cliquer — l'option retenue en gras, l'autre
# barrée.
# ----------------------------------------------------------------------
# `toggle_line` et `pick_line` vivent maintenant dans embeds.py : le panneau
# de statut les utilise aussi, et ce sont des helpers d'affichage.


def _channel_line(guild: discord.Guild, key: str) -> str:
    channel = resources.get_text_channel(guild, key)
    return t(
        guild.id, "wiz.opt_channel_line",
        channel=channel.mention if channel is not None else t(guild.id, "wiz.not_set"),
    )


def options_embed(guild: discord.Guild, *, solo: bool = False) -> discord.Embed:
    """L'accueil des options : les quatre sujets, un bouton chacun."""
    gid = guild.id
    embed = discord.Embed(
        title=t(gid, "wiz.opt_title"),
        description="\n".join([
            t(gid, "wiz.opt_menu_leaderboard"),
            t(gid, "wiz.opt_menu_result"),
            t(gid, "wiz.opt_menu_mmr"),
            t(gid, "wiz.opt_menu_clan"),
            "",
            t(gid, "wiz.opt_menu_roles"),
            t(gid, "wiz.opt_menu_staff"),
        ]),
        color=0x000000
    )
    return embed


class OptionsWizard(discord.ui.View):
    """Menu d'accueil des options."""

    def __init__(self, guild: discord.Guild, *, solo: bool = False):
        # Sans expiration : ce panneau est aussi le message public d'arrivée,
        # qui doit répondre encore le lendemain.
        super().__init__(timeout=None)
        self.guild = guild
        self.solo = solo
        gid = guild.id
        self.leaderboard.label = t(gid, "wiz.opt_btn_leaderboard")
        self.result.label = t(gid, "wiz.opt_btn_result")
        self.mmr.label = t(gid, "wiz.opt_btn_mmr")
        self.clan.label = t(gid, "wiz.opt_btn_clan")
        self.roles.label = t(gid, "wiz.opt_btn_roles")
        self.staff.label = t(gid, "wiz.opt_btn_staff")
        self.finish.label = t(gid, "wiz.btn_close" if solo else "wiz.btn_finish")
        self.finish.disabled = not queue_ready(gid)

    async def guard(self, interaction: discord.Interaction) -> bool:
        if _may_configure(interaction.user):
            return True
        await interaction.response.send_message(t(self.guild.id, "wiz.admin_only"), ephemeral=True)
        return False

    async def _open(self, interaction: discord.Interaction, view: "SubPanel") -> None:
        await interaction.response.edit_message(content=None, embed=view.embed(), view=view)

    @discord.ui.button(label="Classement", style=discord.ButtonStyle.secondary,
                       emoji="📊", row=0, custom_id="cyq:wiz:lb")
    async def leaderboard(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self.guard(interaction):
            await self._open(interaction, FeaturePanel(self, "leaderboard"))

    @discord.ui.button(label="Résultat", style=discord.ButtonStyle.secondary,
                       emoji="📚", row=0, custom_id="cyq:wiz:res")
    async def result(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self.guard(interaction):
            await self._open(interaction, FeaturePanel(self, "result"))

    @discord.ui.button(label="MMR", style=discord.ButtonStyle.secondary,
                       emoji="⭐", row=0, custom_id="cyq:wiz:mmr")
    async def mmr(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self.guard(interaction):
            await self._open(interaction, MMRPanel(self))

    @discord.ui.button(label="Clan", style=discord.ButtonStyle.secondary,
                       emoji="📜", row=0, custom_id="cyq:wiz:clan")
    async def clan(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self.guard(interaction):
            await self._open(interaction, ClanPanel(self))

    # Cinq boutons sur la rangée 0 : c'est le maximum autorisé par Discord.
    # Un sujet de plus demandera une seconde rangée.
    @discord.ui.button(label="Rôle", style=discord.ButtonStyle.secondary,
                       emoji="🔗", row=0, custom_id="cyq:wiz:roles")
    async def roles(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self.guard(interaction):
            await self._open(interaction, RolePanel(self))
    
    @discord.ui.button(label="Staff", style=discord.ButtonStyle.secondary,
                       emoji="🛡️", row=1, custom_id="cyq:wiz:staff")
    async def staff(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self.guard(interaction):
            await self._open(interaction, StaffPanel(self))

    @discord.ui.button(label="📚 Guide", style=discord.ButtonStyle.primary,
                       row=1, custom_id="cyq:wiz:guide")
    async def guide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Affiche le guide d'activation des options."""
        if await self.guard(interaction):
            embed = discord.Embed(
                title=t(self.guild.id, "wiz.opt_guide_title"),
                description=t(self.guild.id, "wiz.opt_guide_desc"),
                color=0x5865F2
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Terminer", style=discord.ButtonStyle.success,
                       emoji="✅", row=2, custom_id="cyq:wiz:done")
    async def finish(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.guard(interaction):
            return
        gid = self.guild.id
        # Permettre de terminer même si la configuration n'est pas complète
        mark_setup_complete(gid, interaction.user.id)
        await interaction.response.edit_message(
            content=None, embed=done_embed(self.guild), view=None
        )

    @discord.ui.button(label="◀️ Retour", style=discord.ButtonStyle.secondary,
                       row=2, custom_id="cyq:wiz:back")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Retourne au panneau de configuration des salons."""
        if await self.guard(interaction):
            from cogs.wizard import ChannelsWizard, channels_embed
            view = ChannelsWizard(self.guild, intro=False)
            await interaction.response.edit_message(
                content=None,
                embed=channels_embed(self.guild, intro=False),
                view=view
            )


class SubPanel(discord.ui.View):
    """Ce que toutes les pages ont en commun : le retour et le contrôle
    d'accès. Chaque page ne code que ce qui la distingue."""

    def __init__(self, home: OptionsWizard):
        super().__init__(timeout=600)
        self.home = home
        self.guild = home.guild
        self.gid = home.guild.id

    async def guard(self, interaction: discord.Interaction) -> bool:
        return await self.home.guard(interaction)

    def sync(self) -> None:
        """Reconstruit les boutons : leur couleur et leur libellé dépendent
        de l'état, qui vient de changer."""

    async def refresh(self, interaction: discord.Interaction) -> None:
        """Tout se met à jour dans le message, sans en poster un second."""
        self.sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    def add_back(self, row: int) -> None:
        button = discord.ui.Button(
            label=t(self.gid, "wiz.opt_back"), emoji="◀️",
            style=discord.ButtonStyle.secondary, row=row,
        )

        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            await interaction.response.edit_message(
                embed=options_embed(self.guild, solo=self.home.solo), view=self.home
            )
        button.callback = callback
        self.add_item(button)


class FeaturePanel(SubPanel):
    """Classement et Résultat : même page, même réglage — un salon, un
    interrupteur. Les séparer en deux classes aurait garanti que l'une
    finisse par prendre du retard sur l'autre."""

    SPEC = {
        "leaderboard": ("channel_queue_classement", "leaderboard"),
        "result": ("channel_queue_resultat", None),
    }

    def __init__(self, home: OptionsWizard, kind: str):
        super().__init__(home)
        self.kind = kind
        self.slot, self.feature = self.SPEC[kind]
        self.sync()

    def is_on(self) -> bool:
        """Le Résultat n'a pas d'interrupteur propre : il est actif dès qu'un
        salon est désigné. Un second réglage laisserait activer une fonction
        qui n'a nulle part où écrire."""
        if self.feature is None:
            return resources.get_text_channel(self.guild, self.slot) is not None
        return bool(get_features(self.gid)[self.feature])

    def sync(self) -> None:
        self.clear_items()
        select = discord.ui.ChannelSelect(
            placeholder=t(self.gid, "wiz.opt_pick_channel")[:150],
            channel_types=[discord.ChannelType.text], row=0,
        )
        select.callback = self._set_channel(select)
        self.add_item(select)
        self.add_item(self._toggle_button())
        self.add_back(1)

    def _toggle_button(self) -> discord.ui.Button:
        on = self.is_on()
        button = discord.ui.Button(
            label=t(self.gid, "wiz.opt_off_word" if on else "wiz.opt_on_word"),
            emoji="🔴" if on else "🟢",
            style=discord.ButtonStyle.danger if on else discord.ButtonStyle.success,
            row=1,
        )

        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            if self.feature is None:
                if not self.is_on():
                    await interaction.response.send_message(
                        t(self.gid, "wiz.opt_need_channel"), ephemeral=True)
                    return
                # Éteindre le Résultat, c'est oublier son salon : il n'y a
                # rien d'autre à couper.
                clear_resource_id(self.gid, self.slot)
            else:
                set_features(self.gid, **{self.feature: not self.is_on()})
            await self.refresh(interaction)
        button.callback = callback
        return button

    def _set_channel(self, select: discord.ui.ChannelSelect):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            set_resource_id(self.gid, self.slot, select.values[0].id)
            await self.refresh(interaction)
        return callback

    def embed(self) -> discord.Embed:
        embed = embeds.base(
            self.gid,
            title=t(self.gid, f"wiz.opt_{self.kind}_title"),
            description=(
                f"{_channel_line(self.guild, self.slot)}\n\n"
                f"{embeds.toggle_line(self.gid, self.is_on())}"
            ),
            kind="brand",
        )
        embeds.brand(embed, self.guild)
        return embed


class ClanPanel(SubPanel):
    """Les clans : une catégorie, un rôle, un interrupteur.

    La catégorie n'est pas un confort : c'est là que le bot ouvre le salon de
    liaison de chaque clan. Sans elle, activer les clans créerait des salons
    n'importe où — on refuse donc d'allumer tant qu'elle n'est pas désignée.

    Le rôle, lui, ne sert qu'à `/clantransfer` : passer la propriété d'un clan
    à quelqu'un d'autre est un acte de modération, pas une action de joueur."""

    def __init__(self, home: OptionsWizard):
        super().__init__(home)
        self.sync()

    def is_on(self) -> bool:
        return bool(get_features(self.gid)["clans"])

    def category(self) -> discord.CategoryChannel | None:
        return resources.get_category(self.guild, "category_clan")

    def sync(self) -> None:
        self.clear_items()

        pick = discord.ui.ChannelSelect(
            placeholder=t(self.gid, "wiz.opt_pick_category")[:150],
            channel_types=[discord.ChannelType.category], row=0,
        )
        pick.callback = self._set_category(pick)
        self.add_item(pick)

        role = discord.ui.RoleSelect(
            placeholder=t(self.gid, "wiz.opt_clan_transfer")[:150], row=1,
        )
        role.callback = self._set_role(role)
        self.add_item(role)

        self.add_item(self._toggle_button())
        self.add_item(self._notice_button())
        self.add_back(2)

    def notice_in_chat(self) -> bool:
        return bool(get_features(self.gid)["clan_notice"])

    def _notice_button(self) -> discord.ui.Button:
        """Bascule l'annonce des demandes d'adhésion.

        Le bouton porte le mode vers lequel il fait basculer, comme les
        interrupteurs du reste du panneau : on lit ce que fera le clic."""
        chat = self.notice_in_chat()
        button = discord.ui.Button(
            label=t(self.gid, "wiz.opt_clan_notice_btn" if chat else "wiz.opt_clan_notice_chat"),
            style=discord.ButtonStyle.primary, row=2,
        )

        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            set_features(self.gid, clan_notice=not chat)
            await self.refresh(interaction)
        button.callback = callback
        return button

    def _set_category(self, select: discord.ui.ChannelSelect):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            set_resource_id(self.gid, "category_clan", select.values[0].id)
            await self.refresh(interaction)
        return callback

    def _set_role(self, select: discord.ui.RoleSelect):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            role = select.values[0]
            # @everyone voudrait dire « tout le monde peut transférer
            # n'importe quel clan » : ici ça veut dire « personne ».
            if role.is_default():
                clear_resource_id(self.gid, "role_clan_transfer")
            else:
                set_resource_id(self.gid, "role_clan_transfer", role.id)
            await self.refresh(interaction)
        return callback

    def _toggle_button(self) -> discord.ui.Button:
        on = self.is_on()
        button = discord.ui.Button(
            label=t(self.gid, "wiz.opt_off_word" if on else "wiz.opt_on_word"),
            emoji="🔴" if on else "🟢",
            style=discord.ButtonStyle.danger if on else discord.ButtonStyle.success,
            row=2,
        )

        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            if not on and self.category() is None:
                await interaction.response.send_message(
                    t(self.gid, "wiz.opt_need_category"), ephemeral=True)
                return
            set_features(self.gid, clans=not on)
            await self.refresh(interaction)
        button.callback = callback
        return button

    def embed(self) -> discord.Embed:
        category = self.category()
        role = resources.get_role(self.guild, "role_clan_transfer")
        embed = embeds.base(
            self.gid,
            title=t(self.gid, "wiz.opt_clan_title"),
            description="\n".join([
                t(self.gid, "wiz.opt_category_line",
                  category=f"**{category.name}**" if category is not None
                  else t(self.gid, "wiz.not_set")),
                "",
                t(self.gid, "wiz.opt_role_line",
                  label=t(self.gid, "wiz.opt_clan_transfer"),
                  role=role.mention if role is not None else t(self.gid, "wiz.not_set")),
                "",
                f"**{t(self.gid, 'wiz.opt_clan_notice_label')}**",
                embeds.pick_line(self.gid, "wiz.opt_clan_notice_chat",
                          "wiz.opt_clan_notice_btn", self.notice_in_chat()),
                "",
                embeds.toggle_line(self.gid, self.is_on()),
            ]),
            kind="brand",
        )
        embeds.brand(embed, self.guild)
        return embed


class RolePanel(SubPanel):
    """Les rôles : organisateur, connexion, chef de clan.

    Aucun n'est créé par le bot — on désigne des rôles qui existent déjà."""

    SLOTS = [("role_staff", "wiz.opt_staff"),
             ("role_connexion", "wiz.opt_connexion"),
             ("role_clan_leader", "wiz.opt_clan_leader")]

    def __init__(self, home: OptionsWizard):
        super().__init__(home)
        self.sync()

    def sync(self) -> None:
        self.clear_items()
        for row, (key, label_key) in enumerate(self.SLOTS):
            select = discord.ui.RoleSelect(
                placeholder=t(self.gid, label_key)[:150], row=row,
            )
            select.callback = self._set_role(key, select)
            self.add_item(select)
        self.add_item(self._connexion_toggle())
        self.add_back(3)

    def _set_role(self, key: str, select: discord.ui.RoleSelect):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            role = select.values[0]
            if role.is_default():
                # @everyone comme rôle organisateur donnerait la queue au
                # serveur entier ; sur les autres il veut dire « aucun ».
                if key == "role_staff":
                    await interaction.response.send_message(
                        t(self.gid, "wiz.opt_staff_everyone"), ephemeral=True)
                    return
                clear_resource_id(self.gid, key)
            else:
                set_resource_id(self.gid, key, role.id)
            await self.refresh(interaction)
        return callback

    def _connexion_toggle(self) -> discord.ui.Button:
        on = resources.get_role(self.guild, "role_connexion") is not None
        button = discord.ui.Button(
            label=t(self.gid, "wiz.opt_off_word" if on else "wiz.opt_on_word"),
            emoji="🔴" if on else "🟢",
            style=discord.ButtonStyle.danger if on else discord.ButtonStyle.success,
            row=3,
        )

        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            if not on:
                # On ne peut pas allumer un verrou sans dire avec quel rôle :
                # le menu juste au-dessus est la seule réponse possible.
                await interaction.response.send_message(
                    t(self.gid, "wiz.opt_need_role"), ephemeral=True)
                return
            clear_resource_id(self.gid, "role_connexion")
            await self.refresh(interaction)
        button.callback = callback
        return button

    def embed(self) -> discord.Embed:
        lines = []
        for key, label_key in self.SLOTS:
            role = resources.get_role(self.guild, key)
            lines.append(t(
                self.gid, "wiz.opt_role_line", label=t(self.gid, label_key),
                role=role.mention if role is not None else t(self.gid, "wiz.not_set"),
            ))
            if key == "role_connexion":
                lines.append(embeds.toggle_line(self.gid, role is not None))
            lines.append("")
        embed = embeds.base(
            self.gid, title=t(self.gid, "wiz.opt_roles_title"),
            description="\n".join(lines).strip(), kind="brand",
        )
        embeds.brand(embed, self.guild)
        return embed


# Rangs : clé de traduction (mmr.tier_*), seuil par défaut, emoji.
RANK_TIERS = [
    ("silver", 800, "🥈"),
    ("gold", 1000, "🥇"),
    ("platinum", 1200, "💎"),
    ("diamond", 1400, "🔷"),
    ("champion", 1600, "👑"),
    ("grand_champion", 1800, "🏆"),
]


def _rank_lines(gid: int, config: dict) -> list[str]:
    lines = [f"🥉 {t(gid, 'mmr.tier_bronze')} — 0"]
    for key, default, emoji in RANK_TIERS:
        lines.append(f"{emoji} {t(gid, f'mmr.tier_{key}')} — {config.get(f'rank_{key}', default)}")
    return lines


def _state_line(gid: int, on: bool) -> str:
    """« 🟢 **Activé** / ~~Désactivé~~ » : l'état retenu en gras, l'autre barré."""
    yes = t(gid, "wiz.enabled_word")
    no = t(gid, "wiz.disabled_word")
    if on:
        return f"🟢 **{yes}** / ~~{no}~~"
    return f"🔴 ~~{yes}~~ / **{no}**"


class StaffPanel(SubPanel):
    """Configuration du système de ticket pour le staff."""

    def __init__(self, home: OptionsWizard):
        super().__init__(home)
        self.sync()

    def sync(self) -> None:
        self.clear_items()
        from guild_settings import get_ticket_config
        enabled = bool((get_ticket_config(self.gid) or {}).get("enabled", False))

        toggle = discord.ui.Button(
            label=t(self.gid, "wiz.opt_off_word" if enabled else "wiz.opt_on_word"),
            emoji="🔴" if enabled else "🟢",
            style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
            row=0,
        )
        toggle.callback = self._toggle_enabled()
        self.add_item(toggle)

        channel_select = discord.ui.ChannelSelect(
            placeholder=t(self.gid, "wiz.staff_pick_channel")[:150],
            channel_types=[discord.ChannelType.text],
            row=1,
        )
        channel_select.callback = self._set_channel(channel_select)
        self.add_item(channel_select)

        self.add_back(2)

    def _toggle_enabled(self):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            from guild_settings import get_ticket_config, set_ticket_config
            config = get_ticket_config(self.gid) or {}
            config["enabled"] = not config.get("enabled", False)
            set_ticket_config(self.gid, config)
            await self.refresh(interaction)
        return callback

    def _set_channel(self, select: discord.ui.ChannelSelect):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            from guild_settings import get_ticket_config, set_ticket_config
            config = get_ticket_config(self.gid) or {}
            config["staff_channel_id"] = select.values[0].id
            set_ticket_config(self.gid, config)
            await self.refresh(interaction)
        return callback

    def embed(self) -> discord.Embed:
        from guild_settings import get_ticket_config
        config = get_ticket_config(self.gid) or {}
        enabled = config.get("enabled", False)
        channel_id = config.get("staff_channel_id")
        channel = self.guild.get_channel(channel_id) if channel_id else None

        lines = [
            t(self.gid, "wiz.staff_status",
              state=t(self.gid, "wiz.state_enabled" if enabled else "wiz.state_disabled")),
            t(self.gid, "wiz.staff_channel_line",
              channel=channel.mention if channel else t(self.gid, "wiz.not_set")),
            "",
            t(self.gid, "wiz.staff_hint"),
        ]
        embed = embeds.base(
            self.gid, title=t(self.gid, "wiz.staff_title"),
            description="\n".join(lines), kind="brand",
        )
        embeds.brand(embed, self.guild)
        return embed


class MMRPanel(SubPanel):
    """Le MMR : trois interrupteurs et un bouton vers les réglages fins."""

    def __init__(self, home: OptionsWizard):
        super().__init__(home)
        self.sync()

    def sync(self) -> None:
        self.clear_items()
        config = get_mmr_config(self.gid)
        features = get_features(self.gid)

        # État MMR, capitaines, rôles de rang : dans cet ordre, comme l'embed.
        for on, callback in (
            (bool(config["enabled"]), self._toggle_mmr()),
            (bool(features.get("captains", False)), self._toggle_captains()),
            (bool(features.get("mmr", False)), self._toggle_rank()),
        ):
            button = discord.ui.Button(
                label=t(self.gid, "wiz.enabled_word" if on else "wiz.disabled_word"),
                emoji="🟢" if on else "🔴",
                style=discord.ButtonStyle.success if on else discord.ButtonStyle.danger,
                row=0,
            )
            button.callback = callback
            self.add_item(button)

        others_btn = discord.ui.Button(
            label=t(self.gid, "wiz.mmr_other_heading"),
            emoji="🗂️",
            style=discord.ButtonStyle.primary,  # Discord n'a pas de jaune, primary = bleu
            row=1,
        )
        others_btn.callback = self._open_settings()
        self.add_item(others_btn)

        self.add_back(2)

    def _toggle_mmr(self):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            config = get_mmr_config(self.gid)
            new = not bool(config["enabled"])
            set_mmr_config(self.gid, enabled=new)
            set_features(self.gid, mvp=new)
            await self.refresh(interaction)
        return callback

    def _toggle_captains(self):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            features = get_features(self.gid)
            new = not bool(features.get("captains", False))
            set_features(self.gid, captains=new)
            await self.refresh(interaction)
        return callback

    def _toggle_rank(self):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            features = get_features(self.gid)
            new = not bool(features.get("mmr", False))
            set_features(self.gid, mmr=new)
            await self.refresh(interaction)
        return callback

    def _open_settings(self):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            view = MMRSettingsPanel(self.home)
            await interaction.response.edit_message(embed=view.embed(), view=view)
        return callback

    def embed(self) -> discord.Embed:
        gid = self.gid
        config = get_mmr_config(gid)
        features = get_features(gid)
        sections = [
            ("wiz.mmr_state_heading", bool(config["enabled"])),
            ("wiz.mmr_captains_heading", bool(features.get("captains", False))),
            ("wiz.mmr_ranks_heading", bool(features.get("mmr", False))),
        ]
        description = "\n\n".join(f"**_{t(gid, key)}_**\n{_state_line(gid, on)}" for key, on in sections)
        description += f"\n\n\n🗂️ **{t(gid, 'wiz.mmr_other_heading')}**"
        # Pas de footer, pas d'author, pas de logo
        return discord.Embed(title=t(gid, "wiz.mmr_panel_title"), description=description, color=0x000000)


class MMRAmountModal(discord.ui.Modal):
    """Modal pour modifier une valeur MMR."""

    def __init__(self, panel: SubPanel, key: str):
        super().__init__(title=t(panel.gid, "wiz.mmr_edit_title")[:45])
        self.panel = panel
        self.key = key
        self.value = discord.ui.TextInput(
            label=t(panel.gid, "wiz.mmr_new_value")[:45],
            placeholder=t(panel.gid, "wiz.mmr_value_placeholder")[:100],
            required=True,
            max_length=10,
        )
        self.add_item(self.value)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.value.value.strip()
        if not raw.isdigit():
            await interaction.response.send_message(t(self.panel.gid, "wiz.mmr_value_invalid"), ephemeral=True)
            return
        set_mmr_config(self.panel.gid, **{self.key: int(raw)})
        await self.panel.refresh(interaction)


class MMRSettingsPanel(SubPanel):
    """Paramètres MMR : points, durées et rangs."""

    def __init__(self, home: OptionsWizard):
        super().__init__(home)
        self.sync()

    def sync(self) -> None:
        self.clear_items()
        for label_key, row, opener in (
            ("wiz.mmr_params_btn", 0, self._open_mmr_params()),
            ("wiz.mmr_durations_btn", 0, self._open_durations()),
            ("wiz.mmr_ranks_btn", 0, self._open_ranks()),
            ("wiz.mmr_default_ranks_btn", 1, self._reset_ranks()),
        ):
            button = discord.ui.Button(label=t(self.gid, label_key), style=discord.ButtonStyle.secondary, row=row)
            button.callback = opener
            self.add_item(button)
        self.add_back(2)

    def _open_mmr_params(self):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            view = MMRParamsPanel(self.home)
            await interaction.response.edit_message(embed=view.embed(), view=view)
        return callback

    def _open_durations(self):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            view = MMRDurationsPanel(self.home)
            await interaction.response.edit_message(embed=view.embed(), view=view)
        return callback

    def _open_ranks(self):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            view = MMRRanksPanel(self.home)
            await interaction.response.edit_message(embed=view.embed(), view=view)
        return callback

    def _reset_ranks(self):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            set_mmr_config(self.gid, win=15, loss=12, start=1000, mvp_bonus=8)
            await self.refresh(interaction)
        return callback

    def embed(self) -> discord.Embed:
        gid = self.gid
        config = get_mmr_config(gid)
        lines = [
            f"**{t(gid, 'wiz.mmr_params_btn')}**",
            t(gid, "wiz.mmr_line_start", value=config.get("start", 1000)),
            t(gid, "wiz.mmr_line_win", value=config.get("win", 15)),
            t(gid, "wiz.mmr_line_loss", value=config.get("loss", 12)),
            t(gid, "wiz.mmr_line_mvp", value=config.get("mvp_bonus", 8)),
            "",
            f"**{t(gid, 'wiz.mmr_durations_btn')}**",
            t(gid, "wiz.mmr_line_captains_vote", value=config.get("captain_vote_seconds", 60)),
            t(gid, "wiz.mmr_line_mvp_vote", value=config.get("mvp_vote_seconds", 300)),
            t(gid, "wiz.mmr_line_close", value=config.get("cleanup_seconds", 120)),
            "",
            f"**{t(gid, 'wiz.mmr_ranks_btn')}**",
            *_rank_lines(gid, config),
        ]
        return discord.Embed(title=t(gid, "wiz.mmr_other_title"), description="\n".join(lines), color=0x000000)


class MMRParamsPanel(SubPanel):
    """Paramètres MMR : points de départ, victoire, défaite, MVP."""

    def __init__(self, home: OptionsWizard):
        super().__init__(home)
        self.sync()

    def sync(self) -> None:
        self.clear_items()
        config = get_mmr_config(self.gid)
        for key, label_key, default, row in (
            ("start", "wiz.mmr_btn_start", 1000, 0),
            ("win", "wiz.mmr_btn_win", 15, 0),
            ("loss", "wiz.mmr_btn_loss", 12, 1),
            ("mvp_bonus", "wiz.mmr_btn_mvp", 8, 1),
        ):
            button = discord.ui.Button(
                label=t(self.gid, label_key, value=config.get(key, default)),
                style=discord.ButtonStyle.secondary,
                row=row,
            )
            button.callback = self._edit_value(key)
            self.add_item(button)
        self.add_back(2)

    def _edit_value(self, key: str):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            await interaction.response.send_modal(MMRAmountModal(self, key))
        return callback

    def embed(self) -> discord.Embed:
        return discord.Embed(
            title=t(self.gid, "wiz.mmr_params_title"),
            description=t(self.gid, "wiz.mmr_params_desc"),
            color=0x000000,
        )


class MMRDurationsPanel(SubPanel):
    """Durées : vote capitaines, vote MVP, fermeture."""

    def __init__(self, home: OptionsWizard):
        super().__init__(home)
        self.sync()

    def sync(self) -> None:
        self.clear_items()
        config = get_mmr_config(self.gid)
        for key, label_key, default, row in (
            ("captain_vote_seconds", "wiz.mmr_btn_captains_vote", 60, 0),
            ("mvp_vote_seconds", "wiz.mmr_btn_mvp_vote", 300, 0),
            ("cleanup_seconds", "wiz.mmr_btn_close", 120, 1),
        ):
            button = discord.ui.Button(
                label=t(self.gid, label_key, value=config.get(key, default)),
                style=discord.ButtonStyle.secondary,
                row=row,
            )
            button.callback = self._edit_value(key)
            self.add_item(button)
        self.add_back(2)

    def _edit_value(self, key: str):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            await interaction.response.send_modal(MMRAmountModal(self, key))
        return callback

    def embed(self) -> discord.Embed:
        return discord.Embed(
            title=t(self.gid, "wiz.mmr_durations_title"),
            description=t(self.gid, "wiz.mmr_durations_desc"),
            color=0x000000,
        )


class MMRRanksPanel(SubPanel):
    """Configuration des rangs et seuils."""

    def __init__(self, home: OptionsWizard):
        super().__init__(home)
        self.sync()

    def sync(self) -> None:
        self.clear_items()
        config = get_mmr_config(self.gid)
        for i, (key, default, _emoji) in enumerate(RANK_TIERS):
            button = discord.ui.Button(
                label=f"{t(self.gid, f'mmr.tier_{key}')}: {config.get(f'rank_{key}', default)}",
                style=discord.ButtonStyle.secondary,
                row=i // 2,
            )
            button.callback = self._edit_rank(key)
            self.add_item(button)
        self.add_back(3)

    def _edit_rank(self, key: str):
        async def callback(interaction: discord.Interaction) -> None:
            if not await self.guard(interaction):
                return
            await interaction.response.send_modal(MMRAmountModal(self, f"rank_{key}"))
        return callback

    def embed(self) -> discord.Embed:
        config = get_mmr_config(self.gid)
        return discord.Embed(
            title=t(self.gid, "wiz.mmr_ranks_title"),
            description="\n".join(_rank_lines(self.gid, config)),
            color=0x000000,
        )



def done_embed(guild: discord.Guild) -> discord.Embed:
    gid = guild.id
    features = get_features(gid)
    embed = embeds.base(
        gid,
        title=t(gid, "wiz.done_title"),
        description=t(gid, "wiz.done_desc"),
        kind="success",
        footer=t(gid, "wiz.done_footer"),
    )
    embeds.brand(embed, guild)

    lines = []
    for key, _kind, _req in list(WIZARD_SLOTS) + list(OPTIONAL_SLOTS):
        resource = _resolve(guild, key)
        if resource is None:
            continue
        shown = resource.mention if isinstance(resource, discord.TextChannel) else f"**{resource.name}**"
        lines.append(f"{SLOT_EMOJI.get(key, '📁')} {t(gid, f'wiz.slot_{key}')} — {shown}")
    staff = resources.get_role(guild, "role_staff")
    if staff is not None:
        lines.append(f"👑 {t(gid, 'wiz.opt_staff')} — {staff.mention}")
    connexion = resources.get_role(guild, "role_connexion")
    lines.append(
        f"🔓 {t(gid, 'wiz.opt_connexion')} — "
        + (connexion.mention if connexion else t(gid, "wiz.not_set"))
    )
    embeds.section(embed, t(gid, "wiz.done_recap"), "\n".join(lines) or "—")

    embeds.section(
        embed, t(gid, "wiz.done_features"),
        f"{embeds.state(features['leaderboard'])} {t(gid, 'wiz.opt_btn_leaderboard')}"
        + "\n" + f"{embeds.state(features['mvp'])} {t(gid, 'wiz.opt_btn_mmr')}",
    )
    return embed


# ----------------------------------------------------------------------
# Entrée dans l'assistant
# ----------------------------------------------------------------------
async def open_wizard(interaction: discord.Interaction) -> None:
    """Ouvre l'étape qui reste à faire.

    C'est la porte d'entrée des commandes qui exigent une configuration
    complète (`/queue`, `/config`) : elles renvoient ici plutôt que de
    répondre « configure d'abord le bot » sans dire où."""
    guild = interaction.guild
    if guild is None:
        return
    if not channels_ready(guild.id):
        await interaction.response.send_message(
            embed=channels_embed(guild), view=ChannelsWizard(guild), ephemeral=True
        )
        return
    await interaction.response.send_message(
        embed=options_embed(guild), view=OptionsWizard(guild), ephemeral=True
    )


class Wizard(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._restored = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Réactive les menus du message d'arrivée après un redémarrage.

        Sans ça, un serveur qui ajoute le bot le soir et le configure le
        lendemain trouve des menus qui ne répondent plus."""
        if self._restored:
            return
        self._restored = True
        for guild in self.bot.guilds:
            panel = get_setup_panel(guild.id)
            if not panel or queue_ready(guild.id):
                continue
            try:
                view = (ChannelsWizard(guild, intro=True) if not channels_ready(guild.id)
                        else OptionsWizard(guild))
                self.bot.add_view(view, message_id=panel["message_id"])
            except Exception as e:
                log.error(f"Panneau de configuration non restauré sur {guild.name} : {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Désactivé - Le cog welcome gère maintenant l'accueil."""
        # L'accueil est géré par cogs/welcome.py
        pass

    @app_commands.command(
        name="option",
        description="Les réglages facultatifs : rôle organisateur, salons en plus, classement et MVP.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def option(self, interaction: discord.Interaction) -> None:
        """Le panneau des facultatifs, à part et à volonté.

        Les salons obligatoires se désignent une fois, dans le message
        d'arrivée. Tout le reste vit ici : on y revient pour allumer le
        classement un mois plus tard sans retraverser la configuration."""
        guild = interaction.guild
        if guild is None:
            return
        if not channels_ready(guild.id):
            # Pas un cul-de-sac : les menus des salons sont dans le message.
            await interaction.response.send_message(
                embed=channels_embed(guild),
                view=ChannelsWizard(guild),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=options_embed(guild, solo=True),
            view=OptionsWizard(guild, solo=True),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Wizard(bot))
    log.info("Cog Wizard chargé")
