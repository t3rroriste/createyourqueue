"""
Cog : ModMail
=============
Bot de support par message privé (`python bot.py --bot modmail`).

Parcours :
1. Un membre écrit au bot en MP.
2. Il choisit une catégorie (Bug, Signalement, Question, Suggestion) et
   décrit sa demande.
3. Le ticket arrive dans le salon staff (`MODMAIL_STAFF_CHANNEL_ID`). Tant
   qu'il est ouvert, les messages suivants du membre y sont recopiés.
4. Un membre du staff le prend en charge, répond — la réponse est traduite
   dans la langue du membre — puis le ferme.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import discord
from discord.ext import commands
from langdetect import DetectorFactory, LangDetectException, detect
from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import TooManyRequests

from config import (
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARNING,
    DIAGNOSTIC_CHANNEL_ID,
    MODMAIL_STAFF_CHANNEL_ID,
    MODMAIL_STAFF_ROLE_ID,
)
import custom_emojis
from i18n import get_lang, t, t_in
from json_store import write_json

log = logging.getLogger("bot.modmail")

# langdetect tire au sort par défaut : le même texte pouvait être détecté dans
# une langue, puis dans une autre au message suivant.
DetectorFactory.seed = 0

SESSIONS_FILE = "data/modmail_sessions.json"
# Ancien emplacement, à la racine du projet : hors de data/, donc hors du
# .gitignore, les tickets partaient sur GitHub avec le code.
LEGACY_SESSIONS_FILE = "modmail_sessions.json"

SUPPORTED = ("fr", "en", "es", "de", "ko")

# Anti-flood des MP : au-delà de FLOOD_MAX messages en FLOOD_WINDOW secondes,
# les suivants sont ignorés (ni recopiés au staff, ni traduits).
FLOOD_MAX = 5
FLOOD_WINDOW = 10
LANGUAGE_NAMES = {"fr": "Français", "en": "English", "es": "Español", "de": "Deutsch", "ko": "한국어"}

# (clé enregistrée dans la session, emoji, style, clé du libellé)
CATEGORIES = [
    ("bug", "🐛", discord.ButtonStyle.primary, "modmail.cat_bug"),
    ("report", "⚠️", discord.ButtonStyle.danger, "modmail.cat_report"),
    ("question", "❓", discord.ButtonStyle.secondary, "modmail.cat_question"),
    ("suggestion", "💡", discord.ButtonStyle.success, "modmail.cat_suggestion"),
]
CATEGORY_LABEL_KEYS = {key: label_key for key, _emoji, _style, label_key in CATEGORIES}
CATEGORY_EMOJI = {key: emoji for key, emoji, _style, _label_key in CATEGORIES}

# (action, emoji, style, clé du libellé)
STAFF_ACTIONS = [
    ("take", "🎯", discord.ButtonStyle.primary, "modmail.btn_take"),
    ("reply", "📝", discord.ButtonStyle.secondary, "modmail.btn_reply"),
    ("close", "🔒", discord.ButtonStyle.danger, "modmail.btn_close"),
]


def member_text(lang: str, key: str, **kwargs) -> str:
    """Texte côté membre, dans la langue de son message (anglais à défaut)."""
    return t_in(lang, key, **kwargs) or t_in("en", key, **kwargs)


def category_label(category: str, *, lang: str | None = None, guild_id: int | None = None) -> str:
    """Libellé d'une catégorie, côté membre (`lang`) ou côté staff (`guild_id`)."""
    label_key = CATEGORY_LABEL_KEYS.get(category)
    if label_key is None:
        return str(category)
    label = member_text(lang, label_key) if lang else t(guild_id, label_key)
    return f"{CATEGORY_EMOJI[category]} {label}"


def detect_language(text: str) -> str:
    """Langue d'un message parmi les cinq du bot, anglais à défaut. Bloquant."""
    cleaned = (text or "").strip()
    if not cleaned:
        return "en"
    try:
        lang = detect(cleaned)
    except LangDetectException:
        return "en"
    return lang if lang in SUPPORTED else "en"


