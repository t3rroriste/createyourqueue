"""
Essaie « Ouvrir la queue » sur l'API du bot, et dit ce qu'elle répond.
=====================================================================
C'est le seul maillon de la chaîne panneau → bot que rien ne vérifiait.
`verifier_api_bot.py` prouve que le bot répond ; celui-ci prouve qu'il
AGIT — qu'une ouverture demandée de l'extérieur publie bien une annonce.

Ce qu'il ne prouve pas, et il faut le savoir en le lançant : il parle
DIRECTEMENT au bot, avec la clé du site. Il saute donc le relais PHP
(`site/api/index.php`, route `/guilds/{id}/queue/open`) et son garde de
session. Ce relais a été vérifié autrement : sans cookie il répond 401,
et avec un cookie sans « Gérer le serveur » il répond 403. Ce qui reste
hors de portée d'ici, c'est le chemin complet avec une vraie session
Discord — il demande un navigateur connecté, pas un script.

ATTENTION, CE N'EST PAS UN ESSAI À BLANC.
`--ouvrir` publie une vraie annonce dans un vrai salon, devant de vraies
personnes. `--fermer` est pire : elle supprime l'annonce, les salons
d'équipe, révoque les accès et repurge le salon de commande. C'est une
fermeture définitive, pas une pause. D'où trois précautions :

  · sans `--ouvrir` ni `--fermer`, l'outil ne fait que LIRE ;
  · `--guilde` est obligatoire pour agir, jamais deviné ;
  · une queue déjà en cours fait répondre 409 « already_open » au bot,
    donc une partie en train de se jouer ne peut pas être écrasée.

EN AVEUGLE, comme les autres outils de secrets : la clé est lue dans
site/api/secrets.php et n'est jamais affichée, ni en entier ni en partie.

    python outils/essayer_queue.py --lister
    python outils/essayer_queue.py --guilde 123456789012345678
    python outils/essayer_queue.py --guilde 123456789012345678 --ouvrir
    python outils/essayer_queue.py --guilde 123456789012345678 --fermer

Les 409 du bot ne sont pas des pannes : « setup_incomplete »,
« no_config » et « cooldown » veulent dire que la chaîne a fonctionné
jusqu'au bout et que c'est le serveur Discord qui n'est pas prêt. Rien
n'est publié dans ces cas-là.
"""

import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)

SECRETS_PHP = os.path.join(RACINE, "site", "api", "secrets.php")

# Le bot est sur une autre machine, et une queue qui s'ouvre crée des
# salons : dix secondes, pas trois.
DELAI = 10


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
        "User-Agent": "CreateYourQueue (outils/essayer_queue.py)",
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
        # Port fermé, bot éteint, délai dépassé : le relais PHP répond 502
        # BOT_INJOIGNABLE dans ce cas, et c'est la même situation.
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
    print("bot_api_base : " + ("renseignée" if base else "VIDE"))
    print("bot_api_key  : " + ("présente" if cle else "VIDE"))
    if not base or not cle:
        print("\nL'une des deux manque. `relever_cle_bot.py` va chercher la "
              "vraie sur le serveur.", file=sys.stderr)
        return None
    if not cle.isascii():
        print("\nLa clé contient un caractère hors ASCII : elle a été recopiée "
              "depuis un\naffichage qui l'avait abrégée, et un en-tête HTTP ne "
              "peut pas la transporter.", file=sys.stderr)
        return None
    return base, cle


def lister(base: str, cle: str) -> int:
    code, rep = appeler(base, cle, "GET", "/api/guilds")
    if code != 200:
        print(f"\nHTTP {code} — {rep}", file=sys.stderr)
        return 1
    guildes = rep.get("guilds", rep) if isinstance(rep, dict) else rep
    if not isinstance(guildes, list):
        print(f"\nRéponse inattendue : {str(rep)[:200]}", file=sys.stderr)
        return 1
    print(f"\n{len(guildes)} serveur(s) :\n")
    for g in guildes:
        if not isinstance(g, dict):
            print("  " + str(g)[:80])
            continue
        print("  %-24s  %s" % (str(g.get("name", "?"))[:24], g.get("id", "?")))
    print("\nPuis :  python outils/essayer_queue.py --guilde <id>")
    return 0


