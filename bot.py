"""
CreateYourQueue — point d'entrée
================================
Lance un ou plusieurs bots Discord dans le même programme. Chacun a son token
dans `.env` et sa liste de cogs dans `config.py`.

    python bot.py --bot main         le bot principal
    python bot.py --bot temporaire   le bot temporaire (/waiting, /tempo)
    python bot.py --bot modmail      le bot de support par MP
    python bot.py --bot both         principal + temporaire
    python bot.py                    les trois (exige les trois tokens)
"""

import argparse
import asyncio
import logging
import os
import socket

from dotenv import load_dotenv

# .env AVANT tout import du projet : config.py lit ses variables au moment où
# il est importé. Chargé après, .env arrivait trop tard — SUPPORT_GUILD_ID et
# les IDs du modmail gardaient leur valeur par défaut, quoi qu'on y écrive.
load_dotenv()

import discord
from discord import app_commands
from discord.ext import commands

import embeds
from command_sync import sync_if_changed
from config import (
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_WARNING,
    DIAGNOSTIC_CHANNEL_ID,
    INITIAL_EXTENSIONS,
    MODMAIL_EXTENSIONS,
    TEMPORARY_EXTENSIONS,
    WELCOME_EXTENSIONS,
)
from guild_settings import is_setup_complete, load_settings
from i18n import load_langs, t

# ---------------------------------------------------------
# Logging — configuré avant de charger les données, qui peuvent signaler
# un fichier illisible.
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
)
log = logging.getLogger("bot")

# Couleurs pour les diagnostics
DIAGNOSTIC_COLOR_SUCCESS = COLOR_SUCCESS
DIAGNOSTIC_COLOR_ERROR = COLOR_ERROR

# Stockage partagé pour les IDs de messages de diagnostic
diagnostic_message_ids = {}

load_langs()
load_settings()

# Parser d'arguments pour le choix du bot
parser = argparse.ArgumentParser(description="CreateYourQueue Bot")
parser.add_argument("--bot", choices=["main", "temporaire", "modmail", "both", "all"], default="all",
                    help="Quel bot lancer (main, temporaire, modmail, both pour main+temporaire, ou all pour les trois)")
args = parser.parse_args()

# Vérification des tokens
MAIN_TOKEN = os.getenv("DISCORD_TOKEN")
TEMP_TOKEN = os.getenv("DISCORD_TOKEN_TEMPORAIRE")
MODMAIL_TOKEN = os.getenv("DISCORD_TOKEN_MODMAIL")

if args.bot == "all":
    if not MAIN_TOKEN:
        raise RuntimeError("DISCORD_TOKEN manquant ! Ajoute-le dans le fichier .env")
    if not TEMP_TOKEN:
        raise RuntimeError("DISCORD_TOKEN_TEMPORAIRE manquant ! Ajoute-le dans le fichier .env")
    if not MODMAIL_TOKEN:
        raise RuntimeError("DISCORD_TOKEN_MODMAIL manquant ! Ajoute-le dans le fichier .env")
elif args.bot == "both":
    if not MAIN_TOKEN:
        raise RuntimeError("DISCORD_TOKEN manquant ! Ajoute-le dans le fichier .env")
    if not TEMP_TOKEN:
        raise RuntimeError("DISCORD_TOKEN_TEMPORAIRE manquant ! Ajoute-le dans le fichier .env")
elif args.bot == "main":
    if not MAIN_TOKEN:
        raise RuntimeError("DISCORD_TOKEN manquant ! Ajoute-le dans le fichier .env")
elif args.bot == "temporaire":
    if not TEMP_TOKEN:
        raise RuntimeError("DISCORD_TOKEN_TEMPORAIRE manquant ! Ajoute-le dans le fichier .env")
elif args.bot == "modmail":
    if not MODMAIL_TOKEN:
        raise RuntimeError("DISCORD_TOKEN_MODMAIL manquant ! Ajoute-le dans le fichier .env")

# ---------------------------------------------------------
# Intents
# ---------------------------------------------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True


