/* =========================================================================
   Modules — motion.
   anime.js v4, chargé en UMD (le site n'a pas d'étape de build) : les
   exports nommés sont donc lus sur le global `anime`.

     entree()   — l'en-tête, en UNE timeline
     reveler()  — chaque module à son entrée dans l'écran, une seule fois
     flotter()  — un parallaxe borné sur les maquettes

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

  /* Une timeline par module : le titre, puis le paragraphe, puis la
     maquette qui arrive de côté. Des départs relatifs dans une seule
     timeline plutôt que trois animate() à délais calculés — si une durée
     change, les suivantes suivent.
     Le stagger porte sur deux éléments au lieu de sept depuis que les
     puces sont parties : le pas monte à 110 ms, sinon titre et paragraphe
     arrivent quasiment ensemble et la cascade ne se lit plus. */
  function timelineDuModule(sec) {
    var texte  = [$('.mod__title', sec), $('.mod__body', sec)].filter(Boolean);
    var visuel = $('[data-mod-visual]', sec);

    var tl = createTimeline({ defaults: { ease: OUT }, autoplay: false });
    tl.add(texte, { opacity: 1, y: 0, duration: 700, delay: stagger(110) }, 0);
    if (visuel) {
      tl.add(visuel, { opacity: 1, x: 0, scale: 1, duration: 900 }, 160);
    }
    return tl;
  }

  function reveler() {
    var secs = $$('[data-mod]');
    if (!secs.length) return [];

    if (calm || !window.IntersectionObserver) {
      secs.forEach(function (sec) {
        utils.set([$('.mod__title', sec), $('.mod__body', sec)].filter(Boolean),
                  { opacity: 1, y: 0 });
        var v = $('[data-mod-visual]', sec);
        if (v) utils.set(v, { opacity: 1, x: 0, scale: 1 });
      });
      return [];
    }

    /* Le sens d'arrivée de la maquette suit la colonne qu'elle occupe :
       elle entre depuis son propre bord, pas depuis un côté arbitraire. */
    var faites = [];
    secs.forEach(function (sec, i) {
      utils.set([$('.mod__title', sec), $('.mod__body', sec)].filter(Boolean),
                { opacity: 0, y: 18 });
      var v = $('[data-mod-visual]', sec);
      if (v) utils.set(v, { opacity: 0, x: (i % 2 ? -28 : 28), scale: .97 });
      faites.push(timelineDuModule(sec));
    });

    var obs = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        if (!e.isIntersecting) return;
        var i = secs.indexOf(e.target);
        if (i !== -1) faites[i].play();
        obs.unobserve(e.target);        // une seule fois, pas de rejeu au retour
      });
    }, { threshold: 0.25 });

    secs.forEach(function (sec) { obs.observe(sec); });

    /* Un module déjà à l'écran au chargement ne déclenchera jamais
       l'observateur s'il occupe plus que le seuil : on le joue à la main. */
    secs.forEach(function (sec, i) {
      var r = sec.getBoundingClientRect();
      if (r.top < window.innerHeight * 0.75 && r.bottom > 0) {
        faites[i].play();
        obs.unobserve(sec);
      }
    });

    return faites;
  }

  /* ============================== 3. le parallaxe ======================= */

  /* Borné à 14 px, et coupé sous 768 px : sur un téléphone la maquette est
     déjà pleine largeur, la faire flotter ne ferait que du bruit. */
  function flotter() {
    if (calm || window.innerWidth < 768) return null;
    var visuels = $$('[data-mod-visual]');
    if (!visuels.length) return null;

    var tick = false;
    function placer() {
      var h = window.innerHeight;
      visuels.forEach(function (v) {
        var r = v.getBoundingClientRect();
        if (r.bottom < 0 || r.top > h) return;
        // -1 au bas de l'écran, +1 en haut : le visuel monte un peu plus
        // vite que la page, jamais de plus de 14 px.
        var p = ((h - r.top) / (h + r.height)) * 2 - 1;
        v.style.setProperty('--flot', (Math.max(-1, Math.min(1, p)) * -14).toFixed(2) + 'px');
      });
      tick = false;
    }
    function auDefilement() {
      if (tick) return;
      tick = true;
      requestAnimationFrame(placer);
    }
    addEventListener('scroll', auDefilement, { passive: true });
    addEventListener('resize', auDefilement, { passive: true });
    placer();
    return auDefilement;
  }

  /* ============================================== orchestration ========= */

  var scope = createScope({ root: document.body }).add(function () {
    var started = false;

    function start() {
      if (started) return;
      started = true;
      entree();
      reveler();
      flotter();
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
