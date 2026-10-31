/* =========================================================================
   LE THÈME, POSÉ AVANT LA PREMIÈRE PEINTURE
   =========================================================================
   Depuis que « Système » est le choix par défaut, la page ne peut plus
   attendre app.js pour savoir de quelle couleur elle est. app.js est
   chargé en fin de `body` : le navigateur a déjà peint l'écran en sombre
   — les jetons de `:root` — et quelqu'un dont le système est en clair
   voyait un éclair noir puis la bascule. Sur une page longue, cet éclair
   dure le temps du téléchargement des polices.

   Ce fichier est donc chargé dans le `<head>`, AVANT les feuilles de
   style, et SANS `defer` ni `async` : il doit s'exécuter pendant que le
   navigateur lit encore l'en-tête, c'est-à-dire avant d'avoir rien
   dessiné. C'est le seul script du site dans ce cas, et c'est la raison
   pour laquelle il est si court — tout ce qu'on écrit ici retarde
   l'affichage de toutes les pages.

   IL NE CONNAÎT PAS config.js, qui est chargé en fin de page. La règle
   de repli est donc écrite deux fois : ici, et dans `DEFAULT_THEME`.
   Elles doivent dire la même chose, et elles le disent : pas de choix
   enregistré → on suit le système.

   Il ne lit RIEN d'autre que ce qu'il pose. app.js reprend la main
   ensuite avec la même valeur, et c'est lui qui gère le reste : les trois
   boutons du menu, le suivi du système en cours de route, le balayage.
   ========================================================================= */
(function (h) {
  'use strict';

  var choix = null;
  try { choix = localStorage.getItem('cyq.theme'); }
  catch (e) { /* navigation privée, stockage bloqué : on suivra le système */ }

  /* Une valeur inconnue — un réglage d'une version précédente, un
     stockage abîmé — vaut « pas de choix », et non « sombre » : la
     réponse la moins fausse est celle du système. */
  if (choix !== 'light' && choix !== 'dark') choix = 'system';

  var affiche = choix;
  if (choix === 'system') {
    affiche = (window.matchMedia &&
               window.matchMedia('(prefers-color-scheme: dark)').matches)
      ? 'dark' : 'light';
  }
  h.setAttribute('data-theme', affiche);
})(document.documentElement);
