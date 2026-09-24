"""
Hook Claude Code : synchronise automatiquement chaque fichier modifié
vers le serveur AdKyNet (panel Pterodactyl) via SFTP.

Ne fait rien tout seul : Claude Code l'appelle après chaque Edit/Write
(voir .claude/settings.json) en lui passant les infos de l'opération sur
son entrée standard (stdin), au format JSON.

L'hôte, l'utilisateur et les règles d'exclusion vivent dans `adkynet.py`,
partagés avec `sync_all.py` : une seule liste d'exclusions à maintenir.

Pré-requis :
    pip install paramiko

Le mot de passe SFTP ne doit JAMAIS être écrit dans ce fichier. Il est lu
depuis la variable d'environnement ADKYNET_SFTP_PASSWORD, à définir une
fois sur ta machine :

    setx ADKYNET_SFTP_PASSWORD "ton-mot-de-passe"

(puis rouvrir le terminal ; `setx` n'affecte pas la session en cours)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adkynet  # noqa: E402

try:
    import paramiko  # noqa: F401
except ImportError:
    print(
        "[sync] Le module 'paramiko' n'est pas installé — AUCUN envoi. "
        "Lance : pip install paramiko",
        file=sys.stderr,
    )
    sys.exit(0)  # on ne bloque jamais Claude Code pour ça


def main() -> None:
    if not adkynet.password():
        print(
            "[sync] ADKYNET_SFTP_PASSWORD n'est pas défini — AUCUN envoi. "
            'Lance : setx ADKYNET_SFTP_PASSWORD "ton-mot-de-passe" puis '
            "rouvre le terminal.",
            file=sys.stderr,
        )
        return

    # Claude Code envoie les infos de l'événement en JSON sur stdin.
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    local_path = data.get("tool_input", {}).get("file_path")
    if not local_path or not os.path.isfile(local_path):
        return  # rien à envoyer (dossier, fichier supprimé, etc.)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    rel_path = adkynet.to_relative(local_path, project_dir)
    if rel_path.startswith("..") or adkynet.should_skip(rel_path):
        return

    remote_path = "/" + rel_path
    try:
        transport, sftp = adkynet.connect()
        try:
            adkynet.ensure_remote_dir(sftp, remote_path)
            sftp.put(local_path, remote_path)
        finally:
            sftp.close()
            transport.close()
        print(f"[sync] {rel_path} envoyé sur AdKyNet", file=sys.stderr)
    except Exception as e:
        # On ne bloque jamais Claude Code même si l'upload échoue.
        print(f"[sync] Échec de l'envoi de {rel_path} : {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
