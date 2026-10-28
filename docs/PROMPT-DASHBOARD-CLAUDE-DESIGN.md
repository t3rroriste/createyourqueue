# Prompt — refonte de `dashboard.html`

À coller tel quel dans Claude Design. Le prompt est **autonome** : tout ce
qu'il faut connaître du site est écrit dedans, aucun fichier à ouvrir.

---

## 0. Avant d'écrire une ligne

**Charge ta ou tes skills de design et applique-les.**

Puis réponds-moi **trois lignes** : ce que tu as compris du problème, le
parti que tu prends, ce que tu sacrifies. Ensuite seulement, le code.

---

## 1. Le produit

**CreateYourQueue** — un bot Discord de file d'attente et son panneau web.
Quelqu'un se connecte avec Discord, choisit un de ses serveurs, puis
configure le bot dessus.

La page que tu refais est **`dashboard.html`** : cette configuration. C'est
le dernier écran du parcours, et le seul où l'on reste longtemps.

## 2. Le vrai problème de cette page

Ce n'est pas une page de marketing. C'est une **console de réglages
dense** : dix sections, et à l'intérieur **14 interrupteurs, 11 champs
numériques, 11 listes déroulantes, 2 contrôles segmentés**, répartis sur
17 rangées de réglage.

Le piège est là. Une console de réglages devient vite un formulaire
administratif : des lignes grises, des libellés à gauche, des contrôles à
droite, et rien qui respire. C'est exactement ce qui est arrivé à la
version actuelle.

**Ta mission tient en une phrase : rendre léger un écran dense.** Pas en
cachant des réglages derrière des onglets, pas en les empilant dans des
accordéons — en travaillant le rythme, la hiérarchie et le vide.

## 3. La direction artistique — les jetons, exactement

Le site a une seule D.A., celle de l'accueil, de la connexion, de l'écran
de transition et du choix du serveur. **Le panneau la rejoint.** Copie ces
valeurs telles quelles, n'en invente aucune, n'en ajoute aucune.

```css
/* noir chaud, jamais bleuté */
--bg:       #0A0908;   /* le fond, derrière tout */
--panel:    #121110;   /* un bloc posé dessus */
--raised:   #24211F;   /* un creux dans un bloc */
--raised-2: #2E2A28;

/* encre */
--ink:    #F4F1EC;                 /* texte principal */
--ink-60: rgba(244,241,236,.60);   /* plancher du texte courant */
--ink-40: rgba(244,241,236,.40);   /* JAMAIS de texte courant — décor seul */
--hair:   rgba(244,241,236,.08);   /* filet */
--film:   rgba(244,241,236,.05);   /* fond d'une pilule fantôme */

/* l'unique accent */
--accent: #C08A5A;   /* cuivre */

/* formes — le rayon n'est jamais uniforme */
--r-shell: 36px;  --r-card: 24px;  --r-media: 20px;  --r-pill: 999px;
--gutter: 16px;

/* respiration */
--sp-1: 8px; --sp-2: 16px; --sp-3: 32px; --sp-4: 64px; --sp-5: 120px;

/* mouvement */
--e-out:  cubic-bezier(.16,1,.3,1);
--e-soft: cubic-bezier(.4,0,.2,1);

--sans: 'Geist', 'Archivo', system-ui, sans-serif;
```

**Le cuivre est tenu en laisse.** Un seul emploi par écran. Sur une page à
dix sections, « par écran » veut dire **par section visible** : l'indicateur
de la section active dans le menu, et rien d'autre. Jamais un fond, jamais
un dégradé, jamais deux fois à l'image.

**Une seule police : Geist. Pas de monospace.** Le monospace est ce qui
faisait « panneau d'administration » sur la version actuelle, et c'est
précisément ce dont je ne veux plus.

**Sombre uniquement.** L'ancien panneau avait un thème clair ; il
disparaît. Ne prévois aucune variante claire, et aucun bouton pour en
changer.

## 4. La page sœur, dont tu dois être le frère

`servers.html` vient d'être refait dans cette D.A. : en-tête en pilule
flottante au centre, menu vertical à gauche avec un indicateur cuivre sur
l'entrée active, avatar Discord et `@pseudo` collés en bas à gauche,
contenu à droite, cartes sombres à grand rayon posées sur le noir.

**Le panneau doit se lire comme la suite de cet écran-là**, pas comme une
autre application. Même en-tête, même menu, même pied de menu avec le
compte. Quelqu'un qui passe de l'un à l'autre ne doit pas avoir
l'impression de changer de produit.

