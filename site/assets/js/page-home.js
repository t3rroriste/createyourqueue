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
      var texte = $$('[data-reveal-text]', sec);
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
   LA FENÊTRE D'UN MODULE
   =========================================================================
   Les six cartes de la grille menaient sur /modules et son ancre. Elles
   ouvrent maintenant une fenêtre, sur place : la lecture de l'accueil
   n'est pas coupée, et « Ajouter à Discord » est sous la main au moment
   où le module vient de convaincre.

   Dans sa propre IIFE, et pour la raison qui vaut pour la FAQ : elle ne
   doit rien à anime.js. Si la bibliothèque manque, la fenêtre s'ouvre
   quand même, sans l'arrivée en fondu — et si JavaScript manque tout
   entier, le `href` des cartes mène toujours à /modules#queue.

   CE QU'ELLE MONTRE EST RECOPIÉ DE LA CARTE. La maquette, le titre et le
   résumé sont clonés depuis la carte cliquée ; seul le texte long lui est
   propre (`mm.*`). Six maquettes réécrites ici seraient six choses à
   tenir d'accord avec la grille, et c'est précisément comme ça qu'un
   second texte finit par mentir.
   ========================================================================= */
(function fenetreModule() {
  'use strict';

  var boite = document.querySelector('[data-modmodal]');
  var cartes = document.querySelectorAll('[data-mod-open]');
  if (!boite || !cartes.length) return;

  var dialogue = boite.querySelector('[data-modmodal-boite]');
  var vue      = boite.querySelector('[data-modmodal-view]');
  var titre    = boite.querySelector('[data-modmodal-t]');
  var para     = boite.querySelector('[data-modmodal-p]');
  var fond     = boite.querySelector('[data-modmodal-fond]');
  var fermerB  = boite.querySelector('[data-modmodal-close]');

  /* Le module ouvert, et la carte d'où l'on vient : c'est à elle que le
     focus revient à la fermeture. Sans ça, on se retrouve rejeté en haut
     de la page, à chercher où on en était. */
  var ouvert = null;
  var origine = null;

  /* Le texte long de chaque module. Les clés sont dans les cinq
     dictionnaires ; le nom du module est celui de l'ancre, qui est déjà
     écrit sur la carte. */
  var TEXTES = {
    queue: 'mm.queue', mmr: 'mm.mmr', duel: 'mm.duel',
    clan: 'mm.clan', securite: 'mm.sec', options: 'mm.opt'
  };

  function t(cle) {
    return (window.CYQ && CYQ.t) ? CYQ.t(cle) : '';
  }

  /* Tout ce qui peut recevoir le focus dans la fenêtre. Recalculé à
     chaque Tab plutôt que gardé : le bouton Discord devient inerte quand
     CLIENT_ID est vide, et une liste figée l'enverrait quand même. */
  function focusables() {
    return Array.prototype.filter.call(
      dialogue.querySelectorAll('a[href], button:not([disabled])'),
      function (el) { return el.offsetParent !== null; });
  }

  function remplir(carte) {
    var nom = carte.getAttribute('data-mod-open');
    var vignette = carte.querySelector('.mcard__view');
    var h = carte.querySelector('.mcard__t');

    vue.innerHTML = '';
    if (vignette) {
      var copie = vignette.cloneNode(true);
      copie.removeAttribute('aria-hidden');     // le parent le porte déjà
      vue.appendChild(copie);
    }
    if (h) titre.textContent = h.textContent;
    para.textContent = t(TEXTES[nom] || '');
    return nom;
  }

  function ouvrir(carte) {
    if (ouvert) return;
    origine = carte;
    ouvert = remplir(carte);

    boite.hidden = false;
    /* Le défilement de la page est bloqué par une classe sur <html> et
       non par `overflow` posé en style inline : la page Modules et le
       tiroir mobile se servent du même verrou, et deux verrous qui se
       croisent en laissent toujours un ouvert. */
    document.documentElement.classList.add('modmodal-ouvert');

    /* L'ancre dans la barre d'adresse : la fenêtre devient partageable,
       et surtout /#queue rouvre exactement ce qu'on avait envoyé.
       `replaceState` et non une vraie ancre — le navigateur sauterait
       sur la section `#modules` de la page. */
    if (window.history && history.replaceState) {
      try { history.replaceState(history.state, '', '#' + ouvert); } catch (e) {}
    }

    /* Le premier élément de la fenêtre prend le focus, et pas la
       fenêtre elle-même : on arrive sur le bouton qui sert. */
    var f = focusables();
    if (f.length) f[0].focus();

    /* L'effet ballon sur la maquette : la fenêtre n'existait pas au
       démarrage, app.js ne l'a donc pas encore vue. Une seule fois, la
       fonction se garde elle-même d'un second branchement. */
    if (window.CYQ && CYQ.ballon) CYQ.ballon(vue);
  }

  function fermer() {
    if (!ouvert) return;
    ouvert = null;
    boite.hidden = true;
    document.documentElement.classList.remove('modmodal-ouvert');

    /* L'ancre est nettoyée : une adresse qui garde `#duel` alors que la
       fenêtre est fermée rouvrirait le duel au prochain rechargement. */
    if (window.history && history.replaceState) {
      try {
        history.replaceState(history.state, '', location.pathname + location.search);
      } catch (e) {}
    }

    if (origine) { origine.focus(); origine = null; }
  }

  Array.prototype.forEach.call(cartes, function (carte) {
    carte.addEventListener('click', function (e) {
      /* Clic du milieu, Ctrl, Cmd, Maj : on laisse le lien faire son
         travail et ouvrir /modules dans un onglet. C'est la même règle
         que pour le reste des liens du site. */
      if (e.defaultPrevented || e.button !== 0 || e.metaKey ||
          e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      ouvrir(carte);
    });
  });

  if (fond) fond.addEventListener('click', fermer);
  if (fermerB) fermerB.addEventListener('click', fermer);

  document.addEventListener('keydown', function (e) {
    if (!ouvert) return;
    if (e.key === 'Escape') { e.preventDefault(); fermer(); return; }
    if (e.key !== 'Tab') return;

    /* Le piège à focus. Sans lui, Tab sort de la fenêtre et va parcourir
       la page derrière, que personne ne voit. */
    var f = focusables();
    if (!f.length) return;
    var premier = f[0], dernier = f[f.length - 1];
    if (e.shiftKey && document.activeElement === premier) {
      e.preventDefault(); dernier.focus();
    } else if (!e.shiftKey && document.activeElement === dernier) {
      e.preventDefault(); premier.focus();
    }
  });

  /* La langue change pendant que la fenêtre est ouverte : le texte long
     n'a pas de `data-i18n` — il est posé par ce script — donc
     `applyI18n` ne le voit pas et il resterait dans l'ancienne langue. */
  document.addEventListener('cyq:lang', function () {
    if (ouvert) para.textContent = t(TEXTES[ouvert] || '');
  });

  /* ARRIVER DIRECTEMENT SUR UN MODULE.
     /#duel ouvre le duel. C'est ce que `replaceState` écrit plus haut,
     donc c'est ce qu'un lien partagé contient — il doit rouvrir la même
     chose, sans quoi l'adresse ment. */
  function depuisAncre() {
    var nom = (location.hash || '').slice(1);
    if (!nom || !TEXTES[nom]) return;
    var carte = document.querySelector('[data-mod-open="' + nom + '"]');
    if (carte) ouvrir(carte);
  }
  depuisAncre();
  window.addEventListener('hashchange', function () {
    if (ouvert) return;
    depuisAncre();
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

  /* ---------------------------------------------------------------------
     L'affiche manquante. Le src pointe sur un fichier qui n'est peut-être
     pas encore déposé : plutôt qu'une icône d'image cassée au milieu de
     l'accueil, la coque devient un aplat. */
  function sansAffiche() { coque.classList.add('video__coque--nue'); }
  if (affiche) {
    affiche.addEventListener('error', sansAffiche);
    if (affiche.complete && affiche.naturalWidth === 0) sansAffiche();
  }

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

  bCC.addEventListener('click', function () { ccOn = !ccOn; pistesLangue(); });

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
  document.addEventListener('fullscreenchange', function () { mesurer(); maj(); });

  /* --------------------------- le média lui-même ----------------------- */

  function montrerErreur() { erreur.hidden = false; }
  var sources = video.querySelectorAll('source');
  if (sources.length) sources[sources.length - 1].addEventListener('error', montrerErreur);
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
    if (!amorce) { amorce = true; video.preload = 'metadata'; video.load(); }
    else if (position > 0) { video.currentTime = position; }

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

    if (origine && origine.focus) origine.focus();
    else ouvrirB.focus();
    origine = null;
  }

  ouvrirB.addEventListener('click', ouvrir);
  fermerB.addEventListener('click', fermer);
  fond.addEventListener('click', fermer);

  bPlay.addEventListener('click', basculer);
  bRec.addEventListener('click', function () { aller(-PAS); });
  bAv.addEventListener('click', function () { aller(PAS); });

  window.addEventListener('resize', function () { if (ouvert) { mesurer(); maj(); } });

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
  });
})();
