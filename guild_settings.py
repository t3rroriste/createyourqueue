"""
Guild settings — Réglages persistants par serveur.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
import os
import time
from datetime import datetime, timezone
from typing import Any
from json_store import write_json
import logging

SETTINGS_FILE = "data/guild_settings.json"
log = logging.getLogger("bot.settings")
_settings: dict[int, dict[str, Any]] = {}


def load_settings() -> None:
    """Charge les réglages. Un fichier illisible est mis de côté, jamais écrasé.

    L'ancien code ignorait l'erreur et repartait d'un dictionnaire vide : le
    premier réglage modifié réécrivait alors le fichier... vide, et la
    configuration de tous les serveurs était perdue pour de bon."""
    global _settings
    if not os.path.exists(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _settings = {int(k): v for k, v in data.items()}
    except (OSError, ValueError, AttributeError) as e:
        backup = f"{SETTINGS_FILE}.illisible-{int(time.time())}"
        try:
            os.replace(SETTINGS_FILE, backup)
            log.error(f"Réglages illisibles ({e}) : fichier mis de côté dans {backup}")
        except OSError:
            log.error(f"Réglages illisibles ({e}), et impossibles à mettre de côté")
        return
    # Le tableau de bord en ligne a été supprimé : son jeton n'a plus de
    # raison de rester dans les données de chaque serveur.
    stale = [info for info in _settings.values()
             if isinstance(info, dict) and "dashboard_token" in info]
    for info in stale:
        del info["dashboard_token"]
    if stale:
        save_settings()


# Ecriture differee : chaque setter enregistre tout le fichier. Sur une
# boucle — le MMR de huit joueurs en fin de match — cela faisait huit
# reecritures completes pour un seul resultat. `deferred_save()` les
# regroupe en une, sans changer un seul appelant.
_defer_depth = 0
_defer_dirty = False


def save_settings() -> None:
    global _defer_dirty
    if _defer_depth:
        _defer_dirty = True
        return
    write_json(SETTINGS_FILE, {str(k): v for k, v in _settings.items()}, indent=4, ensure_ascii=False)


@contextmanager
def deferred_save():
    """Regroupe les enregistrements du bloc en une seule ecriture.

    Reentrant : un bloc imbrique n ecrit pas avant la sortie du plus
    exterieur. L ecriture a lieu meme si le bloc leve, pour ne pas perdre ce
    qui a deja ete modifie en memoire."""
    global _defer_depth, _defer_dirty
    _defer_depth += 1
    try:
        yield
    finally:
        _defer_depth -= 1
        if _defer_depth == 0 and _defer_dirty:
            _defer_dirty = False
            save_settings()


def _ensure(guild_id: int) -> dict[str, Any]:
    if guild_id not in _settings:
        _settings[guild_id] = {
            "setup_complete": False,
            "setup_at": None,
            "setup_by": None,
        }
        save_settings()
    return _settings[guild_id]


def is_setup_complete(guild_id: int | None) -> bool:
    if guild_id is None:
        return False
    from config import GUNZFRANCE_GUILD_ID
    if GUNZFRANCE_GUILD_ID and guild_id == GUNZFRANCE_GUILD_ID:
        return True
    return bool(_settings.get(guild_id, {}).get("setup_complete"))


def mark_setup_complete(guild_id: int, user_id: int) -> None:
    info = _ensure(guild_id)
    info["setup_complete"] = True
    info["setup_at"] = datetime.now(timezone.utc).isoformat()
    info["setup_by"] = user_id
    save_settings()


def save_queue_config(guild_id: int, queue_config: dict[str, Any]) -> None:
    """Sauvegarde la configuration de queue pour un serveur."""
    info = _ensure(guild_id)
    info["queue_config"] = queue_config
    save_settings()


def get_queue_config(guild_id: int) -> dict[str, Any] | None:
    """Récupère la configuration de queue pour un serveur."""
    return _settings.get(guild_id, {}).get("queue_config")


def get_webhook_url(guild_id: int) -> str | None:
    """Webhook facultatif utilisé pour publier le résultat d'une partie.

    Accesseur plutôt que lecture directe de `_settings` depuis un cog : le
    jour où le stockage change, il n'y a qu'un endroit à corriger."""
    return _settings.get(guild_id, {}).get("webhook_url")


MAX_QUEUE_PRESETS = 10


def get_queue_presets(guild_id: int) -> list[dict[str, Any]]:
    """Presets de queue enregistrés, triés A-Z pour que les menus soient lisibles.

    Un preset est une configuration de queue complète, plus une clé `name` qui
    l'identifie (c'est ce nom que /schedule mémorise)."""
    presets = _settings.get(guild_id, {}).get("queue_presets", [])
    return sorted(presets, key=lambda preset: str(preset.get("name", "")).lower())


def get_queue_preset(guild_id: int, name: str) -> dict[str, Any] | None:
    """Preset par son nom, insensible à la casse."""
    wanted = name.lower()
    return next(
        (p for p in get_queue_presets(guild_id) if str(p.get("name", "")).lower() == wanted),
        None,
    )


def save_queue_preset(guild_id: int, preset: dict[str, Any]) -> None:
    """Crée un preset, ou remplace celui qui porte déjà ce nom.

    Le plafond est appliqué ici et pas seulement dans l'interface : aucun
    chemin d'appel ne doit pouvoir faire grossir le fichier de réglages sans
    limite. Lève ValueError("preset_limit_reached") quand il est atteint."""
    info = _ensure(guild_id)
    presets = info.setdefault("queue_presets", [])
    name = str(preset.get("name", "")).lower()
    for i, existing in enumerate(presets):
        if str(existing.get("name", "")).lower() == name:
            presets[i] = preset
            save_settings()
            return
    if len(presets) >= MAX_QUEUE_PRESETS:
        raise ValueError("preset_limit_reached")
    presets.append(preset)
    save_settings()


def delete_queue_preset(guild_id: int, name: str) -> bool:
    """Supprime un preset. Retourne True s'il existait."""
    info = _ensure(guild_id)
    presets = info.setdefault("queue_presets", [])
    wanted = name.lower()
    for i, existing in enumerate(presets):
        if str(existing.get("name", "")).lower() == wanted:
            del presets[i]
            save_settings()
            return True
    return False


