"""
Cog : Poll
==========
Commande : /poll — un sondage à boutons pour trancher avant une queue.

« On joue à quoi ce soir ? », « 21h ou 22h ? » : ces questions se réglaient
avec des réactions sur un message, qu'il fallait compter à la main et que
n'importe qui pouvait fausser en cliquant sur tout.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import custom_emojis
import embeds
import resources
from guild_settings import get_poll, save_poll, delete_poll, get_polls
from i18n import t
from text_safety import NO_PINGS, sanitize

log = logging.getLogger("bot.poll")

MAX_OPTIONS = 5          # une rangée de boutons : au-delà, l'embed devient illisible
MIN_OPTIONS = 2
OPTION_EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪"]

# Une option « Oui » ou « Non », dans l'une des cinq langues, prend l'emoji
# perso du même nom au lieu de sa lettre — s'il a été téléversé (voir
# custom_emojis.py).
YES_WORDS = {"oui", "yes", "si", "sí", "ja", "예", "네"}
NO_WORDS = {"non", "no", "nein", "아니오", "아니요"}


def option_emoji(index: int, option: str) -> str:
    word = option.strip().lower().rstrip("!.?")
    if word in YES_WORDS and custom_emojis.has("yes"):
        return custom_emojis.get("yes")
    if word in NO_WORDS and custom_emojis.has("no"):
        return custom_emojis.get("no")
    return OPTION_EMOJIS[index]


def parse_options(raw: str) -> list[str]:
    """« A | B | C » → ['A', 'B', 'C'], vides et doublons écartés."""
    seen, options = set(), []
    for part in raw.split("|"):
        cleaned = sanitize(part.strip(), 80)
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            options.append(cleaned)
    return options[:MAX_OPTIONS]


def build_poll_embed(guild: discord.Guild, poll: dict) -> discord.Embed:
    """Résultat en direct : barres proportionnelles, gagnant mis en avant."""
    gid = guild.id
    options = poll["options"]
    votes = poll.get("votes", {})
    counts = [0] * len(options)
    for choice in votes.values():
        if 0 <= choice < len(counts):
            counts[choice] += 1
    total = sum(counts)
    best = max(counts) if counts else 0
    closed = poll.get("closed", False)

    embed = embeds.base(
        gid,
        title=f"📊  {poll['question']}",
        kind="gold" if closed else "brand",
        footer=t(gid, "poll.footer_closed" if closed else "poll.footer_open", count=total),
        timestamp=True,
    )
    embeds.brand(embed, guild)

    lines = []
    for i, option in enumerate(options):
        count = counts[i]
        share = (count / total * 100) if total else 0
        # Le gagnant n'est signalé qu'une fois le sondage clos : pendant le
        # vote, une couronne sur le meneur influence les votes suivants.
        lead = "👑 " if closed and count == best and count > 0 else ""
        name = f"{lead}**{option}**" if closed and lead else option
        lines.append(
            f"{option_emoji(i, option)}  {name}\n"
            f"`{share:>3.0f}%`  ·  "
            + t(gid, "poll.votes", count=count)
        )
    embed.description = "\n\n".join(lines)

    author = guild.get_member(poll.get("author_id", 0))
    if author is not None:
        embed.set_author(name=t(gid, "poll.by", name=author.display_name),
                         icon_url=author.display_avatar.url)
    return embed


class PollView(discord.ui.View):
    """Boutons de vote. Reconstruite au démarrage pour chaque sondage ouvert."""

    def __init__(self, cog: "Poll", guild_id: int, message_id: int, options: list[str]):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.message_id = message_id
        for i, option in enumerate(options):
            button = discord.ui.Button(
                label=option[:80],
                emoji=option_emoji(i, option),
                style=discord.ButtonStyle.secondary,
                custom_id=f"cyq:poll:{i}",
                row=0,
            )
            button.callback = self._vote_callback(i)
            self.add_item(button)
        # Pas de bouton « Terminer » : un sondage se clôt avec /endpoll, réservé
        # aux administrateurs.

    def _poll(self) -> dict | None:
        return get_poll(self.guild_id, self.message_id)

    def _vote_callback(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            poll = self._poll()
            if poll is None:
                await interaction.response.send_message(
                    t(self.guild_id, "poll.gone"), ephemeral=True
                )
                return
            if poll.get("closed"):
                await interaction.response.send_message(
                    t(self.guild_id, "poll.already_closed"), ephemeral=True
                )
                return

            votes = poll.setdefault("votes", {})
            key = str(interaction.user.id)
            if votes.get(key) == index:
                # Recliquer sur son propre choix le retire : sans ça, on ne
                # peut jamais annuler un vote donné par erreur.
                del votes[key]
                notice = t(self.guild_id, "poll.vote_removed")
            else:
                votes[key] = index
                notice = t(self.guild_id, "poll.vote_saved", option=poll["options"][index])
            save_poll(self.guild_id, poll)

            await interaction.response.edit_message(
                embed=build_poll_embed(interaction.guild, poll), view=self
            )
            await interaction.followup.send(notice, ephemeral=True)

        return callback

class Poll(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._restored = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Réactive les boutons des sondages encore ouverts."""
        if self._restored:
            return
        self._restored = True
        for guild in self.bot.guilds:
            for poll in get_polls(guild.id):
                if poll.get("closed"):
                    continue
                try:
                    view = PollView(self, guild.id, poll["message_id"], poll["options"])
                    self.bot.add_view(view, message_id=poll["message_id"])
                except Exception as e:
                    log.error(f"Sondage non restauré sur {guild.name} : {e}")
                    continue
                # Le message est redessiné : une mise à jour du bot s'applique
                # aussi aux sondages déjà ouverts.
                channel = guild.get_channel(poll.get("channel_id") or 0)
                if channel is not None:
                    try:
                        await channel.get_partial_message(poll["message_id"]).edit(
                            embed=build_poll_embed(guild, poll), view=view)
                    except discord.HTTPException:
                        pass

    @app_commands.command(name="poll", description="Lance un sondage à boutons (jeu, horaire, format...).")
    @app_commands.describe(
        question="La question posée",
        options="Les choix séparés par | — exemple : Valorant | CS2 | Rocket League",
        salon="Où publier le sondage (ici par défaut)",
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        salon: discord.TextChannel | None = None,
    ) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        if guild is None:
            return

        user = interaction.user
        allowed = isinstance(user, discord.Member) and (
            user.guild_permissions.manage_messages or resources.is_staff(user)
        )
        if not allowed:
            await interaction.response.send_message(t(gid, "poll.staff_only"), ephemeral=True)
            return

        clean_question = sanitize(question.strip(), 200)
        choices = parse_options(options)
        if not clean_question or len(choices) < MIN_OPTIONS:
            await interaction.response.send_message(
                t(gid, "poll.invalid", min=MIN_OPTIONS, max=MAX_OPTIONS), ephemeral=True
            )
            return

        channel = salon or interaction.channel
        me = guild.me
        if me is not None and not channel.permissions_for(me).send_messages:
            await interaction.response.send_message(
                t(gid, "poll.no_access", channel=channel.mention), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        poll = {
            "message_id": 0,
            "channel_id": channel.id,
            "question": clean_question,
            "options": choices,
            "votes": {},
            "author_id": interaction.user.id,
            "closed": False,
        }
        try:
            # Publié avec un embed sans vue : l'identifiant du message n'existe
            # pas encore, et la vue en a besoin pour retrouver son sondage.
            message = await channel.send(embed=build_poll_embed(guild, poll), allowed_mentions=NO_PINGS)
        except discord.HTTPException as e:
            log.error(f"Sondage non publié dans {guild.name} : {e}")
            await interaction.followup.send(t(gid, "poll.failed"), ephemeral=True)
            return

        poll["message_id"] = message.id
        save_poll(gid, poll)
        view = PollView(self, gid, message.id, choices)
        try:
            await message.edit(view=view)
            self.bot.add_view(view, message_id=message.id)
        except discord.HTTPException as e:
            log.error(f"Boutons du sondage non attachés : {e}")
            delete_poll(gid, message.id)
            await interaction.followup.send(t(gid, "poll.failed"), ephemeral=True)
            return

        await interaction.followup.send(
            t(gid, "poll.created", link=message.jump_url), ephemeral=True
        )

    async def open_poll_choices(self, interaction: discord.Interaction,
                                current: str) -> list[app_commands.Choice[str]]:
        """Les sondages encore ouverts du serveur, les plus récents d'abord."""
        gid = interaction.guild_id
        if gid is None:
            return []
        wanted = current.casefold()
        polls = [poll for poll in reversed(get_polls(gid))
                 if not poll.get("closed") and wanted in poll.get("question", "").casefold()]
        return [app_commands.Choice(name=poll["question"][:100], value=str(poll["message_id"]))
                for poll in polls[:25]]

    @app_commands.command(name="endpoll", description="Termine un sondage et affiche le résultat (administrateurs).")
    @app_commands.describe(sondage="Le sondage à terminer")
    @app_commands.autocomplete(sondage=open_poll_choices)
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def endpoll(self, interaction: discord.Interaction, sondage: str) -> None:
        gid = interaction.guild_id
        guild = interaction.guild
        if guild is None:
            return
        poll = get_poll(gid, int(sondage)) if sondage.isdigit() else None
        if poll is None:
            await interaction.response.send_message(t(gid, "poll.gone"), ephemeral=True)
            return
        if poll.get("closed"):
            await interaction.response.send_message(t(gid, "poll.already_closed"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        poll["closed"] = True
        save_poll(gid, poll)
        channel_id = poll.get("channel_id") or 0
        channel = guild.get_channel(channel_id)
        if channel is not None:
            try:
                # Résultat final avec le gagnant, et plus aucun bouton de vote.
                await channel.get_partial_message(poll["message_id"]).edit(
                    embed=build_poll_embed(guild, poll), view=None)
            except discord.HTTPException as e:
                log.warning(f"[{guild.name}] Sondage clos mais message non mis à jour : {e}")
        link = f"https://discord.com/channels/{gid}/{channel_id}/{poll['message_id']}"
        await interaction.followup.send(t(gid, "poll.ended", link=link), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Poll(bot))
    log.info("Cog Poll chargé")
