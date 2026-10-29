"""
Historique des matchs, saisons et statistiques.
===============================================
Le bot jouait des matchs, calculait du MMR et tenait un classement, mais ne
gardait trace de RIEN : seul le total courant survivait au match. On ne
pouvait donc ni revoir un match, ni dire ce qu'un joueur valait le mois
dernier, ni savoir à quelle heure les files se remplissent.

Ce module est le seul endroit qui écrit cette mémoire. Un fichier par
serveur — `data/history/<id>.json` — et non un gros fichier commun : un
serveur actif réécrirait sinon l'historique de tous les autres à chaque
match, et un fichier abîmé les emporterait tous.

    {"matches": [...], "queues": [...], "season": 1}

Les deux listes sont BORNÉES (voir les constantes). Un historique qui
grossit sans fin finit par coûter plus cher à relire qu'il ne rapporte, et
personne ne remonte au millième match.

Le PALMARÈS n'est pas ici. `cogs/automation.py` archive déjà le podium de
chaque saison close dans `season.archive`, et en tenir un second
garantirait deux versions de la même histoire. `season` n'est qu'un
compteur, pour étiqueter les matchs.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from json_store import write_json

log = logging.getLogger("bot.history")

HISTORY_DIR = "data/history"

# Ce qu'on garde. 500 matchs, c'est plusieurs mois pour un serveur actif, et
# un fichier qui reste sous le mégaoctet. 2000 ouvertures de file suffisent
# aux statistiques, qui ne regardent de toute façon que les dernières
# semaines.
MAX_MATCHES = 500
MAX_QUEUES = 2000

# Les serveurs déjà lus. Relire le fichier à chaque appel coûterait un accès
# disque par ligne de classement affichée.
_cache: dict[int, dict[str, Any]] = {}


def _path(guild_id: int) -> str:
    return os.path.join(HISTORY_DIR, f"{guild_id}.json")


def _vide() -> dict[str, Any]:
    return {"matches": [], "queues": [], "season": 1, "next_id": 1}


def _lire(guild_id: int) -> dict[str, Any]:
    """Le dossier d'un serveur, lu une fois puis gardé en mémoire."""
    if guild_id in _cache:
        return _cache[guild_id]
    chemin = _path(guild_id)
    donnees = _vide()
    if os.path.exists(chemin):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                brut = json.load(f)
            if isinstance(brut, dict):
                # Clé par clé : un fichier d'une version plus ancienne n'a
                # pas toutes les listes, et il ne doit pas pour autant être
                # jeté en entier.
                for cle in ("matches", "queues"):
                    if isinstance(brut.get(cle), list):
                        donnees[cle] = brut[cle]
                for cle in ("season", "next_id"):
                    if isinstance(brut.get(cle), int):
                        donnees[cle] = max(1, brut[cle])
        except (OSError, ValueError) as e:
            # Mis de côté, jamais écrasé : repartir d'un dossier vide
            # effacerait l'historique à la première écriture.
            secours = f"{chemin}.illisible-{int(time.time())}"
            try:
                os.replace(chemin, secours)
                log.error(f"Historique illisible ({e}) : mis de côté dans {secours}")
            except OSError:
                log.error(f"Historique illisible ({e}), et impossible à mettre de côté")
    _cache[guild_id] = donnees
    return donnees


def _ecrire(guild_id: int) -> None:
    try:
        write_json(_path(guild_id), _cache[guild_id], indent=2, ensure_ascii=False)
    except OSError as e:
        log.error(f"Historique non enregistré pour {guild_id} : {e}")


