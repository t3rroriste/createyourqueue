"""
Cog : Match
===========
Salon de match privé, capitaines, vote du MVP et MMR.
Commande : /mmr (panneau de configuration)

Déroulé d'une partie
--------------------
1. L'organisateur clique « Lancer la partie ».
2. Le bot crée un **salon texte privé**, visible uniquement des joueurs de la
   queue et du staff.
3. **Mode capitaines** (activable) : les joueurs votent pour leurs capitaines
   dans ce salon. Les deux plus votés se partagent ensuite les joueurs à tour
   de rôle. Sans ce mode, les équipes sont réparties automatiquement selon le
   niveau, comme avant.
4. La partie démarre : chaque joueur reçoit un **rôle temporaire à la couleur
   de son équipe**, les salons vocaux sont créés, et le salon de match passe
   en lecture seule.
5. À la fin, le salon se rouvre et un **vote du MVP** démarre (5 minutes par
   défaut). Le MMR est appliqué à la clôture du vote.
6. Deux minutes plus tard, **tout est supprimé** : salon de match, rôles
   d'équipe, salons vocaux.

Pourquoi une boucle et pas des `sleep`
--------------------------------------
Les échéances (fin du vote, nettoyage) sont **enregistrées sur disque** et
relues par une boucle toutes les 15 secondes. Un `asyncio.sleep(300)` meurt
avec le processus : un redémarrage pendant un vote laissait un salon privé et
des rôles orphelins que plus personne ne nettoyait.
"""

from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

import embeds
import mmr
import resources
from guild_settings import (
    get_mmr_config, set_mmr_config,
    get_player_mmr, set_player_mmr,
    deferred_save,
    get_match_state, set_match_state,
)
from i18n import t
from rate_limit import throttled_each
from text_safety import NO_PINGS, USERS_ONLY, sanitize

log = logging.getLogger("bot.match")

TICK_SECONDS = 15

# Phases d'un match, dans l'ordre.
PHASE_CAPTAINS = "captains"   # vote des capitaines
PHASE_DRAFT = "draft"         # les capitaines choisissent
PHASE_LIVE = "live"           # partie en cours, salon verrouillé
PHASE_MVP = "mvp"             # vote du meilleur joueur
PHASE_CLOSING = "closing"     # compte à rebours avant suppression

MAX_VOTE_OPTIONS = 25         # limite d'un menu déroulant Discord


def now() -> int:
    return int(time.time())


def tiers_of(guild_id: int, config: dict) -> list[dict]:
    """Paliers configurés, ou les paliers par défaut traduits."""
    return config.get("tiers") or mmr.default_tiers(guild_id)


# ----------------------------------------------------------------------
# Votes (capitaines, MVP)
# ----------------------------------------------------------------------
class VoteView(discord.ui.View):
    """Menu de vote réservé aux joueurs du match.

    Un seul vote par personne, modifiable. On ne peut pas voter pour
    soi-même : sans cette règle, le MVP se réduit à qui clique le plus vite
    sur son propre nom."""

    def __init__(self, cog: "Match", guild_id: int, kind: str, candidates: list[tuple[int, str]]):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.kind = kind
        select = discord.ui.Select(
            placeholder=t(guild_id, f"match.{kind}_pick"),
            options=[
                discord.SelectOption(label=name[:100], value=str(uid))
                for uid, name in candidates[:MAX_VOTE_OPTIONS]
            ],
            custom_id=f"cyq:match:{kind}",
        )
        select.callback = self._vote
        self.add_item(select)
        self._select = select

    async def _vote(self, interaction: discord.Interaction) -> None:
        gid = self.guild_id
        state = get_match_state(gid)
        if not state or state.get("phase") != self.kind:
            await interaction.response.send_message(t(gid, "match.vote_closed"), ephemeral=True)
            return
        if interaction.user.id not in state.get("players", []):
            await interaction.response.send_message(t(gid, "match.vote_not_player"), ephemeral=True)
            return

        choice = int(self._select.values[0])
        if choice == interaction.user.id:
            await interaction.response.send_message(t(gid, "match.vote_not_self"), ephemeral=True)
            return

        state.setdefault("votes", {})[str(interaction.user.id)] = choice
        set_match_state(gid, state)
        await interaction.response.send_message(
            t(gid, "match.vote_saved", player=f"<@{choice}>"), ephemeral=True
        )


class DraftView(discord.ui.View):
    """Sélection d'un joueur par le capitaine dont c'est le tour."""

    def __init__(self, cog: "Match", guild_id: int, available: list[tuple[int, str]]):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        select = discord.ui.Select(
            placeholder=t(guild_id, "match.draft_pick"),
            options=[
                discord.SelectOption(label=name[:100], value=str(uid))
                for uid, name in available[:MAX_VOTE_OPTIONS]
            ],
            custom_id="cyq:match:draft",
        )
        select.callback = self._pick
        self.add_item(select)
        self._select = select

    async def _pick(self, interaction: discord.Interaction) -> None:
        gid = self.guild_id
        state = get_match_state(gid)
        if not state or state.get("phase") != PHASE_DRAFT:
            await interaction.response.send_message(t(gid, "match.draft_over"), ephemeral=True)
            return

        turn = state.get("turn")
        if interaction.user.id != turn:
            await interaction.response.send_message(
                t(gid, "match.draft_not_your_turn", captain=f"<@{turn}>"), ephemeral=True
            )
            return

        picked = int(self._select.values[0])
        if picked not in state.get("available", []):
            await interaction.response.send_message(t(gid, "match.draft_taken"), ephemeral=True)
            return

        # Garde-fou : même si l'ordre de sélection était mal construit, une
        # équipe ne peut pas dépasser sa taille et en laisser une à trois.
        team = next((n for n, ids in state["teams"].items() if turn in ids), None)
        session = self.cog._session(interaction.guild)
        limit = session.queue_config.get("max_players_per_team", 4) if session else 99
        if team is not None and len(state["teams"][team]) >= limit:
            await interaction.response.send_message(t(gid, "match.draft_team_full"), ephemeral=True)
            return

        await interaction.response.defer()
        await self.cog.apply_pick(interaction.guild, state, picked)


