/* =========================================================================
   Le film de présentation — le moteur
   =========================================================================
   Une fonction, `CYQ_FILM.creer(hote, options)`, qui monte UNE instance du
   film dans `hote` et la rend pilotable par le temps : `seek(ms)` pose
   l'image de l'instant voulu. Le film n'a pas d'horloge à lui : c'est la
   voix (l'élément <audio> du lecteur) qui donne l'heure, et le lecteur
   appelle `seek` à chaque image. Deux horloges finissent toujours par se
   séparer ; une seule ne le peut pas.

   Deux instances vivent sur l'accueil : l'affiche, figée sur l'annonce, et
   le film du lecteur. D'où la fabrique : chacune a son état, ses mesures,
   sa timeline.

   Ce qui est réel et ce qui est mis en scène :
   - film-textes.js : les libellés du panneau et le message du bot, extraits
     des vrais fichiers de langue par outils/textes_video.py ;
   - film-scenario.js : le serveur fictif et ses conversations ;
   - assets/video/voix/<l>.cues.js : le minutage, écrit par
     outils/voix_video.py à partir de la voix enregistrée.

   Mesures : tout est mesuré à plat au montage (getBoundingClientRect), donc
   `hote` doit être affiché quand on appelle `creer` — un conteneur en
   `display: none` donnerait des zéros, et une caméra qui vise le coin.
   ========================================================================= */
