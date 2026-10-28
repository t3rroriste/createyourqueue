#!/usr/bin/env bash
# =========================================================================
# LA commande du MacBook. Une seule, à coller dans le Terminal :
#
#   curl -fsSL https://raw.githubusercontent.com/t3rroriste/createyourqueue/main/outils/installer.sh | bash
#
# Elle récupère tout — le bot Discord, le site, l'API, les outils — puis
# enchaîne sur amorcer.py, qui demande les identifiants, pose la veille
# dans launchd et cale la référence de publication.
#
# Son jumeau Windows est `installer.ps1`.
#
# Le script est lu par un tube (`| bash`), donc il ne peut pas lire de
# réponse au clavier de la manière habituelle : `read` prend son texte dans
# le tube et avale le reste du script. D'où le `< /dev/tty` sur la seule
# question posée ici — le reste des questions est posé par amorcer.py, qui
# tourne, lui, comme un programme normal.
# =========================================================================

set -u

DEPOT="https://github.com/t3rroriste/createyourqueue.git"
DEFAUT="$HOME/Developer/CYQ"

echo
echo "=== CreateYourQueue — installation sur ce Mac ==="
echo

if ! command -v git >/dev/null 2>&1; then
  echo "git est introuvable."
  echo "Lance :  xcode-select --install"
  echo "Puis recolle cette commande."
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then PY=python3
else
  echo "Python 3 est introuvable."
  echo "Lance :  brew install python    (ou installe-le depuis python.org)"
  exit 1
fi

printf "Dossier d'installation [%s] : " "$DEFAUT"
if [ -t 0 ]; then read -r CIBLE; else read -r CIBLE < /dev/tty; fi
CIBLE="${CIBLE:-$DEFAUT}"
CIBLE="${CIBLE/#\~/$HOME}"

if [ -d "$CIBLE/.git" ]; then
  echo
  echo "Le dépôt est déjà là : on le met simplement à jour."
  git -C "$CIBLE" pull --rebase --autostash || exit 1
elif [ -d "$CIBLE" ] && [ -n "$(ls -A "$CIBLE" 2>/dev/null)" ]; then
  # Cloner par-dessus un dossier qui contient déjà quelque chose, c'est le
  # bon moyen de perdre du travail sans s'en apercevoir. On refuse.
  echo
  echo "$CIBLE existe et n'est pas vide, et ce n'est pas un dépôt git."
  echo "Choisis un autre dossier, ou déplace celui-là, puis recommence."
  exit 1
else
  echo
  echo "Récupération du dépôt…"
  git clone "$DEPOT" "$CIBLE" || exit 1
fi

# git ne garde que le bit exécutable, et seulement s'il était posé au
# commit. On le remet ici par sécurité : un `./cyq` qui répond
# « permission denied » juste après l'installation est un mauvais accueil.
chmod +x "$CIBLE/cyq" "$CIBLE/outils/cyq.sh" 2>/dev/null

echo
"$PY" "$CIBLE/outils/amorcer.py" < /dev/tty

echo
echo "Le projet est dans : $CIBLE"
echo "Ouvre-le avec :  cd \"$CIBLE\"  puis  ./cyq etat"
