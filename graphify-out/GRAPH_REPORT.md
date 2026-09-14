# Graph Report - createyourqueue  (2026-09-14)

## Corpus Check
- 51 files · ~99,863 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 4, .example 1)

## Summary
- 1814 nodes · 4435 edges · 77 communities (74 shown, 2 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 74 edges (avg confidence: 0.85)
- Token cost: 71,998 input · 0 output

## Community Hubs (Navigation)
- Démarrage bot & modération
- Panneau /config
- Panneaux de rôles
- Cœur des files d'attente
- Stockage des réglages serveur
- Session ClanWar
- Classement & stats
- Clans : espaces & adhésions
- Assistant salons
- Langue & retraduction
- Hub des modules partagés
- Assistant fonctionnalités
- Données des clans
- Diagnostic
- Déroulé des matchs
- Anti-raid
- Logs serveur
- Réglages MMR
- Docs & installation
- Boutons espace clan
- Reset serveur
- Panneau de statut
- Accueil & choix de langue
- Accès aux ressources Discord
- Réglages parties & sondages
- Préréglages & planning
- Groupes (party)
- Sous-panneaux assistant
- Commandes /clan
- Sondages
- Lancement & revanche file
- Paliers MMR
- Embeds de marque & saisons
- Session de file
- Garde de l'assistant
- Tickets & invitations clan
- Aide /help
- Nettoyage auto
- Vue planning
- Stockage ModMail
- Scores & résultats
- Constructeur d'équipes
- Guide des files
- Panneau MMR assistant
- Assistant options & rangs
- Anti-lien
- Tâches planifiées & saisons
- Vue config de file
- Sélecteur d'équipes
- Demandes de guerre de clan
- Elo & rôles de rang
- Vue ModMail
- Limitation de débit
- Draft & votes
- Protection des salons
- Cog ModMail
- Réglages statut
- Gestion vocale
- Traduction t() & statut
- Tickets staff
- Préparation ClanWar
- Infos serveur/membre
- Bot temporaire
- Modale de préréglage
- Recherche & sauvegarde équipes
- Déploiement Railway
- Menu de choix automation
- Relais MP ModMail
- Réponse staff ModMail
- Fiche de clan
- Réponse ticket clan
- Reset ModMail
- Formulaire ModMail
- Nom d'équipe
- Interrupteurs classement
- Activation ClanWar

## God Nodes (most connected - your core abstractions)
1. `t()` - 329 edges
2. `sanitize()` - 65 edges
3. `save_settings()` - 49 edges
4. `Clan` - 35 edges
5. `_ensure()` - 35 edges
6. `get_mmr_config()` - 34 edges
7. `Match` - 31 edges
8. `QueueConfig` - 31 edges
9. `OptionsWizard` - 30 edges
10. `ClanWarSession` - 29 edges

## Surprising Connections (you probably didn't know these)
- `.env variables (DISCORD_TOKEN, SUPPORT_GUILD_ID, DIAGNOSTIC_CHANNEL_ID, ...)` --semantically_similar_to--> `ModMail env vars (DISCORD_TOKEN_MODMAIL, MODMAIL_GUILD_ID, MODMAIL_STAFF_CHANNEL_ID)`  [INFERRED] [semantically similar]
  README.md → MODMAIL_SETUP.md
- `Voice/TTS stack (gTTS, PyNaCl, davey, pyttsx3)` --conceptually_related_to--> `CreateYourQueue README`  [AMBIGUOUS]
  requirements.txt → README.md
- `Web stack (fastapi, uvicorn, aiofiles)` --conceptually_related_to--> `CreateYourQueue README`  [AMBIGUOUS]
  requirements.txt → README.md
- `_sorted_clans()` --calls--> `get_clans()`  [EXTRACTED]
  cogs/classement.py → guild_settings.py
- `report()` --calls--> `t()`  [EXTRACTED]
  cogs/queue_config.py → i18n.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Three-bot launch configuration (flag, cog lists, tokens)** — readme_three_bots_architecture, readme_bot_cli_flag, readme_extension_lists, readme_env_variables, modmail_setup_modmail_env_config [EXTRACTED 1.00]
- **ModMail support flow** — modmail_setup_modmail_bot, modmail_setup_ticket_flow, modmail_setup_ticket_categories, modmail_setup_modmail_sessions_json [EXTRACTED 1.00]
- **Local setup and verification workflow** — readme_local_installation, requirements_dependencies, readme_env_variables, readme_privileged_intents, readme_pyflakes_check [EXTRACTED 1.00]

## Communities (77 total, 2 thin omitted)

### Community 0 - "Démarrage bot & modération"
Cohesion: 0.06
Nodes (49): CreateYourQueueBot, cycle_presence(), global_setup_check(), main(), on_app_command_error(), AppCommandError, Bot, Interaction (+41 more)

### Community 1 - "Panneau /config"
Cohesion: 0.06
Nodes (36): AppearanceView, ChannelsView, pick(), Config, ConfigLanguageSelect, ConfigView, _fetch_image(), _main_embed() (+28 more)

### Community 2 - "Panneaux de rôles"
Cohesion: 0.06
Nodes (36): assign_is_still_safe(), build_panel_embed(), _member_lock(), PanelBuilderView, callback(), callback(), callback(), callback() (+28 more)

### Community 3 - "Cœur des files d'attente"
Cohesion: 0.06
Nodes (31): Bot, command, Guild, listener, Member, Role, TextChannel, VoiceChannel (+23 more)

### Community 4 - "Stockage des réglages serveur"
Cohesion: 0.07
Nodes (53): Cog : Queue System ================== Système de queue avec embed et boutons,…, add_queue_history_entry(), add_saved_team(), add_season_archive(), add_to_queue_blacklist(), clear_clan_war_session(), create_clan(), delete_poll() (+45 more)

### Community 5 - "Session ClanWar"
Cohesion: 0.06
Nodes (29): ClanWarSession, Any, Annule le ClanWar car un leader est absent., Surveille le salon vocal et lance le match quand les 2 leaders sont présents et…, Surveille le salon vocal et lance le match quand il est plein., Lance le compte à rebours de 30 secondes., Notifie qu'un joueur a quitté le vocal., Envoie une mise à jour du compte à rebours. (+21 more)

### Community 6 - "Classement & stats"
Cohesion: 0.07
Nodes (21): Classement, _sorted_clans(), publish(), Bot, command, Embed, Guild, Interaction (+13 more)

### Community 7 - "Clans : espaces & adhésions"
Cohesion: 0.08
Nodes (22): Clan, Embed, Guild, Role, TextChannel, User, Déchargement du cog : annule la tâche de fond et réinitialise les channels., Restaure les sessions de ClanWar actives après un redémarrage. (+14 more)

### Community 8 - "Assistant salons"
Cohesion: 0.08
Nodes (33): Crée une nouvelle queue, ou ouvre l'assistant si rien n'est réglé. Une seule…, _channel_line(), channels_embed(), ChannelsWizard, done_embed(), open_wizard(), options_embed(), Bot (+25 more)

### Community 9 - "Langue & retraduction"
Cohesion: 0.08
Nodes (33): Language, LanguageSelect, LanguageView, AppCommandError, Bot, command, error, has_permissions (+25 more)

### Community 10 - "Hub des modules partagés"
Cohesion: 0.07
Nodes (28): Cog : Anti-Link ================== Commande pour activer/désactiver l'anti-link…, Cog : Diagnostic ================ Commande : /diagnostic Auto-contrôle du bot.…, Cog : Guard =========== Protection des noms de salons créés par le bot. Le bot…, Cog : Modération ==================== Commandes : /clear, /lock, /unlock,…, color_name(), Nom d'une couleur de la palette dans une langue donnée. Les douze noms tiennent…, Cog : Reaction Roles personnalisables ======================================…, Cog : Voice Manager ==================== Gestion de la voix du bot pour les… (+20 more)

### Community 11 - "Assistant fonctionnalités"
Cohesion: 0.10
Nodes (24): ClanPanel, callback(), callback(), callback(), callback(), callback(), callback(), callback() (+16 more)

### Community 12 - "Données des clans"
Cohesion: 0.08
Nodes (34): clan_stats(), Bot, Cog : Clans =========== Équipes permanentes, par-dessus les queues. Une queue…, Clans triés par victoires, puis par ratio à égalité., Victoires, défaites et ratio du clan. Les chiffres viennent du classement des…, setup(), sorted_clans(), add_clan_member() (+26 more)

### Community 13 - "Diagnostic"
Cohesion: 0.12
Nodes (16): Check, Diagnostic, _flatten(), Bot, command, Guild, Interaction, listener (+8 more)

### Community 14 - "Déroulé des matchs"
Cohesion: 0.12
Nodes (15): Match, before_loop, Guild, listener, Crée le salon privé et lance la première phase. Retourne False si le salon n'a…, Les plus votés deviennent capitaines. À égalité — ou sans aucun vote — on…, Ordre de sélection en serpentin : A, B, B, A, A, B… Choisir en premier est un…, Enregistre un choix et passe au capitaine suivant. (+7 more)

### Community 15 - "Anti-raid"
Cohesion: 0.11
Nodes (21): AntiRaid, AppCommandError, Bot, command, datetime, Embed, Guild, has_permissions (+13 more)

### Community 16 - "Logs serveur"
Cohesion: 0.12
Nodes (18): Logs, _now_ts(), Bot, Choice, choices, command, Embed, has_permissions (+10 more)

### Community 17 - "Réglages MMR"
Cohesion: 0.15
Nodes (13): _bounded(), MMRView, PointsModal, button, Interaction, Création ou modification d'un rang (nom, seuil, couleur, icône)., Combien rapporte une victoire, coûte une défaite, et vaut le MVP., Durées des votes et délai avant suppression du salon. (+5 more)

### Community 18 - "Docs & installation"
Cohesion: 0.09
Nodes (32): ModMail Bot Setup, ModMail env vars (DISCORD_TOKEN_MODMAIL, MODMAIL_GUILD_ID, MODMAIL_STAFF_CHANNEL_ID), modmail_sessions.json session storage, ModMail Required Permissions, Ticket Categories (Bug, Signalement, Question, Suggestion), ModMail Ticket Flow (DM -> category -> staff channel -> reply/close), Adding a command (copy cogs/info.py template), bot.py --bot flag (main|modmail|temporaire|both) (+24 more)

### Community 19 - "Boutons espace clan"
Cohesion: 0.13
Nodes (14): ClanSpaceView, ClanWarActionView, button, Interaction, Boutons d'action pour le ClanWar (Manche, Abandonné, Problème)., Lance le vote pour la manche., L'abandon du ClanWar., Signale un problème au staff via ticket. (+6 more)

### Community 20 - "Reset serveur"
Cohesion: 0.10
Nodes (19): build_preview_embed(), ConfirmModal, generate_code(), AppCommandError, Bot, button, command, Embed (+11 more)

### Community 21 - "Panneau de statut"
Cohesion: 0.11
Nodes (18): before_loop, Bot, Embed, Guild, listener, loop, Qualité de la liaison avec Discord, en clair. « 240 ms » ne dit rien à qui ne…, Le gros titre, au-dessus du cadre. Un titre d'embed est limité en taille… (+10 more)

### Community 22 - "Accueil & choix de langue"
Cohesion: 0.12
Nodes (21): LanguageSelectView, Bot, button, Guild, Interaction, listener, Cog : Welcome ============= Gère l'accueil du bot sur les nouveaux serveurs…, Ouvre le panneau de configuration après la sélection de langue. (+13 more)

### Community 23 - "Accès aux ressources Discord"
Cohesion: 0.12
Nodes (27): _resolve_resource(), État de la configuration du serveur, en clair, pour l'étape 1., server_status(), collect_targets(), Cog : Reset =========== Commande : /reset (administrateur uniquement) Remet le…, Ressources réellement présentes, retrouvées par ID mémorisé. Volontairement…, get_resource_id(), Efface toute la configuration d'un serveur (voir /reset). Retourne la liste des… (+19 more)

### Community 24 - "Réglages parties & sondages"
Cohesion: 0.11
Nodes (25): group_players(), party_members(), Cog : Party =========== Commandes : /duo, /trio, /quatro, /groupe S'inscrire à…, Coéquipiers garantis d'un joueur, lui inclus. Liste vide s'il est seul., Regroupe des joueurs par groupe, les solos en groupes d'un. Sert à la…, Cog : Poll ========== Commande : /poll — un sondage à boutons pour trancher…, dissolve_party(), _fresh_parties() (+17 more)

### Community 25 - "Préréglages & planning"
Cohesion: 0.13
Nodes (23): _bounded_int(), build_schedule_embed(), next_occurrence(), _parse_time(), datetime, Cog : Automation ================ Commandes : /schedule (queue programmée),…, Ce que le planificateur publiera : (configuration, nom du preset, perdu ?).…, Choisit CE QUI est publié à l'heure programmée. (+15 more)

### Community 26 - "Groupes (party)"
Cohesion: 0.14
Nodes (14): Party, Bot, button, command, Embed, Guild, Interaction, listener (+6 more)

### Community 27 - "Sous-panneaux assistant"
Cohesion: 0.11
Nodes (13): MMRAmountModal, MMRDurationsPanel, callback(), MMRParamsPanel, callback(), Paramètres MMR : points de départ, victoire, défaite, MVP., Durées : vote capitaines, vote MVP, fermeture., Ce que toutes les pages ont en commun : le retour et le contrôle d'accès.… (+5 more)

### Community 28 - "Commandes /clan"
Cohesion: 0.14
Nodes (14): autocomplete, clan_embed(), Choice, command, Member, La fiche : nom, logo, ratio, effectif, membres, serveur du clan. La même en…, Rôle de chef et tag de clan dans le pseudo. Le rôle n'est **pas créé** : c'est…, Retire le rôle et le tag quand on quitte ou dissout. Le pseudo n'est remis à… (+6 more)

### Community 29 - "Sondages"
Cohesion: 0.12
Nodes (17): build_poll_embed(), parse_options(), Poll, PollView, callback(), Bot, command, Embed (+9 more)

### Community 30 - "Lancement & revanche file"
Cohesion: 0.14
Nodes (11): ConfirmPublishView, button, Interaction, select_callback(), Montre l'aperçu AVANT de publier. L'annonce partait directement avec un…, Dernier filet avant le @everyone : publier, ou revenir corriger., Confirmation d'un /rematch : republier tel quel, ou en prévenant les joueurs de…, Relance la dernière queue terminée sans rien reconfigurer. Juste après un… (+3 more)

### Community 31 - "Paliers MMR"
Cohesion: 0.11
Nodes (21): build_mmr_embed(), Embed, Paliers configurés, ou les paliers par défaut traduits., tiers_of(), apply(), default_tiers(), delta(), format_change() (+13 more)

### Community 32 - "Embeds de marque & saisons"
Cohesion: 0.11
Nodes (22): build_podium_embed(), build_season_embed(), period_label(), Embed, « 2026-07 » → « Juillet 2026 » dans la langue du serveur. Les douze mois…, Saison en cours + podiums archivés, du plus récent au plus ancien., align(), brand() (+14 more)

### Community 33 - "Session de file"
Cohesion: 0.11
Nodes (10): QueueSession, Représente une session de queue en cours., Ajoute un joueur à la file d'attente (pas encore réparti en équipe)., Retire un joueur de la file d'attente., Répartit la file d'attente dans les équipes et démarre la partie. La…, Avance dans les équipes en serpentin : 0,1,2 puis 2,1,0, etc., La file d'attente a-t-elle atteint la capacité totale (avant lancement) ?, Sérialise la session en IDs — les objets discord.py ne sont pas picklables et… (+2 more)

### Community 34 - "Garde de l'assistant"
Cohesion: 0.22
Nodes (7): _may_configure(), button, Interaction, Revient à la sélection de langue en cas d'erreur., Affiche le guide d'activation des options., Retourne au panneau de configuration des salons., Qui a le droit de configurer : les administrateurs du serveur. Volontairement…

### Community 35 - "Tickets & invitations clan"
Cohesion: 0.10
Nodes (9): CreateModal, CreateView, InviteView, Modal pour signaler un problème., Envoie le ticket au staff., View pour gérer les tickets du staff., Les deux boutons de l'invitation, en message privé. `interaction_check` est la…, TicketActionView (+1 more)

### Community 36 - "Aide /help"
Cohesion: 0.16
Nodes (14): _build_category_embed(), _build_overview_embed(), Help, HelpSelect, HelpView, Bot, button, command (+6 more)

### Community 37 - "Nettoyage auto"
Cohesion: 0.14
Nodes (13): AutoClean, AppCommandError, Bot, command, has_permissions, Interaction, TextChannel, Arrête le nettoyage automatique. (+5 more)

### Community 38 - "Vue planning"
Cohesion: 0.28
Nodes (8): button, Interaction, ScheduleView, on_submit(), SeasonView, callback(), set_schedule(), set_season()

### Community 39 - "Stockage ModMail"
Cohesion: 0.13
Nodes (10): ModMailStorage, Sauvegarde les sessions dans le fichier., Crée une nouvelle session et retourne l'ID du message staff., Récupère une session par son ID., Met à jour l'ID du message staff., Récupère l'ID de session d'un utilisateur (s'il en a une ouverte)., Gère le stockage des sessions modmail., Détecte la langue du texte et retourne le code de langue. (+2 more)

### Community 40 - "Scores & résultats"
Cohesion: 0.12
Nodes (12): build_score_embed(), LaunchView, Embed, Panel organisateur : répartit la file d'attente en équipes et démarre la partie., Annule la queue : supprime l'annonce, déverrouille le vocal, libère la session., Le tableau des points, en direct puis publié. Un seul constructeur pour les…, Panel de suivi des scores : un bouton par équipe + Finish pour clore et publier…, Ajoute un point horodaté à l'équipe cliquée. (+4 more)

### Community 41 - "Constructeur d'équipes"
Cohesion: 0.18
Nodes (11): Select, Écrit le nom et la couleur choisis dans le slot en cours d'édition., Deuxième étape de la création : la couleur, puis enregistrement dans la…, Tout ce qui concerne les équipes, au même endroit. Le panneau avait quatre…, Le menu des équipes dépend de leur nombre : on reconstruit la vue., callback(), color_callback(), TeamsBuilderView (+3 more)

### Community 42 - "Guide des files"
Cohesion: 0.18
Nodes (11): build_step_embed(), GuideView, Bot, button, command, Embed, Guild, Interaction (+3 more)

### Community 43 - "Panneau MMR assistant"
Cohesion: 0.18
Nodes (10): callback(), MMRPanel, callback(), MMRSettingsPanel, callback(), callback(), callback(), callback() (+2 more)

### Community 44 - "Assistant options & rangs"
Cohesion: 0.21
Nodes (5): MMRRanksPanel, callback(), OptionsWizard, Configuration des rangs et seuils., Menu d'accueil des options.

### Community 45 - "Anti-lien"
Cohesion: 0.13
Nodes (13): AntiLink, Bot, choices, command, Interaction, listener, Member, Message (+5 more)

### Community 46 - "Tâches planifiées & saisons"
Cohesion: 0.16
Nodes (8): Automation, before_loop, command, Guild, has_permissions, listener, loop, Le bot archivait les podiums de saison sans jamais les montrer. Visible de tout…

### Community 47 - "Vue config de file"
Cohesion: 0.13
Nodes (10): QueueConfigView, Modal générique à un seul champ texte, écrit dans…, Vue pour la configuration de queue avec boutons., Le bouton dit son état : vert allumé, gris éteint. Grisé si le système de match…, Change le titre de l'annonce., Configure le nom/numéro de la session., Configure l'heure de la session., Configure le type de session (texte libre). (+2 more)

### Community 48 - "Sélecteur d'équipes"
Cohesion: 0.16
Nodes (7): _natural_key(), Découpe le nom en morceaux texte/nombre pour que « Team2 » passe avant « Team10…, A→Z et Z→A rangent les noms qui commencent par un chiffre à la fin ; le mode…, Menu contextuel des noms d'équipe, sur le modèle du bouton Couleur : on choisit…, sort_teams(), TeamPickerView, Button

### Community 49 - "Demandes de guerre de clan"
Cohesion: 0.16
Nodes (8): QueueView, Publie le défi dans le salon du clan visé et l'inscrit dans sa file., Supprime toutes les anciennes demandes de wars d'un clan., Accepter ou refuser un défi, dans le salon du clan défié. Persistante elle…, Les demandes en attente : on en choisit une, puis on répond. Le même écran sert…, WarAnswerView, get_clan_requests(), kind : "wars" (defis recus) ou "joins" (demandes d adhesion).

### Community 50 - "Elo & rôles de rang"
Cohesion: 0.13
Nodes (12): now(), command, loop, Member, Role, Dépouille le vote, applique le MMR, annonce les gains., Attribue à chacun le rôle de son palier, et retire les autres., Icône de rôle — réservée aux serveurs boostés (niveau 2). Sans le boost,… (+4 more)

### Community 51 - "Vue ModMail"
Cohesion: 0.22
Nodes (9): ModMailView, button, Interaction, Vue avec les catégories de support., Catégorie Signalement., Catégorie Suggestion., Envoie la confirmation de la catégorie et demande la description., Prend en charge le ticket. (+1 more)

### Community 52 - "Limitation de débit"
Cohesion: 0.14
Nodes (12): Cog : Classement ================ Système de classement persistant — victoires,…, Chemin de l'annonce vocale dans la langue du serveur, avec repli sur le…, Met la partie en place une fois les équipes formées. Extrait du bouton « Lancer…, Retire le rôle Connexion à tous ses porteurs (fin/lancement de queue). Sans ça,…, voice_announce_path(), Exception, get_classement_message_id(), ID du message de classement affiché dans le salon dédié — mémorisé pour pouvoir… (+4 more)

### Community 53 - "Draft & votes"
Cohesion: 0.15
Nodes (9): DraftView, Bot, Cog : Match =========== Salon de match privé, capitaines, vote du MVP et MMR.…, Sélection d'un joueur par le capitaine dont c'est le tour., Menu de vote réservé aux joueurs du match. Un seul vote par personne,…, setup(), VoteView, get_match_state() (+1 more)

### Community 54 - "Protection des salons"
Cohesion: 0.18
Nodes (10): Guard, protected_key(), Bot, Guild, listener, Member, Clé de ressource d'un salon protégé, ou None s'il n'appartient pas au bot., Réaligne les noms sur la langue du serveur au démarrage. Sans appel API si tout… (+2 more)

### Community 55 - "Cog ModMail"
Cohesion: 0.20
Nodes (9): ModMail, Bot, User, Cog : ModMail ============ Bot de support par message privé. Les utilisateurs…, Affiche les catégories de support., Envoie un nouveau ticket au staff., Vue pour que le staff puisse prendre en charge et répondre aux tickets., setup() (+1 more)

### Community 56 - "Réglages statut"
Cohesion: 0.26
Nodes (6): ChannelSelect, TextChannel, Le panneau de réglage : un salon, un interrupteur. Même lecture que les pages…, StatusSettings, callback(), callback()

### Community 57 - "Gestion vocale"
Cohesion: 0.20
Nodes (10): Bot, command, Interaction, Member, Cog pour la gestion de la voix du bot., Vérifie si un membre est staff., Le bot rejoint le salon vocal de l'utilisateur., Le bot quitte le salon vocal actuel. (+2 more)

### Community 58 - "Traduction t() & statut"
Cohesion: 0.18
Nodes (10): build_panel_description(), Légende du panneau, construite depuis PANEL_BUTTONS : chaque ligne reprend…, _format_uptime(), AppCommandError, command, has_permissions, Interaction, Cog : Status Panel ================== Commande : /status — panneau de réglage… (+2 more)

### Community 59 - "Tickets staff"
Cohesion: 0.23
Nodes (8): Configuration du système de ticket pour le staff., StaffPanel, callback(), callback(), get_ticket_config(), Récupère la configuration du système de ticket d'un serveur., Définit la configuration du système de ticket d'un serveur., set_ticket_config()

### Community 60 - "Préparation ClanWar"
Cohesion: 0.24
Nodes (5): callback(), Select, Choisir l'adversaire, puis le format. Deux menus dans le même message éphémère…, WarSetupView, callback()

### Community 61 - "Infos serveur/membre"
Cohesion: 0.25
Nodes (7): Info, Bot, command, Interaction, Member, Cog : Info ========== Commandes : /userinfo, /serverinfo, setup()

### Community 62 - "Bot temporaire"
Cohesion: 0.22
Nodes (8): Bot, command, Interaction, Cog : Temp Bot =============== Commandes spécifiques pour le bot temporaire…, Commandes spécifiques pour le bot temporaire., Envoie le message d'attente et supprime la commande (owner uniquement)., setup(), TempBot

### Community 63 - "Modale de préréglage"
Cohesion: 0.22
Nodes (4): PresetModal, Bot, Création d'un preset depuis le panneau /schedule. Volontairement limité aux…, setup()

### Community 64 - "Recherche & sauvegarde équipes"
Cohesion: 0.25
Nodes (4): on_submit(), Enregistre la configuration actuelle sous un nom réutilisable. Le nom est…, Filtre la bibliothèque d'équipes par nom., TeamSearchModal

### Community 65 - "Déploiement Railway"
Cohesion: 0.29
Nodes (6): build, builder, deploy, numReplicas, startCommand, $schema

### Community 66 - "Menu de choix automation"
Cohesion: 0.40
Nodes (3): ChooserView, Select, Menu affiché *à la place* du panneau, qui redevient ensuite le panneau. Un…

### Community 67 - "Relais MP ModMail"
Cohesion: 0.40
Nodes (4): listener, Message, Écoute les messages privés pour le support., Transmet un message de l'utilisateur au staff.

### Community 68 - "Réponse staff ModMail"
Cohesion: 0.40
Nodes (3): Modal pour que le staff réponde à l'utilisateur., Traite la soumission de la réponse., StaffReplyModal

### Community 69 - "Fiche de clan"
Cohesion: 0.50
Nodes (3): ClanView, Boutons de la fiche. Ce qu'on voit dépend de qui regarde : seul le chef peut…, UserSelect

### Community 70 - "Réponse ticket clan"
Cohesion: 0.40
Nodes (3): Modal pour répondre à un ticket., Envoie la réponse à l'utilisateur., TicketResponseModal

### Community 71 - "Reset ModMail"
Cohesion: 0.40
Nodes (4): command, Réinitialise toutes les sessions modmail (owner only)., Context, is_owner

### Community 72 - "Formulaire ModMail"
Cohesion: 0.40
Nodes (3): ModMailModal, Modal pour collecter la description du problème., Traite la soumission du formulaire.

### Community 74 - "Interrupteurs classement"
Cohesion: 0.40
Nodes (3): FeaturePanel, Classement et Résultat : même page, même réglage — un salon, un interrupteur.…, Le Résultat n'a pas d'interrupteur propre : il est actif dès qu'un salon est…

## Ambiguous Edges - Review These
- `CreateYourQueue README` → `Voice/TTS stack (gTTS, PyNaCl, davey, pyttsx3)`  [AMBIGUOUS]
  requirements.txt · relation: conceptually_related_to
- `CreateYourQueue README` → `Web stack (fastapi, uvicorn, aiofiles)`  [AMBIGUOUS]
  requirements.txt · relation: conceptually_related_to
- `Five-language i18n (fr, en, es, de, ko) via t(guild_id, key)` → `Translation stack (langdetect, deep-translator)`  [AMBIGUOUS]
  requirements.txt · relation: conceptually_related_to

## Knowledge Gaps
- **9 isolated node(s):** `$schema`, `builder`, `numReplicas`, `startCommand`, `Ticket Categories (Bug, Signalement, Question, Suggestion)` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 589 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `CreateYourQueue README` and `Voice/TTS stack (gTTS, PyNaCl, davey, pyttsx3)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `CreateYourQueue README` and `Web stack (fastapi, uvicorn, aiofiles)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Five-language i18n (fr, en, es, de, ko) via t(guild_id, key)` and `Translation stack (langdetect, deep-translator)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `t()` connect `Traduction t() & statut` to `Démarrage bot & modération`, `Panneau /config`, `Panneaux de rôles`, `Cœur des files d'attente`, `Stockage des réglages serveur`, `Session ClanWar`, `Classement & stats`, `Clans : espaces & adhésions`, `Assistant salons`, `Langue & retraduction`, `Hub des modules partagés`, `Assistant fonctionnalités`, `Données des clans`, `Diagnostic`, `Déroulé des matchs`, `Anti-raid`, `Logs serveur`, `Réglages MMR`, `Boutons espace clan`, `Reset serveur`, `Panneau de statut`, `Accueil & choix de langue`, `Accès aux ressources Discord`, `Réglages parties & sondages`, `Préréglages & planning`, `Groupes (party)`, `Sous-panneaux assistant`, `Commandes /clan`, `Sondages`, `Lancement & revanche file`, `Paliers MMR`, `Embeds de marque & saisons`, `Session de file`, `Garde de l'assistant`, `Tickets & invitations clan`, `Aide /help`, `Nettoyage auto`, `Vue planning`, `Scores & résultats`, `Constructeur d'équipes`, `Guide des files`, `Panneau MMR assistant`, `Assistant options & rangs`, `Anti-lien`, `Tâches planifiées & saisons`, `Vue config de file`, `Sélecteur d'équipes`, `Demandes de guerre de clan`, `Elo & rôles de rang`, `Limitation de débit`, `Draft & votes`, `Protection des salons`, `Réglages statut`, `Tickets staff`, `Préparation ClanWar`, `Infos serveur/membre`, `Modale de préréglage`, `Recherche & sauvegarde équipes`, `Menu de choix automation`, `Fiche de clan`, `Nom d'équipe`, `Interrupteurs classement`?**
  _High betweenness centrality (0.614) - this node is a cross-community bridge._
- **Why does `sanitize()` connect `Commandes /clan` to `Panneau /config`, `Panneaux de rôles`, `Cœur des files d'attente`, `Stockage des réglages serveur`, `Session ClanWar`, `Classement & stats`, `Clans : espaces & adhésions`, `Hub des modules partagés`, `Données des clans`, `Déroulé des matchs`, `Réglages MMR`, `Boutons espace clan`, `Réglages parties & sondages`, `Préréglages & planning`, `Sondages`, `Lancement & revanche file`, `Session de file`, `Tickets & invitations clan`, `Vue planning`, `Scores & résultats`, `Vue config de file`, `Demandes de guerre de clan`, `Elo & rôles de rang`, `Limitation de débit`, `Draft & votes`, `Préparation ClanWar`, `Recherche & sauvegarde équipes`, `Nom d'équipe`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `ModMailStorage` connect `Stockage ModMail` to `Cog ModMail`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **What connects `$schema`, `builder`, `numReplicas` to the rest of the system?**
  _9 weakly-connected nodes found - possible documentation gaps or missing edges._