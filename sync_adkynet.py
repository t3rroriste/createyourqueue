"""
Envoi complet du projet sur AdKyNet — à lancer à la main.
===========================================================
Le hook `.claude/hooks/upload_sftp.py` n'envoie qu'un fichier à la fois,
quand Claude Code le modifie. Il ne sert à rien pour :

- rattraper du code écrit pendant que la synchro était en panne (paramiko
  absent ou mot de passe non défini : le hook se tait et ne renvoie rien) ;
- démarrer depuis un nouveau PC ;
- envoyer des fichiers modifiés à la main, hors de Claude Code.

D'où ce script. Il applique EXACTEMENT les mêmes exclusions que le hook —
elles vivent dans `.claude/hooks/adkynet.py`, écrites une seule fois — donc
ni `.env`, ni `data/`, ni les dépendances Windows ne partent jamais.

Il n'efface rien à distance : un fichier présent sur AdKyNet mais absent en
local reste en place.

    python sync_adkynet.py --comparer   # ce que le SERVEUR a et que ce PC n'a pas
    python sync_adkynet.py --apercu     # lister ce qui partirait, sans envoyer
    python sync_adkynet.py              # envoyer

Lance `--comparer` AVANT le premier envoi depuis une machine. Le hook ne
fonctionne que là où il est configuré : du code peut avoir été poussé sur
AdKyNet depuis un autre PC sans jamais passer par git. Ce mode le montre,
avant que l'envoi ne l'écrase.
"""

from __future__ import annotations

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_DIR, ".claude", "hooks"))

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


def comparer() -> int:
    """Montre ce que le serveur a et que ce PC n'a pas, sans rien modifier."""
    from datetime import datetime

    transport, sftp = adkynet.connect()
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Envoie tout le projet sur AdKyNet.")
    parser.add_argument("--apercu", action="store_true",
                        help="affiche ce qui partirait, sans rien envoyer")
    parser.add_argument("--comparer", action="store_true",
                        help="montre ce que le serveur a et que ce PC n'a pas")
    args = parser.parse_args()

    wanted = files_to_send()
    print(f"{len(wanted)} fichier(s) pour {adkynet.HOST}:{adkynet.PORT}")

    if args.apercu:
        for rel in wanted:
            print(f"  {rel}")
        print("\nAperçu terminé. Relance sans --apercu pour envoyer.")
        return 0

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

    transport, sftp = adkynet.connect()
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
        print("Redémarre le bot depuis le panneau AdKyNet pour appliquer.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
