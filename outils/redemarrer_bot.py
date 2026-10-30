"""
Redémarre le bot, et vérifie qu'il est bien revenu.
===================================================
Publier les fichiers du bot ne suffit pas : `publier_bot.py` les dépose sur
AdKyNet, mais le processus en cours garde l'ancien code en mémoire jusqu'à ce
qu'on le relance. Pendant longtemps ce dernier geste était à faire à la main
dans le panneau, et c'est précisément celui qu'on oublie — un bot qui tourne
semble à jour.

Le bot se relance LUI-MÊME, par sa propre API (`POST /api/restart`). Le
panneau Pterodactyl a bien une API de puissance, mais elle demanderait une
clé de plus, à créer, à ranger dans les deux coffres et à garder valide,
pour faire ce qu'`os.execv` fait sans rien de neuf.

À LANCER À LA MAIN, ET À REGARDER. La veille ne l'appelle plus : son premier
vrai essai, le 30 octobre 2026, a mis le bot à terre — il a fallu le relancer
depuis le panneau. Le mécanisme a été repris depuis (la relance part d'un fil
système et ne ferme plus la passerelle avant de partir), mais il n'a pas
encore fait ses preuves. La veille se contente donc de rappeler dans son
journal qu'un redémarrage est dû.

UNE QUEUE EN COURS N'EST PAS ÉCRASÉE. Les sessions vivent en mémoire :
relancer pendant une partie perd les équipes, les accès aux salons et le
lien de l'annonce. Le bot répond alors 409, cet outil sort avec le code 2,
et la veille réessaiera au passage suivant. `--force` existe, et il faut
l'écrire.

EN AVEUGLE, comme les autres outils de secrets : l'adresse et la clé sont
lues dans site/api/secrets.php et ne sont jamais affichées, ni en entier ni
en partie.

    python outils/redemarrer_bot.py           # relance, si c'est sans risque
    python outils/redemarrer_bot.py --etat    # lecture seule, ne touche à rien
    python outils/redemarrer_bot.py --force   # relance même pendant une queue

Codes de sortie, parce que la veille les lit :
  0  relancé, et le bot a répondu après
  2  remis à plus tard (une queue est en cours)
  1  échec — y compris « parti et jamais revenu », le seul cas grave
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)

SECRETS_PHP = os.path.join(RACINE, "site", "api", "secrets.php")

# Court pour une lecture, et le redémarrage n'attend pas de réponse longue.
DELAI = 10
# Le temps qu'on laisse au bot pour revenir. Il doit se reconnecter à Discord
# et rouvrir son port. Trente secondes au premier essai, le 30 octobre 2026 :
# trop court pour conclure, et l'outil a crié « pas revenu » sur un bot qui
# était peut-être encore en train de se connecter. Une minute, maintenant —
# une attente un peu longue vaut mieux qu'une fausse alerte sur un bot en
# production.
RETOUR_MAX = 60
RETOUR_PAS = 3


def valeur(texte: str, cle: str) -> str:
    """La valeur d'une clé du tableau PHP. Rien n'est imprimé ici, jamais."""
    m = re.search(r"'" + re.escape(cle) + r"'\s*=>\s*'((?:[^'\\]|\\.)*)'", texte)
    return m.group(1) if m else ""


def appeler(base: str, cle: str, methode: str, chemin: str, corps=None):
    """Renvoie (code, données). code 0 si rien n'a répondu."""
    donnees = None
    entetes = {
        "Accept": "application/json",
        "X-API-Key": cle,
        # Le bot journalise l'origine de ses appels : autant qu'elle se
        # reconnaisse dans ses logs, et ne passe pas pour le site.
        "User-Agent": "CreateYourQueue (outils/redemarrer_bot.py)",
    }
    if corps is not None:
        donnees = json.dumps(corps).encode("utf-8")
        entetes["Content-Type"] = "application/json"

    req = urllib.request.Request(base + chemin, data=donnees,
                                 headers=entetes, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=DELAI) as rep:
            brut = rep.read().decode("utf-8", "replace")
            return rep.status, json.loads(brut) if brut.strip() else {}
    except urllib.error.HTTPError as e:
        brut = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(brut) if brut.strip() else {}
        except ValueError:
            return e.code, {"corps": brut[:200]}
    except Exception as e:
        return 0, {"erreur": str(e)}


