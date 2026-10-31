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

   RIEN N'EST INVENTÉ. Sans API, les chiffres gardent leur tiret
   cadratin et la progression le dit. Un zéro se lirait comme une mesure,
   et ce serait faux — un serveur dont on ne sait rien n'est pas un
   serveur à zéro membre, et une semaine dont on ne sait rien n'est pas
   une semaine sans queue.
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
  var semaine = null;
  var semaineDemandee = false;

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

    /* Les boosts viennent du BOT : `null` quand il dort, et le tiret
       alors — pas un zéro, qui se lirait comme « ce serveur n'a aucun
       boost » alors qu'on n'en sait rien. */
    poser('boosts', g && g.boosts != null ? nombre(g.boosts) : TIRET);

    rendreAnciennete(g);

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

    /* L'état du bot n'est plus ici : page-dashboard.js l'écrit au pied du
       menu, où il se lit depuis n'importe quelle section. Le dire deux
       fois sur le même écran, c'était deux endroits à tenir d'accord. */
  }

  /* ==================================================================
     DEPUIS QUAND LE BOT EST LÀ

     `botSince` est la date à laquelle le bot a rejoint le serveur, lue
     par le bot lui-même (`guild.me.joined_at`). Elle vaut `null` quand
     il ne répond pas, et la carte garde alors son tiret.

     L'unité change avec la durée — des jours la première semaine, des
     mois ensuite, des années après — parce que « 743 jours » ne se lit
     pas. Les mois comptés à 30,44 jours : c'est la longueur moyenne d'un
     mois, et la carte dit une ancienneté, pas une date d'anniversaire.
     ================================================================== */
  function rendreAnciennete(g) {
    var meta = $('[data-ov="sinceMeta"]');
    var ms = lireDate(g && g.botSince);

    if (ms === null) {
      poser('since', TIRET);
      if (meta) meta.textContent = '';
      return;
    }

    var jours = Math.max(0, Math.floor((Date.now() - ms) / 86400000));
    if (jours < 60) poser('since', t('ov.sinceDays', { n: nombre(jours) }));
    else if (jours < 730) poser('since', t('ov.sinceMonths', { n: nombre(Math.round(jours / 30.44)) }));
    else poser('since', t('ov.sinceYears', { n: nombre(Math.floor(jours / 365.25)) }));

    /* La date exacte sous le chiffre : l'ancienneté se lit d'un coup
       d'œil, la date répond à « depuis quand, au juste ». */
    if (meta) meta.textContent = dateCourte(ms);
  }

  /* Les noms de jours et de mois passent par Intl et non par les cinq
     fichiers de langue : ce sont des noms du calendrier, pas des phrases
     du site, et chaque langue a déjà les siens — les retraduire à la
     main, c'était cinq occasions de se tromper d'abréviation. Les
     PHRASES, elles, restent dans les fichiers de langue. */
  function dateCourte(ms) {
    try {
      return new Date(ms).toLocaleDateString(CYQ.lang, {
        year: 'numeric', month: 'long', day: 'numeric'
      });
    } catch (e) { return ''; }
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

  /* ==================================================================
     LA SEMAINE

     Sept lignes, et deux informations par ligne qui ne disent pas la
     même chose :

       · ce qui a EU LIEU — le nombre de files lancées ce jour-là, lu
         dans `byDay` du relevé d'activité ;
       · ce qui est PRÉVU — l'encoche de droite, qui vient de
         `schedule.days` et ne s'allume que si l'ouverture automatique
         est allumée.

     Les deux sont indépendantes : un jour prévu peut n'avoir rien
     donné, et une file lancée à la main tombe un jour qui n'était pas
     prévu. Les confondre en une seule colonne aurait fait passer la
     seconde pour la première.

     `schedule.days` compte à partir du LUNDI (0 = lundi, cf.
     bot/guild_settings.py), là où `getDay()` de JavaScript compte à
     partir du dimanche. D'où le `+ 6) % 7` : l'oublier décalait toutes
     les encoches d'un jour, et rien n'aurait protesté.
     ================================================================== */

  function cleJour(d) {
    /* `byDay` porte des dates en texte, « 2026-10-01 ». On fabrique la
       même forme à partir d'une date locale plutôt que d'utiliser
       toISOString(), qui bascule en UTC et rend la veille pour tout ce
       qui se passe après minuit à l'ouest de Greenwich. */
    var m = d.getMonth() + 1, j = d.getDate();
    return d.getFullYear() + '-' + (m < 10 ? '0' : '') + m + '-' + (j < 10 ? '0' : '') + j;
  }

  function joursPrevus() {
    var r = guilde && guilde.settings;
    if (!r) return null;
    /* Éteinte, la programmation ne prévoit rien : garder les encoches
       aurait annoncé des ouvertures qui n'auront pas lieu. */
    var allumee = r['schedule.enabled'];
    if (allumee === false || allumee === 0 || allumee === '0' || allumee === 'false') return [];
    var brut = r['schedule.days'];
    if (brut == null || String(brut).trim() === '') return [];
    return String(brut).split(',').map(function (n) {
      return parseInt(String(n).trim(), 10);
    }).filter(function (n) { return n >= 0 && n <= 6; });
  }

  function rendreSemaine() {
    var hote = $('[data-ov-week]');
    if (!hote) return;

    var aujourdhui = $('[data-ov-today]');
    if (aujourdhui) aujourdhui.textContent = dateCourte(Date.now());

    poser('opened', semaine && semaine.opened != null ? nombre(semaine.opened) : TIRET);
    poser('slots', semaine && semaine.playerSlots != null ? nombre(semaine.playerSlots) : TIRET);

    /* Les files lancées, rangées par date pour les retrouver en une
       lecture au lieu de parcourir la liste sept fois. */
    var parDate = {};
    if (semaine && semaine.byDay && semaine.byDay.length) {
      semaine.byDay.forEach(function (ligne) {
        if (ligne && ligne.day != null) parDate[String(ligne.day)] = ligne.n;
      });
    }

    var prevus = joursPrevus();
    var html = '';
    var base = new Date();
    base.setHours(12, 0, 0, 0); /* midi : un pas de 24 h ne saute alors
                                   aucun jour au changement d'heure. */

    for (var i = 6; i >= 0; i--) {
      var d = new Date(base.getTime() - i * 86400000);
      var cle = cleJour(d);
      var n = parDate[cle];
      var indice = (d.getDay() + 6) % 7;
      var prevu = prevus && prevus.indexOf(indice) !== -1;

      var classes = 'ovjour';
      if (i === 0) classes += ' is-today';
      if (n) classes += ' is-plein';
      if (prevu) classes += ' is-prevu';

      html += '<li class="' + classes + '">'
            + '<span class="ovjour__nom">' + esc(nomJour(d)) + '</span>'
            + '<span class="ovjour__n">' + (semaine ? esc(nombre(n || 0)) : TIRET) + '</span>'
            + '<span class="ovjour__coche" aria-hidden="true"></span>'
            + '</li>';
    }
    hote.innerHTML = html;
  }

  function nomJour(d) {
    try {
      return d.toLocaleDateString(CYQ.lang, { weekday: 'short', day: 'numeric' });
    } catch (e) { return cleJour(d); }
  }

  /* Une requête pour les deux chiffres et les sept jours. `days=7`
     parce que la carte montre une semaine : en demander trente pour
     n'en dessiner que sept aurait fait porter au bot un calcul que
     personne ne regarde. */
  function chargerSemaine() {
    if (semaineDemandee || !CYQ.api || !CYQ.api.configured || !guildId) return;
    semaineDemandee = true;
    CYQ.api.get('/guilds/' + encodeURIComponent(guildId) + '/activity?days=7')
      .then(function (r) { semaine = r || {}; rendreSemaine(); })
      .catch(function () {
        semaine = null;
        semaineDemandee = false;
        rendreSemaine();
      });
  }

  function rendre() {
    rendreChiffres();
    rendreProgression();
    rendreSemaine();
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
    chargerSemaine();
  });

  /* La langue change : on repeint avec ce qu'on a déjà. Les libellés des
     paliers et les durées relatives sont des phrases, pas des nombres —
     `applyI18n` ne peut pas les retrouver tout seul, puisqu'ils portent
     des variables. */
  document.addEventListener('cyq:lang', function () { rendre(); });

  brancherLiens(sec);
  rendre();
})();
