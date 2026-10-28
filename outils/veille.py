"""
La veille : les deux PC et les deux hébergeurs à jour, sans rien taper.
=======================================================================
Un passage, toutes les trente secondes :

  1. si une feuille ou un script du site a changé, renuméroter les `?v=`
     AVANT d'enregistrer — sinon le numéro change à chaque publication et
     la boucle s'auto-alimente, un commit toutes les trente secondes pour
     l'éternité ;
  2. enregistrer, récupérer, pousser (`synchro_git.py`) ;
  3. publier ce qui a changé depuis la dernière publication réussie :
     `site/` part sur LWS, `bot/` part sur AdKyNet.

    python outils/veille.py                  # la boucle, 30 s
    python outils/veille.py --intervalle 120 # plus calme
    python outils/veille.py --une-fois       # un seul passage
    python outils/veille.py --sans-publier   # git seulement, rien en ligne

Pourquoi « depuis la dernière publication réussie » et non « depuis le
dernier passage » : si l'hébergeur est injoignable pendant une heure, les
fichiers de cette heure doivent partir au retour du réseau. Un décompte par
passage les perdrait. La référence est donc le dernier commit RÉELLEMENT
publié, gardé dans `outils/etat/dernier-publie.txt`.

Deux garde-fous, parce qu'une boucle qui publie toute seule doit savoir
s'arrêter :

  - un conflit entre les deux PC pose `outils/etat/conflit` et suspend tout.
    Rien ne part en ligne tant qu'un humain n'a pas tranché ;
  - `cyq pause` pose `outils/etat/pause` : la synchro git continue, la mise
    en ligne attend. C'est ce qu'on veut en pleine refonte d'une page.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
ETAT = os.path.join(OUTILS_DIR, "etat")

sys.path.insert(0, OUTILS_DIR)
import synchro_git  # noqa: E402

JOURNAL = os.path.join(ETAT, "journal.log")
DERNIER_PUBLIE = os.path.join(ETAT, "dernier-publie.txt")
CONFLIT = os.path.join(ETAT, "conflit")
PAUSE = os.path.join(ETAT, "pause")


# ----------------------------------------------------------------- état ---

def _assurer_etat() -> None:
    os.makedirs(ETAT, exist_ok=True)


def dire(texte: str, *, journal: bool = True) -> None:
    """À l'écran et dans le journal. La veille tourne souvent sans fenêtre
    visible : sans trace écrite, un échec d'il y a deux heures est invisible."""
    quand = datetime.now().strftime("%d/%m %H:%M:%S")
    print(f"[{quand}] {texte}", flush=True)
    if journal:
        _assurer_etat()
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(f"[{quand}] {texte}\n")


def lire_marque(chemin: str) -> str | None:
    try:
        with open(chemin, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def ecrire_marque(chemin: str, contenu: str = "") -> None:
    _assurer_etat()
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)


# ----------------------------------------------------------- numérotation ---

def site_touche(exe: str) -> bool:
    """Vrai si une page, une feuille ou un script du site attend d'être
    enregistré. Seul ce cas justifie de renuméroter les `?v=`."""
    etat = synchro_git.git(exe, "status", "--porcelain", "--", "site")
    for ligne in etat.stdout.splitlines():
        chemin = ligne[3:].strip().strip('"')
        if chemin.endswith((".html", ".css", ".js")):
            return True
    return False


def numeroter() -> None:
    script = os.path.join(OUTILS_DIR, "numeroter-versions.ps1")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


# -------------------------------------------------------------- publication ---

def changements_a_publier(exe: str) -> list[str]:
    """Les chemins modifiés depuis la dernière publication réussie."""
    depuis = lire_marque(DERNIER_PUBLIE)
    tete = synchro_git.git(exe, "rev-parse", "HEAD").stdout.strip()
    if not depuis:
        # Première publication depuis cette machine : on ne devine pas, on
        # prend tout. `publier-site.ps1` envoie de toute façon la liste
        # complète, et `publier-bot.py` sans --fichiers aussi.
        return ["*"]
    if depuis == tete:
        return []
    res = synchro_git.git(exe, "diff", "--name-only", f"{depuis}..{tete}")
    if res.returncode != 0:
        # Le commit de référence a disparu (historique réécrit) : on repart
        # d'une publication complète plutôt que de ne rien publier.
        return ["*"]
    return [l.strip() for l in res.stdout.splitlines() if l.strip()]


