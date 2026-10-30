<?php
/* =========================================================================
 * API du panneau CreateYourQueue — version PHP, pour l'hébergement LWS.
 *
 * Pourquoi PHP et pas le server.py du dépôt : l'hébergement mutualisé LWS
 * n'exécute que du PHP. Un programme Python y est impossible, et une API sur
 * une autre machine aurait voulu un sous-domaine, un certificat, du CORS et
 * un cookie tiers. Ici, l'API vit DANS le dossier du panneau : même origine,
 * donc rien de tout cela.
 *
 * Elle fait exactement ce que fait server.py — qui reste, lui, l'outil de
 * développement local :
 *
 *   GET   /api/auth/login              départ vers Discord, avec state
 *   GET   /api/auth/callback           retour, échange du code, session
 *   POST  /api/auth/logout             fin de session
 *   GET   /api/me                      le compte connecté
 *   GET   /api/guilds                  les serveurs qu'on peut gérer
 *   GET   /api/guilds/{id}             un serveur, ses salons, ses rôles
 *   PATCH /api/guilds/{id}/settings    enregistre des réglages
 *
 * Le CLIENT_SECRET n'est pas dans ce fichier : il est lu dans secrets.php,
 * qui n'est pas versionné et se dépose à la main sur le serveur.
 * ========================================================================= */

declare(strict_types=1);

/* L'hebergement peut encore servir du PHP 7.4 : str_starts_with() n'existe
   qu'a partir de 8.0. Deux lignes evitent une panne qu'on ne verrait qu'en
   production, et seulement sur certaines offres. */
if (!function_exists('str_starts_with')) {
    function str_starts_with(string $sujet, string $debut): bool
    {
        return $debut === '' || strncmp($sujet, $debut, strlen($debut)) === 0;
    }
}

const API_DISCORD   = 'https://discord.com/api/v10';
const MANAGE_GUILD  = 0x20;          // le bit « Gérer le serveur »
const DUREE_SESSION = 7 * 24 * 3600;

// ------------------------------- les secrets --------------------------------

$conf = @include __DIR__ . '/secrets.php';
if (!is_array($conf)) {
    // Pas de secrets : on le dit proprement, sans détail exploitable.
    repondre(500, ['error' => 'NOT_CONFIGURED']);
}
$CLIENT_ID     = (string)($conf['client_id'] ?? '');
$CLIENT_SECRET = (string)($conf['client_secret'] ?? '');
$BOT_TOKEN     = (string)($conf['bot_token'] ?? '');

/* L'API que le bot ouvre pour ce panneau (cogs/dashboard_api.py). Elle sert
   aux actions qui vivent DANS le bot — ouvrir une queue — par opposition aux
   réglages, qui vivent ici. Vide : la route répond 503 et le panneau le dit,
   plutôt que de faire semblant. */
$BOT_API_BASE = rtrim((string)($conf['bot_api_base'] ?? ''), '/');
$BOT_API_KEY  = (string)($conf['bot_api_key'] ?? '');

// --------------------------------- réponses ---------------------------------

function repondre(int $code, $donnees = null): void
{
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('X-Content-Type-Options: nosniff');
    // Une réponse d'API ne se met jamais en cache : elle dépend de la session.
    header('Cache-Control: no-store');
    if ($donnees !== null) {
        echo json_encode($donnees, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    }
    exit;
}

function rediriger(string $vers): void
{
    header('Location: ' . $vers, true, 302);
    exit;
}

/* Où vit le panneau, vu du navigateur. L'API est dans son dossier `api/`,
   donc il suffit de remonter d'un cran — et ça marche quel que soit le
   domaine, sans rien écrire en dur. */
function base_panneau(): string
{
    $racine = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? '/api/index.php'), '/');  // /api
    $racine = rtrim(dirname($racine), '/');                                      // /
    $hote   = $_SERVER['HTTP_HOST'] ?? 'dashboard.cyqbot.eu';
    return 'https://' . $hote . ($racine === '' ? '' : $racine) . '/';
}

function url_retour(): string
{
    return rtrim(base_panneau(), '/') . '/api/auth/callback';
}

// --------------------------------- session ----------------------------------

/* Les sessions natives de PHP : le jeton d'accès reste sur le serveur, et le
   navigateur ne reçoit qu'un identifiant opaque. `Secure` et `HttpOnly` vont
   de soi ; `SameSite=Lax` suffit puisque l'API et la page sont sur la même
   origine. */
function demarrer_session(): void
{
    if (session_status() === PHP_SESSION_ACTIVE) {
        return;
    }
    session_set_cookie_params([
        'lifetime' => DUREE_SESSION,
        'path'     => '/',
        'secure'   => true,
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
    session_name('cyq_sid');
    session_start();
}

function session_ouverte(): ?array
{
    demarrer_session();
    $s = $_SESSION['cyq'] ?? null;
    return is_array($s) && !empty($s['access_token']) ? $s : null;
}

// -------------------------------- Discord -----------------------------------

/* Un seul endroit appelle Discord. `$type` vaut « Bearer » pour le jeton de
   la personne connectée, « Bot » pour celui du bot — les salons et les rôles
   ne sont lisibles qu'avec le second. */
function appel_discord(string $chemin, string $jeton, string $type = 'Bearer'): array
{
    $c = curl_init(API_DISCORD . $chemin);
    curl_setopt_array($c, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
        CURLOPT_HTTPHEADER     => [
            'Authorization: ' . $type . ' ' . $jeton,
            'Accept: application/json',
        ],
        CURLOPT_USERAGENT      => 'CreateYourQueue (https://cyqbot.eu)',
    ]);
    $corps = curl_exec($c);
    $code  = (int)curl_getinfo($c, CURLINFO_HTTP_CODE);
    $err   = curl_error($c);
    curl_close($c);

    if ($corps === false) {
        throw new RuntimeException('curl: ' . $err, 0);
    }
    if ($code >= 400) {
        throw new RuntimeException('discord', $code);
    }
    $json = json_decode((string)$corps, true);
    return is_array($json) ? $json : [];
}

/* Écrire sur Discord, pas seulement lire. Une fonction à part de
   `appel_discord` parce que les enjeux ne sont pas les mêmes : celle-ci
   modifie, donc elle ne doit JAMAIS lever. L'appelant enregistre ses
   autres réglages quoi qu'il arrive ; un surnom refusé par Discord — droit
   manquant, nom interdit, limite de débit — ne doit pas faire perdre le
   reste du lot.

   Renvoie vrai si Discord a accepté. */
function appel_discord_patch(string $chemin, array $donnees, string $jeton): bool
{
    $c = curl_init(API_DISCORD . $chemin);
    curl_setopt_array($c, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_CUSTOMREQUEST  => 'PATCH',
        CURLOPT_POSTFIELDS     => json_encode($donnees, JSON_UNESCAPED_UNICODE),
        CURLOPT_HTTPHEADER     => [
            'Authorization: Bot ' . $jeton,
            'Content-Type: application/json',
            'Accept: application/json',
        ],
        CURLOPT_USERAGENT      => 'CreateYourQueue (https://cyqbot.eu)',
    ]);
    curl_exec($c);
    $code = (int)curl_getinfo($c, CURLINFO_HTTP_CODE);
    curl_close($c);
    return $code >= 200 && $code < 300;
}

function peut_gerer(array $g): bool
{
    if (!empty($g['owner'])) {
        return true;
    }
    // Les permissions arrivent en chaîne : elles dépassent la taille d'un
    // entier sur les plateformes 32 bits, d'où la comparaison en chaîne.
    $p = $g['permissions'] ?? '0';
    return (((int)$p) & MANAGE_GUILD) === MANAGE_GUILD;
}

function url_icone(string $gid, ?string $h, int $taille = 64): ?string
{
    if (!$h) {
        return null;
    }
    $ext = str_starts_with($h, 'a_') ? 'gif' : 'png';
    return "https://cdn.discordapp.com/icons/$gid/$h.$ext?size=$taille";
}

// ------------------------------ les réglages --------------------------------

/* Un fichier JSON, pas une base — assez pour commencer, et remplaçable sans
   toucher au reste : seules ces deux fonctions y touchent. Le dossier `data`
   est interdit d'accès par son propre .htaccess ; sans lui, les réglages
   seraient lisibles par n'importe qui à l'adresse /api/data/guilds.json. */
function fichier_reglages(): string
{
    $dossier = __DIR__ . '/data';
    if (!is_dir($dossier)) {
        @mkdir($dossier, 0750, true);
    }
    return $dossier . '/guilds.json';
}

function lire_reglages(): array
{
    $f = fichier_reglages();
    if (!is_file($f)) {
        return [];
    }
    $brut = @file_get_contents($f);
    $json = json_decode((string)$brut, true);
    return is_array($json) ? $json : [];
}