# Google Traduction (gratuit, sans clé) coupe l'accès un moment quand on
# dépasse son quota : il répond alors 429 (TooManyRequests) à chaque appel, et
# les réponses du staff partaient sans traduction.
GOOGLE_COOLDOWN_SECONDS = 15 * 60
# MyMemory refuse les textes de plus de 500 caractères : on découpe.
MYMEMORY_CHUNK = 450
MYMEMORY_CODES = {"fr": "fr-FR", "en": "en-GB", "es": "es-ES", "de": "de-DE", "ko": "ko-KR"}

_google_blocked_until = 0.0


def _chunks(text: str, size: int) -> list[tuple[str, str]]:
    """Morceaux de `size` caractères au plus, coupés aux fins de ligne ou aux
    espaces. Rend (morceau, séparateur à remettre après)."""
    out = []
    rest = text.strip()
    while len(rest) > size:
        cut = rest.rfind("\n", 0, size)
        if cut <= 0:
            cut = rest.rfind(" ", 0, size)
        if cut <= 0:
            cut = size
        out.append((rest[:cut], "\n" if rest[cut:cut + 1] == "\n" else " "))
        rest = rest[cut:].lstrip()
    out.append((rest, ""))
    return out


def _translate_mymemory(text: str, source: str, target: str) -> str:
    translator = MyMemoryTranslator(source=MYMEMORY_CODES[source], target=MYMEMORY_CODES[target])
    pieces = []
    for chunk, separator in _chunks(text, MYMEMORY_CHUNK):
        translated = translator.translate(chunk)
        # Quota épuisé : MyMemory répond 200 avec un avertissement à la place
        # de la traduction — surtout ne pas l'envoyer au membre.
        if not translated or "MYMEMORY WARNING" in translated.upper():
            raise TooManyRequests()
        pieces.append(translated + separator)
    return "".join(pieces)


def translate_text(text: str, target: str) -> tuple[str, bool]:
    """Traduit vers `target`. Bloquant."""
    global _google_blocked_until
    if not text or target not in SUPPORTED:
        return text, True
    source = detect_language(text)
    if source == target:
        return text, True

    if time.monotonic() >= _google_blocked_until:
        try:
            translated = GoogleTranslator(source="auto", target=target).translate(text)
            if translated:
                return translated, True
        except TooManyRequests:
            _google_blocked_until = time.monotonic() + GOOGLE_COOLDOWN_SECONDS
            log.warning("Google Traduction saturé (429) : MyMemory prend le relais "
                        f"pendant {GOOGLE_COOLDOWN_SECONDS // 60} min")
        except Exception as e:  # service externe : toute panne est possible
            log.warning(f"Google Traduction indisponible ({type(e).__name__}) : essai avec MyMemory")

    try:
        return _translate_mymemory(text, source, target), True
    except Exception as e:  # service externe : toute panne est possible
        log.warning(f"Traduction impossible ({type(e).__name__}) : réponse envoyée sans traduction")
    return text, False


