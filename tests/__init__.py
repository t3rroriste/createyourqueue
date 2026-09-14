"""Tests du projet. Lancer depuis la racine :

    venv\\Scripts\\python.exe -m unittest discover -s tests -t .
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
