# Prompt — audit de sécurité complet

À coller dans Claude Code, à la racine du dépôt (`/Users/alexandre/Developer/CYQ`
sur le MacBook, `C:\…\CYQ` sur le PC). Tout ce qui suit la ligne de tirets est
le prompt lui-même.

Avant de le lancer, deux choses à savoir :

- **L'audit est statique.** Il lit le code, les configurations et l'historique
  git. Il ne tire pas un paquet vers `cyqbot.eu` ni vers le serveur du bot :
  ces machines appartiennent à LWS et à AdKyNet, et les scanner sans leur
  autorisation écrite est interdit par leurs conditions, quand bien même les
  comptes sont les tiens. La seule cible vivante autorisée est le serveur
  local (`./cyq local`). Si tu veux un vrai test d'intrusion en ligne, il
  faut d'abord l'accord écrit des deux hébergeurs.
- **Il ne publie qu'à un seul moment.** La correction reste dans le dépôt, en
  commits ; la mise en ligne se demande séparément, après relecture. La seule
  exception est la phase 4 : à court de contexte, il range, il vérifie, il
  commite et il publie, pour que tu puisses reprendre d'une base en ligne.

---

Tu vas mener un audit de sécurité complet de CreateYourQueue, puis corriger ce
que tu trouves. Lis d'abord `CLAUDE.md` et `README.md` : ils décrivent le dépôt,
ses garde-fous et ses pièges, et plusieurs incidents passés y sont racontés —
ils t'économiseront des hypothèses.

## Ce que couvre l'audit

Quatre morceaux, tous dans ce dépôt :

- `bot/` — le bot Discord en Python, ses cogs, et l'API HTTP qu'il ouvre pour
  le panneau web.
- `site/` — la vitrine statique, le panneau web, et `site/api/*.php`, l'API de
  production (OAuth Discord, sessions, pont des réglages).
- `api-locale/server.py` — la même API en Python, pour le développement.
- `outils/` — la synchro, la publication FTP/SFTP, le coffre à mots de passe.

Et deux choses qui ne sont pas du code mais comptent autant : le fichier
`site/.htaccess`, et **l'historique git, parce que le dépôt GitHub est public**.

## Les règles, avant tout le reste

1. **Ne lis jamais** `bot/.env`, `site/api/secrets.php`, `outils/reglages/lws.json`
   ni l'ancien `lws.config.ps1`. `.claude/settings.json` les refuse déjà ; ne
   cherche pas à contourner. Les modèles `.env.example`, `secrets.exemple.php`
   et `lws.config.exemple.ps1` documentent les champs, et c'est eux qu'on cite.
2. **N'attaque aucune machine en ligne.** Pas de scan, pas de requête de test
   vers `cyqbot.eu`, `dashboard.cyqbot.eu`, `status.cyqbot.eu` ni vers le
   serveur du bot chez AdKyNet. Si une vérification demande vraiment une cible
   vivante, monte-la en local (`./cyq local`, `.claude/launch.json`) et dis-le
   dans le rapport.
3. **Ne publie rien de ta propre initiative**, sauf dans le cas unique décrit
   en phase 4. Pas de push forcé, et jamais de redémarrage du bot.
4. **N'ajoute aucune dépendance.** Le site n'en a qu'une, anime.js, copiée dans
   `site/assets/js/vendor/`. Le bot et l'outillage sont en Python. Une
   correction qui réclame une bibliothèque nouvelle se propose dans le rapport,
   elle ne s'installe pas.
5. Si tu trouves un secret en clair quelque part — dans un fichier suivi, dans
   l'historique, dans un commentaire — **ne le recopie nulle part**, pas même
   dans le rapport. Donne le fichier, la ligne, la nature du secret, et
   « à révoquer ».

## Phase 1 — les agents, en parallèle

Déploie **six agents en lecture seule**. Aucun ne modifie un fichier : chacun
rend une liste de constats. Donne à chacun son périmètre et sa question de
départ, et dis-lui de lire `CLAUDE.md` avant de commencer.

**Agent 1 — authentification et sessions.**
`site/api/index.php` (routes `/auth/*`), `api-locale/server.py`,
`site/assets/js/page-login.js`, `site/assets/js/app.js` (les fabriques d'URL
OAuth), `site/login.html`. Le `state` est-il tiré, stocké et comparé
correctement, des deux côtés ? La comparaison est-elle à temps constant ? Le
cookie de session : `Secure`, `HttpOnly`, `SameSite`, durée, régénération de
l'identifiant après connexion ? Le flux implicite de `login.html` peut-il
servir à injecter un jeton obtenu ailleurs ? Le jeton Discord fuit-il dans une
URL, un `Referer`, un journal ? Une redirection ouverte quelque part après la
connexion ? La déconnexion invalide-t-elle vraiment la session côté serveur ?

