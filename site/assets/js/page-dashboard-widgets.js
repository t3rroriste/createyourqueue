/* =========================================================================
   CreateYourQueue — le tableau de bord se range comme on veut
   =========================================================================
   L'écran d'arrivée n'est plus une page figée : chaque bloc est un widget
   qu'on pose, qu'on retire, qu'on déplace et qu'on élargit. Ce fichier
   tient la DISPOSITION — rien d'autre. Le CONTENU des widgets reste
   écrit par ceux qui l'ont toujours écrit :

     page-dashboard-apercu.js   les chiffres, la semaine
     page-dashboard-memoire.js  l'activité récente
     ce fichier-ci              les cinq fiches de la collection, qui
                                n'existaient pas avant lui

   LES WIDGETS NE SONT JAMAIS FABRIQUÉS NI DÉTRUITS. Ils sont tous écrits
   dans dashboard.html ; retirer un widget le passe en `hidden`, le poser
   le rend visible. C'est ce qui permet aux deux autres scripts d'écrire
   dedans sans jamais se demander si leur hôte existe — un `innerHTML`
   dans un nœud caché est sans effet visible et sans erreur, et le widget
   reparaît déjà rempli. Les fabriquer à la demande aurait obligé ces
   scripts à redessiner à un moment qu'ils n'ont aucun moyen de connaître.

   LA DISPOSITION VIT DANS LE NAVIGATEUR, pas chez le bot, et c'est un
   choix. Ce n'est pas un réglage du serveur Discord : deux organisateurs
   du même serveur ne rangent pas leur écran pareil, et l'un n'a pas à
   imposer le sien à l'autre. Elle n'a donc aucun pont `PONT_*` à tenir
   d'accord dans api/index.php, et — ce qui compte le jour où ça casse —
   elle se range et se relit même quand le bot ne répond pas.

   Elle est gardée PAR SERVEUR : on ne regarde pas la même chose sur un
   serveur de 2 000 membres et sur celui où l'on teste.
   ========================================================================= */

