"""Le dashboard web : jetons de connexion, gardes d'accès et enregistrement
de la configuration de queue.

Les tests tournent dans un dossier temporaire (avec une copie de `locales/`) :
aucune écriture ne doit atterrir dans le `data/` du projet.
"""

import asyncio
import os
import re
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import aiohttp
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parent.parent

SECRET = "x" * 48
GUILD_ID = 111222333444555666
OTHER_GUILD_ID = 999888777666555444
USER_ID = 424242424242424242


# ---------------------------------------------------------------------------
# Doublures : le dashboard ne lit du bot que get_guild/get_member/is_ready.
# ---------------------------------------------------------------------------

class FakePermissions:
    def __init__(self, administrator: bool):
        self.administrator = administrator


class FakeMember:
    def __init__(self, member_id: int, guild, *, administrator: bool = True):
        self.id = member_id
        self.guild = guild
        self.guild_permissions = FakePermissions(administrator)
        self.roles = []


class FakeRole:
    def __init__(self, role_id: int, name: str, position: int = 1, default: bool = False):
        self.id = role_id
        self.name = name
        self.position = position
        self._default = default

    def is_default(self) -> bool:
        return self._default


class FakeChannel:
    """Un salon réel de discord.py, juste assez pour les tests : le code du
    dashboard vérifie le type avec isinstance, d'où les vraies classes."""

    def __new__(cls, channel_id: int, name: str, kind: str):
        import discord

        base = {
            "text": discord.TextChannel,
            "voice": discord.VoiceChannel,
            "category": discord.CategoryChannel,
        }[kind]
        channel = object.__new__(base)
        channel.id = channel_id
        channel.name = name
        channel.position = channel_id
        return channel


class FakeGuild:
    def __init__(self, guild_id: int, name: str = "Serveur de test"):
        self.id = guild_id
        self.name = name
        self.roles = []
        self.members: dict[int, FakeMember] = {}
        self.text_channels = []
        self.voice_channels = []
        self.categories = []

    def get_member(self, user_id: int):
        return self.members.get(user_id)

    def get_channel(self, channel_id: int):
        every = self.text_channels + self.voice_channels + self.categories
        return next((c for c in every if c.id == channel_id), None)

    def get_role(self, role_id: int):
        return next((r for r in self.roles if r.id == role_id), None)


class FakeBot:
    def __init__(self, *guilds: FakeGuild):
        self.guilds = {guild.id: guild for guild in guilds}

    def get_guild(self, guild_id: int):
        return self.guilds.get(guild_id)

    def is_ready(self) -> bool:
        return True


def csrf_of(html: str) -> str:
    found = re.search(r'name="csrf" value="([^"]+)"', html)
    assert found, "aucun jeton CSRF dans la page"
    return found.group(1)


