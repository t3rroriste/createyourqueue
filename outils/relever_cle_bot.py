"""
Relève la clé d'API sur le serveur du bot, et aligne le site dessus.
====================================================================
Le `.env` du serveur est la SOURCE DE VÉRITÉ, et c'est voulu :
`publier_bot.py` ne l'envoie jamais, pour qu'un PC ne puisse pas écraser
la configuration d'un bot qui tourne. La conséquence, c'est que le `.env`
d'ici peut très bien ne rien contenir pendant que celui de là-bas marche
— c'est exactement ce qui s'est passé, et ce qui a fait croire pendant
une heure que l'API du bot n'avait jamais été allumée. Elle l'était.

Ce script va donc chercher la valeur là où elle fait autorité, et aligne
les deux fichiers qui doivent la connaître :

  bot/.env              pour pouvoir lancer le bot ici
  site/api/secrets.php  pour que le panneau et la page d'état le joignent

LE PORT NE SE LIT PAS DANS LE .env. Pterodactyl n'expose qu'une
allocation, et le bot le dit lui-même quand `DASHBOARD_API_PORT` n'est
pas celle-là :

    DASHBOARD_API_PORT=8080 est ignoré : l'hébergeur n'expose que
    l'allocation 25209.

Ce script lisait pourtant `DASHBOARD_API_PORT`, et écrivait donc dans
`bot_api_base` un port sur lequel le bot n'écoute pas. Le 6 novembre
2026, le site appelait le 25117 — une allocation périmée — pendant que
le bot répondait sur le 25209 : API allumée, clé juste, panneau web
hors ligne, et `cyq redemarrer` qui échouait depuis une semaine en
disant « port fermé, bot éteint, ou clé désaccordée ».

Le port se lit maintenant dans `data/api-adresse.txt`, que le cog écrit
à chaque démarrage avec le port qu'il écoute POUR DE VRAI. Le `.env` ne
sert plus que de recours, quand ce fichier n'existe pas encore.

Rien n'est écrit sur le serveur, rien n'y est redémarré. C'est l'inverse
de `activer_api_bot.py`, qui tire une clé neuve : celui-ci ne décide de
rien, il recopie.

EN AVEUGLE, comme les autres : la clé n'est jamais affichée.

    python outils/relever_cle_bot.py

Il faut le mot de passe SFTP, dans le coffre du système ou dans
ADKYNET_SFTP_PASSWORD — le même que pour publier le bot.
"""

import io
import os
import re
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)

sys.path.insert(0, OUTILS_DIR)
import adkynet  # noqa: E402
import activer_api_bot as activer  # noqa: E402

ENV_LOCAL = os.path.join(RACINE, "bot", ".env")
SECRETS_PHP = os.path.join(RACINE, "site", "api", "secrets.php")

# `bot.py` est à la racine du serveur, pas dans un sous-dossier : le .env
# est donc à la racine lui aussi. C'est la même règle que publier_bot.py.
ENV_DISTANT = "/.env"

# Ce que le cog dashboard_api écrit à chaque démarrage : l'état de l'API et
# le port qu'elle écoute vraiment. `publier_bot.py` n'emporte jamais
# `data/`, donc ce fichier n'est écrasé par aucune publication.
ADRESSE_DISTANTE = "/data/api-adresse.txt"


