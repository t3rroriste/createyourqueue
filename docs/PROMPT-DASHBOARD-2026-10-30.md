# Chantier — le panneau gagne un écran d'arrivée

## Ce qui ne va pas

On choisit un serveur dans `servers.html`, et on atterrit dans
`dashboard.html` sur un mur de réglages : 22 sections rangées en
familles, toutes au même niveau d'importance, toutes muettes sur l'état
réel du serveur. Rien ne dit si la configuration est finie, si une queue
a déjà tourné, ce qu'il reste à faire. Le panneau est une boîte à
outils ; il lui manque la page qui dit **où on en est**.

## La référence, et ce qu'il faut en prendre

Le panneau de `fakecrime.bio` fait bien une chose : on arrive, et en
trois secondes on sait où on en est. Quatre chiffres en haut, une barre
de progression vers un objectif nommé, une colonne « voici quoi faire
ensuite », une colonne « gérer », et des raccourcis. Aucun réglage sur
cet écran — il montre et il oriente.

**Ce qu'on prend : la structure et la densité.**

- Une rangée de cartes-chiffres en haut, grandes, lisibles de loin.
- Une progression vers un objectif *nommé*, avec les paliers visibles
  et celui qui vient mis en avant.
- Deux colonnes sous les chiffres : à gauche « ce qu'il reste à faire »,
  à droite « gérer ce serveur » en liste de lignes cliquables.
- Une grille de raccourcis vers les sections les plus utilisées.
- Des chiffres secondaires en bas (activité, provenance).

**Ce qu'on ne prend PAS : sa direction artistique.**

`fakecrime` est noir et rouge. Le panneau de CreateYourQueue est
monochrome crème sur noir — `--acc #F6F6F3`, Archivo et IBM Plex Mono,
thème clair via `html[data-theme="light"]`. `CLAUDE.md` l'écrit noir sur
blanc : les deux D.A. du projet ne partagent aucun token et on ne les
« harmonise » jamais. Importer un accent rouge ici, ce n'est pas
s'inspirer, c'est changer de design system — et ça se décide
explicitement, pas en passant.

La hiérarchie que fakecrime obtient avec de la couleur, on l'obtient
autrement : par la taille, la graisse, l'espace, et le contraste entre
Archivo et IBM Plex Mono sur les chiffres.

## Ce qu'il faut construire

Une section **« Vue d'ensemble »**, première du menu, celle sur laquelle
`dashboard.html` ouvre par défaut au lieu de `configurations`.

### 1. Les cartes-chiffres

Quatre, en haut, dans la grille du panneau. Toutes alimentées par des
données réelles de l'API — `GET /guilds/{id}` et les routes de lecture
du bot (`/matches`, `/activity`, `/stats`) :

- le nom du serveur et son icône ;
- le nombre de membres ;
- le nombre de queues jouées (depuis `/matches`) ;
- la dernière queue, en durée relative (« il y a 2 h »).

### 2. La progression de configuration

C'est la traduction honnête de la barre de badges de la référence. Pas
des badges : **l'état réel de la configuration**, en paliers nommés,
avec celui qui vient mis en avant.

Les paliers se lisent dans la réponse de l'API, jamais devinés :

1. salons définis ;
2. rôle staff défini ;
3. format de queue enregistré ;
4. logs branchés ;
5. premier lancement effectué.

Les quatre premiers sont exactement ce qui fait répondre `409` à
l'ouverture de queue (`setup_incomplete`, `no_config`). Cette barre doit
donc dire la même vérité que le bot : si elle est pleine, « Ouvrir la
queue » marche. Si elle ne l'est pas, elle nomme le palier manquant et
le rend cliquable vers la section qui le règle.

### 3. Ce qu'il reste à faire

Sous la progression, la liste des paliers non franchis, une ligne
chacun, avec un lien vers la section concernée. **Si tout est fait, la
liste disparaît** et laisse la place à une ligne qui le dit. Pas de
liste vide, pas de coches décoratives.

### 4. Gérer ce serveur

Colonne de droite, lignes cliquables avec titre et sous-titre, sur le
modèle de « Manage Account » de la référence. Elles existent déjà comme
sections : Diagnostic, Journal, Blacklist, Logs, Statistiques. Les
compteurs `data-nav-count` du menu sont déjà alimentés — réutilise la
même source, n'en crée pas une deuxième.

### 5. Les raccourcis

Quatre cartes vers Lanceur de queue, Presets, Classement, Salons.

## Les règles qui ne se négocient pas

Elles sont dans `CLAUDE.md`, et ce chantier n'en exempte aucune.

- **Aucune dépendance nouvelle.** anime.js 4.5.0 est hébergé dans
  `site/assets/js/vendor/`, c'est la seule, et elle suffit.
- **Animations en `transform` et `opacity` uniquement.** La barre de
  progression s'anime en `scaleX`, pas en `width`.
- **`prefers-reduced-motion: reduce` a toujours une variante calme**, et
  `?motion=on` force l'animation pour pouvoir la vérifier.
- **Si anime.js ne charge pas, la page reste lisible.** Les états de
  départ se posent en JS, jamais en CSS.
- **Jamais de données inventées.** Sans API, l'écran affiche ses vrais
  états vides. Un serveur sans queue jouée affiche « aucune queue
  jouée », pas un zéro qui ressemble à une mesure.
- **i18n** : tout texte visible passe par `data-i18n`, et toute clé
  nouvelle entre dans les **cinq** fichiers de `site/assets/js/lang/`.
  Ils ont 467 clés chacun aujourd'hui, et la parité est vérifiable.
- **Commentaires en français**, qui expliquent le *pourquoi* d'une
  valeur et pas le *quoi* d'une ligne. Ne retire jamais ceux qui sont
  déjà là.

Un fichier neuf doit être déclaré dans `outils/fichiers_du_site.py`,
sinon il ne part pas en ligne. Après toute modification de CSS ou de JS :

```
python outils/numeroter_versions.py
```

## Comment vérifier avant de livrer

```
.\cyq local
```

Puis `http://localhost:8765/dashboard?guild=<id>&motion=on`.

- La page s'ouvre sur la Vue d'ensemble.
- La console est vide.
- En `prefers-reduced-motion: reduce`, rien ne bouge et tout reste
  lisible.
- À 375 px de large, rien ne déborde et les cartes s'empilent.
- En thème clair (`html[data-theme="light"]`), les contrastes tiennent.
- Sans API — coupe `cyq-api` — l'écran affiche ses états vides réels et
  ne casse pas.

Dis ensuite ce que tu as vérifié **et ce que tu n'as pas pu vérifier**.

## Livraison

Un commit par effet, message en français, une phrase qui dit ce que ça
change — pas une liste de fichiers. Le style des commits existants :

> Le menu du panneau range ses sections sous six noms
> La catégorie Queue s'ouvre sur un lanceur, et la programmation exige un preset

**Ne lance aucune publication.** `cyq publier`, `outils/publier_site.py`
et `outils/publier_bot.py` envoient en production sur `cyqbot.eu`. Ce
sont des commandes qu'on demande.

**Ne lis ni ne recopie aucun secret** : `bot/.env`,
`site/api/secrets.php`, `outils/reglages/lws.json`. Les modèles
`.env.example` et `secrets.exemple.php` documentent les champs, et c'est
eux qu'on cite.
