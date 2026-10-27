import datetime
import json
import os
import tempfile
import unittest

from _load import load

capture = load("reddit-setup", "capture")

NOW = datetime.datetime(2026, 10, 27, 12, 0, 0, tzinfo=datetime.timezone.utc)


def listing(**extra):
    raw = {
        "kind": "listing", "source": "new", "url": "https://www.reddit.com/r/espresso/new/",
        "items": [{
            "url": "https://www.reddit.com/r/espresso/comments/1abc2d/first_shot_sour/",
            "title": "First shot is sour, what am I doing wrong?", "sub": "r/espresso",
            "author": "u/beanhead", "age": "5 hr. ago", "score": "12", "comments": "3 comments",
            "body": "Using a <b>Gaggia</b> &amp; fresh beans.",
        }],
    }
    raw.update(extra)
    return raw


class ParseCount(unittest.TestCase):
    def test_forms(self):
        cases = {"1.2k members": 1200, "12,345": 12345, "1.5M": 1500000, "3 comments": 3, "98": 98,
                 "4.1K weekly visitors": 4100, 7: 7, "-3": -3, "2.3m": 2300000}
        for raw, want in cases.items():
            self.assertEqual(capture.parse_count(raw), want, raw)

    def test_unknown_is_none(self):
        for raw in ("Vote", "•", "", None, "score hidden"):
            self.assertIsNone(capture.parse_count(raw), raw)

    def test_bool_is_not_a_count(self):
        self.assertIsNone(capture.parse_count(True))


class ParseAge(unittest.TestCase):
    def test_relative(self):
        cases = {
            "5 hr. ago": "2026-10-27T07:00:00Z", "5h": "2026-10-27T07:00:00Z",
            "30 min. ago": "2026-10-27T11:30:00Z", "45m": "2026-10-27T11:15:00Z",
            "2 days ago": "2026-10-25T12:00:00Z", "1d": "2026-10-26T12:00:00Z",
            "3 wk. ago": "2026-10-06T12:00:00Z", "1 mo. ago": "2026-09-27T12:00:00Z",
            "2y": "2024-10-27T12:00:00Z", "just now": "2026-10-27T12:00:00Z",
            "10 sec. ago": "2026-10-27T11:59:50Z",
        }
        for raw, want in cases.items():
            self.assertEqual(capture.parse_age(raw, NOW), want, raw)

    def test_absolute(self):
        self.assertEqual(capture.parse_age("2026-10-20", NOW), "2026-10-20T00:00:00Z")
        self.assertEqual(capture.parse_age("2026-10-20T08:30:00Z", NOW), "2026-10-20T08:30:00Z")
        self.assertEqual(capture.parse_age("2026-10-20T08:30:00+02:00", NOW), "2026-10-20T06:30:00Z")

    def test_unknown(self):
        for raw in ("", None, "yesterday-ish", "edited", "99999999999 years ago"):
            self.assertIsNone(capture.parse_age(raw, NOW), raw)

    def test_month_name_dates(self):
        self.assertEqual(capture.parse_age("Created Jan 25, 2008", NOW), "2008-01-25T00:00:00Z")
        self.assertEqual(capture.parse_age("Oct 20, 2026", NOW), "2026-10-20T00:00:00Z")
        self.assertEqual(capture.parse_age("Cake day: September 3, 2019", NOW), "2019-09-03T00:00:00Z")


class ParseCountEdges(unittest.TestCase):
    def test_overflow_and_unicode_minus(self):
        self.assertIsNone(capture.parse_count(float("inf")))
        self.assertEqual(capture.parse_count("−3"), -3)


