#!/usr/bin/env bash
# =========================================================================
# cyq — la seule commande à retenir. Version macOS (et Linux).
#
#   ./cyq amorcer      installe tout sur ce Mac (à faire une fois)
#   ./cyq veille       lance la synchro continue en arrière-plan
#   ./cyq arret        arrête la veille
#   ./cyq synchro      un passage tout de suite
#   ./cyq publier      met en ligne : site sur LWS, bot sur AdKyNet
#   ./cyq etat         où en est tout
#   ./cyq pause        la synchro continue, la mise en ligne attend
#   ./cyq reprendre    lève la pause, et lève un conflit réglé
#   ./cyq local        sert le site sur http://localhost:8765
#
# Le jumeau de `cyq.ps1`, verbe pour verbe. Les deux appellent les mêmes
# scripts Python : il n'y a qu'une implémentation de chaque geste, et elle
# ne peut donc pas diverger d'une machine à l'autre.
# =========================================================================

set -u

OUTILS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RACINE="$(dirname "$OUTILS")"
ETAT="$OUTILS/etat"
PIDFILE="$ETAT/veille.pid"
PLIST_NOM="eu.cyqbot.veille"
PLIST="$HOME/Library/LaunchAgents/$PLIST_NOM.plist"

# python3 d'abord : sur macOS, `python` tout court peut être absent, ou
# pointer sur un Python 2 fossile selon ce qui a été installé.
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "Python est introuvable. Installe-le : brew install python" >&2; exit 1
fi

assurer_etat() { mkdir -p "$ETAT"; }

veille_pid() {
  [ -f "$PIDFILE" ] || return 1
  local n; n=$(cat "$PIDFILE" 2>/dev/null) || return 1
  [ -n "$n" ] || return 1
  kill -0 "$n" 2>/dev/null || return 1
  echo "$n"
}

aide() { sed -n '3,18p' "$OUTILS/cyq.sh" | sed 's/^# \{0,1\}//'; }

verbe="${1:-aide}"
shift || true

case "$verbe" in

  amorcer)
    "$PY" "$OUTILS/amorcer.py" "$@"
    ;;

  veille)
    # Si launchd gère déjà l'agent, c'est lui le patron : le relancer à la
    # main créerait deux veilles qui se marcheraient dessus sur le même
    # dépôt git.
    if [ -f "$PLIST" ]; then
      launchctl kickstart -k "gui/$(id -u)/$PLIST_NOM" 2>/dev/null \
        && echo "Veille relancée par launchd." \
        || echo "launchd n'a pas pu la relancer — regarde $ETAT/veille-launchd.log"
      exit 0
    fi
    if veille_pid >/dev/null; then
      echo "La veille tourne déjà (processus $(veille_pid))."
      exit 0
    fi
    assurer_etat
    nohup "$PY" "$OUTILS/veille.py" "$@" >>"$ETAT/veille-sortie.log" 2>&1 &
    echo $! >"$PIDFILE"
    echo "Veille lancée (processus $!)."
    echo "Son journal : $ETAT/journal.log"
    ;;

  arret)
    if [ -f "$PLIST" ]; then
      launchctl bootout "gui/$(id -u)/$PLIST_NOM" 2>/dev/null
      echo "Agent launchd déchargé. Il repartira à la prochaine ouverture de session ;"
      echo "pour l'empêcher définitivement, supprime $PLIST"
    fi
    if n=$(veille_pid); then
      kill "$n" && rm -f "$PIDFILE"
      echo "Veille arrêtée."
    else
      echo "Aucune veille lancée à la main ne tournait."
    fi
    ;;

  synchro)
    "$PY" "$OUTILS/veille.py" --une-fois "$@"
    ;;

  publier)
    # Une publication demandée à la main ne consulte pas la pause : si on
    # tape la commande, c'est qu'on veut publier.
    echo "=== le site vers LWS ==="
    "$PY" "$OUTILS/publier_site.py" "$@"
    echo
    echo "=== le bot vers AdKyNet ==="
    "$PY" "$OUTILS/publier_bot.py"
    ;;

  etat)
    echo "--- dépôt ---"
    git -C "$RACINE" status --short --branch
    echo
    echo "--- veille ---"
    if [ -f "$PLIST" ]; then echo "  agent launchd installé"; fi
    if n=$(veille_pid); then echo "  active (processus $n)"; else echo "  arrêtée"; fi
    if [ -f "$ETAT/conflit" ]; then
      echo "  CONFLIT non réglé : rien n'est publié."
      sed 's/^/    /' "$ETAT/conflit"
    fi
    [ -f "$ETAT/pause" ] && echo "  publication en pause"
    if [ -f "$ETAT/dernier-publie.txt" ]; then
      sha=$(cat "$ETAT/dernier-publie.txt")
      titre=$(git -C "$RACINE" log -1 --format='%h %s' "$sha" 2>/dev/null || echo "$sha")
      echo "  dernier publié : $titre"
    else
      echo "  rien n'a encore été publié depuis cette machine"
    fi
    echo
    echo "--- dix dernières lignes du journal ---"
    [ -f "$ETAT/journal.log" ] && tail -n 10 "$ETAT/journal.log" || echo "  (vide)"
    ;;

  pause)
    assurer_etat; : >"$ETAT/pause"
    echo "Publication en pause. La synchro entre les deux machines continue."
    ;;

  reprendre)
    leve=""
    for m in pause conflit; do
      [ -f "$ETAT/$m" ] && rm -f "$ETAT/$m" && leve="$leve $m"
    done
    if [ -n "$leve" ]; then echo "Levé :$leve."; else echo "Il n'y avait ni pause ni conflit."; fi
    ;;

  local)
    echo "http://localhost:8765/  —  Ctrl+C pour arrêter."
    "$PY" -m http.server 8765 --directory "$RACINE/site"
    ;;

  *)
    aide
    ;;
esac
