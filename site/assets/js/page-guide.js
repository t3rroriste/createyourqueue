/* =========================================================================
   Guide — motion.
   Beaucoup plus court que l'accueil : une page de lecture n'a pas besoin
   d'une chorégraphie, juste d'une arrivée propre et d'un repère de lecture.

     entree()    — nav et en-tête, en cascade
     reveler()   — chaque partie à son entrée dans l'écran, une seule fois
     suivre()    — la partie en cours, marquée dans le sommaire
   ========================================================================= */
(function () {
  'use strict';

  function decouvrir() { document.documentElement.classList.remove('motion-pending'); }

  var A = window.anime;
  if (!A) { decouvrir(); return; }

  var animate        = A.animate,
      createTimeline = A.createTimeline,
      stagger        = A.stagger,
      utils          = A.utils;

  var $  = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* Même règle que sur l'accueil : motion-force vient de ?motion=on et passe
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

    decouvrir();

    if (calm) {
      utils.set(nav,  { opacity: 1, y: 0 });
      utils.set(tete, { opacity: 1, y: 0 });
      return;
    }

    createTimeline({ defaults: { ease: OUT } })
      .add(nav,  { opacity: 1, y: 0, duration: 700 }, 0)
      .add(tete, { opacity: 1, y: 0, duration: 650, delay: stagger(90) }, 160);
  }

  /* ============================== 2. les révélations ==================== */

  /* Une seule fois, sans rejeu au défilement inverse : on cesse d'observer
     dès que la partie est passée. Le seuil est bas parce qu'une partie fait
     souvent plus d'un écran de haut — attendre la moitié ne se déclencherait
     jamais sur les plus longues. */
  function reveler() {
    var parts = $$('[data-part]');
    if (!parts.length) return;

    if (calm || !window.IntersectionObserver) {
      utils.set(parts, { opacity: 1, y: 0 });
      return;
    }

    /* On ne cache que ce qui est hors de l'écran. Masquer une partie déjà
       visible la ferait clignoter : affichée au rendu, cachée par le script,
       puis réapparue. Celles du haut restent donc simplement là. */
    var aVenir = parts.filter(function (p) {
      return p.getBoundingClientRect().top > window.innerHeight * 0.9;
    });
    if (!aVenir.length) return;
    utils.set(aVenir, { opacity: 0, y: 20 });

    var obs = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        if (!e.isIntersecting) return;
        animate(e.target, { opacity: 1, y: 0, duration: 700, ease: OUT });
        obs.unobserve(e.target);
      });
    }, { rootMargin: '0px 0px -12% 0px', threshold: 0.06 });

    aVenir.forEach(function (p) { obs.observe(p); });
  }

  /* =========================== 3. le repère de lecture ================== */

  /* Le sommaire marque la partie qu'on est en train de lire. Le décalage en
     haut correspond à la pilule de navigation, qui est fixe : sans lui, la
     partie serait déclarée courante alors qu'elle est encore cachée. */
  function suivre() {
    var liens = $$('.toc__list a');
    if (!liens.length || !window.IntersectionObserver) return;

    var parId = {};
    liens.forEach(function (a) { parId[a.getAttribute('href').slice(1)] = a; });

    var vues = [];
    var obs = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        var id = e.target.id;
        var i  = vues.indexOf(id);
        if (e.isIntersecting && i === -1) vues.push(id);
        else if (!e.isIntersecting && i !== -1) vues.splice(i, 1);
      });
      liens.forEach(function (a) { a.removeAttribute('aria-current'); });
      // la première visible dans l'ordre du document, pas la dernière signalée
      var ordre = $$('[data-part]').map(function (p) { return p.id; });
      var actif = ordre.filter(function (id) { return vues.indexOf(id) !== -1; })[0];
      if (actif && parId[actif]) parId[actif].setAttribute('aria-current', 'true');
    }, { rootMargin: '-120px 0px -55% 0px' });

    $$('[data-part]').forEach(function (p) { obs.observe(p); });
  }

  /* ============================================== orchestration ========= */

  function demarrer() {
    entree();
    reveler();
    suivre();
  }

  if (document.fonts && document.fonts.ready) {
    var lance = false;
    var une = function () { if (!lance) { lance = true; demarrer(); } };
    document.fonts.ready.then(function () { requestAnimationFrame(une); });
    setTimeout(une, 1500);              // filet si fonts.ready ne se résout pas
  } else {
    requestAnimationFrame(demarrer);
  }
})();
