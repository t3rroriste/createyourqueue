# Journal de la refonte du tableau de bord

Ce que j'ai décidé, section par section, et pourquoi. Les règles
elles-mêmes (rayons, surfaces, espacement, mouvement, contrastes mesurés)
sont dans `DESIGN-SYSTEM.md`, partie II.

---

## 1. Le périmètre, et une décision à annoncer

`app.css` est partagé entre `dashboard.html` et `servers.html`. Le prompt
laissait le choix entre faire évoluer le système entier et confiner les
nouveautés sous `.app`. **J'ai fait évoluer le système entier** — l'option
annoncée comme préférable, et la seule honnête : une console et un
sélecteur de serveur qui n'auraient pas les mêmes boutons ne seraient plus
le même produit.

Conséquence : `servers.html` et `page-servers.js` ont été repris aussi.
Même traitement, mêmes classes, zéro attribut `style` là non plus
(`servers.html` en avait 15, `page-servers.js` 7). La page est vérifiée en
fin de document.

Trois fichiers n'ont **pas** été touchés : `index.html`, `home.css` et leur
JavaScript. L'accueil garde sa D.A., et les deux systèmes ne partagent
toujours aucun token.

J'ai aussi supprimé de `app.css` tout le code mort — `.hero`, `.scene`,
`.viz` et la cinématique de l'ancien accueil, environ 180 lignes. Vérifié
avant : seuls `dashboard.html` et `servers.html` chargent `app.css`, et
aucun des deux n'utilise ces classes. C'est ce qui rend lisible ce qui
reste.

## 2. Les six symptômes, un par un

| Symptôme | Traitement | Vérification |
|---|---|---|
| Un seul rayon (`2px` / `4px`) | Quatre rayons, emploi documenté | 9 / 16 / 22 / 999 px relevés à l'écran |
| Tout est encadré | Le bloc n'a plus de contour ; filet réservé aux séparations internes et aux états | `border: 0` et `box-shadow: none` mesurés sur `.group` |
| `01 … 09` en double | `.navlink .num` et `.section__num` supprimés | aucune occurrence dans le HTML ni le JS |
| Neuf sections, une seule grille | Cinq compositions, voir §3 | — |
| `hidden` sec | Sortie + entrée décalée, 312–397 ms mesurés | `performance.now()` sur les dix sections |
| 73 `style="…"` | 81 trouvés, 0 restant | `grep` |

## 3. La composition, section par section

**Langue** — une colonne étroite (520 px). Cinq boutons radio ne
remplissent pas 1440 px, et la colonne d'aperçu de droite était à moitié
vide. L'aperçu du renommage (`#file-attente → #queue`) descend sous les
choix, où il est lu après eux et pas à côté. Les cinq lignes deviennent des
options à surface pleine, cliquables sur toute leur largeur.

**Fonctions** — pleine largeur, une colonne, lignes hautes (`.row--tall`).
Six interrupteurs avec une description chacun : il n'y a rien à mettre en
regard, et la description a besoin de place.

**Salons** — deux colonnes **à parts égales**. Le tableau des permissions
est la conséquence directe des six choix de gauche, et il a besoin de ses
quatre colonnes pour rester lisible ; le déséquilibre `1.32fr / 1fr` le
serrait pour rien.

**Rôles** — deux colonnes classiques. La hiérarchie de droite est
l'avertissement qui conditionne les quatre choix de gauche, mais elle est
courte : elle prend la colonne mince.

**MMR** — deux colonnes, gardées telles quelles : on règle à gauche, on
voit l'effet à droite, en direct. Ajout : la simulation est `sticky`, elle
reste à l'écran pendant qu'on descend dans les huit valeurs. Les trois
réglages dépendants d'un interrupteur (bonus MVP, bonus de série, série
requise) passent en `.row--sub` : décalés, sur une surface plus claire,
rattachés visuellement à l'interrupteur qui les commande.

**Queue par défaut** — le cœur du produit, donc le seul écran qui garde
`1.45fr / 1fr` **et** l'aperçu collant au défilement. C'est la section où
l'on passe le plus de temps et la seule dont l'aperçu change à chaque
frappe.

**Presets** — une colonne à largeur de lecture (760 px). Dix lignes de
`nom · format · action` étalées sur 1440 px deviendraient un tableau de
gare : l'œil perdrait le lien entre le nom et son bouton.

**Logs** — densité assumée. Dix lignes identiques, donc **deux colonnes de
lignes au-delà de 1240 px** : la liste tient d'un seul regard au lieu de
demander un défilement, et en-dessous elle retombe sur une colonne.

**Sécurité** — une colonne à largeur de lecture. Ce ne sont pas dix
réglages mais **trois décisions**, chacune suivie de ses réglages
dépendants en `.row--sub`. La hiérarchie de la section est celle des
dépendances, pas celle d'une grille.

**Diagnostic** — une colonne à largeur de lecture. C'est un rapport, pas un
écran de réglage : il ne porte pas de barre d'enregistrement, et son
en-tête annonce « Outils » et non « Configuration ».

## 4. Le rail

Le numéro est remplacé par une information d'état réelle, et il n'y en a
jamais deux sur la même entrée. La nouveauté, c'est la **pastille de
modification non enregistrée** : `app.js` émettait déjà `cyq:dirty` avec le
nombre de champs modifiés, et personne ne l'écoutait.

