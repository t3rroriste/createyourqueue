/* =========================================================================
   CreateYourQueue — configuration du site
   C'est le SEUL fichier à modifier avant la mise en ligne.
   ========================================================================= */

window.CYQ_CONFIG = {

  /* --- Les deux adresses du site ---------------------------------------
     La vitrine et l'application sont sur deux domaines :

       SITE_ORIGIN   cyqbot.eu            index, modules, guide
       APP_ORIGIN    dashboard.cyqbot.eu  login, welcome, servers, dashboard

     Pourquoi ces deux lignes existent : pour le navigateur, un
     sous-domaine est un AUTRE site. Un lien relatif « login.html » écrit
     sur la vitrine chercherait cyqbot.eu/login.html, qui n'y est plus.
     app.js lit ces deux valeurs et récrit les liens marqués data-site et
     data-app, ainsi que tous les « Se connecter ».

     Laisse les DEUX chaînes vides pour revenir à un seul domaine, ou pour
     travailler en local : les liens redeviennent relatifs, et tout
     fonctionne comme avant. Pas de barre oblique à la fin.                */
  SITE_ORIGIN: 'https://cyqbot.eu',
  APP_ORIGIN:  'https://dashboard.cyqbot.eu',

  /* --- Discord ---------------------------------------------------------
     CLIENT_ID : l'identifiant de ton application, dans le portail
     développeur Discord → ton application → General Information.
     Ce n'est PAS un secret : il apparaît de toute façon dans l'URL OAuth.
     Ne mets jamais le CLIENT_SECRET ici, il n'a rien à faire côté site.   */
  CLIENT_ID: '1521589617521070240',

  /* L'adresse de retour n'est plus construite ici : c'est le serveur qui
     la connaît, et lui seul. Il l'affiche au démarrage, c'est cette
     valeur-là qu'il faut déclarer dans le portail Discord → OAuth2 →
     Redirects. Laissée ici pour les pages servies sans API.               */
  REDIRECT_URI: window.location.origin + '/api/auth/callback',

  /* L'adresse de retour du flux SANS back-end, celui qu'utilise login.html.
     Discord renvoie le jeton dans le fragment de cette URL, et exige
     qu'elle soit déclarée AU CARACTÈRE PRÈS dans le portail développeur →
     OAuth2 → Redirects. Avec www ici, il faut www là-bas.

     Depuis la scission, login.html n'existe QUE sur le sous-domaine : la
     valeur se déduit donc d'APP_ORIGIN, et c'est
     « https://dashboard.cyqbot.eu/login.html » qui doit être déclarée.
     Une redirection 301 ne suffit pas : Discord compare l'URL telle
     quelle, avant toute redirection.

     Laissée VIDE, elle est calculée en bas de ce fichier :
     APP_ORIGIN + '/login.html', ou l'origine courante si APP_ORIGIN est
     vide. Mets une valeur ici seulement pour forcer autre chose.          */
  OAUTH_REDIRECT_URI: '',

  /* Permissions demandées à l'installation du bot (somme des bits Discord).

     Cette valeur DOIT rester identique à `invite_permissions` dans
     api/secrets.php, sur le serveur : c'est l'API qui construit le lien
     d'invitation réel, celle-ci ne sert qu'au site sans back-end.

     Onze droits, et chacun répond à une chose que le bot fait :
        4  gérer les salons        créer et supprimer les vocaux d'équipe
        6  ajouter des réactions   les votes se font en réaction
       10  voir les salons
       11  envoyer des messages
       13  gérer les messages      nettoyage automatique, anti-lien
       14  intégrer des liens      les annonces du bot sont des embeds
       16  lire l'historique       retrouver ses propres messages
       20  se connecter            entrer dans le vocal d'attente
       24  déplacer des membres    répartir les joueurs en équipes
       26  changer de pseudo       porter un surnom propre à ce serveur
       28  gérer les rôles
       40  modérer les membres     anti-raid, par exclusion temporaire

     Volontairement ABSENTS : expulser et bannir, trop lourds pour un bot
     de file d'attente — l'anti-raid se contente de l'exclusion temporaire ;
     mentionner @everyone, jamais nécessaire pour poster ; parler, le bot
     n'émet aucun son.

     L'ancienne valeur, 1099780064336, n'accordait en réalité que cinq
     droits : ni écrire, ni se connecter, ni déplacer. Son commentaire
     affirmait le contraire, ce qui a masqué le problème longtemps.       */
  INVITE_PERMISSIONS: '1099865091152',

  /* --- Back-end --------------------------------------------------------
     URL de ton API. Laisse la chaîne vide tant que tu n'en as pas :
     le site fonctionne, se navigue, et affiche ses états vides réels
     au lieu d'inventer des données.
     Exemple : 'https://api.cyq.gg'                                        */
  /* L'API vit dans le dossier `api/` du panneau, et elle est écrite en PHP
     — le seul langage que l'hébergement mutualisé LWS sache exécuter. Elle
     est donc sur LA MÊME ORIGINE que les pages du panneau : pas de CORS,
     pas de cookie tiers, rien à héberger ailleurs.

     L'adresse est écrite en entier plutôt qu'en '/api' parce que ce fichier
     sert aussi la vitrine, où /api n'existe pas.

     Remets cette chaîne à VIDE pour revenir au site sans back-end : les
     écrans affichent alors leurs états vides au lieu d'erreurs.           */
  API_BASE: 'https://dashboard.cyqbot.eu/api',

  /* --- Divers ---------------------------------------------------------- */
  SITE_NAME: 'CreateYourQueue',
  DOCS_URL: 'guide',
  COMMANDS_URL: '#',
  /* Invitation vers ton serveur Discord d'entraide. Alimente le lien
     « Support » de la navigation et celui du pied de page.
     Exemple : 'https://discord.gg/xxxxxxx'                                */
  SUPPORT_URL: '#',
  STATUS_URL: '#',
  PRIVACY_URL: '#',

  /* Langue de repli si celle du navigateur n'est pas gérée. */
  DEFAULT_LANG: 'fr',

  /* Thème au premier chargement : 'dark' ou 'light'. */
  DEFAULT_THEME: 'dark'
};

