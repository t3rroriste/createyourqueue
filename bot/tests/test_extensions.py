"""Les cogs : chacun s'importe, le bot principal les charge tous, et /help
liste exactement ses commandes."""

import asyncio
import importlib
import os
import tempfile
import unittest

import discord
from discord.ext import commands

import config

ALL_EXTENSIONS = (config.INITIAL_EXTENSIONS + config.WELCOME_EXTENSIONS
                  + config.TEMPORARY_EXTENSIONS + config.MODMAIL_EXTENSIONS)


async def load_main_bot() -> list[str]:
    intents = discord.Intents.default()
    intents.members = intents.message_content = intents.voice_states = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as scratch:
        # Toute écriture éventuelle d'un cog atterrit ici, jamais dans data/.
        os.chdir(scratch)
        try:
            async with bot:
                for name in config.INITIAL_EXTENSIONS + config.WELCOME_EXTENSIONS:
                    await bot.load_extension(name)
                return [command.name for command in bot.tree.get_commands()]
        finally:
            os.chdir(previous)


class ExtensionsTest(unittest.TestCase):
    def test_every_extension_imports_and_has_setup(self):
        for name in ALL_EXTENSIONS:
            with self.subTest(extension=name):
                module = importlib.import_module(name)
                self.assertTrue(callable(getattr(module, "setup", None)))

    def test_main_bot_loads_and_help_matches_commands(self):
        names = asyncio.run(load_main_bot())
        self.assertEqual(len(names), len(set(names)), "une commande est déclarée deux fois")

        from cogs.help import CATEGORIES
        cited = {str(item[0]).lstrip("/").split(" ")[0]
                 for category in CATEGORIES.values() for item in category["commands"]}
        self.assertEqual(sorted(cited - set(names)), [], "/help cite une commande qui n'existe pas")
        self.assertEqual(sorted(set(names) - cited), [], "une commande manque dans /help")

        # Une faute de frappe dans la liste laisserait la commande ouverte
        # sur les serveurs non configurés, sans que rien ne le signale.
        self.assertEqual(sorted(config.SETUP_REQUIRED_COMMANDS - set(names)), [],
                         "SETUP_REQUIRED_COMMANDS cite une commande qui n'existe pas")


if __name__ == "__main__":
    unittest.main()