SCHEDULE_DEFAULTS = {
    "enabled": False,
    "time": "21:00",
    "days": [0, 1, 2, 3, 4, 5, 6],  # 0 = lundi
    "reminder": True,
    "reminder_minutes": 15,
    "preset": None,         # nom du preset publié ; None = dernière queue configurée
    "last_run": None,       # "AAAA-MM-JJ" de la dernière publication
    "last_reminder": None,
}

SEASON_DEFAULTS = {
    "enabled": False,
    "reset_day": 1,         # jour du mois
    "announce": True,
    "keep_history": True,   # archiver le podium avant la remise à zéro
    "last_reset": None,     # "AAAA-MM"
    "archive": [],
}


def get_schedule(guild_id: int) -> dict[str, Any]:
    """Programmation automatique des queues, fusionnée avec les valeurs par défaut."""
    return {**SCHEDULE_DEFAULTS, **_settings.get(guild_id, {}).get("schedule", {})}


def set_schedule(guild_id: int, **changes: Any) -> None:
    info = _ensure(guild_id)
    info.setdefault("schedule", {}).update(changes)
    save_settings()


def get_season(guild_id: int) -> dict[str, Any]:
    """Réglages de la remise à zéro mensuelle du classement."""
    return {**SEASON_DEFAULTS, **_settings.get(guild_id, {}).get("season", {})}


def set_season(guild_id: int, **changes: Any) -> None:
    info = _ensure(guild_id)
    info.setdefault("season", {}).update(changes)
    save_settings()


def add_season_archive(guild_id: int, entry: dict[str, Any]) -> None:
    """Archive le podium d'une saison close (12 dernières conservées)."""
    info = _ensure(guild_id)
    season = info.setdefault("season", {})
    archive = season.setdefault("archive", [])
    archive.append(entry)
    del archive[:-12]
    save_settings()


def reset_guild(guild_id: int) -> list[str]:
    """Efface toute la configuration d'un serveur (voir /reset).

    Retourne la liste des sections effacées, pour le compte-rendu."""
    info = _settings.get(guild_id)
    if not info:
        return []
    cleared = [key for key in info if key not in ("setup_at", "setup_by")]
    _settings[guild_id] = {
        "setup_complete": False,
        "setup_at": None,
        "setup_by": None,
    }
    save_settings()
    return cleared


def get_status_panel(guild_id: int) -> dict[str, Any] | None:
    """Message du panneau d'état du bot (voir cogs/statuspanel.py)."""
    return _settings.get(guild_id, {}).get("status_panel")


def set_status_panel(guild_id: int, channel_id: int, message_id: int) -> None:
    info = _ensure(guild_id)
    info["status_panel"] = {"channel_id": channel_id, "message_id": message_id}
    save_settings()


def clear_status_panel(guild_id: int) -> None:
    info = _ensure(guild_id)
    if info.pop("status_panel", None) is not None:
        save_settings()