/* --- Réglage depuis la page ---------------------------------------------
   En ligne, on n'a pas toujours la main sur ce fichier. Le bandeau de
   l'accueil enregistre le CLIENT_ID et l'API dans le navigateur, et c'est
   ici qu'ils sont relus : avant app.js, qui lit la config une seule fois.

   Deux valeurs seulement, et aucune des deux n'est un secret. Le
   CLIENT_SECRET n'a rien à faire côté site, il n'est pas accepté ici.
   Ce qui est écrit dans ce fichier reste la valeur par défaut : effacer
   le réglage local suffit à y revenir.                                    */
(function (cfg) {
  try {
    var local = JSON.parse(localStorage.getItem('cyq:config') || '{}');
    ['CLIENT_ID', 'API_BASE'].forEach(function (k) {
      if (typeof local[k] === 'string' && local[k]) cfg[k] = local[k];
    });
  } catch (e) {
    /* stockage refusé (navigation privée, cookies bloqués) : on garde le fichier */
  }

  /* Une origine ne porte jamais de barre oblique finale : sans ce nettoyage,
     « https://dashboard.cyqbot.eu/ » + '/login.html' donnerait une adresse à
     double barre, que Discord refuserait. */
  ['SITE_ORIGIN', 'APP_ORIGIN'].forEach(function (k) {
    cfg[k] = (cfg[k] || '').replace(/\/+$/, '');
  });

  /* L'adresse de retour OAuth suit le sous-domaine, puisque login.html n'est
     que là. Déclarée vide dans le fichier, elle se calcule ici.

     Hors des deux domaines (dossier local, serveur de test, adresse IP),
     c'est l'origine courante qui sert : sans cela, un essai en local
     renverrait Discord vers le site en production.                        */
  if (!cfg.OAUTH_REDIRECT_URI) {
    var ici = window.location.origin;
    var surLesVraisDomaines = (cfg.SITE_ORIGIN && ici === cfg.SITE_ORIGIN) ||
                              (cfg.APP_ORIGIN  && ici === cfg.APP_ORIGIN);
    cfg.OAUTH_REDIRECT_URI =
      (surLesVraisDomaines ? cfg.APP_ORIGIN : ici) + '/login.html';
  }
})(window.CYQ_CONFIG);
