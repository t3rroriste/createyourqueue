/* =========================================================================
   Modules — motion.
   anime.js v4, chargé en UMD (le site n'a pas d'étape de build) : les
   exports nommés sont donc lus sur le global `anime`.

     entree()   — l'en-tête, en UNE timeline
     reveler()  — chaque rangée à son entrée dans l'écran, une seule fois

   Règles tenues : on n'anime que transform, opacity et filter ; les états
   initiaux sont posés en JS, jamais en CSS, pour que la page reste lisible
   si le script échoue ; et tout se réduit à l'état final si la personne a
   demandé moins de mouvement.
   ========================================================================= */
(function () {
  'use strict';

  /* Le <head> a masqué l'en-tête le temps qu'on pose les états de départ.
     Tout chemin qui sort d'ici doit le redonner, sinon il reste vide. */
  function decouvrir() { document.documentElement.classList.remove('motion-pending'); }

  var A = window.anime;
  if (!A) { decouvrir(); return; }   // sans la bibliothèque : page statique, mais lisible

  var animate        = A.animate,
      createTimeline = A.createTimeline,
      createScope    = A.createScope,
      stagger        = A.stagger,
      utils          = A.utils;

  var $  = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* Un seul drapeau, lu une fois. motion-force vient de ?motion=on et passe
     outre le réglage système, le temps de revoir l'animation. */
  var force = document.documentElement.classList.contains('motion-force');
  var calm  = !force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* La courbe signature du site (DESIGN-SYSTEM §5). Passée en FONCTION et
     non en chaîne : anime.js v4 a retiré la syntaxe `ease: 'cubicBezier(...)'`
     du cœur. Elle n'échouait pas bruyamment, elle retombait simplement sur
     l'easing par défaut en laissant un avertissement en console — donc la
     courbe n'était pas appliquée du tout. */
  var OUT = A.cubicBezier(.16, 1, .3, 1);

  /* ===================================================== 1. l'entrée ==== */

  function entree() {
    var nav  = $('[data-nav]');
    var tete = $$('[data-reveal]');

    utils.set(nav,  { opacity: 0, y: -24 });
    utils.set(tete, { opacity: 0, y: 14 });

    // Les états de départ sont posés : plus rien ne peut sauter, on affiche.
    decouvrir();

    if (calm) {
      /* Comme sur l'accueil : remettre l'opacité ne suffit pas, il faut
         défaire les décalages, sinon la nav reste 24 px trop haut et
         l'en-tête 14 px trop bas, en permanence. */
      utils.set(nav,  { opacity: 1, y: 0 });
      utils.set(tete, { opacity: 1, y: 0 });
      return;
    }

    createTimeline({ defaults: { ease: OUT } })
      .add(nav,  { opacity: 1, y: 0, duration: 700 }, 0)
      .add(tete, { opacity: 1, y: 0, duration: 650, delay: stagger(90) }, 160);
  }

  /* ============================== 2. les révélations ==================== */

  /* LES MÊMES RANGÉES QUE L'ACCUEIL, donc la même révélation, et pour la
     même raison : cette page montrait six `.mod` avec leur propre mise en
     page, elle montre maintenant le bloc `.mrows` repris de l'accueil.
     Les sélecteurs suivent — `data-reveal-text` pour le texte,
     `data-mod-visual` pour la scène — et aucun ne nomme plus `.mod__`.

     L'appel à l'action de fin porte `data-mod` lui aussi : il n'a pas de
     scène, seulement du texte, et le code n'a pas à le distinguer. */
  function reveler() {
    var secs = $$('[data-mod]');
    if (!secs.length) return;

    /* Sans mouvement : rien n'est masqué, il n'y a donc rien à révéler.
       On sort AVANT de masquer quoi que ce soit — jamais après, sinon la
       page resterait vide sous l'en-tête. */
    if (calm) return;

    var faites = secs.map(function (sec, i) {
      /* Une section peut en contenir d'autres — la grille porte un
         `data-mod`, et chacune de ses six rangées aussi. Chacune ne prend
         que ce qui est à elle : sinon la grille ferait apparaître les six
         rangées d'un coup, au lieu de les laisser venir une à une. */
      function aMoi(el) { return el.closest('[data-mod]') === sec; }
      var texte  = $$('[data-reveal-text]', sec).filter(aMoi);
      var visuel = $$('[data-mod-visual]', sec).filter(aMoi)[0];

      /* Une rangée de module : sa scène arrive depuis son propre bord —
         la gauche, ou la droite quand la rangée est inversée — et de
         plus loin qu'une maquette de section, pour qu'on la voie venir. */
      var rangee = sec.classList.contains('mrow');
      var dx = rangee ? (sec.classList.contains('mrow--inv') ? 64 : -64) : (i % 2 ? -28 : 28);

      utils.set(texte, { opacity: 0, y: rangee ? 26 : 18 });
      if (visuel) utils.set(visuel, { opacity: 0, x: dx, scale: rangee ? .92 : .97 });

      var tl = createTimeline({ defaults: { ease: OUT }, autoplay: false });
      tl.add(texte, { opacity: 1, y: 0, duration: 700, delay: stagger(110) }, rangee ? 140 : 0);
      if (visuel) tl.add(visuel, { opacity: 1, x: 0, scale: 1, duration: 900 }, rangee ? 0 : 160);
      return tl;
    });

    /* Pourquoi un écouteur de défilement et pas un IntersectionObserver.

       L'observateur ne prévient que lorsque l'état d'intersection CHANGE.
       Un saut d'une seule image — ancre `#duel`, position restaurée au
       rechargement, molette franche, « fin de page » au clavier — fait
       passer une rangée de « sous l'écran » à « au-dessus de l'écran »
       sans jamais la rendre visible entre les deux. Aucun changement
       d'état, donc aucun appel, donc une rangée invisible pour toujours.
       C'est exactement ce qui arrivait sur l'accueil, et les ancres des
       modules rendent le cas bien plus fréquent ici.

       Un contrôle au défilement n'a pas ce trou : il regarde où sont les
       choses, pas comment elles y sont arrivées. Il est passif, il ne lit
       que des rectangles, et il se retire tout seul quand tout a joué. */
    var restant = secs.slice();

    function controler() {
      var limite = window.innerHeight * 0.85;

      for (var i = restant.length - 1; i >= 0; i--) {
        if (restant[i].getBoundingClientRect().top >= limite) continue;
        faites[secs.indexOf(restant[i])].play();
        restant.splice(i, 1);
      }

      if (!restant.length) {
        window.removeEventListener('scroll', planifier);
        window.removeEventListener('resize', planifier);
      }
    }

    /* Une lecture par image au plus : le défilement en émet bien
       davantage, et mesurer huit rectangles à chaque événement coûterait
       un calcul de mise en page à chaque fois. */
    var prevu = false;
    function planifier() {
      if (prevu) return;
      prevu = true;
      requestAnimationFrame(function () { prevu = false; controler(); });
    }

    window.addEventListener('scroll', planifier, { passive: true });
    window.addEventListener('resize', planifier);
    controler();          // ce qui est déjà à l'écran au chargement
  }

  /* Le parallaxe des maquettes est parti avec les `.mod` : les rangées
     lévitent en CSS (`.mrow__flot`, @keyframes mrow-leviter), et poser un
     second transform sur la même scène, c'est le dernier écrit qui gagne.
     Voir le commentaire des trois calques dans index.html. */

  /* ============================================== orchestration ========= */

  var scope = createScope({ root: document.body }).add(function () {
    var started = false;

    function start() {
      if (started) return;
      started = true;
      entree();
      reveler();
      /* Le titre peut se taper : les polices sont là, donc la hauteur
         qu'il réserve est mesurée sur la bonne fonte. Même signal que
         `cyq:titre-libre` sur l'accueil, sous un autre nom — frappe.js
         ne connaît que l'attribut `data-frappe-depart`. */
      document.dispatchEvent(new CustomEvent('cyq:modules-prets'));
    }

    /* Après les polices : les puces et les titres sont mesurés une fois
       la bonne fonte en place, sinon les positions bougent sous
       l'animation. Le minuteur est le filet si fonts.ready ne résout pas. */
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () { requestAnimationFrame(start); });
      setTimeout(start, 1500);
    } else {
      requestAnimationFrame(start);
    }
  });

  window.CYQ_MODULES = scope;
})();