def publier_site() -> bool:
    script = os.path.join(OUTILS_DIR, "publier-site.ps1")
    # -NoBump : les `?v=` ont déjà été posés avant le commit, et les reposer
    # ici ferait repartir la boucle.
    res = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-NoBump"],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if res.returncode == 0:
        dire("Site publié sur LWS.")
        return True
    derniere = (res.stdout or res.stderr).strip().splitlines()
    dire("Site NON publié sur LWS — " + (derniere[-1] if derniere else "cause inconnue"))
    return False


def publier_bot(fichiers: list[str] | None) -> bool:
    script = os.path.join(OUTILS_DIR, "publier-bot.py")
    commande = [sys.executable, script]
    if fichiers:
        commande += ["--fichiers", *fichiers]
    res = subprocess.run(
        commande, cwd=RACINE, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if res.returncode == 0:
        combien = len(fichiers) if fichiers else "tous les"
        dire(f"Bot publié sur AdKyNet ({combien} fichier(s)). "
             "Redémarre-le depuis le panneau pour appliquer.")
        return True
    derniere = (res.stdout or res.stderr).strip().splitlines()
    dire("Bot NON publié sur AdKyNet — " + (derniere[-1] if derniere else "cause inconnue"))
    return False


def publier(exe: str) -> None:
    if os.path.exists(PAUSE):
        dire("Publication en pause (cyq reprendre pour la relancer).", journal=False)
        return

    chemins = changements_a_publier(exe)
    if not chemins:
        return

    tout = chemins == ["*"]
    du_site = tout or any(c.startswith("site/") for c in chemins)
    # Les chemins du bot sont relatifs à `bot/` côté AdKyNet : `bot/bot.py`
    # s'y appelle `bot.py`. On retire le préfixe ici, une fois.
    du_bot = [] if tout else [c[len("bot/"):] for c in chemins if c.startswith("bot/")]

    if not du_site and not du_bot and not tout:
        # Seuls des outils, des notes ou des réglages ont changé : rien à
        # mettre en ligne, mais la référence avance quand même.
        ecrire_marque(DERNIER_PUBLIE, synchro_git.git(exe, "rev-parse", "HEAD").stdout.strip())
        return

    ok = True
    if du_site:
        ok = publier_site() and ok
    if du_bot or tout:
        ok = publier_bot(du_bot or None) and ok

    if ok:
        ecrire_marque(DERNIER_PUBLIE, synchro_git.git(exe, "rev-parse", "HEAD").stdout.strip())
    else:
        dire("La référence de publication n'avance pas : le prochain passage réessaiera.")


# ------------------------------------------------------------------ passage ---

def un_passage(exe: str, avec_publication: bool) -> None:
    if os.path.exists(CONFLIT):
        dire("Conflit non réglé — la veille ne touche plus à rien.\n"
             "  git pull --rebase, règle les conflits, puis : cyq reprendre",
             journal=False)
        return

    if site_touche(exe):
        numeroter()

    r = synchro_git.passage(exe)

    if r.conflit:
        ecrire_marque(CONFLIT, "\n".join(r.erreurs))
        dire("CONFLIT entre les deux PC. Rien n'est perdu, rien n'est publié.")
        for e in r.erreurs:
            dire("  " + e.replace("\n", "\n  "))
        return

    for ligne in r.lignes:
        dire(ligne)
    for e in r.erreurs:
        dire("ERREUR : " + e)
    if r.erreurs:
        return

    if avec_publication:
        publier(exe)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchro continue des deux PC et des hébergeurs.")
    parser.add_argument("--intervalle", type=int, default=30,
                        help="secondes entre deux passages (défaut : 30)")
    parser.add_argument("--une-fois", action="store_true", help="un seul passage, puis on sort")
    parser.add_argument("--sans-publier", action="store_true",
                        help="synchronise git, mais ne met rien en ligne")
    args = parser.parse_args()

    exe = synchro_git._git_exe()
    if exe is None:
        print("git introuvable.", file=sys.stderr)
        return 1
    if not os.path.isdir(os.path.join(RACINE, ".git")):
        print(f"{RACINE} n'est pas un dépôt git.", file=sys.stderr)
        return 1

    if args.une_fois:
        un_passage(exe, not args.sans_publier)
        return 0

    dire(f"Veille lancée — un passage toutes les {args.intervalle} s. Ctrl+C pour arrêter.")
    try:
        while True:
            try:
                un_passage(exe, not args.sans_publier)
            except Exception as e:  # une boucle de fond ne meurt pas sur une exception
                dire(f"Incident pendant le passage : {e!r}")
            time.sleep(args.intervalle)
    except KeyboardInterrupt:
        dire("Veille arrêtée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