class CreateYourQueueBot(commands.Bot):
    """Bot standard, avec un arrêt propre.

    close() est appelé par `async with bot:` aussi bien à l'arrêt normal qu'au
    Ctrl+C. C'est le seul endroit où le bot est encore connecté tout en sachant
    qu'il va s'éteindre : on en profite pour basculer le panneau d'état en
    HORS LIGNE avant de perdre la connexion."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diagnostic_channel_id = DIAGNOSTIC_CHANNEL_ID
        # Remplacé par run_bot() : c'est la clé du message de diagnostic.
        # Resté à « Bot », il ne correspondait à aucun message, et le passage
        # en HORS LIGNE à l'arrêt n'avait jamais lieu.
        self.bot_name = "Bot"
        self.presence_task: asyncio.Task | None = None

    async def send_diagnostic(self, bot_name: str, status: str = "online", has_error: bool = False):
        """Envoie ou met à jour un message de diagnostic dans le channel configuré."""
        if self.diagnostic_channel_id == 0:
            return  # Pas de channel de diagnostic configuré

        try:
            diagnostic_channel = self.get_channel(self.diagnostic_channel_id)
            if not diagnostic_channel:
                log.warning(f"Channel diagnostic introuvable: {self.diagnostic_channel_id}")
                return

            # Déterminer la couleur selon le statut
            if status == "online":
                if has_error:
                    color = COLOR_WARNING  # Orange s'il y a une erreur
                    status_text = "🟡 ONLINE (Error)"
                else:
                    color = DIAGNOSTIC_COLOR_SUCCESS  # Vert si tout est OK
                    status_text = "🟢 ONLINE"
            else:
                color = DIAGNOSTIC_COLOR_ERROR  # Rouge si offline
                status_text = "🔴 OFFLINE"

            timestamp = discord.utils.utcnow()

            embed = discord.Embed(
                title=f"🤖 {bot_name} - {status_text}",
                description=f"**Bot ID:** {self.user.id}\n**Username:** {self.user}\n**Status:** {status_text}\n**Timestamp:** {timestamp}",
                color=color,
                timestamp=timestamp
            )

            # Utiliser le stockage partagé pour retrouver le message existant
            message_id = diagnostic_message_ids.get(bot_name)

            # Si un message existe déjà, le mettre à jour
            if message_id:
                try:
                    old_message = await diagnostic_channel.fetch_message(message_id)
                    await old_message.edit(embed=embed)
                    log.info(f"Message de diagnostic mis à jour pour {bot_name}")
                except discord.NotFound:
                    # Le message n'existe plus, en créer un nouveau
                    message = await diagnostic_channel.send(embed=embed)
                    diagnostic_message_ids[bot_name] = message.id
                    log.info(f"Nouveau message de diagnostic créé pour {bot_name}")
                except Exception as e:
                    log.error(f"Erreur lors de la mise à jour du diagnostic: {e}")
                    # En cas d'erreur, créer un nouveau message
                    message = await diagnostic_channel.send(embed=embed)
                    diagnostic_message_ids[bot_name] = message.id
            else:
                # Créer un nouveau message
                message = await diagnostic_channel.send(embed=embed)
                diagnostic_message_ids[bot_name] = message.id
                log.info(f"Message de diagnostic envoyé pour {bot_name}")

        except Exception as e:
            log.error(f"Erreur lors de l'envoi du diagnostic: {e}")

    async def close(self) -> None:
        if self.presence_task is not None:
            self.presence_task.cancel()

        # Mettre à jour le diagnostic en offline avant de se déconnecter (sans supprimer le message)
        if self.bot_name and self.bot_name in diagnostic_message_ids:
            try:
                diagnostic_channel = self.get_channel(self.diagnostic_channel_id)
                if diagnostic_channel:
                    message_id = diagnostic_message_ids.get(self.bot_name)
                    if message_id:
                        try:
                            old_message = await diagnostic_channel.fetch_message(message_id)
                            embed = discord.Embed(
                                title=f"🤖 {self.bot_name} - 🔴 OFFLINE",
                                description=f"**Bot ID:** {self.user.id}\n**Username:** {self.user}\n**Status:** 🔴 OFFLINE\n**Timestamp:** {discord.utils.utcnow()}",
                                color=DIAGNOSTIC_COLOR_ERROR,
                                timestamp=discord.utils.utcnow()
                            )
                            await old_message.edit(embed=embed)
                        except discord.NotFound:
                            pass  # Le message n'existe plus, ce n'est pas grave
                        except Exception as e:
                            log.error(f"Erreur lors de la mise à jour du diagnostic: {e}")
            except Exception as e:
                log.error(f"Erreur lors de la mise à jour du diagnostic: {e}")

        panel = self.get_cog("StatusPanel")
        if panel is not None:
            try:
                await panel.mark_offline()
            except Exception as e:
                log.error(f"Bascule du panneau d'état en hors ligne impossible : {e}")
        await super().close()


# Commandes accessibles avant la configuration.
# /queue en fait partie : c'est elle qui ouvre l'assistant. La bloquer
# enfermait l'administrateur dehors — la commande qui configure le bot
# était précisément celle qu'il ne pouvait pas lancer.
_SETUP_EXEMPT = {"queue", "option", "config", "help", "guide", "language", "diagnostic", "status"}


async def global_setup_check(interaction: discord.Interaction) -> bool:
    from config import GUNZFRANCE_GUILD_ID

    if interaction.guild_id is None:
        return True

    if GUNZFRANCE_GUILD_ID and interaction.guild_id == GUNZFRANCE_GUILD_ID:
        return True

    if is_setup_complete(interaction.guild_id):
        return True

    cmd_name = interaction.command.name if interaction.command else ""
    if cmd_name in _SETUP_EXEMPT:
        return True

    # t(None, …) répondait toujours en anglais, y compris sur un serveur qui
    # avait déjà choisi sa langue avec /language.
    gid = interaction.guild_id
    embed = embeds.base(
        gid,
        title=t(gid, "setup.required_title"),
        description=t(gid, "setup.required_desc"),
        kind="warning",
    )
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=embed, ephemeral=True)
    return False


async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Dernier filet : une commande qui plante doit dire pourquoi.

    Sans ce gestionnaire, discord.py se contente d'écrire la trace dans les
    logs et l'utilisateur voit « L'application n'a pas répondu » — le même
    message qu'un bot hors ligne, impossible à distinguer d'une panne."""
    gid = interaction.guild_id

    if isinstance(error, app_commands.MissingPermissions):
        message = t(gid, "errors.missing_permissions")
    elif isinstance(error, app_commands.BotMissingPermissions):
        message = t(gid, "errors.bot_missing_permissions",
                    perms=", ".join(error.missing_permissions))
    elif isinstance(error, app_commands.CommandOnCooldown):
        message = t(gid, "errors.cooldown", seconds=round(error.retry_after))
    elif isinstance(error, app_commands.CheckFailure):
        # /setup non fait : global_setup_check a déjà répondu.
        return
    else:
        command = interaction.command.name if interaction.command else "?"
        log.exception(f"Erreur non gérée dans /{command}", exc_info=error)
        message = t(gid, "errors.generic")

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        # Salon supprimé, interaction expirée : le message d'erreur est perdu,
        # mais la trace est déjà dans les logs.
        pass