MAX_ROLE_PANELS = 2
MAX_ROLES_PER_PANEL = 20


def get_role_panels(guild_id: int) -> list[dict[str, Any]]:
    """Panneaux de rôles personnalisés d'un serveur (2 maximum)."""
    return _settings.get(guild_id, {}).get("role_panels", [])


def get_role_panel(guild_id: int, panel_id: int) -> dict[str, Any] | None:
    return next((p for p in get_role_panels(guild_id) if p.get("id") == panel_id), None)


def save_role_panel(guild_id: int, panel: dict[str, Any]) -> None:
    """Crée ou met à jour un panneau. Le plafond MAX_ROLE_PANELS est appliqué
    ici et pas seulement dans l'interface : une commande ne doit jamais pouvoir
    le contourner."""
    info = _ensure(guild_id)
    panels = info.setdefault("role_panels", [])
    for i, existing in enumerate(panels):
        if existing.get("id") == panel.get("id"):
            panels[i] = panel
            save_settings()
            return
    if len(panels) >= MAX_ROLE_PANELS:
        raise ValueError("panel_limit_reached")
    panels.append(panel)
    save_settings()


def delete_role_panel(guild_id: int, panel_id: int) -> bool:
    info = _ensure(guild_id)
    panels = info.setdefault("role_panels", [])
    for i, existing in enumerate(panels):
        if existing.get("id") == panel_id:
            del panels[i]
            save_settings()
            return True
    return False


def next_role_panel_id(guild_id: int) -> int:
    """Plus petit identifiant libre (1..MAX_ROLE_PANELS), 0 si tout est pris."""
    used = {p.get("id") for p in get_role_panels(guild_id)}
    for candidate in range(1, MAX_ROLE_PANELS + 1):
        if candidate not in used:
            return candidate
    return 0


MAX_QUEUE_HISTORY = 20


def get_queue_history(guild_id: int) -> list[dict[str, Any]]:
    """Historique des dernières queues terminées pour un serveur, plus récente en premier."""
    return list(reversed(_settings.get(guild_id, {}).get("queue_history", [])))


def add_queue_history_entry(guild_id: int, entry: dict[str, Any]) -> None:
    """Ajoute une queue terminée à l'historique (persistant), en ne gardant que
    les MAX_QUEUE_HISTORY dernières pour ne pas grossir indéfiniment."""
    info = _ensure(guild_id)
    history = info.setdefault("queue_history", [])
    history.append(entry)
    del history[:-MAX_QUEUE_HISTORY]
    save_settings()


MMR_DEFAULTS = {
    "enabled": True,
    "captains": True,        # vote des capitaines + draft avant la partie
    "start": 1000,
    "win": 15,
    "loss": 12,
    "mvp_bonus": 8,
    "streak_bonus": 0,       # points en plus par victoire consécutive
    "captain_vote_seconds": 60,
    "mvp_vote_seconds": 300,   # 5 minutes
    "cleanup_seconds": 120,    # tout se ferme 2 minutes après le vote
    "rank_roles": True,        # attribuer un rôle de rang selon le MMR
    "tiers": None,             # None = paliers par défaut, traduits
}


def get_mmr_config(guild_id: int) -> dict[str, Any]:
    """Réglages du système de MMR et de salon de match."""
    return {**MMR_DEFAULTS, **_settings.get(guild_id, {}).get("mmr", {})}


def set_mmr_config(guild_id: int, **changes: Any) -> None:
    info = _ensure(guild_id)
    info.setdefault("mmr", {}).update(changes)
    save_settings()


def get_player_mmr(guild_id: int, user_id: int, default: int) -> int:
    """MMR d'un joueur sur CE serveur.

    Volontairement par serveur : un niveau gagné dans une communauté n'a pas
    de sens dans une autre, qui ne joue ni au même jeu ni au même format."""
    raw = _settings.get(guild_id, {}).get("mmr_players", {}).get(str(user_id))
    try:
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


def set_player_mmr(guild_id: int, user_id: int, value: int) -> None:
    info = _ensure(guild_id)
    info.setdefault("mmr_players", {})[str(user_id)] = max(0, int(value))
    save_settings()


def get_match_state(guild_id: int) -> dict[str, Any] | None:
    """Match en cours (salon privé, phase, échéances).

    Persisté pour qu'un redémarrage du bot ne laisse pas un salon privé et
    des rôles d'équipe orphelins : au démarrage, la boucle reprend là où elle
    en était ou nettoie."""
    return _settings.get(guild_id, {}).get("match")


def set_match_state(guild_id: int, state: dict[str, Any] | None) -> None:
    info = _ensure(guild_id)
    if state is None:
        info.pop("match", None)
    else:
        info["match"] = state
    save_settings()


