/* =========================================================================
   Accueil — motion.
   anime.js v4, chargé en UMD (le site n'a pas d'étape de build) : les
   exports nommés sont donc lus sur le global `anime`.

   Deux séquences, et elles ne se mélangent pas :
     entree()           — la chorégraphie d'ouverture, en UNE timeline
     titreQuiSeTape()   — la boucle du titre, dans sa PROPRE IIFE, hors de
                          la portée d'anime.js : elle ne lui doit rien et
                          doit jouer même quand la bibliothèque manque.

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

  function entree() {
    var shell  = $('.shell');
    var nav    = $('[data-nav]');
    var matter = $('[data-hero="matter"]');
    var titre  = $('[data-hero="title"]');

    /* L'ordre de la cascade est celui-ci, et il est tenu par les temps de
       départ plus bas : titre, accroche, boutons, mention. */
    var lead  = $('[data-hero="lead"]'),
        cta   = $('[data-hero="cta"]'),
        cta2  = $('[data-hero="cta2"]'),       // la pilule fantôme, vers la démo
        note  = $('[data-hero="note"]'),
        setup = $('[data-needs-client-id]');   // visible seulement si CLIENT_ID est vide
    var around = [lead, cta, cta2, note, setup].filter(Boolean);

    /* La maquette d'embed, à part du halo et pour une raison précise : le
       halo est flouté pendant toute l'ouverture, et un flou de 12 px sur
       une carte couverte de texte la rend illisible une seconde et demie.
       Elle arrive donc en opacité, échelle et translation seules. */
    var embed = $('[data-hero="embed"]');

    utils.set(nav,    { opacity: 0, y: -24 });
    utils.set(around, { opacity: 0, y: 14 });
    utils.set(titre,  { opacity: 0, y: 14 });
    utils.set(matter, { opacity: 0, scale: 1.12, y: 40, filter: 'blur(12px)' });
    utils.set(embed,  { opacity: 0, scale: .97, y: 24 });

    // Les états de départ sont posés : plus rien ne peut sauter, on affiche.
    decouvrir();

    if (calm) {
      utils.set(matter, { scale: 1, y: 0, filter: 'blur(6px)' });
      /* Les décalages posés juste au-dessus doivent être défaits, pas
         seulement l'opacité : sans ça la nav reste 24 px trop haut et le
         reste du héros 14 px trop bas, en permanence. */
      utils.set(nav,    { y: 0 });
      utils.set(around, { y: 0 });
      utils.set(titre,  { y: 0 });
      utils.set(embed,  { scale: 1, y: 0 });
      utils.set($('[data-hero-in]'), { scale: 1, y: 0, opacity: 1, filter: 'none' });
      var all = [nav, matter, embed, titre].concat(around).filter(Boolean);
      utils.set(all, { opacity: 1 });
      rendreLaMainAuCss();
      titreLibre();
      return null;
    }

    /* Une fois l'ouverture terminée, on efface les transformations que la
       bibliothèque a écrites en style inline. Sans ça, le bouton du héros
       garde un `transform` inline, et un style inline l'emporte sur une
       règle `:hover` : il ne pourrait plus se soulever au survol.
       L'opacité, elle, peut rester — rien ne la dispute. */
    function rendreLaMainAuCss() {
      around.forEach(function (el) { el.style.transform = ''; });
      if (titre) titre.style.transform = '';
      /* La carte d'embed aussi : la rotation de trois degrés est sur son
         ENFANT, donc rien ne se dispute ici, mais un `transform` inline
         resté sur un élément qui n'en a plus besoin finit toujours par
         gêner la règle suivante qu'on écrira. */
      if (embed) embed.style.transform = '';
    }

    /* La boucle de frappe attend ce signal, et rien d'autre. Elle ne peut
       pas démarrer pendant la cascade : on verrait le titre se taper
       pendant qu'il monte et change d'opacité, deux mouvements sur le même
       élément. Elle a son propre filet si ce signal n'arrive jamais. */
    function titreLibre() {
      document.dispatchEvent(new CustomEvent('cyq:titre-libre'));
    }

    var tl = createTimeline({ defaults: { ease: OUT }, onComplete: function () {
      rendreLaMainAuCss();
      titreLibre();
    } });

    // t=0 — la coque s'installe dans l'écran
    tl.add(shell, { scale: [.96, 1], borderRadius: ['64px', '36px'], duration: 900 }, 0)
      // t=120 — la pilule de navigation descend
      .add(nav,   { opacity: 1, y: 0, duration: 700 }, 120);

    /* t=380 — le titre arrive d'un bloc, et c'est un changement assumé.
       Il montait mot par mot derrière des caches, découpé par splitText :
       ce découpage n'est plus possible, puisque le texte du titre change
       maintenant à chaque caractère. Deux mécanismes se disputeraient le
       même DOM, et le second effacerait les wrappers du premier.
       La frappe EST devenue l'entrée du titre ; il ne reste ici qu'à le
       découvrir, à sa place dans la cascade. */
    if (titre) tl.add(titre, { opacity: 1, y: 0, duration: 650 }, 380);

    // t=300 — le halo, sous le texte
    tl.add(matter, { opacity: 1, scale: 1, y: 0,
                     filter: ['blur(12px)', 'blur(6px)'], duration: 1300 }, 300);

    /* t=520 — la carte, par-dessus le halo. Elle part après lui : le halo
       doit avoir commencé à monter pour que la carte paraisse se poser
       dessus, et non surgir d'un fond noir. */
    if (embed) tl.add(embed, { opacity: 1, scale: 1, y: 0, duration: 900 }, 520);

    /* La suite de la cascade. Des départs séparés plutôt qu'un stagger :
       chaque élément a sa propre durée, et l'accroche doit attendre que le
       titre soit posé avant de paraître — ce qu'un stagger régulier, qui
       ne connaît qu'un pas constant, ne sait pas faire. */
    if (lead) tl.add(lead, { opacity: 1, y: 0, duration: 550 }, 620);
    tl.add(cta, { opacity: 1, y: 0, duration: 550 }, 740);
    /* La seconde pilule suit la première de 60 ms : assez pour qu'on lise
       deux gestes et non un, trop peu pour qu'on attende. */
    if (cta2) tl.add(cta2, { opacity: 1, y: 0, duration: 550 }, 800);
    if (note) tl.add(note, { opacity: 1, y: 0, duration: 500 }, 880);

    /* La cascade se termine ici. Le ressort outBack qui fermait la marche
       est parti avec la carte d'accroche : c'était son seul emploi de toute
       la page, et le réintroduire ailleurs contredirait la règle d'un seul
       ressort par écran. */
    if (setup) tl.add(setup, { opacity: 1, y: 0, duration: 500 }, 940);

    return tl;
  }

  /* ============================================== orchestration ========= */

  var scope = createScope({ root: document.body }).add(function () {
    var started = false;

    function start() {
      if (started) return;
      started = true;
      entree();
    }

    /* On attend toujours les polices, même sans découpage à faire : le
       titre est mesuré par la boucle de frappe pour réserver sa hauteur, et
       une mesure prise sur la police de repli donnerait une réserve
       fausse, qu'on verrait sauter au premier échange de police. */
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () { requestAnimationFrame(start); });
      setTimeout(start, 1500);            // filet si fonts.ready ne se résout pas
    } else {
      requestAnimationFrame(start);
    }
  });

  /* ============== les sections, révélées au défilement ================== */

  /* Huit sections sous le héros : repères, trois étapes, démo, grille des
     modules, communauté, FAQ, appel final. Chacune porte `data-mod`, son
     texte porte `data-reveal-text`, et sa maquette `data-mod-visual`.

     L'en-tête `.mhead` que cette fonction animait est parti avec la reprise
     intégrale de la page Modules : il n'y a plus d'en-tête à part, chaque
     section a le sien, et un `$$('.mhead [data-reveal]')` qui ne trouve
     jamais rien est une timeline vide qu'on joue pour personne.

     À part du scope du héros, et volontairement : l'entrée du héros attend
     le chargement des polices, ce qui peut prendre une seconde et demie.
     Ces sections sont hors de l'écran au chargement — les faire dépendre de
     cette attente les ferait apparaître en retard, ou pas du tout si la
     mesure du titre échoue. */
  (function sections() {
    var secs = $$('[data-mod]');
    if (!secs.length) return;

    /* Sans mouvement : rien n'est masqué, il n'y a donc rien à révéler.
       On sort AVANT de masquer quoi que ce soit — jamais après, sinon la
       page resterait vide sous le héros. */
    if (calm) return;

    /* Le sens d'arrivée de la maquette suit la colonne qu'elle occupe :
       elle entre depuis son propre bord, pas depuis un côté arbitraire. */
    var faites = secs.map(function (sec, i) {
      /* Un seul attribut, et non trois classes. Les sections de l'accueil
         ne sont plus les six `.mod` de la page Modules : ce sont des
         repères, trois étapes, une démo, une grille, une FAQ, un appel
         final, et chacune nomme ses propres classes. `data-reveal-text`
         dit « ce texte arrive au défilement » sans rien savoir de la
         section qui le porte — une classe de plus à ajouter ici à chaque
         section neuve, c'est la ligne qu'on oublie. */
      /* Une section peut en contenir d'autres — les rangées des modules
         portent chacune leur `data-mod`. Chacune ne prend que ce qui est
         à elle : sinon l'en-tête des modules ferait apparaître les six
         rangées d'un coup, au lieu de les laisser venir une à une. */
      function aMoi(el) { return el.closest('[data-mod]') === sec; }
      var texte = $$('[data-reveal-text]', sec).filter(aMoi);
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

    /* Une lecture par image au plus : le défilement en émet bien davantage,
       et mesurer huit rectangles à chaque événement coûterait un calcul de
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


/* =========================================================================
   LE TITRE QUI SE TAPE, S'EFFACE, ET RECOMMENCE
   =========================================================================
   Dans sa PROPRE IIFE, et c'est la seule chose qui ne se négocie pas ici :
   celle du dessus sort à sa deuxième ligne quand `window.anime` est absent
   (`if (!A) { decouvrir(); return; }`). Une boucle écrite à l'intérieur ne
   jouerait donc jamais sur un navigateur où la bibliothèque n'a pas chargé
   — exactement le cas où l'on tient le plus à ce que la page vive.

   Elle ne doit rien à anime.js : un setTimeout récursif, et rien d'autre.
   ========================================================================= */
(function titreQuiSeTape() {
  'use strict';

  var h1 = document.querySelector('[data-hero="title"]');
  if (!h1) return;

  /* ----------------------------------------------------- les cadences ----
     Les délais sont ici, en haut, parce que ce sont eux qui donnent le ton.

     FRAPPE est une moyenne, pas une cadence : chaque caractère tire son
     propre délai entre FRAPPE et FRAPPE+ALEA. Un rythme parfaitement
     régulier fait « terminal de film », et c'est précisément ce qu'on ne
     veut pas d'un titre d'accueil. Quarante-six millisecondes donnent
     environ vingt caractères par seconde : assez vif pour qu'une phrase de
     soixante signes s'écrive en trois secondes, assez lent pour qu'on la
     lise en même temps qu'elle s'écrit.

     EFFACE est deux fois plus rapide : on ne relit pas une phrase qui
     disparaît, et l'y faire traîner double l'attente avant le tour suivant.

     TENUE est le temps où la phrase reste entière. Deux secondes et demie,
     c'est le temps de la lire sans la relire. VIDE est la respiration à
     zéro caractère : sans elle, la frappe repart dans le même mouvement
     que l'effacement et on ne voit pas la boucle recommencer.             */
  var FRAPPE = 46;
  var ALEA   = 38;
  var EFFACE = 24;
  var TENUE  = 2500;
  var VIDE   = 540;

  /* Même lecture que page-home.js, et non une valeur partagée : les deux
     IIFE sont étanches, et ?motion=on doit forcer la boucle ici aussi. */
  var force = document.documentElement.classList.contains('motion-force');
  var calme = !force && window.matchMedia &&
              window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var vu = null;           // la partie animée, la seule qui change
  var sr = null;           // le texte réel, figé, pour les lecteurs d'écran
  var texte = '';
  var minuteur = null;
  var demarre = false;

  function texteCourant() {
    /* La clé plutôt que le DOM : applyI18n vient peut-être d'écrire dedans,
       mais c'est le dictionnaire qui fait foi, et lui seul sait la langue
       choisie. Le contenu de la balise sert de repli quand app.js n'a pas
       (encore) tourné. */
    if (window.CYQ && window.CYQ.t) {
      var v = window.CYQ.t('h.title');
      if (v && v !== 'h.title') return v;
    }
    return (h1.textContent || '').trim();
  }

  /* Le balisage de la frappe. Deux enfants, et le partage est net :

       <span class="sr-only">        le texte réel, entier, UNE fois. C'est
                                     lui que lit un lecteur d'écran.
       <span class="hero__type">     la partie qui change, aria-hidden.

     Pas d'aria-live, jamais : la frappe serait annoncée lettre par lettre,
     indéfiniment, et le titre deviendrait inécoutable. Et pas de caractère
     « | » injecté dans le DOM pour le curseur — il serait lu lui aussi.
     Le curseur est un pseudo-élément, animé en opacité seule.             */
  function batir() {
    h1.textContent = '';
    sr = document.createElement('span');
    sr.className = 'sr-only';
    sr.textContent = texte;
    vu = document.createElement('span');
    vu.className = 'hero__type';
    vu.setAttribute('aria-hidden', 'true');
    h1.appendChild(sr);
    h1.appendChild(vu);
  }

  /* La hauteur réservée, MESURÉE et non devinée. Sans elle, une phrase qui
     passe de trois lignes à une repousse le bouton d'invitation à chaque
     caractère — la page tremble pendant toute la boucle. On mesure le
     texte complet, on fige cette hauteur sur le h1, et le texte varie
     dedans.

     Une valeur en CSS ne pourrait pas faire ce travail : la hauteur dépend
     de la langue, de la largeur de l'écran et de la police effectivement
     chargée. Elle est donc reprise à chaque changement de langue et à
     chaque redimensionnement. */
  function mesurer() {
    var garde = vu.textContent;
    vu.textContent = texte;
    h1.style.minHeight = '';
    var haut = h1.offsetHeight;
    vu.textContent = garde;
    if (haut) h1.style.minHeight = haut + 'px';
  }

  function stopper() {
    if (minuteur) { clearTimeout(minuteur); minuteur = null; }
  }

  /* L'état final, figé : le titre entier, sans curseur, sans boucle. C'est
     ce que voit quelqu'un qui a demandé moins de mouvement, et c'est aussi
     le repli de tout ce qui pourrait mal tourner. */
  function poserEntier() {
    stopper();
    h1.classList.remove('is-typing');
    vu.textContent = texte;
  }

  function boucle() {
    var i = 0;
    var sens = 1;            // 1 : on écrit ; -1 : on efface

    function pas() {
      vu.textContent = texte.slice(0, i);

      if (sens === 1) {
        if (i >= texte.length) {
          sens = -1;
          minuteur = setTimeout(pas, TENUE);
          return;
        }
        i += 1;
        minuteur = setTimeout(pas, FRAPPE + Math.random() * ALEA);
        return;
      }

      /* On efface jusqu'à la CHAÎNE VIDE, pas jusqu'au premier mot : un
         titre réduit à « configure, » avec un curseur qui clignote
         derrière ressemble à un champ de saisie abandonné, pas à un
         titre. */
      if (i <= 0) {
        sens = 1;
        minuteur = setTimeout(pas, VIDE);
        return;
      }
      i -= 1;
      minuteur = setTimeout(pas, EFFACE);
    }

    stopper();
    h1.classList.add('is-typing');
    pas();
  }

  /* Un onglet caché n'affiche rien : une boucle qui continue d'y tourner
     réveille le processeur toutes les quarante millisecondes pour
     personne. On la coupe, et on la reprend du début au retour — reprendre
     au caractère exact où l'on s'était arrêté n'apporte rien que personne
     n'a vu partir. */
  document.addEventListener('visibilitychange', function () {
    if (!demarre || calme) return;
    if (document.hidden) stopper();
    else if (!minuteur) boucle();
  });

  function partir() {
    if (demarre) return;
    demarre = true;
    texte = texteCourant();
    if (!texte) return;
    batir();
    mesurer();
    if (calme) { poserEntier(); return; }
    boucle();
  }

  /* app.js émet `cyq:lang` APRÈS avoir réécrit le texte des [data-i18n] —
     donc après avoir effacé les deux enfants posés plus haut. On rebâtit
     tout : nouvelle phrase, nouvelle mesure, boucle repartie de zéro. Sans
     ça, le titre continuerait de taper l'ancienne langue dans un DOM qui
     n'existe plus. */
  document.addEventListener('cyq:lang', function () {
    if (!demarre) return;
    stopper();
    texte = texteCourant();
    if (!texte) return;
    batir();
    mesurer();
    if (calme) poserEntier();
    else boucle();
  });

  /* La hauteur réservée dépend de la largeur : à 375 px la même phrase
     prend cinq lignes au lieu de deux. On remesure, sans refaire la
     boucle — elle garde son avancement. */
  var redim = null;
  window.addEventListener('resize', function () {
    if (!demarre || !vu) return;
    clearTimeout(redim);
    redim = setTimeout(mesurer, 150);
  });

  /* Deux départs possibles, et le premier qui arrive gagne :

       cyq:titre-libre   la cascade d'ouverture a fini de poser le titre ;
       le filet          1 900 ms, juste après que le <head> ait découvert
                         le héros de lui-même (1 800 ms). C'est le chemin
                         pris quand anime.js manque, quand la timeline ne
                         se termine pas, ou quand on a demandé moins de
                         mouvement sans passer par page-home.js.           */
  document.addEventListener('cyq:titre-libre', partir);
  setTimeout(partir, 1900);
})();


/* =========================================================================
   LA FAQ
   =========================================================================
   Dans sa propre IIFE, pour la même raison que la boucle du titre : la
   fonction du dessus sort à sa deuxième ligne quand `window.anime` manque,
   et une FAQ qui ne s'ouvre plus parce qu'une bibliothèque d'animation n'a
   pas chargé serait un contenu perdu, pas un effet perdu.

   Elle ne doit donc rien à anime.js, et elle n'anime rien : ouvrir une
   réponse change la hauteur de la page, et animer une hauteur fait
   recalculer la mise en page à chaque image. Le site n'anime que
   `transform` et `opacity` — une réponse paraît, c'est tout.

   Chaque question peut rester ouverte avec les autres. Un accordéon qui
   referme la précédente est un geste de plus à comprendre, et il enlève à
   quelqu'un ce qu'il venait d'ouvrir pour comparer deux réponses.
   ========================================================================= */
(function faq() {
  'use strict';

  var qs = document.querySelectorAll('[data-faq]');
  if (!qs.length) return;

  Array.prototype.forEach.call(qs, function (q) {
    q.addEventListener('click', function () {
      var rep = document.getElementById(q.getAttribute('aria-controls'));
      if (!rep) return;
      var ouvert = q.getAttribute('aria-expanded') === 'true';
      q.setAttribute('aria-expanded', String(!ouvert));
      /* `hidden` et non une classe : c'est l'attribut que les lecteurs
         d'écran et la recherche du navigateur comprennent déjà, et
         home.css le force en `display: none` pour tout le site. */
      if (ouvert) rep.setAttribute('hidden', '');
      else rep.removeAttribute('hidden');
    });
  });
})();


/* =========================================================================
   LE LECTEUR DE LA PRÉSENTATION.

   Sa propre IIFE, hors de la portée d'anime.js : la fenêtre doit s'ouvrir
   et la vidéo se lire même si la bibliothèque n'a pas chargé. Rien ici ne
   lui doit quoi que ce soit — l'ouverture est une animation CSS.

   Trois choix qui ne sont pas évidents à la lecture :

   1. Les contrôles natifs sont coupés. Ceux du navigateur ne savent pas
      reculer de dix secondes, et ils ne sont pas de cette D.A.
   2. La barre n'est PAS rafraîchie par `timeupdate` : le navigateur ne
      l'émet que trois ou quatre fois par seconde, et la tête de lecture
      avance alors par paliers bien visibles. On tourne en rAF pendant la
      lecture seulement, et on coupe la boucle à la pause.
   3. Les deux couches de la barre sont mises à l'ÉCHELLE, jamais
      redimensionnées : une largeur animée soixante fois par seconde
      relance la mise en page de toute la rangée.
   ========================================================================= */
(function () {
  'use strict';

  var coque   = document.querySelector('[data-video-coque]');
  var ouvrirB = document.querySelector('[data-video-open]');
  var boite   = document.querySelector('[data-lecteur]');
  if (!coque || !ouvrirB || !boite) return;

  var q = function (s) { return boite.querySelector(s); };

  var video   = q('[data-lecteur-video]'),
      hoteFilm = q('[data-lecteur-film]'),
      fond    = q('[data-lecteur-fond]'),
      cadre   = q('[data-lecteur-boite]'),
      fermerB = q('[data-lecteur-close]'),
      erreur  = q('[data-lecteur-erreur]'),
      bRec    = q('[data-lecteur-back]'),
      bPlay   = q('[data-lecteur-play]'),
      bAv     = q('[data-lecteur-fwd]'),
      piste   = q('[data-lecteur-piste]'),
      tampon  = q('[data-lecteur-tampon]'),
      lu      = q('[data-lecteur-lu]'),
      tete    = q('[data-lecteur-tete]'),
      champT  = q('[data-lecteur-t]'),
      champD  = q('[data-lecteur-d]'),
      bMuet   = q('[data-lecteur-muet]'),
      vol     = q('[data-lecteur-vol]'),
      bCC     = q('[data-lecteur-cc]'),
      bPlein  = q('[data-lecteur-plein]');

  var affiche = document.querySelector('[data-video-affiche]'),
      champDuree = document.querySelector('[data-video-duree]');

  var icoPlay  = bPlay.querySelector('.lecteur__ico-play'),
      icoPause = bPlay.querySelector('.lecteur__ico-pause'),
      icoSon   = bMuet.querySelector('.lecteur__ico-son'),
      icoMuet  = bMuet.querySelector('.lecteur__ico-muet');

  var PAS = 10;          // les deux boutons de transport, en secondes
  var PAS_CLAVIER = 5;   // les flèches SUR la barre : plus fin que les boutons
  var MARGE_RAIL = 10;   // le retrait du rail dans sa zone de touche (home.css)

  var ouvert = false,     // la fenêtre est-elle affichée
      origine = null,     // qui l'a ouverte, pour lui rendre le focus
      boucle = 0,         // l'identifiant du rAF en cours
      saisie = false,     // un doigt ou une souris tient la tête de lecture
      amorce = false,     // le média a-t-il déjà été demandé une fois
      ccOn = false,       // les sous-titres sont-ils affichés
      position = 0,       // là où on en était en fermant
      railW = 0;          // la course de la tête, mesurée et non relue

  function t(k) { return (window.CYQ && window.CYQ.t) ? window.CYQ.t(k) : ''; }

  /* --------------------------- le temps lu ---------------------------- */

  function mmss(s) {
    if (!isFinite(s) || s < 0) s = 0;
    var m = Math.floor(s / 60), r = Math.floor(s % 60);
    return m + ':' + (r < 10 ? '0' : '') + r;
  }

  /* La durée affichée sous le bouton de lecture n'est pas écrite dans la
     page : elle est lue sur le fichier. Une durée en dur ment au premier
     remontage, et personne ne pense à la corriger. */
  function poserDuree() {
    if (!champDuree || !isFinite(video.duration) || video.duration <= 0) return;
    champDuree.textContent = mmss(video.duration);
    champDuree.hidden = false;
  }

  /* ---------------------------- le film -------------------------------
     L'image n'est pas une vidéo : film.js la dessine, et c'est l'<audio>
     qui donne l'heure. `dessiner` pose l'image de l'instant lu, à chaque
     image pendant la lecture et à chaque saut.

     currentTime n'avance que par paliers ; entre deux, on extrapole à
     l'horloge du navigateur, plafonné à 250 ms : si le son cale, l'image
     l'attend au lieu de partir seule devant. */
  var calme = window.matchMedia('(prefers-reduced-motion: reduce)').matches &&
              !/[?&]motion=on(&|$)/.test(location.search);
  var film = null, filmFormat = '', filmAffiche = null, langueSon = '';
  var dernierT = -1, dernierP = 0;

  // La langue du site, si le film l'a ; le français sinon
  function langueFilm() {
    var l = (window.CYQ && window.CYQ.lang) || 'fr';
    return (window.CYQ_VOIX && window.CYQ_VOIX[l]) ? l : 'fr';
  }
  // Sur un téléphone tenu droit, le film prend sa mise en page verticale
  function formatLecteur() {
    return window.matchMedia('(max-width: 640px) and (orientation: portrait)').matches ? 'p' : 'l';
  }
  function poserAffiche() {
    if (!affiche || !window.CYQ_FILM) return;
    if (filmAffiche) filmAffiche.detruire();
    filmAffiche = window.CYQ_FILM.creer(affiche, { langue: langueFilm(), format: 'l' });
    if (filmAffiche && champDuree) {
      champDuree.textContent = mmss(filmAffiche.total / 1000);
      champDuree.hidden = false;
    }
  }
  // Vrai si la source a changé, donc s'il faut recharger
  function poserSon() {
    var l = langueFilm();
    if (l === langueSon) return false;
    langueSon = l;
    video.innerHTML = '';
    var src = document.createElement('source');
    src.src = 'assets/video/voix/' + l + '.mp4';
    src.type = 'audio/mp4';
    src.addEventListener('error', montrerErreur);
    video.appendChild(src);
    return true;
  }
  function monterFilm() {
    if (!window.CYQ_FILM) return;
    if (film) film.detruire();
    filmFormat = formatLecteur();
    cadre.classList.toggle('lecteur__boite--p', filmFormat === 'p');
    film = window.CYQ_FILM.creer(hoteFilm, { langue: langueFilm(), format: filmFormat, calme: calme, depart: 0 });
    dernierT = -1;
  }
  function dessiner() {
    if (!film) return;
    var t = (video.currentTime || 0) * 1000, now = performance.now();
    if (!video.paused && t === dernierT) t += Math.min(now - dernierP, 250);
    else { dernierT = t; dernierP = now; }
    film.seek(t, ccOn);
  }

  /* ------------------------- la barre, en rAF ------------------------- */

  function mesurer() {
    railW = Math.max(0, piste.getBoundingClientRect().width - 2 * MARGE_RAIL);
  }

  function maj() {
    var d = video.duration;
    var p = (isFinite(d) && d > 0) ? Math.min(1, Math.max(0, video.currentTime / d)) : 0;

    lu.style.transform = 'scaleX(' + p + ')';
    tete.style.transform = 'translateX(' + (p * railW) + 'px)';

    champT.textContent = mmss(video.currentTime);
    champD.textContent = mmss(d);

    piste.setAttribute('aria-valuemax', isFinite(d) ? Math.round(d) : 0);
    piste.setAttribute('aria-valuenow', Math.round(video.currentTime || 0));
    piste.setAttribute('aria-valuetext', mmss(video.currentTime) + ' / ' + mmss(d));
    dessiner();

    /* Le tampon : ce qui est déjà téléchargé. Sans lui, une attente de
       chargement ressemble à un plantage. */
    try {
      var b = video.buffered;
      if (b && b.length && isFinite(d) && d > 0) {
        tampon.style.transform = 'scaleX(' + Math.min(1, b.end(b.length - 1) / d) + ')';
      }
    } catch (e) {}
  }

  function tourner() { maj(); boucle = requestAnimationFrame(tourner); }
  function lancerBoucle() { if (!boucle) boucle = requestAnimationFrame(tourner); }
  function couperBoucle() {
    if (boucle) { cancelAnimationFrame(boucle); boucle = 0; }
    maj();   // une dernière fois, pour que la barre s'arrête juste
  }

  /* ---------------------------- les états ----------------------------- */

  function majLecture() {
    var joue = !video.paused && !video.ended;
    icoPlay.hidden = joue;
    icoPause.hidden = !joue;
    bPlay.setAttribute('aria-label', t(joue ? 'lec.pause' : 'lec.play'));
    bPlay.setAttribute('title', t(joue ? 'lec.pause' : 'lec.play'));
  }

  function majSon() {
    var muet = video.muted || video.volume === 0;
    icoSon.hidden = muet;
    icoMuet.hidden = !muet;
    bMuet.setAttribute('aria-label', t(muet ? 'lec.unmute' : 'lec.mute'));
    bMuet.setAttribute('title', t(muet ? 'lec.unmute' : 'lec.mute'));
  }

  /* Les sous-titres suivent la langue du site, et retombent sur le
     français si la langue choisie n'a pas de piste. */
  function pistesLangue() {
    var lang = (window.CYQ && window.CYQ.lang) || 'fr';
    var tt = video.textTracks, choisie = null, repli = null, i;
    if (!tt) return;
    for (i = 0; i < tt.length; i++) {
      if (tt[i].language === lang) choisie = tt[i];
      if (tt[i].language === 'fr') repli = tt[i];
      tt[i].mode = 'disabled';
    }
    var cible = choisie || repli;
    if (cible && ccOn) cible.mode = 'showing';
    bCC.setAttribute('aria-pressed', ccOn ? 'true' : 'false');
  }

  /* --------------------------- le transport --------------------------- */

  function basculer() {
    if (video.paused || video.ended) {
      var p = video.play();
      if (p && p.catch) p.catch(function () {});   // refus d'autoplay : silence
    } else {
      video.pause();
    }
  }

  function aller(delta) {
    var d = video.duration;
    var cible = (video.currentTime || 0) + delta;
    if (cible < 0) cible = 0;
    if (isFinite(d) && cible > d) cible = d;
    video.currentTime = cible;
    maj();
  }

  /* --------------------- la barre, souris et doigt --------------------- */

  function partDe(x) {
    var r = piste.getBoundingClientRect();
    var course = Math.max(1, r.width - 2 * MARGE_RAIL);
    return Math.min(1, Math.max(0, (x - r.left - MARGE_RAIL) / course));
  }

  function deplacer(e) {
    if (!isFinite(video.duration) || video.duration <= 0) return;
    video.currentTime = partDe(e.clientX) * video.duration;
    maj();
  }

  piste.addEventListener('pointerdown', function (e) {
    if (e.button !== undefined && e.button !== 0) return;
    e.preventDefault();
    saisie = true;
    piste.setAttribute('data-saisie', '');
    try { piste.setPointerCapture(e.pointerId); } catch (err) {}
    deplacer(e);
  });

  piste.addEventListener('pointermove', function (e) { if (saisie) deplacer(e); });

  function finSaisie(e) {
    if (!saisie) return;
    saisie = false;
    piste.removeAttribute('data-saisie');
    try { piste.releasePointerCapture(e.pointerId); } catch (err) {}
  }
  piste.addEventListener('pointerup', finSaisie);
  piste.addEventListener('pointercancel', finSaisie);

  /* Les flèches sur la barre elle-même. Sans elles, seule la souris sait
     se déplacer dans la vidéo. */
  piste.addEventListener('keydown', function (e) {
    var k = e.key;
    if (k === 'ArrowLeft')       { e.preventDefault(); aller(-PAS_CLAVIER); }
    else if (k === 'ArrowRight') { e.preventDefault(); aller(PAS_CLAVIER); }
    else if (k === 'Home')       { e.preventDefault(); video.currentTime = 0; maj(); }
    else if (k === 'End' && isFinite(video.duration)) { e.preventDefault(); video.currentTime = video.duration; maj(); }
  });

  /* ---------------------------- le son -------------------------------- */

  bMuet.addEventListener('click', function () {
    video.muted = !video.muted;
    /* Rétablir le son alors que le curseur est à zéro ne rendrait rien :
       on lui redonne un niveau audible. */
    if (!video.muted && video.volume === 0) { video.volume = 0.6; vol.value = '0.6'; }
  });

  vol.addEventListener('input', function () {
    video.volume = parseFloat(vol.value);
    video.muted = (video.volume === 0);
  });

  video.addEventListener('volumechange', function () {
    if (!saisie) vol.value = String(video.muted ? 0 : video.volume);
    majSon();
  });

  /* -------------------------- les sous-titres -------------------------- */

  // Les sous-titres sont dessinés par le film, d'après le minutage de la
  // voix : un <audio> n'affiche pas ses pistes, et ce sont les mêmes phrases.
  bCC.addEventListener('click', function () { ccOn = !ccOn; pistesLangue(); maj(); });

  /* -------------------------- le plein écran --------------------------- */

  function plein() {
    var d = document;
    if (d.fullscreenElement || d.webkitFullscreenElement) {
      if (d.exitFullscreen) d.exitFullscreen();
      else if (d.webkitExitFullscreen) d.webkitExitFullscreen();
      return;
    }
    if (cadre.requestFullscreen) cadre.requestFullscreen();
    else if (cadre.webkitRequestFullscreen) cadre.webkitRequestFullscreen();
    /* iPhone : la boîte ne peut pas passer en plein écran, seule la vidéo
       le peut. On perd nos contrôles le temps du plein écran, et c'est le
       seul endroit où ceux du système reprennent la main. */
    else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();
  }
  bPlein.addEventListener('click', plein);
  document.addEventListener('fullscreenchange', function () { if (film) film.echelle(); mesurer(); maj(); });

  /* --------------------------- le média lui-même ----------------------- */

  function montrerErreur() { erreur.hidden = false; }
  video.addEventListener('error', montrerErreur);
  video.addEventListener('loadeddata', function () { erreur.hidden = true; });

  video.addEventListener('loadedmetadata', function () { poserDuree(); mesurer(); maj(); });
  video.addEventListener('play', function () { majLecture(); lancerBoucle(); });
  video.addEventListener('pause', function () { majLecture(); couperBoucle(); });
  video.addEventListener('ended', function () { majLecture(); couperBoucle(); });
  video.addEventListener('seeked', maj);
  video.addEventListener('progress', maj);

  /* ------------------------ ouvrir et fermer --------------------------- */

  function focusables() {
    return Array.prototype.slice.call(cadre.querySelectorAll(
      'a[href], button:not([disabled]), input, summary, [tabindex]:not([tabindex="-1"])'
    )).filter(function (el) { return el.offsetParent !== null; });
  }

  function ouvrir() {
    if (ouvert) return;
    ouvert = true;
    origine = document.activeElement;

    boite.hidden = false;
    document.documentElement.classList.add('lecteur-ouvert');

    /* Le média n'est demandé qu'ICI, au premier clic. Tant que la fenêtre
       n'a pas été ouverte, l'accueil n'a téléchargé que l'affiche. */
    var autreSon = poserSon();
    if (!amorce || autreSon) { amorce = true; position = 0; video.preload = 'auto'; video.load(); }
    else if (position > 0) { video.currentTime = position; }
    /* Le film se monte ICI, fenêtre ouverte : il mesure sa scène au
       montage, et une boîte cachée ne mesure que des zéros. Remonté
       seulement si la langue ou le sens de l'écran ont changé. */
    if (!film || autreSon || filmFormat !== formatLecteur()) monterFilm();

    mesurer();
    maj();
    majLecture();
    majSon();
    pistesLangue();

    /* La lecture part sur le clic qui a ouvert la fenêtre — c'est le même
       geste, et le navigateur l'accepte comme tel. Un refus d'autoplay
       laisse simplement la vidéo en pause, prête. */
    var p = video.play();
    if (p && p.catch) p.catch(function () { majLecture(); });

    bPlay.focus();
  }

  function fermer() {
    if (!ouvert) return;
    ouvert = false;

    /* On retient où on en était : rouvrir la fenêtre dans la même visite
       ne doit pas tout faire recommencer. En mémoire seulement — rien
       n'est écrit dans le navigateur pour ça. */
    position = video.currentTime || 0;
    video.pause();
    couperBoucle();

    boite.hidden = true;
    document.documentElement.classList.remove('lecteur-ouvert');

    /* Le focus revient d'où il venait — et sur le bouton de l'affiche si
       la fenêtre a été ouverte autrement que par un clic au clavier
       (body n'est pas un point de retour, il annule la navigation). */
    if (origine && origine.focus && origine !== document.body) origine.focus();
    else ouvrirB.focus();
    origine = null;
  }

  ouvrirB.addEventListener('click', ouvrir);
  fermerB.addEventListener('click', fermer);
  fond.addEventListener('click', fermer);

  bPlay.addEventListener('click', basculer);
  bRec.addEventListener('click', function () { aller(-PAS); });
  bAv.addEventListener('click', function () { aller(PAS); });

  window.addEventListener('resize', function () {
    if (filmAffiche) filmAffiche.echelle();
    if (!ouvert) return;
    // Le téléphone a tourné : le film change de mise en page, pas d'échelle
    if (film && filmFormat !== formatLecteur()) monterFilm();
    else if (film) film.echelle();
    mesurer(); maj();
  });

  /* --------------------------- le clavier ------------------------------ */

  document.addEventListener('keydown', function (e) {
    if (!ouvert) return;

    if (e.key === 'Escape') { e.preventDefault(); fermer(); return; }

    if (e.key === 'Tab') {
      /* Le piège à focus : sans lui, Tab sort de la fenêtre et parcourt
         la page derrière, que personne ne voit. */
      var f = focusables();
      if (!f.length) return;
      var premier = f[0], dernier = f[f.length - 1];
      if (e.shiftKey && document.activeElement === premier) { e.preventDefault(); dernier.focus(); }
      else if (!e.shiftKey && document.activeElement === dernier) { e.preventDefault(); premier.focus(); }
      return;
    }

    /* Les raccourcis ne doivent pas doubler la touche d'un bouton qui a
       le focus : Espace sur un bouton déclenche déjà son clic, et les
       flèches appartiennent à la barre quand c'est elle qu'on tient. */
    var cible = document.activeElement;
    var surCommande = cible && cadre.contains(cible) &&
                      (cible.tagName === 'BUTTON' || cible.tagName === 'INPUT' ||
                       cible.tagName === 'SUMMARY' || cible === piste);

    switch (e.key) {
      case ' ':
      case 'k':
      case 'K':
        if (surCommande && cible.tagName === 'BUTTON') return;
        e.preventDefault(); basculer(); break;
      case 'ArrowLeft':
        if (cible === piste || (cible && cible.type === 'range')) return;
        e.preventDefault(); aller(-PAS); break;
      case 'ArrowRight':
        if (cible === piste || (cible && cible.type === 'range')) return;
        e.preventDefault(); aller(PAS); break;
      case 'm':
      case 'M':
        e.preventDefault(); bMuet.click(); break;
      case 'f':
      case 'F':
        e.preventDefault(); plein(); break;
    }
  });

  /* La langue change pendant que la fenêtre est ouverte : les libellés
     que CE script pose n'ont pas de `data-i18n`, donc `applyI18n` ne les
     voit pas et ils resteraient dans l'ancienne langue. */
  document.addEventListener('cyq:lang', function () {
    majLecture(); majSon(); pistesLangue();
    // Le film parle la langue du site : l'affiche suit tout de suite, le
    // lecteur aussi s'il est ouvert — sinon, à sa prochaine ouverture.
    poserAffiche();
    if (ouvert) {
      // Recharger le son l'arrête : s'il jouait, il reprend au début de
      // l'autre langue — les deux films n'ont pas le même minutage.
      var jouait = !video.paused && !video.ended;
      if (poserSon()) {
        position = 0; video.load(); monterFilm(); maj();
        if (jouait) { var p = video.play(); if (p && p.catch) p.catch(function () { majLecture(); }); }
      }
    }
  });

  // Les polices changent la largeur des textes, donc les mesures du film :
  // l'affiche attend qu'elles soient là.
  (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(poserAffiche);
})();

/* =========================================================================
   LA CARTE QUI SE LANCE QUAND ON ARRIVE DESSUS.

   Sa propre IIFE, comme le lecteur complet, et pour la même raison : elle
   ne doit rien à anime.js. Si la bibliothèque manque, la carte se lance
   quand même.

   CE QU'ELLE FAIT, ET DANS QUEL ORDRE :

     elle approche  → on charge la voix et on monte le film ;
     elle est vue   → on joue, et on essaie le son ;
     elle sort      → on coupe le son, la lecture continue ;
     elle revient   → le son revient, si on ne l'avait pas coupé à la main.

   LE SON AUTOMATIQUE N'EST PAS UN DROIT. Les navigateurs le refusent tant
   que la page n'a pas été touchée — Safari toujours, Chrome selon ce qu'il
   sait de vos habitudes sur le site. On l'essaie, et sur un refus on joue
   EN SILENCE plutôt que de ne pas jouer : le film reste muet, le bouton
   montre le son coupé, et un clic le rétablit. C'est la seule façon
   honnête de tenir la promesse — prétendre que le son part toujours
   serait faux un jour sur deux.

   UN CLIC À LA MAIN L'EMPORTE ENSUITE. Quelqu'un qui coupe le son ne veut
   pas qu'il revienne au prochain passage, et le défilement n'a pas à
   défaire ce qu'il vient de décider.

   ON NE DESSINE QUE CE QU'ON VOIT. La voix continue hors écran — c'est
   demandé — mais l'image, elle, n'est plus regardée : la boucle de rendu
   s'arrête et reprend à l'entrée. Trente images par seconde dessinées
   pour personne, c'est une batterie de téléphone.
   ========================================================================= */
(function () {
  'use strict';

  var carte = document.querySelector('[data-vcard]');
  if (!carte) return;

  var hote = carte.querySelector('[data-vcard-film]');
  var son  = carte.querySelector('[data-vcard-son]');
  var bSon = carte.querySelector('[data-vcard-muet]');
  if (!hote || !son || !bSon) return;

  var icoSon  = bSon.querySelector('.vcard__ico--son');
  var icoMuet = bSon.querySelector('.vcard__ico--muet');

  if (!window.CYQ_FILM) { carte.classList.add('vcard--nue'); return; }

  var calme = window.matchMedia('(prefers-reduced-motion: reduce)').matches &&
              !/[?&]motion=on(&|$)/.test(location.search);

  var film = null,       // le film monté, ou null
      langue = '',       // la langue de la voix chargée
      boucle = 0,        // l'identifiant du rAF de dessin
      visible = false,   // la carte est-elle à l'écran
      coupeAlaMain = false,  // quelqu'un a cliqué le bouton
      refuse = false,    // le navigateur a refusé le son
      dernierT = -1, dernierP = 0;

  function langueFilm() {
    var l = (window.CYQ && window.CYQ.lang) || 'fr';
    return (window.CYQ_VOIX && window.CYQ_VOIX[l]) ? l : 'fr';
  }

  /* ---- monter ------------------------------------------------------- */

  function monter() {
    var l = langueFilm();
    if (film && l === langue) return;
    langue = l;
    if (film) film.detruire();
    /* Sans `depart` : le film s'arrête sur l'image que film.js a choisie
       comme affiche — l'annonce Discord et ses réactions. La carte n'est
       donc jamais vide, même avant d'avoir joué une seconde. */
    film = window.CYQ_FILM.creer(hote, { langue: l, format: 'l', calme: calme });
    if (!film) { carte.classList.add('vcard--nue'); return; }
    son.innerHTML = '';
    var src = document.createElement('source');
    src.src = 'assets/video/voix/' + l + '.mp4';
    src.type = 'audio/mp4';
    son.appendChild(src);
    son.load();
    dernierT = -1;
  }

  /* ---- dessiner ----------------------------------------------------- */

  /* `currentTime` n'avance que par paliers ; entre deux, on extrapole à
     l'horloge du navigateur, plafonné à 250 ms : si le son cale, l'image
     l'attend au lieu de partir seule devant. Même règle que le lecteur
     complet — deux horloges qui dérivent, c'est un film désynchronisé. */
  function dessiner() {
    boucle = 0;
    if (!film || !visible) return;
    var t = (son.currentTime || 0) * 1000, now = performance.now();
    if (!son.paused && t === dernierT) t += Math.min(now - dernierP, 250);
    else { dernierT = t; dernierP = now; }
    film.seek(t);
    if (!son.paused) boucle = requestAnimationFrame(dessiner);
  }

  function tourner() {
    if (!boucle) boucle = requestAnimationFrame(dessiner);
  }

  /* ---- le son -------------------------------------------------------- */

  function montrerLeBouton() {
    var muet = son.muted;
    bSon.setAttribute('aria-pressed', String(muet));
    var cle = muet ? 'lec.unmute' : 'lec.mute';
    var mot = (window.CYQ && window.CYQ.t) ? window.CYQ.t(cle) : '';
    if (mot) { bSon.setAttribute('aria-label', mot); bSon.setAttribute('title', mot); }
    bSon.setAttribute('data-i18n-attr', 'aria-label:' + cle + ', title:' + cle);
    if (icoSon) icoSon.hidden = muet;
    if (icoMuet) icoMuet.hidden = !muet;
  }

  /* Rend une promesse tenue si la lecture est partie, rompue sinon. Un
     navigateur ancien ne rend rien du tout : on considère alors que
     c'est parti, ce qu'il n'a aucun moyen de démentir. */
  function jouer() {
    var p = son.play();
    return (p && p.then) ? p : Promise.resolve();
  }

  function lancer() {
    if (!film) return;
    /* On essaie AVEC le son, et on retombe sur le silence s'il est
       refusé. L'ordre compte : commencer muet puis démuter demande la
       même permission, mais une seconde plus tard et sans geste — c'est
       refusé à tous les coups. */
    var avecSon = !coupeAlaMain && !refuse;
    son.muted = !avecSon;
    montrerLeBouton();
    jouer().then(tourner).catch(function () {
      if (son.muted) return;         // refusé même en silence : on renonce
      refuse = true;
      son.muted = true;
      montrerLeBouton();
      jouer().then(tourner).catch(function () { /* rien à faire de plus */ });
    });
  }

  /* ---- entrer et sortir de l'écran ----------------------------------- */

  function entre() {
    visible = true;
    monter();
    if (calme) { tourner(); return; }   /* moins de mouvement : on ne lance pas */
    if (son.paused) lancer();
    else { son.muted = coupeAlaMain || refuse; montrerLeBouton(); tourner(); }
  }

  function sort() {
    visible = false;
    if (boucle) { cancelAnimationFrame(boucle); boucle = 0; }
    /* La lecture continue, le son s'arrête : c'est exactement ce qu'on
       veut d'une présentation qu'on a dépassée — on peut revenir dessus
       sans l'avoir perdue, et on ne l'entend plus depuis le pied de la
       page. */
    son.muted = true;
    montrerLeBouton();
  }

  /* La moitié de la carte, et pas un pixel : une carte qui dépasse à
     peine en haut de l'écran n'est pas « arrivée ». Le `rootMargin`
     laisse le temps de charger la voix avant qu'elle ne soit vue. */
  if (window.IntersectionObserver) {
    new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        if (e.isIntersecting && e.intersectionRatio >= 0.5) entre();
        else if (visible && e.intersectionRatio < 0.3) sort();
      });
    }, { threshold: [0, 0.3, 0.5], rootMargin: '200px 0px' }).observe(carte);
  } else {
    /* Pas d'observateur : on monte le film pour que la carte ne soit pas
       vide, et on laisse le clic faire le reste. */
    monter();
  }

  /* ---- les branchements ---------------------------------------------- */

  bSon.addEventListener('click', function (e) {
    e.stopPropagation();
    coupeAlaMain = !son.muted;      /* on note la DÉCISION, pas l'état */
    refuse = false;                 /* un clic est un geste : le son est permis */
    son.muted = coupeAlaMain;
    montrerLeBouton();
    if (son.paused && !calme) jouer().then(tourner).catch(function () {});
  });

  /* Un onglet caché ne dessine rien. La voix, elle, est coupée par le
     navigateur lui-même. */
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { if (boucle) { cancelAnimationFrame(boucle); boucle = 0; } }
    else if (visible) tourner();
  });

  son.addEventListener('ended', function () {
    if (boucle) { cancelAnimationFrame(boucle); boucle = 0; }
  });
  son.addEventListener('play', function () { if (visible) tourner(); });

  /* Les polices changent la largeur des textes, donc les mesures du
     film ; la fenêtre change son échelle. */
  window.addEventListener('resize', function () { if (film) film.echelle(); });

  document.addEventListener('cyq:lang', function () {
    if (!film) return;
    var jouait = !son.paused;
    monter();
    if (jouait && visible && !calme) lancer();
  });

  /* ---- quand le lecteur complet s'ouvre par-dessus -------------------

     DEUX VOIX EN MÊME TEMPS. La carte continue de jouer derrière la
     fenêtre — elle est toujours à l'écran, donc rien ne l'arrête — et le
     lecteur complet lance la sienne. On entend les deux, décalées.

     On surveille l'attribut `hidden` de la fenêtre plutôt que le clic
     qui l'ouvre : elle se ferme aussi par Échap et par le fond, et trois
     écouteurs pour un même état finissent toujours par en oublier un.

     La carte REPREND là où elle en était, muette ou non selon ce qui
     avait été décidé avant — on ne la remet pas au début pour être
     passé par la grande version. */
  var modale = document.querySelector('[data-lecteur]');
  if (modale && window.MutationObserver) {
    var jouaitAvant = false;
    new MutationObserver(function () {
      var ouverte = !modale.hidden;
      if (ouverte) {
        jouaitAvant = !son.paused;
        son.pause();
        if (boucle) { cancelAnimationFrame(boucle); boucle = 0; }
      } else if (jouaitAvant && visible && !calme) {
        jouer().then(tourner).catch(function () {});
      }
    }).observe(modale, { attributes: true, attributeFilter: ['hidden'] });
  }

  /* MUET AU REPOS, et le bouton le dit. C'est l'état dans lequel la
     carte partira neuf fois sur dix, puisque le son automatique est
     refusé par défaut : annoncer « Couper le son » avant d'avoir joué
     une seule note promettait quelque chose qu'on ne tient pas. */
  son.muted = true;
  montrerLeBouton();
})();
