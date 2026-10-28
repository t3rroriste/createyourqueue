"""Classement propre à chaque serveur, et téléchargements refusés vers le réseau interne."""

import asyncio
import unittest

import net_safety
from cogs.classement import Classement, parse_classement


class ClassementParServeurTest(unittest.TestCase):
    def setUp(self):
        self.board = Classement(bot=None)

    def test_stats_isolees_par_serveur(self):
        self.board.add_win(1, 42)
        self.board.add_loss(2, 42)
        self.assertEqual(self.board.players(1)[42]["wins"], 1)
        self.assertEqual(self.board.players(2)[42]["wins"], 0)
        self.assertEqual(self.board.players(2)[42]["losses"], 1)
        self.assertEqual(self.board.players(3), {})

    def test_reset_d_un_serveur_ne_touche_pas_les_autres(self):
        self.board.add_win(1, 42)
        self.board.add_win(2, 42)
        self.board.guild_stats.pop(1, None)
        self.assertEqual(self.board.players(1), {})
        self.assertEqual(self.board.players(2)[42]["wins"], 1)

    def test_compteur_de_queues_par_serveur(self):
        self.board.record_queue(1)
        self.board.record_queue(1)
        self.board.record_queue(2)
        self.assertEqual(self.board.server_stats["guilds"], {"1": 2, "2": 1})
        self.assertEqual(self.board.server_stats["total_queues"], 3)

    def test_nouveau_format_relu(self):
        data = {"10": {"42": {"wins": 3, "losses": 1, "streak": 2, "max_streak": 2}}}
        parsed = parse_classement(data)
        self.assertEqual(parsed[10][42]["wins"], 3)
        self.assertEqual(parsed[10][42]["weekly_wins"], 0)

    def test_ancien_format_rattache_au_serveur_support(self):
        from config import SUPPORT_GUILD_ID
        parsed = parse_classement({"42": {"wins": 5, "streak": 0, "max_streak": 4}})
        self.assertEqual(list(parsed), [SUPPORT_GUILD_ID])
        self.assertEqual(parsed[SUPPORT_GUILD_ID][42]["wins"], 5)


class NetSafetyTest(unittest.TestCase):
    def test_adresses_internes_refusees(self):
        for address in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "10.0.0.1",
                        "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0"):
            with self.subTest(address=address):
                self.assertFalse(net_safety.is_public_address(address))
        self.assertTrue(net_safety.is_public_address("8.8.8.8"))

    def test_ip_en_clair_refusee_sans_requete(self):
        for url in ("http://127.0.0.1/x.png", "http://[::1]/x.png", "http://169.254.169.254/latest"):
            with self.subTest(url=url):
                self.assertIsNone(asyncio.run(net_safety.safe_fetch(url, max_bytes=1024)))

    def test_nom_qui_pointe_en_interne_refuse(self):
        async def resolve():
            return await net_safety.PublicOnlyResolver().resolve("localhost")
        with self.assertRaises(OSError):
            asyncio.run(resolve())

    def test_schema_non_http_refuse(self):
        self.assertIsNone(asyncio.run(net_safety.safe_fetch("file:///etc/passwd", max_bytes=1024)))


if __name__ == "__main__":
    unittest.main()
