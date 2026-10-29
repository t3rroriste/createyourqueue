<?php
/* Modèle. À copier en « etat.secrets.php » SUR LE SERVEUR du sous-domaine
 * status.cyqbot.eu, jamais dans le dépôt.
 *
 * etat.secrets.php n'est PAS dans la liste d'envoi : il se dépose à la
 * main et ne part jamais d'ici. C'est voulu — une publication ne doit pas
 * pouvoir écraser la clé du serveur, ni l'emporter par erreur.
 *
 * DEUX valeurs, et pas une de plus. Ce fichier n'a rien à faire du
 * CLIENT_SECRET Discord ni du jeton du bot : la page d'état ne connaît
 * personne et ne fait qu'une chose, demander au bot comment il va. Lui
 * confier les autres secrets, ce serait les recopier sur un troisième
 * serveur sans aucune raison.
 */
return [
    /* L'adresse de l'API que le bot ouvre (cogs/dashboard_api.py), vue de
       l'extérieur, port compris. La même valeur que `bot_api_base` dans
       api/secrets.php du panneau.

       Vide : la page affiche « mesure non configurée » et le dit
       franchement, au lieu de laisser croire que tout va bien. */
    'bot_api_base' => '',          // ex. http://node2.adky.net:25117

    /* La DASHBOARD_API_KEY du bot, recopiée à l'identique. Elle part en
       en-tête X-API-Key. C'en est une vraie : elle autorise à ouvrir des
       queues sur n'importe quel serveur. Elle ne quitte jamais ce
       fichier — etat.php ne la rend dans aucune réponse. */
    'bot_api_key'  => '',
];
