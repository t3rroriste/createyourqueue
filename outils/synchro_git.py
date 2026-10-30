"""
Le moteur de la synchro : enregistre, récupère, pousse.
======================================================
Un passage = trois gestes, toujours dans cet ordre :

  1. enregistrer ce que CE PC a changé (add -A puis commit) ;
  2. récupérer ce que l'AUTRE PC a poussé (pull --rebase) ;
  3. pousser le tout sur GitHub.

L'ordre compte. Enregistrer avant de récupérer évite le « vous avez des
modifications locales » qui bloque un pull ; rebaser plutôt que fusionner
évite un commit de fusion toutes les trente secondes, qui rendrait
l'historique illisible en une journée.

GitHub est la référence, pas l'hébergeur. Pendant une semaine, le code
partait sur AdKyNet sans passer par git : cinq jours de travail n'ont existé
que sur l'hébergeur. Ici, rien ne part en ligne avant d'être enregistré.

    python outils/synchro-git.py --apercu    # ce qui serait enregistré
    python outils/synchro-git.py             # enregistre, récupère, pousse
    python outils/synchro-git.py --rapport   # idem, mais la sortie est du JSON

En cas de conflit, le script N'INVENTE RIEN : il annule le rebase, laisse le
dépôt exactement comme il était, et le dit. Un rebase à moitié appliqué dans
une boucle automatique est le seul moyen sûr de perdre du travail.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)

sys.path.insert(0, OUTILS_DIR)
import sans_fenetre  # noqa: E402

# Git n'est pas toujours dans le PATH d'un processus lancé avant son
# installation : on le cherche aussi là où l'installeur Windows le met.
CHEMINS_GIT = (
    "git",
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files (x86)\Git\cmd\git.exe",
)


def _git_exe() -> str | None:
    for chemin in CHEMINS_GIT:
        try:
            subprocess.run([chemin, "--version"], capture_output=True, check=True,
                           creationflags=sans_fenetre.DRAPEAU)
            return chemin
        except (OSError, subprocess.CalledProcessError):
            continue
    return None


def git(exe: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [exe, *args], cwd=RACINE, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        # Sous `pythonw`, chaque appel à git ouvrirait sa propre fenêtre de
        # console. Une dizaine par passage, un passage toutes les trente
        # secondes : le bureau clignotait sans arrêt.
        creationflags=sans_fenetre.DRAPEAU,
    )


def message(fichiers: list[str]) -> str:
    """Un message honnête : on ne sait pas ce qui a été fait, on dit quoi a changé.

    Le nom de la machine y figure : en relisant l'historique à deux PC, la
    première question est toujours « ça vient d'où ? »."""
    quand = datetime.now().strftime("%d/%m/%Y %H:%M")
    ou = socket.gethostname()
    if len(fichiers) <= 6:
        detail = ", ".join(fichiers)
    else:
        detail = ", ".join(fichiers[:6]) + f" et {len(fichiers) - 6} autre(s)"
    return f"Synchro automatique — {ou}, {quand}\n\n{len(fichiers)} fichier(s) : {detail}"


class Rapport:
    """Ce qu'un passage a fait. `veille.py` le lit pour savoir quoi publier."""

    def __init__(self) -> None:
        self.enregistres: list[str] = []   # fichiers commités par ce PC
        self.recus = 0                     # commits ramenés de l'autre PC
        self.pousses = False
        self.conflit = False
        self.tete_avant = ""
        self.tete_apres = ""
        self.erreurs: list[str] = []
        self.lignes: list[str] = []        # ce qu'on dit à l'écran

    def dire(self, texte: str) -> None:
        self.lignes.append(texte)

    def en_json(self) -> str:
        return json.dumps({
            "enregistres": self.enregistres,
            "recus": self.recus,
            "pousses": self.pousses,
            "conflit": self.conflit,
            "tete_avant": self.tete_avant,
            "tete_apres": self.tete_apres,
            "erreurs": self.erreurs,
        }, ensure_ascii=False)


def tete(exe: str) -> str:
    return git(exe, "rev-parse", "HEAD").stdout.strip()