(function () {
  'use strict';

  var sec = document.querySelector('[data-section="apercu"]');
  if (!sec) return;

  var CYQ = window.CYQ;
  if (!CYQ) return;

  var grille = sec.querySelector('[data-ov-grid]');
  var barre  = sec.querySelector('[data-ov-bar]');
  var galerie = sec.querySelector('[data-ov-gal]');
  var motVide = sec.querySelector('[data-ov-vide]');
  if (!grille || !barre || !galerie) return;

  function $(sel, root) { return (root || sec).querySelector(sel); }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || sec).querySelectorAll(sel));
  }
  function t(cle, vars) { return CYQ.t(cle, vars); }
  function esc(s) { return CYQ.esc(String(s == null ? '' : s)); }
  function icon(nom, taille) { return CYQ.icon(nom, taille); }

  var guildId = new URLSearchParams(location.search).get('guild') || '';
  var guilde = null;

  var TIRET = '—';

  /* ==================================================================
     LA COLLECTION

     `id` est écrit dans la page (`data-w`) ET dans la disposition
     enregistrée : le renommer casserait les tableaux de bord déjà
     rangés, qui porteraient alors un identifiant que ce script ne
     connaît plus. C'est une clé, pas un libellé — le libellé est `nom`,
     et lui change avec la langue.

     `defaut` est la largeur de départ, en douzièmes. Elle ne vaut que
     pour la disposition par défaut et pour un widget qu'on vient de
     poser : une largeur choisie à la main l'emporte toujours.
     ================================================================== */

  var CATALOGUE = [
    { id: 'membres',       nom: 'ov.wMembers',  des: 'ov.wMembersD',  defaut: 3 },
    { id: 'boosts',        nom: 'ov.wBoosts',   des: 'ov.wBoostsD',   defaut: 3 },
    { id: 'anciennete',    nom: 'ov.wSince',    des: 'ov.wSinceD',    defaut: 3 },
    { id: 'queues',        nom: 'ov.wMatches',  des: 'ov.wMatchesD',  defaut: 3 },
    { id: 'derniere',      nom: 'ov.wLast',     des: 'ov.wLastD',     defaut: 3 },
    { id: 'raccourcis',    nom: 'ov.wQuick',    des: 'ov.wQuickD',    defaut: 9 },
    { id: 'semaine',       nom: 'ov.wWeek',     des: 'ov.wWeekD',     defaut: 6 },
    { id: 'activite',      nom: 'ov.wJournal',  des: 'ov.wJournalD',  defaut: 6 },
    { id: 'gerer',         nom: 'ov.wManage',   des: 'ov.wManageD',   defaut: 12 },
    { id: 'serveur',       nom: 'ov.wServer',   des: 'ov.wServerD',   defaut: 6 },
    { id: 'format',        nom: 'ov.wFormat',   des: 'ov.wFormatD',   defaut: 6 },
    { id: 'salons',        nom: 'ov.wChannels', des: 'ov.wChannelsD', defaut: 6 },
    { id: 'programmation', nom: 'ov.wSchedule', des: 'ov.wScheduleD', defaut: 6 },
    { id: 'droits',        nom: 'ov.wPerms',    des: 'ov.wPermsD',    defaut: 6 }
  ];

  /* La disposition de départ, et celle que « Réinitialiser » remet. Les
     cinq chiffres puis les raccourcis font une première rangée pleine,
     la semaine et l'activité la deuxième : des rangées qui se terminent,
     parce qu'un trou en bout de rangée se lit comme un widget manquant.
     Les cinq derniers du catalogue dorment dans la collection. */
  var DEFAUT = [
    { id: 'membres', t: 3 }, { id: 'boosts', t: 3 }, { id: 'anciennete', t: 3 },
    { id: 'queues', t: 3 }, { id: 'derniere', t: 3 }, { id: 'raccourcis', t: 9 },
    { id: 'semaine', t: 6 }, { id: 'activite', t: 6 },
    { id: 'gerer', t: 12 }
  ];

  /* Les quatre largeurs, en douzièmes. Quatre et non un curseur libre :
     un quart, une moitié, trois quarts, toute la largeur sont les seules
     qui retombent sur une rangée pleine, et une largeur de 5/12 ne laisse
     que des trous. Le bouton les fait tourner dans cet ordre. */
  var TAILLES = [3, 6, 9, 12];

  function nomTaille(n) {
    return t({ 3: 'ov.sizeQuarter', 6: 'ov.sizeHalf',
               9: 'ov.sizeThree', 12: 'ov.sizeFull' }[n] || 'ov.sizeHalf');
  }

  function fiche(id) {
    for (var i = 0; i < CATALOGUE.length; i++) {
      if (CATALOGUE[i].id === id) return CATALOGUE[i];
    }
    return null;
  }

  function noeud(id) { return grille.querySelector('[data-w="' + id + '"]'); }

  /* ==================================================================
     CE QU'ON GARDE

     Une seule clé par serveur, et une valeur qui se relit sans rien
     savoir du catalogue d'avant : une liste d'objets {id, t}. Un widget
     disparu du catalogue est ignoré à la relecture plutôt que de faire
     échouer tout le reste — c'est ce qui permet d'en retirer un du code
     sans casser les tableaux de bord déjà rangés.
     ================================================================== */

  var CLE = 'cyq.widgets.' + (guildId || 'sans-serveur');

  function lire() {
    var brut = null;
    try { brut = localStorage.getItem(CLE); }
    catch (e) { return DEFAUT.slice(); }   /* navigation privée : le défaut */
    if (!brut) return DEFAUT.slice();

    var liste;
    try { liste = JSON.parse(brut); } catch (e) { return DEFAUT.slice(); }
    if (!liste || !liste.length) return [];   /* vraiment vide, pas « jamais rangé » */

    var vus = {}, propre = [];
    liste.forEach(function (w) {
      var id = w && w.id;
      if (!id || vus[id] || !fiche(id)) return;   /* inconnu ou en double */
      vus[id] = true;
      propre.push({ id: id, t: TAILLES.indexOf(w.t) === -1 ? fiche(id).defaut : w.t });
    });
    return propre;
  }

  function ecrire(d) {
    try { localStorage.setItem(CLE, JSON.stringify(d)); }
    catch (e) { /* navigation privée, stockage plein : on range quand même
                   l'écran, il ne survivra simplement pas au rechargement */ }
  }

  function oublier() {
    try { localStorage.removeItem(CLE); } catch (e) { /* idem */ }
  }

  var dispo = lire();

  /* ==================================================================
     POSER LA DISPOSITION

     `appendChild` sur un nœud déjà dans la page le DÉPLACE : rien n'est
     recréé, donc rien ne perd ni son contenu, ni ses écouteurs, ni le
     focus du clavier s'il était dedans.
     ================================================================== */

  function appliquer() {
    var poses = {};
    dispo.forEach(function (w) {
      var el = noeud(w.id);
      if (!el) return;
      poses[w.id] = true;
      el.hidden = false;
      el.className = 'ovw ovw--s' + w.t;
      grille.appendChild(el);
    });

    /* Ceux qui ne sont pas posés : cachés, et rangés à la fin pour que
       l'ordre du DOM suive l'ordre affiché — sans quoi la tabulation
       sautait d'un widget à l'autre dans l'ordre d'écriture du HTML. */
    CATALOGUE.forEach(function (c) {
      if (poses[c.id]) return;
      var el = noeud(c.id);
      if (!el) return;
      el.hidden = true;
      grille.appendChild(el);
    });

    if (motVide) {
      motVide.hidden = dispo.length > 0;
      motVide.textContent = dispo.length ? '' : t('ov.allRemoved');
    }

    combler();
  }

  /* ==================================================================
     LES RANGÉES SE TERMINENT

     Une largeur choisie ne tombe pas juste à toutes les tailles d'écran.
     Cinq quarts de largeur suivis d'un bloc pleine page font, sur un
     téléphone où un quart vaut une demi-colonne, deux rangées pleines
     puis une carte SEULE avec un trou à sa droite — et un trou en bout
     de rangée se lit comme une carte qui manque, pas comme un choix.

     On répartit donc ce qui reste sur les widgets de la rangée, en
     commençant par le dernier. Jamais en retirant : une case ne fait que
     grandir pour finir sa rangée, et la largeur enregistrée, elle, ne
     bouge pas — l'écran large la retrouve intacte.

     LES LARGEURS VIENNENT DE LA FEUILLE DE STYLE, pas d'un calcul. Un
     quart devient une moitié sous 1080 px et toute la largeur sous
     560 px : ce sont des décisions de mise en page, pas des divisions,
     et les refaire ici aurait posé une deuxième liste de points de
     rupture à tenir d'accord avec la première. On EFFACE donc ce qu'on
     avait posé, on LIT ce que le CSS donne, et on ne repose que le
     complément.
     ================================================================== */

  function colonnes() {
    var c = '';
    try { c = getComputedStyle(grille).gridTemplateColumns || ''; } catch (e) { return 12; }
    var n = c.split(' ').filter(function (x) { return x; }).length;
    return n > 0 ? n : 12;
  }

  /* `grid-column: span 3` pose la portée sur le DÉBUT et laisse la fin à
     `auto` — lire la fin seule rendait « auto » pour tout le monde, donc
     une colonne pour tout le monde, et la rangée se remplissait de
     travers. On lit les deux, le début d'abord. */
  function portee(el) {
    var st;
    try { st = getComputedStyle(el); } catch (e) { return 1; }
    var m = /span\s+(\d+)/.exec(st.gridColumnStart || '') ||
            /span\s+(\d+)/.exec(st.gridColumnEnd || '');
    return m ? parseInt(m[1], 10) : 1;
  }

  var colonnesVues = 0;

  function combler() {
    var poses = [];
    dispo.forEach(function (w) {
      var el = noeud(w.id);
      if (!el) return;
      el.style.gridColumn = '';     /* d'abord effacer : sinon on relit
                                       le complément du passage précédent */
      poses.push(el);
    });
    if (!poses.length) return;

    var cols = colonnesVues = colonnes();
    var rangees = [], rangee = [], reste = cols;

    poses.forEach(function (el) {
      var span = Math.max(1, Math.min(cols, portee(el)));
      if (span > reste) {
        rangees.push({ cases: rangee, reste: reste });
        rangee = []; reste = cols;
      }
      rangee.push({ el: el, span: span, nat: span });
      reste -= span;
    });
    rangees.push({ cases: rangee, reste: reste });

    rangees.forEach(function (r) {
      /* Une colonne à la fois, en partant de la fin : donner tout le
         reste au dernier aurait fait d'un quart de largeur un trois
         quarts dès qu'il finissait une rangée à moitié vide. */
      var i = r.cases.length - 1;
      while (r.reste > 0 && r.cases.length) {
        r.cases[i].span++;
        r.reste--;
        i = i === 0 ? r.cases.length - 1 : i - 1;
      }
      /* `nat` est la largeur lue AVANT tout complément : relire le style
         calculé ici rendrait ce qu'on vient d'écrire. */
      r.cases.forEach(function (c) {
        if (c.span !== c.nat) c.el.style.gridColumn = 'span ' + c.span;
      });
    });
  }

  /* La fenêtre change de largeur : la feuille de style redistribue les
     colonnes, et les compléments d'hier ne valent plus. On ne refait le
     calcul que si le NOMBRE de colonnes a bougé — redimensionner une
     fenêtre produit des dizaines d'évènements, et la quasi-totalité ne
     change rien à la grille. */
  window.addEventListener('resize', function () {
    if (colonnes() !== colonnesVues) combler();
  });

  function enregistrer() {
    ecrire(dispo);
    appliquer();
    if (edition) { poserChrome(); rendreGalerie(); }
  }

  /* ==================================================================
     LES GESTES
     ================================================================== */

  function index(id) {
    for (var i = 0; i < dispo.length; i++) if (dispo[i].id === id) return i;
    return -1;
  }

  function deplacer(id, vers) {
    var i = index(id);
    if (i === -1) return;
    var j = Math.max(0, Math.min(dispo.length - 1, vers));
    if (i === j) return;
    dispo.splice(j, 0, dispo.splice(i, 1)[0]);
    enregistrer();
    dire(t('ov.moved', { n: j + 1, total: dispo.length }));
    /* Le focus suit le widget : sans ça, un « Monter » répété obligeait à
       retrouver le bouton à la souris entre chaque pression. */
    var b = grille.querySelector('[data-w="' + id + '"] [data-w-up]');
    if (b) b.focus();
  }

  function retirer(id) {
    var i = index(id);
    if (i === -1) return;
    dispo.splice(i, 1);
    enregistrer();
    var f = fiche(id);
    dire(t('ov.removed', { nom: f ? t(f.nom) : id }));
  }

  function poser(id) {
    if (index(id) !== -1) return;
    var f = fiche(id);
    if (!f) return;
    dispo.push({ id: id, t: f.defaut });
    enregistrer();
    dire(t('ov.added', { nom: t(f.nom) }));
    /* On l'amène sous les yeux : ajouté en bas d'une page longue, il
       était ajouté « quelque part », et rien ne le disait. */
    var el = noeud(id);
    if (el && el.scrollIntoView) {
      el.scrollIntoView({ block: 'nearest',
        behavior: doux() ? 'smooth' : 'auto' });
    }
  }

  function agrandir(id) {
    var i = index(id);
    if (i === -1) return;
    var suivant = TAILLES[(TAILLES.indexOf(dispo[i].t) + 1) % TAILLES.length];
    dispo[i].t = suivant;
    enregistrer();
    dire(nomTaille(suivant));
    var b = grille.querySelector('[data-w="' + id + '"] [data-w-size-btn]');
    if (b) b.focus();
  }

  function reinitialiser() {
    oublier();
    dispo = DEFAUT.slice();
    enregistrer();
    dire(t('ov.resetDone'));
  }

  /* Le mouvement n'est pas une décision de ce fichier : il suit le
     réglage du système, et `?motion=on` le force pour pouvoir le
     regarder. Même règle que partout ailleurs sur le site. */
  function doux() {
    if (document.documentElement.classList.contains('motion-force')) return true;
    try { return !window.matchMedia('(prefers-reduced-motion: reduce)').matches; }
    catch (e) { return true; }
  }

  /* La page a déjà une région annoncée, une seule, au-dessus des
     sections. On s'en sert plutôt que d'en ouvrir une deuxième : deux
     régions aria-live sur le même écran se marchent dessus. */
  function dire(msg) {
    var live = document.querySelector('[data-live]');
    if (!live) return;
    live.textContent = '';
    setTimeout(function () { live.textContent = msg; }, 30);
  }

  /* ==================================================================
     LE MODE ÉDITION

     Hors édition, l'écran n'a RIEN de plus qu'avant : un bouton dans le
     chapeau, et c'est tout. Les poignées, les flèches et les croix
     n'existent que tant que le mode dure — un tableau de bord qu'on lit
     n'a pas à porter en permanence les commandes qui servent à le
     ranger.
     ================================================================== */

  var edition = false;

  function basculer(actif) {
    edition = !!actif;
    sec.classList.toggle('is-edit', edition);
    grille.classList.toggle('ovgrid--edit', edition);
    rendreBarre();
    poserChrome();
    rendreGalerie();
    if (!edition && galerie) galerie.hidden = true;
    dire(t(edition ? 'ov.editOn' : 'ov.editOff'));
  }

  function rendreBarre() {
    if (!edition) {
      barre.innerHTML =
        '<button class="pill pill--ghost pill--sm" type="button" data-ov-edit>' +
          icon('swap', 13) + '<span>' + esc(t('ov.customize')) + '</span>' +
        '</button>';
    } else {
      barre.innerHTML =
        '<button class="pill pill--ghost pill--sm" type="button" data-ov-add>' +
          icon('plus', 13) + '<span>' + esc(t('ov.addWidget')) + '</span>' +
        '</button>' +
        '<button class="pill pill--ghost pill--sm" type="button" data-ov-reset>' +
          icon('undo', 13) + '<span>' + esc(t('ov.reset')) + '</span>' +
        '</button>' +
        '<button class="pill pill--sm" type="button" data-ov-done>' +
          icon('check', 13) + '<span>' + esc(t('ov.customizeDone')) + '</span>' +
        '</button>';
    }
  }

  /* ---- la bande de commandes d'un widget ------------------------------
     Elle est RÉÉCRITE à chaque changement, et c'est voulu : « Monter »
     doit disparaître sur le premier, « Descendre » sur le dernier, et la
     taille affichée doit être la vraie. Tenir ces trois choses à jour une
     par une, c'était trois endroits où elles finiraient par mentir. */
  function poserChrome() {
    $$('[data-w]', grille).forEach(function (el) {
      var vieux = el.querySelector('[data-w-chrome]');
      if (vieux) vieux.parentNode.removeChild(vieux);
      el.removeAttribute('draggable');
      el.removeAttribute('role');
      el.removeAttribute('aria-label');
    });
    if (!edition) return;

    dispo.forEach(function (w, i) {
      var el = noeud(w.id);
      var f = fiche(w.id);
      if (!el || !f) return;

      el.setAttribute('role', 'group');
      el.setAttribute('aria-label', t(f.nom));
      el.setAttribute('draggable', 'true');

      var ch = document.createElement('div');
      ch.className = 'ovw__chrome';
      ch.setAttribute('data-w-chrome', '');
      ch.innerHTML =
        '<span class="ovw__grip" aria-hidden="true">' + icon('swap', 13) + '</span>' +
        /* Pas de nom dans la bande : chaque widget porte déjà le sien
           juste en dessous, et à 212 px de large il n'en restait que
           « Me… ». Le nom entier est dans l'`aria-label` du groupe, donc
           annoncé — il n'est pas perdu, il n'est pas répété. */
        '<span class="ovw__gap"></span>' +
        '<span class="ovw__acts">' +
          bouton('w-up', 'caret', t('ov.wUp'), i === 0, 'ovw__act--up') +
          bouton('w-down', 'caret', t('ov.wDown'), i === dispo.length - 1, '') +
          '<button class="ovw__act ovw__act--size" type="button" data-w-size-btn ' +
            'title="' + esc(t('ov.wSize')) + '" aria-label="' +
            esc(t('ov.wSize')) + ' — ' + esc(nomTaille(w.t)) + '">' +
            '<span aria-hidden="true">' + esc(w.t + '/12') + '</span>' +
          '</button>' +
          bouton('w-remove', 'x', t('ov.wRemove'), false, 'ovw__act--off') +
        '</span>';
      el.insertBefore(ch, el.firstChild);
    });
  }

  function bouton(attr, ic, titre, eteint, extra) {
    return '<button class="ovw__act ' + extra + '" type="button" data-' + attr +
      ' title="' + esc(titre) + '" aria-label="' + esc(titre) + '"' +
      (eteint ? ' disabled' : '') + '>' + icon(ic, 13) + '</button>';
  }

  /* ==================================================================
     LA COLLECTION, telle qu'on la parcourt

     Elle ne montre QUE ce qui n'est pas posé. Montrer les quatorze avec
     des coches aurait demandé de lire chaque ligne pour savoir laquelle
     ajoute quelque chose ; une liste qui raccourcit à chaque ajout se lit
     d'un coup d'œil, et elle se vide quand il n'y a plus rien à ajouter —
     ce qui est une réponse, pas un écran vide.
     ================================================================== */

  function rendreGalerie() {
    if (!edition) { galerie.innerHTML = ''; return; }
    var ouverte = !galerie.hidden;

    var absents = CATALOGUE.filter(function (c) { return index(c.id) === -1; });

    var corps = absents.length
      ? '<ul class="ovgal__liste">' + absents.map(function (c) {
          return '<li><button class="ovgal__item" type="button" data-w-add="' +
            esc(c.id) + '">' +
            '<span class="ovgal__t">' +
              '<span class="ovgal__n">' + esc(t(c.nom)) + '</span>' +
              '<span class="ovgal__d">' + esc(t(c.des)) + '</span>' +
            '</span>' +
            '<span class="ovgal__go" aria-hidden="true">' + icon('plus', 14) + '</span>' +
          '</button></li>';
        }).join('') + '</ul>'
      : '<p class="ovgal__vide">' + esc(t('ov.galleryEmpty')) + '</p>';

    galerie.innerHTML =
      '<div class="ovgal__head">' +
        '<h2 class="grp__title">' + esc(t('ov.gallery')) + '</h2>' +
        '<button class="ovw__act" type="button" data-ov-gal-close ' +
          'title="' + esc(t('c.close')) + '" aria-label="' + esc(t('c.close')) + '">' +
          icon('x', 13) + '</button>' +
      '</div>' + corps;

    galerie.hidden = !ouverte;
  }

  /* ==================================================================
     LE GLISSER-DÉPOSER

     Il DOUBLE les flèches, il ne les remplace pas : une poignée qui se
     tire à la souris n'existe pas au clavier, et sur un écran tactile
     elle entre en conflit avec le défilement. « Monter » et « Descendre »
     restent donc le chemin complet, et celui-ci est le raccourci.

     On ne déplace que la LIGNE de la disposition, jamais le nœud pendant
     le glissé : `appliquer()` repose tout à la fin, une seule fois.
     ================================================================== */

  var tire = null;

  grille.addEventListener('dragstart', function (e) {
    if (!edition) return;
    var el = e.target && e.target.closest && e.target.closest('[data-w]');
    if (!el) return;
    tire = el.getAttribute('data-w');
    el.classList.add('is-drag');
    try {
      e.dataTransfer.effectAllowed = 'move';
      /* Firefox n'ouvre pas de glissé sans charge utile. */
      e.dataTransfer.setData('text/plain', tire);
    } catch (err) { /* un glissé sans presse-papiers reste un glissé */ }
  });

  grille.addEventListener('dragend', function () {
    tire = null;
    $$('.is-drag', grille).forEach(function (el) { el.classList.remove('is-drag'); });
    $$('.is-over', grille).forEach(function (el) { el.classList.remove('is-over'); });
  });

  grille.addEventListener('dragover', function (e) {
    if (!edition || !tire) return;
    e.preventDefault();
    try { e.dataTransfer.dropEffect = 'move'; } catch (err) { /* idem */ }
    var el = e.target && e.target.closest && e.target.closest('[data-w]');
    $$('.is-over', grille).forEach(function (x) { x.classList.remove('is-over'); });
    if (el && el.getAttribute('data-w') !== tire) el.classList.add('is-over');
  });

  grille.addEventListener('drop', function (e) {
    if (!edition || !tire) return;
    e.preventDefault();
    var el = e.target && e.target.closest && e.target.closest('[data-w]');
    var cible = el && el.getAttribute('data-w');
    if (cible && cible !== tire) deplacer(tire, index(cible));
    tire = null;
  });

  /* ==================================================================
     LES CLICS

     Un seul écouteur sur la section, et non un par bouton : les boutons
     sont réécrits à chaque changement, et des écouteurs posés sur eux
     disparaîtraient avec eux.
     ================================================================== */

  sec.addEventListener('click', function (e) {
    var c = e.target && e.target.closest;
    if (!c) return;

    if (e.target.closest('[data-ov-edit]')) { basculer(true); return; }
    if (e.target.closest('[data-ov-done]')) { basculer(false); return; }

    if (e.target.closest('[data-ov-add]')) {
      galerie.hidden = !galerie.hidden;
      if (!galerie.hidden) {
        galerie.scrollIntoView({ block: 'nearest',
          behavior: doux() ? 'smooth' : 'auto' });
        var p = galerie.querySelector('.ovgal__item');
        if (p) p.focus();
      }
      return;
    }
    if (e.target.closest('[data-ov-gal-close]')) {
      galerie.hidden = true;
      var retour = barre.querySelector('[data-ov-add]');
      if (retour) retour.focus();
      return;
    }

    if (e.target.closest('[data-ov-reset]')) { reinitialiser(); return; }

    var ajout = e.target.closest('[data-w-add]');
    if (ajout) { poser(ajout.getAttribute('data-w-add')); return; }

    var hote = e.target.closest('[data-w]');
    if (!hote) return;
    var id = hote.getAttribute('data-w');

    if (e.target.closest('[data-w-up]'))        { deplacer(id, index(id) - 1); return; }
    if (e.target.closest('[data-w-down]'))      { deplacer(id, index(id) + 1); return; }
    if (e.target.closest('[data-w-size-btn]'))  { agrandir(id); return; }
    if (e.target.closest('[data-w-remove]'))    { retirer(id); return; }
  });

  /* Échap sort du mode édition — c'est le geste qu'on fait sans y penser
     quand on a fini. La collection d'abord si elle est ouverte : un seul
     Échap ne doit pas fermer deux choses à la fois. */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || !edition) return;
    if (!galerie.hidden) { galerie.hidden = true; return; }
    basculer(false);
    var b = barre.querySelector('[data-ov-edit]');
    if (b) b.focus();
  });

  /* ==================================================================
     LES CINQ FICHES DE LA COLLECTION

     Elles ne demandent RIEN au réseau : tout vient de la charge de
     `GET /guilds/{id}` que page-dashboard.js diffuse déjà. Un widget
     qu'on pose ne doit pas coûter un aller-retour.

     RIEN N'EST INVENTÉ, ici comme ailleurs : sans réponse, chaque ligne
     garde son tiret cadratin. « Non réglé » et « on ne sait pas » ne sont
     pas la même phrase, et les confondre ferait passer une panne d'API
     pour une configuration vide.
     ================================================================== */

  function reglage(cle) {
    var r = guilde && guilde.settings;
    if (!r) return null;                       /* on ne sait pas */
    var v = r[cle];
    if (v == null || String(v).trim() === '') return '';   /* non réglé */
    return String(v);
  }

  /* Le nom d'un salon ou d'un rôle, depuis les listes que
     page-dashboard.js a rangées pour les menus déroulants. L'identifiant
     brut ne dit rien à personne, et un identifiant qui ne figure plus
     dans la liste désigne un salon supprimé — ce que les menus disent
     déjà de leur côté, avec les mêmes mots. */
  function nommer(source, id, cleSupprime) {
    if (id === null) return TIRET;
    if (id === '') return t('ov.unset');
    var liste = (CYQ.data && CYQ.data[source]) || [];
    for (var i = 0; i < liste.length; i++) {
      if (String(liste[i].id) === id) return liste[i].name;
    }
    return liste.length ? t(cleSupprime) : TIRET;
  }

  function faits(nom, lignes) {
    var hote = grille.querySelector('[data-ov-facts="' + nom + '"]');
    if (!hote) return;
    hote.innerHTML = lignes.map(function (l) {
      return '<div class="ovfact">' +
        '<dt>' + esc(l[0]) + '</dt>' +
        '<dd' + (l[2] ? ' class="' + l[2] + '"' : '') + '>' + esc(l[1]) + '</dd>' +
      '</div>';
    }).join('');
  }

  function ouNon(v) { return v === null ? TIRET : (v === '' ? t('ov.unset') : v); }

  function rendreFiches() {
    /* ---- le serveur ---- */
    var g = guilde;
    faits('serveur', [
      [t('ov.fServerName'), g && g.name ? g.name : TIRET],
      [t('ov.members'), g && g.memberCount != null
        ? Number(g.memberCount).toLocaleString(CYQ.lang) : TIRET],
      [t('ov.fServerId'), guildId || TIRET],
      [t('ov.fLang'), ouNon(reglage('language'))]
    ]);

    /* ---- le format de queue ---- */
    var joueurs = reglage('queue.players');
    var equipes = reglage('queue.teams');
    faits('format', [
      [t('ov.fQueueName'), ouNon(reglage('queue.name'))],
      [t('ov.fPlayers'), ouNon(joueurs)],
      [t('ov.fTeams'), ouNon(equipes)],
      [t('ov.fType'), ouNon(reglage('queue.type'))]
    ]);

    /* ---- les salons et les rôles ---- */
    faits('salons', [
      [t('ch.commands'), nommer('channels', reglage('channel.commands'), 'ch.deleted')],
      [t('ch.announcements'), nommer('channels', reglage('channel.announcements'), 'ch.deleted')],
      [t('ch.results'), nommer('channels', reglage('channel.results'), 'ch.deleted')],
      [t('rl.organizer'), nommer('roles', reglage('role.organizer'), 'rl.deleted')]
    ]);

    /* ---- l'ouverture automatique ----
       `schedule.enabled` éteinte, les jours et l'heure ne prévoient plus
       rien : les afficher quand même aurait annoncé des ouvertures qui
       n'auront pas lieu. */
    var allumee = reglage('schedule.enabled');
    var active = allumee !== null && allumee !== '' &&
                 allumee !== '0' && allumee !== 'false' && allumee !== 'off';
    faits('programmation', [
      [t('ov.fState'), allumee === null ? TIRET : t(active ? 'c.enabled' : 'c.disabled')],
      [t('ov.fDays'), !active ? (allumee === null ? TIRET : t('ov.fNone')) : jours(reglage('schedule.days'))],
      [t('ov.fTime'), !active ? (allumee === null ? TIRET : t('ov.fNone')) : ouNon(reglage('schedule.time'))],
      [t('ov.fPreset'), !active ? (allumee === null ? TIRET : t('ov.fNone')) : ouNon(reglage('schedule.preset'))]
    ]);

    /* ---- les droits Discord ----
       La seule des quatre mesures de l'ancien « Prêt à lancer » qui ne se
       règle PAS dans le panneau : elle se répare sur Discord, ou en
       réinvitant le bot. Elle méritait donc de rester lisible ici.

       `missingPermissions` absent n'est pas une liste vide : le bot n'a
       pas répondu, et on ne sait pas. */
    var manque = g && g.missingPermissions;
    faits('droits', manque == null
      ? [[t('ov.fState'), TIRET], [t('ov.fPermsHow'), t('ov.unknownShort')]]
      : (manque.length
          ? [[t('ov.fState'), t('ov.fPermsMissing', { n: manque.length })],
             [t('ov.fPermsList'), manque.join(', ')]]
          : [[t('ov.fState'), t('dg.allGood')]]));
  }

  /* `schedule.days` compte à partir du LUNDI (0 = lundi, cf.
     bot/guild_settings.py). Les noms viennent d'Intl et non des cinq
     fichiers de langue : ce sont des noms du calendrier, pas des phrases
     du site, et chaque langue a déjà les siens. Même choix que
     page-dashboard-apercu.js. */
  function jours(brut) {
    if (brut === null) return TIRET;
    if (brut === '') return t('ov.fNone');
    /* Un lundi quelconque, pour nommer les sept jours dans l'ordre du bot. */
    var lundi = new Date(2024, 0, 1);
    var noms = brut.split(',').map(function (n) {
      var i = parseInt(String(n).trim(), 10);
      if (!(i >= 0 && i <= 6)) return null;
      var d = new Date(lundi.getTime() + i * 86400000);
      try { return d.toLocaleDateString(CYQ.lang, { weekday: 'short' }); }
      catch (e) { return String(i); }
    }).filter(Boolean);
    return noms.length ? noms.join(' · ') : t('ov.fNone');
  }

  /* ==================================================================
     LES BRANCHEMENTS
     ================================================================== */

  document.addEventListener('cyq:guild', function (e) {
    guilde = e.detail || null;
    rendreFiches();
  });

  /* La langue change : la barre, les commandes, la collection et les
     fiches portent toutes des phrases écrites en JS — `applyI18n` ne
     peut rien pour elles, puisqu'elles n'ont pas de `data-i18n`. */
  document.addEventListener('cyq:lang', function () {
    rendreBarre();
    poserChrome();
    rendreGalerie();
    rendreFiches();
    if (motVide && !motVide.hidden) motVide.textContent = t('ov.allRemoved');
  });

  appliquer();
  rendreBarre();
  rendreFiches();
})();