def start_presence_cycle(bot_instance: CreateYourQueueBot) -> None:
    """Lance la rotation du statut, une seule fois par bot.

    on_ready se redéclenche à chaque reconnexion, et l'ancien code relançait
    aussi la boucle à chaque arrivée ou départ de serveur : les boucles
    infinies s'empilaient et changeaient toutes le statut en même temps. La
    boucle relit elle-même le nombre de serveurs à chaque tour, il n'y a donc
    rien à relancer."""
    task = bot_instance.presence_task
    if task is not None and not task.done():
        return
    bot_instance.presence_task = asyncio.create_task(cycle_presence(bot_instance))


async def cycle_presence(bot_instance: commands.Bot) -> None:
    """Fait tourner la bio du bot cycliquement : servers -> queues -> total -> repeat"""
    while True:
        try:
            # Récupérer les informations
            queue_cog = bot_instance.get_cog("QueueConfig")
            active = 0
            if queue_cog is not None:
                active = sum(1 for s in queue_cog.active_sessions.values() if not s.ended)

            classement_cog = bot_instance.get_cog("Classement")
            total_queues = 0
            if classement_cog is not None:
                total_queues = classement_cog.server_stats.get("total_queues", 0)

            servers_count = len(bot_instance.guilds)

            # Cycle : servers -> queues -> total -> help
            statuses = [
                f"{servers_count} servers",
                f"{active} queues",
                f"{total_queues} total queue(s) start",
                "/help"
            ]

            for status in statuses:
                try:
                    await bot_instance.change_presence(
                        activity=discord.CustomActivity(name=status)
                    )
                    await asyncio.sleep(20)  # Attendre 20 secondes
                except discord.HTTPException as e:
                    log.error(f"Statut non mis a jour : {e}")
        except asyncio.CancelledError:
            return  # Le bot s'arrête
        except Exception as e:
            log.error(f"Erreur dans le cycle de présence : {e}")
            await asyncio.sleep(20)


GATEWAY_HOST = "gateway.discord.gg"
RETRY_START = 5      # secondes avant le premier nouvel essai
RETRY_MAX = 300      # plafond : 5 minutes entre deux essais