class NormaliseListing(unittest.TestCase):
    def test_happy_path(self):
        out = capture.normalise(listing(), NOW)
        self.assertEqual(out["kind"], "listing")
        self.assertEqual(out["captured"], "2026-10-27T12:00:00Z")
        self.assertEqual(out["pages"], 1)
        self.assertFalse(out["blocked"])
        item = out["items"][0]
        self.assertEqual(item["id"], "t3_1abc2d")
        self.assertEqual(item["sub"], "espresso")
        self.assertEqual(item["author"], "beanhead")
        self.assertEqual(item["created"], "2026-10-27T07:00:00Z")
        self.assertEqual(item["age_text"], "5 hr. ago")
        self.assertEqual((item["score"], item["comments"]), (12, 3))
        self.assertEqual(item["body"], "Using a Gaggia & fresh beans.")
        self.assertFalse(item["locked"])

    def test_listing_source_must_be_known(self):
        with self.assertRaisesRegex(ValueError, "source"):
            capture.normalise(listing(source="trending"), NOW)

    def test_home_feed_is_a_listing(self):
        out = capture.normalise(listing(source="home", url="https://www.reddit.com/"), NOW)
        self.assertEqual(out["source"], "home")

    def test_item_problems_are_all_reported(self):
        raw = listing()
        raw["items"].append({"url": "https://example.com/x", "sub": "espresso"})
        with self.assertRaises(ValueError) as err:
            capture.normalise(raw, NOW)
        msg = str(err.exception)
        self.assertIn("item 2", msg)
        self.assertIn("title", msg)
        self.assertIn("reddit", msg)

    def test_page_url_must_be_reddit(self):
        with self.assertRaisesRegex(ValueError, "url"):
            capture.normalise(listing(url="https://google.com/search?q=reddit"), NOW)

    def test_unknown_kind(self):
        with self.assertRaisesRegex(ValueError, "kind"):
            capture.normalise({"kind": "dm", "url": "https://www.reddit.com/", "items": []}, NOW)

    def test_unknown_item_field_rejected(self):
        raw = listing()
        raw["items"][0]["upvote_now"] = True
        with self.assertRaisesRegex(ValueError, "upvote_now"):
            capture.normalise(raw, NOW)

    def test_long_body_truncated(self):
        raw = listing()
        raw["items"][0]["body"] = "word " * 2000
        item = capture.normalise(raw, NOW)["items"][0]
        self.assertLessEqual(len(item["body"]), capture.MAX_TEXT)
        self.assertTrue(item["truncated"])

    def test_pages_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "pages"):
            capture.normalise(listing(pages=0), NOW)

    def test_blocked_capture_needs_no_items(self):
        raw = {"kind": "listing", "source": "new", "url": "https://www.reddit.com/r/espresso/new/",
               "blocked": True, "note": "captcha shown", "items": []}
        out = capture.normalise(raw, NOW)
        self.assertTrue(out["blocked"])
        self.assertEqual(out["note"], "captcha shown")

    def test_blocked_capture_skips_kind_checks(self):
        for raw in ({"kind": "listing", "url": "https://www.reddit.com/", "blocked": True, "note": "captcha"},
                    {"kind": "rules", "url": "https://old.reddit.com/r/x/about/rules", "blocked": True},
                    {"kind": "thread", "url": "https://accounts.reddit.com/login", "blocked": True}):
            self.assertTrue(capture.normalise(raw, NOW)["blocked"], raw)

    def test_relative_ages_count_from_captured(self):
        out = capture.normalise(listing(captured="2026-10-20T12:00:00Z"), NOW)
        self.assertEqual(out["items"][0]["created"], "2026-10-20T07:00:00Z")

    def test_user_about(self):
        raw = {"kind": "user_about", "url": "https://www.reddit.com/user/quiet_brewer/",
               "items": [{"name": "u/quiet_brewer", "karma": "1,204", "created": "Oct 20, 2026"}]}
        item = capture.normalise(raw, NOW)["items"][0]
        self.assertEqual((item["name"], item["karma"]), ("quiet_brewer", 1204))
        self.assertEqual(item["created"], "2026-10-20T00:00:00Z")


