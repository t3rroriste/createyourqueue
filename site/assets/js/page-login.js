/* =========================================================================
   CreateYourQueue — écran de connexion
   Deux étapes : on relie le compte Discord, puis on invite le bot et on
   choisit le serveur à configurer.

   Pourquoi le flux « implicite » (response_type=token) et pas le flux
   classique par code : l'échange d'un code contre un jeton exige le
   CLIENT_SECRET, donc un serveur. Le site est hébergé en statique chez LWS,
   il n'y en a pas. Le flux implicite rend le jeton directement au
   navigateur, sans secret — c'est exactement le cas prévu pour une page
   sans back-end. Si un jour API_BASE pointe sur une vraie API, la fonction
   CYQ.discordAuthUrl() lui rend la main toute seule et ce fichier n'a pas
   à changer.

   Le jeton ne vit que dans sessionStorage : il disparaît à la fermeture de
   l'onglet, et il n'est jamais écrit dans l'URL une fois lu.
   ========================================================================= */
(function () {
  'use strict';

  var CFG = window.CYQ_CONFIG || {};
  var t = CYQ.t, esc = CYQ.esc;

  var API = 'https://discord.com/api/v10';
  var KEY_TOKEN = 'cyq.dtoken';
  var KEY_STATE = 'cyq.dstate';

  var racine  = document.querySelector('[data-auth]');
  var etapes  = {
    login:  document.querySelector('[data-step="login"]'),
    invite: document.querySelector('[data-step="invite"]'),
    error:  document.querySelector('[data-step="error"]')
  };

  function decouvrir() { document.documentElement.classList.remove('motion-pending'); }

  /* ------------------------------------------------------------ session */

  function sessionGet(k) {
    try { return sessionStorage.getItem(k); } catch (e) { return null; }
  }
  function sessionSet(k, v) {
    try { if (v === null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); }
    catch (e) { /* navigation privée : on continue sans mémoire */ }
  }

  /* Un state tiré au sort avant le départ, relu au retour. Sans lui,
     n'importe quelle page peut renvoyer la personne ici avec un jeton
     qu'elle a obtenu ailleurs. */
  function nouveauState() {
    var a = new Uint8Array(16);
    (window.crypto || window.msCrypto).getRandomValues(a);
    return Array.prototype.map.call(a, function (n) {
      return ('0' + n.toString(16)).slice(-2);
    }).join('');
  }

  /* ------------------------------------------------------------- étapes */

  function montrer(nom) {
    Object.keys(etapes).forEach(function (k) {
      if (etapes[k]) etapes[k].hidden = (k !== nom);
    });
    entree(etapes[nom]);
  }

  function erreur(titre, corps) {
    var et = etapes.error;
    et.querySelector('[data-err-title]').textContent = titre;
    et.querySelector('[data-err-body]').textContent = corps || '';
    montrer('error');
  }

  /* ---------------------------------------------------------- le départ */

  function partirVersDiscord(ev) {
    if (ev) ev.preventDefault();

    /* Avec une vraie API, c'est elle qui mène la danse : elle tire le state
       côté serveur et garde le secret. On ne fait que suivre. */
    if (CFG.API_BASE && CYQ.apiLoginUrl) {
      location.href = CYQ.apiLoginUrl();
      return;
    }
    if (!CFG.CLIENT_ID) {
      erreur(t('au.noClientTitle'), t('au.noClientBody'));
      return;
    }
    var st = nouveauState();
    sessionSet(KEY_STATE, st);
    location.href = CYQ.discordAuthUrl(st);
  }

  /* --------------------------------------------------------- le retour */

  /* Discord renvoie le jeton dans le FRAGMENT (#access_token=…), jamais
     dans la query : le fragment n'est pas envoyé au serveur, donc il
     n'apparaît ni dans les journaux d'Apache ni dans le Referer. On le lit,
     puis on le retire de la barre d'adresse. */
  function lireFragment() {
    var brut = location.hash.replace(/^#/, '');
    if (!brut) return null;
    var out = {};
    brut.split('&').forEach(function (p) {
      var i = p.indexOf('=');
      if (i > 0) out[decodeURIComponent(p.slice(0, i))] = decodeURIComponent(p.slice(i + 1).replace(/\+/g, ' '));
    });
    return out.access_token || out.error ? out : null;
  }

  function nettoyerUrl() {
    if (window.history && history.replaceState) {
      history.replaceState(null, '', location.pathname + location.search);
    } else {
      location.hash = '';
    }
  }

  /* ------------------------------------------------------- appels Discord */

  function discord(chemin, jeton) {
    return fetch(API + chemin, { headers: { Authorization: 'Bearer ' + jeton } })
      .then(function (r) {
        if (r.status === 401) { var e = new Error('EXPIRED'); e.code = 'EXPIRED'; throw e; }
        if (r.status === 429) { var l = new Error('RATE'); l.code = 'RATE'; throw l; }
        if (!r.ok) { var x = new Error('HTTP_' + r.status); x.code = 'HTTP'; throw x; }
        return r.json();
      });
  }

  /* MANAGE_GUILD (1<<5) ou ADMINISTRATOR (1<<3), ou bien être propriétaire.
     Les permissions arrivent en CHAÎNE parce qu'elles dépassent depuis
     longtemps ce qu'un Number sait porter sans perdre de bits : on les lit
     donc en BigInt, avec un repli sur les 32 bits bas là où il manque. */
  function peutGerer(g) {
    if (g.owner) return true;
    var p = g.permissions;
    if (p == null) return false;
    try {
      var b = BigInt(p);
      return (b & 32n) === 32n || (b & 8n) === 8n;
    } catch (e) {
      var n = parseInt(String(p).slice(-9), 10) || 0;
      return (n & 32) === 32 || (n & 8) === 8;
    }
  }

  function initiales(nom) {
    return (nom || '?').replace(/[^\p{L}\p{N} ]/gu, '').trim().split(/\s+/)
      .slice(0, 2).map(function (m) { return m[0]; }).join('').toUpperCase() || '?';
  }

  /* ------------------------------------------------------- étape 2 : rendu */

  /* L'avatar par défaut de Discord, pour qui n'en a pas posé.
     Son numéro se lit dans l'identifiant : les bits de l'horodatage,
     décalés de 22, modulo 6. Un identifiant Discord dépasse 2^53, donc
     Number() en perdrait la fin — d'où BigInt. Les comptes d'avant le
     changement de pseudos gardent, eux, leur discriminateur modulo 5.
     Si quoi que ce soit échoue, on retombe sur les initiales plutôt que
     sur un trou. */
  function avatarParDefaut(u) {
    try {
      if (u.discriminator && u.discriminator !== '0') {
        return (Number(u.discriminator) % 5);
      }
      return Number((BigInt(u.id) >> 22n) % 6n);
    } catch (e) {
      return null;
    }
  }

  function rendreQui(u) {
    var puce = document.querySelector('[data-who]');
    if (!u || !puce) return;
    var av = puce.querySelector('[data-who-avatar]');
    var nm = puce.querySelector('[data-who-name]');

    /* Le pseudo unique, préfixé de @ : c'est lui qui identifie vraiment le
       compte. Le nom d'affichage, lui, peut être n'importe quoi — « x »,
       par exemple — et ne dit pas à qui on est connecté. */
    nm.textContent = '@' + (u.username || u.global_name || '');
    nm.setAttribute('title', u.global_name || u.username || '');

    var src = null;
    if (u.avatar) {
      src = 'https://cdn.discordapp.com/avatars/' + esc(u.id) + '/' + esc(u.avatar) + '.png?size=64';
    } else {
      var n = avatarParDefaut(u);
      if (n !== null) src = 'https://cdn.discordapp.com/embed/avatars/' + n + '.png';
    }

    if (src) {
      av.innerHTML = '<img src="' + src + '" alt="" width="28" height="28" ' +
        'style="width:100%;height:100%;border-radius:50%;object-fit:cover">';
    } else {
      av.textContent = initiales(u.global_name || u.username);
    }
    puce.hidden = false;
  }

  /* Le second argument est le rang dans la liste, fourni par Array.map : il
     devient `--i`, que le CSS transforme en retard d'arrivée. La cascade est
     donc décrite une fois, en CSS, et le JS ne pilote aucune animation. */
  function carteServeur(g, i) {
    var href = 'welcome.html?guild=' + encodeURIComponent(g.id);
    var icone = g.icon
      ? '<img class="gcard__icon" src="https://cdn.discordapp.com/icons/' + esc(g.id) + '/' +
        esc(g.icon) + '.png?size=64" alt="" width="34" height="34" loading="lazy">'
      : '<span class="gcard__icon" aria-hidden="true">' + esc(initiales(g.name)) + '</span>';
    return '<a class="gcard" href="' + href + '" style="--i:' + i + '">' + icone +
      '<span class="gcard__body">' +
        '<span class="gcard__name">' + esc(g.name) + '</span>' +
        '<span class="gcard__meta">' + esc(g.owner ? t('au.owner') : t('au.manager')) + '</span>' +
      '</span>' +
      '<svg class="gcard__go" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>' +
    '</a>';
  }

  function rendreServeurs(liste) {
    var boite = document.querySelector('[data-guilds]');
    if (!boite) return;
    if (!liste.length) {
      boite.innerHTML = '<p class="fine" style="text-align:center">' + esc(t('au.noGuild')) + '</p>';
      return;
    }
    boite.innerHTML = liste.map(carteServeur).join('');
  }

  function chargerServeurs(jeton) {
    var boite = document.querySelector('[data-guilds]');
    if (boite) boite.innerHTML = '<p class="fine" style="text-align:center">' + esc(t('c.loading')) + '</p>';
    return discord('/users/@me/guilds', jeton).then(function (gs) {
      rendreServeurs((Array.isArray(gs) ? gs : []).filter(peutGerer));
    }).catch(function (err) {
      if (boite) {
        boite.innerHTML = '<p class="fine" style="text-align:center">' +
          esc(err.code === 'RATE' ? t('au.rate') : t('sv.loadErr')) + '</p>';
      }
    });
  }

  /* ---------------------------------------------------- l'invitation du bot */

  /* On ouvre l'autorisation Discord dans une fenêtre à part plutôt que dans
     l'onglet : la personne revient ici avec sa session intacte. Quand la
     fenêtre se referme, la liste des serveurs est relue — le serveur qu'elle
     vient d'ajouter y apparaît. Impossible de savoir autrement si le bot a
     bien été invité : seul le bot lui-même le sait, et il n'expose pas
     d'API accessible depuis ce site. */
  function inviter(ev) {
    if (ev) ev.preventDefault();
    var url = CYQ.inviteUrl();
    if (!url) { erreur(t('au.noClientTitle'), t('au.noClientBody')); return; }

    var w = window.open(url, 'cyq-invite', 'width=520,height=820,noopener');
    if (!w) { location.href = url; return; }   // pop-up bloquée : on y va franchement

    var minuteur = setInterval(function () {
      if (!w.closed) return;
      clearInterval(minuteur);
      var jeton = sessionGet(KEY_TOKEN);
      if (jeton) chargerServeurs(jeton);
    }, 700);
  }

  /* -------------------------------------------------------------- motion */

  var A = window.anime;
  var force = document.documentElement.classList.contains('motion-force');
  var calm  = !force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function entree(bloc) {
    if (!bloc) { decouvrir(); return; }
    if (!A || calm) { decouvrir(); return; }

    var utils = A.utils;
    var nav = document.querySelector('[data-nav]');
    var enfants = Array.prototype.slice.call(bloc.children);

    utils.set(nav, { opacity: 0, y: -24 });
    utils.set(enfants, { opacity: 0, y: 14 });
    decouvrir();

    var tl = A.createTimeline({ defaults: { ease: A.cubicBezier(.16, 1, .3, 1) } });
    tl.add(document.querySelector('.shell'),
           { scale: [.98, 1], borderRadius: ['52px', '36px'], duration: 800 }, 0)
      .add(nav, { opacity: 1, y: 0, duration: 650 }, 100)
      .add(enfants, { opacity: 1, y: 0, duration: 560, delay: A.stagger(70) }, 260);
  }

  /* --------------------------------------------------------- orchestration */

  function demarrer() {
    var frag = lireFragment();

    if (frag && frag.error) {
      nettoyerUrl();
      erreur(
        frag.error === 'access_denied' ? t('au.deniedTitle') : t('au.failTitle'),
        frag.error_description || t('au.deniedBody')
      );
      return;
    }

    if (frag && frag.access_token) {
      var attendu = sessionGet(KEY_STATE);
      nettoyerUrl();
      /* Un state absent des deux côtés reste acceptable (stockage bloqué) ;
         deux states DIFFÉRENTS, jamais : c'est le cas qu'on refuse. */
      if (attendu && frag.state && attendu !== frag.state) {
        erreur(t('au.stateTitle'), t('au.stateBody'));
        return;
      }
      sessionSet(KEY_STATE, null);
      sessionSet(KEY_TOKEN, frag.access_token);
    }

    var jeton = sessionGet(KEY_TOKEN);
    if (!jeton) { montrer('login'); return; }

    montrer('invite');
    discord('/users/@me', jeton).then(function (u) {
      rendreQui(u);
      return chargerServeurs(jeton);
    }).catch(function (err) {
      if (err.code === 'EXPIRED') {
        sessionSet(KEY_TOKEN, null);
        montrer('login');
        return;
      }
      erreur(t('au.failTitle'), t('au.failBody'));
    });
  }

  document.querySelectorAll('[data-discord-login]').forEach(function (a) {
    a.addEventListener('click', partirVersDiscord);
  });
  var btnInvite = document.querySelector('[data-invite-bot]');
  if (btnInvite) {
    var u = CYQ.inviteUrl();
    if (u) btnInvite.setAttribute('href', u);
    btnInvite.addEventListener('click', inviter);
  }
  var rafraichir = document.querySelector('[data-refresh-guilds]');
  if (rafraichir) {
    rafraichir.addEventListener('click', function (ev) {
      ev.preventDefault();
      var j = sessionGet(KEY_TOKEN);
      if (j) chargerServeurs(j);
    });
  }
  document.addEventListener('cyq:lang', function () {
    var j = sessionGet(KEY_TOKEN);
    if (j && etapes.invite && !etapes.invite.hidden) chargerServeurs(j);
  });

  demarrer();
})();
