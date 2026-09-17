"""
Cog : Classement
================
Système de classement persistant — victoires, défaites, win rate, séries.
Commandes : /classement, /stats
"""

import logging
import json
import os
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

import embeds
import resources
from guild_settings import get_classement_message_id, set_classement_message_id, get_clans
from i18n import t
from rate_limit import throttled_each
from text_safety import sanitize
from json_store import write_json

log = logging.getLogger("bot.classement")

CLASSEMENT_SAVE_FILE  = "data/classement.json"
MVP_SAVE_FILE         = "data/mvp.json"
SERVERSTATS_SAVE_FILE = "data/serverstats.json"

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _win_rate(stats: dict) -> float:
    total = stats["wins"] + stats.get("losses", 0)
    return (stats["wins"] / total * 100) if total > 0 else 0.0


def _streak_label(streak: int) -> str:
    if streak >= 5:
        return f"🔥🔥 **{streak}**"
    if streak >= 3:
        return f"🔥 **{streak}**"
    return f"**{streak}**"


class Classement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.player_stats: dict[int, dict] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "streak": 0, "max_streak": 0, "weekly_wins": 0}
        )
        self.server_stats: dict = {"total_queues": 0}
        self.last_mvp_check: datetime | None = None
        self._synced = False  # Flag pour éviter les synchronisations multiples
        self._mvp_task_started = False  # idem pour la tâche de fond MVP hebdo

    def _is_staff(self, member: discord.Member) -> bool:
        return resources.is_staff(member)

    @commands.Cog.listener()
    async def on_ready(self):
        """Chargement des configs et synchronisation au démarrage du bot."""
        # Charger les configurations
        await self.load_classement_config()
        await self.load_mvp_config()
        await self.load_server_stats()
        
        # Synchroniser le classement (une seule fois)
        if not self._synced:
            await self.sync_classement_on_ready()
            self._synced = True
        
        # Démarrer le check MVP hebdomadaire (une seule fois : on_ready peut se
        # redéclencher après une reconnexion, et cette tâche tourne en boucle
        # infinie — sans garde, une reconnexion en créerait une deuxième et
        # doublerait l'annonce MVP hebdomadaire).
        if not self._mvp_task_started:
            self._mvp_task_started = True
            self.bot.loop.create_task(self.weekly_mvp_check())

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    async def load_classement_config(self):
        if not os.path.exists(CLASSEMENT_SAVE_FILE):
            os.makedirs(os.path.dirname(CLASSEMENT_SAVE_FILE), exist_ok=True)
            return
        try:
            with open(CLASSEMENT_SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for uid_str, stats in data.items():
                uid = int(uid_str)
                self.player_stats[uid] = stats
                # Migration : champs ajoutés après la v1
                self.player_stats[uid].setdefault("losses", 0)
                self.player_stats[uid].setdefault("weekly_wins", 0)
            log.info(f"Classement chargé : {len(self.player_stats)} joueur(s)")
        except Exception as e:
            log.error(f"Erreur chargement classement : {e}")

    async def load_mvp_config(self):
        if not os.path.exists(MVP_SAVE_FILE):
            os.makedirs(os.path.dirname(MVP_SAVE_FILE), exist_ok=True)
            return
        try:
            with open(MVP_SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            last = data.get("last_check")
            self.last_mvp_check = datetime.fromisoformat(last) if last else None
        except Exception as e:
            log.error(f"Erreur chargement MVP : {e}")

    async def save_classement_config(self):
        try:
            write_json(CLASSEMENT_SAVE_FILE, dict(self.player_stats), indent=4)
        except Exception as e:
            log.error(f"Erreur sauvegarde classement : {e}")

    async def load_server_stats(self):
        if not os.path.exists(SERVERSTATS_SAVE_FILE):
            return
        try:
            with open(SERVERSTATS_SAVE_FILE, "r", encoding="utf-8") as f:
                self.server_stats = json.load(f)
        except Exception as e:
            log.error(f"Erreur chargement serverstats : {e}")

    async def save_server_stats(self):
        try:
            write_json(SERVERSTATS_SAVE_FILE, self.server_stats, indent=4)
        except Exception as e:
            log.error(f"Erreur sauvegarde serverstats : {e}")

    def record_queue(self):
        self.server_stats["total_queues"] = self.server_stats.get("total_queues", 0) + 1

    async def save_mvp_config(self):
        try:
            write_json(MVP_SAVE_FILE, {'last_check': self.last_mvp_check.isoformat() if self.last_mvp_check else None})
        except Exception as e:
            log.error(f"Erreur sauvegarde MVP : {e}")

    # ------------------------------------------------------------------
    # Mise à jour des stats
    # ------------------------------------------------------------------
    def add_win(self, user_id: int):
        s = self.player_stats[user_id]
        s["wins"] += 1
        s["weekly_wins"] += 1
        s["streak"] += 1
        if s["streak"] > s["max_streak"]:
            s["max_streak"] = s["streak"]

    def add_loss(self, user_id: int):
        s = self.player_stats[user_id]
        s["streak"] = 0
        s["losses"] = s.get("losses", 0) + 1

    # ------------------------------------------------------------------
    # MVP hebdomadaire
    # ------------------------------------------------------------------
    async def weekly_mvp_check(self):
        while not self.bot.is_closed():
            try:
                now = datetime.now()
                if self.last_mvp_check is None or (now - self.last_mvp_check) >= timedelta(days=7):
                    await self.assign_mvp_role()
                    self.last_mvp_check = now
                    await self.save_mvp_config()
                await asyncio.sleep(3600)
            except Exception as e:
                log.error(f"Erreur check MVP : {e}")
                await asyncio.sleep(3600)

    async def assign_mvp_role(self):
        if not self.player_stats:
            return
        sorted_players = sorted(
            self.player_stats.items(),
            key=lambda x: x[1]["weekly_wins"],
            reverse=True,
        )
        top_id, top_stats = sorted_players[0]
        if top_stats["weekly_wins"] == 0:
            return

        # top_stats est une RÉFÉRENCE vers l'entrée de player_stats : la remise
        # à zéro ci-dessous l'écrase.
        mvp_wins = top_stats["weekly_wins"]

        # Réinitialiser les wins hebdo
        for uid in self.player_stats:
            self.player_stats[uid]["weekly_wins"] = 0
        await self.save_classement_config()

        for guild in self.bot.guilds:
            try:
                mvp_role = resources.get_role(guild, "role_mvp_week")
                # Le rôle MVP est **désigné** par l'administrateur, jamais
                # créé.
                if mvp_role:
                    # Vérifier que le rôle existe vraiment et n'est pas un rôle par défaut
                    # Éviter d'attribuer des rôles système comme "Owner"
                    if mvp_role.name.lower() in ["owner", "administrator", "admin", "moderator", "mod"]:
                        log.warning(
                            f"[{guild.name}] Le rôle MVP désigné '{mvp_role.name}' semble être un rôle système. "
                            f"Attribution de rôle MVP ignorée pour éviter les conflits."
                        )
                        mvp_role = None
                    else:
                        await throttled_each(
                            list(mvp_role.members),
                            lambda m: m.remove_roles(mvp_role, reason="Réinit hebdo MVP"),
                            label="réinit MVP hebdo",
                        )

                member = guild.get_member(top_id)
                if not member:
                    continue

                if mvp_role:
                    await member.add_roles(mvp_role, reason="MVP de la semaine")
                    log.info(f"MVP → {member.display_name} ({guild.name})")
                else:
                    log.info(
                        f"[{guild.name}] Aucun rôle MVP désigné : "
                        f"{member.display_name} est annoncé sans rôle."
                    )

                # Le MVP est un résultat de classement : il va dans le salon
                # classement, pas dans les annonces de queue.
                announce_ch = resources.get_text_channel(guild, "channel_queue_classement")
                if announce_ch:
                    embed = embeds.base(
                        guild.id,
                        title=t(guild.id, "classement.mvp_announce_title"),
                        description=t(
                            guild.id,
                            "classement.mvp_announce_desc",
                            mention=member.mention,
                            wins=mvp_wins,
                        ),
                        kind="gold",
                        timestamp=True,
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embeds.brand(embed, guild)
                    await announce_ch.send(embed=embed)
            except Exception as e:
                log.error(f"Erreur MVP dans {guild.name} : {e}")

    # ------------------------------------------------------------------
    # Construction des embeds
    # ------------------------------------------------------------------
    def _player_label(self, guild: discord.Guild | None, uid: int) -> str:
        """Pseudo affichable dans un tableau monospace."""
        member = guild.get_member(uid) if guild is not None else None
        name = member.display_name if member is not None else f"#{uid}"
        # Les emojis et caractères larges cassent l'alignement d'un tableau
        # monospace : on ne garde que ce qui occupe une chasse fixe.
        cleaned = "".join(c for c in name if c.isprintable() and ord(c) < 0x2000).strip()
        return (cleaned or f"#{uid}")[:14]

    def _player_name(self, guild: discord.Guild | None, uid: int) -> str:
        """Comment nommer un joueur dans le classement."""
        member = guild.get_member(uid) if guild is not None else None
        if member is not None:
            return member.mention
        return f"`{self._player_label(guild, uid)}`"

    async def create_classement_embed(
        self, guild_id: int | None = None, guild: discord.Guild | None = None
    ) -> discord.Embed:
        """Classement en tableau aligné."""
        sorted_players = sorted(
            self.player_stats.items(),
            key=lambda x: (x[1]["wins"], x[1].get("max_streak", 0)),
            reverse=True,
        )
        ranked = [(uid, s) for uid, s in sorted_players
                  if s["wins"] or s.get("losses", 0)]
        top = ranked[:10]

        embed = embeds.base(
            guild_id,
            title=t(guild_id, "classement.title"),
            kind="gold",
            timestamp=True,
            footer=t(guild_id, "classement.footer_count", count=len(ranked)),
        )
        embeds.brand(embed, guild)
        if guild is not None and guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)

        if not top:
            embed.description = t(guild_id, "classement.no_data")
            return embed

        # Une ligne par joueur, et rien d’autre.
        rows = []
        for rank, (uid, s) in enumerate(top, start=1):
            streak = s.get("streak", 0)
            rows.append(t(
                guild_id, "classement.row",
                rank=embeds.MEDALS[rank] if rank <= 3 else f"`{rank}`",
                player=self._player_name(guild, uid),
                wins=s["wins"], losses=s.get("losses", 0),
                streak=t(guild_id, "classement.row_streak", n=streak) if streak >= 3 else "",
            ))
        embed.description = '\n'.join(rows)
        return embed

    # ------------------------------------------------------------------
    # Sync au démarrage
    # ------------------------------------------------------------------
    async def sync_classement_on_ready(self):
        for guild in self.bot.guilds:
            ch = resources.get_text_channel(guild, "channel_queue_classement")
            if ch:
                await self._publish_classement(guild, ch)

    def create_clan_embed(self, guild: discord.Guild) -> discord.Embed:
        """Classement des clans, trie par victoires."""
        gid = guild.id
        cog = self.bot.get_cog("Clan")
        embed = embeds.base(
            gid, title=t(gid, "clan.board_title"), kind="gold", timestamp=True,
        )
        embeds.brand(embed, guild)
        if cog is None:
            embed.description = t(gid, "clan.board_empty")
            return embed

        rows, shown = [], 0
        length = 0
        
        # Recréer la fonction sorted_clans localement
        def _sorted_clans(guild_id: int):
            """Clans triés par victoires, puis par ratio à égalité."""
            clans = get_clans(guild_id).values()
            rows = []
            for clan in clans:
                wins = losses = 0
                for uid in clan.get("members", []):
                    entry = self.player_stats.get(uid) or {}
                    wins += int(entry.get("wins", 0))
                    losses += int(entry.get("losses", 0))
                ratio = wins / losses if losses else float(wins)
                rows.append((clan, wins, losses, ratio))
            rows.sort(key=lambda r: (r[1], r[3]), reverse=True)
            return rows
        
        for rank, (clan, wins, losses, ratio) in enumerate(_sorted_clans(gid), start=1):
            line = t(
                gid, "clan.board_row",
                rank=embeds.MEDALS[rank] if rank <= 3 else str(rank),
                name=sanitize(clan.get("name", "?"), 32),
                leader=f"<@{clan.get('leader_id')}>",
                members=len(clan.get("members", [])),
                wins=wins, losses=losses, kd=f"{ratio:.2f}",
            )
            if length + len(line) + 1 > 4000:
                break
            rows.append(line)
            length += len(line) + 1
            shown = rank

        embed.description = "\n".join(rows) or t(gid, "clan.board_empty")
        embed.set_footer(text=t(gid, "clan.board_footer", count=shown))
        return embed

    async def update_classement_channel(self, guild: discord.Guild):
        ch = resources.get_text_channel(guild, "channel_queue_classement")
        if not ch:
            return
        await self._publish_classement(guild, ch)

    async def refresh_everywhere(self) -> tuple[int, int]:
        """Réécrit le classement sur tous les serveurs. (mis à jour, ignorés)"""
        done = 0
        targets = [
            guild for guild in self.bot.guilds
            if resources.get_text_channel(guild, "channel_queue_classement") is not None
        ]

        async def publish(guild: discord.Guild) -> None:
            nonlocal done
            await self.update_classement_channel(guild)
            done += 1

        await throttled_each(targets, publish, delay=0.6, label="republication du classement")
        log.info(f"Classement republié sur {done}/{len(self.bot.guilds)} serveur(s).")
        return done, len(self.bot.guilds) - done

    async def _publish_classement(self, guild: discord.Guild, ch: discord.TextChannel) -> None:
        """Met à jour LE message de classement du salon sans jamais en laisser
        deux : on édite le message mémorisé s'il existe encore côté Discord,
        on n'en recrée un que s'il a disparu."""
        # Deux embeds dans UN message : le classement des joueurs puis celui
        # des clans.
        payload = [await self.create_classement_embed(guild.id, guild),
                   self.create_clan_embed(guild)]
        message_id = get_classement_message_id(guild.id)

        if message_id:
            try:
                msg = await ch.fetch_message(message_id)
                await msg.edit(embeds=payload)
                return
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                log.error(f"Erreur édition classement {guild.name} : {e}")
                return

        # Pas de message mémorisé (ou supprimé côté Discord) : on nettoie les
        # doublons hérités du bug ci-dessus avant d'en publier un nouveau.
        try:
            async for old in ch.history(limit=25):
                if old.author == guild.me and old.embeds:
                    try:
                        await old.delete()
                    except discord.HTTPException:
                        pass
        except discord.HTTPException as e:
            log.error(f"Erreur purge classement {guild.name} : {e}")

        try:
            new_msg = await ch.send(embeds=payload)
            set_classement_message_id(guild.id, new_msg.id)
            log.info(f"Classement (re)publié dans {guild.name}")
        except discord.HTTPException as e:
            log.error(f"Erreur publication classement {guild.name} : {e}")

    # ------------------------------------------------------------------
    # Commandes
    # ------------------------------------------------------------------
    @app_commands.command(
        name="leaderboard",
        description="Met à jour le classement dans 📃・queue-classement (staff uniquement).",
    )
    @app_commands.describe(partout="Republier le classement sur TOUS les serveurs (propriétaire du bot)")
    async def classement(self, interaction: discord.Interaction, partout: bool = False):
        guild_id = interaction.guild_id
        if not isinstance(interaction.user, discord.Member) or not self._is_staff(interaction.user):
            await interaction.response.send_message(
                embed=embeds.base(guild_id, description=t(guild_id, "common.members_only"), kind="error"),
                ephemeral=True,
            )
            return

        if partout:
            # Réservé au propriétaire : un staff local n'a rien à faire sur les
            # autres serveurs, et un rafraîchissement global coûte un appel API
            # par serveur.
            if not await self.bot.is_owner(interaction.user):
                await interaction.response.send_message(
                    embed=embeds.base(guild_id, kind="error",
                                      description=t(guild_id, "classement.owner_only")),
                    ephemeral=True,
                )
                return
            await interaction.response.defer(ephemeral=True)
            done, skipped = await self.refresh_everywhere()
            await interaction.followup.send(
                embed=embeds.base(
                    guild_id, kind="success",
                    description=t(guild_id, "classement.updated_all", done=done, skipped=skipped),
                ),
                ephemeral=True,
            )
            return

        ch = resources.get_text_channel(interaction.guild, "channel_queue_classement")
        if not ch:
            await interaction.response.send_message(
                embed=embeds.base(
                    guild_id, kind="error",
                    description=t(
                        guild_id, "classement.channel_not_found",
                        channel=resources.resource_name(guild_id, "channel_queue_classement"),
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await self.update_classement_channel(interaction.guild)
        await interaction.followup.send(
            embed=embeds.base(
                guild_id, kind="success",
                description=t(guild_id, "classement.updated", channel=ch.mention),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="stats",
        description="Affiche les statistiques détaillées d'un joueur.",
    )
    @app_commands.describe(membre="Le joueur à consulter (toi par défaut)")
    async def stats(self, interaction: discord.Interaction, membre: discord.Member | None = None):
        guild_id = interaction.guild_id
        target = membre or interaction.user
        uid = target.id
        s = self.player_stats[uid]
        losses = s.get("losses", 0)
        total = s["wins"] + losses
        wr = _win_rate(s)

        # Rang dans le classement
        sorted_ids = [
            uid_
            for uid_, _ in sorted(
                self.player_stats.items(),
                key=lambda x: (x[1]["wins"], x[1].get("max_streak", 0)),
                reverse=True,
            )
        ]
        rank = sorted_ids.index(uid) + 1 if uid in sorted_ids and total > 0 else None

        embed = embeds.base(
            guild_id,
            title=t(guild_id, "classement.stats_title", name=target.display_name),
            kind="gold" if rank and rank <= 3 else "brand",
            timestamp=True,
            footer=t(guild_id, "classement.stats_footer"),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embeds.brand(embed, interaction.guild)

        embed.description = (
            f"{t(guild_id, 'classement.stats_winrate')}  ·  **{wr:.0f}%**"
            if total else t(guild_id, "classement.stats_no_games")
        )

        embeds.stat(embed, t(guild_id, "classement.stats_wins"), s["wins"])
        embeds.stat(embed, t(guild_id, "classement.stats_losses"), losses)
        embeds.stat(embed, t(guild_id, "classement.stats_games_played"), total)
        embed.add_field(name=t(guild_id, "classement.stats_streak"),
                        value=_streak_label(s["streak"]), inline=True)
        embeds.stat(embed, t(guild_id, "classement.stats_best_streak"), s["max_streak"])
        if rank:
            embeds.stat(embed, t(guild_id, "classement.stats_rank"), embeds.medal(rank).strip("`"))
        else:
            embeds.spacer(embed)

        if s.get("weekly_wins", 0) > 0:
            embeds.stat(embed, t(guild_id, "classement.stats_weekly"), s["weekly_wins"])
        embeds.align(embed)
        await interaction.response.send_message(embed=embed, ephemeral=True)


    @app_commands.command(
        name="serverstats",
        description="Affiche les statistiques globales du serveur.",
    )
    async def serverstats(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        players = [(uid, s) for uid, s in self.player_stats.items() if s["wins"] > 0 or s.get("losses", 0) > 0]
        total_queues  = self.server_stats.get("total_queues", 0)
        total_wins    = sum(s["wins"] for _, s in players)
        total_players = len(players)

        best_alltime  = max(players, key=lambda x: x[1]["wins"],        default=None)
        best_streak   = max(players, key=lambda x: x[1]["max_streak"],  default=None)
        best_weekly   = max(players, key=lambda x: x[1].get("weekly_wins", 0), default=None)

        embed = embeds.base(
            guild_id,
            title=t(guild_id, "classement.serverstats_title"),
            kind="brand",
            timestamp=True,
            footer=t(guild_id, "classement.serverstats_footer"),
        )
        embeds.brand(embed, interaction.guild)
        embeds.stat(embed, t(guild_id, "classement.serverstats_queues"), total_queues)
        embeds.stat(embed, t(guild_id, "classement.serverstats_players"), total_players)
        embeds.stat(embed, t(guild_id, "classement.serverstats_wins"), total_wins)

        wins_word = t(guild_id, "classement.wins_word")
        streak_word = t(guild_id, "classement.streak_word")
        highlights = []
        if best_alltime and best_alltime[1]["wins"] > 0:
            highlights.append(
                f"🏆  {t(guild_id, 'classement.serverstats_best')} — <@{best_alltime[0]}>"
                f"  **{best_alltime[1]['wins']}** {wins_word}"
            )
        if best_streak and best_streak[1]["max_streak"] > 0:
            highlights.append(
                f"🔥  {t(guild_id, 'classement.serverstats_streak')} — <@{best_streak[0]}>"
                f"  **{best_streak[1]['max_streak']}** {streak_word}"
            )
        if best_weekly and best_weekly[1].get("weekly_wins", 0) > 0:
            highlights.append(
                f"⚡  {t(guild_id, 'classement.serverstats_active')} — <@{best_weekly[0]}>"
                f"  **{best_weekly[1]['weekly_wins']}** {wins_word}"
            )
        if highlights:
            embeds.section(embed, embeds.BLANK, embeds.RULE + "\n" + "\n".join(highlights))
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Classement(bot))
