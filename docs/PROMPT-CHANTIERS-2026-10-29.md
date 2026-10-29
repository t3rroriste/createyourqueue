# Prompt d'exécution — douze chantiers, 29 octobre 2026

> À coller tel quel dans Claude Code, à la racine du dépôt `CYQ`.
> Tout ce qui suit s'adresse à l'agent qui exécute.

---

## 0. Ce qu'on te demande

Douze chantiers sur le site **CreateYourQueue** (`cyqbot.eu`, panneau sur
`dashboard.cyqbot.eu`), plus un sous-domaine neuf (`status.cyqbot.eu`).
Ils sont **indépendants les uns des autres** sauf là où c'est dit.

**Enchaîne du début à la fin.** Pas de question intermédiaire, pas de
« veux-tu que je continue », pas de demande de capture d'écran. Si un
chantier se révèle impossible en l'état, fais tous les autres en entier et
dis à la fin, en une ligne, lequel tu as laissé et pourquoi. Tu ne publies
rien.

L'ordre ci-dessous est délibéré : 1 à 3 sont courts et isolés, 4 à 9
touchent au panneau et se recouvrent (fais-les à la suite, dans cet ordre,
pour ne pas réécrire deux fois la même navigation), 10 à 12 sont de nouveau
isolés.

---

## 1. Les règles du dépôt, qui ne se négocient pas

Lis `CLAUDE.md` avant de commencer. Le résumé opérationnel :

- **Site statique.** Pas de build, pas de bundler, pas de `npm install`.
  Apache sert les fichiers tels quels.
- **Aucune dépendance nouvelle.** anime.js 4.5.0 est la seule, déjà copiée
  dans `site/assets/js/vendor/`. Pas de CDN, pas de paquet.
- **HTML / CSS / JS vanilla**, ES5 prudent, IIFE, `'use strict'`.
- **Animations en `transform` et `opacity` uniquement.** Pas de
  `box-shadow` animée, pas de `filter: blur()` animé sur grande surface,
  rien qui déclenche un calcul de mise en page dans une boucle.
- **`prefers-reduced-motion: reduce` a toujours une variante calme**, et
  `?motion=on` force l'animation pour pouvoir la vérifier.
- **Si anime.js ne charge pas, la page reste lisible.** Les états de départ
  se posent en JS, jamais en CSS.
- **Deux directions artistiques, jamais mélangées.** `home.css` (accueil,
  login, welcome, et le panneau depuis la refonte) et l'ancienne D.A. du
  panneau (`app.css`, plus chargée par personne) ne partagent aucun token.
  `docs/DESIGN-SYSTEM.md` et `docs/DESIGN-AUDIT.md` font loi.
- **Commentaires en français**, et ils expliquent le *pourquoi* d'une
  valeur, pas le *quoi* de la ligne. **Ne retire jamais** les commentaires
  existants pour « nettoyer » : c'est ce qui a abîmé `dashboard.html` et
  `bot.py` le 28 octobre.
- **i18n** : tout texte visible passe par `data-i18n` et les **cinq**
  fichiers `site/assets/js/lang/{fr,en,es,de,ko}.js`. Ajouter une clé =
  l'ajouter dans les cinq. Une clé retirée se retire dans les cinq.
  *Exception connue* : `guide.html` est en français en dur, sans
  `data-i18n` — voir le chantier 11.
- **Jamais de données inventées.** Sans API, un écran affiche son état vide
  réel. Jamais une courbe plate qui ressemble à de l'activité.
- **Un fichier neuf doit être déclaré** dans `outils/fichiers_du_site.py`
  (`COMMUN`, `VITRINE`, `APPLICATION`, `DECLARES`). Un fichier non déclaré
  ne part pas en ligne — `servers.css`, `dashboard.css`, `support.html` et
  `page-support.js` en ont tous fait les frais.
- **Après chaque modification de CSS ou de JS** :
  ```
  python outils/numeroter_versions.py
  ```
  Sans lui, le navigateur sert l'ancienne version depuis son cache.
- **Ne lance aucune publication.** `cyq publier`, `outils/publier_site.py`,
  `outils/publier_bot.py` envoient en production. Ce sont des commandes
  qu'on demande.
- **Ne lis ni ne recopie aucun secret** : `bot/.env`,
  `site/api/secrets.php`, `outils/reglages/lws.json`, `lws.pass`. Les
  modèles `.env.example`, `secrets.exemple.php`, `lws.config.exemple.ps1`
  documentent les champs — c'est eux qu'on cite et qu'on édite.
- **`archives/` est en lecture seule**, refusée en écriture par
  `.claude/settings.json`. Ce n'est pas un bug.

### Vérifier en local

```
.\cyq local
```

