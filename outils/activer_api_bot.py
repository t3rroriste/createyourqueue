"""
Allume l'API que le bot ouvre pour le site.
===========================================
Le bot n'ouvre aucun port tant que `DASHBOARD_API_KEY` est vide dans son
`.env` — c'est écrit dans `.env.example`, et c'est une bonne chose : une
API sans clé serait ouverte à tout le monde. Mais tant qu'elle est vide,
le bouton « Ouvrir la queue » du panneau et la page d'état n'ont rien à
joindre, et le disent chacun à leur manière.

Ce script allume la liaison des DEUX côtés à la fois, avec la MÊME clé :

  bot/.env             DASHBOARD_API_KEY, DASHBOARD_API_PORT
  site/api/secrets.php bot_api_key, bot_api_base

C'est tout l'intérêt de le faire ici plutôt qu'à la main. Ces deux
fichiers portent deux copies de la même valeur, rien ne les tient
alignées, et c'est exactement par là que la liaison a cassé : une clé
recopiée depuis un affichage qui l'avait abrégée, et une adresse sans
port. Une valeur écrite deux fois par la même commande ne peut pas
diverger.

EN AVEUGLE, comme les autres outils de secrets : la clé est tirée au
hasard et écrite dans les deux fichiers sans jamais être affichée. Elle
n'apparaît nulle part ailleurs — ni dans un terminal, ni dans le dépôt,
les deux fichiers étant dans `.gitignore`.

    python outils/activer_api_bot.py               # montre, n'écrit rien
    python outils/activer_api_bot.py --port 25117  # allume

L'hôte n'est pas demandé : `outils/adkynet.py` le connaît, c'est la
machine du SFTP et c'est la même. Le port, lui, ne se devine pas — c'est
l'allocation réseau de ton serveur, dans le panneau AdKyNet
(Pterodactyl), onglet Network. Elle doit être OUVERTE, sinon le bot
écoutera derrière une porte fermée.

Ensuite, dans l'ordre : redémarrer le bot, vérifier avec
`verifier_api_bot.py`, déposer `site/api/secrets.php` sur le panneau par
FTP, et lancer `deposer_secrets_etat.py` pour le sous-domaine d'état.
"""

import argparse
import io
import os
import re
import secrets
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)

sys.path.insert(0, OUTILS_DIR)
import adkynet  # noqa: E402

ENV = os.path.join(RACINE, "bot", ".env")
SECRETS_PHP = os.path.join(RACINE, "site", "api", "secrets.php")

# 48 octets en base64url : 64 caractères, tous ASCII, aucun qui demande
# d'être échappé dans un .env, dans du PHP ou dans un en-tête HTTP. Cette
# dernière contrainte n'est pas théorique — c'est un « … » dans un en-tête
# qui a fait échouer la liaison sans un mot d'explication.
LONGUEUR = 48


def lire(chemin: str) -> str:
    with io.open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


def ecrire(chemin: str, texte: str) -> None:
    with io.open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write(texte)


def poser_env(texte: str, cle: str, valeur: str) -> str:
    """Remplace une ligne du .env, ou l'ajoute si elle manque. Le reste du
    fichier n'est pas touché : il porte les jetons du bot."""
    motif = re.compile(r"^(" + re.escape(cle) + r")=.*$", re.M)
    if motif.search(texte):
        return motif.sub(lambda m: m.group(1) + "=" + valeur, texte, count=1)
    saut = "\r\n" if "\r\n" in texte else "\n"
    if texte and not texte.endswith(("\n", "\r")):
        texte += saut
    return texte + cle + "=" + valeur + saut


