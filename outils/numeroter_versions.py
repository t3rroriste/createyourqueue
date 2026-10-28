"""
Renumérote les assets (?v=…) des pages du site.
===============================================
Pourquoi : le navigateur garde en cache les CSS, les JS et les fichiers de
langue. Sans ce numéro, on modifie un fichier, on recharge… et on voit
l'ancienne version. Le numéro change -> l'URL change -> le navigateur
retélécharge. C'est le seul moyen fiable sur un site sans build.

    python outils/numeroter_versions.py
    python outils/numeroter_versions.py --dossier archives/en-ligne-2026-09-28

La veille le lance toute seule AVANT d'enregistrer, quand une page, une
feuille ou un script a changé. À la main, c'est la commande ci-dessus.

Il avertit aussi quand une page réclame un fichier qui n'est pas déclaré
dans `fichiers_du_site.py` — il AVERTIT, il ne bloque pas : renuméroter
reste utile même si la liste est incomplète, et un script de cache n'a pas
à refuser de travailler. Deux fois de suite, une feuille neuve est partie en
ligne sans être déclarée, et les deux fois on ne l'a vu qu'une fois en
production.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
SITE = os.path.join(RACINE, "site")

sys.path.insert(0, OUTILS_DIR)
import fichiers_du_site  # noqa: E402

# href="assets/….css" et src="assets/….js", avec ou sans ?v= déjà posé.
FEUILLE = re.compile(r'(href="assets/[^"?]+\.css)(\?v=[^"]*)?"')
SCRIPT = re.compile(r'(src="assets/[^"?]+\.js)(\?v=[^"]*)?"')
DEMANDE = re.compile(r'(?:href|src)="(assets/[^"?]+)')


def pages(dossier: str) -> list[str]:
    return sorted(
        os.path.join(dossier, n) for n in os.listdir(dossier)
        if n.endswith(".html") and os.path.isfile(os.path.join(dossier, n))
    )


def numeroter(dossier: str, version: str) -> list[str]:
    """Réécrit les pages ; retourne celles qui ont bougé."""
    changees = []
    for page in pages(dossier):
        # newline="" : on ne veut pas que Python convertisse les fins de
        # ligne au passage. Un fichier réécrit en CRLF sur Windows et en LF
        # sur le Mac ferait voir à git un fichier entièrement modifié à
        # chaque synchro, alors qu'une seule ligne a changé.
        with open(page, encoding="utf-8", newline="") as f:
            avant = f.read()
        apres = FEUILLE.sub(r'\1?v=' + version + '"', avant)
        apres = SCRIPT.sub(r'\1?v=' + version + '"', apres)
        if apres != avant:
            with open(page, "w", encoding="utf-8", newline="") as f:
                f.write(apres)
            changees.append(os.path.basename(page))
    return changees


def oublis(dossier: str) -> list[str]:
    """Les assets qu'une page réclame et que la liste d'envoi ignore."""
    trouves = []
    for page in pages(dossier):
        with open(page, encoding="utf-8") as f:
            texte = f.read()
        for m in DEMANDE.finditer(texte):
            demande = m.group(1)
            if demande not in fichiers_du_site.DECLARES:
                trouves.append(f"{demande}   (demandé par {os.path.basename(page)})")
    return sorted(set(trouves))


def main() -> int:
    parser = argparse.ArgumentParser(description="Renumérote les ?v= des pages.")
    parser.add_argument("--dossier", default=SITE,
                        help="le dossier à traiter (défaut : site/)")
    parser.add_argument("--silencieux", action="store_true",
                        help="n'affiche que l'essentiel (la veille s'en sert)")
    args = parser.parse_args()

    dossier = os.path.abspath(args.dossier)
    if not os.path.isdir(dossier):
        print(f"{dossier} n'existe pas.", file=sys.stderr)
        return 1

    version = datetime.now().strftime("%Y%m%d%H%M")
    changees = numeroter(dossier, version)

    if not args.silencieux:
        for nom in changees:
            print(f"  mis à jour : {nom}")
        print(f"\nVersion des assets : {version}")
    elif changees:
        print(f"{len(changees)} page(s) renumérotée(s) en {version}")

    # Le contrôle des oublis ne vaut que pour le site de travail : sur une
    # copie d'archive, la liste d'envoi n'a rien à dire.
    if dossier == os.path.abspath(SITE):
        manquants = oublis(dossier)
        if manquants:
            print("\nATTENTION — ces fichiers sont demandés par une page mais NE PARTIRONT PAS :",
                  file=sys.stderr)
            for m in manquants:
                print("  " + m, file=sys.stderr)
            print("Ajoute-les à outils/fichiers_du_site.py, sinon la page s'affichera "
                  "sans style en ligne.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
