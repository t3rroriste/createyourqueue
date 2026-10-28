# Prompt — refonte de `servers.html`

À coller tel quel dans Claude Design. Le prompt est **autonome** : tout ce
qu'il faut connaître du site est écrit dedans, aucun fichier à ouvrir.

---

## 0. Avant d'écrire une ligne

**Charge ta skill de design et applique-la.** ← _(remplace par le nom exact
de ta skill avant d'envoyer : `/<nom-de-la-skill>`)_

Puis réponds-moi **trois lignes** : ce que tu as compris du problème, le
parti que tu prends, ce que tu sacrifies. Ensuite seulement, le code.

---

## 1. Le produit

**CreateYourQueue** — un bot Discord de file d'attente et son panneau web.
Quelqu'un se connecte avec Discord, choisit un de ses serveurs, puis
configure le bot dessus.

La page que tu refais est **`servers.html`** : le choix du serveur. C'est
l'écran entre la connexion et le panneau. Il est vu une fois par session,
quelques secondes, et il doit donner envie d'entrer.

## 2. Ce qu'il y a aujourd'hui, et pourquoi je n'en veux plus

Un tableau. En-tête de colonnes `SERVEUR · MEMBRES · ÉTAT · ACTION`, des
lignes grises, une barre de filtre, une case à cocher « Masquer sans le
bot », un bouton « Actualiser », un encadré d'aide en bas. Le tout en
Archivo + IBM Plex Mono, crème sur noir.

Ça ressemble à un back-office générique. Je veux l'inverse : **léger,
simple, propre**, et visiblement de la même famille que l'écran de
connexion (voir § 4).

## 3. La direction artistique — les jetons, exactement

Le site a deux D.A. qui ne se mélangent pas. `servers.html` passe sur la
**première**, celle de l'accueil et de la connexion. Copie ces valeurs
telles quelles, n'en invente aucune, n'en ajoute aucune.

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

**Le cuivre est tenu en laisse.** Trois emplois autorisés sur tout le
site : la flèche d'un bouton d'action, le point de pagination actif, un
indicateur de delta positif. Sur cette page, tu as droit à **un seul
emploi** — je te propose l'indicateur de la catégorie active dans le menu.
Jamais un fond, jamais un dégradé, jamais deux fois dans le même écran.

**Une seule police : Geist.** Pas de monospace. Le monospace est ce qui
fait « tableau d'administration » sur la version actuelle, et c'est
précisément ce dont je ne veux plus.

## 4. La structure que je veux

Trois zones.

**À gauche, un menu vertical** — les catégories de serveurs (§ 5). Largeur
confortable, pas un rail d'icônes. Chaque entrée : son nom, et son nombre
à droite, discret.

**En bas à gauche, sous le menu, l'utilisateur** — son avatar Discord rond
et son `@pseudo`, à la manière du panneau utilisateur de Discord : collé
en bas, discret, toujours visible. Une sortie de session accessible, sans
qu'elle crie.

**À droite, la liste des serveurs** — le contenu de la catégorie choisie.
Un serveur par ligne : son icône (ou ses initiales s'il n'en a pas), son
nom, son état, son action. Pas de colonnes alignées en en-tête de
tableau : chaque ligne se lit seule.

La référence visuelle est l'écran de connexion du site : un en-tête en
pilule flottante, un titre large, des cartes sombres à grand rayon
posées sur le noir, un bouton crème plein comme seule action remplie de
l'écran. Reste dans cette famille.

## 5. Les catégories du menu

Elles sont adossées à des **états réels** des données, jamais inventées :

| Catégorie | Ce qu'elle contient |
| --- | --- |
| Tous mes serveurs | tout ce que l'API renvoie |
| Configurés | `botPresent && configured` |
| À configurer | `botPresent && !configured` |
| Sans le bot | `!botPresent` |
| Droits insuffisants | `missingPermissions.length` ou `!canManage` |

**La dernière n'apparaît que si elle a au moins un serveur.** Une
catégorie vide affichée en permanence est un mensonge de plus.

Le filtre texte reste, mais il va **en haut de la liste de droite**, pas
dans une barre d'outils. La case « Masquer sans le bot » disparaît : elle
est remplacée par les catégories, qui font le même travail en mieux.

## 6. Les animations

- **`transform` et `opacity` uniquement.** Rien qui déclenche un calcul de
  mise en page dans une boucle. Pas de `box-shadow` animée, pas de
  `filter: blur()` animé sur une grande surface.
- **Au survol d'une catégorie**, je veux quelque chose de senti, pas vu :
  amplitude faible, 160–240 ms, `--e-out`. Un indicateur qui pousse depuis
  le bord gauche, le libellé qui avance de quelques pixels, le nombre qui
  se révèle. À toi de composer — mais **un seul objet bouge vite à la
  fois**, et le texte ne change jamais d'échelle.
- **Pas de rebond, pas d'élastique.** La classe est dans la retenue.
- **L'entrée de la page** : les lignes de serveurs arrivent en cascade,
  décalage court (40–60 ms), amplitude faible. Elles ne tombent pas de
  200 px.
- **`prefers-reduced-motion: reduce`** a toujours une variante calme : les
  états finaux sont posés, le mouvement disparaît, rien ne clignote. Le
  drapeau `?motion=on` force l'animation pour pouvoir la vérifier.
- `anime.js` v4 est déjà chargé en UMD (exports nommés sur le global
  `anime`). **Si la bibliothèque ne charge pas, la page doit rester
  lisible** : les états de départ se posent en JS, jamais en CSS.

## 7. Les états réels — tous à dessiner

Sans API, la page affiche ses vrais états vides. **Aucune donnée inventée,
aucun faux serveur de démonstration.**

1. **Chargement** — squelette des lignes, pas un spinner centré.
2. **Non connecté** — « Connexion requise » + bouton vers Discord.
3. **Erreur API** — « Impossible de charger tes serveurs · L'API n'a pas
   répondu. Rien n'a été modifié. » + réessayer.
4. **Aucun serveur éligible** — l'utilisateur n'est propriétaire de rien :
   un bouton « Créer un serveur et inviter le bot ».
5. **Le filtre ne donne rien** — « Aucun serveur ne correspond au filtre ».
6. **Catégorie vide** — un message par catégorie, pas un message générique.

Garde aussi la note du bas : seuls les serveurs où l'on est propriétaire
ou où l'on a « Gérer le serveur » apparaissent, c'est Discord qui le
décide, la liste est en cache 60 s. Mais trouve-lui une place qui ne
pèse pas.

## 8. Les données dont tu disposes

`GET /guilds` renvoie :

```js
[{ id, name, iconUrl, memberCount, botPresent, configured,
   missingPermissions: [], canManage, updatedAt }]
```

L'utilisateur connecté :

```js
{ id, username, global_name, avatar, discriminator }
// avatar  -> https://cdn.discordapp.com/avatars/<id>/<avatar>.png?size=64
// sinon   -> https://cdn.discordapp.com/embed/avatars/<0-5>.png
```

Les actions par état :

| État | Action |
| --- | --- |
| configuré | « Configurer » → `dashboard.html?guild=<id>` |
| bot présent, jamais configuré | « Lancer l'assistant » → même URL |
| bot absent | « Inviter le bot » → l'URL d'invitation |
| droits manquants | « Réautoriser » |
| accès révoqué | bouton désactivé |

## 9. L'internationalisation

Tout texte visible passe par `data-i18n="clé"` sur l'élément, ou
`data-i18n-attr="aria-label:clé, placeholder:clé"` pour un attribut. Cinq
langues : fr · en · es · de · ko.

Les clés qui existent déjà et que tu réutilises telles quelles :

```
sv.title sv.lead sv.count sv.filter
sv.stConfigured sv.stToConfigure sv.stNoBot sv.stNoPerms sv.stRevoked
sv.actConfigure sv.actWizard sv.actInvite sv.actFix
sv.neverConfigured sv.modified
sv.missTitle sv.missBody sv.missLink
sv.emptyTitle sv.emptyBody sv.emptyCta sv.noFilterTitle
sv.needLogin sv.needLoginBody sv.loadErr sv.loadErrBody sv.revokedHelp
c.refresh c.back c.lang c.skip
```

**Toute clé nouvelle doit m'être livrée dans les cinq langues.** Les
catégories du menu et la sortie de session en auront besoin.

## 10. Les contraintes techniques — non négociables

- **HTML / CSS / JS vanilla, aucun build.** Pas de React, pas de bundler,
  pas de Tailwind, pas de dépendance nouvelle. Apache sert les fichiers
  tels quels. JS en ES5 prudent, IIFE, `'use strict'`.
- **Aucun CDN.** Les polices viennent de Google Fonts comme le reste du
  site, tout le reste est hébergé.
- **Le CSS va dans un fichier neuf, `assets/css/servers.css`**, posé
  par-dessus `home.css` — exactement comme `auth.css` l'est pour la
  connexion. **N'importe aucun jeton de l'autre D.A.**
- **Accessibilité** : navigation au clavier complète, focus visible,
  contrastes tenus (`--ink-60` est le plancher du texte courant),
  `aria-live` sur la liste qui change.
- **Mobile d'abord** : aussi bon en 375 px qu'en 1440. En petit écran, le
  menu de gauche devient une rangée de catégories en tête de page — il ne
  disparaît pas dans un tiroir.
- **Commentaires en français**, et ils expliquent le **pourquoi** d'une
  valeur, pas le **quoi** de la ligne. C'est la convention de tout le code.

## 11. Ce que je refuse, explicitement

- Les numéros d'étape façon `01` `02` `03`, et toute numérotation
  décorative.
- Le monospace, les petites capitales très espacées en guise d'étiquette,
  les en-têtes de colonnes.
- Les cartes dans des cartes dans des cartes.
- Les dégradés, le néon, le violet SaaS, les ombres colorées, les emojis.
- Les icônes décoratives qui ne disent rien.
- Les faux chiffres, les faux serveurs, les fausses activités récentes.
- Une deuxième couleur d'accent.

## 12. Le livrable

1. Les trois lignes du § 0.
2. **`servers.html` en entier.**
3. **`assets/css/servers.css` en entier.**
4. **`assets/js/page-servers.js` en entier** — même contrat d'API, mêmes
   clés i18n, nouveau balisage.
5. Les clés i18n nouvelles, **dans les cinq langues**, prêtes à coller.

Pas d'extrait. Pas de `/* … reste inchangé */`. Pas de pseudo-code.
Si un choix te semble discutable, fais-le quand même et dis-le en une
ligne à la fin.
