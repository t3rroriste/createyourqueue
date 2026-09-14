"""Le calcul du MMR (mmr.py) : points par partie, bonus, paliers."""

import unittest

import mmr

CONFIG = {"win": 15, "loss": 12, "mvp_bonus": 8, "streak_bonus": 0}
TIERS = {"tiers": [
    {"name": "Or", "min": 1000},
    {"name": "Bronze", "min": 0},
    {"name": "Argent", "min": "800"},
    {"name": "Cassé", "min": "abc"},
]}


class DeltaTest(unittest.TestCase):
    def test_win_and_loss(self):
        self.assertEqual(mmr.delta(CONFIG, won=True), 15)
        self.assertEqual(mmr.delta(CONFIG, won=False), -12)

    def test_mvp_bonus_counts_even_when_losing(self):
        self.assertEqual(mmr.delta(CONFIG, won=False, is_mvp=True), -4)

    def test_streak_bonus_only_on_wins(self):
        config = {**CONFIG, "streak_bonus": 5}
        self.assertEqual(mmr.delta(config, won=True, streak=3), 25)
        self.assertEqual(mmr.delta(config, won=True, streak=1), 15)
        self.assertEqual(mmr.delta(config, won=False, streak=3), -12)

    def test_mmr_never_goes_below_zero(self):
        self.assertEqual(mmr.apply(CONFIG, 5, won=False), (0, -5))


class TierTest(unittest.TestCase):
    def test_invalid_thresholds_are_ignored_and_tiers_sorted(self):
        self.assertEqual([tier["name"] for tier in mmr.sorted_tiers(TIERS)], ["Bronze", "Argent", "Or"])

    def test_current_and_next_tier(self):
        self.assertEqual(mmr.tier_for(TIERS, 950)["name"], "Argent")
        self.assertEqual(mmr.next_tier(TIERS, 950)["name"], "Or")
        self.assertIsNone(mmr.next_tier(TIERS, 5000))
        self.assertIsNone(mmr.tier_for({"tiers": []}, 100))

    def test_progress_is_full_at_the_top(self):
        self.assertEqual(mmr.progress(TIERS, 5000), (1, 1))

    def test_change_always_shows_its_sign(self):
        self.assertEqual([mmr.format_change(x) for x in (15, -12, 0)], ["+15", "-12", "±0"])


if __name__ == "__main__":
    unittest.main()
