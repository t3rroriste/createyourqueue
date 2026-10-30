"""
Tient d'accord le panneau, l'API PHP et l'API Python.
=====================================================
Pourquoi : l'API est écrite DEUX FOIS. `site/api/index.php` répond en
production, parce que LWS n'exécute que du PHP ; `api-locale/server.py`
répond pendant qu'on développe. Changer une réponse oblige à la changer
des deux côtés, et rien ne proteste quand on en oublie un.

Mais le piège le plus coûteux n'est pas là. Il est entre `dashboard.html`
et le pont du PHP : une ligne de réglage s'ajoute en posant un
`data-setting` dans la page, et le panneau sait alors l'afficher, la
suivre et l'enregistrer — tout seul, sans toucher au JavaScript. Si les
tables `PONT_*` d'`index.php` ne connaissent pas la clé, elle ne quitte
jamais le fichier du site : le panneau affiche, enregistre, dit
« Enregistré », et le bot n'en sait rien. C'est arrivé aux sept réglages
de sécurité et aux trois clés de clan, et les deux fois on ne l'a vu
qu'en se demandant pourquoi le bot n'obéissait pas.

    python outils/verifier_api.py
    python outils/verifier_api.py --silencieux

PHP n'est pas installé sur les machines de développement : ce contrôle
est donc STATIQUE. Il lit les deux fichiers, il ne les exécute pas, et il
ne peut rien dire de ce qu'ils renvoient vraiment.

CE QU'IL VÉRIFIE
----------------
Dur (une faute, il sort en erreur) :
  · un `data-setting` du panneau qu'aucun pont ne connaît, que le PHP ne
    cite nulle part, et dont `docs/INVENTAIRE-REGLAGES.md` ne parle pas ;
  · un point d'API servi par une implémentation et pas par l'autre.

Souple (un avis) :
  · un réglage qui traverse AUTREMENT que par le pont — `bot.nick` part
    vers Discord et non vers le bot, et c'est voulu ;
  · un réglage que l'inventaire déclare propre au site — `queue.session`
    n'a pas d'équivalent côté bot, et c'est voulu aussi.

L'inventaire sert de liste d'exceptions, et ce n'est pas un pis-aller :
une clé qui ne traverse pas est une décision, elle doit être écrite
quelque part qu'un humain lit. Mettre cette liste dans ce script
l'aurait cachée là où personne ne la cherche.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)

PANNEAU = os.path.join(RACINE, "site", "dashboard.html")
API_PHP = os.path.join(RACINE, "site", "api", "index.php")
API_PY = os.path.join(RACINE, "api-locale", "server.py")
INVENTAIRE = os.path.join(RACINE, "docs", "INVENTAIRE-REGLAGES.md")

# La fonction du PHP qui décide de ce qui part vers le bot.
TRI = "function trier_pour_le_bot"


def lire(chemin: str) -> str:
    with open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


# ------------------------------------------------------------ le pont -------

def pont(php: str) -> tuple[set[str], list[str]]:
    """Ce que le PHP sait faire traverser : clés en clair, et motifs.

    Les motifs comptent autant que les clés : `mmr.rank3.name` n'est
    écrit nulle part, il est reconnu par une expression. Les ignorer
    ferait crier au loup sur une quarantaine de réglages parfaitement
    reliés.
    """
    i = php.index(TRI)
    fin = php.index("\n}", i)
    fonction = php[i:fin]

    cles = set(re.findall(r"\$k\s*===\s*'([^']+)'", fonction))

    for table in set(re.findall(r"array_key_exists\(\$k,\s*(PONT_\w+)\)", fonction)):
        deb = php.index("const %s = [" % table)
        cles |= set(re.findall(r"'([^']+)'\s*=>", php[deb:php.index("];", deb)]))

    # Les motifs PHP passent tels quels en Python : ce sont des PCRE sans
    # rien d'exotique. `\d`, `[a-z]`, l'alternance et les accolades se
    # lisent pareil des deux côtés.
    motifs = re.findall(r"preg_match\('#([^']+)#',\s*\$k", fonction)
    return cles, motifs


def reglages_du_panneau(html: str) -> list[str]:
    return sorted(set(re.findall(r'data-setting="([^"]+)"', html)))


# ----------------------------------------------------------- les routes -----

# PHP : $chemin === '/me' && $methode === 'GET'
ROUTE_PHP = re.compile(r"\$chemin\s*===\s*'(/[^']*)'")
# PHP : preg_match('#^/guilds/(\d{5,25})/(matches|activity|audit)$#', $chemin
MOTIF_PHP = re.compile(r"preg_match\('#\^(/[^']+?)\$?#',\s*\$chemin")
# Python : chemin == "/api/me"  ·  chemin.endswith("/settings")
ROUTE_PY = re.compile(r'chemin\s*==\s*"(/[^"]*)"')
BOUT_PY = re.compile(r'chemin\.endswith\(\s*"(/[^"]*)"')


def points(texte: str, *motifs: re.Pattern) -> set[str]:
    """Les NOMS de points d'API cités, prefixe /api et identifiants ôtés.

    On ne compare pas des routes entières : le PHP les écrit en
    expressions, le Python en `startswith` + `endswith`, et prétendre
    reconstruire les deux formes donnerait un outil qui se trompe plus
    souvent qu'il n'aide. On compare ce dont on est sûr — les noms qui
    apparaissent dans les chemins. Un point ajouté d'un seul côté s'y
    voit, et c'est la faute qu'on cherche.
    """
    vus: set[str] = set()
    for m in motifs:
        for brut in m.findall(texte):
            chemin = re.sub(r"^/api", "", brut)
            for bout in chemin.split("/"):
                bout = bout.strip()
                # Ce qui n'est pas un nom : un identifiant, un groupe
                # d'expression, un reste de syntaxe.
                if re.fullmatch(r"[a-z][a-z0-9_.-]*", bout) and bout != "api":
                    vus.add(bout)
            for alt in re.findall(r"\(([a-z|]+)\)", chemin):
                vus |= {a for a in alt.split("|") if a}
    return vus


# ----------------------------------------------------------------- relevé ---

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--silencieux", action="store_true",
                    help="ne dit rien quand tout va bien")
    args = ap.parse_args()

    def dire(*bouts):
        if not args.silencieux:
            print(*bouts)

    php, py = lire(API_PHP), lire(API_PY)
    html = lire(PANNEAU)
    inventaire = lire(INVENTAIRE) if os.path.isfile(INVENTAIRE) else ""

    cles, motifs = pont(php)
    fautes = 0

    # 1. Les réglages du panneau qui n'arrivent pas au bot.
    perdus, autrement, declares = [], [], []
    for k in reglages_du_panneau(html):
        if k in cles or any(re.search(m, k) for m in motifs):
            continue
        if ("'%s'" % k) in php or ('"%s"' % k) in php:
            autrement.append(k)
        elif ("`%s`" % k) in inventaire:
            declares.append(k)
        else:
            perdus.append(k)

    if perdus:
        fautes += len(perdus)
        print("Réglages du panneau qui n'atteignent jamais le bot :")
        for k in perdus:
            print("  %s" % k)
        print("  Le panneau les enregistre et dit « Enregistré ». Le bot"
              " n'en sait rien.")
        print("  À relier dans les tables PONT_* de site/api/index.php, ou"
              "\n  à déclarer propres au site dans docs/INVENTAIRE-REGLAGES.md.")

    # 2. Les points d'API servis d'un seul côté.
    cote_php = points(php, ROUTE_PHP, MOTIF_PHP)
    cote_py = points(py, ROUTE_PY, BOUT_PY)
    manque_py = sorted(cote_php - cote_py)
    manque_php = sorted(cote_py - cote_php)

    if manque_py or manque_php:
        fautes += len(manque_py) + len(manque_php)
        print("\nPoints d'API servis d'un seul côté :")
        for p in manque_py:
            print("  %-14s en PHP, pas dans api-locale/server.py" % p)
        for p in manque_php:
            print("  %-14s en Python, pas dans site/api/index.php" % p)
        print("  Le développement et la production ne répondent pas pareil.")

    # 3. Les avis.
    if autrement:
        dire("\n%d réglage(s) traversent autrement que par le pont :"
             % len(autrement))
        dire("  " + ", ".join(autrement))
    if declares:
        dire("\n%d réglage(s) que l'inventaire déclare propres au site :"
             % len(declares))
        dire("  " + ", ".join(declares))

    if fautes:
        print("\n%d faute(s)." % fautes)
        return 1

    dire("\n%d réglages du panneau, %d points d'API : les trois fichiers"
         " sont d'accord." % (len(reglages_du_panneau(html)), len(cote_php)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
