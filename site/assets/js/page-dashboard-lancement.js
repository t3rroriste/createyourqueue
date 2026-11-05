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

  /* Le plafond. 3 s pour la barre, puis le fondu. */
  var PLAFOND = 3000;
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

    A.animate(logo, {
      opacity: [0, 1], scale: [0.94, 1],
      duration: 520, ease: A.cubicBezier(.16, 1, .3, 1),
    });
    /* Une respiration, pas un clignotement : 3 % d'échelle, aller et
       retour, le temps que dure l'attente. Elle s'arrête d'elle-même
       quand l'écran part. */
    A.animate(logo, {
      scale: [1, 1.035], duration: 1400, delay: 520,
      ease: 'inOutQuad', loop: true, alternate: true,
    });
    animBarre = A.animate(barre, {
      scaleX: [0, 0.9], duration: PLAFOND, ease: 'outQuart',
    });
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
    if (barre && !calme) barre.style.transitionDuration = '220ms';
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
    }, calme ? 0 : 200);
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
