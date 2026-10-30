"""
Dépose les fichiers de secrets du site, qu'aucune publication n'emporte.
========================================================================
Deux fichiers vivent chez LWS sans jamais figurer dans une liste d'envoi,
et c'est délibéré : une publication ordinaire ne doit pouvoir ni les
écraser, ni les emporter par erreur.

  panneau   site/api/secrets.php     -> racine de dashboard.cyqbot.eu
  état      site/etat.secrets.php    -> racine de status.cyqbot.eu

Le second n'existe pas dans le dépôt : il est ÉCRIT ICI, à partir des deux
valeurs du premier — `bot_api_base` et `bot_api_key`. La page d'état n'a
besoin que de celles-là, et lui confier le CLIENT_SECRET Discord ou le
jeton du bot serait les recopier sur un troisième serveur sans raison.

C'est aussi ce qui garantit que les deux hôtes parlent au bot avec la
MÊME clé. Une clé recopiée à la main depuis un affichage qui l'avait
abrégée a coûté une longue soirée : elle commençait par « … », un
caractère qu'un en-tête HTTP ne peut pas transporter, et curl échouait
sans un mot. Une valeur écrite par la même commande ne peut pas diverger.

EN AVEUGLE : les valeurs ne sont jamais affichées, ici pas plus
qu'ailleurs. Le script n'imprime que « trouvée » ou « VIDE ».

    python outils/deposer_secrets.py                  # les deux
    python outils/deposer_secrets.py --cible etat     # le sous-domaine
    python outils/deposer_secrets.py --cible panneau  # le panneau
    python outils/deposer_secrets.py --essai          # écrit, n'envoie rien

À relancer le jour où la DASHBOARD_API_KEY du bot change —
`relever_cle_bot.py` va la rechercher sur le serveur, où elle fait
autorité, et met d'abord api/secrets.php à jour.
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

PANNEAU = os.path.join(RACINE, "site", "api", "secrets.php")
ETAT = os.path.join(RACINE, "site", "etat.secrets.php")

# Le modèle de ce qui est déposé sur le sous-domaine d'état. Les
# commentaires voyagent avec les valeurs : dans six mois, on doit
# retrouver SUR LE SERVEUR l'explication de ce qu'on y lit, sans avoir à
# revenir dans le dépôt.
GABARIT = """<?php
/* Les deux valeurs dont la page d'état a besoin, et rien d'autre.
 *
 * Écrit par outils/deposer_secrets.py, qui les recopie de
 * api/secrets.php. Ce fichier n'est dans aucune liste d'envoi : une
 * publication ne peut ni l'écraser, ni l'emporter. Le modèle versionné
 * est site/etat.secrets.exemple.php.
 *
 * Deux copies de la même valeur, et rien ne les tient alignées tout
 * seul : si la DASHBOARD_API_KEY du bot change, relance le script.
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


def ecrire_etat() -> bool:
    """Fabrique etat.secrets.php depuis api/secrets.php. False si une
    valeur manque — on ne dépose pas un fichier à moitié rempli."""
    with io.open(PANNEAU, encoding="utf-8") as f:
        brut = f.read()
    base = valeur(brut, "bot_api_base")
    cle = valeur(brut, "bot_api_key")

    print("  bot_api_base : " + ("trouvée" if base else "VIDE"))
    print("  bot_api_key  : " + ("trouvée" if cle else "VIDE"))
    if not base or not cle:
        print("\nL'une des deux manque dans api/secrets.php. La page d'état "
              "afficherait\n« mesure non configurée » — exact, mais sans "
              "intérêt. Rien n'est écrit.", file=sys.stderr)
        return False
    if not cle.isascii():
        print("\nLa clé contient un caractère hors ASCII : elle a été "
              "recopiée depuis un\naffichage qui l'avait abrégée. "
              "`relever_cle_bot.py` va chercher la vraie sur\nle serveur.",
              file=sys.stderr)
        return False

    # newline="\n" : un PHP en CRLF fonctionne, mais autant qu'il soit
    # identique depuis les deux machines.
    with io.open(ETAT, "w", encoding="utf-8", newline="\n") as f:
        f.write(GABARIT % (php(base), php(cle)))
    print("  " + os.path.relpath(ETAT, RACINE) + " écrit.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dépose les fichiers de secrets du site sur LWS.")
    parser.add_argument("--cible", choices=("panneau", "etat", "tout"),
                        default="tout")
    parser.add_argument("--essai", action="store_true",
                        help="écrit ce qui doit l'être, n'envoie rien")
    args = parser.parse_args()

    if not os.path.isfile(PANNEAU):
        print(f"{os.path.relpath(PANNEAU, RACINE)} est absent de ce PC.",
              file=sys.stderr)
        print("C'est lui qui porte les valeurs. Sans lui, rien à déposer.",
              file=sys.stderr)
        return 1

    if args.cible in ("etat", "tout"):
        print("sous-domaine d'état :")
        if not ecrire_etat():
            return 1

    if args.essai:
        print("\nEssai : rien n'a été envoyé.")
        return 0

    conf = publier_site.lire_config()
    if conf is None:
        print("Réglages LWS absents. Lance  cyq amorcer.", file=sys.stderr)
        return 1

    envois = []
    if args.cible in ("panneau", "tout"):
        envois.append(("panneau", conf.get("racine_app", ""), PANNEAU,
                       "secrets.php", "racine_app"))
    if args.cible in ("etat", "tout"):
        envois.append(("état", conf.get("racine_status", ""), ETAT,
                       "etat.secrets.php", "racine_status"))

    mot_de_passe = secrets_locaux.lire("lws")
    if not mot_de_passe:
        print("Aucun mot de passe FTP dans le coffre du système.", file=sys.stderr)
        print("Lance  cyq amorcer  pour l'y enregistrer.", file=sys.stderr)
        return 1
    curl = publier_site.Curl(conf, mot_de_passe)

    echecs = 0
    for nom, racine, local, distant, champ in envois:
        racine = str(racine).strip().rstrip("/")
        if not racine:
            print(f"{nom} : « {champ} » est vide dans lws.json — on ne sait "
                  "pas où déposer.", file=sys.stderr)
            echecs += 1
            continue
        cible = "ftp://" + conf["serveur"] + racine + "/" + distant
        print(f"\n{nom} -> {cible}")
        code, sortie = curl("--ftp-create-dirs", "--upload-file", local, cible)
        if code != 0:
            print("  ÉCHEC — " + publier_site.explique(code, sortie),
                  file=sys.stderr)
            echecs += 1
        else:
            print("  déposé.")

    if echecs:
        return 1
    print("\nRecharge https://status.cyqbot.eu — le cache garde la mesure "
          "vingt secondes,\ndonc clique « Mesurer maintenant » si le verdict "
          "n'a pas bougé.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
