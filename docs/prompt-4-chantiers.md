# Prompt pour Claude Code — 4 chantiers CreateYourQueue

> Copie tout ce qui suit la ligne de séparation dans Claude Code.

---

Quatre chantiers sur CreateYourQueue. Lis `CLAUDE.md` avant de commencer : ses
règles (pas de dépendance nouvelle, commentaires en français qui expliquent le
*pourquoi*, i18n sur les cinq langues, aucune donnée inventée, jamais de
publication de ta propre initiative) s'appliquent à tout ce qui suit.

**Méthode attendue.** Traite les chantiers **dans l'ordre**. Pour chacun :
diagnostique d'abord en lisant le code réel — ne crois pas sur parole le
repérage ci-dessous, il vient d'une lecture rapide et peut être incomplet —,
dis ce que tu as trouvé, puis corrige. Après chaque chantier, montre le diff
et ce que tu as vérifié. Les chantiers 3 et 4 sont des bugs : trouve la cause,
ne masque pas le symptôme.

**Garde-fous.** Ne touche pas à `archives/`. Ne lis ni ne recopie `bot/.env`,
`site/api/secrets.php`, `outils/reglages/lws.json`. Ne lance aucune
publication (`cyq publier`, `outils/publier_*.py`). Après toute modification de
CSS ou de JS : `python outils/numeroter_versions.py`. Tout fichier neuf doit
être déclaré dans `outils/fichiers_du_site.py`, sinon il ne part jamais en
ligne.

---

## Chantier 1 — l'accueil doit défiler d'un seul tenant

**Le symptôme.** En descendant sur `site/index.html`, les modules arrivent
comme une « nouvelle fenêtre » qui recouvre le héros. Je veux une seule page
continue : le héros, puis les modules à la suite, sans effet de panneau qui
glisse par-dessus et sans qu'un module occupe tout l'écran.

**Le repérage.**

- `site/assets/css/home.css` : `.hero { position: sticky; top: 0; z-index: 1 }`
  et `.hero__in { min-height: calc(100dvh - …); border-radius: … }` — c'est ce
  couple qui épingle le héros et fait glisser la suite par-dessus lui.
- `site/index.html` : la div `.homemods` existe **uniquement** pour servir de
  calque au-dessus du héros épinglé (son commentaire le dit). Si le héros
  cesse d'être `sticky`, cette enveloppe perd sa raison d'être.
- `site/assets/css/modules.css` : `.mod { min-height: 100dvh }` — chaque module
  occupe un écran entier. C'est la deuxième moitié de l'effet « une fenêtre par
  module ».
- `site/assets/js/page-home.js` (bloc `modules()`, ~l.181-275) : la révélation
  au défilement, avec son écouteur `scroll` et son commentaire qui explique
  pourquoi ce n'est pas un `IntersectionObserver`. **Garde la révélation** —
  elle n'est pas le problème — mais vérifie qu'elle fonctionne encore quand la
  hauteur des sections change.

**Attendu.**

- Un seul flux de défilement, sans couche qui recouvre le héros.
- Les modules s'enchaînent avec un rythme vertical lisible (filets, espacement),
  pas en plein écran chacun.
- Décide et explique ce que devient `.homemods` : retirée, ou gardée en simple
  conteneur sans rôle de calque.
- `site/modules.html` utilise la même `modules.css`. Dis explicitement si ta
  modification change cette page, et si oui, est-ce voulu. Si tu veux les
  découpler, fais-le par une classe sur l'accueil, pas en dupliquant le CSS.
- Animations en `transform` et `opacity` seulement. Variante calme sous
  `prefers-reduced-motion: reduce`, et `?motion=on` force toujours l'animation.
- Si anime.js ne charge pas, la page reste lisible : les états de départ
  restent posés en JS, jamais en CSS.

---

## Chantier 2 — une vraie page Support

**L'état actuel.** `site/support.html` est un copier-coller de `modules.html` :
elle affiche le titre et la maquette des modules, charge `page-modules.js`, et
`page-support.js` existe mais **n'est référencée par aucune page** et **n'est
pas déclarée** dans `outils/fichiers_du_site.py` (contrôle-le). La ligne 3 du
fichier contient en plus un `<script src="/___vscode_livepreview_injected_script">`
injecté par VS Code : retire-le.

**Ce que je veux sur cette page.**

1. Un **formulaire de contact** qui envoie un message à `contact@cyqbot.eu` :
   nom, adresse de réponse, sujet, message. Validation côté client, états
   d'envoi / de succès / d'échec visibles, et un message d'erreur honnête
   quand ça échoue.
