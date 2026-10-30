# DESIGN-SYSTEM

Deux systèmes, deux fichiers, **aucun token partagé** — c'est délibéré, et
c'est ce qui garantit qu'une retouche dans l'un ne déplace rien dans
l'autre.

| Partie | Pages | Tokens |
|---|---|---|
| **I — accueil** | `index.html` | `assets/css/home.css` |
| **II — tableau de bord** | `dashboard.html`, `servers.html` | `assets/css/app.css` |

---

# Partie I — accueil

Fichier des tokens : `assets/css/home.css`, bloc `:root`.

## 1. Couleur

| Token | Valeur | Emploi | Contraste sur `--panel` |
|---|---|---|---|
| `--bg` | `#0A0908` | fond derrière la coque | — |
| `--panel` | `#121110` | la coque | — |
| `--raised` | `#1B1918` | sections paires, carte flottante | — |
| `--raised-2` | `#242120` | vignette dans la carte | — |
| `--ink` | `#F4F1EC` | titres, texte fort | 17,8:1 |
| `--ink-60` | `rgba(244,241,236,.60)` | **tout le texte courant** | **6,5:1 — mesuré** |
| `--ink-40` | `rgba(244,241,236,.40)` | wordmark, numéros de liste | 3,5:1 |
| `--hair` | `rgba(244,241,236,.08)` | filets | — |
| `--accent` | `#C08A5A` | voir ci-dessous | 6,3:1 |

Le noir est **chaud** : il tire vers le brun, jamais vers le bleu. C'est ce
qui sépare visuellement cette D.A. d'un thème sombre générique.

**Le piège de la §5.4 est évité.** Le prompt avertissait que l'encre à 55 %
risquait d'échouer en AA. J'ai posé le texte courant à **60 %**, mesuré à
6,5:1 sur le panneau — largement au-dessus des 4,5:1 exigés. À 55 % on
serait encore passé (5,6:1), mais 60 % laisse de la marge si le panneau
s'éclaircit un jour.

`--ink-40` est à 3,5:1 : **il ne porte jamais de texte courant.** Il est
réservé au wordmark géant et aux numéros de liste de 11 px, qui sont du
décor ou de la redondance. Cette contrainte est écrite en commentaire dans
le CSS pour qu'on ne la perde pas.

**L'accent — et la règle a changé le 30 octobre 2026.**

Elle était unique : `--accent` n'apparaissait que sur la flèche `↗` du
disque du CTA et sur le code de langue actif, jamais un fond, jamais un
dégradé, **jamais deux fois dans le même écran**.

La maquette de refonte l'employait dix fois par planche. Les deux ne
pouvaient pas être vraies à la fois, et l'arbitrage est celui-ci :

- **Sur la vitrine, la règle ne bouge pas.** Un écran de vitrine a une
  action principale et une seule ; le cuivre la désigne. Accueil, modules,
  guide, support, pied de page : un emploi par regard. L'aperçu de la carte
  « File d'attente » dans la grille des six modules en est un, et c'est
  pour cela qu'il est le seul aperçu coloré de la grille.
- **Dans le panneau, le cuivre devient fonctionnel.** Un écran de réglages
  ne pose pas la question « que faire ici » mais « où en est cette
  rangée-ci », soixante fois de suite. Le cuivre y répond, et la liste de
  ses emplois est fermée : l'indicateur de la section active, l'interrupteur
  allumé, la valeur retenue d'un contrôle segmenté. Rien d'autre — pas de
  titre cuivré, pas de filet cuivré.

Dans les deux cas il ne porte **jamais** un état à lui seul : la position
du bouton d'un interrupteur, `aria-pressed`, `role="switch"` et le libellé
disent la même chose sans couleur. Sur le segmenté, le fond est cuivré mais
l'encre reste crème — du cuivre sur cuivre tombait à 4,6:1, trop près du
bord pour un chiffre de 13 px.

Il est échantillonné dans le caramel de la référence ; faute de photo sur
ce site, il est le seul rappel de sa chaleur.

