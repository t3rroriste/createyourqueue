"""
Les pages du site, sans Discord ni bot réels.

Tout est simulé : la connexion Discord et les réponses du bot. Ces tests
disent surtout qui voit quoi, c'est la partie qu'on ne veut pas casser
par accident.

    cd site
    venv/Scripts/python -m unittest test_site        (Windows)
    venv/bin/python -m unittest test_site            (Linux)
"""

import os
import time
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

# Avant d'importer main : il lit ces valeurs au chargement.
os.environ.setdefault("DISCORD_CLIENT_ID", "123456789")
os.environ.setdefault("DISCORD_CLIENT_SECRET", "secret")
os.environ.setdefault("DISCORD_REDIRECT_URI", "http://testserver/callback")
os.environ.setdefault("SESSION_SECRET", "x" * 40)
os.environ.setdefault("BOT_API_URL", "http://bot.invalid:8080")
os.environ.setdefault("BOT_API_KEY", "cle")

from fastapi.testclient import TestClient  # noqa: E402

import bot_api  # noqa: E402
import discord_oauth  # noqa: E402
import main  # noqa: E402

# Deux serveurs administrés : un où le bot est, un où il n'est pas.
MY_GUILDS = [{"id": "42", "name": "Serveur test", "icon": None},
             {"id": "99", "name": "Sans le bot", "icon": None}]

PRESENT = [{"id": "42", "name": "Serveur test", "icon": None, "members": 1284,
            "setup_complete": True, "joined": "2025-06-14", "available": True}]

DETAIL = {
    "id": "42", "name": "Serveur test", "icon": None, "members": 1284,
    "setup_complete": True, "language": "fr",
    "languages": {"fr": "Français", "en": "English"},
    "features": {"leaderboard": True, "mvp": False, "clans": False,
                 "clan_notice": True, "status": False, "password": False},
    "resources": {"channel_queue_command": {"id": "5", "name": "commandes"},
                  "channel_queue_announcement": None,
                  "channel_queue_resultat": None,
                  "channel_queue_classement": None,
                  "voice_queue_waiting": {"id": "9", "name": None},
                  "role_staff": {"id": "3", "name": "Staff"},
                  "role_queue_notif": None,
                  "role_connexion": None,
                  "role_mvp_week": None},
}

OPTIONS = {"text": [{"id": "5", "name": "commandes"}, {"id": "6", "name": "annonces"}],
           "voice": [{"id": "9", "name": "attente"}],
           "role": [{"id": "3", "name": "Staff"}, {"id": "4", "name": "Joueur"}]}


class SiteCase(unittest.TestCase):
    """Une personne connectée, un bot qui répond. `owner` décide si c'est
    le propriétaire du bot ou un simple admin de serveur."""

    owner = False

    def setUp(self):
        self.asked = {}
        self.sent = {}
        self.client = TestClient(main.app)

        async def fake_exchange(code):
            return "jeton"

        async def fake_user(token):
            return {"id": "7", "name": "Testeur", "avatar": None}

        async def fake_managed(token):
            return MY_GUILDS

        async def fake_guilds():
            return list(PRESENT)

        async def fake_stats(guild_ids):
            self.asked["stats"] = list(guild_ids)
            return {"uptime_seconds": 4095000, "servers": 1,
                    "users": 1284, "commands_24h": 18392}

        async def fake_commands(user_id, limit=25):
            self.asked["commands_user"] = user_id
            self.asked["limit"] = limit
            return [{"at": time.time(), "guild_id": "42", "guild": "Serveur test",
                     "user": "Testeur", "command": "/queue", "status": "OK"},
                    {"at": time.time() - 60, "guild_id": "42", "guild": "Serveur test",
                     "user": "Testeur", "command": "/ban", "status": "ERR"}]

        async def fake_is_owner(user_id):
            return self.owner

        async def fake_guild(guild_id):
            return DETAIL

        async def fake_options(guild_id):
            return OPTIONS

        async def fake_patch(guild_id, payload):
            self.sent["guild_id"] = guild_id
            self.sent["payload"] = payload
            return DETAIL

        for module, name, double in (
            (discord_oauth, "exchange_code", fake_exchange),
            (discord_oauth, "fetch_user", fake_user),
            (discord_oauth, "fetch_managed_guilds", fake_managed),
            (bot_api, "guilds", fake_guilds),
            (bot_api, "stats", fake_stats),
            (bot_api, "commands", fake_commands),
            (bot_api, "is_owner", fake_is_owner),
            (bot_api, "guild", fake_guild),
            (bot_api, "options", fake_options),
            (bot_api, "patch", fake_patch),
        ):
            patcher = mock.patch.object(module, name, double)
            patcher.start()
            self.addCleanup(patcher.stop)

    def connect(self):
        """Fait la connexion Discord, état compris."""
        redirect = self.client.get("/login", follow_redirects=False)
        state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
        return self.client.get(f"/callback?code=abc&state={state}", follow_redirects=False)


