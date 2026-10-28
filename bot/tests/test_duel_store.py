"""Les teams de duel dans guild_settings.py : création, invitations, départs,
durée de vie, défis et duels en cours."""

import unittest
from unittest import mock

import guild_settings as gs

GID = 1


class DuelStoreCase(unittest.TestCase):
    def setUp(self):
        # Rien n'est écrit sur le disque : les réglages vivent dans un
        # dictionnaire neuf pour chaque test.
        for patcher in (mock.patch.object(gs, "_settings", {}), mock.patch.object(gs, "save_settings")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def team(self, name="Alpha", leader=1, invited=(), duels=3):
        return gs.create_duel_team(GID, name=name, color="🔴", leader_id=leader, invited=list(invited), duels=duels)


class TeamCreationTest(DuelStoreCase):
    def test_solo_team_is_ready_at_once(self):
        team = self.team()
        self.assertEqual(team["status"], "ready")
        self.assertEqual(team["members"], [1])
        self.assertIs(gs.duel_team_of(GID, 1), team)

    def test_team_with_mates_waits_for_every_invite(self):
        team = self.team(invited=[2, 3])
        self.assertEqual(team["status"], "pending")
        self.assertIsNone(gs.duel_team_of(GID, 2), "une invitation n'est pas une appartenance")
        self.assertEqual(gs.accept_duel_invite(GID, team["id"], 2), "waiting")
        self.assertEqual(gs.accept_duel_invite(GID, team["id"], 3), "ready")
        self.assertEqual(team["members"], [1, 2, 3])
        self.assertEqual(team["status"], "ready")

    def test_only_invited_players_can_accept_and_only_once_in_one_team(self):
        first = self.team(name="Alpha", leader=1, invited=[2])
        second = self.team(name="Bravo", leader=3, invited=[2])
        self.assertEqual(gs.accept_duel_invite(GID, first["id"], 9), "not_invited")
        self.assertEqual(gs.accept_duel_invite(GID, first["id"], 2), "ready")
        self.assertEqual(gs.accept_duel_invite(GID, second["id"], 2), "busy")
        self.assertEqual(gs.accept_duel_invite(GID, "404", 2), "gone")

    def test_name_is_unique_and_cannot_copy_a_clan(self):
        self.team(name="Alpha")
        with self.assertRaisesRegex(ValueError, "name_taken"):
            self.team(name="ALPHA", leader=2)
        gs.create_clan(GID, name="Wolves", leader_id=50)
        with self.assertRaisesRegex(ValueError, "clan_name"):
            self.team(name="wolves", leader=2)

    def test_a_player_belongs_to_one_team(self):
        self.team(leader=1)
        with self.assertRaisesRegex(ValueError, "busy"):
            self.team(name="Bravo", leader=1)
        with self.assertRaisesRegex(ValueError, "busy"):
            self.team(name="Bravo", leader=2, invited=[1])

    def test_size_is_capped(self):
        with self.assertRaisesRegex(ValueError, "size"):
            self.team(invited=range(2, 2 + gs.MAX_TEAM_SIZE))
        self.assertEqual(len(self.team(invited=range(2, 1 + gs.MAX_TEAM_SIZE))["invited"]), gs.MAX_TEAM_SIZE - 1)

    def test_the_leader_is_never_counted_twice(self):
        team = self.team(invited=[1, 2, 2])
        self.assertEqual(team["invited"], [2])


class TeamLifeTest(DuelStoreCase):
    def test_member_leaves_but_leader_leaving_dissolves(self):
        team = self.team(invited=[2, 3])
        gs.accept_duel_invite(GID, team["id"], 2)
        gs.accept_duel_invite(GID, team["id"], 3)
        self.assertEqual(gs.leave_duel_team(GID, team["id"], 3), "left")
        self.assertEqual(team["members"], [1, 2])
        self.assertIsNone(gs.leave_duel_team(GID, team["id"], 3))
        self.assertEqual(gs.leave_duel_team(GID, team["id"], 1), "dissolved")
        self.assertIsNone(gs.get_duel_team(GID, team["id"]))

    def test_a_team_lives_the_chosen_number_of_duels(self):
        team = self.team(duels=3)
        self.assertEqual(gs.consume_duel(GID, team["id"]), "kept")
        self.assertEqual((team["duels_left"], team["played"]), (2, 1))
        gs.consume_duel(GID, team["id"])
        self.assertEqual(gs.consume_duel(GID, team["id"]), "dissolved")
        self.assertIsNone(gs.get_duel_team(GID, team["id"]))
        self.assertIsNone(gs.consume_duel(GID, team["id"]))

    def test_unlimited_team_never_expires(self):
        team = self.team(duels=0)
        for _ in range(20):
            self.assertEqual(gs.consume_duel(GID, team["id"]), "kept")
        self.assertEqual(team["played"], 20)


class RequestsAndSessionsTest(DuelStoreCase):
    def test_a_challenge_is_recorded_once(self):
        request = {"message_id": 10, "thread_id": 11, "from_team": "1", "to_team": "2", "at": 0}
        self.assertTrue(gs.add_duel_request(GID, request))
        self.assertFalse(gs.add_duel_request(GID, {**request, "message_id": 12}))
        self.assertIs(gs.pending_duel_request(GID, "1", "2"), request)
        self.assertIsNone(gs.pending_duel_request(GID, "2", "1"))
        self.assertIs(gs.remove_duel_request(GID, 10), request)
        self.assertIsNone(gs.remove_duel_request(GID, 10))

    def test_a_disappearing_team_takes_its_challenges_with_it(self):
        gs.add_duel_request(GID, {"message_id": 1, "from_team": "1", "to_team": "2"})
        gs.add_duel_request(GID, {"message_id": 2, "from_team": "3", "to_team": "1"})
        gs.add_duel_request(GID, {"message_id": 3, "from_team": "3", "to_team": "2"})
        self.assertEqual(sorted(r["message_id"] for r in gs.remove_duel_requests_of_team(GID, "1")), [1, 2])
        self.assertEqual([r["message_id"] for r in gs.get_duel_requests(GID)], [3])

    def test_duel_numbers_reuse_the_freed_ones(self):
        self.assertEqual(gs.next_duel_number(GID), 1)
        gs.save_duel_session(GID, {"number": 1, "team_a": "1", "team_b": "2"})
        gs.save_duel_session(GID, {"number": 2, "team_a": "3", "team_b": "4"})
        self.assertEqual(gs.next_duel_number(GID), 3)
        gs.delete_duel_session(GID, 1)
        self.assertEqual(gs.next_duel_number(GID), 1)
        self.assertEqual(gs.duel_session_of_team(GID, "4")["number"], 2)
        self.assertIsNone(gs.duel_session_of_team(GID, "1"))

    def test_threads_are_deleted_only_when_due(self):
        gs.add_duel_trash(GID, 100, delete_at=10)
        gs.add_duel_trash(GID, 200, delete_at=20)
        gs.add_duel_trash(GID, None, delete_at=0)
        self.assertEqual(gs.pop_due_duel_trash(GID, 15), [100])
        self.assertEqual(gs.pop_due_duel_trash(GID, 15), [])
        self.assertEqual(gs.pop_due_duel_trash(GID, 25), [200])

    def test_config_defaults_to_off(self):
        self.assertFalse(gs.get_duel_config(GID)["enabled"])
        gs.set_duel_config(GID, enabled=True, category_id=5)
        self.assertEqual(gs.get_duel_config(GID)["category_id"], 5)
        self.assertIsNone(gs.get_duel_config(GID)["requests_channel_id"])


if __name__ == "__main__":
    unittest.main()
