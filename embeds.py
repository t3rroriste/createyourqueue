"""
Embeds — style commun à tous les panneaux du bot.
=================================================
Chaque cog construisait ses embeds dans son coin : couleurs choisies au
hasard (bleu ici, vert là pour la même idée), pieds de page tantôt présents
tantôt absents, chiffres bruts sans mise en forme. Résultat, deux commandes
côte à côte n'avaient pas l'air de venir du même bot.

Ce module ne fait rien de magique : il donne un point de départ unique.

- `base()` crée un embed déjà habillé (couleur d'intention, pied de page,
  horodatage) — on ne change plus la couleur à la main.
- Les couleurs portent une **intention**, pas une teinte : `success`,
  `error`, `warning`, `info`, `brand`, `gold`. Un message d'erreur est rouge
  partout, sans que personne ait à s'en souvenir.
- Les helpers d'affichage (`bar`, `medal`, `trend`…) évitent que chaque cog
  réinvente sa barre de progression avec des caractères différents.

Toutes les fonctions acceptent `guild_id=None` : les panneaux publiés hors
d'un serveur (démarrage, logs) restent lisibles.
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

COLORS = {
    "brand": BRAND,
    "info": BRAND,
    "success": SUCCESS,
    "error": ERROR,
    "warning": WARNING,
    "gold": GOLD,
    "neutral": NEUTRAL,
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
    """Embed déjà habillé : couleur d'intention, pied de page, horodatage.

    `kind` décrit ce que l'embed veut dire, pas sa couleur : le jour où la
    palette change, elle change ici seulement."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=COLORS.get(kind, BRAND),
        url=url,
    )
    if timestamp:
        embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text=footer if footer is not None else t(guild_id, "common.footer_main"))
    return embed


def brand(embed: discord.Embed, guild: discord.Guild | None) -> discord.Embed:
    """Ajoute l'icône du serveur au pied de page.

    Discord n'affiche l'icône que si le pied de page a du texte : on ne
    l'ajoute donc jamais à un embed sans footer."""
    if guild is not None and guild.icon is not None and embed.footer.text:
        embed.set_footer(text=embed.footer.text, icon_url=guild.icon.url)
    return embed


def stat(embed: discord.Embed, name: str, value, *, inline: bool = True) -> discord.Embed:
    """Champ chiffré : la valeur est mise en gras une bonne fois pour toutes."""
    embed.add_field(name=name, value=f"**{value}**", inline=inline)
    return embed


def spacer(embed: discord.Embed) -> discord.Embed:
    """Champ invisible qui complète une ligne de 3 colonnes.

    Sans lui, deux champs en ligne s'étalent sur toute la largeur et la
    grille se déforme d'un embed à l'autre."""
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
    """Médaille pour le podium, numéro aligné au-delà.

    Le rang est cadré à droite dans un bloc de code pour que la colonne des
    noms reste alignée quels que soient les rangs affichés."""
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
    """« **🟢 Activer** / ~~🔴 Désactiver~~ » selon l'état.

    Barrer l'option non retenue plutôt que de l'effacer garde les deux choix
    visibles : on voit du même coup ce que fera le prochain clic."""
    return pick_line(guild_id, "wiz.opt_on", "wiz.opt_off", on)


def pick_line(guild_id: int | None, first_key: str, second_key: str, first: bool) -> str:
    """Même lecture que `toggle_line`, pour un choix entre deux modes qui ne
    sont ni « allumé » ni « éteint » : le retenu en gras, l'autre barré."""
    a = t(guild_id, first_key)
    b = t(guild_id, second_key)
    if first:
        return f"**{a}** / ~~{b}~~"
    return f"~~{a}~~ / **{b}**"
