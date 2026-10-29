"""L'API lue par le site : la clé protège tout, et une demande refusée
n'écrit rien du tout."""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

import discord
from aiohttp.test_utils import TestClient, TestServer

import guild_settings
import i18n
import retranslate
from cogs import dashboard_api

KEY = "cle-de-test"
GUILD_ID = 4242
OWNER = 777
ADMIN = 888


def fake_channel(spec, channel_id: int, name: str):
    channel = MagicMock(spec=spec)
    channel.id = channel_id
    channel.name = name
    channel.permissions_for.return_value = MagicMock(send_messages=True)
    return channel


def fake_role(role_id: int, name: str):
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = name
    role.managed = False
    role.is_default.return_value = False
    return role


def fake_guild():
    text = fake_channel(discord.TextChannel, 10, "commandes")
    text2 = fake_channel(discord.TextChannel, 11, "annonces")
    voice = fake_channel(discord.VoiceChannel, 20, "attente")
    categorie = fake_channel(discord.CategoryChannel, 40, "Clans")
    staff = fake_role(30, "Staff")
    chef = fake_role(31, "Chef de clan")

    guild = MagicMock(spec=discord.Guild)
    guild.id = GUILD_ID
    guild.name = "Serveur test"
    guild.icon = None
    guild.member_count = 12
    guild.text_channels = [text, text2]
    guild.voice_channels = [voice]
    guild.categories = [categorie]
    guild.roles = [staff, chef]
    guild.unavailable = False
    guild.me = MagicMock(spec=discord.Member)
    guild.me.joined_at = datetime(2025, 6, 14, 12, 0, tzinfo=timezone.utc)

    channels = {c.id: c for c in (text, text2, voice, categorie)}
    roles = {r.id: r for r in (staff, chef)}
    guild.get_channel.side_effect = channels.get
    guild.get_role.side_effect = roles.get
    return guild


class FakeLogs:
    """Le cog des logs, réduit à ce que l'API lui demande."""

    def __init__(self):
        self.state = {kind: {"on": False, "channel": None,
                             "channel_name": None, "writable": None}
                      for kind in dashboard_api.LOG_KINDS}
        self.updates = []

    def dashboard_state(self, _guild):
        return self.state

    def dashboard_update(self, _guild, changes):
        self.updates.append(changes)


class RetraductionEspionne:
    """Remplace `retranslate_guild` pendant les tests.

    Ce qu'on veut vérifier ici, c'est QUE la retraduction est demandée, avec
    les bonnes langues — pas renommer les salons d'un serveur simulé. La
    vraie fonction irait chercher des catégories sur un MagicMock et
    échouerait pour une raison qui n'apprend rien."""

    def __init__(self):
        self.appels: list[tuple[int, str, str]] = []
        self.erreur: Exception | None = None

    async def __call__(self, bot, guild, ancienne, nouvelle):
        self.appels.append((guild.id, ancienne, nouvelle))
        if self.erreur is not None:
            raise self.erreur
        return {"renamed": 0, "failed": 0, "panels": 0}


class DashboardApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Les réglages s'écrivent dans un dossier jetable, jamais dans data/.
        self._previous_cwd = os.getcwd()
        self._temp = tempfile.TemporaryDirectory()
        os.chdir(self._temp.name)
        os.makedirs("data", exist_ok=True)
        guild_settings._settings.clear()
        i18n._guild_langs.clear()

        dashboard_api.DASHBOARD_API_KEY = KEY
        dashboard_api.OWNER_ID = OWNER
        self.guild = fake_guild()
        bot = MagicMock()
        bot.guilds = [self.guild]
        bot.get_guild.side_effect = lambda gid: self.guild if gid == GUILD_ID else None

        self.logs = FakeLogs()
        bot.get_cog.side_effect = lambda name: self.logs if name == "Logs" else None

        self.cog = dashboard_api.DashboardAPI(bot)
        self.client = TestClient(TestServer(self.cog.build_app()))
        await self.client.start_server()

        # `_retraduire` importe la fonction au moment de l'appel : on peut
        # donc la remplacer ici, sur le module.
        self.retraduction = RetraductionEspionne()
        self._vrai_retranslate = retranslate.retranslate_guild
        retranslate.retranslate_guild = self.retraduction

    async def attendre_retraductions(self):
        """Laisse finir les retraductions lancées en arrière-plan.

        Elles ne sont pas attendues par la requête — c'est tout l'intérêt,
        le PHP n'accorde que 12 secondes — donc un test qui regarde leur
        résultat juste après le PATCH ne verrait rien."""
        taches = list(self.cog._retraductions)
        if taches:
            await asyncio.gather(*taches, return_exceptions=True)

    def run_command(self, name: str = "queue", status: str = "OK", guild_id: int = GUILD_ID):
        """Fait comme si quelqu'un venait de lancer une commande."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild_id = guild_id
        interaction.guild = self.guild
        interaction.user = MagicMock(display_name="Testeur")
        self.cog._record(interaction, MagicMock(qualified_name=name), status)

    async def asyncTearDown(self):
        await self.attendre_retraductions()
        retranslate.retranslate_guild = self._vrai_retranslate
        await self.client.close()
        os.chdir(self._previous_cwd)
        self._temp.cleanup()
        guild_settings._settings.clear()
        i18n._guild_langs.clear()
        i18n._official_guild = 0

    def headers(self, key: str = KEY) -> dict[str, str]:
        return {"X-API-Key": key}

    # ------------------------------------------------------------------
    # La clé
    # ------------------------------------------------------------------
    async def test_sans_cle_rien_ne_passe(self):
        for path in ("/api/health", "/api/guilds", f"/api/guilds/{GUILD_ID}"):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status, 401)

    async def test_mauvaise_cle_refusee(self):
        response = await self.client.get("/api/health", headers=self.headers("autre"))
        self.assertEqual(response.status, 401)

    async def test_ecriture_refusee_sans_cle(self):
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", json={"language": "en"}
        )
        self.assertEqual(response.status, 401)
        self.assertEqual(i18n._guild_langs, {})

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    async def test_health(self):
        response = await self.client.get("/api/health", headers=self.headers())
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["status"], "ok")

    async def test_liste_des_serveurs(self):
        response = await self.client.get("/api/guilds", headers=self.headers())
        data = await response.json()
        self.assertEqual([g["id"] for g in data], [str(GUILD_ID)])
        self.assertEqual(data[0]["members"], 12)
        self.assertEqual(data[0]["joined"], "2025-06-14")
        self.assertTrue(data[0]["available"])

    async def test_chiffres_du_tableau_de_bord(self):
        self.run_command()
        self.run_command("clan")
        response = await self.client.get("/api/stats", headers=self.headers())
        data = await response.json()
        self.assertEqual(data["servers"], 1)
        self.assertEqual(data["users"], 12)
        self.assertEqual(data["commands_24h"], 2)
        self.assertGreaterEqual(data["uptime_seconds"], 0)

    async def test_chiffres_limites_aux_serveurs_demandes(self):
        self.run_command()
        response = await self.client.get("/api/stats?guilds=999", headers=self.headers())
        data = await response.json()
        self.assertEqual(data["servers"], 0)
        self.assertEqual(data["commands_24h"], 0, "l'activité d'un autre serveur ne fuit pas")

    async def test_journal_reserve_au_proprietaire(self):
        self.run_command("queue")
        rows = await (await self.client.get(f"/api/commands?user={OWNER}",
                                            headers=self.headers())).json()
        self.assertEqual([row["command"] for row in rows], ["/queue"])

        # Un admin de serveur, et même un site qui oublierait le paramètre,
        # se font refuser : le verrou est dans le bot, pas dans le gabarit.
        for query in (f"?user={ADMIN}", "", "?user=", f"?guilds={GUILD_ID}"):
            with self.subTest(query=query):
                response = await self.client.get(f"/api/commands{query}", headers=self.headers())
                self.assertEqual(response.status, 403)

    async def test_qui_est_proprietaire(self):
        owner = await (await self.client.get(f"/api/viewer?user={OWNER}",
                                             headers=self.headers())).json()
        admin = await (await self.client.get(f"/api/viewer?user={ADMIN}",
                                             headers=self.headers())).json()
        anonymous = await (await self.client.get("/api/viewer", headers=self.headers())).json()
        self.assertTrue(owner["owner"])
        self.assertFalse(admin["owner"])
        self.assertFalse(anonymous["owner"], "sans identifiant, ce n'est pas le propriétaire")

    async def test_journal_des_commandes(self):
        self.run_command("queue")
        self.run_command("ban", status="ERR")
        response = await self.client.get(f"/api/commands?user={OWNER}", headers=self.headers())
        rows = await response.json()
        self.assertEqual([row["command"] for row in rows], ["/ban", "/queue"],
                         "la plus récente en premier")
        self.assertEqual(rows[0]["status"], "ERR")
        self.assertEqual(rows[0]["user"], "Testeur")
        self.assertNotIn("options", rows[0], "les arguments ne sortent jamais de Discord")

    async def test_aucun_serveur_demande_ne_montre_rien(self):
        # Le site envoie « guilds= » vide pour qui n'administre aucun serveur.
        self.run_command()
        stats = await (await self.client.get("/api/stats?guilds=", headers=self.headers())).json()
        self.assertEqual((stats["servers"], stats["users"], stats["commands_24h"]), (0, 0, 0))

    async def test_journal_filtre_par_serveur(self):
        self.run_command("queue")
        self.run_command("secret", guild_id=999)
        response = await self.client.get(f"/api/commands?user={OWNER}&guilds={GUILD_ID}",
                                         headers=self.headers())
        rows = await response.json()
        self.assertEqual([row["command"] for row in rows], ["/queue"])

    async def test_commande_hors_serveur_ignoree(self):
        self.run_command(guild_id=None)
        response = await self.client.get(f"/api/commands?user={OWNER}", headers=self.headers())
        self.assertEqual(await response.json(), [])

    async def test_serveur_inconnu(self):
        response = await self.client.get("/api/guilds/999", headers=self.headers())
        self.assertEqual(response.status, 404)

    async def test_details_et_options(self):
        response = await self.client.get(f"/api/guilds/{GUILD_ID}", headers=self.headers())
        data = await response.json()
        self.assertEqual(data["name"], "Serveur test")
        self.assertIn("leaderboard", data["features"])
        self.assertIsNone(data["resources"]["role_staff"])

        response = await self.client.get(
            f"/api/guilds/{GUILD_ID}/options", headers=self.headers()
        )
        options = await response.json()
        self.assertEqual([c["name"] for c in options["text"]], ["commandes", "annonces"])
        self.assertEqual([r["name"] for r in options["role"]], ["Staff", "Chef de clan"])
        # La catégorie des clans se règle depuis le panneau : il lui faut la liste.
        self.assertEqual([c["name"] for c in options["category"]], ["Clans"])

    # ------------------------------------------------------------------
    # Écriture
    # ------------------------------------------------------------------
    async def test_modification_complete(self):
        response = await self.client.patch(f"/api/guilds/{GUILD_ID}", headers=self.headers(), json={
            "language": "es",
            "features": {"leaderboard": True},
            "resources": {"channel_queue_command": "10", "role_staff": 30},
        })
        self.assertEqual(response.status, 200)
        self.assertEqual(i18n.get_lang(GUILD_ID), "es")
        self.assertTrue(guild_settings.get_features(GUILD_ID)["leaderboard"])
        self.assertEqual(guild_settings.get_resource_id(GUILD_ID, "channel_queue_command"), 10)
        self.assertEqual(guild_settings.get_resource_id(GUILD_ID, "role_staff"), 30)

    # ------------------------------------------------------------------
    # La langue
    #
    # Le symptôme rapporté : « je change la langue dans le panneau et le bot
    # continue en français sur Discord ». Il y avait deux causes distinctes,
    # une par classe de serveur, et chacune a son test ici.
    # ------------------------------------------------------------------
    async def test_changer_la_langue_retraduit_le_serveur(self):
        """La cause n°1 : les salons et les rôles restaient dans l'ancienne
        langue. `retranslate.py` sait les renommer, mais plus personne ne
        l'appelait depuis que /language est partie sur le site."""
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(), json={"language": "es"}
        )
        self.assertEqual(response.status, 200)
        await self.attendre_retraductions()
        self.assertEqual(self.retraduction.appels, [(GUILD_ID, "en", "es")])

    async def test_la_meme_langue_ne_retraduit_rien(self):
        """Réenregistrer sans rien changer ne doit pas renommer onze salons
        pour le plaisir : c'est onze appels à l'API de Discord."""
        await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(), json={"language": "de"}
        )
        await self.attendre_retraductions()
        self.retraduction.appels.clear()

        await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(), json={"language": "de"}
        )
        await self.attendre_retraductions()
        self.assertEqual(self.retraduction.appels, [])

    async def test_une_retraduction_qui_echoue_n_annule_pas_la_langue(self):
        """La retraduction est un EFFET du changement de langue, pas une
        condition. Si Discord refuse un renommage, la langue reste changée et
        la requête reste un succès — sinon le panneau annoncerait un échec
        alors que le bot a bien compris."""
        self.retraduction.erreur = RuntimeError("Discord a refusé")
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(), json={"language": "ko"}
        )
        self.assertEqual(response.status, 200)
        await self.attendre_retraductions()
        self.assertEqual(i18n.get_lang(GUILD_ID), "ko")

    async def test_le_serveur_officiel_suit_le_choix_du_panneau(self):
        """La cause n°2 : `get_lang` renvoyait « fr » pour le serveur
        officiel avant même de regarder ce qui avait été choisi. Le panneau
        affichait « Enregistré », le fichier gardait la nouvelle langue, et
        le bot répondait en français."""
        i18n._official_guild = GUILD_ID
        self.assertEqual(i18n.get_lang(GUILD_ID), "fr")   # le défaut, lui, reste

        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(), json={"language": "en"}
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(i18n.get_lang(GUILD_ID), "en")

        # Et le panneau doit lire la même chose que le bot, sinon il
        # réafficherait « Français » au rechargement.
        lu = await self.client.get(f"/api/guilds/{GUILD_ID}", headers=self.headers())
        self.assertEqual((await lu.json())["language"], "en")

    async def test_les_quatre_roles_du_bot_sont_reglables(self):
        # /config ne propose plus les rôles : si l'un d'eux manquait ici,
        # il ne serait plus réglable nulle part.
        for key in ("role_staff", "role_queue_notif", "role_connexion", "role_mvp_week"):
            with self.subTest(role=key):
                response = await self.client.patch(
                    f"/api/guilds/{GUILD_ID}", headers=self.headers(),
                    json={"resources": {key: 30}},
                )
                self.assertEqual(response.status, 200)
                self.assertEqual(guild_settings.get_resource_id(GUILD_ID, key), 30)

    async def test_les_logs_se_reglent_depuis_le_site(self):
        # Les commandes /logs* n'existent plus : si ce chemin casse, plus
        # personne ne peut choisir un salon de logs.
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(),
            json={"logs": {"moderation": {"on": True, "channel": "10"}}},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(self.logs.updates,
                         [{"moderation": {"on": True, "channel": 10}}])
        self.assertIn("moderation", (await response.json())["logs"])

    async def test_logs_refuses_quand_c_est_incoherent(self):
        for payload in ({"logs": {"inventé": {"on": True}}},
                        {"logs": {"vocal": {"on": "oui"}}},
                        {"logs": {"vocal": {"channel": 30}}},  # un rôle, pas un salon
                        {"logs": {"vocal": {"channel": 12345}}}):
            with self.subTest(payload=payload):
                response = await self.client.patch(
                    f"/api/guilds/{GUILD_ID}", headers=self.headers(), json=payload)
                self.assertEqual(response.status, 400)
        self.assertEqual(self.logs.updates, [], "rien n'a été écrit")

    async def test_effacer_un_salon(self):
        guild_settings.set_resource_id(GUILD_ID, "channel_queue_command", 10)
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(),
            json={"resources": {"channel_queue_command": None}},
        )
        self.assertEqual(response.status, 200)
        self.assertIsNone(guild_settings.get_resource_id(GUILD_ID, "channel_queue_command"))

    async def test_refus_langue_inconnue_sans_rien_ecrire(self):
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(),
            json={"language": "xx", "features": {"leaderboard": True}},
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(i18n._guild_langs, {})
        self.assertFalse(guild_settings.get_features(GUILD_ID)["leaderboard"])

    async def test_refus_fonction_inconnue(self):
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(),
            json={"features": {"invente": True}},
        )
        self.assertEqual(response.status, 400)

    async def test_refus_mauvais_type_de_salon(self):
        # Un rôle proposé comme salon textuel, ou un salon comme rôle.
        for key, value in (("channel_queue_command", 30), ("role_staff", 10)):
            with self.subTest(key=key):
                response = await self.client.patch(
                    f"/api/guilds/{GUILD_ID}", headers=self.headers(),
                    json={"resources": {key: value}},
                )
                self.assertEqual(response.status, 400)
                self.assertIsNone(guild_settings.get_resource_id(GUILD_ID, key))

    async def test_refus_salon_inconnu(self):
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(),
            json={"resources": {"channel_queue_command": 12345}},
        )
        self.assertEqual(response.status, 400)

    async def test_refus_json_invalide(self):
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(), data="pas du json",
        )
        self.assertEqual(response.status, 400)

    # ------------------------------------------------------------------
    # Les clans et l'anti-raid : ce qui ne traversait pas
    # ------------------------------------------------------------------
    async def test_les_ressources_de_clan_se_reglent(self):
        """Le bot les tenait déjà, mais elles manquaient de EDITABLE_RESOURCES :
        le panneau avait trois champs qui n'arrivaient jamais jusqu'ici."""
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(),
            json={"resources": {"category_clan": "40", "role_clan_leader": "31"}},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(guild_settings.get_resource_id(GUILD_ID, "category_clan"), 40)
        self.assertEqual(guild_settings.get_resource_id(GUILD_ID, "role_clan_leader"), 31)

    async def test_une_categorie_n_est_pas_un_role(self):
        """Le repli de `_matches_kind` renvoyait « est-ce un salon vocal ? »
        pour tout type inconnu. Chaque type se vérifie maintenant pour
        lui-même, et ce qui n'est pas prévu se refuse."""
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(),
            json={"resources": {"role_clan_leader": "40"}},
        )
        self.assertEqual(response.status, 400)
        self.assertIsNone(guild_settings.get_resource_id(GUILD_ID, "role_clan_leader"))

    async def test_l_anti_raid_s_enregistre(self):
        """Les sept réglages de sécurité du panneau n'allaient nulle part :
        il disait « Enregistré » et le bot gardait ses anciens seuils."""
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(),
            json={"security": {"join_threshold": 7, "join_interval": 45,
                               "min_account_age_hours": 48, "auto_kick": True}},
        )
        self.assertEqual(response.status, 200)
        cfg = guild_settings.get_antiraid_config(GUILD_ID)
        self.assertEqual(cfg["join_threshold"], 7)
        self.assertEqual(cfg["join_interval"], 45)
        self.assertEqual(cfg["min_account_age_hours"], 48)
        self.assertIs(cfg["auto_kick"], True)

    async def test_l_anti_raid_se_lit(self):
        """L'autre sens : réglé par /antiraid config sur Discord, il doit se
        voir dans le panneau sans rien avoir à faire."""
        guild_settings.set_antiraid_config(GUILD_ID, join_threshold=3, auto_kick=True)
        response = await self.client.get(
            f"/api/guilds/{GUILD_ID}", headers=self.headers())
        charge = await response.json()
        self.assertEqual(charge["security"]["join_threshold"], 3)
        self.assertIs(charge["security"]["auto_kick"], True)
        # Et rien d'autre : les clés que le panneau ne règle pas n'ont pas à
        # sortir d'ici.
        self.assertEqual(set(charge["security"]), set(dashboard_api.SECURITY_FIELDS))

    async def test_un_seuil_hors_bornes_n_ecrit_rien(self):
        """Les bornes sont celles de /antiraid config. Deux chemins vers le
        même réglage qui n'accepteraient pas les mêmes valeurs, c'est la
        promesse d'un panneau qui refuse ce que Discord vient d'accepter."""
        defaut = guild_settings.get_antiraid_config(GUILD_ID)
        for mauvais in ({"join_threshold": 1}, {"join_threshold": 101},
                        {"join_interval": 301}, {"min_account_age_hours": 721},
                        {"auto_kick": "oui"}, {"inconnu": 1}):
            with self.subTest(envoi=mauvais):
                response = await self.client.patch(
                    f"/api/guilds/{GUILD_ID}", headers=self.headers(),
                    json={"security": mauvais},
                )
                self.assertEqual(response.status, 400)
                self.assertEqual(guild_settings.get_antiraid_config(GUILD_ID), defaut)
        self.assertNotIn("antiraid_config", guild_settings._settings.get(GUILD_ID, {}))

    async def test_un_lot_refuse_n_ecrit_rien_du_tout(self):
        """La langue est valide, la sécurité ne l'est pas : rien ne passe.
        Enregistrer la moitié d'un formulaire en disant « c'est fait » serait
        pire que de tout refuser."""
        response = await self.client.patch(
            f"/api/guilds/{GUILD_ID}", headers=self.headers(),
            json={"language": "en", "security": {"join_threshold": 999}},
        )
        self.assertEqual(response.status, 400)
        self.assertNotIn(GUILD_ID, i18n._guild_langs)
        self.assertNotIn("antiraid_config", guild_settings._settings.get(GUILD_ID, {}))


if __name__ == "__main__":
    unittest.main()