def poser_php(texte: str, cle: str, valeur: str) -> tuple[str, bool]:
    """Remplace la valeur d'une clé du tableau PHP, sans toucher au reste —
    les commentaires de ce fichier valent mieux que sa syntaxe."""
    motif = re.compile(r"('" + re.escape(cle) + r"'\s*=>\s*')(?:[^'\\]|\\.)*(')")
    echappee = valeur.replace("\\", "\\\\").replace("'", "\\'")
    neuf, n = motif.subn(lambda m: m.group(1) + echappee + m.group(2),
                         texte, count=1)
    return neuf, n == 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Allume l'API du bot, des deux côtés, avec la même clé.")
    # L'hôte n'est pas demandé : adkynet.py le connaît depuis toujours,
    # c'est la machine du SFTP et c'est la même. L'option reste là pour le
    # jour où le bot déménagerait.
    parser.add_argument("--hote", default=adkynet.HOST,
                        help="l'hôte du bot vu de l'extérieur, sans http:// "
                             "(défaut : %(default)s)")
    parser.add_argument("--port", type=int,
                        help="le port de l'allocation ouverte du serveur ; "
                             "sans lui, l'outil montre ce qui est configuré "
                             "et ne touche à rien")
    parser.add_argument("--https", action="store_true",
                        help="le bot est derrière un proxy TLS (rare)")
    args = parser.parse_args()

    if not os.path.isfile(ENV):
        print("bot/.env est absent de ce PC.", file=sys.stderr)
        return 1
    if not os.path.isfile(SECRETS_PHP):
        print("site/api/secrets.php est absent de ce PC.", file=sys.stderr)
        return 1
    if args.port is None:
        # Lecture seule : on dit ce qui est en place, sans rien écrire.
        # Un port n'est pas un secret — c'est un numéro que le premier
        # scan venu trouverait. De la clé, on ne dit que si elle est
        # vide, parce que c'est la seule chose qui nous intéresse ici.
        env = lire(ENV)
        m = re.search(r"^DASHBOARD_API_PORT=(.*)$", env, re.M)
        port = (m.group(1).strip() if m else "")
        m = re.search(r"^DASHBOARD_API_KEY=(.*)$", env, re.M)
        cle_vide = not (m and m.group(1).strip())
        print("bot/.env :")
        print("  DASHBOARD_API_PORT = " + (port or "absent"))
        print("  DASHBOARD_API_KEY  = "
              + ("VIDE — le bot n'ouvre aucun port" if cle_vide
                 else "renseignée"))
        print("  hôte connu du dépôt : " + args.hote
              + "   (outils/adkynet.py)")
        print(
            """
Rien n'a été écrit. Si ce port est bien l'allocation OUVERTE de ton
serveur — panneau AdKyNet, onglet Network — relance avec :

  python outils/activer_api_bot.py --port %s

Sinon, mets le bon numéro à la place. C'est la seule valeur que ce
dépôt ne peut pas connaître.""" % (port or "LE_PORT"))
        return 0

    if not 1 <= args.port <= 65535:
        print("Le port doit être entre 1 et 65535.", file=sys.stderr)
        return 1
    if "/" in args.hote or "://" in args.hote:
        print("L'hôte s'écrit sans protocole et sans chemin : « node2.adky.net »,"
              "\npas « http://node2.adky.net/ ».", file=sys.stderr)
        return 1

    base = ("https://" if args.https else "http://") + args.hote + ":" + str(args.port)
    cle = secrets.token_urlsafe(LONGUEUR)

    env = lire(ENV)
    env = poser_env(env, "DASHBOARD_API_KEY", cle)
    env = poser_env(env, "DASHBOARD_API_PORT", str(args.port))
    # HOST reste 0.0.0.0 : le bot doit écouter sur toutes les interfaces du
    # conteneur, sinon rien ne lui parle de l'extérieur.
    env = poser_env(env, "DASHBOARD_API_HOST", "0.0.0.0")

    php = lire(SECRETS_PHP)
    php, ok_cle = poser_php(php, "bot_api_key", cle)
    php, ok_base = poser_php(php, "bot_api_base", base)
    if not ok_cle or not ok_base:
        manquant = []
        if not ok_cle:
            manquant.append("bot_api_key")
        if not ok_base:
            manquant.append("bot_api_base")
        print("Ces clés sont introuvables dans site/api/secrets.php : "
              + ", ".join(manquant), file=sys.stderr)
        print("Rien n'a été écrit. Ajoute-les d'après secrets.exemple.php, "
              "puis relance.", file=sys.stderr)
        return 1

    ecrire(ENV, env)
    ecrire(SECRETS_PHP, php)

    print("clé tirée au hasard (%d caractères, ASCII) et écrite dans les deux "
          "fichiers." % len(cle))
    print("bot/.env             : DASHBOARD_API_KEY, _PORT=%d, _HOST=0.0.0.0"
          % args.port)
    print("site/api/secrets.php : bot_api_key, bot_api_base=%s" % base)
    print("""
Il reste quatre gestes, dans cet ordre :

  1. REPORTER LES TROIS LIGNES sur le serveur. Ouvre bot/.env ici, copie
     les lignes DASHBOARD_API_KEY, _HOST et _PORT, et colle-les dans le
     .env du serveur — panneau AdKyNet, gestionnaire de fichiers. Une
     publication ne les y portera pas : publier_bot.py exclut .env, pour
     que le fichier du serveur ne puisse jamais être écrasé depuis un
     PC. Puis redémarre le bot : tant qu'il tourne, il garde l'ancienne
     valeur, c'est-à-dire aucune, et n'ouvre aucun port ;
  2. python outils/verifier_api_bot.py
     doit répondre « HTTP 200 » et « tous présents » ;
  3. déposer site/api/secrets.php à la racine du panneau par FTP, à la
     main : il n'est dans aucune liste d'envoi, pour la même raison ;
  4. python outils/deposer_secrets_etat.py
     pour porter la même clé sur le sous-domaine d'état.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
