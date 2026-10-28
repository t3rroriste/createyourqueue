# Prompt pour Claude Design — refaire les six maquettes de `modules.html`

> À coller tel quel. Tout ce qui suit s'adresse à Claude Design.

---

## 0. La demande, en une phrase

Les six maquettes de la page `modules.html` du site CreateYourQueue doivent
être refaites. Deux reproches aux maquettes actuelles :

1. **Elles ne ressemblent pas à Discord.** Ce sont des listes abstraites
   (lignes, pilules, puces) qui pourraient illustrer n'importe quel SaaS.
   Or le produit *vit* dans Discord : la personne qui lit cette page doit
   reconnaître l'endroit où le bot agit — salons, messages, embeds,
   boutons, salon vocal, liste de membres, commandes slash.
2. **Elles ne montrent pas ce que le produit fait.** Les visuels actuels
   ont été composés avant que les modules ne soient décrits précisément ;
   ils illustrent des idées vagues, pas les fonctions réelles. La section 2
   de ce document explique le projet pour que tu puisses les recomposer
   sur du concret.

Troisième contrainte, nette : **plus de pied de maquette.** Les deux ou
trois pilules alignées sous chaque maquette (`2 × 5`, `preset · ranked`,
`départ 1 000`, `MVP +15`, `12 membres`, `online`, `99.9 %`…) doivent
disparaître partout. Elles font « étiquette de spécification » collée sous
une image, et c'est exactement ce qui trahit la maquette. Si une
information de ce genre compte vraiment, elle doit vivre **à l'intérieur**
de l'interface Discord simulée — dans l'embed, dans le nom du salon, dans
le texte d'un message — pas en légende dessous.

Et une contrainte qui ne se négocie pas : **la direction artistique
actuelle ne change pas.** On ne veut pas les couleurs de Discord. On veut
les *formes* et la *grammaire* de Discord, rendues dans la palette du
site. Détail en section 3.

---

## 1. Le contexte technique, avant tout le reste

- Site **statique**, servi tel quel par Apache. Pas de build, pas de
  bundler, pas de npm, **aucune dépendance nouvelle** (la seule du projet
  est anime.js 4.5.0, déjà copiée dans `assets/js/vendor/`).
- HTML + CSS + JS **vanilla**, ES5 prudent, IIFE, `'use strict'`.
- Les fichiers concernés :
  - `modules.html` — le balisage des six maquettes (blocs
    `<div class="mod__visual" aria-hidden="true" data-mod-visual>`).
  - `assets/css/modules.css` — la section `/* === maquettes === */`,
    c'est-à-dire tout ce qui commence par `.mock`.
  - `assets/js/page-modules.js` — **à ne pas toucher.** Il anime
    `[data-mod-visual]` à la révélation et pose un parallaxe borné sur
    `.mock` via la variable `--flot`. Ton balisage doit donc garder
    l'élément racine `.mock` à l'intérieur de `.mod__visual`, et ne jamais
    poser de `transform` dessus en CSS (le JS en est propriétaire).
- Les maquettes sont **décoratives** : `aria-hidden="true"` sur le
  conteneur, aucun texte à traduire dedans (c'est pour ça que les pseudos
  — Nova, Mira, Kite, Dax — et les chiffres sont en dur, et c'est à
  garder). Aucune clé `data-i18n` dans une maquette.
- Après toute modification de CSS ou de JS, le projet exige
  `powershell -ExecutionPolicy Bypass -File bump-version.ps1` (il
  renumérote les `?v=` et casse le cache du navigateur).

---

## 2. Le projet — lis cette section, elle est le cœur de la demande

### 2.1 Ce qu'est CreateYourQueue

**Un bot Discord de file d'attente et de matchmaking pour serveurs de jeu
compétitif**, accompagné d'un panneau web (le site que tu vois) qui sert
uniquement à le configurer. Le bot n'a pas d'interface à lui : tout ce
qu'il fait, il le fait **dans Discord**, par des messages, des embeds, des
boutons, des salons et des rôles qu'il crée lui-même.

Le public : des organisateurs de scrims, de tournois internes, de ligues —
des gens qui, sans le bot, composent les équipes à la main dans un salon
texte et recopient les scores dans un tableur.

### 2.2 Le déroulé d'une session, vu de Discord

C'est ce film-là que les six maquettes doivent raconter, chacune pour son
module :

1. Un organisateur ouvre une queue (commande slash, ou depuis le panneau
   web). Le bot publie **une annonce** dans le salon dédié : nom de la
   queue, format (`2 × 5`), places prises, et des **boutons** pour
   rejoindre / quitter.
