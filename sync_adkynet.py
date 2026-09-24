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

    python sync_adkynet.py --apercu     # lister sans rien envoyer
    python sync_adkynet.py              # envoyer
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Envoie tout le projet sur AdKyNet.")
    parser.add_argument("--apercu", action="store_true",
                        help="affiche la liste sans rien envoyer")
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
