# Prompt — héros à carrousel + rangées de modules

Prompt à coller tel quel dans Claude Code, à la racine du dépôt CYQ.
Quatre lots, à enchaîner sans s'arrêter entre eux.

Les captures citées plus bas sont dans `docs/references-accueil/` :

| Fichier | Ce qu'il montre |
| --- | --- |
| `actuel-heros.webp` | le héros tel qu'il est aujourd'hui |
| `actuel-rangee-module.webp` | une rangée de module aujourd'hui |
| `ref-mee6-texte.png` | la référence MEE6 — contenu de la colonne de texte |
| `ref-codex-cadre.png` | la référence Codex — cadre, proportions, débord |

---

Tu travailles sur l'accueil du site vitrine, `site/index.html`, avec
`site/assets/css/home.css`, `site/assets/js/page-home.js` et le fragment
`outils/communs/maquette.html`. Lis `CLAUDE.md` avant de toucher quoi que
ce soit : les règles qui y sont écrites ne se négocient pas, en
particulier celles qui suivent.

**Ce qui est déjà en place et qu'il ne faut pas réinventer**

- Les six scènes Discord (`queue`, `mmr`, `duel`, `clan`, `securite`,
  `options`) vivent dans `outils/communs/maquette.html`, une seule fois,
  derrière `{{si module=…}}`. `outils/fragments.py` les recopie dans les
  pages entre les repères `<!-- cyq:maquette module=x -->` et
  `<!-- cyq:/maquette -->`. **Ne jamais corriger une scène dans une
  page** : elle sera écrasée au passage suivant. On modifie le fragment,
  puis `python outils/fragments.py`.
- Le héros, lui, porte aujourd'hui une **copie à la main** de la scène
  `queue`, simplifiée, dans `.hero__embed-card` (vers la ligne 241 de
  `site/index.html`). C'est exactement le doublon que `outils/communs/`
  existe pour supprimer : il disparaît au lot 2.
- `[data-ballon]` (app.js, l. 1480) donne la lévitation au survol,
  `[data-hero="embed"]` est animé à l'ouverture par `page-home.js`
  (l. 72 et 149), et `.hero__embed-card` porte le `rotate(-3deg)` et
  l'ombre portée. Trois calques, trois rôles : ne pas empiler deux
  `transform` sur le même élément.
- Les textes passent tous par `data-i18n` et les cinq dictionnaires de
  `site/assets/js/lang/`. On écrit la clé dans `fr.js`, puis
  `python outils/verifier_langues.py --completer`.

**Les garde-fous**

- Aucune dépendance nouvelle. anime.js est déjà là, hébergé.
- Animations en `transform` et `opacity` uniquement.
- `prefers-reduced-motion: reduce` a toujours une variante calme, et
  `?motion=on` force l'animation pour pouvoir la vérifier.
- Si anime.js ne charge pas, la page reste lisible : les états de départ
  se posent en JS, jamais en CSS.
- Commentaires en français, et ils expliquent le *pourquoi* d'une valeur.
  Ne retire aucun commentaire existant.
- Après toute modification de CSS ou de JS :
  `python outils/numeroter_versions.py`.
- Un fichier neuf doit être déclaré dans `outils/fichiers_du_site.py`,
  sinon il ne part pas en ligne.
- Ne publie rien. `cyq publier` ne se lance pas de ta propre initiative.

---

## Lot 1 — deux réglages de cadrage dans le héros

1. **Descendre très légèrement le titre.** Le bloc `.hero__copy`
   commence trop haut par rapport à la carte de droite. Ajoute une
   respiration au-dessus du titre, de l'ordre de 24 à 40 px sur grand
   écran, en valeur fluide pour qu'elle fonde à mesure que la fenêtre
   rétrécit, et nulle sous 900 px de large où le héros passe en une
   colonne. Ne touche pas au `padding: 156px` de `.hero__in`, qui dégage
   la nav fixe : c'est la colonne de gauche qu'on descend, pas le héros.
2. **Décaler la maquette vers la droite.** `.hero__stage` est centré dans
   sa colonne. Pousse-le un peu vers la droite — marge ou `justify-self`,
   pas une `transform`, qui entrerait en conflit avec l'animation
   d'ouverture et avec `[data-ballon]`. Le décalage doit retomber à zéro
   sous 1100 px, là où la carte perd déjà son inclinaison, et la carte ne
   doit jamais toucher ni dépasser le bord arrondi de la coque — vérifie
   à 1280, 1440 et 1920 px.

Les deux valeurs portent un commentaire disant *pourquoi* ce chiffre-là.

## Lot 2 — le héros devient un carrousel de modules

La disposition actuelle ne change pas : texte à gauche, carte penchée à
droite, même taille, même inclinaison, même ombre. Ce qui change, c'est
que la carte montre tour à tour **les six modules** au lieu de la seule
file d'attente.