`.claude/launch.json` déclare `cyq-site` (8765), `cyq-api` (3000) et
`cyq-archive` (8766, l'instantané de septembre pour comparer). Pour un
écran animé : `http://localhost:8765/welcome.html?guild=test&motion=on`.

**Avant de livrer chaque chantier visuel** : sers le dossier, ouvre la
page, regarde la console, teste en `prefers-reduced-motion` et à 375 px de
large. Dis ensuite ce que tu as vérifié et ce que tu n'as pas pu vérifier.

---

# Les chantiers

## Chantier 1 — Le titre de l'accueil s'écrit, s'efface, se réécrit

**Fichiers** : `site/assets/js/page-home.js`, `site/assets/css/home.css`,
`site/index.html` (balisage du titre uniquement).

L'élément : `site/index.html` → `<h1 class="hero__title" data-hero="title"
data-i18n="h.title"></h1>`. Le texte vient de la clé `h.title` des cinq
fichiers de langue (fr : « Configure, customise et crée tes queues en moins
de 5 minutes. »).

Ce qu'on veut : le titre **se tape caractère par caractère, se tient un
moment, s'efface caractère par caractère, et recommence — en boucle,
indéfiniment**.

Les contraintes, toutes impératives :

1. **Pas de saut de mise en page.** Un titre dont la longueur varie
   repousse le bouton d'invitation à chaque frappe. Réserve la hauteur :
   mesure le texte complet une fois, fixe `min-height` sur le `h1` **en JS,
   après mesure** (pas une valeur devinée en CSS), et laisse le texte
   changer à l'intérieur.
2. **Le curseur est un pseudo-élément** (`.hero__title::after`), animé en
   `opacity` seule. Pas de caractère `|` injecté dans le DOM : il serait lu
   par un lecteur d'écran.
3. **Accessibilité.** Le `h1` doit rester lisible par les technologies
   d'assistance **en entier, une seule fois**. Deux options, prends la
   première qui marche : soit le texte réel vit dans un
   `<span class="sr-only">` figé et la partie animée est
   `aria-hidden="true"`, soit le `h1` porte `aria-label` avec le texte
   complet et son contenu est `aria-hidden`. **Jamais un `aria-live`** : la
   frappe serait annoncée lettre par lettre.
4. **`prefers-reduced-motion: reduce`** → le titre s'affiche en entier,
   tout de suite, sans curseur, sans boucle. `?motion=on` force la boucle.
5. **Changement de langue** : `app.js` émet `cyq:lang`
   (`site/assets/js/app.js:120`). À cet événement, la boucle **s'arrête,
   lit la nouvelle valeur de `h.title`, remesure, repart**. Sans ça, le
   titre continuerait de taper l'ancienne phrase.
6. **Le pilote est un `setTimeout` récursif, pas une animation CSS** : la
   vitesse de frappe doit varier légèrement (un rythme parfaitement
   régulier fait « terminal de film »). Mets les délais dans des constantes
   commentées en haut de la fonction, et explique le choix. Ajoute un
   arrêt sur `document.hidden` / `visibilitychange` : une boucle qui
   continue dans un onglet caché consomme pour rien.
7. **Si anime.js manque, l'effet marche quand même.** Il n'a rien à voir
   avec anime.js ; n'y touche pas. Mais `page-home.js` sort tôt quand `A`
   est absent (`if (!A) { decouvrir(); return; }`, ligne ~22) : ta boucle
   doit être **en dehors** de ce garde, dans sa propre IIFE, sinon elle ne
   jouera jamais sur un navigateur où la bibliothèque n'a pas chargé.
8. **La ponctuation finale ne clignote pas toute seule.** Efface jusqu'à la
   chaîne vide, pas jusqu'au premier mot.

Après : `python outils/numeroter_versions.py`.

---

## Chantier 2 — La barre du haut s'efface *avec* une animation

**Fichiers** : `site/assets/js/app.js`, fonction `barreQuiSEfface()`
(≈ l. 290-339) ; `site/assets/css/home.css` l. 160-192 (`.nav.is-hidden`,
`.nav:focus-within`, la transition de `.nav`).

Le comportement voulu existe déjà : au-delà de 8 px de défilement la barre
remonte et disparaît, et elle revient quand on est de retour tout en haut.
**Le défaut** : elle *saute* à la descente, et ne s'anime qu'au retour.

**La cause, trouvée — ne cherche pas ailleurs avant de l'avoir vérifiée.**
`placer()` appelle `liberer()` à **chaque** événement `scroll` :

```js
function liberer() {
  if (nav.getAnimations) {
    nav.getAnimations().forEach(function (a) { a.cancel(); });
  }
}
```

`getAnimations()` ne rend pas seulement les animations d'anime.js : il rend
**aussi la `CSSTransition` que la règle
`.nav { transition: transform 280ms …; }` vient de créer**. Un défilement
émet des dizaines d'événements d'affilée : le premier démarre la transition
de sortie, le deuxième l'annule, et la barre se retrouve à l'arrivée en une
image. Au retour en haut, le dernier événement est… le dernier : plus rien
ne vient annuler la transition, et elle se joue — d'où l'asymétrie exacte
que tu observes.

**Le correctif, en deux gestes. Les deux, pas l'un ou l'autre :**

1. **N'annule que ce qu'il faut annuler.** Dans `liberer()`, saute les
   transitions CSS :
   `if (typeof CSSTransition === 'undefined' || !(a instanceof CSSTransition)) a.cancel();`
   — avec le garde de disponibilité, parce que `CSSTransition` n'est pas
   exposé partout. **Garde le commentaire existant** sur anime.js : il
   explique pourquoi `liberer()` existe, et il reste vrai.
2. **Ne réécris pas un état déjà posé.** Mémorise l'état courant
   (`var cachee = null;`) et sors immédiatement si `cacher === cachee`. Ça
   règle le problème à la racine — un seul passage par changement d'état —
   et supprime au passage des dizaines d'écritures de style par seconde.

**À ne pas casser** (chaque point correspond à un commentaire déjà présent
dans le fichier ; lis-les) :

- Les styles sont écrits **en ligne**, pas par la classe, parce qu'anime.js
  pose du style en ligne pendant l'animation d'ouverture.
- `.nav.is-hidden` garde ses `!important`, pour la même raison.
- `.nav:focus-within` ramène la barre : au clavier, on ne perd jamais ce
  qu'on vient d'atteindre. **Vérifie-le après ton changement** (Tab depuis
  le haut de la page, en étant défilé).
- Pas de `requestAnimationFrame` : le navigateur le suspend dans un onglet
  en arrière-plan, et la barre restait cachée au retour.
- Le seuil de 8 px reste 8 px : en deçà, c'est le rebond d'un clic sur une
  ancre, pas un geste de lecture.

**Vérifie sur les quatre pages qui ont la barre** : `index.html`,
`modules.html`, `guide.html`, `dashboard.html` — l'animation d'ouverture
d'anime.js diffère sur chacune, et c'est précisément ce qui avait obligé à
écrire `liberer()`.

Après : `python outils/numeroter_versions.py`.

---

## Chantier 3 — Les adresses sans `.html`, partout

**Fichiers** : `site/.htaccess`, les huit pages de `site/`,
`site/assets/js/config.js`, `site/assets/js/app.js` (réécriture des liens
`data-site` / `data-app`).

Aujourd'hui, `site/.htaccess` fait déjà **la moitié** du travail (voir sa
section « adresses sans .html ») :

```apache
RewriteRule ^(index|login|welcome|servers|dashboard|modules|guide)/$ /$1 [R=301,L,QSA]
RewriteCond %{REQUEST_FILENAME}.html -f
RewriteRule ^(index|login|welcome|servers|dashboard|modules|guide)$ $1.html [L,QSA]
```

Ce qui manque :

1. **`support` est absent des deux listes.** `support.html` existe depuis le
   16 octobre ; `cyqbot.eu/support` ne répond pas. Ajoute-le aux deux.
2. **Rien ne redirige la forme longue vers la forme courte.**
   `cyqbot.eu/guide.html` reste `cyqbot.eu/guide.html` dans la barre
   d'adresse. Ajoute une redirection **301** `/<page>.html` → `/<page>`,
   **avant** la réécriture interne, et avec une condition qui empêche la
   boucle (teste `%{THE_REQUEST}`, pas `%{REQUEST_URI}`, qui est déjà
   réécrit par la règle d'après).
3. **`login.html` est la seule exception, et elle est absolue.** Discord
   compare l'adresse de retour OAuth **au caractère près, avant toute
   redirection** : c'est `https://dashboard.cyqbot.eu/login.html` qui est
   déclarée dans le portail développeur (voir `OAUTH_REDIRECT_URI` dans
   `site/assets/js/config.js`, calculé en bas du fichier).
   **N'ajoute jamais `login` à la redirection 301 du point 2.** `/login`
   doit servir la page, et `/login.html` doit continuer de répondre **en
   200**, sans redirection. Écris ce pourquoi en commentaire dans le
   `.htaccess`, au-dessus de l'exception.
4. **Les liens écrits dans les pages pointent encore sur `.html`.** Passe
   tous les `href` internes à la forme courte :
   - les huit pages : `index`, `modules`, `guide`, `support`, `login`,
     `welcome`, `servers`, `dashboard` ;
   - les attributs `data-site="…"` et `data-app="…"`, que `app.js` récrit
     en préfixant `SITE_ORIGIN` / `APP_ORIGIN` : la valeur devient aussi la
     forme courte (`data-site="modules"`, `data-app="servers"`) —
     **vérifie dans `app.js` que la réécriture ne suppose pas
     l'extension** avant de changer quoi que ce soit ;
   - `DOCS_URL: 'guide.html'` dans `config.js` → `'guide'`.
   Seuls `href="login.html"` et `data-app="login.html"` **restent en forme
   longue** : c'est l'adresse déclarée chez Discord.
5. **`/api` ne passe jamais par ces règles** — il est servi par PHP. La
   liste explicite de pages (plutôt qu'une règle attrape-tout) est là pour
   ça : garde la liste explicite.
6. **`site/api/.htaccess` et `site/api/data/.htaccess` ne bougent pas.**
7. Les redirections d'anciennes adresses vers le sous-domaine
   (`RewriteCond %{HTTP_HOST} !^dashboard\.`) restent, et doivent rester
   **avant** tes nouvelles règles : le même fichier est déployé sur les
   deux domaines, et la condition sur l'hôte est ce qui empêche une boucle.

**Vérifie-le réellement.** Le serveur local est un serveur Python : il
n'applique pas `.htaccess`. Donc :

- relis chaque règle et explique dans ta réponse l'ordre d'application ;
- vérifie qu'**aucune page de `site/` ne contient plus de `href="….html"`
  interne** hors `login.html` — un `grep` suffit, montre-le ;
- vérifie que les pages marchent encore **telles quelles** en local, où
  l'extension est servie directement.

---

## Chantier 4 — La navigation du panneau devient des catégories nommées

**Fichiers** : `site/dashboard.html` (bloc `<nav class="dbnav">`,
≈ l. 87-140), `site/assets/css/dashboard.css`, les cinq fichiers de langue.

État actuel : cinq familles séparées par des `<div class="dbnav__grp">`,
sans étiquette. Le commentaire du fichier dit pourquoi : « le regroupement
se lit à l'espace entre les familles, pas à une étiquette ».

**On change d'avis, et il faut l'assumer** : le panneau passe de 19 à plus
de 20 sections, et l'espace ne suffit plus à distinguer les familles. Les
groupes reçoivent donc un **titre**.

- Nouvelle classe `.dbnav__cat` : une étiquette courte, en haut de chaque
  `.dbnav__grp`. Petite, en `--ink-40`. **Pas de
  `text-transform: uppercase`** sur une chaîne traduite : le coréen n'a pas
  de majuscules. Elle n'est **pas** cliquable, elle ne replie rien.
  Balise : `<p class="dbnav__cat" data-i18n="…">`.
- **Remplace le commentaire existant** par celui qui dit la nouvelle
  raison, sans effacer l'ancienne explication : écris que l'espace seul ne
  suffisait plus au-delà de vingt entrées.
- En dessous de 900 px la nav passe en rangée défilante. Une étiquette y
  prendrait la place d'une entrée : **masque `.dbnav__cat` sous 900 px** et
  garde l'espacement entre groupes comme aujourd'hui.
- `data-mark` (l'indicateur qui glisse) est mesuré sur `offsetTop` /
  `offsetLeft` du lien actif par `placerMarque()`
  (`site/assets/js/page-dashboard.js` ≈ l. 1789). Ajouter des étiquettes
  **décale ces mesures**. Vérifie que l'indicateur tombe juste, en large
  comme en étroit, au chargement et après changement de langue
  (`cyq:lang` rappelle `placerMarque(false)`).

**Les catégories, et leur contenu final** (après les chantiers 5 à 8) :

| Catégorie | Clé i18n proposée | Sections |
| --- | --- | --- |
| Le bot | `cat.bot` | Configurations, Options (+ ses sous-entrées conditionnelles) |
| Queue | `cat.queue` | **Lanceur de queue**, Programmation, Presets |
| Le serveur | `cat.server` | Salons, Rôles |
| Accès | `cat.access` | **Blacklist** |
| Sécurité | `cat.security` | **Logs**, **Anti-raid**, **Nettoyage auto**, **Anti-lien** |
| Suivi | `cat.monitor` | Statistiques, Journal, Diagnostic |

Les sous-entrées conditionnelles d'« Options » (`data-sub="feature.match"`,
`feature.leaderboard`, `feature.clans`) **ne changent pas de mécanisme** :
elles restent `hidden` tant que l'option est éteinte, pilotées par le
script — les montrer éteintes promettrait des réglages sans effet. Elles
vivent dans la catégorie « Le bot ».

Ajoute les six clés `cat.*` dans les **cinq** fichiers de langue.

Après : `python outils/numeroter_versions.py`.

---

## Chantier 5 — « Accès » devient la catégorie, « Blacklist » la section

**Fichiers** : `site/dashboard.html` (section `data-section="acces"`,
l. 1051-1107), `site/assets/js/page-dashboard-memoire.js` (`rendreAcces()`,
≈ l. 341-400), `site/assets/css/dashboard.css`, les cinq fichiers de langue.

1. **La section `acces` disparaît en tant qu'entrée de menu.** « Accès »
   devient un titre de catégorie (chantier 4). À sa place, une section
   `data-section="blacklist"`, titre « Blacklist », entrée de menu
   `data-goto="blacklist"`, compteur `data-nav-count="blacklist"`.
   Mets à jour `data-nav-count="acces"` dans `rendreAcces()` en
   conséquence.

2. **Le système d'absences part.** Le groupe `ac.grpNoshow` (« Absences »)
   et ses trois rangées — `noshow.enabled`, `noshow.threshold`,
   `noshow.banHours` — sont retirés du panneau.

   **Attention, c'est le point sensible du chantier** : ces trois réglages
   **existent côté bot** et continuent d'agir. Tu retires l'*écran*, pas la
   fonction.
   - Ne touche ni à `bot/`, ni à `site/api/index.php`, ni à
     `api-locale/server.py` : les clés restent acceptées.
   - **Vérifie que l'enregistrement du panneau n'envoie que les champs
     présents** (`[data-setting]` existants). Si la collecte envoie une clé
     absente du DOM comme chaîne vide, retirer les rangées **écraserait les
     valeurs du bot**. Relis la fonction d'enregistrement de
     `page-dashboard.js` et dis dans ta réponse ce que tu as constaté.
   - Note le retrait dans `docs/INVENTAIRE-REGLAGES.md` : un réglage que le
     bot a et que le panneau ne montre plus doit être écrit quelque part.
   - Retire les clés `ac.grpNoshow`, `ac.enabled`, `ac.enabledD`,
     `ac.threshold`, `ac.thresholdD`, `ac.banHours`, `ac.banHoursD` des
     cinq fichiers de langue — après avoir vérifié par `grep` qu'aucune
     autre page ne les utilise.

3. **La note sous le formulaire part.** La clé `ac.blacklistNote` (« Clic
   droit sur un pseudo dans Discord, "Copier l'identifiant". C'est la même
   liste que /blacklist. ») est supprimée du balisage **et des cinq
   fichiers de langue**. En revanche, le **commentaire HTML** qui explique
   pourquoi c'est un identifiant et pas un sélecteur de membre (le panneau
   ne charge pas la liste des membres, qui peut compter des dizaines de
   milliers de lignes) **reste** : il documente un choix technique, pas la
   note affichée.

4. **L'espacement du formulaire d'ajout.** Aujourd'hui les deux champs et
   le bouton sont collés dans `.rank__add`. Ce qu'on veut :
   - un **espace franc** entre le champ « identifiant Discord » et le champ
     « motif » ;
   - puis un **petit espace** avant le tableau ;
   - le bouton « Exclure » garde sa place en fin de rangée.

   Fais-le en CSS sur une classe propre à cet usage
   (`.rank__add--blacklist` ou une variante locale), **sans toucher à
   `.rank__add`** : elle sert aussi aux rangs, aux presets et à
   l'export/import. Prends les pas d'espacement dans les variables
   existantes de `dashboard.css` (`--sp-*`), pas des pixels en dur.

5. **Le tableau des exclus.** `[data-blacklist]` est aujourd'hui rempli par
   `rendreAcces()` avec une suite de `.row > .ligne` (pseudo, motif, date,
   bouton « Retirer »). On veut un **vrai tableau** : trois colonnes
   alignées, un en-tête (Membre · Motif · Depuis), l'action à droite.
   - Un `<table>` sémantique est plus simple et se lit mieux qu'une grille
     avec rôles ARIA : prends le `<table>`.
   - À 375 px, quatre colonnes débordent. Donne-lui une variante empilée
     sous 640 px — le fichier a déjà ce média (voir
     `.match__date, .ligne__date { flex: 1 1 100%; }`, `dashboard.css`
     l. 1508).
   - **Garde les états vides réels** : `vide('ac.blacklistEmpty')` quand la
     liste est vide, et les états d'erreur de `panne()` (pas d'API, bot
     éteint, session expirée, erreur). **Jamais une ligne d'exemple.**
   - Le nom affiché reste `e.name || ('#' + String(e.id).slice(-4))` : le
     panneau ne charge pas les membres, il n'a parfois que l'identifiant.

