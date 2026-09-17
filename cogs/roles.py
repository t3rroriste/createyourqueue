"""
Cog : Reaction Roles personnalisables
======================================
Commandes : /rolepanel (construction), /roles (publication), /queuerole

Chaque serveur compose ses panneaux : titre, description, couleur, pied de
page et liste des rôles proposés, jusqu'à 2 panneaux par serveur.
"""

from __future__ import annotations

import asyncio
import logging
import re

import discord
from discord import app_commands

import custom_emojis
from discord.ext import commands

from config import COLOR_SUCCESS, COLOR_ERROR
import embeds
import resources
from guild_settings import (
    MAX_ROLE_PANELS,
    MAX_ROLES_PER_PANEL,
    get_role_panels,
    get_role_panel,
    save_role_panel,
    delete_role_panel,
    next_role_panel_id,
)
from i18n import t
from text_safety import NO_PINGS, sanitize

log = logging.getLogger("bot.roles")

# Permissions qui font d'un rôle une cible d'élévation de privilèges : un rôle
# qui en porte au moins une ne doit jamais être auto-attribuable.
DANGEROUS_PERMISSIONS = (
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
    "ban_members",
    "kick_members",
    "moderate_members",
    "manage_messages",
    "manage_nicknames",
    "mention_everyone",
    "manage_events",
    "manage_threads",
    "view_audit_log",
)

CUSTOM_ID_RE = re.compile(r"^cyq:rp:(\d+):(\d+)$")

BUTTON_STYLES = {
    "grey": discord.ButtonStyle.secondary,
    "blue": discord.ButtonStyle.primary,
    "green": discord.ButtonStyle.success,
    "red": discord.ButtonStyle.danger,
}

PANEL_COLORS = [
    ("⚫", "black", 0x010101),
    ("🔵", "blue", 0x3498DB),
    ("🟢", "green", 0x2ECC71),
    ("🔴", "red", 0xE74C3C),
    ("🟣", "purple", 0x9B59B6),
    ("🟡", "gold", 0xF1C40F),
]

# Limites Discord, appliquées à la saisie utilisateur avant tout envoi.
MAX_TITLE = 256
MAX_DESCRIPTION = 4000
MAX_FOOTER = 2048
MAX_LABEL = 80

_member_locks: dict[tuple[int, int], asyncio.Lock] = {}


def _member_lock(guild_id: int, user_id: int) -> asyncio.Lock:
    key = (guild_id, user_id)
    lock = _member_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _member_locks[key] = lock
    return lock


def role_is_dangerous(role: discord.Role) -> bool:
    return any(getattr(role.permissions, perm, False) for perm in DANGEROUS_PERMISSIONS)


def validate_role_for_panel(
    role: discord.Role,
    invoker: discord.Member,
    me: discord.Member,
) -> str | None:
    """Retourne la clé i18n d'une erreur, ou None si le rôle est acceptable."""
    if role.is_default():
        return "roles.err_everyone"
    if role.managed:
        return "roles.err_managed"
    if role_is_dangerous(role):
        return "roles.err_dangerous"
    if role >= me.top_role:
        return "roles.err_above_bot"
    # Le propriétaire du serveur n'est pas contraint par la hiérarchie.
    if invoker.id != invoker.guild.owner_id and role >= invoker.top_role:
        return "roles.err_above_you"
    return None


def assign_is_still_safe(role: discord.Role, me: discord.Member) -> bool:
    """Revalidation au moment du clic : un rôle stocké dans un panneau a pu
    gagner des permissions depuis, ou passer au-dessus du bot."""
    return (
        not role.is_default()
        and not role.managed
        and not role_is_dangerous(role)
        and role < me.top_role
    )


