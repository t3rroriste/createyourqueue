<?php
/* Modèle. À copier en « secrets.php » SUR LE SERVEUR, jamais dans le dépôt.
 *
 * Le CLIENT_SECRET est un vrai secret : il ne doit exister que sur la
 * machine qui sert le site. Ce fichier-ci ne contient que des trous.
 *
 * secrets.php n'est PAS dans la liste d'envoi : il se dépose à la main et
 * ne part jamais d'ici. C'est voulu — un déploiement ne doit pas pouvoir
 * écraser les jetons du serveur, ni les emporter par erreur.
 */
return [
    // Portail développeur Discord -> ton application -> General Information
    'client_id'     => '1521589617521070240',

    // Portail -> OAuth2 -> Client Secret. À régénérer s'il a fuité.
    'client_secret' => 'A_REMPLIR',

    // Portail -> Bot -> Token. Techniquement facultatif, en pratique
    // nécessaire : sans lui les menus de salons et de rôles restent vides,
    // la présence du bot ne peut pas être demandée à Discord, et son
    // surnom par serveur ne peut pas être écrit.
    'bot_token'     => '',

    // Doit rester aligné sur INVITE_PERMISSIONS dans assets/js/config.js.
    // Douze droits : gérer salons et rôles, voir, écrire, gérer les
    // messages, intégrer des liens, lire l'historique, réagir, se
    // connecter en vocal, déplacer des membres, modérer, et changer son
    // propre pseudo — ce dernier pour porter un surnom propre à chaque
    // serveur.
    // Sans « se connecter » ni « déplacer des membres », le bot ne peut
    // pas répartir les joueurs en équipes — c'est pourtant son métier.
    'invite_permissions' => '1099865091152',

    // ------------------------------------------------------------------
    // L'API que le bot ouvre pour ce panneau (cogs/dashboard_api.py).
    // Elle sert aux ACTIONS qui vivent dans le bot — ouvrir une queue —
    // par opposition aux réglages, qui vivent ici.
    //
    // L'adresse est celle du conteneur vue de l'extérieur, port compris :
    // le site est chez LWS, le bot chez AdKyNet, ils ne partagent pas
    // localhost. Côté bot, DASHBOARD_API_PORT doit valoir ce même port,
    // et DASHBOARD_API_HOST rester 0.0.0.0.
    //
    // Vide : le bouton « Ouvrir la queue » répond que rien n'a été
    // ouvert, et c'est tout — le reste du panneau ne change pas.
    'bot_api_base' => '',          // ex. http://node2.adky.net:25117

    // La DASHBOARD_API_KEY du bot, recopiée à l'identique. Elle part en
    // en-tête X-API-Key à chaque appel. C'en est un vrai : elle autorise à
    // ouvrir des queues sur n'importe quel serveur.
    'bot_api_key'  => '',
];
