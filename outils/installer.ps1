# =========================================================================
# LA commande du PC portable. Une seule, à coller dans PowerShell :
#
#   powershell -NoProfile -Command "irm https://raw.githubusercontent.com/t3rroriste/createyourqueue/main/outils/installer.ps1 | iex"
#
# Elle récupère tout — le bot Discord, le site, l'API, les outils — puis
# enchaîne sur amorcer.ps1, qui demande les identifiants et pose la veille.
#
# Ce fichier est fait pour être LU PAR LE RÉSEAU, pas lancé depuis le
# disque : il est donc enregistré sans BOM, parce qu'une BOM arrivant dans
# `iex` fait échouer l'analyse de la première ligne. Si tu le lances depuis
# le dépôt, passe plutôt par `.\cyq amorcer` : c'est la même chose, en
# mieux encodé.
# =========================================================================

$ErrorActionPreference = 'Stop'
$depot = 'https://github.com/t3rroriste/createyourqueue.git'

Write-Host ""
Write-Host "=== CreateYourQueue - installation sur ce PC ===" -ForegroundColor Cyan
Write-Host ""

# --- git est le seul prérequis de cette étape ----------------------------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "git est introuvable." -ForegroundColor Yellow
  Write-Host "Installe-le : https://git-scm.com/download/win"
  Write-Host "Puis recolle cette commande."
  return
}

# --- où ? ----------------------------------------------------------------
$defaut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'CYQ'
$cible = Read-Host "Dossier d'installation [$defaut]"
if ([string]::IsNullOrWhiteSpace($cible)) { $cible = $defaut }

if (Test-Path (Join-Path $cible '.git')) {
  Write-Host ""
  Write-Host "Le depot est deja la : on le met simplement a jour." -ForegroundColor DarkGray
  & git -C $cible pull --rebase --autostash
} elseif ((Test-Path $cible) -and (Get-ChildItem $cible -Force | Select-Object -First 1)) {
  # Cloner par-dessus un dossier qui contient déjà quelque chose, c'est le
  # bon moyen de perdre du travail sans s'en apercevoir. On refuse.
  Write-Host ""
  Write-Host "$cible existe et n'est pas vide, et ce n'est pas un depot git." -ForegroundColor Yellow
  Write-Host "Choisis un autre dossier, ou deplace celui-la, puis recommence."
  return
} else {
  Write-Host ""
  Write-Host "Recuperation du depot..." -ForegroundColor DarkGray
  & git clone $depot $cible
  if ($LASTEXITCODE -ne 0) { Write-Host "Le clone a echoue." -ForegroundColor Red; return }
}

# --- la suite est dans le dépôt ------------------------------------------
Write-Host ""
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $cible 'outils\amorcer.ps1')

Write-Host ""
Write-Host "Le projet est dans : $cible" -ForegroundColor Green
Write-Host "Ouvre-le avec :  cd `"$cible`"  puis  .\cyq etat"
