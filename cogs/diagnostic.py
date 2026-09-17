"""
Cog : Diagnostic
================
Commande : /diagnostic

Auto-contrôle du bot. Tourne automatiquement au démarrage (résultat dans la
console) et à la demande via /diagnostic (résultat dans Discord).
"""

import json
import logging
import os
import shutil

import discord
from discord import app_commands
from discord.ext import commands

import resources
from command_sync import sync_if_changed
import embeds
from config import INITIAL_EXTENSIONS, WELCOME_EXTENSIONS
from guild_settings import OPTIONAL_SLOTS, WIZARD_SLOTS, get_resource_id, queue_ready
from i18n import t, LANGUAGES
import importlib.util

log = logging.getLogger("bot.diagnostic")

# INFO : un réglage facultatif laissé de côté. Affiché, mais ce n'est pas un problème.
OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"
ICONS = {OK: "✅", WARN: "⚠️", FAIL: "❌", INFO: "➖"}

# Permissions serveur dont le bot a besoin, et ce qui casse sans elles.
REQUIRED_PERMS = [
    ("manage_roles", "rôles Connexion et rangs de MMR"),
    ("manage_channels", "vocaux d'équipe, salons de clan, vocaux de duel"),
    ("move_members", "répartition des joueurs dans les vocaux d'équipe"),
    ("manage_messages", "/clear, /autoclean, purge du salon queue"),
    ("kick_members", "anti-raid (auto-kick)"),
    ("moderate_members", "/timeout"),
    ("connect", "annonce vocale de lancement"),
    ("speak", "annonce vocale de lancement"),
    ("embed_links", "tous les panneaux et embeds"),
    ("add_reactions", "inscription à la queue via ✅"),
    ("read_message_history", "purge et logs"),
]

# Rôles attribués/retirés par le bot : ils doivent être SOUS son rôle le plus haut.
MANAGED_ROLES = ["role_connexion", "role_queue_notif", "role_mvp_week"]


class Check:
    """Une ligne de résultat : statut, libellé, et détail affiché si ce n'est pas OK."""

    __slots__ = ("status", "label", "detail")

    def __init__(self, status: str, label: str, detail: str = ""):
        self.status, self.label, self.detail = status, label, detail

    def line(self) -> str:
        return f"{ICONS[self.status]} {self.label}" + (f" : {self.detail}" if self.detail else "")


def _flatten(data: dict, prefix: str = "") -> set[str]:
    keys = set()
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            keys |= _flatten(value, f"{full}.")
        else:
            keys.add(full)
    return keys


