<?php
declare(strict_types=1);

/* =========================================================================
   contact.php — l'envoi du formulaire de support.

   POURQUOI CE FICHIER EST À LA RACINE DE LA VITRINE, et pas dans api/.

   La vitrine (cyqbot.eu) et le panneau (dashboard.cyqbot.eu) sont deux
   origines distinctes, et `site/api/index.php` ne pose AUCUN en-tête CORS —
   c'est un choix, écrit noir sur blanc en tête de ce fichier : l'API vit sur
   la même origine que les pages qui l'appellent, donc pas de CORS, pas de
   cookie tiers, rien à héberger ailleurs.

   support.html est une page de la VITRINE. Lui faire appeler l'API du
   panneau obligerait à ouvrir CORS sur une API qui tient une session
   Discord — beaucoup de surface gagnée pour un formulaire de contact. Ce
   point d'entrée vit donc à côté de la page qui l'appelle, et elle le
   joint en relatif. Il ne connaît ni session, ni jeton, ni Discord.

   `verif-php.php`, déjà déclaré dans la liste des fichiers de la vitrine,
   a servi à vérifier que LWS exécute bien du PHP de ce côté-là.
   ========================================================================= */

/* L'adresse de destination. Ce n'est pas un secret : elle est écrite en
   toutes lettres sur la page, et le but du formulaire est de lui écrire. */
const DESTINATAIRE = 'contact@cyqbot.eu';

/* L'expéditeur annoncé au serveur de courrier. Il DOIT être une adresse
   du domaine : mettre celle du visiteur dans `From:` ferait partir
   un message qui prétend venir de gmail.com depuis un serveur LWS, que SPF
   et DMARC rejettent — le courrier n'arriverait pas, ou en indésirable.
   L'adresse du visiteur va dans `Reply-To:`, qui est fait pour ça. */
const EXPEDITEUR = 'contact@cyqbot.eu';
const EXPEDITEUR_NOM = 'CreateYourQueue';

/* Trois messages par quart d'heure et par adresse IP. Assez pour renvoyer
   un message qu'on a raté, trop peu pour servir de robinet à spam. */
const QUOTA_NOMBRE = 3;
const QUOTA_FENETRE = 900;

/* Les bornes de chaque champ. Elles sont redites côté page (maxlength),
   mais un `maxlength` ne protège personne : il ne vit que dans le
   navigateur, et ce point d'entrée est joignable sans lui. */
const BORNES = [
    'nom'     => [2, 80],
    'email'   => [5, 190],
    'sujet'   => [2, 120],
    'message' => [10, 5000],
];

// ------------------------------------------------------------- réponses ----

/* Même forme que site/api/index.php : un code HTTP, et un corps JSON qui
   porte le MOTIF. C'est lui qui permet à la page d'écrire une phrase juste
   plutôt qu'un « une erreur est survenue ». */
function repondre(int $code, ?array $donnees = null): void
{
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('X-Content-Type-Options: nosniff');
    header('Cache-Control: no-store');
    if ($donnees !== null) {
        echo json_encode($donnees, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    }
    exit;
}

function erreur(int $code, string $motif): void
{
    repondre($code, ['error' => $motif]);
}

// ---------------------------------------------------------- nettoyage ------

/* Tout ce qui finit dans un EN-TÊTE de courrier passe par ici. Un retour
   chariot dans le sujet ou dans l'adresse permettrait d'ajouter un `Bcc:`
   et de se servir du formulaire comme d'un relais : c'est l'injection
   d'en-tête, et elle se coupe en retirant CR, LF et NUL, pas en les
   échappant. */
function sans_saut(string $v): string
{
    return trim(str_replace(["\r", "\n", "\0"], ' ', $v));
}

/* Le corps du message, lui, a le droit d'avoir des lignes. On normalise
   seulement les fins de ligne, parce qu'un courrier les veut en CRLF. */
function corps_propre(string $v): string
{
    return str_replace(["\r\n", "\r"], "\n", trim($v));
}

/* Le nom affiché dans un en-tête d'adresse. `sans_saut` a déjà retiré de
   quoi injecter un en-tête entier ; restent les caractères qui structurent
   une ADRESSE. Un nom comme « Alex <autre@exemple.com> » donnerait
   `Reply-To: Alex <autre@exemple.com> <alex@vrai.fr>` : deux adresses, dont
   une qui n'est jamais passée par FILTER_VALIDATE_EMAIL, et un en-tête que
   chaque client de messagerie interprète à sa façon. On les retire.
   `mb_encode_mimeheader` protège les accents, pas la grammaire. */
function nom_pour_entete(string $v): string
{
    return trim((string)preg_replace('/[<>"\',;:]/u', ' ', $v));
}

/* Un sujet non-ASCII doit être encodé, sinon les accents arrivent en
   charabia. `mb_encode_mimeheader` fait le pliage de ligne correctement ;
   sans mbstring — improbable, mais LWS est un mutualisé — on se rabat sur
   un encodage base64 d'un seul tenant. */
function entete_encodee(string $v): string
{
    if (function_exists('mb_encode_mimeheader')) {
        return mb_encode_mimeheader($v, 'UTF-8', 'B');
    }
    return '=?UTF-8?B?' . base64_encode($v) . '?=';
}

// ------------------------------------------------------------- quota -------

/* Le compteur vit dans le dossier temporaire du système, pas dans le
   dépôt : il n'a aucune valeur passé le quart d'heure, et un dossier de
   plus à créer sur le serveur FTP serait un oubli de plus le jour d'une
   réinstallation. S'il est vidé entre deux requêtes, le pire qui arrive
   est qu'un visiteur puisse renvoyer un message : ce n'est pas un contrôle
   de sécurité, c'est un robinet qu'on serre. */
function fichier_quota(string $ip): string
{
    return sys_get_temp_dir() . '/cyq-contact-' . sha1($ip) . '.json';
}

function quota_depasse(string $ip): bool
{
    $f = fichier_quota($ip);
    $maintenant = time();
    $vus = [];
    if (is_file($f)) {
        $lu = json_decode((string)@file_get_contents($f), true);
        if (is_array($lu)) {
            // On ne garde que ce qui est encore dans la fenêtre.
            $vus = array_values(array_filter($lu, static function ($t) use ($maintenant) {
                return is_int($t) && ($maintenant - $t) < QUOTA_FENETRE;
            }));
        }
    }
    if (count($vus) >= QUOTA_NOMBRE) {
        return true;
    }
    $vus[] = $maintenant;
    @file_put_contents($f, json_encode($vus), LOCK_EX);
    return false;
}

// --------------------------------------------------------------- route -----

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'POST') {
    header('Allow: POST');
    erreur(405, 'METHOD_NOT_ALLOWED');
}

