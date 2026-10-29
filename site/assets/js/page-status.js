/* =========================================================================
   status.html — la page d'état.

   Elle fait une seule chose : demander etat.php comment va le bot, et
   montrer ce qu'il répond. Rien n'est deviné, rien n'est gardé entre deux
   visites : il n'y a pas d'historique, et la page le dit.

   Trois décisions qui expliquent la forme du fichier :

   · Le minuteur s'ARRÊTE quand l'onglet passe en arrière-plan. Une page
     d'état reste ouverte des heures ; sans cela, un seul onglet oublié
     appellerait le serveur cent vingt fois par heure pour personne.

   · Les clés de traduction sont POSÉES sur les éléments (data-i18n), pas
     seulement leur texte. Un changement de langue passe alors par app.js
     comme pour le reste de la page, et le verdict suit sans qu'on ait à
     le redemander.

   · Aucun état d'animation n'est posé d'ici. Si ce script ne tourne pas,
     la page reste lisible — elle affiche son état d'attente, qui est la
     vérité : rien n'a été mesuré.
   ========================================================================= */

(function () {
  'use strict';

  var CYQ = window.CYQ;
  if (!CYQ) return;

  function $(s) { return document.querySelector(s); }

  /* Trente secondes, comme REFRESH_SECONDS du panneau Discord
     (bot/cogs/statuspanel.py) : les deux relevés battent au même rythme.
     Le cache de etat.php tient vingt secondes, donc chaque mesure
     automatique en obtient bien une neuve. */
  var RAFRAICHIR = 30;

  var verdict   = $('.stverdict');
  var nomEtat   = $('[data-verdict]');
  var descEtat  = $('[data-verdict-desc]');
  var tempo     = $('[data-tempo]');
  var bouton    = $('[data-refresh]');
  var chiffres  = $('[data-chiffres]');
  if (!verdict) return;

  var dernier = null;      // la dernière mesure obtenue, pour la retraduire
  var enCours = false;     // un appel en vol : on n'en lance pas un second
  var reste = RAFRAICHIR;
  var minuteur = null;

  /* ------------------------------------------------------- traduction ---- */

  /* Pose la clé ET le texte. app.js relit les data-i18n à chaque
     changement de langue : le verdict se traduit donc tout seul, sans que
     ce fichier écoute quoi que ce soit pour les textes fixes. */
  function poser(el, cle) {
    if (!el) return;
    el.setAttribute('data-i18n', cle);
    el.textContent = CYQ.t(cle);
  }

  function valeur(el, texte) {
    if (!el) return;
    /* Pas de clé ici : c'est un nombre, pas une phrase. On retire une
       éventuelle clé laissée par le HTML de départ, sinon app.js
       écraserait le chiffre au premier changement de langue. */
    el.removeAttribute('data-i18n');
    el.textContent = texte;
  }

  /* « 3 j 4 h 12 min », dans l'ordre et les unités de _format_uptime
     (bot/cogs/statuspanel.py) : le même temps de fonctionnement ne doit
     pas s'écrire de deux façons selon qu'on le lit ici ou dans Discord. */
  function duree(secondes) {
    secondes = Math.max(0, parseInt(secondes, 10) || 0);
    var jours = Math.floor(secondes / 86400);
    var heures = Math.floor((secondes % 86400) / 3600);
    var minutes = Math.floor((secondes % 3600) / 60);
    var bouts = [];
    if (jours) bouts.push(CYQ.t('stt.uD', { n: jours }));
    if (heures || jours) bouts.push(CYQ.t('stt.uH', { n: heures }));
    bouts.push(CYQ.t('stt.uM', { n: minutes }));
    return bouts.join(' ');
  }

  /* ---------------------------------------------------------- l'écran ---- */

  function rendre() {
    var e = dernier;
    var etat = e ? String(e.verdict || 'down') : 'wait';
    /* Une réponse sans verdict connu vaut « ça ne répond pas » : on ne
       montre jamais mieux que ce qu'on a mesuré. */
    if (['good', 'ok', 'slow', 'down', 'unset', 'wait', 'nopage'].indexOf(etat) === -1) {
      etat = 'down';
    }
    verdict.setAttribute('data-etat', etat);

    var mots = {
      wait:   ['stt.vWait',  'stt.dWait'],
      good:   ['stt.vGood',  'stt.dGood'],
      ok:     ['stt.vOk',    'stt.dOk'],
      slow:   ['stt.vSlow',  'stt.dSlow'],
      down:   ['stt.vDown',  'stt.dDown'],
      unset:  ['stt.vUnset', 'stt.dUnset'],
      nopage: ['stt.vNoPage', 'stt.dNoPage']
    }[etat];
    poser(nomEtat, mots[0]);
    /* La nuance de « ok » : le bot répond mais sa latence Discord n'est
       pas encore connue — le premier battement de cœur n'est pas revenu.
       Le dire plutôt que de laisser lire « liaison correcte » sur une
       mesure qui n'existe pas. */
    if (etat === 'ok' && e && e.latency_ms === null) poser(descEtat, 'stt.dNoPing');
    else poser(descEtat, mots[1]);

    var ms = CYQ.t('stt.ms');
    valeur($('[data-ping]'), e && e.latency_ms != null
      ? e.latency_ms + ' ' + ms : CYQ.t('stt.na'));
    valeur($('[data-api]'), e && e.api_ms != null
      ? e.api_ms + ' ' + ms : CYQ.t('stt.na'));

    /* Les chiffres du bot n'apparaissent que si le bot a répondu. Un
       « 0 serveur » affiché pendant une panne serait faux. */
    var repond = e && ['good', 'ok', 'slow'].indexOf(etat) !== -1;
    if (chiffres) chiffres.hidden = !repond;
    if (repond) {
      valeur($('[data-uptime]'), e.uptime_seconds != null
        ? duree(e.uptime_seconds) : CYQ.t('stt.na'));
      valeur($('[data-guilds]'), e.guilds != null ? String(e.guilds) : CYQ.t('stt.na'));
      valeur($('[data-queues]'), e.active_queues != null
        ? String(e.active_queues) : CYQ.t('stt.na'));
    }
  }

  function rendreTempo() {
    if (!tempo) return;
    if (document.hidden) { poser(tempo, 'stt.paused'); return; }
    if (enCours) { poser(tempo, 'stt.measuring'); return; }
    tempo.removeAttribute('data-i18n');
    tempo.textContent = CYQ.t('stt.next', { n: reste });
  }

  /* --------------------------------------------------------- la mesure --- */

  function mesurer() {
    if (enCours) return;
    enCours = true;
    reste = RAFRAICHIR;
    rendreTempo();

    /* cache: 'no-store' en plus de l'en-tête de etat.php : une mesure
       servie depuis le cache du navigateur serait une mesure d'hier. */
    fetch('etat.php', { cache: 'no-store', credentials: 'omit' })
      .then(function (r) {
        if (!r.ok) throw new Error('http');
        return r.json();
      })
      .then(function (json) {
        dernier = json;
      })
      .catch(function () {
        /* Le script de mesure n'a pas répondu : c'est le sous-domaine
           lui-même qui est en cause, pas forcément le bot. On ne met pas
           la panne sur le dos de ce qu'on n'a pas pu joindre. */
        dernier = { verdict: 'nopage', latency_ms: null, api_ms: null };
      })
      .then(function () {
        enCours = false;
        rendre();
        rendreTempo();
      });
  }

  /* --------------------------------------------------------- le minuteur - */

  function battre() {
    if (enCours) return;
    reste -= 1;
    if (reste <= 0) mesurer();
    else rendreTempo();
  }

  function lancer() {
    if (minuteur === null) minuteur = window.setInterval(battre, 1000);
  }

  function arreter() {
    if (minuteur !== null) { window.clearInterval(minuteur); minuteur = null; }
  }

  /* Onglet en arrière-plan : on arrête tout. Au retour, on remesure
     immédiatement — ce qui était affiché a vieilli pendant l'absence, et
     montrer une mesure d'il y a vingt minutes comme si elle était fraîche
     serait le pire service à rendre sur cette page. */
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { arreter(); rendreTempo(); }
    else { lancer(); mesurer(); }
  });

  if (bouton) {
    bouton.addEventListener('click', function () { mesurer(); });
  }

  /* Changement de langue : app.js a retraduit tout ce qui porte une clé,
     mais pas les chiffres ni le décompte. On les réécrit. */
  document.addEventListener('cyq:lang', function () {
    rendre();
    rendreTempo();
  });

  rendre();
  rendreTempo();
  if (!document.hidden) { lancer(); mesurer(); }
})();
