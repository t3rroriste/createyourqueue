"""
Recopie dans le film les vrais textes du site et du bot, pour les cinq langues.
================================================================================
Pourquoi : le film montre le panneau et l'annonce Discord tels qu'ils sont.
Si ses libellés étaient retapés à la main, ils dériveraient au premier
renommage — et le film montrerait un panneau qui n'existe plus. On les lit
donc à la source : site/assets/js/lang/<l>.js pour le panneau,
bot/locales/<l>.json pour le message du bot et les noms de salons.

    python outils/textes_video.py

Écrit docs/maquettes-video/textes.js. À relancer quand un de ces libellés
change ; le film n'a rien d'autre à faire.
"""

from __future__ import annotations

import json
import os
import re
import sys

OUTILS_DIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(OUTILS_DIR)
SORTIE = os.path.join(RACINE, "docs", "maquettes-video", "textes.js")
LANGUES = ["fr", "en", "es", "de", "ko"]

# Les clés du site que le film affiche — et seulement celles-là.
SITE = """
s.overview s.config s.options fn.leaderboard s.ranks s.mmr s.history s.seasons fn.clans
s.queue s.schedule s.presets s.channels s.roles s.blacklist s.logs se.grpRaid se.grpClean
se.grpAntilink s.stats s.journal d.diagnostic cat.bot cat.queue cat.server cat.access
cat.security cat.monitor d.find c.back n.docs m.nav n.support
q.lead q.grpIdentity q.name q.type q.session q.sessionOnDemand q.grpFormat q.teams q.players
q.grpTeams q.previewTitle q.launch q.launching q.launchOk q.stop
d.unsaved c.save c.cancel c.saved
se.threshold se.window se.accountAge se.raidKick se.raidLead se.linkLead se.cleanLead
se.autoclean se.autocleanChannel se.autocleanDelay
mm.start mm.win mm.loss mm.mvpBonus mm.grpPoints mm.lead
se2.enabled se2.resetDay se2.announce se2.keepHistory
sc.preset sc.enabled sc.time sc.days sc.lead rk.grpList rk.lead se.previewTitle
ov.week ov.recent fn.leaderboardD fn.clansD
""".split()

BOT = """
queue.ann_title queue.ann_by queue.ann_team_line queue.ann_cta queue.ann_started
queue.ann_footer_join queue.field_time queue.field_type queue.team_default
names.channel_queue_announcement names.voice_queue_waiting names.channel_queue_classement
""".split()

PAIRE = re.compile(r'"([A-Za-z0-9_.]+)"\s*:\s*"((?:[^"\\]|\\.)*)"')


def aplatir(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from aplatir(v, f"{p}.{k}" if p else k)
    else:
        yield p, o


def main() -> int:
    tout, manques = {}, []
    for l in LANGUES:
        with open(os.path.join(RACINE, "site", "assets", "js", "lang", f"{l}.js"), encoding="utf-8") as f:
            site = {k: json.loads(f'"{v}"') for k, v in PAIRE.findall(f.read())}
        with open(os.path.join(RACINE, "bot", "locales", f"{l}.json"), encoding="utf-8") as f:
            bot = dict(aplatir(json.load(f)))
        entree = {"site": {}, "bot": {}}
        for k in SITE:
            if k in site:
                entree["site"][k] = site[k]
            else:
                manques.append(f"{l} site {k}")
        for k in BOT:
            if k in bot:
                entree["bot"][k] = bot[k]
            else:
                manques.append(f"{l} bot {k}")
        tout[l] = entree

    with open(SORTIE, "w", encoding="utf-8") as f:
        f.write("/* Écrit par outils/textes_video.py — ne pas corriger à la main. */\n")
        f.write("window.CYQ_TEXTES = ")
        json.dump(tout, f, ensure_ascii=False, indent=1)
        f.write(";\n")
    for m in manques:
        print("  manque :", m)
    print(f"{len(SITE)} clés du site, {len(BOT)} du bot, {len(LANGUES)} langues → docs/maquettes-video/textes.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
