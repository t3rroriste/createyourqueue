"""
Envoi complet du projet sur AdKyNet — à lancer à la main.
===========================================================
La veille (`outils/veille.ps1`) envoie au fil de l'eau les fichiers qu'elle
voit changer. Ce script-ci sert aux cas qu'elle ne couvre pas :

- rattraper du code écrit pendant que la synchro était en panne (paramiko
  absent ou mot de passe non défini : le hook se tait et ne renvoie rien) ;
- démarrer depuis un nouveau PC ;
- envoyer des fichiers modifiés à la main, hors de Claude Code.

D'où ce script. Il applique EXACTEMENT les mêmes exclusions que la veille —
elles vivent dans `outils/adkynet.py`, écrites une seule fois — donc ni
`.env`, ni `data/`, ni les dépendances Windows ne partent jamais.

Il n'efface rien à distance : un fichier présent sur AdKyNet mais absent en
local reste en place.

    python outils/publier_bot.py --comparer   # ce que le SERVEUR a et que ce PC n'a pas
    python outils/publier_bot.py --apercu     # lister ce qui partirait, sans envoyer
    python outils/publier_bot.py              # envoyer tout le bot

Lance `--comparer` AVANT le premier envoi depuis une machine neuve. Du code
peut avoir été poussé sur AdKyNet depuis l'autre PC sans jamais passer par
git. Ce mode le montre, avant que l'envoi ne l'écrase.
"""

from __future__ import annotations

import argparse
import os
import sys

# Depuis la réunion des deux dépôts, ce script vit dans `outils/` et le bot
# dans `bot/`. Les chemins envoyés restent relatifs à `bot/` : sur AdKyNet,
# `bot.py` est à la racine du serveur, pas dans un sous-dossier `bot/`.
OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
PROJECT_DIR = os.path.join(RACINE, "bot")
sys.path.insert(0, OUTILS_DIR)

import adkynet  # noqa: E402


def files_to_send() -> list[str]:
    """Les chemins relatifs à envoyer, triés."""
    found: list[str] = []
    for root, dirs, names in os.walk(PROJECT_DIR):
        rel_root = adkynet.to_relative(root, PROJECT_DIR)
        rel_root = "" if rel_root == "." else rel_root + "/"
        # On élague les dossiers exclus au lieu de les parcourir : sur un
        # venv, ce sont des milliers de fichiers inspectés pour rien.
        dirs[:] = [d for d in dirs if not adkynet.should_skip(f"{rel_root}{d}/")]
        for name in names:
            rel = f"{rel_root}{name}"
            if not adkynet.should_skip(rel):
                found.append(rel)
    return sorted(found)


def walk_remote(sftp, base: str = "/") -> dict[str, tuple[int, int]]:
    """Les fichiers présents sur AdKyNet : {chemin relatif: (taille, mtime)}.

    Mêmes exclusions qu'à l'envoi : `data/` et `.env` vivent légitimement
    sur le serveur et n'ont pas à être signalés comme des écarts."""
    import stat as statmod

    found: dict[str, tuple[int, int]] = {}
    a_visiter = [base.rstrip("/") or ""]
    while a_visiter:
        dossier = a_visiter.pop()
        try:
            entrees = sftp.listdir_attr(dossier or "/")
        except OSError:
            continue  # dossier illisible : on l'ignore plutôt que d'échouer
        for entree in entrees:
            chemin = f"{dossier}/{entree.filename}"
            rel = chemin.lstrip("/")
            if statmod.S_ISDIR(entree.st_mode):
                if not adkynet.should_skip(rel + "/"):
                    a_visiter.append(chemin)
            elif not adkynet.should_skip(rel):
                found[rel] = (entree.st_size, entree.st_mtime)
    return found


