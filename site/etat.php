<?php
/* =========================================================================
 * status.cyqbot.eu — la mesure, côté serveur.
 *
 * Pourquoi un PHP et pas un appel direct depuis la page : joindre l'API du
 * bot demande la clé DASHBOARD_API_KEY en en-tête X-API-Key. Une clé posée
 * dans du JavaScript est une clé publique, et celle-là autorise à ouvrir
 * des queues sur n'importe quel serveur. Elle reste donc ici, dans un
 * fichier que personne ne télécharge, et la page ne voit que le résultat.
 *
 * Ce fichier ne rend JAMAIS l'adresse du bot ni sa clé. Pas même en cas
 * d'erreur : un message de panne détaillé est une carte du réseau.
 *
 * Il vit à la racine du sous-domaine, à côté de la page qui l'appelle —
 * comme contact.php vit à côté de support.html, et pour la même raison :
 * l'API du panneau ne pose aucun en-tête CORS, un appel d'une origine à
 * l'autre serait refusé par le navigateur.
 * ========================================================================= */

declare(strict_types=1);

/* Le cache est OBLIGATOIRE, pas une optimisation. Sans lui, chaque
   visiteur — et chaque rafraîchissement automatique de chaque onglet
   resté ouvert — déclenche un appel au bot. Une page d'état qui attire du
   monde quand ça va mal deviendrait elle-même la panne. Vingt secondes :
   moins que les trente du rafraîchissement de la page, donc une page qui
   se recharge toute seule voit bien une mesure neuve à chaque fois. */
const TTL = 20;

/* Au-delà, on considère que le bot ne répond pas. Quatre secondes : assez
   pour une liaison lente, assez peu pour que la page ne reste pas en
   attente. PHP, lui, a souvent trente secondes — on ne les attend pas. */
const DELAI = 4;

/* Les MÊMES seuils que bot/cogs/statuspanel.py : _quality() dit
   « Excellent » jusqu'à 150 ms et « Correct » jusqu'à 400. Le panneau
   Discord et cette page lisent la même mesure ; ils ne doivent pas en
   tirer deux verdicts différents. Changer l'un oblige à changer l'autre. */
const SEUIL_BON = 150;
const SEUIL_OK  = 400;

const CACHE = __DIR__ . '/etat-cache/etat.json';

header('Content-Type: application/json; charset=utf-8');
/* La réponse ne doit jamais être gardée par le navigateur : c'est une
   mesure horodatée. Le cache qui compte est celui du serveur, au-dessus. */
header('Cache-Control: no-store, max-age=0');

/* ----------------------------------------------------------- le cache ---- */

$garde = @file_get_contents(CACHE);
if ($garde !== false) {
    $vu = json_decode($garde, true);
    if (is_array($vu) && isset($vu['checked_at'])
        && (time() - (int)$vu['checked_at']) < TTL) {
        $vu['cached'] = true;
        echo json_encode($vu);
        exit;
    }
}

/* ---------------------------------------------------------- la mesure ---- */

$conf = @include __DIR__ . '/etat.secrets.php';
$base = is_array($conf) ? rtrim((string)($conf['bot_api_base'] ?? ''), '/') : '';
$cle  = is_array($conf) ? (string)($conf['bot_api_key'] ?? '') : '';

$etat = [
    'verdict'        => 'unset',
    'latency_ms'     => null,
    'api_ms'         => null,
    'guilds'         => null,
    'active_queues'  => null,
    'uptime_seconds' => null,
    'checked_at'     => time(),
    'ttl'            => TTL,
    'cached'         => false,
];

if ($base !== '') {
    /* Le temps mesuré ici est celui que met le site à obtenir une réponse
       du bot : c'est la liaison LWS → AdKyNet, et c'est bien ce que vit
       un visiteur du panneau. La latence Discord, elle, vient du bot et
       n'est pas mesurable d'ici. Deux chiffres, deux choses. */
    $depart = microtime(true);
    $c = curl_init($base . '/api/health');
    curl_setopt_array($c, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => DELAI,
        CURLOPT_CONNECTTIMEOUT => DELAI,
        CURLOPT_HTTPHEADER     => ['Accept: application/json', 'X-API-Key: ' . $cle],
        CURLOPT_USERAGENT      => 'CreateYourQueue (https://status.cyqbot.eu)',
    ]);
    $brut = curl_exec($c);
    $code = (int)curl_getinfo($c, CURLINFO_HTTP_CODE);
    curl_close($c);
    $etat['api_ms'] = (int)round((microtime(true) - $depart) * 1000);

    $rep = ($brut === false) ? null : json_decode((string)$brut, true);
    if ($code === 200 && is_array($rep) && ($rep['status'] ?? '') === 'ok') {
        $etat['guilds']         = isset($rep['guilds']) ? (int)$rep['guilds'] : null;
        $etat['active_queues']  = isset($rep['active_queues']) ? (int)$rep['active_queues'] : null;
        $etat['uptime_seconds'] = isset($rep['uptime_seconds']) ? (int)$rep['uptime_seconds'] : null;

        /* Le bot rend 0 tant que le premier battement de cœur Discord
           n'est pas revenu — c'est la garde de dashboard_api.py, et 0
           n'est pas une latence. On ne la montre donc pas, et le verdict
           se contente de « ça répond » : afficher « Excellent » sur une
           mesure absente serait exactement ce qu'on cherche à éviter. */
        $ms = isset($rep['latency_ms']) ? (int)$rep['latency_ms'] : 0;
        if ($ms > 0) {
            $etat['latency_ms'] = $ms;
            $etat['verdict'] = $ms <= SEUIL_BON ? 'good' : ($ms <= SEUIL_OK ? 'ok' : 'slow');
        } else {
            $etat['verdict'] = 'ok';
        }
    } else {
        /* Injoignable, refusé, ou une réponse qu'on ne comprend pas : du
           point de vue d'un visiteur, c'est la même chose. Le code HTTP
           reste dans les logs d'Apache et ne part pas sur la page. */
        $etat['verdict'] = 'down';
    }
}

/* L'écriture peut échouer — dossier non inscriptible sur l'hébergement.
   Ce n'est pas une raison de ne pas répondre : on sert la mesure, et le
   prochain visiteur en refera une. */
@file_put_contents(CACHE, json_encode($etat), LOCK_EX);

echo json_encode($etat);
