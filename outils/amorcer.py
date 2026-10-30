"""
Prépare CETTE machine à travailler sur CYQ. À lancer une fois.
==============================================================
    cyq amorcer          (Windows : .\\cyq amorcer   macOS : ./cyq amorcer)

Ce qu'il fait, dans cet ordre :

  1. vérifie git et Python, et le dit clairement s'il en manque un ;
  2. installe les dépendances du bot, plus paramiko (l'envoi SFTP) ;
  3. demande les identifiants qui ne sont PAS dans le dépôt — ils n'y
     seront jamais, le dépôt est public ;
  4. pose la veille au démarrage de la session ;
  5. cale la référence de publication sur l'état actuel.

Le point 5 n'est pas un détail. Sans lui, la première veille d'une machine
fraîchement clonée considère que RIEN n'a jamais été publié, et pousse les
trois cents fichiers du bot sur AdKyNet — en écrasant ce que le serveur
aurait de plus récent. On part donc du principe que l'hébergeur est à jour,
et on ne publie que ce qui change APRÈS l'installation.

Les mots de passe ne voyagent pas : chaque machine a son coffre (DPAPI sur
Windows, Trousseau sur macOS), et aucun des deux ne sait lire l'autre. Le
MacBook les redemande une fois. C'est voulu.
"""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
REGLAGES = os.path.join(OUTILS_DIR, "reglages")
ETAT = os.path.join(OUTILS_DIR, "etat")

sys.path.insert(0, OUTILS_DIR)
import publier_site  # noqa: E402
import secrets_locaux  # noqa: E402

MAC = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"


def titre(t: str) -> None:
    print(f"\n--- {t}")


def bien(t: str) -> None:
    print(f"  ok    {t}")


def note(t: str) -> None:
    print(f"  ->    {t}")


def souci(t: str) -> None:
    print(f"  !     {t}")


def demander(invite: str, defaut: str = "") -> str:
    suffixe = f" [{defaut}]" if defaut else ""
    reponse = input(f"  {invite}{suffixe} : ").strip()
    return reponse or defaut


# ------------------------------------------------------------ 1. outils ---

def verifier_outils() -> bool:
    titre("git, Python et curl")
    ok = True
    for nom, commande, ou in (
        ("git", ["git", "--version"],
         "https://git-scm.com/download/win" if WINDOWS else "xcode-select --install"),
        ("curl", ["curl", "--version"], "déjà présent sur les deux systèmes, normalement"),
    ):
        try:
            res = subprocess.run(commande, capture_output=True, text=True)
            bien(res.stdout.splitlines()[0] if res.stdout else nom)
        except OSError:
            souci(f"{nom} est introuvable. Installe-le : {ou}")
            ok = False
    bien(f"python  {sys.version.split()[0]}  ({sys.executable})")
    return ok


# ------------------------------------------------------ 2. dépendances ---

def pip(*arguments: str) -> bool:
    """pip install, avec un repli sur --user.

    Le Python livré par Apple installe dans un dossier système que l'on
    n'écrit pas sans sudo. Plutôt que de demander un mot de passe
    administrateur pour une dépendance d'outillage, on retombe sur
    l'installation « pour cet utilisateur », qui suffit."""
    base = [sys.executable, "-m", "pip", "install", "--quiet",
            "--disable-pip-version-check"]
    if subprocess.run(base + list(arguments)).returncode == 0:
        return True
    return subprocess.run(base + ["--user", *arguments]).returncode == 0


def installer_dependances() -> None:
    titre("dépendances")

    # paramiko n'est pas dans requirements.txt : le bot n'en a pas besoin
    # pour tourner, c'est l'outil de publication qui s'en sert. Il n'a donc
    # rien à faire dans les dépendances envoyées sur l'hébergeur.
    if pip("paramiko"):
        bien("paramiko (envoi SFTP vers AdKyNet)")
    else:
        souci("paramiko n'a pas pu être installé : la publication du bot sera refusée")
        note("Réessaie à la main :  python3 -m pip install --user paramiko")

    req = os.path.join(RACINE, "bot", "requirements.txt")
    if not os.path.isfile(req):
        return

    # Les dépendances du bot sont épinglées sur les versions testées en
    # Python 3.14. Sur le Python 3.9 livré avec macOS, pip ne trouvera pas
    # ces versions et s'arrêtera. Ce n'est PAS bloquant : cette machine sert
    # à écrire du code et à le synchroniser, le bot tourne sur AdKyNet. On
    # le dit au lieu d'afficher une page d'erreur rouge qui fait croire que
    # l'installation a raté.
    if sys.version_info < (3, 10):
        souci(f"Python {sys.version_info.major}.{sys.version_info.minor} : trop ancien "
              "pour les dépendances du bot (épinglées sur 3.14).")
        note("Ce n'est pas grave : synchro et publication n'ont besoin que de paramiko.")
        note("Pour faire TOURNER le bot sur cette machine, installe un Python récent :")
        note("  brew install python@3.13     puis relance  cyq amorcer")
        return

    if pip("-r", req):
        bien("bot/requirements.txt")
    else:
        souci("certaines dépendances du bot n'ont pas pu être installées")
        note("La synchro et la publication marchent quand même.")


