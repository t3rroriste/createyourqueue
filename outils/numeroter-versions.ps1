# Renumérote tous les assets (?v=…) des pages HTML.
#
# Pourquoi : le navigateur garde en cache app.css, app.js et les fichiers de
# langue. Sans ce numéro, on modifie un fichier, on recharge… et on voit
# l'ancienne version. Le numéro change -> l'URL change -> le navigateur
# retélécharge. C'est le seul moyen fiable sur un site sans build.
#
# À lancer après chaque modification de CSS ou de JS, avant d'envoyer le
# dossier à l'hébergeur :
#
#     powershell -File outils/numeroter-versions.ps1
#     powershell -File outils/numeroter-versions.ps1 -Dossier autre

param(
  # Le dossier dont on renumérote les pages. Par défaut `site/`, le seul
  # dossier servi. Le paramètre reste là pour traiter une copie (un essai,
  # un instantané d'archive) sans toucher au site de travail.
  [string]$Dossier
)

$ErrorActionPreference = 'Stop'
$ici    = Split-Path -Parent $MyInvocation.MyCommand.Path
$leSite = Join-Path (Split-Path -Parent $ici) 'site'
$racine = if ($Dossier) { (Resolve-Path $Dossier).Path } else { $leSite }
$version = Get-Date -Format 'yyyyMMddHHmm'

$pages = Get-ChildItem -Path $racine -Filter '*.html' -File

foreach ($page in $pages) {
  $texte = Get-Content -Path $page.FullName -Raw -Encoding UTF8
  $avant = $texte

  # href="assets/…​.css" et src="assets/….js", avec ou sans ?v= existant
  $texte = [regex]::Replace($texte,
    '(href="assets/[^"?]+\.css)(\?v=[^"]*)?"', ('${1}?v=' + $version + '"'))
  $texte = [regex]::Replace($texte,
    '(src="assets/[^"?]+\.js)(\?v=[^"]*)?"',  ('${1}?v=' + $version + '"'))

  if ($texte -ne $avant) {
    [System.IO.File]::WriteAllText($page.FullName, $texte, (New-Object System.Text.UTF8Encoding $false))
    Write-Host ("  mis a jour : " + $page.Name)
  } else {
    Write-Host ("  inchange   : " + $page.Name)
  }
}

Write-Host ""
Write-Host ("Version des assets : " + $version)
Write-Host "Recharge la page une fois avec Ctrl+Maj+R, puis envoie le dossier."

# ------------------------------------------- le fichier oublie -----------
#
# Deux fois de suite, une feuille NEUVE est partie en ligne sans etre
# declaree : servers.css, puis dashboard.css. Les deux fois, la page s'est
# affichee en HTML nu en production, et les deux fois on ne l'a vu qu'une
# fois en ligne.
#
# La cause est toujours la meme : la liste d'envoi est ecrite a la main, et
# personne ne pense a l'ouvrir en creant un fichier. Ce controle la compare
# a ce que les pages demandent REELLEMENT. Il tourne ici parce que ce script
# est lance apres chaque modification de CSS ou de JS — c'est-a-dire
# precisement quand un fichier neuf vient d'apparaitre.
#
# Il AVERTIT, il ne bloque pas : renumeroter reste utile meme si la liste
# est incomplete, et un script de cache n'a pas a refuser de travailler.

$liste = Join-Path $ici 'fichiers-du-site.ps1'

if ((Test-Path $liste) -and ($racine -eq $leSite)) {
  . $liste
  $declares = @($commun + $fichiersSite + $fichiersApp) | Select-Object -Unique
  $oublies = @()

  foreach ($page in $pages) {
    $texte = Get-Content -Path $page.FullName -Raw -Encoding UTF8
    foreach ($m in [regex]::Matches($texte, '(?:href|src)="(assets/[^"?]+)')) {
      $a = $m.Groups[1].Value
      if ($declares -notcontains $a) {
        $oublies += ($a + "   (demande par " + $page.Name + ")")
      }
    }
  }

  $oublies = $oublies | Select-Object -Unique
  if ($oublies.Count) {
    Write-Host ""
    Write-Host "ATTENTION — ces fichiers sont demandes par une page mais NE PARTIRONT PAS :" -ForegroundColor Red
    $oublies | ForEach-Object { Write-Host ("  " + $_) -ForegroundColor Red }
    Write-Host "Ajoute-les a fichiers-du-site.ps1, sinon la page s'affichera sans style en ligne." -ForegroundColor Red
  }
}
