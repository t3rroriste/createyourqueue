# -*- coding: utf-8 -*-
# =========================================================================
# coffre.py — dire ce que le coffre de cette machine contient, et refaire
# une entrée qui ne marche plus.
#
#   python outils/coffre.py              ce qui est rangé, et où
#   python outils/coffre.py --refaire lws       ressaisir ce mot de passe
#   python outils/coffre.py --refaire adkynet
#
# Pourquoi ce fichier existe : `amorcer.py` saute tout secret déjà présent
#
#     if secrets_locaux.lire(cle):
#         bien(f"{quoi} : déjà dans le coffre")
#         continue
#
# ce qui est juste à l'amorçage — on ne redemande pas dix fois la même
# chose — mais laisse sans issue le jour où la valeur rangée devient
# fausse. Et c'est arrivé : le mot de passe FTP de LWS a changé début
# novembre 2026, le Mac a été remis à jour, le PC non. Résultat, du
# 02 au 05 novembre, la veille du PC a publié zéro fichier à chaque
# passage, en écrivant « Identifiant ou mot de passe refusé » dans un
# journal que personne ne lit. Le site ne bougeait que lorsque le Mac
# était allumé. Le seul recours était d'effacer `outils/reglages/lws.pass`
# à la main avant de relancer l'amorçage : un geste qu'il faut connaître,
# et qui n'existe pas sur l'autre machine.
#
# La valeur n'est jamais affichée, ni ici ni ailleurs : on en montre la
# longueur, qui suffit à voir qu'on a tapé à côté, et jamais le contenu.
# =========================================================================

from __future__ import annotations

import argparse
import getpass
import os
import sys

OUTILS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUTILS)

import secrets_locaux  # noqa: E402

# Ce que chaque entrée ouvre, et où aller le chercher quand il faut le
# retaper. Les deux mêmes lignes qu'`amorcer.py`, à dessein : si une
# troisième entrée apparaît un jour, elle se déclare aux deux endroits.
QUOI = {
    "lws": ("Mot de passe FTP de LWS",
            "panneau client LWS -> FTP",
            "le site sur cyqbot.eu"),
    "adkynet": ("Mot de passe SFTP d'AdKyNet",
                "panneau Pterodactyl -> Settings -> SFTP",
                "le bot sur node2.adky.net"),
}


def etat() -> int:
    print("Coffre de cette machine :")
    manquants = 0
    for cle, (quoi, ou_le_trouver, sert_a) in QUOI.items():
        valeur = secrets_locaux.lire(cle)
        print(f"\n  {cle} — {quoi}")
        print(f"      sert à : {sert_a}")
        if valeur:
            # La longueur, pas la valeur : elle dit « il y a quelque chose »
            # et « ce n'est pas la bonne longueur » sans rien divulguer.
            print(f"      rangé  : {secrets_locaux.ou(cle)}")
            print(f"      taille : {len(valeur)} caractères")
        else:
            manquants += 1
            print(f"      ABSENT — à prendre dans : {ou_le_trouver}")
            print(f"      python outils/coffre.py --refaire {cle}")
    print("\nUne entrée présente mais refusée par le serveur se refait avec")
    print("  python outils/coffre.py --refaire <entrée>")
    return manquants


def refaire(cle: str) -> int:
    quoi, ou_le_trouver, sert_a = QUOI[cle]
    avant = secrets_locaux.lire(cle)

    variable = secrets_locaux.SECRETS[cle][0]
    if os.environ.get(variable):
        # Le piège du `.env` du bot, en version coffre : une variable
        # d'environnement passe AVANT le coffre dans `lire()`. Ranger une
        # nouvelle valeur ne servirait alors à rien, et on chercherait
        # longtemps pourquoi.
        print(f"ATTENTION : la variable d'environnement {variable} est posée")
        print("sur cette machine, et elle passe avant le coffre. Tant qu'elle")
        print("existe, c'est elle qui sera utilisée. Retire-la d'abord :")
        print(f"  Windows : setx {variable} \"\"  puis ouvre un nouveau terminal")
        print(f"  macOS   : enlève la ligne de ton ~/.zshrc")
        return 1

    print(f"{quoi}")
    print(f"  à prendre dans : {ou_le_trouver}")
    print(f"  il ouvre       : {sert_a}")
    if avant:
        print(f"  déjà rangé     : {len(avant)} caractères — il va être remplacé")
    print()

    # getpass : la saisie ne s'affiche pas, et ne reste pas dans
    # l'historique du terminal comme le ferait un `$env:… = '…'`.
    valeur = getpass.getpass("  Nouveau mot de passe (vide pour annuler) : ")
    if not valeur:
        print("Annulé : le coffre n'a pas été touché.")
        return 1

    encore = getpass.getpass("  Le même, pour être sûr                   : ")
    if valeur != encore:
        # Deux saisies, parce qu'on ne relit jamais ce qu'on vient de ranger :
        # une faute de frappe ne se verrait qu'à la publication suivante.
        print("Les deux saisies diffèrent : le coffre n'a pas été touché.")
        return 1

    if not secrets_locaux.ecrire(cle, valeur):
        print("Le coffre du système a refusé l'écriture.")
        return 1

    relu = secrets_locaux.lire(cle)
    if relu != valeur:
        print("Rangé, mais la relecture ne rend pas la même chose.")
        print(f"  {secrets_locaux.ou(cle)}")
        return 1

    print(f"Rangé : {secrets_locaux.ou(cle)} ({len(valeur)} caractères).")
    if cle == "lws":
        print("À essayer tout de suite : python outils/publier_site.py")
    else:
        print("À essayer tout de suite : python outils/publier_bot.py")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Ce que le coffre de cette machine contient, et comment "
                    "refaire une entrée devenue fausse.")
    p.add_argument("--refaire", metavar="ENTRÉE", choices=sorted(QUOI),
                   help="ressaisir cette entrée : " + ", ".join(sorted(QUOI)))
    args = p.parse_args()

    if args.refaire:
        return refaire(args.refaire)
    return etat()


if __name__ == "__main__":
    sys.exit(main())