# Salons/rôles que l'assistant fait choisir. (clé, type, obligatoire)
# Rien n'est créé automatiquement : l'organisateur désigne des salons qui
# existent déjà sur son serveur, quel que soit leur nom.
# Une vue Discord n'a que 5 rangées et un menu déroulant en occupe une
# entière : l'étape 1 en montre quatre, la place restante servant aux
# boutons. Le salon du classement est demandé à l'étape 2, avec l'option
# classement dont il dépend.
WIZARD_SLOTS = [
    ("channel_queue_command", "text", True),
    ("channel_queue_announcement", "text", True),
    ("voice_queue_waiting", "voice", True),
]

# Salons facultatifs, demandés à l'étape 2 avec les autres options : on ne
# fait pas désigner un salon de résultats à qui ne veut pas de résultats.
OPTIONAL_SLOTS = [
    ("channel_queue_resultat", "text", False),
    ("channel_queue_classement", "text", False),
]

FEATURE_DEFAULTS = {
    "leaderboard": False,   # classement + /stats
    "mvp": False,           # salon de match, capitaines, vote MVP, MMR
    "clans": False,         # salon + rôle par clan, ClanWar (voir cogs/clan.py)
    # Demandes d'adhésion : annoncées dans le salon du clan, ou silencieuses
    # et visibles seulement derrière le bouton Invites.
    "clan_notice": True,
    "status": False,        # panneau d'état permanent (voir cogs/statuspanel.py)
}


def get_features(guild_id: int) -> dict[str, Any]:
    """Fonctions activées à la carte. Tout est éteint tant qu'on n'a pas dit oui."""
    return {**FEATURE_DEFAULTS, **_settings.get(guild_id, {}).get("features", {})}


def set_features(guild_id: int, **changes: Any) -> None:
    info = _ensure(guild_id)
    info.setdefault("features", {}).update(changes)
    save_settings()


def channels_ready(guild_id: int) -> bool:
    """Tous les salons obligatoires ont-ils été désignés ?"""
    ids = _settings.get(guild_id, {}).get("resource_ids", {})
    return all(ids.get(key) for key, _kind, required in WIZARD_SLOTS if required)


def queue_ready(guild_id: int) -> bool:
    """Le serveur est-il prêt à lancer une queue ?

    Il faut les salons **et** un rôle organisateur : sans ce rôle, personne
    ne pourrait ouvrir le panneau, pas même celui qui vient de configurer."""
    ids = _settings.get(guild_id, {}).get("resource_ids", {})
    return channels_ready(guild_id) and bool(ids.get("role_staff"))


def get_setup_panel(guild_id: int) -> dict[str, Any] | None:
    """Message de configuration publié à l'arrivée du bot.

    Mémorisé pour réactiver ses menus après un redémarrage : un serveur qui
    ajoute le bot le soir et le configure le lendemain doit retrouver un
    panneau qui répond."""
    return _settings.get(guild_id, {}).get("setup_panel")


def set_setup_panel(guild_id: int, channel_id: int, message_id: int) -> None:
    info = _ensure(guild_id)
    info["setup_panel"] = {"channel_id": channel_id, "message_id": message_id}
    save_settings()


def get_custom_names(guild_id: int) -> dict[str, str]:
    """Noms choisis à la main pour les salons et rôles du bot.

    Un nom personnalisé prime sur le nom traduit : c'est un choix explicite
    de l'administrateur, il ne doit être écrasé ni par un changement de
    langue, ni par la protection des noms."""
    return _settings.get(guild_id, {}).get("custom_names", {})


def get_custom_name(guild_id: int, key: str) -> str | None:
    return get_custom_names(guild_id).get(key)


def set_custom_name(guild_id: int, key: str, name: str | None) -> None:
    """Fixe un nom personnalisé, ou le retire avec None (retour au traduit)."""
    info = _ensure(guild_id)
    names = info.setdefault("custom_names", {})
    if name:
        names[key] = name
    else:
        names.pop(key, None)
    save_settings()


MAX_PARTY = 4          # duo, trio, quatro
PARTY_TTL = 12 * 3600  # une équipe formée hier ne s'applique pas aujourd'hui


def _fresh_parties(guild_id: int) -> list[dict[str, Any]]:
    """Groupes encore valides, les périmés écartés à la lecture.

    Purger à la lecture évite une tâche de fond : un groupe expiré n'a aucun
    effet et disparaît à la première écriture qui suit."""
    limit = time.time() - PARTY_TTL
    return [
        p for p in _settings.get(guild_id, {}).get("parties", [])
        if p.get("created_at", 0) >= limit
    ]


