"""
ClanWar — la session de guerre de clans et ses boutons
======================================================
- ClanWarSession : préparation (15 min), vocaux, présence des chefs, décompte,
  salon de match, abandon, fin et nettoyage.
- ClanWarActionView : les boutons Manche / Abandonner / Problème du salon de match.
- AbandonConfirmView : confirmation de l'abandon par le chef du clan.
- RoundVoteView : le vote qui attribue une manche.

Séparé de cogs/clan.py, qui dépassait 2 800 lignes. Ce n'est pas un cog : pas
de setup(), pas d'entrée dans config.py ; cogs/clan.py l'importe.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import unicodedata
from typing import TYPE_CHECKING, Any

import discord

import embeds
import resources
from guild_settings import (
    MAX_CLAN_NAME, get_clan, set_clan_war_session, clear_clan_war_session,
    get_ticket_config, increment_clan_announcement,
)
from i18n import t
from text_safety import sanitize

from cogs.clan_tickets import TicketProblemModal
from cogs.logs import send_log

if TYPE_CHECKING:
    from cogs.clan import Clan

log = logging.getLogger("bot.clan")


def _slug(name: str) -> str:
    """Nom de salon à partir d'un nom de clan."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", plain).strip("-").lower()
    return slug[:90] or "clan"


# ----------------------------------------------------------------------
# Session de ClanWar
# ----------------------------------------------------------------------
class ClanWarSession:
    """Gère une session de ClanWar après acceptation."""
    
    def __init__(self, cog: "Clan", guild: discord.Guild, clan1: dict, clan2: dict, size: int):
        self.cog = cog
        self.guild = guild
        self.guild_id = guild.id
        self.clan1 = clan1
        self.clan2 = clan2
        self.size = size
        self.started = False
        self.ended = False
        self.preparation_end_time = None
        self.voice_channel = None
        self.team_channels = {}
        self.captain_vote_channel = None
        self.timer_task = None
        self.notification_messages = {}  # channel_id -> message_id
        self.countdown_task = None
        self.countdown_started = False
        self.voice_client = None
        self.leader_timeout_task = None
        self.leader_left_time = None
        self.leader_left_which = None  # "clan1" ou "clan2"
        self.clan1_points = 0
        self.clan2_points = 0
        self.round_votes = {}  # user_id -> clan_choice
        self.main_embed_message = None  # Stocke le message principal pour les mises à jour
    
    def to_dict(self) -> dict[str, Any]:
        """Sérialise la session pour persistance."""
        team1_id = self.team_channels.get("team1").id if self.team_channels.get("team1") else None
        team2_id = self.team_channels.get("team2").id if self.team_channels.get("team2") else None
        
        return {
            "guild_id": self.guild_id,
            "clan1_id": self.clan1["id"],
            "clan2_id": self.clan2["id"],
            "size": self.size,
            "started": self.started,
            "ended": self.ended,
            "preparation_end_time": self.preparation_end_time,
            "voice_channel_id": getattr(self.voice_channel, "id", None),
            "captain_vote_channel_id": getattr(self.captain_vote_channel, "id", None),
            "notification_messages": self.notification_messages,
            "countdown_started": self.countdown_started,
            "team_channels": {
                "team1": team1_id,
                "team2": team2_id,
            },
            "clan1_points": self.clan1_points,
            "clan2_points": self.clan2_points,
            "round_votes": self.round_votes,
        }
    
    @classmethod
    def from_dict(cls, cog: "Clan", guild: discord.Guild, data: dict[str, Any]) -> "ClanWarSession | None":
        """Reconstruit une session depuis les données persistées."""
        if guild is None:
            return None
        
        clan1 = get_clan(guild.id, data.get("clan1_id"))
        clan2 = get_clan(guild.id, data.get("clan2_id"))
        
        if clan1 is None or clan2 is None:
            return None
        
        session = cls(cog, guild, clan1, clan2, data.get("size", 1))
        session.started = data.get("started", False)
        session.ended = data.get("ended", False)
        session.preparation_end_time = data.get("preparation_end_time")
        session.notification_messages = data.get("notification_messages", {})
        session.countdown_started = data.get("countdown_started", False)
        
        # Reconstruire les channels
        voice_channel_id = data.get("voice_channel_id")
        if voice_channel_id:
            session.voice_channel = guild.get_channel(voice_channel_id)
        
        captain_vote_channel_id = data.get("captain_vote_channel_id")
        if captain_vote_channel_id:
            session.captain_vote_channel = guild.get_channel(captain_vote_channel_id)
        
        # Reconstruire les channels d'équipe
        team_channels_data = data.get("team_channels", {})
        session.team_channels = {}
        if team_channels_data.get("team1"):
            session.team_channels["team1"] = guild.get_channel(team_channels_data["team1"])
        if team_channels_data.get("team2"):
            session.team_channels["team2"] = guild.get_channel(team_channels_data["team2"])
        
        # Restaurer les points et votes
        session.clan1_points = data.get("clan1_points", 0)
        session.clan2_points = data.get("clan2_points", 0)
        session.round_votes = data.get("round_votes", {})
        
        return session
        
    def _log(self, key: str, *, user: discord.abc.User | None = None, color: int | None = None,
             winner: str | None = None, loser: str | None = None) -> None:
        """Journal « duel » (voir cogs/logs.py) : les deux clans et le format
        accompagnent chaque étape, pour qu'un log se lise seul."""
        gid = self.guild_id
        name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
        name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
        send_log(self.cog.bot, gid, "duel", t(gid, key), user=user, color=color,
                 description=f"**{name1}** vs **{name2}**",
                 fields=[(t(gid, "logs.f_format"), f"{self.size} vs {self.size}"),
                         (t(gid, "logs.f_score"), f"{self.clan1_points} – {self.clan2_points}"),
                         (t(gid, "logs.f_winner"), winner),
                         (t(gid, "logs.f_loser"), loser)])

    async def start(self):
        """Démarre la session de ClanWar."""
        if self.started:
            return
        
        self.started = True
        self.preparation_end_time = time.time() + 900  # 15 minutes = 900 secondes
        
        # Sauvegarder la session
        set_clan_war_session(self.guild_id, self.to_dict())
        
        # Créer le salon vocal privé pour les 2 clans
        await self._create_war_voice_channel()
        
        # Muter tous les membres sauf les leads
        await self._setup_voice_permissions()
        
        # Envoyer les notifications avec le nouveau format (une seule fois)
        if not self.notification_messages:  # Ne pas envoyer si déjà envoyé
            await self._send_war_notifications()
        
        # Lancer le timer de 15 minutes avec mise à jour du minuteur
        self.timer_task = asyncio.create_task(self._preparation_timer_with_update())
        
        log.info(f"[{self.guild.name}] ClanWar démarré: {self.clan1.get('name')} vs {self.clan2.get('name')} ({self.size}v{self.size})")
    
    async def _create_war_voice_channel(self):
        """Crée un salon vocal privé pour les 2 clans avec limite de joueurs."""
        category = resources.get_category(self.guild, "category_clan")
        if category is None:
            log.error(f"[{self.guild.name}] Pas de catégorie clan pour créer le vocal de ClanWar")
            return
        
        # Récupérer les rôles des 2 clans
        role1 = self.cog.clan_role(self.guild, self.clan1)
        role2 = self.cog.clan_role(self.guild, self.clan2)
        
        if role1 is None or role2 is None:
            log.error(f"[{self.guild.name}] Rôles de clan manquants pour le vocal de ClanWar")
            return
        
        # Permissions : seul les 2 clans et le staff peuvent voir/joindre
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(
                view_channel=False, connect=False
            ),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=True, manage_channels=True
            ),
            role1: discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=False  # Muted par défaut
            ),
            role2: discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=False  # Muted par défaut
            ),
        }
        
        staff = resources.get_role(self.guild, "role_staff")
        if staff is not None:
            overwrites[staff] = discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=True
            )
        
        # Donner le droit de parler aux leads
        leader1 = self.guild.get_member(self.clan1.get("leader_id"))
        leader2 = self.guild.get_member(self.clan2.get("leader_id"))
        
        try:
            name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
            name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
            channel_name = f"⚔️-{_slug(name1)}-vs-{_slug(name2)}"
            
            # Limite de joueurs : size vs size
            user_limit = self.size * 2
            
            self.voice_channel = await self.guild.create_voice_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                user_limit=user_limit,
                reason=f"ClanWar: {name1} vs {name2}"
            )
            
            # Permissions spécifiques pour les leads
            if leader1:
                await self.voice_channel.set_permissions(
                    leader1,
                    speak=True,
                    reason="Lead du clan peut parler"
                )
            if leader2:
                await self.voice_channel.set_permissions(
                    leader2,
                    speak=True,
                    reason="Lead du clan peut parler"
                )
            
            log.info(f"[{self.guild.name}] Vocal créé pour ClanWar: {channel_name} (limite: {user_limit} joueurs)")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour créer le vocal de ClanWar")
        except discord.HTTPException as e:
            log.error(f"[{self.guild.name}] Erreur lors de la création du vocal de ClanWar: {e}")
    
    async def _setup_voice_permissions(self):
        """Configure les permissions vocales pour que seuls les leads puissent parler."""
        if self.voice_channel is None:
            return
        
        # Les permissions sont déjà configurées dans _create_war_voice_channel
        # Cette méthode peut être étendue pour gérer les changements dynamiques
        pass
    
    async def _preparation_timer(self):
        """Gère le timer de 15 minutes de préparation."""
        try:
            # Attendre 15 minutes
            await asyncio.sleep(900)
            
            # Le temps est écoulé, lancer la partie
            await self._start_match()
            
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Timer de ClanWar annulé")
    
    async def _send_war_notifications(self):
        """Envoie les notifications de début de ClanWar avec le nouveau format."""
        gid = self.guild_id
        
        # Calculer le temps initial pour le minuteur
        initial_remaining = self.preparation_end_time - time.time()
        initial_minutes = int(initial_remaining // 60)
        initial_seconds = int(initial_remaining % 60)
        initial_timer = t(gid, "clan.war_timer", 
                         minutes=f"{initial_minutes:02d}", seconds=f"{initial_seconds:02d}")
        
        # Notifier le clan 1
        channel1 = self.cog.clan_channel(self.guild, self.clan1)
        if channel1:
            try:
                voice_mention = self.voice_channel.mention if self.voice_channel else "@vocal"
                base_desc = t(gid, "clan.war_started_desc", voice=voice_mention)
                description = f"{base_desc}\n\n{initial_timer}"
                embed = discord.Embed(
                    title=t(gid, "clan.war_started_title"),
                    description=description,
                    color=embeds.BLACK
                )
                # Pas de footer
                message = await channel1.send(embed=embed)
                self.notification_messages[channel1.id] = message.id
                
                # Incrémenter le compteur d'annonces
                increment_clan_announcement(gid, self.clan1["id"])
            except discord.HTTPException:
                pass
        
        # Notifier le clan 2
        channel2 = self.cog.clan_channel(self.guild, self.clan2)
        if channel2:
            try:
                voice_mention = self.voice_channel.mention if self.voice_channel else "@vocal"
                base_desc = t(gid, "clan.war_started_desc", voice=voice_mention)
                description = f"{base_desc}\n\n{initial_timer}"
                embed = discord.Embed(
                    title=t(gid, "clan.war_started_title"),
                    description=description,
                    color=embeds.BLACK
                )
                # Pas de footer
                message = await channel2.send(embed=embed)
                self.notification_messages[channel2.id] = message.id
                
                # Incrémenter le compteur d'annonces
                increment_clan_announcement(gid, self.clan2["id"])
            except discord.HTTPException:
                pass
    
    async def _preparation_timer_with_update(self):
        """Gère le timer de 15 minutes avec mise à jour visuelle du minuteur."""
        try:
            log.info(f"[{self.guild.name}] Démarrage du timer de préparation")
            # Lancer le monitoring du vocal en parallèle
            monitoring_task = asyncio.create_task(self._monitor_voice_channel_for_leaders())
            log.info(f"[{self.guild.name}] Tâche de monitoring créée")
            
            # Mettre à jour le minuteur chaque seconde
            while time.time() < self.preparation_end_time:
                await self._update_timer_messages()
                await asyncio.sleep(1)
            
            # Temps écoulé - annuler le monitoring et vérifier si le match a commencé
            if not self.ended:
                log.info(f"[{self.guild.name}] Temps écoulé, annulation du monitoring")
                monitoring_task.cancel()
                await self._check_leader_presence_and_start()
            
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Timer de ClanWar annulé")
    
    async def _update_timer_messages(self):
        """Met à jour les messages de notification avec le temps restant."""
        remaining = self.preparation_end_time - time.time()
        if remaining <= 0:
            return
        
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    timer_text = t(self.guild_id, "clan.war_timer", 
                                  minutes=f"{minutes:02d}", seconds=f"{seconds:02d}")
                    
                    # Remplacer le minuteur existant dans la description
                    embed = message.embeds[0] if message.embeds else None
                    if embed:
                        # La description contient le timer à la fin, on le remplace
                        lines = embed.description.split('\n\n')
                        if lines and lines[-1].startswith('⏱️'):
                            # Remplacer la dernière ligne (le timer)
                            lines[-1] = timer_text
                            new_description = '\n\n'.join(lines)
                        else:
                            # Ajouter le timer s'il n'existe pas
                            new_description = embed.description + f"\n\n{timer_text}"
                        
                        new_embed = discord.Embed(
                            title=embed.title,
                            description=new_description,
                            color=embed.color
                        )
                        await message.edit(embed=new_embed)
                except discord.HTTPException:
                    pass
    
    async def _check_leader_presence_and_start(self):
        """Vérifie la présence des leaders et lance le match si présents."""
        if self.ended:
            return
        
        log.info(f"[{self.guild.name}] Vérification de la présence des leaders")
        
        # Vérifier si les leaders sont présents dans le vocal
        leader1_present = False
        leader2_present = False
        
        if self.voice_channel:
            for member in self.voice_channel.members:
                if member.id == self.clan1.get("leader_id"):
                    leader1_present = True
                    log.info(f"[{self.guild.name}] Leader 1 présent: {member.name}")
                elif member.id == self.clan2.get("leader_id"):
                    leader2_present = True
                    log.info(f"[{self.guild.name}] Leader 2 présent: {member.name}")
        
        log.info(f"[{self.guild.name}] Leaders présents: L1={leader1_present}, L2={leader2_present}")
        
        if not leader1_present or not leader2_present:
            # Annuler le ClanWar si un leader est absent
            log.warning(f"[{self.guild.name}] Un leader est absent, annulation du ClanWar")
            await self._cancel_due_to_missing_leader()
            return
        
        # Les leaders sont présents, lancer le monitoring du vocal
        log.info(f"[{self.guild.name}] Les deux leaders sont présents, lancement du monitoring")
        await self._monitor_voice_channel()
    
    async def _cancel_due_to_missing_leader(self):
        """Annule le ClanWar car un leader est absent."""
        self.ended = True
        self._log("logs.duel_leader_missing", color=embeds.WARNING)
        
        # Nettoyer la session persistée
        clear_clan_war_session(self.guild_id)
        
        # Envoyer les notifications d'annulation
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = embeds.base(
                        self.guild_id,
                        description=t(self.guild_id, "clan.war_leader_missing"),
                        kind="error"
                    )
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
        
        # Nettoyer les channels
        await self.cancel()
        
        log.info(f"[{self.guild.name}] ClanWar annulé: leader absent")
    
    async def _monitor_voice_channel_for_leaders(self):
        """Surveille le salon vocal et lance le match quand les 2 leaders sont présents et le vocal est plein."""
        log.info(f"[{self.guild.name}] === DÉBUT DU MONITORING DU VOCAL ===")
        
        if not self.voice_channel:
            log.warning(f"[{self.guild.name}] Aucun channel vocal")
            return
        
        max_players = self.size * 2  # size vs size
        log.info(f"[{self.guild.name}] Monitoring du vocal: limite={max_players}, channel={self.voice_channel.name}")
        
        try:
            while not self.ended:
                # Vérifier si les 2 leaders sont présents
                leader1_present = False
                leader2_present = False
                
                for member in self.voice_channel.members:
                    if member.id == self.clan1.get("leader_id"):
                        leader1_present = True
                    elif member.id == self.clan2.get("leader_id"):
                        leader2_present = True
                
                current_players = len(self.voice_channel.members)
                
                log.info(f"[{self.guild.name}] Leaders présents: L1={leader1_present}, L2={leader2_present}, Joueurs: {current_players}/{max_players}")
                
                # Vérifier les deux conditions : vocal plein ET leaders présents
                if leader1_present and leader2_present and current_players >= max_players:
                    # Les 2 leaders sont présents ET le vocal est plein, lancer le match
                    log.info(f"[{self.guild.name}] Conditions remplies! Lancement du match")
                    await self._start_match()
                    return
                
                # Attendre 2 secondes avant de vérifier à nouveau
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Monitoring des leaders annulé")
        except Exception as e:
            log.error(f"[{self.guild.name}] Erreur dans le monitoring: {e}")
        
        log.info(f"[{self.guild.name}] === FIN DU MONITORING DU VOCAL ===")
    
    async def _monitor_voice_channel(self):
        """Surveille le salon vocal et lance le match quand il est plein."""
        if not self.voice_channel:
            log.warning(f"[{self.guild.name}] Aucun channel vocal, lancement direct du match")
            await self._start_match()
            return
        
        max_players = self.size * 2  # size vs size
        log.info(f"[{self.guild.name}] Monitoring du vocal: limite={max_players}, channel={self.voice_channel.name}")
        
        try:
            while not self.ended:
                current_players = len(self.voice_channel.members)
                log.info(f"[{self.guild.name}] Joueurs dans le vocal: {current_players}/{max_players}")
                
                if current_players >= max_players:
                    # Le salon est plein, lancer le compte à rebours de 30 secondes
                    log.info(f"[{self.guild.name}] Salon plein! Lancement du countdown")
                    if not self.countdown_started:
                        self.countdown_started = True
                        await self._start_countdown()
                    # Le countdown gère le lancement du match, on attend qu'il se termine
                    return
                else:
                    # Attendre 5 secondes avant de vérifier à nouveau
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Monitoring du vocal annulé")
    
    async def _start_countdown(self):
        """Lance le compte à rebours de 30 secondes."""
        countdown = 30
        log.info(f"[{self.guild.name}] Countdown démarré: {countdown}s")
        
        try:
            while countdown > 0 and not self.ended:
                max_players = self.size * 2
                current_players = len(self.voice_channel.members) if self.voice_channel else 0
                
                log.info(f"[{self.guild.name}] Countdown: {countdown}s, joueurs: {current_players}/{max_players}")
                
                if current_players < max_players:
                    # Un joueur a quitté, réinitialiser le compte à rebours
                    log.warning(f"[{self.guild.name}] Joueur parti! Réinitialisation du countdown")
                    await self._notify_player_left()
                    countdown = 30
                    await asyncio.sleep(5)
                    continue
                
                # Mettre à jour le compte à rebours
                if countdown % 10 == 0 or countdown <= 5:
                    await self._send_countdown_update(countdown)
                
                await asyncio.sleep(1)
                countdown -= 1
            
            if countdown <= 0 and not self.ended:
                # Le compte à rebours est terminé, lancer le match
                log.info(f"[{self.guild.name}] Countdown terminé, lancement du match")
                await self._start_match()
        
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Compte à rebours annulé")
    
    async def _notify_player_left(self):
        """Notifie qu'un joueur a quitté le vocal."""
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = embeds.base(
                        self.guild_id,
                        description=t(self.guild_id, "clan.war_player_left"),
                        kind="warning"
                    )
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
    
    async def _send_countdown_update(self, countdown):
        """Envoie une mise à jour du compte à rebours."""
        if countdown == 30:
            message = t(self.guild_id, "clan.war_full_warning")
        elif countdown <= 5:
            message = t(self.guild_id, "clan.war_starting")
        else:
            return
        
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = embeds.base(
                        self.guild_id,
                        description=message,
                        kind="success"
                    )
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
    
    async def _start_match(self):
        """Lance la partie après la période de préparation."""
        log.info(f"[{self.guild.name}] === DÉBUT DE _start_match ===")
        
        if self.ended:
            log.warning(f"[{self.guild.name}] Match déjà terminé, annulation")
            return
        
        self.ended = True
        
        # Nettoyer la session persistée car la phase de préparation est terminée
        log.info(f"[{self.guild.name}] Nettoyage de la session persistée")
        clear_clan_war_session(self.guild_id)
        self._log("logs.duel_started", color=embeds.SUCCESS)
        
        # Envoyer un message pour dire que le match est lancé
        log.info(f"[{self.guild.name}] Envoi de la notification de démarrage")
        await self._send_match_started_notification()
        
        # Créer les channels vocaux séparés pour chaque équipe (déplace les joueurs)
        log.info(f"[{self.guild.name}] Création des channels vocaux d'équipe")
        await self._create_team_voice_channels()
        
        # Le bot rejoint le vocal pour annoncer que le match va commencer
        log.info(f"[{self.guild.name}] Tentative de rejoindre le vocal pour annoncer le début")
        await self._bot_voice_announce()
        
        # Attendre 15 secondes avant de déplacer les joueurs
        log.info(f"[{self.guild.name}] Attente de 15 secondes avant le déplacement des joueurs")
        await asyncio.sleep(15)
        
        # Déplacer les membres du vocal de préparation vers leurs vocaux d'équipe
        log.info(f"[{self.guild.name}] Déplacement des joueurs vers leurs vocaux d'équipe")
        if self.voice_channel:
            for member in self.voice_channel.members:
                if member.id in self.clan1.get("members", []):
                    try:
                        await member.move_to(self.team_channels["team1"])
                        log.info(f"[{self.guild.name}] {member.name} déplacé vers {self.team_channels['team1'].name}")
                    except discord.HTTPException:
                        pass
                elif member.id in self.clan2.get("members", []):
                    try:
                        await member.move_to(self.team_channels["team2"])
                        log.info(f"[{self.guild.name}] {member.name} déplacé vers {self.team_channels['team2'].name}")
                    except discord.HTTPException:
                        pass
        
        # Attendre 15 secondes avant de déplacer les joueurs
        log.info(f"[{self.guild.name}] Attente de 15 secondes avant le déplacement des joueurs")
        await asyncio.sleep(15)
        
        # Déplacer les membres du vocal de préparation vers leurs vocaux d'équipe
        log.info(f"[{self.guild.name}] Déplacement des joueurs vers leurs vocaux d'équipe")
        if self.voice_channel:
            for member in self.voice_channel.members:
                if member.id in self.clan1.get("members", []):
                    try:
                        await member.move_to(self.team_channels["team1"])
                        log.info(f"[{self.guild.name}] {member.name} déplacé vers {self.team_channels['team1'].name}")
                    except discord.HTTPException:
                        pass
                elif member.id in self.clan2.get("members", []):
                    try:
                        await member.move_to(self.team_channels["team2"])
                        log.info(f"[{self.guild.name}] {member.name} déplacé vers {self.team_channels['team2'].name}")
                    except discord.HTTPException:
                        pass
        
        # Créer le channel textuel avec le nouveau système de points
        log.info(f"[{self.guild.name}] Création du channel textuel")
        await self._create_match_text_channel()
        
        # Lancer la surveillance des leaders pour le timeout
        log.info(f"[{self.guild.name}] Lancement de la surveillance des leaders")
        self.leader_timeout_task = asyncio.create_task(self._monitor_leader_timeout())
        
        log.info(f"[{self.guild.name}] ClanWar lancé: {self.clan1.get('name')} vs {self.clan2.get('name')}")
        log.info(f"[{self.guild.name}] === FIN DE _start_match ===")
    
    async def _send_match_started_notification(self):
        """Envoie une notification que le match est lancé."""
        gid = self.guild_id
        name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
        name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
        
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = discord.Embed(
                        title=t(gid, "clan.war_start_title"),
                        description=t(gid, "clan.war_start_desc",
                                     clan1=name1, clan2=name2, size=self.size),
                        color=embeds.BLACK
                    )
                    # Pas de footer
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
    
    async def _create_team_voice_channels(self):
        """Crée des channels vocaux séparés pour chaque équipe et y déplace les joueurs."""
        category = resources.get_category(self.guild, "category_clan")
        if category is None:
            log.error(f"[{self.guild.name}] Pas de catégorie clan pour créer les vocaux d'équipe")
            return
        
        # Récupérer les rôles des 2 clans
        role1 = self.cog.clan_role(self.guild, self.clan1)
        role2 = self.cog.clan_role(self.guild, self.clan2)
        
        if role1 is None or role2 is None:
            log.error(f"[{self.guild.name}] Rôles de clan manquants pour les vocaux d'équipe")
            return
        
        try:
            name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
            name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
            
            # Créer le vocal pour l'équipe 1
            overwrites1 = {
                self.guild.default_role: discord.PermissionOverwrite(
                    view_channel=False, connect=False
                ),
                self.guild.me: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True, manage_channels=True
                ),
                role1: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                ),
            }
            
            staff = resources.get_role(self.guild, "role_staff")
            if staff is not None:
                overwrites1[staff] = discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                )
            
            channel1 = await self.guild.create_voice_channel(
                name=f"🎮-{_slug(name1)}",
                category=category,
                overwrites=overwrites1,
                user_limit=self.size,
                reason=f"ClanWar: Équipe {name1}"
            )
            self.team_channels["team1"] = channel1
            log.info(f"[{self.guild.name}] Vocal créé pour l'équipe 1: {channel1.name}")
            
            # Créer le vocal pour l'équipe 2
            overwrites2 = {
                self.guild.default_role: discord.PermissionOverwrite(
                    view_channel=False, connect=False
                ),
                self.guild.me: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True, manage_channels=True
                ),
                role2: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                ),
            }
            
            if staff is not None:
                overwrites2[staff] = discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                )
            
            channel2 = await self.guild.create_voice_channel(
                name=f"🎮-{_slug(name2)}",
                category=category,
                overwrites=overwrites2,
                user_limit=self.size,
                reason=f"ClanWar: Équipe {name2}"
            )
            self.team_channels["team2"] = channel2
            log.info(f"[{self.guild.name}] Vocal créé pour l'équipe 2: {channel2.name}")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour créer les vocaux d'équipe")
        except discord.HTTPException as e:
            log.error(f"[{self.guild.name}] Erreur lors de la création des vocaux d'équipe: {e}")
    
    async def _monitor_leader_timeout(self):
        """Surveille quand un leader quitte le vocal et lance un timer de 10 minutes."""
        log.info(f"[{self.guild.name}] === DÉBUT SURVEILLANCE TIMEOUT LEADER ===")
        
        try:
            while not self.ended:
                # Vérifier si les leaders sont dans n'importe quel vocal
                leader1_in_voice = False
                leader2_in_voice = False
                
                # Vérifier dans tous les vocaux du serveur
                for channel in self.guild.voice_channels:
                    for member in channel.members:
                        if member.id == self.clan1.get("leader_id"):
                            leader1_in_voice = True
                        elif member.id == self.clan2.get("leader_id"):
                            leader2_in_voice = True
                
                log.info(f"[{self.guild.name}] Leaders en vocal: L1={leader1_in_voice}, L2={leader2_in_voice}")
                
                # Si un leader n'est pas en vocal
                if not leader1_in_voice or not leader2_in_voice:
                    # Déterminer quel leader est absent
                    absent_leader = "clan1" if not leader1_in_voice else "clan2"
                    
                    # Si ce n'est pas déjà enregistré
                    if self.leader_left_which is None:
                        self.leader_left_which = absent_leader
                        self.leader_left_time = time.time()
                        log.warning(f"[{self.guild.name}] Leader {absent_leader} a quitté le vocal! Timer de 10min lancé")
                    
                    # Vérifier si 10 minutes se sont écoulées
                    if time.time() - self.leader_left_time >= 600:  # 10 minutes = 600 secondes
                        log.warning(f"[{self.guild.name}] Timeout de 10 minutes écoulé! Victoire par abandon")
                        await self._declare_winner_by_timeout()
                        return
                else:
                    # Les deux leaders sont en vocal, réinitialiser le timer
                    if self.leader_left_which is not None:
                        log.info(f"[{self.guild.name}] Leaders revenus, timer réinitialisé")
                        self.leader_left_which = None
                        self.leader_left_time = None
                
                # Attendre 10 secondes avant de vérifier à nouveau
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            log.info(f"[{self.guild.name}] Surveillance timeout leader annulée")
        except Exception as e:
            log.error(f"[{self.guild.name}] Erreur dans la surveillance timeout: {e}")
        
        log.info(f"[{self.guild.name}] === FIN SURVEILLANCE TIMEOUT LEADER ===")
    
    async def _declare_winner_by_timeout(self):
        """Déclare le vainqueur par timeout du leader adverse."""
        if self.leader_left_which == "clan1":
            winner = self.clan2
            loser = self.clan1
        else:
            winner = self.clan1
            loser = self.clan2
        
        winner_name = sanitize(winner.get("name", "?"), MAX_CLAN_NAME)
        loser_name = sanitize(loser.get("name", "?"), MAX_CLAN_NAME)
        
        log.info(f"[{self.guild.name}] Victoire par abandon: {winner_name} gagne contre {loser_name}")
        self._log("logs.duel_timeout", winner=winner_name, loser=loser_name)
        
        # Notifier les deux clans
        for channel_id, message_id in self.notification_messages.items():
            channel = self.guild.get_channel(channel_id)
            if channel:
                try:
                    embed = discord.Embed(
                        title=t(self.guild_id, "clan.war_timeout_title"),
                        description=t(self.guild_id, "clan.war_timeout_desc", winner=winner_name, loser=loser_name),
                        color=embeds.BLACK
                    )
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass
        
        # Terminer la session
        await self.cancel()
    
    async def _bot_voice_announce(self):
        """Le bot rejoint le vocal et annonce le début de la partie."""
        if self.voice_channel is None:
            log.warning(f"[{self.guild.name}] Aucun channel vocal pour l'annonce")
            return
        
        try:
            log.info(f"[{self.guild.name}] Tentative de connexion au vocal: {self.voice_channel.name}")
            # Connecter le bot au vocal
            voice_client = await self.voice_channel.connect()
            
            # Jouer l'annonce vocale
            from cogs.queue_config import voice_announce_path
            voice_file = voice_announce_path(self.guild_id)
            
            if os.path.exists(voice_file):
                audio_source = discord.FFmpegPCMAudio(voice_file)
                voice_client.play(audio_source)
                
                # Attendre que l'audio soit terminé
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)
            else:
                log.warning(f"[{self.guild.name}] Fichier audio non trouvé: {voice_file}")
            
            # Se déconnecter après l'annonce
            await voice_client.disconnect()
            
            log.info(f"[{self.guild.name}] Annonce vocale terminée pour ClanWar")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour rejoindre le vocal")
        except Exception as e:
            log.error(f"[{self.guild.name}] Erreur lors de l'annonce vocale: {e}")
    
    async def _create_match_text_channel(self):
        """Crée un channel textuel pour le match avec le système de points et de vote de manche."""
        category = resources.get_category(self.guild, "category_clan")
        if category is None:
            log.error(f"[{self.guild.name}] Pas de catégorie clan pour créer le channel de match")
            return
        
        # Récupérer les rôles des 2 clans
        role1 = self.cog.clan_role(self.guild, self.clan1)
        role2 = self.cog.clan_role(self.guild, self.clan2)
        
        if role1 is None or role2 is None:
            log.error(f"[{self.guild.name}] Rôles de clan manquants pour le channel de match")
            return
        
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_messages=True
            ),
            role1: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            role2: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        
        staff = resources.get_role(self.guild, "role_staff")
        if staff is not None:
            overwrites[staff] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )
        
        try:
            name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
            name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
            channel_name = f"🎮-{_slug(name1)}-vs-{_slug(name2)}"
            
            self.captain_vote_channel = await self.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Match ClanWar: {name1} vs {name2}"
            )
            
            # Envoyer le message de début avec le système de points
            embed = discord.Embed(
                title=f"🛡️ {name1} vs {name2}",
                description=t(self.guild_id, "clan.war_points_desc", clan1=name1, clan2=name2, points1=self.clan1_points, points2=self.clan2_points),
                color=embeds.BLACK
            )
            
            self.main_embed_message = await self.captain_vote_channel.send(embed=embed, view=ClanWarActionView(self))
            
            log.info(f"[{self.guild.name}] Channel de match créé: {channel_name}")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour créer le channel de match")
        except discord.HTTPException as e:
            log.error(f"[{self.guild.name}] Erreur lors de la création du channel de match: {e}")
    
    async def _create_empty_channel(self):
        """Crée un channel vide si l'option capitaine est désactivée."""
        category = resources.get_category(self.guild, "category_clan")
        if category is None:
            return
        
        # Récupérer les rôles des 2 clans
        role1 = self.cog.clan_role(self.guild, self.clan1)
        role2 = self.cog.clan_role(self.guild, self.clan2)
        
        if role1 is None or role2 is None:
            return
        
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_messages=True
            ),
            role1: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            role2: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        
        staff = resources.get_role(self.guild, "role_staff")
        if staff is not None:
            overwrites[staff] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )
        
        try:
            name1 = sanitize(self.clan1.get("name", "?"), MAX_CLAN_NAME)
            name2 = sanitize(self.clan2.get("name", "?"), MAX_CLAN_NAME)
            channel_name = f"🎮-{_slug(name1)}-vs-{_slug(name2)}"
            
            self.captain_vote_channel = await self.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"ClanWar: {name1} vs {name2}"
            )
            
            # Envoyer un message simple
            await self.captain_vote_channel.send(
                embed=embeds.base(
                    self.guild_id,
                    title=t(self.guild_id, "clan.war_start_title"),
                    description=t(self.guild_id, "clan.war_start_desc",
                                 clan1=name1, clan2=name2, size=self.size),
                    kind="success"
                )
            )
            
            log.info(f"[{self.guild.name}] Channel vide créé pour ClanWar: {channel_name}")
            
        except discord.Forbidden:
            log.error(f"[{self.guild.name}] Permission refusée pour créer le channel")
        except discord.HTTPException as e:
            log.error(f"[{self.guild.name}] Erreur lors de la création du channel: {e}")
    
    async def forfeit(self, leader_id: int) -> None:
        """Abandon demandé par le chef d'un des deux clans : l'autre clan gagne."""
        if self.ended:
            return
        if leader_id == self.clan1.get("leader_id"):
            loser, winner = self.clan1, self.clan2
        else:
            loser, winner = self.clan2, self.clan1
        winner_name = sanitize(winner.get("name", "?"), MAX_CLAN_NAME)
        loser_name = sanitize(loser.get("name", "?"), MAX_CLAN_NAME)
        log.info(f"[{self.guild.name}] ClanWar abandonné par {loser_name} : victoire de {winner_name}")
        self._log("logs.duel_forfeit", user=self.guild.get_member(leader_id),
                  winner=winner_name, loser=loser_name)
        embed = discord.Embed(
            title=t(self.guild_id, "clan.war_forfeit_title"),
            description=t(self.guild_id, "clan.war_forfeit_desc", winner=winner_name, loser=loser_name),
            color=embeds.BLACK,
        )
        # Les clés deviennent des chaînes quand la session est relue depuis le disque.
        for channel_id in list(self.notification_messages):
            channel = self.guild.get_channel(int(channel_id))
            if channel is None:
                continue
            try:
                await channel.send(embed=embed)
            except discord.HTTPException as e:
                log.warning(f"[{self.guild.name}] Annonce d'abandon non envoyée : {e}")
        await self.cancel()
        active = getattr(self.cog, "active_war_sessions", None)
        if isinstance(active, dict):
            active.pop(str(self.guild_id), None)

    async def cancel(self):
        """Annule la session de ClanWar."""
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
        if self.countdown_task and not self.countdown_task.done():
            self.countdown_task.cancel()
        if self.leader_timeout_task and not self.leader_timeout_task.done():
            self.leader_timeout_task.cancel()
        
        self.ended = True
        
        # Nettoyer les channels créés
        if self.voice_channel:
            try:
                await self.voice_channel.delete(reason="ClanWar annulé")
            except discord.HTTPException:
                pass
        
        for channel in self.team_channels.values():
            if channel:
                try:
                    await channel.delete(reason="ClanWar annulé")
                except discord.HTTPException:
                    pass
        
        if self.captain_vote_channel:
            try:
                await self.captain_vote_channel.delete(reason="ClanWar annulé")
            except discord.HTTPException:
                pass
        
        # Nettoyer la session persistée
        clear_clan_war_session(self.guild_id)
        
        log.info(f"[{self.guild.name}] ClanWar annulé: {self.clan1.get('name')} vs {self.clan2.get('name')}")