(function () {
  'use strict';

  var A = window.anime;
  var LOGO = 'assets/img/logo.png';
  var CHAPITRES = ['chaos', 'panneau', 'format', 'apercu', 'ouvrir', 'annonce', 'equipes', 'vocal', 'suivi', 'securite', 'fin'];

  function creer(hote, o) {
    o = o || {};
    if (!A || !window.CYQ_TEXTES || !window.CYQ_FILM_TEXTES || !window.CYQ_VOIX) return null;
    var LANGUE = window.CYQ_VOIX[o.langue] ? o.langue : 'fr';
    var S = window.CYQ_TEXTES[LANGUE].site, B = window.CYQ_TEXTES[LANGUE].bot, F = window.CYQ_FILM_TEXTES[LANGUE];
    var VOIX = window.CYQ_VOIX[LANGUE];
    // Chaque plan part de l'instant de SA phrase : une langue plus lente
    // décale la suite, sans qu'on retouche le montage.
    var T = {};
    VOIX.lignes.forEach(function (x) { T[x.id] = Math.round(x.debut * 1000); });
    var TOTAL = Math.round(VOIX.total * 1000);
    var etat = { W: 1280, H: 720, k: 1, scene: null, tick: null, cles: null };

    function fmt(t, v) { return t.replace(/\{(\w+)\}/g, function (_, k) { return v[k] != null ? v[k] : ''; }); }
    // Le gras de Discord : **texte** dans les fichiers du bot
    function md(t) { return t.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); }
    function nb(v) { return v.toLocaleString(F.loc); }
    function equipe(n) { return fmt(B['queue.team_default'], { n: n }); }

  /* ───────── icônes ───────── */
  function ico(d, extra) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"' + (extra || '') + '>' + d + '</svg>';
  }
  var I = {
    chev: ico('<path d="m6 9 6 6 6-6"/>'),
    vox: ico('<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/>'),
    plus: ico('<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>', ' stroke-width="1.8"'),
    menu: ico('<path d="M4 7h16M4 12h16M4 17h16"/>'),
    loupe: ico('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
    ecrou: ico('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>', ' stroke-width="1.7"'),
    sortie: ico('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>'),
    ok: ico('<path d="m5 12.5 4.5 4.5L19 7.5"/>', ' stroke-width="2.6"'),
    fleche: ico('<path d="M7 17 17 7M9 7h8v8"/>', ' stroke-width="2.2"'),
    lecture: ico('<path d="M7 5v14l12-7z" fill="currentColor"/>'),
    pause: ico('<path d="M8 5v14M16 5v14"/>', ' stroke-width="3"'),
    bouclier: ico('<path d="M12 3 5 6v5c0 4.4 3 8 7 10 4-2 7-5.6 7-10V6z"/><path d="m9 12 2 2 4-4"/>'),
    discord: '<svg viewBox="0 0 24 24"><path fill="#fff" d="M19.3 5.3A17 17 0 0 0 15 4l-.5 1a15.7 15.7 0 0 0-5 0L9 4a17 17 0 0 0-4.3 1.3C2 9.3 1.3 13.2 1.6 17a17 17 0 0 0 5.2 2.6l1.1-1.8c-.6-.2-1.2-.5-1.8-.9l.4-.3a12.2 12.2 0 0 0 10.6 0l.4.3c-.6.4-1.2.7-1.8.9l1.1 1.8a17 17 0 0 0 5.2-2.6c.4-4.4-.7-8.3-2.9-11.7zM8.7 14.7c-1 0-1.9-.9-1.9-2.1s.8-2.1 1.9-2.1 1.9.9 1.9 2.1-.8 2.1-1.9 2.1zm6.6 0c-1 0-1.9-.9-1.9-2.1s.8-2.1 1.9-2.1 1.9.9 1.9 2.1-.8 2.1-1.9 2.1z"/></svg>',
    curseur: '<svg viewBox="0 0 24 24"><path d="M5 3l14 8.2-6.3 1.6L9.6 19z" fill="#F4F1EC" stroke="#0A0908" stroke-width="1.5" stroke-linejoin="round"/></svg>'
  };

  /* ───────── le casting ───────── */
  // Le dernier, Alex, est l'organisateur : c'est lui qui règle le panneau.
  var G = [
    { n: 'Kaito', h: 28 }, { n: 'nyxx', h: 200 }, { n: 'Bastien', h: 140 }, { n: 'Lou', h: 330 },
    { n: 'R3d', h: 15 }, { n: 'Mehdi', h: 260 }, { n: 'zoé.gg', h: 300 }, { n: 'Sacha', h: 170 },
    { n: 'Ivan', h: 230 }, { n: 'Pablo', h: 70 }, { n: 'Aya', h: 290 }, { n: 'Tom', h: 100 }, { n: 'Alex', h: 45 }
  ];
  var ALEX = 12;
  // Qui écrit quoi dans le salon du début ; le texte vient de F.chaos
  var CHAOS = [0, 1, 2, 4, 3, 5, 6, 7, 1, 8, 9, 10, 11, 0];
  // L'ordre des réactions : l'organisateur d'abord, puis neuf joueurs.
  var FILE = [ALEX, 0, 1, 2, 3, 4, 5, 6, 7, 8];
  var EQ = [[ALEX, 3, 4, 7, 8], [0, 1, 2, 5, 6]];
  var RAID = ['n1tr0_drop_01', 'free.skins.gg', 'raid_b0t_77', 'giveaway_xx', 'n0va_spam'];

  function h(tag, cls, parent, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    if (parent) parent.appendChild(e);
    return e;
  }
  function av(i, parent, cls) {
    var a = h('span', 'k-av' + (cls ? ' ' + cls : ''), parent, G[i].n.charAt(0).toUpperCase());
    a.style.setProperty('--h', G[i].h);
    return a;
  }
  function avHtml(i, cls) {
    return '<span class="k-av' + (cls ? ' ' + cls : '') + '" style="--h:' + G[i].h + '">' + G[i].n.charAt(0).toUpperCase() + '</span>';
  }
  function ment(i) { return '<span class="k-ment">@' + G[i].n + '</span>'; }
  // Mesures en coordonnées de scène, prises à plat avant tout transform de
  // départ : la caméra et le curseur visent la place finale des choses.
  function boite(e, ref) {
    var r = e.getBoundingClientRect(), s = (ref || etat.scene).getBoundingClientRect(), k = etat.k;
    return { x: (r.left - s.left) / k, y: (r.top - s.top) / k, w: r.width / k, h: r.height / k };
  }
  function centre(e, ref) { var b = boite(e, ref); return { x: b.x + b.w / 2, y: b.y + b.h / 2 }; }
  function decale(p, dx, dy) { return { x: p.x + (dx || 0), y: p.y + (dy || 0) }; }
  function cadre(p, s) { return { x: (etat.W / 2 - p.x) * s, y: (etat.H / 2 - p.y) * s, scale: s }; }
    function ecrire(e, v) { v = String(v); if (e.textContent !== v) e.textContent = v; }
  function classe(e, c, on) { if (e.classList.contains(c) !== !!on) e.classList.toggle(c, !!on); }
  // Une suite d'états datés : la valeur en vigueur à l'instant t.
  function aT(liste, t) { var v = liste[0][1]; for (var i = 0; i < liste.length; i++) if (t >= liste[i][0]) v = liste[i][1]; return v; }

  /* ════════════════════════ Discord ════════════════════════ */
  function discord(par, P) {
    var R = {};
    var k = R.win = h('div', 'k', par);
    var dr = R.drawer = h('div', 'k-drawer', k);
    var rail = h('nav', 'k-rail', dr);
    h('i', '', rail, I.discord).style.background = 'var(--k-chat)';
    h('hr', '', rail);
    h('i', 'is-on', rail, F.gi);
    h('i', '', rail, 'GG');
    h('i', '', rail, 'R6');
    h('i', '', rail, I.plus).style.color = '#23A55A';
    var side = R.side = h('aside', 'k-side', dr);
    h('header', 'k-guild', side, F.guild + I.chev);
    var ch = h('div', 'k-chans', side);
    h('div', 'k-cat', ch, F.catText);
    function salon(nom, on) {
      var r = h('div', 'k-ch', ch, '<span class="k-chbg"></span><span class="k-hash">#</span><span>' + nom + '</span>');
      return r;
    }
    salon(F.chanGen);
    R.chRech = salon(F.chanLfg);
    R.chAnn = salon(B['names.channel_queue_announcement']);
    // Deux salons de moins que sur un vrai serveur : les deux vocaux
    // d'équipe et leurs dix joueurs doivent tenir dans la colonne.
    h('div', 'k-cat', ch, F.catVoice);
    R.chAtt = h('div', 'k-ch', ch, I.vox + '<span>' + B['names.voice_queue_waiting'] + '</span><span class="k-badge">0/10</span>');
    R.badge = R.chAtt.lastChild;
    var vz = R.vz = h('div', 'k-vz', ch);
    R.att = FILE.map(function (g) {
      var r = h('div', 'k-vm', vz);
      var a = av(g, r);
      var n = h('span', '', r, G[g].n);
      return { row: r, av: a, nom: n };
    });
    var eqs = h('div', 'k-eqs', vz);
    R.eqHead = []; R.eqSlots = []; R.eqFlash = []; R.eqBadge = [];
    EQ.forEach(function (eq, i) {
      var hd = h('div', 'k-ch', eqs, '<span class="k-chflash"></span>' + I.vox + '<span>' + equipe(i + 1) + '</span><span class="k-badge">0/5</span>');
      R.eqHead.push(hd); R.eqFlash.push(hd.firstChild); R.eqBadge.push(hd.lastChild);
      R.eqSlots.push(eq.map(function (g) {
        var r = h('div', 'k-vm', eqs);
        var a = av(g, r);
        var sp = h('i', 'k-speak', a);
        h('span', '', r, G[g].n);
        return { row: r, av: a, speak: sp };
      }));
    });
    var me = h('div', 'k-me', side);
    av(ALEX, me);
    h('div', '', me, '<b>Alex</b><span>' + F.online + '</span>');

    var main = R.main = h('section', 'k-main', k);
    var head = h('header', 'k-head', main);
    var burger = P ? I.menu : '';
    var ann = B['names.channel_queue_announcement'];
    R.headA = h('div', '', head, burger + '<span class="k-hash">#</span>' + F.chanLfg + '<em>' + F.topicLfg + '</em>');
    R.headB = h('div', '', head, burger + '<span class="k-hash">#</span>' + ann + '<em>' + F.topicAnn + '</em>');
    var flux = R.flux = h('div', 'k-flux', main);
    var chatA = R.chatA = h('div', 'k-chat', flux);
    R.list = h('div', 'k-list', chatA);
    R.msgs = CHAOS.map(function (g, i) {
      return h('div', 'k-msg', R.list, avHtml(g) + '<div class="k-mb"><div class="k-mh"><b class="k-mn">' + G[g].n +
        '</b><span class="k-mt">' + fmt(F.today, { h: '20:' + (41 + Math.floor(i / 3)) }) + '</span></div><p>' + F.chaos[i] + '</p></div>');
    });
    R.tape = h('div', 'k-tape', chatA, '<i><u></u><u></u><u></u></i><span>' + F.typing + '</span>');

    var chatB = R.chatB = h('div', 'k-chat k-chatB', flux);
    h('div', 'k-debut', chatB, '<i>#</i><b>' + fmt(F.welcomeT, { c: ann }) + '</b><span>' + F.welcomeS + '</span>');
    var bot = R.bot = h('div', 'k-msg k-mention', chatB);
    h('img', 'k-av', bot).src = LOGO;
    var mb = h('div', 'k-mb', bot);
    h('div', 'k-mh', mb, '<b class="k-mn">CreateYourQueue</b><span class="k-app">APP</span><span class="k-mt">' + fmt(F.today, { h: '20:58' }) + '</span>');
    h('p', '', mb, '<span class="k-ment">@everyone</span>');
    var vers = h('div', 'k-vers', mb);
    // Deux états du MÊME message, empilés : l'annonce change de forme au
    // lancement, et la faire grandir en place animerait une hauteur.
    var vb = R.verB = h('div', 'k-verB', vers);
    var va = R.verA = h('div', 'k-verA', vers);
    // L'annonce, ligne à ligne comme queue_config.py la compose, avec les
    // textes du bot dans la langue du serveur.
    var tete = '<div class="k-et">' + fmt(B['queue.ann_title'], { name: 'Scrim 5v5' }) + '</div>';
    var champs = '<div class="k-ef"><div><b>' + B['queue.field_time'] + '</b><span><b>21:00</b></span></div><div><b>' + B['queue.field_type'] + '</b><span><b>Scrim</b></span></div></div>';
    var par = '<p>' + fmt(B['queue.ann_by'], { author: ment(ALEX) }) + '</p><p class="k-vide"></p>';
    function ligneEq(n) { return '<p>' + md(fmt(B['queue.ann_team_line'], { n: n, name: equipe(n), color: n === 1 ? '🔴' : '🔵' })) + '</p>'; }
    h('div', 'k-emb', va, tete + '<div class="k-ed">' + par + ligneEq(1) + ligneEq(2) + '<p class="k-vide"></p>' +
      '<p>' + md(fmt(B['queue.ann_cta'], { channel: B['names.voice_queue_waiting'] })) + '</p></div>' + champs +
      '<div class="k-eft">' + B['queue.ann_footer_join'] + '</div>');
    var ra = h('div', 'k-reacs', va);
    var reac = R.reac = h('span', 'k-reac', ra);
    R.reacMe = h('span', 'k-reacme', reac);
    h('span', '', reac, '✅');
    var rn = h('span', 'k-rn', reac);
    var rs = R.reacStrip = h('span', 'k-rs', rn);
    for (var n = 1; n <= 11; n++) h('b', '', rs, n);
    h('div', 'k-emb', vb, tete + '<div class="k-ed">' + par +
      ligneEq(1) + '<p>' + EQ[0].map(ment).join(' ') + '</p>' +
      ligneEq(2) + '<p>' + EQ[1].map(ment).join(' ') + '</p><p class="k-vide"></p>' +
      '<p>' + md(B['queue.ann_started']) + '</p></div>' + champs);
    h('div', 'k-reacs', vb, '<span class="k-reac"><span class="k-reacme"></span><span>✅</span><span>11</span></span>');

    var saisie = h('div', 'k-saisie', main, I.plus);
    R.phA = h('span', '', saisie, fmt(F.placeholder, { c: F.chanLfg }));
    R.phB = h('span', '', saisie, fmt(F.placeholder, { c: ann }));

    if (!P) {
      var mem = h('aside', 'k-mem', k);
      h('div', 'k-cat', mem, fmt(F.onlineN, { n: 13 }));
      [ALEX, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].slice(0, 12).forEach(function (g) {
        h('div', 'k-mm', mem, avHtml(g) + '<span>' + G[g].n + '</span>');
      });
    }
    R.dim = h('div', 'k-dim', k);
    R.jet = h('div', 'k-jet', k);
    R.ring = h('span', 'k-ring', R.jet);
    // Deux échos par jeton : la traînée qui rend le trajet lisible d'un vocal à l'autre
    R.ombres = FILE.map(function (g) { return [av(g, R.jet, 'k-ghost'), av(g, R.jet, 'k-ghost')]; });
    R.jetons = FILE.map(function (g) { return av(g, R.jet); });
    return R;
  }

  /* ════════════════════════ le panneau ════════════════════════ */
  function dashboard(par, P) {
    var R = { nav: {}, sec: {} };
    var d = R.win = h('div', 'd', par);
    h('nav', 'd-nav', d, '<span class="d-nav__mark"><img src="' + LOGO + '" alt="">CreateYourQueue</span>' +
      '<span class="d-nav__links"><span>' + S['n.docs'] + '</span><span>' + S['m.nav'] + '</span><span>' + S['n.support'] + '</span></span>' +
      '<span class="d-disc">' + I.ecrou + '</span><span class="d-pill d-pill--ghost d-pill--sm">' + S['c.back'] + '</span>');
    var db = R.db = h('div', 'd-db', d);
    var side = h('div', 'd-side', db);
    h('div', 'd-guild', side, '<span class="d-guild__ic">' + F.gi + '</span><span><b>' + F.guild + '</b><span>' + F.members + '</span></span>');
    h('div', 'd-find', side, I.loupe + S['d.find'] + '<kbd>⌘ K</kbd>');
    var navv = R.navv = h('div', 'd-navv', side);
    var navin = R.navin = h('div', 'd-navin', navv);
    R.mark = h('span', 'd-mark', navin);
    // Les clés sont celles de dashboard.html : le menu se lit dans la langue du site
    var GROUPES = [
      [null, [['apercu', 's.overview']]],
      ['cat.bot', [['configurations', 's.config'], ['options', 's.options'], ['classement', 'fn.leaderboard', 1], ['rangs', 's.ranks', 1],
        ['mmr', 's.mmr', 1], ['historique', 's.history', 1], ['saisons', 's.seasons', 1], ['clans', 'fn.clans', 1]]],
      ['cat.queue', [['queue', 's.queue'], ['programmation', 's.schedule'], ['presets', 's.presets']]],
      ['cat.server', [['salons', 's.channels'], ['roles', 's.roles']]],
      ['cat.access', [['blacklist', 's.blacklist']]],
      ['cat.security', [['logs', 's.logs'], ['antiraid', 'se.grpRaid'], ['nettoyage', 'se.grpClean'], ['antilien', 'se.grpAntilink']]],
      ['cat.monitor', [['stats', 's.stats'], ['journal', 's.journal'], ['diagnostic', 'd.diagnostic']]]
    ];
    // Le téléphone range les sections en une rangée défilante, sans les
    // sous-sections fléchées — exactement comme dashboard.css sous 900 px.
    GROUPES.forEach(function (gr) {
      var g = h('div', 'd-grp', navin);
      if (gr[0]) h('div', 'd-cat', g, S[gr[0]] + I.chev);
      gr[1].forEach(function (it) {
        R.nav[it[0]] = h('div', 'd-nl', g, (it[2] ? '<i>↳</i>' : '') + '<span>' + S[it[1]] + '</span>');
      });
    });
    h('div', 'd-me', side, '<i>A</i><span>Alex</span>');
    var main = R.main = h('div', 'd-main', db);

    function section(cle, titre, lead) {
      var s = h('section', 'd-sec', main);
      var sc = h('div', 'd-sc', s);
      h('h2', 'd-title', sc, titre);
      if (lead) h('p', 'd-lead', sc, lead);
      R.sec[cle] = { box: s, sc: sc };
      return sc;
    }
    function groupe(par, titre, pad) {
      var g = h('div', 'd-grp2', par);
      if (titre) h('h3', 'd-gt', g, titre);
      return h('div', 'd-card' + (pad ? ' d-card--pad' : ''), g);
    }
    function rang(card, label, desc, ctl) {
      var r = h('div', 'd-row', card, '<p class="d-rt"><b>' + label + '</b>' + (desc || '') + '</p>');
      var c = h('div', 'd-ctl', r, ctl || '');
      return { row: r, ctl: c };
    }
    function inter(on) {
      return '<span class="d-sw"><span class="d-swon" style="opacity:' + (on ? 1 : 0) + '"></span><span class="d-swk" style="transform:translateX(' + (on ? 18 : 0) + 'px)"><i style="opacity:' + (on ? 1 : 0) + '"></i></span></span>';
    }
    function nombre(v, u) { return '<span class="d-in d-in--sm"><span>' + v + '</span>' + (u ? '<u>' + u + '</u>' : '') + '</span>'; }
    function liste(v) { return '<span class="d-select">' + v + I.chev + '</span>'; }

    // Le tableau de bord d'accueil
    var s0 = section('apercu', S['s.overview'], fmt(F.apLead, { g: F.guild }));
    var c0 = groupe(h('div', 'd-col', s0), S['ov.week']);
    c0.innerHTML = '<div class="d-stats">' + [37, 112, 86].map(function (v, i) { return '<div><b>' + v + '</b><span>' + F.stats[i] + '</span></div>'; }).join('') + '</div>';
    var c0b = groupe(s0.lastChild, S['ov.recent']);
    F.act.forEach(function (a) { rang(c0b, a[0], a[1], '<span class="d-rt">' + a[2] + '</span>'); });

    // La file — la section du film
    var sq = section('queue', S['s.queue'], S['q.lead']);
    var body = h('div', 'd-body', sq);
    var col = h('div', 'd-col', body);
    var ci = groupe(col, S['q.grpIdentity']);
    var rn = rang(ci, S['q.name'], '', '<span class="d-in"><span class="d-sel-txt"><span class="d-sel-hl"></span><span data-txt>Queue</span></span><span class="d-caret"></span></span>');
    R.nomIn = rn.ctl.firstChild; R.nomTxt = rn.ctl.querySelector('[data-txt]'); R.nomHl = rn.ctl.querySelector('.d-sel-hl'); R.nomCaret = rn.ctl.querySelector('.d-caret');
    R.rowNom = rn.row;
    rang(ci, S['q.type'], '', '<span class="d-in">Scrim</span>');
    rang(ci, S['q.session'], '', liste(S['q.sessionOnDemand']));
    var cf = groupe(col, S['q.grpFormat']);
    R.grpFormat = cf.parentNode;
    function seg(card, label, vals, on) {
      var r = rang(card, label, '', '<span class="d-seg"><i class="d-segsel"></i>' + vals.map(function (v) { return '<span>' + v + '</span>'; }).join('') + '</span>');
      var spans = r.ctl.querySelectorAll('.d-seg span');
      return { row: r.row, sel: r.ctl.querySelector('.d-segsel'), btns: spans, on: on };
    }
    R.segEq = seg(cf, S['q.teams'], [2, 3, 4, 5, 6], 0);
    R.segJo = seg(cf, S['q.players'], [1, 2, 3, 4, 5, 6], 3);
    var ct = groupe(col, S['q.grpTeams']);
    R.grpEq = ct.parentNode;
    [[equipe(1), '#DD2E44'], [equipe(2), '#55ACEE']].forEach(function (e, i) {
      var r = rang(ct, fmt(F.teamNo, { n: i + 1 }), '', '<span class="d-in d-in--team">' + e[0] + '</span><span class="d-swatch" style="--c:' + e[1] + '"><i></i></span>');
      if (i) R.swatch2 = r.ctl.lastChild;
    });
    var aside = h('div', 'd-col', body);
    var cp = groupe(aside, S['q.previewTitle'], true);
    cp.style.position = 'relative'; cp.style.overflow = 'hidden';
    R.prev = h('div', 'dprev', cp, '<span class="dprev__av"><img src="' + LOGO + '" alt=""></span><div class="dprev__main">' +
      '<div class="dprev__head"><span class="dprev__name">CreateYourQueue</span><span class="dprev__app">APP</span><span class="dprev__time">20:58</span></div>' +
      '<p><span class="dprev__ment">@everyone</span></p><div class="dprev__embed">' +
      '<p class="dprev__title">' + fmt(B['queue.ann_title'], { name: '<span data-ptitre>Queue</span>' }) + '</p><p class="dprev__by">' + fmt(B['queue.ann_by'], { author: '<b>@Alex</b>' }) + '</p>' +
      '<div>' + [1, 2].map(function (n) { return '<p>' + md(fmt(B['queue.ann_team_line'], { n: n, name: equipe(n), color: '' })) + '<span class="dprev__dot" style="--c:' + (n === 1 ? '#DD2E44' : '#55ACEE') + '"></span></p>'; }).join('') + '</div>' +
      '<p class="dprev__cta">' + md(fmt(B['queue.ann_cta'], { channel: B['names.voice_queue_waiting'] })) + '</p>' +
      '<div class="dprev__fields"><div><span class="dprev__fname">' + B['queue.field_time'] + '</span><b>21:00</b></div><div><span class="dprev__fname">' + B['queue.field_type'] + '</span><b>Scrim</b></div></div>' +
      '<p class="dprev__foot">' + B['queue.ann_footer_join'] + '</p></div><p class="dprev__react"><span>✅</span>1</p></div>');
    R.prevTitre = R.prev.querySelector('[data-ptitre]');
    R.prevBalai = h('span', 'dprev__balai', cp);
    R.cardPrev = cp;
    var cl = groupe(aside, null, true);
    cl.classList.add('d-launch');
    R.launch = h('span', 'd-pill', cl, S['q.launch']);
    R.stop = h('span', 'd-pill d-pill--ghost', cl, S['q.stop']);
    R.state = h('p', 'd-state', cl, fmt(S['q.launchOk'], { channel: B['names.channel_queue_announcement'] }));
    R.cardLaunch = cl;

    // Le suivi, une section par plan
    var sc1 = section('classement', S['fn.leaderboard'], S['fn.leaderboardD']);
    var cc = groupe(sc1, S['se.previewTitle'] + ' · ' + B['names.channel_queue_classement']);
    [[0, 1412], [3, 1388], [ALEX, 1350], [6, 1297], [4, 1264]].forEach(function (x, i) {
      rang(cc, '', '', '').row.innerHTML = '<div class="d-lb"><u>' + (i + 1) + '</u>' + avHtml(x[0]) + '<b>' + G[x[0]].n + '</b></div><span class="d-num" style="margin-left:auto">' + nb(x[1]) + ' MMR</span>';
    });
    var sc2 = section('rangs', S['s.ranks'], S['rk.lead']);
    var cr = groupe(sc2, S['rk.grpList']);
    [[1600, '#B9E2F5'], [1400, '#9AD1C4'], [1250, '#E8C26A'], [1100, '#BFC3C8'], [0, '#C0875A']].forEach(function (x, i) {
      rang(cr, '', '', '').row.innerHTML = '<div class="d-lb"><i class="d-rank" style="--c:' + x[1] + '"></i><b>' + F.ranks[i] + '</b></div><span class="d-num" style="margin-left:auto">' + fmt(F.des, { n: nb(x[0]) }) + '</span>';
    });
    var sc3 = section('mmr', S['s.mmr'], S['mm.lead']);
    var cm = groupe(sc3, S['mm.grpPoints']);
    rang(cm, S['mm.start'], '', nombre(nb(1000)));
    rang(cm, S['mm.win'], '', nombre('25'));
    rang(cm, S['mm.loss'], '', nombre('20'));
    rang(cm, S['mm.mvpBonus'], '', nombre('5'));
    var sc4 = section('saisons', S['s.seasons'], F.seasonsLead);
    var cs = groupe(sc4, S['se2.enabled']);
    rang(cs, S['se2.enabled'], '', inter(true));
    rang(cs, S['se2.resetDay'], '', nombre('1'));
    rang(cs, S['se2.announce'], '', inter(true));
    rang(cs, S['se2.keepHistory'], '', inter(true));
    var sc5 = section('clans', S['fn.clans'], S['fn.clansD']);
    var cn = groupe(sc5, F.clansGroup);
    [['Les Lynx', 12, 0], ['Nova', 9, 3], ['Ronin', 7, 5]].forEach(function (x) {
      rang(cn, '', '', '').row.innerHTML = '<div class="d-lb">' + avHtml(x[2]) + '<b>' + x[0] + '</b></div><span class="d-rt" style="flex:0 0 auto">' + fmt(F.clan, { n: x[1], c: G[x[2]].n }) + '</span>';
    });
    var sc6 = section('programmation', S['s.schedule'], S['sc.lead']);
    var cg = groupe(sc6, S['sc.enabled']);
    rang(cg, S['sc.preset'], '', liste('Scrim 5v5'));
    var rauto = rang(cg, S['sc.enabled'], '', inter(false));
    R.swAuto = rauto.ctl.firstChild;
    rang(cg, S['sc.time'], '', '<span class="d-in d-in--sm">21:00</span>');
    var rj = rang(cg, S['sc.days'], '', '<span class="d-chips">' + F.days.map(function (j) { return '<span><i></i><b>' + j + '</b></span>'; }).join('') + '</span>');
    R.jours = rj.ctl.querySelectorAll('.d-chips i');
    R.cardProg = cg;

    // La sécurité
    var sr = section('antiraid', S['se.grpRaid'], S['se.raidLead']);
    var car = groupe(sr, S['se.grpRaid']);
    rang(car, S['se.threshold'], '', nombre('10', F.uAcc));
    rang(car, S['se.window'], '', nombre('30', F.uSec));
    rang(car, S['se.accountAge'], '', nombre('7', F.uDays));
    var rk = rang(car, S['se.raidKick'], '', inter(false));
    R.swKick = rk.ctl.firstChild;
    R.cardRaid = car;
    var sl = section('antilien', S['se.grpAntilink'], S['se.linkLead']);
    var cli = groupe(sl, F.watched);
    rang(cli, '#' + F.chanGen, '', inter(true));
    rang(cli, '#' + F.chanLfg, '', inter(true));
    rang(cli, '#' + F.clips, '', inter(false));
    var sn = section('nettoyage', S['se.grpClean'], S['se.cleanLead']);
    var cnet = groupe(sn, S['se.grpClean']);
    rang(cnet, S['se.autoclean'], '', inter(true));
    rang(cnet, S['se.autocleanChannel'], '', liste('#' + F.botcmd));
    rang(cnet, S['se.autocleanDelay'], '', liste(F.every24));

    var save = R.save = h('div', 'd-save', d);
    R.saveMsg = h('span', 'd-save__msg', save, S['d.unsaved']);
    var sa = h('span', 'd-save__a', save, '<span>' + S['c.cancel'] + '</span><span>' + S['c.save'] + '</span>');
    R.saveOk = sa.lastChild;
    return R;
  }

  function pip(par) {
    var R = {};
    var p = R.box = h('div', 'pip', par);
    function volet(titre, icone) {
      var v = h('div', '', p);
      v.style.cssText = 'position:absolute;inset:0';
      h('div', 'pip__ph', v, icone + titre);
      return { box: v, body: h('div', 'pip__body', v) };
    }
    var raid = R.raid = volet(F.newMembers, I.bouclier);
    R.raidRows = RAID.map(function (n, i) {
      var r = h('div', 'pr', raid.body, '<span class="k-av" style="--h:' + (i * 67 + 10) + '">' + n.charAt(0).toUpperCase() + '</span><span><b>' + n + '</b><small>' + fmt(F.created, { n: i + 1 }) + '</small></span><span class="pr__tag">' + F.kicked + '</span><i class="pr__trait"></i>');
      return { row: r, tag: r.querySelector('.pr__tag'), trait: r.querySelector('.pr__trait') };
    });
    var lien = R.lien = volet(F.chanGen, '<span class="k-hash">#</span>');
    R.lienMsg = h('div', 'pm', lien.body, '<span class="k-av" style="--h:120">F</span><div class="k-mb"><div class="k-mh"><b class="k-mn">free.skins.gg</b><span class="k-mt">20:59</span></div><p>' + F.freeSkins + ' <a>disc0rd-gift.ru/n1tro</a></p></div>');
    R.lienSys = h('div', 'psys', lien.body, I.bouclier + '<span>' + F.linkRemoved + '</span>');
    var net = R.net = volet(F.botcmd, '<span class="k-hash">#</span>');
    R.netMsgs = [[0, '!rank'], [5, '!stats Lou'], [6, 'test test'], [2, '!elo'], [9, '?'], [3, '!top']].map(function (m) {
      return h('div', 'pm', net.body, avHtml(m[0]) + '<div class="k-mb"><div class="k-mh"><b class="k-mn">' + G[m[0]].n + '</b></div><p>' + m[1] + '</p></div>');
    });
    R.netMsgs.forEach(function (m) { m.style.padding = '2px 4px'; });
    R.netVide = h('div', 'pvide', net.body, '<div>' + I.ok.replace('<svg', '<svg style="width:30px;height:30px;color:#23A55A;margin:0 auto 8px"') + F.cleaned + '</div>');
    return R;
  }

  /* ════════════════════════ le montage ════════════════════════ */
  function film(scene, P) {
    var W = etat.W, H = etat.H;
    var cam = h('div', 'cam', scene);
    // Un second calque sous la caméra, pour les petits coups de zoom à
    // chaque clic : sur la caméra elle-même, ils se battraient avec ses
    // travellings en cours.
    var punch = h('div', 'cam', cam);
    var K = discord(punch, P);
    var D = dashboard(punch, P);
    var Q = pip(punch);
    var cur = h('div', P ? 'doigt' : 'cur', punch, P ? '' : I.curseur);
    var clic = h('div', 'clic', punch);
    var burst = h('div', 'burst', punch);
    var fin = h('div', 'fin', scene, '<div class="fin__in"><img src="' + LOGO + '" alt=""><b>CreateYourQueue</b><span>cyqbot.eu</span><span class="d-pill">' + F.add + '<i>' + I.fleche + '</i></span></div>');
    var noir = h('div', 'noir', scene);

    /* ── mesures, tout à plat ── */
    var hMsg = 52;
    var visibles = Math.floor((K.flux.clientHeight - 30) / hMsg);
    var cFluxA = centre(K.flux);
    var cBot = centre(K.bot);
    var pReac = centre(K.reac);
    var cVz = centre(K.vz);
    var cAttCh = centre(K.chAtt);
    var cWin = centre(K.win);
    // Positions des jetons, dans le repère de la fenêtre Discord
    var jAtt = K.att.map(function (a) { return centre(a.av, K.win); });
    var jEq = [].concat(K.eqSlots[0], K.eqSlots[1]).map(function (s) { return centre(s.av, K.win); });
    var jReac = centre(K.reac, K.win);
    var ordreEq = [].concat(EQ[0], EQ[1]);

    // Le panneau : défilement de la colonne de sections et de la page
    var navMax = Math.max(0, (P ? D.navin.scrollWidth - D.navv.clientWidth : D.navin.scrollHeight - D.navv.clientHeight));
    function navPour(cle) {
      var it = D.nav[cle], b = boite(it, D.navin), vue = P ? D.navv.clientWidth : D.navv.clientHeight;
      var pos = P ? b.x : b.y, taille = P ? b.w : b.h;
      return -Math.max(0, Math.min(navMax, pos + taille / 2 - vue / 2));
    }
    function navPoint(cle, off) { var c = centre(D.nav[cle]); return P ? decale(c, off, 0) : decale(c, 0, off); }
    function markY(cle) { var b = boite(D.nav[cle], D.navin); return b.y + b.h / 2 - 9; }
    var mainH = D.main.clientHeight;
    // Sur ordinateur, seule la colonne de la section défile ; sur téléphone
    // c'est la page entière (le panneau passe en une colonne sous 900 px),
    // et la pilule de navigation reste posée au-dessus.
    var scQ = P ? D.db : D.sec.queue.sc;
    function defile(cle, el, marge) {
      if (P) return -Math.max(0, boite(el, D.win).y - (marge || 0));
      var sc = D.sec[cle].sc, b = boite(el, sc), haut = sc.scrollHeight;
      return -Math.max(0, Math.min(haut - mainH + 40, b.y - (marge || 0)));
    }
    var pNom = centre(D.nomIn);
    var pJo5 = centre(D.segJo.btns[4]);
    var segPas = D.segJo.btns[1].offsetLeft - D.segJo.btns[0].offsetLeft;
    var segPasEq = D.segEq.btns[1].offsetLeft - D.segEq.btns[0].offsetLeft;
    var pSwatch = centre(D.swatch2);
    var pSave = centre(D.saveOk);
    var pLaunch = centre(D.launch);
    var pSwAuto = centre(D.swAuto);
    var pSwKick = centre(D.swKick);
    var cRowNom = centre(D.rowNom);
    var cFormat = centre(D.grpFormat);
    var cEquipes = centre(D.grpEq);
    var cPrev = centre(D.cardPrev);
    var cLaunch = centre(D.cardLaunch);
    var cProg = centre(D.cardProg);
    var cRaid = centre(D.cardRaid);
    var cMain = centre(D.main);
    var yFormat = defile('queue', D.grpFormat, P ? 96 : 60);
    var yPrev = P ? defile('queue', D.cardPrev.parentNode, 96) : 0;
    var yLaunch = defile('queue', D.cardLaunch, P ? 470 : 360);
    var navQ = navPour('queue'), navProg = navPour('programmation'), navRaid = navPour('antiraid');
    var navLien = navPour('antilien'), navNet = navPour('nettoyage');
    var drawerW = K.drawer.offsetWidth;

    var tl = A.createTimeline({ autoplay: false, defaults: { ease: 'outExpo', duration: 600 } });
    function vise(v, t, d, e, panneau) {
      if (P && panneau) v = { x: 0, y: 0, scale: 1 };
      tl.add(cam, { x: v.x, y: v.y, scale: v.scale, duration: d || 1000, ease: e || 'inOutCubic' }, t);
    }
    function va(p, t, d) { tl.add(cur, { x: p.x, y: p.y, duration: d || 700, ease: 'inOutCubic' }, t); }
    function tape(p, t) {
      tl.add(cur, { scale: .8, duration: 100, ease: 'outQuad' }, t)
        .add(cur, { scale: 1, duration: 200, ease: 'outQuad' }, t + 100)
        .set(clic, { x: p.x, y: p.y, scale: .3, opacity: .7 }, t)
        .add(clic, { scale: 1.6, opacity: 0, duration: 520, ease: 'outQuad' }, t + 10)
        .add(punch, { scale: 1.022, duration: 90, ease: 'outQuad' }, t)
        .add(punch, { scale: 1, duration: 480, ease: 'outExpo' }, t + 90);
    }
    function sec(de, vers, t) {
      tl.add(D.sec[de].box, { opacity: 0, y: -4, duration: 180, ease: 'outQuad' }, t)
        .set(D.sec[vers].box, { opacity: 0, y: 8 }, t + 160)
        .add(D.sec[vers].box, { opacity: 1, y: 0, duration: 320, ease: 'outExpo' }, t + 180);
    }
    function marque(cle, t) { if (!P) tl.add(D.mark, { y: markY(cle), duration: 260, ease: 'outExpo' }, t); }
    function inter(sw, t) {
      tl.add(sw.querySelector('.d-swon'), { opacity: 1, duration: 200, ease: 'outQuad' }, t)
        .add(sw.querySelector('.d-swk'), { x: 18, duration: 240, ease: 'outExpo' }, t)
        .add(sw.querySelector('.d-swk i'), { opacity: 1, duration: 200 }, t);
    }
    function navScroll(v, t) { var o = {}; o[P ? 'x' : 'y'] = v; o.duration = 700; o.ease = 'inOutCubic'; tl.add(D.navin, o, t); }

    /* ── états de départ ── */
    var tousSec = Object.keys(D.sec).map(function (c) { return D.sec[c].box; });
    tl.set(cam, { x: 0, y: 0, scale: 1 }, 0)
      .set(punch, { scale: 1 }, 0)
      .set(burst, { opacity: 0 }, 0)
      .set(K.ring, { opacity: 0 }, 0)
      .set([].concat.apply([], K.ombres), { opacity: 0 }, 0)
      .set(K.eqFlash, { opacity: 0 }, 0)
      .set([].concat(K.eqSlots[0], K.eqSlots[1]).map(function (s) { return s.speak; }), { opacity: 0 }, 0)
      .set(noir, { opacity: 1 }, 0)
      .set(K.win, { opacity: 1, x: 0, scale: 1 }, 0)
      .set(D.win, { opacity: 0, x: 150, scale: .97 }, 0)
      .set(Q.box, { opacity: 0, y: 30 }, 0)
      .set([Q.raid.box, Q.lien.box, Q.net.box], { opacity: 0 }, 0)
      .set(fin.firstChild.children, { opacity: 0, y: 14 }, 0)
      .set(fin.firstChild.firstChild, { scale: .85 }, 0)
      .set(cur, { x: W * .7, y: H * .8, opacity: 0, scale: 1 }, 0)
      .set(clic, { opacity: 0 }, 0)
      // Discord
      .set(K.msgs, { opacity: 0, y: 18, scale: .96 }, 0)
      .set(K.list, { y: 0 }, 0)
      .set(K.tape, { opacity: 0 }, 0)
      .set([K.chatA, K.headA, K.phA], { opacity: 1 }, 0)
      .set([K.chatB, K.headB, K.phB], { opacity: 0 }, 0)
      .set(K.chRech.firstChild, { opacity: 1 }, 0)
      .set(K.chAnn.firstChild, { opacity: 0 }, 0)
      .set(K.bot, { opacity: 0, y: 18 }, 0)
      .set(K.verA, { opacity: 1 }, 0)
      .set(K.verB, { opacity: 0, y: 4 }, 0)
      .set(K.reac, { scale: 0 }, 0)
      .set(K.reacMe, { opacity: 0 }, 0)
      .set(K.reacStrip, { y: 0 }, 0)
      .set(K.jetons, { opacity: 0, scale: .4, x: jReac.x, y: jReac.y }, 0)
      .set(K.att.map(function (a) { return a.row; }), { opacity: 0, x: -6 }, 0)
      .set(K.eqHead, { opacity: 0, y: -6, scale: .92 }, 0)
      .set([].concat(K.eqSlots[0], K.eqSlots[1]).map(function (s) { return s.row; }), { opacity: 0, x: -6 }, 0)
      .set(K.badge, { opacity: 0 }, 0)
      .set(K.dim, { opacity: 0 }, 0);
    if (P) tl.set(K.drawer, { x: -(drawerW + 30) }, 0);
    // Panneau
    tl.set(tousSec, { opacity: 0, y: 0 }, 0)
      .set(D.sec.apercu.box, { opacity: 1 }, 0)
      .set(Object.keys(D.sec).map(function (c) { return D.sec[c].sc; }), { y: 0 }, 0)
      .set(D.navin, P ? { x: 0 } : { y: 0 }, 0)
      .set(D.db, { y: 0 }, 0)
      .set(D.mark, { y: markY('apercu') }, 0)
      .set(D.segJo.sel, { x: segPas * 3 }, 0)
      .set(D.segEq.sel, { x: 0 }, 0)
      .set(D.nomHl, { opacity: 0 }, 0)
      .set(D.save, { opacity: 0, y: 16 }, 0)
      .set(D.prevBalai, { x: -100, opacity: 1 }, 0)
      .set(D.prev, { y: 0, opacity: 1 }, 0)
      .set(D.state, { opacity: 0, y: 4 }, 0)
      .set(D.jours, { opacity: 0, scale: .6 }, 0)
      .set(Q.raidRows.map(function (r) { return r.row; }), { opacity: 0, x: 0, y: 8 }, 0)
      .set(Q.raidRows.map(function (r) { return r.tag; }), { opacity: 0, scale: .7 }, 0)
      .set(Q.raidRows.map(function (r) { return r.trait; }), { scaleX: 0 }, 0)
      .set(Q.lienMsg, { opacity: 0, y: 10, scaleY: 1 }, 0)
      .set(Q.lienSys, { opacity: 0, y: 6 }, 0)
      .set(Q.netMsgs, { opacity: 1, x: 0 }, 0)
      .set(Q.netVide, { opacity: 0, scale: .9 }, 0);
    [D.swAuto, D.swKick].forEach(function (sw) {
      tl.set(sw.querySelector('.d-swon'), { opacity: 0 }, 0).set(sw.querySelector('.d-swk'), { x: 0 }, 0).set(sw.querySelector('.d-swk i'), { opacity: 0 }, 0);
    });

    /* ── 1. le problème : un salon qui déborde ── */
    tl.add(noir, { opacity: 0, duration: 600, ease: 'outQuad' }, 0);
    var vChaos = cadre(decale(cFluxA, 0, P ? 40 : 60), P ? 1.06 : 1.14);
    vise(vChaos, 0, T.panneau - 700, 'inOutSine');
    K.msgs.forEach(function (m, i) {
      var t = 250 + i * Math.round((T.panneau - 1900) / CHAOS.length);
      tl.add(m, { opacity: 1, y: 0, scale: 1, duration: 320, ease: 'outBack(1.4)' }, t);
      if (i >= visibles) tl.add(K.list, { y: -(i - visibles + 1) * hMsg, duration: 300, ease: 'outQuad' }, t);
    });
    tl.add(K.tape, { opacity: 1, duration: 300 }, 900).add(K.tape, { opacity: 0, duration: 300 }, T.panneau - 900);

    /* ── 2. le panneau ── */
    var tA = T.panneau - 700;
    // L'un sort avant que l'autre n'entre : deux interfaces en fondu
    // l'une sur l'autre, à mi-course, ne se lisent ni l'une ni l'autre.
    tl.add(K.win, { opacity: 0, x: -150, scale: .95, duration: 480, ease: 'inCubic' }, tA)
      .add(D.win, { opacity: 1, x: 0, scale: 1, duration: 900, ease: 'outExpo' }, tA + 430);
    vise({ x: 0, y: 0, scale: 1 }, tA, 700);
    vise(cadre(centre(D.win), P ? 1 : 1.03), tA + 900, 3000, 'inOutSine');
    tl.add(cur, { opacity: 1, duration: 300 }, T.panneau + 700);
    navScroll(navQ, T.panneau + 2000);
    var pQ = navPoint('queue', navQ);
    va(pQ, T.panneau + 2200, 900);
    var tQ = T.panneau + 3300;
    tape(pQ, tQ); marque('queue', tQ); sec('apercu', 'queue', tQ);

    /* ── 3. le format ── */
    vise(cadre(decale(cRowNom, 120, 30), 1.45), T.format - 1000, 1000, null, true);
    va(pNom, T.format - 900, 700);
    tape(pNom, T.format - 150);
    var tTape = T.format + 250, NOM = 'Scrim 5v5';
    tl.add(D.nomHl, { opacity: 1, duration: 80 }, T.format - 100).add(D.nomHl, { opacity: 0, duration: 60 }, tTape);
    tl.add(D.save, { opacity: 1, y: 0, duration: 500, ease: 'outExpo' }, tTape + 300);
    tl.add(scQ, { y: yFormat, duration: 800, ease: 'inOutCubic' }, T.format + 1500);
    var vFormat = cadre(decale(cFormat, P ? 0 : 60, yFormat + (P ? 40 : 0)), P ? 1.08 : 1.4);
    vise(vFormat, T.format + 1400, 1000, null, true);
    var p5 = decale(pJo5, 0, yFormat);
    va(p5, T.format + 2000, 700);
    var tJo = T.format + 2900;
    tape(p5, tJo);
    tl.add(D.segJo.sel, { x: segPas * 4, duration: 380, ease: 'outExpo' }, tJo);
    var vEq = cadre(decale(cEquipes, P ? 0 : 60, yFormat + (P ? 10 : 0)), P ? 1.08 : 1.35);
    vise(vEq, T.format + 3600, 1000, null, true);
    va(decale(pSwatch, 0, yFormat), T.format + 3800, 900);

    /* ── 4. l'aperçu ── */
    tl.add(scQ, { y: yPrev, duration: 900, ease: 'inOutCubic' }, T.apercu - 700);
    vise(cadre(decale(cPrev, -40, yPrev), 1.6), T.apercu - 700, 1200, null, true);
    va(decale(cPrev, P ? 120 : 100, yPrev + (P ? 200 : 150)), T.apercu - 600, 1000);
    tl.add(D.prevBalai, { x: 380, duration: 1100, ease: 'inOutSine' }, T.apercu + 900);

    /* ── 5. enregistrer, ouvrir ── */
    tl.add(scQ, { y: yLaunch, duration: 800, ease: 'inOutCubic' }, T.ouvrir - 1100);
    vise(cadre(P ? decale(cLaunch, 0, yLaunch + 90) : decale(cLaunch, 30, yLaunch + 20), P ? 1.05 : 1.35), T.ouvrir - 1100, 1000, null, true);
    va(pSave, T.ouvrir - 700, 600);
    var tSave = T.ouvrir + 100;
    tape(pSave, tSave);
    tl.add(D.save, { opacity: 0, y: 16, duration: 300, ease: 'inQuad' }, tSave + 700);
    var pL = decale(pLaunch, 0, yLaunch);
    va(pL, tSave + 800, 600);
    var tOpen = tSave + 1600;
    tape(pL, tOpen);
    tl.set(burst, { x: pL.x, y: pL.y, scale: .5, opacity: .9 }, tOpen + 40)
      .add(burst, { scale: 3, opacity: 0, duration: 700, ease: 'outExpo' }, tOpen + 40);
    tl.add(D.prev, { y: -8, opacity: .5, duration: 300, ease: 'outQuad' }, tOpen + 50)
      .add(D.prev, { y: 0, opacity: 1, duration: 420, ease: 'outExpo' }, tOpen + 400)
      .add(D.state, { opacity: 1, y: 0, duration: 300 }, tOpen + 700);

    /* ── 6. l'annonce dans Discord ── */
    var tB = T.annonce - 1000;
    tl.add(D.win, { opacity: 0, x: 150, scale: .95, duration: 480, ease: 'inCubic' }, tB)
      .add(cur, { opacity: 0, duration: 200 }, tB)
      .set([K.chatA, K.headA, K.phA, K.chRech.firstChild], { opacity: 0 }, tB)
      .set([K.chatB, K.headB, K.phB, K.chAnn.firstChild], { opacity: 1 }, tB)
      .set(K.win, { x: -150 }, tB)
      .add(K.win, { opacity: 1, x: 0, scale: 1, duration: 900, ease: 'outExpo' }, tB + 430);
    vise({ x: 0, y: 0, scale: 1 }, tB, 700);
    var vBot = cadre(decale(cBot, P ? 0 : 60, 0), P ? 1.1 : 1.32);
    vise(vBot, tB + 800, 1000);
    tl.add(K.bot, { opacity: 1, y: 0, duration: 600, ease: 'outExpo' }, T.annonce - 300)
      .add(K.reac, { scale: 1, duration: 450, ease: 'outBack(2.2)' }, T.annonce + 700);
    var pR = pReac;
    tl.set(cur, { x: pR.x + 160, y: pR.y + 120 }, T.annonce + 900).add(cur, { opacity: 1, duration: 250 }, T.annonce + 1000);
    va(pR, T.annonce + 1100, 700);
    var tMe = T.annonce + 2000;
    tape(pR, tMe);
    tl.add(K.reacMe, { opacity: 1, duration: 200 }, tMe);
    // Chaque coche : la pastille sursaute, le compteur roule d'un cran, et
    // l'avatar du joueur part rejoindre le vocal d'attente.
    var tR = [tMe];
    for (var j = 1; j < 10; j++) tR.push(T.annonce + 3100 + (j - 1) * Math.round((T.equipes - T.annonce - 4800) / 9));
    if (!P) vise(cadre(decale(cWin, 0, 0), 1.06), tMe + 300, 1000);
    tl.add(cur, { opacity: 0, duration: 300 }, tMe + 600);
    tR.forEach(function (t, i) {
      tl.add(K.reacStrip, { y: -(i + 1) * 18, duration: 260, ease: 'outBack(1.6)' }, t)
        .add(K.reac, { scale: 1.16, duration: 110, ease: 'outQuad' }, t)
        .add(K.reac, { scale: 1, duration: 300, ease: 'outBack(3)' }, t + 110)
        .set(K.ring, { x: jReac.x, y: jReac.y, scale: .6, opacity: .7 }, t)
        .add(K.ring, { scale: 1.9, opacity: 0, duration: 460, ease: 'outQuad' }, t)
        .set(K.jetons[i], { x: jReac.x, y: jReac.y - 4, scale: .4, opacity: 0 }, t)
        .add(K.jetons[i], { opacity: 1, scale: 1.25, y: jReac.y - 34, duration: 260, ease: 'outBack(2)' }, t);
      if (P) {
        tl.add(K.jetons[i], { x: -20, y: jReac.y - 160 - i * 6, opacity: 0, scale: .8, duration: 700, ease: 'inQuad' }, t + 300);
      } else {
        tl.add(K.jetons[i], { x: jAtt[i].x, duration: 760, ease: 'inOutSine' }, t + 280)
          .add(K.jetons[i], { y: jAtt[i].y, scale: .95, duration: 760, ease: 'inBack(1.4)' }, t + 280)
          .add(K.att[i].row, { opacity: 1, x: 0, duration: 300 }, t + 980)
          .add(K.jetons[i], { opacity: 0, duration: 120 }, t + 1040);
      }
    });
    var tPlein = tR[9] + 1100;
    tl.add(K.badge, { opacity: 1, duration: 300 }, tR[0] + 1000);
    if (P) {
      // Le téléphone ouvre le panneau des salons pour montrer le vocal
      tl.add(K.drawer, { x: 0, duration: 650, ease: 'outExpo' }, tPlein - 600)
        .add(K.dim, { opacity: .5, duration: 400 }, tPlein - 600)
        .add(K.att.map(function (a) { return a.row; }), { opacity: 1, x: 0, duration: 300, delay: A.stagger(60) }, tPlein - 300);
      vise({ x: 0, y: 0, scale: 1 }, tPlein - 700, 800);
    }

    /* ── 7. les équipes, puis le déplacement vocal ──
       Ce que le bot fait mieux que personne, donc filmé de près : le
       vocal d'attente se replie en une rangée d'avatars, les deux vocaux
       d'équipe naissent dessous, et chaque joueur y est déplacé l'un
       après l'autre, avec sa traînée, sous les compteurs qui suivent. */
    var vVz = cadre(decale(cVz, P ? 0 : 30, 10), P ? 1.15 : 1.75);
    vise(vVz, T.equipes - 600, 900);
    tl.add(cam, { x: vVz.x * 1.07, y: vVz.y * 1.07, scale: vVz.scale * 1.07, duration: T.vocal + 3200 - T.equipes, ease: 'inOutSine' }, T.equipes + 300);
    var tPli = T.equipes + 250;
    var rangee = FILE.map(function (_, i) { return { x: jAtt[0].x + i * 19, y: jAtt[0].y }; });
    FILE.forEach(function (g, de) {
      tl.set(K.jetons[de], { x: jAtt[de].x, y: jAtt[de].y, scale: .95, opacity: 1 }, tPli)
        .add(K.jetons[de], { x: rangee[de].x, y: rangee[de].y, scale: .82, duration: 560, ease: 'inOutCubic' }, tPli + 40 + de * 30);
    });
    tl.add(K.att.map(function (a) { return a.row; }), { opacity: 0, duration: 140 }, tPli);
    K.eqHead.forEach(function (hd, i) {
      var t = T.equipes + 1500 + i * 380;
      tl.add(hd, { opacity: 1, y: 0, scale: 1, duration: 520, ease: 'outBack(2)' }, t)
        .add(K.eqFlash[i], { opacity: 1, duration: 120 }, t)
        .add(K.eqFlash[i], { opacity: 0, duration: 700, ease: 'outQuad' }, t + 220);
    });
    var tMove = T.vocal + 150, PAS_MOVE = 250;
    var slots = [].concat(K.eqSlots[0], K.eqSlots[1]);
    ordreEq.forEach(function (g, i) {
      var de = FILE.indexOf(g), t = tMove + i * PAS_MOVE, c = jEq[i];
      tl.add(K.jetons[de], { scale: 1.3, duration: 140, ease: 'outQuad' }, t)
        .add(K.jetons[de], { x: c.x, duration: 760, ease: 'inOutCubic' }, t + 100)
        .add(K.jetons[de], { y: c.y, duration: 760, ease: 'inOutSine' }, t + 100)
        .add(K.jetons[de], { scale: 1, duration: 320, ease: 'outBack(2.6)' }, t + 800)
        .add(slots[i].row, { opacity: 1, x: 0, duration: 240 }, t + 820)
        .add(K.jetons[de], { opacity: 0, duration: 100 }, t + 900)
        // L'anneau vert de Discord : le joueur est arrivé, il parle déjà
        .add(slots[i].speak, { opacity: 1, duration: 100 }, t + 940)
        .add(slots[i].speak, { opacity: 0, duration: 260 }, t + 1500 + (i % 3) * 180);
      K.ombres[de].forEach(function (o, k) {
        var d = 55 * (k + 1);
        tl.set(o, { x: rangee[de].x, y: rangee[de].y, scale: 1.15, opacity: 0 }, t + 100)
          .add(o, { opacity: .38 / (k + 1), duration: 80 }, t + 100 + d)
          .add(o, { x: c.x, duration: 760, ease: 'inOutCubic' }, t + 100 + d)
          .add(o, { y: c.y, duration: 760, ease: 'inOutSine' }, t + 100 + d)
          .add(o, { opacity: 0, duration: 160 }, t + 700 + d);
      });
    });
    var tStart = tMove + 9 * PAS_MOVE + 1400;
    if (P) {
      // Le panneau des salons reste ouvert jusqu'au dernier arrivé : c'est
      // l'image qu'on est venu voir, on la laisse tenir.
      tl.add(K.drawer, { x: -(drawerW + 30), duration: 500, ease: 'inOutCubic' }, tStart - 450)
        .add(K.dim, { opacity: 0, duration: 350 }, tStart - 450);
    }
    vise(vBot, tStart - (P ? 450 : 800), P ? 600 : 900);
    tl.add(K.verA, { opacity: 0, duration: 300, ease: 'outQuad' }, tStart)
      .add(K.verB, { opacity: 1, y: 0, duration: 450, ease: 'outExpo' }, tStart + 120);

    /* ── 8. le suivi ── */
    var tC = T.suivi - 800;
    var MONTAGE = ['classement', 'rangs', 'mmr', 'saisons', 'clans', 'programmation'];
    tl.add(K.win, { opacity: 0, x: -150, scale: .95, duration: 480, ease: 'inCubic' }, tC)
      .set(tousSec, { opacity: 0 }, tC)
      .set(D.sec.classement.box, { opacity: 1, y: 0 }, tC)
      .set(scQ, { y: 0 }, tC)
      .set(D.navin, P ? { x: navPour('classement') } : { y: 0 }, tC)
      .set(D.mark, { y: markY('classement') }, tC)
      .set(D.win, { x: 150 }, tC)
      .add(D.win, { opacity: 1, x: 0, scale: 1, duration: 900, ease: 'outExpo' }, tC + 430);
    // Plan large : les clics se font dans la barre latérale, elle doit rester dans le cadre
    vise(P ? cadre(decale(cMain, 0, -60), 1) : cadre(centre(D.win), 1.03), tC, 900);
    tl.set(cur, { x: W * .55, y: H * .75 }, tC + 600).add(cur, { opacity: 1, duration: 250 }, tC + 700);
    var pasM = Math.round((T.securite - T.suivi - 1600) / MONTAGE.length);
    var tMont = [T.suivi - 200];
    for (var m = 1; m < MONTAGE.length; m++) tMont.push(T.suivi - 200 + m * pasM);
    var navCourant = 0;
    MONTAGE.forEach(function (cle, i) {
      if (!i) return;
      var t = tMont[i];
      var off = P ? navPour(cle) : (cle === 'programmation' ? navProg : 0);
      if (off !== navCourant) { navScroll(off, t - 900); navCourant = off; }
      var p = navPoint(cle, off);
      va(p, t - 500, 450);
      tape(p, t); marque(cle, t); sec(MONTAGE[i - 1], cle, t);
    });
    var tP = tMont[5];
    vise(cadre(decale(cProg, 20, -20), 1.2), tP + 300, 900, null, true);
    va(pSwAuto, tP + 500, 600);
    tape(pSwAuto, tP + 1200);
    inter(D.swAuto, tP + 1200);
    tl.add([D.jours[0], D.jours[2], D.jours[4], D.jours[5]], { opacity: 1, scale: 1, duration: 300, ease: 'outBack(2)', delay: A.stagger(110) }, tP + 1500);

    /* ── 9. la sécurité ── */
    navScroll(navRaid, T.securite - 1300);
    vise(P ? cadre(decale(cMain, 0, -60), 1) : cadre(centre(D.win), 1.03), T.securite - 1300, 900);
    var pRaid = navPoint('antiraid', navRaid);
    va(pRaid, T.securite - 900, 600);
    tape(pRaid, T.securite - 200); marque('antiraid', T.securite - 200); sec('programmation', 'antiraid', T.securite - 200);
    vise(cadre(decale(cRaid, 60, 0), 1.28), T.securite + 200, 900, null, true);
    va(pSwKick, T.securite + 600, 600);
    tape(pSwKick, T.securite + 1300);
    inter(D.swKick, T.securite + 1300);
    var tPip = T.securite + 1700;
    vise(P ? { x: 0, y: 0, scale: 1 } : cadre(decale(cWin, 60, 30), 1.02), tPip - 100, 900);
    tl.add(Q.box, { opacity: 1, y: 0, duration: 600, ease: 'outExpo' }, tPip)
      .add(Q.raid.box, { opacity: 1, duration: 200 }, tPip)
      .add(Q.raidRows.map(function (r) { return r.row; }), { opacity: 1, y: 0, duration: 300, delay: A.stagger(150) }, tPip + 300);
    Q.raidRows.forEach(function (r, i) {
      var t = tPip + 1300 + i * 150;
      tl.add(r.tag, { opacity: 1, scale: 1, duration: 260, ease: 'outBack(2)' }, t)
        .add(r.trait, { scaleX: 1, duration: 260, ease: 'outQuad' }, t + 60)
        .add(r.row, { opacity: .3, x: 14, duration: 400, ease: 'inOutQuad' }, t + 500);
    });
    var tLien = T.securite + 4200;
    var pLienNav = navPoint('antilien', navLien);
    va(pLienNav, tLien - 600, 500);
    tape(pLienNav, tLien); marque('antilien', tLien); sec('antiraid', 'antilien', tLien);
    tl.add(Q.raid.box, { opacity: 0, duration: 200 }, tLien)
      .add(Q.lien.box, { opacity: 1, duration: 200 }, tLien)
      .add(Q.lienMsg, { opacity: 1, y: 0, duration: 400 }, tLien + 200)
      .add(Q.lienMsg, { opacity: 0, scaleY: .4, y: -14, duration: 380, ease: 'inQuad' }, tLien + 1050)
      .add(Q.lienSys, { opacity: 1, y: -58, duration: 400 }, tLien + 1350);
    var tNet = T.securite + 6000;
    var pNetNav = navPoint('nettoyage', navNet);
    va(pNetNav, tNet - 500, 450);
    tape(pNetNav, tNet); marque('nettoyage', tNet); sec('antilien', 'nettoyage', tNet);
    tl.add(Q.lien.box, { opacity: 0, duration: 200 }, tNet)
      .add(Q.net.box, { opacity: 1, duration: 200 }, tNet)
      .add(Q.netMsgs, { opacity: 0, x: -36, duration: 280, ease: 'inQuad', delay: A.stagger(70) }, tNet + 500)
      .add(Q.netVide, { opacity: 1, scale: 1, duration: 400, ease: 'outBack(1.6)' }, tNet + 1100);
    tl.add(Q.box, { opacity: 0, y: 20, duration: 400, ease: 'inQuad' }, T.fin - 400);

    /* ── 10. la fin ── */
    tl.add(cur, { opacity: 0, duration: 250 }, T.fin - 400);
    vise({ x: 0, y: 0, scale: .94 }, T.fin - 300, 900);
    tl.add(D.win, { opacity: 0, scale: .95, duration: 700, ease: 'inOutCubic' }, T.fin - 200)
      .add(fin.firstChild.firstChild, { opacity: 1, scale: 1, y: 0, duration: 700, ease: 'outBack(1.4)' }, T.fin + 300)
      .add([].slice.call(fin.firstChild.children, 1), { opacity: 1, y: 0, duration: 600, delay: A.stagger(160) }, T.fin + 550)
      .add(noir, { opacity: 1, duration: 800, ease: 'inQuad' }, TOTAL - 900)
      .add(noir, { opacity: 1, duration: 10 }, TOTAL);

    /* ── les états qui ne glissent pas : ils basculent ── */
    var COURANT = [[0, 'apercu'], [tQ, 'queue'], [tC, 'classement']];
    MONTAGE.forEach(function (c, i) { if (i) COURANT.push([tMont[i], c]); });
    COURANT.push([T.securite - 200, 'antiraid'], [tLien, 'antilien'], [tNet, 'nettoyage']);
    var navKeys = Object.keys(D.nav);
    etat.tick = function (t) {
      var c = aT(COURANT, t);
      navKeys.forEach(function (key) { classe(D.nav[key], 'is-on', key === c); });
      // Le nom tapé lettre à lettre, et l'aperçu qui le suit
      var nom = t < tTape ? 'Queue' : NOM.slice(0, Math.min(NOM.length, Math.floor((t - tTape) / 85)));
      ecrire(D.nomTxt, nom);
      ecrire(D.prevTitre, nom);
      var focus = t >= T.format - 150 && t < tTape + NOM.length * 85 + 600;
      classe(D.nomIn, 'is-focus', focus);
      D.nomCaret.style.opacity = focus && Math.floor(t / 450) % 2 === 0 ? 1 : 0;
      var jo = t < tJo ? 3 : 4;
      for (var i = 0; i < D.segJo.btns.length; i++) classe(D.segJo.btns[i], 'is-on', i === jo);
      classe(D.segEq.btns[0], 'is-on', true);
      ecrire(D.saveMsg, t < tSave ? S['d.unsaved'] : S['c.saved']);
      ecrire(D.launch, t >= tOpen && t < tOpen + 700 ? S['q.launching'] : S['q.launch']);
      D.stop.style.color = t >= tOpen + 700 ? 'var(--ink)' : '';
      D.stop.style.borderColor = t >= tOpen + 700 ? 'var(--hair)' : '';
      classe(K.chRech, 'is-on', t < tB);
      classe(K.chAnn, 'is-on', t >= tB);
      var n = 0;
      for (var r = 0; r < 10; r++) if (t >= tR[r] + (P ? 300 : 1000)) n++;
      var partis = 0, arrives = [0, 0];
      for (var mv = 0; mv < 10; mv++) {
        if (t >= tMove + mv * PAS_MOVE + 100) partis++;
        if (t >= tMove + mv * PAS_MOVE + 820) arrives[mv < 5 ? 0 : 1]++;
      }
      ecrire(K.badge, (n - partis) + '/10');
      ecrire(K.eqBadge[0], arrives[0] + '/5');
      ecrire(K.eqBadge[1], arrives[1] + '/5');
    };
    etat.cles = {
      chaos: 4200, panneau: T.panneau + 1800, format: T.format + 3300, apercu: T.apercu + 1500, ouvrir: tOpen + 900,
      annonce: tR[9] + 1300, equipes: T.equipes + 2600, vocal: tMove + 5 * PAS_MOVE + 600, suivi: tP + 2200, securite: tPip + 2200, fin: T.fin + 2400
    };
    return tl;
  }


    /* ── le montage ── */
    var P = o.format === 'p';
    etat.W = P ? 450 : 1280; etat.H = P ? 800 : 720;
    hote.classList.add('film');
    hote.innerHTML = '';
    var scene = h('div', 'scene ' + (P ? 'is-p' : 'is-l'), hote);
    scene.setAttribute('lang', LANGUE);
    scene.setAttribute('aria-hidden', 'true');
    scene.style.width = etat.W + 'px'; scene.style.height = etat.H + 'px';
    etat.scene = scene;
    /* L'échelle se prenait sur la seule largeur. Tant que le conteneur
       tombait pile en 16/9 ça passait — mais `aspect-ratio` arrondit, et
       il suffisait d'un pixel de trop en hauteur pour qu'une bande du
       fond apparaisse sous le film : une bordure, encore. On couvre donc
       le conteneur (le plus grand des deux rapports) et on recentre ce
       qui dépasse, comme un `object-fit: cover`. La scène est en
       `transform-origin: 0 0` : la translation vient AVANT l'échelle,
       sinon elle serait multipliée par elle. */
    function echelle() {
      var lh = hote.clientWidth, hh = hote.clientHeight;
      etat.k = Math.max(lh / etat.W, hh / etat.H) || (lh / etat.W);
      var dx = (lh - etat.W * etat.k) / 2, dy = (hh - etat.H * etat.k) / 2;
      scene.style.transform = 'translate(' + dx + 'px, ' + dy + 'px) scale(' + etat.k + ')';
    }
    echelle();
    var tl = film(scene, P);
    var cc = h('div', 'film__cc', hote);
    cc.hidden = true;

    function seek(ms, sousTitres) {
      var t = Math.max(0, Math.min(TOTAL, ms || 0)), cible = t;
      if (o.calme) {
        // Mouvement réduit : un plan fixe par chapitre. La voix continue,
        // l'image ne change qu'aux chapitres, sans rien entre deux.
        var ch = 'chaos';
        CHAPITRES.forEach(function (c) { if (t >= T[c] - 300) ch = c; });
        cible = etat.cles[ch];
      }
      tl.seek(cible);
      if (etat.tick) etat.tick(cible);
      var ligne = null;
      if (sousTitres) VOIX.lignes.forEach(function (l) { if (t >= l.debut * 1000 && t < (l.debut + l.duree) * 1000 + 500) ligne = l; });
      cc.hidden = !ligne;
      if (ligne) ecrire(cc, ligne.texte);
    }
    seek(o.depart != null ? o.depart : etat.cles.annonce);

    return {
      langue: LANGUE, total: TOTAL, cles: etat.cles, seek: seek, echelle: echelle,
      detruire: function () { tl.pause(); hote.innerHTML = ''; }
    };
  }

  window.CYQ_FILM = { creer: creer };
})();
