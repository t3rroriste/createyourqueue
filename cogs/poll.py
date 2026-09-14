"""
Cog : Poll
==========
Commande : /poll — un sondage à boutons pour trancher avant une queue.

« On joue à quoi ce soir ? », « 21h ou 22h ? » : ces questions se réglaient
avec des réactions sur un message, qu'il fallait compter à la main et que
n'importe qui pouvait fausser en cliquant sur tout.

Ici, chaque option est un bouton, **une voix par personne** (changeable), et
le résultat se met à jour tout seul sous les yeux de tout le monde.

Points d'attention
------------------
- **Le sondage survit à un redémarrage.** Les votes sont enregistrés à chaque
  clic et les boutons sont réattachés au démarrage : un sondage lancé le soir
  fonctionne encore le lendemain.
- **Les identifiants de bouton sont stables** (`cyq:poll:0`… `cyq:poll:4`).
  discord.py refuse d'enregistrer une vue persistante dont un bouton a un
  identifiant tiré au hasard — c'est ce qui l'empêchait de repartir.
- **La question et les options sont du texte de membre** : elles passent par
  `sanitize`, sinon un `@everyone` dans une option pingue tout le serveur à
  chaque affichage.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import embeds
import resources
from guild_settings import get_poll, save_poll, delete_poll, get_polls
from i18n import t
from text_safety import NO_PINGS, sanitize

log = logging.getLogger("bot.poll")

MAX_OPTIONS = 5          # une rangée de boutons : au-delà, l'embed devient illisible
MIN_OPTIONS = 2
OPTION_EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪"]


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
            f"{OPTION_EMOJIS[i]}  {name}\n"
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
                emoji=OPTION_EMOJIS[i],
                style=discord.ButtonStyle.secondary,
                custom_id=f"cyq:poll:{i}",
                row=0,
            )
            button.callback = self._vote_callback(i)
            self.add_item(button)

        close = discord.ui.Button(
            label=t(guild_id, "poll.btn_close"),
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id="cyq:poll:close",
            row=1,
        )
        close.callback = self._close_callback
        self.add_item(close)

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

    async def _close_callback(self, interaction: discord.Interaction) -> None:
        poll = self._poll()
        if poll is None:
            await interaction.response.send_message(t(self.guild_id, "poll.gone"), ephemeral=True)
            return

        user = interaction.user
        allowed = user.id == poll.get("author_id") or (
            isinstance(user, discord.Member)
            and (user.guild_permissions.manage_messages or resources.is_staff(user))
        )
        if not allowed:
            await interaction.response.send_message(t(self.guild_id, "poll.close_denied"), ephemeral=True)
            return
        if poll.get("closed"):
            await interaction.response.send_message(t(self.guild_id, "poll.already_closed"), ephemeral=True)
            return

        poll["closed"] = True
        save_poll(self.guild_id, poll)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=build_poll_embed(interaction.guild, poll), view=self
        )


class Poll(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._restored = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Réactive les boutons des sondages encore ouverts.

        Une vue échoue parfois seule (message supprimé, options corrompues) :
        chacune est réattachée dans son propre try, sinon un sondage cassé
        empêcherait tous les suivants de repartir."""
        if self._restored:
            return
        self._restored = True
        for guild in self.bot.guilds:
            for poll in get_polls(guild.id):
                if poll.get("closed"):
                    continue
                try:
                    self.bot.add_view(
                        PollView(self, guild.id, poll["message_id"], poll["options"]),
                        message_id=poll["message_id"],
                    )
                except Exception as e:
                    log.error(f"Sondage non restauré sur {guild.name} : {e}")

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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Poll(bot))
    log.info("Cog Poll chargé")