- Les six scènes viennent du fragment, pas d'une copie : supprime la
  maquette écrite à la main dans le héros et pose à sa place six repères
  `<!-- cyq:maquette module=… -->`, un par vue, chacun dans son conteneur
  de diapositive. Puis `python outils/fragments.py` pour les remplir.
  Au besoin, étends `outils/fragments.py` pour accepter plusieurs blocs
  `maquette` dans une même page — vérifie d'abord s'il le fait déjà.
- **Défilement automatique toutes les 3 s.** Transition en fondu croisé,
  `opacity` et un très léger déplacement, rien d'autre. Les six
  diapositives sont empilées au même endroit ; la hauteur du bloc est
  celle de la plus haute, figée, pour que le héros ne saute pas à chaque
  changement — mesure-la en JS après chargement des polices plutôt que
  d'écrire un chiffre en dur, comme `page-home.js` le fait déjà pour la
  hauteur du `h1` (l. 315).
- **Une flèche pour aller plus vite.** Un vrai `<button>`, pas un `<div>`
  cliquable, avec un `aria-label` traduit dans les cinq langues. La scène
  est décorative et porte `aria-hidden` : la flèche vit donc **hors** du
  sous-arbre masqué, sinon le clavier atterrit sur du décor — c'est la
  remarque déjà écrite en tête de `outils/communs/maquette.html`. Un clic
  avance d'un cran et **réarme le minuteur à zéro**.
- **Des pastilles** sous la carte ou le long d'un bord, une par module,
  qui disent où l'on en est et permettent d'aller directement à une vue.
  Même exigence de bouton réel et d'étiquette traduite.
- **Le minuteur se met en pause** au survol de la carte, quand une
  diapositive a le focus clavier, et quand l'onglet passe en arrière-plan
  (`visibilitychange`) : une animation qui tourne dans un onglet caché ne
  sert personne et mange de la batterie.
- **`prefers-reduced-motion: reduce`** : pas de défilement automatique du
  tout. La première vue s'affiche, la flèche et les pastilles continuent
  de marcher, et le changement est instantané plutôt que fondu.
  `?motion=on` rétablit le comportement complet, comme ailleurs sur le
  site.
- **Sans JS, ou si anime.js ne charge pas**, une seule vue reste visible
  et lisible — celle de la file d'attente. Les cinq autres sont masquées
  par le script au démarrage, jamais par la feuille de style.
- L'animation d'ouverture (`[data-hero="embed"]`) continue de s'appliquer
  au cadre du carrousel, pas à chaque diapositive.

## Lot 3 — des scènes fidèles à ce que le bot envoie vraiment

C'est le lot le plus important, et le plus long. La scène `queue` est
bonne parce qu'elle ressemble à un vrai message Discord. Les cinq autres
sont des suppositions. **Aucune invention** : chaque scène doit
reproduire ce que le bot envoie réellement.

Pour chaque module, va lire le code qui construit le message dans
`bot/cogs/` avant d'écrire une ligne de HTML :

| Scène | Où est la vérité |
| --- | --- |
| `queue` | `queue_config.py`, `party.py`, `match.py` |
| `mmr` | `classement.py`, `match.py` |
| `duel` | `duel.py` |
| `clan` | `clan.py`, `clan_war.py`, `clan_tickets.py` |
| `securite` | `antiraid.py`, `antilink.py`, `guard.py`, `moderation.py` |
| `options` | `config.py`, `wizard.py`, `welcome.py`, `logs.py` |

Relève, pour chacun : le titre de l'embed, ses champs et leurs noms
exacts, la couleur de la barre latérale, l'auteur, le pied de page,
l'horodatage, les libellés des boutons et leur style (primaire,
secondaire, danger, désactivé), les menus déroulants, et les textes —
dans leur version `fr` de `bot/locales/`, puisque la page de référence
est en français.

Et reproduis la **chrome de Discord** telle qu'elle est, pas telle qu'on
l'imagine : la barre de salon avec son `#`, l'avatar et le badge `APP`,
la barre de couleur à gauche de l'embed, les champs en ligne sur trois
colonnes, les boutons sous le message et non dedans, les réactions sous
les boutons. Reprends la structure `mock__*` de la scène `queue`, qui est
déjà juste — ne crée pas un second jeu de classes.

Si une information manque dans le code du bot, dis-le dans ton compte
rendu et laisse la scène en l'état plutôt que de combler le trou.

Tout ça se modifie dans `outils/communs/maquette.html` uniquement, puis
`python outils/fragments.py` repropage dans `index.html` **et** dans
`modules.html`, qui montre les mêmes scènes. Vérifie que les deux pages
restent correctes.

## Lot 4 — la section des six modules, en bas

Elle est aujourd'hui en rangées `.mrow` : scène d'un côté, titre et
paragraphe de l'autre, en alternance. Le principe reste, la mise en page
change. Deux références, et elles ne disent pas la même chose :

