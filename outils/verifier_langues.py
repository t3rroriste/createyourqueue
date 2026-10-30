"""
Tient les cinq fichiers de langue d'accord entre eux.
=====================================================
Pourquoi : ajouter un texte visible, c'est ajouter une clé dans `fr.js`,
`en.js`, `es.js`, `de.js` ET `ko.js`. Cinq fichiers pour une phrase, et
rien ne proteste quand on en oublie un — `t()` renvoie la clé elle-même,
donc la page affiche « ov.recent » à la place du titre. En français tout
va bien, et personne ne s'en aperçoit avant de changer de langue.

    python outils/verifier_langues.py              le relevé
    python outils/verifier_langues.py --completer  recopie les manquantes
    python outils/verifier_langues.py --silencieux  ne parle qu'en cas de faute

Il ne TRADUIT pas et ne le prétend pas : `--completer` recopie la valeur
française dans les fichiers où la clé manque, en la marquant. La page
cesse d'afficher une clé nue — ce qui est toujours mieux qu'un identifiant
au milieu d'une phrase — et le marqueur dit ce qui reste à faire. Chercher
`À TRADUIRE` donne la liste.

CE QU'IL VÉRIFIE, ET CE QU'IL NE PEUT PAS VÉRIFIER
--------------------------------------------------
Dur (une faute, il sort en erreur) :
  · une clé de `fr.js` absente d'une autre langue ;
  · une clé d'une autre langue absente de `fr.js` — un reste d'un texte
    supprimé, qui restera là indéfiniment sans ça ;
  · une clé demandée par le balisage (`data-i18n`) ou par un `t('…')`
    écrit en toutes lettres, et définie nulle part.

Souple (un avis, il n'échoue pas) :
  · une clé définie que personne ne semble demander. « Semble » est le
    mot : beaucoup d'appels construisent leur clé à l'exécution —
    `t(cle)`, `t(colonne)`, `t('ov.ago' + unite)` — et le relevé ne les
    voit pas. Une clé signalée ici n'est donc pas forcément morte ; c'est
    une piste, à vérifier à la main avant d'effacer quoi que ce soit.

`fr.js` fait foi pour l'ordre comme pour la liste : c'est la langue dans
laquelle les textes sont écrits d'abord.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
SITE = os.path.join(RACINE, "site")
LANGUES_DIR = os.path.join(SITE, "assets", "js", "lang")

REFERENCE = "fr"
LANGUES = ["fr", "en", "es", "de", "ko"]

# "une.cle": "sa valeur"
DEFINITION = re.compile(r'"([A-Za-z_][\w.\-]*)"\s*:\s*"((?:[^"\\]|\\.)*)"')
# data-i18n="une.cle" dans les pages ET dans le balisage bâti en JS
POSE = re.compile(r'data-i18n="([^"]+)"')
# data-i18n-attr="aria-label:c.lang, title:sv.logout"
POSE_ATTR = re.compile(r'data-i18n-attr="([^"]+)"')
# t('une.cle') écrit en toutes lettres. Le `(?<![\w.])` écarte les
# `parseInt(`, `encodeURIComponent(` et autres fins de mot en « t ».
APPEL = re.compile(r"(?<![\w.])t\(\s*'([A-Za-z_][\w.\-]*)'\s*\)")

# La forme d'une clé : « ov.recent », « c.save ». Sert à écarter ce qui
# n'en est pas une — un `{n}` de substitution, un bout de concaténation.
CLE_VALIDE = re.compile(r"[A-Za-z_][\w.\-]*")

MARQUE = "/* À TRADUIRE */"


def fichier(langue: str) -> str:
    return os.path.join(LANGUES_DIR, langue + ".js")


def lire(chemin: str) -> str:
    with open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


def definies(langue: str) -> dict[str, str]:
    """Les clés d'une langue, DANS L'ORDRE du fichier."""
    return {m.group(1): m.group(2) for m in DEFINITION.finditer(lire(fichier(langue)))}


def sources() -> list[str]:
    """Les pages et les scripts, c'est-à-dire tout ce qui réclame une clé."""
    out = []
    for n in sorted(os.listdir(SITE)):
        if n.endswith(".html"):
            out.append(os.path.join(SITE, n))
    js = os.path.join(SITE, "assets", "js")
    for n in sorted(os.listdir(js)):
        if n.endswith(".js"):
            out.append(os.path.join(js, n))
    return out


def demandees() -> dict[str, set[str]]:
    """Les clés réclamées, et par quels fichiers — pour pouvoir le dire."""
    ou: dict[str, set[str]] = {}

    def noter(cle: str, fich: str) -> None:
        # Tout ce qui n'a pas la forme d'une clé est écarté SANS RIEN DIRE,
        # et c'est voulu : le panneau bâtit son balisage en JS, donc on
        # tombe sur des `data-i18n="' + cle + '"` et des `data-i18n="lo.'
        # + k + '"`. Ce sont de vraies poses, dont la clé ne se connaîtra
        # qu'à l'exécution — les signaler reviendrait à demander qu'on
        # écrive en dur ce qui est justement calculé.
        if CLE_VALIDE.fullmatch(cle):
            ou.setdefault(cle, set()).add(os.path.basename(fich))

    for chemin in sources():
        texte = lire(chemin)
        for m in POSE.finditer(texte):
            noter(m.group(1), chemin)
        for m in POSE_ATTR.finditer(texte):
            for paire in m.group(1).split(","):
                if ":" in paire:
                    noter(paire.split(":", 1)[1].strip(), chemin)
        for m in APPEL.finditer(texte):
            noter(m.group(1), chemin)
    return ou


