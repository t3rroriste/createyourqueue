"""
Fabrique la voix off de la vidéo de présentation.
=================================================
Pourquoi un outil plutôt qu'un fichier audio posé à la main : l'animation
se cale sur la voix, pas l'inverse. Chaque phrase a un instant de départ,
et chaque plan de la vidéo part de l'instant de sa phrase. Changer un mot
change la durée d'une phrase, donc tout ce qui suit ; si le minutage
n'était pas recalculé ici, le film décrocherait de sa voix sans que rien
ne le signale.

    python outils/voix_video.py                 (français)
    python outils/voix_video.py --langue en

Lit   docs/maquettes-video/voix/<langue>.json   (le texte, l'instant visé)
Écrit docs/maquettes-video/voix/<langue>.mp4    (la piste complète, AAC)
      docs/maquettes-video/voix/<langue>.cues.js (le minutage réel, pour le film)
      docs/maquettes-video/voix/<langue>.vtt    (les sous-titres)

La synthèse passe par `say`, donc par le MacBook seulement : c'est une voix
provisoire, faite pour caler le montage. La voix définitive sera soit
enregistrée, soit une voix « premium » installée dans Réglages ›
Accessibilité › Contenu énoncé — il suffit alors de changer « voix » dans
le JSON et de relancer. Pour une voix enregistrée, poser un fichier
<id>.wav par phrase dans voix/<langue>/ : l'outil les prend tels quels au
lieu de synthétiser.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
DOSSIER = os.path.join(RACINE, "docs", "maquettes-video", "voix")

# 24 kHz mono : la voix n'a rien au-dessus, et la piste reste sous 1 Mo
# pour plus d'une minute une fois passée en AAC.
FREQ = 24000
# Le souffle minimal entre deux phrases, quand la précédente déborde sur
# l'instant visé de la suivante. En dessous, les phrases se collent et la
# voix a l'air de lire une liste.
SOUFFLE = 0.35
# Le silence laissé après la dernière phrase : le plan de fin a besoin de
# tenir un instant sans voix, sinon le film coupe au dernier mot.
QUEUE = 2.2


def synthetiser(texte: str, voix: str, debit: int, sortie: str) -> None:
    subprocess.run(
        ["say", "-v", voix, "-r", str(debit), "-o", sortie,
         "--file-format=WAVE", f"--data-format=LEI16@{FREQ}", texte],
        check=True,
    )


def lire(chemin: str) -> tuple[bytes, float]:
    with wave.open(chemin, "rb") as w:
        if w.getframerate() != FREQ or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"{chemin} : il faut du WAV mono 16 bits à {FREQ} Hz")
        donnees = w.readframes(w.getnframes())
        return donnees, w.getnframes() / FREQ


def horodatage(s: float) -> str:
    m, s = divmod(s, 60)
    return f"00:{int(m):02d}:{s:06.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--langue", default="fr")
    args = ap.parse_args()

    source = os.path.join(DOSSIER, f"{args.langue}.json")
    with open(source, encoding="utf-8") as f:
        cfg = json.load(f)

    enregistrees = os.path.join(DOSSIER, args.langue)
    if not shutil.which("say") and not os.path.isdir(enregistrees):
        print("La synthèse demande `say` (macOS). Sur ce poste, poser les phrases "
              f"enregistrées dans {enregistrees}/<id>.wav.", file=sys.stderr)
        return 1

    piste = bytearray()
    curseur = 0.0
    reperes = []
    with tempfile.TemporaryDirectory() as tmp:
        for ligne in cfg["lignes"]:
            wav = os.path.join(enregistrees, ligne["id"] + ".wav")
            if not os.path.exists(wav):
                wav = os.path.join(tmp, ligne["id"] + ".wav")
                synthetiser(ligne.get("dit", ligne["texte"]), cfg["voix"], cfg["debit"], wav)
            donnees, duree = lire(wav)
            debut = max(float(ligne["cible"]), curseur + (SOUFFLE if reperes else 0))
            if debut > float(ligne["cible"]) + 0.05:
                print(f"  {ligne['id']} : décalée de {debut - ligne['cible']:.2f} s "
                      "(la phrase précédente déborde)")
            silence = int(round((debut - len(piste) / 2 / FREQ) * FREQ))
            piste += b"\x00\x00" * max(0, silence)
            piste += donnees
            curseur = debut + duree
            reperes.append({"id": ligne["id"], "debut": round(debut, 3),
                            "duree": round(duree, 3), "texte": ligne["texte"]})

        piste += b"\x00\x00" * int(QUEUE * FREQ)
        brut = os.path.join(tmp, "piste.wav")
        with wave.open(brut, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(FREQ)
            w.writeframes(bytes(piste))
        # .mp4 et non .m4a : c'est le même conteneur, mais .m4a n'est servi
        # ni par tous les hébergeurs ni par les artifacts, et le navigateur
        # lit l'AAC dans un .mp4 partout.
        sortie = os.path.join(DOSSIER, f"{args.langue}.mp4")
        subprocess.run(["afconvert", "-f", "mp4f", "-d", "aac", "-b", "64000", brut, sortie], check=True)

    total = round(len(piste) / 2 / FREQ, 3)
    # Un script et non un JSON : le film l'inclut d'une balise <script>,
    # ce qui marche aussi ouvert depuis le disque, sans serveur.
    with open(os.path.join(DOSSIER, f"{args.langue}.cues.js"), "w", encoding="utf-8") as f:
        f.write("/* Écrit par outils/voix_video.py — ne pas corriger à la main. */\n")
        f.write("window.CYQ_VOIX = window.CYQ_VOIX || {};\n")
        f.write(f"window.CYQ_VOIX[{json.dumps(args.langue)}] = ")
        json.dump({"total": total, "lignes": reperes}, f, ensure_ascii=False, indent=1)
        f.write(";\n")
    with open(os.path.join(DOSSIER, f"{args.langue}.vtt"), "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for r in reperes:
            f.write(f"{horodatage(r['debut'])} --> {horodatage(r['debut'] + r['duree'])}\n{r['texte']}\n\n")

    for r in reperes:
        print(f"  {r['debut']:6.2f} s  +{r['duree']:5.2f}  {r['id']}")
    print(f"Piste : {total:.1f} s → voix/{args.langue}.mp4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
