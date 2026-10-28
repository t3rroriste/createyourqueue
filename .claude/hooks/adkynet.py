"""
AdKyNet — connexion SFTP et règles d'exclusion, en un seul endroit.
=====================================================================
Deux outils envoient du code sur l'hébergeur :

- `upload_sftp.py`, appelé par Claude Code après chaque Edit/Write : un
  fichier à la fois, au fil de l'eau ;
- `sync_all.py`, lancé à la main : tout le projet d'un coup, pour rattraper
  ce qui a été écrit pendant que la synchro ne marchait pas.

Les deux doivent obéir aux MÊMES exclusions. Les écrire deux fois, c'est
garantir qu'un jour l'une des deux laissera passer `data/` et effacera la
configuration de tous les serveurs Discord.

Le mot de passe n'est jamais dans le code : il vient de la variable
d'environnement ADKYNET_SFTP_PASSWORD.
"""

from __future__ import annotations

import os
import sys


def _env(name: str, default: str | None = None) -> str | None:
    """Variable d'environnement, avec un rattrapage propre à Windows.

    Une variable définie avec SetEnvironmentVariable(..., "User") est écrite
    dans le registre : les processus DÉJÀ lancés ne la voient pas, terminal
    compris. On relit donc le registre quand le processus n'a rien — sinon on
    annonce « mot de passe non défini » alors qu'il est bien enregistré, et on
    cherche le problème au mauvais endroit."""
    valeur = os.environ.get(name)
    if valeur:
        return valeur
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as cle:
                return winreg.QueryValueEx(cle, name)[0] or default
        except OSError:
            return default
    return default


HOST = _env("ADKYNET_SFTP_HOST", "node2.adky.net")
PORT = int(_env("ADKYNET_SFTP_PORT", "2022"))
USER = _env("ADKYNET_SFTP_USER", "bdexh0br.a197589d")

# Dossiers qui n'ont rien à faire sur le serveur : dépendances compilées
# pour Windows, caches, historique git, réglages locaux de Claude, tests.
SKIP_PREFIXES = (
    "venv/", ".venv/", "__pycache__/", ".git/", ".claude/",
    "tests/", "graphify-out/",
)

# Fichiers à ne jamais écraser : les secrets et les données vivantes du
# serveur. `data/` contient la configuration de TOUS les serveurs Discord —
# l'écraser depuis une copie locale effacerait clans, MMR et historiques.
# Les outils de synchro tournent sur le PC du développeur : ils n'ont rien à
# faire sur l'hébergeur, et `sync_git.py` y serait même trompeur (le serveur
# n'est pas un dépôt git).
SKIP_EXACT = (".env", "locales.zip", "sync_adkynet.py", "sync_git.py")
SKIP_PREFIX_PATHS = ("data/",)
SKIP_SUFFIXES = (".log", ".pyc")


def password() -> str | None:
    return _env("ADKYNET_SFTP_PASSWORD")


def to_relative(local_path: str, project_dir: str) -> str:
    """Chemin relatif au projet, en séparateurs Unix (le serveur est Linux)."""
    return os.path.relpath(local_path, project_dir).replace("\\", "/")


def should_skip(rel_path: str) -> bool:
    """Vrai si ce chemin ne doit pas partir sur l'hébergeur."""
    if any(rel_path.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True
    if any(rel_path.startswith(prefix) for prefix in SKIP_PREFIX_PATHS):
        return True
    if rel_path in SKIP_EXACT:
        return True
    return any(rel_path.endswith(suffix) for suffix in SKIP_SUFFIXES)


def connect():
    """Ouvre une session SFTP. Retourne (transport, sftp).

    L'appelant referme les deux. Lève si le mot de passe manque : les deux
    outils vérifient `password()` avant d'arriver ici."""
    import paramiko

    transport = paramiko.Transport((HOST, PORT))
    transport.connect(username=USER, password=password())
    return transport, paramiko.SFTPClient.from_transport(transport)


def ensure_remote_dir(sftp, remote_path: str) -> None:
    """Recrée les sous-dossiers manquants côté serveur."""
    path = ""
    for part in os.path.dirname(remote_path).strip("/").split("/"):
        if not part:
            continue
        path += "/" + part
        try:
            sftp.stat(path)
        except FileNotFoundError:
            sftp.mkdir(path)