def get_party_of(guild_id: int, user_id: int) -> dict[str, Any] | None:
    """Groupe auquel appartient ce joueur, ou None."""
    return next((p for p in _fresh_parties(guild_id) if user_id in p.get("members", [])), None)


def save_party(guild_id: int, members: list[int]) -> None:
    """Enregistre un groupe. Chacun ne peut être que dans un seul : les
    anciens groupes de ses membres sont dissous, sinon un joueur pourrait
    être « garanti » avec deux équipes différentes."""
    info = _ensure(guild_id)
    kept = [
        p for p in _fresh_parties(guild_id)
        if not set(p.get("members", [])) & set(members)
    ]
    kept.append({"members": list(dict.fromkeys(members)), "created_at": time.time()})
    info["parties"] = kept
    save_settings()


def dissolve_party(guild_id: int, user_id: int) -> bool:
    """Dissout le groupe d'un joueur. Retourne True s'il en avait un."""
    info = _ensure(guild_id)
    before = _fresh_parties(guild_id)
    after = [p for p in before if user_id not in p.get("members", [])]
    info["parties"] = after
    save_settings()
    return len(after) != len(before)


def get_team_requests(guild_id: int) -> list[dict[str, Any]]:
    return _settings.get(guild_id, {}).get("team_requests", [])


def get_team_request(guild_id: int, message_id: int) -> dict[str, Any] | None:
    return next((r for r in get_team_requests(guild_id) if r.get("message_id") == message_id), None)


def save_team_request(guild_id: int, request: dict[str, Any]) -> None:
    info = _ensure(guild_id)
    requests = info.setdefault("team_requests", [])
    for i, existing in enumerate(requests):
        if existing.get("message_id") == request.get("message_id"):
            requests[i] = request
            save_settings()
            return
    requests.append(request)
    del requests[:-20]
    save_settings()


def delete_team_request(guild_id: int, message_id: int) -> bool:
    info = _ensure(guild_id)
    requests = info.setdefault("team_requests", [])
    for i, existing in enumerate(requests):
        if existing.get("message_id") == message_id:
            del requests[i]
            save_settings()
            return True
    return False


MAX_POLLS = 10


def get_polls(guild_id: int) -> list[dict[str, Any]]:
    """Sondages du serveur, le plus récent en dernier."""
    return _settings.get(guild_id, {}).get("polls", [])


def get_poll(guild_id: int, message_id: int) -> dict[str, Any] | None:
    return next((p for p in get_polls(guild_id) if p.get("message_id") == message_id), None)


def save_poll(guild_id: int, poll: dict[str, Any]) -> None:
    """Crée ou met à jour un sondage, identifié par son message.

    Les plus anciens sont oubliés au-delà de MAX_POLLS : un sondage sert le
    temps d'un vote, le garder à vie ferait grossir le fichier pour rien."""
    info = _ensure(guild_id)
    polls = info.setdefault("polls", [])
    for i, existing in enumerate(polls):
        if existing.get("message_id") == poll.get("message_id"):
            polls[i] = poll
            save_settings()
            return
    polls.append(poll)
    del polls[:-MAX_POLLS]
    save_settings()


def delete_poll(guild_id: int, message_id: int) -> bool:
    info = _ensure(guild_id)
    polls = info.setdefault("polls", [])
    for i, existing in enumerate(polls):
        if existing.get("message_id") == message_id:
            del polls[i]
            save_settings()
            return True
    return False


def get_queue_blacklist_entries(guild_id: int) -> list[dict[str, Any]]:
    """Entrées complètes de la liste noire (membre, raison, auteur, date).

    Les premières versions ne stockaient qu'une liste d'IDs : on normalise à la
    lecture pour qu'une liste noire créée avant l'ajout des raisons continue de
    fonctionner sans migration."""
    raw = _settings.get(guild_id, {}).get("queue_blacklist", [])
    entries = []
    for item in raw:
        if isinstance(item, dict):
            entries.append(item)
        else:
            entries.append({"user_id": item, "reason": None, "by": None, "at": None})
    return entries


def get_queue_blacklist(guild_id: int) -> list[int]:
    """IDs seuls — utilisé pour le test d'appartenance à chaque réaction."""
    return [e["user_id"] for e in get_queue_blacklist_entries(guild_id)]


