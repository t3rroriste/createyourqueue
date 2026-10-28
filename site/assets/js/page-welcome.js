/* =========================================================================
   CreateYourQueue — l'écran de transition

   L'attente ne compte plus, elle s'étend. La version précédente rangeait
   quatre jetons dans quatre emplacements : quatre à-coups, la grammaire
   d'un formulaire en plusieurs étapes. Ici le nom de la marque se compose
   lettre à lettre, et UN SEUL trait de cuivre s'étend sous lui.

   Ce qui n'a pas changé, et qui est l'essentiel : les QUATRE JALONS SONT
   RÉELS — polices, logo décodé, dashboard.html, puis app.css +
   page-dashboard.js. Chacun pousse le trait d'un quart, et celui qui
   arrive en dernier déclenche la sortie : la fin de l'animation et le
   basculement sont un seul geste.

   La progression ne ment pas. Ce n'est pas une boucle décorative de 5
   secondes : si tout est prêt à 2,6 s on part à 2,6 s. Les 5 secondes sont
   un PLAFOND — le contrat « cet écran ne retient jamais personne plus
   longtemps que ça ».

   C'est le seul écran du site dont la sortie est un minuteur, et il ne se
   saute pas : le lien « Ouvrir maintenant » a été retiré. Toute la charge
   repose donc sur ce minuteur, qui est posé avant la moindre animation —
   un onglet en arrière-plan gèle les images, jamais les minuteurs.
   Les deux portes du panneau passent par ici : la connexion et le choix
   du serveur.

   anime.js v4 en UMD, comme le reste du site : les exports nommés sont lus
   sur le global `anime`, et la page doit rester lisible si la bibliothèque
   n'a pas chargé. L'avancée du trait, elle, ne dépend PAS d'anime.js :
   elle passe par des transitions CSS, qui tournent hors du thread
   principal pendant que la page précharge le panneau.
   ========================================================================= */