def build_panel_embed(guild: discord.Guild, panel: dict) -> discord.Embed:
    embed = discord.Embed(
        title=sanitize(panel.get("title") or t(guild.id, "roles.default_title"), MAX_TITLE),
        description=sanitize(panel.get("description") or "", MAX_DESCRIPTION) or None,
        color=panel.get("color", 0x010101),
    )
    footer = panel.get("footer")
    if footer:
        embed.set_footer(text=sanitize(footer, MAX_FOOTER))
    return embed


class RolePanelView(discord.ui.View):
    """Vue publiée : un bouton par rôle. Persistante (custom_id stable), donc
    toujours fonctionnelle après un redémarrage du bot."""

    def __init__(self, panel: dict):
        super().__init__(timeout=None)
        panel_id = panel.get("id", 0)
        for index, entry in enumerate(panel.get("roles", [])[:MAX_ROLES_PER_PANEL]):
            self.add_item(
                discord.ui.Button(
                    label=sanitize(entry.get("label") or "Role", MAX_LABEL),
                    # Le 🔔 du panneau Notif Queue prend l'emoji perso s'il a
                    # été téléversé : les panneaux déjà publiés en profitent
                    # aussi, sans rien réenregistrer.
                    emoji=(custom_emojis.get("discord_notification_settings_d")
                           if entry.get("emoji") == "🔔" else entry.get("emoji") or None),
                    style=BUTTON_STYLES.get(entry.get("style", "grey"), discord.ButtonStyle.secondary),
                    custom_id=f"cyq:rp:{panel_id}:{entry['role_id']}",
                    row=index // 5,
                )
            )