/* Lecture-modification-écriture sous verrou : deux onglets qui enregistrent
   en même temps écraseraient sinon l'un les réglages de l'autre. */
function modifier_reglages(callable $modif): void
{
    $f = fichier_reglages();
    $fp = @fopen($f, 'c+');
    if (!$fp) {
        repondre(500, ['error' => 'STORAGE']);
    }
    try {
        flock($fp, LOCK_EX);
        $brut = stream_get_contents($fp);
        $tout = json_decode((string)$brut, true);
        if (!is_array($tout)) {
            $tout = [];
        }
        $tout = $modif($tout);
        $texte = json_encode($tout, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        ftruncate($fp, 0);
        rewind($fp);
        fwrite($fp, (string)$texte);
        fflush($fp);
    } finally {
        flock($fp, LOCK_UN);
        fclose($fp);
    }
}

// --------------------------------- routage ----------------------------------

$methode = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$chemin  = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';

/* On ne garde que ce qui suit « /api ». Le dossier peut être ailleurs qu'à la
   racine du domaine, donc on ne suppose pas sa position. */
$prefixe = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? '/api/index.php'), '/');
if ($prefixe !== '' && str_starts_with($chemin, $prefixe)) {
    $chemin = substr($chemin, strlen($prefixe));
}
$chemin = '/' . ltrim($chemin, '/');

// ------------------------------- connexion ----------------------------------

if ($chemin === '/auth/login' && $methode === 'GET') {
    if (!$CLIENT_ID) {
        repondre(500, ['error' => 'NOT_CONFIGURED']);
    }
    demarrer_session();
    /* Le `state` est tiré au sort ICI et retrouvé au retour : sans lui,
       n'importe quel site pourrait déclencher la connexion à votre place. */
    $state = bin2hex(random_bytes(16));
    $_SESSION['cyq_state'] = $state;

    /* Un seul écran pour les deux : `identify guilds` ouvre la session, et
       `bot applications.commands` fait apparaître le choix du serveur où
       ajouter le bot. Discord renvoie alors guild_id en plus du code. */
    $q = http_build_query([
        'client_id'     => $CLIENT_ID,
        'response_type' => 'code',
        'redirect_uri'  => url_retour(),
        'scope'         => 'identify guilds bot applications.commands',
        'permissions'   => (string)($conf['invite_permissions'] ?? '1099865091152'),
        'state'         => $state,
    ]);
    rediriger('https://discord.com/oauth2/authorize?' . $q);
}

if ($chemin === '/auth/callback' && $methode === 'GET') {
    demarrer_session();
    $attendu = (string)($_SESSION['cyq_state'] ?? '');
    unset($_SESSION['cyq_state']);
    $panneau = base_panneau();

    if (isset($_GET['error'])) {
        rediriger($panneau . 'servers.html?auth=refus');
    }
    $code  = (string)($_GET['code'] ?? '');
    $state = (string)($_GET['state'] ?? '');
    if ($code === '') {
        rediriger($panneau . 'servers.html?auth=incomplet');
    }
    // Comparaison à temps constant : une comparaison naïve fuit la valeur.
    if ($attendu === '' || !hash_equals($attendu, $state)) {
        rediriger($panneau . 'servers.html?auth=state');
    }

    // --- échange du code contre un jeton ---
    $c = curl_init(API_DISCORD . '/oauth2/token');
    curl_setopt_array($c, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => http_build_query([
            'client_id'     => $CLIENT_ID,
            'client_secret' => $CLIENT_SECRET,
            'grant_type'    => 'authorization_code',
            'code'          => $code,
            'redirect_uri'  => url_retour(),
        ]),
        CURLOPT_HTTPHEADER     => ['Content-Type: application/x-www-form-urlencoded'],
    ]);
    $corps = curl_exec($c);
    $http  = (int)curl_getinfo($c, CURLINFO_HTTP_CODE);
    curl_close($c);

    if ($corps === false || $http >= 400) {
        // Le corps peut contenir des éléments du secret : on n'en garde rien.
        rediriger($panneau . 'servers.html?auth=echange');
    }
    $jeton = json_decode((string)$corps, true);
    if (!is_array($jeton) || empty($jeton['access_token'])) {
        rediriger($panneau . 'servers.html?auth=echange');
    }

    try {
        $moi = appel_discord('/users/@me', $jeton['access_token']);
    } catch (Throwable $e) {
        rediriger($panneau . 'servers.html?auth=erreur');
    }

    session_regenerate_id(true);   // l'identifiant de session change à la connexion
    $_SESSION['cyq'] = [
        'access_token' => $jeton['access_token'],
        'user_id'      => (string)($moi['id'] ?? ''),
        'user_name'    => (string)($moi['global_name'] ?? $moi['username'] ?? ''),
        'username'     => (string)($moi['username'] ?? ''),
        'avatar_url'   => !empty($moi['avatar'])
            ? 'https://cdn.discordapp.com/avatars/' . $moi['id'] . '/' . $moi['avatar'] . '.png?size=64'
            : null,
    ];

    /* Avec le scope `bot`, Discord indique le serveur où le bot vient d'être
       ajouté. On le NOTE — c'est su, pas deviné — mais on n'y emmène pas
       d'office : on arrive toujours sur le choix du serveur.

       La version précédente ouvrait directement le panneau de ce serveur-là.
       C'est une supposition de trop : on se connecte le plus souvent pour
       régler un serveur DÉJÀ configuré, pas celui qu'on vient d'ajouter, et
       atterrir sans l'avoir demandé dans un panneau vide désoriente. Le
       choix du serveur coûte un clic et montre ce qu'on a. */
    $gid = (string)($_GET['guild_id'] ?? '');
    if ($gid !== '' && ctype_digit($gid)) {
        modifier_reglages(function (array $tout) use ($gid): array {
            $tout[$gid] = array_merge($tout[$gid] ?? [], ['botPresent' => true]);
            return $tout;
        });
    }
    rediriger($panneau . 'servers.html');
}

if ($chemin === '/auth/logout' && $methode === 'POST') {
    demarrer_session();
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $p = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $p['path'], $p['domain'], $p['secure'], $p['httponly']);
    }
    session_destroy();
    repondre(204);
}

// ---------------------------------- api -------------------------------------

$session = session_ouverte();
if (!$session) {
    repondre(401, ['error' => 'UNAUTHORIZED']);
}

if ($chemin === '/me' && $methode === 'GET') {
    repondre(200, [
        'id'        => $session['user_id'],
        'name'      => $session['user_name'],
        'username'  => $session['username'],
        'avatarUrl' => $session['avatar_url'],
    ]);
}

/* Les serveurs de la personne, filtrés sur « Gérer le serveur ». Discord est
   la seule source de vérité ici : on ne se fie jamais à ce que le navigateur
   affirme. */
function mes_guildes(array $session): array
{
    try {
        return appel_discord('/users/@me/guilds', $session['access_token']);
    } catch (RuntimeException $e) {
        if ($e->getCode() === 401) {
            repondre(401, ['error' => 'UNAUTHORIZED']);
        }
        if ($e->getCode() === 429) {
            repondre(429, ['error' => 'RATE']);
        }
        repondre(502, ['error' => 'DISCORD_UNAVAILABLE']);
    }
}

/* Les serveurs OÙ LE BOT SE TROUVE, demandés à Discord.

   Pourquoi ne pas se fier à l'enregistrement local : `botPresent` n'y est
   écrit qu'au retour OAuth portant `guild_id`, c'est-à-dire quand le bot a
   été ajouté DEPUIS ce panneau. Un bot invité autrement — un lien collé
   dans Discord, une invitation antérieure à ce site — n'y figure pas, et
   son serveur s'affichait « Bot absent » alors qu'il y était.

   Une seule requête couvre tous les serveurs. Interroger `/guilds/{id}` en
   ferait une par ligne de la liste, et Discord compte les requêtes.

   Renvoie null quand on NE SAIT PAS — pas de jeton de bot, ou Discord
   muet. L'appelant retombe alors sur l'enregistrement local, au lieu
   d'affirmer que le bot est absent de partout. */
