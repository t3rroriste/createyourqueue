"""
La liste des fichiers du site, et de quel côté chacun va.
=========================================================
Elle vit dans son propre fichier parce que PLUSIEURS outils en ont besoin :
`publier_site.py` pour l'envoi FTP, `numeroter_versions.py` pour vérifier
qu'aucune feuille demandée par une page n'a été oubliée. Tant que la liste
était écrite en dur dans un seul endroit, un fichier neuf pouvait être
ajouté d'un côté et pas de l'autre. C'est exactement ce qui est arrivé à
`servers.css`, puis à `dashboard.css` : la page est partie en ligne sans son
CSS et s'est affichée en HTML nu. Puis à `support.html`, qui n'est jamais
partie du tout.

Une seule liste, plusieurs lecteurs. Ajouter un fichier au site, c'est
l'ajouter ICI, et nulle part ailleurs.

En Python et non en PowerShell depuis que le second PC est un MacBook : les
deux machines lisent la même liste, et il n'y a pas deux versions à tenir
alignées.
"""

# Le socle, identique des deux côtés.
COMMUN = [
    ".htaccess",
    "assets/img/logo.png",
    "assets/js/app.js",
    "assets/js/config.js",
    "assets/js/lang/fr.js", "assets/js/lang/en.js", "assets/js/lang/es.js",
    "assets/js/lang/de.js", "assets/js/lang/ko.js",
    "assets/js/vendor/anime.umd.min.js",
    "assets/js/vendor/anime.LICENSE.md",   # la licence MIT accompagne le code
    "assets/css/home.css",                 # la vitrine ET login/welcome s'en servent
]

# cyqbot.eu — la vitrine.
VITRINE = COMMUN + [
    "index.html", "guide.html", "modules.html",
    # support.html a été écrite le 16 octobre et n'a jamais été déclarée :
    # elle n'est donc jamais partie en ligne, alors que index.html et
    # modules.html pointent dessus. C'est le troisième cas du même oubli.
    "support.html",
    "verif-php.php",                       # temporaire : test de l'hébergement
    # L'envoi du formulaire de support. Il est du côté VITRINE et pas dans
    # api/ parce que support.html est une page de la vitrine, et que l'API du
    # panneau ne pose aucun en-tête CORS — un appel d'une origine à l'autre
    # serait refusé par le navigateur. Le fichier vit donc à côté de la page
    # qui l'appelle. Rien à y déposer à la main : il ne contient aucun secret,
    # l'adresse de destination est écrite sur la page de toute façon.
    "contact.php",
    "assets/css/guide.css", "assets/css/modules.css", "assets/css/support.css",
    "assets/js/page-home.js", "assets/js/page-guide.js", "assets/js/page-modules.js",
    # page-support.js existait depuis le 16 octobre sans jamais être déclarée
    # — et sans être chargée par personne, support.html appelant
    # page-modules.js. Quatrième cas du même oubli.
    "assets/js/page-support.js",
]

# dashboard.cyqbot.eu — l'application.
APPLICATION = COMMUN + [
    "login.html", "welcome.html", "servers.html", "dashboard.html",
    # app.css n'est plus chargée par aucune page depuis que le panneau est
    # passé sur home.css + dashboard.css. On la laisse partir quand même :
    # elle est inoffensive, et la retirer casserait une page qu'on y
    # ramènerait sans y penser. À supprimer le jour où on en est sûr.
    "assets/css/app.css", "assets/css/auth.css", "assets/css/servers.css",
    "assets/css/dashboard.css",
    "assets/js/page-login.js", "assets/js/page-welcome.js",
    "assets/js/page-servers.js", "assets/js/page-dashboard.js",
    # La mémoire du bot : historique, statistiques, accès, journal,
    # palmarès. À part de page-dashboard.js, qui ne partage ni son
    # état ni son mécanisme d'enregistrement.
    "assets/js/page-dashboard-memoire.js",
    # L'API elle-même. secrets.php n'y figure pas : il se dépose à la main
    # sur le serveur et ne doit jamais partir d'ici.
    "api/index.php", "api/.htaccess", "api/secrets.exemple.php",
    "api/data/.htaccess",
]

# status.cyqbot.eu — la page d'état.
#
# Le sous-domaine a sa propre racine chez LWS, et il n'y reçoit QUE de quoi
# répondre à une question : est-ce que le bot marche. Pas de panneau, pas
# d'OAuth, pas d'anime.js — c'est la page qu'on ouvre quand quelque chose
# est cassé, elle ne doit dépendre de rien.
#
# status.html part sous ce nom et c'est DirectoryIndex, dans .htaccess, qui
# en fait la porte d'entrée du sous-domaine. Les fichiers vivent donc tous
# à leur place habituelle dans `site/` : la page s'essaie en local comme
# n'importe quelle autre, sans dossier à part et sans chemin à traduire.
#
# etat.secrets.php n'y figure pas : comme api/secrets.php, il se dépose à
# la main sur le serveur et ne doit jamais partir d'ici.
STATUT = COMMUN + [
    "status.html",
    "assets/css/status.css",
    "assets/js/page-status.js",
    # La mesure, côté serveur : c'est elle qui détient la clé de l'API du
    # bot, pour qu'elle ne soit pas dans le JavaScript de la page.
    "etat.php",
    "etat.secrets.exemple.php",
    "etat-cache/.htaccess",
]

# Tout ce qui est déclaré, sans doublon — ce que lit le contrôle des oublis.
DECLARES = sorted(set(VITRINE) | set(APPLICATION) | set(STATUT))
