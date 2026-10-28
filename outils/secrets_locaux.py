"""
Les mots de passe, rangés là où chaque système les range.
=========================================================
Deux machines, deux coffres. Windows a DPAPI, macOS a le Trousseau. Aucun
des deux ne sait lire le coffre de l'autre, et c'est voulu : un mot de
passe chiffré pour ton compte Windows ne doit pas être déchiffrable par
quelqu'un qui a copié le dossier.

Conséquence pratique : **les mots de passe ne se synchronisent pas**. Le
MacBook les redemande une fois, à l'amorçage. C'est deux minutes, et ça
évite de faire voyager des secrets dans un dépôt public.

Ordre de lecture, toujours le même :

  1. la variable d'environnement, si elle existe — elle l'emporte, c'est
     le moyen de forcer une valeur le temps d'une session ;
  2. le coffre du système ;
  3. rien, et l'appelant demande.

    from secrets_locaux import lire, ecrire
    mdp = lire("lws")          # None s'il n'y en a pas
    ecrire("adkynet", valeur)
"""

from __future__ import annotations

import os
import subprocess
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
REGLAGES = os.path.join(OUTILS_DIR, "reglages")

# clé interne -> (variable d'environnement, nom dans le coffre, fichier DPAPI)
SECRETS = {
    "lws": ("LWS_FTP_PASS", "cyq-lws-ftp", os.path.join(REGLAGES, "lws.pass")),
    "adkynet": ("ADKYNET_SFTP_PASSWORD", "cyq-adkynet-sftp",
                os.path.join(REGLAGES, "adkynet.pass")),
}

MAC = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"


# ------------------------------------------------------------- Windows ---

def _powershell(script: str, entree: str | None = None) -> str | None:
    """Lance un bout de PowerShell. Le secret passe par l'entrée standard,
    jamais par la ligne de commande : celle-ci est lisible par n'importe
    quel autre programme de la machine, dans la liste des processus."""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            input=entree, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except OSError:
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


def _dpapi_lire(fichier: str) -> str | None:
    if not os.path.isfile(fichier):
        return None
    # DPAPI refuse de déchiffrer ce qu'un autre compte a chiffré, et c'est
    # le comportement voulu. Mais un profil Windows restauré produit la même
    # erreur : on ne plante pas, on rend None et l'appelant redemande.
    return _powershell(
        f"$s = (Get-Content -LiteralPath '{fichier}' -Raw).Trim() | ConvertTo-SecureString; "
        "$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); "
        "try { [Runtime.InteropServices.Marshal]::PtrToStringAuto($b) } "
        "finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }"
    )


def _dpapi_ecrire(fichier: str, valeur: str) -> bool:
    os.makedirs(os.path.dirname(fichier), exist_ok=True)
    sortie = _powershell(
        "$v = [Console]::In.ReadToEnd().TrimEnd(\"`r`n\"); "
        "ConvertTo-SecureString -String $v -AsPlainText -Force | ConvertFrom-SecureString",
        entree=valeur,
    )
    if not sortie:
        return False
    with open(fichier, "w", encoding="ascii") as f:
        f.write(sortie)
    return True


# --------------------------------------------------------------- macOS ---

def _trousseau_lire(nom: str) -> str | None:
    try:
        res = subprocess.run(
            ["security", "find-generic-password", "-s", nom, "-w"],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    return res.stdout.strip() or None if res.returncode == 0 else None


def _trousseau_ecrire(nom: str, valeur: str) -> bool:
    try:
        # -U met à jour l'entrée si elle existe déjà, au lieu d'échouer.
        # -w après -U : le mot de passe passe en argument, ce qui n'est pas
        # idéal, mais `security` n'accepte rien d'autre sans interaction.
        res = subprocess.run(
            ["security", "add-generic-password", "-U", "-a", os.environ.get("USER", "cyq"),
             "-s", nom, "-w", valeur],
            capture_output=True, text=True,
        )
    except OSError:
        return False
    return res.returncode == 0


# ------------------------------------------------------------- publique ---

def lire(cle: str) -> str | None:
    variable, nom_coffre, fichier = SECRETS[cle]

    valeur = os.environ.get(variable)
    if valeur:
        return valeur

    if MAC:
        valeur = _trousseau_lire(nom_coffre)
        if valeur:
            return valeur
    elif WINDOWS:
        valeur = _dpapi_lire(fichier)
        if valeur:
            return valeur
        # Rattrapage propre à Windows : une variable posée avec
        # SetEnvironmentVariable(..., "User") est écrite dans le registre, et
        # les processus DÉJÀ lancés ne la voient pas. Sans cette relecture, on
        # annonce « mot de passe non défini » alors qu'il est enregistré.
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return winreg.QueryValueEx(k, variable)[0] or None
        except (OSError, ImportError):
            return None
    return None


def ecrire(cle: str, valeur: str) -> bool:
    _, nom_coffre, fichier = SECRETS[cle]
    if MAC:
        return _trousseau_ecrire(nom_coffre, valeur)
    if WINDOWS:
        return _dpapi_ecrire(fichier, valeur)
    return False


def ou(cle: str) -> str:
    """Où ce secret est rangé sur cette machine — pour le dire à l'écran."""
    variable, nom_coffre, fichier = SECRETS[cle]
    if os.environ.get(variable):
        return f"variable d'environnement {variable}"
    if MAC:
        return f"Trousseau macOS ({nom_coffre})"
    if WINDOWS:
        return f"chiffré par Windows dans {os.path.relpath(fichier, os.path.dirname(OUTILS_DIR))}"
    return "nulle part : ce système n'a pas de coffre connu"
