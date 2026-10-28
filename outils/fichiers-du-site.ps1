# =========================================================================
# La liste des fichiers du site, et de quel côté chacun va.
#
# Pourquoi elle vit dans son propre fichier : DEUX scripts en ont besoin —
# `publier-site.ps1` pour l'envoi FTP, `numeroter-versions.ps1` pour vérifier
# qu'aucune feuille demandée par une page n'a été oubliée. Tant que la liste
# était écrite en dur dans un seul endroit, une feuille neuve pouvait être
# ajoutée d'un côté et pas de l'autre. C'est exactement ce qui est arrivé à
# `servers.css` : la page est partie en ligne sans son CSS, et s'est affichée
# en HTML nu.
#
# Une seule liste, deux lecteurs. Ajouter un fichier au site, c'est
# l'ajouter ICI, et nulle part ailleurs.
#
# S'utilise en le sourçant :
#     . (Join-Path $ici 'fichiers-du-site.ps1')
# Il pose $commun, $fichiersSite et $fichiersApp.
# =========================================================================

# Le socle, identique des deux côtés.
$commun = @(
  '.htaccess',
  'assets/img/logo.png',
  'assets/js/app.js',
  'assets/js/config.js',
  'assets/js/lang/fr.js', 'assets/js/lang/en.js', 'assets/js/lang/es.js',
  'assets/js/lang/de.js', 'assets/js/lang/ko.js',
  'assets/js/vendor/anime.umd.min.js',
  'assets/js/vendor/anime.LICENSE.md',   # la licence MIT accompagne le code
  'assets/css/home.css'                  # la vitrine ET login/welcome s'en servent
)

# cyqbot.eu — la vitrine.
$fichiersSite = $commun + @(
  'index.html', 'guide.html', 'modules.html',
  # support.html a été écrite le 16 octobre et n'a jamais été déclarée ici :
  # elle n'est donc jamais partie en ligne, alors que index.html et
  # modules.html pointent dessus. C'est le troisième cas du même oubli.
  'support.html',
  'verif-php.php',                       # temporaire : test de l'hebergement
  'assets/css/guide.css', 'assets/css/modules.css',
  'assets/js/page-home.js', 'assets/js/page-guide.js', 'assets/js/page-modules.js'
)

# dashboard.cyqbot.eu — l'application.
$fichiersApp = $commun + @(
  'login.html', 'welcome.html', 'servers.html', 'dashboard.html',
  # app.css n'est plus chargée par aucune page depuis que le panneau est
  # passé sur home.css + dashboard.css. On la laisse partir quand même :
  # elle est inoffensive, et la retirer casserait une page qu'on y
  # ramènerait sans y penser. À supprimer le jour où on en est sûr.
  'assets/css/app.css', 'assets/css/auth.css', 'assets/css/servers.css',
  'assets/css/dashboard.css',
  'assets/js/page-login.js', 'assets/js/page-welcome.js',
  'assets/js/page-servers.js', 'assets/js/page-dashboard.js',
  # L'API elle-meme. secrets.php n'y figure pas : il se depose a la main sur
  # le serveur et ne doit jamais partir d'ici.
  'api/index.php', 'api/.htaccess', 'api/secrets.exemple.php',
  'api/data/.htaccess'
)