# ------------------------------------------------------------- completion ---

def completer(manquantes: dict[str, list[str]], ref: dict[str, str]) -> int:
    """Recopie dans chaque langue les clés qui lui manquent.

    Chacune est posée sur SA PROPRE LIGNE, juste après la clé qui la
    précède dans `fr.js`. Poser la ligne entière plutôt que l'ajouter à
    une ligne existante garde le fichier lisible, et surtout garde le
    diff court : une ligne ajoutée, et rien de déplacé autour.
    """
    ordre = list(ref)
    ecrites = 0

    for langue, cles in manquantes.items():
        if not cles:
            continue
        texte = lire(fichier(langue))
        for cle in cles:
            i = ordre.index(cle)
            # On remonte jusqu'à une clé que CE fichier possède déjà :
            # si deux clés voisines manquent, la première vient d'être
            # posée, et la seconde se range juste derrière elle.
            ancre = None
            for j in range(i - 1, -1, -1):
                if ('"%s"' % ordre[j]) in texte:
                    ancre = ordre[j]
                    break

            ligne = '  "%s": "%s",  %s\n' % (cle, ref[cle], MARQUE)
            if ancre is None:
                # Aucune clé avant elle : juste après l'accolade ouvrante.
                pos = texte.index("{", texte.index("CYQ_I18N")) + 1
                texte = texte[:pos] + "\n" + ligne.rstrip("\n") + texte[pos:]
            else:
                pos = texte.index('"%s"' % ancre)
                fin = texte.index("\n", pos) + 1
                texte = texte[:fin] + ligne + texte[fin:]
            ecrites += 1

        with open(fichier(langue), "w", encoding="utf-8", newline="") as f:
            f.write(texte)
    return ecrites


# ------------------------------------------------------------------ relevé ---

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--completer", action="store_true",
                    help="recopie les clés manquantes depuis le français")
    ap.add_argument("--inutilisees", action="store_true",
                    help="liste les clés que le relevé ne voit demandées nulle part")
    ap.add_argument("--silencieux", action="store_true",
                    help="ne dit rien quand tout va bien")
    args = ap.parse_args()

    def dire(*bouts):
        if not args.silencieux:
            print(*bouts)

    ref = definies(REFERENCE)
    autres = {lg: definies(lg) for lg in LANGUES if lg != REFERENCE}
    reclamees = demandees()

    fautes = 0

    # 1. Ce qui manque à une langue.
    manquantes = {lg: [c for c in ref if c not in d] for lg, d in autres.items()}
    total_manquant = sum(len(v) for v in manquantes.values())
    if total_manquant:
        fautes += total_manquant
        print("Clés présentes en français et absentes ailleurs :")
        for lg, cles in manquantes.items():
            if cles:
                print("  %s.js — %d : %s" % (lg, len(cles), ", ".join(cles[:8])
                                             + (" …" if len(cles) > 8 else "")))

    # 2. Ce qu'une langue a en trop.
    surplus = {lg: [c for c in d if c not in ref] for lg, d in autres.items()}
    if any(surplus.values()):
        fautes += sum(len(v) for v in surplus.values())
        print("\nClés qui n'existent plus en français :")
        for lg, cles in surplus.items():
            if cles:
                print("  %s.js — %s" % (lg, ", ".join(cles)))

    # 3. Ce que le code réclame sans que personne ne le définisse.
    orphelines = sorted(c for c in reclamees if c not in ref)
    if orphelines:
        fautes += len(orphelines)
        print("\nClés réclamées par le code et définies nulle part :")
        for c in orphelines:
            print("  %-28s %s" % (c, ", ".join(sorted(reclamees[c]))))

    if args.completer and total_manquant:
        n = completer(manquantes, ref)
        print("\n%d clé(s) recopiée(s) depuis le français, marquées « %s »."
              % (n, MARQUE.strip("/* ").strip(" */")))
        print("Elles s'affichent donc en français tant qu'elles ne sont pas"
              " traduites — pas en tant que clé nue.")
        fautes -= total_manquant

    # 4. L'avis, qui ne fait pas échouer. Voir l'en-tête : beaucoup de clés
    #    sont construites à l'exécution et n'apparaissent pas au relevé.
    #    Une ligne par défaut, la liste seulement si on la demande : elles
    #    sont 230 sur 686, et les déverser à chaque passage noierait les
    #    trois lignes pour lesquelles on lance ce script.
    jamais_vues = [c for c in ref if c not in reclamees]
    if jamais_vues and not args.inutilisees:
        dire("\n%d clé(s) ne sont réclamées nulle part au relevé — beaucoup"
             " sont bâties à l'exécution." % len(jamais_vues))
        dire("  La liste : --inutilisees")
    elif jamais_vues:
        print("\n%d clé(s) que le relevé ne voit réclamées nulle part."
              % len(jamais_vues))
        print("  Une clé bâtie à l'exécution — t(cle), t('ov.ago' + unite) —"
              " figure forcément ici.")
        print("  À vérifier une par une, jamais à effacer sur la foi de"
              " cette liste.\n")
        for c in jamais_vues:
            print("  " + c)

    if fautes:
        print("\n%d faute(s). Pour recopier les manquantes depuis le français :"
              "\n  python outils/verifier_langues.py --completer" % fautes)
        return 1

    dire("\nLes %d clés des %d langues sont d'accord."
         % (len(ref), len(LANGUES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