# ----------------------------------------------------------------------
# Cog
# ----------------------------------------------------------------------
class Match(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._started = False

    def cog_unload(self) -> None:
        self.ticker.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._started:
            self._started = True
            self.ticker.start()

    # -- Accès -----------------------------------------------------------
    def enabled(self, guild_id: int) -> bool:
        return bool(get_mmr_config(guild_id).get("enabled"))

    def captains_mode(self, guild_id: int) -> bool:
        config = get_mmr_config(guild_id)
        return bool(config.get("enabled") and config.get("captains"))

    def queue_cog(self):
        return self.bot.get_cog("QueueConfig")

    # -- Création du salon de match --------------------------------------
    async def begin(self, guild: discord.Guild, session, author: discord.Member) -> bool:
        """Crée le salon privé et lance la première phase.

        Retourne False si le salon n'a pas pu être créé : l'appelant reprend
        alors le déroulé classique plutôt que de laisser la queue en plan."""
        gid = guild.id
        config = get_mmr_config(gid)
        players = [m for m in session.waiting_players if not m.bot]
        if len(players) < 2:
            return False

        # Le vote des capitaines se décide queue par queue : le panneau de
        # /queue porte le choix de cette partie, le réglage du serveur sert
        # de valeur de départ pour les queues qui ne disent rien (celles
        # programmées avant que l'option existe, par exemple).
        use_captains = bool(session.queue_config.get("captains", config["captains"]))

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                  manage_channels=True),
        }
        for member in players:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        staff = resources.get_role(guild, "role_staff")
        if staff is not None:
            overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        category = session.waiting_channel.category if session.waiting_channel else None
        queue_name = sanitize(str(session.queue_config.get("queue_name", "match")), 40)
        try:
            channel = await guild.create_text_channel(
                name=t(gid, "match.channel_name", name=queue_name)[:100],
                category=category,
                overwrites=overwrites,
                reason="Salon de match privé",
            )
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Salon de match non créé : {e}")
            return False

        state = {
            "channel_id": channel.id,
            "players": [m.id for m in players],
            "queue_name": queue_name,
            "author_id": author.id,
            "phase": PHASE_CAPTAINS if use_captains else PHASE_LIVE,
            "votes": {},
            "captains": [],
            "teams": {},
            "available": [],
            "turn": None,
            "order": [],
            "role_ids": [],
            "deadline": now() + int(config["captain_vote_seconds"]),
            "mvp_id": None,
        }
        set_match_state(gid, state)

        if use_captains:
            await self._post_captain_vote(guild, channel, state, session)
        else:
            await channel.send(embed=self._intro_embed(guild, state), allowed_mentions=NO_PINGS)
            await self.go_live(guild, session)
        return True

    def _intro_embed(self, guild: discord.Guild, state: dict) -> discord.Embed:
        gid = guild.id
        embed = embeds.base(
            gid,
            title=t(gid, "match.intro_title", name=state["queue_name"]),
            description=t(gid, "match.intro_desc"),
            kind="brand",
        )
        embeds.brand(embed, guild)
        embeds.section(
            embed, t(gid, "match.field_players", count=len(state["players"])),
            " ".join(f"<@{uid}>" for uid in state["players"])[:1024],
        )
        return embed

    # -- Phase 1 : vote des capitaines -----------------------------------
    async def _post_captain_vote(self, guild, channel, state: dict, session) -> None:
        gid = guild.id
        candidates = [(m.id, m.display_name) for m in session.waiting_players if not m.bot]
        embed = embeds.base(
            gid,
            title=t(gid, "match.captains_title"),
            description=t(gid, "match.captains_desc", count=len(state["teams"]) or 2),
            kind="brand",
        )
        embeds.brand(embed, guild)
        embeds.section(embed, t(gid, "match.field_deadline"), f"<t:{state['deadline']}:R>")
        try:
            await channel.send(
                content=" ".join(f"<@{uid}>" for uid in state["players"])[:1900],
                embed=embed,
                view=VoteView(self, gid, PHASE_CAPTAINS, candidates),
                allowed_mentions=USERS_ONLY,
            )
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Vote des capitaines non publié : {e}")

    async def _close_captain_vote(self, guild: discord.Guild, state: dict) -> None:
        """Les plus votés deviennent capitaines. À égalité — ou sans aucun
        vote — on complète avec les joueurs les mieux classés : un match ne
        doit pas rester bloqué parce que personne n'a voté."""
        gid = guild.id
        session = self._session(guild)
        if session is None:
            await self._abort(guild, state)
            return

        tally: dict[int, int] = {}
        for choice in state.get("votes", {}).values():
            tally[int(choice)] = tally.get(int(choice), 0) + 1

        needed = max(2, len(session.teams))
        ordered = sorted(
            state["players"],
            key=lambda uid: tally.get(uid, 0),
            reverse=True,
        )
        captains = ordered[:needed]

        team_names = list(session.teams.keys())[:needed]
        state["captains"] = captains
        state["teams"] = {name: [captains[i]] for i, name in enumerate(team_names) if i < len(captains)}
        state["available"] = [uid for uid in state["players"] if uid not in captains]
        # Le draft s'arrête quand les équipes sont pleines, pas quand il n'y a
        # plus de joueurs : une file plus grande que la capacité laissait
        # sinon des tours de sélection sans place où mettre le joueur.
        limit = session.queue_config.get("max_players_per_team", 4)
        slots = sum(max(0, limit - len(members)) for members in state["teams"].values())
        state["order"] = self._draft_order(captains, min(len(state["available"]), slots))
        state["turn"] = state["order"][0] if state["order"] else None
        state["phase"] = PHASE_DRAFT
        state["deadline"] = 0
        set_match_state(gid, state)

        channel = guild.get_channel(state["channel_id"])
        if isinstance(channel, discord.TextChannel):
            await self._post_draft(guild, channel, state, tally)

    @staticmethod
    def _draft_order(captains: list[int], picks: int) -> list[int]:
        """Ordre de sélection en serpentin : A, B, B, A, A, B…

        Choisir en premier est un avantage — on prend le meilleur joueur
        disponible. Le serpentin le compense en donnant deux tours d'affilée
        au second capitaine. Construire l'ordre par tours complets, alternés,
        est plus sûr qu'un index qu'on fait rebondir à la main."""
        if not captains or picks <= 0:
            return []
        order, forward = [], True
        while len(order) < picks:
            order.extend(captains if forward else list(reversed(captains)))
            forward = not forward
        return order[:picks]

    # -- Phase 2 : draft --------------------------------------------------
    def _draft_embed(self, guild: discord.Guild, state: dict, tally: dict | None = None) -> discord.Embed:
        gid = guild.id
        embed = embeds.base(
            gid, title=t(gid, "match.draft_title"), kind="brand",
            description=t(gid, "match.draft_turn", captain=f"<@{state['turn']}>")
            if state.get("turn") else t(gid, "match.draft_done"),
        )
        embeds.brand(embed, guild)
        for name, members in state["teams"].items():
            embeds.section(
                embed, f"{state.get('colors', {}).get(name, '▫️')}  {name}",
                "\n".join(f"<@{uid}>" for uid in members) or "—",
            )
        remaining = state.get("available") or []
        embeds.section(
            embed, t(gid, "match.field_remaining", count=len(remaining)),
            " ".join(f"<@{uid}>" for uid in remaining)[:1024] or "—",
        )
        if tally:
            top = sorted(tally.items(), key=lambda x: x[1], reverse=True)[:3]
            embeds.section(
                embed, t(gid, "match.field_votes"),
                "\n".join(f"{embeds.medal(i)} <@{uid}> — **{n}**"
                          for i, (uid, n) in enumerate(top, start=1)),
            )
        return embed

    async def _post_draft(self, guild, channel, state: dict, tally: dict | None = None) -> None:
        available = [(uid, self._name(guild, uid)) for uid in state["available"]]
        try:
            message = await channel.send(
                content=t(guild.id, "match.draft_ping", captain=f"<@{state['turn']}>")
                if state.get("turn") else None,
                embed=self._draft_embed(guild, state, tally),
                view=DraftView(self, guild.id, available) if available else None,
                allowed_mentions=USERS_ONLY,
            )
            state["draft_message_id"] = message.id
            set_match_state(guild.id, state)
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Panneau de draft non publié : {e}")

    async def apply_pick(self, guild: discord.Guild, state: dict, picked: int) -> None:
        """Enregistre un choix et passe au capitaine suivant."""
        gid = guild.id
        captain = state["turn"]
        team = next((name for name, members in state["teams"].items() if captain in members), None)
        if team is None:
            return
        # Un duo/trio choisi ensemble : prendre l'un embarque les autres,
        # tant qu'il reste de la place. C'est la promesse faite au /duo.
        session = self._session(guild)
        limit = session.queue_config.get("max_players_per_team", 4) if session else 99
        try:
            from cogs.party import party_members
            block = [uid for uid in party_members(guild, picked) if uid in state["available"]]
        except Exception as e:
            log.error(f"[{guild.name}] Groupe ignoré au draft : {e}")
            block = []
        chosen = [picked]
        for uid in block:
            if uid != picked and len(state["teams"][team]) + len(chosen) < limit:
                chosen.append(uid)

        for uid in chosen:
            state["teams"][team].append(uid)
            state["available"].remove(uid)
        # Un tour consommé par joueur pris, sinon le draft compterait faux.
        state["order"] = state["order"][len(chosen):]
        state["turn"] = state["order"][0] if state["order"] else None
        set_match_state(gid, state)

        channel = guild.get_channel(state["channel_id"])
        if isinstance(channel, discord.TextChannel):
            message_id = state.get("draft_message_id")
            available = [(uid, self._name(guild, uid)) for uid in state["available"]]
            try:
                if message_id:
                    await channel.get_partial_message(message_id).edit(
                        content=t(gid, "match.draft_ping", captain=f"<@{state['turn']}>")
                        if state["turn"] else t(gid, "match.draft_done"),
                        embed=self._draft_embed(guild, state),
                        view=DraftView(self, gid, available) if available else None,
                        allowed_mentions=USERS_ONLY,
                    )
            except discord.HTTPException as e:
                log.error(f"[{guild.name}] Draft non rafraîchi : {e}")

        if not state["available"] or not state["order"]:
            await self._finish_draft(guild, state)

    async def _finish_draft(self, guild: discord.Guild, state: dict) -> None:
        """Applique les équipes choisies à la session de queue, puis lance."""
        session = self._session(guild)
        if session is None:
            await self._abort(guild, state)
            return
        for name, ids in state["teams"].items():
            session.teams[name] = [m for m in session.waiting_players if m.id in ids]
        session.started = True
        queue = self.queue_cog()
        if queue is not None:
            await queue.deploy_teams(guild, session)
        await self.go_live(guild, session)

    # -- Phase 3 : partie en cours ---------------------------------------
    async def go_live(self, guild: discord.Guild, session) -> None:
        """Crée les rôles d'équipe, verrouille le salon de match."""
        gid = guild.id
        state = get_match_state(gid)
        if not state:
            return

        colors = session.queue_config.get("team_colors", {})
        role_ids = []
        for name, members in session.teams.items():
            colour = self._role_colour(session, name)
            try:
                role = await guild.create_role(
                    name=sanitize(name, 90) or "Team",
                    colour=colour,
                    hoist=True,
                    reason="Rôle d'équipe temporaire (match en cours)",
                )
            except discord.HTTPException as e:
                log.error(f"[{guild.name}] Rôle d'équipe '{name}' non créé : {e}")
                continue
            role_ids.append(role.id)
            await throttled_each(
                members,
                lambda m, r=role: m.add_roles(r, reason="Composition de l'équipe"),
                delay=0.3,
                label=f"rôle d'équipe {name}",
            )

        state["role_ids"] = role_ids
        state["colors"] = {name: colors.get(name, "▫️") for name in session.teams}
        state["teams"] = {name: [m.id for m in members] for name, members in session.teams.items()}
        state["phase"] = PHASE_LIVE
        state["deadline"] = 0
        set_match_state(gid, state)

        channel = guild.get_channel(state["channel_id"])
        if isinstance(channel, discord.TextChannel):
            # Lecture seule : le salon reste visible pour retrouver les
            # équipes, mais la discussion se fait en vocal pendant le match.
            try:
                await channel.set_permissions(
                    guild.default_role, view_channel=False, reason="Match en cours"
                )
                for uid in state["players"]:
                    member = guild.get_member(uid)
                    if member is not None:
                        await channel.set_permissions(member, view_channel=True, send_messages=False)
            except discord.HTTPException as e:
                log.error(f"[{guild.name}] Verrouillage du salon de match : {e}")
            embed = embeds.base(
                gid, title=t(gid, "match.live_title"),
                description=t(gid, "match.live_desc"), kind="success",
            )
            embeds.brand(embed, guild)
            for name, ids in state["teams"].items():
                embeds.section(
                    embed, f"{state['colors'].get(name, '▫️')}  {name}",
                    "\n".join(f"<@{uid}>" for uid in ids) or "—",
                )
            try:
                await channel.send(embed=embed, allowed_mentions=NO_PINGS)
            except discord.HTTPException:
                pass

    @staticmethod
    def _role_colour(session, team_name: str) -> discord.Colour:
        """Couleur du rôle, reprise de celle affichée dans l'annonce."""
        palette = {
            "🔴": 0xE74C3C, "🔵": 0x3498DB, "🟢": 0x2ECC71, "🟡": 0xF1C40F,
            "🟣": 0x9B59B6, "🟠": 0xE67E22, "⚪": 0xECF0F1, "⚫": 0x2C2F33,
            "🟤": 0x8B5A2B, "🩷": 0xFF6FA5, "🩵": 0x1ABC9C, "🟦": 0x1F3A93,
        }
        emoji = session.queue_config.get("team_colors", {}).get(team_name)
        return discord.Colour(palette.get(emoji, 0x5865F2))

    # -- Phase 4 : vote du MVP -------------------------------------------
    async def begin_mvp_vote(self, guild: discord.Guild, session) -> None:
        """Appelé quand l'organisateur clôture le suivi des scores."""
        gid = guild.id
        state = get_match_state(gid)
        if not state or state.get("phase") not in (PHASE_LIVE, PHASE_DRAFT, PHASE_CAPTAINS):
            return
        config = get_mmr_config(gid)

        state["winner"] = session.winner
        state["phase"] = PHASE_MVP
        state["votes"] = {}
        state["deadline"] = now() + int(config["mvp_vote_seconds"])
        set_match_state(gid, state)

        channel = guild.get_channel(state["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            return
        # Le salon se rouvre à l'écriture : c'est le moment où l'on débriefe.
        try:
            for uid in state["players"]:
                member = guild.get_member(uid)
                if member is not None:
                    await channel.set_permissions(member, view_channel=True, send_messages=True)
        except discord.HTTPException:
            pass

        embed = embeds.base(
            gid, title=t(gid, "match.mvp_title"),
            description=t(gid, "match.mvp_desc", bonus=config["mvp_bonus"]), kind="gold",
        )
        embeds.brand(embed, guild)
        embeds.section(embed, t(gid, "match.field_deadline"), f"<t:{state['deadline']}:R>")
        candidates = [(uid, self._name(guild, uid)) for uid in state["players"]]
        try:
            await channel.send(
                content=" ".join(f"<@{uid}>" for uid in state["players"])[:1900],
                embed=embed,
                view=VoteView(self, gid, PHASE_MVP, candidates),
                allowed_mentions=USERS_ONLY,
            )
        except discord.HTTPException as e:
            log.error(f"[{guild.name}] Vote MVP non publié : {e}")

    async def _close_mvp_vote(self, guild: discord.Guild, state: dict) -> None:
        """Dépouille le vote, applique le MMR, annonce les gains."""
        gid = guild.id
        config = get_mmr_config(gid)

        tally: dict[int, int] = {}
        for choice in state.get("votes", {}).values():
            tally[int(choice)] = tally.get(int(choice), 0) + 1
        mvp_id = max(tally, key=tally.get) if tally else None
        state["mvp_id"] = mvp_id

        winner = state.get("winner")
        # La serie vient du classement, seul endroit qui la tient a jour :
        # la recompter ici la ferait diverger des le premier decalage.
        board = self.bot.get_cog("Classement")
        streaks = getattr(board, "player_stats", {}) if board is not None else {}

        changes = []
        # Une seule ecriture pour toute l equipe : sans ca, chaque joueur
        # declenchait un enregistrement complet du fichier de reglages.
        with deferred_save():
            for name, ids in state.get("teams", {}).items():
                won = (name == winner)
                for uid in ids:
                    current = get_player_mmr(gid, uid, config["start"])
                    streak = int((streaks.get(uid) or {}).get("streak", 0)) if won else 0
                    new_value, change = mmr.apply(config, current, won=won,
                                                  is_mvp=(uid == mvp_id), streak=streak)
                    set_player_mmr(gid, uid, new_value)
                    changes.append((uid, new_value, change, uid == mvp_id))

        state["phase"] = PHASE_CLOSING
        state["deadline"] = now() + int(config["cleanup_seconds"])
        set_match_state(gid, state)

        channel = guild.get_channel(state["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(
                    embed=self._results_embed(guild, state, changes, tally),
                    allowed_mentions=NO_PINGS,
                )
            except discord.HTTPException as e:
                log.error(f"[{guild.name}] Résultats MMR non publiés : {e}")

        if config.get("rank_roles"):
            await self.sync_rank_roles(guild, [uid for uid, _v, _c, _m in changes])

    def _results_embed(self, guild, state, changes, tally) -> discord.Embed:
        gid = guild.id
        config = get_mmr_config(gid)
        embed = embeds.base(
            gid, title=t(gid, "match.results_title"), kind="gold", timestamp=True,
            footer=t(gid, "match.results_footer", minutes=round(config["cleanup_seconds"] / 60)),
        )
        embeds.brand(embed, guild)

        mvp_id = state.get("mvp_id")
        if mvp_id:
            embed.description = t(
                gid, "match.mvp_winner",
                player=f"<@{mvp_id}>", votes=tally.get(mvp_id, 0), bonus=config["mvp_bonus"],
            )
        else:
            embed.description = t(gid, "match.mvp_none")

        lines = []
        for uid, value, change, is_mvp in sorted(changes, key=lambda c: c[1], reverse=True):
            tier = mmr.tier_for({"tiers": tiers_of(gid, config)}, value)
            badge = f"{tier.get('icon', '')} " if tier and tier.get("icon") else ""
            crown = " 👑" if is_mvp else ""
            lines.append(
                f"{badge}<@{uid}>{crown} — **{value}** `{mmr.format_change(change)}`"
            )
        embeds.section(embed, t(gid, "match.field_mmr"), "\n".join(lines)[:1024] or "—")
        return embed

    # -- Rôles de rang ----------------------------------------------------
    async def sync_rank_roles(self, guild: discord.Guild, user_ids: list[int]) -> None:
        """Attribue à chacun le rôle de son palier, et retire les autres."""
        gid = guild.id
        config = get_mmr_config(gid)
        tiers = tiers_of(gid, config)
        roles: dict[str, discord.Role] = {}

        for tier in tiers:
            name = sanitize(str(tier.get("name", "")), 90) or "Rang"
            role = discord.utils.get(guild.roles, name=name)
            if role is None:
                try:
                    role = await guild.create_role(
                        name=name,
                        colour=discord.Colour(int(tier.get("color", 0x99AAB5))),
                        hoist=True,
                        reason="Rôle de rang MMR",
                    )
                    await self._apply_icon(guild, role, tier.get("icon"))
                except discord.HTTPException as e:
                    log.error(f"[{guild.name}] Rôle de rang '{name}' non créé : {e}")
                    continue
            roles[name] = role

        for uid in user_ids:
            member = guild.get_member(uid)
            if member is None:
                continue
            value = get_player_mmr(gid, uid, config["start"])
            wanted = mmr.tier_for({"tiers": tiers}, value)
            wanted_role = roles.get(sanitize(str(wanted.get("name", "")), 90)) if wanted else None
            obsolete = [r for r in member.roles if r in roles.values() and r != wanted_role]
            try:
                if obsolete:
                    await member.remove_roles(*obsolete, reason="Changement de rang MMR")
                if wanted_role is not None and wanted_role not in member.roles:
                    await member.add_roles(wanted_role, reason="Rang MMR atteint")
            except discord.HTTPException as e:
                log.error(f"[{guild.name}] Rang non appliqué à {uid} : {e}")

    @staticmethod
    async def _apply_icon(guild: discord.Guild, role: discord.Role, icon) -> None:
        """Icône de rôle — réservée aux serveurs boostés (niveau 2).

        Sans le boost, Discord refuse la requête : on n'essaie donc même pas,
        plutôt que de logger une erreur à chaque création de rôle."""
        if not icon or "ROLE_ICONS" not in getattr(guild, "features", []):
            return
        try:
            await role.edit(display_icon=str(icon), reason="Icône de rang MMR")
        except (discord.HTTPException, TypeError) as e:
            log.info(f"[{guild.name}] Icône de rang non appliquée : {e}")

    # -- Nettoyage --------------------------------------------------------
    async def _cleanup(self, guild: discord.Guild, state: dict) -> None:
        """Supprime salon de match, rôles d'équipe et vocaux d'équipe."""
        gid = guild.id
        for role_id in state.get("role_ids", []):
            role = guild.get_role(role_id)
            if role is not None:
                try:
                    await role.delete(reason="Match terminé : rôle temporaire")
                except discord.HTTPException as e:
                    log.error(f"[{guild.name}] Rôle d'équipe non supprimé : {e}")

        session = self._session(guild)
        if session is not None:
            for channel in list(session.team_channels.values()):
                try:
                    await channel.delete(reason="Match terminé")
                except discord.HTTPException:
                    pass
            session.team_channels.clear()

        channel = guild.get_channel(state.get("channel_id") or 0)
        if channel is not None:
            try:
                await channel.delete(reason="Match terminé")
            except discord.HTTPException as e:
                log.error(f"[{guild.name}] Salon de match non supprimé : {e}")

        set_match_state(gid, None)
        log.info(f"[{guild.name}] Match nettoyé.")

    async def _abort(self, guild: discord.Guild, state: dict) -> None:
        log.warning(f"[{guild.name}] Match interrompu : session de queue introuvable.")
        await self._cleanup(guild, state)

    def _session(self, guild: discord.Guild):
        cog = self.queue_cog()
        if cog is None:
            return None
        session = cog.active_sessions.get(guild.id)
        return session if session is not None and not session.ended else session

    @staticmethod
    def _name(guild: discord.Guild, uid: int) -> str:
        member = guild.get_member(uid)
        return member.display_name if member is not None else f"#{uid}"

    # -- Boucle des échéances --------------------------------------------
    @tasks.loop(seconds=TICK_SECONDS)
    async def ticker(self) -> None:
        for guild in list(self.bot.guilds):
            state = get_match_state(guild.id)
            if not state or not state.get("deadline"):
                continue
            if now() < state["deadline"]:
                continue
            try:
                phase = state.get("phase")
                if phase == PHASE_CAPTAINS:
                    await self._close_captain_vote(guild, state)
                elif phase == PHASE_MVP:
                    await self._close_mvp_vote(guild, state)
                elif phase == PHASE_CLOSING:
                    await self._cleanup(guild, state)
            except Exception as e:
                log.error(f"[{guild.name}] Phase de match '{state.get('phase')}' : {e}")

    @ticker.before_loop
    async def before_ticker(self) -> None:
        await self.bot.wait_until_ready()

    # -- Panneau de configuration ----------------------------------------


    @app_commands.command(name="elo", description="Affiche ton niveau, ton rang et le palier suivant.")
    @app_commands.describe(membre="Le joueur à consulter (toi par défaut)")
    async def elo(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        gid = interaction.guild_id
        config = get_mmr_config(gid)
        if not config["enabled"]:
            await interaction.response.send_message(t(gid, "mmr.elo_disabled"), ephemeral=True)
            return

        target = membre or interaction.user
        value = get_player_mmr(gid, target.id, config["start"])
        tiers = tiers_of(gid, config)
        current = mmr.tier_for({"tiers": tiers}, value)
        upper = mmr.next_tier({"tiers": tiers}, value)
        done, span = mmr.progress({"tiers": tiers}, value)

        embed = embeds.base(
            gid,
            title=t(gid, "mmr.elo_title", name=target.display_name),
            kind="gold",
            footer=t(gid, "mmr.elo_footer",
                     win=config["win"], loss=config["loss"], mvp=config["mvp_bonus"]),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embeds.brand(embed, interaction.guild)
        if current is not None:
            embed.colour = discord.Colour(int(current.get("color", 0xF1C40F)))
        embed.description = (
            f"{(current or {}).get('icon', '') or '▫️'}  "
            f"**{(current or {}).get('name') or t(gid, 'mmr.elo_none')}**"
        )
        embeds.stat(embed, t(gid, "mmr.elo_points"), value)
        embed.add_field(
            name=t(gid, "mmr.elo_next"),
            value=(t(gid, "mmr.elo_next_value", name=upper["name"], points=upper["min"] - value)
                   if upper else t(gid, "mmr.elo_max")),
            inline=True,
        )
        embeds.align(embed)
        await interaction.response.send_message(embed=embed)


# ----------------------------------------------------------------------
# Panneau /mmr
# ----------------------------------------------------------------------
def build_mmr_embed(guild: discord.Guild) -> discord.Embed:
    gid = guild.id
    config = get_mmr_config(gid)
    on = config["enabled"]

    embed = discord.Embed(
        title=t(gid, "mmr.panel_title"),
        description=t(gid, "mmr.panel_desc"),
        color=0x000000  # Noir
    )
    # Pas de footer, pas de branding

    embed.add_field(name=t(gid, "mmr.field_state"),
                    value=t(gid, "auto.on" if on else "auto.off"), inline=True)
    embed.add_field(name=t(gid, "mmr.field_captains"),
                    value=t(gid, "auto.on" if config["captains"] else "auto.off"), inline=True)
    embed.add_field(name=t(gid, "mmr.field_roles"),
                    value=t(gid, "auto.on" if config["rank_roles"] else "auto.off"), inline=True)

    embeds.section(
        embed, t(gid, "mmr.field_points"),
        t(gid, "mmr.points_value",
          start=config["start"], win=config["win"], loss=config["loss"], mvp=config["mvp_bonus"]),
    )
    embeds.section(
        embed, t(gid, "mmr.field_timers"),
        t(gid, "mmr.timers_value",
          captain=config["captain_vote_seconds"],
          mvp=config["mvp_vote_seconds"],
          cleanup=config["cleanup_seconds"]),
    )

    tiers = tiers_of(gid, config)
    embeds.section(
        embed, t(gid, "mmr.field_tiers", count=len(tiers)),
        "\n".join(
            f"{tier.get('icon', '') or '▫️'} **{tier.get('name', '?')}** — `{tier.get('min', 0)}` "
            f"`#{int(tier.get('color', 0)):06X}`"
            for tier in mmr.sorted_tiers({"tiers": tiers})
        )[:1024] or "—",
    )
    return embed


class MMRView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild = guild
        self._sync()

    def _sync(self) -> None:
        gid = self.guild.id
        config = get_mmr_config(gid)
        self.toggle.label = t(gid, "auto.btn_off" if config["enabled"] else "auto.btn_on")
        self.toggle.style = (discord.ButtonStyle.danger if config["enabled"]
                             else discord.ButtonStyle.success)
        self.toggle.emoji = "⏸️" if config["enabled"] else "▶️"
        self.captains.label = t(gid, "mmr.btn_captains")
        self.rank_roles.label = t(gid, "mmr.btn_roles")
        self.points.label = t(gid, "mmr.btn_points")
        self.timers.label = t(gid, "mmr.btn_timers")
        self.tiers.label = t(gid, "mmr.btn_tiers")
        self.reset_tiers.label = t(gid, "mmr.btn_reset_tiers")

    async def _refresh(self, interaction: discord.Interaction, content: str | None = None) -> None:
        self._sync()
        await interaction.response.edit_message(
            content=content, embed=build_mmr_embed(self.guild), view=self
        )

    @discord.ui.button(label="Activer", style=discord.ButtonStyle.success, emoji="▶️",
                       row=0, custom_id="cyq:mmr:toggle")
    async def toggle(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        set_mmr_config(self.guild.id, enabled=not get_mmr_config(self.guild.id)["enabled"])
        await self._refresh(interaction)

    @discord.ui.button(label="Capitaines", style=discord.ButtonStyle.secondary, emoji="👑",
                       row=0, custom_id="cyq:mmr:captains")
    async def captains(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        set_mmr_config(self.guild.id, captains=not get_mmr_config(self.guild.id)["captains"])
        await self._refresh(interaction)

    @discord.ui.button(label="Rôles de rang", style=discord.ButtonStyle.secondary, emoji="🎖️",
                       row=0, custom_id="cyq:mmr:roles")
    async def rank_roles(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        set_mmr_config(self.guild.id, rank_roles=not get_mmr_config(self.guild.id)["rank_roles"])
        await self._refresh(interaction)

    @discord.ui.button(label="Points", style=discord.ButtonStyle.primary, emoji="📈",
                       row=1, custom_id="cyq:mmr:points")
    async def points(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(PointsModal(self))

    @discord.ui.button(label="Durées", style=discord.ButtonStyle.primary, emoji="⏱️",
                       row=1, custom_id="cyq:mmr:timers")
    async def timers(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(TimersModal(self))

    @discord.ui.button(label="Rangs", style=discord.ButtonStyle.primary, emoji="🎖️",
                       row=2, custom_id="cyq:mmr:tiers")
    async def tiers(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(TierModal(self))

    @discord.ui.button(label="Rangs par défaut", style=discord.ButtonStyle.secondary, emoji="↩️",
                       row=2, custom_id="cyq:mmr:resettiers")
    async def reset_tiers(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        set_mmr_config(self.guild.id, tiers=None)
        await self._refresh(interaction, t(self.guild.id, "mmr.tiers_reset"))


def _bounded(value: str, low: int, high: int) -> int | None:
    cleaned = value.strip()
    if not cleaned.lstrip("-").isdigit():
        return None
    number = int(cleaned)
    return number if low <= number <= high else None


class PointsModal(discord.ui.Modal):
    """Combien rapporte une victoire, coûte une défaite, et vaut le MVP."""

    def __init__(self, view: MMRView):
        gid = view.guild.id
        super().__init__(title=t(gid, "mmr.points_modal"))
        self.view_ref = view
        config = get_mmr_config(gid)
        self.f_start = discord.ui.TextInput(label=t(gid, "mmr.f_start"),
                                            default=str(config["start"]), max_length=5)
        self.f_win = discord.ui.TextInput(label=t(gid, "mmr.f_win"),
                                          default=str(config["win"]), max_length=3)
        self.f_loss = discord.ui.TextInput(label=t(gid, "mmr.f_loss"),
                                           default=str(config["loss"]), max_length=3)
        self.f_mvp = discord.ui.TextInput(label=t(gid, "mmr.f_mvp"),
                                          default=str(config["mvp_bonus"]), max_length=3)
        for field in (self.f_start, self.f_win, self.f_loss, self.f_mvp):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = self.view_ref.guild.id
        start = _bounded(self.f_start.value, 0, 10000)
        win = _bounded(self.f_win.value, 0, mmr.MAX_POINTS)
        loss = _bounded(self.f_loss.value, 0, mmr.MAX_POINTS)
        bonus = _bounded(self.f_mvp.value, 0, mmr.MAX_POINTS)
        if None in (start, win, loss, bonus):
            await interaction.response.send_message(
                t(gid, "mmr.points_invalid", max=mmr.MAX_POINTS), ephemeral=True
            )
            return
        set_mmr_config(gid, start=start, win=win, loss=loss, mvp_bonus=bonus)
        await self.view_ref._refresh(interaction, t(gid, "mmr.saved"))


class TimersModal(discord.ui.Modal):
    """Durées des votes et délai avant suppression du salon."""

    def __init__(self, view: MMRView):
        gid = view.guild.id
        super().__init__(title=t(gid, "mmr.timers_modal"))
        self.view_ref = view
        config = get_mmr_config(gid)
        self.f_captain = discord.ui.TextInput(label=t(gid, "mmr.f_captain_secs"),
                                              default=str(config["captain_vote_seconds"]), max_length=4)
        self.f_mvp = discord.ui.TextInput(label=t(gid, "mmr.f_mvp_secs"),
                                          default=str(config["mvp_vote_seconds"]), max_length=4)
        self.f_cleanup = discord.ui.TextInput(label=t(gid, "mmr.f_cleanup_secs"),
                                              default=str(config["cleanup_seconds"]), max_length=4)
        for field in (self.f_captain, self.f_mvp, self.f_cleanup):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = self.view_ref.guild.id
        # 30 s minimum : la boucle passe toutes les 15 s, plus court n'aurait
        # aucun effet visible et couperait le vote avant que quiconque clique.
        captain = _bounded(self.f_captain.value, 30, 3600)
        mvp_secs = _bounded(self.f_mvp.value, 30, 3600)
        cleanup = _bounded(self.f_cleanup.value, 30, 3600)
        if None in (captain, mvp_secs, cleanup):
            await interaction.response.send_message(t(gid, "mmr.timers_invalid"), ephemeral=True)
            return
        set_mmr_config(gid, captain_vote_seconds=captain, mvp_vote_seconds=mvp_secs,
                       cleanup_seconds=cleanup)
        await self.view_ref._refresh(interaction, t(gid, "mmr.saved"))


class TierModal(discord.ui.Modal):
    """Création ou modification d'un rang (nom, seuil, couleur, icône)."""

    def __init__(self, view: MMRView):
        gid = view.guild.id
        super().__init__(title=t(gid, "mmr.tier_modal"))
        self.view_ref = view
        self.f_name = discord.ui.TextInput(label=t(gid, "mmr.f_tier_name"), max_length=90)
        self.f_min = discord.ui.TextInput(label=t(gid, "mmr.f_tier_min"), max_length=5)
        self.f_color = discord.ui.TextInput(label=t(gid, "mmr.f_tier_color"),
                                            placeholder="#F1C40F", required=False, max_length=7)
        self.f_icon = discord.ui.TextInput(label=t(gid, "mmr.f_tier_icon"),
                                           required=False, max_length=4)
        for field in (self.f_name, self.f_min, self.f_color, self.f_icon):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = self.view_ref.guild.id
        config = get_mmr_config(gid)
        name = sanitize(self.f_name.value.strip(), 90)
        threshold = _bounded(self.f_min.value, 0, 10000)
        if not name or threshold is None:
            await interaction.response.send_message(t(gid, "mmr.tier_invalid"), ephemeral=True)
            return

        colour = 0x99AAB5
        raw = self.f_color.value.strip().lstrip("#")
        if raw:
            try:
                colour = int(raw, 16)
            except ValueError:
                await interaction.response.send_message(t(gid, "mmr.tier_bad_color"), ephemeral=True)
                return

        tiers = [dict(tier) for tier in tiers_of(gid, config)]
        entry = {"name": name, "min": threshold, "color": colour,
                 "icon": self.f_icon.value.strip()[:4]}
        # Même nom = modification, sinon ajout : un panneau qui empile des
        # doublons devient vite illisible.
        for i, tier in enumerate(tiers):
            if str(tier.get("name", "")).lower() == name.lower():
                tiers[i] = entry
                break
        else:
            if len(tiers) >= mmr.MAX_TIERS:
                await interaction.response.send_message(
                    t(gid, "mmr.tier_full", max=mmr.MAX_TIERS), ephemeral=True
                )
                return
            tiers.append(entry)

        set_mmr_config(gid, tiers=tiers)
        await self.view_ref._refresh(interaction, t(gid, "mmr.tier_saved", name=name))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Match(bot))
    log.info("Cog Match chargé")
