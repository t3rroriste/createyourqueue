# =========================================================================
# cyq — la seule commande à retenir.
#
#   .\cyq amorcer      installe tout sur ce PC (à faire une fois)
#   .\cyq veille       lance la synchro continue en arrière-plan
#   .\cyq arret        arrête la veille
#   .\cyq synchro      un passage tout de suite (enregistre, récupère, pousse)
#   .\cyq publier      met en ligne maintenant : site sur LWS, bot sur AdKyNet
#   .\cyq etat         où en est tout : git, veille, dernière publication
#   .\cyq pause        la synchro continue, la mise en ligne attend
#   .\cyq reprendre    lève la pause, et lève un conflit réglé
#   .\cyq local        sert le site sur http://localhost:8765
#
# Pourquoi une seule porte d'entrée : les scripts en dessous ont des noms
# clairs mais des arguments à retenir. Ici, il n'y a qu'un verbe.
#
# Son jumeau macOS est `cyq.sh`, verbe pour verbe. Les deux appellent les
# mêmes scripts Python : il n'y a qu'une implémentation de chaque geste.
# =========================================================================

param(
  [Parameter(Position = 0)]
  [ValidateSet('amorcer', 'veille', 'arret', 'synchro', 'publier', 'etat',
               'pause', 'reprendre', 'local', 'aide')]
  [string]$Verbe = 'aide',

  # Repassés tels quels au script appelé : -Cible app, -DryRun, --intervalle 120…
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Reste
)

$ErrorActionPreference = 'Stop'
$outils = Split-Path -Parent $MyInvocation.MyCommand.Path
$racine = Split-Path -Parent $outils
$etat   = Join-Path $outils 'etat'
$pid_veille = Join-Path $etat 'veille.pid'

function Assurer-Etat { if (-not (Test-Path $etat)) { New-Item -ItemType Directory -Path $etat | Out-Null } }

# pythonw.exe lance Python SANS fenêtre : c'est ce qu'on veut pour un
# processus qui doit tourner toute la journée. S'il n'est pas là, on
# retombe sur python.exe, fenêtre réduite.
function Python-Sans-Fenetre {
  $py = (Get-Command python -ErrorAction SilentlyContinue)
  if (-not $py) { throw "Python introuvable dans le PATH. Installe-le depuis python.org, puis relance." }
  $pyw = Join-Path (Split-Path -Parent $py.Source) 'pythonw.exe'
  if (Test-Path $pyw) { return $pyw }
  return $py.Source
}

function Veille-Active {
  $n = Get-Content $pid_veille -ErrorAction SilentlyContinue
  if (-not $n) { return $null }
  $p = Get-Process -Id $n -ErrorAction SilentlyContinue
  if ($p -and $p.ProcessName -match '^python') { return $p }
  return $null
}

switch ($Verbe) {

  'amorcer' {
    & python (Join-Path $outils 'amorcer.py') @Reste
  }

  'veille' {
    $deja = Veille-Active
    if ($deja) { Write-Host ("La veille tourne déjà (processus " + $deja.Id + ")."); break }
    Assurer-Etat
    $exe = Python-Sans-Fenetre
    # Surtout pas $args : c'est une variable automatique de PowerShell.
    $argsVeille = @((Join-Path $outils 'veille.py')) + $Reste
    $p = Start-Process -FilePath $exe -ArgumentList $argsVeille -WorkingDirectory $racine `
                       -WindowStyle Hidden -PassThru
    $p.Id | Out-File -FilePath $pid_veille -Encoding ascii
    Write-Host ("Veille lancée (processus " + $p.Id + ").")
    Write-Host ("Son journal : " + (Join-Path $etat 'journal.log'))
  }

  'arret' {
    $p = Veille-Active
    if (-not $p) { Write-Host "La veille ne tourne pas."; break }
    Stop-Process -Id $p.Id
    Remove-Item $pid_veille -ErrorAction SilentlyContinue
    Write-Host "Veille arrêtée."
  }

  'synchro' {
    & python (Join-Path $outils 'veille.py') --une-fois @Reste
  }

  'publier' {
    # Une publication demandée à la main ne consulte pas la pause : si on
    # tape la commande, c'est qu'on veut publier.
    Write-Host "=== le site vers LWS ==="
    & python (Join-Path $outils 'publier_site.py') @Reste
    Write-Host ""
    Write-Host "=== le bot vers AdKyNet ==="
    & python (Join-Path $outils 'publier_bot.py')
  }

  'etat' {
    Write-Host "--- dépôt ---"
    & git -C $racine status --short --branch
    Write-Host ""
    Write-Host "--- veille ---"
    $p = Veille-Active
    if ($p) { Write-Host ("  active (processus " + $p.Id + ")") } else { Write-Host "  arrêtée" }
    if (Test-Path (Join-Path $etat 'conflit')) {
      Write-Host "  CONFLIT non réglé : rien n'est publié." -ForegroundColor Red
      Get-Content (Join-Path $etat 'conflit') -Encoding UTF8 | ForEach-Object { Write-Host ("    " + $_) }
    }
    if (Test-Path (Join-Path $etat 'pause')) { Write-Host "  publication en pause" -ForegroundColor Yellow }
    $dp = Join-Path $etat 'dernier-publie.txt'
    if (Test-Path $dp) {
      $sha = (Get-Content $dp -Raw).Trim()
      # Pas d'opérateur ternaire ici : PowerShell 5.1, livré avec Windows 10,
      # ne le connaît pas et s'arrête sur une erreur de syntaxe.
      $titre = (& git -C $racine log -1 --format='%h %s' $sha 2>$null)
      if (-not $titre) { $titre = $sha }
      Write-Host ("  dernier publié : " + $titre)
    } else {
      Write-Host "  rien n'a encore été publié depuis ce PC"
    }
    Write-Host ""
    Write-Host "--- dix dernières lignes du journal ---"
    $j = Join-Path $etat 'journal.log'
    # -Encoding UTF8 : sans lui, PowerShell 5.1 lit le journal en ANSI et
    # tous les accents ressortent en charabia.
    if (Test-Path $j) { Get-Content $j -Tail 10 -Encoding UTF8 } else { Write-Host "  (vide)" }
  }

  'pause' {
    Assurer-Etat
    Set-Content -Path (Join-Path $etat 'pause') -Value '' -Encoding ascii
    Write-Host "Publication en pause. La synchro entre les deux PC continue."
  }

  'reprendre' {
    $leve = @()
    foreach ($m in @('pause', 'conflit')) {
      $c = Join-Path $etat $m
      if (Test-Path $c) { Remove-Item $c; $leve += $m }
    }
    if ($leve.Count) { Write-Host ("Levé : " + ($leve -join ', ') + ".") }
    else { Write-Host "Il n'y avait ni pause ni conflit." }
  }

  'local' {
    # Pas `http.server` : les pages se lient par leur forme courte (/guide),
    # qu'un serveur de fichiers nu renvoie en 404. serveur_local.py rejoue
    # les règles du .htaccess, donc on essaie en local ce qui part en ligne.
    & python (Join-Path $outils 'serveur_local.py')
  }

  default {
    Get-Content (Join-Path $outils 'cyq.ps1') | Select-Object -First 17 |
      ForEach-Object { $_ -replace '^# ?', '' } | Where-Object { $_ -notmatch '^=+$' }
  }
}
