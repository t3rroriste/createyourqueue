/* =========================================================================
   CreateYourQueue — l'écran de lancement du panneau
   =========================================================================
   Le logo, une barre qui monte, et le panneau derrière qui se prépare.
   Il part QUAND LES DONNÉES SONT LÀ, pas au bout d'un compte à rebours
   décoratif : c'est ce qui le distingue d'une animation d'attente. Avant
   lui, on voyait le panneau se dessiner avec ses tirets cadratins puis
   les chiffres tomber un par un, et deux bandeaux d'erreur apparaître en
   cours de route.

   TROIS SECONDES AU MAXIMUM, et c'est un plafond, pas une durée. Si la
   fiche arrive en 200 ms — ce qu'elle fait depuis que l'API ne sérialise
   plus ses appels — la barre se termine en 200 ms. Un écran d'attente
   qui attend plus longtemps que nécessaire devient une taxe sur chaque
   visite.

   LE SIGNAL QU'IL ÉCOUTE est `cyq:charge`, que page-dashboard.js diffuse
   depuis `finChargement()` — le seul endroit par lequel les TROIS fins
   passent : la réussite, l'échec, et l'absence d'API. Écouter `cyq:guild`
   n'aurait couvert que la première, et l'écran serait resté trois
   secondes de plus chaque fois que quelque chose n'allait pas.

   LE SIGNAL QU'IL DIFFUSE est `cyq:pret`. page-dashboard.js joue son
   ouverture dessus plutôt qu'au chargement : les deux mouvements se
   suivent au lieu de se superposer.

   RIEN NE DÉPEND DE CE FICHIER POUR QUE LA PAGE MARCHE. Si anime.js
   manque, la barre avance quand même (transition CSS). Si ce script-ci
   manque, l'en-tête de la page retire `splash-on` toute seule au bout de
   3,6 s et page-dashboard.js ouvre sur son propre filet. Une page de
   chargement qui reste coincée est pire que pas de page de chargement.
   ========================================================================= */

