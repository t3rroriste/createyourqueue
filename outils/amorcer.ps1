# =========================================================================
# amorcer — prépare CE PC à travailler sur CYQ. À lancer une fois.
#
#     .\cyq amorcer
#
# Ce qu'il fait, dans cet ordre :
#
#   1. vérifie git et Python, et le dit clairement s'il en manque un ;
#   2. installe les dépendances du bot, plus paramiko (l'envoi SFTP) ;
#   3. demande les identifiants qui ne sont PAS dans le dépôt — ils n'y
#      seront jamais : le dépôt est public ;
#   4. pose la veille au démarrage de Windows ;
#   5. cale la référence de publication sur l'état actuel, pour qu'un
#      premier passage n'envoie pas tout le projet sur les hébergeurs.
#
# Le point 5 n'est pas un détail. Sans lui, la première veille d'un PC
# fraîchement cloné considère que RIEN n'a jamais été publié, et pousse les
# trois cents fichiers du bot sur AdKyNet — en écrasant ce que le serveur
# aurait de plus récent. On part donc du principe que l'hébergeur est à
# jour, et on ne publie que ce qui change APRÈS l'installation.
# =========================================================================

param(
  [switch]$SansDemarrage,   # ne pose pas la veille au démarrage de Windows
  [switch]$SansDependances  # ne lance pas pip
)

$ErrorActionPreference = 'Stop'
$outils   = Split-Path -Parent $MyInvocation.MyCommand.Path
$racine   = Split-Path -Parent $outils
$reglages = Join-Path $outils 'reglages'
$etat     = Join-Path $outils 'etat'

function Titre { param([string]$t) Write-Host ""; Write-Host ("--- " + $t) -ForegroundColor Cyan }
function Bien  { param([string]$t) Write-Host ("  ok    " + $t) -ForegroundColor DarkGray }
function Note  { param([string]$t) Write-Host ("  ->    " + $t) }
function Souci { param([string]$t) Write-Host ("  !     " + $t) -ForegroundColor Yellow }

if (-not (Test-Path $etat)) { New-Item -ItemType Directory -Path $etat | Out-Null }

# ------------------------------------------------------- 1. les outils ---

Titre "git et Python"
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) { Bien ("git  " + (& git --version)) }
else {
  Souci "git est introuvable. Installe-le : https://git-scm.com/download/win"
  Souci "Puis relance .\cyq amorcer."
  exit 1
}
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) { Bien ("python  " + (& python --version 2>&1)) }
else {
  Souci "Python est introuvable. Installe-le : https://www.python.org/downloads/"
  Souci "Coche « Add python.exe to PATH » pendant l'installation, puis relance."
  exit 1
}

# ------------------------------------------------ 2. les dépendances ------

if (-not $SansDependances) {
  Titre "dépendances"
  $req = Join-Path $racine 'bot\requirements.txt'
  if (Test-Path $req) {
    & python -m pip install --quiet --disable-pip-version-check -r $req
    Bien "bot/requirements.txt"
  }
  # paramiko n'est pas dans requirements.txt : le bot n'en a pas besoin pour
  # tourner, c'est l'outil de publication qui s'en sert. Il n'a donc rien à
  # faire dans les dépendances envoyées sur l'hébergeur.
  & python -m pip install --quiet --disable-pip-version-check paramiko
  Bien "paramiko (envoi SFTP vers AdKyNet)"
}

# -------------------------------------------------- 3. les identifiants ---

Titre "identifiants (jamais dans le dépôt)"

# --- LWS, pour le site
$conf = Join-Path $reglages 'lws.config.ps1'
if (Test-Path $conf) {
  Bien "réglages FTP de LWS déjà en place"
} else {
  Note "Réglages FTP de LWS. Panneau client LWS -> ton hébergement -> rubrique FTP."
  $serveur = Read-Host "  Serveur FTP (sans ftp:// devant)"
  $utilisateur = Read-Host "  Identifiant FTP"
  $racineSite = Read-Host "  Dossier de la vitrine cyqbot.eu (ex: /cyqbot.eu)"
  $racineApp  = Read-Host "  Dossier du panneau dashboard.cyqbot.eu (ex: /dashboard.cyqbot.eu)"
  @"
# Réglages FTP de LWS. Ce fichier n'est PAS versionné (voir .gitignore).
@{
  Serveur     = '$serveur'
  Utilisateur = '$utilisateur'
  RacineSite  = '$racineSite'
  RacineApp   = '$racineApp'
  Ftps        = `$true
  # Le certificat de LWS est valide mais émis pour *.lwspanel.com : sans
  # cette ligne, curl s'arrête sur le nom qui ne correspond pas. La liaison
  # reste chiffrée, c'est l'identité du serveur qui n'est plus vérifiée.
  CertificatNonVerifie = `$true
}
"@ | Set-Content -Path $conf -Encoding UTF8
  Bien "outils/reglages/lws.config.ps1 écrit"
}

