/* =========================================================================
   CreateYourQueue — la Vue d'ensemble du panneau
   =========================================================================
   L'écran d'arrivée. Il ne règle rien : il lit, il situe, et il renvoie
   vers la section qui règle. C'est pour ça qu'il vit dans son propre
   fichier plutôt que dans page-dashboard.js, qui est tout entier bâti
   autour de la rangée de réglage, de sa validation et de sa barre
   d'enregistrement — trois choses dont cette page n'a aucun usage.

   Il s'accroche à `cyq:guild`, l'évènement que page-dashboard.js diffuse
   avec la réponse de GET /guilds/{id}. Redemander la même charge serait
   un deuxième aller-retour pour des données déjà là.

   RIEN N'EST INVENTÉ. Sans API, les quatre chiffres gardent leur tiret
   cadratin et la progression le dit. Un zéro se lirait comme une mesure,
   et ce serait faux — un serveur dont on ne sait rien n'est pas un
   serveur à zéro membre.
   ========================================================================= */

(function () {
  'use strict';

  var sec = document.querySelector('[data-section="apercu"]');
  if (!sec) return;

  var CYQ = window.CYQ;
  if (!CYQ) return;

  function $(sel, root) { return (root || sec).querySelector(sel); }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || sec).querySelectorAll(sel));
  }
  function t(cle, vars) { return CYQ.t(cle, vars); }
  function esc(s) { return CYQ.esc(String(s == null ? '' : s)); }

  var guildId = new URLSearchParams(location.search).get('guild') || '';

  /* La dernière charge reçue, gardée pour pouvoir tout repeindre quand la
     langue change sans redemander quoi que ce soit au réseau. */
  var guilde = null;
  var matchs = null;
  var matchsDemandes = false;

  var TIRET = '—';

  /* ==================================================================
     LES QUATRE PALIERS

     Ce ne sont pas des étapes choisies pour faire joli : ce sont les
     contrôles que `open_queue` fait, dans son ordre (bot/cogs/
     dashboard_api.py). Chacun correspond à un refus que le bot renvoie
     en 409, et c'est ce qui donne sa valeur à la barre — pleine, elle
     dit que « Ouvrir la queue » répondra 200.

     Quatre et non cinq : un palier « premier lancement » n'aurait
     conditionné aucune ouverture, et la charge de l'API ne le porte pas.
     ================================================================== */

  var PALIERS = [
    {
      cle: 'ov.stepChannels', va: 'salons',
      /* Les deux salons sans lesquels le bot n'a nulle part où publier :
         c'est `queue_ready` qui les exige, et son échec est le 409
         « setup_incomplete ». */
      ok: function (r) { return plein(r, 'channel.commands') && plein(r, 'channel.announcements'); }
    },
    {
      cle: 'ov.stepRole', va: 'roles',
      ok: function (r) { return plein(r, 'role.organizer'); }
    },
    {
      cle: 'ov.stepQueue', va: 'queue',
      /* Le format enregistré. Son absence est le 409 « no_config », et
         le bot refuse plutôt que d'inventer un format par défaut. */
      ok: function (r) {
        return plein(r, 'queue.name') && plein(r, 'queue.players') && plein(r, 'queue.teams');
      }
    },
    {
      cle: 'ov.stepPerms', va: 'diagnostic',
      /* Les droits Discord. Ils ne se règlent pas dans le panneau — d'où
         le renvoi vers Diagnostic, qui les nomme un par un. */
      ok: function (r, g) {
        return !(g && g.missingPermissions && g.missingPermissions.length);
      }
    }
  ];

  /* Les réglages arrivent à plat, avec des clés pointées : `settings`
     porte « channel.commands », pas un objet `channel`. C'est la même
     forme que `remplir()` consomme. */
  function plein(reglages, cle) {
    if (!reglages) return false;
    var v = reglages[cle];
    return v != null && String(v).trim() !== '';
  }

  function nombre(n) {
    try { return Number(n).toLocaleString(CYQ.lang); } catch (e) { return String(n); }
  }

  /* ==================================================================
     LE TEMPS QUI PASSE

     Écrit à la main plutôt qu'avec Intl.RelativeTimeFormat : les cinq
     fichiers de langue portent déjà toutes les phrases du site, et une
     sixième source de traduction qui ne couvre pas le coréen de la même
     façon donnerait deux voix sur le même écran.
     ================================================================== */
  /* Une date arrive en TEXTE ISO de l'historique — `_maintenant()` côté
     bot rend un isoformat UTC — et en secondes depuis 1970 de certaines
     autres lignes, ce que rend `time.time()`. Les deux passent ici, comme
     dans page-dashboard-memoire.js, et une valeur illisible rend null
     plutôt que de produire « il y a NaN jours ». */
  function lireDate(v) {
    if (v == null || v === '') return null;
    var d = typeof v === 'number' ? new Date(v * 1000) : new Date(v);
    return isNaN(d.getTime()) ? null : d.getTime();
  }

  function ilYA(ms) {
    var s = Math.max(0, Math.round((Date.now() - ms) / 1000));
    if (s < 90) return t('ov.agoNow');
    var m = Math.round(s / 60);
    if (m < 60) return t('ov.agoMin', { n: m });
    var h = Math.round(m / 60);
    if (h < 36) return t('ov.agoHour', { n: h });
    return t('ov.agoDay', { n: Math.round(h / 24) });
  }

  /* ==================================================================
     LE DESSIN
     ================================================================== */

  function poser(cle, texte) {
    var el = $('[data-ov="' + cle + '"]');
    if (el) el.textContent = texte;
  }

  function rendreChiffres() {
    var g = guilde;

    poser('members', g && g.memberCount != null ? nombre(g.memberCount) : TIRET);

    if (matchs && matchs.total != null) {
      poser('matches', nombre(matchs.total));
      /* `total` dit combien sont CONSERVÉS, pas combien ont été joués :
         au delà de `kept`, les plus vieux sont tombés. L'API le précise,
         donc la page le précise — un total faux serait pire que pas de
         total du tout. */
      var meta = $('[data-ov="matchesMeta"]');
      if (meta) {
        meta.textContent = matchs.kept && matchs.total >= matchs.kept
          ? t('ov.matchesCap', { n: nombre(matchs.kept) })
          : '';
      }
    } else {
      poser('matches', TIRET);
      poser('matchesMeta', '');
    }

    var dernier = matchs && matchs.matches && matchs.matches[0];
    var ms = lireDate(dernier && dernier.at);
    if (ms !== null) poser('last', ilYA(ms));
    /* Une queue existe mais sa date ne se lit pas : le tiret, et surtout
       pas « aucune pour l'instant » — ce serait affirmer le contraire de
       ce que la réponse contient. */
    else if (dernier) poser('last', TIRET);
    else if (matchs) poser('last', t('ov.lastNone'));
    else poser('last', TIRET);

    /* `=== false` et pas `!` : une API plus ancienne ne renvoie pas du
       tout ce champ, et son silence ne veut pas dire « bot éteint ».
       C'est la même précaution que page-dashboard.js prend pour l'avis. */
    if (!g) poser('bot', TIRET);
    else if (g.botJoignable === false) poser('bot', t('ov.botOff'));
    else if (g.botJoignable === true) poser('bot', t('ov.botOn'));
    else poser('bot', TIRET);
  }

  function rendreProgression() {
    var rail = $('[data-ov-rail]');
    var mot = $('[data-ov-word]');
    var compte = $('[data-ov="steps"]');
    if (!rail) return;

    var reglages = guilde && guilde.settings;
    var connu = !!guilde;

    var faits = 0, premierManquant = null;
    var html = '';

    PALIERS.forEach(function (p) {
      var fait = connu && p.ok(reglages, guilde);
      if (fait) faits++;
      else if (!premierManquant && connu) premierManquant = p;

      var classes = 'ovstep';
      if (fait) classes += ' is-done';
      else if (connu && premierManquant === p) classes += ' is-next';

      html += '<li class="' + classes + '">'
            + '<span class="ovstep__bar"></span>'
            + '<span class="ovstep__lab">' + esc(t(p.cle)) + '</span>'
            + '</li>';
    });
    rail.innerHTML = html;

    if (compte) {
      compte.textContent = connu
        ? t('ov.steps', { n: faits, total: PALIERS.length })
        : '';
    }

    if (!mot) return;
    if (!connu) {
      /* Pas d'API, ou chargement échoué : on ne prétend ni que tout va
         bien, ni que quelque chose manque. On dit qu'on ne sait pas. */
      mot.innerHTML = esc(t('ov.unknown'));
    } else if (!premierManquant) {
      mot.innerHTML = esc(t('ov.ready'));
    } else {
      /* Un seul lien, celui du premier palier manquant. Lister les
         quatre reproduirait le menu, qui est déjà à gauche. */
      mot.innerHTML = esc(t('ov.missing')) + ' '
        + '<a href="#' + esc(premierManquant.va) + '" data-ov-goto="'
        + esc(premierManquant.va) + '">' + esc(t(premierManquant.cle)) + '</a>';
      brancherLiens(mot);
    }
  }

  function rendre() {
    rendreChiffres();
    rendreProgression();
  }

  /* ==================================================================
     LES LIENS VERS LES SECTIONS

     app.js n'écoute que `.navlink[data-goto]` et le `popstate` : un
     simple href="#salons" changerait l'adresse sans rien afficher. On
     passe donc par CYQ.showSection, qui est exposée pour ça. Le href
     reste écrit : il donne le clic du milieu, et il dit où ça mène.
     ================================================================== */
  function brancherLiens(racine) {
    $$('[data-ov-goto]', racine).forEach(function (a) {
      if (a.hasAttribute('data-ov-lie')) return;
      a.setAttribute('data-ov-lie', '');
      a.addEventListener('click', function (e) {
        if (!CYQ.showSection) return;
        e.preventDefault();
        CYQ.showSection(a.getAttribute('data-ov-goto'), true, true);
      });
    });
  }

  /* ==================================================================
     LES QUEUES EN MÉMOIRE

     Une requête, et une seule, pour deux chiffres : le total conservé et
     la date du dernier match. `limit=1` parce qu'on n'affiche pas la
     liste — c'est la section Historique qui la dessine, à sa première
     visite, et lui faire payer vingt-cinq matchs ici serait les charger
     deux fois.
     ================================================================== */
  function chargerMatchs() {
    if (matchsDemandes || !CYQ.api || !CYQ.api.configured || !guildId) return;
    matchsDemandes = true;
    CYQ.api.get('/guilds/' + encodeURIComponent(guildId) + '/matches?limit=1')
      .then(function (r) { matchs = r || {}; rendreChiffres(); })
      .catch(function () {
        /* Un échec ici ne doit pas abîmer le reste de l'écran : les
           autres chiffres viennent d'une autre requête, qui a réussi. */
        matchs = null;
        matchsDemandes = false;
        rendreChiffres();
      });
  }

  /* ==================================================================
     LES BRANCHEMENTS
     ================================================================== */

  document.addEventListener('cyq:guild', function (e) {
    guilde = e.detail || null;
    rendre();
    chargerMatchs();
  });

  /* La langue change : on repeint avec ce qu'on a déjà. Les libellés des
     paliers et les durées relatives sont des phrases, pas des nombres —
     `applyI18n` ne peut pas les retrouver tout seul, puisqu'ils portent
     des variables. */
  document.addEventListener('cyq:lang', function () { rendre(); });

  brancherLiens(sec);
  rendre();
})();