function guildes_du_bot(string $botToken): ?array
{
    if ($botToken === '') {
        return null;
    }

    $cache = __DIR__ . '/data/bot-guilds.json';

    /* 60 s : exactement la durée que l'interface annonce déjà à qui vient
       d'inviter le bot. Sans ce cache, afficher la liste coûterait une
       requête de plus à chaque fois. */
    if (is_file($cache) && (time() - (int)@filemtime($cache)) < 60) {
        $v = json_decode((string)@file_get_contents($cache), true);
        if (is_array($v)) {
            return $v;
        }
    }

    $vues  = [];
    $apres = '';
    try {
        /* Discord renvoie 200 guildes au plus par page. Sans pagination, un
           bot présent sur davantage de serveurs perdrait les suivants — et
           ce sont les plus récemment rejoints, donc précisément ceux qu'on
           vient de configurer. Le plafond de 25 tours évite une boucle sans
           fin si l'API répond de travers. */
        for ($page = 0; $page < 25; $page++) {
            $url = '/users/@me/guilds?limit=200' . ($apres !== '' ? '&after=' . $apres : '');
            $lot = appel_discord($url, $botToken, 'Bot');
            if (!$lot) {
                break;
            }
            foreach ($lot as $g) {
                if (!empty($g['id'])) {
                    $vues[] = (string)$g['id'];
                }
            }
            if (count($lot) < 200) {
                break;
            }
            $apres = (string)($lot[count($lot) - 1]['id'] ?? '');
            if ($apres === '') {
                break;
            }
        }
    } catch (Throwable $e) {
        return null;
    }

    @file_put_contents($cache, json_encode($vues), LOCK_EX);
    return $vues;
}


/* ------------------------- le pont vers le bot ---------------------------
 * Jusqu'ici, le panneau écrivait ses réglages dans son propre fichier et le
 * bot lisait les siens : deux vérités pour un même serveur, et c'est la
 * sienne qui compte, puisque c'est lui qui publie les annonces et crée les
 * salons. Les réglages qu'il sait tenir passent donc chez lui.
 *
 * Il n'en tient toujours pas la totalité : les presets de queue restent
 * dans le fichier du site, faute de route côté bot. Les tables ci-dessous
 * disent exactement ce qui traverse — et `docs/INVENTAIRE-REGLAGES.md`
 * pourquoi le reste ne traverse pas.
 * ------------------------------------------------------------------------- */

/* Salons et rôles. À gauche la clé du panneau, à droite celle du bot. */
const PONT_RESSOURCES = [
    'channel.commands'      => 'channel_queue_command',
    'channel.announcements' => 'channel_queue_announcement',
    'channel.results'       => 'channel_queue_resultat',
    'channel.leaderboard'   => 'channel_queue_classement',
    'channel.waitingVoice'  => 'voice_queue_waiting',
    'role.organizer'        => 'role_staff',
    'role.queueNotify'      => 'role_queue_notif',
    /* Ces deux-là, le bot les lisait depuis toujours (le vocal d'attente
       verrouillé, le rôle du MVP hebdomadaire) et ne se réglaient que par
       /config : le panneau n'avait pas de champ pour eux. */
    'role.connexion'        => 'role_connexion',
    'role.mvpWeek'          => 'role_mvp_week',
    /* Les clans. Le bot tenait déjà ces trois ressources — l'assistant les
       pose, cogs/clan.py les lit — mais elles manquaient de cette table :
       le panneau avait trois champs qui n'arrivaient jamais jusqu'à lui. */
    'channel.clanCategory'  => 'category_clan',
    'role.clanLeader'       => 'role_clan_leader',
    'role.clanTransfer'     => 'role_clan_transfer',
];

/* Fonctions activées. Le bot les nomme autrement : `mvp` couvre tout le
   bloc match (capitaines, vote MVP, MMR), et `clan_notice` l'annonce des
   adhésions. */
const PONT_FONCTIONS = [
    'feature.leaderboard'   => 'leaderboard',
    'feature.match'         => 'mvp',
    'feature.clans'         => 'clans',
    'feature.joinAnnounce'  => 'clan_notice',
    'feature.statusPanel'   => 'status',
    'feature.queuePassword' => 'password',
];



/* Le MMR. Les points de défaite sont la seule valeur qui change de forme
   en traversant : le panneau les demande NÉGATIFS — « Valeur négative »,
   dit son libellé — là où le bot garde un nombre positif qu'il retranche.
   Le signe est donc retourné dans les deux sens, et nulle part ailleurs. */
const PONT_MMR = [
    'mmr.enabled'     => 'enabled',
    'mmr.start'       => 'start',
    'mmr.win'         => 'win',
    'mmr.loss'        => 'loss',
    'mmr.mvpBonus'    => 'mvp_bonus',
    'mmr.streakBonus' => 'streak_bonus',
    'mmr.captainVote' => 'captain_vote_seconds',
    'mmr.resultVote'  => 'mvp_vote_seconds',
];

/* L'anti-raid. Le bot le réglait déjà par /antiraid config, et le panneau
   avait ses propres champs qui n'allaient nulle part : on cochait, il
   disait « Enregistré », et le bot continuait avec ses anciens seuils.

   Deux choses du panneau ont disparu plutôt que d'être pontées, parce
   qu'elles ne correspondaient à rien :
   - son interrupteur anti-raid, alors que la détection est TOUJOURS active
     côté bot ;
   - deux de ses quatre actions (exclure temporairement, bannir), que le bot
     ne sait pas faire. Il ne connaît qu'une expulsion automatique pendant
     un lockdown, qui est maintenant un simple interrupteur. */
const PONT_SECURITE = [
    'security.raidThreshold'  => 'join_threshold',
    'security.raidWindow'     => 'join_interval',
    'security.raidAccountAge' => 'min_account_age_hours',
    'security.raidKick'       => 'auto_kick',
];

/* Les dix journaux, dans l'ordre de KINDS (bot/cogs/logs.py). Le panneau les
   nomme `log.<type>.enabled` et `log.<type>.channel` ; le bot les range dans
   un bloc `logs`. Rien ne les pontait : la section Logs du panneau écrivait
   dans le fichier du site et le bot n'en voyait jamais rien — on allumait
   « Modération », il disait « Enregistré », et aucun log n'arrivait. */
const PONT_JOURNAUX = [
    'vocal', 'message', 'queue', 'match', 'duel',
    'clan', 'commande', 'join', 'moderation', 'serveur',
];

/* La queue par défaut. Le bot range tout dans un seul objet `queue`, d'où
   cette table à part : ce ne sont ni des ressources, ni des fonctions. */
const PONT_QUEUE = [
    'queue.name'    => 'queue_name',
    'queue.type'    => 'type',
    'queue.time'    => 'heure',
    'queue.teams'   => 'num_teams',
    'queue.players' => 'max_players_per_team',
    'queue.embedColor' => 'embed_color',
    'queue.notifMessage' => 'notif_message',
];

/* La file programmée (/schedule côté Discord). `days` traverse en texte —
   « 0,5,6 » — parce que les réglages du panneau sont des chaînes : une
   liste y entrerait comme « Array ». Elle est refaite en tableau à
   l'écriture. */
const PONT_PROGRAMME = [
    'schedule.enabled'         => 'enabled',
    'schedule.time'            => 'time',
    'schedule.reminder'        => 'reminder',
    'schedule.reminderMinutes' => 'reminder_minutes',
    'schedule.preset'          => 'preset',
];

/* Les saisons (/season). `archive` n'y est pas : c'est le palmarès, il se
   lit et ne se réécrit pas depuis un formulaire. */
const PONT_SAISON = [
    'season.enabled'     => 'enabled',
    'season.resetDay'    => 'reset_day',
    'season.announce'    => 'announce',
    'season.keepHistory' => 'keep_history',
];

/* Les absences répétées. */
const PONT_ABSENCES = [
    'noshow.enabled'   => 'enabled',
    'noshow.threshold' => 'threshold',
    'noshow.banHours'  => 'ban_hours',
];

/* Les clés BOOLÉENNES de ces trois blocs. Sans cette liste, « 0 » partirait
   en `true` chez le bot : une chaîne non vide est vraie en PHP, et
   « anti-raid éteint » deviendrait « anti-raid allumé ». */
const PONT_BOOLEENS = [
    'enabled', 'reminder', 'announce', 'keep_history',
];

/* Les douze couleurs du panneau et le rond que le bot écrit pour chacune.
   C'est la même liste que COLOR_PALETTE côté bot, dans le même ordre : une
   équipe affichée en rouge dans le panneau doit sortir rouge dans
   l'annonce, pas « à peu près rouge ». */
const PONT_RONDS = [
    '#ed4245' => "\u{1F534}", '#3b88c3' => "\u{1F535}", '#78b159' => "\u{1F7E2}",
    '#fdcb58' => "\u{1F7E1}", '#aa8ed6' => "\u{1F7E3}", '#f4900c' => "\u{1F7E0}",
    '#e6e7e8' => "\u{26AA}",  '#31373d' => "\u{26AB}",  '#c1694f' => "\u{1F7E4}",
    '#f9a7c0' => "\u{1FA77}", '#9cdcf0' => "\u{1FA75}", '#3b5998' => "\u{1F7E6}",
];

