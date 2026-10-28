# Réglages de mise en ligne — copie ce fichier sous le nom
# « deploy-lws.config.ps1 » et remplis les quatre valeurs.
#
# Où les trouver : panneau client LWS -> ton hébergement -> « FTP ».
# Le mot de passe ne se met PAS ici : le script le demande, ou le lit dans
# la variable d'environnement LWS_FTP_PASS.

@{
  # Serveur FTP indiqué par LWS. Souvent ftp.cyqbot.eu, parfois
  # ftp.lwsXX.fr ou une adresse IP. Un seul compte FTP sert les deux
  # domaines : ce sont deux dossiers du même hébergement.
  Serveur = 'ftp.cyqbot.eu'

  # Identifiant FTP du compte.
  Utilisateur = 'cyqbot'

  # Dossier public de cyqbot.eu — la vitrine. index.html doit arriver à sa
  # racine. Chez LWS c'est très souvent « / » ou « /htdocs ».
  RacineSite = '/'

  # Dossier public de dashboard.cyqbot.eu — l'application. C'est LWS qui le
  # crée quand tu ajoutes le sous-domaine (panneau -> Domaines ->
  # Sous-domaines) : il te demande un dossier, souvent « /dashboard » ou
  # « /subdomains/dashboard ». Recopie ici exactement celui que tu as donné.
  RacineApp = '/dashboard'

  # Dans le doute sur l'un ou l'autre :
  #   powershell -ExecutionPolicy Bypass -File deploy-lws.ps1 -ListRemote
  # liste les deux dossiers sans rien envoyer.

  # FTP chiffré (FTPS explicite). Laisse $true ; passe à $false seulement
  # si l'hébergeur le refuse — le mot de passe circulerait alors en clair.
  Ftps = $true

  # Chez LWS, le certificat du serveur FTP est émis pour leur nom technique
  # (*.lwspanel.com) et pas pour ton domaine : curl refuse alors de valider
  # le nom et s'arrête (code 60). $true chiffre quand même, sans vérifier
  # l'identité du serveur. Pour une vérification complète, mets le nom
  # technique du serveur (visible dans le panneau LWS) dans Serveur, et
  # repasse cette ligne à $false.
  CertificatNonVerifie = $true
}
