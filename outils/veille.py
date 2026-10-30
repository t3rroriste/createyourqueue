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
# Un redémarrage du bot est dû. Une marque sur le disque et non une variable :
# une queue en cours fait attendre le redémarrage, et cette attente doit
# survivre à l'arrêt de la veille. Sinon un bot redémarré « plus tard » ne
# l'est jamais, et personne ne s'en aperçoit — il tourne.
REDEMARRAGE = os.path.join(ETAT, "redemarrage-du")


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
    subprocess.run(
        [sys.executable, os.path.join(OUTILS_DIR, "numeroter_versions.py"), "--silencieux"],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


# -------------------------------------------------------------- publication ---

def changements_a_publier(exe: str) -> list[str]:
    """Les chemins modifiés depuis la dernière publication réussie."""
    depuis = lire_marque(DERNIER_PUBLIE)
    tete = synchro_git.git(exe, "rev-parse", "HEAD").stdout.strip()
    if not depuis:
        # Première publication depuis cette machine : on ne devine pas, on
        # prend tout. `publier_site.py` envoie de toute façon la liste
        # complète, et `publier_bot.py` sans --fichiers aussi.
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
    # --sans-numerotation : les `?v=` ont déjà été posés avant le commit, et
    # les reposer ici ferait repartir la boucle.
    res = subprocess.run(
        [sys.executable, os.path.join(OUTILS_DIR, "publier_site.py"), "--sans-numerotation"],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if res.returncode == 0:
        dire("Site publié sur LWS.")
        return True
    derniere = (res.stdout or res.stderr).strip().splitlines()
    dire("Site NON publié sur LWS — " + (derniere[-1] if derniere else "cause inconnue"))
    return False


def publier_bot(fichiers: list[str] | None) -> bool:
    script = os.path.join(OUTILS_DIR, "publier_bot.py")
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
    bot_publie = False
    if du_site:
        ok = publier_site() and ok
    if du_bot or tout:
        bot_publie = publier_bot(du_bot or None)
        ok = bot_publie and ok

    # Les fichiers sont déposés, mais le processus en cours garde l'ancien
    # code en mémoire : tant qu'il n'est pas relancé, la publication n'a rien
    # changé pour personne. On note donc que le redémarrage est dû, et c'est
    # `redemarrage_du()` qui s'en charge — tout de suite, ou dans une heure
    # si une queue est en cours.
    if bot_publie:
        ecrire_marque(REDEMARRAGE,
                      synchro_git.git(exe, "rev-parse", "HEAD").stdout.strip())

    if ok:
        ecrire_marque(DERNIER_PUBLIE, synchro_git.git(exe, "rev-parse", "HEAD").stdout.strip())
    else:
        dire("La référence de publication n'avance pas : le prochain passage réessaiera.")


# ----------------------------------------------------------- redémarrage ---

# Après un échec, on laisse passer ce délai avant de réessayer. Sans lui, un
# bot qui refuse de repartir ferait écrire une ligne d'échec toutes les
# trente secondes : au bout d'une nuit, le journal ne contiendrait plus que
# ça et la ligne utile y serait introuvable.
ECHEC_ATTENTE = 300


def redemarrage_du() -> None:
    """Relance le bot s'il a reçu du code neuf.

    HISTOIRE, parce qu'elle explique chaque garde-fou qui suit. Ce
    redémarrage automatique a été écrit le 30 octobre 2026, et son premier
    vrai essai a mis le bot à terre : la relance lisait
    `sys.flags.unbuffered`, qui n'existe pas, et mourait sur cet attribut
    juste après avoir fermé la passerelle Discord, sans jamais atteindre
    `os.execv`. Le processus est sorti proprement, et le panneau marque
    « éteint » un serveur qui sort proprement. Il a fallu le relancer à la
    main.

    L'appel a donc été coupé, le temps que le geste fasse ses preuves à la
    main — deux fois de suite, le même jour, dont une avec la vérification
    améliorée. Il est revenu ici ensuite, mais entouré : un `.py` qui ne
    compile pas ne part plus (`publier_bot.verifier_syntaxe`), une queue en
    cours fait répondre 409 au bot, et `redemarrer_bot.py` n'annonce le
    retour que quand la passerelle Discord est reconnectée — pas quand le
    port répond.

    Tenté à CHAQUE passage, et pas une seule fois après la publication : une
    queue en cours reporte, et ce report doit être repris plus tard. Tant que
    la marque est là, on redemande.

    La pause est respectée : `cyq pause` veut dire « la mise en ligne
    attend », et un redémarrage est le dernier geste de la mise en ligne.
    """
    if not os.path.exists(REDEMARRAGE) or os.path.exists(PAUSE):
        return

    # La marque porte le commit publié, et sur une deuxième ligne l'heure du
    # dernier échec s'il y en a eu un.
    lignes = (lire_marque(REDEMARRAGE) or "").splitlines()
    tete = lignes[0] if lignes else ""
    try:
        dernier_echec = float(lignes[1]) if len(lignes) > 1 else 0.0
    except ValueError:
        dernier_echec = 0.0
    if dernier_echec and time.time() - dernier_echec < ECHEC_ATTENTE:
        return

    res = subprocess.run(
        [sys.executable, os.path.join(OUTILS_DIR, "redemarrer_bot.py")],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )

    if res.returncode == 0:
        try:
            os.remove(REDEMARRAGE)
        except OSError:
            pass
        dire("Bot redémarré : il tourne sur le code publié, et il est "
             "connecté à Discord.")
        return

    if res.returncode == 2:
        # Une queue est en cours : ce n'est pas un échec, c'est une attente.
        # Pas de délai — dès que la partie se termine, le passage suivant
        # relance. Mais rien dans le journal : à trente secondes
        # d'intervalle, une partie d'une heure y écrirait cent vingt lignes
        # identiques.
        dire("Redémarrage du bot en attente — une queue est en cours.",
             journal=False)
        return

    derniere = (res.stdout or res.stderr).strip().splitlines()
    ecrire_marque(REDEMARRAGE, tete + "\n" + str(time.time()))
    dire("Bot NON redémarré — " + (derniere[-1] if derniere else "cause inconnue")
         + f" (nouvel essai dans {ECHEC_ATTENTE // 60} min)")


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
        redemarrage_du()


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