def main() -> int:
    if adkynet.password() is None:
        print("Aucun mot de passe SFTP — ni dans le coffre, ni dans "
              "ADKYNET_SFTP_PASSWORD.", file=sys.stderr)
        print("C'est le même que pour  python outils/publier_bot.py.",
              file=sys.stderr)
        return 1

    lien = adkynet.connect()
    if lien is None:
        print(f"Connexion impossible à {adkynet.HOST}:{adkynet.PORT}.",
              file=sys.stderr)
        return 1
    transport, sftp = lien
    try:
        with sftp.open(ENV_DISTANT, "r") as f:
            distant = f.read().decode("utf-8", "replace")
        # Absent tant que le bot n'a pas redémarré sur un code qui l'écrit :
        # c'est un confort de diagnostic, pas une raison d'échouer.
        try:
            with sftp.open(ADRESSE_DISTANTE, "r") as f:
                adresse = f.read().decode("utf-8", "replace")
        except IOError:
            adresse = ""
    except IOError as e:
        print(f"Impossible de lire {ENV_DISTANT} sur le serveur — {e}",
              file=sys.stderr)
        return 1
    finally:
        sftp.close()
        transport.close()

    def champ(nom: str) -> str:
        m = re.search(r"^" + nom + r"=(.*)$", distant, re.M)
        return m.group(1).strip() if m else ""

    def ligne_adresse(nom: str) -> str:
        """Une ligne de `api-adresse.txt`, qui est en « nom   valeur »."""
        m = re.search(r"^" + nom + r"\s+(.*)$", adresse, re.M)
        return m.group(1).strip() if m else ""

    cle = champ("DASHBOARD_API_KEY")
    port_env = champ("DASHBOARD_API_PORT") or "8080"

    # Dans l'ordre de ce qui fait autorité : ce que le bot écoute, puis
    # l'allocation que l'hébergeur lui donne, puis le .env en dernier
    # recours — celui-là, le bot l'ignore dès qu'il ne correspond pas.
    ecoute = ligne_adresse("ecoute")
    m = re.search(r":(\d+)$", ecoute)
    port = m.group(1) if m else (ligne_adresse("SERVER_PORT") or port_env)
    doù = ("le port écouté" if m else
           "l'allocation de l'hébergeur" if ligne_adresse("SERVER_PORT")
           else "le .env, à défaut de mieux")

    print("sur le serveur :")
    print("  DASHBOARD_API_KEY  = " + ("présente" if cle else
                                       "VIDE — le bot n'ouvre aucun port"))
    if adresse:
        print("  API                = " + (ligne_adresse("etat") or "?")
              + ", depuis " + (ligne_adresse("depuis") or "?"))
        print("  port               = " + port + "  (" + doù + ")")
        if port != port_env:
            # Ce n'est pas une faute : le bot ignore le .env quand
            # l'hébergeur ne lui donne pas ce port-là. On le dit pour que
            # personne ne « corrige » le .env en croyant régler quelque chose.
            print("  DASHBOARD_API_PORT = " + port_env
                  + "  (ignoré par le bot — normal)")
    else:
        print("  port               = " + port + "  (" + doù + ")")
        print("\n  " + ADRESSE_DISTANTE + " est absent du serveur : le bot "
              "tourne sur un code\n  antérieur à cette trace. Le port "
              "ci-dessus peut être faux — c'est\n  précisément ce que ce "
              "fichier est là pour éviter.")
    if not cle:
        print("\nIl n'y a rien à relever. C'est  activer_api_bot.py  qu'il "
              "faut, pour en\nposer une — mais il faudra alors la reporter "
              "là-bas à la main, et redémarrer.", file=sys.stderr)
        return 1
    if not cle.isascii():
        print("\nLa clé du serveur contient un caractère hors ASCII. Elle ne "
              "peut pas voyager\ndans un en-tête HTTP : c'est elle qu'il faut "
              "corriger, sur le serveur.", file=sys.stderr)
        return 1

    env = activer.lire(ENV_LOCAL)
    env = activer.poser_env(env, "DASHBOARD_API_KEY", cle)
    # `port_env` et non `port` : le .env dit le port DEMANDÉ, et le serveur
    # a le droit d'en imposer un autre. Y recopier l'allocation ferait
    # croire que le bot la réclame, et le prochain qui lirait les deux
    # fichiers n'aurait plus aucun moyen de voir la différence.
    env = activer.poser_env(env, "DASHBOARD_API_PORT", port_env)
    env = activer.poser_env(env, "DASHBOARD_API_HOST", "0.0.0.0")

    php = activer.lire(SECRETS_PHP)
    php, ok_cle = activer.poser_php(php, "bot_api_key", cle)
    php, ok_base = activer.poser_php(
        php, "bot_api_base", "http://" + adkynet.HOST + ":" + port)
    if not (ok_cle and ok_base):
        print("bot_api_key ou bot_api_base est introuvable dans "
              "site/api/secrets.php.\nRien n'a été écrit.", file=sys.stderr)
        return 1

    activer.ecrire(ENV_LOCAL, env)
    activer.ecrire(SECRETS_PHP, php)
    print("\nbot/.env et site/api/secrets.php portent maintenant la valeur du "
          "serveur.")
    print("""
Rien n'a été touché sur le serveur, et le bot n'a pas besoin d'être
redémarré : c'est le site qui était désaccordé, pas lui.

  1. python outils/verifier_api_bot.py
     doit répondre « HTTP 200 » et non plus 401 ;
  2. déposer site/api/secrets.php à la racine du panneau par FTP, à la
     main — il n'est dans aucune liste d'envoi ;
  3. python outils/deposer_secrets.py
     pour porter la même clé sur les deux hôtes.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