**Le bleu de Discord n'est pas un accent.** `--discord: #5865F2` est la
couleur d'une marque tierce. Un seul emploi légitime : un bouton qui mène
littéralement sur Discord — aujourd'hui, celui de la section Communauté de
l'accueil. Jamais un fond, jamais un filet, jamais un état.

## 2. Typographie

Une seule famille : **Geist**, avec **Archivo** en repli. Deux `<link>`
séparés vers Google Fonts, pour qu'un éventuel refus sur l'un ne fasse pas
tomber l'autre.

| Rôle | Taille | Graisse | Détail |
|---|---|---|---|
| Titre héros | `clamp(2.5rem, 4.4vw, 4.25rem)` | 500 | `line-height: 1.02`, `letter-spacing: -.03em`, **bas de casse**, ragged right |
| Titre de section | `clamp(2rem, 3.4vw, 3.25rem)` | 500 | bas de casse |
| Chiffre marquant | `clamp(2.5rem, 4vw, 4rem)` | 500 | `tabular-nums` |
| Corps | 15 px | 400 | `line-height: 1.6` |
| UI | 13–14 px | 400–500 | |
| Label | 11 px | 500 | `letter-spacing: .06em`, capitales |

Ratio titre / corps : **4,8×** au repos, jusqu'à 6,5× sur grand écran.

Le titre n'est pas justifié et n'utilise pas `text-wrap: balance` : les
lignes **doivent** rester inégales. Elles sont découpées à l'exécution par
`anime.splitText`, après le chargement des polices — un découpage fait avant
mesurerait les lignes sur la police de repli, puis les recomposerait. Le
découpage est refait au redimensionnement, et il conserve une copie
accessible du texte complet pour les lecteurs d'écran.

## 3. Formes

Quatre familles, aucun rectangle.

| Forme | Rayon | Emploi |
|---|---|---|
| Coque | `36px` | le panneau racine, détaché de 16 px des bords |
| Carte | `24px` | carte flottante, bloc de configuration |
| Média | `20px` | vignette |
| Pilule | `999px` | navigation, boutons primaire et secondaire |
| Disque | `50%` | contrôles, flèche du CTA |
| Section empilée | `32px 32px 0 0` | coins hauts seulement — elle vient de sous l'écran |

Aucune bordure sur les cartes : la séparation se fait par contraste de fond
(`--panel` contre `--raised`) ou par filet à 8 %. Une seule ombre dans tout
le système, très large et très diffuse : `0 60px 120px -60px rgba(0,0,0,.9)`.

Grain : `feTurbulence` en SVG inline, à **3 %**, `pointer-events: none`, sur
toute la coque.

## 4. Respiration

`8 / 16 / 32 / 64 / 120 / 200`. Aucune valeur intermédiaire.

## 5. Mouvement

| Rôle | Courbe | Durée |
|---|---|---|
| Entrées | `cubicBezier(.16,1,.3,1)` | 600–1300 ms |
| Micro | `outQuad` | 120–260 ms |
| Ressort | `outBack(1.2)` | 700 ms — **une seule fois**, sur la carte flottante |
| Scrub | `linear` | lié au défilement |

Séquence d'ouverture, en **une** `createTimeline()` :

```
t=0    coque      scale .96 → 1, radius 64 → 36px      900 ms
t=120  navigation y -24 → 0, opacité 0 → 1             700 ms
t=200  titre      ligne par ligne, y 110% → 0          1000 ms, stagger 80
t=350  matière    scale 1.12 → 1, blur 12 → 6px        1300 ms
t=550  wordmark   y 55% → 6%, opacité 0 → .08          1200 ms
t=600  texte      y 14 → 0, opacité                    600 ms, stagger 60
t=700  carte      scale .92 → 1                        700 ms, outBack
```

Interface cliquable à **400 ms** (vérifié). Aucun déplacement ne dépasse
40 px, le wordmark excepté, exprimé en pourcentage. Seuls `transform`,
`opacity` et `filter` sont animés.

## 6. Trois pièges rencontrés, et leur cause

Ils sont documentés ici parce qu'ils se reproduiront à la prochaine
modification.