class NormaliseOtherKinds(unittest.TestCase):
    def test_sub_search(self):
        raw = {"kind": "sub_search", "url": "https://www.reddit.com/search/?q=espresso&type=communities",
               "query": "espresso",
               "items": [{"name": "r/espresso", "members": "1.2M members", "description": "All things"},
                         {"name": "r/Coffee", "members": "3.4m"}]}
        out = capture.normalise(raw, NOW)
        self.assertEqual(out["query"], "espresso")
        self.assertEqual([i["name"] for i in out["items"]], ["espresso", "Coffee"])
        self.assertEqual(out["items"][0]["members"], 1200000)

    def test_sub_about(self):
        raw = {"kind": "sub_about", "url": "https://www.reddit.com/r/espresso/",
               "items": [{"name": "espresso", "members": "1.2M", "weekly_visitors": "210K",
                          "weekly_contributions": "4.5K", "created": "2010-05-01"}]}
        item = capture.normalise(raw, NOW)["items"][0]
        self.assertEqual((item["weekly_visitors"], item["weekly_contributions"]), (210000, 4500))
        self.assertEqual(item["created"], "2010-05-01T00:00:00Z")

    def test_rules(self):
        raw = {"kind": "rules", "sub": "r/espresso", "url": "https://old.reddit.com/r/espresso/about/rules",
               "items": [{"title": "No AI-generated content", "text": "Posts written by AI are removed."},
                         {"title": "Be kind"}]}
        out = capture.normalise(raw, NOW)
        self.assertEqual(out["sub"], "espresso")
        self.assertEqual(out["items"][1]["text"], "")
        self.assertEqual(out["items"][0]["number"], 1)

    def test_rules_need_sub(self):
        raw = {"kind": "rules", "url": "https://old.reddit.com/r/espresso/about/rules",
               "items": [{"title": "Be kind"}]}
        with self.assertRaisesRegex(ValueError, "sub"):
            capture.normalise(raw, NOW)

    def test_thread(self):
        raw = {"kind": "thread", "url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/",
               "post": {"url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/", "title": "Sour shots",
                        "sub": "espresso", "author": "beanhead", "age": "5h", "score": "12", "comments": "2"},
               "items": [{"author": "AutoModerator", "text": "Read the wiki", "score": "1", "age": "5h"},
                         {"author": "pro", "text": "Grind finer and pull longer.", "score": "9", "age": "4h"}]}
        out = capture.normalise(raw, NOW)
        self.assertEqual(out["post"]["id"], "t3_1abc2d")
        self.assertTrue(out["items"][0]["bot"])
        self.assertFalse(out["items"][1]["bot"])

    def test_profile(self):
        raw = {"kind": "profile", "url": "https://www.reddit.com/user/me/comments/",
               "items": [{"url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/kx9zz1/",
                          "sub": "espresso", "type": "comment", "text": "grind finer", "score": "4",
                          "age": "2d", "removed": True}]}
        item = capture.normalise(raw, NOW)["items"][0]
        self.assertEqual(item["id"], "t1_kx9zz1")
        self.assertTrue(item["removed"])

    def test_profile_type_checked(self):
        raw = {"kind": "profile", "url": "https://www.reddit.com/user/me/",
               "items": [{"url": "https://www.reddit.com/r/a/comments/1/x/", "sub": "aa", "type": "vote"}]}
        with self.assertRaisesRegex(ValueError, "type"):
            capture.normalise(raw, NOW)


