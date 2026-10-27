import datetime
import os
import tempfile
import unittest

from _load import load

profile = load("reddit-setup", "profile")

TODAY = datetime.date(2026, 10, 27)


def good(**extra):
    data = {
        "username": "u/quiet_brewer",
        "topics": ["home espresso"],
        "terms": ["sour shot", "grind size"],
        "knows": ["I have pulled shots on a Gaggia Classic for three years"],
        "account": {"created": "2026-10-20", "karma": 12},
        "product": None,
    }
    data.update(extra)
    return data


class Check(unittest.TestCase):
    def test_good_profile(self):
        out = profile.check(good(), TODAY)
        self.assertEqual(out["username"], "quiet_brewer")
        self.assertEqual(out["account"]["age_days"], 7)

    def test_needs_topics(self):
        with self.assertRaisesRegex(ValueError, "topics"):
            profile.check(good(topics=[]), TODAY)

    def test_account_date_checked(self):
        with self.assertRaisesRegex(ValueError, "created"):
            profile.check(good(account={"created": "next week", "karma": 1}), TODAY)
        with self.assertRaisesRegex(ValueError, "future"):
            profile.check(good(account={"created": "2026-11-01", "karma": 1}), TODAY)

    def test_karma_whole_number(self):
        with self.assertRaisesRegex(ValueError, "karma"):
            profile.check(good(account={"created": "2026-10-20", "karma": "lots"}), TODAY)

    def test_negative_karma_allowed(self):
        out = profile.check(good(account={"created": "2026-10-20", "karma": -4}), TODAY)
        self.assertEqual(out["account"]["karma"], -4)

    def test_username_shape(self):
        with self.assertRaisesRegex(ValueError, "username"):
            profile.check(good(username="not a name!"), TODAY)

    def test_username_optional(self):
        out = profile.check(good(username=""), TODAY)
        self.assertEqual(out["username"], "")

    def test_one_account_only(self):
        for key in ("accounts", "alt_accounts", "alts", "usernames"):
            with self.assertRaisesRegex(ValueError, "one account"):
                profile.check(good(**{key: ["a", "b"]}), TODAY)

    def test_unknown_key(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            profile.check(good(vote_ring=True), TODAY)

    def test_product_needs_name_and_what(self):
        with self.assertRaisesRegex(ValueError, "product"):
            profile.check(good(product={"url": "https://x.io"}), TODAY)
        out = profile.check(good(product={"name": "Brewlog", "what": "a shot log app", "url": "https://brewlog.app"}),
                            TODAY)
        self.assertEqual(out["product"]["name"], "Brewlog")

    def test_caps_can_be_lowered_not_past_ceiling(self):
        out = profile.check(good(caps={"comments_per_day": 2, "posts_per_day": 0}), TODAY)
        self.assertEqual(out["caps"]["comments_per_day"], 2)
        with self.assertRaisesRegex(ValueError, "ceiling"):
            profile.check(good(caps={"comments_per_day": profile.HARD_CEILING + 1}), TODAY)
        with self.assertRaisesRegex(ValueError, "caps"):
            profile.check(good(caps={"comments_per_day": -1}), TODAY)
        with self.assertRaisesRegex(ValueError, "caps"):
            profile.check(good(caps={"votes_per_day": 3}), TODAY)

    def test_caps_together_stay_under_ceiling(self):
        with self.assertRaisesRegex(ValueError, "together"):
            profile.check(good(caps={"comments_per_day": 8, "posts_per_day": 3}), TODAY)

    def test_product_fields_must_be_text(self):
        for product in ({"name": 5, "what": "x"}, {"name": "x", "what": ["a"]}, {"name": "x", "what": "y", "url": 3}):
            with self.assertRaisesRegex(ValueError, "product"):
                profile.check(good(product=product), TODAY)


class Posting(unittest.TestCase):
    def test_default_manual(self):
        self.assertEqual(profile.check(good(), TODAY)["posting"], "manual")

    def test_approved(self):
        self.assertEqual(profile.check(good(posting="approved"), TODAY)["posting"], "approved")

    def test_no_unattended_mode(self):
        for mode in ("auto", "autonomous", "unattended"):
            with self.assertRaisesRegex(ValueError, "posting"):
                profile.check(good(posting=mode), TODAY)


class Files(unittest.TestCase):
    def test_init_then_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = profile.init(tmp)
            self.assertTrue(os.path.exists(path))
            with self.assertRaises(FileExistsError):
                profile.init(tmp)
            # the template is a valid shape once the blanks are filled
            data = profile.read(tmp)
            self.assertIn("topics", data)

    def test_read_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "reddit-setup"):
                profile.read(tmp)


if __name__ == "__main__":
    unittest.main()