2. Un bloc **serveur Discord de support** : le lien vient de `SUPPORT_URL`
   dans `site/assets/js/config.js` (actuellement `'#'`, et le lien « Support »
   de la nav porte déjà `data-cfg-link="SUPPORT_URL"`). Tant que la valeur
   vaut `'#'`, la page doit le dire plutôt que d'offrir un lien mort — c'est
   la règle « aucune donnée inventée ».

**La question à trancher avant d'écrire.** LWS n'exécute que du PHP, et il n'y
a aujourd'hui **aucune** infrastructure d'envoi de courrier dans le dépôt
(`grep` sur `mail(` ne renvoie rien). Deux chemins :

- **(a) `mailto:`** — zéro back-end, le formulaire prépare le message dans le
  client de messagerie du visiteur. Simple, mais ce n'est pas vraiment un
  envoi, et ça casse pour qui n'a pas de client configuré.
- **(b) un point d'entrée PHP** (`site/api/contact.php` ou une route de
  `site/api/index.php`) qui envoie réellement. Il lui faut alors : limite de
  débit par IP, piège à robots (champ honeypot, pas de CAPTCHA), longueurs
  bornées, en-têtes assainis contre l'injection, `Reply-To` sur l'adresse
  saisie, réponses JSON avec les mêmes codes d'erreur que le reste de l'API.

**Pars sur (b)** et fais fonctionner (a) en repli automatique si le point
d'entrée répond une erreur ou si `API_BASE` est vide — le site doit rester
utilisable sans back-end, comme partout ailleurs. Si en lisant le code tu
estimes que (b) ne tient pas sur LWS, arrête-toi et explique pourquoi avant
d'écrire.

**Les obligations de la page.**

- La direction artistique de la vitrine : `home.css`, jamais un token du
  panneau. Les clés `sp.*` existent déjà dans `site/assets/js/lang/fr.js`
  (l.317-327) et dans `ko.js`, **mais pas dans `en.js`, `es.js`, `de.js`** —
  complète les cinq, et ajoute-y les clés neuves du formulaire.
- Tout texte visible passe par `data-i18n`.
- La page charge `page-support.js`, pas `page-modules.js`. Adapte le script :
  il est aujourd'hui une copie de celui des modules.
- Déclare dans `outils/fichiers_du_site.py` tout fichier neuf **et**
  `assets/js/page-support.js`, qui y manque. Puis lance
  `python outils/numeroter_versions.py` et vérifie qu'il ne signale plus de
  fichier non déclaré.
- Accessibilité : `<label>` pour chaque champ, erreurs annoncées en
  `aria-live`, navigation au clavier complète.

---

## Chantier 3 — changer la langue dans le panneau ne change pas la langue du bot

**Le symptôme.** Je choisis une langue dans le dashboard, elle est enregistrée,
mais sur Discord le bot continue de parler l'ancienne.

**Le chemin complet, à vérifier maillon par maillon.**

1. `site/dashboard.html` l.195-203 — cinq `<input type="radio" name="botlang"
   data-setting="language">`.
2. `site/assets/js/page-dashboard.js` — `valeurDe()` (l.333), le filtre
   `if (f.type === 'radio' && !f.checked) return;` (l.568), `enregistrerTout()`
   (l.492) qui envoie `PATCH /guilds/{id}/settings` avec `{"language": "xx"}`,
   et `remplir()` (l.1532, l.1541 pour les radios).
3. `site/api/index.php` — le handler `PATCH` (l.908+), le filtre de clés, puis
   `trier_pour_le_bot()` (l.683) qui range `language` dans `$pourLeBot`, et
   `appel_bot('PATCH', '/api/guilds/{id}', …)`.
4. `bot/cogs/dashboard_api.py` — `language` validé contre `LANGUAGES` (l.555)
   puis `set_lang(guild.id, language)` (l.617).
5. `bot/i18n.py` — `set_lang()` écrit dans `_guild_langs` (dictionnaire **en
   mémoire du processus bot**) et `save_langs()` sur disque.

**Trois pistes sérieuses, à écarter ou confirmer par la preuve :**

- **`bot/i18n.py:get_lang()` force `"fr"`** quand `guild_id == _official_guild`
  (`GUNZFRANCE_GUILD_ID` dans `config.py`). Sur ce serveur-là, *aucun* choix de
  langue ne peut avoir d'effet, et le panneau n'en dit rien. Si je teste sur le
  serveur officiel, c'est l'explication entière.
- **`get_lang()` retombe sur `"en"`** quand le serveur n'est pas dans
  `_guild_langs`, alors que `dashboard.html` coche `fr` par défaut dans le
  balisage. Les deux défauts se contredisent.
