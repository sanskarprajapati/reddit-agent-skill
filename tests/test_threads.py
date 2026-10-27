import datetime
import unittest

from _load import load

threads = load("reddit-threads", "threads")

NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.timezone.utc)
PROFILE = {"username": "quiet_brewer", "topics": ["home espresso"], "terms": ["grinder", "sour shot"]}


def post(pid, title, hours=3, comments=1, sub="espresso", author="someone", body="", locked=False, score=5):
    created = (NOW - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": "t3_" + pid, "url": "https://www.reddit.com/r/%s/comments/%s/x/" % (sub, pid), "title": title,
            "sub": sub, "author": author, "bot": False, "created": created, "score": score, "comments": comments,
            "locked": locked, "body": body, "flair": ""}


def listing(items, source="new", captured="2026-10-27T12:00:00Z"):
    return {"kind": "listing", "source": source, "captured": captured, "url": "https://www.reddit.com/",
            "items": items, "blocked": False}


class Score(unittest.TestCase):
    def test_fresh_relevant_unanswered_question_scores_high(self):
        good = threads.score(post("a", "Why is my shot sour? New grinder", hours=2, comments=0), PROFILE, NOW)
        stale = threads.score(post("b", "My grinder setup", hours=24 * 6, comments=40), PROFILE, NOW)
        self.assertGreater(good["score"], 80)
        self.assertLess(stale["score"], good["score"])

    def test_unknowns_are_listed(self):
        p = post("a", "grinder?")
        p["created"], p["comments"] = None, None
        out = threads.score(p, PROFILE, NOW)
        self.assertIn("age", out["unknown"])
        self.assertIn("comments", out["unknown"])

    def test_answered_well_drops_room(self):
        thread = {"kind": "thread", "post": post("a", "Sour shot?"), "items": [
            {"author": "AutoModerator", "bot": True, "text": "x " * 40, "score": 50},
            {"author": "pro", "bot": False, "text": "Grind finer. " * 10, "score": 12}]}
        self.assertTrue(threads.answered_well(thread))
        thin = {"kind": "thread", "post": post("a", "Sour shot?"),
                "items": [{"author": "pro", "bot": False, "text": "grind finer", "score": 12}]}
        self.assertFalse(threads.answered_well(thin))


class Rank(unittest.TestCase):
    def test_filters(self):
        caps = [listing([
            post("a", "Sour shot help?"),
            post("b", "Locked grinder thread?", locked=True),
            post("c", "Old grinder question?", hours=24 * 200),
            post("d", "My own grinder question?", author="quiet_brewer"),
            post("e", "grinder in a banned sub?", sub="NoAI"),
            post("f", "grinder bot post?", author="RemindMeBot"),
            post("g", "grinder I already answered?"),
            post("h", "cats are great", hours=1),
        ])]
        log = [{"url": "https://www.reddit.com/r/espresso/comments/g/x/kx1/", "status": "posted"}]
        out = threads.rank(caps, PROFILE, {"espresso": "ok", "noai": "skip"}, log, [], NOW)
        self.assertEqual([t["id"] for t in out["ranked"]], ["t3_a"])
        reasons = {t["id"]: t["why_left_out"] for t in out["left_out"]}
        self.assertIn("locked", reasons["t3_b"])
        self.assertIn("archived", reasons["t3_c"])
        self.assertIn("your own", reasons["t3_d"])
        self.assertIn("bans AI", reasons["t3_e"])
        self.assertIn("bot", reasons["t3_f"])
        self.assertIn("already", reasons["t3_g"])
        self.assertIn("off topic", reasons["t3_h"])

    def test_rules_state_attached(self):
        caps = [listing([post("a", "grinder?", sub="pourover")], source="home")]
        out = threads.rank(caps, PROFILE, {}, [], [], NOW)
        self.assertEqual(out["ranked"][0]["rules"], "missing")
        self.assertEqual(out["ranked"][0]["found_in"], ["home"])

    def test_dedupe_keeps_latest_numbers(self):
        caps = [listing([post("a", "grinder?", comments=1)], captured="2026-10-27T10:00:00Z"),
                listing([post("a", "grinder?", comments=9)], source="search", captured="2026-10-27T11:00:00Z")]
        out = threads.rank(caps, PROFILE, {"espresso": "ok"}, [], [], NOW)
        self.assertEqual(len(out["ranked"]), 1)
        self.assertEqual(out["ranked"][0]["comments"], 9)
        self.assertEqual(out["ranked"][0]["found_in"], ["new", "search"])

    def test_thread_capture_marks_answered(self):
        caps = [listing([post("a", "sour shot?", comments=2)]),
                {"kind": "thread", "captured": "2026-10-27T12:00:00Z", "post": post("a", "sour shot?"), "blocked": False,
                 "items": [{"author": "pro", "bot": False, "text": "Grind finer and dose up. " * 6, "score": 30}]}]
        out = threads.rank(caps, PROFILE, {"espresso": "ok"}, [], [], NOW)
        self.assertTrue(out["ranked"][0]["answered_well"])

    def test_already_drafted_left_out(self):
        caps = [listing([post("a", "grinder?")])]
        drafts = [{"url": "https://www.reddit.com/r/espresso/comments/a/x/", "status": "drafted"}]
        out = threads.rank(caps, PROFILE, {"espresso": "ok"}, [], drafts, NOW)
        self.assertEqual(out["ranked"], [])

    def test_freshness_note(self):
        caps = [listing([post("a", "grinder?")], captured="2026-10-20T12:00:00Z")]
        out = threads.rank(caps, PROFILE, {"espresso": "ok"}, [], [], NOW)
        self.assertEqual(out["newest_capture_hours"], 168)


class Report(unittest.TestCase):
    def test_escapes(self):
        caps = [listing([post("a", "grinder [click](http://evil.example) <b>?")])]
        text = threads.report(threads.rank(caps, PROFILE, {"espresso": "ok"}, [], [], NOW), NOW)
        self.assertNotIn("](http://evil", text)
        self.assertIn("t3\\_a", text)


if __name__ == "__main__":
    unittest.main()