class Budget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write_raw(self, raw):
        path = os.path.join(self.dir, "inbox.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh)
        return path

    def test_add_needs_a_run(self):
        with self.assertRaisesRegex(ValueError, "start"):
            capture.add(self.dir, self.write_raw(listing()), NOW)

    def test_add_saves_and_counts(self):
        capture.start(self.dir, NOW, limit=5)
        path = capture.add(self.dir, self.write_raw(listing(pages=2)), NOW)
        self.assertTrue(os.path.basename(path).startswith("0001-listing"))
        self.assertEqual(capture.budget(self.dir)["used"], 2)
        self.assertEqual(len(capture.load_all(self.dir)), 1)
        self.assertEqual(len(capture.load_all(self.dir, kind="rules")), 0)

    def test_inbox_removed_after_add(self):
        capture.start(self.dir, NOW)
        raw = self.write_raw(listing())
        capture.add(self.dir, raw, NOW)
        self.assertFalse(os.path.exists(raw))

    def test_over_budget_refused(self):
        capture.start(self.dir, NOW, limit=2)
        capture.add(self.dir, self.write_raw(listing(pages=2)), NOW)
        with self.assertRaisesRegex(ValueError, "budget"):
            capture.add(self.dir, self.write_raw(listing()), NOW)

    def test_limit_has_a_ceiling(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            capture.start(self.dir, NOW, limit=capture.MAX_LIMIT + 1)

    def test_blocked_halts_run(self):
        capture.start(self.dir, NOW)
        blocked = {"kind": "listing", "source": "new", "url": "https://www.reddit.com/r/a/new/",
                   "blocked": True, "note": "you are doing that too much", "items": []}
        capture.add(self.dir, self.write_raw(blocked), NOW)
        self.assertIn("too much", capture.budget(self.dir)["halted"])
        with self.assertRaisesRegex(ValueError, "halted"):
            capture.add(self.dir, self.write_raw(listing()), NOW)

    def test_restart_after_halt_needs_user_check(self):
        capture.start(self.dir, NOW)
        blocked = {"kind": "listing", "source": "new", "url": "https://www.reddit.com/r/a/new/",
                   "blocked": True, "note": "captcha", "items": []}
        capture.add(self.dir, self.write_raw(blocked), NOW)
        later = NOW + datetime.timedelta(hours=1)
        with self.assertRaisesRegex(ValueError, "checked"):
            capture.start(self.dir, later)
        capture.start(self.dir, later, user_checked=True)
        self.assertIsNone(capture.budget(self.dir)["halted"])

    def test_old_run_is_replaced(self):
        capture.start(self.dir, NOW, limit=2)
        capture.add(self.dir, self.write_raw(listing(pages=2)), NOW)
        run = capture.start(self.dir, NOW + capture.RUN_WINDOW + datetime.timedelta(minutes=1), limit=5)
        self.assertEqual((run["limit"], run["used"]), (5, 0))

    def test_restart_after_a_day_is_fine(self):
        capture.start(self.dir, NOW)
        blocked = {"kind": "listing", "source": "new", "url": "https://www.reddit.com/r/a/new/",
                   "blocked": True, "note": "captcha", "items": []}
        capture.add(self.dir, self.write_raw(blocked), NOW)
        capture.start(self.dir, NOW + datetime.timedelta(hours=25))
        self.assertEqual(capture.budget(self.dir)["used"], 0)

    def test_start_continues_a_recent_run(self):
        capture.start(self.dir, NOW, limit=3)
        capture.add(self.dir, self.write_raw(listing(pages=3)), NOW)
        run = capture.start(self.dir, NOW + datetime.timedelta(minutes=30), limit=60)
        self.assertEqual((run["limit"], run["used"]), (3, 3))
        with self.assertRaisesRegex(ValueError, "budget"):
            capture.add(self.dir, self.write_raw(listing()), NOW + datetime.timedelta(minutes=31))

    def test_daily_maximum_across_runs(self):
        t = NOW
        for _ in range(capture.DAILY_MAX // capture.MAX_LIMIT):
            capture.start(self.dir, t, limit=capture.MAX_LIMIT)
            capture.add(self.dir, self.write_raw(listing(pages=capture.MAX_LIMIT)), t)
            t += capture.RUN_WINDOW + datetime.timedelta(minutes=1)
        capture.start(self.dir, t)
        with self.assertRaisesRegex(ValueError, "24 hours"):
            capture.add(self.dir, self.write_raw(listing()), t)
        later = NOW + datetime.timedelta(hours=25)
        capture.start(self.dir, later + capture.RUN_WINDOW)
        capture.add(self.dir, self.write_raw(listing()), later + capture.RUN_WINDOW)

    def test_halt_without_a_run(self):
        capture.halt(self.dir, "captcha on the search page", NOW)
        self.assertIn("captcha", capture.budget(self.dir)["halted"])
        with self.assertRaisesRegex(ValueError, "checked"):
            capture.start(self.dir, NOW + datetime.timedelta(minutes=5))

    def test_blocked_add_without_a_run_still_halts(self):
        blocked = {"kind": "listing", "url": "https://www.reddit.com/", "blocked": True, "note": "rate limited"}
        capture.add(self.dir, self.write_raw(blocked), NOW)
        self.assertIn("rate limited", capture.budget(self.dir)["halted"])

    def test_numbering_past_9999(self):
        capture.start(self.dir, NOW)
        with open(os.path.join(self.dir, "9999-listing.json"), "w") as fh:
            json.dump(capture.normalise(listing(), NOW), fh)
        first = capture.add(self.dir, self.write_raw(listing()), NOW)
        second = capture.add(self.dir, self.write_raw(listing()), NOW)
        self.assertNotEqual(first, second)
        self.assertEqual(len(capture.load_all(self.dir)), 3)
        self.assertTrue(capture.load_all(self.dir)[-1] is not None)

    def test_stored_capture_cannot_be_added_again(self):
        capture.start(self.dir, NOW)
        stored = capture.add(self.dir, self.write_raw(listing()), NOW)
        with self.assertRaisesRegex(ValueError, "already stored"):
            capture.add(self.dir, stored, NOW)

    def test_bad_capture_is_kept_for_fixing(self):
        capture.start(self.dir, NOW)
        raw = self.write_raw({"kind": "listing", "url": "https://www.reddit.com/", "items": []})
        with self.assertRaises(ValueError):
            capture.add(self.dir, raw, NOW)
        self.assertTrue(os.path.exists(raw))
        self.assertEqual(capture.budget(self.dir)["used"], 0)


if __name__ == "__main__":
    unittest.main()