def ouvrir():
    """Ouvre la connexion, ou explique pourquoi elle échoue.

    Une pile d'appels paramiko de trente lignes ne dit pas quoi corriger :
    dans la quasi-totalité des cas, c'est le mot de passe."""
    import paramiko

    try:
        return adkynet.connect()
    except paramiko.AuthenticationException:
        longueur = len(adkynet.password() or "")
        print(
            f"\nAuthentification refusée par {adkynet.HOST}.\n"
            f"  utilisateur       : {adkynet.USER}\n"
            f"  mot de passe      : {longueur} caractère(s) enregistré(s)\n\n"
            "Sur un panneau Pterodactyl, le mot de passe SFTP est celui de ton\n"
            "COMPTE du panneau, pas un mot de passe distinct. Si le nombre de\n"
            "caractères ci-dessus ne correspond pas au tien, la variable a été\n"
            "tronquée — `setx` coupe sur certains caractères spéciaux. Redéfinis-la\n"
            "sans setx :\n\n"
            '  $s = Read-Host "Mot de passe SFTP" -AsSecureString\n'
            "  $p = [Runtime.InteropServices.Marshal]::PtrToStringBSTR("
            "[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))\n"
            '  [Environment]::SetEnvironmentVariable("ADKYNET_SFTP_PASSWORD", $p, "User")\n\n'
            "puis rouvre le terminal.",
        )
        return None
    except OSError as e:
        print(f"\nConnexion impossible à {adkynet.HOST}:{adkynet.PORT} — {e}")
        return None


def comparer() -> int:
    """Montre ce que le serveur a et que ce PC n'a pas, sans rien modifier."""
    from datetime import datetime

    lien = ouvrir()
    if lien is None:
        return 1
    transport, sftp = lien
    try:
        distant = walk_remote(sftp)
    finally:
        sftp.close()
        transport.close()

    locaux = set(files_to_send())
    print(f"{len(distant)} fichier(s) sur AdKyNet, {len(locaux)} en local.\n")

    orphelins = sorted(set(distant) - locaux)
    print(f"--- Seulement sur AdKyNet : {len(orphelins)} ---")
    if orphelins:
        print("  Du code qui n'est NI ici NI sur GitHub. Sauvegarde-le avant d'envoyer.")
        for rel in orphelins:
            taille, mtime = distant[rel]
            quand = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
            print(f"    {rel}  ({taille} o, modifié le {quand})")
    else:
        print("  (aucun)")

    plus_recents = []
    for rel in sorted(set(distant) & locaux):
        _taille, mtime = distant[rel]
        local_mtime = os.path.getmtime(os.path.join(PROJECT_DIR, rel.replace("/", os.sep)))
        # Deux minutes de marge : les horloges et les horodatages SFTP ne
        # tombent jamais à la seconde près.
        if mtime > local_mtime + 120:
            plus_recents.append((rel, mtime, local_mtime))

    print(f"\n--- Plus récents sur AdKyNet qu'ici : {len(plus_recents)} ---")
    if plus_recents:
        print("  Un envoi les REMPLACERAIT par la version de ce PC.")
        for rel, distant_mtime, local_mtime in plus_recents:
            d = datetime.fromtimestamp(distant_mtime).strftime("%d/%m/%Y %H:%M")
            l = datetime.fromtimestamp(local_mtime).strftime("%d/%m/%Y %H:%M")
            print(f"    {rel}  (serveur {d}, local {l})")
    else:
        print("  (aucun)")

    nouveaux = sorted(locaux - set(distant))
    print(f"\n--- Absents du serveur, seraient ajoutés : {len(nouveaux)} ---")
    for rel in nouveaux[:20]:
        print(f"    {rel}")
    if len(nouveaux) > 20:
        print(f"    … et {len(nouveaux) - 20} autre(s)")

    if orphelins or plus_recents:
        print("\nATTENTION : le serveur a du contenu que ce PC ignore. Récupère-le")
        print("avant de lancer l'envoi (gestionnaire de fichiers du panneau AdKyNet).")
    else:
        print("\nRien sur le serveur qui ne soit pas ici. L'envoi est sans risque.")
    return 0


