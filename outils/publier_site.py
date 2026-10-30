"""
Mise en ligne du site sur l'hébergement LWS, en une commande.
=============================================================
Le site vit sur TROIS domaines :

  cyqbot.eu             la vitrine    index, modules, guide, support
  dashboard.cyqbot.eu   l'application login, welcome, servers, dashboard
  status.cyqbot.eu      la page d'état status.html et sa mesure

Chacun reçoit ses pages, plus le socle commun (app.js, config.js, les cinq
langues, anime.js, le logo, .htaccess). Le script :

  1. renumérote les assets (?v=…) dans les pages — sinon les visiteurs
     gardent l'ancien CSS et l'ancien JS en cache ;
  2. envoie chaque fichier par FTP, chiffré si l'hébergeur le permet ;
  3. dit ce qui est parti et ce qui a échoué.

    python outils/publier_site.py                 # les deux domaines
    python outils/publier_site.py --cible app     # le panneau seulement
    python outils/publier_site.py --cible statut  # la page d'état seulement
    python outils/publier_site.py --essai         # montre, n'envoie rien
    python outils/publier_site.py --lister        # repérage des dossiers
    python outils/publier_site.py --recuperer ici # TÉLÉCHARGE ce qui est en ligne

`--recuperer` ne modifie rien en ligne : il rapatrie la version publiée dans
un dossier à part, pour comparer. C'est comme ça qu'on a retrouvé les
commentaires effacés de `dashboard.html` le 28 octobre.

Pourquoi Python et plus PowerShell : le second PC est un MacBook. Le travail
réel est fait par `curl`, présent sur les deux systèmes, et avec exactement
les mêmes options qu'avant — c'est le pilote qui a changé, pas la mécanique
qui marchait.

Le mot de passe n'est JAMAIS écrit en clair ici. Il vient du coffre du
système (voir `secrets_locaux.py`), ou de l'écran.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import tempfile
import uuid

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
SITE = os.path.join(RACINE, "site")
REGLAGES = os.path.join(OUTILS_DIR, "reglages")
CONFIG = os.path.join(REGLAGES, "lws.json")
CONFIG_ANCIENNE = os.path.join(REGLAGES, "lws.config.ps1")

sys.path.insert(0, OUTILS_DIR)
import fichiers_du_site  # noqa: E402
import sans_fenetre  # noqa: E402
import secrets_locaux  # noqa: E402

# Les codes de sortie de curl, traduits. Sans ça, un échec de connexion
# s'affiche « exit 67 » et n'apprend rien.
EXPLICATIONS = {
    6: "Serveur FTP introuvable : vérifie le champ serveur (sans ftp:// devant).",
    7: "Connexion refusée : le serveur ne répond pas sur le port FTP.",
    9: "Dossier refusé ou inexistant : vérifie racine_site / racine_app.",
    28: "Délai dépassé : le serveur n'a pas répondu à temps.",
    35: "Échec de la poignée de main TLS. Même piste que le code 64 : ftps à false.",
    60: ("Le certificat du serveur ne correspond pas au nom utilisé. Mets "
         "certificat_non_verifie à true (la liaison reste chiffrée), ou reprends le "
         "nom technique du serveur donné par LWS — du genre xxx.lwspanel.com."),
    64: ("Le serveur a refusé le FTP chiffré. Mets ftps à false dans lws.json (le mot "
         "de passe circulera alors en clair) ou demande le FTPS au support LWS."),
    67: "Identifiant ou mot de passe refusé par le serveur.",
    78: "Fichier ou dossier distant introuvable : vérifie racine_site / racine_app.",
}


# ------------------------------------------------------------- réglages ---

def _migrer_depuis_powershell() -> dict | None:
    """L'ancien lws.config.ps1 relu une fois, et réécrit en JSON.

    Le PC principal a ses identifiants dans un fichier PowerShell depuis
    octobre. Les retaper serait une corvée inutile et une occasion de se
    tromper : on les convertit, une seule fois, le jour où ce script tourne
    pour la première fois."""
    if sys.platform != "win32" or not os.path.isfile(CONFIG_ANCIENNE):
        return None
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
             f"& '{CONFIG_ANCIENNE}' | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=sans_fenetre.DRAPEAU,
        )
    except OSError:
        return None
    if res.returncode != 0 or not res.stdout.strip():
        return None
    try:
        brut = json.loads(res.stdout)
    except json.JSONDecodeError:
        return None
    conf = {
        "serveur": brut.get("Serveur", ""),
        "utilisateur": brut.get("Utilisateur", ""),
        "racine_site": brut.get("RacineSite", ""),
        "racine_app": brut.get("RacineApp", ""),
        "racine_status": brut.get("RacineStatus", ""),
        "ftps": bool(brut.get("Ftps", True)),
        "certificat_non_verifie": bool(brut.get("CertificatNonVerifie", False)),
    }
    ecrire_config(conf)
    print(f"Réglages repris de lws.config.ps1 et écrits dans {os.path.basename(CONFIG)}.")
    return conf


def ecrire_config(conf: dict) -> None:
    os.makedirs(REGLAGES, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(conf, f, ensure_ascii=False, indent=2)
        f.write("\n")


def lire_config() -> dict | None:
    if os.path.isfile(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    return _migrer_depuis_powershell()


def verifier_config(conf: dict) -> list[str]:
    # `racine_status` n'est PAS dans cette liste, et c'est volontaire : une
    # installation en place doit continuer à publier ses deux sites sans
    # avoir à remplir une clé neuve. Tant qu'elle est vide, la cible
    # `statut` est simplement sautée, et `--cible statut` le dit.
    manquants = [c for c in ("serveur", "utilisateur", "racine_site", "racine_app")
                 if not str(conf.get(c, "")).strip()
                 or "A_REMPLIR" in str(conf.get(c, ""))]
    return manquants


# ----------------------------------------------------------------- curl ---

def _protege(valeur: str) -> str:
    """Dans un fichier de configuration curl, une valeur entre guillemets
    comprend \\\\ et \\" : un mot de passe contenant une barre oblique
    inverse ou un guillemet doit être échappé, sinon curl lit un identifiant
    tronqué et le serveur répond « login incorrect » — sur un mot de passe
    pourtant juste."""
    return valeur.replace("\\", "\\\\").replace('"', '\\"')


class Curl:
    """Les identifiants passent par un fichier temporaire, et pas par la
    ligne de commande : celle-ci est lisible par n'importe quel autre
    programme de la machine, dans la liste des processus."""

    def __init__(self, conf: dict, mot_de_passe: str, avec_ssl: bool | None = None):
        ssl = conf.get("ftps", True) if avec_ssl is None else avec_ssl
        lignes = [f'user = "{_protege(conf["utilisateur"])}:{_protege(mot_de_passe)}"']
        if ssl:
            lignes.append("ssl-reqd")
            # Le certificat de LWS est valide mais émis pour *.lwspanel.com :
            # sans cette ligne, curl s'arrête sur le nom qui ne correspond
            # pas. La liaison reste chiffrée ; c'est l'identité du serveur
            # qui n'est plus vérifiée.
            if conf.get("certificat_non_verifie"):
                lignes.append("insecure")
        self.config = "\n".join(lignes)

    def __call__(self, *arguments: str) -> tuple[int, str]:
        chemin = os.path.join(tempfile.gettempdir(), f"cyq-ftp-{uuid.uuid4().hex}.txt")
        try:
            with open(chemin, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.config)
            # --connect-timeout : sans lui, un serveur injoignable fait
            # attendre une minute avant de dire quoi que ce soit.
            res = subprocess.run(
                ["curl", "--silent", "--show-error", "--stderr", "-",
                 "--connect-timeout", "20", "--config", chemin, *arguments],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                # Un appel de curl PAR FICHIER, et la veille tourne sous
                # `pythonw`, qui n'a pas de console : sans ce drapeau,
                # Windows ouvrait une fenêtre pour chacun. Une publication
                # du site en faisait clignoter soixante-treize.
                creationflags=sans_fenetre.DRAPEAU,
            )
            return res.returncode, (res.stdout or "").strip()
        finally:
            try:
                os.remove(chemin)
            except OSError:
                pass


def explique(code: int, sortie: str) -> str:
    return EXPLICATIONS.get(code, sortie or f"curl a rendu le code {code}")


# ------------------------------------------------------------------ gestes ---

def cibles(conf: dict, quoi: str) -> list[dict]:
    liste = []
    if quoi in ("tout", "site"):
        liste.append({"nom": "vitrine (cyqbot.eu)", "court": "vitrine",
                      "racine": conf["racine_site"].rstrip("/"),
                      "fichiers": fichiers_du_site.VITRINE})
    if quoi in ("tout", "app"):
        liste.append({"nom": "application (dashboard.cyqbot.eu)", "court": "app",
                      "racine": conf["racine_app"].rstrip("/"),
                      "fichiers": fichiers_du_site.APPLICATION})
    # Le sous-domaine d'état n'existe que si on lui a donné un dossier. Sans
    # racine_status, on ne devine pas : on saute la cible, plutôt que
    # d'envoyer la page d'état à la racine de la vitrine.
    if quoi in ("tout", "statut"):
        racine = str(conf.get("racine_status", "")).strip().rstrip("/")
        if racine:
            liste.append({"nom": "état (status.cyqbot.eu)", "court": "statut",
                          "racine": racine,
                          "fichiers": fichiers_du_site.STATUT})
    return liste


def lister(conf: dict, curl: Curl, base: str) -> int:
    # Un premier appel sert de test de connexion : tant qu'il échoue, lister
    # le second dossier ne ferait que répéter la même erreur.
    code, sortie = curl("--list-only", base + "/")
    if code != 0:
        print(f"\nConnexion impossible (code curl {code})", file=sys.stderr)
        print("  " + explique(code, sortie), file=sys.stderr)
        if conf.get("ftps", True):
            # Le cas le plus fréquent chez un mutualisé : le FTP chiffré
            # n'est pas proposé. On le VÉRIFIE, sans rien envoyer, et on le
            # dit — on ne bascule pas en clair tout seul, ce serait décider
            # à ta place.
            sans = Curl(conf, _mot_de_passe_courant, avec_ssl=False)
            code2, _ = sans("--list-only", base + "/")
            if code2 == 0:
                print("\nDiagnostic : la connexion passe SANS chiffrement, donc "
                      "l'identifiant et\nle mot de passe sont bons — c'est le FTPS "
                      "que ce serveur refuse.\nDeux choix : demander l'activation du "
                      "FTPS au support LWS (préférable),\nou mettre ftps à false dans "
                      "lws.json en sachant que le mot de passe\ncirculera alors en "
                      "clair sur le réseau.", file=sys.stderr)
            else:
                print("\nSans chiffrement non plus : c'est donc le serveur, "
                      "l'identifiant ou le\nmot de passe. Revérifie-les dans le "
                      "panneau LWS, rubrique FTP.", file=sys.stderr)
        return 1

    dossiers = [("vitrine", conf["racine_site"]), ("application", conf["racine_app"])]
    if str(conf.get("racine_status", "")).strip():
        dossiers.append(("état", conf["racine_status"]))
    for nom, racine in dossiers:
        racine = racine.rstrip("/")
        print(f"\n--- {nom} : {base}{racine}/")
        code, sortie = curl("--list-only", base + racine + "/")
        print(sortie if code == 0 else "  inaccessible — " + explique(code, sortie))
    return 0


def recuperer(conf: dict, curl: Curl, base: str, dest: str) -> int:
    """Télécharge ce qui est en ligne. N'envoie rien, n'efface rien."""
    ok = absents = echecs = 0
    for cible in cibles(conf, "tout"):
        court = cible["court"]
        for rel in cible["fichiers"]:
            local = os.path.join(dest, court, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(local), exist_ok=True)
            code, sortie = curl("--output", local, base + cible["racine"] + "/" + rel)
            if code == 0:
                ok += 1
            else:
                try:
                    os.remove(local)
                except OSError:
                    pass
                if code in (19, 78):
                    absents += 1
                    print(f"  absent en ligne  {court}/{rel}")
                else:
                    echecs += 1
                    print(f"  ÉCHEC  {court}/{rel} — {explique(code, sortie)}", file=sys.stderr)
    print(f"\n{ok} fichier(s) récupéré(s) dans {dest}"
          + (f", {absents} absent(s) en ligne" if absents else "")
          + (f", {echecs} échec(s)" if echecs else ""))
    return 1 if echecs else 0


def envoyer(conf: dict, curl: Curl, base: str, quoi: str, essai: bool) -> int:
    buts = cibles(conf, quoi)
    if not buts:
        print("Rien à envoyer : « racine_status » est vide dans lws.json. "
              "Mets-y le dossier\ndu sous-domaine status.cyqbot.eu — "
              "lws.config.exemple.ps1 explique où le trouver.", file=sys.stderr)
        return 1

    # Un fichier listé mais absent du disque est une erreur de manifeste,
    # pas un détail : on s'arrête avant d'envoyer un site incomplet.
    manquants = sorted({rel for c in buts for rel in c["fichiers"]
                        if not os.path.isfile(os.path.join(SITE, rel.replace("/", os.sep)))})
    if manquants:
        print("Fichiers introuvables sur le disque :", file=sys.stderr)
        for m in manquants:
            print("  " + m, file=sys.stderr)
        return 1

    partis, rates = 0, []
    for cible in buts:
        print(f"=== {cible['nom']}  ->  {base}{cible['racine']}/   "
              f"({len(cible['fichiers'])} fichiers)")
        for rel in cible["fichiers"]:
            local = os.path.join(SITE, rel.replace("/", os.sep))
            if essai:
                print(f"  [essai] {rel}")
                continue
            code, sortie = curl("--ftp-create-dirs", "--upload-file", local,
                                base + cible["racine"] + "/" + rel)
            if code == 0:
                partis += 1
                print(f"  envoyé  {rel}")
            else:
                rates.append(f"{cible['nom']} : {rel}")
                print(f"  ÉCHEC   {rel} — {explique(code, sortie)}", file=sys.stderr)
        print()

    if essai:
        print("Essai terminé : rien n'a été envoyé.")
        return 0
    print(f"Envoyés : {partis}")
    if rates:
        print("Échecs :", file=sys.stderr)
        for r in rates:
            print("  " + r, file=sys.stderr)
        return 1
    print("Ouvre https://cyqbot.eu et https://dashboard.cyqbot.eu — "
          "Ctrl+Maj+R (Cmd+Maj+R) la première fois.")
    print("Rappel : https://dashboard.cyqbot.eu/login.html doit être déclarée dans")
    print("le portail Discord -> OAuth2 -> Redirects, sinon la connexion est refusée.")
    return 0


# ---------------------------------------------------------------- entrée ---

_mot_de_passe_courant = ""


def main() -> int:
    global _mot_de_passe_courant

    parser = argparse.ArgumentParser(description="Publie le site sur LWS.")
    parser.add_argument("--cible", choices=("site", "app", "statut", "tout"),
                        default="tout")
    parser.add_argument("--essai", action="store_true", help="montre, n'envoie rien")
    parser.add_argument("--sans-numerotation", action="store_true",
                        help="n'incrémente pas les ?v= (la veille l'a déjà fait)")
    parser.add_argument("--lister", action="store_true", help="liste les dossiers distants")
    parser.add_argument("--recuperer", metavar="DOSSIER",
                        help="télécharge ce qui est en ligne, sans rien envoyer")
    args = parser.parse_args()

    conf = lire_config()
    if conf is None:
        print(f"Réglages absents : {os.path.relpath(CONFIG, RACINE)}", file=sys.stderr)
        print("Lance  cyq amorcer  pour les saisir.", file=sys.stderr)
        return 1
    manquants = verifier_config(conf)
    if manquants:
        print("Il reste des valeurs à remplir dans lws.json :", file=sys.stderr)
        for m in manquants:
            print("  " + m, file=sys.stderr)
        print("\nPanneau client LWS -> ton hébergement -> rubrique FTP.", file=sys.stderr)
        return 1

    mot_de_passe = secrets_locaux.lire("lws")
    if not mot_de_passe:
        if not sys.stdin.isatty():
            print("Aucun mot de passe FTP disponible, et rien pour le demander.",
                  file=sys.stderr)
            print("Lance  cyq amorcer  pour l'enregistrer dans le coffre du système.",
                  file=sys.stderr)
            return 1
        mot_de_passe = getpass.getpass(f"Mot de passe FTP de {conf['utilisateur']} : ")
    _mot_de_passe_courant = mot_de_passe

    if conf.get("ftps", True) and conf.get("certificat_non_verifie"):
        print("FTPS actif, sans vérification du nom du serveur "
              "(certificat LWS *.lwspanel.com).")
    elif not conf.get("ftps", True):
        print("ATTENTION : FTP en clair. Le mot de passe circule sans chiffrement.")

    curl = Curl(conf, mot_de_passe)
    base = "ftp://" + conf["serveur"]

    if args.lister:
        return lister(conf, curl, base)
    if args.recuperer:
        return recuperer(conf, curl, base, os.path.abspath(args.recuperer))

    if not args.sans_numerotation and not args.essai:
        # Les blocs communs d'abord : une page dont la nav a dérivé de son
        # fragment partirait telle quelle, et les `?v=` doivent numéroter
        # ce qui part, pas l'état d'avant la recopie.
        subprocess.run([sys.executable, os.path.join(OUTILS_DIR, "fragments.py"),
                        "--silencieux"], cwd=RACINE)
        subprocess.run([sys.executable, os.path.join(OUTILS_DIR, "numeroter_versions.py"),
                        "--silencieux"], cwd=RACINE)
        print()

    # Les langues : on AVERTIT, on ne bloque pas. Même raison que pour les
    # fichiers non déclarés — une clé manquante ne casse que la langue
    # concernée, et refuser une mise en ligne entière pour ça empêcherait
    # de corriger en urgence ce qui n'a rien à voir. Mais elle se dit
    # fort, parce qu'une fois en ligne la page affiche la clé nue.
    if not args.essai:
        manque = subprocess.run(
            [sys.executable, os.path.join(OUTILS_DIR, "verifier_langues.py"),
             "--silencieux"], cwd=RACINE)
        if manque.returncode:
            print("  ! Des clés de langue manquent — voir ci-dessus.")
            print("    python outils/verifier_langues.py --completer")
            print("    La mise en ligne continue.\n")

    return envoyer(conf, curl, base, args.cible, args.essai)


if __name__ == "__main__":
    raise SystemExit(main())
