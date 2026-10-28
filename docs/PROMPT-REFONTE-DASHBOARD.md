# Prompt — refonte du design de `dashboard.html`

> À coller tel quel dans une session Claude ouverte à la racine de
> `Site Dashboard/`. Tout ce qui suit a été vérifié dans le code.

---

## 0 · Rôle

Tu es designer d'interfaces produit **et** intégrateur. Tu ne rends pas une
maquette : tu modifies directement `dashboard.html`, `assets/css/app.css` et
`assets/js/page-dashboard.js`, et la page doit s'ouvrir et fonctionner à la
fin de ton travail. Tu écris le CSS à la main — aucun framework, aucune
étape de build, aucun paquet npm. Tu commentes en français, comme le reste
du dépôt.

Avant d'écrire une ligne : lis `DESIGN-SYSTEM.md`, `DESIGN-AUDIT.md`,
`assets/css/app.css` en entier, `dashboard.html` en entier,
`assets/js/app.js` (routeur `wireRouter`, `initSection`, `wireDrawer`) et
`assets/js/page-dashboard.js`.

---

## 1 · Ce qui existe

Site statique, zéro build : on envoie le dossier à l'hébergeur tel quel.

| Fichier | Rôle |
|---|---|
| `dashboard.html` | 9 sections de configuration + 1 diagnostic, 789 lignes |
| `assets/css/app.css` | thème sombre + clair, **partagé avec `servers.html`** |
| `assets/js/app.js` | i18n 5 langues, thème, routeur de sections, suivi des modifications, comboboxes, validation |
| `assets/js/page-dashboard.js` | rendu des logs, équipes, simulation MMR, permissions, hiérarchie, presets |
| `assets/js/lang/{fr,en,es,de,ko}.js` | 217 clés, toutes les chaînes passent par `data-i18n` |

Direction actuelle, à **conserver** :

- Monochrome. Deux couleurs réelles : crème `#F6F6F3`, noir `#0C0C0B`. Tout
  le reste est un gris tiré de l'un vers l'autre.
- L'accent **est** le crème : ce qui distingue une action n'est pas une
  teinte, c'est l'**aplat**. Un seul objet plein par écran.
- Couleur réservée aux états (`--ok` `--warn` `--err`), chroma basse, jamais
  en décoration, toujours doublée d'un glyphe **et** d'un mot.
- Deux familles : **Archivo** (sans) et **IBM Plex Mono** (chiffres, ids,
  clés techniques, `tabular-nums`).
- Thème clair : pas une inversion — fond gris papier `#E8E8E2`, panneaux au
  crème du logo.
- Densité d'outil : c'est une console de configuration, pas une vitrine.
  L'accueil (`index.html`, `home.css`) a sa propre D.A. et ne partage aucun
  token avec celle-ci. **Ne touche pas à `home.css`.**

---

## 2 · Le diagnostic — pourquoi ça fait « généré par une IA »

Ce n'est pas la palette, ni la typo : elles sont bonnes. C'est la **forme**
et l'**uniformité**. Six symptômes, tous vérifiables dans le code :

1. **Un seul rayon pour tout l'écran.** `--r: 2px` et `--r-lg: 4px`
   (`app.css` ~l. 50). Bouton, champ, carte, étiquette, vignette, palette :
   même angle. Résultat : une grille de rectangles, du 44 px au 600 px.
2. **Tout est encadré.** `.group`, `.row`, `.notice`, `.tag`, `.ptable`,
   `.savebar`, `.combo__button`, `.field`, `.segmented` portent chacun un
   filet de 1 px. Un écran de la section *MMR* empile trois niveaux de
   bordure (groupe → ligne → champ). La séparation devrait venir du
   **contraste de surface**, pas d'un trait de plus.
3. **La numérotation `01 … 09` fait double emploi.** Elle apparaît dans
   `.navlink .num` *et* dans `.section__num`, alors que les sections ne se
   lisent pas dans l'ordre et qu'aucune n'est un prérequis d'une autre.
   Elle impose une fausse séquence et occupe la place utile.
4. **Les neuf sections ont exactement la même composition** : `.cols` en
   `1.32fr / 1fr`, un `.group` à gauche, un `.group` d'aperçu à droite, un
   `.group__head` en mono 10 px capitales. Rien ne distingue *Langue*
   (5 boutons radio) de *Queue* (le cœur du produit).
5. **Le changement de section est un `hidden` sec.** `wireRouter()`
   (`app.js` ~l. 690) bascule `s.hidden` et remet le défilement à 0 : zéro
   continuité, l'écran saute. Le seul mouvement de la page est le `skpulse`
   des squelettes.
6. **73 attributs `style="…"` dans `dashboard.html`**, plus des
   `border-radius:2px` en dur dans les chaînes de `page-dashboard.js`
   (l. 172, l. 269). Le système de design existe sur le papier mais est
   contourné partout : c'est ce qui donne ce rendu « assemblé », bloc après
   bloc.

