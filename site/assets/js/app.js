/* =========================================================================
   CreateYourQueue — cœur du site
   Thème, langues, OAuth, adaptateur d'API, comboboxes, suivi des
   modifications, validation, tiroir mobile, routage des sections.
   Aucune dépendance. Aucune donnée inventée : sans API, les écrans
   affichent leurs états vides.
   ========================================================================= */
(function () {
  'use strict';

  var CFG = window.CYQ_CONFIG || {};
  var DICT = window.CYQ_I18N || {};
  var LANGS = ['fr', 'en', 'es', 'de', 'ko'];

  var CYQ = window.CYQ = {
    lang: CFG.DEFAULT_LANG || 'fr',
    theme: CFG.DEFAULT_THEME || 'dark'
  };

  /* ---------------------------------------------------------------- utils */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  CYQ.esc = esc;

  function store(key, val) {
    try {
      if (val === undefined) return localStorage.getItem('cyq.' + key);
      localStorage.setItem('cyq.' + key, val);
    } catch (e) { /* navigation privée, stockage bloqué : on continue */ }
    return null;
  }

  function icon(name, size) {
    var s = size || 13;
    var p = {
      check:   '<path d="M20 6 9 17l-5-5"/>',
      x:       '<path d="M6 6l12 12M18 6 6 18"/>',
      warn:    '<path d="M12 3 2 20h20L12 3zM12 9v5M12 17.5v.01"/>',
      err:     '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.01"/>',
      info:    '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.01"/>',
      search:  '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
      caret:   '<path d="m6 9 6 6 6-6"/>',
      chevron: '<path d="m9 18 6-6-6-6"/>',
      plus:    '<path d="M12 5v14M5 12h14"/>',
      swap:    '<path d="m8 7 4-4 4 4M8 17l4 4 4-4"/>',
      hash:    '<path d="M5 9h14M5 15h14M10 3 8 21M16 3l-2 18"/>',
      voice:   '<path d="M11 5 6 9H3v6h3l5 4V5zM16 9a4 4 0 0 1 0 6"/>',
      folder:  '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>',
      ext:     '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
      lock:    '<rect x="4" y="10" width="16" height="10" rx="1.5"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
      login:   '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/>',
      sun:     '<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2.5M12 19.5V22M22 12h-2.5M4.5 12H2M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8M18.4 18.4l-1.8-1.8M7.4 7.4 5.6 5.6"/>',
      moon:    '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
      globe:   '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18"/>',
      menu:    '<path d="M4 7h16M4 12h16M4 17h16"/>',
      refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5"/>',
      spin:    '<path d="M12 3a9 9 0 1 0 9 9"/>',
      trash:   '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>',
      save:    '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7M8 20v-6h8v6"/>',
      undo:    '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-4"/>',
      down:    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>'
    }[name] || '';
    return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true" focusable="false"' + (name === 'spin' ? ' class="spin"' : '') + '>' + p + '</svg>';
  }
  CYQ.icon = icon;

  /* ------------------------------------------------------------- traduction */

  function t(key, vars) {
    var table = DICT[CYQ.lang] || DICT.fr || {};
    var s = table[key];
    if (s == null) s = (DICT.fr || {})[key];
    if (s == null) return key;
    if (vars) {
      Object.keys(vars).forEach(function (k) {
        s = s.split('{' + k + '}').join(String(vars[k]));
      });
    }
    return s;
  }
  CYQ.t = t;

  function applyI18n(root) {
    $$('[data-i18n]', root).forEach(function (el) {
      el.textContent = t(el.getAttribute('data-i18n'));
    });
    $$('[data-i18n-attr]', root).forEach(function (el) {
      // format : "aria-label:c.close, title:c.close"
      el.getAttribute('data-i18n-attr').split(',').forEach(function (pair) {
        var bits = pair.split(':');
        if (bits.length === 2) el.setAttribute(bits[0].trim(), t(bits[1].trim()));
      });
    });
  }
  CYQ.applyI18n = applyI18n;

  /* ---- l'adresse porte la langue, sur la vitrine ---------------------
     L'accueil répondait sous « / » et « /index » : deux adresses pour une
     page, et aucune des deux ne disait dans quelle langue on allait la
     lire. Un lien partagé arrivait donc dans la langue du navigateur de
     celui qui l'ouvrait, et non dans celle qu'on avait voulu montrer.

     Seules les pages qui le demandent par `data-lang-url` sont
     concernées — c'est la page qui dit ce qu'elle veut, comme pour les
     fragments de nav, et le script ne tient aucune liste. Les pages du
     panneau ont des adresses qui veulent dire autre chose. */
  function pageAAdresseDeLangue() {
    return document.documentElement.hasAttribute('data-lang-url');
  }

  /* La langue lue dans le chemin : « /fr », et rien d'autre. Deux
     segments, une extension, un sous-dossier : ce n'est pas une adresse
     de langue, on ne devine pas. */
  function langueDeLAdresse() {
    var seg = location.pathname.replace(/^\/+|\/+$/g, '');
    return LANGS.indexOf(seg) !== -1 ? seg : null;
  }

  /* `replaceState` et non `pushState` : changer de langue n'est pas une
     navigation, et le bouton Retour doit ramener d'où l'on vient, pas à
     la version précédente de la même page. La requête et l'ancre
     suivent — « ?motion=on » sert justement à revoir l'ouverture, et il
     serait perdu au premier changement de langue. */
  function poserAdresseDeLangue(code) {
    if (!pageAAdresseDeLangue()) return;
    if (!window.history || !history.replaceState) return;
    var voulu = '/' + code + location.search + location.hash;
    if (location.pathname + location.search + location.hash === voulu) return;
    try { history.replaceState(history.state, '', voulu); }
    catch (e) { /* fichier local (file://), ou origine refusée : l'adresse reste */ }
  }

  /* Le canonique suit la langue affichée. Il est écrit sur /fr dans le
     fichier — il faut bien une valeur quand le script ne tourne pas —
     mais un visiteur qui est passé en espagnol lit la version espagnole,
     et c'est /es qui est l'adresse de ce qu'il a sous les yeux. Les
     `hreflang`, eux, ne bougent pas : ils listent les cinq, toujours. */
  function poserCanonique(code) {
    if (!pageAAdresseDeLangue()) return;
    var lien = document.querySelector('link[rel="canonical"]');
    if (!lien) return;
    var base = (CFG.SITE_ORIGIN || '').replace(/\/+$/, '');
    if (base) lien.setAttribute('href', base + '/' + code);
  }

  function setLang(code, silent) {
    if (LANGS.indexOf(code) === -1) code = 'fr';
    CYQ.lang = code;
    store('lang', code);
    document.documentElement.setAttribute('lang', code);
    applyI18n(document);
    $$('[data-lang-code]').forEach(function (el) { el.textContent = code.toUpperCase(); });
    poserDrapeaux(code);
    $$('[data-lang-pick]').forEach(function (el) {
      var on = String(el.getAttribute('data-lang-pick') === code);
      // menuitemradio se coche, un bouton bascule se presse
      if (el.getAttribute('role') === 'menuitemradio') el.setAttribute('aria-checked', on);
      else el.setAttribute('aria-pressed', on);
    });
    poserAdresseDeLangue(code);
    poserCanonique(code);
    if (!silent) document.dispatchEvent(new CustomEvent('cyq:lang', { detail: code }));
  }
  CYQ.setLang = setLang;

  /* ----------------------------------------------------------------- thème */

  function setTheme(mode) {
    CYQ.theme = mode === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', CYQ.theme);
    store('theme', CYQ.theme);
    $$('[data-theme-toggle]').forEach(function (btn) {
      var toLight = CYQ.theme === 'dark';
      btn.innerHTML = icon(toLight ? 'sun' : 'moon', 14);
      btn.setAttribute('aria-label', t(toLight ? 'c.themeLight' : 'c.themeDark'));
    });
  }
  CYQ.setTheme = setTheme;

  /* ---------------------------------------------------------------- Discord */

  function oauthBase() { return 'https://discord.com/oauth2/authorize'; }

  /* ------------------------------------------------- les deux domaines --
     La vitrine (cyqbot.eu) et l'application (dashboard.cyqbot.eu) sont
     deux origines distinctes. Un lien relatif ne traverse pas : écrit sur
     la vitrine, « login.html » chercherait cyqbot.eu/login.html, qui n'y
     est plus.

     Ces deux fonctions rendent un lien ABSOLU quand la page visée vit sur
     l'autre domaine, et le laissent RELATIF sinon — donc en local, où les
     deux origines de config.js sont vides, rien ne change et le site se
     teste comme un dossier unique.                                       */

  /* La scission ne vaut que sur les VRAIS domaines. Ouvert depuis un
     dossier local, un serveur de test ou une adresse IP, le site est un
     seul dossier : on garde les liens relatifs, sinon un clic en local
     renverrait le testeur sur le site en production. */
  /* STATUS_ORIGIN depuis le 29 octobre : le sous-domaine d'état est un
     TROISIÈME vrai domaine. Sans lui dans cette liste, la page d'état
     était traitée comme un dossier de test, ses liens restaient relatifs,
     et « Documentation » y cherchait status.cyqbot.eu/guide. */
  function surUnDesDeuxDomaines() {
    var ici = window.location.origin;
    return (CFG.SITE_ORIGIN   && ici === CFG.SITE_ORIGIN) ||
           (CFG.APP_ORIGIN    && ici === CFG.APP_ORIGIN) ||
           (CFG.STATUS_ORIGIN && ici === CFG.STATUS_ORIGIN);
  }

  /* Le nom du dossier qui porte l'application dans le dépôt, déduit du
     sous-domaine lui-même : live/dashboard.cyqbot.eu/. Un seul endroit où
     cette correspondance est écrite. */
  function dossierApp() {
    if (!CFG.APP_ORIGIN) return '';
    return CFG.APP_ORIGIN.replace(/^[a-z]+:\/\//i, '').replace(/[:/].*$/, '');
  }

  function versOrigine(origine, page) {
    if (!origine) return page;
    page = String(page).replace(/^\/+/, '');

    if (surUnDesDeuxDomaines()) {
      // Déjà du bon côté : un lien relatif est plus court et survit à un
      // changement de domaine.
      if (window.location.origin === origine) return page;
      return origine + '/' + page;
    }

    /* Hors des vrais domaines — dossier local, serveur de test, adresse IP.
       On ne part surtout pas en absolu : un clic renverrait le testeur sur
       la production. On reproduit la DISPOSITION DES DOSSIERS du dépôt, où
       l'application occupe un sous-dossier de la vitrine. Le dossier
       complet se teste donc d'un bloc, liens croisés compris. */
    var dossier = dossierApp();
    if (!dossier) return page;
    var dansApp = window.location.pathname.indexOf('/' + dossier + '/') !== -1;
    var versApp = (origine === CFG.APP_ORIGIN);
    if (versApp === dansApp) return page;
    return versApp ? dossier + '/' + page : '../' + page;
  }

  /* « index » n'est plus une adresse : l'accueil s'atteint par sa langue.
     La traduction se fait ICI, dans le seul endroit qui fabrique les liens
     vers la vitrine, plutôt que dans chaque page — sinon le jour où une
     langue s'ajoute il faut repasser sur sept fichiers.

     La valeur reste « index » dans le HTML : c'est le nom de la page, et
     il ne change pas quand on change de langue. Seul le lien change. */
  function pageVitrine(page) {
    return page === 'index' ? (CYQ.lang || CFG.DEFAULT_LANG || 'fr') : page;
  }

  CYQ.siteUrl = function (page) { return versOrigine(CFG.SITE_ORIGIN, pageVitrine(page)); };
  CYQ.appUrl  = function (page) { return versOrigine(CFG.APP_ORIGIN,  page); };

  /* Tous les « Se connecter » du site mènent au MÊME écran, login.html :
     c'est lui qui explique ce qui va être demandé, montre le logo Discord,
     puis enchaîne sur l'invitation du bot. Depuis la scission, cet écran
     est sur le sous-domaine, et le lien part donc en absolu depuis la
     vitrine. */
  CYQ.loginUrl = function () { return CYQ.appUrl('login.html'); };

  /* Le point d'entrée côté serveur, quand il existe. C'est LUI qui tire le
     state et garde le CLIENT_SECRET ; le site ne fait que suivre. */
  CYQ.apiLoginUrl = function () {
    if (!CFG.API_BASE) return null;
    return CFG.API_BASE.replace(/\/$/, '') + '/auth/login';
  };

  /* Le départ vers Discord sans back-end (flux implicite). Le jeton revient
     dans le fragment de l'URL, que le navigateur n'envoie à personne. Ce
     n'est utilisable que parce que le site est statique : dès qu'une API
     existe, apiLoginUrl() reprend la main.
     Le state est fourni par l'appelant, qui doit le retrouver au retour. */
  CYQ.discordAuthUrl = function (state) {
    if (!CFG.CLIENT_ID) return null;
    var retour = CFG.OAUTH_REDIRECT_URI ||
      (window.location.origin + window.location.pathname.replace(/[^/]*$/, '') + 'login.html');
    return oauthBase() +
      '?client_id=' + encodeURIComponent(CFG.CLIENT_ID) +
      '&response_type=token' +
      '&redirect_uri=' + encodeURIComponent(retour) +
      '&scope=' + encodeURIComponent('identify guilds') +
      (state ? '&state=' + encodeURIComponent(state) : '');
  };

  CYQ.inviteUrl = function (guildId) {
    if (!CFG.CLIENT_ID) return null;
    return oauthBase() +
      '?client_id=' + encodeURIComponent(CFG.CLIENT_ID) +
      '&permissions=' + encodeURIComponent(CFG.INVITE_PERMISSIONS || '0') +
      '&scope=' + encodeURIComponent('bot applications.commands') +
      (guildId ? '&guild_id=' + encodeURIComponent(guildId) + '&disable_guild_select=true' : '');
  };

  /* -------------------------------------------------------------- API ------
     Sans API_BASE, get() rejette avec {code:'NO_API'} et les pages
     affichent leur état vide plutôt que d'inventer des données.          */

  function NoApi() { var e = new Error('NO_API'); e.code = 'NO_API'; return e; }

  CYQ.api = {
    get configured() { return !!CFG.API_BASE; },

    request: function (path, opts) {
      if (!CFG.API_BASE) return Promise.reject(NoApi());
      opts = opts || {};
      var headers = { 'Accept': 'application/json' };
      if (opts.body) headers['Content-Type'] = 'application/json';
      return fetch(CFG.API_BASE.replace(/\/$/, '') + path, {
        method: opts.method || 'GET',
        headers: headers,
        credentials: 'include',
        body: opts.body ? JSON.stringify(opts.body) : undefined
      }).then(function (r) {
        /* Le corps d'une réponse réussie n'est pas forcément du JSON : un
           avertissement PHP imprimé avant la charge, une page d'erreur
           glissée par un cache ou un proxy, et `r.json()` rejette avec une
           SyntaxError — un objet sans `.code` ni `.status`, que l'appelant
           range donc dans « erreur inconnue » et annonce comme « l'API n'a
           pas répondu ». Elle avait répondu, et c'est le genre de phrase
           qui envoie chercher une panne ailleurs pendant une heure. On
           nomme donc le cas. */
        if (r.ok) {
          if (r.status === 204) return null;
          return r.json().catch(function () {
            var e = new Error('BAD_JSON');
            e.code = 'BAD_JSON';
            e.status = r.status;
            throw e;
          });
        }
        /* Le corps d'une erreur porte souvent le MOTIF ({"error":"…"}), et
           c'est lui qui permet une phrase juste plutôt qu'un « erreur ».
           On le lit donc avant de rejeter, et son absence n'est pas une
           erreur de plus : la réponse peut être vide ou ne pas être du
           JSON, et le code HTTP suffit alors. */
        return r.json().catch(function () { return null; }).then(function (corps) {
          var e = new Error(r.status === 401 ? 'UNAUTHORIZED'
                          : r.status === 409 ? 'CONFLICT' : 'HTTP_' + r.status);
          e.code = r.status === 401 ? 'UNAUTHORIZED'
                 : r.status === 409 ? 'CONFLICT' : 'HTTP';
          e.status = r.status;
          e.motif = (corps && corps.error) || '';
          throw e;
        });
      });
    },
    get:   function (p) { return CYQ.api.request(p); },
    patch: function (p, b) { return CYQ.api.request(p, { method: 'PATCH', body: b }); },
    post:  function (p, b) { return CYQ.api.request(p, { method: 'POST', body: b }); }
  };

  /* ----------------------------------------------------- la barre fixe --
     Elle est haute de 60 px et reste au-dessus de tout : sur une page
     qu'on parcourt, c'est 60 px de moins pour lire. Elle part donc dès
     qu'on descend, et ne revient QU'EN HAUT — pas au premier mouvement
     vers le haut, sinon elle clignote à chaque correction de trajectoire
     sur un pavé tactile.

     Ici plutôt que dans une page : c'est la même barre partout, de
     l'accueil au panneau. Seul `transform` est animé. */

  (function barreQuiSEfface() {
    var nav = $('[data-nav]');
    if (!nav) return;

    // 8 px : en deçà, c'est le rebond d'un clic sur une ancre, pas un
    // geste de lecture.
    var SEUIL = 8;

    /* anime.js laisse son animation d'ouverture OUVERTE sur la barre, et
       une animation l'emporte sur une règle CSS, `!important` compris :
       tant qu'elle vit, la barre refuse de bouger. On la retire au premier
       défilement — à ce moment l'ouverture est jouée depuis longtemps —
       puis on efface les styles en ligne qu'elle avait posés, sans quoi
       l'état de DÉPART (invisible, remontée) reprendrait la main. */
    /* À CHAQUE passage, et non une fois pour toutes : anime.js recrée ses
       animations derrière nous, et une animation l'emporte sur un style en
       ligne comme sur une règle. Sans ce ménage, la barre refusait de
       revenir. Le coût est nul quand il n'y en a pas. */
    /* On n'annule QUE les animations d'anime.js. `getAnimations()` rend
       aussi la CSSTransition que la règle `.nav { transition: transform … }`
       vient de créer : l'annuler à chaque événement de défilement tuait la
       transition de sortie à l'image suivante, et la barre SAUTAIT en
       partant. Au retour en haut, le dernier événement n'était suivi de
       rien, plus personne n'annulait, et la transition se jouait — d'où
       l'asymétrie exacte qu'on observait.

       Le garde sur `CSSTransition` n'est pas de la prudence gratuite :
       l'interface n'est pas exposée partout, et la lire sans vérifier
       ferait tomber tout l'effacement sur ces navigateurs-là. */
    function liberer() {
      if (!nav.getAnimations) return;
      nav.getAnimations().forEach(function (a) {
        if (typeof CSSTransition === 'undefined' || !(a instanceof CSSTransition)) a.cancel();
      });
    }

    /* On écrit le mouvement EN LIGNE, et non par la classe : anime.js a
       posé ses propres styles en ligne sur la barre, et un style en ligne
       ne se laisse pas effacer par une règle. En écrivant au même endroit
       que lui, on est sûr d'avoir le dernier mot. La classe reste pour le
       reste — les clics qui traversent, la transition. */
    var CACHEE = 'translate3d(0, calc(-100% - var(--gutter) - 24px), 0)';

    /* Sans requestAnimationFrame : le navigateur le suspend sur un onglet
       en arrière-plan, et la barre restait cachée au retour en haut. Lire
       `pageYOffset` dans un écouteur passif ne coûte rien, et
       `classList.toggle` ne réécrit pas une classe déjà en place. */
    /* L'état courant, et le seul. Un défilement émet des dizaines
       d'événements d'affilée ; sans cette mémoire, chacun réécrivait le
       même `transform`, la même opacité et la même classe. C'était des
       dizaines d'écritures de style par seconde pour un état qui ne
       changeait pas — et, surtout, autant d'occasions de couper la
       transition en cours. `null` et non `false` : au premier passage,
       aucun état n'a encore été posé, et il faut l'écrire même s'il se
       trouve être « visible ». */
    var cachee = null;

    function placer() {
      var cacher = window.pageYOffset > SEUIL;
      if (cacher === cachee) return;
      cachee = cacher;
      liberer();
      nav.style.transform = cacher ? CACHEE : 'none';
      nav.style.opacity = cacher ? '0' : '1';
      nav.classList.toggle('is-hidden', cacher);
    }

    addEventListener('scroll', placer, { passive: true });

    /* Pas au chargement : l'ouverture de la page anime justement cette
       barre, et la libérer tout de suite couperait l'animation. Le premier
       défilement s'en chargera. */
    if (window.pageYOffset > SEUIL) placer();
  })();

  /* ------------------------------------------------------------- combobox --
     <div class="combo" data-combo data-source="channels">
       <input type="hidden" name="..."><button class="combo__button">…</button>
     </div>
     Les options viennent de CYQ.data.channels / .roles, chargées par la page. */

  function buildCombo(combo) {
    var srcName = combo.getAttribute('data-source') || 'channels';
    var hidden = $('input[type="hidden"]', combo);
    var button = $('.combo__button', combo);
    if (!button) return;

    var panel = document.createElement('div');
    panel.className = 'combo__panel';
    panel.innerHTML =
      '<div class="combo__search">' + icon('search', 13) +
        '<input type="search" autocomplete="off" aria-label="' + esc(t('c.search')) + '"' +
          ' placeholder="' + esc(t('c.searchPlaceholder')) + '">' +
        '<span class="combo__count"></span></div>' +
      '<div class="combo__list" role="listbox"></div>';
    combo.appendChild(panel);

    var input = $('input[type="search"]', panel);
    var list  = $('.combo__list', panel);
    var count = $('.combo__count', panel);
    var active = -1;
    var shown = [];

    function all() { return ((CYQ.data && CYQ.data[srcName]) || []); }

    /* Le pliage de comparaison : minuscules ET sans accents. Les salons
       Discord sont pleins de « ・arrivé », « annoncé-jeux » ; chercher
       « arrive » doit les trouver, sinon le champ a l'air cassé. */
    function plie(v) {
      v = String(v == null ? '' : v).toLowerCase();
      try { return v.normalize('NFD').replace(/[̀-ͯ]/g, ''); }
      catch (e) { return v; }
    }

    function render() {
      var q = plie(input.value.trim());
      var items = all().filter(function (o) {
        return !q || plie(o.name).indexOf(q) !== -1;
      });
      shown = items;
      /* Le compteur « 7/16 » porte seul l'information du filtre : il dit
         combien de salons restent ET combien il y en a. Le pied qui
         répétait « 9 masqués » disait donc la même chose une seconde fois,
         plus bas, dans une zone qu'on ne regarde pas. */
      count.textContent = items.length + '/' + all().length;

      if (!all().length) {
        list.innerHTML = '<div class="combo__empty"><p class="hint">' +
          esc(CYQ.api.configured ? t('c.loading') : t('d.noApi')) + '</p></div>';
        return;
      }
      if (!items.length) {
        list.innerHTML = '<div class="combo__empty"><div class="combo__empty-title">' +
          esc(t('ch.noMatch')) + '</div><p class="hint">' + esc(t('ch.noMatchBody')) + '</p></div>';
        return;
      }

      var html = '', lastCat = null;

      /* Se dédire. Sans cette entrée, un salon choisi par erreur ne peut
         plus être retiré : toutes les options en posent un autre, aucune
         n'en enlève.
         Elle n'apparaît que s'il y a quelque chose à annuler, et jamais
         pendant une recherche — on tape le nom d'un salon qu'on veut, pas
         d'un vide qu'on cherche. */
      if (hidden && hidden.value && !q) {
        html += '<button type="button" role="option" class="combo__opt combo__opt--none"' +
          ' data-id="" aria-selected="false">' +
          '<span class="combo__value">' + esc(t('ch.none')) + '</span></button>';
      }

      items.forEach(function (o, i) {
        if (o.category && o.category !== lastCat) {
          lastCat = o.category;
          html += '<div class="combo__cat">' + esc(o.category) + '</div>';
        }
        var label = esc(o.name);
        if (q) {
          var idx = plie(o.name).indexOf(q);
          if (idx !== -1) {
            label = esc(o.name.slice(0, idx)) + '<mark>' + esc(o.name.slice(idx, idx + q.length)) +
                    '</mark>' + esc(o.name.slice(idx + q.length));
          }
        }
        var selected = hidden && hidden.value === String(o.id);
        html += '<button type="button" role="option" class="combo__opt" data-i="' + i + '"' +
          ' data-id="' + esc(o.id) + '" aria-selected="' + (selected ? 'true' : 'false') + '"' +
          (o.disabled ? ' disabled' : '') + '>' +
          (o.type === 'voice' ? icon('voice', 12) : o.type === 'category' ? icon('folder', 12) :
            '<span class="hash">#</span>') +
          '<span class="combo__value">' + label + '</span>' +
          (o.disabled ? '<span class="tag tag--warn tag--sm">' +
            icon('warn', 10) + esc(t('ch.writeDenied')) + '</span>' : '') +
          (selected ? '<span class="tick">' + icon('check', 12) + '</span>' : '') +
          '</button>';
      });
      list.innerHTML = html;
    }

    function open() {
      combo.setAttribute('data-open', 'true');
      button.setAttribute('aria-expanded', 'true');
      render();
      input.value = '';
      input.focus();
      render();
    }
    function close(focusBack) {
      combo.removeAttribute('data-open');
      button.setAttribute('aria-expanded', 'false');
      active = -1;
      if (focusBack) button.focus();
    }
    function choose(opt) {
      if (!opt || opt.disabled) return;
      var id = opt.getAttribute('data-id');

      /* L'entrée « aucun ». On vide, et on laisse la page repeindre le
         bouton : elle seule connaît le texte d'attente à remettre, qui
         diffère pour un salon, une catégorie ou un rôle. */
      if (id === '') {
        if (hidden) hidden.value = '';
        button.classList.remove('is-error');
        close(true);
        combo.dispatchEvent(new CustomEvent('cyq:change', { bubbles: true, detail: null }));
        return;
      }

      var o = all().filter(function (x) { return String(x.id) === id; })[0];
      if (!o) return;
      if (hidden) { hidden.value = o.id; }
      button.classList.remove('is-error');
      button.innerHTML =
        (o.type === 'voice' ? icon('voice', 12) : o.type === 'category' ? icon('folder', 12) :
          '<span class="combo__sigil">#</span>') +
        '<span class="combo__value">' + esc(o.name) + '</span>' +
        '<span class="caret">' + icon('caret', 12) + '</span>';
      close(true);
      combo.dispatchEvent(new CustomEvent('cyq:change', { bubbles: true, detail: o }));
    }

    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', function () {
      combo.getAttribute('data-open') ? close(true) : open();
    });
    input.addEventListener('input', function () { active = -1; render(); });
    list.addEventListener('click', function (e) {
      var opt = e.target.closest('.combo__opt');
      if (opt) choose(opt);
    });
    panel.addEventListener('keydown', function (e) {
      var opts = $$('.combo__opt:not([disabled])', list);
      if (e.key === 'Escape') { e.preventDefault(); close(true); }
      else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!opts.length) return;
        active = e.key === 'ArrowDown'
          ? Math.min(opts.length - 1, active + 1)
          : Math.max(0, active - 1);
        opts.forEach(function (o) { o.classList.remove('is-active'); });
        opts[active].classList.add('is-active');
        opts[active].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        choose(opts[active] || opts[0]);
      }
    });
    document.addEventListener('click', function (e) {
      if (!combo.contains(e.target)) close(false);
    });

    combo._cyqRender = render;
  }

  CYQ.initCombos = function (root) {
    $$('[data-combo]', root).forEach(function (c) {
      if (!c._cyqRender) buildCombo(c);
    });
  };
  CYQ.refreshCombos = function () {
    $$('[data-combo]').forEach(function (c) { if (c._cyqRender) c._cyqRender(); });
  };

  /* -------------------------------------------------------- interrupteurs */

  function wireSwitches(root) {
    $$('.switch input[type="checkbox"]', root).forEach(function (cb) {
      var label = cb.closest('.switch');
      var state = $('.state', label);
      function paint() {
        if (state) state.textContent = t(cb.disabled ? 'c.inactive' : cb.checked ? 'c.enabled' : 'c.disabled');
        // dépendances : data-controls="sel1,sel2"
        var ctl = cb.getAttribute('data-controls');
        if (ctl) {
          ctl.split(',').forEach(function (sel) {
            $$(sel.trim()).forEach(function (row) {
              row.classList.toggle('is-locked', !cb.checked);
              $$('input,select,button', row).forEach(function (f) { f.disabled = !cb.checked; });
              var note = $('[data-locked-note]', row);
              if (note) {
                note.hidden = cb.checked;
                note.textContent = t('mm.lockedBy', { name: cb.getAttribute('data-name') || '' });
              }
            });
          });
        }
      }
      cb.addEventListener('change', paint);
      document.addEventListener('cyq:lang', paint);
      paint();
    });
  }

  /* --------------------------------------------------------- segmentés ---- */

  function wireSegmented(root) {
    $$('.segmented', root).forEach(function (seg) {
      seg.addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b) return;
        $$('button', seg).forEach(function (x) { x.setAttribute('aria-pressed', 'false'); });
        b.setAttribute('aria-pressed', 'true');
        var hidden = $('input[type="hidden"]', seg.parentNode);
        if (hidden) hidden.value = b.textContent.trim();
        seg.dispatchEvent(new CustomEvent('cyq:change', { bubbles: true }));
      });
    });
  }

  /* ------------------------------------------------------- validation ----- */

  function validateField(f) {
    var wrap = f.closest('.row') || f.parentNode;
    var holder = wrap.querySelector('[data-error-for="' + f.id + '"]');
    var min = f.getAttribute('data-min'), max = f.getAttribute('data-max');
    var msg = '';
    var raw = f.value.trim();

    if (f.type === 'number' && raw !== '') {
      if (!/^-?\d+$/.test(raw)) msg = t('mm.errNum');
      else if (max !== null && max !== undefined && Number(raw) > Number(max)) msg = t('mm.errMax', { max: max });
      else if (min !== null && min !== undefined && Number(raw) < Number(min)) msg = t('mm.errMin', { min: min });
    }

    var was = f.getAttribute('aria-invalid');
    f.setAttribute('aria-invalid', msg ? 'true' : 'false');
    if (holder) {
      holder.innerHTML = msg ? icon('err', 13) + '<span>' + esc(msg) + '</span>' : '';
      holder.hidden = !msg;
    }
    // La barre d'enregistrement doit se repeindre : l'état de validité vient
    // de changer après le « change » qui l'avait déjà mise à jour.
    if (was !== f.getAttribute('aria-invalid')) {
      f.dispatchEvent(new CustomEvent('cyq:change', { bubbles: true }));
    }
    return !msg;
  }

  function wireValidation(root) {
    $$('input[data-min],input[data-max]', root).forEach(function (f) {
      f.addEventListener('blur', function () { validateField(f); });
      f.addEventListener('input', function () {
        // on ne crie pas pendant la frappe, mais on lève l'erreur dès qu'elle
        // est corrigée, et on la signale si la valeur sort franchement des bornes
        if (f.getAttribute('aria-invalid') === 'true') validateField(f);
      });
      f.addEventListener('change', function () { validateField(f); });
    });
  }

  /* --------------------------------------------- suivi des modifications -- */

  function fieldValue(f) {
    if (f.type === 'checkbox') return f.checked ? '1' : '0';
    return f.value;
  }

  function initSection(section) {
    if (section._cyqInit) return;
    section._cyqInit = true;
    var fields = $$('[data-setting]', section);
    var bar = $('.savebar', section);
    if (!bar) return;

    var initial = {};
    fields.forEach(function (f) { initial[f.getAttribute('data-setting')] = fieldValue(f); });

    var textEl   = $('.savebar__text', bar);
    var detailEl = $('.savebar__detail', bar);
    var saveBtn  = $('[data-save]', bar);
    var cancelBtn = $('[data-cancel]', bar);

    function changed() {
      return fields.filter(function (f) {
        return initial[f.getAttribute('data-setting')] !== fieldValue(f);
      });
    }
    function invalid() {
      return fields.filter(function (f) { return f.getAttribute('aria-invalid') === 'true'; });
    }

    function paint() {
      var ch = changed(), bad = invalid();
      bar.hidden = ch.length === 0;
      bar.classList.remove('savebar--ok');
      bar.classList.toggle('savebar--err', bad.length > 0);
      if (!ch.length) return;
      if (bad.length) {
        textEl.textContent = t('st.fixBeforeSave');
      } else {
        textEl.textContent = ch.length === 1 ? t('c.change') : t('c.sectionChanges', { n: ch.length });
      }
      if (detailEl) {
        detailEl.textContent = ch.map(function (f) {
          return f.getAttribute('data-label') || f.getAttribute('data-setting');
        }).slice(0, 4).join(' · ');
      }
      if (saveBtn) saveBtn.disabled = bad.length > 0;
      section.dispatchEvent(new CustomEvent('cyq:dirty', { bubbles: true, detail: ch.length }));
    }

    fields.forEach(function (f) {
      ['input', 'change'].forEach(function (ev) { f.addEventListener(ev, paint); });
    });
    section.addEventListener('cyq:change', paint);
    document.addEventListener('cyq:lang', paint);

    if (cancelBtn) cancelBtn.addEventListener('click', function () {
      fields.forEach(function (f) {
        var v = initial[f.getAttribute('data-setting')];
        if (f.type === 'checkbox') { f.checked = v === '1'; }
        else { f.value = v; }
        f.setAttribute('aria-invalid', 'false');
        f.dispatchEvent(new Event('change', { bubbles: true }));
      });
      paint();
    });

    if (saveBtn) saveBtn.addEventListener('click', function () {
      var payload = {};
      changed().forEach(function (f) { payload[f.getAttribute('data-setting')] = fieldValue(f); });

      saveBtn.disabled = true;
      var restore = saveBtn.innerHTML;
      saveBtn.innerHTML = icon('spin', 13) + '<span>' + esc(t('c.saving')) + '</span>';
      bar.setAttribute('aria-busy', 'true');

      var gid = document.body.getAttribute('data-guild') || '';
      CYQ.api.patch('/guilds/' + gid + '/settings', payload).then(function () {
        fields.forEach(function (f) { initial[f.getAttribute('data-setting')] = fieldValue(f); });
        bar.removeAttribute('aria-busy');
        bar.classList.remove('savebar--err');
        bar.classList.add('savebar--ok');
        bar.innerHTML = icon('check', 14) +
          '<span class="savebar__text--ok">' + esc(t('c.saved')) + '</span>' +
          '<span class="savebar__detail">' + esc(new Date().toLocaleTimeString(CYQ.lang)) + '</span>';
        setTimeout(function () { location.reload(); }, 3500);
      }).catch(function (err) {
        bar.removeAttribute('aria-busy');
        saveBtn.innerHTML = restore;
        saveBtn.disabled = false;
        bar.classList.add('savebar--err');
        textEl.textContent = err.code === 'NO_API' ? t('d.noApi') : t('st.saveFailTitle');
        if (detailEl) detailEl.textContent = err.code === 'NO_API' ? t('d.noApiBody') : t('st.saveFailBody');
      });
    });

    paint();
  }

  /* Les rangées fabriquées APRÈS le chargement — la liste de l'anti-lien,
     un salon par rangée — ont besoin du même câblage que les autres : sans
     lui, l'interrupteur bascule mais n'écrit pas son état à côté, et ses
     dépendances ne se verrouillent pas. */
  CYQ.wireSwitches = wireSwitches;

  CYQ.initSections = function (root) {
    $$('[data-section]', root).forEach(initSection);
  };

  /* --------------------------------------------------- menu de langue ---- */

  /* ------------------------------------------------------------ drapeaux --
     Des SVG et pas des emoji. Windows n'a pas les glyphes de drapeaux dans
     Segoe UI Emoji : un emoji drapeau y rend « FR », « GB »... soit
     exactement ce qu'on cherche a remplacer. Ronds, taille fixe, aucun
     fichier a charger.                                                     */

  var DRAPEAUX = {
    fr: '<rect width="20" height="20" fill="#fff"/>' +
        '<rect width="6.67" height="20" fill="#0055A4"/>' +
        '<rect x="13.33" width="6.67" height="20" fill="#EF4135"/>',

    en: '<rect width="20" height="20" fill="#012169"/>' +
        '<path d="M0 0 20 20M20 0 0 20" stroke="#fff" stroke-width="4.5"/>' +
        '<path d="M0 0 20 20M20 0 0 20" stroke="#C8102E" stroke-width="2"/>' +
        '<path d="M10 0V20M0 10H20" stroke="#fff" stroke-width="6.5"/>' +
        '<path d="M10 0V20M0 10H20" stroke="#C8102E" stroke-width="3.8"/>',

    es: '<rect width="20" height="20" fill="#AA151B"/>' +
        '<rect y="5" width="20" height="10" fill="#F1BF00"/>',

    de: '<rect width="20" height="20" fill="#000"/>' +
        '<rect y="6.67" width="20" height="6.67" fill="#DD0000"/>' +
        '<rect y="13.33" width="20" height="6.67" fill="#FFCE00"/>',

    /* Le taegeuk seul, sans les quatre trigrammes : a 18 px ils tournent a
       la bouillie de pixels et salissent la pastille. Le symbole central
       suffit largement a identifier le drapeau. */
    ko: '<rect width="20" height="20" fill="#fff"/>' +
        '<g transform="rotate(-33 10 10)">' +
        '<path d="M5.5 10A2.25 2.25 0 0 1 10 10A2.25 2.25 0 0 0 14.5 10A4.5 4.5 0 0 0 5.5 10Z" fill="#CD2E3A"/>' +
        '<path d="M5.5 10A2.25 2.25 0 0 0 10 10A2.25 2.25 0 0 1 14.5 10A4.5 4.5 0 0 1 5.5 10Z" fill="#0047A0"/>' +
        '</g>'
  };

  /* Un identifiant de clip par langue : plusieurs <svg> dans la meme page
     ne peuvent pas partager le meme id sans que le premier gagne. */
  CYQ.drapeau = function (code) {
    var d = DRAPEAUX[code];
    if (!d) return '';
    var id = 'cyqflag-' + code;
    return '<svg class="flag" viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">' +
             '<defs><clipPath id="' + id + '"><circle cx="10" cy="10" r="10"/></clipPath></defs>' +
             '<g clip-path="url(#' + id + ')">' + d + '</g>' +
             '<circle cx="10" cy="10" r="9.5" fill="none" stroke="rgba(0,0,0,.28)"/>' +
           '</svg>';
  };

  /* Idempotent : appele a l'init ET a chaque changement de langue, il ne
     doit jamais empiler deux pastilles sur le meme bouton. */
  /* Un drapeau posé une fois pour toutes, hors du menu de langue : porter
     `data-flag="fr"` suffit. Le dessin reste celui de DRAPEAUX, donc il n'y a
     jamais deux versions d'un même drapeau dans le site. */
  function poserDrapeauxFixes(root) {
    $$('[data-flag]', root || document).forEach(function (el) {
      if (el.firstElementChild) return;
      el.innerHTML = CYQ.drapeau(el.getAttribute('data-flag'));
    });
  }
  CYQ.poserDrapeauxFixes = poserDrapeauxFixes;

  function poserDrapeaux(code) {
    $$('[data-lang-pick]').forEach(function (el) {
      var lg = el.getAttribute('data-lang-pick');
      var d = $('.flag', el);
      if (d) { if (d.getAttribute('data-lg') === lg) return; d.remove(); }
      el.insertAdjacentHTML('afterbegin', CYQ.drapeau(lg));
      var neuf = $('.flag', el);
      if (neuf) neuf.setAttribute('data-lg', lg);
    });
    $$('[data-lang-menu]').forEach(function (btn) {
      var d = $('.flag', btn);
      if (d) { if (d.getAttribute('data-lg') === code) return; d.remove(); }
      btn.insertAdjacentHTML('afterbegin', CYQ.drapeau(code));
      var neuf = $('.flag', btn);
      if (neuf) neuf.setAttribute('data-lg', code);
    });
  }

  function wireLangMenu() {
    $$('[data-lang-menu]').forEach(function (btn) {
      var wrap = btn.closest('.langmenu');
      if (!wrap || wrap._cyqMenu) return;
      wrap._cyqMenu = true;
      var panel = $('.langmenu__panel', wrap);
      if (!panel) return;

      function opts() { return $$('.langmenu__opt', panel); }
      function open() {
        wrap.setAttribute('data-open', 'true');
        btn.setAttribute('aria-expanded', 'true');
        var cur = $('.langmenu__opt[aria-checked="true"]', panel) || opts()[0];
        if (cur) cur.focus();
      }
      function close(back) {
        wrap.removeAttribute('data-open');
        btn.setAttribute('aria-expanded', 'false');
        if (back) btn.focus();
      }

      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        wrap.getAttribute('data-open') ? close(true) : open();
      });
      btn.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); open(); }
      });
      panel.addEventListener('keydown', function (e) {
        var list = opts(), i = list.indexOf(document.activeElement);
        if (e.key === 'Escape') { e.preventDefault(); close(true); }
        else if (e.key === 'ArrowDown') { e.preventDefault(); list[Math.min(list.length - 1, i + 1)].focus(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); list[Math.max(0, i - 1)].focus(); }
        else if (e.key === 'Home') { e.preventDefault(); list[0].focus(); }
        else if (e.key === 'End') { e.preventDefault(); list[list.length - 1].focus(); }
        else if (e.key === 'Tab') { close(false); }
      });
      panel.addEventListener('click', function (e) {
        if (e.target.closest('.langmenu__opt')) close(true);
      });
      document.addEventListener('click', function (e) {
        if (!wrap.contains(e.target)) close(false);
      });
    });
  }

  /* -------------------------------------------------------- tiroir mobile */

  function wireDrawer() {
    var btn = $('[data-drawer-open]');
    var scrim = $('.scrim');
    if (!btn) return;
    function open() {
      document.body.classList.add('drawer-open');
      btn.setAttribute('aria-expanded', 'true');
      var first = $('.side .navlink');
      if (first) first.focus();
    }
    function close() {
      // Ne rend le focus au bouton que si le tiroir était bien ouvert :
      // sinon un simple changement de section volerait le focus au chargement.
      var wasOpen = document.body.classList.contains('drawer-open');
      document.body.classList.remove('drawer-open');
      btn.setAttribute('aria-expanded', 'false');
      if (wasOpen) btn.focus();
    }
    btn.addEventListener('click', function () {
      document.body.classList.contains('drawer-open') ? close() : open();
    });
    if (scrim) scrim.addEventListener('click', close);
    $$('[data-drawer-close]').forEach(function (b) { b.addEventListener('click', close); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && document.body.classList.contains('drawer-open')) close();
    });
    CYQ.closeDrawer = close;
  }

  /* ------------------------------------------------- routage des sections */

  function wireRouter() {
    var sections = $$('[data-section]');
    if (!sections.length) return;
    var links = $$('.navlink[data-goto]');

    function show(id, push, moveFocus) {
      var found = false;
      sections.forEach(function (s) {
        var match = s.getAttribute('data-section') === id;
        s.hidden = !match;
        if (match) found = true;
      });
      if (!found) return show(sections[0].getAttribute('data-section'), push, moveFocus);

      links.forEach(function (l) {
        var on = l.getAttribute('data-goto') === id;
        if (on) l.setAttribute('aria-current', 'page');
        else l.removeAttribute('aria-current');
      });

      var cur = $('[data-crumb-current]');
      var active = links.filter(function (l) { return l.getAttribute('data-goto') === id; })[0];
      if (cur && active) cur.textContent = $('.navlink-label', active)
        ? $('.navlink-label', active).textContent : active.textContent.trim();

      if (push && location.hash !== '#' + id) history.pushState(null, '', '#' + id);
      if (window.innerWidth <= 900 && CYQ.closeDrawer) CYQ.closeDrawer();

      // On ne déplace le focus que sur une navigation voulue : au premier
      // chargement, un anneau de focus sur le titre ressemble à un bug.
      if (moveFocus) {
        var h = $('h1, h2', $('[data-section="' + id + '"]'));
        if (h) { h.setAttribute('tabindex', '-1'); h.focus({ preventScroll: true }); }
      }
      window.scrollTo(0, 0);
      /* Qui entre où. Les écrans de lecture — historique, statistiques,
         journal — se chargent à leur PREMIÈRE visite : tout charger au
         démarrage ferait payer cinq cents matchs à quelqu'un venu changer
         un salon. Surveiller le hash ne suffirait pas, il ne dit rien des
         retours arrière. */
      document.dispatchEvent(new CustomEvent('cyq:section', { detail: id }));
    }

    links.forEach(function (l) {
      l.addEventListener('click', function (e) {
        e.preventDefault();
        show(l.getAttribute('data-goto'), true, true);
      });
    });
    window.addEventListener('popstate', function () {
      show((location.hash || '').replace('#', '') || sections[0].getAttribute('data-section'), false, true);
    });
    show((location.hash || '').replace('#', '') || sections[0].getAttribute('data-section'), false, false);
    CYQ.showSection = show;
  }

  /* ------------------------------------------------------------- démarrage */

  /* ================== LE RETOUR, JOUÉ À L'ENVERS ======================

     Trois écrans portent un bouton Retour — le panneau, le choix du
     serveur, la connexion — et ils reculent tous les trois d'un cran dans
     le même parcours. L'effet est donc ici et pas dans l'un des trois
     `page-*.js` : écrit là, il aurait manqué aux deux autres, et c'est
     exactement comme ça que le lien « Documentation » avait fini par
     s'écrire de cinq façons.

     Ce qu'on joue est L'OUVERTURE DE LA PAGE À L'ENVERS. Les blocs s'en
     vont du dernier vers le premier — l'ordre du DOM remonté, donc
     l'ordre de lecture pris à rebours — et ils redescendent vers le bas
     d'où ils étaient venus. La barre du haut remonte par où elle est
     descendue, et la page recule d'un pour cent et demi : le `.985` du
     départ, repris en sens inverse. C'est ce rembobinage qui le fait lire
     comme un retour en arrière ; une sortie qui glisserait vers l'avant
     annoncerait une page de plus, pas la précédente.

     260 ms, et pas davantage : au-delà, ce n'est plus une transition,
     c'est une attente avant de naviguer. La navigation part de toute
     façon au bout de 320 ms même si l'animation ne rend pas la main —
     un bouton Retour qui ne revient pas est un cul-de-sac.

     Sans anime.js, ou si la personne demande moins de mouvement, cette
     fonction ne câble RIEN : le lien reste un lien ordinaire et navigue
     tout seul. C'est la variante calme, et c'est aussi ce qui se passe si
     le script ne tourne pas du tout. */
  function wireRetour() {
    var liens = $$('[data-retour]');
    if (!liens.length) return;

    var A = window.anime;
    var force = document.documentElement.classList.contains('motion-force');
    var calme = !force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!A || calme) return;

    /* La page dit elle-même ce qui s'en va, en marquant ses blocs. Sans
       marque — la connexion, dont les étapes s'échangent déjà toutes
       seules — c'est la page entière qui recule, ce qui suffit. */
    var blocs = $$('[data-sortie]');
    var barre = $('[data-nav]');
    var shell = $('.shell');

    function remonter(apres) {
      var parti = false;
      function partir() { if (!parti) { parti = true; apres(); } }
      setTimeout(partir, 320);

      var tl = A.createTimeline({
        defaults: { ease: A.cubicBezier(.4, 0, 1, 1) },
        onComplete: partir
      });
      if (shell) tl.add(shell, { scale: .985, duration: 260 }, 0);
      if (blocs.length) {
        /* `from: 'last'` : le dernier bloc arrivé est le premier à
           repartir. C'est toute la différence entre « ça s'en va » et
           « ça revient en arrière ». */
        tl.add(blocs, { opacity: 0, y: 12, duration: 200,
                        delay: A.stagger(40, { from: 'last' }) }, 0);
      }
      if (barre) tl.add(barre, { opacity: 0, y: -24, duration: 220 }, 60);
      return tl;
    }

    liens.forEach(function (lien) {
      lien.addEventListener('click', function (e) {
        /* Clic du milieu, Ctrl, Cmd, Maj : la page courante ne s'en va
           pas, elle reste ouverte sous un nouvel onglet. Rien à jouer. */
        if (e.defaultPrevented || e.button !== 0 || e.metaKey ||
            e.ctrlKey || e.shiftKey || e.altKey) return;
        var ou = lien.getAttribute('href');
        if (!ou || ou === '#') return;
        e.preventDefault();
        remonter(function () { location.href = ou; });
      });
    });
  }

  function boot() {
    document.documentElement.setAttribute('data-theme', store('theme') || CFG.DEFAULT_THEME || 'dark');

    /* L'ADRESSE D'ABORD, avant la langue retenue et avant celle du
       navigateur. Quelqu'un qui ouvre /es a demandé l'espagnol
       explicitement ; lui servir le français parce qu'il a lu la page en
       français la semaine dernière, c'est ignorer ce qu'il vient de
       taper. Et comme setLang enregistre, son choix est retenu ensuite. */
    var depuisUrl = langueDeLAdresse();
    var saved = store('lang');
    var nav = (navigator.language || '').slice(0, 2).toLowerCase();
    setLang(depuisUrl || saved ||
            (LANGS.indexOf(nav) !== -1 ? nav : (CFG.DEFAULT_LANG || 'fr')), true);
    poserDrapeauxFixes(document);
    setTheme(store('theme') || CFG.DEFAULT_THEME || 'dark');

    $$('[data-theme-toggle]').forEach(function (b) {
      b.addEventListener('click', function () { setTheme(CYQ.theme === 'dark' ? 'light' : 'dark'); });
    });
    $$('[data-lang-pick]').forEach(function (b) {
      b.addEventListener('click', function () { setLang(b.getAttribute('data-lang-pick')); });
    });

    // liens Discord
    $$('[data-login]').forEach(function (a) {
      var u = CYQ.loginUrl();
      if (u) a.setAttribute('href', u);
      else { a.setAttribute('aria-disabled', 'true'); a.setAttribute('href', '#'); a.classList.add('is-unconfigured'); }
    });
    $$('[data-invite]').forEach(function (a) {
      var u = CYQ.inviteUrl(a.getAttribute('data-guild-id') || null);
      if (u) a.setAttribute('href', u);
      else { a.setAttribute('aria-disabled', 'true'); a.setAttribute('href', '#'); a.classList.add('is-unconfigured'); }
    });
    if (!CFG.CLIENT_ID) {
      $$('[data-needs-client-id]').forEach(function (el) { el.hidden = false; });
      wireCfgForm();
    }
    /* Le bandeau CLIENT_ID sait aussi l'enregistrer. C'est ce qui rend le
       site utilisable en ligne sans toucher à config.js. La valeur part
       dans localStorage, donc elle ne quitte jamais cet appareil, et
       config.js la relit au chargement suivant. */
    function wireCfgForm() {
      var form = $('[data-cfg-form]');
      if (!form) return;
      var champ = $('#cfg-client-id', form);
      var msg   = $('[data-cfg-msg]', form);

      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var val = (champ.value || '').trim();
        // Un identifiant Discord est un snowflake : uniquement des chiffres.
        if (!/^[0-9]{15,25}$/.test(val)) {
          msg.textContent = "Un CLIENT_ID ne contient que des chiffres, 15 à 25.";
          msg.removeAttribute('data-etat');
          champ.focus();
          return;
        }
        try {
          var local = JSON.parse(localStorage.getItem('cyq:config') || '{}');
          local.CLIENT_ID = val;
          localStorage.setItem('cyq:config', JSON.stringify(local));
        } catch (err) {
          msg.textContent = "Ce navigateur refuse le stockage local. Renseignez CLIENT_ID dans config.js.";
          msg.removeAttribute('data-etat');
          return;
        }
        msg.textContent = "Enregistré. Rechargement…";
        msg.setAttribute('data-etat', 'ok');
        // Un rechargement plutôt qu'un recâblage à chaud : CFG est lu une
        // seule fois au démarrage, et une moitié de page reconfigurée
        // serait pire qu'une page qui repart propre.
        setTimeout(function () { location.reload(); }, 450);
      });
    }

    /* Les liens qui traversent d'un domaine à l'autre. Le HTML garde
       l'adresse relative — elle reste juste quand tout est sur un seul
       domaine — et c'est ici qu'elle devient absolue si besoin.
         data-site : vers la vitrine   (index, modules, guide, support)
         data-app  : vers le panneau   (login.html, welcome, servers, dashboard)

       La valeur est la FORME COURTE, sans .html, depuis le 29 octobre.
       `versOrigine` ne suppose rien de l'extension : il nettoie les barres
       obliques de tête et préfixe, c'est tout. Seul login garde sa forme
       longue, parce que Discord compare l'adresse de retour OAuth au
       caractère près et que c'est login.html qui est déclarée là-bas. */
    function poserLiensCroises() {
      $$('[data-site]').forEach(function (a) {
        a.setAttribute('href', CYQ.siteUrl(a.getAttribute('data-site')));
      });
      $$('[data-app]').forEach(function (a) {
        a.setAttribute('href', CYQ.appUrl(a.getAttribute('data-app')));
      });
    }
    poserLiensCroises();
    /* Le lien vers l'accueil porte maintenant une langue : il doit suivre
       celle qu'on vient de choisir, sinon le logo de la nav ramène à la
       version qu'on lisait avant de changer. */
    document.addEventListener('cyq:lang', poserLiensCroises);

    $$('[data-cfg-link]').forEach(function (a) {
      var k = a.getAttribute('data-cfg-link');
      if (!CFG[k] || CFG[k] === '#') return;
      /* DOCS_URL vaut « guide » : une page de la vitrine. Depuis le
         panneau, elle doit donc partir sur l'autre domaine. Une adresse
         déjà absolue (http…, //…, mailto:) n'est jamais touchée. */
      a.setAttribute('href', /^([a-z][a-z0-9+.-]*:|\/\/)/i.test(CFG[k])
        ? CFG[k] : CYQ.siteUrl(CFG[k]));
    });

    CYQ.initCombos(document);
    wireSwitches(document);
    wireSegmented(document);
    wireValidation(document);
    CYQ.initSections(document);
    wireLangMenu();
    wireDrawer();
    wireRouter();
    wireRetour();

    document.addEventListener('cyq:lang', function () {
      wireSwitches(document);
      CYQ.refreshCombos();
      setTheme(CYQ.theme);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
