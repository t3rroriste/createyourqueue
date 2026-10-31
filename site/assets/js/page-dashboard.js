/* =========================================================================
   CreateYourQueue — le panneau d'un serveur

   Contrat d'API inchangé :
     GET   /guilds/{id}          -> { id, name, iconUrl, memberCount,
                                      channels:[{id,name,category,disabled}],
                                      voiceChannels:[…], categories:[…],
                                      roles:[{id,name,position}], botRolePosition,
                                      permissions:[{channel,view,write,manage,state}],
                                      missingPermissions:[…], presets:[…],
                                      settings:{ "mmr.start":1000, … } }
     PATCH /guilds/{id}/settings <- { "clé": valeur }

   Un réglage part DÈS QU'IL CHANGE, seul, et sa rangée dit ce qu'il est
   devenu : en cours, enregistré, ou échoué avec « Réessayer ». Il n'y a
   plus de barre d'enregistrement ni de bouton « Enregistrer » : une page
   de soixante réglages où l'on doit penser à valider en bas est une page
   où l'on perd des modifications.

   Ce fichier ne contient AUCUNE valeur de style. Il pose des classes, des
   attributs d'état et des MESURES (la position de l'indicateur du menu) ;
   tout le dessin, durées et courbes comprises, est dans dashboard.css. La
   seule exception est la couleur des équipes, qui n'est pas un choix de
   design mais une donnée saisie par la personne.

   Ce que app.js fournit déjà, et qu'on réutilise tel quel :
     - le routage des sections (hash, hidden, focus sur le titre) ;
     - les listes déroulantes filtrables au clavier ([data-combo]) ;
     - la validation des champs bornés ([data-min] / [data-max]) ;
     - le segmenté ([.segmented] + son champ caché) ;
     - la traduction, le menu de langue, les liens entre domaines.
   ========================================================================= */