def _maintenant() -> str:
    """L'heure en UTC, au format ISO. Le panneau la traduit dans le fuseau
    du lecteur ; stocker une heure locale rendrait les statistiques fausses
    dès qu'un organisateur change de pays."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _horodatage(ligne: dict) -> float:
    """L'heure d'une ligne, en secondes. Zéro si elle est illisible — une
    ligne sans date ne doit pas faire tomber tout un relevé."""
    try:
        return datetime.fromisoformat(ligne["at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return 0.0


# ----------------------------------------------------------------------
# Les matchs
# ----------------------------------------------------------------------

def record_match(guild_id: int, *, teams: dict[str, list[int]], winner: str | None,
                 mvp_id: int | None, changes: list[tuple[int, int, int, bool]]) -> dict:
    """Range un match terminé. `changes` est ce que `_close_mvp_vote` fabrique :
    (joueur, MMR après, variation, est MVP).

    Rend la fiche enregistrée — c'est elle que le webhook sortant envoie,
    pour que les deux ne puissent pas décrire le même match autrement.
    """
    dossier = _lire(guild_id)
    gagnants = set(teams.get(winner, [])) if winner else set()
    joueurs = {}
    for uid, valeur, variation, est_mvp in changes:
        joueurs[str(uid)] = {
            "mmr": int(valeur),
            "change": int(variation),
            "mvp": bool(est_mvp),
            # Gagnant : déduit de l'équipe, pas de la variation. Un serveur
            # réglé à 0 point par victoire donnerait sinon « perdu » à tout
            # le monde.
            "won": uid in gagnants,
        }
    fiche = {
        "id": int(dossier["next_id"]),
        "at": _maintenant(),
        "season": dossier["season"],
        "teams": {nom: [str(u) for u in ids] for nom, ids in teams.items()},
        "winner": winner,
        "mvp": str(mvp_id) if mvp_id else None,
        "players": joueurs,
    }
    dossier["next_id"] = fiche["id"] + 1
    dossier["matches"].insert(0, fiche)
    del dossier["matches"][MAX_MATCHES:]
    _ecrire(guild_id)
    return fiche


def matches(guild_id: int, *, limit: int = 25, offset: int = 0,
            player_id: int | None = None, season: int | None = None) -> list[dict]:
    """Les matchs, du plus récent au plus ancien."""
    liste = _lire(guild_id)["matches"]
    if season is not None:
        liste = [m for m in liste if m.get("season") == season]
    if player_id is not None:
        cle = str(player_id)
        liste = [m for m in liste if cle in (m.get("players") or {})]
    return liste[offset:offset + max(1, limit)]


def match_count(guild_id: int) -> int:
    return len(_lire(guild_id)["matches"])


# ----------------------------------------------------------------------
# La fiche d'un joueur
# ----------------------------------------------------------------------

def player_card(guild_id: int, user_id: int, *, courbe: int = 20) -> dict:
    """Ce qu'un joueur a fait sur ce serveur, d'après les matchs gardés.

    Les totaux ne valent que pour l'historique CONSERVÉ : au-delà de
    MAX_MATCHES, les plus vieux sont tombés. `partial` le dit, pour que le
    panneau n'affiche pas un « 412 matchs » qui n'est le total de rien.
    """
    cle = str(user_id)
    tous = _lire(guild_id)["matches"]
    siens = [m for m in tous if cle in (m.get("players") or {})]

    victoires = sum(1 for m in siens if m["players"][cle].get("won"))
    mvp = sum(1 for m in siens if m["players"][cle].get("mvp"))

    # La série en cours : on remonte du plus récent tant que ça gagne.
    serie = 0
    for m in siens:
        if not m["players"][cle].get("won"):
            break
        serie += 1

    # La courbe de MMR, du plus ancien au plus récent : c'est le sens de
    # lecture d'un graphique, et l'inverser ici éviterait au panneau de
    # devoir y penser.
    points = [{"at": m["at"], "mmr": m["players"][cle].get("mmr")}
              for m in reversed(siens[:courbe])]

    # Avec qui il joue le plus souvent : même équipe, même match.
    ensemble: dict[str, int] = {}
    for m in siens:
        for ids in (m.get("teams") or {}).values():
            if cle not in ids:
                continue
            for autre in ids:
                if autre != cle:
                    ensemble[autre] = ensemble.get(autre, 0) + 1
    duos = sorted(ensemble.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "id": cle,
        "matches": len(siens),
        "wins": victoires,
        "losses": len(siens) - victoires,
        "mvp": mvp,
        "streak": serie,
        "curve": points,
        "mates": [{"id": uid, "count": n} for uid, n in duos],
        "partial": len(tous) >= MAX_MATCHES,
    }


# ----------------------------------------------------------------------
# Les files : ce qu'il faut pour les statistiques
# ----------------------------------------------------------------------

def record_queue(guild_id: int, event: str, *, players: int = 0,
                 waited: int | None = None) -> None:
    """Note une ouverture, un lancement ou une annulation de file.

    `waited` est le nombre de SECONDES entre l'ouverture et le lancement.
    Il n'est connu qu'au lancement : à l'ouverture, il vaut None, et les
    statistiques ignorent les lignes qui ne l'ont pas.
    """
    if event not in ("opened", "launched", "cancelled"):
        return
    dossier = _lire(guild_id)
    dossier["queues"].insert(0, {
        "at": _maintenant(),
        "event": event,
        "players": int(players),
        "waited": None if waited is None else max(0, int(waited)),
    })
    del dossier["queues"][MAX_QUEUES:]
    _ecrire(guild_id)


def stats(guild_id: int, *, days: int = 30) -> dict:
    """Le relevé d'activité des `days` derniers jours.

    Tout vient de ce qui est enregistré. Une case sans donnée vaut zéro et
    non une moyenne inventée : un serveur qui n'a rien joué doit voir un
    graphique vide, pas une courbe plate qui ressemble à de l'activité.
    """
    dossier = _lire(guild_id)
    limite = time.time() - days * 86400

    files = [q for q in dossier["queues"] if _horodatage(q) >= limite]
    parties = [m for m in dossier["matches"] if _horodatage(m) >= limite]

    ouvertes = [q for q in files if q["event"] == "opened"]
    lancees = [q for q in files if q["event"] == "launched"]
    annulees = [q for q in files if q["event"] == "cancelled"]

    attentes = [q["waited"] for q in lancees if q.get("waited") is not None]
    moyenne = round(sum(attentes) / len(attentes)) if attentes else None

    # Par jour et par heure. `par_jour` garde une case par jour, trous
    # compris : un graphique qui saute les jours creux ment sur le rythme.
    par_jour: dict[str, int] = {}
    for i in range(days):
        jour = datetime.fromtimestamp(time.time() - i * 86400, timezone.utc).date().isoformat()
        par_jour[jour] = 0
    par_heure = [0] * 24
    for q in lancees:
        horo = _horodatage(q)
        if not horo:
            continue
        quand = datetime.fromtimestamp(horo, timezone.utc)
        jour = quand.date().isoformat()
        if jour in par_jour:
            par_jour[jour] += 1
        par_heure[quand.hour] += 1

    return {
        "days": days,
        "opened": len(ouvertes),
        "launched": len(lancees),
        "cancelled": len(annulees),
        # Le taux d'abandon : des files ouvertes, celles qui n'ont jamais
        # démarré. Sans ouverture, pas de taux — et pas de zéro trompeur.
        "abandonRate": (round(100 * len(annulees) / len(ouvertes)) if ouvertes else None),
        "avgWait": moyenne,
        "matches": len(parties),
        "byDay": [{"day": j, "n": n} for j, n in sorted(par_jour.items())],
        "byHour": par_heure,
    }


# ----------------------------------------------------------------------
# Les saisons
# ----------------------------------------------------------------------

def current_season(guild_id: int) -> int:
    return _lire(guild_id)["season"]


def bump_season(guild_id: int) -> int:
    """Passe à la saison suivante. Rend le nouveau numéro.

    Le PALMARÈS n'est pas ici : `cogs/automation.py` l'archive déjà dans
    `season.archive` depuis toujours, podium compris, et en tenir un second
    garantirait deux versions de la même histoire. Ce compteur ne sert qu'à
    ÉTIQUETER les matchs, pour qu'on puisse demander « les matchs de la
    saison 3 » sans deviner où elle commence.
    """
    dossier = _lire(guild_id)
    dossier["season"] += 1
    _ecrire(guild_id)
    return dossier["season"]


def forget(guild_id: int) -> None:
    """Oublie ce serveur. Appelé par /reset, et par les tests."""
    _cache.pop(guild_id, None)
    try:
        os.remove(_path(guild_id))
    except OSError:
        pass