/* Appelle l'API du bot. Rend [code HTTP, données]. Code 0 : injoignable —
   le site ne doit alors ni inventer ni enregistrer en douce. */
function appel_bot(string $methode, string $chemin, ?array $corps = null): array
{
    global $BOT_API_BASE, $BOT_API_KEY;
    if ($BOT_API_BASE === '') {
        return [0, []];
    }
    $entetes = ['Accept: application/json', 'X-API-Key: ' . $BOT_API_KEY];
    $options = [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 12,
        CURLOPT_CUSTOMREQUEST  => $methode,
        CURLOPT_USERAGENT      => 'CreateYourQueue (https://cyqbot.eu)',
    ];
    if ($corps !== null) {
        $options[CURLOPT_POSTFIELDS] = json_encode($corps);
        $entetes[] = 'Content-Type: application/json';
    }
    $options[CURLOPT_HTTPHEADER] = $entetes;

    $c = curl_init($BOT_API_BASE . $chemin);
    curl_setopt_array($c, $options);
    $brut = curl_exec($c);
    $code = (int)curl_getinfo($c, CURLINFO_HTTP_CODE);
    curl_close($c);

    if ($brut === false || $code === 0) {
        return [0, []];
    }
    $json = json_decode((string)$brut, true);
    return [$code, is_array($json) ? $json : []];
}

/* Les réglages du bot, traduits dans les clés du panneau. Tableau vide s'il
   ne répond pas : l'appelant garde alors ce qu'il avait. */
function reglages_du_bot(string $gid): array
{
    [$code, $rep] = appel_bot('GET', '/api/guilds/' . $gid);
    if ($code !== 200) {
        return [];
    }
    $sortie = [];
    foreach (PONT_RESSOURCES as $cleSite => $cleBot) {
        $res = $rep['resources'][$cleBot] ?? null;
        $sortie[$cleSite] = is_array($res) ? (string)($res['id'] ?? '') : '';
    }
    foreach (PONT_FONCTIONS as $cleSite => $cleBot) {
        if (isset($rep['features'][$cleBot])) {
            $sortie[$cleSite] = $rep['features'][$cleBot] ? '1' : '0';
        }
    }
    if (!empty($rep['language'])) {
        $sortie['language'] = (string)$rep['language'];
    }

    /* Le surnom, dans l'autre sens. Il partait bien sur Discord, mais le
       panneau le relisait depuis notre fichier : renommé à la main sur
       Discord, il affichait l'ancien. Le bot, lui, le lit sur `guild.me`,
       donc à la source. `array_key_exists` et non `!empty` : une chaîne
       vide est une réponse — « aucun surnom » — et doit effacer la copie. */
    if (array_key_exists('nick', $rep)) {
        $sortie['bot.nick'] = (string)$rep['nick'];
    }

    /* La queue : les clés simples, puis les équipes, que le bot garde en
       deux listes parallèles (noms, et couleurs indexées par nom). */
    $q = is_array($rep['queue'] ?? null) ? $rep['queue'] : [];
    foreach (PONT_QUEUE as $cleSite => $cleBot) {
        if (array_key_exists($cleBot, $q) && $q[$cleBot] !== null) {
            $sortie[$cleSite] = (string)$q[$cleBot];
        }
    }
    if (array_key_exists('captains', $q)) {
        $sortie['queue.captainVote'] = $q['captains'] ? '1' : '0';
    }
    $ronds = array_flip(PONT_RONDS);
    $noms = is_array($q['team_names'] ?? null) ? $q['team_names'] : [];
    $couleurs = is_array($q['team_colors'] ?? null) ? $q['team_colors'] : [];
    foreach ($noms as $i => $nom) {
        if ($i > 5) { break; }           // le panneau n'affiche que six équipes
        $sortie["queue.team$i.name"] = (string)$nom;
        /* Pas de couleur enregistrée pour cette équipe : le bot prend le
           rond de son rang dans la palette. Le panneau doit montrer le
           même, sinon il affiche une teinte que l'annonce n'aura pas. */
        $rond = $couleurs[$nom] ?? null;
        $hexs = array_keys(PONT_RONDS);
        $sortie["queue.team$i.color"] = ($rond !== null && isset($ronds[$rond]))
            ? $ronds[$rond]
            : $hexs[$i % count($hexs)];
    }
    $sortie['queue.passwordValue'] = (string)($rep['queue_password'] ?? '');

    /* Les journaux. `channel` vaut null quand aucun salon n'est désigné :
       le panneau attend une chaîne vide, pas la chaîne « null ». */
    $journaux = is_array($rep['logs'] ?? null) ? $rep['logs'] : [];
    foreach (PONT_JOURNAUX as $type) {
        if (!isset($journaux[$type]) || !is_array($journaux[$type])) {
            continue;
        }
        $j = $journaux[$type];
        $sortie["log.$type.enabled"] = !empty($j['on']) ? '1' : '0';
        $sortie["log.$type.channel"] = (string)($j['channel'] ?? '');
    }

    /* Le nettoyage automatique. Sa configuration ne survivait pas à un
       redémarrage du bot : il n'y avait rien à lire. Elle est maintenant
       sur le disque, et c'est le bot qui en a la vérité — /autoclean on
       l'écrit aussi. */
    $net = is_array($rep['autoclean'] ?? null) ? $rep['autoclean'] : [];
    if ($net !== []) {
        $sortie['security.autoclean'] = !empty($net['enabled']) ? '1' : '0';
        $sortie['security.autocleanChannel'] = (string)($net['channel_id'] ?? '');
        $sortie['security.autocleanDelay'] = (string)(int)($net['interval_minutes'] ?? 20);
    }

    /* La file programmée, les saisons, les absences. Les trois se
       réglaient sur Discord seulement ; le panneau n'en savait rien. */
    foreach ([['schedule', PONT_PROGRAMME], ['season', PONT_SAISON],
              ['noshow', PONT_ABSENCES]] as [$bloc, $table]) {
        $source = is_array($rep[$bloc] ?? null) ? $rep[$bloc] : [];
        foreach ($table as $cleSite => $cleBot) {
            if (!array_key_exists($cleBot, $source)) {
                continue;
            }
            $v = $source[$cleBot];
            $sortie[$cleSite] = is_bool($v) ? ($v ? '1' : '0') : (string)$v;
        }
    }
    /* Les jours cochés, en texte. Une liste vide donne une chaîne vide, ce
       que le panneau sait lire comme « aucun jour ». */
    $jours = is_array($rep['schedule']['days'] ?? null) ? $rep['schedule']['days'] : null;
    if ($jours !== null) {
        $sortie['schedule.days'] = implode(',', array_map('strval', $jours));
    }

    /* Le webhook sortant. */
    if (array_key_exists('webhook', $rep)) {
        $sortie['webhook.url'] = (string)$rep['webhook'];
    }

    /* L'anti-lien, salon par salon. Une clé par salon surveillé —
       `antilink.<id>` — plutôt qu'une liste dans une seule valeur : le
       panneau enregistre champ par champ, et une liste obligerait à
       renvoyer tous les salons à chaque case cochée. */
    $anti = is_array($rep['antilink']['channels'] ?? null) ? $rep['antilink']['channels'] : [];
    $sortie['security.antilinkList'] = implode(',', array_map('strval', $anti));
    foreach ($anti as $cid) {
        $sortie['antilink.' . $cid] = '1';
    }

    /* L'anti-raid, dans l'autre sens : réglé par /antiraid config sur
       Discord, il doit se voir dans le panneau sans rien avoir à faire. */
    $sec = is_array($rep['security'] ?? null) ? $rep['security'] : [];
    foreach (PONT_SECURITE as $cleSite => $cleBot) {
        if (!array_key_exists($cleBot, $sec)) {
            continue;
        }
        $sortie[$cleSite] = $cleBot === 'auto_kick'
            ? ($sec[$cleBot] ? '1' : '0')
            : (string)(int)$sec[$cleBot];
    }

    /* Les rangs : la liste du bot devient des champs numérotés, que le
       panneau sait afficher et enregistrer un par un. */
    $rangs = is_array($rep['mmr']['tiers'] ?? null) ? $rep['mmr']['tiers'] : [];
    $sortie['mmr.rankCount'] = (string)count($rangs);
    foreach (array_values($rangs) as $i => $rang) {
        if ($i >= 12) { break; }
        $sortie["mmr.rank$i.name"] = (string)($rang['name'] ?? '');
        $sortie["mmr.rank$i.min"] = (string)(int)($rang['min'] ?? 0);
        $sortie["mmr.rank$i.color"] = sprintf('#%06x', (int)($rang['color'] ?? 0xF1C40F));
    }

    $m = is_array($rep['mmr'] ?? null) ? $rep['mmr'] : [];
    foreach (PONT_MMR as $cleSite => $cleBot) {
        if (!array_key_exists($cleBot, $m) || $m[$cleBot] === null) {
            continue;
        }
        if ($cleBot === 'enabled') {
            $sortie[$cleSite] = $m[$cleBot] ? '1' : '0';
        } elseif ($cleBot === 'loss') {
            $sortie[$cleSite] = (string)(-abs((int)$m[$cleBot]));
        } else {
            $sortie[$cleSite] = (string)(int)$m[$cleBot];
        }
    }

    return $sortie;
}