6. **« Exclusions automatiques » passe dessous**, dans la même section,
   après le tableau. C'est `[data-queuebans]`, rempli par la même fonction.
   **Les deux listes ne se mélangent pas** — le commentaire de la section
   l'explique : celle du staff est sans fin, celle du bot se lève d'elle-
   même ; les confondre ferait disparaître une sanction du staff au bout de
   vingt-quatre heures. Garde ce commentaire, garde les deux groupes
   distincts, garde les deux boutons distincts (« Retirer » / « Lever »).

7. **`ac.lead`** parle encore des deux listes *et* des absences. Réécris-la
   dans les cinq langues : la blacklist du staff, et les exclusions que le
   bot pose tout seul.

Après : `python outils/numeroter_versions.py`.

---

## Chantier 6 — Une maquette Discord dans chaque option

**Fichiers** : `site/dashboard.html` (section `data-section="options"`,
l. 242-281), `site/assets/css/dashboard.css` (bloc `.dprev`, l. 967-1040),
`site/assets/js/page-dashboard.js`.

Les six options sont des interrupteurs secs. On veut, **sous chaque
rangée**, une maquette qui montre *ce que l'option fait dans Discord* — une
copie 1:1 du message que le bot publie.

### Le socle existe déjà : ne le réinvente pas