class DashboardTestCase(unittest.TestCase):
    """Chaque test repart d'un dossier de données vierge."""

    def setUp(self):
        os.environ["DASHBOARD_SECRET"] = SECRET
        # En http : le client de test parle à 127.0.0.1, et un cookie marqué
        # « Secure » ne serait jamais renvoyé. Le comportement en https est
        # vérifié séparément par CookieTest.
        os.environ["DASHBOARD_BASE_URL"] = "http://127.0.0.1"

        self._previous_cwd = os.getcwd()
        self._scratch = tempfile.TemporaryDirectory()
        shutil.copytree(ROOT / "locales", Path(self._scratch.name) / "locales")
        os.chdir(self._scratch.name)

        import guild_settings
        from web import auth

        guild_settings._settings.clear()
        auth._used_links.clear()

        self.guild = FakeGuild(GUILD_ID)
        self.member = FakeMember(USER_ID, self.guild)
        self.guild.members[USER_ID] = self.member

        self.guild.text_channels = [
            FakeChannel(10, "commandes", "text"),
            FakeChannel(11, "annonces", "text"),
            FakeChannel(12, "resultats", "text"),
        ]
        self.guild.voice_channels = [FakeChannel(20, "Attente", "voice")]
        self.guild.categories = [FakeChannel(30, "CLANS", "category")]
        self.everyone = FakeRole(GUILD_ID, "@everyone", 0, default=True)
        self.staff_role = FakeRole(40, "Organisateur", 5)
        self.guild.roles = [self.everyone, self.staff_role, FakeRole(41, "Connexion", 3)]

        self.bot = FakeBot(self.guild, FakeGuild(OTHER_GUILD_ID, "Autre"))

    def tearDown(self):
        os.chdir(self._previous_cwd)
        self._scratch.cleanup()

    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    async def client(self) -> TestClient:
        from web import server

        # Un jar « unsafe » : le cookie de session est posé sur 127.0.0.1, que
        # le jar standard d'aiohttp refuse.
        client = TestClient(
            TestServer(server.build_app(self.bot)),
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
        await client.start_server()
        return client

    async def signed_in(self, client: TestClient, guild_id: int = GUILD_ID) -> None:
        from web import auth

        response = await client.get(f"/d/{auth.make_link(guild_id, USER_ID)}", allow_redirects=False)
        assert response.status == 302, await response.text()


# ---------------------------------------------------------------------------
# Jetons
# ---------------------------------------------------------------------------

class TokenTest(DashboardTestCase):
    def test_signature_is_checked(self):
        from web import auth

        token = auth.make_link(GUILD_ID, USER_ID)
        body, _, signature = token.partition(".")
        self.assertIsNotNone(auth.loads(token))
        # Un corps modifié ne passe plus, même signature à l'identique.
        self.assertIsNone(auth.loads(f"{body}x.{signature}"))
        self.assertIsNone(auth.loads(f"{body}.{signature}x"))
        self.assertIsNone(auth.loads("n'importe quoi"))
        self.assertIsNone(auth.loads(None))

    def test_expired_token_is_refused(self):
        from web import auth

        expired = auth.dumps({"g": GUILD_ID, "u": USER_ID, "exp": time.time() - 1})
        self.assertIsNone(auth.loads(expired))

    def test_link_works_once(self):
        from web import auth

        token = auth.make_link(GUILD_ID, USER_ID)
        self.assertEqual(auth.consume_link(token), (GUILD_ID, USER_ID))
        self.assertIsNone(auth.consume_link(token))

    def test_secret_must_be_long_enough(self):
        from web import auth

        os.environ["DASHBOARD_SECRET"] = "trop-court"
        with self.assertRaises(auth.SecretMissing):
            auth.secret()

    def test_csrf_comparison(self):
        from web import auth

        session = auth.read_session(auth.make_session(GUILD_ID, USER_ID))
        self.assertTrue(auth.check_csrf(session, session["csrf"]))
        self.assertFalse(auth.check_csrf(session, "autre"))
        self.assertFalse(auth.check_csrf(session, None))


# ---------------------------------------------------------------------------
# Accès
# ---------------------------------------------------------------------------

class AccessTest(DashboardTestCase):
    def test_healthz(self):
        async def scenario():
            client = await self.client()
            try:
                response = await client.get("/healthz")
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())["ok"], True)
            finally:
                await client.close()

        self.run_async(scenario())

    def test_link_opens_the_queue_page(self):
        async def scenario():
            client = await self.client()
            try:
                await self.signed_in(client)
                response = await client.get(f"/g/{GUILD_ID}/queue")
                self.assertEqual(response.status, 200)
                body = await response.text()
                self.assertIn("Serveur de test", body)
                self.assertIn('name="queue_name"', body)
            finally:
                await client.close()

        self.run_async(scenario())

    def test_used_link_is_dead(self):
        async def scenario():
            from web import auth

            client = await self.client()
            try:
                token = auth.make_link(GUILD_ID, USER_ID)
                first = await client.get(f"/d/{token}", allow_redirects=False)
                self.assertEqual(first.status, 302)
                second = await client.get(f"/d/{token}", allow_redirects=False)
                self.assertEqual(second.status, 403)
            finally:
                await client.close()

        self.run_async(scenario())

    def test_page_needs_a_session(self):
        async def scenario():
            client = await self.client()
            try:
                response = await client.get(f"/g/{GUILD_ID}/queue")
                self.assertEqual(response.status, 401)
            finally:
                await client.close()

        self.run_async(scenario())

    def test_session_does_not_open_another_guild(self):
        async def scenario():
            client = await self.client()
            try:
                await self.signed_in(client)
                response = await client.get(f"/g/{OTHER_GUILD_ID}/queue")
                self.assertEqual(response.status, 403)
            finally:
                await client.close()

        self.run_async(scenario())

    def test_cookie_flags(self):
        async def scenario():
            from web import auth

            # En production, DASHBOARD_BASE_URL est en https : le cookie de
            # session doit alors porter Secure, HttpOnly et SameSite=Lax.
            os.environ["DASHBOARD_BASE_URL"] = "https://dashboard.test"
            client = await self.client()
            try:
                response = await client.get(
                    f"/d/{auth.make_link(GUILD_ID, USER_ID)}", allow_redirects=False
                )
                raw = response.headers["Set-Cookie"]
                self.assertIn("HttpOnly", raw)
                self.assertIn("Secure", raw)
                self.assertIn("SameSite=Lax", raw)
                self.assertIn("Path=/", raw)
            finally:
                await client.close()

        self.run_async(scenario())

    def test_security_headers(self):
        async def scenario():
            client = await self.client()
            try:
                response = await client.get("/")
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            finally:
                await client.close()

        self.run_async(scenario())

    def test_losing_admin_closes_the_door(self):
        async def scenario():
            client = await self.client()
            try:
                await self.signed_in(client)
                # Rétrogradé APRÈS s'être connecté : le cookie reste valide,
                # les droits sont relus à chaque requête.
                self.member.guild_permissions.administrator = False
                response = await client.get(f"/g/{GUILD_ID}/queue")
                self.assertEqual(response.status, 403)
            finally:
                await client.close()

        self.run_async(scenario())