2. Les joueurs cliquent. Le message **se met à jour en direct** : les
   places se remplissent, équipe par équipe. Un **salon vocal d'attente**
   rassemble tout le monde avant le lancement.
3. Les équipes se forment — soit automatiquement, soit par **élection de
   deux capitaines au vote**, qui se partagent ensuite l'effectif.
4. La partie se joue ailleurs (dans le jeu). Au retour, le score est
   **confirmé par un vote** dans un temps imparti, et un **MVP est élu au
   vote**.
5. Le bot attribue les points, met à jour le **classement MMR** et le
   republie dans son salon.

### 2.3 Les six modules, et ce que chaque maquette doit montrer

Pour chacun : ce que le module fait réellement (texte de la page, déjà
écrit et à ne pas contredire), puis la scène Discord à composer. Les
scènes proposées sont des recommandations fortes — tu peux les affiner,
pas les remplacer par de l'abstrait.

---

**01 — Queue / Scrims** (`#queue`)

*Ce que ça fait* : la file d'attente et la composition des équipes. De 2 à
6 équipes, de 1 à 6 joueurs chacune, chaque équipe avec son nom et sa
couleur (couleur appliquée aussi au rôle Discord de l'équipe). Vote des
capitaines en option. Salon vocal de rassemblement. Mot de passe pour
fermer la queue. Dix presets de configuration.

*La scène* : **l'annonce de queue dans un salon texte.** Un message du bot
(avatar + nom du bot + badge « APP »), un **embed** avec barre de couleur
à gauche, le titre de la queue, le format, et deux colonnes d'équipes où
les places occupées portent un pseudo et les places libres sont des
emplacements vides. Sous l'embed, **une rangée de boutons Discord** :
`Rejoindre`, `Quitter`, `Lancer`. Un compteur de places qui a l'air vivant
(`6/10`). En-tête de salon en haut, avec le `#` et le nom du salon.

---

**02 — Match & MMR** (`#mmr`)

*Ce que ça fait* : le classement se tient tout seul. MMR de départ, points
par victoire, points par défaite, bonus MVP (élu au vote), bonus de série
à partir de N victoires. Durées de vote réglables. Le classement se publie
automatiquement dans le salon qu'on lui donne.

*La scène* : **le classement publié en embed** dans son salon, ou le
message de fin de match. Un embed avec un titre (`Classement — saison 3`),
des lignes de joueurs avec rang, pseudo, points et variation, alignées
comme Discord rend un bloc monospace. Idéalement, une trace du **vote
MVP** : un petit message ou une rangée de boutons avec décompte. Pas de
graphique, pas de dataviz inventée.

---

**03 — Duel** (`#duel`)

*Ce que ça fait* : l'affrontement direct, sans passer par la file. Une
équipe en défie une autre, le bot ouvre le duel et annonce les
participants. Score confirmé par vote dans le temps imparti. Chaque duel
se range dans le salon qu'on lui a donné.

*La scène* : **le message de défi, puis la confirmation de score.** Un
embed de face-à-face (`Alpha` contre `Bravo`), le score proposé, et le
**vote de confirmation** : boutons `Confirmer` / `Contester` avec un
décompte de voix et un temps restant (`18/25 · 1 min 58 s`). C'est la
maquette la plus « message Discord » des six : c'est voulu.

---

**04 — Clan & ClanWar** (`#clan`)

*Ce que ça fait* : les équipes permanentes et leurs guerres. On choisit
une catégorie, les salons de clan s'y créent tout seuls. Chaque clan a son
chef, qui peut transmettre son rôle. Les adhésions s'annoncent dans le
salon choisi. Le résultat des guerres compte au classement.

*La scène* : **la barre latérale des salons de Discord.** C'est la
maquette qui doit le plus ressembler à l'application : une catégorie en
petites capitales avec son chevron (`CLANS`), et dessous la liste des
salons créés par le bot — salons texte avec l'icône `#`, salons vocaux
avec l'icône haut-parleur, et **sous un salon vocal, les membres connectés
dedans avec leurs pastilles d'avatar**, exactement comme Discord les
affiche. Un rôle de chef visible (pastille de couleur sur un pseudo, ou
mention de rôle).

---

**05 — Modération & sécurité** (`#securite`)

*Ce que ça fait* : ce qui tourne en arrière-plan. Anti-lien (garde les
adresses hors des salons où on n'en veut pas), nettoyage automatique des
messages devenus inutiles, anti-raid déclenché aux seuils choisis. **Dix
journaux indépendants**, chacun dans son salon : vocal, messages, queue,
match, duel, clan, commandes, arrivées, modération, serveur.

*La scène* : **un salon de journal qui défile.** Des lignes de log comme
le bot les écrit vraiment : horodatage, icône, et une phrase avec des
mentions (`@Nova`) et des salons (`#queue-5v5`) mis en forme comme Discord
les rend — pastille de fond sur la mention. Par exemple : un lien
supprimé, un message nettoyé, un anti-raid déclenché. C'est la maquette
qui porte la notion de trace écrite : elle doit se lire comme un
historique, pas comme un tableau de bord. Les trois interrupteurs actuels
(anti-link / auto-clean / anti-raid) n'ont rien à faire là : les
interrupteurs, c'est le panneau web, pas Discord.

---

**06 — Options** (`#options`)

*Ce que ça fait* : le reste des réglages. Cinq langues (fr, en, es, de,
ko), qui renomment au passage les salons et les rôles créés par le bot. On
désigne les salons — commandes, annonces, vocal d'attente, résultats,
classement — et les rôles : organisateur, notification de queue, chef de
clan, transfert.

*La scène* : **une commande slash en train d'être tapée**, avec le menu
d'autocomplétion de Discord ouvert au-dessus de la barre de saisie : le
nom de la commande, son argument surligné, et la liste des choix proposés.
Ou, en variante, **la carte de profil du bot** (avatar, nom, badge, statut
en ligne). L'idée à faire passer : le bot se pilote aussi depuis Discord,
et il s'adapte au serveur. Pas de liste de réglages clé/valeur : c'est
littéralement ce que fait le panneau web, et ça n'illustre rien.

---

## 3. La direction artistique — ce qui ne change pas

Le site a **deux D.A. étanches** qui ne partagent aucun token.
`modules.html` dépend de `home.css` : c'est cette palette-là, et elle
seule.

```
--bg       #0A0908   noir chaud, jamais bleuté
--panel    #121110
--raised   #24211F
--raised-2 #2E2A28
--ink      #F4F1EC                  texte plein
--ink-60   rgba(244,241,236,.60)    plancher du texte courant
--ink-40   rgba(244,241,236,.40)    JAMAIS de texte courant : filets, icônes
--hair     rgba(244,241,236,.08)    filets
--film     rgba(244,241,236,.05)    fond des pilules fantômes
--accent   #C08A5A                  cuivre
--r-card 24px · --r-media 20px · --r-pill 999px
police Geist
```

Les règles qui encadrent cette palette :

- **L'accent cuivre : un seul emploi par écran.** Pas un par élément — un
  par module, et c'est déjà beaucoup. Il sert à désigner *une* chose (la
  couleur d'une équipe, une variation positive, le rôle du chef), pas à
  colorer une interface.
- **Pas de bleu Discord, pas de `#5865F2`, pas de blurple**, pas de vert
  `#23A55A`, pas de rouge d'erreur Discord. Les boutons « primaire » de
  Discord se rendent ici en `--ink` sur fond sombre ou en `--film` ; la
  barre de couleur d'un embed se rend en `--accent` ou en `--ink-40`
  selon qu'elle est l'accent de l'écran ou non.
- **Pas de dégradé, pas d'ombre portée colorée.** L'élévation se fait par
  `--panel` / `--raised` / `--raised-2` et par `--hair`. L'ombre unique
  déjà en place sur `.mock` (`0 60px 120px -60px rgba(0,0,0,.9)`) peut
  rester.
- **Pas de captures d'écran, pas d'images.** Tout est composé en HTML/CSS
  avec les tokens, pour que les maquettes vieillissent avec le site. Les
  avatars sont des formes CSS (cercles en `--raised-2`, éventuellement une
  initiale) — pas de photos, pas de SVG de marque. Seul
  `assets/img/logo.png` est disponible, pour l'avatar du bot.
- **Les icônes** sont des `<svg>` inline, trait 2, `stroke-linecap: round`,
  `currentColor`, 13 à 16 px, comme partout ailleurs sur le site. Il en
  faut : `#` (texte), haut-parleur (vocal), chevron (catégorie), horloge,
  bouclier. Dessine-les, ne les importe pas.

Autrement dit : **la grammaire de Discord, la peau du site.** Quelqu'un
qui connaît Discord doit reconnaître la disposition au premier regard ;
quelqu'un qui connaît le site ne doit pas voir de rupture de palette.

---

## 4. Les contraintes de réalisation

- **Animations en `transform` et `opacity` uniquement.** Pas de
  `box-shadow` animée, pas de `filter: blur()` animé sur une grande
  surface, rien qui déclenche un layout dans une boucle. Et en pratique :
  **n'ajoute aucune animation.** Les maquettes sont animées par
  `page-modules.js`, qui ne doit pas être touché. Si une scène a besoin
  d'un état « vivant » (un compteur, un vote en cours), il est **figé**
  dans un état crédible.
- **Aucun état initial d'animation en CSS.** Pas d'`opacity: 0`, pas de
  `translate` dans `modules.css` — c'est une règle écrite en tête du
  fichier : si le script échoue, la page doit rester entièrement lisible.
  Les états de départ sont posés en JS, et le JS existant s'en occupe.
- **`prefers-reduced-motion: reduce`** : le bloc final de `modules.css`
  neutralise déjà `transform` / `opacity` / `filter` sur `.mock`. Si tu
  introduis un nouvel élément susceptible d'être transformé, ajoute-le à
  ce bloc.
- **375 px de large doit tenir.** Les media queries existantes (`1100px`,
  `780px`) passent les modules en une colonne et retirent le `max-width`
  de `.mock`. Une barre latérale de salons ou une rangée de boutons doit
  survivre à cette largeur sans débordement horizontal : prévois le repli.
- **Commentaires en français**, et ils expliquent le *pourquoi* d'une
  valeur, pas le *quoi* de la ligne. C'est la convention de tout le code
  du projet, CSS compris.
- **Nommage** : reste sur la convention BEM en place (`.mock`,
  `.mock__bar`, `.mock__row`, `.mock__embed`…). Tu peux renommer et
  réorganiser librement à l'intérieur de `.mock`, mais garde ce préfixe —
  et **supprime les classes devenues mortes** plutôt que de les laisser
  traîner (`.mock__foot`, `.mock__pill`, `.mock__pill--acc`, `.mock__tog`,
  `.mock__chip`, `.mock__tag` si tu ne les réemploies pas).
- **Jamais de données inventées qui ressemblent à de vraies données.** Les
  pseudos restent les mêmes quatre (Nova, Mira, Kite, Dax) ; les chiffres
  restent cohérents avec le texte du module (un `2 × 5` affiché = 10
  places, pas 8).

---

## 5. Ce qu'il ne faut pas faire

- Pas de pied de maquette, pas de rangée de pilules de légende, pas
  d'étiquette de spécification sous l'interface. C'est le point de départ
  de la demande.
- Pas de « harmonisation » avec `app.css` (la D.A. du dashboard) : les
  deux directions sont séparées **exprès**.
- Pas de nouvelle dépendance, pas de CDN, pas de police supplémentaire.
  Discord utilise gg sans / Whitney : **on ne les charge pas**, Geist fait
  le travail.
- Pas de reproduction d'un logo, d'un badge ou d'une marque Discord. On
  simule une disposition familière, on ne copie pas une identité.
- Ne touche pas au reste de `modules.html` (nav, en-tête, textes des
  modules, CTA, pied) ni aux fichiers de langue : seuls les six blocs
  `.mod__visual` changent.
- Ne touche pas à l'aperçu d'annonce du dashboard (clé `q.previewTitle`) :
  celui-là porte volontairement la mention « aperçu de la mise en forme du
  message, pas une copie de l'interface Discord », et il garde sa retenue.
  La licence Discord s'arrête aux maquettes de `modules.html`.

---

## 6. Le livrable

1. Les **six blocs HTML** remplaçant le contenu de chaque
   `<div class="mod__visual" aria-hidden="true" data-mod-visual>` de
   `modules.html`, dans l'ordre : queue, mmr, duel, clan, securite,
   options.
2. La **section « maquettes » de `assets/css/modules.css`** réécrite — tout
   ce qui commence par `.mock` — commentaires en français inclus, plus les
   ajouts nécessaires aux media queries `1100px` / `780px` et au bloc
   `prefers-reduced-motion: reduce`.
3. Une note courte disant, par maquette, **quelle scène Discord** tu as
   choisie et pourquoi, et ce que tu n'as pas pu rendre dans cette
   palette.

Et dis ce que tu as vérifié : la page servie en local
(`python -m http.server 8765` depuis `Site Dashboard/`, puis
`http://localhost:8765/modules.html?motion=on`), la console sans erreur, le
rendu en `prefers-reduced-motion: reduce`, et le rendu à 375 px.
