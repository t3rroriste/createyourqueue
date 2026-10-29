"""
Sert le dossier `site/` comme Apache le sert en ligne.
======================================================
`python -m http.server` a fait l'affaire tant que toutes les adresses
portaient leur « .html ». Depuis le 29 octobre, les pages se lient entre
elles par leur FORME COURTE — /guide, /modules, /support — et un serveur
de fichiers nu répond 404 à tout ça. On ne peut donc plus vérifier en
local ce qui part en ligne, ce qui est exactement ce qu'on demande au
serveur local de permettre.

Ce fichier rejoue les trois règles de `site/.htaccess`, et rien d'autre :

  1. /guide/      -> redirection 301 vers /guide  (la barre finale casse
                     la résolution des « assets/… » relatifs)
  2. /guide.html  -> redirection 301 vers /guide  (une seule adresse par
                     page), sauf /login.html, qui répond 200 lui-même :
                     c'est l'adresse de retour OAuth déclarée chez
                     Discord, au caractère près, et une redirection y
                     serait vue comme une redirect_uri inconnue.
  3. /guide       -> sert guide.html, SANS changer la barre d'adresse.

En Python, et dans `outils/`, parce que les deux machines doivent avoir le
même geste : `cyq.ps1` et `cyq.sh` l'appellent toutes les deux.

    python outils/serveur_local.py            (port 8765)
    python outils/serveur_local.py --port 9000 --dossier site
"""

from __future__ import annotations

import argparse
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)

# La liste est EXPLICITE, comme dans le .htaccess : /api est servi par PHP
# en ligne et ne doit jamais passer par ces règles. Une règle attrape-tout
# donnerait un serveur local qui se comporte autrement que la production,
# c'est-à-dire un serveur local qui ne sert à rien.
PAGES = ("index", "login", "welcome", "servers", "dashboard",
         "modules", "guide", "support")

# login n'y est pas : voir l'en-tête du fichier.
VERS_FORME_COURTE = tuple(p for p in PAGES if p != "login")


class Handler(SimpleHTTPRequestHandler):

    def send_head(self):
        chemin, _, requete = self.path.partition("?")
        nom = urlsplit(chemin).path.strip("/")
        suffixe = ("?" + requete) if requete else ""

        # 1. la barre finale
        if nom.endswith("/"):
            nom = nom[:-1]
        if chemin.endswith("/") and nom in PAGES:
            return self._rediriger("/" + nom + suffixe)

        # 2. la forme longue renvoie vers la courte
        if nom.endswith(".html"):
            base = nom[:-5]
            if base == "index":
                return self._rediriger("/" + suffixe)
            if base in VERS_FORME_COURTE:
                return self._rediriger("/" + base + suffixe)

        # 3. la forme courte sert la page, sans bouger la barre d'adresse
        if nom in PAGES:
            fichier = os.path.join(self.directory, nom + ".html")
            if os.path.isfile(fichier):
                self.path = "/" + nom + ".html" + suffixe

        return super().send_head()

    def _rediriger(self, vers: str):
        self.send_response(301)
        self.send_header("Location", vers)
        self.send_header("Content-Length", "0")
        self.end_headers()
        return None

    def log_message(self, fmt, *args):
        pass        # le journal par défaut noie la sortie utile


def main() -> int:
    parser = argparse.ArgumentParser(description="Sert site/ comme Apache.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dossier", default=os.path.join(RACINE, "site"))
    args = parser.parse_args()

    dossier = os.path.abspath(args.dossier)
    if not os.path.isdir(dossier):
        print(f"{dossier} n'existe pas.", file=sys.stderr)
        return 1

    def fabrique(*a, **kw):
        return Handler(*a, directory=dossier, **kw)

    print(f"  http://localhost:{args.port}/  —  Ctrl+C pour arrêter.")
    ThreadingHTTPServer(("0.0.0.0", args.port), fabrique).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