## 5. Les dix sections

Le menu de gauche les liste dans cet ordre. Elles sont regroupées, et le
regroupement doit se voir sans qu'on l'écrive en gros.

| Section | Ce qu'elle contient |
| --- | --- |
| Langue | 5 choix. Change aussi le nom des salons et rôles créés par le bot. |
| Fonctions | Classement, Match & MMR, Clans, Annonce des adhésions, Panneau d'état, Mot de passe des queues. |
| Salons | Commandes, annonces, vocal d'attente, résultats, classement, catégorie des clans. |
| Rôles | Organisateur, notification de queue, chef de clan, transfert de clan. |
| MMR | 3 interrupteurs et 8 valeurs : départ, victoire, défaite, MVP, série, durées de vote. |
| Queue par défaut | 2 à 6 équipes, 1 à 6 joueurs, nom et couleur par équipe, session, heure, type, vote des capitaines. |
| Presets | Jusqu'à 10 configurations de queue enregistrées et rechargeables. |
| Logs | 10 journaux : vocal, messages, queue, match, duel, clan, commandes, arrivées, modération, serveur. |
| Sécurité | Anti-lien, nettoyage automatique, anti-raid et ses seuils. |
| Diagnostic | Les permissions du bot, salon par salon, et ce qui lui manque. |

Une seule section est visible à la fois. Les autres sont masquées, pas
détruites — on navigue entre elles par le menu et par l'ancre dans l'URL
(`#mmr`, `#logs`…).

## 6. Les contrôles — là où la page se gagne ou se perd

Six familles, et c'est tout. Dessine-les **une fois**, proprement, et ne
t'en écarte plus :

1. **L'interrupteur** (14 occurrences) — un réglage qui est oui ou non.
2. **Le champ numérique** (11) — une valeur bornée, avec son unité.
3. **La liste déroulante** (11) — choisir un salon, un rôle, une langue.
   Les listes de salons et de rôles sont **longues** et se filtrent au
   clavier.
4. **Le segmenté** (2) — deux ou trois choix exclusifs, tous visibles.
5. **La rangée de réglage** (17) — ce qui porte les quatre précédents :
   un libellé, une explication courte, le contrôle. C'est la brique la plus
   répétée de la page : si elle est lourde, toute la page est lourde.
6. **Le groupe** — ce qui réunit des rangées qui vont ensemble.

**Sur la rangée, la question à trancher** : l'explication sous chaque
libellé double la hauteur de la page. La supprimer rend les réglages
opaques. Trouve la troisième voie et défends-la.

## 7. Les animations

- **`transform` et `opacity` uniquement.** Rien qui déclenche un calcul de
  mise en page dans une boucle. Pas de `box-shadow` animée, pas de
  `filter: blur()` animé sur une grande surface.
- **Le passage d'une section à l'autre** est le geste principal de la
  page : il arrive des dizaines de fois par visite. Court, discret,
  jamais un glissement horizontal de toute la colonne. 180–260 ms,
  `--e-out`.
- **L'indicateur du menu** se déplace d'une entrée à l'autre plutôt que de
  disparaître et réapparaître.
- **Un réglage qui change doit se voir** — c'est la seule confirmation que
  l'utilisateur reçoit. Discret, immédiat, et jamais un encadré qui
  s'ouvre et pousse le reste de la page vers le bas.
- **Pas de rebond, pas d'élastique.** Un seul objet bouge vite à la fois.
- **`prefers-reduced-motion: reduce`** a toujours une variante calme ; le
  drapeau `?motion=on` force l'animation pour pouvoir la vérifier.
- `anime.js` v4 est déjà chargé en UMD (exports nommés sur le global
  `anime`). **Si la bibliothèque ne charge pas, la page doit rester
  utilisable** : les états de départ se posent en JS, jamais en CSS.

## 8. Les états réels — tous à dessiner

**Aucune donnée inventée, aucun faux serveur, aucun faux chiffre.**

1. **Chargement** — squelette de la section, pas un spinner centré.
2. **Sans API** — la page reste navigable et affiche ses états vides.
3. **Enregistrement en cours**, **enregistré**, **échec de
   l'enregistrement** — trois états d'une même rangée.
4. **Permissions manquantes** — le bot ne peut pas faire ce qu'on lui
   demande ; la section Diagnostic le détaille salon par salon, et le menu
   doit le signaler sans crier.
5. **Presets : aucun enregistré** — et le chemin pour en créer un.