# ---------------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------------

class SaveTest(DashboardTestCase):
    async def _page(self, client: TestClient) -> str:
        response = await client.get(f"/g/{GUILD_ID}/queue")
        return await response.text()

    def test_post_saves_the_configuration(self):
        async def scenario():
            from guild_settings import get_queue_config

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                response = await client.post(f"/g/{GUILD_ID}/queue", data={
                    "csrf": token,
                    "queue_name": "Soirée 5v5",
                    "num_teams": "3",
                    "team_name_0": "Alpha",
                    "team_name_1": "Bravo",
                    "team_name_2": "Charlie",
                    "team_color_0": "🔴",
                    "team_color_1": "🔵",
                    "team_color_2": "🟢",
                    "max_players_per_team": "5",
                    "session": "Entraînement",
                    "heure": "21:00",
                    "type": "Tournoi",
                    "captains": "1",
                }, allow_redirects=False)
                self.assertEqual(response.status, 302)
                self.assertIn("m=saved", response.headers["Location"])

                config = get_queue_config(GUILD_ID)
                self.assertEqual(config["queue_name"], "Soirée 5v5")
                self.assertEqual(config["num_teams"], 3)
                self.assertEqual(config["team_names"], ["Alpha", "Bravo", "Charlie"])
                self.assertEqual(config["max_players_per_team"], 5)
                self.assertEqual(config["heure"], "21:00")
                self.assertTrue(config["captains"])
                # Les couleurs sont indexées par nom d'équipe, comme sur Discord.
                self.assertEqual(config["team_colors"]["Bravo"], "🔵")
            finally:
                await client.close()

        self.run_async(scenario())

    def test_post_without_csrf_is_refused(self):
        async def scenario():
            from guild_settings import get_queue_config

            client = await self.client()
            try:
                await self.signed_in(client)
                response = await client.post(
                    f"/g/{GUILD_ID}/queue",
                    data={"queue_name": "Pirate", "num_teams": "2"},
                    allow_redirects=False,
                )
                self.assertEqual(response.status, 403)
                self.assertIsNone(get_queue_config(GUILD_ID))
            finally:
                await client.close()

        self.run_async(scenario())

    def test_duplicate_team_names_are_refused(self):
        async def scenario():
            from guild_settings import get_queue_config

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                response = await client.post(f"/g/{GUILD_ID}/queue", data={
                    "csrf": token,
                    "queue_name": "Queue",
                    "num_teams": "2",
                    "team_name_0": "Alpha",
                    "team_name_1": "alpha",
                    "max_players_per_team": "4",
                }, allow_redirects=False)
                self.assertEqual(response.status, 302)
                self.assertIn("m=err_dup", response.headers["Location"])
                self.assertIsNone(get_queue_config(GUILD_ID))
            finally:
                await client.close()

        self.run_async(scenario())

    def test_out_of_range_values_fall_back(self):
        async def scenario():
            from guild_settings import get_queue_config

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                # Un formulaire bricolé ne doit pas créer 9999 équipes.
                response = await client.post(f"/g/{GUILD_ID}/queue", data={
                    "csrf": token,
                    "queue_name": "Queue",
                    "num_teams": "9999",
                    "team_name_0": "Alpha",
                    "team_name_1": "Bravo",
                    "max_players_per_team": "-3",
                }, allow_redirects=False)
                self.assertEqual(response.status, 302)
                config = get_queue_config(GUILD_ID)
                self.assertEqual(config["num_teams"], 2)
                self.assertEqual(config["max_players_per_team"], 4)
            finally:
                await client.close()

        self.run_async(scenario())

    def test_empty_name_is_refused(self):
        async def scenario():
            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                response = await client.post(f"/g/{GUILD_ID}/queue", data={
                    "csrf": token,
                    "queue_name": "   ",
                    "num_teams": "2",
                }, allow_redirects=False)
                self.assertIn("m=err_name", response.headers["Location"])
            finally:
                await client.close()

        self.run_async(scenario())

    def test_preset_round_trip(self):
        async def scenario():
            from guild_settings import get_queue_config, get_queue_presets

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                await client.post(f"/g/{GUILD_ID}/queue", data={
                    "csrf": token, "queue_name": "Scrim", "num_teams": "2",
                    "team_name_0": "Alpha", "team_name_1": "Bravo",
                    "max_players_per_team": "5",
                }, allow_redirects=False)

                saved = await client.post(
                    f"/g/{GUILD_ID}/presets",
                    data={"csrf": token, "name": "Scrim du soir"},
                    allow_redirects=False,
                )
                self.assertIn("m=saved_preset", saved.headers["Location"])
                self.assertEqual([p["name"] for p in get_queue_presets(GUILD_ID)], ["Scrim du soir"])

                # On change la config, puis on recharge le preset.
                await client.post(f"/g/{GUILD_ID}/queue", data={
                    "csrf": token, "queue_name": "Autre chose", "num_teams": "2",
                    "team_name_0": "A", "team_name_1": "B", "max_players_per_team": "2",
                }, allow_redirects=False)
                loaded = await client.post(
                    f"/g/{GUILD_ID}/presets/load",
                    data={"csrf": token, "name": "Scrim du soir"},
                    allow_redirects=False,
                )
                self.assertIn("m=loaded_preset", loaded.headers["Location"])
                config = get_queue_config(GUILD_ID)
                self.assertEqual(config["queue_name"], "Scrim")
                self.assertEqual(config["max_players_per_team"], 5)
                self.assertNotIn("name", config)

                removed = await client.post(
                    f"/g/{GUILD_ID}/presets/delete",
                    data={"csrf": token, "name": "Scrim du soir"},
                    allow_redirects=False,
                )
                self.assertIn("m=deleted_preset", removed.headers["Location"])
                self.assertEqual(get_queue_presets(GUILD_ID), [])
            finally:
                await client.close()

        self.run_async(scenario())

    def test_team_name_cannot_forge_a_mention(self):
        async def scenario():
            from guild_settings import get_queue_config

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                await client.post(f"/g/{GUILD_ID}/queue", data={
                    "csrf": token,
                    "queue_name": "@everyone",
                    "num_teams": "2",
                    "team_name_0": "@here",
                    "team_name_1": "Bravo",
                    "max_players_per_team": "4",
                }, allow_redirects=False)
                config = get_queue_config(GUILD_ID)
                # text_safety.sanitize glisse une espace de largeur nulle : le
                # nom reste lisible, Discord ne notifie personne.
                self.assertNotEqual(config["queue_name"], "@everyone")
                self.assertNotEqual(config["team_names"][0], "@here")
            finally:
                await client.close()

        self.run_async(scenario())