(function () {
  'use strict';

  /* ------------------------------------------------------------- réglages */

  /* L'entrée a la parole en premier : le trait ne bouge pas avant que le
     nom soit posé. 760 ms = coque (700) + dernière lettre arrivée. */
  var DEBUT = 760;

  /* Cadence minimale entre deux poussées. Ce n'est PAS une fausse durée :
     les jalons peuvent tous être tenus en 300 ms sur un réseau rapide, et
     quatre poussées dans la même image ne se lisent pas. 380 ms est le
     temps qu'il faut pour voir le trait avancer et comprendre qu'il
     continue le mouvement précédent. */
  var CADENCE = 380;

  /* La durée de la poussée, à l'identique du CSS. La sortie s'enchaîne sur
     la fin de la dernière, elle ne l'interrompt pas. */
  var POUSSEE = 620;

  /* 70 ms, le token --t-leave du design system : l'écran est vide avant la
     fin de la durée. +20 ms pour laisser passer une image avant de
     basculer, sinon on remplace le document pendant le fondu. */
  var SORTIE = 70;

  /* Le plafond. Au-delà, on part même si un préchargement traîne : le
     panneau sait charger ce qui lui manque, et personne ne doit rester
     coincé ici. */
  var PLAFOND = 5000;

  /* Sans mouvement il n'y a rien à regarder, donc rien à attendre. */
  var DEBUT_CALME   = 120;
  var CADENCE_CALME = 220;
  var POUSSEE_CALME = 180;
  var PLAFOND_CALME = 1500;

  /* Quatre jalons, donc quatre quarts. Le nombre vit ici et dans le
     `aria-valuemax` du balisage : les deux doivent dire la même chose. */
  var TOTAL = 4;

  var $ = function (s, r) { return (r || document).querySelector(s); };

  var splash = $('[data-splash]');
  var logo   = $('[data-logo]');
  var halo   = $('[data-halo]');
  var titre  = $('[data-title]');
  var lead   = $('[data-lead]');
  var trait  = $('[data-trait]');
  var fil    = $('[data-fil]');
  var tete   = $('[data-tete]');

  /* ------------------------------------------------------ la destination */

  /* Le panneau a besoin d'un serveur : sans lui il ne sait pas quoi
     afficher. login.html passe l'identifiant choisi, et s'il manque on
     renvoie vers le sélecteur plutôt que vers un panneau vide. */
  function destination() {
    var guild = new URLSearchParams(location.search).get('guild');
    return guild ? 'dashboard.html?guild=' + encodeURIComponent(guild) : 'servers.html';
  }

  var cible = destination();
  var parti = false;

  /* Le numéro de version des assets, relu sur le <script> de cette page.
     Pourquoi le relire : le préchargement doit viser EXACTEMENT les URL
     que le panneau demandera ensuite, numéro compris, sinon on télécharge
     deux fois les mêmes fichiers sous deux clés de cache différentes. */
  function version() {
    var moi = $('script[src*="page-welcome.js"]');
    var m = moi && /\?v=([^"&]+)/.exec(moi.getAttribute('src') || '');
    return m ? '?v=' + m[1] : '';
  }

  /* ------------------------------------------------------- mode de rendu */

  var A = window.anime;
  var force = document.documentElement.classList.contains('motion-force');
  var calme = !force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var debut   = calme ? DEBUT_CALME   : DEBUT;
  var cadence = calme ? CADENCE_CALME : CADENCE;
  var poussee = calme ? POUSSEE_CALME : POUSSEE;
  var plafond = calme ? PLAFOND_CALME : PLAFOND;

  /* ------------------------------------------------------------ la sortie */

  function partir(ev) {
    if (ev) ev.preventDefault();
    if (parti) return;
    parti = true;

    if (splash) splash.classList.add('is-leaving');
    setTimeout(function () { location.replace(cible); }, SORTIE + 20);
  }

  /* Le minuteur de plafond ne dépend PAS des animations : un onglet en
     arrière-plan les met en pause, et la personne se retrouverait devant
     un trait qui n'arrive jamais au bout.

     Depuis qu'il n'y a plus de lien pour sauter l'écran, cette ligne EST
     la sortie. Elle est posée ici, avant toute animation et avant tout
     préchargement, pour qu'aucune erreur survenant plus bas ne puisse
     empêcher la page de partir. */
  setTimeout(partir, plafond);

  /* ------------------------------------------------------- les lettres -- */

  /* Le nom est découpé en JS et non dans le HTML, parce que l'i18n écrit
     `textContent` sur ce titre : des <span> posés à la main seraient
     effacés au premier passage de la traduction. On découpe donc APRÈS
     elle, et on recommence si la langue change.

     Le mot entier reste annoncé d'un bloc : `aria-label` sur le titre, et
     les lettres masquées aux lecteurs d'écran — sinon le nom serait épelé
     caractère par caractère. */
  var lettres = [];

  function decouper() {
    if (!titre) return;

    var texte = (titre.getAttribute('data-mot') || titre.textContent || '').trim();
    if (!texte) return;

    /* Mémorisé au premier passage : après le découpage, `textContent`
       vaudrait toujours le mot, mais autant ne pas en dépendre. */
    titre.setAttribute('data-mot', texte);
    titre.setAttribute('aria-label', texte);

    var html = '';
    for (var i = 0; i < texte.length; i++) {
      var c = texte.charAt(i);
      /* L'espace insécable : une espace ordinaire dans un inline-block de
         largeur nulle disparaîtrait au rendu. */
      html += '<span aria-hidden="true">' + (c === ' ' ? '&nbsp;' : c) + '</span>';
    }
    titre.innerHTML = html;
    lettres = Array.prototype.slice.call(titre.querySelectorAll('span'));
  }

  /* --------------------------------------------------------- le trait --- */

  var tenus   = 0;   // jalons tenus
  var pousses = 0;   // quarts déjà parcourus
  var dernier = 0;   // horodatage de la dernière poussée
  var depart  = Date.now();
  var prevu   = false;

  /* La largeur de la piste, mesurée à la demande. Elle dépend du nom, donc
     de la police : la relire au moment de bouger la pointe évite de la
     figer avant que Geist soit arrivée. Une lecture toutes les 380 ms ne
     coûte rien ; la figer coûterait une pointe au mauvais endroit. */
  function avancer() {
    var p = pousses / TOTAL;

    if (fil) fil.style.transform = 'scaleX(' + p + ')';
    if (tete && trait) {
      tete.style.transform =
        'translate3d(' + Math.round(trait.getBoundingClientRect().width * p) + 'px, 0, 0)';
    }
    if (trait) trait.setAttribute('aria-valuenow', String(pousses));

    /* Au bout, la pointe cesse de respirer : un battement sur un trait
       plein dirait qu'il reste quelque chose à attendre. */
    if (tete && pousses >= TOTAL) tete.classList.add('is-done');
  }

  function pousser() {
    prevu = false;
    if (parti || pousses >= TOTAL) return;

    pousses += 1;
    avancer();
    dernier = Date.now();

    if (pousses >= TOTAL) {
      /* Le trait est au bout : on enchaîne sur la FIN de sa course. Il
         arrive, l'écran s'efface, le panneau s'ouvre. */
      setTimeout(partir, poussee);
    } else {
      programmer();
    }
  }

  function programmer() {
    if (prevu || parti || pousses >= TOTAL) return;
    if (tenus <= pousses) return;   // aucun jalon neuf à annoncer

    var quand = Math.max(dernier + cadence, depart + debut);
    prevu = true;
    setTimeout(pousser, Math.max(0, quand - Date.now()));
  }

  /* Un jalon tenu = un quart de plus. Une promesse qui ÉCHOUE compte
     aussi : une police qui ne charge pas ou un préchargement refusé
     n'empêche pas le panneau de s'ouvrir, et l'écran ne doit pas
     s'arrêter sur un détail. Ce qu'une poussée affirme, c'est « cette
     vérification est finie », pas « elle a réussi ». */
  function jalon(p) {
    var compter = function () { tenus += 1; programmer(); };
    try { p.then(compter, compter); } catch (e) { compter(); }
  }

  function precharger(url) {
    if (!window.fetch) return Promise.resolve();
    return fetch(url, { credentials: 'same-origin', mode: 'same-origin' });
  }

  function jalons() {
    var v = version();

    // 1 — les polices. Geist arrive du réseau ; tant qu'elle manque, le
    //     nom se composerait sur la police de repli puis sauterait — et
    //     c'est précisément le nom qu'on regarde ici.
    jalon(document.fonts ? document.fonts.ready : Promise.resolve());

    // 2 — le logo décodé. `decode()` attend le décodage, pas seulement le
    //     téléchargement : c'est la différence entre « l'octet est là » et
    //     « l'image peut être peinte sans saccade ».
    jalon(logo && logo.decode ? logo.decode() : Promise.resolve());

    // 3 — la page de destination elle-même.
    jalon(precharger(cible));

    // 4 — ce dont la destination a besoin pour s'afficher. Groupés : sans
    //     les deux, le panneau s'ouvre sur une page nue.
    jalon(Promise.all([
      precharger('assets/css/app.css' + v),
      precharger('assets/js/page-dashboard.js' + v)
    ]));
  }

  /* ----------------------------------------------------------- l'entrée */

  /* anime.js lève sur une cible absente, et une exception ICI est le pire
     endroit possible : les états de départ sont posés, la suite ne l'est
     plus, et l'écran reste à `opacity: 0` — donc vide, avec le seul lien
     de secours pour sortir. Un élément manquant doit coûter son animation,
     pas la page. */
  function vivants(liste) {
    return liste.filter(function (el) { return !!el; });
  }

  /* Le filet.

     Les états de départ sont à `opacity: 0`, et c'est la frise qui les
     ramène. Si elle n'avance pas, l'écran reste VIDE — pas « sans
     animation », vide, avec le seul lien de secours pour sortir.

     Et elle n'avance pas dans un cas parfaitement ordinaire : un onglet
     ouvert en arrière-plan. Le navigateur y suspend `requestAnimationFrame`
     ET les transitions CSS, donc anime.js est gelé pendant que les
     minuteurs, eux, continuent de tourner. La page finit par basculer sans
     que personne ait rien vu.

     D'où ce délai : passé 1400 ms, si la frise n'a pas fini, on efface les
     styles qu'elle a posés et tout apparaît d'un coup. Un nom qui surgit
     sans élégance vaut infiniment mieux qu'un écran noir. */
  var FILET = 1400;
  var tl = null;
  var entreeFinie = false;

  function poserFinal() {
    if (entreeFinie) return;
    entreeFinie = true;

    /* `revert()` retire les styles en ligne qu'anime.js a écrits : on
       retombe sur ce que dit la feuille, c'est-à-dire l'état final. Le
       faire AVANT le nettoyage manuel, sinon la frise les réécrirait. */
    if (tl && tl.revert) { try { tl.revert(); } catch (e) {} }

    vivants([logo, halo, trait, lead]).concat(lettres).forEach(function (el) {
      el.style.opacity = '';
      el.style.transform = '';
    });
  }

  function ouverture() {
    var utils = A.utils;
    var OUT = A.cubicBezier(.16, 1, .3, 1);

    A.createScope({ root: document.body }).add(function () {

      /* États de départ posés en JS, jamais en CSS : si le script tombe,
         la page reste lisible au lieu de rester invisible. Le lien de
         secours n'est PAS dans cette liste — il doit être là dès le
         début. */
      function poser(liste, props) {
        var cibles = vivants(liste);
        if (cibles.length) utils.set(cibles, props);
      }

      poser([logo], { opacity: 0, scale: .94 });
      poser([halo], { opacity: 0, scale: .82 });
      poser(lettres, { opacity: 0, y: 12 });
      poser([trait, lead], { opacity: 0 });

      tl = A.createTimeline({
        defaults: { ease: OUT },
        /* La frise est allée au bout : le filet n'a plus de raison d'être,
           et surtout il ne doit plus effacer quoi que ce soit. */
        onComplete: function () { entreeFinie = true; }
      });

      function etape(cible, props, t) { if (cible) tl.add(cible, props, t); }

      /* Pas de rayon animé sur la coque : `border-radius` repeint une
         surface plein écran à chaque image. Seule l'échelle bouge, et de
         1,2 % — on doit sentir que l'écran se pose, pas le voir grandir. */
      tl.add('.shell', { scale: [.988, 1], duration: 700 }, 0);

      etape(halo, { opacity: 1, scale: 1, duration: 1200 }, 40);

      /* Le logo arrive sans dépassement et sans flou : un ressort ou un
         `blur` qui se résorbe sont deux effets que l'écran ne peut pas
         s'offrir, puisque c'est le nom qu'on doit regarder. */
      etape(logo, { opacity: 1, scale: 1, duration: 700 }, 120);

      /* 26 ms entre deux lettres : assez pour qu'on voie le mot s'écrire,
         trop peu pour qu'on l'attende. Quinze lettres tiennent ainsi en
         390 ms, et la dernière est posée avant que le trait démarre à
         760 ms. Au-delà de 30 ms on lit une machine à écrire, ce qui est
         une autre animation — et une moins sobre. */
      if (lettres.length) {
        tl.add(lettres, {
          opacity: 1, y: 0, duration: 620, delay: A.stagger(26)
        }, 300);
      }

      /* La piste apparaît APRÈS le nom : elle est le socle de ce qui
         vient d'être écrit, pas un objet qui l'accompagne. */
      etape(trait, { opacity: 1, duration: 420 }, 700);
      etape(lead,  { opacity: 1, duration: 520 }, 780);
    });
  }

  /* --------------------------------------------------------- orchestration */

  /* La langue est posée par app.js sur `DOMContentLoaded`, et le découpage
     doit venir après elle. app.js ayant enregistré son démarrage en
     premier, il passera avant celui-ci. */
  function demarrer() {
    decouper();
    avancer();

    if (!A || calme) {
      /* Sans bibliothèque ou sans mouvement : rien n'est masqué, tout est
         déjà à sa place. Le trait avance quand même — c'est lui qui porte
         l'information, et l'information ne dépend pas d'anime.js. */
      entreeFinie = true;
      jalons();
      return;
    }

    /* Une page ouverte en arrière-plan n'anime rien : inutile de masquer
       quoi que ce soit, on poserait un écran vide que personne ne verrait
       se remplir. On attend qu'elle revienne au premier plan. */
    if (document.visibilityState === 'hidden') {
      entreeFinie = true;
      jalons();
      return;
    }

    ouverture();
    setTimeout(poserFinal, FILET);

    /* Repartir en arrière-plan pendant l'entrée produit le même gel. On ne
       rejoue pas la frise au retour — on la termine. Rejouer une entrée
       qu'on a ratée fait surgir une animation au moment où l'on regarde
       déjà ailleurs. */
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') poserFinal();
    });

    jalons();
  }

  /* Changer de langue ne change pas le nom — il est identique dans les
     cinq — mais l'i18n réécrit quand même `textContent`, ce qui effacerait
     les lettres. On redécoupe, et on repose l'avancée du trait. */
  document.addEventListener('cyq:lang', function () {
    decouper();
    avancer();
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', demarrer);
  else demarrer();
})();
