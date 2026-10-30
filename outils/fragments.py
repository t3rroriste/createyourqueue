"""
Recopie les blocs communs (la nav, le pied) dans les pages du site.
==================================================================
Pourquoi : la barre de navigation vit sur six pages et le pied sur cinq.
Les modifier voulait dire les modifier six fois, et c'est exactement ce
qui s'est passé — le lien « Documentation » partait sur « # » depuis
l'accueil et sur « guide » depuis le support, parce qu'une correction
n'avait été reportée que sur une page. Personne ne l'a vu : les deux
liens avaient l'air de marcher.

Ce n'est PAS un build. Le site reste statique, Apache sert les fichiers
tels quels, et ce script fait ce que `numeroter_versions.py` fait déjà :
il réécrit une portion des pages sur le disque. Après son passage, les
fichiers du dossier `site` sont toujours exactement ce qui part en ligne.

    python outils/fragments.py              recopie
    python outils/fragments.py --verifier   dit ce qui a dérivé, n'écrit rien

Les sources sont dans `outils/communs/`, HORS du dossier `site` : un
fragment n'est pas une page, il ne doit jamais partir en ligne, et le
mettre dans `site` revenait à compter sur `fichiers_du_site.py` pour
l'oublier.

COMMENT UNE PAGE RÉCLAME UN BLOC
--------------------------------
Elle pose deux repères, et c'est tout :

    <!-- cyq:nav courant=modules origine=site -->
    <!-- cyq:/nav -->

Le script remplit l'entre-deux. Les paramètres sont lus sur le repère
ouvrant, donc c'est LA PAGE qui dit ce qu'elle veut : le script n'a pas
de liste de pages à tenir à jour, et une page neuve hérite de la nav en
collant ces deux lignes. L'indentation du repère ouvrant est reportée sur
tout le bloc, pour que la page reste lisible.

CE QU'UN FRAGMENT SAIT FAIRE
----------------------------
Deux constructions, et il n'y en aura pas de troisième — un gabarit qui
grossit finit par demander qu'on apprenne un langage pour changer un
lien :

    {{si origine=app}}…{{sinon}}…{{/si}}   selon un paramètre
    {{=courant}}                            la valeur d'un paramètre

Un `{{si}}` seul sur sa ligne ne laisse pas de ligne vide derrière lui.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
SITE = os.path.join(RACINE, "site")
COMMUNS = os.path.join(OUTILS_DIR, "communs")

# <!-- cyq:nav courant=modules origine=site -->  …  <!-- cyq:/nav -->
# Le `.*?` est non gourmand et `re.S` lui laisse franchir les lignes :
# sans ça, deux blocs dans la même page n'en feraient qu'un.
REPERES = re.compile(
    r"([ \t]*)<!--[ \t]*cyq:([a-z][a-z0-9_-]*)([^>]*?)-->"
    r"(.*?)"
    r"[ \t]*<!--[ \t]*cyq:/\2[ \t]*-->",
    re.S,
)

PARAM = re.compile(r"([a-z][a-z0-9_-]*)=([^\s]+)")
# `sinon` AVANT `si` : l'alternation s'arrête au premier qui colle, et
# « si » colle au début de « sinon » — {{sinon}} se lisait {{si non}}.
JETON = re.compile(r"\{\{(sinon|si|/si|=)[ \t]*([^}]*?)[ \t]*\}\}")

# Un jeton seul sur sa ligne : on mange la ligne entière, lui compris.
# Sinon `{{si}}` posé sur sa propre ligne laisserait une ligne vide dans
# la page engendrée, et il y en aurait une par condition.
SEUL = re.compile(r"^[ \t]*(\{\{(?:si[^}]*|sinon|/si)\}\})[ \t]*\r?\n", re.M)


# Le commentaire qui OUVRE un fragment documente le fragment : ce que font
# ses paramètres, pourquoi il existe. Il parle au prochain qui ouvrira
# `outils/communs/`, pas au lecteur d'une page — recopié onze fois, il
# noierait le balisage qu'il accompagne. Les commentaires qui suivent, eux,
# expliquent une ligne de HTML et partent avec elle.
ENTETE = re.compile(r"\A\s*<!--.*?-->[ \t]*\r?\n", re.S)


def charger(nom: str) -> str:
    chemin = os.path.join(COMMUNS, nom + ".html")
    if not os.path.isfile(chemin):
        raise SystemExit(f"fragment introuvable : {chemin}")
    with open(chemin, encoding="utf-8", newline="") as f:
        return ENTETE.sub("", f.read(), count=1)


def rendre(gabarit: str, params: dict, ou: str) -> str:
    """Déroule les conditions et les valeurs. `ou` ne sert qu'aux messages."""
    gabarit = SEUL.sub(r"\1", gabarit)

    morceaux: list[str] = []
    pile: list[bool] = []          # pour chaque {{si}} ouvert : on écrit ?
    pos = 0

    for m in JETON.finditer(gabarit):
        if all(pile):
            morceaux.append(gabarit[pos:m.start()])
        pos = m.end()
        genre, corps = m.group(1), m.group(2)

        if genre == "si":
            p = PARAM.fullmatch(corps.strip())
            if not p:
                raise SystemExit(f"{ou} : condition illisible — {{{{si {corps}}}}}")
            cle, attendu = p.group(1), p.group(2)
            if cle not in params:
                # On avertit sans refuser : un paramètre oublié rend la
                # condition fausse, ce qui est visible à l'œil sur la page.
                print(f"  ! {ou} : paramètre « {cle} » non fourni")
            pile.append(params.get(cle) == attendu)
        elif genre == "sinon":
            if not pile:
                raise SystemExit(f"{ou} : {{{{sinon}}}} sans {{{{si}}}}")
            pile[-1] = not pile[-1]
        elif genre == "/si":
            if not pile:
                raise SystemExit(f"{ou} : {{{{/si}}}} en trop")
            pile.pop()
        else:                       # {{=cle}}
            if all(pile):
                morceaux.append(params.get(corps, ""))

    if pile:
        raise SystemExit(f"{ou} : un {{{{si}}}} n'est pas refermé")
    morceaux.append(gabarit[pos:])
    return "".join(morceaux)


