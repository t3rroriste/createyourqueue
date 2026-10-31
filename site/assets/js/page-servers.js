/* =========================================================================
   CreateYourQueue — le choix du serveur

   Contrat d'API inchangé :
     GET /guilds -> [{ id, name, iconUrl, memberCount, botPresent,
                       configured, missingPermissions: [], canManage,
                       updatedAt }]

   Sans API, la page affiche son état « aucune API ». Aucun serveur de
   démonstration, aucun chiffre inventé : tout ce qui s'affiche vient de la
   réponse, ou ne s'affiche pas.

   Le menu de gauche remplace l'ancienne case « masquer sans le bot ». Ses
   catégories sont adossées aux champs ci-dessus, et chacune porte son
   nombre réel.

   anime.js v4 en UMD, comme le reste du site. Il ne sert QU'À l'ouverture
   de la page ; la cascade des lignes et tous les survols sont en CSS, donc
   la liste reste parfaitement fonctionnelle si la bibliothèque n'a pas
   chargé.
   ========================================================================= */
(function () {
  'use strict';

  var t = CYQ.t, esc = CYQ.esc;

  /* La session Discord posée par login.html. On la relit pour afficher le
     compte en bas du menu : c'est la même donnée, déjà obtenue, et il n'y
     a rien à redemander. */
  var DISCORD = 'https://discord.com/api/v10';
  var KEY_TOKEN = 'cyq.dtoken';

  var $  = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) {
    return Array.prototype.slice.call((r || document).querySelectorAll(s));
  };

  var elCats   = $('[data-cats]');
  var elList   = $('[data-list]');
  var elCount  = $('[data-count]');
  var elFilter = $('[data-filter]');

  var guilds = null;
  var etat   = 'loading';          // loading · noapi · auth · error · ready
  var actif  = 'all';              // la catégorie choisie

  /* --------------------------------------------------------------- états */

  /* Un serveur a UN état, pas plusieurs. L'ordre de ce test est donc une
     priorité, pas une liste : si l'accès est révoqué, savoir que le bot est
     présent n'aide personne. C'est exactement l'ordre qu'affiche la ligne,
     ce qui garantit que l'étiquette d'un serveur correspond toujours à la
     catégorie dans laquelle il est rangé. */
  function etatDe(g) {
    if (!g.canManage) return 'revoked';
    if (g.missingPermissions && g.missingPermissions.length) return 'noperms';
    if (!g.botPresent) return 'nobot';
    if (!g.configured) return 'toconfigure';
    return 'configured';
  }

  /* Les catégories. `all` d'abord, puis l'ordre du parcours : ce qui marche,
     ce qui attend une action, ce qui est bloqué.
     `seulSiRempli` : une catégorie vide affichée en permanence est un
     mensonge de plus — celles-là disparaissent quand elles n'ont personne. */
  var CATS = [
    { cle: 'all',         i18n: 'sv.catAll' },
    { cle: 'configured',  i18n: 'sv.catConfigured',  vide: 'sv.noneConfigured' },
    { cle: 'toconfigure', i18n: 'sv.catToConfigure', vide: 'sv.noneToConfigure' },
    { cle: 'nobot',       i18n: 'sv.catNoBot',       vide: 'sv.noneNoBot' },
    { cle: 'noperms',     i18n: 'sv.catNoPerms',     seulSiRempli: true }
  ];

  /* « Droits insuffisants » réunit les deux empêchements : il manque des
     permissions au bot, ou la personne a perdu « Gérer le serveur ». Du
     point de vue de qui regarde, c'est le même problème — « je ne peux pas
     y toucher » — et deux entrées de menu pour ça seraient deux entrées de
     trop. Les deux lignes gardent en revanche leur étiquette distincte. */
  function dansCat(g, cle) {
    if (cle === 'all') return true;
    var e = etatDe(g);
    if (cle === 'noperms') return e === 'noperms' || e === 'revoked';
    return e === cle;
  }

  function compte(cle) {
    if (!guilds) return null;
    var n = 0;
    for (var i = 0; i < guilds.length; i++) if (dansCat(guilds[i], cle)) n++;
    return n;
  }

  /* ------------------------------------------------------------- glyphes */

  /* Un glyphe par état, et jamais une couleur seule : « droits
     insuffisants » et « accès révoqué » se distinguent par leur dessin ET
     par leur luminosité, pas par une teinte — la D.A. n'a qu'un accent et
     il est déjà pris par l'indicateur du menu. */
  var GLYPHES = {
    configured:  '<path d="M20 6 9 17l-5-5"/>',
    toconfigure: '<path d="M12 5v14M5 12h14"/>',
    nobot:       '<circle cx="12" cy="12" r="9"/><path d="M9 9h.01M15 9h.01M9 15h6"/>',
    noperms:     '<path d="M12 3 2 20h20L12 3zM12 9v5M12 17.5v.01"/>',
    revoked:     '<rect x="4" y="10" width="16" height="10" rx="1.5"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>'
  };

  function glyphe(cle, taille) {
    var s = taille || 13;
    return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.9" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' + (GLYPHES[cle] || '') + '</svg>';
  }

  var LIBELLE_ETAT = {
    configured:  'sv.stConfigured',
    toconfigure: 'sv.stToConfigure',
    nobot:       'sv.stNoBot',
    noperms:     'sv.stNoPerms',
    revoked:     'sv.stRevoked'
  };

  var LIBELLE_ACTION = {
    configured:  'sv.actConfigure',
    toconfigure: 'sv.actWizard',
    nobot:       'sv.actInvite',
    noperms:     'sv.actFix'
  };

  /* ---------------------------------------------------------- le menu --- */

  function rendreCats() {
    if (!elCats) return;

    var html = '';
    CATS.forEach(function (c) {
      var n = compte(c.cle);
      if (c.seulSiRempli && !n) return;
      var sel = c.cle === actif;
      html +=
        '<button class="svcat" type="button" role="tab" id="sv-cat-' + c.cle + '"' +
        ' aria-selected="' + (sel ? 'true' : 'false') + '"' +
        ' aria-controls="sv-list"' +
        ' tabindex="' + (sel ? '0' : '-1') + '"' +
        ' data-cat="' + c.cle + '">' +
          '<span class="svcat__label">' + esc(t(c.i18n)) + '</span>' +
          '<span class="svcat__n">' + (n === null ? '' : n) + '</span>' +
        '</button>';
    });
    elCats.innerHTML = html;

    /* La catégorie active a pu disparaître (elle s'est vidée pendant un
       rafraîchissement) : on revient alors sur « tous », plutôt que de
       laisser un panneau sans onglet. */
    if (!$('[data-cat="' + actif + '"]', elCats)) {
      actif = 'all';
      rendreCats();
      return;
    }
    if (elList) elList.setAttribute('aria-labelledby', 'sv-cat-' + actif);
  }

  function choisir(cle, donnerLeFocus) {
    if (cle === actif) return;
    actif = cle;
    rendreCats();
    rendreListe();
    if (donnerLeFocus) {
      var b = $('[data-cat="' + cle + '"]', elCats);
      if (b) b.focus();
    }
  }

  /* Un tablist se parcourt aux flèches, pas à la tabulation : tout le menu
     ne compte que pour un arrêt, et on passe d'une catégorie à l'autre sans
     quitter le clavier. Les deux axes sont acceptés parce que le menu est
     vertical sur grand écran et horizontal sur petit. */
  function clavier(ev) {
    var k = ev.key;
    var suivant = (k === 'ArrowDown' || k === 'ArrowRight');
    var prec    = (k === 'ArrowUp'   || k === 'ArrowLeft');
    if (!suivant && !prec && k !== 'Home' && k !== 'End') return;

    var onglets = $$('[data-cat]', elCats);
    var i = onglets.indexOf(document.activeElement);
    if (i === -1) return;
    ev.preventDefault();

    var j = k === 'Home' ? 0
          : k === 'End'  ? onglets.length - 1
          : suivant      ? (i + 1) % onglets.length
                         : (i - 1 + onglets.length) % onglets.length;
    choisir(onglets[j].getAttribute('data-cat'), true);
  }

  /* ------------------------------------------------------------ la liste */

  function initiales(nom) {
    return (nom || '?').replace(/[^\p{L}\p{N} ]/gu, '').trim().split(/\s+/)
      .slice(0, 2).map(function (m) { return m[0]; }).join('').toUpperCase() || '?';
  }

  function nombre(n) {
    return Number(n).toLocaleString(CYQ.lang);
  }

  /* Le contexte d'une ligne. Chaque morceau vient d'un champ réel ; s'il
     manque, le morceau n'apparaît pas — on n'écrit jamais « 0 membre »
     pour un serveur dont on ignore la taille. */
  function contexte(g, cle) {
    var bouts = [];
    if (g.memberCount != null) bouts.push(nombre(g.memberCount) + ' ' + t('c.members'));

    if (cle === 'revoked') {
      bouts.push(t('sv.revokedHelp'));
    } else if (cle === 'noperms') {
      bouts.push(g.missingPermissions.join(' · '));
    } else if (cle === 'configured' && g.updatedAt) {
      bouts.push(t('sv.modified', {
        date: new Date(g.updatedAt).toLocaleDateString(CYQ.lang)
      }));
    }
    return bouts;
  }

  function ligne(g, i) {
    var cle = etatDe(g);
    /* Au-delà de dix lignes, le retard d'entrée ne grandit plus : la
       vingtième arriverait une seconde après la première. */
    var rang = i < 10 ? i : 10;
    var alerte = (cle === 'noperms' || cle === 'revoked');

    var icone = g.iconUrl
      ? '<span class="svrow__icon"><img src="' + esc(g.iconUrl) + '" alt="" ' +
        'width="44" height="44" loading="lazy" decoding="async"></span>'
      : '<span class="svrow__icon" aria-hidden="true">' + esc(initiales(g.name)) + '</span>';

    var bouts = contexte(g, cle).map(function (b) {
      return '<span class="svrow__num">' + esc(b) + '</span>';
    }).join('<span class="svrow__dot" aria-hidden="true">·</span>');

    var corps =
      icone +
      '<span class="svrow__body">' +
        '<span class="svrow__name">' + esc(g.name) + '</span>' +
        '<span class="svrow__meta">' +
          '<span class="svrow__state' + (alerte ? ' is-alert' : '') + '">' +
            glyphe(cle, 13) + esc(t(LIBELLE_ETAT[cle])) +
          '</span>' +
          (bouts ? '<span class="svrow__dot" aria-hidden="true">·</span>' + bouts : '') +
        '</span>' +
      '</span>';

    /* Accès révoqué : pas de lien. Un lien mort ou un bouton désactivé qu'on
       peut quand même atteindre au clavier promet une action qui n'existe
       pas ; ici la ligne sort simplement du parcours, et son étiquette dit
       pourquoi. */
    if (cle === 'revoked') {
      return '<div class="svrow is-off" style="--i:' + rang + '">' + corps + '</div>';
    }

    /* On passe par l'écran de transition, pas directement au panneau.
       Ce n'est pas un détour décoratif : welcome.html précharge app.css et
       page-dashboard.js pendant qu'il s'affiche, et n'ouvre le panneau que
       lorsqu'ils sont là. Sans lui, le panneau s'ouvrirait sur une page
       nue le temps du téléchargement. C'est déjà le trajet qu'emprunte la
       connexion ; le choix du serveur l'emprunte maintenant aussi. */
    var href = (cle === 'nobot' || cle === 'noperms')
      ? '#'    // recâblé juste après avec l'URL d'invitation, qui dépend du CLIENT_ID
      : 'welcome.html?guild=' + encodeURIComponent(g.id);

    return '<a class="svrow" style="--i:' + rang + '" href="' + esc(href) + '"' +
      (cle === 'nobot' || cle === 'noperms'
        ? ' data-invite data-guild-id="' + esc(g.id) + '"' : '') + '>' +
      corps +
      '<span class="svrow__go">' +
        '<span class="svrow__goText">' + esc(t(LIBELLE_ACTION[cle])) + '</span>' +
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>' +
      '</span>' +
    '</a>';
  }

  /* ------------------------------------------------------- états vides -- */

  function vide(titre, corps, cta, href, plein) {
    return '<div class="svempty">' +
      '<h2>' + esc(titre) + '</h2>' +
      (corps ? '<p>' + esc(corps) + '</p>' : '') +
      (cta ? '<a class="pill' + (plein ? '' : ' pill--ghost') + '" href="' +
             esc(href || '#') + '">' + esc(cta) + '</a>' : '') +
    '</div>';
  }

  function squelette() {
    var out = '';
    for (var i = 0; i < 4; i++) {
      out += '<div class="svskel" aria-hidden="true">' +
        '<span class="svskel__icon"></span>' +
        '<span class="svskel__body">' +
          '<span class="svskel__l1"></span><span class="svskel__l2"></span>' +
        '</span>' +
        '<span class="svskel__go"></span>' +
      '</div>';
    }
    return out;
  }

  /* ----------------------------------------------------------- le rendu */

  function poser(html, occupe) {
    elList.innerHTML = html;
    if (occupe) elList.setAttribute('aria-busy', 'true');
    else elList.removeAttribute('aria-busy');
  }

  var premierRendu = true;

  function rendreListe() {
    if (!elList) return;
    elList.classList.remove('svlist--entre');

    if (etat === 'loading') {
      poser(squelette(), true);
      elCount.textContent = t('c.loading');
      return;
    }
    if (etat === 'noapi') {
      poser(vide(t('d.noApi'), t('d.noApiBody')));
      elCount.textContent = '';
      return;
    }
    if (etat === 'auth') {
      poser(vide(t('sv.needLogin'), t('sv.needLoginBody'), t('h.loginBtn'),
                 CYQ.loginUrl() || 'login.html', true));
      elCount.textContent = '';
      return;
    }
    /* 429 : Discord limite, ce n'est pas une panne. La page de choix tape
       la même route que le panneau et se heurte donc au même mur — la
       traiter comme une erreur de chargement envoyait chercher ailleurs. */
    if (etat === 'rate') {
      poser(vide(t('d.rate'), t('d.rateBody'), t('c.retry'), '#', true));
      var rr = $('.svempty .pill', elList);
      if (rr) rr.addEventListener('click', function (ev) { ev.preventDefault(); charger(); });
      elCount.textContent = '';
      return;
    }
    if (etat === 'error') {
      poser(vide(t('sv.loadErr'), t('sv.loadErrBody'), t('c.retry'), '#', true));
      var r = $('.svempty .pill', elList);
      if (r) r.addEventListener('click', function (ev) { ev.preventDefault(); charger(); });
      elCount.textContent = '';
      return;
    }

    /* ---- état « ready » ---- */

    if (!guilds.length) {
      poser(vide(t('sv.emptyTitle'), t('sv.emptyBody'), t('sv.emptyCta'),
                 CYQ.inviteUrl() || '#', true));
      elCount.textContent = '';
      return;
    }

    var q = (elFilter.value || '').trim().toLowerCase();
    var dansLaCat = guilds.filter(function (g) { return dansCat(g, actif); });
    var lignes = dansLaCat.filter(function (g) {
      return !q || (g.name || '').toLowerCase().indexOf(q) !== -1;
    });

    elCount.textContent = t('sv.count', { n: lignes.length, total: guilds.length });

    /* Une catégorie vide a son propre message : « aucun serveur configuré »
       et « aucun serveur ne correspond au filtre » ne disent pas du tout la
       même chose, et un message générique obligerait à deviner laquelle des
       deux situations on vit. */
    if (!dansLaCat.length) {
      var cat = CATS.filter(function (c) { return c.cle === actif; })[0];
      var base = cat && cat.vide;
      poser(vide(base ? t(base + 'Title') : t('sv.noFilterTitle'),
                 base ? t(base + 'Body') : ''));
      return;
    }

    if (!lignes.length) {
      poser(vide(t('sv.noFilterTitle'), '', t('c.clear'), '#'));
      var c = $('.svempty .pill', elList);
      if (c) c.addEventListener('click', function (ev) {
        ev.preventDefault();
        elFilter.value = '';
        rendreListe();
        elFilter.focus();
      });
      return;
    }

    /* La cascade ne joue qu'une fois, au premier affichage de la liste.
       La classe est posée AVANT l'insertion : l'animation doit exister au
       moment où les lignes entrent dans le document. Pour les rendus
       suivants — une lettre tapée, une catégorie changée — elle est
       absente, et les lignes apparaissent d'un coup, ce qui est le seul
       comportement supportable quand on filtre. */
    if (premierRendu) { elList.classList.add('svlist--entre'); premierRendu = false; }
    poser(lignes.map(ligne).join(''));

    /* Les URL d'invitation dépendent du CLIENT_ID : si la configuration est
       vide, le lien n'existe pas et on le dit plutôt que d'envoyer la
       personne sur une page d'erreur de Discord. */
    $$('[data-invite]', elList).forEach(function (a) {
      var u = CYQ.inviteUrl(a.getAttribute('data-guild-id'));
      if (u) a.setAttribute('href', u);
      else { a.setAttribute('aria-disabled', 'true'); a.removeAttribute('href'); }
    });
  }

  /* ------------------------------------------------------- le chargement */

  function charger() {
    etat = 'loading';
    rendreCats();
    rendreListe();

    CYQ.api.get('/guilds').then(function (data) {
      guilds = Array.isArray(data) ? data : [];
      etat = 'ready';
      rendreCats();
      rendreListe();
    }).catch(function (err) {
      etat = err.code === 'NO_API'       ? 'noapi'
           : err.code === 'UNAUTHORIZED' ? 'auth'
           : err.status === 429          ? 'rate'
                                         : 'error';
      guilds = null;
      rendreCats();
      rendreListe();
    });
  }

  /* ---------------------------------------------------------- le compte */

  function sessionGet(k) {
    try { return sessionStorage.getItem(k); } catch (e) { return null; }
  }
  function sessionSet(k, v) {
    try { if (v === null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); }
    catch (e) { /* navigation privée : on continue sans mémoire */ }
  }

  /* Le numéro de l'avatar par défaut se lit dans l'identifiant : les bits de
     l'horodatage, décalés de 22, modulo 6. Un identifiant Discord dépasse
     2^53, donc Number() en perdrait la fin — d'où BigInt. Les comptes
     d'avant le changement de pseudos gardent leur discriminateur modulo 5.
     Même calcul que sur l'écran de connexion. */
  function avatarParDefaut(u) {
    try {
      if (u.discriminator && u.discriminator !== '0') return (Number(u.discriminator) % 5);
      return Number((BigInt(u.id) >> 22n) % 6n);
    } catch (e) { return null; }
  }

  function rendreCompte(u) {
    var connu = $('[data-me-known]');
    var invite = $('[data-me-guest]');
    if (!connu || !invite) return;

    if (!u) { connu.hidden = true; invite.hidden = false; return; }

    var av = $('[data-me-avatar]', connu);
    var nm = $('[data-me-name]', connu);

    /* Le pseudo unique, préfixé de @ : c'est lui qui identifie vraiment le
       compte. Le nom d'affichage peut être n'importe quoi et ne dit pas à
       qui on est connecté. */
    nm.textContent = '@' + (u.username || u.global_name || '');
    nm.setAttribute('title', u.global_name || u.username || '');

    var src = null;
    if (u.avatar) {
      src = 'https://cdn.discordapp.com/avatars/' + encodeURIComponent(u.id) +
            '/' + encodeURIComponent(u.avatar) + '.png?size=64';
    } else {
      var n = avatarParDefaut(u);
      if (n !== null) src = 'https://cdn.discordapp.com/embed/avatars/' + n + '.png';
    }

    if (src) {
      av.innerHTML = '<img src="' + esc(src) + '" alt="" width="30" height="30">';
    } else {
      av.textContent = initiales(u.global_name || u.username);
    }

    connu.hidden = false;
    invite.hidden = true;
  }

  /* Deux sources possibles, les deux réelles, jamais inventées :
     - le jeton Discord déposé par login.html, quand le site tourne sans
       back-end (c'est le cas par défaut) ;
     - l'API, quand elle existe : la session est alors un cookie, et le
       jeton Discord n'a jamais été écrit ici.
     Si aucune des deux ne répond, on ne montre pas de compte : on montre
     « se connecter ». */
  function chargerCompte() {
    var jeton = sessionGet(KEY_TOKEN);

    if (jeton) {
      fetch(DISCORD + '/users/@me', { headers: { Authorization: 'Bearer ' + jeton } })
        .then(function (r) {
          if (r.status === 401) { sessionSet(KEY_TOKEN, null); throw new Error('EXPIRED'); }
          if (!r.ok) throw new Error('HTTP_' + r.status);
          return r.json();
        })
        .then(rendreCompte)
        .catch(function () { rendreCompte(null); });
      return;
    }

    if (!CYQ.api.configured) { rendreCompte(null); return; }
    CYQ.api.get('/me').then(rendreCompte).catch(function () { rendreCompte(null); });
  }

  function deconnecter() {
    sessionSet(KEY_TOKEN, null);
    location.href = CYQ.loginUrl() || 'login.html';
  }

  /* -------------------------------------------------------------- motion */

  var A = window.anime;
  var force = document.documentElement.classList.contains('motion-force');
  var calme = !force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function decouvrir() { document.documentElement.classList.remove('motion-pending'); }

  function ouverture() {
    if (!A || calme) { decouvrir(); return; }

    var utils = A.utils;
    var nav   = $('[data-nav]');
    var blocs = [$('.svcats'), $('.sv__main'), $('.svme')].filter(Boolean);

    /* États de départ posés en JS, jamais en CSS : si le script tombe, la
       page reste lisible au lieu de rester invisible. */
    utils.set(nav, { opacity: 0, y: -24 });
    utils.set(blocs, { opacity: 0, y: 12 });
    decouvrir();

    var tl = A.createTimeline({ defaults: { ease: A.cubicBezier(.16, 1, .3, 1) } });

    /* Pas de rayon animé sur la coque : `border-radius` repeint une surface
       plein écran à chaque image. Seule l'échelle bouge, et de 1,5 %. */
    /* L'ouverture reste courte : cet écran n'est pas une page d'accueil,
       on vient y chercher un serveur. 160 ms d'attente avant que le
       contenu commence à paraître, pas 260 comme sur la connexion. */
    tl.add('.shell', { scale: [.985, 1], duration: 700 }, 0)
      .add(nav, { opacity: 1, y: 0, duration: 560 }, 80)
      .add(blocs, { opacity: 1, y: 0, duration: 480, delay: A.stagger(60) }, 160);
  }

  /* --------------------------------------------------------- orchestration */

  if (elCats) {
    elCats.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('[data-cat]') : null;
      /* `true` : rendreCats() reconstruit le menu, donc le bouton cliqué
         n'existe plus. Sans ce rappel, le focus retomberait sur <body>. */
      if (b) choisir(b.getAttribute('data-cat'), true);
    });
    elCats.addEventListener('keydown', clavier);
  }

  if (elFilter) {
    elFilter.addEventListener('input', function () {
      if (etat === 'ready') rendreListe();
    });
  }

  var sortie = $('[data-logout]');
  if (sortie) sortie.addEventListener('click', deconnecter);

  /* L'orientation du tablist suit la disposition : verticale en colonne,
     horizontale en rangée. Les lecteurs d'écran annoncent la bonne, et les
     flèches des deux axes fonctionnent de toute façon. */
  var etroit = window.matchMedia('(max-width: 900px)');
  function poserOrientation() {
    if (elCats) {
      elCats.setAttribute('aria-orientation', etroit.matches ? 'horizontal' : 'vertical');
    }
  }
  poserOrientation();
  if (etroit.addEventListener) etroit.addEventListener('change', poserOrientation);
  else if (etroit.addListener) etroit.addListener(poserOrientation);

  document.addEventListener('cyq:lang', function () {
    rendreCats();
    rendreListe();
  });

  /* Ce script s'exécute à l'analyse de la page, donc AVANT le démarrage de
     app.js, qui pose la langue sur `DOMContentLoaded`. Lancé tout de suite,
     le premier rendu se ferait en français quelle que soit la langue du
     visiteur — et les états vides contiennent du texte produit en JS, que
     rien ne viendrait retraduire ensuite. app.js ayant enregistré son
     démarrage en premier, il passera avant celui-ci. */
  function demarrer() {
    ouverture();
    chargerCompte();
    charger();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', demarrer);
  else demarrer();
})();
