"""L'arrivée du bot sur un serveur : un message vers le tableau de bord,
et plus aucune étape de configuration dans Discord."""

import unittest
from types import SimpleNamespace
from unittest import mock

import guild_settings as gs
from cogs import welcome

GID = 4242


class FakeChannel:
    def __init__(self, name: str, writable: bool = True):
        self.name = name
        self.writable = writable
        self.sent = []

    def permissions_for(self, _member):
        return SimpleNamespace(send_messages=self.writable)

    async def send(self, content=None, **kwargs):
        self.sent.append((content, kwargs))
        return SimpleNamespace(id=1)


class FakeGuild:
    def __init__(self, *channels: FakeChannel):
        self.id = GID
        self.name = "Serveur test"
        self.text_channels = list(channels)
        self.me = object()


class MessageDArriveeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = welcome.Welcome(mock.MagicMock())

    async def test_un_seul_message_vers_le_dashboard(self):
        bruit = FakeChannel("bavardage")
        general = FakeChannel("general")
        guild = FakeGuild(bruit, general)

        await self.cog.on_guild_join(guild)

        self.assertEqual(bruit.sent, [], "un seul salon reçoit le message")
        self.assertEqual(len(general.sent), 1)
        content, kwargs = general.sent[0]
        self.assertIsNone(content, "tout est dans l'embed")
        embed = kwargs["embed"]
        self.assertIn(welcome.JOIN_TITLE, embed.description)
        self.assertIn(welcome.JOIN_BODY, embed.description)
        self.assertIn(f"> {welcome.DASHBOARD_URL}", embed.description)

        # Un seul bouton, de type lien : il ouvre le site, il n'appelle
        # jamais le bot, donc il marche encore après n'importe quelle panne.
        buttons = kwargs["view"].children
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].label, "Dashboard")
        self.assertEqual(buttons[0].url, welcome.DASHBOARD_URL)
        self.assertIsNone(buttons[0].custom_id, "un bouton de lien n'a rien à restaurer")

    async def test_sans_salon_prefere_le_premier_ou_le_bot_peut_ecrire(self):
        mur = FakeChannel("annonces", writable=False)
        ouvert = FakeChannel("blabla")
        await self.cog.on_guild_join(FakeGuild(mur, ouvert))
        self.assertEqual(mur.sent, [])
        self.assertEqual(len(ouvert.sent), 1)

    async def test_aucun_salon_ou_ecrire_ne_casse_rien(self):
        mur = FakeChannel("annonces", writable=False)
        await self.cog.on_guild_join(FakeGuild(mur))
        self.assertEqual(mur.sent, [])


class ServeurPretTest(unittest.TestCase):
    """Sans assistant à l'arrivée, c'est le tableau de bord qui débloque
    les commandes : désigner les salons obligatoires suffit."""

    def setUp(self):
        for patcher in (mock.patch.object(gs, "_settings", {}),
                        mock.patch.object(gs, "save_settings")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_un_serveur_neuf_n_est_pas_pret(self):
        self.assertFalse(gs.is_setup_complete(GID))

    def test_les_salons_designes_suffisent(self):
        required = [key for key, _kind, needed in gs.WIZARD_SLOTS if needed]
        for index, key in enumerate(required):
            gs.set_resource_id(GID, key, 100 + index)
            if key != required[-1]:
                self.assertFalse(gs.is_setup_complete(GID),
                                 "il manque encore un salon obligatoire")
        self.assertTrue(gs.is_setup_complete(GID))

    def test_l_assistant_discord_marche_toujours(self):
        gs.mark_setup_complete(GID, 7)
        self.assertTrue(gs.is_setup_complete(GID))


if __name__ == "__main__":
    unittest.main()