`dashboard.css` contient un système de maquette Discord complet, construit
pour l'aperçu de la queue : `.dprev`, `.dprev__av`, `.dprev__head`,
`.dprev__name`, `.dprev__app`, `.dprev__time`, `.dprev__ping`,
`.dprev__ment`, `.dprev__embed`, `.dprev__title`, `.dprev__by`,
`.dprev__teams`, `.dprev__line`, `.dprev__cta`, `.dprev__fields`,
`.dprev__field`, `.dprev__fname`, `.dprev__fval`, `.dprev__foot`,
`.dprev__react`, plus deux animations `.dprev.is-envoi` et
`.dprev.is-retrait`. Le balisage de référence est dans la section Queue de
`dashboard.html` (≈ l. 682-712).

**Réutilise ces classes.** N'en crée de nouvelles que pour ce qui n'existe
pas (liste de membres, salon vocal, commande slash, bouton Discord), et
nomme-les dans la même famille (`.dprev__*`).

### La règle de fidélité

« 1:1 avec Discord » veut dire : **les formes et la grammaire de Discord,
rendues dans la palette du site.** Pas les couleurs de Discord.
`docs/PROMPT-MAQUETTES-DISCORD.md` (section 3) détaille cette D.A. —
lis-le, le travail a déjà été fait pour `modules.html`.

**Le contenu, lui, est exact.** Pour chaque option, va lire le code qui
publie le message et recopie : titre de l'embed, ordre des lignes, noms des
champs, pied, emoji, réactions. Un aperçu qui dirait autre chose que le
vrai message ne servirait à rien — c'est le commentaire de l'aperçu de
queue, et il vaut pour les six.

| Option (`data-setting`) | Où est le code du bot |
| --- | --- |
| `feature.leaderboard` — Classement | `bot/cogs/classement.py`, `bot/elo_card.py` |
| `feature.match` — Match & MMR | `bot/cogs/match.py`, `bot/mmr.py` |
| `feature.clans` — Clans | `bot/cogs/clan.py`, `clan_war.py`, `clan_tickets.py` |
| `feature.joinAnnounce` — Annonce des adhésions | `bot/cogs/welcome.py` |
| `feature.statusPanel` — Panneau d'état | `bot/cogs/statuspanel.py`, `build_embed()` l. 119 |
| `feature.queuePassword` — Mot de passe des queues | `bot/cogs/queue_config.py`, `bot/cogs/party.py` |

Les textes affichés dans les maquettes viennent de `bot/locales/fr.json` —
recopiés, pas retraduits, et **en dur**, comme pour les maquettes de
`modules.html`.

### Les contraintes

- **Décoratives** : `aria-hidden="true"` sur chaque maquette, **aucune clé
  `data-i18n` dedans**, aucun élément focusable. Ce que la maquette montre
  est déjà lisible dans le libellé et la description de la rangée.
- **Repliées par défaut.** Six maquettes dépliées feraient de la section
  Options un mur. Chaque rangée reçoit un **révélateur** : un
  `<button type="button" aria-expanded aria-controls="…">` « Voir dans
  Discord », et la maquette est `hidden` au départ. Le bouton, lui, est un
  vrai contrôle : libellé traduit, dans les cinq langues.
- **Une seule ouverte à la fois** — sinon on perd le fil.
- **Animation à l'ouverture** en `transform` + `opacity` seulement, par la
  classe existante `.dprev.is-envoi`. Variante calme sous
  `prefers-reduced-motion`.
- **La maquette ne dépend pas de l'état de l'interrupteur** : elle montre
  ce que l'option *ferait*. Ne la grise pas, ne la masque pas quand
  l'option est éteinte.
- À 375 px, chaque maquette tient sans défilement horizontal.

Après : `python outils/numeroter_versions.py`.

---

## Chantier 7 — La catégorie Sécurité : quatre sections, quatre maquettes animées

**Fichiers** : `site/dashboard.html` (sections `logs` l. 773-790 et
`securite` l. 791-900, à éclater), `site/assets/css/dashboard.css`,
`site/assets/js/page-dashboard.js`, les cinq fichiers de langue.

### Éclater, sans rien perdre

| Section | Ce qu'elle reçoit |
| --- | --- |
| `logs` | déjà une section : `[data-logs]`, `[data-logs-count]` |
| `antiraid` | le groupe `se.grpRaid` (seuil, fenêtre, âge du compte, expulsion) |
| `nettoyage` | le groupe `se.grpClean` (interrupteur, salon, intervalle) |
| `antilien` | le groupe `se.grpAntilink` (note, filtre, `[data-antilink]`) |