def indenter(bloc: str, marge: str) -> str:
    """Repose le bloc à la marge du repère. Les lignes vides restent vides :
    une ligne faite d'espaces apparaît dans un diff et ne se voit pas."""
    return "\n".join(
        (marge + l if l.strip() else "") for l in bloc.splitlines()
    )


def pages(dossier: str) -> list[str]:
    return sorted(
        os.path.join(dossier, n) for n in os.listdir(dossier)
        if n.endswith(".html") and os.path.isfile(os.path.join(dossier, n))
    )


def traiter(page: str, verifier: bool) -> tuple[int, bool]:
    """Retourne (nombre de blocs vus, la page a-t-elle bougé)."""
    with open(page, encoding="utf-8", newline="") as f:
        avant = f.read()

    vus = 0

    def remplacer(m: re.Match) -> str:
        nonlocal vus
        vus += 1
        marge, nom, args, _ancien = m.group(1), m.group(2), m.group(3), m.group(4)
        params = dict(PARAM.findall(args))
        ou = f"{os.path.basename(page)} / {nom}"
        bloc = rendre(charger(nom), params, ou).strip("\r\n")
        # Une ligne, et une seule, pour dire d'où vient ce qui suit : qui
        # ouvre la page doit voir tout de suite que le corriger ici ne
        # servira à rien. L'explication, elle, reste dans le fragment.
        return (
            f"{marge}<!-- cyq:{nom}{args.rstrip()}"
            + (" " if args.strip() else "")
            + "-->\n"
            + f"{marge}<!-- engendré par outils/fragments.py "
            + f"depuis outils/communs/{nom}.html -->\n"
            + indenter(bloc, marge)
            + f"\n{marge}<!-- cyq:/{nom} -->"
        )

    apres = REPERES.sub(remplacer, avant)

    if not vus or apres == avant:
        return vus, False
    if not verifier:
        with open(page, "w", encoding="utf-8", newline="") as f:
            f.write(apres)
    return vus, True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--verifier", action="store_true",
                    help="n'écrit rien ; sort en erreur si une page a dérivé")
    # La veille l'appelle à chaque passage : sans ce drapeau, son journal
    # n'aurait plus que ça dedans. Les erreurs, elles, parlent toujours —
    # elles passent par SystemExit, et --verifier n'est jamais silencieux
    # puisque c'est précisément pour lire sa réponse qu'on le lance.
    ap.add_argument("--silencieux", action="store_true",
                    help="ne dit rien quand tout va bien (la veille)")
    args = ap.parse_args()

    def dire(*bouts):
        if not args.silencieux or args.verifier:
            print(*bouts)

    total, bouge = 0, []
    for page in pages(SITE):
        vus, change = traiter(page, args.verifier)
        total += vus
        if change:
            bouge.append(os.path.basename(page))

    if not total:
        dire("Aucun repère cyq: dans les pages — rien à faire.")
        return 0

    if args.verifier:
        if bouge:
            dire("Ces pages ne correspondent plus à leur fragment :")
            for n in bouge:
                dire("  -", n)
            dire("\n  python outils/fragments.py")
            return 1
        dire(f"{total} blocs, tous à jour.")
        return 0

    for n in bouge:
        dire("  mis à jour :", n)
    dire(f"\n{total} blocs communs, {len(bouge)} page(s) réécrite(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
