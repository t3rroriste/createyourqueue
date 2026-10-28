"""
MMR — Classement de niveau, façon Rocket League.
=================================================
Le classement par victoires récompense celui qui joue le plus, pas celui qui
joue le mieux : quarante victoires sur soixante parties passaient derrière
trois victoires sur trois. Le MMR corrige ça — chaque partie déplace le
joueur, à la hausse comme à la baisse.

Règles, toutes réglables par serveur (voir `/mmr`) :
"""

from __future__ import annotations

from i18n import t

# Bornes de sécurité : un serveur ne doit pas pouvoir se configurer un
# système où une partie fait gagner 10 000 points.
MAX_POINTS = 500
MAX_TIERS = 10

# (clé du nom, seuil, couleur, icône par défaut)
DEFAULT_TIERS = [
    ("bronze", 0, 0xCD7F32, "🥉"),
    ("silver", 800, 0xC0C0C0, "🥈"),
    ("gold", 1000, 0xF1C40F, "🥇"),
    ("platinum", 1200, 0x4FC3F7, "💎"),
    ("diamond", 1400, 0x5865F2, "🔷"),
    ("champion", 1600, 0x9B59B6, "👑"),
    ("grand_champion", 1800, 0xE74C3C, "🏆"),
]


def default_tiers(guild_id: int | None) -> list[dict]:
    """Paliers par défaut, nommés dans la langue du serveur."""
    return [
        {"name": t(guild_id, f"mmr.tier_{key}"), "min": threshold, "color": color, "icon": icon}
        for key, threshold, color, icon in DEFAULT_TIERS
    ]


def sorted_tiers(config: dict) -> list[dict]:
    """Paliers du plus bas au plus haut, seuils invalides écartés."""
    clean = []
    for tier in config.get("tiers") or []:
        try:
            clean.append({**tier, "min": int(tier.get("min", 0))})
        except (TypeError, ValueError):
            continue
    return sorted(clean, key=lambda item: item["min"])


def tier_for(config: dict, value: int) -> dict | None:
    """Palier atteint avec ce MMR, ou None si aucun palier n'est configuré."""
    reached = None
    for tier in sorted_tiers(config):
        if value >= tier["min"]:
            reached = tier
        else:
            break
    return reached


def next_tier(config: dict, value: int) -> dict | None:
    """Palier suivant, pour afficher ce qu'il reste à gagner."""
    for tier in sorted_tiers(config):
        if tier["min"] > value:
            return tier
    return None


def delta(config: dict, *, won: bool, is_mvp: bool = False, streak: int = 0) -> int:
    """Points gagnés ou perdus sur une partie."""
    change = int(config.get("win", 15)) if won else -int(config.get("loss", 12))
    if is_mvp:
        change += int(config.get("mvp_bonus", 8))
    if won and streak >= 2:
        change += int(config.get("streak_bonus", 0)) * (streak - 1)
    return change


def apply(config: dict, current: int, *, won: bool, is_mvp: bool = False,
          streak: int = 0) -> tuple[int, int]:
    """Nouveau MMR et variation appliquée. Le total reste positif ou nul."""
    change = delta(config, won=won, is_mvp=is_mvp, streak=streak)
    new_value = max(0, current + change)
    return new_value, new_value - current


def progress(config: dict, value: int) -> tuple[int, int]:
    """(points dans le palier, largeur du palier) pour une barre de progression."""
    current = tier_for(config, value)
    upper = next_tier(config, value)
    if current is None or upper is None:
        return 1, 1
    span = max(1, upper["min"] - current["min"])
    return max(0, min(span, value - current["min"])), span


def format_change(change: int) -> str:
    """« +15 » / « -12 » / « ±0 », signe toujours visible."""
    if change > 0:
        return f"+{change}"
    if change < 0:
        return str(change)
    return "±0"
