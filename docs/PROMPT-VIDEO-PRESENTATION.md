# Prompt — la vidéo de présentation (remplace « prêt en trois étapes »)

À coller tel quel dans une session Claude ouverte sur le dépôt CYQ.
Le prompt a deux moitiés : **A. la vidéo** (motion design + voix IA),
**B. le lecteur** (le bloc de la page et la fenêtre qui s'ouvre).
Elles se tiennent : la vidéo est produite pour le lecteur décrit en B,
et le lecteur est écrit pour le fichier produit en A.

---

## Contexte

**CreateYourQueue** est un bot Discord de file d'attente, avec un panneau web.
L'accueil (`site/index.html`) présente le produit en défilant. Sa troisième
section, « prêt en trois étapes », est une frise de trois icônes avec trois
phrases. Elle dit la vérité et elle n'apprend rien : trois pictos génériques,
un trait horizontal, et le visiteur a déjà oublié en arrivant à la section
suivante.

**Je la remplace entièrement** par un seul bloc : une affiche cliquable qui
ouvre, dans une fenêtre du site, une vidéo d'animation complète avec une voix
off IA qui présente le projet — ce que c'est, à quoi ça sert, comment on s'en
sert.

**Pas de YouTube, pas de Vimeo, pas d'iframe, pas de CDN.** La vidéo est un
fichier du site, servi par Apache comme le reste. On clique, une fenêtre
s'ouvre par-dessus la page, la vidéo part.

---

## Contraintes techniques — non négociables

- **HTML/CSS/JS vanilla, aucun build.** Pas de React, pas de bundler. Apache
  sert les fichiers tels quels. ES5 prudent, IIFE, `'use strict'`.
- **Aucune dépendance nouvelle.** Pas de Video.js, Plyr, Vidstack ou autre
  lecteur tiers. anime.js v4 UMD est déjà là et reste la seule bibliothèque.
- **La D.A. de `home.css`, et rien d'autre** : `--bg #0A0908`,
  `--panel #121110`, `--raised #24211F`, `--ink #F4F1EC`, `--ink-60`,
  `--hair rgba(244,241,236,.08)`, `--accent #C08A5A` (cuivre, **un seul
  emploi par écran** — ici ce sera la tête de lecture, donc nulle part
  ailleurs dans le bloc). Rayons `--r-shell 36px`, `--r-card 24px`,
  `--r-media 20px`. Police Geist. Le thème clair passe par les mêmes jetons,
  aucune couleur écrite en dur.
- **`transform` et `opacity` seulement** pour les animations d'interface.
  Pas de `box-shadow` animée, pas de `filter: blur()` animé sur une grande
  surface.
- **`prefers-reduced-motion: reduce`** : l'affiche ne bouge pas toute seule,
  la fenêtre s'ouvre sans ressort, et **la vidéo ne démarre jamais en
  autoplay** — elle attend le clic, dans tous les cas.
- **Si anime.js ne charge pas, le bloc reste utilisable** : l'affiche est
  visible, le clic ouvre la fenêtre, la vidéo se lit. Les états de départ
  sont posés en JS, jamais en CSS.
- **i18n** : tout texte visible passe par `data-i18n` et les cinq fichiers de
  `site/assets/js/lang/`. On écrit la clé dans `fr.js`, puis
  `python outils/verifier_langues.py --completer`.
- **Commentaires en français**, qui expliquent le *pourquoi* d'une valeur.
- **Jamais de données inventées** : pas de faux compteur de vues, pas de faux
  témoignage dans la vidéo, pas de chiffre d'usage qu'on ne mesure pas.

---

# A. La vidéo

## Le fond — ce qu'elle doit dire

Trois minutes au maximum, deux et demie si possible. Trois mouvements, dans
cet ordre, qui sont les trois questions d'un visiteur qui découvre :

1. **Le problème, puis ce que c'est.** (≈ 35 s) Un serveur Discord, un salon
   où quinze personnes écrivent « +1 », quelqu'un recompte à la main, les
   équipes se font au feeling et deux joueurs sont oubliés. Puis le bot
   arrive : un message, des boutons, la file se tient toute seule.
2. **À quoi ça sert.** (≈ 60 s) Les modules, montrés en fonctionnement et pas
   en liste : la file et ses boutons, la composition des équipes, les salons
   vocaux créés et les joueurs déplacés dedans, les rôles et les permissions,
   les cinq langues, l'historique des parties.
3. **Comment on s'en sert.** (≈ 60 s) Le parcours réel, écran par écran :
   on invite le bot (OAuth Discord), on arrive sur le sélecteur de serveur,
   on ouvre le panneau, on règle le format et les salons, on enregistre, et
   on montre le résultat **dans Discord** — le même réglage, devenu un
   message de file. Puis la clôture : le logo, l'adresse, rien d'autre.

Le troisième mouvement est le plus important et c'est celui qu'on bâcle
d'habitude. Il doit être assez précis pour qu'un visiteur sache, en sortant,
où il clique en premier.

## La forme — l'art direction

Pas un screencast, pas une capture d'écran filmée. Une **animation** qui
rejoue les interfaces, dans la D.A. du site :

- Fond `--bg`, surfaces `--panel` et `--raised`, encre `--ink` et `--ink-60`,
  filets `--hair`. Le cuivre `--accent` n'apparaît **que** pour marquer
  l'action en cours — le bouton qu'on presse, la valeur qui vient de changer.
  Jamais deux emplois cuivre dans le même plan.
- Typo Geist, pour les titres comme pour les faux messages.
- Les maquettes Discord et celles du panneau existent déjà en HTML dans
  `site/index.html` (classes `mock__*`) et dans
  `docs/PROMPT-MAQUETTES-DISCORD.md` : **s'en servir comme référence de
  pixel**, pour que la vidéo et la page d'accueil montrent littéralement la
  même chose.
- Mouvement : des glissements courts, des fondus, des éléments qui arrivent
  dans l'ordre où on les lit. Pas de rotation 3D, pas de rebond cartoon, pas
  de particules. Les courbes du site : `cubic-bezier(.16,1,.3,1)`.
- Des plans qui respirent : un plan = une idée. Si une idée demande deux
  plans, c'est deux plans, pas un plan chargé.
- **Aucune musique qui couvre la voix.** Une nappe très basse, bien sous la
  voix, ou rien du tout. Pas de corporate ukulélé.

## La voix

- **Voix IA, française, neutre et posée.** Pas d'enthousiasme commercial, pas
  de « révolutionnaire », pas de point d'exclamation. Le ton des commentaires
  du dépôt : on explique pourquoi, calmement.
- Débit lent. Des silences entre les mouvements — la voix se tait pendant que
  l'écran montre.
- **Le script est écrit avant l'animation**, et l'animation se cale dessus,
  jamais l'inverse. Rendre le script en français d'abord, dans
  `docs/SCRIPT-VIDEO.md`, avec le minutage par plan.
- Les quatre autres langues **ne sont pas doublées** : une seule voix
  française, et des **sous-titres WebVTT** pour `fr`, `en`, `es`, `de`, `ko`.
  C'est volontaire, et la raison s'écrit dans le script : cinq doublages
  divergent dès la première correction, cinq fichiers de sous-titres se
  recorrigent en trois minutes, et le site est déjà bâti sur ce principe.

## Le livrable technique

- `site/assets/video/presentation.mp4` — H.264, AAC, **1920×1080, 30 fps**,
  `-movflags +faststart`, viser **moins de 25 Mo** ; au-delà, baisser le
  débit avant de baisser la durée.
- `site/assets/video/presentation.webm` — VP9 + Opus, même montage, servi en
  premier.
- `site/assets/video/affiche.jpg` — l'image d'affiche, le plan d'ouverture,
  1920×1080, moins de 200 Ko.
- `site/assets/video/sous-titres.{fr,en,es,de,ko}.vtt`.
- **Tous ces fichiers doivent être ajoutés à `outils/fichiers_du_site.py`**,
  sinon ils ne partent pas en ligne. C'est exactement ce qui est arrivé à
  `servers.css` et à `support.html`.
- Vérifier le poids total du dossier `site/` après ajout : LWS reçoit tout
  par FTP, une publication qui double de taille se remarque.

---

# B. Le lecteur

## Le bloc dans la page

Il remplace la `<section class="bloc etapes">` de `site/index.html`
(section 3), ses styles dans `home.css`, et ses clés `step.*`. Les clés
devenues inutiles se retirent des cinq fichiers de langue —
`verifier_langues.py` les signalera.

À la place, un bloc sobre :

- un titre (`data-i18n="video.title"`), une ligne de contexte (`video.lead`) ;
- **l'affiche**, dans une coque `--r-shell`, filet `--hair`, ratio 16/9,
  `<img src="assets/video/affiche.jpg">` en `loading="lazy"` ;
- par-dessus, un **bouton de lecture** centré : disque `--raised`, triangle
  en `currentColor`, et la durée réelle écrite dessous (« 2 min 40 »). C'est
  un vrai `<button>`, pas un `div` — il ouvre la fenêtre, il doit être
  atteignable au clavier ;
- au survol : l'affiche monte de 2 px en `transform`, le disque passe à
  `--raised-2`. Rien d'autre.

La vidéo **n'est pas chargée tant qu'on n'a pas cliqué** : l'élément `<video>`
est créé (ou son `preload="none"` levé) à l'ouverture de la fenêtre. Un
accueil qui télécharge 25 Mo avant le premier clic est un accueil cassé.

## La fenêtre

Un `<dialog>` natif, ou une surcouche `position: fixed` si `<dialog>` pose un
problème de style — mais alors avec le piège de focus écrit à la main.

- Voile `rgba(10,9,8,.88)` sur toute la page, le fond ne défile plus
  (`overflow: hidden` sur `html` pendant l'ouverture, rendu à la fermeture).
- Le cadre : largeur `min(1120px, 92vw)`, ratio 16/9, rayon `--r-shell`,
  fond `--bg`, filet `--hair`.
- Ouverture : opacité 0 → 1 et `scale(.98)` → `1` en 240 ms sur `--e-out`.
  En `reduced-motion`, un fondu seul en 120 ms.
- Fermeture : la croix en haut à droite, la touche `Échap`, ou un clic sur le
  voile. Dans les trois cas **la vidéo se met en pause** et le focus revient
  sur le bouton de lecture qui avait ouvert la fenêtre.
- Le focus est piégé dans la fenêtre tant qu'elle est ouverte ; `aria-modal`,
  `role="dialog"`, `aria-label` traduit.

## Les contrôles — le point précis de la demande

**Les contrôles natifs sont désactivés** (`<video>` sans `controls`), et la
barre s'écrit à la main, pour qu'elle soit dans la D.A. du site et pas dans
celle de Chrome.

Une seule rangée, collée en bas du cadre, fond `--panel` à 92 %, filet
`--hair` au-dessus. **De gauche à droite, dans cet ordre exact :**

1. **⟲ −10 s** — reculer de dix secondes
2. **▶ / ❚❚** — lire / mettre en pause
3. **⟳ +10 s** — avancer de dix secondes
4. **la barre de progression** — elle occupe tout l'espace restant
5. le temps écoulé / la durée, en chiffres tabulaires
6. le son (muet + volume), puis le plein écran

Les trois boutons de transport sont **à gauche de la barre** : c'est le point
de la demande et il ne se discute pas. Chacun est un `<button>` avec un
`aria-label` traduit et une icône SVG en trait 1.8, comme le reste du site.

La barre de progression :

- un rail `--hair` de 3 px, la partie lue en `--ink`, et **la tête de lecture
  en `--accent`** — c'est l'unique emploi du cuivre dans toute la fenêtre ;
- cliquable sur toute sa hauteur de touche (44 px de zone, 3 px de trait
  visible) ;
- **déplaçable** à la souris et au doigt (`pointerdown` / `pointermove` /
  `pointerup` avec `setPointerCapture`), avec aperçu de la position pendant
  le glissement ;
- une bande plus claire pour le **tampon** (`video.buffered`), pour que
  l'attente se voie au lieu d'avoir l'air d'un plantage ;
- accessible au clavier : `role="slider"`, `aria-valuemin/max/now`, et les
  flèches gauche/droite déplacent de 5 s.

Raccourcis quand la fenêtre a le focus : `Espace` ou `K` lecture/pause,
`←` / `→` −10 s / +10 s, `M` muet, `F` plein écran, `Échap` ferme. Ils sont
listés dans un petit bloc d'aide replié sous la vidéo, traduit.

Les sous-titres : un bouton **CC** qui bascule les pistes `<track>` selon la
langue active du site, et retombe sur `fr` si la langue n'a pas de piste.

## Le comportement réel, pas supposé

- Si le navigateur ne sait lire ni le WebM ni le MP4, la fenêtre affiche un
  message traduit et un lien de téléchargement direct du MP4. Pas d'écran
  noir muet.
- Le `timeupdate` ne rafraîchit pas la barre : on anime en
  `requestAnimationFrame` pendant la lecture seulement, et on coupe la boucle
  à la pause. Une barre qui saute par paliers de 250 ms se voit.
- `playsinline` sur iOS, sinon Safari prend la vidéo en plein écran tout seul
  et la fenêtre ne sert plus à rien.
- La vidéo ne reprend pas à zéro si on rouvre la fenêtre dans la même visite :
  la position est gardée en mémoire (variable JS, pas de `localStorage`).

---

## Les fichiers à toucher

| Fichier | Ce qu'on y fait |
| --- | --- |
| `site/index.html` | la section 3 remplacée par le bloc affiche + le `<dialog>` |
| `site/assets/css/home.css` | les règles `.video__*` et `.lecteur__*` ; les `.etape*` retirées |
| `site/assets/js/page-home.js` | l'ouverture de la fenêtre, le lecteur, les raccourcis |
| `site/assets/js/lang/fr.js` | les clés `video.*` et `lecteur.*` (puis `--completer`) |
| `site/assets/video/` | les fichiers livrés en A |
| `outils/fichiers_du_site.py` | **déclarer chaque fichier neuf**, sinon rien ne part |
| `docs/SCRIPT-VIDEO.md` | le script, le minutage, et pourquoi une seule voix |

Puis, dans cet ordre :

```
python outils/fragments.py
python outils/numeroter_versions.py
.\cyq verifier
```

## Ce que je veux lire à la fin

Ce qui a été vérifié et ce qui ne l'a pas pu, explicitement : la page servie
en local (`.\cyq local`, `http://localhost:8765/`), la console sans erreur,
le rendu à 375 px de large, le comportement en `prefers-reduced-motion`, le
parcours clavier complet (ouvrir, lire, reculer, glisser la barre, fermer),
et le poids final du dossier `site/`.

Rien n'est publié : `cyq publier` ne se lance que si je le demande.
