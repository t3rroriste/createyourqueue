"""
Dépose etat.secrets.php sur le sous-domaine d'état.
===================================================
La page d'état interroge le bot côté serveur, et il lui faut pour cela
l'adresse et la clé de l'API du bot — les deux mêmes valeurs que le panneau
garde dans `site/api/secrets.php`. Ce script les recopie d'un fichier à
l'autre et dépose le résultat à la racine de status.cyqbot.eu.

EN AVEUGLE, et c'est tout l'objet de ce fichier. Les valeurs ne sont jamais
affichées : il n'imprime que « trouvée » ou « VIDE ». Elles ne passent ni
par un terminal, ni par le dépôt — `etat.secrets.php` est dans `.gitignore`,
comme `api/secrets.php` d'où elles viennent.

Pourquoi un script et pas une ligne du manifeste : `etat.secrets.php` ne
doit JAMAIS pouvoir partir — ni être écrasé — par une publication
ordinaire. `publier_site.py` l'ignore, et c'est volontaire. Le déposer est
un geste à part, qu'on refait seulement quand la clé du bot change.

    python outils/deposer_secrets_etat.py            # écrit et dépose
    python outils/deposer_secrets_etat.py --essai    # écrit, n'envoie rien

En Python comme le reste de l'outillage : les deux machines l'appellent.
"""

import argparse
import io
import os
import re
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)

sys.path.insert(0, OUTILS_DIR)
import publier_site      # noqa: E402
import secrets_locaux    # noqa: E402

SOURCE = os.path.join(RACINE, "site", "api", "secrets.php")
CIBLE = os.path.join(RACINE, "site", "etat.secrets.php")

# Le modèle de ce qui est déposé. Les commentaires voyagent avec les
# valeurs : dans six mois, on doit retrouver SUR LE SERVEUR l'explication
# de ce qu'on y lit, sans avoir à revenir dans le dépôt.
GABARIT = """<?php
/* Les deux valeurs dont la page d'état a besoin, et rien d'autre.
 *
 * Écrit par outils/deposer_secrets_etat.py, qui les recopie de
 * api/secrets.php. Ce fichier n'est PAS dans la liste d'envoi de
 * publier_site.py : une publication ne peut ni l'écraser, ni l'emporter
 * par erreur. Le modèle versionné est site/etat.secrets.exemple.php.
 *
 * Deux copies de la même valeur, et rien ne les tient alignées tout seul :
 * si la DASHBOARD_API_KEY du bot change, relance ce script.
 */
return [
    // L'API que le bot ouvre (cogs/dashboard_api.py), vue de l'extérieur.
    'bot_api_base' => '%s',

    // La DASHBOARD_API_KEY du bot. Elle part en en-tête X-API-Key, et
    // etat.php ne la rend dans aucune réponse.
    'bot_api_key'  => '%s',
];
"""


def valeur(texte: str, cle: str) -> str:
    """La valeur d'une clé du tableau PHP. Rien n'est imprimé ici, jamais."""
    m = re.search(r"'" + cle + r"'\s*=>\s*'((?:[^'\\]|\\.)*)'", texte)
    return m.group(1) if m else ""


def php(valeur_brute: str) -> str:
    """Une valeur prête à entrer entre apostrophes dans du PHP."""
    return valeur_brute.replace("\\", "\\\\").replace("'", "\\'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dépose etat.secrets.php sur le sous-domaine d'état.")
    parser.add_argument("--essai", action="store_true",
                        help="écrit le fichier localement, n'envoie rien")
    args = parser.parse_args()

    if not os.path.isfile(SOURCE):
        print(f"{os.path.relpath(SOURCE, RACINE)} est absent de ce PC.",
              file=sys.stderr)
        print("C'est lui qui porte les deux valeurs. Sans lui, rien à recopier.",
              file=sys.stderr)
        return 1

    with io.open(SOURCE, encoding="utf-8") as f:
        brut = f.read()
    base = valeur(brut, "bot_api_base")
    cle = valeur(brut, "bot_api_key")

    print("bot_api_base : " + ("trouvée" if base else "VIDE"))
    print("bot_api_key  : " + ("trouvée" if cle else "VIDE"))
    if not base or not cle:
        print("\nL'une des deux manque dans api/secrets.php. Rien n'est écrit ni "
              "envoyé : la\npage d'état continuerait d'afficher « mesure non "
              "configurée », ce qui serait\nexact mais sans intérêt.", file=sys.stderr)
        return 1

    # newline="\n" : un fichier PHP en CRLF fonctionne, mais autant qu'il
    # soit identique des deux machines.
    with io.open(CIBLE, "w", encoding="utf-8", newline="\n") as f:
        f.write(GABARIT % (php(base), php(cle)))
    print(f"\n{os.path.relpath(CIBLE, RACINE)} écrit.")

    if args.essai:
        print("Essai : rien n'a été envoyé.")
        return 0

    conf = publier_site.lire_config()
    if conf is None:
        print("Réglages LWS absents. Lance  cyq amorcer.", file=sys.stderr)
        return 1
    racine = str(conf.get("racine_status", "")).strip().rstrip("/")
    if not racine:
        print("« racine_status » est vide dans lws.json : on ne sait pas où "
              "déposer.\nlws.config.exemple.ps1 explique où trouver le dossier "
              "du sous-domaine.", file=sys.stderr)
        return 1

    mot_de_passe = secrets_locaux.lire("lws")
    if not mot_de_passe:
        print("Aucun mot de passe FTP dans le coffre du système.", file=sys.stderr)
        print("Lance  cyq amorcer  pour l'y enregistrer.", file=sys.stderr)
        return 1

    curl = publier_site.Curl(conf, mot_de_passe)
    cible = "ftp://" + conf["serveur"] + racine + "/etat.secrets.php"
    print(f"envoi vers {cible}")
    code, sortie = curl("--ftp-create-dirs", "--upload-file", CIBLE, cible)
    if code != 0:
        print("ÉCHEC — " + publier_site.explique(code, sortie), file=sys.stderr)
        return 1

    print("déposé.")
    print("\nRecharge https://status.cyqbot.eu — le cache garde la mesure vingt")
    print("secondes, donc clique « Mesurer maintenant » si le verdict n'a pas bougé.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