---

## 3 · La commande

### A · Formes et matière — casser le carré

Remplace le rayon unique par une **échelle de quatre valeurs**, chacune avec
un emploi écrit en commentaire dans le `:root` :

| Rôle | Ordre de grandeur | Exemple |
|---|---|---|
| Contrôle | 8–10 px | bouton, champ, interrupteur, segment |
| Bloc | 14–18 px | un groupe de réglages, un panneau d'aperçu |
| Coque | 20–24 px | la zone de contenu, le panneau latéral |
| Pilule / disque | 999 px / 50 % | étiquette, badge, pastille, bouton icône |

Règles de forme :

- **Un bloc ne porte plus de contour par défaut.** Il se détache par sa
  surface (`--panel` sur `--bg`). Le filet de 1 px est réservé aux
  séparations *internes* (entre deux `.row`) et aux états (`--ok-line`,
  `--warn-line`, `--err-line`).
- **Une seule ombre dans tout le système**, large et diffuse, et seulement
  sur ce qui flotte réellement (panneau de combobox, menu de langue, tiroir
  mobile). Pas d'ombre sur les blocs posés.
- **Pas de carte dans une carte dans une carte.** Deux niveaux de surface au
  maximum dans une même colonne.
- Les coins au contact d'un bord d'écran (panneau latéral, barre
  d'enregistrement collée en bas) ne s'arrondissent que du côté intérieur.
- Rythme d'espacement unique : `4 / 8 / 12 / 20 / 32 / 48`. Aucune valeur
  intermédiaire, aucun `padding` inventé dans un attribut `style`.
- **Supprime les 73 `style="…"` de `dashboard.html`** et les styles en dur
  des chaînes de `page-dashboard.js`. Chaque valeur devient une classe ou un
  token. C'est la moitié du travail : tant qu'ils sont là, la page restera
  incohérente.

### B · Tuer la numérotation

- Supprime `.navlink .num` et `.section__num`, et toutes les chaînes
  `01`…`09` du HTML.
- Dans le panneau latéral, chaque entrée devient : **libellé** (Archivo 500,
  13 px) + **une information d'état réelle** à droite, et rien d'autre.
  Cette information est l'une de celles-ci, jamais un numéro :
  - un compteur déjà calculé par le code : `#nav-presets` (`0/10`),
    `#nav-logs` (`0/10`) ;
  - un signal d'alerte : `#nav-roles-warn` ;
  - **une pastille de modification non enregistrée** — nouveauté : la
    section émet déjà `cyq:dirty` avec le nombre de champs modifiés
    (`app.js` ~l. 485). Écoute-le et marque l'entrée correspondante. C'est
    l'information que l'utilisateur cherche vraiment, et elle n'est affichée
    nulle part aujourd'hui.
- Dans l'en-tête de section, remplace le numéro par le **nom du groupe**
  (`Configuration` / `Outils`) en petit au-dessus du titre, puis le titre,
  puis la description longue déjà traduite (`s.languageD`, `s.queueD`… elles
  existent dans les cinq langues et ne sont pas toutes utilisées : sers-t'en).

### C · Le panneau latéral interactif

C'est la pièce centrale de la refonte.

**Structure** (conserve l'ordre actuel) : identité du serveur (icône, nom,
nombre de membres, « Changer de serveur ») → liste des catégories, groupées
`Configuration` (9) et `Outils` (1) → pied (langue, thème, compte, retour).

**Composition de la liste**

- Les entrées respirent : hauteur ≥ 36 px au repos, ≥ 44 px sous 900 px.
- Le groupe (`Configuration`, `Outils`) est un libellé discret, pas un
  encadré.
- Pas d'icône décorative dans un carré de couleur. Si tu poses un glyphe, il
  est tracé en 1,8 px de `currentColor`, monochrome, et il **dit quelque
  chose** — sinon pas de glyphe du tout.

**L'état actif**

- Un **indicateur unique, partagé**, qui **glisse** d'une entrée à l'autre :
  un seul élément positionné en absolu dans le panneau, animé en
  `transform: translateY()`, jamais recréé. 260 ms,
  `cubic-bezier(.2,.8,.3,1)`.
- Forme de l'indicateur : une surface arrondie (rayon « contrôle ») derrière
  l'entrée, **ou** un rail de 2–3 px à gauche aux bouts arrondis. Un seul des
  deux, pas les deux.
- L'entrée active passe en `--fg` / graisse 600 ; les autres restent en
  `--fg-2`. L'accent crème n'est jamais un aplat ici (règle du §1).

**L'effet au clic**

- Enfoncement : `scale(.985)` sur l'entrée pendant 80 ms, relâché en 140 ms.
  Pas de ripple, pas de halo, pas de glow.
- Au survol : la surface passe à `--panel-2` en 120 ms, et **rien d'autre**
  ne bouge (pas de translation, pas de changement de taille de texte).
- Le focus clavier garde l'anneau unique du système (`:focus-visible`, 2 px
  `--acc`, offset 2 px). Ne le supprime jamais.

**La mise à jour automatique du contenu** (« on clique, ça part tout seul et
tout se met à jour ») : au clic, **sans rechargement de page**, dans l'ordre —

1. animer la sortie de la section courante : `opacity 1 → 0` +
   `translateY(0 → -6px)`, 140 ms, `cubic-bezier(.4,0,1,1)` ;
2. basculer `hidden` — c'est le routeur existant, ne le remplace pas :
   enveloppe-le ;
3. animer l'entrée de la nouvelle : `opacity 0 → 1` + `translateY(8px → 0)`,
   220 ms, `cubic-bezier(.16,1,.3,1)`, avec un **décalage de 40 ms** entre
   les blocs de premier niveau de la section (5 blocs décalés au maximum,
   au-delà tout arrive ensemble) ;
4. déplacer l'indicateur du panneau **en parallèle**, pas après ;
5. mettre à jour le fil d'Ariane, le titre du document, le focus du titre et
   la position de défilement — déjà fait par `wireRouter`, vérifie que ça
   marche toujours.

Total perçu : **≤ 400 ms**. Au-delà, on a l'impression d'attendre une page.
Rien ne doit animer la **mise en page** (pas de `height`, pas de `width`, pas
de `margin`) : uniquement `transform` et `opacity`.

**Sous 900 px**, le panneau redevient le tiroir existant (`.side` en
`position: fixed`, `body.drawer-open`, `.scrim`) : conserve ce mécanisme,
redessine-le. Un clic sur une entrée ferme le tiroir — comportement déjà
présent, ne le casse pas.

### D · Hiérarchie entre les sections

Les neuf sections ne peuvent plus avoir la même grille. Attribue à chacune la
composition qui correspond à son contenu :

- **Langue** : 5 choix. Une seule colonne étroite, aérée. Pas de colonne
  d'aperçu à moitié vide.
- **Fonctions** : liste d'interrupteurs. Pleine largeur, une colonne, lignes
  hautes.
- **Queue par défaut** : le cœur du produit. C'est elle qui mérite les deux
  colonnes et l'aperçu vivant, collant au défilement.
- **MMR** : réglages à gauche, simulation à droite — garde les deux colonnes,
  c'est justifié : on voit l'effet en direct.
- **Logs** : 10 lignes identiques. Densité assumée, deux colonnes de lignes
  si la largeur le permet.
- **Presets**, **Sécurité**, **Salons**, **Rôles**, **Diagnostic** : choisis,
  et justifie en une phrase dans la documentation finale.

---

## 4 · Contraintes dures — ce qui casse si tu y touches

Vérifie chacun de ces points avant de rendre.

**Routeur et sections** — `app.js` `wireRouter()` lit `[data-section]`,
`.navlink[data-goto]`, pose `aria-current="page"`, lit `.navlink-label` pour
le fil d'Ariane, écoute `popstate` et l'ancre d'URL. Garde ces attributs **au
caractère près**.

**Suivi des modifications** — `initSection()` indexe `[data-setting]` et
`[data-label]`, et exige dans chaque section une `.savebar` contenant
`.savebar__text`, `.savebar__detail`, `[data-save]`, `[data-cancel]`. La
barre est remplacée par du HTML en dur après un enregistrement réussi
(`app.js` ~l. 520) : si tu changes sa structure, change-la **aussi** là.

**Tiroir mobile** — `[data-drawer-open]`, `[data-drawer-close]`, `.scrim`,
`body.drawer-open`, fermeture par Échap, focus rendu au bouton.

**Composants pilotés par JS** — `.combo` / `.combo__panel` / `.combo__opt`
sont **générés** par `app.js` ; `.segmented` lit le `textContent` de ses
boutons comme une valeur numérique ; `.switch` attend `.state` et `.track` ;
`#logs-list`, `#q-teams-list`, `#mmr-sim`, `#perm-body`, `#role-hierarchy`,
`#presets-list` sont remplis par `page-dashboard.js` — si tu changes leur
apparence, change la chaîne qui les produit, pas seulement le CSS.

**Internationalisation** — toute chaîne visible passe par `data-i18n` ou
`data-i18n-attr`. Aucun texte en dur. Si tu as besoin d'un nouveau libellé,
ajoute la clé dans **les cinq** fichiers de langue. Teste en **allemand**
(libellés les plus longs) et en **coréen** (`:lang(ko)` impose
`line-height: 1.75`).

**`app.css` est partagé avec `servers.html`.** Un changement sur `.btn`,
`.field`, `.tag`, `.langmenu`, `.glist`, `.topbar` s'y voit aussi. Deux
options, au choix, mais annoncée : soit tu fais évoluer le système entier de
façon cohérente (préférable — la console et le sélecteur de serveur sont le
même produit), soit tu portes les nouveautés sous `.app` pour les confiner.
Ouvre `servers.html` à la fin et vérifie qu'il n'est pas cassé.

**Accessibilité, non négociable** — contraste AA **mesuré** sur toute couleur
de texte que tu introduis ou modifies (`--fg-3` à 5,1:1 est le plancher,
jamais plus clair) ; contour de contrôle `--ctl-line` à 3,3:1 ; cibles ≥ 44 px
sous 900 px (`--ctl-h` / `--row-h` y passent déjà à 44 px) ; anneau de focus
jamais supprimé ; `prefers-reduced-motion` annule **toutes** les transitions
que tu ajoutes, glissement de l'indicateur et transition de section compris —
et dans ce cas le contenu apparaît immédiatement, jamais invisible.

**Les deux thèmes.** Chaque valeur ajoutée dans `:root` a son équivalent dans
`html[data-theme="light"]`. Vérifie la page entière dans les deux, ombres
comprises (`rgba(0,0,0,.5)` en sombre devient `rgba(22,24,27,.16)` en clair —
le motif existe déjà).

**Pas de dépendance.** `dashboard.html` ne charge **pas** anime.js
aujourd'hui, et c'est bien. Fais tout en CSS. Si une seule chose est
impossible en CSS, la bibliothèque est déjà dans le dépôt
(`assets/js/vendor/anime.umd.min.js`, 116 Ko) : ajoute la balise et
justifie-le en une phrase. Aucun CDN, aucun `npm install`.

**`@media print`** masque `.side`, `.appbar`, `.savebar`, `.topbar` : garde
ces sélecteurs valides ou mets la règle à jour.

---

## 5 · Interdits

Ces choix sont la signature exacte de ce qu'on fuit :

- Dégradé violet → bleu, texte en dégradé, `#6366f1`, `#8b5cf6`, lueur, néon,
  ombre colorée.
- Glassmorphism posé partout « parce que c'est joli ».
- Icône dans un carré arrondi coloré devant chaque titre.
- Emoji, badge « ✨ », capsule « nouveau » qui ne signale rien.
- Même `border-radius` sur tout — c'est le problème de départ ; ne le
  remplace pas par 16 px partout.
- Même `fade-in 300ms` sur tous les éléments de la page.
- Ombre portée sur un bloc qui ne flotte pas.
- Une deuxième teinte d'accent. Il y en a une, c'est le crème, c'est tout.
- Un contour de 1 px ajouté « pour délimiter » alors qu'un changement de
  surface suffit.
- Du texte sous 11 px, du gris clair sur gris foncé non mesuré.

---

## 6 · Livrables

1. `dashboard.html`, `assets/css/app.css`, `assets/js/page-dashboard.js`
   modifiés, la page fonctionnelle, aucune erreur en console.
2. Mise à jour de `DESIGN-SYSTEM.md` : une section « tableau de bord » avec
   l'échelle de rayons, les surfaces, le rythme d'espacement, le tableau des
   mouvements (rôle / courbe / durée) et les contrastes **mesurés**.
3. Un court journal : les décisions de composition prises section par
   section, et pourquoi.
4. Captures avant / après en **1440 px**, **1180 px** et **390 px**, thème
   sombre **et** clair, sur au moins *Queue par défaut*, *MMR* et *Logs*.

## 7 · Critères d'acceptation

On relit avec cette liste ; tout doit être vrai.

- [ ] Aucun `01`…`09` visible nulle part dans l'interface.
- [ ] Au moins quatre rayons distincts, chacun avec un emploi documenté.
- [ ] Un bloc de réglages ne porte plus de contour sur ses quatre côtés.
- [ ] Zéro attribut `style="…"` dans `dashboard.html`.
- [ ] Zéro valeur de style en dur dans `page-dashboard.js`.
- [ ] L'indicateur du panneau glisse ; il n'apparaît ni ne clignote.
- [ ] Changer de section n'entraîne ni rechargement, ni saut, ni écran vide ;
      le tout dure moins de 400 ms.
- [ ] Une section modifiée et non enregistrée est signalée dans le panneau.
- [ ] Les neuf sections n'ont pas toutes la même grille.
- [ ] Thème clair vérifié écran par écran.
- [ ] `prefers-reduced-motion: reduce` : aucune animation, aucun contenu
      masqué.
- [ ] Navigation entière au clavier, anneau de focus toujours visible.
- [ ] Allemand et coréen : aucun débordement, aucune troncature.
- [ ] `servers.html` toujours intact.
- [ ] Aucune dépendance ajoutée, aucune étape de build.