def montrer(base: str, cle: str, gid: str) -> int:
    """Lecture seule : ce que le bot sait de ce serveur. Rien n'est touché.

    On s'intéresse à deux champs seulement, et c'est délibéré : ce sont
    ceux dont dépend l'ouverture. Sans eux, `--ouvrir` répond 409 et ne
    publie rien — autant le savoir avant d'essayer que l'apprendre en
    POSTant au hasard sur les serveurs de quelqu'un."""
    code, rep = appeler(base, cle, "GET", "/api/guilds/" + gid)
    if code != 200:
        print(f"\nHTTP {code} — {rep}", file=sys.stderr)
        return 1
    if not isinstance(rep, dict):
        print(f"\nRéponse inattendue : {str(rep)[:200]}", file=sys.stderr)
        return 1

    print("\n" + str(rep.get("name") or gid))
    # L'assistant de configuration a-t-il tourné : salons et rôle staff.
    print("  assistant terminé  : "
          + ("oui" if rep.get("setup_complete") else "NON"))
    # Un format de queue enregistré. Vide, le bot refuse plutôt que
    # d'inventer un format par défaut.
    queue = rep.get("queue")
    garnie = bool(queue) if not isinstance(queue, dict) else bool(
        [v for v in queue.values() if v not in (None, "", [], {})])
    print("  queue configurée   : " + ("oui" if garnie else "NON"))

    print("\nRien n'a été touché.")
    if rep.get("setup_complete") and garnie:
        print("Ce serveur peut ouvrir une queue :")
        print(f"  python outils/essayer_queue.py --guilde {gid} --ouvrir")
    else:
        print("`--ouvrir` répondrait 409 ici, sans rien publier.")
    return 0


def agir(base: str, cle: str, gid: str, geste: str) -> int:
    # Le bot attend un identifiant Discord, et retombe sur lui-même si le
    # membre est introuvable sur le serveur. On ne lui en donne donc pas :
    # une queue d'essai doit être signée par le bot, pas par quelqu'un qui
    # n'a rien demandé.
    champ = "openedBy" if geste == "open" else "closedBy"
    code, rep = appeler(base, cle, "POST",
                        f"/api/guilds/{gid}/queue/{geste}", {champ: {}})
    print(f"\nHTTP {code}")
    print(json.dumps(rep, ensure_ascii=False, indent=2))

    if code == 0:
        print("\nRien n'a répondu. Le relais PHP dirait BOT_INJOIGNABLE.",
              file=sys.stderr)
        return 1
    if code in (200, 201):
        if geste == "open":
            print("\nUne annonce a été publiée. Pour la retirer :")
            print(f"  python outils/essayer_queue.py --guilde {gid} --fermer")
        return 0
    if code == 409:
        print("\nLa chaîne a fonctionné jusqu'au bout : c'est le bot qui "
              "refuse, et il dit\npourquoi ci-dessus. Rien n'a été publié.")
        return 0
    if code in (401, 403):
        print("\nLa clé du site n'est pas celle du bot. "
              "`relever_cle_bot.py` les réaligne.", file=sys.stderr)
        return 1
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Essaie l'ouverture et la fermeture de queue sur l'API "
                    "du bot.")
    parser.add_argument("--lister", action="store_true",
                        help="les serveurs que le bot voit (lecture seule)")
    parser.add_argument("--guilde", help="l'identifiant du serveur Discord")
    parser.add_argument("--ouvrir", action="store_true",
                        help="PUBLIE une annonce dans un vrai salon")
    parser.add_argument("--fermer", action="store_true",
                        help="SUPPRIME l'annonce et les salons d'équipe")
    args = parser.parse_args()

    if args.ouvrir and args.fermer:
        print("--ouvrir et --fermer dans le même appel : choisis.",
              file=sys.stderr)
        return 2
    if (args.ouvrir or args.fermer) and not args.guilde:
        print("--guilde est obligatoire pour agir. Un identifiant ne se "
              "devine pas : une\nannonce part dans un vrai salon.",
              file=sys.stderr)
        return 2
    if not args.lister and not args.guilde:
        parser.print_help()
        return 2

    charge = charger()
    if charge is None:
        return 1
    base, cle = charge

    if args.lister:
        return lister(base, cle)
    if args.ouvrir:
        return agir(base, cle, args.guilde, "open")
    if args.fermer:
        return agir(base, cle, args.guilde, "close")
    return montrer(base, cle, args.guilde)


if __name__ == "__main__":
    raise SystemExit(main())