**Les commentaires des trois groupes suivent leur groupe, mot pour mot.**
Ils portent des informations qu'on ne retrouve pas dans le code : pourquoi
l'anti-raid n'a plus d'interrupteur (la détection est toujours active côté
bot, la case ne l'éteignait pas) ; pourquoi il n'a plus de menu d'action
(le bot ne sait faire qu'une expulsion pendant un lockdown) ; pourquoi les
bornes sont exactement celles de `/antiraid config` (deux chemins vers le
même réglage qui n'accepteraient pas les mêmes valeurs, c'est un panneau
qui refuse ce que Discord vient d'enregistrer) ; pourquoi le nettoyage se
règle *vraiment* depuis que sa configuration est sur le disque
(`data/autoclean.json`) ; pourquoi l'anti-lien est **par salon** et non par
serveur. **Ne les résume pas. Déplace-les.**

Ce qui ne bouge pas :

- Les bornes : `security.raidThreshold` 2-100, `security.raidWindow`
  2-300 s, `security.raidAccountAge` 0-720 h, `security.autocleanDelay`
  1-10080 min.
- `data-controls="#se-clean-row,#se-clean-delay-row"` sur l'interrupteur de
  nettoyage : le salon et le délai se verrouillent quand il est éteint.
- Le filtre `[data-antilink-filtre]` : un serveur à quatre-vingts salons
  donne quatre-vingts rangées.
- Les rangées d'anti-lien et les dix journaux sont **fabriqués par
  `page-dashboard.js`**, qui les cherche par `[data-antilink]`,
  `[data-logs]`, `[data-logs-count]`. Si tu déplaces ces conteneurs,
  vérifie que les sélecteurs trouvent encore leur cible et que
  `compterJournaux()` tourne toujours.
- `lbl-log-channel` (le libellé masqué partagé, `dashboard.html` l. 170)
  doit rester atteignable depuis la section Logs.

### Les quatre maquettes

Dans chaque section, **une maquette qui montre l'effet, en boucle**, sur le
socle `.dprev` du chantier 6.

Tu as demandé un GIF. **On ne met pas de GIF** : ce serait un binaire de
plusieurs centaines de kilo-octets par maquette, non versionné par `?v=`,
impossible à rendre calme sous `prefers-reduced-motion`, et une dépendance
d'image là où le dépôt n'en veut pas. On fait **la même chose en CSS +
JS**, en `transform` et `opacity` : plus léger, plus net, et conforme. Si
tu veux vraiment des GIF, demande-le après avoir vu le résultat.

Ce que chaque boucle montre — va lire le cog pour le détail :

- **Logs** (`bot/cogs/logs.py`) : un événement arrive, le bot poste son
  embed dans le salon de journal. Il y a **dix types**, chacun avec son
  icône, et c'est `KINDS` en haut du fichier (l. 36) : `vocal 🎤`,
  `message 💬`, `queue 🔔`, `match 🎮`, `duel ⚔️`, `clan 🛡️`, `commande ⚡`,
  `join 👋`, `moderation 🔨`, `serveur 🏠`. **L'ordre est celui de
  `/logs` — garde-le.** L'embed est construit par `build()` (l. 177) :
  titre `«  icône  titre »`, description, auteur, horodatage. La boucle
  fait défiler deux ou trois de ces entrées.
- **Anti-raid** (`bot/cogs/antiraid.py`) : plusieurs arrivées coup sur
  coup, le seuil tombe, le bot verrouille. L'embed est
  `antiraid.lockdown_title` / `antiraid.lockdown_*` (l. 106-130, 169).
  Montre la séquence : trois `👋` rapprochés, puis le cadenas. **N'invente
  pas de bannissement** : le bot ne sait faire qu'une expulsion pendant un
  lockdown, et `/antiraid unlock` lève le verrou.
- **Nettoyage auto** (`bot/cogs/auto_clean.py`) : le salon se remplit, le
  délai tombe, les messages s'effacent. La boucle est
  `clean_channel_loop()` (l. 155) ; la confirmation est
  `moderation.autoclean_on`, avec le salon et l'intervalle. Utilise
  l'animation `.dprev.is-retrait`, qui existe déjà pour la disparition.
- **Anti-lien** (`bot/cogs/antilink.py`) : un membre poste un lien, le
  message disparaît, le bot répond. L'embed est
  `moderation.antilink_title` / `moderation.antilink_deleted`
  (l. 150-155). Le filtre agit dans `on_message` (l. 113) et **le staff est
  exempté** (`_is_staff`, l. 39) — c'est exactement ce que la maquette doit
  montrer : le lien d'un membre part, celui du staff reste.

Contraintes des boucles :

- `transform` et `opacity` **uniquement**. Pas de `height` animée, pas de
  `box-shadow`, pas de `filter`.
- **La boucle ne tourne que quand sa section est visible.** `app.js` émet
  `cyq:section` avec le nom de la section à chaque navigation
  (`site/assets/js/app.js:916`) : branche-toi dessus pour démarrer et
  arrêter. Quatre boucles qui tournent en permanence, c'est du calcul pour
  rien. Ajoute aussi un arrêt sur `visibilitychange`.
- **Variante calme** sous `prefers-reduced-motion: reduce` : l'état final,
  figé, sans boucle. `?motion=on` force l'animation.
- `aria-hidden="true"`, aucun texte traduit dedans, aucun élément
  focusable.
- Si anime.js manque, la maquette reste lisible (état final posé en JS).

Après : `python outils/numeroter_versions.py`.

---

## Chantier 8 — La catégorie Queue : Lanceur, Programmation, Presets

**Fichiers** : `site/dashboard.html` (sections `queue` l. 532-733,
`presets` l. 737-771, `programmation` l. 901-948),
`site/assets/css/dashboard.css`, `site/assets/js/page-dashboard.js`, les
cinq fichiers de langue.

### 8.1 — « Lanceur de queue », miroir de la section Queue

Une **section neuve**, `data-section="lanceur"`, entrée de menu « Lanceur
de queue », en tête de la catégorie Queue. Elle ne règle rien : elle
**montre et elle lance**.

Dans cet ordre :

1. **L'aperçu de l'annonce.** C'est le bloc `[data-qprev]` qui vit
   aujourd'hui dans l'`<aside>` de la section Queue (l. 682-712), alimenté
   par `apercuQueue()` dans `page-dashboard.js`.

   **Décision à prendre, et elle compte** : un seul aperçu, deux endroits.
   Le plus simple est de **déplacer** le bloc dans la nouvelle section et
   de garder la section Queue pour les réglages seuls — un aperçu dupliqué
   demanderait à `apercuQueue()` d'écrire à deux endroits et de rester
   synchrone. Si tu choisis de dupliquer, alors `apercuQueue()` doit
   parcourir **tous** les `[data-qprev]` et non le premier. Dis dans ta
   réponse ce que tu as choisi et pourquoi.
2. **Un espace franc.** C'est le point explicite de la demande : entre
   l'aperçu et les boutons, un vrai blanc. Aujourd'hui les deux `.grp` se
   suivent de près. Prends un pas d'espacement existant (`--sp-*`), pas une
   valeur en dur, et commente la raison : les deux boutons sont
   destructeurs, ils ne doivent pas être à portée d'un clic distrait depuis
   l'aperçu.
3. **Les deux boutons**, tels quels : `[data-launch]` (« Ouvrir la queue
   maintenant ») et `[data-stop]` (« Fermer la queue en cours »), plus la
   ligne d'état `[data-launch-state]` (`role="status" aria-live="polite"`).
   Ne touche pas à leur logique : ils restent `disabled` tant que l'API n'a
   pas répondu — **pas de faux succès**, et la ligne d'état dit toujours ce
   qui s'est réellement passé. Le second clic de confirmation sur
   « Fermer » reste : fermer supprime l'annonce et purge le salon de
   commande, c'est définitif.

La section Queue garde son titre « Queue par défaut » et tous ses réglages.
Elle perd son `<aside>` — donc sa classe `sec--aside` et sa structure
`.sec__body` / `.sec__main`, à nettoyer proprement si l'aside part.

### 8.2 — Programmation : un preset obligatoire, un aperçu, pas de bouton

Dans `data-section="programmation"` :

1. **Un sélecteur de preset, en haut, requis.** Nouvelle rangée, au-dessus
   de l'interrupteur `schedule.enabled` : une combobox
   (`<div class="combo" data-combo>` — le mécanisme est `buildCombo` dans
   `app.js:347`) alimentée par la liste des presets que
   `page-dashboard.js` connaît déjà (`[data-presets]`,
   `data-nav-count="presets"`).
   - Tant qu'aucun preset n'est choisi, **l'interrupteur « Ouvrir
     automatiquement » est verrouillé**, et une ligne dit pourquoi : une
     ouverture programmée sans preset n'aurait pas de configuration à
     appliquer. Utilise le mécanisme existant `data-controls` (voir
     `schedule.enabled`, qui pilote déjà
     `#sc-time-row,#sc-days-row,#sc-rem-row`).
   - **Vérifie avant d'écrire** si le bot a un champ pour ça : cherche
     `schedule` dans `bot/guild_settings.py`, `bot/cogs/automation.py` et
     `bot/cogs/queue_config.py`. **S'il n'existe pas de clé côté bot, ne
     l'invente pas.** Fais la contrainte côté panneau (le choix sert à
     remplir les champs de la queue), écris-le en commentaire, et signale-le
     dans ta réponse finale **et** dans `docs/INVENTAIRE-REGLAGES.md`. Le
     dépôt interdit les réglages qui n'arrivent nulle part — c'est
     précisément le défaut que cette section a eu pendant des mois, et son
     commentaire actuel le raconte.
2. **L'aperçu de l'annonce**, le même `.dprev` — mais **sans aucun bouton**.
   Pas de « lancer maintenant », pas de « fermer ». La section programme,
   elle ne déclenche pas.
3. **L'heure est celle du bot, en UTC.** Le commentaire de la section le
   dit déjà, et c'est à garder : un organisateur à Paris qui lit « 21:00 »
   et voit la file s'ouvrir à 23 h croirait à une panne. La mention doit
   rester lisible **dans l'écran** (`sc.timeD`), pas seulement dans le code.
4. Les sept cases de jours restent fabriquées par le script
   (`[data-days]` → `schedule.days`, valeur « 0,5,6 ») : les noms des jours
   changent avec la langue, et les écrire dans le HTML obligerait à les
   traduire deux fois.

### 8.3 — Presets

La section `presets` existe déjà et ne change que de place : elle entre dans
la catégorie Queue. Garde le groupe « Emporter la configuration »
(export / import) avec son commentaire : tout se passe dans le navigateur,
rien n'est envoyé avant enregistrement, et les réglages propres à un
serveur (salons, rôles, mot de passe) ne sont **pas** exportés — un
identifiant de salon ne veut rien dire sur un autre serveur, et l'y poser
désignerait le vide.

Si tu touches au nom de la section dans le menu, **garde
`data-goto="presets"` et `data-nav-count="presets"`** : plusieurs scripts
les cherchent.

Après : `python outils/numeroter_versions.py`.

---

## Chantier 9 — Les statistiques

**Fichiers** : `site/assets/js/page-dashboard-memoire.js` (`rendreStats()`
l. 296-340, `visiter()` l. 601-615), `site/api/index.php` (relais l. 1091),
`api-locale/server.py` (`route_memoire`, l. 770),
`bot/cogs/dashboard_api.py` (`activity` l. 1210, `stats` l. 420),
`bot/history.py` (`stats` l. 254).

« Les statistiques du bot buggent » est trop vague pour corriger à
l'aveugle. **Diagnostique d'abord, corrige ensuite, et dis ce que tu as
trouvé.** Voici ce qui est **déjà écarté** — ne le refais pas :

- Les neuf clés `st2.*` existent dans les **cinq** langues : ce n'est pas
  un défaut de traduction.
- Les classes CSS sont toutes là : `.chiffres`, `.chiffre`, `.chiffre__n`,
  `.chiffre__l`, `.barres`, `.barre`, `.barre__fill`, `.barres__axe`,
  `.vide` (`dashboard.css` l. 1458-1509).
- `page-dashboard-memoire.js` est bien chargé par `dashboard.html`
  (l. 1153) **et** déclaré dans `outils/fichiers_du_site.py`.
- `app.js` émet bien `cyq:section` (l. 916) : le chargement paresseux
  `visiter('stats')` est donc déclenché à la première visite.
- Les clés rendues par `bot/history.py:stats()` correspondent une à une à
  celles que `rendreStats()` lit : `opened`, `launched`, `matches`,
  `abandonRate`, `avgWait`, `byHour`, `byDay`.
- Le relais PHP enlève la chaîne de requête avant de router
  (`parse_url(..., PHP_URL_PATH)`, l. 264) : `?days=30` ne casse pas
  l'expression régulière `^/guilds/(\d{5,25})/(matches|activity|audit)$`.

Ce qui reste à vérifier, dans cet ordre :

1. **Ouvre la section, console ouverte.** `cyq local`, puis
   `http://localhost:8765/dashboard.html?guild=<un id>#stats`. Note
   l'erreur exacte, le code HTTP exact, le corps exact.
2. **`charge[nom] = true` est posé AVANT l'appel** (l. 602-603) : un échec
   réseau marque la section comme chargée et **elle ne retentera jamais**,
   même en y revenant. Un bot éteint une seconde laisse donc un écran
   définitivement vide pour le reste de la visite. C'est un défaut réel, et
   à corriger **quoi qu'il arrive** : ne marque `charge[nom]` qu'au succès,
   ou efface le drapeau dans le `catch`. Même traitement pour
   `historique` et `journal`, qui ont le même mécanisme.
3. **`/api/stats` du bot n'est relayé par personne.**
   `bot/cogs/dashboard_api.py:254` ouvre `/api/stats` (`uptime_seconds`,
   `servers`, `users`, `commands_24h`), et **ni `site/api/index.php` ni
   `api-locale/server.py` ne le relaient** ; aucune page ne l'appelle. Si
   ce sont *ces* chiffres-là — les statistiques **du bot**, pas celles d'un
   serveur — que tu croyais voir, le défaut est là : la route n'arrive
   jamais jusqu'au site. Elle servira de toute façon au chantier 12.
4. **Les barres à zéro sont invisibles.** `barres()` calcule
   `max = Math.max.apply(null, valeurs.concat([1]))` : un serveur sans
   activité donne vingt-quatre barres de hauteur 0 et un axe seul.
   `.barre__fill` a bien `min-height: 2px`, mais à 0 % le trait reste
   quasi invisible : visuellement, ça ressemble à un écran cassé. Si c'est
   ça, la bonne réponse **n'est pas** d'inventer une hauteur minimale,
   c'est d'afficher l'état vide `st2.empty` quand **toutes** les valeurs
   sont nulles. Un graphique vide doit se dire, pas se dessiner.
5. **`byDay`** : `x.day.slice(8)` sur « 2026-10-29 » donne « 29 » —
   correct, mais trente barres à 375 px avec une étiquette sur trois reste
   dense. Vérifie-le réellement à cette largeur.

**Corrige ce que tu as constaté, et seulement ça** — plus le point 2, qui
est un vrai défaut dans tous les cas. Si rien ne se reproduit, dis-le
franchement, avec la liste de ce que tu as testé.

Après : `python outils/numeroter_versions.py`.

---

## Chantier 10 — Le serveur de support

**Fichiers** : `site/assets/js/config.js`, `site/support.html`, les cinq
fichiers de langue.

1. **Renseigne l'invitation** : dans `site/assets/js/config.js`,
   `SUPPORT_URL: '#'` → `'https://discord.gg/e9E8Fc4Bqb'`.
   Cette valeur alimente le lien « Support » de la navigation, celui du
   pied de page, et le bouton `[data-sp-discord]` de `support.html`
   (l. 184), qui est `hidden` tant que la configuration vaut `'#'`.
   Vérifie que le bouton apparaît bien une fois la valeur posée, et lis le
   commentaire de `support.html:50` avant de toucher au balisage : il
   explique pourquoi cette page-là ne porte pas `data-cfg-link` au même
   endroit que les autres.
2. **Retire la phrase sur les délais.** Clé `sp.delay` (« Les réponses ne
   sont pas automatiques : elles peuvent prendre quelques jours. ») :
   supprime-la du balisage de `support.html` **et des cinq fichiers de
   langue**. Vérifie par `grep` qu'aucune autre page ne l'utilise.
3. Profites-en pour vérifier les autres `data-cfg-link` de la page
   (`DOCS_URL`, `STATUS_URL`, `PRIVACY_URL`). `STATUS_URL` sera renseigné
   au chantier 12 ; **ne touche pas à `PRIVACY_URL`**, il n'a pas de cible.

Après : `python outils/numeroter_versions.py`.

---

## Chantier 11 — La documentation, redessinée

**Fichiers** : `site/guide.html`, `site/assets/css/guide.css`,
`site/assets/js/page-guide.js`.

Le reproche est précis : **les numéros `01`, `02`, `03`… font « page
générée »**. Ils sont partout — dans le sommaire
(`<span class="n">01</span>`, l. 90-94), dans chaque partie
(`<p class="label part__num">01 / 05</p>`, l. 102), dans les listes
`.notes` (`.notes .n`), et dans la numérotation automatique des `.steps`
(`counter-reset: pas`, `.steps li::before`, `guide.css` l. 69-80).

**Carte blanche sur le dessin**, dans ces limites :

- **Tous les numéros décoratifs partent** : sommaire, en-tête de partie,
  notes. Une exception possible, et une seule : les étapes de « Mise en
  route » (`.steps`) sont une **procédure ordonnée** — leur numérotation
  porte du sens. Garde-les numérotées si ça reste discret, ou trouve autre
  chose qui dit l'ordre. Ailleurs, rien.
- **Les cinq parties restent cinq parties**, avec les mêmes ancres :
  `#setup`, `#queue`, `#duel`, `#clan`, `#options`. Des liens pointent
  dessus depuis l'extérieur.
- **Le sommaire reste collant** (`.toc { position: sticky; top: 132px }`)
  et reste un vrai sommaire. Il doit continuer de fonctionner en rangée
  sous 900 px (`.toc__list` en `repeat(auto-fit, minmax(150px, 1fr))`).
- **`page-guide.js` suit le sommaire** et pose `aria-current="true"` sur
  l'entrée visible — lis-le avant de changer le balisage, et garde le
  mécanisme en état.
- **`.part { scroll-margin-top: 120px }` reste** : sans ça, une ancre passe
  sous la barre fixe.
- **Le contenu du texte ne change pas.** Tu redessines, tu ne réécris pas.
  Si une tournure te semble fausse, signale-la ; ne la corrige pas.
- **`guide.html` est en français en dur, sans `data-i18n`.** Ce chantier
  **n'est pas** celui de sa traduction. N'ajoute pas de clés à moitié : ou
  tu ne touches pas à l'i18n, ou tu fais la page entière dans les cinq
  langues — et dans ce cas dis-le, parce que c'est un chantier à soi seul.
  **Par défaut : n'y touche pas.**
- La D.A. reste celle de `home.css` : `--bg #0A0908`, `--panel #121110`,
  `--ink #F4F1EC`, `--accent #C08A5A` (cuivre, **un seul emploi par
  écran**), `--hair rgba(244,241,236,.08)`, police Geist. `guide.css` est
  une surcouche, pas une seconde direction artistique.
- Pas de nouvelle dépendance, pas d'icône tirée d'un CDN. Les SVG sont
  écrits en ligne, comme partout dans le dépôt.
- Si `.part__num` disparaît du balisage, **retire aussi ses règles CSS**
  devenues mortes, et dis-le dans ta réponse.

Après : `python outils/numeroter_versions.py`.

---

## Chantier 12 — `status.cyqbot.eu`

Le plus lourd, et le seul qui touche à l'infrastructure. Fais-le en dernier.

**Ce qu'on veut** : une page d'état publique pour **CreateYourQueue
uniquement** — pas une page générique, pas un faux tableau de bord
multi-services. Allure Cloudflare : un verdict en grand, les composants en
dessous, la latence en millisecondes, un historique lisible.

### 12.1 — D'où viennent les chiffres

Le bot sait déjà tout ce qu'il faut : lis `bot/cogs/statuspanel.py`,
`build_embed()` (l. 119-176). Il publie **dans Discord** l'uptime, la
latence (`self.bot.latency`, avec son garde `nan` tant que le premier
heartbeat n'est pas revenu), le nombre de serveurs, le nombre de membres,
et le nombre de **queues actives** (lues sur le cog `QueueConfig`). Il
qualifie même la liaison : `_quality()` (l. 102) → bon ≤ 150 ms, correct
≤ 400 ms, lent au-delà. **Reprends ces mêmes seuils.** Deux endroits qui
qualifient la même latence différemment, c'est une page d'état qui
contredit le bot.

Côté API, `bot/cogs/dashboard_api.py` expose déjà :

- `/api/health` → `status`, `bot`, `guilds` ;
- `/api/stats` (l. 420) → `uptime_seconds`, `servers`, `users`,
  `commands_24h`.

Il **manque la latence et les queues actives**. Ajoute-les — dans
`/api/health`, qui est la route faite pour ça, ou dans une route
`/api/status` si tu juges plus propre de ne pas changer une réponse que
quelqu'un consomme peut-être. **Vérifie qui appelle `/api/health` avant de
la modifier.** Mêmes gardes que `build_embed` : latence `nan` → 0, cog
absent → 0, jamais une valeur devinée.

### 12.2 — Pourquoi il faut du PHP, et pas du JavaScript

Ne fais **pas** appeler le bot par la page. Trois raisons, et chacune
suffit :

1. **L'appel au bot demande une clé.** `appel_bot()` dans
   `site/api/index.php` (l. 647) envoie `X-API-Key`. Cette clé autorise à
   **ouvrir des queues sur n'importe quel serveur** : elle n'a rien à faire
   dans une page publique. Elle vit dans `site/api/secrets.php`, qui n'est
   pas dans la liste d'envoi et se dépose à la main.
2. **CORS.** `status.cyqbot.eu` est une **autre origine** que
   `dashboard.cyqbot.eu`. L'API du panneau ne pose aucun en-tête CORS, et
   lui en ajouter pour cette page serait ouvrir une API de session à une
   origine tierce.
3. **L'adresse du bot ne doit pas être publique.** `bot_api_base` est une
   adresse de conteneur, port compris.

**Donc** : un petit PHP sur le sous-domaine, par exemple
`site/status/api/etat.php`, qui appelle le bot côté serveur, mesure le
temps de réponse, et rend un JSON minimal **sans aucun secret**. LWS
n'exécute que du PHP — c'est déjà la contrainte qui a produit
`site/api/index.php`.

- **Il lui faut ses propres secrets.** Ne lis pas `site/api/secrets.php` et
  ne le partage pas entre deux sous-domaines : écris un
  `site/status/api/secrets.exemple.php` sur le modèle de
  `site/api/secrets.exemple.php`, avec **seulement** `bot_api_base` et
  `bot_api_key`. Le vrai fichier se dépose à la main et **n'entre pas dans
  la liste d'envoi**.
- **Un cache court, obligatoire.** Une page d'état publique peut être
  rechargée en boucle : sans cache, chaque visite devient un appel au bot.
  Dix à trente secondes dans un fichier, sous `site/status/api/data/`, avec
  un `.htaccess` qui refuse l'accès — exactement comme
  `site/api/data/.htaccess`.
- **Le JSON rendu est public.** Donc : pas d'adresse de bot, pas de clé,
  pas de nom de serveur Discord, pas de nombre de membres par serveur. Un
  verdict, une latence, un uptime, un total de serveurs, un total de queues
  actives, un horodatage. Rien d'autre.
- **Bot éteint** : la page le dit clairement et garde sa forme. Pas de 500
  blanc, pas de chiffres de la dernière fois présentés comme actuels.

### 12.3 — La page

`site/status/index.html`, plus `site/status/assets/css/status.css` et
`site/status/assets/js/page-status.js`. Ou, si tu préfères réutiliser le
socle, `site/status.html` servi par le sous-domaine — **tranche, et dis
pourquoi**. Dans tous les cas :

- **Même D.A. que la vitrine** : `home.css`, police Geist, le cuivre
  `--accent` **une seule fois sur l'écran** (il est pour le verdict, et
  pour rien d'autre). Réutilise `home.css` au lieu de réécrire ses tokens.
- **La barre de navigation** de la vitrine, avec son retour vers
  `cyqbot.eu` : `app.js` récrit `data-site` avec `SITE_ORIGIN`, c'est le
  mécanisme à utiliser.
- **Le verdict en grand**, en haut : « Tous les systèmes sont
  opérationnels » / « Service dégradé » / « Service indisponible ».
  Dérive-le des seuils de `_quality()`, pas d'un jugement nouveau.
- **Les composants, en liste** : le bot (en ligne / hors ligne), la liaison
  Discord (latence en ms + qualité), le panneau web, l'API. Chaque ligne
  dit ce qu'elle mesure. **Ne liste pas un composant que tu ne mesures
  pas** : un voyant vert sans mesure derrière est un mensonge.
- **Les chiffres** : uptime, serveurs, queues actives. Pas de membres
  (voir 12.2).
- **Un historique, si et seulement si tu as de quoi le remplir.** Le bot ne
  garde aucun historique de disponibilité. Deux options honnêtes : le PHP
  tient un petit journal roulant (une ligne par relevé, N jours, dans
  `data/`), ou **il n'y a pas d'historique** et la page n'en montre pas.
  **Quatre-vingt-dix jours de barres vertes inventées sont exclus** : la
  règle du dépôt est « jamais de données inventées », et c'est exactement
  ce que cette page serait tentée de faire.
- **Rafraîchissement automatique** toutes les 30 à 60 s, avec un compte à
  rebours visible et un bouton pour rafraîchir tout de suite. Arrête-le sur
  `visibilitychange`.
- **i18n, cinq langues**, comme partout. Clés `stt.*`.
- Animations en `transform` / `opacity`, variante calme, `?motion=on`.
- Lisible à 375 px, sans défilement horizontal.
- **Pas de `<meta name="robots" content="noindex">`** : contrairement à
  `dashboard.html`, cette page est publique et doit pouvoir être indexée.

### 12.4 — Le déploiement, à préparer sans l'exécuter

- **Déclare les fichiers neufs** dans `outils/fichiers_du_site.py` : une
  liste `STATUT` à côté de `VITRINE` et `APPLICATION`, bâtie sur `COMMUN`
  si la page réutilise `home.css`, `app.js`, `config.js` et les cinq
  fichiers de langue. Ajoute-la à `DECLARES`. **`secrets.php` n'y figure
  jamais** ; `secrets.exemple.php`, oui.
- **`outils/publier_site.py`** : la fonction `cibles()` (l. 190) connaît
  `racine_site` et `racine_app`. Ajoute `racine_status` et le choix
  `statut` à `--cible` (l. 321, aujourd'hui `("site", "app", "tout")`).
  **Ne lis pas `outils/reglages/lws.json`** : documente la clé neuve dans
  `outils/reglages/lws.config.exemple.ps1` et dans `README.md`.
- **Un `.htaccess` pour le sous-domaine.** Celui de la racine est déployé
  sur les deux domaines et porte déjà des règles conditionnées sur l'hôte.
  Si `status.` reçoit le même fichier, **vérifie que les règles existantes
  ne s'y appliquent pas de travers** — en particulier
  `^(login|welcome|servers|dashboard)\.html$` vers `dashboard.cyqbot.eu`,
  dont la condition est `!^dashboard\.` et qui s'appliquerait donc aussi
  sur `status.`. Dans le doute, donne au sous-domaine son propre fichier,
  et dis-le.
- **`site/assets/js/config.js`** : `STATUS_URL: '#'` →
  `'https://status.cyqbot.eu'`. Trois pages ont déjà le lien « État du
  service » dans leur pied (`index.html:579`, `modules.html:515`,
  `support.html:214`) : il s'allumera tout seul.
- **Ne publie rien.** Écris dans ta réponse finale ce qui reste à faire à la
  main : créer le sous-domaine chez LWS, déposer `secrets.php`, renseigner
  `racine_status`.

---

## 13. Ce que tu dis à la fin

Une seule réponse, courte, et qui tient ces trois promesses :

1. **Ce qui a changé**, chantier par chantier, une ou deux lignes chacun,
   avec les fichiers touchés.
2. **Ce que tu as vérifié réellement** : quelle page, à quelle largeur,
   avec quel réglage de mouvement, et ce que disait la console. Et **ce que
   tu n'as pas pu vérifier** — notamment tout ce qui demande une API
   vivante, un bot allumé, ou Apache (les règles `.htaccess` ne jouent pas
   sous le serveur Python local).
3. **Les décisions que tu as prises à ma place**, et pourquoi : l'aperçu
   déplacé ou dupliqué (8.1), le preset de programmation si le bot n'a pas
   la clé (8.2), ce que tu as trouvé pour les statistiques (9), la route du
   bot étendue ou neuve (12.1), un `.htaccess` partagé ou propre au
   sous-domaine (12.4), l'existence ou non d'un historique de
   disponibilité (12.3).

Plus **un commit par chantier**, en français, dans le style des commits
existants (`git log --oneline -5` pour le ton : une phrase qui dit l'effet,
pas la liste des fichiers).

**N'exécute aucune publication.**