**Agent 2 — l'API PHP de production.**
`site/api/index.php` en entier. Pour CHAQUE route : qui a le droit de
l'appeler, et le code le vérifie-t-il ? En particulier `/guilds/{id}` et
`/guilds/{id}/settings` — rien n'empêche-t-il d'écrire les réglages d'un
serveur Discord qu'on n'administre pas ? Traversée de chemin sur les
identifiants ? Validation et bornes de chaque valeur de réglage (types,
longueurs, listes fermées) ? Écritures de fichiers : chemin, permissions,
concurrence, écriture atomique ? Messages d'erreur : fuient-ils un chemin, une
version, une trace ? Y a-t-il une limite de débit, et sinon où elle manque.

**Agent 3 — le bot et son API HTTP.**
`bot/bot.py`, `bot/cogs/*.py`. L'API du bot : comment la clé
`DASHBOARD_API_KEY` est-elle comparée (égalité naïve ou temps constant ?), sur
quelle interface le port écoute-t-il, que peut-on faire sans clé ? Les
commandes : chaque commande sensible vérifie-t-elle les permissions Discord de
qui l'appelle, et pas seulement l'affichage du bouton ? Injection dans les
embeds et les noms de salons créés (mentions `@everyone`/`@here`, markdown,
caractères de contrôle) ? Les écritures dans `bot/data/` : un identifiant de
serveur peut-il sortir du dossier ? Désérialisation de JSON écrit par le
panneau : que se passe-t-il si le fichier est hostile ou corrompu ? Et les
boucles qui envoient des messages : peut-on les faire marteler Discord ?

**Agent 4 — le front et le panneau.**
`site/assets/js/page-dashboard*.js`, `page-servers.js`, `app.js`, et les pages.
Chaque `innerHTML` : la donnée qui y entre passe-t-elle par `esc()` ? Les noms
de serveurs, de salons, de rôles et les pseudos viennent de Discord et sont
hostiles par principe. Les `href` construits à l'exécution peuvent-ils porter
un `javascript:` ? `config.js` est public : contient-il quelque chose qui n'a
rien à y faire ? Manque-t-il une CSP, `X-Content-Type-Options`,
`Referrer-Policy`, `X-Frame-Options` ? Le site est-il encadrable dans une
iframe ?

**Agent 5 — infrastructure, secrets et historique.**
`site/.htaccess` : les fichiers sensibles sont-ils servis par Apache
(`.env`, `secrets.php`, `*.json` de réglages, `.git`) ? Le listage de
répertoire est-il coupé ? Les réécritures peuvent-elles être détournées pour
servir un fichier hors du dossier prévu ? Puis l'outillage : `outils/` — le
coffre (`secrets_locaux.py`, `coffre.py`), la publication FTP (le FTP de LWS
est-il en clair ?), ce que `journal.log` écrit. Enfin **l'historique git** :
cherche tout ce qui ressemble à un jeton Discord, une clé, un mot de passe ou
une URL de webhook dans les commits passés, y compris dans des fichiers depuis
supprimés — le dépôt est public, un secret poussé une fois y reste. Signale,
ne recopie pas.

**Agent 6 — dépendances et chaîne d'approvisionnement.**
Les dépendances Python du bot et de l'outillage : versions épinglées ? CVE
connues pour les versions utilisées ? La copie d'anime.js dans
`site/assets/js/vendor/` correspond-elle bien à la version annoncée en amont ?
Les workflows GitHub, s'il y en a : secrets exposés, actions non épinglées ?
Le `contact.php` de la vitrine : qui peut l'appeler, et combien de fois ?

Chaque agent rend ses constats sous cette forme, et rien d'autre :

```
[CRITIQUE|ÉLEVÉ|MOYEN|FAIBLE] titre court
  Où       fichier:ligne
  Quoi     ce que le code fait, en une phrase
  Scénario comment on en abuse concrètement, pas en théorie
  Correctif ce qu'il faut changer, précisément
```

Pas de constat sans scénario d'abus concret. Une bonne pratique manquante dont
personne ne sait quoi faire n'est pas une faille : range-la en FAIBLE et dis
pourquoi elle compte ici.

## Phase 2 — le rapport

Rassemble tout dans `docs/AUDIT-SECURITE.md` : les doublons fusionnés, les
constats classés par gravité, et en tête un tableau de synthèse. Pour chaque
constat, garde le scénario d'abus — c'est lui qui permettra de décider.
Ajoute une section « ce que je n'ai pas pu vérifier », honnête : ce qui
demanderait une cible vivante, l'accès au panneau de l'hébergeur, ou un secret.

