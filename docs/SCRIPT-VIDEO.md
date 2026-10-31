# Script de la vidéo de présentation

Le texte dit par la voix, le minutage, et ce que montre l'écran pendant
qu'elle parle. C'est ce document qui est écrit en premier : l'animation se
cale dessus, jamais l'inverse. Un montage fait d'abord et commenté ensuite
se reconnaît à ses silences bouchés.

Durée visée : **2 min 40**, trois mouvements. Au-delà de trois minutes,
personne ne va au bout, et le troisième mouvement — celui qui sert — est
justement à la fin.

---

## Pourquoi une seule voix, et des sous-titres

La voix est **française**, et elle est la seule. Les quatre autres langues
passent par des sous-titres WebVTT.

Ce n'est pas une économie, c'est une question d'entretien. Cinq doublages
divergent dès la première correction : on remonte un plan, on réenregistre
le français, et les quatre autres gardent l'ancienne phrase — sans que rien
ne le signale, parce qu'aucun outil ne lit une bande-son. Cinq fichiers de
sous-titres, eux, se recorrigent en trois minutes et se relisent à l'œil.

C'est déjà le principe du site : une seule page d'accueil qui se traduit à
l'exécution, et non cinq pages à tenir alignées.

---

## Le ton

Neutre et posé. Pas de point d'exclamation, pas de « révolutionnaire », pas
d'enthousiasme commercial. Le ton des commentaires du dépôt : on explique
pourquoi, calmement, et on laisse l'écran montrer le reste.

Débit lent. **La voix se tait pendant que l'écran montre** — les silences
indiqués ci-dessous sont des plans, pas des trous à combler.

---

## Mouvement 1 — le problème, puis ce que c'est  (0:00 → 0:38)

| Temps | Écran | Voix |
| --- | --- | --- |
| 0:00 – 0:06 | Un salon Discord. Les messages tombent : « +1 », « moi », « +1 », « je prends mid ». Rien d'autre ne bouge. | *(silence)* |
| 0:06 – 0:16 | La colonne continue de défiler. Un curseur remonte, recompte, redescend. | Organiser une partie à dix, sur Discord, c'est recompter une liste qui bouge pendant qu'on la lit. |
| 0:16 – 0:24 | Deux pseudos restent en dehors des deux équipes qui se dessinent. Ils s'effacent. | Il y a toujours quelqu'un qu'on oublie, et une équipe faite au hasard de qui a répondu en premier. |
| 0:24 – 0:38 | Le message du bot arrive à la place de la colonne : un embed sobre, deux boutons, un compteur **0 / 10**. | CreateYourQueue remplace la liste par une file. Un message, deux boutons, et un compte qui ne se trompe pas. |

## Mouvement 2 — à quoi ça sert  (0:38 → 1:40)

Montré en fonctionnement, jamais en liste à puces.

| Temps | Écran | Voix |
| --- | --- | --- |
| 0:38 – 0:50 | Le compteur monte, 3 / 10, 7 / 10, 10 / 10. Les pseudos s'empilent sous l'embed. | Les joueurs rejoignent d'un clic. La file se tient toute seule, et elle se vide quand la partie part. |
| 0:50 – 1:04 | Les dix pseudos se séparent en deux colonnes. Le format — 5 v 5 — est marqué en haut. | À dix, le bot compose les deux équipes selon le format réglé, et affiche qui joue avec qui. |
| 1:04 – 1:16 | Deux salons vocaux apparaissent dans la colonne de gauche. Les pseudos y glissent. | Il crée les salons vocaux, y déplace tout le monde, et les retire quand c'est fini. |
| 1:16 – 1:28 | Un rôle se pose sur un pseudo ; une permission bascule. | Les rôles décident qui ouvre une file et qui la rejoint. C'est Discord qui tranche, pas une liste tenue à part. |
| 1:28 – 1:34 | Le même embed, cinq fois, en cinq langues, en fondu enchaîné. | Le bot parle cinq langues, et il parle celle du serveur. |
| 1:34 – 1:40 | Un tableau d'historique : dates, formats, résultats. | Et il garde la trace des parties jouées. |

