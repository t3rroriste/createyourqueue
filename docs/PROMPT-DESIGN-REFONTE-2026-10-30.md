# Prompt pour Claude Design — grossir la vitrine et le panneau

> À coller tel quel. Tout ce qui suit s'adresse à Claude Design.
> Rédigé le 30 octobre 2026, après lecture du code en place.

---

## 0. La demande, en une phrase

Le site **CreateYourQueue** (`cyqbot.eu`) est juste, propre, et **trop
sobre** : la typographie est petite, l'accent est tenu en laisse au point de
ne plus se voir, la page se lit en vingt secondes et personne n'a de raison
d'y rester. On veut la **même palette**, le même noir chaud, la même rigueur
— mais **en grand**, avec du relief, et avec de quoi retenir quelqu'un.

**Ce qu'on attend de toi : des maquettes, pas du code.** Quatre écrans, en
deux largeurs chacun :

| # | Écran | Desktop | Mobile |
|---|---|---|---|
| A | Accueil / vitrine (`index.html`) | 1440 × hauteur libre | 390 × hauteur libre |
| B | Panneau — vue d'ensemble (écran neuf) | 1440 | 390 |
| C | Panneau — une section de réglages | 1440 | 390 |
| D | Pied de page + appel à l'action final | 1440 | 390 |

Plus, en texte à côté des maquettes : les **valeurs exactes** (tailles,
graisses, interlignes, rayons, espacements, opacités) et les **tokens neufs**
que tu introduis. C'est Claude Code qui implémentera ensuite, dans du HTML et
du CSS écrits à la main : une maquette dont on ne peut pas tirer de valeurs
ne sert à rien.

---

## 1. Le produit, parce que tu ne le connais pas

**CreateYourQueue** est un **bot Discord de file d'attente et de matchmaking**
pour serveurs de jeu compétitif, accompagné d'un **panneau web** qui le règle.

- Un organisateur ouvre une **file** (« queue ») dans un salon Discord. Le bot
  poste une annonce ; les joueurs réagissent pour s'inscrire ; quand la file
  est pleine, le bot **compose les équipes**, crée les **salons vocaux** et y
  **déplace** les joueurs.
