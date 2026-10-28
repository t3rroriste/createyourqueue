"""
Hook Claude Code : synchronise automatiquement chaque fichier modifié
vers le serveur AdKyNet (panel Pterodactyl) via SFTP.

Ne fait rien tout seul : Claude Code l'appelle après chaque Edit/Write
(voir .claude/settings.json) en lui passant les infos de l'opération sur
son entrée standard (stdin), au format JSON.

Pré-requis :
    pip install paramiko

Le mot de passe SFTP ne doit JAMAIS être écrit dans ce fichier. Il est lu
depuis la variable d'environnement ADKYNET_SFTP_PASSWORD, à définir une
fois sur ta machine (voir les instructions données à côté de ce fichier).
"""

import sys
import os
import json

try:
    import paramiko
except ImportError:
    print(
        "[sync] Le module 'paramiko' n'est pas installé. "
        "Lance : pip install paramiko",
        file=sys.stderr,
    )
    sys.exit(0)  # on ne bloque jamais Claude Code pour ça

# --- Paramètres de connexion à ton serveur AdKyNet -------------------
REMOTE_HOST = "node2.adky.net"
REMOTE_PORT = 2022
REMOTE_USER = "bdexh0br.a197589d"
REMOTE_PASSWORD = os.environ.get("ADKYNET_SFTP_PASSWORD")


def main() -> None:
    if not REMOTE_PASSWORD:
        print(
            "[sync] ADKYNET_SFTP_PASSWORD n'est pas défini — upload ignoré. "
            "Voir les instructions pour le configurer.",
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
    rel_path = os.path.relpath(local_path, project_dir).replace("\\", "/")

    # On ne synchronise jamais les fichiers qui n'ont rien à faire sur le
    # serveur (venv, cache, config locale de Claude...).
    # "site/" est le site web : il tourne sur l'autre VPS, pas sur le serveur du bot.
    ignored_prefixes = ("venv/", "__pycache__/", ".git/", ".claude/", "tests/", "graphify-out/", "site/")
    if any(rel_path.startswith(p) for p in ignored_prefixes):
        return
    # Jamais les secrets ni les données vivantes du serveur : les écraser
    # depuis la copie locale ferait perdre les tokens ou la config des serveurs.
    if rel_path in (".env", "locales.zip") or rel_path.startswith("data/") or rel_path.endswith(".log"):
        return

    remote_path = "/" + rel_path

    try:
        transport = paramiko.Transport((REMOTE_HOST, REMOTE_PORT))
        transport.connect(username=REMOTE_USER, password=REMOTE_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Recrée les sous-dossiers manquants côté serveur si besoin.
        remote_dir = os.path.dirname(remote_path)
        path = ""
        for part in remote_dir.strip("/").split("/"):
            if not part:
                continue
            path += "/" + part
            try:
                sftp.stat(path)
            except FileNotFoundError:
                sftp.mkdir(path)

        sftp.put(local_path, remote_path)
        sftp.close()
        transport.close()
        print(f"[sync] {rel_path} envoyé sur AdKyNet", file=sys.stderr)
    except Exception as e:
        # On ne bloque jamais Claude Code même si l'upload échoue.
        print(f"[sync] Échec de l'envoi de {rel_path} : {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