def branche(exe: str) -> str:
    return git(exe, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def amont(exe: str) -> str:
    """Le dernier commit connu de la branche distante, ou '' s'il n'y en a pas."""
    res = git(exe, "rev-parse", "@{upstream}")
    return res.stdout.strip() if res.returncode == 0 else ""


def passage(exe: str) -> Rapport:
    r = Rapport()
    r.tete_avant = r.tete_apres = tete(exe)

    # On relève où en était le distant AVANT de le consulter : c'est la seule
    # façon de compter honnêtement ce qui vient de l'autre PC. Après un
    # rebase, les commits locaux changent d'identifiant et tout décompte pris
    # sur HEAD gonfle de nos propres commits.
    distant_avant = amont(exe)
    git(exe, "fetch", "--quiet")
    distant_apres = amont(exe)
    if distant_avant and distant_apres and distant_avant != distant_apres:
        compte = git(exe, "rev-list", "--count", f"{distant_avant}..{distant_apres}")
        r.recus = int((compte.stdout.strip() or "0"))

    # --- 1. enregistrer ce que ce PC a changé ----------------------------
    etat = git(exe, "status", "--porcelain")
    if etat.returncode != 0:
        r.erreurs.append(f"statut illisible : {etat.stderr.strip()}")
        return r

    fichiers = [l[3:].strip().strip('"') for l in etat.stdout.splitlines() if l.strip()]
    if fichiers:
        ajout = git(exe, "add", "-A")
        if ajout.returncode != 0:
            r.erreurs.append(f"add impossible : {ajout.stderr.strip()}")
            return r
        commit = git(exe, "commit", "-m", message(fichiers))
        if commit.returncode != 0:
            sortie = (commit.stdout + commit.stderr).lower()
            # « nothing to commit » n'est pas une erreur : un commit écrit à la
            # main juste avant a pu tout prendre.
            if "nothing to commit" not in sortie:
                r.erreurs.append(f"commit impossible : {commit.stderr.strip()}")
                return r
        else:
            r.enregistres = fichiers
            r.dire(f"{len(fichiers)} fichier(s) enregistré(s).")

    # --- 2. récupérer ce que l'autre PC a poussé -------------------------
    #
    # On ne rebase QUE si le distant a vraiment avancé. Un `pull --rebase`
    # lancé alors qu'on est seulement en avance n'est pas l'opération vide
    # qu'on imagine : git rejoue nos commits sur le distant et APLATIT les
    # fusions au passage. L'historique contient une fusion (la réunion des
    # deux dépôts) ; la rejouer ressortait le conflit déjà réglé, toutes les
    # trente secondes.
    #
    # Et quand il faut rebaser, `--rebase=merges` garde les fusions telles
    # quelles au lieu de les défaire.
    retard = git(exe, "rev-list", "--count", "HEAD..@{upstream}")
    en_retard = retard.returncode == 0 and (retard.stdout.strip() or "0") != "0"

    pull = (git(exe, "pull", "--rebase=merges", "--autostash", "--quiet")
            if en_retard else
            subprocess.CompletedProcess([], 0, "", ""))
    if pull.returncode != 0:
        sortie = (pull.stdout + pull.stderr).strip()
        # Un rebase interrompu laisse le dépôt dans un état intermédiaire.
        # On le défait : mieux vaut deux versions côte à côte qu'un dépôt à
        # moitié fusionné pendant que la boucle continue de tourner.
        if os.path.isdir(os.path.join(RACINE, ".git", "rebase-merge")) or \
           os.path.isdir(os.path.join(RACINE, ".git", "rebase-apply")):
            git(exe, "rebase", "--abort")
            r.conflit = True
            r.erreurs.append(
                "Les deux PC ont modifié les mêmes lignes. Le rebase a été annulé, "
                "rien n'est perdu.\n"
                "  À faire une fois, à la main :  git pull --rebase\n"
                "  puis régler les conflits, puis :  cyq reprendre"
            )
            return r
        # Pas de branche amont : premier passage sur une branche neuve.
        if "no tracking information" in sortie.lower() or "no such ref" in sortie.lower():
            r.dire("Pas encore de branche amont — on pousse pour la créer.")
        else:
            r.erreurs.append(f"récupération impossible : {sortie}")
            return r
    elif r.recus:
        r.dire(f"{r.recus} commit(s) récupéré(s) de l'autre machine.")

    # --- 3. pousser ------------------------------------------------------
    besoin = git(exe, "rev-list", "--count", "@{upstream}..HEAD")
    a_pousser = besoin.returncode != 0 or (besoin.stdout.strip() or "0") != "0"
    if a_pousser:
        push = git(exe, "push")
        sortie = (push.stdout + push.stderr).strip()
        if push.returncode != 0 and "no upstream branch" in sortie:
            push = git(exe, "push", "--set-upstream", "origin", branche(exe))
            sortie = (push.stdout + push.stderr).strip()
        if push.returncode != 0:
            r.erreurs.append(f"push refusé : {sortie}")
        else:
            r.pousses = True
            r.dire("Poussé sur GitHub.")

    r.tete_apres = tete(exe)
    return r


def main() -> int:
    parser = argparse.ArgumentParser(description="Enregistre, récupère et pousse.")
    parser.add_argument("--apercu", action="store_true",
                        help="montre ce qui serait enregistré, sans rien faire")
    parser.add_argument("--rapport", action="store_true",
                        help="écrit un rapport JSON sur la sortie standard")
    args = parser.parse_args()

    exe = _git_exe()
    if exe is None:
        print("git introuvable — rien n'a été fait.", file=sys.stderr)
        return 1
    if not os.path.isdir(os.path.join(RACINE, ".git")):
        print(f"{RACINE} n'est pas un dépôt git.", file=sys.stderr)
        return 1

    if args.apercu:
        etat = git(exe, "status", "--porcelain")
        fichiers = [l[3:].strip().strip('"') for l in etat.stdout.splitlines() if l.strip()]
        if not fichiers:
            print("Rien à enregistrer.")
            return 0
        print(f"{len(fichiers)} fichier(s) seraient enregistrés :")
        for f in fichiers:
            print(f"  {f}")
        print("\n" + message(fichiers).splitlines()[0])
        return 0

    r = passage(exe)

    if args.rapport:
        print(r.en_json())
    else:
        for ligne in r.lignes:
            print(ligne)
        for e in r.erreurs:
            print(e, file=sys.stderr)
        if not r.lignes and not r.erreurs:
            print("Déjà à jour.")
    return 1 if (r.erreurs or r.conflit) else 0


if __name__ == "__main__":
    raise SystemExit(main())