(function () {
  'use strict';

  var t = CYQ.t, esc = CYQ.esc, icon = CYQ.icon;

  var $  = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) {
    return Array.prototype.slice.call((r || document).querySelectorAll(s));
  };

  /* Le panneau ne sait rien afficher sans serveur. Plutôt qu'un écran vide,
     on renvoie au choix du serveur — c'est là que la personne voulait être. */
  var guildId = new URLSearchParams(location.search).get('guild') || '';
  if (!guildId) {
    location.replace(CYQ.appUrl ? CYQ.appUrl('servers.html') : 'servers.html');
    return;
  }
  document.body.setAttribute('data-guild', guildId);
  /* `presets` est une source comme les autres pour la combobox, à ceci
     près que son identifiant EST son nom : le bot range ses presets par
     nom (`get_queue_preset(guild_id, name)`) et `schedule.preset` garde
     un nom, pas un numéro. */
  CYQ.data = { channels: [], voiceChannels: [], categories: [], roles: [], presets: [] };

  var DISCORD   = 'https://discord.com/api/v10';
  var KEY_TOKEN = 'cyq.dtoken';

  /* Les huit couleurs proposées pour une équipe. Ce sont des DONNÉES — la
     couleur que le bot donnera au rôle Discord de l'équipe — et non des
     couleurs d'interface : elles n'apparaissent que dans les pastilles. */
  /* Les douze couleurs d'équipe, et pas une de plus : ce sont exactement
     les ronds de COLOR_PALETTE dans cogs/queue_config.py, dans le même
     ordre. Le bot n'écrit pas un code couleur dans son annonce, il écrit
     l'un de ces ronds — en autoriser d'autres ici donnait un rôle d'une
     teinte et un rond d'une autre. L'ordre compte : il décide de la
     couleur par défaut de chaque équipe, comme chez le bot. */
  var TEAM_COLORS = [
    '#ED4245',  // 🔴 rouge
    '#3B88C3',  // 🔵 bleu
    '#78B159',  // 🟢 vert
    '#FDCB58',  // 🟡 jaune
    '#AA8ED6',  // 🟣 violet
    '#F4900C',  // 🟠 orange
    '#E6E7E8',  // ⚪ blanc
    '#31373D',  // ⚫ noir
    '#C1694F',  // 🟤 marron
    '#F9A7C0',  // 🩷 rose
    '#9CDCF0',  // 🩵 cyan
    '#3B5998'   // 🟦 bleu marine
  ];
  var LOG_TYPES = ['voice', 'messages', 'queue', 'match', 'duel', 'clan', 'commands', 'joins', 'moderation', 'server'];

  var CARET = '<span class="caret">' + icon('caret', 12) + '</span>';
  var SWITCH_TRACK = '<span class="switch__track" aria-hidden="true"><span class="switch__knob"></span></span>';

  /* =======================================================================
     RENDU SYNCHRONE
     Les rangées répétitives sont écrites ICI, à l'analyse de la page, donc
     avant le démarrage de app.js : c'est lui qui câble les listes
     déroulantes et les interrupteurs, et il ne voit que ce qui existe à ce
     moment-là. Tout texte visible porte un data-i18n — la langue de la
     personne n'est connue qu'au démarrage, qui les traduira.
     ======================================================================= */

  function placeholderDe(src) {
    return src === 'roles' ? 'rl.pickRole'
         : src === 'categories' ? 'ch.pickCategory'
         : src === 'presets' ? 'sc.pickPreset'
         : 'ch.pickChannel';
  }
  function sigilDe(src) {
    return src === 'roles' ? '@' : src === 'channels' ? '#' : '';
  }
  /* Ce que dit le bouton quand la liste est lisible mais vide : le serveur
     n'a simplement rien de ce type. Un message par source, parce que
     « aucun » et « aucune » ne se disent pas pareil, et qu'un message
     générique obligerait à relire le libellé pour savoir de quoi on
     parle. */
  function aucunDe(src) {
    return src === 'roles' ? 'd.noRole'
         : src === 'categories' ? 'd.noCategory'
         : src === 'voiceChannels' ? 'd.noVoice'
         : src === 'presets' ? 'p.noPreset'
         : 'd.noChannel';
  }

  (function rendreJournaux() {
    var hote = $('[data-logs]');
    if (!hote) return;
    hote.innerHTML = LOG_TYPES.map(function (k) {
      return '<div class="row row--log" data-log="' + k + '">' +
        '<p class="row__text"><label class="row__label" for="log-' + k + '" id="log-' + k + '-l" data-i18n="lo.' + k + '"></label></p>' +
        '<span class="row__state" data-state aria-hidden="true"></span>' +
        '<div class="row__ctl">' +
          '<div class="combo" data-combo data-source="channels" id="log-chan-' + k + '">' +
            '<input type="hidden" data-setting="log.' + k + '.channel">' +
            /* Le nom accessible enchaîne « Salon du journal », le nom du
               journal, puis le contenu du bouton lui-même : le salon choisi
               fait partie du nom, comme il fait partie de ce qu'on voit. */
            '<button class="combo__button" type="button" id="log-chan-' + k + '-b" ' +
              'aria-labelledby="lbl-log-channel log-' + k + '-l log-chan-' + k + '-b"></button>' +
          '</div>' +
          '<span class="switch"><input type="checkbox" role="switch" id="log-' + k + '" ' +
            'data-setting="log.' + k + '.enabled" data-controls="#log-chan-' + k + '" data-log-toggle>' +
            SWITCH_TRACK + '</span>' +
        '</div>' +
      '</div>';
    }).join('');
  })();

  /* Les rangs. Douze au maximum : au-delà, une barre de progression dans
     /elo ne veut plus rien dire, et le bot refuse de toute façon. */
  var RANGS_MAX = 12;

  (function rendreRangs() {
    var hote = $('[data-ranks]');
    if (!hote) return;
    var html = '';
    for (var i = 0; i < RANGS_MAX; i++) {
      html += '<div class="row row--rank" data-rank="' + i + '" hidden>' +
        '<div class="row__ctl rank">' +
          '<input class="couleur" type="color" value="#f1c40f" ' +
            'data-setting="mmr.rank' + i + '.color" data-i18n-attr="aria-label:rk.color">' +
          '<input class="text rank__nom" type="text" maxlength="32" autocomplete="off" ' +
            'data-setting="mmr.rank' + i + '.name" data-i18n-attr="aria-label:rk.name">' +
          '<span class="num rank__seuil"><input class="num__input" type="number" ' +
            'inputmode="numeric" step="1" min="0" max="100000" value="0" ' +
            'data-min="0" data-max="100000" data-setting="mmr.rank' + i + '.min" ' +
            'data-i18n-attr="aria-label:rk.min"><span class="num__unit">MMR</span></span>' +
          '<button class="rank__suppr" type="button" data-rank-del="' + i + '" ' +
            'data-i18n-attr="aria-label:rk.remove">' + icon('trash', 15) + '</button>' +
        '</div>' +
        '<span class="row__state" data-state aria-hidden="true"></span>' +
      '</div>';
    }
    html += '<input type="hidden" data-setting="mmr.rankCount" value="0">';
    hote.innerHTML = html;
  })();

  (function rendreEquipes() {
    var hote = $('[data-teams]');
    if (!hote) return;
    var html = '';
    for (var i = 0; i < 6; i++) {
      var c = TEAM_COLORS[i];
      html += '<div class="row row--team" data-team="' + i + '"' + (i >= 2 ? ' hidden' : '') + '>' +
        '<div class="row__ctl">' +
          '<div class="swatch-wrap">' +
            '<button class="swatch" type="button" data-swatch="' + i + '" aria-haspopup="true" aria-expanded="false">' +
              '<span class="swatch__dot" data-dot style="--c:' + c + '"></span></button>' +
            '<div class="palette" data-palette="' + i + '">' +
              '<div class="palette__grid">' + TEAM_COLORS.map(function (col) {
                return '<button type="button" data-pick="' + col + '" style="--c:' + col + '" ' +
                  'aria-label="' + col + '" aria-pressed="' + (col === c) + '"></button>';
              }).join('') + '</div>' +
              '<p class="palette__note" data-i18n="q.colorNote"></p>' +
            '</div>' +
            '<input type="hidden" value="' + c + '" data-setting="queue.team' + i + '.color">' +
          '</div>' +
          '<input class="text" type="text" maxlength="32" autocomplete="off" value="Équipe ' + (i + 1) + '" ' +
            'data-setting="queue.team' + i + '.name" data-required data-team-name="' + i + '">' +
        '</div>' +
        '<span class="row__state" data-state aria-hidden="true"></span>' +
      '</div>';
    }
    hote.innerHTML = html;
  })();

  /* Vrai une fois la réponse du serveur reçue. Avant, une liste vide veut
     dire « pas encore lue » ; après, elle veut dire « illisible ». */
  var listesLues = false;

  /* Chaque bouton de liste reçoit son état « rien de choisi » tout de
     suite : app.js ne le dessine qu'après un choix. */
  function peindreCombo(combo) {
    var src = combo.getAttribute('data-source') || 'channels';
    var cache = $('input[type="hidden"]', combo);
    var bouton = $('.combo__button', combo);
    if (!cache || !bouton) return;
    var sigil = sigilDe(src);
    var id = cache.value;
    var pre = sigil ? '<span class="combo__sigil" aria-hidden="true">' + sigil + '</span>' : '';

    /* Une liste vide a DEUX causes, et le bouton disait la même chose pour
       les deux — « Liste indisponible », qui affirme un échec de lecture.

       C'est faux une fois sur deux. Si le serveur a renvoyé des salons
       textuels et des rôles, c'est qu'il sait parfaitement les lire : une
       liste de salons vocaux vide signifie alors qu'il n'y en a aucun sur
       ce serveur, pas qu'on n'a pas pu les voir. Dire « indisponible »
       envoie chercher une panne qui n'existe pas.

       On distingue donc : rien du tout n'a été lu -> indisponible ; le
       reste a été lu mais pas celle-ci -> ce serveur n'en a pas. */
    var liste0 = (CYQ.data && CYQ.data[src]) || [];
    var vide = listesLues && !liste0.length;

    if (vide && !id) {
      var lecturePossible = !!(
        ((CYQ.data && CYQ.data.channels) || []).length ||
        ((CYQ.data && CYQ.data.roles) || []).length
      );
      var cleVide = lecturePossible ? aucunDe(src) : 'd.listUnavailable';

      bouton.innerHTML = pre + '<span class="combo__value is-empty" data-i18n="' + cleVide + '">' +
        esc(t(cleVide)) + '</span>' + CARET;
      /* Dans les deux cas il n'y a rien à choisir, donc rien à ouvrir. */
      bouton.disabled = true;
      return;
    }

    bouton.disabled = false;

    if (!id) {
      var cle = placeholderDe(src);
      bouton.innerHTML = pre + '<span class="combo__value is-empty" data-i18n="' + cle + '">' +
        esc(t(cle)) + '</span>' + CARET;
      return;
    }

    var liste = (CYQ.data && CYQ.data[src]) || [];
    var o = liste.filter(function (x) { return String(x.id) === String(id); })[0];

    if (o) {
      bouton.innerHTML = pre + '<span class="combo__value">' + esc(o.name) + '</span>' + CARET;
    } else if (liste.length) {
      /* La liste est connue et l'identifiant enregistré n'y figure plus :
         le salon a été supprimé côté Discord. On le dit, on n'invente pas
         un nom. */
      var parti = src === 'roles' ? 'rl.deleted' : 'ch.deleted';
      bouton.innerHTML = icon('warn', 12) + '<span class="combo__value is-gone">' +
        esc(t(parti)) + '</span>' + CARET;
    } else {
      /* Liste vide : le serveur n'a pas pu lire les salons (pas de jeton de
         bot). On ne sait pas le nom, on montre l'identifiant enregistré —
         c'est la seule chose vraie qu'on ait. */
      bouton.innerHTML = pre + '<span class="combo__value">' + esc(id) + '</span>' + CARET;
      if (listesLues) bouton.disabled = true;
    }
  }
  $$('[data-combo]').forEach(peindreCombo);

  /* =======================================================================
     DÉMARRAGE — après app.js, qui s'est inscrit le premier sur
     DOMContentLoaded et a donc déjà traduit la page, câblé les listes et
     affiché la bonne section.
     ======================================================================= */

  document.addEventListener('DOMContentLoaded', function () {

    var db     = $('[data-db]');
    var live   = $('[data-live]');
    var noteEl = $('[data-note]');
    var nav    = $('[data-dbnav]');
    var mark   = $('[data-mark]');

    var A = window.anime;
    var force = document.documentElement.classList.contains('motion-force');
    var calme = !force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var etroit = window.matchMedia('(max-width: 900px)');

    var donnees = null;       // la dernière réponse de GET /guilds/{id}
    var avisCourant = null;   // l'avis de page affiché, pour le retraduire
    var remplissage = false;  // vrai pendant remplir() : rien ne part

    /* ------------------------------------------------------- utilitaires */

    function vrai(v) { return v === true || v === 1 || v === '1' || v === 'true' || v === 'on'; }

    /* Le nom annoncé : le libellé de la rangée s'il y en a un, sinon le nom
       du champ lui-même (une équipe n'a pas de libellé, son champ en porte
       un), sinon le titre de la section (le choix de langue). */
    function annoncer(rangee, msg, champ) {
      if (!live) return;
      var nom = '';
      var l = rangee && $('.row__label', rangee);
      if (l) nom = l.textContent.trim();
      else if (champ && champ.getAttribute('aria-label')) nom = champ.getAttribute('aria-label');
      else if (rangee) {
        var h = rangee.closest('[data-section]');
        h = h && $('.sec__title', h);
        if (h) nom = h.textContent.trim();
      }
      /* On vide d'abord : deux annonces identiques à la suite ne seraient
         sinon lues qu'une fois. */
      live.textContent = '';
      requestAnimationFrame(function () {
        live.textContent = nom ? nom + ' — ' + msg : msg;
      });
    }

    function sectionsInertes(oui) {
      $$('[data-section]').forEach(function (s) {
        if (oui) s.setAttribute('inert', ''); else s.removeAttribute('inert');
      });
    }

    /* ==================================================================
       L'ENREGISTREMENT, RÉGLAGE PAR RÉGLAGE
       ================================================================== */

    /* clé -> { champ, rangée, avant }. « avant » est la valeur ENREGISTRÉE,
       celle que « Annuler » remet. Il n'y a plus de file d'envois : une
       seule requête part, et elle part de la barre. */
    var enAttente = {};

    function valeurDe(f) {
      if (f.type === 'checkbox') return f.checked ? '1' : '0';
      if (f.type === 'radio') {
        var c = $('input[type="radio"][name="' + f.name + '"]:checked');
        return c ? c.value : '';
      }
      if (f.type === 'number' || f.getAttribute('data-type') === 'int') {
        return f.value.trim() === '' ? '' : Number(f.value);
      }
      return f.value;
    }

    /* La dernière valeur ENREGISTRÉE d'un champ, celle qui sert de point de
       comparaison et de retour en arrière.

       Les boutons radio sont à part, et c'est ce qui faisait que la langue
       ne s'enregistrait jamais. Cinq champs y portent UNE valeur : celle du
       groupe. Retenir `f.value` revenait à retenir l'étiquette du bouton,
       « en » sur le bouton English, qui ne change évidemment jamais. Le
       comparatif d'`envoyer` trouvait donc toujours « avant » égal à
       « maintenant », retirait la langue de l'attente aussitôt posée, et la
       barre d'enregistrement n'apparaissait même pas. On choisissait
       l'anglais, rien ne partait, et le rechargement remontait le français.

       On retient donc la valeur COCHÉE, et sur TOUS les boutons du groupe :
       ne la poser que sur celui qui vient de bouger laisserait les quatre
       autres croire que rien n'a changé — revenir au français juste après
       aurait été vu comme un non-changement. */
    function retenir(f) {
      if (f.type === 'radio') {
        var choisie = valeurDe(f);
        $$('input[type="radio"][name="' + f.name + '"]').forEach(function (r) {
          r._dernier = choisie;
        });
        return;
      }
      f._dernier = f.type === 'checkbox' ? f.checked : f.value;
    }

    /* L'emplacement d'état de la rangée. Il est réservé dans la mise en
       page : changer d'état n'y change que le contenu et l'opacité. */
    function etat(rangee, s, champ) {
      var slot = rangee && $('[data-state]', rangee);
      if (!slot) return;
      clearTimeout(slot._minuteur);
      slot.setAttribute('data-s', s);
      slot.setAttribute('aria-hidden', s === 'error' ? 'false' : 'true');

      if (s === 'saving') {
        slot.innerHTML = '<span class="row__dot"></span>';
      } else if (s === 'saved') {
        slot.innerHTML = icon('check', 12) + '<span>' + esc(t('c.saved')) + '</span>';
        /* 1,8 s : le temps de lever les yeux vers la rangée après le clic.
           Plus, la confirmation devient du bruit sur une page où l'on
           change dix réglages d'affilée. */
        slot._minuteur = setTimeout(function () { slot.setAttribute('data-s', 'idle'); }, 1800);
      } else if (s === 'error') {
        slot._champ = champ;
        slot.innerHTML = '<button class="row__retry" type="button" data-retry>' +
          icon('warn', 12) + '<span>' + esc(t('c.retry')) + '</span></button>';
      } else if (s === 'local') {
        slot.innerHTML = icon('warn', 12) + '<span>' + esc(t('d.notSaved')) + '</span>';
      }
    }

    function envoyer(f) {
      if (remplissage || !f) return;
      var cle = f.getAttribute('data-setting');
      if (!cle) return;
      var rangee = f.closest('.row');

      /* app.js a déjà validé le champ (son écouteur est posé sur le champ,
         le nôtre sur le document : il passe avant). Une valeur refusée ne
         part pas ; le message d'erreur est déjà sous la rangée. */
      if (f.getAttribute('aria-invalid') === 'true') return;

      /* Un champ obligatoire vidé, ou un nombre effacé, ne part pas non
         plus : on remet la dernière valeur connue. Envoyer « » au bot
         donnerait une queue sans nom. */
      if ((f.hasAttribute('data-required') || f.type === 'number') && String(f.value).trim() === '') {
        if (f._dernier !== undefined) f.value = f._dernier;
        return;
      }

      if (!CYQ.api.configured) { etat(rangee, 'local'); annoncer(rangee, t('d.notSaved'), f); return; }

      /* Rien ne part ici. Le réglage est MIS EN ATTENTE, et c'est la barre
         du bas qui décide — à la manière de Discord.

         Pourquoi avoir renoncé à l'envoi immédiat : sur cette page on règle
         le MMR, les durées de vote, la composition des équipes. Ce sont des
         valeurs qu'on ajuste les unes par rapport aux autres, et chacune
         partait seule. Une configuration à moitié appliquée restait sur le
         serveur dès qu'on s'interrompait, et rien ne permettait de revenir
         en arrière.

         On retient la valeur d'AVANT, pas seulement la nouvelle : c'est ce
         qui rend « Annuler » possible. Si la rangée est déjà en attente, on
         garde le « avant » du premier changement — sinon annuler ne
         ramènerait qu'au dernier état intermédiaire. */
      if (!enAttente[cle]) {
        enAttente[cle] = { champ: f, rangee: rangee, avant: f._dernier };
      } else {
        enAttente[cle].champ = f;
        enAttente[cle].rangee = rangee;
      }

      /* Revenir à la valeur enregistrée retire la rangée de l'attente :
         sans ça, la barre resterait affichée après un aller-retour sur un
         interrupteur, en promettant une modification qui n'existe plus. */
      var avant = enAttente[cle].avant;
      // Même raison que dans `retenir` : pour un groupe de boutons radio,
      // ce qui compte est la valeur cochée, pas celle du bouton cliqué.
      var maintenant = f.type === 'checkbox' ? f.checked
                     : f.type === 'radio' ? valeurDe(f)
                     : f.value;
      if (avant !== undefined && String(avant) === String(maintenant)) {
        delete enAttente[cle];
      }

      etat(rangee, 'idle');
      peindreBarre();
    }

    /* ==================================================================
       LA BARRE D'ENREGISTREMENT
       Elle n'existe que lorsqu'il y a quelque chose à enregistrer, et elle
       est le seul chemin vers le serveur.
       ================================================================== */

    var barre = null;

    function construireBarre() {
      if (barre) return barre;
      barre = document.createElement('div');
      barre.className = 'savebar';
      barre.setAttribute('data-savebar', '');
      barre.hidden = true;
      /* `role="status"` et non `alert` : l'apparition de la barre est une
         information, pas une urgence, et une alerte interromprait la
         lecture à chaque réglage touché. */
      barre.setAttribute('role', 'status');
      barre.setAttribute('aria-live', 'polite');
      barre.innerHTML =
        '<span class="savebar__msg" data-savebar-msg></span>' +
        '<span class="savebar__actions">' +
          '<button class="savebar__cancel" type="button" data-save-cancel>' +
            esc(t('c.cancel')) + '</button>' +
          '<button class="savebar__ok" type="button" data-save-ok>' +
            esc(t('c.save')) + '</button>' +
        '</span>';
      document.body.appendChild(barre);

      $('[data-save-cancel]', barre).addEventListener('click', annulerTout);
      $('[data-save-ok]', barre).addEventListener('click', enregistrerTout);
      return barre;
    }

    function nbAttente() { return Object.keys(enAttente).length; }

    /* Posé plus bas, par le bloc « ouvrir une queue ». La barre d'attente
       est le seul endroit qui sait quand le brouillon change ; c'est donc
       elle qui prévient le bouton, plutôt qu'une minuterie. */
    var majLancement = null;

    function peindreBarre() {
      var n = nbAttente();
      construireBarre();
      if (majLancement) majLancement();

      if (!n) {
        barre.hidden = true;
        barre.removeAttribute('data-s');
        return;
      }

      var msg = $('[data-savebar-msg]', barre);
      if (barre.getAttribute('data-s') !== 'error') {
        msg.textContent = t(n === 1 ? 'd.unsavedOne' : 'd.unsavedMany', { n: n });
      }
      $('[data-save-cancel]', barre).textContent = t('c.cancel');
      $('[data-save-ok]', barre).textContent =
        barre.getAttribute('data-s') === 'saving' ? t('c.saving')
        : barre.getAttribute('data-s') === 'error' ? t('c.retry')
        : t('c.save');
      barre.hidden = false;
    }

    function enregistrerTout() {
      var cles = Object.keys(enAttente);
      if (!cles.length || barre.getAttribute('data-s') === 'saving') return;

      var corps = {};
      cles.forEach(function (c) { corps[c] = valeurDe(enAttente[c].champ); });

      barre.setAttribute('data-s', 'saving');
      $('[data-save-ok]', barre).disabled = true;
      peindreBarre();

      CYQ.api.patch('/guilds/' + encodeURIComponent(guildId) + '/settings', corps)
        .then(function () {
          /* Tout est parti ensemble : chaque rangée le confirme chez elle,
             puis l'attente est vidée et la barre disparaît. */
          cles.forEach(function (c) {
            var e = enAttente[c];
            if (!e) return;
            retenir(e.champ);
            etat(e.rangee, 'saved');
            annoncer(e.rangee, t('c.saved'), e.champ);
            delete enAttente[c];
          });
          barre.removeAttribute('data-s');
          $('[data-save-ok]', barre).disabled = false;
          peindreBarre();
        })
        .catch(function (err) {
          /* L'attente n'est PAS vidée : rien n'a été enregistré, et vider
             ferait croire le contraire. La barre reste, le bouton devient
             « Réessayer ». */
          barre.setAttribute('data-s', 'error');
          $('[data-save-ok]', barre).disabled = false;
          $('[data-savebar-msg]', barre).textContent = t('st.saveFailTitle');
          peindreBarre();
          if (err && err.code === 'UNAUTHORIZED') avis('session');
        });
    }

    function annulerTout() {
      var cles = Object.keys(enAttente);
      if (!cles.length) return;

      /* On rejoue les valeurs d'AVANT par le même chemin que le chargement :
         `remplir` repeint les listes, les segmentés, les dépendances et les
         aperçus, et `remplissage` l'empêche de remettre quoi que ce soit en
         attente. Refaire ce travail à la main ici, c'est l'oublier
         quelque part. */
      var avant = {};
      cles.forEach(function (c) {
        var v = enAttente[c].avant;
        avant[c] = (v === true) ? '1' : (v === false) ? '0' : (v === undefined ? '' : v);
        etat(enAttente[c].rangee, 'idle');
        delete enAttente[c];
      });

      remplir(avant, true);
      rendreTout();
      peindreBarre();
    }

    /* Quitter la page avec des réglages en attente les perdrait sans rien
       dire. Le navigateur impose son propre texte, on ne peut que demander
       la confirmation. */
    window.addEventListener('beforeunload', function (e) {
      if (!nbAttente()) return;
      e.preventDefault();
      e.returnValue = '';
    });

    /* Les champs natifs partent sur « change » : à la case cochée, au choix
       dans la liste, et pour un texte ou un nombre quand on quitte le champ
       — pas à chaque touche. */
    document.addEventListener('change', function (e) {
      var f = e.target;
      if (!f || !f.hasAttribute || !f.hasAttribute('data-setting')) return;
      if (f.type === 'radio' && !f.checked) return;
      envoyer(f);
      /* Une option qui s'allume ouvre sa configuration dans le menu, tout
         de suite — avant même d'être enregistrée. C'est volontaire : on
         vient de demander la fonction, on doit pouvoir la régler sans
         attendre un aller-retour réseau. */
      if ($('[data-sub="' + f.getAttribute('data-setting') + '"]')) syncSousMenus();
    });

    /* Les contrôles dessinés (listes de app.js, segmentés) n'émettent pas de
       « change » : ils émettent « cyq:change ». app.js en émet aussi un
       depuis un champ natif quand sa validité bascule — celui-là est
       ignoré, le « change » natif l'a déjà traité. */
    document.addEventListener('cyq:change', function (e) {
      var cible = e.target;
      if (!cible || !cible.classList) return;
      if (cible.matches('input, select, textarea')) return;

      if (cible.hasAttribute('data-combo')) {
        peindreCombo(cible);
        envoyer($('input[type="hidden"][data-setting]', cible));
        if (cible.getAttribute('data-source') === 'roles') rendreHierarchie();
        if (cible.getAttribute('data-source') === 'presets') verrouProgrammation();
        return;
      }
      if (cible.classList.contains('segmented')) {
        envoyer($('input[type="hidden"][data-setting]', cible.parentNode));
        syncFormat();
      }
    });

    document.addEventListener('click', function (e) {
      var r = e.target.closest ? e.target.closest('[data-retry]') : null;
      if (!r) return;
      /* Il n'y a plus d'envoi par rangée : réessayer, c'est renvoyer le
         lot, et c'est la barre qui le fait. */
      enregistrerTout();
    });

    /* ==================================================================
       LES RANGÉES DÉPENDANTES
       Un réglage qui ne sert à rien tant que son interrupteur est éteint
       n'est pas affiché grisé : il n'est pas affiché. C'est la moitié de
       la légèreté de la page. Il réapparaît sous son interrupteur, en
       descendant de 4 px, quand on l'allume.
       ================================================================== */

    function montrer(rangee, oui) {
      if (!rangee) return;
      var etait = !rangee.hidden;
      rangee.hidden = !oui;
      if (oui && !etait && !remplissage) {
        rangee.classList.remove('is-revealed');
        void rangee.offsetWidth;             // relance l'animation
        rangee.classList.add('is-revealed');
      }
    }

    /* Les sous-entrées du menu. Chacune porte la clé de l'interrupteur qui
       la commande : `data-sub="feature.match"`. Allumer l'option ouvre sa
       configuration dans le menu, l'éteindre la referme.

       Le cas qui compte est le second : si on éteint l'option ALORS QU'ON
       EST sur un de ses écrans, on se retrouverait sur une section dont
       l'entrée de menu a disparu — l'indicateur n'aurait plus rien à
       désigner, et la page semblerait cassée. On revient donc sur Options,
       qui est l'écran d'où la décision vient d'être prise. */
    function syncSousMenus() {
      $$('[data-sub]').forEach(function (bloc) {
        var cle = bloc.getAttribute('data-sub');
        var inter = $('[data-setting="' + cle + '"]');
        var ouvert = !!(inter && inter.checked);
        if (bloc.hidden === !ouvert) return;      // rien à changer
        bloc.hidden = !ouvert;

        if (!ouvert) {
          var courant = $('.navlink[aria-current="page"]', bloc);
          if (courant) location.hash = '#options';
        }
      });
      placerMarque(false);
    }

    function syncDependances() {
      $$('[data-reveal]').forEach(function (sw) {
        sw.getAttribute('data-reveal').split(',').forEach(function (sel) {
          montrer($(sel.trim()), sw.checked);
        });
      });
      var sess = $('#q-session');
      if (sess) montrer($('#q-time-row'), sess.value === 'scheduled');
    }

    $$('[data-reveal]').forEach(function (sw) { sw.addEventListener('change', syncDependances); });
    var sessSel = $('#q-session');
    if (sessSel) sessSel.addEventListener('change', syncDependances);

    /* ==================================================================
       QUEUE PAR DÉFAUT : format, équipes, aperçu
       ================================================================== */

    function segValeur(id) {
      var b = $('#' + id + ' button[aria-pressed="true"]');
      return b ? Number(b.textContent.trim()) : null;
    }
    function poserSeg(id, val) {
      if (val == null || val === '') return;
      $$('#' + id + ' button').forEach(function (b) {
        b.setAttribute('aria-pressed', String(Number(b.textContent.trim()) === Number(val)));
      });
    }

    function syncFormat() {
      var equipes = segValeur('seg-teams') || 2;
      var joueurs = segValeur('seg-players') || 5;
      var ht = $('#q-teams'), hp = $('#q-players');
      if (ht) ht.value = equipes;
      if (hp) hp.value = joueurs;
      /* Le compte « 2 × 5 = 10 joueurs requis » ne s'affiche plus à côté du
         titre : il est déjà dans l'aperçu de l'annonce, et deux fois la
         même phrase sur un écran, c'est une de trop. */
      $$('[data-team]').forEach(function (r, i) { montrer(r, i < equipes); });
      apercuQueue();
    }

    function nommerEquipes() {
      $$('[data-team]').forEach(function (r, i) {
        var n = i + 1;
        var nom = $('[data-team-name]', r);
        var sw = $('[data-swatch]', r);
        if (nom) nom.setAttribute('aria-label', t('q.teamName', { n: n }));
        if (sw) sw.setAttribute('aria-label', t('q.color', { n: n }));
      });
    }

    /* Le gras de Discord, et rien d'autre : les chaînes viennent des
       fichiers de langue du bot, où **…** est la seule mise en forme.
       L'échappement passe AVANT, donc un nom d'équipe ne peut pas
       introduire de balise. */
    function gras(texte) {
      return esc(texte).split('**').map(function (bout, i) {
        return i % 2 ? '<b>' + bout + '</b>' : bout;
      }).join('');
    }

    /* Un trou à remplir après coup, que l'échappement ne peut pas casser :
       il ne reste rien de lui dans le texte échappé s'il n'y est pas. */
    var TROU = '\u0001';

    /* Le nom du salon vocal d'attente, tel qu'il apparaîtra dans la phrase
       d'appel. Non choisi, le bot n'a rien à nommer : un tiret le dit. */
    function nomVocalAttente() {
      var cache = $('[data-setting="channel.waitingVoice"]');
      var id = cache && cache.value;
      if (!id) return '—';
      var liste = (CYQ.data && CYQ.data.voiceChannels) || [];
      for (var i = 0; i < liste.length; i++) {
        if (String(liste[i].id) === String(id)) return liste[i].name;
      }
      return '—';
    }

    /* Qui organise : le compte connecté, puisque c'est lui qui cliquera sur
       « Ouvrir la queue ». Inconnu tant que /me n'a pas répondu. */
    function nomOrganisateur() {
      var el = $('[data-me-name]');
      var pseudo = el && el.textContent ? el.textContent.trim() : '';
      return pseudo || '@organisateur';
    }

    function apercuQueue() {
      var nom = String((($('#q-name') || {}).value || '')).trim();
      var equipes = Number(($('#q-teams') || {}).value || 2);
      var type = String((($('#q-type') || {}).value || '')).trim();
      var sess = $('#q-session');
      var heure = String((($('#q-time') || {}).value || '')).trim();
      var motDePasse = !!($('#fn-qpass') || {}).checked;

      /* Deux aperçus depuis le chantier du Lanceur : celui qu'on regarde
         avant d'ouvrir, et celui de la Programmation. Le premier venu ne
         suffit plus — on écrit dans tous. */
      function poser(sel, html) {
        $$(sel).forEach(function (el) { el.innerHTML = html; });
      }

      /* « Nouveau {name} » : le bot met le nom DANS son titre, il ne le
         remplace pas. Sans nom il écrirait « Nouveau  », d'où le repli
         « Queue », qui est le sien (queue_config.py). */
      poser('[data-qprev-title]', esc(t('qa.title', { name: nom || 'Queue' })));

      poser('[data-qprev-by]', gras(t('qa.by', { author: TROU }))
        .replace(TROU, '<span class="dprev__ment">' + esc(nomOrganisateur()) + '</span>'));

      var lignes = '';
      for (var i = 0; i < equipes; i++) {
        var r = $('[data-team="' + i + '"]');
        if (!r) continue;
        var tn = String($('[data-team-name]', r).value || '').trim();
        var col = $('input[type="hidden"]', r).value;
        /* {color} est un emoji rond dans le message : ici une pastille de
           la même teinte, posée après le nom comme le fait le bot. */
        lignes += '<p>' + gras(t('qa.teamLine', { n: i + 1, name: tn, color: TROU }))
          .replace(TROU, '<span class="dprev__dot" style="--c:' + col + '"></span>') + '</p>';
      }
      poser('[data-qprev-teams]', lignes);

      /* Le bot n'écrit la ligne Session que si elle est renseignée. */
      var libSession = sess && sess.selectedOptions && sess.selectedOptions[0]
        ? sess.selectedOptions[0].textContent.trim() : '';
      $$('[data-qprev-session]').forEach(function (ls) {
        ls.innerHTML = libSession ? gras(t('qa.session', { value: libSession })) : '';
        ls.hidden = !libSession;
      });

      poser('[data-qprev-cta]', gras(t(motDePasse ? 'qa.ctaPassword' : 'qa.cta',
                                       { channel: nomVocalAttente() })));

      poser('[data-qprev-ftime]', esc(t('qa.fieldTime')));
      poser('[data-qprev-ftype]', esc(t('qa.fieldType')));
      /* Le tiret est celui du bot : `cfg.get('heure') or '—'`. Une queue à
         la demande n'a pas d'heure d'ouverture — le champ en garde une en
         mémoire pour le jour où on programmera, mais l'annonce, elle, ne
         doit pas annoncer un rendez-vous qui n'existe pas. */
      var programmee = sess && sess.value === 'scheduled';
      poser('[data-qprev-vtime]', esc((programmee && heure) || '—'));
      poser('[data-qprev-vtype]', esc(type || '—'));
      poser('[data-qprev-foot]', esc(t(motDePasse ? 'qa.footerPassword' : 'qa.footerJoin')));

      /* La barre de l'embed. Le bot garde son noir d'origine tant qu'aucune
         couleur n'est choisie, et le noir sur fond sombre ne se voit pas :
         l'apercu laisse alors sa teinte sourde plutot que de montrer une
         barre invisible qui ferait croire a un bug. */
      var teinte = ($('[data-setting="queue.embedColor"]') || {}).value || '';
      var choisie = /^#[0-9a-f]{6}$/i.test(teinte) && teinte.toLowerCase() !== '#000000';
      $$('[data-qprev] .dprev__embed').forEach(function (embed) {
        if (choisie) { embed.style.setProperty('--barre', teinte); }
        else { embed.style.removeProperty('--barre'); }
      });

      var d = new Date();
      var heureDite = (d.getHours() < 10 ? '0' : '') + d.getHours() + ':' +
                      (d.getMinutes() < 10 ? '0' : '') + d.getMinutes();
      $$('[data-qprev-clock]').forEach(function (h) { h.textContent = heureDite; });
    }

    ['#q-name', '#q-type', '#q-session', '#q-time', '#q-cvote', '#fn-qpass', '#q-embedcolor'].forEach(function (s) {
      var el = $(s);
      if (!el) return;
      el.addEventListener('input', apercuQueue);
      el.addEventListener('change', apercuQueue);
    });
    $$('[data-team-name]').forEach(function (el) { el.addEventListener('input', apercuQueue); });

    /* ================== les rangs ====================================
       Le compte est un réglage comme un autre : c'est lui qui dit au bot
       combien de rangs garder. Les rangées au-delà sont cachées, pas
       supprimées — on en rouvre une sans rien reconstruire. */

    function nbRangs() {
      var c = $('[data-setting="mmr.rankCount"]');
      return Math.max(0, Math.min(RANGS_MAX, Number((c || {}).value || 0)));
    }

    function peindreRangs() {
      var n = nbRangs();
      $$('[data-rank]').forEach(function (r, i) { montrer(r, i < n); });
      var ajouter = $('[data-rank-add]');
      if (ajouter) ajouter.disabled = n >= RANGS_MAX;
    }

    function poserNbRangs(n) {
      var c = $('[data-setting="mmr.rankCount"]');
      if (!c) return;
      c.value = String(Math.max(0, Math.min(RANGS_MAX, n)));
      peindreRangs();
      envoyer(c);
    }

    document.addEventListener('click', function (e) {
      var ajout = e.target.closest ? e.target.closest('[data-rank-add]') : null;
      if (ajout) {
        var n = nbRangs();
        if (n >= RANGS_MAX) return;
        /* Le nouveau rang part du seuil le plus haut plus cent : un rang
           créé au même seuil qu'un autre serait ignoré par le bot, qui
           range ses paliers par seuil croissant. */
        var dernier = $('[data-rank="' + (n - 1) + '"]');
        var depart = dernier ? Number($('.num__input', dernier).value || 0) + 100 : 0;
        var rangee = $('[data-rank="' + n + '"]');
        if (rangee) {
          $('.rank__nom', rangee).value = t('rk.newName', { n: n + 1 });
          $('.num__input', rangee).value = String(depart);
          envoyer($('.rank__nom', rangee));
          envoyer($('.num__input', rangee));
        }
        poserNbRangs(n + 1);
        return;
      }

      var suppr = e.target.closest ? e.target.closest('[data-rank-del]') : null;
      if (suppr) {
        /* On retire le dernier et on décale les suivants : le bot reçoit
           une liste, pas des cases numérotées — un trou au milieu ferait
           disparaître tous les rangs qui suivent. */
        var index = Number(suppr.getAttribute('data-rank-del'));
        var total = nbRangs();
        for (var k = index; k < total - 1; k++) {
          var ici = $('[data-rank="' + k + '"]'), suite = $('[data-rank="' + (k + 1) + '"]');
          if (!ici || !suite) continue;
          [['.rank__nom', 'value'], ['.num__input', 'value'], ['.couleur', 'value']]
            .forEach(function (paire) {
              $(paire[0], ici)[paire[1]] = $(paire[0], suite)[paire[1]];
              envoyer($(paire[0], ici));
            });
        }
        poserNbRangs(total - 1);
        return;
      }
    });

    /* ---- la palette d'une équipe ---- */

    function fermerPalettes(sauf) {
      $$('[data-palette]').forEach(function (p) {
        if (p === sauf) return;
        p.classList.remove('is-open');
        var b = $('[data-swatch="' + p.getAttribute('data-palette') + '"]');
        if (b) b.setAttribute('aria-expanded', 'false');
      });
    }

    function peindreEquipe(r, col) {
      var dot = $('[data-dot]', r);
      if (dot) dot.style.setProperty('--c', col);
      $$('[data-pick]', r).forEach(function (b) {
        b.setAttribute('aria-pressed', String(b.getAttribute('data-pick').toLowerCase() === String(col).toLowerCase()));
      });
    }

    function poserCouleur(r, col) {
      if (!r) return;
      var cache = $('input[type="hidden"]', r);
      if (!cache) return;
      cache.value = col;
      peindreEquipe(r, col);
      apercuQueue();
      envoyer(cache);
    }

    document.addEventListener('click', function (e) {
      var sw = e.target.closest ? e.target.closest('[data-swatch]') : null;
      var pick = e.target.closest ? e.target.closest('[data-pick]') : null;
      var dans = e.target.closest ? e.target.closest('[data-palette]') : null;

      if (sw) {
        var p = $('[data-palette="' + sw.getAttribute('data-swatch') + '"]');
        var ouvert = p.classList.contains('is-open');
        fermerPalettes(p);
        p.classList.toggle('is-open', !ouvert);
        sw.setAttribute('aria-expanded', String(!ouvert));
        if (!ouvert) {
          var cur = $('[aria-pressed="true"]', p) || $('[data-pick]', p);
          if (cur) cur.focus();
        }
        return;
      }
      if (pick) {
        var r = pick.closest('[data-team]');
        poserCouleur(r, pick.getAttribute('data-pick'));
        fermerPalettes(null);
        $('[data-swatch]', r).focus();
        return;
      }
      if (!dans) fermerPalettes(null);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      var ouverte = $('[data-palette].is-open');
      if (!ouverte) return;
      fermerPalettes(null);
      var b = $('[data-swatch="' + ouverte.getAttribute('data-palette') + '"]');
      if (b) b.focus();
    });

    /* ================== montrer ou cacher le mot de passe =============
       Le choix tient dans ce navigateur, sur cet appareil : il ne regarde
       ni le serveur ni les autres organisateurs. localStorage peut être
       refusé (navigation privée, réglages stricts) — on s'en passe alors
       sans rien casser, le champ reste simplement masqué. */

    (function oeilDuMotDePasse() {
      var champ = $('#q-passval');
      var oeil = $('[data-mdp-oeil]');
      if (!champ || !oeil) return;

      var CLE = 'cyq.mdp.visible';

      function retenu() {
        try { return localStorage.getItem(CLE) === '1'; } catch (e) { return false; }
      }
      function retenir(v) {
        try { localStorage.setItem(CLE, v ? '1' : '0'); } catch (e) { /* tant pis */ }
      }

      var OUVERT = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
      var BARRE = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7a9.6 9.6 0 0 1 5 1.4M22 12s-3.5 7-10 7a9.6 9.6 0 0 1-5-1.4"/><path d="M4 4l16 16"/></svg>';

      function poser(visible) {
        champ.type = visible ? 'text' : 'password';
        oeil.innerHTML = visible ? BARRE : OUVERT;
        oeil.setAttribute('aria-pressed', String(visible));
        oeil.setAttribute('aria-label', t(visible ? 'q.passwordHide' : 'q.passwordShow'));
      }

      oeil.addEventListener('click', function () {
        var visible = champ.type === 'password';
        poser(visible);
        retenir(visible);
        champ.focus();
      });

      poser(retenu());
    })();

    /* ==================================================================
       OUVRIR UNE QUEUE DEPUIS LE SITE

       Le site ne compose rien et n'écrit rien dans Discord : il demande à
       l'API d'ouvrir la queue avec la configuration ENREGISTRÉE, et l'API
       passe la main au bot. Deux conséquences tenues ici :

         — tant que des modifications ne sont pas enregistrées, le bouton
           est fermé. Ouvrir avec ce qu'affiche l'écran alors que le bot
           lira autre chose serait le pire des deux mondes ;
         — rien n'est annoncé avant la réponse. Un « queue ouverte »
           affiché par optimisme, suivi d'un salon vide, coûte plus cher
           qu'un bouton qui prend deux secondes.
       ================================================================== */

    (function ouvrirQueue() {
      var btn = $('[data-launch]');
      if (!btn) return;
      var ligne = $('[data-launch-state]');
      var label = $('[data-launch-label]');
      var enCours = false;
      /* La ligne sert à deux choses : dire pourquoi on ne peut pas ouvrir,
         et dire ce qu'a donné le dernier essai. On garde donc l'issue —
         la clé ET ses variables — et non un simple drapeau : un
         empêchement passager (le temps d'un enregistrement) prend la
         ligne, puis la rend, et le « queue ouverte » revient au lieu de
         disparaître pour de bon. Il ne s'efface qu'au prochain essai. */
      var resultat = null;


    /* Pose une animation et la retire une fois jouée. Sans le retrait, la
       classe rejouerait le mouvement à chaque retour sur la section. */
    function anime(el, classe) {
      if (!el) return;
      el.classList.remove(classe);
      // lecture forcée : sans elle, retirer puis remettre dans le même
      // cadre ne redémarre pas l'animation.
      void el.offsetWidth;
      el.classList.add(classe);
      setTimeout(function () { el.classList.remove(classe); }, 900);
    }

      function dire(cle, vars) {
        if (!ligne) return;
        ligne.textContent = cle ? t(cle, vars || {}) : '';
        ligne.hidden = !cle;
        if (cle) anime(ligne, 'is-neuf');
      }

      /* Dernier recours seulement : si le bot ne dit pas où il a publié, on
         nomme le salon d'annonces de ce panneau. Il peut se tromper — la
         configuration qui fait foi est la sienne — d'où le « recours ». */
      function salonAnnonces() {
        var c = $('[data-setting="channel.announcements"]');
        return c && c.value ? String(c.value) : '';
      }

      /* Le nom plutôt que l'identifiant : « ouverte dans #annonces » se
         vérifie d'un coup d'œil, « ouverte dans 913… » ne se vérifie pas. */
      function nomSalon(id) {
        var liste = (CYQ.data && CYQ.data.channels) || [];
        for (var i = 0; i < liste.length; i++) {
          if (String(liste[i].id) === String(id)) return '#' + liste[i].name;
        }
        return '#' + id;
      }

      /* Un empêchement prime sur le compte rendu, le temps qu'il dure :
         tant qu'on ne peut pas ouvrir, savoir ce qu'a donné l'essai
         précédent n'aide pas. Il ne l'efface pas pour autant. */
      function empeche(cle) { btn.disabled = true; dire(cle); }

      /* Ce qui empêche d'ouvrir — salon manquant, assistant jamais passé,
         queue déjà en cours — c'est le BOT qui le sait : sa configuration
         n'est pas celle que ce panneau enregistre. On ne refuse donc ici
         que ce qui est vrai depuis le navigateur, et on laisse le bot
         répondre pour le reste, quitte à ce que ce soit après le clic. */
      function reevaluer() {
        if (enCours) return;
        if (!CYQ.api.configured) return empeche('q.launchNoApi');
        if (nbAttente())         return empeche('q.launchUnsaved');
        btn.disabled = false;
        dire(resultat && resultat.cle, resultat && resultat.vars);
      }

      /* Une issue d'essai : affichée tout de suite, et gardée pour être
         réaffichée après un empêchement passager. */
      function issue(cle, vars) {
        resultat = { cle: cle, vars: vars || {} };
        dire(cle, vars);
      }

      btn.addEventListener('click', function () {
        if (btn.disabled || enCours) return;
        enCours = true;
        resultat = null;          // un nouvel essai efface le précédent
        btn.disabled = true;
        if (label) label.textContent = t('q.launching');
        dire(null);

        var salon = salonAnnonces();

        CYQ.api.post('/guilds/' + encodeURIComponent(guildId) + '/queue/open', {})
          .then(function (rep) {
            // L'aperçu part vers Discord : c'est le message qu'on vient
            // d'envoyer, et il revient vide pour la prochaine queue.
            anime($('[data-section="queue"] [data-qprev]'), 'is-envoi');
            issue('q.launchOk', { channel: nomSalon((rep && rep.channelId) || salon) });
          })
          .catch(function (e) {
            /* Les motifs viennent du bot, mot pour mot (dashboard_api.py).
               Chacun se répare à un endroit différent : le dire vaut mieux
               qu'un « erreur » qui laisse chercher. */
            var motifs = {
              cooldown: 'q.launchCooldown',
              already_open: 'q.launchBusy',
              no_channel: 'q.launchNoChannel',
              setup_incomplete: 'q.launchSetup',
              no_config: 'q.launchNoConfig',
              missing_permissions: 'q.launchPerms'
            };
            var cle = e && motifs[e.motif];
            /* Tout le reste — API muette, bot éteint, 500 — se dit d'une
               seule façon : rien n'a été ouvert. */
            issue(cle || 'q.launchErr');
          })
          .then(function () {
            enCours = false;
            if (label) label.textContent = t('q.launch');
            reevaluer();
          });
      });

      /* ---------------- fermer la queue en cours ---------------------
         Fermer supprime l'annonce, les salons d'équipe et purge le salon
         de commande : rien ne se récupère ensuite. D'où un second clic —
         pas une fenêtre de confirmation, qu'on apprend à cliquer sans
         lire, mais le bouton lui-même qui change de mot et qui se
         désarme tout seul si on le laisse. */
      var stop = $('[data-stop]');
      var stopLabel = $('[data-stop-label]');
      var arme = null;              // minuterie du désarmement

      function desarmer() {
        if (arme) { clearTimeout(arme); arme = null; }
        if (stopLabel) stopLabel.textContent = t('q.stop');
        if (stop) stop.classList.remove('is-armed');
      }

      function majStop() {
        if (!stop) return;
        stop.disabled = !CYQ.api.configured || enCours;
        if (stop.disabled) desarmer();
      }

      if (stop) {
        stop.addEventListener('click', function () {
          if (stop.disabled || enCours) return;

          if (!arme) {
            stop.classList.add('is-armed');
            stopLabel.textContent = t('q.stopConfirm');
            issue('q.stopWarn');
            /* 15 s : le temps de lire l'avertissement, qui fait deux
               lignes, et de décider. À 6 s on se faisait désarmer en
               plein milieu de la phrase. */
            arme = setTimeout(desarmer, 15000);
            return;
          }

          desarmer();
          enCours = true;
          resultat = null;
          stop.disabled = true;
          btn.disabled = true;
          stopLabel.textContent = t('q.stopping');
          dire(null);

          CYQ.api.post('/guilds/' + encodeURIComponent(guildId) + '/queue/close', {})
            .then(function (rep) {
              anime($('[data-section="queue"] [data-qprev]'), 'is-retrait');
              issue('q.stopOk', { n: (rep && rep.players) || 0 });
            })
            .catch(function (e) {
              issue(e && e.motif === 'no_queue' ? 'q.stopNone'
                  : e && e.motif === 'missing_permissions' ? 'q.launchPerms'
                  : 'q.stopErr');
            })
            .then(function () {
              enCours = false;
              stopLabel.textContent = t('q.stop');
              reevaluer();
              majStop();
            });
        });
      }

      majLancement = function () { reevaluer(); majStop(); };
      reevaluer();
      majStop();
    })();

    /* ==================================================================
       MMR : l'effet des valeurs, calculé à partir des champs
       ================================================================== */

    function lireNombre(sel, dflt) {
      var el = $(sel);
      var v = el ? Number(el.value) : NaN;
      return isNaN(v) ? dflt : v;
    }
    function nombre(n) { return Number(n).toLocaleString(CYQ.lang); }
    function signe(n) { return (n > 0 ? '+' : n < 0 ? '−' : '±') + nombre(Math.abs(n)); }

    function simuler() {
      var hote = $('[data-sim]');
      if (!hote) return;
      var depart = lireNombre('#f-start', 1000);
      var victoire = lireNombre('#f-win', 25);
      var defaite = lireNombre('#f-loss', -18);
      var mvp = lireNombre('#f-mvp', 0);
      var mvpOn = mvp > 0;

      var a = depart, b = a + victoire, c = b + victoire + mvp, d = c + defaite;
      var rapport = defaite === 0 ? null : Math.abs(victoire / defaite);
      var bancal = rapport === null || rapport > 5;

      function ligne(lib, delta, total, somme) {
        return '<div class="sim__row' + (somme ? ' sim__row--sum' : '') + '">' +
          '<span class="sim__label">' + esc(lib) + '</span>' +
          (delta === null ? '' : '<span class="sim__delta">' + signe(delta) + '</span>') +
          '<span class="sim__total">' + total + '</span></div>';
      }
      hote.innerHTML =
        ligne(t('mm.first'), null, nombre(a)) +
        ligne(t('mm.aWin'), victoire, nombre(b)) +
        (mvpOn ? ligne(t('mm.aWinMvp'), victoire + mvp, nombre(c)) : '') +
        ligne(t('mm.aLoss'), defaite, nombre(mvpOn ? d : b + defaite)) +
        ligne(t('mm.ratio'), null,
          rapport === null ? '∞' : rapport.toLocaleString(CYQ.lang, { maximumFractionDigits: 1 }) + ' : 1', true);
      var w = $('[data-sim-warn]');
      if (w) w.hidden = !bancal;
    }
    ['#f-start', '#f-win', '#f-loss', '#f-mvp'].forEach(function (s) {
      var el = $(s);
      if (el) el.addEventListener('input', simuler);
    });

    /* ==================================================================
       LOGS : le compte des journaux actifs
       ================================================================== */

    function compterJournaux() {
      var n = $$('[data-log-toggle]').filter(function (c) { return c.checked; }).length;
      var g = $('[data-logs-count]');
      if (g) g.textContent = t('lo.enabledCount', { n: n });
      var nv = $('[data-nav-count="logs"]');
      if (nv) nv.textContent = n + '/10';
    }
    $$('[data-log-toggle]').forEach(function (c) { c.addEventListener('change', compterJournaux); });

    /* ==================================================================
       LES JOURS DE LA SEMAINE (file programmée)
       Sept cases, et non sept boutons : les noms changent avec la langue,
       et sept vraies checkbox donnent au clavier la navigation par groupe
       qu'un aria-pressed lui retire. La valeur enregistrée est « 0,5,6 »,
       parce qu'un réglage du panneau est une chaîne.
       ================================================================== */

    function rendreJours() {
      var hoteJours = $('[data-days]');
      if (!hoteJours || hoteJours.children.length) return;
      var noms = (t('sc.dayNames') || 'L,M,M,J,V,S,D').split(',');
      hoteJours.innerHTML = noms.map(function (nom, i) {
        return '<span class="jour">' +
          '<input class="jour__box" type="checkbox" id="jour-' + i + '" data-day="' + i + '">' +
          '<label class="jour__lab" for="jour-' + i + '">' + CYQ.esc(nom.trim()) + '</label>' +
        '</span>';
      }).join('');
    }

    /* Les cases vers le champ caché, et l'inverse. Le champ est la seule
       valeur que l'enregistrement connaît : les cases ne sont qu'un
       affichage, et elles doivent le suivre après un « Annuler ». */
    function joursVersChamp() {
      var champ = $('[data-setting="schedule.days"]');
      if (!champ) return;
      var coches = $$('[data-day]').filter(function (c) { return c.checked; })
        .map(function (c) { return c.getAttribute('data-day'); });
      champ.value = coches.join(',');
      champ.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function champVersJours() {
      var champ = $('[data-setting="schedule.days"]');
      if (!champ) return;
      var voulus = String(champ.value || '').split(',');
      $$('[data-day]').forEach(function (c) {
        c.checked = voulus.indexOf(c.getAttribute('data-day')) !== -1;
      });
    }

    document.addEventListener('change', function (e) {
      if (e.target && e.target.hasAttribute && e.target.hasAttribute('data-day')) {
        /* Pendant le remplissage, c'est le champ qui commande : réagir
           ici renverrait sa propre valeur et marquerait la section comme
           modifiée alors que personne n'a rien touché. */
        if (!remplissage) joursVersChamp();
      }
      if (e.target && e.target.getAttribute &&
          e.target.getAttribute('data-setting') === 'schedule.days') {
        champVersJours();
      }
    });

    /* ==================================================================
       ANTI-LIEN
       Une rangée par salon textuel, et une seule construction : les
       rangées portent l'état coché, et les refabriquer après `remplir`
       l'effacerait. D'où l'appel au chargement, avant le remplissage.
       ================================================================== */

    function rendreAntilien() {
      var hote = $('[data-antilink]');
      if (!hote) return;
      var liste = (CYQ.data && CYQ.data.channels) || [];

      /* Aucun salon : il y a DEUX raisons, très différentes, et les
         confondre envoie chercher une panne qui n'existe pas. C'est la même
         distinction que `peindreCombo` fait pour les menus — on la refait
         ici au lieu de se taire.

         Se taire était le comportement d'avant, et il donnait l'écran que
         personne ne sait lire : un titre, une phrase d'explication, un
         champ « Filtrer les salons »… et rien en dessous. Rien ne dit si ce
         serveur n'a aucun salon textuel, si le panneau n'a pas pu les lire,
         ou si la page est cassée. */
      if (!liste.length) {
        /* Avant le premier chargement, ou sans API : la section est inerte
           et un avis global le dit déjà. Inutile d'en rajouter ici. */
        if (!listesLues) { hote.innerHTML = ''; return; }
        var cleVide = ((CYQ.data && CYQ.data.roles) || []).length
          ? 'd.noChannel' : 'd.listUnavailable';
        hote.innerHTML = '<div class="row row--stack">' +
          '<p class="row__note" data-i18n="' + cleVide + '">' +
          esc(t(cleVide)) + '</p></div>';
        return;
      }
      hote.innerHTML = liste.map(function (c) {
        var id = String(c.id);
        return '<div class="row" data-antilink-row data-nom="' +
            CYQ.esc(String(c.name || '').toLowerCase()) + '">' +
          '<p class="row__text"><label class="row__label" for="al-' + id + '">#' +
            CYQ.esc(c.name || id) + '</label></p>' +
          '<span class="row__state" data-state aria-hidden="true"></span>' +
          '<div class="row__ctl"><span class="switch">' +
            '<input type="checkbox" role="switch" id="al-' + id + '" ' +
              'data-setting="antilink.' + id + '">' +
            SWITCH_TRACK + '</span></div>' +
        '</div>';
      }).join('');
      /* Les interrupteurs neufs ne sont pas câblés : wireSwitches ne passe
         qu'une fois, au chargement de app.js. L'enregistrement, lui, est
         délégué sur `document` et marche sans rien. */
      if (CYQ.wireSwitches) CYQ.wireSwitches(hote);
    }

    /* Le filtre ne cherche que dans le nom du salon : c'est tout ce que la
       rangée montre, et filtrer sur un identifiant que personne ne lit
       donnerait des disparitions inexplicables. */
    var filtreAnti = $('[data-antilink-filtre]');
    if (filtreAnti) {
      filtreAnti.addEventListener('input', function () {
        var q = filtreAnti.value.trim().toLowerCase();
        $$('[data-antilink-row]').forEach(function (r) {
          r.hidden = q !== '' && r.getAttribute('data-nom').indexOf(q) === -1;
        });
      });
    }

    /* ==================================================================
       PRESETS
       L'API les lit, elle ne sait pas en écrire : ni index.php ni
       server.py n'ont de route pour enregistrer un preset. La section
       montre donc ce qui existe, et rien de ce qu'elle ne peut pas faire.
       ================================================================== */

    function formatDe(p) {
      var s = (p && p.settings) || p || {};
      var e = s['queue.teams'] || p.teams, j = s['queue.players'] || p.players;
      return e && j ? e + ' × ' + j : '';
    }

    function rendrePresets(liste) {
      var hote = $('[data-presets]');
      if (!hote) return;
      liste = Array.isArray(liste) ? liste.slice(0, 10) : [];
      var nv = $('[data-nav-count="presets"]');
      if (nv) nv.textContent = liste.length + '/10';

      if (!liste.length) {
        hote.innerHTML = '<div class="grp__card"><div class="dbempty">' +
          '<h2>' + esc(t('p.emptyTitle')) + '</h2>' +
          '<p>' + esc(t('p.emptyBody')) + '</p>' +
          '<a class="pill pill--ghost pill--sm" href="#queue">' + esc(t('p.goQueue')) + '</a>' +
        '</div></div>';
        return;
      }
      hote.innerHTML = '<div class="grp__head grp__head--end"><span class="grp__meta">' +
          liste.length + '/10</span></div>' +
        '<div class="grp__card">' + liste.map(function (p) {
          var f = formatDe(p);
          return '<div class="row"><p class="row__text"><span class="row__label">' +
            esc((p && p.name) || '—') + '</span>' +
            (f ? ' <span class="row__desc">' + esc(f) + '</span>' : '') + '</p></div>';
        }).join('') + '</div>';
    }

    /* ==================================================================
       RÔLES : la hiérarchie, seulement quand elle pose un problème
       ================================================================== */

    function rendreHierarchie() {
      var hote = $('[data-hier]');
      if (!hote) return;
      var pos = donnees && donnees.botRolePosition;
      var roles = (donnees && donnees.roles) || [];
      if (pos == null || !roles.length) { hote.hidden = true; hote.innerHTML = ''; return; }

      /* Seuls comptent les rôles CHOISIS dans cette section et placés
         au-dessus de celui du bot : ceux qu'il devra attribuer et ne pourra
         pas. Les autres rôles hauts du serveur ne le concernent pas. */
      var choisis = $$('[data-section="roles"] [data-combo] input[type="hidden"]')
        .map(function (h) { return h.value; }).filter(Boolean);
      var hauts = roles.filter(function (r) {
        return choisis.indexOf(String(r.id)) !== -1 && Number(r.position) > Number(pos);
      });
      if (!hauts.length) { hote.hidden = true; hote.innerHTML = ''; return; }

      hote.innerHTML = '<h2 class="grp__title">' + esc(t('rl.hierarchyTitle')) + '</h2>' +
        '<div class="grp__card">' +
          '<div class="row row--stack"><p class="row__note">' + esc(t('rl.hierarchyBody')) + '</p></div>' +
          hauts.map(function (r) {
            return '<div class="row"><p class="row__text"><span class="row__label">@' + esc(r.name) + '</span></p>' +
              '<span class="perm__mark is-no">' + icon('warn', 12) + '<span>' + esc(t('d.navWarn')) + '</span></span></div>';
          }).join('') +
          '<div class="row"><a class="pill pill--ghost pill--sm" target="_blank" rel="noopener" href="https://discord.com/channels/' +
            encodeURIComponent(guildId) + '">' + esc(t('rl.openRoles')) + '</a></div>' +
        '</div>';
      hote.hidden = false;
    }

    /* ==================================================================
       DIAGNOSTIC
       ================================================================== */

    function marque(cle, v) {
      var lib = t(cle);
      if (v === true) {
        return '<span class="perm__mark">' + icon('check', 12) + '<span>' + esc(lib) +
          '</span><span class="sr-only">' + esc(t('dg.ok')) + '</span></span>';
      }
      if (v === false) {
        return '<span class="perm__mark is-no">' + icon('x', 12) + '<span>' + esc(lib) +
          '</span><span class="sr-only">' + esc(t('dg.denied')) + '</span></span>';
      }
      return '<span class="perm__mark"><span aria-hidden="true">—</span><span>' + esc(lib) +
        '</span><span class="sr-only">' + esc(t('dg.unknown')) + '</span></span>';
    }

    function rendreDiagnostic() {
      var hote = $('[data-diag]');
      if (!hote) return;
      var manque = (donnees && donnees.missingPermissions) || [];
      var perms = donnees && Array.isArray(donnees.permissions) ? donnees.permissions : null;
      var html = '';

      var refus = perms ? perms.some(function (p) {
        return p.view === false || p.write === false || p.manage === false || p.state === 'deleted';
      }) : false;

      if (manque.length) {
        var reauth = CYQ.inviteUrl(guildId);
        html += '<div class="grp"><h2 class="grp__title">' + esc(t('st.permTitle')) + '</h2>' +
          '<div class="grp__card">' +
            '<div class="row row--stack"><p class="row__note">' + esc(t('dg.missingBody')) + '</p></div>' +
            manque.map(function (m) {
              return '<div class="row"><p class="row__text"><span class="row__label">' + esc(m) + '</span></p>' +
                '<span class="perm__mark is-no">' + icon('x', 12) + '<span>' + esc(t('dg.denied')) + '</span></span></div>';
            }).join('') +
            (reauth ? '<div class="row"><a class="pill pill--sm" href="' + esc(reauth) + '">' +
              esc(t('st.permReauth')) + '</a></div>' : '') +
          '</div></div>';
      }

      if (perms && perms.length) {
        if (!manque.length && !refus) {
          html += '<div class="grp"><div class="grp__card grp__card--pad"><p class="diag-ok">' +
            icon('check', 14) + '<span>' + esc(t('dg.allGood')) + '</span></p></div></div>';
        }
        html += '<div class="grp"><h2 class="grp__title">' + esc(t('ch.permTitle')) + '</h2><div class="grp__card">' +
          perms.map(function (p) {
            var supprime = p.state === 'deleted';
            return '<div class="row"><p class="row__text"><span class="row__label row__label--chan">' + esc(p.channel) + '</span>' +
              (supprime ? '<span class="row__tag">' + esc(t('ch.deleted')) + '</span>' : '') + '</p>' +
              '<div class="perm">' + marque('ch.permView', p.view) + marque('ch.permWrite', p.write) +
              marque('ch.permManage', p.manage) + '</div></div>';
          }).join('') + '</div></div>';
      } else if (!manque.length) {
        html += '<div class="grp"><div class="grp__card"><div class="dbempty">' +
          '<h2>' + esc(t('ch.permTitle')) + '</h2>' +
          '<p>' + esc(CYQ.api.configured ? t('dg.empty') : t('d.noApi')) + '</p></div></div></div>';
      }
      hote.innerHTML = html;

      /* Le menu le signale sans crier : un glyphe, et le mot pour les
         lecteurs d'écran. Rien ne clignote, rien n'est rouge. */
      var w = $('[data-nav-warn]');
      if (w) w.hidden = !(manque.length || refus);
    }

    /* ==================================================================
       L'AVIS DE PAGE
       ================================================================== */

    function avis(genre) {
      avisCourant = genre;
      if (!noteEl) return;
      if (!genre) { noteEl.hidden = true; noteEl.innerHTML = ''; return; }

      var titre, texte, action = '';
      if (genre === 'noapi') {
        titre = t('d.noApi'); texte = t('d.noApiBody');
      } else if (genre === 'session') {
        titre = t('st.sessionTitle'); texte = t('st.sessionBody');
        action = '<a class="pill pill--sm" href="' + esc(CYQ.loginUrl() || 'login.html') + '">' + esc(t('st.sessionCta')) + '</a>';
      } else if (genre === 'botoff') {
        /* L'API a répondu, mais le bot, lui, n'a pas répondu à l'API : ce
           qu'on affiche vient de la copie du site et peut dater. Jusqu'ici
           cette copie s'affichait sans un mot, avec la même assurance qu'une
           lecture fraîche — et c'est le refus d'enregistrement qui
           l'apprenait, une fois le formulaire rempli. */
        titre = t('d.botOff'); texte = t('d.botOffBody');
        action = '<button class="pill pill--sm" type="button" data-reload>' + esc(t('c.retry')) + '</button>';
      } else if (genre === 'forbidden') {
        titre = t('sv.stRevoked'); texte = t('sv.revokedHelp');
        action = '<a class="pill pill--ghost pill--sm" href="' + esc(CYQ.appUrl ? CYQ.appUrl('servers.html') : 'servers.html') + '">' + esc(t('d.changeServer')) + '</a>';
      } else {
        titre = t('d.loadErr'); texte = t('sv.loadErrBody');
        action = '<button class="pill pill--sm" type="button" data-reload>' + esc(t('c.retry')) + '</button>';
      }
      noteEl.setAttribute('role', genre === 'noapi' ? 'status' : 'alert');
      noteEl.innerHTML = icon('warn', 15) +
        '<div class="dbnote__body"><p class="dbnote__title">' + esc(titre) + '</p>' +
        '<p class="dbnote__text">' + esc(texte) + '</p>' +
        (action ? '<div class="dbnote__act">' + action + '</div>' : '') + '</div>';
      noteEl.hidden = false;
      var b = $('[data-reload]', noteEl);
      if (b) b.addEventListener('click', charger);
    }

    /* ==================================================================
       LE SERVEUR ET LE COMPTE
       ================================================================== */

    function initiales(nom) {
      return (nom || '?').replace(/[^\p{L}\p{N} ]/gu, '').trim().split(/\s+/)
        .slice(0, 2).map(function (m) { return m[0]; }).join('').toUpperCase() || '?';
    }

    function poserServeur(g) {
      var nom = $('[data-g-name]'), meta = $('[data-g-members]'), ic = $('[data-g-icon]');
      if (nom) { nom.textContent = g.name || ''; nom.setAttribute('title', g.name || ''); }
      if (meta) meta.textContent = g.memberCount == null ? '' : nombre(g.memberCount) + ' ' + t('c.members');
      if (ic) {
        if (g.iconUrl) ic.innerHTML = '<img src="' + esc(g.iconUrl) + '" alt="" width="38" height="38">';
        else ic.textContent = initiales(g.name);
      }
      if (g.name) document.title = g.name + ' — CreateYourQueue';
    }

    /* L'etat du bot au pied du menu. `=== true` / `=== false` et non `!` :
       une API plus ancienne n'envoie pas le champ du tout, et son silence
       ne dit pas « eteint » — la ligne reste alors cachee, ce qui est la
       seule chose vraie qu'on puisse en montrer. */
    function etatDuBot(joignable) {
      var ligne = $('[data-bot-state]');
      if (!ligne) return;
      if (joignable !== true && joignable !== false) { ligne.hidden = true; return; }
      var mot = $('[data-bot-state-text]', ligne);
      if (mot) mot.textContent = t(joignable ? 'ov.botOn' : 'ov.botOff');
      ligne.setAttribute('data-on', joignable ? '1' : '0');
      ligne.hidden = false;
    }

    function sessionGet(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
    function sessionSet(k, v) {
      try { if (v === null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); }
      catch (e) { /* navigation privée : on continue sans mémoire */ }
    }

    /* Le numéro de l'avatar par défaut se lit dans l'identifiant : bits de
       l'horodatage, décalés de 22, modulo 6. Un identifiant dépasse 2^53,
       d'où BigInt. Même calcul que la connexion et le choix du serveur. */
    function avatarParDefaut(u) {
      try {
        if (u.discriminator && u.discriminator !== '0') return (Number(u.discriminator) % 5);
        return Number((BigInt(u.id) >> 22n) % 6n);
      } catch (e) { return null; }
    }

    /* Deux formes de compte possibles, toutes deux réelles : celle de
       l'API (id, name, username, avatarUrl) et celle de Discord (id,
       username, global_name, avatar, discriminator). */
    function rendreCompte(u) {
      var connu = $('[data-me-known]'), invite = $('[data-me-guest]');
      if (!connu || !invite) return;
      if (!u) { connu.hidden = true; invite.hidden = false; return; }

      var pseudo = u.username || u.name || u.global_name || '';
      var nm = $('[data-me-name]', connu), av = $('[data-me-avatar]', connu);
      nm.textContent = '@' + pseudo;
      nm.setAttribute('title', u.global_name || u.name || pseudo);

      var src = u.avatarUrl || null;
      if (!src && u.avatar) {
        src = 'https://cdn.discordapp.com/avatars/' + encodeURIComponent(u.id) + '/' +
              encodeURIComponent(u.avatar) + '.png?size=64';
      }
      if (!src && u.id) {
        var n = avatarParDefaut(u);
        if (n !== null) src = 'https://cdn.discordapp.com/embed/avatars/' + n + '.png';
      }
      if (src) av.innerHTML = '<img src="' + esc(src) + '" alt="" width="30" height="30">';
      else av.textContent = initiales(pseudo);

      connu.hidden = false;
      invite.hidden = true;
    }

    function chargerCompte() {
      if (CYQ.api.configured) {
        CYQ.api.get('/me').then(rendreCompte).catch(function () { compteDiscord(); });
        return;
      }
      compteDiscord();
    }
    function compteDiscord() {
      var jeton = sessionGet(KEY_TOKEN);
      if (!jeton) { rendreCompte(null); return; }
      fetch(DISCORD + '/users/@me', { headers: { Authorization: 'Bearer ' + jeton } })
        .then(function (r) {
          if (r.status === 401) { sessionSet(KEY_TOKEN, null); throw new Error('EXPIRED'); }
          if (!r.ok) throw new Error('HTTP_' + r.status);
          return r.json();
        })
        .then(rendreCompte)
        .catch(function () { rendreCompte(null); });
    }

    /* La sortie ferme aussi la session côté API : effacer seulement le jeton
       local laisserait le cookie de session vivant. */
    function deconnecter() {
      sessionSet(KEY_TOKEN, null);
      var aller = function () { location.href = CYQ.loginUrl() || 'login.html'; };
      if (CYQ.api.configured) CYQ.api.post('/auth/logout', {}).then(aller, aller);
      else aller();
    }
    var sortie = $('[data-logout]');
    if (sortie) sortie.addEventListener('click', deconnecter);

    /* ==================================================================
       LE REMPLISSAGE
       ================================================================== */

    /* `partiel` : ne toucher QUE les clés présentes. « Annuler » s'en sert
       pour remettre les seules rangées modifiées, sans réinitialiser les
       segmentés et les équipes que personne n'a touchés. */
    function remplir(reglages, partiel) {
      remplissage = true;
      if (reglages) {
        Object.keys(reglages).forEach(function (k) {
          var champs = $$('[data-setting="' + (window.CSS && CSS.escape ? CSS.escape(k) : k) + '"]');
          if (!champs.length) return;
          var v = reglages[k];
          champs.forEach(function (f) {
            if (f.type === 'checkbox') f.checked = vrai(v);
            else if (f.type === 'radio') f.checked = String(v) === f.value;
            else f.value = v == null ? '' : String(v);
          });
          /* Un « change » par réglage : il repeint ce que app.js tient
             (interrupteurs, dépendances, validation) et nos aperçus. Rien ne
             part, remplissage est vrai. */
          var f0 = champs.filter(function (f) { return f.type !== 'radio' || f.checked; })[0] || champs[0];
          f0.dispatchEvent(new Event('change', { bubbles: true }));
        });
        if (!partiel || 'queue.teams' in reglages)   poserSeg('seg-teams', reglages['queue.teams']);
        if (!partiel || 'queue.players' in reglages) poserSeg('seg-players', reglages['queue.players']);
        $$('[data-team]').forEach(function (r) {
          peindreEquipe(r, $('input[type="hidden"]', r).value);
        });
      }
      $$('[data-setting]').forEach(retenir);
      $$('[data-combo]').forEach(peindreCombo);
      syncDependances();
      syncSousMenus();
      syncFormat();
      remplissage = false;
    }

    function rendreTout() {
      nommerEquipes();
      syncFormat();
      simuler();
      compterJournaux();
      peindreRangs();
      apercuQueue();
      /* Les réglages viennent d'arriver : le salon d'annonces est peut-être
         renseigné depuis, et le bouton d'ouverture s'en déduit. */
      if (majLancement) majLancement();
      rendrePresets(donnees && donnees.presets);
      verrouProgrammation();
      rendreHierarchie();
      rendreDiagnostic();
      $$('[data-combo]').forEach(peindreCombo);
    }

    /* ==================================================================
       LE CHARGEMENT
       ================================================================== */

    function debutChargement() {
      if (db) db.classList.add('is-loading');
      sectionsInertes(true);
    }
    function finChargement(inerte) {
      if (db) db.classList.remove('is-loading');
      sectionsInertes(!!inerte);
    }

    function charger() {
      if (!CYQ.api.configured) {
        donnees = null;
        finChargement(false);
        avis('noapi');
        remplir(null);
        rendreTout();
        return;
      }
      debutChargement();
      avis(null);
      CYQ.api.get('/guilds/' + encodeURIComponent(guildId)).then(function (g) {
        donnees = g || {};
        poserServeur(donnees);
        CYQ.data.channels      = donnees.channels || [];
        CYQ.data.voiceChannels = donnees.voiceChannels || [];
        CYQ.data.categories    = donnees.categories || [];
        CYQ.data.roles         = donnees.roles || [];
        /* Le nom tient lieu d'identifiant : c'est lui que `schedule.preset`
           enregistre, et c'est lui que le bot cherche. */
        CYQ.data.presets = (donnees.presets || []).map(function (pr) {
          var nom = (pr && pr.name) || '';
          return { id: nom, name: nom };
        }).filter(function (pr) { return pr.id; });
        listesLues = true;
        CYQ.refreshCombos();
        /* AVANT `remplir` : c'est lui qui coche les cases, et il ne peut
           cocher que des cases qui existent déjà. */
        rendreAntilien();
        rendreJours();
        remplir(donnees.settings);
        /* Les listes d'accès et le palmarès voyagent avec les réglages —
           elles sont courtes — mais c'est page-dashboard-memoire.js qui
           les dessine. On les lui repasse plutôt que de le faire
           redemander ce qu'on vient de recevoir. */
        document.dispatchEvent(new CustomEvent('cyq:guild', { detail: donnees }));
        rendreTout();
        finChargement(false);
        placerMarque(false);
        /* `=== false` et pas `!` : une API plus ancienne ne renvoie pas du
           tout ce champ, et son silence ne veut pas dire « bot éteint ». */
        if (donnees.botJoignable === false) avis('botoff');
        etatDuBot(donnees.botJoignable);
      }).catch(function (err) {
        donnees = null;
        /* Sur un échec, les sections restent visibles mais INERTES : elles
           montrent les valeurs par défaut, pas celles du serveur, et les
           modifier serait régler à l'aveugle. */
        finChargement(true);
        remplir(null);
        rendreTout();
        if (err && err.code === 'UNAUTHORIZED') avis('session');
        else if (err && err.status === 403) avis('forbidden');
        else avis('error');
      });
    }

    var revoir = $('[data-recheck]');
    if (revoir) revoir.addEventListener('click', charger);

    /* ==================================================================
       LE MENU : l'indicateur qui glisse, la section qui entre
       ================================================================== */

    function lienActif() { return nav ? $('.navlink[aria-current="page"]', nav) : null; }

    /* Une MESURE, pas un choix de dessin : où se trouve l'entrée active.
       Le CSS fait le reste — taille, couleur, durée, courbe. */
    function placerMarque(animer) {
      var l = lienActif();
      if (!l || !mark) return;
      if (!animer) mark.classList.add('is-instant');
      if (etroit.matches) {
        mark.style.setProperty('--x', (l.offsetLeft + 16) + 'px');
        mark.style.setProperty('--w', String(Math.max(0, l.offsetWidth - 32) / 100));
      } else {
        mark.style.setProperty('--y', (l.offsetTop + l.offsetHeight / 2 - 9) + 'px');
      }
      if (!animer) { void mark.offsetWidth; mark.classList.remove('is-instant'); }
      mark.classList.add('is-on');

      /* En rangée, l'entrée active est ramenée dans le champ si elle en est
         sortie — à l'horizontale seulement, sans faire défiler la page. */
      if (etroit.matches && nav) {
        var g = l.offsetLeft - 16, d = l.offsetLeft + l.offsetWidth + 16;
        if (g < nav.scrollLeft || d > nav.scrollLeft + nav.clientWidth) {
          nav.scrollTo({ left: Math.max(0, g), behavior: calme ? 'auto' : 'smooth' });
        }
      }
    }

    /* app.js réécrit `hidden` sur les dix sections à chaque navigation,
       même sur celle qui reste affichée : sans ce garde-fou, recliquer
       l'entrée active rejouerait l'entrée de sa section. */
    var sectionAffichee = $('[data-section]:not([hidden])');

    function entrer(sec) {
      placerMarque(true);
      if (sec === sectionAffichee) return;
      sectionAffichee = sec;
      if (calme) return;
      sec.classList.remove('is-entering');
      void sec.offsetWidth;                 // relance l'animation d'entrée
      sec.classList.add('is-entering');
    }

    /* On observe la section qui devient visible plutôt que le clic : le
       même geste couvre le menu, le retour arrière du navigateur et un lien
       #ancre posé n'importe où dans la page. Le routeur de app.js a déjà
       fait le reste (hidden, aria-current, focus sur le titre). */
    if (window.MutationObserver) {
      var obs = new MutationObserver(function (muts) {
        muts.forEach(function (m) {
          if (m.attributeName === 'hidden' && !m.target.hidden) entrer(m.target);
        });
      });
      $$('[data-section]').forEach(function (s) {
        obs.observe(s, { attributes: true, attributeFilter: ['hidden'] });
      });
    }

    var redim = null;
    window.addEventListener('resize', function () {
      clearTimeout(redim);
      redim = setTimeout(function () { placerMarque(false); }, 120);
    });
    if (etroit.addEventListener) etroit.addEventListener('change', function () { placerMarque(false); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { placerMarque(false); });

    /* ==================================================================
       LA LANGUE
       ================================================================== */

    document.addEventListener('cyq:lang', function () {
      rendreTout();
      avis(avisCourant);
      if (donnees) poserServeur(donnees);
      $$('[data-state][data-s="saved"], [data-state][data-s="error"], [data-state][data-s="local"]').forEach(function (s) {
        etat(s.closest('.row'), s.getAttribute('data-s'), s._champ);
      });
      setTimeout(function () { placerMarque(false); }, 0);
    });

    /* ==================================================================
       LE MENU : FAMILLES DÉPLIABLES, RECHERCHE, COLONNE REPLIABLE
       ================================================================== */

    /* Ce que la personne a replié se garde dans CE navigateur, et
       seulement là : c'est un confort de lecture, pas un réglage du
       serveur. Rien de tout ça ne part au bot, et rien ne doit tomber si
       le stockage est refusé — navigation privée, cookies coupés. */
    function memoire(cle, val) {
      try {
        if (val === undefined) return localStorage.getItem('cyq:nav:' + cle);
        if (val === null) localStorage.removeItem('cyq:nav:' + cle);
        else localStorage.setItem('cyq:nav:' + cle, val);
      } catch (e) { /* on continue sans mémoire */ }
      return null;
    }

    /* ---- les familles se replient -------------------------------------
       Vingt-huit entrées sur six familles, et personne n'en règle
       vingt-huit dans la même séance : on vient pour la queue, ou pour la
       sécurité. Replier les autres rend la colonne lisible d'un coup
       d'œil — et c'est ce qui paie les deux points de corps repris sur
       les entrées.

       La famille qui contient la section ouverte se déplie TOUJOURS, quoi
       qu'en dise la mémoire : un menu qui cache l'endroit où l'on est
       laisse croire qu'on l'a quitté. */
    function famillesDepliables() {
      var boutons = $$('.dbnav__cat[data-grp]');
      if (!boutons.length) return;

      function poser(bouton, ouvert) {
        var items = document.getElementById(bouton.getAttribute('aria-controls'));
        bouton.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
        if (items) items.hidden = !ouvert;
      }

      boutons.forEach(function (bouton) {
        var nom = bouton.getAttribute('data-grp');
        /* Ouvertes par défaut : on ne cache pas à quelqu'un qui arrive ce
           qu'il n'a pas demandé à cacher. Seul un « 0 » écrit ferme. */
        poser(bouton, memoire('grp:' + nom) !== '0');

        bouton.addEventListener('click', function () {
          var ouvert = bouton.getAttribute('aria-expanded') === 'true';
          poser(bouton, !ouvert);
          memoire('grp:' + nom, ouvert ? '0' : '1');
          placerMarque(false);
        });
      });

      function ouvrirCelleDeLaSection() {
        var actif = $('.navlink[aria-current="page"]');
        if (!actif) return;
        var items = actif.closest('.dbnav__items');
        if (!items) return;
        var bouton = $('.dbnav__cat[aria-controls="' + items.id + '"]');
        if (bouton && bouton.getAttribute('aria-expanded') === 'false') {
          poser(bouton, true);
          placerMarque(false);
        }
      }
      document.addEventListener('cyq:section', ouvrirCelleDeLaSection);
      ouvrirCelleDeLaSection();
    }

    /* ---- chercher une section -----------------------------------------
       Le champ FILTRE, il ne classe pas : ce qui ne correspond pas
       disparaît, et le reste garde sa place. Une liste qui se réordonne
       sous les doigts oblige à relire à chaque lettre.

       Pendant une recherche les familles s'ouvrent toutes, y compris
       celles qu'on avait repliées : on cherche justement ce qu'on ne voit
       pas. Le champ vidé, chacune retrouve son état. */
    function chercherDansLeMenu() {
      var champ = $('[data-nav-find]');
      if (!champ) return;
      var vide = $('[data-find-empty]');
      var groupes = $$('.dbnav__grp');

      /* Le nom du raccourci change avec la machine : ⌘K sur un Mac,
         Ctrl K ailleurs. L'écrire en dur en aurait fait un mensonge sur
         l'une des deux. */
      var pomme = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
      var kbd = $('[data-find-kbd]');
      if (kbd) kbd.textContent = pomme ? '⌘ K' : 'Ctrl K';

      /* Les accents ne doivent pas faire manquer une section : « rôles »
         se trouve en tapant « roles ». NFD sépare la lettre de son
         accent, et on retire les accents restés seuls. */
      function nu(s) {
        s = String(s || '').toLowerCase();
        return s.normalize ? s.normalize('NFD').replace(/[̀-ͯ]/g, '') : s;
      }

      function filtrer() {
        var q = nu(champ.value).trim();
        var trouves = 0;

        groupes.forEach(function (grp) {
          var liens = $$('.navlink', grp), visibles = 0;
          liens.forEach(function (l) {
            var lab = $('.navlink-label', l);
            var ok = !q || nu(lab ? lab.textContent : l.textContent).indexOf(q) !== -1;
            l.hidden = !ok;
            if (ok) visibles++;
          });
          trouves += visibles;

          /* Un bloc de sous-entrées dont plus rien ne correspond s'en va
             avec ses entrées : sinon il ne resterait que son blanc.

             Champ vidé, on ne le remet PAS visible d'office : c'est
             l'interrupteur de l'option qui commande ce bloc
             (`syncSousMenus`), et le rouvrir ici afficherait la
             configuration d'une option éteinte. On relit donc
             l'interrupteur, exactement comme lui. */
          $$('.dbnav__sub', grp).forEach(function (sub) {
            if (!q) {
              var inter = $('[data-setting="' + sub.getAttribute('data-sub') + '"]');
              sub.hidden = !(inter && inter.checked);
              return;
            }
            sub.hidden = !$$('.navlink', sub).filter(function (l) { return !l.hidden; }).length;
          });

          var cat = $('.dbnav__cat', grp);
          var items = cat && document.getElementById(cat.getAttribute('aria-controls'));
          if (q) {
            grp.hidden = !visibles;
            if (items) items.hidden = false;      // on cherche ce qu'on ne voit pas
          } else {
            grp.hidden = false;
            if (items && cat) items.hidden = cat.getAttribute('aria-expanded') === 'false';
          }
        });

        if (vide) vide.hidden = !q || trouves > 0;
        placerMarque(false);
      }

      champ.addEventListener('input', filtrer);
      champ.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { champ.value = ''; filtrer(); champ.blur(); }
      });

      document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
          e.preventDefault();
          champ.focus();
          champ.select();
        }
      });
    }

    /* ---- replier la colonne --------------------------------------------
       Pour gagner la largeur, pas pour cacher : repliée, la grille repasse
       à une colonne et le contenu prend toute la place. Le bouton reste
       où il est — une commande qui disparaît avec ce qu'elle replie ne se
       rouvre jamais. */
    function colonneRepliable() {
      var bouton = $('[data-fold]');
      var db = $('[data-db]');
      if (!bouton || !db) return;

      function poser(replie) {
        db.classList.toggle('is-replie', replie);
        bouton.setAttribute('aria-expanded', replie ? 'false' : 'true');
        var mot = t(replie ? 'd.foldShow' : 'd.foldHide');
        bouton.setAttribute('aria-label', mot);
        bouton.setAttribute('title', mot);
        /* L'indicateur se mesure dans une colonne qui vient de changer de
           largeur — ou qui n'est plus affichée du tout. */
        setTimeout(function () { placerMarque(false); }, 0);
      }

      poser(memoire('replie') === '1');

      bouton.addEventListener('click', function () {
        var replie = !db.classList.contains('is-replie');
        poser(replie);
        memoire('replie', replie ? '1' : '0');
      });

      /* Le mot du titre est traduit : il change avec la langue, comme le
         reste de la page. */
      document.addEventListener('cyq:lang', function () {
        poser(db.classList.contains('is-replie'));
      });
    }

    /* ==================================================================
       L'OUVERTURE
       ================================================================== */

    function decouvrir() { document.documentElement.classList.remove('motion-pending'); }

    function ouverture() {
      if (!A || calme) { decouvrir(); return; }
      var utils = A.utils;
      var navPill = $('[data-nav]');
      var blocs = [$('.dbguild'), $('.dbnav'), $('.db__main'), $('.dbme')].filter(Boolean);

      /* États de départ posés en JS, jamais en CSS : si le script tombe, la
         page reste lisible au lieu de rester invisible. */
      utils.set(navPill, { opacity: 0, y: -24 });
      utils.set(blocs, { opacity: 0, y: 12 });
      decouvrir();

      /* Même ouverture que le choix du serveur, à la milliseconde : on
         passe d'un écran à l'autre sans changer de rythme. */
      var tl = A.createTimeline({ defaults: { ease: A.cubicBezier(.16, 1, .3, 1) } });
      tl.add('.shell', { scale: [.985, 1], duration: 700 }, 0)
        .add(navPill, { opacity: 1, y: 0, duration: 560 }, 80)
        .add(blocs, { opacity: 1, y: 0, duration: 480, delay: A.stagger(60) }, 160);
    }

    /* ---- les maquettes Discord des options ---------------------------
       Six interrupteurs secs ne disent pas ce qu'ils font. Sous chacun, le
       message que le bot publie quand l'option est allumée — replié, parce
       que six cartes ouvertes feraient un mur, et une seule à la fois,
       parce que deux ouvertes font perdre le fil.

       La maquette ne regarde PAS l'état de l'interrupteur : on l'ouvre
       justement pour voir ce que l'option ferait avant de la cocher. */
    function maquettesOptions() {
      var boutons = $$('[data-optprev]');
      if (!boutons.length) return;

      function cible(b) { return document.getElementById(b.getAttribute('data-optprev')); }

      function fermer(b) {
        var c = cible(b);
        b.setAttribute('aria-expanded', 'false');
        if (c) c.hidden = true;
      }

      boutons.forEach(function (b) {
        b.addEventListener('click', function () {
          var ouvert = b.getAttribute('aria-expanded') === 'true';
          boutons.forEach(fermer);
          if (ouvert) return;          // le second clic referme, et c'est tout
          var c = cible(b);
          if (!c) return;
          b.setAttribute('aria-expanded', 'true');
          c.hidden = false;
          /* Rien à jouer ici depuis que la maquette porte la boucle de la
             Sécurité (`[data-secprev="options"]`) : elle était en
             display:none, elle revient, et ses lignes repartent donc de
             zéro d'elles-mêmes. Un coup unique posé par-dessus aurait
             joué la même arrivée deux fois, décalée d'un cadre. */
        });
      });
    }

    /* ---- la programmation ne part pas sans preset ---------------------
       Une ouverture programmée applique une configuration : sans preset,
       elle n'en a aucune à appliquer. L'interrupteur reste donc verrouillé
       tant que rien n'est choisi, et la note dit pourquoi — un contrôle
       grisé sans raison est une impasse.

       `data-controls` fait déjà ce geste, mais il ne part que d'une case à
       cocher (app.js l. 553) ; on en reproduit ici l'effet exact — la même
       classe `is-locked`, les mêmes champs désactivés — depuis une liste.
       Et c'est un verrou de PANNEAU, pas un réglage : le bot n'a pas de
       clé « preset obligatoire », on n'en invente pas. */
    function verrouProgrammation() {
      var champ = $('[data-setting="schedule.preset"]');
      var rangee = $('#sc-on-row');
      if (!champ || !rangee) return;
      var choisi = !!String(champ.value || '').trim();
      rangee.classList.toggle('is-locked', !choisi);
      $$('input,select,button', rangee).forEach(function (f) { f.disabled = !choisi; });
      var note = $('[data-preset-note]', rangee);
      if (note) note.hidden = choisi;

      /* Le verrou retombe en cascade : l'heure, les jours et le rappel ne
         se règlent que si l'ouverture automatique est allumée, et elle ne
         peut plus l'être. Repasser par `change` laisse app.js refaire son
         propre travail plutôt que de le doubler ici. */
      var inter = $('#sc-on');
      if (inter && !choisi && inter.checked) {
        inter.checked = false;
        inter.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }

    /* ---- les boucles des maquettes de Sécurité ------------------------
       Quatre maquettes, quatre boucles, et une seule règle : une boucle ne
       tourne que lorsque sa section est à l'écran. app.js émet
       `cyq:section` à chaque navigation ; on écoute, et on coupe tout le
       reste du temps. Quatre animations qui tourneraient en permanence,
       ce serait du calcul — et de la batterie sur un portable — dépensé
       pour une maquette que personne ne regarde. L'onglet passé en
       arrière-plan coupe de même.

       `calme` ne ralentit pas la boucle, il l'éteint : la maquette garde
       alors son état final, qui se lit tout aussi bien, et c'est la
       variante demandée sous `prefers-reduced-motion`. `?motion=on` la
       remet pour qu'on puisse la vérifier. */
    var sectionVue = null;

    function boucles() {
      var tourne = !document.hidden && (force || !calme);
      $$('[data-secprev]').forEach(function (m) {
        m.classList.toggle('is-anime',
          tourne && m.getAttribute('data-secprev') === sectionVue);
      });
    }

    function maquettesSecurite() {
      if (!$('[data-secprev]')) return;
      /* app.js a déjà affiché une section avant nous : son événement est
         passé, on lit donc la section visible plutôt que de l'attendre. */
      var vue = $('.sec:not([hidden])');
      sectionVue = vue ? vue.getAttribute('data-section') : null;
      boucles();

      document.addEventListener('cyq:section', function (e) {
        sectionVue = e.detail;
        boucles();
      });
      document.addEventListener('visibilitychange', boucles);
    }

    /* ------------------------------------------------------------ départ */

    nommerEquipes();
    syncDependances();
    syncFormat();
    simuler();
    compterJournaux();
    apercuQueue();
    maquettesOptions();
    maquettesSecurite();
    verrouProgrammation();
    famillesDepliables();
    chercherDansLeMenu();
    colonneRepliable();
    placerMarque(false);
    ouverture();
    chargerCompte();
    charger();
  });
})();