class Diagnostic(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._startup_done = False

    # ------------------------------------------------------------------
    # Contrôles indépendants du serveur
    # ------------------------------------------------------------------
    def check_extensions(self) -> list[Check]:
        loaded = set(self.bot.extensions)
        expected = [e for e in INITIAL_EXTENSIONS + WELCOME_EXTENSIONS if not e.startswith("#")]
        missing = [e for e in expected if e not in loaded]
        if missing:
            return [Check(FAIL, f"Cogs ({len(loaded)}/{len(expected)})", "non chargés : " + ", ".join(missing))]
        return [Check(OK, f"Cogs chargés ({len(loaded)}/{len(expected)})")]

    def check_commands(self) -> list[Check]:
        out = []
        cmds = self.bot.tree.get_commands()
        names = [c.name for c in cmds]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            out.append(Check(FAIL, "Commandes en double", ", ".join(f"/{n}" for n in duplicates)))
        else:
            out.append(Check(OK, f"Commandes slash ({len(cmds)})"))

        # Discord rejette une commande sans description ou avec plus de 100 caractères
        bad = [
            f"/{c.name}"
            for c in cmds
            if not getattr(c, "description", "") or len(getattr(c, "description", "")) > 100
        ]
        if bad:
            out.append(Check(FAIL, "Descriptions de commande invalides", ", ".join(bad)))
        return out

    def check_locales(self) -> list[Check]:
        """Compare les 5 fichiers de langue entre eux : une clé présente en
        français mais absente en coréen s'affiche brute (`queue.lib_title`)."""
        loaded = {}
        for lang in LANGUAGES:
            path = os.path.join("locales", f"{lang}.json")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded[lang] = _flatten(json.load(f))
            except Exception as e:
                return [Check(FAIL, f"Langue `{lang}`", f"illisible : {e}")]

        if "fr" not in loaded:
            return [Check(FAIL, "Traductions", "locales/fr.json introuvable")]

        reference = loaded["fr"]
        problems = []
        for lang, keys in loaded.items():
            if lang == "fr":
                continue
            missing = reference - keys
            if missing:
                sample = ", ".join(sorted(missing)[:3])
                problems.append(f"{lang}: {len(missing)} manquante(s) ({sample}…)")
        if problems:
            return [Check(WARN, "Traductions incomplètes", " · ".join(problems))]
        return [Check(OK, f"Traductions ({len(LANGUAGES)} langues, {len(reference)} clés)")]

    def check_voice_stack(self) -> list[Check]:
        out = []
        if shutil.which("ffmpeg"):
            out.append(Check(OK, "FFmpeg installé"))
        else:
            out.append(Check(FAIL, "FFmpeg introuvable", "l'annonce vocale de lancement ne marchera pas"))
        if importlib.util.find_spec("nacl") is not None:
            out.append(Check(OK, "PyNaCl installé"))
        else:
            out.append(Check(FAIL, "PyNaCl manquant", "le bot ne peut pas rejoindre un vocal"))
        from cogs.queue_config import VOICE_ANNOUNCE_FILES
        missing = [f"{lang} ({fn})" for lang, fn in VOICE_ANNOUNCE_FILES.items() if not os.path.exists(fn)]
        if not missing:
            out.append(Check(OK, f"Annonces vocales ({len(VOICE_ANNOUNCE_FILES)} langues)"))
        elif "fr" in [m.split()[0] for m in missing]:
            out.append(Check(FAIL, "Annonce vocale française absente", "aucune langue n'a de repli, l'annonce ne jouera jamais"))
        else:
            out.append(Check(WARN, "Annonces vocales incomplètes",
                              ", ".join(missing) + ", ces langues utiliseront le français"))
        return out

    def check_data_files(self) -> list[Check]:
        if not os.path.isdir("data"):
            return [Check(WARN, "Dossier data/", "absent (il sera créé au besoin)")]
        broken = []
        for name in sorted(os.listdir("data")):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join("data", name), "r", encoding="utf-8") as f:
                    json.load(f)
            except Exception as e:
                broken.append(f"{name} ({type(e).__name__})")
        if broken:
            return [Check(FAIL, "Fichiers de données corrompus", ", ".join(broken))]
        return [Check(OK, "Fichiers de données valides")]

    # ------------------------------------------------------------------
    # Contrôles par serveur
    # ------------------------------------------------------------------
    def check_guild_permissions(self, guild: discord.Guild) -> list[Check]:
        me = guild.me
        if me is None:
            return [Check(FAIL, f"{guild.name} : membre bot introuvable")]
        perms = me.guild_permissions
        if perms.administrator:
            return [Check(OK, "Permissions (Administrateur)")]
        missing = [(name, why) for name, why in REQUIRED_PERMS if not getattr(perms, name, False)]
        if missing:
            return [
                Check(FAIL, f"Permissions manquantes ({len(missing)})",
                      " · ".join(f"`{n}` → {why}" for n, why in missing))
            ]
        return [Check(OK, "Permissions suffisantes")]

    def check_guild_hierarchy(self, guild: discord.Guild) -> list[Check]:
        """Le bot ne peut attribuer un rôle que s'il est strictement au-dessus.
        C'est la cause n°1 d'un « le rôle n'est pas donné » sans message d'erreur."""
        me = guild.me
        if me is None:
            return []
        top = me.top_role.position
        blocked = []
        for key in MANAGED_ROLES:
            role = resources.get_role(guild, key)
            if role and role.position >= top:
                blocked.append(role.name)
        if blocked:
            return [
                Check(FAIL, "Hiérarchie des rôles",
                      "le bot est SOUS " + ", ".join(f"`{n}`" for n in blocked)
                      + ", il ne peut pas les attribuer. Remonte son rôle.")
            ]
        return [Check(OK, "Hiérarchie des rôles")]

    def check_guild_resources(self, guild: discord.Guild) -> list[Check]:
        """Les salons et le rôle organisateur choisis dans l'assistant."""
        if not queue_ready(guild.id):
            return [Check(INFO, "Queue pas encore configurée", "`/option` pour choisir les salons")]
        gone = []
        for key, kind, _required in list(WIZARD_SLOTS) + list(OPTIONAL_SLOTS):
            if get_resource_id(guild.id, key) is None:
                continue
            find = resources.get_voice_channel if kind == "voice" else resources.get_text_channel
            if find(guild, key) is None:
                gone.append(resources.resource_name(guild.id, key))
        if resources.get_role(guild, "role_staff") is None:
            gone.append(resources.resource_name(guild.id, "role_staff"))
        if gone:
            return [Check(WARN, "Salons ou rôle supprimés",
                          ", ".join(f"`{n}`" for n in gone) + " : à rechoisir dans `/option`")]
        return [Check(OK, "Salons et rôle organisateur en place")]

    def check_waiting_lock(self, guild: discord.Guild) -> list[Check]:
        """Avec un rôle Connexion, le vocal d'attente reste fermé à @everyone.
        Sans rôle Connexion, la queue le laisse ouvert exprès."""
        waiting = resources.get_voice_channel(guild, "voice_queue_waiting")
        if waiting is None:
            return []
        if resources.get_role(guild, "role_connexion") is None:
            return [Check(INFO, "Vocal d'attente ouvert", "aucun rôle Connexion choisi, c'est voulu")]
        overwrite = waiting.overwrites_for(guild.default_role)
        if overwrite.connect is False:
            return [Check(OK, "Vocal d'attente verrouillé")]
        return [Check(FAIL, "Vocal d'attente OUVERT", "@everyone peut se connecter sans réagir")]

    def check_notif_role(self, guild: discord.Guild) -> list[Check]:
        """Un MP « Notif Queue » qui n'arrive pas vient presque toujours d'un rôle
        que personne ne porte, ou du membre qui a fermé ses MP."""
        role = resources.get_role(guild, "role_queue_notif")
        if role is None:
            return [Check(INFO, "Notif Queue", "aucun rôle choisi, pas de MP au lancement d'une queue")]
        subscribers = [m for m in role.members if not m.bot]
        if not subscribers:
            return [
                Check(INFO, "Notif Queue : 0 inscrit",
                      f"personne n'a `{role.name}`, les membres le prennent avec `/queuerole`")
            ]
        return [Check(OK, f"Notif Queue ({len(subscribers)} inscrit(s))")]

    def check_queue_state(self, guild: discord.Guild) -> list[Check]:
        cog = self.bot.get_cog("QueueConfig")
        if cog is None:
            return [Check(FAIL, "Cog QueueConfig absent", "/queue ne répondra pas")]
        session = cog.active_sessions.get(guild.id)
        if session is None:
            return [Check(OK, "Aucune queue en cours")]
        phase = "terminée" if session.ended else ("lancée" if session.started else "inscriptions")
        return [Check(OK, f"Queue en cours ({phase}, {len(session.waiting_players)} joueur(s))")]

    # ------------------------------------------------------------------
    # Exécution
    # ------------------------------------------------------------------
    def run_global_checks(self) -> list[Check]:
        results = []
        results += self.check_extensions()
        results += self.check_commands()
        results += self.check_locales()
        results += self.check_voice_stack()
        results += self.check_data_files()
        return results

    def run_guild_checks(self, guild: discord.Guild) -> list[Check]:
        results = []
        results += self.check_guild_permissions(guild)
        results += self.check_guild_hierarchy(guild)
        results += self.check_guild_resources(guild)
        results += self.check_waiting_lock(guild)
        results += self.check_notif_role(guild)
        results += self.check_queue_state(guild)
        return results

    @commands.Cog.listener()
    async def on_ready(self):
        """Auto-contrôle au démarrage — le résultat part dans la console."""
        if self._startup_done:
            return
        self._startup_done = True

        globals_ = self.run_global_checks()
        problems = [c for c in globals_ if c.status in (WARN, FAIL)]

        log.info("─" * 62)
        log.info("DIAGNOSTIC DE DÉMARRAGE")
        for check in globals_:
            (log.error if check.status == FAIL else log.warning if check.status == WARN else log.info)(
                "  " + check.line()
            )

        for guild in self.bot.guilds:
            guild_checks = self.run_guild_checks(guild)
            guild_problems = [c for c in guild_checks if c.status in (WARN, FAIL)]
            problems += guild_problems
            log.info(f"  ── {guild.name} ({guild.id})")
            for check in guild_checks:
                (log.error if check.status == FAIL else log.warning if check.status == WARN else log.info)(
                    "     " + check.line()
                )

        if problems:
            fails = sum(1 for c in problems if c.status == FAIL)
            log.warning(f"DIAGNOSTIC : {fails} erreur(s), {len(problems) - fails} avertissement(s). Détail ci-dessus.")
        else:
            log.info("DIAGNOSTIC : tout est opérationnel.")
        log.info("─" * 62)

    @app_commands.command(name="diagnostic", description="Check that every part of the bot works.")
    @app_commands.describe(resync="Force la resynchronisation des commandes slash (à n'utiliser qu'en cas de souci)")
    async def diagnostic(self, interaction: discord.Interaction, resync: bool = False):
        if not isinstance(interaction.user, discord.Member) or not (
            interaction.user.guild_permissions.administrator or resources.is_staff(interaction.user)
        ):
            await interaction.response.send_message(t(interaction.guild_id, "common.no_permission"), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Volontairement manuel : la synchronisation est une route très limitée
        # par Discord, elle ne doit pas partir à chaque appel de /diagnostic.
        if resync:
            count = await sync_if_changed(self.bot, force=True)
            await interaction.followup.send(
                t(interaction.guild_id, "diagnostic.resync_done", count=count)
                if count is not None
                else t(interaction.guild_id, "diagnostic.resync_failed"),
                ephemeral=True,
            )

        globals_ = self.run_global_checks()
        guild_checks = self.run_guild_checks(interaction.guild) if interaction.guild else []
        everything = globals_ + guild_checks
        fails = sum(1 for c in everything if c.status == FAIL)
        warns = sum(1 for c in everything if c.status == WARN)

        embed = embeds.base(
            interaction.guild_id,
            title=t(interaction.guild_id, "diagnostic.title"),
            description=(
                t(interaction.guild_id, "diagnostic.all_good") if not (fails or warns)
                else t(interaction.guild_id, "diagnostic.summary", fails=fails, warns=warns)
            ),
            kind="error" if fails else ("warning" if warns else "success"),
            footer=t(interaction.guild_id, "diagnostic.footer"),
            timestamp=True,
        )
        embeds.brand(embed, interaction.guild)
        embeds.section(
            embed, t(interaction.guild_id, "diagnostic.field_global"), self._render(globals_)
        )
        if guild_checks:
            embeds.section(
                embed,
                t(interaction.guild_id, "diagnostic.field_guild", guild=interaction.guild.name),
                self._render(guild_checks),
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @staticmethod
    def _render(checks: list[Check]) -> str:
        """Assemble les lignes en respectant la limite de 1024 caractères d'un champ d'embed."""
        text = ""
        for check in checks:
            line = check.line() + "\n"
            if len(text) + len(line) > 1000:
                text += "…"
                break
            text += line
        return text or "—"


async def setup(bot: commands.Bot):
    await bot.add_cog(Diagnostic(bot))
    log.info("Cog Diagnostic chargé")