class PanelBuilderView(discord.ui.View):
    """Interface de configuration d'un panneau (éphémère, réservée au staff)."""

    def __init__(self, cog: "Roles", guild: discord.Guild, panel: dict, author_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.panel = panel
        self.author_id = author_id
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        gid = self.guild.id
        self.btn_title.label = t(gid, "roles.btn_title")
        self.btn_description.label = t(gid, "roles.btn_description")
        self.btn_color.label = t(gid, "roles.btn_color")
        self.btn_footer.label = t(gid, "roles.btn_footer")
        self.btn_add_role.label = t(gid, "roles.btn_add_role")
        self.btn_remove_role.label = t(gid, "roles.btn_remove_role")
        self.btn_publish.label = t(gid, "roles.btn_publish")
        self.btn_delete.label = t(gid, "roles.btn_delete")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Un panneau éphémère reste cliquable par son destinataire uniquement,
        mais on revérifie aussi la permission : elle a pu être retirée depuis
        l'ouverture du menu."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                t(self.guild.id, "roles.err_not_yours"), ephemeral=True
            )
            return False
        if not self.cog.can_manage(interaction.user):
            await interaction.response.send_message(
                t(self.guild.id, "roles.error_permission"), ephemeral=True
            )
            return False
        return True

    def content(self) -> str:
        gid = self.guild.id
        lines = [
            t(gid, "roles.builder_header", id=self.panel.get("id", "?")),
            t(gid, "roles.builder_title", value=self.panel.get("title") or "—"),
            t(gid, "roles.builder_description", value=(self.panel.get("description") or "—")[:80]),
            t(gid, "roles.builder_footer", value=self.panel.get("footer") or "—"),
        ]
        entries = self.panel.get("roles", [])
        if entries:
            listed = "\n".join(
                f"{e.get('emoji') or '•'} <@&{e['role_id']}> — `{e.get('label')}`" for e in entries
            )
            lines.append(t(gid, "roles.builder_roles", count=len(entries), max=MAX_ROLES_PER_PANEL))
            lines.append(listed)
        else:
            lines.append(t(gid, "roles.builder_no_roles"))
        return "\n".join(lines)

    async def refresh(self, interaction: discord.Interaction, notice: str = "") -> None:
        save_role_panel(self.guild.id, self.panel)
        body = (notice + "\n\n" if notice else "") + self.content()
        await interaction.response.edit_message(content=body, embed=build_panel_embed(self.guild, self.panel), view=self)

    # -- Champs texte ---------------------------------------------------
    async def _text_modal(self, interaction: discord.Interaction, field: str, limit: int, title_key: str) -> None:
        gid = self.guild.id
        modal = discord.ui.Modal(title=t(gid, title_key))
        text_input = discord.ui.TextInput(
            label=t(gid, title_key),
            default=self.panel.get(field) or "",
            required=False,
            max_length=min(limit, 4000),
            style=discord.TextStyle.paragraph if limit > 256 else discord.TextStyle.short,
        )
        modal.add_item(text_input)

        async def on_submit(modal_interaction: discord.Interaction) -> None:
            self.panel[field] = sanitize(text_input.value.strip(), limit)
            await self.refresh(modal_interaction, t(gid, "roles.updated"))

        modal.on_submit = on_submit  # type: ignore[method-assign]
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Titre", style=discord.ButtonStyle.secondary, emoji="📛", row=0)
    async def btn_title(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._text_modal(interaction, "title", MAX_TITLE, "roles.btn_title")

    @discord.ui.button(label="Description", style=discord.ButtonStyle.secondary, emoji="📝", row=0)
    async def btn_description(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._text_modal(interaction, "description", MAX_DESCRIPTION, "roles.btn_description")

    @discord.ui.button(label="Pied de page", style=discord.ButtonStyle.secondary, emoji="🔖", row=0)
    async def btn_footer(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._text_modal(interaction, "footer", MAX_FOOTER, "roles.btn_footer")

    @discord.ui.button(label="Couleur", style=discord.ButtonStyle.secondary, emoji="🎨", row=1)
    async def btn_color(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        gid = self.guild.id
        select = discord.ui.Select(
            placeholder=t(gid, "roles.color_placeholder"),
            options=[
                discord.SelectOption(label=t(gid, f"roles.color_{name}"), emoji=emoji, value=str(value))
                for emoji, name, value in PANEL_COLORS
            ],
        )

        async def callback(select_interaction: discord.Interaction) -> None:
            self.panel["color"] = int(select.values[0])
            await self.refresh(select_interaction, t(gid, "roles.updated"))

        select.callback = callback  # type: ignore[method-assign]
        view = discord.ui.View(timeout=300)
        view.add_item(select)
        await interaction.response.send_message(view=view, ephemeral=True)

    # -- Rôles ----------------------------------------------------------
    @discord.ui.button(label="Ajouter un rôle", style=discord.ButtonStyle.success, emoji="➕", row=1)
    async def btn_add_role(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        gid = self.guild.id
        if len(self.panel.get("roles", [])) >= MAX_ROLES_PER_PANEL:
            await interaction.response.send_message(
                t(gid, "roles.err_role_limit", max=MAX_ROLES_PER_PANEL), ephemeral=True
            )
            return

        role_select = discord.ui.RoleSelect(placeholder=t(gid, "roles.role_placeholder"))

        async def callback(select_interaction: discord.Interaction) -> None:
            role = role_select.values[0]
            member = select_interaction.user
            me = self.guild.me
            if not isinstance(member, discord.Member) or me is None:
                return

            error_key = validate_role_for_panel(role, member, me)
            if error_key:
                await select_interaction.response.send_message(
                    t(gid, error_key, role=role.name), ephemeral=True
                )
                return
            if any(e["role_id"] == role.id for e in self.panel.get("roles", [])):
                await select_interaction.response.send_message(
                    t(gid, "roles.err_duplicate", role=role.name), ephemeral=True
                )
                return

            self.panel.setdefault("roles", []).append(
                {"role_id": role.id, "label": sanitize(role.name, MAX_LABEL), "emoji": None, "style": "grey"}
            )
            save_role_panel(self.guild.id, self.panel)
            await select_interaction.response.edit_message(
                content=t(gid, "roles.role_added_panel", role=role.name), view=None
            )

        role_select.callback = callback  # type: ignore[method-assign]
        view = discord.ui.View(timeout=300)
        view.add_item(role_select)
        await interaction.response.send_message(view=view, ephemeral=True)

    @discord.ui.button(label="Retirer un rôle", style=discord.ButtonStyle.danger, emoji="➖", row=1)
    async def btn_remove_role(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        gid = self.guild.id
        entries = self.panel.get("roles", [])
        if not entries:
            await interaction.response.send_message(t(gid, "roles.builder_no_roles"), ephemeral=True)
            return

        select = discord.ui.Select(
            placeholder=t(gid, "roles.remove_placeholder"),
            options=[
                discord.SelectOption(label=e.get("label", str(e["role_id"]))[:100], value=str(e["role_id"]))
                for e in entries[:25]
            ],
        )

        async def callback(select_interaction: discord.Interaction) -> None:
            role_id = int(select.values[0])
            self.panel["roles"] = [e for e in self.panel.get("roles", []) if e["role_id"] != role_id]
            save_role_panel(self.guild.id, self.panel)
            await select_interaction.response.edit_message(content=t(gid, "roles.role_removed_panel"), view=None)

        select.callback = callback  # type: ignore[method-assign]
        view = discord.ui.View(timeout=300)
        view.add_item(select)
        await interaction.response.send_message(view=view, ephemeral=True)

    # -- Publication / suppression --------------------------------------
    @discord.ui.button(label="Publier", style=discord.ButtonStyle.primary, emoji="📢", row=2)
    async def btn_publish(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        gid = self.guild.id
        if not self.panel.get("roles"):
            await interaction.response.send_message(t(gid, "roles.err_publish_empty"), ephemeral=True)
            return

        channel_select = discord.ui.ChannelSelect(
            placeholder=t(gid, "roles.channel_placeholder"),
            channel_types=[discord.ChannelType.text],
        )

        async def callback(select_interaction: discord.Interaction) -> None:
            channel = self.guild.get_channel(channel_select.values[0].id)
            if not isinstance(channel, discord.TextChannel):
                await select_interaction.response.send_message(
                    t(gid, "common.text_channel_only"), ephemeral=True
                )
                return

            me = self.guild.me
            perms = channel.permissions_for(me) if me else None
            if not perms or not (perms.send_messages and perms.embed_links):
                await select_interaction.response.send_message(
                    t(gid, "roles.err_channel_perms", channel=channel.mention), ephemeral=True
                )
                return

            try:
                message = await channel.send(
                    embed=build_panel_embed(self.guild, self.panel),
                    view=RolePanelView(self.panel),
                    allowed_mentions=NO_PINGS,
                )
            except discord.HTTPException as e:
                log.error(f"Publication du panneau de rôles impossible : {e}")
                await select_interaction.response.send_message(
                    t(gid, "roles.err_publish_failed"), ephemeral=True
                )
                return

            self.panel["message_id"] = message.id
            self.panel["channel_id"] = channel.id
            save_role_panel(self.guild.id, self.panel)
            self.cog.register_panel_view(self.panel)
            await select_interaction.response.edit_message(
                content=t(gid, "roles.published", channel=channel.mention), view=None
            )

        channel_select.callback = callback  # type: ignore[method-assign]
        view = discord.ui.View(timeout=300)
        view.add_item(channel_select)
        await interaction.response.send_message(view=view, ephemeral=True)

    @discord.ui.button(label="Supprimer le panneau", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
    async def btn_delete(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        gid = self.guild.id
        delete_role_panel(gid, self.panel.get("id", 0))
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=t(gid, "roles.panel_deleted"), embed=None, view=self
        )


class Roles(commands.Cog):
    # Groupe : /roles panel (configurer), /roles post (publier), /roles notif
    roles = app_commands.Group(name="roles", description="Panneaux de rôles à cliquer.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def can_manage(self, user: discord.abc.User) -> bool:
        """Configurer un panneau de rôles revient à distribuer des rôles :
        on exige la permission Gérer les rôles, pas seulement le rôle staff."""
        return isinstance(user, discord.Member) and user.guild_permissions.manage_roles

    def register_panel_view(self, panel: dict) -> None:
        if panel.get("message_id"):
            self.bot.add_view(RolePanelView(panel), message_id=panel["message_id"])

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Réattache les vues des panneaux publiés (sinon leurs boutons ne
        répondent plus après un redémarrage)."""
        for guild in self.bot.guilds:
            for panel in get_role_panels(guild.id):
                self.register_panel_view(panel)

    # ------------------------------------------------------------------
    # Clic sur un bouton de panneau
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        match = CUSTOM_ID_RE.match(custom_id)
        if not match:
            return
        await self.handle_role_click(interaction, int(match.group(1)), int(match.group(2)))

    async def handle_role_click(self, interaction: discord.Interaction, panel_id: int, role_id: int) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return
        gid = guild.id

        # Le panneau doit exister ET appartenir à ce serveur : un custom_id
        # recopié depuis un autre serveur ne doit rien déclencher ici.
        panel = get_role_panel(gid, panel_id)
        if panel is None or not any(e["role_id"] == role_id for e in panel.get("roles", [])):
            await interaction.response.send_message(t(gid, "roles.err_panel_gone"), ephemeral=True)
            return

        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(t(gid, "roles.err_role_gone"), ephemeral=True)
            return

        me = guild.me
        if me is None or not me.guild_permissions.manage_roles:
            await interaction.response.send_message(t(gid, "roles.err_bot_perms"), ephemeral=True)
            return

        # Revalidation : le rôle a pu devenir dangereux depuis sa mise au panneau.
        if not assign_is_still_safe(role, me):
            log.warning(
                f"Panneau de rôles : attribution refusée pour '{role.name}' sur {guild.name} "
                f"(permissions sensibles, rôle géré, ou au-dessus du bot)."
            )
            await interaction.response.send_message(t(gid, "roles.err_now_unsafe"), ephemeral=True)
            return

        # Verrou par membre : deux clics rapides ne doivent pas se marcher dessus.
        async with _member_lock(gid, member.id):
            try:
                if role in member.roles:
                    await member.remove_roles(role, reason="Panneau de rôles")
                    key, color = "roles.role_removed", COLOR_ERROR
                else:
                    await member.add_roles(role, reason="Panneau de rôles")
                    key, color = "roles.role_added", COLOR_SUCCESS
            except discord.Forbidden:
                await interaction.response.send_message(t(gid, "roles.error_hierarchy"), ephemeral=True)
                return
            except discord.HTTPException as e:
                log.error(f"Erreur d'attribution de rôle : {e}")
                await interaction.response.send_message(t(gid, "roles.err_generic"), ephemeral=True)
                return

        await interaction.response.send_message(
            embed=discord.Embed(description=t(gid, key, role=role.mention), color=color),
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # Commandes
    # ------------------------------------------------------------------
    @roles.command(name="panel", description="Crée et personnalise un panneau de rôles (2 maximum).")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def panel(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return
        gid = guild.id

        panels = get_role_panels(gid)
        options = [
            discord.SelectOption(
                label=t(gid, "roles.select_existing", id=p.get("id"), title=(p.get("title") or "—")[:40]),
                value=str(p.get("id")),
            )
            for p in panels
        ]
        if len(panels) < MAX_ROLE_PANELS:
            options.append(discord.SelectOption(label=t(gid, "roles.select_new"), emoji="➕", value="new"))

        select = discord.ui.Select(placeholder=t(gid, "roles.select_placeholder"), options=options)

        async def callback(select_interaction: discord.Interaction) -> None:
            choice = select.values[0]
            if choice == "new":
                panel_id = next_role_panel_id(gid)
                if panel_id == 0:
                    await select_interaction.response.send_message(
                        t(gid, "roles.err_panel_limit", max=MAX_ROLE_PANELS), ephemeral=True
                    )
                    return
                panel = {
                    "id": panel_id,
                    "title": t(gid, "roles.default_title"),
                    "description": "",
                    "footer": "",
                    "color": 0x010101,
                    "roles": [],
                    "message_id": None,
                    "channel_id": None,
                }
                try:
                    save_role_panel(gid, panel)
                except ValueError:
                    await select_interaction.response.send_message(
                        t(gid, "roles.err_panel_limit", max=MAX_ROLE_PANELS), ephemeral=True
                    )
                    return
            else:
                panel = get_role_panel(gid, int(choice))
                if panel is None:
                    await select_interaction.response.send_message(t(gid, "roles.err_panel_gone"), ephemeral=True)
                    return

            builder = PanelBuilderView(self, guild, panel, interaction.user.id)
            await select_interaction.response.edit_message(
                content=builder.content(), embed=build_panel_embed(guild, panel), view=builder
            )

        select.callback = callback  # type: ignore[method-assign]
        view = discord.ui.View(timeout=300)
        view.add_item(select)
        await interaction.response.send_message(view=view, ephemeral=True)

    @roles.command(name="post", description="Republie les panneaux de rôles configurés ici.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def post(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        gid = interaction.guild_id or 0
        if guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=discord.Embed(description=t(gid, "common.text_channel_only"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        panels = [p for p in get_role_panels(gid) if p.get("roles")]
        if not panels:
            await interaction.response.send_message(
                embed=discord.Embed(description=t(gid, "roles.err_no_panel"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        for panel in panels:
            message = await interaction.channel.send(
                embed=build_panel_embed(guild, panel),
                view=RolePanelView(panel),
                allowed_mentions=NO_PINGS,
            )
            panel["message_id"] = message.id
            panel["channel_id"] = interaction.channel.id
            save_role_panel(gid, panel)
            self.register_panel_view(panel)

        await interaction.followup.send(
            embed=discord.Embed(description=t(gid, "roles.published_count", count=len(panels)), color=COLOR_SUCCESS),
            ephemeral=True,
        )

    @roles.command(name="notif", description="Publie le panneau pour être notifié en MP des queues.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def notif(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        gid = interaction.guild_id or 0
        if guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=discord.Embed(description=t(gid, "common.text_channel_only"), color=COLOR_ERROR),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        # Rôle **désigné**, jamais créé : le bot n'ajoute pas de rôle au
        # serveur sans qu'on le lui demande.
        role = resources.get_role(guild, "role_queue_notif")
        if role is None:
            await interaction.followup.send(
                embed=embeds.base(gid, kind="error", description=t(gid, "roles.err_no_notif_role")),
                ephemeral=True,
            )
            return

        # Panneau intégré, stocké hors des 2 panneaux personnalisés pour ne pas
        # consommer un des emplacements du serveur.
        panel = {
            "id": 0,
            "title": t(gid, "roles.notif_title"),
            "description": t(gid, "roles.notif_description"),
            "footer": t(gid, "roles.notif_footer"),
            "color": 0x010101,
            "roles": [{"role_id": role.id, "label": t(gid, "roles.notif_button"), "emoji": "🔔", "style": "grey"}],
        }
        await interaction.channel.send(
            embed=build_panel_embed(guild, panel),
            view=RolePanelView(panel),
            allowed_mentions=NO_PINGS,
        )
        await interaction.followup.send(
            embed=discord.Embed(description=t(gid, "roles.published_notif"), color=COLOR_SUCCESS),
            ephemeral=True,
        )

    @panel.error
    @post.error
    @notif.error
    async def roles_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            gid = interaction.guild_id or 0
            embed = discord.Embed(description=t(gid, "roles.error_permission"), color=COLOR_ERROR)
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            log.exception("Erreur cog roles", exc_info=error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
