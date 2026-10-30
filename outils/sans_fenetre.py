"""
Lancer git, curl ou powershell sans faire clignoter une fenêtre.
================================================================
La veille tourne sous `pythonw.exe`, choisi exprès pour qu'elle ne montre
rien pendant qu'elle travaille. Mais `pythonw` n'a PAS de console, et quand
un processus sans console lance un programme console — git, curl,
powershell — Windows lui en crée une, visible, au premier plan.

Rediriger la sortie n'y change rien : la fenêtre est créée par Windows avant
que le programme ait écrit quoi que ce soit. Et le compte monte vite. Un
passage de veille, c'est une dizaine d'appels à git toutes les trente
secondes ; une publication du site, c'est un appel à `curl` PAR FICHIER —
soixante-treize fenêtres qui clignotent l'une après l'autre sur le bureau.

`CREATE_NO_WINDOW` le dit à Windows une bonne fois. Ailleurs, le drapeau
n'existe pas : il vaut 0, et `subprocess` accepte 0 sur tous les systèmes.

À n'utiliser QUE là où la sortie est capturée ou jetée. Un programme qu'on
veut voir écrire dans le terminal — `pip install` pendant `cyq amorcer` —
doit garder la console dont il hérite.

    import sans_fenetre
    subprocess.run(commande, capture_output=True,
                   creationflags=sans_fenetre.DRAPEAU)
"""

from __future__ import annotations

import subprocess
import sys

# getattr : la constante n'existe que sur Windows, et seulement depuis
# Python 3.7. Sur un Mac, et sur un Python plus ancien, elle vaut 0 — ce que
# subprocess traite comme « aucun drapeau particulier ».
DRAPEAU = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
           if sys.platform == "win32" else 0)