Montre-moi ce rapport **avant** de corriger quoi que ce soit.

## Phase 3 — la correction

Une fois le rapport validé, corrige dans cet ordre : CRITIQUE, puis ÉLEVÉ, puis
MOYEN. Un commit par thème, jamais un commit fourre-tout.

Les garde-fous du dépôt restent valables pendant la correction :

- Commentaires **en français**, et ils expliquent le *pourquoi* d'une valeur.
  Ne retire jamais un commentaire existant pour « nettoyer ».
- Un texte visible passe par `data-i18n` et les cinq fichiers de langue
  (`python outils/verifier_langues.py --completer`).
- La nav et le pied se modifient dans `outils/communs/`, jamais dans une page.
- Un fichier neuf se déclare dans `outils/fichiers_du_site.py`.
- Une route ou un réglage touché : vérifie les DEUX implémentations, PHP et
  Python, et le pont `PONT_*` (`python outils/verifier_api.py`).
- Après toute modification de CSS ou de JS :
  `python outils/numeroter_versions.py`.
- À la fin : `./cyq verifier` doit passer les trois relevés.

Et vérifie ce que tu corriges : sers le site en local, ouvre la page, regarde
la console, teste le cas d'abus décrit dans le constat et montre qu'il ne
marche plus. Dis ensuite ce que tu as vérifié et ce que tu n'as pas pu
vérifier.

## Phase 4 — quand tu arrives à court de contexte

Cet audit est long, et tu n'iras probablement pas au bout d'une traite.
**Quand il te reste moins de 15 % de contexte, arrête-toi de toi-même.**
N'attends pas d'être au bout : à 5 %, tu n'as plus la place de ranger
derrière toi.

Dans cet ordre, et l'ordre compte :

1. **Tu n'ouvres plus rien.** Pas de nouvel agent, pas de nouveau constat,
   pas de correction commencée.
2. **Tu rends le dépôt cohérent.** Une correction à moitié appliquée, tu la
   défais (`git checkout --` sur ses fichiers) plutôt que de la laisser. Du
   code de sécurité à demi écrit est plus dangereux que pas de correction du
   tout : il donne l'illusion que le trou est bouché.
3. **Tu fais passer les contrôles.** `python outils/numeroter_versions.py` si
   tu as touché du CSS ou du JS, puis `./cyq verifier` — les trois relevés
   doivent passer. S'ils ne passent pas, tu répares ça AVANT tout le reste.
4. **Tu écris la reprise dans `docs/AUDIT-SECURITE.md`**, avant de publier :
   l'état de chaque constat, où tu t'es arrêté exactement, et le premier
   geste à faire au retour. Si tu tombes en panne pendant la publication, je
   veux que cette note existe déjà.
5. **Tu commites**, avec un message qui dit où en est l'audit.
6. **Puis tu publies** : `./cyq publier`. C'est une autorisation donnée ici,
   d'avance, et elle ne vaut QUE pour ce cas-là — à court de contexte, après
   les cinq étapes ci-dessus. Pas pour publier au fil de l'eau.
7. **Tu finis par trois lignes** : ce qui est en ligne, ce qui ne l'est pas,
   et la commande pour reprendre.

Deux choses à savoir sur cette publication :

- **Le site part tout de suite, le bot non.** `publier_site.py` envoie chez
  LWS et c'est en ligne. `publier_bot.py` dépose les fichiers chez AdKyNet,
  mais le bot qui tourne garde son ancien code jusqu'à
  `python outils/redemarrer_bot.py`. **Ne le redémarre pas** : laisse-moi ce
  geste. Il refuse de couper une queue en cours, et je préfère choisir le
  moment.
- **Aucune publication n'emporte les secrets.** `bot/.env` et
  `site/api/secrets.php` ne sont dans aucune liste d'envoi, délibérément.
  Tu n'as rien à faire de ce côté.

Et la règle qui passe avant « vite » : **tu ne publies jamais ce que tu n'as
pas vérifié**. Si au moment de t'arrêter la dernière correction n'est pas
testée, tu la défais et tu publies sans elle. Publier vite, ce n'est pas
publier n'importe quoi — une faille non corrigée me laisse là où j'étais, un
site cassé me met plus bas.

## Ce que j'attends à la fin

Le rapport `docs/AUDIT-SECURITE.md` à jour, avec l'état de chaque constat
(corrigé, en attente, écarté et pourquoi), les commits de correction, et une
liste courte de ce qui reste à faire **à la main** de mon côté : un secret à
révoquer, un réglage à changer dans le panneau d'un hébergeur, une permission
Discord à réduire.