def verifier_syntaxe(relatifs: list[str]) -> bool:
    """Vrai si tous les .py de la liste compilent.

    Ce contrôle est arrivé avec le redémarrage automatique du bot. Avant
    lui, un fichier cassé déposé sur AdKyNet ne faisait rien : le processus
    en cours gardait l'ancien code jusqu'à ce qu'on le relance à la main, et
    on s'en apercevait en le relançant. Maintenant que la veille relance
    toute seule, le même fichier éteint le bot — et c'est le seul incident
    de cette chaîne qui oblige à ouvrir la console du panneau pour en
    sortir. Deux secondes de lecture ici valent mieux.

    `compile()` ne lit que la syntaxe. Il n'exécute rien et n'importe aucun
    module du bot : ce PC n'a ni les jetons Discord ni les dépendances du
    serveur, et un import les réclamerait.
    """
    mauvais = []
    for rel in relatifs:
        if not rel.endswith(".py"):
            continue
        chemin = os.path.join(PROJECT_DIR, rel.replace("/", os.sep))
        try:
            with open(chemin, encoding="utf-8") as f:
                compile(f.read(), rel, "exec")
        except SyntaxError as e:
            mauvais.append(f"{rel}, ligne {e.lineno} : {e.msg}")
        except OSError as e:
            mauvais.append(f"{rel} : {e}")

    if not mauvais:
        return True
    print("\nRIEN N'A ÉTÉ ENVOYÉ : ces fichiers ne compilent pas.",
          file=sys.stderr)
    for m in mauvais:
        print("  " + m, file=sys.stderr)
    print("\nCorrige-les puis relance. Le bot en ligne n'a pas été touché.",
          file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Envoie tout le projet sur AdKyNet.")
    parser.add_argument("--apercu", action="store_true",
                        help="affiche ce qui partirait, sans rien envoyer")
    parser.add_argument("--comparer", action="store_true",
                        help="montre ce que le serveur a et que ce PC n'a pas")
    # La veille (outils/veille.ps1) sait exactement quels fichiers ont changé :
    # elle les passe ici plutôt que de refaire parcourir les trois cents
    # fichiers du bot à chaque enregistrement. Les chemins sont relatifs à
    # `bot/`, comme ceux que produit `files_to_send()`.
    parser.add_argument("--fichiers", nargs="+", metavar="CHEMIN",
                        help="n'envoie que ces fichiers (relatifs à bot/)")
    args = parser.parse_args()

    if args.fichiers:
        wanted = []
        for rel in args.fichiers:
            rel = rel.replace("\\", "/").lstrip("/")
            if adkynet.should_skip(rel):
                print(f"  ignoré  {rel} (exclusion)")
            elif not os.path.isfile(os.path.join(PROJECT_DIR, rel.replace("/", os.sep))):
                print(f"  absent  {rel}")
            else:
                wanted.append(rel)
        if not wanted:
            print("Rien à envoyer.")
            return 0
    else:
        wanted = files_to_send()
    print(f"{len(wanted)} fichier(s) pour {adkynet.HOST}:{adkynet.PORT}")

    if args.apercu:
        for rel in wanted:
            print(f"  {rel}")
        print("\nAperçu terminé. Relance sans --apercu pour envoyer.")
        return 0

    if not verifier_syntaxe(wanted):
        return 1

    try:
        import paramiko  # noqa: F401
    except ImportError:
        print("Le module 'paramiko' n'est pas installé. Lance : pip install paramiko")
        return 1

    if not adkynet.password():
        print('ADKYNET_SFTP_PASSWORD n\'est pas défini.\n'
              '  setx ADKYNET_SFTP_PASSWORD "ton-mot-de-passe"\n'
              "puis rouvre le terminal.")
        return 1

    if args.comparer:
        return comparer()

    lien = ouvrir()
    if lien is None:
        return 1
    transport, sftp = lien
    sent = failed = 0
    try:
        for rel in wanted:
            remote_path = "/" + rel
            try:
                adkynet.ensure_remote_dir(sftp, remote_path)
                sftp.put(os.path.join(PROJECT_DIR, rel.replace("/", os.sep)), remote_path)
                sent += 1
                print(f"  envoyé  {rel}")
            except Exception as e:
                failed += 1
                print(f"  ÉCHEC   {rel} : {e}")
    finally:
        sftp.close()
        transport.close()

    print(f"\n{sent} envoyé(s), {failed} échec(s).")
    if sent:
        # Les fichiers sont là, le processus en cours garde l'ancien code.
        # La veille s'en charge seule ; à la main, c'est cette commande, qui
        # refuse de couper une queue en cours et vérifie le retour du bot.
        print("Les fichiers sont déposés. Pour que le bot les lise :")
        print("  python outils/redemarrer_bot.py")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
