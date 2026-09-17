"""
Embeds — style commun à tous les panneaux du bot.
=================================================
Chaque cog construisait ses embeds dans son coin : couleurs choisies au
hasard (bleu ici, vert là pour la même idée), pieds de page tantôt présents
tantôt absents, chiffres bruts sans mise en forme. Résultat, deux commandes
côte à côte n'avaient pas l'air de venir du même bot.

Ce module ne fait rien de magique : il donne un point de départ unique.
"""

from __future__ import annotations

import discord

from i18n import t


BRAND = 0x5865F2
SUCCESS = 0x57F287
ERROR = 0xED4245
WARNING = 0xFEE75C
GOLD = 0xF1C40F
NEUTRAL = 0x2B2D31
# Pour Discord, 0x000000 veut dire « pas de couleur » : la bordure disparaît.
BLACK = 0x010101

COLORS = {
    "brand": BRAND,
    "info": BRAND,
    "success": SUCCESS,
    "error": ERROR,
    "warning": WARNING,
    "gold": GOLD,
    "neutral": NEUTRAL,
    "black": BLACK,
}


RULE = "─" * 30

BLANK = "​"

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}



def base(
    guild_id: int | None,
    *,
    title: str | None = None,
    description: str | None = None,
    kind: str = "brand",
    footer: str | None = None,
    timestamp: bool = False,
    url: str | None = None,
) -> discord.Embed:
    """Embed déjà habillé : couleur d'intention, horodatage, pied de page."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=COLORS.get(kind, BRAND),
        url=url,
    )
    if timestamp:
        embed.timestamp = discord.utils.utcnow()
    # Pas de signature « CreateYourQueue » par défaut : le pied de page ne
    # porte que ce que l'appelant a à dire.
    if footer:
        embed.set_footer(text=footer)
    return embed


def brand(embed: discord.Embed, guild: discord.Guild | None) -> discord.Embed:
    """Ajoute l'icône du serveur au pied de page."""
    if guild is not None and guild.icon is not None and embed.footer.text:
        embed.set_footer(text=embed.footer.text, icon_url=guild.icon.url)
    return embed


def stat(embed: discord.Embed, name: str, value, *, inline: bool = True) -> discord.Embed:
    """Champ chiffré : la valeur est mise en gras une bonne fois pour toutes."""
    embed.add_field(name=name, value=f"**{value}**", inline=inline)
    return embed


def spacer(embed: discord.Embed) -> discord.Embed:
    """Champ invisible qui complète une ligne de 3 colonnes."""
    embed.add_field(name=BLANK, value=BLANK, inline=True)
    return embed


def align(embed: discord.Embed) -> discord.Embed:
    """Complète la dernière ligne pour qu'elle tienne bien en 3 colonnes."""
    inline_count = sum(1 for f in embed.fields if f.inline)
    for _ in range((3 - inline_count % 3) % 3):
        spacer(embed)
    return embed


def section(embed: discord.Embed, title: str, value: str) -> discord.Embed:
    """Bloc pleine largeur précédé d'un filet : sépare visuellement les
    parties d'un embed dense sans multiplier les embeds."""
    embed.add_field(name=title, value=value, inline=False)
    return embed


def medal(rank: int) -> str:
    """Médaille pour le podium, numéro aligné au-delà."""
    return MEDALS.get(rank, f"`#{rank:>2}`")


def trend(current: int, previous: int) -> str:
    """Flèche d'évolution entre deux valeurs comparables."""
    if current > previous:
        return "📈"
    if current < previous:
        return "📉"
    return "➖"


def state(on: bool) -> str:
    """Pastille d'état, identique partout où quelque chose s'active."""
    return "🟢" if on else "🔴"


def toggle_line(guild_id: int | None, on: bool) -> str:
    """« **🟢 Activer** / ~~🔴 Désactiver~~ » selon l'état."""
    return pick_line(guild_id, "wiz.opt_on", "wiz.opt_off", on)


def pick_line(guild_id: int | None, first_key: str, second_key: str, first: bool) -> str:
    """Même lecture que `toggle_line`, pour un choix entre deux modes qui ne
    sont ni « allumé » ni « éteint » : le retenu en gras, l'autre barré."""
    a = t(guild_id, first_key)
    b = t(guild_id, second_key)
    if first:
        return f"**{a}** / ~~{b}~~"
    return f"~~{a}~~ / **{b}**"