- **MEE6** (`docs/references-accueil/ref-mee6-texte.png`) donne le
  contenu de la colonne de texte : titre, paragraphe long, deux actions.
- **Codex** (`docs/references-accueil/ref-codex-cadre.png`) donne le
  traitement du visuel et les proportions, et c'est lui qui l'emporte
  quand les deux divergent.

Ouvre les deux images avant d'écrire une ligne de CSS, et compare-les à
`docs/references-accueil/actuel-rangee-module.webp`, qui est l'état
d'aujourd'hui.

### La présentation, façon Codex

La scène Discord n'est plus posée nue sur le fond : elle est **encadrée**.

- Un grand cadre arrondi, large — autour de 55 à 60 % de la largeur de
  la rangée — avec son propre fond, plus clair que la page. La scène est
  posée **dedans**, avec une marge généreuse en haut et sur les côtés, et
  elle **sort du cadre par le bas** : le bord inférieur la coupe. C'est
  ce débord qui donne la profondeur ; une scène entièrement contenue
  retombe à plat. `overflow: clip` sur le cadre, et la coupe tombe sur
  une zone lisible de la maquette, jamais au milieu d'un bouton.
- Le fond du cadre est un **dégradé doux**, du plus clair en haut à
  gauche vers le fond de page en bas à droite. **Attention** : le
  dégradé lilas de la capture est la couleur de Codex, pas la nôtre.
  `home.css` n'a qu'un accent, `--accent #C08A5A`, **un seul emploi par
  écran** — et le héros s'en sert déjà. Construis le dégradé avec
  `--panel`, `--hair` et des crèmes très peu opaques tirés de `--ink`.
  N'importe quel bleu ou violet ici serait une couleur venue d'ailleurs.
  Si une touche de cuivre est tentante, elle ne peut apparaître que sur
  **une seule** des six rangées.
- La scène garde son ombre portée et son léger flottement
  (`[data-ballon]`), mais **perd son inclinaison** : dans un cadre, une
  maquette penchée se lit comme une erreur de montage.
- Le second panneau flottant de la capture — la petite fenêtre posée en
  bas à droite, par-dessus le reste — est à reprendre **seulement** là où
  le module a vraiment un second écran à montrer (le panneau de config
  du dashboard pour `options`, le ticket pour `clan`). Pas de panneau
  décoratif qui ne montrerait rien.

### La colonne de texte

- Nettement plus étroite que le visuel, **centrée verticalement** sur
  lui et non alignée en haut.
- Un sur-titre discret facultatif, un titre large qui **tient sur deux
  ou trois lignes** — pas un titre d'une seule ligne, c'est le rythme de
  la capture —, puis un paragraphe long et aéré.
- Puis **deux actions** : une pleine (« Ajouter à Discord », qui
  réutilise `.pill--discord` et `data-invite`) et une fantôme
  (« En savoir plus », vers l'ancre du module sur `modules.html`).
  Codex n'en a pas ; nous en gardons deux, parce que l'invitation est la
  raison d'être de la page. Mais elles restent discrètes : pas de
  troisième action, pas de liste à puces, pas de badge.

### Le reste

- L'alternance gauche/droite est conservée (`.mrow--inv`), et l'espace
  vertical entre deux rangées augmente franchement : les rangées doivent
  respirer et se lire comme des sections, pas comme les lignes d'un
  tableau.
- Sous 900 px, tout repasse en une colonne, cadre au-dessus du texte, et
  les deux actions s'empilent proprement à 375 px. À cette largeur le
  cadre perd sa marge intérieure et la scène peut cesser de déborder :
  un débord sur un écran de téléphone ne se lit plus comme de la
  profondeur, juste comme du contenu coupé.
- Les nouveaux textes et étiquettes passent par `data-i18n`, écrits dans
  `fr.js` puis `python outils/verifier_langues.py --completer`.

Ne touche pas aux ancres des rangées (`#queue`, `#mmr`, `#duel`,
`#clan`, `#securite`, `#options`) : des liens y mènent.

---

## Avant de dire que c'est fini

```
python outils/fragments.py
python outils/numeroter_versions.py
.\cyq verifier
```

Puis sers le site et regarde-le pour de vrai :

```
.\cyq local
```

- `http://localhost:8765/index.html` — le carrousel tourne, la flèche
  avance, les pastilles suivent, rien ne saute en hauteur.
- `http://localhost:8765/index.html?motion=on` en
  `prefers-reduced-motion: reduce` — la variante calme, puis l'animation
  forcée.
- La console : zéro erreur, zéro avertissement nouveau.
- 375 px de large, puis 1280, 1440 et 1920.
- `modules.html`, qui partage les mêmes scènes.
- Thème clair (`html[data-theme="light"]`) et thème sombre.

Termine en disant **ce que tu as vérifié et ce que tu n'as pas pu
vérifier**. Ne publie pas.