/* La personne connectée peut-elle agir sur ce serveur ?

   Elle doit en être administratrice, vu de Discord. Écrit une fois plutôt
   qu'à chaque route : c'est le genre de vérification qu'on finit par
   oublier dans la cinquième. Refuse et s'arrête — elle ne rend jamais
   « non ». */
function garde_de_guilde(array $session, string $gid): void
{
    foreach (mes_guildes($session) as $g) {
        if ((string)$g['id'] === $gid && peut_gerer($g)) {
            return;
        }
    }
    repondre(403, ['error' => 'FORBIDDEN']);
}

/* Un réglage du panneau, dans le type que le bot attend.

   Le panneau n'envoie QUE des chaînes : « 0 », « 1 », « 21:00 », « 3 ».
   Les passer telles quelles ferait de « 0 » un vrai booléen — une chaîne
   non vide est vraie en PHP — et le bot refuserait les entiers reçus en
   texte. D'où cette table unique, plutôt qu'un test par clé. */
function valeur_pour_le_bot(string $cleBot, $v)
{
    if (in_array($cleBot, PONT_BOOLEENS, true)) {
        return ($v === '1' || $v === 1 || $v === true);
    }
    if (in_array($cleBot, ['reminder_minutes', 'reset_day', 'threshold', 'ban_hours'], true)) {
        return (int)$v;
    }
    if ($cleBot === 'preset') {
        /* Vide = « la dernière configuration utilisée », que le bot note
           null. La chaîne vide serait un nom de preset introuvable. */
        return ($v === '' || $v === null) ? null : (string)$v;
    }
    return (string)$v;
}

/* Sépare un lot de réglages : ce qui part au bot, ce qui reste ici. */
function trier_pour_le_bot(array $propre, array $reglagesActuels = []): array
{
    $pourLeBot = ['resources' => [], 'features' => []];
    $ici = [];
    $equipes = [];
    $rangs = [];
    $nbRangs = null;
    $journaux = [];
    $nettoyage = [];
    $antilien = [];
    foreach ($propre as $k => $v) {
        if (array_key_exists($k, PONT_RESSOURCES)) {
            // Vide = on retire la désignation : le bot attend null.
            $pourLeBot['resources'][PONT_RESSOURCES[$k]] = ($v === '' || $v === null) ? null : (string)$v;
        } elseif (array_key_exists($k, PONT_FONCTIONS)) {
            $pourLeBot['features'][PONT_FONCTIONS[$k]] = ($v === '1' || $v === 1 || $v === true);
        } elseif ($k === 'language') {
            $pourLeBot['language'] = (string)$v;
        } elseif (array_key_exists($k, PONT_QUEUE)) {
            $cleBot = PONT_QUEUE[$k];
            // Le bot attend des entiers là où le panneau envoie du texte.
            $pourLeBot['queue'][$cleBot] = in_array($cleBot, ['num_teams', 'max_players_per_team'], true)
                ? (int)$v : (string)$v;
        } elseif ($k === 'queue.captainVote') {
            $pourLeBot['queue']['captains'] = ($v === '1' || $v === 1 || $v === true);
        } elseif (array_key_exists($k, PONT_MMR)) {
            $cleBot = PONT_MMR[$k];
            if ($cleBot === 'enabled') {
                $pourLeBot['mmr'][$cleBot] = ($v === '1' || $v === 1 || $v === true);
            } else {
                // Le bot retranche une valeur positive : on lui donne la
                // valeur absolue de ce que le panneau affiche en négatif.
                $pourLeBot['mmr'][$cleBot] = abs((int)$v);
            }
        } elseif (array_key_exists($k, PONT_SECURITE)) {
            $cleBot = PONT_SECURITE[$k];
            $pourLeBot['security'][$cleBot] = $cleBot === 'auto_kick'
                ? ($v === '1' || $v === 1 || $v === true)
                : (int)$v;
        } elseif ($k === 'queue.passwordValue') {
            $pourLeBot['queue_password'] = (string)$v;
        } elseif (preg_match('#^log\.([a-z]+)\.(enabled|channel)$#', $k, $mj)
                  && in_array($mj[1], PONT_JOURNAUX, true)) {
            /* Un journal se tient d'un bloc chez le bot — il éteint tout
               seul un type allumé sans salon. On lui envoie donc les deux
               champs ensemble, celui qui n'a pas changé compris. */
            $journaux[$mj[1]][$mj[2]] = $v;
        } elseif ($k === 'security.autoclean' || $k === 'security.autocleanChannel'
                  || $k === 'security.autocleanDelay') {
            $nettoyage[$k] = $v;
        } elseif (array_key_exists($k, PONT_PROGRAMME)) {
            $cleBot = PONT_PROGRAMME[$k];
            $pourLeBot['schedule'][$cleBot] = valeur_pour_le_bot($cleBot, $v);
        } elseif ($k === 'schedule.days') {
            /* « 0,5,6 » -> [0, 5, 6]. Les valeurs hors 0–6 tombent ici
               plutôt que chez le bot, qui refuserait le lot entier. */
            $jours = [];
            foreach (explode(',', (string)$v) as $j) {
                if ($j !== '' && ctype_digit(trim($j)) && (int)$j >= 0 && (int)$j <= 6) {
                    $jours[] = (int)$j;
                }
            }
            $pourLeBot['schedule']['days'] = array_values(array_unique($jours));
        } elseif (array_key_exists($k, PONT_SAISON)) {
            $cleBot = PONT_SAISON[$k];
            $pourLeBot['season'][$cleBot] = valeur_pour_le_bot($cleBot, $v);
        } elseif (array_key_exists($k, PONT_ABSENCES)) {
            $cleBot = PONT_ABSENCES[$k];
            $pourLeBot['noshow'][$cleBot] = valeur_pour_le_bot($cleBot, $v);
        } elseif ($k === 'webhook.url') {
            $pourLeBot['webhook'] = trim((string)$v);
        } elseif (preg_match('#^antilink\.(\d{5,25})$#', $k, $ma)) {
            /* Le bot veut la liste COMPLÈTE : un lot qui ne porte qu'une
               case cochée ne dit pas lesquels retirer. On part donc de ce
               qui est déjà enregistré et on applique la case par-dessus. */
            $antilien[$ma[1]] = ($v === '1' || $v === 1 || $v === true);
        } elseif (preg_match('#^mmr\.rank(\d{1,2})\.(name|min|color)$#', $k, $mr)) {
            // Même principe que les équipes : un rang se tient d'un bloc,
            // on ne peut pas en envoyer la moitié.
            $rangs[(int)$mr[1]][$mr[2]] = (string)$v;
        } elseif ($k === 'mmr.rankCount') {
            $nbRangs = max(1, min(12, (int)$v));
        } elseif (preg_match('#^queue\.team([0-5])\.(name|color)$#', $k, $mm)) {
            // Les équipes partent ensemble ou pas du tout : le bot les range
            // en deux listes liées par le nom, donc une moitié n'a pas de
            // sens. On les reconstruit toutes depuis le lot ET l'existant.
            $equipes[(int)$mm[1]][$mm[2]] = (string)$v;
        } else {
            $ici[$k] = $v;
        }
    }
    if (!$pourLeBot['resources']) { unset($pourLeBot['resources']); }
    if (!$pourLeBot['features'])  { unset($pourLeBot['features']); }

    /* Les équipes : on complète le lot avec ce qui est déjà enregistré,
       sinon renommer l'équipe 2 effacerait la couleur de l'équipe 1. */
    if ($equipes) {
        $connu = $reglagesActuels;
        $noms = [];
        $couleurs = [];
        for ($i = 0; $i < 6; $i++) {
            $nom = $equipes[$i]['name'] ?? ($connu["queue.team$i.name"] ?? null);
            if ($nom === null || $nom === '') { continue; }
            $hex = strtolower((string)($equipes[$i]['color'] ?? ($connu["queue.team$i.color"] ?? '')));
            $noms[] = (string)$nom;
            /* Une teinte hors des douze — un reste d'une version qui en
               autorisait d'autres — vaut le rond du rang, comme chez le
               bot. Chaque équipe a une couleur, toujours : sans cela, le
               bot reçoit un objet vide et refuse le lot entier. */
            if (!array_key_exists($hex, PONT_RONDS)) {
                $hexs = array_keys(PONT_RONDS);
                $hex = $hexs[$i % count($hexs)];
            }
            $couleurs[(string)$nom] = PONT_RONDS[$hex];
        }
        if ($noms) {
            $pourLeBot['queue']['team_names'] = $noms;
            // (object) : un tableau PHP vide s'encode en `[]`, et le bot
            // attend un objet. Il ne devrait plus être vide, mais la
            // garantie ne coûte rien.
            $pourLeBot['queue']['team_colors'] = (object)$couleurs;
        }
    }
    /* Les rangs, reconstruits entiers : le lot ne porte que ce qui a
       changé, le reste vient de ce que le bot a déjà. Sans cela, renommer
       un rang effacerait tous les autres. */
    if ($rangs || $nbRangs !== null) {
        $combien = $nbRangs ?? (int)($reglagesActuels['mmr.rankCount'] ?? 0);
        $liste = [];
        for ($i = 0; $i < max($combien, 0); $i++) {
            $nom = $rangs[$i]['name'] ?? ($reglagesActuels["mmr.rank$i.name"] ?? '');
            if (trim((string)$nom) === '') { continue; }
            $hex = strtolower((string)($rangs[$i]['color']
                   ?? ($reglagesActuels["mmr.rank$i.color"] ?? '#f1c40f')));
            $liste[] = [
                'name'  => (string)$nom,
                'min'   => (int)($rangs[$i]['min'] ?? ($reglagesActuels["mmr.rank$i.min"] ?? 0)),
                'color' => hexdec(ltrim($hex, '#')) ?: 0xF1C40F,
            ];
        }
        if ($liste) {
            $pourLeBot['mmr']['tiers'] = $liste;
        }
    }

    /* Les journaux, chacun complété par ce qui est déjà enregistré : le
       bot éteint un type allumé sans salon, donc lui envoyer l'interrupteur
       sans le salon l'éteindrait aussitôt. */
    foreach ($journaux as $type => $champs) {
        $actif = array_key_exists('enabled', $champs)
            ? ($champs['enabled'] === '1' || $champs['enabled'] === 1 || $champs['enabled'] === true)
            : (($reglagesActuels["log.$type.enabled"] ?? '0') === '1');
        $salon = array_key_exists('channel', $champs)
            ? (string)$champs['channel']
            : (string)($reglagesActuels["log.$type.channel"] ?? '');
        $pourLeBot['logs'][$type] = [
            'on'      => $actif,
            'channel' => $salon === '' ? null : $salon,
        ];
    }

    /* Le nettoyage automatique : le bot veut les trois champs ensemble,
       parce qu'« actif » sans salon n'est pas un réglage applicable. */
    if ($nettoyage) {
        $actif = array_key_exists('security.autoclean', $nettoyage)
            ? ($nettoyage['security.autoclean'] === '1' || $nettoyage['security.autoclean'] === 1
               || $nettoyage['security.autoclean'] === true)
            : (($reglagesActuels['security.autoclean'] ?? '0') === '1');
        $salon = array_key_exists('security.autocleanChannel', $nettoyage)
            ? (string)$nettoyage['security.autocleanChannel']
            : (string)($reglagesActuels['security.autocleanChannel'] ?? '');
        $minutes = array_key_exists('security.autocleanDelay', $nettoyage)
            ? (int)$nettoyage['security.autocleanDelay']
            : (int)($reglagesActuels['security.autocleanDelay'] ?? 20);
        $pourLeBot['autoclean'] = [
            'enabled'          => $actif,
            'channel_id'       => $salon === '' ? null : $salon,
            'interval_minutes' => max(1, min(10080, $minutes)),
        ];
    }

    /* L'anti-lien, reconstruit entier depuis l'existant plus les cases du
       lot. `security.antilinkList` tient la liste d'avant — c'est la
       lecture qui l'a posée, et elle est la seule forme compacte dont on
       dispose quand le lot ne porte qu'un salon. */
    if ($antilien) {
        $connus = array_filter(explode(',', (string)($reglagesActuels['security.antilinkList'] ?? '')));
        $liste = [];
        foreach ($connus as $cid) {
            $liste[(string)$cid] = true;
        }
        foreach ($antilien as $cid => $actif) {
            if ($actif) {
                $liste[(string)$cid] = true;
            } else {
                unset($liste[(string)$cid]);
            }
        }
        $pourLeBot['antilink'] = ['channels' => array_keys($liste)];
    }

    return [$pourLeBot, $ici];
}