(function () {
  'use strict';

  var racine = document.documentElement;
  var ecran = document.querySelector('[data-splash]');

  /* Pas d'écran dans la page, ou l'en-tête ne l'a pas allumé : il n'y a
     rien à piloter, et page-dashboard.js ouvrira de son côté. */
  if (!ecran || !racine.classList.contains('splash-on')) return;

  var barre = ecran.querySelector('[data-splash-bar]');
  var logo = ecran.querySelector('[data-splash-logo]');
  var loupe = ecran.querySelector('[data-splash-loupe]');
  var anneau = ecran.querySelector('[data-splash-anneau]');
  var reflet = ecran.querySelector('[data-splash-reflet]');

  /* ==================================================================
     LES DEUX VARIANTES DE LA LOUPE

     Elles ne font pas la même promesse, et c'est pour ça qu'il y en a
     deux plutôt qu'un réglage de vitesse :

       « balayage » — la loupe cherche. Elle décrit un petit arc dans son
         disque, comme une main qui passe au-dessus de quelque chose. Le
         geste dit ce que le produit fait, et il se lit même à 76 px.

       « reflet »   — la loupe est posée, et la lumière passe dessus. Un
         trait clair traverse le verre, une fois par tour. C'est plus
         calme, plus « marque », et ça ne raconte rien — ce qui est
         parfois exactement ce qu'on veut d'un logo.

     ON EN CHOISIT UNE, à `VARIANTE`. `?logo=balayage` ou `?logo=reflet`
     dans l'adresse force l'autre le temps de comparer, sans toucher au
     fichier — même mécanisme que `?motion=on`.

     Les deux ne bougent QUE par `transform` et `opacity`. Une loupe
     qu'on animerait par ses attributs SVG — `cx`, `r`, le tracé — ferait
     recalculer la géométrie à chaque image, ce que le reste du site
     s'interdit.
     ================================================================== */

  var VARIANTE = 'balayage';

  var demandee = /[?&]logo=(balayage|reflet)(&|$)/.exec(location.search);
  if (demandee) VARIANTE = demandee[1];

  /* TROIS SECONDES EN TOUT, et c'est là-dessus que le chiffre est
     calculé : 2,8 s de montée plus les 200 ms du dernier bond jusqu'à
     100 %. Mettre 3 s sur la seule montée aurait fait 3,2 s à l'écran,
     et « 3 secondes au maximum » serait devenu approximatif — c'est le
     genre de promesse qu'on tient ou qu'on ne fait pas. */
  var PLAFOND = 2800;
  var BOND = 200;
  /* En dessous, l'écran clignote au lieu de se montrer : on lit le logo,
     pas le mouvement. 420 ms est le plancher à partir duquel une
     apparition se lit comme une apparition et non comme un défaut. */
  var PLANCHER = 420;
  var FONDU = 380;

  var A = window.anime;
  var calme = (function () {
    if (racine.classList.contains('motion-force')) return false;
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; }
    catch (e) { return false; }
  })();

  var depart = Date.now();
  var fini = false;
  var animBarre = null;

  function poserBarre(part) {
    if (barre) barre.style.transform = 'scaleX(' + part + ')';
  }

  /* ==================================================================
     LA MONTÉE

     La barre va jusqu'à 90 % en trois secondes, et jamais jusqu'au bout
     toute seule : les 10 % restants sont ce que la réponse apporte. Une
     barre qui atteint 100 % avant que la page ne soit prête annonce une
     chose fausse, et c'est le genre de mensonge qu'on remarque — on
     attend devant une barre pleine.

     `scaleX` et non la largeur : une largeur animée fait recalculer la
     mise en page à chaque image, ce que le reste du site s'interdit.
     ================================================================== */

  function monter() {
    poserBarre(0);
    if (logo) logo.style.opacity = '0';

    if (calme) {
      /* Variante calme : pas de montée continue. La barre se pose à un
         tiers, et sautera à 1 quand la réponse arrivera. Deux états au
         lieu d'un mouvement — ça dit la même chose sans bouger. */
      if (logo) logo.style.opacity = '1';
      poserBarre(0.34);
      return;
    }

    if (!A) {
      /* Sans anime.js, la transition CSS fait le travail. Il faut
         seulement laisser passer une image entre les deux valeurs, sinon
         le navigateur les regroupe et rien ne bouge. */
      if (logo) logo.style.opacity = '1';
      requestAnimationFrame(function () {
        if (barre) barre.style.transitionDuration = PLAFOND + 'ms';
        poserBarre(0.9);
      });
      return;
    }

    /* L'arrivée est la même pour les deux variantes : le logo entier se
       pose. Ce qui les sépare commence après, et ne concerne que ses
       pièces. */
    A.animate(logo, {
      opacity: [0, 1], scale: [0.94, 1],
      duration: 520, ease: A.cubicBezier(.16, 1, .3, 1),
    });

    if (VARIANTE === 'reflet') refletEnBoucle();
    else balayageEnBoucle();

    animBarre = A.animate(barre, {
      scaleX: [0, 0.9], duration: PLAFOND, ease: 'outQuart',
    });
  }

  /* ---- A. le balayage : la loupe cherche ------------------------------

     Quatorze degrés, pas plus. Au-delà, la loupe sort visiblement de son
     disque et on voit une pièce détachée qui glisse ; en deçà de dix,
     on se demande si quelque chose bouge. L'anneau reste immobile —
     c'est le cadre, et un cadre qui tremble donne le mal de mer.

     L'aller-retour est volontairement lent (1,5 s) : à 76 px, un geste
     rapide se lit comme un défaut d'affichage. */
  function balayageEnBoucle() {
    if (!loupe) return;
    A.animate(loupe, {
      rotate: [-14, 14],
      duration: 1500, delay: 420,
      ease: 'inOutSine', loop: true, alternate: true,
    });
  }

  /* ---- B. le reflet : la lumière passe sur le verre -------------------

     Un trait clair qui traverse le verre, enfermé dedans par un
     `clipPath` — sans lui, il balaierait tout le disque et ce ne serait
     plus un reflet mais un essuie-glace.

     Il ne traverse pas en continu : il passe, puis il attend. Une
     lumière qui tourne sans fin devient un gyrophare ; une qui passe
     toutes les deux secondes se remarque à peine, et c'est le but.

     L'opacité monte à 0,26, et le chiffre a été réglé À 76 PX et non
     sur une maquette agrandie : à 0,2 le reflet était net sur un logo
     de 190 px et proprement invisible à la taille où il vit. Le dégradé
     éteint les deux bords, donc seule la crête atteint cette valeur —
     c'est ce qui l'empêche de devenir une tache. */
  function refletEnBoucle() {
    if (!reflet) return;
    /* `translateX` et non `x` : sur un rectangle SVG, `x` est aussi un
       attribut de géométrie, et le déplacer par là fait recalculer la
       forme à chaque image. La translation reste une affaire de
       composition. */
    A.animate(reflet, {
      translateX: [-70, 190],
      opacity: [
        { to: 0.26, duration: 170 },
        { to: 0.26, duration: 380 },
        { to: 0, duration: 250 },
      ],
      duration: 800, delay: 520,
      ease: 'inOutQuad', loop: true, loopDelay: 1100,
    });
    /* Le disque respire pendant que la lumière passe — 2,5 %, assez pour
       que l'écran ne soit pas tout à fait immobile entre deux reflets. */
    if (anneau) {
      A.animate(logo, {
        scale: [1, 1.025], duration: 1900, delay: 520,
        ease: 'inOutQuad', loop: true, alternate: true,
      });
    }
  }

  /* ==================================================================
     LA SORTIE

     Elle est demandée par `cyq:charge`, ou par le plafond. Dans les deux
     cas elle passe par ici, une seule fois, et elle respecte le
     plancher : une réponse immédiate ne doit pas faire clignoter
     l'écran.
     ================================================================== */

  function terminer() {
    if (fini) return;
    fini = true;
    var reste = Math.max(0, PLANCHER - (Date.now() - depart));
    setTimeout(sortir, reste);
  }

  function sortir() {
    if (animBarre && animBarre.pause) animBarre.pause();

    /* Les 10 % restants, d'un coup : c'est le moment où la page devient
       vraie, et il se voit. */
    if (barre && !calme) barre.style.transitionDuration = BOND + 'ms';
    poserBarre(1);

    setTimeout(function () {
      racine.classList.remove('splash-on');
      /* Le panneau s'ouvre pendant que l'écran s'efface : les deux
         mouvements se recouvrent au lieu de se succéder, ce qui enlève
         le temps mort entre les deux. */
      document.dispatchEvent(new CustomEvent('cyq:pret'));
      /* L'écran est retiré du document une fois le fondu passé. Laissé
         là, il garde une couche opaque au-dessus de la page — invisible,
         mais qui intercepterait les clics si une règle changeait. */
      setTimeout(function () {
        if (ecran.parentNode) ecran.parentNode.removeChild(ecran);
      }, calme ? 0 : FONDU + 60);
    }, calme ? 0 : BOND);
  }

  /* ==================================================================
     LES BRANCHEMENTS
     ================================================================== */

  document.addEventListener('cyq:charge', terminer);

  /* Le plafond, qui vaut aussi de filet : une requête qui n'aboutit ni
     ne échoue — un réseau qui ne répond pas — ne laissera pas l'écran
     en place. */
  setTimeout(terminer, PLAFOND);

  /* « Chargement… » dit une fois, dans la région annoncée de la page.
     L'écran lui-même est `aria-hidden` : un logo et une barre ne se
     lisent pas. */
  var live = document.querySelector('[data-live]');
  if (live && window.CYQ && window.CYQ.t) live.textContent = window.CYQ.t('c.loading');

  monter();
})();
