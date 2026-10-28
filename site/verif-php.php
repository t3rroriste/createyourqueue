<?php
/* Vérification de ce que l'hébergement LWS sait faire.
 *
 * Quatre questions, une réponse : la version de PHP, la présence de cURL,
 * le droit d'écrire dans le dossier, et surtout la possibilité d'appeler
 * Discord depuis le serveur. Sans cette dernière, aucune API de connexion
 * ne peut tourner ici, quel que soit le langage.
 *
 * Fichier TEMPORAIRE : à supprimer une fois la réponse obtenue.
 */

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$r = [
    'php'      => PHP_VERSION,
    'curl'     => function_exists('curl_init'),
    'json'     => function_exists('json_encode'),
    'sessions' => function_exists('session_start'),
    'ecriture' => is_writable(__DIR__),
];

/* L'appel sortant. On vise une adresse publique de Discord qui ne demande
   aucune authentification : si elle répond, l'échange du code OAuth
   fonctionnera aussi. */
if ($r['curl']) {
    $c = curl_init('https://discord.com/api/v10/gateway');
    curl_setopt_array($c, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 8,
        CURLOPT_USERAGENT      => 'CreateYourQueue/verif',
    ]);
    $corps = curl_exec($c);
    if ($corps === false) {
        $r['appel_discord'] = 'ECHEC : ' . curl_error($c);
    } else {
        $r['appel_discord'] = 'OK, code HTTP ' . curl_getinfo($c, CURLINFO_HTTP_CODE);
        $r['reponse_discord'] = substr($corps, 0, 120);
    }
    curl_close($c);
} else {
    $r['appel_discord'] = 'IMPOSSIBLE : cURL absent';
}

echo json_encode($r, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