/* --------------- ce dont le bot se souvient : lecture seule ---------------
 * Quatre relais, tous en GET, tous sans effet : l'historique des matchs, la
 * fiche d'un joueur, le relevé d'activité et le journal des modifications.
 *
 * Ils RELAIENT au lieu de servir une copie, parce que le site n'a rien à
 * copier : ces données ne sont écrites que par le bot, à chaque match et à
 * chaque réglage. Les dupliquer ici garantirait deux versions de la même
 * histoire, et c'est précisément ce que le journal est censé empêcher.
 *
 * Bot éteint : 502, et le panneau affiche son bandeau. Pas de repli sur
 * une copie périmée — un historique d'il y a trois jours présenté comme
 * l'historique est pire qu'un écran vide. */
if (preg_match('#^/guilds/(\d{5,25})/(matches|activity|audit)$#', $chemin, $m)
    && $methode === 'GET') {
    $gid = $m[1];
    $quoi = $m[2];
    garde_de_guilde($session, $gid);

    if ($BOT_API_BASE === '') {
        repondre(503, ['error' => 'BOT_API_ABSENTE']);
    }
    /* Les paramètres sont RECOPIÉS un par un, jamais relayés en bloc :
       passer $_GET tel quel laisserait n'importe qui ajouter ce qu'il veut
       à l'URL appelée chez le bot. */
    $permis = [];
    foreach (['limit', 'offset', 'days', 'player', 'season'] as $nom) {
        if (isset($_GET[$nom]) && preg_match('#^\d{1,10}$#', (string)$_GET[$nom])) {
            $permis[$nom] = (string)$_GET[$nom];
        }
    }
    $suite = $permis ? ('?' . http_build_query($permis)) : '';

    [$code, $rep] = appel_bot('GET', '/api/guilds/' . $gid . '/' . $quoi . $suite);
    if ($code === 0) {
        repondre(502, ['error' => 'BOT_INJOIGNABLE']);
    }
    if ($code !== 200) {
        repondre($code, is_array($rep) && $rep ? $rep : ['error' => 'BOT_REFUS']);
    }
    repondre(200, $rep);
}

if (preg_match('#^/guilds/(\d{5,25})/players/(\d{5,25})$#', $chemin, $m)
    && $methode === 'GET') {
    garde_de_guilde($session, $m[1]);
    if ($BOT_API_BASE === '') {
        repondre(503, ['error' => 'BOT_API_ABSENTE']);
    }
    [$code, $rep] = appel_bot('GET', '/api/guilds/' . $m[1] . '/players/' . $m[2]);
    if ($code === 0) {
        repondre(502, ['error' => 'BOT_INJOIGNABLE']);
    }
    if ($code !== 200) {
        repondre($code, is_array($rep) && $rep ? $rep : ['error' => 'BOT_REFUS']);
    }
    repondre(200, $rep);
}

/* ------------------- exclure ou réintégrer un joueur ----------------------
 * Un GESTE, et pas un réglage : « ajoute celui-ci », « retire celui-là ».
 * Envoyer la liste entière effacerait ce qu'un autre onglet — ou /blacklist
 * sur Discord — vient d'ajouter.
 *
 * Trois gestes : `add` et `remove` pour la liste noire posée à la main,
 * `lift` pour lever une exclusion automatique après trop d'absences. Le bot
 * tient les deux listes séparément et a de bonnes raisons pour ça. */
