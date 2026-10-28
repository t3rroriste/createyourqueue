# =========================================================================
# Mise en ligne sur l'hébergement LWS, en une commande.
#
# Le site vit sur DEUX domaines :
#
#   cyqbot.eu             la vitrine    index, modules, guide
#   dashboard.cyqbot.eu   l'application login, welcome, servers, dashboard
#
# Chacun reçoit ses pages, plus le socle commun (app.js, config.js, les
# cinq langues, anime.js, le logo, .htaccess). Le script :
#
#   1. renumérote les assets (?v=…) dans les pages — sinon les visiteurs
#      gardent l'ancien CSS et l'ancien JS en cache ;
#   2. envoie chaque fichier par FTP, chiffré si l'hébergeur le permet ;
#   3. dit ce qui est parti et ce qui a échoué.
#
# Usage :
#   .\cyq.ps1 publier                 # les deux domaines (le chemin court)
#   powershell -File outils\publier-site.ps1               # idem
#   powershell -File outils\publier-site.ps1 -Cible site   # vitrine
#   powershell -File outils\publier-site.ps1 -Cible app    # panneau
#   powershell -File outils\publier-site.ps1 -DryRun       # essai
#   powershell -File outils\publier-site.ps1 -ListRemote   # repérage
#
# Le mot de passe n'est JAMAIS écrit en clair. Trois sources, dans cet
# ordre :
#
#   1. la variable d'environnement LWS_FTP_PASS, si elle existe ;
#   2. outils/reglages/lws.pass, s'il a été retenu une fois ;
#   3. l'écran, sinon — et on propose alors de le retenir.
#
# outils/reglages/lws.pass est chiffré par Windows (DPAPI) avec la clé de TON compte
# sur CETTE machine : un autre compte, ou la même sauvegarde copiée sur une
# autre machine, ne peut pas le relire. Ce n'est pas un coffre-fort, c'est
# un cran au-dessus d'un fichier texte.
#
#   powershell -File outils\publier-site.ps1 -OublieMotDePasse
#
# efface cette mémoire.
#
#   $env:LWS_FTP_PASS = 'le-mot-de-passe'   # une fois par session, facultatif
# =========================================================================

param(
  [ValidateSet('site', 'app', 'tout')]
  [string]$Cible = 'tout',   # quel domaine mettre à jour
  [switch]$DryRun,           # montre ce qui serait envoyé, n'envoie rien
  [switch]$NoBump,           # n'incrémente pas les ?v= (déconseillé)
  [switch]$ListRemote,       # liste les dossiers distants, pour trouver les racines
  [switch]$OublieMotDePasse  # efface le mot de passe retenu, puis s'arrête
)

$ErrorActionPreference = 'Stop'

# Ce script vit dans `outils/`, le site dans `site/`, les identifiants dans
# `outils/reglages/` (hors git). Trois dossiers, trois rôles : le code servi
# ne contient aucun secret, et un `git add -A` distrait ne peut pas en
# emporter un.
$ici      = Split-Path -Parent $MyInvocation.MyCommand.Path
$racine   = Join-Path (Split-Path -Parent $ici) 'site'
$reglages = Join-Path $ici 'reglages'

# ------------------------------------------------------------ réglages ---

$cheminConf = Join-Path $reglages 'lws.config.ps1'
if (-not (Test-Path $cheminConf)) {
  Write-Host "Fichier de réglages absent : outils/reglages/lws.config.ps1" -ForegroundColor Yellow
  Write-Host "Copie lws.config.exemple.ps1 en lws.config.ps1 et remplis-le." -ForegroundColor Yellow
  exit 1
}
$conf = & $cheminConf

foreach ($cle in @('Serveur', 'Utilisateur', 'RacineSite', 'RacineApp')) {
  if (-not $conf[$cle]) { throw "Réglage manquant dans outils/reglages/lws.config.ps1 : $cle" }
}

# Un fichier laissé avec ses valeurs d'exemple enverrait les fichiers nulle
# part, en demandant un mot de passe au passage. On le dit tout de suite.
$aRemplir = @('Serveur', 'Utilisateur', 'RacineSite', 'RacineApp') |
  Where-Object { "$($conf[$_])" -match 'A_REMPLIR' }
if ($aRemplir.Count) {
  Write-Host "Il reste des valeurs à remplir dans outils/reglages/lws.config.ps1 :" -ForegroundColor Yellow
  $aRemplir | ForEach-Object { Write-Host ("  " + $_) -ForegroundColor Yellow }
  Write-Host ""
  Write-Host "Panneau client LWS -> ton hébergement -> rubrique FTP."
  exit 1
}
$ftps = $true
if ($conf.ContainsKey('Ftps')) { $ftps = [bool]$conf['Ftps'] }
$certNonVerifie = $false
if ($conf.ContainsKey('CertificatNonVerifie')) { $certNonVerifie = [bool]$conf['CertificatNonVerifie'] }