- **Ce qui est déjà affiché ne se retraduit pas** : embeds déjà postés, vues
  persistantes, et surtout les **noms et descriptions des commandes slash**,
  qui sont enregistrés chez Discord et ne changent qu'à une resynchronisation
  (voir `bot/command_sync.py`). Si le bot « parle encore anglais », c'est
  peut-être exactement ça.

**Attendu.** Dis quel maillon casse, prouve-le (journal, appel réel, test), puis
corrige. Si le serveur officiel est volontairement verrouillé en français, le
panneau doit le montrer au lieu de faire semblant d'accepter le changement. Si
le problème est la resynchronisation des commandes, déclenche-la quand la
langue change — avec le respect des quotas Discord. Ajoute au moins un test
dans `bot/tests/` qui couvre le trajet corrigé.

---

## Chantier 4 — les options ne se synchronisent pas entre le panneau et Discord

**Le symptôme.** Une option modifiée sur Discord n'apparaît pas dans le
panneau, et l'inverse non plus.

**Ce que j'ai pu voir du mécanisme.**

- `site/api/index.php` l.1008-1015 : au `GET`, les réglages sont
  `array_merge($local, $duBot)` — **le bot gagne**, ce qui est le bon sens.
  Donc, pour toute clé réellement pontée, Discord → panneau devrait marcher.
- `reglages_du_bot()` (l.606) traduit la réponse du bot via les tables
  `PONT_RESSOURCES`, `PONT_FONCTIONS`, `PONT_QUEUE`, `PONT_MMR`, `PONT_RONDS`.
  **Toute clé absente de ces tables n'est jamais relue chez le bot** : elle
  reste dans `data/guilds.json` côté site, et se fige. C'est mon premier
  suspect : trouve les réglages du panneau qui ne sont pontés nulle part.
- Au `PATCH` (l.983-996), le site recopie **toutes** les clés dans son propre
  `guilds.json`, y compris celles que le bot possède. Cette copie n'est jamais
  invalidée. Elle n'est servie que si le bot est injoignable — mais alors elle
  ment, et le panneau ne signale rien.
- `bot/cogs/config.py` : la langue, la désignation des salons et celle des
  rôles **ont été retirées de `/config` le 11/10/2026** et ne vivent plus que
  sur le site. Donc pour ces réglages-là il n'y a plus de sens Discord →
  panneau : s'il reste une commande ou un bouton qui les écrit encore
  ailleurs, c'est elle le bug.
- `site/api/index.php` l.448-453 : `data/bot-guilds.json` est un cache de 60 s
  sur la *liste* des serveurs. Vérifie qu'il ne déborde pas sur les réglages.
- Côté bot, `guild_settings.py` et `json_store.py` : regarde si plusieurs
  processus (bot, API du tableau de bord) écrivent le même fichier, et ce qui
  arrive quand deux écritures se croisent.

**Attendu.**

1. Un inventaire : pour chaque réglage du panneau, qui en est propriétaire
   (bot ou site), est-il ponté dans les deux sens, et existe-t-il encore une
   commande Discord qui l'écrit. Mets ce tableau dans `docs/`.
2. La correction des écarts : soit on ponte, soit on retire le réglage d'un
   des deux côtés. **Une option, un seul propriétaire** — c'est déjà la règle
   que `bot/cogs/config.py` applique, suis-la.
3. Quand le bot est injoignable, le panneau doit le **dire** au lieu de servir
   une copie périmée en silence.
4. Les deux implémentations de l'API, `site/api/index.php` (PHP, production)
   et `api-locale/server.py` (Python, développement), doivent rester
   d'accord : toute réponse modifiée dans l'une l'est dans l'autre. Le
   contrat est décrit dans `docs/site-README.md` — tiens-le à jour.
5. Des tests dans `bot/tests/` sur le pont de réglages.

---

## Vérification, à la toute fin

```
python outils/numeroter_versions.py
.\cyq local
```

Puis, pour les chantiers 1 et 2, ouvre vraiment les pages :
`http://localhost:8765/index.html`, `http://localhost:8765/support.html`,
et aussi `?motion=on`. Regarde la console, teste en
`prefers-reduced-motion: reduce`, et à 375 px de large.

Pour les chantiers 3 et 4, l'API locale (`cyq local` lance `cyq-api` sur le
port 3000) sert `/api/*` sur la même origine : utilise-la pour rejouer le
trajet complet du `PATCH`.

Finis par un commit par chantier, messages en français, et **dis-moi
explicitement ce que tu as vérifié et ce que tu n'as pas pu vérifier** (ce qui
demande le vrai bot Discord ou la production, notamment).