## Mouvement 3 — comment on s'en sert  (1:40 → 2:34)

Le mouvement le plus important, et celui qu'on bâcle d'habitude. À la fin,
le visiteur doit savoir **où il clique en premier**.

| Temps | Écran | Voix |
| --- | --- | --- |
| 1:40 – 1:50 | Le bouton « Ajouter à Discord », l'écran d'autorisation Discord, le choix du serveur. | On invite le bot depuis le site. Discord demande l'autorisation, on choisit le serveur, c'est fini. |
| 1:50 – 1:58 | Le sélecteur de serveur du panneau : les serveurs en cartes. | De retour sur le site, on se connecte avec Discord. Les serveurs qu'on administre sont là. |
| 1:58 – 2:12 | Le panneau. La section **File d'attente** : le format passe à 5 v 5, un salon est choisi dans une liste. | Le panneau règle tout : le format, le salon où la file s'affiche, les rôles qui peuvent l'ouvrir. |
| 2:12 – 2:20 | La barre d'enregistrement apparaît en bas, on enregistre, elle dit « Enregistré ». | On enregistre. |
| 2:20 – 2:34 | Retour sur Discord, le même salon : le message de file est là, au format 5 v 5. | Et dans Discord, le réglage est déjà en place. |

## Clôture  (2:34 → 2:40)

| Temps | Écran | Voix |
| --- | --- | --- |
| 2:34 – 2:40 | Le logo sur fond `--bg`, l'adresse **cyqbot.eu** dessous. Rien d'autre. | *(silence)* |

Pas de chiffre d'usage, pas de « rejoins des milliers de serveurs », pas de
témoignage : rien de tout cela n'est mesuré, et le site n'invente pas de
données.

---

## Ce que le montage doit respecter

- **Les couleurs sont celles de `home.css`** : fond `--bg #0A0908`, surfaces
  `--panel` et `--raised`, encre `--ink` et `--ink-60`, filets `--hair`.
  Le cuivre `--accent #C08A5A` ne marque QUE l'action en cours — le bouton
  pressé, la valeur qui vient de changer — et **jamais deux fois dans le
  même plan**.
- **Typo Geist**, titres comme faux messages.
- Les maquettes Discord et celles du panneau existent déjà en HTML dans
  `site/index.html` (classes `mock__*`) : elles servent de référence de
  pixel, pour que la vidéo et la page montrent la même chose.
- Glissements courts et fondus, courbe `cubic-bezier(.16,1,.3,1)`. Pas de
  rotation 3D, pas de rebond, pas de particules.
- Un plan = une idée.
- Pas de musique qui couvre la voix. Une nappe très basse, ou rien.

## Les fichiers à produire

| Fichier | Format |
| --- | --- |
| `site/assets/video/presentation.webm` | VP9 + Opus, 1920×1080, 30 fps |
| `site/assets/video/presentation.mp4` | H.264 + AAC, `-movflags +faststart`, **< 25 Mo** |
| `site/assets/video/affiche.jpg` | le plan d'ouverture, 1920×1080, < 200 Ko |
| `site/assets/video/sous-titres.fr.vtt` | d'après ce document |
| `sous-titres.{en,es,de,ko}.vtt` | traduits depuis le fichier français |

**Et ensuite, dans cet ordre :**

1. décommenter les sept lignes `assets/video/…` dans
   `outils/fichiers_du_site.py` — sans ça les fichiers ne partent pas en
   ligne, et `numeroter_versions.py` continue de le signaler ;
2. `python outils/numeroter_versions.py` ;
3. `.\cyq verifier` (sur le MacBook : `./cyq verifier`).

Tant que ces fichiers ne sont pas là, la page fonctionne : l'affiche
devient un aplat, et la fenêtre affiche son message de repli avec le lien
de téléchargement. Rien n'est cassé, il n'y a simplement rien à voir.
