/* =========================================================================
   Accueil — motion.
   anime.js v4, chargé en UMD (le site n'a pas d'étape de build) : les
   exports nommés sont donc lus sur le global `anime`.

   Une seule séquence depuis que la pile de sections a été retirée :
     entree()   — la chorégraphie d'ouverture, en UNE timeline

   Règles tenues : on n'anime que transform, opacity et filter ; les états
   initiaux sont posés en JS, jamais en CSS, pour que la page reste lisible
   si le script échoue ; et tout se réduit à une opacité si la personne a
   demandé moins de mouvement.
   ========================================================================= */
(function () {
  'use strict';

  /* Le <head> a masqué le héros le temps du découpage du titre. Tout chemin
     qui sort d'ici doit le redonner, sinon la page reste vide. */
  function decouvrir() { document.documentElement.classList.remove('motion-pending'); }

  var A = window.anime;
  if (!A) { decouvrir(); return; }   // sans la bibliothèque : page statique, mais lisible

  var createTimeline = A.createTimeline,
      createScope    = A.createScope,
      stagger        = A.stagger,
      utils          = A.utils;

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) {
    return Array.prototype.slice.call((r || document).querySelectorAll(s));
  };

  /* Un seul drapeau, lu une fois. Pas de duplication de code.
     La classe motion-force vient de ?motion=on, posée dans le <head> : elle
     passe outre le réglage système, le temps de revoir l'ouverture. Sans
     elle, une machine dont les animations sont coupées ne joue jamais rien
     et le site paraît cassé alors qu'il obéit. */
  var force = document.documentElement.classList.contains('motion-force');
  var calm  = !force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* La courbe signature du site (DESIGN-SYSTEM §5). Passée en FONCTION et
     non en chaîne : anime.js v4 a retiré la syntaxe `ease: 'cubicBezier(...)'`
     du cœur. Elle n'échouait pas bruyamment, elle retombait simplement sur
     l'easing par défaut en laissant un avertissement en console — donc la
     courbe n'était pas appliquée du tout. */
  var OUT = A.cubicBezier(.16, 1, .3, 1);

  /* ===================================================== 1. l'entrée ==== */

  function entree(splitter) {
    var shell  = $('.shell');
    var nav    = $('[data-nav]');
    var matter = $('[data-hero="matter"]');
    var mots   = splitter && splitter.words ? splitter.words : [];

    /* L'ordre de la cascade est celui-ci, et il est tenu par les temps de
       départ plus bas : titre, accroche, bouton, mention. */
    var lead  = $('[data-hero="lead"]'),
        cta   = $('[data-hero="cta"]'),
        note  = $('[data-hero="note"]'),
        setup = $('[data-needs-client-id]');   // visible seulement si CLIENT_ID est vide
    var around = [lead, cta, note, setup].filter(Boolean);

    utils.set(nav,    { opacity: 0, y: -24 });
    utils.set(around, { opacity: 0, y: 14 });
    utils.set(matter, { opacity: 0, scale: 1.12, y: 40, filter: 'blur(12px)' });
    if (mots.length) utils.set(mots, { y: '110%' });

    // Les états de départ sont posés : plus rien ne peut sauter, on affiche.
    decouvrir();

    if (calm) {
      utils.set(matter, { scale: 1, y: 0, filter: 'blur(6px)' });
      /* Les décalages posés juste au-dessus doivent être défaits, pas
         seulement l'opacité : sans ça la nav reste 24 px trop haut et le
         reste du héros 14 px trop bas, en permanence. */
      utils.set(nav,    { y: 0 });
      utils.set(around, { y: 0 });
      if (mots.length) utils.set(mots, { y: '0%' });
      utils.set($('[data-hero-in]'), { scale: 1, y: 0, opacity: 1, filter: 'none' });
      var all = [nav, matter].concat(around).concat(mots).filter(Boolean);
      utils.set(all, { opacity: 1 });
      rendreLaMainAuCss();
      return null;
    }

    /* Une fois l'ouverture terminée, on efface les transformations que la
       bibliothèque a écrites en style inline. Sans ça, le bouton du héros
       garde un `transform` inline, et un style inline l'emporte sur une
       règle `:hover` : il ne pourrait plus se soulever au survol.
       L'opacité, elle, peut rester — rien ne la dispute. */
    function rendreLaMainAuCss() {
      around.forEach(function (el) { el.style.transform = ''; });
    }

    var tl = createTimeline({ defaults: { ease: OUT }, onComplete: rendreLaMainAuCss });

    // t=0 — la coque s'installe dans l'écran
    tl.add(shell, { scale: [.96, 1], borderRadius: ['64px', '36px'], duration: 900 }, 0)
      // t=120 — la pilule de navigation descend
      .add(nav,   { opacity: 1, y: 0, duration: 700 }, 120);

    /* t=380 — le titre monte, mot par mot, chacun derrière son cache.
       Le pas descend de 80 à 45 ms : il y a onze mots là où il y avait
       quatre lignes, et garder 80 ms étalait la montée sur près d'une
       seconde de plus que le reste de la cascade. */
    if (mots.length) {
      tl.add(mots, { y: ['110%', '0%'], duration: 750, delay: stagger(45) }, 380);
    }

    // t=300 — le halo, sous le texte
    tl.add(matter, { opacity: 1, scale: 1, y: 0,
                     filter: ['blur(12px)', 'blur(6px)'], duration: 1300 }, 300);

    /* La suite de la cascade. Des départs séparés plutôt qu'un stagger :
       le titre prend environ 500 ms de plus que les autres à cause du décalage
       entre ses mots, donc l'accroche doit l'attendre, ce qu'un stagger
       régulier ne sait pas faire. */
    if (lead) tl.add(lead, { opacity: 1, y: 0, duration: 550 }, 620);
    tl.add(cta, { opacity: 1, y: 0, duration: 550 }, 740);
    if (note) tl.add(note, { opacity: 1, y: 0, duration: 500 }, 840);

    /* La cascade se termine ici. Le ressort outBack qui fermait la marche
       est parti avec la carte d'accroche : c'était son seul emploi de toute
       la page, et le réintroduire ailleurs contredirait la règle d'un seul
       ressort par écran. */
    if (setup) tl.add(setup, { opacity: 1, y: 0, duration: 500 }, 940);

    return tl;
  }

  /* ============================================== orchestration ========= */

  var scope = createScope({ root: document.body }).add(function () {
    var splitter = null;
    var started = false;

    function start() {
      if (started) return;
      started = true;

      // Le découpage doit se faire APRÈS les polices : sinon les mots sont
      // mesurés sur la police de repli, puis se recomposent.
      var title = $('[data-hero="title"]');
      if (title && A.splitText) {
        /* Mot par mot. `lines: false` n'est pas décoratif : un découpage en
           lignes fige ses frontières dans des wrappers et les recalcule à
           chaque redimensionnement, ce qui remplace les éléments de mots
           sous l'animation en cours. Sans lui, les mots restent des
           inline-block que le navigateur recompose tout seul. */
        try { splitter = A.splitText(title, { lines: false, words: { wrap: 'clip' } }); }
        catch (e) { splitter = null; }
      }

      /* splitText découpe le DOM à la frame suivante, pas dans l'appel :
         juste après, splitter.words est encore vide. Lu trop tôt, le titre
         n'entre jamais dans la timeline et il apparaît d'un bloc avec le
         reste. On laisse donc passer quelques frames, et on démarre sans lui
         si le découpage n'aboutit pas. */
      var essais = 0;
      (function attendreLignes() {
        var pret = splitter && splitter.words && splitter.words.length;
        if (!pret && splitter && ++essais < 12) {
          requestAnimationFrame(attendreLignes);
          return;
        }
        entree(splitter);
      })();
    }

    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () { requestAnimationFrame(start); });
      setTimeout(start, 1500);            // filet si fonts.ready ne se résout pas
    } else {
      requestAnimationFrame(start);
    }

    return function () { if (splitter && splitter.revert) splitter.revert(); };
  });

  /* ================= les modules, révélés au défilement ================= */

  /* La page Modules est reprise entière dans l'accueil. Sa révélation l'est
     aussi : mêmes sélecteurs, même découpage que page-modules.js, pour que
     les deux pages se comportent pareil. On ne charge PAS page-modules.js
     ici — il rejouerait l'entrée de la nav, que page-home.js anime déjà, et
     les deux se marcheraient dessus.

     À part du scope du héros, et volontairement : l'entrée du héros attend
     le découpage du titre et le chargement des polices, ce qui peut prendre
     une seconde et demie. Les modules sont hors de l'écran au chargement —
     les faire dépendre de cette attente les ferait apparaître en retard, ou
     pas du tout si le découpage échoue. */
  (function modules() {
    var secs  = $$('[data-mod]');
    var tete  = $$('.mhead [data-reveal]');
    var mhead = $('.mhead');
    if (!secs.length) return;

    /* Sans mouvement : rien n'est masqué, il n'y a donc rien à révéler.
       On sort AVANT de masquer quoi que ce soit — jamais après, sinon la
       page resterait vide sous le héros. */
    if (calm) return;

    utils.set(tete, { opacity: 0, y: 14 });

    var tlTete = createTimeline({ defaults: { ease: OUT }, autoplay: false });
    tlTete.add(tete, { opacity: 1, y: 0, duration: 650, delay: stagger(90) }, 0);

    /* Le sens d'arrivée de la maquette suit la colonne qu'elle occupe :
       elle entre depuis son propre bord, pas depuis un côté arbitraire. */
    var faites = secs.map(function (sec, i) {
      var texte = [$('.mod__title', sec), $('.mod__body', sec),
                   $('.mcta__title', sec)].filter(Boolean);
      var visuel = $('[data-mod-visual]', sec);

      utils.set(texte, { opacity: 0, y: 18 });
      if (visuel) utils.set(visuel, { opacity: 0, x: (i % 2 ? -28 : 28), scale: .97 });

      var tl = createTimeline({ defaults: { ease: OUT }, autoplay: false });
      tl.add(texte, { opacity: 1, y: 0, duration: 700, delay: stagger(110) }, 0);
      if (visuel) tl.add(visuel, { opacity: 1, x: 0, scale: 1, duration: 900 }, 160);
      return tl;
    });

    /* Pourquoi un écouteur de défilement et pas un IntersectionObserver.

       L'observateur ne prévient que lorsque l'état d'intersection CHANGE.
       Un saut d'une seule image — ancre, position restaurée au
       rechargement, molette franche, « fin de page » au clavier — fait
       passer une section de « sous l'écran » à « au-dessus de l'écran »
       sans jamais la rendre visible entre les deux. Aucun changement
       d'état, donc aucun appel, donc une section qui reste invisible pour
       toujours. C'est exactement ce qui arrivait ici.

       Un contrôle au défilement n'a pas ce trou : il regarde où sont les
       choses, pas comment elles y sont arrivées. Il est passif, il ne lit
       que des rectangles, et il se retire tout seul quand tout a joué. */
    var restant = secs.slice();
    var tetePrete = !tete.length;

    function controler() {
      var limite = window.innerHeight * 0.85;

      if (!tetePrete && mhead && mhead.getBoundingClientRect().top < limite) {
        tetePrete = true;
        tlTete.play();
      }

      for (var i = restant.length - 1; i >= 0; i--) {
        if (restant[i].getBoundingClientRect().top >= limite) continue;
        faites[secs.indexOf(restant[i])].play();
        restant.splice(i, 1);
      }

      if (!restant.length && tetePrete) {
        window.removeEventListener('scroll', planifier);
        window.removeEventListener('resize', planifier);
      }
    }

    /* Une lecture par image au plus : le défilement en émet bien davantage,
       et mesurer sept rectangles à chaque événement coûterait un calcul de
       mise en page à chaque fois. */
    var prevu = false;
    function planifier() {
      if (prevu) return;
      prevu = true;
      requestAnimationFrame(function () { prevu = false; controler(); });
    }

    window.addEventListener('scroll', planifier, { passive: true });
    window.addEventListener('resize', planifier);
    controler();          // ce qui est déjà à l'écran au chargement
  })();

  window.CYQ_HOME = scope;
})();