## 9. Les données dont tu disposes

`GET /guilds/{id}` renvoie :

```js
{ id, name, iconUrl, memberCount,
  channels: [{ id, name, category, disabled }],
  voiceChannels: [...], categories: [...],
  roles: [{ id, name, position }], botRolePosition,
  permissions: [{ channel, view, write, manage, state }],
  missingPermissions: [...], presets: [...],
  settings: { "mmr.start": 1000, ... } }
```

`PATCH /guilds/{id}/settings` reçoit `{ "clé": "valeur" }`. **Un réglage
part dès qu'il change** — il n'y a pas de bouton « Enregistrer » en bas de
page, et il n'en faut pas.

L'utilisateur connecté, pour le pied du menu :

```js
{ id, username, global_name, avatar, discriminator }
// avatar  -> https://cdn.discordapp.com/avatars/<id>/<avatar>.png?size=64
// sinon   -> https://cdn.discordapp.com/embed/avatars/<0-5>.png
```

## 10. L'internationalisation

Tout texte visible passe par `data-i18n="clé"`, ou
`data-i18n-attr="aria-label:clé, placeholder:clé"` pour un attribut. Cinq
langues : fr · en · es · de · ko.

Les clés des sections existent déjà et se réutilisent telles quelles :
`s.language` `s.languageD` `s.functions` `s.functionsD` `s.channels`
`s.channelsD` `s.roles` `s.rolesD` `s.mmr` `s.mmrD` `s.queue` `s.queueD`
`s.presets` `s.presetsD` `s.logs` `s.logsD` `s.security` `s.securityD`
`d.config` `d.diagnostic` `d.navWarn` `c.lang` `c.back` `c.skip`.

**Toute clé nouvelle doit m'être livrée dans les cinq langues.**

## 11. Les contraintes techniques — non négociables

- **HTML / CSS / JS vanilla, aucun build.** Pas de React, pas de bundler,
  pas de Tailwind, pas de dépendance nouvelle. Apache sert les fichiers
  tels quels. JS en ES5 prudent, IIFE, `'use strict'`.
- **Aucun CDN.** Les polices viennent de Google Fonts comme le reste du
  site, tout le reste est hébergé.
- **Le CSS va dans un fichier neuf, `assets/css/dashboard.css`**, posé
  par-dessus `home.css` — comme `servers.css` l'est pour le choix du
  serveur. **N'importe aucun jeton de l'ancienne feuille `app.css`**, qui
  est destinée à disparaître.
- **Aucune valeur de style écrite en JS.** Le JS pose des classes et des
  mesures, jamais des choix de design. C'est la règle actuelle du fichier
  et elle est bonne.
- **Accessibilité** : navigation au clavier complète sur dix sections et
  une soixantaine de contrôles, focus visible, contrastes tenus
  (`--ink-60` est le plancher du texte courant), chaque contrôle lié à son
  libellé, le changement de section annoncé.
- **Mobile d'abord** : utilisable en 375 px. Le menu de gauche devient une
  rangée de sections en tête de page — il ne disparaît pas dans un tiroir.
- **Commentaires en français**, et ils expliquent le **pourquoi** d'une
  valeur, pas le **quoi** de la ligne.

## 12. Ce que je refuse, explicitement

- Les numéros d'étape façon `01` `02` `03`, et toute numérotation
  décorative.
- Les **carrés** : les angles durs, les grilles de tuiles, les blocs de
  même taille alignés au cordeau.
- Le monospace, les petites capitales très espacées en guise d'étiquette,
  les en-têtes de colonnes.
- Les cartes dans des cartes dans des cartes.
- Les dégradés, le néon, le violet SaaS, les ombres colorées, les emojis.
- Les icônes décoratives qui ne disent rien.
- Les faux chiffres, les faux graphiques, les fausses statistiques
  d'activité. Ce panneau configure un bot, il ne mesure rien.
- Une deuxième couleur d'accent.
- Un thème clair.

## 13. Le livrable

1. Les trois lignes du § 0.
2. **`dashboard.html` en entier.**
3. **`assets/css/dashboard.css` en entier.**
4. **`assets/js/page-dashboard.js` en entier** — même contrat d'API, mêmes
   clés i18n, nouveau balisage.
5. Les clés i18n nouvelles, **dans les cinq langues**, prêtes à coller.

Pas d'extrait. Pas de `/* … reste inchangé */`. Pas de pseudo-code.
Si un choix te semble discutable, fais-le quand même et dis-le en une
ligne à la fin.
