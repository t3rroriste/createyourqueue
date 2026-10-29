/* =========================================================================
   Support — l'envoi du formulaire, et le mouvement d'ouverture.
   anime.js v4, chargé en UMD (le site n'a pas d'étape de build) : les
   exports nommés sont donc lus sur le global `anime`.

     contact()  — validation, envoi, états, repli mailto
     discord()  — montrer le bouton OU la note, selon SUPPORT_URL
     entree()   — l'en-tête et les cartes, en UNE timeline

   Ce fichier était une copie de page-modules.js : il révélait des modules
   qui n'existent pas sur cette page, et il ne savait rien du formulaire.
   Il n'était d'ailleurs chargé par personne — support.html appelait
   page-modules.js.

   L'ordre compte. Le FORMULAIRE est câblé en premier, avant tout ce qui
   touche à l'animation, et hors du scope anime.js : si la bibliothèque
   manque ou si le découpage échoue, on doit toujours pouvoir écrire à
   l'équipe. C'est la seule chose que cette page sert à faire.
   ========================================================================= */
(function () {
  'use strict';

  var $  = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function decouvrir() { document.documentElement.classList.remove('motion-pending'); }

  /* Le dictionnaire n'est pas forcément prêt au moment où ce script tourne —
     app.js pose la langue à son propre rythme. On passe donc toujours par
     CYQ.t, jamais par une chaîne écrite ici. */
  function t(cle, vars) {
    return (window.CYQ && window.CYQ.t) ? window.CYQ.t(cle, vars) : cle;
  }

  /* ======================================== 1. le formulaire ============ */

  /* Les mêmes bornes qu'en PHP (site/contact.php) et que dans l'API locale.
     Trois endroits, et c'est volontaire : celui du navigateur rend la main
     tout de suite, celui du serveur est le seul à faire foi. Changer l'un
     oblige à changer les trois — c'est écrit ici pour qu'on s'en souvienne. */
  var BORNES = {
    nom:     { min: 2,  max: 80 },
    email:   { min: 5,  max: 190 },
    sujet:   { min: 2,  max: 120 },
    message: { min: 10, max: 5000 }
  };

  /* Volontairement permissive : le contrôle qui fait foi est
     `filter_var(..., FILTER_VALIDATE_EMAIL)` côté serveur. Refuser ici une
     adresse valide mais inhabituelle serait pire que de laisser passer une
     adresse douteuse, que le serveur renverra de toute façon. */
  var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  /* Les motifs que le serveur renvoie, et la phrase qui leur correspond.
     Un motif inconnu retombe sur sp.eFail : on préfère une phrase vague à
     un code d'erreur affiché tel quel. */
  var MOTIFS = {
    CHAMP_MANQUANT:    'sp.eRequired',
    TROP_COURT:        'sp.eShort',
    TROP_LONG:         'sp.eLong',
    EMAIL_INVALIDE:    'sp.eEmail',
    TROP_DE_DEMANDES:  'sp.eRate',
    ENVOI_IMPOSSIBLE:  'sp.eFail'
  };

  function contact() {
    var form = $('[data-contact]');
    if (!form) return;

    var bouton  = $('[data-contact-send]', form);
    var etatBox = $('[data-contact-state]', form);
    var mailto  = $('[data-contact-mailto]');
    var champs  = {};
    Object.keys(BORNES).forEach(function (n) { champs[n] = form.elements[n]; });

    /* ---------------------------------------------- dire ce qui se passe */

    function etat(code, cle, options) {
      if (!code) {
        etatBox.hidden = true;
        etatBox.removeAttribute('data-etat');
        etatBox.textContent = '';
        return;
      }
      etatBox.hidden = false;
      etatBox.setAttribute('data-etat', code);
      etatBox.textContent = t(cle);
      /* Sur un échec, on tend l'autre chemin : la messagerie de la personne,
         qui ne dépend ni de notre hébergeur ni de notre quota. Le lien est
         ajouté APRÈS le texte, et jamais en le remplaçant : la phrase doit
         rester lisible par un lecteur d'écran même si le lien est ignoré. */
      if (options && options.replier) {
        etatBox.appendChild(document.createTextNode(' '));
        var a = document.createElement('a');
        a.href = lienMailto();
        a.textContent = t('sp.mailto');
        etatBox.appendChild(a);
      }
    }

    /* L'adresse mailto, remplie avec ce qui est déjà saisi. encodeURIComponent
       et non escape : le sujet et le message contiennent des accents, des
       retours à la ligne et des esperluettes, qui casseraient l'URL. */
    function lienMailto() {
      var sujet = (champs.sujet.value || '').trim();
      var corps = (champs.message.value || '').trim();
      var q = [];
      if (sujet) q.push('subject=' + encodeURIComponent('[Support] ' + sujet));
      if (corps) q.push('body=' + encodeURIComponent(corps));
      return 'mailto:contact@cyqbot.eu' + (q.length ? '?' + q.join('&') : '');
    }

    /* Le lien « contact@cyqbot.eu » du bas de carte emmène ce qui est déjà
       tapé : on ne demande pas de tout retaper dans la messagerie. */
    function majMailto() {
      if (mailto) mailto.href = lienMailto();
    }

    /* ------------------------------------------------------ la validation */

    function erreurDe(nom) {
      var v = (champs[nom].value || '').trim();
      var b = BORNES[nom];
      if (!v) return 'sp.eRequired';
      if (nom === 'email' && !EMAIL.test(v)) return 'sp.eEmail';
      if (v.length < b.min) return 'sp.eShort';
      if (v.length > b.max) return 'sp.eLong';
      return null;
    }

    function marquer(nom, cle) {
      var champ = champs[nom];
      var box = $('[data-err-for="' + nom + '"]', form);
      if (cle) {
        champ.setAttribute('aria-invalid', 'true');
        box.textContent = t(cle);
        box.hidden = false;
        /* Le message d'erreur est rattaché au champ : sans aria-describedby,
           un lecteur d'écran annonce « non valide » sans jamais dire
           pourquoi. On garde l'aide déjà décrite, s'il y en a une. */
        var decrit = box.id || (box.id = 'sp-err-' + nom);
        var deja = (champ.getAttribute('aria-describedby') || '')
                     .split(/\s+/).filter(function (x) { return x && x !== decrit; });
        deja.push(decrit);
        champ.setAttribute('aria-describedby', deja.join(' '));
      } else {
        champ.removeAttribute('aria-invalid');
        box.hidden = true;
        box.textContent = '';
        if (box.id) {
          var reste = (champ.getAttribute('aria-describedby') || '')
                        .split(/\s+/).filter(function (x) { return x && x !== box.id; });
          if (reste.length) champ.setAttribute('aria-describedby', reste.join(' '));
          else champ.removeAttribute('aria-describedby');
        }
      }
    }

    /* On ne crie pas pendant la frappe : un champ n'est jugé qu'une fois
       quitté, ou à l'envoi. Mais une erreur déjà affichée disparaît dès
       qu'elle est réparée — sinon elle reste à contredire ce qu'on lit. */
    Object.keys(champs).forEach(function (nom) {
      var champ = champs[nom];
      champ.addEventListener('blur', function () { marquer(nom, erreurDe(nom)); });
      champ.addEventListener('input', function () {
        if (champ.getAttribute('aria-invalid') === 'true' && !erreurDe(nom)) {
          marquer(nom, null);
        }
        majMailto();
      });
    });

    /* ------------------------------------------------------- le compteur */

    var compteur = $('[data-count-for="message"]', form);
    function majCompteur() {
      if (!compteur) return;
      var n = (champs.message.value || '').length;
      var max = BORNES.message.max;
      /* Il n'apparaît qu'au dernier cinquième : avant, il n'apprend rien et
         il attire l'œil pour rien. */
      var pres = n > max * 0.8;
      compteur.textContent = pres ? n + ' / ' + max : '';
      compteur.setAttribute('data-pres', pres ? '1' : '0');
    }
    champs.message.addEventListener('input', majCompteur);
    majCompteur();

    /* ---------------------------------------------------------- l'envoi */

    var enCours = false;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (enCours) return;

      /* Tous les champs sont jugés d'un coup, pas seulement le premier
         fautif : réparer un champ pour découvrir le suivant, puis le
         suivant, est le plus sûr moyen d'abandonner en route. */
      var premier = null;
      Object.keys(champs).forEach(function (nom) {
        var cle = erreurDe(nom);
        marquer(nom, cle);
        if (cle && !premier) premier = champs[nom];
      });
      if (premier) {
        etat('err', 'sp.eForm');
        premier.focus();
        return;
      }

      enCours = true;
      bouton.disabled = true;
      $('span', bouton).textContent = t('sp.sending');
      etat('info', 'sp.sending');

      /* `fetch` en relatif, et NON CYQ.api : celui-ci vise API_BASE, qui est
         l'API du panneau sur dashboard.cyqbot.eu. support.html est une page
         de la vitrine, et cette API ne pose aucun en-tête CORS — l'appel
         serait refusé par le navigateur. contact.php vit donc à côté de
         cette page, sur la même origine. */
      fetch('contact.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({
          nom:     champs.nom.value.trim(),
          email:   champs.email.value.trim(),
          sujet:   champs.sujet.value.trim(),
          message: champs.message.value.trim(),
          site:    (form.elements.site && form.elements.site.value) || '',
          /* La langue de la page, pour savoir dans laquelle répondre. */
          langue:  (window.CYQ && window.CYQ.lang) || ''
        })
      }).then(function (r) {
        if (r.ok) return null;
        /* Le corps porte le motif, et c'est lui qui permet une phrase juste.
           Son absence n'est pas une erreur de plus : la réponse peut être
           vide ou ne pas être du JSON, et le code HTTP suffit alors. */
        return r.json().catch(function () { return null; }).then(function (corps) {
          var e2 = new Error('HTTP_' + r.status);
          e2.motif = (corps && corps.error) || '';
          e2.status = r.status;
          throw e2;
        });
      }).then(function () {
        /* Envoyé : le formulaire est vidé, parce que le laisser rempli donne
           envie d'appuyer une seconde fois. */
        form.reset();
        Object.keys(champs).forEach(function (nom) { marquer(nom, null); });
        majCompteur();
        majMailto();
        etat('ok', 'sp.sent');
      }).catch(function (err) {
        var cle = MOTIFS[err && err.motif] || null;
        /* Pas de motif et pas de statut : la requête n'est jamais partie —
           hors ligne, ou le fichier n'est pas là. C'est le cas où le repli
           par la messagerie est le plus utile, et il faut le dire autrement
           qu'avec « l'envoi a échoué ». */
        if (!cle) cle = (err && err.status) ? 'sp.eFail' : 'sp.eNet';
        etat('err', cle, { replier: true });
      }).then(function () {
        enCours = false;
        bouton.disabled = false;
        $('span', bouton).textContent = t('sp.send');
      });
    });

    /* La langue peut changer pendant qu'on lit la page : les textes posés
       par ce script ne portent pas de data-i18n, donc applyI18n ne les
       reprend pas. On les repose nous-mêmes. */
    document.addEventListener('cyq:lang', function () {
      Object.keys(champs).forEach(function (nom) {
        if (champs[nom].getAttribute('aria-invalid') === 'true') {
          marquer(nom, erreurDe(nom));
        }
      });
      if (!etatBox.hidden) {
        // L'état courant n'est pas mémorisé : on le retire plutôt que de le
        // réafficher dans la mauvaise langue.
        etat(null);
      }
      $('span', bouton).textContent = t(enCours ? 'sp.sending' : 'sp.send');
      majCompteur();
    });

    majMailto();
  }

  /* ==================================== 2. le serveur Discord =========== */

  /* SUPPORT_URL vaut '#' tant qu'on n'a pas renseigné l'invitation. app.js
     laisse alors le href tel quel — un bouton qui ne mène nulle part. On
     montre la note à la place : les écrans affichent leurs états vides
     réels, ils n'inventent pas un lien. */
  function discord() {
    var bouton = $('[data-sp-discord]');
    var note   = $('[data-sp-discord-absent]');
    if (!bouton || !note) return;

    var cfg = window.CYQ_CONFIG || {};
    var pret = !!cfg.SUPPORT_URL && cfg.SUPPORT_URL !== '#';
    bouton.hidden = !pret;
    note.hidden = pret;
  }

  /* ========================================== 3. l'ouverture ============ */

  /* Deux chemins mènent ici — fonts.ready et le minuteur de secours — et le
     premier arrivé gagne. Sans ce drapeau, le second repose les états de
     départ au milieu de l'animation du premier, et tout clignote. */
  var ouverte = false;

  function entree() {
    if (ouverte) return;
    ouverte = true;

    var A = window.anime;
    var nav  = $('[data-nav]');
    var tete = $$('[data-reveal]');
    /* Les cartes de RECOURS seulement. La carte du formulaire ne porte pas
       data-sp-card : elle n'est jamais masquée, pas même une fraction de
       seconde, parce qu'une animation qui ne finit pas la ferait disparaître
       — et avec elle le seul moyen d'écrire à l'équipe. */
    var cartes = $$('[data-sp-card]');

    // Sans la bibliothèque : page statique, mais entière et utilisable.
    if (!A) { decouvrir(); return; }

    var force = document.documentElement.classList.contains('motion-force');
    var calm  = !force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* La courbe signature du site (DESIGN-SYSTEM §5). Passée en FONCTION et
       non en chaîne : anime.js v4 a retiré la syntaxe `ease: 'cubicBezier(…)'`
       du cœur, et elle retombait silencieusement sur l'easing par défaut. */
    var OUT = A.cubicBezier(.16, 1, .3, 1);
    var utils = A.utils;

    utils.set(nav,    { opacity: 0, y: -24 });
    utils.set(tete,   { opacity: 0, y: 14 });
    utils.set(cartes, { opacity: 0, y: 20 });

    // Les états de départ sont posés : plus rien ne peut sauter, on affiche.
    decouvrir();

    if (calm) {
      /* Remettre l'opacité ne suffit pas : il faut défaire les décalages,
         sinon la nav reste 24 px trop haut et les cartes 20 px trop bas, en
         permanence. */
      utils.set(nav,    { opacity: 1, y: 0 });
      utils.set(tete,   { opacity: 1, y: 0 });
      utils.set(cartes, { opacity: 1, y: 0 });
      return;
    }

    /* Une seule timeline, et pas d'observateur : la page tient en un écran
       et demi, les deux cartes de droite sont déjà là quand on arrive.
       Révéler au défilement ce qui est visible au chargement ne révèle
       rien. */
    A.createTimeline({ defaults: { ease: OUT } })
      .add(nav,    { opacity: 1, y: 0, duration: 700 }, 0)
      .add(tete,   { opacity: 1, y: 0, duration: 650, delay: A.stagger(90) }, 160)
      .add(cartes, { opacity: 1, y: 0, duration: 700, delay: A.stagger(110) }, 340);
  }

  /* ========================================= orchestration ============== */

  /* Le formulaire et la carte Discord d'abord, et sans condition : ils ne
     dépendent ni d'anime.js, ni des polices, ni de quoi que ce soit qui
     puisse ne pas arriver. L'animation vient après, et son échec ne coûte
     que l'animation. */
  contact();
  discord();

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () { requestAnimationFrame(entree); });
    // Le filet, si fonts.ready ne résout pas : la page ne reste pas masquée.
    setTimeout(entree, 1500);
  } else {
    requestAnimationFrame(entree);
  }
})();
