/* =========================================================================
   LA MÉMOIRE DU BOT — historique, statistiques, accès, journal, saisons
   =========================================================================
   Six écrans qui ne règlent rien : ils LISENT ce que le bot a retenu.

   Dans un fichier à part, et c'est délibéré. page-dashboard.js tient déjà
   1800 lignes de formulaires ; ces écrans n'en partagent ni l'état ni le
   mécanisme d'enregistrement. Ils appellent quatre routes qui leur sont
   propres :

       GET  /guilds/{id}/matches?limit&offset&player&season
       GET  /guilds/{id}/players/{uid}
       GET  /guilds/{id}/activity?days
       GET  /guilds/{id}/audit?limit
       POST /guilds/{id}/bans            ← le seul qui écrit

   Pourquoi des routes à part plutôt que la charge utile des réglages :
   cinq cents matchs se paieraient à CHAQUE ouverture du panneau, sur
   toutes les pages, y compris celles qui ne les montrent pas. Elles sont
   donc appelées PARESSEUSEMENT, à la première visite de leur section.

   Et, règle du dépôt : rien d'inventé. Sans API, sans match, sans ligne,
   ces écrans affichent leur état vide réel. Jamais une courbe plate qui
   ressemblerait à de l'activité.
   ========================================================================= */
(function () {
  'use strict';

  var CYQ = window.CYQ || {};
  var t = CYQ.t || function (k) { return k; };
  var esc = CYQ.esc || function (x) { return String(x); };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  var hote = $('[data-section="historique"]');
  if (!hote) return;              // pas la page du panneau

  /* L'identifiant du serveur, lu comme le fait page-dashboard.js. */
  function guildId() {
    var m = /[?&]guild=(\d+)/.exec(window.location.search);
    return m ? m[1] : null;
  }

  var GID = guildId();
  var base = GID ? '/guilds/' + encodeURIComponent(GID) : null;

  /* Ce qui a déjà été chargé. Revenir sur une section ne doit pas
     redemander : ces écrans ne changent pas pendant qu'on les regarde. */
  var charge = {};

  /* ------------------------------------------------------------------ */
  /* Petites fabriques communes                                          */
  /* ------------------------------------------------------------------ */

  /* Une date lisible, dans le FUSEAU DU LECTEUR. Le bot stocke en UTC :
     l'afficher tel quel ferait lire « 19:00 » à quelqu'un qui a joué à
     21 h. `toLocaleString` fait la conversion, et la langue vient de
     celle du panneau. */
  function quand(iso) {
    if (!iso) return '';
    /* Une date arrive en texte ISO du journal, et en SECONDES depuis 1970
       des exclusions automatiques — c'est ce que `time.time()` rend côté
       bot. Les deux passent par ici : un seul endroit sait lire une date,
       et une valeur inattendue rend '' au lieu de faire tomber l'écran
       entier, ce qu'une seule ligne abîmée ne doit pas pouvoir. */
    var d = typeof iso === 'number' ? new Date(iso * 1000) : new Date(iso);
    if (isNaN(d.getTime())) return '';
    try {
      return d.toLocaleString(CYQ.lang || 'fr', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
      });
    } catch (e) {
      return d.toISOString().slice(0, 16).replace('T', ' ');
    }
  }

  /* Un pseudo, ou l'identifiant quand le membre a quitté le serveur. Le
     bouton ouvre sa fiche — d'où `data-joueur`, que l'historique écoute. */
  function pseudo(id, noms) {
    var nom = noms && noms[id];
    return '<button class="joueur" type="button" data-joueur="' + esc(id) + '">' +
      esc(nom || ('#' + String(id).slice(-4))) + '</button>';
  }

  function vide(cle) {
    return '<p class="vide">' + esc(t(cle)) + '</p>';
  }

  /* Dit ce qui s'est passé quand une lecture échoue. Un écran muet
     laisserait croire qu'il n'y a rien à voir, ce qui n'est pas pareil. */
  function panne(err) {
    if (!err) return vide('me.empty');
    if (err.code === 'NO_API') return vide('me.noApi');
    if (err.motif === 'BOT_INJOIGNABLE') return vide('me.botOff');
    if (err.code === 'UNAUTHORIZED') return vide('me.session');
    return vide('me.error');
  }

  function lire(chemin) {
    if (!base || !CYQ.api || !CYQ.api.configured) {
      var e = new Error('NO_API'); e.code = 'NO_API';
      return Promise.reject(e);
    }
    return CYQ.api.get(base + chemin);
  }

  /* ================================================================== */
  /* 1. L'HISTORIQUE DES MATCHS                                          */
  /* ================================================================== */

  var hist = { page: 0, taille: 25, total: 0, noms: {}, joueur: null };

  function ligneDeMatch(m) {
    var equipes = Object.keys(m.teams || {});
    var parts = equipes.map(function (nom) {
      var gagne = (nom === m.winner);
      var membres = (m.teams[nom] || []).map(function (uid) {
        return pseudo(uid, hist.noms);
      }).join(', ');
      return '<span class="' + (gagne ? 'match__win' : 'match__lose') + '">' +
        esc(nom) + (membres ? ' · ' + membres : '') + '</span>';
    });
    return '<div class="row"><div class="match">' +
      '<span class="match__date">' + esc(quand(m.at)) + '</span>' +
      '<span class="match__teams">' + parts.join(' <span class="match__lose">vs</span> ') + '</span>' +
      (m.mvp ? '<span class="match__mvp">MVP ' + pseudo(m.mvp, hist.noms) + '</span>' : '') +
      '</div></div>';
  }

  function rendreHistorique(donnees, err) {
    var carte = $('[data-history]');
    var compte = $('[data-history-count]');
    var plus = $('[data-history-more]');
    if (!carte) return;

    if (err) { carte.innerHTML = panne(err); if (plus) plus.hidden = true; return; }

    var liste = (donnees && donnees.matches) || [];
    if (!liste.length && hist.page === 0) {
      carte.innerHTML = vide('hi.empty');
      if (compte) compte.textContent = '';
      if (plus) plus.hidden = true;
      return;
    }

    var html = liste.map(ligneDeMatch).join('');
    carte.innerHTML = hist.page === 0 ? html : carte.innerHTML + html;

    if (compte) {
      /* « 42 matchs gardés » et non « 42 matchs joués » : au-delà de ce
         que le bot conserve, les plus anciens sont tombés, et annoncer un
         total serait annoncer un chiffre faux. */
      compte.textContent = hist.total === 1 ? t('hi.keptOne')
        : t('hi.kept', { n: hist.total });
    }
    /* Le bouton ne s'affiche que s'il reste vraiment quelque chose. */
    var vus = (hist.page + 1) * hist.taille;
    if (plus) plus.hidden = vus >= hist.total;
  }

  function chargerHistorique(suite) {
    if (!suite) { hist.page = 0; }
    var q = '?limit=' + hist.taille + '&offset=' + (hist.page * hist.taille);
    if (hist.joueur) q += '&player=' + encodeURIComponent(hist.joueur);
    return lire('/matches' + q).then(function (d) {
      hist.total = (d && d.total) || 0;
      /* Les pseudos s'ACCUMULENT : la page suivante n'apporte que les
         siens, et écraser la table ferait réapparaître des identifiants
         bruts dans les lignes déjà affichées. */
      var noms = (d && d.names) || {};
      Object.keys(noms).forEach(function (k) { if (noms[k]) hist.noms[k] = noms[k]; });
      rendreHistorique(d, null);
    }).catch(function (e) {
      rendreHistorique(null, e);
      /* Relancée : l'appelant doit pouvoir savoir que ça a échoué. La
         page suivante l'ignore, le chargement paresseux s'en sert pour
         rendre sa section à nouveau chargeable. */
      throw e;
    });
  }

  var suivant = $('[data-history-next]');
  if (suivant) {
    suivant.addEventListener('click', function () {
      hist.page += 1;
      chargerHistorique(true).catch(function () {});
    });
  }

  /* ================================================================== */
  /* 2. LA FICHE D'UN JOUEUR                                             */
  /* ================================================================== */

  /* La courbe : une polyligne sur une boîte de 100×30, mise à l'échelle
     par le viewBox. Pas de bibliothèque — vingt points et un trait, c'est
     exactement ce dont on a besoin, et le dépôt n'ajoute pas de
     dépendance. */
  function courbe(points) {
    if (!points || points.length < 2) return '';
    var vals = points.map(function (p) { return Number(p.mmr) || 0; });
    var min = Math.min.apply(null, vals);
    var max = Math.max.apply(null, vals);
    /* Tout plat : une étendue nulle diviserait par zéro et la courbe
       disparaîtrait. On la pose au milieu, ce qui est la vérité. */
    var etendue = (max - min) || 1;
    var d = vals.map(function (v, i) {
      var x = (i / (vals.length - 1)) * 100;
      var y = 30 - ((v - min) / etendue) * 30;
      return x.toFixed(2) + ',' + y.toFixed(2);
    }).join(' ');
    return '<svg class="courbe" viewBox="0 0 100 30" preserveAspectRatio="none" ' +
      'role="img" aria-label="' + esc(t('fi.curve')) + '">' +
      '<polyline class="courbe__trait" points="' + d + '"/></svg>';
  }

  function rendreFiche(f, err) {
    var carte = $('[data-player-card]');
    if (!carte) return;
    if (err) { carte.hidden = false; carte.innerHTML = '<div class="grp__card">' + panne(err) + '</div>'; return; }
    if (!f) { carte.hidden = true; carte.innerHTML = ''; return; }

    var avatar = f.avatar
      ? '<img class="fiche__av" src="' + esc(f.avatar) + '" alt="" width="44" height="44">'
      : '';
    var duos = (f.mates || []).map(function (m) {
      return esc(m.name || ('#' + String(m.id).slice(-4))) + ' <span class="match__lose">×' + (m.count | 0) + '</span>';
    }).join(' · ');

    carte.hidden = false;
    carte.innerHTML =
      '<h2 class="grp__title">' + esc(t('fi.title')) + '</h2>' +
      '<div class="grp__card grp__card--pad">' +
        '<div class="fiche">' +
          '<div class="fiche__id">' + avatar +
            '<span><span class="fiche__nom">' + esc(f.name || ('#' + String(f.id).slice(-4))) + '</span>' +
            /* Un MMR absent s'écrit « — » : « undefined MMR » serait pire
               que rien, et le bot peut répondre sans cette valeur si le
               classement est éteint sur ce serveur. */
            '<span class="fiche__mmr">' +
              esc(f.mmr == null ? '—' : t('fi.mmr', { n: f.mmr })) + '</span></span>' +
          '</div>' +
          '<button class="pill pill--ghost pill--sm" type="button" data-fiche-close>' +
            esc(t('fi.close')) + '</button>' +
        '</div>' +
        '<div class="chiffres" style="margin-top:16px">' +
          chiffre(f.matches, 'fi.matches') +
          chiffre(f.wins, 'fi.wins') +
          chiffre(f.losses, 'fi.losses') +
          chiffre(f.mvp, 'fi.mvp') +
          chiffre(f.streak, 'fi.streak') +
        '</div>' +
        (f.partial ? '<p class="rank__note" style="margin-top:14px">' + esc(t('fi.partial')) + '</p>' : '') +
        (courbe(f.curve) ? '<div class="courbe__boite">' + courbe(f.curve) + '</div>' : '') +
        (duos ? '<p class="rank__note" style="margin-top:14px">' + esc(t('fi.mates')) + ' ' + duos + '</p>' : '') +
      '</div>';
  }

  function chiffre(n, cle) {
    return '<span class="chiffre"><span class="chiffre__n">' + (n | 0) + '</span>' +
      '<span class="chiffre__l">' + esc(t(cle)) + '</span></span>';
  }

  /* Un clic sur un pseudo, n'importe où dans la section : délégué, parce
     que les lignes sont refabriquées à chaque page. */
  hote.addEventListener('click', function (e) {
    var ferme = e.target.closest('[data-fiche-close]');
    if (ferme) { rendreFiche(null); return; }
    var bouton = e.target.closest('[data-joueur]');
    if (!bouton) return;
    var uid = bouton.getAttribute('data-joueur');
    lire('/players/' + encodeURIComponent(uid))
      .then(function (f) { rendreFiche(f); })
      .catch(function (err) { rendreFiche(null, err); });
    var carte = $('[data-player-card]');
    if (carte) carte.scrollIntoView({ block: 'nearest' });
  });

  /* ================================================================== */
  /* 3. LES STATISTIQUES                                                 */
  /* ================================================================== */

  function barres(valeurs, etiquettes, titre) {
    var max = Math.max.apply(null, valeurs.concat([1]));
    var corps = valeurs.map(function (v, i) {
      var h = Math.round((v / max) * 100);
      return '<span class="barre" title="' + esc(etiquettes[i] + ' · ' + v) + '">' +
        '<span class="barre__fill" style="height:' + h + '%"></span></span>';
    }).join('');
    /* L'axe ne porte qu'une étiquette sur trois : à 375 px, vingt-quatre
       nombres côte à côte se chevauchent et ne se lisent plus. */
    var axe = etiquettes.map(function (l, i) {
      return '<span>' + (i % 3 === 0 ? esc(l) : '') + '</span>';
    }).join('');
    return '<div role="img" aria-label="' + esc(titre) + '">' +
      '<div class="barres">' + corps + '</div>' +
      '<div class="barres__axe">' + axe + '</div></div>';
  }

  function rendreStats(d, err) {
    var nums = $('[data-stats-nums]');
    var heures = $('[data-stats-hours]');
    var jours = $('[data-stats-days]');
    if (!nums) return;

    if (err) {
      nums.innerHTML = panne(err);
      if (heures) heures.innerHTML = '';
      if (jours) jours.innerHTML = '';
      return;
    }

    /* Un taux d'abandon inconnu s'écrit « — » et non « 0 % » : aucune file
       ouverte et aucune file abandonnée ne sont pas la même chose. */
    var taux = (d.abandonRate === null || d.abandonRate === undefined)
      ? '—' : d.abandonRate + ' %';
    var attente = (d.avgWait === null || d.avgWait === undefined)
      ? '—' : Math.round(d.avgWait / 60) + ' min';

    nums.innerHTML = '<div class="chiffres">' +
      chiffre(d.opened, 'st2.opened') +
      chiffre(d.launched, 'st2.launched') +
      chiffre(d.matches, 'st2.matches') +
      '<span class="chiffre"><span class="chiffre__n">' + esc(taux) + '</span>' +
        '<span class="chiffre__l">' + esc(t('st2.abandon')) + '</span></span>' +
      '<span class="chiffre"><span class="chiffre__n">' + esc(attente) + '</span>' +
        '<span class="chiffre__l">' + esc(t('st2.wait')) + '</span></span>' +
      '</div>';

    /* `bot/history.py:stats()` renvoie TOUJOURS ses vingt-quatre heures et
       ses trente jours, trous compris — c'est voulu, un graphique qui
       saute les jours creux ment sur le rythme. Mais du coup la liste
       n'est jamais vide, l'état vide ne s'affichait jamais, et un serveur
       sans activité se retrouvait avec vingt-quatre barres de hauteur
       nulle sous un axe : ça ne ressemble pas à « rien ne s'est passé »,
       ça ressemble à un écran cassé.

       On regarde donc les VALEURS, pas la longueur. Et on ne triche pas
       avec une hauteur minimale : un graphique vide se dit. */
    function duVide(valeurs) {
      return !valeurs.length || valeurs.every(function (v) { return !v; });
    }

    if (heures) {
      var parHeure = (d.byHour || []).map(Number);
      heures.innerHTML = duVide(parHeure)
        ? vide('st2.empty')
        : barres(parHeure, parHeure.map(function (_, i) { return i + 'h'; }), t('st2.grpHours'));
    }
    if (jours) {
      var parJour = d.byDay || [];
      var n = parJour.map(function (x) { return Number(x && x.n); });
      jours.innerHTML = duVide(n)
        ? vide('st2.empty')
        : barres(n, parJour.map(function (x) { return String(x.day || '').slice(8); }),
                 t('st2.grpDays'));
    }
  }

  /* ================================================================== */
  /* 4. LA BLACKLIST : liste du staff, exclusions automatiques           */
  /* ================================================================== */

  /* Ces deux listes viennent de la charge utile des RÉGLAGES, pas d'une
     route à part : elles sont courtes, et page-dashboard.js les a déjà
     chargées. On les récupère par l'événement qu'il émet. */

  /* Un vrai <table>, et non une grille avec des rôles ARIA. Trois colonnes
     alignées d'une ligne à l'autre, un en-tête qui les nomme, et un
     lecteur d'écran qui annonce « Motif, colonne 2 » sans qu'on ait à le
     lui apprendre : c'est exactement ce qu'un tableau sait faire, et
     refaire ce travail en div coûterait six attributs par cellule.

     `data-th` porte le nom de la colonne sur chaque cellule. Il ne sert
     qu'au petit écran, où le tableau s'empile et où une valeur seule ne
     dirait plus de quelle colonne elle vient. */
  function cellule(valeur, colonne) {
    return '<td data-th="' + esc(t(colonne)) + '">' + valeur + '</td>';
  }

  function rendreAcces(donnees) {
    var noire = $('[data-blacklist]');
    var autos = $('[data-queuebans]');
    var compteur = $('[data-nav-count="blacklist"]');

    var liste = (donnees && donnees.blacklist) || [];
    if (noire) {
      noire.innerHTML = liste.length
        ? '<table class="tbl"><thead><tr>' +
            '<th scope="col">' + esc(t('ac.colMember')) + '</th>' +
            '<th scope="col">' + esc(t('ac.colReason')) + '</th>' +
            '<th scope="col">' + esc(t('ac.colSince')) + '</th>' +
            '<th scope="col"><span class="sr-only">' + esc(t('ac.colAction')) + '</span></th>' +
          '</tr></thead><tbody>' +
          liste.map(function (e) {
            /* Le nom, ou l'identifiant tronqué : le panneau ne charge pas
               les membres, et il n'a parfois que le numéro. */
            return '<tr>' +
              cellule(esc(e.name || ('#' + String(e.id).slice(-4))), 'ac.colMember') +
              cellule('<span class="tbl__sourd">' + esc(e.reason || t('ac.noReason')) + '</span>', 'ac.colReason') +
              cellule('<span class="tbl__date">' + esc(quand(e.at)) + '</span>', 'ac.colSince') +
              '<td class="tbl__fin">' +
                '<button class="pill pill--ghost pill--sm" type="button" data-ban-del="' + esc(e.id) + '">' +
                  esc(t('ac.banRemove')) + '</button>' +
              '</td></tr>';
          }).join('') +
          '</tbody></table>'
        : vide('ac.blacklistEmpty');
    }

    var bans = (donnees && donnees.queueBans) || [];
    if (autos) {
      autos.innerHTML = bans.length ? bans.map(function (e) {
        var fin = quand(e.until);
        return '<div class="row"><div class="ligne">' +
          '<span class="ligne__qui">' + esc(e.name || ('#' + String(e.id).slice(-4))) + '</span>' +
          '<span class="ligne__quoi">' + esc(fin ? t('ac.until', { date: fin }) : '') + '</span>' +
          '</div><div class="row__ctl">' +
            '<button class="pill pill--ghost pill--sm" type="button" data-ban-lift="' + esc(e.id) + '">' +
              esc(t('ac.lift')) + '</button>' +
          '</div></div>';
      }).join('') : vide('ac.autoEmpty');
    }

    if (compteur) {
      var n = liste.length + bans.length;
      compteur.textContent = n ? String(n) : '';
    }
  }

  /* Le seul geste qui ÉCRIT dans ces six écrans. Il passe par sa propre
     route parce que c'est un geste et non un réglage : envoyer la liste
     entière effacerait ce qu'un autre onglet vient d'ajouter. */
  function geste(corps) {
    var err = $('[data-ban-err]');
    if (err) err.hidden = true;
    if (!base || !CYQ.api || !CYQ.api.configured) {
      if (err) { err.hidden = false; err.textContent = t('me.noApi'); }
      return;
    }
    CYQ.api.post(base + '/bans', corps).then(function (d) {
      rendreAcces(d);
      var champ = $('[data-ban-id]');
      var motif = $('[data-ban-reason]');
      if (champ) champ.value = '';
      if (motif) motif.value = '';
    }).catch(function (e) {
      if (err) {
        err.hidden = false;
        err.textContent = e && e.motif === 'BOT_INJOIGNABLE' ? t('me.botOff') : t('me.error');
      }
    });
  }

  var ajout = $('[data-ban-add]');
  if (ajout) {
    ajout.addEventListener('click', function () {
      var champ = $('[data-ban-id]');
      var motif = $('[data-ban-reason]');
      var id = champ ? champ.value.trim() : '';
      var err = $('[data-ban-err]');
      /* Vérifié ICI aussi, et pas seulement côté serveur : un refus qui
         revient d'un aller-retour pour une faute de frappe est un refus
         qu'on aurait pu éviter. */
      if (!/^\d{5,25}$/.test(id)) {
        if (err) { err.hidden = false; err.textContent = t('ac.badId'); }
        return;
      }
      geste({ add: [id], reason: motif ? motif.value.trim() : '' });
    });
  }

  var sectionAcces = $('[data-section="blacklist"]');
  if (sectionAcces) {
    sectionAcces.addEventListener('click', function (e) {
      var sup = e.target.closest('[data-ban-del]');
      if (sup) { geste({ remove: [sup.getAttribute('data-ban-del')] }); return; }
      var leve = e.target.closest('[data-ban-lift]');
      if (leve) { geste({ lift: [leve.getAttribute('data-ban-lift')] }); }
    });
  }

  /* ================================================================== */
  /* 5. LE JOURNAL                                                       */
  /* ================================================================== */

  function rendreJournal(d, err) {
    var carte = $('[data-journal]');
    if (!carte) return;
    if (err) { carte.innerHTML = panne(err); return; }
    var lignes = (d && d.entries) || [];
    if (!lignes.length) { carte.innerHTML = vide('jo.empty'); return; }

    carte.innerHTML = lignes.map(function (l) {
      var qui = (l.who && l.who.name) || t('jo.someone');
      var quoi = (l.details && l.details.length)
        ? l.details.join(', ')
        : l.action;
      return '<div class="row"><div class="ligne">' +
        '<span class="ligne__date">' + esc(quand(l.at)) + '</span>' +
        '<span class="ligne__qui">' + esc(qui) + '</span>' +
        '<span class="ligne__quoi">' + esc(quoi) + '</span>' +
        '<span class="ligne__ou">' + esc(t(l.source === 'panel' ? 'jo.panel' : 'jo.discord')) + '</span>' +
        '</div></div>';
    }).join('');
  }

  /* ================================================================== */
  /* 6. LE PALMARÈS                                                      */
  /* ================================================================== */

  function rendrePalmares(donnees) {
    var carte = $('[data-seasons]');
    if (!carte) return;
    var liste = (donnees && donnees.season && donnees.season.archive) || [];
    if (!liste.length) { carte.innerHTML = vide('se2.empty'); return; }
    /* Le bot ajoute à la fin ; on lit du plus récent au plus ancien. */
    carte.innerHTML = liste.slice().reverse().map(function (s) {
      var podium = (s.podium || []).map(function (p, i) {
        return ['🥇', '🥈', '🥉'][i] + ' ' +
          esc(String(p.user_id).slice(-4)) + ' · ' + (p.wins | 0);
      }).join('  ');
      return '<div class="row"><div class="ligne">' +
        '<span class="ligne__qui">' + esc(s.period || '') + '</span>' +
        '<span class="ligne__quoi">' + podium + '</span>' +
        '</div></div>';
    }).join('');
  }

  /* ================================================================== */
  /* 7. EMPORTER LA CONFIGURATION                                        */
  /* ================================================================== */

  /* Tout se passe DANS le navigateur. L'export fabrique un fichier depuis
     les champs déjà remplis ; l'import le relit et les remplit. Rien n'est
     envoyé tant qu'on n'a pas enregistré, ce qui laisse le temps de
     regarder ce qui est arrivé — un import qui écrirait directement en
     base ne laisserait aucune marche arrière.

     CE QUI N'EST PAS EXPORTÉ, et c'est le cœur du geste : ce qui désigne
     CE serveur. Un identifiant de salon ou de rôle ne veut rien dire
     ailleurs, et l'y poser ferait pointer la configuration vers le vide.
     Le mot de passe de queue non plus : un fichier qu'on s'échange n'est
     pas un endroit pour un secret. */
  var PAS_EXPORTABLE = /^(channel\.|role\.|antilink\.|log\.[a-z]+\.channel$|queue\.passwordValue$|security\.autocleanChannel$|security\.antilinkList$|webhook\.url$|bot\.nick$)/;

  function champsExportables() {
    var sortie = {};
    $$('[data-setting]').forEach(function (f) {
      var cle = f.getAttribute('data-setting');
      if (!cle || PAS_EXPORTABLE.test(cle)) return;
      if (f.type === 'radio' && !f.checked) return;
      sortie[cle] = f.type === 'checkbox' ? (f.checked ? '1' : '0') : f.value;
    });
    return sortie;
  }

  var exporter = $('[data-export]');
  if (exporter) {
    exporter.addEventListener('click', function () {
      var contenu = JSON.stringify({
        /* La version sert à refuser un fichier d'une forme qu'on ne sait
           pas lire, le jour où elle changera. */
        cyq: 1,
        at: new Date().toISOString(),
        settings: champsExportables()
      }, null, 2);
      var lien = document.createElement('a');
      var url = URL.createObjectURL(new Blob([contenu], { type: 'application/json' }));
      lien.href = url;
      lien.download = 'cyq-config.json';
      document.body.appendChild(lien);
      lien.click();
      document.body.removeChild(lien);
      /* L'URL d'objet retient le fichier en mémoire tant qu'on ne la
         libère pas. Au tour suivant : la révoquer tout de suite peut
         couper le téléchargement dans certains navigateurs. */
      setTimeout(function () { URL.revokeObjectURL(url); }, 0);
    });
  }

  var importer = $('[data-import]');
  var fichier = $('[data-import-file]');
  if (importer && fichier) {
    importer.addEventListener('click', function () { fichier.click(); });
    fichier.addEventListener('change', function () {
      var err = $('[data-import-err]');
      if (err) err.hidden = true;
      var f = fichier.files && fichier.files[0];
      if (!f) return;
      /* Un fichier n'est pas une page : on borne sa taille avant de le
         lire. 256 ko, c'est cent fois une configuration complète. */
      if (f.size > 262144) {
        if (err) { err.hidden = false; err.textContent = t('px.tooBig'); }
        fichier.value = '';
        return;
      }
      var lecteur = new FileReader();
      lecteur.onload = function () {
        var data;
        try { data = JSON.parse(String(lecteur.result)); }
        catch (e) { data = null; }
        if (!data || data.cyq !== 1 || typeof data.settings !== 'object') {
          if (err) { err.hidden = false; err.textContent = t('px.badFile'); }
          fichier.value = '';
          return;
        }
        var poses = 0;
        Object.keys(data.settings).forEach(function (cle) {
          if (PAS_EXPORTABLE.test(cle)) return;
          var champs = $$('[data-setting="' + (window.CSS && CSS.escape ? CSS.escape(cle) : cle) + '"]');
          if (!champs.length) return;
          var v = data.settings[cle];
          champs.forEach(function (ch) {
            if (ch.type === 'checkbox') ch.checked = (v === '1' || v === true);
            else if (ch.type === 'radio') ch.checked = (String(v) === ch.value);
            else ch.value = v == null ? '' : String(v);
            /* Un « change » par champ : c'est lui qui marque la section
               comme modifiée et fait apparaître la barre d'enregistrement.
               Sans lui, l'import remplirait les champs en silence et
               personne ne saurait qu'il reste un geste à faire. */
            ch.dispatchEvent(new Event('change', { bubbles: true }));
          });
          poses += 1;
        });
        if (err) {
          err.hidden = false;
          /* Le dictionnaire n'accorde pas : le singulier a sa propre
             clé, comme c.change à côté de c.changes. */
          err.textContent = !poses ? t('px.nothing')
            : poses === 1 ? t('px.loadedOne') : t('px.loaded', { n: poses });
        }
        fichier.value = '';
      };
      lecteur.readAsText(f);
    });
  }

  /* ================================================================== */
  /* LE CHARGEMENT PARESSEUX                                             */
  /* ================================================================== */

  /* Une section se charge À SA PREMIÈRE VISITE. Tout charger au démarrage
     ferait payer l'historique et les statistiques à quelqu'un venu
     changer un salon. */
  function visiter(nom) {
    if (charge[nom]) return;
    /* Le drapeau sert à deux choses, et une seule des deux est permanente.

       Il empêche un second appel de partir pendant que le premier est en
       vol — ça, il faut le poser tout de suite. Mais il disait aussi
       « cette section est chargée », et posé AVANT la réponse il le disait
       même quand la réponse n'arrivait jamais : le bot éteint une seconde,
       et la section restait vide pour le reste de la visite. On y revenait,
       elle se croyait faite, plus rien ne repartait, et le bandeau « API
       injoignable » n'avait aucun moyen de se démentir.

       Il retombe donc à l'échec : revenir sur la section relance l'appel,
       ce qui est exactement ce qu'on attend en revenant dessus. */
    charge[nom] = true;
    function echoue(e) { charge[nom] = false; return e; }

    if (nom === 'historique') {
      chargerHistorique(false).catch(echoue);
    } else if (nom === 'stats') {
      lire('/activity?days=30')
        .then(function (d) { rendreStats(d); })
        .catch(function (e) { rendreStats(null, echoue(e)); });
    } else if (nom === 'journal') {
      lire('/audit?limit=50')
        .then(function (d) { rendreJournal(d); })
        .catch(function (e) { rendreJournal(null, echoue(e)); });
    }
  }

  /* Le panneau annonce chaque changement de section ; sans cet événement,
     il faudrait surveiller le hash, qui ne dit rien des retours arrière. */
  document.addEventListener('cyq:section', function (e) {
    if (e && e.detail) visiter(e.detail);
  });

  /* Les deux listes d'accès et le palmarès viennent des réglages, que
     page-dashboard.js a déjà chargés. Il les repasse par cet événement. */
  document.addEventListener('cyq:guild', function (e) {
    rendreAcces(e && e.detail);
    rendrePalmares(e && e.detail);
  });

  /* Arrivée directement sur #historique : l'événement de section est déjà
     passé quand ce script se branche. */
  var depart = (window.location.hash || '').replace('#', '');
  if (depart) visiter(depart);
})();