**anime.js gère toute la chaîne `transform`.** Une navigation centrée par
`transform: translateX(-50%)` en CSS se retrouve décalée à droite dès qu'on
anime `y` : la bibliothèque réécrit la propriété entière. La pilule est donc
centrée par `left: 0; right: 0; margin: 0 auto; width: max-content`, sans
transform.

**Une section `sticky` a un rectangle figé.** Une fois épinglée, elle ne
bouge plus par rapport à l'écran, donc elle ne peut pas servir de référence
à un calcul de progression au défilement. Chaque section est précédée d'un
repère `.sec-mark` de hauteur nulle, resté dans le flux, et c'est lui qu'on
mesure. Sur un repère de hauteur nulle, les seuils **par défaut** de
`onScroll` donnent exactement « du bas de l'écran au haut ».

**Les seuils `enter`/`leave` personnalisés cassent le scrub sans rien dire.**
`onScroll({ enter: 'top bottom' })` laisse la progression bloquée à 0, sans
erreur en console. On garde les valeurs par défaut et on choisit l'élément
cible en conséquence.

Enfin, le déclenchement des révélations se fait par **test de position**, pas
par `IntersectionObserver` : celui-ci ne se déclenche jamais sur un élément
déjà dépassé, et une arrivée par ancre (`#sys-3`) ou un rechargement qui
restaure la position laissait la section vide.

## 7. Accessibilité

- Contraste AA mesuré sur toutes les couleurs de texte (§1).
- Focus visible : anneau 2 px `--ink`, `outline-offset: 3px`, jamais supprimé.
- Cibles ≥ 44 px, disques compris.
- `prefers-reduced-motion` : drapeau lu **une fois** en JS, pas de
  duplication de code. Empilement, scrub et parallaxe désactivés, sections
  repassées en `position: static`, tout le contenu immédiatement visible,
  compteurs posés à leur valeur finale. Vérifié.
- Sans JavaScript : `page-home.js` sort immédiatement si anime.js manque, et
  aucun état initial n'est posé en CSS — la page reste lisible et navigable.

---

# Partie II — tableau de bord

Fichier des tokens : `assets/css/app.css`, bloc `:root` et
`html[data-theme="light"]`. Couvre `dashboard.html` **et** `servers.html` :
la console et le sélecteur de serveur sont le même produit, ils évoluent
ensemble. Aucune dépendance, aucune étape de build, tout en CSS.

La direction ne change pas : monochrome, deux couleurs réelles (crème
`#F6F6F3`, noir `#0C0C0B`), l'accent **est** l'aplat crème, la couleur est
réservée aux états, Archivo + IBM Plex Mono. Ce qui change, c'est la
**forme** et l'**uniformité**.

## 1. Les quatre rayons

Un seul rayon pour tout l'écran, c'était le vrai défaut : du bouton de
44 px au panneau de 600 px, le même angle. Quatre valeurs, un emploi
chacune, et l'emploi est écrit en commentaire dans le `:root`.

| Token | Valeur | Emploi |
|---|---|---|
| `--r-ctl` | `9px` | **contrôle** — bouton, champ, interrupteur, segment, option de liste, indicateur du rail |
| `--r-blk` | `16px` | **bloc** — groupe de réglages, panneau d'aperçu, notice, panneau flottant |
| `--r-shell` | `22px` | **coque** — rail latéral, barre collée au bas de l'écran |
| `--r-pill` | `999px` | **pilule / disque** — étiquette, badge, pastille, bouton icône, piste d'interrupteur |

Règle de bord : un coin au contact d'un bord d'écran ne s'arrondit **que du
côté intérieur**. Le rail est en `0 22px 22px 0`, la barre
d'enregistrement collée en bas en `22px 22px 0 0`.

## 2. Les surfaces — deux niveaux, pas de contour

Un bloc ne porte plus de contour. Il se détache par sa surface.