class PagesPubliquesTest(SiteCase):
    def test_accueil(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Inviter le bot", page.text)
        self.assertIn('href="/dashboard"', page.text)
        self.assertIn("discord.com/oauth2/authorize", page.text)

    def test_dashboard_demande_la_connexion(self):
        answer = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(answer.status_code, 303)
        self.assertEqual(answer.headers["location"], "/login")

    def test_un_etat_qui_ne_correspond_pas_est_refuse(self):
        self.assertEqual(self.client.get("/callback?code=abc&state=faux").status_code, 400)

    def test_connexion(self):
        answer = self.connect()
        self.assertEqual(answer.status_code, 303)
        self.assertEqual(answer.headers["location"], "/dashboard")


class AdminDeServeurTest(SiteCase):
    """Ce que voit quelqu'un qui administre un serveur, sans plus."""

    owner = False

    def setUp(self):
        super().setUp()
        self.connect()

    def test_les_chiffres_ne_portent_que_sur_ses_serveurs(self):
        page = self.client.get("/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn("47j 9h 30m", page.text)
        self.assertIn("1 284", page.text)
        self.assertEqual(self.asked["stats"], ["42"])

    def test_le_bouton_configurer_est_un_bouton(self):
        page = self.client.get("/dashboard")
        self.assertIn('class="button small" href="/dashboard/42/general"', page.text)
        self.assertIn("Bot absent", page.text, "le serveur sans le bot est signalé")

    def test_pas_de_journal(self):
        page = self.client.get("/dashboard")
        self.assertNotIn("/queue", page.text, "le journal n'est pas affiché")
        self.assertNotIn('href="/dashboard/journal"', page.text, "ni son onglet")
        self.assertEqual(self.client.get("/dashboard/journal").status_code, 403)
        self.assertNotIn("commands_user", self.asked, "le journal n'est même pas demandé")

    def test_serveur_qu_il_n_administre_pas(self):
        self.assertEqual(self.client.get("/dashboard/12345/general").status_code, 403)
        self.assertEqual(self.client.post("/dashboard/12345/general",
                                          data={"language": "fr"}).status_code, 403)


class ProprietaireTest(SiteCase):
    owner = True

    def setUp(self):
        super().setUp()
        self.connect()

    def test_le_journal_lui_est_ouvert(self):
        page = self.client.get("/dashboard")
        self.assertIn("/queue", page.text)
        self.assertIn("Échec", page.text, "une commande ratée se voit")
        self.assertIn('href="/dashboard/journal"', page.text)
        self.assertEqual(self.asked["commands_user"], "7")

    def test_page_journal_complete(self):
        page = self.client.get("/dashboard/journal")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.asked["limit"], 100)


class CategoriesTest(SiteCase):
    """La configuration est découpée, et chaque page n'envoie que sa part."""

    def setUp(self):
        super().setUp()
        self.connect()

    def test_ancienne_adresse(self):
        answer = self.client.get("/dashboard/42", follow_redirects=False)
        self.assertEqual(answer.headers["location"], "/dashboard/42/general")

    def test_les_quatre_categories(self):
        page = self.client.get("/dashboard/42/general")
        for section in ("general", "salons", "roles", "fonctions"):
            self.assertIn(f"/dashboard/42/{section}", page.text)
        self.assertEqual(self.client.get("/dashboard/42/inventee").status_code, 404)

    def test_general(self):
        page = self.client.get("/dashboard/42/general")
        self.assertIn('<option value="fr" selected>', page.text)
        self.assertNotIn("feature_leaderboard", page.text, "les fonctions sont ailleurs")

        self.client.post("/dashboard/42/general", data={"language": "en"})
        self.assertEqual(self.sent["payload"], {"language": "en"})

    def test_salons(self):
        page = self.client.get("/dashboard/42/salons")
        self.assertIn('<option value="5" selected>', page.text)
        self.assertIn("redésigne-le", page.text, "un salon supprimé est signalé")
        self.assertNotIn("resource_role_staff", page.text, "les rôles sont ailleurs")

        self.client.post("/dashboard/42/salons",
                         data={"resource_channel_queue_command": "6",
                               "resource_voice_queue_waiting": ""})
        payload = self.sent["payload"]
        self.assertEqual(set(payload), {"resources"})
        self.assertEqual(payload["resources"]["channel_queue_command"], "6")
        self.assertIsNone(payload["resources"]["voice_queue_waiting"])
        self.assertNotIn("role_staff", payload["resources"])

    def test_roles(self):
        page = self.client.get("/dashboard/42/roles")
        self.assertIn('<option value="3" selected>', page.text)

        self.client.post("/dashboard/42/roles", data={"resource_role_staff": "3"})
        # Les quatre rôles du bot sont ici : /config ne les propose plus.
        self.assertEqual(set(self.sent["payload"]["resources"]),
                         {"role_staff", "role_queue_notif", "role_connexion", "role_mvp_week"})

    def test_fonctions(self):
        page = self.client.get("/dashboard/42/fonctions")
        self.assertIn('name="feature_leaderboard" checked', page.text)

        self.client.post("/dashboard/42/fonctions", data={"feature_mvp": "on"})
        features = self.sent["payload"]["features"]
        self.assertEqual(set(self.sent["payload"]), {"features"})
        self.assertTrue(features["mvp"], "la case cochée arrive à vrai")
        self.assertFalse(features["leaderboard"], "la case décochée arrive à faux")


class DeconnexionTest(SiteCase):
    def test_se_deconnecter_ferme_tout(self):
        self.connect()
        self.client.get("/logout")
        answer = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(answer.headers["location"], "/login")


class BotEteintTest(unittest.TestCase):
    """Le bot ne répond pas : les pages restent lisibles."""

    def test_le_tableau_de_bord_le_dit(self):
        client = TestClient(main.app)

        async def fake_exchange(code):
            return "jeton"

        async def fake_user(token):
            return {"id": "7", "name": "Testeur", "avatar": None}

        async def fake_managed(token):
            return MY_GUILDS

        with mock.patch.object(discord_oauth, "exchange_code", fake_exchange), \
             mock.patch.object(discord_oauth, "fetch_user", fake_user), \
             mock.patch.object(discord_oauth, "fetch_managed_guilds", fake_managed):
            redirect = client.get("/login", follow_redirects=False)
            state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
            client.get(f"/callback?code=abc&state={state}")
            page = client.get("/dashboard")

        self.assertEqual(page.status_code, 200)
        self.assertIn("injoignable", page.text)


if __name__ == "__main__":
    unittest.main()