def add_to_queue_blacklist(guild_id: int, user_id: int, reason: str | None = None, by: int | None = None) -> bool:
    """Ajoute un membre à la liste noire. Retourne False s'il y était déjà."""
    info = _ensure(guild_id)
    entries = get_queue_blacklist_entries(guild_id)
    if any(e["user_id"] == user_id for e in entries):
        return False
    entries.append({
        "user_id": user_id,
        "reason": reason,
        "by": by,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    info["queue_blacklist"] = entries
    save_settings()
    return True


def remove_from_queue_blacklist(guild_id: int, user_id: int) -> bool:
    """Retire un membre de la liste noire. Retourne False s'il n'y était pas."""
    info = _ensure(guild_id)
    entries = get_queue_blacklist_entries(guild_id)
    remaining = [e for e in entries if e["user_id"] != user_id]
    if len(remaining) == len(entries):
        return False
    info["queue_blacklist"] = remaining
    save_settings()
    return True


def get_antiraid_config(guild_id: int) -> dict[str, Any]:
    """Config anti-raid pour un serveur, fusionnée avec les valeurs par défaut de config.py."""
    from config import (
        ANTIRAID_JOIN_THRESHOLD,
        ANTIRAID_JOIN_INTERVAL,
        ANTIRAID_MIN_ACCOUNT_AGE_HOURS,
        ANTIRAID_AUTO_KICK,
    )
    defaults = {
        "join_threshold": ANTIRAID_JOIN_THRESHOLD,
        "join_interval": ANTIRAID_JOIN_INTERVAL,
        "min_account_age_hours": ANTIRAID_MIN_ACCOUNT_AGE_HOURS,
        "auto_kick": ANTIRAID_AUTO_KICK,
    }
    defaults.update(_settings.get(guild_id, {}).get("antiraid_config", {}))
    return defaults


def set_antiraid_config(guild_id: int, **overrides: Any) -> None:
    """Met à jour (partiellement) la config anti-raid d'un serveur."""
    info = _ensure(guild_id)
    info.setdefault("antiraid_config", {}).update(overrides)
    save_settings()


def get_saved_teams(guild_id: int) -> list[dict[str, Any]]:
    """Bibliothèque d'équipes réutilisables (nom + couleur) sauvegardée pour un serveur, triée A-Z."""
    teams = _settings.get(guild_id, {}).get("saved_teams", [])
    return sorted(teams, key=lambda team: team["name"].lower())


def add_saved_team(guild_id: int, name: str, color: str) -> None:
    """Ajoute une équipe à la bibliothèque du serveur, ou met à jour sa couleur si le nom existe déjà (insensible à la casse)."""
    info = _ensure(guild_id)
    teams = info.setdefault("saved_teams", [])
    for team in teams:
        if team["name"].lower() == name.lower():
            team["color"] = color
            save_settings()
            return
    teams.append({"name": name, "color": color})
    save_settings()


def get_classement_message_id(guild_id: int) -> int | None:
    """ID du message de classement affiché dans le salon dédié — mémorisé pour
    pouvoir l'éditer/remplacer sans jamais en laisser deux."""
    return _settings.get(guild_id, {}).get("classement_message_id")


def set_classement_message_id(guild_id: int, message_id: int) -> None:
    info = _ensure(guild_id)
    info["classement_message_id"] = message_id
    save_settings()


def get_resource_id(guild_id: int, key: str) -> int | None:
    """ID mémorisé d'un salon/rôle/catégorie géré par le bot (voir resources.py)."""
    return _settings.get(guild_id, {}).get("resource_ids", {}).get(key)


def set_resource_id(guild_id: int, key: str, resource_id: int) -> None:
    info = _ensure(guild_id)
    info.setdefault("resource_ids", {})[key] = resource_id
    save_settings()


def clear_resource_id(guild_id: int, key: str) -> bool:
    """Oublie un salon/rôle désigné. Renvoie True s'il y en avait un.

    Certains réglages facultatifs doivent pouvoir être **retirés** et pas
    seulement remplacés : le rôle Connexion, par exemple, dont l'absence veut
    dire « vocal d'attente ouvert à tout le monde »."""
    ids = _settings.get(guild_id, {}).get("resource_ids", {})
    if key not in ids:
        return False
    del ids[key]
    save_settings()
    return True


# ----------------------------------------------------------------------
# Clans
#
# Un clan appartient a un serveur : deux communautes peuvent avoir un clan
# du meme nom sans se marcher dessus, et supprimer un serveur n emporte que
# ses clans. L identifiant est numerique et jamais reutilise, pour qu un
# renommage ne casse ni les invitations en cours ni le classement.
# ----------------------------------------------------------------------
MAX_CLAN_NAME = 32
MAX_CLANS_PER_GUILD = 200


def get_clans(guild_id: int) -> dict:
    """Tous les clans du serveur, par identifiant."""
    return _settings.get(guild_id, {}).get("clans", {})


def get_clan(guild_id: int, clan_id: str) -> dict | None:
    return get_clans(guild_id).get(str(clan_id))


def clan_of(guild_id: int, user_id: int) -> dict | None:
    """Le clan d un joueur, ou None. Un joueur n appartient qu a un clan."""
    for clan in get_clans(guild_id).values():
        if user_id in clan.get("members", []):
            return clan
    return None


def clan_named(guild_id: int, name: str) -> dict | None:
    """Recherche insensible a la casse : deux clans ne peuvent pas porter le
    meme nom sur un serveur, sinon le classement devient illisible."""
    wanted = name.strip().casefold()
    for clan in get_clans(guild_id).values():
        if clan.get("name", "").casefold() == wanted:
            return clan
    return None


def create_clan(guild_id: int, *, name: str, leader_id: int,
                icon_url: str = "", invite_url: str = "") -> dict:
    """Cree un clan et y place son fondateur.

    Leve ValueError si le nom est deja pris, si le fondateur a deja un clan,
    ou si le serveur a atteint sa limite."""
    if clan_named(guild_id, name) is not None:
        raise ValueError("name_taken")
    if clan_of(guild_id, leader_id) is not None:
        raise ValueError("already_in_clan")
    info = _ensure(guild_id)
    clans = info.setdefault("clans", {})
    if len(clans) >= MAX_CLANS_PER_GUILD:
        raise ValueError("full")
    next_id = str(int(info.get("clan_seq", 0)) + 1)
    info["clan_seq"] = int(next_id)
    clan = {
        "id": next_id,
        "name": name.strip()[:MAX_CLAN_NAME],
        "icon_url": icon_url.strip(),
        "invite_url": invite_url.strip(),
        "leader_id": leader_id,
        "members": [leader_id],
        "created_at": int(time.time()),
    }
    clans[next_id] = clan
    save_settings()
    return clan


def add_clan_member(guild_id: int, clan_id: str, user_id: int) -> bool:
    """Ajoute un joueur. False s il est deja dans un clan (le sien ou un autre)."""
    clan = get_clan(guild_id, clan_id)
    if clan is None or clan_of(guild_id, user_id) is not None:
        return False
    clan.setdefault("members", []).append(user_id)
    save_settings()
    return True


def remove_clan_member(guild_id: int, clan_id: str, user_id: int) -> bool:
    """Retire un joueur. Le clan disparait si son chef le quitte : un clan
    sans chef ne pourrait plus ni inviter ni etre dissous."""
    clan = get_clan(guild_id, clan_id)
    if clan is None or user_id not in clan.get("members", []):
        return False
    clan["members"].remove(user_id)
    if user_id == clan.get("leader_id") or not clan["members"]:
        _settings.get(guild_id, {}).get("clans", {}).pop(str(clan_id), None)
    save_settings()
    return True


def set_clan_fields(guild_id: int, clan_id: str, **fields: Any) -> dict | None:
    """Memorise le salon, le role et les messages d un clan.

    Ces identifiants sont indispensables pour retrouver la fiche a mettre a
    jour quand l effectif change : la reconstruire en cherchant le salon par
    son nom casserait des qu un moderateur le renomme."""
    clan = get_clan(guild_id, clan_id)
    if clan is None:
        return None
    clan.update(fields)
    save_settings()
    return clan


def clan_by_channel(guild_id: int, channel_id: int) -> dict | None:
    """Le clan a qui appartient un salon. C est ainsi que les boutons de la
    fiche savent de quel clan ils parlent, sans rien coder dans leur id."""
    for clan in get_clans(guild_id).values():
        if clan.get("channel_id") == channel_id:
            return clan
    return None


def transfer_clan_leader(guild_id: int, clan_id: str, new_leader_id: int) -> bool:
    """Passe la propriete du clan a un de ses membres. False si le nouveau
    chef n est pas dans le clan."""
    clan = get_clan(guild_id, clan_id)
    if clan is None or new_leader_id not in clan.get("members", []):
        return False
    clan["leader_id"] = new_leader_id
    save_settings()
    return True


# -- Demandes recues par un clan ---------------------------------------
# Deux files distinctes : les defis d autres clans (ClanWar) et les demandes
# d adhesion de joueurs. Bornees, parce qu une file sans limite se remplit
# toute seule et finit par depasser la taille d un embed.
MAX_CLAN_REQUESTS = 15


def get_clan_requests(guild_id: int, clan_id: str, kind: str) -> list[dict[str, Any]]:
    """kind : "wars" (defis recus) ou "joins" (demandes d adhesion)."""
    clan = get_clan(guild_id, clan_id)
    return list(clan.get(kind, [])) if clan else []


def add_clan_request(guild_id: int, clan_id: str, kind: str,
                     request: dict[str, Any]) -> bool:
    """Ajoute une demande. False si la meme est deja en attente : deux clics
    ne doivent pas produire deux defis identiques."""
    clan = get_clan(guild_id, clan_id)
    if clan is None:
        return False
    queue = clan.setdefault(kind, [])
    key = "from_clan" if kind == "wars" else "user_id"
    if any(item.get(key) == request.get(key) for item in queue):
        return False
    queue.append(request)
    del queue[:-MAX_CLAN_REQUESTS]
    save_settings()
    return True


def remove_clan_request(guild_id: int, clan_id: str, kind: str,
                        value: Any) -> dict[str, Any] | None:
    """Retire une demande et la renvoie, pour pouvoir repondre a son auteur."""
    clan = get_clan(guild_id, clan_id)
    if clan is None:
        return None
    queue = clan.setdefault(kind, [])
    key = "from_clan" if kind == "wars" else "user_id"
    for i, item in enumerate(queue):
        if item.get(key) == value:
            queue.pop(i)
            save_settings()
            return item
    return None


# ----------------------------------------------------------------------
# Sessions de ClanWar actives
# ----------------------------------------------------------------------
def get_clan_war_session(guild_id: int) -> dict[str, Any] | None:
    """Session de ClanWar active pour un serveur."""
    return _settings.get(guild_id, {}).get("clan_war_session")


def set_clan_war_session(guild_id: int, session: dict[str, Any] | None) -> None:
    """Enregistre ou retire une session de ClanWar."""
    info = _ensure(guild_id)
    if session is None:
        info.pop("clan_war_session", None)
    else:
        info["clan_war_session"] = session
    save_settings()


def clear_clan_war_session(guild_id: int) -> None:
    """Retire la session de ClanWar d'un serveur."""
    info = _settings.get(guild_id)
    if info and "clan_war_session" in info:
        del info["clan_war_session"]
        save_settings()


def get_modmail_channel(guild_id: int) -> int | None:
    """Récupère l'ID du channel modmail d'un serveur."""
    if guild_id in _settings:
        return _settings[guild_id].get("modmail_channel_id")
    return None


def set_modmail_channel(guild_id: int, channel_id: int) -> None:
    """Définit l'ID du channel modmail d'un serveur."""
    if guild_id not in _settings:
        _settings[guild_id] = {}
    _settings[guild_id]["modmail_channel_id"] = channel_id
    save_settings()


def get_ticket_config(guild_id: int) -> dict[str, Any] | None:
    """Récupère la configuration du système de ticket d'un serveur."""
    if guild_id in _settings:
        return _settings[guild_id].get("ticket_config")
    return None


def set_ticket_config(guild_id: int, config: dict[str, Any]) -> None:
    """Définit la configuration du système de ticket d'un serveur."""
    if guild_id not in _settings:
        _settings[guild_id] = {}
    _settings[guild_id]["ticket_config"] = config
    save_settings()


def get_clan_announcement_count(guild_id: int, clan_id: int) -> int:
    """Récupère le nombre d'annonces dans le channel de liaison d'un clan."""
    if guild_id in _settings:
        clan_data = _settings[guild_id].get("clan_announcements", {})
        return clan_data.get(str(clan_id), 0)
    return 0


def increment_clan_announcement(guild_id: int, clan_id: int) -> None:
    """Incrémente le compteur d'annonces d'un clan."""
    if guild_id not in _settings:
        _settings[guild_id] = {}
    if "clan_announcements" not in _settings[guild_id]:
        _settings[guild_id]["clan_announcements"] = {}
    _settings[guild_id]["clan_announcements"][str(clan_id)] = get_clan_announcement_count(guild_id, clan_id) + 1
    save_settings()


def reset_clan_announcement(guild_id: int, clan_id: int) -> None:
    """Réinitialise le compteur d'annonces d'un clan."""
    if guild_id not in _settings:
        _settings[guild_id] = {}
    if "clan_announcements" not in _settings[guild_id]:
        _settings[guild_id]["clan_announcements"] = {}
    _settings[guild_id]["clan_announcements"][str(clan_id)] = 0
    save_settings()


def reset_all_clan_announcements(guild_id: int) -> None:
    """Réinitialise tous les compteurs d'annonces d'un serveur."""
    if guild_id not in _settings:
        _settings[guild_id] = {}
    _settings[guild_id]["clan_announcements"] = {}
    save_settings()