if (preg_match('#^/guilds/(\d{5,25})/bans$#', $chemin, $m) && $methode === 'POST') {
    $gid = $m[1];
    garde_de_guilde($session, $gid);

    if ($BOT_API_BASE === '') {
        repondre(503, ['error' => 'BOT_API_ABSENTE']);
    }
    $corps = json_decode((string)file_get_contents('php://input'), true);
    if (!is_array($corps)) {
        repondre(400, ['error' => 'BAD_REQUEST']);
    }
    $gestes = [];
    foreach (['add', 'remove', 'lift'] as $geste) {
        $liste = $corps[$geste] ?? [];
        if (!is_array($liste)) {
            repondre(400, ['error' => 'BAD_REQUEST']);
        }
        foreach ($liste as $uid) {
            if (!preg_match('#^\d{5,25}$#', (string)$uid)) {
                repondre(400, ['error' => 'BAD_REQUEST']);
            }
            $gestes[$geste][] = (string)$uid;
        }
    }
    if (!$gestes) {
        repondre(400, ['error' => 'BAD_REQUEST']);
    }
    $gestes['reason'] = mb_substr((string)($corps['reason'] ?? ''), 0, 200);

    [$code, $rep] = appel_bot('PATCH', '/api/guilds/' . $gid, [
        'bans'  => $gestes,
        'actor' => ['id' => $session['user_id'], 'name' => $session['user_name']],
    ]);
    if ($code === 0) {
        repondre(502, ['error' => 'BOT_INJOIGNABLE']);
    }
    if ($code !== 200) {
        repondre($code, is_array($rep) && $rep ? $rep : ['error' => 'BOT_REFUS']);
    }
    repondre(200, $rep);
}

/* ------------------- ouvrir ou fermer une queue depuis le site ------------
 * Relaie au bot, qui ouvre la queue avec SA configuration enregistrée —
 * exactement le bouton « Publier » du panneau /queue. Le site ne transmet
 * que qui ouvre : s'il envoyait ses propres réglages, deux vérités
 * cohabiteraient et la queue ouverte ne serait ni l'une ni l'autre.
 *
 * Son refus remonte tel quel (already_open, no_channel, setup_incomplete,
 * no_config, missing_permissions, no_queue) : chacun se répare ailleurs, et
 * le panneau en fait une phrase.
 *
 * La fermeture suit le même chemin et le même garde : elle supprime
 * l'annonce et purge le salon de commande, donc elle n'est pas moins
 * sensible que l'ouverture. */
if (preg_match('#^/guilds/(\d{5,25})/queue/(open|close)$#', $chemin, $m) && $methode === 'POST') {
    $gid = $m[1];
    $geste = $m[2];

    $laGuilde = null;
    foreach (mes_guildes($session) as $g) {
        if ((string)$g['id'] === $gid) {
            $laGuilde = $g;
            break;
        }
    }
    if (!$laGuilde || !peut_gerer($laGuilde)) {
        repondre(403, ['error' => 'FORBIDDEN']);
    }

    if ($BOT_API_BASE === '') {
        repondre(503, ['error' => 'BOT_API_ABSENTE']);
    }

    // Le bot nomme l'auteur différemment selon le geste : c'est lui qui
    // apparaît dans le journal Discord, ouverture comme fermeture.
    $qui = ['id' => $session['user_id'], 'name' => $session['user_name']];
    $envoi = json_encode($geste === 'open' ? ['openedBy' => $qui] : ['closedBy' => $qui]);

    [$code, $rep] = appel_bot('POST', '/api/guilds/' . $gid . '/queue/' . $geste,
                             json_decode($envoi, true));
    if ($code === 0) {
        // Bot éteint, port fermé, délai dépassé : rien n'a été ouvert.
        repondre(502, ['error' => 'BOT_INJOIGNABLE']);
    }

    if ($code === 200 || $code === 201) {
        repondre(200, $geste === 'open' ? [
            'channelId'  => $rep['channelId']  ?? null,
            'messageUrl' => $rep['messageUrl'] ?? null,
            'capacity'   => $rep['capacity']   ?? null,
        ] : [
            'queueName' => $rep['queueName'] ?? null,
            'players'   => $rep['players']   ?? null,
        ]);
    }
    if ($code === 409) {
        repondre(409, ['error' => $rep['error'] ?? ($geste === 'open' ? 'already_open' : 'no_queue')]);
    }
    if ($code === 401 || $code === 403) {
        // La clé du panneau et celle du bot ne sont pas la même.
        repondre(502, ['error' => 'BOT_CLE_REFUSEE']);
    }
    repondre(502, ['error' => $rep['error'] ?? 'BOT_INJOIGNABLE']);
}

if ($chemin === '/guilds' && $methode === 'GET') {
    $brut = mes_guildes($session);
    $reglages = lire_reglages();

    /* La présence du bot vient de Discord quand on peut la lui demander, de
       l'enregistrement local sinon. Ce repli peut se tromper PAR DÉFAUT —
       dire « absent » d'un bot présent — jamais dans l'autre sens : la
       ligne propose alors de l'inviter, ce qui ne casse rien s'il est déjà
       là. L'inverse enverrait vers un panneau que le bot ne peut pas
       servir. */
    $presents = guildes_du_bot($BOT_TOKEN);
    $index = $presents === null ? null : array_flip($presents);

    $liste = [];
    foreach ($brut as $g) {
        if (!peut_gerer($g)) {
            continue;
        }
        $enr = $reglages[$g['id']] ?? [];
        $liste[] = [
            'id'                 => $g['id'],
            'name'               => $g['name'],
            'iconUrl'            => url_icone($g['id'], $g['icon'] ?? null),
            'memberCount'        => $g['approximate_member_count'] ?? null,
            'canManage'          => true,
            'botPresent'         => $index === null
                ? (bool)($enr['botPresent'] ?? false)
                : isset($index[(string)$g['id']]),
            'configured'         => !empty($enr['settings']),
            'updatedAt'          => $enr['updatedAt'] ?? null,
            'missingPermissions' => $enr['missingPermissions'] ?? [],
        ];
    }
    repondre(200, $liste);
}

/* Toutes les routes qui suivent portent sur UN serveur. On vérifie à chaque
   fois que la personne le gère vraiment : sans ce contrôle, n'importe quel
   compte connecté lirait et modifierait la configuration de n'importe quelle
   guilde en changeant l'identifiant dans l'URL. */