| Token | Sombre | Clair | Emploi |
|---|---|---|---|
| `--bg` | `#0C0C0B` | `#E8E8E2` | le fond de travail |
| `--panel` | `#131312` | `#F6F6F3` | un bloc posé dessus : groupe, rail, aperçu |
| `--panel-2` | `#1A1A18` | `#EBEBE5` | un creux **dans** un bloc : survol, ligne dépendante, barre d'enregistrement |
| `--panel-3` | `#232320` | `#DEDED7` | l'indicateur du rail, le squelette, l'option sélectionnée |

**Deux niveaux au maximum dans une même colonne.** Pas de carte dans une
carte dans une carte.

Le filet de 1 px n'a plus que **deux emplois** :

1. séparer deux lignes **à l'intérieur** d'un bloc (`.row + .row`,
   `.hier__row + .hier__row`, `thead` / `tbody`) ;
2. signaler un état (`--ok-line`, `--warn-line`, `--err-line`) ;

et une exception, nommée : le **contour de contrôle** `--ctl-line`, qui dit
où l'on peut cliquer ou taper. Un bouton, un champ, un segment, une
combobox le gardent.

**Une seule ombre** dans tout le système, `--shadow`, et seulement sur ce
qui flotte réellement : panneau de combobox, menu de langue, tiroir mobile,
barre collée au bas de l'écran. Aucune ombre sur un bloc posé.

## 3. Le rythme d'espacement

`--s1 4` · `--s2 8` · `--s3 12` · `--s4 20` · `--s5 32` · `--s6 48`.

Aucune valeur intermédiaire. Aucun `padding` ni `margin` inventé dans un
attribut `style` : `dashboard.html` en comptait 81, il en compte **zéro**.
Les écarts verticaux dans un bloc viennent du `gap` de `.group__body`,
jamais d'un `margin-top` posé sur l'élément.

## 4. Le mouvement

| Rôle | Token | Courbe | Durée |
|---|---|---|---|
| Micro-état d'un contrôle qui apparaît (survol, bascule) | `--in` | `cubic-bezier(.2,.8,.3,1)` | 180 ms |
| Micro-état qui s'efface | `--out` | `cubic-bezier(.4,0,1,1)` | 120 ms |
| Enfoncement au clic (`scale(.985)`) | `--press` | `cubic-bezier(.2,.8,.3,1)` | 140 ms, 80 ms à l'appui |
| Glissement de l'indicateur du rail | `--slide` | `cubic-bezier(.2,.8,.3,1)` | 260 ms |
| Sortie de la section | `--t-leave` | `cubic-bezier(.4,0,1,1)` | 70 ms |
| Entrée d'un bloc | `--t-enter` | `cubic-bezier(.16,1,.3,1)` | 200 ms |
| Décalage entre deux blocs | `--t-stag` | — | 28 ms, **3 crans au maximum** |

**Budget du changement de section : 70 + 3 × 28 + 200 = 354 ms.** Mesuré au
`performance.now()` sur les dix sections, du clic au dernier bloc posé :
**312 à 397 ms**, le routeur ayant son propre travail à faire entre les
deux. Jamais au-delà de 400 ms.

Seuls `transform` et `opacity` sont animés. Jamais `height`, jamais
`width`, jamais `margin` : rien n'anime la mise en page.

`prefers-reduced-motion: reduce` annule tout — transitions, glissement de
l'indicateur, entrée des blocs — et le JavaScript saute l'animation au lieu
de la jouer à durée nulle, donc aucun contenu ne peut rester invisible.

## 5. Les contrastes, mesurés

Calculés sur les valeurs réelles des tokens, les deux thèmes.