# ---------------------------------------------------------------------------
# Page serveur (l'équivalent de /option)
# ---------------------------------------------------------------------------

class ServerPageTest(DashboardTestCase):
    async def _page(self, client: TestClient) -> str:
        response = await client.get(f"/g/{GUILD_ID}/server")
        assert response.status == 200, response.status
        return await response.text()

    def test_page_lists_channels_and_roles(self):
        async def scenario():
            client = await self.client()
            try:
                await self.signed_in(client)
                body = await self._page(client)
                self.assertIn("# commandes", body)
                self.assertIn("🔊 Attente", body)
                self.assertIn("CLANS", body)
                self.assertIn("@Organisateur", body)
                # @everyone n'est jamais proposé : le choisir comme
                # organisateur donnerait la queue au serveur entier.
                self.assertNotIn("@@everyone", body)
            finally:
                await client.close()

        self.run_async(scenario())

    def test_features_round_trip(self):
        async def scenario():
            from guild_settings import get_features

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                response = await client.post(f"/g/{GUILD_ID}/server/features", data={
                    "csrf": token, "f_leaderboard": "1", "f_mvp": "1",
                }, allow_redirects=False)
                self.assertIn("m=saved_features", response.headers["Location"])

                features = get_features(GUILD_ID)
                self.assertTrue(features["leaderboard"])
                self.assertTrue(features["mvp"])
                # Une case décochée n'est pas envoyée par le navigateur : elle
                # doit donc être lue comme « éteint », pas comme « inchangé ».
                self.assertFalse(features["clan_notice"])
            finally:
                await client.close()

        self.run_async(scenario())

    def test_clans_need_a_category(self):
        async def scenario():
            from guild_settings import get_features, set_resource_id

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                refused = await client.post(f"/g/{GUILD_ID}/server/features", data={
                    "csrf": token, "f_clans": "1",
                }, allow_redirects=False)
                self.assertIn("m=err_clan_category", refused.headers["Location"])
                self.assertFalse(get_features(GUILD_ID)["clans"])

                set_resource_id(GUILD_ID, "category_clan", 30)
                accepted = await client.post(f"/g/{GUILD_ID}/server/features", data={
                    "csrf": token, "f_clans": "1",
                }, allow_redirects=False)
                self.assertIn("m=saved_features", accepted.headers["Location"])
                self.assertTrue(get_features(GUILD_ID)["clans"])
            finally:
                await client.close()

        self.run_async(scenario())

    def test_channels_are_checked_against_the_guild(self):
        async def scenario():
            from guild_settings import get_resource_id

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                await client.post(f"/g/{GUILD_ID}/server/channels", data={
                    "csrf": token,
                    "c_channel_queue_command": "10",
                    "c_voice_queue_waiting": "20",
                    # Un salon textuel là où un vocal est attendu, et un ID
                    # inventé : ni l'un ni l'autre ne doit être mémorisé.
                    "c_channel_queue_announcement": "20",
                    "c_channel_queue_classement": "999999",
                }, allow_redirects=False)

                self.assertEqual(get_resource_id(GUILD_ID, "channel_queue_command"), 10)
                self.assertEqual(get_resource_id(GUILD_ID, "voice_queue_waiting"), 20)
                self.assertIsNone(get_resource_id(GUILD_ID, "channel_queue_announcement"))
                self.assertIsNone(get_resource_id(GUILD_ID, "channel_queue_classement"))
            finally:
                await client.close()

        self.run_async(scenario())

    def test_staff_role_cannot_be_everyone(self):
        async def scenario():
            from guild_settings import get_resource_id

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                response = await client.post(f"/g/{GUILD_ID}/server/roles", data={
                    "csrf": token, "r_role_staff": str(GUILD_ID),
                }, allow_redirects=False)
                self.assertIn("m=err_staff_everyone", response.headers["Location"])
                self.assertIsNone(get_resource_id(GUILD_ID, "role_staff"))
            finally:
                await client.close()

        self.run_async(scenario())

    def test_roles_saved_and_cleared(self):
        async def scenario():
            from guild_settings import get_resource_id

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                await client.post(f"/g/{GUILD_ID}/server/roles", data={
                    "csrf": token, "r_role_staff": "40", "r_role_connexion": "41",
                }, allow_redirects=False)
                self.assertEqual(get_resource_id(GUILD_ID, "role_staff"), 40)
                self.assertEqual(get_resource_id(GUILD_ID, "role_connexion"), 41)

                # « Aucun » retire un rôle facultatif, mais jamais l'organisateur.
                await client.post(f"/g/{GUILD_ID}/server/roles", data={
                    "csrf": token, "r_role_staff": "", "r_role_connexion": "",
                }, allow_redirects=False)
                self.assertEqual(get_resource_id(GUILD_ID, "role_staff"), 40)
                self.assertIsNone(get_resource_id(GUILD_ID, "role_connexion"))
            finally:
                await client.close()

        self.run_async(scenario())

    def test_mmr_values_are_clamped(self):
        async def scenario():
            from guild_settings import get_mmr_config

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                await client.post(f"/g/{GUILD_ID}/server/mmr", data={
                    "csrf": token, "m_enabled": "1",
                    "m_win": "20", "m_loss": "99999", "m_start": "-5",
                    "m_captain_vote_seconds": "abc",
                }, allow_redirects=False)

                config = get_mmr_config(GUILD_ID)
                self.assertTrue(config["enabled"])
                self.assertEqual(config["win"], 20)
                self.assertEqual(config["loss"], 1000)     # ramené au maximum
                self.assertEqual(config["start"], 0)       # ramené au minimum
                self.assertEqual(config["captain_vote_seconds"], 60)  # valeur gardée
                self.assertFalse(config["captains"])       # case décochée
            finally:
                await client.close()

        self.run_async(scenario())

    def test_password_saved_then_cleared_turns_the_feature_off(self):
        async def scenario():
            from guild_settings import get_features, get_queue_password

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                await client.post(f"/g/{GUILD_ID}/server/features",
                                  data={"csrf": token, "f_password": "1"},
                                  allow_redirects=False)
                await client.post(f"/g/{GUILD_ID}/server/password",
                                  data={"csrf": token, "password": "  motdepasse  "},
                                  allow_redirects=False)
                # Espaces retirés, mais rien d'autre : le mot de passe est
                # comparé caractère par caractère à ce que tape un joueur.
                self.assertEqual(get_queue_password(GUILD_ID), "motdepasse")
                self.assertTrue(get_features(GUILD_ID)["password"])

                await client.post(f"/g/{GUILD_ID}/server/password",
                                  data={"csrf": token, "password": ""},
                                  allow_redirects=False)
                self.assertIsNone(get_queue_password(GUILD_ID))
                # Comme dans /option : sans mot de passe, l'option n'a plus
                # rien à demander.
                self.assertFalse(get_features(GUILD_ID)["password"])
            finally:
                await client.close()

        self.run_async(scenario())

    def test_password_is_not_mangled(self):
        async def scenario():
            from guild_settings import get_queue_password

            client = await self.client()
            try:
                await self.signed_in(client)
                token = csrf_of(await self._page(client))
                await client.post(f"/g/{GUILD_ID}/server/password",
                                  data={"csrf": token, "password": "@everyone"},
                                  allow_redirects=False)
                self.assertEqual(get_queue_password(GUILD_ID), "@everyone")
            finally:
                await client.close()

        self.run_async(scenario())

    def test_server_post_needs_csrf(self):
        async def scenario():
            from guild_settings import get_features

            client = await self.client()
            try:
                await self.signed_in(client)
                response = await client.post(f"/g/{GUILD_ID}/server/features",
                                             data={"f_mvp": "1"}, allow_redirects=False)
                self.assertEqual(response.status, 403)
                self.assertFalse(get_features(GUILD_ID)["mvp"])
            finally:
                await client.close()

        self.run_async(scenario())


# ---------------------------------------------------------------------------
# Filet : aucune clé de traduction ne doit s'afficher telle quelle
# ---------------------------------------------------------------------------

class TranslationTest(DashboardTestCase):
    """`t()` renvoie la clé quand elle manque. Une clé oubliée se lirait donc
    « dashboard.feat_mvp_hint » en plein milieu de la page, dans les cinq
    langues. On regarde les pages rendues plutôt que le code."""

    def test_no_raw_key_leaks_into_the_pages(self):
        async def scenario():
            from i18n import LANGUAGES, set_lang

            client = await self.client()
            try:
                await self.signed_in(client)
                for lang in LANGUAGES:
                    set_lang(GUILD_ID, lang)
                    for page in ("queue", "server"):
                        response = await client.get(f"/g/{GUILD_ID}/{page}")
                        body = await response.text()
                        leaks = sorted(set(re.findall(r"dashboard\.[a-z_]+", body)))
                        self.assertEqual(leaks, [], f"{lang}/{page} : clés non traduites")
            finally:
                await client.close()

        self.run_async(scenario())


if __name__ == "__main__":
    unittest.main()
