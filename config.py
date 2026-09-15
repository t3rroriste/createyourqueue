"""
Configuration centralisée du bot CreateYourQueue
==================================================
Modifie les valeurs ici pour adapter le bot sans toucher à la logique.
Les identifiants Discord se règlent dans `.env` (voir `.env.example`) : aucun
ID réel n'est écrit dans le code.
"""

import os
import discord

# ---------------------------------------------------------
# Serveur support
# ID du serveur officiel CYQ : il saute l'assistant de configuration,
# reste toujours en français et n'affiche pas /config.
# 0 (valeur par défaut) = aucun serveur privilégié.
# ---------------------------------------------------------
SUPPORT_GUILD_ID = int(os.getenv("SUPPORT_GUILD_ID", "0"))

# Alias utilisé partout dans le code (compatibilité interne)
GUNZFRANCE_GUILD_ID = SUPPORT_GUILD_ID

# Invitation du serveur d'aide, affichee dans le message d'arrivee.
# Vide = pas de bouton plutot qu'un lien mort.
SUPPORT_INVITE = os.getenv("SUPPORT_INVITE", "").strip()

# Propriétaire du bot, pour les commandes réservées (/waiting, /tempo).
# 0 = le propriétaire de l'application Discord.
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ---------------------------------------------------------
# Cogs chargés au démarrage
# Défini ici (et pas dans bot.py) pour que /diagnostic puisse vérifier
# que tout ce qui devait être chargé l'a bien été.
# ---------------------------------------------------------
INITIAL_EXTENSIONS = [
    # /start, /setup et /onboarding faisaient la même chose que l'assistant
    # (cogs/wizard.py) avec trois interfaces différentes. Un seul chemin :
    # le message d'arrivée, ou /queue.
    "cogs.config",
    "cogs.language",
    "cogs.roles",
    "cogs.queue_config",  # Système de queue
    "cogs.queue_guide",  # Guide pas-à-pas /guide
    "cogs.voice_manager",  # Gestion de la voix du bot
    "cogs.classement",
    "cogs.automation",  # Queue programmee + saisons + podium
    "cogs.poll",  # Sondages a boutons
    "cogs.match",  # Salon de match, capitaines, MVP et MMR
    "cogs.party",  # Groupe
    "cogs.clan",  # Clans permanents
    "cogs.wizard",  # Assistant de configuration
    "cogs.help",
    "cogs.moderation",
    "cogs.antiraid",
    "cogs.antilink",
    "cogs.auto_clean",
    "cogs.logs",
    "cogs.statuspanel",  # Panneau d etat live /status
    "cogs.info",
    "cogs.diagnostic",
    "cogs.guard",  # Protection des noms de salons
    "cogs.reset",  # Remise a zero du serveur
]

# ---------------------------------------------------------
# Commandes qui exigent un serveur configuré (bot principal)
# Seules les commandes de queue attendent la configuration : elles ont besoin
# des salons choisis dans l'assistant. Tout le reste — administration,
# modération, utilitaires — marche dès l'arrivée du bot. /queue n'est pas
# dans la liste : sur un serveur non configuré, elle ouvre l'assistant.
# Une commande à sous-commandes se désigne par son nom racine.
# ---------------------------------------------------------
SETUP_REQUIRED_COMMANDS = frozenset({
    "rematch", "schedule", "history", "bl", "unbl", "groupe", "clan", "clantransfer",
})

# Extensions spécifiques pour le bot temporaire (commandes owner uniquement)
TEMPORARY_EXTENSIONS = [
    "cogs.temp_bot",  # Commandes /waiting et /tempo
    "cogs.ghost",  # Commande /ghost : ghost ping d'arrivée (administrateurs)
]

# Extensions spécifiques pour le bot modmail
MODMAIL_EXTENSIONS = [
    "cogs.modmail",  # Bot de support par MP
]

# Extensions d'accueil (chargées uniquement pour le bot principal)
WELCOME_EXTENSIONS = [
    "cogs.welcome",  # Système d'accueil et sélection de langue
]

# ---------------------------------------------------------
# Bot modmail
# ---------------------------------------------------------
MODMAIL_GUILD_ID = int(os.getenv("MODMAIL_GUILD_ID", "0"))  # Serveur support
MODMAIL_STAFF_CHANNEL_ID = int(os.getenv("MODMAIL_STAFF_CHANNEL_ID", "0"))  # Salon staff privé
# Rôle autorisé à prendre, répondre et fermer un ticket.
# 0 = pas de contrôle : quiconque voit le salon staff peut agir.
MODMAIL_STAFF_ROLE_ID = int(os.getenv("MODMAIL_STAFF_ROLE_ID", "0"))

# Salon qui reçoit les messages de démarrage des bots. 0 = désactivé.
DIAGNOSTIC_CHANNEL_ID = int(os.getenv("DIAGNOSTIC_CHANNEL_ID", "0"))

# ---------------------------------------------------------
# Couleurs des embeds
# ---------------------------------------------------------
# Une seule palette pour tout le bot (voir embeds.py). Les couleurs nommées
# de discord.py — `Color.green()`, `Color.red()` — sont plus saturées que
# celles de l'interface Discord : côte à côte, deux confirmations vertes
# n'avaient pas le même vert selon le cog qui les envoyait.
COLOR_SUCCESS = discord.Color(0x57F287)
COLOR_ERROR   = discord.Color(0xED4245)
COLOR_INFO    = discord.Color(0x5865F2)
COLOR_WARNING = discord.Color(0xFEE75C)
# ---------------------------------------------------------
# Anti-raid
# ---------------------------------------------------------
ANTIRAID_JOIN_THRESHOLD        = 15
ANTIRAID_JOIN_INTERVAL         = 10
ANTIRAID_MIN_ACCOUNT_AGE_HOURS = 1
ANTIRAID_AUTO_KICK             = True

STAFF_ROLE_NAME                 = "Organisateur"
