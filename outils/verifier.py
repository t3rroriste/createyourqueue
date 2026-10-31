"""
Les trois relevés d'un coup — `cyq verifier`.
=============================================
Pourquoi : chacun des trois surveille un endroit où la même chose
s'écrit à deux places, et où rien ne proteste quand les deux divergent.
Séparés, ils ne servent qu'à qui se souvient qu'ils existent ; c'est
précisément ce qu'on ne fait pas avant de mettre en ligne.

    python outils/verifier.py        (ou : cyq verifier)
    python outils/verifier.py --silencieux

Il ne corrige rien, et c'est voulu : les deux gestes qui réparent —
`fragments.py` et `verifier_langues.py --completer` — réécrivent des
fichiers, et une commande qui s'appelle « vérifier » n'a pas à toucher
au dépôt. Elle dit quoi lancer.

`publier_site.py` lance les mêmes contrôles de son côté, et avertit sans
bloquer. Ici le code de sortie compte : il vaut le nombre de relevés en
faute, pour qu'un enchaînement puisse s'arrêter dessus.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)

# Les filets `──` et les accents ne passent pas en cp1252, et c'est en
# cp1252 que Python écrit dès que sa sortie part ailleurs que sur la
# console — un tuyau, un `> fichier`, un journal. La commande mourait donc
# exactement là où on l'enchaîne, ce qui est précisément ce pour quoi elle
# rend un code de sortie. Les trois enfants écrivent sur la même sortie :
# ils reçoivent la même consigne par l'environnement.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
ENV = dict(os.environ, PYTHONIOENCODING="utf-8:replace")

# Dans cet ordre : du plus mécanique au plus réfléchi. Un bloc commun qui
# a dérivé se répare par une commande, une clé de langue par une commande
# aussi, mais un réglage qui n'atteint pas le bot demande de décider
# quelque chose — autant l'avoir sous les yeux en dernier.
RELEVES = [
    ("Les blocs communs", "fragments.py", ["--verifier"],
     "python outils/fragments.py"),
    ("Les cinq langues", "verifier_langues.py", [],
     "python outils/verifier_langues.py --completer"),
    ("Le panneau et les deux API", "verifier_api.py", [],
     "python outils/verifier_api.py"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--silencieux", action="store_true",
                    help="ne dit rien quand les trois relevés passent")
    args = ap.parse_args()

    fautifs = []
    for titre, script, options, reparer in RELEVES:
        # Le titre AVANT l'appel, et vidé tout de suite : sans le flush,
        # le tampon du parent sort après les trois enfants, et on se
        # retrouve avec les trois relevés en vrac puis leurs trois titres
        # à la fin. L'enfant écrit sur le même terminal, pas dans un tuyau
        # qu'on relirait — c'est à nous de ne pas passer devant lui.
        if not args.silencieux:
            print("── %s %s" % (titre, "─" * max(0, 56 - len(titre))),
                  flush=True)
        sortie = subprocess.run(
            [sys.executable, os.path.join(OUTILS_DIR, script)]
            + options + (["--silencieux"] if args.silencieux else []),
            cwd=RACINE, env=ENV,
        )
        if sortie.returncode:
            fautifs.append((titre, reparer))
        if not args.silencieux:
            print(flush=True)

    if not fautifs:
        if not args.silencieux:
            print("Les trois relevés passent.")
        return 0

    print("%d relevé(s) en faute :" % len(fautifs))
    for titre, reparer in fautifs:
        print("  %-28s %s" % (titre, reparer))
    return len(fautifs)


if __name__ == "__main__":
    sys.exit(main())