# ------------------------------------------------------ 3. identifiants ---

def reglages_lws() -> None:
    titre("identifiants (jamais dans le dépôt)")

    conf = publier_site.lire_config()
    if conf and not publier_site.verifier_config(conf):
        bien("réglages FTP de LWS déjà en place")
    else:
        note("Réglages FTP de LWS. Panneau client LWS -> ton hébergement -> rubrique FTP.")
        conf = conf or {}
        conf = {
            "serveur": demander("Serveur FTP (sans ftp:// devant)", conf.get("serveur", "")),
            "utilisateur": demander("Identifiant FTP", conf.get("utilisateur", "")),
            "racine_site": demander("Dossier de la vitrine cyqbot.eu",
                                    conf.get("racine_site", "/cyqbot.eu")),
            "racine_app": demander("Dossier du panneau dashboard.cyqbot.eu",
                                   conf.get("racine_app", "/dashboard.cyqbot.eu")),
            "racine_status": demander("Dossier de l'état status.cyqbot.eu",
                                      conf.get("racine_status", "/status.cyqbot.eu")),
            "ftps": True,
            # Le certificat de LWS est valide mais émis pour *.lwspanel.com :
            # sans ça, curl s'arrête sur le nom qui ne correspond pas.
            "certificat_non_verifie": True,
        }
        publier_site.ecrire_config(conf)
        bien("outils/reglages/lws.json écrit")

    # `racine_status` est arrivée avec le sous-domaine d'état, après les deux
    # autres racines. `verifier_config` ne l'exige volontairement pas, pour
    # qu'une installation d'avant son existence continue de publier ses deux
    # sites : conséquence, cette installation est jugée « déjà en place » et
    # la clé neuve ne lui est JAMAIS demandée. Et quand elle est vide,
    # `publier_site --cible tout` saute status.cyqbot.eu sans rien dire.
    # On la réclame donc à part, sinon la deuxième machine publie deux
    # sous-domaines sur trois et personne ne s'en aperçoit.
    if not str((conf or {}).get("racine_status", "")).strip():
        note("Dossier du sous-domaine status.cyqbot.eu — même rubrique FTP.")
        conf = conf or {}
        conf["racine_status"] = demander("Dossier de l'état status.cyqbot.eu",
                                         "/status.cyqbot.eu")
        publier_site.ecrire_config(conf)
        bien("« racine_status » ajoutée : status.cyqbot.eu sera publié lui aussi")

    for cle, quoi, ou_le_trouver in (
        ("lws", "Mot de passe FTP de LWS", "panneau client LWS -> FTP"),
        ("adkynet", "Mot de passe SFTP d'AdKyNet", "panneau Pterodactyl -> Settings -> SFTP"),
    ):
        if secrets_locaux.lire(cle):
            bien(f"{quoi} : déjà dans le coffre ({secrets_locaux.ou(cle)})")
            continue
        note(f"{quoi} ({ou_le_trouver}).")
        valeur = getpass.getpass("  (vide pour le saisir plus tard) : ")
        if not valeur:
            souci("non enregistré : il sera redemandé au moment de publier")
            continue
        if secrets_locaux.ecrire(cle, valeur):
            bien(f"rangé : {secrets_locaux.ou(cle)}")
        else:
            souci("le coffre du système a refusé — il sera redemandé à chaque fois")


