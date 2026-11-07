/* =========================================================================
   LE TEXTE QUI SE TAPE, S'EFFACE, ET RECOMMENCE
   =========================================================================
   Un fichier à part, et c'est la seule chose qui ne se négocie pas ici.

   La boucle vivait dans page-home.js, dans sa propre IIFE, parce que celle
   du héros sort à sa deuxième ligne quand `window.anime` est absent — une
   boucle écrite à l'intérieur ne jouerait donc jamais sur un navigateur où
   la bibliothèque n'a pas chargé, exactement le cas où l'on tient le plus à
   ce que la page vive. Elle est maintenant dans son propre fichier, pour la
   même raison poussée d'un cran : la page Modules la réclame aussi, et la
   recopier aurait fait deux boucles à tenir d'accord.

   Elle ne doit rien à anime.js : un setTimeout récursif, et rien d'autre.

   Un élément s'y inscrit par attribut, jamais par sélecteur écrit ici :

     data-frappe="h.title"              la clé i18n du texte à taper
     data-frappe-depart="cyq:titre-..."  l'événement qui lance la boucle
                                         (sinon elle part d'elle-même)

   Le script ne connaît donc aucune page, et une page neuve n'a rien à
   ajouter ici.
   ========================================================================= */
(function () {
  'use strict';

  var CYQ = window.CYQ = window.CYQ || {};

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

  /* Lu ici et non partagé avec page-home.js : les deux fichiers sont
     étanches, et ?motion=on doit forcer la boucle ici aussi. */
  var force = document.documentElement.classList.contains('motion-force');
  var calme = !force && window.matchMedia &&
              window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Une frappe par élément. L'objet rendu n'expose que `partir` : tout le
     reste — langue, redimensionnement, onglet caché — se branche ici. */
  function frapper(el, cle) {
    var vu = null;           // la partie animée, la seule qui change
    var sr = null;           // le texte réel, figé, pour les lecteurs d'écran
    var texte = '';
    var minuteur = null;
    var demarre = false;

    function texteCourant() {
      /* La clé plutôt que le DOM : applyI18n vient peut-être d'écrire
         dedans, mais c'est le dictionnaire qui fait foi, et lui seul sait
         la langue choisie. Le contenu de la balise sert de repli quand
         app.js n'a pas (encore) tourné. */
      if (cle && window.CYQ && window.CYQ.t) {
        var v = window.CYQ.t(cle);
        if (v && v !== cle) return v;
      }
      return (el.textContent || '').trim();
    }

    /* Le balisage de la frappe. Deux enfants, et le partage est net :

         <span class="sr-only">        le texte réel, entier, UNE fois. C'est
                                       lui que lit un lecteur d'écran.
         <span class="frappe__txt">    la partie qui change, aria-hidden.

       Pas d'aria-live, jamais : la frappe serait annoncée lettre par
       lettre, indéfiniment, et le titre deviendrait inécoutable. Et pas de
       caractère « | » injecté dans le DOM pour le curseur — il serait lu
       lui aussi. Le curseur est un pseudo-élément, animé en opacité seule.
     */
    function batir() {
      el.textContent = '';
      sr = document.createElement('span');
      sr.className = 'sr-only';
      sr.textContent = texte;
      vu = document.createElement('span');
      vu.className = 'frappe__txt';
      vu.setAttribute('aria-hidden', 'true');
      el.appendChild(sr);
      el.appendChild(vu);
    }

    /* La hauteur réservée, MESURÉE et non devinée. Sans elle, une phrase
       qui passe de trois lignes à une repousse tout ce qui suit à chaque
       caractère — la page tremble pendant toute la boucle. On mesure le
       texte complet, on fige cette hauteur, et le texte varie dedans.

       Une valeur en CSS ne pourrait pas faire ce travail : la hauteur
       dépend de la langue, de la largeur de l'écran et de la police
       effectivement chargée. Elle est donc reprise à chaque changement de
       langue et à chaque redimensionnement. */
    function mesurer() {
      var garde = vu.textContent;
      vu.textContent = texte;
      el.style.minHeight = '';
      var haut = el.offsetHeight;
      vu.textContent = garde;
      if (haut) el.style.minHeight = haut + 'px';
    }

    function stopper() {
      if (minuteur) { clearTimeout(minuteur); minuteur = null; }
    }

    /* L'état final, figé : le texte entier, sans curseur, sans boucle.
       C'est ce que voit quelqu'un qui a demandé moins de mouvement, et
       c'est aussi le repli de tout ce qui pourrait mal tourner. */
    function poserEntier() {
      stopper();
      el.classList.remove('is-typing');
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
      el.classList.add('is-typing');
      pas();
    }

    /* Un onglet caché n'affiche rien : une boucle qui continue d'y tourner
       réveille le processeur toutes les quarante millisecondes pour
       personne. On la coupe, et on la reprend du début au retour —
       reprendre au caractère exact où l'on s'était arrêté n'apporte rien
       que personne n'a vu partir. */
    document.addEventListener('visibilitychange', function () {
      if (!demarre || calme) return;
      if (document.hidden) stopper();
      else if (!minuteur) boucle();
    });

    /* app.js émet `cyq:lang` APRÈS avoir réécrit le texte des [data-i18n]
       — donc après avoir effacé les deux enfants posés plus haut. On
       rebâtit tout : nouvelle phrase, nouvelle mesure, boucle repartie de
       zéro. Sans ça, l'élément continuerait de taper l'ancienne langue
       dans un DOM qui n'existe plus. */
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

    return function partir() {
      if (demarre) return;
      demarre = true;
      texte = texteCourant();
      if (!texte) return;
      el.classList.add('frappe');
      batir();
      mesurer();
      if (calme) { poserEntier(); return; }
      boucle();
    };
  }

  CYQ.frappe = frapper;

  /* ------------------------------------------------------- le branchement */

  /* Deux départs possibles, et le premier qui arrive gagne :

       data-frappe-depart   l'événement que la page promet d'émettre — sur
                            l'accueil, `cyq:titre-libre`, quand la cascade
                            d'ouverture a fini de poser le titre ;
       le filet             1 900 ms, juste après que le <head> ait
                            découvert le héros de lui-même (1 800 ms).
                            C'est le chemin pris quand anime.js manque,
                            quand la timeline ne se termine pas, ou quand
                            on a demandé moins de mouvement.

     Sans `data-frappe-depart`, il n'y a rien à attendre : la boucle part
     au prochain tour de boucle d'événements, le temps qu'app.js ait posé
     les textes. */
  function brancher() {
    var els = document.querySelectorAll('[data-frappe]');
    Array.prototype.forEach.call(els, function (el) {
      var partir = frapper(el, el.getAttribute('data-frappe'));
      var depart = el.getAttribute('data-frappe-depart');
      if (depart) {
        document.addEventListener(depart, partir);
        setTimeout(partir, 1900);
      } else {
        setTimeout(partir, 0);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', brancher);
  } else {
    brancher();
  }
})();