- Autour de ça : **MMR et rangs**, **classement**, **duels 1v1**, **clans** et
  guerres de clans, **presets** de configuration, **programmation** d'ouvertures
  automatiques, et un volet **sécurité** (anti-raid, anti-lien, nettoyage
  automatique, dix journaux d'événements).
- Le site a trois faces :
  - **`cyqbot.eu`** — la vitrine. Un héros, les six modules expliqués, un
    appel à l'action, un pied. C'est l'écran A.
  - **`dashboard.cyqbot.eu`** — le panneau. Connexion Discord, choix du
    serveur, puis **23 sections** de réglages rangées en six catégories (Le
    bot, Queue, Le serveur, Accès, Sécurité, Suivi). Ce sont les écrans B et C.
  - **`status.cyqbot.eu`** — la page d'état. Hors périmètre, mais elle existe
    et elle alimente un élément du pied (voir §7.6).

La personne qui arrive sur la vitrine est **un administrateur de serveur
Discord**, pas un joueur. Ce qu'elle veut savoir en dix secondes : *est-ce que
ce bot fait tourner mes scrims sans que j'aie à m'en occuper, et est-ce que
c'est sérieux ?*

---

## 2. La référence, lue précisément

Cinq captures t'ont été données. Ce sont des captures de **fakecrime.bio**,
un service de pages de profil — **un autre produit**. On prend son **énergie
visuelle**, pas son modèle, pas ses couleurs, pas ses contenus.

### 2.1 Ce qu'il faut prendre

**Le tableau de bord (capture 1)**
- Rail de gauche permanent, avec un **champ de recherche ⌘K** en haut.
- Navigation **groupée sous des titres de catégorie** repliables.
- Une rangée de **quatre cartes-chiffres** en haut du contenu : petite icône,
  libellé discret, **grande valeur**. C'est la première chose qu'on voit.
- Un panneau **« What's Next »** : une progression vers un palier, avec une
  **piste de jalons** (250 / 500 / 1 000 / 2 500 / 5 000 / 10 000) dont les
  segments atteints sont remplis.
- Une **jauge de stockage** avec une pastille d'incitation à droite.
- Une rangée de **cartes-raccourcis** (quatre tuiles, titre + une phrase).
- Une colonne de droite **« Manage Account »** : des lignes avec une **tuile
  d'icône colorée**, un titre, une phrase, un chevron.
- En bas du rail : la **carte de compte** (avatar, pseudo, URL, bouton de
  sortie). En haut du rail : une **carte promo** encadrée, teintée.

**La vitrine (captures 2 à 5)**
- Un titre **énorme**, sur deux lignes, dont **la seconde ligne est dans la
  couleur d'accent**. C'est l'effet qui fait toute la différence de taille
  perçue.
- Un **objet-produit lumineux** à droite du titre : le logo en très grand,
  avec un **halo** derrière lui et une ombre portée.
- Un **champ de conversion dans le héros** — ici « fakecrime.bio/you » avec un
  bouton collé dedans.
- Une **rangée de chiffres** sous le héros : 49K utilisateurs, 1,3K premium,
  2,7M vues, fondé en 2020.
- Une section de fonctions en **grille de deux cartes**, chacune avec un
  **panneau visuel en haut** (pastilles de couleur, échantillons de polices,
  un lecteur de musique dessiné) et titre + phrase en bas, précédés d'une
  **petite icône d'accent**.
- Une section communauté : **pile d'avatars qui se chevauchent**, titre
  énorme, un paragraphe où les **chiffres sont en gras**, deux gros boutons
  pilule, et en fond une **mosaïque assombrie** de contenus réels.
- Un **pied de page en quatre colonnes** : logo + description + **pastille
  « All Systems Operational »** à points vert, puis trois colonnes de liens,
  puis une ligne de copyright avec un **sélecteur de langue en pilule** et un
  bouton Discord.
- Un **appel à l'action répété** juste au-dessus du pied.
- Une **invite de langue** en bas à droite (« Switch to Français ? »).

### 2.2 Ce qu'il ne faut surtout pas prendre

- **Le rose.** La palette de CreateYourQueue ne bouge pas (§3.1).
- **Le modèle de produit.** Pas de « claim your URL », pas de pseudo à
  réserver, pas de compteur de vues, pas de badges de profil, pas de premium.
  CreateYourQueue n'a rien de tout ça. Transposer la **forme** de ces blocs à
  ce que le produit fait vraiment est le travail ; recopier leurs libellés est
  une faute.
- **Les faux chiffres.** Voir §6, c'est la règle la plus dure du dépôt.
- **La pile d'avatars d'utilisateurs.** On ne dispose d'aucun avatar, et les
  montrer poserait un problème de vie privée. §7.5 donne le remplacement.

---

## 3. Le système en place : ce qui est à toi, ce qui ne l'est pas

Tout est écrit dans `docs/DESIGN-SYSTEM.md`, qui fait loi. Voici le contrat
en vigueur, et **exactement** ce que tu as le droit de déplacer.

### 3.1 Couleur — INTOUCHABLE

| Token | Valeur | Emploi |
|---|---|---|
| `--bg` | `#0A0908` | fond derrière la coque |
| `--panel` | `#121110` | la coque |
| `--raised` | `#24211F` | sections paires, carte flottante |
| `--raised-2` | `#2E2A28` | vignette dans la carte |
| `--ink` | `#F4F1EC` | titres, texte fort — 17,8:1 |
| `--ink-60` | `rgba(244,241,236,.60)` | **tout le texte courant** — 6,5:1 |
| `--ink-40` | `rgba(244,241,236,.40)` | décor seulement — 3,5:1 |
| `--hair` | `rgba(244,241,236,.08)` | filets |
| `--film` | `rgba(244,241,236,.05)` | fond des pilules fantômes |
| `--accent` | `#C08A5A` | cuivre — 6,3:1 |

Ces valeurs sont celles de `site/assets/css/home.css`, qui est la source de
vérité. `docs/DESIGN-SYSTEM.md` donne encore `#1B1918` et `#242120` pour
`--raised` et `--raised-2` : son tableau a pris du retard sur le code, c'est
le CSS qui a raison.

**Le noir est chaud** : il tire vers le brun, jamais vers le bleu. C'est ce
qui sépare cette direction d'un thème sombre générique. **N'introduis aucune
teinte neuve.** Pas de vert, pas de bleu, pas de violet — à **une** exception
près, le blurple Discord `#5865F2`, et **uniquement** sur un bouton qui mène
à Discord, parce que c'est une marque qu'on cite.

Si tu as besoin d'un signal d'état (opérationnel / dégradé / en panne), la
page d'état en a déjà un jeu : va le lire dans `site/assets/css/status.css`
et reprends-le tel quel. N'en invente pas un second.

### 3.2 L'accent — LA RÈGLE QU'ON ASSOUPLIT, ET COMMENT

La règle actuelle, écrite dans le CSS et dans le design system :

> « Trois emplois autorisés : la flèche d'un CTA, le point de pagination
> actif, un indicateur de delta positif. **Jamais un fond, jamais un dégradé,
> jamais deux fois dans le même écran.** »

C'est précisément cette règle qui rend le site sobre au point d'être éteint.
**On l'assouplit, mais on l'écrit.** Le nouveau contrat, que tu dois respecter
et que Claude Code recopiera dans `docs/DESIGN-SYSTEM.md` :

1. **Un seul emploi « plein » par écran défilé**, c'est-à-dire un seul bloc
   où le cuivre couvre une surface : la seconde ligne du titre du héros, **ou**
   le bouton principal, **jamais les deux dans le même premier écran.**
   Recommandation : donne-le au **titre**, et laisse le bouton en crème.
2. **Texte sur fond cuivre : toujours `--bg` (#0A0908), jamais `--ink`.**
   Mesuré : `#0A0908` sur `#C08A5A` = **6,66:1** (passe AA partout) ;
   `#F4F1EC` sur `#C08A5A` = **2,65:1** (échoue, même en grand). Cette ligne
   n'est pas négociable, elle est arithmétique.
3. **Le halo est autorisé**, et c'est lui qui apporte le relief qui manque :
   un dégradé radial de `--accent` à **12 % au centre, 0 % au bord**, derrière
   un objet, jamais sous un texte, jamais au contact d'un bord de carte. Un
   seul par écran.
4. **Les dégradés de texte restent interdits.** Une seconde ligne de titre en
   cuivre **plein**, oui ; un dégradé cuivre→crème dans les lettres, non : il
   fait « template », c'est exactement ce qu'on fuit.
5. **Les micro-emplois ne comptent pas dans le quota** : flèche de CTA,
   curseur de frappe, segment de progression rempli, point actif, puce de
   liste. Ils sont déjà dans le système.

Tout ce que tu ajoutes au-delà, tu l'écris et tu le justifies.

### 3.3 Typographie — ON MONTE, ET C'EST LE CŒUR DU TRAVAIL

Famille unique : **Geist**, repli **Archivo**. Les graisses **400, 500 et
700** sont déjà chargées — tu peux donc utiliser le 700 sans rien ajouter.
**N'introduis aucune police.**

L'échelle actuelle, et ce qu'elle donne :

| Rôle | Aujourd'hui | Plafond réel |
|---|---|---|
| Titre héros | `clamp(2.5rem, 4.4vw, 4.25rem)`, graisse **500**, **bas de casse** | 68 px |
| Titre de section | `clamp(2rem, 3.4vw, 3.25rem)`, graisse 500 | 52 px |
| Chiffre marquant | `clamp(2.5rem, 4vw, 4rem)` | 64 px |
| Corps | 15 px / 1,6 | — |
| UI | 13–14 px | — |
| Label | 11 px, `.06em`, capitales | — |

Le rapport titre/corps est de **4,8×**. Dans la référence, il est au-dessus
de **7×**, et c'est la raison n°1 pour laquelle elle paraît « grande » et
notre page « petite ».

**Ce qu'on te demande de proposer**, avec les valeurs exactes :

- Un **titre de héros au moins à 7×** du corps : vise
  `clamp(3.25rem, 7.5vw, 6.5rem)` comme point de départ, `line-height` entre
  `.94` et `.98`, `letter-spacing` autour de `-.04em`. Donne tes valeurs
  définitives.
- **La graisse monte à 600 ou 700** sur le héros et les titres de section. Le
  500 actuel est trop fin pour cette taille : à 100 px, un 500 paraît mou.
- **Le bas de casse du héros** est une signature de la maison. Garde-le si tu
  peux le faire tenir en très grand ; si tu juges qu'il casse à cette échelle,
  propose l'alternative **explicitement**, avec les deux versions côte à côte
  dans la maquette, et dis laquelle tu recommandes. Ne tranche pas en silence.
- **Le titre reste à bords irréguliers** (ni justifié, ni `text-wrap: balance`) :
  les lignes **doivent** rester inégales. C'est écrit dans le design system.
- **Les chiffres marquants montent aussi** : ils sont l'autre levier de taille
  perçue, et `tabular-nums` reste obligatoire.
- **Le corps ne bouge pas.** 15 px / 1,6 à `--ink-60`. Grossir le corps
  n'agrandit pas une page, ça la rend bavarde.
- `:lang(ko)` porte `line-height: 1.75` : le coréen respire plus. Vérifie que
  tes titres tiennent en coréen — les cinq langues sont fr, en, es, de, ko.

### 3.4 Formes et respiration — ON GARDE

Quatre rayons, aucun rectangle : coque `36px`, carte `24px`, média `20px`,
pilule `999px`, disque `50%`, section empilée `32px 32px 0 0`.

Espacement : **8 / 16 / 32 / 64 / 120 / 200**. **Aucune valeur intermédiaire.**
Si une maquette a besoin de 48 px, c'est que la composition est à revoir.

Pas de bordure sur les cartes : la séparation se fait par contraste de fond
(`--panel` contre `--raised`) ou par filet à 8 %. **Une seule ombre** dans
tout le système : `0 60px 120px -60px rgba(0,0,0,.9)`.

Le **grain** (`feTurbulence` SVG en ligne, 3 %, sur toute la coque) reste. Il
fait une grande partie de la chaleur du noir ; ne le retire pas sous prétexte
qu'il ne se voit pas sur une maquette exportée.

### 3.5 Mouvement — LES RÈGLES DU DÉPÔT S'APPLIQUENT À TES MAQUETTES

Ce que tu dessines doit être **implémentable sous ces contraintes**, sinon la
maquette est un joli mensonge :

- Animations en **`transform` et `opacity` uniquement**. Pas de `box-shadow`
  animée, pas de `filter: blur()` animé sur une grande surface, rien qui
  déclenche un calcul de mise en page dans une boucle.
- Une seule bibliothèque : **anime.js 4.5.0**, déjà hébergée. **Aucune
  dépendance nouvelle**, pas de CDN, pas de npm. Le site est **statique** :
  pas de build, pas de bundler.
- **`prefers-reduced-motion: reduce` a toujours une variante calme.** Dessine-la :
  pour chaque écran animé, dis ce qui reste quand le mouvement est coupé.
- **Si anime.js ne charge pas, la page reste lisible.** Rien d'essentiel ne
  peut dépendre d'une animation.
- Courbes maison : `--e-out: cubic-bezier(.16,1,.3,1)` et
  `--e-soft: cubic-bezier(.4,0,.2,1)`.

### 3.6 Accessibilité — non négociable

- Un seul anneau de focus, jamais supprimé : `2px solid var(--ink)`,
  `outline-offset: 3px`.
- Tout texte courant à **`--ink-60` minimum**. `--ink-40` est du décor, jamais
  une phrase à lire.
- Toute maquette décorative est `aria-hidden` et ne contient **aucun texte à
  traduire**.
- Cinq langues : **fr · en · es · de · ko**. Un libellé qui ne tient que
  parce qu'il fait huit caractères en français est un piège : l'allemand en
  fera dix-huit. Prévois la place.

### 3.7 Points de rupture existants

| Feuille | Ruptures |
|---|---|
| `home.css` (vitrine) | `1100px`, `780px` |
| `modules.css` | `1100px`, `780px` |
| `dashboard.css` | `1240px` (montant), `900px`, `560px` |

**Garde-les.** En ajouter une est possible, mais dis-le et dis pourquoi.
À 900 px le rail du panneau passe déjà en **rangée horizontale défilante**, et
ses trois blocs deviennent des cases de la grille : c'est le mécanisme en
place, ne le remplace pas sans raison.

---

## 4. Ce qui existe déjà et que tu dois réemployer

Ne redessine pas ce qui est fait. Le dépôt contient trois ensembles mûrs :

**Les maquettes Discord (`modules.css`, ~90 classes `.mock__*`).** Un système
complet qui dessine Discord dans la palette du site : salon, liste de salons,
message, embed avec champs et pied, salon vocal, membres, commande slash,
menu, journal, tableau de scores, équipes. C'est **le** matériau visuel de la
maison, et il est sous-employé : il ne sert aujourd'hui que dans les six
modules, loin dans la page. Fais-le remonter.

**L'aperçu d'annonce du panneau (`dashboard.css`, classes `.dprev__*`).** Un
message Discord fidèle, alimenté en direct par les réglages : même titre,
mêmes lignes, mêmes champs, même pied que ce que le bot publie vraiment. Deux
animations existent, `.dprev.is-envoi` et `.dprev.is-retrait`.

**La barre de navigation en pilule flottante.** Présente sur toutes les pages,
elle s'efface au défilement et revient en haut. Elle est bonne : garde-la,
tu peux la faire respirer davantage.

Et un détail qui compte : le **titre du héros se tape déjà caractère par
caractère, en boucle**, avec un curseur cuivre. L'effet est en place
(`page-home.js`, `.hero__title.is-typing`). Ta composition doit en tenir
compte : la hauteur du titre est **figée après mesure** pour que rien ne
saute, donc un titre de deux lignes en réserve deux, toujours.

---

## 5. Écran A — l'accueil, en grand

L'accueil fait aujourd'hui, de haut en bas : **héros** (titre tapé + un bouton
d'invitation + un objet décoratif à droite), puis **les six modules repris en
entier** depuis la page Modules, puis un **appel à l'action**, puis un **pied
d'une seule rangée de cinq liens**. C'est tout. Pas un chiffre, pas une preuve,
pas une raison de rester.

Compose la page suivante. L'ordre est une proposition argumentée : si tu en
changes, dis pourquoi.

### 5.1 Héros

- **Titre énorme, deux lignes**, la seconde en cuivre plein. Il se tape en
  boucle (§4) : prévois que la **ligne colorée** supporte d'être écrite
  caractère par caractère — donc la couleur porte sur la ligne entière, pas
  sur un mot au milieu qu'il faudrait reconstituer lettre à lettre.
- **Une phrase de soutien** en dessous, `--ink-60`, 42 caractères de large au
  plus. Elle manque aujourd'hui sur l'accueil et c'est une perte : le titre
  seul ne dit pas ce qu'est le produit.
- **Deux actions**, pas une : l'action principale (« Invite le bot ») en
  pilule crème, et une action secondaire en pilule fantôme (« Voir une file
  en action », qui descend à la démo de 5.3). Aujourd'hui il n'y en a qu'une
  et elle sort du site.
- **L'objet lumineux à droite.** La référence met son logo en très grand avec
  un halo. Notre équivalent n'est pas le logo : c'est **l'annonce de file**
  — le message que le bot publie, dessiné avec les classes `.mock__embed` /
  `.dprev__*`, posé de biais, avec le halo cuivre à 12 % derrière. C'est la
  seule image qui dit le produit en une seconde. Le bloc `.matter` actuel,
  purement décoratif, lui cède la place.
- **La rangée de chiffres** juste sous le héros. **Lis la §6 avant de la
  dessiner** : les seuls chiffres réels disponibles sont *serveurs*, *files
  ouvertes en ce moment*, *disponibilité*. Dessine **l'état connu et l'état
  inconnu**, les deux.

### 5.2 Les trois étapes

Un ruban court, trois temps, juste après le héros : **invite le bot** →
**règle en deux minutes** → **ouvre ta première file**. Trois vignettes, une
phrase chacune. C'est le bloc qui répond à « combien ça va me coûter de temps »,
et il n'existe nulle part aujourd'hui.

Pas de gros numéros `01 / 02 / 03` : la documentation vient précisément d'être
débarrassée des siens parce qu'ils faisaient « page générée ». Trouve autre
chose pour dire l'ordre.

### 5.3 La démonstration — le bloc de rétention principal

**C'est l'élément qui doit retenir quelqu'un sur la page**, et c'est celui qui
manque le plus. Le dépôt a tout le matériel : le système `.mock__*` dessine
déjà Discord fidèlement.

Dessine une **scène Discord jouable** : l'annonce part dans le salon, les
joueurs s'inscrivent un par un en réaction, le compteur monte, la file se
remplit, les équipes se composent, les salons vocaux apparaissent et les
pseudos basculent dedans. En boucle, et **relançable à la main**.

Contraintes, à respecter dans le dessin :
- `transform` et `opacity` seulement.
- La boucle **ne tourne que quand le bloc est à l'écran**, et s'arrête quand
  l'onglet passe en arrière-plan.
- Variante calme sous `prefers-reduced-motion` : **l'état final, figé** — file
  pleine, équipes faites. Dessine cet état-là aussi, c'est lui que verront les
  gens qui ont coupé le mouvement.
- Décoratif : `aria-hidden`, aucun texte traduit dedans. Le texte qui explique
  la scène vit **à côté**, pas dedans.

### 5.4 Les modules, resserrés

Les six modules (Queue, MMR, Duel, Clan, Sécurité, Options) sont aujourd'hui
six rangées pleine largeur, chacune haute. C'est long et c'est plat.

Propose une **grille**, inspirée de la capture 3 : panneau visuel en haut de
chaque carte (la maquette Discord correspondante, déjà dessinée), puis une
petite icône d'accent, un titre, deux lignes. Deux ou trois colonnes au choix,
mais **dis quel rythme tu choisis et pourquoi** : six cartes identiques font
une grille morte ; une carte plus large que les autres donne un point d'entrée.

Le contenu des six maquettes `.mock` existe et est fidèle au bot : **ne les
redessine pas**, recadre-les.

### 5.5 La section communauté

Même rôle que la capture 4 : dire qu'il y a du monde. Mais **sans pile
d'avatars** (§2.2) : on n'a ni les images ni le droit.

Le remplacement honnête : une **mosaïque assombrie des maquettes Discord** en
fond — des annonces de file, des tableaux de scores, des salons vocaux — avec
par-dessus le titre, une phrase, et deux gros boutons pilule (Discord en
blurple, le panneau en crème). C'est vrai, c'est à nous, et ça montre le
produit au lieu de montrer des visages.

### 5.6 Un bloc de réponses

La référence a « FAQ » dans sa navigation. Nous avons une documentation
complète (`guide.html`) mais rien sur l'accueil. Six questions en accordéon,
courtes, qui règlent les objections réelles : *quelles permissions Discord ?*,
*est-ce que ça lit mes messages ?*, *combien de temps pour configurer ?*,
*et si le bot tombe ?*, *c'est payant ?*, *je peux l'essayer sur un serveur de
test ?*. Les réponses existent déjà dans le guide.

Dessine l'accordéon **fermé et ouvert**, et dis comment il se comporte au
clavier.

### 5.7 L'appel final

Répété juste avant le pied, comme dans la référence : grand, centré, une seule
action. C'est le `.mcta` actuel — il existe, il est petit, il passe inaperçu.
Grossis-le.

---

## 6. La règle la plus dure : jamais de chiffre inventé

Le dépôt interdit les données inventées. Ce n'est pas une préférence de style :
sans API, les écrans affichent leurs **états vides réels**, et jamais une
courbe plate qui ressemblerait à de l'activité. C'est appliqué partout dans le
code existant, et la page d'état a été écrite pour ne **pas** montrer quatre-
vingt-dix jours de barres vertes imaginaires.

Donc, pour la rangée de chiffres du héros et pour la section communauté :

**Ce qui est réellement mesuré aujourd'hui** (`site/etat.php`, qui interroge
le bot) :

| Donnée | Clé | Remarque |
|---|---|---|
| Serveurs où le bot est présent | `guilds` | réel |
| Files ouvertes en ce moment | `active_queues` | réel, et vivant — il bouge |
| Disponibilité / verdict | `verdict` | opérationnel / dégradé / indisponible |
| Latence Discord | `latency_ms` | en ms |
| Uptime | `uptime_seconds` | |

**Ce qui n'existe pas** : un nombre d'utilisateurs, un nombre de joueurs, un
total de matchs joués, une date de fondation, un nombre de vues. Le nombre de
membres est **délibérément exclu** de la réponse publique pour des raisons de
vie privée. **Ne les dessine pas.** Si ta composition a besoin de quatre
chiffres et qu'il n'y en a que trois, change la composition — pas la vérité.

**Deux contraintes techniques dont la maquette dépend :**

1. **`etat.php` n'est déployé que sur `status.cyqbot.eu`.** La vitrine qui
   l'appellerait ferait une requête **inter-origine**, que le navigateur
   refusera. Pour que les chiffres du héros soient vivants, il faudra soit en
   déployer une copie sur la vitrine, soit ouvrir un en-tête CORS **pour la
   seule origine `https://cyqbot.eu`**. Mentionne-le dans tes notes : c'est
   une décision d'implémentation que ta maquette rend nécessaire.
2. **Dessine les trois états de cette rangée** : *chargement*, *chiffres
   connus*, *indisponible*. Le troisième n'est pas un cas d'école — le bot
   peut être éteint, et la page doit rester digne dans ce cas. Pas de « 0 »
   présenté comme une mesure : zéro file ouverte et file inconnue ne sont pas
   la même chose.

Même logique pour la pastille d'état du pied (§7.6) : elle dit ce qu'elle
mesure, ou elle ne dit rien.

---

## 7. Écran D — le pied de page

Le pied actuel est **une seule rangée de cinq liens**, alignée à droite. Pour
une page qui va devenir longue, c'est une fin sèche.

Reprends la structure de la capture 5, transposée :

1. **Colonne de gauche** : logo + wordmark, deux lignes qui disent ce qu'est
   CreateYourQueue, et la **pastille d'état** en dessous.
2. **Trois colonnes de liens** : *Produit* (Modules, Documentation, Panneau),
   *Aide* (Support, Discord, FAQ), *Légal* (Conditions, Confidentialité).
   Vérifie dans le code quelles pages existent vraiment avant d'en lister une :
   la vitrine a `index`, `modules`, `guide`, `support`, et pointe vers
   `dashboard.cyqbot.eu` et `status.cyqbot.eu`. `PRIVACY_URL` **n'a pas de
   cible aujourd'hui** — dessine la colonne, mais dis que ce lien reste à
   fournir.
3. **Ligne de bas** : copyright à gauche ; à droite le **sélecteur de langue
   en pilule** (il existe déjà en haut, en menu — propose une seconde porte en
   bas) et le bouton **Discord** en blurple.

**La pastille d'état.** C'est le « All Systems Operational » de la référence,
et c'est un vrai gage de sérieux. Elle n'est honnête que si elle **mesure** :
elle doit lire `etat.php` (même contrainte d'origine qu'en §6) et afficher le
verdict réel, avec ses trois états. Si on décide de ne pas câbler l'appel,
alors elle devient un **lien** vers `status.cyqbot.eu` **sans point de
couleur** — un voyant vert qui ne mesure rien est un mensonge. Dessine les deux
versions.

**L'invite de langue** (« Vous lisez en français, votre navigateur préfère
l'anglais ») : la référence la pose en bas à droite, au premier passage. Le
site gère déjà cinq langues. Dessine-la, avec son bouton de refus durable
(« garder le français partout ») — une invite qui revient à chaque visite est
une nuisance.

---

## 8. Écrans B et C — le panneau

Le panneau a aujourd'hui : un **rail de gauche** (carte du serveur en haut,
navigation en six catégories au milieu, carte de compte en bas), une barre de
navigation flottante en haut, et **23 sections** de formulaires à droite.
C'est net, et c'est **austère** : on arrive directement dans un formulaire.

### 8.1 Écran B — la vue d'ensemble, qui n'existe pas

Aujourd'hui le panneau s'ouvre sur **Configurations**, c'est-à-dire sur des
champs. La capture 1 montre ce qui manque : un **écran d'accueil** qui dit où
on en est avant de demander de régler quoi que ce soit.

Compose-le, avec les éléments suivants — tous alimentés par des données qui
existent déjà dans le code (sections Statistiques, Journal, Diagnostic,
Lanceur, Historique) :

- **Une rangée de quatre cartes-chiffres** : files ouvertes sur 30 jours,
  files lancées, matchs joués, attente moyenne. Ces quatre valeurs sont
  **réellement rendues** par l'API du bot. Le taux d'abandon et l'attente
  peuvent valoir « inconnu » : le code les affiche déjà en `—`, et c'est
  volontaire — aucune file ouverte et aucune file abandonnée ne sont pas la
  même chose. **Ta maquette doit montrer le `—`.**
- **Un bloc « et maintenant »**, équivalent du « What's Next » de la
  référence : l'état de la configuration du serveur. Le panneau a déjà un
  **Diagnostic** qui vérifie les permissions du bot salon par salon et signale
  ce qui manque — c'est exactement le contenu de ce bloc, et il mérite mieux
  qu'une entrée de menu en bas de liste.
- **Un lanceur rapide** : l'aperçu de l'annonce + le bouton d'ouverture de
  file. La section « Lanceur de queue » existe ; sa tête doit être ici.
- **Une rangée de cartes-raccourcis** vers les destinations fréquentes.
- **Une colonne de droite** sur le modèle de « Manage Account » : des lignes
  à tuile d'icône, titre, phrase, chevron — vers le compte Discord connecté,
  les presets, l'export de configuration, le journal.

**Attention aux tuiles d'icône colorées de la référence** : elles sont roses
parce que c'est sa couleur. Chez nous, le cuivre est contingenté (§3.2).
Propose une solution qui ne consomme pas le quota — `--raised-2` avec l'icône
en `--ink`, par exemple — et dis laquelle tu as choisie.

### 8.2 La recherche ⌘K

La référence en a une, et avec **23 sections** réparties en six catégories,
nous en avons besoin plus qu'elle. Dessine-la :

- **fermée** : un champ dans le rail, avec le raccourci affiché à droite ;
- **ouverte** : la palette, les résultats groupés par catégorie, l'état « rien
  trouvé », l'état survolé/sélectionné au clavier.

Dis ce qu'elle cherche : les sections, mais aussi **les réglages à l'intérieur
des sections** — c'est ce qui la rend utile. Et dis ce qui arrive sur mobile,
où il n'y a pas de ⌘K.

### 8.3 Écran C — une section de réglages

Prends une section dense, par exemple **Queue** (identité, format, annonce,
notification) ou **Sécurité → Anti-raid** (quatre réglages à bornes).

La trame actuelle : un titre de section, une phrase, puis des **groupes**
(`.grp`) contenant des **rangées** (`.row`) — libellé + description à gauche,
état au milieu, contrôle à droite. Elle marche. Ce qui lui manque :

- **de la hauteur de rangée** : tout est tassé ;
- **une hiérarchie entre les groupes** : ils se ressemblent tous ;
- **un en-tête de section qui tient debout** : il est minuscule par rapport au
  contenu qui suit ;
- **l'aperçu en direct mis en valeur** : `.dprev` est le plus bel objet du
  panneau et il est rangé dans une colonne latérale.

Garde les mécanismes : l'**état par rangée** (modifié / enregistré / erreur),
les **bornes affichées** à côté du libellé (`2 – 100`, `1 – 10080`), les
rangées qui se **verrouillent** quand leur interrupteur est éteint, les
listes de salons et de rôles en combobox.

### 8.4 Les deux versions mobiles

Pour A et B, dessine le 390 px **en entier**, pas un recadrage du desktop.
Les points à trancher explicitement :

- **La barre de navigation** : elle s'efface au défilement et revient en haut.
  Dis ce qu'elle contient à 390 px, et où passent les liens qui ne tiennent pas.
- **Le héros** : le titre en très grand tient-il à 390 px ? Donne la valeur
  basse du `clamp`. L'actuel tombe à `clamp(2rem, 9vw, 2.75rem)`.
- **L'objet lumineux** : au-dessus du titre, en dessous, ou retiré ? Tranche.
- **La rangée de chiffres** : 2 × 2, ou une rangée défilante ?
- **La démonstration (5.3)** : une scène Discord à 390 px déborde vite.
  Dessine le cadrage mobile, pas une réduction.
- **Le rail du panneau** : il passe déjà en rangée horizontale défilante à
  900 px. Est-ce que ça tient avec six titres de catégorie ? Les titres sont
  **masqués** sous 900 px dans le code actuel — valide ou corrige ce choix.
- **Une barre d'action collante en bas** sur mobile : le bouton d'enregistrement
  du panneau, et le CTA de la vitrine. À 390 px, un bouton en haut de page est
  un bouton perdu.
- **Zones tactiles : 44 px minimum.** Et `@media (hover: none)` existe déjà
  dans `dashboard.css` : les effets de survol ne doivent pas rester collés.

---

## 9. Ce que tu rends

1. **Huit maquettes** : A, B, C, D × desktop 1440 et mobile 390. Les états
   alternatifs (chargement, indisponible, mouvement réduit, accordéon ouvert,
   palette de recherche ouverte) peuvent être des vignettes à côté plutôt que
   des écrans entiers.
2. **Une page de spécifications** qui donne, en valeurs exactes :
   - l'échelle typographique complète (taille, graisse, interligne,
     interlettrage, par rôle, avec les `clamp()`) ;
   - les tokens neufs, nommés dans le style existant (`--…`), avec leur valeur
     et leur emploi ;
   - les espacements employés, **pris dans 8/16/32/64/120/200** ;
   - les rayons et les opacités.
