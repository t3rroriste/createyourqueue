"""
Enregistre le travail sur GitHub — automatiquement, en fin de tâche.
======================================================================
Claude Code l'appelle par le hook `Stop` (voir .claude/settings.json), donc
une fois par tâche terminée, et non à chaque fichier : un commit par
fonctionnalité plutôt que trois cents commits d'une ligne.

Il marche aussi à la main, pour les modifications faites hors de Claude :

    python sync_git.py --apercu     # ce qui serait enregistré
    python sync_git.py              # commit + push

Pourquoi c'est là : pendant une semaine, le hook SFTP a envoyé du code sur
AdKyNet sans que rien ne passe par git. Cinq jours de travail n'existaient
plus que sur l'hébergeur. Ce script ferme ce trou — GitHub devient la
référence, et un autre PC n'a qu'à cloner.

Il ne force jamais rien. Si le dépôt distant a avancé (travail poussé depuis
une autre machine), le push est refusé et le script le DIT, au lieu de
tenter un rebase automatique qui laisserait le dépôt à moitié fusionné.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

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
            subprocess.run([chemin, "--version"], capture_output=True, check=True)
            return chemin
        except (OSError, subprocess.CalledProcessError):
            continue
    return None


def git(exe: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [exe, *args], cwd=PROJECT_DIR, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def message(fichiers: list[str]) -> str:
    """Un message honnête : on ne sait pas ce qui a été fait, on dit quoi a changé."""
    quand = datetime.now().strftime("%d/%m/%Y %H:%M")
    if len(fichiers) <= 6:
        detail = ", ".join(fichiers)
    else:
        detail = ", ".join(fichiers[:6]) + f" et {len(fichiers) - 6} autre(s)"
    return f"Enregistrement automatique du {quand}\n\n{len(fichiers)} fichier(s) : {detail}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Commit et push vers GitHub.")
    parser.add_argument("--apercu", action="store_true",
                        help="montre ce qui serait enregistré, sans rien faire")
    args = parser.parse_args()

    exe = _git_exe()
    if exe is None:
        print("[git] git introuvable — rien d'enregistré.", file=sys.stderr)
        return 0

    if not os.path.isdir(os.path.join(PROJECT_DIR, ".git")):
        print("[git] pas un dépôt git — rien d'enregistré.", file=sys.stderr)
        return 0

    etat = git(exe, "status", "--porcelain")
    if etat.returncode != 0:
        print(f"[git] statut illisible : {etat.stderr.strip()}", file=sys.stderr)
        return 0

    fichiers = [ligne[3:].strip().strip('"') for ligne in etat.stdout.splitlines() if ligne.strip()]
    if not fichiers:
        if args.apercu:
            print("Rien à enregistrer.")
        return 0

    if args.apercu:
        print(f"{len(fichiers)} fichier(s) seraient enregistrés :")
        for f in fichiers:
            print(f"  {f}")
        print("\n" + message(fichiers).splitlines()[0])
        return 0

    ajout = git(exe, "add", "-A")
    if ajout.returncode != 0:
        print(f"[git] add impossible : {ajout.stderr.strip()}", file=sys.stderr)
        return 0

    commit = git(exe, "commit", "-m", message(fichiers))
    if commit.returncode != 0:
        # « nothing to commit » n'est pas une erreur : tout était peut-être
        # déjà enregistré par un commit écrit à la main juste avant.
        if "nothing to commit" not in (commit.stdout + commit.stderr).lower():
            print(f"[git] commit impossible : {commit.stderr.strip()}", file=sys.stderr)
        return 0

    push = git(exe, "push")
    sortie = (push.stdout + push.stderr).strip()

    # Une branche créée en local n'a pas encore de branche amont : ce n'est
    # pas un conflit, juste un premier push. On le fait, sans rien écraser.
    if push.returncode != 0 and "no upstream branch" in sortie:
        branche = git(exe, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        push = git(exe, "push", "--set-upstream", "origin", branche)
        sortie = (push.stdout + push.stderr).strip()

    if push.returncode != 0:
        print(f"[git] {len(fichiers)} fichier(s) enregistrés en local, mais le push a échoué.",
              file=sys.stderr)
        if "rejected" in sortie or "non-fast-forward" in sortie or "fetch first" in sortie:
            # Volontairement pas de rebase automatique : un conflit laisserait
            # le dépôt à moitié fusionné, sans personne pour le voir.
            print("[git] Le dépôt distant a avancé — quelqu'un a poussé depuis "
                  "une autre machine.\n"
                  "[git] Récupère d'abord : git pull --rebase, puis git push.",
                  file=sys.stderr)
        else:
            print(f"[git] {sortie}", file=sys.stderr)
        return 0

    print(f"[git] {len(fichiers)} fichier(s) poussés sur GitHub.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
