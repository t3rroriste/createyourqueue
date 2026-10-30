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
  · un point d'API décrit dans `docs/site-README.md` dont une des deux
    implémentations ne parle pas du tout.

Le second est volontairement grossier : il cherche les NOMS du chemin,
en mots entiers, n'importe où dans le fichier. Il ne compare pas les
routes, parce que les deux routeurs ne s'écrivent pas pareil — le PHP
range `matches`, `activity` et `audit` dans une seule alternance, le
Python délègue à une méthode qui les traite plus loin. La première
version de ce script tentait de reconstruire les deux formes : elle
criait au loup neuf fois sur un dépôt sain, et un contrôle qui se trompe
autant est un contrôle qu'on apprend à ignorer.

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
CONTRAT_DOC = os.path.join(RACINE, "docs", "site-README.md")

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


# ------------------------------------------------- le contrat ecrit ---------

# Les points d'API tels que `docs/site-README.md` les titre :
#     ### `GET /guilds/{id}/activity`
CONTRAT = re.compile(r"^#{3,4} `(GET|POST|PATCH|DELETE) (/[^`]+)`", re.M)


def points_du_contrat(doc: str) -> list[tuple[str, str]]:
    return CONTRAT.findall(doc)


def sert(fichier: str, chemin: str) -> bool:
    """Le fichier parle-t-il de ce point d'API ?

    On cherche les NOMS du chemin, en mots entiers, n'importe ou dans le
    fichier — pas la route elle-meme. Les deux routeurs ne s'ecrivent pas
    du tout pareil : le PHP range matches, activity et audit dans une
    seule alternance `(matches|activity|audit)`, et le Python delegue a
    une methode qui les traite plus loin. Reconstruire les deux formes
    donnerait un outil qui se trompe plus souvent qu'il n'aide — la
    premiere version de ce script criait au loup neuf fois sur un depot
    sain.

    Une recherche large ne repere donc que l'absence COMPLETE d'un nom.
    C'est peu, mais c'est sur, et c'est exactement la faute qu'on cherche :
    un point ajoute d'un seul cote.
    """
    noms = [b for b in chemin.split("/") if b and not b.startswith("{")]
    return all(re.search(r"\b" + re.escape(n) + r"\b", fichier) for n in noms)


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

    # 2. Le contrat, et les deux implémentations qui doivent le tenir.
    contrat = points_du_contrat(lire(CONTRAT_DOC)) if os.path.isfile(CONTRAT_DOC) else []
    absents = []
    for verbe, chemin in contrat:
        for fichier, nom in ((php, "site/api/index.php"),
                             (py, "api-locale/server.py")):
            if not sert(fichier, chemin):
                absents.append((verbe, chemin, nom))

    if absents:
        fautes += len(absents)
        print("\nPoints du contrat qu'une implémentation ne sert pas :")
        for verbe, chemin, nom in absents:
            print("  %-6s %-32s absent de %s" % (verbe, chemin, nom))
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

    dire("\n%d réglages du panneau et %d points du contrat : le panneau, le"
         " PHP et le Python sont d'accord."
         % (len(reglages_du_panneau(html)), len(contrat)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
