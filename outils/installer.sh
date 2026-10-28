#!/usr/bin/env bash
# =========================================================================
# LA commande du MacBook. Une seule ligne, à coller dans le Terminal :
#
#   curl -fsSL https://raw.githubusercontent.com/t3rroriste/createyourqueue/main/outils/installer.sh -o /tmp/cyq.sh && bash /tmp/cyq.sh
#
# Pourquoi en deux temps (télécharger PUIS lancer) et pas `curl … | bash` :
# avec un tube, l'entrée standard du script EST le script lui-même. Toute
# question posée au clavier y pioche les octets suivants, c'est-à-dire la
# suite du code. On peut contourner avec `< /dev/tty`, et ça marche — tant
# que /dev/tty existe. Dans un Terminal lancé par un script, par ssh sans
# pseudo-terminal, ou dans certains émulateurs, il n'existe pas, et le
# script s'arrête sans rien dire. Deux temps : plus de tube, plus de piège.
#
# On peut aussi passer le dossier en argument et n'avoir aucune question :
#
#   bash /tmp/cyq.sh ~/Developer/CYQ
#
# Son jumeau Windows est `installer.ps1`.
# =========================================================================

set -u

DEPOT="https://github.com/t3rroriste/createyourqueue.git"
DEFAUT="$HOME/Developer/CYQ"

echo
echo "=== CreateYourQueue — installation sur ce Mac ==="
echo

# --- git : exister ne suffit pas -----------------------------------------
#
# Sur un Mac neuf, /usr/bin/git EXISTE mais n'est qu'une amorce : au premier
# appel, elle ouvre la fenêtre « outils de développement en ligne de
# commande » et rend un code d'erreur. Un simple `command -v git` répond
# donc « oui » sur une machine où git ne marche pas encore — c'est le piège
# classique de l'installation sur macOS. On le LANCE pour de bon.
if ! git --version >/dev/null 2>&1; then
  echo "git n'est pas utilisable sur cette machine." >&2
  echo >&2
  echo "Sur un Mac neuf, c'est normal : lance" >&2
  echo "    xcode-select --install" >&2
  echo "accepte la fenêtre qui s'ouvre, attends la fin, puis recolle la commande." >&2
  exit 1
fi
echo "  ok    $(git --version)"

# --- python3 --------------------------------------------------------------
if command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
  PY=python3
  echo "  ok    $(python3 --version 2>&1)"
else
  echo "Python 3 est introuvable." >&2
  echo "    brew install python      (ou installe-le depuis python.org)" >&2
  exit 1
fi

# --- où ? ----------------------------------------------------------------
#
# En argument : aucune question. Sinon on demande, et si l'entrée standard
# n'est pas un clavier (script lancé par un autre script), on prend le
# dossier par défaut au lieu de rester bloqué sur une question que personne
# ne lira.
if [ $# -ge 1 ]; then
  CIBLE="$1"
elif [ -t 0 ]; then
  printf "Dossier d'installation [%s] : " "$DEFAUT"
  read -r CIBLE
else
  CIBLE=""
  echo "  ->    pas de clavier disponible : installation dans $DEFAUT"
fi
CIBLE="${CIBLE:-$DEFAUT}"
CIBLE="${CIBLE/#\~/$HOME}"

# --- récupérer -----------------------------------------------------------
if [ -d "$CIBLE/.git" ]; then
  echo
  echo "Le dépôt est déjà là : on le met simplement à jour."
  git -C "$CIBLE" pull --rebase --autostash || exit 1
elif [ -d "$CIBLE" ] && [ -n "$(ls -A "$CIBLE" 2>/dev/null)" ]; then
  # Cloner par-dessus un dossier qui contient déjà quelque chose, c'est le
  # bon moyen de perdre du travail sans s'en apercevoir. On refuse.
  echo >&2
  echo "$CIBLE existe et n'est pas vide, et ce n'est pas un dépôt git." >&2
  echo "Choisis un autre dossier, ou déplace celui-là, puis recommence." >&2
  exit 1
else
  echo
  echo "Récupération du dépôt dans $CIBLE…"
  git clone "$DEPOT" "$CIBLE" || exit 1
fi

# git ne garde que le bit exécutable, et seulement s'il était posé au
# commit. On le remet ici par sécurité : un `./cyq` qui répond
# « permission denied » juste après l'installation est un mauvais accueil.
chmod +x "$CIBLE/cyq" "$CIBLE/outils/cyq.sh" 2>/dev/null

# --- la suite est dans le dépôt ------------------------------------------
#
# amorcer.py pose des questions. Lancé depuis ici, il hérite de notre
# entrée standard, qui est bien le clavier puisqu'on n'est plus dans un
# tube. S'il n'y en a pas, on le dit et on s'arrête proprement plutôt que
# de laisser une installation à moitié faite.
echo
if [ -t 0 ]; then
  "$PY" "$CIBLE/outils/amorcer.py"
else
  echo "Le dépôt est récupéré, mais l'amorçage a besoin du clavier."
  echo "Termine avec :  cd \"$CIBLE\" && ./cyq amorcer"
  exit 0
fi

echo
echo "Le projet est dans : $CIBLE"
echo "Ouvre-le avec :  cd \"$CIBLE\"  puis  ./cyq etat"