| Couleur | Sur | Sombre | Clair |
|---|---|---|---|
| `--fg` | `--bg` | 18,1:1 | 15,9:1 |
| `--fg` | `--panel` | 17,2:1 | 18,1:1 |
| `--fg-2` | `--bg` | 7,9:1 | 6,1:1 |
| `--fg-2` | `--panel` | 7,5:1 | 6,9:1 |
| `--fg-2` | `--panel-2` | 7,0:1 | 6,3:1 |
| `--fg-2` | `--panel-3` | 6,4:1 | 5,6:1 |
| `--fg-3` | `--bg` | 5,8:1 | 5,7:1 |
| `--fg-3` | `--panel` | 5,5:1 | 6,4:1 |
| `--fg-3` | `--panel-2` | **5,2:1 — le plancher** | 5,8:1 |
| `--ctl-line` | `--bg` | 3,7:1 | 3,3:1 |
| `--ctl-line` | `--panel` | 3,5:1 | 3,8:1 |
| `--ok` | `--ok-bg` | 5,9:1 | 5,5:1 |
| `--warn` | `--warn-bg` | 6,6:1 | 5,4:1 |
| `--err` | `--err-bg` | 5,7:1 | 5,7:1 |

Deux corrections au passage, parce que l'ancien plancher n'était vrai que
sur une seule surface :

- `--fg-3` sombre passe de `#83837C` à `#8C8C85`. Les 5,1:1 annoncés
  étaient mesurés sur `--bg` ; sur `--panel-2`, qui porte la moitié du
  petit texte, l'ancien gris tombait à **4,57:1**. Il est maintenant à
  5,2:1 au pire.
- `--fg-3` clair passe de `#6B6B64` à `#5A5A53` : l'ancien était à
  **4,36:1** sur `--bg`, donc **sous AA**. Il est à 5,7:1.
- `--ctl-line` clair passe de `#85857E` à `#7E7E77` pour tenir les 3,3:1
  exigés sur `--bg` (il était à 3,02:1).

`--fg-3` ne va **jamais** sur `--panel-3` : il y tomberait à 4,7:1 en
sombre. Sur cette surface, c'est `--fg-2`. C'est écrit en commentaire à
côté du token et à côté des deux règles concernées (`.opt__code`,
`.combo__opt .hash`).

Le reste de l'accessibilité : anneau de focus unique (2 px `--acc`, offset
2 px) jamais supprimé ; cibles ≥ 44 px sous 900 px (`--ctl-h`, `--row-h` et
`--nav-h` y passent à 44 px) ; toute chaîne visible passe par `data-i18n`
ou `data-i18n-attr`, dans les cinq langues.

## 6. Le rail et son indicateur

L'état actif n'est pas peint sur l'entrée : c'est **un seul élément**,
`.side__mark`, posé en absolu dans `.side__nav`, qui glisse d'une entrée à
l'autre en `transform: translateY()`. Il n'est jamais recréé — c'est ce qui
fait qu'il ne clignote pas. Tant que `.is-ready` n'est pas posée sur le
rail, il est invisible **et sans transition** : la première mise en place ne
s'anime donc pas non plus.

Chaque entrée porte son libellé et **une seule information d'état réelle** :
un compteur déjà calculé (`0/10`), une alerte de droits manquants, ou la
pastille de modification non enregistrée. Jamais un numéro. La pastille
prend la place du compteur tant qu'elle est là : une information à la fois.

La pastille est un disque de 6 px en `--fg` suivi du nombre de champs
modifiés — pas une couleur d'état, donc pas de règle « glyphe + mot » à
satisfaire, et pas un deuxième accent. Le mot est dans son `.sr-only` et
la phrase complète est dans la barre d'enregistrement de la section.

## 7. Ce que le JavaScript a le droit d'écrire

`page-dashboard.js` ne contient **aucune valeur de design**. Les seules
propriétés qu'il pose sont des mesures ou des données :

- la hauteur et la position de l'indicateur du rail, lues sur l'entrée
  active ;
- la couleur d'équipe choisie par l'utilisateur (`--team`, `background`),
  qui est une donnée et ne peut pas être une classe.

Les durées du mouvement sont **relues** dans le `:root` par
`getComputedStyle` plutôt que recopiées : une seule source de vérité.

Le routeur de `app.js` n'est pas remplacé, il est **enveloppé** : le clic
est capté en phase de capture sur `.side__nav`, la sortie est jouée, puis
`CYQ.showSection` fait son travail habituel (bascule `hidden`,
`aria-current`, fil d'Ariane, focus du titre, défilement, fermeture du
tiroir), puis l'entrée est jouée.
