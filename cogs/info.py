"""
Cog : Info
==========
Commandes : /userinfo, /serverinfo
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import embeds
from i18n import t

log = logging.getLogger("bot.info")


class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="Affiche les informations d'un membre.")
    @app_commands.describe(membre="Le membre à consulter (toi par défaut)")
    async def userinfo(self, interaction: discord.Interaction, membre: discord.Member | None = None):
        gid = interaction.guild_id
        target = membre or interaction.user
        if not isinstance(target, discord.Member):
            await interaction.response.send_message(t(gid, "common.members_only"), ephemeral=True)
            return

        roles = [r.mention for r in reversed(target.roles) if not r.is_default()]
        roles_text = " ".join(roles[:15]) if roles else t(gid, "info.no_roles")

        embed = embeds.base(
            gid,
            title=t(gid, "info.userinfo_title", name=target.display_name),
            description=f"{target.mention}  ·  `{target.id}`",
            timestamp=True,
        )
        # La couleur du rôle le plus haut : l'embed reprend l'identité du
        # membre au lieu d'être bleu comme tous les autres.
        if target.color.value:
            embed.color = target.color
        embed.set_thumbnail(url=target.display_avatar.url)
        embeds.brand(embed, interaction.guild)

        created_ts = int(target.created_at.timestamp())
        embed.add_field(
            name=t(gid, "info.field_created"),
            value=f"<t:{created_ts}:D>\n<t:{created_ts}:R>",
            inline=True,
        )
        if target.joined_at:
            joined_ts = int(target.joined_at.timestamp())
            embed.add_field(
                name=t(gid, "info.field_joined"),
                value=f"<t:{joined_ts}:D>\n<t:{joined_ts}:R>",
                inline=True,
            )
        embed.add_field(
            name=t(gid, "info.field_nickname"),
            value=f"**{target.nick}**" if target.nick else "—",
            inline=True,
        )
        embeds.section(embed, t(gid, "info.field_roles", count=len(roles)), roles_text)

        badges = []
        if target.bot:
            badges.append("🤖 " + t(gid, "info.field_bot"))
        if target.premium_since:
            badges.append(f"💎 <t:{int(target.premium_since.timestamp())}:D>")
        if badges:
            embeds.section(embed, t(gid, "info.field_badges"), "  ·  ".join(badges))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Affiche les informations du serveur.")
    async def serverinfo(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(t(gid, "common.members_only"), ephemeral=True)
            return

        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)

        embed = embeds.base(
            gid,
            title=guild.name,
            description=f"👑  {guild.owner.mention if guild.owner else '—'}"
                        f"  ·  📅 <t:{int(guild.created_at.timestamp())}:D>\n{embeds.RULE}",
            timestamp=True,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)
        embeds.brand(embed, guild)

        embed.add_field(
            name=t(gid, "info.field_members"),
            value=t(gid, "info.members_breakdown", total=guild.member_count, humans=humans, bots=bots),
            inline=True,
        )
        embed.add_field(
            name=t(gid, "info.field_channels"),
            value=t(gid, "info.channels_breakdown", text=len(guild.text_channels), voice=len(guild.voice_channels)),
            inline=True,
        )
        embeds.stat(embed, t(gid, "info.field_roles_count"), len(guild.roles))
        embed.add_field(
            name=t(gid, "info.field_boosts"),
            value=t(gid, "info.boosts_value", count=guild.premium_subscription_count, tier=guild.premium_tier),
            inline=True,
        )
        embeds.align(embed)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
    log.info("Cog Info chargé")