# ----------------------------------------------------------------------
# Stockage
# ----------------------------------------------------------------------
class ModMailStorage:
    """Les sessions de support, une par ticket."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self._move_legacy_file()
        self.load()

    @staticmethod
    def _move_legacy_file() -> None:
        if os.path.exists(LEGACY_SESSIONS_FILE) and not os.path.exists(SESSIONS_FILE):
            try:
                os.makedirs(os.path.dirname(SESSIONS_FILE), exist_ok=True)
                os.replace(LEGACY_SESSIONS_FILE, SESSIONS_FILE)
                log.info("Sessions modmail déplacées dans data/")
            except OSError as e:
                log.error(f"Déplacement des sessions modmail impossible : {e}")

    def load(self) -> None:
        if not os.path.exists(SESSIONS_FILE):
            return
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            log.error(f"Sessions modmail illisibles : {e}")
            return
        self.sessions = data if isinstance(data, dict) else {}
        log.info(f"{len(self.sessions)} session(s) modmail chargée(s)")

    def save(self) -> None:
        try:
            write_json(SESSIONS_FILE, self.sessions, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Écriture des sessions modmail impossible : {e}")

    def create(self, user_id: int, category: str, description: str, language: str) -> str:
        n = len(self.sessions)
        session_id = f"{user_id}_{category}_{n}"
        while session_id in self.sessions:
            n += 1
            session_id = f"{user_id}_{category}_{n}"
        self.sessions[session_id] = {
            "user_id": user_id,
            "category": category,
            "description": description,
            "user_language": language,
            "staff_message_id": None,
            "taken_by": None,
            "created_at": discord.utils.utcnow().isoformat(),
            "closed": False,
            # Identifiants de boutons propres au ticket (voir StaffTicketView).
            "buttons": 2,
        }
        self.save()
        return session_id

    def get(self, session_id: str) -> dict | None:
        return self.sessions.get(session_id)

    def update(self, session_id: str, **fields) -> None:
        if session_id in self.sessions:
            self.sessions[session_id].update(fields)
            self.save()

    def open_session_of(self, user_id: int) -> str | None:
        for session_id, data in self.sessions.items():
            if data.get("user_id") == user_id and not data.get("closed"):
                return session_id
        return None

    def open_sessions(self) -> list[tuple[str, dict]]:
        return [(sid, data) for sid, data in self.sessions.items() if not data.get("closed")]

    def reset(self) -> None:
        self.sessions = {}
        self.save()


# ----------------------------------------------------------------------
# Cog
# ----------------------------------------------------------------------
class ModMail(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = ModMailStorage()
        self._restored = False
        self._recent: dict[int, list[float]] = {}
        # Emojis perso de l'application ModMail (voir custom_emojis.fetch_own).
        self.icons: dict[str, str] = {}

    async def cog_load(self) -> None:
        # Boutons de catégorie envoyés en MP : un exemplaire par langue suffit,
        # la langue est inscrite dans leur identifiant.
        for lang in SUPPORTED:
            self.bot.add_view(CategoryView(self, lang))
        # Messages envoyés avant cette version : anciens identifiants, en anglais.
        self.bot.add_view(CategoryView(self, "en", legacy=True))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Réattache les boutons des tickets encore ouverts."""
        if self._restored:
            return
        self._restored = True
        self.icons = await custom_emojis.fetch_own(self.bot, ("letter", "communication"))
        channel = self.staff_channel()
        guild_id = channel.guild.id if channel is not None else None
        restored = 0
        for session_id, session in self.storage.open_sessions():
            message_id = session.get("staff_message_id")
            if not message_id:
                continue
            view = StaffTicketView(self, session_id, guild_id, legacy=session.get("buttons") != 2)
            self.bot.add_view(view, message_id=int(message_id))
            restored += 1
        if restored:
            log.info(f"{restored} ticket(s) modmail ouvert(s) réattaché(s)")

    # -- Outils ----------------------------------------------------------
    def icon(self, name: str) -> str:
        """Emoji perso de l'application ModMail, emoji Unicode à défaut."""
        return self.icons.get(name) or custom_emojis.FALLBACKS[name]

    async def staff_translation(self, text: str, language: str, guild_id: int) -> str | None:
        """Le texte d'un membre traduit dans la langue du serveur staff."""
        staff_language = get_lang(guild_id)
        if not text or language == staff_language:
            return None
        translated, ok = await asyncio.to_thread(translate_text, text, staff_language)
        if not ok:
            return t(guild_id, "modmail.translation_unavailable")
        return None if translated.strip() == text.strip() else translated

    def staff_channel(self) -> discord.abc.Messageable | None:
        channel_id = MODMAIL_STAFF_CHANNEL_ID or DIAGNOSTIC_CHANNEL_ID
        return self.bot.get_channel(channel_id) if channel_id else None

    def is_staff(self, member: discord.abc.User) -> bool:
        if not MODMAIL_STAFF_ROLE_ID:
            return True
        return isinstance(member, discord.Member) and any(r.id == MODMAIL_STAFF_ROLE_ID for r in member.roles)

    async def fetch_user(self, user_id: int) -> discord.User | None:
        user = self.bot.get_user(int(user_id))
        if user is not None:
            return user
        try:
            return await self.bot.fetch_user(int(user_id))
        except discord.HTTPException:
            return None

    @staticmethod
    async def dm(user: discord.abc.User, content: str | None = None, **kwargs) -> bool:
        try:
            await user.send(content, **kwargs)
            return True
        except discord.HTTPException:
            log.info(f"MP impossible vers {getattr(user, 'id', '?')} (messages privés fermés ?)")
            return False

    # -- Commande --------------------------------------------------------
    @commands.command(name="reset_modmail")
    @commands.is_owner()
    async def reset_modmail(self, ctx: commands.Context) -> None:
        """Réinitialise toutes les sessions modmail (propriétaire uniquement)."""
        self.storage.reset()
        await ctx.send(t(ctx.guild.id if ctx.guild else None, "modmail.reset_done"))
        log.info("Sessions modmail réinitialisées par le propriétaire")

    # -- Messages privés -------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not isinstance(message.channel, discord.DMChannel):
            return
        now = time.monotonic()
        recent = [at for at in self._recent.get(message.author.id, []) if now - at < FLOOD_WINDOW]
        if len(recent) >= FLOOD_MAX:
            self._recent[message.author.id] = recent
            return
        self._recent[message.author.id] = recent + [now]

        language = await asyncio.to_thread(detect_language, message.content)

        if not (MODMAIL_STAFF_CHANNEL_ID or DIAGNOSTIC_CHANNEL_ID):
            log.error("MODMAIL_STAFF_CHANNEL_ID n'est pas défini dans .env")
            await self.dm(message.author, member_text(language, "modmail.err_not_configured"))
            return
        channel = self.staff_channel()
        if channel is None:
            log.error(f"Salon staff du modmail introuvable : {MODMAIL_STAFF_CHANNEL_ID or DIAGNOSTIC_CHANNEL_ID}")
            await self.dm(message.author, member_text(language, "modmail.err_staff_unreachable"))
            return

        session_id = self.storage.open_session_of(message.author.id)
        if session_id:
            await self.forward_to_staff(message, session_id, language, channel)
        else:
            await self.show_categories(message.author, language)

    async def show_categories(self, user: discord.abc.User, language: str) -> None:
        embed = discord.Embed(
            title=member_text(language, "modmail.categories_title"),
            description=member_text(language, "modmail.categories_desc"),
            color=COLOR_INFO,
        )
        await self.dm(user, embed=embed, view=CategoryView(self, language))

    async def forward_to_staff(self, message: discord.Message, session_id: str,
                               language: str, channel: discord.abc.Messageable) -> None:
        """Recopie dans le salon staff un message d'un membre au ticket ouvert."""
        if self.storage.get(session_id) is None:
            return
        self.storage.update(session_id, user_language=language)
        gid = channel.guild.id
        lines = [t(gid, "modmail.msg_original", text=(message.content or "—")[:1900])]
        translation = await self.staff_translation(message.content, language, gid)
        if translation:
            lines.append(t(gid, "modmail.msg_translated", text=translation[:2000]))
        # Plus de pied de page (identifiants, session) : l'heure suffit, le
        # ticket d'origine porte déjà le membre et sa demande.
        embed = discord.Embed(
            title=t(gid, "modmail.staff_message_title", icon=self.icon("letter"), user=str(message.author),
                    language=LANGUAGE_NAMES.get(language, language))[:256],
            description="\n".join(lines)[:4096],
            color=COLOR_INFO,
            timestamp=message.created_at,
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            log.error(f"Message modmail non transmis au staff : {e}")
            await self.dm(message.author, member_text(language, "modmail.err_send"))
            return
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass

    async def open_ticket(self, user: discord.abc.User, category: str,
                          description: str, language: str) -> str | None:
        """Crée le ticket et l'envoie au staff. Rend la clé d'erreur, ou None."""
        channel = self.staff_channel()
        if channel is None:
            log.error("Salon staff du modmail introuvable : ticket non créé")
            return "modmail.err_staff_unreachable"
        session_id = self.storage.create(user.id, category, description, language)
        gid = channel.guild.id
        parts = [
            t(gid, "modmail.ticket_desc", user=user.mention, user_id=user.id),
            "",
            t(gid, "modmail.desc_original", text=description[:1900]),
        ]
        translation = await self.staff_translation(description, language, gid)
        if translation:
            parts.append(t(gid, "modmail.desc_translated", text=translation[:2000]))
        embed = discord.Embed(
            title=t(gid, "modmail.ticket_title", icon=self.icon("letter"),
                    category=category_label(category, guild_id=gid))[:256],
            description="\n".join(parts)[:4096],
            color=COLOR_SUCCESS,
            timestamp=discord.utils.utcnow(),
        )
        try:
            message = await channel.send(embed=embed, view=StaffTicketView(self, session_id, gid))
        except discord.HTTPException as e:
            log.error(f"Ticket modmail non envoyé au staff : {e}")
            return "modmail.err_send"
        self.storage.update(session_id, staff_message_id=message.id)
        return None


# ----------------------------------------------------------------------
# Côté membre
# ----------------------------------------------------------------------
class CategoryView(discord.ui.View):
    """Les quatre catégories, en MP. Persistante : la langue est dans l'identifiant."""

    def __init__(self, cog: ModMail, language: str, *, legacy: bool = False) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.language = language
        for key, emoji, style, label_key in CATEGORIES:
            button = discord.ui.Button(
                label=member_text(language, label_key),
                emoji=emoji,
                style=style,
                custom_id=f"modmail_{key}" if legacy else f"modmail:cat:{language}:{key}",
            )
            button.callback = self._choose(key)
            self.add_item(button)

    def _choose(self, category: str):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.send_modal(TicketModal(self.cog, category, self.language))
        return callback


class TicketModal(discord.ui.Modal):
    """La description de la demande."""

    def __init__(self, cog: ModMail, category: str, language: str) -> None:
        super().__init__(title=member_text(language, "modmail.modal_title",
                                           category=category_label(category, lang=language))[:45])
        self.cog = cog
        self.category = category
        self.language = language
        self.details = discord.ui.TextInput(
            label=member_text(language, "modmail.modal_label")[:45],
            style=discord.TextStyle.paragraph,
            placeholder=member_text(language, "modmail.modal_placeholder")[:100],
            max_length=1000,
        )
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = self.details.value
        await interaction.response.defer(ephemeral=True)
        error = await self.cog.open_ticket(interaction.user, self.category, text, self.language)
        if error:
            await interaction.followup.send(member_text(self.language, error), ephemeral=True)
            return
        embed = discord.Embed(
            title=member_text(self.language, "modmail.sent_title"),
            description=member_text(self.language, "modmail.sent_desc",
                                    category=category_label(self.category, lang=self.language),
                                    description=text)[:4096],
            color=COLOR_SUCCESS,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


# ----------------------------------------------------------------------
# Côté staff
# ----------------------------------------------------------------------
class StaffTicketView(discord.ui.View):
    """Prendre, répondre, fermer."""

    def __init__(self, cog: ModMail, session_id: str, guild_id: int | None, *, legacy: bool = False) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.session_id = session_id
        self.guild_id = guild_id
        self.controls: dict[str, discord.ui.Button] = {}
        handlers = {"take": self.take, "reply": self.reply, "close": self.close}
        for action, emoji, style, label_key in STAFF_ACTIONS:
            button = discord.ui.Button(
                label=t(guild_id, label_key),
                emoji=emoji,
                style=style,
                custom_id=f"modmail_{action}" if legacy else f"modmail:{action}:{session_id}"[:100],
            )
            button.callback = handlers[action]
            self.controls[action] = button
            self.add_item(button)
        if (cog.storage.get(session_id) or {}).get("taken_by"):
            self._mark_taken()

    def _mark_taken(self) -> None:
        take = self.controls["take"]
        take.disabled = True
        take.label = t(self.guild_id, "modmail.btn_taken")
        take.style = discord.ButtonStyle.success

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.cog.is_staff(interaction.user):
            return True
        await interaction.response.send_message(t(interaction.guild_id, "modmail.err_not_staff"), ephemeral=True)
        return False

    def _open_session(self) -> dict | None:
        session = self.cog.storage.get(self.session_id)
        return session if session and not session.get("closed") else None

    async def take(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        session = self._open_session()
        if session is None:
            await interaction.response.send_message(t(gid, "modmail.err_ticket_closed"), ephemeral=True)
            return
        if session.get("taken_by"):
            await interaction.response.send_message(t(gid, "modmail.err_already_taken"), ephemeral=True)
            return
        self.cog.storage.update(self.session_id, taken_by=interaction.user.id)
        message = interaction.message
        embed = message.embeds[0] if message is not None and message.embeds else discord.Embed(color=COLOR_SUCCESS)
        taken = t(gid, "modmail.taken_line", icon=self.cog.icon("communication"),
                  staff=interaction.user.mention)
        embed.description = f"{embed.description or ''}\n\n{taken}"[:4096]
        self._mark_taken()
        await interaction.response.edit_message(embed=embed, view=self)

    async def reply(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        session = self._open_session()
        if session is None:
            await interaction.response.send_message(t(gid, "modmail.err_ticket_closed"), ephemeral=True)
            return
        taken_by = session.get("taken_by")
        if taken_by is None:
            await interaction.response.send_message(t(gid, "modmail.err_take_first"), ephemeral=True)
            return
        if taken_by != interaction.user.id:
            await interaction.response.send_message(t(gid, "modmail.err_taken_by_other"), ephemeral=True)
            return
        await interaction.response.send_modal(StaffReplyModal(self.cog, self.session_id, gid))

    async def close(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        session = self._open_session()
        if session is None:
            await interaction.response.send_message(t(gid, "modmail.err_ticket_closed"), ephemeral=True)
            return
        taken_by = session.get("taken_by")
        if taken_by is not None and taken_by != interaction.user.id:
            await interaction.response.send_message(t(gid, "modmail.err_close_only_taker"), ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=t(gid, "modmail.closed_staff_title"),
                description=t(gid, "modmail.closed_staff_desc"),
                color=COLOR_ERROR,
            ),
            view=None,
        )
        self.cog.storage.update(self.session_id, closed=True)
        self.stop()
        language = session.get("user_language", "en")
        user = await self.cog.fetch_user(session.get("user_id", 0))
        if user is not None:
            await self.cog.dm(user, embed=discord.Embed(
                title=member_text(language, "modmail.closed_user_title"),
                description=member_text(language, "modmail.closed_user_desc"),
                color=COLOR_ERROR,
            ))


class StaffReplyModal(discord.ui.Modal):
    """La réponse du staff, traduite dans la langue du membre."""

    def __init__(self, cog: ModMail, session_id: str, guild_id: int | None) -> None:
        super().__init__(title=t(guild_id, "modmail.reply_modal_title")[:45])
        self.cog = cog
        self.session_id = session_id
        self.guild_id = guild_id
        self.answer = discord.ui.TextInput(
            label=t(guild_id, "modmail.reply_label")[:45],
            style=discord.TextStyle.paragraph,
            placeholder=t(guild_id, "modmail.reply_placeholder")[:100],
            max_length=1000,
        )
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        gid = self.guild_id
        session = self.cog.storage.get(self.session_id)
        if not session or session.get("closed"):
            await interaction.response.send_message(t(gid, "modmail.err_ticket_closed"), ephemeral=True)
            return
        # La traduction peut prendre plusieurs secondes : Discord exige une
        # réponse en moins de trois.
        await interaction.response.defer(ephemeral=True)
        language = session.get("user_language", "en")
        text, translated = await asyncio.to_thread(translate_text, self.answer.value, language)
        user = await self.cog.fetch_user(session.get("user_id", 0))
        # Un simple message, pas un embed : « @staff : réponse », comme une
        # conversation. La mention ne notifie personne.
        content = member_text(language, "modmail.reply_dm", staff=interaction.user.mention, message=text)
        sent = user is not None and await self.cog.dm(
            user, content[:2000], allowed_mentions=discord.AllowedMentions.none())
        if not sent:
            await interaction.followup.send(t(gid, "modmail.err_dm_closed"), ephemeral=True)
            return
        await interaction.followup.send(
            embed=discord.Embed(
                title=t(gid, "modmail.reply_sent_title"),
                # Sans traduction, le staff doit le savoir : le membre lit le
                # message dans la langue où il a été écrit.
                description=t(gid, "modmail.reply_sent_desc", language=LANGUAGE_NAMES.get(language, language))
                if translated else t(gid, "modmail.reply_sent_untranslated"),
                color=COLOR_SUCCESS if translated else COLOR_WARNING,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModMail(bot))
    log.info("Cog ModMail chargé")
