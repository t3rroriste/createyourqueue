"""
Est-ce que l'API du bot répond, et à qui ?
==========================================
La page d'état dit « le bot ne répond pas » sans jamais dire pourquoi :
c'est voulu, un message de panne détaillé sur une page publique est une
carte du réseau. Ce script est l'autre moitié — le détail, pour toi, sur
ta machine.

Il appelle `/api/health` depuis CE PC, avec l'adresse et la clé lues dans
`site/api/secrets.php`. La comparaison avec ce qu'affiche
https://status.cyqbot.eu tranche la question :

  répond ici, pas depuis LWS  -> l'hébergeur bloque les sorties sur ce
                                 port. Le bouton « Ouvrir la queue » du
                                 panneau est logé à la même enseigne.
  ne répond nulle part        -> le bot est arrêté, ou son API n'écoute
                                 pas (DASHBOARD_API_KEY vide dans .env
                                 l'éteint complètement).
  répond 401 ou 403           -> la clé ne correspond pas.

EN AVEUGLE, comme deposer_secrets_etat.py : l'adresse et la clé ne sont
jamais affichées. De l'adresse, il ne dit que sa FORME — protocole, et
port présent ou non — parce que c'est là que se nichent les fautes de
frappe, et que ça ne désigne aucune machine.

    python outils/verifier_api_bot.py
"""

import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
SOURCE = os.path.join(RACINE, "site", "api", "secrets.php")

# Au-delà, on considère que ça ne répond pas. Le même délai que etat.php,
# pour que les deux mesures soient comparables.
DELAI = 4

# Ce que la page d'état attend de /api/health. Un champ absent veut dire
# que le bot tourne sur l'ancien code et n'a pas été redémarré.
ATTENDUS = ("status", "guilds", "latency_ms", "active_queues", "uptime_seconds")


def valeur(texte: str, cle: str) -> str:
    """La valeur d'une clé du tableau PHP. Rien n'est imprimé ici, jamais."""
    m = re.search(r"'" + cle + r"'\s*=>\s*'((?:[^'\\]|\\.)*)'", texte)
    return m.group(1) if m else ""


def forme(base: str) -> str:
    """La forme de l'adresse, sans l'adresse. Les fautes de frappe vivent
    là : protocole oublié, port manquant, barre oblique en trop."""
    m = re.match(r"^(https?)://([^/:]+)(:(\d+))?(/.*)?$", base)
    if not m:
        return "MALFORMÉE — ni http:// ni https:// au début, ou vide après"
    bouts = ["protocole " + m.group(1)]
    bouts.append("port " + m.group(4) if m.group(4) else "SANS PORT")
    if m.group(5) and m.group(5) != "/":
        bouts.append("un chemin est collé à la fin (il ne devrait pas y en avoir)")
    return ", ".join(bouts)


def main() -> int:
    if not os.path.isfile(SOURCE):
        print(f"{os.path.relpath(SOURCE, RACINE)} est absent de ce PC.",
              file=sys.stderr)
        return 1

    with io.open(SOURCE, encoding="utf-8") as f:
        brut = f.read()
    base = valeur(brut, "bot_api_base").rstrip("/")
    cle = valeur(brut, "bot_api_key")

    if not base:
        print("bot_api_base est VIDE dans api/secrets.php : il n'y a rien à "
              "appeler.\nC'est déjà l'explication.", file=sys.stderr)
        return 1
    print("adresse : " + forme(base))
    print("clé     : " + ("présente" if cle else "VIDE — l'API du bot la "
                          "réclame, l'appel sera refusé"))
    print()

    requete = urllib.request.Request(
        base + "/api/health",
        headers={"Accept": "application/json", "X-API-Key": cle,
                 "User-Agent": "CreateYourQueue (verification locale)"},
    )
    try:
        with urllib.request.urlopen(requete, timeout=DELAI) as rep:
            code = rep.status
            corps = rep.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # Une réponse, mais pas celle qu'on voulait. C'est déjà une bonne
        # nouvelle : la liaison existe.
        print(f"Le bot a répondu HTTP {e.code}.")
        if e.code in (401, 403):
            print("\nIl est là et il écoute, mais il refuse la clé. La "
                  "DASHBOARD_API_KEY du\n.env du bot et le bot_api_key de "
                  "api/secrets.php ne sont pas la même.")
        return 1
    except urllib.error.URLError as e:
        print(f"Aucune réponse depuis ce PC — {e.reason}")
        print("\nSi la page d'état dit la même chose, le bot est arrêté ou son "
              "API n'écoute\npas. Un DASHBOARD_API_KEY vide dans bot/.env "
              "l'éteint entièrement : le bot\ndémarre, mais sans ouvrir de "
              "port.")
        return 1
    except OSError as e:
        print(f"Appel impossible — {e}")
        return 1

    print(f"Le bot a répondu HTTP {code} depuis ce PC.")
    try:
        donnees = json.loads(corps)
    except ValueError:
        print("Mais sa réponse n'est pas du JSON. Quelque chose d'autre écoute "
              "sur ce port.")
        return 1

    manquants = [c for c in ATTENDUS if c not in donnees]
    print("champs attendus : " + ("tous présents" if not manquants
                                  else "il manque " + ", ".join(manquants)))
    if manquants:
        print("\nLe bot tourne sur l'ancien code : /api/health n'a pas encore "
              "les champs\najoutés pour la page d'état. Republie-le et "
              "redémarre-le.")
    print("\nSi https://status.cyqbot.eu dit malgré tout « le bot ne répond "
          "pas », alors\nla liaison existe mais pas depuis LWS : c'est le "
          "pare-feu sortant de\nl'hébergeur. Le journal d'erreurs du serveur, "
          "dans le panneau LWS, porte la\nligne « cyq-etat » avec le numéro "
          "d'erreur de curl.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