3. **Les écarts au design system**, listés un par un : ce que tu as déplacé, la
   valeur avant, la valeur après, et **pourquoi**. C'est ce qui permettra de
   mettre `docs/DESIGN-SYSTEM.md` à jour au lieu de le laisser mentir.
4. **Les contrastes mesurés** pour toute paire texte/fond que tu introduis.
   Rappel : cuivre en fond ⇒ texte `--bg`, jamais `--ink`.
5. **Tes décisions**, dites franchement : le bas de casse du héros gardé ou
   abandonné, le rythme de la grille de modules, le sort de l'objet lumineux
   sur mobile, la solution pour les tuiles d'icône du panneau, la pastille
   d'état câblée ou simple lien.
6. **Ce que ta maquette rend nécessaire côté code** : l'appel inter-origine de
   `etat.php`, la recherche ⌘K à écrire, le nouvel écran de vue d'ensemble.

---

## 10. La liste de contrôle, avant de rendre

- [ ] Aucune teinte hors palette, sauf le blurple Discord sur un bouton Discord.
- [ ] **Un seul** emploi plein du cuivre par écran défilé.
- [ ] Aucun texte crème sur fond cuivre.
- [ ] Aucun dégradé dans du texte.
- [ ] Rapport titre/corps ≥ 7× sur le héros.
- [ ] Corps à 15 px, `--ink-60`, jamais `--ink-40`.
- [ ] Tous les espacements pris dans 8/16/32/64/120/200.
- [ ] Quatre rayons, aucun rectangle.
- [ ] Une seule ombre, celle du système.
- [ ] Tout ce qui s'anime s'anime en `transform` / `opacity`.
- [ ] Chaque écran animé a sa variante calme, dessinée.
- [ ] Aucun chiffre qui n'existe pas dans `etat.php` ou dans l'API du bot.
- [ ] État « indisponible » dessiné partout où un chiffre est affiché.
- [ ] Zones tactiles ≥ 44 px sur les maquettes mobiles.
- [ ] Les libellés tiennent en allemand et en coréen.
- [ ] Aucune police ajoutée, aucune bibliothèque ajoutée.