async def wait_for_network() -> None:
    """Attend que Discord soit joignable avant de tenter la connexion.

    discord.py ne sait se reconnecter qu'après une première connexion
    réussie : si le gateway est injoignable au démarrage (Wi-Fi pas encore
    monté, DNS coupé, panne du fournisseur), il essaie de reprendre une
    session qui n'existe pas et remonte un `AttributeError: 'NoneType'
    object has no attribute 'sequence'` — une trace de 200 lignes qui ne dit
    pas que c'est simplement la connexion qui manque.

    On vérifie donc nous-mêmes, et on patiente : le bot lancé sur un PC qui
    démarre repart tout seul dès que la connexion revient, au lieu de mourir.
    """
    delay = RETRY_START
    warned = False
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.getaddrinfo(GATEWAY_HOST, 443)
            if warned:
                log.info("Connexion rétablie — démarrage du bot.")
            return
        except socket.gaierror:
            if not warned:
                log.error(
                    f"Discord injoignable ({GATEWAY_HOST}) : pas de connexion "
                    f"Internet ou DNS bloqué. Le bot réessaiera tout seul."
                )
                warned = True
            log.info(f"Nouvel essai dans {delay}s…")
            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX)


async def run_bot(token: str, bot_name: str, is_temp: bool = False, is_modmail: bool = False):
    """Lance un bot individuel avec son token.

    Args:
        token: Le token Discord du bot
        bot_name: Le nom du bot pour les logs et le message de diagnostic
        is_temp: Si True, charge uniquement les extensions temporaires et désactive le statut
        is_modmail: Si True, charge uniquement les extensions modmail et utilise un statut personnalisé
    """
    bot = CreateYourQueueBot(command_prefix="!", intents=intents, help_command=None)
    bot.bot_name = bot_name
    bot.tree.on_error = on_app_command_error  # type: ignore[method-assign]
    if not is_temp and not is_modmail:
        # Le contrôle « serveur configuré » ne concerne que le bot principal.
        # Appliqué au bot temporaire, il bloquait /waiting sur tout serveur où
        # le bot principal n'avait pas été configuré.
        bot.tree.interaction_check = global_setup_check  # type: ignore[method-assign]

    @bot.event
    async def on_ready():
        log.info(f"[{bot_name}] Connecté en tant que {bot.user} (ID: {bot.user.id})")
        await sync_if_changed(bot)

        if is_modmail:
            await bot.change_presence(activity=discord.CustomActivity(name="DM ME for help!"))
        elif not is_temp:
            start_presence_cycle(bot)

        # Envoyer le diagnostic de démarrage (sans erreur par défaut)
        await bot.send_diagnostic(bot_name, status="online", has_error=False)

    @bot.event
    async def on_resume():
        """Appelé quand le bot se reconnecte après une déconnexion."""
        log.info(f"[{bot_name}] Reconnexion après déconnexion")
        await bot.send_diagnostic(bot_name, status="online", has_error=False)

    async with bot:
        # Choisir les extensions selon le type de bot
        if is_modmail:
            extensions = MODMAIL_EXTENSIONS
        elif is_temp:
            extensions = TEMPORARY_EXTENSIONS
        else:
            extensions = INITIAL_EXTENSIONS + WELCOME_EXTENSIONS

        for extension in extensions:
            try:
                await bot.load_extension(extension)
                log.info(f"[{bot_name}] Extension chargée : {extension}")
            except Exception as e:
                log.error(f"[{bot_name}] Échec du chargement de l'extension {extension} : {e}")

        await wait_for_network()
        try:
            await bot.start(token)
        except discord.LoginFailure:
            log.critical(
                f"[{bot_name}] Token refusé par Discord. Vérifie le token dans .env."
            )
        except discord.PrivilegedIntentsRequired:
            log.critical(
                f"[{bot_name}] Intents privilégiés désactivés. Active « Server Members » et « Message Content »."
            )


async def main():
    if args.bot == "all":
        await asyncio.gather(
            run_bot(MAIN_TOKEN, "Main"),
            run_bot(TEMP_TOKEN, "Temporaire", is_temp=True),
            run_bot(MODMAIL_TOKEN, "ModMail", is_modmail=True),
        )
    elif args.bot == "both":
        await asyncio.gather(
            run_bot(MAIN_TOKEN, "Main"),
            run_bot(TEMP_TOKEN, "Temporaire", is_temp=True),
        )
    elif args.bot == "main":
        await run_bot(MAIN_TOKEN, "Main")
    elif args.bot == "temporaire":
        await run_bot(TEMP_TOKEN, "Temporaire", is_temp=True)
    elif args.bot == "modmail":
        await run_bot(MODMAIL_TOKEN, "ModMail", is_modmail=True)


if __name__ == "__main__":
    asyncio.run(main())