def fichier_env() -> None:
    # Des jetons, pas des mots de passe : on ne les demande pas un par un,
    # on prépare le fichier et on laisse remplir.
    env = os.path.join(RACINE, "bot", ".env")
    if os.path.isfile(env):
        bien("bot/.env en place")
        return
    modele = os.path.join(RACINE, "bot", ".env.example")
    if not os.path.isfile(modele):
        return
    with open(modele, encoding="utf-8") as src, open(env, "w", encoding="utf-8") as dst:
        dst.write(src.read())
    souci("bot/.env créé depuis le modèle — il faut y mettre les jetons Discord")
    note(f"Ouvre-le : {env}")


# -------------------------------------------------- 4. veille au démarrage ---

PLIST = "eu.cyqbot.veille"


def veille_au_demarrage() -> None:
    titre("veille au démarrage de la session")
    if WINDOWS:
        demarrage = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                                 "Start Menu", "Programs", "Startup")
        os.makedirs(demarrage, exist_ok=True)
        chemin = os.path.join(demarrage, "CYQ-veille.cmd")
        with open(chemin, "w", encoding="ascii", newline="\r\n") as f:
            f.write("@echo off\r\n"
                    "rem Lance la veille CYQ a l'ouverture de la session, sans fenetre.\r\n"
                    "rem Pose par outils\\amorcer.py ; supprime ce fichier pour l'arreter.\r\n"
                    f'powershell -NoProfile -ExecutionPolicy Bypass -File '
                    f'"{os.path.join(OUTILS_DIR, "cyq.ps1")}" veille\r\n')
        bien(f"posé : {chemin}")
        return

    if MAC:
        # launchd est le bon endroit sur macOS : il relance la veille si elle
        # s'arrête, et il la démarre à l'ouverture de session sans fenêtre de
        # terminal. Un cron ou un script de login ne font ni l'un ni l'autre.
        agents = os.path.expanduser("~/Library/LaunchAgents")
        os.makedirs(agents, exist_ok=True)
        chemin = os.path.join(agents, f"{PLIST}.plist")
        journal = os.path.join(ETAT, "veille-launchd.log")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{PLIST}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{os.path.join(OUTILS_DIR, "veille.py")}</string>
  </array>
  <key>WorkingDirectory</key><string>{RACINE}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{journal}</string>
  <key>StandardErrorPath</key><string>{journal}</string>
</dict>
</plist>
""")
        # bootout avant bootstrap : recharger un agent déjà chargé échoue,
        # et on veut pouvoir relancer l'amorçage sans se poser la question.
        uid = os.getuid()
        subprocess.run(["launchctl", "bootout", f"gui/{uid}/{PLIST}"],
                       capture_output=True)
        subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", chemin],
                       capture_output=True)
        bien(f"agent launchd posé et chargé : {chemin}")
        return

    souci("système inconnu : lance la veille à la main avec  ./cyq veille")


# ------------------------------------------ 5. référence de publication ---

def reference_publication() -> None:
    titre("référence de publication")
    os.makedirs(ETAT, exist_ok=True)
    dp = os.path.join(ETAT, "dernier-publie.txt")
    if os.path.isfile(dp):
        bien("déjà calée")
        return
    res = subprocess.run(["git", "-C", RACINE, "rev-parse", "HEAD"],
                         capture_output=True, text=True)
    tete = res.stdout.strip()
    with open(dp, "w", encoding="ascii") as f:
        f.write(tete)
    bien(f"calée sur {tete[:8]} : seules les modifications À VENIR seront publiées")
    note("Avant un premier envoi complet du bot, vérifie ce que le serveur a en plus :")
    note("  python outils/publier_bot.py --comparer")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prépare cette machine.")
    parser.add_argument("--sans-demarrage", action="store_true",
                        help="ne pose pas la veille au démarrage")
    parser.add_argument("--sans-dependances", action="store_true",
                        help="ne lance pas pip")
    args = parser.parse_args()

    print("=== CreateYourQueue — préparation de cette machine ===")
    if not verifier_outils():
        print("\nInstalle ce qui manque, puis relance  cyq amorcer.", file=sys.stderr)
        return 1
    if not args.sans_dependances:
        installer_dependances()
    reglages_lws()
    fichier_env()
    if not args.sans_demarrage:
        veille_au_demarrage()
    reference_publication()

    lance = ".\\cyq" if WINDOWS else "./cyq"
    print("\nTerminé. La suite :")
    print(f"  {lance} veille     lance la synchro continue")
    print(f"  {lance} etat       où en est tout")
    print(f"  {lance} local      sert le site sur http://localhost:8765")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