$pass = Join-Path $reglages 'lws.pass'
if (Test-Path $pass) {
  Bien "mot de passe FTP déjà retenu sur ce compte Windows"
} else {
  Note "Mot de passe FTP (chiffré par Windows pour TON compte, sur CE PC)."
  $s = Read-Host "  Mot de passe FTP (vide pour le saisir à chaque envoi)" -AsSecureString
  if ($s.Length -gt 0) {
    $s | ConvertFrom-SecureString | Set-Content -Path $pass -Encoding ascii
    Bien "retenu dans outils/reglages/lws.pass"
  } else {
    Souci "non retenu : il sera demandé à chaque publication du site"
  }
}

# --- AdKyNet, pour le bot
if ([Environment]::GetEnvironmentVariable('ADKYNET_SFTP_PASSWORD', 'User')) {
  Bien "mot de passe SFTP d'AdKyNet déjà enregistré"
} else {
  Note "Mot de passe SFTP d'AdKyNet (panneau Pterodactyl -> Settings -> SFTP)."
  $s = Read-Host "  Mot de passe SFTP (vide pour plus tard)" -AsSecureString
  if ($s.Length -gt 0) {
    # Pas `setx` : il tronque sur certains caractères spéciaux, et on passe
    # ensuite une heure à chercher pourquoi le serveur refuse un mot de
    # passe pourtant juste.
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try {
      $clair = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
      [Environment]::SetEnvironmentVariable('ADKYNET_SFTP_PASSWORD', $clair, 'User')
    } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
    Bien "enregistré dans tes variables d'environnement"
    Souci "les terminaux DÉJÀ ouverts ne le voient pas — rouvre-en un"
  } else {
    Souci "non enregistré : la publication du bot sera ignorée jusque-là"
  }
}

# --- Le .env du bot : des jetons, pas des mots de passe. On ne les demande
#     pas un par un, on ouvre le fichier et on laisse remplir.
$env_bot = Join-Path $racine 'bot\.env'
if (Test-Path $env_bot) {
  Bien "bot/.env en place"
} else {
  $modele = Join-Path $racine 'bot\.env.example'
  if (Test-Path $modele) {
    Copy-Item $modele $env_bot
    Souci "bot/.env créé depuis le modèle — il faut y mettre les jetons Discord"
    Note "Je l'ouvre dans le Bloc-notes : remplis-le, enregistre, ferme."
    Start-Process notepad.exe $env_bot -Wait
  }
}

# --- secrets.php : il vit sur le serveur LWS, pas ici. On le signale.
$secrets = Join-Path $racine 'site\api\secrets.php'
if (-not (Test-Path $secrets)) {
  Souci "site/api/secrets.php absent : nécessaire seulement pour tester l'API PHP en local"
  Note  "Modèle : site/api/secrets.exemple.php. En production, il est déjà sur LWS."
}

# ------------------------------------------------- 4. veille au démarrage ---

if (-not $SansDemarrage) {
  Titre "veille au démarrage de Windows"
  $demarrage = [Environment]::GetFolderPath('Startup')
  $raccourci = Join-Path $demarrage 'CYQ-veille.cmd'
  @"
@echo off
rem Lance la veille CYQ a l'ouverture de la session, sans fenetre.
rem Pose par outils\amorcer.ps1 ; supprime ce fichier pour l'arreter.
powershell -NoProfile -ExecutionPolicy Bypass -File "$outils\cyq.ps1" veille
"@ | Set-Content -Path $raccourci -Encoding ascii
  Bien ("posé : " + $raccourci)
}

# -------------------------------------- 5. référence de publication -------

Titre "référence de publication"
$dp = Join-Path $etat 'dernier-publie.txt'
if (Test-Path $dp) {
  Bien "déjà calée"
} else {
  $tete = (& git -C $racine rev-parse HEAD).Trim()
  Set-Content -Path $dp -Value $tete -Encoding ascii
  Bien ("calée sur " + $tete.Substring(0, 8) + " : seules les modifications À VENIR seront publiées")
  Note "Avant un premier envoi complet du bot, vérifie ce que le serveur a en plus :"
  Note "  python outils/publier-bot.py --comparer"
}

Write-Host ""
Write-Host "Terminé. La suite :" -ForegroundColor Green
Write-Host "  .\cyq veille     lance la synchro continue"
Write-Host "  .\cyq etat       où en est tout"
Write-Host "  .\cyq local      sert le site sur http://localhost:8765"
