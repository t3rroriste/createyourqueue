# Prompt — animation d'attente du panneau serveur

À coller tel quel dans une session Claude ouverte sur `Site Dashboard`.

---

## Contexte

Tu travailles sur **CreateYourQueue**, un dashboard web pour un bot Discord de file
d'attente. Quand l'utilisateur choisit un serveur, il passe par un écran de
transition de 5 secondes avant d'arriver sur son panneau. Cet écran existe déjà,
il est correct, et il est **ennuyeux** : un anneau qui se remplit autour du logo.

Je veux le remplacer par une animation d'attente qui a de la classe et qui innove.
Pas un spinner de plus.

## Ce qui est en place

- `welcome.html` — l'écran de transition (le splash)
- `assets/css/auth.css` — les règles `.splash`, `.splash__logo`, `.splash__ring`,
  `.splash__arc`, `.splash__halo`, `.splash__title`, `.splash__lead`, `.splash__skip`
- `assets/js/page-welcome.js` — la séquence : logo, anneau sur 5 s, puis
  `location.replace()` vers `dashboard.html?guild=…` (ou `servers.html` si le
  paramètre `guild` manque)

Lis ces trois fichiers avant d'écrire quoi que ce soit.

## Contraintes techniques — non négociables

- **HTML/CSS/JS vanilla, aucun build.** Pas de React, pas de bundler, pas de
  dépendance nouvelle. Les fichiers sont servis tels quels par Apache.
- **anime.js v4 en UMD** est déjà chargé, les exports nommés se lisent sur le
  global `anime`. Si la bibliothèque n'a pas chargé, la page doit rester lisible
  et la redirection doit quand même partir.
- **Les tokens existants, rien d'autre** : `--bg #0A0908`, `--panel #121110`,
  `--ink #F4F1EC`, `--accent #C08A5A`, `--hair rgba(244,241,236,.08)`.
  Polices : Archivo et Geist.
- **Un seul accent, tenu en laisse.** Le cuivre `--accent` est la seule couleur
  de l'écran. Pas de dégradé arc-en-ciel, pas de néon, pas de violet SaaS.
- **60 fps** : `transform` et `opacity` uniquement. Rien qui déclenche un layout
  dans une boucle. Pas de `box-shadow` animée, pas de `filter: blur()` animé sur
  une grande surface.
- **`prefers-reduced-motion: reduce`** → variante calme, attente raccourcie à
  1,5 s, pas de mouvement continu. Le flag `?motion=on` force l'animation.
- **Le lien « Ouvrir maintenant » reste cliquable du début à la fin**, c'est la
  sortie de secours d'un écran dont la fin est un minuteur.
- **Commentaires en français**, comme le reste du code, et qui expliquent le
  *pourquoi* d'une valeur, pas le *quoi* de la ligne.

## Ce que je veux de l'animation

Le brief tient en une phrase : **l'attente doit raconter quelque chose au lieu de
tourner en rond.**

Un spinner dit « patiente ». Je veux un écran qui dit « voilà ce qu'on prépare ».
Trois pistes, choisis-en **une** et défends ton choix en trois lignes avant de
coder :

1. **La file qui se forme** — le produit est une file d'attente. Des jetons
   entrent par la droite, se rangent, se compactent, le dernier se cale pile au
   moment où le panneau s'ouvre. La métaphore est le produit lui-même.
2. **Le panneau qui s'assemble** — le squelette filaire du dashboard se dessine
   trait par trait au centre de l'écran (sidebar, en-tête, blocs), puis cède la
   place à la vraie interface. L'attente devient un aperçu de la destination.
3. **La latence rendue visible** — un balayage lent qui traverse l'écran, des
   paquets qui remontent du serveur vers le logo, un rythme de respiration.
   Sobre, technique, haut de gamme.

Quelle que soit la piste :

- **La progression doit être honnête.** Elle est adossée aux 5 secondes réelles,
  pas à une boucle décorative qui ment sur l'avancement. Si tu peux l'accrocher
  à un événement réel (préchargement de `dashboard.html`, chargement des polices),
  fais-le et raccourcis l'attente dès que c'est prêt.
- **La fin doit être nette.** Le dernier geste de l'animation et le basculement
  vers le panneau sont un seul mouvement, pas deux événements qui se télescopent.
  Sortie rapide (ease-in, ~70 ms), entrée posée (~200 ms).
- **Pas de rebond, pas d'élastique.** La classe est dans la retenue : des courbes
  lentes, des amplitudes faibles, un seul élément qui bouge vite à la fois.
- **Ça doit tenir en boucle** si le réseau traîne au-delà de 5 s, sans jamais
  donner l'impression que c'est bloqué.
- **Mobile d'abord** : l'écran doit être aussi bon en 375 px de large qu'en 1440.

## Livrable

1. Les trois lignes qui justifient la piste choisie.
2. Les fichiers modifiés **en entier** : `welcome.html`, le bloc `.splash*` de
   `assets/css/auth.css`, et `assets/js/page-welcome.js`. Pas d'extrait, pas de
   `// … reste inchangé`.
3. Vérifie le résultat toi-même dans le navigateur avant de me le rendre :
   ouvre `welcome.html?guild=test&motion=on`, prends une capture à mi-parcours,
   contrôle la console, puis refais le test en reduced-motion et en 375 px.
4. Dis-moi en une ligne ce que tu as vérifié et ce que tu n'as pas pu vérifier.