class ClanWarActionView(discord.ui.View):
    """Boutons d'action pour le ClanWar (Manche, Abandonné, Problème)."""
    
    def __init__(self, session: "ClanWarSession"):
        super().__init__(timeout=None)
        self.session = session
        gid = session.guild_id
        self.round.label = t(gid, "clan.war_btn_round")
        self.abandon.label = t(gid, "clan.war_btn_abandon")
        self.problem.label = t(gid, "clan.war_btn_problem")
    
    @discord.ui.button(label="Manche", style=discord.ButtonStyle.secondary, emoji="🏴", custom_id="cyq:clanwar:round")
    async def round(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Lance le vote pour la manche."""
        session = self.session
        gid = interaction.guild_id
        
        # Vérifier que c'est un membre d'un clan
        user = interaction.user
        if user.id not in session.clan1.get("members", []) and user.id not in session.clan2.get("members", []):
            await interaction.response.send_message(t(gid, "clan.war_err_member_vote"), ephemeral=True)
            return
        
        # Ouvrir le modal de vote de manche
        await interaction.response.send_message(
            embed=discord.Embed(
                title=t(gid, "clan.war_round_vote_title"),
                description=t(gid, "clan.war_round_vote_desc"),
                color=embeds.BLACK
            ),
            view=RoundVoteView(session),
            ephemeral=True
        )
    
    @discord.ui.button(label="Abandonné", style=discord.ButtonStyle.secondary, emoji="🏳", custom_id="cyq:clanwar:abandon")
    async def abandon(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """L'abandon du ClanWar."""
        session = self.session
        gid = interaction.guild_id
        
        # Vérifier que c'est un leader
        user = interaction.user
        if user.id != session.clan1.get("leader_id") and user.id != session.clan2.get("leader_id"):
            await interaction.response.send_message(t(gid, "clan.err_leader_only"), ephemeral=True)
            return
        
        # Confirmer l'abandon
        await interaction.response.send_message(
            embed=embeds.base(gid, description=t(gid, "clan.war_abandon_confirm"), kind="warning"),
            view=AbandonConfirmView(session, user.id),
            ephemeral=True
        )
    
    @discord.ui.button(label="Problème", style=discord.ButtonStyle.secondary, emoji="⚠️", custom_id="cyq:clanwar:problem")
    async def problem(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Signale un problème au staff via ticket."""
        session = self.session
        gid = interaction.guild_id
        
        # Vérifier que c'est un membre d'un clan
        user = interaction.user
        if user.id not in session.clan1.get("members", []) and user.id not in session.clan2.get("members", []):
            await interaction.response.send_message(t(gid, "clan.war_err_member_problem"), ephemeral=True)
            return
        
        # Vérifier si le système de ticket est configuré
        ticket_config = get_ticket_config(gid)
        log.info(f"[{session.guild.name}] Vérification ticket: config={ticket_config}, enabled={ticket_config.get('enabled', False) if ticket_config else None}")
        
        if not ticket_config or not ticket_config.get("enabled", False):
            await interaction.response.send_message(
                t(gid, "clan.ticket_disabled"),
                ephemeral=True
            )
            return
        
        # Ouvrir le modal de ticket
        await interaction.response.send_modal(TicketProblemModal(session))


class AbandonConfirmView(discord.ui.View):
    """Confirmation de l'abandon d'un ClanWar, réservée au chef qui l'a demandé."""

    def __init__(self, session: "ClanWarSession", leader_id: int):
        super().__init__(timeout=60)
        self.session = session
        self.leader_id = leader_id
        gid = session.guild_id
        self.confirm.label = t(gid, "clan.war_abandon_yes")
        self.keep_playing.label = t(gid, "clan.war_abandon_no")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.leader_id:
            return True
        await interaction.response.send_message(t(interaction.guild_id, "clan.err_leader_only"), ephemeral=True)
        return False

    @discord.ui.button(label="Abandonner", style=discord.ButtonStyle.danger, emoji="🏳")
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        gid = interaction.guild_id
        if self.session.ended:
            await interaction.response.edit_message(
                embed=embeds.base(gid, description=t(gid, "clan.war_gone"), kind="error"), view=None)
            return
        await interaction.response.edit_message(
            embed=embeds.base(gid, description=t(gid, "clan.war_abandon_done"), kind="warning"), view=None)
        await self.session.forfeit(self.leader_id)

    @discord.ui.button(label="Continuer", style=discord.ButtonStyle.secondary)
    async def keep_playing(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        gid = interaction.guild_id
        await interaction.response.edit_message(
            embed=embeds.base(gid, description=t(gid, "clan.war_abandon_cancelled"), kind="brand"), view=None)


class RoundVoteView(discord.ui.View):
    """View pour voter quelle équipe a gagné la manche."""
    
    def __init__(self, session: "ClanWarSession"):
        super().__init__(timeout=None)
        self.session = session
        # Les boutons portent le nom des clans plutôt que « Clan 1 » / « Clan 2 ».
        self.vote_clan1.label = sanitize(session.clan1.get("name", "?"), MAX_CLAN_NAME)[:80]
        self.vote_clan2.label = sanitize(session.clan2.get("name", "?"), MAX_CLAN_NAME)[:80]
    
    @discord.ui.button(label="Clan 1", style=discord.ButtonStyle.primary)
    async def vote_clan1(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Vote pour le clan 1."""
        await self._record_vote(interaction, "clan1")
    
    @discord.ui.button(label="Clan 2", style=discord.ButtonStyle.primary)
    async def vote_clan2(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Vote pour le clan 2."""
        await self._record_vote(interaction, "clan2")
    
    async def _record_vote(self, interaction: discord.Interaction, clan_choice: str) -> None:
        """Enregistre le vote et affiche les résultats."""
        session = self.session
        user = interaction.user
        
        # Vérifier si l'utilisateur a déjà voté
        if user.id in session.round_votes:
            await interaction.response.send_message(t(session.guild_id, "clan.war_err_already_voted"), ephemeral=True)
            return
        
        # Enregistrer le vote
        session.round_votes[user.id] = clan_choice
        
        # Compter les votes
        clan1_votes = sum(1 for v in session.round_votes.values() if v == "clan1")
        clan2_votes = sum(1 for v in session.round_votes.values() if v == "clan2")
        
        # Déterminer le gagnant
        winner = "clan1" if clan1_votes > clan2_votes else "clan2"
        
        # Mettre à jour les points
        if winner == "clan1":
            session.clan1_points += 1
        else:
            session.clan2_points += 1
        voted = session.clan1 if clan_choice == "clan1" else session.clan2
        send_log(interaction.client, session.guild_id, "duel", t(session.guild_id, "logs.duel_round"), user=user,
                 description=t(session.guild_id, "logs.duel_round_desc", player=user.mention,
                               clan=sanitize(voted.get("name", "?"), MAX_CLAN_NAME)),
                 fields=[(t(session.guild_id, "logs.f_score"),
                          f"{sanitize(session.clan1.get('name', '?'), MAX_CLAN_NAME)} {session.clan1_points}"
                          f" – {session.clan2_points} {sanitize(session.clan2.get('name', '?'), MAX_CLAN_NAME)}")])
        
        # Créer le message de résultats temporaire
        name1 = sanitize(session.clan1.get("name", "?"), MAX_CLAN_NAME)
        name2 = sanitize(session.clan2.get("name", "?"), MAX_CLAN_NAME)
        
        vote_list = []
        for user_id, choice in session.round_votes.items():
            member = session.guild.get_member(user_id)
            if member:
                clan_name = name1 if choice == "clan1" else name2
                vote_list.append(t(session.guild_id, "clan.war_vote_line", player=member.mention, clan=clan_name))
        
        result_embed = discord.Embed(
            title=t(session.guild_id, "clan.war_round_result_title"),
            description=t(session.guild_id, "clan.war_round_result_desc", clan1=name1, votes1=clan1_votes, clan2=name2, votes2=clan2_votes),
            color=embeds.BLACK
        )
        
        if vote_list:
            result_embed.add_field(name=t(session.guild_id, "clan.war_votes_field"), value="\n".join(vote_list))
        
        await interaction.response.edit_message(
            embed=result_embed,
            view=None
        )
        
        # Mettre à jour le message principal avec les nouveaux points (éditer le message existant)
        if session.main_embed_message:
            main_embed = discord.Embed(
                title=f"🛡️ {name1} vs {name2}",
                description=t(session.guild_id, "clan.war_points_desc", clan1=name1, clan2=name2, points1=session.clan1_points, points2=session.clan2_points),
                color=embeds.BLACK
            )
            # Réinitialiser les votes pour la prochaine manche
            session.round_votes = {}
            
            # Éditer le message principal existant
            await session.main_embed_message.edit(embed=main_embed, view=ClanWarActionView(session))