# ----------------------------------------------------- mot de passe ------

$cheminPass = Join-Path $reglages 'lws.pass'

# Un SecureString ne se compare ni ne se concatène : curl veut la chaîne.
# Le détour par un BSTR est le seul moyen propre de la sortir, et le bloc
# finally la libère de la mémoire non managée même si la suite lève.
function En-Clair {
  param([Security.SecureString]$s)
  if (-not $s) { return $null }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
  try   { return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

if ($OublieMotDePasse) {
  if (Test-Path $cheminPass) {
    Remove-Item $cheminPass -Force
    Write-Host "Mot de passe oublié. Il sera redemandé au prochain envoi."
  } else {
    Write-Host "Aucun mot de passe n'était retenu."
  }
  exit 0
}

$motDePasse = $env:LWS_FTP_PASS

# DPAPI refuse de déchiffrer ce qu'un autre compte a chiffré, et c'est le
# comportement voulu. Mais un profil Windows restauré ou une session changée
# produisent la même erreur : on ne plante pas, on redemande.
if (-not $motDePasse -and (Test-Path $cheminPass)) {
  try {
    $motDePasse = En-Clair ((Get-Content $cheminPass -Raw).Trim() | ConvertTo-SecureString)
  } catch {
    Write-Host "Le mot de passe retenu n'a pas pu être relu sur ce compte. Il est effacé et redemandé." -ForegroundColor Yellow
    Remove-Item $cheminPass -Force -ErrorAction SilentlyContinue
    $motDePasse = $null
  }
}

if (-not $motDePasse) {
  $secure = Read-Host -Prompt ("Mot de passe FTP de " + $conf.Utilisateur) -AsSecureString
  $motDePasse = En-Clair $secure

  # On ne propose de retenir qu'un mot de passe qu'on vient de saisir : si
  # la variable d'environnement l'a fourni, c'est un choix déjà fait ailleurs
  # et ce n'est pas à ce script de le recopier sur le disque.
  if ($motDePasse) {
    $rep = Read-Host "Le retenir sur cette machine, chiffré par Windows ? (O/n)"
    if ($rep -notmatch '^\s*[nN]') {
      try {
        $secure | ConvertFrom-SecureString | Set-Content -Path $cheminPass -Encoding ASCII -NoNewline
        Write-Host "Retenu dans deploy-lws.pass. Pour l'oublier : -OublieMotDePasse" -ForegroundColor DarkGray
      } catch {
        Write-Host ("Impossible de le retenir : " + $_.Exception.Message) -ForegroundColor Yellow
      }
    }
  }
}

if (-not $motDePasse) { throw "Aucun mot de passe fourni." }

# curl lit les identifiants sur son entrée standard : ils n'apparaissent
# donc pas dans la liste des processus de la machine.
#
# Dans un fichier de configuration curl, une valeur entre guillemets
# comprend \\ et \" : un mot de passe contenant une barre oblique inverse
# ou un guillemet doit donc être échappé, sinon curl lit un identifiant
# tronqué et le serveur répond « login incorrect » — sur un mot de passe
# pourtant juste.
function Protege-ValeurCurl {
  param([string]$v)
  return $v.Replace('\', '\\').Replace('"', '\"')
}

function Config-Curl {
  param([bool]$AvecSsl)
  $u = Protege-ValeurCurl $conf.Utilisateur
  $p = Protege-ValeurCurl $motDePasse
  $c = "user = `"$u`:$p`""
  if ($AvecSsl) {
    $c += "`nssl-reqd"
    # Le certificat de LWS est valide mais émis pour *.lwspanel.com : sans
    # cette ligne, curl s'arrête sur le nom qui ne correspond pas. La
    # liaison reste chiffrée ; c'est l'identité du serveur qui n'est plus
    # vérifiée. Voir le commentaire dans reglages/lws.config.ps1.
    if ($certNonVerifie) { $c += "`ninsecure" }
  }
  return $c
}

$confCurl = Config-Curl $ftps

# Les identifiants passent par un fichier temporaire, et pas par la ligne
# de commande : celle-ci est lisible par n'importe quel autre programme de
# la machine, dans la liste des processus.
#
# Pourquoi un fichier et pas l'entrée standard : « --config - » est refusé
# par le curl livré avec Windows quand PowerShell l'alimente par un tube
# (« error encountered when reading a file »). Le fichier est créé dans le
# dossier temporaire de TON compte, utilisé, puis effacé immédiatement —
# même si curl échoue.
function Invoke-Curl {
  # Surtout pas $Args : c'est une variable automatique de PowerShell, et un
  # paramètre qui porte ce nom n'est jamais alimenté — curl recevait alors
  # ses options sans aucune URL.
  param([string[]]$Arguments)
  $fconf = Join-Path $env:TEMP ("cyq-ftp-" + [guid]::NewGuid().ToString('N') + ".txt")
  try {
    [System.IO.File]::WriteAllText($fconf, $confCurl, (New-Object System.Text.UTF8Encoding $false))
    # --connect-timeout : sans lui, un serveur injoignable fait attendre une
    # minute avant de dire quoi que ce soit.
    $sortie = & curl.exe --silent --show-error --stderr - --connect-timeout 20 --config $fconf @Arguments
    return @{ Code = $LASTEXITCODE; Sortie = ($sortie -join "`n") }
  }
  finally {
    if (Test-Path $fconf) { Remove-Item $fconf -Force -ErrorAction SilentlyContinue }
  }
}

# Les codes de sortie de curl, traduits. Sans ça, un échec de connexion
# s'affiche « exit 67 » et n'apprend rien.
function Explique-Curl {
  param([int]$code, [string]$sortie)
  switch ($code) {
    6  { return "Serveur FTP introuvable : vérifie la ligne Serveur (sans ftp:// devant)." }
    7  { return "Connexion refusée : le serveur ne répond pas sur le port FTP." }
    9  { return "Dossier refusé ou inexistant : vérifie RacineSite / RacineApp." }
    28 { return "Délai dépassé : le serveur n'a pas répondu à temps." }
    67 { return "Identifiant ou mot de passe refusé par le serveur." }
    64 { return "Le serveur a refusé le FTP chiffré. Mets  Ftps = `$false  dans lws.config.ps1 (le mot de passe circulera alors en clair) ou demande le FTPS à LWS." }
    35 { return "Échec de la poignée de main TLS. Même piste que ci-dessus : Ftps = `$false." }
    60 { return "Le certificat du serveur ne correspond pas au nom utilisé. Mets  CertificatNonVerifie = `$true  dans lws.config.ps1 (la liaison reste chiffrée), ou reprends le nom technique du serveur donné par LWS — du genre xxx.lwspanel.com." }
    78 { return "Fichier ou dossier distant introuvable : vérifie RacineSite / RacineApp." }
    default { return $sortie }
  }
}

if ($ftps -and $certNonVerifie) {
  Write-Host "FTPS actif, sans vérification du nom du serveur (certificat LWS *.lwspanel.com)." -ForegroundColor DarkGray
} elseif (-not $ftps) {
  Write-Host "ATTENTION : FTP en clair. Le mot de passe circule sans chiffrement." -ForegroundColor Yellow
}

$base = "ftp://" + $conf.Serveur

# ------------------------------------------- repérage des dossiers -------

if ($ListRemote) {
  # Un premier appel sert de test de connexion : tant qu'il échoue, lister
  # le second dossier ne ferait que répéter la même erreur.
  $essai = Invoke-Curl @("--list-only", ($base + "/"))
  if ($essai.Code -ne 0) {
    Write-Host ""
    Write-Host ("Connexion impossible (code curl " + $essai.Code + ")") -ForegroundColor Red
    Write-Host ("  " + (Explique-Curl $essai.Code $essai.Sortie)) -ForegroundColor Red

    # Le cas le plus fréquent chez un mutualisé : le FTP chiffré n'est pas
    # proposé. On le VÉRIFIE, sans rien envoyer, et on le dit — on ne
    # bascule pas en clair tout seul, ce serait décider à ta place.
    if ($ftps) {
      $confCurl = Config-Curl $false
      $sansSsl = Invoke-Curl @("--list-only", ($base + "/"))
      $confCurl = Config-Curl $true
      if ($sansSsl.Code -eq 0) {
        Write-Host ""
        Write-Host "Diagnostic : la connexion passe SANS chiffrement, donc l'identifiant et" -ForegroundColor Yellow
        Write-Host "le mot de passe sont bons — c'est le FTPS que ce serveur refuse." -ForegroundColor Yellow
        Write-Host "Deux choix : demander l'activation du FTPS au support LWS (préférable)," -ForegroundColor Yellow
        Write-Host "ou mettre  Ftps = `$false  dans lws.config.ps1 en sachant que le" -ForegroundColor Yellow
        Write-Host "mot de passe circulera alors en clair sur le réseau." -ForegroundColor Yellow
      } else {
        Write-Host ""
        Write-Host "Sans chiffrement non plus : c'est donc le serveur, l'identifiant ou le" -ForegroundColor Yellow
        Write-Host "mot de passe. Revérifie-les dans le panneau LWS, rubrique FTP." -ForegroundColor Yellow
      }
    }
    exit 1
  }

  foreach ($d in @(@{ n = 'vitrine'; r = $conf.RacineSite }, @{ n = 'application'; r = $conf.RacineApp })) {
    $r = $d.r.TrimEnd('/')
    Write-Host ""
    Write-Host ("--- " + $d.n + " : " + $base + $r + "/")
    $res = Invoke-Curl @("--list-only", ($base + $r + "/"))
    if ($res.Code -eq 0) { Write-Host $res.Sortie }
    else { Write-Host ("  inaccessible — " + (Explique-Curl $res.Code $res.Sortie)) -ForegroundColor Red }
  }
  Write-Host ""
  Write-Host "Si le dossier de l'application n'existe pas encore : panneau LWS ->"
  Write-Host "Domaines -> Sous-domaines -> dashboard.cyqbot.eu, puis active son SSL."
  exit 0
}

# ------------------------------------------------- qui va où -------------

# La liste vit dans son propre fichier : `verser-au-depot.ps1` la lit aussi,
# et deux copies d'une même liste finissent toujours par diverger — c'est
# comme ça que `servers.css` est parti sans son CSS.
. (Join-Path $racine 'fichiers-du-site.ps1')

$cibles = @()
if ($Cible -eq 'tout' -or $Cible -eq 'site') {
  $cibles += @{ Nom = 'vitrine (cyqbot.eu)'; Racine = $conf.RacineSite.TrimEnd('/'); Fichiers = $fichiersSite }
}
if ($Cible -eq 'tout' -or $Cible -eq 'app') {
  $cibles += @{ Nom = 'application (dashboard.cyqbot.eu)'; Racine = $conf.RacineApp.TrimEnd('/'); Fichiers = $fichiersApp }
}

# Un fichier listé mais absent du dossier est une erreur de manifeste, pas
# un détail : on s'arrête avant d'envoyer un site incomplet.
$manquants = @()
foreach ($c in $cibles) {
  foreach ($f in $c.Fichiers) {
    if (-not (Test-Path (Join-Path $racine $f))) { $manquants += $f }
  }
}
if ($manquants.Count) {
  Write-Host "Fichiers introuvables sur le disque :" -ForegroundColor Red
  $manquants | Sort-Object -Unique | ForEach-Object { Write-Host ("  " + $_) -ForegroundColor Red }
  exit 1
}

# --------------------------------------------------- numéros de version ---

if (-not $NoBump) {
  & powershell -ExecutionPolicy Bypass -File (Join-Path $ici 'numeroter-versions.ps1')
  Write-Host ""
}

# ------------------------------------------------------------- envoi -----

$okTotal = 0; $ko = @()
foreach ($c in $cibles) {
  Write-Host ("=== " + $c.Nom + "  ->  " + $base + $c.Racine + "/   (" + $c.Fichiers.Count + " fichiers)")
  foreach ($rel in $c.Fichiers) {
    $local = Join-Path $racine $rel
    $urlCible = $base + $c.Racine + '/' + $rel

    if ($DryRun) { Write-Host ("  [essai] " + $rel); continue }

    $r = Invoke-Curl @("--ftp-create-dirs", "--upload-file", $local, $urlCible)
    if ($r.Code -eq 0) {
      $okTotal++
      Write-Host ("  envoyé  " + $rel)
    } else {
      $ko += ($c.Nom + " : " + $rel)
      Write-Host ("  ÉCHEC   " + $rel + " — " + (Explique-Curl $r.Code $r.Sortie)) -ForegroundColor Red
    }
  }
  Write-Host ""
}

if ($DryRun) {
  Write-Host "Essai terminé : rien n'a été envoyé."
  exit 0
}
Write-Host ("Envoyés : " + $okTotal)
if ($ko.Count) {
  Write-Host "Échecs :" -ForegroundColor Red
  $ko | ForEach-Object { Write-Host ("  " + $_) -ForegroundColor Red }
  exit 1
}
Write-Host "Ouvre https://cyqbot.eu et https://dashboard.cyqbot.eu — Ctrl+Maj+R la première fois."
Write-Host "Rappel : https://dashboard.cyqbot.eu/login.html doit être déclarée dans"
Write-Host "le portail Discord -> OAuth2 -> Redirects, sinon la connexion est refusée."