if (preg_match('#^/guilds/(\d{5,25})(/settings)?$#', $chemin, $m)) {
    $gid = $m[1];
    $estReglages = isset($m[2]);

    $laGuilde = null;
    foreach (mes_guildes($session) as $g) {
        if ((string)$g['id'] === $gid) {
            $laGuilde = $g;
            break;
        }
    }
    if (!$laGuilde || !peut_gerer($laGuilde)) {
        repondre(403, ['error' => 'FORBIDDEN']);
    }

    // ---- enregistrement ----
    if ($estReglages && $methode === 'PATCH') {
        $brut = file_get_contents('php://input');
        if ($brut === false || strlen($brut) > 262144) {
            repondre(400, ['error' => 'BAD_REQUEST']);
        }
        $corps = json_decode((string)$brut, true);
        if (!is_array($corps)) {
            repondre(400, ['error' => 'BAD_REQUEST']);
        }
        // Les valeurs sont stockées telles quelles, mais les CLÉS sont
        // bornées : sans ça, une clé fantaisiste polluerait le fichier.
        $propre = [];
        foreach ($corps as $k => $v) {
            if (is_string($k) && preg_match('#^[A-Za-z0-9._-]{1,64}$#', $k)
                && (is_scalar($v) || $v === null)) {
                $propre[$k] = is_bool($v) ? ($v ? '1' : '0') : $v;
            }
        }
        /* Le surnom n'est pas un réglage comme les autres : il ne vit pas
           dans notre fichier, il vit sur Discord. On l'y écrit, et on le
           garde aussi chez nous pour que le panneau puisse le réafficher
           sans redemander le membre à chaque ouverture.

           `PATCH /guilds/{id}/members/@me` ne touche QUE ce serveur. Le nom
           et la photo du bot, eux, appartiennent à l'application et sont
           les mêmes partout : cette route ne peut pas les changer, et c'est
           exactement pour ça qu'elle est la seule acceptable ici.

           Un échec ne fait pas échouer la requête entière : les autres
           réglages du même lot sont légitimes et doivent être enregistrés.
           Le surnom manquant se verra au prochain affichage. */
        if (array_key_exists('bot.nick', $propre) && $BOT_TOKEN !== '') {
            $surnom = trim((string)$propre['bot.nick']);
            /* 32 caractères est la limite de Discord. Une chaîne vide
               remet le nom d'origine — `null` et non `''`, que Discord
               refuse. */
            if (mb_strlen($surnom) > 32) {
                $surnom = mb_substr($surnom, 0, 32);
                $propre['bot.nick'] = $surnom;
            }
            @appel_discord_patch("/guilds/$gid/members/@me",
                ['nick' => ($surnom === '' ? null : $surnom)], $BOT_TOKEN);
        }

        /* Ce que le bot tient part chez lui ; le reste reste ici. Son refus
           ou son silence fait échouer TOUT le lot : enregistrer la moitié
           d'un formulaire en disant « c'est fait » serait pire que de ne
           rien enregistrer. Le panneau garde alors les champs en attente. */
        /* La base des équipes vient du BOT, pas de notre fichier : le site
           n'a de ses équipes qu'une copie, parfois incomplète, et repartir
           d'elle revenait à supprimer chez le bot celles qu'elle ignorait.
           Un renommage de l'équipe 1 effaçait ainsi l'équipe 2. */
        $dejaLa = array_merge(lire_reglages()[$gid]['settings'] ?? [], reglages_du_bot($gid));
        [$pourLeBot, $ici] = trier_pour_le_bot($propre, $dejaLa);
        if ($pourLeBot) {
            if ($BOT_API_BASE === '') {
                repondre(503, ['error' => 'BOT_API_ABSENTE']);
            }
            /* Qui enregistre. Le bot ne sait pas vérifier cette identité —
               il ne connaît que la clé — mais nous venons de vérifier que
               la personne est admin de ce serveur. C'est la seule façon
               pour son journal de répondre à « qui a changé ça ? ». */
            $pourLeBot['actor'] = [
                'id'   => $session['user_id'],
                'name' => $session['user_name'],
            ];
            [$code, $rep] = appel_bot('PATCH', '/api/guilds/' . $gid, $pourLeBot);
            if ($code === 0) {
                repondre(502, ['error' => 'BOT_INJOIGNABLE']);
            }
            if ($code === 401 || $code === 403) {
                repondre(502, ['error' => 'BOT_CLE_REFUSEE']);
            }
            if ($code === 404) {
                // Le bot n'est pas sur ce serveur : rien à régler chez lui.
                repondre(409, ['error' => 'BOT_ABSENT']);
            }
            if ($code !== 200) {
                repondre(502, ['error' => $rep['error'] ?? 'BOT_REFUS']);
            }
        }

        /* Le fichier du site ne garde plus que ce que le bot ne sait pas
           tenir — et une copie de ce qu'il tient, pour que le panneau
           s'affiche même quand le bot dort. */
        modifier_reglages(function (array $tout) use ($gid, $propre): array {
            $actuel = $tout[$gid] ?? [];
            $tout[$gid] = array_merge($actuel, [
                'settings'  => array_merge($actuel['settings'] ?? [], $propre),
                'updatedAt' => gmdate('Y-m-d\TH:i:s\Z'),
            ]);
            return $tout;
        });
        repondre(204);
    }

    // ---- lecture ----
    if (!$estReglages && $methode === 'GET') {
        $enr = lire_reglages()[$gid] ?? [];

        /* Le bot répond, ou pas. La différence SE DIT : jusqu'ici, un bot
           éteint faisait servir la copie locale avec exactement la même
           assurance qu'une lecture fraîche. On lisait un écran qui avait
           l'air juste, on modifiait un champ, et c'est le refus
           d'enregistrement (BOT_INJOIGNABLE) qui apprenait que le bot
           dormait. L'écriture était honnête, la lecture non. */
        $duBot = reglages_du_bot($gid);
        $rep = [
            'id'                 => $laGuilde['id'],
            'name'               => $laGuilde['name'],
            'iconUrl'            => url_icone($gid, $laGuilde['icon'] ?? null, 128),
            'memberCount'        => $laGuilde['approximate_member_count'] ?? null,
            'me'                 => ['name' => $session['user_name']],
            /* Le bot a le dernier mot sur ce qu'il tient : c'est lui qui
               publiera et créera, pas nous. Injoignable, on sert la copie
               locale plutôt qu'un écran vide — mais `botJoignable` dit
               alors au panneau que ce qu'il montre peut dater. */
            'botJoignable'       => $duBot !== [],
            'settings'           => $duBot
                ? array_merge($enr['settings'] ?? [], $duBot)
                : ($enr['settings'] ?? null),
            'presets'            => $enr['presets'] ?? [],
            'permissions'        => $enr['permissions'] ?? null,
            'missingPermissions' => $enr['missingPermissions'] ?? [],
            'botRolePosition'    => $enr['botRolePosition'] ?? null,
            'channels'           => [],
            'voiceChannels'      => [],
            'categories'         => [],
            'roles'              => [],
        ];

        /* Salons et rôles ne sont lisibles qu'avec un jeton de BOT : le jeton
           de la personne n'y donne pas accès. Sans jeton de bot, on renvoie
           des listes vides — les menus seront vides, mais rien ne ment. */
        if ($BOT_TOKEN !== '') {
            try {
                $salons = appel_discord("/guilds/$gid/channels", $BOT_TOKEN, 'Bot');
                $roles  = appel_discord("/guilds/$gid/roles", $BOT_TOKEN, 'Bot');
                $nom = fn(array $c) => ['id' => $c['id'], 'name' => $c['name']];
                /* Les types de salons, tels que Discord les numérote.
                   0 textuel · 2 vocal · 4 catégorie · 5 annonces ·
                   13 conférence (« Stage »).

                   Les annonces et les conférences étaient ignorées, alors
                   qu'elles se comportent exactement comme un salon textuel
                   et un salon vocal : le bot y écrit, et il y déplace des
                   joueurs. Un serveur dont le salon d'attente est une
                   conférence voyait donc « aucun salon vocal », sans que
                   rien ne soit cassé nulle part. */
                foreach ($salons as $c) {
                    $type = $c['type'] ?? -1;
                    if ($type === 0 || $type === 5)       { $rep['channels'][]      = $nom($c); }
                    elseif ($type === 2 || $type === 13)  { $rep['voiceChannels'][] = $nom($c); }
                    elseif ($type === 4)                  { $rep['categories'][]    = $nom($c); }
                }
                usort($roles, fn($a, $b) => ($b['position'] ?? 0) <=> ($a['position'] ?? 0));
                foreach ($roles as $r) {
                    if (!empty($r['managed']) || ($r['name'] ?? '') === '@everyone') {
                        continue;
                    }
                    $rep['roles'][] = [
                        'id'       => $r['id'],
                        'name'     => $r['name'],
                        'position' => $r['position'] ?? 0,
                    ];
                }
            } catch (Throwable $e) {
                // Le bot n'est pas sur ce serveur, ou il lui manque un droit.
                // Le repli ci-dessous rattrape ce cas.
            }
        }

        /* LE REPLI SUR LE BOT.
           Jusqu'ici, un BOT_TOKEN absent de secrets.php ou un appel à
           Discord qui échouait donnait quatre listes vides, EN SILENCE.
           Conséquence visible : tous les menus de salons et de rôles du
           panneau restaient muets, et la section Anti-lien n'affichait
           qu'un filtre sans rien à filtrer — un écran qui a l'air fini et
           qui ne sert à rien.

           Le bot tient déjà ces listes : c'est `GET /guilds/{id}/options`,
           et il les a pour les huit serveurs. On les lui redemande plutôt
           que de servir du vide. Il est d'ailleurs mieux placé que nous
           pour les salons textuels : il n'y met que ceux où il a le droit
           d'écrire.

           Liste par liste, et non « tout ou rien » : Discord peut très bien
           rendre les salons et refuser les rôles, et dans ce cas on ne
           remplace que ce qui manque. */
        if (!$rep['channels'] || !$rep['voiceChannels']
            || !$rep['categories'] || !$rep['roles']) {
            [$codeOpt, $opt] = appel_bot('GET', '/api/guilds/' . $gid . '/options');
            if ($codeOpt === 200 && is_array($opt)) {
                /* On recopie champ par champ au lieu de passer la réponse
                   telle quelle : le front attend `{id, name}` en chaînes, et
                   une entrée mal formée doit disparaître, pas arriver
                   jusqu'à un menu sous la forme « undefined ». */
                $repli = static function ($brut): array {
                    $sortie = [];
                    foreach (is_array($brut) ? $brut : [] as $e) {
                        if (!is_array($e) || !isset($e['id'], $e['name'])) {
                            continue;
                        }
                        $un = ['id' => (string)$e['id'], 'name' => (string)$e['name']];
                        if (isset($e['position'])) {
                            $un['position'] = (int)$e['position'];
                        }
                        $sortie[] = $un;
                    }
                    return $sortie;
                };
                if (!$rep['channels'])      { $rep['channels']      = $repli($opt['text'] ?? null); }
                if (!$rep['voiceChannels']) { $rep['voiceChannels'] = $repli($opt['voice'] ?? null); }
                if (!$rep['categories'])    { $rep['categories']    = $repli($opt['category'] ?? null); }
                if (!$rep['roles'])         { $rep['roles']         = $repli($opt['role'] ?? null); }
            }
        }
        repondre(200, $rep);
    }

    repondre(405, ['error' => 'METHOD_NOT_ALLOWED']);
}

repondre(404, ['error' => 'NOT_FOUND']);