Un détail qui compte : `cyq:dirty` n'est émis que **tant qu'il reste au
moins une modification**. Il ne dit jamais « c'est revenu propre ». Le
signal fiable, c'est la barre d'enregistrement de la section — masquée, ou
passée en `savebar--ok` après un enregistrement réussi. La pastille écoute
donc les deux : l'événement pour le nombre, un `MutationObserver` sur la
barre pour l'état. Testé dans les deux sens, modification **et**
annulation.

L'indicateur actif : une surface arrondie qui glisse, pas un rail à gauche
— j'ai choisi l'un des deux, comme demandé. Il part **au clic**, en même
temps que la sortie de la section, pas après (mesuré : 2 ms après le clic,
alors que l'ancienne section est encore visible).

## 5. Trois écarts au prompt, assumés

**Les durées du mouvement.** Le prompt donnait sortie 140 ms, décalage
40 ms, entrée 220 ms — soit 140 + 4 × 40 + 220 = **520 ms**, alors que le
critère d'acceptation demande moins de 400 ms. Les deux ne tiennent pas
ensemble. J'ai gardé les courbes à l'identique et resserré les durées :
70 / 28 / 200, trois crans de décalage au maximum. Mesuré du clic au
dernier bloc posé sur les dix sections : **312 à 397 ms**.

**Les quatre `style=` qui restent dans `page-dashboard.js`.** Ce sont les
couleurs d'équipe : `background` de la pastille et `--team` de la puce. Une
couleur choisie par l'utilisateur est une **donnée**, pas un choix de
design, et elle ne peut pas devenir une classe. Tout le reste — rayons,
marges, tailles, gris — est passé en classe.

**Les contrastes.** Trois valeurs annoncées comme conformes ne l'étaient
pas sur toutes les surfaces (`--fg-3` clair était à 4,36:1 sur `--bg`,
donc sous AA). Elles sont corrigées, et le tableau de `DESIGN-SYSTEM.md`
§5 donne les mesures surface par surface plutôt qu'un chiffre par token.

## 6. Ce que j'ai touché en plus des trois fichiers annoncés

- **`app.js`** — six chaînes générées contenaient des `style="…"`
  (`.combo__opt`, l'étiquette d'un salon interdit, le texte « Enregistré »
  de la barre). Elles sont passées en classes. **Aucune logique n'a été
  modifiée** : le routeur, `initSection`, le tiroir et les comboboxes sont
  au caractère près ce qu'ils étaient.
- **`servers.html`, `page-servers.js`** — voir §1.
- **Les cinq fichiers de langue** — cinq clés ajoutées partout :
  `d.navLabel`, `d.crumbLabel`, `d.diagnosticD`, `d.unsaved`, `d.navWarn`.
  Les descriptions longues `s.*D`, qui existaient dans les cinq langues
  sans être utilisées nulle part, servent maintenant de chapeau à chaque
  section.
- **Une correction d'i18n** — `app.js` écrivait « Inactif : l'interrupteur
  « Nettoyage automatique » est désactivé » avec la valeur brute de
  `data-name`, qui est en français dans le HTML. Un `data-name-i18n` et
  une repasse après le repeint de `app.js` règlent le cas, sans toucher à
  sa logique.

## 7. Ce qui reste ouvert

- **`data-label`** reste en français dans le HTML. Il alimente le détail de
  la barre d'enregistrement (« Points par victoire · Bonus MVP »). Le
  traduire demande de changer `initSection()` dans `app.js`, qui l'indexe
  au démarrage — hors du périmètre annoncé, et c'est le genre de
  modification qui mérite d'être décidée à part.
- **Les noms d'équipe par défaut** (`Équipe 1`…) sont des valeurs de
  formulaire, pas des chaînes d'interface : ils restent en français quelle
  que soit la langue. À traiter côté API le jour où elle existe.
- **Les captures** sont rendues avec **Inter** et **DejaVu Sans Mono** :
  l'environnement de rendu n'a pas accès à Google Fonts. Les proportions
  sont proches d'Archivo et d'IBM Plex Mono, mais les captures ne sont pas
  la typographie finale. Les tests de débordement allemand et coréen ont
  été faits avec ces polices de repli, plus larges : le test est donc
  conservateur.

## 8. Vérifications passées

Toutes automatisées sur Chromium, `file://`, sans serveur.

- Console : **aucune erreur ni avertissement** (hors l'appel API, que
  `file://` ne peut pas faire — c'est le comportement attendu sans
  back-end).
- Indicateur : posé sans transition au chargement, puis glisse ; déplacé
  avant que l'ancienne section ne disparaisse.
- Changement de section : pas de rechargement, pas d'écran vide, aucune
  classe d'animation laissée derrière, fil d'Ariane et `#hash` à jour.
- Pastille de modification : apparaît à la première modification avec son
  compteur, disparaît à l'annulation.
- Quatre rayons distincts relevés à l'écran ; `.group` sans bordure ni
  ombre.
- Débordements : aucun, en français, en allemand et en coréen, sur
  l'ensemble des sections visibles et du rail.
- `prefers-reduced-motion: reduce` : section visible, aucun contenu
  invisible, aucune classe d'animation posée.
- Anneau de focus : 2 px, présent après tabulation.
- Thème clair : vérifié section par section, captures à l'appui.
- `servers.html` : titre, liste, barre supérieure et boutons intacts, même
  rayon de contrôle que la console.
