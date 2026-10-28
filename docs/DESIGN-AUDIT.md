# DESIGN-AUDIT — ce que le prompt a trouvé, et ce qu'il n'a pas trouvé

Audit mené avant toute ligne de code, sur l'état du dépôt au moment de la
demande. Il est court pour une raison précise : **le diagnostic de la §2 du
prompt vise un autre codebase que celui-ci.**

## 1. Les symptômes cherchés par la §2

| Symptôme attendu | Occurrences trouvées |
|---|---|
| Palette `#6366f1` / `#8b5cf6` / `slate-900` | **0** |
| Dégradés purple→blue, titres en dégradé, glow, néon | **0** |
| Glassmorphism hors navigation | **0** |
| Icône Lucide dans un carré arrondi coloré devant chaque titre | **0** |
| Emojis, badges « ✨ AI-powered » | **0** |
| `gap-6` / `p-6` uniformes (Tailwind) | **0** — le projet n'utilise pas Tailwind |
| Fade-in CSS 300 ms identique partout | **0** |

Ces symptômes avaient déjà été traités dans les itérations précédentes : le
site était monochrome, sans dégradé, sans glassmorphism, et son motion était
orchestré. Un audit conforme à la §2 rendrait donc une page vide, ce qui
n'aurait informé personne.

## 2. Les écarts réels à la D.A. de référence

Voici ce qui séparait vraiment l'existant de la référence, avec le fichier
et la ligne d'origine.

| Écart | Où | Traitement |
|---|---|---|
| Le contenu touchait les bords du viewport : aucune coque | `index.html` (racine), `app.css` `body` | `<main class="shell">` en `--panel`, `border-radius: 36px`, `margin: 16px` |
| Rayon uniforme de 2 px sur tout | `app.css` `:root --r` | Quatre rayons : coque 36 · carte 24 · média 20 · pilule 999 · disque 50 % |
| Noir neutre-froid `#0C0C0B` | `app.css` `:root --bg` | Noir chaud `#0A0908`, panneau `#121110` |
| Boutons et champs rectangulaires à filet 1 px | `app.css` `.btn`, `.field` | Pilule claire, pilule fantôme, disque, texte souligné |
| Barre de navigation collée en haut, pleine largeur | `app.css` `.topbar` | Pilule flottante centrée, `backdrop-filter`, à 20 px du bord |
| Aucun wordmark, aucune profondeur par superposition | — | `CYQ` à 18 vw, coupé par le bas, opacité .08, derrière le contenu |
| Hiérarchie typographique plate (titre 54 px / corps 14 px, ratio 3,8×) | `app.css` `.hero__title` | Titre `clamp(2.5rem, 4.4vw, 4.25rem)` bas de casse, ragged right — ratio > 4,8× |
| Densité d'outil sur une page de présentation | `index.html` cinématique | Un point focal par écran, sections d'un plein écran |
| Aucun grain : rendu « propre » donc généré | — | Overlay `feTurbulence` à 3 %, `pointer-events: none` |
| Sections qui défilent l'une après l'autre | `page-home.js` | Empilement : chaque section glisse par-dessus, la sortante recule |

## 3. Ce que je n'ai pas appliqué, et pourquoi

**La photographie (§1.3, §1.6, §1.8).** Toute la couleur et toute la
profondeur de la référence viennent d'images — bois, caramel, poussière — et
d'un objet détouré en lévitation. Ce projet n'a aucune image hors son logo.
Faute de photo, le héros est porté par la typographie, le wordmark coupé et
un halo de matière sans arête ni cadre. Les cartes portrait 3:4 de la §1.8
n'ont donc pas lieu d'être : elles n'auraient contenu que du vide.

**Le périmètre.** La D.A. s'arrête à l'accueil. Le tableau de bord et le
sélecteur de serveur gardent leur direction « outil » : le brief initial de
ce projet posait que *« la densité est le vrai problème de design ici »*, ce
qui est frontalement opposé à la §1.12. Une vitrine et une console n'ont pas
à se ressembler ; elles ont à être bonnes chacune dans son registre.

**`npm i animejs` (§5).** Le site n'a aucune étape de build, ce qui est ce
qui permet de l'envoyer tel quel à l'hébergeur. anime.js v4.5.0 est donc
vendorisé en UMD dans `assets/js/vendor/`, et les exports nommés du prompt
(`animate`, `createTimeline`, `createScope`, `stagger`, `onScroll`, `utils`,
`splitText`) sont lus sur le global.

**Les livrables vidéo et les commits (§6.4, §6.5).** Le dossier n'est pas un
dépôt git. Les captures 390 / 1280 / 1440 sont fournies ; la vidéo ne l'est
pas.
