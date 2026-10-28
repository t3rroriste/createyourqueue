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
#
# Une règle dans tout ce fichier : les variables s'écrivent ${AINSI}, avec
# les accolades. Le bash livré avec macOS est la version 3.2, de 2007 ;
# écrit « $CIBLE… », il avale les trois octets des points de suspension
# dans le nom de la variable, cherche « CIBLE… », ne la trouve pas, et
# s'arrête sur « unbound variable » — sur une ligne qui ne fait qu'afficher
# du texte. Les accolades ferment le nom et le problème.
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
# Y a-t-il un clavier quelque part ? Trois cas, et on les distingue en
# ESSAYANT, pas en supposant. `[ -r /dev/tty ]` répond oui sur des systèmes
# où l'ouvrir échoue quand même (« No such device or address ») : le test
# qui compte est l'ouverture elle-même.
CLAVIER="non"
if [ -t 0 ]; then
  CLAVIER="entree"
elif { : < /dev/tty; } 2>/dev/null; then
  CLAVIER="tty"
fi

CIBLE=""
if [ $# -ge 1 ]; then
  CIBLE="$1"
elif [ "${CLAVIER}" = "entree" ]; then
  printf "Dossier d'installation [%s] : " "${DEFAUT}"
  read -r CIBLE || CIBLE=""
elif [ "${CLAVIER}" = "tty" ]; then
  # L'entrée standard n'est pas un clavier, mais le terminal est joignable
  # directement : avant d'abandonner la question, on frappe à la bonne porte.
  printf "Dossier d'installation [%s] : " "${DEFAUT}" > /dev/tty
  read -r CIBLE < /dev/tty || CIBLE=""
else
  echo "  ->    pas de clavier disponible : installation dans ${DEFAUT}"
fi
if [ -z "${CIBLE}" ]; then CIBLE="${DEFAUT}"; fi
# Le tilde n'est pas développé dans une réponse tapée : ~/Dev reste la
# chaîne « ~/Dev ». On le remplace à la main.
case "${CIBLE}" in
  "~"|"~/"*) CIBLE="${HOME}${CIBLE#\~}" ;;
esac

# --- récupérer -----------------------------------------------------------
if [ -d "${CIBLE}/.git" ]; then
  echo
  echo "Le dépôt est déjà là : on le met simplement à jour."
  git -C "${CIBLE}" pull --rebase --autostash || exit 1
elif [ -d "${CIBLE}" ] && [ -n "$(ls -A "${CIBLE}" 2>/dev/null)" ]; then
  # Cloner par-dessus un dossier qui contient déjà quelque chose, c'est le
  # bon moyen de perdre du travail sans s'en apercevoir. On refuse.
  echo >&2
  echo "${CIBLE} existe et n'est pas vide, et ce n'est pas un dépôt git." >&2
  echo "Choisis un autre dossier, ou déplace celui-là, puis recommence." >&2
  exit 1
else
  echo
  echo "Récupération du dépôt dans ${CIBLE}"
  git clone "${DEPOT}" "${CIBLE}" || exit 1
fi

# git ne garde que le bit exécutable, et seulement s'il était posé au
# commit. On le remet ici par sécurité : un `./cyq` qui répond
# « permission denied » juste après l'installation est un mauvais accueil.
chmod +x "${CIBLE}/cyq" "${CIBLE}/outils/cyq.sh" 2>/dev/null

# --- la suite est dans le dépôt ------------------------------------------
#
# amorcer.py pose des questions. Lancé depuis ici, il hérite de notre
# entrée standard, qui est bien le clavier puisqu'on n'est plus dans un
# tube. S'il n'y en a pas, on le dit et on s'arrête proprement plutôt que
# de laisser une installation à moitié faite.
echo
case "${CLAVIER}" in
  entree) "${PY}" "${CIBLE}/outils/amorcer.py" ;;
  tty)    "${PY}" "${CIBLE}/outils/amorcer.py" < /dev/tty ;;
  *)
    echo "Le dépôt est récupéré, mais l'amorçage pose des questions et"
    echo "aucun clavier n'est joignable depuis ici."
    echo
    echo "Termine avec :  cd \"${CIBLE}\" && ./cyq amorcer"
    exit 0
    ;;
esac

echo
echo "Le projet est dans : ${CIBLE}"
echo "Ouvre-le avec :  cd \"${CIBLE}\"  puis  ./cyq etat"