$brut = file_get_contents('php://input');
if ($brut === false || strlen($brut) > 65536) {
    erreur(400, 'BAD_REQUEST');
}
$corps = json_decode((string)$brut, true);
if (!is_array($corps)) {
    erreur(400, 'BAD_REQUEST');
}

/* Le piège à robots. Le champ `site` existe dans le formulaire, il est
   caché et sans étiquette : une personne ne le voit pas, un robot qui
   remplit tout le remplit. On répond alors 204 — le succès — parce qu'un
   refus lui apprendrait que le piège existe et où il est. Rien n'est
   envoyé. Pas de CAPTCHA : il coûterait une dépendance et un tiers, et il
   punirait surtout les gens qui lisent mal les lettres tordues. */
if (trim((string)($corps['site'] ?? '')) !== '') {
    repondre(204);
}

$valeurs = [];
foreach (BORNES as $champ => [$min, $max]) {
    $v = $corps[$champ] ?? '';
    if (!is_string($v)) {
        erreur(400, 'BAD_REQUEST');
    }
    $v = $champ === 'message' ? corps_propre($v) : sans_saut($v);
    $longueur = function_exists('mb_strlen') ? mb_strlen($v, 'UTF-8') : strlen($v);
    if ($longueur < $min) {
        erreur(400, $v === '' ? 'CHAMP_MANQUANT' : 'TROP_COURT');
    }
    if ($longueur > $max) {
        erreur(400, 'TROP_LONG');
    }
    $valeurs[$champ] = $v;
}

if (!filter_var($valeurs['email'], FILTER_VALIDATE_EMAIL)) {
    erreur(400, 'EMAIL_INVALIDE');
}

$ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
if ($ip !== '' && quota_depasse($ip)) {
    erreur(429, 'TROP_DE_DEMANDES');
}

// ------------------------------------------------------------- l'envoi -----

$sujet = entete_encodee('[Support] ' . $valeurs['sujet']);

/* Le corps porte qui écrit, pour que la réponse parte au bon endroit même
   si le client de messagerie ignore Reply-To. La langue de la page est
   notée parce qu'elle dit dans quelle langue répondre — c'est la seule
   chose qu'on retienne du navigateur, et elle vient du corps JSON, pas
   d'un en-tête qu'on irait renifler. */
$langue = sans_saut((string)($corps['langue'] ?? ''));
if (!in_array($langue, ['fr', 'en', 'es', 'de', 'ko'], true)) {
    $langue = '?';
}

$texte = "De      : {$valeurs['nom']} <{$valeurs['email']}>\n"
       . "Sujet   : {$valeurs['sujet']}\n"
       . "Langue  : {$langue}\n"
       . "Reçu le : " . gmdate('Y-m-d H:i:s') . " UTC\n"
       . str_repeat('-', 60) . "\n\n"
       . $valeurs['message'] . "\n";

$entetes = [
    'From: ' . entete_encodee(EXPEDITEUR_NOM) . ' <' . EXPEDITEUR . '>',
    'Reply-To: ' . entete_encodee(nom_pour_entete($valeurs['nom'])) . ' <' . $valeurs['email'] . '>',
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: 8bit',
    'MIME-Version: 1.0',
    'X-Mailer: cyqbot.eu',
];

/* `-f` donne l'enveloppe d'expédition (le Return-Path). Sans lui, LWS
   envoie sous l'utilisateur système du compte, et le message part avec une
   adresse qui n'existe pas — de quoi le faire refuser. */
$ok = @mail(
    DESTINATAIRE,
    $sujet,
    str_replace("\n", "\r\n", $texte),
    implode("\r\n", $entetes),
    '-f' . EXPEDITEUR
);

if (!$ok) {
    /* On ne prétend pas que c'est parti. La page propose alors d'ouvrir le
       client de messagerie, qui est le chemin qui ne dépend pas de nous. */
    erreur(502, 'ENVOI_IMPOSSIBLE');
}

repondre(204);
