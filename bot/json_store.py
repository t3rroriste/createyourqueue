"""
JSON store — Écriture sûre des fichiers de données.
=====================================================
Tous les fichiers de `data/` passaient par `open(path, "w")` puis `json.dump`.
`open(..., "w")` vide le fichier avant d'écrire : un arrêt pendant l'écriture
(crash, coupure, redémarrage de l'hébergeur) laissait un fichier vide ou
tronqué, et au démarrage suivant la configuration était perdue.

`write_json` écrit d'abord dans un fichier temporaire du même dossier, force
son passage sur le disque, puis le met à la place de l'ancien en une seule
opération (`os.replace`, atomique sur Windows comme sur Linux). À tout
instant, le fichier contient soit l'ancienne version complète, soit la
nouvelle.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Any

# Sous Windows, un antivirus ou un indexeur peut garder le fichier cible ouvert
# une fraction de seconde : os.replace échoue alors avec PermissionError.
_REPLACE_ATTEMPTS = 5
_REPLACE_DELAY = 0.05


def write_json(path: str | os.PathLike, data: Any, **dump_kwargs: Any) -> None:
    """Écrit `data` en JSON dans `path` sans jamais laisser un fichier à moitié écrit."""
    path = os.fspath(path)
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(_REPLACE_DELAY)
    except BaseException:
        # Le fichier temporaire ne doit pas traîner si l'écriture a échoué.
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