def charger():
    """(base, clé) ou None, avec l'explication déjà imprimée."""
    if not os.path.isfile(SECRETS_PHP):
        print("site/api/secrets.php est absent de ce PC — c'est lui qui porte "
              "l'adresse et la clé.", file=sys.stderr)
        return None
    with io.open(SECRETS_PHP, encoding="utf-8") as f:
        brut = f.read()
    base = valeur(brut, "bot_api_base").rstrip("/")
    cle = valeur(brut, "bot_api_key")
    if not base or not cle:
        print("bot_api_base ou bot_api_key est vide dans site/api/secrets.php. "
              "`relever_cle_bot.py`\nva chercher la vraie sur le serveur.",
              file=sys.stderr)
        return None
    if not cle.isascii():
        print("La clé contient un caractère hors ASCII : elle a été recopiée "
              "depuis un\naffichage qui l'avait abrégée, et un en-tête HTTP ne "
              "peut pas la transporter.", file=sys.stderr)
        return None
    return base, cle


def sante(base: str, cle: str):
    """L'état du bot, ou None s'il ne répond pas."""
    code, rep = appeler(base, cle, "GET", "/api/health")
    return rep if code == 200 and isinstance(rep, dict) else None


def montrer(etat: dict) -> None:
    print("  bot                : " + str(etat.get("bot") or "?"))
    print("  serveurs           : " + str(etat.get("guilds", "?")))
    print("  queues en cours    : " + str(etat.get("active_queues", "?")))
    print("  en route depuis    : " + str(etat.get("uptime_seconds", "?")) + " s")


def attendre_retour(base: str, cle: str, avant: int) -> dict | None:
    """Le bot revenu, ou None s'il ne revient pas.

    On ne se contente pas d'une réponse : on exige un `uptime_seconds` PLUS
    PETIT qu'avant. Sans cette comparaison, l'ancien processus encore en
    train de se fermer répondrait « ok » et on annoncerait un redémarrage
    qui n'a pas eu lieu."""
    limite = time.time() + RETOUR_MAX
    while time.time() < limite:
        time.sleep(RETOUR_PAS)
        etat = sante(base, cle)
        if etat is not None and int(etat.get("uptime_seconds", avant)) < avant:
            return etat
    return None


def redemarrer(base: str, cle: str, force: bool) -> int:
    avant = sante(base, cle)
    if avant is None:
        print("Le bot ne répond pas : il n'y a rien à redémarrer d'ici.\n"
              "  Port fermé, bot éteint, ou clé désaccordée — "
              "`verifier_api_bot.py` tranche.", file=sys.stderr)
        return 1

    print("Avant :")
    montrer(avant)
    uptime_avant = int(avant.get("uptime_seconds", 0))

    code, rep = appeler(base, cle, "POST", "/api/restart",
                        {"force": True} if force else {})

    if code == 409 and isinstance(rep, dict) and rep.get("error") == "queues_open":
        combien = rep.get("active_queues", "?")
        print(f"\nRemis à plus tard : {combien} queue(s) en cours. Relancer "
              "maintenant perdrait\nles équipes et les accès déjà distribués. "
              "La veille réessaiera.")
        return 2

    if code == 0:
        # La réponse part avant execv, exprès : une connexion coupée ici
        # veut dire que l'appel n'a pas abouti, pas que le bot est parti.
        print(f"\nAucune réponse à la demande de redémarrage — {rep}",
              file=sys.stderr)
        return 1
    if code == 404:
        print("\nHTTP 404 : ce bot tourne encore sur une version d'avant la "
              "route /api/restart.\n  Publie bot/cogs/dashboard_api.py, puis "
              "redémarre-le une dernière fois à la main.", file=sys.stderr)
        return 1
    if code != 200:
        print(f"\nHTTP {code} — {json.dumps(rep, ensure_ascii=False)}",
              file=sys.stderr)
        return 1

    print("\nRedémarrage accepté. On attend son retour.")
    apres = attendre_retour(base, cle, uptime_avant)
    if apres is None:
        print(f"\nLE BOT N'EST PAS REVENU en {RETOUR_MAX} s.\n"
              "  C'est le cas grave : le code publié ne démarre peut-être pas. "
              "Va voir la\n  console du panneau AdKyNet — elle porte la trace "
              "de l'erreur.", file=sys.stderr)
        return 1

    print("Après :")
    montrer(apres)
    print("\nLe bot tourne sur le code publié.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Redémarre le bot par sa propre API, et vérifie son retour.")
    parser.add_argument("--etat", action="store_true",
                        help="montre l'état du bot, sans rien redémarrer")
    parser.add_argument("--force", action="store_true",
                        help="redémarre MÊME si une queue est en cours")
    args = parser.parse_args()

    charge = charger()
    if charge is None:
        return 1
    base, cle = charge

    if args.etat:
        etat = sante(base, cle)
        if etat is None:
            print("Le bot ne répond pas.", file=sys.stderr)
            return 1
        montrer(etat)
        print("\nRien n'a été touché.")
        return 0

    return redemarrer(base, cle, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
