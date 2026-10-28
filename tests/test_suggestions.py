"""/suggestions : quels messages reçoivent les réactions de vote, et quels emojis."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

import discord

import custom_emojis
from cogs.suggestions import Suggestions

GID, TARGET = 1, 500


def message(channel, *, message_id=900, bot=False):
    return SimpleNamespace(guild=SimpleNamespace(id=GID), author=SimpleNamespace(bot=bot),
                           channel=channel, id=message_id)


def forum_post(post_id, parent_id=TARGET):
    thread = mock.MagicMock(spec=discord.Thread)
    thread.id, thread.parent_id = post_id, parent_id
    return thread


class SuggestionsTest(unittest.TestCase):
    def setUp(self):
        self.cog = Suggestions.__new__(Suggestions)
        self.cog.channels = {GID: TARGET}
        self.cog._app_emojis = None

    def test_text_channel_messages_from_members(self):
        channel = SimpleNamespace(id=TARGET)
        self.assertTrue(self.cog.is_suggestion(message(channel)))
        self.assertFalse(self.cog.is_suggestion(message(channel, bot=True)), "pas les bots")
        self.assertFalse(self.cog.is_suggestion(message(SimpleNamespace(id=TARGET + 1))), "autre salon")

    def test_forum_only_the_first_message_of_a_post(self):
        post = forum_post(700)
        self.assertTrue(self.cog.is_suggestion(message(post, message_id=700)))
        self.assertFalse(self.cog.is_suggestion(message(post, message_id=701)), "une réponse")
        self.assertFalse(self.cog.is_suggestion(message(forum_post(702, parent_id=TARGET + 1), message_id=702)))

    def test_nothing_when_disabled(self):
        self.cog.channels = {}
        self.assertFalse(self.cog.is_suggestion(message(SimpleNamespace(id=TARGET))))

    def test_emojis_found_by_name_with_or_without_emoji_gg_number(self):
        up, down = SimpleNamespace(name="1234_Wobble4"), SimpleNamespace(name="wobble3")
        self.assertIs(custom_emojis.find([up, down], "Wobble4"), up)
        self.assertIs(custom_emojis.find([up, down], "Wobble3"), down)

    def test_vote_emojis_prefer_the_server_then_the_app_then_fallbacks(self):
        server_up = SimpleNamespace(name="Wobble4")
        app_down = SimpleNamespace(name="Wobble3")
        self.cog.bot = SimpleNamespace(fetch_application_emojis=mock.AsyncMock(return_value=[app_down]))
        found, missing = asyncio.run(self.cog.vote_emojis(SimpleNamespace(emojis=[server_up])))
        self.assertEqual((found, missing), ([server_up, app_down], []))

        self.cog._app_emojis = []
        found, missing = asyncio.run(self.cog.vote_emojis(SimpleNamespace(emojis=[])))
        self.assertEqual((found, missing), (["👍", "👎"], ["Wobble4", "Wobble3"]))


if __name__ == "__main__":
    unittest.main()
